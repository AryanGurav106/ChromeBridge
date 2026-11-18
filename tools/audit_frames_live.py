# -*- coding: utf-8 -*-
"""Cross-origin iframes, driven through the REAL extension -- and the claim that
   this was impossible, tested rather than inherited.

THE CLAIM UNDER TEST. CLAUDE.md #2 says of the cross-origin path: "uses chrome.*
APIs -- validated by review + syntax, runtime-verifiable only in the live
extension (Playwright can't exercise it)." `docs/research/STAGE-GENERALITY`
inherited it ("cross-origin iframes: measured by neither arm"), and
`tools/test_frames.py` opens by repeating it ("written off as runtime-only,
Playwright can't exercise chrome.* APIs. That is true of `collectCrossFrames`
itself, but NOT of the part that actually broke: the GEOMETRY").

**It is false, and this repo already contained the counter-example.**
`tools/run_flows.py` has been launching a real Chrome with the real unpacked
extension, a real WebSocket bridge and the real MCP tool functions since #50 --
in CI, on every push. `chrome.webNavigation.getAllFrames` and
`chrome.scripting.executeScript({frameIds, world:"MAIN"})` both run there,
because it is a real extension in a real browser; what Playwright cannot do is
reach `chrome.*` from `page.evaluate()`, which is a different sentence.
So the untested half was never "cross-origin frames", it was "anything that
needs the extension", and the harness for that shipped eight entries ago.
This probe is `run_flows`'s launch path pointed at frame fixtures.

PRINCIPLES 5 / 11 / 15: a probe that has never reported a defect is worth
nothing. `--selftest` plants three controls the collector SHOULD miss (a
depth-2 nested frame, cross-origin under same-origin, and a cross-origin frame
injected after load) and requires the detector to report each as missing; and
`--lossy` deletes a real frame row from a real listing and requires the identity
arm to rise. Both are run before any zero in the write-up is believed.

NO BOT EVASION, NO SPOOFING: every origin here is a local HTTP server this
script starts and stops, on ports the OS picks. Two ports are two real origins
-- Chrome's same-origin policy keys on scheme+host+PORT -- so the frames are
genuinely cross-origin and `contentDocument` genuinely throws.

THE GATE IS GRANTED, NOT BYPASSED, exactly as `run_flows` does it: a throwaway
profile this script creates and destroys, with the grant written into ITS
storage, on a bridge port outside the default 8765-8774 span so the user's own
Chrome never sees it. `ALLOW_ALL_ORIGINS` is not touched.

    python tools/audit_frames_live.py --selftest     # prove the detector fires
    python tools/audit_frames_live.py                # the measurement
    python tools/audit_frames_live.py --lossy        # firing proof on a real listing
    python tools/audit_frames_live.py --drift        # run the matrix twice
"""
from __future__ import annotations

import argparse
import asyncio
import http.server
import importlib.util
import json
import re
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.async_api import async_playwright      # noqa: E402
from core.bridge.server import ExtensionBridge         # noqa: E402
import run_flows as RF                                 # noqa: E402  (launch path reused)

EXT = ROOT / "extension"
OUT = ROOT / "temp" / "frames_live"
# Outside the default span AND outside run_flows' 8901, so this can never be
# mistaken for -- or collide with -- either the user's bridge or the CI one.
BRIDGE_PORT = 8913
# `RF._grant` seeds the throwaway profile with `RF.PORT`, so reusing the grant
# without this writes 8901 into storage, the extension sweeps a port nothing is
# listening on, and `wait_until_connected` dies on a bare TimeoutError naming
# nothing -- which is #17's first-run bug, reached by reusing someone else's
# constant. Rebinding it is the one-spelling fix; copying `_grant` would be two.
RF.PORT = BRIDGE_PORT


# --------------------------------------------------------------------------
# Fixtures. Every page is served from a port this script owns.
# --------------------------------------------------------------------------

def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def serve(port: int, pages: dict):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = pages.get(self.path.split("?")[0], pages.get("/", "")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _child(title: str, marker: str, extra: str = "") -> str:
    """A leaf frame: one button, one field, both with identities nothing else shares."""
    return f"""<!DOCTYPE html><meta charset="utf-8"><title>{title}</title>
<body style="margin:0;font:14px system-ui">
  <h2>{title}</h2>
  <button id="b" onclick="document.getElementById('got').textContent='CLICKED'">{marker} button</button>
  <input id="i" placeholder="{marker} field">
  <label>{marker} choice <select><option>alpha</option><option>beta</option></select></label>
  <span id="got">not-clicked</span>
  {extra}
</body>"""


# --------------------------------------------------------------------------
# Scenarios. Each is (name, parent-html-builder, what we expect to find).
# --------------------------------------------------------------------------

def build_pages(pA: int, pB: int, pC: int) -> tuple:
    """Returns (pages_for_A, pages_for_B, pages_for_C).

    A is the top document's origin. B and C are two OTHER origins, so B-in-A is
    cross-origin and C-in-B is cross-origin at depth 2.
    """
    B = f"http://127.0.0.1:{pB}"
    C = f"http://127.0.0.1:{pC}"

    frame = ('<iframe src="{src}" style="width:460px;height:230px;border:1px solid #999"'
             ' title="{title}"></iframe>')

    a_pages = {
        # S1 -- the baseline. One cross-origin frame at depth 1.
        "/s1.html": f"""<!DOCTYPE html><meta charset="utf-8"><title>s1 depth1 xorigin</title>
<body style="margin:0;font:14px system-ui"><h1>S1 depth-1 cross-origin</h1>
<button>TOPLEVEL s1 button</button>
{frame.format(src=B + "/leaf.html?s1", title="payment frame")}
</body>""",

        # S2 -- same-origin control. Must be collected INLINE, no f<id>: prefix.
        "/s2.html": f"""<!DOCTYPE html><meta charset="utf-8"><title>s2 same-origin frame</title>
<body style="margin:0;font:14px system-ui"><h1>S2 same-origin</h1>
<button>TOPLEVEL s2 button</button>
{frame.format(src="/leaf_same.html", title="same origin frame")}
</body>""",

        # S3 -- NESTED: cross-origin B at depth 1, which itself embeds C at depth 2.
        "/s3.html": f"""<!DOCTYPE html><meta charset="utf-8"><title>s3 nested xorigin</title>
<body style="margin:0;font:14px system-ui"><h1>S3 nested</h1>
<button>TOPLEVEL s3 button</button>
{frame.format(src=B + "/nest.html", title="outer frame")}
</body>""",

        # S4 -- SAME-ORIGIN frame that embeds a CROSS-ORIGIN frame. The inner frame
        # has parentFrameId != 0, which collectCrossFrames filters out.
        "/s4.html": f"""<!DOCTYPE html><meta charset="utf-8"><title>s4 xorigin under same-origin</title>
<body style="margin:0;font:14px system-ui"><h1>S4 x-under-same</h1>
<button>TOPLEVEL s4 button</button>
{frame.format(src="/nest_same.html", title="same origin wrapper")}
</body>""",

        # S5 -- a frame that exists only AFTER an interaction.
        "/s5.html": f"""<!DOCTYPE html><meta charset="utf-8"><title>s5 late frame</title>
<body style="margin:0;font:14px system-ui"><h1>S5 late frame</h1>
<button id="add" onclick="var f=document.createElement('iframe');
  f.src='{B}/leaf.html?s5'; f.title='late frame';
  f.style.cssText='width:460px;height:230px;border:1px solid #999';
  document.body.appendChild(f);">ADD THE FRAME</button>
</body>""",

        # S6 -- THREE same-host cross-origin frames (the Stripe Elements shape:
        # card / expiry / CVC all from js.stripe.com). Exercises the anchoring
        # fallbacks in collectCrossFrames.
        "/s6.html": f"""<!DOCTYPE html><meta charset="utf-8"><title>s6 three same-host frames</title>
<body style="margin:0;font:14px system-ui"><h1>S6 three frames, one host</h1>
{frame.format(src=B + "/leaf.html?card", title="card")}
{frame.format(src=B + "/leaf2.html?expiry", title="expiry")}
{frame.format(src=B + "/leaf3.html?cvc", title="cvc")}
</body>""",

        # S7 -- a cross-origin frame holding MORE than the 40-entry FRAME_CAP.
        "/s7.html": f"""<!DOCTYPE html><meta charset="utf-8"><title>s7 big frame</title>
<body style="margin:0;font:14px system-ui"><h1>S7 over the cap</h1>
{frame.format(src=B + "/big.html", title="consent frame")}
</body>""",

        # S8 -- A HOVER MENU, THROUGH THE REAL STACK. It lives here rather than in
        # audit_hover_stage because that probe calls the collector DIRECTLY from
        # Playwright and therefore cannot see anything the SERVER adds: the
        # `(just appeared)` novelty flag (#31) is server-side state seeded per tab,
        # and a collector-direct harness would report it absent for a reason that
        # has nothing to do with hovering. This rig drives read_page for real.
        "/s8.html": """<!DOCTYPE html><meta charset="utf-8"><title>s8 hover menu</title>
<style>
  body { font: 14px system-ui; margin: 0; }
  nav ul { list-style: none; margin: 0; padding: 12px; display: flex; gap: 20px; }
  .sub { display: none; position: absolute; background: #fff; border: 1px solid #666;
         padding: 8px; z-index: 9; }
  li.has:hover .sub { display: block; }
</style>
<body><h1>S8 hover menu</h1>
  <nav><ul>
    <li class="has" id="root">Products
      <div class="sub">
        <a href="/h1">HOVERONLY alpha</a><br>
        <a href="/h2">HOVERONLY beta</a><br>
        <button>HOVERONLY gamma</button>
      </div>
    </li>
    <li><a href="/plain">Always visible link</a></li>
  </ul></nav>
</body>""",

        # Same-origin leaves, served from A.
        "/leaf_same.html": _child("Same-origin leaf", "SAMEORIGIN"),
        "/nest_same.html": f"""<!DOCTYPE html><meta charset="utf-8"><title>same wrapper</title>
<body style="margin:0"><p>same-origin wrapper</p>
<iframe src="{C}/leaf.html?s4" style="width:420px;height:200px;border:0" title="inner xorigin"></iframe>
</body>""",
    }

    b_pages = {
        # The `target="_top"` link is deliberate. `_fmtLine`'s flag for it reads
        # "(REPLACES the whole page, destroying THIS FRAME and every F-REF in it)"
        # and its legend line calls it an "in-frame link" -- both written for
        # exactly this row, in the formatter cross-origin frame rows never reach.
        # Measured rather than inferred from the source.
        "/leaf.html": _child("B leaf", "XORIGINB",
                             '<a href="/elsewhere" target="_top">XORIGINB escape-hatch</a>'),
        "/leaf2.html": _child("B leaf two", "XORIGINB2"),
        "/leaf3.html": _child("B leaf three", "XORIGINB3"),
        "/nest.html": f"""<!DOCTYPE html><meta charset="utf-8"><title>B nest</title>
<body style="margin:0"><p>outer cross-origin frame</p>
<button>OUTERFRAME button</button>
<iframe src="{C}/leaf.html?s3" style="width:400px;height:150px;border:0" title="inner xorigin"></iframe>
</body>""",
        "/big.html": ("<!DOCTYPE html><meta charset=\"utf-8\"><title>big</title><body style=\"margin:0\">"
                      + "".join(f'<a href="#x{i}">BIGFRAME link {i}</a><br>' for i in range(55))
                      + '<button>BIGFRAME Accept all</button></body>'),
    }

    c_pages = {"/leaf.html": _child("C leaf", "XORIGINC")}
    return a_pages, b_pages, c_pages


# --------------------------------------------------------------------------
# The metric.
#
# Reused where it can be: `identity_of` is imported from measure_findability so
# the "what the listing would print" definition cannot drift (PRINCIPLES 17).
# The CENSUS has to be new, because every existing arm runs in the TOP document
# and a cross-origin frame is exactly what the top document cannot read -- so
# the census runs INSIDE each frame, via Playwright, and the listing it is
# checked against is the real one the agent received.
# --------------------------------------------------------------------------

# Visible controls in THIS document, with the mmid the collector stamped (if any).
# Same admitting sets as audit_generality_live's PROBE2 (core / declared), same
# visibility call -- `{opacityProperty, visibilityProperty}`, because #36 measured
# a bare checkVisibility() reporting 3.81% identity loss that was not there.
FRAME_CENSUS = r"""
(function () {
  const CORE = 'a[href],button,input,select,textarea,summary';
  const DECL = '[role=button],[role=link],[role=menuitem],[role=tab],[role=checkbox],'
    + '[role=radio],[role=switch],[role=option],[role=combobox],[role=textbox],'
    + '[tabindex]:not([tabindex^="-"]),[contenteditable="true"],[onclick]';
  const out = [];
  const seen = new Set();
  for (const sel of [CORE, DECL]) {
    let all; try { all = document.querySelectorAll(sel); } catch (e) { continue; }
    for (const e of all) {
      if (seen.has(e)) continue; seen.add(e);
      let vis = false;
      try { vis = e.checkVisibility({opacityProperty: true, visibilityProperty: true}); }
      catch (x) { vis = true; }
      if (!vis) continue;
      const r = e.getBoundingClientRect();
      if (!(r.width > 0 && r.height > 0)) continue;
      const tag = e.tagName.toLowerCase();
      const name = (e.getAttribute('aria-label') || e.getAttribute('title') || '').trim();
      // A <select>'s innerText IS ITS OPTION LIST, and #37 records that as the one
      // thing AccName forbids using as a name -- the first version of this census
      // used it anyway and duly reported every <select> on every scenario as a
      // lenient loss, which is a defect in the ruler wearing the costume of a
      // defect in the collector. Labelable controls take their wrapping <label>,
      // which is what the collector resolves and therefore what it prints.
      let txt = "";
      if (tag === 'select' || tag === 'input' || tag === 'textarea') {
        const lab = e.closest('label') ||
                    (e.id ? document.querySelector('label[for="' + CSS.escape(e.id) + '"]') : null);
        if (lab) {
          const clone = lab.cloneNode(true);
          clone.querySelectorAll('select,input,textarea,option').forEach(n => n.remove());
          txt = (clone.textContent || '').trim();
        }
      } else {
        txt = (e.innerText || e.textContent || '').trim().slice(0, 120);
      }
      const ph = (e.getAttribute('placeholder') || '').trim();
      out.push({
        tag: tag,
        mmid: e.getAttribute('mmid') || null,
        identity: name || txt || ph || (e.value || '').trim() || '',
        core: e.matches(CORE),
      });
    }
  }
  return out;
})()
"""


def _rows_in_listing(listing: str) -> set:
    """Every ref the listing hands the agent, in every actionable shape.

    `ref_7`, `ref_f6:3`, and a fold's bare `7:"label"` -- the same five shapes
    `bench_trajectory.listing_refs` harvests, because a folded row is still
    actionable and counting it as loss would be the "folding mistaken for loss"
    error that benchmark records.
    """
    refs = set(re.findall(r"\bref_(f?\d+:?\d*)\b", listing))
    refs |= set(re.findall(r"(?:^|[\s,(])(f?\d+:?\d*):\"", listing))
    return refs


def score_frame(census: list, listing: str, fid) -> dict:
    """Identity, two arms, for ONE frame's controls against the TOP listing.

    lenient -- the control's identity string appears somewhere in the listing.
               Satisfiable by a container's rolled-up label, which is why #85
               added the strict arm.
    strict  -- the control OWNS A ROW, matched by the ref the frame's rows use.
               For a cross-origin frame that is `f<frameId>:<mmid>`; for a
               same-origin frame the collector stamps into the top registry, so
               it is a bare `<mmid>`.
    """
    res = {"candidates": 0, "lenient_lost": [], "strict_norow": [], "no_mmid": []}
    rows = _rows_in_listing(listing)
    for c in census:
        if not c["identity"]:
            continue
        res["candidates"] += 1
        if c["identity"] not in listing:
            res["lenient_lost"].append(c)
        if c["mmid"] is None:
            res["no_mmid"].append(c)
            res["strict_norow"].append(c)
            continue
        key = (f"f{fid}:{c['mmid']}" if fid is not None else c["mmid"])
        if key not in rows:
            res["strict_norow"].append(c)
    return res


# --------------------------------------------------------------------------
# The harness: one browser, one bridge, every scenario.
# --------------------------------------------------------------------------

class Rig:
    """Real extension, real bridge, real MCP tools. `run_flows`'s launch path."""

    def __init__(self, origins):
        self.origins = origins
        self.token = "frames-live-" + str(int(time.time()))

    async def __aenter__(self):
        self.ms = RF._load_server()
        self.bridge = ExtensionBridge(host="127.0.0.1", port=BRIDGE_PORT, token=self.token)
        await self.bridge.start()
        self.ms.STATE["bridge"] = self.bridge
        self._pw = async_playwright()
        p = await self._pw.__aenter__()
        self.ctx = await p.chromium.launch_persistent_context(
            user_data_dir="",
            headless=False,
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}",
                  "--headless=new"],
            viewport={"width": 1280, "height": 1000},
        )
        sw = (self.ctx.service_workers[0] if self.ctx.service_workers
              else await self.ctx.wait_for_event("serviceworker", timeout=25000))
        self.ext_id = sw.url.split("/")[2]
        await RF._grant(self.ctx, self.ext_id, self.origins, self.token)
        await self.bridge.wait_until_connected(timeout=30)
        return self

    async def __aexit__(self, *a):
        try:
            await self.ctx.close()
        except Exception:
            pass
        try:
            await self._pw.__aexit__(*a)
        except Exception:
            pass
        await self.bridge.stop()

    def tool(self, name):
        f = getattr(self.ms, name)
        return f.fn if hasattr(f, "fn") else f

    async def new_tab(self) -> int:
        t = await self.tool("tabs_create_mcp")()
        s = str(t)
        return int(json.loads(s)["tabId"]) if s.strip().startswith("{") \
            else int(re.search(r'"tabId":\s*(\d+)', s).group(1))

    async def goto(self, tab: int, url: str):
        return await self.tool("navigate")(url=url, tabId=tab)

    def page_for(self, url_part: str):
        for pg in self.ctx.pages:
            if url_part in pg.url:
                return pg
        return None


async def run_scenario(rig: Rig, tab: int, name: str, url: str, *, pre_click=None):
    """Navigate, optionally interact, read, and census every frame."""
    await rig.goto(tab, url)
    pg = rig.page_for(url.rsplit("/", 1)[-1])
    row = {"scenario": name, "url": url}
    if pg is None:
        row["error"] = "page handle not found"
        return row
    await pg.wait_for_timeout(600)
    if pre_click:
        try:
            await pg.click(pre_click, timeout=4000)
            row["interacted"] = pre_click
            await pg.wait_for_timeout(900)
        except Exception as e:
            row["interact_error"] = str(e).split("\n")[0][:110]

    listing = str(await rig.tool("read_page")(tabId=tab))
    row["listing"] = listing
    row["listing_chars"] = len(listing)
    # CAN THE ONE DIAGNOSTIC THAT EXISTS TO ANSWER "why is this element missing"
    # ANSWER IT HERE? `read_page(ledger=true)` is that tool. The op router does
    # `if (params?.ledger) break;` BEFORE the cross-frame append, so a ledger read
    # never calls collectCrossFrames at all -- measured rather than read off the
    # source, because #29 records the ledger having a silent exit that made it
    # unable to explain a same-origin frame.
    try:
        led = str(await rig.tool("read_page")(tabId=tab, ledger=True))
    except Exception as e:
        led = "ERROR " + str(e)[:80]
    row["ledger_mentions_frame"] = ("iframe" in led.lower())
    row["ledger_has_cross_frame_rows"] = ("f" in led and "ref_f" in led)
    row["ledger_excerpt"] = led[:300].replace("\n", " ")

    # Frame inventory straight from Playwright -- the ground truth the extension
    # is being scored against, and the only place depth is knowable.
    frames = []
    for f in pg.frames:
        if f == pg.main_frame:
            continue
        depth = 0
        p = f.parent_frame
        while p is not None:
            depth += 1
            p = p.parent_frame
        frames.append((f, depth))
    row["frames_present"] = len(frames)

    # Map each frame to the f<frameId> the LISTING announced, by matching the
    # frame's own marker text. `chrome.webNavigation` frame ids are not visible
    # from Playwright, so the join is by content -- which is also how an agent
    # would do it, and the markers are unique per leaf by construction.
    announced = dict(re.findall(r"\[CROSS-ORIGIN IFRAME f(\d+)", listing) and
                     [(m, True) for m in re.findall(r"\[CROSS-ORIGIN IFRAME f(\d+)", listing)] or [])
    row["xorigin_blocks"] = len(announced)

    per_frame = []
    censuses = []
    for f, depth in frames:
        try:
            census = await f.evaluate(FRAME_CENSUS)
        except Exception as e:
            per_frame.append({"url": f.url, "depth": depth, "error": str(e)[:90]})
            censuses.append([])
            continue
        censuses.append(census)
        same_origin = f.url.startswith(url.split("/", 3)[0] + "//" + url.split("/", 3)[2])
        # Which f<id> block, if any, carries this frame's rows? Join by the
        # frame's own unique marker, then take that block's id.
        fid = None
        mark = next((c["identity"].split()[0] for c in census if c["identity"]), None)
        if mark:
            for blk in re.finditer(r"\[CROSS-ORIGIN IFRAME f(\d+)[^\]]*\]\n((?:ref_f\d+:.*\n?)*)",
                                   listing):
                if mark in blk.group(2):
                    fid = blk.group(1)
                    break
        sc = score_frame(census, listing, fid if fid else (None if same_origin else "?"))
        # CAPPED IS NOT THE SAME AS LOST, and conflating them would damn a bound
        # the system states out loud. `collectCrossFrames` prints "N of M
        # element(s) shown" plus a truncation note, which is the one bound this
        # project permits (PRINCIPLES 5: never truncate SILENTLY). Counted
        # separately so the headline can say which kind of absence this is.
        capped = 0
        if fid:
            m = re.search(r"\[CROSS-ORIGIN IFRAME f" + fid + r"\b[^\]]*?(\d+) of (\d+) element",
                          listing)
            if m and int(m.group(1)) < int(m.group(2)):
                capped = int(m.group(2)) - int(m.group(1))
        per_frame.append({
            "url": f.url, "depth": depth, "same_origin": same_origin,
            "announced_as": fid, "controls": len(census),
            "candidates": sc["candidates"],
            "lenient_lost": len(sc["lenient_lost"]),
            "strict_norow": len(sc["strict_norow"]),
            "announced_cap": capped,
            # The number that matters: absent AND nothing said so.
            "silent_norow": max(0, len(sc["strict_norow"]) - capped),
            "no_mmid": len(sc["no_mmid"]),
            "examples": [c["identity"][:50] for c in sc["strict_norow"][:4]],
        })
    row["per_frame"] = per_frame
    row["_census"] = censuses
    row["recovery_claim"] = recovery_claim(row)
    return row


async def reachability(rig: Rig, tab: int, needle: str, ref: str) -> dict:
    """Can the OTHER tools reach a row the listing plainly printed?

    #74's shape: present in every presence metric, unreachable by the tool that
    reads the listing. Four tools, because they take four different routes --
    `find` and `read_interactive_elements` ask for the STRUCTURED array,
    `query_elements` and `search_page` run their own page-context pass.

    THE TEST IS THE REF, NOT THE NEEDLE, and the first version got this wrong in
    the flattering direction. `search_page` ECHOES the caller's pattern in its
    miss message (#42 made it quote the pattern) and `find` echoes the query, so
    `needle in result` scored three of four tools as REACHING when two of them
    had plainly answered "no match" -- a false credit of exactly the kind
    PRINCIPLES 8 exists for, produced by the person writing the probe. A hit
    emits the REF; an echo cannot.
    """
    out = {"needle": needle, "ref": ref}
    # COUNTING IS THIS TOOL'S PURPOSE, and a partial count is the dangerous case.
    # `query_elements` has a frame notice -- but it is on the ZERO-match path only,
    # where the agent is already suspicious. When the top document holds SOME
    # matches and a cross-origin frame holds more, the tool returns a confident
    # number that is wrong and says nothing. Measured against DOM truth rather
    # than asserted: count the selector in every frame via Playwright.
    truth = 0
    for f in rig.ctx.pages[-1].frames:
        try:
            truth += await f.evaluate("() => document.querySelectorAll('button').length")
        except Exception:
            pass
    try:
        q = str(await rig.tool("query_elements")(tabId=tab, selector="button"))
    except Exception as e:
        q = "ERR " + str(e)[:80]
    m = re.search(r"(\d+)\s+element\(s\) match", q)
    out["count_reported"] = int(m.group(1)) if m else None
    out["count_dom_truth_all_frames"] = truth
    out["count_is_partial"] = (out["count_reported"] is not None
                               and out["count_reported"] < truth)
    out["count_warned_about_frames"] = "DID NOT LOOK INSIDE" in q
    for tool, kw, hit in (
            ("find", {"query": needle}, lambda r: ("ref_" + ref) in r),
            ("search_page", {"pattern": needle}, lambda r: "No match" not in r),
            ("query_elements", {"selector": "button"}, lambda r: needle in r),
            ("read_interactive_elements", {}, lambda r: ("ref_" + ref) in r or ref in r)):
        try:
            r = str(await rig.tool(tool)(tabId=tab, **kw))
        except Exception as e:
            r = "ERROR " + str(e)[:90]
        out[tool] = bool(hit(r))
        out[tool + "_echoed_the_query"] = needle in r      # recorded, never credited
        out[tool + "_excerpt"] = r[-400:].replace("\n", " ")
    return out


def recovery_claim(row: dict) -> dict:
    """Does the page-text notice promise a recovery that works for THESE frames?

    `_domTextPage` ends its cross-origin notice with "read_page DOES reach them --
    their refs look like ref_f<frameId>:<n>". That is true at depth 1 and false
    for every other frame, and PRINCIPLES 6 is explicit that a tool may state a
    fact and list causes but may not assert a recovery it has not verified.
    """
    L = row["listing"]
    promises = "read_page DOES reach them" in L
    named = re.findall(r"CROSS-ORIGIN iframe\(s\) on this page whose text is NOT included", L)
    reached = set(re.findall(r"\[CROSS-ORIGIN IFRAME f(\d+)", L))
    # Frames the census found with content that owns no row anywhere.
    unreached = [p for p in row["per_frame"]
                 if not p.get("same_origin") and p.get("candidates")
                 and p.get("announced_as") is None]
    return {"notice_promises_read_page": promises,
            "notices": len(named),
            "frames_read_page_reached": len(reached),
            "frames_with_content_NOT_reached": len(unreached),
            "promise_is_false_here": bool(promises and unreached)}


async def action_routing(rig: Rig, tab: int, listing: str) -> dict:
    """Does a `ref_f<id>:<n>` row actually ACT? The other half of the chrome.* path.

    `resolveFrameSelector` strips the prefix back to a frame-local selector plus a
    frameId; nothing offline can tell whether the op then lands, because the
    dispatch goes through `chrome.scripting`/CDP into a frame the top document
    cannot see.
    """
    m = re.search(r"ref_(f\d+:\d+) \| button", listing)
    if not m:
        return {"ref": None, "why": "no cross-frame button row in the listing"}
    ref = m.group(1)
    res = {"ref": ref}
    # THE CONTROL, and without it this measures the harness rather than the code.
    # A headless browser, a background tab or a dead input channel (#56) would
    # make EVERY click report NOT DELIVERED, in which case a cross-frame click
    # reporting it says nothing about frames. So a TOP-DOCUMENT button is clicked
    # first, under identical conditions, and its verdict is recorded beside.
    top = re.search(r"ref_(\d+) \| button", listing)
    if top:
        try:
            rt = str(await rig.tool("computer")(action="left_click", ref=top.group(1), tabId=tab))
        except Exception as e:
            rt = "ERROR " + str(e)[:80]
        res["control_top_ref"] = top.group(1)
        res["control_says_not_delivered"] = "NOT DELIVERED" in rt
        res["control_excerpt"] = rt[:150].replace("\n", " ")
    try:
        r = str(await rig.tool("computer")(action="left_click", ref=ref, tabId=tab))
        res["click_result"] = r[:260].replace("\n", " ")
        res["says_not_delivered"] = "NOT DELIVERED" in r
    except Exception as e:
        res["click_error"] = str(e)[:140]
    # Did the FRAME receive it? Asked of the page, not of the tool's own report --
    # #56's rule, and the #10/#11/#12 family's whole lesson.
    pg = rig.ctx.pages[-1]
    landed = None
    for f in pg.frames:
        try:
            v = await f.evaluate("() => { const g = document.getElementById('got');"
                                 " return g ? g.textContent : null; }")
        except Exception:
            continue
        if v == "CLICKED":
            landed = f.url
    res["landed_in_frame"] = landed
    res["landed"] = landed is not None
    return res


# --------------------------------------------------------------------------
# Firing proofs.
# --------------------------------------------------------------------------

LOSSY_NOTE = """\
PRINCIPLES 11/15: a zero from a detector nobody has seen fire is worth nothing.
This deletes the cross-frame rows from a REAL listing the extension produced and
requires the strict arm to rise. A fixture is what you thought of; this is the
actual string."""


def lossy(row: dict) -> dict:
    """Delete the cross-frame block from a REAL listing; the strict arm must rise.

    The census is held fixed and only the haystack is mutilated, so a rise can
    only come from the metric noticing the rows are gone."""
    listing = row["listing"]
    cut = re.sub(r"\[CROSS-ORIGIN IFRAME f\d+[^\]]*\]\n(?:ref_f\d+:.*\n?)*", "", listing)
    clean = {"lenient": sum(p.get("lenient_lost", 0) for p in row["per_frame"]),
             "strict": sum(p.get("strict_norow", 0) for p in row["per_frame"])}
    mut = {"lenient": 0, "strict": 0}
    for pf, cen in zip(row["per_frame"], row.get("_census", [])):
        sc = score_frame(cen, cut, pf.get("announced_as"))
        mut["lenient"] += len(sc["lenient_lost"])
        mut["strict"] += len(sc["strict_norow"])
    return {"clean": clean, "mutilated": mut, "cut_chars": len(listing) - len(cut),
            "fired": mut["strict"] > clean["strict"] and mut["lenient"] > clean["lenient"],
            "note": LOSSY_NOTE}


async def hover_through_server(rig: Rig, tab: int, url: str) -> dict:
    """A CSS :hover menu, read through the REAL read_page.

    Three questions a collector-direct probe cannot answer, because all three are
    produced by the server or by per-tab state the server keeps:
      * do the revealed rows appear at all, through the whole pipeline;
      * are they flagged `(just appeared)` (#31's novelty flag, seeded per tab
        from the mmid registry on UNSCOPED reads) -- i.e. is the agent TOLD the
        menu opened, or does it have to diff two listings itself;
      * does a non-modal hover popover raise the MODAL banner (#51's class).
    The baseline read is taken FIRST so the novelty seen-set exists; without it
    nothing is ever marked new and the answer would be "no flag" for a reason
    that has nothing to do with hovering (#31 pins that a first read marks
    nothing).
    """
    await rig.goto(tab, url)
    pg = rig.page_for("s8.html")
    out = {"url": url}
    if pg is None:
        return {"error": "no page handle"}
    await pg.wait_for_timeout(500)
    before = str(await rig.tool("read_page")(tabId=tab))
    out["before_has_hoveronly"] = "HOVERONLY" in before
    out["before_modal_banner"] = "MODAL/DIALOG IS CURRENTLY OPEN" in before
    el = await pg.query_selector("#root")
    bb = await el.bounding_box()
    await pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
    await pg.wait_for_timeout(120)
    await pg.mouse.move(bb["x"] + bb["width"] / 2 + 1, bb["y"] + bb["height"] / 2 + 1)
    await pg.wait_for_timeout(600)
    # The menu must still be open when the listing is taken, or a zero is a zero
    # for the wrong reason. Asked of the DOM.
    out["menu_open_at_read"] = await pg.evaluate(
        "() => { const s = document.querySelector('.sub');"
        " return !!s && getComputedStyle(s).display !== 'none'; }")
    after = str(await rig.tool("read_page")(tabId=tab))
    out["after_has_hoveronly"] = "HOVERONLY" in after
    out["revealed_rows"] = len(re.findall(r'"HOVERONLY \w+"', after))
    out["just_appeared_on_revealed"] = len(
        [l for l in after.splitlines() if "HOVERONLY" in l and "(just appeared)" in l])
    out["after_modal_banner"] = "MODAL/DIALOG IS CURRENTLY OPEN" in after
    out["sample_rows"] = [l.strip() for l in after.splitlines() if "HOVERONLY" in l][:4]
    # Is a revealed row reachable by the tool whose job is reading the listing?
    try:
        f = str(await rig.tool("find")(query="HOVERONLY beta", tabId=tab))
    except Exception as e:
        f = "ERR " + str(e)[:80]
    m = re.search(r"ref_(\d+) \| a \"HOVERONLY beta\"", after)
    out["find_reaches_revealed"] = bool(m and ("ref_" + m.group(1)) in f)
    return out


def selftest_verdict(scenarios: list) -> dict:
    """PROVE THE DETECTOR FIRES, on three controls it SHOULD report missing.

    The scenarios are built so the answer is known in advance from the DOM, not
    from the collector: S3's depth-2 leaf, S4's cross-origin-under-same-origin
    leaf, and S7's over-the-cap tail all hold rendered, visible, named controls.
    If this probe reports zero for them, the probe is broken and every zero it
    prints elsewhere is worthless (PRINCIPLES 15).

    The negative control is S1/S2/S5/S6: the SAME census, the SAME scoring, on
    frames the collector does reach -- those must come back zero, or the probe
    is simply reporting loss everywhere and distinguishes nothing.
    """
    def tot(name, key):
        s = next((x for x in scenarios if x["scenario"].startswith(name)), None)
        return sum(p.get(key, 0) for p in (s or {}).get("per_frame", []))

    # S3 AND S4 MOVED FROM must_fire TO must_stay_zero WHEN THE DEFECT WAS FIXED.
    # They were the firing proof for A1 -- a cross-origin frame below depth 1
    # silently absent, 3 of 3 controls lost on each -- and `collectCrossFrames`
    # now walks any depth, so asserting they still fire would mean asserting the
    # bug is still there. That is an A/B probe's expiry (MEASUREMENT.md: a probe
    # whose arms come from the broken state has a LIFETIME), one layer over: a
    # SELFTEST that asserts a defect EXISTS becomes a failure the moment it is
    # fixed.
    #
    # The firing proof does not disappear with it. S7 still fires on the real
    # 40-entry cap, which is CORRECT behaviour being announced rather than a
    # defect, so the probe is still shown able to report a loss -- which is what
    # makes the zeros below evidence (PRINCIPLES 5). `--lossy` is the other arm.
    must_fire = {"S7 over the frame cap": tot("S7", "strict_norow")}
    must_stay_zero = {n: tot(n, "strict_norow")
                      for n in ("S1", "S2", "S3", "S4", "S5", "S6")}
    ok = all(v > 0 for v in must_fire.values()) and all(v == 0 for v in must_stay_zero.values())
    return {"fires_where_it_must": must_fire,
            "silent_where_it_must_be": must_stay_zero,
            "PASSED": ok}


# --------------------------------------------------------------------------

async def measure(selftest=False, lossy_run=False, keep=False):
    pA, pB, pC = free_port(), free_port(), free_port()
    a, b, c = build_pages(pA, pB, pC)
    sA, sB, sC = serve(pA, a), serve(pB, b), serve(pC, c)
    base = f"http://127.0.0.1:{pA}"
    origins = [base, f"http://127.0.0.1:{pB}", f"http://127.0.0.1:{pC}"]
    report = {"ports": {"A": pA, "B": pB, "C": pC}, "scenarios": [],
              "bg_sha": None}
    try:
        import hashlib
        report["bg_sha"] = hashlib.sha256(
            (EXT / "background.js").read_bytes()).hexdigest()[:16]
        async with Rig(origins) as rig:
            tab = await rig.new_tab()
            plan = [
                ("S1 depth-1 cross-origin", "/s1.html", None),
                ("S2 same-origin frame", "/s2.html", None),
                ("S3 nested: xorigin in xorigin", "/s3.html", None),
                ("S4 xorigin under same-origin", "/s4.html", None),
                ("S5 frame added after a click", "/s5.html", "#add"),
                ("S6 three same-host frames", "/s6.html", None),
                ("S7 frame over the 40-cap", "/s7.html", None),
                ("S8 hover menu (real stack)", "/s8.html", None),
            ]
            for name, path, click in plan:
                if name.startswith("S8"):
                    report["hover"] = await hover_through_server(rig, tab, base + "/s8.html")
                    continue
                row = await run_scenario(rig, tab, name, base + path, pre_click=click)
                if name.startswith("S1"):
                    L = row["listing"]
                    # Does the one notation authored FOR a cross-frame row survive
                    # the hand-rolled serializer? The element is there; the entry
                    # field is set by the collector running inside the frame.
                    row["topnav"] = {
                        "row_present": bool(re.search(r"ref_f\d+:\d+ \| a[^\n]*escape-hatch", L)),
                        "flag_on_row": "REPLACES the whole page" in L,
                        "legend_line": "in-frame link with target" in L,
                    }
                    m = re.search(r"ref_(f\d+:\d+) \| button \"XORIGINB button\"", row["listing"])
                    row["reachability"] = await reachability(
                        rig, tab, "XORIGINB button", m.group(1) if m else "f?:?")
                    row["action"] = await action_routing(rig, tab, row["listing"])
                    if lossy_run:
                        row["lossy"] = lossy(row)
                report["scenarios"].append(row)
            report["selftest"] = selftest_verdict(report["scenarios"]) if selftest else None
            await rig.tool("tabs_close_mcp")(tabId=tab)
    finally:
        for s in (sA, sB, sC):
            s.shutdown()
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"run_{int(time.time())}.json"
    p.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    report["_path"] = str(p)
    return report


def print_report(r: dict):
    print(f"\nbackground.js sha256[:16] = {r['bg_sha']}")
    print(f"origins: A={r['ports']['A']}  B={r['ports']['B']}  C={r['ports']['C']}"
          "   (three ports = three real origins)\n")
    hdr = (f"{'scenario':<34}{'frm':>4}{'blk':>4}{'cand':>6}{'lenient':>9}"
           f"{'strict':>8}{'capped':>8}{'SILENT':>8}")
    print(hdr)
    print("-" * len(hdr))
    for s in r["scenarios"]:
        if s.get("error"):
            print(f"{s['scenario']:<34}  ERROR {s['error']}")
            continue
        g = lambda k: sum(p.get(k, 0) for p in s["per_frame"])  # noqa: E731
        print(f"{s['scenario']:<34}{s['frames_present']:>4}{s['xorigin_blocks']:>4}"
              f"{g('candidates'):>6}{g('lenient_lost'):>9}{g('strict_norow'):>8}"
              f"{g('announced_cap'):>8}{g('silent_norow'):>8}")
        for pf in s["per_frame"]:
            tag = "same-origin" if pf.get("same_origin") else "CROSS"
            print(f"    d{pf.get('depth')} {tag:<12} announced="
                  f"{('f' + pf['announced_as']) if pf.get('announced_as') else 'NO BLOCK'}"
                  f"  cand={pf.get('candidates')} lenient={pf.get('lenient_lost')}"
                  f" strict={pf.get('strict_norow')} capped={pf.get('announced_cap')}"
                  f" SILENT={pf.get('silent_norow')}"
                  + (f"  e.g. {pf['examples'][:3]}" if pf.get("examples") else ""))
        rc = s.get("recovery_claim") or {}
        if rc.get("promise_is_false_here"):
            print(f"    !! the page-text notice promises \"read_page DOES reach them\" while "
                  f"{rc['frames_with_content_NOT_reached']} frame(s) with content got no block")
        if g("silent_norow"):
            print(f"    !! ledger(ref_f rows present)={s.get('ledger_has_cross_frame_rows')} "
                  f"— the one diagnostic for \"why is this missing\"")
    s1 = next((s for s in r["scenarios"] if s["scenario"].startswith("S1")), None)
    if s1 and s1.get("reachability"):
        rr = s1["reachability"]
        print(f"\nREACHABILITY of the row `ref_{rr['ref']}` the listing printed "
              f"({rr['needle']!r}):")
        for t in ("find", "search_page", "query_elements", "read_interactive_elements"):
            echo = "  (result merely ECHOED the query)" if (
                rr.get(t + "_echoed_the_query") and not rr[t]) else ""
            print(f"    {t:<28} {'REACHES' if rr[t] else 'MISSES'}{echo}")
        print(f"\n    COUNTING: query_elements('button') reported "
              f"{rr.get('count_reported')}, the DOM across all frames holds "
              f"{rr.get('count_dom_truth_all_frames')} — partial="
              f"{rr.get('count_is_partial')}, and it warned about frames="
              f"{rr.get('count_warned_about_frames')}")
    if s1 and s1.get("action"):
        a = s1["action"]
        print(f"\nACTION ROUTING on ref_{a.get('ref')}: "
              + (f"LANDED in {a.get('landed_in_frame')}" if a.get("landed") else "DID NOT LAND"))
        print(f"    cross-frame click says NOT DELIVERED: {a.get('says_not_delivered')}")
        print(f"    CONTROL — top-document click (ref_{a.get('control_top_ref')}) "
              f"says NOT DELIVERED: {a.get('control_says_not_delivered')}")
        print(f"    tool said: {str(a.get('click_result', a.get('click_error')))[:230]}")
    if s1 and s1.get("topnav"):
        t = s1["topnav"]
        print(f"\nTOPNAV — a target=\"_top\" link INSIDE the cross-origin frame "
              f"(its flag text says \"destroying this frame and every f-ref in it\"):")
        print(f"    the row is listed: {t['row_present']}")
        print(f"    (REPLACES the whole page) flag on it: {t['flag_on_row']}")
        print(f"    legend line present: {t['legend_line']}")
    if s1 and s1.get("lossy"):
        L = s1["lossy"]
        print(f"\nLOSSY FIRING PROOF (cut {L['cut_chars']} chars of real cross-frame rows): "
              f"clean {L['clean']} -> mutilated {L['mutilated']}   "
              f"{'FIRED' if L['fired'] else 'DID NOT FIRE — the metric is worthless'}")
    if r.get("hover"):
        h = r["hover"]
        print("\nHOVER MENU THROUGH THE REAL STACK (S8):")
        print(f"    before hover: HOVERONLY present={h.get('before_has_hoveronly')}")
        print(f"    menu still open when the listing was taken: {h.get('menu_open_at_read')}")
        print(f"    after hover: rows={h.get('revealed_rows')} "
              f"(just appeared) on {h.get('just_appeared_on_revealed')} of them")
        print(f"    MODAL banner raised by the popover: {h.get('after_modal_banner')} "
              f"(was {h.get('before_modal_banner')} before)")
        print(f"    find reaches a revealed row: {h.get('find_reaches_revealed')}")
        for s in h.get("sample_rows", []):
            print(f"      {s}")
    if r.get("selftest"):
        st = r["selftest"]
        print("\nSELFTEST  fires where it must: " + str(st["fires_where_it_must"]))
        print("          silent where it must be: " + str(st["silent_where_it_must_be"]))
        print("          " + ("PASSED" if st["PASSED"] else "FAILED"))
    print(f"\nsaved: {r['_path']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true",
                    help="prove the detector fires before any zero is believed")
    ap.add_argument("--lossy", action="store_true",
                    help="delete the cross-frame rows from a REAL listing and re-score")
    ap.add_argument("--drift", action="store_true", help="run the matrix twice")
    args = ap.parse_args()

    r = asyncio.run(measure(selftest=args.selftest, lossy_run=args.lossy))
    print_report(r)
    if args.drift:
        print("\n" + "=" * 70 + "\nDRIFT: second pass, same code\n" + "=" * 70)
        r2 = asyncio.run(measure(lossy_run=args.lossy))
        print_report(r2)
        same = all(
            a["frames_present"] == b["frames_present"] and a["xorigin_blocks"] == b["xorigin_blocks"]
            for a, b in zip(r["scenarios"], r2["scenarios"]))
        print(f"\nDRIFT FLOOR: scenario shape identical across passes: {same}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
