# What the 2.3% is: every name-disagreement class, dispositioned

**Probe:** `tools/audit_name_correctness.py` (extended: `--ab-only`, three new candidates)
**Successor to:** `docs/research/NAME-CORRECTNESS-2026-11.md` (#93), corrected by #107/#108
**Artefact chased:** `temp/name_correctness/full108/pass0.json` — #108's 252-site run
**Collector under test:** `_collectInteractivePage`, extracted verbatim from
`extension/background.js` at `d844947`
**Date:** 2026-11-19

> **Headline.** #108 put `src=name` agreement with Chrome's own AccName at a **per-site
> median of 0.9766**. Nobody had asked what the other 2.3% IS. Taken apart mechanism by
> mechanism: **51% of the `src=name` residue is Chrome's ROLE forbidding a name at all**
> (758 of 1,491 rows — `generic`, a decorative `<img alt="">`, a `role=presentation`
> `<svg>`, an attributed `(post-key)`), which is #74's argument one step up from `src=text`
> and is not a wrong name. **A further ~27% is the `title`-versus-name-from-content half
> #93 deliberately deferred — and measuring it CONFIRMS the deferral rather than closing
> it**: on 16% of that class Chrome's spec-correct answer is a Private-Use-Area icon-font glyph
> that identifies nothing, every one of those 139 elements renders no text at all so the
> screen oracle abstains **139/139**, and the remaining 60% is genuinely two-sided. That is
> a decided DON'T-BUILD, not an open item.
>
> **Three defects are genuinely ours, and all three are one concept spelled twice.** A
> wrapping `<label>`'s name was computed on a **DETACHED clone**, where
> `checkVisibility()` is false for every element and `getComputedStyle().display` is `""` —
> so only the label's direct text nodes survived, `<label><input><span>Text</span></label>`
> resolved to `''`, and the control fell through to the HTML `name` attribute. On a radio
> group every member shares that attribute, so twelve radios printed the identical
> `name="icon-family-tTQcQzZF" (post-key)` and Yokohama's search box printed `name="q"`
> where the page declares サイト内検索. `aria-labelledby` was resolved with `innerText`,
> **which an SVG element does not have** — #37 fixed exactly that in `_contentName` and
> this second spelling was left behind, so 40 live icon rows printed `(unlabeled-icon)`
> for a name the page had declared. And a `<br>` contributed nothing, **fusing the two
> lines either side** — #52's defect in a second function.
>
> **Six A/B runs, both arms on the SAME page load against ONE oracle read: 129 names
> changed, 100 improved, 0 rows where a correct name is broken, and entries unchanged in
> every targeted run.** That zero is a measurement rather than a silence: the counter was
> planted against and **fires at 2** on a sabotage candidate. Full suite 21/21, 1,625
> checks, ALL GREEN; ablated against a `git archive HEAD` shadow checkout, the 5
> fix-assertions FAIL and all 8 controls PASS, and the per-site median moves **+0.0000**
> on five of the six runs — the defects are concentrated, so the headline will not
> visibly change.
>
> **The permanent floor: about half of this residue can never close**, because it is rows
> where the spec says there is no name and we print the author's string anyway — which
> #74 proved we must keep doing.

---

## 1. The question #93 and #108 left

#93 built the only independent ruler in this project — our derived accessible name against
Chrome's own `Accessibility.getFullAXTree` — and classified the disagreements into nine
buckets. #108 ran it at full scale and reported the headline. Neither asked, per bucket,
**whether we are wrong or Chrome is**, with a number behind the answer.

That matters because the obvious reading of "0.9766" is "2.3% of our names are wrong", and
it is not. #93 already showed that for the POOLED figure (three quarters of the gap is
`chrome-empty`). Nobody had done it for the `src=name` population, which is the one the
headline quotes.

**And `measure_findability` cannot see any of this.** It scores `find` against the
collector, so a wrong name both agree on scores a hit (#92 says so in as many words).
`lost_identities` cannot see it either: a name that moves to a different row satisfies
both its arms.

---

## 2. Method

### What is reused

The probe, the collector, the sample, the interaction driver and the out-of-sample guard
are all #93's, unchanged. The residue analysis reads #108's saved artefact rather than
re-running it, so the class counts below are *that* run's, not a fresh sample.

### What is new: `--ab-only`

`_collector_src` applied EVERY candidate at once. With two fixes already shipped and a
third not, an A/B would have silently measured all three together — a count standing in
for an inventory (PRINCIPLES 16), one level up. `--ab-only NAME` moves one candidate and
leaves every other exactly as the source has it; the isolation is asserted, not assumed.

A second change was forced by the data: a candidate that INSERTS a line keeps the line it
inserted before, so raw occurrence counting reports `pre=1 post=1` and the direction is
undecidable. The `contents-is-not-invisible` candidate already carried a hand-written
special case for this; it is now the general rule (`na = count(a) − nb * b.count(a)`)
rather than written a second time.

### The counting unit

The saved rows are capped per read and are a **head slice** of each page in document
order, so class SHARES taken from them are not a census. Two things are therefore kept
apart throughout:

* **Exact class totals** come from the probe's uncapped `cls_roles` histogram
  (class × Chrome-role × src), which is a full count.
* **Mechanism attribution within a class** comes from the saved rows, de-duplicated to
  distinct `(site, tag, ours, theirs)` — 13,340 rows collapse to **5,637 distinct
  disagreements** — and is quoted with its coverage (49–87% of each class's population).

---

## 3. The disposition, by class

Exact totals, #108's 252-site run: 101,423 rows compared, 76,525 exact, **24,898
disagreements**.

| class | total | `src=name` | verdict | ours? |
|---|---|---|---|---|
| `chrome-empty` | 18,928 | 758 | **both right, different questions** — Chrome's role forbids a name; we print the author's string | no |
| `punctuation-only` | 2,132 | 29 | Chrome spec-correct (`::before` glyphs, U+200B); **ours better for this reader** | no |
| `chrome-superset` | 1,601 | 91 | #34: Chrome absorbs a descendant's NAME, we concatenate descendant TEXT | **known, unfixed** |
| `case-only` | 1,113 | 20 | CSS `text-transform`; `find` folds case, so it costs nothing | no |
| `disjoint` | 555 | 338 | splits — see §4 and §5 | **part ours** |
| `ours-superset` | 278 | 215 | splits — `title` carrying a boilerplate affix | mostly not |
| `ours-empty` | 162 | 0 (by definition) | **OURS** — `aria-labelledby` → non-HTML target, and #34's degenerate case | **part ours** |
| `partial-overlap` | 87 | 40 | splits with `disjoint` | **part ours** |
| `whitespace-only` | 42 | 0 | **OURS** — a `<br>` the screen renders and we dropped | **ours** |

### The `src=name` residue on ONE denominator

1,491 rows (20,199 compared, 18,708 exact). **Classes are disjoint and exact; mechanisms
cut ACROSS classes and are scaled from the saved rows**, and the two are never mixed inside
a figure — the error #22 records.

| class | rows | share | what dominates it | verdict |
|---|---|---|---|---|
| `chrome-empty` | 758 | **51%** | Chrome's ROLE forbids a name: `image` 314, `generic` 245, form controls whose only handle is the wire key 127 | both right |
| `disjoint` | 338 | 23% | `title` over name-from-content; ~56 are the lost `<label>` | mostly two-sided; part OURS |
| `ours-superset` | 215 | 14% | a `title` carrying a boilerplate affix (`[另開新視窗]…`) | Chrome cleaner, ours not wrong |
| `chrome-superset` | 91 | 6% | #34 — Chrome absorbs a descendant's NAME | known, unfixed |
| `partial-overlap` | 40 | 3% | same family as `disjoint` | mixed |
| `punctuation-only` | 29 | 2% | U+200B / `::before` glyphs | ours better for this reader |
| `case-only` | 20 | 1% | CSS `text-transform` | undecidable, costs nothing |
| **total** | **1,491** | | | |

Across those classes, two mechanisms account for most of it:

| mechanism | rows (scaled) | share | spans |
|---|---|---|---|
| `title` over name-from-content (§5) | **~402** | ~27% | `disjoint` + `ours-superset` + `partial-overlap` |
| a `<label>` exists and we printed the POST KEY (§4.1) | **~108** | ~7% | `disjoint` ~56, `chrome-empty` ~31, `case-only` ~12, `punctuation-only` ~9 |

The `<label>` figure uses the one signature that is not a judgement — an associated
`<label>` AND `synth == 'name-attr'`, i.e. we demonstrably fell through to the post-key
branch, which can only happen when label resolution returned `''`. **It is a lower bound**:
the A/B moved rows on sites this signature search never named (`w2_dhaka`, `w2_courts_ca`,
`w2_tinkoff`, `w2_athens`, `w2_du_bd`), because a labelled control with no `name` attribute
shows up as an empty identity rather than as a post key.

### Mechanism census, distinct elements (saved sample, 49–87% coverage per class)

| mechanism | all | `src=name` | sites | verdict |
|---|---|---|---|---|
| C role prohibits a name | 3,628 | 34 | 214 | both right |
| P CSS generated content (`::before`/`::after`) | 531 | 7 | 70 | Chrome by the spec, ours for the reader |
| I Chrome absorbs a descendant name (#34) | 411 | 20 | 85 | Chrome by the spec, us by the screen |
| N CSS `text-transform` | 403 | 4 | 54 | undecidable, costs nothing |
| **F `title` over name-from-content** | **150** | **138** | **52** | **two-sided — DON'T BUILD, §5** |
| E `chrome-empty`, other | 220 | 24 | 53 | both right |
| O invisible character (U+200B, U+3000) | 82 | 0 | 7 | ours better |
| **A a `<label>` exists and we printed the post key** | **36** | **36** | **11** | **OURS — fixed, §4.1** |
| A2 no label; post key vs a placeholder Chrome used | 29 | 29 | 28 | both printed (#6 keeps them apart) |
| D `title`/`alt` on a role Chrome did not name | 23 | 17 | 12 | both right |
| B post-key, attributed `(post-key)` | 20 | 20 | 14 | both right |
| **M separator the screen has** | **17** | **0** | **10** | **OURS — fixed, §4.3** |
| K descendant NAME not TEXT (#34 degenerate) | 13 | 0 | 7 | #34, unfixed |
| **J `aria-labelledby` → non-HTML target** | **8** | **0** | **1** | **OURS — fixed, §4.2** |
| H other mismatch | 61 | 6 | 26 | mixed, unattributed |

### `chrome-empty | src=name` is HALF the headline residue, and it is not wrong names

758 of the 1,491 `src=name` disagreements. By Chrome's role, exactly:

| Chrome role | n | what it is (saved sample) |
|---|---|---|
| `image` | 314 | an `<svg role=presentation>` named by its own `<title>` (#67's rule, 64 of 80 saved), and `<img alt="" title="…">` (16 of 80) |
| `generic` | 245 | a `title` on a `<div>`, `<span>`, `<i>`, `<picture>` or href-less `<a>` — 100 of 119 saved carry one. ARIA 1.2 gives `generic` **Name From: prohibited** |
| `textbox`/`combobox`/`radio`/`checkbox` | 127 | the HTML `name` attribute, **printed with `(post-key)`** (100 of 114 saved); 29 of them are §4.1's defect |
| `link` | 50 | |
| `button`/`listitem`/`option` | 22 | |

**The `alt=""` case, measured rather than assumed** (#93 named it as explicitly out of
scope and gave it no number). On a fixture driven through both derivations:

| markup | ours | Chrome |
|---|---|---|
| `<img alt="" title="Mother and toddler">` | `name="Mother and toddler"` | `''` |
| `<img title="Only a title">` | `name="Only a title"` | `Only a title` |
| `<img alt="Real alt" title="A tooltip">` | `name="Real alt"` | `Real alt` |

HTML's `alt=""` declares the image decorative and the computation ends there; we treat the
empty string as falsy and fall through to `title`. **Verdict: no action.** It adds an
identity where the page declared none, including on the wrapping `<a>`, which Chrome
reports as an unnamed link — and an unnamed link is a defect on the PAGE, not a reason for
us to print nothing. Same verdict as `punctuation-only`: Chrome is spec-correct and our
string is the more useful one. Recorded with its number so it is not re-opened as an
unknown.

---

## 4. The three defects that are ours

Each was found by chasing a saved row to its mechanism, reproduced OFFLINE against the
shipped collector before anything was written, and measured with both arms on one page
load against one oracle read.

### 4.1 A wrapping `<label>`'s name was computed on a DETACHED clone

**The rows that led here.** `ax_from=relatedElement` — Chrome says it read a related
element — while our row prints the HTML `name` attribute:

```
uni_chula      input[radio]  ours='language'                chrome='ไทย' / 'English' / '中文'
wc_webawesome  input[radio]  ours='icon-family-tTQcQzZF'    chrome='Classic Solid' … ×12
w2_yokohama    input[text]   ours='q'                       chrome='サイト内検索'
w2_athens      input[checkbox] ours='checkbox-57[]'         chrome='Συναινώ στην αποστολή ενημερώσεων.'
w2_moscow      input[checkbox] ours='showFree'              chrome='Бесплатные'
```

Every one has `labels: 1` — the DOM says a `<label>` is associated — and we produced the
wire key.

**The mechanism, measured on a clone rather than reasoned about.** The branch clones the
label, removes the control and calls `_contentName(clone)`, which implements AccName's
"the labelled control's own subtree is not traversed". `_contentName` applies `_namable`
to every element child, and `_namable` asks `checkVisibility()`:

```
clone child  <span>ไทย Thai</span>
  checkVisibility({visibilityProperty:true})   false
  getComputedStyle(n).display                  ""        <- a detached node has no box
```

So **every element child of the clone is skipped** and only direct text nodes survive.
Against the shipped collector, four shapes:

| shape | shipped row |
|---|---|
| `<label><input><span>Thai language</span></label>` | `input[radio] name="lang" (post-key)` |
| `<label><input>English direct</label>` | `input[radio] name="English direct"` |
| `<label for=x><span>For-label span</span></label>` | `input[radio] name="For-label span"` |
| no label at all | `input[text] name="plain_post_key" (post-key)` |

Only the first fails, and it is the common one — an element child is how every design
system styles a radio or checkbox label.

**Why it is worse than a disagreement.** The wire key is shared by every member of a radio
group, so the twelve `wc_webawesome` radios collapse to ONE identity and `find` cannot
separate them. And the words do not vanish: on the fixture the PRE-fix listing reads

```
ref_15 | select value="France" near="Country"
ref_19 | input[checkbox] near="CountryFranceSpain"
```

— the label text lands on a *neighbouring* row through `near=`, attributed to a different
control. That is #93's `lost_identities` reconciliation arriving from the other side.

**The fix.** Exclude the control by IDENTITY on the LIVE tree. `_contentName(node, skip)`
and `_deepText(node, depth, skip)`; the clone goes away. `_namable` then asks its real
question of real nodes, so the eBay `display:none` guard (#37) is intact by construction.

### 4.2 `aria-labelledby` resolved with `innerText`, which an SVG element does not have

```html
<svg role="presentation" aria-labelledby="handshake-outline-desc-1">
  <desc id="handshake-outline-desc-1">handshake icon</desc>
```

`idRoot.getElementById(id).innerText` on an SVG `<desc>` is `undefined`, so `|| ''` wins
and the declared name resolves to nothing. The row prints `(unlabeled-icon)`. Measured on
the shipped collector, with the boundary that decides the fix:

| target | `typeof innerText` | ours | Chrome |
|---|---|---|---|
| SVG `<desc>` | `undefined` | `''` | `handshake icon` |
| SVG `<title>` | `undefined` | `"Twitter"` (rescued by #67's direct-`<title>` rule, not by this path) | `Twitter` |
| HTML `<span hidden>` | `string` | `name="Hidden name wins"` | same |
| HTML `<span>` | `string` | `name="Visible target"` | same |

**#37 established this exact fact for `_contentName`** — *"an SVG element has no
`innerText` at all, so the name path fell through to `textContent`"* — and fixed it there.
This resolver is the same question in a second spelling (PRINCIPLES 17).

**`textContent`, and NOT the composed walk.** AccName 1.2 step 2A excludes a hidden node
*unless it is directly referenced*, and an `aria-labelledby` target is. `_namable` rejects
an SVG `<desc>` outright (`checkVisibility() === false`, measured), so `_deepText` returns
`''` and would not fix anything. The HTML branch is untouched, which is what keeps the
hidden-target case working — pinned by LBY2.

**A third spelling exists and is left alone, with its reason.** `aria-describedby` /
`aria-errormessage` (the `help=` / `error=` reader, #37) uses
`(n.innerText != null ? n.innerText : _deepText(n))` behind a `_namable(n)` gate. That is
the same hazard on the DESCRIPTION path, it has **zero measured instances** in this corpus,
and widening it changes what `help=` prints — which #37 priced and #41/#44 require
measuring again. Reported, not changed.

### 4.3 A `<br>` contributed nothing, fusing the two lines either side

`whitespace-only` is 42 rows and after #93's display-aware separator it is one mechanism:

```
w2_onlinebooks  ours='3420 Walnut StreetPhiladelphia, PA 19104-6206'
                chrome='3420 Walnut Street Philadelphia, PA 19104-6206'
                screen='3420 Walnut Street Philadelphia, PA 19104-6206'
w2_jr_west      ours='HokurikuArea'          chrome/screen='Hokuriku Area'
w2_tra_tw       ours='列車時刻車次查詢'        chrome/screen='列車時刻 車次查詢'
```

`document.querySelector('br').innerText === ''`, measured — so the `if (t.trim())` gate
drops it and the runs either side join. **This is #52's defect in a second function:** #52
fixed `search_page`'s walk for exactly this (*"`<br>` has no children, so `walk()` returned
`''` and `add()` dropped it — FUSING the lines"*). The screen oracle is decisive and
one-sided here, because unlike §5 these elements DO render text.

Verified that the other separator shapes are already right and must not move:

| shape | screen | shipped |
|---|---|---|
| `<span class=inline-block>Hokuriku</span><span>Area</span>` | `Hokuriku Area` | `Hokuriku Area` |
| flex with `gap` | `列車時刻 車次查詢` | `列車時刻 車次查詢` |
| `<span>Save</span><span>changes</span>` inline | `Savechanges` | `Savechanges` |
| `<br>` | `3420 Walnut Street\nPhiladelphia` | **fused** |

---

## 5. The biggest class in the residue is a DECIDED don't-build

`title`-over-name-from-content is **~402 of the 1,491 `src=name` disagreement rows —
~27%**, the second-largest mechanism after `chrome-empty`, on 45 sites. (288 of the 425
saved rows of its class carry a `title` and no `<label>`; scaled onto that class's exact
population of 593. 139 distinct elements.) #93 measured it, named it the harder half, and
deferred it to "its own measurement of both halves". This is that measurement, and it
**confirms the deferral**.

The current code already gates `title` on the element having no text of its own. The class
exists because the element's content is NON-TEXTUAL — an `<img>`, an icon font `<i>`, an
inline `<svg>` — so `innerText` is empty and `title` is the only thing left, while AccName
2F gives Chrome the descendant's NAME. **All 139 render no text: the screen oracle
abstains 139/139.** Split by whether Chrome's answer identifies anything (a letter or a
digit in any script — #29's rule):

| | n | share | |
|---|---|---|---|
| **Chrome's name identifies NOTHING** | 22 | 16% | `th_sanook`: ours `Facebook`, Chrome `\ue978` — a Private-Use-Area icon-font glyph. 23 of 139 contain a PUA codepoint |
| ours = Chrome + a boilerplate affix | 33 | 24% | `gov_tw_moi`: ours `[另開新視窗]內政部臉書`, Chrome `內政部臉書` — **Chrome cleaner** |
| genuinely different, no oracle | 84 | 60% | ours `全臺防災士突破20萬人-防災士心得分享` vs Chrome `影片縮圖` ("video thumbnail"); ours `Trang chủ` vs Chrome `VNU Logo` |

**Following the spec here would destroy a real identity on 16% of the class and improve
24%**, with 60% undecidable by anything this project can measure. "Chrome is spec-correct"
is true and is not sufficient — the same conclusion `punctuation-only` and `case-only`
already reached, now with a count.

**What would reopen it:** a task-success ruler, which `MEASUREMENT.md` §6 records as not
existing for our ladder. Not another spec reading.

---

## 6. Measurement

### Ablation — `git archive HEAD` shadow checkout, suite copied over it

| check | HEAD | patched |
|---|---|---|
| LB1 wrapping label names its control | **FAIL** | PASS |
| LB2 the control's own subtree is still excluded | **FAIL** | PASS |
| LB3 the eBay `display:none` guard survives | **FAIL** | PASS |
| LBY1 `aria-labelledby` → SVG `<desc>` | **FAIL** | PASS |
| BR1 a `<br>` separates | **FAIL** | PASS |
| LB3b/LB4/LB5/LB6 CONTROL | PASS | PASS |
| LBY2/LBY3 CONTROL | PASS | PASS |
| BR2/BR3 CONTROL | PASS | PASS |
| suite total | 284/289 | **289/289** |

Full suite with the patch applied: **21/21 suites, 1,625 checks, ALL GREEN, 0 failed, 0
skipped.**

**Two of the controls had to be built twice**, and that is the point of having them. LB3
was written as a control and it **fails on HEAD** — pre-fix the whole label resolves to
`''`, so asserting only that the hidden text is absent passes vacuously. It is a second
assertion of the fix now, and LB3b (the `label[for]` branch, which the change does not
touch) is the control that carries the same property in both arms. And LBY2/LBY3 failed on
the first run for a reason that was the FIXTURE's: an `<svg>` with no width/height is a
300×150 replaced box, which pushed the two control buttons below the fold of a
viewport-scoped listing.

### A/B — both arms on the SAME page load, ONE oracle read

Movement, not a level: a row is IMPROVED when base disagreed with Chrome and the candidate
agrees. Split on whether Chrome has a name at all, because a row whose role permits none
cannot be "named wrongly" — the split that made #93's own A/B readable.

| candidate | sample | sites | changed | improved | "regressed" | **breaks a correct name** | chars |
|---|---|---|---|---|---|---|---|
| live-label-not-clone | random (`--every 3`) | 89 | 22 | 12 (all Chrome-named) | 10 (all Chrome-EMPTY) | **0** | +0.02% |
| live-label-not-clone | targeted | 14 | 41 | **31** | 10 (all Chrome-EMPTY) | **0** | +0.33% |
| labelledby-non-html | random | 89 | 2 | 2 | 0 | **0** | +0.01% |
| labelledby-non-html | targeted | 7 | 32 | **32** | **0** | **0** | +0.02% |
| br-is-a-separator | random | 89 | 14 | 5 | 0 | **0** | +0.06% |
| br-is-a-separator | targeted | 9 | 18 | **18** | **0** | **0** | −0.00% |
| | | | **129** | **100** | **20** | **0** | |

**The 20 "regressions" are not wrong names, and the dump is what shows it.** Every one is a
row where Chrome's role permits no name and ours moved from `''` or a post key to the
page's own label:

```
uni_chula     input   'language'       -> 'ไทย' / 'English' / '中文'
w2_athens     input   'checkbox-57[]'  -> 'Συναινώ στην αποστολή ενημερώσεων.'
w2_du_bd      input   'search_type'    -> 'People' / 'Website'
w2_tinkoff    input   ''               -> 'Соглашаюсь получать рекламу про кешбэк…'
w2_dhaka      i       ''               -> 'সকল সেবাসমূহ দেখুন'
w2_courts_ca  svg     ''               -> 'Toggle search form and secondary navigation'
```

Five scripts, six sites, and the arithmetic classifies them as regressions because the base
arm's `('' , '')` compared as `exact`. This is #93's lesson — *"the 83 regressions are not
wrong names"* — in its purest form, and it is why the split is reported rather than the
total.

### Per site: the headline will not move, because the defects are CONCENTRATED

The same six runs, per site (n >= 20 compared rows, all `src` pooled):

| candidate | arm | sites | sites that MOVED | per-site median | largest single site |
|---|---|---|---|---|---|
| live-label-not-clone | random | 81 | 6 | +0.0000 | `w2_athens` +0.0045 |
| live-label-not-clone | targeted | 14 | 8 | +0.0000 | `wc_webawesome` +0.0071 |
| labelledby-non-html | random | 82 | 1 | +0.0000 | `w2_titech` +0.0058 |
| labelledby-non-html | targeted | 7 | 1 | +0.0000 | **`w2_nationwide` +0.0688** |
| br-is-a-separator | random | 82 | 3 | +0.0000 | `w2_uba` +0.0132 |
| br-is-a-separator | targeted | 8 | 6 | +0.0062 | `w2_jr_west` +0.0214 |

**8 of 81, 1 of 82 and 3 of 82 sites move at all.** The per-site median — the statistic
the headline quotes — stays at +0.0000 on five of the six runs. So the honest prediction
is that **0.9766 will not visibly change**, and that on the sites carrying the shape the
gain is large: +6.9 points on `w2_nationwide` alone.

That is the right way for this to come out. A defect worth ~100 rows out of 1,491 cannot
move a median over 168 sites, and a change that DID move it would be changing something
other than a defect. `w2_titech` is a site the mechanism search had not identified, so the
`aria-labelledby` case is slightly wider than the single site that produced it.

### The counter that would have stopped this was shown to FIRE

`BREAKS_A_CORRECT_NAME` — Chrome has a name, the base arm had it right, the candidate
breaks it — is **absent from all six runs**. A counter nobody has seen fire is worth
nothing (PRINCIPLES 5, 15), so it was planted against: a sabotage candidate that throws
away every wrapping-`<label>` name, on a fixture of two labelled controls.

```
  SABOTAGE   BREAKS_A_CORRECT_NAME = 2   <- fires
  REAL FIX   BREAKS_A_CORRECT_NAME = 0
```

**The first version of that proof read 0 on BOTH arms** and would have been reported as a
firing proof. Its fixture used `label[for]`, which goes through a different branch, so the
sabotage never reached the code under test. Fixed by using wrapping labels. Eleventh
vacuous fixture in this project, second of mine today.

### Drift

**No drift floor is quoted beside these deltas, because the design removes drift rather
than bounding it**: the two arms are two `page.evaluate` calls milliseconds apart against
the same DOM, and Chrome's AX tree is read ONCE and used for both. The pooled levels move
+0.0000 / +0.0001 / +0.0002 (random) and +0.0019 / +0.0048 / +0.0065 (targeted) — the
random figures are at or below #93's back-to-back floor of **0.0015 pooled**, which is the
honest reading: **129 rows out of ~115,000 compared cannot move a pooled rate, and the
result is the direction of those 129, not the level.**

**Entries are unchanged in all three targeted runs** (24,523 → 24,523; 17,507 → 17,507;
4,745 → 4,745). On the random `live-label` run entries move by **one** across 45,618 — a
name change can flip the same-box collapse, whose richness score reads `name.length`.
Reported rather than rounded away.

### The targeted samples are not prevalence, and are labelled so

The random `--every 3` subset excludes `w2_nationwide` and `wc_webawesome`, which carry the
heaviest instances of two of the three mechanisms — which is why `labelledby` reads 2 rows
there and 32 on the sites where it lives. The random runs are the prevalence figure; the
targeted runs are the concentration. Neither is quoted as the other.

---

## 7. The permanent floor

**About half of the `src=name` residue cannot close, and the reason is a decision this
project already made.**

* `chrome-empty | src=name` = **758 of 1,491 (51%)**. Chrome returns nothing because the
  role prohibits or does not author a name — `generic`, a decorative `<img alt="">`, a
  `role=presentation` `<svg>`, a form control whose only handle is the wire key we mark
  `(post-key)`. We print the author's string. #74 is the proof that printing nothing there
  is the worse error: 118 ptable.com tiles were present in every presence metric this
  project has and unreachable by their own printed label until the blanking rule was
  narrowed.
* `punctuation-only` (29 at `src=name`, 2,132 pooled), `case-only` (20 / 1,113) and the
  icon-glyph part of `title`-over-content: Chrome is spec-correct and **ours is the more
  useful string**. A U+200B in a name is unqueryable; a `U+E978` icon-font glyph
  identifies nothing.
* `chrome-superset` (91 at `src=name`, 1,601 pooled) is #34 and is a completeness gap on one shape, recorded as a
  characterisation since #34 and still unfixed.

So the number to expect is not 1.0. **A metric that measured agreement at 1.0 would mean we
had stopped printing identities the spec forbids and #74 requires** — the rate would rise
and the listing would get worse. That sentence is what 0.9766 is worth: the remainder is
mostly a different claim being made on purpose, and the part that was a defect was three
one-concept-spelled-twice bugs worth **~108 + ~17 + ~8 rows** — under a tenth of the
residue, which is why §6 predicts the headline will not visibly move.

---

## 8. What this does not establish

* **Chrome is an oracle, not ground truth.** A name both derivations get wrong scores as
  agreement. §5 is the case where Chrome is spec-correct and plainly worse.
* **This is a head slice.** Mechanism attribution comes from the saved rows (49–87% of each
  class, in document order per read). The class TOTALS are exact; the mechanism SHARES are
  a sample and are labelled as one.
* **Nothing here says whether a name is USEFUL**, only whether it is the one the browser
  computes. #75 tried to measure that and found the benchmark substrate cannot carry it.
* **The sample is inherited and survivorship-biased.** #85's screening of 445 candidates;
  roughly 180 a headless browser could not reach are absent before this starts, 112 of them
  behind a consent wall or a bot block. No user-agent spoofing and no bot-check evasion.
* **One path per site, declaration-driven interactions only.** Hover-only menus, logins and
  cross-origin frames are not reached.
* **The `<br>` fix has the thinnest live base**, 18 targeted rows against 41 and 32. Its
  blast radius was checked rather than assumed: `_deepText` has exactly **three**
  consumers — itself, `_contentName` (names), and #37's `aria-describedby` /
  `aria-errormessage` reader (`help=` / `error=`). `get_page_text` does not use it, which
  an earlier draft of this sentence got wrong by reading instead of grepping. Every one of
  those consumers `\s+`-collapses, so a `'\n'` becomes the space `innerText` and Chrome
  both put there.

---

## 9. Mistakes made while measuring this

**1. The first fixture read `(post-key)` on a name that came from a label — and that was a
stale DOM expando, not the fix misbehaving.** Running both arms on one page left
`el.__abSynthAttr = 'name-attr'` from the base arm, and nothing ever clears it. Re-running
the candidate FIRST on a fresh page gave the clean row. **It is a real latent defect of its
own**: `__abSynthAttr` is set at five sites and cleared at none, so once a control is named
from the wire key it keeps `(post-key)` on every later read even after the page gives it a
`<label>` — a false provenance claim in the field #41 added so an agent could discount one.
The same expando-survival class #27 records for `_note`. **Not measured and not proposed**:
it needs its own prevalence number, and a two-read fixture rather than a one-read one.

**2. My own checks put a backslash inside an f-string expression, seven times.** C45 forbids
it (a SyntaxError before 3.12 while `pyproject.toml` advertises >=3.10) and PRINCIPLES 15
says the rule "is not learnable at the speed it is violated". Caught by running the
contracts suite, hoisted, re-run clean.

**3. The comments nearly broke the probe's own A/B arms.** Every explanatory comment I
wanted to add landed INSIDE an anchor the probe matches on, which is how
`audit_retext_*.py` expired and how #93's first bidirectional version silently handed back
the shipped collector as its baseline. Resolved by splitting: long prose goes ABOVE the
anchors in `background.js` where it is outside both arms; the one- and three-line comments
live in the probe's POST text as well, byte for byte, so a reflow raises loudly instead of
measuring a build nobody runs. **Verified both ways**: `_collector_src` builds both arms
against the unpatched source AND against the patched one.

**4. "Follow the spec" was my first instinct on class F and it was wrong.** The reading was
that `title` beating name-from-content is a straight inversion of AccName 2F before 2I, so
fixing it is unambiguous. The data says Chrome's spec-correct answer is a PUA icon glyph on
16% of the class. #93 deferred this on judgement; the measurement agrees with the judgement
and not with the spec reading.

---

## 10. Reproducing

```bash
# the fixtures, both arms, against whichever side of the fix the source is on
python tools/audit_name_correctness.py --selftest

# one candidate isolated, both arms on the same page load, one oracle read
python tools/audit_name_correctness.py --candidate-ab \
    --ab-only live-label-not-clone --every 3 --conc 4 --stages 3 \
    --out temp/name_correctness/ab_label

# the ablation
git archive HEAD | tar -x -C /tmp/shadow && cp tools/test_widgets.py /tmp/shadow/tools/
cd /tmp/shadow && python tools/test_widgets.py      # 284/289: LB1 LB2 LB3 LBY1 BR1 FAIL
```

New checks: **LB1–LB6, LBY1–LBY3, BR1–BR3** in `tools/test_widgets.py` (13 checks, 8 of
them controls).

## 11. What is OWED

**A live pass (PRINCIPLES 12).** The change is verified through a real Chromium — every
suite does that, and so do the six A/B runs over real sites and real Chrome AX trees over
CDP. What is NOT verified is the extension boundary, and it cannot be from here: the diff
is unapplied, and `sw_info` reports the running service worker at **71,710s old** with
`extension_code_changed_since_worker_start` already naming `background.js` from earlier
work, so the live browser is stale regardless. Reload at `chrome://extensions` after
applying.

**#19's "the op router is the untested link" does not apply to this change**, which is
why that is said rather than assumed: the diff adds no op, no tool parameter and no
emitted string, and every line is inside `_collectInteractivePage`. There is no router
surface and no string contract to ship inert.

**The checks and the diff must land together.** With `tools/test_widgets.py` updated and
`extension/background.js` not, the suite is **284/289** with exactly LB1, LB2, LB3, LBY1
and BR1 failing — which is the ablation arm, and is the expected state until the diff is
applied.
