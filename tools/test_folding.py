"""Repeated-record folding — compression that must not cost actionability.

WHY THIS EXISTS
---------------
Measured on 35 frozen sites before this feature: 46% of pages exceeded the
150-entry listing cap, the median capped page silently lost 124 elements, and
**96% of a median listing sat in a structurally repeated group** — 20 product
cards, 50 search results, a nav column. Full price was being paid per row for
near-identical rows, and the tail was then dropped.

Folding is a SERIALIZATION change only. The structured array is returned before
this pass runs, which is what `find` and every audit consume — so compression
cannot silently shrink the search space.

Matched A/B on the same 30 sites, detail="brief":
    folding OFF  211,942 chars   answerability 0.761
    folding ON   174,184 chars   answerability 0.759
    => -17.8% tokens for -0.002 answerability, and out-of-sample recall
       unchanged at 93.6% (Mind2Web, 47 labelled targets).

THE INVARIANTS THAT MAKE IT SAFE
--------------------------------
Compression is only acceptable if every folded row stays actionable and
answerable. If a card collapses into a group line, its ref must still be there
and its href must still be there — otherwise we would trade tokens for recall,
which is the one trade this project must never make.

Run:  python tools/test_folding.py
"""

import asyncio
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract as _shared_extract  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = _shared_extract("_collectInteractivePage", BG, verify=True)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))


def cards(n, start=1):
    return "".join(
        f'<a href="/item/{i}" style="display:block;width:300px;height:40px">Product number {i}</a>'
        for i in range(start, start + n))


PAGE_FOLD = f'<!doctype html><meta charset=utf-8><body style="margin:0">{cards(12)}</body>'
PAGE_SMALL = f'<!doctype html><meta charset=utf-8><body style="margin:0">{cards(4)}</body>'


async def listing(page, html, detail="brief", nofold=False):
    await page.set_content(html, wait_until="domcontentloaded")
    await page.wait_for_timeout(120)
    if nofold:
        await page.evaluate("()=>{window.__abNoFold=true;}")
    return await page.evaluate(
        "(function(){ " + COLLECT + "; return _collectInteractivePage(false, null, '" + detail + "'); })()")


async def structured(page, html, detail="brief"):
    await page.set_content(html, wait_until="domcontentloaded")
    await page.wait_for_timeout(120)
    return await page.evaluate(
        "(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, '" + detail + "'); })()")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 900, "height": 900})
        await page.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))

        # ORDER MATTERS: `window.__abNoFold` survives a later set_content, so a
        # nofold run poisons every subsequent listing on this page — which made
        # the "folded" output unfolded and D3 fail against a real, working fold.
        # Everything that needs folding ON runs first; the disabling run is last.
        folded = await listing(page, PAGE_FOLD)

        check("D1 a repeated group of 12 folds into a group line",
              "12×" in folded, folded.splitlines()[-1][:90])

        # THE LOAD-BEARING ONES: compression must not cost actionability.
        # SAME page load for both passes. Calling set_content again restarts the
        # page and the additive mmid counter keeps climbing, so refs from a second
        # load never match the first — comparing across loads tested nothing.
        await page.set_content(PAGE_FOLD, wait_until="domcontentloaded")
        await page.wait_for_timeout(120)
        st = await page.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, 'brief'); })()")
        folded = await page.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false, null, 'brief'); })()")
        mmids = [str(e["mmid"]) for e in st if (e.get("href") or "").find("/item/") >= 0]
        missing = [m for m in mmids if not re.search(rf"\b{m}:", folded)]
        check("D3 every folded row keeps its own ref", not missing,
              f"{len(mmids)} rows, {len(missing)} refs lost: {missing[:5]}")
        hrefs_missing = [i for i in range(1, 13) if f"/item/{i}" not in folded]
        check("D4 every folded row keeps its href (answerability preserved)",
              not hrefs_missing, f"missing /item/: {hrefs_missing}")
        labels_missing = [i for i in range(1, 13) if f"Product number {i}" not in folded]
        check("D5 every folded row keeps its label", not labels_missing,
              f"missing labels: {labels_missing}")

        check("D6 the STRUCTURED array is never folded (find's search space intact)",
              len([e for e in st if (e.get("href") or "").startswith("/item/")]) == 12,
              f"{len(st)} structured entries")

        small = await listing(page, PAGE_SMALL)
        check("D7 a group below the threshold is NOT folded",
              "4×" not in small and "Product number 1" in small,
              small.splitlines()[-1][:80])

        # D2 last, and on a FRESH page: the nofold flag is sticky for the life of
        # the JS context, so it must not run before anything that needs folding.
        page2 = await browser.new_page(viewport={"width": 900, "height": 900})
        await page2.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        plain = await listing(page2, PAGE_FOLD, nofold=True)
        check("D2 folding actually saves tokens", len(folded) < len(plain),
              f"{len(folded)} vs {len(plain)} chars ({(len(folded)-len(plain))/len(plain):+.0%})")

        # ---- D8: a fold's shared description must be true of ALL its members -----
        # The shape signature is tag/role/section/href/size and knows nothing about what
        # the labels SAY. On Hacker News that put a story TITLE, site domains, timestamps
        # and comment links in ONE bucket because they all render at ~98x16px — and a
        # reader gets only the group's shared description, so a front-page story vanished
        # into a metadata pile. Reported by an agent doing a real task ("find the
        # highest-scoring story") that the fold structurally prevented.
        # MODELLED ON REAL HACKER NEWS MARKUP, because the class-less version of
        # this fixture was an abstraction the site does not match, and it drove the
        # wrong fix. HN gives its three link types three different classes
        # (span.pagetop>a, span.titleline>a, span.subline>a.hnuser); an earlier
        # class-less fixture could only be separated by a sibling ordinal, and that
        # ordinal then shattered arXiv's 276 identically-classed author links by
        # author position. Class is what discriminates on the real page.
        hp = await browser.new_page(viewport={"width": 1200, "height": 900})
        _rows = "".join(
            f"<div style='height:20px'>"
            f"<span class=titleline><a href=/s{i} style='display:inline-block;width:98px'>Qwen 3.8 27B v{i}</a></span>"
            f"<span class=sitebit><a href=/d{i} style='display:inline-block;width:98px'>huggingface{i}.co</a></span>"
            f"<span class=subline><a href=/t{i} style='display:inline-block;width:98px'>{i+2} hours ago</a></span></div>"
            for i in range(10))
        await hp.set_content(f"<!DOCTYPE html><meta charset=utf-8><body style='margin:0'>{_rows}</body>")
        await hp.wait_for_timeout(140)
        hout = await hp.evaluate("(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()")
        # MATCH THE ROW'S SHAPE, NOT ITS PROSE. This selected on the literal
        # phrase "same shape", so renaming the group header to "same structure"
        # (when the fold key moved from pixel size to tag path) emptied this list
        # — and D8, a NEGATIVE check that no fold mixes kinds, then passed
        # vacuously on zero folds while D8b was the only thing that noticed.
        # `N× ` is the fold row's actual signature and survives wording changes.
        _folds = [l for l in hout.splitlines() if re.match(r"^\d+×\s", l)]
        _mixed = [l for l in _folds if "huggingface" in l and "hours ago" in l]
        check("D8 a fold never mixes domains with timestamps (heterogeneous labels)",
              not _mixed, f"{len(_mixed)} mixed fold(s): {(_mixed or [''])[0][:90]}")
        check("D8b ...while like-with-like still folds, so compression is preserved",
              any("Qwen" in l for l in _folds), f"{len(_folds)} fold(s) emitted")
        await hp.close()

        # ---- TR: the tree format, which needs no classification at all ----------
        # The fold SIGNATURE was rewritten four times in one day -- pixel buckets,
        # tag path, tag path + sibling ordinal, tag path + class -- because "are
        # these the same kind of thing?" has no heuristic answer. The tree does not
        # ask it: siblings whose subtree shapes are BYTE-IDENTICAL are the same kind
        # by construction, and their contents line up by position.
        tp = await browser.new_page(viewport={"width": 1200, "height": 1400})
        await tp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        hn = "".join(
            f"<tr><td><span class=titleline><a href=/s{i}>Story {i}</a></span> "
            f"<span class=sitebit><a href=/d{i}>site{i}.com</a></span></td></tr>"
            f"<tr><td class=subtext><a href=/u{i}>user{i}</a> "
            f"<a href=/c{i}>{i} comments</a></td></tr>" for i in range(6))
        arx = "".join(
            f"<div class=meta><div class=list-authors><a href=/a1>Author {i}A</a>, "
            f"<a href=/a2>Author {i}B</a>, <a href=/a3>Author {i}C</a></div></div>"
            for i in range(8))
        await tp.set_content("<!doctype html><meta charset=utf-8><body style='margin:0'>"
                             f"<main><table>{hn}</table><section>{arx}</section></main></body>")
        await tp.wait_for_timeout(170)

        async def coll(fmt):
            arg = "false,null,'compact',false,false" + (",'tree'" if fmt else "")
            return await tp.evaluate("(function(){ " + COLLECT
                                     + "; return _collectInteractivePage(" + arg + "); })()")

        t_flat, t_tree = await coll(None), await coll("tree")
        check("TR1 the tree indents rows under the page's own structure",
              "\n main" in ("\n" + t_tree) or t_tree.count("\n table") >= 1,
              next((l for l in t_tree.splitlines() if l.strip() == "main"), "NO main NODE"))
        # Hacker News' user and comments links are same-class siblings, so the flat
        # key groups them and the heterogeneity guard then refuses -- 12 loose rows.
        # Positionally they are two distinct columns, which is what they are.
        _pos = [l for l in t_tree.splitlines() if l.strip().startswith("#")]
        check("TR2 identical sibling records collapse POSITIONALLY, one line per field",
              any('"user0"' in l and '"user5"' in l for l in _pos)
              and any('"0 comments"' in l and '"5 comments"' in l for l in _pos),
              f"{len(_pos)} position lines")
        check("TR3 ...and no position line mixes two different fields",
              not any(('"user0"' in l and '"0 comments"' in l) for l in _pos))
        # The flat fold put all 24 arXiv authors in ONE line, losing which paper
        # each belonged to. Positions keep first/second/third author apart.
        check("TR4 a 3-field record keeps its fields in separate positions",
              sum(1 for l in _pos if "Author" in l) == 3,
              f"{sum(1 for l in _pos if 'Author' in l)} author position lines")
        check("TR5 every folded member keeps its own ref",
              all(f'"Author {i}A"' in t_tree for i in range(8)))
        # Pass-through wrappers must not each buy an indent level: that was 80% of
        # the tree's cost before pruning (36,576 of 45,868 chars on one real page).
        deep = max((len(l) - len(l.lstrip(" ")) for l in t_tree.splitlines()), default=0)
        check("TR6 pass-through wrappers are pruned, so indentation stays shallow",
              deep <= 8, f"deepest indent {deep} spaces")
        check("TR7 the tree is not more expensive than the flat listing here",
              len(t_tree) <= len(t_flat),
              f"tree {len(t_tree)} vs flat {len(t_flat)} chars")
        # The document declares a <table>; a <tbody> is often inserted by the
        # PARSER and names an implementation detail. The pruning pass used to
        # remove the table it had just decided to keep and let the tbody stand in
        # for it — invisible until the tree started being built from a post-prune
        # parent map.
        check("TR9 a declared <table> survives pruning; the parser's <tbody> does not"
              " stand in for it",
              any(l.strip().startswith("table ") for l in t_tree.splitlines())
              and not any(l.strip() == "tbody" for l in t_tree.splitlines()),
              next((l for l in t_tree.splitlines()
                    if l.strip().startswith("table ") or l.strip() == "tbody"), "NEITHER"))
        await tp.close()

        # TR8: once the container heuristics stopped deleting (#28), one nav item
        # printed as a chain of same-label wrappers. They must still EXIST — one of
        # them carries the handler — but a row whose every printed field repeats the
        # row above is not information. The <a> is the negative control: a declared
        # control never merges into its child, because there the tag IS the fact.
        cp = await browser.new_page(viewport={"width": 900, "height": 700})
        await cp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await cp.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'><div id=nav>"
            "<span id=a onclick='void 0' style='display:block;width:200px;height:30px'>"
            "<div id=b onclick='void 0' style='width:200px;height:30px'>"
            "<div id=c onclick='void 0' style='width:200px;height:30px'>Elements</div>"
            "</div></span>"
            "<a id=real href=#x style='display:block;width:200px;height:30px'>"
            "<div id=rk onclick='void 0' style='width:200px;height:30px'>Real Link</div>"
            "</a></div></body>")
        await cp.wait_for_timeout(150)
        c_tree = await cp.evaluate(
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(false,null,'compact',false,false,'tree'); })()")
        c_arr = await cp.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        _rows = [l for l in c_tree.splitlines() if "Elements" in l and l.strip().startswith("ref_")]
        _ids = await cp.evaluate(
            "()=>['a','b','c'].map(i=>document.getElementById(i).getAttribute('mmid'))")
        check("TR8 identical nested rows share ONE row carrying every ref",
              len(_rows) == 1 and all(f"ref_{m}" in _rows[0] for m in _ids),
              f"{len(_rows)} row(s) mmids={_ids} -> {(_rows or ['NONE'])[0].strip()[:90]}")
        check("TR8b ...in document order, outermost first",
              bool(_rows) and [_rows[0].index("ref_" + m) for m in _ids]
              == sorted(_rows[0].index("ref_" + m) for m in _ids),
              f"positions={[(m, (_rows or [''])[0].find('ref_' + m)) for m in _ids]}")
        check("TR8c ...and every folded ref is still in the structured array",
              all(any(str(e.get("mmid")) == str(m) for e in c_arr) for m in _ids),
              f"present={[any(str(e.get('mmid')) == str(m) for e in c_arr) for m in _ids]}")
        # Quoted, so the fold row's near="Elements Real Link" does not count — a
        # bare substring match made this assert 3 rows and read as a failure of the
        # code rather than of the test.
        # TR11: NO INDENT LEVEL IS SKIPPED. A bare div/span/li wrapper prints no
        # line (#27 dropped the word to save characters) but kept incrementing
        # depth, so every descendant row paid a space for a row that is not there —
        # seen live on svelte.dev as ref_69 at indent 2 with its own child at indent
        # 5. Indentation under an invisible parent is also unreadable: there is no
        # row at the shallower level to group under, so it reads as a gap. TR6 only
        # bounds the maximum depth, which a skipped level passes.
        wp = await browser.new_page(viewport={"width": 900, "height": 700})
        await wp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await wp.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'><main>"
            # TWO bare wrappers as SIBLINGS, each branching. Both conditions are
            # needed for one to survive pruning while printing nothing: >=2 kept
            # children of its own, AND a kept ancestor with >=2 kept children --
            # otherwise the second pruning clause splices it out. A single nested
            # chain passes this check VACUOUSLY, verified by re-introducing the
            # defect and watching the check still pass.
            "<div><a href=#a style='display:block;width:120px;height:22px'>One</a>"
            "<a href=#b style='display:block;width:120px;height:22px'>Two</a></div>"
            "<div><a href=#c style='display:block;width:120px;height:22px'>Three</a>"
            "<a href=#d style='display:block;width:120px;height:22px'>Four</a></div>"
            "</main></body>")
        await wp.wait_for_timeout(150)
        w_tree = await wp.evaluate(
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(false,null,'compact',false,false,'tree'); })()")
        _rows = [l for l in w_tree.split("scroll_to by ref, or screenshot to look at pixels).\n")[-1]
                 .splitlines() if l.strip()]
        _depths = [len(l) - len(l.lstrip(" ")) for l in _rows]
        _seen, _gap = set(), None
        for d in _depths:
            if d > 0 and (d - 1) not in _seen:
                _gap = d
                break
            _seen.add(d)
        check("TR11 no row is indented under a level that printed nothing",
              _gap is None,
              f"depths={_depths} first orphaned depth={_gap}"
              + (f"  rows={[l[:44] for l in _rows]}" if _gap is not None else ""))
        await wp.close()

        # TR12/TR13: THE LISTING MUST NOT NAME NOTATION IT DOES NOT PRINT. #27
        # strips ` section=` from tree rows because the enclosing node is one line
        # above — but the modal banner and the section legend were both written for
        # the flat listing and kept telling the agent about `section=dialog`. In the
        # DEFAULT format that token then appeared only inside the legend sentence
        # describing it, so the single instruction an agent gets when a modal is
        # open pointed at a marker no row carried. #13 established the rule (a
        # legend line is gated on its notation appearing); #27 changed the default
        # format underneath it and both sites went stale.
        dp = await browser.new_page(viewport={"width": 1000, "height": 700})
        await dp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        _dlg = ("<!doctype html><meta charset=utf-8><body style='margin:0'>"
                "<button style='width:120px;height:30px'>Page Button</button>"
                "<div role=dialog aria-modal=true style='width:400px;height:200px'>"
                "<h2>Delete this item?</h2>"
                "<button style='width:110px;height:28px'>Keep</button>"
                "<button style='width:110px;height:28px'>Delete</button></div></body>")
        await dp.set_content(_dlg)
        await dp.wait_for_timeout(150)

        async def _fmt(f):
            return await dp.evaluate(
                "(function(){ " + COLLECT + "; return _collectInteractivePage("
                "false, null, 'compact', false, false, '" + f + "'); })()")

        _tree, _flat = await _fmt("tree"), await _fmt("flat")
        _rows_t = [l for l in _tree.splitlines() if l.strip().startswith("ref_")]
        check("TR12 the tree names no notation it strips — no `section=` anywhere,"
              " banner and legend included",
              "section=" not in _tree and bool(_rows_t),
              f"section= present={'section=' in _tree} rows={len(_rows_t)}"
              + (f"  offending={[l.strip()[:70] for l in _tree.splitlines() if 'section=' in l][:2]}"
                 if "section=" in _tree else ""))
        check("TR13 ...while the flat listing, which does print it, still explains it"
              " — the fix is format-aware, not a deletion",
              "section=dialog" in _flat
              and any("section=dialog" in l for l in _flat.splitlines()
                      if l.strip().startswith("ref_")),
              f"in_legend_or_banner={'section=' in _flat} "
              f"on_a_row={any('section=dialog' in l for l in _flat.splitlines() if l.strip().startswith('ref_'))}")
        # And the tree must still SAY a modal is open, by pointing at the nesting.
        # TR14 asserts the banner names a marker that is REALLY IN THE ROWS. Its
        # first version checked for "[dialog]" and passed — because the fixture's
        # own listing happened to contain that substring elsewhere — while the
        # dialog row prints `role=dialog`. A live agent searched the output for
        # `[dialog]`, found nothing, and concluded the dialog had not been listed.
        # So the check now takes the marker OUT of the banner text and requires it
        # to appear on an actual row: that is the property, and it cannot be
        # satisfied by the banner talking about itself.
        # The general property, because a literal check is what went wrong twice.
        # The tree renders a dialog TWO ways — as an entry (`… role=dialog`) when it
        # earned a ref, or as a structural node (`div[dialog]`) when it did not —
        # so any literal the banner quotes is absent on half of all pages. The
        # invariant is therefore: every `key=value` or `[token]` literal the banner
        # quotes must appear somewhere in the ROWS. That catches "[dialog]" on an
        # entry-style page and "role=dialog" on a node-style page, which is exactly
        # the pair of mistakes made here.
        import re as _re
        _banner = next((l for l in _tree.splitlines()
                        if "MODAL/DIALOG IS CURRENTLY OPEN" in l), "")
        _rowtext = "\n".join(l for l in _tree.splitlines()
                             if "MODAL/DIALOG" not in l and not l.startswith("  - "))
        _quoted = _re.findall(r"\[[a-z-]+\]|\b[a-z_]+=[a-z-]+", _banner)
        _absent = [q for q in _quoted if q not in _rowtext]
        _identified = ("role=dialog" in _rowtext) or ("[dialog]" in _rowtext)
        check("TR14 ...and every literal the modal banner quotes appears in the ROWS"
              " (the tree renders a dialog two ways, so no single literal is safe)",
              bool(_banner) and not _absent and _identified
              and any(l.startswith(" ") and "Keep" in l for l in _tree.splitlines()),
              f"banner={bool(_banner)} quoted={_quoted} absent_from_rows={_absent} "
              f"dialog_identified={_identified} "
              f"indented_child={any(l.startswith(' ') and 'Keep' in l for l in _tree.splitlines())}")
        await dp.close()

        # TR10: an element's accessible name falls back to its descendants' text
        # concatenated, so a page shell reads as the whole page — demoqa's outermost
        # div arrived as a 390-char first row naming every nav item, heading, field
        # and the copyright line, every word of which was on its own row beneath it.
        # A flat list needed that string; a tree states it by nesting. Dropped only
        # when the descendants account for ALL of it (exact, no threshold), and
        # never for a declared control, whose name is its identity not a summary.
        rp = await browser.new_page(viewport={"width": 900, "height": 700})
        await rp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        await rp.set_content(
            "<!doctype html><meta charset=utf-8><body style='margin:0'>"
            "<div id=shell onclick='void 0' style='width:400px'>"
            "<a href=#a style='display:block;width:200px;height:24px'>Elements</a>"
            "<a href=#b style='display:block;width:200px;height:24px'>Forms</a></div>"
            "<div id=card onclick='void 0' style='width:400px'>"
            "A quarterly summary of regional performance."
            "<a href=#d style='display:block;width:200px;height:24px'>Read more</a>"
            "</div>"
            # TR10c's shape: the shell above has NO text but its own children's, so
            # the old subtraction rule caught it. This one adds ONE non-interactive
            # text node in a NESTED div — a copyright line, the commonest thing on
            # the web — which no child entry accounts for, so the subtraction never
            # came out empty and the whole concatenation printed. That is what made
            # Dzen emit two ~4,000-char rows (evicting real rows from a 12,000-char
            # budget) and demoqa a 390-char first row. Keep the copyright NESTED:
            # as a direct text node it would be the container's own prose, which is
            # TR10b's case and must be kept.
            "<div id=shell2 onclick='void 0' style='width:400px'>"
            "<a href=#e style='display:block;width:200px;height:24px'>Widgets</a>"
            "<a href=#f style='display:block;width:200px;height:24px'>Alerts</a>"
            "<div>&copy; 2013-2026 EXAMPLE.COM | ALL RIGHTS RESERVED.</div>"
            "</div></body>")
        await rp.wait_for_timeout(150)
        r_tree = await rp.evaluate(
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(false,null,'compact',false,false,'tree'); })()")
        _shell = [l for l in r_tree.splitlines()
                  if l.startswith("ref_") and " div" in l and "Elements" in l]
        check("TR10 a container whose label is only its descendants' labels prints"
              " without it",
              not _shell,
              f"shell row still carries the concatenation: {(_shell or ['none'])[0][:80]}")
        check("TR10b ...while a container with prose of its own keeps its label",
              any("A quarterly summary" in l for l in r_tree.splitlines()),
              next((l.strip()[:70] for l in r_tree.splitlines()
                    if "quarterly" in l), "LABEL LOST"))
        # TR10c: ONE non-interactive text node in the subtree used to defeat the
        # rollup entirely, because the subtraction only removed kept descendant
        # ENTRIES' labels and a text node has no entry. The container's own DIRECT
        # text is the test that separates this from TR10b — both are identical under
        # subtraction, which is why subtraction could not decide between them.
        _shell2 = [l for l in r_tree.splitlines()
                   if l.strip().startswith("ref_") and " div" in l and "Widgets" in l]
        check("TR10c ...and one non-interactive text node in the subtree no longer"
              " defeats the rollup (the whole-page-label defect)",
              not _shell2,
              f"shell row still carries the concatenation: {(_shell2 or ['none'])[0].strip()[:90]}")
        check("TR10d ...while its children and their labels all survive",
              all(any(f'"{t}"' in l for l in r_tree.splitlines())
                  for t in ("Widgets", "Alerts", "Read more")),
              "children present" if all(any(f'"{t}"' in l for l in r_tree.splitlines())
                                        for t in ("Widgets", "Alerts", "Read more"))
              else "A CHILD LABEL WAS LOST WITH THE CONTAINER'S")
        await rp.close()

        _link = [l for l in c_tree.splitlines() if '"Real Link"' in l]
        check("TR8d a declared control (<a>) is NEVER merged into its child wrapper",
              len(_link) == 2,
              f"{len(_link)} row(s): {[l.strip()[:60] for l in _link]}")
        await cp.close()

        await browser.close()

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} folding checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
