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
