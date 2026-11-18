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
an unchanged page, and §7's diff is three lines. The second entry is that
`97efc75` (this morning) put cross-origin frame entries into the structured
array, which silently reversed a documented behaviour, made one fixture vacuous
and created a crowd whose only discriminator is the order Chrome enumerated the
frames in. Everything after those two is already known and ranked here only so
the ordering is honest.

---

## 1. The ranked list

Ranked by (can it bind wrongly and report PASS) × (how reachable) × (how bad
the wrong action is). `SILENT` is the only unacceptable verdict.

| # | mode | verdict | closable from declarations? |
|---|---|---|---|
| **1** | **Atoms bind when the recorded record is GONE** | **SILENT** — reproduced; a regression against pre-#83 | **YES, exactly.** §2, diff §7.1 |
| **2** | **A cross-origin frame crowd, ordered by frame enumeration** | **SILENT** — reproduced; surface opened today by `97efc75` | **Partly.** Refusal is exact (§3); full identity is `MEASURE FIRST` |
| 3 | An unwitnessed ordinal in a **virtualised window** | `SILENT`, known (#90 M1, `OPEN.md` 2) | **NO** — §4, measured |
| 4 | An unwitnessed ordinal under a **re-sort** | `SILENT`, known (#72, `OPEN.md` 2) | **NO** for the residue — §4 |
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
`drop-other`. **None removes the target.** `tools/audit_flow_resolve.py` HAS a
`delete-target` arm (100% REFUSED) and **does not model atoms at all** — `grep
-n atoms tools/audit_flow_resolve.py` returns nothing, so the arm that would
have caught this ran against a resolver path it could not reach.

That is `MEASUREMENT.md` §4 verbatim, one entry after it was written: *a
mutation harness measures the code against the mutations it models, and when a
harness reports a perfect score the next question is what it does not model.*

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
real collector, so §2.7's coverage column is the shipped number.

### 2.7 Prevalence, measured

<!--CORPUS-->

---

## 3. Mode 2 — cross-origin frames entered the flow pool this morning

### 3.1 What changed

`97efc75` (2026-11-18, #94) added to the op router:

```js
if (params?.structured && Array.isArray(result)) {
  const _fx = await collectCrossFrames(t.id, !!params?.geometry);
  … result = result.concat(_fx.entries);
}
```

`_flow_entries` asks for `structured=True`, so cross-frame entries are now in
the pool the recorder describes from and the runner resolves against.

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
- **`FD22` is now vacuous.** Its `FakeBridge` returns `[E(2,"button")]` with no
  frame entry, so it tests a pool shape the collector no longer produces. It
  passes, and would pass if the drop were deleted. This is PRINCIPLES 11 and 18
  in one place: a fixture encoding the world its author thought of, under a
  comment asserting a guarantee the code no longer has.

Recording the step is arguably an IMPROVEMENT — it closes M2's gap for free.
The problem is what the descriptor can say about it.

### 3.3 The new silent bind

`collectCrossFrames` pushes `section: e.section || 'iframe'`, and the
descriptor carries no frame identity at all (`grep -c frame core/flows/*.py`:
one comment in `recorder.py`, nothing in `descriptor.py` or `runner.py`). So
every cross-frame control on a page collapses into one `section` bucket — and
`section` is the rung that takes the descriptor from 59.5% to 84.7% unique.

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

<!--RESIDUE-->

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
- **The oracle problem is untouched** (`FLOWS-FAILURE-SURFACE` 1.7). This pass
  is about binding to the wrong ELEMENT, not about recording the wrong TRUTH.

---

## 7. The diffs

<!--DIFFS-->
