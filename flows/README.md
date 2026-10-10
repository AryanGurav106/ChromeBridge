# Recorded flows

`*.flow.json` written by `record_flow`, replayed by `run_flow`. See
`FLOW_RECORDER_PLAN.md` for the design and CLAUDE.md #49 for what was measured.

Flows for a real app belong in git next to the code they test — they are tests.

`playground-idempotent.flow.json` is the one worked example, kept because it is
the live verification referenced in #49, and it is **an example, not a CI test**:
it drives a third-party page (shadcn/ui's playground) that will drift, and
nothing in `run_tests.py` runs it.

## The one thing to get right when recording

**Start the recording BEFORE the `navigate` that establishes the page state.**

A flow replays from whatever state the tab is in. This example's first step is
its own `navigate`, so it runs twice back to back (measured: 0.33s, 0.30s).

The first flow recorded here did not, and could not run twice — `form_input` on
a Radix combobox leaves its listbox open, an open popup marks the rest of the
document `aria-hidden`, and the second run failed at step 0 on an unrelated
textarea. The runner now names that cause when it sees an open surface in its
own listing, but naming it is a consolation prize; recording from the navigate
is the fix.

## What makes a flow able to FAIL

Only what you checked while recording becomes an assertion: a `get_url`, a
`search_page` that hit, or a `query_elements` count. An action with no
observation after it records no postcondition, so the replay can only detect
that the control went missing — never that it produced the wrong result.
`record_flow(action="stop")` says so when no step carries one.

A zero-hit observation is deliberately NOT recorded. A `search_page` that found
nothing is not evidence of anything, and an assertion that cannot fail is worse
than no assertion.
