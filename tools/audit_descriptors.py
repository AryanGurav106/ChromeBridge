"""Can a control be named by DECLARATIONS alone, uniquely and repeatably?

FLOW_RECORDER_PLAN rests on one assumption: a recorded step can store a
descriptor made of what the document declares -- tag, role, accessible name,
the landmark it sits in, the heading above it -- instead of a DOM path, and
that descriptor will still pick out exactly one control on a later run.

Every other record-and-replay tool stores a path (Midscene an XPath, Chrome's
Recorder a CSS/ARIA tuple) and a path breaks on the re-render that fix #5
exists to survive. The claim here is that declarations survive it. That claim
is measurable, and until it is measured it is a design preference.

TWO questions, because either one alone is misleading:

  UNIQUENESS  of the entries in one listing, how many are picked out by their
              own descriptor and nothing else? A descriptor matching three
              controls cannot drive a click -- #24's submit picker refuses
              when several candidates match rather than taking the first, and
              a flow step must refuse the same way.

  STABILITY   replay the SAME source twice and diff the descriptor sets. A
              descriptor that is unique but regenerates differently is worse
              than useless: the flow fails on a frontend that did not change.
              This is the drift control #19 demands, and the corpus needs it --
              18 of the 108 frozen sites replay non-deterministically (#16) and
              are named rather than chased.

WHAT IS DELIBERATELY NOT IN A DESCRIPTOR, and why:

  value       CURRENT CONTENTS (#6). It changes as the flow types into it, so
              identity built on it dissolves at the moment of use.
  active, unselected, disabled, required
              STATE. The flow asserts these; it must not identify by them, or
              a step can only find a control that is already in the state the
              step exists to produce.
  x, y, w, h  geometry. #26 made it opt-in after WorkArena measured
              coordinates HURTING on dense pages, and #23/#25 measured ours
              drifting 110px and 1097px.
  class names, framework names, pixel sizes
              #27/#28 removed these from the path that decides existence.
              Re-introducing them here would put them back one layer up.

Usage:
    python tools/audit_descriptors.py                 # 40 sites, both passes
    python tools/audit_descriptors.py --sites 12      # quick
    python tools/audit_descriptors.py --live          # against the real web
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "temp" / "frozen"
OUT = ROOT / "temp" / "descriptors"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract  # noqa: E402
from capture_listings import SITES  # noqa: E402

sys.path.insert(0, str(ROOT))
from core.flows import descriptor as D  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = extract("_collectInteractivePage", BG, verify=True)
TAG_JS = str(ROOT / "extension" / "listener_tag.js")
VIEWPORT = {"width": 1280, "height": 1600}
FULL_LV = D.FULL


# ---------------------------------------------------------------------------
# The descriptor ladder is IMPORTED, never restated here. A probe that carries
# its own copy of the thing it measures stops measuring it the moment one of
# them changes -- #21's one-concept-two-spellings, and the exact reason
# measure_retention.py imports the real find() scorer rather than reproducing
# it. The ladder below is whatever core/flows/descriptor.py currently says.
# ---------------------------------------------------------------------------
LEVELS = [" ".join(l) for l in D.LEVELS]


def descriptor(e: dict, level: int) -> tuple:
    d = D.at_level(e, level)
    return tuple(d[k] for k in sorted(d))


# Same rule as the resolver's pool, imported for the same reason as the ladder.
_identifying = D._targetable


async def collect(page) -> list[dict]:
    return await page.evaluate(
        "(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, 'compact'); })()"
    ) or []


async def load(ctx, name: str, url: str, live: bool):
    page = await ctx.new_page()
    if not live:
        har = FROZEN / f"{name}.har"
        if not har.exists():
            await page.close()
            return None
        await ctx.route_from_har(str(har), not_found="abort")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
    except Exception:
        try:
            await page.close()
        except Exception:
            pass
        return None
    await page.wait_for_timeout(1200)
    return page


async def run_site(browser, name: str, url: str, live: bool) -> dict | None:
    """Collect the SAME source twice, in two fresh contexts.

    Two contexts rather than a reload, because a reload reuses the renderer and
    would flatter the stability number -- the question is whether a descriptor
    survives being regenerated from scratch, which is what a later test run does.
    """
    passes = []
    for _ in range(2):
        ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True)
        await ctx.add_init_script(path=TAG_JS)
        try:
            page = await load(ctx, name, url, live)
            if page is None:
                await ctx.close()
                return None
            passes.append(await collect(page))
        finally:
            await ctx.close()

    a, b = passes
    if len(a) < 5:
        return None

    targets = [e for e in a if _identifying(e)]
    if not targets:
        return None

    row: dict = {"name": name, "entries": len(a), "targets": len(targets)}

    # --- uniqueness -------------------------------------------------------
    for lv in range(len(LEVELS)):
        counts = Counter(descriptor(e, lv) for e in a)
        uniq = sum(1 for e in targets if counts[descriptor(e, lv)] == 1)
        row[f"uniq_{lv}"] = round(uniq / len(targets), 4)
        # Where it is NOT unique, how crowded is the tie? A tie of 2 is a
        # different problem from a tie of 40: the first is resolvable by one
        # more declared field, the second is a repeated record and wants an
        # ordinal, which is what the tree format already states positionally.
        ties = [counts[descriptor(e, lv)] for e in targets
                if counts[descriptor(e, lv)] > 1]
        row[f"tie_med_{lv}"] = statistics.median(ties) if ties else 0

    # --- stability --------------------------------------------------------
    # Compare at the strongest and the cheapest useful level. A descriptor set
    # that differs between two identical loads is the floor on what any
    # uniqueness number can mean.
    for lv in (1, FULL_LV):
        sa = Counter(descriptor(e, lv) for e in a if _identifying(e))
        sb = Counter(descriptor(e, lv) for e in b if _identifying(e))
        kept = sum((sa & sb).values())
        total = max(sum(sa.values()), sum(sb.values())) or 1
        row[f"stable_{lv}"] = round(kept / total, 4)

    # --- ORDER stability, which set stability does NOT cover ---------------
    # The measurement above says the same descriptors come back. It says
    # nothing about whether the 3rd match is the same element both times --
    # and a tie is resolved by ordinal, so if the order flips the ordinal
    # picks a different control while every other number here looks perfect.
    # That is the #10/#11/#12 shape: right-looking, acting elsewhere.
    #
    # Geometry is the right ruler HERE and wrong in a descriptor: it answers
    # "is this the same element" for a measurement, which is exactly what it
    # cannot be trusted to do at click time (#23's 110px, #25's 1097px).
    def groups(entries, lv):
        g: dict[tuple, list] = {}
        for e in entries:
            if _identifying(e):
                g.setdefault(descriptor(e, lv), []).append(
                    (round((e.get("y") or 0) / 10), round((e.get("x") or 0) / 10)))
        return g

    ga, gb = groups(a, FULL_LV), groups(b, FULL_LV)
    tied = [k for k, v in ga.items() if len(v) > 1]
    agree = sum(1 for k in tied if gb.get(k) == ga[k])
    row["tied_groups"] = len(tied)
    row["ord_stable"] = round(agree / len(tied), 4) if tied else None

    # --- what is carrying the work ---------------------------------------
    row["named"] = round(sum(1 for e in targets if (e.get("name") or e.get("label") or "").strip())
                         / len(targets), 4)
    row["synth"] = round(sum(1 for e in targets if e.get("synth")) / len(targets), 4)
    return row


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", type=int, default=40)
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()

    sites = sorted(SITES.items())[: args.sites] if isinstance(SITES, dict) else list(SITES)[: args.sites]

    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for i, item in enumerate(sites, 1):
            name, url = item if isinstance(item, tuple) else (item["name"], item["url"])
            try:
                r = await run_site(browser, name, url, args.live)
            except Exception as exc:
                print(f"  [{i:>3}/{len(sites)}] {name:<24} ERROR {exc}")
                continue
            if r is None:
                print(f"  [{i:>3}/{len(sites)}] {name:<24} skipped")
                continue
            rows.append(r)
            print(f"  [{i:>3}/{len(sites)}] {name:<24} targets={r['targets']:<4} "
                  f"uniq@name={r['uniq_1']:.2f} uniq@full={r["uniq_" + str(FULL_LV)]:.2f} "
                  f"stable={r["stable_" + str(FULL_LV)]:.2f}")
        await browser.close()

    if not rows:
        print("no sites measured")
        return 1

    def med(k):
        return statistics.median(r[k] for r in rows)

    print(f"\n{'=' * 78}\nDESCRIPTOR UNIQUENESS — {len(rows)} sites, "
          f"{sum(r['targets'] for r in rows)} targetable controls\n{'=' * 78}")
    print(f"{'descriptor':<30}{'median uniq':>14}{'worst':>10}{'median tie':>13}")
    for lv, label in enumerate(LEVELS):
        cum = LEVELS[lv]
        print(f"  {cum:<28}{med(f'uniq_{lv}'):>13.1%}"
              f"{min(r[f'uniq_{lv}'] for r in rows):>10.1%}"
              f"{med(f'tie_med_{lv}'):>13.0f}")

    print(f"\nSTABILITY (same source, two fresh contexts — the drift floor)")
    for lv in (1, FULL_LV):
        worst = min(rows, key=lambda r: r[f"stable_{lv}"])
        print(f"  level {lv} ({LEVELS[lv]:<14}) median {med(f'stable_{lv}'):.1%}"
              f"   worst {worst[f'stable_{lv}']:.1%} ({worst['name']})")

    ordr = [r for r in rows if r.get("ord_stable") is not None]
    if ordr:
        worst = min(ordr, key=lambda r: r["ord_stable"])
        print(f"\nORDINAL stability (is the Nth match the same element twice?)")
        print(f"  tied groups {sum(r['tied_groups'] for r in ordr)} across {len(ordr)} sites"
              f"   median {statistics.median(r['ord_stable'] for r in ordr):.1%}"
              f"   worst {worst['ord_stable']:.1%} ({worst['name']})")

    print(f"\n  controls carrying an accessible name : {med('named'):.1%}")
    print(f"  ...whose name is SYNTHESIZED (#23/#41): {med('synth'):.1%}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "descriptors.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT / 'descriptors.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
