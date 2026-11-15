# Open questions, ranked

The single working list. Each entry carries its evidence, because an open item
without evidence is a rumour and this project has had to delete several.

**When something closes, delete it from here** and leave the history in
`CLAUDE.md`. A stale open item sends the next reader to re-derive something
already done — and a retraction at the bottom of a long entry does not retract
the heading (#67).

Status key: `OPEN` · `IN FLIGHT` (being fixed now) · `MEASURE FIRST` (do not
build until the number exists) · `ACCEPTED` (a limit we are choosing to keep,
documented rather than fixed).

Last reviewed: 2026-11-15. Closed and deleted from here since the last
review: `query_elements`' missing visibility count (Q6c-Q6f), and the
readiness window measured in an unthrottled regime (R23/R23b — a 1000ms
window is 50.7% false-quiet at a 2s commit interval; 3000ms is 0.0%). Closed this session and deleted from here:
the kana fold collision, silent truncation loss in the default format,
`require` never firing, resume binding the wrong target, the handler-property
blindness, and the locale hazard (which did NOT reproduce) — all in `CLAUDE.md`
#71, #72 and #73.

---

## Tier 1 — a wrong answer reaches the user

### 0. Nothing measures REACHABILITY BY NAME `MEASURE FIRST`
Every ruler here measures PRESENCE — presence, `lost_identities`, Mind2Web
recall, and item 12's own DS. CLAUDE.md #74 found 118 elements that were
present in all of them and unreachable by `find`, on a page the readiness probe
called settled, including by their VERBATIM label. The listing was correct
throughout; the tool reading it was not.

Three of this session's defects were in the tools that READ the listing rather
than in the listing (the `find` blanking, the table column misalignment, the
submit verdict), and **no offline measurement in this repo could have caught
any of them**. A ruler that scores `find` against the labels the collector
emitted — ask for each entry's own printed identity and check it comes back —
would be cheap and would have caught #74 the day it shipped.



### 1. The observe→act gap is unguarded `OPEN`
We re-measure refs at click time but never compare what is there **now** against
what was **observed**. The model turn in between is ~3.6s (#38), which is the
whole exposure window.

Evidence: [arXiv:2603.00476](https://arxiv.org/abs/2603.00476) — **all 10
evaluated browser agents vulnerable, 100% trigger ratio**, prompt-only
mitigation gave no improvement; a MutationObserver (into shadow roots and
same-origin iframes) **plus a ResizeObserver**, checked immediately before
execution, gives **0% trigger at <0.05s**.
[arXiv:2610.39282](https://arxiv.org/abs/2610.39282) measures stale clicks at
**0.4% on a settled page vs 17% at DOM-ready**, and its break-even formula puts
the worthwhile-check threshold at **≈1.2% for an irreversible action** — i.e.
`fill_form(submit=True)`.

What we have: #51's `page_fingerprint` ref-resolution check is the machinery.
What we lack: a **ResizeObserver** (an overlay that shifts a box without
touching the DOM is invisible to a ref check, and `(occluded/blocked)` is
computed at listing time, not action time), and observation **through** the
model turn rather than at step boundaries.

### 2. 59.4% of ordinal-bearing descriptors cannot be witnessed `ACCEPTED`
The re-sort mis-bind is **closed for the witnessed majority** (#72): `resort` on
a witnessed descriptor is **0.0% WRONG at 94.3% CORRECT**, for +0.2pp refusals
on the six pre-existing mutations. What remains is crowds identical in every
declared field *and* in their surroundings, where nothing the collector emits
separates the members. They are no worse than before and no better.

Refusing them was rejected deliberately: it would pause ~14% of all descriptors
on an **unchanged** page, which is not a safety cost but losing the feature. The
recorder warns at record time instead, and the step carries a `review` line.

**Flows recorded before #72 carry no witness** and keep the old behaviour until
re-recorded.

What would close it: a declared per-member discriminator the collector does not
currently emit. Geometry would do it (87.3% coverage, measured) and is refused —
it drifts, so the safeguard would fire on every reflow.

### 3. `query(scope, …)` is dead code `OPEN`
`__abMut.query()` is called five times across the extension and the suites and
**every caller passes `null`**. The whole composed-tree `inScope()` containment
helper is unreachable — a half-contract shipped on the day the both-halves
principle was indexed (PRINCIPLES §14).

`READINESS.md` §5(b) presents per-scope attribution as part of "The design" in
present tense and marks it "Designed, not built" near the END of the file, which
is the retraction-at-the-bottom pattern the same doc set warns about. Either
wire it or delete the parameter.

### 4. `no_effect` and the hollow/unproven classifier — CLOSED
They now compose. The dead-click guard gated on `not step.expect`, and a
hollow assertion is a TRUTHY dict, so the guard skipped exactly the population
#57 and #68 exist to identify: a check that was already true before the step
cannot catch a click that did nothing, and nothing else was looking.

`Step.review` was persisted by #72 and read by nobody — the half-contract
shape this project keeps finding. The recorder now marks the fully-unevidenced
case at RECORD time (`unevidenced:`), because it already knows which checks
were hollow or unproven and re-deriving that from prose at replay would be a
second spelling of a fact we hold (#21). The runner keys on that prefix alone.

Unevidenced is still NOT a failure on its own (#68) — it only decides the tie
when the tool ALSO reports it did nothing. FR21 fails against the pre-fix
runner; FR21b and FR21c pass in both arms, which is what makes them controls,
and they assert WHICH PATH stopped the step rather than the fixture's row
count.


### 5. SPA readiness, the remaining half `OPEN`
The mutation-recency signal (#70) separates "still building" from "ready but
chatty" — measured 9–18ms vs 907–3514ms with no overlap. Still open:
- **scoped attribution.** theguardian.com shows ~7 ad-driven mutations per 2s,
  so document-wide recency alone would misreport a readable page. Kind-splitting
  (`40 @style` vs `40 structural`) covers the dominant case; per-subtree
  attribution is designed (`READINESS.md` §5b) and not built.
- **a per-ref primitive.** Playwright's actionability has one — *same bounding
  box for two consecutive animation frames* — and it is the cheapest readiness
  check anywhere. We have nothing equivalent.
- **nobody has measured whether telling the model helps.** We and browser-use
  are the only two projects that expose a settling signal to the model, and
  there is no published evidence it improves anything. A cheap A/B with
  `bench_turns`.

### 6. A CSS transition is not waited for `OPEN`
#51's settle covers **navigations**. A `browser_batch` of four observations after
a click all read the page before a ~300ms Bootstrap fade and came back empty on
a click that had worked. A fixed transition duration would be a chosen number;
the mutation signal from #70 may answer it properly, and that has not been
tried.

### 7. Page-level scans never cross an iframe boundary `OPEN`
An open dialog inside a frame gets no modal banner and no `section=dialog`.

### 8. Coordinate trust on canvas-dominated pages `ACCEPTED`
On OpenStreetMap the same ref reported clicks 1,097px apart, and a missed click
hits the map, so there is no symptom. Refs re-measure and are safe; the printed
coordinate is not.

### 9. Three unreproducible 30s+ stalls `OPEN`
Every page-injecting op hangs together while `get_url`/`sw_info`/`navigate`
answer in milliseconds — a blocked page main thread rather than a dead
extension; navigating recovers it. Not reproducible across four attempts. The
bridge's timeout ring (#50) now gives the next sighting its evidence. **Cannot
be fixed by guessing at it.**

---

## Tier 3 — measurement debts

### 10. Which Mind2Web positive we score against `MEASURE FIRST`
The headline itself was audited in #73 and **stands** (~96%, reproduced three
ways, zero label defects across 186 actions). What remains is upstream of it:
`fetch_mind2web.py` keeps only **`pos_candidates[0]`**, and the original ~590MB
shards were not retained. If Mind2Web marks several nodes positive per action,
our ruler uses one of them and may be stricter or looser than MindAct's.

**This is the largest unaudited choice in the measurement spine** and it sits
under every number derived from it. Closing it means re-downloading from
HuggingFace.

Also owed from #73, all small: `bench_mind2web.py`'s comment claiming the 13
excluded targets are "absent from the saved snapshot entirely" is **false** and
hid a real input defect for a year; the ~6-line serialization repair would make
the denominator the full 186 (and fix the one false ancestor credit for free);
and the ancestor credit path has **no area bound** while the descendant path —
the direction that cannot fail — has one.

### 11. No task-success measurement for our own ladder `MEASURE FIRST`
`detail` and `format` are priced on recall and tokens, never on end-to-end
success with a strong model. The literature disagrees with itself about which
way this cuts — [arXiv:2604.01535](https://arxiv.org/abs/2604.01535) measures
**+14.6 to +17.5pp for full HTML over a compact a11y tree** on strong models,
while EconWebArena measures **−10.2pp** for raw HTML. Unsettled rather than
alarming, and unmeasured here either way.

### 12. Sufficiency: measured for CONTROLS, unmeasured for TEXT `MEASURE FIRST`
`tools/measure_sufficiency.py` + `docs/SUFFICIENCY.md` close the control half.
Baseline: **`DS | reachable` = 0.933** (83/89 labelled targets distinguishable
among the rows we printed), LOSO 0.921–0.951, both negative controls passing and
both cross-checks against `bench_mind2web` / `bench_trajectory` exact. The
accessible name carries **51.7pp**, the tree's ancestry path **11.2pp** — a
number #27 never had, since the tree shipped on a NULL A/B result because no
metric there could read a listing the way an agent does.

**The 38.2pp this entry carried until now was a RULER BUG**, caught in
`SUFFICIENCY.md` and not propagated back to here — the listing prints identity
two ways (a bare quoted string after the tag, and `name="…"`) and the ablation
removed only the first, so it meant different things on different row shapes.
Recorded because a correction at the bottom of a long document does not correct
the index that points at it (#67), and this index was wrong for the hour
between the two being written.

**MEASURED AND REFUTED, as a design: the obvious probe cannot work.**
`tools/measure_text_sufficiency.py` uses eval 4's blind labels (author told
only to write varied two-hop tasks; every answer re-derived by an independent
referee) and harvests the pages mechanically from both arms' transcripts. On
4 tasks it reports 2/5 values carried, and both misses are a validation
message and a search result -- values that do not EXIST until the page is
interacted with. The confound is total and checkable in one line: `tasks.md`
records `Interactions needed` per task and **0 of 22 need zero**. The probe
measures how many eval tasks are two-hop, which is 100%.

**The route that would work runs through the flow recorder**: replay a
recorded flow to the step before the answer, then ask the text surface there.
That separates "the text surface failed to carry it" from "the value did not
exist yet", which no static load can.

**HALF OF THAT ROUTE IS NOW BUILT.** `run_flow(stop_after=N)` replays up to
and including step N and stops with the page in the state that step left it —
a validation message, a search result, a filtered table — which a fresh
navigate to the same url cannot reproduce. It reports `stopped_early` and
never `passed`, because the later steps' assertions did not run and a caller
reading "passed" would be reading a flow most of which did not execute
(FR22/FR22b, with FR22c the control that an ordinary replay still runs to the
end). What remains is the 20 recordings.

**The larger half is open and it is the one the source paper ranks first:
TEXT** (30.5 / 59.5 coverage drop when ablated, against 4.8–13.6 for any control
type). Our listing is a listing of *controls*; prose and table data reach the
agent only via `get_page_text`, `search_page` and `query_elements`, and nothing
measures whether those carry what a task needs. #14's scoped text and #26's
table rendering were both built from live-agent complaints, never priced.

Two measurement debts the control half surfaced, both cheap:
- **Mind2Web's snapshots have no `href`, no `src`, and no `aria-label`** (0 of
  61,709 `<a>`; 0 of 6,454 `<img>`; 17,272 `aria_label` against 1 hyphenated
  attribute). So the `detail` ladder is a near no-op there and AccName step 2C
  is dead for every implementation. Three structurally-absent signals beyond the
  two #73 names — **no `detail`/`brief`/`full` comparison taken on Mind2Web
  means anything.**
- **Density is not sufficiency, by about 4×** (27.6% of on-screen rows share a
  printed identity vs 6.7% of the rows a human needed). `audit_dom_quality.py`'s
  `ambiguous` rate is the first number and has never been the second.

### 13. The browser-use A/B may be measuring a legacy path `MEASURE FIRST`
The 84.5%-junk figure (#33) was measured against their `ClickableElementDetector`.
Their current `ax.py` takes existence from the Chrome AX tree instead. The
conclusion (do not import their admission rules) is unaffected; the **framing**
"we are more disciplined than browser-use about existence" is going stale.
Re-run before quoting it forward.

### 14. `opacity:0` and the accessibility tree `MEASURE FIRST`
We deliberately do not pass `opacityProperty` when deriving a NAME, because
opacity:0 content is still in the accessibility tree and excluding it would be
our judgement rather than the page's (#37, #39). browser-use's `ax.py` carries
the counter-case explicitly: *"the AX tree keeps opacity:0 text (pre-rendered
success banners), which agents then report as success"*. Our reasoning is sound
for naming and weaker for a tool whose output an agent reads as "what the page
says". Worth re-deciding deliberately rather than by inherited rule.

### 15. What our 31 tool schemas cost at session start `MEASURE FIRST`
Playwright MCP's own README now steers people toward CLI+skills over MCP on
token grounds. That is Microsoft's assertion with no published measurement, and
#38 says turns dominate tokens — but we have never measured our own schema
prefill.

---

## Settled — do not re-open without new evidence

- **Off-viewport admission.** +6.9pp first-read reachability for +18.7% tokens,
  **70% of the spend on tasks that gain nothing**, and the waste fraction does
  not move under two narrower predicates (#44). Three independent 2026 results
  now agree the problem is not that the model cannot see off-viewport content
  but that it does not execute the reveal — IGG measures **+3.1pp for telling
  the agent vs +48pp for doing it for it**, which is the sharpest argument for
  the region hint and against "scroll down".
- **browser-use's admission rules** — 84.5% of the gap is `cursor-pointer` and a
  10–50px icon rule; their own samples include a Hacker News rank number.
- **The Chrome AX tree** — 7.15× tokens for 4pp recall, and needs an attach that
  #12 proves gets refused on password-manager pages.
- **`find` for goal→element** — 0% with a human's task phrasing. That is
  semantic inference, not retrieval.
- **`id` / `data-testid` as a descriptor rung** — 6.8% / 2.5% coverage, perfect
  where present. Reopens only with a corpus of the internal apps this feature
  actually runs against.
- **Self-healing locators.** Unanimity across independent models is a valid
  signal for *which surviving element is this* and **actively anti-correlated**
  for *does it still exist*: 34/34 unanimous verdicts on deleted elements were
  **false heals**, and growing the model pool 3→7 did not reduce it. Keep the
  absence test structurally separate from the identity test. Never let a
  fallback rung answer "it's gone".
- **MHTML for corpus freezing** — 0% element retention.
