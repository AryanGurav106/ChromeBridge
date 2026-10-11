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

import json
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
# ONE TOKEN, NOT A LIST OF WORDINGS. The first version enumerated the prose a
# tool prints when it did not act, and was incomplete within a day:
# `form_input(radio, true)` answers "no radio in this group is labelled" and
# that was not in it, so a call that changed nothing was compiled into a test
# as a real step. Enumerating messages is the open-ended-list failure this
# codebase removes everywhere else -- the next wording is always one away.
#
# The fill ops already decide this: they return {ok: false, msg}. The router
# now renders that branch with a single `NOT DONE: ` token, so one marker
# covers every wording it will ever have. The bare word WARNING could not be
# the token because it is also APPENDED to clicks that DID land (the hit-test
# echo, and "click had NO detectable effect").
#
# What remains below is the set that is NOT a fill result -- a refusal from the
# gate, a dead input channel, a navigation that never committed. Each is a
# distinct op reporting a distinct fact, and FD19 pins every one against the
# file that emits it.
REFUSALS = (
    "NOT DONE: ",                                           # the fill family, one token
    "*** NOT DELIVERED:",                                   # #56, trusted input dropped
    "NAVIGATION DID NOT COMMIT",                            # #40
    "DID NOT MOVE — the tab is still at",                   # #40, back/forward
    "Permission required: ChromeBridge is not allowed",     # the gate
    "ChromeBridge is PAUSED",                               # the kill switch
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


_ROW = re.compile(r'(?m)^\s*<[^>\n]*>\s+(?=")')


def query_first_text(result: str) -> Optional[str]:
    """The TEXT of the first element query_elements printed, or None.

    The tool already returns it -- `<div ref_9> "Durian" aria-expanded="false"`
    -- and the recorder threw it away, so an agent that checked an element's
    CONTENT recorded only how many matched (#63/D17). Measured live: the flow
    with the strongest summary line in the whole eval ("5 of 5 steps had their
    postconditions checked") asserted `#combo1 == 1` on the two steps that pick
    an option, which is true on an untouched page.

    Parsed with a real JSON decoder rather than a quote-to-quote regex, because
    the renderer now emits the text json-quoted for exactly this reason: a
    label containing a double quote has to come back whole.
    """
    m = _ROW.search(result or "")
    if not m:
        return None
    try:
        txt, _ = json.JSONDecoder().raw_decode(result[m.end():])
    except ValueError:
        return None
    return txt if isinstance(txt, str) and txt.strip() else None


# The attribute row anchor is DELIBERATELY not `_ROW`: that one requires a
# quoted text immediately after the tag, and an <input> prints `(no text)` --
# which is exactly the element whose attributes matter most here.
_ROW_ANY = re.compile(r'(?m)^\s*<[^>\n]*>')
_ATTR = re.compile(r'\s([A-Za-z_][\w:.@-]*)=(?=")')


def query_first_attrs(result: str) -> dict:
    """The ATTRIBUTES query_elements printed for its first element.

    D1 made a typed value readable -- `attributes=["value"]` on a field holding
    typed text returns `value="Ada Lovelace"` -- and D17 made a single-match
    query keep what it read. The two were built separately and did not meet:
    D17 keeps `text`, and an <input> HAS no text, so its value arrived in the
    ATTRIBUTES and the recording stored existence. Measured in round two of the
    #63 eval: all three typing steps on the httpbin form recorded
    `{"selector": "input[name=custname]", "count": 1}`, which is true whether or
    not anything was typed, while the agent had the value in hand twice over.
    """
    m = _ROW_ANY.search(result or "")
    if not m:
        return {}
    line = (result[m.end():].split("\n") or [""])[0]
    # skip the element's own text, which the row prints first
    dec = json.JSONDecoder()
    try:
        _txt, off = dec.raw_decode(line)
        line = line[off:]
    except ValueError:
        pass
    out: dict = {}
    for am in _ATTR.finditer(line):
        try:
            val, _ = dec.raw_decode(line[am.end():])
        except ValueError:
            continue
        if isinstance(val, str):
            out[am.group(1)] = val
    return out


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
        # ...AND SO IS A CALL THAT RETURNED A WARNING INSTEAD OF ACTING. None
        # of those raise: the call succeeds and returns a string saying nothing
        # happened, so `form_input(ref, 25)` answering `WARNING: no option
        # matching "25.0"` was compiled into the flow TWICE as a real step,
        # while the report said `dropped: 0 failed call(s)` (#63/D7). #62
        # taught the RUNNER to stop on these strings; a string meaning "this
        # did not happen" has to mean the same thing at record time.
        live = [r for r in self.raw
                if not r.get("error") and not (r.get("mutates") and refused(r.get("result")))]
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
        # AN ABSENCE IS ONLY EVIDENCE IF THE THING WAS SEEN. D13 made a zero a
        # real answer so a disappearance could be asserted -- and the same
        # change promoted every MISTYPED search during recording to a
        # permanent contract. Measured in round two: an agent searched the
        # straight-apostrophe form of a sentence the page renders with a curly
        # one, got nothing, corrected itself, and the flow recorded
        # `{"pattern": "…you're…", "absent": true}` beside the working check.
        # A typo became a requirement that the typo must never appear.
        #
        # #57's rule separates them and needs no new signal: `.modal.show` was
        # observed at 1 BEFORE the Close, so its 0 afterwards witnesses a real
        # disappearance; the mistyped pattern was never seen non-zero anywhere,
        # so its absence witnesses nothing. Dropped and NAMED, never silently:
        # an agent that really meant it can re-record deliberately.
        unwitnessed: list = []
        for _n, (idx, st) in enumerate(zip(action_ix, kept)):
            if st.expect:
                ever = self._checks([r for r in live[:idx] if not r["mutates"]])
                # ASKED EXPLICITLY, because `1 in (True, 0)` is True in Python
                # -- a terser emptiness test read a count of ONE as a miss and
                # dropped the very disappearance it was written to keep.
                seen = {k for k, v in self._check_items(ever).items()
                        if not self._is_empty(k, v)}
                drop = [key for key, val in self._check_items(st.expect).items()
                        if self._is_empty(key, val) and key not in seen]
                for key in drop:
                    unwitnessed.append((_n, key[0], key[1]))
                    self._drop_check(st.expect, key)
        for _n, (idx, st) in enumerate(zip(action_ix, kept)):
            if not st.expect:
                continue
            prior = self._checks_before(live, idx)
            # PER CHECK, not per KIND. Since a step may now carry several
            # checks of one kind, comparing `expect["query"]` wholesale missed
            # a step where only one of them was hollow -- and reporting a
            # partial hollow as "this flow would pass even if the step did
            # nothing" asserts more than is known (#63 round two, R2-D4).
            now, before = self._check_items(st.expect), self._check_items(prior)
            same = sorted(k for k, v in now.items() if k in before and before[k] == v)
            if same:
                hollow.append((_n, ", ".join(x[0] for x in same), len(same) == len(now)))

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
            "unwitnessed_absence": unwitnessed,
            "notes": self.notes,
        }
        return flow, report

    @staticmethod
    def _checks(records: list, keep_first: bool = False) -> dict:
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

        THREE THINGS THE GENERALITY EVAL (#63) FOUND HERE, all in `setdefault`:

        * ZERO IS AN ANSWER and it was being thrown away. `if hits`/`if tot`
          treats a miss as nothing observed, so an observation that something
          is GONE could not become an assertion -- an agent confirmed a modal
          had closed three separate ways and all three were discarded, leaving
          a step that passes if Close does nothing. `query_total`'s own
          docstring argues zero must be distinguishable from an unreadable
          result, and returns 0 rather than None for exactly that; this
          collapsed them again one function later.
        * THE FIRST OBSERVATION WON, so a stale read beat a fresh one. After a
          navigating click the first `get_url` read the document being
          REPLACED; the agent re-read it a moment later and got the right one;
          the recorder kept the first and baked a wrong url into the flow.
          Later is strictly more settled, and everything before the next ACTION
          still belongs to this step -- so last wins. `keep_first` is for
          `_checks_before`, which feeds records in REVERSE and therefore wants
          the first it encounters.
        * ONE SLOT PER KIND discarded the rest. Two `query_elements` after one
          action kept only the first, and the dropped one was the content check
          -- so the flow asserted a row COUNT where the agent had checked that
          every row said "Edinburgh". Checks are now keyed by what they look
          at, so different selectors and different patterns coexist.
        """
        exp: dict = {}
        _q: dict = {}
        _s: dict = {}

        def _put(d, k, v):
            if keep_first:
                d.setdefault(k, v)
            else:
                d[k] = v

        for r in records:
            name, res = r["name"], r["result"] or ""
            if name == "get_url":
                # AN OBSERVATION THAT SAYS IT READ THE WRONG PAGE IS NOT A
                # POSTCONDITION. #61 made get_url name an in-flight navigation;
                # compiling that read into an assertion is how the arXiv flow
                # came to assert the url it was navigating AWAY from.
                if "IN FLIGHT" in res:
                    continue
                m = re.search(r'"url"\s*:\s*"([^"]+)"', res)
                if m:
                    _put(exp, "url", m.group(1))
            elif name == "search_page":
                hits = search_hits(res)
                inp = r["input"] or {}
                pat = inp.get("pattern")
                # THE FLAGS ARE PART OF THE ASSERTION, not of the call. A regex
                # recorded and replayed as a literal can never match: measured
                # in round two of #63, an agent asserted
                # `Showing 1[–-]50 of [\d,]+ results` with regex=True, got one
                # match, and the replay searched that string literally and
                # failed the flow. The agent reached for a regex deliberately,
                # because the header carries a COUNT that drifts -- so dropping
                # the flag silently downgrades the robust assertion to the
                # brittle one. `css_scope` was dropped the same way and made a
                # scoped check pass for the wrong reason, over the whole page.
                _flags = {k: inp[k] for k in ("regex", "css_scope", "case_sensitive")
                          if inp.get(k)}
                if hits == 0 and pat:
                    # ABSENCE, asserted as absence. The agent looked and it was
                    # not there, which is half of what a UI test checks.
                    _put(_s, pat, {"pattern": pat, "absent": True, **_flags})
                elif hits and pat:
                    # PRESENCE, not the exact tally. A page-wide text search is
                    # genuinely volatile -- a toast saying "Created X"
                    # legitimately turns 1 hit into 2 -- and the question this
                    # check is really asking is "is it there". The observed
                    # count is kept for the reader, not asserted on.
                    _put(_s, pat, {"pattern": pat, "min": 1, "observed": hits, **_flags})
            elif name == "query_elements":
                tot = query_total(res)
                sel = r["input"].get("selector")
                if tot is not None and sel:
                    # EXACT, because that is what was observed. "At least N" is
                    # a weaker claim than the run made and cannot see anything
                    # being ADDED: measured live, a row injected above the
                    # table left the flow green at min=4 against 5 rendered.
                    chk = {"selector": sel, "count": tot}
                    # THE TEXT THAT WAS READ, when the query named ONE element.
                    # Without it a content check compiles to an existence check:
                    # `#combo1 == 1` is true whatever the combobox displays.
                    # Only for a single match -- across several the text belongs
                    # to no particular one -- and never when the step's own
                    # input was what produced it, which `_paramize` turns into a
                    # variable so an override follows.
                    if tot == 1:
                        txt = query_first_text(res)
                        if txt:
                            chk["text"] = txt
                        # AND THE ATTRIBUTES, which is where a typed value
                        # lives. An <input> has no text, so `text` alone left
                        # every typing step asserting existence -- the one
                        # action a UI test performs most often (#63 round two).
                        att = query_first_attrs(res)
                        if att:
                            chk["attrs"] = att
                    _put(_q, sel, chk)
        if _s:
            exp["search"] = list(_s.values()) if len(_s) > 1 else next(iter(_s.values()))
        if _q:
            exp["query"] = list(_q.values()) if len(_q) > 1 else next(iter(_q.values()))
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

        ONLY WHERE THE APP DEMONSTRATED IT WAS SLOW, which is the correction
        #63/D14 forced. The first version took the gap from the action to the
        last contributing observation -- which on a REAL recording is mostly
        the agent's own model turns (~3.6s each, #38), not the page. Measured:
        18,548ms recorded for a navigate and 16,465ms for a modal that opens in
        well under a second, so every replay then allowed ~18s of slack on
        steps needing none. The Boxsy figures #60 reported are inflated the
        same way.

        The fixture that motivated #60 had the right shape all along: an agent
        that checks, gets one answer, waits, and checks again and gets a
        DIFFERENT one. That change is the app saying "I was not ready yet". A
        single look says only that the agent got round to looking.

        So the bound is the gap from the action to the last moment any check
        CHANGED its answer, and with nothing changing it is zero. Note this had
        to be the answer CHANGING rather than a look that found nothing: since
        #63/D13 a zero IS an answer, so "found nothing" is a legitimate
        assertion rather than a failed attempt.
        """
        base = live[i].get("ts") or 0
        if not base:
            return 0
        first: dict = {}           # check key -> the FIRST answer seen for it
        best = 0.0
        for r in live[i + 1:]:
            if r["mutates"]:
                break
            for key, val in cls._check_items(cls._checks([r])).items():
                if key in first:
                    if first[key] != val:
                        best = max(best, r.get("ts") or 0)
                else:
                    first[key] = val
        return int(max(0.0, best - base) * 1000) if best else 0

    @staticmethod
    def _is_empty(key, val) -> bool:
        """Does this check say the thing was NOT there?"""
        if key[0] == "search":
            return val[0] is True                       # absent=True
        if key[0] == "query":
            return isinstance(val[0], int) and val[0] == 0 and val[0] is not True
        return False

    @staticmethod
    def _drop_check(exp: dict, key) -> None:
        kind, which = key[0], key[1]
        if kind == "url":
            exp.pop("url", None)
            return
        cur = exp.get(kind)
        if cur is None:
            return
        field = "pattern" if kind == "search" else "selector"
        items = [c for c in (cur if isinstance(cur, list) else [cur])
                 if c.get(field) != which]
        if not items:
            exp.pop(kind, None)
        else:
            exp[kind] = items if len(items) > 1 else items[0]

    @staticmethod
    def _check_items(exp: dict) -> dict:
        """Each check as key -> answer, so two looks at one thing are comparable."""
        out: dict = {}
        if "url" in exp:
            out[("url",)] = exp["url"]
        sv = exp.get("search")
        for s in (sv if isinstance(sv, list) else [sv] if sv else []):
            out[("search", s.get("pattern"))] = (s.get("absent"), s.get("observed"))
        qv = exp.get("query")
        for q in (qv if isinstance(qv, list) else [qv] if qv else []):
            out[("query", q.get("selector"))] = (q.get("count"), q.get("text"))
        return out

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
        return cls._checks([r for r in reversed(live[:i]) if not r["mutates"]],
                           keep_first=True)

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
