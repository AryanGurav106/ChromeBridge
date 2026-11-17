# Eval 10 — pre-registration

Written and committed BEFORE any task exists and before any run.

## Why this one is not another turn count

Evals 3, 5, 7 and 9 all compared ChromeBridge and Claude-in-Chrome on
**tool calls to complete a lookup**. Three of them tied. Eval 9 tied at
`p = 1.0000` against a bar fixed in advance, and its own closeout says the
honest reading is that the arms are level on that axis once our own defects are
removed. Running a fifth turn-count eval would be asking a question four evals
have already answered.

**The axis nobody has measured is REPEATABILITY.** ChromeBridge can record a
driven task as a replayable test and run it again deterministically with no
model call per step. The other arm has no equivalent: its own tool surface has
no record, no replay, no assertion. So the comparison is not "who is faster
once" — it is **"what does it cost to do this same task again tomorrow, and
does the second run still tell the truth when the app has changed."**

That is the capability the brief names, and it is the one where the difference
is categorical rather than a few percent inside a noise floor.

## What is being compared

For each scenario, both arms do the task once. Then:

| | ChromeBridge | Claude-in-Chrome |
|---|---|---|
| repeat the task | `run_flow(name)` | drive the whole task again |
| model calls on the repeat | measured | measured |
| does the repeat ASSERT anything | measured | n/a — nothing to assert with |
| app changed underneath | measured (see below) | n/a |

**The second run is the measurement.** The first run is setup for both arms and
its cost is reported but is not the headline, because eval 9 settled that axis.

## Bars, fixed now

- **H1 (primary).** Median model calls to repeat a completed task.
  ChromeBridge must be **< 25%** of the other arm's. This is a prediction that
  can fail: if a replay needs rebinding on most scenarios, or if flows do not
  survive to a second run, the ratio collapses.
- **H2 (the one that matters more).** On every scenario where the replay
  passes, it must have checked at least one postcondition that **would fail if
  the step did nothing**. A replay that passes vacuously is worth less than no
  replay, and `record_flow`'s own `UNPROVEN`/`hollow` review lines are the
  evidence. **Target: 100%.** Anything less is reported as the headline, not
  as a footnote.
- **H3 (hardening).** After recording, the app is CHANGED — a list re-sorted, a
  label renamed, a row inserted above the target. The replay must either
  **resolve correctly and say the page moved**, or **refuse and name the
  candidates**. A silent wrong bind is a FALSIFIER for the whole eval.
  **Target: 0 silent wrong binds.**
- **Falsifier.** Correctness of the first run, both arms, against an
  independently re-derived answer. If either arm is below 80% this is reported
  as a tooling failure, not a comparison.

## What this design explicitly cannot show

- **It is not a fair fight and it is not meant to be.** One arm has the feature
  and the other does not. The honest claim is "this capability exists and here
  it is working on real sites", NOT "we are 4x better at browsing".
- Both arms are the same model, so first-run correctness saturates.
- A flow that mutates state is not re-runnable without a reset, which is a
  property of any create-a-record test and must be designed around per
  scenario, not hidden.
- Per-origin consent is a one-time cost we pay and they do not. It is excluded
  from the call counts and that exclusion is stated here, before any run.

## Rules carried forward from the evals that went wrong

- **Tasks written blind** by an agent told only to write complex multi-step
  scenarios, given a deny-list of every domain used in evals 1–9, and told
  nothing about any toolset (eval 4's headline had to be withdrawn when its
  prompt turned out to mandate the behaviour it measured).
- **Ground truth re-derived independently**, not taken from the task author
  (eval 3 dropped two tasks on this rule).
- **Scored from transcripts and from the saved `.flow.json`**, never from an
  agent's self-report (eval 5 found two scorer defects that way).
- **Prompts asserted identical** modulo the tool namespace.
- **The bar does not move after data exists.** Eval 9 cleared nothing and was
  reported as a tie; the same applies here.
- **An amendment is dated and written BEFORE the run it affects**, except one
  that records what a completed wave found.

## Status

NOT STARTED. Written while the staleness-refusal measurement for outcome 1 was
still running, because outcome 2 depends on outcome 1 and the brief says so.
No task list, no runs, no results.
