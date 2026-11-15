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

Closed this session and deleted from here: a variable reaching the input and
the assertion but **not the target** (a flow acting on the thing it just
created bound to the record a PREVIOUS run left and reported PASSED), and an
assertion tool that was REFUSED or RAISED being reported as a failed assertion
rather than as a check that never ran. Both in `FLOWS-FAILURE-SURFACE.md`
(2.6, 5.6), both pinned by checks that fail against the pre-fix code.

Last reviewed: 2026-11-15. Closed and deleted from here since the last
review: `query_elements`' missing visibility count (Q6c-Q6f), and the
readiness window measured in an unthrottled regime (R23/R23b — a 1000ms
window is 50.7% false-quiet at a 2s commit interval; 3000ms is 0.0%). Closed this session and deleted from here:
the kana fold collision, silent truncation loss in the default format,
`require` never firing, resume binding the wrong target, the handler-property
blindness, and the locale hazard (which did NOT reproduce) — all in `CLAUDE.md`
#71, #72 and #73; **item 14 (`opacity:0`)** — measured and CLOSED as DON'T
BUILD (#78): 175 elements across 21/96 sites, **0 declare any ARIA role**, **0
identities lost**, and Chrome keeps 149 of them but the only interactive ones are
14 skip links and 2 back-to-top buttons, transparent precisely because the page
is not offering them; on the text half the risk surface is **505 characters
corpus-wide** (in-viewport AND not aria-hidden) against 22,252 if you cut on
opacity alone, with **0 of 434 sampled strings matching the success/error
vocabulary** that motivated the question. Probe kept at
`tools/audit_opacity.py`. And **`query(scope,…)` as dead code** — WIRED rather than
deleted, on a measurement (`CLAUDE.md` #76, `READINESS.md` §5b). Its residual is
narrower and lives in `READINESS.md`'s own open list: landmark attribution for
an UNSCOPED read is still unbuilt and is a different problem, needing a rule for
which landmark owns a record and a way to print several at once.

---

## Tier 1 — a wrong answer reaches the user

### 0. Reachability by name — MEASURED, residual is one shape `OPEN`
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
is now built: `tools/measure_findability.py`. **811/824 = 0.9842** across 34
frozen sites, with contested identities (shared by several entries, so the
probed one can fall outside find's bounded result set) counted separately.

**And the claim that it would have caught #74 is FALSE on this corpus** —
ablating the fix gives the identical number, because none of these 34 sites has
#74's shape. `--self-test` builds it synthetically and DOES fail against the
pre-fix scorer, with a known-miss control passing in both arms; that is the
guard, and the corpus run is the population number. Two different jobs.

**Residual: 13 misses, all one shape, none an app shell** — a label joined to a
badge (`span "Search Cmd+K"`, `a "Issues 5k+"`, `ul "4.1.0 25.9k 6.1k"`). The
name is assembled, so it is blanked, and unlike ptable's tile some contributors
ARE kept entries, so it is not a sole carrier. **The metric is therefore
stricter than the agent's real situation**: find("Issues") returns the inner
span, and clicking it does what clicking the link would, which is the same
reasoning #18/#73 use to credit a descendant on Mind2Web. Deciding whether to
credit a descendant here should be taken on its own merits, NOT while looking
at the misses it would erase.



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
The re-sort mis-bind is **closed on the `resort` arm, for the witnessed
minority** (#72): `resort` on a witnessed descriptor is **0.0% WRONG at 94.3%
CORRECT**, for +0.2pp refusals on the six pre-existing mutations. What remains
is crowds identical in every declared field *and* in their surroundings, where
nothing the collector emits separates the members. They are no worse than
before and no better.

**Two corrections to how that was written down**, both checkable and both now
carried in `FLOWS-FAILURE-SURFACE.md` 3.3a. The witnessed set is a **minority**,
not a majority — 212 of 558 (38.0%) on resort, 238 of 586 (40.6%) on reorder,
which is the same fact as the 59.4% in this heading. And the closure number is
from the `resort` arm alone: on the adversarial `reorder` arm a **witnessed**
descriptor is **71.4% WRONG** (#72's own table; re-derived at 55.6% on a
different 6-site sample). An anchor-only witness stays put while its element
moves, so whichever member arrives at the recorded anchor is bound confidently
and reported as a successful `moved` re-bind. #72 dismisses that arm as not
physically realisable, which is an argument rather than a measurement.

Refusing them was rejected deliberately: it would pause ~14% of all descriptors
on an **unchanged** page, which is not a safety cost but losing the feature. The
recorder warns at record time instead, and the step carries a `review` line.

**Flows recorded before #72 carry no witness** and keep the old behaviour until
re-recorded.

What would close it: a declared per-member discriminator the collector does not
currently emit. Geometry would do it (87.3% coverage, measured) and is refused —
it drifts, so the safeguard would fire on every reflow.

### 2c. Starting state: the precondition reaches 1 flow in 20 `OPEN`
`require` is derived from the observations between the landing navigation and
the first action, and `_checks` understands exactly three tools: `get_url`,
`search_page`, `query_elements`. The opening every agent is taught (#45's
`instructions=`, #46's `browser_batch` description) is
`tabs_create_mcp → navigate → read_page`, and **`read_page` contributes
nothing**. Measured across `flows/*.flow.json`: **1 of 20 carries a `require`**,
and that one was recorded to demonstrate the feature.

Not a one-liner: `read_page`'s first line is
`Current URL: <pathname + search>` while `expect.url` compares against
`get_url`'s ABSOLUTE url, so deriving one from the other would put two
spellings of one fact into the file (rule 17). Either a path-shaped check kind
or a reconstruction from the flow's origin, and both are schema-level.

Compounding it, and unlisted until now: nothing isolates one replay from the
next. `run_flow(stop_after=N)` ends mid-flow by design, `run_flows.py` creates
ONE tab for a whole batch, and `_pg_reset` runs only under `--playground` — so
the `ev-*` flows replay back-to-back in one tab with no isolation. Every flow on
disk happens to begin with a `navigate`, which is what has hidden it.
`FLOWS-FAILURE-SURFACE.md` 6.5–6.7.

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
- ~~**scoped attribution.**~~ **BUILT (#76).** A scoped read now scopes the
  readiness answer to the same subtree: measured at `since=4013ms / 0 structural`
  for the table a caller scoped to, at the instant the document read
  `since=48ms / 110 structural`. It also covers a case the kind-split provably
  does NOT — a ticker updating via `textContent` arrives as `childList`, not as
  an attribute write, so `@style` damping never saw it (measured: 25 structural,
  0 text, for a clock). **Residual: landmark attribution for an UNSCOPED read**,
  which is a different problem (which landmark owns a record, and how to print
  several), tracked in `READINESS.md`'s own list.
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

### 6b. A flow replayed against a LOCALISED app names no cause `OPEN`
The descriptor's identity rung IS the accessible name, so changing the app's
language invalidates every step at once. The playground already ships a `ja`
chaos flag whose own comment says "the whole descriptor design rests on the
accessible name" — and the failure surface had no entry for it.

Measured: a target recorded as `name='Sign in'`, replayed against a Japanese
render, reports *"no element on the page matches this step's target:
tag='button' name='Sign in'"* and nothing else, while the SAME failure at a
different viewport width appends *"The window is also a different WIDTH…"*.
The page declares the fact (`<html lang>`); the recorded half is missing, and
`Flow` has no `lang` field. `viewport` is populated by `mcp_server` at stop
time, so closing this needs a writer there as well as a reader in the runner —
both halves or neither (rule 14).

### 7. Page-level scans and the iframe boundary `MEASURE FIRST`
**HALF THIS ITEM WAS WRONG and is corrected (#78).** Same-origin frames ARE
reached: `dialogOpen` queries `_allComposed`, which iterates `mmidReg`, and the
collection walk stamps mmids across same-origin frame boundaries; `_readinessPage`
already merges same-origin frames (#70/R19). The real decomposition is:
- **cross-origin frames are invisible to all three page-level scans.**
  `collectCrossFrames` runs AFTER the banner is built and merely appends rows, so
  no cross-frame dialog can ever raise it. Nine constructed fixtures (two ports,
  so cross-origin is real): a cross-origin CMP as a full-page fixed overlay gets
  NO banner, **0 rows flagged `(occluded/blocked)`**, and no dialog text — while
  the same-origin version raises the banner and names what it omitted.
- **`section=dialog` is on 0 rows in all 9 fixtures**, including the three where
  the banner correctly fires: an in-frame dialog's controls resolve to
  `section=iframe`. Extends #23's open `section=` item across the boundary.
- ~~same-origin geometry~~ **FIXED (#78, MV4).**

**FREQUENCY IS NOT ANSWERABLE ON THIS CORPUS, and the zero is verified real.**
42/96 sites have a child frame (128 frames), 17/96 have a RENDERED one, and
**0 of 128 declare any page-level trigger**. Probe firing confirmed by a control
over the same pages' TOP documents: 91 dialog nodes, 15 visible, 7 `aria-modal`,
6/96 raising the banner. The corpus cannot hold the shape because **HARs are
captured after consent**, 21/128 frames no longer replay, and the one CMP-shaped
frame present declares its `role=dialog aria-modal` wrapper in the TOP document.

**THE COST ASSUMPTION IN THIS ITEM WAS ALSO WRONG.** `collectCrossFrames`
already injects the collector into **27 of 33 rendered frames (81.8%)** on every
unscoped string read, so the per-frame round trip is ALREADY PAID — it just calls
the structured arm (no modal verdict) and appends after the banner. Per-frame
injection is median 14ms against a 66ms top-level collect. The "free"
same-origin-only variant reaches **12/33 (36.4%)** and misses exactly where CMPs
live.

**Do not build on this evidence** — #26's rule needs both halves and the benefit
half is unmeasured. What makes it answerable: re-freeze a corpus slice with
cookies cleared so the CMP shape exists, or a live pass. If it is ever built, the
design the cost data points at is zero-round-trip: have the existing per-frame
call return each frame's verdict and feed it back before the banner is built.
Probe: `tools/audit_frames.py` (`--fixtures` serves the 9 shapes from two ports).

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

**CLOSED — the three small debts #73 left.** The false comment is gone, the
snapshot is repaired before it is rendered (`tools/_m2w_ruler.py`), and the
ancestor credit path carries the same area bound as the descendant path. One
denominator now, all 186 actions: **177/186 = 95.2%**, exact 161/186 = 86.6%.
`--no-repair` reproduces the pre-#73 arm (166/173 = 96.0% of the targets that
resolved) so both figures stay obtainable from the tool rather than from memory.
Three things #73 got wrong, each found by running rather than by arithmetic:

- the repair "fixes the ikea credit for free" is true only of the FAITHFUL
  repair (every non-void self-closed tag), not of the RAWTEXT-only one that
  yields the 96.2% #73 headlines — so the two sentences in its closing
  paragraph cannot both hold;
- "mirroring the cap gives 165/173 = 95.4%" is **166/173 = 96.0%**: refusing an
  ancestor credit is not losing the row, and that one falls through to the
  target's own `<input>`, which is sound by bubbling. **The bound costs zero
  recall on either arm** and removes the one credit #73 called false;
- the minimal repair also leaves two further ancestor credits standing
  (sixflags, underarmour) whose "wrapping anchor" the raw bytes show is a
  self-closed `<a … bounding_box_rect="-1,-1,-1,-1"/>` — empty and rendering
  nothing in the original page.

The faithful repair was chosen on a signal independent of recall: it is the only
arm with **zero cloned nodes** (the unrepaired parse re-creates unclosed
formatting elements, emitting several DOM nodes under one `backend_node_id` on
**137 of 186 samples**, up to 2.48×), and it never recovers fewer distinct ids
than the other arms. Residue, stated: a median 99.8% of each snapshot's ids
parse, worst 43.4%, because Mind2Web nests a frame's whole document inside the
`<iframe>` element. No labelled target is among them.

### 11. No task-success measurement for our own ladder — A ROUTE EXISTS `MEASURE FIRST`
`detail` and `format` are priced on recall and tokens, never on end-to-end
success with a strong model.

**"The literature disagrees with itself" was wrong and is withdrawn (#78).**
Verified at source: EconWebArena's −10.2pp arm is **o4-mini**, and its 36.7%
figure is labelled `- use_ax_tree + use_html`, i.e. raw HTML *replacing* the
AXTree. A small reasoning model degrading on raw HTML is exactly what
[arXiv:2604.01535](https://arxiv.org/abs/2604.01535) predicts. Both support ONE
capability-dependent model, and 2604.01535 raises the format confound itself and
controls it — the effect survives, and is *larger* under indentation (+20.9),
which is our format.

**THE ROUTE: WebPageBench ([arXiv:2609.35026](https://arxiv.org/abs/2609.35026),
Apache-2.0).** Verified from the released artefact rather than the paper
(`tools/audit_webpagebench.py` exits nonzero if any claim fails and self-tests
against three planted violations): 152 tasks / 65 canonical + 87 variants, 6
sites, 19 event types, 521 conditions, all exact; **no judge model** — `check()`
imports only `requests/os/json/re/datetime` and the oracle is a semantic event
emitted by business logic AFTER the state mutation, so it cannot see how the
agent acted or what it was shown; and the control swap keeps prompt AND success
conditions **byte-identical on 87/87**. Design in `docs/WEBPAGEBENCH.md`.

**Caveats that must travel with any number from it.** It is a **v1 preprint, 5
authors, no venue, not peer reviewed**. It is a **Russian-language benchmark** —
152/152 prompts are Cyrillic, which no description of it mentioned. The sites are
**synthetic**, which is the real missing leg; it is softened but not removed by
the fact that our only out-of-sample number today comes from stripped static
snapshots with no CSS and no scripts. Per-step element ground truth is **absent**
(end-of-task only), so this measures SUCCESS, not element recall. Hotels is 30%
of the set, so leave-one-site-out is mandatory.

**Build M-B first even though M-A is the question as asked**, because it needs
one arm instead of two: the same task re-rendered through a different date
picker or combobox, with identical success conditions, which is a direct test of
"works on framework-heavy SPAs without site-specific code". **The benchmark
ships its own negative control** — 12 `theme_dark` variants change colour only,
so a structural representation must score identically on them; if dark theme
moves the number, the instrument is wrong before any result is believed.

**The confound to design out:** our surface has escape hatches. An agent that
reaches the state via `javascript_tool` or by typing a URL measures Claude's
ingenuity, not the listing. Pin the toolset and report the fallback rate beside
every number, as #27 pinned `filter="interactive"`.

**Blocked on standing the site up**, which needs Docker started or `npm install`
on a third-party repo. Not established yet: real `href`/roles (expected from a
Vue router app, unverified), and the oracle has never fired end to end.

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

### 13. The browser-use A/B measures a path that is no longer theirs `RETIRE THE FRAMING`
The 84.5%-junk figure (#33) was measured against their `ClickableElementDetector`.
**Confirmed by reading their current source (#78): the AX-tree path is now the
DEFAULT** — their README documents `mode='ultrafast'` acting on accessibility-tree
ids as the default on `bu-fast`, and `bu-fast` is their stated default. So this is
past "going stale": the comparison describes code that is no longer the thing it
names, and **re-running it would measure the same obsolete path again.**

The CONCLUSION is unaffected and still earned — we did not import their admission
rules, and the measurement of why is in #33. What must stop is the FRAMING "we
are more disciplined than browser-use about existence", which is now a claim
about a path they do not take.

**One thing from their current source is worth more than the re-run would be:**
they split opacity BY PURPOSE, with a reason on each side — `checkOpacity: true`
for the text surface, because "the AX tree keeps opacity:0 text (pre-rendered
success banners), which agents then report as success", and OFF for action-target
validation, because "custom-styled widgets often keep an opacity-0 native select
underneath". That is the distinction item 14 was reaching for, and our own
measurement found **0 of 434 sampled opacity:0 strings matching success/error
vocabulary** — so their stated hazard has zero instances on our corpus while
their counter-case (the hidden native control) is exactly what our
`_declaredCtl` exemption already rescues.

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
