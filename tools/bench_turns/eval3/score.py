"""Score one eval run from its TRANSCRIPT, never from what the agent reported.

An agent counting its own tool calls is a self-report inside the thing being
measured; #41 records an agent misattributing a marker from a neighbouring row,
and #40 records a tool reporting a navigation that never happened. The JSONL is
the only record that cannot be mistaken about what was actually dispatched.

A TURN is one assistant message containing at least one tool_use -- NOT one tool
call. That is the unit #38 priced at ~3.6s and 92-97% of a tool call's wall
clock: two parallel calls in one message cost one turn, and a browser_batch of
seven steps costs one turn. Raw call count is recorded beside it because the
earlier evals reported calls and the two must not be silently conflated.
"""
import json, os, sys, glob, re

D = os.path.expanduser("~/.claude/projects/-Users-aryangurav-Desktop-ChromeBridge/"
                       "b86bef56-47ca-4359-99a5-97b83519d3e0/subagents")

# A call that hands the agent PAGE CONTENT. tabs_context/tabs_create/sw_info/
# get_url return browser STATE, not what is on a page -- that distinction is the
# whole of H2, so it is spelled out rather than left to a substring match.
CONTENT = {"read_page", "get_page_text", "search_page", "query_elements", "find",
           "read_interactive_elements", "computer", "javascript_tool",
           "accessible_names", "page_tools"}
CEREMONY = {"tabs_context_mcp", "tabs_create_mcp", "tabs_close_mcp", "get_url",
            "sw_info", "debug_targets"}


# The harness's own reply mechanism, not an action the agent chose. It appears
# EXACTLY ONCE in every run of BOTH arms, so excluding it cannot change any
# pair's direction -- but leaving it in makes the absolute turn count wrong, and
# it is what made the first scored run read 5 against a self-reported 4.
HARNESS = {"SubagentHandback"}


def short(name):
    return re.sub(r"^mcp__(chromebridge|claude-in-chrome)__", "", name or "")


def is_browser(name):
    return bool(name) and name.startswith(("mcp__chromebridge__",
                                           "mcp__claude-in-chrome__"))


def score(agent_id):
    f = os.path.join(D, f"agent-{agent_id}.jsonl")
    if not os.path.exists(f):
        return {"agent": agent_id, "error": "no transcript"}
    turns = []            # one entry per assistant message carrying tool_use
    answer = None
    final_text = []
    for line in open(f, encoding="utf-8", errors="replace"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        m = d.get("message") or {}
        c = m.get("content")
        if m.get("role") != "assistant" or not isinstance(c, list):
            continue
        calls, texts = [], []
        for b in c:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                if b.get("name") in HARNESS:
                    # Not a turn, but it CARRIES the seven-line report: an agent
                    # that hands back directly emits no final text block, so the
                    # ANSWER line lives only here. Run 2 scored answer=null
                    # until this was read.
                    texts.append(str((b.get("input") or {}).get("message", "")))
                    continue
                calls.append({"name": b.get("name"), "input": b.get("input") or {}})
            elif b.get("type") == "text":
                texts.append(b.get("text", ""))
        if calls:
            turns.append(calls)
        final_text.extend(texts)

    ncalls = sum(len(t) for t in turns)
    browser_turns = [t for t in turns if any(is_browser(c["name"]) for c in t)]

    # H2: turns taken BEFORE the first one that returned page content, counting
    # from the agent's first action. A run that opens by reading a page scores 1.
    first_content_turn = None
    for i, t in enumerate(turns, 1):
        hit = False
        for c in t:
            n = short(c["name"])
            if is_browser(c["name"]) and n in CONTENT:
                hit = True
            if n == "browser_batch":
                for step in (c["input"].get("actions") or []):
                    if short((step or {}).get("name")) in CONTENT:
                        hit = True
        if hit:
            first_content_turn = i
            break

    # H3: did the first browser turn use the shipped one-turn start?
    one_turn_start = False
    if browser_turns:
        for c in browser_turns[0]:
            if short(c["name"]) == "browser_batch":
                names = [short((s or {}).get("name"))
                         for s in (c["input"].get("actions") or [])]
                if "tabs_create_mcp" in names:
                    one_turn_start = True

    ceremony_calls = sum(1 for t in turns for c in t
                         if is_browser(c["name"]) and short(c["name"]) in CEREMONY)
    toolsearch = sum(1 for t in turns for c in t if c["name"] == "ToolSearch")

    blob = "\n".join(final_text)
    mm = re.search(r"^ANSWER:\s*(.+)$", blob, re.M)
    if mm:
        answer = mm.group(1).strip()

    return {
        "agent": agent_id,
        "turns": len(turns),
        "calls": ncalls,
        "browser_turns": len(browser_turns),
        "first_content_turn": first_content_turn,
        "one_turn_start": one_turn_start,
        "ceremony_calls": ceremony_calls,
        "toolsearch": toolsearch,
        "batches": sum(1 for t in turns for c in t if short(c["name"]) == "browser_batch"),
        "answer": answer,
        "seq": [[short(c["name"]) for c in t] for t in turns],
    }


if __name__ == "__main__":
    for a in sys.argv[1:]:
        print(json.dumps(score(a), ensure_ascii=False))
