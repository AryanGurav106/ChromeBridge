# Eval 9 — pre-registration

Written and committed BEFORE any task exists and before any run. Eval 4's
headline had to be withdrawn when its prompt turned out to mandate the
behaviour it measured; eval 7 lost three runs to a generator bug; eval 8 was
void before it started. Each was only catchable because the design was on disk
first.

## Why this one is on PUBLIC sites, which eval 8 learned the hard way

Eval 8 used a locally-hosted benchmark for its exact event oracle, and the
claude-in-chrome arm scored 0/4 because **it is not driving a browser on this
machine**. Measured directly (eval 8, Amendment 3): `localhost:8080` gives an
error page, `https://example.com` loads fine, and this host's LAN address
reports a successful `navigate` while the tab stays where it was. Its tab ids
are `1662410xxx`; ChromeBridge's are `1711645xxx`.

So the trade is forced, and it is the whole reason this design looks like
eval 3's: **a local benchmark buys an exact oracle and costs the other arm
entirely; public sites buy a fair comparison and cost the oracle.** Scoring
here is a short exact string against ground truth a referee establishes
independently.

**A property eval 8 did NOT have, which falls out of the same fact:** the arms
are in different browsers, so cross-arm tab contamination is impossible. #39's
reason for running serially does not apply BETWEEN arms. It still applies
WITHIN an arm, so no two tasks of the same arm run at once.

## Design

- **Tasks written blind.** An authoring agent was told only to write two-hop
  browser tasks with short exact answers and a named distractor, given a
  deny-list of every domain used in evals 1–8, and told nothing about any
  toolset. It verified each answer against the live page or dropped the task.
  Its output is `tasks.json`, committed before any run.
- **Ground truth re-derived by a referee** — headless Chromium, deterministic,
  no model — not taken from the task author. Where the referee and the author
  disagree, the task is DROPPED, not adjudicated.
- **One independent agent per (task, arm).** No shared context.
- **Prompts from one template**, namespace substituted, then asserted identical
  with the namespace normalised away. A difference is a blocking error.
- **Both arms of a task launched together** (different browsers, so no
  cross-talk); tasks run one pair at a time.

## Bars, fixed now

- **H1 (primary)** — paired sign test on tool calls per task, ties excluded.
  At n=6 the best achievable two-sided p is **0.031**, so the bar is reachable:
  **p < 0.05**, i.e. 6/6. 5/6 is p = 0.219 and is a TIE. If tasks are dropped
  and n falls below 6, H1 cannot clear and will be reported as underpowered
  with the achievable p stated beside it.
- **Falsifier** — correctness against the referee's value. If either arm scores
  below 4/6 this is reported as a tooling failure, not a comparison.
- **Noise** — arXiv:2608.06171 measures a 12–14% rerun floor. A totals
  difference inside that band is not a result.
- **Wall clock is not a bar.** #35 and #41 both measured a ~47s/task drift floor
  that swallows it.

## What this cannot show

Both arms are the same model, so correctness saturates and is a falsifier
rather than a metric. And a tool-call count is not a quality measure: an arm
can be fast and wrong, which is what the falsifier is for.

---

## AMENDMENT 1 — two pairs per wave, not one. Written at launch.

The design above says "no two tasks of the same arm run at once". I am running
**two pairs per wave** (4 agents), so two tasks of the same arm DO overlap.

Reason, and the evidence for it: eval 8 ran four chromebridge agents
concurrently and all four completed, each in its own tab. The within-arm hazard
is specifically the one two of eval 8's claude-in-chrome agents reported —
`tabs_context_mcp(createIfEmpty)` handing out a tab another agent then
navigated — and every brief here carries the same instruction, identical in
both arms: *"Work in a tab you open yourself, and leave any tab that was
already open exactly as it is."*

**The risk this accepts, stated plainly:** if an agent reports an anomaly that
looks like another agent moving its tab, that pair is dropped rather than
scored, and the drop is recorded. It is not adjudicated and it is not quietly
kept.

Cross-arm contamination remains impossible for the reason in the design: the
arms are in different browsers (eval 8, Amendment 3).

Waves: `T3,T5` · `T6,T7` · `T8,T9` · `T10,T11`.
