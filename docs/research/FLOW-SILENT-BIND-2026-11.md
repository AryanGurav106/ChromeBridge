# What can still bind to the wrong element and report PASS

Research pass, 2026-11-18. Nothing in `core/flows/`, `extension/` or
`mcp_server.py` was changed; every proposal is a diff in §7 for the owner to
apply. Probe written: `tools/audit_atoms_safety.py`.

Read `FLOWS-FAILURE-SURFACE.md` for the enumerated surface,
`FLOW-UNBREAKABLE-2026-11.md` for the ordinal-witness measurement, and
`FLOWS-CONCEPTUAL-BREAKS-2026-11.md` for the page shapes. This pass went
looking for what those three do not list, and the headline is that **the two
newest things in the feature are the two that can bind wrongly** — the content
witness that shipped yesterday to fix the last silent bind, and a collector
change that landed this morning.

---

## 0. The one-paragraph answer

The ranked list is below, and its first entry is a **regression introduced by
the fix for the previous entry**. #83 shipped record-text atoms to close the
re-sort mis-bind #72 measured at 94.4% WRONG. The atoms resolver is the only
binding path in `descriptor.py` that **deliberately ignores crowd composition**,
and that exemption is exactly what makes it unsafe when the target's own record
is gone: it binds on a single shared token, so a step that recorded
`['Acme Ltd', 'INV-1001', 'Paid']` binds to an unrelated invoice because that
one also renders the word `Paid`. Before atoms existed the same case REFUSED.
It is fixable from declarations, exactly, with no threshold and at zero cost on
an unchanged page, and §7's diff is three lines. **Its prevalence is NOT
measurable here**, and that is a finding rather than a gap: a single deletion
cannot produce it (0 of 77, corroborated by a second harness), because the
atoms recorded are by construction unique within the recorded crowd — it needs
the DATA to have moved on, and a frozen HAR has no "a week later". The second entry is that
`97efc75` (this morning) put cross-origin frame entries into the structured
array, which silently reversed a documented behaviour, made one fixture vacuous
and created a crowd whose only discriminator is the order Chrome enumerated the
frames in. Everything after those two is already known, and the brief's own three
questions are answered against it: a virtualised window IS declarable and
the declaration fires on **1 of 2,531** tied crowds, so it is DON'T BUILD
with the sample caveat (§4.3); the unwitnessable residue is **43.5%
dangerous, 36.9% provably interchangeable, 19.6% unknown**, and ~10% of it
is witnessable today and lost to a definition mismatch (§4.4); and
refusing costs nothing on an unchanged page for the gate proposed here,
against ~12.7% of all descriptors for the blanket refusal #72 rejected
(§2.8).

---

## 1. The ranked list

Ranked by (can it bind wrongly and report PASS) × (how reachable) × (how bad
the wrong action is). `SILENT` is the only unacceptable verdict.

**How the list was arrived at**, because "things I thought of" is what a
failure surface is always made of. Every point in `_resolve_recorded` and
`resolve` that RETURNS an mmid was enumerated — there are six — and each was
asked the same question: *under what change is the mmid it returns not the
element that was recorded?* The ranking below is that enumeration, not a sweep
for interesting cases. Two of the six turned out to be sound and are recorded
as such rather than dropped: the `len(hits) == 1` unique-match path and the
`narrowed` path both require the descriptor to still name exactly one element,
and the `alt` fallback re-tests href uniqueness at replay, so binding to a
different element needs the recorded one to be gone AND a new one to appear
carrying the same declaration — at which point it is the same destination.

| # | mode | verdict | closable from declarations? |
|---|---|---|---|
| **1** | **Atoms bind when the recorded record is GONE and a surviving record shares one of its words** | **SILENT** — reproduced deterministically; a regression against pre-#83. Prevalence **not measurable on a frozen corpus** (§2.8) and the reason is structural | **YES, exactly.** §2, diff §7.1 |
| **2** | **A cross-origin frame crowd, ordered by frame enumeration** | **SILENT** — reproduced; surface opened today by `97efc75` | **Partly.** Refusal is exact (§3); full identity is `MEASURE FIRST` |
| 3 | An unwitnessed ordinal in a **virtualised window** | `SILENT`, known (#90 M1, `OPEN.md` 2) | **NO, measured.** The declaration exists, is already read twice, and fires on **1 of 2,531** crowds — §4.3, DON'T BUILD on this corpus |
| 4 | An unwitnessed ordinal under a **re-sort** | `SILENT`, known (#72) — re-measured here at **86.2% WRONG with 0.0% refusals** | **NO** for the residue — §4.4, every candidate priced and refused |
| 5 | The self+anchor witness on the adversarial `reorder` arm | `SILENT`, known (`FLOWS-FAILURE-SURFACE` 3.3a) | no change proposed |
| 6 | `FRAME_CAP = 40` is a priority-sorted constant window | `SILENT` in principle, **unreached** | §5 — recorded, not built |
| 7 | A re-render that reuses nodes between `_bind` and the call | known, `OPEN.md` 1 | measured, deliberately unshipped |

**Re-derived and REFUTED, recorded so nobody re-opens them:** the 150-entry
listing cap does **not** reach the structured array (`if (structured)` returns
`out`, the uncapped array; `shown`/`_capTail` exist only for the string
render), so the cap is not a constant-size window for flows. And the
self+anchor **witness** path does **not** have mode 1's hazard — the crowd
composition check runs ahead of it, so dropping the target REFUSES there (§2.4).
Both were plausible, both were tested, both are dead.

---

## 2. Mode 1 — the content witness binds when the record it names is gone

### 2.1 The mechanism

`_resolve_recorded` has four branches that return an mmid. Three of them test
the crowd's COMPOSITION first (`len(hits) != of` ⇒ refuse). The atoms branch
does not, and says so in its own comment:

> ATOMS FIRST, AND THAT ORDERING IS SAFE FOR THE REASON THE BLOCK BELOW IS NOT.
> […] A content witness makes no positional claim at all.

That is true of a re-sort and of a *different* record being deleted, which are
the two arms it was measured on. It is false when the target's own record is
gone, because the resolver then has to decide between "my row lost a cell" and
"my row is gone and a stranger shares a word" — and it binds on
**intersection**, so one shared token is enough.

### 2.2 Reproduced, in pure Python, with no page

Three invoice rows; the flow deletes `INV-1001`. Recorded atoms are
`['Acme Ltd', 'INV-1001', 'Paid']` (`tools/audit_atoms_safety.py --self-test`):

| the page at replay | shipped resolver |
|---|---|
| unchanged | binds to the recorded row ✓ |
| re-sorted | binds to the recorded row ✓ |
| a DIFFERENT record deleted | binds to the recorded row ✓ |
| **target's record gone; a survivor is also `Acme Ltd`** | **binds to `INV-1099`** |
| **target's record gone; a survivor is also `Paid`** | **binds to `Delta SA / INV-1099`** |
| target's record gone, nothing shared | refuses ✓ |

The fifth row is the one that matters: the step deletes an invoice belonging to
a different customer, because both rows render a four-letter status word.

### 2.3 It is a REGRESSION, not a pre-existing gap

Strip `atoms` from that same descriptor — i.e. the file a pre-#83 recorder
would have written — and re-ask:

```
pre-#83  (ordinal only, no atoms)    -> REFUSED  (correct)
shipped  (atoms)                     -> BOUND ref_15  ['Delta SA','INV-1099']
```

The ordinal path refuses because `len(hits)=2 != of=3`. **The safety feature
made this case worse than the thing it replaced.**

### 2.4 And the mitigation that exists is a coincidence

`descriptor.py` appends a `via: "atoms"` note — which the runner surfaces as
`moved` — only when the bound element's index differs from the recorded `nth`.
Whether it does is luck:

```
target was row 1 (nth=0)   -> BOUND ref_15 (Gamma Co)   notes=1  REPORTED as moved
target was row 2 (nth=1)   -> BOUND ref_15 (Gamma Co)   notes=0  FULLY SILENT
```

A mid-list target binds wrongly with nothing reported anywhere.

**The witness path is NOT affected**, and testing it is what isolates the
cause. Same shape, a self+anchor witness instead of atoms: re-sort binds
correctly, and dropping the target's whole row, or just the target button,
**refuses** — because `len(hits) != want` is tested before the witness is
consulted. Mode 1 is specifically the composition exemption.

### 2.5 Why the measurement that shipped it could not see this

`tools/audit_record_witness.py` scores eight arms — `base`, `resort`,
`resort-last`, `resort-first`, `shuffle`, `edit-cell`, `bump-digits`,
`drop-other`. **None removes the target.** That is `MEASUREMENT.md` §4
verbatim, one entry after it was written: *a mutation harness measures the code
against the mutations it models, and when a harness reports a perfect score the
next question is what it does not model.*

**`tools/audit_flow_resolve.py` DOES have a `delete-target` arm, and I was
wrong about why it did not catch this.** My first reading was that it "does not
model atoms at all", on the evidence that `grep -n atoms` returns nothing from
it. The word is absent and the behaviour is not: it collects with the real
`_collectInteractivePage`, so its entries carry `recordAtoms`, so `build()`
records atoms and `resolve()` takes the atoms branch. The arm reaches the code.

What is actually true is narrower and worse: **its published `delete-target`
result — 0% CORRECT / 100% REFUSED / 0% WRONG — is #72's, and #72 predates
#83.** The arm that would have caught this existed, could reach the code, and
its last published number describes a build that did not contain the code.

**Re-run here for the first time since atoms shipped** (`--sites 40`):
`delete-target` comes back **0% CORRECT / 100% REFUSED / 0% WRONG** — the arm
is clean, and §2.8 explains why a single deletion cannot produce the hazard at
all. So the published number was stale and is also still right, which is the
least satisfying way for an audit to end and the honest one.

### 2.6 A second gap in the same place: the probe measured a different record

`audit_record_witness.py`'s header states its record definition is structural —
"the lowest common ancestor of the crowd, recursed until the member stands
alone… No `tr`/`li` vocabulary, no class name, no threshold". What shipped into
`background.js` is:

```js
let r = el.closest && el.closest('tr,li,dl,article,figure,fieldset');
```

Both are defensible. They are not the same, so **the coverage figure published
for atoms (43.9%) describes a field that was never built.** A `<div>`-built
card list — every modern SPA — has no such ancestor and gets
`recordAtoms: null`. `tools/audit_atoms_safety.py` reads `recordAtoms` off the
real collector, so §2.8's coverage column is the shipped number.

**And the mismatch has a price, measured in §4.4 from the other end:**
1,146 of the 1,445 crowds the shipped field finds no record for DO have
the structural one, and **248 of those carry text unique to the member** —
~10% of the whole unwitnessed residue, witnessable today, lost to the
definition mismatch alone.

### 2.7 The gate is not only a cost — it is strictly more discriminating

Worth stating before the prevalence table, because "add a refusal" reads as a
pure trade and this one is not. When the composition changed because a row was
**added** that shares a token — the same customer getting a second invoice,
which is the ordinary thing an invoice list does — intersection alone returns
two carriers and refuses. Requiring the whole record separates them:

```
HEAD      row added sharing the customer name -> REFUSED
PATCHED   row added sharing the customer name -> BOUND ref_11   (correct)
```

So on a changed crowd the gate refuses the case that was silently wrong **and**
resolves a case that was costing a turn. On an unchanged crowd it is inert by
construction, which is the answer to "what does refusing cost" (§6 of the
brief): `len(hits) == of` is exactly what "unchanged" means, and the gate is
guarded on its negation. That is what makes it a different proposal from the
blanket refusal #72 rejected at a ~14% pause rate on unchanged pages.

### 2.8 Prevalence, measured

`tools/audit_atoms_safety.py --sites 70`, 29 frozen sites contributing.
**Coverage is the first finding, and it is §2.6's gap as a number:**

| over ordinal-bearing descriptors | n | share |
|---|---|---|
| ordinal-bearing (the population that makes a positional claim) | 5,804 | — |
| carrying the **shipped** `recordAtoms` | 759 | **13.1%** |
| carrying the self+anchor witness | 2,497 | 43.0% |
| carrying **neither** | 3,198 | **55.1%** |

#83 published 43.9% for the record-text witness. The field that shipped reaches
**13.1%** — a 3.3× gap, and it is not a regression, it is two different
definitions of a record (§2.6). The residue agrees closely with #83's 52.6%,
which is the part both definitions share.

#### A pure deletion is SAFE, and that is structural rather than lucky

| arm | n | resolver | CORRECT | REFUSED | **WRONG** |
|---|---|---|---|---|---|
| base (fresh reload, nothing mutated) | 759 | shipped | 99.3% | 0.7% | **0.0%** |
| | | gated | 98.0% | 2.0% | **0.0%** |
| drop-target (the victim's record removed) | 77 | shipped | 0.0% | **100.0%** | **0.0%** |
| | | gated | 0.0% | 100.0% | **0.0%** |
| drop-other (a different record removed) | 252 | shipped | 88.1% | 11.9% | **0.0%** |
| | | gated | 84.9% | 15.1% | **0.0%** |

**`drop-target` is 0 of 77, and the reason is worth more than the number.**
`atoms_map` records only the atoms **no other member of the recorded crowd
carries**. Delete one record and the survivors are the same rows with the same
text, so by construction not one of them can carry a recorded atom — the
resolver finds zero carriers and refuses. A single deletion cannot produce this
hazard.

**Corroborated independently.** `tools/audit_flow_resolve.py --sites 40`, which
HAS a `delete-target` arm and whose published numbers predate #83, re-run here
for the first time since atoms shipped: `delete-target` **0% CORRECT / 100%
REFUSED / 0% WRONG**. Two harnesses, two mutation models, same answer.

#### So the corpus cannot price this, and saying so is the result

The hazard needs **two** things — the recorded record gone AND a record that
now carries one of its atoms. The second is a change in the DATA: a new invoice
for the same customer, a status flipping to the one that was recorded. A frozen
HAR is one page state and has no way to express a second one, so the prevalence
of the dangerous case is **not measurable on this corpus**. That is #25 in its
usual direction: an ablation measures the code against the sample, and the
sample has no "a week later".

What the corpus DOES settle is that the fix is cheap and that the safe cases
stay safe: `drop-other` — the arm #83 built atoms FOR — keeps 84.9% against
88.1%, and `base` keeps 98.0% against 99.3%.

**A retraction, before it is quoted.** An earlier run of this probe reported
`drop-target` at **2.8% WRONG, 9 mis-binds on coinmarketcap and guardian**, and
it is withdrawn. That run chose a victim PER TARGET, so several records of one
crowd were removed at once and the arm quietly contained its own control (§7's
probe comment). Both affected sites are among the 18 replays `CLAUDE.md` #16
names as non-deterministic, so drift is at least as good an explanation. The
clean arm is the one above.

#### What the gate costs, exactly

| | shipped | gated | delta |
|---|---|---|---|
| refusals on a fresh reload (`base`) | 0.7% | 2.0% | **+1.3pp** |
| refusals when a different record was removed | 11.9% | 15.1% | **+3.2pp** |
| refusals on a genuinely unchanged crowd | — | — | **0 by construction** |

The last row is not a measurement, it is the guard: `gated` is
`want is not None and len(hits) != want`, and `len(hits) == of` is what
"unchanged" means. The +1.3pp on `base` is not a contradiction — replaying a
live-captured HAR is not byte-identical, so a crowd really does change size on
a reload, and there the gate correctly asks for more evidence before binding.

That is the answer to the brief's third question. #72 rejected refusing the
unwitnessed because it would pause **~14%** of all descriptors on an UNCHANGED
page, which is losing the feature rather than buying safety. Re-derived here on
a different sample and it agrees: 55.1% unwitnessed × #72's 23.0%
ordinal-bearing ≈ **12.7%** of all descriptors. This gate is a different
proposal precisely because its cost on an unchanged page is zero.

---

## 3. Mode 2 — cross-origin frames entered the flow pool this morning

### 3.1 What changed

`97efc75` (2026-11-18, #94) added to the op router:

```js
if (params?.structured && Array.isArray(result)) {
  try {
    const _fx = await collectCrossFrames(t.id, !!params?.geometry);
    if (_fx.entries.length
        && (!params?.scopeMmid
            || result.some((e) => e && e.crossFrame))) {
      result = result.concat(_fx.entries);
    }
  } catch (e) {}
}
```

`_flow_entries` calls `get_interactive_elements` with `structured=True`,
`detail="brief"` and **no `scopeMmid`**, so `!params?.scopeMmid` is true and the
concat always happens. Cross-frame entries are now in the pool the recorder
describes from and the runner resolves against.

**This is established by reading the router and by driving the real
`Recorder`** (§3.2), not by a live frame capture — see §6.

### 3.2 Three documented things became false, silently

Driving the real `Recorder` with a pool that does and does not carry a
cross-frame entry:

| pool | steps kept | note |
|---|---|---|
| pre-`97efc75` (no frame entries) | **none** | `ref_f12:3 is not in the current listing` + the CROSS-ORIGIN IFRAME explanation |
| post-`97efc75` (frame entries present) | **`computer`**, descriptor at level 1 | **none at all** |

- `FLOWS-FAILURE-SURFACE` **8.3** says `BOUNDED` — "the step is dropped, it now
  says WHY". It is no longer dropped.
- `FLOWS-CONCEPTUAL-BREAKS` **M2** says the structured array "is built before
  that pass and never carries them". It carries them.
- **`FD22` models a condition that no longer arises.** Its `FakeBridge` returns
  `[E(2,"button")]` with no frame entry, which is not what `_flow_entries`
  returns any more.

  **I first wrote that it is "vacuous — it would pass if the drop were
  deleted", and that is wrong.** Tested rather than asserted, by ablating the
  clause in a `git archive HEAD` tree: `FD22` **FAILS**, 301/302. It guards its
  code perfectly well. What is stale is the SCENARIO, not the check — in
  production the ref is now in the pool, the step is kept, and the branch
  `FD22` protects is unreachable. The behaviour `FLOWS-FAILURE-SURFACE` 8.3
  documents cannot happen, and nothing in the suite would notice, which is a
  different and quieter failure than a vacuous fixture. Recorded because
  PRINCIPLES 18 is about claims a reader will stop checking, and this one was
  mine.

Recording the step is arguably an IMPROVEMENT — it closes M2's gap for free.
The problem is what the descriptor can say about it.

### 3.3 The new silent bind

The descriptor carries no frame identity at all (`grep frame core/flows/*.py`:
one pattern in `recorder.py`, nothing in `descriptor.py` or `runner.py`). And
the rung that would otherwise separate two frames cannot: `section` is computed
**inside each frame**, by that frame's own collector run, and
`collectCrossFrames` then pushes `section: e.section || 'iframe'`. So two
frames serving the same widget produce the *same* section whatever it is — the
rung that takes a descriptor from 59.5% to 84.7% unique does no work across a
frame boundary by construction, not by coincidence.

A page embedding the same widget twice (a saved-card and a new-card payment
frame; one CMP mounting in two frames):

```
descriptor: tag=button name='Pay now' section='iframe' under='' near=''
ordinal   : nth=0 of=2     witness: None     atoms: None

A same frame order                       -> BOUND f12:3
B frames enumerated in the other order   -> BOUND f17:3     <-- wrong frame
C one frame failed to inject             -> REFUSED
```

**The ordinal's declared basis is document order**, and `descriptor.py` says so
("Document order is the ordinal's basis and the collector emits in composed
walk order"). Across frames there is no document. The order is whatever
`chrome.webNavigation.getAllFrames` returned, concatenated after the top
document — and nothing in the platform declares that to be stable. I have
**not** measured it as unstable, and will not claim it: the argument for
refusing is structural, not empirical. *The ordinal rests on a basis that does
not exist here.*

### 3.4 What is closable, and what is not

**Closable exactly, today:** a crowd whose members do not all live in the same
frame has no declared order, so the ordinal means nothing and the step should
refuse rather than guess (PRINCIPLES 7). The frame is declared by the mmid's own
`f<frameId>:` form, which the extension already emits and `recorder.py` already
parses (`_CROSS_FRAME_REF`). Diff in §7.2. Cost on the frozen corpus is **zero**
— #78 measured 0 of 128 frames cross-origin there — and on a real page it costs
a pause exactly where the alternative is a coin flip between two payment frames.

**`MEASURE FIRST`:** carrying the frame's declared origin+path as a rung
(`FLOW-UNBREAKABLE` P7) would let two frames with different `src` resolve
instead of pausing. `collectCrossFrames` already computes `host` for the text
block, so the data is in hand. It cannot be priced on this corpus, and the
probe that would settle it needs the `/lab/frames` fixture extended to serve
the SAME widget from two origins.

---

## 4. Modes 3 and 4 — the unwitnessable residue

### 4.1 How big it is, on the fields that actually ship

From `audit_atoms_safety.py` (§2.8), over 5,804 ordinal-bearing descriptors on
29 frozen sites: **55.1% carry neither witness**. #83 measured 52.6% on its own
definitions and #72 59.4% on a 24-site sample; three samples, one answer, and
the figure moves with the sample rather than with the code.

### 4.2 And it is silently wrong, not merely unprotected

`audit_flow_resolve.py --sites 40`, re-run post-#83, split on whether anything
witnesses the ordinal:

| arm | population | n | CORRECT | REFUSED | **WRONG** |
|---|---|---|---|---|---|
| `resort` (each record moves with its contents — the live case) | witnessed | 275 | 93.1% | 6.2% | **0.7%** |
| | **UNWITNESSED** | 428 | 13.8% | **0.0%** | **86.2%** |
| `reorder` (the crowd permuted inside a fixed scaffold) | witnessed | 316 | 44.9% | 4.7% | **50.3%** |
| | **UNWITNESSED** | 436 | 13.5% | **0.0%** | **86.5%** |

**0.0% refusals on both unwitnessed rows** is the whole problem: these do not
cost a turn, they return an answer. And the witnessed `reorder` row at 50.3%
independently reproduces `FLOWS-FAILURE-SURFACE` 3.3a — the self+anchor witness
is sound on `resort` and is not on `reorder`, and 3.2's closure quoted only the
first.

### 4.3 Is there ANY declaration for the virtualised case?

**Yes, ARIA declares exactly this — and #83 rejected it for the wrong failure
mode.** The dismissal on record is that `aria-posinset`/`aria-rowindex` are
"positional, so they travel with the sort". That is true, and **a re-sort is
not the failure here.** Virtualisation and re-sorting break an ordinal for
opposite reasons, and the same declaration that is useless against one is exact
against the other:

| | what breaks the ordinal | what ARIA declares |
|---|---|---|
| re-sort | the ORDER changed, the set did not | nothing — `posinset` moves with the row |
| **virtualised window** | the SET being counted is a window onto a larger one | `aria-setsize` / `aria-rowcount` = the **dataset** size; `aria-posinset` / `aria-rowindex` = the member's **dataset** position |

Two consequences, both exact and both threshold-free:

1. **A crowd whose members declare `aria-setsize` larger than the crowd is a
   WINDOW, stated by the page.** That is precisely the fact `len(hits) != of`
   cannot supply — #90 M1's whole point is that a window's size does not change
   when it scrolls, so composition looks identical. Where the page declares it,
   "this ordinal is a screen position" stops being an inference.
2. **Where `aria-posinset` is declared, storing it INSTEAD OF `nth` is a strict
   improvement.** It is exactly as vulnerable to a re-sort as `nth` (both are
   positions) and strictly better under scrolling, because it names a position
   in the dataset rather than in the viewport. Same claim, better anchored, no
   new failure mode.

#### And this project ALREADY READS that declaration, in two places, neither of them this one

This is the part that changes the ranking. The rule, the code and the
justification for (1) exist already — twice, in the same file, a few thousand
lines from each other:

| where | what it does | since |
|---|---|---|
| `_collectInteractivePage` → `virtualNote` | `_allComposed('[aria-rowcount]')`, compares the declared total against rendered `[role=row], tr`, and prints *"declares N total rows but only M are rendered in the DOM"* | the listing's own note |
| `_queryElementsPage` → `declared` / `declaredVia` | reads `aria-setsize` off the first match, then walks up to 8 levels for `aria-rowcount`, and leads the result with the discrepancy | #35, Q8/Q8b |

`query_elements`' comment says it in as many words: *"on a virtualized or
paginated grid a count of RENDERED rows is not a smaller answer — it is a WRONG
one"*, and *"ARIA declares exactly this and nothing else is read"*. That is
precisely the sentence mode 3 needs, written for a tool whose wrong answer
costs a re-read — while the descriptor, whose wrong answer deletes a different
invoice, asks nothing.

**So this is PRINCIPLES/#18's asymmetry again**, in its usual shape: two passes
with the same question, one of them answering it. The fix needs no new
detection and no new vocabulary — it needs the fact propagated to the one place
whose failure is irreversible.

#### MEASURED, and the answer is "yes in principle, effectively no in practice"

`tools/audit_window_declarations.py` (93 of 106 sites loaded, three
independent runs, drift floor **0%** on every counter below; `--fire`
plants a positive for every detector and a plain `<ul>` of identical
buttons as the negative control that must report 0 windowed):

| over 2,531 FULL-descriptor tied crowds | n |
|---|---|
| carrying ANY of the four attributes (narrow: self or nearest `[role=row\|option\|listitem]`) | 81 |
| …`aria-rowindex` | 80 |
| …`aria-setsize` | 1 (27 if any ancestor within 12 hops counts) |
| …**`aria-rowcount`** — the only one that states how big a GRID is | **0** |
| **declared total ≠ rendered peers — the window signal** | **1** |

**One crowd, on one site of 93**: `archive_org`, an `<article>` set declaring
`aria-setsize=100` against 55 rendered. `aria-rowcount` does not appear on a
single tied crowd anywhere in the corpus.

So the mechanism is sound, already implemented twice, and **fires on 0.04% of
the population**. On this evidence it is **DON'T BUILD**, for the same reason
and at the same order of magnitude as `OPEN.md` item 2's scroll-container
candidate (5.9% of the unwitnessed, 6 of 96 sites — independently re-run during
this census at 6.0%, same 8 crowds, so that number reproduces).

**Two things keep it from being closed as dead.** `aria-rowindex` IS present —
80 crowds on 2 sites — and the corpus never EXERCISES it: `syncfusion_grid`
carries 1…40 on 40 rendered rows, contiguous and identical to document order,
and `mui_datepicker` has 15 nodes with 5 distinct values. Nothing here
virtualises enough for the attribute to diverge from position, so the data
cannot say whether it would track the dataset under real virtualisation — only
that it is the right attribute if it does. And #25 applies in full: this corpus
is component demos and landing pages, `aria-rowcount` is what AG Grid,
react-window and TanStack emit, and **`aggrid` is one of the 13 sites that did
not render.** A corpus of the internal admin tools this feature actually runs
against could move it materially, and that is the same corpus `OPEN.md` item 2
already asks for. **Measure once, for both.**

**The census corrected its own 27× overstatement before reporting it**, which
is the reason to trust the 1. Its first run reported 27 window discrepancies
led by "mastodon declared=20 rendered=277" — a signal pointing the wrong way,
caused by counting every role-less element under a feed whose members are
`<article>` with no explicit role. Re-derived by counting `[aria-posinset]`
under the owner (ARIA's own definition of a set): **27 → 1**. An error in
exactly the direction that would have justified building something.

### 4.4 What the residue actually IS — classified, not quoted as a percentage

The brief asked for this rather than the number, and the number turns out to be
the least interesting part. Same probe, 2,522 unwitnessed ordinal-bearing
descriptors (49.8% of 5,062 sampled — #83's 52.6%, mine 55.1%, all three moving
with the sample as #83 says):

| bucket | n | share | diverges | call |
|---|---|---|---|---|
| `no-record` (no `tr,li,dl,article,figure,fieldset` ancestor) | **1,445** | 57.3% | 45.5% | **MIXED — and the largest actionable finding** |
| `shared-record` (all members in ONE record) | 677 | 26.8% | 19.5% | mostly **HARMLESS** |
| `record-identical` (records render the same text) | 203 | 8.0% | 65.5% | MIXED → **DANGEROUS** |
| `record-distinct` | 109 | 4.3% | 100% | **DANGEROUS** — already rescued by atoms |
| `tablist` | 63 | 2.5% | 65.1% | DANGEROUS but **reversible** |
| `record-digits` | 25 | 1.0% | 100% | **DANGEROUS** — already rescued by atoms |

Only `no-record`'s pooled share survives a per-site check (median 57.1% over 57
sites); every other bucket has a per-site median of **0.0%** and sits on 3–27
sites, so those shares are not population rates (#25).

#### Dangerous or interchangeable, decided from the data rather than asserted

Two signals, both decidable: does anything the page DECLARES differ across the
crowd (href, form `name`, live `value`, record text, any attribute distinct on
every member), and is there a wrong member at all — `nested` (one member
contains another, so a click bubbles to the same action, #29's collapse rule)
or `same box` (identical x/y/w/h *in this observation*, which is not a
stability claim, so geometry's drift is not in play).

| | n | share |
|---|---|---|
| **DANGEROUS** — something diverges | **1,098** | **43.5%** |
| **PROVABLY INTERCHANGEABLE** — nested/same-box and nothing diverges | **930** | **36.9%** |
| **UNKNOWN** — nothing diverges, not interchangeable | 494 | 19.6% |

**So more than a third of the residue is not a hazard at all** — it is wrapper
and child rows of one control, where binding "wrongly" performs the same
action. `shared-record` is 79.2% interchangeable; `record-distinct` is 1.8% and
`record-digits` 0%, and those two are exactly the buckets atoms already cover.
The signals agree with each other, which is what makes the split worth having.

**43.5% is an UPPER bound**, stated by the census: 408 members both diverge and
are nested, where bubbling makes them the same action anyway. And "nothing the
page declares separates them" is **not** "they are interchangeable" — two tied
controls can carry different handlers with no declared difference, and no
declaration-based measurement can see that. The 19.6% UNKNOWN is the honest
residue of the honest residue.

#### The one finding here that is actionable, and it is §2.6's gap priced

**1,146 of the 1,445 `no-record` crowds DO have the LCA-structural record #83
measured, and 248 of those carry text unique to the member.** They are
unwitnessed only because the shipped `recordAtoms` keys on a declared TAG LIST
(`closest('tr,li,dl,article,figure,fieldset')`) where the probe that justified
it derived the record structurally.

That is **~10% of the whole residue, witnessable today, lost to a definition
mismatch** — and it is the same gap §2.6 found from the other end, now with a
number. It also explains the coverage split: 13.1%/18.5% shipped against #83's
43.9%. Changing it is not free (a structural record has no declared boundary,
which is why the tag list was chosen), but it is the largest single lever left
in this residue and nobody has priced the trade.

#### What is left is not closable from declarations

Strip those out and what remains is crowds **identical in every declared field
and in their surroundings**. The census asked the exhaustive version of the
question — is there ANY attribute distinct on every member? — and the answer is
**no for 1,910 of 2,522 (75.7%)**; 510 (20.2%) have one, led by `src` (188) and
`id` (174). **The `id` count must not be read as 174 usable keys**: #83
measured Angular Material mis-binding 4 of 120 on `mat-select-value-3`, a
per-load counter that is unique, looks declared, and survives a two-load
stability check.

Every other candidate has been measured and refused: geometry (87.3% coverage,
drifts 110px–1,097px, so the safeguard fires on every reflow — #72),
`id`/`data-testid` (6.8%/2.5%, #61), attribute atoms (#83), a neighbour window
(worse than the record on every arm — #83), a declared scroll container (5.9%,
re-derived at 6.0% here), and now ARIA set declarations (§4.3, **0.04%**).

That is the measured price of PRINCIPLES 1 applied to a locator — the same
answer #79 gives for the nine Mind2Web misses and `OPEN.md` 4f for the three
month titles. **Refusing them is not available either**: #72 priced a blanket
refusal at ~14% of all descriptors pausing on an UNCHANGED page, re-derived at
~12.7% in §2.8. What ships for them is the recorder's `positional:` warning and
the runner repeating it on a pass.

**One composition caveat on all of the above**: 926 of 2,522 (36.7%) of the
residue is UNNAMED and 215 are `role=media`, because `_targetable` admits media
rows. Part of what is being counted as a dangerous crowd is a run of images.

---

## 5. Mode 6 — `FRAME_CAP` is a constant-size window

`collectCrossFrames` caps each frame at 40 entries and **selects them by a
priority sort, not document order**:

```js
const FRAME_CAP = 40;
const ordered = raw.length > FRAME_CAP
  ? raw.slice().sort((a, b) => _pri(a) - _pri(b)).slice(0, FRAME_CAP) : raw;
```

Those entries now reach `_flow_entries` (§3.1). A crowd inside a frame holding
more than 40 controls therefore has the same structural property as a
virtualised list — the window's size is constant, so `len(hits) != of` cannot
fire — with the extra hazard that membership is decided by a priority function
rather than by position.

**Not built, and the reason is reach rather than principle.** It needs a
cross-origin frame with >40 controls holding a tied crowd. The frozen corpus
has no cross-origin frames at all, so this cannot be priced here; §7.2's
refusal covers it as a side effect, because such a crowd is a cross-frame
crowd. Recorded so it is not re-derived.

---

## 6. What this pass could not model

- **The frozen corpus is component demos and landing pages.** #83 already says
  there is no admin table, invoice list or order grid in it — and those are
  exactly where a tied crowd of Delete buttons lives. The §2.7 numbers measure
  the code against that sample and cannot measure the sample (R2).
- **Cross-origin frames do not occur in it** (#78: 0 of 128), so every number
  in §3 is a reproduction of the resolution logic against a hand-built pool of
  the shape `collectCrossFrames` emits, not a live measurement. It is labelled
  as such everywhere it appears.
- **Frame enumeration stability is unmeasured.** §3.3 argues from the absence
  of a declared order, not from observed instability.
- **No live pass.** Everything here is offline: pure-Python reproductions plus
  frozen-HAR replay. PRINCIPLES 12 is explicit that a live pass is required
  before committing, and §7's diffs have not had one.
- **The census behind §4.3/§4.4 loaded 93 of 106 sites**, and the 13 that did
  not render are **unmeasured, not passed** — `aggrid` among them, which is a
  data grid and so is exactly the population §4.3 is about. One page load per
  site, no interaction, 1280x1600: a dropdown or dialog opened would change
  both populations.
- **`aria-rowindex` is present in the corpus and never EXERCISED** (contiguous
  1…N matching the rendered rows), so nothing here says whether it tracks the
  dataset under real virtualisation — only that it is the right attribute if it
  does.
- **"Nothing declared separates them" is not "they are interchangeable."** Two
  tied controls can carry different handlers with no declared difference, and
  no declaration-based measurement can see that. §4.4's 36.9% rests on
  containment and geometry; the 19.6% UNKNOWN is where that runs out.

- **The oracle problem is untouched** (`FLOWS-FAILURE-SURFACE` 1.7). This pass
  is about binding to the wrong ELEMENT, not about recording the wrong TRUTH.

**Provenance, because the tree moved under the run.** Another agent committed
`b9feaf7` while the corpus pass was in flight, and it touches
`extension/background.js` — which is where this probe extracts the collector
from. #73 hit the same thing and recorded the rule. Checked rather than
assumed: `_collectInteractivePage` is **byte-identical** across `8a05113` and
`b9feaf7` (463,596 chars either side) and so is the `recordAtoms` block, so
every number here describes the collector the repo now has. That commit also
swept this paper and `tools/audit_atoms_safety.py` into itself in an
intermediate state; the working tree is the finished one.

---

## 7. The diffs

Both land in `core/flows/descriptor.py` and nowhere else. Verified against
`git archive HEAD`: the patch applies cleanly, and with it applied
`python tools/test_flows.py` is **302/302** — neither fix breaks an existing
check, including `FD8`, `FA10`–`FA10g`, `FD20*` and `FR20*`, which are the
guards the ordinal and both witnesses already had.

### 7.1 + 7.2 — the patch

`7.1` is the composition gate on the atoms branch (§2). `7.2` is the
cross-frame refusal and the `frame_of` helper (§3), which also deletes
`recorder.py`'s private second copy of the same pattern — the import in 7.3
replaces it.

```diff
--- a/core/flows/descriptor.py	2026-11-17 23:01:13
+++ b/core/flows/descriptor.py	2026-11-18 21:59:21
@@ -41,7 +41,22 @@
 """
 from __future__ import annotations
 
+import re
 from typing import Any, Iterable, Optional
+
+# WHICH DOCUMENT AN ENTRY LIVES IN, as the extension declares it.
+# `collectCrossFrames` prefixes a cross-origin frame's mmid `f<frameId>:` and
+# `resolveFrameSelector` routes on that spelling, so it is a declaration rather
+# than a guess. Defined HERE, in the leaf module, because `recorder.py` already
+# carries a private second copy of this pattern and two spellings of one
+# concept is what rule 17 exists to stop -- that import replaces it.
+CROSS_FRAME_REF = re.compile(r"^f(\d+):")
+
+
+def frame_of(entry: dict) -> str:
+    """The frame id an entry belongs to; '' for the top document."""
+    m = CROSS_FRAME_REF.match(str(entry.get("mmid") or ""))
+    return m.group(1) if m else ""
 
 # Cumulative strengths. A recorded step stores the CHEAPEST one that resolves,
 # not the strongest: every field added is another thing that can change
@@ -576,15 +591,62 @@
     if atoms:
         want_a = set(atoms)
         cand = [e for e in hits if want_a & set(e.get("recordAtoms") or [])]
+        # THE COMPOSITION GATE, and it is the ONE place this branch reads `of`.
+        #
+        # Everything above was written on the premise that a content witness
+        # makes no positional claim, so neither a re-sort nor a row being added
+        # or removed touches it. That is true of a re-sort and of a DIFFERENT
+        # record being deleted -- which are the two arms it was measured on --
+        # and FALSE when the target's own record is gone, because the resolver
+        # then has to tell "my row lost a cell" from "my row is gone and a
+        # stranger shares a word". It binds on INTERSECTION, so one shared
+        # token decides it. MEASURED: a step recording
+        # ['Acme Ltd', 'INV-1001', 'Paid'] binds to an unrelated customer's
+        # invoice because that row also renders `Paid`, and when the survivor
+        # happens to land at the recorded index it emits no note either, so the
+        # flow reports PASSED having deleted the wrong record. Worse, the
+        # ordinal path REFUSED that case before atoms existed
+        # (`len(hits) != of`), so this was a regression introduced by the fix
+        # for the previous silent mis-bind. tools/audit_atoms_safety.py.
+        #
+        # THE RULE IS EXACT AND THERE IS NO THRESHOLD IN IT. Composition
+        # unchanged -> a SUBSET still identifies the member, which is the
+        # tolerance the intersection rule exists for (a status flipping, a
+        # total recalculated). Composition CHANGED -> the record must be wholly
+        # present, because a missing record and an edited cell are otherwise
+        # the same evidence and the page declares nothing that separates them.
+        # "All of them" and "the same number as before" are facts, not chosen
+        # numbers.
+        #
+        # THE TOLERANT VARIANT IS REJECTED, and it is the one that looks
+        # better: requiring only the atoms still present ANYWHERE in the crowd
+        # would survive a simultaneous edit, and it re-admits the defect --
+        # with the target's record gone the only surviving recorded atom IS
+        # `Paid`, so "all present atoms" is `{Paid}` and the stranger carries
+        # all of it.
+        gated = want is not None and len(hits) != want
+        if gated:
+            cand = [e for e in cand
+                    if want_a <= set(e.get("recordAtoms") or [])]
         if len(cand) != 1:
             raise Unresolved(
-                f"{len(hits)} element(s) match {_describe(desc)}, and {len(cand)} of "
-                f"them carry the text that identified this one when the flow was "
-                f"recorded ({', '.join(repr(x) for x in atoms[:3])}"
-                f"{', …' if len(atoms) > 3 else ''}). Exactly one must. Its record "
-                f"was removed, its text changed, or another record now carries the "
-                f"same text — and the recorded position is not evidence of which "
-                f"element was meant in any of those cases",
+                (f"{len(hits)} element(s) match {_describe(desc)} but {want} did when "
+                 f"this flow was recorded, so the crowd CHANGED — and {len(cand)} of "
+                 f"them still carry the whole of the text that identified this one "
+                 f"({', '.join(repr(x) for x in atoms[:3])}"
+                 f"{', …' if len(atoms) > 3 else ''}). Exactly one must. When a row "
+                 f"has been added or removed, a record that carries only PART of that "
+                 f"text is as consistent with a different record sharing a word as it "
+                 f"is with this one having changed a cell, and the recorded position "
+                 f"is not evidence either"
+                 if gated else
+                 f"{len(hits)} element(s) match {_describe(desc)}, and {len(cand)} of "
+                 f"them carry the text that identified this one when the flow was "
+                 f"recorded ({', '.join(repr(x) for x in atoms[:3])}"
+                 f"{', …' if len(atoms) > 3 else ''}). Exactly one must. Its record "
+                 f"was removed, its text changed, or another record now carries the "
+                 f"same text — and the recorded position is not evidence of which "
+                 f"element was meant in any of those cases"),
                 _candidates(hits))
         if nth is not None and 0 <= nth < len(hits) \
                 and str(cand[0].get("mmid")) != str(hits[nth].get("mmid")):
@@ -598,6 +660,45 @@
                               "mmid": str(cand[0].get("mmid"))})
         return str(cand[0].get("mmid"))
 
+    # AN ORDINAL ACROSS FRAMES HAS NO BASIS. The ordinal's declared basis is
+    # DOCUMENT ORDER -- "the collector emits in composed walk order", a few
+    # lines up. A crowd spanning frames has no single document: cross-frame
+    # entries are CONCATENATED after the top document's, in whatever order
+    # `chrome.webNavigation.getAllFrames` returned the frames, and nothing in
+    # the platform declares that to be stable.
+    #
+    # This became reachable on 2026-11-18 (97efc75, #94): the structured array
+    # the recorder describes from now carries cross-frame entries, where before
+    # it did not and the step was dropped at compile. `collectCrossFrames`
+    # forces `section: e.section || 'iframe'`, so every cross-frame control on
+    # a page collapses into ONE landmark bucket -- and `section` is the rung
+    # that takes a descriptor from 59.5% to 84.7% unique. A page embedding the
+    # same widget twice (a saved-card and a new-card payment frame; one CMP
+    # mounting in two frames) therefore produces a crowd of identical
+    # descriptors whose only discriminator is the enumeration order, and
+    # swapping it binds the other frame and reports success.
+    #
+    # REFUSE RATHER THAN GUESS (#24, #49): the frame is declared by the mmid's
+    # own form, so this needs no new field and no threshold. The cost on the
+    # frozen corpus is ZERO -- #78 measured 0 of 128 frames cross-origin there
+    # -- and on a real page it is a pause exactly where the alternative is a
+    # coin flip between two payment frames.
+    #
+    # NOT applied to the atoms branch above, deliberately: a content witness
+    # names the member by text its own record carries, which is as true inside
+    # a frame as outside it. This guards the paths that rest on ORDER, and the
+    # self+anchor witness is inside it because `witness_map` builds its window
+    # by walking `entries` in that same concatenated order.
+    if want is not None and nth is not None \
+            and len({frame_of(e) for e in hits}) > 1:
+        raise Unresolved(
+            f"the {len(hits)} element(s) matching {_describe(desc)} are spread across "
+            f"several frames, so there is no document order to count position "
+            f"{nth} in — cross-origin frames are listed after the top document in "
+            f"whatever order the browser enumerated them, which is not something "
+            f"the page declares. Name the one you mean",
+            _candidates(hits))
+
     if want is not None and nth is not None:
         if len(hits) != want:
             raise Unresolved(
```

### 7.3 — one concept, one spelling

`recorder.py` carries its own `_CROSS_FRAME_REF = re.compile(r"^f\d+:")`.
With 7.2 applied that is a second spelling of a concept the leaf module now
owns (rule 17), so:

```diff
--- a/core/flows/recorder.py
+++ b/core/flows/recorder.py
-from .descriptor import build, unwitnessed_ordinal
+from .descriptor import CROSS_FRAME_REF, build, unwitnessed_ordinal
@@
-_CROSS_FRAME_REF = re.compile(r"^f\d+:")
+_CROSS_FRAME_REF = CROSS_FRAME_REF      # see descriptor.CROSS_FRAME_REF
```

**Do this one only with §3's open question settled.** `recorder.py` uses that
pattern to explain why a cross-frame ref was dropped at compile — and since
`97efc75` it is no longer dropped, so the branch it guards is dead code and
`FD22` passes vacuously over it (§3.2). The right change is to decide what the
recorder should now DO with a cross-frame step, not to tidy the pattern under
a branch that cannot fire.

### 7.4 — the checks, ablated

These go in `tools/test_flows.py` beside the existing `FA10*` block (which
already has the `_res`, `_row` and `E(atoms=…)` helpers they use). Run against
`git archive HEAD` they give **4/7**; with 7.1+7.2 applied, **7/7**:

| check | HEAD | patched | what it is |
|---|---|---|---|
| `FA10h` a gone record does not bind to a stranger sharing one word, once the crowd changed size | **binds `30`** | REFUSED | finding |
| `FA10i` …including when the stranger lands at the RECORDED index, where `moved` does not fire | **binds `30`** | REFUSED | finding |
| `FA10j` CONTROL: a DIFFERENT record removed still resolves | `10` | `10` | control |
| `FA10k` CONTROL: a cell changing on an UNCHANGED crowd still resolves | `10` | `10` | control |
| `FD26` an ordinal counted across FRAMES refuses | **binds `f12:3`** | REFUSED | finding |
| `FD26b` CONTROL: a crowd INSIDE one frame still uses its ordinal | `f12:3` | `f12:3` | control |
| `FD26c` CONTROL: a top-document crowd is untouched | `3` | `3` | control |

`FA10j` and `FA10k` are the two that matter most: without them "refuse whenever
the crowd changed size" and "refuse whenever an atom is missing" would both
satisfy `FA10h`/`FA10i` while deleting the tolerance #83 built the intersection
rule for. `FD26b` is the same guard for the frame rule — it is not "refuse
anything carrying an `f<n>:` ref".

Bodies, written against the `E()`, `_res()` and `check()` helpers already in
`tools/test_flows.py` — `_row` there takes `(n, num, firm)`, so these use a
local variant carrying a status cell, which is the field that makes the
collision realistic:

```python
    # ---- FA10h/FA10i: THE RECORD IS GONE AND A STRANGER SHARES A WORD ------
    # The atoms branch is the only binding path that ignores crowd COMPOSITION.
    # That is safe for a re-sort (what it was built for) and unsafe when the
    # target's own record is gone: it binds on INTERSECTION, so one shared
    # token decides it, and the ordinal path REFUSED the same case before atoms
    # existed. docs/research/FLOW-SILENT-BIND-2026-11.md §2.
    def _inv(n, num, firm, status="Open"):
        return [E(n, "button", name="Delete", section="main", under="Invoices",
                  atoms=[f"INV-{num}", firm, status, "Delete"])]

    _iv = _inv(10, 1001, "Acme", "Paid") + _inv(20, 1002, "Globex") \
        + _inv(30, 1003, "Initech")
    _t0 = build(_iv[0], _iv)
    _g0 = _inv(20, 1002, "Globex") + _inv(30, 1099, "Delta", "Paid")
    check("FA10h a record that is GONE does not bind to a stranger sharing one "
          "word of it, once the crowd has CHANGED SIZE",
          _res(_t0, _g0) == "REFUSED", f"-> {_res(_t0, _g0)}")

    _t1 = build(_iv[1], _iv)
    _g1 = _inv(10, 1001, "Acme", "Paid") + _inv(30, 1099, "Delta", "Globex")
    check("FA10i ...including when the stranger lands at the RECORDED index, "
          "where the `moved` note does not fire either",
          _res(_t1, _g1) == "REFUSED", f"-> {_res(_t1, _g1)}")

    # THE TWO CONTROLS. Without them "refuse whenever the crowd changed size"
    # and "refuse whenever an atom is missing" both satisfy the two above while
    # deleting the tolerance #83 built the intersection rule for.
    _c0 = _inv(10, 1001, "Acme", "Paid") + _inv(30, 1003, "Initech")
    check("FA10j CONTROL: a DIFFERENT record removed still resolves — the gate "
          "must not be 'refuse whenever the crowd changed size'",
          _res(_t0, _c0) == "10", f"-> {_res(_t0, _c0)}")
    _c1 = _inv(10, 1001, "Acme", "Overdue") + _inv(20, 1002, "Globex") \
        + _inv(30, 1003, "Initech")
    check("FA10k CONTROL: a cell changing on an UNCHANGED crowd still resolves",
          _res(_t0, _c1) == "10", f"-> {_res(_t0, _c1)}")

    # ---- FD26: AN ORDINAL COUNTED ACROSS FRAMES ---------------------------
    # 97efc75 put cross-frame entries into the structured array. `section` is
    # computed INSIDE each frame, so it cannot separate two of them, and the
    # ordinal's declared basis -- document order -- does not exist across a
    # frame boundary. §3.
    def _F(fid, n, name):
        return E(f"f{fid}:{n}", "button", name=name, section="iframe")

    _two = [_F(12, 3, "Pay now"), _F(17, 3, "Pay now")]
    _tf = build(_two[0], _two)
    check("FD26 an ordinal counted across FRAMES refuses — cross-frame entries "
          "are concatenated in enumeration order, which is not document order",
          _res(_tf, _two) == "REFUSED", f"-> {_res(_tf, _two)}")
    _one = [_F(12, 3, "Pay now"), _F(12, 5, "Pay now")]
    _t1f = build(_one[0], _one)
    check("FD26b CONTROL: a crowd INSIDE one frame still uses its ordinal — "
          "this is not 'refuse anything carrying an f<n>: ref'",
          _res(_t1f, _one) == "f12:3", f"-> {_res(_t1f, _one)}")
    _top = [E("3", "button", name="Pay now"), E("5", "button", name="Pay now")]
    _tt = build(_top[0], _top)
    check("FD26c CONTROL: a top-document crowd is untouched",
          _res(_tt, _top) == "3", f"-> {_res(_tt, _top)}")
```

### 7.5 — NOT proposed as a diff

- **`FD22`'s fixture and `FLOWS-FAILURE-SURFACE` 8.3 / `FLOWS-CONCEPTUAL-BREAKS`
  M2** are stale as of `97efc75` (§3.2). Correcting them is a documentation
  change that should land with whatever §3's open question decides, not before.
- **The frame origin+path rung** (`FLOW-UNBREAKABLE` P7) — `MEASURE FIRST`. The
  data is already in hand in `collectCrossFrames` (`host` is computed for the
  text block), and the corpus cannot price it.
- **Mode 3's window detector** — **DON'T BUILD on this corpus**, §4.3: the
  detection already exists twice and the declaration fires on **1 of 2,531**
  tied crowds, with `aria-rowcount` on zero. The design is recorded there so it
  is not re-derived, and what would reopen it is the admin-tool corpus
  `OPEN.md` item 2 already asks for — not another attribute.
- **Switching `recordAtoms` to the LCA-structural record** — the largest lever
  left in the residue (**~10% of it**, §4.4) and genuinely not free: a
  structural record has no declared boundary, which is why the tag list was
  chosen. `MEASURE FIRST`, and the probe is `audit_record_witness.py` with the
  shipped resolver run against both record definitions in one pass.
- **`audit_record_witness.py`'s record definition** should either adopt the
  shipped `closest('tr,li,dl,article,figure,fieldset')` or the shipped field
  should adopt the probe's structural definition (§2.6). They are 13.1% against
  43.9% apart and one of the two numbers describes nothing that runs.
