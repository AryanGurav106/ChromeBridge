# -*- coding: utf-8 -*-
"""How often would the observe-to-act guard REFUSE on a page where nothing is wrong?

THE DECISION THIS SETTLES. #84 shipped the guard as a NOTE and deliberately held
the REFUSAL half, because the only number available for the population a refusal
would gate -- controls the DOCUMENT declares as submits -- was 0 diffs out of 10,
which the rule of three bounds at roughly 30%. A refusal shipped on an unbounded
false-refusal rate turns a live counter into a dead tool, so the honest move was
to measure rather than to be brave or cautious.

WHAT IT MEASURES. On a SETTLED frozen page: collect, stamp every entry's
signature, wait a MODEL TURN (#38 measured ~3.6s), re-stamp, and count the
controls whose signature moved. Reported for every control and separately for
DECLARED SUBMITS -- `input[type=submit|image]`, `button[type=submit]`, or a
`<button>` with no `type` inside a real `<form>`, which is the same declaration
#24's submit picker reads and the same one the refusal would gate on.

THE SIGNATURE IS SLICED OUT OF background.js, not reimplemented. Two copies live
there (`dup:obssig`, pinned byte-identical by OB8); a third spelling in a probe
would measure a different question from the one the product asks, which is
PRINCIPLE 17 and the exact failure #83 found between two placeholder tests.

A frozen HAR serves no live data, so this bounds the STATIC rate: a page whose
server pushes a counter cannot show it here. That is stated rather than hidden,
and it is why the figure is a floor for the note and a ceiling for nothing.

Run:  python tools/audit_stale_refusal.py --sites 30 --wait 3.6
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from _extract import extract as _x                               # noqa: E402
from capture_listings import SITES                               # noqa: E402

BG = (ROOT / "extension" / "background.js").read_text("utf-8")
COLLECT = _x("_collectInteractivePage", BG, verify=True)
FROZEN = ROOT / "temp" / "frozen"
TAG = str(ROOT / "extension" / "listener_tag.js")


def _sig_src() -> str:
    i = BG.index("const _obsSig = (el) => {")
    j = BG.index("\n  };", i) + len("\n  };")
    return BG[i:j]


SIG = _sig_src()

# Stamp every entry, and say which of them the DOCUMENT declares a submit.
STAMP = """(function(){
  %s;
  %s
  const out = {};
  // ORDER IS LOAD-BEARING: the collector REPLACES window.__mmidReg on every run,
  // so reading it first held a stale (here undefined) map and every lookup
  // returned undefined -- 0 stamped controls on a page with 252 entries, and the
  // probe reported "no usable sites", which reads exactly like an empty corpus.
  const ents = _collectInteractivePage(true, null, 'compact', false, false, 'tree') || [];
  const reg = window.__mmidReg;
  for (const e of ents) {
    let n = null;
    try { n = reg && reg.get(String(e.mmid)); } catch (x) {}
    if (!n || !n.isConnected) continue;
    let submit = false;
    try {
      const tag = (n.tagName || '').toLowerCase();
      const ty = (n.getAttribute('type') || '').toLowerCase();
      // THE DECLARATION, not a label. Same rule #24's submit picker reads.
      submit = (tag === 'input' && (ty === 'submit' || ty === 'image'))
            || (tag === 'button' && ty === 'submit')
            || (tag === 'button' && !ty && !!n.closest('form'));
    } catch (x) {}
    out[String(e.mmid)] = { sig: _obsSig(n), submit: submit };
  }
  return out;
})()""" % (COLLECT, SIG)

FIELDS = ("tag", "role", "name", "dis", "href", "rec")


async def one(browser, name, url, wait_s):
    from playwright.async_api import Error as PWError            # noqa: F401
    har = FROZEN / f"{name}.har"
    if not har.exists():
        return {"skip": "no har"}
    ctx = await browser.new_context(viewport={"width": 1280, "height": 900},
                                    ignore_https_errors=True)
    await ctx.add_init_script(path=TAG)
    try:
        await ctx.route_from_har(str(har), not_found="abort")
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:                                    # noqa: BLE001
            return {"skip": f"goto: {str(e)[:70]}"}
        await page.wait_for_timeout(1500)          # let it settle BEFORE the window
        a = await page.evaluate(STAMP) or {}
        if len(a) < 5:
            return {"skip": f"only {len(a)} stamped control(s)"}
        await page.wait_for_timeout(int(wait_s * 1000))
        b = await page.evaluate(STAMP) or {}
    finally:
        await ctx.close()

    both = [m for m in a if m in b]
    diffs, sub_n, sub_diff, which = 0, 0, 0, {}
    for m in both:
        moved = [f for f in FIELDS if a[m]["sig"].get(f) != b[m]["sig"].get(f)]
        if a[m]["submit"]:
            sub_n += 1
            if moved:
                sub_diff += 1
        if moved:
            diffs += 1
            for f in moved:
                which[f] = which.get(f, 0) + 1
    return {"site": name, "n": len(both), "diffs": diffs, "fields": which,
            "submits": sub_n, "submit_diffs": sub_diff,
            "gone": len([m for m in a if m not in b])}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", type=int, default=30)
    ap.add_argument("--wait", type=float, default=3.6,
                    help="the model turn to sit out; #38 measured ~3.6s")
    a = ap.parse_args()
    from playwright.async_api import async_playwright

    rows = []
    async with async_playwright() as p:
        br = await p.chromium.launch(headless=True)
        for name, url, *_ in SITES[: a.sites]:
            try:
                r = await one(br, name, url, a.wait)
            except Exception as e:                                # noqa: BLE001
                print(f"  {name:22} ERROR {str(e)[:60]}")
                continue
            if not r:
                continue
            if r.get("skip"):
                print(f"  {name:22} SKIP {r['skip']}")
                continue
            rows.append(r)
            print(f"  {r['site']:22} n={r['n']:>4} moved={r['diffs']:>3} "
                  f"submits={r['submits']:>3} moved={r['submit_diffs']:>2} "
                  f"{r['fields'] or ''}")
        await br.close()

    if not rows:
        print("no usable sites -- is temp/frozen/ populated?")
        return 2
    N = sum(r["n"] for r in rows)
    D = sum(r["diffs"] for r in rows)
    S = sum(r["submits"] for r in rows)
    SD = sum(r["submit_diffs"] for r in rows)
    agg: dict = {}
    for r in rows:
        for k, v in r["fields"].items():
            agg[k] = agg.get(k, 0) + v
    print(f"\n{len(rows)} site(s), {a.wait}s window (one model turn, #38)")
    print(f"  ALL controls      {N:>6}   moved {D:>4}  = {D/max(N,1):.3%}")
    print(f"  DECLARED SUBMITS  {S:>6}   moved {SD:>4}  = {SD/max(S,1):.3%}"
          + ("   <-- the population a REFUSAL would gate" if S else ""))
    print(f"  fields that moved: {agg or 'none'}")
    # The rule of three: with 0 of n, the upper 95% bound is about 3/n. Printed
    # because "0%" from a small n is the number that misleads (#84 held the
    # refusal on exactly this).
    if S and SD == 0:
        print(f"  0 of {S}: rule-of-three upper bound ~{3/S:.2%}")
    med = statistics.median([r["diffs"] / max(r["n"], 1) for r in rows])
    print(f"  per-site median rate {med:.3%}")
    print("\n  CAVEAT: a frozen HAR serves no live data, so a server-pushed")
    print("  counter cannot show here. This bounds the STATIC rate only.")
    (ROOT / "temp").mkdir(exist_ok=True)
    (ROOT / "temp" / "stale_refusal.json").write_text(
        json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
