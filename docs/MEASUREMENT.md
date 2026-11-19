# Measurement — the rulers, and how each one has lied

**Read this before you quote a number.** Every figure this project publishes
came from one of the instruments below, and almost every one of them has at some
point produced a confident wrong answer. The failures are listed with the
instruments, because that is the only form in which the warning is useful.

History: CLAUDE.md #16, #19, #25, #26, #44, #45, #48.

---

## 1. The four rules

**R1. A result that flatters or damns the system gets re-derived before it is
believed.** Damning results get believed too readily — two live agents agreeing
with each other is correlated error, not evidence. (PRINCIPLES §8.)

**R2. An ablation measures the code against the sample. It cannot measure the
sample.** (PRINCIPLES §9.)

**R3. Interleave, rotate, and take a drift control first.** Block-structured A/B
aligns run-order drift exactly with variant order; it once produced three
"CLIFF" verdicts that were artefacts and were not even monotonic. Measure every
variant on the same page load, rotate the order per site, and establish the
noise floor by measuring **the same arm twice** before attributing anything.

**R4. Measure cost and benefit in the same pass.** A cost without its benefit
cannot tell a targeted rule from an indiscriminate one — off-viewport admission
looked Pareto-positive at +1.1% chars and turned out to be +18.7% tokens for
+6.9pp with **70% of the spend on tasks that gained nothing**.

---

## 2. The instruments

| Ruler | Scores | Can see | **Cannot see** |
|---|---|---|---|
| `bench_mind2web.py` | target recall on 173 human-labelled actions, 16 untuned sites | whether the element could be reached | whether the agent would use it; prose; anything about turns |
| `bench_trajectory.py` | observation cost across 22 labelled trajectories | the reads a representation forces | a representation *misleading* the agent — it assumes the gold path, so it is a **lower bound** |
| `measure_retention.py` | presence / answerability / findability vs tokens on the frozen corpus | regression | generalisation — all 106 sites informed development |
| `bench_headtohead.py` | three representations, one metric definition, same actions | the size/recall trade exactly | end-to-end task success |
| `audit_dom_quality.py`, `audit_ablation.py` | recall / ambiguity / payload, and what one signature is worth | whether a rule carries anything **on this corpus** | whether the corpus contains the shape the rule exists for (R2) |
| `audit_descriptors.py`, `audit_flow_resolve.py` | locator uniqueness and survival under mutation | mis-binds under the mutations it models | **any mutation it does not model** — see §4 |
| `tools/bench_turns/` | live head-to-head, turns, pre-registered | what a real agent costs | anything below the ~47s/task wall-clock drift floor |
| `inspect_site.py` | `lost_identities` — a visible control named nowhere | identity loss | sufficiency: whether what survived is *enough* |
| `audit_name_correctness.py` | our derived accessible name against **Chrome's own** `Accessibility.getFullAXTree`, at first paint and after up to four declared interactions | whether the name we print is the name the browser computes — the only independent oracle in the repo, since every other ruler scores the collector against our own tools | whether a name BOTH derivations get wrong is wrong; the 20,691 rows Chrome ignores and the 11,753 with no AX node; anything behind a consent wall |
| `measure_sufficiency.py` | **decision sufficiency** — is the human-labelled target *distinguishable* among the rows we printed, and which printed field carries the discrimination | a listing that is complete and still does not determine the action | whether an agent succeeds; anything about **prose**, which the source paper measures as the largest contributor; the 84 targets that were never printed |

### The one that is missing — half built

`measure_sufficiency.py` ports the metric **shape** (see `SUFFICIENCY.md`) for
CONTROLS: **`DS | reachable` = 0.933** on 89 reachable Mind2Web targets, LOSO
0.921–0.951, with the accessible name worth 38.2pp and the tree's ancestry path
worth 11.2pp. It also measures why density is not sufficiency: **27.6%** of
on-screen rows share a printed identity against **6.7%** of the rows a human
actually needed.

**The larger half is still missing**, and it is the half the paper says matters
most: TEXT. Our listing is a listing of controls, so prose and table data reach
the agent only through `get_page_text`, `search_page` and `query_elements`, and
nothing measures whether those carry what a task needs.

### The original note

**Minimal Failure Set / coverage** — `arXiv:2605.29397`, 28 May 2026. MFS is the
smallest set of elements whose removal causes task failure; coverage is the
fraction of instances where a reduction fully retains it. It needs **no web
access and no model inference** to evaluate, and gives a ~290× speedup over
end-to-end evaluation (232 cumulative hours → 48 minutes across 32
configurations).

**Every ruler we have measures PRESENCE. MFS measures SUFFICIENCY**, which is the
question `lost_identities = 0` cannot answer: it says nothing a user can see went
missing, not that what remains is enough to finish the task.

Their Table 3 — coverage drop when one element type is ablated — is immediately
usable and uncomfortable:

| | WorkArena | WebLinx |
|---|---|---|
| **Text** | **30.5** | **59.5** |
| select / `a` | 13.6 | 7.1 |
| span / input | 8.5 | 5.1 |
| button / div | 4.8 | 4.8 |
| attr `value` | 22.0 | 7.1 |
| attr `id` | 16.9 | — |
| attr `href` | — | **16.7** |
| attr `class` | 10.2 | 7.1 |

**Text dominates by a wide margin**, and our listing is a listing of *controls* —
prose and table data are reachable only through `get_page_text`, `search_page`
and `query_elements`. That is the strongest external evidence that #14's scoped
text and #26's table rendering were load-bearing rather than conveniences, and
an argument for making text reachability a first-class measurement rather than a
fallback. `href` at 16.7% independently validates `detail="brief"`; `class` at
7–10% agrees with the locator literature down-weighting it.

**Caveat, which is large:** their ground truth derives from ONE agent's
self-reported elements and that agent's failures, so it measures "what this
policy needed", not "what a correct answer requires". n = 59 and 42. Port the
metric **shape** — sufficiency, coverage against reduction ratio — rather than
waiting to import labels that cost ~2,700 model inferences to build.

---

## 3. How these instruments have lied
| `detail="full"` scores **0.5806** against `compact`'s 1.0000 on tab rows, i.e. *"full's media rows crowd the controls out"* | `find` reads its bridge from a **module global**, so with sites measured concurrently one site's query was scored against another site's entries. The result was coherent and carried a mechanism, which is what made it dangerous. Re-derived on a single page both arms matched every time; properly measured they are **identical, 3,059/3,059, twice**. A scoring lock and a `bridge_race` counter now exist, and it reads 0. |

Each of these produced a clean, plausible, wrong number.

| The lie | The cause |
|---|---|
| 89.4% recall | the benchmark walked only to the **nearest** mmid-bearing ancestor, scoring as misses the cases where clicking the wrapping `<button>` succeeds. Fixing the **ruler** gave 93.6%. |
| "a rule started deleting again", 6 sites | the harness **restated** the tripwire's permitted-set instead of reading it, and had drifted |
| 3.81% identity loss | a bare `checkVisibility()` checks layout only. With `{opacityProperty, visibilityProperty}` the same probe reports **0.00%** |
| 13.9% descriptor mis-binds | ground truth was `(tag,x,y,w,h)` and the second pass laid out 521px lower. Geometry was chosen *because* descriptors exclude it — and the reason they exclude it is that it drifts |
| 43.6% of turns were "ceremony" | **the author's own prompt mandated the behaviour being measured** |
| 538 unexplained misses incl. GitHub's whole top nav | the probe compared **element** identity where the listing carries **concept** identity under a collapsed sibling's ref |
| +0 on all 26 sites, including a `<select>` demo | a `^ref_` anchor matched nothing, because tree rows are **indented** |
| 78.7% marker cost | numerator from the whole-page **structured** set, denominator from the viewport-scoped **string** listing |
| 36/38 correct, wrong on **both** arms | a transcription error in the answer key. A falsifier firing identically on both arms is a broken ruler, not a broken system |
| markers inflated by repeated content | the cap detector counted **occurrences**; one genuine 99-char label repeated 39 times is a textbook cap signature for a value that is not cut at all. It counts **distinct values** now |
| "a revealed control is named far worse", 0.6215 vs 0.7370 | the NEW population is keyed on the identity STRING (mmids are additive), and an unnamed row's identity is `""`, which is never in the seen set — so **every `(unlabeled)` row counted as revealed-by-the-interaction and none as carried**, and a defect class concentrated itself in one arm by construction. Corrected: 0.6628 against 0.7370, most of which is composition rather than wrong names — and a smaller run with the fix built in reverses the sign, so the effect is not established either way |
| "the name fix is a wash: 80 improved, 83 regressed" | all 83 "regressions" are rows where Chrome's role permits **no name at all** and ours now prints the element's TEXT — the `chrome-empty` population #74 requires us to keep printing. Split on whether Chrome has a name: **80/80 improvements real, 0 correct names broken** |
| 1.65x tree token cost | `format` was never passed, so **every corpus token figure ever produced described the FLAT listing** — and the table divided two medians drawn from different sites. The real per-site figure is **1.09×** |
| the climb record costs **+1,530ms** on one page | a tight loop reimplementing the rule over `__mmidReg`, which is the right POPULATION and not the right WORK: the real collector does far more per element, so the relative delta shrinks, and its own A/A floor is 24.3ms median. Timed against `_collectInteractivePage` ITSELF in three interleaved arms the worst case is **+432ms** and the median is **+0.0ms**. The direction survived; the magnitude was 3.5x out |
| every drop arm refuses, for every record definition | the probe's per-member cell function nulled the WHOLE crowd when any member's node was gone, so the resolver saw no atoms anywhere and could not take the content branch **by construction**. The collector's own `recordAtoms` was intact for the survivors the whole time. A 100% REFUSED column that agrees across every arm is the signature of a disabled branch, not of a safe one |
| `audit_flow_resolve.py` says a content witness survives a re-sort | its mutations permute a PYTHON LIST of entries, and `recordAtoms` is a field ON an entry — so the witness travels with the logical element and the atoms branch is CORRECT for free. Measured: both `reorder` and `resort` returned CORRECT with the field present and WRONG with it absent. Fixing the scaffold-fixed arm to leave the record at its POSITION moved its witnessed CORRECT rate 48.8% -> 9.8%. **39 points of that arm's score was the harness handing over the answer** |

Seventeen measurement bugs — the count is the rows of the table above, which is
the only place it can be read from (PRINCIPLES 16). Twelve were found by
re-deriving a number that looked too clean or too damning; two by a falsifier
firing where it should not. **None was found by reading the code.**

---

## 4. The failure mode that applies to a ruler itself

A mutation harness measures the code against **the mutations it models**, which
is R2 pointed at a safety claim rather than at a corpus.

`audit_flow_resolve.py` published *"2,726 descriptors, 100% CORRECT, 0% WRONG on
every mutation"* across six mutations: rename-target, counter-in-name,
delete-target, insert-twin, twin-elsewhere, rename-neighbour. **None of them is
a reorder** — and a re-sorted list is the one change an ordinal cannot survive,
because the crowd's composition is identical and only the order differs.

Measured with a reorder arm added: of 1,119 sampled controls, 299 (26.7%) carry
an ordinal, and under a permutation **94% bind to the wrong element with 0%
refusals.** The published headline was true of the mutation set and the mutation
set excluded the case.

> **When a harness reports a perfect score, the next question is what it does
> not model.** A perfect score is weak evidence about the world and strong
> evidence about the harness.

---

## 5. Where the numbers are allowed to come from

- **Out-of-sample** — Mind2Web only. The frozen corpus's `--holdout` splits by
  name hash, but all 106 sites informed development, so that column measures
  site-to-site variance and **must not be quoted as generalisation**.
- **Live** — `tools/bench_turns/`, pre-registered with the bar fixed **before**
  any data exists. 9/10 was declared once and then honoured when the result came
  in at 8/10. Wall clock below ~47s/task is noise.
- **Frozen corpus** — regression only. 18 of 106 sites replay
  non-deterministically and are named; do not assert exact-match invariants on
  them.
- **A live pass** — required before committing a batch of fixes. #42 shipped 15
  fixtured fixes with no live pass and produced seven regressions.

Reproducibility is not optional: six live head-to-heads were reported before
`tools/bench_turns/` existed, every one of them in a session scratchpad under
`/tmp`, and all six are now unreproducible. **A result nobody can re-derive is
an anecdote with a p-value.**

---

## 6. Known debts in our own numbers

- **The Mind2Web 173 WERE audited (#73) and the headline stands**, reproduced
  three ways with zero label defects across 186 actions. Two corrections came
  out of it: the Online-Mind2Web staleness criticism **does not reach us** (the
  benchmark never navigates, and 0 of 186 snapshots contain a script, link or
  style tag, so the page and its label come from one frozen record); and the
  number should be quoted as **~96% / 95–96%**, never as a point estimate —
  173 actions come from 22 trajectories, one widget is 17% of the sample, and
  leave-one-site-out spans 95.1%–98.1%.
  Still open upstream: `fetch_mind2web.py` keeps only `pos_candidates[0]`, and
  the original shards were not retained, so **whether that is the right
  positive is the largest unaudited choice** and it sits under everything else.
- **There is no successor dataset.** Mind2Web-Live ignores element changes;
  Online-Mind2Web is binary per-trajectory; Mind2Web 2 scores only a final
  answer. The 2023 release is the only family member with a per-step element
  label. **The conclusion once drawn from that -- that our out-of-sample number
  "will not be independently corroborated by anything newer" -- is withdrawn.**
  It was a claim about the Mind2Web family being read as a claim about the
  field. ComponentBench (2026) carries per-step element ground truth, verified
  by hand in `tools/audit_componentbench.py` against an episode pack no paper
  mentions: 7,773 steps with tag / id / testid / role / name / bbox, and the
  step VALUE on every `type` step. Whether it can SERVE as a corroborating
  ruler is a different and open question -- its traces were recorded in a
  different render mode at viewports the harness does not use, so a ruler must
  re-resolve each target by identity, and the rate at which that resolves
  UNIQUELY on a live production page is unmeasured. Plausible and unproven;
  `docs/research/COMPONENTBENCH-VERIFICATION-2026-11.md` section 7.
- **No task-success measurement exists for our own ladder.** `detail` and
  `format` are priced on recall and tokens, never on end-to-end success with a
  strong model. Two 2026 results disagree about which way that cuts (one
  measures +14.6 to +17.5pp for full HTML over a compact tree, another −10.2pp),
  so it is unsettled rather than alarming — and unmeasured here either way.

## An A/B probe that patches a source anchor has a LIFETIME

`audit_retext_tier.py` and `audit_retext_prevalence.py` build their two arms by
string-patching an anchor in `extension/listener_tag.js`, and they `assert` the
anchor occurs exactly once so they cannot silently measure a build nobody runs.
That assertion is right and it is why the adversarial auditor's #82 numbers
could not have drifted.

**It also means both probes stop working the moment the fix ships.** Verified
2026-11-18, minutes after the re-text diff landed:

    AssertionError: anchor drifted: "kd[s] = r.type === 'childList' ? 1 : (r."

So the corpus figure they produced (27.6% of in-window childList records are
re-texts, 105 frozen sites) is **not re-derivable from the repo as it now
stands** without first reverting the patch. Nothing is wrong with the number;
what is wrong is that the instrument has no way back to its own baseline.

**The rule this earns.** A probe whose arms come from patching source must
construct the arm that does NOT exist yet, not the one that does. Patch
FORWARD from the shipped state (apply the candidate) rather than patching the
candidate onto a baseline it assumes is still there — or carry both anchors and
detect which side of the fix it is on, so it keeps working in either direction.
Otherwise every such measurement is a one-shot that expires on commit, and the
next reader who wants to re-derive it (PRINCIPLES 5: a result that flatters or
damns the system gets re-derived before it is believed) finds an assertion
instead of a number.

**What was confirmed independently instead**, since the probe could not be
re-run: a plain load of the fixture's login page reports `18 structural, 14
text` live, a split that did not exist before the fix. That is the same
direction and the same rough magnitude as the corpus figure, measured through
the real extension rather than through the probe.
