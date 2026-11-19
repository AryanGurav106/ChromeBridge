"""Does the SHIPPED content witness refuse when the record it names is GONE?

#83 shipped `recordAtoms` to close the re-sort mis-bind that #72 measured at
94.4% WRONG. It was measured by tools/audit_record_witness.py over eight arms:
base, resort, resort-last, resort-first, shuffle, edit-cell, bump-digits,
drop-other. **None of them removes the TARGET.**

That is #72's own lesson arriving one entry later, and docs/MEASUREMENT.md §4
states it as a rule: a mutation harness measures the code against the mutations
it models, and when a harness reports a perfect score the next question is what
it does not model.

The hazard is in the resolver's INTERSECTION rule. Atoms are recorded as the
text unique to the member within its crowd, and at replay a member "carries"
them if its atom set intersects the stored one. One shared token is therefore
enough to bind. A crowd of three invoice rows records
`['Acme Ltd', 'INV-1001', 'Paid']`; at replay INV-1001 is gone and some other
row also renders the word `Paid`; exactly one member intersects; the step binds
to an unrelated invoice and reports PASSED. Reproduced in pure Python before
this probe was written -- it needs no page at all -- which is why the probe
exists to measure PREVALENCE rather than existence.

AND THE PROBE THAT MEASURED ATOMS USED A DIFFERENT DEFINITION OF A RECORD FROM
THE ONE THAT SHIPPED. audit_record_witness.py derives a record structurally
(the lowest common ancestor of the crowd, recursed until the member stands
alone -- no tag list, by its own header). What ships in background.js is
`el.closest('tr,li,dl,article,figure,fieldset')`. Both are defensible; they are
not the same, so the shipped field's coverage is unmeasured. This probe reads
`recordAtoms` off the real collector, so the number it reports is the shipped
one.

ARMS, each a real DOM mutation of a real page, re-collected:

  base          nothing changes. The control: every descriptor must resolve to
                itself, or a WRONG elsewhere means nothing.
  drop-target   the victim's own record is removed. THE ONLY CORRECT OUTCOME IS
                A REFUSAL -- the recorded element is gone, so any binding is a
                binding to something else.
  drop-other    a DIFFERENT record is removed. The control for the fix: a rule
                that refuses here has not been made safe, it has been deleted.

RESOLVERS, both run on the SAME mutated page in the same pass so run-order
drift cannot align with the arm (#19):

  shipped       core.flows.descriptor.resolve, exactly as it runs today.
  gated         the candidate fix. When the crowd's COMPOSITION is unchanged
                (len(hits) == of) a subset of the atoms still identifies the
                member, because a cell may legitimately have changed. When the
                composition HAS changed, the record must be wholly present --
                a missing record and an edited cell are otherwise the same
                evidence, and the page declares nothing that separates them.
                Exact, not a threshold: "all of them" and "the same number as
                before" are facts, not chosen numbers.

Usage:
    python tools/audit_atoms_safety.py --sites 40
    python tools/audit_atoms_safety.py --self-test     # the firing proof
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "temp" / "frozen"
OUT = ROOT / "temp" / "descriptors"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))
from core.flows import descriptor as D  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VIEWPORT = {"width": 1280, "height": 1600}
PER_SITE = 120

# The record, spelled exactly as extension/background.js spells it for
# `recordAtoms`. A SECOND spelling here would make the probe measure a record
# the collector never used (rule 17) -- which is the defect this file exists to
# report about audit_record_witness.py, so reproducing it would be funny once.
RECORD_SEL = "tr,li,dl,article,figure,fieldset"

PAGE_JS = r"""
(function () {
  const reg = () => window.__mmidReg;
  const el = (m) => { const r = reg(); const n = r && r.get(String(m)); return n && n.isConnected ? n : null; };
  window.__as = {
    // Remove the RECORD of `mm`, spelled as background.js spells it. Returns
    // what it removed so the caller can tell a real mutation from a no-op --
    // a probe whose mutation silently did nothing reports the base arm twice
    // and calls it a pass (PRINCIPLES 5).
    dropRecord(mm) {
      const n = el(mm);
      if (!n) return 'no-node';
      const r = n.closest && n.closest(RECORD_SEL_);
      const t = (r && r !== n) ? r : n;
      if (!t.parentNode) return 'no-parent';
      t.remove();
      return (r && r !== n) ? 'record' : 'element';
    },
    hasRecord(mm) {
      const n = el(mm);
      if (!n) return false;
      const r = n.closest && n.closest(RECORD_SEL_);
      return !!(r && r !== n);
    },
  };
  return true;
})()
"""


def page_js() -> str:
    return PAGE_JS.replace("RECORD_SEL_", json.dumps(RECORD_SEL))


# ---------------------------------------------------------------------------
# The candidate fix, implemented HERE rather than in core/ so this probe can
# score both arms in one pass. It is a transcription of the diff proposed in
# docs/research/FLOW-SILENT-BIND-2026-11.md; the diff is the thing that ships.
# ---------------------------------------------------------------------------
def resolve_gated(target: dict, entries: list[dict]) -> str:
    """descriptor.resolve with the composition gate on the atoms branch."""
    desc = target.get("desc") or {}
    full = target.get("full") or desc
    pool = [e for e in entries if D._targetable(e)]
    want, nth = target.get("of"), target.get("nth")
    hits = [e for e in pool if D.matches(full if want is not None else desc, e)]

    atoms = target.get("atoms")
    if atoms:
        want_a = set(atoms)
        cand = [e for e in hits if want_a & set(e.get("recordAtoms") or [])]
        # THE GATE. Composition unchanged -> a subset still identifies the
        # member (a cell may have changed). Composition changed -> the record
        # must be wholly present, because "my row lost a cell" and "my row is
        # gone and a stranger shares a word" are the same evidence otherwise.
        if want is not None and len(hits) != want:
            cand = [e for e in cand
                    if want_a <= set(e.get("recordAtoms") or [])]
        if len(cand) != 1:
            raise D.Unresolved("atoms did not name exactly one element",
                               D._candidates(hits))
        return str(cand[0].get("mmid"))

    # Everything below is byte-for-byte the shipped behaviour; it is reached
    # only when no atoms were recorded, so it cannot be what the arms score.
    return D._resolve_recorded(target, entries)


def resolve_ungated(target: dict, entries: list[dict]) -> str:
    """The atoms branch WITHOUT the composition gate -- the behaviour that
    shipped in #83 and was corrected in #99.

    IT EXISTS ONLY SO THE FIRING PROOF CANNOT EXPIRE. The self-test originally
    asked whether `D.resolve` -- the live resolver -- was WRONG on a
    drop-target case, which was true while the defect was live and became
    false the instant the gate shipped. From then on the probe printed
    "the probe cannot fire -- it is measuring nothing" and exited 1 on a
    codebase where nothing was wrong. That is docs/MEASUREMENT.md's
    probe-lifetime rule: an A/B whose firing proof IS a defect expires when
    the defect is fixed, and the way out is to carry BOTH arms rather than to
    assume the baseline is still in the tree.

    So the proof now asks a question whose answer does not move: can this
    probe's verdict function distinguish a resolver that has the defect from
    one that does not? If it ever cannot, the probe really is measuring
    nothing.
    """
    desc = target.get("desc") or {}
    full = target.get("full") or desc
    pool = [e for e in entries if D._targetable(e)]
    want = target.get("of")
    hits = [e for e in pool if D.matches(full if want is not None else desc, e)]
    atoms = target.get("atoms")
    if atoms:
        want_a = set(atoms)
        cand = [e for e in hits if want_a & set(e.get("recordAtoms") or [])]
        if len(cand) != 1:
            raise D.Unresolved("atoms did not name exactly one element",
                               D._candidates(hits))
        return str(cand[0].get("mmid"))
    return D._resolve_recorded(target, entries)


def resolve_gated_alt(target: dict, entries: list[dict]) -> str:
    try:
        return resolve_gated(target, entries)
    except D.Unresolved:
        alt = target.get("alt")
        if not alt:
            raise
        pool = [e for e in entries if D._targetable(e)]
        hits = [e for e in pool if D.matches(alt, e)]
        if len(hits) != 1:
            raise
        return str(hits[0].get("mmid"))


# ---------------------------------------------------------------------------


def crowd_id(crowd) -> str:
    return ",".join(sorted(str(e.get("mmid")) for e in crowd))


def crowds_of(entries):
    pool = [e for e in entries if D._targetable(e)]
    groups: dict = {}
    for e in pool:
        groups.setdefault(json.dumps(D.at_level(e, D.FULL), sort_keys=True),
                          []).append(e)
    return [g for g in groups.values() if len(g) >= 2]


def verdict(fn, target, entries, want_mmid):
    """CORRECT / REFUSED / WRONG, where CORRECT depends on the arm.

    `want_mmid=None` means the recorded element is GONE, so the only correct
    answer is a refusal.
    """
    try:
        got = fn(target, entries)
    except D.Unresolved:
        return "REFUSED"
    except Exception:
        return "REFUSED"
    if want_mmid is None:
        return "WRONG"
    return "CORRECT" if str(got) == str(want_mmid) else "WRONG"


async def collect(page, COLLECT):
    return await page.evaluate(
        "(function(){ " + COLLECT
        + "; return _collectInteractivePage(true, null, 'brief'); })()") or []


async def load(browser, name, url, TAG_JS):
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


async def run_site(browser, name, url, COLLECT, TAG_JS, rows, cov):
    """One site: build descriptors on a clean load, then score each arm on its
    own fresh load (a DOM removal is destructive, so arms cannot share one)."""
    ctx, page = await load(browser, name, url, TAG_JS)
    if not page:
        return 0
    try:
        base_entries = await collect(page, COLLECT)
    finally:
        await ctx.close()
    if len(base_entries) < 4:
        return 0

    by_mm = {str(e.get("mmid")): e for e in base_entries}
    targets = []
    for crowd in crowds_of(base_entries):
        for e in crowd[:PER_SITE]:
            t = D.build(e, base_entries)
            if t.get("of") is None:
                continue
            cov["ordinal"] += 1
            cov["atoms"] += bool(t.get("atoms"))
            cov["witness"] += bool(t.get("witness"))
            cov["neither"] += not (t.get("atoms") or t.get("witness"))
            if t.get("atoms"):
                targets.append((str(e.get("mmid")), t, crowd))
        if len(targets) >= PER_SITE:
            break
    if not targets:
        return 0

    # The crowds the scored targets belong to, and the ONE member of each that
    # both drop arms remove. Deterministic (the first member in document
    # order) so the two arms are comparable and a re-run reproduces.
    crowd_victims: dict = {}
    for _mm, _t, _crowd in targets:
        crowd_victims.setdefault(crowd_id(_crowd),
                                 [str(e.get("mmid")) for e in _crowd])

    for arm in ("base", "drop-target", "drop-other"):
        ctx, page = await load(browser, name, url, TAG_JS)
        if not page:
            continue
        try:
            await page.evaluate(page_js())
            # COLLECT ONCE BEFORE MUTATING. `window.__mmidReg` is built BY the
            # collection walk, so a mutation issued before it has no way to
            # resolve an mmid to a node. The first version of this probe
            # mutated first: every call returned 'no-node', both drop arms
            # contributed ZERO rows, and the run reported only `base`. It
            # failed loudly rather than reporting a flattering zero, which is
            # the only reason it was caught (#16).
            await collect(page, COLLECT)
            # ONE VICTIM PER CROWD, and both drop arms use the SAME one.
            #
            # The first version chose a victim PER TARGET, and several targets
            # share a crowd -- so for target A it dropped B's record and for
            # target B it dropped A's, and then scored BOTH as `drop-other`
            # with both records gone. That reported `drop-other` at 53.3%
            # CORRECT against #83's 96.3%, which is what made it worth
            # re-deriving (#16): a control arm that quietly contains the
            # treatment cannot say whether the treatment is safe.
            dropped = {}
            if arm != "base":
                for _cid, members in crowd_victims.items():
                    v = members[0]
                    dropped[v] = await page.evaluate(
                        "(m)=>window.__as.dropRecord(m)", v)
            ents = await collect(page, COLLECT)
        finally:
            await ctx.close()

        for mm, t, crowd in targets:
            cid = crowd_id(crowd)
            victim = crowd_victims[cid][0]
            if arm == "drop-target":
                if mm != victim:
                    continue                      # scored on the victim only
                if dropped.get(victim) not in ("record", "element"):
                    continue                      # mutation did not apply
                want = None                       # gone: refusal is correct
            elif arm == "drop-other":
                if mm == victim:
                    continue                      # that is the other arm
                if dropped.get(victim) not in ("record", "element"):
                    continue
                want = mm                         # intact: must still resolve
            else:
                want = mm
            rows.append({
                "site": name, "arm": arm, "mmid": mm,
                "n_atoms": len(t.get("atoms") or []),
                "shipped": verdict(lambda a, b: D.resolve(a, b), t, ents, want),
                "gated": verdict(lambda a, b: resolve_gated_alt(a, b), t, ents, want),
                "name": (by_mm.get(mm, {}).get("name") or "")[:40],
                "tag": by_mm.get(mm, {}).get("tag") or "",
            })
    return 1


def self_test() -> int:
    """The firing proof. A detector reporting zero is worth nothing until it has
    been shown to fire (PRINCIPLES 5), and the controls are what separate "this
    is safe now" from "this refuses everything"."""
    def row(mm, company, inv, status):
        return {"mmid": str(mm), "tag": "button", "role": "", "type": "",
                "name": "Delete", "label": "", "placeholder": "",
                "text": "Delete", "section": "main", "underHeading": "Invoices",
                "near": "", "href": "", "clickable": True,
                "recordAtoms": [company, inv, status, "Delete"]}

    rec = [row(11, "Acme Ltd", "INV-1001", "Paid"),
           row(13, "Beta Inc", "INV-1002", "Pending"),
           row(15, "Gamma Co", "INV-1003", "Pending")]
    t = D.build(rec[0], rec)
    assert t.get("atoms"), "fixture does not reach the atoms path"

    cases = [
        # label,                               entries,                        want
        ("base: resolves to itself",           rec,                            "11"),
        ("re-sort: still resolves",            [rec[2], rec[0], rec[1]],       "11"),
        ("drop-other: still resolves",         [rec[0], rec[2]],               "11"),
        ("drop-target + shared company",
         [row(13, "Beta Inc", "INV-1002", "Pending"),
          row(15, "Acme Ltd", "INV-1099", "Pending")],                         None),
        ("drop-target + shared STATUS only",
         [row(13, "Beta Inc", "INV-1002", "Pending"),
          row(15, "Delta SA", "INV-1099", "Paid")],                            None),
        ("drop-target, nothing shared",
         [row(13, "Beta Inc", "INV-1002", "Pending"),
          row(15, "Delta SA", "INV-1099", "Pending")],                         None),
        # The edit-cell control: composition UNCHANGED and one cell changed.
        # The gate must still resolve here, or it has deleted the tolerance the
        # intersection rule exists for.
        ("edit-cell (composition same)",
         [row(11, "Acme Ltd", "INV-1001", "Overdue"), rec[1], rec[2]],         "11"),
    ]
    bad = 0
    print(f"{'case':<38} {'shipped':>10} {'gated':>10}   expected")
    for label, ents, want in cases:
        s = verdict(lambda a, b: D.resolve(a, b), t, ents, want)
        g = verdict(lambda a, b: resolve_gated_alt(a, b), t, ents, want)
        exp = "CORRECT" if want else "REFUSED"
        ok = (g == exp)
        bad += not ok
        print(f"{label:<38} {s:>10} {g:>10}   {exp}{'' if ok else '   <-- GATE FAILS'}")
    # THE FIRING PROOF, re-based so it cannot expire (see resolve_ungated).
    # It used to ask whether the SHIPPED resolver is WRONG here, which stopped
    # being true the moment the gate shipped -- and the probe then reported
    # "measuring nothing" on a healthy tree.
    fired = any(
        verdict(lambda a, b: resolve_ungated(a, b), t, ents, want) == "WRONG"
        for label, ents, want in cases if want is None)
    live_ok = all(
        verdict(lambda a, b: D.resolve(a, b), t, ents, want) != "WRONG"
        for label, ents, want in cases if want is None)
    print()
    print(f"detector fires against a resolver WITHOUT the gate: {fired}")
    if not fired:
        print("  !! the probe cannot report WRONG -- it is measuring nothing")
        bad += 1
    print(f"the SHIPPED resolver is clean on every drop-target case: {live_ok}")
    if not live_ok:
        print("  !! the gate has regressed in core/flows/descriptor.py")
        bad += 1
    return 1 if bad else 0


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", type=int, default=40)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()

    from playwright.async_api import async_playwright
    from _extract import extract
    from capture_listings import SITES
    BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
    COLLECT = extract("_collectInteractivePage", BG, verify=True)
    TAG_JS = str(ROOT / "extension" / "listener_tag.js")

    rows: list = []
    cov = Counter()
    # SITES rows are 2- OR 3-tuples (some carry a post-load action), which is
    # what the first run of this probe crashed on after 25 sites. Take the two
    # fields every row has rather than restating the shape (PRINCIPLES 17).
    _rows = SITES.items() if isinstance(SITES, dict) else SITES
    sites = [(s[0], s[1]) for s in _rows][: args.sites]
    done = 0
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        for name, url in sites:
            try:
                done += await run_site(browser, name, url, COLLECT, TAG_JS,
                                       rows, cov)
            except Exception as exc:
                print(f"  ! {name}: {type(exc).__name__}: {exc}"[:140])
            print(f"\r  {done} site(s), {len(rows)} scored row(s)",
                  end="", flush=True)
        await browser.close()
    print()

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "atoms_safety.json").write_text(
        json.dumps({"cov": dict(cov), "rows": rows}, indent=1), encoding="utf-8")

    print(f"\nsites contributing: {done}")
    print("\nCOVERAGE of the SHIPPED recordAtoms, over ordinal-bearing descriptors")
    o = cov["ordinal"] or 1
    print(f"  ordinal-bearing            {cov['ordinal']}")
    print(f"  ...carrying atoms          {cov['atoms']}  ({cov['atoms']/o:.1%})")
    print(f"  ...carrying a witness      {cov['witness']}  ({cov['witness']/o:.1%})")
    print(f"  ...carrying NEITHER        {cov['neither']}  ({cov['neither']/o:.1%})")

    print("\nRESOLUTION, atoms-bearing descriptors only")
    hdr = f"{'arm':<14}{'n':>6}  {'resolver':<9}{'CORRECT':>9}{'REFUSED':>9}{'WRONG':>9}"
    print(hdr)
    for arm in ("base", "drop-target", "drop-other"):
        sub = [r for r in rows if r["arm"] == arm]
        if not sub:
            continue
        for key in ("shipped", "gated"):
            c = Counter(r[key] for r in sub)
            n = len(sub)
            print(f"{arm if key=='shipped' else '':<14}{n if key=='shipped' else '':>6}  "
                  f"{key:<9}{c['CORRECT']/n:>8.1%}{c['REFUSED']/n:>9.1%}"
                  f"{c['WRONG']/n:>9.1%}")

    wrong = [r for r in rows if r["arm"] == "drop-target" and r["shipped"] == "WRONG"]
    if wrong:
        print(f"\nSILENT MIS-BINDS under drop-target (shipped): {len(wrong)}")
        for r in wrong[:10]:
            print(f"   {r['site']:<18} ref_{r['mmid']:<8} {r['tag']:<8} "
                  f"{r['n_atoms']} atom(s)  {r['name']!r}")
        print(f"   sites affected: "
              f"{sorted({r['site'] for r in wrong})}")
    print(f"\n  raw -> {OUT / 'atoms_safety.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
