"""Does the hidden-cell table fix (#E4-D12) change anything it should not?

The fix: the aligned-table grid filters cells with a bare `checkVisibility()`,
so a `display:none` <th>/<td> stops being counted as a column. It shipped on a
correctness argument plus three fixtures; this asks the corpus.

THE GATING QUESTION IS #4 IN THE BRIEF, NOT #1: how many frozen sites contain a
display:none TD or TH inside a table AT ALL. If that is near zero, the corpus
demonstrates nothing and the fixtures are the only evidence -- which is #25's
rule (an ablation measures the code against the sample; it cannot measure the
sample) and must be said plainly rather than dressed up as a clean result.

Measured IN ONE PAGE LOAD per site. There are no arms to rotate: the two
quantities (cells that exist, cells the page lays out) are read from the same
DOM in the same evaluate, so run-order drift cannot align with anything.

  python tools/audit_table_hidden_cells.py [--n 40]
"""
import argparse, asyncio, json, sys
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "temp" / "frozen"
sys.path.insert(0, str(ROOT / "tools"))
from capture_listings import SITES  # noqa: E402

VIEWPORT = {"width": 1280, "height": 1600}

# Reads the SAME question the renderer now asks (`c.checkVisibility()`), per
# cell, plus the per-row counts that decide alignment. Nothing is reimplemented
# -- this measures the predicate, not a copy of the renderer.
PROBE = r"""() => {
  const out = {tables: 0, cells: 0, unpainted: 0, rows_changed: 0,
               mismatch_before: 0, mismatch_after: 0, samples: []};
  const laid = (c) => { try { return c.checkVisibility ? c.checkVisibility() : true; }
                        catch (e) { return true; } };
  for (const t of Array.from(document.querySelectorAll('table')).slice(0, 40)) {
    let trs = [];
    try { trs = Array.from(t.querySelectorAll('tr')).filter(r => r.closest('table') === t); }
    catch (e) { continue; }
    if (trs.length < 2) continue;
    out.tables++;
    const widthsBefore = [], widthsAfter = [];
    for (const tr of trs) {
      const cells = Array.from(tr.children).filter(c => /^(TD|TH)$/.test(c.tagName));
      if (!cells.length) continue;
      const kept = cells.filter(laid);
      out.cells += cells.length;
      out.unpainted += cells.length - kept.length;
      if (kept.length !== cells.length) {
        out.rows_changed++;
        if (out.samples.length < 3) {
          out.samples.push({
            dropped: cells.filter(c => !laid(c)).slice(0, 3)
              .map(c => ({tag: c.tagName,
                          txt: (c.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40),
                          disp: getComputedStyle(c).display})),
            row_before: cells.length, row_after: kept.length});
        }
      }
      widthsBefore.push(cells.length);
      widthsAfter.push(kept.length);
    }
    // A table "misaligns" when its rows do not all agree on a width. That is
    // the condition the fix exists for; colspan can also cause it legitimately,
    // so this is a SCREEN and not a verdict.
    if (new Set(widthsBefore).size > 1) out.mismatch_before++;
    if (new Set(widthsAfter).size > 1) out.mismatch_after++;
  }
  return out;
}"""


async def one(browser, name, url):
    ctx = await browser.new_context(viewport=VIEWPORT)
    try:
        har = FROZEN / f"{name}.har"
        if not har.exists():
            return None
        await ctx.route_from_har(str(har), not_found="abort")
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        await page.wait_for_timeout(500)
        return await page.evaluate(PROBE)
    except Exception:
        return None
    finally:
        await ctx.close()


async def main(n):
    rows = []
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        for name, url in SITES[:n]:
            r = await one(b, name, url)
            if r and r.get("tables"):
                rows.append((name, r))
                flag = "  <-- HAS UNPAINTED CELLS" if r["unpainted"] else ""
                print(f"  {name:<22} tables={r['tables']:<3} cells={r['cells']:<5} "
                      f"unpainted={r['unpainted']:<4} rows_changed={r['rows_changed']:<4} "
                      f"ragged {r['mismatch_before']}->{r['mismatch_after']}{flag}")
        await b.close()

    withu = [r for _n, r in rows if r["unpainted"]]
    print(f"\nsites with any table: {len(rows)}")
    print(f"sites with a display:none TD/TH: {len(withu)}")
    print(f"total cells seen: {sum(r['cells'] for _n, r in rows)}; "
          f"unpainted: {sum(r['unpainted'] for _n, r in rows)}")
    print(f"ragged tables BEFORE the fix: {sum(r['mismatch_before'] for _n, r in rows)}; "
          f"AFTER: {sum(r['mismatch_after'] for _n, r in rows)}")
    for nm, r in rows:
        for s in r["samples"]:
            print(f"  sample {nm}: row {s['row_before']}->{s['row_after']} "
                  f"dropped={json.dumps(s['dropped'], ensure_ascii=False)[:150]}")
    if not withu:
        print("\nVERDICT: the corpus contains NO display:none table cell, so it "
              "demonstrates NOTHING about this fix either way. The fixtures "
              "(TB15/TB15b/TB15c) are the only evidence. #25: an ablation "
              "measures the code against the sample, it cannot measure the sample.")
    else:
        print(f"\nVERDICT: {len(withu)} site(s) exercise the fix. Read the samples "
              "above and judge whether each dropped cell is genuinely not laid out.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    asyncio.run(main(ap.parse_args().n))
