"""How much of a REAL page's DOM churn is a re-text rather than a structural change?

`audit_retext_tier.py` measures the reclassification against 21 synthetic shapes
built to put it under load. That answers "does the rule behave", and PRINCIPLES 9
is explicit that it cannot answer "does it matter on the web" -- an ablation
measures the code against the sample and cannot measure the sample. This is the
sample half: the frozen corpus, replayed with JS intact, with the SAME
instrumented ring, read at two offsets past DOMContentLoaded.

WHAT IS REPORTED, per site and per offset:
  structural / retext / text / attrs  -- the raw counts in the 3000ms window
  shipped tier                        -- what the banner says today
  candidate tier                      -- what it would say with the re-text fix
A site is "moved" when the two differ. Nothing here can move a read into
silence: a reclassified record goes from `structural` to `text` and both are
non-zero tiers, so a page that warned still warns (see audit_retext_tier.py).

THE CAVEAT, stated rather than rounded away. A HAR replays with `not_found=abort`,
so churn driven by a request the capture did not record never happens. A
`setInterval` + `textContent` clock still runs; a live price fed by polling does
not. The "ready but chatty" class is therefore UNDER-represented here and these
numbers are a FLOOR -- the same shape as #78's note that corpus HARs are
captured after consent, so CMP frames are under-counted.

Run:  .venv/bin/python tools/audit_retext_prevalence.py [--limit N] [--json out.json]
"""
import asyncio, json, sys
from collections import Counter
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from capture_listings import SITES                      # noqa: E402
from audit_retext_tier import TAG_RT                    # noqa: E402

FROZEN = ROOT / "temp" / "frozen"
OFFSETS = [1500, 4000]


def tiers(q):
    """(shipped, candidate) for one ring reading."""
    na = sum(q["attrs"].values())
    ship = ("STRONG" if (q["structural"] or q["text"])
            else ("MINOR" if na else "QUIET"))
    cs = q["structural"] - q["retext"]
    ct = q["text"] + q["retext"]
    cand = ("STRONG" if cs else ("TEXT" if ct else ("MINOR" if na else "QUIET")))
    return ship, cand


async def one(browser, name, url, sem):
    async with sem:
        har = FROZEN / f"{name}.har"
        if not har.exists():
            return None
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        try:
            await ctx.add_init_script(TAG_RT)
            await ctx.route_from_har(str(har), not_found="abort")
            pg = await ctx.new_page()
            try:
                await pg.goto(url, wait_until="domcontentloaded", timeout=25000)
            except Exception:
                await ctx.close()
                return None
            rows = []
            last = 0
            for off in OFFSETS:
                await pg.wait_for_timeout(off - last)
                last = off
                q = await pg.evaluate(
                    "() => window.__abMut ? window.__abMut.query(null, 3000) : null")
                if not q:
                    continue
                s, c = tiers(q)
                rows.append(dict(off=off, structural=q["structural"],
                                 retext=q["retext"], text=q["text"],
                                 attrs=sum(q["attrs"].values()),
                                 shipped=s, candidate=c))
            await ctx.close()
            return dict(name=name, rows=rows)
        except Exception:
            try: await ctx.close()
            except Exception: pass
            return None


async def main():
    lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    out_json = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    items = SITES[:lim] if lim else list(SITES)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        sem = asyncio.Semaphore(4)
        res = await asyncio.gather(*[one(browser, n, u, sem) for n, u, *_ in items])
        await browser.close()
    res = [r for r in res if r and r["rows"]]

    print(f"{'site':26} {'off':>5} {'struct':>7} {'retext':>7} {'text':>5} {'attr':>5} "
          f"{'shipped':>8} {'candidate':>10}")
    moved = Counter(); seen = Counter(); movers = set()
    for r in res:
        for w in r["rows"]:
            seen[w["off"]] += 1
            flag = ""
            if w["shipped"] != w["candidate"]:
                moved[w["off"]] += 1; movers.add(r["name"]); flag = "  MOVED"
            if w["structural"] or w["retext"] or w["text"] or w["attrs"]:
                print(f"{r['name']:26} {w['off']:>5} {w['structural']:>7} {w['retext']:>7} "
                      f"{w['text']:>5} {w['attrs']:>5} {w['shipped']:>8} "
                      f"{w['candidate']:>10}{flag}")
    print(f"\nsites replayed: {len(res)}")
    for off in OFFSETS:
        n = seen[off] or 1
        print(f"  @{off}ms: {moved[off]}/{seen[off]} reads change tier "
              f"({100.0 * moved[off] / n:.1f}%)")
    print(f"  sites moving at either offset: {len(movers)}/{len(res)} "
          f"-> {sorted(movers)}")
    # The share of structural records that are really re-texts, pooled. A page
    # with a lot of them is one where today's banner is describing a clock.
    tot_s = sum(w["structural"] for r in res for w in r["rows"])
    tot_r = sum(w["retext"] for r in res for w in r["rows"])
    print(f"  pooled: {tot_r}/{tot_s} childList records in-window are re-texts "
          f"({100.0 * tot_r / (tot_s or 1):.1f}%)")
    if out_json:
        Path(out_json).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
