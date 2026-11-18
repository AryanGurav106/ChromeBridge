# Readiness adversarial audit, 2026-11

> **STATUS, 2026-11-18 — read `READINESS-RESIDUE-2026-11.md` before quoting any
> number below.** Both of this file's top-ranked defects have since SHIPPED, so
> the matrix and the totals here describe a build nobody runs any more: Patch A
> (a `ShadowRoot` has no `parentElement`) is in `listener_tag.js`, and the
> cross-origin `blindFrames` clause is in `background.js`. Re-derived on the
> current code, **unscoped FALSE-QUIET is 1 and not 3**, and **scoped-to-main is
> 1 and not 5**. The six steady-state false busies did reproduce, were traced to
> a `textContent =` being filed as *structural*, and five of the six are closed
> by a node-type reclassification — the sixth was never a defect. The probe grew
> three shapes (19, 20, 21) and **refuses to run** if Patch A is ever reverted.
> A retraction at the bottom of a long entry does not retract the heading
> (`#67`), so it is at the top here.

Probe: `tools/audit_readiness_adversarial.py` (`.venv/bin/python tools/audit_readiness_adversarial.py --json out.json`).
Injects the real `_readinessPage` ALONE (no prepended helpers; C11 passes 95/95, test_readiness 44/44),
renders the real `readinessNote` through node with `runInTab`/`_netPending` stubbed from what Playwright
saw on the wire (types mapped to webRequest names). Ground truth is objective: each shape defines a
content signature; "changes later" = signature at this offset differs from signature at t=9.5s.
Verdict classes: QUIET (empty), MINOR, STRONG (STILL CHANGING), DOMSTABLE (DOM STABLE/NETWORK BUSY), UNKNOWN.
The listener_tag.js used is the real file plus ONE inserted method (asserted a pure insertion).
Headless Chromium, tab NOT throttled; the hidden-tab regime (#12) is only approximated by shapes 17/18 (400ms commits).

Error classes: FALSE-QUIET (QUIET/MINOR while content changes later); FB-PERM (STRONG, offset >= 3500, since < 1000ms,
content never changes again: steady-state warn-forever); fb-tail (STRONG, since >= 1000: the 3000ms window still covering
a finished build; documented cost); fb-load (STRONG < 3000ms after load: the window necessarily covers the parse itself).

## Totals (18 shapes x 4 offsets = 72 unscoped reads, plus scoped-to-main and scoped-to-host reads)

| | count |
|---|---|
| unscoped FALSE-QUIET | **3** (05@3500, 15@3500, 15@6500) |
| unscoped FB-PERM (steady-state) | **6** (01 x2, 11 x2, 13 x2) |
| unscoped fb-tail | 5 |
| unscoped fb-load | 14 (inherent) |
| hedged DOMSTABLE | 3 (2 noise on settled long-poll, 1 correct on late fetch) |
| scoped-to-main FALSE-QUIET | **5** (05@3500, 15@3500/6500, 18@3500/6500) |
| scoped-to-host FALSE-QUIET | 3 |

## Matrix (since ms / structural / text / attr / frames; verdict; scoped main; scoped host; error)

| shape | off | net | mut | verdict | sc.main | sc.host | err |
|---|---|---|---|---|---|---|---|
| 01_textContent_ticker | 300 | - | 26/35/0/0/0 | STRONG | STRONG | STRONG | fb-load |
| 01_textContent_ticker | 1500 | - | 27/47/0/0/0 | STRONG | STRONG | STRONG | fb-load |
| 01_textContent_ticker | 3500 | - | 22/30/0/0/0 | STRONG | QUIET | STRONG | FB-PERM |
| 01_textContent_ticker | 6500 | - | 21/30/0/0/0 | STRONG | QUIET | STRONG | FB-PERM |
| 02_xorigin_ad_iframe_churn | 300 | - | 329/32/0/0/0 | STRONG | STRONG | STRONG | fb-load |
| 02_xorigin_ad_iframe_churn | 1500 | - | 1530/32/0/0/0 | STRONG | STRONG | STRONG | fb-load |
| 02_xorigin_ad_iframe_churn | 3500 | - | 3525/0/0/0/0 | QUIET | QUIET | QUIET |  |
| 02_xorigin_ad_iframe_churn | 6500 | - | 6524/0/0/0/0 | QUIET | QUIET | QUIET |  |
| 03_chunked_table_no_network | 300 | - | 16/91/0/0/0 | STRONG | STRONG | STRONG |  |
| 03_chunked_table_no_network | 1500 | - | 89/311/0/0/0 | STRONG | STRONG | STRONG |  |
| 03_chunked_table_no_network | 3500 | - | 1570/280/0/0/0 | STRONG | STRONG | STRONG | fb-tail |
| 03_chunked_table_no_network | 6500 | - | 4570/0/0/0/0 | QUIET | QUIET | QUIET |  |
| 04_intersectionobserver_lazy | 300 | - | 324/34/0/0/0 | STRONG | STRONG | STRONG | fb-load |
| 04_intersectionobserver_lazy | 1500 | - | 1525/34/0/0/0 | STRONG | STRONG | STRONG | fb-load |
| 04_intersectionobserver_lazy | 3500 | - | 3519/0/0/0/0 | QUIET | QUIET | QUIET |  |
| 04_intersectionobserver_lazy | 6500 | - | 6518/0/0/0/0 | QUIET | QUIET | QUIET |  |
| 05_skeleton_late_timer_paint | 300 | - | 327/12/0/0/0 | STRONG | STRONG | STRONG |  |
| 05_skeleton_late_timer_paint | 1500 | - | 1526/12/0/0/0 | STRONG | STRONG | STRONG |  |
| 05_skeleton_late_timer_paint | 3500 | - | 3520/0/0/0/0 | QUIET | QUIET | QUIET | FALSE-QUIET |
| 05_skeleton_late_timer_paint | 6500 | - | 1517/1/0/0/0 | STRONG | STRONG | STRONG | fb-tail |
| 06_css_animation_only_settled | 300 | - | 325/32/0/0/0 | STRONG | STRONG | STRONG | fb-load |
| 06_css_animation_only_settled | 1500 | - | 1529/32/0/0/0 | STRONG | STRONG | STRONG | fb-load |
| 06_css_animation_only_settled | 3500 | - | 3528/0/0/0/0 | QUIET | QUIET | QUIET |  |
| 06_css_animation_only_settled | 6500 | - | 6531/0/0/0/0 | QUIET | QUIET | QUIET |  |
| 07_closed_shadow_chunked | 300 | - | 18/91/0/0/0 | STRONG | STRONG | UNKNOWN |  |
| 07_closed_shadow_chunked | 1500 | - | 95/311/0/0/0 | STRONG | STRONG | UNKNOWN |  |
| 07_closed_shadow_chunked | 3500 | - | 1587/280/0/0/0 | STRONG | QUIET | UNKNOWN | fb-tail |
| 07_closed_shadow_chunked | 6500 | - | 4590/0/0/0/0 | QUIET | QUIET | UNKNOWN |  |
| 08_longpoll_finished_dom | 300 | xmlhttprequest:2 | 319/32/0/0/0 | STRONG | STRONG | STRONG | fb-load |
| 08_longpoll_finished_dom | 1500 | xmlhttprequest:2 | 1523/32/0/0/0 | STRONG | STRONG | STRONG | fb-load |
| 08_longpoll_finished_dom | 3500 | xmlhttprequest:1 | 3523/0/0/0/0 | DOMSTABLE | DOMSTABLE | DOMSTABLE | hedged-noise |
| 08_longpoll_finished_dom | 6500 | xmlhttprequest:1 | 6526/0/0/0/0 | DOMSTABLE | DOMSTABLE | DOMSTABLE | hedged-noise |
| 09_same_origin_iframe_paints | 300 | - | 3/96/0/0/1 | STRONG | STRONG | STRONG |  |
| 09_same_origin_iframe_paints | 1500 | - | 79/316/0/0/1 | STRONG | STRONG | STRONG |  |
| 09_same_origin_iframe_paints | 3500 | - | 1567/280/0/0/1 | STRONG | STRONG | STRONG | fb-tail |
| 09_same_origin_iframe_paints | 6500 | - | 4569/0/0/0/1 | QUIET | QUIET | QUIET |  |
| 10_xorigin_iframe_paints | 300 | - | 323/10/0/0/0 | STRONG | STRONG | STRONG |  |
| 10_xorigin_iframe_paints | 1500 | - | 1527/10/0/0/0 | STRONG | STRONG | STRONG |  |
| 10_xorigin_iframe_paints | 3500 | - | 3527/0/0/0/0 | QUIET | QUIET | QUIET |  |
| 10_xorigin_iframe_paints | 6500 | - | 6529/0/0/0/0 | QUIET | QUIET | QUIET |  |
| 11_virtualised_live_grid | 300 | - | 22/132/0/0/0 | STRONG | STRONG | STRONG | fb-load |
| 11_virtualised_live_grid | 1500 | - | 20/492/0/0/0 | STRONG | STRONG | STRONG | fb-load |
| 11_virtualised_live_grid | 3500 | - | 18/900/0/0/0 | STRONG | STRONG | STRONG | FB-PERM |
| 11_virtualised_live_grid | 6500 | - | 20/900/0/0/0 | STRONG | STRONG | STRONG | FB-PERM |
| 12_attr_carousel_static_content | 300 | - | 22/32/0/3/0 | STRONG | STRONG | STRONG | fb-load |
| 12_attr_carousel_static_content | 1500 | - | 24/32/0/15/0 | STRONG | STRONG | STRONG | fb-load |
| 12_attr_carousel_static_content | 3500 | - | 20/0/0/30/0 | MINOR | QUIET | MINOR |  |
| 12_attr_carousel_static_content | 6500 | - | 23/0/0/30/0 | MINOR | QUIET | MINOR |  |
| 13_clock_plus_building_table | 300 | - | 16/97/0/0/0 | STRONG | STRONG | STRONG |  |
| 13_clock_plus_building_table | 1500 | - | 2/349/0/0/0 | STRONG | STRONG | STRONG |  |
| 13_clock_plus_building_table | 3500 | - | 14/310/0/0/0 | STRONG | STRONG | STRONG | FB-PERM |
| 13_clock_plus_building_table | 6500 | - | 19/30/0/0/0 | STRONG | QUIET | STRONG | FB-PERM |
| 14_skeleton_late_fetch | 300 | xmlhttprequest:1 | 317/12/0/0/0 | STRONG | STRONG | STRONG |  |
| 14_skeleton_late_fetch | 1500 | xmlhttprequest:1 | 1518/12/0/0/0 | STRONG | STRONG | STRONG |  |
| 14_skeleton_late_fetch | 3500 | xmlhttprequest:1 | 3515/0/0/0/0 | DOMSTABLE | DOMSTABLE | DOMSTABLE | hedged-ok |
| 14_skeleton_late_fetch | 6500 | - | 1507/1/0/0/0 | STRONG | STRONG | STRONG | fb-tail |
| 15_late_xorigin_iframe_slow_paint | 300 | - | 319/11/0/0/0 | STRONG | STRONG | STRONG |  |
| 15_late_xorigin_iframe_slow_paint | 1500 | - | 1016/12/0/0/0 | STRONG | STRONG | STRONG |  |
| 15_late_xorigin_iframe_slow_paint | 3500 | - | 3015/0/0/0/0 | QUIET | QUIET | QUIET | FALSE-QUIET |
| 15_late_xorigin_iframe_slow_paint | 6500 | - | 6016/0/0/0/0 | QUIET | QUIET | QUIET | FALSE-QUIET |
| 16_late_sameorigin_iframe_slow_paint | 300 | - | 312/11/0/0/0 | STRONG | STRONG | STRONG |  |
| 16_late_sameorigin_iframe_slow_paint | 1500 | - | 203/82/0/0/1 | STRONG | STRONG | STRONG |  |
| 16_late_sameorigin_iframe_slow_paint | 3500 | - | 195/140/0/0/1 | STRONG | STRONG | STRONG |  |
| 16_late_sameorigin_iframe_slow_paint | 6500 | - | 375/140/0/0/1 | STRONG | STRONG | STRONG |  |
| 17_slow_chunked_table_400ms | 300 | - | 309/31/0/0/0 | STRONG | STRONG | STRONG |  |
| 17_slow_chunked_table_400ms | 1500 | - | 313/91/0/0/0 | STRONG | STRONG | STRONG |  |
| 17_slow_chunked_table_400ms | 3500 | - | 298/140/0/0/0 | STRONG | STRONG | STRONG |  |
| 17_slow_chunked_table_400ms | 6500 | - | 73/160/0/0/0 | STRONG | STRONG | STRONG |  |
| 18_slow_chunked_closed_shadow | 300 | - | 309/31/0/0/0 | STRONG | STRONG | UNKNOWN |  |
| 18_slow_chunked_closed_shadow | 1500 | - | 310/91/0/0/0 | STRONG | STRONG | UNKNOWN |  |
| 18_slow_chunked_closed_shadow | 3500 | - | 292/140/0/0/0 | STRONG | QUIET | UNKNOWN |  |
| 18_slow_chunked_closed_shadow | 6500 | - | 68/160/0/0/0 | STRONG | QUIET | UNKNOWN |  |

Truth per shape:

- 01_textContent_ticker: settled; ticker is header-only
- 02_xorigin_ad_iframe_churn: settled; churn is in a cross-origin ad
- 03_chunked_table_no_network: building 0-2s
- 04_intersectionobserver_lazy: settled until the user scrolls (no signal possible without acting)
- 05_skeleton_late_timer_paint: building until 5s; nothing signals it in 0.3-5s
- 06_css_animation_only_settled: settled; animation is pure CSS
- 07_closed_shadow_chunked: building 0-2s inside a closed root
- 08_longpoll_finished_dom: settled; requests pending forever
- 09_same_origin_iframe_paints: building 0-2s in same-origin frame
- 10_xorigin_iframe_paints: building 0-2s in cross-origin frame (stated limit)
- 11_virtualised_live_grid: settled structurally; values change forever by design
- 12_attr_carousel_static_content: settled; carousel is attribute-only
- 13_clock_plus_building_table: header ticks forever; main building 0-2s
- 14_skeleton_late_fetch: building until 5s; network in flight
- 15_late_xorigin_iframe_slow_paint: iframe inserted at .5s then paints 0.9-8.9s; CROSS-origin: top ring sees only the insertion
- 16_late_sameorigin_iframe_slow_paint: control for 15: same shape, same-origin
- 17_slow_chunked_table_400ms: building at 400ms commits for 8s: tab-throttle regime
- 18_slow_chunked_closed_shadow: closed-root rows appended DIRECTLY to the root, 400ms commits

## Cost, re-earned (saturated ring: wrote > 1024 slots, 25-deep targets, 200-call batches, 5 interleaved reps)

| call | ms/call |
|---|---|
| query_ms | 0.002 to 0.006 |
| scoped_query_ms | 0.026 to 0.028 |
| regions_ms | 3.318 to 3.638 |
| per_landmark_5_ms | 2.094 to 2.710 |
| per_landmark_30_ms | 13.420 to 14.598 |

Patch A experiment (scoped reads 4s in, shadow still painting; since / structural):

- shipped/closed: {"9main": {"since": 4032, "sinceAny": 7, "structural": 0}, "9host": {"since": -1, "sinceAny": 91, "structural": 0}, "9foot": {"since": 4125, "sinceAny": 100, "structural": 0}}
- shipped/open: {"9main": {"since": 4034, "sinceAny": 12, "structural": 0}, "9host": {"since": -1, "sinceAny": 29, "structural": 0}, "9foot": {"since": 4058, "sinceAny": 36, "structural": 0}}
- patched/closed: {"9main": {"since": 396, "sinceAny": 396, "structural": 140}, "9host": {"since": 400, "sinceAny": 400, "structural": 140}, "9foot": {"since": 4024, "sinceAny": 5, "structural": 0}}
- patched/open: {"9main": {"since": 44, "sinceAny": 44, "structural": 160}, "9host": {"since": 50, "sinceAny": 50, "structural": 160}, "9foot": {"since": 4073, "sinceAny": 53, "structural": 0}}

## Ranked defects

1. **Scoped read false-quiet for a ShadowRoot's direct children (open AND closed). REAL, SILENT, FIX IS ONE LINE.**
   `listener_tag.js` `rec()` stores `el = target.nodeType === 1 ? target : target.parentElement`. A mutation whose
   target is a ShadowRoot (a custom element appending rows straight into its root: the normal Lit/Stencil shape)
   has `parentElement === null`, so `tg[s] = null`, and `query(scope)` can never attribute it (`hit = !!el && ...`).
   Measured, scoped read of `main` 4s in while a shadow root paints 400 rows: shipped `since=4032, structural=0`
   (QUIET, content still changing, true sinceAny=7ms). Scoped to the host: `since=-1` (UNKNOWN, safe, but only
   because #77's unknown branch catches it). Unscoped is correct (STRONG) because the doc-wide query ignores tg.
   R25 does not catch it because it mutates an Element child inside the shadow subtree, not the root itself.
   Patch (tested in the probe, 4/4 variants fixed, footer control unchanged at since 4024):
   ```
   -        const el = r.target && r.target.nodeType === 1 ? r.target : (r.target && r.target.parentElement);
   +        const el = r.target && r.target.nodeType === 1 ? r.target : (r.target && (r.target.parentElement || r.target.host || null));
   ```
   Add a check beside R25: shadow-root-direct-child painting, scope = host and scope = ancestor landmark, must not be quiet.
2. **Cross-origin iframe painting: unscoped AND scoped FALSE-QUIET (shape 15, 4 reads).** Stated limit, but the
   measured consequence is a flat "nothing" over a frame still building (the top ring sees only the iframe insertion
   and its window expires 3s later). Same-origin control (shape 16) is correctly STRONG at all four offsets, so #76/#77's
   merge works. Candidate (not built, needs a prevalence measurement first; #78 counts 128 frames on 96 corpus sites):
   a FACT clause when otherwise QUIET: "N cross-origin frame(s) of at least the 30px _frameShellsPage size are present;
   their DOM cannot be observed". It chooses no threshold beyond reusing an existing one, but it is an always-on line
   on every ad page, so it is #15 noise unless prevalence is low. Do not ship unmeasured.
3. **Idle gap before a late paint (shape 05, timer-only; shape 14 with a fetch).** FALSE-QUIET at 3500 (page silent 3.5s,
   paints at 5s) with no network. With a pending fetch the banner is DOMSTABLE (hedged, correct). Not fixable from
   recency: the infinite CSS shimmer present in 05 is also present in settled shape 06, with identical signals at
   every offset, so "running infinite animation" cannot separate them (checked, rejected by construction). Residual limit.
4. **Steady-state false busy (6 reads: textContent ticker, live-value grid, ticker+building table).** Real noise.
   Unscoped STRONG forever with `since` 3-5ms. A scoped read already solves the ticker (sc.main QUIET at 3500/6500 in
   shape 01, and shape 13 at 6500), so the escape hatch exists; 11 (a live grid INSIDE the content region) is
   inseparable by any attribution because the churn is in the region. Document it, do not "fix" it.
5. fb-load (14) and fb-tail (5) are the window itself, printed with `since`; not defects.

## Is (a), landmark attribution for UNSCOPED reads, worth building? NO, not as designed.

- It would convert 3 of the 6 steady-state false-busy reads (01 x2, 13 x1; 13 at 3500 is correctly busy) into
  attributable "header churning, main quiet for N ms". 11 and the 15 false-quiet are untouched.
- **Cost is not free any more.** One-pass owner attribution (prototype `regions()`, `matches(sel)` walk per slot) costs
  about **3.0-3.6 ms per read** on a saturated ring with 25-deep targets, versus 0.002-0.006 ms for the doc-wide query and
  0.026 ms for one scoped query. The alternative (enumerate landmarks, one scoped query each) costs 2.1-2.7 ms at 5
  landmarks and 13.4-14.6 ms at 30 (each out-of-scope slot walks to the root). Against a ~3,600 ms turn (#38) that is
  0.1% to 0.4%, so cost alone does not forbid it, but it undoes the "below timer granularity" claim for this path
  and would need a record-time owner cache on the hot path to stay cheap.
- The prototype also exposed the trap: churn in `(gc)` (collected targets, and shadow roots before Patch A) and `(none)`
  (outside any landmark) must be printed, never excused, or "main quiet" becomes a new false-quiet. That is a rule about
  who owns a record, which is exactly the judgement the design was meant to avoid.
- Cheaper sufficient step: ship Patch A, keep recommending `ref_id` scoping for ticker pages (already verified to work).

## Investigated and rejected

- "Running infinite CSS animation as a skeleton signal": identical on settled shape 06 and building shape 05.
- Network type as separator for late-paint shapes: shape 05 has no network at all; 14 already hedged.
- An IntersectionObserver lazy list (04): settles to QUIET and no signal can predict the scroll-triggered load; not a defect.
- Long-poll with finished DOM (08): DOMSTABLE correctly says the DOM is stable; the two DOMSTABLE rows are hedged-noise only
  by my ground-truth definition (content never changes), the sentence itself claims nothing.
- Same-origin iframe (09, 16) and closed shadow root unscoped (07, 18) were all STRONG while building: the shipped
  paths hold. The only closed/open shadow defect is the scoped direct-child one above.
- My first harness run printed all QUIET because the node stub lacked `_readinessPage`, so `runInTab(..., _readinessPage)`
  threw inside readinessNote's try and returned ''. A reminder that readinessNote swallows its own ReferenceErrors.
