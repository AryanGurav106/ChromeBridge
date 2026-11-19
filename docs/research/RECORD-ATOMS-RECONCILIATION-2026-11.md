# What IS a record? Reconciling the number that was measured with the code that shipped

> **WHERE RA1-RA7 LIVE NOW (added when the diff landed).** The B half shipped,
> so RA1 plus its controls RA2/RA3/RA5/RA6 are in `tools/test_widgets.py` and
> run in CI; ablated against a `git archive HEAD` shadow, RA1 FAILS with
> `HIDDENTOKEN-1` in the atoms and all four controls PASS in both arms.
> **RA4 and RA7 are not anywhere, deliberately.** They are the checks for the
> record-rule swap, which this paper recommends against and which was not
> applied -- a standing red check for a design nobody shipped is the noise #15
> priced and #95 records as actively harmful, because it trains the reader past
> a real one. Their evidence stays in this paper. The standalone harness that
> carried all seven was removed rather than kept beside the suite: the project's
> ablation is a shadow checkout with the suite copied over it, and two spellings
> of one concept is what PRINCIPLES 17 deletes.


Research pass, 2026-11-19, against `ba566b8`. Nothing in `extension/`, `core/`
or `mcp_server.py` was changed; the proposal is a diff in §10 and Appendix A
for the owner to apply.

Probes written: `tools/audit_record_definition.py` (the factorial, `--selftest`),
`tools/audit_record_cost_live.py` (the cost question asked of the product,
`--selftest`), `tools/test_widgets.py` (RA1-RA6) (RA1–RA7, the checks for the
diff — deliberately not named `test_*`, see Appendix A).

Three existing probes were repaired, and each repair is a finding in §9:
`audit_atoms_safety.py` (its firing proof had EXPIRED and it said so on every
run), `audit_flow_resolve.py` (its `reorder` arm could not test a content
witness at all), and `audit_record_witness.py` (its baseline column stopped
being a baseline the day `recordAtoms` shipped; it now says so). A fourth
defect — a two-way unpack that kills every descriptor probe at site 60 of 106
— is fixed in all four (§1c).

Read first: `CLAUDE.md` #72, #83, #99; `docs/OPEN.md` item 2;
`docs/MEASUREMENT.md` §4 and the probe-lifetime rule at the end;
`FLOW-UNBREAKABLE-2026-11.md` (which produced the 43.9%) and
`FLOW-SILENT-BIND-2026-11.md` (which produced the gate).

---

## 0. The one-paragraph answer

**The shipped field and #83's number differ in three ways, only one of them
matters, and the better definition is the one that cannot be built where the
field is.** On 5,062 ordinal-bearing descriptors across 81 sites — the first
flow-descriptor measurement to see past site 59, because a two-way unpack of
`SITES` kills every one of them there (§1c) — the shipped tag list witnesses
**18.6%** and the probe's structural rule **41.0%**, against a 0.1–0.6% drift
floor. #99's 13.1% and 43.9% are corroborated and are now one measurement. The
cap is **inert** (2.1% of members, identical uniqueness with and without), and
hidden text is **22.3% of every recorded witness** while deciding only 0.2% of
them. **Neither definition is dominant**: the shipped one is too narrow (half
of all ordinal-bearing descriptors have no `tr`/`li`/`article` ancestor), and
the measured one **cannot be computed where `recordAtoms` is computed**, because
`recordOf` takes the crowd and the collector builds entries one at a time. A
third candidate was already in the tree — `search_page`'s `_climbTo`, which the
field's own comment wrongly claims to be using — and **the safety arms reversed
my recommendation about it**: it finds a record for 90.6% of descriptors and is
WRONG *more* often than what ships (14.9% against 12.7% under a re-sort, and
the only definition that mis-binds when the recorded row is deleted), because
its tighter record stops discriminating and the ordinal takes over. So: **ship
the hidden-text fix** — two lines, and it removes 16 silent mis-binds while
introducing 4 — **do not swap the record rule**, and **build the record-time
move**, which is the only way to have the definition that is better on every
axis measured here.

---

## 1. What was already true before anything was measured

`CLAUDE.md` #99 records that the number #83 published and the code #83 shipped
use different definitions of a record. Reading the two confirms it, and finds a
third difference nobody had named.

| | shipped — `extension/background.js:10089` | probe — `tools/audit_record_witness.py:111` |
|---|---|---|
| **A. what the record is** | `el.closest('tr,li,dl,article,figure,fieldset')` — a TAG LIST | the child of the tied crowd's lowest common ancestor, recursed until the member stands alone — STRUCTURAL, no vocabulary |
| **B. what text counts** | a bare `TreeWalker` over every text node: no visibility test, no `SCRIPT`/`STYLE`/`TEMPLATE` exclusion | skips `SCRIPT`/`STYLE`/`NOSCRIPT`/`TEMPLATE` and anything failing `checkVisibility({visibilityProperty:true})` |
| **C. the cap** | 40 distinct text atoms, then `img[alt]` to 48 | uncapped |

C is a confound rather than a design anyone argued for: the bigger the record
the more a cap bites, so it is entangled with A and has to be separated or the
A column is wrong. All three are measured independently in §3.

### 1a. "The same set `_climbTo` uses" is not true, and the difference is the fix

`recordAtoms`' own comment says the tag list is *"the same set `_climbTo` uses
for search_page's context (#47) and the observe-to-act signature"*. There are
**four spellings of "what is a record" in `background.js`** and they do not
agree:

| site | rule |
|---|---|
| `recordAtoms` (10091) | `closest('tr,li,dl,article,figure,fieldset')` |
| `_obsSig` (1081, and its `dup:obssig` twin at 11440) | the same selector, but hashing **`innerText`** — which is visibility-aware |
| `_climbTo` / `_RECORD` (14304, 14418) | `{TR, LI, DL, FIGURE, ARTICLE}` — **no `FIELDSET`** — within 4 hops, **else `_isRecord`** |

`_isRecord` is the part that matters: a node with at least one **same-kind
sibling** under its parent, i.e. one of a repeated run — MDR/DEPTA's data
record, the same notion #27's fold signature uses. `_sameKind` compares tag plus
class-set *intersection*, with a depth-3 structural signature when neither side
has classes, and `_CLIMB_STOP` bounds the walk at a landmark. Its cost is
already measured in the file (`+0.08ms` on a 4,000-row record list, `+11.86ms`
on the worst shape found) and it was deliberately left uncapped.

So the project already owns a structural record rule, already argued for,
already cost-measured, used for exactly this question one tool over — and
`recordAtoms` uses only the tag-list half of it. That is PRINCIPLES 17, and it
is why a `<div>`-built row has no record in the flow recorder while the same row
has one in `search_page`. It is measured here as a third candidate.

Divergence B has the same shape: `_obsSig` hashes `innerText`, which excludes a
`display:none` subtree; `recordAtoms` walks raw text nodes, which does not. Two
spellings of "the record's text", differing in exactly the way #37 priced at
−24.9% of one listing.

### 1b. The probe's definition cannot be computed where the field is computed

This is the part of the reconciliation that no amount of coverage data settles,
and it is checkable rather than arguable.

`recordOf(member, members)` takes **the crowd**. `recordAtoms` is built inside
the per-element entry literal at `background.js:10055-10451`, one element at a
time as the walk proceeds — at the moment element X's atoms are computed, the
elements it will tie with have not been visited. A crowd is defined by equality
of `at_level(entry, FULL)`, which is computed in **Python**, in
`core/flows/descriptor.py`, after the whole array has crossed the bridge.

So #83's 43.9% is not merely a different definition. It describes a record the
shipped field **cannot build**, and closing that gap in place would mean
re-spelling `LEVELS[FULL]`'s seven-field grouping in JS — a second spelling of
the descriptor itself, which is the failure this whole entry is about.

Two ways out exist and both are real:

- **A per-element rule.** `_climbTo` is one: it asks only about the node and
  its siblings, so it fits exactly where `closest()` sits today. That is the
  third candidate, and it is what §3 measures.
- **Move the computation to RECORD time.** The server already knows the crowd;
  it could ask the extension for the record text of a named set of mmids,
  grouped, in one op. That costs one bridge round trip (~24ms, #38) **on the
  rare call that records a flow**, and it would make any definition — including
  the LCA one — computable exactly. It would also remove a cost that is
  currently paid by every read: `recordAtoms` is not behind `if (structured)`,
  so **every `read_page` on every page computes it for every element**, for a
  consumer only `record_flow` uses. §7 prices that.

### 1c. And no descriptor probe has ever seen the second half of the corpus

Found by meeting it: this probe died at site 60 of a 106-site run with
`ValueError: too many values to unpack (expected 2)`. **35 of the 106 `SITES`
entries are `(name, url, settle_ms)` rather than `(name, url)`**, the first at
index 59 — and `audit_record_witness.py:493`, `audit_flow_resolve.py:438` and
`audit_href_rung.py:240` all unpack two. Their defaults (30–40 sites) are why
nobody met it; `audit_atoms_safety.py` did meet it, "after 25 sites", and fixed
it locally without the others learning.

The practical consequence is not a crash, it is a **sample**: every
flow-descriptor figure this project has published — #49's 12,030 controls,
#61's href rung, #72's and #83's witness coverage — comes from the first
≤59 sites. `adminlte`, `syncfusion_grid`, `jspreadsheet`, `moodle`,
`premierleague`, `fullcalendar` and `daterangepicker` all sit past that line,
and they are the closest thing the corpus has to the admin tables this feature
actually records against (§11.1). All four probes are fixed here; the figures
taken before are not wrong, they are narrower than they read.

---

## 2. The instrument, and its firing proof

`tools/audit_record_definition.py`. Seven cells, **all computed from one page
load**, so run-order drift cannot align with the arm (#19 / MEASUREMENT R3):

| cell | record | filter | cap | |
|---|---|---|---|---|
| `tag_raw` | tag list | none | 40 | **== SHIPPED** |
| `tag_vis` | tag list | rendered | 40 | isolates B |
| `lca_raw` | LCA | none | 40 | isolates A |
| `lca_vis` | LCA | rendered | 40 | A+B |
| `lca_vis_nc` | LCA | rendered | — | **== the PROBE's definition** (A+B+C) |
| `climb_raw` | `_climbTo` | none | 40 | **== search_page's rule** |
| `climb_vis` | `_climbTo` | rendered | 40 | |

Four things make it a measurement of the DEFINITION rather than of a
reimplementation:

- **The parity assert.** `tag_raw` is a second spelling of `recordAtoms`, and a
  second spelling drifts, so every member's `tag_raw` is compared against the
  collector's own field. It reported **32 mismatches of 5,062 (0.63%)** and
  that is not probe drift — see §4a; every one is a product gap the assert
  found instead.
- **The climb cells are sliced out of `background.js`**, not retyped:
  `_RECORD`, `_CLIMB_STOP`, `_sig`, `_cls`, `_sameKind`, `_isRecord` are
  extracted by source text and injected verbatim, and the probe exits if any of
  them cannot be found.
- **Scoring goes through the real resolver.** `core.flows.descriptor.resolve` is
  called unchanged; only `recordAtoms` is substituted per cell. A cell with no
  atoms falls back to the shipped witness+ordinal path, which is the policy.
- **Mutations are applied to the DOM**, then the page is re-collected, so atoms
  are RE-DERIVED. This is not a style preference — see §9c.

**A defect of my own, found by asking why a number was possible.** The
per-member cell function nulled the WHOLE crowd when any member's node was
gone — so after a record was removed the resolver saw no atoms anywhere, could
not take the content branch at all, and every drop arm was **100% REFUSED by
construction**. Measured on a three-row fixture: `cells()` returned null for
all three while the collector's own `recordAtoms` was intact for the two
survivors. Fixed (the survivors are also the right CROWD for the LCA rule — at
replay the crowd is whatever matches now), and the drop arms re-run against
the fix.

The arms that remove nothing are **provably** unaffected rather than assumed
to be: with no missing member `live` is `all`, every member takes the same
path, and the one index change (`k !== i` becomes `m !== n`) is the same test
when the arrays are identical and mmids are unique. §5 says which run each row
came from.

### The firing proof

`--selftest`, six directions, all of which must fire:

```
fixture div-rows: 3 entries, 1 crowd(s)
  A  div rows: shipped recordAtoms=None  of=3 atoms=None  lca_raw unique=True  -> fires: True
  A2 search_page's _climbTo record on the same rows: ['Acme Ltd', 'INV-1001', 'HIDDENTOKEN-1'] unique=True  -> fires: True
  C  unique before blanking=True after=False  -> fires: True
  fixture li-rows: 3 entries, 1 crowd(s)
  B  shipped field carries ['HIDDENTOKEN-1']; filtered cell carries []  -> fires: True
  B2 the descriptor records it: atoms=['Acme Ltd', 'HIDDENTOKEN-1', 'INV-1001']  -> fires: True
  D  resolver on a correct page=CORRECT on a swapped page=WRONG  -> fires: True

  selector parity with background.js: ok

SELFTEST PASS
```

Row A is divergence A end to end through the product: on `<div>`-built rows the
shipped field is `null`, the descriptor records `of=3` with **no atoms**, and
the step is left pinned by position alone. Row B is divergence B end to end: a
`display:none` token is one of the three witnesses `D.build` records.

**The fixture had to be built by running it, and the first two versions were
vacuous** (PRINCIPLES 11). With the `<button>` a direct child of the row, `near`
picks up the whole row text — `"Acme LtdINV-1001ActionsDelete"` — so every
descriptor is unique at the `near` rung, **no crowd forms, no ordinal is
recorded, and the atoms path is never reached at all**. An actions cell is what
makes `near` identical across rows. That is worth keeping in view for the whole
of §3: the population that needs a record witness is narrower than "rows in a
table", because `near` already carries the record text whenever the control sits
directly in the row.

---

## 3. Coverage

81 of 93 loaded sites produce an ordinal-bearing descriptor at all; **5,062
descriptors**, sampled at most 120 per site so one data grid cannot dominate
(#73's lesson about one widget being 17% of a sample). This is the first
flow-descriptor measurement to see past site 59 (§1c), and 27 sites hit the
per-site cap.

**Drift floor first, or the deltas mean nothing** (MEASUREMENT R3). The same
arm measured twice, 81 sites, same per-site seed so the sampled members are
identical:

| cell | pass 1 | pass 2 | delta |
|---|---|---|---|
| descriptors | 5,062 | 5,062 | 0.0% |
| `tag_raw` | 942 | 948 | **0.6%** |
| `lca_vis` | 2,075 | 2,081 | **0.3%** |
| `climb_raw` | 1,469 | 1,470 | **0.1%** |

Coverage — a witness **unique within the crowd**, the same rule `atoms_map`
applies, since an atom two members share cannot say which was meant:

| cell | witnessed | with the shipped self+anchor witness | rescues an unwitnessed ordinal |
|---|---|---|---|
| shipped self+anchor witness alone | 49.5% | — | — |
| **`tag_raw` == SHIPPED** | **18.6%** | 52.8% | 6.7% |
| `tag_vis` (B only) | 18.5% | 52.8% | 6.6% |
| `lca_raw` (A only) | 41.8% | 59.7% | 20.3% |
| `lca_vis` (A+B) | 41.0% | 59.6% | 20.0% |
| **`lca_vis_nc` == the PROBE's definition** | **41.0%** | 59.6% | 20.0% |
| **`climb_raw` == `search_page`'s rule** | **29.0%** | 55.1% | 11.1% |
| `climb_vis` | 28.0% | 54.9% | 10.7% |

**#99's two numbers are corroborated and are now the same measurement.**
It cites 13.1% shipped against 43.9% probe, taken on different samples with
different tools; measured together on one page load across 5,062 descriptors
they are **18.6% against 41.0%**. The gap is 22.4pp where the floor moves
each cell by 6 members of 5,062 (0.12pp), so it is ~190× it, and it is
divergence A almost entirely — `lca_raw` (A alone) is 41.8% and
`tag_vis` (B alone) is 18.5%.

**Where the gap comes from, and it is not subtle:**

| | no record found at all |
|---|---|
| tag list (shipped) | **49.8%** |
| LCA (probe) | 32.4% |
| climb (`search_page`) | **9.4%** |

Half of all ordinal-bearing descriptors have no `tr`/`li`/`dl`/`article`/
`figure`/`fieldset` ancestor. The climb rule finds a record for **90.6%** of
them — and still yields fewer unique witnesses than the LCA rule, because its
records are tighter and therefore share more text with their siblings (§6).

**Divergence C is inert.** Only **2.2%** of members have more than 40 atoms
uncapped, and among those the unique rate is **87.4% with the cap and 87.4%
without**. The cap is a confound in the arithmetic of #83's comparison and
nothing else; it costs no coverage and is not worth changing.

### 3a. A pure swap would LOSE records, and the number is small

The climb rule is not a superset of the tag list: `_CLIMB_STOP` contains
`FIELDSET` and `TABLE`, and the declared-tag preference is bounded at 4 hops
where `closest()` has none. Per member:

| | n | of which had a unique witness |
|---|---|---|
| both rules find a record | 2,491 | — |
| **TAG only** (a pure swap loses these) | **52** (1.0%) | **17** |
| **CLIMB only** (a pure swap gains these) | **2,074** (41.0%) | **615** |
| neither | 445 | — |

So a pure one-spelling swap is **+615 / −17 witnesses**, and an additive
"tag list first, climb as a fallback" is **+615 / −0** at the cost of a fourth
spelling of the concept. The measured regression surface of the pure swap is
0.34% of descriptors.

### 3b. Finding a record and getting a witness are different problems

Split the 81 sites by how often a member has a TAG record at all — i.e. by
whether the page is built from declared record tags:

| site group | members | shipped | LCA | climb |
|---|---|---|---|---|
| ≥80% of members have a tag record (27 sites) | 2,005 | **20.0%** | **62.2%** | 22.5% |
| <30% do (38 sites) | 2,204 | 0.0% | 28.3% | 18.6% |

(per-site medians)

Two things fall out, and the second is the one that matters for §10.

**The shipped field's problem is not only that it often finds no record.**
Even where a `<tr>`/`<li>` record exists for nearly every member, it yields a
unique witness only 20% of the time — because a nav built from `<li>`s, or a
table whose rows differ only in a number, has record text its siblings share.
Finding the record is necessary and not sufficient.

**The climb rule is ≈ the shipped rule where the markup is declared** (22.5%
against 20.0%) and much better where it is not (18.6% against 0.0%). It is
doing exactly what it says: preferring the declared record, falling back to
the repeated run. **The LCA rule's advantage is concentrated in the group
where a record already exists** (62.2% against 20.0% on the same markup),
which is only possible by choosing a DIFFERENT, larger ancestor than the row
— the same effect §6 measures as "big records are 22pp more likely to be
unique".

The per-site extremes are worth seeing: Hacker News is 100% on all three;
`syncfusion_grid`, a real data grid, is **90.8% shipped**; drawio and desmos
are 0.0% shipped and ~10% LCA.

---

## 4. Divergence B on its own

**22.3% of the text in the shipped field is text no user can see** — 5,641
atoms of 25,258, across 32.1% of the members that have atoms. That is far
larger than it looks from a small sample (0 of 597 on the first four sites),
and it is the eBay shape #37 priced at −24.9% of one listing, arriving in the
one field whose entire job is to identify a row.

**And it almost never decides the binding: 5 members of 2,414 (0.2%) are
unique ONLY via hidden text.** Removing it costs 0.1pp of coverage
(18.6% → 18.5%) — inside the 0.6% drift floor.

Both halves matter and they say different things:

- As a **coverage** question B is nothing, and no coverage argument can
  justify changing it.
- As a **correctness** question it is 22.3% of every recorded witness being a
  string the user cannot verify, which can stop matching when a menu opens or
  a panel collapses — a refusal rather than a mis-bind, so it fails in the
  safe direction, but it fails for a reason the file gives no way to see.

The figure is an **upper bound** (§11.5): the probe's filter is stricter than
the collector's own `_namable`, which keeps `display: contents`.

### 4a. The parity assert found a product gap, not probe drift

`tag_raw` disagreed with the collector's own `recordAtoms` on 32 of 5,062
members. Chased on five sites, with the result re-derived on a second pass:
**38 of 38 mismatches are `role: 'media'` entries, 100%.**

There are **three entry literals** in `_collectInteractivePage` — the main one
at `background.js:10055`, and two media ones at `11197` (a CSS
`background-image`) and `11229` (a rendered `<img>`). The main one computes
`recordAtoms`; the other two do not, while setting `clickable: true`. So a
media entry is a legal flow target, can be a member of a tied crowd, and
**can never carry a content witness** — not because its record has no text
(the probe reads plenty from the same `<li>`), but because two of the three
places that build an entry do not compute the field.

That is PRINCIPLES 14 (a field with one half of its contract) and 17 (one
concept, three literals) in the field this whole entry is about. It is 0.63%
of this corpus and it is a one-line fix in each literal — not included in the
§10 diff, because it is a different defect and deserves its own fixture.

---

## 5. Safety

73 sites, every arm a real DOM mutation followed by a re-collect, scored
through `core.flows.descriptor.resolve` with only `recordAtoms` substituted.
**WRONG is the only disqualifying outcome; REFUSED is a designed one**
(PRINCIPLES 7), so a definition that refuses more and is never wrong can still
be the right one — and one of them is.

Two things about the ruler before the numbers. `resolve()` falls back to the
`alt` href key when the recorded descriptor fails, and that fallback is LEFT
IN deliberately: this measures the POLICY a replay actually runs, not the
atoms branch in isolation. And the arms that remove a record come from a
second run against the fixed probe (§2); the rest come from the first, and are
provably identical under both.

| arm | cell | n | CORRECT | REFUSED | **WRONG** |
|---|---|---|---|---|---|
| **base** (control) | all seven | 4,315 | 99.9% | 0.1% | **0.0%** |
| **resort** | `tag_raw` == SHIPPED | 1,397 | 74.6% | 12.7% | **12.7%** |
| | `tag_vis` (B) | 1,397 | 74.6% | 12.7% | **12.7%** |
| | `lca_raw` | 1,397 | 84.8% | 6.3% | **8.9%** |
| | `lca_vis` | 1,397 | 84.4% | 6.6% | **9.0%** |
| | **`climb_raw`** | 1,397 | 78.0% | 7.1% | **14.9%** |
| **shuffle** | `tag_raw` | 1,417 | 72.6% | 13.2% | 14.2% |
| | `lca_raw` | 1,417 | 84.1% | 6.0% | 9.9% |
| | `climb_raw` | 1,417 | 75.9% | 7.0% | 17.1% |
| **edit-cell** | `tag_raw` | 466 | 62.2% | 37.8% | 0.0% |
| | `lca_raw` | 466 | 69.5% | 30.5% | 0.0% |
| | `climb_raw` | 466 | 68.0% | 32.0% | 0.0% |
| **bump-digits** | `tag_raw` | 1,344 | 66.5% | 31.6% | **1.9%** |
| | **`tag_vis` (B)** | 1,344 | 68.1% | 31.0% | **1.0%** |
| | `lca_raw` / `lca_vis` | 1,344 | 66.5 / 68.2% | 31.6 / 30.9% | 1.9% / **1.0%** |
| **swap-controls** | — read the REFUSED column only — | 2,127 | | 8.5–12.6% | (not scorable) |

The two arms that REMOVE a record, from the second run (§2), where a refusal
is the correct answer on `drop-target` and a resolution is on `drop-other`:

| arm | cell | n | CORRECT | REFUSED | **WRONG** |
|---|---|---|---|---|---|
| base (control) | all seven | 4,531 | 100.0% | 0.0% | **0.0%** |
| **drop-target** — only a refusal is right | `tag_raw` / `tag_vis` | 292 | 0.0% | **100.0%** | **0.0%** |
| | `lca_raw` / `lca_vis` | 292 | 0.0% | **100.0%** | **0.0%** |
| | **`climb_raw` / `climb_vis`** | 292 | 0.0% | 99.3% | **0.7%** |
| **drop-other** — must still resolve | `tag_raw` | 879 | 43.7% | 56.0% | **0.3%** |
| | **`tag_vis` (B)** | 879 | 44.4% | 55.6% | **0.0%** |
| | `lca_raw` | 879 | **62.1%** | 37.9% | **0.0%** |
| | `climb_vis` | 879 | 59.3% | 40.7% | **0.0%** |

**`drop-target` is #99's arm and only ONE definition fails it.** The shipped
rule and the LCA rule refuse 100% of the time, as the gate is meant to make
them; the climb rule binds to something else on 0.7% (1.4% of the descriptors
it witnesses) — two silent mis-binds where the recorded row no longer exists.
Its tighter record shares more text with its siblings, so after the row is
removed a sibling still carries the whole recorded set and the composition
gate lets it through.

On `drop-other` the LCA rule recovers **62.1%** where the shipped rule
recovers 43.7% — a refusal there is not safety, it is the step failing — and
B again removes the only mis-bind (0.3% → 0.0%).

### 5a. The climb rule buys coverage and LOSES safety, and the mechanism is exact

This is the result I did not expect and it is the one that decides §10.
`climb_raw` witnesses 29.0% against the tag list's 18.6% and is **WRONG MORE
OFTEN under a re-sort: 14.9% against 12.7%.**

More coverage cannot make a resolver worse unless it takes witnesses AWAY
somewhere, so the per-member cross-tab was computed rather than argued about
(1,397 targets, resort arm, `h` = this cell had atoms):

| tag_raw → climb_raw | n |
|---|---|
| `Ch → Ch` both witnessed, both correct | 449 |
| `C- → Ch` climb GAINS a witness, still correct | 158 |
| `R- → Ch` climb GAINS a witness, refusal becomes correct | 89 |
| `W- → Ch` climb GAINS a witness, **mis-bind becomes correct** | 26 |
| **`Ch → W-` climb LOSES the witness and the ordinal then mis-binds** | **61** |
| `Ch → C-` climb loses the witness, ordinal happens to be right | 94 |
| `W- → W-` neither has one | 147 |

**61 descriptors that the shipped rule got right via its atoms, the climb rule
gets WRONG via the ordinal.** §3b is why: the climb record is TIGHTER (median
10 elements against the tag list's 20), so on `<li>`-built navs and `<tr>`
rows it finds a record more often and a DISCRIMINATING one less often. Its
coverage gain is concentrated on pages where the ordinal was already fine; its
loss lands where the ordinal is not.

Net on the resort arm: **+30 WRONG.** That is the whole case against §10's
option A, and no coverage number would have shown it.

### 5b. When a cell HAS a witness, it is never wrong under a re-sort

Restricted to the descriptors each cell actually witnesses:

| arm | tag_raw | lca_vis | climb_raw |
|---|---|---|---|
| base | 100.0% C | 100.0% C | 100.0% C |
| resort | 97.4% C / 2.6% R / **0.0% W** | 93.4 / 6.6 / **0.0** | 93.8 / 6.2 / **0.0** |
| shuffle | 97.4 / 2.6 / **0.0** | 94.0 / 6.0 / **0.0** | 93.8 / 6.2 / **0.0** |

**0.0% WRONG for every definition, on both permutation arms.** A content
witness of any of the three kinds is safe under a re-sort; every mis-bind in
the pooled table is the ORDINAL, reached because that cell had no witness.
That is #83's thesis confirmed on a 73-site sample — and it also means the
question is purely *how often can a witness be had*, which is §3, plus *what
is lost when a definition takes one away*, which is §5a.

### 5c. Divergence B removes silent mis-binds

Across every mutated arm, comparing the shipped rule with and without the
rendered-text filter on the same targets — **7,942 member-arm verdicts, 54
disagreements (0.68%)**; of the 3,415 where BOTH cells had a witness, 39
disagree:

| `tag_raw` → `tag_vis` | n | |
|---|---|---|
| **WRONG → REFUSED** | 15 | a silent mis-bind becomes an honest refusal |
| **WRONG → CORRECT** | 1 | |
| REFUSED → CORRECT | 26 | |
| CORRECT → REFUSED | 8 | the cost |
| REFUSED → WRONG | 2 | the cost |
| CORRECT → WRONG | 2 | the cost |

**16 mis-binds removed, 4 introduced; 27 resolutions gained, 10 lost.** On
`bump-digits` — every number in every record +1, which is what a live table
does — the shipped rule's WRONG rate **halves, 1.9% → 1.0%**, and the same
halving appears on the LCA rule (1.9% → 1.0%).

I had expected B to be a correctness argument with no measurable safety
effect, because it changes uniqueness for only 0.2% of members (§4). It is
better than that: an atom nobody can see is not just unverifiable, it
**matches the wrong row** often enough to show up in the WRONG column.

---

## 6. The hazard in the structural definition

The worry is specific: the lowest common ancestor of a crowd that spans the
page is a SECTION, and a section's text distinguishes its members for the
wrong reason. Looked for rather than assumed, by cutting uniqueness on the
record's own size and on whether it swallowed a sibling.

**Record shapes, 5,062 descriptors:**

| rule | elements median / p90 / max | chars median / p90 / max | the tags it lands on |
|---|---|---|---|
| tag (shipped) | 20 / 135 / **12,615** | 79 / 3,329 / 55,338 | li 1187, tr 682, article 577, figure 64, fieldset 17, dl 16 |
| LCA (probe) | 12 / 129 / 13,885 | 62 / 881 / **79,104** | div 1435, li 656, tr 539, a 239, span 88 |
| climb (`search_page`) | **10 / 79 / 6,685** | 47 / 517 / 98,124 | div 1694, li 988, tr 409, a 360, article 348, td 230 |

All three have a long tail; the climb rule's is the shortest at the p90.

**Does a BIG record buy uniqueness?** Cut at each rule's own p90, so the
threshold is the observed distribution rather than a chosen size:

| rule | unique among its SMALL records | unique among its BIGGEST tenth |
|---|---|---|
| `lca_vis` | 58.4% | **80.6%** |
| `climb_vis` | 31.0% | **31.5%** |
| `tag_raw` | 40.3% | **5.1%** |

**This is the hazard, quantified, and it is the LCA rule's.** Its biggest
records are 22pp MORE likely to yield a unique witness than its typical ones —
which is what "unique for the wrong reason" looks like from the outside, since
a bigger text pool is more likely to contain something a sibling lacks. The
climb rule is **flat** (0.5pp, inside the drift floor), so its uniqueness is
not bought with size. The tag list runs the other way for a different reason:
its big records are whole navs and sections wrapped in one `<li>` or
`<article>`, whose text every member shares.

**Where each rule fails, it fails quietly rather than wrongly:**

| | members whose record swallows another crowd member | of those, unique anyway |
|---|---|---|
| `lca_vis` | 508 (10.0%) | 15.6% |
| `climb_vis` | **1,762 (34.8%)** | **4.5%** |

The climb rule lands on an ancestor containing another member of the same
crowd a THIRD of the time — `_isRecord` fires on a wrapper that is itself one
of a repeated run, which is a correct answer to "is this node one of a
series?" and the wrong answer to "is this node THIS member's row". When it
does, it yields a witness 4.5% of the time, i.e. it mostly produces nothing.
That is the whole of why its coverage (29.0%) sits below the LCA rule's
(41.0%) despite finding a record five times as often (90.6% against 67.6%):
**it declines where the LCA rule guesses.**

Neither rule ever produced a record that was `<body>` or `<html>`: 0 of 5,062.

**The `<td>` in the climb rule's tag distribution is not #47's defect
returning**, which was worth checking rather than assuming, since `_isRecord`
is tested at EVERY depth before the walk moves on and a `<td>` with sibling
`<td>`s looks like a repeated run. Measured on a constructed table: a
`<button>` inside the last `<td>` of three rows resolves to the **`<tr>`**,
because `_sameKind` compares a depth-3 signature when neither side has
classes and `TD.(BUTTON.())` is not `TD.()`. Same for #47's own live shape, a
link inside a `<th>`: `<tr>`, atoms `['Module Identifier', 'info_module']` —
the label AND the value, which is the pair that case exists for. The 230 `td`
records in the corpus are rows of genuinely identical cells, where the cell IS
one of a series.

### 6a. The verdicts, cut the same way

The uniqueness cut above says where a witness can be HAD. This says what
happens when it is used, over 12,257 member-arm verdicts on the mutated arms:

| cut | n | CORRECT | REFUSED | WRONG |
|---|---|---|---|---|
| `lca_vis`, small records | 6,928 | 51.6% | 25.5% | **23.0%** |
| `lca_vis`, biggest tenth | 1,013 | 58.2% | 24.2% | **17.6%** |
| `climb_vis`, small records | 7,125 | 50.3% | 24.9% | **24.7%** |
| `climb_vis`, biggest tenth | 331 | 49.2% | **37.5%** | **13.3%** |
| `tag_raw`, small records | 4,583 | 58.2% | 23.0% | 18.8% |
| `tag_raw`, biggest tenth | 46 | 65.2% | 15.2% | 19.6% |

**The LCA rule's big records are not a hazard on this corpus — they are its
best population** (17.6% WRONG against 23.0%). The "unique for the wrong
reason" worry is measurable as a PATTERN and does not show up as mis-binds.
What it does show up as is a REFUSAL cost elsewhere, which §5's `drop-other`
row prices: when a neighbouring record changes, a big record's atom set is no
longer wholly present and the composition gate refuses.

**The climb rule's swallow cases are its hazard, and they ARE one.** On the
1,601 members (33.9%) whose climb record contains another crowd member, the
mutated arms give **21.5% CORRECT / 57.0% REFUSED / 21.5% WRONG** — it mostly
declines, and when it does bind there it is wrong as often as it is right.
That is the same population §5a's `Ch → W-` cell is made of.

---

## 7. Cost

This matters more here than it does in `search_page`, and the reason is
structural: `_climbTo` runs **once per search hit** — a handful. `recordAtoms`
is built inside the entry loop at `background.js:7982`
(`mmidReg.forEach`), is **not** behind `if (structured)`, and therefore runs
**once per stamped element on every `read_page`**, for a field only
`record_flow` consumes.

**I measured it twice and the first measurement was wrong in the damning
direction.** A tight loop over `__mmidReg` reimplementing both rules reported
the climb rule at median +2.3ms, p90 +30.5ms and **max +1,530.9ms** on drawio.
That is a number that would have ended the argument, so it was re-derived
against the product (MEASUREMENT R1): `tools/audit_record_cost_live.py` times
`_collectInteractivePage` ITSELF in three arms — as it ships, with
`recordAtoms` removed, and with the climb record — built by patching the
extracted source (each patch asserting its anchor occurs exactly once) and
**interleaved on one page load with the order rotated per replicate**.

| 20 sites, median of 5 replicates | median | p90 | max |
|---|---|---|---|
| the collector as it ships | 45.8ms | 565.7ms | 898.4ms |
| …with `recordAtoms` removed | 44.5ms | 529.0ms | 869.6ms |
| …with the climb record | 62.9ms | 530.8ms | 987.8ms |
| **what `recordAtoms` costs TODAY** | **+1.3ms** | +35.6ms | +36.7ms |
| **what the climb record would ADD** | **+0.0ms** | +89.4ms | **+432.4ms** |
| **A/A floor** (worst spread within an arm) | **24.3ms** | 166.0ms | 2,041.7ms |

**The median delta is zero and the A/A floor is 24.3ms**, so on a typical page
the climb rule is free — and on three of the twenty it is measurably FASTER
than `closest()` (ionic −23.0ms, java_api −34.9ms, syncfusion_grid −4.8ms),
because it bails at a `_CLIMB_STOP` where a six-tag `closest()` keeps walking.

**The tail is real and it is one site.** drawio: +432.4ms against its own
41.3ms floor, over 2,992 stamped elements — 144µs each, which is `_isRecord`
scanning siblings with a depth-3 signature on a canvas app. 432ms is ~12% of a
model turn (#38) and ~18 bridge hops, paid by every read of that page whether
or not anything is being recorded.

So the isolated-loop figure overstated the worst case by **3.5×** and the
direction of the finding survived. Quote the live numbers.

**And the existing field is not free either**: +1.3ms median, +36.7ms max,
on every read, for a consumer used on the rare call that records a flow.

That "every read" is from the source — the field sits in the single entry
literal inside `mmidReg.forEach` with no `structured` guard — and the timing
agrees without being able to prove it on its own: with `structured=false` (the
string listing an ordinary `read_page` returns) the atoms cost is **+1.4ms on
ionic and +1.7ms on java_api**, same sign both times, against a 20ms floor.
Consistent, inside the noise at that size, and the code is the evidence.

---

## 8. Drift floors, in one place

Three different ones are used here and they are not interchangeable:

| what | floor | how |
|---|---|---|
| coverage (§3) | **0.1–0.6%** | 81 sites loaded twice, same per-site seed so the sampled members are identical |
| collection TIME (§7) | **median 24.3ms, p90 166.0ms** | the worst spread WITHIN one arm across 5 interleaved replicates on one page load |
| `audit_flow_resolve` arms (§9c) | n/a | pure Python on a frozen entry array; deterministic by construction |

The coverage floor is what licenses calling 18.6% vs 41.0% a result: the delta
is ~70× it. The timing floor is what stops §7 from claiming a median cost —
the median delta is below it, so the honest statement is "free on a typical
page", not "+0.0ms".

A saturated floor would be weak evidence (#19), and the coverage floor is not
saturated: it moves by 6 members on `tag_raw` and 6 on `lca_vis` between
passes, which is the live-replay noise 18 of the 106 HARs are named for (#16).

---

## 9. Have these probes ever been shown to fire?

Asked of all four, because a coverage number from a detector nobody has
watched report a miss is worth nothing (PRINCIPLES 5). **All three existing
ones had a problem**, each a different kind, and one of them had it in the
exact form `MEASUREMENT.md` warns about:

| probe | what was wrong | status |
|---|---|---|
| `audit_atoms_safety.py` | its firing proof EXPIRED when the defect it tested for shipped; it printed "measuring nothing" and exited 1 on a healthy tree | re-based, fires, and now also catches a regression |
| `audit_record_witness.py` | no firing proof, and its `exist` baseline column silently became the atoms resolver | banner added; the column is no longer a baseline and says so |
| `audit_flow_resolve.py` | its mutations are entry-level, so a content witness is CORRECT by construction on both permutation arms | `mut_reorder` fixed; 39pp of its score was the harness |
| all four, including mine | a two-way unpack of `SITES`, which kills any run past site 59 | fixed in all four (§1c) |

### 9a. `audit_atoms_safety.py` — its firing proof had EXPIRED, and it said so

Run against this tree it printed:

```
detector fires against the SHIPPED resolver: False
  !! the probe cannot fire -- it is measuring nothing
```

and exited 1 on a codebase where nothing is wrong. The proof asked whether
`D.resolve` — the live resolver — is WRONG on a drop-target case. That was
true while the #99 defect was live and became false the instant the gate
shipped. This is `MEASUREMENT.md`'s probe-lifetime rule, which was written
about `audit_retext_*` two days earlier: **an A/B whose firing proof IS a
defect expires when the defect is fixed.**

Re-based so it cannot expire: the probe now carries `resolve_ungated`, an
explicit transcription of the pre-#99 behaviour, and asks whether its own
verdict function can distinguish a resolver that has the defect from one that
does not. It also gained the stronger assertion the old form could not make —
that the shipped gate has **not regressed**:

```
detector fires against a resolver WITHOUT the gate: True
the SHIPPED resolver is clean on every drop-target case: True
```

Proven in both directions: with `D.resolve` monkeypatched back to the ungated
behaviour, the self-test prints `!! the gate has regressed in
core/flows/descriptor.py` and exits 1.

### 9b. `audit_record_witness.py` — no firing proof, and its baseline is no longer a baseline

It has no `--selftest`. Its `base` arm is a control (a WRONG there voids
everything else) and its mutation arms demonstrably produce WRONG, so the
verdict function works — but that is weaker than a firing proof for the
COVERAGE number, which is what #83's 43.9% is.

The sharper problem is that **its `exist` column stopped being the thing it
measures.** `v_exist` calls `D.resolve`, and since `6382583` the collector
emits `recordAtoms`, so `D.build` puts `atoms` on the target and
`_resolve_recorded` takes the content branch **before** it ever reads the
witness or the ordinal. Verified in pure Python rather than inferred:

| | after a re-sort |
|---|---|
| target built from entries WITH `recordAtoms` | resolves to `11` — the recorded element |
| the same entries with the field absent | resolves to `13` — the wrong one |

The probe was last touched at 17:37 and `recordAtoms` shipped at 22:52 the
same day, so the figures #83 published with it were valid when taken and
**cannot be re-derived from it now** — it would be atoms against atoms. A
banner now says so on every run.

### 9c. `audit_flow_resolve.py` — the suggested reasoning is right for the ordinal and wrong for atoms

The reasoning offered was: its `reorder` arm reports 94.4% WRONG, so it
demonstrably can report WRONG. That is **true of the ordinal path and false of
the content path**, and the difference is structural rather than incidental.

`recordAtoms` is a field ON AN ENTRY, and this probe's mutations are
entry-level permutations of a Python list. So the witness travels with the
logical element by construction. Measured on a three-row fixture:

| | with `recordAtoms` | with the field absent |
|---|---|---|
| `mut_reorder` | **CORRECT** | WRONG |
| `mut_resort` | **CORRECT** | WRONG |

Both arms pass a content witness for free. Run today, that probe would report
the shipped atoms as near-perfect under re-sorting and the number would be an
artefact of the harness — which is `MEASUREMENT.md` §4's own lesson acquiring
a new instance inside the probe that lesson is written about.

Fixed for `mut_reorder` only, where it is decidable: that mutation's stated
model is that **only the tied controls move and the scaffold stays**, so the
row — and therefore its text — belongs to the POSITION exactly as the mmid
does. One line. `mut_resort` is left alone, because there the record really
does move with its contents and CORRECT is the right answer.

The effect, same 8 sites, same seed, HEAD against the one-line fix:

| arm | HEAD | fixed |
|---|---|---|
| `reorder` witnessed (n=123) | 48.8% CORRECT / 4.9% REFUSED / **46.3% WRONG** | 9.8% / 4.9% / **85.4% WRONG** |
| `reorder` unwitnessed (n=96) | 10.4% / 0% / 89.6% | 6.2% / 0% / 93.8% |
| `resort` witnessed (n=103) | 94.2% / 5.8% / 0% | **unchanged** |
| `resort` unwitnessed (n=93) | 10.8% / 0% / 89.2% | **unchanged** |

**39 percentage points of that arm's CORRECT rate was the harness handing the
content witness the answer.** `resort` does not move, which is the control
that the fix touched only the arm whose model required it.

Read the REFUSED column, not the CORRECT one: it is **4.9% before and after**.
Under the contested convention, "WRONG" here means *bound to the control now
sitting in the recorded row rather than to the recorded element* — which a
user who re-sorted a table would call correct. What the arm establishes
either way is that **nothing refuses**.

The same caveat applies to this paper's own `swap-controls` arm, and it is
now written at `mut_reorder`'s call site too.

### 9d. `audit_record_definition.py` — the new one

`--selftest`, six directions, output in §2. Each was built by running it:
two of the fixtures were vacuous before they fired.

---

## 10. Recommendation

**Neither definition is dominant, and the one that IS better on every axis is
the one that cannot be built where the field is.** Summarised on the three
numbers that decide it:

| | coverage | resort WRONG | drop-target WRONG | drop-other CORRECT | buildable in `recordAtoms`? |
|---|---|---|---|---|---|
| `tag_raw` — SHIPPED | 18.6% | 12.7% | 0.0% | 43.7% | — |
| **`tag_vis` — B only** | **18.5%** | **12.7%** | **0.0%** | **44.4%** | **yes, 2 lines** |
| `climb_*` — `search_page`'s rule | 29.0% | **14.9%** | **0.7%** | 59.3% | yes, ~50 lines |
| `lca_*` — the PROBE's rule | **41.0%** | **9.0%** | **0.0%** | **62.1%** | **no — it needs the crowd (§1b)** |

### SHIP: divergence B. Two lines, and it is a safety fix, not a tidiness one

`if (!_namable(n.parentElement)) continue;` in the walk, and the same guard on
the `img[alt]` pass. `_namable` is already in scope in
`_collectInteractivePage`, so there is nothing to duplicate.

- **22.3%** of every recorded witness is text no user can see (§4).
- Across the mutated arms it removes **16 silent mis-binds and introduces 4**,
  gains 27 resolutions and loses 10 (§5c); on `bump-digits` it HALVES the
  shipped rule's WRONG rate, 1.9% → 1.0%; and it removes the only mis-bind on
  `drop-other`.
- It costs **0.1pp of coverage**, inside the 0.6% drift floor.
- The diff is in Appendix A with RA1/RA2/RA3 and their ablation; the suite is
  green against it.

It is also the half with the clearest argument independent of any number: the
project's OTHER record-text consumer, `_obsSig`, already hashes `innerText`,
which excludes a `display:none` subtree. This makes two spellings of one
concept agree (PRINCIPLES 17).

### DO NOT SHIP: swapping the record rule to `_climbTo`

This is the recommendation I expected to make and the measurement reversed it.
It is **right on principle** — it is the project's own record notion, the
field's comment already claims to be using it, and it finds a record for 90.6%
of descriptors against the tag list's 50.2%. It is **wrong on the numbers**:

- **resort: 14.9% WRONG against the shipped 12.7%.** 61 descriptors the
  shipped rule gets right via its atoms, the climb rule gets WRONG via the
  ordinal, because its tighter record stops discriminating (§5a).
- **drop-target: 0.7% WRONG against 0.0%** — the only definition that binds to
  a stranger when the recorded row is gone, which is the exact hazard #99
  closed.
- Its coverage gain lands where the ordinal was already fine, and its losses
  land where it was not.

More coverage is not more safety, and nothing in §3 could have shown that. The
cost (§7: median free, p90 inside the A/A floor, one site +432ms) would have
been an argument about the tail; the safety numbers settle it without needing
one. The A-half diff is in Appendix A anyway, ablated and suite-green, because
a rejected candidate with a working patch is cheaper to re-open than one
without.

### BUILD NEXT: move the atom computation to RECORD time

The LCA definition is better on coverage (41.0%), on re-sort (9.0% WRONG), on
a dropped neighbour (62.1% recovered) and on the arm that matters most
(drop-target, 0.0% WRONG). It **cannot** be computed in the collector, because
`recordOf` takes the crowd and the crowd is a Python-side equality over seven
fields (§1b). Reproducing that grouping in JS would be a second spelling of
the descriptor itself.

The server already knows the crowd — `atoms_map(hits)` is where it is formed.
A `record_atoms(mmids, groups)` op would:

- make **any** definition computable exactly, including this one and anything
  better;
- cost **one bridge round trip (~24ms, #38) on the rare call that records a
  flow**, instead of what it costs now;
- **delete** the standing per-read cost — `recordAtoms` is not behind
  `if (structured)`, so every `read_page` on every page computes it for every
  stamped element, at +1.3ms median and +36.7ms worst (§7), for a consumer
  only `record_flow` uses;
- and close §4a's media gap for free, because the server would ask by mmid
  rather than depending on which of the three entry literals built the row.

What it needs before it is built is the thing §12 says is missing: the
measurement is of a definition's BEHAVIOUR under mutations I modelled, on a
corpus that is mostly not the target population. The record-time design makes
the definition swappable, which is the right property to have while that is
still true.

### ALSO WORTH FIXING, separately

§4a: two of the three entry literals (`background.js:11197`, `:11229`) set
`clickable: true` and do not compute `recordAtoms`, so a `role: 'media'` entry
is a legal flow target that can never carry a content witness — 0.63% of this
corpus. One line each, and it deserves its own fixture rather than being
folded into this diff.

---

## 11. What this sample cannot tell you

1. **The corpus is mostly the wrong population, and §1c changes that claim
   rather than removing it.** #83 said flatly that the frozen corpus holds no
   admin tables. That was true OF THE FIRST 59 SITES, which is all any
   descriptor probe could reach. This run saw 93, and the second half does
   contain the shape: `syncfusion_grid` (n=120, shipped **109**),
   `premierleague` (120, 53), `daterangepicker` (120, 32), `adminlte` (49, 32),
   `jspreadsheet` (4, 2) — plus `moodle` and `fullcalendar`, which produce no
   tied crowd at all.

   That is the single most interesting cut in the data and it points AGAINST
   the headline: on a real `<tr>`-built data grid the shipped tag list is
   nearly complete (109 of 120 on syncfusion), and the 18.6% corpus-wide
   figure is dominated by `<div>`-built pages that are not data grids. These
   are still DEMOS of admin UIs rather than internal tools behind a login, so
   the population question is narrowed, not closed (MEASUREMENT R2). What
   would close it is the corpus `OPEN.md` item 2 already asks for.

2. **The population that needs a record witness at all is narrower than "rows
   in a table", and the fixture work is what showed it.** `near` is the fourth
   descriptor rung, and whenever the control sits directly in its row `near`
   picks up the row's own text — so the descriptor is unique, no ordinal is
   recorded, and `recordAtoms` is never consulted. A crowd only forms when
   something makes `near` identical across rows, such as an actions cell. Any
   coverage figure here is a share of *that* population, not of rows.

3. **The arms are DOM moves, not re-renders.** A real re-sort in React may
   discard and rebuild nodes, which re-stamps mmids and changes what every
   resolver sees. Within one page mmids persist with the element, which is what
   lets `want = mm` track logical identity at all; a re-render cannot be
   modelled this way. The arms are therefore the *kind* re-sort, not the whole
   family.

4. **`swap-controls` has no ground truth** and is read for its refusal rate
   only (§9c).

5. **Divergence B's figure is an UPPER bound.** The filtered cells use the
   probe's rule, which is stricter than the collector's `_namable`: it rejects
   `display: contents`, which `_namable` keeps for the reason #93 measured. So
   the measurement can only over-report how much of the shipped field is text
   nobody can see.

6. **The cost figure is in-page JS on a replayed HAR**, on an idle machine,
   with the page already settled. It is a lower bound on a loaded machine and
   says nothing about a page that is still building.

7. **Nothing here measures task success.** Every figure is about whether a
   descriptor binds to the element it was recorded for. Whether a recorded flow
   completes more often is not measured by any ruler in this repo
   (`MEASUREMENT.md` §6).

---

## 12. The one thing I am least sure of

**Whether the LCA rule's advantage is real or an artefact of the mutations I
modelled** — because that is what §10 asks the owner to build for, and because
the same question already reversed one recommendation in this document.

The climb rule looked clearly better on the only axis §3 can see (29.0%
against 18.6%) and turned out to be WORSE where it counts. The LCA rule now
looks better on every axis I measured: coverage 41.0%, re-sort 9.0% WRONG,
drop-target 0.0%, drop-other 62.1% recovered. **Every one of those is a
behaviour under a mutation I chose**, and `MEASUREMENT.md` §4 exists because
exactly this harness family published "0% WRONG on every mutation" over a set
that excluded the one mutation an ordinal cannot survive.

The arm I most suspect is missing is a **re-render**: React discarding and
rebuilding the rows rather than moving them. My arms move existing nodes, so
mmids persist with the element and `want = mm` tracks logical identity — which
is what makes them scorable and also what makes them unlike the thing that
breaks flows in practice (fix #5 is in this codebase because a re-render
orphans mmids mid-form). A record witness built from a big container is
plausibly more robust there than one built from a row, or plausibly less;
nothing here says which.

Two smaller ones, in order:

- **B's safety benefit rests on small numbers.** 16 mis-binds removed against
  4 introduced, out of 39 disagreements in 4,207 witnessed comparisons. The
  direction is consistent across four arms and the `bump-digits` halving is
  the clearest single piece, but I would not defend "16 vs 4" as a precise
  ratio. The reason I still recommend shipping it is that it does not depend
  on that number: an atom nobody can see cannot be verified by the person
  reading the flow file, and `_obsSig` already answers the same question the
  same way.
- **Whether the climb rule's records are the member's own ROW.** §6a measures
  the consequence rather than the thing: on the 33.9% of members whose climb
  record contains another crowd member it is 21.5% CORRECT / 21.5% WRONG, so
  there it is a coin flip. A record has no independent oracle the way a
  rendered control does, so the only test is behaviour under the mutations
  above — which is the first bullet again.

The cheapest thing that would settle all three is not another corpus pass: it
is ten recorded flows on real admin tables, replayed after a real re-sort and
after a real re-render. That is the same evidence `OPEN.md` item 2 already
asks for, and the same evidence §11.1 says this corpus cannot supply.

---

## Appendix A. The diff, and its ablation

The change is in `extension/background.js` only. Two independent halves; they
were built and ablated separately so neither hides the other.

Four shadow checkouts from `git archive HEAD`, patched with
`tools/patches/apply_record_atoms_diff.py` (which refuses loudly if an anchor is not found
exactly once, so it can never silently patch nothing), then
`CB_ROOT=<shadow> python tools/test_widgets.py`:

| check | pre | B only | A only | both |
|---|---|---|---|---|
| RA1 hidden text is not a witness | FAIL | **PASS** | FAIL | PASS |
| RA4 a `<div>`-built row has a record | FAIL | FAIL | **PASS** | PASS |
| RA7 the `dup:record` copies are byte-identical | FAIL | FAIL | PASS | PASS |
| RA2 the record's VISIBLE text is still recorded | PASS | PASS | PASS | PASS |
| RA3 a row with nothing hidden is unchanged | PASS | PASS | PASS | PASS |
| RA5 a `<li>`-built row still has a record | PASS | PASS | PASS | PASS |
| RA6 a control with no repeated sibling row gets none | PASS | PASS | PASS | PASS |

The three assertions fail against HEAD and each is fixed by its own half; the
four controls pass in all four arms, which is what makes them controls
(PRINCIPLES 11). RA6 is the one that matters most of the four: it is the
control that this did not become "every element has a record".

**The repo's own tripwire caught the first version of the diff.** With
`dup:record` tagging only the new copy, `MC2 no dup: tag claims a duplication
that no longer exists` failed with `singletons=['record']` — so the diff had to
tag the originals in `_searchTextPage` as well, which is the correct shape for
a FORCED duplicate and is what RA7 then enforces.

Full suite against the patched shadow, run with the repo's own
`tools/run_tests.py` from inside the shadow so nothing resolves back to the
working tree:

```
pre   : 21 passed, 0 failed, 0 skipped of 21 suite(s); 1607 checks; 156.3s  ALL GREEN
B only: 21 passed, 0 failed, 0 skipped of 21 suite(s); 1607 checks; 155.3s  ALL GREEN
A + B : 21 passed, 0 failed, 0 skipped of 21 suite(s); 1607 checks; 156.7s  ALL GREEN
```

Identical, suite for suite and check for check, for the half I recommend and
for both halves together.

`tools/test_widgets.py` (RA1-RA6) is deliberately **not** named `test_*`:
`run_tests.py` discovers suites with `root.glob("test_*.py")` and `C28`
requires every discovered suite to have a row in `tools/README.md`, so landing
a suite whose checks fail against the current tree would turn the project red
for a fix that has not been applied. Rename it and add its row when the diff
lands; RA7 belongs in `test_contracts.py` beside MC1/OC7/C48.

`tools/patches/apply_record_atoms_diff.py <checkout> [--b-only|--a-only]`
applies it to any tree, which is how the four arms above were built. The diff
it produces (116 lines) is reproduced below; **B is the half this paper
recommends**, and `--b-only` is the two-line version.

```diff
--- a/extension/background.js
+++ b/extension/background.js
@@ -6400,6 +6400,74 @@
 }
 
 function _collectInteractivePage(structured, scopeMmid, detail, ledger, geometry, format) {
+  // dup:record — BYTE-IDENTICAL to the copies in `_searchTextPage`, pinned by
+  // RA7. Both are injected separately so neither can call the other: a free
+  // sibling identifier in an injected function throws a ReferenceError that
+  // every try/catch swallows, which is the C11 class that left three readiness
+  // signals dead in production for a release (#30).
+  //
+  // WHY THESE ARE HERE. `recordAtoms` used to ask `closest('tr,li,dl,article,
+  // figure,fieldset')`, and its own comment claimed that was "the same set
+  // `_climbTo` uses". It was not: `_RECORD` carries no FIELDSET, and -- the
+  // part that matters -- `_climbTo` falls back to `_isRecord`, a node with at
+  // least one SAME-KIND sibling under its parent, i.e. one of a repeated run
+  // (MDR/DEPTA's data record, the notion #27's fold signature uses). A tag
+  // list only finds a record in <tr>/<li> markup, and the apps this feature
+  // runs against build rows from <div>s. One concept, one spelling
+  // (PRINCIPLES 17).
+  const _RECORD = { TR: 1, LI: 1, DL: 1, FIGURE: 1, ARTICLE: 1 };
+  const _CLIMB_STOP = {
+    MAIN: 1, NAV: 1, HEADER: 1, FOOTER: 1, ASIDE: 1, SECTION: 1,
+    FORM: 1, FIELDSET: 1, TABLE: 1, UL: 1, OL: 1, BODY: 1, HTML: 1,
+  };
+  const _sig = (e, d) => {
+    const s = e.tagName + '.' + (typeof e.className === 'string'
+      ? e.className.trim().replace(/\s+/g, ' ') : '');
+    if (d <= 0) return s;
+    const k = [];
+    for (const c of e.children) k.push(_sig(c, d - 1));
+    return s + '(' + k.join(',') + ')';
+  };
+  const _cls = (e) => {
+    try {
+      return (typeof e.className === 'string'
+        ? e.className.trim().split(/\s+/).filter(Boolean) : []);
+    } catch (err) { return []; }
+  };
+  const _sameKind = (a, b) => {
+    if (a.tagName !== b.tagName) return false;
+    const ca = _cls(a), cb = _cls(b);
+    if (!ca.length && !cb.length) return _sig(a, 3) === _sig(b, 3);
+    if (!ca.length || !cb.length) return false;
+    for (const t of ca) if (cb.indexOf(t) !== -1) return true;
+    return false;
+  };
+  const _isRecord = (n) => {
+    try {
+      const p = n.parentElement;
+      if (!p || p.children.length < 2) return false;
+      let k = 0;
+      for (const c of p.children) { if (_sameKind(n, c) && ++k > 1) return true; }
+      return false;
+    } catch (e) { return false; }
+  };
+  // `_climbTo` returns a hop COUNT because search_page needs the distance;
+  // this is the same walk returning the node.
+  const _recordOf = (node) => {
+    try {
+      let n = node, d = 0;
+      while (n && d < 8) {
+        n = n.parentElement || (n.getRootNode && n.getRootNode().host) || null;
+        if (!n) break;
+        d++;
+        if (d <= 4 && _RECORD[n.tagName]) return n;
+        if (_CLIMB_STOP[n.tagName]) break;
+        if (_isRecord(n)) return n;
+      }
+    } catch (e) {}
+    return null;
+  };
+
   // ONE MEMBER TOKEN FOR BOTH FOLD RENDERERS.
   //
   // There were two, hand-maintained, and they had drifted in BOTH directions:
@@ -10088,12 +10156,19 @@
       // counter — and a two-load stability check does not catch it.
       recordAtoms: (() => {
         try {
-          let r = el.closest && el.closest('tr,li,dl,article,figure,fieldset');
+          let r = _recordOf(el);
           if (!r || r === el) return null;
           const out = [];
           const w = document.createTreeWalker(r, NodeFilter.SHOW_TEXT);
           let n, seen = 0;
           while ((n = w.nextNode()) && seen < 40) {
+            // RENDERED TEXT ONLY, the same question `_namable` answers for a
+            // name (#37) and the same answer `_obsSig` already gives by
+            // hashing `innerText`. An atom nobody can see witnesses something
+            // the user cannot verify, and it stops matching the moment that
+            // subtree's state changes — a closed mega-menu donated 339
+            // characters to one eBay nav item, 26.3% of a listing.
+            if (!_namable(n.parentElement)) continue;
             const t = (n.nodeValue || '').replace(/\s+/g, ' ').trim();
             // A letter or a digit in ANY script. The shortest strings on a page
             // are often the answer (#29), so this is not a length test — it is
@@ -10103,6 +10178,7 @@
             if (out.indexOf(t) < 0) { out.push(t); seen++; }
           }
           for (const im of r.querySelectorAll('img[alt]')) {
+            if (!_namable(im)) continue;
             const a = (im.getAttribute('alt') || '').trim();
             if (a && out.indexOf(a) < 0 && out.length < 48) out.push(a);
           }
@@ -14301,6 +14377,9 @@
   // on. The aozora and gov.uk leaks stay fixed because <a> inside <li> reaches <li>
   // and stops there; it is the COLLECTION above it that was the defect, and no
   // record rule ever climbs into one.
+  // dup:record — the record notion, copied BYTE-IDENTICALLY into
+  // `_collectInteractivePage` for `recordAtoms`. Injected functions lose their
+  // closure, so the duplication is FORCED; RA7 is the enforcement.
   const _RECORD = { TR: 1, LI: 1, DL: 1, FIGURE: 1, ARTICLE: 1 };
   // ...AND WHEN NO TAG DECLARES THE RECORD, THE REPETITION DOES.
   //
```
