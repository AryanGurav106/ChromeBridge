"""Score eval 7 against WebPageBench's event oracle, with PARTIAL credit.

The point of this eval is the partial credit. Every previous head-to-head in
`bench_turns/` reported correctness saturated at 100% on both arms, because both
arms are the same model (#41). These tasks carry up to 10 conditions each, so an
agent that books the right train for the wrong number of passengers scores 7/10
and the metric can still discriminate.

ROUTE NOTE THAT COST EVAL 6 A WRONG VERDICT: events come from `POST /event/get`.
`POST /track/get` returns the CONFIG. Reading events from the config endpoint
reports FAIL on a task that PASSED.

Grouped conditions are ALTERNATIVES (the benchmark's own client ORs them);
ungrouped ones must each hold. For the per-task credit a group counts as ONE
condition, satisfied if any member holds -- otherwise a task offering three ways
to do one thing would score 1/3 for doing it.

Run:  python tools/bench_turns/eval7/score.py [--turns runs.tsv]
"""

from __future__ import annotations

import argparse
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

HOST = "http://localhost:8080"
HERE = Path(__file__).resolve().parent


def _post(path: str, data: dict) -> dict:
    req = urllib.request.Request(
        HOST + path, data=urllib.parse.urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


# Frozen in PREREG Amendment 1 after run 1 found it, and READ rather than
# restated, so the prose and the arithmetic cannot drift (rule 17). Three of the
# eight tasks hard-code a date two months in the app's past, and the app's
# calendar has exactly one navigation control -- forward -- and no date input.
# Both arms meet the identical wall, so these are uninformative rather than
# unfair; the eval reports BOTH denominators and never one alone.
_UNREACH = json.loads((HERE / "unreachable.json").read_text(encoding="utf-8"))


def _is_unreachable(key: str, c: dict) -> bool:
    for u in _UNREACH["conditions"]:
        if (u["key"] == key and u["event_name"] == c.get("event_name")
                and u["parameters"] == (c.get("parameters") or {})):
            return True
    return False


def score(track_id: str, conds: list, key: str = "") -> dict:
    events = _post("/event/get", {"track_id": track_id}).get("events", []) or []
    for e in events:
        if isinstance(e.get("event_data"), str):
            try:
                e["event_data"] = json.loads(e["event_data"])
            except Exception:
                pass

    def holds(c):
        want, params = c.get("event_name"), (c.get("parameters") or {})
        for e in events:
            if e.get("event_name") != want:
                continue
            d = e.get("event_data") or {}
            if all(str(d.get(k)) == str(v) for k, v in params.items()):
                return True
        return False

    groups, loose = {}, []
    for c in conds:
        g = c.get("group")
        (groups.setdefault(g, []).append(c) if g else loose.append(c))
    units = [(f"g{g}", any(holds(c) for c in cs), False) for g, cs in groups.items()]
    units += [(c.get("event_name", "?"), holds(c), _is_unreachable(key, c))
              for c in loose]
    # `sum(1 for _, ok in units)` counts the UNITS, not the satisfied ones. The
    # first run of this scorer reported 39/39 and 8/8 PASS against a benchmark
    # nobody had touched -- impossible, and visible only because the `unmet`
    # list printed underneath disagreed with it. #16: a result that flatters the
    # system gets re-derived before it is believed.
    met = sum(1 for _, ok, _u in units if ok)
    # Amendment 1 point 3: an arm that DOES satisfy one of the four is believed,
    # and the exclusion is withdrawn for it. The claim is that we measured it
    # unreachable, not that it must be.
    unreach = [n for n, ok, u in units if u and not ok]
    reach = len(units) - len(unreach)
    return {"track": track_id, "units": len(units), "met": met,
            "reachable": reach, "events": len(events),
            "passed": bool(units) and met == len(units),
            "passed_reachable": bool(units) and met == reach,
            "unreachable": unreach,
            "unmet": [n for n, ok, _u in units if not ok]}


def _sign_p(wins: int, losses: int) -> float:
    n = wins + losses
    if not n:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", default=str(HERE / "runs.tsv"),
                    help="optional key\\tarm\\tbrowser_calls rows")
    a = ap.parse_args()
    rows = json.loads((HERE / "tracks.json").read_text(encoding="utf-8"))
    by_key = {}
    out = []
    for r in rows:
        try:
            s = score(r["track"], r["conditions"], r["key"])
        except Exception as e:                                   # noqa: BLE001
            s = {"track": r["track"], "units": len(r["conditions"]), "met": None,
                 "reachable": None, "events": 0, "passed": None,
                 "passed_reachable": None, "unreachable": [], "unmet": [],
                 "error": str(e)[:60]}
        s.update(key=r["key"], arm=r["arm"], task_file=r["task_file"])
        out.append(s)
        by_key.setdefault(r["key"], {})[r["arm"]] = s

    turns = {}
    tp = Path(a.turns)
    if tp.exists():
        for line in tp.read_text(encoding="utf-8").splitlines():
            p = line.split("\t")
            if len(p) >= 3 and p[2].strip().lstrip("-").isdigit():
                turns[(p[0].strip(), p[1].strip())] = int(p[2])

    print(f"{'task':12} {'conds':>5} | {'CB met':>7} {'pass':>5} {'turns':>6} "
          f"| {'CIC met':>8} {'pass':>5} {'turns':>6} | winner")
    w = l = 0
    tot = {"cb": 0, "cic": 0}
    pas = {"cb": 0, "cic": 0}
    trn = {"cb": 0, "cic": 0}
    for key in [r["key"] for r in rows if r["arm"] == "cb"]:
        c, i = by_key[key].get("cb", {}), by_key[key].get("cic", {})
        cm, im = c.get("met"), i.get("met")
        ct, it = turns.get((key, "cb")), turns.get((key, "cic"))
        for arm, s, t in (("cb", c, ct), ("cic", i, it)):
            if s.get("met") is not None:
                tot[arm] += s["met"]
                pas[arm] += 1 if s.get("passed_reachable") else 0
            if t:
                trn[arm] += t
        win = ""
        if cm is not None and im is not None and cm != im:
            win = "CB" if cm > im else "CIC"
            w, l = (w + 1, l) if cm > im else (w, l + 1)
        print(f"{key:12} {c.get('units', '?'):>5} | {str(cm):>7} "
              f"{'Y' if c.get('passed') else '.':>5} {str(ct or '-'):>6} "
              f"| {str(im):>8} {'Y' if i.get('passed') else '.':>5} "
              f"{str(it or '-'):>6} | {win}")
    n = len(rows) // 2
    all_c = sum(len(r["conditions"]) for r in rows if r["arm"] == "cb")
    n_unr = len(_UNREACH["conditions"])
    print(f"\n{'TOTAL conditions met':28} CB {tot['cb']:>3} / {all_c}      "
          f"CIC {tot['cic']:>3} / {all_c}   (as pre-registered)")
    print(f"{'  ...of the REACHABLE ones':28} CB {tot['cb']:>3} / {all_c - n_unr}      "
          f"CIC {tot['cic']:>3} / {all_c - n_unr}   "
          f"({n_unr} excluded, PREREG Amendment 1)")
    print(f"{'tasks passed (reachable)':28} CB {pas['cb']:>3} / {n}       "
          f"CIC {pas['cic']:>3} / {n}")
    if any(trn.values()):
        print(f"{'browser tool calls':28} CB {trn['cb']:>3}          CIC {trn['cic']:>3}")
    dec = w + l
    best = (2 / (2 ** n)) if n else 1.0
    print(f"\nH1 decided tasks: {dec}/{n}  (CB {w}, CIC {l})  "
          f"p={_sign_p(w, l):.4f}   best achievable at n={n}: {best:.4f}")
    if dec < 6:
        print("   fewer than 6 decided -> DESCRIPTIVE ONLY, per the pre-registration.")
    for s in out:
        if s.get("unreachable"):
            print(f"   {s['track']:22} UNREACHABLE (excluded): "
                  f"{', '.join(s['unreachable'])}")
    for s in out:
        if s.get("unmet"):
            print(f"   {s['track']:22} unmet: {', '.join(s['unmet'])[:80]}")
    (HERE / "scores.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
