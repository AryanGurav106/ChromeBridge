# -*- coding: utf-8 -*-
"""How often is a page's readiness ACTUALLY unobservable because of a frame?

THE DECISION THIS SETTLES. The readiness probe reads mutation recency, images,
`aria-busy` and `role=progressbar` from the top document and from SAME-ORIGIN
frames. A CROSS-ORIGIN frame is opaque to all of it, so a page whose content
paints inside one reports QUIET while it is still building -- the readiness
audit measured exactly that on one of its 18 shapes, at two offsets.

The obvious answer is a line saying "N cross-origin frame(s) present, which this
cannot observe". The obvious objection is that it would then appear on every
page carrying an ad or an embedded video, which is the always-on warning #15
priced and #43 deleted `readyState` for. Neither side of that is worth arguing
without a number, so this counts.

WHAT COUNTS AS A FRAME THAT MATTERS, and every clause is there to avoid
reporting one that does not:
  * RENDERED -- `checkVisibility` with opacity and visibility, the same call
    #36 records a bare version getting wrong by 3.81%.
  * CROSS-ORIGIN -- `contentDocument` genuinely throws. Not inferred from the
    src attribute, which is wrong for `about:blank`, `srcdoc` and same-site
    subdomains.
  * BIG ENOUGH TO HOLD CONTENT -- the 30px bound `_frameShellsPage` already
    uses, reused rather than re-chosen so the two passes agree (#30 found these
    two disagreeing once already).

Reports the share of pages with >=1 such frame and the distribution, so the
question "would this note discriminate or fire always" has an answer.

Run:  python tools/audit_xorigin_frames.py --sites 60
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from capture_listings import SITES                               # noqa: E402

FROZEN = ROOT / "temp" / "frozen"
TAG = str(ROOT / "extension" / "listener_tag.js")

COUNT = """(function(){
  const out = { total: 0, rendered: 0, xorigin: 0, big: 0, hosts: [] };
  const fr = Array.from(document.querySelectorAll('iframe,frame'));
  out.total = fr.length;
  for (const f of fr) {
    let vis = false;
    try {
      vis = f.checkVisibility
          ? f.checkVisibility({opacityProperty: true, visibilityProperty: true})
          : true;
    } catch (e) { vis = true; }
    if (!vis) continue;
    out.rendered++;
    let opaque = false;
    try { const d = f.contentDocument; opaque = !d; } catch (e) { opaque = true; }
    if (!opaque) continue;
    out.xorigin++;
    let r = null;
    try { r = f.getBoundingClientRect(); } catch (e) {}
    // The SAME 30px bound _frameShellsPage uses, so the two passes agree about
    // which frames are worth naming.
    if (r && r.width >= 30 && r.height >= 30) {
      out.big++;
      try {
        const u = new URL(f.src || '', location.href);
        if (out.hosts.indexOf(u.host) < 0) out.hosts.push(u.host);
      } catch (e) {}
    }
  }
  return out;
})()"""


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", type=int, default=60)
    a = ap.parse_args()
    from playwright.async_api import async_playwright

    rows, hosts = [], collections.Counter()
    async with async_playwright() as p:
        br = await p.chromium.launch(headless=True)
        for name, url, *_ in SITES[: a.sites]:
            har = FROZEN / f"{name}.har"
            if not har.exists():
                print(f"  {name:22} SKIP no har")
                continue
            ctx = await br.new_context(viewport={"width": 1280, "height": 900},
                                       ignore_https_errors=True)
            await ctx.add_init_script(path=TAG)
            try:
                await ctx.route_from_har(str(har), not_found="abort")
                pg = await ctx.new_page()
                try:
                    await pg.goto(url, wait_until="domcontentloaded", timeout=25000)
                except Exception as e:                            # noqa: BLE001
                    print(f"  {name:22} SKIP goto {str(e)[:40]}")
                    continue
                await pg.wait_for_timeout(1800)
                r = await pg.evaluate(COUNT)
            except Exception as e:                                # noqa: BLE001
                print(f"  {name:22} SKIP {str(e)[:50]}")
                continue
            finally:
                await ctx.close()
            r["site"] = name
            rows.append(r)
            for h in r["hosts"]:
                hosts[h] += 1
            if r["big"]:
                print(f"  {name:22} frames={r['total']:>2} rendered={r['rendered']:>2} "
                      f"x-origin>=30px={r['big']:>2}  {r['hosts'][:3]}")
        await br.close()

    if not rows:
        print("no usable sites -- is temp/frozen/ populated?")
        return 2
    n = len(rows)
    withbig = [r for r in rows if r["big"]]
    print(f"\n{n} site(s)")
    print(f"  pages with >=1 RENDERED CROSS-ORIGIN frame >=30px: "
          f"{len(withbig)} = {len(withbig)/n:.1%}")
    print(f"  pages with any iframe at all:                      "
          f"{sum(1 for r in rows if r['total'])} = "
          f"{sum(1 for r in rows if r['total'])/n:.1%}")
    dist = collections.Counter(r["big"] for r in rows)
    print(f"  distribution of that count: {dict(sorted(dist.items()))}")
    print(f"  commonest embed hosts: {dict(hosts.most_common(6))}")
    print("\n  READ IT AS: this is the share of pages a 'cross-origin frames are")
    print("  unobservable' line would appear on. High means the note is the")
    print("  always-on warning #15 priced; low means it discriminates.")
    (ROOT / "temp").mkdir(exist_ok=True)
    (ROOT / "temp" / "xorigin_frames.json").write_text(
        json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
