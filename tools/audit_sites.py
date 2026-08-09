"""Multi-site DOM-listing audit.

Runs Playwright headless against several real public sites, injects the same
collection JS the Chrome extension uses, and prints a noise/effectiveness
audit per site. Lets us spot site-specific noise patterns the universal
filters miss, before we get an angry user run.

Run:  python tools/audit_sites.py
"""

import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

from playwright.async_api import async_playwright

SITES = [
    ("example.com",     "https://example.com/"),
    ("HackerNews",      "https://news.ycombinator.com/"),
    ("Wikipedia (en)",  "https://en.wikipedia.org/wiki/Main_Page"),
    ("DuckDuckGo home", "https://duckduckgo.com/"),
    ("GitHub home",     "https://github.com/"),
    ("StackOverflow",   "https://stackoverflow.com/"),
    ("Notion landing",  "https://www.notion.so/"),
]

# Two JS snippets:
#   COLLECT_RAW  — no filters at all (returns every isInteractive candidate)
#   COLLECT_FILT — current extension filter set
# Same isInteractive/visibility logic, isolated so we can compare apples-to-apples.

COMMON = r"""
const tags_to_ignore = ['head','style','script','link','meta','noscript','template','iframe','g','main','c-wiz','path'];
const ids_to_ignore = ['agentDriveAutoOverlay'];
const decorativeTags = new Set(['svg','rect','path','circle','polyline','polygon','line','ellipse','g','use','defs','symbol']);
const formyTags = new Set(['input','textarea','select']);

// Inject deterministic mmids.
{
  let id = 0;
  document.querySelectorAll('*').forEach(el => {
    const tag = el.tagName.toLowerCase();
    if (tags_to_ignore.includes(tag) || ids_to_ignore.includes(el.id)) return;
    el.setAttribute('mmid', `${++id}`);
  });
}

const vw = window.innerWidth || document.documentElement.clientWidth;
const vh = window.innerHeight || document.documentElement.clientHeight;

const isInteractive = (el) => {
    const tag = el.tagName.toLowerCase();
    if (['a','button','input','select','textarea'].includes(tag)) return true;
    const role = el.getAttribute('role');
    if (role && ['button','link','menuitem','menuitemcheckbox','menuitemradio','tab','checkbox','radio','switch','option','combobox','searchbox','textbox'].includes(role)) return true;
    if (el.hasAttribute('onclick') || el.hasAttribute('tabindex') || el.isContentEditable) return true;
    try { if (getComputedStyle(el).cursor === 'pointer') return true; } catch (e) {}
    return false;
};

const _isSemanticTable = (t) => {
    if (!t) return false;
    if (t.querySelector && (t.querySelector('thead') || t.querySelector('th'))) return true;
    const r = t.getAttribute && t.getAttribute('role');
    return !!(r && ['table','grid','treegrid'].includes(r));
};
const section = (el) => {
    let walker = el;
    while (walker && walker !== document.body && walker.tagName) {
      const tag = walker.tagName.toLowerCase();
      const role = walker.getAttribute ? walker.getAttribute('role') : null;
      if (tag === 'thead') { if (_isSemanticTable(walker.parentElement)) return 'table-header'; }
      else if (tag === 'tbody') { if (_isSemanticTable(walker.parentElement)) return 'table-body'; }
      else if (tag === 'table' || role === 'table' || role === 'grid' || role === 'treegrid') {
        if (_isSemanticTable(walker)) return 'table';
      }
      if (tag === 'dialog' || role === 'dialog' || role === 'alertdialog' ||
          (walker.getAttribute && walker.getAttribute('aria-modal') === 'true')) return 'dialog';
      if (tag === 'aside' || role === 'complementary') return 'sidebar';
      if (tag === 'nav'   || role === 'navigation')    return 'nav';
      if (tag === 'header'|| role === 'banner')        return 'header';
      if (tag === 'footer'|| role === 'contentinfo')   return 'footer';
      if (tag === 'main'  || role === 'main')          return 'main';
      if (role === 'tablist' || role === 'tabpanel')   return role;
      if (role === 'menu' || role === 'menubar' || role === 'listbox') return role;
      if (role === 'form' || tag === 'form')           return 'form';
      walker = walker.parentElement;
    }
    return '';
};

const activeHint = (el) => {
    try {
      const ac = el.getAttribute('aria-current');
      if (ac && ac !== 'false') return 'current';
      if (el.getAttribute('aria-selected') === 'true') return 'selected';
      if (el.getAttribute('aria-pressed') === 'true') return 'pressed';
      if (el.getAttribute('aria-expanded') === 'true') return 'expanded';
      const ds = el.getAttribute('data-state');
      if (ds === 'active' || ds === 'open' || ds === 'on' || ds === 'checked') return ds;
      if (el.getAttribute('data-active') === 'true') return 'active';
      if (el.getAttribute('data-current') === 'true') return 'current';
    } catch (e) {}
    return '';
};
"""

# RAW: candidate set (interactive + visible + in viewport) — no other filters.
COLLECT_RAW = COMMON + r"""
const out = [];
document.querySelectorAll('[mmid]').forEach(el => {
    if (!isInteractive(el)) return;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const visible = r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity || '1') > 0;
    const inViewport = r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw;
    if (!visible || !inViewport) return;
    const tag = el.tagName.toLowerCase();
    let label = (el.getAttribute('aria-label') || el.value || el.getAttribute('placeholder') ||
                 el.innerText || el.getAttribute('name') || el.getAttribute('title') || el.getAttribute('alt') || '').trim();
    label = label.replace(/\s+/g, ' ').slice(0, 60);
    out.push({mmid: el.getAttribute('mmid'), tag, label,
              w: Math.round(r.width), h: Math.round(r.height),
              section: section(el), role: el.getAttribute('role'),
              active: activeHint(el)});
});
return out;
"""

# FILTERED: drops decorative SVG, aria-hidden, sub-8px, empty-label-non-form,
# and same-label-as-ancestor-already-in-list (the parent-child dedup).
COLLECT_FILT = COMMON + r"""
const addedMmids = new Set();
const out = [];
document.querySelectorAll('[mmid]').forEach(el => {
    if (!isInteractive(el)) return;
    const tag = el.tagName.toLowerCase();
    if (decorativeTags.has(tag)) {
        const rr = el.getAttribute('role');
        if (!rr || !['button','link','tab','menuitem','checkbox','radio','combobox','option','menuitemcheckbox','menuitemradio'].includes(rr)) return;
    }
    if (el.getAttribute('aria-hidden') === 'true') return;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const visible = r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity || '1') > 0;
    const inViewport = r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw;
    if (!visible || !inViewport) return;
    if (r.width < 8 || r.height < 8) { if (!formyTags.has(tag)) return; }
    let label = (el.getAttribute('aria-label') || el.value || el.getAttribute('placeholder') ||
                 el.innerText || el.getAttribute('name') || el.getAttribute('title') || el.getAttribute('alt') || '').trim();
    label = label.replace(/\s+/g, ' ').slice(0, 60);
    if (!label && !formyTags.has(tag)) return;
    if (label) {
      let walker = el.parentElement, skip = false;
      while (walker && walker !== document.body) {
        const pMmid = walker.getAttribute && walker.getAttribute('mmid');
        if (pMmid && addedMmids.has(pMmid)) {
          const parentEntry = out.find(o => o.mmid === pMmid);
          if (parentEntry && parentEntry.label === label) { skip = true; break; }
        }
        walker = walker.parentElement;
      }
      if (skip) return;
    }
    addedMmids.add(el.getAttribute('mmid'));
    out.push({mmid: el.getAttribute('mmid'), tag, label,
              w: Math.round(r.width), h: Math.round(r.height),
              section: section(el), role: el.getAttribute('role'),
              active: activeHint(el)});
});
return out;
"""


def summarise(elements: list[dict]) -> dict:
    n = len(elements)
    chars = sum(80 + len(e.get("label") or "") for e in elements)  # rough listing-size proxy
    sec = Counter(e.get("section") or "(none)" for e in elements)
    tag = Counter(e.get("tag") for e in elements)
    unlabeled = sum(1 for e in elements if not (e.get("label") or "").strip())
    tiny = sum(1 for e in elements if (e.get("w") or 0) < 12 and (e.get("h") or 0) < 12)
    active = sum(1 for e in elements if e.get("active"))
    return dict(n=n, chars=chars, unlabeled=unlabeled, tiny=tiny,
                active=active, top_sections=dict(sec.most_common(5)),
                top_tags=dict(tag.most_common(5)))


async def audit_one(browser, name: str, url: str) -> dict:
    ctx = await browser.new_context(viewport={"width": 1366, "height": 900})
    page = await ctx.new_page()
    page.set_default_navigation_timeout(20000)
    page.set_default_timeout(20000)
    out = {"name": name, "url": url}
    try:
        await page.goto(url, wait_until="domcontentloaded")
        # Give SPAs a moment to render their initial DOM.
        try: await page.wait_for_load_state("networkidle", timeout=4000)
        except Exception: pass
        raw  = await page.evaluate("() => { " + COLLECT_RAW + " }")
        filt = await page.evaluate("() => { " + COLLECT_FILT + " }")
        out["raw"]      = summarise(raw)
        out["filtered"] = summarise(filt)
        out["raw_to_filt_ratio"] = (out["filtered"]["n"] / out["raw"]["n"]) if out["raw"]["n"] else 0
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    finally:
        await ctx.close()
    return out


async def main():
    artefact_dir = Path("temp/site_audit"); artefact_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        rows = []
        for name, url in SITES:
            print(f"  • {name:20s} {url}", flush=True)
            row = await audit_one(browser, name, url)
            rows.append(row)
        await browser.close()

    # Save full JSON + print a compact table.
    (artefact_dir / "audit.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print()
    h = f"{'Site':<18} {'raw':>6} {'filt':>6} {'kept%':>6} {'tiny':>5} {'noLabel':>7} {'active':>6}  top sections"
    print(h); print("-" * len(h))
    for r in rows:
        if "error" in r:
            print(f"{r['name']:<18} ERROR: {r['error'][:80]}"); continue
        raw, fi = r["raw"], r["filtered"]
        kept = f"{r['raw_to_filt_ratio']*100:5.1f}%" if r['raw_to_filt_ratio'] else "  n/a"
        secs = ", ".join(f"{k}={v}" for k, v in (fi['top_sections'] or {}).items() if k != '(none)')
        print(f"{r['name']:<18} {raw['n']:>6} {fi['n']:>6} {kept:>6} "
              f"{fi['tiny']:>5} {fi['unlabeled']:>7} {fi['active']:>6}  {secs or '(no semantic sections detected)'}")
    print(f"\nFull JSON: {artefact_dir/'audit.json'}")

if __name__ == "__main__":
    asyncio.run(main())
