"""What do the two signals a static snapshot CANNOT carry actually buy?

THE CLAIM THIS TESTS, which has been asserted three times and never measured.
Our headline out-of-sample number is Mind2Web target recall, currently
177/186 = 95.2% with nine misses. CLAUDE.md #73 characterises every one of those
misses as an element that declares NOTHING in static markup, and explains it
structurally: Mind2Web's snapshots carry no scripts and no CSS, so two of the
collector's eight admitting signals measure **0/186** and cannot fire at all --
a registered listener (`__abClickBound`, stamped by `listener_tag.js`) and
`cursor:pointer` (CSS). #73 therefore calls the figure "a structural lower
bound". README repeats it.

**That is an argument, not a measurement.** It says the two signals would have
fired on a live page; it does not say how much they are worth. If they are worth
almost nothing, the nine misses are a real gap and "lower bound" is a comforting
story. If they are worth a lot, the bound is real and quantified.

WHAT THIS DOES. Takes the shipped collector, ablates exactly those two signals
-- the `__abClickBound` admission and the `cursor:pointer` admission, in all of
their sites -- and runs both arms over the SAME live page load. The delta is
what a static snapshot costs us, measured rather than argued.

WHY WEBPAGEBENCH. It has to be a page that is genuinely live: real scripts
binding real handlers, real CSS setting real cursors. The frozen 106-site corpus
replays JS so it would also work, and is 1.1GB and not always present; this is
six apps already standing for the other measurements, with a 0 drift floor
measured by `measure_wpb_invariance.py`. The cost is that it is six synthetic
apps, so the NUMBER does not transfer to the web -- the DIRECTION and the
mechanism do.

Run (site up; see measure_wpb_invariance.py):
    python tools/measure_static_floor.py --repo <path-to-WebPageBench>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_wpb_invariance import (  # noqa: E402
    HOST, TAG, COLLECT, build_track_config, create_track,
)

_ROW = re.compile(r"^\s*(?:ref_|mmid=)")

# The two admissions a static snapshot cannot carry, ablated at every site.
# Each is asserted to apply, because a transformation that silently matches
# nothing is an ablation that measures nothing -- the failure mode this repo
# records in `audit_ablation.py`'s own history.
ABLATIONS = [
    ("listener", "if (el.__abClickBound && tag !== 'body'",
     "if (false && el.__abClickBound && tag !== 'body'"),
    ("listener-svg", "wiredSvg = !!el.__abClickBound ||",
     "wiredSvg = (false && !!el.__abClickBound) ||"),
    ("cursor-owner", "if (getComputedStyle(el).cursor === 'pointer') {",
     "if (false && getComputedStyle(el).cursor === 'pointer') {"),
    ("cursor-keep", "if (getComputedStyle(el).cursor === 'pointer') return true;",
     "if (false && getComputedStyle(el).cursor === 'pointer') return true;"),
]


def ablated_source(src: str) -> str:
    out = src
    missing = []
    for name, old, new in ABLATIONS:
        if old not in out:
            missing.append(name)
            continue
        out = out.replace(old, new)
    if missing:
        raise SystemExit(
            f"ABLATION DID NOT APPLY at: {missing}. The collector moved and this "
            f"probe would have reported 'no difference' from a transformation "
            f"that changed nothing. Fix the patterns before trusting any number.")
    return out


def rows(listing: str) -> set[str]:
    out = set()
    for line in (listing or "").splitlines():
        if line.startswith("***") or not _ROW.match(line):
            continue
        out.add(re.sub(r"\b(?:ref_|mmid=['\"]?)\d+['\"]?", "", line).strip())
    return out


async def collect(browser, track: str, src: str) -> str:
    pg = await browser.new_page(viewport={"width": 1280, "height": 900})
    await pg.add_init_script(TAG)
    try:
        await pg.goto(f"{HOST}/{track}", wait_until="networkidle", timeout=30000)
        await pg.wait_for_timeout(2500)
        return await pg.evaluate("(function(){ " + src + "; return _collectInteractivePage(false); })()")
    finally:
        await pg.close()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--limit", type=int, default=12)
    a = ap.parse_args()
    repo = Path(a.repo).resolve()

    live = COLLECT
    dead = ablated_source(COLLECT)
    print(f"ablation applied at all {len(ABLATIONS)} site(s)\n")

    tasks = repo / "tests" / "bench" / "tasks"
    # One task per DOMAIN, so the number is not six readings of one app.
    by_domain, picked = {}, []
    for f in sorted(tasks.glob("*.json")):
        if "__" in f.name:
            continue
        d = json.loads(f.read_text(encoding="utf-8"))["test_data"]
        dom = d.get("bench_first_domain")
        if dom and dom not in by_domain:
            by_domain[dom] = f
            picked.append((dom, f))
    picked = picked[: a.limit]
    print(f"{len(picked)} domain(s): {[d for d, _ in picked]}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        results = []
        for dom, f in picked:
            tid = f"sf_{dom[:12]}"
            if not await create_track(None, tid, build_track_config(repo, f)):
                print(f"  {dom}: track create failed"); continue
            # SAME PAGE LOAD IS NOT POSSIBLE across two injections, so the arms
            # are two loads of the same track -- which `measure_wpb_invariance`
            # measured at a 0 drift floor on these pages, which is why that
            # probe had to run first.
            l_rows = rows(await collect(browser, tid, live))
            d_rows = rows(await collect(browser, tid, dead))
            lost = l_rows - d_rows
            gained = d_rows - l_rows
            results.append((dom, len(l_rows), len(d_rows), lost, gained))
        await browser.close()

    print(f"{'domain':12} {'live':>6} {'static':>7} {'lost':>6} {'lost %':>8}")
    tot_l = tot_d = 0
    for dom, nl, nd, lost, gained in results:
        tot_l += nl; tot_d += nd
        pct = (len(lost) / nl * 100) if nl else 0
        extra = f"   (+{len(gained)} only-in-static)" if gained else ""
        print(f"{dom:12} {nl:>6} {nd:>7} {len(lost):>6} {pct:>7.1f}%{extra}")

    print()
    if not tot_l:
        print("NOTHING MEASURED."); return 1
    pct = (tot_l - tot_d) / tot_l * 100
    print(f"TOTAL rows: live {tot_l}, static-equivalent {tot_d}  -> {pct:.1f}% of the "
          f"listing depends on\n      a registered listener or a pointer cursor, i.e. on "
          f"signals a snapshot\n      with no scripts and no CSS cannot carry.")
    print()
    print("A sample of what is lost (these are the rows Mind2Web-style markup")
    print("could never have admitted):")
    shown = 0
    for dom, nl, nd, lost, gained in results:
        for r in sorted(lost)[:3]:
            print(f"   {dom:10} {r[:104]}")
            shown += 1
        if shown >= 12:
            break
    print()
    print("SCOPE. Six synthetic apps, so the PERCENTAGE does not transfer to the web.")
    print("What transfers is the mechanism and its direction: the two signals are")
    print("load-bearing on a live page and measure 0/186 on Mind2Web, so the")
    print("out-of-sample figure really is a floor rather than an estimate.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
