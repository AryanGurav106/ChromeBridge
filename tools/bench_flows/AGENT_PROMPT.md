# Recording-agent prompt template

One agent per app, run SERIALLY. `{{...}}` is substituted per app.

The agent RECORDS only. The replay is run by the scorer afterwards, so M1/M2
never depend on a self-report — #47 found two scorer defects by noticing a
self-report disagreeing with the transcript. What the agent reports back is
the verbatim text of a tool's own output, never a judgement about it.

Nothing in this prompt names the feature under test, what is expected to
break, or that anything is being measured. #45's headline had to be withdrawn
because the prompt mandated the behaviour it measured.

---

You are driving a real Chrome browser through the `chromebridge` MCP tools.

Load the tools you need in ONE ToolSearch call.

**Your task, in order:**

1. `tabs_create_mcp` — work in the tab it returns, and pass that `tabId`
   explicitly to every later call.
2. `record_flow(action="start", name="{{SLUG}}")`
3. Carry out this interaction on the page, using ordinary tool calls:

   Start at: `{{URL}}`

   {{STEPS}}

4. **Check your work as you go.** After each action that changes something,
   make an observation confirming it worked — `get_url`, `search_page`, or
   `query_elements`. Those observations are what make the recording able to
   detect a regression later, so a step with nothing confirming it is a step
   that proves nothing. In particular confirm this at the end:

   {{CHECK}}

5. `record_flow(action="stop")`
6. `tabs_close_mcp(tabId=<your tab>)`

**Then report back exactly this, and nothing else:**

- `STOP_MESSAGE:` the complete verbatim text that `record_flow(action="stop")`
  returned, including any note or warning after the first line.
- `STEPS_DRIVEN:` one line per tool call you made between start and stop, as
  `toolname — what it did`.
- `TROUBLE:` anything that did not work the way you expected, in one line
  each — a tool that errored, a refusal, a result you did not understand, a
  thing you had to retry, or a message that told you something you could not
  act on. Write `none` if there was none. Be specific and quote the tool's
  own words; do not soften or explain them away.

If the very first call is refused for permission, STOP and report that
verbatim — do not retry in a loop.
