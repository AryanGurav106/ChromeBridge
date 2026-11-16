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

---

## AMENDMENT 1 — written at launch, before any result

**4 tasks, not 8.** Launched `shop3`, `grocat`, `hoteldxb`, `rail2p` — 8
conditions. All 16 tracks exist and the other four tasks can be run later, but
the account came off a weekly API limit under four hours ago and sixteen
browser agents at once is how it is re-exhausted. Running half and reporting
half honestly beats running all and losing the lot.

**This moves the bar, and the bar moves BEFORE the data.** At n=4 the best
achievable two-sided sign-test p is **0.125**, so **H1 cannot clear p<0.05 at
this n, by construction.** A 4/4 sweep is reported as 4/4 with p=0.125 and
called *directionally consistent, underpowered*, never as a result. That is the
same arithmetic eval 3's AMENDMENT 1 ran into and it is stated here first
rather than discovered afterwards. The remaining four tasks would take n to 8
and the bar back to p<0.05; whether to run them is a decision for after these
land.

**Both arms of each task launched TOGETHER**, rather than serially with the arm
order rotated as in evals 3 and 7. Contemporaneous pairs are a stronger drift
control — the two arms see the same machine, the same browser and the same
minute — and the cross-talk that forced serial running in #39 is addressed
differently here: every brief tells the agent to work only in a tab it creates
itself and to leave pre-existing tabs alone.

**Falsifier unchanged**, scaled: if either arm scores below 3 of 4 on the
benchmark's own event oracle, this is reported as a tooling failure rather than
as a comparison.

---

## AMENDMENT 2 — THE RUN IS VOID. Written as the results came in.

**The falsifier fired.** My own bar: *"if either arm scores below 3 of 4 on the
benchmark's own event oracle, this is reported as a tooling failure rather than
as a comparison."* The claude-in-chrome arm scored **0 of 3 returned** — every
one failed before touching the app.

All three failed identically:

```
navigate -> "Navigated to http://localhost:8080/e8_cic_…/"
read_page -> Failed: Frame with ID 0 is showing error page
screenshot -> same
```

Each retried on `localhost` and on `127.0.0.1`, one after a 3s wait. Each
checked `curl` from a shell and got **HTTP 200 in ~1ms**.

**And it is not the app, which I verified rather than assumed.** ChromeBridge
loaded `http://localhost:8080/e8_cic_rail2p/` — the very URL the cic agent
could not open — routed to `/state_rail_main/bench_rail_main`, and read 45
elements off it. Same browser, same minute, same track. So the failure is on
the claude-in-chrome side and the arms were never comparable.

**Therefore no comparison is reported from this run, and none will be quoted
from it.** The chromebridge numbers that did land are recorded below as
observations about our own arm only. A result built on the other arm failing to
reach the start page would be worthless, and worse than worthless if published.

**What the cause probably is, stated as a hypothesis and NOT as a finding:**
claude-in-chrome has its own per-site permission model, separate from
ChromeBridge's side-panel grant, and the brief's line "permission for
localhost:8080 is already granted" is true only of ours. Eval 7's cic agents
did reach the app, so something differs — the container restart, the new track
ids, or that extension's state. Not diagnosed, and it is not this project's bug
to diagnose.

**Contamination note, in our favour and therefore worth stating loudest:** two
cic agents reported that `tabs_context_mcp(createIfEmpty)` handed them a tab
another agent then navigated, so the arms shared a tab group. Contemporaneous
pairs (Amendment 1) bought a drift control and cost tab isolation. If this is
rerun, the arms go back to serial with rotation, which is what evals 3 and 7
did and why.

## Observations about the chromebridge arm only (NOT a comparison)

- `grocat:cb` **completed** in 12 calls (11 browser). One-turn start, 0 ceremony
  calls. Its agent named three things unprompted: the readiness banner fired on
  a page that was already actionable; `find` for "Оливки … add to cart" returned
  the image and the name div but not the «Добавить» button, which is named only
  "Добавить" with no product in it; and a default `filter="all"` read after a
  nav dumped a very long PAGE TEXT block it did not need.

---

## CLOSEOUT — void as a comparison, and the most productive run so far

**Final tally. ChromeBridge 4/4 completed; claude-in-chrome 0/4.** All four of
theirs failed before touching the app, identically. That is the falsifier, so
**no comparison is reported** — see Amendment 2 for the verification that it is
not the app.

What the run was actually worth is the chromebridge arm's own feedback, because
four agents drove four real multi-step flows and three of them independently
hit the same wall.

### THE FINDING: real controls absent from the listing, on four apps

| arm | what was missing from `read_page` |
|---|---|
| `hoteldxb:cb` | the **entire search form** — destination, dates, guests, Найти |
| `rail2p:cb` | calendar day cells, city suggestions, passenger `+`, seat-map seats |
| `shop3:cb` | the add-to-cart button (text «Завтра», not «В корзину») |

Each fell back to screenshots and coordinate clicks. One said it plainly: the
form "was not in it ... I had to run `query_elements(...)` to get the refs."

**DIAGNOSED IN ONE CALL, by the diagnostic built for exactly this.** Reproduced
live, then `read_page(ref_id=…)` on the missing field answered:

> *an ancestor is `aria-hidden="true"`*

`query_elements('[aria-hidden="true"]')` names the culprit: `div.blockWrapper`,
carrying the whole widget — *"Направление Заезд Выезд 1 номер для 1 гость
Найти"*. **The app marks its own main content inert while displaying it.** The
collector dropping it is #28's rule working: the page declared it absent.

**What was OURS is the advice.** That message said aria-hidden is *"usually a
library marking the page inert behind an OPEN menu or dialog somewhere else;
close that and re-read"* — one named cause and a recovery. On this page the
only `role=dialog` is **not rendered**: nothing was open and nothing could be
closed. #33's class, in the one message that fires when the page's own content
has vanished, and C15 could not see it because the sentence is declarative.

Fixed the way #33 fixed the page-level note: look for the popup in what is
ACTUALLY RENDERED, name it when present, and otherwise state the fact, refuse
to pick a cause, and point at `query_elements` — which reaches these elements,
because it queries the rendered document instead of applying the listing's
visibility rule. AH6 fails pre-fix; AH6b covers the other branch.

**NOT changed: whether to list aria-hidden content at all.** That is #28's
delete rule and changing it needs its own measurement, not an anecdote. Recorded
as the open question this run raises.

### Also reported, unprompted, by the chromebridge agents

- The readiness banner fired on pages that were already actionable — **three of
  four said so**. Same complaint as eval rounds 1 and 2.
- `find` missed the add-to-cart button for "Оливки … add to cart" (it is named
  only «Добавить», with no product in it) and returned NO CONFIDENT MATCH for a
  hotel card that `search_page` found at once.
- Two ref clicks reported "landed" while the URL did not change and nothing
  happened — **the dead-click guard this session made reachable would now mark
  those**, and these runs predate that build.
- The `(occluded/blocked)` flag and long runs of unnamed `div`/`svg` header rows
  were called noise.
