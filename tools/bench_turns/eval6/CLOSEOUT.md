# EVAL 6 — CLOSEOUT

Ten runs, five pairs, all scored from the oracle (`score.py`, re-runnable from
`tracks.json` against a live WebPageBench at `localhost:8080`). Raw verdicts in
`scores.json`; every claim below is re-derivable from it and from `FINDINGS.md`.

## The result

| pair | tree | flat | decided |
|---|---|---|---|
| hotels | 8 | 9 | tree |
| books | 7 | 7 | tie |
| shop | 6 | 6 | tie |
| files | 6 | 6 | tie |
| grocery | 7 | 6 | **flat** |
| **total** | **34** | **34** | **1–1** |

**H1 (success): 10/10 PASS on both arms.** Pre-registered as descriptive — at
n=5 the best achievable p is 0.0625, so it could not have cleared and the
pre-registration says so in writing. The falsifier H3 (either arm failing a task
the other passes) **did not fire**.

**H2 (turns): dead level, 34–34, one decided pair each way.** A sign test on two
decided pairs gives p = 1.0. The eval sits inside the **12–14% rerun noise
floor** arXiv:2608.06171 measures for observation-format A/Bs, which the
pre-registration named as the strongest reason H1 is descriptive.

**H4 was half right.** I predicted no success difference (correct) and
tree ≤ flat on turns (wrong at the total — exactly level). So #27's +8.7% token
cost for the tree is **not** repaid in turns on these five tasks, and it is not
punished either.

## What this settles, stated narrowly

**`format` does not decide success on these tasks.** #27 shipped the tree
default on an explicitly NULL A/B and said so at the time; this is a second,
oracle-scored benchmark reaching the same null on a different app family, a
different language and a metric that reads the app's own business events rather
than a listing. `OPEN.md` item 11's success half is answered for `format`: the
answer is "no measurable difference", not "tree wins".

It does **not** say the two formats are interchangeable. #27's argument was
never about success rate — it was that a flat list cannot express a row, and
that the cases where the formats differ are cases where flat misleads
(two folds of unequal length both claiming document order). This eval contains
no task where that shape decides the answer, so it does not test that argument.

## What it actually bought

Six defects, **none of them in the collector**, which is the finding worth
carrying forward. Everything the agents hit was in the layer that TALKS about
the listing — a note, a priority rule, a tense, a length gate:

| # | defect | fix |
|---|---|---|
| 1 | aria-hidden note offered a recovery that structurally cannot work | AH5 |
| 2 | `find`'s miss census claimed to describe the page | F37 rewritten |
| 3 | off-viewport hint named regions by TAG, so two agents scoped to the wrong `<form>` | RG2b/RG2c |
| 4 | readiness banner asserted a present tense its own number contradicted | R-TENSE |
| 5 | cap notice ignored the recovery in its own response | C35/C35b |
| 6 | a length gate decided a disambiguation, written twice | NB2/NB2b |
| 7 | cap notice had no answer for rows that share ONE label | CT1c |
| 8 | **a CLOSED off-canvas drawer took every cap slot from the page** | CT2/CT2b |

Plus one class named rather than fixed: **rows that mean different things,
printed the same** (three independent instances across three pairs). Every
guardrail in this project scores PRESENCE, and in all three cases everything
was present — so no existing ruler can see it, and an agent cannot detect it
from the output alone.

And one decision left to the owner with a number attached: 43 sibling groups on
the shop app declare their selected state **only** in a class token, 42 of them
(98%) declaring nothing an ARIA or native rule can read. #29 deleted that token
as measured-dead on a corpus that included Vuetify but not this shape — #25's
rule applied to a DELETION rather than an addition.

## Open, with evidence

- **`search_page`'s climb is a no-op against a chain of same-text wrappers.**
  Measured six levels deep on the grocery cart widget. The stated rule is about
  sufficiency; the implementation applies it once. Candidate fix and why the
  obvious one re-opens #43 are in `FINDINGS.md` and `docs/OPEN.md`.
- **The drawer fix is corpus-measured and fixture-pinned but not yet
  live-verified** — the "before" was reproduced through the real extension on
  the real page, the "after" needs an extension reload.

## Weaknesses of this eval, restated after the data

Everything the pre-registration listed still applies and nothing got better:
n=5 cannot clear its own primary; one agent per cell against a 12–14% rerun
floor; six synthetic Russian-language apps from one team, v1 preprint, not peer
reviewed. The per-pair turn numbers are therefore **descriptive only** and the
honest headline is the defect list, not the 34–34.
