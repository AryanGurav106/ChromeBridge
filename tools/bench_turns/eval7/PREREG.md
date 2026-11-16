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

---

## AMENDMENT 2 — 2026-11-16, after runs 1–2, before run 1 is re-run

**One build per arm, for the whole eval.** Three changes to
`extension/background.js` landed during eval 6's write-up and were not live
when run 1 executed: the entry cap no longer gives `section=dialog` priority
unless a dialog is actually open, the cap notice names `query_elements` for rows
that share one label, and the scoped readiness note states the page-wide
recency as a bound instead of recommending an unscoped re-read.

**Two of eval 7's eight apps carry the off-canvas drawers the first of those
fixes is about**, so leaving run 1 on the old build would put a build change
inside our own arm, between tasks, in the direction that flatters later runs.

**Decision: the extension was reloaded (worker `g25h9p` age 16,015s ->
`p5fcai` age 7s, and `bridge_ms_total` reset to 6.0, which is what distinguishes
a respawned stdio process from a client that merely re-handshook), the
`e7_cb_rail2p` track was recreated from zero, and run 1 is re-run on the new
build.** Its old result (9/9 reachable conditions, 28 browser calls) is
superseded and is NOT carried forward; it survives only in this amendment, as
the thing that found the impossible date in Amendment 1.

**No further `background.js` change until the eval finishes.** Eval-7 findings
are recorded in `docs/OPEN.md` as they are found and fixed afterwards, so that
every ChromeBridge run in this eval is the same build. The Claude-in-Chrome arm
is unaffected either way, which is also what makes it the drift control (#35,
#41): its code has not changed at all.

**What this costs:** one run, about seven minutes, and it is cheaper than a
split build nobody can explain later.

---

## AMENDMENT 3 — 2026-11-16, after runs 1–3, which are all DISCARDED

**AMENDMENT 1 WAS WRONG ABOUT WHOSE DEFECT IT WAS, and the correction came from
the benchmark's own published leaderboard rather than from reading my code.**

Amendment 1 recorded that three tasks ask for a date the app's calendar cannot
reach, measured it carefully, and called it "a decay property of the benchmark
itself, worth reporting upstream". The measurement was right. The attribution
was not.

`liderboard/results/raw/*/results.json` ships per-condition results for 24
published model×harness runs. A run started **2026-09-16** carries

```
{"event_name": "select_date", "parameters": {"date": "2026-09-17"}, "success": true}
```

for the task whose file says `2026-09-04`. **Their harness rewrites the date.**
`bench_eval/task_dates.py` says so in its own docstring: *"Task JSON keeps
authored ISO dates as templates; this module shifts a task's booking dates (and
matching prompt text) forward by one shared delta when the earliest date would
otherwise be in the past."* Hotel and rail calendars disable past days, which is
exactly the wall both arms hit.

`make_tracks.py` merged the task file verbatim and never called it. **The
impossible task was mine.**

**THE FIX, and it is better than the workaround it replaces.**
`make_tracks.py` now imports the benchmark's own `apply_booking_dates` and
REFUSES to generate tracks if it cannot — generating with authored template
dates is precisely what produced Amendment 1. All 16 tracks are recreated.

| task | prompt was | prompt now | conditions |
|---|---|---|---|
| rail2p | 04.09.2026 | **16.11.2026** | `2026-11-16` |
| railpay | 04.09.2026 | **16.11.2026** | `2026-11-16` |
| hotel2rm | 12–16.09.2026 | **16–20.11.2026** | `2026-11-16`, `2026-11-20` |
| hoteldxb | 05–09.03.2027 | unchanged | already future |

The gap is preserved and the prompt text is rewritten with the conditions, so
the task an agent reads and the oracle it is scored against agree.

**AMENDMENT 1's EXCLUSION IS WITHDRAWN IN FULL.** All 39 conditions are
reachable; both denominators are now 39 and will print identically.
`unreachable.json` keeps the four under a `withdrawn` key rather than being
deleted, so what was excluded stays visible and the scorer's exclusion path
stays exercised.

**RUNS 1, 2 AND 3 ARE DISCARDED** and their tracks recreated from zero. They ran
against a task that asked for an impossible date, and the two arms handled that
differently in a way that makes them incomparable: run 2 (CIC) declined to edit
the URL, writing *"the task required completing through the page's own UI"*, and
run 3 (CIC) did edit it, writing *"reaching the requested date required the URL
parameter"*. Scoring those against each other, or against a ChromeBridge run
that picked a different date again, would be comparing three different tasks.
Nothing from them is carried forward. What they bought is this amendment, and
two findings already recorded in `docs/OPEN.md` (4e, 4f).

**WHAT I WOULD DO DIFFERENTLY, stated because it is the reusable part:** #48's
eval had a referee validate every task before any run, and it dropped two.
Eval 7 had no such pass, and the thing that found this was a run. A generator
that merges a task file should be read against the harness that normally
consumes it — the answer was in a file called `task_dates.py` the whole time.

**AN EXTERNAL BASELINE, recorded now rather than after seeing our numbers.**
The same leaderboard gives published pass rates for all 24 runs on these exact
eight tasks:

| task | published |
|---|---|
| rail_book_to_cart_2_passengers | **0/24** |
| rail_book_and_pay_2_passengers | 1/24 |
| ecommerce_basket_three_products | 9/24 |
| hotel_search_scenario_dubai | 10/24 |
| hotel_search_scenario_two_rooms | 10/24 |
| grocery_basket_category_named_product | 10/24 |
| digital_books_author_expensive_basket | 15/24 |
| files_download_pdf | 19/24 |
| **the eight together** | **74/192 = 38.5%** |

against a best published whole-benchmark run of **125/152 = 82.2%**. So this is
a HARD subset, chosen for condition count and not for difficulty, and the
metric has room to move rather than saturating the way every previous
head-to-head here did. **Two caveats, before anyone quotes a comparison:** those
runs are scored all-conditions-or-fail while this eval's primary metric is
conditions satisfied, so the numbers are not directly comparable; and they ran
in September 2026 against their own rolled-forward dates, which is a different
task text from ours. They bound difficulty, not performance.

---

## AMENDMENT 4 — 2026-11-16, after run 7. CHANGES NOTHING; records a threat I did not foresee.

**Both MCP servers are loaded in every agent's environment, so each arm can
read the other's server instructions.** Run 7's Claude-in-Chrome agent did,
explicitly:

> The capability is plainly expressible — the chromebridge server instructions
> loaded in this same session describe the opposite behaviour ("A batch may open
> with `tabs_create_mcp` and OMIT tabId on the steps after it — they inherit the
> tab it just made"). One wasted turn on bookkeeping, every single session.

It is comparing its own tool against ours because ours is in its context.

**What this can and cannot do.** It cannot change what either toolset DOES. It
can change (a) what an agent ATTEMPTS — trying a pattern the other server
documents and its own does not — and (b) the feedback it writes, which is the
qualitative half of this eval.

**Direction of the bias is AGAINST the arm that reads the other's instructions
and tries the unsupported pattern**, which here is Claude-in-Chrome. So it does
not flatter us; if anything it costs them a call. That is the opposite of the
direction that would need the eval re-run, and it is why nothing changes.

**Not fixed, deliberately.** Suppressing it means telling every agent to ignore
a namespace, which is more instruction in a prompt whose whole discipline is to
teach neither arm anything (#45). Unloading one server per run would change the
environment between arms, which is worse.

**How to remove it properly, if this eval is ever repeated:** run each arm in a
session with only its own server registered. That is a harness change, not a
prompt change, and it is the right one.

**Recorded here rather than in FINDINGS** because a threat to validity found
mid-run belongs with the design, dated, including the part where I did not
anticipate it.

---

## AMENDMENT 5 — 2026-11-16, after run 12. CHANGES NOTHING; records a fact about the build.

**Every ChromeBridge run in this eval is on ONE build, server AND extension,
and it is the build as of the reload before run 1.** Amendment 2 covered the
extension deliberately. The server half is true by accident and is worth stating
because it is load-bearing for how the findings read.

The stdio server imports `mcp_server.py` at CONNECT time. The last `/mcp`
reconnect was before run 1 was re-run, so every server-side fix made since —
and there have been several, each from a finding in this very eval — is on disk
and NOT in the running process. `sw_info` says so without being asked:

```
server_code_changed_since_start: ["mcp_server.py", "core/flows/model.py",
                                  "core/flows/runner.py"]
```

**Confirmed from an agent rather than from that field.** Run 12 quoted
`"[1] waited 257ms … this step read the settled page"` — wording replaced hours
earlier. The agents are reading the old strings, which is exactly what one build
throughout means.

**Two consequences, both stated rather than left to be inferred:**

1. **No server-side fix in this session has been verified live.** Each is
   fixtured, most are ablated against the pre-fix code, and none has been seen
   working through a real Chrome. #43's rule is explicit that fixtures encode
   what you thought of; the live pass is owed and must happen after the eval,
   not during it.
2. **A finding reported by a later run may already be fixed on disk.** Run 12's
   report of the batch/banner contradiction is a real example: the wording it
   quotes was changed after run 4 raised the same thing. Reading the findings
   file as a list of OPEN defects would overstate the backlog, so each entry
   says its status.

**What would have been wrong to do:** reconnect mid-eval to pick the fixes up.
That splits the server build inside our own arm, between tasks, in the direction
that flatters later runs — the identical hazard Amendment 2 reloaded the
extension to avoid, one layer down.
