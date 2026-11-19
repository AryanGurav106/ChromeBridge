# The name axis after an interaction — and the premise of the question was wrong

**Probe:** `tools/audit_name_correctness.py` (extended: `--stage-report`, per-read
`by_pop` / `synth_map`, stage-attributed `--candidate-ab`)
**Driver reused verbatim:** `tools/audit_stage_generality.py` (#89)
**Collector under test:** `_collectInteractivePage`, extracted verbatim from
`extension/background.js` at `58fb1d9` (post-#114)
**Baseline artefact:** `temp/name_correctness/full108/pass0.json` (#108, post-#93, pre-#114)
**Date:** 2026-11-19

> **The headline is a correction, and it is the most useful thing here.** #112 and
> `STAGE-GENERALITY-2026-11b.md` both say `audit_name_correctness.py` "runs at first paint
> only" and name a post-interaction name run as the highest-value next step. **It has never
> run at first paint only.** Its own docstring gives post-interaction evidence as the reason
> it exists; it imports `audit_stage_generality`'s driver verbatim; #93 published a by-stage
> table over **329 post-interaction reads**; and the run behind the 0.9766 headline (#108)
> has **333 post-interaction reads** across s1–s4. The claim was asserted about a sibling
> instrument that the paper making it had not run, and it reached CLAUDE.md and a task brief
> within hours. PRINCIPLES §V: *when an entry names a file, function or flag, verify it
> still exists before recommending it.*
>
> **What was genuinely missing is narrower and was worth doing.** The published stage table
> pools every `src`, so the statistic the headline quotes — `src=name` — had never been read
> per stage. Both the stage gradient and the revealed-vs-carried comparison were **pooled
> across sites**, which is the one shape that cannot answer either question. And `new` vs
> `carried` was never split by `src` at all, so the headline population had never been
> compared between revealed and carried controls.
>
> **Both pooled effects are composition, and pairing dissolves both.** The `src=name` rate
> appears to decline s0 **0.9399** → s3 **0.9087**; paired within a site (its own s0 against
> its own deepest read) the median difference is **+0.0000** and **59 of 81 sites are
> identical to the digit**. #93's open question — are revealed controls named worse? — is
> **settled as NO, and the direction is the opposite**: on the headline population a
> revealed control agrees with Chrome **0.9648** against a carried control's **0.9171**
> (replication: 0.9913 against 0.9223, both arms restricted to post-interaction reads), and
> no paired cut has it worse. The pooled appearance of "worse" is NOT a `src` mix — the
> proportions are 21.8% against 23.4% — it is the `chrome-empty` floor inside the TEXT arm,
> **87% of the revealed disagreements there**.
>
> **ONE name fix of four is worth more after an interaction — and reading the rate alone
> would have claimed three.** Both arms on the same page load against one AX read, on the
> sites that carry each shape: #93's slot fix improves **12.55 rows per 1,000 at first paint
> and 35.62 at s4, 2.84x**, with its COUNT rising 13 → 28 as the denominator falls. The
> other three only look like they rise: `labelledby-non-html` improves a flat 9/9/8/8 while
> `compared` shrinks 464 → 120, `live-label-not-clone` puts 16 of 31 at one depth on one
> site, and `br-is-a-separator` is a first-paint fix. `BREAKS_A_CORRECT_NAME` is **0 in
> every cell**, from a counter #114 showed firing at 2.
>
> **The new defect class is #34's gap in its degenerate case, and half of what looks like
> it is not ours.** `ours-empty` runs 1.91x post-interaction — but ~half of those rows are
> ones where Chrome's "name" is a Private-Use-Area icon glyph or the literal string
> `undefined`, where we are right to print nothing. The real half is
> `<wa-button><wa-icon aria-label="Search">`: AccName 2F takes a descendant's **NAME**, we
> concatenate descendant **TEXT**, and there is no text. Reproduced live. For **9 of 24 on
> `wc_webawesome` the name is in the listing nowhere at all** — live instances of the blind
> spot #112 demonstrated on a fixture.

---

## 1. The premise, checked before anything was measured

The task was framed on two sentences:

> `STAGE-GENERALITY-2026-11b.md` §"Next": *"a post-interaction run of the **name** rulers,
> since both of them currently measure first paint"*
>
> CLAUDE.md #112: *"`audit_name_correctness.py` and `measure_findability.py` both run at
> first paint only. A post-interaction name run is the highest-value next step."*

Four independent checks, each a measurement rather than a reading:

| check | result |
|---|---|
| the probe's own docstring | *"no post-interaction evidence at all, which is exactly the regime #89/#92 showed matters"* — it names that as its reason for existing |
| what it imports | `import audit_stage_generality as ASG  # (the interaction driver)`; `STAGE_PICK` / `_act` / `STAGE_VERIFY` used in four call sites |
| what #93 published | a `### By stage` table, s0–s4, and `580 reads (329 post-interaction)` |
| what the #108 artefact contains | reads by stage `{s0: 256, s1: 156, s2: 83, s3: 54, s4: 40}` — **333 post-interaction** |

So the probe has driven interactions since the day it was written, and the run behind the
0.9766 headline was staged. The sibling claim is half-true in a way that is also misleading:
`measure_findability.py` is first-paint, but `measure_findability_at_stage.py` exists and
#92 ran it over 254 sites and 327 post-interaction reads.

**The lesson is not that the paper was careless.** `STAGE-GENERALITY-2026-11b.md` is
unusually rigorous about the limits of its *own* instrument — it converted a one-line
disclaimer into a demonstrated control pair, and printed a coverage table showing only 1 of
13 collector hunks was within its reach. The false claim is about the instrument it did
**not** run. A probe's capabilities are checkable in one grep, and a paper that demonstrates
its own blind spot can still assert a neighbour's.

---

## 2. What was actually missing, and what was built

Three shapes made the real questions unanswerable. None of them is a sample problem.

| | the shape | why it cannot answer |
|---|---|---|
| 1 | `per_stage` rolls up `counts`, which **pools every `src`** | the headline is `src=name`; `src=text` is a weaker claim the legend spells out, and Chrome has no name for most roles that carry it. A pooled stage table moves with the text/name MIX |
| 2 | `new` vs `carried` is **pooled over every site and read** | the arms are two different mixtures of pages, so one large site dominates both |
| 3 | `new`/`carried` is **not split by `src`**, and its class breakdown comes from the **capped** `rows` head slice | the headline population had never been compared between arms, and a mechanism's absence at s0 was unfalsifiable |

Added to the probe, reusing rather than forking (PRINCIPLES 17):

* per-read `by_pop` — `pop × src × class`, **exact and uncapped**;
* `per_stage_src` and `per_pop_src` rollups, so the stage table and the population table
  come from the same place as every other number;
* `paired_reads` — both arms from **one read of one page**, so site composition, page
  weight and the depth a site reached cancel by construction rather than by argument;
* stage attribution inside `--candidate-ab`, so a fix's value can be read per stage;
* `synth_map` — name provenance per element across reads, for `OPEN.md` item 21;
* `--stage-report`, so all of it is re-derivable from a saved artefact.

Sample, exclusions, out-of-sample guard, collector extraction, interaction driver,
visibility rule and the no-spoofing rule are all inherited unchanged.

---

## 3. Proving the comparator fires

`--selftest`: **PASS**, `failures: []`. The planted arm moves an element's `aria-label`
after collection so the join-and-compare path is proven end to end independently of what
the collector does: **8 planted, 8 reported**, each disposed as
`compared:disjoint:SENTINEL`. The fixture's one genuine disagreement is `chrome-superset`
(#34's known class, Chrome absorbing a descendant's name).

`fmt_drift = 0` and `ax_failures = 0` on every run below. A non-zero `fmt_drift` means the
probe's restatement of the identity precedence has drifted from `_fmtLine` and the numbers
are void; it is checked on every row.

---

## 4. Results — `src=name` per stage

256 of 265 candidates usable, **600 reads, 344 of them post-interaction**, 103,223 rows
compared against Chrome's AX tree, `fmt_drift = 0`, `ax_failures = 0`.

| stage | reads | `src=name` compared | exact | **pooled** | **per-site median** | sites n>=20 | `src=text` agree |
|---|---|---|---|---|---|---|---|
| s0 first paint | 256 | 9,416 | 8,850 | **0.9399** | **0.9815** | 129 | 0.7459 |
| s1 | 161 | 5,635 | 5,221 | **0.9265** | **0.9791** | 86 | 0.6986 |
| s2 | 86 | 3,305 | 3,027 | **0.9159** | **0.9853** | 56 | 0.6664 |
| s3 | 55 | 1,906 | 1,732 | **0.9087** | **0.9938** | 36 | 0.7056 |
| s4 | 42 | 1,505 | 1,380 | **0.9169** | **1.0000** | 28 | 0.7075 |

**The two columns point in OPPOSITE directions, and that is the finding.** Pooled, the rate
falls 3.1 points from s0 to s3. Per site — the statistic the project's headline actually
quotes, because #93 measured a 7pp pooled-vs-median gap from composition alone — it
**rises**, to 1.0000 at s4. Pooled replication (`--every 2`, 130 sites): 0.9448 / 0.9372 /
0.9202 / 0.9086 / 0.9346, the same shape.

### The disagreement classes per stage, exact and uncapped

| stage | disagree | chrome-empty | disjoint | ours-superset | chrome-superset | partial-overlap | punctuation-only | case-only |
|---|---|---|---|---|---|---|---|---|
| s0 | 566 | **252** (44.5%) | 170 | 74 | 29 | 16 | 20 | 5 |
| s1 | 414 | **226** (54.6%) | 97 | 50 | 19 | 13 | 4 | 5 |
| s2 | 278 | **157** (56.5%) | 45 | 45 | 17 | 6 | 5 | 3 |
| s3 | 174 | **91** (52.3%) | 19 | 42 | 15 | 3 | 1 | 3 |
| s4 | 125 | **85** (68.0%) | 12 | 9 | 14 | 2 | 1 | 2 |

`chrome-empty` — Chrome's role forbidding a name while we print the author's string, which
#114 measured as 51% of the whole residue and #74 requires us to keep doing — **rises from
44.5% of the disagreements at first paint to 68.0% at s4**. So the deeper a page is driven,
the more of what is left is the permanent floor rather than anything that could be fixed.
`disjoint`, the class with real defects in it, falls 170 → 12.

### The headline did not move, which #114 predicted in advance

| run | per-site median `src=name` | sites |
|---|---|---|
| #108, pre-#114 | 0.9766 | 168 |
| this run, post-#114 | **0.9749** | 170 |
| replication | **0.9793** | 86 |

#114 predicted *"0.9766 will not visibly change"*, because the defects it fixed are
concentrated on a handful of sites and a median over 168 cannot move on ~100 rows. The
three figures straddle each other within #93's back-to-back drift floor of 0.0015 pooled.
**A change that HAD moved the median would have been changing something other than a
defect** — which is #114's sentence, now with the post-fix measurement behind it.

---

## 5. The stage gradient is COMPOSITION — paired per site, it is zero

Deeper stages are reached by fewer and different sites, so the stage column changes the
sample as it goes. Pairing a site against **itself** — its own s0 against its own deepest
read, so only sites that reached that depth contribute to both arms — removes that:

| | main run | replication |
|---|---|---|
| sites with >=20 `src=name` rows at both ends | 81 | 38 |
| deeper read BETTER | 13 | 6 |
| s0 better | 9 | 2 |
| **identical** | **59** | **30** |
| **median difference** | **+0.0000** | **+0.0000** |
| mean difference | −0.0002 | +0.0000 |

**59 of 81 sites, and 30 of 38 on the replication, are identical to the digit**, and the median difference is zero on both
runs. The pooled decline is which sites reach which depth, not names getting worse as a
page is used. The largest individual falls are small and site-specific (`w2_seoul`
0.576→0.500 at s1, `w2_admin_ch` 1.000→0.963 at s2).

---

## 6. #93's open question, settled: a revealed control is NOT named worse

#93 asked whether a control that exists only because of an interaction is named worse, got
**0.6628 against 0.7370**, said most of it was probably composition, and could not settle
it — a 34-site rerun with corrected code reversed the sign. `MEASUREMENT.md` carries it as
one of the seventeen ways an instrument here has lied.

**Paired within ONE read of ONE page**, so composition cannot enter:

| | all `src` | **`src=name`** |
|---|---|---|
| reads with >=10 / >=5 rows in both arms | 75 | 27 |
| revealed BETTER | 40 | **11** |
| carried better | 35 | **3** |
| identical | 0 | 13 |
| median paired difference | +0.0156 | +0.0000 |
| sign test | p = 0.6445 | p = 0.0574 |
| pooled over those reads, revealed | 0.6703 | **0.9774** |
| pooled over those reads, carried | 0.7042 | **0.8887** |

And the **exact, uncapped** population x src join, which no earlier run could produce.
**Restricted to post-interaction reads on BOTH arms** — `new` only exists there, so letting
`carried` keep its s0 rows would compare a post-only arm against one containing first
paint, which is the composition error this whole section is about. (My first version of
this table did exactly that; correcting it made the gap larger, not smaller.)

| population | src | compared | exact | agree | top disagreement classes |
|---|---|---|---|---|---|
| `new` (revealed) | **name** | 681 | 657 | **0.9648** | chrome-empty 14, chrome-superset 4, disjoint 3 |
| `carried` | **name** | 11,670 | 10,703 | **0.9171** | chrome-empty, disjoint, ours-superset |
| `new` (revealed) | text | 2,439 | 1,523 | 0.6244 | **chrome-empty 800**, punctuation-only 80 |
| `carried` | text | 38,103 | 26,550 | 0.6968 | **chrome-empty**, punctuation-only |

Replication (130 sites, same restriction): `new|name` **0.9913** against `carried|name`
**0.9223**.

**The answer is NO, and the mechanism is complete.** On the population the headline quotes,
a revealed control is named **better** than one that was already there — **+4.8pp** on the
main run, **+6.9pp** on the replication, same direction in both, and never worse in any
paired cut.

**It is NOT a `src` mix effect**, which was my first explanation and is refuted by the same
table: `src=name` is **21.8%** of the revealed rows and **23.4%** of the carried ones —
near-identical proportions. The pooled "worse" comes from inside the TEXT arm, where
revealed rows run 0.6244 against carried 0.6968, and **`chrome-empty` is 87% of the
revealed disagreements there** (800 of 916) against 77% of the carried ones. Revealed
content sits disproportionately inside the generic containers Chrome's role rules forbid
naming, where our row prints the author's own string. #114 measured that class as **51% of
the whole `src=name` residue**, and #74 is the proof that printing nothing there is the
worse error. So the one population where the pooled figure looked like a defect is the one
where the disagreement is most often not a wrong name at all.

Why would a revealed control be named *better*? Because what an interaction reveals is
mostly a menu item, a dialog button or a tab panel — declared controls a design system
labels — while the carried population at a post-interaction read still contains every
generic wrapper on the page.

## 7. Where the name fixes actually pay — and only ONE of them pays post-interaction

`--candidate-ab` runs both collectors on the **same page load** against **one** AX read, so
drift is removed by construction. One candidate at a time (`--ab-only`), because all five
candidates are already shipped and moving them together would isolate none of them. For
every one of the five the candidate arm is **asserted** to equal the shipped source and the
base arm is the reconstructed pre-fix state, so these runs measure what the fix bought and
cannot expire the way `MEASUREMENT.md` records for `audit_retext_*`.

**The prevalence arm found nothing, and that is a sample artefact rather than a result.**
On `--every 3` (89 sites) `contents-is-not-invisible` changed **0 names across 31,504
compared rows and all five stages**. The stride excludes `wc_webawesome`, `gov_au`,
`w2_nationwide`, `w2_jr_west` and `w2_onlinebooks` — i.e. most of the sites that carry the
shapes these fixes exist for. #114 recorded this exact trap ("the random `--every 3` subset
excludes `w2_nationwide` and `wc_webawesome`, which carry the heaviest instances"), so both
arms are reported: the stride is prevalence, the targeted run is concentration.

**Targeted, on the sites that carry each shape:**

| candidate | sites | improved | regressed | **breaks a correct name** | chars |
|---|---|---|---|---|---|
| `contents-is-not-invisible` (#93, slots) | 6 | 108 | 99 (all `chrome-empty`) | **0** | +0.80% |
| `live-label-not-clone` (#114) | 9 | 31 | 10 (all `chrome-empty`) | **0** | +0.07% |
| `labelledby-non-html` (#114) | 4 | 34 | 0 | **0** | +0.11% |
| `br-is-a-separator` (#114) | 5 | 12 | 0 | **0** | +0.03% |

Every "regression" is a row where Chrome's role permits no name and ours moved from `''`
or a wire key to the page's own label, which is #114's split and #74's requirement.

**Both arms independently reproduce #114's published numbers, which is worth more than
either on its own** — a different day, a different site subset, and the stage attribution
added:

| candidate | arm | this run | #114 as published |
|---|---|---|---|
| `live-label-not-clone` | targeted | 41 changed, **31** improved, 10, 0 breaks | 41 changed, **31** improved, 10, 0 breaks |
| `live-label-not-clone` | stride | 12 improved, 10 regressed | 12 improved, 10 (`chrome-empty`) |
| `labelledby-non-html` | stride | **2** improved, 0 regressed | **2** improved, 0 |
| `br-is-a-separator` | stride | **5** improved, 0 regressed | **5** improved, 0 |

Every one of the three stride arms #114 published reproduces to the digit, and the targeted
row matches on a **9**-site subset against #114's 14 — which means both subsets contain all
the carriers, the concentration #114 described, confirmed from the outside. The stride arm
for `br-is-a-separator` also puts 4 of its 5 improvements at s0, agreeing with the targeted
run that it is a first-paint fix.

### By stage — and the count matters as much as the rate

| | s0 | s1 | s2 | s3 | s4 |
|---|---|---|---|---|---|
| **`contents-is-not-invisible`** improved | 13 | 12 | **27** | **28** | **28** |
| per 1,000 compared | 12.55 | 10.95 | 29.97 | 30.04 | **35.62** |
| `labelledby-non-html` improved | 9 | 9 | 8 | 8 | — |
| per 1,000 compared | 19.40 | 18.87 | 38.65 | **66.67** | — |
| `live-label-not-clone` improved | 7 | 4 | 4 | **16** | 0 |
| per 1,000 compared | 2.26 | 1.69 | 1.77 | 20.73 | 0.00 |
| `br-is-a-separator` improved | **9** | 1 | 1 | 1 | — |
| per 1,000 compared | 14.11 | 8.47 | 10.75 | 10.75 | — |

**Only `contents-is-not-invisible` has a genuine post-interaction premium**, and reading
the rate alone would have claimed three. The distinction is whether the **count** moves:

* **the slot fix** improves 13 rows at s0 and **28** at s4 — more slotted controls EXIST
  once you have opened things — while the denominator *falls* 1,036 → 786. Both halves push
  the same way, giving **2.84x per row**. That is #93's 2.8x hypothesis confirmed by direct
  measurement of the fix rather than by the footprint of the class it removes.
* **`labelledby-non-html`** improves 9, 9, 8, 8 — a flat count. Its rate triples only
  because `compared` shrinks 464 → 120. These are the same few `<svg aria-labelledby>`
  icons re-measured at every stage, not new ones appearing. **The rate is an artefact of
  the denominator and the fix has no stage effect.**
* **`live-label-not-clone`** is lumpy: 16 of its 31 improvements land at s3 and none at s4.
  That is one site revealing a radio group at one depth, which is a SITE effect wearing a
  stage effect's clothes.
* **`br-is-a-separator`** is the opposite — 9 of 12 at first paint. It is a first-paint fix.

So the answer to "do these fixes pay more where they fire?" is **one yes and three no**,
and the one yes is the fix whose mechanism predicted it: a design system renders its
slotted controls when you open something. #114's three fixes are concentrated by SITE, not
by STAGE — which is consistent with #114's own finding that they move 8 of 81, 1 of 82 and
3 of 82 sites.

**`BREAKS_A_CORRECT_NAME` is 0 in every cell of every table above.** That zero is a
measurement rather than a silence: #114 planted it against a sabotage candidate that
discards every wrapping-label name and it **fires at 2**.

## 8. A defect class that concentrates after an interaction — and half of it is not ours

Nobody had looked for a disagreement SHAPE that only appears post-interaction. The rate
tables above cannot show one: a brand-new mechanism with 40 instances moves a rate by
nothing while being exactly the thing worth finding. Counted from the **uncapped**
`cls_roles` histogram (class x Chrome-role x src) rather than the capped `rows` head slice,
as a rate per 10,000 compared rows:

| class \| Chrome role \| src | s0 /10k | post /10k | ratio |
|---|---|---|---|
| `chrome-empty\|radio\|name` | 0.00 | 5.11 | **inf** |
| `chrome-superset\|cell\|text` | 1.65 | 5.84 | 3.54x |
| `chrome-empty\|group\|text` | 3.51 | 11.86 | 3.38x |
| **`ours-empty\|button\|unlabeled`** | **4.75** | **14.96** | **3.15x** |
| `punctuation-only\|button\|text` | 24.57 | 73.91 | 3.01x |
| `chrome-empty\|image\|name` | 15.90 | 44.53 | 2.80x |

`ours-empty` — we produce NO name where Chrome produces one — is the one worth chasing,
because it is the only shape here where the row an agent reads says `(unlabeled)`.
Overall it runs at **0.099% at s0 and 0.190% post-interaction, 1.91x**.

### Half of `ours-empty` is a row where OURS IS BETTER

Chasing the saved rows to their mechanism splits the class cleanly, and the split matters
more than the count:

| | s0 | post |
|---|---|---|
| **Chrome's name identifies NOTHING** | 17 | 36 |
| **a real name we missed** | 20 | 34 |

The first bucket is two mechanisms, both of which we handle correctly and the metric
penalises:

* `w2_alrajhi` (37 rows) — an icon-font button. Chrome's name is `'\ue9e7'`, `'\ue904'`,
  `'\ue903'`: a **Private-Use-Area glyph** generated by `::before` on
  `<span class="arb-font-icon arb-icon-minus">`. It identifies nothing. #114 measured the
  same shape at 16% of its class F and concluded that following the spec there would
  destroy a real identity.
* `w2_trenitalia` (8 rows) — `<button aria-label="undefined">`, a template bug on the page.
  Chrome's name is the literal string `undefined`; we print nothing, which is right.

### The real half: AccName 2F takes a descendant's NAME, we take its TEXT

The 54 real misses are 70% on two web-component sites (`wc_webawesome` 38, `gov_au` 6).
Reproduced live rather than inferred — the shipped collector, one page, Chrome's own AX
tree:

```html
<wa-button>                                   <!-- the host, light DOM -->
  <wa-icon label="Search" aria-label="Search" name="magnifying-glass"></wa-icon>
</wa-button>
  shadowRoot:
    <button part="base button" mmid="107">    <!-- the row we print -->
      <slot name="start"></slot><slot></slot><slot name="end"></slot>
```

`hostInnerText` is `''`, `hostTextContent` is `''`, and every slot's `assignedNodes`
contributes **no text at all**. There is no text anywhere. Chrome names the button
`Search` because AccName 1.2 step 2F says each child's contribution is its **NAME**, and
`<wa-icon>`'s name is its `aria-label`. **We concatenate descendant TEXT.**

So this is **#34's documented gap in its degenerate case** — recorded as a
characterisation since #34 and still unfixed — and what is new is that it is not uniformly
distributed. It concentrates on component libraries and its **rate is 1.50x higher after an
interaction** — count 20 -> 34 against denominators of 48,435 and 54,796, so the count
ratio of 1.70x overstates it — because a design system renders its icon buttons when you
open something. That is the same mechanism #93 identified for the slot defect, in a second
class.

### What it costs, measured rather than assumed

`lost_identities = 0` (#112) is CORRECT here and this is not a contradiction — that metric
asks whether a control owns a ROW, and #112 demonstrated it is blind to a missing NAME.
Asking where the name went, live, with composed-tree containment:

| | `wc_webawesome` | `gov_au` |
|---|---|---|
| unnamed by us, named by Chrome | 24 | 3 |
| the name is on a row **INSIDE** the control (a click bubbles) | 10 | 3 |
| the name is only on an unrelated row elsewhere | 5 | 0 |
| **the name is NOWHERE in the listing** | **9** | **0** |

So the cost is graded. For 10 of 24 the name sits on the `<wa-icon>` row nested inside the
button, so an agent that acts on it still hits the button — this is #93's
*"the words survive on a NEIGHBOURING row, attributed to a different control"*, arriving
from a third direction. **For 9 of 24 the name is in the listing nowhere at all**, and
those are live instances of exactly the blind spot #112 demonstrated on a fixture.

**NOT PROPOSED AS A FIX.** Making `_contentName` take a descendant's NAME rather than its
TEXT is #34, it is a change to the most load-bearing function in the collector, and
#41/#44's rule is that both halves are measured first. The honest statement is that the
class is now located, mechanised, and priced.

## 9. `OPEN.md` item 21, answered by its own falsifier

Item 21 records that `__abSynthAttr` is set at five sites in the collector and cleared at
none. It is a DOM expando, so a control read once before its label exists would keep
`(post-key)` for the life of that document — **a false provenance claim in the one field
whose purpose is provenance**, pointing the wrong way: it tells an agent to distrust a name
that is now authored and correct. The item asks for a prevalence number before anything is
changed, and names its own falsifier:

> *"if a corpus pass finds zero controls whose name provenance CHANGES between two reads of
> one document, this is a latent defect with no instances and should be recorded as such
> rather than fixed."*

**A staged run IS that pass** — the driver breaks on a url change, so every stage reads one
document. Per-read `synth_map` (marker plus the identity under it, keyed by mmid, kept only
for entries that carry a marker) over the 130-site replication:

| | |
|---|---|
| sites with >= 2 reads of one document | 82 |
| elements carrying a synth marker, seen at 2+ reads | **100** |
| **marker UNCHANGED while the name under it CHANGED** | **0** |
| marker itself changed between reads | 0 |

**Zero instances on a non-empty population of 100.** Item 21's falsifier fires: on this
corpus it is a latent defect with no instances, to be recorded rather than fixed.

**The limit is real and is the reason this does not close the item outright.** The
condition item 21 describes needs a label to ARRIVE between two reads, and a
declaration-driven interaction (open a menu, flip a tab) rarely causes that — an SPA
hydrating a form, or a field unlocking after another is filled, is the shape that would,
and this driver does not produce it. 100 repeat-seen marked elements is a small population.
So: **no instances found by the pass the item asked for**, not "the hazard does not exist".

**The denominator here is the whole point, and my first version of this check did not have
one.** It counted only CHANGES, so it printed `0` for both the numerator and the
population and read exactly like a fired falsifier while being vacuous — a count standing
in for an inventory (PRINCIPLES 16), in the check written to test somebody else's. The
`100` is what makes the `0` mean anything.

## 10. Mistakes made while measuring this

**1. A composed-tree containment walk that could not cross a slot, and it inverted the
conclusion.** Asking "is the missing name on a row INSIDE the unnamed control" first
returned **0 inside / 15 outside** for `wc_webawesome` — which would have made the defect
far more serious than it is. A slotted node's `parentNode` is the HOST, not the shadow
element it renders inside, so walking `parentNode` from the `<wa-icon>` goes
`wa-icon -> wa-button` and never reaches the `<button>` in the shadow root. `assignedSlot`
is the flat-tree parent. With it: **10 inside, 5 outside, 9 nowhere.** A damning number,
re-derived before it was believed (PRINCIPLES 8) — and the same composed-vs-node tree
confusion #37 records fixing in six walks inside `_treeLines`.

**2. Then the same check took only the FIRST row carrying the name**, so a row that
happened to share the string elsewhere on the page decided the verdict for a name that was
sitting inside the control all along. Fixed by asking whether ANY row carrying the name
(exact, then substring) is inside. That moved 9 inside to 10 and is why the table reports
`only-outside` separately rather than folding it into a single "recoverable" number.

**3. My item-21 check printed `0` for its own denominator.** It incremented only when
something CHANGED, so a corpus with 100 repeat-seen marked elements and no changes printed
`0` in both the numerator and the population — reading exactly like a fired falsifier while
being vacuous. That is a count standing in for an inventory (PRINCIPLES 16), in the check
written to test somebody else's unmeasured claim. The population is counted separately now,
and the falsifier only means something because it is 0 of **100**.

**4. My own population x src table compared a post-only arm against one containing first
paint.** `new` exists only after an interaction; `carried` was summed over every read,
including s0 where the rate is highest. That is the exact composition error sections 5 and
6 are about, committed inside the table written to settle it. Restricting both arms to
post-interaction reads moved the gap from +3.8pp to **+4.8pp** — the flaw was making the
result look WEAKER, which is the direction least likely to be noticed.

**5. The premise was checked before any of this was built, and it is the reason the rest
exists.** Taking "`audit_name_correctness.py` runs at first paint only" at face value would
have produced a re-run of a measurement already in the repo, reported as a first.

## 11. Sample, and what this cannot establish

**Chrome is an oracle, not ground truth.** A name both derivations get wrong scores as
agreement. #114 measured that **51% of the `src=name` residue is `chrome-empty`** — rows
where Chrome's ROLE forbids a name and we print the author's own string, which #74 proves
is the better error. A change that raised the rate by deleting those names would be a
regression whatever the number said, which is why every A/B below is split on whether
Chrome has a name at all and carries a `BREAKS_A_CORRECT_NAME` counter.

**The sample is inherited and survivorship-biased.** The pool is #85's `usable85` — the
sites that rendered in its final run, screened from 445 candidates — so roughly 180 a
headless browser could not reach are absent before this starts, 112 of them behind a
consent wall or a bot block. **No user-agent spoofing and no bot-check evasion**; a refused
site is UNMEASURED and named, never a pass.

**One path per site, declarations only.** The driver picks an interaction only from what
the page declares (`aria-expanded`, `aria-haspopup`, `aria-controls`, `role=combobox`,
`<details>`) and counts a stage only when the page's own declared state FLIPPED. Hover-only
menus declare no state on their trigger and are structurally unpickable; logins, paywalls
and cross-origin frames are not reached. Depth is not uniform — the deepest tier rests on
the few sites that offer four declared things in a chain.

**Cross-run comparisons are not causal.** Where a class rate here is set beside #108's, the
two runs are on different days and a live-web drift floor applies (#112 measured p90 3.06%
on listing characters with the code held constant). **Only the A/B is causal**, because both
arms are `page.evaluate` calls milliseconds apart on one DOM scored against a single AX
read — that design removes drift rather than bounding it.

**Nothing here says whether a name is USEFUL**, only whether it is the one the browser
computes. #75 tried to measure usefulness and found the benchmark substrate could not carry
the question.

---

## 12. Reproducing

```bash
# the firing proof
python tools/audit_name_correctness.py --selftest

# the staged run (this paper's main artefact)
python tools/audit_name_correctness.py --pool usable85 --conc 6 --stages 4 \
    --examples 60 --out temp/name_at_stage/main

# every table in this paper, from a saved artefact
python tools/audit_name_correctness.py --stage-report temp/name_at_stage/main/pass0.json

# one fix isolated, both arms on the same page load, attributed per stage.
# --every 3 is the PREVALENCE arm and it excludes every carrier site, so it reads 0
# for a fix that works; --only is the CONCENTRATION arm and is where the numbers are.
python tools/audit_name_correctness.py --candidate-ab --ab-only contents-is-not-invisible \
    --every 3 --conc 6 --stages 4 --out temp/name_at_stage/ab_contents-is-not-invisible
python tools/audit_name_correctness.py --candidate-ab --ab-only contents-is-not-invisible \
    --only wc_webawesome gov_au wc_salesforce wc_lit wc_spectrum w2_nationwide \
    --conc 4 --stages 4 --out temp/name_at_stage/abt_contents-is-not-invisible
```

The probe's own `--selftest` is the comparator's firing proof; `--fire` repeats the plant
on live pages at the deepest stage reached. The A/B arms are bidirectional — each candidate
carries both anchors and the direction is taken from the source — so these commands keep
working after the fixes ship, which is the trap `MEASUREMENT.md` records
`audit_retext_*.py` falling into.

## 13. What this establishes

**Establishes.**

1. **A correction.** `audit_name_correctness.py` has never run at first paint only; the run
   behind the 0.9766 headline carries 333 post-interaction reads. #112 and
   `STAGE-GENERALITY-2026-11b.md` both say otherwise and both should be amended.
2. **The headline statistic per stage**, which had never been read: `src=name` 0.9399 /
   0.9265 / 0.9159 / 0.9087 / 0.9169 across s0–s4, replicated on an independent subset.
3. **The apparent decline is composition.** Paired per site, 59 of 81 are identical to the
   digit and the median difference is +0.0000.
4. **#93's open question is settled, in the opposite direction.** On the headline
   population a revealed control agrees with Chrome **0.9648** against carried **0.9171**
   (replication 0.9913 / 0.9223, both arms post-interaction only), and no paired cut has it
   worse. The pooled "worse" is the `chrome-empty` floor inside the TEXT arm — 87% of the
   revealed disagreements there — and NOT a `src` mix, which is 21.8% against 23.4%.
5. **One fix of four has a real post-interaction premium**, measured both arms on one page
   load: the slot fix at **2.84x per row**, count rising 13 → 28 while the denominator
   falls. The other three are concentrated by SITE, not by stage, and reading rates alone
   would have claimed three.
6. **`BREAKS_A_CORRECT_NAME` = 0** in every cell of every A/B table — from a counter #114
   planted against a sabotage candidate and showed firing at 2, so the zero is a
   measurement rather than a silence.
7. **`OPEN.md` item 21's falsifier fires**: 0 provenance changes over 100 repeat-seen
   marked elements.
8. **A located, mechanised defect class**: AccName 2F takes a descendant's NAME, we take
   its TEXT, so a `<wa-button><wa-icon aria-label="Search">` prints `(unlabeled)`. The
   count rises 20 -> 34 post-interaction, a **1.50x rate** once the denominator is taken
   into account (the distinction item 5 turns on). 70% on two component-library sites, and for **9 of 24 on
   `wc_webawesome` the name is in the listing nowhere at all** — live instances of the
   blind spot #112 demonstrated on a fixture.

**Does not establish.** That any of this transfers off the inherited, survivorship-biased
`usable85` pool; that a name both derivations get wrong is wrong; that the `ours-empty`
class is worth fixing (#34 is a change to the most load-bearing function in the collector
and #41/#44 require both halves measured first); or anything about hover-only menus,
logins, cross-origin frames or second paths through a site.

**The single thing I am least sure of** is the revealed-vs-carried *direction*. That
revealed controls are not named WORSE is solid — two independent subsets, paired within
read, and no cut going the other way. That they are named **better** rests on 681 and 461
`new|name` rows and a sign test at p = 0.0574 and p = 0.6875; neither clears 0.05. The
pooled gap is large and consistent, and the mechanism is plausible (an interaction mostly
reveals declared, labelled controls), but #93's history on this exact question — a sign
that reversed between two runs — is the reason to state it as "not worse, probably better"
rather than as a result.

---

## 14. Artefacts

| | |
|---|---|
| main staged run (256 sites, 600 reads) | `temp/name_at_stage/main/pass0.json` |
| replication + `synth_map` (130 sites) | `temp/name_at_stage/pass2/pass0.json` |
| targeted A/B, one per candidate | `temp/name_at_stage/abt_<candidate>/candidate_ab.json` |
| prevalence A/B (`--every 3`) | `temp/name_at_stage/ab_<candidate>/candidate_ab.json` |
| baseline, #108's run (pre-#114) | `temp/name_correctness/full108/pass0.json` |
