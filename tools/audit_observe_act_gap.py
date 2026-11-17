"""Exposure matrix for the OBSERVE-TO-ACT gap (docs/OPEN.md item 1).

An agent reads a page, spends a model turn (~3.6s, CLAUDE.md #38), then acts on a
ref. This probe builds the hostile shapes and asks, for each one, which signal
that EXISTS TODAY (or that is cheap to add) would notice, and whether the act
that follows is actually harmed. Nothing under extension/ is modified.

Signals (all evaluated on the SAME page load, after the hazard):
  ref     page_fingerprint's question: does the mmid still resolve to a live node
  ring    window.__abMut mutation ring (#70): any record since observation,
          document-wide / inside the element / inside its declared record
  rect    getBoundingClientRect moved since observation (> 1px)
  occl    the REAL _rectForPage action-time pre-flight (blockedBy / not visible)
  sig     a light signature carried from the read: tag, role, name, disabled,
          href and the text of the declared record (tr/li/dl/article/figure)
  RO      a ResizeObserver on the target / on its ancestors / on body
Outcome of acting NOW through the real pre-flight and a real (trusted) mouse
click: refused / OK / NOOP / HARM, plus the same for a COORDINATE click aimed at
the observed centre (computer(coordinate=) never re-measures).

Run:  python tools/audit_observe_act_gap.py            (matrix)
      python tools/audit_observe_act_gap.py --drift    (false-positive rate on frozen pages)
      python tools/audit_observe_act_gap.py --cost     (what each piece costs)
"""
import asyncio, json, sys, statistics, time
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
TAG = str(ROOT / "extension" / "listener_tag.js")
COLLECT = extract("_collectInteractivePage", BG, verify=True)
RECTFOR = extract("_rectForPage", BG, verify=True)

# The proposed observed-signature, as one injectable function. Every field is
# DECLARED by the document (tag, role, accessible-ish name, :disabled, href, the
# nearest declared record) -- no size/class/wordlist (PRINCIPLES 1, 4).
SIG_JS = r"""
window.__sig = function (el) {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const h = s => { let x = 5381; for (let i = 0; i < s.length; i++) x = ((x << 5) + x + s.charCodeAt(i)) | 0; return x; };
  const rec = el.closest('tr,li,dl,article,figure,fieldset');
  const r = el.getBoundingClientRect();
  return { tag: el.tagName.toLowerCase(), role: el.getAttribute('role') || '',
    name: norm(el.getAttribute('aria-label') || el.innerText || el.value || el.title || el.alt || ''),
    dis: !!(el.matches(':disabled') || el.getAttribute('aria-disabled') === 'true'),
    href: el.href || '', rec: rec ? h(norm(rec.innerText)) : 0,
    r: { x: r.x, y: r.y, w: r.width, h: r.height } };
};
window.__sigDiff = function (a, b) {
  const d = [];
  for (const k of ['tag', 'role', 'name', 'dis', 'href', 'rec']) if (a[k] !== b[k]) d.push(k);
  return d;
};
"""

CSS = "body{margin:0;font:14px sans-serif} #hdr{position:fixed;top:0;left:0;right:0;height:40px;background:#ddd;z-index:5}" \
      " .pad{height:48px} button{height:30px;min-width:90px}"
def page(body, extra=""):
    return f"<!doctype html><meta charset=utf-8><style>{CSS}{extra}</style><body>{body}"

LOGJS = "window.__log=[];"
BTN = "<button id=t>Save</button>"
SAVE = "t.onclick=()=>__log.push('save');"
TBL = ("<table id=tb><tbody>" + "".join(
    f"<tr><td>INV-{i}</td><td><button {'id=t ' if i==1 else ''}class=d>Delete</button></td></tr>" for i in (1, 2, 3))
    + "</tbody></table>")
TBLJS = ("document.querySelectorAll('#tb tr').forEach(tr=>{const id=tr.cells[0].textContent;"
         "tr.querySelector('button').onclick=()=>__log.push('delete-'+id)});")

# name, html, setup-js, mutate-js, expected act, wait-ms after mutate, harm-note
H = [
 ("C0 nothing changes (control)", page('<div id=hdr></div><div class=pad></div>' + BTN), SAVE, "", "save", 100),
 ("C1 ticker churn elsewhere (control)", page('<div id=hdr><span id=tk>1</span></div><div class=pad></div>' + BTN), SAVE,
  "for(let i=0;i<20;i++)setTimeout(()=>tk.textContent=i+2,i*5);", "save", 200),
 ("C2 self class/style churn (control)", page('<div id=hdr></div><div class=pad></div>' + BTN), SAVE,
  "t.classList.add('hot');t.style.color='red';", "save", 100),
 ("H1 cookie banner pushes page down 80px", page('<div id=ban></div><div id=hdr></div><div class=pad></div>' + BTN), SAVE,
  "ban.style.height='80px';", "save", 100),
 ("H2a sticky header grows over target (page not scrollable)", page('<div id=hdr></div><div style="height:60px"></div>' + BTN), SAVE,
  "hdr.style.height='160px';", "save", 100),
 ("H2b sticky header grows over target (scrollable page)", page('<div id=hdr></div><div style="height:150px"></div>' + BTN + '<div style="height:3000px"></div>'), "window.scrollTo(0,100);" + SAVE,
  "hdr.style.height='160px';", "save", 100),
 ("H3 toast covers the button", page('<div id=hdr></div><div class=pad></div>' + BTN), SAVE,
  "const x=document.createElement('div');x.id='toast';x.textContent='Saved!';x.style.cssText='position:fixed;left:0;top:40px;width:300px;height:80px;background:#333;color:#fff;z-index:9';document.body.append(x);", "save", 100),
 ("H3b toast with pointer-events:none", page('<div id=hdr></div><div class=pad></div>' + BTN), SAVE,
  "const x=document.createElement('div');x.textContent='Saved!';x.style.cssText='position:fixed;left:0;top:40px;width:300px;height:80px;background:#333;color:#fff;z-index:9;pointer-events:none';document.body.append(x);", "save", 100),
 ("H8 modal + backdrop opens after the read", page('<div id=hdr></div><div class=pad></div>' + BTN), SAVE,
  "const x=document.createElement('div');x.setAttribute('role','dialog');x.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9';x.innerHTML='<div style=\"margin:100px;background:#fff;padding:20px\">Subscribe?</div>';document.body.append(x);", "save", 100),
 ("H4a node REPLACED, same tag+name, different action", page('<div id=hdr></div><div class=pad></div><div id=w>' + BTN + '</div>'), SAVE,
  "const n=document.createElement('button');n.textContent='Save';n.id='t';n.onclick=()=>__log.push('publish');w.replaceChildren(n);", "save", 100),
 ("H4b SAME node, handler swapped (no DOM mutation)", page('<div id=hdr></div><div class=pad></div>' + BTN), SAVE,
  "t.onclick=()=>__log.push('publish');", "save", 100),
 ("H5a list re-sort by MOVING nodes (ref follows record)", page('<div id=hdr></div><div class=pad></div>' + TBL), TBLJS,
  "const tb=document.querySelector('#tb tbody');tb.append(tb.rows[0]);", "delete-INV-1", 100),
 ("H5b list re-sort by REUSING nodes (React-unkeyed)", page('<div id=hdr></div><div class=pad></div>' + TBL), TBLJS,
  "const rs=[...document.querySelectorAll('#tb tr')];const ids=['INV-3','INV-2','INV-1'];rs.forEach((tr,i)=>{tr.cells[0].textContent=ids[i];tr.querySelector('button').onclick=()=>__log.push('delete-'+ids[i])});", "delete-INV-1", 100),
 ("H6 lazy image above loads, reflows column (no DOM mutation)", page('<div id=hdr></div><div class=pad></div><img src="/img.svg" style="display:block">' + BTN), SAVE,
  "", "save", 700),
 ("H7 target becomes disabled", page('<div id=hdr></div><div class=pad></div>' + BTN), SAVE,
  "t.disabled=true;", "save", 100),
 ("H9 label flips in place: Save -> Publish", page('<div id=hdr></div><div class=pad></div>' + BTN), SAVE,
  "t.textContent='Publish';t.onclick=()=>__log.push('publish');", "save", 100),
 ("H11 target removed", page('<div id=hdr></div><div class=pad></div>' + BTN), SAVE,
  "t.remove();", "save", 100),
 ("H11b target display:none", page('<div id=hdr></div><div class=pad></div>' + BTN), SAVE,
  "t.style.display='none';", "save", 100),
]

IMG = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="400"><rect width="100" height="400" fill="#999"/></svg>')

async def new_page(browser, html):
    ctx = await browser.new_context(viewport={"width": 800, "height": 600})
    await ctx.add_init_script(path=TAG)
    async def route(r):
        u = r.request.url
        if u.endswith("/img.svg"):
            await asyncio.sleep(0.35)
            await r.fulfill(status=200, content_type="image/svg+xml", body=IMG)
        else:
            await r.fulfill(status=200, content_type="text/html", body=html)
    await ctx.route("http://fx.test/**", route)
    pg = await ctx.new_page()
    await pg.goto("http://fx.test/h.html", wait_until="domcontentloaded")
    await pg.wait_for_timeout(60)
    return ctx, pg

async def prepare(pg, setup):
    await pg.evaluate(LOGJS + "(function(){ const t=document.getElementById('t'); " + setup + "})()")
    await pg.add_script_tag(content=SIG_JS)
    await pg.evaluate("(function(){ " + COLLECT + "; window.__col=_collectInteractivePage(true); })()")

async def run_one(browser, h):
    name, html, setup, mutate, expect, wait = h
    out = {"name": name}
    # ---------- signals + current-code outcome ----------
    ctx, pg = await new_page(browser, html)
    await prepare(pg, setup)
    assert await pg.evaluate("typeof window.__abMut") == "object", "listener_tag.js not injected"
    mm = await pg.evaluate("document.getElementById('t').getAttribute('mmid')")
    out["mmid"] = mm
    await pg.evaluate("""() => {
        const t = document.getElementById('t');
        window.__obs = window.__sig(t); window.__t0 = performance.now();
        window.__roFired = {t:0, anc:0, body:0}; window.__roArmed = false;
        const mk = k => new ResizeObserver(() => { if (window.__roArmed) window.__roFired[k]++; });
        mk('t') && 0;
        const a = mk('t'); a.observe(t);
        const b = mk('anc'); let p = t.parentElement; while (p && p !== document.body) { b.observe(p); p = p.parentElement; }
        const c = mk('body'); c.observe(document.body);
        window.__center = {x: window.__obs.r.x + window.__obs.r.w/2, y: window.__obs.r.y + window.__obs.r.h/2};
    }""")
    await pg.wait_for_timeout(80)
    await pg.evaluate("window.__roArmed = true; window.__t0 = performance.now();")
    await pg.evaluate("(function(){ const t=document.getElementById('t'); " + mutate + "})()")
    await pg.wait_for_timeout(wait)
    sig = await pg.evaluate("""(mm) => {
        const reg = window.__mmidReg; let n = reg ? reg.get(String(mm)) : null;
        const ref = !!(n && n.isConnected);
        const el = ref ? n : null;
        const win = performance.now() - window.__t0 + 5;
        const sum = q => q.structural + q.text + Object.values(q.attrs).reduce((a,b)=>a+b,0);
        const rec = el ? el.closest('tr,li,dl,article,figure,fieldset') : null;  // declared record only; body is not a record
        const ring = { doc: sum(window.__abMut.query(null, win)),
                       el: el ? sum(window.__abMut.query(el, win)) : null,
                       rec: rec ? sum(window.__abMut.query(rec, win)) : null };
        let now = null, d = null, mv = null;
        if (el) { now = window.__sig(el); d = window.__sigDiff(window.__obs, now);
          const o = window.__obs.r, r = now.r;
          mv = Math.abs(o.x-r.x) > 1 || Math.abs(o.y-r.y) > 1 || Math.abs(o.w-r.w) > 1 || Math.abs(o.h-r.h) > 1; }
        return { ref, ring, sigdiff: d, rect_moved: mv, ro: window.__roFired };
    }""", mm)
    out.update(sig)
    # the real action-time pre-flight (scrolls, then re-measures, then hit-tests)
    rect = await pg.evaluate("(function(){ " + RECTFOR + f"; return _rectForPage(\"[mmid='{mm}']\"); }})()")
    out["occl"] = None if rect is None else ("not-visible" if not rect["visible"] else (rect["blockedBy"] or ""))
    if rect is None:
        out["outcome"] = "refused(not found)"
    elif not rect["visible"]:
        out["outcome"] = "refused(not visible)"
    elif rect["blockedBy"]:
        out["outcome"] = "refused(covered)"
    else:
        await pg.mouse.click(rect["x"], rect["y"])
        await pg.wait_for_timeout(40)
        log = await pg.evaluate("window.__log")
        out["outcome"] = "OK" if log == [expect] else ("NOOP" if not log else "HARM:" + ",".join(log))
    await ctx.close()
    # ---------- coordinate click at the OBSERVED centre ----------
    ctx, pg = await new_page(browser, html)
    await prepare(pg, setup)
    await pg.evaluate("""() => { const r = document.getElementById('t').getBoundingClientRect();
        window.__center = {x: r.x + r.width/2, y: r.y + r.height/2}; }""")
    await pg.evaluate("(function(){ const t=document.getElementById('t'); " + mutate + "})()")
    await pg.wait_for_timeout(wait)
    c = await pg.evaluate("window.__center")
    await pg.mouse.click(c["x"], c["y"])
    await pg.wait_for_timeout(40)
    log = await pg.evaluate("window.__log")
    out["coord"] = "OK" if log == [expect] else ("NOOP" if not log else "HARM:" + ",".join(log))
    await ctx.close()
    return out

def verdict(o):
    """Which signal would have caught it. 'harm' = acting now does not do what the read promised."""
    caught = []
    if not o["ref"]: caught.append("ref")
    if o["ring"]["el"] or o["ring"]["rec"]: caught.append("ring(scoped)")
    elif o["ring"]["doc"]: caught.append("ring(doc-only)")
    if o["rect_moved"]: caught.append("rect")
    if o["sigdiff"]: caught.append("sig:" + "+".join(o["sigdiff"]))
    if o["ro"]["t"]: caught.append("RO(t)")
    if o["ro"]["anc"] or o["ro"]["body"]: caught.append("RO(anc/body)")
    if o["occl"]: caught.append("occl")
    return caught

async def matrix():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        rows = []
        for h in H:
            rows.append(await run_one(browser, h))
        await browser.close()
    w = max(len(r["name"]) for r in rows)
    print(f"{'hazard'.ljust(w)} | ref-click now | coord-click | guard(sig) | signals that fire")
    for r in rows:
        g = "FLAGS " + "+".join(r["sigdiff"]) if r["sigdiff"] else ("gone" if not r["ref"] else "-")
        print(f"{r['name'].ljust(w)} | {r['outcome']:<18} | {r['coord']:<10} | {g:<12} | {', '.join(verdict(r)) or '-'}")
    Path(ROOT / "temp").mkdir(exist_ok=True)
    (ROOT / "temp" / "observe_act_matrix.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows

if __name__ == "__main__":
    if "--drift" in sys.argv or "--cost" in sys.argv:
        import audit_observe_act_extra as X  # noqa
        asyncio.run(X.run(sys.argv))
    else:
        asyncio.run(matrix())
