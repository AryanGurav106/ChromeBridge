"""Threshold sensitivity — are the MAGIC NUMBERS general, or tuned to our corpus?

WHAT THIS TESTS THAT NOTHING ELSE DOES
--------------------------------------
`audit_ablation.py` neuters SIGNATURES (does the CodeMirror class list carry
weight it shouldn't?). It proved nine library signatures were load-bearing and
forced them to be rewritten structurally. It never touched the NUMBERS.

Every threshold in the collector was chosen by hand while looking at a specific
page: `< 8px` is decoration, canvas needs `0.25 x viewport`, the listing caps at
150, a delegation root has `>= 8` children — and, added in one day, folding needs
`>= 6` members with 40x20px shape buckets, deltas need 25%/60% survival, and
readiness counts images within 200px of the viewport.

A hand-picked number is only site-specific if the behaviour is SENSITIVE to it:

    PLATEAU — output barely moves as the value changes. The number is a rough
              guard and any nearby value works. Generalises.
    CLIFF   — output jumps at or near the shipped value. The value was fitted to
              the pages we happened to look at, and a site on the other side of
              the cliff gets different behaviour for no principled reason.

So this sweeps each threshold and reports the SHAPE of the response, measured two
ways that can disagree:
  - dev corpus (frozen, 106 sites): listing size and answerability
  - out-of-sample (Mind2Web labelled targets): does recall move?

A threshold that is flat on the dev corpus but moves out-of-sample recall is
exactly the failure this exists to catch.

METHOD
------
Source substitution on the extracted collector, same mechanism as
audit_ablation.py, so the REAL function runs — no reimplementation to drift from.
Frozen HAR replay removes the drift control that live pages forced on the earlier
audit, so a difference here is the change, not the weather.

Run:
    python tools/audit_thresholds.py                 # dev corpus, all thresholds
    python tools/audit_thresholds.py --sites 12
    python tools/audit_thresholds.py --only fold-min-members
    python tools/audit_thresholds.py --oos           # add Mind2Web recall (slower)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "temp" / "frozen"
M2W = ROOT / "temp" / "mind2web"
OUT = ROOT / "temp" / "thresholds"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
BASE = extract("_collectInteractivePage", BG, verify=True)
# Some thresholds live in sibling page functions, not the collector. Patching the
# wrong source matched zero times and was correctly SKIPPED rather than silently
# reporting a plateau — but the sweeps still need to run, so each names its host.
FUNCS = {
    "_collectInteractivePage": BASE,
    "_domTextPage": extract("_domTextPage", BG, verify=True),
    "_readinessPage": extract("_readinessPage", BG, verify=True),
}
TAG_JS = str(ROOT / "extension" / "listener_tag.js")
VIEWPORT = {"width": 1280, "height": 1600}

# (name, needle, [values...], shipped_value)
# The needle must appear EXACTLY ONCE in the collector — asserted at build time,
# because a silently-unmatched substitution would report a perfect plateau for a
# sweep that never actually changed anything.
SWEEPS = [
    ("decoration-min-px",
     "r.width > 1 && r.height > 1", ["r.width > {} && r.height > {}"],
     [0, 1, 2, 4], 1),
    ("listing-cap",
     "const LISTING_CAP = 150;", ["const LISTING_CAP = {};"],
     [60, 100, 150, 250, 400], 150),
    ("fold-min-members",
     "if (members.length < 6 || window.__abNoFold) continue;",
     ["if (members.length < {} || window.__abNoFold) continue;"],
     [3, 4, 6, 10, 20], 6),
    ("fold-shape-bucket-w",
     "Math.round((e.w || 0) / 40)", ["Math.round((e.w || 0) / {})"],
     [10, 20, 40, 80, 100000], 40),

]


def build_variants(only: str | None) -> dict[str, str]:
    """name -> collector source. Fails loudly if a needle does not match once."""
    # The SAME source, twice. Any difference between these two is pure measurement
    # noise (frozen replay is 88/106 byte-stable, and the unstable sites move).
    # Without this control the first run reported a 12% "CLIFF" that sat barely
    # above a 4.5% noise floor nobody had measured.
    variants = {"__shipped__": BASE, "__control__": BASE}
    for name, needle, tmpls, values, shipped in SWEEPS:
        if only and only != name:
            continue
        n = BASE.count(needle)
        if n != 1:
            print(f"  !! {name}: needle matched {n} times — SKIPPED (fix the needle, "
                  f"a silent miss would look like a perfect plateau)")
            continue
        for v in values:
            repl = tmpls[0].replace("{}", str(v))
            variants[f"{name}={v}"] = BASE.replace(needle, repl)
    return variants


def load_sites(limit: int) -> list[tuple[str, str]]:
    src = (ROOT / "tools" / "capture_listings.py").read_text(encoding="utf-8")
    body = src[src.index("SITES = ["):src.index("\nOUT = ")]
    sites = re.findall(r'\(\s*"([a-z_0-9]+)"\s*,\s*"(https?://[^"]+)"', body)
    return [s for s in sites if (FROZEN / f"{s[0]}.har").exists()][:limit]


async def measure_dev(browser, collector: str, sites) -> dict:
    chars, entries = 0, 0
    for name, url in sites:
        ctx = await browser.new_context(viewport=VIEWPORT)
        try:
            await ctx.add_init_script(path=TAG_JS)
            await ctx.route_from_har(str(FROZEN / f"{name}.har"), not_found="abort")
            page = await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(600)
            li = await page.evaluate(
                "(function(){ " + collector + "; return _collectInteractivePage(false, null, 'brief'); })()")
            st = await page.evaluate(
                "(function(){ " + collector + "; return _collectInteractivePage(true, null, 'brief'); })()")
            chars += len(li or "")
            entries += len(st or [])
        except Exception:
            pass
        finally:
            await ctx.close()
    return {"chars": chars, "entries": entries}


M2W_PROBE = r"""(bn)=>{const el=document.querySelector(`[backend_node_id="${String(bn).replace(/"/g,'')}"]`);
if(!el)return null;const a=[];for(let n=el.parentElement;n;n=n.parentElement){const m=n.getAttribute&&n.getAttribute('mmid');if(m)a.push(m);}
const d=el.querySelector&&el.querySelector('[mmid]');
return {own:el.getAttribute('mmid'),ancs:a,desc:d?d.getAttribute('mmid'):null};}"""


def load_m2w(limit: int) -> list[dict]:
    rows = []
    for f in sorted(M2W.glob("samples_shard*.jsonl")):
        for line in f.open(encoding="utf-8"):
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    from collections import defaultdict
    by = defaultdict(list)
    for r in rows:
        by[r["website"]].append(r)
    out = []
    i = 0
    while len(out) < limit:
        added = False
        for site in sorted(by):
            if i < len(by[site]):
                out.append(by[site][i])
                added = True
                if len(out) >= limit:
                    break
        if not added:
            break
        i += 1
    return out


async def measure_oos(browser, collector: str, samples) -> dict:
    ctx = await browser.new_context(viewport=VIEWPORT)
    hit = seen = 0
    try:
        await ctx.add_init_script(path=TAG_JS)
        page = await ctx.new_page()
        for s in samples:
            try:
                await page.set_content(s["html"], wait_until="domcontentloaded")
                await page.wait_for_timeout(70)
                st = await page.evaluate(
                    "(function(){ " + collector + "; return _collectInteractivePage(true, null, 'brief'); })()")
                pr = await page.evaluate(M2W_PROBE, s["target_backend_node_id"])
                if not pr:
                    continue
                seen += 1
                kept = {str(e.get("mmid")) for e in st}
                if pr["own"] in kept or any(a in kept for a in pr["ancs"]) or pr["desc"] in kept:
                    hit += 1
            except Exception:
                pass
    finally:
        await ctx.close()
    return {"recall": hit / seen if seen else 0.0, "n": seen}


def verdict(values: list[float], noise: float = 0.0) -> str:
    """Plateau vs cliff, judged AGAINST THE NOISE FLOOR.

    A step smaller than the gap between two identical runs is not a finding. The
    first run of this tool reported a 12% "CLIFF" on a 4.5% noise floor, which is
    barely two noise widths and non-monotonic besides — i.e. weather.
    """
    if len(values) < 2 or not any(values):
        return "?"
    base = statistics.fmean(v for v in values if v) or 1.0
    steps = [abs(values[i + 1] - values[i]) / base for i in range(len(values) - 1)]
    worst = max(steps)
    floor = max(0.02, noise * 1.5)
    if worst < floor:
        return f"PLATEAU  (max step {worst:.1%} < noise floor {floor:.1%} — generalises)"
    if worst < floor * 2.5:
        return f"gentle slope  (max step {worst:.1%} vs noise {floor:.1%})"
    return f"CLIFF  ({worst:.0%} step, noise floor {floor:.1%})"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", type=int, default=14)
    ap.add_argument("--only", default="")
    ap.add_argument("--oos", action="store_true", help="also measure Mind2Web recall")
    ap.add_argument("--oos-n", type=int, default=24)
    args = ap.parse_args()

    sites = load_sites(args.sites)
    variants = build_variants(args.only or None)
    samples = load_m2w(args.oos_n) if args.oos else []
    OUT.mkdir(parents=True, exist_ok=True)

    print(f"{len(sites)} frozen sites x {len(variants)} variants"
          + (f", {len(samples)} out-of-sample actions" if samples else ""))
    t0 = time.time()
    results: dict[str, dict] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for i, (vname, src) in enumerate(variants.items(), 1):
            r = await measure_dev(browser, src, sites)
            if samples:
                r.update(await measure_oos(browser, src, samples))
            results[vname] = r
            extra = f"  recall {r['recall']:.1%}" if "recall" in r else ""
            print(f"  [{i:>2}/{len(variants)}] {vname:<26} {r['chars']:>8} chars  "
                  f"{r['entries']:>6} entries{extra}", flush=True)
        await browser.close()

    print(f"\n{'='*74}\nSENSITIVITY — does the shipped value sit on a plateau or a cliff?\n{'='*74}")
    ship = results.get("__shipped__", {})
    ctrl = results.get("__control__", {})
    noise = 0.0
    if ship.get("chars") and ctrl.get("chars"):
        noise = abs(ctrl["chars"] - ship["chars"]) / ship["chars"]
    print("")
    print(f"NOISE FLOOR (two runs of the SAME source): {noise:.1%} — any step "
          f"smaller than this is measurement, not behaviour.")
    for name, needle, _t, values, shipped in SWEEPS:
        if args.only and args.only != name:
            continue
        row = [(v, results.get(f"{name}={v}")) for v in values]
        row = [(v, r) for v, r in row if r]
        if len(row) < 2:
            continue
        chars = [r["chars"] for _v, r in row]
        print(f"\n{name}   (shipped: {shipped})")
        for v, r in row:
            mark = "  <== shipped" if v == shipped else ""
            d = (r["chars"] / ship["chars"] - 1) if ship.get("chars") else 0
            rec = f"   recall {r['recall']:.1%}" if "recall" in r else ""
            print(f"   {str(v):>8}: {r['chars']:>8} chars ({d:+6.1%})  "
                  f"{r['entries']:>6} entries{rec}{mark}")
        print(f"   tokens  -> {verdict(chars, noise)}")
        if "recall" in row[0][1]:
            print(f"   recall  -> {verdict([r['recall'] for _v, r in row], noise)}")

    (OUT / "latest.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n{round(time.time()-t0)}s  -> temp/thresholds/latest.json")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
