# Eval 14 — what a SECOND run of the same task costs

Written 2026-11-19, BEFORE any arm ran. Fixture reset immediately before.

## The claim under test, stated narrowly

Not "we browse better". Earlier head-to-heads (#39, #40, #41, #43, #47, #48)
cover the first pass and mostly came back ties or modest wins, and eval 13
could not run at all because the other extension was wedged.

**This measures the SECOND run of a task a team already does.** ChromeBridge
can record the first pass as a replayable flow and re-run it deterministically
with zero model calls. Claude-in-Chrome has no equivalent, so its second run is
another full agent pass.

## Task (identical for both arms, phrased without naming any tool)

> On the Acme Ops app at http://localhost:8787 (sign in as ada@acme.test with
> password demo-pass-1234), open the invoices list, filter it for "Corp", sort
> by amount ascending, open the first result and report its reference number
> and amount.

## Ground truth — derived independently, before either arm ran

By a headless Chromium driven by neither toolset:

    INV-1012 | Oscorp | 2026-05-13 | 9,870

Accept: reference `INV-1012` AND amount `9,870` (commas/currency optional).

## Metrics, fixed now

- **M1 (primary): tool calls for the SECOND run of the task.**
- **M2: wall clock for the second run**, reported with the ~47s/task drift
  floor #35/#41 measured, so a difference under that is NOT a result.
- **M3 (falsifier): correctness against the referee on both runs of both arms.**
  A wrong answer invalidates that arm's numbers regardless of speed.

## What this CANNOT show, written before the data so it cannot be softened after

- It says nothing about which toolset is better at the FIRST pass.
- Replay is deterministic re-execution, not reasoning. A flow that drifts needs
  a rebind, which costs a turn — #61 measures that at 6.58s against 0.4s clean.
  This task's flow is one the fixture resets for, so drift is excluded BY
  CONSTRUCTION here and that is a limit of the setup, not evidence of
  robustness.
- n=1 task. It is a capability demonstration, not a statistical result, and the
  word "demonstration" is the one to use when reporting it.
- The fixture is an app I wrote. The LOCATOR half is measured on 37 real sites
  (#49) and the record/replay loop on 8 real apps (#63/#64), but this specific
  task is home ground.

## Procedure

1. Fixture reset. Referee ground truth recorded above.
2. Arm B (Claude-in-Chrome): one independent agent, told only the task, does it
   TWICE in one session. Both runs scored.
3. Arm A (ChromeBridge): pass 1 is the already-recorded
   `flows/acme-invoices-drilldown.flow.json` (7 steps, 4 asserted). Pass 2 is
   `run_flow`, measured.
4. Scored from transcripts, not self-reports — #47 found two scorer defects
   that way.
