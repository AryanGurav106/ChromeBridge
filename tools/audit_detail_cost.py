"""What does detail="full" cost, and did adding it make the DEFAULT more expensive?

Two separate questions, and the second one matters more. `full` is opt-in, so its
size is a choice the agent makes; the escape-hatch legend line is paid by EVERY
observation on every page, forever, and that is the number that needs watching.

Measures on each corpus page, against the same loaded DOM so nothing drifts:
  compact           the default listing
  compact-minus     the same listing with the escape-hatch line removed
                    -> the standing tax of making the omission discoverable
  full (page)       whole-page full detail — the expensive, rarely-correct call
  full (scoped)     full detail on the largest plausible content region
                    -> the intended usage, and the number the design rests on

Run:  python tools/audit_detail_cost.py [-n N] [-c CONCURRENCY]
"""

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from _extract import extract            # noqa: E402
from audit_dom_quality import load_sites  # noqa: E402

OUT = ROOT / "temp" / "dom_quality"

PROBE = r"""
(function () {
  const compact = _collectInteractivePage(false, null, 'compact');
  const full    = _collectInteractivePage(false, null, 'full');
  // Largest sane content region to scope to — what an agent would pick after a
  // compact read tells it roughly where its target lives.
  let scope = null;
  try {
    const c = document.querySelector('main, [role="main"], #content, #main, article');
    scope = c && c.getAttribute('mmid');
  } catch (e) {}
  const scoped = scope ? _collectInteractivePage(false, scope, 'full') : '';
  const hatch = (compact.match(/^  - .*are NOT listed\..*$/m) || [''])[0];
  return {
    compact: compact.length,
    hatch: hatch.length ? hatch.length + 1 : 0,
    full: full.length,
    scoped: scoped.length,
    hasScope: !!scope,
    entries: _collectInteractivePage(true, null, 'compact').length,
    mediaRows: (full.match(/\(media — not a control\)/g) || []).length,
  };
})()
"""


async def one(ctx, name, url, extra, wrap):
    page = await ctx.new_page()
    rec = {"name": name}
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        await page.wait_for_timeout(2000 + extra)
        rec.update(await page.evaluate(wrap))
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:70]}"
    finally:
        try:
            await page.close()
        except Exception:
            pass
    return rec


async def main(limit, concurrency):
    src = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
    wrap = ("(function(){ " + extract("_collectInteractivePage", src, verify=True)
            + "\n; return (" + PROBE.strip() + "); })()")
    sites = load_sites()
    if limit:
        sites = sites[:limit]
    print(f"{len(sites)} sites\n", flush=True)

    sem = asyncio.Semaphore(concurrency)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1366, "height": 900})
        await ctx.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))

        async def guarded(s):
            async with sem:
                r = await one(ctx, s[0], s[1], s[2], wrap)
                if "error" in r:
                    print(f"  {r['name']:<18} SKIP {r['error'][:50]}", flush=True)
                else:
                    sc = f"{r['scoped']:>6}" if r["hasScope"] else "     -"
                    print(f"  {r['name']:<18} compact {r['compact']:>6}  hatch {r['hatch']:>3}  "
                          f"full {r['full']:>6} (x{r['full']/max(r['compact'],1):.2f})  scoped {sc}  "
                          f"media {r['mediaRows']}", flush=True)
                return r

        rows = await asyncio.gather(*[guarded(s) for s in sites])
        await browser.close()

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "detail_cost.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")

    ok = [r for r in rows if "error" not in r]
    if not ok:
        return
    comp = [r["compact"] for r in ok]
    hatch = [r["hatch"] for r in ok]
    ratio = [r["full"] / max(r["compact"], 1) for r in ok]
    scoped = [r for r in ok if r["hasScope"] and r["scoped"]]
    print(f"\n=== {len(ok)} pages ===")
    print(f"  compact listing        median {statistics.median(comp):.0f} chars")
    print(f"  escape-hatch line      median {statistics.median(hatch):.0f} chars "
          f"= {100*statistics.median(hatch)/statistics.median(comp):.1f}% of a compact read "
          f"(absent on {sum(1 for h in hatch if h == 0)} pages with nothing to reveal)")
    print(f"  full / compact         median x{statistics.median(ratio):.2f}   "
          f"p90 x{sorted(ratio)[int(.9*len(ratio))]:.2f}   max x{max(ratio):.2f}")
    if scoped:
        sr = [r["scoped"] / max(r["full"], 1) for r in scoped]
        print(f"  scoped full / full     median {100*statistics.median(sr):.0f}%  "
              f"(on {len(scoped)} pages with a main-content region)")
    print(f"  pages surfacing media   {sum(1 for r in ok if r['mediaRows'])}"
          f"  (median {statistics.median([r['mediaRows'] for r in ok if r['mediaRows']] or [0]):.0f} images per page)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--limit", type=int, default=0)
    ap.add_argument("-c", "--concurrency", type=int, default=5)
    a = ap.parse_args()
    asyncio.run(main(a.limit, a.concurrency))
