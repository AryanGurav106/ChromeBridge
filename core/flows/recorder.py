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
from .model import Flow, Step, mutates, ref_paths, get_ref

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

    def __init__(self, name: str, entries_fn: Callable, origin: str = ""):
        self.name = name
        self.origin = origin
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

            kept.append(Step(
                name=r["name"], input=inp, targets=r["targets"],
                expect=self._expect_after(live, i),
                on_fail="ask",
            ))

        flow = Flow(
            name=self.name, origin=self.origin,
            recorded_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            steps=kept,
        )
        report = {
            "steps": len(kept),
            "dropped_errors": dropped_err,
            "dropped_observations": dropped_obs,
            "asserted": sum(1 for s in kept if s.expect),
            "notes": self.notes,
        }
        return flow, report

    @staticmethod
    def _expect_after(live: list, i: int) -> dict:
        """Postconditions = what the agent checked NEXT, before acting again.

        Only observations that actually SUCCEEDED become assertions, and only
        ones whose answer is a number or a url -- never the prose of a listing,
        which changes for a hundred innocent reasons. A weak assertion is worse
        than none, because a flow that cannot fail still reports green.
        """
        exp: dict = {}
        for r in live[i + 1:]:
            if r["mutates"]:
                break                       # the next action starts a new state
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
                    # genuinely volatile -- a toast saying "Created echo-gateway"
                    # legitimately turns 1 hit into 2 -- and the question this
                    # assertion is really asking is "is it there". The observed
                    # count is kept for the reader, not asserted on.
                    exp.setdefault("search",
                                   {"pattern": pat, "min": 1, "observed": hits})
            elif name == "query_elements":
                tot = query_total(res)
                sel = r["input"].get("selector")
                if tot and sel:
                    # EXACT, because that is what was observed. Recording "at
                    # least N" is a weaker claim than the run actually made, and
                    # it cannot see anything being ADDED: measured live, a row
                    # injected above the table left the flow green at min=4
                    # against 5 rendered. A count that legitimately grows is a
                    # real case -- edit the file to {"min": N} for it -- but the
                    # default must be the observation, or the flow quietly stops
                    # being able to fail (#15).
                    exp.setdefault("query", {"selector": sel, "count": tot})
        return exp
