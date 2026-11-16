"""M-B: does the listing survive the same control being BUILT DIFFERENTLY?

This is the generality claim stated as a measurement. WebPageBench re-renders a
task through a different implementation of ONE control -- a date picker that is
a native input in one arm and a popup in another, a text field that is filled /
outlined / pill / underlined, a guest counter that is pill buttons or an inline
stepper -- while the prompt and the success conditions stay byte-identical. 75
such pairs across 8 control keys.

WHY BYTE-INVARIANCE IS THE WRONG TEST HERE, and is the right one for the theme.
A colour change must not move the listing at all (`measure_wpb_invariance.py`,
12/12 at 0). A genuine widget swap SHOULD move it: different markup is different
markup. The question is not whether the listing changed but whether it still
describes something an agent can act on.

THE METRIC, chosen so it needs no gold element and no per-widget vocabulary.
Per-widget expectations ("a date swap should yield a row matching /date|calendar/")
would be exactly the hardcoded pattern matching this project removes from every
path that decides something -- and it would be English, on a Russian site.
Instead, three counts the formatter already produces:

  rows        actionable entries in the listing
  named       entries carrying a resolved identity (a quoted accessible name)
  unlabeled   entries our own formatter marked `(unlabeled)` -- a real control
              with no resolvable name, which is the shape a representation
              produces when it can SEE a widget and cannot DESCRIBE it

A generality failure is then one of two things, both declarative:
  * `named` COLLAPSES in the variant arm -- the affordance left the listing, so
    an agent can no longer reach it;
  * `unlabeled` RISES -- the control survived and its identity did not, which is
    the half-failure that a presence metric would score as a pass.

Neither is a threshold on a chosen number: both are compared against the
canonical arm of the SAME task, and the floor is measured by re-rendering the
canonical arm (`measure_wpb_invariance.py` measured that floor at 0 on these
pages, which is why one re-render per key is enough here).

Needs the site up; see `measure_wpb_invariance.py` for how.
Run:  python tools/measure_wpb_variants.py --repo <path-to-WebPageBench>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_wpb_invariance import (  # noqa: E402
    HOST, TAG, COLLECT, build_track_config, create_track, _norm,
)

_ROW = re.compile(r"^\s*(?:ref_|mmid=)")
_QUOTED = re.compile(r'"[^"]+"')
# The listing states its own aria-hidden drop count. That number is the
# difference between "the representation lost this control" and "the page
# declared the rest of itself absent because a modal opened", and without it the
# first version of this probe reported a false generality failure -- see `score`.
_HIDDEN = re.compile(r"(\d+) interactive element\(s\) are NOT listed because an "
                     r"ancestor is aria-hidden")


def score(listing: str) -> dict:
    """Count affordances, AND the page's own declared aria-hidden drop.

    WHY `hidden` IS HERE, and it is the whole correction this probe needed.
    The first version compared `named` alone and reported `hotels_date_inline`
    at -7 as a generality failure. It is not one. That variant renders an OPEN
    inline calendar, and an open overlay marks the rest of the document
    `aria-hidden="true"` -- measured, 829 hidden elements in the variant against
    55 in the canonical. The 7 rows it "lost" are blog links the PAGE declared
    absent from the accessibility tree, which the collector drops on purpose
    (#23) and reports the count of.

    So a drop in `named` is only evidence of a representation failure when it is
    NOT accompanied by a rise in the page's own hidden count. That test is
    declarative -- it reads a number the page caused and the listing printed --
    rather than a judgement about which drops are acceptable.
    """
    rows = named = unlabeled = 0
    hidden = 0
    for line in (listing or "").splitlines():
        m = _HIDDEN.search(line)
        if m:
            hidden = int(m.group(1))
        if line.startswith("***") or not _ROW.match(line):
            continue
        rows += 1
        if "(unlabeled" in line:
            unlabeled += 1
        if _QUOTED.search(line) or 'name="' in line:
            named += 1
    return {"rows": rows, "named": named, "unlabeled": unlabeled, "hidden": hidden}


async def listing_for(browser, track_id: str) -> str:
    pg = await browser.new_page(viewport={"width": 1280, "height": 900})
    await pg.add_init_script(TAG)
    try:
        await pg.goto(f"{HOST}/{track_id}", wait_until="networkidle", timeout=30000)
        await pg.wait_for_timeout(2500)
        return await pg.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(false); })()")
    finally:
        await pg.close()


def pairs_for(repo: Path):
    tasks = repo / "tests" / "bench" / "tasks"
    out = []
    for v in sorted(tasks.glob("*__*.json")):
        d = json.loads(v.read_text(encoding="utf-8"))["test_data"]
        uv = d.get("ui_variants") or {}
        if not uv or "theme" in uv:
            continue                      # theme is the invariance probe's job
        canon = tasks / (v.name.split("__")[0] + ".json")
        if not canon.is_file():
            continue
        c = json.loads(canon.read_text(encoding="utf-8"))["test_data"]
        # The pair is only usable if the two really are the same task.
        if c.get("task") != d.get("task") or c.get("conditions") != d.get("conditions"):
            continue
        out.append((canon, v, d.get("ui_variant_profile") or v.stem, uv))
    return out


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    repo = Path(a.repo).resolve()

    pairs = pairs_for(repo)
    if a.limit:
        pairs = pairs[: a.limit]
    print(f"{len(pairs)} usable control-swap pair(s), task and conditions identical on all\n")

    per_key = defaultdict(list)
    failures, seen_canon = [], {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for canon, var, prof, uv in pairs:
            key = ",".join(sorted(uv))
            cid, vid = f"mb_c_{canon.stem[:22]}", f"mb_v_{var.stem[:22]}"
            ok = await create_track(None, cid, build_track_config(repo, canon))
            ok = ok and await create_track(None, vid, build_track_config(repo, var))
            if not ok:
                failures.append((prof, "track create failed")); continue
            # The canonical arm is rendered once per canonical task and reused:
            # the invariance probe measured the same-arm floor at 0 on these
            # pages, so a second render would cost time and tell us nothing.
            if cid not in seen_canon:
                raw = await listing_for(browser, cid)
                seen_canon[cid] = (score(raw), _norm(raw))
            cs, cnorm = seen_canon[cid]
            raw_v = await listing_for(browser, vid)
            vs = score(raw_v)
            # AN INERT VARIANT PROVES NOTHING, and this benchmark has them.
            # Measured: `text_search_outlined` renders a listing IDENTICAL to its
            # canonical twin, because outlined IS the component's default -- so
            # that pair passes whatever the representation does. Counting it as
            # evidence of generality would be counting a check that cannot fail,
            # which is the defect `record_flow(stop)` warns about one feature
            # over. They are separated out and reported, not silently included.
            inert = _norm(raw_v) == cnorm
            per_key[key].append((prof, cs, vs, inert))
        await browser.close()

    print(f"{'control key':18} {'n':>3} {'rows c->v':>14} {'named c->v':>14} "
          f"{'unlabeled c->v':>16} {'inert':>6}")
    worst_named, worst_unlab, total = None, None, 0
    inert_total, explained = {}, []
    for key in sorted(per_key):
        items = per_key[key]
        total += len(items)
        cr = statistics.median(i[1]["rows"] for i in items)
        vr = statistics.median(i[2]["rows"] for i in items)
        cn = statistics.median(i[1]["named"] for i in items)
        vn = statistics.median(i[2]["named"] for i in items)
        cu = sum(i[1]["unlabeled"] for i in items)
        vu = sum(i[2]["unlabeled"] for i in items)
        n_inert = sum(1 for i in items if i[3])
        print(f"{key:18} {len(items):>3} {int(cr):>6} -> {int(vr):<5} "
              f"{int(cn):>6} -> {int(vn):<5} {cu:>7} -> {vu:<6} {n_inert:>6}")
        inert_total[key] = n_inert
        for prof, cs, vs, _ in items:
            dn = vs["named"] - cs["named"]
            du = vs["unlabeled"] - cs["unlabeled"]
            # EXPLAINED BY THE PAGE, not by us: a named drop that comes with a
            # rise in the page's own aria-hidden count is the overlay rule
            # working, not an affordance lost.
            if dn < 0 and vs["hidden"] > cs["hidden"]:
                explained.append((prof, dn, cs["hidden"], vs["hidden"]))
                continue
            if worst_named is None or dn < worst_named[1]:
                worst_named = (prof, dn)
            if worst_unlab is None or du > worst_unlab[1]:
                worst_unlab = (prof, du)

    print()
    if failures:
        print(f"{len(failures)} pair(s) could not be measured: {failures[:3]}")
    ti = sum(inert_total.values())
    print(f"measured {total} pair(s) across {len(per_key)} control key(s); "
          f"{ti} INERT (listing identical to canonical -- the variant is the "
          f"component's own default, so those pairs could not have failed)")
    print(f"pairs that actually vary the markup: {total - ti}")
    if explained:
        print(f"{len(explained)} named drop(s) EXPLAINED by the page's own "
              f"aria-hidden count rising (an overlay opened):")
        for prof, dn, ch, vh in explained[:4]:
            print(f"    {prof:44} named {dn:+d}, page-hidden {ch} -> {vh}")
    if worst_named:
        print(f"worst NAMED delta (variant - canonical): {worst_named[1]:+d}  ({worst_named[0]})")
    if worst_unlab:
        print(f"worst UNLABELED delta:                   {worst_unlab[1]:+d}  ({worst_unlab[0]})")
    print()
    # REPORTS, DOES NOT JUDGE. An earlier version printed a pass/fail verdict and
    # got it WRONG TWICE on this very data: it called `hotels_date_inline` a
    # generality failure when the page had opened an overlay and declared 829
    # elements aria-hidden, and it called `rail_date_native` one when a custom
    # two-element date widget had been replaced by a single native `input[date]`
    # -- the same affordance in fewer rows, carrying MORE information
    # (`format=YYYY-MM-DD`). Both needed a human to read the diff.
    #
    # A count cannot tell "the affordance left" from "the page has fewer
    # elements for it", so this prints the numbers and the explanations and
    # leaves the call to the reader. #33's rule: state the fact, name the
    # candidate causes, never assert one the tool has not verified.
    print("WHAT THIS DOES AND DOES NOT SAY. Every number above is a COUNT, and a")
    print("count cannot distinguish an affordance that left the listing from one")
    print("the variant renders with fewer elements. A named delta is a prompt to")
    print("read that pair's diff, not a verdict. Drops already explained by the")
    print("page's own aria-hidden count are separated out above; anything left is")
    print("unexplained and should be diffed by hand before it is believed.")
    print()
    print("Scope: the control keys this benchmark varies, on 6 synthetic")
    print("Russian-language apps. Not a statement about the web.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
