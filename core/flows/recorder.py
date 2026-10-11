"""Recording a flow: compile an agent's run into a replayable script.

Chrome's Recorder watches a HUMAN. A human demonstration says what was done
and nothing about what should then be true, which is why every record-replay
tool in this space makes you write the assertions by hand.

This records an AGENT, and an agent narrates its postconditions for free. When
Claude clicks Submit and then calls search_page("Thanks for signing up"), that
observation IS the expected state. The exploratory calls that look like noise
in a transcript are the assertion material -- ReUseIt (IUI '26) spends 15-52
minutes per task family re-running variations to synthesise the same guards,
and reports 24.2% -> 70.1% for having them.

So recording is a COMPILE, not a transcription:

    raw tool calls
      -> drop the dead ends (calls that errored)
      -> keep the state-changing steps
      -> promote the observations that FOLLOWED them into postconditions
      -> rewrite every per-document ref into a declared descriptor
      -> flow file

THE REF REWRITE HAPPENS BEFORE THE CALL, not after. A ref is only meaningful in
the document it came from, and the action is frequently what destroys that
document -- fix #5 is React orphaning mmids mid-form. Capturing the descriptor
afterwards would describe whatever replaced it.
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable, Optional

from .descriptor import build
from . import secrets
from .model import Flow, Step, mutates, ref_paths, get_ref, set_value, slug

# Result-string contracts. These parse the OUTPUT of two tools, which is a
# string contract with mcp_server -- exactly the thing #30 found dead for the
# whole life of `delta` because the server split on "Act on an element" while
# the extension emitted "Act on a row by its ref_N:". tools/test_flows.py FD17
# pins both against the real functions, and they are deliberately NOT anchored
# to the start of the string: a readiness banner (#15) is prepended whenever
# the page is still settling, which is exactly when a flow is most likely to
# be running.
_SEARCH_HITS = re.compile(r"(?m)^(\d+) match\(es\) for ")
_QUERY_TOTAL = re.compile(r"(?m)^(\d+) element\(s\) match ")


# WHEN A TOOL SAYS IT DID NOT DO THE THING. The runner only ever caught
# EXCEPTIONS, and none of these raise: every one is a STRING the tool returns
# while the call itself succeeds. Measured with a fake bridge -- a click
# reported `*** NOT DELIVERED` left the flow PASSING whenever that step carried
# no postcondition, which is a false green in a test runner and the worst
# direction there is. Where a postcondition did catch it, the reported reason
# was `query_elements('tr') counted 0, recorded exactly 5` -- true, useless, and
# #33's class exactly: the cause was sitting in our own output and the message
# did not name it.
#
# THIS IS NOT THE WORDLIST CLASS #24 DELETED, and the distinction is #39's.
# Those read PAGE TEXT, guessing an author's words in languages nobody
# enumerated. These are strings WE emit, in English, from code in this repo --
# a contract with ourselves, the same kind as the two parsers below, and
# mitigated the same way: FD19 pins every one against the file that emits it,
# so a reworded message fails a test instead of silently disarming the guard.
#
# Each phrase is the DISTINCTIVE part of its message rather than a fragment,
# because `fill_form` echoes the page's own validation errors and a short
# fragment could in principle arrive from a site.
REFUSALS = (
    "*** NOT DELIVERED:",                                   # #56, trusted input dropped
    "NAVIGATION DID NOT COMMIT",                            # #40
    "DID NOT MOVE — the tab is still at",                   # #40, back/forward
    "Permission required: ChromeBridge is not allowed",     # the gate
    "ChromeBridge is PAUSED",                               # the kill switch
    "the write reported success but did NOT land",          # #24 readback
)


def refused(result) -> Optional[str]:
    """The tool's own words, when it reported that nothing happened.

    Returns the matched marker, or None. Deliberately NOT a judgement about
    whether the step "worked" -- only whether the tool SAID it did not, which
    is a fact already in hand.
    """
    text = result if isinstance(result, str) else str(result or "")
    for m in REFUSALS:
        if m in text:
            return m
    return None


def search_hits(result: str) -> Optional[int]:
    m = _SEARCH_HITS.search(result or "")
    if m:
        return int(m.group(1))
    return 0 if "No match for" in (result or "") else None


def query_total(result: str) -> Optional[int]:
    """Matches, or None when the answer could not be read at all.

    ZERO IS AN ANSWER. query_elements reports a miss in prose ("No element
    matches …") rather than as "0 element(s) match", so reading only the
    numeric line conflates "nothing matched" with "I could not parse this" --
    and the runner then blames the contract for a page that simply does not
    have the thing. Measured live: a session expiring mid-flow bounced the run
    to the login page, the flow correctly FAILED, and the reason it printed was
    "the result-string contract moved" instead of "counted 0, recorded at
    least 4". search_hits already handled its own miss; this did not, which is
    the asymmetry (#21) rather than a new idea.
    """
    m = _QUERY_TOTAL.search(result or "")
    if m:
        return int(m.group(1))
    return 0 if "No element matches" in (result or "") else None


class Recorder:
    """Buffers raw tool calls; `compile()` turns them into a Flow.

    `entries_fn(tabId) -> list[dict]` fetches the structured collector entries.
    It is injected rather than imported so this module never reaches for the
    bridge itself, and so a test can drive it with a fake that does NOT share
    this file's assumptions (#19).
    """

    def __init__(self, name: str, entries_fn: Callable, origin: str = "",
                 viewport: Optional[dict] = None):
        self.name = name
        self.origin = origin
        # Set by the caller at stop time: a page call, and the only
        # moment the answer is both known and cheap.
        self.viewport = viewport
        self.entries_fn = entries_fn
        self.raw: list = []
        self.started = time.time()
        self.notes: list = []

    # -- during the run ----------------------------------------------------
    async def before(self, tool: str, inp: dict) -> dict:
        """Describe every ref this call is about to consume, while it still means something."""
        paths = ref_paths(tool, inp)
        if not paths:
            return {}
        tab = inp.get("tabId")
        try:
            entries = await self.entries_fn(tab)
        except Exception as exc:
            self.notes.append(f"could not describe refs for {tool}: {exc}")
            return {}
        by_mmid = {str(e.get("mmid")): e for e in entries if e.get("mmid") is not None}
        out = {}
        for p in paths:
            ref = get_ref(inp, p)
            mm = re.sub(r"^ref_", "", str(ref)).strip()
            e = by_mmid.get(mm)
            if e is None:
                self.notes.append(
                    f"{tool}: {ref} is not in the current listing, so this step "
                    f"cannot be described and will be dropped")
                continue
            out[p] = build(e, entries)
        return out

    def after(self, tool: str, inp: dict, result: Any, targets: dict,
              error: Optional[str] = None) -> None:
        self.raw.append({
            "name": tool,
            "input": {k: v for k, v in (inp or {}).items()},
            "targets": targets or {},
            "result": result if isinstance(result, str) else "",
            "error": error,
            "mutates": mutates(tool, inp or {}),
            "ts": time.time(),
        })

    # -- afterwards --------------------------------------------------------
    def compile(self) -> tuple:
        """-> (Flow, report). The report says what was dropped and why."""
        kept, dropped_err, dropped_obs = [], 0, 0

        # An errored call is a dead end -- the agent tried something and it did
        # not work. Replaying it would replay the mistake. ReUseIt turns these
        # into pre-condition checks; that is the obvious next thing to build
        # here and is deliberately NOT guessed at now.
        live = [r for r in self.raw if not r.get("error")]
        dropped_err = len(self.raw) - len(live)

        # Focus is established by the last step that NAMED a ref. That is #43's
        # rule for the batch guard, reused here so `computer(action="type")` --
        # which names nothing and goes wherever focus is -- can be judged from
        # the recording instead of from a second probe of the page.
        focus_target = None
        redacted: list = []
        variables: dict = {}

        def _var(target, path, value):
            """Name a typed form value so replay can override it.

            workflow-use extracts variables from forms the same way. What it
            buys is that running the flow with a different project name is a
            run_flow argument instead of a re-record -- and it is DECLARED
            (the step named a form field), not a guess about which strings
            look parameter-shaped.
            """
            desc = (target or {}).get("full") or (target or {}).get("desc") or {}
            base = slug(desc.get("name") or "") or slug(path) or "value"
            nm, n = base, 2
            while nm in variables and variables[nm] != value:
                nm, n = f"{base}_{n}", n + 1
            variables[nm] = value
            return "{{" + nm + "}}"

        action_ix: list = []   # live index each kept step came from
        hollow: list = []      # (step, checks) that were already true
        for i, r in enumerate(live):
            if not r["mutates"]:
                dropped_obs += 1
                continue
            paths = ref_paths(r["name"], r["input"])
            if paths and len(r["targets"]) != len(paths):
                # A ref we could not describe. Dropping the step is the honest
                # outcome: a step that cannot name its target cannot be
                # replayed, and silently emitting it would fail later with a
                # worse message.
                self.notes.append(
                    f"step {i} ({r['name']}) dropped — {len(paths)} ref(s) to "
                    f"describe, {len(r['targets'])} described")
                continue

            inp = {k: v for k, v in r["input"].items() if k not in ("tabId",)}
            for p in paths:
                if p.startswith("fields."):
                    idx = int(p.split(".", 1)[1])
                    flds = [dict(f) for f in (inp.get("fields") or [])]
                    for k in ("ref", "mmid", "selector"):
                        flds[idx].pop(k, None)
                    inp["fields"] = flds
                else:
                    inp.pop(p, None)

            # A PASSWORD IS NEVER WRITTEN TO THE FILE. Declared by HTML's own
            # type enum (secrets.is_secret), so there is no wordlist and no
            # entropy test; the placeholder names the environment variable the
            # replay must read, which is what makes the file safe to commit.
            for p in paths:
                tgt = r["targets"].get(p)
                if secrets.is_secret(tgt):
                    nm = secrets.env_name(self.name, tgt, p)
                    set_value(inp, p, secrets.placeholder(nm))
                    redacted.append(nm)
                else:
                    from .model import get_value as _gv
                    val = _gv(inp, p)
                    if isinstance(val, str) and val != "":
                        set_value(inp, p, _var(tgt, p, val))
            if paths:
                focus_target = r["targets"].get(paths[-1])
            elif r["name"] == "computer" and \
                    str(r["input"].get("action") or "") in ("type", "key"):
                if secrets.is_secret(focus_target):
                    nm = secrets.env_name(self.name, focus_target, "typed")
                    inp["text"] = secrets.placeholder(nm)
                    redacted.append(nm)

            kept.append(Step(
                name=r["name"], input=inp, targets=r["targets"],
                expect=self._expect_after(live, i),
                on_fail="ask",
                settle_ms=self._settle_after(live, i),
            ))
            action_ix.append(i)

        # AN ASSERTION MUST FOLLOW THE VARIABLE ITS INPUT USES.
        #
        # `_var` parameterises the typed VALUE, and `_checks` records what was
        # OBSERVED -- and until now nothing connected them, so a flow recorded
        # creating "atlas-svc" asserted `search_page("atlas-svc")` forever.
        # Measured: run_flow(vars={"project_name": "beta-svc"}) typed beta-svc
        # and then failed with `search_page('atlas-svc') found 0, recorded at
        # least 1`. That is the headline use of the feature -- "running the
        # flow with a different project name is a run_flow argument instead of
        # a re-record" -- failing on its own example.
        #
        # EXACT EQUALITY ONLY, never substring. Replacing every occurrence of a
        # short value like "Team" inside unrelated prose or a CSS selector is a
        # guess, and the rule #27/#28 settled on is the one that cannot be
        # wrong. The cost is stated rather than hidden: a pattern that merely
        # CONTAINS the value (`search_page("Created atlas-svc")`) keeps the
        # literal and still needs a re-record.
        def _paramize(obj):
            if isinstance(obj, str):
                for nm, val in variables.items():
                    if isinstance(val, str) and val and obj == val:
                        return "{{" + nm + "}}"
                return obj
            if isinstance(obj, dict):
                return {k: _paramize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_paramize(v) for v in obj]
            return obj

        # AN ASSERTION THAT WAS ALREADY TRUE WITNESSES NOTHING.
        #
        # The most dangerous thing this feature can produce is a flow that cannot
        # fail, and it does not look wrong: it passes, in CI, forever. I recorded
        # one TWICE while building this -- a playground flow asserting 4 table rows
        # BEFORE the create and 4 after (the form had silently refused, because two
        # required fields were unfilled), and a saucedemo flow asserting a product
        # name that is on that page whether or not anything was clicked.
        #
        # It is detectable at exactly the moment it can still be fixed cheaply:
        # the agent is here, driving. If a check had the SAME value immediately
        # before the action, that action did not change what the check measures.
        # Said as a warning, never as a refusal -- "already true" is not always
        # wrong (an idempotent step legitimately leaves state alone), and the
        # recorder does not get to overrule the person who drove it.
        for _n, (idx, st) in enumerate(zip(action_ix, kept)):
            if not st.expect:
                continue
            prior = self._checks_before(live, idx)
            same = [k for k, v in st.expect.items() if k in prior and prior[k] == v]
            if same:
                hollow.append((_n, ", ".join(sorted(same))))

        for st in kept:
            if st.expect:
                st.expect = _paramize(st.expect)
        _require = _paramize(self._require_before(live))

        # THE ORIGIN THE FLOW ACTS ON, which was a declared field that nothing
        # ever filled: `_FlowRecorder(name, entries_fn)` is constructed without
        # one, so every flow ever recorded shipped `origin: ""`. Harmless only
        # because run_flows._origins() falls back to parsing step urls -- i.e. a
        # field whose emptiness was covered by a workaround, which is how a
        # contract rots quietly (#30's `delta` and C12). Taken from the first
        # navigate, which is the step that decides where the flow runs.
        if not self.origin:
            for r in live:
                u = (r.get("input") or {}).get("url")
                if isinstance(u, str):
                    m = re.match(r"^(https?://[^/]+)", u)
                    if m:
                        self.origin = m.group(1)
                        break

        flow = Flow(
            name=self.name, origin=self.origin,
            recorded_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            viewport=self.viewport,
            vars=variables, require=_require,
            steps=kept,
        )
        report = {
            "steps": len(kept),
            "dropped_errors": dropped_err,
            "dropped_observations": dropped_obs,
            "asserted": sum(1 for s in kept if s.expect),
            # NAMES ONLY. The report is printed to the agent and lands in a
            # transcript, so it says which secret is needed and never which
            # value was typed.
            "secrets": sorted(set(redacted)),
            "vars": sorted(variables),
            "require": sorted(flow.require),
            "hollow": hollow,
            "notes": self.notes,
        }
        return flow, report

    @staticmethod
    def _checks(records: list) -> dict:
        """Turn a run of OBSERVATIONS into declared checks.

        One function for both directions: the observations after an action are
        its postconditions, and the ones before the first action are what the
        flow expects to start from. Two copies would drift, and they would
        drift silently because each is only exercised by one half of the tests
        (#21).

        Only observations that SUCCEEDED become checks, and only ones whose
        answer is a number or a url -- never the prose of a listing, which
        changes for a hundred innocent reasons. A weak check is worse than
        none, because a flow that cannot fail still reports green.
        """
        exp: dict = {}
        for r in records:
            name, res = r["name"], r["result"] or ""
            if name == "get_url":
                m = re.search(r'"url"\s*:\s*"([^"]+)"', res)
                if m:
                    exp.setdefault("url", m.group(1))
            elif name == "search_page":
                hits = search_hits(res)
                pat = r["input"].get("pattern")
                if hits and pat:
                    # PRESENCE, not the exact tally. A page-wide text search is
                    # genuinely volatile -- a toast saying "Created X"
                    # legitimately turns 1 hit into 2 -- and the question this
                    # check is really asking is "is it there". The observed
                    # count is kept for the reader, not asserted on.
                    exp.setdefault("search",
                                   {"pattern": pat, "min": 1, "observed": hits})
            elif name == "query_elements":
                tot = query_total(res)
                sel = r["input"].get("selector")
                if tot and sel:
                    # EXACT, because that is what was observed. "At least N" is
                    # a weaker claim than the run made and cannot see anything
                    # being ADDED: measured live, a row injected above the
                    # table left the flow green at min=4 against 5 rendered.
                    exp.setdefault("query", {"selector": sel, "count": tot})
        return exp

    @classmethod
    def _expect_after(cls, live: list, i: int) -> dict:
        """Postconditions = what the agent checked NEXT, before acting again."""
        run = []
        for r in live[i + 1:]:
            if r["mutates"]:
                break                       # the next action starts a new state
            run.append(r)
        return cls._checks(run)

    @classmethod
    def _settle_after(cls, live: list, i: int) -> int:
        """Milliseconds the agent actually waited for step i's checks to hold.

        MEASURED, not chosen. The shipped window was a flat 6s, and on a real
        app whose create -> table-refresh cycle takes ~11s the flow reported
        FAILED for an action that had SUCCEEDED -- the record was there, just
        not yet. A false negative is the safe direction and still a wrong
        answer, and the one number that would have fixed it was already in the
        recording: every call is timestamped.

        Only an observation that CONTRIBUTED a check counts, and the LAST of
        them, so a trailing unrelated read does not inflate the bound.
        """
        base = live[i].get("ts") or 0
        last = 0.0
        for r in live[i + 1:]:
            if r["mutates"]:
                break
            if cls._checks([r]):
                last = max(last, r.get("ts") or 0)
        return int(max(0.0, last - base) * 1000) if (last and base) else 0

    @classmethod
    def _checks_before(cls, live: list, i: int) -> dict:
        """The most recent value the agent had seen for each check before step i.

        NOT "the run of observations immediately before", which was the first
        version and was too narrow to catch the case it was written for: the real
        shape is `count rows -> click to open a modal -> fill it -> count rows`,
        so the row count sits two steps back with an action in between, and
        stopping at that action found nothing to compare.

        Scans backwards across actions and takes the LATEST value per check --
        `_checks` uses setdefault, so feeding it reverse-chronologically keeps
        the most recent. The residual false positive is a value an intermediate
        action changed and another changed back, which is worth flagging anyway.
        Used ONLY to ask whether a postcondition witnesses anything.
        """
        return cls._checks([r for r in reversed(live[:i]) if not r["mutates"]])

    @classmethod
    def _require_before(cls, live: list) -> dict:
        """The state the flow EXPECTS TO START FROM.

        Everything the agent observed before it first changed anything. A flow
        whose first step is its own `navigate` establishes its state and needs
        none, which is why this is derived rather than mandatory.
        """
        run = []
        for r in live:
            if r["mutates"]:
                break
            run.append(r)
        return cls._checks(run)
