# AccName 2F takes each child's NAME; we take its TEXT — both halves, measured

**Probe:** `tools/audit_name_correctness.py` (extended: a `child-declared-name` candidate
in three arms, a `--ab-arm` switch, reachability grading of every gained row, and a second
sabotage candidate)
**Successor to:** `docs/research/NAME-AT-STAGE-2026-11.md` (#115) §8, which located the
class and priced it but explicitly did not propose a fix
**Prior claim:** CLAUDE.md **#34**, recorded as a characterisation of a gap rather than a
defect, and unfixed since
**Collector under test:** `_collectInteractivePage`, extracted verbatim from
`extension/background.js` at `11c2024`
**Date:** 2026-11-19

> **Headline.** AccName 1.2 step 2F says each element child contributes its **NAME**;
> `_contentName` concatenates each child's **TEXT**. #115 found the degenerate case live —
> 54 rows where there is no text anywhere, so the row carries no identity at all, and of 24
> on one site **9 had the name nowhere in the listing**. This is the both-halves
> measurement #41/#44 require before such a change ships.
>
> **The mechanism is narrower than "we take text", and reproducing it first is what showed
> that.** `synthLabel` ALREADY rescues an icon-only control with
> `querySelector('svg[aria-label], [aria-label]')`, which is why
> `<button><span aria-label=Search></span></button>` prints `"Search"` today. **A
> querySelector does not cross a SLOT boundary**, and `_deepText` — which does cross it —
> is looking for text, of which an icon has none. So the hole is exactly: *a node that
> contributes no TEXT may still DECLARE a name, and the composed tree is where to look.*
>
> **Three arms were measured, not one**, because the obvious spec-faithful version is the
> expensive one: it absorbs a nested control's label into its container, and it **expires
> the name oracle's own firing proof**. The recommendation is the `guarded` arm — on
> 251 live out-of-sample sites: **`BREAKS_A_CORRECT_NAME` = 0** from a counter shown firing
> at 756, **159 rows** become exact matches with Chrome and none is broken, the **median
> site pays +0.000% characters**, identity loss is 0/0/0 on the sites it touches, and the
> whole project suite goes 20/21 → **21/21**.
>
> **The benefit is smaller than #115's sample implied and the table nearly said the
> opposite.** The genuinely-unreachable class this removes is **2 rows across 251 sites**,
> not the 9-in-24 a single site suggested. And the unguarded arm appears to beat it 41 to 2
> on exactly that number — until the rows are read, at which point all 41 turn out to be
> carousel containers absorbing the labels of every button inside them. **Reading the rows
> reversed the table** (§8).

---

## 1. The defect, reproduced before anything was designed

Against the shipped collector, on the shape #115 measured (`wc_webawesome`, 38 of its 54
rows):

```html
<wa-button>                                   <!-- host, LIGHT dom -->
  <wa-icon aria-label="Search"></wa-icon>
shadowRoot:
  <button part="base"><slot></slot></button>  <!-- the row we print -->
```

| asked of the shadow `<button>` | answer |
|---|---|
| `btn.innerText` | `''` |
| `btn.textContent` | `''` |
| `btn.querySelector('[aria-label]')` — synthLabel's rescue | **false** |
| `slot.assignedNodes({flatten:true})` | `[WA-ICON[aria-label=Search]]` |
| **our row** | `button (unlabeled)` |
| **Chrome** | `Search` |

The name is *reachable*, and only across the slot boundary. That is the whole defect.

**Two more shapes come with it, and neither is about slots.** `synthLabel` has an
`aria-label` branch and **no `aria-labelledby` branch at all**, so a child declaring one is
missed in the light DOM too; and its `querySelector` returns the **first** match only, so a
control whose accessible name is `Prev Next` printed as `Prev`. Both are in the fixture
(CD2, CD3) and both fail against the pre-fix collector.

---

## 2. The three arms

All three insert one helper, `_declName(n)`, which reads **declarations only** —
`aria-labelledby` (AccName 2B) and `aria-label` (2C) — and resolves a `<slot>` through
`assignedNodes({flatten:true})`. They differ only in when it is consulted.

| arm | rule |
|---|---|
| **narrow** | a child's declared name is used **only when that child contributes no text** |
| **guarded** | …and **the child is not itself a declared control** |
| **broad** | AccName's own order: a declared name **outranks** the child's text |

`guarded` is a deliberate divergence from the spec, which recurses into controls too —
which is why Chrome names
`<a>Read the report <button aria-label="Dismiss this card">×</button></a>`
*"Read the report Dismiss this card"*. **This codebase decided that question once already**,
in `synthLabel`: *"A PARENT HOLDING A SECOND CONTROL IS A GROUP, AND ITS TEXT LABELS THE
GROUP, NOT THIS CONTROL"* — measured in eval 7 on a quantity stepper where both buttons came
back named after the **quantity**. Reusing that rule here is PRINCIPLES 17 rather than a
second judgement, and the guard sits **inside** `_declName` so it reaches a slot-assigned
node and a direct child in one spelling.

### The fixture that separates them

One page, four collectors, Chrome as the oracle, re-verified after the AccName 2A rule of
§7 was added (it changes nothing here, because none of these shapes is `aria-hidden`).

| | base | narrow | guarded | broad | Chrome |
|---|---|---|---|---|---|
| named icon behind a **slot** | `(unlabeled)` | **Search** | **Search** | Search | Search |
| child declares `aria-labelledby` | `(unlabeled)` | **Delete row** | **Delete row** | Delete row | Delete row |
| **two** named icon children | `"Prev"` | **Prev Next** | **Prev Next** | Prev Next | Prev Next |
| nested control **with** text (`?`) | `Deadline ?` | *unchanged* | *unchanged* | absorbs | absorbs |
| nested control **without** text (icon ×) | `Read the report` | **absorbs** | *unchanged* | absorbs | absorbs |
| labelled `<input>` in a group | `Filter` | **absorbs** | *unchanged* | absorbs | — |
| ordinary labelled controls ×3 | *unchanged in every arm* | | | | |

`narrow` absorbs a nested control's label whenever that control renders no text — which is
an icon-only dismiss button inside a card link, a common shape. `guarded` absorbs nothing
and fixes everything `narrow` fixes.

**And the listing gets SMALLER, which is worth saying because the opposite was assumed.**
On this fixture: base 1,371 chars, `narrow` 1,299, **`guarded` 1,265**, `broad` 1,344. A row
that acquires an identity stops needing the `(unlabeled)` marker and the `near=` hint #37
attaches to rows that have none, and those are longer than the name that replaces them.

---

## 3. THE TRAP: the fix expires the name oracle's firing proof — but only on one arm

`audit_name_correctness.py`'s `--selftest` check 1 stood on **#34's `chrome-superset`
shape**, the nested button's `aria-label` Chrome absorbs and we do not. That is *the same
gap this change addresses*, so the proof's life was tied to a change already in flight.
#107 records this probe's proof expiring exactly this way once before.

Asked rather than reasoned about, by swapping `AGL.COLLECT` for each arm and running the
selftest:

| arm | selftest | the disagreement it stands on |
|---|---|---|
| shipped | PASS | `chrome-superset` `'Deadline ?'` |
| **narrow** | **PASS** | `chrome-superset` `'Deadline ?'` |
| **guarded** | **PASS** | `chrome-superset` `'Deadline ?'` |
| **broad** | **FAIL** | *no disagreement at all* |

The narrow arms survive because the nested button **has text** (`?`), so the declared name
is never consulted. **"It happens to survive the arm we shipped" is not a property to rely
on**, so the proof was rebased anyway.

### What it was rebased onto, and why that one outlives the change

**#114's class F** — `title` against name-from-content, where the content is an icon font's
generated glyph:

```html
<style>.ico::before{content:"\e978"}</style>
<a class=ico title="Facebook"></a>
```

> ours `"Facebook"` · Chrome `""` · class `disjoint`

#114 measured this at **139 elements, all of which render no text**, with **22 (16%)** where
Chrome's spec-correct name is a Private-Use-Area glyph that identifies nothing — and
recorded it as a **DECIDED don't-build**: following the spec there destroys a real identity
on a sixth of the class. **A proof anchored on a decision outlives a proof anchored on a
backlog item.** It is also the permanent floor #114 names: a metric reading 1.000 here
would mean we had stopped printing identities #74 requires.

Verified: the rebased proof **PASSES on all four arms including `broad`**, which previously
failed. #34's shape stays in the fixture and is still **reported** (`nested_label_34` in the
selftest's JSON), because it is the shape the next reader will look for and losing it
silently is how the first expiry went unnoticed — it is simply no longer what the pass
depends on.

**One trap of mine, caught by the probe's own guard.** My first arm-comparison script
mutated `AGL.COLLECT` and then called `_collector_src` again, which READS it — so the second
arm was patched on top of the first. `AssertionError: candidate 'child-declared-name' is
half-applied in the source`. That assertion exists for exactly this and it fired on the
person adding a candidate to it.

---

## 4. The regression risks, each bounded with a number

The brief named three. Two are eliminated by construction and the third is real and
measured rather than capped.

### (a) Infinite recursion through a cycle — **cannot happen**

`_declName` reads **attributes**, and resolves `aria-labelledby` to the referenced node's
`textContent`. It never computes another node's *name*, so there is no recursion to loop.
The only traversal is the slot hop, and that one is bounded by the platform:

> Measured on a three-deep slot-forwarding chain (`x-outer → x-mid → x-inner`):
> `assignedNodes({flatten: true})` returns the **final assigned node and never a slot**.

So **there is no depth bound to choose** — which matters, because a chosen number would have
been an argument against the change.

Driven anyway, on a page carrying all three pathological shapes:

| shape | base | narrow | guarded |
|---|---|---|---|
| child's `aria-labelledby` → an **ancestor** of its own control | `''` | `'outer prose here'` | `'outer prose here'` |
| child references **itself** | `''` | `''` | `''` |
| wall clock | 0.04s | 0.03s | 0.03s |

No hang, in any arm.

### (b) The inverse defect — a container absorbing a nested control's label

Real, measured, and the reason `guarded` is the recommendation rather than `narrow`. See
the fixture table in §2: `narrow` absorbs the label of any nested control that renders no
text. `guarded` does not, and CD6 pins it in both directions.

### (c) Cost on deep trees

Timed against **`_collectInteractivePage` itself**, not a tight loop reimplementing the
rule — MEASUREMENT.md records that mistake producing a 3.5×-wrong magnitude. Interleaved,
rotated per replicate, with the A/A floor taken in the same interleave. The page is
adversarial by construction: **every** element child contributes no text, which is the only
condition under which `_declName` is called at all, so this is an upper bound rather than
an estimate.

| page | A/A floor | narrow | guarded |
|---|---|---|---|
| 150 controls × 4 icon children + 40 × depth-12 + 40 slot chains (230 entries) | +1.06% | +3.19% (**+0.30 ms**) | +1.06% — *inside the floor* |
| 700 × 6 + 40 × depth-14 + 40 slot chains (780 entries) | +6.13% | +19.7% (**+6.1 ms**) | +17.7% (**+5.5 ms**) |
| …the same page, re-run under heavier load | **+13.03%** | +20.5% (**+6.3 ms**) | +19.9% (**+6.1 ms**) |

**The absolute delta reproduces and the percentage does not**, which is the reason to quote
the first: between the two runs of the same page the A/A floor doubled (6.13% → 13.03%)
while the measured cost moved by 0.2 ms. The machine was carrying two full-pool A/B runs
throughout; both arms pay that equally, so it cannot align with an arm, but it does inflate
the denominator. **Quote ~6 ms on an adversarial 780-entry page**, against #38's ~24 ms
bridge hop and ~3,600 ms model turn — i.e. ~0.17% of the thing it is spent inside.

### (d) A risk the brief did not name, found by driving it: an enormous name

A child whose `aria-labelledby` points at a large container yields a **10,799-character
name** in a constructed case. The existing `accessibleName` resolver has the identical
exposure for an element's *own* `aria-labelledby`, so this adds a second entrance to a hole
the codebase already has rather than a new one — and #24 removed per-field caps on the
argument that a label is bounded by human authorship, leaving the caller's `max_chars` as
the only bound. **It is reported as a measured distribution rather than capped**, because a
cap would be a chosen number.

---

## 5. Fixtures, and the ablation

Ten checks (`CD1`–`CD9`, with `CD1b`), run against a `git archive HEAD` shadow checkout
with the new suite copied over it, against the same tree with the patch applied, and
against a **third arm with the AccName 2A rule removed** — because `CD9` would otherwise be
a control nothing reaches, which is the vacuity this project has found eleven times.

| arm | whole widget suite | failing |
|---|---|---|
| **HEAD** (pre-fix) | **295 / 299** | exactly `CD1`, `CD1b`, `CD2`, `CD3` |
| **patched** | **299 / 299** | none |
| patched, **2A rule deleted** | 298 / 299 | exactly `CD9` |

**295 + 4 = 299**, and no non-`CD` check fails in any arm, so nothing else in the suite
moved.

**And the WHOLE project suite, not just widgets**, run in both shadow checkouts:

| arm | suites | checks |
|---|---|---|
| HEAD | 20 passed, 1 failed (`widgets`, on the four CD assertions) | 1,635 |
| **patched** | **21 passed, 0 failed** | **1,635** |

So the change breaks nothing anywhere in the project, not merely nothing in the suite it
ships with.

**The row shape is the assertion, not the presence of the string.** `"Search" in listing`
passes against the broken collector, because the word survives in the `near=` hint on a
neighbouring row — #93 found three vacuous fixtures on this exact code path for exactly
that reason, two of them its own. `CD1` asserts `button "Search"`; `CD1b` asserts the row is
not `(unlabeled)`.

**`CD1b` is labelled a fix assertion, not a control, because it FAILS on HEAD.** #114 made
the identical mistake with `LB3` and had to relabel it.

The six controls (`CD4`–`CD9`) pass in **both** the HEAD and patched arms. `CD7`/`CD8` are
what keep this a declaration rule (PRINCIPLES 1): a `_declName` that returned a tag name, a
class token or anything it invented would satisfy `CD1`–`CD3` and nothing else would notice.
`CD6` passes on HEAD and on the fix and **fails on `narrow`**, which is what stops a later
simplification quietly reintroducing the inverse defect. `CD9` passes on HEAD and on the
fix and **fails with the 2A rule deleted**, which is what makes it evidence rather than an
empty check.

---

## 6. Scope decisions, stated rather than buried

- **`alt` and `title` are NOT read by `_declName`.** Both already have `synthLabel`
  branches for the light-DOM case, and a second spelling of a rule that already exists is
  the thing PRINCIPLES 17 forbids. **The residual is real**: an `<img alt>` or a titled icon
  behind a *slot* is still missed.
- **Nothing in the existence path is EDITED, and the entry count still moves slightly.**
  `_contentName` decides a NAME, and every fixture returns the same number of entries in
  every arm. Across the corpus it is **+0.013% (144,961 → 144,980, +19 of ~145k)**, and the
  direction is upward: a row that acquires an identity can escape a demotion that keys on
  having none. Saying "existence is untouched" would be the kind of claim PRINCIPLES 18 is
  about, so the number is printed instead. It moves **toward** PRINCIPLES 3 (more
  identities, not fewer), but `lost_identities` itself was not re-run — see §9.
- **No class name, framework name, wordlist, pixel size or threshold appears anywhere in
  the fix.** The admitting set is two ARIA attributes and the platform's own slot
  assignment. `wa-button` appears nowhere.

---

## 7. The one number that would stop it, and what it found

`BREAKS_A_CORRECT_NAME` counts a row where **Chrome has a name, we had it right, and the
candidate breaks it**. It read **5 on both arms** in the first full pass.

**A zero from that counter is worth nothing until it has fired** (PRINCIPLES 15), so it was
planted against a sabotage candidate — twice, because the first attempt is itself a finding:

| sabotage | sites | rows compared | `BREAKS` |
|---|---|---|---|
| `synthLabel`'s `aria-label` rescue discarded | 28 | 7,673 | **0** |
| `accessibleName`'s `aria-label` read discarded | 26 | 7,632 | **756** |

The first sabotage moved `chars` by +0.08% and changed **zero** compared rows: `synthLabel`
fires only on controls with no name from any other source, and Chrome mostly **ignores**
those rows, so the damage landed outside the compared population entirely. **A sabotage that
changes nothing the comparator looks at is not a firing proof.** It is kept, because that
null is the evidence for the sentence above, and a second one was aimed at the population
the counter actually watches. At 756 the counter is demonstrably alive.

### The 5 were one element, one site, and a spec rule we were missing

All five are the same `<input>` on `w2_cityline` seen at five stages:

> base `Search Keyword(s)` · candidate `Search Keyword(s) icon: search` · Chrome `Search Keyword(s)`

Read off the live page rather than guessed at:

```html
<label class="event-filter-sidebar__search">
  <span class="…__sr-only">Search Keyword(s)</span>
  <i aria-label="icon: search" class="anticon anticon-search" aria-hidden="true">…</i>
  <input>
</label>
```

The icon is **`aria-hidden="true"`**. AccName step **2A** excludes a hidden node, so Chrome
is right and `_declName` was reading an attribute off a node the page had declared absent
from the accessibility tree. `_namable` asks the *rendering* question (`checkVisibility`),
which an `aria-hidden` icon passes — it is painted, it is just not in the tree.

**Ant Design's `anticon` ships `aria-label` and `aria-hidden` on the same element**, so this
is a whole library's idiom rather than one page's mistake, and it would have recurred on
every antd site. The rule added is one line and it is a declaration:

```js
if (n.getAttribute('aria-hidden') === 'true') return '';
```

The node's own attribute is sufficient and no ancestor walk is needed, because the only
descent `_declName` makes is through a `<slot>` and the slot branch re-enters it — so every
node whose attributes are read has been through the test. `CD9` pins it, and the ablation
below shows it is a real control rather than one nothing reaches.


---

## 8. THE LIVE MEASUREMENT — both halves, and the benefit is smaller than #115 implied

`guarded`, 265 live out-of-sample sites (**251 usable, 14 named and unmeasured**), up to
four declared interactions each. Both arms on the SAME page load against ONE oracle read.

### Cost

| | |
|---|---|
| listing chars | 3,298,146 -> 3,302,528 — **+0.133%** |
| per-site chars | **median +0.000%**, mean +0.084%, range −7.78% … +9.08% |
| sites whose listing moves at all | **24 of 251** |
| structured entries | 141,677 -> 141,842 — +0.116% |
| worst case on an adversarial 780-entry page | **~6 ms** (§4c) |

The median site pays **nothing** — the same profile as #31's constraints and #67's
`<svg><title>`: free where nothing is declared, and it costs most where it is worth most.

### Correctness against Chrome

| | |
|---|---|
| rows compared | 90,971 |
| agreement | 0.7651 -> **0.7653** |
| names changed | 496 |
| **improved** | **159** — every one a row where Chrome HAS a name |
| "regressed" | 145 — **every one a row where Chrome has NO name** |
| **`BREAKS_A_CORRECT_NAME`** | **0** |

**The 145 are not regressions, and #114 had to make this exact correction once already**
(*"the name fix is a wash: 80 improved, 83 regressed"* -> all 83 were `chrome-empty`). They
are rows where Chrome's role permits no name and ours moved from nothing to the page's own
declared label — the floor #74 requires us to keep printing. Split on whether Chrome has a
name at all, the change is **159 better, 0 worse**.

### PRINCIPLES 3, asked directly rather than inferred

`audit_generality_live` run from both shadow checkouts on the ten sites where the fix
changes anything — the only sites where it could lose an identity — after its own selftest
was shown to fire on planted losses:

| arm | sites | controls (core / deep / declared) | **lost** | unexpected drop reasons |
|---|---|---|---|---|
| HEAD | 9 usable | 1,710 / 1,838 / 108 | **0 / 0 / 0** | none |
| **patched** | 8 usable | 1,638 / 1,767 / 113 | **0 / 0 / 0** | none |

(The usable count differs by one because the live web does; this is a targeted check, not a
corpus run.)

### Benefit — and this is where the honest number is

| where the gained name was in the BASE listing | rows | share |
|---|---|---|
| **`inside`** the control (a nested row — a click bubbles) | 143 | 63.6% |
| **`elsewhere`** (some unrelated row carried the string) | 80 | 35.6% |
| **`nowhere` — genuinely unreachable** | **2** | **0.9%** |
| total, Chrome-verified subset | 225 | |
| all identity gains incl. rows Chrome ignores | 256 | |

**#115's "9 of 24 have the name nowhere in the listing" does NOT generalise.** At corpus
scale the outright-loss class is **2 rows across 251 sites** — both the same headline on
`w2_shanghai`. That is what this change actually removes from #74's defect class, and it is
small. The honest benefit is therefore mostly ATTRIBUTION (the name lands on the control
rather than on a descendant) plus 159 Chrome-verified corrections, not reach.

**And `elsewhere` overstates its own case**, because the grading matches by NAME STRING: a
page with 29 identical `Remove` buttons scores each one's name as present "elsewhere" on the
others' rows, which is duplicate labelling rather than mis-attribution. 29 of the 80 are
exactly that.

**The gains are concentrated and partly furniture.** Six of 251 sites carry the shape, and
of the 125 gains recorded in detail **37 are `Image for Taboola Advertising Unit`** — an ad
network's own `aria-label`. Naming an ad container correctly is neither harmful nor
valuable.

### `narrow` measured on the same footing — and its extra "benefit" is the defect

`narrow` was re-run with the AccName 2A rule so the two arms differ only in the control
guard. 252 usable sites.

| | `narrow` | `guarded` |
|---|---|---|
| listing chars | +0.078% | +0.133% |
| sites whose listing moves | **54** of 252 | **24** of 251 |
| entries | +0.001% | +0.116% |
| agreement | 0.7631 -> 0.7603 | 0.7651 -> **0.7653** |
| names changed | 836 | 496 |
| improved (Chrome has a name) | 217 | 159 |
| "regressed" (all `chrome-empty`) | 472 | 145 |
| `BREAKS_A_CORRECT_NAME` | 0 | 0 |
| gains `inside` / `elsewhere` / **`nowhere`** | 431 / 70 / **41** | 143 / 80 / **2** |

**Read as a table, `narrow` wins the number that matters: 41 genuinely-unreachable rows
against 2.** Read as ROWS, it is the opposite, and this is the finding:

```
div 'Go to slide 1 Go to slide 2 Go to slide 3 Go to slide 4 Go…'     uni_chula
div 'スライド1 スライド2 スライド3 スライド4 スライド5 スライド6 スライド7 スライド8'   w2_tokyo_metro
div 'Wechsle zu Seite 1 Wechsle zu Seite 2 Wechsle zu Seite 3 W…'     w2_admin_ch
div 'Next slide Previous slide'                                       hi_aajtak
div 'Previous Next'                                                   w2_chicago
div '#'                                                               hi_aajtak
```

**Every one of narrow's 41 is a carousel pagination container absorbing the labels of all
the buttons inside it.** Those buttons are declared controls, each already listed with its
own ref and its own name — which is exactly why `guarded` skips them and `narrow` does not.
Nothing was recovered; a container acquired a composite name made of identities that were
already on their own rows. It is the shape #80's live agent described as *"a name that is
confidently wrong is worse than `(unlabeled-icon)`"*, and it is CD6 occurring on 16 real
sites rather than on a fixture.

**AND IT EXPOSES A FLAW IN MY OWN BENEFIT METRIC, which is why the rows had to be read.**
`nowhere` matches the WHOLE gained string, so a concatenation of N names that are each
already printed scores as "the name was nowhere" — the concatenation is novel even though
every part of it is redundant. The 41 is therefore not 41 recoveries and the 2 is not
directly comparable to it. A count that flatters an arm gets its rows read before it is
believed (#16); doing that reversed what the table said.

`guarded`'s own 2 survive that reading: both are `w2_shanghai`'s
`div '鼓励专业服务业发展 上海推出"数广贷"等专项信贷'`, a single headline rather than a
concatenation of controls.

### The blowup risk, resolved by measurement rather than a cap

Gained-name length across the corpus: **median 10, p90 34, max 34 characters.** The
constructed 10,799-character case of §4(d) has **no live instance**, so no cap is added and
#24's one-bound rule stays intact.

## 9. What this does NOT measure, and what is least certain

- **The sample is the live out-of-sample pool, and the shape is concentrated.** #115 found
  70% of the class on two component-library sites and that holds here: a handful of sites
  carry almost all of it. The cost is ~0 on a site without the shape and the benefit is ~0
  there too, which is the same profile as #31's constraints and #67's `<svg><title>` — free
  where nothing is declared, worth most where it is. **It is not a broad win and should not
  be reported as one.**
- **The two arms were measured in separate passes.** Within each pass, base-vs-candidate is
  interleaved on the same page load against one oracle read, so each arm's delta is sound
  (R3). `narrow` versus `guarded` is a comparison ACROSS passes on a live corpus, so it is
  directional rather than exact — the direction is large enough to act on, the second
  decimal is not. The fixture (§2, CD6) is what actually decides between them.
- **Chrome is an oracle, not ground truth** (#114). A name both derivations get wrong scores
  as agreement, and `BREAKS_A_CORRECT_NAME` can only see rows Chrome names.
- **The benefit buckets are scored only where Chrome also has a name**, which is the subset
  where a gain is VERIFIED correct. `gained_identity_any` is reported beside it because a
  row that stops saying `(unlabeled)` is a gain to the reader whether or not Chrome has an
  opinion — and Chrome ignores a great many icon controls.
- **`alt` and `title` behind a slot are still missed**, by the scope decision in §6.
- **`lost_identities` was run on the TEN SITES THE FIX TOUCHES, not on the corpus.** Those
  are the only sites where it could lose one, and the answer is 0/0/0 in both arms (§8). A
  full 445-site pass was not spent. The mechanism worth naming, if it is ever re-checked:
  a name change can reach the listing's row count through the identical-nested-row collapse
  (#29), because a child that acquires its parent's name and box becomes a merge candidate
  — that collapse **merges refs onto one row rather than dropping any**, `TR8d` pins that a
  declared control survives and keeps its own ref, and the structured entry count moves
  **up**, not down.
- **No live pass through the real extension.** This is fixtures, a frozen-collector A/B and
  an ablation. PRINCIPLES 12 asks for a live pass before committing, and the extension
  cannot be reloaded from here.

### The single thing I am least sure of

**That the control guard's BOUNDARY is in the right place** — not that the guard belongs
(§8 settled that: without it, 16 live sites grow composite carousel names), but that
"declared control" is the right line to draw it on.

The guard is `A|BUTTON|INPUT|SELECT|TEXTAREA|SUMMARY` plus an interactive ARIA role. That
is a declaration and it needs no threshold, which is why it was chosen. But the live data
shows the boundary doing heavy lifting in both directions: on `tix_songkick` the fix
prefixes an artist link with an adjacent element's label and **Chrome agrees exactly on 32
rows**, so composite names are sometimes right — `guarded` keeps those only because that
contributing element is not a declared control. An `<a>` with no `href` is skipped by the
guard though it is not really a control; a `role=group` wrapper is not skipped though it
sometimes is one. Neither case appeared in the 251 sites, which is evidence of rarity and
not of correctness, and card-dense commerce layouts — the shape most likely to probe it —
are thin in this corpus.


---

## 10. Recommendation

**SHIP the `guarded` arm — and do not oversell it.** It is a small, cheap, measured
correctness fix, not the recovery of a large unreachable class.

**What carries the decision:**

| | |
|---|---|
| `BREAKS_A_CORRECT_NAME` | **0**, from a counter shown firing at **756** under sabotage |
| rows that become exact matches with Chrome | **159**, with **0** correct names broken |
| listing cost | **+0.133%** pooled, **median site +0.000%**, 24 of 251 sites move |
| identity loss on the sites it touches | **0 / 0 / 0**, both arms |
| whole project suite | **21/21, 1,635 checks**, against 20/21 on HEAD |
| worst-case collection cost | ~6 ms on an adversarial 780-entry page (~0.17% of a model turn) |
| chosen numbers in the fix | **none** — no depth bound, no cap, no threshold, no list |

**What does NOT carry it, and must be said in the same breath:** the outright-unreachable
class it fixes is **2 rows across 251 sites**, not the per-site figure #115's sample
suggested; six sites carry the shape; and a third of the detailed gains are an ad network's
own label. If the only argument were reach, the answer would be DON'T BUILD.

The argument that actually survives is **correctness at no cost**: 159 rows gain the name
the browser agrees they have, nothing loses a name the browser agrees it had, the median
page pays zero characters, and the rule is two ARIA attributes plus the platform's own slot
assignment — which is a strictly better state than a standing known-wrong spec gap that has
been quoted forward since #34.

**NOT the `narrow` arm.** It fixes the same three shapes and additionally absorbs a nested
control's label whenever that control renders no text — and measured on the same footing
that is not a fixture concern but **16 live sites whose carousel pagination containers
acquire a composite name built from every button inside them** (§8). Its headline advantage
(41 `nowhere` rows against 2) **reverses when the rows are read**: all 41 are that defect,
and the metric scored them as recoveries only because a concatenation of already-printed
names is a novel string.
**NOT the `broad` arm**, which is AccName's own order: it absorbs more, and it is the one
that expires the name oracle's firing proof (§3).

**Conditions on shipping**, both of which this work could not satisfy from here:
1. **A live pass through the real extension** (PRINCIPLES 12). #43 is the entry where 15
   fixtured fixes with no live pass produced seven regressions.
2. The `w2_shanghai` pair is the only genuine reach gain measured; if a live pass finds the
   shape commoner than 2-in-251, that strengthens the case, and if it finds it rarer, the
   case is still the correctness column rather than the reach column.

---

## 11. Reproducing this

A result nobody can re-derive is an anecdote with a p-value (`MEASUREMENT.md` §5). The
candidate lives in the probe with BOTH anchors, so it keeps working whichever side of the
fix the source is on, and `--ab-arm` defaults to the arm this write-up proposes.

```bash
# the firing proof, all four arms (it must PASS on every one)
python tools/audit_name_correctness.py --selftest

# the proposal, full pool, both halves in one pass
python tools/audit_name_correctness.py --candidate-ab --ab-only child-declared-name \
       --ab-arm guarded --conc 6 --stages 4 --out temp/accname2f/guarded2

# the arm it is chosen over, on the same footing
python tools/audit_name_correctness.py --candidate-ab --ab-only child-declared-name \
       --ab-arm narrow  --conc 5 --stages 4 --out temp/accname2f/narrow2

# the counter that would stop it, shown FIRING (756) before any zero is believed
python tools/audit_name_correctness.py --candidate-ab \
       --ab-only sabotage-drop-name-arialabel --every 9 --conc 2 --stages 2 \
       --out temp/accname2f/sabotage2

# and the one that does NOT fire, kept because that null is itself the evidence
python tools/audit_name_correctness.py --candidate-ab \
       --ab-only sabotage-drop-aria-label --every 9 --conc 2 --stages 2
```

The ablation is a `git archive HEAD` shadow checkout with the new suite copied over it,
plus a second shadow with the patch applied and a third with only the AccName 2A line
removed — because `CD9` is otherwise a control nothing reaches.

**Artefacts:** `temp/accname2f/{guarded2,narrow2,sabotage,sabotage2}/candidate_ab.json`.
**Not in the repo:** the two patches, which are proposals rather than changes. They were
generated by applying the edit to a copy and diffing, so they are guaranteed to apply, and
`verify_patch` asserts the patched file's extracted collector is **byte-identical, comments
aside, to the arm that was measured** — because "it looks like the same code" is the kind
of claim PRINCIPLES 18 is about.
