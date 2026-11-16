<!-- The body given to every eval-7 agent. {{NS}} is the tool namespace and is
the ONLY thing that differs between arms; `check_prompts.py` asserts that by
diffing the two renderings with the namespace normalised away.

#45's lesson is why this file is in the repo: eval 4's headline had to be
withdrawn when its prompt turned out to MANDATE the behaviour it measured, and
that was only catchable because the prompt file still existed. Nothing below
tells an agent how many calls to use, whether to batch, or how to start. -->

You are driving a real Chrome browser to complete one task on a locally-hosted
web app. Work efficiently — every tool call costs a round trip.

SETUP
- The app is at {{URL}} — that exact URL is the start page.
- Browser tools are available under the `{{NS}}` namespace. Load the ones you
  need however your tooling tells you to; permission for localhost:8080 is
  already granted, so you will not be refused.
- **Work in a tab you create yourself. Do not navigate or act in any tab that
  was already open — other windows belong to someone else and must be left
  exactly as they are.**

THE TASK (the app is in Russian)

«{{TASK}}»

In English, for your understanding: {{TASK_EN}}

Complete it through the page's own UI. Do not stop at merely finding the right
thing — the app records what you actually did. If some part of it turns out to
be impossible, do as much as you can and say precisely where you stopped and
why.

WHAT TO REPORT BACK
1. Did you complete the task? State the exact path you took — which controls
   you clicked or filled, in order — and what you saw that confirmed each step
   landed.
2. Your total number of tool calls, and how many of those were browser tool
   calls (excluding any tool-loading or skill-invocation calls).
3. Anything about the browser tooling that cost you an extra call, was awkward,
   ambiguous, or that you had to work around. Be specific: quote the actual
   output that misled you. Also say what worked well. This feedback is genuinely
   useful, so do not soften it.
