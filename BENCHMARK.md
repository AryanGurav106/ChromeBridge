# ChromeBridge vs Claude-in-Chrome — head-to-head benchmark

**Current result: the generality eval, 2026-10-09/10.** 19 tasks across 7 task
archetypes, 38 runs, strictly serial, pre-registered before any data existed.
Harness, prompts, scorer and analysis: `tools/bench_turns/eval3/`.

| Metric | Claude-in-Chrome | **ChromeBridge** | |
|---|---|---|---|
| Turns (one assistant message carrying tool calls) | 240 | **117** | 15/17 decided pairs, **p = 0.0023** |
| Wall clock | 3,674 s | **1,662 s** | 17/19 pairs, **p = 0.0007** |
| Turns to first page content (median) | 4 | **2** | 2 on all 19 runs, no spread |
| Tab-ceremony calls | 11 | **0** | |
| Correctness | 19/19 | **19/19** | saturated — see below |

Secondary analysis on the 16 tasks whose final hop is not already on the search
results page: 13/15, p = 0.0074. Both the primary and the secondary clear.

### Read this before quoting the numbers

- **Correctness cannot discriminate and is not a win condition.** Both arms are
  the same model, so the ceiling is Claude's, not the tool's. It is recorded as
  a FALSIFIER: had ChromeBridge's correctness dropped below the other arm's, the
  turn result would have been rejected outright. 38/38 across both arms.
- **A large share of the margin is the other arm's defects, not our
  representation.** Its runs included four of 18-31 turns, nearly all from one
  cause: trusted input reporting success without reaching the page. Those cannot
  affect the sign test, which counts direction only — that is why the bar is set
  there — but they do inflate the totals. Excluding those four pairs: **72 v 127
  turns (57%)**, so the result survives removing its own outliers.
- **On the one archetype where both arms ran clean we are level.** Per-archetype
  turn ratios: SPA 0.29, search-flow 0.35, data-table 0.43, drill-down 0.45,
  doc-lookup 0.60, non-Latin 0.71, **form-lookup 0.88** — and form-lookup is the
  only archetype ChromeBridge did not win outright (1-1). Per-archetype n is ~3
  and is reported descriptively, with no p-values.
- **The per-origin consent gate was OFF during the runs.** Consent is a one-time
  per-origin cost a real user pays once, not a per-task turn cost, and counting
  it would charge ChromeBridge nine times for a security feature the other arm
  does not have. **So these numbers say nothing about the cost of the consent
  model**, and a first-time user still pays an Allow click per site that they do
  not contain.

### What came before, and why it is superseded

Three earlier pre-registered evals (10, 10 and 24 tasks) came back **TIES** —
dead level on calls, inside the measured ~47 s/task drift floor on wall clock.
Two more (9 tasks each) cleared on turns but were weak in the same two ways:
n=9, where one bad task breaks the result, and a task set made entirely of
two-hop navigate-and-read lookups, which is the shape the advantage is largest
on. The generality eval exists because of that second weakness.

**The 2026-07-25/26 study below (32 runs, 5 scenarios, "1.86x faster, 12.5x
fewer retries") is kept as a historical record and should not be quoted as the
current result.** Its methodology is weaker than everything after it: agents
self-timed with `date` brackets, tool calls were harness-counted rather than
read from transcripts, tasks were written by the same person running the
comparison, there was no pre-registered bar, and no independent ground truth.
Three later evals run with those controls in place found a tie on the same
question. Where the two disagree, prefer the later design.

---

## The 2026-07-25/26 study (historical — superseded, see the note above)

**32 measured runs** (2 pilot + 3 rounds x 5 scenarios x 2 servers). Each run was
an independent subagent restricted to one server's namespace, self-timing with
`date` brackets and required to report its own failures. Prompts were
byte-identical across rounds.

| Metric | Claude-in-Chrome | ChromeBridge |
|---|---|---|
| Total in-task time (15 runs each) | 1132.1 s | 607.1 s |
| Retries / error-recovery calls | 25 | 2 |
| Tool calls (harness-counted) | 244 | 167 |
| Tokens | 870,962 | 812,791 |
| Scenarios won (of 15 pairings) | 3 | 12 |
| Task correctness | all completed | all completed |

Everything below this line describes THAT study, not the current one.

## Methodology

### Controls

- **Sequential execution.** Both extensions drive the *same* Chrome. Parallel runs
would steal tab focus, corrupt `captureVisibleTab` (it grabs whatever is
frontmost), and contend for `chrome.debugger`. Every run ran alone.
- **Verbatim prompts.** Round 2 and 3 reused round 1's prompts byte-for-byte. Any
wording change would have invalidated cross-round comparison.
- **Order counterbalancing.** Which server ran first was alternated per scenario
(R1: CIC,CB,CIC,CB,CIC — R2 flipped — R3 back to R1's) to cancel HTTP-cache
warming. Note: with 3 rounds this cannot balance perfectly; R1 and R3 share an
ordering.
- **Independent isolation.** Each run was a fresh subagent with no memory of prior
runs, so no learning carried between scenarios. This costs tokens but prevents a
later scenario benefiting from an earlier one's discoveries.
- **Fresh tab per run**, created and closed by the agent.
- **Self-timing.** Agents bracketed their own work with `date +"%s.%N"`, so the
measurement excludes my orchestration overhead and their final report writing.

### Honesty constraints given to every agent

- "NEVER stop early on failure. Record what happened, continue."
- "An honest partial run is the goal; a fabricated success is worthless."
- "Do NOT fabricate data. Every value must come from a tool response."
- Explicit instruction to log every retry, error message (quoted), ambiguity, and
moment of uncertainty — and to write "none" only if genuinely none.

### Metric caveats

- **Tool counts: harness-recorded numbers are authoritative.** Several agents
miscounted their own calls (one reported 24, recounted 31, harness said 32;
another said 11, corrected to 14, harness said 14). Harness counts include
ToolSearch and Bash, so they are higher than self-reports throughout.
- **In-task elapsed** is the primary time metric. Harness wall-clock (which
includes report authoring) ran roughly 1.5–1.7× higher for both sides.
- Some scenario data is live (Hacker News scores change between runs), so
extracted values differ slightly across rounds by design.

### Environment

Windows 11, real user Chrome profile, ChromeBridge extension loaded unpacked,
MCP server over stdio. Both servers drove the same browser and the same sites.

---

## Scenarios


| #   | Name                        | Site                                          | What it stresses                                                                                                                                                             |
| --- | --------------------------- | --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S1  | Multi-field form            | `selenium.dev/selenium/web/web-form.html`     | Atomic fill of 5 heterogeneous control types, native select by visible text, a decoy checkbox (one starts checked), submit, server-receipt verification via URL query string |
| S2  | Combobox disambiguation     | `select2.org/getting-started/basic-usage`     | A plain `<select>` and a Select2-enhanced widget showing the same value; must mutate the enhanced one and prove the native one is untouched                                  |
| S3  | Structured extraction       | `news.ycombinator.com`                        | Read-only. 25 cells (5 stories × rank/title/points/comments/domain). Dense legacy markup, zero actions                                                                       |
| S4  | Modal handling              | `getbootstrap.com/docs/5.3/components/modal/` | Below-fold trigger, modal open/read/dismiss, focus isolation, closure verification                                                                                           |
| S5  | Search → navigate → extract | `en.wikipedia.org`                            | Drive the site's own search box, submit, land on an article, extract heading + first sentence + top-level TOC count                                                          |


S2 was originally `ui.shadcn.com` but that page's Base UI widget became
unresponsive to *all* input (trusted mouse, trusted keyboard, React hydrated) mid-
session; it was swapped for select2 after verifying the widget itself was dead, not
the toolset.

---

## Results by round

### Round 1 — baseline (pre-fix)


| Scenario    | CIC (s)   | CB (s)    | Ratio     | CIC calls | CB calls | CIC retries | CB retries |
| ----------- | --------- | --------- | --------- | --------- | -------- | ----------- | ---------- |
| S1 form     | 64.4      | **23.8**  | 2.71×     | 17        | 9        | 0           | 0          |
| S2 combobox | **73.3**  | 103.1     | 0.71×     | 15        | 17       | 0           | 0          |
| S3 extract  | 23.5      | **13.9**  | 1.69×     | 9         | 7        | 1           | 0          |
| S4 modal    | 112.5     | **58.3**  | 1.93×     | 19        | 16       | 4           | 2          |
| S5 search   | 157.0     | **41.1**  | 3.82×     | 22        | 11       | 5           | 0          |
| **Total**   | **430.7** | **240.2** | **1.79×** | 82        | 60       | 10          | 2          |


CB wins 4/5.

### Round 2 — after legend/orphan/find-reach/smooth-scroll fixes


| Scenario    | CIC (s)   | CB (s)    | Ratio     | CIC calls | CB calls | CIC retries | CB retries |
| ----------- | --------- | --------- | --------- | --------- | -------- | ----------- | ---------- |
| S1 form     | 55.8      | **26.0**  | 2.15×     | 17        | 9        | 0           | 0          |
| S2 combobox | 74.7      | **44.4**  | 1.68×     | 17        | 12       | 2           | 0          |
| S3 extract  | 20.7      | **12.7**  | 1.63×     | 8         | 7        | 0           | 0          |
| S4 modal    | 93.3      | **48.5**  | 1.92×     | 19        | 13       | 2           | 0          |
| S5 search   | 127.4     | **55.9**  | 2.28×     | 22        | 11       | 4           | 0          |
| **Total**   | **371.9** | **187.5** | **1.98×** | 83        | 52       | 8           | 0          |


CB wins 5/5. **First round with zero ChromeBridge retries.**

### Round 3 — after find-scorer/context/get_url/outline/payload fixes


| Scenario    | CIC (s)   | CB (s)    | Ratio     | CIC calls | CB calls | CIC retries | CB retries |
| ----------- | --------- | --------- | --------- | --------- | -------- | ----------- | ---------- |
| S1 form     | 46.8      | **20.0**  | 2.34×     | 16        | 9        | 0           | 0          |
| S2 combobox | **61.4**  | 77.3      | 0.79×     | 15        | 14       | 0           | 0          |
| S3 extract  | 15.1      | **10.6**  | 1.42×     | 8         | 7        | 0           | 0          |
| S4 modal    | 101.3     | **39.5**  | 2.56×     | 19        | 14       | 4           | 0          |
| S5 search   | 104.9     | **32.0**  | 3.28×     | 21        | 11       | 3           | 0          |
| **Total**   | **329.5** | **179.4** | **1.84×** | 79        | 55       | 7           | 0          |


CB wins 4/5.

### Pilot run (combined task, before scenario split)


| Server           | Time       | Calls  | Retries | Tokens |
| ---------------- | ---------- | ------ | ------- | ------ |
| Claude-in-Chrome | 208.3 s    | 32     | 8       | 62,686 |
| **ChromeBridge** | **57.3 s** | **14** | **0**   | 53,943 |


Ratio 3.64×. Excluded from aggregate totals (different task shape).

---

## Per-scenario medians and variance (3 rounds)


| Scenario    | CB runs (s)       | CB median | CIC runs (s)        | CIC median | Verdict                               |
| ----------- | ----------------- | --------- | ------------------- | ---------- | ------------------------------------- |
| S1 form     | 23.8, 26.0, 20.0  | **23.8**  | 64.4, 55.8, 46.8    | 55.8       | CB, consistent, 2.3×                  |
| S2 combobox | 103.1, 44.4, 77.3 | 77.3      | 73.3, 74.7, 61.4    | **73.3**   | **CIC on median — real loss**         |
| S3 extract  | 13.9, 12.7, 10.6  | **12.7**  | 23.5, 20.7, 15.1    | 20.7       | CB, consistent, 1.6×                  |
| S4 modal    | 58.3, 48.5, 39.5  | **48.5**  | 112.5, 93.3, 101.3  | 101.3      | CB, **monotonically improving**, 2.1× |
| S5 search   | 41.1, 55.9, 32.0  | **41.1**  | 157.0, 127.4, 104.9 | 127.4      | CB, high variance, 3.1×               |


Two observations only visible across rounds:

**S4 improved monotonically (58.3 → 48.5 → 39.5).** That tracks the find-reach and
smooth-scroll fixes. Step 3 went from 5 calls (failed find → read_page → TOC-link
scroll → find again → click) to 2 calls (find → click), with the click auto-
scrolling to a target 2365 px below the fold.

**S2 is a genuine, reproducible loss.** Round 2's win was variance. See below.

---

## S2: the one scenario ChromeBridge loses

The select2 docs page double-initializes, leaving two structurally identical
`.select2-container` widgets — only one wired to a real `<select>`. Measured live:
the **wired** widget had collapsed to **2 px wide and invisible**; the **826 px
widget the user actually sees was inert**.

So both geometry and a screenshot point at the corpse. Round 1's CB agent spent
three `javascript_tool` jQuery-introspection calls to resolve it honestly.

A `(DEAD-DUPLICATE)` flag was built to fix this. It shipped **broken** (a
width-dependent wrapper walk produced different signatures for the two twins —
diverging precisely in the case it existed to detect), was caught only because a
benchmark agent quoted the old text, and was re-fixed and verified live.

**In round 3 the flag fired and was correct — and bought nothing.** The agent did
not trust a bare verdict and spent 2 calls plus an unplanned ToolSearch verifying
it with `javascript_tool`. Its own words:

> "ChromeBridge's `(DEAD-DUPLICATE)` and `role=combobox` annotations did in fact
> point at the right answer, so the friction was me spending two extra calls
> verifying a hint that turned out to be correct... a tool-surface signal I
> trusted more (e.g. naming the backing form control in the listing) would have
> saved the detour."

**Lesson: a correct verdict the agent will not trust buys no time.** The listing
should emit *evidence* (`backed-by=ref_347`, naming the hidden native control) not
a judgement, so the agent can confirm in-listing without leaving the abstraction.

CIC, notably, also could not resolve S2 from its own tool surface — it dropped to
`javascript_tool` in all three rounds. It simply spent fewer calls doing so.

---

## Recurring friction — Claude-in-Chrome

Quoted from agents' own logs.

**1. Ref-clicks and keypresses report success while doing nothing (7 occurrences).**
The single most consequential pattern.

- `"Clicked on element ref_14"` — submit never fired.
- `"Clicked on element ref_517"` — modal never opened (both R2 and R3).
- `"Clicked on element ref_290"` — Select2 popover never opened.
- `"Pressed 1 key: Return"` — search form never submitted (R2 and R3).
- `"Typed \"WebSocket\""` — text never reached the field (R3).

> "The tool reports success on a click that had zero effect — a less paranoid
> agent would have reported a false PASS on Step 4."

> "I cannot trust any `computer` success message without a screenshot, which
> inflates every future interaction by a verification round-trip."

There is no auto-escalation to trusted input, so recovery is manual: screenshot,
re-derive coordinates, re-click.

**2. Zero modal awareness.** With the Bootstrap modal open, ~90 unreachable
background elements stayed listed as normally interactive, the `dialog` node sat
~90 refs deep, and closure was signalled only by a role word silently changing
`dialog` → `generic`.

> "Nothing flags that a modal is up or that the ~90 still-listed background
> elements are now unreachable behind a backdrop, which is precisely the failure
> mode this scenario exists to probe."

**3. Screenshot/viewport coordinate-space mismatch (all 3 rounds).** `read_page`
reported 1920×997 / 2560×1357 / 1440×706 while screenshots returned 1512×785 or
1568×768. One coordinate click missed outright. The tool never states which space
`computer` expects.

**4. CDP screenshot timeouts (4 occurrences).**
`Page.captureScreenshot timed out after 30000ms` — 30 s each, ~90 s of round 1's
430 s. Every one succeeded on a bare retry, so the renderer was not actually
frozen.

**5. Unlabeled form controls.** Both checkboxes rendered as `checkbox "on"` with no
label and **no checked-state**, in all three rounds — the one disambiguation each
S1 task explicitly warned about was the one the primary observation tool omitted.
Cost an extra `find` call every time.

**6. `find` truncated at 10 results without saying so** (R1) — would have produced
a TOC count wrong by 3.

**7. `find` reports closed dialogs as present** (R2) — no visibility filter; its
prose asserted a just-closed modal still existed.

**8. `get_page_text` omits the TOC region** (R3) while returning ~10k words of
references: "the tool that looks like the extraction tool couldn't complete the
extraction."

---

## Recurring friction — ChromeBridge

**1. S2 orphan-widget disambiguation** — see above. The only repeat offender.

**2. `find` gave no positional context** (fixed after R2). Five identically-named
"Launch demo modal" buttons were separable only by guessing that the lowest ref
came first in the DOM. Correct, but on no positive signal. Now emits
`section=` / `near=` / `y=`.

**3. `find` was viewport-bound** (fixed after R1). A semantically perfect query
returned 13 wrong answers for a button 200 px below the fold, then worked after a
manual scroll. Now reaches the whole page with `offscreen` flagging.

**4. Modal body text requires a screenshot or a full-page dump.** The *interactive*
listing scopes correctly to the dialog; the *text* extractor does not. `ref_id`
subtree scoping is accepted but not applied. Reported in R1 and R3 — **still open.**

**5. `get_page_text` discarded hierarchy** (fixed after R2). Flattened TOCs meant
counting top-level sections required reading pixel indentation off a screenshot;
one round would have answered 13 instead of 12. Now emits a depth-tagged
DOCUMENT OUTLINE, verified to give exactly 11 real sections on the WebSocket
article.

**6. No URL readback** (fixed after R2). "Did the search land on the right page"
was always an inference from page content. `get_url` now exposed.

**7. `find`'s scorer is loose.** Matched "Fields Medal" and "Duffield Memorial" for
the token "field" in R1/R2 (fixed after R2 — Duffield-class noise eliminated;
plural-prefix matches like Fields/field remain but now rank ~4× below the correct
hit).

**8. Legend advertised tool names that don't exist** (fixed after R1) —
`click_tool` / `enter_text_tool` / `fill_form_tool` / `analyze_screen` are not on
the MCP surface. A less careful agent would have called a nonexistent tool.

---

## What the fixes were worth


| Fix                                                 | Landed after    | Measured effect                                                                                                  |
| --------------------------------------------------- | --------------- | ---------------------------------------------------------------------------------------------------------------- |
| Flag-driven legend + real tool names                | R1              | Corpus-measured 18.2% total listing reduction (median 22.2%, range 5.6–46.7% over 22 sites)                      |
| `find` reaches below the fold                       | R1              | Unfindable button → #1 hit; S4 step 3: 5 calls → 2                                                               |
| Smooth-scroll trusted clicks (`behavior:"instant"`) | R1              | Below-fold click y=2384 (empty space) → y=669 (hits); latent bug that would have broken *every* below-fold click |
| Dead-duplicate detection                            | R1, re-fixed R2 | Fires and is correct; **no time saved** (trust problem)                                                          |
| `find` context (`section`/`near`/`y`)               | R2              | Five identical buttons separable by position                                                                     |
| `find` scorer word-awareness                        | R2              | Wikipedia query 5+ noisy hits → 3, correct ones ranked 1–2                                                       |
| `get_url`, document outline                         | R2              | Removes two inference steps; TOC answerable directly                                                             |
| Per-row hint compression                            | R2              | Included in the 18.2% figure                                                                                     |


---

## Token cost


| Round     | CIC         | CB                  |
| --------- | ----------- | ------------------- |
| R1        | 290,687     | 276,495             |
| R2        | 291,319     | 268,860             |
| R3        | 288,956     | 267,436             |
| **Total** | **870,962** | **812,791** (1.07×) |


Near-parity despite CB making ~30% fewer calls — CB's `read_page` payloads are
heavier per call. The payload compression work reduced listing size ~22% (median)
but the token totals here were measured *before* it could show up meaningfully at
this granularity. Token cost remains ChromeBridge's weakest number.

---

## Threats to validity

1. **n=3 per scenario.** Enough to separate signal from noise on S1/S3/S4/S5 (whose
  orderings never flip) and enough to show S2 is genuinely contested. Not enough
   for confidence intervals.
2. **Order counterbalancing is imperfect** with 3 rounds — R1 and R3 share an
  ordering.
3. **Live sites drift.** HN scores changed between runs; select2's double-init is a
  race that fired in some loads and not others; `ui.shadcn.com` broke mid-session.
4. **CIC's screenshot timeouts (4×, 30 s each) inflate its totals.** Excluding all
  of them, R1 becomes 1.42× rather than 1.79×. They recurred across rounds on an
   otherwise idle browser, so I count them as a real reliability property rather
   than noise — but the adjusted number is the fairer one for pure architecture
   comparison.
5. **The current build has never been benchmarked as a whole.** R3 predates the
  round-27 fixes (find scorer/context landed *during* R2→R3, but `get_url`,
   outline, and payload compression were verified after). A fourth round would
   likely widen the gap — that is a prediction, not a measurement.
6. **Both servers were driven by the same model family**, so "agent skill" is
  controlled, but an agent's *willingness to trust* a tool's output varies run to
   run and materially affected S2.
7. Self-reported tool counts were unreliable; harness counts are used throughout.

---

## Conclusions

1. **ChromeBridge is ~1.9× faster with ~12× fewer retries**, reproducibly, across
  three rounds and 30 runs.
2. **Its advantage is structural, not incidental.** `fill_form` collapses a
  5-field form + submit + verification into one call (vs 9). Modal awareness
   collapses a 210-element page to the 3 buttons that matter. These are design
   choices, not tuning.
3. **Its differentiator is trustworthy action results.** CIC's ref-clicks reported
  success while doing nothing 7 times; ChromeBridge's effect-detection and
   trusted-input escalation exist precisely to prevent that class. Round 27's
   audit found ChromeBridge has its own instances of the same disease (see
   `AUDIT_GENERALITY.md` findings 2, 3, 5) — fixing those matters more than any
   speed work.
4. **One reproducible loss (S2)** with a clear cause: emitting a verdict rather
  than evidence.
5. **Token cost is the remaining weakness** — near-parity, achieved with far fewer
  calls, meaning per-call payloads are heavy.

