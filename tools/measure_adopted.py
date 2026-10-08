"""Cost of the browser-use-derived listing additions, measured on the frozen corpus.

Two changes are priced here, both on the SAME page load per site so run-order drift
cannot align with variant order (CLAUDE.md #19: block-structured A/B measures drift,
not behaviour):

  A. constraints= / options= / format= per row  -- purely additive text, gated on the
     element declaring the attribute. Priced as a share of listing characters.
  B. `type` in the fold shape key -- BEHAVIOURAL: it splits folds whose members do not
     share an input type, so it can only add lines. Priced by re-running the SAME
     extracted collector with that block neutered.

Variant B is produced by string-patching the extracted source, so both variants are the
same code path on the same DOM, measured back to back.

Run:  python tools/measure_adopted.py [--n 30]
"""

import argparse
import asyncio
import json
import re
import statistics
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract as _extract_fn  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "temp" / "frozen"
TAG_JS = str(ROOT / "extension" / "listener_tag.js")
VIEWPORT = {"width": 1280, "height": 1600}
BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = _extract_fn("_collectInteractivePage", BG, verify=True)

# Neuter the type-in-shape-key block: same source, one predicate flipped off.
COLLECT_NOTYPE = COLLECT.replace("if (_tg === 'input' || _tg === 'button') {",
                                 "if (false) {")
assert COLLECT_NOTYPE != COLLECT, "fold-key patch did not apply -- the A/B is vacuous"

FOLD_RE = re.compile(r"^\s*\d+× ", re.M)


async def one(browser, name, url):
    ctx = await browser.new_context(viewport=VIEWPORT)
    try:
        await ctx.add_init_script(path=TAG_JS)
        har = FROZEN / f"{name}.har"
        if not har.exists():
            return None
        await ctx.route_from_har(str(har), not_found="abort")
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        await page.wait_for_timeout(700)

        listing = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()")
        entries = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        listing_b = await page.evaluate("(function(){ " + COLLECT_NOTYPE + "; return _collectInteractivePage(false); })()")
        if not isinstance(listing, str) or not listing.strip():
            return None

        # Only rows that were actually PRINTED can cost anything, so the numerator and
        # the denominator must come from the same population (#22: a ratio whose halves
        # come from different populations reported markers at 78.7% of a payload).
        # ROWS ARE INDENTED. The default format is the tree, so every row carries
        # leading spaces and an `^ref_` anchor matched NOTHING -- the first run of
        # this script reported +0 chars on all 26 sites including a <select> demo,
        # which is the kind of too-clean number CLAUDE.md says to re-derive rather
        # than believe. Fold counting used `^\s*` already and was unaffected.
        add = 0
        for m in re.finditer(r"^\s*ref_(\S+) \|", listing, re.M):
            e = next((x for x in entries if str(x.get("mmid")) == m.group(1)), None)
            if e:
                add += len(e.get("constraints") or "") + len(e.get("options") or "")
        return {
            "name": name,
            "chars": len(listing),
            "added": add,
            "pct": 100.0 * add / max(1, len(listing)),
            "folds": len(FOLD_RE.findall(listing)),
            "folds_notype": len(FOLD_RE.findall(listing_b)),
            "chars_notype": len(listing_b),
        }
    except Exception:
        return None
    finally:
        await ctx.close()


def sites():
    src = (ROOT / "tools" / "capture_listings.py").read_text(encoding="utf-8")
    body = src[src.index("SITES = ["):src.index("\nOUT = ")]
    return re.findall(r'\(\s*"([a-z_0-9]+)"\s*,\s*"(https?://[^"]+)"', body)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    args = ap.parse_args()
    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for name, url in sites()[: args.n]:
            r = await one(browser, name, url)
            if r:
                rows.append(r)
                print(f"  {r['name']:22} {r['chars']:7} chars  +{r['added']:5} "
                      f"({r['pct']:5.2f}%)  folds {r['folds_notype']}->{r['folds']}  "
                      f"B:{r['chars_notype']:7}")
        await browser.close()

    if not rows:
        print("no sites replayed -- rebuild temp/frozen with tools/freeze_corpus.py")
        return 1
    pct = [r["pct"] for r in rows]
    fold_delta = sum(r["folds"] - r["folds_notype"] for r in rows)
    b_tot = sum(r["chars_notype"] for r in rows)
    a_tot = sum(r["chars"] for r in rows)
    print(f"\n  sites                     {len(rows)}")
    print(f"  A. constraints/options    median {statistics.median(pct):.2f}%  "
          f"mean {statistics.mean(pct):.2f}%  worst {max(pct):.2f}% ({max(rows, key=lambda r: r['pct'])['name']})")
    print(f"  B. type in fold key       fold groups {fold_delta:+d} over {len(rows)} sites; "
          f"listing chars {b_tot} -> {a_tot} ({100.0*(a_tot-b_tot)/max(1,b_tot):+.2f}%)")
    (ROOT / "temp" / "adopted_cost.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
