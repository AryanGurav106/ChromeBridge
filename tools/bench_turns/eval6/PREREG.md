# PRE-REGISTRATION — EVAL 6, `format` priced on SUCCESS

Written **before any track is created and before any agent runs**. Nothing below
is revised after data; corrections go in dated amendments.

## The question, and why it is still open

`read_page(format=…)` defaults to `"tree"`. CLAUDE.md #27 shipped that default
on an **explicitly NULL A/B**: six agents, five tasks, 15/15 correct in both
arms, 3 content escapes in both arms, zero `javascript_tool` in either. It was
shipped on a judgement — that a flat list cannot express a row, and that the
cases where the formats differ are cases where flat misleads — with the token
cost (+8.7%) accepted explicitly, because **no metric in this project could read
a listing the way an agent does.**

`OPEN.md` item 11 has said since then that `detail` and `format` are priced on
recall and tokens and never on end-to-end success. This prices `format` on
success.

## Why this benchmark and not the others

WebPageBench's oracle is a **semantic event emitted by the app's own business
logic after the state mutation** — verified by reading `check()`'s imports (no
model) and by watching a real run: the generic click tracker fired 2 `click` and
2 `scroll` events and the condition keyed on **neither**. It cannot see how the
agent acted or what it was shown, which is exactly what a representation
comparison needs and what every benchmark here has lacked.

Mind2Web cannot do this: no agent loop, and #73/#78 measured two of our eight
admitting signals at 0/186 there. The frozen corpus is read-only HAR with no
success to check. `bench_turns`' own correctness metric is saturated at 100% on
both arms across four evals, because both arms are the same model.

## Design

- **Arms: `format="tree"` (default) vs `format="flat"`, PINNED.** Every other
  parameter identical. #27 pinned `filter="interactive"` for the same reason:
  the listing must be the thing under test.
- **One track per (task, arm)**, created from `config.json` merged with the task
  file. Tracks are independent, so no arm inherits another's state.
- **Agents are independent and are told nothing about a comparison**, which arm
  they are, or that `format` is under test. They get the task text and the
  pinned parameter.
- **Serial.** #39 recorded six parallel agents corrupting each other's tab
  groups.
- **Scored from the ORACLE and the TRANSCRIPT, never from self-reports.** Eval 4
  Amendment 5 found `runs.tsv` holding agent prose where the scorer expected an
  id, and re-scoring moved 2 of the first 5 pairs.

## Hypotheses and bars, fixed now

**H1 — SUCCESS. The primary, and I expect it to be NULL.** Two-tailed sign test
on decided pairs, bar p<0.05. With n=5 the best achievable p is **0.0625**, so
**H1 CANNOT CLEAR at this sample size and is reported as descriptive only.**
That is stated now rather than discovered later: a 5-task success comparison is
a pilot, and claiming significance from it would be the thing pre-registration
exists to prevent. If both arms succeed on everything, **that is the result** —
it means `format` does not decide success on these tasks, and #27's null A/B
generalises to a second, oracle-scored benchmark.

**H2 — TURNS, and this is where any signal will actually be.** Every previous
eval here found correctness saturated and turns discriminating. Reported per
pair with the sign test and its achievable p beside it. **No bar; descriptive.**

**H3 — THE FALSIFIER THAT CAN FIRE AT n=5.** If either arm **fails a task the
other passes**, that is a real asymmetry worth chasing regardless of p, and the
transcript of both runs gets read by hand. A single such pair is more
informative than the aggregate at this size.

**H4 — a prediction that can be wrong.** I predict **no success difference** and
**tree ≤ flat on turns**, because #27's qualitative finding was that flat
misleads on grouped records (two folds of unequal length both claiming document
order) rather than that it loses information. If flat wins on turns, #27's
token cost was paid for nothing on these tasks and the entry needs correcting.

## What this will NOT measure, stated now

- **`detail`.** Measured earlier today: the ladder is inert on 4 of 6 domains,
  because `brief`/`full` differ from `compact` by `href=`/`src=` and books and
  shop have **0 anchors**. Any `detail` arm would be measuring hotels and rail
  only.
- **Anything about the consent model.** One grant covers all six apps because
  they are one origin, so this eval pays no per-origin cost and says nothing
  about one.
- **The web.** Six synthetic Russian-language apps by one team, v1 preprint, not
  peer reviewed.

## Known weaknesses, before the data

- **n=5 cannot clear its own primary.** Stated above; the eval is a pilot and is
  labelled one.
- **The tasks are Russian.** That is a property of the benchmark and it applies
  to both arms equally, but it is not nothing: a format difference could
  interact with a non-Latin listing in a way this design cannot separate.
- **One agent per cell.** A rerun of the same cell can differ by more than the
  arms do — arXiv:2608.06171 measures a **12–14% rerun noise floor** for
  observation-format A/Bs on WebArena. At n=5 with one run per cell, this eval
  is inside that floor and cannot escape it. That is the strongest reason H1 is
  descriptive.
