"""Page-level scans and the iframe boundary -- exposure, and what a fix would cost.

`docs/OPEN.md` item 7. THE ITEM'S PREMISE IS HALF WRONG AND THIS FILE IS WHY.
`dialogOpen` queries `_allComposed`, which iterates `mmidReg` -- and the
collection walk stamps mmids ACROSS SAME-ORIGIN FRAME BOUNDARIES. So:

  same-origin frames  ARE reached by the page-level scans. What is broken there
                      is GEOMETRY: `dialogOpen` compares a frame-relative
                      getBoundingClientRect() against the TOP window's
                      innerWidth/innerHeight, so a full-bleed dialog inside a
                      760x420 frame measures 15.6% of "the viewport" and misses
                      the >=50% dominates-the-viewport branch. The same dialog
                      in a viewport-sized frame fires, because the two
                      coordinate systems happen to coincide.
  cross-origin frames are invisible to all of it. `collectCrossFrames` runs
                      AFTER `_collectInteractivePage` has already produced the
                      banner and simply APPENDS rows, so no cross-frame dialog
                      can ever raise it.

MEASURED, 96 usable frozen sites (2026-11-15):
  pages with >=1 child frame            42/96 (43.8%), 128 frames
  pages with >=1 RENDERED frame (>=30px) 17/96 (17.7%), 33 frames
  rendered-frame origin mix             21 cross / 7 same / 5 about
  frames declaring ANY page-level trigger        0 / 128
  per-frame collector injection         median 14ms, p90 18ms, max 377ms
  per-frame readiness probe             median 1ms, max 24ms
  top-level collector (reference)       median 66ms

THE ZERO IS REAL AND THE CORPUS CANNOT SPEAK FOR IT -- both halves matter.
The probe is verified firing: the SAME census over the TOP documents of the
same pages finds 91 dialog nodes on 31 sites, 15 with a visible dialog, 7
aria-modal, 1 progressbar, 1 aria-busy. And the corpus structurally cannot hold
the shape: HARs are captured AFTER consent, 21 of 128 frames fail to replay at
all (they come back chrome-error), and the one CMP-shaped frame that IS present
-- theguardian's full-viewport sourcepoint iframe -- declares its `role=dialog`
`aria-modal` wrapper in the TOP document, so the gap does not bite there.
That is MEASUREMENT.md R2: an ablation measures the code against the sample.

So `--fixtures` builds the shapes the corpus cannot contain, from TWO ports so
cross-origin is real rather than simulated. Results (2026-11-15):

  frame content                              top banner   frame's own banner
  same-origin CMP, 760x420 frame                 NO             yes
  same-origin CMP, viewport-sized frame          yes            yes
  CROSS-origin CMP, viewport-sized frame         NO             yes
  CROSS-origin CMP as full-page fixed overlay    NO             yes
  CROSS-origin checkout, showModal()             NO             yes
  same-origin focus-trap (aria-hidden sibs)      yes            yes
  same-origin progressbar + aria-busy        readiness SEES it  --
  CROSS-origin progressbar + aria-busy       readiness MISSES it --

Rows 1 and 2 are the SAME markup on the SAME origin with ONE variable changed —
the iframe's size — so the geometric mis-measurement is isolated rather than
argued. The dialog node is collected in both (it has a tree row either way).

AND `section=dialog` IS ON ZERO ROWS IN ALL NINE, including the three where
the banner correctly fires: an in-frame dialog's controls resolve to
`section=iframe`, because the section walk crosses the frame boundary into the
`<iframe>` element and stops there. That extends CLAUDE.md #23's open
`section=` item across the frame boundary. In the TREE format the banner points
at "the dialog node below" and that row does exist, so the instruction is still
satisfiable; in `format="flat"` the banner says "focus on elements with
section=dialog" and nothing carries it.

The full-page-overlay row is the sharpest: the top listing shows the page's own
5 controls as actionable, with no occlusion flag and no mention of the consent
dialog, while the same-origin version correctly raises the banner, quotes the
dialog text and omits the 5 underlying controls by name.

COST, and it is not what the item assumes. `collectCrossFrames` ALREADY calls
`runInTab(tabId, _collectInteractivePage, [true], fid)` for every top-level
non-`about:` child frame on every unscoped string read -- measured at
**27 of the 33 rendered frames (81.8%)**, the other 6 being 5 `about:` frames
and 1 nested one. The per-frame round trip the "expensive" option would add is
therefore ALREADY BEING PAID; what is missing is that it calls the STRUCTURED
arm, which returns no modal verdict, and that it appends its rows AFTER the
banner has already been built. The "free" same-origin `contentDocument` option
reaches only 12 of 33 rendered frames (36.4%) -- it misses the cross-origin
case, which is where consent CMPs and embedded checkouts actually live.

Run:
    python tools/audit_frames.py              # the corpus sweep
    python tools/audit_frames.py --fixtures   # the constructed shapes
    python tools/audit_frames.py --only guardian,naver
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from playwright.async_api import async_playwright

ROOT = Path("/Users/aryangurav/Desktop/ChromeBridge")
FROZEN = ROOT / "temp" / "frozen"
sys.path.insert(0, str(ROOT / "tools"))
from _extract import extract  # noqa: E402

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = extract("_collectInteractivePage", BG, verify=False)
READY = extract("_readinessPage", BG, verify=False)
TAG_JS = str(ROOT / "extension" / "listener_tag.js")
VIEWPORT = {"width": 1280, "height": 1600}
BANNER = "A MODAL/DIALOG IS CURRENTLY OPEN"
SHELL_MIN = 30          # the same bound _frameShellsPage uses

# The five things a page-level scan looks at, asked WITHOUT running the
# collector -- a cheap census that says what is in there even when the
# collector declines to call it modal.
TRIGGERS = r"""
(function () {
  const out = { dialogNodes: 0, visibleDialog: 0, ariaModal: 0, nativeModal: 0,
                progressbar: 0, ariaBusy: 0, siblingTrap: 0, dominating: 0,
                inertBg: 0, samples: [] };
  const vis = (el) => {
    try {
      const r = el.getBoundingClientRect();
      if (!(r.width > 0 && r.height > 0)) return false;
      if (el.checkVisibility &&
          !el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) return false;
      return true;
    } catch (e) { return false; }
  };
  // Composed walk, so a dialog inside a shadow root counts -- the collector's
  // own _allComposed crosses shadow roots, and only the FRAME boundary is at
  // issue here.
  const all = [];
  const walk = (root, d) => {
    if (d > 8) return;
    let els = [];
    try { els = root.querySelectorAll('*'); } catch (e) { return; }
    for (const e of els) {
      all.push(e);
      const sr = e.shadowRoot || e.__abClosedRoot;
      if (sr) walk(sr, d + 1);
    }
  };
  try { walk(document, 0); } catch (e) {}
  const vw = innerWidth, vh = innerHeight;
  for (const el of all) {
    let role = '', tag = (el.tagName || '').toLowerCase();
    try { role = el.getAttribute('role') || ''; } catch (e) {}
    const isDlg = role === 'dialog' || role === 'alertdialog' || tag === 'dialog' ||
                  (el.getAttribute && el.getAttribute('aria-modal') === 'true');
    if (isDlg) {
      out.dialogNodes++;
      if (vis(el)) {
        out.visibleDialog++;
        if (el.getAttribute('aria-modal') === 'true') out.ariaModal++;
        try { if (el.matches(':modal')) out.nativeModal++; } catch (e) {}
        const r = el.getBoundingClientRect();
        let cs; try { cs = getComputedStyle(el); } catch (e) { cs = {}; }
        if ((r.width * r.height) / (vw * vh) >= 0.5 &&
            r.left <= vw / 2 && r.right >= vw / 2 &&
            r.top <= vh / 2 && r.bottom >= vh / 2 &&
            /^(fixed|absolute|sticky)$/.test(cs.position || '')) out.dominating++;
        let n = el;
        for (let up = 0; up < 4 && n && n.parentElement; up++, n = n.parentElement) {
          let hid = 0, sibs = 0;
          for (const s of n.parentElement.children) {
            if (s === n) continue;
            sibs++;
            if (s.getAttribute && (s.getAttribute('aria-hidden') === 'true' ||
                                   s.hasAttribute('inert'))) hid++;
          }
          if (sibs > 0 && hid === sibs) { out.siblingTrap++; break; }
        }
        if (out.samples.length < 6) {
          out.samples.push({
            tag: tag, role: role || null,
            ariaModal: el.getAttribute('aria-modal'),
            w: Math.round(r.width), h: Math.round(r.height),
            cls: (typeof el.className === 'string' ? el.className : '').slice(0, 80),
            txt: (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 70),
          });
        }
      }
    }
    if (role === 'progressbar' && vis(el)) out.progressbar++;
    try { if (el.getAttribute('aria-busy') === 'true' && vis(el)) out.ariaBusy++; } catch (e) {}
  }
  try { if (document.body && document.body.hasAttribute('inert')) out.inertBg++; } catch (e) {}
  out.anyTrigger = (out.visibleDialog + out.progressbar + out.ariaBusy) > 0;
  return out;
})()
"""


def origin_of(u: str) -> str:
    try:
        p = urlparse(u)
        if p.scheme in ("about", "data", "blob", "javascript", ""):
            return f"{p.scheme}:"
        return f"{p.scheme}://{p.netloc}"
    except Exception:
        return "?"


async def run_site(browser, name: str, url: str) -> dict:
    ctx = await browser.new_context(viewport=VIEWPORT)
    try:
        await ctx.add_init_script(path=TAG_JS)
        har = FROZEN / f"{name}.har"
        if not har.exists():
            return {"name": name, "skipped": "no recording"}
        await ctx.route_from_har(str(har), not_found="abort")
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        try:
            await page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass
        await page.wait_for_timeout(900)

        top_origin = origin_of(page.url)
        res: dict = {"name": name, "url": page.url, "top_origin": top_origin}

        # What the listing says TODAY, same page load.
        t0 = time.time()
        listing = await page.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage("
            "false, null, 'compact', false, false, 'tree'); })()") or ""
        res["top_ms"] = round((time.time() - t0) * 1000)
        res["top_chars"] = len(listing)
        res["top_banner"] = BANNER in listing
        # ROWS ONLY. A bare `"section=dialog" in listing` matches the BANNER's own
        # instruction sentence ("focus on elements with section=dialog"), so it
        # reported True on pages where no row carried the notation -- which is
        # the thing worth knowing, since an in-frame dialog's controls resolve to
        # `section=iframe` and never `section=dialog` (CLAUDE.md #23's open item,
        # extended across the frame boundary). Measured: 0 rows in all 9 fixtures.
        res["top_section_dialog"] = any(
            "section=dialog" in ln for ln in listing.splitlines()
            if ln.strip().startswith("ref_"))
        res["top_triggers"] = await page.evaluate(TRIGGERS)
        t0 = time.time()
        res["top_ready"] = await page.evaluate(
            "(function(){ " + READY + "; return _readinessPage(); })()")
        res["top_ready_ms"] = round((time.time() - t0) * 1000)

        frames = [f for f in page.frames if f != page.main_frame]
        res["n_frames"] = len(frames)
        rows = []
        for fr in frames:
            row = {"url": (fr.url or "")[:160], "origin": origin_of(fr.url)}
            row["cross_origin"] = (row["origin"] != top_origin
                                   and not row["origin"].startswith("about:"))
            # A THIRD-PARTY FRAME IS THE ONE MOST LIKELY NOT TO BE IN THE HAR.
            # route_from_har(not_found="abort") turns it into chrome-error, so
            # the corpus systematically UNDER-represents exactly the shape this
            # item is about. Counted rather than silently averaged in (R2).
            row["replay_failed"] = row["origin"].startswith("chrome-error")
            # Frame SHELL rect, read from the PARENT side so it works cross-origin.
            try:
                fe = await fr.frame_element()
                box = await fe.bounding_box()
                row["shell"] = ({"w": round(box["width"]), "h": round(box["height"]),
                                 "x": round(box["x"]), "y": round(box["y"])}
                                if box else None)
            except Exception as e:
                row["shell"] = None
                row["shell_err"] = str(e)[:60]
            s = row.get("shell")
            row["shell_real"] = bool(s and s["w"] >= SHELL_MIN and s["h"] >= SHELL_MIN)
            row["shell_share"] = (round((s["w"] * s["h"]) /
                                        (VIEWPORT["width"] * VIEWPORT["height"]), 4)
                                  if s else None)
            try:
                row["triggers"] = await fr.evaluate(TRIGGERS)
            except Exception as e:
                row["triggers"] = None
                row["trig_err"] = str(e)[:80]
            # THE FIX, SIMULATED: the real collector injected into this frame.
            try:
                t0 = time.time()
                fl = await fr.evaluate(
                    "(function(){ " + COLLECT + "; return _collectInteractivePage("
                    "false, null, 'compact', false, false, 'tree'); })()") or ""
                row["inject_ms"] = round((time.time() - t0) * 1000)
                row["frame_banner"] = BANNER in fl
                row["frame_chars"] = len(fl)
            except Exception as e:
                row["inject_ms"] = None
                row["frame_banner"] = None
                row["inject_err"] = str(e)[:80]
            try:
                t0 = time.time()
                row["frame_ready"] = await fr.evaluate(
                    "(function(){ " + READY + "; return _readinessPage(); })()")
                row["ready_ms"] = round((time.time() - t0) * 1000)
            except Exception as e:
                row["frame_ready"] = None
                row["ready_err"] = str(e)[:60]
            rows.append(row)
        res["frames"] = rows
        return res
    except Exception as e:
        return {"name": name, "skipped": str(e)[:140]}
    finally:
        await ctx.close()


def load_sites() -> list[tuple[str, str]]:
    src = (ROOT / "tools" / "capture_listings.py").read_text(encoding="utf-8")
    body = src[src.index("SITES = ["):src.index("\nOUT = ")]
    return re.findall(r'\(\s*"([a-z_0-9]+)"\s*,\s*"(https?://[^"]+)"', body)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=str(ROOT / "temp" / "frames_results.json"))
    ap.add_argument("--fixtures", action="store_true",
                    help="build the shapes the frozen corpus cannot contain")
    args = ap.parse_args()
    if args.fixtures:
        await fixtures_main()
        return
    sites = load_sites()
    if args.only:
        want = set(args.only.split(","))
        sites = [s for s in sites if s[0] in want]
    if args.limit:
        sites = sites[:args.limit]
    rows, t0 = [], time.time()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for n, u in sites:
            r = await run_site(browser, n, u)
            rows.append(r)
            if "skipped" in r:
                print(f"  SKIP {n}: {r['skipped']}", flush=True)
            else:
                trip = sum(1 for f in r["frames"] if f.get("frame_banner"))
                trg = sum(1 for f in r["frames"]
                          if (f.get("triggers") or {}).get("anyTrigger"))
                print(f"  {n}: frames={r['n_frames']} real="
                      f"{sum(1 for f in r['frames'] if f['shell_real'])} "
                      f"triggers={trg} frame_banner={trip} "
                      f"top_banner={r['top_banner']}", flush=True)
        await browser.close()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print(f"\n{len(rows)} sites in {time.time()-t0:.0f}s -> {args.out}")





PORT_A, PORT_B = 8931, 8932

TOP = """<!doctype html><html><head><meta charset=utf-8><title>Top</title></head><body>
<h1>Shop</h1>
<nav><a href="/a">Home</a> <a href="/b">Cart</a> <a href="/c">Help</a></nav>
<main><button id="buy">Buy now</button> <input name=q placeholder="Search"></main>
<iframe src="%SRC%" width="%W%" height="%H%" style="border:0;%STY%"></iframe>
</body></html>"""

CMP = """<!doctype html><html><head><meta charset=utf-8><title>Consent</title></head><body>
<div role="dialog" aria-modal="true" aria-label="Privacy preferences"
     style="position:fixed;inset:0;background:#fff;padding:20px">
  <h2>We value your privacy</h2>
  <p>We and our partners use cookies.</p>
  <button id="accept">Accept all</button>
  <button id="reject">Reject all</button>
  <button id="manage">Manage options</button>
</div></body></html>"""

CHECKOUT = """<!doctype html><html><head><meta charset=utf-8><title>Checkout</title></head><body>
<dialog id="d" style="width:600px;height:320px">
  <h2>Confirm payment</h2>
  <label>Card <input id="card" name="card"></label>
  <button id="pay">Pay $40.00</button>
  <button id="cancel">Cancel</button>
</dialog>
<script>document.getElementById('d').showModal();</script>
</body></html>"""

BUSY = """<!doctype html><html><head><meta charset=utf-8><title>Loading</title></head><body>
<div aria-busy="true" style="padding:18px">
  <div role="progressbar" aria-valuenow="40" aria-valuemin="0" aria-valuemax="100"
       style="width:300px;height:22px;background:#eee">40%</div>
  <p>Loading your order…</p>
  <button id="cancel2">Cancel</button>
</div></body></html>"""

TRAP = """<!doctype html><html><head><meta charset=utf-8><title>Trap</title></head><body>
<div aria-hidden="true"><p>Background content</p><button>Background button</button></div>
<div aria-hidden="true"><p>More background</p></div>
<div role="dialog" aria-label="Sign in" style="width:380px;height:200px;border:1px solid #333;padding:12px">
  <h2>Sign in</h2>
  <label>Email <input id="em" name="email"></label>
  <button id="go">Continue</button>
</div></body></html>"""

PAGES = {"/cmp": CMP, "/checkout": CHECKOUT, "/busy": BUSY, "/trap": TRAP}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/top"):
            TOPS = {
              "/top-cmp":        (f"http://127.0.0.1:{PORT_A}/cmp",      760, 420),
              "/top-cmp-full":   (f"http://127.0.0.1:{PORT_A}/cmp",      1280, 1600),
              "/top-cmp-x-full": (f"http://127.0.0.1:{PORT_B}/cmp",      1280, 1600),
              "/top-checkout":   (f"http://127.0.0.1:{PORT_B}/checkout", 760, 420),
              "/top-busy":       (f"http://127.0.0.1:{PORT_B}/busy",     760, 420),
              "/top-busy-same":  (f"http://127.0.0.1:{PORT_A}/busy",     760, 420),
              "/top-trap":       (f"http://127.0.0.1:{PORT_A}/trap",     760, 420),
              # THE REAL CMP SHAPE: a full-page fixed overlay iframe
              # (Sourcepoint / OneTrust / Didomi all ship this).
              "/top-overlay-x":    (f"http://127.0.0.1:{PORT_B}/cmp", 1280, 1600),
              "/top-overlay-same": (f"http://127.0.0.1:{PORT_A}/cmp", 1280, 1600),
            }
            src, w, h = TOPS.get(path, ("about:blank", 400, 300))
            sty = ("position:fixed;inset:0;z-index:99999;width:100%;height:100%"
                   if "overlay" in path else "")
            body = (TOP.replace("%SRC%", src).replace("%W%", str(w))
                       .replace("%H%", str(h)).replace("%STY%", sty))
        else:
            body = PAGES.get(path, "<!doctype html><title>x</title><p>nothing</p>")
        b = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


def serve(port):
    s = HTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


CASES = [
    ("same-origin CMP (aria-modal), 760x420 frame",  f"http://127.0.0.1:{PORT_A}/top-cmp"),
    ("same-origin CMP (aria-modal), FULL-viewport frame", f"http://127.0.0.1:{PORT_A}/top-cmp-full"),
    ("CROSS-origin CMP (aria-modal), FULL-viewport frame", f"http://127.0.0.1:{PORT_A}/top-cmp-x-full"),
    ("same-origin progressbar + aria-busy", f"http://127.0.0.1:{PORT_A}/top-busy-same"),
    ("CROSS-origin checkout (showModal)", f"http://127.0.0.1:{PORT_A}/top-checkout"),
    ("CROSS-origin progressbar + aria-busy", f"http://127.0.0.1:{PORT_A}/top-busy"),
    ("same-origin focus-trap (aria-hidden sibs)", f"http://127.0.0.1:{PORT_A}/top-trap"),
    ("CROSS-origin CMP as FULL-PAGE FIXED OVERLAY", f"http://127.0.0.1:{PORT_A}/top-overlay-x"),
    ("same-origin CMP as FULL-PAGE FIXED OVERLAY", f"http://127.0.0.1:{PORT_A}/top-overlay-same"),
]


async def fixtures_main():
    serve(PORT_A)
    serve(PORT_B)
    time.sleep(0.4)
    out = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1280, "height": 1600})
        await ctx.add_init_script(path=TAG_JS)
        page = await ctx.new_page()
        for label, url in CASES:
            await page.goto(url, wait_until="load")
            await page.wait_for_timeout(500)
            top = await page.evaluate(
                "(function(){ " + COLLECT + "; return _collectInteractivePage("
                "false, null, 'compact', false, false, 'tree'); })()") or ""
            top_flat = await page.evaluate(
                "(function(){ " + COLLECT + "; return _collectInteractivePage("
                "false, null, 'compact', false, false, 'flat'); })()") or ""
            tready = await page.evaluate(
                "(function(){ " + READY + "; return _readinessPage(); })()")
            rec = {"case": label, "top_banner": BANNER in top,
                   "top_section_dialog": any(
                       "section=dialog" in ln for ln in top_flat.splitlines()
                       if ln.strip().startswith("ref_")),
                   "top_flat": top_flat,
                   "top_chars": len(top),
                   "top_occluded": top_flat.count("(occluded/blocked)"),
                   "top_rows": top_flat.count("mmid=") or top.count("ref_"),
                   "top_ready": tready,
                   "top_listing": top, "frames": []}
            for fr in page.frames:
                if fr == page.main_frame:
                    continue
                t0 = time.time()
                fl = await fr.evaluate(
                    "(function(){ " + COLLECT + "; return _collectInteractivePage("
                    "false, null, 'compact', false, false, 'tree'); })()") or ""
                ms = round((time.time() - t0) * 1000)
                fready = await fr.evaluate(
                    "(function(){ " + READY + "; return _readinessPage(); })()")
                rec["frames"].append({
                    "url": fr.url, "inject_ms": ms,
                    "frame_banner": BANNER in fl,
                    "frame_section_dialog": any(
                        "section=dialog" in ln for ln in fl.splitlines()
                        if ln.strip().startswith("ref_")),
                    "frame_ready": fready,
                    "frame_listing": fl,
                    "same_origin_reachable": await page.evaluate(
                        """(u)=>{try{const f=[...document.querySelectorAll('iframe')]
                           .find(i=>i.src===u); return !!(f && f.contentDocument);}
                           catch(e){return false;}}""", fr.url),
                })
            out.append(rec)
        await b.close()
    (ROOT / "temp" / "fixture_results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for r in out:
        print(f"\n=== {r['case']}")
        print(f"  TOP today : banner={r['top_banner']}  section=dialog="
              f"{r['top_section_dialog']}  chars={r['top_chars']}  "
              f"rows={r['top_rows']} occluded={r['top_occluded']}")
        print(f"  TOP ready : {json.dumps(r['top_ready'])[:150]}")
        for f in r["frames"]:
            print(f"  FRAME     : banner={f['frame_banner']} "
                  f"section=dialog={f['frame_section_dialog']} "
                  f"inject={f['inject_ms']}ms contentDocument-reachable="
                  f"{f['same_origin_reachable']}")
            print(f"  FRAME rdy : {json.dumps(f['frame_ready'])[:150]}")





if __name__ == "__main__":
    asyncio.run(main())
