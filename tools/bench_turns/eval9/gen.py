# -*- coding: utf-8 -*-
"""Render the eval-9 prompts. The arms differ ONLY by tool namespace, and that
is asserted here rather than hoped for: eval 4's headline had to be withdrawn
because its prompt mandated the behaviour it measured, and the prompt file is
what made that catchable.

Nothing below tells an agent how many calls to use, whether to batch, or how to
start. The only instruction about tabs is a correctness one, identical in both
arms, and it is there because agents of the SAME arm share a browser.
"""
import json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
NS = {"cb": "mcp__chromebridge", "cic": "mcp__claude-in-chrome"}

TPL = """You are completing one task in a live web browser. Answer from the pages you
actually load, never from memory or prior knowledge.

TOOLS: use ONLY tools whose names begin with `{NS}`. Do not use any other
browser toolset, and do not use curl, fetch or any non-browser route to the
page — the point is to read it through the browser.

START AT: {START}

TASK:
{TASK}

Work in a tab you open yourself, and leave any tab that was already open
exactly as it is.

Do not guess. Every value you report must have been read off a page you
loaded. If it is genuinely unobtainable, say so instead of inventing it. Do not
log in, buy anything, or submit any personal information.

When you are done, reply with exactly these three lines and nothing else:

ANSWER: <the exact string the task asked for, or UNOBTAINABLE>
CALLS: <how many browser tool calls you made, counting each browser_batch as one>
NOTES: <one sentence on anything that cost you a call, or "none">
"""


def main():
    tasks = json.loads((HERE / "tasks.json").read_text(encoding="utf-8"))
    out = {}
    for t in tasks:
        for arm, ns in NS.items():
            out[f'{t["id"]}:{arm}'] = (TPL.replace("{NS}", ns)
                                          .replace("{START}", t["start"])
                                          .replace("{TASK}", t["task"].strip()))
    # THE ASSERTION, not a hope: normalise the namespace away and diff.
    bad = [t["id"] for t in tasks
           if out[f'{t["id"]}:cb'].replace(NS["cb"], "NS")
           != out[f'{t["id"]}:cic'].replace(NS["cic"], "NS")]
    if bad:
        print(f"ARMS DIFFER beyond the namespace on: {bad}", file=sys.stderr)
        return 2
    (HERE / "prompts.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    print(f"{len(tasks)} task(s) x 2 arms = {len(out)} prompts; "
          f"arms differ beyond namespace on: NONE")
    for t in tasks:
        print(f"  {t['id']:<4} {t['shape']:<12} {t['start'][:58]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
