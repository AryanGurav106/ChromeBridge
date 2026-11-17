# Eval 9 — closeout

**A TIE, and it fails the bar that was fixed before any task existed.**
Reproduce with `python analyse.py` from this directory.

| | |
|---|---|
| H1 PRIMARY (paired sign test on tool calls) | **4/7 decided pairs to CB, p = 1.0000** |
| best p achievable at n=7 | 0.0156 — so the bar was reachable and was not met |
| pre-registered bar | p < 0.05 |
| total calls, scored pairs | CB **58** v CIC **68** (14.7%) |
| falsifier (correctness vs the referee) | **0 wrong of 16** |

| task | site | CB | CIC | |
|---|---|---|---|---|
| T3 | NOAA annual mean CO2 | **5** | 8 | CB |
| T5 | gesetze-im-internet BGB | 1 | 4 | EXCLUDED (Amendment 5) |
| T6 | postgresql docs | 11 | **7** | CIC |
| T7 | debian release history | 9 | **7** | CIC |
| T8 | federalreserve.gov | **6** | 13 | CB |
| T9 | kubernetes.io | **7** | 12 | CB |
| T10 | boe.es (es) | **8** | 12 | CB |
| T11 | nobelprize.org | 12 | **9** | CIC |

The totals lean our way by 14.7%, a hair outside the 12–14% rerun floor
arXiv:2608.06171 measures for this kind of A/B. **That is not the result.** The
sign test is what was pre-registered, precisely because it is immune to one
blow-out pair, and it says 4/7 — the least informative number available. Evals
5 and 7 both cleared; this one does not, and quoting the totals instead would
be picking the statistic after seeing the data.

## Why, and it is mine

`analyse.py` counts it rather than asserting it: **5 of our 7 scored runs lost
calls to a guard I shipped hours before this eval began.**

`computerOp`'s dead-click guard reports `NO EFFECT` when a click was delivered
and the page did not change. Its own comment claims that requiring
`_delivered === true` means "same document", and **that is false.** The delivery
probe lives on `window` of the OLD document and the readback is one
`executeScript` round trip — a few milliseconds — after `mouseReleased`. A
click on a link has not committed its navigation by then, so the probe is alive,
answers `true`, and the before/after snapshot is taken twice against the page
being left. Identical, every time. The guard then marks a click that did the
biggest thing a click can do.

It is a comment stating a guarantee the code does not have, which is the C15
class inside a guard written to stop tools claiming things they have not
checked. Recorded as Amendment 7 during the run and NOT fixed during it;
changing the build mid-eval would have invalidated the arm.

Cost: roughly one to two extra calls per affected task — a `get_url` or a
re-read to find out whether the click had in fact worked. On T6, T7 and T11 that
is the whole margin.

## The comparison the defect makes available, which is worth more than a win

Both products are currently wrong about what a click did, in **opposite
directions**:

- **Ours over-warns.** It says NO EFFECT and the page moved. The agent spends a
  round trip discovering it was fine.
- **Theirs under-warns.** T9: `ref clicks reported SUCCESS and never navigated`,
  about five calls, recovered only by abandoning the ref for a coordinate.
  T11: the same shape again.

An over-warn costs a re-check. A false success costs the agent its belief about
which page it is standing on, and every observation after it is about the wrong
document. Ours is the better failure and it is still a defect.

**One thing is NOT resolved in our favour.** T11/cb's agent wrote that clicks
"reported success or NO EFFECT without navigating" and did not separate the two.
If the first half is real we produced a false success too. It is recorded as
`cb-false-success?` with the question mark, because deciding an ambiguity in the
home arm's favour is the one move a scorer does not get to make.

## Amendment 8, and that it fired on both arms

An href READ OFF a page the agent navigated to is a link followed; only a URL
recalled from prior knowledge is the shortcut Amendment 5 excludes. Our listing
carries `href` at `brief` detail (#61) and eval 7 recorded the other arm's
`find` omitting it, so the move is more available to us — which is why the rule
had to be written down rather than decided per task.

It then fired on the other arm unprompted: **T11/cic** reached its last hop by
the Macleod link's own href after a ref click did not navigate, the same move as
T11/cb two rows up. The rule is symmetric in practice and not only on paper.

## What this eval cannot show

Both arms are the same model, so correctness saturates — 16/16 — and is a
falsifier, not a metric. A tool-call count is not quality: an arm can be fast
and wrong, which is what the falsifier is for. n=7 decided pairs is small. And
the headline comparison is confounded by our own build being broken, which is a
reason to fix it and re-run, not a reason to discount the tie.

## What happens next

1. Fix the guard: ask Chrome whether a main-frame navigation STARTED on this tab
   since the click, from `_navState`'s own counter, instead of inferring "same
   document" from a probe that outlives the click. That is #51's ask-don't-predict
   move applied one probe over, and #56's own `null`-claims-nothing rule, which
   the effect probe was never given.
2. A check that fails against the current code: a navigating click must not carry
   the `NO EFFECT` token even when the delivery probe survives the readback.
3. Re-run, with the bar unchanged and this closeout left in place. A result that
   improves after a fix is only meaningful next to the one it replaced.
