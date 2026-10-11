"""Replaying a flow: deterministic by default, the agent only where needed.

THE ESCALATION IS SHAPED BY THIS PROJECT'S ARCHITECTURE, and it comes out
better for it. Stagehand's selfHeal and workflow-use's fallback both call a
model from inside the library. ChromeBridge holds NO LLM key -- Claude Code is
the agent loop -- so "ask the agent" cannot mean an internal model call. It
means the runner STOPS and hands back a precise question with the candidates,
and Claude answers by resuming the run with a binding.

That is strictly more honest than an internal heal: the decision appears in the
transcript, it costs a visible turn, and nothing is re-bound behind the user's
back.

THREE RULES THAT ARE NOT NEGOTIABLE, each paid for by someone else's bug:

  1. A postcondition is checked LIVE on every run and is NEVER healed or
     cached. Midscene caches planning and location and deliberately never
     caches aiAssert/aiQuery; the moment a check can adapt to what it finds,
     the suite cannot fail and is worth less than no suite (#15: a probe that
     never fires looks identical to all settled).
  2. A step that was rebound still has to satisfy the ORIGINAL postcondition.
     Stagehand practitioners' warning is that a self-heal can quietly bind to
     the wrong control; the postcondition is what catches that, so relaxing it
     alongside the heal defeats the only guard there is.
  3. A rebinding PROPOSES a patch; it never edits the flow. ReUseIt's own LLM
     judge agreed with a human at kappa=0.528, and workflow-use calls its
     fallback "currently really bad". The patch diff is also the more useful
     artefact: it IS the report that the frontend moved.
"""
from __future__ import annotations

import re
import asyncio
import json
import time
import uuid
from typing import Any, Callable, Optional

from . import secrets
from .descriptor import Unresolved, build, resolve
from .model import Flow, Step, resolve_vars, set_ref
from .recorder import (query_first_attrs, query_first_text, query_total,
                       refused, search_hits)

PASSED, FAILED, NEEDS = "passed", "failed", "needs_decision"

# Live runs, so a resume continues from the stopped step instead of replaying
# the side effects of every step before it.
RUNS: dict = {}


def _as_list(v) -> list:
    """One check or several. A step may assert on several selectors or several
    patterns since #63/D5; files recorded before that carry a bare dict, and
    both shapes read the same way here rather than needing a schema bump."""
    if v is None:
        return []
    return list(v) if isinstance(v, list) else [v]


def _created_tab(result) -> Optional[int]:
    """The tab id `tabs_create_mcp` just made, or None if it cannot be read.

    The tool answers with JSON, but a result-string contract is exactly what
    kept `delta` dead for its whole life (#30), so this accepts the parsed
    shape as well and refuses to guess when neither is there -- the caller
    stops rather than silently carrying on in the old tab.
    """
    if isinstance(result, dict):
        v = result.get("tabId")
        return int(v) if v is not None else None
    try:
        return int((json.loads(result) or {}).get("tabId"))
    except Exception:
        pass
    m = re.search(r'"tabId"\s*:\s*(\d+)', str(result or ""))
    return int(m.group(1)) if m else None


class Run:
    def __init__(self, flow: Flow, tab_id: int, call: Callable, entries_fn: Callable,
                 overrides: Optional[dict] = None, viewport_fn: Optional[Callable] = None):
        self.id = "run_" + uuid.uuid4().hex[:8]
        self.flow = flow
        self.tab_id = tab_id
        # THE TAB THE FLOW IS CURRENTLY ACTING IN, which is not always the one it
        # started in. A flow may create a tab mid-run -- `tabs_create_mcp` is
        # already an ACTION (it is in MUTATES) so the recorder keeps it -- and
        # every later step belongs in the tab it made. Forcing `tab_id` on every
        # step meant a recorded `tabs_create_mcp` made a tab that was then
        # ignored, so the flow carried on in the old one: the batch had exactly
        # this defect until #46, with exactly this consequence.
        #
        # It matters beyond tidiness because #56's one VERIFIED recovery from a
        # tab that has lost its trusted-input channel IS a new tab, and a flow
        # could not perform it.
        self.cur_tab = tab_id
        self.call = call
        self.viewport_fn = viewport_fn
        self.entries_fn = entries_fn
        self.i = 0
        # Recorded defaults, overridden per run. A flow that creates a record
        # needs a different name on the second run, and that is an argument
        # rather than a re-record.
        self.vars = dict(flow.vars or {})
        self.vars.update(overrides or {})
        self.checked_require = False
        self.log: list = []
        self.patches: list = []
        # Steps that resolved on their DECLARED DESTINATION after the recorded
        # descriptor stopped matching (#61). Not a rebind -- no decision was
        # asked for and nothing was guessed -- but not a clean pass either, so
        # it is reported separately from both.
        self.drifted: list = []
        self._last_entries: list = []
        self.started = time.time()
        # Accumulated EXECUTION time, not wall time. A paused run waits for a
        # human (or an agent turn), and billing that to the flow turns the one
        # number people will quote -- "it replays in 0.25s" -- into whatever
        # the reviewer had for lunch. Measured live: a resumed run reported
        # 8.59s for 0.3s of work.
        self.elapsed = 0.0

    # ------------------------------------------------------------------
    async def go(self, binding: Optional[str] = None) -> dict:
        """Run from the current step. `binding` answers the question that stopped us."""
        self._t0 = time.time()

        # THE PRECONDITION, BEFORE ANYTHING RUNS. Without it a flow pointed at
        # the wrong starting state fails deep inside with a message about one
        # element -- measured live, a flow that begins at a login page was run
        # while already signed in, and step 1 reported "no element matches
        # tag='button' name='Sign in'", which describes the symptom of being on
        # a page the flow never expected. Checking first turns that into one
        # sentence about the app's state.
        if not self.checked_require and self.flow.require:
            self.checked_require = True
            bad = await self._verify(self.flow.require)
            if bad:
                return self._stop(FAILED,
                                  f"the app is not in the state this flow starts "
                                  f"from: {bad}. Nothing was run.")
        self.checked_require = True

        while self.i < len(self.flow.steps):
            step = self.flow.steps[self.i]
            # A TARGET GETS THE SAME WINDOW A POSTCONDITION DOES.
            #
            # #55 gave postconditions a bounded window to BECOME true and left
            # resolution asking once, which is the wrong half for a real app:
            # measured on a live SPA, step 1 failed on `name='Investors 38'`
            # because mid-render the tab's accessible name is still "Investors"
            # -- the count had not arrived yet. The control was not missing, it
            # was not there YET, and one attempt reports those identically.
            #
            # Same bound, same poll and the same reasoning as `_check`: nothing
            # is weakened, since the target must still resolve and within the
            # bound, and a genuinely absent control still fails, just later.
            # `_bind` re-fetches the entries on each attempt, so this is a retry
            # rather than a sleep over one stale snapshot.
            deadline = time.time() + self.SETTLE_MS / 1000.0
            unresolved = None
            while True:
                try:
                    # THE RECORDED DESCRIPTOR GETS ITS WHOLE WINDOW FIRST, and
                    # the declared destination is not offered inside it. Found
                    # live on the first real-app run of the fallback: the step
                    # resolved on href in 3.87s and reported the name had moved
                    # from 'Investors 43' to 'Investors' -- which is not a drift
                    # at all, it is the badge not having rendered yet, and the
                    # proposed patch would have written the MID-RENDER name into
                    # the flow. "Not there yet" and "the label changed" are
                    # exactly the two things #59 added this window to tell
                    # apart, and offering the alternate on the first attempt
                    # collapsed them again one entry later.
                    inp, healed = await self._bind(step, binding, allow_alt=False)
                    unresolved = None
                    break
                except Unresolved as exc:
                    unresolved = exc
                    if time.time() >= deadline:
                        break
                    await asyncio.sleep(self.POLL_MS / 1000.0)
                except Exception as exc:
                    # READING THE PAGE CAN FAIL FOR REASONS THAT ARE NOT THE
                    # TARGET. Only Unresolved was caught, so a bridge or gate
                    # error escaped `start()` entirely and the caller reported
                    # it with a hardcoded at:0 — measured on a CI run, where a
                    # navigate that did not commit left the tab at about:blank
                    # and the run surfaced `cannot act on about:blank
                    # [op=get_interactive_elements]` with no step named and a
                    # step count of 0/4, two steps after the actual cause. The
                    # step is named now, and the preceding step's result is
                    # already in the log, which is what points at the navigate.
                    return self._stop(FAILED,
                                      f"step {self.i} ({step.name}): could not read "
                                      f"the page to resolve its target — {exc}")
            if unresolved is not None:
                # The window is spent and the recorded descriptor never matched.
                # NOW the name really has changed, so ask the destination.
                try:
                    inp, healed = await self._bind(step, binding, allow_alt=True)
                    unresolved = None
                except Unresolved:
                    pass
            if unresolved is not None:
                why = unresolved.reason + self._surface_note() \
                    + await self._viewport_note()
                # The enum is validated at LOAD (model.ON_FAIL), so there is
                # no third value to fall through here. There used to be:
                # "heal" was declared, never written, never branched on, and a
                # flow asking for it got "ask" in silence.
                if step.on_fail == "fail":
                    return self._stop(FAILED, f"step {self.i} ({step.name}): {why}",
                                      candidates=unresolved.candidates)
                return self._stop(NEEDS, why, candidates=unresolved.candidates)
            binding = None

            # VARIABLES FIRST, then secrets -- a variable is an ordinary
            # parameter and may be printed; a secret may not, so it is resolved
            # last and exists only for this one call.
            inp, unknown = resolve_vars(inp, self.vars)
            if unknown:
                return self._stop(FAILED,
                                  f"step {self.i} ({step.name}): this flow has no "
                                  f"value for {', '.join(sorted(set(unknown)))} — "
                                  f"pass it to run_flow, or re-record.")
            inp, missing = secrets.resolve(inp)
            if missing:
                return self._stop(FAILED,
                                  f"step {self.i} ({step.name}): "
                                  + secrets.missing_message(missing))

            inp["tabId"] = self.cur_tab
            try:
                result = await self.call(step.name, inp)
            except Exception as exc:
                return self._stop(FAILED,
                                  f"step {self.i} ({step.name}) raised: {exc}")

            # A TOOL THAT SAID IT DID NOT ACT STOPS THE FLOW HERE, rather than
            # being left for a postcondition that may not exist. None of these
            # raise -- the call succeeds and returns a string saying nothing
            # happened -- so until now a dead click left the run PASSING unless
            # some later assertion happened to catch it. The tool's own words
            # already carry the cause and the recovery; repeating them beats
            # reporting `counted 0, recorded 5` two steps later (#33).
            _ref = refused(result)
            if _ref:
                return self._stop(FAILED,
                                  f"step {self.i} ({step.name}) reported that it did "
                                  f"NOT act — the flow stopped rather than asserting "
                                  f"against a page nothing was done to.\n  the tool "
                                  f"said: {str(result).strip()[:400]}")

            # A TAB THIS FLOW JUST MADE IS THE TAB THIS FLOW MEANT -- the same
            # rule browser_batch threads (#46), and deliberately the same shape:
            # only `tabs_create_mcp` sets it, because it returns exactly one id
            # it just created, where `tabs_context_mcp` returns the whole group
            # and choosing among several would be a guess.
            if step.name == "tabs_create_mcp":
                made = _created_tab(result)
                if made is None:
                    return self._stop(FAILED,
                                      f"step {self.i} (tabs_create_mcp): no tab id came "
                                      f"back, so every later step would have run in the "
                                      f"previous tab without saying so.")
                self.cur_tab = made

            bad = await self._check(step)
            if bad:
                # NOT escalated, on purpose. A failed postcondition is the
                # RESULT of the run, not an obstacle to getting through it.
                return self._stop(FAILED, f"step {self.i} ({step.name}): {bad}")

            self.log.append({"step": self.i, "name": step.name, "ok": True,
                             "healed": healed,
                             "asserted": sorted(step.expect) or None})
            self.i += 1

        return self._stop(PASSED, "")

    async def _viewport_note(self) -> str:
        """Name a size difference, but only while explaining a failure.

        A flow recorded wide and replayed narrow can meet a responsive layout
        where the target genuinely does not exist -- a nav bar that became a
        hamburger -- and "no element matches" is then true and useless, the same
        shape `_surface_note` exists for.

        NO THRESHOLD, and that is deliberate: a "material" difference would be a
        chosen number, and #27/#28 took those out of the paths that decide
        things. Any difference is reported, and it is only reported HERE, on a
        resolve failure, where the reader is already looking for causes. A note
        that fired on every run because the window was two pixels narrower would
        be the noise #15 priced.

        Fetched lazily and only on failure, so a passing flow pays nothing --
        #38's rule that a round trip is taken where its answer can change what
        happens next.
        """
        rec = self.flow.viewport or {}
        if not rec.get("width") or not self.viewport_fn:
            return ""
        try:
            live = await self.viewport_fn(self.cur_tab)
        except Exception:
            return ""
        if not live or not live.get("width"):
            return ""
        # WIDTH ONLY, and that is the whole correction. Comparing both fired on a
        # 56px HEIGHT difference between two tabs of the same window (1512x812
        # against 1512x868) -- browser chrome, not a responsive break -- which is
        # the noise #15 priced, produced by my own no-threshold choice in exactly
        # the commonest case. Width is still threshold-free: CSS media queries
        # are overwhelmingly width-based, so width is the dimension that decides
        # whether a control EXISTS, and it does not drift between tabs.
        if int(live["width"]) == int(rec["width"]):
            return ""
        return (f" The window is also a different WIDTH than when this was recorded: "
                f"{int(live['width'])}px now against {int(rec['width'])}px then. A "
                f"responsive layout can genuinely not have this control at one of "
                f"those widths.")

    def _surface_note(self) -> str:
        """Name the cause when it is sitting in our own output.

        "no element matches tag='textarea'" is a true and useless sentence when
        the real answer is "a dropdown is open". An open listbox/menu/dialog
        marks the REST of the document aria-hidden, so the collector correctly
        drops everything behind it and every descriptor stops resolving at once
        -- #23 and #33 both record live agents being sent hunting by exactly
        this. #33's rule is the one applied here: look for the popup surface in
        what is ALREADY listed, name it when it is there, and say nothing when
        it is not. Never assert a cause that has not been observed (C15).

        MEASURED LIVE on the first replay of the first recorded flow: a
        form_input on a Radix combobox left its listbox open, the next run
        failed at step 0 on an unrelated textarea, and the message named
        neither the popover nor the recovery.
        """
        try:
            open_surfaces = [e for e in (self._last_entries or [])
                             if (e.get("role") or "") in ("listbox", "menu", "dialog")]
        except Exception:
            return ""
        if not open_surfaces:
            return ""
        roles = sorted({e.get("role") for e in open_surfaces})
        return (f" — NOTE: an open {'/'.join(roles)} IS listed on this page, and an "
                f"open popup surface marks the rest of the document aria-hidden, so "
                f"every other descriptor stops resolving at once. Dismiss it (Escape) "
                f"and re-run before concluding the control is gone.")

    # ------------------------------------------------------------------
    async def _bind(self, step: Step, binding: Optional[str],
                    allow_alt: bool = True) -> tuple:
        if not step.targets:
            return dict(step.input), False
        entries = await self.entries_fn(self.cur_tab)
        self._last_entries = entries
        inp = dict(step.input)
        healed = False
        for path, target in step.targets.items():
            if binding is not None:
                ref = re.sub(r"^ref_", "", str(binding)).strip()
                healed = True
                self._propose_patch(step, path, ref, entries)
                binding = None
            else:
                notes: list = []
                ref = resolve(target, entries, notes if allow_alt else None,
                              allow_alt=allow_alt)
                for n in notes:
                    self.drifted.append({"step": self.i, "name": step.name,
                                         "path": path, "via": n["via"],
                                         "was": n["was"], "alt": n["alt"]})
                    self._propose_patch(step, path, ref, entries)
            set_ref(inp, path, f"ref_{ref}")
        return inp, healed

    def _propose_patch(self, step: Step, path: str, ref: str, entries: list) -> None:
        """Write down what the descriptor WOULD become. Never apply it."""
        e = next((x for x in entries if str(x.get("mmid")) == str(ref)), None)
        if e is None:
            return
        built = build(e, entries)
        self.patches.append({
            "step": self.i, "name": step.name, "path": path,
            "was": step.targets.get(path, {}).get("desc"),
            "now": built.get("desc"),
            # THE WHOLE REBUILT TARGET, not only the part shown. A patch that
            # carries the display diff and nothing else cannot be APPLIED --
            # `full`, the ordinal and the href alternate all move with the
            # descriptor, and replacing only `desc` would leave a target
            # describing two different page states at once.
            "target": built,
        })

    # ------------------------------------------------------------------
    # How long a POSTCONDITION may take to become true, and how often it is
    # re-asked. Not a settle delay: a check that holds immediately costs one
    # evaluation and no wait at all.
    SETTLE_MS = 6000
    POLL_MS = 400

    async def _check(self, step: Step) -> str:
        """A postcondition gets a bounded window to BECOME true.

        Found by recording against a real app. The recorder captures what the
        agent observed, which is necessarily after the agent took a moment; the
        runner asked instantly, so a flow recorded on saucedemo failed every
        replay with `search_page('Sauce Labs Backpack') found 0, recorded at
        least 1` -- the login had worked and the SPA simply had not painted the
        grid yet. The url and row-count checks passed because they are true the
        moment the document commits; the text search is true a few hundred
        milliseconds later. Server-rendered fixtures never show this, which is
        why a year of playground flows did not.
        
        THIS DOES NOT WEAKEN THE ASSERTION. It must still become true, and
        within a bound; what changes is that "not yet" stops being reported as
        "not at all". Every retrying test runner works this way (Playwright's
        auto-waiting assertions, Cypress's retry-ability) for the same reason.
        The falsifier is unaffected -- a login that genuinely failed never
        reaches the recorded url, so it still fails, just later.
        """
        exp = step.expect or {}
        if not exp:
            return ""
        # THE DEFAULT PLUS WHAT THIS APP ACTUALLY NEEDED. `settle_ms` is the
        # time the recording measured between this action and its checks
        # holding, so an app that answered instantly keeps the plain default
        # and a slow one gets the margin it demonstrated. A flow recorded
        # before this existed carries 0 and is unchanged.
        deadline = time.time() + (self.SETTLE_MS + (step.settle_ms or 0)) / 1000.0
        while True:
            bad = await self._verify(exp)
            if not bad or time.time() >= deadline:
                return bad
            await asyncio.sleep(self.POLL_MS / 1000.0)

    async def _verify(self, exp: dict) -> str:
        """Every assertion, live. Returns '' when they all hold.

        Used for BOTH the flow's precondition and each step's postcondition:
        the same declared checks, asked at two different moments. Two copies
        would drift and each would be exercised by only half the tests (#21).

        VARIABLES ARE RESOLVED HERE TOO, not only in the inputs. An assertion
        that kept the recorded literal while the input took an override is a
        flow that types one thing and checks for another -- which is how
        `run_flow(vars={"project_name": "beta-svc"})` failed on the very flow
        that feature exists for. Resolved at the same point and in the same
        order as the input (variables, then the live call), so there is one
        rule rather than two.
        """
        exp, _unknown = resolve_vars(exp or {}, self.vars)
        if "url" in exp:
            res = await self.call("get_url", {"tabId": self.cur_tab})
            m = re.search(r'"url"\s*:\s*"([^"]+)"', str(res))
            got = m.group(1) if m else str(res)
            if got != exp["url"]:
                return f'url is {got!r}, recorded {exp["url"]!r}'
        for s in _as_list(exp.get("search")):
            _call = {"tabId": self.cur_tab, "pattern": s["pattern"]}
            for _k in ("regex", "css_scope", "case_sensitive"):
                if s.get(_k):
                    _call[_k] = s[_k]
            res = await self.call("search_page", _call)
            hits = search_hits(str(res))
            if hits is None:
                return (f'could not read a hit count out of search_page for '
                        f'{s["pattern"]!r} — the result-string contract moved')
            # ABSENCE IS AN ASSERTION. Recorded when the agent looked and found
            # nothing, which is half of what a UI test checks -- a dialog
            # closed, an error cleared, a row deleted (#63/D13).
            if s.get("absent"):
                if hits:
                    return (f'search_page({s["pattern"]!r}) found {hits}, and the '
                            f'recording found NONE — this step is supposed to make '
                            f'that text go away')
                continue
            if hits < s.get("min", 1):
                return (f'search_page({s["pattern"]!r}) found {hits}, '
                        f'recorded at least {s["min"]}')
        for q in _as_list(exp.get("query")):
            _qc = {"tabId": self.cur_tab, "selector": q["selector"], "max_results": 1}
            if q.get("attrs"):
                _qc["attributes"] = sorted(q["attrs"])
            res = await self.call("query_elements", _qc)
            tot = query_total(str(res))
            if tot is None:
                return (f'could not read a total out of query_elements for '
                        f'{q["selector"]!r} — the result-string contract moved')
            # THE TEXT THAT WAS READ, when one was recorded. Without this a
            # content check degrades to an existence check and the step cannot
            # fail (#63/D17). Compared with `in` rather than `==`: the recorded
            # string came from this same renderer, and a surrounding label the
            # page adds later should not break a step whose point is the value.
            if q.get("text") is not None and tot:
                got = query_first_text(str(res))
                if got is None or q["text"] not in got:
                    return (f'query_elements({q["selector"]!r}) reads '
                            f'{(got if got is not None else "(no text)")!r}, '
                            f'recorded {q["text"]!r}')
            # AND THE ATTRIBUTES THAT WERE READ. Where `text` covers an element
            # that shows its state, this covers the one that holds it -- a
            # field's `value` is an attribute, not a text node, so without this
            # every typing step asserts only that the field exists.
            if q.get("attrs") and tot:
                got = query_first_attrs(str(res))
                for _k, _v in q["attrs"].items():
                    if got.get(_k) != _v:
                        return (f'query_elements({q["selector"]!r}) reads '
                                f'{_k}={got.get(_k)!r}, recorded {_v!r}')
            # `count` is the recorded observation and must match exactly;
            # `min` is the hand-relaxed form for a list that legitimately grows.
            if "count" in q and tot != q["count"]:
                # A COUNT THAT GREW IS THE COMMONEST WAY A FLOW FAILS ON ITS
                # SECOND RUN, and the bare numbers do not say so. A flow that
                # CREATES something changes the count it recorded, so replaying
                # it in place leaves the app one row further on every time --
                # measured: run 1 passes, run 2 fails here with 5 against 4.
                # That is not a defect in the flow, it is what a mutating test
                # needs a fixture reset for (`run_flows.py --playground` does
                # one, which is why CI never sees it).
                #
                # STATED AS A CAUSE AMONG CAUSES, never as the diagnosis: the
                # count also grows when someone else is using the app, when a
                # seed changed, or when the page genuinely regressed. #33's
                # rule, and the one C15 exists to enforce -- a note that picks
                # a cause is how three earlier messages sent agents the wrong
                # way.
                grew = ("  The count GREW. Causes that need different answers: "
                        "a previous run of this flow left its own rows behind "
                        "(replay against a reset fixture, or record a flow that "
                        "cleans up after itself); the data changed underneath; "
                        "or the page really does render more now."
                        if tot > q["count"] else "")
                return (f'query_elements({q["selector"]!r}) counted {tot}, '
                        f'recorded exactly {q["count"]}' + grew)
            if "min" in q and tot < q["min"]:
                return (f'query_elements({q["selector"]!r}) counted {tot}, '
                        f'recorded at least {q["min"]}')
        return ""

    # ------------------------------------------------------------------
    def _stop(self, status: str, reason: str, candidates: Optional[list] = None) -> dict:
        self.elapsed += time.time() - getattr(self, "_t0", time.time())
        if status != NEEDS:
            RUNS.pop(self.id, None)
        else:
            RUNS[self.id] = self
        return {
            "status": status, "run_id": self.id, "flow": self.flow.name,
            "at": self.i, "of": len(self.flow.steps), "reason": reason,
            "candidates": candidates or [],
            "log": self.log, "patches": self.patches, "drifted": self.drifted,
            "seconds": round(self.elapsed, 2),
        }


async def start(flow: Flow, tab_id: int, call: Callable, entries_fn: Callable,
                overrides: Optional[dict] = None,
                viewport_fn: Optional[Callable] = None) -> dict:
    return await Run(flow, tab_id, call, entries_fn, overrides, viewport_fn).go()


async def resume(run_id: str, binding: str) -> dict:
    run = RUNS.get(run_id)
    if run is None:
        raise KeyError(
            f"no paused run {run_id!r} — it finished, or the server restarted. "
            f"Start the flow again.")
    return await run.go(binding=binding)
