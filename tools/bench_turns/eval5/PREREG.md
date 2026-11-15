# PRE-REGISTRATION — EVAL 5, the long-scenario and replay eval

Written **before the tasks exist**, before any run, and before the extension
carrying this session's changes has been loaded into a browser. Nothing below is
revised after data; corrections go in dated amendments, as in eval 4.

Status: **NOT RUN.** It is blocked on one thing only — the repo owner reloading
the extension and reconnecting the MCP client — and it is written now because
the bars have to be fixed before the data exists, and because writing them after
is the move that invalidates a pre-registration.

## Why a fifth eval, and why this shape

Evals 1–4 share a limitation that is now the binding one. Every task in them is
short: eval 3's were two-hop navigate-and-read, eval 4's were single interaction
shapes of a few steps each. On that sample, **31% of our measured margin was
fixed STARTUP cost** (eval 3's own decomposition). A benchmark made of short
tasks measures our opening move repeatedly and the rest of the system barely at
all.

Two consequences, and the second is the interesting one:

1. **A long scenario amortises startup.** If the margin survives at 6–12 steps
   it is about the representation; if it collapses to parity, eval 3's headline
   was mostly a one-turn trick and should be re-described. Either answer is
   worth having and the second is more useful.
2. **A long scenario is the only place record-and-replay can be measured at
   all.** Replaying a two-hop lookup saves nothing worth saying. Replaying a
   twelve-step scenario is where "zero model calls" becomes a number. The other
   arm has no equivalent capability, so this is the one measurement in the
   series that is not a race on the same axis.

## Design

- **8–10 scenarios**, each **6–12 steps** against a real site, authored by an
  agent told only to write complex multi-step browser scenarios. That author is
  given the deny-list of every domain used in evals 1–4 and in CLAUDE.md
  #39–#48, and **is not told that any toolset is under comparison**, that a
  second arm exists, or that replay is being measured. Eval 3 established this
  protocol after I wrote eval 1's tasks myself, on home ground.
- **Each scenario must END in a verifiable state**, not an opinion: a value on
  screen, a row count, a url, a confirmation string. An author-supplied answer
  is not ground truth.
- **An independent referee** re-derives every answer by driving headless
  Chromium, without seeing the author's key. **Any task where the two disagree
  is DROPPED, not adjudicated.** Eval 3 dropped two at this step and eval 4
  dropped two; that step is why the rest is trustworthy.
- **Serial runs, arm order rotated per scenario.** Never parallel: #39 records
  six parallel agents corrupting each other's tab groups.
- **Scored from transcripts, never self-reports.** Eval 4 Amendment 5 found
  `runs.tsv` holding seven-line agent summaries where the scorer expected an
  agent id, and re-scoring from transcripts moved 2 of the first 5 pairs. An
  agent under-counting its own calls is not lying; it does not know.

## Hypotheses and the bars, fixed now

**H1 — PRIMARY. Turns to completion, paired by scenario.** Two-tailed sign test
over decided pairs. At n=9 the achievable p values are 0.004 (9/9), 0.039 (8/9)
and 0.180 (7/9), so **the bar is 8 of 9 decided pairs, p<0.05**. Below that this
is reported as a tie whatever the totals look like. `analyse.py` prints the
achievable-p beside every p, because at small n a subset can sweep and still not
clear — eval 4's secondary did exactly that.

**H2 — REPLAY COST, and this is the one with no counterpart in the other arm.**
After a successful ChromeBridge run, the same scenario is recorded with
`record_flow` and replayed with `run_flow`. Fixed before data:
- **a replay must make ZERO model calls.** This is a property of the design, not
  a measurement, so it is a FALSIFIER: if any replay requires a model turn, the
  claim "deterministic replay" is wrong and gets retracted, not softened.
- **a replay must reach the same verified end state** the live run did.
- **bar: ≥7 of 9 recorded scenarios replay green on a reset fixture state.**
  Below 7, the feature is not ready to showcase and post 001 does not ship.

**H3 — the honest falsifier for the series.** Correctness has been 100% on both
arms in every eval (30/30, 38/38, 48/48) because both arms are the same model —
the ceiling is Claude's, not the tool's. It is pre-registered again anyway: **if
either arm drops below 100% correct, the turn comparison is secondary to that**
and gets reported second.

**H4 — a prediction that can be wrong, stated so it can be.** Eval 3 measured
31% startup / 69% in-task on its longer tasks. I predict **the per-scenario turn
RATIO narrows relative to eval 3's 0.49**, because startup amortises, and that
**it stays below 0.75**. If the ratio exceeds 0.75 the representation is not
carrying the margin at length and eval 3's framing needs correcting in
`docs/EVALS.md`. If it lands below 0.40 I have under-predicted and should say
so rather than claiming the prediction hit.

## What this eval deliberately does NOT measure

- **The consent model.** Scenario origins will not be pre-granted, so running
  this requires the gate to be armed for the duration, as evals 3 and 4 did and
  recorded. **That is a one-time per-origin cost, not a per-task turn cost**, and
  counting it would charge us once per scenario for a security feature the other
  arm does not have. **So this eval says NOTHING about the cost of per-origin
  consent and must not be quoted as though it did.** Arming requires the owner's
  explicit authorisation each time; restoration is verified three ways — the flag
  `false`, `git diff` empty, and `node tools/test_permissions.js` reporting
  24/24 with no "gate off" caveat — and an extension RELOAD, because #47
  measured that a flag restored on disk is not a flag restored in a live worker.
- **Wall clock as a primary.** #35 and #41 measured a ~47s/task drift floor and
  #35 records the CONTROL arm improving 47s on unchanged code. Seconds are
  reported; only eval 3 ever cleared on them, and only because its per-task gap
  was 65s.
- **Anything about the other product's quality.** Eval 3's widest archetype band
  was driven by their renderer failing, not by our representation helping. Where
  a scenario is decided by an arm's own defect rather than by its page
  representation, `FINDINGS.md` says so and the pair is still counted — but the
  summary does not claim the representation earned it.

## Known weaknesses, stated before the data

- **n=9 is small.** One bad scenario moves the result. That is why the bar is
  8/9 rather than a totals comparison.
- **Long scenarios have more places to break for reasons that are neither arm's
  representation** — a site rate-limiting, a cookie wall, a flaky third party.
  A scenario that fails for an environmental reason on EITHER arm is dropped
  from the pair and named, and the drop is reported in the headline, not buried.
- **Replay is measured on a reset state, which real apps do not have.** A flow
  that CREATES something is not re-runnable in place (CLAUDE.md #54), so H2
  measures replay against a reset, and the post must say so rather than implying
  flows are idempotent against production.
- **The author cannot be blinded to the sites**, only to the comparison. A
  scenario on a site that happens to defeat one arm's renderer is a real
  outcome, but it is not evidence about representation, per the rule above.

## Files, when it runs

`tasks.md` (author output) · `referee_key.md` (independent re-derivation) ·
`prompts/` (identical modulo the tool namespace, ASSERTED by the generator) ·
`gen.py` · `score.py` · `collect.py` (rebuilds `runs.tsv` from subagent meta —
never self-reports) · `analyse.py` (prints achievable-p and leave-one-host-out)
· `runs.tsv` · `FINDINGS.md` · `CLOSEOUT.md`.
