# -*- coding: utf-8 -*-
"""Score eval 10 from ARTEFACTS, never from an agent's self-report.

Eval 5 found two scorer defects by noticing a self-report disagreeing with the
transcript, and eval 9's defect tally first grepped prose the scorer's own
author had written. So nothing here reads a NOTES line: turns come from the
transcript, and everything about a replay comes from the saved `.flow.json` and
`run_flow`'s own output.

THE METRIC IS THE SECOND RUN. Eval 9 settled the first-run axis at p = 1.0000,
so the first run is setup whose cost is reported and is not the headline:

  H1  median model calls to REPEAT a completed task; CB must be < 25% of CIC's.
  H2  every PASSING replay must have checked a postcondition that would FAIL if
      the step did nothing. `record_flow(stop)` emits `UNPROVEN` / `hollow` /
      `unwitnessed absence` review lines, and a step carrying only those has not
      earned its pass. TARGET 100%, and a miss is the headline rather than a
      footnote -- a replay that passes vacuously is worth less than no replay,
      and this project has shipped that bug twice.
  H3  after the app is CHANGED, a replay either resolves and SAYS the page
      moved, or refuses and names candidates. A silent wrong bind FALSIFIES the
      whole eval.

Run:  python tools/bench_turns/eval10/score.py
"""
from __future__ import annotations

import json
import pathlib
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
FLOWS = HERE.parent.parent.parent / "flows"

# A review tag that means the assertion carries no evidence it would have
# failed. Read from the recorder's own vocabulary rather than restated as prose.
HOLLOW = ("hollow:", "unproven:", "dropped:")


def _flow(name: str) -> dict | None:
    p = FLOWS / f"{name}.flow.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def h2_for(flow: dict) -> tuple[int, int, list]:
    """(steps with a check that COULD fail, steps with any check, the weak ones).

    A step whose every review line is hollow/unproven has an assertion nobody
    has seen change, which is exactly the line `record_flow` tells you to read
    first in review.
    """
    strong, any_check, weak = 0, 0, []
    for i, s in enumerate(flow.get("steps") or []):
        exp = s.get("expect") or {}
        if not exp:
            continue
        any_check += 1
        rev = [r for r in (s.get("review") or [])]
        bad = [r for r in rev if any(r.startswith(h) for h in HOLLOW)]
        # Weak only when EVERY assertion on the step is unevidenced. A step with
        # one proven check and one unproven one is still able to fail.
        if bad and len(bad) >= len(rev) and len(rev) > 0 and len(exp) <= len(bad):
            weak.append((i, s.get("name"), bad[0][:70]))
        else:
            strong += 1
    return strong, any_check, weak


def main() -> int:
    runs_p = HERE / "runs.tsv"
    if not runs_p.exists():
        print("runs.tsv not written yet — no runs have happened.")
        return 1
    rows = []
    for line in runs_p.read_text(encoding="utf-8").strip().splitlines()[1:]:
        f = line.split("\t")
        if len(f) < 6:
            continue
        rows.append({"task": f[0], "arm": f[1], "phase": f[2],
                     "calls": int(f[3]), "status": f[4], "note": f[5]})

    rep = {}
    for r in rows:
        if r["phase"] == "repeat":
            rep.setdefault(r["task"], {})[r["arm"]] = r["calls"]
    pairs = [(t, v["cb"], v["cic"]) for t, v in sorted(rep.items())
             if "cb" in v and "cic" in v]
    print(f"{'task':<6} {'CB repeat':>10} {'CIC repeat':>11}  ratio")
    for t, a, b in pairs:
        print(f"{t:<6} {a:>10} {b:>11}  {a/max(b,1):.2f}")
    if pairs:
        ratio = statistics.median(a / max(b, 1) for _, a, b in pairs)
        print(f"\nH1 median repeat ratio {ratio:.2f} "
              + ("-> MEETS < 0.25" if ratio < 0.25 else "-> DOES NOT MEET < 0.25"))
    else:
        print("\nH1 no completed repeat pairs yet")

    print("\nH2 — would each passing replay have FAILED if the step did nothing?")
    tot_strong = tot_any = 0
    for t, *_ in pairs or []:
        fl = _flow(f"e10-{t.lower()}")
        if not fl:
            print(f"  {t}: no flow recorded")
            continue
        strong, any_check, weak = h2_for(fl)
        tot_strong += strong
        tot_any += any_check
        print(f"  {t}: {strong}/{any_check} step(s) with an assertion that could fail"
              + ("" if not weak else f"   WEAK: {weak}"))
    if tot_any:
        print(f"  TOTAL {tot_strong}/{tot_any} = {tot_strong/tot_any:.0%} "
              + ("-> MEETS 100%" if tot_strong == tot_any else "-> BELOW 100%, "
                 "which is the headline, not a footnote"))

    print("\nH3 — after the app changed, did any replay bind SILENTLY to the "
          "wrong element?")
    bad = [r for r in rows if r["phase"] == "changed" and r["status"] == "wrong-silent"]
    print(f"  {len(bad)} silent wrong bind(s)"
          + ("  -> FALSIFIED" if bad else "  -> clean"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
