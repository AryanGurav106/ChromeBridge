# Flows — record once, replay deterministically

History: CLAUDE.md #49 (the design), #50, #54–#68. Design and rejected
alternatives in `FLOW_RECORDER_PLAN.md`. Per-flow eval results in
`tools/bench_flows/`.

---

## 1. What is actually novel here

Chrome's Recorder, Midscene and workflow-use all record a **human**. A
demonstration says what was done and nothing about what should then be true,
which is why every one of them makes you write assertions by hand.

We record an **agent**, and an agent narrates its postconditions for free: a
`search_page` after a click IS the expected state. ReUseIt (IUI '26) spends
15–52 minutes per task family re-running variations to synthesise the same
guards; we get a first draft from one honest run.

So recording is a **compile**: drop the dead ends, keep the state-changing
steps, rewrite every ref into a declared descriptor, and promote the
observations that followed an action into its postconditions.

Measured: a 2-step flow recorded from 4 agent turns replays in **0.25–0.33s**
with **zero model calls per step**.

## 2. The three rules that cannot be traded away

1. **A postcondition is checked live every run, never healed, never cached.**
   The moment a check can adapt, the suite cannot fail.
2. **A rebound step must satisfy the ORIGINAL postcondition.** Relaxing it
   alongside the heal defeats the only guard there is.
3. **A rebind PROPOSES a patch and never writes.** `run_flow` owns the run;
   `record_flow(action="patch")` owns the file, and it is a separate call the
   agent makes after reading the diff.

Rule 3 is why `on_fail="heal"` was **deleted** rather than implemented (#62): an
automatic rebind means ranking candidates, which is exactly what rule 3 forbids.

**The evidence for rule 3 is now external and strong.** A controlled study of
LLM locator repair found that unanimity across independent model families is a
valid confidence signal for *which surviving element is this* and **actively
anti-correlated** for *does it still exist*: on deleted elements, **34 of 34
unanimous verdicts were false heals**, and growing the model pool from 3 to 7
did not reduce the rate. A non-LLM heuristic baseline produced 40–57% false
heals on removed elements. Separately, a multi-agent test-repair study found
**2 of 7 "converged" families converged by assertion weakening or test
deletion**.

> **Keep the absence test structurally separate from the identity test, and
> never let a fallback rung answer "it's gone."**

## 3. The locator

A ref is per-document, so storing one stores nothing. Everyone else stores a DOM
path, which breaks on the re-render fix #5 exists to survive. We store a
**declaration ladder**, measured over 37 frozen sites and 12,030 controls:

| descriptor | median unique | worst | median tie |
|---|---|---|---|
| tag+role+type | 1.2% | 0.0% | 92 |
| +identity | 62.9% | 23.0% | 4 |
| **+section/heading** | **84.7%** | 39.5% | 2 |
| +near | 86.1% | 42.6% | 2 |

`type`/`placeholder` were **deleted** as their own rung (beat identity alone on
3 of 37 sites by ≤0.9pp). `near` was nearly deleted on its +1.4pp median and
kept on its **distribution** (+9.6pp on one site, helping 17 of 37) — a median
is an ablation over sites, and it measured the corpus.

A link also stores its declared **`href` as an alternate**, tried only after the
recorded descriptor has had its whole settle window. Measured: href is a *worse*
primary key (62.1% unique vs 79.2% for name, lower on 22 of 28 sites) but the
two keys **never disagree** (0.00%), so as corroboration it converts a refusal
into a resolution and can never change a step that already worked. It rescues
30.9% of renamed targets and 15.8% of the count-badge case; the remainder are
buttons, which declare no destination.

`id` (6.8% coverage) and `data-testid` (2.5%) are perfect where present and
almost never present. Not built. Reopens only with a corpus of the internal apps
this feature actually runs against.

## 4. The two problems that do not have clean answers

### Identity can be live data
A nav tab's accessible name is `Records 43` because AccName concatenates a count
badge. Add a record and it is `Records 44`. A rebind can only ever propose
another count-bearing name that re-breaks at 45. Links recover via `href`;
buttons with badges do not, and pause.

### The oracle problem
A recorded assertion can simply be **wrong**, and then the suite passes forever
on a wrong answer. This is not solvable by the recorder and we do not pretend
otherwise. What *is* decidable is whether any evidence exists, so each check is
classified:

- `hollow` — the same value before the step and after, so the step did not move
  what the check measures
- `unwitnessed_absence` — an empty result never observed non-empty; **dropped
  and named**
- `unproven` — never observed before the step at all, so it carries no evidence
  that it would have failed earlier. *Not necessarily wrong.*

The re-grader is a human reading a small JSON diff. What this buys is that
review is **targeted rather than uniform**.

## 5. The ordinal problem — found, measured, and mostly closed (#72)

> `audit_flow_resolve.py` published *"2,726 descriptors, 100% CORRECT, 0% WRONG
> on every mutation"* across six mutations — and **none of them was a reorder.**
> A re-sorted list leaves the crowd's composition identical and only the order
> different, which is the one change an ordinal cannot survive. Measured once the
> arm existed: of 2,496 descriptors, **574 (23.0%) carry an ordinal, and under a
> permutation 94.4% bind to the wrong element with 0% refusals.**

**0% refusals is the number that mattered**, not 94.4%: there was no signal of
any kind. The live shape is a flow that clicks Delete on the first invoice row,
replayed after the sort flips — it deletes a different invoice and **reports
PASSED**, because "one fewer row" still holds.

**The fix is a witness**: the five identity fields the descriptor ignores, plus
an *anchor* of the nearest preceding non-crowd controls, recorded only where it
is unique at record time. Result on the live re-sort shape:

| | n | CORRECT | REFUSED | WRONG |
|---|---|---|---|---|
| **resort, witnessed** | 212 | **94.3%** | 5.7% | **0.0%** |
| resort, unwitnessed | 346 | 5.8% | 0.0% | 94.2% |

Refusal cost on the six pre-existing mutations: **+0.2pp**.

**Geometry was the best witness at 87.3% coverage and is deliberately not
used.** It is excluded from identity because it drifts (110px in #23, 1,097px in
#25), so a witness built on it would refuse on every reflow and lazy image — a
safeguard that fires on innocent change is noise wearing a safety label.

**The residue: 59.4% of ordinal-bearing descriptors have nothing to witness
them** — crowds identical in every declared field *and* in their surroundings.
Those are no worse than before and no better, and the recorder now says so at
record time. Refusing them was rejected: it would pause ~14% of all descriptors
on an *unchanged* page, which is not a safety cost but losing the feature.
**Flows already on disk carry no witness and are protected only once
re-recorded.**

## 6. Also closed in #72

| | |
|---|---|
| resume bound the **first** target rather than the one that failed, could never get past the step, and proposed a patch rewriting the Email descriptor to a password box — eight times per resume | fixed; `Unresolved` carries the path |
| `text` compared with `in`, so `Approved` passed against `Not Approved` | whitespace-normalised equality — and the old `in` did not deliver the tolerance it was justified by either |
| an ineffective click passed on a step with no assertion (23% of steps) | `NO EFFECT:` token, fatal only where nothing else can catch it |
| unknown keys in `expect` asserted nothing, silently | validated at load, from both `Step` and `Flow` |
| `settle_ms` widened the assertion window but not the target window | one line |
| **`require` had never once fired** — `{}` in all 19 flows | derived from before the first *non-navigational* action; proven firing live, both directions |
| `Step.note`, `descriptor["untargetable"]`, and the three review markers were all half-contracts | wired or persisted; `--check-only` now prints the review lines, so CI sees them |

## 7. Still open

See `FLOWS-FAILURE-SURFACE.md` for the systematic version: every way this can
break, by the stage it breaks at, with evidence and status for each. What
follows is the short list.

- `query_elements` has no visibility filter — one `display:none` on the app root
  hides everything and **every count assertion still passes**. 29% of assertions
  in the repo's own flows are a bare count. `OPEN.md` Tier 1.
- an absence assertion is satisfied by a blank page, and the settle window
  points the wrong way for it.
- the unwitnessed 59.4% above.

## 8. Historical — the state before #72

A nine-finding audit reproduced defects not covered by the 28 already fixed in
`tools/bench_flows/`. The headline is a hole in the feature's own safety
measurement:

> `audit_flow_resolve.py` published *"2,726 descriptors, 100% CORRECT, 0% WRONG
> on every mutation"* across six mutations — and **none of them is a reorder.**
> A re-sorted list leaves the crowd's composition identical and only the order
> different, which is the one change an ordinal cannot survive. Measured with a
> reorder arm: of 1,119 controls, **299 (26.7%) carry an ordinal, and under a
> permutation 94% bind to the wrong element with 0% refusals.**
>
> A flow that clicks Delete on the first invoice row, replayed after the default
> sort flips, deletes a different invoice **and reports PASSED**, because "one
> fewer row" still holds.

The others, all reproduced, all tracked in `OPEN.md`:

| | |
|---|---|
| `query_elements` has no visibility filter — one `display:none` on the app root hides everything and **every count assertion still passes**. 29% of assertions in the repo's own flows are a bare count | Tier 1 |
| an absence assertion is satisfied by a blank page, and the settle window points the wrong way for it (a presence check gets stronger as a page settles; an absence check gets weaker) | Tier 1 |
| resume binds the **first** target rather than the one that failed, can never get past the step, and proposes a patch that rewrites the Email descriptor to a password box | Tier 2 |
| `text` compared with `in`, so `Approved` passes against `Not Approved` | Tier 1 |
| 23% of recorded steps carry no assertion, and "click had NO detectable effect" is deliberately not a refusal token | Tier 1 |
| `settle_ms` widens the **assertion** window but not the **target** window, on exactly the slow SPAs it was measured for | Tier 2 |
| `require` has never once fired — `{}` in all 19 flows, because `MUTATES` contains the `tabs_create_mcp` every agent is taught to open with | Tier 2 |

## 9. What this is not

It is **not** a claim that a recorded flow cannot break. It can, and §5 is how.
The defensible claim is narrower and stronger:

> Every way it breaks is named, measured, and pinned by a check that fails
> against the pre-fix code.

Also genuinely absent, and each is a deliberate call rather than an oversight:
no headless CI runner beyond `run_flows.py`; no failure artefact (a screenshot
and the final listing on failure would cost one call on a path that is already
failing); no machine-readable report; no uncaught-page-exception check, which
Cypress has by default; no conditional/optional step, written down in #62 with
the exact condition that would justify building it. Retry-until-pass **conflicts
with the design** and will not be built — a runner that passes on attempt three
is a runner that hides a real failure.
