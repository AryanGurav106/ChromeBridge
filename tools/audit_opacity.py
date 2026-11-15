"""`opacity:0` — what the collector deletes for it, and whether Chrome agrees.

`docs/OPEN.md` item 14. THE ITEM'S PREMISE NEEDS CORRECTING FIRST: the
collector does NOT drop everything failing
`checkVisibility({opacityProperty, visibilityProperty})`. Two narrower rules
delete for opacity, and a third deliberately does not:

  THE SELF-OPACITY GATE (`_collectInteractivePage`)
      visible = … && (_selfOpaque || !!ownLabel || _declaredCtl)
      Only the element's OWN computed opacity counts, and a declared control
      (an interactive ARIA role, aria-expanded/-autocomplete/-controls/-label/
      -labelledby, a title, or a widget `input[type]`) is exempt.
  THE PHANTOM-MIRROR RULE
      an element that fails EVERY hit-test AND `checkVisibility({checkOpacity})`
      — i.e. effective opacity 0 and covered — is dropped as a visually-hidden
      duplicate (React Aria's native <select> behind its styled button).
  ANCESTOR OPACITY IS KEPT ON PURPOSE — the opacity-0 `input[file]` under a
      styled upload button, MUI DateField's section list. The comment at the
      gate says so.

MEASURED, 96 usable frozen sites, all arms on the SAME page load with the
order rotated and `base` measured twice (MEASUREMENT.md R3). 2026-11-15:

  drift floor (base vs base2)          entries +0.135%, chars +0.241%
    excluding the named unstable sites entries +0.006%, chars +0.148%
  SELF-OPACITY GATE deletes            175 elements, 21/96 sites, median 0/site
    cost of keeping them               entries +0.51%, chars +0.31% corpus-wide
                                       (+1.59% / +1.13% on the 21 affected)
    of the 175: in the viewport        31 (the other 144 would not print anyway)
    declaring an ARIA role             0  — the `_declaredCtl` exemption
                                       already rescues everything that does
  PHANTOM-MIRROR RULE deletes          78 elements, 3/96 sites

  CHROME KEEPS 149 OF THE 175 (85.1%) and ignores 26 as `uninteresting`.
  So the item's premise is confirmed: Chrome's AX tree does keep opacity:0
  content and we do not. But of the 149 Chrome keeps, 109 are `generic`, 17
  are mastodon's `article` feed posts, 3 are `image`, and only 20 carry an
  INTERACTIVE role. Those 20 are, exhaustively: 14 SKIP LINKS (3 on yahoo_fin,
  8 Korean "…바로가기" on naver, plus kayak / maplibre / select2), 2 BACK-TO-TOP
  buttons (chakra "Scroll to top", maplibre "Back to top"), and 4 UNNAMED (3
  jsfiddle `<a>`, 1 kayak `<input>`). Every named one is an affordance that is
  transparent precisely because the page is not currently offering it — and an
  agent acting by ref needs neither.

  AND NOTHING LOSES AN IDENTITY (PRINCIPLES §3), which is the bar that decides
  it: of the 175, 72 carry a name, and 72/72 have that text somewhere in the
  listing, the structured array or get_page_text. 0 lost.
  `--identities` is that check.

A RETRACTION, recorded because the method is the point. The identity check
first reported 6 NAMED CONTROLS LOST by the phantom-mirror rule ("Add row",
"Sort column", "Clear search"). Re-derived: all 78 have EFFECTIVE OPACITY
EXACTLY 0 — a Lexical table toolbar revealed on hover, a surveyjs dropdown
that is closed, a Carbon "Clear search" that appears when the box has content.
§3's bar is "a rendered, genuinely VISIBLE control"; the user cannot see these
either. The first probe checked identity presence and not visibility, which is
the same corner #36's 3.81%-identity-loss probe fell into — and a bare
`checkVisibility()` calls all 78 of them visible. Not a §3 violation; a
hover-discoverability limitation, the same class as any closed menu.

THE TEXT HALF (`--text`) is what item 14 actually quotes. `_namable` passes
`visibilityProperty` and deliberately NOT `opacityProperty`, so opacity:0 text
flows into names, `get_page_text` and `search_page`. browser-use's `ax.py`
names the hazard: "the AX tree keeps opacity:0 text (pre-rendered success
banners), which agents then report as success". Measured over 97 sites:

  opacity:0 text reaching the text surface  22,252 / 603,171 chars = 3.69%
  sites with any                            28/97 (28.9%)
  sampled strings confirmed in get_page_text 420/434; findable by search_page 412
  sampled strings matching success/error vocabulary   0 / 434

  AND THE CUT THAT DISCRIMINATES. Off-viewport opacity:0 text is content the
  reader has simply not scrolled to; the hazard is text that is INVISIBLE while
  sitting WHERE AN AGENT READS IT. Of the 22,252 chars: 580 (2.6%) are in the
  viewport, 3,640 (16.4%) are under an `aria-hidden` ancestor, and
  **505 chars (2.3%) are in the viewport AND not aria-hidden** — the whole
  risk surface, across 97 sites, and none of it success/error-shaped. What the
  bulk actually is: github's scroll-triggered fade-in marketing copy, mastodon's
  off-screen feed posts (10,707 chars on its own), vimeo promos.

Two derivations, because one would not be believed: a DOM census of elements
whose effective opacity is 0 and which pass `_namable`, and a substring check
against the real `_domTextPage()` output plus a real `_searchTextPage()` hit.

Run:
    python tools/audit_opacity.py                 # the ablation + Chrome's AX verdict
    python tools/audit_opacity.py --identities    # does anything lose an identity?
    python tools/audit_opacity.py --text          # the text-surface census
    python tools/audit_opacity.py --only github,mui_datepicker
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics as st
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "temp" / "frozen"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract  # noqa: E402

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = extract("_collectInteractivePage", BG, verify=False)
TEXTFN = extract("_domTextPage", BG, verify=False)
SEARCHFN = extract("_searchTextPage", BG, verify=False)
TAG_JS = str(ROOT / "extension" / "listener_tag.js")
VIEWPORT = {"width": 1280, "height": 1600}

GATE = "(_selfOpaque || !!ownLabel || _declaredCtl)"
MIRROR = ("else if (el.checkVisibility && !el.checkVisibility({ checkOpacity: true })) "
          "return _drop(el, 'checkVisibility-false');")
# A moved anchor must fail LOUDLY here rather than silently measuring nothing
# (PRINCIPLES §15: a detector that cannot fire also asserts nothing is wrong).
assert COLLECT.count(GATE) == 1, "self-opacity gate anchor moved in background.js"
assert COLLECT.count(MIRROR) == 1, "phantom-mirror anchor moved in background.js"

# THE RECORDER RETURNS THE ORIGINAL VALUE. Observing must not change behaviour,
# and the entry-count equality against `base` is what proves it did not.
PROBE_GATE = ("(window.__opqRec(el, _selfOpaque, !!ownLabel, _declaredCtl, cs, r), "
              + GATE + ")")
PROBE_MIRROR = MIRROR.replace("return _drop(", "return (window.__opqMir(el), _drop(")[:-2] + "));"

ARMS = {
    "base": COLLECT,
    "probe": COLLECT.replace(GATE, PROBE_GATE).replace(MIRROR, PROBE_MIRROR),
    "ablate": COLLECT.replace(GATE, "(true)"),
    "ablate_mirror": COLLECT.replace(MIRROR, ""),
}

RECORDER = r"""
(function () {
  window.__opqEls = []; window.__opqMirEls = [];
  window.__opqInfo = []; window.__opqMirInfo = [];
  const seen = new WeakSet(), seenM = new WeakSet();
  const grab = (el, r) => {
    const cs = getComputedStyle(el);
    let eff = 1, n = el, hops = 0, zeroAt = null;
    while (n && n.nodeType === 1 && hops++ < 40) {
      const o = parseFloat(getComputedStyle(n).opacity || '1');
      if (o === 0 && zeroAt === null)
        zeroAt = (n === el ? 'SELF' : n.tagName.toLowerCase());
      eff *= o;
      n = n.parentElement || (n.getRootNode && n.getRootNode().host) || null;
    }
    const vw = innerWidth, vh = innerHeight;
    let cvCss = true, cvOpVis = null, cvBare = null;
    try { cvCss = !el.checkVisibility || el.checkVisibility({ checkVisibilityCSS: true }); } catch (e) {}
    try { cvOpVis = el.checkVisibility
          ? el.checkVisibility({ opacityProperty: true, visibilityProperty: true }) : null; } catch (e) {}
    try { cvBare = el.checkVisibility ? el.checkVisibility() : null; } catch (e) {}
    return {
      tag: (el.tagName || '').toLowerCase(),
      role: el.getAttribute ? (el.getAttribute('role') || null) : null,
      type: el.getAttribute ? (el.getAttribute('type') || null) : null,
      cls: (typeof el.className === 'string' ? el.className : '').slice(0, 120),
      txt: (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 120),
      al: (el.getAttribute && (el.getAttribute('aria-label') ||
           el.getAttribute('title') || el.getAttribute('alt'))) || '',
      href: el.getAttribute ? (el.getAttribute('href') || null) : null,
      w: Math.round(r.width), h: Math.round(r.height),
      x: Math.round(r.left), y: Math.round(r.top),
      inViewport: (r.top + r.height) > 0 && (r.left + r.width) > 0 &&
                  r.top < vh && r.left < vw,
      effOpacity: eff, zeroAt: zeroAt,
      // #36's corollary, kept visible in the data: the BARE call checks layout
      // only and calls opacity:0 and visibility:hidden elements visible.
      cvCss: cvCss, cvOpacityVisibility: cvOpVis, cvBare: cvBare,
      fading: /opacity|all/.test(cs.transitionProperty || '') &&
              !/^0s(,\s*0s)*$/.test((cs.transitionDuration || '0s').trim()),
      animating: (cs.animationName || 'none') !== 'none',
      pointerEvents: cs.pointerEvents,
      tabindex: el.getAttribute ? el.getAttribute('tabindex') : null,
      parentCls: (el.parentElement && typeof el.parentElement.className === 'string'
                  ? el.parentElement.className : '').slice(0, 120),
    };
  };
  window.__opqRec = function (el, selfOpaque, ownLabel, declaredCtl, cs, r) {
    try {
      // Short-circuiting means size / visibility / display already passed
      // before we were called, so this IS the population the gate deletes.
      if (selfOpaque || ownLabel || declaredCtl) return;
      if (seen.has(el)) return;
      seen.add(el);
      window.__opqEls.push(el);
      window.__opqInfo.push(grab(el, r));
    } catch (e) {}
  };
  window.__opqMir = function (el) {
    try {
      if (seenM.has(el)) return;
      seenM.add(el);
      window.__opqMirEls.push(el);
      window.__opqMirInfo.push(grab(el, el.getBoundingClientRect()));
    } catch (e) {}
  };
})()
"""

# --------------------------------------------------------------------------
# The TEXT census. `_namable`'s own question, and effective opacity beside it.
# --------------------------------------------------------------------------
TEXT_CENSUS = r"""
(function () {
  const namable = (el) => {
    try { return !el.checkVisibility || el.checkVisibility({ visibilityProperty: true }); }
    catch (e) { return true; }
  };
  const effOpacity = (el) => {
    let n = el, hops = 0;
    while (n && n.nodeType === 1 && hops++ < 40) {
      try { if (parseFloat(getComputedStyle(n).opacity || '1') === 0) return 0; } catch (e) {}
      n = n.parentElement || (n.getRootNode && n.getRootNode().host) || null;
    }
    return 1;
  };
  const out = { total_chars: 0, zero_chars: 0, zero_nodes: 0, nodes: 0, samples: [],
                zero_chars_inVp: 0, zero_chars_ariaHidden: 0,
                zero_chars_inVp_notAriaHidden: 0 };
  const walk = (root, d) => {
    if (d > 8) return;
    let els = [];
    try { els = root.querySelectorAll('*'); } catch (e) { return; }
    for (const el of els) {
      const sr = el.shadowRoot || el.__abClosedRoot;
      if (sr) walk(sr, d + 1);
      let own = '';
      for (const c of el.childNodes) if (c.nodeType === 3) own += c.nodeValue;
      own = own.replace(/\s+/g, ' ').trim();
      if (!own) continue;
      const tag = el.tagName.toLowerCase();
      if (tag === 'script' || tag === 'style' || tag === 'template' || tag === 'noscript') continue;
      if (!namable(el)) continue;
      out.nodes++; out.total_chars += own.length;
      if (effOpacity(el) === 0) {
        const rr = el.getBoundingClientRect();
        const inVp = (rr.top + rr.height) > 0 && rr.top < innerHeight &&
                     (rr.left + rr.width) > 0 && rr.left < innerWidth;
        const ah = !!el.closest('[aria-hidden="true"]');
        out.zero_nodes++; out.zero_chars += own.length;
        if (inVp) out.zero_chars_inVp += own.length;
        if (ah) out.zero_chars_ariaHidden += own.length;
        if (inVp && !ah) out.zero_chars_inVp_notAriaHidden += own.length;
        if (out.samples.length < 40) {
          out.samples.push({ tag: tag, txt: own.slice(0, 140), inViewport: inVp,
                             ariaHidden: ah, w: Math.round(rr.width),
                             h: Math.round(rr.height), y: Math.round(rr.top) });
        }
      }
    }
  };
  try { walk(document, 0); } catch (e) {}
  return out;
})()
"""


# --------------------------------------------------------------------------
async def ax_verdicts(page, n_rec: int, n_mir: int) -> dict:
    """Chrome's own verdict per recorded element, over CDP.

    `Accessibility.getFullAXTree` RETURNS AN EMPTY LIST, NOT AN ERROR, if
    `Accessibility.enable` has not run — that cost this project a live
    debugging session (#34). `ax_total` is printed so a silent zero is visible.
    `getPartialAXTree` returns the node even when ignored, which `getFullAXTree`
    membership alone cannot distinguish; both are taken and cross-checked.
    """
    cdp = await page.context.new_cdp_session(page)
    res: dict = {}
    try:
        await cdp.send("DOM.enable")
        await cdp.send("Accessibility.enable")
        await cdp.send("DOM.getDocument", {"depth": 1})
        full = await cdp.send("Accessibility.getFullAXTree")
        nodes = full.get("nodes", [])
        res["ax_total"] = len(nodes)
        res["ax_ignored_in_full"] = sum(1 for n in nodes if n.get("ignored"))
        kept = {n["backendDOMNodeId"] for n in nodes
                if n.get("backendDOMNodeId") is not None and not n.get("ignored")}
        allb = {n["backendDOMNodeId"] for n in nodes
                if n.get("backendDOMNodeId") is not None}

        async def one(js: str, count: int) -> list:
            out = []
            if not count:
                return out
            ev = await cdp.send("Runtime.evaluate", {"expression": js, "returnByValue": False})
            oid = ev.get("result", {}).get("objectId")
            if not oid:
                return out
            props = await cdp.send("Runtime.getProperties",
                                   {"objectId": oid, "ownProperties": True})
            by_idx = {int(p["name"]): p["value"]["objectId"]
                      for p in props.get("result", [])
                      if p["name"].isdigit() and p.get("value", {}).get("objectId")}
            for i in range(count):
                rec = {"i": i}
                eoid = by_idx.get(i)
                if not eoid:
                    rec["err"] = "no objectId"
                    out.append(rec)
                    continue
                try:
                    d = await cdp.send("DOM.describeNode", {"objectId": eoid})
                    bid = d["node"]["backendNodeId"]
                    rec["backendNodeId"] = bid
                    rec["unignored_in_full_tree"] = bid in kept
                    rec["in_full_tree"] = bid in allb
                    pa = await cdp.send("Accessibility.getPartialAXTree",
                                        {"backendNodeId": bid, "fetchRelatives": False})
                    mine = [n for n in pa.get("nodes", []) if n.get("backendDOMNodeId") == bid]
                    if mine:
                        n0 = mine[0]
                        rec["ignored"] = bool(n0.get("ignored"))
                        rec["ax_role"] = (n0.get("role") or {}).get("value")
                        rec["ax_name"] = ((n0.get("name") or {}).get("value") or "")[:70]
                        rec["ignoredReasons"] = [r.get("name")
                                                 for r in (n0.get("ignoredReasons") or [])]
                    else:
                        rec["ignored"] = None
                        rec["err"] = "absent from getPartialAXTree"
                except Exception as e:
                    rec["err"] = str(e)[:90]
                out.append(rec)
            return out

        res["recorded"] = await one("window.__opqEls", n_rec)
        res["mirror"] = await one("window.__opqMirEls", n_mir)
    except Exception as e:
        res["error"] = str(e)[:200]
    finally:
        try:
            await cdp.detach()
        except Exception:
            pass
    return res


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s or "")).strip().casefold()


async def _load(ctx_browser, name: str, url: str):
    ctx = await ctx_browser.new_context(viewport=VIEWPORT)
    await ctx.add_init_script(path=TAG_JS)
    await ctx.route_from_har(str(FROZEN / f"{name}.har"), not_found="abort")
    page = await ctx.new_page()
    await page.goto(url, wait_until="domcontentloaded", timeout=40000)
    try:
        await page.wait_for_load_state("networkidle", timeout=6000)
    except Exception:
        pass
    await page.wait_for_timeout(900)
    return ctx, page


async def _arm(page, name: str) -> dict:
    src = ARMS[name]
    if name == "probe":
        await page.evaluate(RECORDER)
    entries = await page.evaluate(
        "(function(){ " + src + "; return _collectInteractivePage(true); })()") or []
    # COST AND BENEFIT IN THE SAME PASS (R4), and on the DEFAULT surface: the
    # tree listing, not the structured array. Measuring the array alone is how
    # every corpus token figure here once described a listing nobody receives.
    listing = await page.evaluate(
        "(function(){ " + src + "; return _collectInteractivePage("
        "false, null, 'compact', false, false, 'tree'); })()") or ""
    out = {"entries": len(entries), "chars": len(listing)}
    if name == "probe":
        out["info"] = await page.evaluate("window.__opqInfo")
        out["mirror"] = await page.evaluate("window.__opqMirInfo")
    return out


async def run_site(browser, name: str, url: str, rotate: int, mode: str) -> dict:
    try:
        ctx, page = await _load(browser, name, url)
    except Exception as e:
        return {"name": name, "skipped": str(e)[:140]}
    try:
        if mode == "text":
            c = await page.evaluate(TEXT_CENSUS)
            txt = await page.evaluate(
                "(function(){ " + TEXTFN + "; try { const t=_domTextPage(); "
                "return typeof t === 'string' ? t : JSON.stringify(t); } "
                "catch(e){ return 'ERR ' + e; } })()") or ""
            hay = _norm(txt)
            for s in c["samples"]:
                key = _norm(s["txt"])[:50]
                s["in_page_text"] = bool(key) and key in hay
                try:
                    s["search_hits"] = await page.evaluate(
                        "(function(){ " + SEARCHFN + "; try { const r = _searchTextPage("
                        + json.dumps(s["txt"][:40]) +
                        ", {regex:false, caseSensitive:false, contextChars:0, maxResults:3});"
                        " return (r && r.total) || 0; } catch(e){ return -1; } })()")
                except Exception:
                    s["search_hits"] = -2
            return {"name": name, "census": c, "text_chars": len(txt)}

        order = ["base", "probe", "ablate"]
        order = order[rotate % 3:] + order[:rotate % 3]
        res: dict = {"name": name, "order": order}
        for a in order:
            res[a] = await _arm(page, a)
        res["base2"] = await _arm(page, "base")
        info, mir = res["probe"]["info"], res["probe"]["mirror"]
        if mode == "identities":
            res["ablate_mirror"] = await _arm(page, "ablate_mirror")
            base_struct = await page.evaluate(
                "(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()") or []
            base_list = await page.evaluate(
                "(function(){ " + COLLECT + "; return _collectInteractivePage("
                "false, null, 'compact', false, false, 'tree'); })()") or ""
            dom_text = await page.evaluate(
                "(function(){ " + TEXTFN + "; try { const t=_domTextPage(); "
                "return typeof t === 'string' ? t : JSON.stringify(t); } "
                "catch(e){ return ''; } })()") or ""
            hay = _norm(base_list) + " \x00 " + _norm(" ".join(
                " ".join(str(e.get(k) or "") for k in
                         ("name", "label", "value", "placeholder", "text", "near"))
                for e in base_struct)) + " \x00 " + _norm(dom_text)
            for rows in (info, mir):
                for i in rows:
                    ident = _norm(i["txt"] or i["al"])
                    i["has_identity"] = bool(ident)
                    i["identity_present"] = bool(ident) and ident[:40] in hay
        else:
            res["ax"] = await ax_verdicts(page, len(info), len(mir))
        return res
    except Exception as e:
        return {"name": name, "skipped": str(e)[:140]}
    finally:
        await ctx.close()


def load_sites() -> list[tuple[str, str]]:
    src = (ROOT / "tools" / "capture_listings.py").read_text(encoding="utf-8")
    body = src[src.index("SITES = ["):src.index("\nOUT = ")]
    return [(n, u) for n, u in
            re.findall(r'\(\s*"([a-z_0-9]+)"\s*,\s*"(https?://[^"]+)"', body)
            if (FROZEN / f"{n}.har").exists()]


# --------------------------------------------------------------------------
def report_main(rows):
    live = [r for r in rows if "skipped" not in r and r["base"]["entries"] > 0]
    dead = [r for r in rows if "skipped" not in r and r["base"]["entries"] == 0]
    print(f"\nusable {len(live)}  replayed-empty {len(dead)}  "
          f"skipped {len(rows)-len(live)-len(dead)}")

    print("\n--- PROBE SELF-CHECK ---")
    bad = [(r["name"], r["base"]["entries"], r["probe"]["entries"]) for r in live
           if r["base"]["entries"] != r["probe"]["entries"]]
    drifted = {r["name"] for r in live if r["base"]["entries"] != r["base2"]["entries"]}
    print(f"probe != base on {len(bad)}/{len(live)}"
          + (f" {bad[:6]} — of which also drift in base2: "
             f"{[n for n, _, _ in bad if n in drifted]}" if bad else ""))
    over = [r["name"] for r in live
            if r["ablate"]["entries"] - r["base"]["entries"] > len(r["probe"]["info"])]
    print(f"ablate-delta EXCEEDS the recorded population on {len(over)} sites"
          + (f" {over} — THE PROBE IS WRONG" if over else "  (invariant holds)"))

    UNSTABLE = {"wikipedia_ar", "mdn_select", "spotify", "coinmarketcap"}
    for label, sel in (("all usable", live),
                       ("excl. named non-deterministic replays",
                        [r for r in live if r["name"] not in UNSTABLE])):
        e1 = sum(r["base"]["entries"] for r in sel)
        e2 = sum(r["base2"]["entries"] for r in sel)
        ea = sum(r["ablate"]["entries"] for r in sel)
        c1 = sum(r["base"]["chars"] for r in sel)
        c2 = sum(r["base2"]["chars"] for r in sel)
        ca = sum(r["ablate"]["chars"] for r in sel)
        print(f"\n{label} (n={len(sel)})")
        print(f"  DRIFT  entries {100*(e2/e1-1):+.3f}%   chars {100*(c2/c1-1):+.3f}%")
        print(f"  EFFECT entries {100*(ea/e1-1):+.3f}%   chars {100*(ca/c1-1):+.3f}%")

    info = [(r["name"], i, ax) for r in live
            for i, ax in zip(r["probe"]["info"],
                             (r.get("ax", {}).get("recorded") or [{}] * len(r["probe"]["info"])))]
    hits = [r for r in live if r["probe"]["info"]]
    print(f"\n--- SELF-OPACITY GATE: {len(info)} elements on {len(hits)}/{len(live)} sites "
          f"({100*len(hits)/len(live):.1f}%) ---")
    print("worst:", [f"{r['name']}:{len(r['probe']['info'])}" for r in
                     sorted(hits, key=lambda r: -len(r["probe"]["info"]))[:8]])
    print("tags  :", Counter(i["tag"] for _, i, _ in info).most_common(8))
    print("roles :", Counter(i["role"] or "-" for _, i, _ in info).most_common(5))
    print("in viewport:", Counter(i["inViewport"] for _, i, _ in info))
    print("fading/animating:", Counter(i["fading"] or i["animating"] for _, i, _ in info))
    print("pointer-events:none:", sum(1 for _, i, _ in info if i["pointerEvents"] == "none"))

    ax = [a for _, _, a in info if a and a.get("ignored") is not None]
    if ax:
        kept = sum(1 for a in ax if not a["ignored"])
        print(f"\n--- CHROME'S AX TREE: resolved {len(ax)}/{len(info)} ---")
        print(f"KEPT {kept} ({100*kept/len(ax):.1f}%)   IGNORED {len(ax)-kept} "
              f"({100*(len(ax)-kept)/len(ax):.1f}%)")
        print("ignoredReasons:", Counter(r for a in ax
                                         for r in (a.get("ignoredReasons") or [])).most_common(5))
        print("ax_role of the kept:", Counter(a.get("ax_role") for a in ax
                                              if not a["ignored"]).most_common(8))
        mism = sum(1 for a in ax if a.get("unignored_in_full_tree") is not None
                   and a["unignored_in_full_tree"] == a["ignored"])
        print(f"getFullAXTree vs getPartialAXTree disagreements: {mism}")
        INTER = {"button", "link", "textbox", "combobox", "checkbox", "radio", "menuitem",
                 "tab", "switch", "slider", "listbox", "option", "searchbox", "spinbutton"}
        inter = [(n, i, a) for n, i, a in info
                 if a and a.get("ax_role") in INTER and not a.get("ignored")]
        print(f"\nkept WITH AN INTERACTIVE AX ROLE: {len(inter)}")
        for n, i, a in inter:
            print(f"   {n:16} {i['tag']:7} ax={a['ax_role']:9} vp={str(i['inViewport']):5} "
                  f"name={a['ax_name']!r}")

    mir = [(r["name"], m) for r in live for m in r["probe"]["mirror"]]
    print(f"\n--- PHANTOM-MIRROR RULE: {len(mir)} elements on "
          f"{sum(1 for r in live if r['probe']['mirror'])} sites ---")
    if mir:
        nz = [(n, m) for n, m in mir if m["effOpacity"] > 0]
        print(f"with EFFECTIVE OPACITY > 0 (a user could see them): {len(nz)}")
        print("a BARE checkVisibility() would call visible:",
              sum(1 for _, m in mir if m["cvBare"]))


def report_identities(rows):
    live = [r for r in rows if "skipped" not in r]
    for label, key in (("SELF-OPACITY GATE", "info"), ("PHANTOM-MIRROR RULE", "mirror")):
        allr = [x for r in live for x in r["probe"][key]]
        named = [x for x in allr if x["has_identity"]]
        lost = [x for x in named if not x["identity_present"]]
        print(f"\n{label}: {len(allr)} deleted, {len(named)} carry an identity")
        print(f"  identity present in listing/structured/get_page_text: {len(named)-len(lost)}")
        print(f"  IDENTITY ABSENT EVERYWHERE                          : {len(lost)}")
        for x in lost[:20]:
            # The second question, and the one that decides whether it is a
            # PRINCIPLES #3 violation: could a user have seen it?
            print(f"     {x['tag']:8} {x['w']:4}x{x['h']:<4} effOpacity={x['effOpacity']} "
                  f"zeroAt={x['zeroAt']} checkVis(op,vis)={x['cvOpacityVisibility']} "
                  f"bare={x['cvBare']} {(x['txt'] or x['al'])[:60]!r}")
        vis_lost = [x for x in lost if x["effOpacity"] > 0]
        print(f"  ... of those, GENUINELY VISIBLE (effective opacity > 0): {len(vis_lost)}"
              f"   <-- only these would violate PRINCIPLES #3")


def report_text(rows):
    live = [r for r in rows if "skipped" not in r and r["census"]["nodes"] > 0]
    tz = sum(r["census"]["zero_chars"] for r in live)
    tt = sum(r["census"]["total_chars"] for r in live)
    zi = sum(r["census"]["zero_chars_inVp"] for r in live)
    za = sum(r["census"]["zero_chars_ariaHidden"] for r in live)
    zn = sum(r["census"]["zero_chars_inVp_notAriaHidden"] for r in live)
    print(f"\n=== {len(live)} usable sites ===")
    print(f"text chars at effective opacity 0 that pass the rendered test: "
          f"{tz}/{tt} = {100*tz/tt:.2f}%")
    print(f"sites with any: {sum(1 for r in live if r['census']['zero_nodes'])}/{len(live)}")
    print(f"  IN the viewport                 : {zi} ({100*zi/max(1,tz):.1f}%)")
    print(f"  under an aria-hidden ancestor   : {za} ({100*za/max(1,tz):.1f}%)")
    print(f"  IN viewport AND NOT aria-hidden : {zn} ({100*zn/max(1,tz):.1f}%)"
          f"  <-- the only sub-class where 'what the page says' can mislead")
    samples = [(r["name"], s) for r in live for s in r["census"]["samples"]]
    print(f"sampled: {len(samples)}; confirmed in get_page_text: "
          f"{sum(1 for _, s in samples if s.get('in_page_text'))}; "
          f"findable by search_page: {sum(1 for _, s in samples if (s.get('search_hits') or 0) > 0)}")
    # FOR A HUMAN TO READ. This wordlist decides nothing (PRINCIPLES #4).
    pat = re.compile(r"\b(success|succeeded|complete|completed|confirmed|thank you|"
                     r"your order|submitted|saved|error|failed|invalid|sorry|oops|"
                     r"welcome back|signed in|logged in)\b", re.I)
    hit = [(n, s) for n, s in samples if pat.search(s["txt"])]
    print(f"\n[reading aid, decides nothing] sampled strings matching "
          f"success/error vocabulary: {len(hit)}")
    for n, s in hit[:15]:
        print(f"   {n:16} inVp={s['inViewport']} ah={s['ariaHidden']} {s['txt'][:80]!r}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="")
    ap.add_argument("--identities", action="store_true",
                    help="does either rule lose an identity? (PRINCIPLES #3)")
    ap.add_argument("--text", action="store_true",
                    help="opacity:0 text reaching get_page_text / search_page")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    mode = "identities" if args.identities else ("text" if args.text else "main")

    sites = load_sites()
    if args.only:
        want = set(args.only.split(","))
        sites = [s for s in sites if s[0] in want]
    if args.limit:
        sites = sites[:args.limit]

    rows, t0 = [], time.time()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for i, (n, u) in enumerate(sites):
            r = await run_site(browser, n, u, i, mode)
            rows.append(r)
            if "skipped" in r:
                print(f"  SKIP {n}: {r['skipped']}", flush=True)
            elif mode == "text":
                c = r["census"]
                print(f"  {n}: nodes={c['nodes']} zero={c['zero_nodes']} "
                      f"zero_chars={c['zero_chars']}/{c['total_chars']}", flush=True)
            else:
                print(f"  {n}: base={r['base']['entries']} probe={r['probe']['entries']} "
                      f"ablate={r['ablate']['entries']} base2={r['base2']['entries']} "
                      f"gate={len(r['probe']['info'])} mirror={len(r['probe']['mirror'])}",
                      flush=True)
        await browser.close()
    out = Path(args.out) if args.out else (ROOT / "temp" / f"opacity_{mode}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    {"main": report_main, "identities": report_identities, "text": report_text}[mode](rows)
    print(f"\n{len(rows)} sites in {time.time()-t0:.0f}s -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
