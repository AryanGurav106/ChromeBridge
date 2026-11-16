"""Assert the two arms' prompts differ ONLY by the tool namespace.

Eval 4's headline had to be withdrawn because its prompt mandated the behaviour
it measured (#45). This makes "identical modulo the namespace" a checkable fact
rather than an intention: it renders both arms and diffs them with the namespace
and the track URL normalised away, so any other divergence fails loudly.

Run:  python tools/bench_turns/eval7/check_prompts.py
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NS = {"cb": "mcp__chromebridge__", "cic": "mcp__claude-in-chrome__"}


def render(arm: str, key: str, task: str, task_en: str) -> str:
    body = (HERE / "PROMPT_TEMPLATE.md").read_text(encoding="utf-8")
    body = body.split("-->", 1)[1].lstrip()
    # The benchmark's own task strings carry a %HOST% placeholder its harness
    # substitutes at serve time; an agent handed it literally would have to
    # guess. Same substitution for both arms, so it cannot bias one.
    task = task.replace("%HOST%", "localhost:8080")
    return (body.replace("{{NS}}", NS[arm])
                .replace("{{URL}}", f"http://localhost:8080/e7_{arm}_{key}")
                .replace("{{TASK}}", task).replace("{{TASK_EN}}", task_en))


def main() -> int:
    rows = json.loads((HERE / "tracks.json").read_text(encoding="utf-8"))
    en = json.loads((HERE / "task_en.json").read_text(encoding="utf-8"))
    bad = 0
    for r in rows:
        if r["arm"] != "cb":
            continue
        k = r["key"]
        a = render("cb", k, r["task"], en[k])
        b = render("cic", k, r["task"], en[k])
        norm = lambda s, arm: (s.replace(NS[arm], "<NS>")              # noqa: E731
                                .replace(f"e7_{arm}_{k}", "<TRACK>"))
        if norm(a, "cb") != norm(b, "cic"):
            print(f"DIVERGENT: {k}")
            bad += 1
        if "{{" in a or "{{" in b:
            print(f"UNRENDERED PLACEHOLDER: {k}")
            bad += 1
        # The prompt must not teach either arm how to start or how many calls to
        # spend -- that is the eval-4 failure, and it is checkable.
        for forbidden in ("on its own", "batch", "in one call", "ToolSearch"):
            if forbidden.lower() in a.lower():
                print(f"PROMPT MANDATES BEHAVIOUR ({forbidden!r}) in {k}")
                bad += 1
    print("OK — prompts differ only by namespace and track" if not bad
          else f"{bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
