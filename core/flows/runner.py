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
import time
import uuid
from typing import Any, Callable, Optional

from . import secrets
from .descriptor import Unresolved, build, resolve
from .model import Flow, Step, resolve_vars, set_ref
from .recorder import query_total, search_hits

PASSED, FAILED, NEEDS = "passed", "failed", "needs_decision"

# Live runs, so a resume continues from the stopped step instead of replaying
# the side effects of every step before it.
RUNS: dict = {}


class Run:
    def __init__(self, flow: Flow, tab_id: int, call: Callable, entries_fn: Callable,
                 overrides: Optional[dict] = None):
        self.id = "run_" + uuid.uuid4().hex[:8]
        self.flow = flow
        self.tab_id = tab_id
        self.call = call
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
            try:
                inp, healed = await self._bind(step, binding)
            except Unresolved as exc:
                why = exc.reason + self._surface_note()
                if step.on_fail == "fail":
                    return self._stop(FAILED, f"step {self.i} ({step.name}): {why}",
                                      candidates=exc.candidates)
                return self._stop(NEEDS, why, candidates=exc.candidates)
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

            inp["tabId"] = self.tab_id
            try:
                result = await self.call(step.name, inp)
            except Exception as exc:
                return self._stop(FAILED,
                                  f"step {self.i} ({step.name}) raised: {exc}")

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
    async def _bind(self, step: Step, binding: Optional[str]) -> tuple:
        if not step.targets:
            return dict(step.input), False
        entries = await self.entries_fn(self.tab_id)
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
                ref = resolve(target, entries)
            set_ref(inp, path, f"ref_{ref}")
        return inp, healed

    def _propose_patch(self, step: Step, path: str, ref: str, entries: list) -> None:
        """Write down what the descriptor WOULD become. Never apply it."""
        e = next((x for x in entries if str(x.get("mmid")) == str(ref)), None)
        if e is None:
            return
        self.patches.append({
            "step": self.i, "name": step.name, "path": path,
            "was": step.targets.get(path, {}).get("desc"),
            "now": build(e, entries).get("desc"),
        })

    # ------------------------------------------------------------------
    async def _check(self, step: Step) -> str:
        return await self._verify(step.expect or {})

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
            res = await self.call("get_url", {"tabId": self.tab_id})
            m = re.search(r'"url"\s*:\s*"([^"]+)"', str(res))
            got = m.group(1) if m else str(res)
            if got != exp["url"]:
                return f'url is {got!r}, recorded {exp["url"]!r}'
        if "search" in exp:
            s = exp["search"]
            res = await self.call("search_page",
                                  {"tabId": self.tab_id, "pattern": s["pattern"]})
            hits = search_hits(str(res))
            if hits is None:
                return (f'could not read a hit count out of search_page for '
                        f'{s["pattern"]!r} — the result-string contract moved')
            if hits < s["min"]:
                return (f'search_page({s["pattern"]!r}) found {hits}, '
                        f'recorded at least {s["min"]}')
        if "query" in exp:
            q = exp["query"]
            res = await self.call("query_elements",
                                  {"tabId": self.tab_id, "selector": q["selector"],
                                   "max_results": 1})
            tot = query_total(str(res))
            if tot is None:
                return (f'could not read a total out of query_elements for '
                        f'{q["selector"]!r} — the result-string contract moved')
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
            "log": self.log, "patches": self.patches,
            "seconds": round(self.elapsed, 2),
        }


async def start(flow: Flow, tab_id: int, call: Callable, entries_fn: Callable,
                overrides: Optional[dict] = None) -> dict:
    return await Run(flow, tab_id, call, entries_fn, overrides).go()


async def resume(run_id: str, binding: str) -> dict:
    run = RUNS.get(run_id)
    if run is None:
        raise KeyError(
            f"no paused run {run_id!r} — it finished, or the server restarted. "
            f"Start the flow again.")
    return await run.go(binding=binding)
