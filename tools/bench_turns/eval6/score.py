"""Score an eval-6 run against WebPageBench's event oracle.

NOT a judge model and not a self-report. The oracle is a semantic event the
app's own business logic emits AFTER the state mutation; `check()` in their
client imports only requests/os/json/re/datetime. A real run confirmed the
condition keys on NEITHER the `click` nor the `scroll` that the generic tracker
also logs, so it cannot see how the agent acted or what it was shown.

ONE ROUTE NOTE THAT COST A WRONG VERDICT: events come from `POST /event/get`.
`POST /track/get` returns the CONFIG. Reading events from the config endpoint
reports FAIL on a task that PASSED -- caught by reading the server's own log
rather than believing the verdict.

Run:  python tools/bench_turns/eval6/score.py [track_id ...]
"""

from __future__ import annotations

import json
import sys
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


def score(track_id: str) -> dict:
    cfg = json.loads(_post("/track/get", {"track_id": track_id}).get("config", "{}"))
    conds = cfg.get("test_data", {}).get("conditions", []) or []
    events = _post("/event/get", {"track_id": track_id}).get("events", []) or []
    for e in events:
        if isinstance(e.get("event_data"), str):
            try:
                e["event_data"] = json.loads(e["event_data"])
            except Exception:
                pass

    # Grouped conditions are alternatives (their client's own OR rule);
    # ungrouped ones must each hold.
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
        (groups.setdefault(g, []) if g else loose).append(c) if g else loose.append(c)
    per = [{"cond": c, "pass": holds(c)} for c in conds]
    ok_loose = all(holds(c) for c in loose)
    ok_groups = all(any(holds(c) for c in cs) for cs in groups.values())
    return {"track": track_id, "conditions": len(conds), "events": len(events),
            "names": sorted({e.get("event_name") for e in events if e.get("event_name")}),
            "per": per, "passed": bool(conds) and ok_loose and ok_groups}


def main() -> int:
    ids = sys.argv[1:]
    if not ids:
        rows = json.loads((HERE / "tracks.json").read_text(encoding="utf-8"))
        ids = [r["track"] for r in rows]
    out = []
    for t in ids:
        try:
            out.append(score(t))
        except Exception as e:
            out.append({"track": t, "error": str(e)[:80], "passed": None})
    print(f"{'track':22} {'conds':>5} {'events':>7} {'verdict':>9}   events seen")
    for r in out:
        if r.get("error"):
            print(f"{r['track']:22} {'-':>5} {'-':>7} {'ERROR':>9}   {r['error']}")
            continue
        v = "PASS" if r["passed"] else ("no events" if not r["events"] else "FAIL")
        print(f"{r['track']:22} {r['conditions']:>5} {r['events']:>7} {v:>9}   "
              f"{','.join(r['names'])[:58]}")
        for p in r["per"]:
            if not p["pass"]:
                print(f"{'':22} unmet: {json.dumps(p['cond'], ensure_ascii=False)[:90]}")
    (HERE / "scores.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
