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

---

## AMENDMENT 1 — written after the tasks arrived, BEFORE the referee pass and
## before any run. Three grading defects found mechanically.

The tasks were authored blind and all ten were walked by their author. A
mechanical check of the answer key against each task's own steps — run while
building the blinded referee input — found three problems that would have
corrupted grading. Eval 4 found the same class twice (Amendments 6 and 7) and
found it AFTER 12 runs; this is the same check moved before the data.

**(a) T4 carries ZERO backticked answer values, so it cannot be graded.** The
key is built from backticked spans on the `**Answer:**` line (eval 4 Amendment
6, adopted because comma-splitting breaks on an answer that contains commas). A
task with no span has an empty requirement set, which every answer satisfies —
a check that cannot fail, which is the defect `record_flow(stop)` warns about in
a different part of this repo. **T4 is DROPPED unless its author supplies
backticked values at the referee pass.** It is not silently patched by me: I
have read the answers and can no longer act as its author.

**(b) T5 and T10 have an answer span that is also an INSTRUCTION term.** T5's
answer is `University of Vermont` and its step 4 says "click **University of
Vermont**". T10's answer carries `狼煙町` as a qualifier and its step 6 says to
find 狼煙町. A grader keying on backticked spans would credit an agent for
echoing the instruction it was given.

Neither is a leak of the thing being asked — T5 asks which of two universities
is higher and the steps visit both; T10 asks for a postal code. But the GRADER
cannot tell an echo from a derivation. Fixed at the grader, not the task:
**a required span that also appears in that task's own prompt is dropped from
`require_all` for that task**, leaving T5 on `$19,058` and T10 on `927-1441`,
which are the values only the live page can supply. If that leaves a task with
no requirement, it is dropped under (a).

**(c) The first blinding attempt leaked 5 of 17 answer values** and would have
handed the referee the key. It stripped `**Answer:**` and `**Verified:**` lines
— a blacklist — and the values leaked through the author's FLAG prose, which
discusses the figures it cautions about ("the count of 96 and which occupation
lands…"). Rebuilt as a WHITELIST: only the title, site, numbered steps and
question survive. This repo's own rule, applied to a protocol rather than to
code.

**A note on my own check, because it was wrong first too.** It compared every
answer value against the WHOLE blinded file and reported `17` as leaked — in
fact matching the substring inside "drops from 17 to", in an unrelated task. A
value must be checked against ITS OWN task's section, with word boundaries. The
global substring version reported 5 leaks where there are 2, which is the
flattering-or-damning-result rule landing on a safety check.

---

## AMENDMENT 2 — the referee pass. Written BEFORE any run.

An independent referee walked all ten scenarios on the live sites without the
author's answers (blinded by whitelist; see Amendment 1) and reported no
contamination. **10/10 completed. 3 dropped or reworded, and one of them was
found by the referee and by nobody else.**

**T1 — DROPPED. Its step 7 is factually wrong and yields TWO defensible
answers.** The step says "click the OCCUPATION header once to sort A→Z". The
referee checked the live table and it is **already** sorted A→Z on a pristine
load (`aria-sort="ascending"`, `order [[0,"asc"]]`, rows begin Accountants /
Actors / Actuaries), and the column's `asSorting` is `["asc","desc"]` — so one
real click toggles to DESCENDING. Verified by clicking it. Page 3 row 1 is
therefore `Law teachers, postsecondary` under the step's stated INTENT and
`Healthcare diagnosing or treating practitioners, all other` under what the step
literally instructs. The count `96` is unambiguous either way. **Author and
referee agree on the answer and the task is still unusable**, which is a drop
condition the protocol did not previously have words for: not "the two
disagree", but "the instruction admits two readings". Recorded as a drop rather
than quietly reworded, because I have read the answer key and can no longer act
as this task's author.

**T4 — DROPPED, confirming Amendment 1(a) by a different route.** Every token in
the PyTorch download box is determined by selections the instructions already
state (`libtorch`, `cu132` ⇔ CUDA 13.2, `shared-with-deps` ⇔ Linux, and the only
ABI offered). **The one fact that must be read off the page is the version
`2.15.0`** — and that is the most perishable value in the set, since PyTorch
ships minor releases quarterly and the CUDA labels churn with them. Ungradeable
as written AND severely time-sensitive.

**T5 — KEPT, with the grader restricted.** Amendment 1(b) is confirmed: both
institution names are handed over by steps 4 and 8, so "which had the higher"
is a coin flip between two strings the agent was just given. **Only `$19,058`
and `$11,952` come from the live page**, and `require_all` for T5 is restricted
to those. The referee also found a second ambiguity no mechanical check would
catch: **"In-state" appears twice** in that expenses block — once under *Tuition
and fees* and once as a band heading over *Total Expenses* ($36,802 / $33,274).
Only the first is single-valued, so it resolves; the step should say "In-state
**tuition and fees**".

**T10 — KEPT, graded on the code alone and EXACTLY.** Amendment 1(b)'s flag is
technically right and does not bite: the instructions give the town and its
reading, but **`927-1441` is not in them and is only obtainable live**.
Critical grader note: `狼煙新町` = **927-1442** sits directly above `狼煙町` =
**927-1441** in the same list, differing in the last digit, so **prefix matching
on `927-144` credits the wrong row.** Exact match only.

**T7 — KEPT and FLAGGED.** The top event (M8.2 at 600.0 km) is safe. The count
`17` is fragile: two of the seventeen sit exactly at M7.0 and USGS still revises
these, so one downward revision makes it 16. Re-verify immediately before the
run. Cross-checked against the USGS FDSNWS API, which agreed with the UI.

**Time sensitivity, now named per task**: T4 severe, T1 and T7 moderate, T5
mild. Stable: T2, T3, T6, T8, T9, T10. **No visitor or geography dependence
found on any of the ten.**

**THE BAR RECALCULATES WITH n, MECHANICALLY, AND IS NOT RE-CHOSEN.** The RULE
fixed before any data was a two-tailed sign test at p<0.05 on decided pairs.
Dropping T1 and T4 leaves **n=8**, where the achievable values are 0.0078 (8/8)
and 0.070 (7/8) — **so the bar becomes 8 of 8.** That is harsher than the 8/9 in
the original design, and it stands: the threshold follows from the test and the
sample size, and adjusting it after seeing the sample shrink is exactly the move
a pre-registration exists to prevent.

**TWO INCIDENTAL CORRECTIONS**, neither load-bearing: T2 step 3 says the
Programme dropdown drops "from 184 options"; at Autumn Semester 2024 it is
**186** (the "to 31" and "17 → 15" figures are exactly right). And T6 step 3's
"Too many documents" banner could not be reproduced from a plain fetch — it
appears to be client-side rendered. Narrative only; the substantive chain
reproduces.

**A DEFECT IN MY OWN BLINDING TOOL, found by the referee noticing something
missing.** T10's question line is `**Question (English):**` and the whitelist
matched `**Question:**` literally, so that line fell through to the skip branch:
**9 of 10 questions survived when 10 should have.** The referee inferred the
question from step 7 and still answered correctly, which is luck rather than
design. Amendment 1 rebuilt this tool as a whitelist precisely because a
blacklist leaked — and a whitelist that is too literal silently DROPS instead,
which is the same class of error pointing the other way. Fixed to match any
`**Question` prefix.

**AN OPERATIONAL FINDING FOR THE RUN ITSELF, and it is a product observation.**
The referee reported that **ChromeBridge's permission gate refused `bls.gov`**
— default-deny working exactly as designed — and that **as a subagent it had no
way to ask for a grant**, so it completed that task with the other toolset
instead. That is the consent model behaving correctly and a real friction: a
subagent cannot reach the side panel. It is also why this eval needs its grant
decision settled BEFORE the run rather than discovered during it.
