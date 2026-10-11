# Flow generality eval — pre-registration

Written BEFORE the app list exists and before any run. #45's headline had to be
withdrawn when the prompt turned out to mandate the behaviour it measured, and
that was only catchable because the prompt file still existed. So: this file
first, apps second, runs third.

## The question

Everything measured about this feature so far measures the LOCATOR — can a
descriptor pick out one element on an arbitrary page. That is 37 frozen sites,
12,030 controls, 23 sites and 2,376 descriptors under six mutations at 0% WRONG.

The LOOP — record an agent's run, compile it, replay it — is demonstrated on
**five** apps, two of which I wrote, and CI replays **one**. This eval measures
the loop.

## Design

- **8 apps**, named by an agent told only to describe short public browser
  interactions, with no knowledge that any feature is under test and no
  knowledge of this file.
- **Serial**, one recording agent at a time. #39 recorded six parallel agents
  on one Chrome corrupting each other's tab groups.
- Each agent: create a tab, record a 3-5 step flow, STOP, replay it once, report.
- **Scored from ARTEFACTS** — the saved `*.flow.json` and the `run_flow` output —
  never from the agent's own prose. #47 found a scorer counting the handback as
  a turn and an answer-extractor returning null, both by a self-report
  disagreeing with the transcript.
- The permission gate stays ON and per-origin. `ALLOW_ALL_ORIGINS` stays `false`.
  Origins are granted by the user in the side panel, which is the product's
  real first-run path. An eval that disables the consent model measures a
  product nobody runs.

## Metrics

| | |
|---|---|
| **M1 PRIMARY** | flows that REPLAY GREEN immediately after recording |
| **M2** | flows that replay green AGAIN on a second replay (idempotence) |
| **M3 FALSIFIER** | a step that binds to the WRONG element and reports success. **Target 0.** Any occurrence invalidates the feature, not the eval |
| **M4** | recordings where #57's witness check fires (an assertion already true) |
| **M5** | distinct DEFECT CLASSES found that no existing fixture models |

## Predictions, fixed now

- **P1** M1 ≥ 6/8. The locator is measured; failures should be in the loop.
- **P2** The failures cluster in three places: SPA settle timing, a postcondition
  that is not reproducible (a clock, a counter, a rotating item), and a popup or
  dialog left open changing the start state (#49 recorded exactly that).
- **P3** M5 ≥ 2. Six of the last eight log entries found something live that no
  fixture modelled; there is no reason this one is different.
- **P4** M4 ≥ 1. A naive recording asserting something already true is the
  easiest mistake this feature allows, and I made it twice myself.
- **P5** M3 = 0.

## What counts as a pass

M1 counts a replay reported `PASSED` by `run_flow` with at least one step
carrying a postcondition. A flow with zero assertions is recorded as such and
does NOT count toward M1 — it can only detect a control going missing, which is
not what this feature claims.

## What would make me report this as a failure

- M3 > 0 — a silent mis-bind is the #10/#11/#12 family and is disqualifying.
- M1 < 4/8 — the loop does not generalise and the five-app demonstration was
  the sample flattering itself (#25).
