"""Adversarial audit of the page-readiness signal (CLAUDE.md #15/#43/#70/#76/#77).

Builds 14 page shapes, interrogates the REAL `_readinessPage` (injected ALONE,
as executeScript({func}) ships it -- no sibling helpers prepended, #30/#77) and
renders the REAL `readinessNote` through node with `runInTab`/`_netPending`
stubbed from what Playwright observed on the wire. Reports, per shape and per
offset, every raw signal, the rendered verdict, and the error direction against
an OBJECTIVE ground truth: does the page's own content signature differ at the
end of the run from what it was at this offset?

  false quiet  = verdict claims readiness (QUIET or MINOR) and content changed later
  false busy   = verdict is the STRONG banner and content never changed again
  fb-load      = STRONG within 3000ms of load on content that never changes again (the window
                 necessarily covers the parse itself; inherent to any recency signal)
  FB-PERM      = STRONG at offset>=3500 with since<1000ms on content that never changes again
                 (steady-state live churn: the real "warn forever" noise)
  fb-tail      = STRONG with since>=1000ms: the 3000ms window still covering a FINISHED build
                 (documented cost; `since` is printed so the reader can see it)
  hedged       = DOM STABLE / NETWORK BUSY (states two facts, claims neither)

Also prototypes OPEN.md item 5(a): per-landmark attribution of the mutation ring,
as a PATCHED COPY of listener_tag.js (the real file is not edited). The copy is
asserted to be the real file plus one inserted method, so every verdict above is
produced by unmodified ring logic.

Run:  .venv/bin/python tools/audit_readiness_adversarial.py [--json out.json]
"""
import asyncio, json, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract

ROOT = Path(__file__).resolve().parent.parent
BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
TAG = (ROOT / "extension" / "listener_tag.js").read_text(encoding="utf-8")
READY = extract("_readinessPage", BG, verify=True)
NOTE = extract("readinessNote", BG, verify=True)
OFFSETS = [300, 1500, 3500, 6500]
FINAL = 9500

# ---- the prototype: one-pass region attribution, inserted into the ring API ----
REGION_SEL = ("header,nav,main,footer,aside,table,[role=banner],[role=navigation],[role=main],"
              "[role=contentinfo],[role=complementary],[role=region],[role=grid],[role=table]")
PROTO = """
      regions(winMs, sel) {
        const now = performance.now(), cut = now - (winMs || 3000);
        const out = {};
        const seen = Math.min(n, CAP);
        for (let i = 0; i < seen; i++) {
          const t = ts[i]; if (!t) continue;
          const el = tg[i] && tg[i].deref ? tg[i].deref() : null;
          let key = el ? '(none)' : '(gc)';
          let cur = el;
          for (let h = 0; cur && h < 200; h++) {
            if (cur.nodeType === 1 && cur.matches && cur.matches(sel)) {
              key = cur.tagName.toLowerCase() + (cur.id ? '#' + cur.id : ''); break; }
            cur = cur.parentNode || null;
            if (cur && cur.nodeType === 11) cur = cur.host || null;
          }
          const o = out[key] || (out[key] = { since: -1, structural: 0, text: 0, attrs: 0 });
          const age = Math.round(now - t);
          if (o.since < 0 || age < o.since) o.since = age;
          if (t < cut) continue;
          if (kd[i] === 1) o.structural++; else if (kd[i] === 2) o.text++; else o.attrs++;
        }
        return out;
      },
"""
ANCHOR = "      watch(root) {"
assert TAG.count(ANCHOR) == 1
TAG_PROTO = TAG.replace(ANCHOR, PROTO + ANCHOR)
assert TAG_PROTO.replace(PROTO, "") == TAG, "prototype must be a pure insertion"

# ---- fixtures ----------------------------------------------------------------
ROWS = "".join(f"<tr><td>r{i}</td><td>v{i}</td></tr>" for i in range(40))
STATIC_MAIN = f"<main id=m><h1>Report</h1><table id=t>{ROWS}</table></main>"
CLOCK = ("<header id=hd><span id=clk>0</span></header>")
def page(body, script="", extra_head=""):
    return (f"<!doctype html><meta charset=utf-8><style>body{{margin:8px}}{extra_head}</style>"
            f"<body>{body}<script>{script}</script></body>")

CHUNK = ("let i=0;const host=document.getElementById('{h}');(function s(){{for(let k=0;k<20&&i<400;k++,i++){{"
         "const d=document.createElement('div');d.textContent='row '+i;host.appendChild(d);}}"
         "if(i<400)setTimeout(s,100);}})();")

FIX = {}
def fx(name, html, sig, truth, **kw):
    FIX[name] = dict(html=html, sig=sig, truth=truth, **kw)

fx("01_textContent_ticker", page(CLOCK + STATIC_MAIN,
   "let c=0;setInterval(()=>{document.getElementById('clk').textContent=++c},100)"),
   "document.getElementById('m').innerText.length", "settled; ticker is header-only")
fx("02_xorigin_ad_iframe_churn", page(CLOCK + STATIC_MAIN + "<iframe src='http://ads.test/ad' width=300 height=100></iframe>"),
   "document.getElementById('m').innerText.length", "settled; churn is in a cross-origin ad")
fx("03_chunked_table_no_network", page("<main id=m><div id=h></div></main>", CHUNK.format(h="h")),
   "document.querySelectorAll('#h>div').length", "building 0-2s")
fx("04_intersectionobserver_lazy", page("<main id=m><div id=h></div></main><div style='height:4000px'></div><div id=s>end</div>",
   "const h=document.getElementById('h');for(let i=0;i<20;i++){const d=document.createElement('div');d.textContent='r'+i;h.appendChild(d)}"
   "new IntersectionObserver(es=>{if(es[0].isIntersecting){for(let i=0;i<20;i++){const d=document.createElement('div');d.textContent='more'+i;h.appendChild(d)}}}).observe(document.getElementById('s'))"),
   "document.querySelectorAll('#h>div').length", "settled until the user scrolls (no signal possible without acting)")
fx("05_skeleton_late_timer_paint", page("<main id=m><div id=content class=sk>loading skeleton</div></main>",
   "setTimeout(()=>{document.getElementById('content').textContent='REAL CONTENT '.repeat(50)},5000)",
   "@keyframes sh{from{opacity:.4}to{opacity:1}}.sk{animation:sh 1s infinite alternate}"),
   "document.getElementById('content').textContent.length", "building until 5s; nothing signals it in 0.3-5s")
fx("06_css_animation_only_settled", page(CLOCK + STATIC_MAIN,
   "", "@keyframes sh{from{background:#eee}to{background:#ccc}}#hd{animation:sh 500ms infinite alternate}"),
   "document.getElementById('m').innerText.length", "settled; animation is pure CSS")
fx("07_closed_shadow_chunked", page("<main id=m><x-feed id=f></x-feed></main>",
   "window.__cnt=0;customElements.define('x-feed',class extends HTMLElement{connectedCallback(){const r=this.attachShadow({mode:'closed'});"
   "let i=0;(function s(){for(let k=0;k<20&&i<400;k++,i++){const d=document.createElement('div');d.textContent='row '+i;r.appendChild(d);window.__cnt++}"
   "if(i<400)setTimeout(s,100)})()}})"),
   "window.__cnt", "building 0-2s inside a closed root")
fx("08_longpoll_finished_dom", page(CLOCK.replace("<span id=clk>0</span>","") + STATIC_MAIN,
   "fetch('/lp').catch(()=>{});setInterval(()=>fetch('/beacon').catch(()=>{}),150)"),
   "document.getElementById('m').innerText.length", "settled; requests pending forever")
fx("09_same_origin_iframe_paints", page("<main id=m><iframe id=fr srcdoc=\"<div id=h></div><script>"
   + CHUNK.format(h="h").replace('"', "&quot;") + "</script>\" width=600 height=300></iframe></main>"),
   "document.getElementById('fr').contentDocument.querySelectorAll('#h>div').length", "building 0-2s in same-origin frame")
fx("10_xorigin_iframe_paints", page("<main id=m><iframe src='http://other.test/f' width=600 height=300></iframe></main>"),
   "@frame:other.test|document.querySelectorAll('#h>div').length", "building 0-2s in cross-origin frame (stated limit)")
fx("11_virtualised_live_grid", page(CLOCK.replace("<span id=clk>0</span>","") + "<main id=m><div id=g></div></main>",
   "const g=document.getElementById('g');for(let i=0;i<30;i++){const d=document.createElement('div');d.className='row';d.dataset.k=i;g.appendChild(d)}"
   "let c=0;setInterval(()=>{c++;g.querySelectorAll('.row').forEach((d,i)=>d.textContent='$'+(i*7+c))},100)"),
   "document.querySelectorAll('#g>.row').length", "settled structurally; values change forever by design")
fx("12_attr_carousel_static_content", page(CLOCK + STATIC_MAIN + "<div id=car style='width:50px;height:20px'></div>",
   "let c=0;setInterval(()=>{document.getElementById('car').style.marginLeft=(++c%50)+'px'},100)"),
   "document.getElementById('m').innerText.length", "settled; carousel is attribute-only")
fx("13_clock_plus_building_table", page(CLOCK + "<main id=m><div id=h></div></main>",
   "let c=0;setInterval(()=>{document.getElementById('clk').textContent=++c},100);" + CHUNK.format(h="h")),
   "document.querySelectorAll('#h>div').length", "header ticks forever; main building 0-2s")
fx("14_skeleton_late_fetch", page("<main id=m><div id=content>loading</div></main>",
   "fetch('/slow5').then(r=>r.text()).then(t=>{document.getElementById('content').textContent='DATA '.repeat(50)})"),
   "document.getElementById('content').textContent.length", "building until 5s; network in flight")

SLOW = ("let i=0;const host=document.getElementById('h');(function s(){for(let k=0;k<20&&i<400;k++,i++){"
        "const d=document.createElement('div');d.textContent='row '+i;host.appendChild(d);}"
        "if(i<400)setTimeout(s,400);})();")
fx("15_late_xorigin_iframe_slow_paint", page("<main id=m><div id=slot></div></main>",
   "setTimeout(()=>{const f=document.createElement('iframe');f.src='http://slow.test/f';f.width=600;f.height=300;document.getElementById('slot').appendChild(f)},500)"),
   "@frame:slow.test|document.querySelectorAll('#h>div').length", "iframe inserted at .5s then paints 0.9-8.9s; CROSS-origin: top ring sees only the insertion")
fx("16_late_sameorigin_iframe_slow_paint", page("<main id=m><div id=slot></div></main>",
   "setTimeout(()=>{const f=document.createElement('iframe');f.src='/same/f';f.id='fr';f.width=600;f.height=300;document.getElementById('slot').appendChild(f)},500)"),
   "(document.getElementById('fr')&&document.getElementById('fr').contentDocument&&document.getElementById('fr').contentDocument.querySelectorAll('#h>div').length)||0", "control for 15: same shape, same-origin")
fx("17_slow_chunked_table_400ms", page("<main id=m><div id=h></div></main>", SLOW),
   "document.querySelectorAll('#h>div').length", "building at 400ms commits for 8s: tab-throttle regime")
fx("18_slow_chunked_closed_shadow", page("<main id=m><x-feed id=f></x-feed></main>",
   "window.__cnt=0;customElements.define('x-feed',class extends HTMLElement{connectedCallback(){const r=this.attachShadow({mode:'closed'});"
   "let i=0;(function s(){for(let k=0;k<20&&i<400;k++,i++){const d=document.createElement('div');d.textContent='row '+i;r.appendChild(d);window.__cnt++}"
   "if(i<400)setTimeout(s,400)})()}})"),
   "window.__cnt", "closed-root rows appended DIRECTLY to the root, 400ms commits")

# 19/20 are the TEXT-TIER controls (see audit_retext_tier.py). The set had no
# shape that is sampled WHILE content arrives as text and none where a
# `textContent =` DESTROYS elements, so a reclassification of text-node childList
# records could have been called safe on a corpus that never put it under load.
fx("19_text_only_arrival_inflight", page(
   "<main id=m>" + "".join(f"<div class=slot id=s{i}></div>" for i in range(20)) + "</main>",
   "let i=0;(function s(){const e=document.getElementById('s'+i);"
   "if(e)e.textContent='DATA '.repeat(20);if(++i<20)setTimeout(s,400);})();"),
   "document.getElementById('m').innerText.length",
   "content arrives ONLY as textContent on existing divs, 0-8s: every offset is mid-arrival")
fx("20_textContent_destroys_controls", page(
   "<main id=m><div id=box>" + "<button>b</button>" * 10 + "</div></main>",
   "setTimeout(()=>{document.getElementById('box').textContent='gone'},2000)"),
   "document.querySelectorAll('#box button').length",
   "a textContent= that REMOVES 10 real controls: the record carries elements, so it is structural")

# 21 is the shape the set never had: an ATTRIBUTE-only page (so the verdict is
# MINOR, which claims "the listing below is structurally current") that ALSO has
# a cross-origin frame still painting. `_withBlind` rides the two QUIET paths and
# not this one, so the structural claim is made with no caveat. The frame sits
# OUTSIDE <main> on purpose, so the same shape also asks whether a SCOPED read
# names a frame it deliberately excluded -- the page-level-fact leak #11 and #26
# both had to stop, which the network clause in this same banner avoids by saying
# PAGE-WIDE and this one does not.
fx("21_attr_only_plus_blind_frame", page(
   CLOCK.replace("<span id=clk>0</span>", "") + STATIC_MAIN
   + "<div id=car style='width:50px;height:20px'></div>"
   + "<footer><iframe src='http://ads.test/ad' width=300 height=100></iframe></footer>",
   "let c=0;setInterval(()=>{document.getElementById('car').style.marginLeft=(++c%50)+'px'},100)"),
   "document.getElementById('m').innerText.length",
   "settled; carousel is attribute-only AND a cross-origin frame churns outside main")

async def route_all(ctx, name, html):
    async def h(route):
        u = route.request.url
        if u.endswith("/lp"):
            await asyncio.sleep(25)
            try: await route.fulfill(status=200, body="x")
            except Exception: pass
        elif u.endswith("/slow5"):
            await asyncio.sleep(5)
            await route.fulfill(status=200, body="x")
        elif "ads.test" in u:
            await route.fulfill(status=200, content_type="text/html", body=page("<div id=a></div>",
                "let c=0;setInterval(()=>{document.getElementById('a').textContent='AD '+(++c)},60)"))
        elif u.endswith("/same/f"):
            await route.fulfill(status=200, content_type="text/html", body=page("<div id=h></div>", SLOW))
        elif "slow.test" in u:
            await route.fulfill(status=200, content_type="text/html", body=page("<div id=h></div>", SLOW))
        elif "other.test" in u:
            await route.fulfill(status=200, content_type="text/html", body=page("<div id=h></div>", CHUNK.format(h="h")))
        elif u.endswith("/beacon"):
            await route.fulfill(status=200, body="x")
        else:
            await route.fulfill(status=200, content_type="text/html", body=html)
    await ctx.route("**/*", h)

TYPE = {"fetch": "xmlhttprequest", "xhr": "xmlhttprequest", "document": "main_frame",
        "image": "image", "script": "script", "stylesheet": "stylesheet"}

async def run_one(browser, name, f, sem):
    async with sem:
        ctx = await browser.new_context(viewport={"width": 900, "height": 700})
        await ctx.add_init_script(TAG_PROTO)
        await route_all(ctx, name, f["html"])
        pg = await ctx.new_page()
        pend = {}
        pg.on("request", lambda r: pend.__setitem__(id(r), TYPE.get(r.resource_type, r.resource_type)) if r.resource_type != "document" else None)
        for ev in ("requestfinished", "requestfailed"):
            pg.on(ev, lambda r: pend.pop(id(r), None))
        await pg.goto("http://app.test/", wait_until="domcontentloaded")
        SC = {"main": "main", "host": "x-feed"}
        for key, sel in SC.items():
            await pg.evaluate("([s,k])=>{const e=document.querySelector(s);if(e)e.setAttribute('mmid',k)}", [sel, "9" + key])
        t0 = time.monotonic()

        async def sig():
            s = f["sig"]
            try:
                if s.startswith("@frame:"):
                    host, expr = s[7:].split("|", 1)
                    for fr in pg.frames:
                        if host in fr.url: return await fr.evaluate(expr)
                    return None
                return await pg.evaluate(s)
            except Exception as e:
                return f"ERR {e}"
        rows = []
        for off in OFFSETS:
            await pg.wait_for_timeout(max(0, off - (time.monotonic() - t0) * 1000))
            # the signature is read BEFORE the probe so both describe one instant
            sg = await sig()
            r = await pg.evaluate("(function(){ " + READY + "; return _readinessPage(); })()")
            scoped = {}
            for key in SC:
                scoped[key] = await pg.evaluate("(m)=>{ " + READY + "; return _readinessPage(m); }", "9" + key)
            regs = await pg.evaluate("([w,s])=>window.__abMut.regions(w,s)", [3000, REGION_SEL])
            rows.append(dict(off=off, sig=sg, r=r, scoped=scoped, net=dict(_count(pend)), regions=regs))
        await pg.wait_for_timeout(max(0, FINAL - (time.monotonic() - t0) * 1000))
        final = await sig()
        # scoped-to-main read, taken at the end of each offset is not possible
        # post hoc; instead take one scoped probe per offset in a second pass is
        # impossible too, so scoped answers are measured in a dedicated run below.
        await ctx.close()
        return dict(name=name, truth=f["truth"], rows=rows, final=final)

def _count(pend):
    c = {}
    for t in pend.values():
        if t in ("websocket", "media"): continue
        c[t] = c.get(t, 0) + 1
    return c

NODE_HARNESS = r"""
const fs=require('fs');const inp=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const NOTE_SRC=fs.readFileSync(process.argv[3],'utf8');
let R=null;const _netPending=new Map();function _readinessPage(){}
async function runInTab(){return R;}
eval(NOTE_SRC+';globalThis.readinessNote=readinessNote;');
(async()=>{const out=[];for(const it of inp){R=it.r;const m=new Map();let i=0;
 for(const [k,n] of Object.entries(it.net))for(let j=0;j<n;j++)m.set(i++,k);
 _netPending.set(1,m);out.push(await globalThis.readinessNote(1,it.scope??undefined));}
 console.log(JSON.stringify(out));})();
"""

def render(items):
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "in.json").write_text(json.dumps(items)); (d / "note.js").write_text(NOTE)
        (d / "h.js").write_text(NODE_HARNESS)
        o = subprocess.run(["node", str(d / "h.js"), str(d / "in.json"), str(d / "note.js")],
                           capture_output=True, text=True)
        if o.returncode: raise SystemExit(o.stderr)
        return json.loads(o.stdout)

def classify(n):
    if not n: return "QUIET"
    if "STILL CHANGING" in n: return "STRONG"
    # The TEXT tier: no element was added or removed, but words inside existing
    # elements changed. A WARNING tier, not a quiet one -- it is counted as a
    # false quiet nowhere below, and by construction it can only ever receive
    # reads that were STRONG before.
    if "TEXT IS CHANGING" in n: return "TEXT"
    if "Minor DOM activity" in n: return "MINOR"
    if "DOM STABLE" in n: return "DOMSTABLE"
    if "could be attributed" in n: return "UNKNOWN"
    # The cross-origin-frame clause (#82) rides the QUIET paths only, so a note
    # that is ONLY that clause is the answer to "quiet, but I could not see
    # everything". It is NOT a false quiet: it states the limit and says
    # explicitly that it does not mean the content has arrived. Classed before
    # FADE because the fade sentence can ride along and this is the one that
    # bears on the readiness question.
    if "cross-origin frame(s) are rendered" in n: return "BLIND"
    if "STILL SETTLING" in n: return "SETTLING"
    if "held at opacity" in n: return "FADE"
    return "OTHER"

async def cost_probe(browser):
    """Re-earn cost with a ring that is REALLY saturated (wrote > CAP), a 25-deep
    scope chain, timing 200-call batches so Chrome's 0.1ms timer granularity
    cannot hide the number, arms interleaved x5."""
    ctx = await browser.new_context()
    await ctx.add_init_script(TAG_PROTO)
    await ctx.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html",
        body=page("<header id=hd></header><main id=m><div id=h></div></main>")))
    pg = await ctx.new_page(); await pg.goto("http://cost.test/")
    res = await pg.evaluate("""async ([sel])=>{
      let h=document.getElementById('h'); for(let d=0;d<25;d++){const x=document.createElement('div');h.appendChild(x);h=x;}
      const mc=new MessageChannel(); const tick=()=>new Promise(r=>{mc.port1.onmessage=()=>r();mc.port2.postMessage(0)});
      for(let i=0;i<1300;i++){h.appendChild(document.createElement('p'));await tick();await Promise.resolve();}
      const per=(fn,n)=>{const t=performance.now();for(let i=0;i<n;i++)fn();return (performance.now()-t)/n;};
      const q=window.__abMut.query(null,3000);
      const A=[],B=[],S=[],L5=[],L30=[];
      const scope=h.parentElement;
      // design 2: enumerate landmarks, then one SCOPED query each (no ring change needed)
      const lm=(n)=>{const els=[...document.querySelectorAll(sel)]; while(els.length<n){const d=document.createElement('section');d.setAttribute('role','region');document.body.appendChild(d);els.push(d);} return els.slice(0,n);};
      const L5s=lm(5), L30s=lm(30);
      const perLm=(els)=>per(()=>{const o={};for(const e of els)o[e.tagName]=window.__abMut.query(e,3000);return o;},50);
      for(let k=0;k<5;k++){A.push(per(()=>window.__abMut.query(null,3000),200));
        S.push(per(()=>window.__abMut.query(scope,3000),200));
        B.push(per(()=>window.__abMut.regions(3000,sel),200));
        L5.push(perLm(L5s)); L30.push(perLm(L30s));}
      return {saturated:q.saturated,total:q.total,query_ms:A,scoped_query_ms:S,regions_ms:B,per_landmark_5_ms:L5,per_landmark_30_ms:L30};}""", [REGION_SEL])
    await ctx.close(); return res

# ---- PATCH A: a ShadowRoot is not an Element, so its own direct children were never attributable
# SHIPPED (CLAUDE.md #82, pinned by R25c/R25d). This block used to carry the
# experiment; it now carries the ASSERTION that the fix is still in the file,
# because this probe's own numbers were produced against the patched ring and a
# silent revert would make every verdict below describe a build nobody ships.
# The probe ALSO refused to run when the fix landed -- the assertion fired, which
# is a detector doing its job rather than skipping (PRINCIPLES 15). The arm is
# kept so the before/after can still be produced on demand.
PATCH_A_NEW = "const el = r.target && r.target.nodeType === 1 ? r.target\n          : (r.target && (r.target.parentElement || r.target.host || null));"
PATCH_A_OLD = "const el = r.target && r.target.nodeType === 1 ? r.target\n          : (r.target && r.target.parentElement);"
assert TAG.count(PATCH_A_NEW) == 1, "Patch A (ShadowRoot -> host) is not in listener_tag.js"
TAG_UNPATCHED = TAG_PROTO.replace(PATCH_A_NEW, PATCH_A_OLD)
assert TAG_UNPATCHED != TAG_PROTO

async def patch_a(browser):
    out = {}
    for variant, tag in (("shipped", TAG_PROTO), ("pre-fix", TAG_UNPATCHED)):
        for mode in ("closed", "open"):
            ctx = await browser.new_context(viewport={"width": 900, "height": 700})
            await ctx.add_init_script(tag)
            html = page("<main id=m><x-feed id=f></x-feed></main><footer id=ft>f</footer>",
               "customElements.define('x-feed',class extends HTMLElement{connectedCallback(){const r=this.attachShadow({mode:'%s'});"
               "let i=0;(function s(){for(let k=0;k<20&&i<400;k++,i++){const d=document.createElement('div');d.textContent='row '+i;r.appendChild(d)}"
               "if(i<400)setTimeout(s,400)})()}})" % mode)
            def _mk(h):
                return lambda route: route.fulfill(status=200, content_type="text/html", body=h)
            await ctx.route("**/*", _mk(html))
            pg = await ctx.new_page(); await pg.goto("http://pa.test/")
            await pg.evaluate("()=>{document.querySelector('main').setAttribute('mmid','9main');document.querySelector('x-feed').setAttribute('mmid','9host');document.querySelector('footer').setAttribute('mmid','9foot')}")
            await pg.wait_for_timeout(4000)   # window cleared of the parse, shadow still painting
            res = {}
            for k in ("9main", "9host", "9foot"):
                r = await pg.evaluate("(m)=>{ " + READY + "; return _readinessPage(m); }", k)
                res[k] = r["mut"] and dict(since=r["mut"]["since"], sinceAny=r["mut"]["sinceAny"], structural=r["mut"]["structural"])
            out[f"{variant}/{mode}"] = res
            await ctx.close()
    return out

async def main():
    out_json = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        sem = asyncio.Semaphore(5)
        results = await asyncio.gather(*[run_one(browser, n, f, sem) for n, f in FIX.items()])
        cost = await cost_probe(browser)
        pa = await patch_a(browser)
        await browser.close()
    items = []
    for res in results:
        for row in res['rows']:
            items.append(dict(r=row['r'], net=row['net']))
            for key in ('main', 'host'):
                items.append(dict(r=row['scoped'][key], net=row['net'], scope='9' + key))
    notes = render(items); k = 0
    sc_stats = {'main': [0, 0, 0], 'host': [0, 0, 0]}
    fq = fb = hed = unk = tail = load = blind = 0
    print(f"{'shape':32} {'off':>5} {'net':>14} bsy prog img  mut(since/str/txt/attrs/frames)  verdict    sig  later?  err")
    for res in results:
        for row in res["rows"]:
            note = notes[k]; k += 1
            row["scoped_notes"] = {}
            for key in ("main", "host"):
                row["scoped_notes"][key] = classify(notes[k]); k += 1
            v = classify(note); row["verdict"] = v; row["note"] = note
            row["blind"] = "cross-origin frame(s) are rendered" in (note or "")
            m = row["r"].get("mut") or {}
            changes_later = (row["sig"] != res["final"])
            err = ""
            if v == "BLIND" and changes_later: err = "blind-stated"; blind += 1
            elif v in ("QUIET", "MINOR") and changes_later: err = "FALSE-QUIET"; fq += 1
            elif v == "STRONG" and not changes_later:
                if row["off"] < 3000: err = "fb-load"; load += 1       # page parsed <3s ago: inherent
                elif m.get("since", 0) < 1000: err = "FB-PERM"; fb += 1  # steady-state live churn
                else: err = "fb-tail"; tail += 1
            elif v in ("DOMSTABLE", "SETTLING") and changes_later: err = "hedged-ok"; hed += 1
            elif v in ("DOMSTABLE", "SETTLING") and not changes_later: err = "hedged-noise"; hed += 1
            row["err"] = err; row["changes_later"] = changes_later
            print(f"{res['name']:32} {row['off']:>5} {str(row['net']):>14} {row['r']['busy']:>3} {row['r']['prog']:>4} {row['r']['imgs']:>3}  "
                  f"{m.get('since')}/{m.get('structural')}/{m.get('text')}/{sum(m.get('attrs',{}).values())}/{m.get('frames',0)}".ljust(40)
                  + f" {v:9} {str(row['sig'])[:6]:>6} {str(changes_later):6} {err:11} scoped main={row['scoped_notes']['main']} host={row['scoped_notes']['host']}")
    sfq = {"main": 0, "host": 0}; sunk = 0
    for res in results:
        for row in res["rows"]:
            for key in ("main", "host"):
                if row["scoped_notes"][key] in ("QUIET", "MINOR") and row["changes_later"]:
                    sfq[key] += 1
                    if key == "main": print("  SCOPED-FALSE-QUIET", res["name"], row["off"], "main")
    print(f"\nSCOPED false-quiet (main/host): {sfq}")
    print(f"\nFALSE-QUIET={fq}  blind-stated={blind}  FB-PERM={fb}  fb-tail={tail}  fb-load={load}  hedged={hed}")
    print("\nREGION ATTRIBUTION (item 5a prototype), per shape/offset: region=since/struct/text/attrs")
    for res in results:
        for row in res["rows"]:
            print(f"{res['name']:32} {row['off']:>5} " + "  ".join(
                f"{k}={v['since']}/{v['structural']}/{v['text']}/{v['attrs']}" for k, v in sorted(row["regions"].items())))
    print("\nCOST (saturated ring, 25-deep, ms/call, 5 interleaved x200):"); print(json.dumps(cost))
    print("\nPATCH A (shadow-root direct children attributable to host), scoped reads at +4s while painting:")
    for k, v in pa.items(): print(" ", k, json.dumps(v))
    if out_json:
        Path(out_json).write_text(json.dumps(dict(results=results, cost=cost, patch_a=pa), indent=1))

# GUARDED so the 18 fixtures, the routing table and the ground-truth signatures
# can be IMPORTED by a sibling probe rather than copied. A second copy of this
# corpus would drift from this one (PRINCIPLES 17), and the whole point of a
# shape set is that two probes answering different questions answer them about
# the same pages.
if __name__ == "__main__":
    asyncio.run(main())
