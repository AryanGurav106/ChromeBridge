"""Build `ground_truth.json` from the referee key.

The key is prose, written by a referee that drove every task. The scorer needs
JSON, and the conversion must be MECHANICAL — a hand-copied key is how #48's
correctness falsifier fired on BOTH arms, which is the signature of a broken
ruler rather than a broken system (the accept value had been transcribed with
the wrong Unicode codepoint).

So this parses the key and refuses anything it cannot parse, rather than
guessing. Run it, read what it refuses, fix the KEY, run it again.

  python tools/bench_turns/eval4/build_gt.py            # parse + report
  python tools/bench_turns/eval4/build_gt.py --write    # write ground_truth.json

REJECTED tasks in the key are dropped from the ground truth entirely, so a
dropped task cannot be scored by accident. Tasks marked DROPPED in tasks.md
(T15, T18 — see PREREG Amendment 3) are dropped here too, and the two lists
must agree: a task dropped in one place and live in the other is the
half-contract shape this project keeps finding.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = os.path.join(HERE, "referee_key.md")
TASKS = os.path.join(HERE, "tasks.md")
OUT = os.path.join(HERE, "ground_truth.json")

# Shapes, from PREREG. The letters are the scorer's, not the author's prose.
SHAPE_OF = {
    "multi-step form": "F", "form with dependency": "F", "validation": "F",
    "filter": "L", "sort": "L", "paginate": "L",
    "drill down": "D", "drill-down": "D",
    "late-loading": "A", "loads after": "A", "late-arriving": "A",
    "non-latin": "N",
    "widget": "W",
    "data table": "T", "grid": "T",
}
# Reclassifications fixed in PREREG Amendment 3, before any run.
OVERRIDE = {"T7": "A", "T13": "W", "T21": "T"}
DROPPED = {"T15", "T18"}

# GRADING OVERRIDES — from the SECOND, blind referee (PREREG Amendment 4).
# It agreed with the first on all three answers, and then found the thing that
# agreement cannot find: parts of these are obtainable WITHOUT doing the work,
# so grading on the guessable half would score a guesser as correct.
#
#   T7  `Cheese, cheddar` is the archetypal cheese and the obvious #1 relevance
#       hit for the query -- guessable from general knowledge. The count 19 is
#       not guessable by any route, so the count is the discriminating half.
#   T20 the commonly republished figure for almond magnesium is ~270 and the
#       true Max is 271, so a pure knowledge guess lands within 1 without ever
#       opening the table. EXACT match only; a tolerance band would erase the
#       distinction entirely.
#   T21 cheddar sodium is generally cited around 620-660, so "~650" is
#       guessable -- but n=41 is not, and it is what proves the table was read.
#       Require BOTH. (Note the widely-republished figure is 653, the SR Legacy
#       value, so a knowledge-only guess lands on 653 rather than 650.)
#
# `require_all` means every listed string must appear, not any one of them.
GRADING = {
    "T7":  {"require_all": ["19"],
            "reject": ["277", "787", "59,556", "59556", "50",
                       "Cheese spread", "Cheese, cotija"]},
    "T20": {"require_all": ["271"],
            "reject": ["258", "238", "276", "273", "268", "280", "81.3", "2.32"]},
    "T21": {"require_all": ["650", "41"],
            "reject": ["654", "743", "575", "653", "195", "110", "42"]},
}


def shape_for(tid, header):
    if tid in OVERRIDE:
        return OVERRIDE[tid]
    h = header.lower()
    for frag, letter in SHAPE_OF.items():
        if frag in h:
            return letter
    return None


def host_for(tid, tasks_src):
    m = re.search(rf"^### {tid}\b[\s\S]*?\*\*Start URL:\*\*\s*(\S+)", tasks_src, re.M)
    if not m:
        return None
    return re.sub(r"^https?://", "", m.group(1)).split("/")[0]


def main():
    key = open(KEY, encoding="utf-8").read()
    tasks = open(TASKS, encoding="utf-8").read()
    # task headers in the ORIGINAL file carry the author's shape label
    headers = dict(re.findall(r"^### (T\d+)\s+\[shape: ([^\]]+)\]", tasks, re.M))

    gt, problems, dropped = {}, [], []
    for m in re.finditer(r"^### (T\d+)\s+(ACCEPT|REJECT)([^\n]*)\n([\s\S]*?)(?=^### T\d|\Z)",
                         key, re.M):
        tid, verdict, _tail, body = m.group(1), m.group(2), m.group(3), m.group(4)
        if tid in DROPPED:
            dropped.append(f"{tid} (dropped in tasks.md / PREREG Amendment 3)")
            continue
        if verdict == "REJECT":
            dropped.append(f"{tid} (referee REJECTED)")
            continue
        a = re.search(r"^\*\*Answer:\*\*\s*(.+)$", body, re.M)
        if not a:
            problems.append(f"{tid}: no **Answer:** line")
            continue
        # THE REFEREE BACKTICKS EXACTLY THE LOAD-BEARING VALUES AND NOTHING
        # ELSE -- verified across all 22 answer lines. So the spans ARE the
        # requirement, and every other word on the line is connective prose.
        #
        # This replaces a split on " and " / ";" / " / " that was wrong twice
        # over, and scored 5 of the first 12 runs WRONG while every one of
        # them was right:
        #   * it stripped backticks only from the ENDS, so a comma-joined
        #     answer kept its internal ones and the needle `Regice`, Sp. Def
        #     `200` was a literal no agent could ever emit; and
        #   * a comma-joined composite was never split at all, so the whole
        #     phrase had to appear verbatim -- "Third row is Regice, with a
        #     Sp. Def of 200" could not match it.
        # Both arms failed identically on T5 and T6, which is the signature of
        # a broken ruler rather than a broken system (#48, #16).
        #
        # Spans are ATOMIC, which is why this rule and not comma-splitting:
        # T19's answer is `2, 8, 18, 8`, one value containing commas.
        ans = a.group(1).strip()
        require = [x.strip() for x in re.findall(r"`([^`]+)`", ans) if x.strip()]
        if not require:
            problems.append(f"{tid}: **Answer:** line has no backticked value, "
                            f"so there is nothing to grade on: {ans!r}")
            continue
        # "**Also acceptable:**" is PROSE, not a literal -- harvesting the whole
        # sentence as a needle produced inert entries like
        # '22.96` without the dollar sign.' that could never match anything.
        # Its backticked spans are the usable part, and they are ALTERNATIVES
        # to a required value, never requirements of their own.
        accept = []
        alsom = re.search(r"^\*\*Also acceptable:\*\*\s*(.+)$", body, re.M)
        if alsom and "none" not in alsom.group(1).lower():
            accept = [x.strip() for x in re.findall(r"`([^`]+)`", alsom.group(1))
                      if x.strip()]
        # REJECTS ARE CURATED ONLY. The auto-harvest that used to live here is
        # DELETED, after it produced false rejections three different ways on
        # answers that were right:
        #   * T21 scored a correct "Median Sodium 650 mg, n = 41" WRONG because
        #     the bare column name `n` was harvested as a near-miss;
        #   * T8 and T16 were rejected by `ForgeFlex Tools` (the brand the task
        #     TELLS you to filter by) and by `总笔画 12` (the literal correct
        #     answer), because a referee's verification notes quote the CORRECT
        #     values and the harvest assumed a notes section holds near-misses;
        #   * T22's section regex ran past its own task boundary to \Z and
        #     harvested answers belonging to five OTHER tasks (`Start Order`
        #     from T9, `100-0000` from T2, `Sp. Atk` from T5...).
        #
        # Each fix made the filter narrower and the next hole appeared somewhere
        # else, which is this project's own signature for a matcher that reads
        # as general and measures as narrow (#21). A near-miss is a JUDGEMENT
        # about what a guesser would plausibly say, and the second referee
        # already made it for the three tasks where it matters -- those are in
        # GRADING, written before any run. Everywhere else the require_all
        # conjunction does the work, and a reject that can fire on a correct
        # answer is strictly worse than no reject at all.
        reject = []
        shape = shape_for(tid, headers.get(tid, ""))
        if not shape:
            problems.append(f"{tid}: cannot determine shape from {headers.get(tid)!r}")
            continue
        host = host_for(tid, tasks)
        if not host:
            problems.append(f"{tid}: no Start URL in tasks.md")
            continue
        entry = {"require_all": require, "accept": accept,
                 # A reject that is ALSO an accepted variant is a contradiction
                 # the key cannot act on -- T19 carried `2 8 18 8` in both.
                 "reject": [r for r in reject
                            if r not in require and r not in accept],
                 "shape": shape, "host": host}
        g = GRADING.get(tid)
        if g:
            entry["require_all"] = g["require_all"]
            entry["reject"] = sorted(set(entry["reject"]) | set(g["reject"])
                                     - set(g["require_all"]))
        gt[tid] = entry

    print(f"parsed {len(gt)} task(s); dropped {len(dropped)}; {len(problems)} problem(s)")
    for d in dropped:
        print("  DROPPED ", d)
    for p in problems:
        print("  PROBLEM ", p)
    if gt:
        from collections import Counter
        print("  shapes:", dict(Counter(v["shape"] for v in gt.values())))
        print("  hosts :", len({v["host"] for v in gt.values()}), "distinct")
    if "--write" in sys.argv:
        if problems:
            print("\nREFUSING to write: fix the key, not this script.")
            return 1
        json.dump({"gt": gt, "weak": []}, open(OUT, "w", encoding="utf-8"),
                  indent=1, ensure_ascii=False)
        print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
