"""Score the flow generality eval FROM THE ARTEFACTS, never from a self-report.

#47 found two scorer defects by noticing a self-report disagreeing with the
transcript -- the harness's own handback counted as a turn, and answer
extraction returned null for any agent that handed back without a final text
block. So nothing here reads what an agent SAID. It reads:

  * the saved flows/<name>.flow.json  -- did a flow get recorded, with what
  * runs.tsv                          -- what run_flow actually printed

Metrics and their pass bars are fixed in PREREG.md, written before the app
list existed.

Usage:  python tools/bench_flows/score.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FLOWS = ROOT / "flows"
RUNS = HERE / "runs.tsv"

# runs.tsv columns, one row per app:
#   app  origin  shape  flow_name  replay1  replay2  witness  notes
# replay1/replay2 are the literal first word of run_flow's reply:
#   PASSED | FAILED | PAUSED | NOTRECORDED
FIELDS = ["app", "origin", "shape", "flow_name", "replay1", "replay2",
          "witness", "notes"]


def load_rows():
    if not RUNS.exists():
        print(f"no {RUNS} yet")
        return []
    with RUNS.open(encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh, delimiter="\t") if r.get("app")]


def flow_facts(name: str) -> dict:
    """What the recorded artefact itself says. Independent of any claim."""
    p = FLOWS / f"{name}.flow.json"
    if not name or not p.exists():
        return {"exists": False, "steps": 0, "asserted": 0, "alts": 0, "vars": 0}
    d = json.loads(p.read_text(encoding="utf-8"))
    steps = d.get("steps") or []
    return {
        "exists": True,
        "steps": len(steps),
        "asserted": sum(1 for s in steps if s.get("expect")),
        "alts": sum(1 for s in steps
                    for t in (s.get("targets") or {}).values() if t.get("alt")),
        "vars": len(d.get("vars") or {}),
        "origin": d.get("origin", ""),
    }


def main() -> int:
    rows = load_rows()
    if not rows:
        return 1
    n = len(rows)
    print(f"{'app':<26}{'shape':<18}{'steps':>6}{'asrt':>6}{'alt':>5}"
          f"{'replay1':>9}{'replay2':>9}{'witness':>9}")
    m1 = m2 = m4 = 0
    unrecorded = []
    for r in rows:
        f = flow_facts(r["flow_name"])
        # PREREG: a flow with zero assertions does NOT count toward M1 -- it can
        # only detect a control going missing, which is not the claim.
        ok1 = r["replay1"] == "PASSED" and f["asserted"] >= 1
        ok2 = r["replay2"] == "PASSED" and f["asserted"] >= 1
        m1 += ok1
        m2 += ok2
        m4 += r.get("witness", "").strip().lower() in ("1", "yes", "true")
        if not f["exists"]:
            unrecorded.append(r["app"])
        print(f"{r['app']:<26}{r['shape']:<18}{f['steps']:>6}{f['asserted']:>6}"
              f"{f['alts']:>5}{r['replay1']:>9}{r['replay2']:>9}"
              f"{r.get('witness',''):>9}")

    print(f"\n{'=' * 78}")
    print(f"  M1 replays green (>=1 assertion) : {m1}/{n}   "
          f"{'MEETS' if m1 >= 6 else 'BELOW'} the pre-registered bar of 6/8")
    print(f"  M2 green again on a second run   : {m2}/{n}")
    print(f"  M4 witness check fired           : {m4}/{n}   "
          f"{'MEETS' if m4 >= 1 else 'below'} P4 (>=1)")
    if unrecorded:
        print(f"  NOT RECORDED AT ALL              : {unrecorded}")
    print("\n  M3 (a step binding to the WRONG element and reporting success) and")
    print("  M5 (defect classes no fixture models) are judged by reading the")
    print("  flow files and the failures, and are reported in RESULTS.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
