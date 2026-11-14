# -*- coding: utf-8 -*-
"""Generate eval 4's prompts — READ FROM tasks.md, never transcribed.

eval 3's generator carried its task text in a hardcoded dict. That is the same
transcription risk that produced #48's broken answer key, where a value copied
by hand with the wrong Unicode codepoint made the correctness falsifier fire on
BOTH arms — the signature of a broken ruler rather than a broken system. So
this parses the task file and the ground truth, and refuses anything it cannot
parse.

Two arms, differing ONLY by the tool namespace. That is asserted here rather
than assumed, because #45's headline had to be withdrawn when its prompt turned
out to mandate the behaviour it measured, and the only reason that was catchable
is that the prompt file happened to survive.

  python tools/bench_turns/eval4/gen.py            # report + assert
  python tools/bench_turns/eval4/gen.py --write    # write prompts/
"""
import json, os, random, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS = os.path.join(HERE, "tasks.md")
GT = os.path.join(HERE, "ground_truth.json")
OUT = os.path.join(HERE, "prompts")

TPL = """You are running one task in a browser-automation evaluation. Work entirely in the
browser. Answer from the live pages, never from memory or prior knowledge.

TOOLS: use ONLY tools whose names start with `{NS}`. Do not use any other
browser toolset.

TASK {TID}:
Start at {START}
{TASK}

Work efficiently but do not guess: every reported value must have been read off a
page you actually loaded. If a value is genuinely unobtainable, say so rather than
inventing it. Do not close any tab you did not open. Do not log in, buy anything,
post anything, or enter personal data anywhere.

When done, reply with EXACTLY these seven lines and nothing else:

ANSWER: <the answer, all requested parts, verbatim where the task says exact>
TOOL_CALLS: <total number of tool calls you made, including ToolSearch>
BROWSER_CALLS: <of those, how many were {NS} calls>
FIRST_CONTENT_AT: <the 1-based index of the first tool call that returned actual PAGE CONTENT to you>
BATCHED: <no | yes, N times>
BLOCKERS: <none | anything that cost you an extra round trip>
DEFECTS: <none | any tool output that was wrong, misleading, empty when it should not be, or that made you re-check something>"""

ARMS = {"cb": "mcp__chromebridge__", "cic": "mcp__claude-in-chrome__"}


def load_tasks():
    src = open(TASKS, encoding="utf-8").read()
    gt = json.load(open(GT, encoding="utf-8"))["gt"]
    out, missing = {}, []
    for tid in sorted(gt, key=lambda x: int(x[1:])):
        # The DROPPED marker block sits BEFORE the original header, so anchor on
        # the original and stop at the next header of any kind.
        m = re.search(rf"^### {tid}\s+\[shape:[^\n]*\n([\s\S]*?)(?=^### T\d|\Z)", src, re.M)
        if not m:
            missing.append(f"{tid}: no section in tasks.md")
            continue
        body = m.group(1)
        t = re.search(r"^\*\*Task:\*\*\s*(.+?)$", body, re.M)
        u = re.search(r"^\*\*Start URL:\*\*\s*(\S+)", body, re.M)
        if not t or not u:
            missing.append(f"{tid}: missing **Task:** or **Start URL:**")
            continue
        out[tid] = (u.group(1), t.group(1).strip())
    return out, gt, missing


def main():
    tasks, gt, missing = load_tasks()
    for m in missing:
        print("  PROBLEM ", m)
    print(f"loaded {len(tasks)} task(s) from tasks.md; ground truth has {len(gt)}")
    if missing or len(tasks) != len(gt):
        print("REFUSING: tasks.md and ground_truth.json disagree. Fix the files.")
        return 1

    # ORDER ROTATED PER TASK, fixed by a seeded shuffle so the run order is
    # reproducible from the repo rather than from whoever ran it.
    rnd = random.Random(4)
    order = {tid: (["cb", "cic"] if i % 2 == 0 else ["cic", "cb"])
             for i, tid in enumerate(sorted(tasks, key=lambda x: int(x[1:])))}

    written, diffs = 0, []
    for tid, (start, text) in tasks.items():
        rendered = {}
        for arm, ns in ARMS.items():
            rendered[arm] = (TPL.replace("{NS}", ns).replace("{TID}", tid)
                                .replace("{START}", start).replace("{TASK}", text))
        # ASSERT IDENTICAL MODULO NAMESPACE. Not a comment, a check: the two
        # prompts must differ in exactly the namespace token and nothing else.
        a = rendered["cb"].replace(ARMS["cb"], "<NS>")
        b = rendered["cic"].replace(ARMS["cic"], "<NS>")
        if a != b:
            diffs.append(tid)
        if "--write" in sys.argv:
            os.makedirs(OUT, exist_ok=True)
            for arm in ARMS:
                with open(os.path.join(OUT, f"{tid}.{arm}.txt"), "w",
                          encoding="utf-8") as f:
                    f.write(rendered[arm])
            written += 2

    print(f"prompts identical modulo namespace: "
          f"{'YES for all ' + str(len(tasks)) if not diffs else 'NO — ' + ', '.join(diffs)}")
    if diffs:
        return 1
    # The prompt must say nothing about tabs, batching or ceremony: #45's
    # headline measured a behaviour its own prompt had mandated.
    leak = [w for w in ("tabs_create", "tabs_context", "batch", "browser_batch",
                        "ToolSearch in one", "one call")
            if w in TPL]
    print(f"prompt mandates nothing about tabs/batching: "
          f"{'YES' if not leak else 'NO — ' + ', '.join(leak)}")
    if leak:
        return 1
    if "--write" in sys.argv:
        json.dump(order, open(os.path.join(HERE, "run_order.json"), "w"), indent=1)
        print(f"wrote {written} prompt file(s) and run_order.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
