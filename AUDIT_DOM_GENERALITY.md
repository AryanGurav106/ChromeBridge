# DOM collection — generality audit

**Question:** does `_collectInteractivePage` (and the `get_page_text` path beside it) work on
*any* site, or has it quietly become specific — to English, to the light DOM, or to the handful of
UI libraries whose class names appear in its source?

Previous rounds answered this by reading the code and arguing about it. `AUDIT_GENERALITY.md`
concluded "no site-specific code; library signatures are boosters beside general paths, never sole
gates." This round tested that claim instead of asserting it, and **the claim was false in nine
places** — one of them affecting every non-Latin-script site on the web.

---

## 1. How it was tested

Three instruments, all running the **real** collector sliced out of `extension/background.js` (no
re-implementation that could drift from what ships).

### `tools/audit_dom_quality.py` — is the listing any good?

Runs the corpus of **106 real sites** (`tools/capture_listings.py::SITES`) and measures, per page:

| metric | definition |
|---|---|
| **recall** | of the ground-truth controls, how many are reachable in the structured output |
| **unlabeled** | entries with no name/text/value/placeholder at all |
| **ambiguous** | entries whose label collides with another's *and* that carry no `near=`/`under=` breadcrumb — the metric that predicts "the agent clicked the wrong one" |
| **generic** | `div`/`span`/`li` entries with no ARIA role: the collector's own noise floor |
| **chars/entry** | payload efficiency |

Ground truth is deliberately **independent** of the collector: a selector-based definition of "this
is a control" (`a[href]`, `button`, `input`, `select`, `textarea`, `summary`, the ARIA widget roles),
filtered to visible, in-viewport, not-`aria-hidden`, swept through shadow roots and same-origin
frames. The two are allowed to disagree — that disagreement *is* the measurement.

A control counts as covered if it appears as itself, a composed ancestor, **or** a composed
descendant. Dedup legitimately keeps a different node for the same visual control, so exact-mmid
equality would have scored correct behaviour as loss.

`--tag NAME` snapshots a run; `--compare A B` diffs two.

### `tools/audit_ablation.py` — how load-bearing is each library signature?

For every page: run the collector, then run it again with **one** hard-coded signature neutered to a
never-matching token, and diff entry by entry.

* A signature that is genuinely a *booster* produces small, cosmetic diffs.
* A signature that is *load-bearing* produces entries appearing or disappearing — which means
  **every site using a different library of the same kind is getting the ablated behaviour today.**

That inversion is the whole point: you cannot see the gap by testing the sites that happen to use
the library you named, only by removing the name and watching what the general path fails to do.

### `tools/test_generality.py` + `tools/generality_zoo.html` — 33 pinned shapes

Offline fixtures for every defect found here, so the next change in this area is caught by a test
rather than by a user on a Japanese page.

---

## 2. Two methodology bugs, found before any conclusions were drawn

Worth recording, because the first version of each produced confident, wrong numbers.

**The ablation was measuring page churn, not ablation.** mmid injection is additive, so a live SPA
that re-renders between two evaluations hands the second one a new mmid for a control that never
visually changed. Diffing on mmid alone scored that as a removal plus an addition. The first run
reported MUI's autocomplete page as `115 added / 116 removed` for *nine different signatures*, and
Spotify as 28 additions for a selector the page does not contain — the tell was that the diffs grew
monotonically down the ablation order, i.e. they tracked elapsed time, not the variable. Fixed by
(a) cancelling add/remove pairs that describe the same control (same tag, role, label, box) under a
new mmid, and (b) bracketing every variant with its own `base → ablated → base` control, so each
comparison is measured against the churn over exactly its own window. A single up-front control was
not enough — the first ablation in the list absorbed all remaining hydration and got blamed for it.
After the fix, churn on those pages reads 0 and the phantom effects are gone.

**The function extractor counted braces inside comments.** Every harness here slices the collector
out of `background.js` by brace-matching from the function header. Writing `greet() {` inside a
prose comment made the slice run past the end of the function, and the test then died inside
unrelated code with `ReferenceError: chrome is not defined` — pointing at the wrong file and the
wrong bug. Now `tools/_extract.py` skips comments, strings, template literals and regex literals,
and optionally parses the slice with Node so a bad extraction fails loudly at the extraction site.
All six harnesses share it.

---

## 3. Baseline

105 of 106 pages reachable (`surveyjs` timed out).

```
recall      99.91%   (8858/8866 ground-truth controls reachable)
entries     19423    (464099 chars, 24 chars/entry)
unlabeled   341 (1.8%)
ambiguous   847 (4.4%)
generic     242 (1.2%)
```

Coverage was already strong — the collector finds essentially everything a selector-based definition
calls a control. The defects were not in *what it finds* but in **what it can say about what it
finds**, and they concentrated exactly where no corpus site would reveal them.

### After

Measured on the 102 pages reachable in both runs:

```
baseline   8743/8751 = 99.909%   (8 controls unreachable)
final      8824/8826 = 99.977%   (2 controls unreachable)

per-page:  amazon     94.3% -> 100.0%
           amazon_de  94.4% -> 100.0%
           pages where recall DROPPED: none
```

**Totals are not quotable, and the drift control is why.** Running the *identical* source twice over
the corpus moves entries by 345 and characters by 4,635 — Spotify's personalized shelves,
premierleague's consent state and drawio's startup dialog alone account for hundreds of entries per
load. So `entries +620` between baseline and final is roughly twice the noise floor and mostly those
three pages, not the code. **Per-page recall is the stable signal**; it improved on two pages and
regressed on none. The listing does get modestly larger where the fixes add genuinely-missing
controls (Amazon's two header buttons, structurally-detected editor hosts) — that is a real and
intended cost.

---

## 4. Findings

### 4.1 Non-Latin text was rejected outright — three ASCII gates

The most consequential finding, and invisible to every existing test.

```js
if (!/[a-z]/i.test(v)) continue;                   // synthLabel: data-* attribute labels
if (c && c.length <= 40 && /[a-z0-9]/i.test(c))    // ::before icon-font content
return /[a-z0-9]/i.test(rest);                     // dialog body text
```

Each asks "does this contain letters?" and answers it with the Latin alphabet. A `data-testid="検索"`
is discarded and the button is listed as an unlabeled icon; a CJK icon-font ligature is discarded;
and — worst — **the dialog-text filter drops every line of a Japanese, Chinese, Korean, Russian,
Arabic or Hindi modal**, so `read_page` reports a modal is open and says nothing about what it says.
That is the one place the agent most needs prose and least able to guess it.

The corpus contains `yahoo_jp`, `baidu`, `naver`, `habr`, `wikipedia_ar` and none of them caught it,
because none of them had an open modal at capture time and the collector never *errored* — it just
returned less.

**Fixed:** `\p{L}` / `[\p{L}\p{N}]` with the `u` flag. Also `/^\d{1,6}$/` → `/^\p{Nd}{1,6}$/u`, so
Arabic-Indic and Devanagari digits count as digits.

### 4.2 Every page-level scan was blind to shadow DOM

`section=dialog` is computed with a composed-tree ancestor walk and works correctly inside web
components. But the four **page-level** scans beside it used `document.querySelectorAll`, which
cannot see into a shadow root:

| scan | consequence on a Lit / Shoelace / Ionic app |
|---|---|
| `dialogOpen` | a `<sl-dialog>` opens and the MODAL banner never fires |
| `dialogText` | no dialog text at all |
| `mainHeading` | a component's `<h1>` produces no "Main heading" |
| `virtualNote` | a virtualized grid inside a component declares 10,000 rows silently |
| `_domTextPage` outline + alts | the DOCUMENT OUTLINE is empty on exactly the component-heavy pages where a flat text dump is hardest to navigate |

So the collector correctly tagged a shadow dialog's *controls* while simultaneously telling the agent
no dialog was open.

**Fixed:** `_allComposed(sel)` filters the mmid registry — which *is* the composed walk, in tree
order — so these get the shadow-piercing answer with no extra traversal. `_domTextPage` got its own
shadow-piercing `deepQuery`. The dialog's own control labels are now gathered composed too, otherwise
a web-component dialog's buttons survive into the text as prose (`"Are you sure? Cancel Delete"`).

### 4.3 Code-editor support was three library names — measured, not guessed

Ablating the class list `.CodeMirror, .cm-editor, .monaco-editor, .ace_editor` changed the listing on
**9 of the 106 pages**. On Godbolt the entry lost its `(code-editor)` flag and its value became
`"1 2 3 4 // Type your code here"` — the line-number gutter, read as content. So any editor that is
not one of those three was already being presented to the agent as a div full of digits that it had
no reason to think it could type into.

**Fixed with two general mechanisms, keeping the class list as a fast path:**

* **Structural host detection** — the shape of a code editor, stated without naming one: a visually
  hidden `<textarea>` (the real input) inside an ancestor big enough to be an editing surface, which
  actually contains the textarea's position, and which renders monospaced or pre-formatted text.
  Rich-text editors are `contenteditable` and go down the existing `ceRoot` path, so requiring
  monospace/pre costs nothing and keeps ordinary hidden textareas out.
* **Structural gutter stripping** — a run of *consecutive* line numbers is never the value, in either
  layout a gutter renders in (its own column, so `innerText` emits the whole strip first; or inline
  per line). Requires the run to actually be consecutive, and the inline form requires every
  non-blank line to be numbered, so content that merely starts with a number survives.
  **Correction:** the `get_page_text` copy of this rule had *no* such context — it matched integer
  runs anywhere in the flat text and deleted a month calendar's 1–31. Flat text cannot distinguish a
  gutter from a calendar, so that path now hides the editor's gutter ELEMENT before reading
  `innerText` instead. Describing the two as "the same structural rule" was wrong.

One near-miss worth recording: the first version of the structural detector matched **every** hidden
textarea on the web, because Chrome's UA stylesheet gives `<textarea>` `font-family: monospace` — so
asking the editor's own input whether it "looks like code" always said yes. A comment box's autogrow
shim became a code editor. The fixture `E3` pins that.

### 4.4 A named native `<button>` could be dropped for being small

Amazon's header ships its language switcher and account menu as **8×4 px** `<button>`s with real
`aria-label`s. The sub-8×8 decoration filter dropped both, on `.com` and `.de` — the agent could not
reach the site's own language control. The filter's stated principle is "semantics beat pixels", but
it only exempted form tags and explicit ARIA roles.

**Fixed:** a native `a`/`button`/`summary` with a resolvable name is exempt too, still requiring ~3px
in the smaller dimension so genuinely zero-area sr-only anchors and tracking pixels stay out. Recall
on both Amazon locales went 94% → 100%.

### 4.5 Combobox placeholder state was detectable only in English

`/^(select|choose|pick)\b/i`. Ablating it changed combobox state on **chakra (18 controls),
primevue (18) and vuetify (3)** — those pages have neither `data-placeholder` nor a
descendant placeholder node, so the wordlist was their *only* signal. A German Chakra page reported
`value="Rahmen wählen"`, `unselected=false`: the agent believes a value is already chosen.

Inspecting what those libraries actually emit showed a general signal was available all along, just
broader than the one attribute being checked:

```
Radix / TipTap        data-placeholder                    (boolean, on the value node)
Ark UI / Chakra v3    data-placeholder-shown              (boolean, on the trigger)
PrimeVue              class="p-placeholder" + data-p="placeholder"
Ant / select2 / …     a child node classed …-placeholder
```

What they share is the **token `placeholder`** appearing in a `data-*` attribute name, a `data-*`
attribute value, or a class list. Class and attribute names are *code*, not content — they read the
same in any language.

**Fixed:** `_phMarked` / `_showingPlaceholder` match that token across all three locations, on the
trigger or on the node rendering its text. `aria-placeholder` is excluded on purpose (a static
description, present whether or not the hint is on screen), and an attribute carrying the hint
*string* rather than a boolean only counts when that string is what is actually rendered — otherwise
a real pick that left `data-placeholder="Choose a size"` behind would read as unselected.

**Verified:** with the fix in place, ablating the English wordlist changes **nothing** on Chakra
(23 comboboxes) or PrimeVue (27) — placeholder state is now derived structurally, and the wordlist
survives only as a last-resort supplement. The same detector was applied to `_triggerEvidencePage`,
which decides whether `fill_form` believes a pick landed; having the two disagree meant a widget was
read one way when observed and another way when acted on.

### 4.6 The icon-name rescue never worked on an SVG

```js
const m = /(?:^|\s)(?:fa|far|fas|fab|bi|icon)-…/.exec(ic.className || '');
```

On an `<svg>` — Lucide, Feather, Heroicons, Tabler, i.e. most of the modern set — `.className` is an
`SVGAnimatedString` that stringifies to `"[object SVGAnimatedString]"`, so this could never match an
SVG icon. Combined with a prefix list of two libraries, an icon+badge control collapsed to just the
badge count (`a "3"` for a messages menu).

**Fixed:** read via `getAttribute('class')`, and cover icon *libraries* rather than two of them. The
selector is only a cheap prefilter; the regex is the gate, so `graph-container` matching
`[class*="ph-"]` is still rejected.

### 4.7 Four smaller shadow/Unicode correctness gaps

* `aria-hidden` on a **component host** did not exclude its shadow content — `closest()` stops at the
  shadow boundary, so the W3C whole-subtree rule was unenforceable there. Now walked composed, and
  only for elements that actually live in a shadow root, so it costs nothing elsewhere.
* The `(required)` marker resolved `label[for=…]` against `document` while the accessible-name path
  correctly used `getRootNode()` — a required field inside a web component kept its name and lost its
  flag.
* The backing-control walk for custom comboboxes used `parentElement`, stopping dead at the shadow
  boundary, so a Shoelace/Ionic select lost `backed-by=` and `(unselected)` — its only
  language-independent evidence.
* Truncation used `String.slice`, which cuts UTF-16 code **units**: a label whose 60th unit lands
  inside a surrogate pair was cut through the middle of a character, emitting a lone surrogate. Any
  emoji in a button label. Five truncation sites were fixed in that round — **and a later audit found
  seven more inside `synthLabel` alone**, plus `dialogText`, `mainHeading` and `near=`, so the
  original "five sites now back off one unit" understated the problem. All are code-point safe now.

### 4.8 Performance, while in the neighbourhood

The parent-child dedup ran a composed ancestor walk for every element and did `out.find()` at each
hop — O(elements × depth × listed) for what is a hash lookup. On `java_api` (4,719 entries) that
dominated the walk. Now a `Map`. The new composed page-level scans are memoised per selector, since
the dialog selector alone is needed twice.

---

## 5. Ablation scorecard

Ablating one signature at a time across all 106 pages, each variant bracketed by its own
`base → ablated → base` drift control.

| signature | pages changed — before | after | what is left |
|---|---|---|---|
| `code-editor-host` (CodeMirror/Monaco/Ace class list) | **9** | **4** | labelling only — see below |
| `code-editor-content` (gutter/content class list) | **7** | **3** | cosmetic (no entry added or removed) |
| `english-select-wordlist` (`select\|choose\|pick`) | **3** — chakra 18 controls, primevue 18, vuetify 3 | **1** (vuetify) | chakra + primevue now fully structural |
| `radix-data-state` | 2 | 3 | `activeHint` booster; no general alternative exists |
| `active-selected-class` | 2 | 2 | same |
| `canvas-class-regex` | 1 | 1 | marginal, at churn level |
| `icon-font-class` → `icon-library-prefixes` | 1 | 1 (cosmetic) | now covers 18 icon libraries, and works on `<svg>` |
| `data-placeholder` → `placeholder-attr-name` | 0 (inert) | 2 | this is now the *general* signal, not a library name |
| `placeholder-class-token` | — | 0 (inert) | redundant second structural path |
| `cm-placeholder` | 2 (cosmetic) | 1 (cosmetic) | |

**The `code-editor-host` residual is a labelling difference, not a detection failure.** All four
remaining pages (`w3s_tryit`, `mdn_select`, `regex101`, `graphiql`) run CodeMirror 6, which has **no
textarea at all** — it is a pure `contenteditable` — so the structural rule (a suppressed *input
surface* inside a code-rendering box) cannot apply by construction. What happens instead is that
CM6's `.cm-content` is picked up by the existing `contenteditable` path: same element box, same
value, same `role=textbox`, and typing routes through the identical `execCommand('insertText')` code.
The only thing that changes is whether the listing says `(code-editor)` or `(rich-text-editor)`.
Measured side by side on regex101:

```
with class list:  div role=textbox codeEditor  box(492,24)  value="insert your regular expression here"
ablated:          div role=textbox editable    box(492,24)  value="insert your regular expression here"
```

GraphiQL additionally loses one entry — an empty secondary editor pane whose 1×1 textarea is parked
off-screen, so the containment test rejects it. That is the one genuine remaining loss.

Getting from 9 pages to 4 took three corrections that only measurement could have produced, each of
which had been guessed wrong:

* **"Hidden" is not "zero-sized".** Monaco's `.inputarea` is 147×48 with `color: rgba(0,0,0,0)` and
  `z-index: -10` — invisible because its text does not paint and it sits *behind* the render layer.
  That is the other standard way to keep an input focusable and form-serialisable while hiding it.
* **The monospace evidence is on descendants.** Monaco's host computes
  `font-family: -apple-system` and `white-space: normal`; only the line elements deep inside are
  monospace. Checking the host and its direct children finds nothing.
* **`readonly` does not identify a clipboard shim.** Monaco's mirror is readonly with an empty value.
  What identifies the shim a static code block ships is that its value is a *copy of the text the
  host renders* — a guard I first wrote as a blanket `readonly` reject, which broke Monaco while
  I was in the middle of generalising it.

A fourth correction was needed for *which* element to call the host: editors nest identical boxes
(`.overflow-guard` inside `.monaco-editor`), and taking the innermost left the outer one as a second
entry for the same visual editor. Preferring the ancestor that declares `role="code"`/`role="textbox"`
— an ARIA signal, not a class name — makes the structural result identical to the class-list one.

---

## 6. What is still specific — honestly

* **Library class lists remain as fast paths** for code editors and their content layers. They are no
  longer detection gates (§4.3, §5) — an unknown Monaco-shaped editor is found structurally — but
  they still decide whether a CodeMirror-6-shaped editor is labelled `(code-editor)` or
  `(rich-text-editor)`, and they are cheaper than the structural pass for the libraries they name.
* **`data-state` = active/open/on/checked** (Radix) and the `active|selected|current` class token on
  `role=tab`/`role=option` are boosters in `activeHint`, sitting beside the `aria-*` signals. A site
  using neither ARIA state nor those conventions cannot have its active tab detected — there is no
  third source.
* **The English `select|choose|pick` wordlist** survives as a last-resort supplement. It is now
  measurably redundant on Chakra and PrimeVue (ablating it changes nothing there), still load-bearing
  on Vuetify, and a hand-rolled non-English combobox that
  marks placeholder state *only* by rendering grey text remains structurally indistinguishable from a
  chosen value. This is the known residual, unchanged from earlier rounds — but it is now the *only*
  path for that case rather than the primary path for all of them.
* **Icon-library prefixes** are a list. It covers the mainstream set; an in-house icon font named
  something else falls back to `(unlabeled-icon)` plus a screenshot hint, which is a graceful
  degradation rather than a wrong answer.
* **Closed shadow roots** are still unreachable (would need CDP `pierce`). Unchanged.
* **Magic geometry thresholds** (25% viewport for a canvas, 8px decoration floor, ≥8 for a delegation
  root, ≥10 for grid compaction) are shape heuristics, not site heuristics, but they are tuned rather
  than derived.

---

## 6b. Follow-on: detail levels, and the difference between filtering and omission

The audit above is about filtering — deciding which of the page's controls to show. A separate
question came out of it: some things are **not filtered out, they were never collected**. A compact
listing has no `href`, no `src`, and no non-clickable `<img>` at all. No amount of loosening a filter
surfaces an image URL, because `<img>` is not interactive and was never a candidate.

That is why "just let the agent decide what to filter" does not solve it, and why the fix is a
detail level rather than a looser default:

| | cost, measured over 106 pages |
|---|---|
| `full` vs `compact` | **×1.39 median, ×2.09 p90, ×3.21 max** |
| escape-hatch legend line (paid on every compact read) | **110 chars, 2.6%** of a median listing; suppressed on the 4 pages with no links or media |
| `full` scoped to `main` vs whole-page `full` | 69% (a deliberately weak scope) |
| `full` scoped to one Hacker News story row | **924 chars vs 13,575** — 7% |

Three design points worth keeping:

* **`detail="full"` means more FIELDS, not more entries and not less filtering.** Those were bundled
  in the first sketch. They have different triggers and wildly different costs — lifting the 150 cap
  affects 36% of pages, and dropping the noise rules is the 2–18× case from §1. Keeping them separate
  means an agent that wants one image URL doesn't pay for the other two.
* **It composes with `ref_id`, because the agent has almost always already located the element**
  before it wants that element's URL. Page-level full detail is available and is almost never the
  right call; the tool description says so, and an unscoped `full` on a dense page prints an explicit
  "pass ref_id" note rather than quietly emitting a truncated payload.
* **The legend line is the actual feature.** Filtering is fine; *silent* filtering is not. Without
  one sentence naming what is absent, the capability is undiscoverable and the agent reports that a
  page lacks something it has. 2.6% is the standing price of never lying by omission.

`get_links()` / `get_media()` were considered and dropped — once `full` is ref-scopable they are the
same thing with a fixed field set and one more tool to keep consistent.

### What building the benchmark found

`tools/bench_detail.py` prices the shipped design (compact + scoped escalation) against the rejected
one (always full) on real tasks. Writing it surfaced two defects the fixtures had not:

* **Scoping excluded the host.** `read_page(ref_id=<the link>, detail="full")` — the most natural
  thing an agent would type — returned the link's *children*: zero rows for a plain link, and for an
  image-wrapping link, the image with the href swallowed. Fixed by including the host when
  `detail="full"`. Compact scoping still excludes it, because there the host is a container being
  looked *into*; the two rules are opposites and are now pinned side by side (D11–D13).
* **The op router was the one untested link in the chain.** Every other test injects the collector
  directly, so a `detail` parameter that never reached `_collectInteractivePage` would have looked
  perfect offline and silently served `compact` for every `full` request in production. Four router
  checks now cover it, including that an unrecognised value fails safe to `compact`.

Measured over 30 observations per task: **always-full costs ×1.73–1.81 of the two-step path**
(stable across four runs), targets reachable 5/5, URL/media questions answered 2/2.

Three apparent failures in the benchmark all traced to *correct* behaviour, and each was verified
rather than assumed — the habit this whole audit was built on:

| looked like | actually |
|---|---|
| saucedemo had no escape-hatch line | 0 links, 0 images — correctly suppressed |
| a Bootstrap input was "unreachable" | 45px below the fold; the listing says so and `find()` resolves it |
| an MDN link was "unreachable" | inside a collapsed `<details>` — a closed-details ghost, excluded on purpose |

Pinned by D1–D13 in `tools/test_generality.py`, including the two cases most likely to rot: a `data:`
URI must be *described* rather than emitted as a fetchable URL, and a 1×1 tracking pixel must not be
surfaced as media.

---

## 6c. Round 4 — adversarial review with verification required

Four Fable-5 auditors, one per region, briefed to treat documented residuals as non-findings and to
mark every claim verified-or-reasoning. They produced **28 findings, 21 verified against the running
code**, on a codebase that was already 210 checks green and had survived three prior review rounds.

The failure mode had MOVED. Coverage was no longer the problem — the problem was the layers that
**delete, merge and describe**, all of which fail silently:

| what was wrong | why no earlier method saw it |
|---|---|
| `opacity:0` form controls dropped entirely — Bootstrap 4's `.custom-control-input`, every styled file upload | the recall harness's own ground truth filters out `opacity:0` elements, so recall could never fall |
| clickable cards deleted at ≥3 children; clickable rows at ≥8 | both passes' comments described guards the code did not implement |
| an empty combobox reporting `value="<its own label + helper text>"` | no fixture modelled a wrapper containing a label |
| `aria-label="删除"` discarded as "too short to be real" | every fixture label was Latin |
| a calendar's 1–31 deleted from `get_page_text` | introduced the same day, by a fix for a real bug |
| coordinates wrong inside a `transform: scale()` frame | `test_frames.py` covers offsets, never transforms |
| Korean/Indic queries ranking buried matches first | the boundary-script class was an allowlist |
| `find` reporting "Found 20" when 31 matched | nothing asserted the count against the total |

Two of the findings were that **this document overstates what was fixed** (§4.7 and §4.3 above, now
corrected). An audit that cannot correct its own audit report is not an audit.

The through-line across all four rounds: reading found nothing; measuring (ablation) disproved a
documented claim in nine places; using it (nine live agents) found fifteen more; adversarial review
with verification required found twenty-one more. **Each method finds a class the previous one is
structurally blind to.** Budget for all four, and expect the last one to correct the first.

---

## 7. Re-running any of this

```powershell
# quality across the corpus, snapshot + diff
.venv\Scripts\python.exe tools\audit_dom_quality.py --tag before
.venv\Scripts\python.exe tools\audit_dom_quality.py --tag after
.venv\Scripts\python.exe tools\audit_dom_quality.py --compare before after

# which library signatures are load-bearing (use --src to pin a snapshot)
.venv\Scripts\python.exe tools\audit_ablation.py -c 5

# observation latency, A/B against a previous source file
.venv\Scripts\python.exe tools\audit_collect_time.py --before temp\dom_quality\background.prefix.js

# fixtures
.venv\Scripts\python.exe tools\test_generality.py     # 20 — this round
.venv\Scripts\python.exe tools\test_widgets.py        # 18 — combobox/popover shapes
.venv\Scripts\python.exe tools\test_gaps.py           # 48 — DOM-pattern inventory
.venv\Scripts\python.exe tools\test_shadow.py         # 11
.venv\Scripts\python.exe tools\test_frames.py         #  9 — cross-origin geometry
.venv\Scripts\python.exe tools\test_pixels.py         # 11 — device/CSS pixel scaling
node tools\test_ops.js                                # 83 — op router
```

**A note on interpreting corpus diffs:** the corpus is live. Between two runs of *identical* code,
Spotify's personalized shelves, premierleague's consent state and drawio's startup dialog move entry
counts by hundreds. Always run the drift control (`--compare` two runs of the same source) before
attributing a change in totals to a code change; per-page recall is the stable signal.
