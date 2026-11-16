# Eval 8 — pre-registration

Written and committed BEFORE any run. #45's headline had to be withdrawn when
its prompt turned out to mandate the behaviour it measured, and that was only
catchable because the prompt file still existed; eval 7's Amendment 1 was a
generator bug found the same way. So: tasks, prompts, tracks and bars first.

## Design

8 tasks x 2 arms = 16 conditions, one independent agent each, no shared context.
Tasks and the oracle come from WebPageBench (arXiv:2609.35026, Apache-2.0),
unchanged. Tracks minted fresh under the `e8_` prefix so no eval-7 event log can
contribute. `make_tracks.py` calls the benchmark's own `apply_booking_dates`,
and refuses to run if it cannot import it — that refusal is eval 7's Amendment 3.

Arms differ ONLY by tool namespace and track id. Asserted mechanically before
launch by normalising both away and diffing: **16 prompts, 0 differences**.

## The one deviation from eval 7, declared

Each agent is given a POINTER to its brief in `prompts.json` rather than the
brief inline. That adds exactly ONE file read to every condition, in both arms,
so it inflates absolute turn counts by 1 and cancels in a paired comparison.
H1 is a sign test over pairs and is unaffected; absolute totals are not
comparable to eval 7's and will not be quoted as if they were.

## Bars, fixed now

- **H1 (primary)** — paired sign test on tool calls per task. At n=8 the best
  achievable two-sided p is 0.0078 (8/8). **Bar: p < 0.05**, i.e. at least 7 of
  8 decided pairs. 6/8 is p = 0.289 and is a TIE, whatever the totals look like.
- **H2** — turns to first page content; descriptive, no bar.
- **H3** — one-turn start (create+navigate+read in a single batch); descriptive.
- **Falsifier** — correctness by the benchmark's own event oracle. If either arm
  scores below 6/8 the run is reported as a tooling failure, not a comparison.
- **Noise** — arXiv:2608.06171 measures a 12–14% rerun floor for
  observation-format A/Bs. A totals difference inside that band is not a result.

## Scoring

`score.py`, unchanged from eval 7, against each track's own `/event/get`. Turn
counts read from transcripts, not self-reports (#47 found two scorer defects
that way). Ties are pairs with equal call counts and are excluded from the sign
test, as in eval 7.

## What this cannot show

Both arms are the same model, so correctness saturates and cannot discriminate —
it is a falsifier, not a metric. Wall clock is not a bar: #35 and #41 both
measured a ~47s/task drift floor that swallows it.
