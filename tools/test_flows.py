"""Unit suite for the flow descriptor — naming a control so a recorded step survives.

Why this exists: a recorded step cannot store a ref. mmids are per-document and
additive (limitation #1, fix #5), so on the next run the number does not mean
"not found", it means SOME OTHER ELEMENT — a step that stores one is a step that
clicks the wrong thing and reports success, which is the #10/#11/#12 family.

Every check here has a negative control beside it, because the failure mode this
module can have is the quiet one: a descriptor that resolves to a plausible
wrong element looks exactly like a descriptor that works.

FD8 and FD12 are the two that matter. FD12 is the whole claim — survive a
re-render that renumbers every mmid. FD8 is the whole safety property — when
the crowd around the target changed, REFUSE rather than take the ordinal.

Run:  python tools/test_flows.py
"""

import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core.flows.descriptor import (  # noqa: E402
    ALT, FULL, LEVELS, Unresolved, build, fields, resolve,
)
from core.flows import model as FM  # noqa: E402
from core.flows import secrets as FS  # noqa: E402
from core.flows.recorder import Recorder, query_total, search_hits  # noqa: E402
from core.flows.runner import FAILED, NEEDS, PASSED, Run, resume, start  # noqa: E402

# TEST-ONLY TIMING. `SETTLE_MS` is the window a target or a postcondition gets
# to BECOME true (#55, #59); the fixtures deliberately present controls that
# will never appear, so at the shipped 6s each of those waits out the full
# bound. Lowered here, not in the product: the behaviour under test is the
# retry, not the duration.
Run.SETTLE_MS = 300
Run.POLL_MS = 50

sys.path.insert(0, str(ROOT / "tools"))
from _extract import extract  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))


def E(mmid, tag="button", role="", name="", type_="", placeholder="",
      section="", under="", value="", disabled=False, clickable=True,
      editable=False, text="", href=""):
    """One collector entry, in the shape _collectInteractivePage(structured) emits."""
    return {
        "mmid": mmid, "tag": tag, "role": role, "name": name, "label": "",
        "type": type_, "placeholder": placeholder, "section": section,
        "underHeading": under, "value": value, "text": text,
        "disabled": disabled, "clickable": clickable, "editable": editable,
        "href": href,
    }


def main():
    # ---------------------------------------------------------------- build
    page = [
        E(1, "button", name="Save"),
        E(2, "button", name="Cancel"),
        E(3, "input", type_="email", placeholder="you@example.com",
          section="form", editable=True, clickable=False),
    ]
    t = build(page[0], page)
    check("FD1 a uniquely-named control gets the CHEAPEST descriptor that resolves",
          t["level"] == 1 and t["desc"].get("name") == "Save", f"level={t['level']}")
    check("FD1b ...and therefore does NOT carry section/heading, which a rename "
          "elsewhere on the page would otherwise break",
          "under" not in t["desc"] and "section" not in t["desc"],
          f"desc keys={sorted(t['desc'])}")

    # Two controls sharing a name, separated by the landmark they sit in.
    dup = [
        E(10, "button", name="Delete", section="main", under="Drafts"),
        E(11, "button", name="Delete", section="main", under="Published"),
    ]
    t2 = build(dup[0], dup)
    check("FD2 a shared name escalates to section/heading rather than giving up",
          t2["desc"].get("under") == "Drafts" and "nth" not in t2,
          f"level={t2['level']} nth={t2.get('nth')}")
    check("FD2b ...and stops THERE rather than climbing to near=, which costs a "
          "field for nothing once the heading already resolved it",
          "near" not in t2["desc"], f"desc keys={sorted(t2['desc'])}")

    # Identical in every declared field: only an ordinal can separate them.
    rows = [E(20 + i, "button", name="Edit", section="main", under="Rows")
            for i in range(4)]
    t3 = build(rows[2], rows)
    check("FD3 controls identical in every DECLARED field fall back to an ordinal",
          t3.get("nth") == 2 and t3.get("of") == 4,
          f"nth={t3.get('nth')} of={t3.get('of')}")

    # -------------------------------------------------------------- resolve
    check("FD4 a level-1 descriptor resolves to the one element it names",
          resolve(t, page) == "1")
    check("FD5 zero matches refuses, and NAMES the descriptor it looked for "
          "(#24: refuse and name the candidates, never guess)",
          _raises(lambda: resolve(t, [page[1], page[2]]), "Save"))

    t_noord = {"level": FULL, "desc": dict(t3["desc"])}
    check("FD6 several matches with no recorded ordinal refuses AND hands back "
          "the candidates, so the refusal is actionable (#39)",
          _raises(lambda: resolve(t_noord, rows), "4 elements match",
                  want_candidates=4))

    check("FD7 the ordinal resolves when the crowd is unchanged",
          resolve(t3, rows) == "22")

    # ---- FD8: THE safety property -----------------------------------------
    # A row inserted ABOVE the target shifts every ordinal. Taking nth here
    # would act on a different element and report success.
    grown = [E(19, "button", name="Edit", section="main", under="Rows")] + rows
    ok8 = _raises(lambda: resolve(t3, grown), "but 4 did when")
    check("FD8 a CHANGED crowd refuses instead of taking the ordinal — a row "
          "added above the target must not silently redirect the click", ok8)
    check("FD8b ...and the control: an UNCHANGED crowd still resolves, so the "
          "guard is not simply refusing everything",
          resolve(t3, list(rows)) == "22")

    # FD8c is the case 17 green checks missed and tools/audit_flow_resolve.py
    # found: the crowd SHRINKS TO EXACTLY ONE. A `len(hits) == 1` fast path
    # ahead of the crowd-check returns the survivor without ever reading the
    # recorded ordinal, so "the 1st of 2" binds to the OTHER one. Measured at
    # 7.9% silent mis-binds across the corpus before the order was fixed.
    pair = [E(30, "button", name="Search", section="nav"),
            E(31, "button", name="Search", section="nav")]
    t_pair = build(pair[0], pair)
    check("FD8c a crowd that SHRANK TO ONE refuses — the survivor is not known "
          "to be the element the step recorded",
          t_pair.get("of") == 2
          and _raises(lambda: resolve(t_pair, [pair[1]]), "1 element(s) match"))
    check("FD8d ...and the control: a step that recorded NO ordinal, because it "
          "was unique, still resolves against a single match",
          resolve(build(page[0], page), [page[0]]) == "1")

    # ---- FD9/FD10: what identity must NOT depend on ------------------------
    typed = [dict(e) for e in page]
    typed[2]["value"] = "ada@example.com"
    t_in = build(page[2], page)
    check("FD9 value is not identity: a field still resolves after the flow has "
          "typed into it (#6 — value is CURRENT CONTENTS)",
          resolve(t_in, typed) == "3")

    off = [dict(e) for e in page]
    off[0]["disabled"] = True
    check("FD10 state is not identity: a control a step is about to assert on "
          "still resolves once that state changes",
          resolve(t, off) == "1")

    # ---- FD11: the pool is the collector's own answer ----------------------
    noise = page + [E(99, "div", name="Save", clickable=False, editable=False)]
    check("FD11 a non-targetable entry sharing the name creates no phantom tie "
          "(#18 — asking 'is this a control' a second way was 60% of the gap)",
          resolve(t, noise) == "1")

    # ---- FD12: THE claim ---------------------------------------------------
    # Re-render: same page, every mmid renumbered. A stored ref is now wrong; a
    # stored XPath may be wrong; a declaration is not.
    rerendered = [dict(e, mmid=e["mmid"] + 500) for e in page]
    check("FD12 a descriptor survives a re-render that renumbers every mmid — "
          "the property a stored ref and a stored DOM path do not have",
          resolve(t, rerendered) == "501")
    check("FD12b ...including when the ordinal is doing the work",
          resolve(t3, [dict(e, mmid=e["mmid"] + 500) for e in rows]) == "522")

    # ---- FD14: the cheap/full tie-break ------------------------------------
    # build() stores the CHEAPEST descriptor that resolved, so a heading rename
    # cannot break a step whose name was already unique. The cost is that a
    # same-named control appearing elsewhere later makes it ambiguous --
    # measured at 54% of targets by audit_flow_resolve's twin-elsewhere
    # mutation. Carrying the full descriptor as a tie-break bought all of that
    # back (54% refused -> 0%) with no new mis-binds.
    solo = [E(40, "button", name="Export", section="main", under="Reports")]
    t_solo = build(solo[0], solo)
    check("FD14 a uniquely-named control records the cheap descriptor AND the "
          "full one, so a later collision can be narrowed instead of escalated",
          "under" not in t_solo["desc"] and t_solo["full"]["under"] == "Reports")
    later = solo + [E(41, "button", name="Export", section="footer", under="Legal")]
    check("FD14b ...and when that collision happens the step still resolves, to "
          "the element it was recorded for",
          resolve(t_solo, later) == "40")
    both = solo + [E(42, "button", name="Export", section="main", under="Reports")]
    check("FD14c ...but the control: when the FULL descriptor is ambiguous too, "
          "it still refuses rather than taking the first",
          _raises(lambda: resolve(t_solo, both), "match"))

    # ---- FD13: fields() normalisation --------------------------------------
    check("FD13 label fills the identity slot when name is empty, and tag is "
          "lowercased, so a descriptor built from either side matches",
          fields({"tag": "BUTTON", "label": "Submit"})["name"] == "Submit"
          and fields({"tag": "BUTTON"})["tag"] == "button")

    # ------------------------------------------------------------------ FA
    # The href ALT key (#61). Measured first, and the measurement REFUTED the
    # obvious design: href is a WORSE primary key than the accessible name
    # (62.1% unique against 79.2% across 28 frozen sites, lower on 22 of 28),
    # so it is a fallback and never a rung. These pin that it rescues #59's
    # case, plus the five controls that keep it from being a licence to guess.
    nav = [
        E(10, "a", name="Investors 38", href="/pipeline/investors",
          section="nav", under="Fundraising Pipeline"),
        E(11, "a", name="Contacts 9", href="/pipeline/contacts",
          section="nav", under="Fundraising Pipeline"),
        E(12, "button", name="Add investor"),
    ]
    t = build(nav[0], nav)
    check("FA1 a link records its declared destination as an ALTERNATE key, "
          "beside the name descriptor rather than instead of it",
          t["desc"]["name"] == "Investors 38"
          and t.get("alt") == {"tag": "a", "role": "", "type": "",
                               "href": "/pipeline/investors"})

    # #59's live failure, exactly: AccName 2F concatenates a badge that is a
    # descendant, so adding a record rewrites the identity.
    later = [dict(nav[0], name="Investors 43"), nav[1], nav[2]]
    notes = []
    check("FA2 a name carrying live data can change and the step still resolves "
          "— #59's 'Investors 38' -> 'Investors 43', which a rebind could only "
          "ever re-break at 44",
          resolve(t, later, notes) == "10")
    check("FA2b ...and the run is TOLD it matched on the destination, because a "
          "step that resolved on a different key than it recorded is not a "
          "clean pass",
          len(notes) == 1 and notes[0]["via"] == "href"
          and notes[0]["was"]["name"] == "Investors 38")

    clean = []
    check("FA3 CONTROL: a step whose recorded descriptor still matches reports "
          "NOTHING — a note that fired on every run would be the noise #15 "
          "priced",
          resolve(t, nav, clean) == "10" and clean == [])

    gone = [nav[1], nav[2]]
    check("FA4 CONTROL: the link is GONE, so the destination names nothing and "
          "the step still refuses — the fallback is a second key, not a licence "
          "to pick something",
          _raises(lambda: resolve(t, gone, []), "no element on the page matches"))

    twinned = [dict(nav[0], name="Investors 43"),
               E(13, "a", name="Investors", href="/pipeline/investors"),
               nav[1], nav[2]]
    check("FA5 CONTROL: two links to the same destination is ambiguous, so it "
          "refuses rather than taking the first",
          _raises(lambda: resolve(t, twinned, []), "no element on the page matches"))

    shared = [E(20, "a", name="Open", href="/x"), E(21, "a", name="Open", href="/x")]
    check("FA6 CONTROL: an href shared by two links is recorded as no alternate "
          "at all — storing it would only produce a second ambiguous refusal "
          "after the first",
          build(shared[0], shared).get("alt") is None)

    div = [E(30, "div", name="Pretend link", href="/elsewhere"),
           E(31, "button", name="Other")]
    check("FA7 CONTROL: href is read as a DESTINATION only on <a>/<area>, where "
          "HTML says that is what it means — on a div the attribute declares "
          "nothing (#27/#28's rule against class-substring guesses)",
          build(div[0], div).get("alt") is None)

    nohref = [E(40, "a", name="Plain"), E(41, "button", name="Other")]
    check("FA8 CONTROL: a link with no href carries no alternate, so nothing "
          "matches on the empty string",
          build(nohref[0], nohref).get("alt") is None)

    # The extension is installed BY HAND, so a version skew between it and the
    # server is the normal condition rather than an edge case (that is why the
    # handshake carries PROTOCOL_VERSION at all). `href` only exists at
    # detail="brief", so a flow recorded with an alternate can be replayed by a
    # stack that does not supply one -- and the only acceptable answer there is
    # the behaviour that shipped before the alternate existed.
    stripped = [{k: v for k, v in e.items() if k != "href"} for e in later]
    check("FA9 DEGRADATION: entries carrying no href at all fall back to the "
          "recorded descriptor and refuse exactly as they did before the "
          "alternate existed — never to a match on the empty string",
          _raises(lambda: resolve(t, stripped, []), "no element on the page matches"))
    check("FA9b ...and the same stripped entries still resolve a step whose "
          "recorded NAME matches, so the degradation costs nothing else",
          resolve(t, [{k: v for k, v in e.items() if k != "href"} for e in nav],
                  []) == "10")

    # ---- FD15: the field-name contract -------------------------------------
    # Every check above runs on dicts THIS FILE wrote. If the collector spells
    # a field differently from fields(), all of them stay green and nothing
    # resolves on a real page -- #16's "test stubs that share your assumptions
    # test nothing", and #30 found exactly this twice behind green suites.
    # So: read the real collector and require every key the descriptor depends
    # on to be a key it actually emits. Same job as C11/C12.
    src = extract("_collectInteractivePage",
                  (ROOT / "extension" / "background.js").read_text(encoding="utf-8"),
                  verify=True)
    needed = sorted({k for lv in LEVELS for k in lv} | set(ALT) |
                    {"label", "placeholder", "underHeading", "near", "text",
                     "mmid", "clickable", "editable"})
    # Read the keys off the ENTRY LITERALS themselves -- the out.push({...})
    # objects that carry an mmid -- rather than grepping the function body. A
    # loose grep passes on a mention in a comment, which is how a tripwire
    # quietly stops tripping (#39: a drift check that could not fire).
    emitted = set()
    for m in re.finditer(r"out\.push\(\{", src):
        seg = src[m.start(): m.start() + 1200]
        if "mmid:" in seg:
            emitted |= set(re.findall(r"[{,]\s*([A-Za-z_]\w*)\s*:", seg))
    # `under` is the descriptor's name for the collector's `underHeading`.
    missing = [k for k in needed if k != "under" and k not in emitted]
    check("FD15 every field the descriptor reads is a field the real collector "
          "emits — the fixtures above all use dicts this file wrote",
          not missing, f"missing from _collectInteractivePage: {missing}")

    asyncio.run(record_and_replay())

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} flow checks passed.")
    return 0 if passed == len(results) else 1


# =========================================================================
# FR series — the recorder and the runner, end to end against a fake bridge.
#
# The fake returns the REAL result-string shapes (FD17 pins them against
# mcp_server), because #19's lesson is that a stub sharing your assumptions
# tests nothing: the delta unit test passed for its whole life while the live
# path was broken, because the fake returned get_url as a dict and the real
# bridge returns a JSON string.
# =========================================================================
PAGE_A = [E(1, "button", name="Save"), E(2, "input", type_="email",
            placeholder="you@example.com", editable=True, clickable=False),
          E(3, "button", name="Delete", section="main", under="Drafts")]


class FakeBridge:
    """Stands in for the extension. Records what it was asked to do."""

    def __init__(self, entries=None):
        self.entries = list(entries if entries is not None else PAGE_A)
        self.calls = []
        self.url = "https://app.test/start"
        self.search_hits = 2
        self.query_total = 7

    async def entries_fn(self, tabId=None):
        return list(self.entries)

    async def call(self, tool, inp):
        self.calls.append((tool, dict(inp)))
        if tool == "get_url":
            return '{"url": "%s", "title": "t"}' % self.url
        if tool == "search_page":
            if not self.search_hits:
                return 'No match for "%s". 91 text block(s) were searched.' % inp.get("pattern")
            return '%d match(es) for "%s"\n  <p ref_9> ...' % (self.search_hits, inp.get("pattern"))
        if tool == "query_elements":
            return "%d element(s) match %r" % (self.query_total, inp.get("selector"))
        return "ok"


async def record_and_replay():
    # ---- recording -------------------------------------------------------
    fb = FakeBridge()
    rec = Recorder("signup", fb.entries_fn, origin="https://app.test")

    inp = {"ref": "ref_1", "tabId": 5}
    tgts = await rec.before("form_input", inp)
    check("FR1 the recorder describes a ref BEFORE the call runs, because the "
          "action is often what destroys the document the ref belonged to",
          "ref" in tgts and tgts["ref"]["desc"].get("name") == "Save",
          f"targets={tgts}")

    rec.after("form_input", inp, "Typed", tgts)
    rec.after("get_url", {"tabId": 5}, '{"url": "https://app.test/done"}', {})
    rec.after("search_page", {"tabId": 5, "pattern": "Welcome"},
              '2 match(es) for "Welcome"', {})
    rec.after("query_elements", {"tabId": 5, "selector": "tr"},
              "7 element(s) match \'tr\'", {})
    rec.after("computer", {"tabId": 5, "action": "left_click", "ref": "ref_99"},
              "", {}, error="Element not found")

    flow, report = rec.compile()
    check("FR2 a call that ERRORED is dropped — replaying it would replay the "
          "agent's dead end", report["dropped_errors"] == 1, str(report))
    check("FR3 observations are folded into the PREVIOUS action's assertions "
          "rather than replayed as steps",
          len(flow.steps) == 1 and report["dropped_observations"] == 3, str(report))
    exp = flow.steps[0].expect
    check("FR3b ...and all three kinds survive: url, search hit count, element count",
          exp.get("url") == "https://app.test/done"
          and exp["search"] == {"pattern": "Welcome", "min": 1, "observed": 2}
          and exp["query"] == {"selector": "tr", "count": 7}, str(exp))
    check("FR3d a COUNT is recorded exactly, not as a floor — 'at least N' is a "
          "weaker claim than the run made and cannot see a row being ADDED "
          "(measured live: an injected row left the flow green at min=4)",
          exp["query"].get("count") == 7 and "min" not in exp["query"])
    check("FR3e ...while a page-wide TEXT search records presence, because a "
          "toast legitimately turns one hit into two",
          exp["search"]["min"] == 1 and exp["search"]["observed"] == 2)
    check("FR3c the recorded ref is GONE from the step input — a per-document "
          "handle in a saved file is a wrong click waiting to happen",
          "ref" not in flow.steps[0].input and "tabId" not in flow.steps[0].input,
          str(flow.steps[0].input))

    # A ref the listing does not carry cannot be described, so the step goes.
    rec2 = Recorder("bad", fb.entries_fn)
    t2 = await rec2.before("form_input", {"ref": "ref_404", "tabId": 5})
    rec2.after("form_input", {"ref": "ref_404", "tabId": 5}, "ok", t2)
    f2, r2 = rec2.compile()
    check("FR4 a ref that is not in the listing is NOT silently recorded; the "
          "step is dropped and the reason is reported",
          not f2.steps and any("not in the current listing" in n for n in r2["notes"]),
          str(r2["notes"]))

    # ---- replay ----------------------------------------------------------
    fb2 = FakeBridge()
    fb2.url = "https://app.test/done"
    res = await start(flow, 5, fb2.call, fb2.entries_fn)
    check("FR5 replay resolves the descriptor and calls the tool with a FRESH "
          "ref for the current document",
          res["status"] == PASSED and ("form_input", {"ref": "ref_1", "tabId": 5})
          in [(t, i) for t, i in fb2.calls], str(fb2.calls[:2]))
    check("FR5b ...and the assertions were actually run, not just stored",
          any(t == "search_page" for t, _ in fb2.calls)
          and any(t == "query_elements" for t, _ in fb2.calls))

    # ---- THE FALSIFIER ---------------------------------------------------
    fb3 = FakeBridge(); fb3.url = "https://app.test/done"; fb3.search_hits = 0
    res3 = await start(flow, 5, fb3.call, fb3.entries_fn)
    check("FR6 a flow FAILS when a postcondition stops holding — a suite that "
          "cannot fail is worth less than no suite",
          res3["status"] == FAILED and "search_page" in res3["reason"], str(res3["reason"]))
    fb4 = FakeBridge(); fb4.url = "https://app.test/elsewhere"
    res4 = await start(flow, 5, fb4.call, fb4.entries_fn)
    check("FR6b ...and it notices a wrong URL too, naming both values",
          res4["status"] == FAILED and "elsewhere" in res4["reason"], str(res4["reason"]))

    # ---- escalation ------------------------------------------------------
    gone = FakeBridge([E(7, "button", name="Store"), E(8, "button", name="Store")])
    gone.url = "https://app.test/done"
    res5 = await start(flow, 5, gone.call, gone.entries_fn)
    check("FR7 a step that cannot be pinned to one element PAUSES and hands "
          "back the candidates, instead of guessing",
          res5["status"] == NEEDS and res5["run_id"].startswith("run_"),
          str(res5["reason"]))
    check("FR7b ...and nothing was dispatched for that step",
          not any(t == "form_input" for t, _ in gone.calls))

    res6 = await resume(res5["run_id"], "ref_7")
    check("FR8 resuming with a binding continues the run from the paused step",
          res6["status"] == PASSED and res6["at"] == 1, str(res6["status"]))
    check("FR8b ...the step is MARKED as rebound, so a green run that needed "
          "help does not read like a clean one",
          any(l.get("healed") for l in res6["log"]), str(res6["log"]))
    check("FR8c ...and the fix is PROPOSED as a patch, never written into the "
          "flow file", res6["patches"] and res6["patches"][0]["now"] != res6["patches"][0]["was"]
          and flow.steps[0].targets["ref"]["desc"].get("name") == "Save",
          str(res6["patches"]))

    # A rebind must not rescue a broken assertion.
    bad = FakeBridge([E(7, "button", name="Store"), E(8, "button", name="Store")])
    bad.url = "https://app.test/WRONG"
    r7 = await start(flow, 5, bad.call, bad.entries_fn)
    r8 = await resume(r7["run_id"], "ref_7")
    check("FR8d the reported time is EXECUTION time, not wall time — a paused "
          "run waits for a human, and billing that to the flow corrupts the one "
          "number anyone will quote",
          res6["seconds"] < 1.0, f'{res6["seconds"]}s for a fake-bridge run')

    check("FR9 a rebound step still has to satisfy the ORIGINAL postcondition — "
          "healing the LOCATOR must never relax the CHECK",
          r8["status"] == FAILED and "WRONG" in r8["reason"], str(r8["reason"]))

    # ---- FR11: name the cause, do not just report the symptom ------------
    # Found on the FIRST live replay: form_input on a Radix combobox left its
    # listbox open, an open popup aria-hides the rest of the document, and the
    # next run failed at step 0 on an unrelated textarea saying only "no
    # element matches tag='textarea'" — true, useless, and the reason was in
    # the runner's own listing.
    popped = FakeBridge([E(7, "div", role="listbox", name="Models"),
                         E(8, "button", name="Elsewhere")])
    popped.url = "https://app.test/done"
    r9 = await start(flow, 5, popped.call, popped.entries_fn)
    check("FR11 when a descriptor cannot resolve AND an open listbox/menu/dialog "
          "is listed, the runner names it and the recovery",
          r9["status"] == NEEDS and "open listbox" in r9["reason"]
          and "aria-hidden" in r9["reason"], str(r9["reason"]))
    plain = FakeBridge([E(9, "button", name="Elsewhere")])
    plain.url = "https://app.test/done"
    r10 = await start(flow, 5, plain.call, plain.entries_fn)
    check("FR11b ...and the control: with no popup listed it asserts no cause, "
          "because a note that always fires is noise (#15) and a note that "
          "guesses is C15's defect",
          r10["status"] == NEEDS and "aria-hidden" not in r10["reason"],
          str(r10["reason"]))

    # ---- FR12: THE SECOND RUN OF A MUTATING FLOW ------------------------
    #
    # A flow that CREATES something changes the count it recorded, so replaying
    # it in place leaves the app one row further on every time. Measured on the
    # shipped CI flow: run 1 passes, run 2 fails with "counted 5, recorded
    # exactly 4". That is not a defect -- it is what a mutating test needs a
    # fixture reset for (`run_flows.py --playground` does one, which is why CI
    # never sees it) -- but the bare numbers do not say so, and an agent
    # re-running its own flow meets a failure with no cause attached.
    class _V(Run):
        def __init__(self, result):
            self.call = lambda t, i: _async(result)
            self.tab_id, self.cur_tab, self.vars = 1, 1, {}

    async def _async(v):
        return v

    grew = await _V("5 element(s) match 'tr':")._verify(
        {"query": {"selector": "tr", "count": 4}})
    check("FR12 a count that GREW names the previous-run cause among others, "
          "rather than leaving the agent two bare numbers",
          "GREW" in grew and "previous run" in grew and "reset fixture" in grew,
          grew[:120])
    # Listed as ONE cause of three, never as the diagnosis: the count also grows
    # when the seed changed or the page genuinely regressed. #33's rule, and the
    # defect C15 exists to catch.
    check("FR12b ...as one cause of several, not as the diagnosis",
          "Causes that need different answers" in grew
          and "changed underneath" in grew, grew[:160])
    # CONTROL. A count that SHRANK is a different failure with a different
    # answer, and a clause that fires on every mismatch is the noise #15 priced.
    shrank = await _V("2 element(s) match 'tr':")._verify(
        {"query": {"selector": "tr", "count": 4}})
    check("FR12c CONTROL: a count that SHRANK gets no grew-clause at all",
          "counted 2" in shrank and "GREW" not in shrank, shrank[:120])

    # ---- fill_form carries several refs ----------------------------------
    fb5 = FakeBridge()
    multi = {"fields": [{"ref": "ref_1", "value": "a"}, {"ref": "ref_3", "value": "b"}],
             "tabId": 5}
    mt = await rec.before("fill_form", multi)
    check("FR10 fill_form's fields are described one per entry, by input path",
          sorted(mt) == ["fields.0", "fields.1"]
          and mt["fields.1"]["desc"].get("name") == "Delete", str(sorted(mt)))

    # ---- FS: a recorded flow must never carry a password -----------------
    # Flow files are tests, so they live in git. Recording a login wrote the
    # password in plaintext into a file whose whole purpose is to be committed
    # -- undoing #31/W24, which removed exactly this leak from read_page.
    import os as _os
    fb6 = FakeBridge([E(50, "input", type_="email", name="Work email", editable=True,
                        clickable=False),
                      E(51, "input", type_="password", name="Password", editable=True,
                        clickable=False),
                      E(52, "button", name="Sign in", type_="submit")])
    rec3 = Recorder("acme-login", fb6.entries_fn)
    li = {"fields": [{"ref": "ref_50", "value": "ada@acme.test"},
                     {"ref": "ref_51", "value": "hunter2-real-password"}],
          "submit": True, "submit_ref": "ref_52", "tabId": 1}
    lt = await rec3.before("fill_form", li)
    rec3.after("fill_form", li, "Filled 2/2", lt)
    lf, lr = rec3.compile()
    blob = json.dumps(lf.to_json())
    check("FS1 the typed password is NOWHERE in the flow file",
          "hunter2-real-password" not in blob, blob[:160])
    check("FS1b ...and the email beside it IS stored — the control that this "
          "redacts the declared password field, not every value",
          "ada@acme.test" in blob)
    check("FS1c the placeholder NAMES the environment variable, so the file "
          "says which secret it needs without containing it",
          "CB_SECRET_ACME_LOGIN_PASSWORD" in blob, blob[:200])
    check("FS1d the compile report lists the variable NAMES and no values",
          lr["secrets"] == ["CB_SECRET_ACME_LOGIN_PASSWORD"]
          and "hunter2" not in json.dumps(lr), str(lr.get("secrets")))

    # ---- replay ----------------------------------------------------------
    fb7 = FakeBridge(fb6.entries); fb7.url = "https://app.test/start"
    _os.environ.pop("CB_SECRET_ACME_LOGIN_PASSWORD", None)
    rr = await start(lf, 1, fb7.call, fb7.entries_fn)
    check("FS2 replay with the secret UNSET fails and names the variable, "
          "rather than typing an empty string",
          rr["status"] == FAILED
          and "CB_SECRET_ACME_LOGIN_PASSWORD" in rr["reason"], str(rr["reason"])[:140])
    check("FS2b ...and nothing was dispatched for that step — a blank password "
          "submits, then looks like a wrong credential instead of a missing one",
          not any(t == "fill_form" for t, _ in fb7.calls))

    _os.environ["CB_SECRET_ACME_LOGIN_PASSWORD"] = "hunter2-real-password"
    try:
        fb8 = FakeBridge(fb6.entries); fb8.url = "https://app.test/start"
        rr2 = await start(lf, 1, fb8.call, fb8.entries_fn)
        sent = next((i for t, i in fb8.calls if t == "fill_form"), {})
        vals = [f.get("value") for f in (sent.get("fields") or [])]
        check("FS3 with the variable exported, replay types the real secret",
              rr2["status"] == PASSED and "hunter2-real-password" in vals, str(vals))
        check("FS3b ...and the secret does not appear in the run REPORT, which "
              "goes into a transcript", "hunter2" not in json.dumps(rr2))
    finally:
        _os.environ.pop("CB_SECRET_ACME_LOGIN_PASSWORD", None)

    # ---- the focus rule: computer(type) names nothing --------------------
    for kind, expect_redacted in (("password", True), ("text", False)):
        fbx = FakeBridge([E(60, "input", type_=kind, name="Secret", editable=True,
                            clickable=True)])
        rx = Recorder("kb", fbx.entries_fn)
        ci = {"action": "left_click", "ref": "ref_60", "tabId": 1}
        ct = await rx.before("computer", ci)
        rx.after("computer", ci, "clicked", ct)
        ti = {"action": "type", "text": "typed-secret-xyz", "tabId": 1}
        rx.after("computer", ti, "typed", {})
        fx, _ = rx.compile()
        hidden = "typed-secret-xyz" not in json.dumps(fx.to_json())
        check(f"FS4{'' if expect_redacted else 'b'} computer(type) after a click "
              f"on a {kind} field is {'redacted' if expect_redacted else 'stored'} "
              f"— focus is established by the last step that named a ref (#43)",
              hidden == expect_redacted, f"hidden={hidden}")

    check("FS5 'is this secret' is DECLARED, never guessed: a text field whose "
          "name contains 'password' is not redacted, and a password field named "
          "in another script is",
          not FS.is_secret({"desc": {"type": "text", "name": "password hint"}})
          and FS.is_secret({"desc": {"type": "password", "name": "\u30d1\u30b9\u30ef\u30fc\u30c9"}}))
    check("FS5b ...and a non-Latin field name falls back to its POSITION rather "
          "than emitting an empty variable name (POSIX env names are ASCII)",
          FS.env_name("f", {"desc": {"type": "password",
                                     "name": "\u30d1\u30b9\u30ef\u30fc\u30c9"}},
                      "fields.1") == "CB_SECRET_F_FIELDS_1")

    # ---- FV: variables — a recorded value is a parameter ------------------
    fbv = FakeBridge([E(70, "input", type_="text", name="Project name",
                        editable=True, clickable=False),
                      E(71, "button", name="Create", type_="submit")])
    rv = Recorder("mk", fbv.entries_fn)
    vi = {"fields": [{"ref": "ref_70", "value": "echo-gateway"}],
          "submit": True, "submit_ref": "ref_71", "tabId": 1}
    vt = await rv.before("fill_form", vi)
    rv.after("fill_form", vi, "Filled 1/1", vt)
    vf, vr = rv.compile()
    check("FV1 a value typed into a form field becomes a NAMED variable with "
          "what was recorded as its default",
          vf.vars == {"project_name": "echo-gateway"}, str(vf.vars))
    check("FV1b ...and the step stores the placeholder, not the literal",
          "{{project_name}}" in json.dumps(vf.to_json())
          and "echo-gateway" not in json.dumps([s.to_json() for s in vf.steps]))

    fbv2 = FakeBridge(fbv.entries)
    r = await start(vf, 1, fbv2.call, fbv2.entries_fn)
    sent = next(i for t, i in fbv2.calls if t == "fill_form")
    check("FV2 replaying with no overrides types what was recorded",
          sent["fields"][0]["value"] == "echo-gateway", str(sent["fields"][0]))
    fbv3 = FakeBridge(fbv.entries)
    await start(vf, 1, fbv3.call, fbv3.entries_fn, overrides={"project_name": "beta-svc"})
    sent3 = next(i for t, i in fbv3.calls if t == "fill_form")
    check("FV3 an override replaces it — the same flow with a different input "
          "is an argument, not a re-record",
          sent3["fields"][0]["value"] == "beta-svc", str(sent3["fields"][0]))

    # The hostile case: a flow file hand-edited to reference a variable that
    # does not exist must FAIL loudly, not type the literal "{{typo}}" into a
    # field and report success.
    import copy as _copy
    broken = _copy.deepcopy(vf)
    broken.steps[0].input["fields"][0]["value"] = "{{typo_not_declared}}"
    fbv4 = FakeBridge(fbv.entries)
    rb = await start(broken, 1, fbv4.call, fbv4.entries_fn)
    check("FV4 an UNDECLARED variable fails and names it, instead of typing "
          "the placeholder text into the field",
          rb["status"] == FAILED and "typo_not_declared" in rb["reason"]
          and not any(t == "fill_form" for t, _ in fbv4.calls), str(rb["reason"])[:120])
    check("FV5 a secret is NOT turned into an ordinary variable — it stays "
          "env-backed, or the redaction would be undone by the next feature",
          "password" not in " ".join(lf.vars) and lf.vars.get("work_email"),
          str(lf.vars))

    # ---- FV6: AN ASSERTION MUST FOLLOW THE VARIABLE ITS INPUT USES.
    #
    # `_var` parameterised the typed VALUE and `_checks` recorded what was
    # OBSERVED, and nothing connected them -- so a flow recorded creating
    # "echo-gateway" asserted search_page("echo-gateway") forever. Measured
    # live before this existed: run_flow(vars={"project_name": "beta-svc"})
    # typed beta-svc and then failed with `search_page('echo-gateway') found 0,
    # recorded at least 1`, i.e. the headline use of the feature failing on its
    # own example. A flow that types one thing and checks for another is worse
    # than one with no assertion, because it reports red on a correct run.
    fbv5 = FakeBridge(fbv.entries)
    rv5 = Recorder("mk2", fbv5.entries_fn)
    vi5 = {"fields": [{"ref": "ref_70", "value": "echo-gateway"}],
           "submit": True, "submit_ref": "ref_71", "tabId": 1}
    vt5 = await rv5.before("fill_form", vi5)
    rv5.after("fill_form", vi5, "Filled 1/1", vt5)
    # The observation the agent makes next IS the postcondition (#49).
    si5 = {"pattern": "echo-gateway", "tabId": 1}
    rv5.after("search_page", si5, '1 match(es) for "echo-gateway":\n  <td> x', {})
    qi5 = {"selector": "tbody tr", "tabId": 1}
    rv5.after("query_elements", qi5, "5 element(s) match 'tbody tr':", {})
    vf5, _ = rv5.compile()
    exp5 = (vf5.steps[0].expect or {})
    check("FV6 an expectation whose value IS a variable is stored as the "
          "variable, not the literal",
          (exp5.get("search") or {}).get("pattern") == "{{project_name}}",
          json.dumps(exp5, ensure_ascii=False))
    # EXACT EQUALITY, NEVER SUBSTRING. Replacing every occurrence of a short
    # value inside a CSS selector or unrelated prose is a guess, and #27/#28's
    # rule is to prefer the one that cannot be wrong.
    check("FV6b CONTROL: a value that is not a variable is left alone — the "
          "selector keeps its literal",
          (exp5.get("query") or {}).get("selector") == "tbody tr",
          json.dumps(exp5, ensure_ascii=False))

    # AND THE RESOLUTION HALF. Storing the placeholder is useless if the runner
    # checks for the placeholder text; this is the end the live failure was at.
    fbv6 = FakeBridge(fbv.entries)
    # Match what FV6 recorded, so the postcondition holds on the first
    # evaluation. Since #55 a failing postcondition is RE-ASKED for a few
    # seconds before it is reported, so a fake that disagrees with the
    # recording turns a unit check into a six-second poll.
    fbv6.query_total = 5
    fbv6.search_hits = 1
    rr6 = await start(vf5, 1, fbv6.call, fbv6.entries_fn,
                      overrides={"project_name": "beta-svc"})
    asked = [i.get("pattern") for t, i in fbv6.calls if t == "search_page"]
    # THE INVARIANT IS *WHAT* IT ASKS FOR, not how many times. The first
    # version asserted exactly one call, which was only ever true because the
    # runner checked once; #55 gave a postcondition a bounded window to become
    # true, and the check failed on the retry count while the thing it exists
    # to pin was still correct. Same rewrite as #30's TR8d.
    check("FV6c an override changes what the ASSERTION looks for, not only "
          "what is typed",
          asked and set(asked) == {"beta-svc"},
          f"search_page called with {asked}")

    # ---- FR13: A TARGET THAT IS NOT THERE *YET* --------------------------
    #
    # #55 gave postconditions a window to BECOME true and left resolution asking
    # once -- the wrong half for a real app. Measured on a live SPA: step 1
    # failed on `name='Investors 38'` because mid-render that tab's accessible
    # name is still "Investors", the count having not arrived. The control was
    # not missing, it was not there yet, and one attempt reports those the same.
    class LateBridge(FakeBridge):
        """Renders the target only from the Nth entries fetch, like an SPA."""

        def __init__(self, entries, appear_on=3):
            super().__init__(entries)
            self.fetches, self.appear_on = 0, appear_on

        async def entries_fn(self, tabId=None):
            self.fetches += 1
            return list(self.entries) if self.fetches >= self.appear_on else []

    lb = LateBridge([E(70, "button", name="Create")])
    rl = Recorder("late", FakeBridge([E(70, "button", name="Create")]).entries_fn)
    li = {"ref": "ref_70", "tabId": 1}
    lt = await rl.before("computer", li)
    rl.after("computer", li, "clicked", lt)
    flate, _ = rl.compile()

    rres = await start(flate, 1, lb.call, lb.entries_fn)
    check("FR13 a target that renders a moment late still resolves, instead of "
          "being reported as missing",
          rres["status"] == PASSED and lb.fetches >= 3,
          f"status={rres['status']} after {lb.fetches} fetch(es); "
          f"reason={str(rres.get('reason'))[:70]}")

    # THE CONTROL. A control that never appears must still FAIL -- otherwise the
    # window would have turned every missing element into a slow success.
    never = LateBridge([E(70, "button", name="Create")], appear_on=10_000)
    rnev = await start(flate, 1, never.call, never.entries_fn)
    check("FR13b CONTROL: a target that never appears still fails, just later",
          rnev["status"] in (NEEDS, FAILED) and "no element" in str(rnev["reason"]),
          f"status={rnev['status']} reason={str(rnev['reason'])[:80]}")

    # ---- FR14: THE WINDOW BELONGS TO THE RECORDED DESCRIPTOR -------------
    #
    # Found on the first REAL-APP run of the href fallback, which is the only
    # place it could have been found. The step resolved on the destination in
    # 3.87s and reported the name had moved from 'Investors 43' to
    # 'Investors' -- and that is not a drift, it is the count badge not having
    # rendered yet. The proposed patch would have written the MID-RENDER name
    # into the flow. "Not there yet" and "the label changed" are exactly the
    # two things FR13's window exists to separate, and offering the alternate
    # on the first attempt collapsed them again one entry later.
    class BadgeBridge(FakeBridge):
        """The name arrives late; the href is there from the start, like an SPA."""

        def __init__(self, settles_on=3, final_name="Investors 43"):
            self.settles_on, self.final_name = settles_on, final_name
            super().__init__([])
            self.fetches = 0

        async def entries_fn(self, tabId=None):
            self.fetches += 1
            nm = self.final_name if self.fetches >= self.settles_on else "Investors"
            return [E(80, "a", name=nm, href="/pipeline/investors"),
                    E(81, "a", name="Contacts", href="/pipeline/contacts")]

    rb = Recorder("badge", BadgeBridge(settles_on=1).entries_fn)
    bi = {"ref": "ref_80", "tabId": 1}
    bt = await rb.before("computer", bi)
    rb.after("computer", bi, "clicked", bt)
    fbadge, _ = rb.compile()
    assert (list(fbadge.steps[0].targets.values())[0]).get("alt"), "fixture lost the alt"

    late = BadgeBridge(settles_on=3)
    rlate = await start(fbadge, 1, late.call, late.entries_fn)
    check("FR14 a name that has not RENDERED yet is waited for, not routed "
          "around — the recorded descriptor gets its whole window before the "
          "declared destination is offered",
          rlate["status"] == PASSED and not rlate.get("drifted")
          and late.fetches >= 3,
          f"status={rlate['status']} drifted={rlate.get('drifted')} "
          f"fetches={late.fetches}")

    # THE CONTROL, and without it "never use the alternate" would pass FR14
    # while deleting the feature. A name that never comes back IS a drift, and
    # there the destination must carry the step -- and say so.
    gone = BadgeBridge(settles_on=10_000, final_name="never")
    rgone = await start(fbadge, 1, gone.call, gone.entries_fn)
    check("FR14b CONTROL: a name that never comes back IS a drift, so the "
          "destination carries the step and the run reports it",
          rgone["status"] == PASSED and len(rgone.get("drifted") or []) == 1
          and (rgone["drifted"][0].get("alt") or {}).get("href") == "/pipeline/investors",
          f"status={rgone['status']} drifted={rgone.get('drifted')}")

    # ---- FS6: THE SETTLE WINDOW IS MEASURED, NOT CHOSEN ------------------
    #
    # The shipped window was a flat 6s. On a real app whose create ->
    # table-refresh cycle takes ~11s the flow reported FAILED for an action
    # that had SUCCEEDED -- the record was there, just not yet. A false
    # negative is the safe direction and still a wrong answer, and the number
    # that fixes it was already in the recording: every call is timestamped.
    import time as _t
    fb6 = FakeBridge([E(70, "button", name="Create")])
    r6 = Recorder("slow", fb6.entries_fn)
    ai6 = {"ref": "ref_70", "tabId": 1}
    at6 = await r6.before("computer", ai6)
    r6.after("computer", ai6, "clicked", at6)
    # The agent checked, got nothing, waited, checked again -- which is what a
    # slow backend looks like from the outside.
    r6.raw[-1]["ts"] = _t.time() - 9.0
    r6.after("query_elements", {"selector": "tr", "tabId": 1},
             "No element matches 'tr'", {})
    r6.raw[-1]["ts"] = _t.time() - 6.0
    r6.after("query_elements", {"selector": "tr", "tabId": 1},
             "5 element(s) match 'tr'", {})
    r6.raw[-1]["ts"] = _t.time() - 1.0
    f6, _ = r6.compile()
    check("FS6 the flow records how long the app ACTUALLY took for its checks "
          "to hold",
          7500 <= f6.steps[0].settle_ms <= 8500, f"settle_ms={f6.steps[0].settle_ms}")
    check("FS6b ...and it survives the file format",
          FM.Flow.from_json(f6.to_json()).steps[0].settle_ms == f6.steps[0].settle_ms,
          str(FM.Flow.from_json(f6.to_json()).steps[0].settle_ms))

    # CONTROL. An app that answered immediately records nothing, so its replay
    # keeps the plain default — the margin is earned, not handed out.
    fb7 = FakeBridge([E(70, "button", name="Create")])
    r7 = Recorder("fast", fb7.entries_fn)
    at7 = await r7.before("computer", ai6)
    r7.after("computer", ai6, "clicked", at7)
    r7.after("query_elements", {"selector": "tr", "tabId": 1},
             "5 element(s) match 'tr'", {})
    f7, _ = r7.compile()
    check("FS6c CONTROL: an app that answered at once records no extra margin",
          f7.steps[0].settle_ms < 500, f"settle_ms={f7.steps[0].settle_ms}")

    # ---- FT: A FLOW MAY SPAN TABS ---------------------------------------
    #
    # `tabs_create_mcp` is already an ACTION (it is in MUTATES), so the recorder
    # kept it -- and the runner then forced `tabId` on every step, so the tab it
    # made was created and ignored and the flow carried on in the old one. The
    # batch had exactly this defect until #46, with exactly this consequence.
    # It matters beyond tidiness: #56's one VERIFIED recovery from a tab that has
    # lost its trusted-input channel IS a new tab, and a flow could not do it.
    class TabBridge(FakeBridge):
        def __init__(self, entries=None):
            super().__init__(entries)
            self.made = 0

        async def call(self, tool, inp):
            if tool == "tabs_create_mcp":
                self.calls.append((tool, dict(inp)))
                self.made += 1
                return '{"tabId": %d}' % (900 + self.made)
            return await super().call(tool, inp)

    tf = TabBridge([E(70, "button", name="Create")])
    rt = Recorder("tabs", tf.entries_fn)
    ci = {"tabId": 1}
    ct = await rt.before("tabs_create_mcp", ci)
    rt.after("tabs_create_mcp", ci, '{"tabId": 901}', ct)
    ai = {"ref": "ref_70", "tabId": 1}
    at = await rt.before("computer", ai)
    rt.after("computer", ai, "clicked", at)
    ftf, _ = rt.compile()
    check("FT1 a recorded tabs_create_mcp survives the compile as a step",
          [st.name for st in ftf.steps] == ["tabs_create_mcp", "computer"],
          str([st.name for st in ftf.steps]))

    tf2 = TabBridge([E(70, "button", name="Create")])
    rr = await start(ftf, 5, tf2.call, tf2.entries_fn)
    after = [i.get("tabId") for t, i in tf2.calls if t == "computer"]
    check("FT2 steps after it run in the tab it MADE, not the one the flow started in",
          rr["status"] == PASSED and after == [901],
          f"status={rr['status']} computer ran in {after} (flow started in 5)")

    # THE CONTROL. A flow that creates nothing is untouched -- otherwise this
    # would have quietly changed where every existing flow runs.
    tf3 = TabBridge([E(70, "button", name="Create")])
    r2 = Recorder("plain", tf3.entries_fn)
    ai2 = {"ref": "ref_70", "tabId": 1}
    at2 = await r2.before("computer", ai2)
    r2.after("computer", ai2, "clicked", at2)
    fplain, _ = r2.compile()
    tf4 = TabBridge([E(70, "button", name="Create")])
    await start(fplain, 7, tf4.call, tf4.entries_fn)
    check("FT3 CONTROL: with no create step every call stays in the flow's tab",
          [i.get("tabId") for t, i in tf4.calls if t == "computer"] == [7],
          str([i.get("tabId") for t, i in tf4.calls if t == "computer"]))

    # A create whose id cannot be read must STOP. Carrying on would run every
    # later step in the previous tab without saying so, which is the silent
    # wrong-tab defect #46 fixed in the batch.
    class MuteTabBridge(TabBridge):
        async def call(self, tool, inp):
            if tool == "tabs_create_mcp":
                self.calls.append((tool, dict(inp)))
                return "created a tab"          # no id anywhere
            return await FakeBridge.call(self, tool, inp)

    tf5 = MuteTabBridge([E(70, "button", name="Create")])
    r3 = await start(ftf, 5, tf5.call, tf5.entries_fn)
    check("FT4 a create with no readable tab id FAILS instead of carrying on "
          "in the old tab",
          r3["status"] == FAILED and "no tab id" in r3["reason"]
          and not any(t == "computer" for t, _ in tf5.calls),
          f"status={r3['status']} reason={str(r3['reason'])[:90]}")

    # ---- FVP: the viewport, populated AND compared --------------------
    #
    # It was a declared field that nothing wrote and nothing read -- the shape
    # that kept `delta` dead for its whole life (#30) and left `origin` empty
    # until #54. Shipping one half is what makes that happen, so both halves
    # land together: the recorder stores the size, and the runner names a
    # difference as a CAUSE when a target cannot be resolved.
    vpf = FakeBridge([E(70, "button", name="Create")])
    rvp = Recorder("vp", vpf.entries_fn, viewport={"width": 1280, "height": 900})
    vpi = {"ref": "ref_70", "tabId": 1}
    vpt = await rvp.before("computer", vpi)
    rvp.after("computer", vpi, "clicked", vpt)
    fvp, _ = rvp.compile()
    check("FVP1 the recorded flow carries the viewport it was recorded at",
          fvp.viewport == {"width": 1280, "height": 900}, str(fvp.viewport))
    check("FVP1b ...and it survives a round trip through the file format",
          FM.Flow.from_json(fvp.to_json()).viewport == {"width": 1280, "height": 900},
          str(FM.Flow.from_json(fvp.to_json()).viewport))

    # A target that cannot be resolved AND a different window size: the size is
    # named as one cause among others, never as the diagnosis (#33).
    gone = FakeBridge([E(9, "button", name="Something else")])
    async def _vp_small(tab_id):
        return {"width": 400, "height": 800}
    r_vp = await start(fvp, 1, gone.call, gone.entries_fn, viewport_fn=_vp_small)
    check("FVP2 a failed resolve names the size difference as a cause",
          r_vp["status"] == NEEDS and "400px" in r_vp["reason"]
          and "1280px" in r_vp["reason"], str(r_vp["reason"])[:200])

    # THE CONTROL. Same failure, same size as the recording: saying nothing is
    # what keeps the note readable when it does fire (#15).
    async def _vp_same(tab_id):
        return {"width": 1280, "height": 900}
    gone2 = FakeBridge([E(9, "button", name="Something else")])
    r_vp2 = await start(fvp, 1, gone2.call, gone2.entries_fn, viewport_fn=_vp_same)
    # THE CORRECTION #59 MADE, pinned: a height-only difference is browser chrome
    # between two tabs of one window, not a responsive break. Measured live at
    # 1512x812 against 1512x868, where the note fired and meant nothing.
    async def _vp_short(tab_id):
        return {"width": 1280, "height": 500}
    gone_h = FakeBridge([E(9, "button", name="Something else")])
    r_vph = await start(fvp, 1, gone_h.call, gone_h.entries_fn, viewport_fn=_vp_short)
    # Keyed on the phrase BOTH versions share, not on the word the new one
    # happens to use: asserting "WIDTH" not in reason passed against the old
    # code for free, because the old sentence said "different size". A control
    # that cannot fail is the vacuous-fixture shape #29 names.
    check("FVP2b CONTROL: a HEIGHT-only difference says nothing — responsive "
          "layout is a function of width",
          r_vph["status"] == NEEDS
          and "than when this was recorded" not in r_vph["reason"],
          str(r_vph["reason"])[:160])

    check("FVP3 CONTROL: the same size as the recording is not mentioned",
          r_vp2["status"] == NEEDS and "different size" not in r_vp2["reason"],
          str(r_vp2["reason"])[:160])

    # And a flow recorded before this existed has no viewport, so there is
    # nothing to compare and nothing to say.
    fvp_old = FM.Flow.from_json({**fvp.to_json(), "viewport": None})
    gone3 = FakeBridge([E(9, "button", name="Something else")])
    r_vp3 = await start(fvp_old, 1, gone3.call, gone3.entries_fn, viewport_fn=_vp_small)
    check("FVP4 CONTROL: an older flow with no recorded viewport makes no claim",
          r_vp3["status"] == NEEDS and "different size" not in r_vp3["reason"],
          str(r_vp3["reason"])[:160])

    # ---- FW: AN ASSERTION THAT WAS ALREADY TRUE WITNESSES NOTHING ---------
    #
    # The most dangerous thing this feature can produce is a flow that cannot
    # fail, and it does not look wrong -- it passes, in CI, forever. Recorded
    # TWICE while building this: a playground flow asserting 4 table rows BEFORE
    # the create and 4 after (the form had silently refused, two required fields
    # unfilled), and a real-app flow asserting a product name that is on the page
    # whether or not anything was clicked. Both were caught by a human reading
    # the numbers; neither had to be.
    async def _hollow(after_result):
        fb = FakeBridge([E(70, "button", name="Create")])
        rr = Recorder("h", fb.entries_fn)
        qi = {"selector": "tr", "tabId": 1}
        rr.after("query_elements", qi, "4 element(s) match 'tr'", {})   # BEFORE
        ai = {"ref": "ref_70", "tabId": 1}
        at = await rr.before("computer", ai)
        rr.after("computer", ai, "clicked", at)
        rr.after("query_elements", qi, after_result, {})                # AFTER
        return rr.compile()

    _f, _rep = await _hollow("4 element(s) match 'tr'")
    check("FW1 an assertion that was already true before the step is reported as "
          "witnessing nothing",
          _rep.get("hollow") == [(0, "query")], f"hollow={_rep.get('hollow')}")

    # THE CONTROL THAT MAKES IT WORTH HAVING. A check that CHANGED because of the
    # action is exactly what a postcondition should be, and warning there would be
    # the noise #15 priced -- it would fire on every correct flow.
    _f, _rep = await _hollow("5 element(s) match 'tr'")
    check("FW2 CONTROL: an assertion that CHANGED is not flagged",
          not _rep.get("hollow"), f"hollow={_rep.get('hollow')}")

    # Nothing observed before the action means nothing to compare against, and an
    # unknown must not be reported as a finding (the same rule as #56's ID3).
    fb3 = FakeBridge([E(70, "button", name="Create")])
    r3 = Recorder("h3", fb3.entries_fn)
    ai3 = {"ref": "ref_70", "tabId": 1}
    at3 = await r3.before("computer", ai3)
    r3.after("computer", ai3, "clicked", at3)
    r3.after("query_elements", {"selector": "tr", "tabId": 1}, "4 element(s) match 'tr'", {})
    _f3, _rep3 = r3.compile()
    check("FW3 CONTROL: with nothing observed beforehand there is no claim to make",
          not _rep3.get("hollow"), f"hollow={_rep3.get('hollow')}")

    # ---- FP: preconditions — the state the flow starts from ---------------
    fbp = FakeBridge([E(80, "button", name="New project")])
    rp = Recorder("pre", fbp.entries_fn)
    rp.after("get_url", {"tabId": 1}, '{"url": "https://app.test/projects"}', {})
    rp.after("query_elements", {"tabId": 1, "selector": "tbody tr"},
             "4 element(s) match 'tbody tr'", {})
    ci2 = {"action": "left_click", "ref": "ref_80", "tabId": 1}
    ct2 = await rp.before("computer", ci2)
    rp.after("computer", ci2, "clicked", ct2)
    pf, pr = rp.compile()
    check("FP1 what the agent observed BEFORE it changed anything becomes the "
          "flow's precondition",
          pf.require.get("url") == "https://app.test/projects"
          and pf.require["query"] == {"selector": "tbody tr", "count": 4},
          str(pf.require))

    ok = FakeBridge([E(80, "button", name="New project")])
    ok.url = "https://app.test/projects"; ok.query_total = 4
    rok = await start(pf, 1, ok.call, ok.entries_fn)
    check("FP2 the right starting state passes — the control, without which a "
          "precondition that always fires is indistinguishable from one that "
          "works", rok["status"] == PASSED, str(rok["reason"])[:100])

    wrong = FakeBridge([E(80, "button", name="New project")])
    wrong.url = "https://app.test/login"; wrong.query_total = 4
    rw = await start(pf, 1, wrong.call, wrong.entries_fn)
    check("FP3 the WRONG starting state fails before anything runs, and says "
          "the app is not where the flow begins",
          rw["status"] == FAILED and "not in the state this flow starts" in rw["reason"]
          and "login" in rw["reason"], str(rw["reason"])[:140])
    check("FP3b ...and NOTHING was dispatched — this is the case that used to "
          "fail deep inside with a message about one element",
          not any(t == "computer" for t, _ in wrong.calls), str(wrong.calls))

    drifted = FakeBridge([E(80, "button", name="New project")])
    drifted.url = "https://app.test/projects"; drifted.query_total = 5
    rd = await start(pf, 1, drifted.call, drifted.entries_fn)
    check("FP4 a precondition catches app STATE drift too, not just the url — "
          "5 rows where the flow was recorded against 4",
          rd["status"] == FAILED and "counted 5" in rd["reason"], str(rd["reason"])[:120])

    check("FP5 a flow that establishes its own state records NO precondition, "
          "so it is derived rather than mandatory",
          Recorder("self", fbp.entries_fn).compile()[0].require == {})

    # ---- contracts -------------------------------------------------------
    check("FD16 REF_KEYS matches browser_batch's own _REF_KEYS — one concept, "
          "one spelling (#21), enforced rather than hoped for",
          _batch_ref_keys() == set(FM.REF_KEYS) | {"coordinate"},
          f"batch={_batch_ref_keys()} flows={FM.REF_KEYS}")
    check("FD17 the result-string parsers still match what mcp_server emits — "
          "#30 found `delta` dead for its whole life behind exactly this kind "
          "of contract",
          search_hits('3 match(es) for "x"') == 3
          and search_hits('No match for "x". 9 text block(s) were searched.') == 0
          and query_total("12 element(s) match 'tr'") == 12
          and _server_emits_these_shapes())
    _bad, _ok = _signatures_survive_wrapping()
    check("FD18 recording wrappers preserve every tool's SIGNATURE — browser_batch "
          "pre-flights against it, and a bare **kw wrapper refuses every batch "
          "with \"missing required argument(s) kw\"",
          not _bad and _ok, f"opaque={_bad} distinguishes_tools={_ok}")

    check("FD17c a query MISS reads as 0, not as an unreadable result — the "
          "zero case is prose, and conflating it with a parse failure makes the "
          "runner blame the contract for a page that simply lacks the element",
          query_total("No element matches 'tbody tr' in the rendered document.") == 0
          and query_total("some unrelated text") is None
          and "No element matches" in (ROOT / "mcp_server.py").read_text(encoding="utf-8"))

    check("FD17b ...and a readiness banner in front of them does not blind the "
          "parser, which is exactly when a flow is most likely to be running",
          search_hits("PAGE IS STILL SETTLING\n2 match(es) for \"x\"") == 2)


def _signatures_survive_wrapping():
    """Wrapping a tool for recording must not hide its signature.

    browser_batch's pre-flight introspects the function to decide which
    arguments a tool takes and which are required. A bare `**kw` wrapper makes
    inspect.signature report one VAR_KEYWORD parameter, and EVERY batch is then
    refused with "missing required argument(s) kw". Found live on the first
    real call after the wrappers shipped; functools.wraps sets __wrapped__,
    which inspect.signature follows.
    """
    import importlib.util
    import inspect
    spec = importlib.util.spec_from_file_location("ms_sig", ROOT / "mcp_server.py")
    ms = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ms)
    bad = []
    for name, fn in ms._BATCHABLE.items():
        ps = list(inspect.signature(fn).parameters.values())
        if len(ps) == 1 and ps[0].kind is inspect.Parameter.VAR_KEYWORD:
            bad.append(name)
    # and the two that must still differ, as a positive control
    ok = (not list(inspect.signature(ms._BATCHABLE["tabs_create_mcp"]).parameters)
          and "tabId" in inspect.signature(ms._BATCHABLE["read_page"]).parameters)
    return bad, ok


def _batch_ref_keys():
    src = (ROOT / "mcp_server.py").read_text(encoding="utf-8")
    m = re.search(r"_REF_KEYS\s*=\s*\(([^)]*)\)", src)
    return set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()


def _server_emits_these_shapes():
    src = (ROOT / "mcp_server.py").read_text(encoding="utf-8")
    return ('match(es) for "' in src and "element(s) match" in src
            and 'No match for "' in src)


def _raises(fn, needle, want_candidates=0):
    try:
        fn()
    except Unresolved as exc:
        if needle not in str(exc):
            print(f"        (reason did not mention {needle!r}: {exc})")
            return False
        if want_candidates and len(exc.candidates) != want_candidates:
            print(f"        (expected {want_candidates} candidates, "
                  f"got {len(exc.candidates)})")
            return False
        return True
    except Exception as exc:  # a different exception is not the contract
        print(f"        (raised {type(exc).__name__}: {exc})")
        return False
    return False


if __name__ == "__main__":
    sys.exit(main())
