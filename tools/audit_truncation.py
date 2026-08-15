"""How much of the listing was being hidden in silence, and what marking it costs.

WHY
---
Seven of twenty live agents reported a bounded field that gave no sign of being
bounded. The argument for fixing it was qualitative — `value="Acme Corporation
Interna"` and a field whose contents really are that string are the same 24
characters, one of them a lie the agent cannot detect. This puts numbers on both
halves of that argument, over the frozen 108-site corpus so the answer is
deterministic:

  HIDDEN    how many fields hit a cap, and how many characters vanished with no
            marker. This is the size of the defect.
  COST      what the `…(+N)` markers add to a listing. This is the price, and it
            has to be small or the fix is not worth having — the same standard
            the detail-level legend was held to (110 chars, 2.6% of a median
            listing).

Runs against temp/frozen/*.har via Playwright route_from_har, so it measures the
collector and not the network.

Run:
    python tools/audit_truncation.py
    python tools/audit_truncation.py --limit 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
from collections import defaultdict
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "temp" / "frozen"
OUT = ROOT / "temp" / "dom_audit"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = extract("_collectInteractivePage", BG, verify=True)
TAG_JS = str(ROOT / "extension" / "listener_tag.js")
VIEWPORT = {"width": 1280, "height": 1600}

MARK = re.compile(r"…\(\+(\d+)\)")
# The fields an agent READS to decide what a control is and what it holds. A cut
# in any of these is a cut in the evidence, not in the decoration.
FIELDS = ("name", "label", "value", "placeholder", "text", "near")
# Every literal cap the collector applies to an agent-facing string.
CAPS = (24, 30, 40, 50, 60, 80, 100, 120, 200, 2000)


def load_sites() -> list[tuple[str, str]]:
    src = (ROOT / "tools" / "capture_listings.py").read_text(encoding="utf-8")
    body = src[src.index("SITES = ["):src.index("\nOUT = ")]
    return re.findall(r'\(\s*"([a-z_0-9]+)"\s*,\s*"(https?://[^"]+)"', body)


async def run_site(browser, name: str, url: str) -> dict | None:
    har = FROZEN / f"{name}.har"
    if not har.exists():
        return None
    ctx = await browser.new_context(viewport=VIEWPORT)
    try:
        await ctx.add_init_script(path=TAG_JS)
        await ctx.route_from_har(str(har), not_found="abort")
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        try:
            await page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass
        await page.wait_for_timeout(700)
        raw = await page.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        listing = await page.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()")
    except Exception as e:
        return {"name": name, "skipped": str(e)[:90]}
    finally:
        await ctx.close()

    # COST is measured on the string listing, DEFECT on the structured entries.
    # Mixing them put marker cost at 78.7% of payload for the guardian, because
    # the structured set is whole-page while the string listing is viewport-
    # scoped — two different populations over one denominator. The corpus has
    # produced this exact class of error before (drift attributed to a code
    # change); the rule is that a ratio's numerator and denominator must come
    # from the same population.
    listing_marks = MARK.findall(listing or "")
    marker_chars = sum(len("…(+" + n + ")") for n in listing_marks)

    cuts, hidden = 0, 0
    per_field: dict[str, int] = {}
    # SILENT CAPS: fields landing exactly on a known cap with no marker. This is
    # the detector for the caps I have NOT found — the marked ones are fixed by
    # construction, so counting them only measures the fix. A field whose length
    # is exactly 40 or exactly 120 happens by chance about once in that many
    # values; a cap produces a spike, and a spike on one field name is a site to
    # go and read.
    silent: dict[str, set] = {}
    for e in raw or []:
        for f in FIELDS:
            v = e.get(f) or ""
            if not isinstance(v, str):
                continue
            for m in MARK.finditer(v):
                cuts += 1
                hidden += int(m.group(1))
                per_field[f] = per_field.get(f, 0) + 1
            if v and not MARK.search(v):
                # COUNT DISTINCT VALUES, NOT OCCURRENCES. A cap truncates MANY
                # DIFFERENT strings to the same length; one string repeated many
                # times is just repeated content. Measured: an MUI demo page
                # repeats a genuine 99-char aria-label 39 times, which produced a
                # textbook cap signature (39 at length 99, neighbours ~2) for a
                # value that is not cut at all. Distinct-counting dissolves it —
                # 39 occurrences of one string is 1.
                k = f"{f}@{len(v)}"
                silent.setdefault(k, set()).add(v)
    return {
        "name": name,
        "entries": len(raw or []),
        "listing_chars": len(listing or ""),
        "cuts": cuts,
        "listing_cuts": len(listing_marks),
        "hidden": hidden,
        "marker_chars": marker_chars,
        "per_field": per_field,
        "silent": {k: len(v) for k, v in silent.items()},
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    sites = load_sites()
    sites = [s for s in sites if (FROZEN / f"{s[0]}.har").exists()]
    if args.limit:
        sites = sites[: args.limit]
    if not sites:
        print("no frozen recordings — run tools/freeze_corpus.py first")
        return 1
    print(f"{len(sites)} frozen sites\n")

    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for i, (name, url) in enumerate(sites, 1):
            r = await run_site(browser, name, url)
            if r and "skipped" not in r:
                rows.append(r)
            if i % 20 == 0 or i == len(sites):
                print(f"  [{i:>3}/{len(sites)}] scored {len(rows)}", flush=True)
        await browser.close()

    if not rows:
        print("nothing scored")
        return 1

    tot_cuts = sum(r["cuts"] for r in rows)
    tot_hidden = sum(r["hidden"] for r in rows)
    tot_marker = sum(r["marker_chars"] for r in rows)
    tot_listing = sum(r["listing_chars"] for r in rows)
    with_cuts = [r for r in rows if r["cuts"]]
    per_field: dict[str, int] = {}
    for r in rows:
        for k, v in r["per_field"].items():
            per_field[k] = per_field.get(k, 0) + v

    print(f"\n{'='*66}\nTRUNCATION ON THE FROZEN CORPUS — {len(rows)} sites\n{'='*66}")
    print(f"sites with at least one cut field   {len(with_cuts):>6} / {len(rows)}"
          f"  ({len(with_cuts)/len(rows):.0%})")
    print(f"fields cut                          {tot_cuts:>6}")
    print(f"characters that used to vanish      {tot_hidden:>6}"
          f"   (median {statistics.median([r['hidden'] for r in with_cuts]) if with_cuts else 0:.0f}/site)")
    print("\nby field (which evidence was being cut):")
    for k, v in sorted(per_field.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<14}{v:>5}")

    print(f"\ncost of saying so                   {tot_marker:>6} chars"
          f"  = {tot_marker/max(1,tot_listing):.3%} of listing payload")
    worst = max(rows, key=lambda r: r["marker_chars"] / max(1, r["listing_chars"]))
    print(f"  worst site: {worst['name']} "
          f"{worst['marker_chars']}/{worst['listing_chars']} = "
          f"{worst['marker_chars']/max(1,worst['listing_chars']):.2%}")
    top = sorted(rows, key=lambda r: -r["hidden"])[:6]
    print("\nmost content previously hidden without a signal:")
    for r in top:
        print(f"  {r['name']:<16}{r['hidden']:>6} chars across {r['cuts']:>3} fields")

    sil: dict[str, int] = {}
    for r in rows:
        for k, v in (r.get("silent") or {}).items():
            sil[k] = sil.get(k, 0) + v
    # A raw count at one length proves nothing: short labels genuinely cluster,
    # so `label@24 = 264` is as consistent with the natural mode of button text
    # as with a cap. A CAP is a length that is common while its NEIGHBOURS are
    # not — everything that would have been 61..90 chars piles onto exactly 60,
    # and 61 goes to zero. So compare each length against the lengths around it,
    # which is the same discipline as the corpus drift control: measure the
    # thing against its own baseline, not against zero.
    hist: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for k, v in sil.items():
        fld, n = k.rsplit("@", 1)
        hist[fld][int(n)] += v
    spikes = []
    for fld, h in hist.items():
        for n, c in h.items():
            if c < 12:
                continue
            nb = [h.get(n + d, 0) for d in (-3, -2, -1, 1, 2, 3)]
            base = sum(nb) / len(nb)
            above = h.get(n + 1, 0) + h.get(n + 2, 0)
            # a cap also has a CLIFF: almost nothing survives past it
            if c >= max(4 * base, 12) and above <= c * 0.25:
                spikes.append((fld, n, c, base, above))
    spikes.sort(key=lambda t: -t[2])
    print("\nSILENT CAPS — a length that is common while its neighbours are not,")
    print("and past which almost nothing survives. That shape is a cap, not a mode.")
    if spikes:
        print(f"  {'field@len':<18}{'count':>7}{'neighbours':>12}{'>len':>7}")
        for fld, n, c, base, above in spikes[:12]:
            print(f"  {fld + '@' + str(n):<18}{c:>7}{base:>12.1f}{above:>7}")
    else:
        print("  none: every agent-facing cap is routed through markCut.")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "truncation.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\n-> {OUT / 'truncation.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
