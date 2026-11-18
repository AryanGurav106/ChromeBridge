# Findability AT STAGE: can `find` reach a control by the identity the listing printed, after the page has been interacted with?

**Probe:** `tools/measure_findability_at_stage.py`
**Reuses:** `tools/audit_stage_generality.py` (#89, the interaction driver) and
`tools/measure_findability.py` (#74, the metric)
**Collector under test:** `_collectInteractivePage` @ `18548bf50abc20bd`
(`extension/background.js` @ `c1a6992712284b30`, repo `07b80d3`)
**Date:** 2026-11-18

> **Headline.** 254 live out-of-sample sites, 581 reads of which **327 are after an
> interaction**, **13,797 probes**: a control the listing prints is reachable by the
> identity it printed **13,682 of 13,682 times (1.0000)**, with **zero** needing
> descendant or ancestor credit and **zero** needing `find`'s weak tier. **A control
> revealed BY an interaction is no harder to reach than one that was always there.** The
> whole residue is in the rows the listing deliberately blanks, and it is dominated by
> `find`'s own result caps.

---

## The question, and why it was open

Every ruler in this project measures **presence**: presence, `lost_identities`, Mind2Web
recall, `measure_sufficiency`'s DS. CLAUDE.md #74 is the case that shows presence is not
enough — 118 ptable.com element tiles were present in all of them and **unreachable by
their own verbatim printed label**, on a page the readiness probe itself called settled.
The listing was correct throughout; the tool that reads it was not, and no offline
measurement in this repo could have caught it.

`measure_findability.py` closed that gap on the **frozen corpus at first paint**
(0.9797 strict / 0.9996 with descendant credit, 84 sites, 2,661 unique identities).
#89 then measured identity **loss** after up to four compounding interactions on 255 live
out-of-sample sites and found zero — and closed by naming this as the most valuable
unmeasured thing:

> every number here says the control is *present*, and none says it is present under its
> own name.

A page after four interactions is a different page: a menu is open, a submenu is open
inside it, a tab panel has swapped, a combobox has rendered a listbox in a portal at the
document root, a field holds typed text, and an overlay may have marked everything behind
it `aria-hidden`. #89 measured **2,106 controls that existed only because of an
interaction** and lost none of them. **Present is not reachable.**

So: **does reachability-by-name survive an interaction, and is a control revealed BY an
interaction harder to reach than one that was always there?**

---

## What this measures, and what it does not

**Measures.** For a control the listing prints, hand `find` the identity the listing
printed for that row and ask whether that same element comes back. It is deliberately the
weakest possible question — not "can `find` infer the goal", which #20 measured at 0% and
which is semantic inference rather than retrieval. A miss here is unambiguous.

**Does not measure**, each with its own tool:

* whether the name is **right**. This scores `find` against the **collector**, so a name
  both of them get wrong scores as a hit. It sees an unreachable name, never a wrong one.
* whether a model then **picks** the row (#75 — that work found the benchmark substrate
  cannot carry the question).
* anything behind a login, a paywall, a consent wall, or a cross-origin frame
  (inherited from #89).
* hover-only menus: a CSS `:hover` submenu declares no state on its trigger, so there is
  no flip to verify and PRINCIPLES 1 forbids picking it by class or position.

---

## Method

### Both halves are reused, not rewritten

The **driver** is `audit_stage_generality`'s, verbatim: `STAGE_PICK` / `_act` /
`STAGE_VERIFY`, the declaration-only tier list, the flip rule, the excluded-host set and
the sample pool. The **metric** is `measure_findability`'s, verbatim: `identity_of`, the
`_FB` fake bridge, the real `find` bound out of `mcp_server.py`, and `_relation_returned`.
Forking either would let two definitions drift, which PRINCIPLES 17 forbids and #36
recorded happening to the permitted-drop-reason set.

One thing was **added** to `measure_findability.py` rather than copied beside it:
`_relation_returned` answers the descendant and the ancestor question in one evaluate,
and `_descendant_returned` is now a thin wrapper over it so the frozen-corpus number keeps
its definition exactly.

### Two arms, both from the same page load and the same stage

| arm | search space | why |
|---|---|---|
| **full** | the entries `find` REALLY receives — the shipped tool calls `get_interactive_elements(structured=True, detail="full")`, so images are in its search space | the headline |
| **compact** | the entries `measure_findability.py` feeds it | keeps the frozen-corpus number comparable, and prices that ruler's fidelity rather than leaving it a matter of taste |

The **probe** is always the COMPACT entry: its mmid identifies the element and its identity
is the one the listing printed. Only the search space changes between arms, which is
exactly the production situation — the listing a reader sees is compact, and the array
`find` scores over is full. Both arms are measured on the same page at the same stage, so
run-order drift cannot align with an arm (PRINCIPLES 10 / `MEASUREMENT.md` R3).

### Three populations, which is how the sharp question gets answered

| population | definition |
|---|---|
| `s0` | probed at first paint |
| `new` | probed at stage ≥ 1, identity string **never seen at an earlier stage** — the control exists *because of* the interaction |
| `carried` | probed at stage ≥ 1, identity already seen — the control that was always there, now on a page that has been interacted with |

`carried` is the control arm. If `new` and `carried` fall together, the cause is the page
after interaction; if only `new` falls, it is the revealed control itself.

**NEW is keyed on the identity STRING, not the mmid.** mmids are additive, so one
re-render mints hundreds of fresh ones for elements that did not change (#9), and #89's
`new_named_controls` uses the same name-set definition.

### Which rows can honestly be asked the question

A row the listing prints with its identity **blanked** poses no question. When
`subtreeName && !subtreeNameSole` the collector builds `e.line` with name/label/text
emptied plus `(container — the text here belongs to the elements inside it)`, on purpose:
#74's rule, so an app shell does not match every query. Asking `find` for that name asks
for a string the listing never showed anyone.

Those rows are **not excluded quietly**. They are counted, and asked a different and
fairer question: *the blanking rule's own justification is that the text stays findable
through the contributors, which are themselves kept entries* — so the agent-relevant
outcome is whether asking for those words returns this element **or anything inside it**,
which is the descendant reasoning #18 and #73 use on Mind2Web.

### Sampling

Probes are **stride-sampled** across the whole entry list rather than head-sliced, because
the first rows of a live page are its header and the entire point of a staged read is that
the interesting controls appeared further down. New identities are reserved a share of the
budget so a revealed menu is actually probed.

### Sample

The 265 sites that rendered in #89's run (itself #85's screening). Hosts are checked
against the frozen corpus (`capture_listings.py` `SITES`), `tools/bench_turns/` and
`tools/bench_flows/`; the run refuses to start if any appears. **No user-agent spoofing
and no bot-check evasion**: a site that blocks us is UNMEASURED and counted as such, never
as a pass.

### Proving the ruler can fire

A high score is worth nothing until the metric has been shown to report a miss for a
control whose printed name does not match its element (PRINCIPLES 11 and 15).

* `--selftest`, on a fixture driven through one real declared interaction: a control
  revealed by the interaction is reachable by its printed identity; #74's **sole-carrier**
  shape revealed by the interaction is reachable; **the generic plant** — the same control
  with its identity moved off it — scores a miss; **#74's own defect, reproduced** — with
  `subtreeNameSole` stripped from the entry (the pre-#74 state, reached without touching
  the extension) the sole carrier scores `zero-match` with the live symptom verbatim,
  `No elements matched "36 Kr Krypton 83.798"`; and a blanked row is routed to its own
  question and never scored in the printed denominator.
* `--fire`, on live markup: drive the stages on a real site, then at the deepest stage
  reached move K controls' identities off their elements and require every one to stop
  being a hit while the untouched controls keep theirs. A fixture is what you thought of;
  this is not.

---

## Results

265 candidates, **254 usable**, four interaction stages each at most. **581 reads** — 254
at first paint and **327 after an interaction**. `bridge_races = 0` on every read, which is
the probe asserting that no site's query was ever scored against another site's entries.

### The headline

| | |
|---|---|
| reads | **581** (254 first paint + 327 post-interaction) |
| entries collected | 162,457 |
| …of which the listing **blanks** the identity | 16,397 (**10.1%**) |
| **printed-identity probes** | **13,797** |
| …contested (identity shared with another entry, excluded) | 115 |
| **reached by the identity the listing printed** | **13,682 / 13,682 = 1.0000** |
| …of those, needed descendant credit | **0** |
| …of those, needed ancestor credit | **0** |
| …of those, came back only in the weak `NO STRONG MATCH` tier | **0** |
| **misses** | **0** |
| 95% upper bound on the miss rate (rule of three, 0 in 13,682) | **≤ 0.00022** |

**Zero misses, in 14 script families and across 9 kinds of declared interaction.** Every
hit was in the confident tier; `find` never had to fall back to its weak list to return a
probed control.

### By stage

| stage | probes | shared identity | **strict** | unique-only | miss |
|---|---|---|---|---|---|
| s0 first paint | 5,996 | 3,188 (53%) | **1.0000** (5,938/5,938) | **1.0000** (2,808/2,808) | 0 |
| s1 | 3,633 | 1,868 (51%) | **1.0000** (3,610/3,610) | **1.0000** (1,765/1,765) | 0 |
| s2 | 1,960 | 974 (50%) | **1.0000** (1,946/1,946) | **1.0000** (986/986) | 0 |
| s3 | 1,272 | 633 (50%) | **1.0000** (1,262/1,262) | **1.0000** (639/639) | 0 |
| s4 | 936 | 512 (55%) | **1.0000** (926/926) | **1.0000** (424/424) | 0 |

Depth: 101 sites offered nothing the picker could act on declaratively, 71 reached one
interaction, 29 a second on top of the first, 14 a third, **39 the fourth** (the cap).

### The sharp question: is a control revealed BY an interaction harder to reach?

**No, and the control arm says the cause is not "the page after an interaction" either.**

| population | probes | shared | **strict** | unique-only | miss | 95% upper bound |
|---|---|---|---|---|---|---|
| `s0` (first paint) | 5,996 | 53% | **1.0000** (5,938/5,938) | **1.0000** (2,808/2,808) | 0 | ≤ 0.0005 |
| **`new`** (exists only because of the interaction) | 1,957 | 48% | **1.0000** (1,952/1,952) | **1.0000** (1,010/1,010) | 0 | ≤ 0.0015 |
| `carried` (was always there, page now interacted with) | 5,844 | 52% | **1.0000** (5,792/5,792) | **1.0000** (2,804/2,804) | 0 | ≤ 0.0005 |

The three bounds differ only because the samples differ in size. **`new` is the population
#89 measured at 2,106 controls and 0 lost; this says those same controls are not merely
present but reachable by the name the listing gave them.**

**And `new` really is "revealed by the interaction" rather than page churn**, which matters
because the population is defined on the identity STRING. It concentrates in exactly the
kinds that render something that was not there — not in `text-input`, where a new identity
would mostly be the probe's own typed value:

| interaction kind | stages | NEW probes | NEW hits | carried probes |
|---|---|---|---|---|
| menu-popup | 53 | 567 | 567 | 696 |
| expandable-controls | 65 | 461 | 459 | 1,072 |
| expandable | 55 | 386 | 386 | 934 |
| tab | 25 | 179 | 179 | 421 |
| dialog-trigger | 16 | 148 | 148 | 236 |
| details | 7 | 88 | 88 | 80 |
| text-input | 87 | **99** | 96 | 1,978 |
| combobox | 3 | 16 | 16 | 56 |
| select | 16 | 13 | 13 | 371 |

224 of the 327 post-interaction reads produced at least one new identity to probe. (The
small gaps between NEW probes and NEW hits are contested identities, excluded from the
denominator on both sides, not misses.)

### By interaction kind, and by script

Every row is 1.0000 with zero misses. Printed probes per kind: `text-input` 2,077,
`expandable-controls` 1,533, `expandable` 1,320, `menu-popup` 1,263, `tab` 600,
`select` 384, `dialog-trigger` 384, `details` 168, `combobox` 72.

Script families, printed probes: latin-english 8,122 · latin-other 2,110 · kana+han 840 ·
han-trad 600 · cyrillic 336 · han-simp 336 · hangul 306 · hebrew (RTL) 255 · thai 232 ·
greek 168 · arabic (RTL) 130 · bengali 120 · devanagari 120 · vietnamese 122. **All
1.0000.**

### The residue is entirely in the rows the listing BLANKS

| | |
|---|---|
| blanked rows probed | **2,371** |
| text reached (the row itself, or something inside it) | **2,114 = 0.8916** |
| not reached | **257** |
| …`blanked-text-outranked` — `find` returned other elements, ours not among them | **240** |
| …`blanked-text-no-match` — `find` returned nothing at all | **17** |

**`blanked-text-outranked` (240) is dominated by `find`'s own result caps, not by
unreachability.** 136 of the 240 came back with exactly **5** refs — the size of the
capped weak list under `NO CONFIDENT MATCH` — and 30 came back with 20, the confident cap.
The query in this arm is a container's *concatenated* name, which is a paragraph rather
than a label; handing `find` a paragraph and getting a weak list is the behaviour #20
documents, not a defect. 113 of the 240 had the query bounded at 100 characters, so the
probe did not even ask the whole string.

**`blanked-text-no-match` (17) splits 14 / 3, and both halves are intended behaviour.**
All 17 records are listed here rather than characterised, because 17 is small enough to
read:

* **14 are strips of short repeated tokens** — pagers (`1 2 3`, `1 2 3 4`, `1 2 3 4 5`,
  `1 2 3 4 5 6`, `3 / 13`), a font-size switcher (`A A A`), transit line codes (`GL C`),
  a passenger counter (`인원 총 1 명`), a repeated site word (`本站 本站 站群`), on
  `w2_ubb`, `w2_titech`, `w2_jr_west`, `w2_beijing`, `w2_pkp`, `w2_mbta`, `tix_korail`
  and `w2_shanghai`. For the Latin-digit ones `find` drops a lone letter or digit on
  purpose (`F41d`: *"it identifies nothing and would match most of a page"*). For the CJK
  ones that rule does not apply (`F41` deliberately keeps a single logograph), so the
  cause there is the other one: the container is blanked, so it cannot match itself, and
  no kept descendant carries those exact words.
* **3 are whole-page shells** — `<body>` on `w2_sparkasse` and `w2_worldcat`, and a
  cookie-banner-plus-nav blob on `w2_tinkoff`. `find` declining those is the blanking rule
  working, the same verdict `OPEN.md` item 0 reaches for carbon's half-page `div`.

**Three sites concentrate the blanked residue**: `w2_cityline` and `w2_barclays` at 15 of
30, `w2_ndl_jp` at 12 of 25.

### What this does NOT let you do: fold the two arms into one number

Folding the blanked rows back into the strict denominator the way the frozen-corpus ruler
does gives **13,683/16,053 = 0.8524**, or 0.9840 with descendant credit. **Neither figure
should be quoted**, for two reasons:

1. the mix is set by this probe's sampling caps (24 printed rows per stage against 6
   blanked), not by the population, so the ratio measures the caps; and
2. a blanked row is one `find` is *deliberately prevented* from matching, so its strict
   score can only ever be ~0 — **`b_hit` is 1 of 2,371.** A strict number with those rows
   in the denominator is mostly measuring how many of them a page has.

That is the argument for asking the two questions separately.

**And the obvious follow-on explanation was measured and is NOT supported.** It would be
tidy to say the frozen-corpus number is high because that corpus has fewer blanked rows —
the two live pages dumped for timing have them at 27–30% of identity-bearing entries. Run
over 23 frozen sites (`scratchpad/frozen_blanked_share.py`), the frozen corpus has **675
of 8,923 entries blanked = 7.6%**, against **10.1% live**. Same order. So the two
corpora are comparable on this axis and the "frozen corpus under-represents the shape"
story does not hold; reason 1 above — the sampling mix — is the one that stands.

### Proving the ruler fires, on live markup

`--fire` drives the stages on a real site and then, at the deepest stage reached, moves
8 controls' identities off their elements — blanking them in the array `find` searches
while keeping the query the listing printed:

| site | stages reached | entries | clean hits | hits after the identity moved |
|---|---|---|---|---|
| gov_au | 1 | 133 | 8/8 | **0** |
| leg_perldoc | 4 | 36 | 8/8 | **0** |
| ko_daum | 4 | 1,733 | 8/8 | **0** |
| wc_webawesome | 4 | 714 | 8/8 | **0** |
| w2_unicode | 1 | 132 | 8/8 | **0** |

**5/5 fired.** So a zero on the intact pages is a measurement rather than a silence.

### The two arms are identical — `detail="full"` costs nothing here

Both arms ran on the same page at the same stage in the drift passes, so run-order drift
cannot align with an arm:

| pass | sites | arm | probes | **strict** | miss | blanked reached |
|---|---|---|---|---|---|---|
| 0 | 62 | full | 3,082 | **1.0000** (3,059/3,059) | 0 | 533 / 582 |
| 0 | 62 | compact | 3,082 | **1.0000** (3,059/3,059) | 0 | 530 / 582 |
| 1 | 56 | full | 2,491 | **1.0000** (2,478/2,478) | 0 | 428 / 465 |
| 1 | 56 | compact | 2,491 | **1.0000** (2,478/2,478) | 0 | 426 / 465 |

**Identical on the printed arm in both passes.** The extra media rows that
`detail="full"` puts in `find`'s search space do not cost a control its reachability. On
the blanked arm `full` is marginally *better* (+3, +2), which is inside noise and is the
opposite direction from the artefact described under "Mistakes" below.

This also settles a fidelity question about `measure_findability.py`: it feeds `find` the
**compact** entries while the shipped tool asks for `detail="full"`. On this sample that
substitution changes nothing.

### Drift floor

67 sites (every 4th of the pool, chosen by position), run twice back to back with the code
held constant:

| | |
|---|---|
| sites usable in pass 0 / pass 1 | 62 / 56 |
| sites comparable (usable in both) | **54** |
| pooled strict, pass 0 / pass 1 | **1.0000 / 1.0000** |
| pooled absolute delta | **0.0000** |
| per-site absolute delta, median / p90 | **0.0000 / 0.0000** |
| stage COUNT identical across passes | **46 / 54** |

**The 0.0000 floor is real and almost worthless, and saying only the first half would be
the misleading reading.** #19's rule is that *a saturated metric cannot detect
regression*: both passes sit at 1.0000, so their difference is 0 by construction and this
drift control cannot put a floor on a quantity that never moved.

What it DOES establish is that the things around the metric are stable enough for the
result to mean something: **54 of 67 sites rendered in both passes**, and **46 of 54
reached the same number of stages**. The 8 that did not are live-web variation in the
DRIVER, not in the metric — `tix_songkick` 5 → 1, `ar_aljazeera` 3 → 1, `w2_alrajhi`
1 → 3. A future change that moved findability would have to move it by more than 0 against
a sample that re-renders this consistently.

---

## Sample bias, stated plainly

**11 of 265 candidates are UNMEASURED, not passed.** Eight timed out at 45 s navigation
(`w2_buenosaires`, `w2_cdmx`, `w2_gov_pl`, `w2_ccb`, `w2_garanti`, `w2_osu_courses`,
`w2_kaist`, `w2_nlc_cn`) and three served fewer than five probeable rows at first paint
(`w2_extjs_ks`, `w2_helsinki`, `w2_seoul_metro`). No user-agent spoofing and no bot-check
evasion was used, so a site that declines automated traffic is simply absent.

**That is the small loss; the large one is inherited.** This sample is #89's, which is
#85's screening of 445 candidates — so roughly 180 candidates a headless browser could not
reach are missing before this probe starts, 112 of them behind a consent wall or a bot
block (banks, ticketing, several government portals). **The sample is survivorship-biased
toward simpler pages**, and this run inherits that whole.

**Depth is not uniform.** 101 of 254 sites offered nothing the picker could act on
declaratively, so the post-interaction evidence rests on 153 sites and the deepest tier on
39.

**Within a site, one path.** The driver follows a single interaction chain; a site whose
interesting state is behind the *second* menu is measured on the first.

**257 printed identities were skipped for length** (over 300 characters). Measured on two
dumped pages they are 0.25% and 0.00% of printed candidates, and they are news-teaser
paragraphs rendered as clickable `<div>`s — prose, not a label anyone would type. They are
counted rather than truncated, because a truncated query asks a different question and
could manufacture a false miss.

**Not reached at all**, inherited from #89: hover-only menus (a CSS `:hover` submenu
declares no state flip, and PRINCIPLES 1 forbids picking it by class or position); closed
shadow roots and same-origin frames are MEASURED but not PICKED FROM, because Playwright
cannot address them by CSS selector; cross-origin frames; anything behind a login.

**And the question this still cannot answer** is whether the name is RIGHT. This scores
`find` against the collector, so a name both of them get wrong scores as a hit.

---

## Mistakes made while measuring this

Recorded because the method is the part that transfers.

### 1. The probe's own shared global produced a clean, plausible, WRONG product finding

`find` takes `(query, tabId)` and reads its bridge from `mcp_server.STATE` — a **module
global**. This probe runs several sites concurrently in one process and the scoring loop
yields, so between one site installing its entries and its next `find`, another site's
coroutine installed **its** entries. `find` then scored the query against a different page.

The result was not noise. It read as a coherent finding about the product:

| | full arm | compact arm |
|---|---|---|
| `tab` rows | **0.5806** | 1.0000 |
| `hangul` | 0.8085 | 1.0000 |
| `new` population | 0.9333 | 1.0000 |

…which says *"the extra media rows in `detail="full"` crowd real controls out of `find`'s
bounded result set, so the shipped tool is worse than the frozen-corpus ruler reports"* —
a publishable-sounding claim with a mechanism and a direction. **Re-deriving it on a single
page (PRINCIPLES 8) showed both arms matching, every time**, and every "miss" was
`No elements matched`, which a larger search space cannot cause.

Fixed with a lock around scoring, plus a `bridge_race` counter so the correctness argument
about yield points is checkable rather than asserted (PRINCIPLES 18). It reports **0** on
the run above.

### 2. One pathological entry ate three of the first six sites

ynet's `<body>` carries an assembled name of **29,422 characters**, and `find` takes
**144 seconds** on it — `find` is O(query tokens × entries × fields) with no bound on
either. The first smoke run lost `he_ynet`, `ko_daum` and `wc_webawesome` to a per-site
timeout, i.e. **the three largest pages**, and would have left a sample of easy pages
reporting a flattering number.

The fix is not a bigger timeout: that entry is a row the listing BLANKS, so the probe was
asking for a string the listing never showed anyone. Separating the blanked rows removed
the pathology and made the question honest at the same time.

### 3. My own query bound cut a token it should not have

The blanked arm bounded its query with `q[:100].rsplit(" ", 1)[0]` — applied
**unconditionally**, so a 12-character identity lost its last token: `정상가 16,900원`
("regular price 16,900 won") was asked as `정상가`, which matches nothing. **6 of the first
14 "unreachable" blanked rows were that cut rather than the page.** Bounded only when it is
actually too long now.

### 4. A waiter that could never finish

`until ! pgrep -f "measure_findability_at_stage.py --only leg_perldoc"` matches **its own
command line**, because `pgrep -f` matches full command lines and the pattern is in the
argument. That is #83's self-matching waiter, repeated by someone who had read #83.
Waiting on a PID cannot self-match.

### 5. A phantom flag in the tool this one extends

`measure_findability.py`'s summary line has read *"see `--dump` to classify them"* since it
was written, and **`--dump` did not exist** — PRINCIPLES 15's shape, and #67's
(`--check-only` validating zero files and exiting 0). The flag exists now and writes every
miss record.

### 6. A tidy explanation that the data refused

The first draft of "why is the frozen number not comparable" said the frozen corpus has
far fewer blanked rows, on the strength of two live pages at 27–30%. Measured on 23 frozen
sites it is **7.6% of entries against 10.1% live** — the same order, and the explanation
is wrong. Deleted rather than softened.

---

## What this does and does not establish

**Establishes.** The layer that READS the listing does not lose a control's reachability
when the page is interacted with: through four compounding interactions, nine kinds of
declared interaction, 14 script families, 254 live out-of-sample sites, **0 misses in
13,797 probes** (95% upper bound ≤ 0.00022), with a ruler proven to fire both on a fixture
and on live markup, and both search-space arms agreeing exactly.

**This closes #89's named next step**, and it closes it in the direction #89 could not
reach: every number there says a control is *present*; this says it is present **under its
own name** and that `find` returns it.

**Does NOT establish that `find` is good at finding things.** This is deliberately the
weakest question there is — hand an element its own printed words and ask for it back.
#20 measured the hard question (given a human's GOAL, find the control) at **0%**, and
that is semantic inference rather than retrieval. A 1.0000 here means the blanking and
scoring layer no longer breaks a lookup that ought to be trivial; #74 is the proof that
"ought to be trivial" is not the same as "is".

**Does not establish that the name is RIGHT.** The ruler scores `find` against the
collector, so a name both of them get wrong scores as a hit. That question has no
instrument in this repo.

**Nor anything about** hover-only menus, logged-in states, paywalls, cross-origin frames,
or the ~180 consent- and bot-walled candidates absent before this probe starts.

**Next, if this line is continued.** The two cheapest unmeasured things are the SECOND
path through a site (the driver follows one chain, and 101 of 254 sites offered it
nothing), and whether an agent handed a *blanked* container's row can work out what to
query instead — which is a prose question this probe turns into a descendant lookup
because that is what it can measure.

## Why this reads 1.0000 at first paint where `measure_findability` reads 0.9774/0.9797

**MEASURED, not inferred, and the measurement is what this section is for.** The
first version of this paragraph argued from `OPEN.md` item 0's classification —
53 of its 54 strict misses are the label-plus-badge shape, and that shape IS
`subtreeName && !subtreeNameSole`, the exact condition this probe routes to the
blanked arm. That is a reading of someone else's classification, not a result,
and `--dump` could not settle it: the `desc_hit` branch incremented and moved
on without recording, so the descendant-credited population was invisible.

One line added to that branch, then `measure_findability.py --n 84 --dump`:

| | |
|---|---|
| records dumped | 45 |
| descendant-credited | 43 |
| **…carrying `subtreeName && !subtreeNameSole`** | **43/43 = 1.0000** |
| strict misses | 2 |
| …carrying the same shape | 2/2 |

**45 of 45.** The prediction was ~0.98 and the answer is 1.0000, so the two
figures are ONE system measured with those rows **inside** the strict
denominator (`measure_findability`) and **beside** it (this probe). Examples are
the shape exactly: `span "Search Cmd+K"`, and three `body`/`div` shells carrying
a whole page's concatenated text.

Four differences separate the numbers, in descending order of effect:
1. blanked rows are in that denominator and beside this one;
2. different corpora — 84 frozen sites against 254 live out-of-sample ones;
3. this probe skips a printed identity over 300 characters and counts it (257
   of them) where the frozen ruler asks it;
4. sampling — 40 head-sliced entries per site there, 24 stride-sampled per
   stage here.

**Quote neither number as an improvement on the other.** Folding the arms back
together is refused: the fold's value would be set by this probe's caps rather
than by the page.

**The falsifier, stated because it did not fire:** had the descendant-credited
population NOT been dominated by blanked rows, this reconciliation would be
wrong and the two numbers would differ for a reason nobody has found. It is
1.0000, so it is not that.
