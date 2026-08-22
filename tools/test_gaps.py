"""Deterministic gap probe: run the REAL _collectInteractivePage (extracted
verbatim from extension/background.js) against tools/gap_fixture.html, which
contains one instance of every known-hard DOM pattern, and report which are
CAPTURED vs MISSED. Unlike test_shadow.py this is NOT pass/fail — it is a
gap inventory. Output feeds temp/dom_audit/FINDINGS.md.

Run:  python tools/test_gaps.py
"""

import asyncio
import json
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract as _shared_extract  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")


def extract(name: str) -> str:
    """Delegates to tools/_extract, which skips comments/strings/regexes.

    The brace counter this replaced also counted braces inside comments, so one
    `{` in prose silently sliced in the wrong amount of code and the failure
    surfaced somewhere unrelated.
    """
    return _shared_extract(name, BG, verify=True)


COLLECT = extract("_collectInteractivePage")
CLICK = extract("_clickPage")
TYPE = extract("_enterTextPage")
RECT = extract("_rectForPage")

rows: list[dict] = []


def report(gap: str, status: str, detail: str = ""):
    rows.append({"gap": gap, "status": status, "detail": detail})
    pad = {"CAPTURED": "CAPTURED ", "MISSED": "MISSED   ", "PARTIAL": "PARTIAL  ", "INFO": "INFO     "}[status]
    print(f"  {pad} {gap}" + (f"  — {detail}" if detail else ""))


async def main():
    url = (ROOT / "tools" / "gap_fixture.html").as_uri()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1366, "height": 2400})
        # Mirror the extension's document_start listener-tagging content script
        # (extension/listener_tag.js) — in the real extension this runs on every
        # page; Playwright needs it injected explicitly.
        await page.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await page.goto(url)
        await page.wait_for_timeout(300)

        raw = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        listing = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()")
        (ROOT / "temp" / "dom_audit" / "gap_fixture.txt").write_text(listing, encoding="utf-8")

        def find(substr):
            return [e for e in raw if substr in json.dumps(e, default=str)]

        def named(substr):
            return [e for e in raw if substr in (e.get("name") or "") or substr in (e.get("label") or "") or substr in (e.get("text") or "")]

        def member_flags(label):
            """Flags attached to `label` specifically — as a row OR a fold member.

            Probes that grepped a whole LINE broke the moment folding grouped more
            elements together: G24 asserted "(occluded" was absent from the Add
            Investor line and failed because a DIFFERENT member of the same fold
            carried it. Flags belong to a member, so they have to be read per member.
            """
            m = re.search(r'\d+:"' + re.escape(label) + r'"((?:\([^)]*\))*)', listing)
            if m:
                return m.group(1)
            for ln in listing.split("\n"):
                if label in ln and ln.startswith("ref_"):
                    return ln
            return None

        def listed_once(label):
            """How many times `label` appears, counting rows and fold members."""
            return (len(re.findall(r'\d+:"' + re.escape(label) + r'"', listing))
                    + len([1 for ln in listing.split("\n")
                           if ln.startswith("ref_") and label in ln]))

        # --- G1 bare handler div (via document_start listener tagging) ---
        report("G1 handler-div (JS listener, no role/cursor)",
               "CAPTURED" if named("Handler div") else "MISSED",
               "listener_tag.js content script not effective" if not named("Handler div") else "")
        if named("Handler div"):
            hd = named("Handler div")[0]
            r = await page.evaluate("(function(){ " + CLICK + "; return _clickPage(\"[mmid='" + hd["mmid"] + "']\"); })()")
            clicks = await page.evaluate("window.__divClicks || 0")
            report("G1b handler-div clickable via mmid", "CAPTURED" if r.get("ok") and clicks >= 1 else "MISSED",
                   f"clicks={clicks}")

        # --- G2 same-origin iframe ---
        fb = named("Iframe button")
        report("G2 button inside same-origin iframe",
               "CAPTURED" if fb else "MISSED",
               "" if fb else "iframe contents not walked")
        if fb:
            # coordinates must be TOP-document absolute (frame offset applied)
            exp = await page.evaluate("""() => {
                const f = document.getElementById('frame1');
                const fr = f.getBoundingClientRect();
                const br = f.contentDocument.getElementById('iframe-btn').getBoundingClientRect();
                return { x: Math.round(fr.left + f.clientLeft + br.left), y: Math.round(fr.top + f.clientTop + br.top) };
            }""")
            dx, dy = abs(fb[0]["x"] - exp["x"]), abs(fb[0]["y"] - exp["y"])
            report("G2c in-frame box() is top-document absolute",
                   "CAPTURED" if dx <= 2 and dy <= 2 else "MISSED",
                   f"listed=({fb[0]['x']},{fb[0]['y']}) expected=({exp['x']},{exp['y']})")
            r = await page.evaluate("(function(){ " + CLICK + "; return _clickPage(\"[mmid='" + fb[0]["mmid"] + "']\"); })()")
            clicks = await page.evaluate("window.__iframeClicks || 0")
            report("G2d click in-frame button via mmid registry",
                   "CAPTURED" if r.get("ok") and clicks == 1 else "MISSED", f"result={r} clicks={clicks}")
            rect = await page.evaluate("(function(){ " + RECT + "; return _rectForPage(\"[mmid='" + fb[0]["mmid"] + "']\"); })()")
            report("G2e _rectForPage (CDP coords) offset for frames",
                   "CAPTURED" if rect and abs(rect["x"] - (exp["x"] + fb[0]["w"] / 2)) <= 3 else "MISSED",
                   f"rect={rect}")
        ff = named("Frame field")
        report("G2f label[for] resolved INSIDE frame document", "CAPTURED" if ff else "MISSED")
        if ff:
            r = await page.evaluate("(function(){ " + TYPE + "; return _enterTextPage(\"[mmid='" + ff[0]["mmid"] + "']\", 'hello frame'); })()")
            val = await page.evaluate("document.getElementById('frame1').contentDocument.getElementById('fi').value")
            report("G2g type into in-frame input", "CAPTURED" if r.get("ok") and val == "hello frame" else "MISSED",
                   f"result={r} value={val!r}")
        xo = [e for e in raw if e.get("crossFrame")]
        report("G2h cross-origin iframe surfaced as opaque box",
               "CAPTURED" if xo else "MISSED",
               f"label={xo[0].get('label') or xo[0].get('name')!r}" if xo else "agent has NO signal the embed exists")
        report("G2i same-origin iframe shell NOT double-listed", "CAPTURED" if not [
            e for e in raw if e.get("tag") == "iframe" and not e.get("crossFrame")] else "MISSED")

        # --- G3 inner scroll container ---
        vis_rows = named("Inner row")
        out_rows = [e for e in vis_rows if "scrolled out" in (e.get("name") or "") + (e.get("text") or "")]
        if len(vis_rows) >= 8:
            report("G3 inner-scroll rows", "CAPTURED", f"all {len(vis_rows)} rows listed (incl. clipped)")
        elif vis_rows and not out_rows:
            report("G3 inner-scroll rows", "PARTIAL",
                   f"only {len(vis_rows)} visible rows; clipped rows dropped with NO container-scroll hint")
        else:
            report("G3 inner-scroll rows", "MISSED", f"rows found: {len(vis_rows)}")
        # Assert the ACTUAL clip hint, not incidental words. This used to check
        # for "scroll" + "container" anywhere in the listing, which passed only
        # because the old static legend contained the phrase "which container the
        # element lives in" — it would have stayed green even with the clip hint
        # entirely removed.
        low = listing.lower()
        scroll_hint = ("inner scrollable panel" in low) or ("auto-scroll" in low)
        report("G3b container-scroll hint in listing", "CAPTURED" if scroll_hint else "MISSED")

        # --- G4 hover menu ---
        trig = named("Products")
        hidden_items = named("Hover item")
        report("G4 hover-menu trigger", "CAPTURED" if trig else "MISSED")
        report("G4b hover-only submenu items (display:none)", "INFO",
               f"listed while hidden: {bool(hidden_items)} (correct = False; agent must hover/click trigger first)")

        # --- G5 contenteditable ---
        ed = [e for e in raw if e.get("tag") in ("div",) and "Notes editor" in (e.get("name") or "")]
        ed_any = named("Notes editor")
        if ed_any:
            kind = ed_any[0]
            report("G5 contenteditable editor", "CAPTURED",
                   f"tag={kind.get('tag')} role={kind.get('role')} — check it reads as a TEXT-ENTRY target")
        else:
            report("G5 contenteditable editor", "MISSED")

        # --- G6 canvas with handler ---
        cv = [e for e in raw if e.get("tag") == "canvas"]
        report("G6 canvas (click handler + aria-label)",
               "CAPTURED" if cv else "MISSED",
               "" if cv else "canvas-drawn UI invisible to collector")

        # --- G7 ARIA grid datepicker ---
        cells = [e for e in raw if e.get("role") == "gridcell" or "June " in (e.get("name") or "")]
        gridcell_lines = [ln for ln in listing.split("\n") if "role=gridcell" in ln]
        compact = [ln for ln in listing.split("\n") if "cells as mmid:label" in ln]
        if not cells:
            report("G7 datepicker gridcells", "MISSED", "tabindex=-1 cursor:pointer cells dropped entirely")
        elif compact and not gridcell_lines:
            report("G7 datepicker gridcells", "CAPTURED",
                   f"{len(cells)} cells collected, listing compacted to {len(compact)} block line(s)")
        else:
            report("G7 datepicker gridcells", "PARTIAL",
                   f"{len(gridcell_lines)} individual gridcell lines in listing — compaction not applied")

        # --- G8 misc input types ---
        for lbl, key in [("date input", "Pick date"), ("range slider", "Volume"),
                         ("file input", "Upload CV"), ("color input", "Favorite color")]:
            hit = named(key)
            t = f"type shown: {hit[0].get('input_type') or hit[0].get('type') or '?'}" if hit else ""
            report(f"G8 {lbl}", "CAPTURED" if hit else "MISSED", t)
        report("G8 details/summary", "CAPTURED" if named("More options") else "MISSED")
        report("G8b link inside CLOSED details", "INFO",
               f"listed while closed: {bool(named('Link inside details'))} (correct = False)")
        report("G8 audio controls", "CAPTURED" if named("Sample audio") or [e for e in raw if e.get('tag') == 'audio'] else "MISSED")

        # --- G9 description pollution + sr-only ---
        save = named("Save draft")
        if save:
            nm = save[0].get("name") or ""
            polluted = "30 seconds" in nm
            report("G9 aria-describedby pollution", "PARTIAL" if polluted else "CAPTURED",
                   f"name={nm!r}" if polluted else "description NOT merged into name (correct)")
        else:
            report("G9 aria-describedby pollution", "MISSED", "Save draft button absent")
        sr = named("Close notifications")
        report("G9b sr-only (clip) label on icon button", "CAPTURED" if sr else "MISSED",
               "" if sr else "1x1 clipped span text not used as accessible name")

        # --- G10 disabled states ---
        dis = [e for e in raw if "Disabled real" in (e.get("text") or "") + (e.get("name") or "")]
        report("G10 disabled button excluded or flagged", "INFO",
               f"listed: {bool(dis)}" + (f" flags={ {k: v for k, v in dis[0].items() if 'disab' in k.lower()} }" if dis else ""))
        adis = named("Aria-disabled")
        report("G10b aria-disabled flagged", "INFO",
               f"listed: {bool(adis)}; disabled flag present: {bool(adis and any('disab' in json.dumps(adis[0]).lower() for _ in [0]))}")
        ro = named("Readonly field")
        report("G10c readonly input flagged", "INFO",
               f"listed: {bool(ro)}; readonly flag present: {bool(ro and 'readonly' in json.dumps(ro[0]).lower())}")

        # --- G11 sticky-overlap occlusion ---
        us = named("Partially under sticky")
        report("G11 partially-occluded button", "INFO",
               f"listed: {bool(us)}" + (f" occluded-flag: {bool(us and us[0].get('occluded'))}" if us else ""))

        # --- G13 CodeMirror-style code editor ---
        cm = [e for e in raw if e.get("codeEditor")]
        cm_inner = [e for e in raw if e.get("mmid") and "cm-mirror" in json.dumps(e)]
        report("G13 code-editor host listed as ONE editor target",
               "CAPTURED" if cm and not cm_inner else ("PARTIAL" if cm else "MISSED"),
               f"name={cm[0].get('name')!r} role={cm[0].get('role')}" if cm else "")
        if cm:
            r = await page.evaluate("(function(){ " + TYPE + "; return _enterTextPage(\"[mmid='" + cm[0]["mmid"] + "']\", '<p>typed</p>'); })()")
            val = await page.evaluate("document.getElementById('cm-mirror').value")
            report("G13b typing routed to editor's mirror textarea",
                   "CAPTURED" if val == "<p>typed</p>" else "MISSED", f"mirror value={val!r}")

        # --- G14 operable controls under opacity-0 wrapper (MUI DateField) ---
        sb = [e for e in raw if e.get("role") == "spinbutton"]
        report("G14 spinbutton sections under opacity:0 wrapper",
               "CAPTURED" if len(sb) >= 2 else "MISSED",
               f"{len(sb)} listed (MUI hides sections until focus; they must stay targetable)")

        # --- G15 splitter suppression ---
        spl_mmid = await page.evaluate("(document.getElementById('splitter') || {getAttribute(){return null}}).getAttribute('mmid')")
        spl = [e for e in raw if e.get("mmid") == spl_mmid]
        _spl_dem = bool(spl) and str(spl[0].get("demoted") or "").startswith("was:")
        report("G15 unlabeled sliver splitter DEMOTED (kept, not detailed)",
               "CAPTURED" if (_spl_dem or not spl) else "MISSED",
               "" if _spl_dem else (f"splitter listed undemoted: {spl[0].get('line')}" if spl else "absent"))

        # --- G16 menu/disclosure affordances ---
        report("G16 aria-haspopup trigger flagged (opens menu/popup)",
               "CAPTURED" if "(opens menu/popup)" in listing and "Actions" in listing else "MISSED")
        report("G16b aria-expanded=false flagged (collapsed)",
               "CAPTURED" if any("Advanced settings" in ln and "(collapsed)" in ln for ln in listing.split("\n")) else "MISSED")

        # --- G17 same-box twin collapse ---
        # The substance is that the overlaying span and the unnamed submit collapse
        # into ONE entry which IS the submit, carrying the span's text. Asserted on
        # the structured entry for the type and on the listing for the single
        # occurrence, so it holds whether that entry prints as a row or folds.
        _ap = named("Apply filters")
        _apn = listed_once("Apply filters")
        report("G17 label-overlay span merged into unnamed submit",
               "CAPTURED" if _apn == 1 and _ap and _ap[0].get("type") == "submit" else "MISSED",
               f"occurrences={_apn} type={(_ap[0].get('type') if _ap else None)!r}")

        # --- G18 ARIA widget roles without tabindex/cursor ---
        report("G18 role=slider div (no tabindex) listed", "CAPTURED" if named("Price range") else "MISSED")
        report("G18b svg role=switch listed", "CAPTURED" if named("Dark mode") else "MISSED")
        sbx = [e for e in raw if e.get("role") == "searchbox"]
        report("G18c unlabeled role=searchbox kept (not dropped as noise)",
               "CAPTURED" if sbx else "MISSED")

        # --- G19 German native select: structural (unselected) ---
        gsel = [ln for ln in listing.split("\n") if "Land" in ln and "select" in ln]
        report("G19 non-English select flagged (unselected) structurally",
               "CAPTURED" if gsel and "(unselected)" in gsel[0] else "MISSED",
               gsel[0] if gsel else "no Land select line")

        # --- G20 role=separator splitter suppressed semantically ---
        sep_mmid = await page.evaluate("(document.getElementById('sep-splitter') || {getAttribute(){return null}}).getAttribute('mmid')")
        _sep = [e for e in raw if e.get("mmid") == sep_mmid]
        report("G20 role=separator splitter DEMOTED (kept, not detailed)",
               "CAPTURED" if (not _sep or str(_sep[0].get("demoted") or "").startswith("was:")) else "MISSED",
               "" if not _sep else f"demoted={_sep[0].get('demoted')!r}")

        # --- G21 tiny role=checkbox survives the 8px size floor ---
        report("G21 6x6 role=checkbox kept (semantics beat size floor)",
               "CAPTURED" if named("Compact toggle") else "MISSED")

        # --- G23 hidden-input-under-styled-label (custom radio pattern) ---
        g23 = [e for e in raw if e.get("tag") == "input" and e.get("name") in ("7", "8")]
        big = [e for e in g23 if e.get("w", 0) >= 40 and e.get("h", 0) >= 40]
        checked = [e for e in g23 if e.get("name") == "8" and e.get("active") == "checked"]
        report("G23 sr-only radios listed via label-proxy geometry",
               "CAPTURED" if len(big) == 2 else "MISSED",
               f"{len(g23)} radios, {len(big)} with label-size boxes")
        report("G23b checked radio flagged", "CAPTURED" if checked else "MISSED")

        # --- G24 pointer-events:none disabled submit stays listed ---
        _g24 = member_flags("Add Investor")
        report("G24 pointer-events:none disabled submit listed + flagged",
               "CAPTURED" if _g24 is not None and "(disabled)" in _g24 and "(occluded" not in _g24
               else "MISSED",
               f"flags={_g24!r}" if _g24 is not None
               else "shadcn-style disabled submit vanished from listing")

        # --- G22 shadow-slotted label on a text-less anchor ---
        tile = [ln for ln in listing.split("\n") if "How to search the archive" in ln and "| a " in ln]
        report("G22 anchor labeled from descendant shadow-root text",
               "CAPTURED" if tile else "MISSED",
               tile[0] if tile else "tile anchor unlabeled (host.innerText empty for shadow content)")

        # --- G25 custom-picker harvest must survive stale ARIA portals ---
        # Replicates the live Boxsy failure: trigger's aria-controls popover has
        # clickable rows with NO role=option, while a closed menu portal still
        # has invisible [role=menuitem] nodes mounted. The old `!all.length`
        # gate let those 2 stale matches block the harvest fallback entirely.
        PICK = extract("_pickOptionPage")
        g25 = await page.evaluate(
            "(function(){ " + PICK + "; return _pickOptionPage('Beta Two', '#g25-trigger'); })()"
        )
        g25_clicked = await page.evaluate("window.__g25Picked || ''")
        g25_via = (g25 or {}).get("dbg", {}).get("via", "")
        report("G25 custom-picker pick with stale closed-portal present",
               "CAPTURED" if g25 and g25.get("ok") and g25_clicked == "Beta Two" else "MISSED",
               f"picked={g25 and g25.get('actual')!r} clicked={g25_clicked!r} via={g25_via}")

        # --- G26 dead-duplicate custom combobox (double-init orphan) ---
        # widgetSig is the TRIGGER's own tag.firstClass — deliberately not the
        # wrapper's, so a collapsed live widget and a full-size orphan still
        # land in the same comparison group (see background.js).
        g26 = [e for e in raw if (e.get("widgetSig") or "").endswith("g26-selection")]
        g26_backed = [e for e in g26 if e.get("comboBacked")]
        g26_orphan = [e for e in g26 if e.get("orphanWidget")]
        ok26 = len(g26_backed) == 1 and len(g26_orphan) == 1 and not g26_backed[0].get("orphanWidget")
        report("G26 orphaned duplicate combobox flagged, backed twin left alone",
               "CAPTURED" if ok26 else "MISSED",
               f"widgets={len(g26)} backed={len(g26_backed)} flagged={len(g26_orphan)}")
        # The default `listing` is captured at scroll-top and is viewport-scoped by
        # design, so G26 (far down the fixture) is legitimately absent from it.
        # Scroll it into view to assert the flag actually RENDERS.
        await page.evaluate("document.querySelector('#g26').scrollIntoView({block:'center'})")
        await page.wait_for_timeout(150)
        listing_g26 = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()")
        await page.evaluate("window.scrollTo(0,0)")
        await page.wait_for_timeout(100)
        report("G26b DEAD-DUPLICATE tag + legend rendered in the listing",
               "CAPTURED" if "(DEAD-DUPLICATE)" in listing_g26 and "backing form control" in listing_g26 else "MISSED")

        # --- G27 FALSE-POSITIVE GUARD: unbacked framework triggers stay unflagged ---
        g27 = named("G27 Framework Trigger")
        g27_bad = [e for e in g27 if e.get("orphanWidget")]
        report("G27 unbacked framework comboboxes NOT false-flagged",
               "CAPTURED" if len(g27) == 2 and not g27_bad else "MISSED",
               f"found={len(g27)} falsely_flagged={len(g27_bad)}")

        # --- G28 find-reach: below-fold control in structured output only ---
        # The asymmetry this pins looks indefensible — the requested OUTPUT FORMAT
        # decides whether an element exists, so find() reaches a below-fold button
        # that read_page cannot see. It was removed on that argument and
        # tools/bench_trajectory.py priced all three alternatives over Mind2Web
        # gold paths: listing every offscreen row costs 1.51x tokens for +20.2pp
        # first-read reachability, 3.39x for +42.7pp, and folding-only costs 1.12x
        # for +0.0pp. All four variants end at the same 96.0% recoverable, so the
        # viewport-scoped listing reaches the same place for a third of the budget.
        # Kept deliberately, and this probe is the tripwire.
        deep = named("Deep below fold action")
        deep_in_string = "Deep below fold action" in listing
        ok28 = bool(deep) and bool(deep[0].get("offscreen")) and not deep_in_string
        report("G28 below-fold control reachable by find() but kept out of the listing",
               "CAPTURED" if ok28 else "MISSED",
               f"inStructured={bool(deep)} offscreen={deep[0].get('offscreen') if deep else None} inStringListing={deep_in_string}")

        # --- G29 unmatched option must FAIL LOUDLY, not click something arbitrary ---
        g29 = await page.evaluate(
            "(function(){ " + PICK + "; return _pickOptionPage('Gamma Nine', '#g29-trigger'); })()"
        )
        g29_ok = bool(g29) and g29.get("ok") is False and "Alpha One" in (g29.get("msg") or "")
        report("G29 unmatched option fails loudly and lists what IS available",
               "CAPTURED" if g29_ok else "MISSED",
               f"ok={g29 and g29.get('ok')} msg={(g29 or {}).get('msg','')[:90]!r}")

        # --- G30 backing control overrides the English placeholder wordlist ---
        g30 = [e for e in raw if "G30 Trigger" in json.dumps(e, default=str)
               or (e.get("label") or "") == "Select All Regions"]
        g30t = [e for e in g30 if e.get("role") == "combobox"]
        g30_ok = bool(g30t) and not g30t[0].get("unselected") and bool(g30t[0].get("backedBy"))
        report("G30 real 'Select...' value not mis-flagged (unselected); backed-by emitted",
               "CAPTURED" if g30_ok else "MISSED",
               f"found={len(g30t)} unselected={g30t[0].get('unselected') if g30t else None} backedBy={g30t[0].get('backedBy') if g30t else None}")

        # --- G12 link semantics ---
        ext = named("External docs")
        report("G12 target=_blank flagged (new-tab warning)", "INFO",
               f"listed: {bool(ext)}; new-tab flag: {bool(ext and 'blank' in json.dumps(ext[0]).lower())}")
        dl = named("Download report")
        report("G12b download attr flagged", "INFO",
               f"listed: {bool(dl)}; download flag: {bool(dl and 'download' in json.dumps(dl[0]).lower())}")

        await browser.close()

    out = ROOT / "temp" / "dom_audit" / "gap_probe_results.json"
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    missed = [r for r in rows if r["status"] == "MISSED"]
    partial = [r for r in rows if r["status"] == "PARTIAL"]
    print(f"\n{len(missed)} MISSED, {len(partial)} PARTIAL, {len([r for r in rows if r['status']=='CAPTURED'])} CAPTURED  -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
