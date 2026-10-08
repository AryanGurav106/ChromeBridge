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


async def listing(page, html, detail="brief", nofold=False, fmt="flat"):
    """The D-series tests the FLAT fold, so it asks for flat EXPLICITLY.

    These checks predate the tree and describe the cross-parent shape fold that only
    the flat listing does — `12x a, same structure` grouped by shape regardless of
    where the members sit. That mechanism still exists and is still reachable, and
    the tests are the right tests for it.

    What they must not do is get it BY OMISSION. The collector's default is now the
    product's default (tree), because a parameter whose omission silently changes the
    output and cannot fail is a trap: it is why #29's corpus token figures all
    described a format the product had stopped shipping, and why RG10 and TB12 passed
    against empty sets this session. Stating the format is the whole point.
    """
    await page.set_content(html, wait_until="domcontentloaded")
    await page.wait_for_timeout(120)
    if nofold:
        await page.evaluate("()=>{window.__abNoFold=true;}")
    return await page.evaluate(
        "(function(){ " + COLLECT + "; return _collectInteractivePage(false, null, '"
        + detail + "', false, false, '" + fmt + "'); })()")


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
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(false, null, 'brief', false, false, 'flat'); })()")
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
        # TR19: THE TREE MUST FOLD AT THE TOP LEVEL TOO. `emit` walks <body>/<html>
        # without printing a row for them — they are on every page and say nothing —
        # and it did that with a direct `emit(child)` loop, which skips
        # `_emitChildren` and therefore skips ALL grouping. The pass-through was
        # written to suppress a ROW, not to suppress folding, so twelve identical
        # links directly under <body> printed as twelve rows while the same twelve
        # inside a <div>, a <ul> or a <main> folded into one. Measured across all
        # four containers: only the bare-body case failed.
        _tf = await listing(page, PAGE_FOLD, fmt="tree")
        check("TR19 a repeated group directly under <body> folds in the tree, like"
              " the same group inside any container",
              "12×" in _tf,
              f"{len([l for l in _tf.splitlines() if 'identical siblings' in l])} fold(s),"
              f" {len(_tf)} chars")

        # TR20: ONE MEMBER SPLIT OUT OF A SEQUENCE — the arXiv citation shape, where a
        # fold of reference links ran [1]..[12] and silently omitted [8]. It was not
        # omitted: it carried one extra class, so it grouped separately and printed as
        # its own row, and the fold's "in document order" header invited reading the
        # remaining eleven as the complete run. The interleave marker covers it, and
        # the interesting part is the boundary — exactly ONE element inside the span,
        # the smallest count that must still fire.
        _cs = "".join(
            f'<a class="c{" hi" if i == 8 else ""}" href=/r{i}'
            f' style="display:block;width:60px;height:18px">[{i}]</a>' for i in range(12))
        _cpg = await browser.new_page(viewport={"width": 900, "height": 900})
        await _cpg.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # add_init_script only affects documents created AFTER it, and set_content
        # reuses the existing about:blank — without this navigation listener_tag.js
        # never runs and everything below tests an untagged page. Pinned by C14.
        await _cpg.goto("about:blank")
        await _cpg.set_content("<!doctype html><meta charset=utf-8>"
                               f"<body style='margin:0'><div>{_cs}</div></body>")
        await _cpg.wait_for_timeout(150)
        _cl = await _cpg.evaluate(
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(false,null,'compact',false,false,'flat'); })()")
        _cf = [l for l in _cl.splitlines() if "same structure" in l]
        check("TR20 a sequence with one member split out says so — the fold no longer"
              " reads as the complete run",
              len(_cf) == 1 and "INTERLEAVED with 1 other a" in _cf[0],
              (_cf[0][:110] if _cf else "NO FOLD"))
        check("TR20b ...and the split-out member is still present and actionable",
              '"[8]"' in _cl, next((l[:70] for l in _cl.splitlines() if "[8]" in l),
                                   "MEMBER LOST"))
        await _cpg.close()

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
        # FLAT, EXPLICITLY: D8/D8b are about the flat listing's cross-parent shape
        # fold — the mechanism that once put Hacker News' story titles, domains and
        # comment links in one bucket. Omitting the format used to give flat by
        # accident; it now gives the product default, so the format has to be named.
        hout = await hp.evaluate("(function(){ " + COLLECT
                                 + "; return _collectInteractivePage(false, null, 'compact',"
                                 + " false, false, 'flat'); })()")
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
        # add_init_script only affects documents created AFTER it, and set_content
        # reuses the existing about:blank — without this navigation listener_tag.js
        # never runs and everything below tests an untagged page. Pinned by C14.
        await cp.goto("about:blank")
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
        # add_init_script only affects documents created AFTER it, and set_content
        # reuses the existing about:blank — without this navigation listener_tag.js
        # never runs and everything below tests an untagged page. Pinned by C14.
        await wp.goto("about:blank")
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
        # add_init_script only affects documents created AFTER it, and set_content
        # reuses the existing about:blank — without this navigation listener_tag.js
        # never runs and everything below tests an untagged page. Pinned by C14.
        await rp.goto("about:blank")
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
        # TR15/TR16: TWO FOLDS ARE NOT TWO COLUMNS OF ONE TABLE. Each group's "in
        # document order" is true of that group, and printing two invites reading
        # position N of one against position N of the other. Measured live on Hacker
        # News: a 17-member group of comment counts printed ABOVE a 16-member group
        # of story titles, both claiming document order, and zipping them paired
        # every title with the PREVIOUS story's count — "The Art and Beauty of Blade
        # Runner" against 50 comments when its real count was 21, all 16 pairs
        # shifted by one, with nothing stating the mismatch. #27 cited this as a
        # reason the tree beats a flat list and left it unsaid in the output.
        # BOTH RUNS MUST EXCEED THE FOLD THRESHOLD (6 members): at 6 and 5 the
        # smaller run prints as loose rows, only one group exists, and the check
        # passes without exercising anything — which is what two earlier drafts did.
        fp2 = await browser.new_page(viewport={"width": 900, "height": 900})
        await fp2.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        # THE TWO RUNS MUST INTERLEAVE, which is the real shape and the dangerous one.
        # Two folds with DISJOINT ref spans are separate regions and counting inside
        # one is fine; the wrong-answer case is one ordered sequence cut into pieces
        # whose members alternate. Measured on Wikipedia's ranked GDP column: a
        # 10-member and an 88-member fold, both headed "in document order", where
        # position 5 gives Spain (15th) or Russia (9th) instead of the UK. An earlier
        # draft of this fixture put all titles then all counts -- disjoint spans, so
        # the marker correctly did not fire and the check tested nothing.
        _rows = "".join(
            f'<li><a class=t href=/s{i} style="display:block;width:300px;height:20px">'
            f'Story {i}</a></li>'
            + (f'<li><a class=c href=/c{i} style="display:block;width:120px;height:18px">'
               f'{10 * i} comments</a></li>' if i < 7 else "")
            for i in range(8))
        await fp2.set_content("<!doctype html><meta charset=utf-8><body style='margin:0'>"
                              f"<ul>{_rows}</ul></body>")
        await fp2.wait_for_timeout(150)
        _ft = await fp2.evaluate(
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(false,null,'compact',false,false,'tree'); })()")
        _groups = [l for l in _ft.splitlines() if "identical siblings" in l]
        check("TR15 two folded groups of UNEQUAL length are both emitted",
              len(_groups) == 2,
              f"{len(_groups)} group(s): {[g.strip()[:24] for g in _groups]}")
        # The marker must sit ON the fold header, not in a legend: it is true of the
        # folds that interleave and false of folds that do not, so it cannot be a
        # blanket statement. TR16b is the negative control -- without it, a marker
        # printed on every fold would pass TR16 while telling agents to distrust
        # perfectly countable groups.
        _marked = [l for l in _ft.splitlines()
                   if "identical siblings" in l and "INTERLEAVED with" in l]
        check("TR16 an interleaved fold says so ON ITS HEADER, and that position is"
              " not page order",
              len(_marked) == len(_groups) and all("position is not rank" in l for l in _marked),
              f"{len(_marked)} of {len(_groups)} group(s) marked: "
              + (_marked[0].strip()[:100] if _marked
                 else "NO MARKER — an agent counting positions here gets the wrong rank"))
        # TR18: THE SAME WARNING IN THE FLAT LISTING, where it matters MORE. Flat
        # folds group ACROSS parents, so interleaving is the norm there rather than
        # the exception — and every flat fold header said "in document order"
        # unconditionally until now, while the tree had said it since #27. Same page,
        # same instant, only `format` differs, so this cannot pass for a reason other
        # than the format.
        _ff = await fp2.evaluate(
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(false,null,'compact',false,false,'flat'); })()")
        _fgroups = [l for l in _ff.splitlines() if "same structure" in l]
        _fmarked = [l for l in _fgroups if "INTERLEAVED with" in l]
        check("TR18 an interleaved fold in the FLAT listing says so on its header too",
              len(_fgroups) == 2 and len(_fmarked) == 2
              and all("position is not rank" in l for l in _fmarked),
              f"{len(_fmarked)} of {len(_fgroups)} marked: "
              + (_fmarked[0][:96] if _fmarked
                 else "NO MARKER — pairing these two folds by position shifts every pair"))
        # TR18b: the negative control, and the reason the test is keyed on SAME KIND.
        # `folded` is D1's listing: twelve contiguous <a> with nothing between them,
        # so position IS rank and a marker would be false. A warning printed on every
        # fold would satisfy TR18 while training agents to distrust countable groups
        # — the #15 lesson about always-on warnings.
        check("TR18b ...and a contiguous fold is NOT marked",
              "12×" in folded and "INTERLEAVED" not in folded,
              next((l[:80] for l in folded.splitlines() if "12×" in l), "no fold found"))
        await fp2.close()

        # TR17: A GROUP THAT DOES NOT FOLD MUST NOT BE HOISTED. Sibling grouping
        # pools members by shape wherever they sit, and a pooled group can only be
        # PRINTED in one place — so it is emitted at its FIRST member's position.
        # For a group that folds that is sound (one line, every member's ref on it,
        # and `_ordPhrase` says so when the spans interleave). For a group BELOW the
        # fold threshold it is not: the members print as ordinary rows, in a place
        # the page does not put them, with no header and therefore no marker.
        #
        # Measured live on ant.design's own select demo: three options where the
        # chosen one carries an extra state class, so `shapeOf` — which includes the
        # full class list — split them into runs of 2 and 1, and the tree printed
        # Jack, yiminghe, Lucy for a document reading Jack, Lucy, yiminghe. The
        # SELECTED option was the displaced one, which is the worst member to move.
        #
        # Asserted as the general property, not the antd shape: refs are assigned in
        # document order, so when nothing folds the printed refs must ascend. (With a
        # fold present they legitimately do not — that is TR15/TR16's case, and it is
        # marked.) FIVE members with ONE odd class keeps both runs under the
        # threshold of 6, which is what makes this the silent path rather than TR16's.
        fp3 = await browser.new_page(viewport={"width": 900, "height": 900})
        await fp3.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        _opts = "".join(
            f'<a class="o{" sel" if i == 1 else ""}" href=/o{i}'
            f' style="display:block;width:200px;height:22px">Opt {i}</a>'
            for i in range(5))
        await fp3.set_content("<!doctype html><meta charset=utf-8><body style='margin:0'>"
                              f"<nav>{_opts}</nav></body>")
        await fp3.wait_for_timeout(150)
        _ot = await fp3.evaluate(
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(false,null,'compact',false,false,'tree'); })()")
        _folded = [l for l in _ot.splitlines() if "identical siblings" in l]
        _refs = [int(m) for m in re.findall(r"\bref_(\d+)\b", _ot)]
        _labs = re.findall(r'"(Opt \d)"', _ot)
        check("TR17 with no fold, printed rows ascend by ref — a group below the fold"
              " threshold is not hoisted to its first member's position",
              not _folded and _refs == sorted(_refs) and len(_labs) == 5
              and _labs == sorted(_labs),
              (f"{len(_folded)} fold(s); refs {_refs}; order {_labs}"
               if _folded or _refs != sorted(_refs) or _labs != sorted(_labs)
               else f"ascending: {_labs}"))
        await fp3.close()

        # TR10e: THE OTHER SIDE OF THE SAME RULE, and a false negative I caused with
        # it. react-select's control is a div with TWO element children, only ONE of
        # which carries text — so its name is that one thing's name restated, not a
        # summary of unrelated things. Flagged as a borrowed subtree name, `find`
        # dropped the label and demoqa's City field became unreachable by search
        # while read_page listed it as `div "Select City" (disabled)`: #27's
        # most-reported false negative, reappearing through my own fix for the
        # whole-page-label defect. Reproduced live before this check was written.
        # KEEP THE SECOND CHILD EMPTY — with text in it there are two contributors,
        # which is TR10's case, and this check would pass for the wrong reason.
        await rp.evaluate(
            "()=>{const w=document.createElement('div');"
            "w.id='rsctl'; w.setAttribute('onclick','void 0');"
            "w.style.cssText='width:300px;height:38px';"
            "w.innerHTML='<div style=\"width:200px;height:20px\">Select City</div>"
            "<div style=\"width:20px;height:20px\"></div>';"
            "document.body.appendChild(w);}")
        await rp.wait_for_timeout(80)
        _rs = await rp.evaluate(
            "(function(){ " + COLLECT
            + "; return _collectInteractivePage(true,null,'compact',false,false,'tree'); })()")
        _rsm = await rp.evaluate("()=>document.getElementById('rsctl').getAttribute('mmid')")
        _rse = next((e for e in _rs if str(e.get("mmid")) == str(_rsm)), None)
        check("TR10e a container whose label comes from ONE child keeps it — nothing"
              " was concatenated, so it is still that control's identity",
              _rse is not None
              and "Select City" in ((_rse.get("label") or "") + (_rse.get("name") or ""))
              and not _rse.get("subtreeName"),
              f"label={(_rse or {}).get('label')!r} "
              f"subtreeName={(_rse or {}).get('subtreeName')}")

        check("TR10d ...while its children and their labels all survive",
              all(any(f'"{t}"' in l for l in r_tree.splitlines())
                  for t in ("Widgets", "Alerts", "Read more")),
              "children present" if all(any(f'"{t}"' in l for l in r_tree.splitlines())
                                        for t in ("Widgets", "Alerts", "Read more"))
              else "A CHILD LABEL WAS LOST WITH THE CONTAINER'S")
        await rp.close()

        # TR8d USED TO ASSERT len == 2, which encoded the implementation rather than
        # the invariant: at the time neither row could collapse, because the rule
        # required BOTH ends to be plain wrappers and one end here is an <a>. The
        # collapse now runs in the other direction too, so the <a> absorbs the
        # wrapper and one row remains. The invariant it exists to protect is
        # unchanged and is what is asserted now -- a declared control is the
        # SURVIVOR, keeping its tag, its own name and its own ref. The defect it
        # caught was the <a>'s name being deleted because a child wrapper repeated
        # it, leaving `ref_7 | a`; that is still a failure here.
        _link = [l for l in c_tree.splitlines() if '"Real Link"' in l]
        _realm = await cp.evaluate("()=>document.getElementById('real').getAttribute('mmid')")
        _wrapm = await cp.evaluate("()=>document.getElementById('rk').getAttribute('mmid')")
        _lr = _link[0].strip() if _link else ""
        check("TR8d a declared control (<a>) keeps its own name and ref — it is the"
              " survivor, never merged INTO its child wrapper",
              len(_link) == 1 and _lr.split("|")[1].strip().startswith("a ")
              and f"ref_{_realm}" in _lr,
              f"{len(_link)} row(s): {[l.strip()[:60] for l in _link]}")
        # And the wrapper's ref rides along rather than becoming unreachable, in
        # document order with the outermost first -- the legend's own promise.
        check("TR8d2 ...and the absorbed wrapper is still actionable, outermost first",
              f"ref_{_wrapm}" in _lr
              and _lr.index(f"ref_{_realm}") < _lr.index(f"ref_{_wrapm}"),
              f"a=ref_{_realm} wrapper=ref_{_wrapm} row={_lr[:60]!r}")
        await cp.close()

        # ---- FF1-FF3: THE TWO FOLD RENDERERS MUST AGREE.
        #
        # There were two hand-maintained member-flag lists, one per format, and they
        # had drifted in BOTH directions: the TREE (the default since #27) dropped
        # `(read-only)` and `(post-key)`, while FLAT dropped `(just appeared)`.
        # CLAUDE.md #40 and #41 each close by stating their new notation survives
        # folding, each pinned by a fixture -- and W28g and NP5 exercise the FLAT fold
        # only, so both claims were false in the format agents actually get.
        # Reproduced live: a readonly input holding "locked" printed as `7:"b"` in the
        # tree, byte-identical to the writable field beside it.
        #
        # SEVEN members, because the fold threshold is 6 and my first version of this
        # fixture had five -- nothing folded, and the check passed vacuously (#21: a
        # detector that cannot fire is worth nothing).
        fp = await browser.new_page(viewport={"width": 1280, "height": 1600})
        await fp.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        STATEFUL = ('<!doctype html><meta charset=utf-8><body><form>'
                    '<div><input type="text" name="a" pattern="[0-9]{5}" disabled></div>'
                    '<div><input type="text" name="b" readonly value="locked"></div>'
                    '<div><input type="text" name="c" maxlength="4" required></div>'
                    '<div><input type="text" name="d"></div>'
                    '<div><input type="text" name="e" maxlength="9"></div>'
                    '<div><input type="text" name="f" maxlength="8"></div>'
                    '<div><input type="text" name="g" maxlength="7"></div>'
                    '</form></body>')
        # A SEPARATE PAGE PER FORMAT, because both must be a FIRST read. Reading the
        # same page twice made the second carry `(just appeared)` on every member
        # (#31's novelty flag, which seeds on the first unscoped read) and restarted
        # the comparison at different mmids -- so the first version of FF2 failed on
        # my fixture rather than on the code.
        flat = await listing(fp, STATEFUL, fmt="flat")
        fp2 = await browser.new_page(viewport={"width": 1280, "height": 1600})
        await fp2.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        tree = await listing(fp2, STATEFUL, fmt="tree")

        def fold_members(txt):
            """The member run of the fold line, which is what both formats share."""
            for ln in txt.splitlines():
                if "\u00d7 input" in ln and "via its ref" in ln:
                    return ln.split("via its ref):", 1)[-1].strip()
            return ""

        mf, mt = fold_members(flat), fold_members(tree)
        check("FF1 both formats actually fold these seven inputs",
              bool(mf) and bool(mt), f"flat={mf[:50]!r} tree={mt[:50]!r}")
        # The invariant, and the reason this is one check rather than one per
        # notation: a NEW flag cannot reach one format and miss the other.
        check("FF2 ...and their fold MEMBER TOKENS are byte-identical",
              mf == mt, f"flat={mf[:110]!r}\n            tree={mt[:110]!r}")
        # FF3 is the control that FF2 is not satisfied by both formats printing
        # nothing: the state must really be present. read-only and post-key are the
        # two that were actually missing from the tree.
        check("FF3 ...and the states that were dropped are present in BOTH",
              all(t in mf and t in mt for t in ("(read-only)", "(post-key)",
                                                "(disabled)", "(required)")),
              f"tree={mt[:140]!r}")
        await fp.close(); await fp2.close()

        await browser.close()

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} folding checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
