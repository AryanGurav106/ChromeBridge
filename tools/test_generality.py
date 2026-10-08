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
                              'gp-wrap','gp-inner','gq-shell',
                              'gt-badge',
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
        # A name read off a class name is a GUESS, not something the page says out
        # loud. #23 made this fix for data-* automation hooks and left the icon path
        # unattributed, so a library's token for a glyph sat in the slot the legend
        # calls "the field's IDENTITY" with nothing marking it.
        check("N4b ...and says so, because a class name is not an accessible name",
              bool(e) and e.get("synth") == "icon-class",
              f"synth={(e or {}).get('synth')!r}")
        _bg = ent.get("gt-badge")
        check("N4c an icon+badge link is not listed as its badge count alone",
              bool(_bg) and "envelope" in ((_bg.get("label") or "") + (_bg.get("name") or "")),
              f"label={(_bg or {}).get('label')!r} text={(_bg or {}).get('text')!r}"
              f" (it used to list as just the count)")

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

        # ---- H: no heuristic deletes ---------------------------------------------
        # The complete list of rules that can remove an element is now:
        # not-visible / not-connected / aria-hidden / inert (all spec-decided,
        # the page declaring the element absent) plus `not-interactive`, which is
        # the COMPLEMENT of the declaration set in isInteractive — HTML
        # interactive tags, audio/video[controls], canvas/svg, an ARIA
        # interactive role, onclick/tabindex/contenteditable, a registered
        # listener, cursor:pointer, a measured-monospace editor host. "The page
        # declared nothing about this element" is not a guess about what matters.
        # Everything that IS such a guess demotes. H1/H2 pin the last two rules
        # that used to delete; H3 is the negative control that the demotion is a
        # real verdict and not an accident of the fixture.
        _pw, _pi = ent.get("gp-wrap"), ent.get("gp-inner")
        check("H1 a same-label child of a listed control EXISTS, demoted not deleted"
              " — the field react-select renames on commit",
              bool(_pw) and bool(_pi) and _pi.get("demoted") == "was:parent-child-dedup",
              f"wrapper={'present' if _pw else 'ABSENT'} inner={'present' if _pi else 'ABSENT'}"
              f" inner.demoted={(_pi or {}).get('demoted')!r}")
        _qs = ent.get("gq-shell")
        check("H2 a handler-only app shell over 9 controls EXISTS, demoted not deleted",
              bool(_qs) and _qs.get("demoted") == "was:delegation-root",
              f"entry={'present' if _qs else 'ABSENT'} demoted={(_qs or {}).get('demoted')!r}")
        check("H3 ...and the shell's 9 children are listed on their own, undemoted"
              " (a demotion that swallowed its subtree would be a deletion by"
              " another name)",
              sum(1 for e in raw if (e.get("label") or "") in
                  ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
                  and not e.get("demoted")) == 9,
              "kept+undemoted children="
              + str(sum(1 for e in raw if (e.get("label") or "") in
                        ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
                        and not e.get("demoted"))))

        # H4: the zoo has carried an aria-hidden HOST with a button inside its
        # shadow root since the shadow fixtures were written, and nothing ever
        # asserted on it — a fixture with no check, which is how CLAUDE.md #25
        # came to list "aria-hidden shadow subtrees" among three drop rules
        # "proven invisible even to ledger:true". `closest()` genuinely does not
        # cross a shadow boundary, so the concern was reasonable; the drop is
        # handled elsewhere and IS recorded. Both halves are asserted, because a
        # correct-but-silent drop is exactly what left this unfalsifiable.
        _led = await page.evaluate(
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(true, null, 'compact', true); })()")
        _gi = await page.evaluate("""() => {
            const h = document.getElementById('gi-host');
            const b = h && h.shadowRoot && h.shadowRoot.querySelector('button');
            return { btn: b && b.getAttribute('mmid'),
                     closestCrosses: !!(b && b.closest && b.closest('[aria-hidden="true"]')) };
        }""")
        _rows = [d for d in (_led.get("dropped") or []) if str(d["mmid"]) == str(_gi["btn"])]
        check("H4 a control in the shadow root of an aria-hidden HOST is excluded AND"
              " recorded, even though closest() cannot see across the boundary",
              not any(str(e["mmid"]) == str(_gi["btn"]) for e in _led["elements"])
              and [d["rule"] for d in _rows] == ["aria-hidden"]
              and _gi["closestCrosses"] is False,
              f"listed={any(str(e['mmid']) == str(_gi['btn']) for e in _led['elements'])}"
              f" rules={[d['rule'] for d in _rows]} closest_crosses={_gi['closestCrosses']}")

        # ---- H5: A BLANK RESULT MUST STILL EXPLAIN ITSELF --------------------
        # `blankNote` was computed and never used — assigned, then dropped, so the one
        # case where the agent most needs an explanation produced the LEAST output.
        # Observed live on ant.design in a background tab, where the whole response
        # was one line: `Current URL: /components/select`. No count, no "0 elements",
        # no readiness banner, and no hidden-tab note either (the legend returns early
        # when nothing was collected, and that note lives in the legend). An agent
        # reads that as "this page has no controls" — and the page has 557.
        bp = await browser.new_page(viewport={"width": 900, "height": 700})
        await bp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # add_init_script only affects documents created AFTER it, and set_content
        # reuses the existing about:blank — without this navigation listener_tag.js
        # never runs and everything below tests an untagged page. Pinned by C14.
        await bp.goto("about:blank")
        await bp.set_content("<!doctype html><meta charset=utf-8><body style='margin:0'>"
                             "<p>" + ("Plenty of prose. " * 20) + "</p></body>")
        await bp.wait_for_timeout(120)
        _blank = await bp.evaluate(
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(false,null,'compact',false,false,'tree'); })()")
        check("H5 a page with text and zero controls says so, instead of returning"
              " only the URL line",
              "NO interactive elements" in _blank,
              " | ".join(l.strip()[:70] for l in _blank.splitlines()) or "EMPTY OUTPUT")
        await bp.close()

        # ---- CU: a pointer cursor is INHERITED, so it is not always a declaration --
        # `cursor` is an inherited CSS property, so a pointer cursor on a descendant
        # of a control belongs to the CONTROL — the same error contenteditable-non-root
        # corrects, where isContentEditable is inherited and only the root is the
        # control. Measured on Wikipedia's citation markup
        # (`<sup><a><span class=cite-bracket>[`): three rows per citation, the anchor
        # plus its two bracket spans, each declaring nothing of its own.
        #
        # CU2 IS THE LOAD-BEARING HALF. A segmented control written as
        # `<div onclick><span>Day</span><span>Week</span></div>` has the IDENTICAL
        # shape, and there the spans really are distinct targets because a delegated
        # handler dispatches on event.target — dropping them would leave one row
        # labelled "Day Week Month" and no way to pick Week. HTML settles it: an <a>
        # or <button> does ONE thing when activated, so its descendants cannot be
        # separate targets, while a generic element with a handler makes no such
        # promise. Both fixtures on ONE page, so neither can pass by configuration.
        cu = await browser.new_page(viewport={"width": 900, "height": 700})
        await cu.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # add_init_script only affects documents created AFTER it, and set_content
        # reuses the existing about:blank — without this navigation listener_tag.js
        # never runs and everything below tests an untagged page. Pinned by C14.
        await cu.goto("about:blank")
        await cu.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<p>Cited<sup class=reference><a href='#c1'>"
            "<span class=b>[</span>1<span class=b>]</span></a></sup>.</p>"
            "<div id=seg onclick='void 0' style='cursor:pointer;width:300px;height:30px'>"
            "<span style='display:inline-block;width:90px'>Day</span>"
            "<span style='display:inline-block;width:90px'>Week</span>"
            "<span style='display:inline-block;width:90px'>Month</span></div></body>")
        await cu.wait_for_timeout(140)
        _cul = await cu.evaluate(
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(false,null,'compact',false,false,'tree'); })()")
        _curows = [l for l in _cul.splitlines() if "ref_" in l and "|" in l]
        check("CU1 a citation's bracket spans are parts of the link, not three rows",
              len([l for l in _curows if '"["' in l or '"]"' in l]) == 0
              and any('[ 1 ]' in l for l in _curows),
              " / ".join(r.strip()[:38] for r in _curows[:4]))
        check("CU2 ...while a delegating container's children stay distinct targets,"
              " because activating a <div> promises nothing",
              all(any(f'"{w}"' in l for l in _curows) for w in ("Day", "Week", "Month")),
              " / ".join(r.strip()[:30] for r in _curows))
        _cled = await cu.evaluate(
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(false,null,'compact',true,false,'tree'); })()")
        # CU4: NOTHING MAY LOSE AN IDENTITY, the condition that changed this rule after
        # it was written. The owner test alone removed 155 labels on mdn_select and 28
        # on gh_issues that appeared on NO kept row — including
        # span "188530 users starred this repository" inside a link whose own
        # aria-label is shorter. Those spans are not separate TARGETS, which the owner
        # test decides correctly; their TEXT is content, and deleting it is silent loss.
        # When the owner declares NO override its name comes from its content and
        # therefore contains the descendant's text, so nothing is lost — that is CU1.
        # THE aria-label MUST NOT CONTAIN THE SPAN'S TEXT or the containment test is
        # satisfied and this passes without exercising the rule.
        _ovr = await cu.evaluate(
            "()=>{const a=document.createElement('a');a.href='/repo/stargazers';"
            "a.setAttribute('aria-label','Star');a.style.cssText='display:block;width:200px;height:24px';"
            "a.innerHTML='<span id=sc>188530 users starred this repository</span>';"
            "document.body.appendChild(a);return 1;}")
        await cu.wait_for_timeout(90)
        _ovl = await cu.evaluate(
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(false,null,'compact',false,false,'tree'); })()")
        check("CU4 a descendant whose text the owner's aria-label does NOT carry keeps"
              " its row — the rule may not delete an identity",
              "188530 users starred" in _ovl,
              next((l.strip()[:80] for l in _ovl.splitlines() if "188530" in l),
                   "IDENTITY LOST — the only row says aria-label 'Star'"))
        # CU5: THE SHAPE WIKIPEDIA ACTUALLY SHIPS, found live after CU1 shipped. The
        # <a> wraps ONE span that is its entire content, so the span's text is
        # non-empty and the no-identity rule keeps it -- each citation still printed
        # two rows. The tree's identical-nested-row collapse could not merge them
        # either: it needs exact label equality, and the two names come from different
        # AccName paths ("[4]" from a text node vs "[ 4 ]" separator-joined, #28).
        # So the rule also drops a descendant whose identity EQUALS its owner's --
        # equality, never containment, because containment against innerText is
        # trivially true for any descendant and is the wide version that lost 93.
        await cu.evaluate(
            "()=>{const s=document.createElement('sup');s.className='reference';"
            "const a=document.createElement('a');a.setAttribute('href','#n4');"
            "const w=document.createElement('span');w.textContent='[4]';"
            "a.appendChild(w);s.appendChild(a);"
            "document.body.appendChild(s);return 1;}")
        await cu.wait_for_timeout(90)
        _cu5 = await cu.evaluate(
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(false,null,'compact',false,false,'tree'); })()")
        _c5rows = [l for l in _cu5.splitlines() if '"[4]"' in l]
        check("CU5 a wrapper span whose identity EQUALS its owner's does not get a"
              " second row for the same citation",
              len(_c5rows) == 1 and " a " in _c5rows[0],
              " / ".join(r.strip()[:44] for r in _c5rows) or "NO ROW AT ALL")
        # CU6: THE OWNER'S title IS NOT ITS NAME. Found live on Wikipedia's
        # [citation needed], where the <a> carries title="Wikipedia:Citation needed"
        # while its ROW correctly displays "citation needed" from content -- so the
        # inner span, compared against the title, looked different and got a second
        # row saying the identical thing. AccName's order is aria-labelledby,
        # aria-label, native markup, NAME FROM CONTENT, and title only as a last
        # resort; comparing against the title put this rule out of step with the
        # collector's own name resolution for the very same element.
        # THE TITLE MUST DIFFER FROM THE TEXT or the comparison succeeds either way
        # and this passes without exercising the precedence.
        await cu.evaluate(
            "()=>{const sup=document.createElement('sup');"
            "const a=document.createElement('a');a.setAttribute('href','/wiki/CN');"
            "a.setAttribute('title','Wikipedia:Citation needed');"
            "const sp=document.createElement('span');"
            "sp.setAttribute('title','This claim needs references to reliable sources.');"
            "sp.textContent='citation needed';"
            "a.appendChild(sp);sup.appendChild(a);document.body.appendChild(sup);return 1;}")
        await cu.wait_for_timeout(90)
        _cu6 = await cu.evaluate(
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(false,null,'compact',false,false,'tree'); })()")
        _c6 = [l for l in _cu6.splitlines() if "citation needed" in l]
        check("CU6 an owner's title does not stand in for its name, so a span"
              " repeating the link's own text gets no second row",
              len(_c6) == 1 and " a " in _c6[0],
              " / ".join(r.strip()[:52] for r in _c6) or "NO ROW AT ALL")
        check("CU3 ...and the removal is RECORDED, so the ledger can answer why a"
              " bracket span has no row",
              any(str(d.get("rule")) == "cursor-inherited-non-root"
                  for d in (_cled.get("dropped") or [])),
              str(sorted({str(d.get("rule")) for d in (_cled.get("dropped") or [])})[:6]))
        await cu.close()

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
            for (const id of ['gd-link','gd-plain','gd-imglink','gd-data','gd-tracker','gp-submit','gp-leaf','gq-bg','gq-grad','gs-cb','gs-decoy','gs-live','gs-file','gs-cbx','gs-card','gt-day','gt-sec','gt-alink','gt-longalt'])
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
        # P2b is P2's twin, differing ONLY by the declaration. Live on demoqa:
        # react-select drops its <input> to opacity:0 on commit and paints the
        # value into a sibling, so the State field disappeared from every listing
        # the moment it was filled — "no State field" and "State holds NCR" were
        # the same output, the verification read as failure, and the retry hit
        # City, which had shifted into its slot. Focusability cannot separate the
        # two (both are focusable, and Monaco's read-only ime-text-area is too,
        # which #24 recorded form_input reporting Success into). The declaration
        # can. Keep these two side by side: they are one rule seen from both ends.
        check("P2b ...while the same shape DECLARING role=combobox is kept — the"
              " react-select-after-commit field",
              dm["gs-live"] in by,
              "kept" if dm["gs-live"] in by
              else "DELETED — a filled combobox vanishes the moment it succeeds")
        # P2c/P2d: the first version of P2b only covered a declared ARIA role, and a
        # live probe then showed a transparent input survived ONLY when a <label>
        # wrapped it (feeding `ownLabel`) — so the opacity-0 input[file] under a
        # styled upload button, the very case the collector's comment cites as
        # must-keep, did not work, and an explicit aria-label did not rescue it.
        # An input's TYPE is a declaration too: a checkbox/radio/file IS its type,
        # and unlike a text field there is no mirror-checkbox idiom for P2's decoy
        # rule to protect against. file_upload() needs the input's own ref, and a
        # checkbox needs its own row for (checked) to be readable at all.
        _pf, _pc = by.get(dm["gs-file"]), by.get(dm["gs-cbx"])
        check("P2c an opacity:0 input[file] under a styled button is kept — its ref"
              " is the only thing file_upload can act on",
              _pf is not None and _pf.get("type") == "file",
              f"listed={_pf is not None} type={(_pf or {}).get('type')}")
        check("P2d ...and an opacity:0 checkbox whose click target is a SIBLING"
              " label[for] is kept, as a checkbox, with its state readable",
              _pc is not None and _pc.get("type") == "checkbox"
              and "Remember me" in (_pc.get("name") or ""),
              f"listed={_pc is not None} type={(_pc or {}).get('type')} "
              f"name={(_pc or {}).get('name')!r}")
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

        # CV4: a drawing surface DECLARES itself. NOTE the wrapper carries onclick:
        # without it the div is not interactive, has no entry, and this check passes
        # VACUOUSLY -- confirmed by running it against the pre-removal collector,
        # which is the only way to know a fixture reproduces what it names. The second copy of a class-name
        # regex — /(^|[\s-])canvas($|[\s_-])/ over className, with an
        # `!/off-?canvas/` exception bolted on after it told an agent to use VISION
        # for an entire IRS page of plain HTML — survived the #27 removal, which
        # only took the copy in isInteractive. A word-match on a class name plus a
        # list of the cases where the word means something else is the shape this
        # project keeps being burned by. Nothing replaces it: tldraw's .tl-canvas
        # CONTAINS a real <canvas>, and that is what gets marked.
        dp2 = await browser.new_page(viewport={"width": 1100, "height": 800})
        await dp2.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # add_init_script only affects documents created AFTER it, and set_content
        # reuses the existing about:blank — without this navigation listener_tag.js
        # never runs and everything below tests an untagged page. Pinned by C14.
        await dp2.goto("about:blank")
        await dp2.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            # A page-builder wrapper whose class merely contains the WORD, holding
            # ordinary HTML. It must not be announced as pixels.
            "<div class='editor-canvas-wrap' onclick='void 0'"
            " style='width:900px;height:600px'>"
            "<button style='width:120px;height:30px'>Ordinary control</button></div>"
            # The real thing, declared by its tag, inside a similarly-named wrapper.
            "<div class='tl-canvas' style='width:900px;height:600px'>"
            "<canvas width=880 height=580 style='display:block;width:880px;height:580px'></canvas>"
            "</div></body>")
        await dp2.wait_for_timeout(160)
        _cstr2 = await dp2.evaluate(
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(false,null,'compact',false,false,'flat'); })()")
        _craw2 = await dp2.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        check("CV4 a class merely containing the word 'canvas' is not announced as pixels",
              not any(e.get("canvasLike") and e.get("tag") != "canvas" for e in _craw2),
              f"non-canvas tags marked canvasLike="
              f"{[e.get('tag') for e in _craw2 if e.get('canvasLike') and e.get('tag') != 'canvas']}")
        check("CV4b ...while the real <canvas> inside it still is",
              "(canvas)" in _cstr2 and any(e.get("tag") == "canvas" for e in _craw2),
              f"marker={'(canvas)' in _cstr2} canvas entries="
              f"{sum(1 for e in _craw2 if e.get('tag') == 'canvas')}")
        await dp2.close()

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
        # add_init_script only affects documents created AFTER it, and set_content
        # reuses the existing about:blank — without this navigation listener_tag.js
        # never runs and everything below tests an untagged page. Pinned by C14.
        await tb.goto("about:blank")
        await tb.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<div id=wrap><p>Notes before.</p>"
            # The <caption> carries the UNIT here, exactly as Wikipedia's GDP table
            # captions itself "GDP forecast or estimate (million US$) by country".
            # Dropping it let an agent read `United States | 32,383,920` with nothing
            # anywhere saying millions — a 10^6 error with no signal, in the one view
            # built for reading numbers.
            "<table><caption>Revenue by region (thousands of JPY)</caption>"
            "<thead><tr><th>Region</th><th>Q1</th><th>Q2</th></tr></thead><tbody>"
            "<tr><td>North</td><td>1,240</td><td>1,600</td></tr>"
            "<tr><td>東京</td><td>2,300</td><td>2,450</td></tr>"
            "</tbody></table><p>Notes after.</p></div>"
            "<table id=solo><tr><td>x</td><td>y</td></tr><tr><td>z</td><td>w</td></tr></table>"
            "<table id=one><tr><td>lonely</td></tr></table>"
            # TB12's shape: a real multi-column data table whose FIRST row is a single
            # spanning header. `cs` is measured from that first row, so the old
            # >=2-columns rule scored this table as 1 column and left it out of the
            # hint, while the tree announced it on row count alone. Keep the spanning
            # first row: without it every table has >=2 columns and the check passes
            # whatever the rule says.
            "<table id=span1><tr><th colspan=3>Quarterly totals</th></tr>"
            "<tr><td>a</td><td>b</td><td>c</td></tr>"
            "<tr><td>d</td><td>e</td><td>f</td></tr></table>"
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
        # TB11: the <caption> is the table's declared title and often the only place
        # the UNIT appears. HTML says "the caption element represents the caption of
        # its parent table", so there is nothing to infer — it was simply not read.
        # TB12: THE HINT AND THE TREE MUST COUNT THE SAME TABLES. The hint required
        # >=2 columns while the tree prints a table node on >=2 rows alone, so one
        # response announced "6 data table(s)" and then listed SEVEN tables — the
        # missing one a genuine 62-row, 4-header data table. Two counts of the same
        # thing in one output, with nothing to say which is right. The fixture has a
        # two-column table (`#solo`) that the old column rule excluded.
        # `format` MUST BE PASSED: `_full` above uses five positionals, so it is the
        # FLAT listing and contains no tree table nodes at all. The first version of
        # this check read it and compared an empty set, passing either way — the same
        # trap RG10 fell into twice, and #29's measure_retention bug before that.
        _tree_full = await tb.evaluate(
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(false,null,'compact',false,false,'tree'); })()")
        _hint_refs = set(re.findall(r"ref_(\d+) \(\d+x\d+\)", _tnote))
        _tree_refs = set(re.findall(r"read with ref_(\d+)", _tree_full))
        check("TB12 every table the tree names is also in the data-table hint",
              _tree_refs.issubset(_hint_refs) or not _tree_refs,
              f"tree={sorted(_tree_refs)} hint={sorted(_hint_refs)}"
              + (f" MISSING FROM HINT={sorted(_tree_refs - _hint_refs)}"
                 if _tree_refs - _hint_refs else ""))

        check("TB11 the <caption> is rendered, so a figure's UNIT is not lost",
              "[caption] Revenue by region (thousands of JPY)" in w,
              next((l.strip() for l in w.splitlines() if "caption" in l.lower()),
                   "NO CAPTION LINE — every number reads as unitless"))
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

        # TB13: THE UNITS A PAGE PUTS OUTSIDE THE TABLE. <caption> is one way to say
        # what a table's numbers mean and it is already rendered (the Wikipedia
        # "million US$" case); ARIA's way is aria-labelledby/aria-describedby pointing
        # at a heading or a note elsewhere on the page. The Federal Reserve's H.15
        # does exactly that — the grid renders as clean aligned numbers while
        # "percent per annum" lives in a node beside it, so a scoped read handed an
        # agent 3.82 and 3.99 with nothing saying what either figure measured.
        # THE NOTE MUST SIT OUTSIDE THE <table> or it is rendered as a cell anyway and
        # this passes without exercising the association.
        tb2 = await browser.new_page(viewport={"width": 900, "height": 700})
        await tb2.set_content(
            "<!doctype html><meta charset=utf-8><body>"
            "<h2 id=t-title>Selected interest rates</h2>"
            "<p id=t-units>Yields in percent per annum</p>"
            "<table id=fedtab aria-labelledby=t-title aria-describedby=t-units>"
            "<tr><th>Instrument</th><th>Aug 18</th></tr>"
            "<tr><td>1-year T-bill</td><td>3.82</td></tr>"
            "<tr><td>1-year maturity</td><td>3.99</td></tr></table></body>")
        await tb2.wait_for_timeout(120)
        # SCOPED: the aligned-grid renderer runs for a scoped read (that is the view
        # built for reading numbers), so a whole-page read would not exercise it --
        # which is how the first version of this fixture failed for the wrong reason.
        _fm = await tb2.evaluate(
            "(function(){ " + COLLECT + "; _collectInteractivePage(true);"
            "return document.getElementById('fedtab').getAttribute('mmid'); })()")
        _tt = await tb2.evaluate("(function(){ " + DOMTEXT + "; return _domTextPage('"
                                 + str(_fm) + "'); })()")
        check("TB13 a table's declared units reach the grid that renders its numbers",
              "percent per annum" in _tt and "3.82" in _tt
              and "[described by]" in _tt,
              next((l.strip()[:80] for l in _tt.splitlines() if "described by" in l),
                   "NO ASSOCIATION RENDERED — 3.82 arrives with no unit"))
        check("TB13b ...and aria-labelledby titles it, distinctly from a description",
              "[titled by] Selected interest rates" in _tt,
              next((l.strip()[:70] for l in _tt.splitlines() if "titled by" in l), "ABSENT"))
        await tb2.close()

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
        # add_init_script only affects documents created AFTER it, and set_content
        # reuses the existing about:blank — without this navigation listener_tag.js
        # never runs and everything below tests an untagged page. Pinned by C14.
        await rg.goto("about:blank")
        await rg.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<header><a href=/h>Home</a></header>"
            "<main><p>top</p><div style='height:1400px'></div>"
            "<a href=/d1>Deep One</a><a href=/d2>Deep Two</a><button>Deep Btn</button></main>"
            # RG10's ingredients, both OUTSIDE <main>: a data table the tree used to
            # import into every scoped read, and an aria-hidden subtree whose count
            # is a whole-document number. Keep them out of <main> — inside it they
            # legitimately belong to the scope and the checks go vacuous.
            "<table><tr><th>Region</th><th>Q1</th></tr>"
            "<tr><td>North</td><td>1,240</td></tr><tr><td>South</td><td>980</td></tr></table>"
            "<div aria-hidden=true>"
            + "".join(f"<button style='width:80px;height:20px'>Ghost {i}</button>" for i in range(6))
            + "</div>"
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
        # RG10/RG11: two more page-level facts found leaking by live agents, both
        # under the header promising elements outside the scope are omitted.
        #  - the TREE imported every <table> in the document, because its guard was
        #    `(!scopeMmid || ent.size)` over a document-wide query — true for any
        #    scoped read that kept one entry. A read scoped to a single <input> came
        #    back listing eight of the page's data tables.
        #  - the aria-hidden NOTE is a count accumulated over the whole collection
        #    walk, so a read scoped to one <button> reported "312 interactive
        #    element(s) are NOT listed…".
        # Both tables and the aria-hidden subtree sit OUTSIDE <main> in the fixture,
        # so neither is legitimately in scope.
        # SCOPE TO A LEAF for the table check. Every live report was a read scoped to
        # a single <input> or <button>: with a leaf scope the out-of-scope table has
        # no kept ancestor inside the scope, so it becomes its own tree ROOT and
        # prints. Scoping to `main` leaves it unreachable from the emit walk and the
        # check passes without exercising anything — which is what it did first.
        _leaf = await rg.evaluate(
            "()=>{for (const b of document.querySelectorAll('button'))"
            " if ((b.textContent||'').includes('Deep Btn')) return b.getAttribute('mmid');"
            " return null;}")
        # `format` MUST BE PASSED. The other RG calls use five positionals, which
        # leaves `format` undefined — read as not-'tree' — so they exercise the FLAT
        # listing. The table node line is emitted only by the tree, so without this
        # the check cannot fail no matter what the collector does. Exactly the defect
        # #29 records in measure_retention, which called with three positionals and
        # silently measured the flat listing for every corpus figure this project
        # had ever published.
        sub_leaf = await rg.evaluate("(function(){ " + COLLECT
                                     + "; return _collectInteractivePage(false,'" + str(_leaf)
                                     + "','compact',false,false,'tree'); })()")
        check("RG10 a scoped read does not import tables from outside the scope",
              "rows, read with" not in sub_leaf and "data table(s)" not in sub_leaf,
              next((l.strip()[:90] for l in sub_leaf.splitlines()
                    if "rows, read with" in l or "data table(s)" in l), "clean"))
        check("RG11 ...nor the whole-document aria-hidden count",
              "aria-hidden" not in sub,
              next((l.strip()[:100] for l in sub.splitlines() if "aria-hidden" in l), "clean"))
        # The over-correction guard: unscoped, both facts must still be reported.
        # RG13/RG14: A SCOPED READ IS NOT VIEWPORT-LIMITED, so it must not claim to be.
        # The header kept the whole-page wording and counted rows it then flagged
        # (below-fold) in the same output — three live confirmations, one
        # self-contradicting inside a single response: `(17 on screen)` with 10 of
        # those 17 marked `(below-fold)`, and `(978 on screen)` for a 6082px section
        # in an 855px viewport. The cap notice leaked the same assumption, advising a
        # scroll that cannot change a scoped result.
        check("RG13 a scoped read does not claim its rows are 'on screen'",
              "on screen" not in sub and "in this subtree" in sub,
              next((l.strip()[:95] for l in sub.splitlines()
                    if "on screen" in l or "in this subtree" in l), "NO HEADER"))
        check("RG14 ...and the UNSCOPED read still says 'on screen', which is true of it",
              "on screen" in full,
              next((l.strip()[:70] for l in full.splitlines() if "on screen" in l), "MISSING"))

        check("RG12 ...while the UNSCOPED read still reports both",
              ("rows, read with" in full or "data table(s)" in full) and "aria-hidden" in full,
              f"table_hint={'rows, read with' in full or 'data table(s)' in full} "
              f"aria_hidden_note={'aria-hidden' in full}")
        # Unscoped reads must NOT start carrying the whole page: that variant was
        # measured at 1.51x-3.39x tokens for the same 96.0% recoverable and reverted.
        check("RG6 the UNSCOPED listing is still viewport-only",
              "Deep One" not in full and "Home" in full,
              f"{len([l for l in full.splitlines() if l.startswith('ref_')])} rows unscoped")
        await rg.close()

        # ---- N5: AccName's inter-child separator -------------------------------
        # Per AccName 1.2 step 2F each child's contribution is appended WITH A
        # SEPARATOR. We concatenated, and on a spaceless script the seam is invisible
        # and the result is a wrong NUMBER: Baidu's hot-search row is
        # <a><span>4</span><span>9秒39!…</span></a> -- rank 4, a 9.39-second record --
        # reported as "49秒39", i.e. 49.39 seconds. In English the seam shows and a
        # reader recovers; in Chinese it reads as one natural token.
        nm = await browser.new_page(viewport={"width": 900, "height": 700})
        await nm.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # add_init_script only affects documents created AFTER it, and set_content
        # reuses the existing about:blank — without this navigation listener_tag.js
        # never runs and everything below tests an untagged page. Pinned by C14.
        await nm.goto("about:blank")
        await nm.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<a href=/a id=cjk><span>4</span><span>9秒39！中国机器人</span></a>"
            "<button id=plain>Save</button>"
            "<label id=lw>Country <select id=sel><option>France</option></select></label>"
            "</body>")
        await nm.wait_for_timeout(140)
        _n = await nm.evaluate("(function(){ " + COLLECT
                               + "; return _collectInteractivePage(true,null,'compact',false,false); })()")
        _ids = await nm.evaluate(
            "()=>({cjk:document.getElementById('cjk').getAttribute('mmid'),"
            "plain:document.getElementById('plain').getAttribute('mmid'),"
            "sel:document.getElementById('sel').getAttribute('mmid')})")

        def _nm(k):
            e = next((x for x in _n if str(x.get("mmid")) == str(_ids[k])), None)
            return (e.get("name") or e.get("label") or e.get("text") or "") if e else ""

        check("N5 sibling element children are space-separated, not fused into one number",
              _nm("cjk").startswith("4 9秒39"), repr(_nm("cjk")))
        # Negative controls: a pure text node must not gain spaces, and the wrapping
        # label must still EXCLUDE the control's own subtree.
        check("N5b ...a single text node is untouched", _nm("plain") == "Save", repr(_nm("plain")))
        check("N5c ...and a wrapping label still excludes its control's subtree",
              _nm("sel") == "Country", repr(_nm("sel")))
        await nm.close()

        # ---- RG8/RG9: MANY containers sharing one tag ----------------------------
        # The shape that broke live and that no fixture modelled. Al Jazeera has 20
        # <footer> elements: bucketing by the LABEL `footer` counted 34 off-screen
        # links together while taking the ref from whichever element arrived first —
        # a 1-link card footer — so the hint promised `footer(ref_813): 34` and the
        # scoped read returned ONE row under a header saying everything outside the
        # scope is omitted. The real 33-link footer was never named.
        rg2 = await browser.new_page(viewport={"width": 900, "height": 600})
        await rg2.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # add_init_script only affects documents created AFTER it, and set_content
        # reuses the existing about:blank — without this navigation listener_tag.js
        # never runs and everything below tests an untagged page. Pinned by C14.
        await rg2.goto("about:blank")
        await rg2.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<header><a href=/h>Home</a></header>"
            "<div style='height:1200px'></div>"
            # A decoy card footer with one link, FIRST in document order.
            "<footer id=card><a href=/card>Card note</a></footer>"
            # The real site footer, later, with many.
            "<footer id=site>" + "".join(f"<a href=/f{i}>Foot {i}</a>" for i in range(9)) + "</footer>"
            "</body>")
        await rg2.wait_for_timeout(140)
        f2 = await rg2.evaluate("(function(){ " + COLLECT
                                + "; return _collectInteractivePage(false,null,'compact',false,false); })()")
        n2 = next((l for l in f2.splitlines() if l.startswith("[")), "")
        ids = await rg2.evaluate(
            "()=>({card:document.getElementById('card').getAttribute('mmid'),"
            "site:document.getElementById('site').getAttribute('mmid')})")
        # Each container is its own bucket, so the 9-link footer is named with a
        # count of 9 — not merged with the decoy under one label.
        check("RG8 many containers sharing a tag are separate buckets, each with its own ref",
              f"footer(ref_{ids['site']}): 9" in n2,
              n2[:150])
        sub2 = await rg2.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false,'"
                                  + str(ids["site"]) + "','compact',false,false); })()")
        check("RG9 ...and scoping to the named ref returns that container's links",
              sub2.count("Foot ") >= 9 and "Card note" not in sub2,
              f"{sub2.count('Foot ')} Foot rows, decoy present={'Card note' in sub2}")
        await rg2.close()

        # RG15: THE CAP NOTICE MUST NOT TELL A SCOPED CALLER TO SCOPE. It said
        # "Prefer narrowing — read_page(ref_id=…) on a smaller region" to every
        # capped read, including one that had ALREADY passed ref_id — an instruction
        # that restates the parameter just used and names nothing to narrow TO, since
        # region hints are page-level and correctly suppressed under a scope (RG7).
        # The scoped caller does have something available: the refs printed above it.
        # NEEDS >150 ENTRIES INSIDE THE SCOPE or the cap never engages and the check
        # passes over an output that has no notice at all.
        cp = await browser.new_page(viewport={"width": 900, "height": 4000})
        await cp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # add_init_script only affects documents created AFTER it, and set_content
        # reuses the existing about:blank — without this navigation listener_tag.js
        # never runs and everything below tests an untagged page. Pinned by C14.
        await cp.goto("about:blank")
        await cp.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'><main id=m>"
            + "".join(f'<a href=/x{i} style="display:block;width:200px;height:18px">'
                      f'Row {i}</a>' for i in range(200))
            + "</main></body>")
        await cp.wait_for_timeout(200)
        _mid = await cp.evaluate(
            "(function(){ " + COLLECT + "; _collectInteractivePage(true);"
            "return document.getElementById('m').getAttribute('mmid'); })()")
        _cap = await cp.evaluate("(function(){ " + COLLECT
                                 + "; return _collectInteractivePage(false,'" + str(_mid)
                                 + "','compact',false,false,'tree'); })()")
        check("RG15 a capped SCOPED read points at the rows it printed, not at the"
              " ref_id parameter the caller already passed",
              "counts ENTRIES" in _cap and "Narrow FURTHER" in _cap
              and "on a smaller region" not in _cap,
              next((l.strip()[:150] for l in _cap.splitlines()
                    if "counts ENTRIES" in l), "NO CAP NOTICE — cap did not engage"))
        await cp.close()

        # ---- MH: the Main heading is chosen by DECLARED RANK --------------------
        # "Main heading" is the cheapest what-am-I-looking-at signal in the listing,
        # and it took the FIRST visible heading in DOM order. Rank is not document
        # order: HTML declares it with h1..h6 and ARIA declares it with aria-level,
        # so reading position instead of rank ignores what the page states.
        #
        # Measured live on Wikipedia: the Vector-2022 skin emits the table-of-contents
        # heading BEFORE the article's own <h1>, so the line reported the furniture
        # instead of the subject of the page — the single fact it exists to give.
        # THE h2 MUST COME FIRST IN THE DOM or this passes without exercising
        # anything, which is the vacuous-fixture shape that has bitten five checks
        # this session.
        mh = await browser.new_page(viewport={"width": 900, "height": 700})
        await mh.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # add_init_script only affects documents created AFTER it, and set_content
        # reuses the existing about:blank — without this navigation listener_tag.js
        # never runs and everything below tests an untagged page. Pinned by C14.
        await mh.goto("about:blank")
        await mh.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<nav><h2 style='font-size:16px'>Contents</h2>"
            "<a href=#s1>Section one</a></nav>"
            "<main><h1 style='font-size:28px'>Economy of Japan</h1>"
            "<p>Body text.</p></main></body>")
        await mh.wait_for_timeout(120)
        _mhl = await mh.evaluate("(function(){ " + COLLECT
                                 + "; return _collectInteractivePage(false,null,'compact',"
                                   "false,false,'tree'); })()")
        _mhline = next((l for l in _mhl.splitlines() if l.startswith("Main heading")), "ABSENT")
        check("MH1 the Main heading is the DECLARED top-rank heading, not the first"
              " one in DOM order",
              "Economy of Japan" in _mhline, _mhline[:90])
        # MH2: aria-level is the other half of the same declaration, and it must beat
        # the tag. A <h2 aria-level=1> outranks a plain <h2> that precedes it; without
        # this the rule would just be "prefer h1", which is a tag preference rather
        # than a rank read.
        await mh.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<nav><h2 style='font-size:16px'>Site navigation</h2></nav>"
            "<div role=heading aria-level=1 style='font-size:28px'>Quarterly results</div>"
            "<a href=/x>A link</a></body>")
        await mh.wait_for_timeout(120)
        _mhl2 = await mh.evaluate("(function(){ " + COLLECT
                                  + "; return _collectInteractivePage(false,null,'compact',"
                                    "false,false,'tree'); })()")
        _mhline2 = next((l for l in _mhl2.splitlines() if l.startswith("Main heading")), "ABSENT")
        check("MH2 ...and aria-level declares rank too, outranking an earlier <h2>",
              "Quarterly results" in _mhline2, _mhline2[:90])

        # MH3: THE CONSENT-BANNER CASE. Both headings are <h2>, so rank ties and the
        # old tie-break was document order -- and a consent overlay is injected at
        # the TOP of the document. Live on gov.uk: `Main heading: "Cookies on
        # GOV.UK"` while the page's actual subject sat one line below it in the same
        # call's outline. This is the single line an agent reads to decide whether it
        # is even on the right page, and on any site with a banner it named the
        # overlay. <main> is HTML's own declaration of the dominant content.
        await mh.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<div role=region aria-label='Cookie banner'>"
            "<h2 style='font-size:20px'>Cookies on GOV.UK</h2>"
            "<button>Accept</button></div>"
            "<main><h2 style='font-size:28px'>UK bank holidays</h2>"
            "<p>Body text.</p></main></body>")
        await mh.wait_for_timeout(120)
        _mhl3 = await mh.evaluate("(function(){ " + COLLECT
                                  + "; return _collectInteractivePage(false,null,'compact',"
                                    "false,false,'tree'); })()")
        _mhline3 = next((l for l in _mhl3.splitlines() if l.startswith("Main heading")), "ABSENT")
        check("MH3 a rank TIE is broken by <main>, so a consent banner injected at the "
              "top of the document does not become the page's heading",
              "UK bank holidays" in _mhline3 and "Cookies" not in _mhline3, _mhline3[:100])

        # MH3b THE CONTROL: rank still wins ACROSS the landmark boundary. Without it
        # MH3 would also pass over a rule that simply preferred anything inside
        # <main>, which would be a landmark preference rather than a tie-break and
        # would lose a real <h1> that sits outside one.
        await mh.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<header><h1 style='font-size:28px'>The Daily Chronicle</h1></header>"
            "<main><h2 style='font-size:20px'>Today's weather</h2>"
            "<p>Body text.</p></main></body>")
        await mh.wait_for_timeout(120)
        _mhl4 = await mh.evaluate("(function(){ " + COLLECT
                                  + "; return _collectInteractivePage(false,null,'compact',"
                                    "false,false,'tree'); })()")
        _mhline4 = next((l for l in _mhl4.splitlines() if l.startswith("Main heading")), "ABSENT")
        check("MH3b CONTROL: a declared h1 OUTSIDE <main> still outranks an h2 inside "
              "it — the landmark breaks ties, it does not override rank",
              "Daily Chronicle" in _mhline4, _mhline4[:100])
        await mh.close()

        await browser.close()

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} generality checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
