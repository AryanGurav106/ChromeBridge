"""Does a recorded descriptor RESOLVE to the element it was recorded for?

tools/audit_descriptors.py measured whether a descriptor is UNIQUE. That is
only half the claim and the easier half. This measures the half that matters:
build the descriptor from one page state, resolve it against another, and ask
whether the element it lands on is the element it was built for.

Three outcomes, and only one of them is a bug:

  CORRECT   resolved, and to the right element.
  REFUSED   raised Unresolved. NOT a failure -- #24's rule is that refusing and
            naming the candidates beats guessing, and a flow step that refuses
            escalates to the agent, which is the designed path.
  WRONG     resolved, to a DIFFERENT element. This is the only real defect, and
            it is the #10/#11/#12 shape: the step acts somewhere else and
            reports success. Target is zero.

GROUND TRUTH is geometry plus tag, deliberately: a descriptor carries neither
(#26 made box() opt-in, and geometry is excluded from identity precisely
because it drifts at click time). Using it HERE is sound for the same reason it
is unsound THERE -- it answers "is this the same element" for a measurement,
offline, on a deterministic replay, where nothing is moving.

MUTATIONS, because two replays of one frozen HAR barely differ and a resolver
that did nothing would still look perfect on them:

  rename-target     the control's accessible name changes -> must REFUSE
  insert-twin       a duplicate appears above a tied target -> must REFUSE
                    (this is FD8 at corpus scale: the ordinal now points at
                    something else)
  delete-target     the control is gone -> must REFUSE
  rename-neighbour  something ELSE changes -> must still RESOLVE CORRECTLY

That last one is the control and it is not optional. Without it a resolver that
raises Unresolved unconditionally scores 100% on the first three.

Usage:
    python tools/audit_flow_resolve.py            # 30 sites
    python tools/audit_flow_resolve.py --sites 8  # quick
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
from core.flows.descriptor import Unresolved, build, resolve, _targetable  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = extract("_collectInteractivePage", BG, verify=True)
TAG_JS = str(ROOT / "extension" / "listener_tag.js")
VIEWPORT = {"width": 1280, "height": 1600}
PER_SITE = 120          # cap, so one huge page cannot dominate the corpus mean


def gt(e: dict):
    """Ground-truth identity: the mmid the collector stamped on this element.

    THE FIRST VERSION OF THIS USED GEOMETRY AND WAS WRONG, in a way worth
    keeping written down. The argument for it was that a descriptor carries no
    geometry, so geometry is an independent ruler. The argument against it is
    the reason geometry is excluded from descriptors in the first place: it
    DRIFTS. On webdev the second pass laid out 521px lower -- a late image --
    so `a "File a bug"` at y=6128 and the same element at y=6649 were scored as
    different elements, and the audit reported a 13.9% silent mis-bind rate
    against a resolver that had returned the correct mmid every time. #16's
    rule, earned again: a result that damns the system gets re-derived before
    it is believed.

    mmid is the right ruler here. It is assigned by the collection walk, so it
    is independent of every field a descriptor reads, and on a deterministic
    replay of one HAR the same element is stamped with the same number both
    passes. That assumption is CHECKED per site rather than assumed -- see
    `ruler_valid` -- and a site where it does not hold is reported, not scored.
    """
    return str(e.get("mmid"))


def verdict(target: dict, want: dict, entries: list[dict]) -> str:
    try:
        ref = resolve(target, entries)
    except Unresolved:
        return "REFUSED"
    hit = next((e for e in entries if str(e.get("mmid")) == ref), None)
    if hit is None:
        return "WRONG"                     # resolved to a ref that is not there
    return "CORRECT" if gt(hit) == gt(want) else "WRONG"


# --------------------------------------------------------------------------
# Mutations. Each returns (mutated entries, the entry the step still means).
# --------------------------------------------------------------------------
def mut_rename_target(entries, tgt):
    out = []
    for e in entries:
        if gt(e) == gt(tgt):
            e = dict(e, name="zzz-renamed-by-audit", label="", text="", placeholder="")
        out.append(e)
    return out, tgt


def mut_delete_target(entries, tgt):
    return [e for e in entries if gt(e) != gt(tgt)], tgt


def mut_insert_twin(entries, tgt):
    """A duplicate of the target, inserted BEFORE it in document order.

    This is the case that silently redirects an ordinal, so it is the one the
    crowd-check exists for.
    """
    out = []
    for e in entries:
        if gt(e) == gt(tgt):
            twin = dict(e, mmid=f"twin-{e.get('mmid')}", y=(e.get("y") or 0) - 1)
            out.append(twin)
        out.append(e)
    return out, tgt


def mut_rename_neighbour(entries, tgt):
    """Change something that is NOT the target. The step must still work."""
    out, done = [], False
    for e in entries:
        if not done and gt(e) != gt(tgt) and _targetable(e) and (e.get("name") or ""):
            e = dict(e, name="zzz-other-element-changed")
            done = True
        out.append(e)
    return out, tgt


def mut_twin_elsewhere(entries, tgt):
    """A NEW control with the target's name, in a different landmark.

    This tests a design choice made on reasoning rather than evidence:
    build() stores the CHEAPEST descriptor that resolves, on the argument that
    fewer fields means fewer things to break. The counter-argument is that a
    cheap descriptor is likelier to go AMBIGUOUS later. A target recorded at
    the identity rung carries no section, so this twin collides with it; one
    recorded at the section rung does not. Either way the only unacceptable
    outcome is binding to the twin.
    """
    twin = dict(tgt, mmid=f"elsewhere-{tgt.get('mmid')}",
                section="footer", underHeading="Somewhere else",
                x=7, y=99991, w=(tgt.get("w") or 10), h=(tgt.get("h") or 10))
    return list(entries) + [twin], tgt


def mut_counter_in_name(entries, tgt):
    """A number INSIDE the accessible name changes. The control does not.

    This is #59's live failure, modelled exactly rather than approximated: a
    nav tab reading "Records 38" becomes "Records 43" because AccName 2F
    concatenates a badge that is a descendant. The element is the same element
    and the step still means it, so REFUSING here is safe but costs a model
    turn every time the data moves -- and a rebind can only ever propose
    another count-bearing name.

    A target with no digits in its name is left alone, so this mutation
    measures the population it is about rather than the whole corpus.
    """
    import re as _re
    def bump(v):
        return _re.sub(r"\d+", lambda m: str(int(m.group(0)) + 5), v or "")
    out, touched = [], False
    for e in entries:
        if gt(e) == gt(tgt) and _re.search(r"\d", (e.get("name") or "") + (e.get("label") or "")):
            e = dict(e, name=bump(e.get("name")), label=bump(e.get("label")))
            touched = True
        out.append(e)
    return (out, tgt) if touched else (None, tgt)


MUTATIONS = [
    ("rename-target", mut_rename_target, "REFUSED*"),
    ("counter-in-name", mut_counter_in_name, "CORRECT-or-REFUSED"),
    ("delete-target", mut_delete_target, "REFUSED"),
    ("insert-twin", mut_insert_twin, "REFUSED"),
    ("twin-elsewhere", mut_twin_elsewhere, "CORRECT-or-REFUSED"),
    ("rename-neighbour", mut_rename_neighbour, "CORRECT"),
]


async def collect(page) -> list[dict]:
    return await page.evaluate(
        "(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, 'brief'); })()"
    ) or []


async def two_passes(browser, name, url):
    passes = []
    for _ in range(2):
        ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True)
        await ctx.add_init_script(path=TAG_JS)
        try:
            har = FROZEN / f"{name}.har"
            if not har.exists():
                return None
            await ctx.route_from_har(str(har), not_found="abort")
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            except Exception:
                return None
            await page.wait_for_timeout(1200)
            passes.append(await collect(page))
        finally:
            await ctx.close()
    return passes


async def run_site(browser, name, url, rng) -> dict | None:
    got = await two_passes(browser, name, url)
    if not got:
        return None
    a, b = got
    if len(a) < 5 or len(b) < 5:
        return None

    targets = [e for e in a if _targetable(e)]
    if not targets:
        return None
    if len(targets) > PER_SITE:
        targets = rng.sample(targets, PER_SITE)

    # The ruler is only valid where the two passes stamp the same element with
    # the same mmid. Where they do not, the page itself differed between loads
    # (#16 names 18 of the 108 frozen sites as non-deterministic) and nothing
    # here can separate a resolver error from a corpus one, so the site is
    # reported rather than scored.
    ma = {str(e.get("mmid")) for e in a if _targetable(e)}
    mb = {str(e.get("mmid")) for e in b if _targetable(e)}
    row = {"name": name, "sampled": len(targets),
           "ruler_valid": ma == mb,
           "ruler_overlap": round(len(ma & mb) / max(len(ma | mb), 1), 4)}
    base = Counter()
    muts = {m: Counter() for m, _, _ in MUTATIONS}
    # THE ABLATION ARM, measured on the SAME target in the SAME pass. #19's
    # rule applied to an audit: running the corpus once with the fallback and
    # once without would let run-order drift align exactly with the arm, which
    # is the artefact that produced three false CLIFF verdicts in #19.
    noalt = {m: Counter() for m, _, _ in MUTATIONS}
    noalt["base"] = Counter()
    alts = 0

    for e in targets:
        t = build(e, a)
        if t.get("alt"):
            alts += 1
        t0 = {k: v for k, v in t.items() if k != "alt"}
        base[verdict(t, e, b)] += 1
        noalt["base"][verdict(t0, e, b)] += 1
        for mname, fn, _expect in MUTATIONS:
            mb, want = fn(b, e)
            if mb is None:                      # mutation does not apply here
                continue
            muts[mname][verdict(t, want, mb)] += 1
            noalt[mname][verdict(t0, want, mb)] += 1

    row["base"] = dict(base)
    row["muts"] = {k: dict(v) for k, v in muts.items()}
    row["noalt"] = {k: dict(v) for k, v in noalt.items()}
    row["alts"] = alts
    return row


def pct(c: Counter | dict, key) -> float:
    tot = sum(c.values()) or 1
    return c.get(key, 0) / tot


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for i, (name, url) in enumerate(list(SITES)[: args.sites], 1):
            try:
                r = await run_site(browser, name, url, rng)
            except Exception as exc:
                print(f"  [{i:>3}] {name:<22} ERROR {type(exc).__name__}: {exc}")
                continue
            if not r:
                print(f"  [{i:>3}] {name:<22} skipped")
                continue
            rows.append(r)
            b = Counter(r["base"])
            print(f"  [{i:>3}] {name:<22} n={r['sampled']:<4} "
                  f"correct={pct(b,'CORRECT'):>6.1%} refused={pct(b,'REFUSED'):>6.1%} "
                  f"WRONG={pct(b,'WRONG'):>6.1%}")
        await browser.close()

    if not rows:
        print("no sites measured")
        return 1

    scored = [r for r in rows if r["ruler_valid"]]
    tot = Counter()
    for r in scored:
        tot.update(r["base"])
    n = sum(tot.values())
    print(f"\n{'=' * 78}\nRESOLVE ROUND TRIP — {len(scored)} sites, {n} descriptors "
          f"built on pass A and resolved against pass B\n{'=' * 78}")
    for k in ("CORRECT", "REFUSED", "WRONG"):
        print(f"  {k:<10}{tot.get(k,0):>7}  {tot.get(k,0)/n:>7.2%}")

    bad = [r["name"] for r in rows if not r["ruler_valid"]]
    if bad:
        print(f"\n  RULER INVALID on {len(bad)} site(s) — the two passes stamped "
              f"different mmids, so the page differed between loads and a "
              f"resolver error cannot be told from a corpus one: {bad}")
        print(f"  (these are EXCLUDED from the totals above)")

    na = sum(r.get("alts", 0) for r in scored)
    print(f"\n  descriptors carrying the href ALT key: {na} of {n}  {na/n:.1%}")
    print(f"\nMUTATIONS  (expected outcome in brackets; WRONG is the only defect)")
    print(f"  * rename-target now resolves for a LINK whose destination is unchanged "
          f"and unique:\n    the href is what the step meant, and the run REPORTS "
          f"that it matched on it.")
    for mname, _fn, expect in MUTATIONS:
        mt, mz = Counter(), Counter()
        for r in scored:
            mt.update(r["muts"][mname])
            mz.update(r["noalt"][mname])
        m = sum(mt.values()) or 1
        z = sum(mz.values()) or 1
        flag = "" if mt.get("WRONG", 0) == 0 else "   <-- SILENT MIS-BIND"
        print(f"  {mname:<18}[{expect:<18}]  correct={mt.get('CORRECT',0)/m:>6.1%}"
              f"  refused={mt.get('REFUSED',0)/m:>6.1%}"
              f"  WRONG={mt.get('WRONG',0)/m:>6.1%}{flag}")
        print(f"  {'':<18} no-alt ablation      correct={mz.get('CORRECT',0)/z:>6.1%}"
              f"  refused={mz.get('REFUSED',0)/z:>6.1%}"
              f"  WRONG={mz.get('WRONG',0)/z:>6.1%}")

    worst = sorted(scored, key=lambda r: -pct(Counter(r["base"]), "WRONG"))[:5]
    if pct(Counter(worst[0]["base"]), "WRONG") > 0:
        print("\n  worst sites by silent mis-bind:")
        for r in worst:
            w = pct(Counter(r["base"]), "WRONG")
            if w:
                print(f"    {r['name']:<22}{w:>7.1%}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "resolve.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT / 'resolve.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
