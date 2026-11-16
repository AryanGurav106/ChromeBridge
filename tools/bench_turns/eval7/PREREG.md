# PRE-REGISTRATION — EVAL 7, ChromeBridge vs Claude-in-Chrome, scored by an oracle

Written **before any track is created and before any agent runs**. Nothing below
is revised after data; corrections go in dated amendments.

## The question, and why the five previous head-to-heads could not answer it

#39, #40, #41, #43, #47 and #48 all compared ChromeBridge against
Claude-in-Chrome and all six reported **correctness saturated at 100% on both
arms** — 30/30, 48/48, 38/38. #41 said why in one line: *both arms are the same
model, so the ceiling is Claude's, not the tool's.* Every one of those evals
therefore fell back to TURNS, which #47 then measured as noisier than the effect
it was built to resolve (single tasks moving by 4–5 turns on unchanged code).

WebPageBench breaks the saturation, for a reason that has nothing to do with
being a better benchmark in general: its tasks carry **up to 10 oracle
conditions each**, emitted by the app's own business logic after the state
mutation. An agent that books the right train for the wrong number of passengers
satisfies 7 of 10. **Partial credit is the thing every previous head-to-head
lacked**, and it is what makes a success comparison possible at this sample
size.

## Design

- **Arms: ChromeBridge (`mcp__chromebridge__*`) vs Claude-in-Chrome
  (`mcp__claude-in-chrome__*`).** The other arm's code is UNCHANGED, so it also
  serves as the drift control (#35, #41).
- **8 tasks, 16 runs, one agent per cell.** Chosen for CONDITION COUNT, which is
  the resolution of the primary metric, and spread across all six app families.
  Base task files only — the `__date_native_input` / `__theme_dark` variants are
  the control-swap arms #79 used and would confound this.
- **Serial, arm order rotated per task.** #39 recorded six parallel agents
  corrupting each other's tab groups.
- **One track per (task, arm)**, so no arm inherits another's state.
- **Agents are told nothing about a comparison** or which arm they are. They get
  the task text, the track URL, and the identical surrounding instructions
  modulo the tool namespace — asserted by diffing the two prompt bodies.
- **Each arm follows its OWN server's startup instructions** and pays for them.
  #39 found Claude-in-Chrome's own instructions require a skill invocation
  before its tools; forbidding that would be testing a configuration nobody
  ships. Reported gross AND net of fixed setup, as #39 and #48 did.
- **Scored from the ORACLE and the TRANSCRIPT, never from self-reports.** #47
  found two scorer defects by noticing a self-report disagreeing with the
  transcript.

## Hypotheses and bars, fixed now

**H1 — PRIMARY: oracle conditions satisfied, summed over the 8 tasks.**
Two-tailed sign test on decided TASKS (a task is decided when the two arms
satisfy a different number of its conditions), bar **p < 0.05**. With n=8 the
best achievable p is **0.0078**, so unlike eval 6 this CAN clear. If fewer than
6 tasks are decided, the sign test is reported with its achievable p beside it
and the result is descriptive.

**H2 — tasks fully passed (all conditions met), per arm.** Descriptive. This is
the metric every previous eval saturated on; if it saturates again at 8/8 and
8/8, that is itself the finding and H1 is what carries the eval.

**H3 — turns.** Descriptive only, and explicitly subordinate. #47 established
this metric's noise exceeds the effects it is used on, and #48's margin was
driven substantially by the other arm's own defects rather than by
representation.

**H4 — THE FALSIFIER. If ChromeBridge satisfies FEWER conditions in total, or
fails a task the other arm passes, that is a real deficiency** and both
transcripts get read by hand and written up whatever the aggregate says.

**H5 — a prediction that can be wrong.** I predict **no significant difference
on H1** (p ≥ 0.05) and that the two arms land within 15% of each other on
conditions. The honest prior after six ties is a seventh. If ChromeBridge wins
H1 cleanly, the mechanism must be named from the transcripts before it is
believed — #48 found its widest margin was the other arm failing to render a
page at all, which is not a representation result.

## Known weaknesses, before the data

- **n=8, one run per cell**, against the **12–14% rerun noise floor**
  arXiv:2608.06171 measures for observation-format A/Bs. H1's unit is
  conditions, which is finer-grained than task success and should sit better
  against that floor, but the floor was not measured on this metric and I am not
  claiming it does.
- **Six synthetic Russian-language apps from one team**, v1 preprint, not peer
  reviewed. Nothing here transfers to the web as a percentage.
- **The other arm drives the user's real Chrome and has been observed
  hijacking a pre-existing tab** (#47 recorded it in 5 of 9 runs; it did it
  again on the first call of this session's setup, destroying an unrelated
  page). BOTH arms are given the identical instruction to work in a tab they
  create. Any hijack under that instruction is RECORDED as an outcome, and the
  affected tab is restored by hand after the run.
- **This says nothing about the consent model.** One grant covers all six apps
  because they are one origin. Per-origin consent is a one-time cost this design
  does not charge either arm for, and must not be quoted as though it did.

## The 8 tasks

| # | task file | conds | family |
|---|---|---|---|
| 1 | `rail_book_to_cart_2_passengers` | 10 | rail |
| 2 | `rail_book_and_pay_2_passengers` | 8 | rail (payment) |
| 3 | `hotel_search_scenario_dubai` | 6 | hotels |
| 4 | `hotel_search_scenario_two_rooms` | 5 | hotels (two rooms) |
| 5 | `ecommerce_basket_three_products` | 3 | shop (quantity) |
| 6 | `files_download_pdf` | 3 | files |
| 7 | `digital_books_author_expensive_basket` | 2 | books (comparison) |
| 8 | `grocery_basket_category_named_product` | 2 | grocery |

**39 conditions in total.** Task 7 is in deliberately: "the most expensive book
by this author" cannot be answered by locating a named string, so it is the one
task where reading the page beats finding a control.

---

## AMENDMENT 1 — 2026-11-16, after run 1 of 16, before any other run

**Three of the eight tasks carry a date the app cannot reach, and that is a
defect in this pre-registration.** #48's eval had a referee drop two tasks
before any run for exactly this; eval 7 had no feasibility pass, and run 1 found
it instead.

**Measured, independently of the agent that reported it**, through a browser on
`e7_cic_rail2p` (the OTHER arm's track, untouched, so nothing in the measurement
spends a run):

```
app clock / system date:        2026-11-16
calendar opens on:              Ноябрь 2026
visible .nav-btn count:         1     innerHTML: <i class="mdi-arrow-right ...">
visible text inputs on page:    ["Откуда", "Куда"]        <- no date field
```

One navigation control, forward only, and nothing to type into. `04.09.2026` is
two months in the app's past and is unreachable through the UI by any means.

| task | dates in the prompt | status |
|---|---|---|
| rail2p | 2026-09-04 | **PAST** |
| railpay | 2026-09-04 | **PAST** |
| hotel2rm | 2026-09-12, 2026-09-16 | **PAST** |
| hoteldxb | 2027-03-05, 2027-03-09 | future, fine |
| the other four | — | no date |

This is also a decay property of the benchmark itself, worth reporting upstream:
WebPageBench's task files hard-code dates that were future when they were
authored and are past now, against an app that reads the system clock.

**THE EXACT CONDITIONS THIS MAKES UNREACHABLE — four of 39:**

```
rail2p   [2]  select_date                   {"date": "2026-09-04"}
railpay  [2]  select_date                   {"date": "2026-09-04"}
hotel2rm [1]  bench_hotel_select_start_date {"date": "2026-09-12"}
hotel2rm [2]  bench_hotel_select_end_date   {"date": "2026-09-16"}
```

**THE DECISION, fixed now, before the remaining 15 runs.**

1. **Nothing is dropped and no task is replaced.** Both arms meet the identical
   wall, so these four conditions are UNINFORMATIVE, not unfair, and the other
   35 are reachable and genuinely hard. Replacing the tasks would discard a run
   and buy nothing the exclusion does not.
2. **The primary metric is reported against BOTH denominators, always
   together**: `/39` as pre-registered and unrevised, and `/35` excluding the
   four above. The sign test is unaffected either way, because an unreachable
   condition subtracts the same 1 from both arms of every affected pair.
3. **An arm that somehow DOES satisfy one of the four is believed**, and the
   exclusion is withdrawn for that condition. The claim is "we measured it to be
   unreachable", not "it must be".
4. The four condition identities above are frozen here, in the pre-registration,
   so the exclusion cannot be widened after seeing more data.

**What this costs, said plainly:** the honest headline for rail2p and railpay is
now "9 of 10 conditions, and the tenth is impossible", which is a weaker
sentence than "10 of 10" and the right one. Run 1 scored exactly that — 9/10,
with `select_date` the sole unmet condition, which is what the agent predicted
from the UI before the oracle was consulted.
