"""Q1: does ANY declaration separate "row 3 of the rendered window" from "row 3
of the dataset"?  Q2: what IS the unwitnessable ordinal residue?

MEASURING ONLY. Nothing here is built; the probe reports and exits.

Q1 -- THE QUESTION #83 DID NOT ASK. CLAUDE.md #83 measured
`aria-rowindex`/`aria-posinset` on 3.8% of ordinal-bearing descriptors and
dismissed them as "positional, so they carry no information under a sort". That
dismissal is about RE-SORTS and it is right about them. The VIRTUALISATION case
(#90, OPEN.md item 2) is a different question: a virtualised list's ordinal is
wrong because the crowd is a moving WINDOW, and `aria-setsize` / `aria-rowcount`
declare the DATASET size while `len(hits)` is the WINDOW size. A page that
declares them makes the discrepancy DETECTABLE -- setsize != rendered peers
means "this is a window onto something larger", which is exactly the condition
under which `len(hits) != of` can never fire.

  a  tied crowds (>=2 entries identical in the FULL descriptor -- D.at_level)
  b  ...with aria-posinset/setsize/rowindex/rowcount on the member or its
     nearest [role=row]/[role=option]/[role=listitem] ancestor.  A GENEROUS arm
     (any ancestor within 12 hops) bounds the answer from above, so a narrow
     rule cannot be blamed for a zero.
  c  where setsize/rowcount IS declared, how often it DIFFERS from
     c1 the number of rendered CROWD members (what was asked), and
     c2 the number of rendered PEERS of the same role under the same owner
        (the sounder window signal: a crowd is a tie on identity, not a set, so
        a listbox of 10 options where only 3 share a name gives crowd=3 against
        setsize=10 for a reason that has nothing to do with virtualisation).
  d  crowds inside a declared scroll container.  The predicate is COPIED
     VERBATIM from tools/audit_scroll_window.py so the number is comparable to
     its published 5.9% (PRINCIPLES 17: reuse the definition, do not restate
     it).  That probe keys crowds on tag/role/type/name -- LEVEL 1 of the
     ladder -- so both keyings are reported here.

Q2 -- CLASSIFY THE RESIDUE. #83 reports 52.6% of ordinal-bearing descriptors
unwitnessed by the shipped self+anchor witness and ~36% of all of them in
crowds with "no isolable record". Nobody has said WHAT those are. Buckets, first
match wins, every rule decided from a DECLARATION or from structure:

  tablist          member's role is `tab`, or a [role=tablist] ancestor.  A
                   CAROUSEL has no ARIA role of its own and the only signal
                   would be `aria-roledescription`, which is author PROSE in an
                   arbitrary language -- the wordlist #24 deleted.  So carousels
                   are counted only where they declare a tablist, and that
                   limitation is stated rather than papered over.
  shared-record    2+ crowd members resolve to the SAME declared record node
                   (several controls in one <tr>).  The record cannot
                   discriminate by construction.
  no-record        `el.closest('tr,li,dl,article,figure,fieldset')` is null or
                   is the element -- the collector's OWN record set, read off
                   `recordAtoms` (#83).  Sub-counted by whether the members are
                   siblings of one parent (a flat toolbar/icon run).
  record-identical a record exists, per member, and this member's atoms are all
                   shared -- genuinely duplicate rows.
  record-digits    unique atoms exist but every one of them collapses under
                   digit-masking: the members differ only by a NUMBER.
  record-distinct  unique non-digit text exists (the atoms witness rescues it).

DANGEROUS vs HARMLESS is decided from the data, not asserted: a crowd DIVERGES
when its members differ in any declared consequence -- `href` (property, so
absolute), the form `name` attribute, the live `value` property (#63: those are
the IDL attributes whose property is the live state), or their record text.
Members that are byte-identical in all four are interchangeable as far as
anything the page declares; one that diverges means acting on the wrong member
has a different effect.

METHOD, copied from tools/audit_record_witness.py: frozen HAR replay,
`tools/_extract.py` to pull `_collectInteractivePage` verbatim out of
background.js, mmid identity as the ruler with a per-site validity check, and
EVERY arm from the SAME page load (#19 / MEASUREMENT R3).

  --fire   plant synthetic positives and show every detector catching them,
           plus a negative control it must NOT flag (PRINCIPLES 5)
  --drift  measure the same arm twice and print the floor BEFORE anything else

Run:  .venv/bin/python <this file> --sites 106
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/Users/aryangurav/Desktop/ChromeBridge")
FROZEN = ROOT / "temp" / "frozen"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

from _extract import extract  # noqa: E402
from capture_listings import SITES  # noqa: E402
from core.flows import descriptor as D  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = extract("_collectInteractivePage", BG, verify=True)
TAG_JS = str(ROOT / "extension" / "listener_tag.js")
VIEWPORT = {"width": 1280, "height": 1600}

BUCKETS = ("tablist", "shared-record", "no-record", "record-identical",
           "record-digits", "record-distinct")

# ---------------------------------------------------------------------------
# In-page probe. window.__wd.probe([[mmid,...], ...]) -> {mmid: facts}
# ---------------------------------------------------------------------------
PAGE_JS = r"""
(function () {
  const reg = () => window.__mmidReg;
  const el = (m) => { const r = reg(); const n = r && r.get(String(m));
                      return (n && n.isConnected) ? n : document.querySelector(`[mmid='${m}']`); };

  // Implicit ARIA roles, for the few host elements whose role decides a COUNT.
  // Not a general role map: only what is needed to count peers of a set member.
  const IMPLICIT = { TR: 'row', LI: 'listitem', OPTION: 'option', TABLE: 'table',
                     UL: 'list', OL: 'list', TBODY: 'rowgroup', TD: 'cell', TH: 'columnheader' };
  const roleOf = (n) => {
    if (!n || n.nodeType !== 1) return '';
    const r = (n.getAttribute('role') || '').trim().toLowerCase().split(/\s+/)[0];
    return r || IMPLICIT[n.tagName] || '';
  };
  // The three ancestors the question names, plus the element itself.
  const SET_SEL = '[role=row],[role=option],[role=listitem]';
  const OWNER_SEL = '[role=listbox],[role=list],[role=tree],[role=menu],[role=tablist],' +
                    '[role=grid],[role=table],[role=treegrid],[role=group],[role=rowgroup],' +
                    '[role=feed],[role=radiogroup],[role=menubar],ul,ol,select,table,tbody';
  const GRID_SEL = '[role=grid],[role=table],[role=treegrid],table';

  const attr = (n, k) => { try { const v = n && n.getAttribute && n.getAttribute(k);
                                 return (v == null || v === '') ? null : v; } catch (e) { return null; } };
  const num = (v) => { if (v == null) return null; const n = Number(String(v).trim());
                       return Number.isFinite(n) ? n : null; };

  // Walk UP for an attribute. `limit` 0 = self only, 1 = the SET_SEL ancestor,
  // 99 = the generous arm (any ancestor). Returns [value, source].
  function up(node, k, mode) {
    if (!node) return [null, ''];
    const self = attr(node, k);
    if (self != null) return [self, 'self'];
    if (mode === 'self') return [null, ''];
    if (mode === 'set') {
      const s = node.parentElement && node.parentElement.closest(SET_SEL);
      const v = s ? attr(s, k) : null;
      return v != null ? [v, 'setmember'] : [null, ''];
    }
    let p = node.parentElement, hops = 0;
    while (p && hops++ < 12) { const v = attr(p, k); if (v != null) return [v, 'ancestor#' + hops]; p = p.parentElement; }
    return [null, ''];
  }

  // Rendered peers of the element that CARRIES aria-setsize.
  //
  // THE FIRST VERSION OF THIS COUNTED 277 WHERE THE PAGE RENDERS 20, and it was
  // my bug rather than a finding (#16 / MEASUREMENT R1). mastodon's set members
  // are <article> with NO role attribute, so roleOf() returned '' and the count
  // became "every role-less element under the feed" -- 277 of them, against a
  // declared 20. The page agrees with itself; the probe did not.
  //
  // ARIA says what a set is, so ask it: the rendered size of the set is the
  // number of elements under the owner that declare aria-posinset. That needs no
  // role resolution at all. Only where posinset is absent does it fall back to
  // structural likeness, and that fallback matches TAG AND explicit role
  // together so a role-less host is compared with role-less hosts.
  function peersOf(node) {
    if (!node) return 0;
    const owner = node.parentElement ? (node.parentElement.closest(OWNER_SEL) || node.parentElement) : null;
    if (!owner) return 0;
    try {
      const declared = owner.querySelectorAll('[aria-posinset]').length;
      if (declared) return declared;
      const r = (node.getAttribute('role') || '').trim().toLowerCase();
      const t = node.tagName;
      let n = 0;
      for (const c of owner.querySelectorAll('*'))
        if (c.tagName === t && (c.getAttribute('role') || '').trim().toLowerCase() === r) n++;
      return n;
    } catch (e) { return 0; }
  }
  function rowsOf(node) {
    if (!node) return 0;
    try {
      const s = new Set();
      for (const c of node.querySelectorAll('[role=row],tr')) s.add(c);
      return s.size;
    } catch (e) { return 0; }
  }

  // VERBATIM from tools/audit_scroll_window.py's scrollerOf (PRINCIPLES 17).
  const scrollerOf = (e) => {
    let p = e; let hops = 0;
    while (p && p !== document.body && hops++ < 12) {
      try {
        const cs = getComputedStyle(p);
        const ov = (cs.overflowY || '') + ' ' + (cs.overflow || '');
        if (/auto|scroll/.test(ov) && p.scrollHeight > p.clientHeight + 4) return p;
      } catch (e2) {}
      p = p.parentElement;
    }
    return null;
  };

  const REC_SEL = 'tr,li,dl,article,figure,fieldset';   // the collector's own set

  // #83's STRUCTURAL record, copied from tools/audit_record_witness.py so the
  // two definitions cannot drift (PRINCIPLES 17). The SHIPPED collector uses
  // REC_SEL -- a declared tag list -- and the two are not the same population,
  // which is the point of measuring both.
  const chain = (n) => { const a = []; for (let x = n; x; x = x.parentNode) a.push(x); return a; };
  function lca(nodes) {
    let c = chain(nodes[0]);
    for (const n of nodes.slice(1)) { const s = new Set(chain(n)); c = c.filter((x) => s.has(x)); }
    return c[0] || null;
  }
  function childToward(parent, n) { let x = n; while (x && x.parentNode !== parent) x = x.parentNode; return x; }
  function recordOf(member, members) {
    let S = members, last = null;
    for (let guard = 0; guard < 40; guard++) {
      const L = lca(S); if (!L) return last;
      const c = childToward(L, member);
      if (!c || c === member) return last || member;
      const S2 = S.filter((m) => c.contains(m));
      last = c;
      if (S2.length <= 1) return c;
      if (S2.length === S.length) return c;
      S = S2;
    }
    return last;
  }
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  function textAtoms(root) {
    const out = new Set();
    if (!root) return out;
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

  window.__wd = {
    probe(groups) {
      const out = {};
      for (const g of groups) {
        const nodes = g.map(el);
        const live = nodes.filter(Boolean);
        const lcaRecs = new Map();
        const recIds = new Map();       // record node -> index within this crowd
        const parIds = new Map();
        for (let i = 0; i < g.length; i++) {
          const n = nodes[i];
          if (!n) { out[g[i]] = null; continue; }
          let rec = null;
          try { rec = n.closest(REC_SEL); } catch (e) {}
          if (rec === n) rec = null;
          if (rec && !recIds.has(rec)) recIds.set(rec, recIds.size);
          const par = n.parentElement;
          if (par && !parIds.has(par)) parIds.set(par, parIds.size);

          const fact = { recIdx: rec ? recIds.get(rec) : -1,
                         parIdx: par ? parIds.get(par) : -1 };

          // --- ARIA, two arms: NARROW (self or the named set ancestor) and
          //     GENEROUS (any ancestor within 12 hops).
          for (const [k, short] of [['aria-posinset', 'pos'], ['aria-setsize', 'set'],
                                    ['aria-rowindex', 'rix'], ['aria-rowcount', 'rcn']]) {
            const [vn, sn] = up(n, k, 'set');
            const [vg, sg] = up(n, k, 'any');
            fact[short] = num(vn); fact[short + '_src'] = sn;
            fact[short + 'G'] = num(vg); fact[short + 'G_src'] = sg;
          }
          // Owner counts, from whichever element actually carries the attribute.
          let setCarrier = null;
          if (attr(n, 'aria-setsize') != null) setCarrier = n;
          else { try { const s = n.parentElement && n.parentElement.closest(SET_SEL);
                       if (s && attr(s, 'aria-setsize') != null) setCarrier = s; } catch (e) {} }
          if (!setCarrier && fact.setG != null) {
            let p = n.parentElement, h = 0;
            while (p && h++ < 12) { if (attr(p, 'aria-setsize') != null) { setCarrier = p; break; } p = p.parentElement; }
          }
          fact.peers = setCarrier ? peersOf(setCarrier) : 0;
          fact.carrierRole = setCarrier ? roleOf(setCarrier) : '';

          let gridCarrier = null;
          { let p = n, h = 0;
            while (p && h++ < 13) { if (attr(p, 'aria-rowcount') != null) { gridCarrier = p; break; } p = p.parentElement; } }
          if (!gridCarrier) { try { const gg = n.closest(GRID_SEL); if (gg && attr(gg, 'aria-rowcount') != null) gridCarrier = gg; } catch (e) {} }
          fact.rowsRendered = gridCarrier ? rowsOf(gridCarrier) : 0;

          // --- declared grouping
          fact.roleIsTab = roleOf(n) === 'tab';
          try { fact.inTablist = !!n.closest('[role=tablist]'); } catch (e) { fact.inTablist = false; }

          // --- scroller (verbatim predicate)
          const sc = scrollerOf(n);
          let h = 0;
          try { h = n.getBoundingClientRect().height || 0; } catch (e) {}
          fact.scroll = sc ? { tag: sc.tagName.toLowerCase(), sh: sc.scrollHeight, ch: sc.clientHeight } : null;
          fact.windowed = !!(sc && sc.scrollHeight > sc.clientHeight + Math.max(h, 8));

          // --- declared consequences (#63: property, not attribute)
          let href = '';
          try { href = (n.tagName === 'A' || n.tagName === 'AREA') ? (n.href || '') : ''; } catch (e) {}
          fact.href = href;
          fact.nameAttr = attr(n, 'name') || '';
          let val = '';
          try { val = (typeof n.value === 'string') ? n.value : ''; } catch (e) {}
          fact.val = val;

          // --- EVERY attribute, so "is there ANY declaration" is answered by
          //     enumeration rather than by a list someone thought of. class and
          //     style are excluded as PRESENTATION (#27/#28 took those out of
          //     the paths that decide things); mmid is our own instrumentation.
          const SKIP = { class: 1, style: 1, mmid: 1 };
          const bag = (node) => {
            const o = {};
            if (!node || !node.attributes) return o;
            for (const a of node.attributes) if (!SKIP[a.name]) o[a.name] = a.value;
            return o;
          };
          fact.attrs = bag(n);
          fact.recAttrs = bag(rec);
          // The nearest ancestor within 4 hops carrying any data-* attribute:
          // ag-grid writes row-index/row-id on the ROW, react-virtualized on a
          // wrapper, so the discriminator is often one hop off the control.
          let dAnc = null, p2 = n.parentElement, h2 = 0;
          while (p2 && h2++ < 4) {
            let any = false;
            for (const a of p2.attributes || []) if (/^data-|^row-/.test(a.name)) { any = true; break; }
            if (any) { dAnc = p2; break; }
            p2 = p2.parentElement;
          }
          fact.ancAttrs = bag(dAnc);

          // #83's STRUCTURAL record, beside the shipped DECLARED one. The
          // shipped `recordAtoms` keys on a tag list, so a crowd whose records
          // are <div>s has none; #83 measured the LCA-child record at 43.9%
          // text coverage against what the shipped field actually delivers.
          // IS THIS MEMBER NESTED INSIDE ANOTHER MEMBER OF ITS OWN CROWD?
          // A click bubbles, so an outer and an inner entry that tie on every
          // declared field ARE the same action -- which is exactly why #29's
          // identical-nested-row collapse merges their refs onto one row rather
          // than picking one. Decidable, and the strongest HARMLESS signal
          // available: there is no wrong member to act on.
          let nested = false;
          try {
            for (const o of live) if (o !== n && (o.contains(n) || n.contains(o))) { nested = true; break; }
          } catch (e) {}
          fact.nested = nested;

          let lrec = null;
          try { if (live.length >= 2) lrec = recordOf(n, live); } catch (e) {}
          if (lrec === n) lrec = null;
          if (lrec && !lcaRecs.has(lrec)) lcaRecs.set(lrec, lcaRecs.size);
          fact.lcaIdx = lrec ? lcaRecs.get(lrec) : -1;
          fact.lcaAtoms = lrec ? [...textAtoms(lrec)].slice(0, 60) : [];
          out[g[i]] = fact;
        }
      }
      return out;
    },
  };
  return true;
})()
"""

DIGITS = re.compile(r"[0-9٠-٩۰-۹०-९０-９]+")


def mask(s: str) -> str:
    return DIGITS.sub("#", s)


def crowds_full(entries):
    """Tied crowds on the FULL descriptor -- what build() actually counts."""
    pool = [e for e in entries if D._targetable(e)]
    g = defaultdict(list)
    for e in pool:
        g[json.dumps(D.at_level(e, D.FULL), sort_keys=True)].append(e)
    return [v for v in g.values() if len(v) >= 2]


def crowds_l1(entries):
    """Tied crowds on tag/role/type/name -- audit_scroll_window.py's keying."""
    g = defaultdict(list)
    for e in entries:
        if not e.get("mmid"):
            continue
        g[(e.get("tag"), e.get("role") or "", e.get("type") or "", e.get("name") or "")].append(e)
    return [v for v in g.values() if len(v) >= 2]


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


async def collect(page):
    return await page.evaluate(
        "(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, 'brief'); })()") or []


def q1_for_crowds(crowds, pr, tag):
    """Counts (a)-(d) for one crowd keying."""
    c = Counter()
    ex = []
    for g in crowds:
        mms = [str(e["mmid"]) for e in g]
        facts = [pr.get(m) for m in mms]
        if any(f is None for f in facts):
            c["unresolvable"] += 1
            continue
        c["crowds"] += 1
        c["members"] += len(g)

        narrow = any(f[k] is not None for f in facts for k in ("pos", "set", "rix", "rcn"))
        gen = any(f[k + "G"] is not None for f in facts for k in ("pos", "set", "rix", "rcn"))
        if narrow:
            c["aria_narrow"] += 1
        if gen:
            c["aria_generous"] += 1
        for k in ("pos", "set", "rix", "rcn"):
            if any(f[k] is not None for f in facts):
                c["has_" + k] += 1
            if any(f[k + "G"] is not None for f in facts):
                c["hasG_" + k] += 1

        # (c) dataset-vs-window, two denominators
        sets = [f["set"] if f["set"] is not None else f["setG"] for f in facts]
        sets = [s for s in sets if s is not None]
        if sets:
            c["setsize_crowds"] += 1
            declared = max(sets)
            if declared != len(g):
                c["c1_set_ne_crowd"] += 1
            peers = max((f["peers"] for f in facts), default=0)
            if peers:
                c["setsize_with_peers"] += 1
                if declared != peers:
                    c["c2_set_ne_peers"] += 1
                    # DIRECTION IS THE WHOLE SIGNAL. A window renders FEWER than
                    # the dataset; declared < rendered means the declaration is
                    # per-batch or stale and says nothing about a window.
                    c["c2_set_window" if declared > peers else "c2_set_stale"] += 1
                    if len(ex) < 40:
                        ex.append({"kind": "setsize", "key": tag, "declared": declared,
                                   "peers": peers, "crowd": len(g),
                                   "name": (g[0].get("name") or g[0].get("text") or "")[:34],
                                   "tag": g[0].get("tag")})
        rcs = [f["rcn"] if f["rcn"] is not None else f["rcnG"] for f in facts]
        rcs = [s for s in rcs if s is not None]
        if rcs:
            c["rowcount_crowds"] += 1
            declared = max(rcs)
            if declared != len(g):
                c["c1_rcn_ne_crowd"] += 1
            rows = max((f["rowsRendered"] for f in facts), default=0)
            if rows:
                c["rowcount_with_rows"] += 1
                if declared != rows:
                    c["c2_rcn_ne_rows"] += 1
                    c["c2_rcn_window" if declared > rows else "c2_rcn_stale"] += 1
                    if len(ex) < 40:
                        ex.append({"kind": "rowcount", "key": tag, "declared": declared,
                                   "peers": rows, "crowd": len(g),
                                   "name": (g[0].get("name") or g[0].get("text") or "")[:34],
                                   "tag": g[0].get("tag")})

        # (d) scroller, first member -- audit_scroll_window.py's own rule
        if facts[0]["scroll"]:
            c["in_scroller"] += 1
            if facts[0]["windowed"]:
                c["windowed"] += 1
        if all(f["scroll"] for f in facts):
            c["in_scroller_all"] += 1
            if all(f["windowed"] for f in facts):
                c["windowed_all"] += 1
    return c, ex


def classify(mm, mms, pr, by_mm):
    f = pr[mm]
    if f["roleIsTab"] or f["inTablist"]:
        return "tablist", {}
    if f["recIdx"] >= 0 and sum(1 for o in mms if pr[o] and pr[o]["recIdx"] == f["recIdx"]) > 1:
        return "shared-record", {}
    if f["recIdx"] < 0:
        flat = (f["parIdx"] >= 0
                and sum(1 for o in mms if pr[o] and pr[o]["parIdx"] == f["parIdx"]) == len(mms))
        # Does #83's STRUCTURAL record exist where the shipped DECLARED one does
        # not, and does it carry text no other member has? That is the share of
        # this bucket the shipped tag list is leaving on the table.
        lca_u = False
        if f["lcaIdx"] >= 0 and sum(1 for o in mms if pr[o] and pr[o]["lcaIdx"] == f["lcaIdx"]) == 1:
            mine = set(f["lcaAtoms"] or [])
            others = set()
            for o in mms:
                if o != mm and pr[o]:
                    others |= set(pr[o]["lcaAtoms"] or [])
            lca_u = bool(mine - others)
        return "no-record", {"flat": flat, "lca_unique": lca_u, "lca": f["lcaIdx"] >= 0}
    mine = set(by_mm[mm].get("recordAtoms") or [])
    others = set()
    for o in mms:
        if o != mm:
            others |= set(by_mm.get(o, {}).get("recordAtoms") or [])
    u = mine - others
    if not u:
        return "record-identical", {}
    if not ({mask(x) for x in mine} - {mask(x) for x in others}):
        return "record-digits", {}
    return "record-distinct", {}


def discriminating_attrs(mms, pr):
    """Which attribute NAMES take a different value on every member?

    The exhaustive form of "is there ANY declaration": rather than a list of
    four ARIA attributes someone thought of, enumerate every attribute the page
    actually wrote on the member, on its declared record root, and on the
    nearest data-* bearing ancestor, and ask which of them separate the crowd.
    Returns {scope: {attr-name: 'all'|'some'}}.

    'all'  = every member carries the name and every value is distinct -- the
             shape a safeguard could key on.
    'some' = the name is present on some members only, or values are distinct
             but not on every member. Reported separately because a partial
             declaration cannot name one member of a crowd of N.
    """
    out = {}
    for scope in ("attrs", "recAttrs", "ancAttrs"):
        res = {}
        names = set()
        for m in mms:
            names |= set((pr[m] or {}).get(scope) or {})
        for nm in names:
            vals = [((pr[m] or {}).get(scope) or {}).get(nm) for m in mms]
            present = [v for v in vals if v not in (None, "")]
            if len(present) < 2:
                continue
            if len(set(present)) != len(present):
                continue                       # a repeated value names nobody
            res[nm] = "all" if len(present) == len(mms) else "some"
        if res:
            out[scope] = res
    return out


def diverges(mms, pr, by_mm, attrs_all=False):
    """Does the page DECLARE that acting on the wrong member differs?

    THE FIRST VERSION MANUFACTURED ITS OWN ANSWER. `record` was taken from the
    collector's `recordAtoms`, which is null for every member of the `no-record`
    bucket BY DEFINITION -- so the largest bucket scored 0.8% divergence for a
    reason that had nothing to do with the pages. A signal that cannot fire on
    the population it is asked about is PRINCIPLES 15, and the conclusion it was
    about to support ("the biggest bucket is harmless") is exactly the flattering
    shape #16 exists for.

    `record` now falls back to #83's STRUCTURAL record text where the shipped
    declared record is absent, so the component can fire everywhere; and the
    exhaustive attribute scan is folded in, so "the page declares nothing that
    separates these" means every declaration was looked at, not four of them.
    """
    def distinct(vals):
        return len({v for v in vals if v}) > 1
    hrefs = [pr[m]["href"] for m in mms if pr[m]]
    names = [pr[m]["nameAttr"] for m in mms if pr[m]]
    vals = [pr[m]["val"] for m in mms if pr[m]]
    recs = []
    for m in mms:
        a = by_mm.get(m, {}).get("recordAtoms")
        if not a:
            a = (pr[m] or {}).get("lcaAtoms") or []
        recs.append("\u0001".join(a))
    return {"href": distinct(hrefs), "nameAttr": distinct(names),
            "value": distinct(vals), "record": distinct(recs), "attr": attrs_all}


async def run_site(browser, name, url, per_site, rng, verbose=True):
    ctx, page = await load(browser, name, url)
    if not page:
        return None
    try:
        await page.evaluate(PAGE_JS)
        ents = await collect(page)
        if len(ents) < 5:
            return None
        cfull, cl1 = crowds_full(ents), crowds_l1(ents)
        all_groups = [[str(e["mmid"]) for e in g] for g in cfull] + \
                     [[str(e["mmid"]) for e in g] for g in cl1]
        pr = await page.evaluate("(g)=>window.__wd.probe(g)", all_groups) if all_groups else {}
        # mmid-identity ruler validity: everything we probed must have resolved
        probed = {m for g in all_groups for m in g}
        unresolved = sum(1 for m in probed if pr.get(m) is None)
    finally:
        await ctx.close()

    row = {"name": name, "entries": len(ents), "n_full": len(cfull), "n_l1": len(cl1),
           "unresolved_probe": unresolved}
    q1f, exf = q1_for_crowds(cfull, pr, "full")
    q1l, exl = q1_for_crowds(cl1, pr, "l1")
    row["q1_full"] = dict(q1f)
    row["q1_l1"] = dict(q1l)
    row["q1_examples"] = exf + exl

    # ---- Q2: ordinal-bearing descriptors, sampled per site (#83's 120 cap)
    by_mm = {str(e["mmid"]): e for e in ents}
    members = [(e, g) for g in cfull for e in g]
    if len(members) > per_site:
        members = rng.sample(members, per_site)
    gof = {}
    for g in cfull:
        for e in g:
            gof[str(e["mmid"])] = [str(x["mmid"]) for x in g]

    b = Counter()
    rows_q2 = []
    for e, _g in members:
        mm = str(e["mmid"])
        if pr.get(mm) is None:
            continue
        t = D.build(e, ents)
        if t.get("of") is None:
            continue
        b["ordinal"] += 1
        has_w = bool(t.get("witness"))
        has_a = bool(t.get("atoms"))
        b["witnessed"] += has_w
        b["atoms"] += has_a
        b["either"] += (has_w or has_a)
        if has_w:
            continue
        b["unwit"] += 1
        b["unwit_no_atoms"] += (not has_a)
        mms = gof[mm]
        bucket, extra = classify(mm, mms, pr, by_mm)
        da_pre = discriminating_attrs(mms, pr)
        attrs_all = any(h == "all" for names in da_pre.values() for h in names.values())
        div = diverges(mms, pr, by_mm, attrs_all)
        anydiv = any(div.values())
        b["B_" + bucket] += 1
        if not has_a:
            b["BN_" + bucket] += 1
        if anydiv:
            b["DIV_" + bucket] += 1
        if extra.get("flat"):
            b["flat_no_record"] += 1
        if extra.get("lca"):
            b["no_record_has_lca"] += 1
        if extra.get("lca_unique"):
            b["no_record_lca_unique"] += 1
        # Which attribute NAMES separate this crowd, if any?
        for scope, names in da_pre.items():
            for anm, how in names.items():
                b[f"attr|{scope}|{anm}|{how}"] += 1
        if attrs_all:
            b["any_attr_all"] += 1
        elif da_pre:
            b["any_attr_some"] += 1
        else:
            b["no_attr_at_all"] += 1
        # Per-component divergence, so "nothing separates them" can be audited
        for comp, on in div.items():
            if on:
                b["div_" + comp] += 1
                b[f"divb_{bucket}_{comp}"] += 1
        if not anydiv:
            b["NODIV_" + bucket] += 1
        if not D._name_of(e):
            b["unnamed"] += 1
        if (e.get("role") or "") == "media":
            b["media"] += 1
        # INTERCHANGEABILITY, two decidable forms.
        # nested  -- another crowd member contains this one, so a click on
        #            either reaches the same handler by bubbling (#29).
        # samebox -- identical x/y/w/h, i.e. the same pixels right now.
        #            Geometry is excluded from IDENTITY because it DRIFTS
        #            between loads (#23: 110px, #25: 1097px); this is not a
        #            stability claim, it asks "are these the same spot in THIS
        #            observation", which a single page load answers exactly.
        box = (e.get("x"), e.get("y"), e.get("w"), e.get("h"))
        same_box = any(o != mm and (by_mm[o].get("x"), by_mm[o].get("y"),
                                    by_mm[o].get("w"), by_mm[o].get("h")) == box
                       for o in mms if o in by_mm)
        if pr[mm].get("nested"):
            b["nested"] += 1
            b["nested_" + bucket] += 1
        if same_box:
            b["samebox"] += 1
            b["samebox_" + bucket] += 1
        if pr[mm].get("nested") or same_box:
            b["interchangeable"] += 1
            b["ichg_" + bucket] += 1
            if not anydiv:
                b["ichg_nodiv_" + bucket] += 1
        f = pr[mm]
        if f["scroll"]:
            b["unwit_in_scroller"] += 1
            if f["windowed"]:
                b["unwit_windowed"] += 1
        rows_q2.append({"mmid": mm, "bucket": bucket, "atoms": has_a,
                        "div": div, "anydiv": anydiv, "of": t.get("of"),
                        "tag": e.get("tag"), "role": e.get("role") or "",
                        "name": (D._name_of(e) or "")[:46],
                        "sect": e.get("section") or "",
                        "windowed": bool(f["windowed"])})
    row["q2"] = dict(b)
    row["q2_rows"] = rows_q2
    if verbose:
        print(f"  {name:<22} ents={len(ents):<5} crowdsFULL={len(cfull):<4} crowdsL1={len(cl1):<4} "
              f"ord={b['ordinal']:<4} unwit={b['unwit']:<4} ariaN={q1f['aria_narrow']:<3} "
              f"windowed={q1f['windowed']}")
    return row


def sites_list(n):
    out = []
    for s in SITES:
        out.append((s[0], s[1]))
        if len(out) >= n:
            break
    return out


def pooled(rows, key):
    c = Counter()
    for r in rows:
        for k, v in (r.get(key) or {}).items():
            c[k] += v
    return c


# ---------------------------------------------------------------------------
# FIRING PROOF
# ---------------------------------------------------------------------------
FIXTURE = """<!doctype html><html><body>
<h1>fixture</h1>

<!-- POSITIVE 1: a virtualised listbox. 10 rendered options of a 200-row
     dataset, inside a declared scroller with content taller than its box. -->
<div id="vlist" style="height:120px;overflow:auto">
  <div style="height:4000px">
    <div role="listbox" aria-label="Pick">
      %OPTS%
    </div>
  </div>
</div>

<!-- POSITIVE 2: a grid declaring 500 rows and rendering 12. -->
<div role="grid" aria-rowcount="500" aria-label="Ledger" id="grid">
  %ROWS%
</div>

<!-- NEGATIVE CONTROL: a plain list of identical buttons, no aria-*, not in a
     scroller.  Nothing here may be reported as a window. -->
<ul id="plain">
  <li><button>Go</button></li><li><button>Go</button></li>
  <li><button>Go</button></li><li><button>Go</button></li>
</ul>

<!-- Q2 bucket fixtures, one crowd per bucket -->
<div role="tablist" id="tabs">
  <button role="tab" aria-label="Tab">A</button><button role="tab" aria-label="Tab">B</button>
</div>
<table id="shared"><tr><td><button name="x">Act</button><button name="x">Act</button></td></tr></table>
<div id="toolbar"><button aria-label="Tool">1</button><button aria-label="Tool">2</button>
  <button aria-label="Tool">3</button></div>
<ul id="dupes"><li>Same row <button aria-label="Dup">Open</button></li>
  <li>Same row <button aria-label="Dup">Open</button></li></ul>
<ul id="paged"><li>Page 1 <button aria-label="Num">Open</button></li>
  <li>Page 2 <button aria-label="Num">Open</button></li></ul>
<ul id="distinct"><li>Acme Ltd <button aria-label="Del">Delete</button></li>
  <li>Globex Inc <button aria-label="Del">Delete</button></li></ul>
<!-- a NESTED pair: same tag, same name, one inside the other.  A click on
     either reaches the same handler, so there is no wrong member. -->
<div id="nest"><span tabindex="0" onclick="void 0" aria-label="Wrap"><span tabindex="0"
  onclick="void 0" aria-label="Wrap">Inner</span></span></div>
</body></html>"""


async def fire(browser):
    opts = "\n".join(
        f'<div role="option" aria-setsize="200" aria-posinset="{i+1}" '
        f'aria-label="Row" style="height:30px">Row</div>' for i in range(10))
    rows = "\n".join(
        f'<div role="row" aria-rowindex="{i+1}"><span role="gridcell">'
        f'<button aria-label="Edit">Edit</button></span></div>' for i in range(12))
    html = FIXTURE.replace("%OPTS%", opts).replace("%ROWS%", rows)
    ctx = await browser.new_context(viewport=VIEWPORT)
    await ctx.add_init_script(path=TAG_JS)
    await ctx.route("http://fixture.test/**", lambda r: asyncio.ensure_future(
        r.fulfill(status=200, content_type="text/html", body=html)))
    page = await ctx.new_page()
    await page.goto("http://fixture.test/x", wait_until="domcontentloaded")
    await page.wait_for_timeout(400)
    await page.evaluate(PAGE_JS)
    ents = await collect(page)
    cfull = crowds_full(ents)
    groups = [[str(e["mmid"]) for e in g] for g in cfull]
    pr = await page.evaluate("(g)=>window.__wd.probe(g)", groups)
    q1, ex = q1_for_crowds(cfull, pr, "fixture")
    by_mm = {str(e["mmid"]): e for e in ents}

    print("\n" + "=" * 78)
    print("FIRING PROOF (PRINCIPLES 5) -- a planted positive, and a negative control")
    print("=" * 78)
    print(f"  entries={len(ents)}  crowds(FULL)={len(cfull)}")
    print(f"  Q1 (a) crowds                      {q1['crowds']}")
    print(f"  Q1 (b) with aria, narrow / generous {q1['aria_narrow']} / {q1['aria_generous']}")
    print(f"  Q1 (c1) setsize != crowd size       {q1['c1_set_ne_crowd']}")
    print(f"  Q1 (c2) setsize != rendered peers   {q1['c2_set_ne_peers']}  "
          f"(of {q1['setsize_with_peers']} measurable)")
    print(f"  Q1 (c1) rowcount != crowd size      {q1['c1_rcn_ne_crowd']}")
    print(f"  Q1 (c2) rowcount != rendered rows   {q1['c2_rcn_ne_rows']}  "
          f"(of {q1['rowcount_with_rows']} measurable)")
    print(f"  Q1 (d) in scroller / WINDOWED       {q1['in_scroller']} / {q1['windowed']}")
    for e in ex:
        print(f"         e.g. {e['kind']} declared={e['declared']} rendered-peers={e['peers']} "
              f"crowd={e['crowd']} <{e['tag']}> {e['name']!r}")

    got = {}
    for g, mms in zip(cfull, groups):
        for e in g:
            mm = str(e["mmid"])
            if pr.get(mm) is None:
                continue
            t = D.build(e, ents)
            if t.get("of") is None:
                continue
            bk, _x = classify(mm, mms, pr, by_mm)
            da_ = discriminating_attrs(mms, pr)
            aa_ = any(h == "all" for ns in da_.values() for h in ns.values())
            got.setdefault(bk, []).append((e.get("tag"), D._name_of(e),
                                           any(diverges(mms, pr, by_mm, aa_).values()),
                                           bool(pr[mm]["windowed"])))
    print("\n  Q2 buckets caught on the fixture (each crowd was planted for one):")
    for bk in BUCKETS:
        v = got.get(bk, [])
        print(f"    {bk:<18} {len(v):>3}   {v[:2]}")
    missing = [b for b in BUCKETS if b not in got]
    plain = [v for bk, vs in got.items() for v in vs if v[1] == "Go"]
    print(f"\n  buckets with no planted positive: {missing or 'NONE'}")
    print(f"  NEGATIVE CONTROL -- the plain <ul> of identical buttons:")
    print(f"    reported as windowed: {sum(1 for v in plain if v[3])} (must be 0)")
    nested = sum(1 for g, mms in zip(cfull, groups) for m in mms
                 if pr.get(m) and pr[m].get("nested"))
    wraps = sum(1 for g in cfull for e in g if D._name_of(e) == "Wrap")
    print(f"  NESTED detector: planted a same-tag nested pair -> crowd members "
          f"seen={wraps}, flagged nested={nested} (must be >0 if seen=2)")
    await ctx.close()
    return not missing


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", type=int, default=106)
    ap.add_argument("--per-site", type=int, default=120)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--fire", action="store_true")
    ap.add_argument("--drift", type=int, default=0,
                    help="run the FIRST N sites twice and print the floor before anything else")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    rng = random.Random(args.seed)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        if args.fire:
            ok = await fire(browser)
            await browser.close()
            return 0 if ok else 1

        # ---- DRIFT CONTROL FIRST (MEASUREMENT R3)
        if args.drift:
            print("=" * 78)
            print(f"DRIFT CONTROL -- the SAME arm measured twice, {args.drift} sites, taken FIRST")
            print("=" * 78)
            passes = []
            for rep in (1, 2):
                rows = []
                for nm, u in sites_list(args.drift):
                    try:
                        r = await run_site(browser, nm, u, args.per_site,
                                           random.Random(args.seed), verbose=False)
                    except Exception:
                        r = None
                    if r:
                        rows.append(r)
                passes.append(rows)
                print(f"  pass {rep}: {len(rows)} sites loaded")
            a, b = passes
            ka = {r["name"]: r for r in a}
            kb = {r["name"]: r for r in b}
            both = sorted(set(ka) & set(kb))
            fields = [("crowds(FULL)", lambda r: r["n_full"]),
                      ("ordinal-bearing", lambda r: r["q2"].get("ordinal", 0)),
                      ("unwitnessed", lambda r: r["q2"].get("unwit", 0)),
                      ("aria narrow crowds", lambda r: r["q1_full"].get("aria_narrow", 0)),
                      ("windowed crowds", lambda r: r["q1_full"].get("windowed", 0))]
            print(f"  {len(both)} sites in both passes")
            for lbl, fn in fields:
                xa = sum(fn(ka[n]) for n in both)
                xb = sum(fn(kb[n]) for n in both)
                same = sum(1 for n in both if fn(ka[n]) == fn(kb[n]))
                d = (abs(xb - xa) / xa * 100) if xa else 0.0
                print(f"    {lbl:<22} {xa:>6} -> {xb:>6}   delta {d:>5.2f}%   "
                      f"identical on {same}/{len(both)} sites")
            bk = Counter()
            for n in both:
                for key in BUCKETS:
                    bk["a_" + key] += ka[n]["q2"].get("B_" + key, 0)
                    bk["b_" + key] += kb[n]["q2"].get("B_" + key, 0)
            print("    bucket counts pass1 -> pass2:",
                  {k: (bk['a_' + k], bk['b_' + k]) for k in BUCKETS})
            print()

        rows = []
        skipped = []
        print("=" * 78)
        print(f"MEASURING {args.sites} frozen sites")
        print("=" * 78)
        for nm, u in sites_list(args.sites):
            try:
                r = await run_site(browser, nm, u, args.per_site, rng)
            except Exception as exc:
                print(f"  {nm:<22} ERROR {type(exc).__name__}: {str(exc)[:70]}")
                skipped.append((nm, type(exc).__name__))
                continue
            if not r:
                skipped.append((nm, "no-render"))
                continue
            rows.append(r)
        await browser.close()

    out = Path(args.out or (Path(__file__).parent / "window_declarations.json"))
    out.write_text(json.dumps({"rows": rows, "skipped": skipped}, indent=1), encoding="utf-8")
    report(rows, skipped)
    print(f"\n  raw rows: {out}")
    return 0


def report(rows, skipped):
    qf = pooled(rows, "q1_full")
    ql = pooled(rows, "q1_l1")
    q2 = pooled(rows, "q2")
    nsites = len(rows)
    print(f"\n{'=' * 78}\nQ1 -- WINDOW-vs-DATASET DECLARATIONS   ({nsites} sites loaded, "
          f"{len(skipped)} did not render)\n{'=' * 78}")
    print(f"  {'':<48}{'FULL-desc':>12}{'tag/role/type/name':>22}")
    pairs = [("(a) tied crowds (>=2 members)", "crowds"),
             ("    members in them", "members"),
             ("(b) aria-* NARROW (self / row|option|listitem anc.)", "aria_narrow"),
             ("(b) aria-* GENEROUS (any ancestor, 12 hops)", "aria_generous"),
             ("      aria-posinset", "has_pos"), ("      aria-setsize", "has_set"),
             ("      aria-rowindex", "has_rix"), ("      aria-rowcount", "has_rcn"),
             ("      ...generous posinset", "hasG_pos"), ("      ...generous setsize", "hasG_set"),
             ("      ...generous rowindex", "hasG_rix"), ("      ...generous rowcount", "hasG_rcn"),
             ("(c) crowds where setsize is declared", "setsize_crowds"),
             ("    c1: setsize != crowd size", "c1_set_ne_crowd"),
             ("    ...of which peers measurable", "setsize_with_peers"),
             ("    c2: setsize != rendered peers", "c2_set_ne_peers"),
             ("      c2 DIRECTION: declared > rendered (a WINDOW)", "c2_set_window"),
             ("      c2 DIRECTION: declared < rendered (stale/batched)", "c2_set_stale"),
             ("(c) crowds where rowcount is declared", "rowcount_crowds"),
             ("    c1: rowcount != crowd size", "c1_rcn_ne_crowd"),
             ("    ...of which rendered rows measurable", "rowcount_with_rows"),
             ("    c2: rowcount != rendered rows", "c2_rcn_ne_rows"),
             ("      c2 DIRECTION: declared > rendered (a WINDOW)", "c2_rcn_window"),
             ("      c2 DIRECTION: declared < rendered (stale/batched)", "c2_rcn_stale"),
             ("(d) in a declared scroller (1st member)", "in_scroller"),
             ("(d) ...and genuinely WINDOWED", "windowed"),
             ("(d) in a scroller, ALL members", "in_scroller_all"),
             ("(d) ...and all WINDOWED", "windowed_all"),
             ("    crowd members the probe could not resolve", "unresolvable")]
    for lbl, k in pairs:
        print(f"  {lbl:<48}{qf[k]:>12}{ql[k]:>22}")

    ns = sum(1 for r in rows if r["q1_full"].get("aria_narrow"))
    ng = sum(1 for r in rows if r["q1_full"].get("aria_generous"))
    nw = sum(1 for r in rows if r["q1_full"].get("windowed"))
    nc2 = sum(1 for r in rows if r["q1_full"].get("c2_set_ne_peers") or r["q1_full"].get("c2_rcn_ne_rows"))
    print(f"\n  PER-SITE DISTRIBUTION (#25 -- a pooled number over component demos is not the population)")
    print(f"    sites with >=1 crowd                      {sum(1 for r in rows if r['n_full']):>4} / {nsites}")
    print(f"    sites with ANY narrow aria-* crowd        {ns:>4} / {nsites}")
    print(f"    sites with ANY generous aria-* crowd      {ng:>4} / {nsites}")
    print(f"    sites with ANY window-vs-dataset mismatch {nc2:>4} / {nsites}")
    print(f"    sites with ANY windowed crowd             {nw:>4} / {nsites}")
    top = sorted(rows, key=lambda r: -r["q1_full"].get("aria_generous", 0))[:8]
    print("    top aria-bearing sites:",
          ", ".join(f"{r['name']}={r['q1_full'].get('aria_generous',0)}/{r['n_full']}"
                    for r in top if r["q1_full"].get("aria_generous")) or "(none)")
    topw = sorted(rows, key=lambda r: -r["q1_full"].get("windowed", 0))[:8]
    print("    top windowed sites:",
          ", ".join(f"{r['name']}={r['q1_full'].get('windowed',0)}/{r['n_full']}"
                    for r in topw if r["q1_full"].get("windowed")) or "(none)")
    exs = [e for r in rows for e in r.get("q1_examples", []) if e["key"] == "full"][:8]
    for e in exs:
        print(f"      mismatch e.g. {e['kind']} declared={e['declared']} "
              f"rendered={e['peers']} crowd={e['crowd']} <{e['tag']}> {e['name']!r}")

    print(f"\n{'=' * 78}\nQ2 -- THE UNWITNESSED ORDINAL RESIDUE\n{'=' * 78}")
    n = q2["ordinal"] or 1
    print(f"  ordinal-bearing descriptors sampled        {q2['ordinal']}")
    print(f"    with the shipped self+anchor witness     {q2['witnessed']:>6}  {q2['witnessed']/n:>7.1%}")
    print(f"    with record-content atoms (#83, shipped) {q2['atoms']:>6}  {q2['atoms']/n:>7.1%}")
    print(f"    with EITHER                              {q2['either']:>6}  {q2['either']/n:>7.1%}")
    print(f"    UNWITNESSED by self+anchor (#83's 52.6%) {q2['unwit']:>6}  {q2['unwit']/n:>7.1%}")
    print(f"    ...and no atoms either (truly nothing)   {q2['unwit_no_atoms']:>6}  "
          f"{q2['unwit_no_atoms']/n:>7.1%}")
    u = q2["unwit"] or 1
    un = q2["unwit_no_atoms"] or 1
    print(f"\n  {'bucket':<18}{'n':>6}{'share':>8}   {'no-atoms':>9}{'share':>8}   "
          f"{'DIVERGES':>14}   {'NOTHING separates':>18}")
    for bk in BUCKETS:
        v, vn, dv = q2["B_" + bk], q2["BN_" + bk], q2["DIV_" + bk]
        nd = q2["NODIV_" + bk]
        print(f"  {bk:<18}{v:>6}{v/u:>8.1%}   {vn:>9}{vn/un:>8.1%}   {dv:>7} {dv/max(v,1):>6.1%}"
              f"   {nd:>10} {nd/max(v,1):>6.1%}")
    print(f"  {'TOTAL':<18}{u:>6}{1.0:>8.1%}   {un:>9}{1.0:>8.1%}"
          f"   {q2['DIV_tablist']+q2['DIV_shared-record']+q2['DIV_no-record']+q2['DIV_record-identical']+q2['DIV_record-digits']+q2['DIV_record-distinct']:>7}")
    print(f"\n  INTERCHANGEABLE BY CONSTRUCTION -- there is no wrong member to act on")
    print(f"    {'bucket':<18}{'nested':>8}{'same box':>10}{'either':>9}{'share':>8}"
          f"{'either AND nothing diverges':>30}")
    for bk in BUCKETS:
        v = q2["B_" + bk] or 1
        print(f"    {bk:<18}{q2['nested_'+bk]:>8}{q2['samebox_'+bk]:>10}{q2['ichg_'+bk]:>9}"
              f"{q2['ichg_'+bk]/v:>8.1%}{q2['ichg_nodiv_'+bk]:>30}")
    print(f"    {'TOTAL':<18}{q2['nested']:>8}{q2['samebox']:>10}{q2['interchangeable']:>9}"
          f"{q2['interchangeable']/u:>8.1%}")

    print(f"\n  WHICH component fires (a member may trip several):")
    for comp in ("href", "nameAttr", "value", "record", "attr"):
        print(f"    {comp:<10}{q2['div_'+comp]:>7}  {q2['div_'+comp]/u:>7.1%}")
    print(f"  per bucket, which component fires:")
    for bk in BUCKETS:
        bits = ", ".join(f"{c}={q2[f'divb_{bk}_{c}']}" for c in
                         ("href", "nameAttr", "value", "record", "attr")
                         if q2[f"divb_{bk}_{c}"])
        print(f"    {bk:<18} {bits or '(none)'}")
    print(f"\n    of the no-record bucket ({q2['B_no-record']}):")
    print(f"      members in a FLAT sibling run (one parent)          {q2['flat_no_record']}")
    print(f"      an LCA-structural record exists (#83's definition)  {q2['no_record_has_lca']}")
    print(f"      ...and its text is UNIQUE to this member            {q2['no_record_lca_unique']}"
          f"   <- the shipped tag-list record misses these")
    print(f"    composition of the residue: unnamed {q2['unnamed']}, role=media {q2['media']}")
    print(f"    unwitnessed descriptors inside a scroller: {q2['unwit_in_scroller']}"
          f"  WINDOWED: {q2['unwit_windowed']}  ({q2['unwit_windowed']/u:.1%} of unwitnessed)")

    print(f"\n  IS THERE *ANY* ATTRIBUTE THAT SEPARATES THE CROWD?  (exhaustive, not a list)")
    print(f"    at least one attribute distinct on EVERY member  {q2['any_attr_all']:>6}  "
          f"{q2['any_attr_all']/u:>7.1%}")
    print(f"    only a PARTIAL one (present on some members)     {q2['any_attr_some']:>6}  "
          f"{q2['any_attr_some']/u:>7.1%}")
    print(f"    nothing at all                                   {q2['no_attr_at_all']:>6}  "
          f"{q2['no_attr_at_all']/u:>7.1%}")
    names = Counter()
    for k, v in q2.items():
        if k.startswith("attr|") and k.endswith("|all"):
            _p, scope, anm, _h = k.split("|")
            names[(scope, anm)] += v
    print(f"    top attribute names distinct on every member (scope, name, n):")
    for (scope, anm), v in names.most_common(18):
        print(f"      {scope:<9} {anm:<28} {v:>6}")

    # Examples, per bucket
    print(f"\n  REPRESENTATIVE EXAMPLES (site / tag / role / name / crowd size / diverges)")
    seen = defaultdict(list)
    for r in rows:
        for q in r.get("q2_rows", []):
            if len(seen[q["bucket"]]) < 6:
                seen[q["bucket"]].append((r["name"], q))
    for bk in BUCKETS:
        print(f"    {bk}:")
        for nm, q in seen[bk][:4]:
            print(f"      {nm:<18} <{q['tag']}{' role='+q['role'] if q['role'] else ''}> "
                  f"{q['name']!r} of={q['of']} diverge={''.join(k[0] for k,v in q['div'].items() if v) or '-'}")
    # Per-site bucket spread
    print(f"\n  PER-SITE bucket spread (sites contributing each bucket):")
    for bk in BUCKETS:
        ns_ = sum(1 for r in rows if r["q2"].get("B_" + bk))
        tops = sorted(rows, key=lambda r: -r["q2"].get("B_" + bk, 0))[:4]
        print(f"    {bk:<18} on {ns_:>3} sites   top: "
              + ", ".join(f"{t['name']}={t['q2'].get('B_'+bk,0)}" for t in tops if t['q2'].get('B_'+bk)))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
