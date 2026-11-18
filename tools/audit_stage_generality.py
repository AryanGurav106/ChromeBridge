"""Identity loss AFTER the page has been interacted with -- live, out-of-sample, multi-stage.

WHY THIS EXISTS. `audit_generality_live.py` (#85) measured `lost_identities` = 0 across 260
live out-of-sample sites, and that number describes ONE static read at first paint plus, at
most, ONE disclosure opened. "Works on any site AT ANY STAGE" is the project's own claim and
the post-interaction half of it was unmeasured. A page after four interactions is a different
page: menus are open, a submenu is open inside the first, a tab panel has swapped, a combobox
listbox is rendered, a field holds typed text, and an overlay may have marked everything
behind it aria-hidden. Every one of those changes what the collector sees.

WHAT IS REUSED, NOT REWRITTEN. The whole measurement half comes from
`audit_generality_live` (which itself reuses `inspect_site.PROBE` verbatim):
`_measure_js` (the real collector, extracted from background.js), `_summ`, `usable`,
`EXCLUDED` (frozen corpus + bench_turns + bench_flows), `SCRIPT_OF`, `VIEWPORT`, `TAG_JS`.
Forking the metric would let the two definitions drift, which PRINCIPLES 17 forbids and #36
recorded happening to the permitted-drop-reason set.

WHAT IS NEW. A bounded interaction DRIVER. Each stage picks ONE action from what the page
DECLARES -- never a class name, never a label wordlist (PRINCIPLES 1, 4) -- performs it as a
user would, and counts the stage ONLY if the page's own declared state actually flipped
(#85's rule, kept). Tiers, in order:

    menu-popup       [aria-expanded=false][aria-haspopup]        flip: aria-expanded -> true
    dialog-trigger   [aria-haspopup=dialog] / controls a dialog  flip: a visible dialog appears
    expandable-controls  [aria-expanded=false][aria-controls]    flip: aria-expanded -> true
    combobox         [role=combobox][aria-expanded=false]        flip: aria-expanded -> true
    details          details:not([open]) > summary               flip: details.open -> true
    tab              [role=tab][aria-selected=false]             flip: aria-selected -> true
    expandable       [aria-expanded=false]                       flip: aria-expanded -> true
    select           select with >= 2 options, keyboard first    flip: selectedIndex changes
    text-input       a writable text field                       flip: value holds what we typed

A kind is used at most twice per site, so a site that is all menus still reaches a select or a
field; within a tier a candidate INSIDE an already-opened target is preferred, so stage 2
compounds on stage 1 (that is how a second-level menu is reached without naming one).

THINGS THAT WOULD INVALIDATE THE RESULT, AND WHAT IS DONE ABOUT THEM.
  * Visibility. `checkVisibility({opacityProperty:true, visibilityProperty:true})` everywhere.
    A bare call reported 3.81% phantom loss and 0.00% with the options passed (#36).
  * Our own footprint. The probe writes NOTHING to the DOM: the click target is an element
    HANDLE and used-ness lives in a `window.__abStage*` expando. The first version marked the
    target with an attribute and removed it after clicking, and that set/remove pair is itself
    a mutation the readiness probe then reported ~18ms before every post-interaction read, on
    every site -- #70's lesson rebuilt by someone who had read #70. `probe_attrs_clean` asserts
    the absence on every measurement.
  * Navigation. A stage that leaves the document ends the site's chain; links, submits and
    image buttons are never picked in the first place.
  * `Array.prototype.toJSON`. Inherited from `_measure_js` (#85 hit it on kebhana.com, where it
    makes `JSON.stringify(array)` a string-of-a-string and every mmid lookup silently misses).
  * Bot blocks. No user-agent spoofing, no automation hiding. A site that blocks us is
    UNMEASURED and is counted as such, never as a pass.
  * Drift. `--compare` runs the same sites twice with the code held constant. A stage-to-stage
    difference smaller than that floor is noise.

LOSS IS REPORTED TWO WAYS, because #85 found the lenient one too weak: LENIENT (the name
appears anywhere in the listing or the blob -- satisfiable by a container's concatenated
label) and STRICT (the control OWNS a row, by mmid / ref_N). Both must be 0.

READINESS is measured by extracting `_readinessPage` from background.js and calling it in the
page, plus Playwright's own in-flight request count standing in for the service worker's
`_netPending` (same exclusions: websocket, media). CAVEAT, stated because it is load-bearing:
here the tab is VISIBLE, while the extension's tab is hidden BY DESIGN (#12) and Chrome
throttles a hidden page's timers -- so mutation recency here is an optimistic floor for how
busy a real agent's tab looks.

Run:  python tools/audit_stage_generality.py --selftest            # the fixture proof
      python tools/audit_stage_generality.py --lossy --only A B C  # the LIVE proof
      python tools/audit_stage_generality.py --pool usable85 --conc 6
      python tools/audit_stage_generality.py --compare --only ...  # drift floor
      python tools/audit_stage_generality.py --report temp/stage_generality/main/pass0.json

Findings: docs/research/STAGE-GENERALITY-2026-11.md
"""
import argparse
import asyncio
import collections
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from playwright.async_api import async_playwright  # noqa: E402
from _extract import extract as _extract_fn  # noqa: E402
import audit_generality_live as AGL  # noqa: E402  (metric, sample, exclusions -- all reused)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
READY_FN = _extract_fn("_readinessPage", BG, verify=True)
VIEWPORT = AGL.VIEWPORT
TAG_JS = AGL.TAG_JS
GOTO_MS = 45000
OUT = ROOT / "temp" / "stage_generality"
TYPED = "ab test"          # short, ASCII, no page meaning
MAX_PER_KIND = 2
SETTLE_MS = 1100           # after an interaction, before measuring


# --------------------------------------------------------------------------------------
# PICKER. Declarations only. Returns null when the page declares nothing left to do.
# --------------------------------------------------------------------------------------
STAGE_PICK = r"""
(function (opts) {
  const W = window;
  if (!W.__abStageUsed) W.__abStageUsed = [];       // strong refs; <= 6 per site
  if (!W.__abStageOpened) W.__abStageOpened = [];   // targets already activated, for descendant preference
  const used = W.__abStageUsed, opened = W.__abStageOpened;
  const usedKinds = opts.usedKinds || {};

  function vis(el) {
    try { return el.checkVisibility({ visibilityProperty: true, opacityProperty: true }); }
    catch (e) { return false; }
  }
  function declaredHidden(el) {
    for (let n = el, i = 0; n && i < 120; i++) {
      if (n.nodeType === 1 && (n.getAttribute('aria-hidden') === 'true' || n.hasAttribute('inert'))) return true;
      n = n.parentNode || n.host;
    }
    return false;
  }
  function ok(el) {
    if (used.indexOf(el) >= 0) return false;
    let r; try { r = el.getBoundingClientRect(); } catch (e) { return false; }
    if (r.width < 4 || r.height < 4) return false;
    if (r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) return false;
    if (!vis(el)) return false;
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
    if (declaredHidden(el)) return false;
    return true;
  }
  // Would activating it LEAVE the document? Then it is not a disclosure. Decided from the
  // declaration (href / type=submit / type=image), never from the label.
  function leaves(el) {
    if (el.tagName === 'A' || el.tagName === 'AREA') {
      const h = (el.getAttribute('href') || '').trim();
      if (h && !/^#|^javascript:/i.test(h)) return true;
    }
    if (el.tagName === 'BUTTON' && el.form && (el.type === 'submit' || el.type === 'reset')) return true;
    if (el.tagName === 'INPUT' && (el.type === 'submit' || el.type === 'image' || el.type === 'reset')) return true;
    if (el.getAttribute('target')) return true;
    return false;
  }
  // Composed walk: document + OPEN shadow roots. Closed roots and same-origin frames are
  // deliberately NOT picked from -- Playwright cannot address them by CSS selector, so a
  // pick there could not be clicked as a user would. They are still MEASURED.
  const roots = [];
  (function walk(root, depth) {
    roots.push(root);
    if (depth > 5) return;
    let all; try { all = root.querySelectorAll('*'); } catch (e) { return; }
    let budget = 6000;
    for (const e of all) { if (--budget < 0) break; if (e.shadowRoot) walk(e.shadowRoot, depth + 1); }
  })(document, 0);

  function qsa(sel) {
    const out = [];
    for (const r of roots) { try { for (const e of r.querySelectorAll(sel)) out.push(e); } catch (x) {} }
    return out;
  }
  function visibleDialogs() {
    return qsa('[role=dialog],[role=alertdialog],dialog,[aria-modal="true"]').filter(vis).length;
  }

  const TIERS = [
    ['menu-popup',          '[aria-expanded="false"][aria-haspopup]:not([aria-haspopup="false"])'],
    ['dialog-trigger',      '[aria-haspopup="dialog"],[aria-haspopup="true"][aria-controls]'],
    ['expandable-controls', '[aria-expanded="false"][aria-controls]'],
    ['combobox',            '[role=combobox][aria-expanded="false"]'],
    ['details',             'details:not([open]) > summary'],
    ['tab',                 '[role=tab][aria-selected="false"]'],
    ['expandable',          '[aria-expanded="false"]'],
    ['select',              'select:not([disabled])'],
    ['text-input',          'input[type=text],input[type=search],input[type=email],input[type=tel],'
                            + 'input[type=url],input[type=number],input:not([type]),textarea'],
  ];

  function extraOk(kind, el) {
    if (kind === 'select') return el.options && el.options.length >= 2 && el.size <= 1
                                  && el.selectedIndex < el.options.length - 1;
    if (kind === 'text-input') return !el.readOnly && !el.value;
    if (kind === 'dialog-trigger') {
      if (el.getAttribute('aria-haspopup') === 'dialog') return true;
      const id = el.getAttribute('aria-controls');
      if (!id) return false;
      const t = document.getElementById(id.split(/\s+/)[0]);
      return !!(t && (t.tagName === 'DIALOG' || /dialog/.test(t.getAttribute('role') || '')));
    }
    return true;
  }
  // Prefer a candidate INSIDE something already opened: that is how a second-level menu is
  // reached without naming one. Falls back to document order.
  function rank(el) {
    for (const o of opened) { try { if (o !== el && o.contains && o.contains(el)) return 0; } catch (x) {} }
    for (const o of opened) {
      const id = o.getAttribute && o.getAttribute('aria-controls');
      if (!id) continue;
      for (const part of id.split(/\s+/)) {
        const t = document.getElementById(part);
        try { if (t && t.contains(el)) return 0; } catch (x) {}
      }
    }
    return 1;
  }

  for (const [kind, sel] of TIERS) {
    if ((usedKinds[kind] || 0) >= (opts.maxPerKind || 2)) continue;
    const cands = qsa(sel).filter(el => ok(el) && !leaves(el) && extraOk(kind, el));
    if (!cands.length) continue;
    cands.sort((a, b) => rank(a) - rank(b));
    const el = cands[0];
    const det = el.tagName === 'SUMMARY' ? el.parentElement : null;
    W.__abStage = {
      el: el, kind: kind,
      pre: {
        expanded: el.getAttribute('aria-expanded'),
        selected: el.getAttribute('aria-selected'),
        detailsOpen: det ? !!det.open : null,
        selectedIndex: el.tagName === 'SELECT' ? el.selectedIndex : null,
        value: (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') ? el.value : null,
        dialogs: visibleDialogs(),
        url: location.href,
      },
    };
    const r = el.getBoundingClientRect();
    // A <select>'s typeahead target: the first option after the selected one whose label starts
    // with an ASCII letter or digit. Playwright can only PRESS a key it can name, so a Japanese
    // or Cyrillic label has no keystroke available (measured) and the caller falls back.
    let typeahead = null, optIndex = null;
    if (kind === 'select') {
      for (let i = 0; i < el.options.length; i++) {
        if (i === el.selectedIndex) continue;
        const t = (el.options[i].text || '').trim();
        if (optIndex === null) optIndex = i;
        if (/^[A-Za-z0-9]/.test(t)
            && t[0].toLowerCase() !== ((el.options[el.selectedIndex] || {}).text || ' ').trim()[0]?.toLowerCase()) {
          typeahead = t[0]; optIndex = i; break;
        }
      }
    }
    return {
      kind: kind, tag: el.tagName.toLowerCase(), role: el.getAttribute('role'),
      nested: rank(el) === 0, typeahead: typeahead, optIndex: optIndex,
      inShadow: !!(el.getRootNode && el.getRootNode() !== document && el.getRootNode().host),
      name: ((el.getAttribute('aria-label') || el.innerText || el.getAttribute('placeholder') || '') + '')
              .replace(/\s+/g, ' ').trim().slice(0, 60),
      candidates: cands.length, box: [Math.round(r.width), Math.round(r.height)],
    };
  }
  return null;
})
"""


# Verify the DECLARED state flipped, then drop our marker so nothing measures a DOM we wrote to.
STAGE_VERIFY = r"""
(function () {
  const W = window, s = W.__abStage;
  if (!s) return { flipped: false, why: 'no stage recorded' };
  const el = s.el;
  function vis(e) { try { return e.checkVisibility({ visibilityProperty: true, opacityProperty: true }); } catch (x) { return false; } }
  function dialogs() {
    const out = [];
    (function walk(root, d) {
      let all; try { all = root.querySelectorAll('[role=dialog],[role=alertdialog],dialog,[aria-modal="true"]'); } catch (x) { return; }
      for (const e of all) out.push(e);
      if (d > 5) return;
      let every; try { every = root.querySelectorAll('*'); } catch (x) { return; }
      let b = 6000;
      for (const e of every) { if (--b < 0) break; if (e.shadowRoot) walk(e.shadowRoot, d + 1); }
    })(document, 0);
    return out.filter(vis).length;
  }
  const navigated = location.href.split('#')[0] !== (s.pre.url || '').split('#')[0];
  const gone = !el || !el.isConnected;
  let flipped = false, now = null;
  if (!gone) {
    const det = el.tagName === 'SUMMARY' ? el.parentElement : null;
    now = {
      expanded: el.getAttribute('aria-expanded'),
      selected: el.getAttribute('aria-selected'),
      detailsOpen: det ? !!det.open : null,
      selectedIndex: el.tagName === 'SELECT' ? el.selectedIndex : null,
      value: (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') ? el.value : null,
      focused: document.activeElement === el,
    };
    if (el.tagName === 'SELECT' && el.options[el.selectedIndex]) {
      now.optionText = (el.options[el.selectedIndex].text || '').replace(/\s+/g, ' ').trim();
    }
    const k = s.kind;
    if (k === 'details') flipped = now.detailsOpen === true && s.pre.detailsOpen === false;
    else if (k === 'tab') flipped = now.selected === 'true' && s.pre.selected !== 'true';
    else if (k === 'select') flipped = now.selectedIndex !== s.pre.selectedIndex;
    else if (k === 'text-input') flipped = !!now.value && now.value !== s.pre.value;
    else if (k === 'dialog-trigger') flipped = dialogs() > s.pre.dialogs || now.expanded === 'true';
    else flipped = now.expanded === 'true' && s.pre.expanded !== 'true';
  }
  if (!gone) { W.__abStageUsed.push(el); if (flipped) W.__abStageOpened.push(el); }
  return { flipped: !!flipped, gone: gone, navigated: navigated, pre: s.pre, now: now };
})()
"""


# One evaluate per stage: readiness FIRST (the collector stamps mmid attributes), then the
# metric, unchanged, from audit_generality_live.
def _measure_js():
    return ("(function(){ " + READY_FN + ";"
            " let rd = null;"
            " try { rd = _readinessPage(null); } catch (e) { rd = { error: String(e).slice(0, 160) }; }"
            " const m = " + AGL._measure_js() + ";"
            " m.readiness = rd;"
            # This probe must leave NOTHING in the DOM the collector reads; see _act.
            " m.probe_attrs_clean = !document.querySelector('[data-ab-stage-target],[data-ab-open-target]');"
            # WALKS SHADOW ROOTS, like the picker's counter does. The first version used a
            # plain document.querySelectorAll and so read 0 on wc_webawesome, whose <wa-popover>
            # keeps its <dialog> in a shadow root -- two counters in one probe answering one
            # question differently, which is the defect class this project keeps finding in
            # other code (PRINCIPLES 17). The 2026-11-18 run was taken with the light-DOM
            # version; the write-up says so.
            " m.dialogs_visible = (function(){ let n=0;"
            "   const sel='[role=dialog],[role=alertdialog],dialog,[aria-modal=\"true\"]';"
            "   (function w(root,d){"
            "     let a; try { a = root.querySelectorAll(sel); } catch (e) { return; }"
            "     for (const e of a) { try { if (e.checkVisibility({visibilityProperty:true,opacityProperty:true})) n++; } catch (x) {} }"
            "     if (d > 5) return;"
            "     let every; try { every = root.querySelectorAll('*'); } catch (x) { return; }"
            "     let b = 6000;"
            "     for (const e of every) { if (--b < 0) break; const sr = e.shadowRoot || e.__abClosedRoot; if (sr) w(sr, d+1); }"
            "   })(document, 0); return n; })();"
            " return m; })()")


_MOVED = ("(function(){const s=window.__abStage.el;"
          "return s.selectedIndex !== window.__abStage.pre.selectedIndex;})()")


async def _act(page, pick):
    """Perform ONE picked interaction and say BY WHAT MECHANISM, so a programmatic selection
    can never be read as a keystroke.

    THE TARGET IS AN ELEMENT HANDLE, NOT A SELECTOR, AND THAT IS NOT A STYLE CHOICE. The first
    version tagged the target `data-ab-stage-target` and removed it after clicking -- and
    setting then removing an attribute IS a DOM mutation, which the readiness probe then
    reported as page activity ~18ms before every post-interaction measurement, on every site.
    That is #70's "our own instrumentation showed up as page activity" rebuilt by someone who
    had read #70, and a 3000ms mutation window means no amount of waiting removes it. A handle
    is a direct reference: this probe now writes NOTHING to the DOM, and `probe_attrs_clean`
    asserts it on every measurement. It also reaches an open shadow root, which a selector
    would only have done by Playwright's piercing CSS engine.

    MEASURED, and the reason the select path is not one line: on macOS Chromium ArrowDown on a
    focused closed <select> changes NOTHING (0 -> 0, no change event) because the platform
    convention is that it opens the native popup -- which is browser UI with no DOM existence,
    so no DOM representation can be measured on it either way. Typeahead works (0 -> 1, a real
    change event) but ONLY for a key Playwright can name: 'B' works, and the first character of
    an option labelled 東京 / Москва / دبي throws `Unknown key`. A third of this sample is
    non-Latin, so leaving it there would have silently reported "select never flips" for every
    non-Latin site -- a harness limit presented as a finding. `select_option` fires the same
    input/change events and leaves the same DOM, which is the collector's entire input."""
    h = await page.evaluate_handle("window.__abStage && window.__abStage.el")
    el = h.as_element()
    if el is None:
        return "no-handle"
    kind = pick["kind"]
    if kind == "select":
        await el.focus()
        if pick.get("typeahead"):
            await page.keyboard.press(pick["typeahead"])
            await page.wait_for_timeout(150)
            if await page.evaluate(_MOVED):
                return "keyboard-typeahead"
        await page.keyboard.press("ArrowDown")      # Linux/Windows convention; no-op on macOS
        await page.wait_for_timeout(150)
        if await page.evaluate(_MOVED):
            return "keyboard-arrow"
        if pick.get("optIndex") is not None:
            await el.select_option(index=pick["optIndex"], timeout=4000)
            return "select_option(programmatic)"
        return "none-available"
    if kind == "text-input":
        await el.click(timeout=4000)
        await page.keyboard.type(TYPED, delay=25)
        return "click+keyboard"
    await el.click(timeout=4000)
    return "click"


def _readiness_summary(rd, net, kinds):
    """Reproduce readinessNote's FIRING CONDITION from background.js, not its prose.

    It fires when any declarative bit is set (images loading / in-flight requests / visible
    progressbar / aria-busy) or when the mutation ring attributes any change to the window.
    `net` stands in for the service worker's `_netPending` (same exclusions)."""
    if not rd or rd.get("error"):
        return {"error": (rd or {}).get("error") or "no readiness", "fired": None}
    bits = []
    if rd.get("imgs"):
        bits.append("imgs=%d" % rd["imgs"])
    if net:
        bits.append("net=%d(%s)" % (net, ",".join(sorted(kinds))))
    if rd.get("prog"):
        bits.append("prog=%d" % rd["prog"])
    if rd.get("busy"):
        bits.append("busy=%d" % rd["busy"])
    m = rd.get("mut") or {}
    moved = 0
    if m and m.get("since", -1) >= 0:
        moved = (m.get("structural", 0) + m.get("text", 0)
                 + sum((m.get("attrs") or {}).values()))
    tier = None
    if moved > 0:
        tier = "strong" if (m.get("structural") or m.get("text")) else "minor"
    elif bits:
        tier = "bits-only"
    return {"fired": bool(tier), "tier": tier, "bits": bits, "moved": moved,
            "since_ms": m.get("since"), "structural": m.get("structural", 0),
            "text": m.get("text", 0), "attrs": m.get("attrs") or {},
            "ready": rd.get("ready"), "blind_frames": rd.get("blindFrames") or 0}


def _stage_row(s, label):
    """One stage reduced to the numbers the tables use."""
    r = {
        "stage": label,
        "entries": s["entries"], "listing_chars": s["listing_chars"],
        "dom_core": s["dom_core"], "dom_deep": s["dom_deep"], "dom_declared": s["dom_declared"],
        "lost_core": s["lost_core"], "lost_deep": s["lost_deep"],
        # The known ad-slot artefact (#82 defect 3) is an <iframe> with tabindex+aria-label whose
        # CONTENTS are listed instead; it is a permitted ledger outcome, counted separately.
        "lost_declared": s["lost_declared"],
        "lost_declared_noniframe": sum(1 for l in s["lost"] if l["arm"] == "declared" and l["tag"] != "iframe"),
        "strict_candidates": s["strict_candidates"],
        "strict_norow_named": s["strict_norow_named"],
        "shadow_roots": s["shadow_roots"], "frames": s["frames"],
        "modal_banner": s["modal_banner"],
        # PERSIST THE VOLUME, not just the exceptions. "0 drop reasons outside SPEC_DELETES"
        # is worth nothing if the ledger returned nothing at all -- the detector-that-cannot-
        # fire shape (PRINCIPLES 15). The first version of this row kept only the exception
        # dict, so the saved data could not tell those two apart and the claim had to be
        # re-established from a fixture afterwards.
        "ledger_drops": s["ledger_drops"],
        "drop_reasons": s["drop_reasons"],
        "unexpected_drop_reasons": s["UNEXPECTED_drop_reasons"],
        "probe_attrs_clean": s.get("probe_attrs_clean"),
        "dialogs_visible": s.get("dialogs_visible"),
        "readiness": s.get("readiness_summary"),
        "lost": [l for l in s["lost"]][:25],
        "strict_examples": s.get("strict_examples", [])[:6],
    }
    return r


async def one(browser, name, url, arch, lang, nstages, shot_dir):
    t0 = time.time()
    ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True,
                                    user_agent=None, locale="en-US")
    inflight = {}

    def _req(r):
        try:
            if r.resource_type in ("websocket", "media"):
                return
            inflight[r] = r.resource_type
        except Exception:
            pass

    def _done(r):
        inflight.pop(r, None)

    base = {"site": name, "url": url, "archetype": arch, "lang": lang}
    try:
        await ctx.add_init_script(path=TAG_JS)
        page = await ctx.new_page()
        page.on("request", _req)
        page.on("requestfinished", _done)
        page.on("requestfailed", _done)
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=GOTO_MS)
            status = resp.status if resp else None
        except Exception as e:
            return dict(base, error="goto: " + str(e)[:120])
        try:
            await page.wait_for_load_state("networkidle", timeout=7000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)

        async def measure(label):
            net = len(inflight)
            kinds = set(inflight.values())
            res = await page.evaluate(_measure_js())
            s = AGL._summ(res)
            s["probe_attrs_clean"] = res.get("probe_attrs_clean")
            s["dialogs_visible"] = res.get("dialogs_visible")
            s["readiness_summary"] = _readiness_summary(res.get("readiness"), net, kinds)
            return _stage_row(s, label), res

        try:
            row0, res0 = await measure("s0")
        except Exception as e:
            return dict(base, error="evaluate: " + str(e)[:160], status=status)

        out = dict(base, final_url=res0["url"], title=(res0["title"] or "")[:80], status=status,
                   stages=[row0])
        seen_names = set(res0["more"]["deep"].get("names") or [])
        if shot_dir:
            try:
                await page.screenshot(path=str(Path(shot_dir) / f"{name}.s0.png"), full_page=False)
            except Exception:
                pass

        used_kinds = collections.Counter()
        picks = []
        # ATTEMPTS, not stages: a declaration whose state does not flip is not a stage (#85's
        # rule) but it has still cost an attempt, and spending the whole budget on a site's
        # first two dead buttons would under-report DEPTH as if the page had nothing to open.
        # Bounded at nstages + 3 so a page of inert aria-expanded buttons still terminates.
        i = 0
        attempts = 0
        while len(out["stages"]) <= nstages and attempts < nstages + 3:
            attempts += 1
            i = len(out["stages"])
            step = {"n": i, "attempt": attempts}
            try:
                pick = await page.evaluate(
                    "(" + STAGE_PICK.strip() + ")(" + json.dumps(
                        {"usedKinds": dict(used_kinds), "maxPerKind": MAX_PER_KIND}) + ")")
            except Exception as e:
                step["error"] = "pick: " + str(e)[:120]
                picks.append(step)
                break
            if not pick:
                step["none_left"] = True
                picks.append(step)
                break
            step.update(pick)
            url_before = page.url
            try:
                step["mechanism"] = await _act(page, pick)
                step["acted"] = True
            except Exception as e:
                step["acted"] = False
                step["act_error"] = str(e).split("\n")[0][:110]
            await page.wait_for_timeout(SETTLE_MS)
            if page.url.split("#")[0] != url_before.split("#")[0]:
                step["navigated"] = True
                picks.append(step)
                break
            try:
                v = await page.evaluate(STAGE_VERIFY)
            except Exception as e:
                step["error"] = "verify: " + str(e)[:120]
                picks.append(step)
                break
            step["verify"] = v
            step["flipped"] = bool(v.get("flipped"))
            used_kinds[pick["kind"]] += 1
            if not step["flipped"]:
                picks.append(step)
                continue              # not counted as a stage; try another declaration
            try:
                row, res = await measure("s%d" % i)
            except Exception as e:
                step["error"] = "measure: " + str(e)[:120]
                picks.append(step)
                break
            row["kind"] = pick["kind"]
            row["nested"] = pick.get("nested")
            # DOES THE REPRESENTATION CARRY WHAT THE INTERACTION PUT THERE? Row-ownership says
            # the control is still listed; it does not say the listing reports its new CONTENTS.
            # That is a different failure (#24's readback class, #82's declared-state class) and
            # the only two interactions that produce a checkable value are these.
            blob = res["ents"] if isinstance(res["ents"], str) else json.dumps(res["ents"], ensure_ascii=False)
            if pick["kind"] == "text-input":
                row["typed_value_in_listing"] = TYPED in res["listing"]
                row["typed_value_in_entries"] = TYPED in blob
            if pick["kind"] == "select":
                ot = ((v.get("now") or {}).get("optionText") or "").strip()
                if ot:
                    row["selected_option_text"] = ot[:60]
                    row["selected_option_in_listing"] = ot in res["listing"]
                    row["selected_option_in_entries"] = ot in blob
            names = set(res["more"]["deep"].get("names") or [])
            new = names - seen_names
            lost_names = {l["name"] for l in row["lost"] if l["arm"] == "deep"}
            row["new_named_controls"] = len(new)
            row["new_named_lost"] = len(new & lost_names)
            row["entries_delta"] = row["entries"] - out["stages"][-1]["entries"]
            seen_names |= names
            out["stages"].append(row)
            picks.append(step)
            if shot_dir:
                try:
                    await page.screenshot(path=str(Path(shot_dir) / f"{name}.s{i}.png"), full_page=False)
                except Exception:
                    pass
        out["picks"] = picks
        out["seconds"] = round(time.time() - t0, 1)
        return out
    finally:
        try:
            await ctx.close()
        except Exception:
            pass


LOSSY_JS = r"""
(function (frac) {
  // Delete a fraction of the REAL listing's rows and the matching entries, then re-run both
  // arms. A probe that reports 0 on an intact page has said nothing until it has been shown to
  // report a loss on a page where one was MANUFACTURED -- and a fixture is not enough, because
  // a fixture is what you thought of (PRINCIPLES 11, 15). The STRICT arm is the one that must
  // scale: the lenient arm is satisfiable by a container's concatenated label, which is exactly
  // why #85 added strict, and this check prices that difference on live markup.
  const r = window.__abLossySrc;
  let ents = r.ents; if (typeof ents === 'string') ents = JSON.parse(ents);
  const ids = ents.map(e => String(e.mmid)).filter(Boolean);
  const drop = new Set();
  for (let i = 0; i < ids.length; i++) if ((i % Math.max(2, Math.round(1 / frac))) === 0) drop.add(ids[i]);
  const keep = ents.filter(e => !drop.has(String(e.mmid)));
  const lines = String(r.listing).split('\n').filter(line => {
    for (const id of drop) { if (new RegExp('(^|[^0-9])' + id + '([^0-9]|$)').test(line)) return false; }
    return true;
  });
  const L = lines.join('\n'), B = JSON.stringify(keep);
  return { dropped_entries: drop.size, total_entries: ents.length,
           core: CORE_PROBE(L, B), more: MORE_PROBE(L, B) };
})
"""


async def lossy_check(browser, name, url, arch, lang, nstages, frac=0.5):
    """Run the stages, then MANUFACTURE a loss at the deepest stage reached and confirm both
    arms report it. Live markup, not a fixture."""
    ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True, locale="en-US")
    try:
        await ctx.add_init_script(path=TAG_JS)
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=GOTO_MS)
        try:
            await page.wait_for_load_state("networkidle", timeout=7000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)
        used = collections.Counter()
        depth = 0
        for _ in range(nstages):
            pick = await page.evaluate("(" + STAGE_PICK.strip() + ")(" + json.dumps(
                {"usedKinds": dict(used), "maxPerKind": MAX_PER_KIND}) + ")")
            if not pick:
                break
            before = page.url
            try:
                await _act(page, pick)
            except Exception:
                pass
            await page.wait_for_timeout(SETTLE_MS)
            if page.url.split("#")[0] != before.split("#")[0]:
                break
            v = await page.evaluate(STAGE_VERIFY)
            used[pick["kind"]] += 1
            if v.get("flipped"):
                depth += 1
        await page.evaluate("window.__abLossySrc = " + _measure_js())
        clean = AGL._summ(await page.evaluate("window.__abLossySrc"))
        js = (LOSSY_JS.replace("CORE_PROBE", "(" + AGL.IS.PROBE.strip() + ")")
                      .replace("MORE_PROBE", "(" + AGL.PROBE2.strip() + ")"))
        mut = await page.evaluate("(" + js.strip() + ")(%r)" % frac)
        return {
            "site": name, "stages_reached": depth, "fraction_dropped": frac,
            "entries_total": mut["total_entries"], "entries_deleted": mut["dropped_entries"],
            "clean": {"lost_core": clean["lost_core"], "lost_deep": clean["lost_deep"],
                      "lost_declared": clean["lost_declared"],
                      "strict_norow_named": clean["strict_norow_named"]},
            "mutilated": {"lost_core": len(mut["core"]["lost"]),
                          "lost_deep": len(mut["more"]["deep"]["lost"]),
                          "lost_declared": len(mut["more"]["declared"]["lost"]),
                          "strict_norow_named": mut["more"]["strict"]["norow_named"]},
            "examples": [x["name"] for x in mut["more"]["deep"]["lost"][:5]],
        }
    finally:
        await ctx.close()


async def run_lossy(sites, nstages, frac):
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        out = []
        for s in sites:
            try:
                out.append(await asyncio.wait_for(lossy_check(b, *s, nstages, frac), 180))
            except Exception as e:
                out.append({"site": s[0], "error": str(e)[:140]})
        await b.close()
    return out


def usable(r):
    """Reuses audit_generality_live's bar, applied to STAGE 0."""
    if "error" in r or not r.get("stages"):
        return False
    s0 = r["stages"][0]
    return s0["dom_core"] >= 10 or s0["entries"] >= 10


def _pool(which, only):
    all_sites = AGL.SITES + AGL.SITES2
    if which == "usable85":
        keep = _usable85()
        all_sites = [s for s in all_sites if s[0] in keep]
    if only:
        all_sites = [s for s in all_sites if s[0] in only]
    return all_sites


def _usable85():
    """Sites that RENDERED in #85's final run. Inheriting that screening is a sample choice,
    stated in the write-up: it spends no time on the 185 candidates #85 already recorded as
    blocked or empty, and it inherits #85's survivorship bias wholesale."""
    names = set()
    d = ROOT / "temp" / "generality_live" / "final"
    for p in sorted(d.glob("pass*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for r in data.get("sites") or []:
            if AGL.usable(r):
                names.add(r["site"])
    return names


def _check_sample(sites):
    bad = []
    for n, u, *_ in sites:
        h = re.sub(r"^www\.", "", urlparse(u).netloc.lower())
        if h in AGL.EXCLUDED:
            bad.append((n, h))
    return bad


async def run_pass(sites, conc, nstages, shot_dir):
    sem = asyncio.Semaphore(conc)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        async def go(s):
            async with sem:
                try:
                    return await asyncio.wait_for(one(browser, *s, nstages, shot_dir), 180)
                except Exception as e:
                    return {"site": s[0], "url": s[1], "archetype": s[2], "lang": s[3],
                            "error": "timeout/" + str(e)[:80]}
        out = await asyncio.gather(*(go(s) for s in sites))
        await browser.close()
    return out


def aggregate(rs):
    ok = [r for r in rs if usable(r)]
    per_stage = collections.defaultdict(lambda: collections.Counter())
    kinds = collections.Counter()
    kind_flip = collections.Counter()
    for r in ok:
        for st in r["stages"]:
            c = per_stage[st["stage"]]
            c["sites"] += 1
            for k in ("dom_core", "dom_deep", "dom_declared", "entries", "lost_core", "lost_deep",
                      "lost_declared_noniframe", "lost_declared", "strict_candidates",
                      "strict_norow_named", "shadow_roots", "frames"):
                c[k] += st[k]
            c["modal_banner"] += 1 if st["modal_banner"] else 0
            c["probe_dirty"] += 0 if st.get("probe_attrs_clean") in (True, None) else 1
            rd = st.get("readiness") or {}
            if rd.get("fired"):
                c["readiness_fired"] += 1
                c["readiness_" + str(rd.get("tier"))] += 1
            c["new_named_controls"] += st.get("new_named_controls", 0)
            c["new_named_lost"] += st.get("new_named_lost", 0)
            c["unexpected_reasons"] += 1 if st["unexpected_drop_reasons"] else 0
        for p in r.get("picks") or []:
            if p.get("kind"):
                kinds[p["kind"]] += 1
                if p.get("flipped"):
                    kind_flip[p["kind"]] += 1
    return {
        "sites_attempted": len(rs), "sites_usable": len(ok),
        "stages_reached": {k: per_stage[k]["sites"] for k in sorted(per_stage)},
        "per_stage": {k: dict(v) for k, v in sorted(per_stage.items())},
        "pick_kinds_tried": dict(kinds.most_common()),
        "pick_kinds_flipped": dict(kind_flip.most_common()),
        "unusable": [{"site": r["site"], "why": r.get("error")
                      or "served <10 controls (dom_core=%s entries=%s)" % (
                          (r.get("stages") or [{}])[0].get("dom_core"),
                          (r.get("stages") or [{}])[0].get("entries"))}
                     for r in rs if not usable(r)],
    }


# --------------------------------------------------------------------------------------
def report(paths):
    rs = []
    for p in paths:
        rs += json.loads(Path(p).read_text(encoding="utf-8"))["sites"]
    ok = [r for r in rs if usable(r)]
    out = ["usable %d of %d attempted" % (len(ok), len(rs))]

    def stage_table(title, rows_of):
        g = collections.defaultdict(lambda: collections.Counter())
        for r in ok:
            for st in r["stages"]:
                c = g[rows_of(r, st)]
                c["n"] += 1
                for k in ("dom_deep", "dom_declared", "entries", "lost_core", "lost_deep",
                          "lost_declared_noniframe", "strict_candidates", "strict_norow_named"):
                    c[k] += st[k]
                c["modal"] += 1 if st["modal_banner"] else 0
                rd = st.get("readiness") or {}
                c["ready"] += 1 if rd.get("fired") else 0
                c["newc"] += st.get("new_named_controls", 0)
                c["newlost"] += st.get("new_named_lost", 0)
        out.append("\n### " + title + "\n")
        out.append("| group | reads | visible controls | declared | entries | LOST lenient core/deep/decl | "
                   "strict: cands / no-row named | NEW named | NEW lost | modal banner | readiness fired |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for k, c in sorted(g.items()):
            out.append("| %s | %d | %d | %d | %d | %d/%d/%d | %d / **%d** | %d | **%d** | %d | %d |" % (
                k, c["n"], c["dom_deep"], c["dom_declared"], c["entries"], c["lost_core"],
                c["lost_deep"], c["lost_declared_noniframe"], c["strict_candidates"],
                c["strict_norow_named"], c["newc"], c["newlost"], c["modal"], c["ready"]))
        return g

    stage_table("by stage", lambda r, st: st["stage"])
    stage_table("by interaction kind (stage >= 1)",
                lambda r, st: st.get("kind") or "(s0 first paint)")
    stage_table("by script family", lambda r, st: AGL.SCRIPT_OF.get(r["lang"], r["lang"]))
    agg = aggregate(rs)
    out.append("\n### interaction kinds: tried -> flipped\n")
    out.append("| kind | tried | flipped |")
    out.append("|---|---|---|")
    for k, v in agg["pick_kinds_tried"].items():
        out.append("| %s | %d | %d |" % (k, v, agg["pick_kinds_flipped"].get(k, 0)))
    out.append("\nunusable / not measured:")
    for u in agg["unusable"]:
        out.append("- %s: %s" % (u["site"], u["why"]))
    return "\n".join(out)


def drift(a_rs, b_rs):
    A = {r["site"]: r for r in a_rs if usable(r)}
    B = {r["site"]: r for r in b_rs if usable(r)}
    both = sorted(set(A) & set(B))
    d = {"sites_compared": len(both), "per_site": {}}
    ent, chars, same_kind, nstage = [], [], 0, 0
    for n in both:
        x, y = A[n], B[n]
        sx, sy = x["stages"][0], y["stages"][0]
        ent.append(abs(sx["entries"] - sy["entries"]))
        chars.append(abs(sx["listing_chars"] - sy["listing_chars"]) / max(1, sx["listing_chars"]))
        kx = [s.get("kind") for s in x["stages"][1:]]
        ky = [s.get("kind") for s in y["stages"][1:]]
        if kx == ky:
            same_kind += 1
        if len(x["stages"]) == len(y["stages"]):
            nstage += 1
        d["per_site"][n] = {
            "stages": [len(x["stages"]), len(y["stages"])], "kinds": [kx, ky],
            "entries_s0": [sx["entries"], sy["entries"]],
            "lost_total": [sum(s["lost_deep"] + s["lost_declared_noniframe"] for s in x["stages"]),
                           sum(s["lost_deep"] + s["lost_declared_noniframe"] for s in y["stages"])],
            "strict_total": [sum(s["strict_norow_named"] for s in x["stages"]),
                             sum(s["strict_norow_named"] for s in y["stages"])],
        }
    ent.sort(); chars.sort()
    d["entries_s0_abs_diff_median"] = ent[len(ent) // 2] if ent else None
    d["entries_s0_abs_diff_mean"] = round(sum(ent) / len(ent), 2) if ent else None
    d["listing_chars_s0_rel_median"] = round(chars[len(chars) // 2], 4) if chars else None
    d["listing_chars_s0_rel_p90"] = round(chars[int(len(chars) * 0.9)], 4) if chars else None
    d["same_stage_count"] = nstage
    d["same_kind_sequence"] = same_kind
    d["lost_in_either_pass"] = sum(
        1 for v in d["per_site"].values() if v["lost_total"][0] or v["lost_total"][1])
    d["strict_in_either_pass"] = sum(
        1 for v in d["per_site"].values() if v["strict_total"][0] or v["strict_total"][1])
    return d


# --------------------------------------------------------------------------------------
SELFTEST_HTML = r"""
<!doctype html><meta charset=utf-8><title>stage fixture</title>
<style>#panel[hidden]{display:none} .pop{display:none} .pop.on{display:block}</style>
<button id=m aria-expanded="false" aria-haspopup="menu" aria-controls="menu">Menu</button>
<div id=menu role=menu class=pop>
  <button id=sub role=menuitem aria-expanded="false" aria-haspopup="menu" aria-controls="sub2">More</button>
  <div id=sub2 role=menu class=pop><button role=menuitem>Deep Item Zeta</button></div>
  <button role=menuitem>Menu Item Alpha</button>
</div>
<details><summary>Summary Beta</summary><button>Inside Details Gamma</button></details>
<div role=tablist><button role=tab aria-selected="true">Tab One</button>
  <button role=tab aria-selected="false" aria-controls=p2>Tab Two</button></div>
<div id=p2 hidden><button>Panel Two Delta</button></div>
<!-- two selects ON PURPOSE: the first has a distinct initial so the KEYSTROKE path runs, the
     second shares one so the programmatic fallback runs. Both are asserted. -->
<select id=sel><option value=1>Opt One</option><option value=2>Beta Two</option></select>
<select id=sel2><option value=1>Same One</option><option value=2>Same Two</option></select>
<input id=txt type=text placeholder="Type here Epsilon">
<a href="https://example.com/away">Leaving Link</a>
<form action="/x"><button type=submit>Submit Button</button></form>
<script>
 m.onclick = () => { const on = m.getAttribute('aria-expanded') === 'true';
   m.setAttribute('aria-expanded', String(!on)); menu.classList.toggle('on', !on); };
 sub.onclick = (e) => { e.stopPropagation(); const on = sub.getAttribute('aria-expanded') === 'true';
   sub.setAttribute('aria-expanded', String(!on)); sub2.classList.toggle('on', !on); };
 document.querySelectorAll('[role=tab]').forEach(t => t.onclick = () => {
   document.querySelectorAll('[role=tab]').forEach(x => x.setAttribute('aria-selected','false'));
   t.setAttribute('aria-selected','true'); p2.hidden = false; });
</script>
"""


async def _selftest():
    """Three things must hold, and a probe that cannot fire is worth nothing (PRINCIPLES 11, 15).

    1. The picker reaches each declared kind, never a link or a submit, and compounds: stage 2
       must pick the submenu INSIDE the menu stage 1 opened.
    2. The flip test is real: a click that changes nothing must NOT count as a stage.
    3. THE LOSS METRIC FIRES AT A POST-INTERACTION STAGE. A control revealed only by the
       interaction, with its name removed from the listing and the blob, must be reported lost
       by BOTH arms. Without this, a run of zeros says nothing.
    """
    fails = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport=VIEWPORT)
        await ctx.add_init_script(path=TAG_JS)
        pg = await ctx.new_page()
        await pg.set_content(SELFTEST_HTML)
        await pg.wait_for_timeout(200)

        used = collections.Counter()
        seq = []
        for i in range(10):
            pick = await pg.evaluate("(" + STAGE_PICK.strip() + ")(" + json.dumps(
                {"usedKinds": dict(used), "maxPerKind": MAX_PER_KIND}) + ")")
            if not pick:
                break
            mech = await _act(pg, pick)
            await pg.wait_for_timeout(120)
            v = await pg.evaluate(STAGE_VERIFY)
            used[pick["kind"]] += 1
            seq.append({"kind": pick["kind"], "nested": pick.get("nested"),
                        "mechanism": mech, "flipped": v["flipped"]})
            if pick["kind"] == "menu-popup" and used["menu-popup"] == 2 and not pick.get("nested"):
                fails.append("stage 2 did not compound inside the opened menu")

        kinds = [s["kind"] for s in seq if s["flipped"]]
        if "menu-popup" not in kinds:
            fails.append("never picked menu-popup")
        if kinds.count("menu-popup") < 2:
            fails.append("never reached the SUBMENU (second menu-popup)")
        # The fixture carries a real link and a real submit; picking either would mean the
        # navigation guard is decided by something other than the declaration.
        if any(s["kind"] in ("link", "submit") for s in seq):
            fails.append("picked a navigating control")
        for want in ("details", "tab", "select", "text-input"):
            if want not in kinds:
                fails.append("tier diversification never FLIPPED kind %r (got %s)" % (want, kinds))
        # BOTH select mechanisms must be alive. Without this the probe could fall back to
        # select_option every time and nobody would see that the keystroke path had died.
        mechs = {s["mechanism"] for s in seq if s["kind"] == "select" and s["flipped"]}
        if "keyboard-typeahead" not in mechs:
            fails.append("the select KEYSTROKE path never fired (mechanisms seen: %s)" % mechs)
        if "select_option(programmatic)" not in mechs:
            fails.append("the select fallback never fired (mechanisms seen: %s)" % mechs)

        # 2. a click that flips nothing is not a stage
        await pg.set_content("<button aria-expanded='false' aria-haspopup='menu'>Inert</button>")
        await pg.wait_for_timeout(50)
        pick = await pg.evaluate("(" + STAGE_PICK.strip() + ")({})")
        await _act(pg, pick)
        v = await pg.evaluate(STAGE_VERIFY)
        if v["flipped"]:
            fails.append("a click that changed no declared state counted as a flip")
        dirty = await pg.evaluate(
            "(function(){const o=[];for(const e of document.querySelectorAll('*'))"
            "for(const a of e.getAttributeNames())if(a.indexOf('data-ab')===0)o.push(a);return o;})()")
        if dirty:
            fails.append("the probe wrote attributes into the measured DOM: %s" % sorted(set(dirty)))

        # 3. THE METRIC MUST FIRE POST-INTERACTION
        await pg.set_content(SELFTEST_HTML)
        await pg.wait_for_timeout(150)
        pick = await pg.evaluate("(" + STAGE_PICK.strip() + ")({})")
        await _act(pg, pick)
        await pg.wait_for_timeout(200)
        await pg.evaluate(STAGE_VERIFY)
        res = await pg.evaluate(_measure_js())
        clean = AGL._summ(res)
        revealed = "Menu Item Alpha"
        if revealed not in res["listing"]:
            fails.append("fixture never revealed %r, so the mutilation check is vacuous" % revealed)
        if clean["lost_core"] or clean["lost_deep"] or clean["lost_declared"]:
            fails.append("clean post-interaction read already reports a loss: %s" % clean["lost"][:2])
        if clean["strict_norow_named"]:
            fails.append("clean post-interaction read reports a strict no-row: %s"
                         % clean["strict_examples"][:2])
        # mutilate: delete that control's row and entry, exactly as a collector defect would
        mutilated = await pg.evaluate(
            "(function(nm){ " + READY_FN + ";"
            " const r = " + AGL._measure_js() + ";"
            " const L = String(r.listing).split('\\n').filter(x => x.indexOf(nm) < 0).join('\\n');"
            " let ents = r.ents; if (typeof ents === 'string') ents = JSON.parse(ents);"
            " const keep = ents.filter(e => JSON.stringify(e).indexOf(nm) < 0);"
            " const B = JSON.stringify(keep);"
            " return { core: (" + AGL.IS.PROBE.strip() + ")(L, B),"
            "          more: (" + AGL.PROBE2.strip() + ")(L, B) }; })",
            revealed)
        lost_names = ([x["name"] for x in mutilated["core"]["lost"]]
                      + [x["name"] for x in mutilated["more"]["deep"]["lost"]])
        if revealed not in lost_names:
            fails.append("MUTILATION DID NOT FIRE: removed %r and the metric still reports no loss"
                         % revealed)
        strict_names = [x["name"] for x in mutilated["more"]["strict"]["norow"]]
        if revealed not in strict_names:
            fails.append("STRICT arm did not fire on the mutilated listing")
        await b.close()
    print("selftest", "PASS" if not fails else "FAIL")
    print(json.dumps({"stage_sequence": seq, "revealed_control": revealed,
                      "lenient_fired_on": lost_names[:5], "strict_fired_on": strict_names[:5],
                      "failures": fails}, indent=1, ensure_ascii=False))
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--pool", default="usable85", choices=("usable85", "all"))
    ap.add_argument("--stages", type=int, default=4)
    ap.add_argument("--conc", type=int, default=6)
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--report", nargs="+")
    ap.add_argument("--shots", action="store_true")
    ap.add_argument("--lossy", action="store_true",
                    help="manufacture a loss on the LIVE sites in --only and check both arms fire")
    ap.add_argument("--frac", type=float, default=0.5)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    if a.selftest:
        return asyncio.run(_selftest())
    if a.report:
        print(report(a.report))
        return 0
    sites = _pool(a.pool, a.only)
    bad = _check_sample(sites)
    if bad:
        print("SAMPLE CONTAINS EXCLUDED HOSTS (frozen corpus / bench_turns / bench_flows):", bad)
        return 2
    if a.list:
        for s in sites:
            print(*s, sep="\t")
        print(len(sites), "sites;", len(AGL.EXCLUDED), "excluded hosts checked")
        return 0
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.lossy:
        res = asyncio.run(run_lossy(sites, a.stages, a.frac))
        (out / "lossy.json").write_text(json.dumps(res, indent=1, ensure_ascii=False),
                                        encoding="utf-8")
        bad = [r for r in res if "error" not in r
               and not (r["mutilated"]["strict_norow_named"] > r["clean"]["strict_norow_named"])]
        for r in res:
            print(json.dumps(r, ensure_ascii=False))
        print("LOSSY:", "PASS" if res and not bad else "FAIL",
              "- sites where the manufactured loss did NOT raise the strict arm:",
              [r["site"] for r in bad])
        return 0 if (res and not bad) else 1
    shot_dir = None
    if a.shots:
        shot_dir = out / "shots"
        shot_dir.mkdir(exist_ok=True)
        shot_dir = str(shot_dir)
    runs = [asyncio.run(run_pass(sites, a.conc, a.stages, shot_dir))]
    if a.compare:
        runs.append(asyncio.run(run_pass(sites, a.conc, a.stages, None)))
    for i, rs in enumerate(runs):
        (out / f"pass{i}.json").write_text(
            json.dumps({"aggregate": aggregate(rs), "sites": rs}, indent=1, ensure_ascii=False),
            encoding="utf-8")
        print(f"pass {i}:", json.dumps(aggregate(rs)["stages_reached"]),
              json.dumps({k: {kk: vv for kk, vv in v.items()
                              if kk in ("sites", "dom_deep", "lost_deep", "lost_core",
                                        "lost_declared_noniframe", "strict_norow_named",
                                        "readiness_fired", "modal_banner", "probe_dirty")}
                          for k, v in aggregate(rs)["per_stage"].items()}))
    if a.compare:
        d = drift(runs[0], runs[1])
        (out / "drift.json").write_text(json.dumps(d, indent=1), encoding="utf-8")
        print("DRIFT:", json.dumps({k: v for k, v in d.items() if k != "per_site"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
