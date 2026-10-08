"""browser_batch — pre-flight validation and the two page-change guards.

WHY THIS SUITE EXISTS
---------------------
browser_batch runs a list of tool calls in one round trip, and until now it broke
only on an unknown tool name or a raised exception. Everything else it fired blind:

  - A typo in `name` at index 3 was discovered AFTER indices 0-2 had run, so
    irreversible actions landed because of a spelling mistake.
  - A step that NAVIGATED did not stop the batch, so the remaining steps — planned
    against the old page, with refs and coordinates from before it — were dispatched
    into whatever the page became. That is CLAUDE.md #10/#11/#12's signature (input
    landing somewhere other than the element while the tool reports success),
    reproduced at batch level, with the docstring stating the hazard rather than
    guarding it.

browser-use's multi_act has both guards: a static `terminates_sequence` flag, and a
runtime URL/focus comparison after every action. This is the same shape.

WHAT IS FAKED, AND WHY THAT IS ENOUGH
-------------------------------------
The tools and the bridge are replaced with recorders, so the checks are about the
BATCH's control flow — what ran, what did not, and what it said — which is the part
that was missing. The tools themselves are covered by their own suites.

Run:  python tools/test_batch.py
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_spec = importlib.util.spec_from_file_location("ms_batch", ROOT / "mcp_server.py")
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)

results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))


def text_of(out):
    return "\n".join(getattr(c, "text", "") for c in out)


RAN = []


async def fake_tool(tabId: int, value: str = "x"):
    RAN.append(("fake_tool", tabId, value))
    return f"did {value}"


async def fake_navigate(url: str, tabId: int):
    RAN.append(("navigate", tabId, url))
    return f"went to {url}"


async def fake_computer(action: str, tabId: int, text: str = "x", coordinate=None):
    """The REAL `computer`, under its real name, because the rule keys on its input.

    A step can address the previous page without naming a ref: `action="key"` and
    `action="type"` go to whatever has FOCUS, which a page change moved. That is an
    implicit target, not a ref, and B5f pins it. `action="screenshot"` has no target
    at all and is B5f2's control -- registering this under the real tool name is
    what makes the two distinguishable, where a hand-named `fake_write` could only
    ever test whether some list happened to contain it.
    """
    RAN.append(("computer", tabId, action))
    return f"did {action}"


async def fake_act(tabId: int, ref: str = "ref_1"):
    """A step that NAMES A REF — i.e. one planned against a particular page.

    `fake_tool` takes only a tabId and so means the same thing whatever the page
    became; it is the stand-in for an observation. The distinction is the whole
    subject of B5c/B10, so the suite needs both.
    """
    RAN.append(("fake_act", tabId, ref))
    return f"acted on {ref}"


# Every page_fingerprint the batch asks for. The guard that skips them is only
# worth having if it can be shown to skip, and only safe if it can be shown NOT to
# skip when a ref is coming (B10/B10b).
FPS = []


def install(fingerprints):
    """Point _BATCHABLE at recorders and _bridge at a scripted fingerprint sequence."""
    RAN.clear()
    FPS.clear()
    ms._BATCHABLE.clear()
    ms._BATCHABLE.update({"fake_tool": fake_tool, "navigate": fake_navigate,
                          "fake_act": fake_act, "computer": fake_computer})
    # NOTHING IS DECLARED SAFE HERE ANY MORE. This used to add `fake_tool` to an
    # `_OBSERVES` whitelist, which meant every check below was really testing
    # whether a name was in a set -- and a name missing from that set was stopped
    # whatever it did, which is the defect those checks now exist to prevent. The
    # rule reads each step's own input instead, so the fakes need no registration
    # beyond being callable.
    seq = list(fingerprints)

    class _B:
        async def call(self, op, **kw):
            if op == "page_fingerprint":
                FPS.append(kw.get("tabId"))
                return seq.pop(0) if seq else {"url": "u", "elements": 10, "textLen": 5}
            return None

    async def _bridge():
        return _B()

    ms._bridge = _bridge


SAME = {"url": "https://a.test/", "elements": 100, "textLen": 500}
MOVED = {"url": "https://b.test/", "elements": 100, "textLen": 500}
GREW = {"url": "https://a.test/", "elements": 140, "textLen": 900}


async def main():
    # ---- B1-B3: pre-flight. NOTHING may run when any step is malformed.
    install([SAME] * 8)
    out = await ms.browser_batch([
        {"name": "fake_tool", "input": {"tabId": 1, "value": "first"}},
        {"name": "fake_toool", "input": {"tabId": 1}},
    ])
    t = text_of(out)
    check("B1 an unknown tool name at index 1 stops the batch BEFORE index 0 runs",
          not RAN and "REFUSED" in t and "NOTHING in this batch ran" in t,
          f"ran={RAN} said={t[:70]!r}")
    check("B1b ...and it names the tools that ARE batchable",
          "fake_tool" in t and "Batchable tools" in t, t[-90:])

    install([SAME] * 8)
    out = await ms.browser_batch([
        {"name": "fake_tool", "input": {"tabId": 1}},
        {"name": "fake_tool", "input": {"tabId": 1, "vale": "typo"}},
    ])
    t = text_of(out)
    check("B2 an unexpected argument stops it too, naming the argument and the "
          "accepted ones",
          not RAN and "vale" in t and "value" in t, f"ran={RAN} said={t[:100]!r}")

    install([SAME] * 8)
    out = await ms.browser_batch([{"name": "fake_tool", "input": {"value": "no tab"}}])
    check("B3 a missing required argument stops it",
          not RAN and "missing required" in text_of(out).lower(), text_of(out)[:90])

    # THE NEGATIVE CONTROL. Refusing everything would pass B1-B3 while breaking the
    # tool outright, so a well-formed batch must still run end to end.
    install([SAME, SAME, SAME, SAME])
    out = await ms.browser_batch([
        {"name": "fake_tool", "input": {"tabId": 1, "value": "a"}},
        {"name": "fake_tool", "input": {"tabId": 1, "value": "b"}},
    ])
    check("B4 ...while a well-formed batch runs every step",
          len(RAN) == 2 and RAN[1][2] == "b" and "BATCH STOPPED" not in text_of(out),
          f"ran={RAN}")

    # ---- B5: LAYER 1, the declaration. navigate always changes the page, so a step
    # that NAMES A REF from before it must not fire. (Until the ref test existed,
    # these checks used a ref-free `fake_tool` as the stand-in for "an action" —
    # which encoded the old implementation, where a navigation stopped EVERYTHING.
    # The invariant was always about refs planned against the old page; B5c is the
    # other half of it.)
    install([SAME] * 8)
    out = await ms.browser_batch([
        {"name": "navigate", "input": {"url": "https://b.test/", "tabId": 1}},
        {"name": "fake_act", "input": {"tabId": 1, "ref": "ref_9"}},
        {"name": "fake_act", "input": {"tabId": 1, "ref": "ref_10"}},
    ])
    t = text_of(out)
    check("B5 after a navigation, a step naming a ref does NOT run",
          len(RAN) == 1 and RAN[0][0] == "navigate" and "SKIPPED" in t,
          f"ran={[r[0] for r in RAN]}")
    check("B5b ...and it counts and NAMES the skipped actions, and says refs are stale",
          "2 STEP(S) SKIPPED" in t and "fake_act" in t and "stale" in t.lower(),
          t[-150:])

    # B5c IS THE POINT OF THE CHANGE. `navigate -> read_page` is the commonest
    # two-step sequence there is, and it was costing a whole agent turn (~3.6s
    # measured) because the batch ended at the navigation. An observation names no
    # ref, so the navigation cannot have invalidated it.
    install([SAME] * 8)
    out = await ms.browser_batch([
        {"name": "navigate", "input": {"url": "https://b.test/", "tabId": 1}},
        {"name": "fake_tool", "input": {"tabId": 1, "value": "observe"}},
    ])
    check("B5c ...while a ref-FREE step after a navigation does run",
          len(RAN) == 2 and RAN[1][0] == "fake_tool"
          and "BATCH STOPPED" not in text_of(out), f"ran={[r[0] for r in RAN]}")

    # ...and the two rules compose: observe after the navigation, then refuse the
    # ref step, and SAY that the earlier steps were fine so their output is usable.
    install([SAME] * 8)
    out = await ms.browser_batch([
        {"name": "navigate", "input": {"url": "https://b.test/", "tabId": 1}},
        {"name": "fake_tool", "input": {"tabId": 1, "value": "observe"}},
        {"name": "fake_act", "input": {"tabId": 1, "ref": "ref_9"}},
    ])
    t = text_of(out)
    check("B5d ...and a ref step AFTER that observation is still refused, naming it",
          len(RAN) == 2 and "fake_act" not in [r[0] for r in RAN]
          and "1 STEP(S) SKIPPED" in t and "fake_act" in t,
          f"ran={[r[0] for r in RAN]} said={t[-120:]!r}")

    # B5e IS THE DEFECT THIS ROUND FIXED. A skipped ref step used to `break`, so the
    # observation BEHIND it was dropped too -- including, absurdly, the `read_page`
    # the stop message itself told the agent to go and perform. Measured live: a
    # click whose own DOM change tripped the guard lost the `get_page_text` behind
    # it and cost a whole agent turn to reissue a call the batch was already holding.
    install([SAME] * 8)
    out = await ms.browser_batch([
        {"name": "navigate", "input": {"url": "https://b.test/", "tabId": 1}},
        {"name": "fake_act", "input": {"tabId": 1, "ref": "ref_9"}},
        {"name": "fake_tool", "input": {"tabId": 1, "value": "read it back"}},
    ])
    t = text_of(out)
    check("B5e a ref-free observation AFTER a skipped ref step STILL RUNS",
          [r[0] for r in RAN] == ["navigate", "fake_tool"]
          and "1 STEP(S) SKIPPED" in t,
          f"ran={[r[0] for r in RAN]} said={t[-120:]!r}")

    # B5g IS THE REGRESSION CHECK. The `_OBSERVES` whitelist (added with B5e) made a
    # SECOND `navigate` stop the batch, because navigate is not an observation --
    # so `navigate -> read -> navigate -> read`, the commonest two-hop shape there
    # is, ended at hop two. Found by the first task of a live benchmark, not by this
    # suite, which is why it is pinned now: a navigate that names its own absolute
    # destination plans nothing against the page it is leaving.
    install([SAME] * 10)
    out = await ms.browser_batch([
        {"name": "navigate", "input": {"url": "https://a.test/", "tabId": 1}},
        {"name": "fake_tool", "input": {"tabId": 1, "value": "read hop 1"}},
        {"name": "navigate", "input": {"url": "https://b.test/", "tabId": 1}},
        {"name": "fake_tool", "input": {"tabId": 1, "value": "read hop 2"}},
    ])
    t = text_of(out)
    check("B5g a two-hop navigate->read->navigate->read batch runs ALL FOUR steps",
          [r[0] for r in RAN] == ["navigate", "fake_tool", "navigate", "fake_tool"]
          and "BATCH STOPPED" not in t,
          f"ran={[r[0] for r in RAN]} said={t[-110:]!r}")

    # ...and the half that keeps it honest: back/forward are NOT self-contained,
    # because they resolve against the tab's history rather than naming a
    # destination, so a page change really can make them mean something else.
    install([SAME] * 10)
    out = await ms.browser_batch([
        {"name": "navigate", "input": {"url": "https://a.test/", "tabId": 1}},
        {"name": "navigate", "input": {"url": "back", "tabId": 1}},
    ])
    # The INVARIANT is that `back` does not fire -- it resolves against the tab's
    # history, which the page change rewrote. It used to also assert the words
    # "BATCH STOPPED", which encoded the implementation: a step that addresses the
    # old page is now SKIPPED and named, like every other such step, instead of
    # ending the batch wholesale. Asserting the wording made this check a second
    # copy of the rule rather than a test of it.
    check("B5g2 CONTROL: navigate('back') after a page change does NOT run",
          [r[0] for r in RAN] == ["navigate"] and "SKIPPED" in text_of(out),
          f"ran={[r[0] for r in RAN]} said={text_of(out)[-130:]!r}")

    # B5f IS ITS CONTROL, and without it B5e could be satisfied by deleting the
    # guard. A step can address the previous page WITHOUT naming a ref: a keystroke
    # goes to whatever has FOCUS, which the page change moved. That is an implicit
    # target, and it is read off the step's own input (`action`), not off a list of
    # tool names -- the list is what had to be remembered and was not, three times.
    install([SAME] * 8)
    out = await ms.browser_batch([
        {"name": "navigate", "input": {"url": "https://b.test/", "tabId": 1}},
        {"name": "computer", "input": {"action": "key", "text": "Enter", "tabId": 1}},
        {"name": "fake_tool", "input": {"tabId": 1, "value": "still runs"}},
    ])
    t = text_of(out)
    check("B5f CONTROL: a keystroke, which targets the FOCUSED element, does not "
          "fire after a page change",
          [r[0] for r in RAN] == ["navigate", "fake_tool"] and "SKIPPED" in t,
          f"ran={[r[0] for r in RAN]} said={t[-150:]!r}")

    # B5f2 IS THE OTHER DIRECTION, and it is what stops B5f being satisfied by
    # blacklisting the whole `computer` tool -- which is exactly what the old
    # whitelist did, "absent even for action=screenshot". A screenshot has no
    # target at all, so a page change cannot make it address the wrong thing.
    install([SAME] * 8)
    out = await ms.browser_batch([
        {"name": "navigate", "input": {"url": "https://b.test/", "tabId": 1}},
        {"name": "computer", "input": {"action": "screenshot", "tabId": 1}},
        {"name": "fake_tool", "input": {"tabId": 1, "value": "also runs"}},
    ])
    check("B5f2 CONTROL: a screenshot, which targets nothing, still runs",
          [r[0] for r in RAN] == ["navigate", "computer", "fake_tool"],
          f"ran={[r[0] for r in RAN]}")

    # B5h: THE THIRD REGRESSION OF THE SAME SHAPE. `javascript_tool` was stopped
    # after a navigate although it names no ref and resolves its own selectors
    # against whatever document exists WHEN IT RUNS. Live: a batch lost its JS step
    # to "javascript_tool CHANGES STATE", costing a whole agent turn.
    install([SAME] * 8)
    ms._BATCHABLE["javascript_tool"] = fake_tool
    out = await ms.browser_batch([
        {"name": "navigate", "input": {"url": "https://b.test/", "tabId": 1}},
        {"name": "javascript_tool", "input": {"tabId": 1, "value": "document.title"}},
    ])
    check("B5h a javascript_tool step after a navigate runs: it names no ref and "
          "resolves against the document it finds",
          [r[0] for r in RAN] == ["navigate", "fake_tool"],
          f"ran={[r[0] for r in RAN]} said={text_of(out)[-130:]!r}")

    # ---- B6/B7: LAYER 2, runtime detection, for the steps no flag can predict.
    install([SAME, MOVED, SAME, SAME])
    out = await ms.browser_batch([
        {"name": "fake_tool", "input": {"tabId": 1, "value": "clicks a link"}},
        {"name": "fake_act", "input": {"tabId": 1, "ref": "ref_9"}},
    ])
    check("B6 a step that navigates WITHOUT being declared is caught by the URL check",
          len(RAN) == 1 and "navigated to https://b.test/" in text_of(out),
          f"ran={len(RAN)} said={text_of(out)[-110:]!r}")

    install([SAME, GREW, SAME, SAME])
    out = await ms.browser_batch([
        {"name": "fake_tool", "input": {"tabId": 1, "value": "opens a dialog"}},
        {"name": "fake_act", "input": {"tabId": 1, "ref": "ref_9"}},
    ])
    check("B7 ...and a same-URL DOM change (a dialog opening) is caught too",
          len(RAN) == 1 and "DOM changed" in text_of(out),
          f"ran={len(RAN)} said={text_of(out)[-110:]!r}")

    # THE OTHER NEGATIVE CONTROL, and the one that matters most: a guard that fires
    # on everything is indistinguishable from a guard that works, and it would make
    # the tool useless. CLAUDE.md #15's rule — verify in BOTH directions.
    install([SAME, SAME, SAME, SAME, SAME])
    out = await ms.browser_batch([
        {"name": "fake_tool", "input": {"tabId": 1, "value": "a"}},
        {"name": "fake_tool", "input": {"tabId": 1, "value": "b"}},
        {"name": "fake_tool", "input": {"tabId": 1, "value": "c"}},
    ])
    check("B8 ...and a settled page does not trip either guard",
          len(RAN) == 3 and "BATCH STOPPED" not in text_of(out),
          f"ran={len(RAN)}")

    # A fingerprint that cannot be taken must DEGRADE, not break: the gate may refuse
    # it, or the tab may be mid-navigation. Layer 1 still applies.
    install([])

    class _Dead:
        async def call(self, op, **kw):
            raise RuntimeError("bridge unavailable")

    async def _dead_bridge():
        return _Dead()

    ms._bridge = _dead_bridge
    out = await ms.browser_batch([
        {"name": "fake_tool", "input": {"tabId": 1, "value": "a"}},
        {"name": "fake_tool", "input": {"tabId": 1, "value": "b"}},
    ])
    check("B9 an unavailable fingerprint degrades to Layer 1 rather than failing the batch",
          len(RAN) == 2, f"ran={len(RAN)}")

    # ---- B10/B10b: THE FINGERPRINT IS A ROUND TRIP, so it is only taken where its
    # answer can change what happens next. Layer 2 ran after EVERY step, which made
    # a batch of N steps cost 2N bridge round trips — measured live at ~162ms each,
    # so a 7-step read batch spent ~1.1s asking whether a read had changed the page.
    # A read names no ref, so nothing downstream could have been invalidated.
    #
    # B10b is the half that makes B10 mean something: "we never fingerprint" would
    # also pass B10 while removing the guard entirely, and the suite would be green
    # over a tool that fires blind — which is the defect this file was written for.
    install([SAME] * 8)
    out = await ms.browser_batch([
        {"name": "fake_tool", "input": {"tabId": 1, "value": "read a"}},
        {"name": "fake_tool", "input": {"tabId": 1, "value": "read b"}},
        {"name": "fake_tool", "input": {"tabId": 1, "value": "read c"}},
        {"name": "fake_tool", "input": {"tabId": 1, "value": "read d"}},
    ])
    check("B10 a batch of pure observations takes NO fingerprints at all",
          len(RAN) == 4 and len(FPS) == 0 and "BATCH STOPPED" not in text_of(out),
          f"ran={len(RAN)} fingerprints={len(FPS)}")

    install([SAME] * 8)
    out = await ms.browser_batch([
        {"name": "fake_tool", "input": {"tabId": 1, "value": "read a"}},
        {"name": "fake_tool", "input": {"tabId": 1, "value": "read b"}},
        {"name": "fake_act", "input": {"tabId": 1, "ref": "ref_9"}},
    ])
    check("B10b CONTROL: as soon as a ref step follows, the guard IS taken",
          len(RAN) == 3 and len(FPS) >= 2,
          f"ran={len(RAN)} fingerprints={len(FPS)}")

    # ...and it still CATCHES a change, so the skipping did not cost the guard its
    # job: the baseline is from before the batch, and the comparison happens at the
    # step that needs it rather than at every step along the way.
    install([SAME, GREW, SAME, SAME])
    out = await ms.browser_batch([
        {"name": "fake_tool", "input": {"tabId": 1, "value": "opens a dialog"}},
        {"name": "fake_tool", "input": {"tabId": 1, "value": "harmless read"}},
        {"name": "fake_act", "input": {"tabId": 1, "ref": "ref_9"}},
    ])
    check("B10c ...and a change that happened earlier in the batch is still caught "
          "at the ref step",
          len(RAN) == 2 and "fake_act" not in [r[0] for r in RAN]
          and "DOM changed" in text_of(out),
          f"ran={[r[0] for r in RAN]} said={text_of(out)[:90]!r}")

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} browser_batch checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
