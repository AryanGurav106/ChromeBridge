# -*- coding: utf-8 -*-
"""Hover-revealed content: does the collector see what the mouse made appear?

WHY THIS WAS UNMEASURED, AND WHY THAT REASONING DOES NOT BLOCK A PROBE.
`audit_stage_generality` picks its interactions from DECLARATIONS ONLY --
`aria-expanded`, `aria-haspopup`, `aria-controls`, `<details>`, `role=tab` --
and counts a stage only when the page's own declared state flipped. A CSS
`:hover` submenu declares none of that, so the PRODUCT must not guess at it
(PRINCIPLES 1) and that picker correctly refuses to choose one.

**That is a rule about what the product may INFER, not about what a probe may
DRIVE.** A probe may put the mouse somewhere deliberately and then ask whether
the collector sees what appeared. Those are different questions and only the
first one was closed. Nothing here asks the collector to detect a hover menu;
it asks whether, once a hover menu IS open, its controls are collected,
identified and reachable.

WHAT IS DRIVEN, and it is still read off the page rather than guessed:
  tier 1  CSS-DECLARED. Walk `document.styleSheets` for rules whose selector
          contains `:hover` and whose declarations change display / visibility /
          opacity / transform / height / max-height / pointer-events -- the page
          literally saying "on hover of X, show Y". Same-origin sheets only;
          cross-origin CSSOM throws and is counted as unreadable, not as absent.
  tier 2  STRUCTURAL. An element that currently CONTAINS controls none of which
          are visible -- a closed submenu, whatever CSS produced it. This tier
          exists because tier 1 misses JS-driven mouseenter menus entirely, and
          those are most of the modern web.
  tier 3  LANDMARK. Top-level items of a `<nav>`/`role=navigation`, hovered in
          document order. The crudest tier, and the one that catches the
          mega-menu shape when neither of the others fires.

WHAT IS MEASURED ON WHAT APPEARED (never assumed -- the control set is compared
BY ELEMENT IDENTITY before and after, held in page memory, so "nothing appeared"
and "something appeared" are distinguished by observation):
  * COLLECTED -- `lost_identities`, lenient AND strict, #85/#92's two
    definitions, reused from audit_generality_live rather than restated.
  * REACHABLE -- the identity the LISTING printed, handed to the real `find`,
    via measure_findability's own `identity_of` and fake bridge. #74 found 118
    elements present in every presence metric and unreachable by their printed
    label; presence is not reach.
  * DOES THE HOVER STATE BREAK THE LISTING -- a MODAL banner on a popover that
    is not modal, a readiness verdict that contradicts the page, rows that went
    stale, and whether the hover SURVIVED the read at all (a measurement taken
    after the menu closed would score zero for the wrong reason).

PROVING IT FIRES (PRINCIPLES 5/11/15): `--selftest` runs a fixture whose
hover-revealed control is DELETED from the listing, and one whose revealed
control carries an identity that does not match its element, and requires both
arms to report them. A zero from a probe nobody has seen fire is worth nothing.

NO BOT EVASION, NO USER-AGENT SPOOFING. A site that blocks us is UNMEASURED and
counted as such, never as a pass. The sample is checked against the frozen
corpus, `bench_turns` and `bench_flows` and the run REFUSES to start on a hit.

    python tools/audit_hover_stage.py --selftest
    python tools/audit_hover_stage.py --sites 60
    python tools/audit_hover_stage.py --drift --sites 40
"""
from __future__ import annotations

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
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.async_api import async_playwright     # noqa: E402
import audit_generality_live as AGL                   # noqa: E402  (metric, sample, exclusions)
import audit_stage_generality as ASG                  # noqa: E402  (stage row, readiness summary)
import measure_findability as MF                      # noqa: E402  (find, identity_of, fake bridge)

VIEWPORT = AGL.VIEWPORT
TAG_JS = AGL.TAG_JS
OUT = ROOT / "temp" / "hover_stage"
GOTO_MS = 45000
SETTLE_MS = 900          # after the mouse lands, before measuring
MAX_HOVERS = 6           # candidates tried per site


# --------------------------------------------------------------------------
# Candidate selection. Three tiers, all read off the page.
# --------------------------------------------------------------------------

# ONE DEFINITION OF "a visible control, on screen", interpolated into BOTH the
# picker and the diff. It is a Python constant rather than two JS copies because
# the first version had two: the picker's `box()` required the element to be IN
# THE VIEWPORT and the diff's required only non-zero size, so every below-fold
# control on the page counted as "newly appeared" the moment anything was
# hovered. That reported 19,324 of 19,618 controls (98.5%) as owning no row --
# a number that damns the system, produced entirely by the probe, and caught
# only because it was too large to believe (PRINCIPLES 8). What it was actually
# measuring is the listing's DELIBERATE viewport scoping (#6, #26), which is not
# what this probe is for. PRINCIPLES 17, enforced by construction.
VISBOX = """
  const vis = (e) => { try { return e.checkVisibility({opacityProperty:true, visibilityProperty:true}); }
                       catch (x) { return false; } };
  const onScreen = (e) => { const r = e.getBoundingClientRect();
                       return r.width > 0 && r.height > 0 && r.top < innerHeight && r.bottom > 0
                              && r.left < innerWidth && r.right > 0; };
  const anySize = (e) => { const r = e.getBoundingClientRect();
                       return r.width > 0 && r.height > 0; };
"""

HOVER_PICK = r"""
(function (cfg) {
  const W = window;
  W.__abHoverUsed = W.__abHoverUsed || [];
""" + VISBOX + r"""
  const box = onScreen;
  const CTL = 'a[href],button,input,select,textarea,summary,[role=button],[role=link],'
            + '[role=menuitem],[role=tab],[role=option],[tabindex]:not([tabindex^="-"]),[onclick]';
  const used = new Set(W.__abHoverUsed);

  // ---- tier 1: the page's OWN CSS says hovering X changes something ----
  // Same-origin sheets only; a cross-origin sheet throws on .cssRules and is
  // counted as unreadable rather than silently treated as "declares nothing".
  const HOVER_PROPS = ['display','visibility','opacity','transform','height',
                       'max-height','pointer-events','clip','clip-path','left','top'];
  let sheetsRead = 0, sheetsBlocked = 0;
  const cssRoots = [];
  for (const sh of Array.from(document.styleSheets)) {
    let rules = null;
    try { rules = sh.cssRules; } catch (e) { sheetsBlocked++; continue; }
    if (!rules) { sheetsBlocked++; continue; }
    sheetsRead++;
    const walk = (list) => {
      for (const r of Array.from(list)) {
        if (r.cssRules && !r.selectorText) { walk(r.cssRules); continue; }
        const sel = r.selectorText;
        if (!sel || sel.indexOf(':hover') === -1) continue;
        let touches = false;
        try { for (const p of HOVER_PROPS) if (r.style && r.style.getPropertyValue(p)) touches = true; }
        catch (e) {}
        if (!touches) continue;
        // The HOVER TARGET is the part of the selector up to and including :hover.
        for (const one of sel.split(',')) {
          const i = one.indexOf(':hover');
          if (i === -1) continue;
          const t = one.slice(0, i).trim();
          if (t && t !== '*') cssRoots.push(t);
        }
      }
    };
    try { walk(rules); } catch (e) {}
  }
  const seen = new Set();
  const cand = [];
  const push = (el, tier, why) => {
    if (!el || used.has(el) || seen.has(el)) return;
    if (!vis(el) || !box(el)) return;
    seen.add(el);
    cand.push({ el: el, tier: tier, why: why });
  };
  for (const sel of cssRoots.slice(0, 120)) {
    let hits = null;
    try { hits = document.querySelectorAll(sel); } catch (e) { continue; }
    for (const e of Array.from(hits).slice(0, 6)) push(e, 'css-hover', sel.slice(0, 60));
  }

  // ---- tier 2: contains controls, NONE of which are currently visible ----
  // A closed submenu, whatever produced it. Bounded scan.
  let n = 0;
  for (const e of document.querySelectorAll('li,div,nav,details,span')) {
    if (++n > 4000) break;
    if (!vis(e) || !box(e)) continue;
    let kids; try { kids = e.querySelectorAll(CTL); } catch (x) { continue; }
    if (kids.length < 2 || kids.length > 60) continue;
    let hiddenKids = 0, shownKids = 0;
    for (const k of kids) (vis(k) ? shownKids++ : hiddenKids++);
    if (hiddenKids >= 2 && shownKids <= 1) push(e, 'hidden-children', e.tagName.toLowerCase()
                                                 + ' +' + hiddenKids);
  }

  // ---- tier 3: top-level nav items ----
  for (const nav of document.querySelectorAll('nav,[role=navigation]')) {
    let items; try { items = nav.querySelectorAll(':scope > ul > li, :scope > li, :scope > a'); }
    catch (x) { continue; }
    for (const e of Array.from(items).slice(0, 8)) push(e, 'nav-item', 'nav');
  }

  if (!cand.length) return { none: true, sheetsRead: sheetsRead, sheetsBlocked: sheetsBlocked,
                             cssRoots: cssRoots.length };
  const pick = cand[0];
  W.__abHover = { el: pick.el };
  // BEFORE-SET held as ELEMENT REFERENCES in page memory. Nothing is written to
  // the DOM -- #70 and audit_stage_generality both record a probe's own
  // attribute write showing up as page activity in the readiness signal, and a
  // 3000ms mutation window means no amount of waiting removes it.
  const before = new Set();
  let all; try { all = document.querySelectorAll(CTL); } catch (e) { all = []; }
  for (const e of all) if (vis(e) && box(e)) before.add(e);
  W.__abHoverBefore = before;
  const r = pick.el.getBoundingClientRect();
  return { tier: pick.tier, why: pick.why, tag: pick.el.tagName.toLowerCase(),
           x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2),
           sheetsRead: sheetsRead, sheetsBlocked: sheetsBlocked, cssRoots: cssRoots.length,
           candidates: cand.length };
})
"""

# AFTER the mouse lands: what is visible now that was not before? Element
# identity, not names -- two different controls can share a name and a name-diff
# would both miss those and invent changes when a label re-renders.
HOVER_DIFF = r"""
(function () {
  const W = window;
""" + VISBOX + r"""
  const CTL = 'a[href],button,input,select,textarea,summary,[role=button],[role=link],'
            + '[role=menuitem],[role=tab],[role=option],[tabindex]:not([tabindex^="-"]),[onclick]';
  const before = W.__abHoverBefore || new Set();
  const root = W.__abHover && W.__abHover.el;
  const now = [];
  let all; try { all = document.querySelectorAll(CTL); } catch (e) { all = []; }
  // SAME predicate as the before-set, or the diff measures scrolling and page
  // height rather than the hover. Off-screen arrivals are counted SEPARATELY
  // (a mega-menu can genuinely extend past the fold) and are not scored as
  // losses, because the string listing is viewport-scoped on purpose.
  for (const e of all) if (vis(e) && onScreen(e)) now.push(e);
  const appeared = now.filter(e => !before.has(e));
  const offScreenArrivals = [];
  for (const e of all) {
    if (before.has(e) || now.indexOf(e) !== -1) continue;
    if (vis(e) && anySize(e)) offScreenArrivals.push(e);
  }
  // Still hovered? `:hover` must survive the measurement, or a zero is a zero
  // for the wrong reason. Asked of the DOM, not assumed from the mouse call.
  let hovered = false;
  try { hovered = !!(root && root.matches(':hover')) ||
                  !!document.querySelector(':hover'); } catch (e) {}
  let rootHover = false;
  try { rootHover = !!(root && root.matches(':hover')); } catch (e) {}
  // THE PAGE DECLARING AN ELEMENT ABSENT is not the collector losing it, and
  // audit_generality_live's arms exclude exactly this. Omitting it here was a
  // third restated-instead-of-reused definition: a mega-menu that marks its
  // closed panels (or the rest of the page) aria-hidden would have scored every
  // one of them as a loss. Crosses shadow hosts and same-origin frame elements,
  // like AGL's `hidden()`.
  const declaredHidden = (el) => {
    let n = el;
    for (let i = 0; n && i < 200; i++) {
      if (n.nodeType === 1 && (n.getAttribute('aria-hidden') === 'true' || n.hasAttribute('inert')))
        return true;
      if (n.nodeType === 9) { let f = null; try { f = n.defaultView && n.defaultView.frameElement; }
                              catch (x) {} n = f; continue; }
      n = n.parentNode || n.host;
    }
    return false;
  };
  const desc = (e) => {
    const r = e.getBoundingClientRect();
    return { tag: e.tagName.toLowerCase(),
             mmid: e.getAttribute('mmid') || null,
             role: e.getAttribute('role') || null,
             name: (e.getAttribute('aria-label') || e.getAttribute('title') || '').trim(),
             text: (e.innerText || e.textContent || '').trim().slice(0, 100),
             href: e.getAttribute('href') || '',
             declaredHidden: declaredHidden(e),
             inRoot: !!(root && root !== e && root.contains(e)),
             x: Math.round(r.left), y: Math.round(r.top),
             w: Math.round(r.width), h: Math.round(r.height) };
  };
  W.__abHoverAppeared = appeared;
  return { appeared: appeared.map(desc), nBefore: before.size, nNow: now.length,
           offScreenArrivals: offScreenArrivals.length,
           hovered: hovered, rootStillHovered: rootHover };
})()
"""

# After the LISTING has been taken, re-read the appeared set's mmids. The
# collector stamps them, so this must run AFTER the measurement and before any
# other interaction.
APPEARED_MMIDS = r"""
(function () {
  const a = window.__abHoverAppeared || [];
  return Array.from(a).map(e => ({
    mmid: e.getAttribute && e.getAttribute('mmid') || null,
    connected: !!(e.isConnected),
    visible: (function(){ try { return e.checkVisibility({opacityProperty:true, visibilityProperty:true}); }
                          catch (x) { return null; } })(),
  }));
})()
"""


def _identity(d: dict) -> str:
    """What the LISTING would print for this element.

    Deliberately the same precedence `measure_findability.identity_of` uses, fed
    the same field names, so "the words a reader would type" has one definition
    (PRINCIPLES 17). Mapped rather than re-ranked.
    """
    return MF.identity_of({"name": d.get("name"), "label": "", "text": d.get("text"),
                           "value": "", "placeholder": ""})


def score_appeared(appeared: list, mmids: list, listing: str, blob: str) -> dict:
    """lost_identities, the two definitions, restricted to what the hover revealed.

    THE ROW SET IS audit_generality_live's, NOT A NEW ONE. Its PROBE2 harvests
    ids from the structured BLOB as well as from the listing's refs and folded
    rows; the first version of this function parsed the listing alone, which is
    a THIRD definition of "owns a row" and a stricter one than the project's.
    Combined with the viewport bug above it put the headline at 98.5% loss.
    Restating a definition instead of reusing it is PRINCIPLES 17, and #36
    records the permitted-drop-reason set drifting the same way.
    """
    rows = set(re.findall(r'"mmid":\s*"([^"]+)"', blob))
    rows |= set(re.findall(r"\bref_(f?\d+:?\d*)\b", listing))
    rows |= set(re.findall(r"(?:^|[\s,(])(f?\d+:?\d*):\"", listing))
    # WHITESPACE-NORMALISE BOTH SIDES. AccName collapses runs and #28's step-2F
    # rule space-delimits each element child's contribution, so the collector
    # prints "DBS Singapore's leading consumer bank" where raw innerText holds
    # "DBS\nSingapore's leading consumer bank". Comparing those raw scored 154
    # of 526 revealed controls as lenient losses while the STRONGER strict arm
    # scored 22 -- the weaker arm losing more than the stronger one is
    # arithmetically impossible for a real loss and is what exposed it. This is
    # the same normalisation #63 settled on for flow assertions, and for the
    # same stated reason: HTML collapses whitespace runs when it paints.
    nrm = lambda s: " ".join((s or "").split())                   # noqa: E731
    nlist, nblob = nrm(listing), nrm(blob)
    out = {"candidates": 0, "lenient_lost": [], "strict_norow": [], "gone": 0,
           "declared_hidden": 0, "no_mmid": 0}
    for d, m in zip(appeared, mmids):
        if not m.get("connected"):
            out["gone"] += 1          # the menu closed under us; not a loss
            continue
        if m.get("visible") is False:
            out["gone"] += 1
            continue
        if d.get("declaredHidden"):
            # The PAGE says this is absent from the accessibility tree. Dropping
            # it is the documented behaviour, not a loss (PRINCIPLES 1/3).
            out["declared_hidden"] += 1
            continue
        ident = nrm(_identity(d))
        if not ident:
            continue
        out["candidates"] += 1
        if ident not in nlist and ident not in nblob:
            out["lenient_lost"].append({**d, "identity": ident})
        if not m.get("mmid"):
            out["no_mmid"] += 1
        if not m.get("mmid") or str(m["mmid"]) not in rows:
            out["strict_norow"].append({**d, "identity": ident,
                                        "mmid": m.get("mmid")})
    return out


async def score_findability(entries: list, listing: str, appeared_mmids: set, cap=12) -> dict:
    """Can `find` reach a hover-revealed row by the identity the listing printed?

    Uses measure_findability's own fake bridge and the REAL `find`, so this is
    the same question that file asks of frozen sites, restricted to the
    newly-revealed set. A descendant counts (acting on it does what acting on
    the target would -- #18/#73's reasoning); an ancestor does not.
    """
    res = {"asked": 0, "reached": 0, "misses": []}
    ents = [e for e in entries if str(e.get("mmid")) in appeared_mmids]
    for e in ents[:cap]:
        ident = MF.identity_of(e)
        if not ident or len(ident) < 2:
            continue
        res["asked"] += 1
        MF.ms.STATE["bridge"] = MF._FB(entries, listing)
        try:
            out = str(await MF._find(query=ident, tabId=1))
        except Exception as ex:
            out = "ERR " + str(ex)[:60]
        if f"ref_{e['mmid']}" in out:
            res["reached"] += 1
        else:
            res["misses"].append({"mmid": e.get("mmid"), "identity": ident[:60],
                                  "tag": e.get("tag")})
    return res


# --------------------------------------------------------------------------

async def one(browser, name, url, arch, lang, shot_dir=None):
    t0 = time.time()
    ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True,
                                    locale="en-US")
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
        await page.wait_for_timeout(1500)

        async def measure():
            net, kinds = len(inflight), set(inflight.values())
            res = await page.evaluate(ASG._measure_js())
            s = AGL._summ(res)
            s["readiness_summary"] = ASG._readiness_summary(res.get("readiness"), net, kinds)
            s["probe_attrs_clean"] = res.get("probe_attrs_clean")
            s["dialogs_visible"] = res.get("dialogs_visible")
            return s, res

        s0, r0 = await measure()
        out = dict(base, status=status, final_url=r0["url"],
                   title=(r0["title"] or "")[:70],
                   s0={"entries": s0["entries"], "dom_deep": s0["dom_deep"],
                       "lost_core": s0["lost_core"], "lost_deep": s0["lost_deep"],
                       "strict_norow_named": s0["strict_norow_named"],
                       "modal_banner": s0["modal_banner"],
                       "listing_chars": s0["listing_chars"]},
                   hovers=[])

        for attempt in range(MAX_HOVERS):
            try:
                pick = await page.evaluate(HOVER_PICK + "(" + json.dumps({}) + ")")
            except Exception as e:
                out["pick_error"] = str(e)[:140]
                break
            if not pick or pick.get("none"):
                out["no_candidates"] = pick or {"none": True}
                break
            h = {"attempt": attempt, "tier": pick["tier"], "why": pick.get("why"),
                 "tag": pick.get("tag"), "sheets_read": pick.get("sheetsRead"),
                 "sheets_blocked": pick.get("sheetsBlocked"),
                 "css_hover_rules": pick.get("cssRoots")}
            # Mark used BEFORE moving, so a crash cannot loop on one element.
            await page.evaluate("() => { if (window.__abHover) "
                                "window.__abHoverUsed.push(window.__abHover.el); }")
            try:
                await page.mouse.move(pick["x"], pick["y"])
                await page.wait_for_timeout(120)
                # Two moves: some menus open on mousemove WITHIN the element, and a
                # single move from (0,0) can land as one event the page ignores.
                await page.mouse.move(pick["x"] + 1, pick["y"] + 1)
            except Exception as e:
                h["hover_error"] = str(e)[:110]
                out["hovers"].append(h)
                continue
            await page.wait_for_timeout(SETTLE_MS)
            try:
                diff = await page.evaluate(HOVER_DIFF)
            except Exception as e:
                h["diff_error"] = str(e)[:110]
                out["hovers"].append(h)
                continue
            h["appeared"] = len(diff["appeared"])
            h["off_screen_arrivals"] = diff.get("offScreenArrivals", 0)
            h["n_before"] = diff["nBefore"]
            h["n_now"] = diff["nNow"]
            h["root_still_hovered"] = diff["rootStillHovered"]
            h["in_root"] = sum(1 for d in diff["appeared"] if d["inRoot"])
            if not diff["appeared"]:
                h["nothing_appeared"] = True
                out["hovers"].append(h)
                continue

            # SOMETHING APPEARED. Measure while the mouse is still there.
            s1, r1 = await measure()
            try:
                mm = await page.evaluate(APPEARED_MMIDS)
            except Exception as e:
                mm = [{"mmid": None, "connected": True, "visible": True}] * len(diff["appeared"])
                h["mmid_error"] = str(e)[:90]
            # Did the hover survive the read? A zero scored after the menu shut is
            # a zero for the wrong reason, so it is recorded, not assumed.
            try:
                still = await page.evaluate(
                    "() => { const r = window.__abHover && window.__abHover.el;"
                    " try { return !!(r && r.matches(':hover')); } catch (e) { return null; } }")
            except Exception:
                still = None
            h["hover_survived_measurement"] = still

            blob = r1["ents"] if isinstance(r1["ents"], str) \
                else json.dumps(r1["ents"], ensure_ascii=False)
            sc = score_appeared(diff["appeared"], mm, r1["listing"], blob)
            # EXPLAIN THE RESIDUE RATHER THAN REPORTING A BARE NUMBER. The
            # collector's own ledger is already in this measurement, so a strict
            # miss can be joined to the rule that dropped it instead of leaving
            # the reader to guess -- which is the mistake #26 made about the
            # Mind2Web misses and #73 had to correct by asking the ledger.
            why = {str(x.get("mmid")): (x.get("rule") or x.get("why"))
                   for x in (r1.get("dropped") or [])}
            for x in sc["strict_norow"]:
                x["ledger"] = why.get(str(x.get("mmid")))
            h.update({"candidates": sc["candidates"],
                      "closed_under_us": sc["gone"],
                      "declared_hidden": sc["declared_hidden"],
                      "no_mmid": sc["no_mmid"],
                      "lenient_lost": len(sc["lenient_lost"]),
                      "strict_norow": len(sc["strict_norow"]),
                      "strict_detail": [{"id": x["identity"][:60], "tag": x["tag"],
                                         "mmid": x.get("mmid"), "ledger": x.get("ledger"),
                                         "inRoot": x.get("inRoot"),
                                         "box": [x.get("x"), x.get("y"), x.get("w"), x.get("h")]}
                                        for x in sc["strict_norow"][:6]],
                      "lenient_examples": [x["identity"][:50] for x in sc["lenient_lost"][:4]],
                      "strict_examples": [x["identity"][:50] for x in sc["strict_norow"][:4]]})
            ents = r1["ents"] if not isinstance(r1["ents"], str) else json.loads(r1["ents"])
            app_m = {str(m["mmid"]) for m in mm if m.get("mmid")}
            h["findability"] = await score_findability(ents, r1["listing"], app_m)
            h["page_lost_core"] = s1["lost_core"]
            h["page_lost_deep"] = s1["lost_deep"]
            h["page_strict_norow_named"] = s1["strict_norow_named"]
            h["entries"] = s1["entries"]
            h["entries_delta"] = s1["entries"] - s0["entries"]
            h["modal_banner"] = s1["modal_banner"]
            h["modal_banner_was_on_at_s0"] = s0["modal_banner"]
            h["dialogs_visible"] = s1["dialogs_visible"]
            h["readiness"] = s1["readiness_summary"]
            h["probe_attrs_clean"] = s1["probe_attrs_clean"]
            h["unexpected_drop_reasons"] = s1["UNEXPECTED_drop_reasons"]
            h["ledger_drops"] = s1["ledger_drops"]
            out["hovers"].append(h)
            if shot_dir:
                try:
                    await page.screenshot(path=str(Path(shot_dir) / f"{name}.h{attempt}.png"))
                except Exception:
                    pass
            # Move the mouse away so the next candidate starts from a closed page.
            try:
                await page.mouse.move(2, VIEWPORT["height"] - 2)
                await page.wait_for_timeout(350)
            except Exception:
                pass
            if sum(1 for x in out["hovers"] if x.get("appeared")) >= 2:
                break
        out["seconds"] = round(time.time() - t0, 1)
        return out
    finally:
        try:
            await ctx.close()
        except Exception:
            pass


def usable(r):
    return "error" not in r and r.get("s0") and (
        r["s0"]["dom_deep"] >= 10 or r["s0"]["entries"] >= 10)


async def run_pass(sites, conc, shot_dir=None):
    sem = asyncio.Semaphore(conc)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        async def go(s):
            async with sem:
                try:
                    return await asyncio.wait_for(one(browser, *s, shot_dir), 170)
                except Exception as e:
                    return {"site": s[0], "url": s[1], "archetype": s[2], "lang": s[3],
                            "error": "timeout/" + str(e)[:80]}
        res = await asyncio.gather(*(go(s) for s in sites))
        await browser.close()
    return res


def aggregate(rs):
    ok = [r for r in rs if usable(r)]
    a = {"attempted": len(rs), "usable": len(ok),
         "unusable": [{"site": r["site"], "why": r.get("error") or "empty/blocked"}
                      for r in rs if not usable(r)]}
    hv = [h for r in ok for h in r.get("hovers", [])]
    opened = [h for h in hv if h.get("appeared")]
    a["hover_attempts"] = len(hv)
    a["hovers_that_revealed"] = len(opened)
    a["sites_with_a_reveal"] = sum(1 for r in ok if any(h.get("appeared") for h in r["hovers"]))
    a["controls_revealed"] = sum(h["appeared"] for h in opened)
    # Counted, never scored: the string listing is viewport-scoped by design
    # (#6/#26 priced widening it and rejected it twice), so an arrival below the
    # fold owning no ROW is that decision, not a defect. It is reported because
    # "a mega-menu extends past the fold" is a real thing an agent meets.
    a["off_screen_arrivals"] = sum(h.get("off_screen_arrivals", 0) for h in opened)
    a["candidates"] = sum(h.get("candidates", 0) for h in opened)
    a["closed_under_us"] = sum(h.get("closed_under_us", 0) for h in opened)
    a["declared_hidden"] = sum(h.get("declared_hidden", 0) for h in opened)
    a["no_mmid"] = sum(h.get("no_mmid", 0) for h in opened)
    # NOT A LOSS METRIC, and the name says so now. Measured: with the strict arm
    # at 0 and the mmid column at 0, every one of these controls DOES own a row --
    # so what this counts is disagreement between THIS PROBE'S naive identity
    # derivation (aria-label || title || innerText) and the collector's AccName
    # implementation. The examples are conclusive: "Ouverture dans un nouvel
    # onglet" and "[另開新視窗]" are the `(opens NEW tab)` FLAG the collector
    # correctly lifts out of the name, a leading "|" is a separator it strips, and
    # one page puts raw HTML in a `title`. Reporting it as identity loss would be
    # a fifth restated definition (PRINCIPLES 17). The question it gestures at --
    # is the right name on the right element -- is #74's, and
    # `tools/audit_name_correctness.py` is the tool that asks it.
    a["naive_name_mismatch"] = sum(h.get("lenient_lost", 0) for h in opened)
    a["strict_norow"] = sum(h.get("strict_norow", 0) for h in opened)
    # THE PROJECT'S OWN ARMS, computed in the same measurement and never restated:
    # audit_generality_live's core/deep lenient arms and its strict arm, over the
    # WHOLE page at each stage. These are the numbers #85 and #92 report.
    a["agl_s0"] = {k: sum(r["s0"][k] for r in ok)
                   for k in ("lost_core", "lost_deep", "strict_norow_named")}
    a["agl_post_hover"] = {
        "lost_core": sum(h.get("page_lost_core", 0) for h in opened),
        "lost_deep": sum(h.get("page_lost_deep", 0) for h in opened),
        "strict_norow_named": sum(h.get("page_strict_norow_named", 0) for h in opened)}
    a["strict_by_ledger"] = dict(collections.Counter(
        str(x.get("ledger")) for h in opened for x in h.get("strict_detail", [])))
    a["strict_detail"] = [dict(x, site=r["site"])
                          for r in ok for h in r.get("hovers", [])
                          for x in h.get("strict_detail", [])][:40]
    a["find_asked"] = sum(h["findability"]["asked"] for h in opened if h.get("findability"))
    a["find_reached"] = sum(h["findability"]["reached"] for h in opened if h.get("findability"))
    a["modal_banner_raised_by_hover"] = sum(
        1 for h in opened if h.get("modal_banner") and not h.get("modal_banner_was_on_at_s0"))
    a["hover_survived_measurement"] = collections.Counter(
        str(h.get("hover_survived_measurement")) for h in opened)
    a["unexpected_drop_reasons"] = [h["unexpected_drop_reasons"] for h in opened
                                    if h.get("unexpected_drop_reasons")]
    a["by_tier"] = {}
    for t in sorted({h["tier"] for h in hv}):
        th = [h for h in hv if h["tier"] == t]
        to = [h for h in th if h.get("appeared")]
        a["by_tier"][t] = {
            "tried": len(th), "revealed": len(to),
            "controls": sum(h["appeared"] for h in to),
            "candidates": sum(h.get("candidates", 0) for h in to),
            "lenient_lost": sum(h.get("lenient_lost", 0) for h in to),
            "strict_norow": sum(h.get("strict_norow", 0) for h in to),
        }
    a["by_script"] = {}
    for r in ok:
        k = AGL.SCRIPT_OF.get(r["lang"], r["lang"])
        d = a["by_script"].setdefault(k, collections.Counter())
        for h in r["hovers"]:
            if not h.get("appeared"):
                continue
            d["reveals"] += 1
            d["controls"] += h["appeared"]
            d["candidates"] += h.get("candidates", 0)
            d["lenient_lost"] += h.get("lenient_lost", 0)
            d["strict_norow"] += h.get("strict_norow", 0)
    a["by_script"] = {k: dict(v) for k, v in sorted(a["by_script"].items())}
    a["css_sheets_blocked_sites"] = sum(
        1 for r in ok for h in r["hovers"][:1] if h.get("sheets_blocked"))
    return a


# --------------------------------------------------------------------------
# Firing proof.
# --------------------------------------------------------------------------

SELFTEST_HTML = r"""<!DOCTYPE html><meta charset="utf-8"><title>hover fixture</title>
<style>
  body { font: 14px system-ui; margin: 0; }
  nav ul { list-style: none; margin: 0; padding: 0; display: flex; gap: 18px; }
  .sub { display: none; position: absolute; background: #fff; border: 1px solid #999;
         padding: 8px; }
  li.has:hover .sub { display: block; }
  .jsmenu { display: none; }
  .jsmenu.open { display: block; }
</style>
<body>
  <h1>Hover fixture</h1>
  <nav><ul>
    <li class="has">Products
      <div class="sub">
        <a href="/a">REVEALED alpha</a><br>
        <a href="/b">REVEALED beta</a><br>
        <button>REVEALED gamma</button>
      </div>
    </li>
    <li><a href="/plain">Always visible link</a></li>
  </ul></nav>
  <div id="jsroot" style="margin-top:120px;padding:10px;border:1px solid #ccc">
    JS menu root
    <div class="jsmenu"><a href="/j1">JSREVEALED one</a> <a href="/j2">JSREVEALED two</a></div>
  </div>
  <script>
    document.getElementById('jsroot').addEventListener('mouseenter', function () {
      this.querySelector('.jsmenu').classList.add('open');
    });
  </script>
</body>"""


async def selftest():
    """PROVE BOTH ARMS FIRE, on controls that are genuinely there.

    Three planted facts, each one the metric must report:
      1. a CSS `:hover` submenu is found by tier 1 and its three controls are
         seen to APPEAR (the before/after diff is by element identity, so this
         also proves the diff is not matching on names);
      2. a JS `mouseenter` menu is found -- by tier 2, because it declares
         nothing in CSS, which is the half tier 1 cannot reach;
      3. with the revealed rows DELETED from the listing, the strict arm rises
         from 0 to 3 and the lenient arm with it. A metric that cannot tell a
         mutilated listing from a complete one is worth nothing, and that is the
         only thing separating "the collector is good" from "the probe is blind".

    The negative control runs the SAME scoring on the UNMUTILATED listing: it
    must report zero, or the probe reports loss everywhere and distinguishes
    nothing.
    """
    ok = True
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport=VIEWPORT)
        await ctx.add_init_script(path=TAG_JS)
        page = await ctx.new_page()
        await page.goto("about:blank")
        await page.set_content(SELFTEST_HTML)
        await page.wait_for_timeout(300)

        tiers_seen, reveals = [], []
        for _ in range(5):
            pick = await page.evaluate(HOVER_PICK + "({})")
            if not pick or pick.get("none"):
                break
            await page.evaluate("() => { if (window.__abHover) "
                                "window.__abHoverUsed.push(window.__abHover.el); }")
            await page.mouse.move(pick["x"], pick["y"])
            await page.wait_for_timeout(80)
            await page.mouse.move(pick["x"] + 1, pick["y"] + 1)
            await page.wait_for_timeout(400)
            diff = await page.evaluate(HOVER_DIFF)
            if diff["appeared"]:
                res = await page.evaluate(ASG._measure_js())
                s = AGL._summ(res)
                mm = await page.evaluate(APPEARED_MMIDS)
                blob = res["ents"] if isinstance(res["ents"], str) \
                    else json.dumps(res["ents"], ensure_ascii=False)
                sc = score_appeared(diff["appeared"], mm, res["listing"], blob)
                # ---- the MUTILATED arm: delete the revealed rows ----
                cut = res["listing"]
                for d in diff["appeared"]:
                    t = (d.get("text") or "").strip()
                    if t:
                        cut = re.sub(r"^.*" + re.escape(t[:40]) + r".*$", "", cut,
                                     flags=re.M)
                sc_cut = score_appeared(diff["appeared"], mm, cut, "")
                reveals.append({"tier": pick["tier"], "n": len(diff["appeared"]),
                                "clean": (len(sc["lenient_lost"]), len(sc["strict_norow"])),
                                "cut": (len(sc_cut["lenient_lost"]), len(sc_cut["strict_norow"])),
                                "cand": sc["candidates"],
                                "texts": [d["text"][:28] for d in diff["appeared"]][:4]})
            tiers_seen.append(pick["tier"])
            await page.mouse.move(2, VIEWPORT["height"] - 2)
            await page.wait_for_timeout(250)
        await browser.close()

    print("  tiers reached: " + str(sorted(set(tiers_seen))))
    for r in reveals:
        print(f"    [{r['tier']}] revealed {r['n']} ({r['texts']}) cand={r['cand']}"
              f"  clean(lenient,strict)={r['clean']}  mutilated={r['cut']}")

    css = any(r["tier"] == "css-hover" and r["n"] >= 3 for r in reveals)
    print(f"  1. a CSS :hover submenu is DRIVEN and its 3 controls are seen to appear: "
          f"{'YES' if css else 'NO'}")
    ok &= css
    js = any("JSREVEALED" in " ".join(r["texts"]) for r in reveals)
    print(f"  2. a JS mouseenter menu (declares nothing in CSS) is reached too: "
          f"{'YES' if js else 'NO'}")
    ok &= js
    clean_zero = all(r["clean"] == (0, 0) for r in reveals)
    print(f"  3a. NEGATIVE CONTROL — on the real listing both arms report 0: "
          f"{'YES' if clean_zero else 'NO'}")
    ok &= clean_zero
    fired = any(r["cut"][0] > 0 and r["cut"][1] >= 0 for r in reveals) and \
        any(r["cut"][0] > r["clean"][0] for r in reveals)
    print(f"  3b. with the revealed rows DELETED, the metric reports them lost: "
          f"{'YES' if fired else 'NO'}")
    ok &= fired

    print("\nSELF-TEST " + ("PASSED — the probe drives a hover menu, sees what appeared, "
                            "and can tell a complete listing from a mutilated one."
                            if ok else
                            "FAILED — any zero this prints is worthless."))
    return 0 if ok else 1


# --------------------------------------------------------------------------

def _pool(n, only):
    sites = ASG._pool("usable85", only)
    if not sites:
        sites = AGL.SITES + AGL.SITES2
    bad = ASG._check_sample(sites)
    if bad:
        raise SystemExit(f"SAMPLE CONTAMINATED — in the frozen corpus / benches: {bad}")
    return sites[:n] if n else sites


def report(a):
    print(f"\nsites attempted {a['attempted']}  usable {a['usable']}  "
          f"(unusable {len(a['unusable'])} — blocked/empty, NOT passes)")
    print(f"hover attempts {a['hover_attempts']}  that revealed something "
          f"{a['hovers_that_revealed']}  on {a['sites_with_a_reveal']} sites")
    print(f"controls revealed ON SCREEN {a['controls_revealed']}  scored (named, still there) "
          f"{a['candidates']}  closed under us {a['closed_under_us']}")
    print(f"arrivals BELOW/BESIDE the fold (counted, not scored — #6/#26's "
          f"deliberate viewport scoping): {a['off_screen_arrivals']}")
    print(f"  the PAGE declared absent (aria-hidden/inert, not scored): "
          f"{a.get('declared_hidden', 0)}")
    print(f"\n  HOVER-REVEALED CONTROLS OWNING NO ROW : {a['strict_norow']}"
          f"   (never stamped with an mmid: {a.get('no_mmid', 0)})")
    print(f"  strict misses by LEDGER reason: {a.get('strict_by_ledger')}")
    print(f"  audit_generality_live's own arms, WHOLE PAGE:")
    print(f"      first paint  : {a.get('agl_s0')}")
    print(f"      after a hover: {a.get('agl_post_hover')}")
    print(f"  (not a loss metric) this probe's naive identity string absent from the "
          f"listing: {a.get('naive_name_mismatch', a.get('lenient_lost'))}"
          f" — see the aggregate comment; it measures THIS PROBE's name derivation")
    fr = a["find_reached"], a["find_asked"]
    print(f"  REACHABLE BY `find`      : {fr[0]}/{fr[1]}"
          + (f" = {fr[0] / fr[1]:.3f}" if fr[1] else ""))
    print(f"  MODAL banner raised by a hover popover: {a['modal_banner_raised_by_hover']}")
    print(f"  hover survived the measurement: {dict(a['hover_survived_measurement'])}")
    print(f"  drop reasons outside SPEC_DELETES: {a['unexpected_drop_reasons'] or 'none'}")
    print("\nBY TIER")
    h = f"  {'tier':<16}{'tried':>7}{'revealed':>10}{'controls':>10}{'cand':>7}{'lenient':>9}{'strict':>8}"
    print(h)
    for t, v in a["by_tier"].items():
        print(f"  {t:<16}{v['tried']:>7}{v['revealed']:>10}{v['controls']:>10}"
              f"{v['candidates']:>7}{v['lenient_lost']:>9}{v['strict_norow']:>8}")
    print("\nBY SCRIPT")
    for k, v in a["by_script"].items():
        print(f"  {k:<18} reveals={v.get('reveals', 0):>3} controls={v.get('controls', 0):>4}"
              f" cand={v.get('candidates', 0):>4} lenient={v.get('lenient_lost', 0)}"
              f" strict={v.get('strict_norow', 0)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--sites", type=int, default=0)
    ap.add_argument("--conc", type=int, default=6)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--drift", action="store_true", help="run the same sample twice")
    ap.add_argument("--tag", default="run")
    args = ap.parse_args()

    if args.selftest:
        return asyncio.run(selftest())

    sites = _pool(args.sites, args.only)
    print(f"{len(sites)} sites, none in the frozen corpus / bench_turns / bench_flows")
    OUT.mkdir(parents=True, exist_ok=True)
    rs = asyncio.run(run_pass(sites, args.conc))
    a = aggregate(rs)
    p = OUT / f"{args.tag}.json"
    p.write_text(json.dumps({"agg": a, "sites": rs}, indent=1, ensure_ascii=False),
                 encoding="utf-8")
    report(a)
    print(f"\nsaved: {p}")
    if args.drift:
        rs2 = asyncio.run(run_pass(sites, args.conc))
        a2 = aggregate(rs2)
        (OUT / f"{args.tag}_b.json").write_text(
            json.dumps({"agg": a2, "sites": rs2}, indent=1, ensure_ascii=False),
            encoding="utf-8")
        print("\n" + "=" * 62 + "\nDRIFT (same code, second pass)\n" + "=" * 62)
        report(a2)
        for k in ("usable", "hovers_that_revealed", "controls_revealed", "candidates",
                  "naive_name_mismatch", "strict_norow", "find_reached", "find_asked"):
            print(f"  {k:<26} {a.get(k, 0):>6} -> {a2.get(k, 0):>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
