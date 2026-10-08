"""Does ChromeBridge MISS controls that browser-use would admit?

The question has never been measured. Every accuracy number in this project
compares ChromeBridge to the Chrome AX tree or to MindAct's cleaned_html; nobody
has run browser-use's OWN admission rule over the same pages.

METHOD
  For each frozen site, on ONE page load:
    OURS   = every element our real collector returns (structured=True, so the
             whole page, offscreen retained -- this is the set `find` can reach)
    THEIRS = every element browser-use's ClickableElementDetector.is_interactive
             would admit, ported to JS from browser_use/dom/serializer/
             clickable_elements.py, run over the same document.

  Reports THEIRS-minus-OURS (candidate misses) and OURS-minus-THEIRS, and — the
  part that decides the answer — WHICH of their rules admitted each element we
  miss. If their extra recall is the search wordlist and the 10-50px icon rule,
  it is noise. If it is `focusable` or a real ARIA role, it is a gap.

LIMITS, stated because they change how the number reads:
  - Their AX-property checks (focusable/editable/settable/...) read Chrome's
    accessibility tree via CDP. A page-context port approximates them with the
    matching ARIA attributes plus native focusability. That makes THEIRS a
    slight UNDER-estimate on that branch and an over-estimate on none.
  - Admission only. Their bbox-containment and paint-order passes DELETE after
    admission and are not modelled, so THEIRS is their upper bound.
  - Viewport scoping is excluded on both sides on purpose: this isolates "would
    it exist at all" from "is it on screen", which is a separate decision.
"""

import argparse
import asyncio
import collections
import json
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(r"C:/Users/Aryan Gurav/Desktop/ChromeBridge")
sys.path.insert(0, str(ROOT / "tools"))
from _extract import extract as _extract_fn  # noqa: E402

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = _extract_fn("_collectInteractivePage", BG, verify=True)
FROZEN = ROOT / "temp" / "frozen"
TAG_JS = str(ROOT / "extension" / "listener_tag.js")
VIEWPORT = {"width": 1280, "height": 1600}

# browser-use's is_interactive, ported. Rule names match their source comments so a
# disagreement can be attributed to the exact branch that caused it.
THEIRS_JS = r"""
(function () {
  const INTERACTIVE_TAGS = new Set(['button','input','select','textarea','a','details','summary','option','optgroup']);
  const INTERACTIVE_ROLES = new Set(['button','link','menuitem','option','radio','checkbox','tab','textbox',
    'combobox','slider','spinbutton','search','searchbox','row','cell','gridcell']);
  const SEARCH_WORDS = ['search','magnify','glass','lookup','find','query','searchbox','search-icon','search-btn','search-button'];
  const EVENT_ATTRS = ['onclick','onmousedown','onmouseup','onkeydown','onkeyup','tabindex'];

  const hasFormControlDescendant = (el, depth) => {
    if (depth <= 0) return false;
    for (const c of el.children) {
      const t = c.tagName.toLowerCase();
      if (t === 'input' || t === 'select' || t === 'textarea') return true;
      if (hasFormControlDescendant(c, depth - 1)) return true;
    }
    return false;
  };

  const verdict = (el) => {
    const tag = el.tagName.toLowerCase();
    if (tag === 'html' || tag === 'body') return null;
    // 2. CDP-detected JS click listener. listener_tag.js gives both sides the same
    //    signal here, so this branch is not a difference between the projects.
    if (el.__abClickBound) return 'js-click-listener';
    // 3. large iframe
    if (tag === 'iframe' || tag === 'frame') {
      const r = el.getBoundingClientRect();
      if (r.width > 100 && r.height > 100) return 'large-iframe';
    }
    // 4/5. label / span wrappers
    if (tag === 'label') {
      if (el.getAttribute('for')) return null;
      if (hasFormControlDescendant(el, 2)) return 'label-wraps-control';
    }
    if (tag === 'span' && hasFormControlDescendant(el, 2)) return 'span-wraps-control';
    // 6. THE SEARCH WORDLIST -- class, id, and ANY data-* VALUE.
    const cls = (el.getAttribute('class') || '').toLowerCase();
    const eid = (el.getAttribute('id') || '').toLowerCase();
    if (SEARCH_WORDS.some((w) => cls.includes(w))) return 'search-wordlist-class';
    if (SEARCH_WORDS.some((w) => eid.includes(w))) return 'search-wordlist-id';
    for (const a of el.attributes) {
      if (a.name.startsWith('data-') && SEARCH_WORDS.some((w) => (a.value || '').toLowerCase().includes(w)))
        return 'search-wordlist-data';
    }
    // 7. aria disabled/hidden reject (their AX equivalent)
    if (el.getAttribute('aria-disabled') === 'true') return null;
    if (el.getAttribute('aria-hidden') === 'true') return null;
    // 8. AX property branch, approximated from ARIA + native focusability.
    for (const p of ['aria-checked','aria-expanded','aria-pressed','aria-selected']) {
      if (el.hasAttribute(p)) return 'ax-state-property';
    }
    if (el.getAttribute('aria-required') === 'true') return 'ax-required';
    if (el.hasAttribute('aria-keyshortcuts')) return 'ax-keyshortcuts';
    if (el.isContentEditable) return 'ax-editable';
    // 9. interactive tags
    if (INTERACTIVE_TAGS.has(tag)) return 'interactive-tag';
    // 10. event attributes
    if (EVENT_ATTRS.some((a) => el.hasAttribute(a))) return 'event-attribute';
    // 11. ARIA role
    const role = el.getAttribute('role');
    if (role && INTERACTIVE_ROLES.has(role)) return 'aria-role';
    // 12. THE ICON RULE -- 10-50px with any of class/role/onclick/data-action/aria-label.
    const r = el.getBoundingClientRect();
    if (r.width >= 10 && r.width <= 50 && r.height >= 10 && r.height <= 50) {
      if (el.hasAttribute('class') || el.hasAttribute('role') || el.hasAttribute('onclick')
          || el.hasAttribute('data-action') || el.hasAttribute('aria-label')) return 'icon-size-rule';
    }
    // 13. cursor:pointer
    try { if (getComputedStyle(el).cursor === 'pointer') return 'cursor-pointer'; } catch (e) {}
    return null;
  };

  const out = [];
  const all = document.querySelectorAll('*');
  for (const el of all) {
    let rendered = true;
    try { rendered = !!(el.getClientRects && el.getClientRects().length); } catch (e) {}
    if (!rendered) continue;
    const v = verdict(el);
    if (!v) continue;
    let mmid = null;
    try { mmid = el.getAttribute('mmid'); } catch (e) {}
    const name = ((el.getAttribute('aria-label') || el.getAttribute('title')
      || (el.innerText || '').trim().slice(0, 60)) || '');
    out.push({ rule: v, mmid: mmid, tag: el.tagName.toLowerCase(), name: name });
  }
  return out;
})()
"""


async def one(browser, name, url):
    ctx = await browser.new_context(viewport=VIEWPORT)
    try:
        har = FROZEN / f"{name}.har"
        if not har.exists():
            return None
        await ctx.add_init_script(path=TAG_JS)
        await ctx.route_from_har(str(har), not_found="abort")
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        await page.wait_for_timeout(800)

        # OURS FIRST: it injects the mmid attributes THEIRS is keyed on, so the two
        # sets can be compared element-by-element rather than by count.
        ours = await page.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage(true); })()")
        if not isinstance(ours, list) or not ours:
            return None
        theirs = await page.evaluate(THEIRS_JS)

        our_ids = {str(e.get("mmid")) for e in ours if e.get("mmid") is not None}
        their_ids = {t["mmid"] for t in theirs if t.get("mmid")}
        # An element with no mmid was never even registered by our walk, so it is a
        # miss by definition -- counted, and attributed to the rule that admitted it.
        miss_rules = collections.Counter()
        miss_samples = []
        for t in theirs:
            if t.get("mmid") and t["mmid"] in our_ids:
                continue
            miss_rules[t["rule"]] += 1
            if len(miss_samples) < 6 and t.get("name"):
                miss_samples.append(f'{t["tag"]}[{t["rule"]}] "{t["name"][:40]}"')
        return {
            "name": name,
            "ours": len(our_ids),
            "theirs": len(theirs),
            "missed": sum(miss_rules.values()),
            "miss_rules": dict(miss_rules),
            "ours_only": len(our_ids - their_ids),
            "samples": miss_samples,
        }
    except Exception as e:
        return {"name": name, "error": str(e)[:90]}
    finally:
        await ctx.close()


def sites():
    src = (ROOT / "tools" / "capture_listings.py").read_text(encoding="utf-8")
    body = src[src.index("SITES = ["):src.index("\nOUT = ")]
    return re.findall(r'\(\s*"([a-z_0-9]+)"\s*,\s*"(https?://[^"]+)"', body)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=22)
    args = ap.parse_args()
    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for name, url in sites()[: args.n]:
            r = await one(browser, name, url)
            if r and not r.get("error"):
                rows.append(r)
                print(f"  {r['name']:20} ours={r['ours']:5} theirs={r['theirs']:5} "
                      f"we-miss={r['missed']:5} ours-only={r['ours_only']:5}")
        await browser.close()

    if not rows:
        print("no sites replayed")
        return 1
    tot_rules = collections.Counter()
    for r in rows:
        tot_rules.update(r["miss_rules"])
    tm = sum(tot_rules.values())
    print(f"\n  sites {len(rows)}   ours {sum(r['ours'] for r in rows)}   "
          f"theirs {sum(r['theirs'] for r in rows)}   we-miss {tm}   "
          f"ours-only {sum(r['ours_only'] for r in rows)}")
    print("\n  WHICH OF THEIR RULES ADMITS WHAT WE MISS:")
    for rule, n in tot_rules.most_common():
        print(f"    {rule:26} {n:6}  ({100.0 * n / max(1, tm):5.1f}%)")
    print("\n  SAMPLES OF WHAT WE MISS:")
    for r in rows[:8]:
        for s in r["samples"][:2]:
            print(f"    {r['name']:18} {s}")
    (ROOT / "temp" / "admission_ab.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
