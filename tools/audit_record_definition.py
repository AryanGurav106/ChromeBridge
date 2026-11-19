"""What IS a record? The shipped answer and the measured answer are different.

#83 shipped `recordAtoms` -- the text of the record a crowd member sits in --
and published 43.9% coverage, 69.0% shipped-OR-record, and a re-sort WRONG rate
falling 11.6% -> 0.4%. CLAUDE.md #99 then recorded that the number measured and
the code that shipped use DIFFERENT definitions and that reconciling them is
MEASURE FIRST. This is that measurement.

THREE DIVERGENCES, and they are orthogonal, so a two-arm A/B cannot attribute
anything. They are measured as a factorial instead:

  A  WHAT THE RECORD IS
       shipped  extension/background.js:10089 --
                `el.closest('tr,li,dl,article,figure,fieldset')`, a TAG LIST.
       probe    tools/audit_record_witness.py `recordOf` -- the child of the
                tied crowd's lowest common ancestor, recursed until the member
                stands alone. STRUCTURAL, no vocabulary.
     A tag list only finds a record in <tr>/<li> markup. Most modern apps build
     rows from <div>s, which is where this feature actually runs.

  B  WHETHER HIDDEN TEXT COUNTS
       shipped  a bare TreeWalker over every text node. No visibility test, no
                SCRIPT/STYLE/TEMPLATE exclusion.
       probe    skips SCRIPT/STYLE/NOSCRIPT/TEMPLATE and anything failing
                `checkVisibility({visibilityProperty: true})`.
     #37 is the precedent: a non-rendered subtree donates its ENTIRE text -- a
     closed mega-menu gave one eBay nav item 339 characters, 26.3% of a
     listing. An atom nobody can see witnesses something the user cannot
     verify, and it stops matching when that subtree's state changes.

  C  THE CAP
       shipped  40 distinct text atoms, then img[alt] up to 48.
       probe    uncapped.
     A confound, not a design choice anyone argued for: the bigger the record
     the more the cap bites, so it is entangled with A and has to be separated
     or the A column is wrong.

FIVE CELLS, ALL FROM ONE PAGE LOAD so run-order drift cannot align with the
arm (#19 / MEASUREMENT R3):

    tag_raw    TAG + no filter + cap40      == SHIPPED
    tag_vis    TAG + filter   + cap40       isolates B
    lca_raw    LCA + no filter + cap40      isolates A
    lca_vis    LCA + filter   + cap40       A+B
    lca_vis_nc LCA + filter   + uncapped    == the PROBE's definition (A+B+C)

THE PARITY ASSERT IS THE LOAD-BEARING PART. `tag_raw` is a SECOND SPELLING of
`recordAtoms`, and rule 17 says a second spelling drifts. Every member's
`tag_raw` is compared against the collector's own field and any mismatch is
reported as `parity_bad`. A probe whose baseline cell disagrees with the
product measures a record nothing builds -- which is the defect #99 reports
about audit_record_witness.py, so reproducing it here would be funny once.

MUTATIONS ARE APPLIED TO THE DOM, NOT TO THE ENTRY LIST, and that is not a
style preference. `recordAtoms` is a FIELD ON AN ENTRY, so an entry-level
permutation (audit_flow_resolve.py's `mut_reorder` / `mut_resort`) carries the
witness along with the logical element by construction and a content witness is
trivially CORRECT. Only a DOM mutation followed by a re-collect re-derives the
atoms from the page, which is what replay actually does.

SCORED THROUGH THE REAL RESOLVER. `core.flows.descriptor.resolve` is called
unchanged; only `recordAtoms` is substituted per cell. So this measures the
DEFINITION, never a reimplementation of the resolver (rule 17 again).

Usage:
    python tools/audit_record_definition.py --selftest      # the firing proof
    python tools/audit_record_definition.py --sites 40
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "temp" / "frozen"
OUT = ROOT / "temp" / "descriptors"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))
from _extract import extract  # noqa: E402
from core.flows import descriptor as D  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VIEWPORT = {"width": 1280, "height": 1600}
PER_SITE = 120

# The record selector, spelled exactly as background.js spells it for
# `recordAtoms`. Checked against the file at import so a rename there fails
# this probe instead of silently making it measure something else.
RECORD_SEL = "tr,li,dl,article,figure,fieldset"

CELLS = ("tag_raw", "tag_vis", "lca_raw", "lca_vis", "lca_vis_nc",
         "climb_raw", "climb_vis")

# A THIRD DEFINITION, AND IT IS ALREADY IN THE TREE. `search_page`'s `_climbTo`
# answers the identical question -- "which ancestor is the record this hit
# belongs to" -- and answers it with a DECLARED tag within 4 hops, falling back
# to `_isRecord`: a node with at least one SAME-KIND sibling under its parent,
# i.e. one of a repeated run (MDR/DEPTA's data record, the same notion #27's
# fold signature uses). `_sameKind` compares tag plus class-set INTERSECTION,
# with a depth-3 structural signature when neither side has classes, and
# `_CLIMB_STOP` bounds the walk at a landmark.
#
# `recordAtoms`' own comment claims it uses "the same set `_climbTo` uses".
# It does not, in two ways: it carries FIELDSET where `_RECORD` does not, and
# it has no structural fallback at all. That is rule 17 -- one concept, two
# spellings -- and it is why a <div>-built row has no record in the flow
# recorder while the same row has one in search_page.
#
# These two cells are the drop-in: the record `_climbTo` would have found,
# scored under the same walk as every other cell. They are EXTRACTED from
# background.js rather than retyped, so a change there changes them too.
_CLIMB_NAMES = ("_RECORD", "_CLIMB_STOP", "_sig", "_cls", "_sameKind", "_isRecord")


def slice_const(src: str, name: str) -> str:
    """The exact source of `const <name> = ...` from background.js.

    Retyping these would be a second spelling of the concept this probe exists
    to measure, and a second spelling drifts (rule 17). Fails loudly rather
    than returning something plausible.
    """
    anchor = f"  const {name} = "
    i = src.find(anchor)
    if i < 0:
        raise SystemExit(f"slice_const: {name} not found in background.js")
    lines = src[i:].split("\n")
    if lines[0].rstrip().endswith("};"):
        return lines[0]
    for k in range(1, len(lines)):
        if lines[k].rstrip() == "  };":
            return "\n".join(lines[: k + 1])
    raise SystemExit(f"slice_const: no terminator for {name}")

# base must come first: it is the control, and a WRONG anywhere else means
# nothing if the unmutated page already mis-binds.
ARMS = ("base", "resort", "shuffle", "drop-target", "drop-other",
        "edit-cell", "bump-digits", "swap-controls")

PAGE_JS = r"""
(function () {
  const reg = () => window.__mmidReg;
  const el = (m) => { const r = reg(); const n = r && r.get(String(m)); return n && n.isConnected ? n : null; };
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();

  // ---- A: the two record definitions -------------------------------------
  function tagRecord(n) {
    const r = n.closest && n.closest(RECORD_SEL_);
    return (r && r !== n) ? r : null;
  }
  const chain = (n) => { const a = []; for (let x = n; x; x = x.parentNode) a.push(x); return a; };
  function lca(nodes) {
    let c = chain(nodes[0]);
    for (const n of nodes.slice(1)) { const s = new Set(chain(n)); c = c.filter((x) => s.has(x)); }
    return c[0] || null;
  }
  function childToward(parent, n) { let x = n; while (x && x.parentNode !== parent) x = x.parentNode; return x; }
  // VERBATIM from tools/audit_record_witness.py: the definition under test.
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
  function lcaRecord(n, members) {
    const r = recordOf(n, members);
    return (r && r !== n) ? r : null;
  }

  // ---- A, third answer: search_page's own record notion ------------------
  // The definitions below are SLICED VERBATIM out of background.js.
CLIMB_DEFS_
  // `_climbTo` returns a hop COUNT; this is the same walk returning the node.
  function climbRecord(node) {
    try {
      let n = node, d = 0;
      while (n && d < 8) {
        n = n.parentElement || (n.getRootNode && n.getRootNode().host) || null;
        if (!n) break;
        d++;
        if (d <= 4 && _RECORD[n.tagName]) return n;
        if (_CLIMB_STOP[n.tagName]) break;
        if (_isRecord(n)) return n;
      }
    } catch (e) {}
    return null;
  }

  // ---- B: the two text filters -------------------------------------------
  // The probe's rule, VERBATIM from audit_record_witness.py, because that is
  // the definition under test. NOT opacity: #78 measured opacity:0 as DON'T
  // BUILD for the collector, so adding it would make the cells disagree with
  // the product about what "rendered" means for a reason nothing measured.
  //
  // IT IS STRICTER THAN THE COLLECTOR'S OWN `_namable`, DELIBERATELY, and that
  // makes every B figure an UPPER BOUND. `_namable` keeps `display: contents`
  // -- a <slot>, or a `<span style="display:contents">` wrapper, generates no
  // box, so a bare checkVisibility() rejects it while its children render
  // normally (#93 measured that fixing 0.154% of rows at first paint and
  // 0.432% after an interaction). This rule rejects them, so it can only
  // OVER-report how much of the shipped field is text nobody can see. If the
  // measured B is ~0 under this rule it is <= that under `_namable`; if it
  // were large, this would have to be re-run with `_namable` before the number
  // meant anything.
  function rendered(p) {
    if (!p) return false;
    if (/^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(p.tagName)) return false;
    try { if (p.checkVisibility && !p.checkVisibility({ visibilityProperty: true })) return false; } catch (e) {}
    return true;
  }

  // ---- the walk. ONE function; `filt` and `cap` are the only differences,
  // so the four capped cells cannot drift apart for any other reason. The
  // uncapped cell passes cap = Infinity.
  function atomsIn(r, filt, cap) {
    if (!r) return null;
    const out = [];
    const w = document.createTreeWalker(r, NodeFilter.SHOW_TEXT);
    let n, seen = 0;
    while ((n = w.nextNode()) && seen < cap) {
      if (filt && !rendered(n.parentElement)) continue;
      const t = norm(n.nodeValue);
      if (!t || !/[\p{L}\p{N}]/u.test(t)) continue;
      if (out.indexOf(t) < 0) { out.push(t); seen++; }
    }
    const lim = cap === Infinity ? Infinity : cap + 8;   // shipped: 40 then <48
    for (const im of r.querySelectorAll('img[alt]')) {
      if (filt && !rendered(im)) continue;
      const a = (im.getAttribute('alt') || '').trim();
      if (a && out.indexOf(a) < 0 && out.length < lim) out.push(a);
    }
    return out.length ? out : null;
  }

  function sizeOf(r) {
    if (!r) return null;
    let txt = 0;
    try { txt = (r.textContent || '').length; } catch (e) {}
    return { els: r.querySelectorAll('*').length, chars: txt, tag: r.tagName.toLowerCase() };
  }

  window.__rd = {
    // EXPOSED for the cost probe, which is a separate page.evaluate() and so
    // cannot see this closure -- a free identifier there would throw into a
    // swallowing catch and the timing would silently be of nothing (C11's
    // class, one layer out).
    climbRecord, atomsIn, tagRecord,
    // Per crowd, per member: all cells plus the record shapes.
    cells(groups) {
      const res = {};
      for (const g of groups) {
        // A MEMBER MAY BE GONE, and nulling the whole group when one is would
        // make every drop arm 100% REFUSED BY CONSTRUCTION -- the resolver
        // would see no atoms anywhere and could not take the content branch
        // at all. Measured: after removing one record, this returned null for
        // all three members while the collector's own `recordAtoms` was intact
        // for the two survivors, so the drop arms were scoring the FALLBACK
        // path and calling it the definition.
        //
        // The survivors are also the right CROWD for the LCA rule: at replay
        // the crowd is whatever matches now, not what matched at record time.
        const all = g.map(el);
        const live = all.filter(Boolean);
        for (let i = 0; i < g.length; i++) {
          const n = all[i];
          if (!n) { res[g[i]] = null; continue; }
          const nodes = live;
          const rt = tagRecord(n);
          const rl = lcaRecord(n, nodes);
          const rc = climbRecord(n);
          res[g[i]] = {
            tag_raw: atomsIn(rt, false, 40),
            tag_vis: atomsIn(rt, true, 40),
            lca_raw: atomsIn(rl, false, 40),
            lca_vis: atomsIn(rl, true, 40),
            lca_vis_nc: atomsIn(rl, true, Infinity),
            climb_raw: atomsIn(rc, false, 40),
            climb_vis: atomsIn(rc, true, 40),
            tag_size: sizeOf(rt),
            lca_size: sizeOf(rl),
            climb_size: sizeOf(rc),
            climb_swallows: rc ? nodes.filter((m) => m !== n && rc.contains(m)).length : 0,
            // Does the LCA record swallow another member of the same crowd?
            // If it does, no atom inside it can be unique and the definition
            // has failed on this crowd rather than merely found nothing.
            lca_swallows: rl ? nodes.filter((m) => m !== n && rl.contains(m)).length : 0,
            lca_is_body: !!(rl && (rl.tagName === 'BODY' || rl.tagName === 'HTML' ||
                                   rl === document.body || rl === document.documentElement)),
          };
        }
      }
      return res;
    },

    // ---- arms. Each returns the mmids it actually applied to: a mutation
    // that silently did nothing reports the base arm twice and calls it a
    // pass (PRINCIPLES 5).
    mutate(kind, groups, victims, seed) {
      let s = seed >>> 0;
      const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
      const applied = [];
      for (const g of groups) {
        const nodes = g.map(el); if (nodes.some((n) => !n)) continue;
        // The record used for MUTATION is the TAG record where there is one
        // and the LCA record otherwise: the arms must move something that
        // looks like a row on the page, not something one cell believes in.
        const recs = nodes.map((n) => tagRecord(n) || lcaRecord(n, nodes));
        if (recs.some((r) => !r)) continue;
        if (recs.some((r) => recs.filter((x) => x === r).length !== 1)) continue;

        if (kind === 'resort' || kind === 'shuffle') {
          const parent = recs[0].parentNode;
          if (!parent || recs.some((r) => r.parentNode !== parent)) continue;
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

        } else if (kind === 'swap-controls') {
          // ADVERSARIAL and deliberately so: the CONTROLS are permuted and
          // their records stay put. #72 dismissed this as not physically
          // realisable; that is an argument rather than a measurement, so it
          // is measured and reported separately.
          const order = nodes.slice();
          const marks = order.map((n) => { const m = document.createComment(''); n.before(m); return m; });
          const rev = order.slice().reverse();
          marks.forEach((m, i) => { m.replaceWith(rev[i]); });
          g.forEach((m) => applied.push(m));

        } else if (kind === 'drop-target' || kind === 'drop-other') {
          const v = victims[g[0]]; if (v == null) continue;
          const i = g.indexOf(String(v)); if (i < 0) continue;
          if (!recs[i].parentNode) continue;
          recs[i].remove();
          if (kind === 'drop-target') applied.push(String(v));
          else g.forEach((m, k) => { if (k !== i) applied.push(m); });

        } else if (kind === 'edit-cell') {
          const v = victims[g[0]]; if (v == null) continue;
          const i = g.indexOf(String(v)); if (i < 0) continue;
          const w = document.createTreeWalker(recs[i], NodeFilter.SHOW_TEXT);
          let done = false;
          for (let n = w.currentNode; n && !done; n = w.nextNode())
            if (norm(n.nodeValue) && rendered(n.parentElement)) { n.nodeValue = n.nodeValue + ' (edited)'; done = true; }
          if (done) applied.push(String(v));

        } else if (kind === 'bump-digits') {
          let any = false;
          for (const r of recs) {
            const w = document.createTreeWalker(r, NodeFilter.SHOW_TEXT);
            for (let n = w.currentNode; n; n = w.nextNode())
              if (/\d/.test(n.nodeValue || '')) { n.nodeValue = n.nodeValue.replace(/\d+/g, (d) => String(Number(d) + 1)); any = true; }
          }
          if (any) g.forEach((m) => applied.push(m));
        }
      }
      return applied;
    },

    // Mutilation, for the firing proof: blank the text of every record so no
    // cell can find an atom. A coverage probe that cannot report a miss is
    // worth nothing (PRINCIPLES 5 / 11).
    blank(groups) {
      let k = 0;
      for (const g of groups) {
        const nodes = g.map(el); if (nodes.some((n) => !n)) continue;
        for (let i = 0; i < g.length; i++) {
          const r = tagRecord(nodes[i]) || lcaRecord(nodes[i], nodes);
          if (!r) continue;
          const w = document.createTreeWalker(r, NodeFilter.SHOW_TEXT);
          for (let n = w.currentNode; n; n = w.nextNode()) { n.nodeValue = ' '; k++; }
        }
      }
      return k;
    },
  };
  return true;
})()
"""


def page_js() -> str:
    bg = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
    defs = "\n".join(slice_const(bg, nm) for nm in _CLIMB_NAMES)
    return (PAGE_JS.replace("RECORD_SEL_", json.dumps(RECORD_SEL))
            .replace("CLIMB_DEFS_", defs))


def check_selector_parity() -> str:
    """The shipped selector must still be the one this probe spells.

    A rename in background.js that this file did not follow would make every
    `tag_*` cell describe a record the product never builds, and the result
    would look like a measurement (rule 17 / PRINCIPLES 15).
    """
    bg = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
    if f"closest('{RECORD_SEL}')" in bg:
        return "ok"
    return "DRIFTED"


# ---------------------------------------------------------------------------


def crowds_of(entries):
    pool = [e for e in entries if D._targetable(e)]
    groups: dict = {}
    for e in pool:
        groups.setdefault(json.dumps(D.at_level(e, D.FULL), sort_keys=True), []).append(e)
    return [g for g in groups.values() if len(g) >= 2]


def sub(entries: list[dict], cells: dict, cell: str) -> list[dict]:
    """A copy of `entries` whose `recordAtoms` is `cell`'s answer.

    Substituting the FIELD rather than reimplementing the resolver is what
    makes this a measurement of the definition: everything downstream is the
    shipped code (rule 17).
    """
    out = []
    for e in entries:
        c = cells.get(str(e.get("mmid")))
        e2 = dict(e)
        e2["recordAtoms"] = (c or {}).get(cell) if c else None
        out.append(e2)
    return out


def verdict(target: dict, entries: list[dict], want) -> str:
    """CORRECT / REFUSED / WRONG. `want=None` means the element is GONE, so a
    refusal is the only correct answer and any binding is a binding to
    something else."""
    try:
        got = D.resolve(target, entries)
    except D.Unresolved:
        return "REFUSED"
    except Exception:
        return "REFUSED"
    if want is None:
        return "WRONG"
    return "CORRECT" if str(got) == str(want) else "WRONG"


def sites_of(n):
    """`SITES` holds BOTH `(name, url)` and `(name, url, settle_ms)`.

    35 of the 106 entries carry a third element. Every descriptor probe in
    this repo unpacks two -- `audit_record_witness.py:493`,
    `audit_flow_resolve.py:438`, `audit_href_rung.py:240` -- so any of them
    run past index 59 dies with `ValueError: too many values to unpack`, and
    their defaults (30-40 sites) are why nobody has met it. The practical
    consequence is that **no flow-descriptor measurement in this project has
    ever seen the second half of the corpus**, which is where adminlte,
    syncfusion_grid, jspreadsheet, moodle and premierleague live -- the
    closest thing the corpus has to the admin tables this feature records
    against. This probe met it at site 60 of a 106-site run.
    """
    from capture_listings import SITES
    out = []
    for s_ in list(SITES)[:n]:
        out.append((s_[0], s_[1], s_[2] if len(s_) > 2 else 1200))
    return out


async def load(browser, name, url, collect_js, settle=1200):
    har = FROZEN / f"{name}.har"
    if not har.exists():
        return None, None
    ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True)
    await ctx.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
    await ctx.route_from_har(str(har), not_found="abort")
    page = await ctx.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
    except Exception:
        await ctx.close()
        return None, None
    # THE CORPUS DECLARES ITS OWN SETTLE TIME for 35 sites and it goes up to
    # 12s. A fixed 1200ms would measure those pages half-built, which is the
    # #15 trap pointed at a probe rather than at a banner.
    await page.wait_for_timeout(settle)
    await page.evaluate(page_js())
    return ctx, page


async def collect(page, collect_js):
    return await page.evaluate(
        "(function(){ " + collect_js + "; return _collectInteractivePage(true, null, 'brief'); })()") or []


def uniq_cells(cells: dict, crowd: list[str]) -> dict:
    """mmid -> {cell: bool}: does this member hold an atom no sibling holds?

    Same rule `atoms_map` applies -- an atom two members share cannot say which
    was meant, so recording it would put a field in the file that looks like a
    safeguard and is not.
    """
    out = {}
    for mm in crowd:
        mine = cells.get(mm) or {}
        row = {}
        for c in CELLS:
            a = set(mine.get(c) or [])
            if not a:
                row[c] = False
                continue
            others = set()
            for o in crowd:
                if o != mm:
                    others |= set((cells.get(o) or {}).get(c) or [])
            row[c] = bool(a - others)
        out[mm] = row
    return out


async def run_site(browser, name, url, rng, collect_js, drift=False, settle=1200):
    ctx, page = await load(browser, name, url, collect_js, settle)
    if not page:
        return None
    try:
        a = await collect(page, collect_js)
        if len(a) < 5:
            return None
        crowds = crowds_of(a)
        if not crowds:
            return {"name": name, "n": 0}
        groups = [[str(e["mmid"]) for e in g] for g in crowds]
        cells = await page.evaluate("(g)=>window.__rd.cells(g)", groups)
    finally:
        await ctx.close()

    by_mm = {str(e["mmid"]): e for e in a}
    members = [(e, gi) for gi, g in enumerate(crowds) for e in g]
    if len(members) > PER_SITE:
        members = rng.sample(members, PER_SITE)

    cov = Counter()
    shapes = {"tag": [], "lca": [], "climb": []}
    tgts = {}
    members_out: list = []
    parity_bad = []
    hidden_rows = Counter()
    for e, gi in members:
        mm = str(e["mmid"])
        t = D.build(e, a)           # the SHIPPED descriptor, incl. shipped atoms
        if t.get("of") is None:
            continue                # not ordinal-bearing: nothing to witness
        crowd = groups[gi]
        u = uniq_cells(cells, crowd)[mm]
        c = cells.get(mm) or {}

        # PARITY. tag_raw is a second spelling of the shipped field.
        shipped_field = by_mm[mm].get("recordAtoms")
        if (c.get("tag_raw") or None) != (shipped_field or None):
            parity_bad.append(mm)

        cov["n"] += 1
        cov["shipped_witness"] += bool(t.get("witness"))
        for cl in CELLS:
            cov[cl] += bool(u[cl])
            cov[cl + "_or_w"] += bool(u[cl] or t.get("witness"))
            cov[cl + "_rescue"] += bool(u[cl]) and not t.get("witness")
        cov["unwit"] += not bool(t.get("witness"))
        cov["tag_none"] += not bool(c.get("tag_size"))
        cov["lca_none"] += not bool(c.get("lca_size"))
        cov["lca_swallows"] += bool(c.get("lca_swallows"))
        cov["climb_none"] += not bool(c.get("climb_size"))
        cov["climb_swallows"] += bool(c.get("climb_swallows"))
        cov["lca_is_body"] += bool(c.get("lca_is_body"))
        if c.get("tag_size"):
            shapes["tag"].append(c["tag_size"])
        if c.get("lca_size"):
            shapes["lca"].append(c["lca_size"])
        if c.get("climb_size"):
            shapes["climb"].append(c["climb_size"])

        # DIVERGENCE B, isolated: atoms the shipped cell holds that the
        # filtered cell does not are text no user can see.
        raw, vis = set(c.get("tag_raw") or []), set(c.get("tag_vis") or [])
        if raw:
            hidden_rows["members_with_atoms"] += 1
            hidden_rows["atoms_total"] += len(raw)
            hidden_rows["atoms_hidden"] += len(raw - vis)
            if raw - vis:
                hidden_rows["members_any_hidden"] += 1
            if u["tag_raw"] and not u["tag_vis"]:
                hidden_rows["unique_only_via_hidden"] += 1
        tgts[mm] = (e, t, gi)
        # PER-MEMBER ROW, for the hazard cut. The aggregate cannot answer
        # "what does the structural definition do in its BAD cases", because
        # that needs unique-ness crossed with record size and with whether the
        # record swallowed a sibling. Kept small: no atom text.
        members_out.append({
            "site": name, "mmid": mm, "crowd": len(crowd),
            "w": bool(t.get("witness")),
            "u": {cl: bool(u[cl]) for cl in CELLS},
            "tag_els": (c.get("tag_size") or {}).get("els"),
            "tag_chars": (c.get("tag_size") or {}).get("chars"),
            "tag_tag": (c.get("tag_size") or {}).get("tag"),
            "lca_els": (c.get("lca_size") or {}).get("els"),
            "lca_chars": (c.get("lca_size") or {}).get("chars"),
            "lca_tag": (c.get("lca_size") or {}).get("tag"),
            "swallows": c.get("lca_swallows"),
            "climb_els": (c.get("climb_size") or {}).get("els"),
            "climb_chars": (c.get("climb_size") or {}).get("chars"),
            "climb_tag": (c.get("climb_size") or {}).get("tag"),
            "climb_swallows": c.get("climb_swallows"),
            "n_ship": len(c.get("tag_raw") or []),
            "n_lca": len(c.get("lca_vis") or []),
            "n_lca_nc": len(c.get("lca_vis_nc") or []),
        })

    # Build each cell's descriptor ONCE per target. `a` and `cells` do not
    # change between arms, so doing it inside the arm loop would be the same
    # work eight times over and would make a 40-site run unaffordable.
    sub_a = {cl: sub(a, cells, cl) for cl in CELLS}
    tv = {mm: {cl: (t if cl == "tag_raw" else D.build(e, sub_a[cl])) for cl in CELLS}
          for mm, (e, t, gi) in tgts.items()}

    row = {"name": name, "crowds": len(crowds), "cov": dict(cov),
           "parity_bad": len(parity_bad), "hidden": dict(hidden_rows),
           "shapes": {k: {"els": [s["els"] for s in v], "chars": [s["chars"] for s in v],
                          "tags": Counter(s["tag"] for s in v).most_common(6)}
                      for k, v in shapes.items()},
           "members": members_out}
    if drift or not tgts:
        return row

    # ---- arms -------------------------------------------------------------
    verd: dict = {}
    # PER-MEMBER VERDICTS, compressed to one letter per cell. The hazard
    # question -- "what does the structural definition do in its BAD cases" --
    # needs a verdict crossed with the record's SIZE, and an aggregate cannot
    # be cut that way afterwards.
    vrows: list = []
    for arm in ARMS:
        ctx, page = await load(browser, name, url, collect_js, settle)
        if not page:
            continue
        try:
            b0 = await collect(page, collect_js)
            if {str(e["mmid"]) for e in b0 if D._targetable(e)} != \
                    {str(e["mmid"]) for e in a if D._targetable(e)}:
                row["ruler_valid"] = False      # the page is not replaying the same
                continue
            victims = {g[0]: rng.choice(g) for g in groups}
            applied = set()
            if arm != "base":
                applied = set(await page.evaluate(
                    "([k,g,v,s])=>window.__rd.mutate(k,g,v,s)",
                    [arm, groups, victims, rng.randrange(1 << 30)]))
            b = await collect(page, collect_js)
            after = await page.evaluate("(g)=>window.__rd.cells(g)", groups)
        finally:
            await ctx.close()

        bm = {str(e["mmid"]) for e in b}
        sub_b = {cl: sub(b, after, cl) for cl in CELLS}
        for mm, (e, t, gi) in tgts.items():
            if arm != "base" and mm not in applied:
                continue
            want = mm
            if arm == "drop-target":
                want = None                  # gone: only a refusal is correct
            elif mm not in bm:
                continue
            vr = {"arm": arm, "mmid": mm}
            for cl in CELLS:
                tvc = tv[mm][cl]
                v = verdict(tvc, sub_b[cl], want)
                vr[cl] = v[0] + ("h" if tvc.get("atoms") else "-")
                verd.setdefault(arm, {}).setdefault(cl, Counter())[v] += 1
                # Restricted population: only where THIS cell actually has a
                # witness. The pooled figure includes the members that fall
                # back to the ordinal and dilutes every rate toward it.
                if tvc.get("atoms"):
                    verd[arm].setdefault(cl + "@has", Counter())[v] += 1
            vrows.append(vr)
    row["verd"] = {k: {c: dict(x) for c, x in v.items()} for k, v in verd.items()}
    row["vrows"] = vrows
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


# ---------------------------------------------------------------------------


async def selftest(collect_js) -> int:
    """The firing proof. Three directions, because a coverage number from a
    detector nobody has watched report a miss is worth nothing."""
    from playwright.async_api import async_playwright
    bad = 0
    # THE FIXTURE HAD TO BE BUILT BY RUNNING IT, and the first two versions
    # were vacuous for the same reason (PRINCIPLES 11). With the <button> as a
    # direct child of the row, `near` picks up the whole row text --
    # "Acme LtdINV-1001ActionsDelete" -- so every descriptor is unique at the
    # `near` rung, NO crowd forms, no ordinal is recorded and the atoms path is
    # never reached. An actions cell is what makes `near` identical across
    # rows, which is the shape that actually needs a witness.
    def _row(tag, co, inv, k):
        return (f'<{tag} class=row><span>{co}</span><span>{inv}</span>'
                f'<div style="display:none">HIDDENTOKEN-{k}</div>'
                f'<div class=acts><span>Actions</span>'
                f'<button onclick="void 0">Delete</button></div></{tag}>')
    DATA = [("Acme Ltd", "INV-1001"), ("Beta Inc", "INV-1002"), ("Gamma Co", "INV-1003")]
    rows_div = "".join(_row("div", c, i, k + 1) for k, (c, i) in enumerate(DATA))
    rows_li = "".join(_row("li", c, i, k + 1) for k, (c, i) in enumerate(DATA))
    HTML = ("<!doctype html><html><body><main><div class=t>" + rows_div +
            "</div></main></body></html>")
    HTML_LI = ("<!doctype html><html><body><main><ul>" + rows_li +
               "</ul></main></body></html>")
    async def one(browser, html, label):
        ctx = await browser.new_context(viewport=VIEWPORT)
        await ctx.add_init_script(path=str(ROOT / "extension" / "listener_tag.js"))
        page = await ctx.new_page()
        await page.goto("about:blank")
        await page.set_content(html)
        await page.evaluate(page_js())
        a_ = await collect(page, collect_js)
        cr = crowds_of(a_)
        print(f"  fixture {label}: {len(a_)} entries, {len(cr)} crowd(s)")
        return ctx, page, a_, cr

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx, page, a, crowds = await one(browser, HTML, "div-rows")
        if not crowds:
            print("  !! no crowd -- the fixture does not reach the code under test")
            await browser.close()
            return 1
        groups = [[str(e["mmid"]) for e in g] for g in crowds]
        cells = await page.evaluate("(g)=>window.__rd.cells(g)", groups)
        mm = groups[0][0]
        u = uniq_cells(cells, groups[0])[mm]
        by = {str(e["mmid"]): e for e in a}

        # 1. DIVERGENCE A, through the PRODUCT not through my reimplementation:
        #    on div-built rows the shipped field is null and the step is left
        #    pinned by position alone, while the structural cell has a witness.
        t = D.build(by[mm], a)
        a_fires = (by[mm].get("recordAtoms") is None) and t.get("of") and not t.get("atoms") \
            and bool(u["lca_raw"])
        print(f"  A  div rows: shipped recordAtoms={by[mm].get('recordAtoms')!r}  "
              f"of={t.get('of')} atoms={t.get('atoms')!r}  lca_raw unique={u['lca_raw']}"
              f"  -> fires: {bool(a_fires)}")
        bad += not a_fires
        # A2: search_page's own record notion finds the SAME div row, with no
        # crowd needed and no new vocabulary -- the claim the third cell makes.
        a2 = bool(cells[mm].get("climb_raw")) and u["climb_raw"]
        print(f"  A2 search_page's _climbTo record on the same rows: "
              f"{(cells[mm].get('climb_raw') or [])[:3]!r} unique={u['climb_raw']}"
              f"  -> fires: {a2}")
        bad += not a2

        # 3. COVERAGE CAN REPORT A MISS. Blank every record's text and the
        #    structural cell must go from unique to nothing.
        before = u["lca_vis"]
        await page.evaluate("(g)=>window.__rd.blank(g)", groups)
        cells2 = await page.evaluate("(g)=>window.__rd.cells(g)", groups)
        after = uniq_cells(cells2, groups[0])[mm]["lca_vis"]
        print(f"  C  unique before blanking={before} after={after}  -> fires: {before and not after}")
        bad += not (before and not after)
        await ctx.close()

        # 2. DIVERGENCE B needs a TAG record to exist at all, so it is asked of
        #    the <li> fixture: a display:none token must reach the shipped
        #    field and not the filtered cell.
        ctx, page, a2, cr2 = await one(browser, HTML_LI, "li-rows")
        g2 = [[str(e["mmid"]) for e in g] for g in cr2]
        c2 = await page.evaluate("(g)=>window.__rd.cells(g)", g2) if g2 else {}
        mm2 = g2[0][0] if g2 else None
        by2 = {str(e["mmid"]): e for e in a2}
        ship2 = set((by2.get(mm2) or {}).get("recordAtoms") or []) if mm2 else set()
        vis2 = set((c2.get(mm2) or {}).get("tag_vis") or []) if mm2 else set()
        hid = {x for x in ship2 if "HIDDENTOKEN" in x}
        b_fires = bool(hid) and not any("HIDDENTOKEN" in x for x in vis2)
        print(f"  B  shipped field carries {sorted(hid)!r}; filtered cell carries "
              f"{sorted(x for x in vis2 if 'HIDDEN' in x)!r}  -> fires: {b_fires}")
        bad += not b_fires
        # and it is a RECORDED witness, not merely collected
        t2 = D.build(by2[mm2], a2) if mm2 else {}
        in_desc = any("HIDDENTOKEN" in x for x in (t2.get("atoms") or []))
        print(f"  B2 the descriptor records it: atoms={t2.get('atoms')!r}  -> fires: {in_desc}")
        bad += not in_desc
        await ctx.close()
        await browser.close()

    # 4. The RESOLVER reports WRONG when the definition is wrong. Pure Python:
    #    a crowd whose atoms name the wrong member must not come back CORRECT.
    def rec(mm_, atoms):
        return {"mmid": str(mm_), "tag": "button", "role": "", "type": "", "name": "Delete",
                "label": "", "placeholder": "", "text": "Delete", "section": "main",
                "underHeading": "Invoices", "near": "", "href": "", "clickable": True,
                "recordAtoms": atoms}
    good = [rec(11, ["Acme Ltd", "INV-1001"]), rec(13, ["Beta Inc", "INV-1002"])]
    t = D.build(good[0], good)
    swapped = [rec(11, ["Beta Inc", "INV-1002"]), rec(13, ["Acme Ltd", "INV-1001"])]
    v_ok = verdict(t, good, "11")
    v_bad = verdict(t, swapped, "11")
    print(f"  D  resolver on a correct page={v_ok} on a swapped page={v_bad}  "
          f"-> fires: {v_ok == 'CORRECT' and v_bad == 'WRONG'}")
    bad += not (v_ok == "CORRECT" and v_bad == "WRONG")

    print(f"\n  selector parity with background.js: {check_selector_parity()}")
    bad += check_selector_parity() != "ok"
    print(f"\n{'SELFTEST PASS' if not bad else f'SELFTEST FAIL ({bad})'}")
    return 1 if bad else 0


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--drift", action="store_true",
                    help="load every site TWICE and report coverage both times")
    ap.add_argument("--out", default="record_definition.json")
    ap.add_argument("--analyse", help="re-report a saved JSON, plus the hazard cut")
    ap.add_argument("--arms", default="",
                    help="comma-separated arm names; the default is all of "
                         "ARMS. `base` is always included -- a WRONG anywhere "
                         "else means nothing without it.")
    ap.add_argument("--only", default="",
                    help="comma-separated site names; the arms are expensive "
                         "(8 reloads each) and most corpus sites produce no "
                         "ordinal-bearing descriptor at all, so a coverage "
                         "pass is run first and this restricts the safety "
                         "pass to the sites that actually have a crowd")
    ap.add_argument("--cost", action="store_true",
                    help="time the record rule at COLLECTION, which runs per entry")
    args = ap.parse_args()

    if args.arms:
        want = {x.strip() for x in args.arms.split(",") if x.strip()}
        bad = want - set(ARMS)
        if bad:
            raise SystemExit(f"unknown arm(s): {sorted(bad)}; known: {ARMS}")
        globals()["ARMS"] = tuple(a for a in ARMS if a == "base" or a in want)
    bg = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
    collect_js = extract("_collectInteractivePage", bg, verify=True)
    if args.selftest:
        return await selftest(collect_js)
    if args.analyse:
        d = json.loads(Path(args.analyse).read_text(encoding="utf-8"))
        report(d["rows"], d.get("drift") or ())
        hazard(d["rows"])
        return 0

    from playwright.async_api import async_playwright
    if args.cost:
        async with async_playwright() as p2:
            br = await p2.chromium.launch()
            rs = await cost(br, collect_js, sites_of(args.sites))
            await br.close()
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "record_cost.json").write_text(json.dumps(rs, indent=1), encoding="utf-8")
        return 0

    rows, rows2 = [], []
    # PER-SITE seed, so pass 2 of --drift samples the SAME members as pass 1.
    # A single advancing RNG would put sampling noise into the drift floor and
    # the floor is the thing the deltas are judged against (MEASUREMENT R3).
    site_rng = lambda nm: random.Random(f"{args.seed}:{nm}")
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        _only = {x.strip() for x in args.only.split(",") if x.strip()}
        _sites = [t for t in sites_of(args.sites) if not _only or t[0] in _only]
        for i, (name, url, settle) in enumerate(_sites, 1):
            try:
                r = await run_site(browser, name, url, site_rng(name), collect_js,
                                   drift=args.drift, settle=settle)
            except Exception as exc:
                print(f"  [{i:>3}] {name:<22} ERROR {type(exc).__name__}: {str(exc)[:80]}", flush=True)
                continue
            if not r or not r.get("cov", {}).get("n"):
                print(f"  [{i:>3}] {name:<22} no ordinal-bearing descriptors", flush=True)
                if r:
                    rows.append(r)
                continue
            rows.append(r)
            c = r["cov"]
            print(f"  [{i:>3}] {name:<22} n={c['n']:<4} shipped={c['tag_raw']:<4} "
                  f"lca_vis={c['lca_vis']:<4} parity_bad={r['parity_bad']}", flush=True)
            if args.drift:
                r2 = await run_site(browser, name, url, site_rng(name),
                                    collect_js, drift=True, settle=settle)
                if r2:
                    rows2.append(r2)
        await browser.close()

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / args.out).write_text(json.dumps({"rows": rows, "drift": rows2}, indent=1),
                                encoding="utf-8")
    print(f"\n  written: {OUT / args.out}", flush=True)
    try:
        report(rows, rows2)
    except Exception as exc:
        print(f"  report FAILED ({type(exc).__name__}: {exc}) -- the data is saved; "
              f"re-run with --analyse {OUT / args.out}")
        import traceback
        traceback.print_exc()
        return 1
    return 0


def report(rows, rows2=()):
    sites = [r for r in rows if r.get("cov", {}).get("n")]
    cov = tot(rows, ["cov"])
    n = cov["n"] or 1
    print(f"\n{'=' * 78}\nRECORD DEFINITION -- {len(rows)} sites, {len(sites)} with "
          f"ordinal-bearing descriptors, {cov['n']} descriptors\n{'=' * 78}")
    pb = sum(r.get("parity_bad", 0) for r in rows)
    print(f"  PARITY  tag_raw vs the collector's own recordAtoms: "
          f"{pb} mismatch(es) of {cov['n']}  [{'ok' if not pb else 'DRIFTED -- the baseline cell is not the shipped field'}]")
    print(f"  selector parity with background.js: {check_selector_parity()}")

    print(f"\n  COVERAGE -- a witness unique within the crowd")
    print(f"  {'cell':<13}{'n':>7}{'share':>9}{'  +shipped witness':>20}{'rescues unwitnessed':>22}")
    print(f"  {'shipped self+anchor witness':<13}{cov['shipped_witness']:>7}{cov['shipped_witness'] / n:>9.1%}")
    for cl in CELLS:
        lbl = cl + (" == SHIPPED" if cl == "tag_raw" else
                    (" == PROBE" if cl == "lca_vis_nc" else
                     (" == search_page" if cl == "climb_raw" else "")))
        print(f"  {lbl:<26}{cov[cl]:>7}{cov[cl] / n:>9.1%}"
              f"{cov[cl + '_or_w'] / n:>16.1%}{cov[cl + '_rescue'] / max(cov['unwit'], 1):>20.1%}")
    print(f"\n  unwitnessed by the shipped self+anchor witness: {cov['unwit']} ({cov['unwit'] / n:.1%})")
    print(f"  DIVERGENCE A: no TAG record in range {cov['tag_none']:>5} ({cov['tag_none'] / n:>5.1%})  "
          f"| no LCA record {cov['lca_none']:>5} ({cov['lca_none'] / n:>5.1%})  "
          f"| no CLIMB record {cov['climb_none']:>5} ({cov['climb_none'] / n:>5.1%})")
    print(f"  climb hazard: record swallows another crowd member {cov['climb_swallows']:>5} "
          f"({cov['climb_swallows'] / n:>5.1%})")
    print(f"  LCA hazard: record swallows another crowd member {cov['lca_swallows']:>5} "
          f"({cov['lca_swallows'] / n:>5.1%})  | record is body/html {cov['lca_is_body']} ")

    h = tot(rows, ["hidden"])
    ha = h["atoms_total"] or 1
    print(f"\n  DIVERGENCE B -- hidden text in the SHIPPED field")
    print(f"    members with shipped atoms           {h['members_with_atoms']:>7}")
    print(f"    atoms total / NOT rendered           {h['atoms_total']:>7} / {h['atoms_hidden']} ({h['atoms_hidden'] / ha:.1%})")
    print(f"    members carrying >=1 hidden atom     {h['members_any_hidden']:>7} "
          f"({h['members_any_hidden'] / max(h['members_with_atoms'], 1):.1%})")
    print(f"    members UNIQUE ONLY via hidden text  {h['unique_only_via_hidden']:>7} "
          f"({h['unique_only_via_hidden'] / max(h['members_with_atoms'], 1):.1%})   <- witnessed by text no user can see")

    for k in ("tag", "lca", "climb"):
        els, chars, tags = [], [], Counter()
        for r in rows:
            s = (r.get("shapes") or {}).get(k) or {}
            els += s.get("els") or []
            chars += s.get("chars") or []
            for t_, c_ in s.get("tags") or []:
                tags[t_] += c_
        if els:
            els.sort(); chars.sort()
            q = lambda v, p: v[min(len(v) - 1, int(len(v) * p))]
            print(f"\n  RECORD SHAPE ({k}): n={len(els)} elements median={statistics.median(els):.0f} "
                  f"p90={q(els, .9)} max={els[-1]} | chars median={statistics.median(chars):.0f} "
                  f"p90={q(chars, .9)} max={chars[-1]}")
            print(f"    tags: {', '.join(f'{t}={c}' for t, c in tags.most_common(6))}")

    if any(r.get("verd") for r in rows):
        print(f"\n  ARM LEGEND -- what CORRECT means, because it is not the same question each time")
        print(f"    base          nothing changed. The control: a WRONG here voids every other row.")
        print(f"    resort        whole records reversed. CORRECT = the recorded ELEMENT, which moved with its record.")
        print(f"    shuffle       same, random permutation.")
        print(f"    drop-target   the recorded element's own record is GONE. A REFUSAL is the only correct answer.")
        print(f"    drop-other    a DIFFERENT record is gone. The control for the fix: refusing here is deletion, not safety.")
        print(f"    edit-cell     one cell of the record was edited. CORRECT = still resolves.")
        print(f"    bump-digits   every number in every record +1.")
        print(f"    swap-controls ADVERSARIAL and NOT SCORABLE: the controls are permuted and their records stay,")
        print(f"                  so 'the element I recorded' and 'the control in the row I recorded' are different")
        print(f"                  elements and nothing the page declares says which the step meant. Read the REFUSED")
        print(f"                  column only -- CORRECT/WRONG there is an artefact of picking one convention.")
        print(f"\n  SAFETY -- every descriptor (a cell with no atoms falls back to the shipped resolver)")
        print(f"  {'arm':<14}{'cell':<14}{'n':>6}{'CORRECT':>10}{'REFUSED':>10}{'WRONG':>9}")
        for arm in ARMS:
            for cl in CELLS:
                c = tot(rows, ["verd", arm, cl])
                nn = sum(c.values())
                if nn:
                    print(f"  {arm:<14}{cl:<14}{nn:>6}{c['CORRECT'] / nn:>10.1%}"
                          f"{c['REFUSED'] / nn:>10.1%}{c['WRONG'] / nn:>9.1%}")
        print(f"\n  SAFETY -- ONLY descriptors where that cell HAS a witness")
        print(f"  {'arm':<14}{'cell':<14}{'n':>6}{'CORRECT':>10}{'REFUSED':>10}{'WRONG':>9}")
        for arm in ARMS:
            for cl in CELLS:
                c = tot(rows, ["verd", arm, cl + "@has"])
                nn = sum(c.values())
                if nn:
                    print(f"  {arm:<14}{cl:<14}{nn:>6}{c['CORRECT'] / nn:>10.1%}"
                          f"{c['REFUSED'] / nn:>10.1%}{c['WRONG'] / nn:>9.1%}")

    if rows2:
        c1 = tot(rows, ["cov"]); c2 = tot(rows2, ["cov"])
        print(f"\n  DRIFT FLOOR -- the SAME arm measured twice ({len(rows2)} sites)")
        print(f"  {'cell':<14}{'pass 1':>9}{'pass 2':>9}{'delta':>9}")
        for cl in ("n",) + CELLS:
            a_, b_ = c1[cl], c2[cl]
            print(f"  {cl:<14}{a_:>9}{b_:>9}{(b_ - a_) / max(a_, 1):>8.1%}")

    inval = [r["name"] for r in rows if r.get("ruler_valid") is False]
    if inval:
        print(f"\n  ruler invalid (mmid sets differ between loads): {', '.join(inval)}")


def hazard(rows):
    """The tail of each definition, which the aggregate cannot show.

    A definition that is more often WRONG in its bad cases is worse than one
    that refuses there, and "bad case" for a structural record means BIG: the
    lowest common ancestor of a crowd that spans the page is a section whose
    text distinguishes members for the wrong reason. This cuts coverage and
    verdicts by the record's own size, and by whether it swallowed a sibling.
    """
    mem, ver = {}, {}
    for r in rows:
        for m in r.get("members") or []:
            mem[(m["site"], m["mmid"])] = m
        for v in r.get("vrows") or []:
            ver.setdefault((r["name"], v["mmid"]), []).append(v)
    print(f"\n{'=' * 78}\nHAZARD CUT -- {len(mem)} members, "
          f"{sum(len(v) for v in ver.values())} member-arm verdicts\n{'=' * 78}")

    for key, cell in (("lca_els", "lca_vis"), ("climb_els", "climb_vis"),
                      ("tag_els", "tag_raw")):
        vals = sorted(m[key] for m in mem.values() if m.get(key))
        if not vals:
            continue
        # DECILES OF THE OBSERVED DISTRIBUTION, not a chosen size. The cut is
        # "the biggest tenth of the records this definition actually built".
        q = vals[int(len(vals) * 0.9)]
        big = [m for m in mem.values() if (m.get(key) or 0) > q]
        small = [m for m in mem.values() if m.get(key) and (m.get(key) or 0) <= q]
        def rate(ms, c):
            return sum(m["u"][c] for m in ms) / max(len(ms), 1)
        print(f"\n  {cell}: record size p90 = {q} elements "
              f"({len(small)} at or below, {len(big)} above)")
        print(f"    unique witness, small records {rate(small, cell):>7.1%}   "
              f"big records {rate(big, cell):>7.1%}")
        for label, ms in (("small", small), ("big", big)):
            c = Counter()
            for m in ms:
                for v in ver.get((m["site"], m["mmid"])) or []:
                    if v["arm"] == "base":
                        continue
                    c[v[cell][0]] += 1
            tot_ = sum(c.values()) or 1
            print(f"    {label:<5} mutated arms: n={tot_:<6} "
                  f"CORRECT {c['C'] / tot_:>6.1%}  REFUSED {c['R'] / tot_:>6.1%}  "
                  f"WRONG {c['W'] / tot_:>6.1%}")

    for key, cell in (("swallows", "lca_vis"), ("climb_swallows", "climb_vis")):
        sw = [m for m in mem.values() if m.get(key)]
        if not sw:
            print(f"\n  {cell}: no member's record swallowed a sibling")
            continue
        c = Counter()
        for m in sw:
            for v in ver.get((m["site"], m["mmid"])) or []:
                if v["arm"] != "base":
                    c[v[cell][0]] += 1
        t_ = sum(c.values()) or 1
        print(f"\n  {cell}: {len(sw)} members whose record SWALLOWS another crowd "
              f"member ({len(sw) / max(len(mem), 1):.1%})")
        print(f"    unique witness anyway {sum(m['u'][cell] for m in sw) / len(sw):.1%}   "
              f"mutated arms n={t_} CORRECT {c['C'] / t_:.1%} REFUSED {c['R'] / t_:.1%} "
              f"WRONG {c['W'] / t_:.1%}")

    capped = [m for m in mem.values() if (m.get("n_lca_nc") or 0) > 40]
    print(f"\n  THE CAP: {len(capped)} of {len(mem)} members ({len(capped) / max(len(mem), 1):.1%}) "
          f"have more than 40 atoms uncapped, i.e. the shipped cap would bite")
    if capped:
        print(f"    of those, unique with the cap {sum(m['u']['lca_vis'] for m in capped) / len(capped):.1%} "
              f"without it {sum(m['u']['lca_vis_nc'] for m in capped) / len(capped):.1%}")

    print(f"\n  WHERE EACH DEFINITION FINDS NO RECORD AT ALL")
    for key, nm in (("tag_els", "tag (shipped)"), ("lca_els", "lca (probe)"),
                    ("climb_els", "climb (search_page)")):
        none_ = [m for m in mem.values() if not m.get(key)]
        print(f"    {nm:<22} {len(none_):>6} ({len(none_) / max(len(mem), 1):>5.1%})")

    # DOES THE CLIMB RULE LOSE A RECORD THE TAG LIST FOUND? It is not a
    # superset by construction: `_CLIMB_STOP` contains FIELDSET and TABLE, and
    # the declared-tag preference is bounded at 4 hops, where `closest()` has
    # no bound at all. A pure one-spelling swap therefore has a regression
    # surface and an additive "tag list, then structural fallback" does not.
    both = tagonly = climbonly = neither = 0
    tagonly_u = climbonly_u = 0
    for m in mem.values():
        t_, c_ = bool(m.get("tag_els")), bool(m.get("climb_els"))
        both += t_ and c_
        tagonly += t_ and not c_
        climbonly += c_ and not t_
        neither += not t_ and not c_
        if t_ and not c_:
            tagonly_u += m["u"]["tag_raw"]
        if c_ and not t_:
            climbonly_u += m["u"]["climb_raw"]
    print(f"\n  TAG RECORD x CLIMB RECORD, per member")
    print(f"    both have one      {both:>6}")
    print(f"    TAG only           {tagonly:>6}   (the climb rule LOSES these; "
          f"{tagonly_u} had a unique witness)")
    print(f"    CLIMB only         {climbonly:>6}   (the climb rule GAINS these; "
          f"{climbonly_u} have a unique witness)")
    print(f"    neither            {neither:>6}")
    tags = Counter(m.get("climb_tag") for m in mem.values() if m.get("climb_tag"))
    print(f"    climb record tags: {', '.join(f'{k}={v}' for k, v in tags.most_common(8))}")

    print(f"\n  AGREEMENT: does a cell that HAS a witness ever disagree with another?")
    for a, b in (("tag_raw", "tag_vis"), ("lca_vis", "lca_vis_nc"),
                 ("climb_raw", "climb_vis"), ("tag_raw", "climb_raw")):
        both = dis = 0
        for vs in ver.values():
            for v in vs:
                if v[a][1] == "h" and v[b][1] == "h":
                    both += 1
                    dis += v[a][0] != v[b][0]
        print(f"    {a:<11} vs {b:<11} both witnessed n={both:<6} different verdict {dis} "
              f"({dis / max(both, 1):.2%})")


COST_JS = r"""
(function () {
  // COST, AND IT IS THE QUESTION THE COVERAGE TABLE CANNOT ASK. `_climbTo`
  // runs once per search HIT (a handful). `recordAtoms` runs once per ENTRY,
  // which is hundreds to thousands per read -- so a record rule that is cheap
  // in search_page is not automatically cheap here. Interleaved, replicated,
  // order rotated per replicate (#19 / MEASUREMENT R3): a block-structured
  // timing measures the JIT warming up, not the rule.
  window.__rdcost = function (reps) {
    const reg = window.__mmidReg;
    if (!reg) return null;
    const els = [];
    for (const [, n] of reg) { if (n && n.isConnected) els.push(n); }
    const run = (which) => {
      let acc = 0;
      const t0 = performance.now();
      for (const e of els) {
        const r = which === 'tag'
          ? (e.closest ? e.closest(RECORD_SEL_) : null)
          : window.__rd.climbRecord(e);
        if (r && r !== e) {
          const a = window.__rd.atomsIn(r, false, 40);
          acc += a ? a.length : 0;
        }
      }
      return { ms: performance.now() - t0, acc };
    };
    const out = { n: els.length, tag: [], climb: [] };
    for (let i = 0; i < reps; i++) {
      const order = i % 2 ? ['climb', 'tag'] : ['tag', 'climb'];
      for (const w of order) out[w].push(run(w).ms);
    }
    return out;
  };
  return true;
})()
"""


async def cost(browser, collect_js, sites, reps=5):
    from statistics import median
    rows = []
    for name, url, settle in sites:
        ctx, page = await load(browser, name, url, collect_js, settle)
        if not page:
            continue
        try:
            await page.evaluate(COST_JS.replace("RECORD_SEL_", json.dumps(RECORD_SEL)))
            a = await collect(page, collect_js)
            r = await page.evaluate("(k)=>window.__rdcost(k)", reps)
        except Exception as exc:
            r = None
            print(f"  {name:<22} ERROR {type(exc).__name__}")
        finally:
            await ctx.close()
        if not r or not r["n"]:
            continue
        t, c = median(r["tag"]), median(r["climb"])
        # A/A FLOOR: the same arm's own spread across replicates. A delta
        # inside it is not a measurement (MEASUREMENT R3).
        spread = max(max(r["tag"]) - min(r["tag"]), max(r["climb"]) - min(r["climb"]))
        rows.append({"name": name, "els": r["n"], "tag_ms": t, "climb_ms": c,
                     "floor_ms": spread, "entries": len(a)})
        print(f"  {name:<22} elements={r['n']:<6} tag={t:>7.2f}ms  climb={c:>7.2f}ms  "
              f"delta={c - t:>+7.2f}ms  A/A floor={spread:.2f}ms", flush=True)
    if rows:
        print(f"\n  COLLECTION-TIME COST of the record rule, {len(rows)} sites")
        for k, lbl in (("tag_ms", "tag list (shipped)"), ("climb_ms", "climb (search_page)")):
            v = sorted(r[k] for r in rows)
            print(f"    {lbl:<24} median {median(v):>7.2f}ms  p90 {v[int(len(v) * .9)]:>8.2f}ms  max {v[-1]:>8.2f}ms")
        d = sorted(r["climb_ms"] - r["tag_ms"] for r in rows)
        f = sorted(r["floor_ms"] for r in rows)
        print(f"    {'delta':<24} median {median(d):>7.2f}ms  p90 {d[int(len(d) * .9)]:>8.2f}ms  max {d[-1]:>8.2f}ms")
        print(f"    {'A/A floor':<24} median {median(f):>7.2f}ms  p90 {f[int(len(f) * .9)]:>8.2f}ms  max {f[-1]:>8.2f}ms")
        worst = max(rows, key=lambda r: r["climb_ms"] - r["tag_ms"])
        print(f"    worst site: {worst['name']} {worst['els']} elements, "
              f"+{worst['climb_ms'] - worst['tag_ms']:.2f}ms")
    return rows


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
