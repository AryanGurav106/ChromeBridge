# Identical for both arms except {NS}. Kept in a file so the arms cannot drift.
# {NS}     = mcp__chromebridge__ | mcp__claude-in-chrome__
# {TASK}   = the verbatim task line from tasks.md (after the second |)
# {TASKID} = T1 .. T10
#
# THE ONE DELIBERATE DIFFERENCE FROM bench25/PROMPT_TEMPLATE.md: this says
# NOTHING about tabs. The old template ordered agents to call tabs_context_mcp
# and tabs_create_mcp "as a call ON ITS OWN (do not batch it with anything)",
# which is the ceremony those evals then measured. Isolation is handled by
# running strictly serially instead.

---TEMPLATE---
You are running one task in a browser-automation evaluation. Work entirely in the
browser. Answer from the live pages, never from memory or prior knowledge.

TOOLS: use ONLY tools whose names start with `{NS}`. Do not use any other
browser toolset.

TASK {TASKID}:
{TASK}

Work efficiently but do not guess: every reported value must have been read off a
page you actually loaded. If a value is genuinely unobtainable, say so rather than
inventing it. Do not close any tab you did not open.

When done, reply with EXACTLY these seven lines and nothing else:

ANSWER: <the answer, all requested parts, verbatim where the task says exact>
TOOL_CALLS: <total number of tool calls you made, including ToolSearch>
BROWSER_CALLS: <of those, how many were {NS} calls>
FIRST_CONTENT_AT: <the 1-based index of the first tool call that returned actual PAGE CONTENT to you>
BATCHED: <no | yes, N times>
BLOCKERS: <none | anything that cost you an extra round trip>
DEFECTS: <none | any tool output that was wrong, misleading, empty when it should not be, or that made you re-check something>
---END---
