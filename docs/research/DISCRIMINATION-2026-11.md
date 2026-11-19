# Discrimination: can a reader tell two printed rows apart, at any stage?

**Probe:** `tools/audit_discrimination.py` (new)
**Closes:** `FINDABILITY-AT-STAGE-2026-11b.md` §8 gap 1 → CLAUDE.md **#117**, *"the one I
would build next"*
**Sibling:** `docs/SUFFICIENCY.md` / `tools/measure_sufficiency.py`, which asks the same
question on Mind2Web's static snapshots with human labels
**Date:** 2026-11-19

> **Headline.** 12.9% of actionable printed rows share their ENTIRE printed description
> with another row (5,285 of 40,961, **239** live out-of-sample sites, 571 reads of which
> **332** are after an interaction). It does **not** get worse after an interaction — paired
> within site, the median change is **+0.0000** at every one of four depths, in all
> three independent passes. It is **concentrated by surface**: 9.9% on an ordinary row
> against **49.2% on the cap's OVERFLOW list**, which prints a ref and a label and declares that
> it does.
>
> **The one shipped-but-opt-in rung is priced on both halves and REFUSED.**
> `detail="brief"` costs ×1.25 of the listing and **62% of the sites that pay gain
> nothing** (#44's ratio) — because most contested rows sit on a fold or the overflow
> list, **where no per-row field has a slot**: 79% of them on the frozen corpus the
> pricing ran on, 47% on the live staged pool. No product change is proposed.
>
> **§13 splits the bound.** 12.9% is an upper bound; the CONTAINER half of its slack is
> measured at **2.61pp** (so the bound is **10.1%**), and the FOLD half is named and
> deliberately not credited, because the only discriminator there is positional zipping.
> The rung that measures it resolves **0** rows on folds and overflow, by construction
> and in the data.
>
> **Read §2 first.** Every row carries a unique `ref_N`, so the ladder is over printed
> fields with the ref stripped; the falsifier that puts it back runs on every pass and
> must read 100%. It does.

---

## 1. The gap, in the words of the entry that named it

#117 audited which instrument answers which question about the listing and found three
axes covered — **presence** (`audit_stage_generality`), **name correctness**
(`audit_name_correctness`), **reachability** (`measure_findability_at_stage`) — and two
shapes falling between them. #118 closed one (name correctness on hover-revealed
content). This is the other:

> **DISCRIMINATION is not measured at any stage.** `measure_sufficiency.py` is the only
> instrument for "is the target *distinguishable* from its neighbours", and it runs on
> Mind2Web — human-labelled actions on static snapshots with no CSS and no interactions.
> Its population is precisely the one every stage probe sets aside: **this run excludes
> 7,335 of 14,071 probes (52%) as contested** because the identity is shared with another
> entry; the presence probe counts them present; and the name oracle can score both of a
> look-alike pair exact. A page after four interactions is where duplicate labels
> concentrate — a menu of nine `Remove` buttons — and nothing asks the question there.

All three existing rulers read **clean** on a listing that does not determine the action:

| ruler | what it says about a look-alike pair |
|---|---|
| `audit_stage_generality` | both present, 0 identities lost |
| `audit_name_correctness` | both names can be scored exactly correct |
| `measure_findability_at_stage` | both **excluded from the denominator**, by a documented rule in `score_arm` |

---

## 2. The subtlety that decides whether any number here means anything

Every row carries a unique `ref_N`. So "can they be told apart" is trivially YES, and
that answer is worth nothing. The question is whether the listing prints something a
reader could use to pick the **intended** one — a field that carries MEANING rather than
mere identity.

Three consequences, each enforced rather than asserted:

* **`ref_N` is stripped from every key**, including from the ancestry keys (an ancestor
  identified by its own ref would smuggle the ref back one level up). The falsifier that
  puts it back is computed on **every run** and printed in the report as
  `CONTROL +ref_N`: it must read 100%. If the reported rungs ever approach it, that is
  the first thing to check.
* **`box()` is reported as an opt-in rung and is not a recommendation.** It is off by
  default (`geometry=true`, #26) and it makes essentially every row unique — which makes
  it a *second falsifier* more than a finding. A coordinate identifies; it does not say
  which one you meant.
* **`href`/`src` are reported as an opt-in rung**, because they are absent from the
  shipped default `detail="compact"` (#10). A field the caller did not ask for is not
  available to them.

---

## 3. The field set, and why it is NOT the flow-descriptor ladder

`audit_descriptors.py` measures the FLOW DESCRIPTOR's ladder. Its **machinery** is reused
here in shape — cumulative `uniq_<lv>`, the tie-size distribution, the
one-site-is-one-row discipline — because that is the same computation. Its **field set**
is not, and must not be, because this asks about a reader looking at printed output:

| field | in the descriptor ladder | printed by `read_page` | here |
|---|---|---|---|
| tag / role / type | yes | yes | **rung 0** |
| accessible name / value / placeholder | yes (as one `name` key) | yes, as separate slots | **rung 1** |
| `under=` (the heading above) | **yes** | **NO** — a `find` output field only | **excluded** |
| `section=` | yes | **flat format only** — `_treeLines` strips it (#27) | **the flat arm** |
| tree position (indentation) | no | **yes, in the default format** | **rung 2** |
| `near=` | yes | yes | **rung 3** |
| state: `(disabled)`, `(required)`, `(read-only)`, `(unselected)`, `(collapsed)`, `(post-key)`, constraints, `options=`, `help=`/`error=` | **deliberately excluded** | **yes, on every row** | **rung 4** |
| `href` / `src` | not a rung (an `alt` key) | `detail="brief"`/`"full"` only | **opt-in, reported apart** |
| geometry | excluded (it drifts) | `geometry=true` only | **opt-in, a falsifier** |

**What was reused, and the one thing that could not be.** The ladder's SHAPE is
`audit_descriptors.py`'s and is deliberately not re-invented: cumulative `uniq_<lv>`, the
tie-size distribution rather than a tie count, and its one-site-is-one-row discipline.
The computation itself — `Counter` the keys, count the singletons, collect the crowd
sizes — is four lines reimplemented rather than imported, because that file holds it
**inline inside a per-site coroutine** over a dict-shaped descriptor key, with no
function to import. Extracting it would mean editing a probe four other papers depend
on, for four lines whose concept is "count duplicates". Stated rather than left to look
like the instruction was ignored (PRINCIPLES 17 — and the field sets genuinely differ,
which is the whole point of this table).

`descriptor.py` excludes state on purpose — *"identify by them and a step can only find a
control already in the state the step exists to produce"*. A **reader** has no such
constraint, so it is a rung here.

Because the ladder's attribution depends on an order I chose, every run also reports a
**leave-one-out marginal** at the full rung, which does not.

---

## 4. One spelling, and it is the collector's — plus the two places that cost a rewrite

The rung keys are built from the entry's own fields and then **verified against the real
printed row**; `decomp_fail` counts any row whose computed identity is not a prefix of
its own line, so a format change under this probe fails loudly instead of silently
mis-attributing a difference to the wrong rung. Ancestry is not reconstructed from the
DOM at all: it is parsed out of the listing's own **indentation**, which is what the
reader sees, including the tree's pruning and grouping.

Two things about "the printed row" were not what I assumed, and both were caught by that
tripwire rather than by reading:

**(a) `e['line']` is `find`'s row, not the reader's.** The collector attaches `line` to
every structured entry, built with **#74's blanking** applied. The TREE runs #29's
container-label rollup instead. They disagree:

```
e['line']     ref_74 | a section=nav (opens NEW tab) (container — the text here belongs…)
tree listing  ref_74 | a "GitHub" (opens NEW tab)
```

Bootstrap's footer ships three such links. Under `e['line']` they are three identical
rows; in the listing a reader is handed they are **GitHub / X / Open Collective**.
Measuring the first would have reported a defect the shipped output does not have.

**(b) `e['near']` survives a suppression the listing applies.** #37 drops a `near` hint
shared by rows that have their own identity — so a `near` that *survives* is one that
discriminates. That pass runs on the string-listing path, and the structured branch
`return out`s before it, so the entry keeps a `near` the listing never prints:

```
e['line']   ref_68 | a "Icons" near="Docs Examples Icons Blog" section=nav (opens NEW tab)
tree row    ref_68 | a "Icons" (opens NEW tab)
```

Computing `near` from the field credited the reader with a discriminator that is not on
the page in front of them. It is read off the row now.

**One printed row is one row.** Since #28 the container rules demote rather than delete,
so one control is routinely two or three nested entries, and #29's collapse puts them on
a single row when label and all four box fields match. Counting each ref separately would
manufacture a contested pair out of one line. Deduplicated by (row, box); FOLD lines are
*not* deduplicated, because their members have different boxes and are different
elements.

---

## 5. Proving the probe can fire, before any number is believed

PRINCIPLES 5 and 15. **A ladder that reports everything unique because of a bug looks
exactly like a system with no problem**, so the probe must be SEEN to report a collision,
and seen NOT to report one where none exists.

### `--selftest` — **PASS**, `failures: []`

| check | result |
|---|---|
| six identical `Star` buttons, no neighbouring text | **6 of 6 contested**, verdict `page` |
| **CONTROL** — the same shape WITH neighbouring text (an invoice table) | identity alone separates **0**; `near=` separates **4 of 4** |
| a crowd the page separates only with `title` | verdict **`ours-absent`** |
| **CONTROL** — four distinctly-named buttons | identity alone separates **4 of 4** |
| **THE REF FALSIFIER** — the same key plus `ref_N` | **6 unique with the ref, 0 without** |
| two links to one destination, same container | verdict **`interchangeable`** |
| the decomposition tripwire on a real page | **0 failures** |

The ref falsifier is the one that matters: it discriminates 6 against 0, so the reported
rungs are provably not counting the ref.

**The first version of the colliding fixture was the canonical ambiguous shape and the
listing SOLVES it.** Four `Remove` buttons in an invoice table came back **4 of 4
unique**, because the collector prints `near="INV-1001 Remove"` on each row. The fixture
encoded my belief that a table of identical buttons is ambiguous (PRINCIPLES 11), and
only running it said otherwise. It is kept as the `near=` control above — a more useful
check than the one I meant to write.

### `--fire` — the LIVE firing proof, **15 of 15 measurable sites fired**

On a real page, take the largest run of **printed, actionable siblings** and give them
one `aria-label`; the planted rows must come back reported as one contested crowd.
1 site UNMEASURED and named (`bank_bbl_th` offered one printed sibling); it is not
counted as a pass. **Re-run on the final probe code after the headline pass**, rather
than inherited from an earlier build — #117's practice, and the reason its own paper
says "both proofs were run on THIS collector".

**Three versions of this plant fired on 0, 1 and 11 of the sites before the fourth
worked, and each failure was the plant not reaching the code under test** — which is
PRINCIPLES 11 one level up, and the reason the sequence is recorded rather than only the
result:

| plant | fired | why not |
|---|---|---|
| k elements strided across the document | **0 / 9** | elements in different parts of a page are already separated by the ANCESTRY rung, so overwriting their names collides nothing |
| the largest run of siblings, chosen off any `[mmid]` | 1 / 10 | most `[mmid]` elements are not printed rows — the listing is viewport-scoped and capped |
| siblings among rows this run measured as printed | 7 / 10, then 11 / 14 at the identity rung | scored by DIFFERENCING a whole-page contested count, which on the live web measures the web: `gov_au`'s identity-rung count went 22 → 16 while the plant plainly landed |
| **…scored on whether the PLANTED rows are reported as one crowd** | **15 / 15** | churn-proof: it asks about the probe, not about the page |

---

## 6. The population, measured rather than inherited

#117 reports **52% of its probes contested**. That is a different population in three
ways, all pushing the same direction, and the only way to say which carries the
difference is to recompute its key on this corpus (the probe does, every run):

| | #117 | here |
|---|---|---|
| what is counted | a **stride sample** of entries | **every PRINTED row**, deduplicated by (row, box) so #29's collapse is one row |
| drawn from | the **WHOLE-PAGE** structured array | the rows the listing actually prints — viewport-scoped and capped |
| keyed on | `identity_of` **alone** | **every printed field** |

Its key, recomputed here: **57.5% of whole-page entries share an `identity_of`** (live
pool) and **63.0%** (frozen corpus). So the definitions agree closely and the 52% is
real for what it measures — *"could this element's name be confused with another's,
anywhere on the page"*. It is not the share of a listing's rows that a reader cannot
tell apart, and it was never offered as one.

**Two numbers answer the question that was asked, and they are different questions.**
Across 239 live out-of-sample sites and 40,961 actionable printed rows:

| | rows | share |
|---|---|---|
| share a printed **IDENTITY** with another row | 10,713 | **26.1%** |
| …still share **EVERY printed field** after ancestry, `near=` and state | 5,285 | **12.9%** |

Both figures reproduce to the decimal across three independent passes (26.1% / 12.9% on
pass A, 25.9% / 12.4% on pass B, 26.1% / 12.9% on pass C — the headline).

The first is "could this row's name be confused with another's". The second is "is there
anything printed that tells them apart" — and it is the one that matters, because the
listing prints more than a name.

**"Actionable" is the collector's own `clickable || editable`, asked of what it already
decided** rather than of a second tag list — #18 measured two rules disagreeing about
what a control is as 60% of a whole accuracy gap, and `descriptor.py` makes the same
choice for the same reason. It is the right population because a reader picks a row in
order to ACT on it; a media row or a pure container is not a choice anyone has to make.
The probe also computes the ladder over EVERY printed row (`all` in the artefact), and
it is reported in the JSON rather than here.

**Two existing numbers bracket what that is worth, and both are already measured.**
`measure_sufficiency` reports **27.6%** of on-screen rows sharing a printed identity on
Mind2Web; this probe's IDENTITY rung — the comparable one, before ancestry, `near=` and
state — reads **26.1%** on 239 live sites. Two corpora, two methods, within 1.5pp: the
density figure is solid.

And the same run reports that only **6.7% of the rows a human actually needed** were
ambiguous — *"a roughly 4× gap … most repetition is unnamed icons, bare `svg` and
generic containers that nobody targets."* **So 12.9% is a rate over ROWS, not over
TARGETS**, and the share that an agent will actually have to disambiguate is several
times smaller. This probe cannot narrow that itself: it has no task labels, which is
precisely the division of labour between it and `measure_sufficiency`.

### It does not degrade after an interaction

| stage | reads | actionable rows | unique | contested |
|---|---|---|---|---|
| s0 first paint | 239 | 16,654 | **87.7%** | 2,047 |
| s1 | 155 | 11,021 | **86.9%** | 1,439 |
| s2 | 83 | 6,218 | **86.1%** | 867 |
| s3 | 54 | 3,923 | **87.0%** | 511 |
| s4 | 40 | 3,145 | **86.6%** | 421 |

**That table compares different site POPULATIONS and on its own it proves nothing** —
238 sites reach s0 and 40 reach s4, so a 1.1pp spread there is composition until shown
otherwise. #115 and #118 both found exactly that shape and both paired to +0.0000. So
the same test, PAIRED WITHIN SITE, over the sites that reach each depth:

| | n | median Δ | mean Δ | better / worse / unchanged |
|---|---|---|---|---|
| s0 → s1 | 160 | **+0.0000** | −0.0020 | 53 / 21 / 86 |
| s0 → s2 | 84 | **+0.0000** | +0.0136 | 34 / 13 / 37 |
| s0 → s3 | 55 | **+0.0000** | +0.0039 | 17 / 13 / 25 |
| s0 → s4 | 41 | **+0.0000** | +0.0009 | 11 / 10 / 20 |

**Median zero at every depth, and reproduced independently in all three passes** (pass A
s0→s4 +0.0015, pass B −0.0014, pass C +0.0009; medians +0.0000 throughout). Where a site moves
at all, more move BETTER than worse at every depth.

#117's expectation that *"a page after four interactions is where duplicate labels
concentrate"* is **not borne out**. A menu of nine `Remove` buttons is no more likely
after an interaction than before — which is a negative result, and the one the gap was
named for.

### …but it is extremely concentrated BY SURFACE, and that is the finding

| surface | rows | contested | rate |
|---|---|---|---|
| ordinary row | 29,561 | 2,937 | **9.9%** |
| fold member | 7,562 | 461 | 6.1% |
| **the cap's OVERFLOW list** | 3,838 | **1,887** | **49.2%** |

The overflow list is 9.4% of printed rows and **36% of all contested ones**. On the
frozen corpus, where pages are denser and the 150-entry cap fires more often, it is
**61.5% contested and 73% of the total** — while the ordinary-row rate is **9.9%**,
identical to the live figure to the decimal. Two corpora, one stable number for ordinary
rows, and the headline moving entirely with how much of the listing is overflow.

That is #27's entry cap behaving exactly as documented: the overflow list keeps every
ref actionable and prints `439:"upvote"` and nothing else. It is a declared trade, not a
silent one.

---

## 7. The ladder

Cumulative over printed fields, actionable rows, 239 live sites. **The leave-one-out
column is the one to trust**, because the cumulative order is one I chose.

| rung | unique | still contested | **of the 10,713 identity-contested, this rung resolves** | leave-one-out |
|---|---|---|---|---|
| `tag` + `role` | 4.7% | 39,036 | — | tag +0.58pp · role +0.06pp |
| **+ identity** (name / value / placeholder / text) | **73.8%** | 10,713 | — | **+54.92pp** |
| **+ ancestry** (the tree's indentation) | **84.8%** | 6,234 | **4,479 (41.8%)** | **+9.19pp** |
| + `near=` | 85.4% | 5,982 | 252 (2.4%) | +0.55pp |
| + state (`(disabled)`, `(required)`, constraints, `options=`, …) | **87.1%** | 5,285 | 697 (6.5%) | **+1.70pp** |
| **residue** | | **5,285** | **49.3% unresolved** | |
| | | | | |
| *opt-in* — `+href/src` (`detail="brief"`) | 90.2% | | | |
| *opt-in* — `+box()` (`geometry=true`) | 99.0% | | | |
| **CONTROL — `+ref_N` (the falsifier)** | **100.0%** | | | must be 100% |
| `format="flat"` (`section=` for indentation) | 86.4% | | | **not comparable — see below** |

**The identity carries 55pp and the tree's indentation carries 9.2pp.** The second
number is the measured value of #27's format change on a question #27 could not ask:
*what is the ancestry a reader can see worth, as a discriminator?* More than `near=` and
state put together, and second only to the name itself.

**The flat row is NOT subtractable from the tree row and I nearly published it as
+0.7pp.** The two formats do not print the same population: 40,961 actionable rows in
the tree against **30,984** in flat, a 9,977-row gap, because flat pulls demoted entries
into one `PROBABLY DECORATION` line and folds differently. Dividing one format's unique
count by the other's row count is #22's rule — numerator and denominator from one
population — which is the same error the tie histogram caught two paragraphs down.
Whether the tree's indentation beats `section=` as a discriminator is a real question
and this run does not answer it; it would need both formats keyed over the intersection
of their mmids.

`near=` and state are worth about half a point and 1.6 points respectively — small, and
both are already near-free (#37 suppresses a `near` that discriminates nothing; state
tokens are short and legend-explained).

**Tie sizes are small.** **57% of the 5,285 contested rows sit in a crowd of 3 or
fewer** (64% on the frozen corpus); the largest crowd on any one page is 28 live and 70
frozen. This is not a listing full of forty-way ambiguities — it is
mostly pairs, which is the cheapest kind to escalate out of.

**And it is concentrated by SITE as well as by surface.** Per-site median **0.948**;
**51 of the 195 sites with at least 50 rows are at ≥0.999** — every row uniquely
described — while the tail is thin and deep: `w2_hku` 0.212 over 480 rows,
`w2_indonesia` 0.526 over 95, `ko_daum` 0.582 over 1,463. The aggregate is not a property most pages
have a little of; it is a property a minority of pages have a lot of.

---

## 8. The residual, classified — and why three outcomes became six

The brief for this work asked for three outcomes: *genuinely interchangeable*,
*distinguished only by something we deliberately do not print*, and *distinguished by
nothing at all*. The middle one turned out to cover four things with four different
answers, so it is split rather than pooled — pooling them produces a figure that is true
and useless, which is the shape #61 warns about for `id`.

| verdict | maps to | what it is | is it a defect? |
|---|---|---|---|
| `interchangeable` | **(1)** | one declared destination for all of them, or they are NESTED in one another — one spot, one action | **no**, and not even a cost |
| `ours-optin` | (2) | the only human-meaningful difference is `href`/`src`, which `detail="brief"` prints | no — a recovery exists and is one parameter |
| `ours-elsewhere` | (2) | what separates them IS printed, on another row — usually the record each sits in | not a missing fact; a pairing problem (#30: *position is not rank*) |
| `ours-devkey` | (2) | only an internal key (`id`, the wire `name`) differs | no — #61 measured `id` at 6.8% coverage and REJECTED it as a rung, and a human cannot read one off the screen either |
| **`ours-absent`** | (2), sharpest | the page declares something human-meaningful and it appears **nowhere** in the listing | **the only candidate defect** |
| `page` | **(3)** | nothing the document declares separates them | no — **no representation could**, so it is the page's ambiguity |

`interchangeable` is PROVED rather than assumed: either one `href` shared by every
member, or a DOM `contains()` test over every pair. It is the single largest class here.

**A citation corrected on the way.** The brief for this work cited *"#116 measured 29 of
these on one site"*. #116 does record a site with **29 identical `Remove` buttons**, but
not as a measurement of interchangeability — it names them as a CONFOUND in its own
grading, which *"matches by name STRING so 29 identical `Remove` buttons each score the
others as reachable-elsewhere"*. That is this paper's population seen from the other
side, and it is a good illustration of why the question needed its own instrument; it is
not a prior measurement of it.

**The verdict is near-complete rather than a sample on the live pool** — 1,710 of 1,755
contested crowds classified (**97%**; 68% on the denser frozen corpus, where the
per-stage cap of 40 crowds bites). The crowds are chosen by a STRIDE over the
size-sorted list, so it is not simply the biggest ones.

| verdict | outcome | crowds | rows | share of contested rows |
|---|---|---|---|---|
| `interchangeable` | **(1)** | 673 | 1,709 | **32.5%** |
| `page` | **(3)** | 333 | 1,139 | **21.7%** |
| `ours-optin` | (2) | 106 | 395 | 7.5% |
| `ours-elsewhere` | (2) | 180 | 614 | 11.7% |
| **`ours-absent`** | **(2)** | 319 | 1,117 | **21.3%** |
| `ours-devkey` | (2) | 10 | 20 | 0.4% |
| `unresolved` | — | 89 | 260 | 4.9% |
| | | **1,710** | **5,254** | |

Rolled up to the three outcomes the brief asked for:

| outcome | rows | share |
|---|---|---|
| **(1)** acting on any member does the same thing | 1,709 | **32.5%** |
| **(2)** the document declares something the listing does not print | 2,146 | **40.8%** |
| **(3)** nothing the document declares separates them | 1,139 | **21.7%** |
| — could not resolve (a member's element was gone by probe time) | 260 | 4.9% |

**A third of the residue costs nothing, a fifth is the page's own ambiguity, and the
only class that is unambiguously a gap of ours is 21.3%** — 1,117 rows, which is **2.7%
of all actionable printed rows**.

### What `ours-absent` actually is, because 1,117 rows deserves a look rather than a label

**1,710 of the 5,254 contested rows (33%) print NO identity at all**, and they carry
**698 of the 1,117** `ours-absent` rows. These are unnamed clickable containers — a
`<div>` with a handler wrapping a group of controls, printed as `ref_57 | div` and
nothing else. On `w2_ccel` nine of them sit side by side; their `textContent` is *"Show
only: Any genre Bibles Biographies…"*, *"Books only Classics only"*, *"Sort by:
Relevance Title Popularity"*.

**What distinguishes them is printed — as their children, one indent down** — which is
§10's limitation, not a missing fact. The remaining ~400 `ours-absent` rows DO carry an
identity and still have a declared difference nowhere in the listing; that is the
sharpest residue this probe found and it is 1.0% of actionable rows.

**Restricted to ORDINARY rows** (the surface where nothing announces the ambiguity, as
a fold header and the overflow notice both do):
`interchangeable` 14.5% · `page` 28.4% · `ours-optin` 8.5% · `ours-elsewhere` 18.6% ·
`ours-absent` 26.3% · `ours-devkey` 0.7% · `unresolved` 2.9%.

---

## 9. The one rung that is shipped-but-opt-in, priced on BOTH halves — **DON'T BUILD**

`href` is the only field in the table of §3 that the collector can already print and the
default does not. #41 and #44 are the entries that govern this: #41 priced a change on
its cost half, it read Pareto-positive, and #44 then measured the benefit half and
refused it because **70% of the spend landed on steps that gained nothing**.

**The benefit is measured on a MATCHED population and the cost on the real listing**,
because the two cannot come from the same arm. 90 frozen sites, 10,734 actionable
printed rows, both arms from the same page load:

| arm | unique | listing chars |
|---|---|---|
| base — the shipped `detail="compact"` | **74.9%** | ×1.000 |
| **TARGETED** — href on contested rows only, where a row has a slot for one | 75.5% | ×1.010 pooled · ×1.000 median · ×1.18 worst |
| **BLANKET** — `detail="brief"` | 79.7% | **×1.250** pooled · ×1.23 per-site median · ×2.27 worst |

**#44's ratio, which is the number that decides it:**

| arm | sites paying >1% chars | of those, gaining NOTHING |
|---|---|---|
| targeted | 20 / 90 | 5 (25%) |
| **blanket** | **90 / 90** | **56 (62%)** |

Per-site median gain is **+0.00%** for both arms. Blanket href costs every site a quarter
of its listing and 62% of them get nothing back — #44's shape, at #44's magnitude.

### Why the targeted rule buys almost nothing, which is the structural finding

**2,132 of the 2,697 contested rows (79%) are on a FOLD line or the cap's OVERFLOW
list** — on the frozen corpus this pricing ran on, where dense pages hit the entry cap
often; **47% on the live staged pool** of §6, whose pages are shallower. Neither surface
has a slot for a per-member field. A fold prints `5:"upvote"`; the
overflow list prints `439:"upvote"`. Appending a URL to either is a different and much
larger format change.

So the discrimination residue does not live where a missing FIELD could fix it. It lives
on the two surfaces that **deliberately drop per-member detail for token economy** —
#7's grid fold and #27's entry cap, both measured and both with a stated recovery (act by
ref). `detail="brief"` appears to fix it only because adding href makes identical
siblings non-identical, which **un-folds them**: 42 of 90 sites gain rows under `brief`,
+284 in total. That is a second, unpriced cost of the blanket rule and it is the
mechanism behind most of its 4.8pp.

**A note on how nearly I got this wrong.** The first targeted arm let href land on fold
and overflow rows too, and reported the targeted rule as *more* expensive than the
blanket one on Hacker News (×1.277 against ×1.02). The model was pricing a change the
format cannot express. Restricted to rows that have a slot, the same rule buys +0.6pp.

---

## 10. What this cannot answer — do not quote a number without these

* **Whether a model USES the information.** This asks whether the information is
  PRESENT. #75 is the entry where conflating those two wasted a day, and
  `measure_sufficiency` says the same of its own DS: *"DECIDABLE means the listing
  permits a correct choice, not that a model makes one."*
* **Whether contested is failure.** It is not. The agent can escalate for one model turn
  (~3.6s, 92–97% of a tool call, #38) or guess 1/N — and for the interchangeable class it
  is not even a cost.
* **Whether the name is RIGHT** (`audit_name_correctness`) or **REACHABLE**
  (`measure_findability_at_stage`). A wrong name shared by two rows scores contested here
  and says nothing about correctness.
* **The residual verdict is per CROWD, not per member.** A crowd mixing a harmless
  nested pair with two genuinely different records gets one label.
* Inherited from #89's driver wholesale: hover-only menus, logins, paywalls,
  cross-origin frames, **one path per site**, and the ~180 consent- and bot-walled
  candidates absent from the pool before this probe starts. No user-agent spoofing and no
  bot-check evasion, so a site that declines automated traffic is simply absent.

### The one I am least sure of

**A reader can use POSITION and this ladder cannot.** Ancestry models where a row sits
*under*; it does not model what sits *beside* it or *beneath* it. Two concrete places
that matters, both pushing the reported contested share **up**:

* a container row is distinguished by what is indented under it — "the div holding
  *Any genre / Bibles / Biographies*" is plainly not "the div holding *Books only /
  Classics only*" — and the key ignores descendants entirely. **1,710 of the 5,254
  contested rows (33%) print no identity at all**, and they carry 698 of the 1,117
  `ours-absent` rows: exactly this shape.
* two sibling FOLDS of equal length can be zipped by position, which is how a reader
  pairs an upvote arrow with its story. #27 and #30 both warn that this silently
  mispairs everything after a gap when the folds are unequal — so the discriminator is
  real and unsafe, and crediting it would be as wrong as ignoring it.

So **12.9% is an upper bound on the share a reader cannot resolve**. **§13 measures the
first half and leaves the second refused**, so the slack is now two lines rather than
one: the container half is **2.61pp** (the bound moves to **10.1%**), and the fold half
is named, unmeasured and deliberately not credited — 57% of what is still contested
sits on a fold or the overflow list, where the only reader-side discriminator is
positional zipping, which #27 and #30 both measured silently mispairing everything after
a gap. **Half a fix to a bound would be worse than a stated bound; a measured half and a
named half is not that.**

---

## 11. Mistakes while measuring this

**1. The tripwire could not fire, in the probe whose report prints it as evidence.**
`decompose` tried three identity candidates and the third was `""`, which always peels —
so `chosen is None` was unreachable and `decomp_fail` read 0 whatever happened. Worse
than a dead counter: a row whose identity failed to peel silently got `ident=""` and had
its identity text swept into `state`, which moves the IDENTITY rung without moving the
full one. PRINCIPLES 15, written by someone who had just read it. Revived by the one
fact that separates the two cases — a row whose label the tree ROLLED UP prints no
identity at all, while a mis-computed one leaves the identity TEXT behind — and shown
firing by ablating `printed_identity`. The legitimate rollup case is now counted
(`ident_rolled`, 25 of 1,636 printed rows on a 15-site corpus).

**2. The evidence test reported 1,018 rows as "declared nowhere in the listing" when
every word was there** (the figure on the pass that had the bug). A container's `textContent` is its children's text
CONCATENATED, and the listing prints those children as separate rows — so that string
can never appear in it contiguously however complete the listing is. Caught by opening
one case (`w2_ccel`, nine identical `div` rows) rather than by reading the code, which
is PRINCIPLES 8 in the damning direction. Word-level now, with authored strings
(`title`/`alt`/`aria-label`) still tested whole.

**3. Three live firing proofs that did not reach the code under test**, in §5. Each
produced a clean low number that looked like "the probe found nothing".

**4. `e['line']` is `find`'s row, not the reader's; `e['near']` survives a suppression
the listing applies.** Both in §4, both caught by the tripwire rather than by reading,
and the first would have reported a defect the shipped output does not have.

**5. The SITES rows are three-tuples and I unpacked two, twice.** `ValueError: too many
values to unpack` at index 59 of 106, losing 59 sites of work because nothing had been
written yet — which is verbatim the failure `RECORD-ATOMS-RECONCILIATION` records
killing **all four** existing descriptor probes at the same site of the same corpus. I
then wrote the same two-way unpack into a second function while fixing the first. One
`frozen_sites()` now, and the `settle_ms` those rows carry is used rather than
discarded.

**6. Two more two-population comparisons, both caught before publishing.** The tie
histogram maps crowd SIZE to a count of ROWS, and weighting it by size reported "24,643
rows in ties" against a ladder that said 5,231 — caught by cross-checking it against the
ladder's own contested count, which it must equal and now does. And `format="flat"`
printed 30,946 rows where the tree printed 40,558, so the two rates are not
subtractable; a "+1.5pp for the tree's ancestry" was written and withdrawn. *(Both
figures are from pass A, where each was caught; §7 carries pass C's.)*

**7. The cost arm compared two different populations.** `detail="brief"` yields **more
rows** than `detail="compact"` on 42 of 90 sites (+284), because href differing breaks
#29's identical-nested-row collapse and un-folds them — so the first cost/benefit table
divided a numerator and a denominator drawn from different populations (#22's rule).
The benefit in §8 is measured on a matched population; the cost is the real listing.

**8. A phantom flag.** This file's own Run block advertised `--controls`, which does not
exist — #67's `--check-only`. Both falsifiers run on every pass instead.

---

## 12. Reproducing

```bash
# the fixture firing proofs — 7 checks, including the REF FALSIFIER
python tools/audit_discrimination.py --selftest

# the LIVE firing proof (plants one aria-label across printed, actionable siblings)
python tools/audit_discrimination.py --fire -n 16

# the headline: live, staged, out-of-sample
python tools/audit_discrimination.py --pool usable85 --conc 6 --stages 4 \
       --out temp/discrimination/mainC

# the deterministic cross-check, first paint, real styled pages
python tools/audit_discrimination.py --corpus frozen -n 106 --out temp/discrimination/frozen

# BOTH halves of detail="brief"
python tools/audit_discrimination.py --cost -n 106

# every table above, from a saved artefact
python tools/audit_discrimination.py --report temp/discrimination/mainC/pass0.json
```

### The runs, and why there are three

Every artefact records the collector hash, the probe hash and its label. **The probe
hash is why there are three live passes and not two**, and the drift script asserts on
it rather than trusting me:

| pass | probe | role |
|---|---|---|
| `mainA` | `e5dc8096…` | first full pass |
| `mainB` | `ba462d75…` | + the tripwire revival and `ident_rolled` |
| **`mainC`** | `f447deb1…` | **+ the word-level evidence test — the headline** |
| `frozen` | `ba462d75…` | deterministic cross-check, first paint |

A↔B was intended as the drift floor and **is not one**: the hashes differ, so it
measures drift PLUS the tripwire diff, and `analyse.py` says so in those words rather
than printing a number that looks like a floor. **B↔C is the floor for the LADDER**,
because the evidence-test diff touches `classify` only and cannot move a rung. The
ladder is stable across all three regardless: identity **0.739 / 0.741 / 0.739**, full
rung **0.871 / 0.876 / 0.871**, and the ref falsifier **1.0000** on every one. B↔C
pooled |Δ| is **0.0032**, per-site median **0.0000**, p90 0.0039, with **196 of 235
sites identical**. The revived tripwire refused the same 41 rows in all three passes —
every one a landmark ref named only in the off-viewport region hint, which is not a row
— so the fix is number-neutral on live markup as well as on the frozen corpus.

| `mainD` | `17c9cec7…` | **+ the scoped children rung of §13** |
| `frozenK` | `17c9cec7…` | §13's frozen cross-check |

Artefacts:
`temp/discrimination/{mainA,mainB,mainC,mainD,frozen,frozenK}/pass0.json`, `cost.json`,
`fire.json`.
The matched-population targeted/blanket arm of §8 is a throwaway that imports this
probe's own `build_recs` and `_uniq_and_ties` so only the KEY changes between arms;
its per-site rows are in `temp/discrimination/targeted.json`.

---

## 13. The container half of the slack, measured — and the fold half, still refused

§10 reports 12.9% as an **upper bound with unmeasured slack**, and names two causes. One
of them is reachable and this section measures it. The other is not, and the refusal
below is unchanged — it is the same argument, stated once more because it is the
load-bearing part.

**This is not the `+children` rung §10 declines**, and the difference is scope. §10
declines adding children *to the ladder* as a general fix, on the grounds that it cannot
fix the fold half. That is an argument for SCOPING the measurement, not against making
it. So: a number for the container half, a named unmeasurable for the fold half, two
lines instead of one.

### Why this cannot credit positional zipping — by construction, then measured

The thing §10 refuses is crediting a reader for pairing member *k* of one fold with
member *k* of another, which #27 and #30 both measured silently mispairing everything
after a gap. The rung cannot reach it, and not because of a rule I had to get right:

* it keys a row on the rows **indented beneath it** — a parent→child relation the tree
  actually prints;
* a **fold member and an overflow entry are not rows with children.** They are tokens on
  one line. `children_index` skips any line carrying more than one ref, so those rows get
  nothing at any value of the rung;
* nothing in it ever looks at a **sibling**, which is where zipping lives.

**Measured rather than left as an argument:** the probe reports
`kids_resolved_by_surface` on every run and the analysis **asserts** that fold and
overflow are zero. The canonical case is Hacker News, whose record spans two sibling
`<tr>`s so the tree groups upvotes and titles into *separate* folds (#27) — the zipping
shape exactly. There:

| hn, first paint | |
|---|---|
| contested rows, by surface | fold **55**, overflow **57**, ordinary row **0** |
| resolved by the children rung | **{}** — nothing |
| full rung unique | **151 → 151** of 263 rows |

The rung is worth precisely zero on the page the refusal was written about.

### A child a reader cannot see is not a discriminator

Children are read from the **listing's own indentation**, so they are printed by
construction — never from the DOM. The cap's overflow list prints on a flat line at the
end and is therefore never indented under anything, which excludes it automatically. A
second variant (`kids_vis`) additionally drops a child whose row is tagged
`(below-fold)` / `(above-fold)` / `(outside the viewport)` / `(off to the side)`, and
both are reported — a sensitivity rather than a choice.

### Firing proofs, run on this code

| check | result |
|---|---|
| **CH1** two sibling containers colliding on every printed field, different children | separated: **4 → 6** unique |
| **CH2 CONTROL** the same shape with IDENTICAL children | **0 → 0** — not separated |
| **CH3 CONTROL** a fold's members | untouched, `resolved_by_surface` empty |
| **ablation** — `children_index` forced to return nothing | **CH1 FAILS**, `(4 -> 4)` |
| **planted violation** — `fold: 1` written into a copy of an artefact | the invariant **raises**: *"THE RUNG TOUCHED A FOLD OR OVERFLOW ROW — it has re-admitted zipping"* |
| no `ref_N` and no `box(` in any child key | asserted per key; refs reduce to the constant token `ref`, which carries nothing |
| the ref falsifier, still | **100.0%** |

CH2 is the one that makes the number mean anything: without it, a rung that separated
every container regardless would pass CH1 and measure nothing.

### The number — and it is not a null

Pass **`mainD`** (probe `17c9cec7…`), 237 usable sites of 265, 558 reads, **39,841
actionable printed rows**. Its five shipped rungs reproduce pass C to within the drift
floor (+0.0003 to +0.0032), which is what licenses reading the sixth.

| | unique | contested | share |
|---|---|---|---|
| full rung, as shipped | 34,769 | 5,072 | **12.73%** |
| **+ children printed under the row** | **35,810** | **4,031** | **10.12%** |
| + children, off-viewport ones dropped | 35,810 | 4,031 | 10.12% |

**The container half of §10's slack is 2.61pp** — the upper bound moves 12.7% → 10.1%.
Against the B↔C drift floor of **0.0032 that is 8.2× the floor**, so it is a measurement
and not noise. Requirement 4 does not apply, and I am not dressing it up either way.

The off-viewport sensitivity is **exactly zero**: dropping children whose rows are
tagged `(below-fold)` and friends changes the figure in neither direction, so the result
does not depend on how generously "a reader can see it" is read.

**Where it lands, which is the whole point of scoping it:**

| surface | contested before | **resolved by the rung** | after |
|---|---|---|---|
| ordinary row | 2,767 | **1,041 (37.6%)** | 1,726 |
| fold member | 453 | **0** | 453 |
| the cap's OVERFLOW list | 1,852 | **0** | 1,852 |

**It resolves 37.6% of the contested ORDINARY rows and nothing at all on the other two
surfaces** — the container half exactly, and the fold half untouched. 9,590 of 39,841
rows (24.1%) have printed children at all, which is the ceiling on what this rung could
ever have moved.

### The frozen cross-check, which moves the way the mechanism predicts

Same probe, 91 frozen sites, first paint, 10,745 actionable rows:

| | live (`mainD`) | frozen (`frozenK`) |
|---|---|---|
| container half of the slack | **+2.61pp** | **+1.61pp** |
| contested ordinary rows it resolves | 1,041 / 2,767 = **37.6%** | 173 / 565 = **30.6%** |
| resolved on fold / overflow | **0 / 0** | **0 / 0** |
| share of contested rows on fold+overflow | 45% | **79%** |

**It is worth LESS where more of the residue is out of its reach**, which is the
mechanism rather than a coincidence: the frozen corpus is denser, hits the entry cap
more often, and puts 79% of its contested rows on the two surfaces this rung
structurally cannot touch. The ordinary-row resolution rate is the stable quantity
(37.6% against 30.6%); the headline delta moves with composition, exactly as the surface
table in §6 says it should.

### The residual after the rung, classified the same way

Sampled crowds, 4,971 → 3,936 rows (97% coverage, same verdicts, not re-probed):

| verdict | outcome | rows before | **rows after** | share after |
|---|---|---|---|---|
| `interchangeable` | **(1)** | 1,634 | **1,490** | **37.9%** |
| `page` | **(3)** | 1,068 | **995** | **25.3%** |
| `ours-optin` | (2) | 352 | 346 | 8.8% |
| `ours-elsewhere` | (2) | 573 | **294** | 7.5% |
| **`ours-absent`** | **(2)** | 1,075 | **581** | **14.8%** |
| `ours-devkey` | (2) | 16 | 2 | 0.1% |
| `unresolved` | — | 253 | 228 | 5.8% |

| outcome | before | after |
|---|---|---|
| **(1)** acting on any member does the same thing | 32.9% | **37.9%** |
| **(2)** declared, not printed | 40.6% | **31.1%** |
| **(3)** nothing the document declares separates them | 21.5% | **25.3%** |

**The tighter bound's residual is LESS sharp, not more**, which is the answer to "a
tighter bound whose residual is mostly interchangeable rows is a different result from
one whose residual is sharp". Every class that could be a gap of ours shrinks — most of
all `ours-elsewhere`, which halves (573 → 294), because "printed on another row" very
often meant "printed as my own children". **`ours-absent` falls from 1,075 rows to 581 —
from 2.7% of all actionable rows to 1.46%.**

### So the slack is now two lines instead of one

* **The container half: measured at 2.61pp.** The bound is **10.1%**, not 12.7%, and
  what remains of that half is 1,726 contested ordinary rows.
* **The fold half: still refused, in the same words.** 2,305 of the 4,031 rows still
  contested (**57%**) sit on a fold or the overflow list. The only reader-side
  discriminator there is pairing two sibling folds BY INDEX, and #27 and #30 both
  measured that silently mispairing everything after a gap. Crediting it would buy a
  smaller number by asserting something the project has already measured as unsafe, so
  it is not credited and this half of the slack stays **named and unmeasured**.

**What this does not become.** 10.1% is still an upper bound, now with a known interior:
one half priced, one half declined for a reason rather than for lack of effort. And the
rung is a MEASUREMENT, not a proposal — nothing is recommended for the product here, for
the same reason §9 recommends nothing: the residue it would address is 1.46% of rows and
most of it is on surfaces a per-row field cannot reach.
