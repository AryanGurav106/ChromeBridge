# Recorded flows

`*.flow.json` written by `record_flow`, replayed by `run_flow`. See
`FLOW_RECORDER_PLAN.md` for the design and CLAUDE.md #49 for what was measured.

Flows for a real app belong in git next to the code they test — they are tests.

`todomvc-add-items.flow.json` is the first real-app flow that INTERACTS rather
than only navigating: it types two items into a third-party React TodoMVC and
asserts the list length after each one, plus a text search. It carries two
variables taken from the typed values, and the search assertion follows them —
`run_flow(vars={"what_needs_to_be_done_2": "…"})` types the new text and checks
for the new text. Example, not a CI test (needs the public internet).

It exists because `saucedemo-login.flow.json` could not include a click:
a trusted click whose effect NAVIGATES kills that tab's input channel (#56),
and TodoMVC's interactions do not navigate. `the-internet.herokuapp.com` was
the first choice and is unreachable from this browser — plain Playwright with
no extension times out on it, which is the network rather than our navigate.

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

`acme-nav-badge.flow.json` is the second CI test, and it exists to be BROKEN:
`--chaos badge` rewrites one nav link's accessible name and leaves its href
alone, which is #59's live failure reproduced offline. The identity rung is
DATA there, so only the href fallback (#61) can carry the step — with the
fallback removed, CI fails at `no element on the page matches … name='Projects
4'`. A fallback nothing exercises is a fallback nobody knows is broken.

The eight `ev-*.flow.json` files are the generality eval (#63/#64): eight apps
named by an agent told only to pick varied ones, each recorded by a separate
agent that did not know a toolset was under test — W3C's APG combobox, arXiv's
advanced search, a Bootstrap modal, DataTables, httpbin's form, Japanese
Wikipedia, the Python docs and TodoMVC. They are examples, not CI tests (each
needs its own public origin), but `--check-only` validates every one on every
push: a format change can orphan a recorded file whose only other symptom is a
SKIP line identical to a healthy skip.

`saucedemo-login.flow.json` is the first flow recorded against a REAL
third-party app — Sauce Labs' published sample application, driven in a
throwaway profile with its public credentials. It is an example, not a CI test
(`--local-only` skips it, because a suite that needs the public internet fails
for reasons that are not the code's). It exists because every other flow here
targets `tools/saas_playground.py`, which we wrote: the descriptor half was
measured on 37 real sites (#49), the record -> replay loop never was. Replaying
it needs `CB_SECRET_SAUCEDEMO_LOGIN_PASSWORD`.

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
python tools/run_flows.py --playground --local-only --chaos badge   # ...and the broken-label arm
python tools/run_flows.py --check-only                # no browser at all: every file still loads
python tools/run_flows.py checkout --headed           # one, visibly
python tools/run_flows.py --vars '{"project_name":"x"}'
```

`--check-only` opens no browser and needs no Playwright, which is the point of
it: it loads every flow file, including the ones CI cannot replay, and also
fails a step that names a target with no descriptor — the shape a compile bug
leaves behind, which otherwise loads fine. (It used to print a SKIP and return
0 on a machine without Playwright, because the import gate ran before the flag
was read. Fixed, and pinned by C26.)

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

## When the page moves

A replay that cannot pin a target to exactly one element does not guess. It
stops, hands back the candidates, and you continue with
`run_flow(resume_id=…, bind="ref_N")`. If a cheaper fallback carried the step
instead — a renamed link matched by its `href` — the run PASSES and reports the
drift:

```
  step 3 computer: name 'Projects 4' is gone; matched href='/projects'
  proposed descriptor changes (not applied):
    step 3 computer: Projects 4 -> Projects 5
  Apply them with record_flow(action="patch", name="acme-nav-badge")
```

Either way the file on disk is untouched. `record_flow(action="patch")` applies
the proposal, and only because you asked: `run_flow` owns the RUN and
`record_flow` owns the FILE. An automatic rebind would mean ranking candidates,
which is the thing this runner refuses to do.

Two other things come out of the recording rather than from a constant: each
step stores the settle time it actually needed (`settle_ms`), so a slow app is
not held to a number someone picked; and a flow that does NOT begin with its own
`navigate` records the state it expects to start from, checked before step 0, so
pointing it at the wrong page says so in one sentence instead of failing deep
inside with a message about one element.

## What makes a flow able to FAIL

Only what you checked while recording becomes an assertion: a `get_url`, a
`search_page` that hit, or a `query_elements` count. An action with no
observation after it records no postcondition, so the replay can only detect
that the control went missing — never that it produced the wrong result.
`record_flow(action="stop")` says so when no step carries one.

A zero-hit observation is deliberately NOT recorded as an absence contract. A
`search_page` that found nothing is not evidence of anything on its own — a
mistyped query becomes a permanent "this must never appear" otherwise. An
absence is only kept when the thing was SEEN first and then went away, and a
dropped observation is NAMED in the stop report rather than silently discarded.

`record_flow(action="stop")` also warns when a check was ALREADY TRUE before
the step it follows: the step did not move what the check measures, so the flow
would pass even if the step did nothing. That is usually a step that silently
failed — a required field left unfilled is the one that caused it twice. A
warning, not a refusal: an idempotent step legitimately leaves state alone.
