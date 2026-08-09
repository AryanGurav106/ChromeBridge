"""Measure the agent-facing listing payload across the real site corpus.

Round-25/26 compressed two things: the LEGEND (fixed ~1.9KB preamble -> flag-driven,
suppressed entirely when 0 elements) and the PER-ROW HINTS (a full sentence of
instructions on every matching row -> short tags explained once in the legend).
Both were quoted from a single fixture / single page, which is not good enough to
publish. This measures them on real pages.

Method: run the REAL `_collectInteractivePage` (extracted from background.js, same
approach as capture_listings.py) on each site, take the current listing, then build
the COUNTERFACTUAL by (a) expanding each short tag back to its pre-compression
string and (b) replacing the flag-driven legend with the old fixed block. The delta
is the saving. No second build needed, so there is no drift risk between variants.

Run:  python tools/measure_payload.py [N]      (N = number of sites, default 20)
"""

import asyncio
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")


def _extract(name: str) -> str:
    marker = f"function {name}("
    i = BG.index(marker)
    j = BG.index("{", i) + 1
    depth = 1
    while depth and j < len(BG):
        if BG[j] == "{":
            depth += 1
        elif BG[j] == "}":
            depth -= 1
        j += 1
    return BG[i:j]


COLLECT = _extract("_collectInteractivePage")
WRAP = "(function(){ " + COLLECT + "\n; return _collectInteractivePage(false); })()"

# short tag -> the string it replaced (round-26 compression)
TAG_EXPANSIONS = [
    ("(rich-text-editor)", "(rich-text editor — type into it with form_input)"),
    ("(code-editor)", "(code editor — type into it with form_input)"),
    ("(scrollable-region)", "(scrollable region — its content scrolls independently of the page)"),
    ("(canvas)", "(canvas — pixel-drawn UI; use a computer screenshot + coordinate clicks for targets inside it)"),
    ("(cross-origin-iframe)", "(cross-origin iframe — its contents are NOT in this listing; use a computer screenshot + coordinate clicks if your target is inside)"),
    ("(clipped-in-scroll-panel)", "(scrolled out of view inside an inner scrollable panel — clicking auto-scrolls it into view)"),
    ("(below-fold)", "(below-fold; modal will auto-scroll to it on action)"),
    ("(unlabeled-icon)", "(icon button — no text label; take a computer screenshot if its purpose is unclear)"),
]

OLD_LEGEND_LEN = 1921  # the fixed preamble emitted on EVERY read_page, pre-round-25

# The flag-driven legend spans from the "Visible interactive elements" line through
# the "Act on an element by its ref" line.
LEGEND_RE = re.compile(r"Visible interactive elements \(.*?\n(?:  - .*\n)*Act on an element by its ref[^\n]*\n", re.S)


def counterfactual(listing: str) -> tuple[int, int, int]:
    """Return (current_len, old_len, legend_len_now)."""
    cur = len(listing)
    grown = listing
    for short, old in TAG_EXPANSIONS:
        grown = grown.replace(short, old)
    m = LEGEND_RE.search(listing)
    legend_now = len(m.group(0)) if m else 0
    # old legend was fixed-size and always present when the page had any listing
    old = len(grown) - legend_now + (OLD_LEGEND_LEN if listing.strip() else 0)
    return cur, old, legend_now


def load_sites():
    src = (ROOT / "tools" / "capture_listings.py").read_text(encoding="utf-8")
    body = src[src.index("SITES = ["):]
    return re.findall(r'\(\s*"([a-z_0-9]+)"\s*,\s*"(https?://[^"]+)"', body)


async def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    sites = load_sites()
    step = max(1, len(sites) // n)
    sample = sites[::step][:n]
    print(f"corpus={len(sites)} sites; sampling every {step} -> {len(sample)} sites\n")

    rows, fails = [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        await ctx.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        for name, url in sample:
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                await page.wait_for_timeout(2200)
                listing = await page.evaluate(WRAP)
                cur, old, leg = counterfactual(listing)
                rows.append((name, cur, old, leg))
                print(f"  {name:<20} now {cur:>6}  was {old:>6}  saved {old-cur:>5} ({100*(old-cur)/max(old,1):4.1f}%)  legend {leg}")
            except Exception as e:
                fails.append((name, str(e).splitlines()[0][:70]))
                print(f"  {name:<20} SKIP ({str(e).splitlines()[0][:60]})")
            finally:
                await page.close()
        await browser.close()

    if rows:
        tc = sum(r[1] for r in rows)
        to = sum(r[2] for r in rows)
        print(f"\n{len(rows)} pages measured, {len(fails)} skipped")
        print(f"  total now : {tc:>8} chars (~{tc//4} tokens)")
        print(f"  total was : {to:>8} chars (~{to//4} tokens)")
        print(f"  SAVED     : {to-tc:>8} chars ({100*(to-tc)/to:.1f}%), ~{(to-tc)//4} tokens over {len(rows)} observations")
        per = [(100 * (r[2] - r[1]) / max(r[2], 1)) for r in rows]
        per.sort()
        print(f"  per-page saving: min {per[0]:.1f}%  median {per[len(per)//2]:.1f}%  max {per[-1]:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
