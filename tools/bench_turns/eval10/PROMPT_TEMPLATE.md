# Eval 10 prompt template

One template, `{{NS}}` substituted per arm, then the two rendered prompts are
asserted identical modulo that token. Eval 4's headline had to be WITHDRAWN
because its prompt instructed the behaviour it then measured, so the rule here
is blunt: **this template names no tool and prescribes no technique.** It says
what to achieve and how to report, and nothing about how to browse.

---

## PHASE 1 — do the task

```
Use the {{NS}} browser tools to do this, starting from the URL given.

{{PROMPT}}

Start at: {{START}}

Work in a tab you open yourself, and leave any tab that was already open
exactly as it is.

When you are done, end your reply with exactly these three lines:
ANSWER: <the short exact string the task asks for>
CALLS: <how many browser tool calls you made>
NOTES: <one line: anything that cost you calls, or that surprised you>
```

## PHASE 2 — do it again

Sent as a SECOND message to the SAME agent, after phase 1 finishes.

```
Do that same task again now, from the same starting URL, and report the same
three lines. Use whatever approach you think is cheapest.
```

**That wording is load-bearing.** It does not say "replay", "re-run the
recording" or "use the flow" — naming the mechanism would be eval 4's mistake
in the other direction, telling one arm what to do and then counting it as a
capability. Each arm decides for itself what cheapest means, and if the
ChromeBridge agent chooses to drive the task again by hand rather than replay
what it recorded, that is a finding about discoverability and it is reported as
one.

## PHASE 3 — the app changed

Sent third, after the scenario's page has been changed underneath the agent
(a list re-sorted, a filter pre-applied, a row inserted). The change is made by
the HARNESS, not by either agent, and identically for both.

```
Do that same task once more and report the same three lines. If anything about
the page is not what you expected, say so in NOTES rather than working around
it silently.
```

## What the runner must NOT add

- No instruction to batch, to open a tab a particular way, or to call anything
  "on its own". Eval 4's tab-ceremony finding dissolved when it turned out the
  prompt had mandated it (1.02 creates/run where the prompt named it, 0.05
  where it did not).
- No mention of recording, flows, assertions, or that two arms exist.
- No hint that the task will be repeated. Phase 1 must be driven as a one-off,
  or the comparison measures foresight rather than capability.
