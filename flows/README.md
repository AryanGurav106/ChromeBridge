# Recorded flows

`*.flow.json` written by `record_flow`, replayed by `run_flow`. See
`FLOW_RECORDER_PLAN.md` for the design and CLAUDE.md #49 for what was measured.

Flows for a real app belong in git next to the code they test — they are tests.

`shadcn-playground-idempotent.flow.json` is a worked example, kept because it is
the live verification referenced in #49, and it is **an example, not a CI test**:
it drives a third-party page (shadcn/ui's playground) that will drift, and
nothing in `run_tests.py` runs it. It was called `playground-idempotent` until
#54 — a name that reads as *our* playground while targeting someone else's, so
CI's own `SKIP playground-idempotent needs https://ui.shadcn.com` looked like
the local fixture was unreachable.

`acme-create-project.flow.json` is the CI test: it runs end to end against
`tools/saas_playground.py` on every commit via
`python tools/run_flows.py --playground --local-only`. It logs in, creates a
project, and asserts the row count and a text search afterwards. It carries
four variables (`work_email`, `project_name`, `region`, `plan`), so
`run_flow(vars={"project_name": "beta-svc"})` reruns it with different input —
and since #54 the ASSERTIONS follow those variables too, which they did not
before: the flow used to type `beta-svc` and then search for the recorded
`atlas-svc`. Its password is never in the file; export
`CB_SECRET_ACME_CREATE_PROJECT_PASSWORD` before replaying.

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

## Running them

```bash
python tools/run_flows.py --playground --local-only   # what CI runs
python tools/run_flows.py checkout --headed           # one, visibly
python tools/run_flows.py --vars '{"project_name":"x"}'
```

Exit code 0 when every flow passed, 1 otherwise. `--playground` starts the
fixture app and resets it first, so the run depends on nothing already
running; `--local-only` skips flows that touch a non-loopback origin, because
a suite that needs the public internet fails for reasons that are not the
code's. Verified in all three directions: clean run exits 0, a chaos flag
exits 1 naming the check that failed, and an unset secret exits 1 naming the
variable.

This is the only suite that crosses every boundary at once — real Chrome, real
unpacked extension, real bridge, real op router, real MCP tool functions.

## Passwords are never in the file

A `<input type="password">` the flow typed into is recorded as a placeholder
naming an environment variable, not as the value:

```json
{"value": "${CHROMEBRIDGE_SECRET:CB_SECRET_ACME_CREATE_PROJECT_PASSWORD}"}
```

Export it before replaying; `run_flow` REFUSES and names the variable when it
is unset rather than typing an empty string, because a blank password submits
and then looks like a wrong credential instead of a missing one.

What counts as a secret is HTML's own `type` enum — declared, so there is no
wordlist to miss `kennwort` or over-redact `password_hint`. The one case that
names no field, `computer(action="type")`, is judged by what the last
ref-naming step clicked, which is the same focus rule the batch guard uses.

The example flow here was MIGRATED rather than re-recorded, using the real
functions so the result matches what a fresh recording produces.

## What makes a flow able to FAIL

Only what you checked while recording becomes an assertion: a `get_url`, a
`search_page` that hit, or a `query_elements` count. An action with no
observation after it records no postcondition, so the replay can only detect
that the control went missing — never that it produced the wrong result.
`record_flow(action="stop")` says so when no step carries one.

A zero-hit observation is deliberately NOT recorded. A `search_page` that found
nothing is not evidence of anything, and an assertion that cannot fail is worse
than no assertion.
