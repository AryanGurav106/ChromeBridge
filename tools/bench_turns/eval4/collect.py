"""Rebuild runs.tsv from the subagent META FILES, never by hand.

This exists because of a defect in this eval's own harness: runs.tsv's fourth
column is consumed by `score(agent_id)`, which reads the JSONL transcript, and
I had been writing the agent's seven-line SELF-REPORT there instead. Every row
would have scored `{"error": "no transcript"}`, and in the meantime the live
table was built from the `TOOL_CALLS:` line each agent wrote about itself --
which is precisely what score.py's first docstring line forbids.

Re-scoring from transcripts changed 2 of the first 5 pairs, both because a
control agent under-counted its own calls.

The mapping comes from each agent's `description`, which this eval sets to the
exact string `eval4 <TID> <chromebridge|claude-in-chrome> arm`. A description
that does not match that shape is REFUSED rather than guessed at, and order is
mtime of the transcript, so the run order is recovered rather than remembered.

  python tools/bench_turns/eval4/collect.py          # report
  python tools/bench_turns/eval4/collect.py --write  # rewrite runs.tsv
"""
import json, os, re, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
SUB = os.path.expanduser("~/.claude/projects/-Users-aryangurav-Desktop-ChromeBridge/"
                         "b86bef56-47ca-4359-99a5-97b83519d3e0/subagents")
PAT = re.compile(r"^eval4 (T\d+) (chromebridge|claude-in-chrome) arm$")


def collect():
    rows, odd = [], []
    for m in glob.glob(os.path.join(SUB, "*.meta.json")):
        try:
            d = json.load(open(m))
        except Exception:
            continue
        desc = (d.get("description") or "").strip()
        if not desc.lower().startswith("eval4"):
            continue
        mm = PAT.match(desc)
        aid = os.path.basename(m).replace("agent-", "").replace(".meta.json", "")
        if not mm:
            odd.append((aid, desc))
            continue
        j = os.path.join(SUB, f"agent-{aid}.jsonl")
        if not os.path.exists(j):
            odd.append((aid, "no transcript on disk"))
            continue
        rows.append((os.path.getmtime(j), mm.group(1),
                     "cb" if mm.group(2) == "chromebridge" else "cic", aid))
    rows.sort()
    return rows, odd


def main():
    rows, odd = collect()
    for aid, why in odd:
        print(f"  REFUSED {aid}: {why}")
    seen = {}
    for _t, tid, arm, aid in rows:
        seen.setdefault(tid, set()).add(arm)
    dupes = [f"{t}/{a}" for t, arms in seen.items() for a in arms
             if sum(1 for r in rows if r[1] == t and r[2] == a) > 1]
    if dupes:
        print(f"  WARNING re-run(s) present, newest NOT auto-chosen: {', '.join(dupes)}")
    print(f"{len(rows)} run(s); "
          f"{sum(1 for v in seen.values() if len(v) == 2)} complete pair(s)")
    if "--write" in sys.argv:
        with open(os.path.join(HERE, "runs.tsv"), "w") as f:
            f.write("order\ttask\tarm\tagent_id\n")
            for i, (_t, tid, arm, aid) in enumerate(rows, 1):
                f.write(f"{i}\t{tid}\t{arm}\t{aid}\n")
        print("wrote runs.tsv")
    return 1 if odd or dupes else 0


if __name__ == "__main__":
    sys.exit(main())
