"""--drift and --cost halves of audit_observe_act_gap.py (kept apart so the matrix stays readable)."""
import asyncio, json, random, statistics, sys, time
from pathlib import Path
from playwright.async_api import async_playwright
import audit_observe_act_gap as G

ROOT = G.ROOT
FROZEN = ROOT / "temp" / "frozen"

def sites():
    import re
    src = (ROOT / "tools" / "capture_listings.py").read_text(encoding="utf-8")
    body = src[src.index("SITES = ["):src.index("\nOUT = ")]
    return [(n, u) for n, u in re.findall(r'\(\s*"([a-z_0-9]+)"\s*,\s*"(https?://[^"]+)"', body) if (FROZEN / f"{n}.har").exists()]

async def load(browser, name, url):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
    await ctx.add_init_script(path=G.TAG)
    await ctx.add_init_script(script=G.SIG_JS)
    await ctx.route_from_har(str(FROZEN / f"{name}.har"), not_found="abort")
    pg = await ctx.new_page()
    await pg.goto(url, wait_until="domcontentloaded", timeout=30000)
    try: await pg.wait_for_load_state("networkidle", timeout=8000)
    except Exception: pass
    await pg.wait_for_timeout(1200)
    return ctx, pg

DRIFT_JS = r"""(async (arg) => {
  const [win] = arg;
  const col = (function(){ %s; return _collectInteractivePage(true); })();
  const reg = window.__mmidReg; const els = [];
  for (const e of col) { if (e.offscreen) continue; const n = reg && reg.get(String(e.mmid)); if (n && n.isConnected) els.push([e.mmid, n]); if (els.length >= 80) break; }
  const obs = els.map(([m, n]) => [m, n, window.__sig(n)]);
  const t0 = performance.now();
  await new Promise(r => setTimeout(r, win));
  const w = performance.now() - t0 + 5;
  const sum = q => q.structural + q.text + Object.values(q.attrs).reduce((a, b) => a + b, 0);
  const o = { n: obs.length, gone: 0, rectMoved: 0, ringEl: 0, ringRec: 0, ringDoc: sum(window.__abMut.query(null, w)),
              diff: {tag:0, role:0, name:0, dis:0, href:0, rec:0}, anyId: 0, submits: 0, submitId: 0 };
  for (const [m, n, a] of obs) {
    if (!n.isConnected) { o.gone++; continue; }
    const b = window.__sig(n); const d = window.__sigDiff(a, b);
    for (const k of d) o.diff[k]++;
    const ident = d.length > 0; if (ident) o.anyId++;
    const isSub = (n.matches('button[type=submit],input[type=submit]') || (n.tagName === 'BUTTON' && n.form && !n.hasAttribute('type')));
    if (isSub) { o.submits++; if (ident) o.submitId++; }
    const r0 = a.r, r1 = b.r;
    if (Math.abs(r0.x-r1.x) > 1 || Math.abs(r0.y-r1.y) > 1 || Math.abs(r0.w-r1.w) > 1 || Math.abs(r0.h-r1.h) > 1) o.rectMoved++;
    if (sum(window.__abMut.query(n, w))) o.ringEl++;
    const rec = n.closest('tr,li,dl,article,figure,fieldset');
    if (rec && sum(window.__abMut.query(rec, w))) o.ringRec++;
  }
  return o;
})""" % G.COLLECT

async def drift(browser, names, win):
    res = []
    sem = asyncio.Semaphore(4)
    async def one(n, u):
        async with sem:
            try:
                ctx, pg = await load(browser, n, u)
                r = await pg.evaluate(DRIFT_JS, [win]); r["site"] = n; res.append(r)
                await ctx.close()
            except Exception as e:
                print("skip", n, str(e)[:80])
    await asyncio.gather(*[one(n, u) for n, u in names])
    return res

async def ro_cost(browser):
    """ResizeObserver cost: interleaved, rotated, A/A drift control (CLAUDE.md #70/#19)."""
    out = {}
    ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
    pg = await ctx.new_page()
    for N in (1000, 5000, 20000):
        await pg.set_content("<style>.c{display:inline-block;width:20px;height:10px}</style><div id=r>" + "<i class=c></i>" * N + "</div>")
        await pg.evaluate("""() => {
          window.__bench = async (mode) => {
            const els = [...document.querySelectorAll('.c')];
            let ro = null;
            if (mode === 'ro') { ro = new ResizeObserver(() => {}); els.forEach(e => ro.observe(e)); await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); }
            const t0 = performance.now();
            for (let k = 0; k < 20; k++) { els.forEach((e, i) => { if (i % 10 === 0) e.style.width = (20 + (k % 2) * 5) + 'px'; }); void document.body.offsetHeight; }
            await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
            const dt = performance.now() - t0;
            if (ro) ro.disconnect();
            return dt; }; }""")
        modes = ["none", "ro", "none2"]; samples = {m: [] for m in modes}
        for rep in range(9):
            order = modes[rep % 3:] + modes[:rep % 3]
            for m in order:
                samples[m].append(await pg.evaluate("(m)=>window.__bench(m)", "ro" if m == "ro" else "none"))
        med = {m: statistics.median(v) for m, v in samples.items()}
        floor = abs(med["none"] - med["none2"]) / max(med["none"], 1e-9) * 100
        out[N] = {"none_ms": round(med["none"], 2), "ro_ms": round(med["ro"], 2), "aa_ms": round(med["none2"], 2),
                  "delta_ms": round(med["ro"] - med["none"], 2), "drift_floor_%": round(floor, 1)}
    await ctx.close()
    return out

async def sig_cost(browser, names):
    rows = []
    for n, u in names:
        try:
            ctx, pg = await load(browser, n, u)
            r = await pg.evaluate("""(function(){
              %s
              const t0 = performance.now(); const col = _collectInteractivePage(true); const tCol = performance.now() - t0;
              const reg = window.__mmidReg; const els = []; for (const e of col) { const x = reg.get(String(e.mmid)); if (x && x.isConnected) els.push([e.mmid, x]); }
              const t1 = performance.now(); const sigs = els.slice(0, 150).map(([m, x]) => window.__sig(x)); const tStampAll = performance.now() - t1;
              const k = els.length ? els[Math.floor(els.length / 2)] : null;
              let tOne = null, tScoped = null;
              if (k) {
                const reps = 200; const t2 = performance.now(); for (let i = 0; i < reps; i++) window.__sigDiff(sigs[0] || window.__sig(k[1]), window.__sig(k[1]));
                tOne = (performance.now() - t2) / reps;
                const t3 = performance.now(); _collectInteractivePage(true, String(k[0])); tScoped = performance.now() - t3;
              }
              return { entries: col.length, tCollectWhole: tCol, tStampUpTo150: tStampAll, tCompareOne: tOne, tScopedCollect: tScoped };
            })()""" % G.COLLECT)
            r["site"] = n; rows.append(r); await ctx.close()
        except Exception as e:
            print("skip", n, str(e)[:80])
    return rows

async def ring_cost(browser):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
    await ctx.add_init_script(path=G.TAG)
    pg = await ctx.new_page(); await pg.goto("about:blank")
    await pg.set_content("<div id=r><div id=s></div></div>")
    await pg.evaluate("() => { for (let i = 0; i < 4000; i++) { const d = document.createElement('i'); r.append(d); } }")
    await pg.wait_for_timeout(100)
    res = await pg.evaluate("""() => { const el = document.getElementById('s'); const a = [], b = [];
        for (let i = 0; i < 60; i++) { let t = performance.now(); window.__abMut.query(null, 3000); a.push(performance.now() - t);
          t = performance.now(); window.__abMut.query(el, 3000); b.push(performance.now() - t); }
        a.sort((x, y) => x - y); b.sort((x, y) => x - y);
        return { total: window.__abMut.query(null, 3000).total, unscoped_p50: a[30], unscoped_p95: a[57], scoped_p50: b[30], scoped_p95: b[57], scoped_max: b[59] }; }""")
    await ctx.close(); return res

async def run(argv):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        if "--cost" in argv:
            print("RO cost:", json.dumps(await ro_cost(browser), indent=1))
            print("ring query at saturation:", json.dumps(await ring_cost(browser)))
            heavy = [(n, u) for n, u in sites() if n in ("java_api", "mdn_select", "amazon", "github", "hn", "nytimes", "syncfusion", "wikipedia_en", "react_dev")]
            rows = await sig_cost(browser, heavy)
            for r in rows: print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
        else:
            all_s = sites(); random.seed(7); pick = random.sample(all_s, min(36, len(all_s)))
            res = await drift(browser, pick, 3600)
            Path(ROOT / "temp" / "observe_act_drift.json").write_text(json.dumps(res, indent=1))
            tot = lambda k: sum(r[k] for r in res)
            n = tot("n")
            print(f"sites={len(res)} listed-in-viewport entries={n}  window=3600ms (one model turn)")
            for k in ("gone", "rectMoved", "ringEl", "ringRec", "anyId", "submits", "submitId"):
                print(f"  {k:10s} {tot(k):6d}  {100*tot(k)/max(n,1):.2f}% of entries" + (f"  ({100*tot('submitId')/max(tot('submits'),1):.2f}% of {tot('submits')} declared submits)" if k == 'submitId' else ""))
            for f in ("tag", "role", "name", "dis", "href", "rec"):
                print(f"  diff.{f:5s} {sum(r['diff'][f] for r in res):6d}")
            print("  sites with ANY identity diff:", sum(1 for r in res if r["anyId"]), "/", len(res), "; with doc ring activity:", sum(1 for r in res if r["ringDoc"]))
        await browser.close()
