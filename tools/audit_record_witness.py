"""Can a tied crowd's ordinal be WITNESSED by what the page declares about the RECORD?

#72 found that an ordinal is a positional claim, that a re-sort destroys it
silently, and that the shipped witness (self fields + the nearest preceding
NAMED CONTROLS) exists for only ~38-41% of ordinal-bearing descriptors. This
probe measures the candidate that the shipped witness cannot see at all: the
RENDERED CONTENT OF THE RECORD the control sits in -- the other cells of its
row, the card's title and price. Those are not controls, so they are not in
`entries`, so `witness_map` never saw them. They are also exactly how a human
says which Delete button they meant ("the one on the 1001 row").

THE RECORD IS STRUCTURAL, NOT A TAG LIST. For a tied crowd, take the lowest
common ancestor of its members; a member's record is the child of that LCA
containing it. Where several members share one child (a grid of cards inside
rows) recurse inside that child until the member stands alone. No `tr`/`li`
vocabulary, no class name, no threshold -- the same MDR/DEPTA assumption #27
uses to decide repetition.

CANDIDATE ATOMS, each a declared fact:
  text   every rendered text node (and img alt) in the record
  attr   every non-presentational attribute on the record root and on the
         member itself ("name=qty[3]", "id=row-1001"). `class` and `style` are
         excluded because they are presentation, not declaration (#27).
  rowix  aria-rowindex / aria-posinset on the record or an ancestor. POSITIONAL,
         so reported for coverage only -- it travels with the position, not the
         record, which is exactly what makes it useless against a re-sort.

A step's witness is the SET of atoms unique to that member AT RECORD TIME. At
replay a member "carries" the witness if its atom set INTERSECTS the stored one;
exactly one carrier resolves, zero or several refuse. Set intersection rather
than equality is what lets one cell change (a status flipping) without
invalidating the step, and it needs no threshold.

MEASURED, every arm applied to a REAL DOM mutation of a real re-collected page
(not the synthetic entry-list permutation audit_flow_resolve uses):

  coverage     of ordinal-bearing descriptors, how many have >=1 unique atom
  stability    same source loaded twice: does the stored witness still resolve
               the same element? (generated ids / timestamps show up here)
  resort       the records are reversed in the DOM
  shuffle      the records are randomly permuted
  edit-cell    ONE atom of the victim's record changes (a status flip)
  bump-digits  every digit run in every record changes (counters, times)
  drop-other   a DIFFERENT record is removed (crowd composition changes)

Verdicts are CORRECT / REFUSED / WRONG as in audit_flow_resolve. WRONG is the
only defect. The EXISTING resolver (descriptor.resolve) is run on the same
mutated page in the same pass, so run-order drift cannot align with the arm
(#19).

Usage:
    python tools/audit_record_witness.py --sites 40
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "temp" / "frozen"
OUT = ROOT / "temp" / "descriptors"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))
from _extract import extract  # noqa: E402
from capture_listings import SITES  # noqa: E402
from core.flows import descriptor as D  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = extract("_collectInteractivePage", BG, verify=True)
TAG_JS = str(ROOT / "extension" / "listener_tag.js")
VIEWPORT = {"width": 1280, "height": 1600}
PER_SITE = 120
ARMS = ("base", "resort", "resort-last", "resort-first", "shuffle", "edit-cell", "bump-digits", "drop-other")
# txt is the text-only variant. It exists because the first full run showed an
# auto-generated id (Angular Material's `mat-select-value-3`) is unique, looks
# stable, and is a per-load counter: 4 of 120 descriptors on one site resolved to
# the WRONG element with NO mutation applied at all.
VARIANTS = {"rec": ("text", "attr"), "txt": ("text", "text"), "win": ("win", "attr")}

# ----------------------------------------------------------------------------
# In-page helpers. window.__rw.atoms(groups) and window.__rw.mutate(kind, ...)
# ----------------------------------------------------------------------------
PAGE_JS = r"""
(function () {
  const reg = () => window.__mmidReg;
  const el = (m) => { const r = reg(); const n = r && r.get(String(m)); return n && n.isConnected ? n : null; };
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const chain = (n) => { const a = []; for (let x = n; x; x = x.parentNode) a.push(x); return a; };
  function lca(nodes) {
    let c = chain(nodes[0]);
    for (const n of nodes.slice(1)) { const s = new Set(chain(n)); c = c.filter((x) => s.has(x)); }
    return c[0] || null;
  }
  function childToward(parent, n) {
    let x = n; while (x && x.parentNode !== parent) x = x.parentNode; return x;
  }
  // The record of `member` among `members`: recurse until it stands alone.
  function recordOf(member, members) {
    let S = members, last = null;
    for (let guard = 0; guard < 40; guard++) {
      const L = lca(S); if (!L) return last;
      const c = childToward(L, member);
      if (!c || c === member) return last || member;
      const S2 = S.filter((m) => c.contains(m));
      last = c;
      if (S2.length <= 1) return c;
      if (S2.length === S.length) return c;     // no progress: cannot split further
      S = S2;
    }
    return last;
  }
  function textAtoms(root, own) {
    const out = new Set();
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    for (let n = w.currentNode; n; n = w.nextNode()) {
      if (n.nodeType === 3) {
        const p = n.parentElement;
        if (!p || /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(p.tagName)) continue;
        try { if (p.checkVisibility && !p.checkVisibility({ visibilityProperty: true })) continue; } catch (e) {}
        const t = norm(n.nodeValue); if (t) out.add(t);
      } else if (n.nodeType === 1 && n.tagName === 'IMG') {
        const t = norm(n.getAttribute('alt')); if (t) out.add(t);
      }
    }
    return out;
  }
  const SKIP = new Set(['class', 'style', 'mmid']);
  function attrAtoms(node) {
    const out = new Set();
    if (!node || !node.attributes) return out;
    for (const a of node.attributes) {
      if (SKIP.has(a.name)) continue;
      const v = norm(a.value); if (v) out.add(a.name + '=' + v);
    }
    return out;
  }
  function rowix(node) {
    for (let x = node; x && x.nodeType === 1; x = x.parentNode) {
      for (const k of ['aria-rowindex', 'aria-posinset']) { const v = x.getAttribute(k); if (v) return k + '=' + v; }
    }
    return '';
  }
  // MDR's "generalized node": a record may span SEVERAL consecutive siblings
  // (Hacker News: a title <tr> then a subtext <tr>). The run of member k is the
  // siblings after the previous member's record up to and including its own; the
  // first member takes the second's STRIDE (records of a list are equal-length,
  // which is the same assumption #27 uses for repetition -- not a threshold).
  function runs(recs, align) {
    const P = recs[0].parentNode;
    if (!P || recs.some((r) => r.parentNode !== P)) return null;
    const kids = [...P.children];
    const idx = recs.map((r) => kids.indexOf(r));
    if (idx.some((i, k) => k > 0 && i <= idx[k - 1])) return null;     // not in doc order
    const out = [];
    const n = recs.length;
    for (let k = 0; k < n; k++) {
      if (align === 'first') {
        // the member OPENS its record (Hacker News: the vote arrow is in the title row)
        const stride = k < n - 1 ? idx[k + 1] - idx[k] : (n > 1 ? idx[k] - idx[k - 1] : 1);
        out.push(kids.slice(idx[k], idx[k] + stride));
      } else {
        const stride = k === 0 ? (n > 1 ? idx[1] - idx[0] : 1) : idx[k] - idx[k - 1];
        out.push(kids.slice(Math.max(0, idx[k] - stride + 1), idx[k] + 1));
      }
    }
    return out;
  }
  window.__rw = {
    atoms(groups) {
      const res = {};
      for (const g of groups) {
        const nodes = g.map(el);
        if (nodes.some((n) => !n)) { for (const m of g) res[m] = null; continue; }
        const recsAll = nodes.map((n) => recordOf(n, nodes));
        const order0 = recsAll.every((r) => r) ? [...recsAll].sort((a, b) => (a.compareDocumentPosition(b) & 4 ? -1 : 1)) : null;
        const rr = order0 ? runs(order0) : null;
        for (let i = 0; i < g.length; i++) {
          const rec = recordOf(nodes[i], nodes);
          const text = rec && rec !== nodes[i] ? [...textAtoms(rec)] : [];
          const attr = [...attrAtoms(rec && rec !== nodes[i] ? rec : null), ...attrAtoms(nodes[i])];
          let run = [], win = [];
          if (order0 && rec) {
            const P = rec.parentNode; const kids = P ? [...P.children] : [];
            const ix = kids.indexOf(rec); const k = order0.indexOf(rec);
            const stride = k > 0 ? ix - kids.indexOf(order0[k - 1]) : (order0.length > 1 ? kids.indexOf(order0[1]) - ix : 1);
            if (ix >= 0 && stride > 0) {
              const w2 = new Set();
              for (const n of kids.slice(Math.max(0, ix - stride + 1), ix + stride)) for (const t of textAtoms(n)) w2.add(t);
              win = [...w2];
            }
          }
          if (rr && rec) { const k = order0.indexOf(rec); if (k >= 0) { const s2 = new Set(); for (const n of rr[k]) for (const t of textAtoms(n)) s2.add(t); run = [...s2]; } }
          res[g[i]] = { text, run, win, attr, rowix: rowix(nodes[i]), rec: !!(rec && rec !== nodes[i]) };
        }
      }
      return res;
    },
    // mutate the DOM for each crowd; returns the mmids the arm applies to
    mutate(kind, groups, victims, seed) {
      let s = seed >>> 0; const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
      const applied = [];
      for (const g of groups) {
        const nodes = g.map(el); if (nodes.some((n) => !n)) continue;
        const recs = nodes.map((n) => recordOf(n, nodes));
        if (recs.some((r) => !r || recs.filter((x) => x === r).length !== 1)) continue;
        if (kind === 'resort-last' || kind === 'resort-first') {
          const order = [...recs].sort((a, b) => (a.compareDocumentPosition(b) & 4 ? -1 : 1));
          const rr = runs(order, kind === 'resort-first' ? 'first' : 'last'); if (!rr) continue;
          const marks = rr.map((b) => { const m = document.createComment(''); b[0].before(m); return m; });
          const blocks = rr.slice().reverse();
          marks.forEach((m, i) => { for (const n of blocks[i]) m.before(n); });
          marks.forEach((m) => m.remove());
          g.forEach((m) => applied.push(m));
        } else if (kind === 'resort' || kind === 'shuffle') {
          const parent = recs[0].parentNode;
          if (!parent || recs.some((r) => r.parentNode !== parent)) continue;
          // order in the DOM, not in the list we were given
          const order = [...recs].sort((a, b) => (a.compareDocumentPosition(b) & 4 ? -1 : 1));
          const marks = order.map((n) => { const m = document.createComment(''); n.before(m); return m; });
          let perm = order.map((_, i) => order.length - 1 - i);
          if (kind === 'shuffle') {
            perm = order.map((_, i) => i);
            for (let i = perm.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [perm[i], perm[j]] = [perm[j], perm[i]]; }
            if (perm.every((p, i) => p === i)) perm.reverse();
          }
          const nn = order.slice();
          marks.forEach((m, i) => { m.replaceWith(nn[perm[i]]); });
          g.forEach((m) => applied.push(m));
        } else if (kind === 'bump-digits') {
          for (const r of recs) {
            const w = document.createTreeWalker(r, NodeFilter.SHOW_TEXT);
            for (let n = w.currentNode; n; n = w.nextNode())
              if (/\d/.test(n.nodeValue || '')) n.nodeValue = n.nodeValue.replace(/\d+/g, (d) => String(Number(d) + 1));
          }
          g.forEach((m) => applied.push(m));
        } else if (kind === 'edit-cell') {
          const v = victims[g[0]]; if (v == null) continue;
          const i = g.indexOf(String(v)); if (i < 0) continue;
          const w = document.createTreeWalker(recs[i], NodeFilter.SHOW_TEXT);
          let done = false;
          for (let n = w.currentNode; n && !done; n = w.nextNode())
            if (norm(n.nodeValue) && n.parentElement && !/^(SCRIPT|STYLE)$/.test(n.parentElement.tagName)) { n.nodeValue = n.nodeValue + ' (edited)'; done = true; }
          if (done) applied.push(String(v));
        } else if (kind === 'drop-other') {
          const v = victims[g[0]]; if (v == null) continue;
          const j = g.findIndex((m) => String(m) !== String(v)); if (j < 0) continue;
          recs[j].remove();
          g.forEach((m, k) => { if (k !== j) applied.push(m); });
        }
      }
      return applied;
    },
  };
  return true;
})()
"""


async def collect(page) -> list[dict]:
    return await page.evaluate(
        "(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, 'brief'); })()"
    ) or []


async def load(browser, name, url):
    har = FROZEN / f"{name}.har"
    if not har.exists():
        return None, None
    ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True)
    await ctx.add_init_script(path=TAG_JS)
    await ctx.route_from_har(str(har), not_found="abort")
    page = await ctx.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
    except Exception:
        await ctx.close()
        return None, None
    await page.wait_for_timeout(1200)
    return ctx, page


def crowds_of(entries):
    """FULL-descriptor crowds of size >= 2, as lists of entries in document order."""
    pool = [e for e in entries if D._targetable(e)]
    groups: dict = {}
    for e in pool:
        groups.setdefault(json.dumps(D.at_level(e, D.FULL), sort_keys=True), []).append(e)
    return [g for g in groups.values() if len(g) >= 2]


def uniq(atoms_by_mmid: dict, mm: str, key: str) -> set:
    mine = set((atoms_by_mmid.get(mm) or {}).get(key) or [])
    others = set()
    for k, v in atoms_by_mmid.items():
        if k != mm and v:
            others |= set(v.get(key) or [])
    return mine - others


def resolve_new(stored: set, hits: list, atoms: dict, keys=("text", "attr")):
    """Set-intersection witness. Returns mmid or None (REFUSED)."""
    cand = []
    for h in hits:
        a = atoms.get(str(h.get("mmid"))) or {}
        have = set()
        for k in keys:
            have |= set(a.get(k) or [])
        if have & stored:
            cand.append(h)
    return str(cand[0].get("mmid")) if len(cand) == 1 else None


def v_exist(t, want, ents):
    try:
        ref = D.resolve(t, ents)
    except D.Unresolved:
        return "REFUSED"
    return "CORRECT" if ref == str(want) else "WRONG"


def v_new(t, want, ents, stored, atoms_after, keys):
    """Policy: a step carrying record atoms is decided by them; otherwise the
    existing resolver decides. Atoms never fall back to the ordinal."""
    full = t.get("full") or t.get("desc") or {}
    hits = [e for e in ents if D._targetable(e) and D.matches(full, e)]
    if not hits:
        return "REFUSED"
    ref = resolve_new(stored, hits, atoms_after, keys)
    if ref is None:
        return "REFUSED"
    return "CORRECT" if ref == str(want) else "WRONG"


async def run_site(browser, name, url, rng):
    ctx, page = await load(browser, name, url)
    if not page:
        return None
    try:
        await page.evaluate(PAGE_JS)
        a = await collect(page)
        if len(a) < 5:
            return None
        crowds = crowds_of(a)
        if not crowds:
            return {"name": name, "ords": 0, "crowds": 0}
        groups = [[str(e["mmid"]) for e in g] for g in crowds]
        atoms = await page.evaluate("(g)=>window.__rw.atoms(g)", groups)
    finally:
        await ctx.close()

    # Ordinal-bearing targets: sample per site so one giant table cannot dominate.
    members = [(e, g) for g in crowds for e in g]
    if len(members) > PER_SITE:
        members = rng.sample(members, PER_SITE)
    row = {"name": name, "crowds": len(crowds), "ords": len(members),
           "sizes": [len(g) for g in crowds][:20]}

    gof = {m: gi for gi, g in enumerate(groups) for m in g}
    cov = Counter()
    tgts = {}
    for e, g in members:
        mm = str(e["mmid"])
        t = D.build(e, a)
        if t.get("of") is None:
            continue
        crowd = groups[gof[mm]]
        sub = {k: atoms.get(k) for k in crowd}
        st = {v: (uniq(sub, mm, ks[0]) | uniq(sub, mm, ks[1])) for v, ks in VARIANTS.items()}
        ex = bool(t.get("witness"))
        cov["n"] += 1
        cov["existing"] += ex
        cov["text"] += bool(uniq(sub, mm, "text"))
        cov["win"] += bool(uniq(sub, mm, "win"))
        cov["attr"] += bool(uniq(sub, mm, "attr"))
        for v in VARIANTS:
            cov[v + "_any"] += bool(st[v])
            cov[v + "_or_shipped"] += bool(st[v] or ex)
            cov[v + "_rescue"] += ((not ex) and bool(st[v]))
        cov["unwit_n"] += (not ex)
        cov["rowix"] += bool((atoms.get(mm) or {}).get("rowix"))
        cov["no_record"] += (not (atoms.get(mm) or {}).get("rec"))
        tgts[mm] = (e, t, st, ex)
    row["cov"] = dict(cov)
    if not tgts:
        return row

    # Arms. Fresh load per arm; the mutation is applied to every crowd at once
    # (crowds are disjoint element sets) and the target set is restricted to the
    # members the mutation actually applied to.
    verd = {arm: {} for arm in ARMS}
    def bump(arm, who, v, ex):
        verd[arm].setdefault(who, Counter())[v] += 1
        if not ex:
            verd[arm].setdefault(who + "_unwit", Counter())[v] += 1
    for arm in ARMS:
        ctx, page = await load(browser, name, url)
        if not page:
            continue
        try:
            await page.evaluate(PAGE_JS)
            b0 = await collect(page)         # stamps mmids exactly as pass A did
            if {str(e["mmid"]) for e in b0 if D._targetable(e)} != \
                    {str(e["mmid"]) for e in a if D._targetable(e)}:
                row["ruler_valid"] = False
                continue
            victims = {g[0]: rng.choice(g) for g in groups}
            applied = set()
            if arm != "base":
                applied = set(await page.evaluate(
                    "([k,g,v,s])=>window.__rw.mutate(k,g,v,s)",
                    [arm, groups, victims, rng.randrange(1 << 30)]))
            b = await collect(page)
            by_mm = {str(e["mmid"]): e for e in b}
            for mm, (e, t, st, ex) in tgts.items():
                if arm != "base" and mm not in applied:
                    continue
                if arm in ("edit-cell", "drop-other"):
                    vic = str(victims[groups[gof[mm]][0]])
                    if (arm == "edit-cell") != (vic == mm):
                        continue          # edit tests the victim; drop tests the survivors
                if mm not in by_mm:
                    continue
                full = t.get("full") or t.get("desc") or {}
                hits = [x for x in b if D._targetable(x) and D.matches(full, x)]
                hm = [str(h["mmid"]) for h in hits]
                post = await page.evaluate("(g)=>window.__rw.atoms([g])", hm) if len(hm) >= 2 else {}
                ve = v_exist(t, mm, b)
                bump(arm, "exist", ve, ex)
                for v, ks in VARIANTS.items():
                    vn = v_new(t, mm, b, st[v], post, ks) if st[v] else ve
                    bump(arm, v, vn, ex)
                    if st[v]:
                        # APPLES TO APPLES: only descriptors that actually HAVE a
                        # record witness. The pooled number above includes the
                        # ~36% that have none and fall back to the ordinal, which
                        # dilutes every rate toward the existing resolver.
                        bump(arm, v + "@has", vn, ex)
                        bump(arm, "exist@" + v, ve, ex)
        finally:
            await ctx.close()
    row["verd"] = {a_: {k: dict(v) for k, v in d.items()} for a_, d in verd.items()}
    return row


def tot(rows, path):
    c = Counter()
    for r in rows:
        d = r
        for p in path:
            d = (d or {}).get(p)
        for k, v in (d or {}).items():
            c[k] += v
    return c


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-win", action="store_true", help="drop the rejected neighbour-window variant")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    if args.no_win:
        VARIANTS.pop("win", None)
    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for i, (name, url) in enumerate(list(SITES)[: args.sites], 1):
            try:
                r = await run_site(browser, name, url, rng)
            except Exception as exc:
                print(f"  [{i:>3}] {name:<22} ERROR {type(exc).__name__}: {str(exc)[:90]}")
                continue
            if not r:
                print(f"  [{i:>3}] {name:<22} skipped")
                continue
            rows.append(r)
            c = r.get("cov") or {}
            print(f"  [{i:>3}] {name:<22} crowds={r.get('crowds', 0):<4} ordinal-bearing={c.get('n', 0):<4} "
                  f"existing-witness={c.get('existing', 0):<4} +text={c.get('text', 0):<4} +attr={c.get('attr', 0):<4}")
        await browser.close()

    sites = [r for r in rows if r.get("cov", {}).get("n")]
    cov = tot(rows, ["cov"])
    n = cov["n"] or 1
    print(f"\n{'=' * 78}\nRECORD-CONTENT WITNESS — {len(rows)} sites loaded, {len(sites)} with ordinal-bearing "
          f"descriptors, {cov['n']} descriptors\n{'=' * 78}")
    print("  (#25: sites contributing a crowd at all -- the corpus is mostly landing pages)")
    top = sorted(sites, key=lambda r: -r["cov"]["n"])[:5]
    print("  top contributors:", ", ".join(f"{r['name']}={r['cov']['n']}" for r in top))
    for label, k in (("existing witness (shipped)", "existing"),
                     ("record TEXT unique (child-of-LCA)", "text"),
                     ("record WINDOW text unique (both neighbours)", "win"),
                     ("record/member ATTR unique", "attr"),
                     ("variant rec = text|attr", "rec_any"), ("variant txt = text only", "txt_any"), ("variant win = win|attr", "win_any"),
                     ("shipped OR rec", "rec_or_shipped"), ("shipped OR win", "win_or_shipped"),
                     ("aria-rowindex/posinset present (positional)", "rowix"),
                     ("no record could be isolated", "no_record")):
        print(f"  {label:<46}{cov[k]:>6}  {cov[k] / n:>7.1%}")
    un = cov["unwit_n"] or 1
    print(f"\n  UNWITNESSED by the shipped witness: {cov['unwit_n']} ({cov['unwit_n'] / n:.1%})")
    for v in VARIANTS:
        print(f"    rescued by variant {v:<4} {cov[v + '_rescue']:>5}  {cov[v + '_rescue'] / un:>7.1%}")
    for v in VARIANTS:
        per = [r["cov"][v + "_rescue"] / r["cov"]["unwit_n"] for r in sites if r["cov"].get("unwit_n")]
        if per:
            print(f"    per-site median rescue ({v}) {statistics.median(per):.1%} over {len(per)} sites")

    print(f"\n  {'arm':<13}{'resolver':<9}{'n':>6}{'CORRECT':>10}{'REFUSED':>10}{'WRONG':>9}"
          f"   | unwitnessed-by-shipped: n / CORRECT / REFUSED / WRONG")
    for arm in ARMS:
        for who in ("exist",) + tuple(VARIANTS):
            c = tot(rows, ["verd", arm, who])
            u = tot(rows, ["verd", arm, who + "_unwit"])
            nn = sum(c.values())
            uu = sum(u.values())
            if not nn:
                continue
            print(f"  {arm:<13}{who:<9}{nn:>6}{c['CORRECT'] / nn:>10.1%}{c['REFUSED'] / nn:>10.1%}{c['WRONG'] / nn:>9.1%}"
                  f"   | {uu:>5} {u['CORRECT'] / max(uu, 1):>6.1%} {u['REFUSED'] / max(uu, 1):>6.1%} {u['WRONG'] / max(uu, 1):>6.1%}")
    print(f"\n  ONLY descriptors that HAVE a record witness (variant rec) -- same targets, both resolvers")
    print(f"  {'arm':<13}{'resolver':<11}{'n':>6}{'CORRECT':>10}{'REFUSED':>10}{'WRONG':>9}")
    for arm in ARMS:
        for who in ("exist@rec", "rec@has", "exist@txt", "txt@has"):
            c = tot(rows, ["verd", arm, who])
            nn = sum(c.values())
            if nn:
                print(f"  {arm:<13}{who:<11}{nn:>6}{c['CORRECT'] / nn:>10.1%}{c['REFUSED'] / nn:>10.1%}{c['WRONG'] / nn:>9.1%}")
    for v in ("rec", "txt"):
        bw = [(r["name"], r["verd"]["base"].get(v, {}).get("WRONG", 0)) for r in rows if r.get("verd")]
        print(f"  base-arm WRONG by site, variant {v} (must be none):", [x for x in bw if x[1]])
    inval = [r["name"] for r in rows if r.get("ruler_valid") is False]
    if inval:
        print(f"\n  ruler invalid (mmid sets differ between loads), arm skipped on: {', '.join(inval)}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "record_witness.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
