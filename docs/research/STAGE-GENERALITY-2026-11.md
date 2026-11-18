# Stage generality: identity loss AFTER the page has been interacted with

**Probe:** `tools/audit_stage_generality.py`
**Collector under test:** `_collectInteractivePage` @ `c3a0dbcebeb28f74…`
(`extension/background.js` @ `0b363b622657d407…`, repo `3fb87b1`)
**Date:** 2026-11-18

> **Attribution, because another agent was editing `background.js` during this session**
> (#73 records a hash changing mid-run and the resulting number being unreproducible). The
> main run, the drift control, the lossy check, the D1 A/B and the typed-value run all used
> `background.js` @ `0b363b62` (repo `3fb87b1`). Commit `4523d30` then landed at 15:00:15,
> and the **ledger-volume** run alone used it. That commit touches `_readinessPage` and
> `readinessNote` only: `_collectInteractivePage` hashes **`c3a0dbcebeb28f74`
> byte-identical across both commits**, and the diff contains zero changes to `_drop`,
> `_dropMmids`, `_noteEntries`, `isInteractive`, `keepForFind` or `dialogOpen`. So the
> drop-reason figures are valid for the same collector as everything else; no readiness
> figure is quoted from that run.

---

## The question, and why it was open

#85 measured `lost_identities = 0` across 260 live out-of-sample sites. That number
describes **one static read at first paint**, plus at most **one** disclosure opened. The
project's own claim is "works on any site **at any stage**", and the post-interaction half of
it had never been measured.

A page after four interactions is a different page. A menu is open; a submenu is open inside
the first; a tab panel has swapped its contents; a combobox has rendered a listbox, often in a
portal at the document root rather than inside the trigger; a field holds typed text; an
overlay may have marked everything behind it `aria-hidden`. Each of those changes what the
collector sees, and several of them are the shapes this project has previously got wrong:
#25's Radix modal detection, #29's decoy listbox, #51's faded consent overlay, #80's
off-canvas drawer taking every slot in the entry cap.

So: **does `lost_identities` stay at zero when the page is no longer the page that loaded?**

**It does.** 255 live out-of-sample sites, **580 reads** of which **325 are after an
interaction**, **73,274 visible controls**, **161,442 entries**: **zero identities lost by
either definition, at every stage, in every script family**, and no drop reason outside the
permitted set. **2,106 named controls existed only because of an interaction and the collector
carried all of them.**

The two defects this found are both in the layer that *describes* the page — a MODAL banner
raised by a non-modal popover, and a note that asserts the dialog as the cause of drops that
predate it. Neither loses an element. That is the same migration #43 recorded: once the
collector settled, the defects moved to the prose around it.

## What this measures, and what it does not

**Measures.** A rendered, genuinely-visible, not-declared-hidden control whose identity the
listing does not carry, at every stage of a bounded interaction sequence. Two definitions,
because #85 found the first too weak on its own:

| | |
|---|---|
| **lenient** | the control's name appears *somewhere* in the listing or the structured array |
| **strict** | the control **owns a row**, matched by `mmid` / `ref_N` |

The lenient test is satisfiable by a container's concatenated label (AccName 2F rolls
descendants' text up), so a control can "pass" because its parent quotes it. The strict test
cannot be satisfied by a neighbour's text.

**Does not measure**, and each of these is a different question with its own tool:

* whether the right name is on the right element (#74's class — a control present under
  another element's identity). `tools/measure_findability.py` asks that, on frozen sites.
* whether a model then *picks* the right row (#75; that work found the benchmark substrate
  cannot carry the question).
* anything behind a login, a paywall, or a consent wall we declined to click through.
* cross-origin iframes: measured by neither arm, because neither this probe nor the collector
  can read into one.

## Method

### The metric is reused, not rewritten

Everything that decides whether an element was lost comes from `audit_generality_live` (#85),
which itself reuses `inspect_site.PROBE` verbatim: `_measure_js` (the **real** collector,
extracted from `background.js` by `_extract.py`), `_summ`, `usable`, the excluded-host set and
`SCRIPT_OF`. Forking the metric would let two definitions drift, which PRINCIPLES 17 forbids
and #36 recorded happening to the permitted-drop-reason set. What is new here is the
interaction **driver**.

### Visibility

`checkVisibility({opacityProperty: true, visibilityProperty: true})`, everywhere, including
inside the picker. A bare call checks layout only; #36 measured a probe using it reporting
**3.81%** identity loss where the same probe with the options passed reports **0.00%**, every
"found" element being one the collector had correctly dropped. Getting this wrong invalidates
the whole run, so it is stated rather than assumed.

### Stages are chosen from declarations only

Tiers, in order. No class name, no label wordlist, no pixel size (PRINCIPLES 1 and 4):

| tier | selector | the flip that counts |
|---|---|---|
| `menu-popup` | `[aria-expanded="false"][aria-haspopup]` | `aria-expanded` → `true` |
| `dialog-trigger` | `[aria-haspopup=dialog]`, or `[aria-controls]` pointing at a dialog | a visible dialog appears |
| `expandable-controls` | `[aria-expanded="false"][aria-controls]` | `aria-expanded` → `true` |
| `combobox` | `[role=combobox][aria-expanded="false"]` | `aria-expanded` → `true` |
| `details` | `details:not([open]) > summary` | `details.open` → `true` |
| `tab` | `[role=tab][aria-selected="false"]` | `aria-selected` → `true` |
| `expandable` | `[aria-expanded="false"]` | `aria-expanded` → `true` |
| `select` | a `<select>` with ≥ 2 options | `selectedIndex` changes |
| `text-input` | a writable, empty text field | `value` holds what was typed |

A stage counts **only if the page's own declared state actually flipped** — #85's rule, kept.
A click that changes nothing is an attempt, not a stage.

`combobox` requires the `aria-expanded` attribute to be present, so the flip is verifiable;
an `input[list]` is deliberately excluded, because its datalist popup is browser UI with no DOM
existence and therefore nothing a DOM representation can be measured on either way.

**Compounding.** Within a tier, a candidate *inside* something already opened is preferred, so
stage 2 opens a submenu inside stage 1's menu rather than wandering to an unrelated control.
That is how "a second disclosure on top of the first" is reached without naming one. A kind is
used at most twice per site, so a site that is all menus still reaches a `select` or a field.

**Nothing that navigates is picked**, decided from the declaration (`href`, `type=submit`,
`type=image`, `target`) and never from the label. A stage that navigates anyway — a `<div>`
with a JS handler — ends that site's chain and is reported.

### Two things about the driver that were measured, not assumed

**The probe writes nothing to the DOM.** The first version marked the click target with
`data-ab-stage-target` and removed it after clicking. Setting then removing an attribute **is a
DOM mutation**, and the readiness probe duly reported it: `since ≈ 18 ms` before *every*
post-interaction measurement, on *every* site, with the mutation window at 3000 ms so no amount
of waiting removes it. That is #70's "our own instrumentation showed up as page activity",
rebuilt by someone who had just read #70. The target is now an element **handle**; used-ness
lives in a `window.__abStage*` expando; `probe_attrs_clean` asserts the absence on every
measurement. After the fix the same sites report `since ≈ 1120 ms` — exactly the settle delay,
i.e. the click itself — and the attributes recorded are the page's own (`data-bs-popper`,
`aria-expanded`, `class` on a Bootstrap dropdown).

**The `<select>` keyboard path is platform-dependent, and the fallback is labelled.** Measured
on this machine (macOS Chromium): `ArrowDown` on a focused closed `<select>` changes
**nothing** (`selectedIndex` 0 → 0, no `change` event), because the platform convention is that
it opens the native popup — which is browser UI with no DOM existence. Typeahead works
(0 → 1, a real `change` event) but only for a key Playwright can name: `'B'` works, and the
first character of an option labelled 東京 / Москва / دبي raises `Unknown key`. A third of this
sample is non-Latin, so shipping the keyboard path alone would have reported "select never
flips" for every non-Latin site — **a harness limit presented as a finding**. The driver tries
typeahead, then `ArrowDown` (the Linux/Windows convention, so the probe is portable), then
`select_option`, and **records which mechanism fired** so a programmatic selection can never be
read as a keystroke.

### Sample

The 265 sites that rendered in #85's final run. Inheriting that screening is a sample choice:
it spends no time on candidates #85 already recorded as blocked or empty, and it **inherits
#85's survivorship bias wholesale**. Hosts are checked against the frozen corpus
(`capture_listings.py` `SITES`), `tools/bench_turns/` and `tools/bench_flows/`; the run refuses
to start if any appears. **No user-agent spoofing and no bot-check evasion**: a site that
blocks us is UNMEASURED and counted as such, never as a pass.

### Proving the metric can fire

A run of zeros is worth nothing until the metric has been shown to report a loss
(PRINCIPLES 11, 15). Two levels:

* `--selftest`, on a fixture: the picker reaches every declared kind, picks the submenu
  *inside* the menu it opened, never picks the fixture's real link or its real submit, an inert
  click does not count as a stage, both `<select>` mechanisms fire, and — the point — a control
  **revealed only by the interaction** whose name is then removed from the listing and the blob
  is reported lost by **both** arms.
* `--lossy`, on live markup: drive the stages on a real site, then delete a fraction of the
  real listing's rows and the matching entries at the deepest stage reached, and require the
  strict arm to rise. A fixture is what you thought of; this is not.

---

## Results

265 candidates, **255 usable**, 4 interaction stages each at most. **580 reads** — 255 at
first paint and **325 after an interaction**. `background.js` hashed identical before and
after the run, so the numbers attribute to one collector version.

### The headline

| | |
|---|---|
| reads | **580** (255 first-paint + 325 post-interaction) |
| visible controls examined | **73,274** |
| entries collected | **161,442** |
| **identities lost, lenient** (core / deep / declared) | **0 / 0 / 0** |
| **controls owning no row, strict** (of 73,274) | **0** |
| drop reasons outside `SPEC_DELETES` | **none** |
| controls that appeared only *because* of an interaction | **2,106** |
| …of those, lost | **0** |

The 2,106 figure is the one that stops this being a null measurement. Interactions genuinely
changed the pages: a menu opened, a submenu opened inside it, a tab panel swapped, a dialog
appeared. **2,106 named controls existed at a later stage that did not exist at first paint,
and the collector carried every one of them.**

### By stage

| stage | reads | visible controls | declared | entries | LOST core/deep/decl | strict: candidates / **no-row named** | NEW named | NEW lost | modal banner | readiness fired |
|---|---|---|---|---|---|---|---|---|---|---|
| s0 first paint | 255 | 34,984 | 1,001 | 73,583 | 0/0/0 | 34,984 / **0** | — | **0** | 29 | 188 |
| s1 | 153 | 17,583 | 643 | 39,614 | 0/0/0 | 17,583 / **0** | 1,272 | **0** | 18 | 132 |
| s2 | 80 | 9,300 | 367 | 23,706 | 0/0/0 | 9,300 / **0** | 387 | **0** | 10 | 76 |
| s3 | 53 | 6,527 | 213 | 13,997 | 0/0/0 | 6,527 / **0** | 263 | **0** | 7 | 50 |
| s4 | 39 | 4,880 | 152 | 10,542 | 0/0/0 | 4,880 / **0** | 184 | **0** | 6 | 38 |
| **total** | **580** | **73,274** | **2,376** | **161,442** | **0/0/0** | **73,274 / 0** | **2,106** | **0** | 70 | 484 |

Depth reached: 153 sites opened at least one declared thing, **80 reached a second
interaction on top of the first**, 53 a third, 39 the fourth (the cap). 102 sites offered
nothing the picker could act on declaratively.

### By interaction kind

| kind | reads | visible controls | entries | LOST | strict no-row | NEW named | NEW lost |
|---|---|---|---|---|---|---|---|
| menu-popup | 54 | 6,425 | 14,923 | 0 | **0** | 765 | **0** |
| expandable-controls | 65 | 7,393 | 18,419 | 0 | **0** | 480 | **0** |
| expandable | 59 | 6,297 | 14,058 | 0 | **0** | 449 | **0** |
| text-input | 86 | 9,632 | 21,230 | 0 | **0** | 126 | **0** |
| tab | 19 | 2,729 | 7,618 | 0 | **0** | 101 | **0** |
| dialog-trigger | 15 | 2,532 | 4,648 | 0 | **0** | 92 | **0** |
| details | 7 | 890 | 1,723 | 0 | **0** | 82 | **0** |
| select | 17 | 1,805 | 3,987 | 0 | **0** | 7 | **0** |
| combobox | 3 | 587 | 1,253 | 0 | **0** | 4 | **0** |

Attempt → flip, which is the honest denominator: `expandable` 121→59, `text-input` 113→86,
`menu-popup` 104→54, `expandable-controls` 100→65, `tab` 33→19, `dialog-trigger` 29→15,
`select` 22→17, `combobox` **14→3**, `details` 7→7. A click that changed no declared state
was not counted, which is why the tried column is roughly double the flipped one.

**`combobox` is the weak row and is stated rather than rounded away:** 3 flips is not a
measurement of anything. A `[role=combobox][aria-expanded=false]` usually needs a click on a
separate toggle button or an arrow key, so clicking the combobox itself flips nothing.

Mechanisms: `click` 276, `click+keyboard` 89, **`keyboard-typeahead` 16**,
`select_option(programmatic)` 3. The `<select>` keystroke path carried 16 of the 19 select
flips on live sites; the programmatic fallback was needed 3 times and is labelled as such.

### By script family

| script | reads | visible controls | entries | LOST | strict no-row | NEW named | NEW lost |
|---|---|---|---|---|---|---|---|
| latin-english | 345 | 41,774 | 75,323 | 0 | **0** | 1,521 | **0** |
| latin-other | 84 | 7,402 | 17,392 | 0 | **0** | 295 | **0** |
| kana+han (ja) | 35 | 5,171 | 10,369 | 0 | **0** | 53 | **0** |
| han-trad | 25 | 3,362 | 6,374 | 0 | **0** | 123 | **0** |
| han-simp | 14 | 1,611 | 3,469 | 0 | **0** | 0 | **0** |
| hangul (ko) | 13 | 2,208 | 9,390 | 0 | **0** | 52 | **0** |
| cyrillic | 12 | 1,261 | 2,581 | 0 | **0** | 14 | **0** |
| hebrew (RTL) | 11 | 1,574 | 7,047 | 0 | **0** | 31 | **0** |
| thai | 10 | 2,100 | 4,606 | 0 | **0** | 4 | **0** |
| arabic (RTL) | 8 | 807 | 2,005 | 0 | **0** | 3 | **0** |
| greek | 7 | 1,929 | 13,810 | 0 | **0** | 2 | **0** |
| vietnamese | 6 | 1,912 | 3,942 | 0 | **0** | 0 | **0** |
| devanagari | 5 | 1,261 | 3,213 | 0 | **0** | 0 | **0** |
| bengali | 5 | 902 | 1,921 | 0 | **0** | 8 | **0** |

English is 345 of 580 reads (59%) — higher than the 52% site share, because English sites
offered more declared disclosures to open.

### Reads that could not have found anything

Two of 580 reads had **zero** visible controls for the probe to lose (`uni_vnu` s1,
`w2_oesterreich` s1 — both behind an overlay that hid the page), and three more had between
one and four. Those five reads contribute nothing to the guarantee and are named rather than
left inside the total.

### Drop reasons — and proving that claim is not vacuous either

"No drop reason outside `SPEC_DELETES`" is worth nothing if the ledger returned nothing at
all; that is the detector-that-cannot-fire shape (PRINCIPLES 15), and the first version of the
stage row saved only the *exception* dict, so the data could not tell those two apart. Fixed
(the row now persists `ledger_drops` and the full histogram) and then measured on a 28-site
subset, 61 reads:

| reason | drops | in `SPEC_DELETES`? |
|---|---|---|
| `not-interactive` | 192,665 | yes |
| `not-visible` | 24,197 | yes |
| `cursor-inherited-non-root` | 5,470 | yes |
| `aria-hidden` | 2,946 | yes |
| `iframe-contents-listed-instead` | 69 | yes |
| `inert` | 38 | yes |
| `checkVisibility-false` | 28 | yes |
| **total** | **225,413** | **7 distinct reasons, 0 outside the set** |

The permitted set is **read from `test_ledger.py`'s `SPEC_DELETES`** via
`inspect_site._permitted_deletes`, never restated — #36 recorded a restated copy drifting and
producing a false "a rule started deleting again" on six sites.

### Probe footprint

`probe_attrs_clean` was true on **all 580 reads**: no attribute this probe wrote was present
in any measured DOM.

### What the interactions actually did to the pages

Entries moved on 230 of the 325 post-interaction reads (168 grew, 62 shrank, 95 unchanged).
The extremes are the useful evidence that this is measuring real state change:

| site | what happened | visible controls | entries | lost |
|---|---|---|---|---|
| `w2_iana_proto` | typed into "Search protocol registries" — the filter emptied the page | 6,350 → **49** | 6,863 → 58 | **0** |
| `w2_admin_ch` | opened "Alle Schweizer Bundesbehörden" (a mega-menu), then typed in "Suche" | 43 → 128 → 19 | 220 → 891 → 134 | **0** |
| `leg_perldoc` | opened a version menu, then a second menu inside it | 33 → 127 → 53 | 36 → 130 → 56 | **0** |
| `uni_vnu` | clicked a language switcher; the page rendered **no visible controls** at all | 172 → **0** | 668 → 6 | — |

The IANA row is the clearest: a single keystroke sequence took a 6,350-control page down to
49, and the collector tracked it exactly, losing nothing in either direction. The `uni_vnu`
row is the honest opposite — one of the two reads where the metric had nothing to find.

Shadow roots and same-origin frames walked: 2,129 / 520 at first paint, **6,573 / 673 across
the post-interaction reads**. Opening things produces more shadow roots, which is the
population the strict arm covers.

### Does the representation carry what the interaction PUT there?

Row ownership says the control is still listed; it does not say the listing reports its new
**contents**, which is a different failure (#24's readback class). Re-run over the 92 sites
that reached a `text-input` or `select` stage:

| | |
|---|---|
| `text-input` stages | 86 |
| typed value present in the listing | **85 / 86** |
| typed value present in the structured array | **85 / 86** |
| `select` stages with an option label | 17 |
| newly selected option label present in the listing | **16 / 17** |
| identities lost in this run | **0** |

**Both misses were investigated and neither is a collector defect.**

*`w2_progressive`* — the probe compared the listing against what was **sent**, and the field
is `<input type="tel" name="Enter ZIP Code" maxlength=5>`, so it accepted `ab te` of
`ab test`. Re-checked against what the field actually **holds**, the row reads:

```
ref_705 | input[tel] name="Enter ZIP Code" value="ab te" maxlength=5
```

Exactly right — including the `maxlength=5` that explains the truncation, which is #31's
declared-constraints work doing its job. So the honest figure is **86/86**; the one failure
was in my test, not the listing.

*`w2_nationwide`* — a cookie preference-center dialog was open (modal banner on, two visible
dialogs) and the `type of insurance` select sits outside it. The identity probe did **not**
flag it, which means the page itself declared it hidden behind the dialog's focus trap, so
dropping it is the documented modal behaviour rather than a loss.

### Readiness — measured, but do not read the post-interaction rows as a property of the pages

| stage | strong | minor | bits-only | silent | median `since_ms` |
|---|---|---|---|---|---|
| s0 | 118 | 35 | 35 | 67 | **2,766** |
| s1 | 73 | 56 | 3 | 21 | **1,119** |
| s2 | 43 | 33 | 0 | 4 | **1,118** |
| s3 | 29 | 21 | 0 | 3 | **1,119** |
| s4 | 14 | 24 | 0 | 1 | **1,121** |

**The post-interaction median `since_ms` is 1,119 ms and the settle delay is 1,100 ms**, so
what those rows are mostly reporting is *our own click*. That is honest behaviour from the
probe — an agent that clicks and then reads is in exactly this position — but it means the
post-interaction firing rate is not evidence that the pages were unsettled. Only the **s0**
row can be read that way: 188 of 255 first-paint reads fired roughly two seconds after
`networkidle`, with a median last-change age of 2.77 s.

The interesting split is `strong` vs `minor`: `minor` means attribute-only churn, i.e. the
listing is structurally current. It rises from 14% of s0 reads to 62% at s4, which is what a
settling page looks like.

### Drift floor

67 sites (every 4th of the pool — chosen by position, not by hand), run twice back to back
with the code held constant:

| | |
|---|---|
| sites compared | 65 |
| stage COUNT identical across passes | **65 / 65** |
| interaction KIND SEQUENCE identical | **64 / 65** |
| entries at s0, absolute difference | median **0**, mean 3.45 |
| listing chars at s0, relative difference | median **0.0%**, p90 **0.72%** |
| losses in either pass | **0** |

The interaction chain is reproducible, which is the part that was not obvious: a declaration-
ordered picker on a live page could easily have chosen differently on a second load, and on
64 of 65 sites it did not. So a stage-to-stage difference of more than ~1 site, or more than
~0.7% of listing characters, is signal rather than live-web noise — and the identity result
(0) sits far outside it, because the floor for *that* number is exactly 0 in both passes.

### Proving the metric can fire, on live markup

The fixture selftest is not enough; a fixture is what you thought of. `--lossy` drives the
stages on a real site and then deletes half the real listing's rows and the matching entries
at the deepest stage reached:

| site | stage reached | entries | deleted | clean lenient / strict | **mutilated lenient / strict** |
|---|---|---|---|---|---|
| leg_perldoc | 4 | 36 | 18 | 0 / 0 | **13 / 16** |
| ko_daum | 4 | 828 | 414 | 0 / 0 | **25 / 108** |
| wc_webawesome | 4 | 714 | 357 | 0 / 0 | **50 / 136** |
| gov_au | 1 | 133 | 67 | 0 / 0 | **1 / 27** |
| he_ynet | 0 | 3,248 | 1,624 | 0 / 0 | **76 / 251** |

Every manufactured loss raises both arms, so a zero on the intact page is a measurement
rather than a silence.

**And this prices the lenient arm's weakness exactly, which #85 asserted and never
quantified.** On `gov_au`, deleting **67 of 133 entries** moves the lenient count by **1** and
the strict count by **27** — a 27× difference on live markup, because a container's
concatenated label still quotes the names of the children whose rows were deleted. On
`he_ynet` it is 76 against 251. **The lenient number on its own would be close to worthless as
a guarantee; the strict number is the one carrying the result.** Both are reported throughout
for that reason.

---

## Sample bias, stated plainly

**10 of 265 candidates never rendered** and are UNMEASURED, not passed: `w2_moscow`,
`w2_jakarta`, `w2_cdmx`, `w2_gov_pl`, `w2_cour_cass`, `w2_kaist`, `w2_nlc_cn` (45 s navigation
timeout), `w2_seoul_metro` (`ERR_EMPTY_RESPONSE`), `w2_extjs_ks` and `w2_osu_courses` (served
fewer than 10 controls). No user-agent spoofing and no bot-check evasion was used, so a site
that declines automated traffic is simply absent from the numbers.

**That is the small loss. The large one is inherited.** This sample is the 265 sites that
rendered for #85, which screened them from 445 candidates — so roughly 180 candidates that a
headless browser could not reach are missing before this probe starts. #85 recorded the
composition of that loss: 112 behind a consent wall or bot block (Bank of America, Mizuho,
MUFG, Shinhan, State Farm, Ticketmaster, StubHub, SBB, gov.kr, the FAA/FCC/FMCSA forms), 20
timeouts, 9 network errors, 4 DNS. **The sample is survivorship-biased toward simpler pages**,
and this run inherits that whole.

**Depth is not uniform.** 102 of 255 sites offered nothing the picker could act on
declaratively, so the post-interaction evidence rests on 153 sites, and the deepest tier (s4)
on 39. The per-stage rows thin out accordingly and should be read that way: `s4`'s 4,880
controls is a real measurement over 39 sites, not over the sample.

**Within a site, one path.** The driver follows a single interaction chain; it does not
explore. A site whose interesting state is behind the *second* menu rather than the first is
measured on the first.

**Not reached at all:**

* **Hover-only menus.** A CSS `:hover` submenu declares no state on its trigger, so there is
  no flip to verify and PRINCIPLES 1 forbids picking it by class or position. It is not
  measured. What reduces the loss: the resulting DOM is the same shape as a clicked menu —
  items that were not rendered now are — and that case *is* measured 54 times.
* **Closed shadow roots and same-origin frames are MEASURED but not PICKED FROM.** Playwright
  cannot address them by CSS selector, so an interaction there could not be performed as a
  user would. Both are in every candidate set (1,272 shadow roots and 141 frames walked across
  the post-interaction reads).
* **Cross-origin frames**: invisible to both the collector and this probe.
* **Anything behind a login or a paywall.**
* **The strict (owns-a-row) arm covers the CORE tag population only** — 73,274 controls. For
  the 2,376 declared-role-only candidates just the lenient test applies, inherited from #85.
  A declared-role control is admitted by `isInteractive` by construction, so the gap is
  narrow, but it is a gap.

**Two questions this cannot answer, each with its own tool:** whether the right name is on the
right element (#74's class — `tools/measure_findability.py`), and whether a model then picks
the right row (#75, which found the benchmark substrate cannot carry the question).

### One bound that was checked and does not bind

`PROBE2`, inherited from #85, stops after examining 12,000 matched elements shared across the
deep and declared arms. If that bound bit on a real page the declared arm would be silently
truncated and a zero there would mean nothing. Measured on the six largest pages in the
sample:

| site | core matched | declared matched | total | budget |
|---|---|---|---|---|
| w2_iana_proto | 6,351 | 0 | **6,351** | 12,000 |
| vi_vnexpress | 1,445 | 43 | 1,488 | 12,000 |
| he_ynet | 812 | 191 | 1,003 | 12,000 |
| vi_tuoitre | 940 | 50 | 990 | 12,000 |
| el_in | 731 | 8 | 739 | 12,000 |
| w2_omnifaces | 496 | 0 | 496 | 12,000 |

The worst page reaches 53% of the budget, so it never truncated anything in this run.

**One environment difference that matters for the readiness numbers only.** Here the tab is
VISIBLE. The extension's tab is hidden BY DESIGN (#12) and Chrome throttles a hidden page's
timers, so a page that finishes painting in 1.8 s here took 4.5 s in a real agent's tab (#70
measured exactly that). The readiness figures below are therefore an optimistic floor for how
busy a real agent's tab looks. The identity numbers do not depend on timing.

---

## Defects found

**Neither is an identity loss.** Both are in the layer that *talks about* the page rather than
the one that collects it — which is where #43 recorded the defects migrating once the
collector settled, and both are the same shape: a note or a banner asserting something the
code has not checked.

### D1 — a MODAL banner on a non-modal `<dialog>`, because the size fallback overrules a declaration

`background.js` ~10594, inside `dialogOpen`:

```js
      // :modal (native showModal) is browser-enforced inertness — trustworthy.
      try { if (d.matches(':modal')) return true; } catch (e) {}
      // "Dominates viewport" fallback …
      if ((rr.width * rr.height) / (_dw * _dh) >= 0.5 &&
          rr.left <= _dw / 2 && rr.right >= _dw / 2 &&
          rr.top <= _dh / 2 && rr.bottom >= _dh / 2 &&
          /^(fixed|absolute|sticky)$/.test(dcs.position)) return true;
```

**Measured on `wc_webawesome`.** `<wa-popover>` renders a native `<dialog>` inside its shadow
root, opens it with **`show()`** rather than `showModal()`, and sizes it to the **full
viewport** as a top-layer positioning container for a small popover panel:

```
{"open": true, "modal": false, "w": 1280, "h": 1600, "host": "wa-popover"}
```

All three fallback conditions pass, so an ordinary popover raised
*** A MODAL/DIALOG IS CURRENTLY OPEN *** and told the agent to *"ignore rows outside that
subtree"* — on a page whose `aria-hidden` count does not move when it opens (the D2 table
above). The page behind is fully interactive.

**The declaration is already in hand and is being overruled.** `d.matches(':modal')` is
checked **four lines above** and returned **false** — that is the browser stating this dialog
was opened with `show()` and that it is **not** making the rest of the page inert. The size
fallback exists for an element that declares *nothing* (a `<div role="dialog">`), where
geometry is the only signal left. Applying it to a `<dialog>`, which has just answered the
question, replaces a declaration with a measurement — the direction PRINCIPLES 1 forbids.

**Proposed diff:**

```diff
+      // A NATIVE <dialog> HAS ALREADY ANSWERED THIS. `:modal` is checked above and returned
+      // false, which is the browser stating this dialog was opened with show() rather than
+      // showModal() and is NOT making the rest of the page inert. The fallback below exists
+      // for an element that declares NOTHING -- a <div role="dialog"> -- where geometry is
+      // the only signal left; applying it to a <dialog> overrules a declaration with a
+      // measurement. Measured on wc_webawesome: <wa-popover> opens a native <dialog> with
+      // show() sized to the FULL viewport (1280x1600) as a positioning container for a small
+      // popover, and the banner told the agent to ignore the rest of a fully interactive page.
+      // A show() dialog that IS modal in practice is still caught below, by the
+      // aria-hidden-siblings and [inert] branches -- which is what the controls pin.
-      if ((rr.width * rr.height) / (_dw * _dh) >= 0.5 &&
+      if (d.tagName !== 'DIALOG' && (rr.width * rr.height) / (_dw * _dh) >= 0.5 &&
           rr.left <= _dw / 2 && rr.right >= _dw / 2 &&
           rr.top <= _dh / 2 && rr.bottom >= _dh / 2 &&
           /^(fixed|absolute|sticky)$/.test(dcs.position)) return true;
```

**Priced, both arms from the same page load at every stage (#19), across the 45 sites that
raised the banner anywhere in the main run — 91 reads:**

| | |
|---|---|
| verdicts CHANGED | **2 of 91** |
| …which reads | `wc_webawesome` s3 and s4, both the `<wa-popover>` shape |
| banners KEPT | **68** |
| rows restored on the affected read | 82 → **92** (chars 10,092 → 11,868) |

The 68 kept banners are raised by other signals entirely (`aria-modal`, aria-hidden siblings,
`[inert]`) and have no visible native `<dialog>` at all, so the patch cannot reach them. This
is a targeted change, not a weakening.

**Controls, and the first version of one of them was wrong.** Five shapes, both arms, same
page load:

| shape | base | patched | wanted |
|---|---|---|---|
| A `showModal()` native modal | banner | **banner** | keep |
| B `show()` full-viewport popover container (the live shape) | banner | **none** | **remove** |
| C `<div role=dialog>` full-viewport overlay, declares nothing else | banner | **banner** | keep |
| D `show()` + siblings marked `aria-hidden` | banner | **banner** | keep |
| E `show()` + siblings marked `inert` (NHK's shape, #25) | banner | **banner** | keep |

C is the control that this is not "stop trusting geometry"; D and E are the controls that a
`show()` dialog which really is modal still raises the banner, through the focus-trap signals
that run after the fallback.

**D's first version reported a FALSE failure, and the fixture was at fault.** It opened the
dialog with an inline `<script>d.show()</script>`, which is a non-hidden **sibling** of the
dialog — and the aria-hidden-siblings branch requires `hiddenSibs === sibs`, *all* siblings
hidden. One `<script>` tag broke the condition and made a working patch look like a
regression. Opening the dialog from outside the document fixes it. That is #29's
vacuous-fixture lesson pointed the other way: a fixture can manufacture a failure as easily as
it can hide one, and the only way to tell is to find out *why* it failed.

### D2 — the aria-hidden note asserts the dialog as the cause, and promises a recovery that does not work

`background.js` ~13087:

```js
} else if (_ah >= 3 && dialogOpen) {
  L.push(`  - NOTE: ${_ah} interactive element(s) are NOT listed because an`
       + ` ancestor is aria-hidden="true"…`
       + ` A dialog IS open (see the banner above), and marking the rest of the page`
       + ` hidden is how focus-trap libraries do that — dismiss it and re-read to see`
       + ` the page again. This is page STATE, not the page's contents.`);
}
```

**Measured on `wc_webawesome` (Web Awesome's own documentation site), driving its stages and
counting controls with an `aria-hidden`/`inert` ancestor across the composed tree at each
one:**

| | banner | controls | with a hidden ancestor |
|---|---|---|---|
| before stage 1 | false | 526 | **50** |
| before stage 2 | false | 526 | **50** |
| before stage 3 | false | 526 | **50** |
| before stage 4 | **true** | 526 | **50** |
| before stage 5 | **true** | 526 | **50** |
| after the popover closed | false | 526 | **49** |

**The suppression does not move when the dialog opens.** The hidden elements are decorative
`<wa-icon>`s that are `aria-hidden` permanently, exactly as icons always are. The note told
the agent that a focus trap had hidden them and that *"dismissing it and re-reading"* brings
the page back; on this page dismissing it brings back one element.

The collector cannot know the answer — it has no history of the page, so whether these were
hidden before the dialog opened is not derivable from a single read. That is precisely what
the comment **twelve lines above this branch** says to do about it: *"state the FACT, list
causes as causes, and never assert a recovery the tool has not verified."* And the **sibling**
branch, for the non-dialog case, already does it right: it lists three causes, says *"WHY it
did is not knowable from here"*, and adds `An open role=${_pop} IS listed below, which is
consistent with (a)` as **evidence for** a cause rather than as the cause.

So this is PRINCIPLE 6 / #33's class, in the note that was rewritten to enforce it, and it is
the third instance of that shape in this file. `C15` cannot catch it: the sentence is
declarative, not hedged.

**Proposed diff** — delete the special branch and let the general one handle it, which also
collapses two spellings of one concept into one (PRINCIPLE 17):

```diff
-    } else if (_ah >= 3 && dialogOpen) {
-      L.push(`  - NOTE: ${_ah} interactive element(s) are NOT listed because an`
-           + ` ancestor is aria-hidden="true"${_ahN ? ` (${_ahN} of them carry their own label or text)` : ''}.`
-           + ` A dialog IS open (see the banner above), and marking the rest of the page`
-           + ` hidden is how focus-trap libraries do that — dismiss it and re-read to see`
-           + ` the page again. This is page STATE, not the page's contents.`);
-    } else if (_ah >= 3 && _ahN >= 3) {
+    } else if (_ah >= 3 && (_ahN >= 3 || dialogOpen)) {
```

…and in the surviving branch's evidence line, let an open dialog count as evidence the same
way an open menu already does:

```diff
-           + (_pop ? ` An open role=${_pop} IS listed below, which is consistent with (a).` : '')
+           + (dialogOpen ? ` A dialog IS open (see the banner above), which is consistent with (a)`
+                        + ` — though whether it is WHY these elements are hidden is not knowable`
+                        + ` from one read, since they may have been hidden before it opened.`
+              : (_pop ? ` An open role=${_pop} IS listed below, which is consistent with (a).` : ''))
```

**NOTE on the shared cause of D1 and D2.** They compound on exactly one page in this sample
and the compounding is the point: the banner says *work inside the dialog, ignore the rest*,
and the note immediately under it says *the rest is hidden because of that dialog, dismiss it
to get the page back*. Both are wrong on `wc_webawesome`, in the same direction, and together
they describe a modal page that does not exist. Fixing D1 alone removes the banner and
therefore the D2 branch on that page — but D2 is reachable by any other modal signal, so both
diffs are worth applying.

**What would make D2 fixture-testable:** a page with ≥ 3 permanently `aria-hidden` controls
and a dialog that opens without hiding anything. The assertion is that the emitted note does
not contain the imperative *"dismiss it and re-read to see the page again"* while still naming
the dialog. It fails against the current code on exactly that string.

### Investigated and NOT a defect

Recorded so they are not re-opened.

**68 reads had a visible `[role=dialog]`/`<dialog>` and no MODAL banner.** That is
`dialogOpen` working as specified: it asks whether a dialog is *modal*, not whether one
exists. A small non-modal popover, a chat launcher or a cookie bar with `role=dialog`
correctly gets no banner. The probe's `dialogs_visible` field counts any visible dialog and is
therefore a broader question than the banner's — it is reported for context, not as a
disagreement.

**Two of 580 reads had the probe's own light-DOM dialog counter read 0 while the banner
fired.** Both are `wc_webawesome`, and both are the D1 shape: the dialog is inside a shadow
root, which `_measure_js`'s counter (plain `document.querySelectorAll`) could not see while
the picker's counter (which walks shadow roots) could. That was an inconsistency *in this
probe* — two counters answering one question differently, the defect class this project keeps
finding in other code — and it touches no identity number. **Fixed after the run**: the
counter now walks shadow roots too, so this run's `dialogs_visible` column is the light-DOM
figure and a re-run will report the shadow-piercing one.

**The entry count falling after an interaction is usually correct.** Net entries across the
325 post-interaction reads is **−6,425**, which looks alarming and is dominated by two
legitimate causes: a filter emptying a page (`w2_iana_proto`, −6,805 entries for a search box
that filtered 6,350 controls down to 49) and a modal correctly suppressing the page behind it.
`lost_deep` and `strict_norow_named` are 0 on every one of those reads, which is the check
that separates "the page has fewer controls now" from "we stopped listing them".

---

## Mistakes made while measuring this

Recorded because the method is the part that transfers.

1. **The probe's own marker was page activity.** The click target was tagged
   `data-ab-stage-target` and the tag removed after clicking — a set/remove pair that is a DOM
   mutation, which the readiness probe reported as `since ≈ 18 ms` before *every*
   post-interaction read on *every* site. #70's lesson rebuilt by someone who had read #70.
   Element handles now; `probe_attrs_clean` asserts it; after the fix the same sites report
   `since ≈ 1120 ms` (the settle delay, i.e. the click) with the page's own Bootstrap
   attributes in the histogram.

2. **A control reported a false failure and the fixture was at fault.** D1's case D opened its
   dialog with an inline `<script>`, which is a non-hidden sibling, and the aria-hidden-siblings
   branch requires *all* siblings hidden. The patch looked like a regression because of one
   tag. #29's vacuous-fixture lesson pointed the other way: a fixture can manufacture a failure
   as easily as hide one, and the only way to tell is to find out *why* it failed.

3. **"Zero unexpected drop reasons" was unfalsifiable from the saved data.** The stage row kept
   only the exception dict, so a ledger that returned nothing would have produced the same
   output as a ledger that returned 225,413 correctly-labelled drops. Fixed, then measured.

4. **The `<select>` keyboard path was platform-dependent and would have been reported as a
   page property.** `ArrowDown` on macOS changes nothing; typeahead works only for keys
   Playwright can name, which excludes every non-Latin option label. Left alone, this would
   have reported "select never flips" for a third of the sample as if it were a finding about
   the sites.

5. **A damning result was checked before it was believed.** `wc_webawesome` raising a MODAL
   banner with zero visible dialogs looked like a collector defect; the first explanation
   (my light-DOM-only counter) was *also* true, and the real finding was underneath both. The
   aria-hidden before/after measurement is what separated them.

---

## What this does and does not establish

**Establishes.** The collector does not lose identities on a page that has been interacted
with — through four compounding interactions, across nine kinds of declared interaction, on
255 live sites in 14 script families, with the result 0 by two independent definitions, a
probe proven able to report a loss on both a fixture and live markup, and a drift floor
(identical stage count on 65/65 sites) far below the effect.

**Does not establish.** That the right name is on the right element; that a model picks the
right row; anything about hover-only menus, logged-in states, cross-origin frames, or the ~180
candidates a headless browser cannot reach. The deepest tier rests on 39 sites.

**Next, if this line is continued:** the cheapest unmeasured thing is the *second* path through
a site rather than a deeper one — the driver follows one chain, and 102 of 255 sites offered it
nothing. The most valuable is #74's question, which no amount of this probe can answer: every
number here says the control is *present*, and none says it is present under its own name.
