"""Unit suite for _truncate — the output bound shared by read_page/get_page_text.

Why this exists: a blind head-slice cuts the TAIL, and in a read_page listing the
tail is the element rows while the head is the notation legend. Measured live on
the saucedemo login page (three elements, all section=form), the legend was ~610
of ~900 chars, so `read_page(max_chars=900)` returned legend and ZERO rows — and
a ref was clicked twice in that state without ever being identified. The bug is
not that the output was truncated; it is that truncation removed the payload and
kept the decoder ring.

Two fixes are pinned here together because either alone leaves the hole open:
  - the legend now names only the section values actually present (background.js),
  - and truncation drops the legend before it drops rows (this file).

Run:  python tools/test_truncate.py
"""

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_spec = importlib.util.spec_from_file_location("ms", ROOT / "mcp_server.py")
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)
_truncate = ms._truncate

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))


LEGEND = ("Current URL: /\nVisible interactive elements (3 on screen).\n"
          + ("  - " + "x" * 300 + "\n") * 3)
ROWS = ('mmid=13 | input[text] name="user-name"\n'
        'mmid=15 | input[password] name="password"\n'
        'mmid=17 | input[submit] name="Login"')
PAGE = LEGEND + ROWS


def _folded_listing():
    """A listing shaped like arXiv's: short individual rows plus folded groups.

    A folded row stands for its whole group, so counting LINES under-reports any
    loss by the fold factor — and the two truncation branches disagreed about it.
    """
    legend = "\n".join(f"  - legend line {i} explaining notation at length to eat budget"
                       for i in range(8))
    rows = [
        'mmid=9 | a name="archive home" | box(24,7,87,39)',
        'mmid=17 | a "Search" | box(2233,12,82,29)',
        "26× a in section=main - shown as ref:\"label\": "
        + " ".join(f'{40+i}:"Author {i}"' for i in range(26)),
        "45× a in section=main - shown as ref:\"label\": "
        + " ".join(f'{100+i}:"Name {i}"' for i in range(45)),
        'mmid=174 | a "Aulia Kharis" | box(255,845,156,16)',
    ]
    return ("Current URL: /list/cs.AI/recent\n" + legend + "\n" + "\n".join(rows),
            2 + 26 + 45 + 1)


def main():
    out = _truncate(PAGE, 900, "scope with ref_id")
    check("T1 a budget too small for the legend still returns element rows",
          "mmid=13" in out, out.splitlines()[-2][:70] if len(out.splitlines()) > 1 else out[:70])
    check("T2 ...and keeps the URL line for context",
          out.startswith("Current URL: /"))
    check("T3 ...and says the legend was dropped, rather than silently reshaping",
          "legend was dropped" in out)
    check("T4 ...and respects the budget", len(out) <= 900 + 220, f"{len(out)} chars")

    # As many rows as fit, and an honest count of what did not.
    tiny = _truncate(PAGE, 120, "")
    check("T5 a very small budget reports how many elements it could not show",
          "not shown" in tiny or "mmid=" in tiny, tiny.splitlines()[-1][:80])

    # NEGATIVE CONTROLS. The new path must engage ONLY when a head-slice would
    # have returned no rows at all — otherwise it silently changes output shape
    # for every caller, which is a worse bug than the one being fixed.
    reached = _truncate(PAGE, len(LEGEND) + 40, "h")
    check("T6 normal truncation is unchanged when the slice already reaches rows",
          reached.startswith("Current URL") and "legend was dropped" not in reached)
    plain = _truncate("x" * 5000, 100, "h")
    check("T7 non-listing text (get_page_text) is untouched by the row logic",
          plain.startswith("x") and "legend was dropped" not in plain)
    short = _truncate(PAGE, 10_000, "h")
    check("T8 text under budget is returned verbatim", short == PAGE)

    # T9-T12: the readiness banner must survive truncation WHOLE. Found live: a
    # get_page_text read cut it mid-sentence at "(1 progress indicator(s) visible;"
    # — losing the remaining counts AND every word of guidance, while still reading
    # as a finished clause. A banner that says how to interpret the rest of the
    # output is the last thing that should be sacrificed to make room for the rest.
    BANNER = ("*** PAGE IS STILL SETTLING (1 progress indicator(s) visible; 1 region(s) "
              "marked aria-busy). Content may still be arriving, and box() coordinates "
              "may shift as it does — re-observe before trusting a coordinate. ***\n")
    withb = _truncate(BANNER + PAGE, 300, "scope with ref_id")
    check("T9 the readiness banner survives truncation whole", withb.startswith(BANNER),
          repr(withb[:90]))
    check("T10 ...including its closing marker and all counts",
          "aria-busy" in withb and withb.count("***") == 2,
          f"{withb.count('***')} markers")
    check("T11 ...and element rows still get room after it", "mmid=" in withb,
          f"{withb.count('mmid=')} rows kept")
    check("T12 text with no banner is unaffected by the banner path",
          not _truncate(PAGE, 300, "h").startswith("***"))

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} truncation checks passed.")
    return 0 if passed == len(results) else 1


async def main_async():
    """T13-T15 exercise get_page_text ITSELF, not just the _truncate helper.

    This split is the whole point: T9-T12 passed while the real tool was broken,
    because get_page_text has its OWN outline-preserving truncation path that
    never calls _truncate. Peeling the banner off there and forgetting to restore
    it deleted it outright — a regression on the fix that was meant to stop it
    being cut in half, invisible to every existing check.
    """
    BANNER = ("*** PAGE IS STILL SETTLING (2 network request(s) in flight). Content may "
              "still be arriving. ***\n")
    OUTLINE = "\n--- DOCUMENT OUTLINE (3 headings) ---\n" + "\n".join(
        f"  h2: Heading number {i} with a reasonably long title" for i in range(40))
    BODY = "Article body. " * 200

    class FB:
        connected = True

        def __init__(self, payload):
            self.payload = payload

        async def call(self, op, **kw):
            return self.payload

    gpt = ms.get_page_text.fn if hasattr(ms.get_page_text, "fn") else ms.get_page_text

    # Outline bigger than the cap -> the "kept whole, body dropped" branch.
    ms.STATE["bridge"] = FB(BANNER + BODY + OUTLINE)
    out = await gpt(tabId=1, max_chars=300)
    check("T13 get_page_text keeps the banner when the outline exceeds the cap",
          out.startswith(BANNER), repr(out[:80]))

    # Outline small enough -> the "body truncated" branch, a DIFFERENT return.
    ms.STATE["bridge"] = FB(BANNER + BODY + "\n--- DOCUMENT OUTLINE (1 headings) ---\n  h2: One")
    out = await gpt(tabId=1, max_chars=600)
    check("T14 ...and on the body-truncated branch too", out.startswith(BANNER),
          repr(out[:80]))

    ms.STATE["bridge"] = FB(BODY + OUTLINE)
    out = await gpt(tabId=1, max_chars=300)
    # T16/T17: shown + claimed == true, at EVERY budget and through BOTH branches.
    # Live on arXiv: at max_chars=600 the listing said "2 more element(s) not shown"
    # while 135 were missing (the fallback matched only `mmid=` lines, so folded
    # groups were dropped from the output AND left out of the count); and at a
    # budget that reached rows the ordinary branch said nothing at all while 74
    # vanished. Both now count ELEMENTS through one helper.
    _text, _true = _folded_listing()
    _bad = []
    for cap in (400, 600, 900, 1200, 1800):
        out = ms._truncate(_text, cap, "scope with ref_id")
        # Count what was actually PRINTED, not what the rows declare. A partially
        # sliced fold row still carries its "26x" prefix, so _row_elements credits
        # all 26 while only 7 refs reached the page — the exact over-count the code
        # fix addresses, and using the same helper here would hide it.
        _body = out.split("[output truncated")[0]
        shown = (len(re.findall(r"^mmid=", _body, re.M))
                 + len(re.findall(r"(?:^|\s)\d+:", _body)))
        m = re.search(r"(\d+) more element\(s\) not shown", out)
        claimed = int(m.group(1)) if m else 0
        if shown + claimed != _true:
            _bad.append(f"cap={cap}: {shown}+{claimed}!={_true}")
    check("T16 shown + 'N more not shown' equals the true element total, every budget",
          not _bad, "; ".join(_bad))
    check("T17 ...and a folded row is counted as its whole group, not as one line",
          ms._row_elements('26× a in section=main - shown as ref:"label": 40:"x"') == 26,
          f"got {ms._row_elements(chr(50)+chr(54)+chr(215)+chr(32)+chr(97))}")

    check("T15 text with no banner is unchanged by the banner path",
          not out.startswith("***"), repr(out[:60]))

    # ---- T24/T25: THE BUDGET MUST RECONCILE AGAINST WHAT THE CALLER PASSED.
    # The most-reported defect of the 24-task eval -- five sightings, four pages,
    # three agents, every one in the same direction. Two separate arithmetic bugs
    # pointing opposite ways: `max_chars` was REBOUND to `max_chars - len(banner)`
    # and the reduced figure then printed as "the N requested" (passed 1600, told
    # 1303); and the body reserved a literal 120 chars for a note that is ~560, so
    # the function returned ~440 MORE than asked while its message reported a
    # shortfall. An agent wrote: "the shortfall between the stated budget and the
    # actual cut is the one number in the run I cannot account for."
    _over, _unquoted = [], []
    for cap in (400, 600, 900, 1500, 2400, 4000):
        for _bnr_on in (True, False):
            payload = ((BANNER if _bnr_on else "") + BODY
                       + "\n--- DOCUMENT OUTLINE (2 headings) ---\n  h2: One\n  h2: Two")
            ms.STATE["bridge"] = FB(payload)
            out = await gpt(tabId=1, max_chars=cap)
            if len(out) > cap:
                _over.append(f"cap={cap} banner={_bnr_on}: returned {len(out)}")
            # Every truncation message must quote the caller's own number, so the
            # reader can add the named deductions back up to it.
            if "truncated" in out and f"max_chars={cap}" not in out:
                _unquoted.append(f"cap={cap} banner={_bnr_on}")
            # AND THE ITEMISED PARTS MUST ADD UP. This is the defect itself: the
            # numbers were arithmetically correct all along and simply could not be
            # reconciled -- an agent compared the printed body figure (7,420) to the
            # max_chars it passed (9,000) and wrote "the shortfall between the
            # stated budget and the actual cut is the one number in the run I cannot
            # account for". It was the outline, the banner and the note, none of
            # which the message named.
            m = re.search(r"was spent as: (.+?), and this note", out, re.S)
            if m:
                parts = [int(x) for x in re.findall(r"(\d+) (?:body|readiness|document)", m.group(1))]
                note = out[out.index("\n\n[body truncated"):out.index("]\n\n") + 3]
                # The named parts plus the note ARE the whole return. If they do not
                # add up, some share of the caller's budget went somewhere the
                # message does not account for -- which is the defect verbatim.
                if sum(parts) + len(note) != len(out):
                    _unquoted.append(
                        f"cap={cap}: itemised {parts} + note {len(note)} = "
                        f"{sum(parts) + len(note)}, but returned {len(out)}")
    check("T24 get_page_text never returns more than the max_chars it was given",
          not _over, "; ".join(_over))
    check("T25 ...and its note quotes the CALLER's max_chars and itemises where it went",
          not _unquoted, "; ".join(_unquoted))

    # T18: A FOLD IS ONE VERY LONG LINE, so a slice almost always lands inside it.
    # Found live: `->/2026/08/21/business/are-you-cuttin`, a URL cut mid-path where
    # the fragment is a plausible slug and nothing marked it -- the residual note
    # counts missing ELEMENTS, so it says nothing about a mangled href. Swept across
    # every budget because the two failure shapes appear at different offsets: a cut
    # mid-token, and a cut on a SPACE INSIDE a quoted label, which leaves the quote
    # unterminated while looking clean.
    _fold = ("45× a, same structure, in document order - shown as ref:\"label\"->href: "
             + " ".join(f'{10+i}:"Headline number {i}"->/2026/08/21/business/story-slug-{i}'
                        for i in range(12)))
    _txt = "\n".join(["Current URL: /",
                      "Visible interactive elements (46 on screen).", _fold])
    _bad = []
    for _cap in range(250, 1000):
        _o = ms._truncate(_txt, _cap, "h")
        _b = _o.split("[output truncated")[0].rstrip()
        if _b.endswith("rest)"):
            continue
        if _b.count('"') % 2:
            _bad.append(f"cap={_cap} unterminated quote")
            continue
        _tail = _b.split(" ")[-1]
        if not (_tail[:1].isdigit() and '"' in _tail):
            _bad.append(f"cap={_cap} partial member {_tail[-24:]!r}")
    check("T18 a truncated fold never leaves half a member, at any budget",
          not _bad, f"{len(_bad)} bad of 750 budgets; first: {(_bad or ['-'])[0]}")

    # T19: THE SAME SWEEP FOR PLAIN ROWS, which T18's guard never covered — it
    # returned early unless the final line matched the FOLD pattern. Found live on
    # the Fed's page at max_chars=1200:
    #   ref_545 | div "An official website of the United States Government Here's
    #                  how you know Official websit
    # cut mid-word, opening quote never closed, no marker, so the label reads as
    # finished content. Reported by two agents independently. Long labels on purpose:
    # a row has to be long enough that budgets land inside it, which is the ordinary
    # case on any real page.
    _rows = "\n".join(
        f'ref_{100 + i} | div "An official website of the United States Government '
        f'Here is how you know official websites use .gov number {i}"'
        for i in range(6))
    _txt2 = "\n".join(["Current URL: /releases/h15",
                       "Visible interactive elements (6 on screen).", _rows])
    _bad2 = []
    for _cap in range(200, 900):
        _o = ms._truncate(_txt2, _cap, "h")
        _b = _o.split("[output truncated")[0].rstrip()
        if _b.count('"') % 2:
            _bad2.append(f"cap={_cap} unterminated quote: {_b.splitlines()[-1][-40:]!r}")
            continue
        _lastline = _b.splitlines()[-1] if _b.splitlines() else ""
        # Every printed row must be whole: if it starts a ref row it must also close
        # its quoted label.
        if _lastline.lstrip().startswith("ref_") and not _lastline.rstrip().endswith('"'):
            _bad2.append(f"cap={_cap} partial row: {_lastline[-40:]!r}")
    check("T19 ...and a truncated PLAIN row is dropped rather than left amputated,"
          " at any budget",
          not _bad2, f"{len(_bad2)} bad of 700 budgets; first: {(_bad2 or ['-'])[0]}")

    # T20: T19's guard tested `startswith("ref_")`, which has a hole a live agent
    # landed in — a cut three characters into a row leaves the bare token `ref`,
    # which does not start with "ref_" and so was returned as a finished line:
    #     ref_239 | a "upvote"
    #      ref
    #     [output truncated at 3000 chars — ...]
    # `ref` reads as a row. Any PREFIX of the token is the same hazard, so this
    # sweeps every budget for a trailing fragment of one.
    _bad3 = []
    for _cap in range(150, 900):
        _o = ms._truncate(_txt2, _cap, "h")
        _b = _o.split("[output truncated")[0].rstrip()
        _tail = (_b.splitlines() or [""])[-1].strip()
        if _tail and _tail != "Current URL: /releases/h15" and not _tail.startswith("Visible")                 and "ref_".startswith(_tail[:4]) and not _tail.startswith("ref_"):
            _bad3.append(f"cap={_cap} left the fragment {_tail!r}")
    check("T20 ...and never leaves a fragment of the ref token itself",
          not _bad3, f"{len(_bad3)} bad of 750 budgets; first: {(_bad3 or ['-'])[0]}")

    # T21: COUNT WHAT THE READER CAN ACT ON, which T16 cannot. T16 compares
    # `_row_elements` on both sides of the cut, and that function returns a FOLD'S
    # GROUP SIZE — so a partially-printed fold is credited at full membership on both
    # sides and the error cancels. It cannot detect a partial-fold miscount at all,
    # which is exactly the defect #25 recorded ("claimed 17 more when ~41 were
    # missing"). Counting DISTINCT REFS present in the body is the reader's own
    # arithmetic: a ref that printed is actionable, one that did not is not, whatever
    # shape its row had.
    #
    # This check also corrected my own measurement. Investigating a live report of a
    # wrong residual, my first probe used `_row_elements` for the "shown" side and
    # made the tool look wrong by 6 elements at one budget — the inflation was the
    # probe's, not the tool's. Shape modelled on Hacker News: a nav fold, twenty
    # plain rows, then two large folds, so budgets land inside folds and between them.
    _lg = chr(10).join(f"  - legend line {i} explaining notation at some length"
                       for i in range(6))
    _rws = ['8x a, identical siblings, in document order - ref:"label": '
            + " ".join(f'{10 + i}:"nav {i}"' for i in range(8))]
    _rws += [f'ref_{100 + i} | a "Story headline number {i} which is fairly long"'
             for i in range(20)]
    _rws.append('15x span, identical siblings, in document order - ref:"label": '
                + " ".join(f'{200 + i}:"{i * 7} comments"' for i in range(15)))
    _rws.append('16x tr, identical siblings, in document order - ref:"label": '
                + " ".join(f'{300 + i}:"domain{i}.com"' for i in range(16)))
    _lst = ("Current URL: /" + chr(10) + "Visible interactive elements (59 on screen)."
            + chr(10) + _lg + chr(10) + chr(10).join(_rws))

    def _actionable(body):
        refs = set(re.findall(r"\bref_(\d+)\b", body))
        refs |= set(re.findall(r'(?:^|\s)(\d+):"', body))
        return len(refs)

    _true = _actionable(chr(10).join(_rws))
    _bad4 = []
    for _cap in range(600, 2600, 20):
        _o = ms._truncate(_lst, _cap, "h")
        _body = _o.split("[output truncated")[0]
        _m = re.search(r"(\d+) more element\(s\) not shown", _o)
        _claimed = int(_m.group(1)) if _m else 0
        _shown = _actionable(_body)
        if _shown + _claimed != _true:
            _bad4.append(f"cap={_cap}: printed {_shown} + claimed {_claimed} != {_true}")
    check("T21 printed refs + 'N more not shown' equals the true total, counted the"
          " way the reader counts it (folds included)",
          not _bad4, f"{len(_bad4)} bad of 100 budgets; first: {(_bad4 or ['-'])[0]}"
                     f" (true total {_true})")

    # ---- T22/T23: A BIG FIRST ROW MUST NOT DELETE THE WHOLE LISTING.
    # #13's fallback drops the legend when a plain slice would return no rows — but it
    # asked whether the raw slice REACHES a row, while `_whole_members` (added later,
    # for half-written rows) then removes that row when the cut left it incomplete. The
    # two cancelled: guard sees a row, keeps the legend, slicer deletes the row, caller
    # gets a decoder ring and nothing to decode. Found by reproducing an app-shell page
    # offline after a live read returned almost nothing; T1-T21 all passed throughout,
    # because none of them has a FIRST row long enough to trigger it.
    _legend = ("Current URL: /x\nVisible interactive elements (21 on screen).\n"
               + "\n".join(f"  - notation line {i} explaining something at length" for i in range(8))
               + "\n")
    _huge = 'ref_3 | div "' + ("Shell label word " * 60).strip() + '"'
    _small = [f'ref_{i} | a "Item {i}"' for i in range(10, 22)]
    _doc = _legend + _huge + "\n" + "\n".join(_small)

    # A budget that fits the first row once the legend is gone, but not with it.
    _out = _truncate(_doc, len(_huge) + 120)
    check("T22 a budget that fits the first row only WITHOUT the legend drops the"
          " legend and prints the row, instead of returning neither",
          "ref_3" in _out, f"got {len(_out)} chars, has_row={'ref_' in _out}")

    # A budget too small for even the first row: must SAY so, and name the real blocker.
    _out2 = _truncate(_doc, 300)
    _blames_first = "FIRST one is" in _out2 and str(len(_huge)) in _out2
    check("T23 ...and when not even the first row fits it says NOTHING could be shown"
          " and names the row that blocked it, not a smaller one that would have fit",
          "NOTHING could be shown" in _out2 and _blames_first,
          f"blames_first={_blames_first}")

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} truncation checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    import asyncio

    main()
    sys.exit(asyncio.run(main_async()))
