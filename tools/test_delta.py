"""Delta reads — send what CHANGED, not the whole page again.

WHY
---
Every observation re-pays the full listing: ~1,000 tokens median, dozens of
observations per task. After a click, most of the page is identical — a dialog
opened, a row appeared, a label flipped. Sending the unchanged 95% again is the
largest recurring cost in the system.

WHY LINE-BASED
--------------
Diffing structured entries would require a THIRD formatter. The project already
has two (the in-page string formatter and find's Python one), and vocabulary
drift between them produced five of the eleven defects a nine-agent live study
found. Diffing the exact rows the agent already reads cannot drift from itself.

THE TRAP THIS MUST NOT FALL INTO
--------------------------------
mmids are assigned per pass and are additive, so a framework re-render gives the
same elements new numbers. Comparing on mmid turns one re-render into hundreds
of phantom add/remove pairs — the ablation audit hit exactly this and had to
solve it the same way. `_line_ident` strips the mmid and compares the element's
description, so churn alone reports NOTHING CHANGED (T3).

WHEN IT MUST REFUSE
-------------------
A delta is only a win if most rows survive. If the page turned over, the delta
is as big as the listing AND costs the reader diff-reading effort on top — worse
than just sending the page. It refuses on: no prior read (T6), a tiny page (T7),
a wholesale change (T4), a scoped read, and any URL change.

Run:  python tools/test_delta.py
"""

import importlib.util
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
delta = ms._delta_listing

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))


def rows(n, start=1, label="Item"):
    return [f'mmid={i + 100} | a "{label} {i}" href="/x/{i}" | box(0,{i * 20},300,20)'
            for i in range(start, start + n)]


def main():
    prev = rows(40)
    cur = rows(40) + ['mmid=999 | button "Remove" | box(0,900,80,20)']
    out = delta(prev, cur)
    check("T1 a one-row change on a 41-row page yields a delta",
          out is not None and "+ " in out, (out or "").splitlines()[0][:78])
    check("T2 ...and the delta is far smaller than the listing",
          out is not None and len(out) < len("\n".join(cur)) * 0.5,
          f"{len(out or '')} vs {len(chr(10).join(cur))} chars "
          f"({(len(out or '') / len(chr(10).join(cur)) - 1):+.0%})")

    # THE LOAD-BEARING CHECK. mmids are additive and per-pass; a re-render
    # renumbers everything. Comparing on mmid would report 40 removals and 40
    # additions for a page where nothing happened.
    churned = [ln.replace("mmid=1", "mmid=7") for ln in rows(40)]
    out2 = delta(rows(40), churned)
    check("T3 a re-render that only renumbers mmids reports NO changes",
          out2 is not None and "Nothing changed" in out2,
          (out2 or "").splitlines()[-1][:66])

    check("T4 a wholesale page change refuses the delta",
          delta(rows(30), rows(30, start=500, label="Totally different")) is None)

    out5 = delta(rows(30), rows(24))
    check("T5 rows that left the listing are reported",
          out5 is not None and "NO LONGER LISTED" in out5,
          (out5 or "").splitlines()[1][:66] if out5 else "")
    # The old wording claimed these refs "no longer exist". A live agent proved
    # that false: the listing is viewport-scoped, so a row can leave it by
    # scrolling while the element and its ref remain valid. Claiming knowledge we
    # do not have is worse than naming both possibilities.
    check("T5b ...without claiming they are definitely dead",
          out5 is not None and "no longer exist" not in out5
          and "scrolled out of the viewport" in out5,
          (out5 or "").splitlines()[1][:90] if out5 else "")

    # T9: geometry is not identity. Same rows, page scrolled 53px.
    moved = [ln.replace("box(0,", "box(0,5") for ln in rows(30)]
    out9 = delta(rows(30), moved)
    check("T9 a pure scroll/reflow reports NO changes",
          out9 is not None and "Nothing changed" in out9,
          (out9 or "").splitlines()[-1][:70])

    check("T6 no previous read means no delta", delta([], rows(10)) is None)
    # T7 changed meaning when the refusal rule did. The old proxy ("refuse unless
    # >=25% of rows survived") arbitrarily refused small pages; the rule now
    # compares ACTUAL sizes, so a 4-row page whose delta is one row correctly
    # produces a delta — it really is smaller. What must still be refused is a
    # delta that is not smaller, which T4 covers.
    _tiny = delta(rows(3), rows(3) + rows(1, start=9))
    check("T7 a small page still gets a delta when the delta is genuinely smaller",
          _tiny is not None and len(_tiny) < len(chr(10).join(rows(3) + rows(1, start=9))) * 1.5,
          f"{len(_tiny or '')} chars vs {len(chr(10).join(rows(3)+rows(1,start=9)))} full")

    # Counts must be honest: an agent trusting "40 unchanged" and finding 39 is
    # worse off than getting the whole listing.
    out8 = delta(rows(40), rows(40) + rows(2, start=90))
    n_new = sum(1 for ln in (out8 or "").splitlines() if ln.strip().startswith("+"))
    check("T8 the reported new-row count matches the rows shown",
          out8 is not None and "NEW OR CHANGED (2)" in out8 and n_new == 2,
          f"{n_new} '+' lines")

    # T12-T14: FEED IT WHAT THE EXTENSION ACTUALLY EMITS. Every check above builds
    # row lists by hand and calls `_delta_listing` directly, so none of them ever
    # ran `_content_rows` — and `_content_rows` split the listing on a boundary
    # string the extension does not emit ("Act on an element" vs "Act on a row by
    # its ref_N:"). It therefore returned [] for every real listing, the baseline
    # was never stored, and read_page(delta=true) answered "first read of this tab"
    # forever. The feature was dead for as long as that mismatch existed, behind a
    # green suite, because the suite tested the half that could not fail.
    #
    # The boundary line here is copied from background.js's own legend. If the
    # extension changes it, C12 in test_contracts.py fails; if the parsing changes,
    # these do.
    _ACT = ("Act on a row by its ref_N: form_input (one field), fill_form (a whole "
            "form incl. dropdowns/checkboxes, with optional submit), computer "
            "(left_click / hover / scroll_to by ref, or screenshot to look at pixels).")

    def _listing(*rowlines):
        return "\n".join([
            "Current URL: /x",
            f"Visible interactive elements ({len(rowlines)} on screen).",
            '  - name="..." — IDENTITY (label / accessible name).',
            _ACT, *rowlines])

    _before = _listing('ref_1 | button "Alpha"', 'ref_2 | a "Beta"',
                       'ref_3 | input[text] name="Gamma"')
    _r1 = ms._content_rows(_before)
    check("T12 rows are extracted from a REAL listing, past the real boundary line",
          len(_r1) == 3 and _r1[0].startswith("ref_1"),
          f"{len(_r1)} rows: {_r1[:2]}")
    check("T13 ...and the preamble and legend are not mistaken for elements",
          not any("Current URL" in r or "IDENTITY" in r or r.startswith("Act on") for r in _r1),
          f"rows={_r1}")
    _after = ms._content_rows(_before.replace('ref_2 | a "Beta"', 'ref_2 | a "Beta Updated"'))
    _d = delta(_r1, _after)
    check("T14 ...so a one-row change over real listings produces a real delta",
          _d is not None and "NEW OR CHANGED (1)" in _d and "Beta Updated" in _d,
          (_d or "NO DELTA — the feature is inert on real input").splitlines()[0][:80])

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} delta checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
