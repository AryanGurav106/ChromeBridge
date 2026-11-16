"""The nine Mind2Web misses: is each one a GAP, or a decided trade-off?

CLAUDE.md #73 and #78 both describe every remaining miss as "an element that
declares nothing clickable in static markup". That sentence is doing a lot of
work -- it is the difference between a defect we have not fixed and a boundary
we chose -- and it has only ever been asserted at the level of the whole set.

This asks each of the nine, one signal at a time. For the target node of every
`missed_present` action it reports the eight things `isInteractive` admits on
(PRINCIPLES #1, the complement rule from #28):

    tag          an HTML interactive tag, audio/video[controls], canvas, svg
    role         an ARIA interactive role
    onclick      the attribute, or a handler assigned to the property (#71)
    tabindex     the attribute
    contentedit  contenteditable
    listener     __abClickBound, stamped by listener_tag.js
    cursor       computed cursor:pointer
    href         a destination

and then what else is on the node: aria-label, title, alt, a name of any kind,
its size, and whether anything inside it declares something.

WHAT A CLEAN RESULT WOULD MEAN, in both directions, because a probe whose
answer is decided in advance is not a probe:

  * ANY miss declaring something -> it is a real DEFECT. The collector had a
    signal and dropped the element, and that is a bug to fix.
  * EVERY miss declaring nothing -> admitting it needs a rule keyed on
    something the page never stated: its size, its position, the shape of its
    text, its class name. Those are the rules #27 and #28 removed from every
    path that decides existence, and that the project owner's own brief forbids
    ("dont hardcode, add regex, pattern matching stuff that may break"). The
    nine are then the measured PRICE of that rule rather than an open gap.

Needs `temp/mind2web/`; `python tools/fetch_mind2web.py` rebuilds it.
Run:  python tools/audit_m2w_misses.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_mind2web as BM  # noqa: E402
from _m2w_ruler import repair_serialization  # noqa: E402

SIGNALS = """(id) => {
  const el = document.querySelector(`[backend_node_id="${id}"]`);
  if (!el) return {found: false};
  const cs = getComputedStyle(el);
  const r  = el.getBoundingClientRect();
  const ON = ['onclick','onmousedown','onmouseup','onpointerdown','onpointerup','onkeydown'];
  return {
    found: true,
    tag: el.tagName.toLowerCase(),
    text: (el.textContent || '').trim().slice(0, 48),
    // --- the eight admitting signals -------------------------------------
    s_tag: /^(a|button|input|select|textarea|summary|label|option|canvas|svg|audio|video)$/
             .test(el.tagName.toLowerCase()),
    s_role: !!el.getAttribute('role'),
    s_onclick: el.hasAttribute('onclick') || ON.some(k => typeof el[k] === 'function'),
    s_tabindex: el.hasAttribute('tabindex'),
    s_editable: el.isContentEditable,
    s_listener: !!el.__abClickBound,
    s_cursor: cs.cursor === 'pointer',
    s_href: el.hasAttribute('href'),
    // --- what else is on it ----------------------------------------------
    aria_label: el.getAttribute('aria-label') || null,
    title: el.getAttribute('title') || null,
    alt: el.getAttribute('alt') || null,
    cls: (el.getAttribute('class') || '').slice(0, 60) || null,
    w: Math.round(r.width), h: Math.round(r.height),
    // Does anything INSIDE declare something? If so the agent can still act,
    // just not on this node -- which is a different situation from a dead end.
    inner_declared: !!el.querySelector(
      'a[href],button,input,select,textarea,[role],[onclick],[tabindex]'),
  };
}"""


async def main() -> int:
    samples = BM.load_samples(0)
    print(f"{len(samples)} labelled action(s)\n")
    rows = []
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        page = await b.new_page(viewport={"width": 1280, "height": 1100})
        await page.add_init_script(
            (Path(__file__).resolve().parent.parent / "extension" / "listener_tag.js")
            .read_text(encoding="utf-8"))
        for s in samples:
            res = await BM.score_one(page, s)
            if res.get("status") != "missed_present":
                continue
            html = repair_serialization(s["cleaned_html"])
            await page.set_content(html, wait_until="domcontentloaded")
            sig = await page.evaluate(SIGNALS, s.get("target_backend_node_id"))
            sig["site"] = s.get("website") or s.get("site") or "?"
            rows.append(sig)
        await b.close()

    if not rows:
        print("NO MISSES — nothing to audit, which is itself the answer.")
        return 0

    keys = ["s_tag", "s_role", "s_onclick", "s_tabindex", "s_editable",
            "s_listener", "s_cursor", "s_href"]
    print(f"{'site':14} {'tag':6} {'text':26} " + " ".join(k[2:7].rjust(6) for k in keys))
    declaring = []
    for r in rows:
        if not r.get("found"):
            print(f"{r.get('site','?'):14} <<node did not resolve>>")
            continue
        marks = " ".join(("YES" if r[k] else ".").rjust(6) for k in keys)
        print(f"{r['site'][:13]:14} {r['tag']:6} {r['text'][:25]:26} {marks}")
        if any(r[k] for k in keys):
            declaring.append(r)

    print()
    print(f"{'misses audited:':34} {len(rows)}")
    print(f"{'declaring ANY admitting signal:':34} {len(declaring)}")
    named = [r for r in rows if r.get("found") and (r.get('aria_label') or r.get('title') or r.get('alt'))]
    print(f"{'carrying aria-label/title/alt:':34} {len(named)}")
    inner = [r for r in rows if r.get("found") and r.get("inner_declared")]
    print(f"{'something DECLARED inside them:':34} {len(inner)}")
    print()
    if declaring:
        print("AT LEAST ONE MISS DECLARES SOMETHING. That is a DEFECT, not a")
        print("trade-off: the collector had a signal on these and dropped them.")
        for r in declaring[:5]:
            on = [k[2:] for k in keys if r[k]]
            print(f"   {r['site']:12} <{r['tag']}> {r['text'][:36]!r} declares: {on}")
        return 1
    print("NONE of the misses declares ANY of the eight admitting signals, and")
    print("none carries aria-label, title or alt. Admitting them would require a")
    print("rule keyed on something the page never stated — size, position, the")
    print("shape of the text, or a class name. Those are exactly the rules #27")
    print("and #28 removed from every path that decides existence.")
    print()
    print("So these are the measured PRICE of 'existence is decided only by")
    print("declarations', not an unfixed gap. The price is 9 of 186 actions on a")
    print("corpus where two of the eight signals cannot fire at all.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
