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

Two independent ways to fail:

| failure | ruler | status |
|---|---|---|
| the element has no row at all | `bench_mind2web` (structured), `bench_trajectory` (listing) | measured — ~96% / 51.4% |
| the element has a row, and so do N look-alikes that print **identically** | `measure_sufficiency.py` | **§1–§9 of this file** |

And a third that neither of those can see, because it is not about an element
at all: the answer is a sentence or a table cell, and nothing in a listing of
*controls* carries it. That is **§10**, `measure_text_flows.py`.

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
  task needs. **That half is now measured separately — §10, through the flow
  recorder — and this bullet stands: DS itself still prices only controls.**
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

---

## 10. The TEXT half — `measure_text_flows.py`

§3 says DS "cannot price prose" and calls that the larger of the two halves.
This is that half. What made it buildable is `run_flow(stop_after=N)`.

### 10.1 Why a static probe cannot answer it

`measure_text_sufficiency.py` is kept as a documented negative result. It takes
eval 4's blind (page, required value) labels — an author told only to write
varied two-hop tasks, every answer re-derived by an independent referee — and
loads the urls the agents visited. It reports 2/5 values carried and **both
misses are a validation message and a search result**: values that do not EXIST
until the page is interacted with. The confound is checkable in one line —
`tasks.md` records `Interactions needed` per task and **0 of 22 need zero** — so
that probe measures how many eval tasks are two-hop, which is 100%.

`stop_after=N` is the separation it lacks. It replays a recorded flow to step N
and stops with the page as that step left it, so "the text surface failed to
carry it" and "the value did not exist yet" stop being the same observation.

### 10.2 The ablation is a parameter, not new code

The source paper ablates an element type from the representation and measures
the coverage drop. Ours needs no new path: **`read_page(filter="interactive")`
IS `read_page` with its text removed.**

    text-dependence = values the controls-only listing does NOT carry / scored
    TS              = carried by any text surface / text-dependent

Every arm is scored separately, so the answer names a TOOL rather than
asserting that "the text surface" carries things: `read_page(filter="all")`
(the default), `get_page_text` at its default budget **and at `max_chars=250k`**
(the budget and the capability are different claims), `search_page`,
`query_elements`, and — for tables — `read_page(ref_id=<table>, filter="all")`,
the aligned renderer #26 built and that `OPEN.md` item 12 records as never
priced.

### 10.3 Where the labels come from

**(a) Playwright reads them, not us.** Every required value, every table
association and the vacuity gate are computed by `page.evaluate` through
Playwright's own CDP session. No collector, no `_domTextPage`, no op router. If
our surface and Chrome's rendering disagree, the probe sides with Chrome.

**(b) The questions are generated, not authored.** Every visible leaf text block
that contains no control, and every table data row with its cells in order.
Nobody writes a task, so nobody gets to choose which values count — which is
what would otherwise let the author pick the values the tools handle well.

**(c) The recorded assertions are never read.** A flow's `expect` blocks were
written by whoever recorded it USING THESE TOOLS, so scoring against them would
ask whether `search_page` finds what `search_page` found. The flows are used
only to reach a state.

What (a)–(c) do not remove: the fixture states were chosen by whoever wrote the
recipes. The `ev-*` corpus is the answer to that — eight recordings made by
eight agents in #63/#64's rounds against eight real third-party apps, by agents
told nothing about any text measurement, and it is the only corpus here with
real page SIZE, which is the thing that makes a budget bite.

### 10.4 Two item kinds, no thresholds

| kind | the item | scored by |
|---|---|---|
| **block** | a visible leaf text block holding no control and inside none | its whole text appears in the arm's output |
| **row** | a table data row: the row key, then its cells in document order | COVERAGE — every value appears. Association is reported **separately** |

A per-cell test was tried first and is wrong: a `Requests` cell reading `1` is a
substring of almost any page, and it scored as carried by the CONTROLS listing,
which prints no table rows at all. An ordered multi-field match has no such
accident.

**Association is three numbers, not one**, because a single rule cannot be
honest about every table: `ordered` (the values appear in order somewhere),
`one line` (reported only over rows whose every cell is itself single-line),
and the scoped renderer. The first version required one line for ALL rows —
see §10.6.

### 10.5 Controls

| control | expectation |
|---|---|
| a random nonce | found by NO arm |
| the text-ablated listing | a SUBSET of the full one |
| vacuity gate | an item whose value is absent from Chrome's own `body.innerText` is EXCLUDED and counted, never scored |
| a state with no items | named, never scored 1.000 |
| two replicates, identical code | item-for-item agreement |

**The vacuity gate currently excludes 0 items on both corpora**, which by §15's
rule is a detector that has not been shown to fire. It fires on the item the
PRE-FIX sweep admitted — jawiki's `出典: フリー百科事典…`, measured absent from
`document.body.innerText` — so the gate works and the `innerText`-only fix
removed its cause upstream. Reported rather than quietly dropped, because a
guard reporting zero is worth nothing until it has been seen to catch
something.

### 10.6 Four probe bugs of mine, three of them in the damning direction

R1 says a result that flatters **or damns** the system gets re-derived before it
is believed, and damning results get believed too readily. All four of these
were caught that way, none by reading the code, and three of them would have
published a worse number than the truth.

| bug | what it did | how it surfaced |
|---|---|---|
| `search_page` miss detected with `startswith("No match")` | the miss path PREPENDS the readiness note (#39), so the sentence is never at the front and **every miss read as a hit** — the random-nonce control scored FOUND on 8 states of 8 | the control, on its first run. Inflating, so it would have raised TS |
| a table row had to be recovered **on one line** | 44 of the 54 rows it scored LOST have a cell whose own text spans lines (an APG keyboard table with a `<ul>` in a cell, a Wikipedia broadcast table) — unrecoverable by construction. The ruler manufactured a third of its own damning result | reading the lost list: `lost rows whose own cell text spans lines: 44` |
| the data-table hint parsed with `data table\(s\) on this page:` | the hint has two shapes, and past a few tables it reads `44 data table(s) on this page, first 6 by document order: ref_…`. The regex matched the short form only, so **jawiki's 44 tables produced an EMPTY scoped arm** and the aligned renderer scored 0 on the only state with real tables | the saved arm dump: `scoped_tables  1 chars` |
| `innerText \|\| textContent` as the sweep's text | HTML makes the `innerText` getter fall back to `textContent` when the element is **not being rendered** (#37 priced that at a quarter of eBay's listing), so the sweep admitted a jawiki string absent from `document.body.innerText` and scored it LOST against tools that were right not to have it | the saved arm dump: absent from the GROUND TRUTH too |

Every arm's raw output is written to `temp/text_flows*/states/<sig>.txt`
alongside Chrome's own `innerText`, which is why three of the four were
findable at all.

### 10.7 The flows, and why each answer is genuinely text-only

Seven recorded against `tools/saas_playground.py` (`flows/txt-pg-*.flow.json`),
plus the nine live ones. "Text-only" is not asserted — it is **measured per
item**, as absence from `read_page(filter="interactive")`, and an item the
controls listing does carry is reported and excluded from the TS denominator.

| flow | the state it stops in | why a fresh navigate cannot reproduce it |
|---|---|---|
| `txt-pg-validation` | the 400 page after submitting a project with no plan | the `.flash` sentence exists only in the response to that POST |
| `txt-pg-login-error` | the 401 login page | same — `GET /login` has no `.err` |
| `txt-pg-new-project` | the table one row longer, `5 project(s) in this workspace` | the row is created BY the flow; the fixture is reset before every replay |
| `txt-pg-modal` | the New-project dialog open | the modal lives in a `[hidden]` backdrop until clicked |
| `txt-pg-report` | the colspan table with a `<br>` in its last header | reachable by url — included as a TABLE case and marked as such |
| `txt-pg-members` | a second table | same |
| `txt-pg-detail` | one project's detail page | same |

**Stopping happens at EVERY step index, not at one someone picked** — choosing
the stop point is choosing the sample. States that repeat (the login landing is
reached by six flows) are deduped by a content hash of the sweep, so the
denominator counts DISTINCT states.

**A fixture reset runs before every replay, not before every flow.**
`run_flows.py` moved from per-run to per-flow because one mutating flow
poisoned every flow after it (#54, one level up); a `stop_after` sweep runs the
same mutating flow many times, so the level goes up again. Without it
`txt-pg-new-project` left a fifth project behind and `txt-pg-validation` failed
its own recorded `4 rows` at every stop point — 0 of its states scored, in
silence except for one REPLAY FAILURES line.

### 10.8 The numbers

**Live — 9 recordings against 9 real third-party apps, 20 distinct states.**
`python tools/measure_text_flows.py --measure --corpus ev --replicates 2`

| | |
|---|---|
| required values scored | **1,133** (985 prose, 148 table rows) |
| TEXT-DEPENDENT (the controls-only listing does not carry them) | **1,047 / 1,133 = 0.924** |
| **TS** | **1,047 / 1,047 = 1.000** |
| LOST by every arm | **0** |

Per arm, over those 1,047:

| arm | carries |
|---|---|
| `read_page(filter="all")`, 50k default | 1,029 = **0.983** |
| `search_page` | 881 = 0.841 |
| `query_elements` (generated selector — an upper bound) | 800 = 0.764 |
| `get_page_text`, 30k default | 797 = **0.761** |
| `get_page_text`, `max_chars=250000` | 1,047 = **1.000** |

**Every loss at default settings is the BUDGET, and nothing else.** 250 values
(211 prose, 39 rows) are missed by `get_page_text` at 30k and carried at 250k;
**0 are missed at both**. The 18 that `read_page(filter="all")` misses at its
50k default are the same class — all 18 come back at the raised text budget.
And the budget is not a silent loss: on jawiki the tool itself reports
`body truncated at 27225 of 62148 chars. YOUR max_chars=30000 was spent as:
27225 body + 332 readiness banner + 1834 document outline`.

So on this sample the text surface's CAPABILITY is complete, and what an agent
actually gets depends on a number it chose and was told about.

**Table rows** (148): the renderer the hint points at,
`read_page(ref_id=<table>, filter="all")`, carries **131 = 0.885**. Association,
which presence does not measure:

| | ordered | one line (111 rows whose cells are single-line) |
|---|---|---|
| `read_page(filter="all")` | 139/148 = 0.939 | 105/111 = 0.946 |
| scoped table renderer | 129/148 = 0.872 | 102/111 = 0.919 |
| `get_page_text` | 109/148 = 0.736 | 95/111 = 0.856 |

`search_page` is the weakest arm for a row (91/148 = 0.615) and is being asked
a question it is not for — it is given the ROW KEY and scored on whether the
hit's bounded context carries the rest of the row.

Every figure above is from **replicate 1 alone**. An earlier draft of this
table mixed three of them in from the two-replicate deduped set, which is two
populations in one ratio — #22's own rule, and the reason it is said here.

**Fixture — 7 recorded flows, 9 distinct states.** 80 required values
(replicate 1, same population rule as above), **text-dependence 43/80 = 0.537**,
**TS 43/43 = 1.000**, every arm 1.000.
**It is saturated and that is the result**: on server-rendered pages that fit
the budget, every surface carries everything. True of small pages, and no
evidence at all about large ones (R2).

**Drift floor.** Two replicates on identical code:

| corpus | items in both | disagreements |
|---|---|---|
| fixture | 77 (of 77 / 77 after collapsing 3 values a page repeats) | **0 on all seven verdict fields = 0.00%** |
| live | 1,107 (of 1,114 / 1,112) | **0 on all seven verdict fields = 0.00%** |

The live STATE set moved by one (20 states, then 19) — that is site drift, not
verdict instability, and it is why the intersection is quoted beside the floor.

**The LOST count across the ruler's own fixes was 55 → 34 → 0**, and every
step of that was my ruler rather than the product:

| | LOST | what changed |
|---|---|---|
| first run | 55 (54 rows) | — |
| row rule: coverage, not same-line | 34 (33 rows) | 44 of the 54 had a cell whose own text spans lines |
| hint regex + `innerText`-only sweep | **0** | the scoped arm could finally run on jawiki's 44 tables; and **0 of the 33 remaining lost rows had every cell in Chrome's own `body.innerText`** — they were collapsed navbox content, so the item count fell by exactly 33 and the tools were right not to carry them |

That last line is the one to check rather than trust, and it was: the removed
set is exactly the lost set, verified value by value against the saved
ground-truth dumps.

### 10.9 What this sample cannot support

Stated before the number, as §3 is.

- **It is not task-weighted.** The items are everything the page renders as
  text, which is a SUPERSET of what any one task needs. That is what makes it
  policy-independent — the same argument §2 makes for DS — and it means a loss
  in a footer counts like a loss in the answer. A real MFS weights by what a
  task asked for; this does not, and #44's lesson applies one axis over.
- **One page dominates the live corpus.** The jawiki article alone contributes
  roughly a fifth of all items, the way exploretock is 17% of Mind2Web's
  sample (#73). Do not put a confidence interval on the live figure.
- **The live corpus is what survived five weeks of drift.** **10 of the 51 live
  stop points (19.6%) failed to replay** — arxiv's Search button, python-docs'
  `Go` input, httpbin's `form_input` refusing, jawiki's history page, and
  todomvc accumulating localStorage across replays because nothing isolates one
  replay from the next (`OPEN.md` 2c). Those states were never scored, so the
  number describes the states that still reproduce. The flows were recorded
  2026-10-11 and replayed 2026-11-16.
- **The block sweep is light-DOM only.** `document.body.querySelectorAll('*')`
  does not enter a shadow root, so a site built on web components contributes
  few prose items. Our own text path DOES cross that boundary (#29), so this
  under-samples the case we handle and cannot flatter us there.
- **The fixture corpus is saturated and says so.** Every arm carries everything
  on pages that fit the budget. That is a true statement about small
  server-rendered pages and no evidence at all about large ones — R2 exactly:
  an ablation measures the code against the sample.

### 10.10 Does this close item 12?

**It narrows it; it does not close it.** The TEXT half goes from *unmeasured*
to *measured with a denominator, a drift floor and a decomposition*, and the
headline is worth stating plainly: **on 20 live post-interaction states, every
one of the 1,047 values a controls-only listing does not carry is carried by
some text surface, and every shortfall at default settings is the caller's own
budget.** That is a stronger answer than the one this file expected to find.

What keeps it open:

1. **Not task-weighted.** The items are everything the page renders, not what a
   task needs. A real MFS weights by the latter. This is the same bound §2
   accepts for DS, and it is the larger of the two gaps.
2. **Association is measured and is NOT 1.000** — 0.939 ordered in
   `read_page(filter="all")`, 0.885 for the scoped renderer's coverage. Carrying
   a value is not the same as saying which row it belongs to, and the table
   half of the paper's "Text" row lives there.
3. **The discovery path is narrower than the tool.** On jawiki the hint reads
   `44 data table(s) on this page, first 6 by document order` — so the aligned
   renderer is reachable for 6 of 44 tables from one listing. The renderer
   scores 0.885; being able to find it is a different number and is not this one.
4. **20 live states, one page a fifth of them, 1 in 5 replays lost to drift.**

