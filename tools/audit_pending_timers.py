# -*- coding: utf-8 -*-
"""Would a PENDING-TIMER signal catch the late paint, or fire on every page?

THE GAP IT IS AIMED AT. The adversarial readiness audit left one unscoped
false-quiet that nothing reaches: a page that goes silent -- no network, no
mutations -- and then paints again from a `setTimeout` that was already
scheduled. Mutation recency correctly reports quiet, because nothing HAS moved;
the page simply has work booked. `listener_tag.js` already wraps
`addEventListener` and `attachShadow` at document_start, so wrapping the timer
functions is the same technique and would make "work is booked" a FACT the page
declared rather than a guess.

THE OBJECTION, AND WHY THIS EXISTS. Most real pages poll. If a pending timer is
normal at a settled moment, the signal is the always-on warning #15 priced and
#43 deleted `readyState` for, and no amount of wording saves it. So this counts,
BEFORE anything is built:

  * how many pages have >=1 timer pending and due soon once they have settled
  * the distribution, so "a couple" and "forty" are distinguishable
  * and the CONTROL that matters: does it fire on a page that is genuinely
    still painting from a timer? A signal that is quiet on both is useless, and
    one that fires on both is noise.

Our own wrapper's bookkeeping is excluded by construction -- it schedules
nothing.

Run:  python tools/audit_pending_timers.py --sites 40 --due 2000
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

# Installed at document_start, before any page script, exactly as
# listener_tag.js installs its own wraps.
WRAP = """
(() => {
  const pend = new Map();
  let seq = 0;
  const ST = window.setTimeout, SI = window.setInterval;
  const CT = window.clearTimeout, CI = window.clearInterval;
  window.setTimeout = function (fn, d, ...a) {
    const id = ST.call(window, function () {
      pend.delete(id);
      try { return typeof fn === 'function' ? fn.apply(this, a) : eval(String(fn)); }
      finally {}
    }, d, ...a);
    pend.set(id, { due: performance.now() + (Number(d) || 0), kind: 'timeout', n: ++seq });
    return id;
  };
  window.setInterval = function (fn, d, ...a) {
    const id = SI.call(window, fn, d, ...a);
    pend.set(id, { due: performance.now() + (Number(d) || 0), kind: 'interval', n: ++seq });
    return id;
  };
  window.clearTimeout = function (id) { pend.delete(id); return CT.call(window, id); };
  window.clearInterval = function (id) { pend.delete(id); return CI.call(window, id); };
  Object.defineProperty(window, '__pendT', {
    value: (withinMs) => {
      const now = performance.now();
      let soon = 0, tOnly = 0, iOnly = 0;
      for (const v of pend.values()) {
        if (v.due - now > withinMs) continue;
        soon++;
        if (v.kind === 'timeout') tOnly++; else iOnly++;
      }
      return { soon, timeouts: tOnly, intervals: iOnly, tracked: pend.size };
    },
    enumerable: false, writable: false, configurable: false,
  });
})();
"""

# THE CONTROL PAGE: silent for a beat, then paints from a timer that was
# already booked. If the signal cannot see this, it is not worth building.
LATE = """<!doctype html><meta charset=utf-8><body style='margin:0'>
<main id=m><h1>Report</h1><p>preparing…</p></main>
<script>
setTimeout(() => {
  const m = document.getElementById('m');
  for (let i = 0; i < 200; i++) {
    const d = document.createElement('div'); d.textContent = 'row ' + i; m.appendChild(d);
  }
}, 2500);
</script></body>"""

SETTLED = """<!doctype html><meta charset=utf-8><body style='margin:0'>
<main><h1>Report</h1><p>all done, nothing scheduled</p></main></body>"""


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", type=int, default=40)
    ap.add_argument("--due", type=int, default=2000,
                    help="count timers due within this many ms")
    ap.add_argument("--settle", type=float, default=4.0,
                    help="seconds to let the page settle before counting")
    a = ap.parse_args()
    from playwright.async_api import async_playwright

    rows = []
    async with async_playwright() as p:
        br = await p.chromium.launch(headless=True)

        # --- the two controls first: the signal must separate them -----------
        ctl = {}
        for name, body in (("late-paint", LATE), ("settled", SETTLED)):
            ctx = await br.new_context(viewport={"width": 1280, "height": 900})
            await ctx.add_init_script(WRAP)
            pg = await ctx.new_page()
            # about:blank + set_content, NOT a route. Two attempts at routing
            # this control timed out at goto, which reads as the control being
            # unreachable rather than as the harness being wrong, and the
            # control is the half that decides whether the signal is worth
            # building at all. set_content removes the question.
            await pg.goto("about:blank")
            await pg.set_content(body)
            await pg.wait_for_timeout(1200)        # BEFORE the late paint fires
            ctl[name] = await pg.evaluate("(d) => window.__pendT(d)", a.due)
            await ctx.close()
        print("CONTROLS (the signal must separate these two):")
        for k, v in ctl.items():
            print(f"  {k:12} {v}")
        sep = (ctl["late-paint"]["soon"] > 0 and ctl["settled"]["soon"] == 0)
        print(f"  -> {'SEPARATES' if sep else 'DOES NOT SEPARATE'} the two\n")

        for name, url, *_ in SITES[: a.sites]:
            har = FROZEN / f"{name}.har"
            if not har.exists():
                continue
            ctx = await br.new_context(viewport={"width": 1280, "height": 900},
                                       ignore_https_errors=True)
            await ctx.add_init_script(WRAP)
            try:
                await ctx.route_from_har(str(har), not_found="abort")
                pg = await ctx.new_page()
                try:
                    await pg.goto(url, wait_until="domcontentloaded", timeout=25000)
                except Exception:
                    print(f"  {name:22} SKIP goto")
                    continue
                await pg.wait_for_timeout(int(a.settle * 1000))
                r = await pg.evaluate("(d) => window.__pendT(d)", a.due)
            except Exception as e:                                # noqa: BLE001
                print(f"  {name:22} SKIP {str(e)[:40]}")
                continue
            finally:
                await ctx.close()
            r["site"] = name
            rows.append(r)
            print(f"  {name:22} soon={r['soon']:>3} (t={r['timeouts']} i={r['intervals']})"
                  f"  tracked={r['tracked']}")
        await br.close()

    if not rows:
        print("no usable sites -- is temp/frozen/ populated?")
        return 2
    n = len(rows)
    firing = [r for r in rows if r["soon"] > 0]
    dist = collections.Counter(min(r["soon"], 10) for r in rows)
    print(f"\n{n} settled site(s), counting timers due within {a.due}ms "
          f"after {a.settle}s")
    print(f"  pages with >=1 pending timer due soon: {len(firing)} = {len(firing)/n:.1%}")
    print(f"  distribution (10 = 10 or more): {dict(sorted(dist.items()))}")
    print("\n  READ IT AS: this is the share of SETTLED pages a pending-timer")
    print("  line would appear on. High means it is the always-on warning #15")
    print("  priced; low means it discriminates and is worth building.")
    (ROOT / "temp").mkdir(exist_ok=True)
    (ROOT / "temp" / "pending_timers.json").write_text(
        json.dumps({"controls": ctl, "sites": rows}, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
