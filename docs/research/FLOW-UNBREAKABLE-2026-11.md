# Recorded flows: what is still breakable, and what the prior art does better

Research pass, 2026-11-17. Nothing in `core/flows/` was changed. Every proposal
below is a diff-in-prose plus a probe; the one probe that was written is
`tools/audit_record_witness.py`. Status vocabulary follows
`docs/FLOWS-FAILURE-SURFACE.md`: HANDLED (check id named), MITIGATED (how it
degrades), OPEN.

Things re-read before writing: `FLOW_RECORDER_PLAN.md`, `FLOWS-FAILURE-SURFACE.md`,
`FLOW-FRAGILITY-2026-11.md`, `flows/README.md`, `core/flows/{descriptor,model,
recorder,runner}.py`, `tools/audit_flow_resolve.py`, `tools/audit_href_rung.py`,
CLAUDE.md #49/#50/#54-#62/#72/#78.

---

## 0. The one-paragraph answer

The locator is not where this feature will break next. What is left is (a) the
**ordinal** — a positional claim — which is protected for only ~47% (39-site sample; 38-41% in #72's) of
the descriptors that make one, and where the shipped witness (the controls
*preceding* the target) has never seen the thing a human actually uses, the
**other content of the record**; (b) a family of leaves that share one shape —
*the flow's evidence is a rendering of the page, not a fact about the app* —
which a **network postcondition** answers structurally; and (c) the fact that
every descriptor silently depends on **the collector's own name derivation**, so
a ChromeBridge upgrade can invalidate recordings with no version anywhere in
the file to say why. The best idea in the prior art is not a locator idea at
all: it is Playwright's documented *row-scoping instead of `nth()`* (which is
candidate P1 here, arrived at independently) and ReUseIt's *synthesise the
guard from variations* (which can be done here for free, per step, at record
time, because `build()` and the mutation set are pure functions).

---

## 1. The failure surface, by layer

`H` handled · `M` mitigated · `O` open. Check ids are from `tools/test_flows.py`
as cited by `FLOWS-FAILURE-SURFACE.md` / CLAUDE.md; **rows marked (new)** are
leaves that document does not list.

### 1.1 Target resolution

| leaf | status |
|---|---|
| DOM path breaks on re-render | H — declared descriptor (#49) |
| descriptor unique at record, ambiguous later | H — cheap+full (#49, 54%→0% refused) |
| link name is live data (`Records 43`) | M — href alternate, links only (#61, FA1–FA9b); a button with a badge still pauses |
| tied crowd, composition changes | H — `len(hits) != of` refuses (FD8) |
| tied crowd, **re-sorted**, shipped witness present | H on the aligned-record arms (FD20…, #72) — see §3.3 for the caveat that the witness assumes member-LAST records |
| tied crowd, re-sorted, **no witness** (52.6% of ordinal-bearing in a 39-site sample; 59.4% in #72) | **O** — §3, proposal P1 |
| control not rendered yet | H — settle window (#59, FR13/FR13b) |
| responsive layout lacks the control | M — width named as a cause (#57, FVP2b) |
| page localised | M — `lang` recorded and compared (model.py `lang`, runner `_lang_note`); a cause is named, descriptors still all fail |
| **(new)** descriptor derivation changes under the flow's feet | **O** — `schema` in the file is the *file* schema (model.py:318). The collector's name derivation is part of every descriptor: #28 N5 changed AccName 2F separators (`49秒39`), #37 stopped hidden-subtree text donating names (eBay −24.9%), #67 named svgs. Every one of those silently re-keyed `name`. A recorded flow on disk across such an upgrade refuses with "no element matches" and nothing says the cause is *our own upgrade*. §4.P2 |
| **(new)** virtualised / windowed lists and grids | **O** — `of`/`nth` count *rendered* rows. A different scroll position renders a different crowd: composition-change refusal (safe) **or**, worse, the target row is simply not rendered and "no element matches" reads as drift. The page does declare `aria-rowcount`/`aria-rowindex`, but only 7.1% of ordinal-bearing descriptors in the 39-site sample carry either (§3.2), and rowindex is positional (travels with the sort) so it cannot witness a re-sort — it helps only with the *virtualisation* leaf |
| **(new)** controls inside cross-origin frames | **O, unmeasured** — mmids are `f<frameId>:<n>`; `section`/`under` are computed per frame; the descriptor has no frame identity (grep: `frame` appears once in descriptor.py, nowhere in runner/recorder). Two identical consent iframes, or an embedded checkout that re-mounts under a new frame id, are not addressable. Not measured because the frozen corpus HARs are captured *after* consent (#78 item 7's own note) |
| two overlays stacked (modal over drawer) | M — `section=dialog` is rung 2; nested dialogs share it |

### 1.2 Action dispatch

| leaf | status |
|---|---|
| trusted input channel dead, click reports success | H — `*** NOT DELIVERED ***` (#56, ID1/ID1b) |
| action refused / did nothing | H — `NOT DONE:` token (#66, FD19c/d), `NO EFFECT:` (#72, FR18) |
| coordinate steps | H by exclusion — deliberately unrecordable (#49) |
| popup/menu left open by previous step | M — runner names the open surface (#49, FR11b) |
| new tab / window | H — recorded `tabs_create_mcp` sets current tab (#58) |
| **(new)** a flow-opened `window.open` / `target=_blank` tab | **O** — `(opens NEW tab)` is in the listing, but a *click* that opens one leaves the runner in the old tab; the next step resolves against the wrong document and either refuses or, if the crowds coincide, mis-binds. Nothing in the recorder turns "a tab appeared" into a tab-switch step |
| hover-only controls, drag, scroll-then-act, keyboard chords | **O, unverified** — all route through `computer`; ref-based forms are recordable, coordinate forms are not, and I did not find (grep: 0 hits for hover/drag/scroll in recorder/runner) any handling. State this as "unverified by reading", not "broken" |
| file upload / download | **O** — 0 hits in runner/recorder; `file_upload` base64-over-bridge is outside the compile |
| native `alert`/`confirm` during replay | M — timeout message names `dismiss_dialog` (#51); flow has no step for it |
| element still animating when clicked | **O (new)** — pre-flight checks occlusion (`_rectForPage`) but not *stability*. Playwright waits for two identical bounding boxes before acting; #10/#11 are exactly this family on our side |

### 1.3 Postcondition semantics

| leaf | status |
|---|---|
| hollow (already true) | H — #57 FW1/FW2 |
| unevidenced (never observed before) | H — named `unproven`, not dropped (#68 FW5–FW7) |
| mistyped absence frozen in | H — #64 FE1d/e |
| text compared with `in` | H — whitespace-normalised equality (#72 FR19) |
| unknown / valid-but-vacuous key | H / **O** (2.7, `{"min": 0}`) |
| tool that could not answer ≠ page failed | H — #78 FR23 |
| settled-but-wrong (race between two XHRs) | **O / INHERENT** per 5.5 — **but see P3**: it is *not* inherent if the check is on the network rather than the pixels |
| **(new)** transient success state (a toast that lives 2 s) | **O** — the recorder promotes what `search_page` saw *at that moment*; the runner polls for up to `6s + settle_ms` for it to **become** true, which works for a toast that is still up and silently fails for one that appeared and left during the previous step's `await_quiet`. The check was true, was seen true while recording, and is false at the moment the runner asks |
| **(new)** assertion on content that is a function of the clock | INHERENT (6.8) — agreed; nothing here changes it |
| **(new)** the oracle problem (1.7) | INHERENT for pixels — **partially solvable for mutations**: §4.P3 |

### 1.4 Variables and secrets

| leaf | status |
|---|---|
| secret in plaintext | H (2.5) |
| variable reaches input, assertion, target | H (#54, #78 FV6–FV9b) |
| exact-equality only: `Created atlas-svc` keeps its literal | M — stated cost (#54); a re-record is the fix |
| generated ids / timestamps not extractable | O (6.8) — see P3, the *response body* is where a created id lives |
| a secret VALUE appearing in a later assertion's text | **O (unchecked)** — `type=password` is redacted at the input; a page that *echoes* the credential ("Signed in as hunter2@…") promoted into `search_page`/`query.text` lands the literal in the file. I did not test this; flagged as a thing to grep `expect` against the redacted names for |

### 1.5 Preconditions

| leaf | status |
|---|---|
| app not in the starting state | H — #50, FP1–FP5, #80 `path` kind (FP11) |
| the 20 files already on disk | M — acquire one only on re-record |
| `stop_after` leaves partial state | O (6.6) |

### 1.6 Timing / settling

| leaf | status |
|---|---|
| runner asks before the SPA painted | H — #55, `settle_ms` #60/#63 |
| `settle_ms` includes model turns | M — upper bound only (#64) |
| navigation race after a click | H — #51 `await_navigation` |
| CSS transition after a click | H — `await_quiet` (4.4) |
| background-tab timer throttling stretches an app's own settle time | M — measured in #70/#76 (a 400-row paint took 4.5 s+ hidden); `settle_ms` is recorded under the same throttling so it matches |

### 1.7 Tab / window identity, cross-document state

| leaf | status |
|---|---|
| flow spans tabs | H — #58 |
| one `run_flows` batch shares one tab (6.7) | H-ish — per-flow tab (#80 note) |
| session expires mid-replay (cookie TTL, CSRF token in a form) | **O** — an auth-dependent flow recorded at minute 0 fails at hour 6 at step 0 with "no element matches" on the *login page*. The precondition (`path`) catches a changed URL but not "same URL, different state" |
| **(new)** replay in a profile with different extensions | O/INHERENT — a password manager injects an iframe → #12 refuses the debugger attach tab-wide; the flow's trusted-input steps then fail on exactly the login page. Message exists (`attachDebugger`); the *flow* gives no pre-flight for it |

### 1.8 Environment

| leaf | status |
|---|---|
| locale | M (`lang`) |
| viewport width | M |
| date / clock | INHERENT |
| timezone, `prefers-color-scheme`, `prefers-reduced-motion` (apps swap markup on them) | **O, unmeasured** — #79 measured colour theme invariance at 12/12 for the *listing*; nothing measured it for *descriptors* |
| A/B bucket / feature flag changes the control set | O/INHERENT — refuses; a flow cannot know which arm it is in |
| network variance (late images → layout drift) | M — refs re-measure; descriptors carry no geometry (#23, #25) |

### 1.9 The recording compile itself

| leaf | status |
|---|---|
| errored call dropped, dead end dropped | H |
| content check kept as existence check | H (#63/#64) |
| **a descriptor built from a mid-render listing** | M — `_flow_entries` is fetched at action time, which can be mid-render; #61 settles the *replay* side, the *record* side of the same race is unaddressed. A name captured as `"Records"` (before the badge arrives) is then stored; the replay sees `"Records 43"`. Unmeasured |
| the agent's own recording-time **mistake** survives (1.7) | INHERENT for pixels |
| **(new)** the recording *is* one sample of a nondeterministic app | O — a descriptor is validated against one page state. The replay-vs-record gap is exactly what `audit_flow_resolve` fuzzes offline, and **the recorder never runs it on the page it just recorded** (§4.P4) |

---

## 2. Prior art: what each does, and what is genuinely better than ours

Sources are the vendors' own docs or a search result I read; where a search
returned nothing on a point it says so. Anything I did not verify is marked.

| system | locator | assertions | healing policy | idea worth stealing |
|---|---|---|---|---|
| **Playwright** (codegen, locators) | `getByRole`/`getByLabel`/`getByText`; **strict mode: >1 match throws** (the same refuse-rather-than-guess rule as ours). Documented guidance is to **narrow a list by row content — `row.filter({ hasText })` / `filter({ has })` and then search *inside* — rather than `nth()`**, because "if a list is reordered, a test that passes with `nth(1)` can quietly check the wrong element" (Checkly guide; a Japanese guide says the same). | web-first assertions that auto-retry (`expect(loc).toHaveText`), `toMatchAriaSnapshot` (subset matching is the default and is recommended for dynamic lists). Retrying is per-assertion, never cached. | none built in. Its newer "Healer" agent is reported to *skip* a test when the app itself is broken rather than rewrite the assertion | **row-scoping is the same idea as P1**, and it is the community's answer to the exact failure #72 measured at 94.4% WRONG. It is genuinely better than ours in one respect: it is *the primary recommended locator form*, where ours treats content-of-record as absent. Also **actionability checks: visible, stable (two identical rects), enabled, receives events** — we have the first, the fourth, partly the third; **not "stable"** |
| **Cypress** | CSS/`contains`; `cy.get(...).contains(row)` chains | queries are *re-run in full* on retry; only the final command's assertion is retried | none | **a retried query re-resolves from the root, never reuses a stale subject.** Ours does (`entries` re-fetched each attempt, #59) — parity, nothing to steal |
| **Chrome DevTools Recorder** | stores *several selector alternatives* per step (ARIA, CSS, XPath, text, pierce) and tries them in order | **none** — a demonstration says what was done and nothing about what should be true (CLAUDE.md #49) | none | the alternative-list is our cheap+full+alt. Parity, and ours is measured. Nothing to steal; stated so it is not reinvestigated |
| **Midscene** | vision/DOM-id model locates; the *located element* is cached | `aiAssert`/`aiQuery`/`aiBoolean` are **never cached** (docs); assertions still run on cache replay | on cache invalidation it falls back to the model; cache key includes page URL and viewport | agree with their never-cache-assertions rule (it is runner rule 1). One point in their favour: the cache is keyed on **URL + viewport + package version** — the *version* is the thing we lack (P2) |
| **Stagehand** | `observe()`/`act()` produce `{selector, method, args}`; cached by instruction | model-judged `extract` | re-runs the model on failure | per-step cache of a *resolved action* keyed by intent — not worth copying; ours refuses and hands the choice to the agent, which keeps the decision in the transcript |
| **workflow-use** (browser-use) | "semantic strategies" in YAML, direct index lookup else AI fallback | none beyond what the agent writes | falls back to the agent for the step; the README's own roadmap lists "agent updates the workflow file" as **unchecked** and flags LLM fallback "currently really bad" (search result; last push June 2025, AGPL) | nothing. They have not shipped the half we ship (declared postconditions, a proposal-not-edit patch) |
| **ReUseIt** (IUI '26, arXiv 2510.14308) | n/a (agent actions) | **condition checks synthesised from failed-run messages; retry strategies from successful runs of generated variations**; success 24.2%→70.1% on 15 tasks | guards + fallback actions | **derive guards from variations of the run.** They pay 15-52 minutes of model-driven re-runs. We hold `build()` and a pure mutation set — the same loop costs milliseconds *per step, at record time*, with no model (§4.P4) |
| **Dagu** | n/a | n/a | re-asks the model on failure | nothing; I did not find a primary source in this session's searches |
| BrowserStack / Momentic / Shiplight (self-healing vendors) | store locator + nearby attributes + DOM structure per element; heal by AI against the live DOM | — | a minority recommend "auto-apply only deterministic, reversible changes, never auto-merge" | agrees with rule 3 (proposal, not edit). Momentic also stores *visual and accessibility signals per target* — we have no visual signal, deliberately (geometry/pixels drift, #23/#25) |

**What is genuinely better than ours, plainly:**
1. Playwright **actionability "stable"**: wait for the target's rect to stop moving before dispatch. We measure occlusion and refuse, but a control mid-transition is clicked where it *was*. (#10/#11 are this family.)
2. Playwright/Cypress **row-scoped locators are the first-class idiom**, with a decade of use behind them. Our descriptor ladder has no way to say "inside the row that says 1001".
3. Midscene's **cache key carries a package version.** Our file carries a file-schema version and nothing about the derivation that produced `name`.

Nothing in the prior art provides **preconditions**, **declared postconditions
promoted from the agent's own checks**, or a **witness for an ordinal**. #50's
claim stands on this search.

---

## 3. The 59.4% unwitnessed population

### 3.1 What the shipped witness can and cannot see

`witness_map` records `self` fields (href/value/text/label/placeholder) and
`after`: the identities of the nearest preceding **named controls** since the
previous crowd member. It cannot see **non-control content** — a row's other
cells, a card's title and price — because those are not in `entries`. That is
the whole of how a human says which Delete they meant: "the one on the 1001
row". Also: #72's `resort` model *defines* a record as "the run of entries from
just after member k-1 up to member k", i.e. it assumes the member is **last**
in its record, and the witness is built on the same assumption. Hacker News'
vote arrow **opens** its record.

### 3.2 The candidate, structurally defined

* **Record** of a member of a tied crowd = child of the crowd's lowest common
  ancestor that contains it; where several members share a child, recurse inside
  it until the member stands alone. No tag list, no class, no threshold (the
  MDR/DEPTA assumption #27 already uses to decide repetition).
* **Atoms**: every rendered text node (and `img alt`) in the record, plus
  every non-presentational attribute of the record root and of the member
  (`name=qty[3]`, `id=row-1001`; `class`/`style` excluded as presentation).
* **Witness** = the *set* of atoms unique to the member **at record time**.
  At replay a member carries the witness if its atom set *intersects* the stored
  set; **exactly one carrier** resolves, zero or several refuse. Intersection,
  not equality, is what lets one cell change without breaking the step, and it
  needs no threshold.
* `aria-rowindex` / `aria-posinset` measured for coverage only; they are
  positional, so they cannot witness a re-sort.
* **Policy**: a step that carries atoms is decided by them (never falls back to
  the ordinal — falling back would reinstate the silent mis-bind); a step
  without atoms behaves exactly as today. Only descriptors that already make an
  ordinal claim are touched.

### 3.3 Measurement

`tools/audit_record_witness.py`. Method copied from `audit_href_rung.py` /
`audit_flow_resolve.py`: frozen HARs, one fresh context per arm, collector
extracted verbatim from `background.js`, mmid identity as the ruler with a
per-site validity check, existing resolver run on the *same mutated page in the
same pass*. Difference from `audit_flow_resolve`: the mutations are **real DOM
mutations of a real page, then re-collected**, not permutations of the entry
array — because the entry-array model bakes in the member-last assumption
(§3.1) and cannot say whether a *content-based* witness survives.

Arms: `base` · `resort` (reverse the record containers) · `resort-last` /
`resort-first` (reverse whole sibling *runs*, member at the end / member at the
start of its record) · `shuffle` · `edit-cell` (one atom changes) ·
`bump-digits` (all digit runs +1) · `drop-other` (a different record removed).

**Run**: `python tools/audit_record_witness.py --sites 50 --no-win` — 41 frozen
sites loaded, 39 contribute ordinal-bearing descriptors, **2,540 descriptors**
(≤120 per site). Three sites (github, select2, kayak) fail the mmid-ruler
validity check and have their mutation arms skipped, not scored. Full output is
reproduced in the findings below; `temp/descriptors/record_witness.json` holds
the raw rows.

**Coverage** (of ordinal-bearing descriptors):

| | n | share |
|---|---|---|
| shipped witness (self + preceding controls) | 1,203 | **47.4%** |
| record TEXT unique (child-of-LCA) | 1,116 | 43.9% |
| record/member ATTR unique | 1,108 | 43.6% |
| text OR attr (`rec`) | 1,533 | 60.4% |
| text only (`txt`) | 1,116 | 43.9% |
| shipped OR `rec` | 1,752 | **69.0%** |
| no record could be isolated at all | 925 | 36.4% |
| `aria-rowindex` / `aria-posinset` present | 97 | 3.8% |

**Unwitnessed by the shipped witness: 1,337 = 52.6%** (59.4% in #72's 24-site
sample; the figure moves with the sample). Of those, `rec` rescues **41.1%**
(per-site median 50.0% over 38 sites) and `txt` rescues **23.0%** (per-site
median 13.5%). The remaining ~36% of all descriptors sit in crowds with no
isolable record (a row of identical toolbar buttons): the page declares nothing
about them in any form this probe reads, and **no content witness exists for
them**. That is the honest floor of this idea, and it is large.

**Resolution under real DOM mutation.** The table that matters is the one that
compares both resolvers on the *same targets* — descriptors that actually HAVE a
record witness (otherwise both columns are diluted toward the ordinal):

| arm | resolver | n | CORRECT | REFUSED | **WRONG** |
|---|---|---|---|---|---|
| resort (containers) | shipped | 883 | 60.2% | 22.8% | **17.0%** |
| | record witness `rec` | 883 | 91.7% | 7.8% | **0.5%** |
| resort-last (member ends record) | shipped | 867 | 59.1% | 23.2% | 17.8% |
| | `rec` | 867 | 90.7% | 9.2% | 0.1% |
| resort-first (member opens record) | shipped | 883 | 55.3% | 26.3% | 18.5% |
| | `rec` | 883 | 88.2% | 11.6% | 0.2% |
| shuffle | shipped | 881 | 57.4% | 19.2% | 23.4% |
| | `rec` | 881 | 92.5% | 6.2% | **1.2%** |
| drop-other (composition changes) | shipped | 276 | 9.4% | 90.2% | 0.4% |
| | `rec` | 276 | 97.5% | 2.5% | 0.0% |
| edit-cell (one atom changes) | shipped | 338 | 51.5% | 48.5% | 0.0% |
| | `rec` | 338 | 70.4% | 29.6% | 0.0% |
| bump-digits (every counter) | shipped | 1,364 | 71.7% | 28.2% | 0.1% |
| | `rec` | 1,364 | 75.5% | 24.3% | 0.2% |
| base (no mutation) | both | 1,487 | 99.9% | 0.1% | 0.0% |

Text-only (`txt`, 758-759 descriptors with a text witness): resort 0.4% WRONG,
shuffle 1.4%, bump-digits **0.6%** WRONG (vs `rec` 0.2%), drop-other 0.0%.

Over the whole sample, including descriptors with no record witness (which fall
back to the ordinal and stay exposed), the shipped resolver is **22.8% WRONG**
under `resort` and `rec` is **8.3%** — the residual is entirely the ~36% with
nothing to witness, which is why §3.4's last bullet matters more than the table.

*Caveat on the shipped column:* it includes descriptors the shipped witness
already covers; on a **faithful** whole-record move (`resort-first` on Hacker
News, whose vote arrow opens its record) the already-witnessed subset was 0/112
WRONG. The 17-18% is overwhelmingly the unwitnessed half. See §3.4.

**Rejected variant `win`** (text of both neighbouring sibling runs), first
41-site run: covers more (63.3% any) but `resort` WRONG on the unwitnessed
population 24.9% vs `rec` 20.7%, and `drop-other` 72.7% vs 78.2% correct.
Neighbours' atoms collide.


### 3.4 Reading it — and what I got wrong on the way (#16)

* **I first read "shipped witness: 10.8% WRONG on re-sort" as a finding. It is
  mostly my mutation.** Split by site and alignment: on Hacker News the shipped
  witness is **0/112 WRONG under `resort-first`** (the faithful whole-record
  move for a member-first record) and **18/112 WRONG under `resort-last` and
  `shuffle`**, which move the *wrong* blocks for that layout and so tear records
  apart. The honest reading is narrower: **the shipped witness is only as sound
  as its member-last assumption**, and that assumption is declared nowhere. On
  a faithful move it held in this sample. It is a *caveat*, not a measured
  defect, and I am not claiming otherwise.
* The *record-content* witness is insensitive to alignment because its atoms
  come from the record container, which travels intact under every permutation.
  That is the property that matters, and also why it can only be fooled by an
  *edit*, not by a re-sort.
* **`win` (the symmetric neighbour window) is worse than `rec` on every arm**
  (more atoms are neighbours', so more collisions) and is **rejected**.
* **Content volatility is not a cost of the witness in this sample** (bump-digits
  refuses 24.3% with it vs 28.2% without, because the set-intersection rule
  survives a counter that moves in only some atoms); **edit-cell** is the arm
  that hurts both resolvers equally (a step whose only unique atom is the one
  that changes). The one thing atoms *do* cost is an `id` they cannot trust:
* **ATTR atoms contain a trap, and run 1 showed it live.** In the first full run
  Angular Material resolved **4 of 120 descriptors to the WRONG element with no
  mutation applied at all**: `id=mat-select-value-3` is unique, looks declared,
  and is a per-load counter. It did not recur in run 2 (load-order dependent),
  which is the point — a stability arm of two loads can pass and the hazard
  stay. `txt` (text only) cannot be fooled this way and costs coverage: `rec`
  rescues 41.1% of the unwitnessed, `txt` 23.0%. **Ship `txt`; admit an attribute
  atom only after a stability check that does not exist yet** (an `id` that is
  identical across two reads is the only kind worth trusting, and the recorder
  cannot reload the page — so: never, until P2-style measurement says otherwise).
* #25 applies in both directions: the corpus is mostly landing pages and
  component-demo sites (top contributors: mui_autocomplete, hn, shoelace,
  mui_datepicker, vuetify at the 120 cap each); there is **no admin table, invoice
  list or order grid** in it, which is precisely where this witness would live.
  Per-site medians (rec 50%, txt 13.5%) are far below what the pooled number
  suggests for `txt`. Quote the per-site figure beside the pooled one.
* **The honest ceiling is 69.0%** (shipped OR `rec`) and **~56% with `txt`**:
  about a third of tied crowds have no record the page declares. For those the
  only defences left are P4 (say so at record time, measured) and refusal-by-default
  — which #72 rejected on a 14% pause rate and which this sample prices at
  *52.6% × 22.8%* of ordinal-bearing steps being silently wrong under a re-sort.
  That arithmetic is the argument for re-opening #72's decision for the
  *no-witness-available* class only, with `run_flow` pausing instead of binding.

---

## 4. Ranked proposals

Ranked by (how badly the leaf fails) × (how cheap the fix is). Each ends in the
number it has, or the exact probe that would settle it.

### P1. Record-content witness for ordinals — number in §3

**Ship text atoms only (`txt`).** Numbers: of the descriptors that HAVE one,
resort 0.4% WRONG / 8.2% refused against the shipped resolver's 11.6% WRONG /
23.4% refused on the same targets; drop-other 96.3% correct against 13.8%.
`descriptor.py`: add `witness["atoms"]` (sorted list) beside `self`/`after`;
`witness_map` gains an in-page structural pass; `_resolve_recorded` checks atoms
*first* when present, by set intersection, ignoring `of` (a content witness that
uniquely identifies the member makes a composition change survivable: the
`drop-other` arm resolves 96% where today it refuses 51%). Needs one new
collector field per entry in the structured array (`record_atoms`, computed only
for members of a crowd, so zero tokens — the array is never printed). Policy
for the existing witness: keep both, atoms decide when present.
*Cost*: one new collector field; edit-cell is unchanged (both resolvers refuse
when a step's only unique atom is the one that moves). *Guard*: a check named
after the `resort-*` arms; `bump-digits` and `base` are its negative controls.

### P2. Stamp the derivation, not just the file — MEASURE FIRST (cheap)

Add `collector: <int>` to the flow, incremented by hand whenever a rule that
changes `name`/`label`/`section`/`under` changes (N5, NR1, SV1, TA1 are
examples). A mismatch is a *cause*, appended to every resolve failure, exactly
as `lang` and viewport are. No threshold, no wordlist; Midscene keys its cache
on package version for the same reason.
**Probe that settles it**: run every `flows/*.flow.json` descriptor against the
frozen-corpus collector *at git tags #37, #67 and HEAD* and count how many
`name` fields differ for the same element. Zero → the leaf is theoretical;
nonzero → it is a recurring silent invalidation. (I did not run it: needs the
old collectors checked out; `git archive <tag> extension/background.js` +
`_extract.py` gives them.)

### P3. A network postcondition — MEASURE FIRST (highest ceiling)

For each *mutating* step the recorder already knows the tab and the window;
`read_network_requests` already exists. Record the **non-GET same-origin
requests the step caused, as `(method, path-with-numeric/uuid-ish segments
replaced by `:id`, status class)`** and assert them at replay. Why this is
structurally better than anything above it:
* it is a **mechanical fact the agent cannot misread** — it takes the oracle
  problem (1.7) off the table for the very commonest assertion ("the record was
  created"), because a 201 POST either happened or did not;
* a silent no-op step issues **no request**, so the hollow-check class (#57)
  becomes un-recordable rather than warned about;
* it separates **settled-right from settled-wrong** (5.5) where nothing in the
  DOM can: the two racing XHRs in the eval 4 case are two requests with an
  order;
* it removes the transient-toast leaf (§1.3), since a request does not leave;
* the created id lives in the response, which is the variable-extraction half of
  6.8.
Costs and risks, stated: `:id` normalisation is a *rule* (digit runs and
hex/uuid-shaped segments) and must be measured for false collapses (two
different endpoints sharing a shape) — do not ship a wordlist of "id-looking"
words; apps that post to GraphQL (one path for everything) need the *operation
name* from the body, which the `webRequest` API does not expose without
`requestBody` permission.
**Probe that settles it**: replay the 20 flows in `flows/` through the existing
`tools/run_flows.py` harness with `read_network_requests` called after each
step, and report (a) fraction of mutating steps with ≥1 non-GET request,
(b) fraction where the *set* of `(method, :path)` pairs is identical across two
replays (stability floor), (c) fraction of steps whose DOM postcondition is
hollow (#57) but whose network witness is non-empty. (b) < ~100% means the
idea needs a different key; (a) tells you the ceiling. Not written this
session: it needs a live browser plus the fixture app and the number would be
over a sample of one app I wrote (#25).

### P4. A record-time **mutation self-test**, per step — cheap, no model

ReUseIt synthesises guards from re-runs of variations; we can do the same at
`record_flow(stop)` with `build()` and the pure mutations already in
`audit_flow_resolve.py`: for each compiled target, run `rename-target`,
`insert-twin`, `twin-elsewhere`, `reorder`, `resort`, `counter-in-name` against
the entries captured at that step and store/print the *verdict row*
(`CORRECT/REFUSED/WRONG`). A step whose `reorder` verdict is `WRONG` is named
at record time — the generalisation of `unwitnessed_ordinal` (which today
fires on a structural proxy) into a **measured** per-step robustness report.
It is read in a diff, which is the only re-grader #68 says exists. Cost:
`audit_flow_resolve` runs 8 mutations × 120 targets per site in seconds.
**Probe**: already exists — `tools/audit_flow_resolve.py`; the work is moving
`mut_*` out of `tools/` into an importable module (the audit file is not
importable without Playwright) and calling it from `Recorder.before`.
Caveat: it inherits the member-last assumption (§3.1) for `resort`; P1 removes
the need to trust it.

### P5. An **optional / guarded step**, proposed from a failed-then-resumed run — MEASURE FIRST

ReUseIt turns failure messages into condition checks. Ours already has the
event: `run_flow` pauses (`needs_decision`), the agent clears an unexpected
banner and resumes. Today `record_flow(action="patch")` can only rebind a
descriptor. When a resume *inserts* actions (the agent did something the flow
did not), the diff between "what the flow expected" and "what the agent did to
get unstuck" is exactly an `optional: true` step with its own precondition
(`#62` already describes this as the third `on_fail` value, "skip", and
declined to build it for lack of a case). **Probe**: grep the transcripts of
`bench_flows` round 1/2 resumes for steps the agent added; count them. Zero →
#62's decision stands.

### P6. Actionability **stability** before dispatch — small, mechanical

Before the trusted click, measure the target's rect twice 50 ms apart (the
attach→settle→measure ordering from fix #10 already waits 50 ms); if it moved,
re-measure instead of dispatching. No threshold: "moved" is *different at all*.
**Probe**: instrument `clickTrusted` to log rect deltas across a corpus of live
SPA clicks (the playground has a CSS-transition modal); frequency of a non-zero
delta is the number.

### P7. Frames — MEASURE FIRST

Add the frame's *origin+path* (declared, from `frameElement.src` / `location`)
to the descriptor as a rung above `section`, only when the entry's mmid has the
`f<n>:` form. **Probe**: needs consent-banner pages, which the frozen corpus
lacks (captured after consent); build 5 fixtures first.

---

## 5. Rejected, with the number

| candidate | number | verdict |
|---|---|---|
| neighbour-window atoms (`win`) as the witness | covers 63% but 24.9% WRONG vs `rec` 20.7% on the unwitnessed set; drop-other 72.7% vs 78.2% correct | rejected — neighbours' atoms collide |
| `aria-rowindex`/`aria-posinset` as a re-sort witness | present on 3.8% of ordinal-bearing descriptors (97 of 2,540); **positional**, so it travels with the position and is information-free under a sort | rejected as a witness; kept as the *only* declared handle for the virtualisation leaf |
| geometry as a witness | 87.3% unique (#72) | already refused: drifts (#23, #25) |
| `id` / `data-testid` | 6.8% / 2.5% coverage (#61) | not re-proposed; note the record-attr atoms in this probe **do** include `id`s on the record root, so they come along for free where they exist without a new collector field |
| a model-ranked heal | ReUseIt judge κ=0.528; workflow-use "really bad" | out of scope by rule 3 |

## 6. What I could not establish

* **The sample is component-demo and landing pages**, not business apps (no admin table, invoice list or order grid); the headline numbers are in §3.3 and the per-site medians are far lower than the pooled ones for `txt`.
* **The `resort-first`/`resort-last` split models record alignment by sibling
  stride**; it is a model, and a record that is not a run of equal-length
  siblings (a masonry grid, a flex-wrap card list) is skipped, not scored.
* Frames, virtualisation, downloads, uploads, hover/drag: listed as OPEN from
  *reading the code*, not from running a flow — #25's own warning about listing
  from reading applies to every `O, unverified` row above.
* P3's ceiling cannot be known without the probe.
