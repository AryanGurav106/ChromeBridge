# Stage generality, re-measured after 49 commits — and what the instrument cannot see

**Probe:** `tools/audit_stage_generality.py` (unchanged since the run it was written for)
**Collector under test:** `_collectInteractivePage` @ `178c8d208d19a6ea`
(`extension/background.js` @ `7b4827ef7c0338e1…`, repo **`d844947`**)
**Date:** 2026-11-19
**Supersedes nothing; successor to** `STAGE-GENERALITY-2026-11.md` (#89), which is the
baseline every number here is compared against.

---

## The gap this closes

The project's claim is "works on any site **at any stage**". After today's work it rested
on two numbers of very different weight:

| | |
|---|---|
| **any site** | #105 — 258 live out-of-sample sites, **first paint only**, 0 identities lost |
| **at any stage** | #89 — 255 sites through four compounding interactions, 0 lost — but **49 commits ago** |
| | #104 — the post-interaction arm re-run today at **30 sites**, a spot check |

So the stage half of the claim was carried by a 30-site sample against a collector that had
moved underneath it. **`_collectInteractivePage` really did change**: `c3a0dbcebeb28f74` →
`178c8d208d19a6ea`, **7,352 → 7,489 lines, +151 / −14, 13 hunks**. This is the full-scale
re-measurement.

**Result: nothing was lost, there are no per-site regressions, and a defect #89 found is
confirmed fixed at scale.** The more useful finding is the one about the ruler, in
§"Where this probe cannot fire" — **most of today's collector diff is outside what this
instrument measures**, and that needed saying rather than leaving a zero to imply coverage.

---

## Method

### Source pinning, because another agent was editing `background.js`

#73 records a hash changing mid-run and the resulting number being unreproducible; #89
opens with an attribution paragraph for the same reason. Rather than hash before and after
and hope, the source was **pinned**: `git archive HEAD` into a scratchpad, `temp/`
symlinked back so the sample screening and the output land with the project's other
artefacts.

    snapshot: 7b4827ef7c0338e1070963bae9758cf494dcb83f1ed87edf9650d53e00b861b7
    HEAD    : 7b4827ef7c0338e1070963bae9758cf494dcb83f1ed87edf9650d53e00b861b7

**Stated rather than implied: the working tree did not in fact drift during the run** — the
concurrent agent touched `tools/audit_name_correctness.py` and not `background.js`. The
pinning was precautionary and is reported as such.

### The comparison is controlled — only the collector changed

| component | #89 (`3fb87b1`) | HEAD (`d844947`) | |
|---|---|---|---|
| `tools/inspect_site.py` (lenient PROBE) | `894b45dfa7739978` | `894b45dfa7739978` | SAME |
| `tools/audit_generality_live.py` (strict PROBE2, sample, exclusions) | `de71e843d6686ee8` | `de71e843d6686ee8` | SAME |
| `tools/_extract.py` | `14f078556d0abfea` | `14f078556d0abfea` | SAME |
| `tools/audit_stage_generality.py` (driver) | created by #89's own commit | `437d291c92cafbbf` | untouched since |
| **`_collectInteractivePage`** | `c3a0dbcebeb28f74` | `178c8d208d19a6ea` | **the variable** |

**One honest qualification.** #89's *run* predates its own commit: its `pass0.json` stage
rows carry no `ledger_drops` field, which the committed driver writes. So the exact driver
that produced #89's numbers is not byte-recoverable. The *metric* files are byte-identical,
so the loss figures compare arm to arm; stage **selection** could in principle differ, and
the drift control is the right denominator for reading any stage-count difference.

One concrete gain from running the committed driver: it persists `ledger_drops`, so "0
reasons outside `SPEC_DELETES`" is **falsifiable here**. In #89's main run it was not, and
that entry had to measure the histogram on a separate 28-site subset to make the claim.

### Everything else is inherited

Sample, metric, visibility rule, declaration-only stage picker, and the no-spoofing rule
are #89's and #85's, unchanged — forking them would let two definitions drift
(PRINCIPLES 17; #36 recorded exactly that producing a false "a rule started deleting
again" on six sites). The pool is the same 265 sites.

---

## Proving the metric can fire, before believing its zeros

### 1. `--selftest` — PASS, `failures: []`

The picker reaches `menu-popup`, a **nested** `menu-popup` (compounding), `details`, `tab`,
`select` by both mechanisms and `text-input`; and a control revealed **only** by an
interaction, whose name is then removed, is reported lost by **both** arms
(`strict_fired_on: ["Menu Item Alpha"]`).

### 2. The out-of-sample guard, with a planted violation

| input | result |
|---|---|
| a frozen-corpus host (`news.ycombinator.com`) | **refused** |
| a genuine out-of-sample host | clean |
| the real 265-site pool, against 160 excluded hosts | clean |

### 3. `--lossy` — mutilating a **real** listing at the deepest stage reached

A fixture is what you thought of. This drives the stages on a live site, then deletes half
the real listing's rows and the matching entries.

| site | stage | entries | deleted | clean (lenient / strict) | **mutilated (lenient / strict)** |
|---|---|---|---|---|---|
| leg_perldoc | 4 | 36 | 18 | 0 / 0 | **13 / 16** |
| ko_daum | 4 | 1,669 | 835 | 0 / 0 | **36 / 170** |
| wc_webawesome | 4 | 714 | 357 | 0 / 0 | **53 / 136** |
| gov_au | 1 | 130 | 65 | 0 / 0 | **1 / 11** |
| he_ynet | 0 | 3,223 | 1,612 | 0 / 0 | **14 / 190** |

`LOSSY: PASS` — every manufactured loss raised the strict arm.

**And it re-prices the lenient arm's weakness on today's code.** On `gov_au`, deleting
**65 of 130 entries** moves lenient by **1** and strict by **11**, because a container's
concatenated label still quotes the names of the children whose rows were deleted. #89
measured 1 against 27 on the same site. **The lenient number alone is close to worthless as
a guarantee; the strict number carries the result**, and both are reported throughout for
that reason.

---

## Results

265 candidates, **258 usable**, **596 reads** — 258 at first paint and **338 after an
interaction**.

### The headline

| | |
|---|---|
| visible controls examined | **72,687** |
| entries collected | **152,855** |
| **identities lost, lenient** (core / deep / declared) | **0 / 0 / 0** |
| **controls owning no row, STRICT** (of 72,687) | **0** |
| drop reasons outside `SPEC_DELETES` | **none** |
| ledger drops actually recorded | **1,161,807**, every one of 596 reads > 0 |
| controls that existed only *because* of an interaction | **2,094** |
| …of those, lost | **0** |
| `probe_attrs_clean` | true on **596 / 596** |

### By stage

| stage | reads | visible controls | declared | entries | LOST core/deep/decl | strict: cands / **no-row named** | NEW named | NEW lost | modal banner | readiness fired |
|---|---|---|---|---|---|---|---|---|---|---|
| s0 first paint | 258 | 34,528 | 1,690 | 70,540 | 0/0/0 | 34,528 / **0** | — | **0** | 29 | 195 |
| s1 | 158 | 17,669 | 1,347 | 37,168 | 0/0/0 | 17,669 / **0** | 1,303 | **0** | 19 | 136 |
| s2 | 84 | 9,225 | 1,043 | 21,004 | 0/0/0 | 9,225 / **0** | 387 | **0** | 12 | 81 |
| s3 | 55 | 6,283 | 187 | 13,466 | 0/0/0 | 6,283 / **0** | 221 | **0** | 8 | 52 |
| s4 | 41 | 4,982 | 130 | 10,677 | 0/0/0 | 4,982 / **0** | 183 | **0** | 6 | 40 |
| **total** | **596** | **72,687** | **4,397** | **152,855** | **0/0/0** | **72,687 / 0** | **2,094** | **0** | 74 | 504 |

Depth: 258 sites measured, **158 opened at least one declared thing**, 84 reached a second
interaction on top of the first, 55 a third, 41 the fourth (the cap). 100 sites offered
nothing the picker could act on declaratively.

The **2,094** figure is what stops this being a null measurement: that many named controls
existed at a later stage and not at first paint, and the collector carried every one.

### By interaction kind — 0 lost in all nine

| kind | reads | visible controls | entries | LOST | strict no-row | NEW named | NEW lost |
|---|---|---|---|---|---|---|---|
| text-input | 89 | 9,732 | 18,077 | 0 | **0** | 124 | **0** |
| expandable-controls | 69 | 7,323 | 15,140 | 0 | **0** | 477 | **0** |
| menu-popup | 57 | 6,606 | 15,186 | 0 | **0** | 777 | **0** |
| expandable | 57 | 6,134 | 13,408 | 0 | **0** | 402 | **0** |
| tab | 23 | 2,859 | 9,502 | 0 | **0** | 126 | **0** |
| select | 18 | 1,847 | 4,045 | 0 | **0** | 8 | **0** |
| dialog-trigger | 16 | 2,597 | 4,807 | 0 | **0** | 96 | **0** |
| details | 7 | 891 | 1,731 | 0 | **0** | 81 | **0** |
| combobox | 2 | 170 | 419 | 0 | **0** | 3 | **0** |

Attempt → flip: `expandable` 118→57, `text-input` 114→89, `menu-popup` 104→57,
`expandable-controls` 103→69, `tab` 35→23, `dialog-trigger` 28→16, `select` 23→18,
`combobox` **13→2**, `details` 7→7. Mechanisms (flipped only): click 230, click+keyboard
89, keyboard-typeahead 17, `select_option(programmatic)` 1.

**`combobox` at 2 flips is not a measurement of anything**, and is stated rather than
rounded away — same weakness #89 recorded at 3.

### By script family — 0 lost in all fourteen

| script | reads | visible controls | entries | LOST | strict no-row | NEW named |
|---|---|---|---|---|---|---|
| latin-english | 345 | 40,926 | 73,404 | 0 | **0** | 1,521 |
| latin-other | 100 | 7,949 | 20,919 | 0 | **0** | 285 |
| kana+han (ja) | 35 | 5,152 | 10,387 | 0 | **0** | 47 |
| han-trad | 25 | 3,350 | 6,355 | 0 | **0** | 124 |
| han-simp | 15 | 1,845 | 3,822 | 0 | **0** | 0 |
| hangul (ko) | 13 | 2,205 | 9,263 | 0 | **0** | 47 |
| cyrillic | 11 | 1,153 | 2,194 | 0 | **0** | 15 |
| hebrew (RTL) | 11 | 1,599 | 7,076 | 0 | **0** | 31 |
| thai | 10 | 2,108 | 4,652 | 0 | **0** | 11 |
| arabic (RTL) | 8 | 807 | 2,014 | 0 | **0** | 3 |
| greek | 7 | 1,542 | 3,533 | 0 | **0** | 2 |
| vietnamese | 6 | 1,930 | 4,077 | 0 | **0** | 0 |
| devanagari | 5 | 1,219 | 3,238 | 0 | **0** | 0 |
| bengali | 5 | 902 | 1,921 | 0 | **0** | 8 |

### Shadow DOM — the at-risk population was genuinely exercised

An ablation measures the code against the sample and cannot measure the sample
(PRINCIPLES 9), so it is worth checking the shape the changed code acts on is present:

| | first paint | post-interaction |
|---|---|---|
| shadow roots walked | 2,141 | **6,599** |
| same-origin frames walked | 530 | 708 |

The ~3× rise independently corroborates the `display:contents` hunk's own claim that
design systems render slotted controls when you open something. **124 of 258 usable sites
carry shadow roots at first paint**; the heaviest are web-component sites by name
(`wc_webawesome` 5,280, `wc_salesforce` 1,840, `w2_nationwide` 246, `gov_au` 230,
`wc_lit` 152).

### Reads that could not have found anything

Six of 596 reads had fewer than five visible controls, so they contribute nothing to the
guarantee and are named rather than left inside the total: `uni_vnu` s1 (0),
`w2_oesterreich` s1 (0), `w2_israel_rail` s0 (1), `cv_windy` s0 (3), `w2_extjs_ks` s0 (3),
`w2_worldcat` s0 (3).

---

## Regression check against #89, site by site

252 sites overlap. **The question is not "are both runs zero" — it is whether any
individual site lost nothing then and loses something now.**

**REGRESSIONS: NONE**, on any of the four arms.

Volume is comparable, so the zero is not a zero because less was examined:

| | #89 | HEAD |
|---|---|---|
| strict candidates over the overlap | 73,016 | 71,982 (−1.4%) |
| reads over the overlap | 577 | 582 |
| entries over the overlap | 160,999 | 148,990 (−7.5%) |

**The −7.5% on entries is one site and it is not ours.** `w2_athens` is −10,272 of the
−12,009, and its *control* count fell with it (1,013 → 625) at an unchanged stage count —
the page served less, rather than the collector emitting less. The control count is
measured by the probe from the DOM independently of the collector, which is what settles
it. Excluding that site: −1,737 over 251 sites (−1.2%), matching the control delta.

**Stage counts differ on 9 of the 252 sites (3.6%) — which is exactly the drift floor.**
The control below measures 2 of 65 sites (3.1%) changing stage count between two passes of
*identical* code taken back to back, so the stage-selection differences between this run
and #89 are at noise level and carry no signal. Three of the nine are the banner deltas
discussed above.

Sample churn, not code: 3 sites usable in #89 and not now (`w2_madrid`, `w2_sorbonne`,
`w2_upenn_cat`), 6 usable now and not then (`w2_cour_cass`, `w2_extjs_ks`, `w2_gov_pl`,
`w2_jakarta`, `w2_osu_courses`, `w2_seoul_metro` — every one of them on #89's own
unmeasured list). That is why 255 became 258.

### D1 is confirmed fixed, at scale, on the site that motivated it

#89 proposed `d.tagName !== 'DIALOG'` before `dialogOpen`'s dominates-viewport fallback,
because `<wa-popover>` opens a native `<dialog>` with `show()` sized to the full viewport.
It has since been applied. **Prediction, made before looking: banners should fall,
concentrated on `wc_webawesome`.**

| stage | #89 banner | HEAD banner | #89 chars | HEAD chars | delta |
|---|---|---|---|---|---|
| s0 | False | False | 11,358 | 11,446 | +88 |
| s1 | False | False | 11,626 | 11,750 | +124 |
| s2 | False | False | 11,560 | 11,818 | +258 |
| **s3** | **True** | **False** | 10,092 | 12,288 | **+2,196** |
| **s4** | **True** | **False** | 10,063 | 12,090 | **+2,027** |

Stage count, entries and losses are identical across the two runs; the only thing that
moved is the spurious banner and the page it was suppressing. #89's own figure for the
affected read (10,092 chars) reproduces exactly as the starting point, and the three
unaffected stages moved only +88…+258.

The other two banner deltas are **stage-count** changes, not verdict changes: `bank_rbc`
2→1 banners with 2→1 stages, `w2_raiffeisen_at` 1→5 with 1→5 stages. Total banners 69→70
over the overlap.

---

## Drift floor

67 sites (every 4th of the pool, chosen by position), run twice back to back with the code
held constant.

| | #89 | this run |
|---|---|---|
| sites compared | 65 | **65** |
| stage COUNT identical | 65 / 65 | **63 / 65** |
| interaction KIND SEQUENCE identical | 64 / 65 | **63 / 65** |
| entries at s0, absolute difference | median 0, mean 3.45 | median **0**, mean 1.89 |
| listing chars at s0, relative | median 0.0%, p90 0.72% | median **0.0%**, p90 **3.06%** |
| **losses in either pass** | 0 | **0** |
| **strict losses in either pass** | 0 | **0** |

**This run's floor is wider than #89's** — 63/65 rather than 65/65 on stage count, and a
p90 on listing characters 4× larger. That is live-web noise on a different day, and it is
reported rather than smoothed: a stage-count difference of one or two sites, or ~3% of
listing characters, is **not** signal here.

It does not touch the result. The floor for the identity numbers is **exactly 0 in both
passes**, so the measured 0 sits outside any noise by construction rather than by margin.

---

## Where this probe CANNOT fire — demonstrated, not disclaimed

#89 disclaims "whether the right name is on the right element" in one line. That
disclaimer is load-bearing **today** in a way it was not in #89, because **5 of the 13
collector hunks since then are in the name path**. So it was worth converting from a
sentence into a control pair.

Three buttons, one fixture, HEAD's collector, three mutations of the same measurement:

| mutation | lenient core | declared | **strict** |
|---|---|---|---|
| intact | `[]` | 0 | **0** |
| **strip the NAME, keep the row and its ref** | `[]` | 0 | **0 — reports nothing** |
| strip the ROW and the entry | `['Delete account']` | 0 | **1** |

The mechanism is explicit in `inspect_site.PROBE`:

```js
const m = el.getAttribute('mmid');
const byRef = m && BLOB.indexOf('"' + m + '"') >= 0;
if (byRef) continue;            // skipped BEFORE the name test ever runs
```

A control that owns a row is skipped before its name is examined, and the strict arm is
`mmid`-based by construction. **So a control rendered `(unlabeled)` is invisible to every
arm of this probe.**

Confirmed on the actual change rather than only on a fixture: a `<button>` whose label
sits in a `display:contents` span is **absent from the #89-era listing and present at
HEAD** — the slot fix working — and **all three arms read 0 in both.**

### Coverage: how much of the diff under test can this instrument see?

| # | hunk | seen? |
|---|---|---|
| 1 | `display:contents` / slots contribute a name | **no** — name path |
| 2 | AccName separator by box generation | **no** — name path |
| 3 | `alt` before `title` | **no** — name path |
| 4–5 | `recordAtoms` gated on `_namable` | **no** — flow descriptors, not the listing |
| 6 | `target="_top"` inside cross-origin frames | **no** — the probe cannot enter a cross-origin frame |
| **7** | **D1: `<dialog>` before the viewport fallback** | **yes — confirmed above** |
| 8–9 | bare-text identity through `JSON.stringify` | partially — changes listing text, not row ownership |
| 10–11 | D2: the aria-hidden note | prose only; folded into `wc_webawesome`'s char delta |

**Most of today's collector diff sits outside what this instrument measures.** What this
run establishes is (a) the diff caused no collateral **presence** damage anywhere across
258 sites and four compounding interactions, and (b) D1 is fixed at scale.

What it does **not** establish is that the name-path changes are correct. That is a
different axis with its own rulers, and a concurrent agent was running one of them today:
`tools/audit_name_correctness.py` (ours against Chrome's own AX tree) and
`tools/measure_findability.py` (reachable by the identity the listing printed).

---

## Sample bias, stated plainly

**7 of 265 candidates never rendered** and are UNMEASURED, not passed: `w2_moscow`
(DNS), `w2_cdmx`, `w2_kaist`, `w2_sorbonne`, `w2_nlc_cn` (45 s navigation timeouts),
`w2_madrid` and `w2_upenn_cat` (served 0 controls). No user-agent spoofing and no
bot-check evasion.

**That is the small loss; the large one is inherited.** This pool is the 265 sites that
rendered for #85, screened from 445 candidates — so roughly 180 candidates a headless
browser could not reach are missing before this probe starts (112 behind a consent wall or
bot block, 20 timeouts, 9 network errors, 4 DNS). **The sample is survivorship-biased
toward simpler pages.**

**Depth is not uniform.** 100 of 258 sites offered nothing the picker could act on, so the
post-interaction evidence rests on 158 sites and the deepest tier on **41**. Read `s4`'s
4,982 controls as a measurement over 41 sites, not over the sample.

**Within a site, one path.** The driver follows a single interaction chain and does not
explore.

**Not reached at all:** hover-only menus (a CSS `:hover` submenu declares no state on its
trigger, so there is no flip to verify and PRINCIPLES 1 forbids picking it by class or
position); closed shadow roots and same-origin frames are *measured* but not *picked from*
(Playwright cannot address them by CSS selector); cross-origin frames; anything behind a
login or paywall. The strict arm covers the **core tag population only** — for the 4,397
declared-role candidates just the lenient test applies.

**Two questions this cannot answer, each with its own tool:** whether the right name is on
the right element (#74 — `measure_findability.py`, `audit_name_correctness.py`), and
whether a model then picks the right row (#75, which found the benchmark substrate cannot
carry the question).

---

## What this establishes

**Establishes.** The collector does not lose identities on a page that has been interacted
with, on today's code — through four compounding interactions, nine kinds of declared
interaction, 258 live out-of-sample sites in 14 script families, 338 post-interaction
reads, 72,687 controls. Zero by two independent definitions, with the probe proven able to
report a loss on a fixture *and* on live markup, a drift floor of exactly 0 for the
identity numbers, and **no per-site regression against #89 across 252 overlapping sites**.
D1 is additionally confirmed fixed at scale on the live site that motivated it.

**Does not establish.** That the right name is on the right element — and that is where
most of today's diff landed. Nothing about hover-only menus, logged-in states, cross-origin
frames, or the ~180 candidates a headless browser cannot reach. The deepest tier rests on
41 sites.

**The single thing I am least sure of.** Not the zero — that is well evidenced for
presence. It is that **"the day's work did not break stage generality" is a much narrower
claim than it sounds**, because the instrument is blind to exactly the axis today's
collector diff moved. A reader who takes this paper as "the 49 commits are safe" would be
over-reading it by the width of the coverage table above.

**Next, if this line is continued:** the cheapest unmeasured thing is still a *second*
path through a site rather than a deeper one — 100 of 258 sites offered the driver nothing.
The most valuable is a post-interaction run of the **name** rulers, since both of them
currently measure first paint and today's changes are measured to fire 2.8× more after an
interaction than before it.

---

## Artefacts

| | |
|---|---|
| main run | `temp/stage_generality/main_b/pass0.json` |
| drift control | `temp/stage_generality/drift_b/{pass0,pass1,drift}.json` |
| live firing proof | `temp/stage_generality/lossy_b/lossy.json` |
| #89 baseline | `temp/stage_generality/main/pass0.json` |

#89's published numbers were re-verified from its artefact (255 usable, 580 reads, 73,274
controls, 161,442 entries, 0/0/0, 2,106 new named, 0 new lost) rather than taken from its
prose. **#103, #104 and #105 left no artefact under `temp/`**, so #104's 30-site spot check
cannot be re-derived — MEASUREMENT.md §5's point that a result nobody can re-derive is an
anecdote with a p-value.
