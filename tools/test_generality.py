"""Generality regression suite: non-Latin pages, shadow DOM, unnamed libraries.

Companion to test_widgets.py. Where that suite pins the combobox/popover shapes
that broke on live pages, this one pins the ways the collector could be
ACCIDENTALLY SPECIFIC — to English, to the light DOM, or to three code-editor
libraries we happen to be able to name.

Every check here maps to a defect that was real:
  N1-N3  /[a-z0-9]/i gates rejected every CJK/Cyrillic/Arabic label and blanked
         dialog text on non-Latin pages entirely.
  S1-S4  page-level scans used document.querySelectorAll, so a web-component
         dialog opened with no modal banner and no dialog text, a shadow <h1>
         produced no main heading, and an aria-hidden component host was ignored.
  E1-E3  code-editor support keyed on .CodeMirror/.cm-editor/.monaco-editor/
         .ace_editor; any other editor was listed as a div full of gutter digits.
  T1-T2  the sub-8x8 decoration filter dropped named native <button>s (Amazon's
         8x4 header language switcher).
  C1-C2  combobox placeholder state was detectable only via an English wordlist.
  U1     60-char truncation split surrogate pairs.

Run:  python tools/test_generality.py
"""

import asyncio
import json
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract as _shared_extract  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")

# The whole point of this suite is non-Latin text; the Windows console defaults
# to cp1252 and would crash on the first Japanese detail line.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def extract(name: str) -> str:
    """Delegates to tools/_extract, which skips comments/strings/regexes.

    The brace counter this replaced also counted braces inside comments, so one
    `{` in prose silently sliced in the wrong amount of code and the failure
    surfaced somewhere unrelated.
    """
    return _shared_extract(name, BG, verify=True)


COLLECT = extract("_collectInteractivePage")
DOMTEXT = extract("_domTextPage")
RECTFOR = extract("_rectForPage")

results = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))


def find(raw, **kw):
    """First entry matching every given field."""
    for e in raw:
        if all(e.get(k) == v for k, v in kw.items()):
            return e
    return None


def by_text(raw, needle):
    return [e for e in raw
            if needle in ((e.get("name") or "") + "|" + (e.get("label") or "") +
                          "|" + (e.get("text") or "") + "|" + (e.get("value") or ""))]


async def main():
    url = (ROOT / "tools" / "generality_zoo.html").as_uri()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Tall enough that every fixture stays IN the viewport. The listing is
        # viewport-scoped by design, so a fixture pushed below the fold vanishes
        # and reads as a collector regression — adding one 200px editor did
        # exactly that to three unrelated checks.
        page = await browser.new_page(viewport={"width": 1280, "height": 2200})
        await page.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await page.goto(url)
        await page.wait_for_timeout(250)

        raw = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        mm = await page.evaluate("""() => {
            const o = {};
            for (const id of ['gb-data','gc-icon','gg-tiny','gh-tiny-unnamed','gk-empty','gk-filled',
                              'gf-editor','gr-editor','gm-not-editor','go-code-block','gl-emoji','gn-svg-icon'])
              { const n = document.getElementById(id); o[id] = n && n.getAttribute('mmid'); }
            return o;
        }""")
        ent = {k: find(raw, mmid=v) for k, v in mm.items() if v}

        # ---- N: non-Latin labels ------------------------------------------------
        e = ent.get("gb-data")
        check("N1 CJK data-* attribute is accepted as a synthesized label",
              bool(e) and "検索" in (e.get("label") or ""),
              f"label={(e or {}).get('label')!r} iconOnly={(e or {}).get('iconOnly')}")
        e = ent.get("gc-icon")
        check("N2 CJK ::before icon-font content is accepted as a label",
              bool(e) and "閉じる" in (e.get("label") or ""),
              f"label={(e or {}).get('label')!r}")

        e = ent.get("gn-svg-icon")
        check("N4 an <svg> icon's library class rescues a badge-only name",
              bool(e) and "bell" in (e.get("name") or ""),
              f"name={(e or {}).get('name')!r}  (SVG .className is an SVGAnimatedString, "
              f"so the old read matched nothing)")

        # ---- T: tiny native controls -------------------------------------------
        e = ent.get("gg-tiny")
        check("T1 named 8x4 native <button> survives the sub-8px decoration filter",
              bool(e) and "Expand language menu" in (e.get("name") or ""),
              f"listed={bool(e)} name={(e or {}).get('name')!r}")
        _t2 = ent.get("gh-tiny-unnamed")
        check("T2 an unnamed 8x4 anchor is DEMOTED, not deleted — a heuristic may"
              " decide prominence, never existence",
              bool(_t2) and _t2.get("demoted") == "was:too-small-unnamed",
              f"demoted={(_t2 or {}).get('demoted')!r} entry={'present' if _t2 else 'ABSENT'}")

        # ---- C: combobox state without English ----------------------------------
        e = ent.get("gk-empty")
        check("C1 class-marked placeholder ('Bitte wählen') reads as unselected, not a value",
              bool(e) and e.get("unselected") is True and not e.get("value"),
              f"unselected={(e or {}).get('unselected')} value={(e or {}).get('value')!r}")
        e = ent.get("gk-filled")
        check("C2 a real German value is NOT mistaken for a placeholder",
              bool(e) and not e.get("unselected") and "Deutschland" in (e.get("value") or ""),
              f"unselected={(e or {}).get('unselected')} value={(e or {}).get('value')!r}")

        # ---- E: code editors with no recognisable class -------------------------
        e = ent.get("gf-editor")
        check("E1 unnamed editor (hidden textarea + monospace host) is detected as a code editor",
              bool(e) and e.get("codeEditor") is True,
              f"listed={bool(e)} codeEditor={(e or {}).get('codeEditor')}")
        check("E2 its value is the code, with the line-number gutter stripped",
              bool(e) and (e.get("value") or "").startswith("function greet"),
              f"value={(e or {}).get('value')!r}")
        check("E3 a hidden textarea in a proportional-font box is NOT an editor host",
              not (ent.get("gm-not-editor") or {}).get("codeEditor"),
              f"codeEditor={(ent.get('gm-not-editor') or {}).get('codeEditor')}")
        check("E5 a readonly copy-to-clipboard textarea in a monospace code block is not an editor",
              not (ent.get("go-code-block") or {}).get("codeEditor"),
              f"codeEditor={(ent.get('go-code-block') or {}).get('codeEditor')}")
        # The editor's internals must not be listed alongside it.
        guts = [x for x in raw if (x.get("text") or "").strip() in ("1", "2", "3")]
        check("E4 the editor's gutter/line nodes are not listed as separate controls",
              not guts, f"leaked={[g.get('text') for g in guts][:4]}")

        e = ent.get("gr-editor")
        _ev = (e or {}).get("value") or ""
        _body = _ev.split("…(+")[0]
        # THE 60-CHAR COMPACT BOUND IS GONE. It is what made four consecutive writes
        # to a Monaco editor read back byte-identical, so an agent could not tell
        # truncation from a failed write. An editor of ordinary size now arrives
        # WHOLE in compact; only genuinely large content is bounded (M-count), and
        # there the residual is exact.
        check("E6 an ordinary editor's value arrives WHOLE in compact",
              bool(e) and len(_ev) == len(_body) and "…(+" not in _ev,
              f"content={len(_body)} total={len(_ev)}")
        check("E6b ...and it is the real code, not a gutter or a prefix",
              "delta" in _ev and not _ev.startswith("1 2 3"),
              repr(_ev[:56]))
        ef = {x["mmid"]: x for x in await page.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, 'full'); })()")}
        e2 = ef.get(dm2["gr-editor"]) if (dm2 := mm) else None
        check("E7 ...and readable in full, so reading code needs no whole-page dump",
              bool(e2) and len(e2.get("value") or "") > 100 and "delta" in (e2.get("value") or ""),
              f"len={len((e2 or {}).get('value') or '')}")

        # ---- U: truncation ------------------------------------------------------
        e = ent.get("gl-emoji")
        blob = json.dumps(e, ensure_ascii=False) if e else ""
        lone = bool(re.search(r"[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]", blob))
        check("U1 truncating at a surrogate pair leaves no broken character",
              bool(e) and not lone,
              f"text={(e or {}).get('text')[-6:]!r} lone_surrogate={lone}")

        # ---- D: detail levels ---------------------------------------------------
        # compact is what every observation pays for; full is the escape hatch.
        dm = await page.evaluate('''() => { const o = {};
            for (const id of ['gd-link','gd-plain','gd-imglink','gd-data','gd-tracker','gp-submit','gp-leaf','gq-bg','gq-grad','gs-cb','gs-decoy','gs-card','gt-day','gt-sec','gt-alink','gt-longalt'])
              { const n = document.getElementById(id); o[id] = n && n.getAttribute('mmid'); }
            return o; }''')
        comp = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false, null, 'compact'); })()")
        fulls = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, 'full'); })()")
        fullstr = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false, null, 'full'); })()")
        fmap = {e["mmid"]: e for e in fulls}

        check("D1 compact listing contains no URLs at all",
              "href=" not in comp and "src=" not in comp,
              "clean" if "href=" not in comp and "src=" not in comp else "LEAKED a URL into compact")
        _hatch = next((l.strip() for l in comp.splitlines() if "NOT listed" in l), "")
        check("D2 compact says what it is withholding and how to get it",
              bool(_hatch) and 'detail="full"' in _hatch and "ref_id" in _hatch,
              _hatch[:110] or "NO ESCAPE-HATCH LINE")
        e = fmap.get(dm["gd-link"])
        check("D3 full resolves a link's href to an absolute URL",
              bool(e) and (e.get("href") or "").endswith("/downloads/report.pdf?v=2")
              and "://" in (e.get("href") or ""),   # absolute; scheme is file:// for the local zoo
              f"href={(e or {}).get('href')!r}")
        e = fmap.get(dm["gd-plain"])
        check("D4 full lists a NON-clickable image, which no filter level could reach",
              bool(e) and e.get("mediaOnly") is True and (e.get("src") or "").endswith("/assets/hero.gif"),
              f"listed={bool(e)} src={(e or {}).get('src')!r}")
        check("D5 that image is absent from compact (it is not a control)",
              dm["gd-plain"] not in [x["mmid"] for x in
                                     await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, 'compact'); })()")],
              "absent")
        e = fmap.get(dm["gd-imglink"])
        check("D6 a link wrapping an image reports both its href and the image src",
              bool(e) and (e.get("href") or "").endswith("/gallery") and (e.get("src") or "").endswith("/assets/thumb.png"),
              f"href={(e or {}).get('href')!r} src={(e or {}).get('src')!r}")
        e = fmap.get(dm["gd-data"])
        check("D7 a data: URI is described, never emitted as a fetchable URL",
              bool(e) and "not a fetchable URL" in (e.get("src") or "") and "base64,R0lGOD" not in (e.get("src") or ""),
              f"src={(e or {}).get('src')!r}")
        check("D8 a 1x1 tracking pixel is not surfaced as media",
              dm["gd-tracker"] not in fmap, f"entry={fmap.get(dm['gd-tracker'])}")
        check("D9 media rows are marked as non-controls in the listing",
              "(media — not a control)" in fullstr,
              next((l.strip()[:96] for l in fullstr.splitlines() if "(media" in l and ("ref_" in l or "mmid=" in l)), "ABSENT"))
        # The whole design rests on scoping keeping `full` cheap.
        host = await page.evaluate("() => document.getElementById('gd-detail').getAttribute('mmid')")
        scoped = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false, '" + host + "', 'full'); })()")
        check("D10 scoping keeps full detail smaller than a full-page read",
              len(scoped) < len(fullstr),
              f"scoped={len(scoped)} vs whole-page full={len(fullstr)} chars")

        # The two scoping rules are opposites and only make sense side by side.
        lref = dm["gd-link"]
        sfull = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false, '" + lref + "', 'full'); })()")
        check("D11 scoping to a LINK with detail=full returns that link and its href",
              f"ref_{lref} " in sfull and "report.pdf" in sfull,
              next((l.strip()[:110] for l in sfull.splitlines() if l.startswith(("ref_", "mmid="))), "EMPTY LISTING"))
        iref = dm["gd-imglink"]
        ifull = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false, '" + iref + "', 'full'); })()")
        check("D12 an image-wrapping link reports its own href, not just the image",
              "/gallery" in ifull and "thumb.png" in ifull,
              " | ".join(l.strip()[:70] for l in ifull.splitlines() if l.startswith(("ref_", "mmid=")))[:150])
        scomp = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true, '" + host + "', 'compact'); })()")
        check("D13 compact scoping still EXCLUDES the host (it is the container, not a result)",
              all(e["mmid"] != host for e in scomp),
              f"host={host} in {len(scomp)} scoped entries")

        # ---- L: defects found by the live escalation study ----------------------
        raw2 = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        e = find(raw2, mmid=dm["gp-submit"])
        check("L1 a submit input is NAMED by its value, not by its HTML name attribute",
              bool(e) and e.get("name") == "Login",
              f"name={(e or {}).get('name')!r}  (was 'login-button')")
        check("L2 ...and that label is not reported as the field's current contents",
              bool(e) and not e.get("value"),
              f"value={(e or {}).get('value')!r}  (was 'Login', the slot meaning CONTENTS)")
        lf = dm["gp-leaf"]
        leaf = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false, '" + lf + "', 'compact'); })()")
        check("L3 scoping to a LEAF control returns that control, not an empty listing",
              f"ref_{lf} " in leaf,
              next((l.strip()[:100] for l in leaf.splitlines() if l.startswith(("ref_", "mmid="))), "EMPTY LISTING"))
        check("L4 a scoped read does not carry page-level facts",
              "Main heading:" not in leaf and "BELOW the current viewport" not in leaf,
              " / ".join(l.strip()[:60] for l in leaf.splitlines()
                         if "Main heading" in l or "BELOW the current" in l) or "clean")
        check("L5 a tiny scoped read drops the notation legend it does not need",
              "section=... — the containing region" not in leaf and len(leaf) < 500,
              f"{len(leaf)} chars")

        # L9: found LIVE, not by any fixture. After fill_form navigated saucedemo to
        # /inventory.html, read_page(ref_id="ref_17") returned all 25 elements of the
        # new page under the header "[scoped to the subtree of ref_17]" — mmid 17 did
        # not exist there at all (the page's lowest was 39). `if (host)` had no else,
        # so an absent ref silently dropped the scope while the server still stamped
        # the scoped banner on it. mmids are per-document, so carrying a ref across a
        # navigation is the ordinary way to hit this, and the listing lies silently.
        missing = await page.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false, '999999', 'compact'); })()")
        check("L9 scoping to a ref absent from this document fails loudly, not silently",
              str(missing).startswith("__SCOPE_MISS__"),
              f"returned {len(str(missing))} chars starting {str(missing)[:60]!r}")
        check("L9b ...and does not return the whole page instead",
              "mmid=" not in str(missing),
              f"{str(missing).count('mmid=')} element rows leaked into a failed scope")

        # U-series: text visibility. Both directions matter and they look alike.
        dom_text = await page.evaluate("(function(){ " + DOMTEXT + "; return _domTextPage(); })()")
        check("U2 a ~1px collapsed panel's text is NOT reported as visible",
              "inside-a-closed-menu" not in dom_text,
              "leaked" if "inside-a-closed-menu" in dom_text else "hidden correctly")
        check("U3 a 0x0 boxless (display:contents) container's text IS kept",
              "inside a boxless container" in dom_text,
              "kept" if "inside a boxless container" in dom_text else "DELETED — the MDN regression")

        # M-series: found by six live agents on real sites, by no fixture.
        M = {e["mmid"]: e for e in
             await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, 'full'); })()")}
        # Re-read mmids AFTER the full pass: media-only rows are assigned an mmid
        # only during a full collection, so the ids captured earlier are null for
        # them. Reusing the stale map made these assertions look up None and PASS
        # vacuously — the failure mode this suite exists to catch.
        tm = await page.evaluate('''() => { const o = {};
            for (const id of ['gt-day','gt-sec','gt-alink','gt-longalt'])
              { const n = document.getElementById(id); o[id] = n && n.getAttribute('mmid'); }
            return o; }''')
        for _k, _v in tm.items():
            check(f"M0 fixture {_k} is present in the listing at all", bool(_v) and _v in M,
                  f"mmid={_v}")
        day = M.get(tm["gt-day"])
        check("M1 a date cell takes its child's aria-label, not the bare number",
              "29 August 2026" in ((day or {}).get("name") or ""),
              f"name={(day or {}).get('name')!r}  label={(day or {}).get('label')!r}")

        sec = M.get(tm["gt-sec"])
        check("M2 a non-media container does NOT adopt a descendant's src",
              not ((sec or {}).get("src") or ""),
              f"section src={(sec or {}).get('src')!r}")
        alink = M.get(tm["gt-alink"])
        check("M3 ...but a link wrapping an image still does",
              "thumb2.png" in ((alink or {}).get("src") or ""),
              f"a src={(alink or {}).get('src')!r}")

        longalt = M.get(tm["gt-longalt"])
        nm = (longalt or {}).get("name") or ""
        check("M4 a long alt is not cut at 60 chars — it is the content, not a label",
              len(nm) > 60 and "40.485121134668" in nm, f"{len(nm)} chars: {nm[:72]!r}")
        check("M5 ...and if it IS cut, the cut is visibly marked",
              (not nm.endswith("…")) or len(nm) >= 200,
              f"ends {nm[-12:]!r} at {len(nm)} chars")

        fullmap = {e["mmid"]: e for e in
                   await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, 'full'); })()")}
        e = fullmap.get(dm["gq-bg"])
        check("L6 a CSS background-image hero is surfaced as media with its URL",
              bool(e) and (e.get("src") or "").endswith("/assets/banner.jpg") and e.get("cssBackground") is True,
              f"src={(e or {}).get('src')!r}")
        check("L7 a gradient background is decoration, not media",
              dm["gq-grad"] not in fullmap, f"entry={fullmap.get(dm['gq-grad'])}")
        compact2 = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, 'compact'); })()")
        check("L8 CSS backgrounds stay out of the compact default",
              all(x["mmid"] != dm["gq-bg"] for x in compact2), "absent from compact")

        # ---- P: shapes that were being deleted with no trace (Fable-5 audit) -----
        raw3 = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        by = {e["mmid"]: e for e in raw3}
        e = by.get(dm["gs-cb"])
        check("P1 an opacity:0 checkbox behind its styled label is listed as a checkbox",
              bool(e) and e.get("type") == "checkbox" and "Accept terms" in (e.get("name") or ""),
              f"listed={bool(e)} type={(e or {}).get('type')} name={(e or {}).get('name')!r}")
        check("P2 ...but an opacity:0 input with NO visible label stays dropped",
              dm["gs-decoy"] not in by, f"entry={by.get(dm['gs-decoy'])}")
        check("P3 a clickable card with a heading and 3 inner links is not deleted as a wrapper",
              dm["gs-card"] in by, "kept" if dm["gs-card"] in by else "DELETED — unreachable by listing AND find")
        txt3 = await page.evaluate("(function(){ " + DOMTEXT + "; return _domTextPage(); })()")
        check("P4 a calendar's day numbers survive the editor-gutter strip",
              all(str(d) in txt3 for d in range(1, 8)),
              "1-7 present" if all(str(d) in txt3 for d in range(1, 8)) else "CALENDAR DELETED")
        out3 = txt3.split("--- DOCUMENT OUTLINE")[-1]
        check("P5 footer link-column headings are not document sections",
              "Products" not in out3 and "Company" not in out3, out3[:80].replace(chr(10), " / "))
        check("P6 an sr-only heading is neither the main heading nor an outline entry",
              "Utility navigation" not in out3 and "Utility navigation" not in
              await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()"),
              "excluded")

        # ---- X: coordinates inside a CSS-TRANSFORMED same-origin frame ----------
        # Adding frameRect.left to an untransformed inner rect is only right when
        # the frame is unscaled. A scale(.5) preview pane put every coordinate out
        # by the scale factor while the tool reported success — the fix #10/#11/#12
        # family. Both the listed box() and the CDP click point are checked, since
        # they are computed by different functions.
        # ---- C: a canvas does not stop existing when the window gets wider --
        # The unlabelled-canvas gate was a VIEWPORT FRACTION (>= 25%), so
        # chartjs.org's 800x400 centrepiece was 29.6% of a 1200x900 viewport and
        # kept, but 11.1% of a 2327x1234 one and dropped — the largest thing on the
        # page absent from every listing at every detail level, leaving a 400px gap
        # between two rows. Nothing about the element changed; only the window did.
        # The early return was also uninstrumented, so `ledger:true` reported
        # nothing and a live agent needed six probes to find it.
        for _vw, _vh in ((1200, 900), (2400, 1300)):
            cp = await browser.new_page(viewport={"width": _vw, "height": _vh})
            await cp.set_content(
                "<!DOCTYPE html><meta charset=utf-8><body style='margin:0'>"
                "<div class=chart-editor><div class=chart-view>"
                "<canvas style='display:block;box-sizing:border-box;height:400px;width:800px'"
                " width=880 height=440></canvas></div>"
                "<a class=chart-action>Randomize</a></div>"
                # must stay out at every size: a sparkline is not a surface to act on
                "<canvas id=spark width=60 height=20 style='display:block'></canvas>"
                "</body>")
            await cp.wait_for_timeout(140)
            craw = await cp.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
            cvs = [f"{e.get('w')}x{e.get('h')}" for e in craw if e.get("tag") == "canvas"]
            check(f"CV1 an unlabelled 800x400 canvas is listed at {_vw}x{_vh}",
                  "800x400" in cvs, f"canvases={cvs}")
            # A sparkline is still JUDGED decoration — but that judgement is a
            # pixel threshold, so it now sets prominence rather than existence.
            # It stays addressable by ref, compacted into the PROBABLY DECORATION
            # line, because "too small to matter" is exactly the kind of guess that
            # has no defensible accuracy on a page nobody has seen.
            _spark = next((e for e in craw if e.get("tag") == "canvas"
                           and (e.get("w") or 0) < 100), None)
            check(f"CV2 ...and a 60x20 sparkline is DEMOTED, not deleted, at {_vw}x{_vh}",
                  bool(_spark) and str(_spark.get("demoted") or "").startswith("was:"),
                  f"demoted={(_spark or {}).get('demoted')!r}")
            cstr = await cp.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()")
            check(f"CV3 ...and it carries the (canvas) marker telling the agent to screenshot ({_vw})",
                  "(canvas)" in cstr, cstr.splitlines()[0][:70])
            await cp.close()

        # ---- N: a name belongs to the element it is printed against -------
        # AccName's "exclude the control's own subtree" rule is written for a
        # LABELABLE form control. Applied to any element inside a <label>, it made
        # siblings SWAP names — each cloned the label, removed itself, and kept the
        # other's text. Live on IKEA's price filters, all five rows, boxes correct:
        # the label span at x=119 reported name="28 products28" and the 14px count
        # badge at x=284 reported name="$0.00 - 499.99". Name and geometry
        # disagreed with nothing saying so.
        np_ = await browser.new_page(viewport={"width": 1200, "height": 800})
        await np_.set_content(
            "<!DOCTYPE html><meta charset=utf-8><body style='margin:0'>"
            "<label style='display:block;position:relative;height:40px'>"
            "<input type=checkbox style='position:absolute;width:0;height:0'>"
            "<span id=lw tabindex=0 style='position:absolute;left:119px;top:4px;"
            "width:157px;height:21px;cursor:pointer'>$0.00 - 499.99</span>"
            "<span id=ct tabindex=0 style='position:absolute;left:284px;top:5px;"
            "width:14px;height:19px;cursor:pointer'>28</span></label>"
            # The two cases the rule EXISTS for must keep working — this is the
            # negative control, and it is why the fix gates on labelable rather
            # than simply on "has its own text" (a <select>'s innerText is its
            # option text, so that simpler rule would have broken it).
            "<label>Country <select id=sel><option>France</option></select></label>"
            "<label><input type=checkbox id=cb2> Remember me</label>"
            "</body>")
        await np_.wait_for_timeout(140)
        nraw = await np_.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        nid = await np_.evaluate("""() => ({lw: lw.getAttribute('mmid'), ct: ct.getAttribute('mmid'),
            sel: sel.getAttribute('mmid'), cb2: cb2.getAttribute('mmid')})""")
        nby = {str(e.get("mmid")): e for e in nraw}
        for key, want, why in (
            ("lw", "$0.00 - 499.99", "a labelled span keeps its OWN text"),
            ("ct", "28", "...and its sibling does not steal it"),
            ("sel", "Country", "a wrapped <select> still adopts the label (AccName)"),
            ("cb2", "Remember me", "a wrapped checkbox still adopts the label"),
        ):
            e = nby.get(str(nid.get(key))) or {}
            got = (e.get("name") or e.get("label") or e.get("text") or "")
            check(f"N-{key} {why}", want in got, f"got {got!r}")
        await np_.close()

        # ---- M: no agent-facing field is cut in silence -------------------
        # Seven of twenty live agents independently reported a bounded field that
        # gave no sign of being bounded. The failure is not the bound, it is that
        # `value="Acme Corporation Interna"` and a field whose contents really are
        # that string are the SAME 24 characters — one of them a lie the agent
        # cannot detect, and one agent read back an identical 60-char prefix after
        # four writes without ever learning its writes were landing. The three
        # hand-rolled copies of this logic are now one markCut(), so a NEW bounded
        # field cannot reintroduce the silence by omitting the five-line snippet.
        mp = await browser.new_page(viewport={"width": 1200, "height": 900})
        LONG = "Alpha Bravo Charlie Delta Echo Foxtrot Golf Hotel India Juliett Kilo Lima Mike November Oscar Papa"
        await mp.set_content(
            "<!DOCTYPE html><meta charset=utf-8><body>"
            f"<label for=mv>Notes</label><input id=mv value='{LONG}'>"
            f"<label for=mp2>Query</label><input id=mp2 placeholder='{LONG}'>"
            f"<div id=mc role=combobox tabindex=0>{LONG}</div>"
            f"<button id=mb>{LONG}</button>"
            "</body>")
        await mp.wait_for_timeout(150)
        mraw = await mp.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        mid = await mp.evaluate("""() => { const o = {};
            for (const id of ['mv','mp2','mc','mb']) { const n = document.getElementById(id);
              o[id] = n && n.getAttribute('mmid'); } return o; }""")
        mby = {v: e for e in mraw for v in [str(e.get("mmid"))] }
        MARK = "…(+"
        # THE CONTRACT CHANGED, DELIBERATELY: these fields are no longer cut at all.
        # Measured on 39 frozen sites, removing every per-field bound costs +3.1%
        # total chars and 1.002x on the median page — a LABEL is bounded by human
        # authorship, so the cap bought almost nothing and cost nine silent-cut
        # defects. These checks previously asserted the marker was present; they now
        # assert the value arrives WHOLE, which is the stronger guarantee.
        for key, field, label in (("mv", "value", "an input's value"),
                                  ("mp2", "placeholder", "a placeholder"),
                                  ("mc", "value", "a combobox trigger's text"),
                                  ("mb", "text", "a button's own text")):
            e = mby.get(str(mid.get(key)))
            got = ((e or {}).get(field) or "") or ((e or {}).get("label") or "")
            check(f"M-{key} {label} is returned COMPLETE, not cut",
                  got == LONG, f"len={len(got)} of {len(LONG)}: {got[-30:]!r}")
        # The count must be the TRUE residual, not a constant: an agent decides
        # whether to escalate to a scoped read from this number.
        # ONE class of field still carries a bound: genuinely UNBOUNDED content, where
        # a single essay would otherwise evict every other row from the caller's
        # max_chars budget. There the residual must be exact — that number is how an
        # agent decides whether a scoped read is worth a call.
        import re as _re
        _BIG = "sierra tango " * 500          # 6500 chars, over the 4000 textarea bound
        await mp.set_content(
            "<!DOCTYPE html><meta charset=utf-8><body>"
            f"<textarea id=ta rows=4>{_BIG}</textarea></body>")
        await mp.wait_for_timeout(140)
        traw = await mp.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        _tv = next((e.get("value") or "" for e in traw if e.get("tag") == "textarea"), "")
        _m = _re.search(r"…\(\+(\d+)\)$", _tv)
        check("M-count unbounded content keeps a bound, and its residual is exact",
              bool(_m) and len(_tv.split(MARK)[0]) + int(_m.group(1)) == len(_BIG.strip()),
              f"shown={len(_tv.split(MARK)[0])} +{_m.group(1) if _m else '?'} vs true={len(_BIG.strip())}")
        # A marker that is itself truncated is worse than no marker: `…(+4` reads
        # as content. `label` derives from four fields that markCut has ALREADY
        # bounded, and was then re-clipped at 60 — so every marked source over
        # ~54 chars came out with its own marker sliced in half. Found by the
        # corpus cap-detector (label@60: 610 fields, neighbours 14), not by
        # reading the code, and not by any fixture that only checked the sources.
        def _wellformed(entries):
            bad = []
            for e in entries:
                for f in ("name", "label", "value", "placeholder", "text", "near"):
                    v = e.get(f) or ""
                    if isinstance(v, str) and "…(+" in v and not v.endswith(")"):
                        bad.append(f"{f}={v[-18:]!r}")
            return bad
        _bad = _wellformed(mraw) + _wellformed(raw)
        check("M-intact no field carries a marker that is itself cut in half",
              not _bad, "; ".join(_bad[:3]))
        # The specific shape: a long name, where `label` adopts an already-marked
        # string and must not bound it a second time.
        await mp.set_content(
            "<!DOCTYPE html><meta charset=utf-8><body>"
            f"<button id=ml aria-label='{LONG}'>x</button></body>")
        await mp.wait_for_timeout(120)
        lraw = await mp.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        _le = next((e for e in lraw if (e.get("name") or "").startswith("Alpha")), None)
        check("M-derived a derived label carries its source's FULL text",
              bool(_le) and (_le.get("label") or "") == LONG,
              f"len={len((_le or {}).get('label') or '')} of {len(LONG)}")

        await mp.close()

        xp = await browser.new_page(viewport={"width": 1000, "height": 700})
        await xp.set_content(
            "<!DOCTYPE html><meta charset=utf-8><body style='margin:0'>"
            "<iframe srcdoc=\"<body style='margin:0'><button id=b style='position:absolute;"
            "left:100px;top:80px;width:120px;height:40px'>Deep Target</button></body>\" "
            "style='position:absolute;left:40px;top:60px;width:600px;height:400px;border:0;"
            "transform:scale(0.5);transform-origin:0 0'></iframe></body>")
        await xp.wait_for_timeout(300)
        xfr = next((f for f in xp.frames if f != xp.main_frame), None)
        truth = await (await xfr.query_selector("#b")).bounding_box()
        xout = await xp.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        xe = next((x for x in xout if "Deep Target" in ((x.get("text") or "") + (x.get("label") or ""))), None)
        check("X1 a listed box inside a scale(.5) frame matches what the user sees",
              bool(xe) and abs(xe["x"] - truth["x"]) <= 2 and abs(xe["y"] - truth["y"]) <= 2
              and abs(xe["w"] - truth["width"]) <= 2,
              f"listed=({(xe or {}).get('x')},{(xe or {}).get('y')},{(xe or {}).get('w')}) "
              f"truth=({truth['x']:.0f},{truth['y']:.0f},{truth['width']:.0f})")
        xrect = await xp.evaluate("(function(){ " + RECTFOR + "; return _rectForPage(\"[mmid='\" + "
                                  + repr((xe or {}).get("mmid", "0")) + " + \"']\"); })()")
        cx, cy = truth["x"] + truth["width"] / 2, truth["y"] + truth["height"] / 2
        check("X2 ...and so does the CDP click point (a different code path)",
              bool(xrect) and abs(xrect["x"] - cx) <= 2 and abs(xrect["y"] - cy) <= 2,
              f"click=({(xrect or {}).get('x')},{(xrect or {}).get('y')}) centre=({cx:.0f},{cy:.0f})")
        await xp.close()

        # ---- A: ACTION-TIME occlusion pre-flight --------------------------------
        # The listing's (occluded/blocked) tag is observation-time. A consent modal
        # that appears AFTER the read means a trusted click lands on whatever is now
        # on top — plausibly its own "Accept all" — and the tool reports success on
        # the element you named. Both negative controls matter as much as the
        # positive: refusing a click that would have worked is its own failure.
        ap = await browser.new_page(viewport={"width": 800, "height": 700})
        await ap.set_content(
            "<!DOCTYPE html><meta charset=utf-8><body style='margin:0'>"
            "<button id=ok style='position:absolute;left:50px;top:50px;width:120px;height:40px'>Save</button>"
            "<button id=under style='position:absolute;left:50px;top:200px;width:120px;height:40px'>Delete account</button>"
            "<div style='position:fixed;left:0;top:150px;width:100%;height:200px;background:rgba(0,0,0,.6)'>"
            "<button style='margin:20px'>Accept all</button></div>"
            "<div style='position:relative;padding-left:24px;top:400px'>"
            "<input type=checkbox id=cb style='position:absolute;left:0;top:0;width:16px;height:20px;opacity:0'>"
            "<label for=cb style='cursor:pointer'>Accept terms</label></div>"
            "<div style='position:fixed;left:0;top:0;width:100%;height:120px;pointer-events:none'></div></body>")
        await ap.wait_for_timeout(150)
        await ap.evaluate("()=>{let i=0;document.querySelectorAll('*').forEach(e=>e.setAttribute('mmid',String(++i)));"
                          "window.__mmidReg=new Map([...document.querySelectorAll('[mmid]')].map(e=>[e.getAttribute('mmid'),e]));}")

        async def _blocked(sel):
            # Pass the mmid as an ARGUMENT rather than splicing it into the source.
            # The first version spliced with a .replace() that bound to the wrong
            # string literal, so every lookup was [mmid='PLACEHOLDER'], every result
            # was null, and all three checks reported "clear" — two of them PASSING
            # for exactly the reason that should have failed them.
            mm = await ap.evaluate("(s)=>document.querySelector(s).getAttribute('mmid')", sel)
            r = await ap.evaluate("(mm)=>{ " + RECTFOR + "; return _rectForPage(\"[mmid='\"+mm+\"']\"); }", mm)
            assert r is not None, f"fixture lookup failed for {sel} (mmid={mm})"
            return r.get("blockedBy") or ""

        b_under = await _blocked("#under")
        check("A1 a click that would land on an overlay is refused, and names the blocker",
              b_under != "" and "Accept all" in b_under, f"blockedBy={b_under!r}")
        check("A2 a pointer-events:none layer does NOT block (clicks pass through it)",
              (await _blocked("#ok")) == "", "clear")
        check("A3 a control under its OWN label does NOT block (styled-input pattern)",
              (await _blocked("#cb")) == "", "clear")
        await ap.close()

        # ---- S: shadow DOM ------------------------------------------------------
        pw = [x for x in raw if x.get("tag") == "input" and x.get("type") == "password"]
        check("S1 required marker on a shadow-root label[for] sets (required)",
              bool(pw) and pw[0].get("required") is True,
              f"found={len(pw)} required={pw[0].get('required') if pw else None}")
        check("S2 aria-hidden on a component HOST excludes its shadow content",
              not by_text(raw, "Hidden twin"),
              f"leaked={[x.get('label') for x in by_text(raw, 'Hidden twin')]}")

        listing = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()")
        check("S3 an <h1> inside a shadow root becomes the page's Main heading",
              "コンポーネント内の見出し" in listing,
              next((l for l in listing.splitlines() if l.startswith("Main heading")), "ABSENT"))

        # Shadow dialog: the modal banner and the dialog text both used
        # document.querySelectorAll and saw nothing here.
        await page.evaluate("() => window.__openShadowDialog()")
        await page.wait_for_timeout(150)
        dl = await page.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()")
        check("S4 a dialog inside a shadow root raises the MODAL banner",
              "A MODAL/DIALOG IS CURRENTLY OPEN" in dl,
              "banner present" if "A MODAL/DIALOG IS CURRENTLY OPEN" in dl else "NO BANNER")
        dtl = next((l for l in dl.splitlines() if l.startswith("Dialog text:")), "")
        check("N3 its Japanese body text is extracted (the ASCII filter returned empty)",
              "取り消せません" in dtl, dtl[:90] or "ABSENT")
        check("S5 shadow-root buttons are excluded from that dialog text",
              bool(dtl) and "キャンセル" not in dtl and "削除" not in dtl.split("しますか")[-1],
              dtl[:90])

        # ---- outline sees shadow headings ---------------------------------------
        txt = await page.evaluate("(function(){ " + DOMTEXT + "; return _domTextPage(); })()")
        outline = txt.split("--- DOCUMENT OUTLINE")[-1] if "--- DOCUMENT OUTLINE" in txt else ""
        check("S6 get_page_text's outline includes headings from inside shadow roots",
              "コンポーネント内の見出し" in outline,
              next((l.strip() for l in outline.splitlines() if "見出し" in l), "ABSENT"))

        # ---- TB: a scoped table keeps its ROW/COLUMN association ----------------
        # innerText flattens a table into a run of cells with nothing saying which
        # column a value belongs to, so the row/column association — which is the
        # entire content of a table — was lost in the one tool that could reach the
        # data at all. CLAUDE.md #14: a scoped read of a table returned 8 column
        # headers and ZERO data rows, and three separate live agents fell back to
        # javascript_tool from three different directions.
        tb = await browser.new_page(viewport={"width": 900, "height": 700})
        await tb.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await tb.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<div id=wrap><p>Notes before.</p>"
            "<table><thead><tr><th>Region</th><th>Q1</th><th>Q2</th></tr></thead><tbody>"
            "<tr><td>North</td><td>1,240</td><td>1,600</td></tr>"
            "<tr><td>東京</td><td>2,300</td><td>2,450</td></tr>"
            "</tbody></table><p>Notes after.</p></div>"
            "<table id=solo><tr><td>x</td><td>y</td></tr><tr><td>z</td><td>w</td></tr></table>"
            "<table id=one><tr><td>lonely</td></tr></table>"
            "<button>Go</button></body>")
        await tb.wait_for_timeout(130)
        await tb.evaluate("(function(){ " + COLLECT
                          + "; return _collectInteractivePage(true,null,'compact',false,false); })()")

        async def scoped(el_id):
            mm = await tb.evaluate(
                f"()=>{{const e=document.getElementById('{el_id}');return e?e.getAttribute('mmid'):null;}}")
            if not mm:
                return None
            return await tb.evaluate("(function(){ " + DOMTEXT
                                     + "; return _domTextPage('" + str(mm) + "'); })()")

        # A capability the agent cannot DISCOVER is not a capability. A <table> is
        # not interactive, so it has no row and find cannot reach it — verifying the
        # renderer live on the Fed's H.15 page required javascript_tool to look the
        # ref up, which is the exact fallback CLAUDE.md #14 recorded three agents
        # being forced into. The listing now names the tables and hands over refs.
        _full = await tb.evaluate("(function(){ " + COLLECT
                                  + "; return _collectInteractivePage(false,null,'compact',false,false); })()")
        _tnote = next((l for l in _full.splitlines() if "data table(s)" in l), "")
        check("TB9 the listing names the page's data tables and hands over their refs",
              "data table(s)" in _tnote and "ref_" in _tnote and "3x3" in _tnote,
              _tnote.strip()[:110])
        _tref = re.search(r"ref_(\d+) \(3x3\)", _tnote)
        check("TB10 ...and that ref scopes to the table it named",
              bool(_tref), _tref.group(0) if _tref else "NO REF")

        w = await scoped("wrap") or ""
        rows = [l.strip() for l in w.splitlines() if "|" in l and "---" not in l]
        check("TB1 a scoped table renders as aligned rows, not flattened cells",
              "--- TABLE (" in w and any(r.startswith("North |") for r in rows),
              next((r for r in rows if r.startswith("North")), "NO DATA ROW") [:70])
        check("TB2 column names come from <th> (the document declaring them)",
              any(r.startswith("Region |") for r in rows),
              next((r for r in rows if "Region" in r), "NO HEADER")[:70])
        check("TB3 a non-Latin cell survives with its row intact",
              any(r.startswith("東京 |") and "2,300" in r for r in rows),
              next((r for r in rows if "東京" in r), "ABSENT")[:70])
        # Cells must not appear twice: the first version appended the grid WITHOUT
        # hiding the table first, so every value was emitted once as flat text and
        # again in the grid — doubling the cost of the one region the caller asked
        # for.
        check("TB4 cells are not duplicated as flat text alongside the grid",
              w.count("1,240") == 1, f"'1,240' x{w.count('1,240')}")
        check("TB5 surrounding prose in the scope is preserved",
              "Notes before." in w and "Notes after." in w)

        s = await scoped("solo") or ""
        check("TB6 a table that IS the scope returns the grid with no textContent garbage",
              "--- TABLE (" in s and "xy" not in s.replace("\n", "") and "x | y" in s,
              s.replace("\n", " / ")[:80])
        o = await scoped("one") or ""
        check("TB7 a single-row table is not re-rendered as a grid, but its text "
              "still comes back",
              "--- TABLE (" not in o and "lonely" in o, o[:60])
        # The hide is temporary; leaving it applied would blank the table for the
        # NEXT reader. Same restore discipline as the gutter strip.
        whole = await tb.evaluate("(function(){ " + DOMTEXT + "; return _domTextPage(); })()")
        check("TB8 hidden-then-restored: the whole-page read still sees the table",
              "1,240" in whole and "東京" in whole)
        await tb.close()

        # ---- WM: WebMCP — tools the PAGE declares about itself -------------------
        # Tested against a STUB document.modelContext so discovery, schema parsing,
        # the annotation surface and the zero-cost-when-absent path are all pinned
        # without needing a Chrome origin trial. The real API is verified live.
        PT = extract("_pageToolsPage")
        CT = extract("_callPageToolPage")
        wm = await browser.new_page(viewport={"width": 900, "height": 700})
        await wm.set_content("<!doctype html><meta charset=utf-8><body><button>ui</button></body>")
        await wm.wait_for_timeout(60)

        # Absent API first: this is every page on today's web, and it must report
        # "not supported" rather than erroring or looking like a broken bridge.
        none = await wm.evaluate("(function(){ " + PT + "; return _pageToolsPage(); })()")
        check("WM1 a page with no modelContext reports supported=false, not an error",
              none.get("supported") is False and none.get("tools") == [],
              json.dumps(none)[:80])

        await wm.evaluate("""() => {
            document.modelContext = {
              getTools: async () => ([
                { name: 'searchProducts', description: 'Search the catalogue',
                  // getTools() returns inputSchema as a JSON STRING
                  inputSchema: JSON.stringify({type:'object',properties:{query:{type:'string'}}}),
                  annotations: { readOnlyHint: true }, origin: 'https://shop.example' },
                { name: 'addToCart', description: '注文に追加',
                  inputSchema: JSON.stringify({type:'object',properties:{sku:{type:'string'}}}),
                  annotations: { readOnlyHint: false, untrustedContentHint: true },
                  origin: 'https://shop.example' },
              ]),
              executeTool: async (t, argsJson) => {
                if (t.name === 'addToCart') return 'added ' + JSON.parse(argsJson).sku;
                if (t.name === 'navigateAway') return null;
                return 'searched';
              },
            };
        }""")
        got = await wm.evaluate("(function(){ " + PT + "; return _pageToolsPage(); })()")
        names = [t["name"] for t in got.get("tools", [])]
        check("WM2 declared tools are enumerated with their names",
              got.get("supported") is True and names == ["searchProducts", "addToCart"],
              str(names))
        check("WM3 inputSchema arrives PARSED, not as an escaped string",
              isinstance(got["tools"][0].get("inputSchema"), dict)
              and got["tools"][0]["inputSchema"]["properties"]["query"]["type"] == "string",
              type(got["tools"][0].get("inputSchema")).__name__)
        # readOnlyHint is the DECLARED destructiveness signal that #24 removed the
        # submit wordlists for lacking. It must survive to the caller intact.
        check("WM4 readOnlyHint=false survives as the declared 'this changes state' signal",
              got["tools"][1]["annotations"]["readOnlyHint"] is False
              and got["tools"][1]["annotations"]["untrustedContentHint"] is True,
              json.dumps(got["tools"][1]["annotations"]))
        check("WM5 a non-Latin description is not mangled",
              got["tools"][1]["description"] == "注文に追加",
              got["tools"][1]["description"])

        ran = await wm.evaluate("(function(){ " + CT + "; return _callPageToolPage('addToCart', '{\"sku\":\"A-1\"}'); })()")
        check("WM6 call_page_tool runs the named tool and returns its result",
              ran.get("ok") is True and ran.get("result") == "added A-1"
              and ran.get("readOnly") is False, json.dumps(ran)[:90])
        miss = await wm.evaluate("(function(){ " + CT + "; return _callPageToolPage('nope', '{}'); })()")
        check("WM7 an unknown tool name is refused AND the alternatives are named",
              miss.get("ok") is False and "searchProducts" in (miss.get("available") or []),
              json.dumps(miss)[:100])
        # executeTool resolves null on navigation: a real outcome, not a failure,
        # and every previously-read ref is stale afterwards.
        await wm.evaluate("""() => { const g = document.modelContext.getTools;
            document.modelContext.getTools = async () => (await g()).concat(
              [{ name: 'navigateAway', description: 'go', inputSchema: '{}', annotations: {} }]); }""")
        nav = await wm.evaluate("(function(){ " + CT + "; return _callPageToolPage('navigateAway', '{}'); })()")
        check("WM8 a tool that navigates reports navigated=true rather than failing",
              nav.get("ok") is True and nav.get("navigated") is True, json.dumps(nav)[:90])
        await wm.close()

        # ---- RG: off-viewport content is LOCATED, and reachable without scrolling -
        # A bare "76 more elements are BELOW the viewport" leaves exactly one move:
        # scroll and re-read the whole page. Measured on Mind2Web gold paths that is
        # 76 of 173 steps at a full extra listing each. Naming the regions AND their
        # refs, plus letting a scoped read escape the viewport filter, replaces that
        # with one small read.
        rg = await browser.new_page(viewport={"width": 900, "height": 600})
        await rg.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await rg.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<header><a href=/h>Home</a></header>"
            "<main><p>top</p><div style='height:1400px'></div>"
            "<a href=/d1>Deep One</a><a href=/d2>Deep Two</a><button>Deep Btn</button></main>"
            "<footer><a href=/f1>F1</a><a href=/f2>F2</a></footer></body>")
        await rg.wait_for_timeout(140)
        full = await rg.evaluate("(function(){ " + COLLECT
                                 + "; return _collectInteractivePage(false,null,'compact',false,false); })()")
        note = next((l for l in full.splitlines() if l.startswith("[")), "")
        check("RG1 the off-viewport hint names the REGIONS, not just a count",
              "main(ref_" in note and "footer(ref_" in note, note[:120])
        m = re.search(r"main\(ref_(\d+)\): (\d+)", note)
        check("RG2 ...with a per-region count", bool(m) and m.group(2) == "3",
              m.group(0) if m else "NO MATCH")
        # The advice has to be PERFORMABLE. The first version named the regions and
        # said to use read_page(ref_id=<that region's ref>) while giving no way to
        # learn the ref, because a landmark container is not interactive and has no
        # row — so the measurement assumed a recovery the agent could not carry out.
        sub = await rg.evaluate("(function(){ " + COLLECT
                                + "; return _collectInteractivePage(false,'" + (m.group(1) if m else "0")
                                + "','compact',false,false); })()")
        check("RG3 the ref in that hint actually scopes to the region",
              "Deep One" in sub and "Deep Two" in sub and "Deep Btn" in sub,
              f"{len([l for l in sub.splitlines() if l.startswith('ref_')])} rows")
        check("RG4 a SCOPED read escapes the viewport filter (the whole point)",
              sub.count("(below-fold)") >= 3,
              f"{sub.count('(below-fold)')} rows flagged below-fold")
        check("RG5 ...and content outside the scope stays out of it",
              "Home" not in sub and "F1" not in sub)
        # PAGE-LEVEL FACTS MUST NOT LEAK INTO A SCOPED READ. Found live: a read
        # scoped to craigslist's footer returned 7 links under "the DOM holds 955
        # controls but only 7 were collectable", inviting the agent to hunt for 948
        # elements it had just excluded on purpose. The gap that note reports is
        # meaningless once the caller narrows the read. Same class as #11.
        check("RG7 the hidden-tab 'DOM holds N controls' note is absent when scoped",
              "were collectable" not in sub,
              next((l.strip() for l in sub.splitlines() if "collectable" in l), ""))
        # Unscoped reads must NOT start carrying the whole page: that variant was
        # measured at 1.51x-3.39x tokens for the same 96.0% recoverable and reverted.
        check("RG6 the UNSCOPED listing is still viewport-only",
              "Deep One" not in full and "Home" in full,
              f"{len([l for l in full.splitlines() if l.startswith('ref_')])} rows unscoped")
        await rg.close()

        await browser.close()

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} generality checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
