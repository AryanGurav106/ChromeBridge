# Findability at stage, re-measured after the name path moved

**Probe:** `tools/measure_findability_at_stage.py`, unchanged
**Successor to:** `docs/research/FINDABILITY-AT-STAGE-2026-11.md` → CLAUDE.md **#92**
**Collector under test:** `_collectInteractivePage` @ `fc1d1cf965345930`
(`extension/background.js` @ `13895f12be4b359c`, repo **`b5bb606`**)
**Baseline:** `temp/findability_stage/main/pass0.json` — #92's run, collector
`18548bf50abc20bd`, repo `07b80d3`
**Date:** 2026-11-19

> **Headline.** 265 candidates, **257 usable**, **596 reads of which 339 are after an
> interaction**, **14,071 printed-identity probes**: a control the listing prints is
> reachable by the identity it printed **13,966 / 13,966 = 1.0000**, with **zero**
> descendant credit, **zero** ancestor credit, **zero** weak-tier hits and **zero** misses.
> Per-site median 1.0000, and **all 257 sites score 1.0000**. 95% upper bound on the miss
> rate (rule of three) **≤ 0.000215**.
>
> **Against #92, site by site over the 251 overlapping sites: 251 identical, 0 improved,
> 0 regressed.** Nothing that was reachable before is unreachable now.
>
> **The blanked population moved, slightly, in both directions**: its share of entries rose
> 10.208% → 10.379% over the overlap and its weaker descendant question fell
> 0.8908 → 0.8866. Both are small, both sit above the only floor available, and **that floor
> is back-to-back while this comparison is a day apart**, which is the weaker footing. The
> causal A/B (§7) is what attributes them.
>
> **The baseline is older than the brief assumed**: five name-path commits separate it from
> HEAD, not four, and **two of them change the printed identity STRING itself** rather than
> only whether a name exists. One of those is visible in #92's own quoted symptom, which no
> longer reproduces verbatim.

---

## 1. Why this was re-run, and a correction to the premise

#92 measured whether `find` can reach a control by the identity the **listing printed**
for it, after the page has been interacted with: 254 live out-of-sample sites, 581 reads
of which 327 were post-interaction, **13,682 / 13,682 = 1.0000** with zero descendant
credit, zero ancestor credit and zero weak-tier hits.

#74 is why that ruler exists: 118 ptable.com tiles were present in **every** presence
metric this project has and unreachable by their own verbatim printed label. **Changing
what gets printed is exactly the change that can break it**, and the name path has moved.

### The brief said four changes; from this baseline it is five commits and eight defects

The task was framed as "#114 shipped three, #116 shipped a fourth". That is true of
*today*. It is not the span this comparison covers, because **#92's baseline predates
#93 as well**. Checked rather than assumed — `git log 07b80d3..HEAD -- extension/background.js`
is 16 commits, of which five are in the name path:

| commit | entry | what it changed in the name path |
|---|---|---|
| `72cca1c` | #93 | a slotted / `display:contents` label was invisible (`_namable` asked the BOX question of a boxless node); `title` consulted before `alt` on the same element |
| `7a443db` | #93 | **the printed identity STRING**: `_fmtLine` emitted bare text by raw interpolation, so a label containing `"` arrived unparseable (Hebrew gershayim) |
| `0a35600` | #93 | **the printed identity STRING**: AccName 2F's child join made display-aware — inline children concatenate with no separator, block children with one |
| `58fb1d9` | #114 | wrapping-`<label>` name computed on a DETACHED clone; `aria-labelledby` resolved with `innerText`, which an SVG has none of; a `<br>` contributing nothing and fusing the lines either side |
| `b5bb606` | #116 | AccName 2F: an element child contributes its **NAME** (`_declName`, guarded), not its text — 159 rows changed name |

**Two of the five change the printed identity string itself**, not merely whether a name
exists. That is the sharper hazard for this ruler, and it is the one the brief's framing
did not name.

The other 11 commits are frames, click guards, readiness wording, `fill_form` and the flow
witness. The two cross-frame ones (`97efc75`, `c090dac`) are **inert here**: they fire only
through `collectCrossFrames`, which runs worker-side via `chrome.scripting` and is
unreachable from a `page.evaluate`.

---

## 2. What this measures, and what it cannot

**Measures.** For a control the listing prints, hand `find` the identity the listing
printed for that row and ask whether that same element comes back. Deliberately the
weakest question there is; a miss is unambiguous.

**Cannot answer** — each with its own instrument, see §8:

* whether the name is **right**. This scores `find` against the **collector**, so a name
  both of them get wrong scores as a hit. It sees an unreachable name, never a wrong one.
* whether a model then **picks** the row (#75 found the benchmark substrate cannot carry
  that question).
* hover-only menus, logins, paywalls, cross-origin frames (inherited from #89/#92).

---

## 3. Proving the ruler can fire, before any zero is believed

PRINCIPLES 5 and 15: a high score is worth nothing until the metric has been shown to
report a miss. Both proofs were run on **this** collector, not inherited from #92.

### `--selftest` — **PASS**, `failures: []`

Four checks, on a fixture driven through one real declared interaction:

| check | result |
|---|---|
| a control REVEALED by the interaction is reachable by its printed identity | hit |
| #74's **sole-carrier** shape, revealed by the interaction | hit |
| **the generic plant** — the same control with its identity moved off it | `cls: zero-match` |
| **#74's own defect reproduced** — `subtreeNameSole` stripped from the entry, which is the pre-#74 state reached without touching the extension | `cls: zero-match` |
| a blanked row is routed to its own question and never scored in the printed denominator | `b_desc: 1`, `tried` absent |

**The #74 reproduction is the one that matters**, and it carries a visible consequence of
`0a35600`: its recorded symptom is now

```
No elements matched "36KrKrypton83.798"
```

where #92's paper quotes `No elements matched "36 Kr Krypton 83.798"`. The tile's four
children (`<b> <abbr> <em> <data>`) are inline, so the display-aware join no longer
inserts separators. The check still fires; the **string it fires on has changed shape**.

### `--fire` — the live firing proof, **5/5 fired**

Drive the stages on a real site, then at the deepest stage reached move 8 controls'
identities off their elements — blanking them in the array `find` searches while keeping
the query the listing printed. The same five sites #92 used, so the entry counts are
comparable:

| site | stages | entries (#92) | clean hits | hits after the identity moved |
|---|---|---|---|---|
| gov_au | 1 | 131 (133) | 8/8 | **0** |
| leg_perldoc | 4 | 36 (36) | 8/8 | **0** |
| ko_daum | 4 | 1,752 (1,733) | 8/8 | **0** |
| wc_webawesome | 4 | 714 (714) | 8/8 | **0** |
| w2_unicode | 1 | 132 (132) | 8/8 | **0** |

A fixture is what you thought of; this is not. **So a zero on the intact pages is a
measurement rather than a silence.**

---

## 4. Method, inherited unchanged

Driver `audit_stage_generality` (#89) verbatim — declaration-only interaction tiers, the
flip rule, the excluded-host set, the sample pool. Metric `measure_findability` (#74)
verbatim. Two arms (`full` = what `find` really receives, `compact` = what the frozen
ruler feeds it) **on the same page load at the same stage**, so run-order drift cannot
align with an arm. Three populations: `s0`, `new` (identity string never seen earlier —
the control exists *because of* the interaction) and `carried`.

**Source pinning.** `extension/background.js` was hashed before the run
(`13895f12be4b359c`) and re-hashed after, so a concurrent editor could not have reached the
collector mid-run — #73's hazard, which #112 handled with a `git archive` shadow checkout.

---

## 5. Results

265 candidates, **257 usable**, four interaction stages each at most. **596 reads** — 257
at first paint and **339 after an interaction**. `bridge_races = 0` on every read, which is
the probe asserting that no site's query was ever scored against another site's entries.

### The headline

| | #92 (`07b80d3`) | **this run (`b5bb606`)** |
|---|---|---|
| sites usable / attempted | 254 / 265 | **257 / 265** |
| reads (post-interaction) | 581 (327) | **596 (339)** |
| entries collected | 162,457 | 160,962 |
| …of which the listing **blanks** | 16,397 (10.093%) | 16,620 (10.325%) |
| **printed-identity probes** | 13,797 | **14,071** |
| …contested (identity shared, excluded) | 7,175 (52%) | 7,335 (52%) |
| **reached by the identity the listing printed** | **13,682 / 13,682 = 1.0000** | **13,966 / 13,966 = 1.0000** |
| …needed descendant credit | 0 | **0** |
| …needed ancestor credit | 0 | **0** |
| …came back only in the weak `NO STRONG MATCH` tier | 0 | **0** |
| **misses** | 0 | **0** |
| probe errors | 0 | **0** |
| per-site median strict | 1.0000 | **1.0000** |
| sites scoring 1.0000 | 254 / 254 | **257 / 257** |
| unique-identities-only strict | 6,622 / 6,622 = 1.0000 | **6,736 / 6,736 = 1.0000** |
| 95% upper bound on the miss rate | ≤ 0.00022 | **≤ 0.000215** |

**Zero misses, in 14 script families and across 9 kinds of declared interaction.** Every
hit was in the confident tier; `find` never fell back to its weak list to return a probed
control.

### By stage — both arms, identical

| stage | probes | shared identity | **strict** | unique-only | miss | blanked probed | blanked unreachable |
|---|---|---|---|---|---|---|---|
| s0 first paint | 6,050 | 3,224 (53%) | **1.0000** (5,989/5,989) | **1.0000** (2,826/2,826) | 0 | 1,027 | 109 |
| s1 | 3,758 | 1,908 (51%) | **1.0000** (3,740/3,740) | **1.0000** (1,850/1,850) | 0 | 652 | 71 |
| s2 | 1,995 | 1,017 (51%) | **1.0000** (1,985/1,985) | **1.0000** (978/978) | 0 | 366 | 46 |
| s3 | 1,284 | 641 (50%) | **1.0000** (1,280/1,280) | **1.0000** (643/643) | 0 | 222 | 26 |
| s4 | 984 | 545 (55%) | **1.0000** (972/972) | **1.0000** (439/439) | 0 | 175 | 22 |

The `compact` arm is **identical to the digit** on the printed question at every stage, so
`detail="full"`'s extra media rows still cost a control nothing — #92's finding, reproduced.

Depth: 97 sites offered nothing the picker could act on declaratively, 76 reached one
interaction, 30 a second, 13 a third, **41 the fourth** (the cap) — against #92's
101 / 71 / 29 / 14 / 39.

### Is a control revealed BY an interaction harder to reach? Still no.

| population | probes | shared | **strict** | unique-only | miss | 95% upper bound |
|---|---|---|---|---|---|---|
| `s0` (first paint) | 6,050 | 53% | **1.0000** (5,989/5,989) | **1.0000** (2,826/2,826) | 0 | ≤ 0.000501 |
| **`new`** (exists only because of the interaction) | 1,967 | 50% | **1.0000** (1,962/1,962) | **1.0000** (988/988) | 0 | ≤ 0.001529 |
| `carried` (was always there) | 6,054 | 52% | **1.0000** (6,015/6,015) | **1.0000** (2,922/2,922) | 0 | ≤ 0.000499 |

### By script family

All 14 at **1.0000, zero misses, both arms**: latin-english 8,177 · latin-other 2,152 ·
kana+han 840 · han-trad 586 · cyrillic 360 · han-simp 336 · hangul 350 · hebrew (RTL) 252 ·
thai 232 · arabic (RTL) 188 · greek 146 · vietnamese 121 · bengali 119 · devanagari 107.

---

## 6. The blanked population, and a mechanism found while waiting

#74's rule blanks a row's printed identity when `subtreeName && !subtreeNameSole` — the
name is a concatenation of descendants' text and some of those descendants are themselves
kept entries. The listing prints **no identity**, so "can `find` reach it by the identity
the listing printed" has no question to ask; #92 routes those rows to a weaker one (does
asking for those words return this element **or anything inside it**) and scored 0.8916.

The brief asked whether the population's **size** moved, because a row that acquires a name
could acquire the flag with it. **It cannot, and the mechanism says so before the data
does.** Read at source: `subtreeName` (background.js:10354) counts *text-contributing*
children with `c.innerText || c.textContent` tested for a letter or digit. `_declName`
contributes a name for a child that has **no text**, so it cannot add a contributor and
cannot newly trip the flag. #116's own measurement agrees in direction: entries move
**+0.013%, upward**.

Confirmed causally on one DOM, both collectors in one evaluate:

| fixture | base @`07b80d3` | HEAD |
|---|---|---|
| `<div tabindex=0><span aria-label=Share></span><a>Open</a></div>` | `'Open'`, `subtreeName=false`, not blanked | `'ShareOpen'`, `subtreeName=false`, **not blanked** |
| `<div tabindex=0><a>Alpha Link</a><a>Beta Link</a></div>` | `'Alpha Link Beta Link'`, blanked | `'Alpha LinkBeta Link'`, **still blanked** |

So the rule's **membership** is stable. What moved is the **string**.

### The string change is a real mechanism for the blanked arm to fall

`0a35600` joins inline children with no separator, and the blanked arm's query is exactly a
container's concatenated child text. Fusing the last word of child N with the first word of
child N+1 produces a token that exists on no row. Measured, both collectors, one DOM, with
the block-children control in the same fixture:

| container | base @`07b80d3` query → | HEAD query → |
|---|---|---|
| three **inline** links | `'Products Pricing Support'` → reached (`b_desc`) | `'ProductsPricingSupport'` → **`blanked-text-no-match`** |
| two **block** links (the control) | `'Gamma Link Delta Link'` → reached | `'Gamma Link Delta Link'` → reached, **unchanged** |
| two inline links | `'Alpha Link Beta Link'` → reached | `'Alpha LinkBeta Link'` → reached |

The block row is what makes this attributable to the inline join rather than to anything
else in 16 commits.

**Three things keep this in proportion, and they are the honest part.**

1. **The fixture is the worst case.** It has no whitespace between tags, so the rendered
   text genuinely *is* `ProductsPricingSupport` and the collector is **right**. Real markup
   almost always has a newline between tags, which collapses to a space. Prevalence is what
   the corpus run prices, not this fixture.
2. **No agent sees this string.** A blanked row prints no identity, so the query is one
   #92 already describes as *"a string the listing never showed anyone"*. The child rows
   (`a "Products"`) are unchanged and are what an agent acts on.
3. **The printed arm is protected by construction** and the blanked arm is not: in the
   printed arm the query and the label are the same fused string, so an exact match still
   lands; the blanked arm needs a **descendant** to match a token taken out of the fused
   string.

---

## 7. Site by site against #92 — and the causal arm that attributes what moved

### The cross-run screen

Both artefacts were re-aggregated with the **current** `aggregate()`, never with the
`aggregate` block stored inside them: #92's run predates `printed_arm_totals`, so reading
the stored blocks would compare two definitions (PRINCIPLES 17). The re-derivation
reproduces every figure #92 published — 13,682/13,682, 0.8916, 16,397/162,457 = 10.093%,
240/17 — which is what licenses using it as a baseline at all.

| over the 251 overlapping sites | |
|---|---|
| **identical** | **251** |
| improved | 0 |
| **REGRESSED** | **0** |
| stage count differs | 8 |
| pooled strict, #92 → new | 13,497/13,497 = 1.0000 → **13,613/13,613 = 1.0000** |
| pooled blanked, #92 → new | 2,072/2,326 = 0.8908 → **2,104/2,373 = 0.8866** |
| blanked share of entries | 10.208% → **10.379%** |

Three sites usable in #92 are not usable now (`w2_budapest`, `w2_jakarta`, `w2_madrid`) and
six are usable that were not (`w2_buenosaires`, `w2_garanti`, `w2_gov_pl`, `w2_helsinki`,
`w2_kaist`, `w2_osu_courses`) — live-web reachability, not a result.

### The floors, derived from #92's own drift passes

#92 published only the printed-arm drift, which is 0.0000 **by construction** because both
passes sit at 1.0000 — #19's rule that a saturated metric cannot detect regression. Its two
back-to-back passes also carry floors for the two quantities that DID move, and nobody had
read them:

| quantity, 54 sites, code held constant | pooled \|Δ\| | per-site median / p90 / max |
|---|---|---|
| blanked-arm rate | **0.0008** | 0.0000 / 0.0000 / **0.3333** |
| blanked share of entries | **0.065 pp** | 0.000 / 0.354 / **5.264 pp** |

So the observed −0.0042 and +0.171 pp are 5× and 2.6× their pooled floors. **That
comparison is weaker than it looks and the weakness is the point**: those floors are
BACK-TO-BACK, while this comparison is a day apart, and #112 measured a day-apart listing
drift p90 of 3.06% against #89's back-to-back 0.72%. A back-to-back floor understates
cross-day noise. The per-site falls (`w2_mbta` 0.3334, `w2_nationwide` 0.5000) are at or
above a max the same code produced on itself.

**Which is why the cross-run table is a screen and not a verdict**, and why the next
section exists.

### The causal arm: both collectors, one DOM, one stage chain

Only the collector string differs — `_collectInteractivePage` extracted from
`07b80d3` (hash `18548bf50abc20bd`, **byte-identical to the one #92's paper names**)
against HEAD's `fc1d1cf965345930`. Both are evaluated on the same page at the same stage,
with the arm order **rotated per site** because the first collector to run stamps the
mmids. Sites chosen as the two biggest cross-run fallers plus four carriers of the name
changes.

| site | order | base strict | **head strict** | base blanked | **head blanked** | entries b/h |
|---|---|---|---|---|---|---|
| gov_au | base+head | 1.0000 (48/48) | **1.0000** (48/48) | 0/0 | 0/0 | 256/256 |
| wc_webawesome | head+base | 1.0000 (110/110) | **1.0000** (103/103) | 25/30 | 25/30 | 3616/3616 |
| w2_cour_cass | base+head | 1.0000 (72/72) | **1.0000** (72/72) | 15/18 | 15/18 | 634/634 |
| **w2_mbta** | head+base | 1.0000 (96/96) | **1.0000** (96/96) | **18/24** | **9/24** | 895/895 |
| **w2_nationwide** | base+head | 1.0000 (96/96) | **1.0000** (96/96) | **3/6** | **0/6** | 683/683 |
| w2_pko | head+base | 1.0000 (96/96) | **1.0000** (96/96) | 17/21 | 17/21 | 903/903 |
| **pooled** | | **518/518 = 1.0000** | **511/511 = 1.0000** | **78/99** | **66/99** | 6987 / 6987 |

**Three things this settles that the cross-run table could not.**

1. **The printed arm is 1.0000 under BOTH collectors on the same DOM.** No printed row
   lost its reachability to the collector change. That is causal, not inferred.
2. **The blanked-arm fall IS the collector**, and it reproduces the two cross-run fallers
   exactly — `w2_mbta` and `w2_nationwide`, with the other four sites byte-identical.
3. **The blanked population's SIZE is NOT the collector.** `entries` 6,987 and
   `blanked-entries` 273 are identical in both arms, which is the mechanism of §6 confirmed
   on live pages: `_declName` cannot add a text contributor, so it cannot newly trip
   `subtreeName`. The +0.171 pp in the cross-run table is live-web variance.

### The two mechanisms behind the blanked fall, read off the records

Both arms' miss records were kept, so the queries can be set side by side.

**`w2_mbta` — the inline join, §6's mechanism on a real page.** The base arm's query is
`'NOV 02'`; the head arm's is `'NOV02'`, `'NOV16'`, `'NOV05'`. A date chip renders its
month and day as inline children, so the display-aware join no longer separates them and
the container's concatenated name becomes one token that no descendant row carries.

**`w2_nationwide` — a different one: more competition in a bounded result list.** The query
is **byte-identical in both arms**
(`'Privacy Preference Center Notice of Right to Opt-Out of Sale'`) and the entry count is
identical, yet head misses twice per stage where base misses once. That leaves only the
search space's **names** — and rather than infer it, both collectors were run on that page
once more and the identities compared:

| `w2_nationwide`, first paint, same DOM | base @`07b80d3` | HEAD |
|---|---|---|
| entries | 159 | 159 |
| **rows carrying an identity of ≥2 chars** | **123** | **137** |
| identities that changed | — | 14 |
| …of those, rows that **gained** one (was empty) | — | **14** |

The 14 are `Twitter`, `LinkedIn`, `Instagram`, `YouTube`, `Facebook`, `Nationwide`,
`store outline` — icon controls that printed `(unlabeled)` and now carry the page's own
declared label. `find` returns a capped list, so 14 more named rows means 14 more
competitors for a blanked container's descendants.

**So the blanked arm got worse for a reason that is an unambiguous WIN on the printed
arm**, and the probe structurally cannot score it as one: a row whose identity is under
two characters is skipped by `choose()`, so those 14 were never in the base arm's
denominator to be counted as misses. This is precisely what #92's refusal to fold the two
arms into one number exists to prevent.

### Why neither costs an agent anything

**A blanked row prints no identity**, so this arm's query is one #92 already calls *"a
string the listing never showed anyone"*. The rows an agent acts on — the children, which
each carry their own ref and their own name — are untouched, and the printed arm measures
them at 1.0000 under both collectors. The honest statement is that **a proxy got harder,
not that reach was lost**, and the proxy got harder partly because the names it is built
from are now the ones Chrome computes.

---

## 8. Coverage: is every axis covered at every stage?

Asked because #112 demonstrated that `audit_stage_generality` is blind to the axis the
day's diff moved, and #115 then established that the name oracle had been running
post-interaction all along. **Verified at source rather than relayed** (PRINCIPLES §V).

### Which probe answers which question

| question | probe | drives interactions? | its own blind spot |
|---|---|---|---|
| does a rendered control own a **ROW**? | `audit_stage_generality` → `audit_generality_live` | yes — #112, 596 reads, s0–s4 | **the name ON that row** — demonstrated by #112 and re-verified at the line below |
| is the printed name the one **Chrome computes**? | `audit_name_correctness` | yes — #115, 344 post-interaction reads | **37.4% of the rows it meets**, and a name both derivations get wrong |
| can the printed name **REACH** the row? | `measure_findability_at_stage` | yes — this run | whether the name is **right**; blanked rows get a weaker question |
| is hover-revealed content collected and reachable? | `audit_hover_stage` | hover, #94 — 0 own no row, `find` 295/323 = **0.913** | whether the name is **right** — no oracle arm |

**The presence probe's blindness, re-verified at the line rather than quoted.** Both the
frozen probe (`tools/inspect_site.py:94-95`) and the live one
(`tools/audit_generality_live.py:659`) short-circuit on the mmid **before** the name test:

```js
const byRef = m && BLOB.indexOf('"' + m + '"') >= 0;
if (byRef) continue;
```

so an element that owns a row is never asked whether the name on it is right. The strict
arm asks only `rowIds.has(mm0)`. #112's demonstration is confirmed independently.

### What the name oracle cannot see, with numbers

From #115's artefact (`temp/name_at_stage/main/pass0.json`), rows the comparator met:

| disposition | rows |
|---|---|
| **compared** | **103,231** |
| `chrome-ignored` | 23,522 |
| `both-empty` | 14,492 |
| `not-in-ax-tree` | 12,662 |
| **`blanked-row` — excluded by the SAME rule findability uses** | **10,767** |
| …of those, rows **Chrome does have a name for** | **3,361** |
| `contents-only-row` | 157 |

So the only independent oracle in the repo compares **103,231 of ~164,831 rows = 62.6%**,
and the rest is structurally outside its reach.

### The answer

**Yes for the three axes the question names — presence, correctness and reachability are
each measured at every stage, by a different instrument, and the gaps between them do not
leave an axis uncovered. Two things do fall between, and neither is one of the three.**

1. **DISCRIMINATION is not measured at any stage.** `measure_sufficiency.py` is the only
   instrument for "is the target *distinguishable* from its neighbours", and it runs on
   Mind2Web — human-labelled actions on static snapshots with no CSS and no interactions.
   Its population is precisely the one every stage probe sets aside: **this run excludes
   7,335 of 14,071 probes (52%) as contested** because the identity is shared with another
   entry; the presence probe counts them present; and the name oracle can score both of a
   look-alike pair exact. A page after four interactions is where duplicate labels
   concentrate — a menu of nine `Remove` buttons — and nothing asks the question there.
   **This is the one I would build next**, because it is the only gap where all three
   existing instruments read clean on a listing that does not determine the action.
2. **NAME CORRECTNESS on hover-revealed content is unmeasured.** #94 drives hover and
   measures presence and reachability; the name oracle does not drive hover at all. A
   hover-revealed control with a *wrong* name would be reported 0-lost by #94, 0.913-ish
   reachable by #94, and never compared against Chrome.

Neither is a hole in this run; both are gaps in the set. Also outside all four probes, as
every one of them states: cross-origin frames, logins, paywalls, and the second path
through a site.

---

## 9. Sample, and what it cannot tell you

**8 of 265 candidates are UNMEASURED, not passed**, and all eight are named: five failed to
navigate (`w2_jakarta`, `w2_cdmx`, `w2_ccb`, `w2_nlc_cn` at the 45 s timeout,
`w2_seoul_metro` with `ERR_EMPTY_RESPONSE`) and three served fewer than five probeable rows
at first paint (`w2_extjs_ks`, `w2_madrid`, `w2_budapest`). **No user-agent spoofing and no
bot-check evasion**, so a site that declines automated traffic is simply absent.

**The large loss is inherited.** The pool is #89's, which is #85's screening of 445
candidates, so roughly 180 a headless browser could not reach are missing before this probe
starts — 112 of them behind a consent wall or a bot block (banks, ticketing, government
portals). **The sample is survivorship-biased toward simpler pages.**

**This probe SAMPLES, and that is the binding limit on its power.** 24 printed rows and 6
blanked rows per stage, stride-sampled across the entry list: **14,071 probes against
160,962 entries is 8.7%**. The name changes under test are *concentrated* — #116 moves 24
of 251 sites, #115 puts 70% of its class on two component-library sites — so a stride
sample of 24 rows per stage can miss a shape entirely. **That is the reason §7's targeted
A/B exists**, and it is why "0 regressions over 251 sites" should be read together with
"both collectors score 1.0000 on the same DOM" rather than on its own.

**Depth is not uniform.** 97 of 257 sites offered nothing the picker could act on
declaratively, so the post-interaction evidence rests on 160 sites and the deepest tier on
41.

**Within a site, one path.** A site whose interesting state is behind the *second* menu is
measured on the first.

**266 printed identities were skipped for length** (over 300 characters) and counted rather
than truncated, because a truncated query asks a different question and could manufacture a
false miss.

**Not reached at all**, inherited: hover-only menus (a CSS `:hover` submenu declares no
state flip, and PRINCIPLES 1 forbids picking it by class or position — #94 drives those
separately), cross-origin frames, logins, paywalls.

**And the question this cannot answer** is whether the name is RIGHT. It scores `find`
against the **collector**, so a name both of them get wrong scores as a hit. That is
`audit_name_correctness.py`'s question and §8's table says where it reaches.

---

## 10. Mistakes and near-misses while measuring this

**1. I nearly reported the brief's framing instead of checking it.** "Four changes landed
in the name path today" is true and is not the span this comparison covers, because #92's
baseline predates #93 as well. One `git log 07b80d3..HEAD` turned four into five commits
and eight defects, and surfaced the two that change the printed identity STRING — the
sharper hazard for this particular ruler, and the one the framing did not name.

**2. The baseline's stored `aggregate` block is not the baseline.** It predates
`printed_arm_totals` and raised `KeyError` on first read. Re-deriving from `sites` with the
CURRENT aggregator reproduces every published figure and is also the only way the two runs
are compared under one definition.

**3. A floor nobody had read.** #92 published the printed-arm drift as 0.0000 and said it
was "real and almost worthless" because the metric is saturated. Its two passes also carry
floors for the blanked RATE (0.0008) and the blanked SHARE (0.065 pp), which are the two
quantities that actually moved. They are derived here — and then immediately discounted,
because they are back-to-back and this comparison is a day apart.

**4. My fixture for the fuse mechanism is the worst case and saying so changes the
reading.** It has no whitespace between tags, so the rendered text genuinely *is*
`ProductsPricingSupport`. Real markup usually has a newline between tags. Prevalence came
from the corpus (`blanked-text-no-match` 17 → **15**, i.e. the fuse did NOT produce a wave
of no-matches) and from the A/B, not from the fixture.

**5. The second mechanism was an inference until it was measured.** "Query identical,
entry count identical, answer different, therefore the names changed" is sound and is still
an argument. Running both collectors on that page and counting named rows (123 → 137, 14
gained) turned it into a measurement, and the 14 rows are readable.

---

## 11. What this establishes, and what it does not

**Establishes.**

1. **No regression on the question #74 created this ruler for.** Across 257 live
   out-of-sample sites, 596 reads of which 339 are post-interaction, **14,071 probes and 0
   misses** (95% bound ≤ 0.000215), with the per-site median at 1.0000 and every one of 257
   sites at 1.0000 — after five name-path commits, two of which change the printed identity
   string itself.
2. **Site by site against #92: 251 identical, 0 regressed**, and — more strongly — **both
   collectors score 1.0000 on the same DOM at the same stage** on the two biggest cross-run
   fallers and four carriers of the name changes.
3. **A revealed control is still no harder to reach than one that was always there**:
   `new` 1,962/1,962, `carried` 6,015/6,015, `s0` 5,989/5,989.
4. **The blanked population's membership is unchanged by the collector** — `entries` and
   `blanked-entries` identical in both A/B arms — with the mechanism read at source before
   the data arrived and confirmed by it.
5. **The blanked arm's weaker question fell 0.8908 → 0.8866, and it IS the collector**, by
   two measured mechanisms: inline-child joins fusing a container's concatenated name
   (`NOV 02` → `NOV02`), and 14 rows per page gaining an identity and competing in `find`'s
   capped result list. Both affect a string no reader sees; the second is a win on the
   printed arm that this arm scores as a loss.
6. **A coverage answer with numbers rather than an assertion** (§8), including the name
   oracle's own reach: it compares 103,231 of ~164,831 rows (62.6%).

**Does not establish** that `find` is good at finding things — this is deliberately the
weakest question there is, and #20 measured the hard one (given a human's GOAL, find the
control) at 0%. Nor that the name is RIGHT. Nor anything about hover-only menus, logins,
paywalls, cross-origin frames, second paths, or the ~180 consent- and bot-walled candidates
absent before this probe starts.

### The single thing I am least sure of

**That this run had the power to detect the regression it was looking for.** It samples
8.7% of entries by stride, and the name changes under test are concentrated on a handful of
sites — #116 moves 24 of 251, #115 puts 70% of a class on two. A defect confined to a rare
shape could sit entirely under the sampling and this run would read 1.0000 either way.
§7's A/B is the answer to that and it is six sites; `wc_webawesome`, the heaviest carrier,
is 1.0000 in both arms on 110 and 103 probes, which is the most load-bearing single cell in
this paper. What would settle it properly is an A/B over all 24 of #116's touched sites,
which was not run.

Second, smaller: the blanked-arm floor is derived from **back-to-back** passes while the
cross-run comparison is a **day apart**, so "5× the floor" overstates its own significance.
The A/B is what carries that conclusion, not the floor comparison.

---

## 12. Reproducing

```bash
# the fixture firing proof (must PASS, and the #74 reproduction must score a miss)
python tools/measure_findability_at_stage.py --selftest

# the live firing proof
python tools/measure_findability_at_stage.py --fire --only gov_au leg_perldoc ko_daum \
       wc_webawesome w2_unicode --k 8 --out temp/findability_stage/fire2

# the main run
python tools/measure_findability_at_stage.py --pool usable85 --conc 6 --stages 4 \
       --out temp/findability_stage/main2

# every pooled table, from the saved artefact
python tools/measure_findability_at_stage.py --report temp/findability_stage/main2/pass0.json
```

The causal arm of §7 is not in the repo: it is a throwaway that extracts
`_collectInteractivePage` from `git show 07b80d3:extension/background.js`, asserts the two
arms differ, and calls `measure_findability_at_stage`'s own `choose` / `score_arm` so that
**only the collector string changes** between arms. Its order is rotated per site because
the first collector to run stamps the mmids.

**Artefacts:** `temp/findability_stage/main2/pass0.json` (main run),
`temp/findability_stage/ab/ab.json` (the causal A/B, with both arms' miss records),
`temp/findability_stage/fire2/fire.json` (the live firing proof).
**Baseline:** `temp/findability_stage/main/pass0.json` (#92) and
`temp/findability_stage/drift/pass{0,1}.json` (#92's drift passes, the source of the two
floors in §7).
