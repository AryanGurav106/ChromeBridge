# Is the name right on content that only exists while the mouse is there?

**Probe:** `tools/audit_name_correctness.py --hover` (new arm)
**Drivers reused verbatim:** `tools/audit_hover_stage.py` (#94) for the pick, the
before/after element-identity diff and the did-the-hover-survive check;
`tools/audit_generality_live.py` for the sample, the exclusions and the collector
**Oracle:** Chrome's own `Accessibility.getFullAXTree`, joined by `backendNodeId`
**Collector under test:** `_collectInteractivePage`, extracted verbatim from
`extension/background.js` at `4d1cec0` — and VERIFIED byte-identical at `18cddfd`,
which landed while these runs were in flight, so the figures describe both
**Date:** 2026-11-19

> **The population is real and the headline population inside it is small, for a
> structural reason.** 254 usable live out-of-sample sites, **99 of them revealed
> something on hover**, 171 reveals, **1,621 controls observed to appear**, 1,579 listed
> as entries, **1,518 reaching the oracle** — three times #94's 528. But a hover menu is
> made of plain links named by their own text: **`src=name`, the slice the 0.9766
> headline quotes, is 8.6% of the hover arm against 22.7% of the carried arm**, so it
> contributes **131 rows**. That is not a sampling shortfall and no sample size fixes it.
>
> **Hover-revealed content is not named worse — and the arm that says so is `src=text`,
> not the headline one.** `src=text` **0.8983** against the same reads' carried rows at
> **0.6653**, paired within one read **68 better / 8 worse** (p = 0.0000), per site
> **48 / 6** across 55 sites (p = 0.0000), and leave-one-site-out moves it only
> +0.2330 → +0.2105. Four robustness cuts (hover still held after the read, every
> arrival inside the hovered element, tier-1 only) keep the direction in every case.
>
> **THE `src=name` FIGURE LOOKS BETTER AND IS NOT A RESULT, AND MY DRAFT HEADLINE SAID
> IT WAS.** 0.9771 against 0.9290 is **131 rows from 18 sites with 79.4% of them on
> three**, and leave-one-site-out inverts the sign: dropping `w2_berkeley_cls` takes it
> to +0.0274, dropping `w2_hdfc_life` as well to **−0.0194**, and the third to
> **−0.0396**. Its paired test is 2 / 0 / 1 at p = 0.5000. I wrote "+0.0481, better on
> both arms" from the pooled table and only asking *how many sites is this?* caught it —
> PRINCIPLES 8 on a flattering number, and the same question #115's own history on this
> comparison turns on. **The honest statement for `src=name` is: not established, in
> either direction.**
>
> **AND ALMOST ALL OF THAT GAP IS NOT A QUALITY DIFFERENCE, which is the half a bare
> rate would have got wrong.** Removing the three classes #114 dispositioned as *not a
> wrong name* (`chrome-empty`, `punctuation-only`, `case-only`) from BOTH arms collapses
> `src=text` from **+0.2330 to +0.0151**. The carried arm's low raw rate is #114's
> permanent floor — `chrome-empty` is **26.07% of its `src=text` rows and 0.59% of the
> hover arm's** — because a hover menu is declared controls while a whole page is full
> of the generic containers ARIA forbids naming. **Run twice, the drift floor on that
> adjusted difference is 0.0069**, so the residual +0.0151 is one to two times the
> noise: the defensible statement is that hover content is named **the same**, not
> better.
>
> **THE OVER-REPRESENTED CLASSES ARE BOTH ONES WHERE WE ARE RIGHT.** The prize this was
> run for: `ours-empty|unlabeled` at **6.87x** (3 rows, 2 sites) and
> `punctuation-only|text` at **3.14x** (**87 rows, 7 sites**) — and the mechanism is the
> same in both. A hover menu's items are icon-prefixed, so Chrome's spec-correct name
> carries an icon font's Private-Use-Area `::before` glyph (85 of the 87) or, on an
> empty `<a class="flex-next">`, **consists of nothing else**. #114 dispositioned that
> class as ours-better and #115 measured the identical shape at 37 rows. **No class with
> multi-site support is both over-represented and a defect of ours.**
>
> **The one row I could not explain turned out not to be ours, and chasing it is what
> settled it.** `gov_tw_moi` printed `name="tbx_advancedSearchBtn"` where Chrome said
> `搜尋`. The page ships
> `<label for=… style="font-size:0em"><span>tbx_advancedSearchBtn</span></label>` — a
> developer placeholder shipped as the field's label. We follow HTML-AAM (`<label>`
> outranks `title`); Chrome drops a label that renders at 0px and falls through. Both
> defensible, the PAGE is what is broken, and ours is the more spec-faithful answer and
> the worse string.

---

## 1. The gap, and why it is a gap rather than an oversight

#117 audited which instrument covers which question at which stage, found the three
main axes covered — presence (#89/#112), name correctness (#93/#108/#115) and
reachability (#92/#117) — and named **two shapes that fall between them**. This is one:

> **Name correctness on hover-revealed content.** `audit_hover_stage.py` (#94) drives
> hover for PRESENCE and REACHABILITY — 120 out-of-sample sites, 63 reveals on 38
> sites, 528 controls revealed, 0 owning no row, `find` reaching 0.913. **The name
> oracle does not drive hover at all.**

The two halves of that sentence have different causes and only one of them is a
decision. #94's driver exists and is good; the oracle simply never used it. What
blocked it is a rule about the PRODUCT that was read as a rule about MEASUREMENT, and
#94's own docstring is the place that separates them:

> `audit_stage_generality` picks its interactions from DECLARATIONS ONLY … A CSS
> `:hover` submenu declares none of that, so the PRODUCT must not guess at it
> (PRINCIPLES 1) and that picker correctly refuses to choose one. **That is a rule
> about what the product may INFER, not about what a probe may DRIVE.**

So the oracle's driver (`audit_stage_generality.STAGE_PICK`) structurally cannot
reach a hover menu, and nothing had plugged the other driver in.

**Why this population is the one most likely to be odd.** A hover menu is built by a
component library at the moment of hover — the same mechanism #115 measured making
the slot defect **2.84x** worse after an interaction, and #116 shipped a fix for.
Every name figure this project publishes describes content that was already on the
page, or content revealed by a DECLARED interaction.

---

## 2. What was built, and what was deliberately not

Reused, not rewritten (PRINCIPLES 17; #117 found an instance of exactly this failure
this week, and #36/#37 each record a restated definition drifting):

| | from |
|---|---|
| hover candidate picker, three tiers, all read off the page | `AHS.HOVER_PICK` (#94) |
| before/after control-set diff, by ELEMENT IDENTITY in page memory | `AHS.HOVER_DIFF` (#94) |
| revealed-element mmid resolution after the collector stamps | `AHS.APPEARED_MMIDS` (#94) |
| the oracle: collector -> declarations -> AX tree -> classify | `read_once` (#93) |
| sample, exclusions, out-of-sample guard, viewport, visibility rule | `AGL` / `ASG` (#85/#89) |

Written here: the **sequencing** (hover -> verify something appeared -> oracle read ->
resolve the revealed mmids), and one new axis inside `read_once`.

**The new axis is `by_hov`, and it is a third population counter beside `by_pop`.**
`hov` is an element a hover was WATCHED to reveal; `pre` is every other compared row
**in that same read**. Both arms therefore come from one read of one page against one
AX tree read, which is the design #115 arrived at after its own pooled
revealed-vs-carried table compared two different mixtures of pages, and after #93's
version of the same question reversed sign between runs.

**`by_pop` is kept rather than replaced**, because the two definitions have disagreed
before: `by_pop`'s `new` is keyed on the identity STRING (#89/#92's rule, because
mmids are additive) and so counts a control that was always on the page but whose
identity happened not to appear earlier. `hov` is keyed on an observation.

**Not built:** an in-root-only headline arm. The confound it would address — content
arriving during the 900ms settle for a reason other than the hover — is instead
BOUNDED and printed (see §3), because changing the population definition after the run
would be choosing the arm that flatters.

---

## 3. Proving the arm fires

**A clean rate over an empty population is the specific hazard here**, and it is the
one a reader cannot see: a driver that silently revealed nothing would produce a
beautiful number. So the proof is about the POPULATION as much as the comparator.

`python tools/audit_name_correctness.py --hover-selftest` — **PASS**, `failures: []`.
Six checks on a fixture carrying a CSS `:hover` submenu, an icon link, and a decoy
that reveals nothing:

| | result |
|---|---|
| 1. a `:hover` submenu is DRIVEN and its controls reach the COMPARED population | 1 reveal, 3 revealed, 3 entries, **3 compared** |
| 1b. the CARRIED arm is non-empty, so the comparison has its other half | `pre_compared` = 1 |
| 2. the comparator fires on a HOVER-REVEALED row known to disagree | `Revealed Facebook` vs `'\ue978'`, `disjoint` |
| 3. CONTROL — the agreeing revealed rows are NOT flagged | `Revealed Alpha` / `Revealed Beta` absent from the rows |
| 4. CONTROL — a hover that reveals nothing is SEEN to reveal nothing | `nothing_appeared` = 1 |
| 5. a sentinel planted on the HOVER-REVEALED rows is reported | 3 moved, 3 reached, **3 reported as `SENTINEL`** |

Check 2 is anchored on **#114's class F** — `title` against an icon font's PUA glyph,
which #114 measured and recorded as a DECIDED don't-build — for the reason this file's
main selftest records: it expired twice when anchored on a defect that then shipped a
fix, and a proof anchored on a decision outlives one anchored on a backlog item.

**Check 2 passed and looked exactly like a check that should have failed, which is why
it is printed as `repr` now.** Chrome's name for that row is `'\ue978'`, a Private-Use
glyph that renders as nothing at all, so with `ensure_ascii=False` the artefact read
`"theirs": ""` — and the check requires `theirs` to be non-empty. Re-derived before it
was believed (PRINCIPLES 8), on a PASS rather than on a failure.

**And the plant's first version proved nothing, for a fixture reason rather than a code
reason.** It ran after the mouse had moved away, so the menu was shut, every revealed
element measured 0x0, `_PLANT_JS`'s size guard skipped all of them, and the arm
reported "tagged nothing". The plant now happens while the mouse is still held. That is
the vacuous-fixture class (PRINCIPLES 11) pointed at the firing proof itself.

**Also proven firing:** the out-of-sample guard refuses on the hover path
(`--plant-in-corpus` → `SAMPLE CONTAINS EXCLUDED HOSTS`, exit 2, before any browser
starts), and `C47` failed on this very paper until it was routed in `docs/README.md`.

**Three invariants are checked on every run and printed in the report**, because a
silent violation of any of them voids every number: `fmt_drift` (the probe's
restatement of `_fmtLine`'s identity precedence having drifted), AX errors, and
`compared == exact + Σ classes` for every arm × `src`. All three were clean.

### The LIVE firing proof

A fixture shows the arm CAN fire; this shows it firing on real pages, on rows a real
hover revealed. `--hover --fire` on an independent 38-site stride (36 usable, 18 with a
reveal, **32 reveals**): after each reveal a sentinel name is written onto the
hover-revealed elements ONLY — never onto whatever the page happens to list first,
because a sentinel on the page header proves the comparator works and says nothing
about whether this driver reached the population.

| | |
|---|---|
| reveals carrying a plant | 32 |
| rows whose name was moved | **115** |
| …of those, reaching the COMPARED population | **115** |
| **sentinels the comparator FAILED to report** | **0** |
| errored reveals | 0 |
| **verdict** | **PASS** |

115 of 115 is a stronger statement than the fixture's 3 of 3, and it is the one that
rules out the hazard this section opens with: the population is not empty, the mmids
resolve, the join holds, and the comparator reports a moved name on hover-revealed
content on live sites.

---

## 4. Results

254 usable sites of 265, **171 reveals on 99 sites**, 1,518 rows compared against
Chrome's AX tree, `fmt_drift = 0`, `ax_failures = 0`, tally reconciles.

### 4.1 The funnel — how big the measurable population actually is

| | |
|---|---|
| sites attempted | 265 |
| UNMEASURED (goto/read failed), named in §5 | 4 |
| rendered too little to compare (**not a pass**) | 7 |
| usable (`usable()`, the project's own rule) | **254** |
| **sites where a hover revealed something** | **99** |
| **reveals measured, one oracle read each** | **171** |
| hover attempts that revealed nothing | 888 |
| sites offering no hover candidate at all | 70 |
| **controls observed to appear** | **1,621** |
| …listed as entries by the collector | 1,579 |
| …reaching the COMPARED population | **1,518** |
| tier that produced the reveal | `css-hover` 106, `hidden-children` 58, `nav-item` 7 |
| hover still held AFTER the oracle read | 158 yes / **13 no** |
| arrivals INSIDE the hovered element | **1,241 of 1,621 = 76.6%** |

Three times #94's 528 revealed controls, on 99 sites against its 38. The 61-row gap
between entries and compared rows is stated and its causes listed, not attributed: a
blanked identity (#74's rule), a contents-only row, a Chrome-ignored node, or both
sides empty.

### 4.2 Where the identity comes from — and why the headline population is small

| `src` | hover n | hover share | carried n | carried share |
|---|---|---|---|---|
| `text` | 1,367 | **90.1%** | 25,635 | 73.8% |
| `name` | **131** | **8.6%** | 7,875 | **22.7%** |
| `label` | 17 | 1.1% | 1,219 | 3.5% |
| `unlabeled` | 3 | 0.2% | 10 | 0.0% |
| **total compared** | **1,518** | | **34,758** | |

**`src=name` means the page DECLARED a name** (`aria-label`, a `<label>`, a `title`);
`src=text` means the row prints the element's own rendered text. A hover menu is a run
of plain links, so its identities come from their text. **The statistic the project's
headline quotes therefore has little hover content in it at any sample size** — 131
rows here — and that is the answer to "how big is the measurable population", rather
than a caveat about this run.

### 4.3 The headline, both arms from the same read

| | compared | exact | **agree** | 95% CI |
|---|---|---|---|---|
| **`src=name` hover-revealed** | 131 | 128 | **0.9771** | 0.9348–0.9922 |
| `src=name` carried, same reads | 7,875 | 7,316 | **0.9290** | 0.9231–0.9345 |
| | | | **+0.0481** | |
| **`src=text` hover-revealed** | 1,367 | 1,228 | **0.8983** | 0.8812–0.9132 |
| `src=text` carried, same reads | 25,635 | 17,055 | **0.6653** | 0.6595–0.6711 |
| | | | **+0.2330** | |

Per-site median: hover `src=text` **1.0000** over 23 sites with n≥20, carried 0.7131
over 99. Paired within one read, `src=text`: **68 better / 8 worse / 2 identical**,
median +0.2188, **p = 0.0000**; per SITE (two reads of one page are not two independent
pairs — the carried arm is the same page both times) **48 / 6 / 1** across 55 sites,
median +0.2093, **p = 0.0000**.

**THE TWO ARMS HAVE COMPLETELY DIFFERENT BREADTH, and only one of them supports a
claim.** A pooled rate over an arm whose rows come from a handful of sites is a
measurement of those sites (#73 quotes the Mind2Web headline with a LOSO span for the
same reason). Dropping the largest contributing sites one at a time:

| dropped | hover n | hover | carried | difference |
|---|---|---|---|---|
| **`src=name`** — 18 sites, top 3 carry **79.4%** | | | | |
| none | 131 | 0.9771 | 0.9290 | **+0.0481** |
| `w2_berkeley_cls` | 68 | 0.9559 | 0.9285 | +0.0274 |
| + `w2_hdfc_life` | 33 | 0.9091 | 0.9285 | **−0.0194** |
| + `w2_buenosaires` | 27 | 0.8889 | 0.9284 | **−0.0396** |
| **`src=text`** — 75 sites, top 3 carry **18.7%** | | | | |
| none | 1,367 | 0.8983 | 0.6653 | **+0.2330** |
| `w2_cuni` | 1,273 | 0.8908 | 0.6676 | +0.2232 |
| + `w2_busan` | 1,187 | 0.8829 | 0.6664 | +0.2165 |
| + `w2_mumbai` | 1,112 | 0.8750 | 0.6645 | **+0.2105** |

**`src=name`'s sign inverts after two drops; `src=text` moves by 0.02 after three.**
On `src=name` only 3 reads carry ≥5 rows in both arms, so its paired test is 2 / 0 / 1
at p = 0.5000. **`src=name` is NOT ESTABLISHED in either direction** and the rest of
this paper does not rest on it.

**Robustness — four cuts, same direction every time:**

| cut | reads | `src=name` diff | `src=text` diff |
|---|---|---|---|
| all reads (headline) | 171 | +0.0481 | +0.2330 |
| hover still held after the read | 158 | +0.0452 | +0.2260 |
| every arrival INSIDE the hovered element | 89 | +0.0599 | +0.2686 |
| tier 1 only (the page's own CSS declared the hover) | 106 | +0.0700 | +0.1871 |

### 4.4 Most of the gap is #114's floor, not quality

Removing from **both** arms the three classes #114 dispositioned as *not a wrong name*
— `chrome-empty` (Chrome's ROLE forbids one; #74 requires we print the author's
string), `punctuation-only` (a `::before` glyph or a zero-width mark) and `case-only`
(CSS `text-transform`, which `find` folds) — **from the denominator as well as the
numerator**, because otherwise it is a credit rather than a rate:

| | raw | **excluding the dispositioned classes** |
|---|---|---|
| `src=name` hover | 0.9771 | **0.9846** |
| `src=name` carried | 0.9290 | **0.9570** |
| difference | +0.0481 | **+0.0277** |
| `src=text` hover | 0.8983 | **0.9746** |
| `src=text` carried | 0.6653 | **0.9595** |
| difference | **+0.2330** | **+0.0151** |

**`chrome-empty` is 26.07% of the carried `src=text` rows and 0.59% of the hover arm's**
(re-derived from `by_hov` rather than read off the table). A whole page is full of the
generic containers ARIA forbids naming; a hover menu is declared controls. So the raw
+0.233 is overwhelmingly composition, and the residual **+0.0151** is what is left of
"named better". Reading the raw figure as a quality finding would have been the mirror
of #115's error, where a pooled "worse" was the same floor sitting in the *other* arm.

The `src=name` row of that table (+0.0481 → +0.0277) is shown for completeness and
inherits §4.3's verdict: that arm is three sites and its sign inverts, so neither its
raw nor its adjusted figure is a result.

### 4.4b The drift control, and what it does to the residual

The same arm run twice over the same 265 sites (R3), because hover candidate selection
is stateful and the live web moves:

| | main | drift | floor |
|---|---|---|---|
| usable sites | 254 | 253 | |
| sites where a hover revealed something | 99 | 97 | |
| reveals | 171 | 168 | |
| rows compared | 1,518 | 1,501 | |
| arrivals inside the hovered element | 76.6% | 77.4% | |
| `src=text` hover | 0.8983 | 0.8915 | 0.0068 |
| `src=text` carried | 0.6653 | 0.6716 | 0.0063 |
| **`src=text` raw difference** | **+0.2330** | **+0.2199** | **0.0131** |
| **`src=text` difference, dispositioned classes removed** | **+0.0151** | **+0.0082** | **0.0069** |
| `src=text` paired per site | 48 / 6 | 46 / 6 | |
| `punctuation-only\|text` | 3.14×, 87 rows, 7 sites | 3.24×, **87 rows, 7 sites** | |
| `ours-empty\|unlabeled` | 6.87×, 3 rows, 2 sites | ∞, 3 rows, 2 sites | |

**The raw +0.23 is 17–34× the floor; the adjusted +0.015 is one to two times it.** So
once #114's dispositioned classes are out of both arms, hover-revealed content is named
**the same** as carried content to within the run-to-run noise of this instrument —
which is a cleaner statement than "slightly better" and is the one this paper rests on.

The `src=name` arm's fragility reproduces as well, and the way it reproduces is itself
evidence of how thin it is: LOSO inverts in both passes, but the third-largest
contributing site is `w2_buenosaires` in one and `w2_tau` in the other.

### 4.5 The prize: which classes concentrate on hover-revealed content

| class \| src | hover n | **sites** | hover /10k | carried /10k | ratio |
|---|---|---|---|---|---|
| `ours-empty\|unlabeled` | 3 | **2** | 19.8 | 2.9 | **6.87x** |
| `punctuation-only\|text` | **87** | **7** | 573.1 | 182.4 | **3.14x** |
| `whitespace-only\|text` | 2 | **1** | 13.2 | 7.8 | 1.70x |
| `chrome-superset\|text` | 30 | **7** | 197.6 | 178.7 | 1.11x |
| `case-only\|text` | 12 | 2 | 79.1 | 156.2 | 0.51x |
| `disjoint\|name` | 2 | 2 | 13.2 | 52.9 | 0.25x |
| `chrome-empty\|text` | 8 | 2 | 52.7 | 1,923.0 | 0.03x |

**The site count is printed beside every ratio deliberately.** #115 read
`live-label-not-clone`'s 16-of-31 at one depth as a stage premium and had to correct it
to a SITE effect; a ratio produced by one site is that shape wearing a population
effect's clothes. Two classes here have multi-site support.

**Both of them are classes where our output is better than Chrome's**, and the
mechanism is one thing — a hover menu's items are icon-prefixed. The character cut,
taken over the saved rows:

* `punctuation-only|text` (7 sites): **"CHROME HAS, we do not: private-use glyph (an
  icon font's `::before`)" × 85** of 87. Live rows: `'\ue315 総長からのメッセージ'`,
  `'\uf007個人訂票'`, `'Undergraduate \uf061'`, `'\ue908 Expand top-level sections'`.
* `ours-empty|unlabeled` (2 sites): all three are an **empty `<a>` whose entire rendered
  content is an icon glyph** — `<a class="flex-prev" href="#"></a>`,
  `<a class="flex-next">`, `<a class="a2">` — which Chrome names `'\uf001'`, `'\uf002'`,
  `'\ue76c'`. We print `(unlabeled)`. Neither string identifies the control; the PAGE
  ships an unlabelled carousel arrow. #115 measured the identical shape at 37 rows on
  `w2_alrajhi` and reached the same verdict.

`whitespace-only|text` is 2 rows on 1 site (`'Graduate Archive(link is external)'`
against Chrome's spaced form) — **ours, and n=2, so it is named and not acted on**
(#26's rule). `chrome-superset|text` at 1.11x is **not** over-represented; it is #34's
known shape plus Chrome doubling a name it sees on two children
(`'TOKYO強靭化プロジェクト TOKYO強靭化プロジェクト'`), and both are general rather than
hover-specific.

### 4.6 The one row that was not explained, chased to its cause

`gov_tw_moi` printed `name="tbx_advancedSearchBtn"` against Chrome's `搜尋` — the only
row in 1,518 I could not account for, and a fixture reproducing its markup gave the
RIGHT answer, which is what said the markup was not the whole story. Asked of the live
page:

```html
<span class="search">
  <label for="tbx_advancedSearchBtn" style="font-size: 0em;">
    <span>tbx_advancedSearchBtn</span>
  </label>
  <input id="tbx_advancedSearchBtn" type="search" placeholder="Search" title="搜尋">
```

The page ships a **developer placeholder as the field's label**, hidden with
`font-size: 0em`. HTML-AAM puts `<label>` above `title`, so we take the label; Chrome
treats a label that renders at 0px as contributing nothing and falls through to the
title. **Both are defensible, the page is what is broken, and ours is the more
spec-faithful answer and the worse string for a reader.** Not actionable: the only rule
that would change it is a threshold on rendered text size, which is what PRINCIPLES 1
removes from every path that decides something, and it is n=1.

### 4.7 No change is proposed

Nothing here is a defect of ours with multi-site support. The two concentrating classes
are ones where we are right; the one class that is ours (`whitespace-only`) is 2 rows
on 1 site; and the unexplained row resolved to a page defect. **#41/#44's rule is that
a change to the name path is measured on both halves first, and there is nothing here
that reaches the bar for proposing one.**

---

## 5. Sample, and what this cannot establish

**Chrome is an ORACLE, not ground truth.** A name both derivations get wrong scores as
agreement. #114 measured that **51% of the `src=name` residue is `chrome-empty`** —
rows where Chrome's ROLE forbids a name and we print the author's own string, which
#74 proves is the better error. A change that raised the rate by deleting those names
would be a regression whatever the number said. Nothing here is a proposal to chase
agreement, and the two tables that could tempt one — the class histogram and the
over-representation cut — are both reported with their MECHANISM beside them for that
reason.

**The rate is a SCREEN; the mechanism table is the verdict.** This is #117's own
framing of its cross-run table, and it applies with more force here, because of the
one confound this design cannot remove: within a read, `hov` is a submenu and `pre` is
the whole page, so the two arms differ in the KIND of element as well as in where the
element came from. Splitting by `src` controls the largest part of that (both arms are
restricted to elements where the collector resolved a declared name, or to elements
where it printed their own text), and it does not control all of it: a hover arm made
of nav links is not role-matched against a carried arm containing headings, form
fields and generic containers. **So a bare rate gap between the arms must not be read
as "hover content is named worse (or better)"** — only a mechanism that concentrates
can support a claim, which is why §4 leads with the class and character cut.

**The population is small and structurally so**, not by sampling — see §4's `src`
mix. A hover menu is overwhelmingly plain links whose identity is their own text, so
the `src=name` arm that the 0.9766 headline quotes has little hover content in it at
any sample size.

**One confound is bounded rather than argued.** The before/after set is every visible
on-screen control, so anything arriving during the 900ms settle for a reason other
than the hover — a lazy-load, a carousel — counts as revealed. An element INSIDE the
hovered root cannot be that, so the in-root share is printed as the bound.

**The sample is inherited and survivorship-biased.** The pool is #85's `usable85` —
sites that rendered in its final run, screened from 445 candidates — so roughly 180 a
headless browser could not reach are absent before this starts, 112 of them behind a
consent wall or a bot block. **No user-agent spoofing and no bot-check evasion**; a
refused site is UNMEASURED and NAMED, never a pass. `usable()` is the project's own
definition, reused rather than restated.

**A probe hovering is not a human hovering.** The mouse lands at the centre of a
picked element, waits 900ms and does not move again; a person arrives along a path,
dwells, and moves through a submenu. Menus that open on a dwell timer longer than
900ms, on a mouse *path* rather than a position, or on `mouseover` of a child the
probe never touches, are not reached. Reveals that need two hovers in sequence are not
reached either — the driver moves the mouse away between candidates on purpose.

**One path per site, at most two reveals.** No logins, no cross-origin frames, no
second route through a site, and hover is driven only at FIRST PAINT, not on top of a
declared interaction — so "a menu inside a dialog" is outside this.

**Nothing here says whether a name is USEFUL**, only whether it is the one the browser
computes. #75 tried to measure usefulness and found the benchmark substrate could not
carry the question.

---

## 6. Mistakes made while measuring this

**1. My draft headline reported the `src=name` arm as a result, and it is not one.**
The pooled table says +0.0481 and reads like the cleanest finding in the paper. It is
131 rows from 18 sites with 79.4% on three, and the sign inverts after two drops. What
caught it was not reviewing the number — it was asking *how many sites is this?*, which
is a question the pooled table cannot answer and the LOSO arm now does, in the tool
rather than in this paragraph.

**2. The firing proof proved nothing on its first run, for a FIXTURE reason.** The
plant ran after the mouse had moved away, so the menu was shut, every revealed element
measured 0×0, `_PLANT_JS`'s size guard skipped all of them, and the arm reported
"tagged nothing". That reads as a broken plant and was a broken fixture — PRINCIPLES 11
pointed at the firing proof itself.

**3. A check PASSED while looking exactly like one that should have failed.** The
class-F anchor requires Chrome's name to be non-empty; Chrome's name there is
`'\ue978'`, a Private-Use glyph that renders as nothing, so with `ensure_ascii=False`
the artefact read `"theirs": ""`. Re-derived on a PASS rather than on a failure
(PRINCIPLES 8), and the field is printed as `repr` now.

**4. The report restated `usable()` as `"error" not in s`**, which counts a site that
rendered three elements as a pass — a looser definition than every other table in the
same file uses. PRINCIPLES 17; #36 records the permitted-drop-reason set drifting the
same way and #117 found an instance this week. It reuses the project's rule now, and
the funnel gained a "rendered too little to compare (**not a pass**)" row.

**5. The one unexplained row nearly went in as a defect, and the FIXTURE is what
stopped it.** From the 7-site smoke, `ours='tbx_advancedSearchBtn'` against Chrome's
`搜尋` looked like a declared `title` losing to an id-derived handle. Reconstructing
the markup gave the RIGHT answer — which is the signal that the markup was not the
whole story, rather than a reason to shrug. Asking the live page found the page's own
zero-font-size `<label>` carrying a developer token (§4.6).

**6. `in_root` is a bound I added only after noticing the population could include
lazy-loaded arrivals.** It came back at 76.6%, not the 90.9% the smoke suggested — so
the confound is larger than the first sample implied, and the robustness cut that
removes it entirely (n=89 reads) is in §4.3 for that reason.

---

## 7. What this establishes

**Establishes.**

1. **The gap #117 named is closed with a measurement**, and the population is three
   times #94's: 99 of 254 live out-of-sample sites, 171 reveals, 1,518 rows compared
   against Chrome's own AX tree.
2. **How big the measurable population is, and why.** `src=name` — the slice the
   0.9766 headline quotes — is **8.6%** of the hover arm against 22.7% of the carried
   arm, because a hover menu is plain links named by their own text. No sample size
   changes that.
3. **Hover-revealed content is not named worse.** On `src=text`, the arm with 75 sites
   behind it: 0.8983 against 0.6653, 48/6 paired per site (p = 0.0000), LOSO-stable,
   same direction in four robustness cuts, and reproduced on a second full pass
   (0.8915 against 0.6716, 46/6).
4. **Almost all of that gap is #114's floor rather than quality**: +0.2330 →
   **+0.0151** once `chrome-empty`/`punctuation-only`/`case-only` leave both arms,
   because `chrome-empty` is 26.07% of the carried arm and 0.59% of the hover arm —
   and **the run-to-run floor on that adjusted difference is 0.0069**, so the right
   statement is "the same", not "better".
5. **The two classes genuinely over-represented on hover content are both ones where
   our string is better** — `ours-empty|unlabeled` 6.87× and `punctuation-only|text`
   3.14× across 7 sites — and they are one mechanism: a hover menu's items are
   icon-prefixed, so Chrome's spec-correct name carries a PUA `::before` glyph.
6. **No defect of ours concentrates on hover-revealed content.** The only ours-side
   class over-represented is `whitespace-only` at 2 rows on 1 site, which is named and
   not acted on.
7. **The arm fires**, on a fixture (6 checks, 2 of them controls) and live (**115 of
   115** planted sentinels on real hover-revealed rows).
8. **The instrument reproduces.** A second full pass: 253 against 254 usable sites,
   168 against 171 reveals, 1,501 against 1,518 rows, and `punctuation-only|text` at
   **87 rows on 7 sites in both passes**.

**Does not establish.** That any of this transfers off the inherited,
survivorship-biased `usable85` pool; that `src=name` content is named better or worse
on hover (§4.3); that a name both derivations get wrong is wrong; or anything about
hover menus that need a dwell longer than 900ms, a mouse path, two hovers in sequence,
a login, or a hover on top of a declared interaction.

**The single thing I am least sure of** is whether the `src=text` result is a statement
about NAMING at all, rather than about what kind of element a hover reveals. The two
arms are not role-matched: `hov` is a submenu and `pre` is the whole page, and §4.4
shows that removing the three dispositioned classes takes **93.5%** of the gap with it.
What is left is **+0.0151 against a measured run-to-run floor of 0.0069** — one to two
times the noise — so a residual composition difference I have not controlled for (menu
links against form fields, headings and generic wrappers) could account for all of it.
The arms could be role-matched, and are not: `by_hov` carries `src` but not tag or
Chrome role, so that is the obvious next cut and it needs another run rather than
another reading of this one.

**The claim I would defend is the NEGATIVE one**, which is what the paper is for:
nothing is named *worse* on hover-revealed content, and no defect of ours concentrates
there. "Named better" is the weaker reading and I would not build on it.

---

## 8. Artefacts

| | |
|---|---|
| main run (265 attempted, 254 usable, 171 reveals) | `temp/name_on_hover/main/hover0.json` |
| drift control, same arm twice | `temp/name_on_hover/pass2/hover0.json` |
| live firing proof (`--fire`, 38-site stride) | `temp/name_on_hover/fire/hover0.json` |
| 7-site smoke that found the first defects | `temp/name_on_hover/smoke/hover0.json` |

---

## 9. Reproducing

```bash
# the firing proof for THIS arm (a driver that reveals nothing gives a clean rate
# over an empty population, so the fixture carries a decoy that reveals nothing)
python tools/audit_name_correctness.py --hover-selftest

# the run
python tools/audit_name_correctness.py --hover --conc 5 --examples 60 \
    --out temp/name_on_hover/main

# every table in this paper, from the saved artefact
python tools/audit_name_correctness.py --hover-report temp/name_on_hover/main/hover0.json

# the drift control (R3): the SAME arm again, so the floor is measured rather than assumed
python tools/audit_name_correctness.py --hover --conc 5 --examples 60 \
    --out temp/name_on_hover/pass2

# the LIVE firing proof: sentinels planted on HOVER-REVEALED rows on real pages.
# The verdict prints at the end of --hover-report.
python tools/audit_name_correctness.py --hover --fire --every 7 --conc 3 \
    --out temp/name_on_hover/fire

# the out-of-sample guard, shown refusing (exit 2, before any browser starts)
python tools/audit_name_correctness.py --hover --plant-in-corpus --limit 1
```
