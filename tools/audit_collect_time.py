"""How long does one observation cost, and did the generality work slow it down?

read_page latency is a product metric — the whole pitch is being faster than the
alternative — and the generality fixes added work to the collector (a composed
query for the page-level scans, a structural editor-host resolution pass, a
Unicode-aware label path) while removing some (an O(n) scan in the parent-child
dedup became a Map lookup).

Measures the REAL collector from two source files on the SAME loaded page,
alternating A/B/A/B so a page that gets heavier as it hydrates cannot be mistaken
for a regression, and reports the median of the paired differences.

Run:  python tools/audit_collect_time.py --before temp/dom_quality/background.prefix.js
"""

import argparse
import asyncio
import statistics
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from _extract import extract          # noqa: E402
from audit_dom_quality import load_sites  # noqa: E402

# Deliberately the heavy end of the corpus — a 4.7k-element frameset, dense docs
# pages, a huge commercial home page — plus two shadow/component-heavy apps where
# the new composed passes do the most extra work.
HEAVY = ["java_api", "mdn_select", "premierleague", "hn", "amazon", "antd",
         "youtube", "shoelace", "caniuse", "habr", "gh_issues", "coinmarketcap"]

TIMER = """(function(){ const t0 = performance.now();
  const a = _collectInteractivePage(true); const s = _collectInteractivePage(false);
  return { ms: performance.now() - t0, n: a.length, chars: s.length }; })()"""


def wrap(src_path):
    src = Path(src_path).read_text(encoding="utf-8")
    return "(function(){ " + extract("_collectInteractivePage", src) + "\n; return " + TIMER + "; })()"


async def main(before, after, reps):
    wa, wb = wrap(after), wrap(before) if before else None
    sites = {n: (u, x) for n, u, x in load_sites()}
    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1366, "height": 900})
        await ctx.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        for name in HEAVY:
            if name not in sites:
                continue
            url, extra = sites[name]
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                await page.wait_for_timeout(3000 + extra)
                await page.evaluate(wa)           # warm up: first run pays mmid injection
                aft, bef = [], []
                for _ in range(reps):
                    if wb:
                        bef.append((await page.evaluate(wb))["ms"])
                    aft.append((await page.evaluate(wa))["ms"])
                info = await page.evaluate(wa)
                rows.append((name, info["n"], statistics.median(bef) if bef else None,
                             statistics.median(aft)))
                b = f"{rows[-1][2]:7.1f}" if bef else "      -"
                d = f"{rows[-1][3] - rows[-1][2]:+7.1f}" if bef else "       "
                print(f"  {name:<16} n={info['n']:<5} before {b} ms   after {rows[-1][3]:7.1f} ms  {d}", flush=True)
            except Exception as e:
                print(f"  {name:<16} SKIP {str(e).splitlines()[0][:60]}", flush=True)
            finally:
                await page.close()
        await browser.close()

    ok = [r for r in rows if r[2] is not None]
    if ok:
        deltas = [r[3] - r[2] for r in ok]
        print(f"\n  {len(ok)} pages: median per-observation change "
              f"{statistics.median(deltas):+.1f} ms "
              f"(before median {statistics.median([r[2] for r in ok]):.1f} ms, "
              f"after {statistics.median([r[3] for r in ok]):.1f} ms)")
        worst = max(ok, key=lambda r: r[3] - r[2])
        print(f"  worst page: {worst[0]} {worst[2]:.1f} -> {worst[3]:.1f} ms")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", default="")
    ap.add_argument("--after", default=str(ROOT / "extension" / "background.js"))
    ap.add_argument("--reps", type=int, default=5)
    a = ap.parse_args()
    asyncio.run(main(a.before or None, a.after, a.reps))
