# Sufficiency — is what survived *enough*?

`OPEN.md` item 12, and the gap `MEASUREMENT.md` §2 names:

> Every ruler we have measures **presence**. `lost_identities = 0` says nothing
> a user can see went missing; it does not say what remains is **enough**.

This file states exactly what `tools/measure_sufficiency.py` answers, what it
cannot answer, and why the operationalisation is honest rather than convenient.
Read `PRINCIPLES.md` §8–§11 first; every design choice below is one of those
rules applied.

---

## 1. The question

> At a step where a human had to act on a specific element, does the listing we
> hand the agent **determine which element that is**?

Two independent ways to fail, and only the first is measured today:

| failure | ruler | status |
|---|---|---|
| the element has no row at all | `bench_mind2web` (structured), `bench_trajectory` (listing) | measured — ~96% / 51.4% |
| the element has a row, and so do N look-alikes that print **identically** | — | **this file** |

The second is a sufficiency failure that presence cannot see. The listing is
complete, nothing was lost, every identity survived — and the agent still cannot
say which `ref` to pass without spending another tool call or guessing 1/N.

**Metric: Decision Sufficiency (DS).** Per labelled action, one of:

- `ABSENT` — the target is not in the listing. (Presence failure; reported so
  the two rulers can be reconciled, not as a new finding.)
- `AMBIGUOUS` — present, and at least one other listed element prints the same
  thing in the same place.
- `DECIDABLE` — present and uniquely described.

`DS = DECIDABLE / scored`. **`DS | reachable = DECIDABLE / (DECIDABLE +
AMBIGUOUS)`** is the number that isolates the new signal from the presence
number already published, and is the one to quote.

## 2. Why this is the MFS shape and not a gesture at it

`arXiv:2605.29397` defines the Minimal Failure Set as the smallest set of
elements whose removal causes task failure, and coverage as the fraction of
instances where a reduction fully retains it. Their MFS is derived from **one
agent's self-reported elements and that agent's failures** (n = 59 and 42), so
it measures "what that policy needed".

We hold no LLM key and run no policy, so we cannot reproduce their ground truth
and do not pretend to. What we can compute is the **policy-independent part of
the MFS**:

1. the target element is in the MFS by construction — removing it makes the
   labelled action impossible;
2. whatever distinguishes the target from its look-alikes is in the MFS too —
   remove it and *no* policy reading only the representation can choose
   correctly. That part is a property of the representation, not of the agent.

DS measures (2) while holding (1) fixed. `MEASUREMENT.md` §2 said to port the
metric **shape** rather than wait for labels that cost ~2,700 model inferences;
this is that port, and the field ablation in §5 is their Table 3 computed
against our own representation instead of against generic HTML tag names.

## 3. What it cannot answer

Stated before the number, because a sufficiency metric that is quoted as a
success rate is worse than no metric.

- **DS is necessary, not sufficient.** `DECIDABLE` means the listing *permits* a
  correct choice. It does not mean a model makes one. A model with the perfect
  listing still fails tasks.
- **`AMBIGUOUS` is not failure.** The agent can guess (1/N), or escalate with
  `query_elements`/`search_page`/a scoped read and succeed. The honest cost of an
  ambiguous step is **one model turn — ~3.6s, 92–97% of a tool call** (#38), and
  that is also why this is worth measuring at all: PRINCIPLES §18 says the lever
  is turns.
- **It cannot price prose.** The paper's single largest finding is that **Text**
  dominates the MFS (30.5 / 59.5 coverage drop). Our listing is a listing of
  *controls*; prose and table data live behind `get_page_text`, `search_page`
  and `query_elements`. DS says nothing about whether those tools carry what a
  task needs. That is a separate, unbuilt measurement, and it is the larger of
  the two halves.
- **It is an upper bound on decidability, in three places.** The identity is
  built from the tree's printed row **plus its printed ancestors**, i.e. we
  credit the agent with reading the whole path. Folded members are credited with
  their per-member label. And a `DECIDABLE` key may still be one the task's own
  wording cannot name.
- **It does not know what the task said.** A row can be unique and still be the
  wrong one to pick. Matching the task's wording to the row is semantic
  inference, which #20 measured `find` at **0%** on and is not retrieval.

## 4. The three things that keep it from being circular

**(a) The ground truth is external.** Which element matters comes from a human
label in Mind2Web, on 16 sites nobody here has tuned against. The collector does
not get a vote on which step counts.

**(b) The identity excludes `ref` and geometry.** This is the whole defence, and
it is not arbitrary. A `ref` is per-document and is the *answer* the agent is
trying to produce, so keying on it makes every row unique and DS 100% by
construction — that is the negative control in §6. Geometry is excluded for the
reason the flow descriptor ladder excludes it: it drifts (110px in #23, 1,097px
in #25), so an identity built on it would be unique and worthless.

**(c) The metric is gameable, and the ablation is the audit.** Printing any
per-element noise — a hash, a coordinate, a `data-testid` — would raise DS
without helping anyone. So the field ablation in §5 reports *which* class of
printed field carries the discrimination. A field that is unique-but-unnameable
shows up there as carrying everything, which is a result to distrust, not to
celebrate. **A rising DS with no field carrying it is a defect, not a win.**

What this is **not** is a claim that the collector agrees with itself: the
collector cannot make two identical buttons distinct by fiat. It has to find a
difference the page declared.

## 5. The field ablation (their Table 3, our fields)

Within one arm and one page load, a class of printed field is removed from the
identity and DS re-measured. The drop is that class's MFS membership frequency.
Classes: `identity` (the accessible name, in **both** the forms the listing
prints it — a bare quoted string and `name="…"`), `near=`, `value=`/
`placeholder=`, `href=`/`src=`, `options=`/`count=`/constraints, tag/role/type/
`section=`, state flags, and the tree `ancestry` path.

A class whose ablation changes **zero** rows is reported `n/a`, never as a drop
of 0.0: a detector that cannot fire is not a field that carries nothing
(PRINCIPLES §15). That is what happens to `href`/`src` here — see §7.

Two arms exist to be compared against, not just reported:

- **`label+near`** is the *shape* of `audit_dom_quality.py`'s existing
  `ambiguous` key (label plus the `near=`/`under=` breadcrumb, no ancestry). It
  is not byte-identical — that key reads the entry's `label` field, this one
  reads what was printed — so treat it as "how much does the narrower key
  lose", not as a reimplementation. That metric has always been **corpus-wide
  density, not task weighted** — the #44 lesson exactly: a rate without its
  benefit cannot tell ambiguity on the button a task needs from ambiguity in a
  footer nobody opens. DS is that question with the task weighting it never had.
- **`+ref`** and **`empty`** are the two negative controls of §6.

## 6. Controls, because a metric with no falsifier is decoration

| control | expectation | what its failure would mean |
|---|---|---|
| `+ref` in the key | DS = 100% | the parser is losing refs |
| `empty` key | DS ≈ 0% | collisions are not being detected at all |
| same arm twice, one page load | Δ = 0 | the collector is not deterministic across calls |
| whole probe re-run | Δ = 0 | the harness carries state |
| `reachable` vs `bench_trajectory.listing_refs` | identical | a new ruler that disagrees with the old one about the **old** question is broken, not insightful |

**Measured, and one prediction of mine was wrong.** I expected the novelty flag
(#31) to make arm order matter: it is monotonic per tab, so a collector call
made twice in one page load should print `(just appeared)` the first time and
not the second. It does not happen here, because the probe's first call on every
page is the structured `full` collection that resolves the target, and that call
absorbs the novelty for every arm after it. The control arm is **byte-identical
to the primary on all 173 actions** — same chars, same slots, same verdict — so
the collector is deterministic across repeated calls on one page load. Rotation
is kept anyway: a confound that did not fire on this corpus is not a confound
that cannot fire, and `(just appeared)` is still stripped from the identity
because it is transient and no task can name it.

| control | result |
|---|---|
| `+ref` in the key | **1.000** — OK |
| `empty` key | **0.000** — OK |
| same arm twice, one page load | **0.00pp, 173/173 per-action agreement** |
| whole probe re-run (3 separate processes) | identical: 83 / 6 / 84 each time |
| parser vs `bench_trajectory.listing_refs` | **78,990 / 78,990 = 100.0%** |

That last one failed first, at 95.7%, and the failure was in the **flattering**
direction — the parser was skipping the off-viewport note, which carries the
region index (`footer(ref_471): 12, main(ref_51): 11`), and a slot that is never
built cannot collide with anything. Fixed by parsing the note's comma-chunks as
slots of their own.

## 6b. Whose ambiguity is it?

A collision where every rival is **the same link four times** — a responsive nav
duplicated in markup — costs nothing: clicking any of them does the job. A
collision between four different vans is a wrong answer. DS cannot tell them
apart on its own, so each AMBIGUOUS target is diagnosed against the DOM's own
**declared attributes**, independently of the collector:

- **`ours`** — the page declares a difference our listing does not print. The
  only actionable class.
- **`inert-here`** — only `aria_label` differs, which on this corpus is not an
  ARIA attribute at all (§7).
- **`class-only`** — only `class` differs; the source paper prices class at
  7–10% and the locator literature down-weights it.
- **`page`** — nothing declared separates them. No representation could.

The comparison is an **allowlist** of what a page author declares, not a
blacklist of dataset noise. The first version compared every attribute and
reported **6 of 6** collisions as our gap — because Mind2Web's capture harness
writes `data_pw_testid_buckeye` (pw = playwright, buckeye = the dataset's
university) into all 16 unrelated sites, along with `is_clickable`,
`input_value`, `option_selected` and `text_value`. A damning number, and wrong.
A blacklist of those names would also go stale the way `_OBSERVES` did three
times in one day (#42), so the rule enumerates the declarations instead.

Two further corrections went the *flattering* way and were each verified element
by element before being accepted (#16): raw `textContent` and a one-level `alt`
lookup both reported `<a><img alt="Find a Theatre"></a>` vs
`<a>Find a Theatre</a>` as a declared difference, when the page declares the
**same name** twice and the listing prints it correctly. Getting that right
means descending the way AccName does, which is a second naming implementation
(PRINCIPLES §17). Whether our AccName agrees with the page is a real question
and it belongs to `accessible_names` (#33/#34 measured it at 49/54 against
Chrome's own), not here.

## 7. Corpora, and what each cannot support

| | Mind2Web (186 actions, 22 trajectories, 16 sites) | frozen corpus (106 real pages) |
|---|---|---|
| gives | human-labelled targets → **task weighting** | real CSS, real scripts, real styling |
| cannot give | real styling: no scripts and no CSS, so two of eight admitting signals are structurally off (#73) and unstyled pages run tall, pushing far more below the fold than on a real page | **any task label** — so density only, never DS |
| drift | deterministic `set_content`; measured, see §6 | real replay instability; 18 sites named non-deterministic (#16) |

Neither corpus can carry the claim alone, and **the frozen half cannot produce a
DS number at all** — it has no labels, so it reports the *density* of
indistinguishable rows and nothing about whether that density lands where it
matters. Saying so is the point: R2 (an ablation measures the code against the
sample) applies to this probe as much as to any other, and the sample that would
settle it — labelled targets on styled pages — does not exist in this repo.

### Three more things Mind2Web structurally cannot show, measured here

#73 names two signals that are switched off by the corpus (`listener_tagged`
0/173, `cursor_pointer` 0/173). Building this probe found three more, each
verified three ways — in the raw `html`, in `cleaned_html`, and in the
**rendered DOM**:

| | measured | consequence |
|---|---|---|
| `href` | **0** of 61,709 `<a>` | `detail="brief"`/`"full"` are a **near no-op** here: href/src printed **0 times across 173 listings**. The `url` field ablation cannot fire and is reported `n/a`, never `0.0`. |
| `src` | **0** of 6,454 `<img>` | same |
| `aria-label` | **17,272 `aria_label`** vs **1** hyphenated attribute in the whole corpus | the dataset rewrites hyphenated ARIA attributes to underscores. `aria_label` is not `aria-label` and carries no ARIA meaning, so **AccName step 2C is dead on this corpus for every implementation, ours and Chrome's alike.** Every name measured here comes from content, `title` or `alt` only. (`role=` survives — 42,195 occurrences — because it has no hyphen.) |

None of this invalidates the existing out-of-sample recall number; it sharpens
#73's "structural floor" argument. It does mean **no comparison of our `detail`
ladder taken on Mind2Web means anything**, which is a trap worth naming before
someone runs one.

## 8. The baseline

`python tools/measure_sufficiency.py --controls --baseline`, 173 scored actions
(13 excluded as `target_not_in_html` — #73 showed that exclusion is a
serialization defect, not absence), 22 trajectories, 16 untuned sites, ~78s.

### The number

| | |
|---|---|
| **`DS \| reachable`** | **83 / 89 = 0.933** |
| leave-one-site-out | **0.921 – 0.951** (16 folds — quote the range) |
| `DS` over all scored | 0.480 (the other 84 are `ABSENT`, i.e. the presence number) |
| per operation | CLICK 66/72 · SELECT 8/8 · TYPE 9/9 |

**Read it as: when the target is on the page we handed over, the listing
distinguishes it 93% of the time.** It does not say an agent succeeds 93% of the
time, and 6 ambiguous steps on 16 sites is a small number to carry a decimal.

### The two cross-checks that license quoting it

| this probe | established ruler | |
|---|---|---|
| `recall_structured` **166/173 = 96.0%** | `bench_mind2web` **96.0%** (#73: 166/173) | exact |
| first-read reachability **89/173 = 51.4%** | `bench_trajectory` **51.4%** (#28, #44) | exact |

The on-disk `trajectory_baseline.json` says 50.9% — that file predates #28 and
#28 itself records the move to 51.4%. The agreement is with the published
figure, not with the stale artefact.

### The field ablation — their Table 3, our fields

| ablated | `DS \| reach` | drop | rows changed |
|---|---|---|---|
| *(none)* | 0.933 | — | — |
| **identity** (the accessible name, both printed forms) | **0.416** | **51.7pp** | 10,757 / 15,828 |
| **ancestry** (the tree path) | **0.820** | **11.2pp** | 12,301 |
| **value / placeholder** | 0.876 | 5.6pp | 855 |
| near | 0.921 | 1.1pp | 456 |
| options / count / constraints | 0.933 | 0.0 | 179 |
| tag / role / type / section | 0.933 | 0.0 | 4,397 |
| state flags | 0.933 | 0.0 | 3,969 |
| href / src | **n/a** | **n/a** | **0 — not printed on this corpus** |
| `label+near` (everything else removed) | 0.506 | 42.7pp | 15,828 |

The accessible name carries most of it, which agrees with the source paper's
finding that **Text** dominates. The second-largest contributor is the **tree's
structural path** — the thing #27 shipped on a null A/B result because no metric
there could read it. This is a number for it, on a sufficiency axis, out of
sample. The two rows are not additive (51.7 + 42.7 > 93.3): fields substitute
for one another, which is what makes removing any single one survivable.

**The identity row was 38.2pp in the first run and that was my ruler being
wrong.** The listing prints the identity two ways — a bare quoted string after
the tag (`button "Update search"`, 47 of 173 target rows) and `name="…"`
(`select name="type"`, 17 of 173) — and the ablation removed only the first, so
it meant different things on different row shapes. Found by reading real rows,
not by reading the regex.

`label+near` is the shape of `audit_dom_quality.py`'s existing `ambiguous` key.
Losing 42.7pp against the full printed row is the measured answer to "is that
metric the same thing as this one": no.

The arm table (`tree-compact` 0.933 vs `flat-compact` 0.910) is **not** a
result — it is a 2-step difference on n=89, well inside what this sample can
resolve. Directionally consistent with the ancestry row; nothing more.

### Density is not sufficiency, and here is the factor

On the same corpus, in the same run: **27.6%** of on-screen rows share a printed
identity with another row, while only **6.7%** of the rows a *human actually
needed* were ambiguous. A roughly 4× gap, and it is the whole argument for task
weighting — `audit_dom_quality.py`'s `ambiguous` rate has always been the first
number and has never been the second. Most repetition is unnamed icons, bare
`svg` and generic containers that nobody targets. #44's lesson, one axis over.

Measured with it, and against my own prediction: `(below-fold)` rows that *are*
listed are **less** repetitive (10.9%) than on-screen ones, so conditioning on
reachability does not obviously flatter the headline. That proxy cannot see the
84 targets that were never printed at all, so the selection effect is bounded,
not eliminated.

### The frozen corpus — density on real styled pages, no DS

24 sites with a non-empty replay (1 skipped on a `goto` timeout, 5 replayed
EMPTY — `amazon`, `amazon_de`, `antd`, `booking`, `aggrid` — named by the probe
rather than quietly dropped from the denominator, because a count is not an
inventory). Median **7.0%** of rows share a printed identity, mean 13.9%, worst
**68.9%** (yahoo_jp, then hn 49.1%, vuetify 39.5%, gh_issues 38.0%).

**Drift floor, two independent two-replicate runs: 0.76pp then 0.00pp**, median
0.00pp both times, the 0.76pp from one site (gflights) once and not on the
repeat. So the floor is ≤0.76pp and usually zero — which is also why it gets
measured twice rather than declared after one clean run.

`flat-compact` sits at median 5.5% / mean 15.3% / worst 71.3%. It is **not** the
same question as the tree: flat prints `section=` (which the tree strips, #23)
while the tree prints an ancestry path, so the two formats carry different
discriminators and the medians cross over per site (`ng_material` 21.7% tree vs
50.0% flat; `headlessui` 11.0% vs 0.0% the other way).

**No DS number can come from here** — there are no labels — and the Mind2Web
half says the task-weighted figure is several times lower than the density
figure, so do not read 7.0% as a failure rate.

## 9. What would make this a real MFS

In increasing order of cost:

1. **Mind2Web's `operation.value`.** `fetch_mind2web.py` flattened `operation`
   to its op name, so for the 19 TYPE and 13 SELECT actions we know *that* a
   value was entered and not *which*. With it, "does the listing carry the option
   the human chose" becomes measurable — a direct test of #31's `options=`.
   Costs a re-fetch, and that re-fetch is already owed for `OPEN.md` item 10.
2. **Labelled targets on styled pages.** The whole corpus split above exists
   because no such dataset is here. `tools/bench_turns/` produces live
   trajectories; labelling the element at each step would give one.
3. **An agent in the loop.** The paper's actual MFS. Out of scope for this
   repo's architecture, and the reason the policy-independent part is what is
   measured instead.
