"""Repeated-record folding — compression that must not cost actionability.

WHY THIS EXISTS
---------------
Measured on 35 frozen sites before this feature: 46% of pages exceeded the
150-entry listing cap, the median capped page silently lost 124 elements, and
**96% of a median listing sat in a structurally repeated group** — 20 product
cards, 50 search results, a nav column. Full price was being paid per row for
near-identical rows, and the tail was then dropped.

Folding is a SERIALIZATION change only. The structured array is returned before
this pass runs, which is what `find` and every audit consume — so compression
cannot silently shrink the search space.

Matched A/B on the same 30 sites, detail="brief":
    folding OFF  211,942 chars   answerability 0.761
    folding ON   174,184 chars   answerability 0.759
    => -17.8% tokens for -0.002 answerability, and out-of-sample recall
       unchanged at 93.6% (Mind2Web, 47 labelled targets).

THE INVARIANTS THAT MAKE IT SAFE
--------------------------------
Compression is only acceptable if every folded row stays actionable and
answerable. If a card collapses into a group line, its ref must still be there
and its href must still be there — otherwise we would trade tokens for recall,
which is the one trade this project must never make.

Run:  python tools/test_folding.py
"""

import asyncio
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract as _shared_extract  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = _shared_extract("_collectInteractivePage", BG, verify=True)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))


def cards(n, start=1):
    return "".join(
        f'<a href="/item/{i}" style="display:block;width:300px;height:40px">Product number {i}</a>'
        for i in range(start, start + n))


PAGE_FOLD = f'<!doctype html><meta charset=utf-8><body style="margin:0">{cards(12)}</body>'
PAGE_SMALL = f'<!doctype html><meta charset=utf-8><body style="margin:0">{cards(4)}</body>'


async def listing(page, html, detail="brief", nofold=False):
    await page.set_content(html, wait_until="domcontentloaded")
    await page.wait_for_timeout(120)
    if nofold:
        await page.evaluate("()=>{window.__abNoFold=true;}")
    return await page.evaluate(
        "(function(){ " + COLLECT + "; return _collectInteractivePage(false, null, '" + detail + "'); })()")


async def structured(page, html, detail="brief"):
    await page.set_content(html, wait_until="domcontentloaded")
    await page.wait_for_timeout(120)
    return await page.evaluate(
        "(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, '" + detail + "'); })()")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 900, "height": 900})
        await page.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))

        # ORDER MATTERS: `window.__abNoFold` survives a later set_content, so a
        # nofold run poisons every subsequent listing on this page — which made
        # the "folded" output unfolded and D3 fail against a real, working fold.
        # Everything that needs folding ON runs first; the disabling run is last.
        folded = await listing(page, PAGE_FOLD)

        check("D1 a repeated group of 12 folds into a group line",
              "12×" in folded, folded.splitlines()[-1][:90])

        # THE LOAD-BEARING ONES: compression must not cost actionability.
        # SAME page load for both passes. Calling set_content again restarts the
        # page and the additive mmid counter keeps climbing, so refs from a second
        # load never match the first — comparing across loads tested nothing.
        await page.set_content(PAGE_FOLD, wait_until="domcontentloaded")
        await page.wait_for_timeout(120)
        st = await page.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, 'brief'); })()")
        folded = await page.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false, null, 'brief'); })()")
        mmids = [str(e["mmid"]) for e in st if (e.get("href") or "").find("/item/") >= 0]
        missing = [m for m in mmids if not re.search(rf"\b{m}:", folded)]
        check("D3 every folded row keeps its own ref", not missing,
              f"{len(mmids)} rows, {len(missing)} refs lost: {missing[:5]}")
        hrefs_missing = [i for i in range(1, 13) if f"/item/{i}" not in folded]
        check("D4 every folded row keeps its href (answerability preserved)",
              not hrefs_missing, f"missing /item/: {hrefs_missing}")
        labels_missing = [i for i in range(1, 13) if f"Product number {i}" not in folded]
        check("D5 every folded row keeps its label", not labels_missing,
              f"missing labels: {labels_missing}")

        check("D6 the STRUCTURED array is never folded (find's search space intact)",
              len([e for e in st if (e.get("href") or "").startswith("/item/")]) == 12,
              f"{len(st)} structured entries")

        small = await listing(page, PAGE_SMALL)
        check("D7 a group below the threshold is NOT folded",
              "4×" not in small and "Product number 1" in small,
              small.splitlines()[-1][:80])

        # D2 last, and on a FRESH page: the nofold flag is sticky for the life of
        # the JS context, so it must not run before anything that needs folding.
        page2 = await browser.new_page(viewport={"width": 900, "height": 900})
        await page2.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        plain = await listing(page2, PAGE_FOLD, nofold=True)
        check("D2 folding actually saves tokens", len(folded) < len(plain),
              f"{len(folded)} vs {len(plain)} chars ({(len(folded)-len(plain))/len(plain):+.0%})")

        await browser.close()

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} folding checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
