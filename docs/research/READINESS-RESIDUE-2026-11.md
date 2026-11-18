# Readiness residue, 2026-11

Closing the nine cases `#82`'s adversarial audit left named and unfixed: **3
unscoped false QUIETS** and **6 steady-state false BUSIES**. Read
`docs/READINESS.md` first; this is its open list worked down, and
`docs/research/READINESS-ADVERSARIAL-2026-11.md` is the run that produced the
nine.

**Headline.** Two of the three false quiets were already closed by work that
shipped after the audit and nobody had re-run the instrument to notice. One
remains and is a recorded DON'T BUILD with its own numbers. Five of the six
false busies are closed by a **misclassification fix**: a `textContent =`
assignment arrives as a `childList` record, and the ring was filing it as
*structural*.

Everything below was produced by running, not by reading. Where a number here
disagrees with `#82`, this one supersedes it and says so.

---

## 0. The diff, and how to reproduce

The product change is **not applied** — `extension/*.js`, `mcp_server.py`,
`tools/test_ops.js` and `tools/test_contracts.py` were outside this task's edit
allowance (other work was in flight there). It is
~~**`docs/research/readiness-residue-2026-11.diff`**~~ — **APPLIED, live-verified
and DELETED on 2026-11-18; the commit is the diff.** It was verified to apply to a clean
`HEAD` checkout:

```
# (the diff is gone — it shipped. See CLAUDE.md #88.)
```

Five files, ten hunks: §3 (the re-text tier, `listener_tag.js` x2 +
`background.js` x2), §4 (the two blind-frame fixes, `background.js` x3), §5 (the
tier marker, `mcp_server.py`), and the renderer/contract checks
(`tools/test_ops.js`, `tools/test_contracts.py`).

**Until it is applied the readiness suite is red by 2 (`R35`, `R36`)**, which is
the point: a check that passes against the code it is meant to fix is not a
check (PRINCIPLES 11).

```
.venv/bin/python tools/audit_readiness_adversarial.py --json out.json   # the 21 shapes
.venv/bin/python tools/audit_retext_tier.py                             # the candidate + its cost
.venv/bin/python tools/audit_retext_prevalence.py                       # the same question on the frozen corpus
.venv/bin/python tools/test_readiness.py                                # 56 checks
```

The adversarial probe **refused to run** at the start of this work: its Patch-A
anchor had shipped, so `assert TAG.count(PATCH_A_OLD) == 1` fired. That is a
detector doing its job rather than skipping (PRINCIPLES 15), and it is the
reason the audit's own numbers could not have silently drifted. The block is now
an assertion that the fix is still in `listener_tag.js`, with the pre-fix arm
kept so the before/after can be produced on demand.

Three shapes were added to the set (19, 20, 21) — see §3.3 and §4.

---

## 1. The nine named cases, re-derived

| # | case | `#82` | now | verdict |
|---|---|---|---|---|
| 1 | 05 skeleton, late timer paint @3500 | FALSE-QUIET | FALSE-QUIET | **still real — DON'T BUILD (§2)** |
| 2 | 15 late cross-origin iframe @3500 | FALSE-QUIET | BLIND (states the limit) | **ALREADY closed, by #82's own `blindFrames`** |
| 3 | 15 late cross-origin iframe @6500 | FALSE-QUIET | BLIND | **ALREADY closed** |
| 4 | 01 `textContent` ticker @3500 | FB-PERM | → TEXT tier | **closed BY THE DIFF (§3)** |
| 5 | 01 `textContent` ticker @6500 | FB-PERM | → TEXT tier | **closed BY THE DIFF** |
| 6 | 11 live-value grid @3500 | FB-PERM | → TEXT tier | **closed BY THE DIFF** |
| 7 | 11 live-value grid @6500 | FB-PERM | → TEXT tier | **closed BY THE DIFF** |
| 8 | 13 clock + finished table @6500 | FB-PERM | → TEXT tier | **closed BY THE DIFF** |
| 9 | 13 clock + building table @3500 | FB-PERM | STRONG | **correctly busy — the audit misclassified it (§3.4)** |

Totals across 21 shapes × 4 offsets = 84 unscoped reads:

| | `#82` (18 shapes) | HEAD (21 shapes) | with §3+§4 applied |
|---|---|---|---|
| unscoped FALSE-QUIET | 3 | **1** | **1** |
| blind-stated (was a false quiet, now a named limit) | — | 2 | 2 |
| unscoped FB-PERM | 6 | 6 | **1** |
| fb-tail | 5 | 6 | **4** |
| fb-load (inherent: the window covers the parse) | 14 | 16 | 16 |
| scoped-to-main FALSE-QUIET | 5 | **1** | **1** |

The scoped column moved from 5 to 1 without anyone touching it: `#82`'s Patch A
(a `ShadowRoot` has no `parentElement`, so direct appends into one were
unattributable) closed 18@3500 and 18@6500, and the blind clause closed 15.

---

## 2. The one remaining false quiet — DON'T BUILD, and it is already recorded

Shape 05: a skeleton, no network at all, silent from ~0.3s, painting from a
`setTimeout` at 5s. At 3500 every signal reads zero and the verdict is silence,
correctly describing a page that is about to change.

This is **not** newly open. `OPEN.md` item 5(c) measured the only mechanism that
could reach it — wrapping `setTimeout`/`setInterval` at `document_start`, the
way `listener_tag.js` already wraps `addEventListener` and `attachShadow`, so
"the page has work booked" becomes a fact it declared. The mechanism *works*
(the probe separates the fixtures) and dies on the corpus:

| window | settled pages carrying the line |
|---|---|
| timers due within 2000ms | **55.2%** |
| timers due within 300ms | **31.0%** |

More than half of settled pages have work booked, because polling is normal —
the always-on warning #15 priced and #43 deleted `readyState` for. Tightening
the window removes the point: the shape this exists to catch paints 2,500ms out,
so a 300ms window misses it *and* still fires on a third of pages. The probe is
kept at `tools/audit_pending_timers.py`.

**Re-confirmed here rather than taken on trust**: shape 05 carries an infinite
CSS shimmer, and shape 06 — a *settled* page — carries one too, with identical
signals at all four offsets. "Running infinite animation" cannot separate them.

A page that is silent, has nothing in flight, and will paint from a timer is
indistinguishable from one that has finished. That is the limit, stated.

---

## 3. The six false busies: a `textContent =` is a RE-TEXT, not a structural change

### 3.1 The defect, in `READINESS.md`'s own words

> *"a ticker that updates via `textContent` arrives as `childList` — Chrome
> records it as remove+add of a text node — so it trips the STRONG banner."*

§5(b) names this as the case the `#70` kind-split provably does not cover, and
`#82` measured the consequence: six steady-state reads told

> *"Elements were added, removed or re-texted in that window … do NOT conclude
> something is absent from this read"*

about content that never changes again. A clock. A live price grid. A table that
finished two seconds ago with a clock ticking beside it.

### 3.2 Why this is a correction, not a new heuristic

The ring's vocabulary already has a `text` kind (`characterData`), and the
banner's own words define `structural` as **elements** being added or removed.
The DOM implements `textContent =` by removing the old `Text` node and inserting
a new one, so it arrives as `childList`. `Node.nodeType` decides which of the two
existing buckets a record belongs in: a declaration, with no threshold, class
name, framework name or wordlist (PRINCIPLES 1).

**It cannot produce silence, by construction rather than by measurement.** A
reclassified record moves from `structural` to `text`, and both are non-zero
tiers — so a read that warned before still warns. What changes is *which*
warning. That is the whole safety argument and it needs no corpus.

The second half is the renderer: `readinessNote` folded `structural || text`
into one sentence, so the reclassification alone changes nothing an agent reads.
Three tiers, decided by the three `MutationRecord` types the spec declares:

| measured | said |
|---|---|
| elements added or removed | **THE DOM IS STILL CHANGING** — do not conclude absence |
| text only | **TEXT IS CHANGING, STRUCTURE IS NOT** — the set of controls is complete; values may be stale |
| attributes only | **Minor DOM activity** — structurally current |
| nothing | silence |

The middle tier still **warns**. It never claims values are stable; it claims
only what was measured, that the set of elements did not change in the window.
A page revealing content by `el.textContent = …` lands here and is told text
changed recently, which is true and is the thing to act on.

Before and after on shape 11, the live-value grid, same instant:

```
HEAD     *** THE DOM IS STILL CHANGING (last change 7ms ago; 900+ change(s) in the last
         3000ms: 900 structural). Elements were added, removed or re-texted in that
         window … do NOT conclude something is absent from this read …

PATCHED  *** TEXT IS CHANGING, STRUCTURE IS NOT (last change 14ms ago; 900+ change(s) in
         the last 3000ms: 900 text). No element was added or removed in that window, so
         every control in the listing below is still there and no new one appeared …
         treat any VALUE here as possibly already stale …
```

### 3.3 Measured, with the arms taken from one ring

The reclassification happens at **record** time, so the naive A/B is two page
loads. Instead one instrumented ring stores a `retext` bit beside each record and
the query reports it, so **both arms are computed from the same records at the
same instant** — run-order drift cannot align with an arm that does not have its
own run (PRINCIPLES 10). `tools/audit_retext_tier.py`, 21 shapes × 4 offsets.

**9 flips, 0 losses.** A flip is a loss only if it moves a read that is genuinely
still building into a tier claiming the set of elements is stable; none does, and
none can (§3.2).

Two shapes were added because the set could not put the rule under load:

- **19 — a text-only arrival sampled WHILE it arrives.** Twenty empty divs
  filled one at a time by `textContent =` over 8s, so every offset is
  mid-arrival. Flips to TEXT at 3500/6500 with `changes_later = True`, which is
  correct: the reader is warned that text is moving.
- **20 — a `textContent =` that DESTROYS ten buttons.** The record carries the
  removed `<button>` elements, so it stays **structural** at every offset. This
  is the control that earns its keep: a rule phrased as *"a textContent
  assignment is a re-text"* would file the loss of ten controls as a text change.
  The rule is about the node types in the record, not the API that produced it.

### 3.4 What it does NOT fix, and that is the correct answer

Shape 13 at 3500 — a clock ticking beside a table that finished at ~2s. The
3000ms window still covers 280 genuine element appends, so the verdict stays
STRONG. `#82` filed it as FB-PERM; it is **fb-tail**, the documented cost of the
window, and `since` is printed beside the count so the reader can tell "changed
20ms ago" from "changed 2,900ms ago". Six minus five is not one defect left; it
is one row that was never a defect.

### 3.5 Cost

The scan early-exits on the first non-`Text` node, so an element append pays one
`nodeType` read. Measured against the unpatched ring, interleaved on the same
page load with an A/A floor taken in the same sequence, 7 replicates, order
rotated, at **40,000 mutations in one batch** — the 2,000-row grid regime `#70`'s
own cost note names:

| churn (40k in one batch) | base | patched | overhead | A/A floor |
|---|---|---|---|---|
| append (elements) | 9.3ms | 9.3ms | −0.00% | 0.00% |
| retext | 14.8ms | 15.0ms | +1.35% | 0.68% |
| attributes | 10.1ms | 10.0ms | −0.99% | 0.00% |

An independent second run of the whole probe, for the machine drift a single
table hides: append 9.9 → 9.9ms (floor 3.03%), retext 16.0 → 15.9ms (−0.62%,
floor 1.88%), attributes 11.3 → 11.2ms (−0.88%, floor 0.00%). **Across both
runs every reading is inside its own floor, and the sign of the "overhead" is
not even stable** — which is what an unmeasurable cost looks like. At 10,000
mutations: −6.45% to +2.94%, same picture. Against `#38`'s ~3,600ms model turn,
0.2ms on 40,000 text swaps is nothing.

**The first version of this cost measurement timed the wrong thing** and reported
`0.0% overhead against a 16.67% A/A floor`, i.e. nothing at all. A
`MutationObserver` callback is a **microtask**: it is queued while the loop runs
and executes at the checkpoint *after* it, so a timer closed at the end of the
synchronous loop measures the page's own DOM writes and none of the work under
test. The probe now `await`s a microtask turn before closing the clock.

### 3.6 The controls are not vacuous — proven by breaking the rule two ways

PRINCIPLES 11, and the brief's own warning that `#82`'s `R29` passed in both
arms. The rule was ablated into the two wrong versions a reviewer would most
plausibly write, and the controls caught both:

| rule as written | R35 | R35c | R35d |
|---|---|---|---|
| **EVERY node is Text** (shipped) | PASS | PASS | PASS |
| **ANY node is Text** (`OR` instead of `AND`) | PASS | **FAIL** | **FAIL** |
| **`addedNodes` only**, ignoring what was removed | PASS | **FAIL** | PASS |

Under both wrong versions, `textContent = 'gone'` over ten `<button>`s reports
`structural +0, text +1` — ten controls destroyed and filed as a text change.
A control that only ever passes is not a control.

### 3.7 Prevalence on real pages

See §7. The synthetic result says the rule behaves; PRINCIPLES 9 is explicit
that it cannot say whether it matters on the web.

---

## 4. Two adjacent defects, both found by one new shape

Shape 21 is an attribute-only carousel (so the verdict is MINOR) beside a
cross-origin frame that is still painting, with the frame in a `<footer>`
outside `<main>`. The set had no such shape, which is why both of these survived
`#82`.

**(a) The MINOR tier claims structural completeness and did not carry the
cross-origin caveat.** `_withBlind` rides the two fully-quiet paths only — so
the one verdict that says *"the listing below is structurally current"* in words
was the one making that claim with nothing said about the frame it cannot read
into. Measured: `blind: False` at HEAD, `True` with the fix.

**(b) The blind-frame count is page-wide and did not say so.** It used
`document.querySelectorAll`, then printed under SCOPED verdicts — so a read
scoped to `<main>` named an ad frame in the `<footer>`. That is the page-level
fact leaking into a scoped read that `#11` and `#26` both had to stop, and the
network clause in the *same banner* avoids it by saying PAGE-WIDE out loud.
Measured: scoped-to-main goes `BLIND → QUIET` with the fix, while
scoped-to-footer still counts it.

Counting through `_scan` also reaches a cross-origin frame nested inside a
same-origin one, and inside a shadow root, which `document.querySelectorAll`
never did.

---

## 5. A live string-contract defect found on the way

`mcp_server.py`'s `_BANNER_TIERS` is a hand-kept list restating the phrases
`background.js` leads a banner with — the same cross-half contract `C12` exists
for, and **the only one of them with no tripwire**. Driving the real
`readinessNote` through every branch and matching each output against the list:

```
structural           tier='THE DOM IS STILL CHANGING'
attr-only            tier='Minor DOM activity'
domstable            tier='DOM STABLE, NETWORK BUSY'
domstable SCOPED     tier=None
    EMITTED: '*** DOM STABLE IN THE SUBTREE YOU SCOPED TO, NETWORK BUSY. …'
scoped-unknown       tier='No DOM change could be attributed'
no recorder          tier='PAGE IS STILL SETTLING'
```

On a **scoped** read the marker matches nothing, so `_banner_tier` falls back to
the raw banner string — which the mutation counter defeats, reinstating the
duplicate-banner defect eval 7 measured (~1,200 characters of
identical-in-substance prose in one response). A scoped read is the documented
way to go deep into a page, so that was the half that mattered.

The marker becomes the invariant prefix `DOM STABLE`. **C44** is the tripwire:
for every marker in the list, some banner literal in `background.js` must carry
it in the run of text between `` `*** `` and the template's first `${…}`.
Anything after an interpolation depends on which branch ran, which is exactly
how this one broke. Banners whose text carries no ticking value (the
frozen-fade and cross-origin-frame sentences) need no marker, because exact
equality already folds them — so the rule asks only that every marker is
reachable, not that every banner has one.

*My first version of that check re-parsed the tier list out of the source and
picked up quoted text from a comment, reporting the PATCHED arm as still
broken. It reads the module attribute now. A too-dirty result gets re-derived
exactly like a too-clean one (PRINCIPLES 8).*

---

## 6. Checks, and the ablation

`tools/test_readiness.py` — 49 → **56**.

| check | HEAD | patched |
|---|---|---|
| **R35** a `textContent=` swapping only Text nodes is a RE-TEXT | **FAIL** | PASS |
| R35b CONTROL appending an ELEMENT is still structural | PASS | PASS |
| R35c CONTROL a `textContent=` that REMOVES an element is still structural | PASS | PASS |
| R35d CONTROL Text **and** Element in one record is structural | PASS | PASS |
| R35e CONTROL a direct `characterData` change is still text | PASS | PASS |
| **R36** a frame OUTSIDE the scope is not counted | **FAIL** | PASS |
| R36b CONTROL a frame INSIDE the scope still counts | PASS | PASS |
| | **54/56** | **56/56** |

Every reading is a **delta**: the fixture's own parse is a run of childList
records, so an absolute `structural == 0` would measure the harness rather than
the rule — the mistake `R14` exists to record.

Renderer and contract checks (delivered as diffs; `tools/test_ops.js` and
`tools/test_contracts.py` were outside this task's edit allowance):

| check | HEAD | patched |
|---|---|---|
| **R-TEXT** text-only churn → the TEXT tier, not the absence warning | **FAIL** | PASS |
| R-TEXT2 CONTROL one structural record still outranks any amount of text | PASS | PASS |
| R-TEXT3 CONTROL the text tier is a WARNING, not silence | PASS | PASS |
| **R-BLIND3** the MINOR tier names the frame it could not see into | **FAIL** | PASS |
| R-BLIND4 CONTROL with no blind frame it says nothing about one | PASS | PASS |
| **C44** every tier marker is reachable in an emitted banner | **FAIL** | PASS |
| C44b CONTROL the rule can fire on a planted marker | PASS | PASS |

**One existing check had to be rewritten to its invariant.** `R24b` asserted
`structural > 0` for a scoped read of a churning region — true only because that
region's `textContent =` ticker was *misfiled* as structural, which is the defect
R35 exists for. Its claim is that scoping to the churning region is not reported
quiet, and that is what it says now (`structural + text > 0`). The guard it
provides for R24 is unchanged, because both are zero for a settled region. Same
rewrite as `#30`'s TR8d, and it passes in **both** arms.

Full suite, both arms, on a shadow checkout (`git archive HEAD`):

| | suites | checks |
|---|---|---|
| HEAD | 21/21, 0 failed | 1,499 |
| HEAD + the readiness checks only | 21/21, 0 failed | 1,506 |
| HEAD + the whole diff | 21/21, 0 failed | **1,513** |

(`README.md`, `tools/README.md` and `CLAUDE.md` all state 1,493, which was
already stale at HEAD by 6 — the runner's own drift note reports it on every
run, and it is not this work's to fix mid-flight.)

`C11` — the injected-function free-identifier tripwire — passes: diff 3 edits
`_readinessPage`, and `_scan` and `_topRectFor` are already its inner closures.
`listener_tag.js` is a content script, not an injected function, so `_allText`
sits in the same IIFE closure as `rec`.

---

## 7. Corpus prevalence — the sample half

`tools/audit_retext_prevalence.py`. The same instrumented ring, the frozen
corpus replayed with JS intact, read at two offsets past DOMContentLoaded.
**105 of 106 sites replayed.**

| | reads whose tier changes |
|---|---|
| **@1500ms** (still building) | **0 / 105 — 0.0%** |
| **@4000ms** (steady state) | **5 / 105 — 4.8%** |
| pooled, all offsets | **6,399 / 23,196 in-window `childList` records are re-texts — 27.6%** |

The movers are `lichess`, `stripe`, `moodle`, `mui_datepicker`, `ng_material` —
a live clock, a payment widget, and three component demos with a ticking field.
Exactly the warn-forever class.

**The 0.0% at 1500ms is the result that matters most**, and it is a negative
control the synthetic shapes could not give: on a real page that is still
building there are always genuine element appends in the window, so the tier
stays STRONG. The fix cannot demote a page that is loading.

**The 27.6% is the other half.** Even where the tier does not move, better than
a quarter of the `childList` records the banner counts are re-texts — so a read
printing `906 structural` is really `413 structural, 493 text`. The kind counts
are the FACT this banner exists to report (`#70`: "40 @style and 40 structural
are opposite facts"), and a quarter of them were wrong.

**Priced against what this project has accepted before:** `blindFrames` shipped
at 6.9% of pages, `help=`/`error=` at 0.87% worst case. 4.8% of reads with a
cost inside the drift floor is comfortably in range, and these are specifically
the reads currently telling an agent *not to conclude absence*, for ever.

**CAVEAT, stated rather than rounded away.** A HAR replays with
`not_found="abort"`, so churn driven by a request the capture did not record
never happens: a `setInterval` + `textContent` clock still runs, a live price
fed by polling does not. The "ready but chatty" class is therefore
UNDER-represented and **4.8% is a floor** — the same shape as `#78`'s note that
corpus HARs are captured after consent, so CMP frames are under-counted.

---

## 8. Investigated and rejected

- **Per-landmark attribution for an unscoped read.** Re-confirmed, not
  re-derived: `regions()` costs **2.88–2.91ms** per read against **0.002–0.006ms**
  for the doc-wide query and **0.022ms** for one scoped query; enumerating
  landmarks and running one scoped query each costs 1.87–1.91ms at 5 and
  11.3–11.5ms at 30. It fixes 3 of the 6 false busies and no false quiet, and it
  forces an ownership rule for records whose target was collected — the judgement
  the design exists to avoid. `OPEN.md` 5(a) stands.
- **Net node-count delta** (`addedNodes.length − removedNodes.length`) as the
  separator. Rejected before measuring: a pagination click that removes 20 rows
  and adds 20 is net zero and is absolutely a content change, so the signal
  cannot carry a tier. Node **type** separates the same cases and is sound on
  that one.
- **Distinct-target counting** ("a ticker rewrites one node; a build adds many").
  Rejected on inspection: a `childList` record's target is the *parent*, so a
  ticker on `#clk` and a build appending to `#h` both report one distinct target.
- **Wrapping `setTimeout` to declare booked work** — see §2, already measured
  and rejected at 55.2% of settled pages.
- **"Running infinite CSS animation" as a skeleton signal** — identical on
  settled shape 06 and building shape 05.

---

## 9. Limits of this work

- **Headless Chromium, tab not throttled.** The agent's tab is hidden by design
  (`#12`), where timers clamp to roughly 1Hz; shapes 17/18 approximate that with
  400ms commits and nothing here reproduces it exactly.
- **The shapes are synthetic.** They are built to put the rule under load, which
  is the right instrument for "does it behave" and the wrong one for "does it
  matter" (PRINCIPLES 9). §7 is the other half.
- **HAR replay aborts unrecorded requests**, so steady-state churn driven by
  polling does not happen and the "ready but chatty" class is under-represented
  in §7. Those numbers are a floor.
- **No live pass.** `extension/*.js` was outside this task's edit allowance, so
  the diffs have been proven in a shadow tree and in both arms of every check,
  and **not** against a real Chrome. PRINCIPLES 12 is explicit that this is the
  step that catches what fixtures do not; it is owed before this ships.
