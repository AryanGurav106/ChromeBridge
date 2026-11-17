# The observe-to-act gap: exposure, design, cost (2026-11-17)

`docs/OPEN.md` item 1. Probe: `tools/audit_observe_act_gap.py` (matrix),
`--drift`, `--cost`; helper `tools/audit_observe_act_extra.py`. Nothing under
`extension/`, `core/` or `mcp_server.py` was touched; every change below is a
proposed diff. Raw output: `temp/observe_act_matrix.json`,
`temp/observe_act_drift.json` (gitignored).

## 1. Headline

1. **Most of the hazards the literature worries about are already caught for
   ref clicks**, by `_rectForPage`'s action-time pre-flight (covered / not found
   / not visible all REFUSE) and by ref resolution. Overlays, toasts, modals,
   removed or hidden targets: 0 harmed clicks.
2. **Three hazards reach a ref click and nothing refuses them.** Two change what
   the control MEANS while it stays the same node, and one is undetectable from
   the DOM:
   - H9 label flips in place (`Save` -> `Publish`): HARM.
   - H5b re-sort by reusing nodes (React-unkeyed): HARM, the click deletes
     INV-3 where the read showed INV-1. This is #72's 94.4%-WRONG hazard one
     layer over.
   - H4b same node, handler swapped, no DOM mutation: HARM, **caught by no
     signal at all**. Residual; only an after-the-fact effect check can see it.
   - H7 target becomes disabled: NOOP (wasted turn, not damage; #72's `NO
     EFFECT` already reports it after the fact).
3. **A ResizeObserver is not needed and is rejected.** It catches no harmful
   hazard that a rect compare or the existing pre-flight does not, misses pure
   translation when attached to the target alone (H6), and its cost is not
   resolvable against drift (section 4). The paper's RO result is for its attack
   set; this matrix is the evidence for ours.
4. **The mutation ring is the wrong verdict signal.** Document-wide it fires on
   every innocent ticker (C1) and on every harmful-or-harmless case alike; scoped
   to the element it fires on self-churn (C2). It adds no catch over the
   signature below.
5. **The guard is a signature carried through the model turn in the page, compared
   inside the pre-flight that already runs** - no new bridge op, no observer.

## 2. Exposure matrix (measured, headless Chromium 1243, macOS)

"Ref click" = real `_rectForPage` pre-flight (extracted verbatim) then a real
trusted mouse click at its coordinates. "Coord click" = the click aimed at the
OBSERVED centre, which `computer(coordinate=)` never re-measures. Expected act
is what the read promised. `sig` = tag/role/name/disabled/href/declared-record
hash (fields in the table are the ones that differ).

| hazard | ref click now | coord click | signals that fire |
|---|---|---|---|
| C0 nothing changes (control) | OK | OK | - |
| C1 ticker churn elsewhere (control) | OK | OK | ring(doc) only |
| C2 target's own class/style churn (control) | OK | OK | ring(el) only |
| H1 cookie banner pushes page down 80px | OK | NOOP | ring(doc), rect, RO(anc/body) |
| H2a header grows over target, page not scrollable | refused(covered) | NOOP | occl |
| H2b header grows over target, scroll centres it | OK | NOOP | ring(doc) |
| H3 toast covers button | refused(covered) | NOOP | occl |
| H3b toast, pointer-events:none | OK | OK | ring(doc) |
| H8 modal + backdrop opens | refused(covered) | NOOP | occl |
| H4a node replaced, same tag+name, other action | refused(not found) | HARM | ref |
| **H4b same node, handler swapped** | **HARM** | HARM | **none** |
| H5a re-sort by moving nodes | OK | HARM | rect, ring(doc) |
| **H5b re-sort by reusing nodes** | **HARM** | HARM | ring(rec), **sig:rec** |
| H6 lazy image reflows column (no DOM mutation) | OK | NOOP | rect, RO(anc/body); ring silent |
| H7 target becomes disabled | NOOP | NOOP | ring(el), sig:dis |
| **H9 label flips Save -> Publish** | **HARM** | HARM | ring(el), **sig:name** |
| H11 target removed | refused(not found) | NOOP | ref, occl-path |
| H11b display:none | refused(not visible) | NOOP | rect, occl |

Reading it:
- **Nothing catches (current code):** H4b. Needs no DOM change at all.
- **Only a new signal catches:** H9 (`sig:name`), H5b (`sig:rec`), H7 (`sig:dis`).
- **Coordinate clicks are exposed in 4 more cases** (H4a, H5a, and every layout
  shift as NOOP); `_hitTestPage`'s echo runs after dispatch (background.js ~1907,
  2041), so it reports, it does not guard.
- **RO(t)** fires only on removal/replace/hide; **RO(anc/body)** fires on H1 and
  H6, both harmless for a ref click. RO never fires on the harmful H5b/H9.
- **H1, H6, H5a (rect moved, outcome OK)** are the shapes a rect-based or
  ring-based guard would refuse for nothing. They are the noise controls.

## 3. Design

**Carry a signature, compare endpoints, inside the pre-flight.** At collection
the collector stamps, per kept entry, `__mmidSig` (a WeakMap element -> sig), the
sig being the harness's `__sig`: `tag`, `role`, name (aria-label / innerText /
value / title / alt, whitespace-normalised), `:disabled` or `aria-disabled`,
`href`, and a hash of the text of the nearest **declared record**
(`tr,li,dl,article,figure,fieldset`, the same record notion `_climbTo` uses, #47).
All declarations; no size, class or wordlist (PRINCIPLES 1, 4). At action time
`_rectForPage` already runs in the page; it computes the same sig for the live
element and returns `observed: {field: [was, now], ...}`. Why not observers: the
question is "is what I act on now what I read", an endpoint comparison; history
(A -> B -> A) is irrelevant to the act, which is why observers add nothing here.

One function, two byte-identical copies (`dup:obssig`, injected functions lose
closure - OC7 pattern). Do NOT reuse the collector's entry label for the "observed"
side and a light name for "now": two spellings of one concept (PRINCIPLE 17).

**Proposed diff (not applied).**

```diff
--- a/extension/background.js  (_collectInteractivePage, after the entries are final)
+ // dup:obssig  -- must stay byte-identical with _rectForPage's copy
+ try {
+   const S = (window.__mmidSig = window.__mmidSig || new WeakMap());
+   const reg = window.__mmidReg;
+   for (const e of out) { const n = reg && reg.get(String(e.mmid)); if (n) S.set(n, _obsSig(n)); }
+ } catch (e) {}
--- a/extension/background.js  (_rectForPage, after `const el = q(selector)`)
+ // dup:obssig
+ let observed = null;
+ try {
+   const was = window.__mmidSig && window.__mmidSig.get(el);
+   if (was) { const now = _obsSig(el); const d = {};
+     for (const k of ['tag','role','name','dis','href','rec']) if (was[k] !== now[k]) d[k] = [was[k], now[k]];
+     if (Object.keys(d).length) observed = d; }
+ } catch (e) {}
  ... return { x, y, w, h, visible, blockedBy, dsx, dsy,
+          observed,   // null = matches (or nothing was stamped: UNKNOWN, claims nothing)
 };
--- a/extension/background.js  (clickTrusted / _clickPage / fill_form submit path)
+ if (rect.observed && isDeclaredSubmit) return { ok:false, msg: observedMsg(rect.observed) };  // irreversible
+ else if (rect.observed) note += observedMsg(rect.observed);                                    // ordinary click
```

`observedMsg` states the fact in the project's voice: *"ref_N changed since you
read it: name 'Save' -> 'Publish'. Nothing was clicked."* (refusal) or *"...
Clicked anyway; the page's own declared text for this control differs from what you
read."* (note). Hash fields print as "the record's text changed", never the hash.
No causes asserted (PRINCIPLE 6).

**Which actions gate (refuse) vs note.**
- **Refuse on any identity diff:** `fill_form(submit=True)` / `submit_ref`, and a
  click on a control the DOCUMENT declares as a submit (`type=submit`, or a
  `<button>` with no `type` inside a `<form>` - the same declaration #24's picker
  reads), and `call_page_tool` with `readOnlyHint:false`. This is the break-even
  formula's "irreversible" case (arXiv:2610.39282, ~1.2%), decided from
  declarations, not from the word "Delete" (that would be the wordlist #24 removed).
- **Note only (never refuse):** every other click. Reason, measured: names are
  data (#59 `Records 38` -> `43`; coinmarketcap in section 4 changed names in 2 of
  80 sampled controls over one turn). Refusing every name diff on ordinary clicks
  converts a live counter into a lost turn (~3.6s, #38) for a reversible action.
- **Never gate on:** rect movement (H1/H6/H5a all OK), document mutation counts
  (C1), self class/style churn (C2), or ResizeObserver.

**What it must NOT do (control set; each must be silent in BOTH arms):** C0, C1,
C2, H1, H3b, H5a, H6. A check set that only ever fires proves nothing
(PRINCIPLE 15); these seven are the proof that the guard is not "always refuse".

## 4. Cost, re-earned

All on this machine, headless Chromium, macOS; interleaved with an A/A drift
control where a delta is claimed.

| item | result | note |
|---|---|---|
| Extra bridge round trips | **0** | guard lives inside the `_rectForPage` executeScript that already runs |
| Stamping sigs at read, up to 150 entries | **0.5-1.4 ms** | github, hn, mdn_select, java_api (5,847 entries), nytimes; vs 28-500 ms for the collection itself |
| Compare one element at action | **3-43 us** (200-rep mean) | |
| ResizeObserver, 1k / 5k / 20k observed elements, 20 layout-churn rounds | **+0.9 / +1.6 / +3.8 ms** over 33 / 33 / 100 ms | **drift floor (A/A) 4.9% / 2.5% / 11.2% = 1.6 / 0.8 / 11 ms**, so the delta is **below the floor at every size**: not resolvable. Rejected on catch, not on cost |
| Mutation ring query at saturation (4,009 recorded) | p95 0.1 ms unscoped and scoped, max 0.1 ms | at Chrome's timer granularity; #70 and #76 stand |
| Re-deriving the name with the collector scoped to one ref (rejected alternative) | **15-18 ms** (github, hn), **124 ms** (mdn_select), **146 ms** (nytimes), **510 ms** (java_api) | the walk is whole-document, scoped is barely cheaper (java_api 499 -> 510). 3-4 orders of magnitude over the light sig |
| Model turn it guards | ~3,600 ms (#38, not re-measured) | |

### False-positive rate on settled pages (the number that decides refuse vs note)

36 frozen sites (HAR replay, seed 7), 1,707 viewport entries, sig taken at read
and again after a real 3.6 s wait:

| | count | rate |
|---|---|---|
| ref gone | 3 | 0.18% |
| rect moved | 23 | 1.35% (22 of them one stripe reflow) |
| any identity diff | 5 | **0.29%** (4 name, 1 href; naver, stripe, coinmarketcap x2, gmaps) |
| declared submits with an identity diff | **0 of 10** | |
| record-text diff | 0 | |
| ring fires scoped to the element | 7 | 0.41% |
| sites whose DOCUMENT ring saw anything | 7 of 36 | the doc-wide ring is a quarter-noisy |

Caveats, stated not buried: n=10 declared submits is far too few to bound the
false-refusal rate (rule of three gives ~30% upper bound); HAR-replayed pages
carry no live server data, so counters (#59) are under-represented; the corpus is
the sample (PRINCIPLE 9). The number supports "identity diffs are rare on
settled pages", not "the refusal is free".

## 5. Rejected / investigated, with numbers

- **ResizeObserver:** 0 catches beyond rect/occlusion; RO(t) did not fire on
  translation (H6); cost unresolvable (below drift floor). Reject.
- **Mutation ring as verdict:** doc-wide fires on C1/H3b/H2b (harmless); scoped to
  record is subsumed by `sig:rec` (H5b), and on self-churn fires on C2. Reject as a
  gate, keep as #70's readiness fact.
- **Rect comparison as a gate:** fires on H1, H5a, H6, all OK. Reject.
- **Collector re-derive at action time:** 15-510 ms. Reject.
- **Landmark/section in the sig:** not tested, no hazard needed it. Not built.
- **H4b (handler swap, no DOM change):** undetectable by any signal here. Only
  `_clickEffectPage`'s post-hoc `NO EFFECT` can see consequences. Accepted residual.
- **External check (search summary only, not read in full):** arXiv:2604.18860
  (desktop GUI agents, UCSD) reports a mean observation-to-action gap of 6.51 s on
  OSWorld and proposes pre-execution UI verification (target pixel similarity,
  screenshot diff), noting a blind spot for zero-visual-footprint DOM injection -
  our H4b. arXiv:2607.10487 (commit-time authorization, 2026-07) frames stale
  authority at the commit point, which is the same logic as gating only
  irreversible actions. Neither is a DOM-level check in a shipped framework per the
  search; unverified beyond the summaries.

## 6. Ranked plan

1. **Sig + refuse on declared irreversible actions** (diff above). Closes H5b, H9
   for submit; zero round trips; ~1 ms at read, microseconds at act.
2. **Note on ordinary clicks** when identity differs. Cheap, names the fact, no
   lost turn.
3. **Refresh the baseline on a legitimate in-batch change.** Risk, untested: a
   `fill_form` then `click(submit)` batch must not compare against a pre-fill read
   in a way that flags the agent's own work. Needs a B10c-style control before
   shipping (baseline = batch start, as #38 decided for the fingerprint).
4. **Coordinate clicks:** no sig exists for a bare coordinate. Open; offer only the
   fact "N structural changes since your read" (doc ring is noisy, C1), or steer the
   agent to refs. Low rank.
5. Not planned: RO, ring/rect verdicts, collector re-derive, H4b.

**Checks to add (PRINCIPLE 11), shown against the pre-change code:** OA-H9, OA-H5b,
OA-H7 (submit variants) must FAIL on current code (outcome HARM/NOOP in the matrix)
and pass after; OA-C0, C1, C2, H1, H3b, H5a, H6 must pass in BOTH arms (silent);
H4b is a pinned known-residual, asserting the guard does NOT claim it.
Also needed per #19: an op-router check that `observed` crosses the
`runInTab`/`executeScript` boundary (inline the sig as a closure; C11 enforces).

## 7. Method notes

Fixtures are served from `http://fx.test/` via `page.route` so `listener_tag.js`
(`add_init_script`) actually runs on a real navigation (C14). The harness
asserts `typeof window.__abMut === 'object'` so a silently untagged page cannot
produce a green matrix. Two probe bugs found and fixed before reporting: an
element id `top` shadowed `window.top` (TypeError), and the first record-scoped
ring fell back to `parentElement`, i.e. `<body>`, making every scoped ring fire;
a record is now only a DECLARED record.
