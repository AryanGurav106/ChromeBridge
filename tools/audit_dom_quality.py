"""Measure DOM-listing QUALITY (not just size) across the real site corpus.

The existing harnesses answer "did it crash?" (test_gaps/test_widgets) and "how
big is it?" (measure_payload). Neither answers the question that decides whether
the collector is GENERAL: **on an arbitrary site, does the listing contain the
controls a human sees, name them distinguishably, and not bury them in noise?**

Metrics, per page, all computed in-page against the REAL collector extracted
from extension/background.js:

  recall       — of the ground-truth controls (visible, in-viewport, not
                 aria-hidden, matching a strict "this is definitely a control"
                 selector, shadow roots included), what fraction is reachable in
                 the structured output — as itself, a composed ancestor, or a
                 composed descendant? Dedup legitimately keeps a different node
                 for the same visual control, so exact-mmid equality would score
                 correct behaviour as loss.
  unlabeled    — entries with no name/text/value/placeholder at all.
  ambiguous    — entries whose label collides with another entry's AND that
                 carry no near=/under= breadcrumb to tell them apart. This is
                 the metric that predicts "the agent clicked the wrong one".
  generic      — div/span/li/p/td entries with no ARIA role: the collector's
                 own noise floor.
  chars/el     — payload efficiency.

Ground truth is deliberately NOT "everything the collector could have found" —
it is an independent selector-based definition, so the two can disagree.

Usage:
  python tools/audit_dom_quality.py --tag baseline            # all sites
  python tools/audit_dom_quality.py --tag baseline -n 30      # first 30
  python tools/audit_dom_quality.py --tag fixed
  python tools/audit_dom_quality.py --compare baseline fixed
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "temp" / "dom_quality"


sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract  # noqa: E402  (skips comments/strings/regexes)


def load_sites():
    src = (ROOT / "tools" / "capture_listings.py").read_text(encoding="utf-8")
    body = src[src.index("SITES = ["):src.index("\nOUT = ")]
    out = []
    for m in re.finditer(r'\(\s*"([a-z_0-9]+)"\s*,\s*"(https?://[^"]+)"(?:\s*,\s*(\d+))?\s*\)', body):
        out.append((m.group(1), m.group(2), int(m.group(3) or 0)))
    return out


# In-page measurement. `_collectInteractivePage` is prepended by the caller.
PROBE = r"""
(function () {
  const out = _collectInteractivePage(true);
  const listing = _collectInteractivePage(false);
  const outSet = new Set(out.map(e => String(e.mmid)));
  const vw = window.innerWidth, vh = window.innerHeight;

  const composedParent = (n) => {
    if (n.parentElement) return n.parentElement;
    try {
      if (n.getRootNode && n.getRootNode().host) return n.getRootNode().host;
      const v = n.ownerDocument && n.ownerDocument.defaultView;
      if (v && v.frameElement) return v.frameElement;
    } catch (e) {}
    return null;
  };

  // ---- GROUND TRUTH: an independent, selector-based definition of "control".
  const GT = 'a[href],button,input,select,textarea,summary,' +
    '[role="button"],[role="link"],[role="checkbox"],[role="radio"],[role="switch"],' +
    '[role="tab"],[role="menuitem"],[role="menuitemcheckbox"],[role="menuitemradio"],' +
    '[role="combobox"],[role="searchbox"],[role="textbox"],[role="slider"],[role="spinbutton"]';
  const cands = [];
  const sweep = (root) => {
    let all = [];
    try { all = Array.from(root.querySelectorAll('*')); } catch (e) { return; }
    for (const el of all) {
      try { if (el.matches(GT)) cands.push(el); } catch (e) {}
      if (el.shadowRoot) sweep(el.shadowRoot);
      const t = el.tagName.toLowerCase();
      if (t === 'iframe' || t === 'frame') { try { if (el.contentDocument) sweep(el.contentDocument); } catch (e) {} }
    }
  };
  sweep(document);

  const nameOf = (el) => {
    try {
      let s = (el.getAttribute('aria-label') || '').trim();
      if (!s) s = (el.innerText || '').replace(/\s+/g, ' ').trim();
      if (!s) s = (el.getAttribute('title') || el.getAttribute('placeholder') || el.value || '').trim();
      return s.slice(0, 50);
    } catch (e) { return ''; }
  };

  const gt = [], misses = [];
  for (const el of cands) {
    let r, cs;
    try { r = el.getBoundingClientRect(); cs = getComputedStyle(el); } catch (e) { continue; }
    if (!(r.width > 1 && r.height > 1)) continue;
    if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity || '1') === 0) continue;
    try { if (el.checkVisibility && !el.checkVisibility({ checkVisibilityCSS: true, checkOpacity: true })) continue; } catch (e) {}
    // frame-local rects: skip the viewport test for in-frame nodes (their own frame clips them)
    if (el.ownerDocument === document) {
      if (!(r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw)) continue;
    }
    try { if (el.closest && el.closest('[aria-hidden="true"]')) continue; } catch (e) {}
    if (el.tagName === 'INPUT' && (el.type || '').toLowerCase() === 'hidden') continue;
    // The collector deliberately does not list a user's typed document inside a
    // rich-text editor, nor a code editor's internal machinery. Excluding those
    // here keeps the metric about LOSS rather than about intentional filtering.
    try {
      const ce = el.closest('[contenteditable="true"],[contenteditable=""]');
      if (ce && ce !== el) continue;
      if (el.closest('.CodeMirror,.cm-editor,.monaco-editor,.ace_editor')) continue;
    } catch (e) {}
    gt.push(el);
  }

  let covered = 0;
  for (const el of gt) {
    const m = el.getAttribute('mmid');
    let ok = m && outSet.has(m);
    if (!ok) {                                   // composed ancestor already listed?
      let n = composedParent(el);
      while (n && !ok) {
        const am = n.getAttribute && n.getAttribute('mmid');
        if (am && outSet.has(am)) ok = true;
        n = composedParent(n);
      }
    }
    if (!ok) {                                   // a descendant listed instead?
      try {
        for (const d of el.querySelectorAll('[mmid]')) {
          if (outSet.has(d.getAttribute('mmid'))) { ok = true; break; }
        }
      } catch (e) {}
    }
    if (ok) covered++;
    else if (misses.length < 15) {
      const r = el.getBoundingClientRect();
      misses.push({
        tag: el.tagName.toLowerCase(), role: el.getAttribute('role') || '',
        name: nameOf(el), w: Math.round(r.width), h: Math.round(r.height),
        y: Math.round(r.top),
      });
    }
  }

  // ---- LISTING QUALITY
  const labelOf = (e) => (e.name || e.text || e.label || e.value || e.placeholder || '').trim();
  const unlabeled = out.filter(e => !labelOf(e)).length;
  const byLabel = new Map();
  for (const e of out) {
    const l = labelOf(e);
    if (l) byLabel.set(l, (byLabel.get(l) || 0) + 1);
  }
  let ambiguous = 0;
  for (const e of out) {
    const l = labelOf(e);
    if (!l || (byLabel.get(l) || 0) < 2) continue;
    if (e.near || e.underHeading || e.groupKey) continue;   // has a breadcrumb
    ambiguous++;
  }
  const generic = out.filter(e => !e.role && ['div','span','li','p','td','section','article'].includes(e.tag)).length;
  const flag = (k) => out.filter(e => e[k]).length;

  return {
    n: out.length,
    chars: listing.length,
    lines: listing ? listing.split('\n').length : 0,
    gt: gt.length,
    covered,
    misses,
    unlabeled,
    ambiguous,
    generic,
    flags: {
      iconOnly: flag('iconOnly'), required: flag('required'), unselected: flag('unselected'),
      disabled: flag('disabled'), canvasLike: flag('canvasLike'), crossFrame: flag('crossFrame'),
      clipped: flag('clippedInContainer'), offscreen: flag('offscreen'),
      occluded: out.filter(e => e.clickable === false).length,
      scrollRegion: flag('scrollRegion'), orphan: flag('orphanWidget'),
      named: flag('name'), near: flag('near'), under: flag('underHeading'),
    },
    modal: listing.indexOf('A MODAL/DIALOG IS CURRENTLY OPEN') !== -1,
    overlay: listing.indexOf('BLOCKED BY AN OVERLAY') !== -1,
    dialogText: listing.indexOf('Dialog text:') !== -1,
    heading: (listing.match(/^Main heading: (.*)$/m) || ['', ''])[1].slice(0, 60),
  };
})()
"""


async def one(ctx, name, url, extra, wrap):
    page = await ctx.new_page()
    rec = {"name": name, "url": url}
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        await page.wait_for_timeout(1400 + extra)
        rec.update(await page.evaluate(wrap))
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:90]}"
    finally:
        try:
            await page.close()
        except Exception:
            pass
    return rec


async def run(tag, limit, concurrency, only):
    src = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
    # NOTE: `return` + newline is ASI — the probe must start on the same line.
    wrap = "(function(){ " + extract("_collectInteractivePage", src) + "\n; return (" + PROBE.strip() + "); })()"
    sites = load_sites()
    if only:
        want = set(only.split(","))
        sites = [s for s in sites if s[0] in want]
    if limit:
        sites = sites[:limit]
    print(f"{len(sites)} sites, concurrency {concurrency}, tag={tag}\n", flush=True)

    rows, sem = [], asyncio.Semaphore(concurrency)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1366, "height": 900})
        await ctx.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))

        async def guarded(s):
            async with sem:
                r = await one(ctx, s[0], s[1], s[2], wrap)
                if "error" in r:
                    print(f"  {r['name']:<18} SKIP  {r['error'][:60]}", flush=True)
                else:
                    rc = 100 * r["covered"] / r["gt"] if r["gt"] else 100.0
                    print(f"  {r['name']:<18} n={r['n']:<4} recall={rc:5.1f}% "
                          f"unlab={r['unlabeled']:<3} ambig={r['ambiguous']:<3} "
                          f"gen={r['generic']:<3} {r['chars']:>6}ch", flush=True)
                return r

        rows = await asyncio.gather(*[guarded(s) for s in sites])
        await browser.close()

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{tag}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    summarise(rows, tag)
    return rows


def totals(rows):
    ok = [r for r in rows if "error" not in r]
    t = dict(sites=len(ok), fails=len(rows) - len(ok),
             n=sum(r["n"] for r in ok), gt=sum(r["gt"] for r in ok),
             covered=sum(r["covered"] for r in ok),
             unlabeled=sum(r["unlabeled"] for r in ok),
             ambiguous=sum(r["ambiguous"] for r in ok),
             generic=sum(r["generic"] for r in ok),
             chars=sum(r["chars"] for r in ok))
    t["recall"] = 100 * t["covered"] / t["gt"] if t["gt"] else 0.0
    return t


def summarise(rows, tag):
    t = totals(rows)
    print(f"\n=== {tag} ===")
    print(f"  {t['sites']} pages measured, {t['fails']} unreachable")
    print(f"  recall      {t['recall']:.2f}%   ({t['covered']}/{t['gt']} ground-truth controls reachable)")
    print(f"  entries     {t['n']}   ({t['chars']} chars, {t['chars']/max(t['n'],1):.0f} chars/entry)")
    print(f"  unlabeled   {t['unlabeled']} ({100*t['unlabeled']/max(t['n'],1):.1f}%)")
    print(f"  ambiguous   {t['ambiguous']} ({100*t['ambiguous']/max(t['n'],1):.1f}%)  [same label, no breadcrumb]")
    print(f"  generic     {t['generic']} ({100*t['generic']/max(t['n'],1):.1f}%)  [div/span, no role]")
    worst = sorted([r for r in rows if "error" not in r and r["gt"] >= 8],
                   key=lambda r: r["covered"] / r["gt"])[:12]
    if worst:
        print("\n  lowest recall:")
        for r in worst:
            eg = ", ".join(
                "{}{} {!r}".format(m["tag"], "[" + m["role"] + "]" if m["role"] else "", m["name"][:22])
                for m in r["misses"][:3])
            print(f"    {r['name']:<18} {100*r['covered']/r['gt']:5.1f}%  "
                  f"({r['gt']-r['covered']}/{r['gt']} missed)  e.g. {eg}")
    amb = sorted([r for r in rows if "error" not in r and r["n"] >= 10],
                 key=lambda r: -r["ambiguous"] / r["n"])[:8]
    if amb:
        print("\n  most ambiguous listings:")
        for r in amb:
            print(f"    {r['name']:<18} {100*r['ambiguous']/r['n']:5.1f}%  ({r['ambiguous']}/{r['n']})")


def compare(a_tag, b_tag):
    a = {r["name"]: r for r in json.loads((OUT / f"{a_tag}.json").read_text(encoding="utf-8"))}
    b = {r["name"]: r for r in json.loads((OUT / f"{b_tag}.json").read_text(encoding="utf-8"))}
    both = [k for k in a if k in b and "error" not in a[k] and "error" not in b[k]]
    print(f"comparing {a_tag} -> {b_tag} over {len(both)} pages reachable in both\n")

    def agg(d):
        rs = [d[k] for k in both]
        return totals(rs)

    ta, tb = agg(a), agg(b)
    rows = [("recall %", ta["recall"], tb["recall"], "+"),
            ("entries", ta["n"], tb["n"], "="),
            ("chars", ta["chars"], tb["chars"], "-"),
            ("unlabeled", ta["unlabeled"], tb["unlabeled"], "-"),
            ("ambiguous", ta["ambiguous"], tb["ambiguous"], "-"),
            ("generic", ta["generic"], tb["generic"], "-")]
    print(f"  {'metric':<12} {a_tag:>12} {b_tag:>12} {'delta':>12}")
    for nm, x, y, want in rows:
        d = y - x
        mark = "" if want == "=" or d == 0 else ("  ok" if (d > 0) == (want == "+") else "  WORSE")
        print(f"  {nm:<12} {x:>12.2f} {y:>12.2f} {d:>+12.2f}{mark}")

    print("\n  per-page recall changes (>0.5pp):")
    moved = []
    for k in both:
        ra = 100 * a[k]["covered"] / a[k]["gt"] if a[k]["gt"] else 100.0
        rb = 100 * b[k]["covered"] / b[k]["gt"] if b[k]["gt"] else 100.0
        if abs(rb - ra) > 0.5:
            moved.append((rb - ra, k, ra, rb))
    for d, k, ra, rb in sorted(moved):
        print(f"    {k:<18} {ra:5.1f}% -> {rb:5.1f}%  {d:+.1f}pp" + ("   REGRESSION" if d < 0 else ""))
    if not moved:
        print("    (none)")

    print("\n  per-page entry-count changes (>10%):")
    ch = []
    for k in both:
        na, nb = a[k]["n"], b[k]["n"]
        if na and abs(nb - na) / na > 0.10:
            ch.append((nb - na, k, na, nb))
    for d, k, na, nb in sorted(ch, key=lambda x: -abs(x[0]))[:20]:
        print(f"    {k:<18} {na} -> {nb}  ({d:+d})")
    if not ch:
        print("    (none)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="run")
    ap.add_argument("-n", "--limit", type=int, default=0)
    ap.add_argument("-c", "--concurrency", type=int, default=4)
    ap.add_argument("--only", default="")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"))
    args = ap.parse_args()
    if args.compare:
        compare(*args.compare)
    else:
        asyncio.run(run(args.tag, args.limit, args.concurrency, args.only))
