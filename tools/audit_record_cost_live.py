"""What does `recordAtoms` cost the REAL collector, per read?

`audit_record_definition.py --cost` times a reimplementation of the record
rule over `__mmidReg`. That is the right population (the entry loop at
`background.js:7982` is `mmidReg.forEach`), but it is still my code, and the
claim it supports -- that the shipped field costs up to half a second of every
`read_page` for a consumer only `record_flow` uses -- is damning enough to
re-derive against the product (MEASUREMENT R1).

This times `_collectInteractivePage` ITSELF, in three arms built by patching
the extracted source, INTERLEAVED on one page load with the order rotated per
replicate (#19 / MEASUREMENT R3):

  base    the collector as it ships
  noatom  `recordAtoms: null` -- the field removed, nothing else touched
  climb   the record found by `_climbTo`'s rule instead of `closest()`

The arms are built by string-patching, and each patch asserts its anchor
occurs exactly once, so the probe cannot silently measure three copies of the
same build (the probe-lifetime rule in docs/MEASUREMENT.md).

    python tools/audit_record_cost_live.py --sites 20
    python tools/audit_record_cost_live.py --selftest
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "temp" / "frozen"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))
from _extract import extract  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VIEWPORT = {"width": 1280, "height": 1600}
REPS = 5

OLD_CLOSEST = "          let r = el.closest && el.closest('tr,li,dl,article,figure,fieldset');"
NEW_CLIMB = "          let r = _rcClimb(el);"
ATOM_HEAD = "      recordAtoms: (() => {"

CLIMB_SRC = """
  const _rcRECORD = { TR: 1, LI: 1, DL: 1, FIGURE: 1, ARTICLE: 1 };
  const _rcSTOP = {
    MAIN: 1, NAV: 1, HEADER: 1, FOOTER: 1, ASIDE: 1, SECTION: 1,
    FORM: 1, FIELDSET: 1, TABLE: 1, UL: 1, OL: 1, BODY: 1, HTML: 1,
  };
  const _rcSig = (e, d) => {
    const s = e.tagName + '.' + (typeof e.className === 'string'
      ? e.className.trim().replace(/\\s+/g, ' ') : '');
    if (d <= 0) return s;
    const k = [];
    for (const c of e.children) k.push(_rcSig(c, d - 1));
    return s + '(' + k.join(',') + ')';
  };
  const _rcCls = (e) => {
    try {
      return (typeof e.className === 'string'
        ? e.className.trim().split(/\\s+/).filter(Boolean) : []);
    } catch (err) { return []; }
  };
  const _rcSame = (a, b) => {
    if (a.tagName !== b.tagName) return false;
    const ca = _rcCls(a), cb = _rcCls(b);
    if (!ca.length && !cb.length) return _rcSig(a, 3) === _rcSig(b, 3);
    if (!ca.length || !cb.length) return false;
    for (const t of ca) if (cb.indexOf(t) !== -1) return true;
    return false;
  };
  const _rcIsRec = (n) => {
    try {
      const p = n.parentElement;
      if (!p || p.children.length < 2) return false;
      let k = 0;
      for (const c of p.children) { if (_rcSame(n, c) && ++k > 1) return true; }
      return false;
    } catch (e) { return false; }
  };
  const _rcClimb = (node) => {
    try {
      let n = node, d = 0;
      while (n && d < 8) {
        n = n.parentElement || (n.getRootNode && n.getRootNode().host) || null;
        if (!n) break;
        d++;
        if (d <= 4 && _rcRECORD[n.tagName]) return n;
        if (_rcSTOP[n.tagName]) break;
        if (_rcIsRec(n)) return n;
      }
    } catch (e) {}
    return null;
  };
"""


def once(src, needle, what):
    if src.count(needle) != 1:
        raise SystemExit(f"anchor {what}: {src.count(needle)} occurrences, expected 1")


def arms(collect_js: str) -> dict:
    once(collect_js, OLD_CLOSEST, "closest")
    once(collect_js, ATOM_HEAD, "recordAtoms head")
    sig = "function _collectInteractivePage("
    once(collect_js, sig, "signature")
    head_end = collect_js.index("{", collect_js.index(sig)) + 1

    noatom = collect_js.replace(
        ATOM_HEAD, "      recordAtoms: (() => { if (1) return null;")
    climb = (collect_js[:head_end] + CLIMB_SRC + collect_js[head_end:]) \
        .replace(OLD_CLOSEST, NEW_CLIMB)
    out = {"base": collect_js, "noatom": noatom, "climb": climb}
    # The arms MUST differ, or this measures one build three times.
    assert len({len(v) for v in out.values()}) == 3, "arms are not distinct"
    return out


async def one(browser, name, url, settle, armsrc):
    har = FROZEN / f"{name}.har"
    if not har.exists():
        return None
    ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True)
    await ctx.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
    await ctx.route_from_har(str(har), not_found="abort")
    page = await ctx.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
    except Exception:
        await ctx.close()
        return None
    await page.wait_for_timeout(settle)
    try:
        for k, src in armsrc.items():
            await page.evaluate("([k,s])=>{window.__rcf=window.__rcf||{};"
                                "window.__rcf[k]=new Function(s+';return "
                                "_collectInteractivePage;')();}", [k, src])
        res = await page.evaluate("""(reps) => {
          const keys = Object.keys(window.__rcf);
          const out = {}; keys.forEach(k => out[k] = []);
          let n = 0;
          for (let i = 0; i < reps; i++) {
            const order = i % 2 ? keys.slice().reverse() : keys;
            for (const k of order) {
              const t = performance.now();
              const r = window.__rcf[k](true, null, 'brief');
              out[k].push(performance.now() - t);
              n = (r || []).length;
            }
          }
          out._entries = n;
          return out;
        }""", REPS)
    except Exception as exc:
        await ctx.close()
        return {"name": name, "error": f"{type(exc).__name__}: {str(exc)[:70]}"}
    await ctx.close()
    med = {k: statistics.median(v) for k, v in res.items() if k != "_entries"}
    spread = max(max(v) - min(v) for k, v in res.items() if k != "_entries")
    return {"name": name, "entries": res["_entries"], "floor_ms": spread, **med}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", type=int, default=20)
    ap.add_argument("--only", default="")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    bg = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
    collect_js = extract("_collectInteractivePage", bg, verify=True)
    armsrc = arms(collect_js)
    if args.selftest:
        print(f"  three distinct arms built: "
              f"{ {k: len(v) for k, v in armsrc.items()} }")
        print(f"  noatom removes the field : {'if (1) return null' in armsrc['noatom']}")
        print(f"  climb replaces closest()  : "
              f"{NEW_CLIMB.strip() in armsrc['climb'] and OLD_CLOSEST not in armsrc['climb']}")
        print("  SELFTEST PASS")
        return 0

    from playwright.async_api import async_playwright
    from capture_listings import SITES
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    sel = [(s[0], s[1], s[2] if len(s) > 2 else 1200) for s in list(SITES)[: args.sites]]
    sel = [t for t in sel if not only or t[0] in only]
    rows = []
    async with async_playwright() as p:
        br = await p.chromium.launch()
        for name, url, settle in sel:
            r = await one(br, name, url, settle, armsrc)
            if not r:
                continue
            if r.get("error"):
                print(f"  {r['name']:<20} ERROR {r['error']}", flush=True)
                continue
            rows.append(r)
            print(f"  {r['name']:<20} entries={r['entries']:<5} base={r['base']:>8.1f}ms "
                  f"noatom={r['noatom']:>8.1f}ms climb={r['climb']:>9.1f}ms  "
                  f"atoms cost={r['base'] - r['noatom']:>+8.1f}ms  "
                  f"climb-base={r['climb'] - r['base']:>+9.1f}ms  floor={r['floor_ms']:.1f}ms",
                  flush=True)
        await br.close()
    if rows:
        print(f"\n  REAL COLLECTOR, {len(rows)} sites. One `read_page` = one of these.")
        for k, lbl in (("base", "collector as it ships"),
                       ("noatom", "...with recordAtoms removed"),
                       ("climb", "...with the climb record")):
            v = sorted(r[k] for r in rows)
            print(f"    {lbl:<30} median {statistics.median(v):>8.1f}ms  "
                  f"p90 {v[int(len(v) * .9)]:>9.1f}ms  max {v[-1]:>9.1f}ms")
        for a, b, lbl in (("base", "noatom", "what recordAtoms costs TODAY"),
                          ("climb", "base", "what the climb record would ADD")):
            v = sorted(r[a] - r[b] for r in rows)
            print(f"    {lbl:<30} median {statistics.median(v):>+8.1f}ms  "
                  f"p90 {v[int(len(v) * .9)]:>+9.1f}ms  max {v[-1]:>+9.1f}ms")
        f = sorted(r["floor_ms"] for r in rows)
        print(f"    {'A/A floor (worst spread)':<30} median {statistics.median(f):>8.1f}ms  "
              f"p90 {f[int(len(f) * .9)]:>9.1f}ms  max {f[-1]:>9.1f}ms")
        (ROOT / "temp" / "descriptors").mkdir(parents=True, exist_ok=True)
        (ROOT / "temp" / "descriptors" / "record_cost_live.json").write_text(
            json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
