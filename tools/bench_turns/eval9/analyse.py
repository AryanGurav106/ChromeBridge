# -*- coding: utf-8 -*-
"""EVAL 9 analysis. Bars, task set and exclusion rule were fixed in PREREG.md
before any run; Amendments 1-8 are dated and each was written before the run it
affects, except 7 and 8, which RECORD what a completed wave found and change no
bar.

Reuses referee.py's `_norm` rather than restating it. A grader that normalises
differently from the referee is two spellings of one concept (#21), and the
difference would show up as a task the referee confirmed and the grader marked
wrong -- which reads as an arm failing.
"""
import importlib.util, json, math, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("_ref", HERE / "referee.py")
_ref = importlib.util.module_from_spec(_spec)
try:
    _spec.loader.exec_module(_ref)            # imports playwright at module level
    _norm = _ref._norm
except Exception:                             # noqa: BLE001
    print("note: referee.py would not import (playwright missing?); "
          "falling back to a COPY of its _norm -- fix before quoting a number",
          file=sys.stderr)
    import re
    def _norm(s):
        s = (s or "").replace(" ", " ")
        s = re.sub(r"[‐-―−]", "-", s)
        s = s.replace("×", "x").replace(" ", " ").replace(" ", " ")
        return re.sub(r"\s+", " ", s).strip().casefold()


def sign_p(k, n):
    """Two-sided sign test. k = the LARGER side."""
    if not n:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n)


GT = {r["id"]: r for r in json.loads((HERE / "ground_truth.json").read_text("utf-8"))}

rows = []
for line in (HERE / "runs.tsv").read_text("utf-8").strip().splitlines()[1:]:
    t, arm, ans, calls, status, defect, note = (line.split("\t") + [""] * 7)[:7]
    rows.append(dict(task=t, arm=arm, answer=ans, calls=int(calls),
                     status=status, defect=defect, note=note))

by = {}
for r in rows:
    by.setdefault(r["task"], {})[r["arm"]] = r

pairs, wrong, excluded = [], [], []
print(f"{'task':<5} {'CB':>3} {'CIC':>4}  {'win':<4}  status")
for t in sorted(by, key=lambda x: int(x[1:])):
    cb, cic = by[t].get("cb"), by[t].get("cic")
    if not (cb and cic):
        continue
    for r in (cb, cic):
        want = GT[t].get("onpage") or GT[t]["answer"]
        if _norm(want) not in _norm(r["answer"]):
            wrong.append(f"{t}/{r['arm']}: {r['answer'][:50]!r}")
    # AMENDMENT 5: a pair solved by typing a RECALLED deep url measures prior
    # knowledge, not the toolset, so it is excluded rather than scored. It is
    # recorded in runs.tsv all the same -- deleting it would hide the fact that
    # one of the tasks could be shortcut at all.
    if "shortcut" in (cb["status"], cic["status"]):
        excluded.append(t)
        print(f"{t:<5} {cb['calls']:>3} {cic['calls']:>4}  --    EXCLUDED (shortcut)")
        continue
    win = ("CB" if cb["calls"] < cic["calls"] else
           "CIC" if cb["calls"] > cic["calls"] else "tie")
    pairs.append((t, cb, cic, win))
    print(f"{t:<5} {cb['calls']:>3} {cic['calls']:>4}  {win:<4}")

dec = [p for p in pairs if p[3] != "tie"]
k = sum(1 for p in dec if p[3] == "CB")
n = len(dec)
p = sign_p(max(k, n - k), n)
best = sign_p(n, n)
print(f"\nH1 PRIMARY: {k}/{n} decided pairs to CB "
      f"({len(pairs) - n} tie, {len(excluded)} excluded)")
print(f"  p = {p:.4f}   best achievable at n={n} is {best:.4f}   -> "
      + ("CLEARS p<0.05" if p < 0.05 else "TIE (fails the pre-registered bar)"))

cbt = sum(pr[1]["calls"] for pr in pairs)
cict = sum(pr[2]["calls"] for pr in pairs)
gap = abs(cbt - cict) / max(cbt, cict)
print(f"\nTOTAL calls over scored pairs: CB {cbt} | CIC {cict}   "
      f"gap {gap:.1%}")
print("  arXiv:2608.06171 measures a 12-14% rerun floor for this kind of A/B, "
      "so a totals gap\n  inside that band is NOT a result. "
      + ("INSIDE the band." if gap <= 0.14 else "Outside the band."))

print(f"\nFALSIFIER (correctness vs the referee's key): "
      f"{len(wrong)} wrong of {2 * len(pairs) + 2 * len(excluded)}"
      + ("" if not wrong else "  -> " + "; ".join(wrong)))

# THE DEFECT TAX, COUNTED FROM AN EXPLICIT COLUMN. Amendment 7 records a guard
# of mine that reports NO EFFECT for a click that DID navigate. My first version
# of this counted it by matching phrases in the free-text note, and it scored
# CIC at 1 when T11/cic plainly has one too: "never navigat" does not match "did
# not navigate". A grep over prose I wrote myself is a detector that cannot fire,
# which is the exact class this project keeps finding in other people's code. The
# judgement is now a column; this only tallies it.
KINDS = {
 "cb-noeffect-fp":     "CB: our NO EFFECT token on a click that DID work",
 "cb-false-success?":  "CB: a click reported success and seems not to have navigated"
                       " (the agent's own wording did not separate this from the"
                       " line above -- UNPROVEN, kept because resolving it in our"
                       " favour is the one thing a scorer must not do)",
 "cic-false-success":  "CIC: a click reported success and did not navigate",
 "cic-click-dead":     "CIC: a ref click did not navigate (report wording not stated)",
}
print("\nCLICK-REPORTING DEFECTS over the 7 scored pairs:")
scored = {pr[0] for pr in pairs}
for kind, label in KINDS.items():
    hit = sorted({r["task"] for r in rows
                  if r["task"] in scored and kind in r["defect"].split(",")},
                 key=lambda x: int(x[1:]))
    print(f"  {len(hit)}/7  {label}\n        {hit}")
cb_hit = {r["task"] for r in rows if r["arm"] == "cb" and r["task"] in scored and r["defect"]}
print(f"\n  CB runs losing calls to a click that misreported: {len(cb_hit)}/7")
print("  Both products are currently wrong about what a click did. Ours OVER-warns,")
print("  which costs a re-check. Theirs UNDER-warns, which costs the agent its")
print("  belief about which page it is on.")
