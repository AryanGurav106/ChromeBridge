# Literature & landscape survey — second pass, 2026-11-19

Surveyed 2026-11-19. Window: work published or shipped since roughly **2026-11-10**,
weighted hard to recency. Scope: turning a live DOM into an agent-readable
observation, and making a recorded browser flow replay reliably.

Everything in `docs/research/SURVEY-2026-11.md` (2026-11-16) is **excluded** —
ComponentBench, WebPageBench, Read More/Think More, Region4Web, BreakingWeb,
WebChallenger, Affora, WebServ, CAP, MAG, NEXT-EVAL, MFS, the 12–14% rerun floor,
`arXiv:2610.39282`, Playwright 1.64's `page.webmcp`. Also excluded: everything in
`RESEARCH.md`'s 2026-05/08 bibliographies.

**The window is nine days.** A null result was the expected outcome and §3 is
where most of the searching landed. What did not come back null is mostly
**shipped software**, not papers.

---

## 0. Verification policy actually used

Stated precisely, because the last survey's §4 exists for this reason.

| source | how I read it |
|---|---|
| every arXiv item | the official `<summary>` from `export.arxiv.org/api/query?id_list=…`, i.e. the abstract as the author filed it — not a search-result snippet |
| WebArena-Pro (`2611.17955`) | **full text**, `arxiv.org/html/2611.17955v1` (400 KB), read for the specific question of per-step labels |
| WebMCP | **raw spec and explainer markdown** from `webmachinelearning/webmcp@main` (`index.bs`, `continuations-explainer.md`, `implementation-status.md`), plus the merged PR bodies |
| Playwright / playwright-mcp / browser-use | the GitHub **releases API JSON**, i.e. the maintainers' own release notes |
| W3C AccName | the repo commit list |

**No finding below came through a page-summarising fetch.** One `WebSearch` was
run (§3.4) and returned nothing that is used here.

Where a paper is a preprint with no venue, one author, or small n, that is
stated inline. Several items in this window are single-author cs.SE preprints
whose abstracts resist extraction; §4 names them and explains why no number from
them is imported.

---

## 1. Findings that could change this project

### 1.1 The WebMCP spec moved under `page_tools`' feet — four merges in nine days, one of them implemented in Blink

This is the highest-value item in the window: it is concrete, it is in shipped
code, and it bears on `page_tools` / `call_page_tool` (CLAUDE.md #26).

The last survey set a watch item with a trigger — *"the day `toolname` appears
in the spec proper"*. **That trigger has not fired** (the declarative API is
still explainer-only). A different set has.

Merged to `webmachinelearning/webmcp@main` in the window:

| PR | merged | what it does |
|---|---|---|
| **#254** | 2026-11-02 | adds **`outputSchema`** to `ModelContextTool` / `RegisteredTool` |
| **#380** | 2026-11-10 | tracks each `ModelContext`'s associated `Document` |
| **#382** | 2026-11-11 | **describes the traversable scope of `getTools()`** |
| **#381** | 2026-11-13 | updates the **continuations** explainer "to match the implementation in Blink" |

And `implementation-status.md` now states plainly what the last survey flagged as
**UNVERIFIED** ("inconsistent Chrome version claims (146 vs 149 vs 149–156)"):

> Chrome: **an Origin Trial is live in Chrome 149**; `about:flags#enable-webmcp-testing` for local development.
> Edge: Origin Trial live in **Edge 150**.
> Brave: supported in Leo AI chat **as of Brave 1.102.2 (expected 2027-01-05)**.
> ChatGPT Desktop: supported. Firefox and Safari: standards-positions only.

That resolves the flagged item from the spec repo's own file. (Noting, because
#70 measured it: the browser this project actually runs on is **Brave**, where
WebMCP arrives in January 2027.)

**Four consequences for our code, each checked against `extension/background.js`
lines 5744–5801 rather than assumed.**

**(a) `call_page_tool` resolves a tool by NAME ALONE, and the spec says that is
ambiguous.** The code is `raw.find((x) => x && x.name === name)`. The spec's own
residual-risk section says:

> "because `getTools()` aggregates tools across all descendant frames at the origin level, callers should inspect `RegisteredTool/origin` and `RegisteredTool/window` on each `RegisteredTool` to disambiguate tools when multiple subframes or origins expose tools with the same `name`."

Two same-origin subframes may each register `search`. We take the first in
traversal order and report success. That is a **silent wrong-target bind** — the
`FLOW-SILENT-BIND` class this project ranks as its worst outcome — and it is the
**one-concept-two-spellings** shape (PRINCIPLES 17): the submit picker refuses
and names candidates when several qualify (#24), and the *missing-tool* branch of
`call_page_tool` already names alternatives; the *ambiguous-tool* branch does not
exist. **`page_tools` already reports `origin`** — the gap is that
`call_page_tool` does not use it, and neither reports `window`.

**(b) `getTools()` is called with no options, so cross-origin tools are invisible
by our own omission.** Read from `index.bs`: a cross-origin frame needs three
independent gates — `allow="tools"` on the iframe, provider opt-in via
`registerTool(…, {exposedTo:[…]})`, and **consumer opt-in via
`getTools({fromOrigins:[…]})`** — and *"`getTools()` only returns tools from same
origin Documents by default."* So a widget that has mutually opted in is absent
from our listing. **This is a decision, not a bug**: passing `fromOrigins`
speculatively would opt us into untrusted tool-list pollution, which the spec's
threat model is explicitly about. It should be decided deliberately rather than
drifted into (PRINCIPLES 14's shape, one layer out).

**The good news in the same paragraph**, and it is worth stating because #94
spent an entry on exactly this class: `getTools()` returns tools *"exposed to
this document by active documents in the same traversable navigable"*, so **the
browser does the frame traversal for us**. Unlike `search_page`, `query_elements`,
`find` and `get_page_text` — all four of which #94 had to teach about frames —
`page_tools` is specified to see same-origin subframes from one top-document
call. That is a claim worth a live check, not an assumption.

**(c) `outputSchema` is new and unread.** The code parses `inputSchema` (and
handles the JSON-string form); `outputSchema` is now a sibling member, and
`registerTool` rejects when *either* schema is invalid. It tells the agent the
shape of what `call_page_tool` will return. One-line listing addition.

**(d) Continuations make `navigated: res === null` a possible FALSE TERMINAL
REPORT.** This is the sharpest of the four. Read from `continuations-explainer.md`:

> "When the tool requests a token, this is a signal to the agent that the tool has not completed execution. The value returned by the original execute callback (or its rejection) is **ignored, and is not shown to the agent**. The browser waits until the token is redeemed and the callback passed to `resumeTool()` settles, and shows the agent the output of that callback as the result of the tool call. **This blocks the agent** until the continued tool call completes."

The motivating case is ours exactly: *"If a site executes a server request that
navigates the document, the original tool request is ended and the agent does not
receive a success signal or tool output."* Tokens are same-origin, same-tab,
redeemable across **any number of navigations**, expiring after **30 seconds** in
Chromium, one per tool call.

Our handling is `navigated: res === null || res === undefined`, with the comment
*"executeTool resolves null on navigation, which is a real outcome."* Under
continuations that outcome is no longer terminal — the call is mid-flight and
will produce real output we never see, while we report "navigated, refs stale".

**Stated as an inference, not a measurement.** I have not run this: it needs
Chrome 149 with the origin trial or `about:flags#enable-webmcp-testing`, and a
page that calls `requestToken()`. What is *read from the source* is (i) the
browser blocks and substitutes the continuation's output, (ii) tool calls may
span hard navigations, (iii) 30s expiry. What is *inferred* is how our MAIN-world
`chrome.scripting` injection behaves when its document is torn down mid-await.
That inference is the MEASURE FIRST item in §6.

**Cost to adopt:** (a) and (c) are small and local. (b) is a policy decision with
no code until it is made. (d) needs a live check before any code.

---

### 1.2 Re-reading the observation is where the tokens actually go — and it weakens a corollary of #38

**Re-Reading Is Not Free: Token Traces and Cache-Aware Energy Estimation for LLM
Agents in Software Engineering.** Vartziotis, Peranidze, Kosteli, Sarikayak,
Dasoulas, Keckeisen, Kotsopoulos, Dominici. `arXiv:2611.20873`, **2026-11-16**,
cs.SE, 21 pages, 8 authors. **v1 preprint, no venue listed.**

*What it measured:* **nearly one billion tokens across 42 sessions and 752 task
episodes over ten weeks of real-world AI-assisted software development.**

| | |
|---|---|
| cached-context reads, share of all API-reported tokens | **94.8%** |
| uncached input | 0.017% |
| cached tokens read per generated token | **~260** |
| context growth over a session / within a task | 5.3× / 1.4× |
| cache-aware vs output-based energy estimate | ~250 kWh vs ~10 kWh (**25×**) |
| effect of starting each task from a fresh context | **−60%** |
| **subagent token undercount in parent-session logs** | **factor of ten** |

**Why this matters here, at full strength.** PRINCIPLES 19 says *"Halving the
payload saves ~10% of prefill. Halving the round trips saves ~50% of
everything."* #38 derived that by differencing timed batches, and it is a
statement about **wall clock per call**. This paper measures **token volume
across a session** and finds the dominant term is re-reading accumulated context.

Those are different quantities and the paper does not contradict #38. What it
does is price a term #38's model has no slot for: **an observation emitted at
step 3 of a 20-step session is re-read on every later turn.** The listing's cost
is multiplicative in remaining turns, not a one-off prefill. "~10% of one call"
and "~10% of one call × every subsequent turn" are different arguments for how
much the representation work was worth.

**And it cuts both ways, which is why this is a weakening and not a
falsification:** fewer turns means fewer re-reads, so #38's *conclusion* —
optimise turns — is reinforced. What moves is the standing dismissal of payload.

**The second finding is about this project's own measurement practice, and it is
sharper.** *"Parent-session logs report only a subagent's final internal call,
undercounting delegated tokens by a factor of ten… token-volume studies are
fully exposed to it."* This project mines subagent transcripts (#45 mined 229
runs; `tools/bench_turns/` scores from transcripts; `ORCHESTRATION.md` is about
delegating). Our exposure is **limited but real**: #38's decomposition is timing,
#45's figures are TURN counts, and the corpus numbers come from the collector —
none of those are parent-log token volumes. But **`OPEN.md` item 15 — "What our
31 tool schemas cost at session start `MEASURE FIRST`" — is exactly a
token-volume question**, and if it is ever measured from session logs across
subagents it is exposed to a 10× undercount. That warning belongs in the item
before anyone runs it.

**Caveats, which are large.** v1 preprint, no venue. The workload is
software development, not browser automation, so the context-growth shape may
differ. The authors say plainly *"neither estimator has been validated on long
cached contexts"*, so the **energy** headline is a modelled estimate. The
**token** figures are API-reported counts and are the part I would lean on.

---

### 1.3 WebArena-Pro: the first substrate whose harness already contains Claude Code

**WebArena-Pro: A Heterogeneous, Multimodal, Reproducible Benchmark for Web
Agents.** Kerboua, Pesaran Zadeh, Lù, Qi, Miller, Song, Tian, Kang, Choi, Nouri,
Gueguen, Boglioni et al. (22 authors; Mila / McGill). `arXiv:2611.17955`,
**2026-11-13**. **Accepted at NeurIPS 2026 D&B Track.**
`https://webarena-pro.github.io`

*Read from the full HTML, not the abstract*, because the decisive question is
per-step labels.

| | |
|---|---|
| tasks / applications / domains | **300 / 20 self-hosted / 6** |
| applications modelled on | Notion, Slack, Spotify, Figma, Airbnb (Table 2 lists all 20) |
| observation space | **accessibility tree** + vision + audio/video, via `transcribe()` / `extract_frames()` / `watch()` / `listen()` |
| scoring | *"Success requires a final reward of 1"* — **end-of-task only** |
| reproducibility | per-task seeded container state, task isolation, parallel evaluation |
| best agents | **Claude Code with Claude Opus 5.5 at 62.3%**, tied with Codex + GPT 6.1 Sol; OpenCode + Kimi 3.1 Pro 60.7% |
| best GenericAgent | Gemini 3.1 Pro omni / Gemma4 31B, **30.3%** |

**Why this is the best route yet for `OPEN.md` item 11, better than
ComponentBench for this specific question.** ComponentBench's advantage is hidden
target values and a programmatic oracle. WebArena-Pro's advantage is that
**the harness already evaluates Claude Code**, which is this project's actual
runtime. That turns the experiment from "port ChromeBridge into a BrowserGym
observation space and hope the comparison is fair" into "run the same agent, the
same model, the same tasks, and swap only the browser tool surface" — which is
the cleanest form of the question #75 could not ask and #27's `format` A/B could
not answer.

Three further properties make it usable: **it is not saturated** (62.3% leaves
headroom, where this project's own live evals saturate at 100% correctness
because both arms are the same model — #41); the applications are the
framework-heavy SPA families this project was built against (fix #1 exists
because Radix gates on `pointerdown`); and self-hosting means the per-origin gate
is granted once in a throwaway profile, exactly as `tools/run_flows.py` already
does.

**What it does NOT do, and this confirms a standing belief rather than
overturning it: there are no per-step element labels.** Scoring is final-reward;
Appendix B.2 adds a Partial Completion Score, which is not element ground truth.
So the conjunction `MEASUREMENT.md` §6 says does not exist — live pages + per-step
element labels + intact step values + an agent loop — **still does not exist**,
and **Mind2Web remains the only out-of-sample element-recall ruler**. That
sentence stands as written.

**Cost to adopt:** one arm. The confound `OPEN.md` item 11 already names applies
unchanged — pin the toolset and report the fallback rate, or an agent reaching the
state via `javascript_tool` measures Claude's ingenuity rather than the listing.

---

### 1.4 Playwright MCP shipped the two things this project documented as a settled choice and a known limitation

Read from the `microsoft/playwright-mcp` releases API.

**v0.0.85, 2026-11-09 — "Keep the browser in the background".** Their own words:

> "connecting through the extension **activated the tab and focused the browser window, taking the screen from the app you were working in**. Pass `--background` alongside `--extension` … to leave the connected tab inactive and its window unfocused… **Chrome throttles timers and animation frames in background tabs.**"

That is **PRINCIPLES 21** and fix #12, arrived at independently by the reference
browser-automation team — and shipped as an **opt-in flag**, where this project
made it the default and recorded why ("that was tried, it works, and it drags the
user out of their work on every click, defeating the whole point"). Their
throttling note is the same fact #76 and #84 hit live when an injected
`setInterval` ticker stopped dead in the agent's hidden tab.

**Nothing to adopt. It is the strongest external validation of a settled choice
in this window**, and it is worth having because the choice costs something
(fix #12's `ensureInputReady` exists only because of it).

**v0.0.86, 2026-11-18 — a shipped multi-client model.** Tab groups resumable per
client, a **Manage clients** page listing connected clients and their tabs with
controls to disconnect and **rotate the token**, `--session-name` / `--session-color`
to tell clients apart in one browser, **each tab has exactly one owner** with
drag-to-transfer, and *"browser-wide changes such as setting or clearing cookies
and granting permissions are now refused."*

This project documents the opposite state as a known limitation (#17, #45, and
the CLAUDE.md port-span section): *"One Chrome, one extension, one socket… the
extension's sweep stops at the first server that answers, so session two gets a
live bridge nobody talks to."* A comparable extension-based product has now
shipped a reference design for it: ownership is **per tab**, not per browser, and
browser-wide authority is refused outright rather than shared.

**Cost to adopt: large, and not proposed.** It is a bridge and consent-model
change. It is recorded so that the limitation's entry can stop describing the
problem as open-ended and point at a shipped answer.

Also from their notes, relevant and smaller: **v0.0.83** fixed *"WebMCP tools no
longer stay bound to a stale tab or frame"* — the same failure family as §1.1(a),
hit in production by someone else. **v0.0.82** made page tools **first-class MCP
tools** (`webmcp_<tool>`, with the page's own schema and annotations, following
the current tab, with `tools/list_changed` notifications), which is a different
design from our `page_tools` + `call_page_tool` pair and worth knowing exists.

---

### 1.5 TESSARA — the nearest published comparator to the flow recorder, and the last survey missed it

**Step-Aligned Script Generation with Verification and Recovery for Web
Automation Testing.** Dhulipala, Rong, Yadavally, Nguyen. `arXiv:2610.25601`,
2026-10-19, cs.SE, 12 pages, 4 authors. **Outside the window** (one month old),
included because it is the closest system in the literature to a feature this
project has eleven CLAUDE.md entries about, and it appears in neither
`SURVEY-2026-11.md` nor `FLOW_RECORDER_PLAN.md`. Verified absent:
`grep -ri tessara` returns nothing.

It opens with this project's own framing, independently:

> "task completion is not the same as producing a test-ware artifact — code that is executable, **replay-able from a reset state**, inspectable by developers, and **tied to an oracle**."

"Replay-able from a reset state" is #54's fixture-reset finding and #101's "a
reset that leaves you signed in is not a reset", in someone else's abstract.

What TESSARA has: NL intent → Playwright scripts with **goal-state assertions**,
**step-level provenance** linking each step to its code fragment, *selector
evidence*, execution outcome and **repair history**; **selective regeneration of
failing suffixes**; **reversibility-aware backtracking that avoids undoing likely
commit points (e.g. form submissions)**; and a three-level verification pipeline
(syntactic, execution, semantic/oracle).

**What it has that we do not**, stated as the useful half:
- **Repair history as a first-class field.** Our `review` line (#72/#95) records
  what was true at record time; there is no record of what has been rebound
  since, and `record_flow(action="patch")` (#65) consumes a proposal without
  leaving a trace in the file.
- **Selective regeneration of a failing suffix.** Our runner pauses and hands
  back candidates (#49), which is the safer design and a strictly smaller one.

**What we have that it does not**, and #83's claim survives with one correction:
preconditions, and postconditions **promoted from the agent's own observations**.
TESSARA's assertions are **goal-state** assertions derived from the stated intent —
auto-generated, but from the task rather than from what was observed. So #83's
*"Nothing in the space does preconditions, promoted postconditions or an ordinal
witness"* holds, and the precise form is: nothing promotes observations;
TESSARA does generate assertions, from the goal.

**Not adoptable as measured.** The reported gains are whole-system against
baselines and VLMs-as-script-generators; nothing isolates the contribution of
provenance or reversibility-aware backtracking, so there is no number to compare
against ours.

---

### 1.6 The mature alternative to the descriptor ladder exists, is a year old, and its metric is not our metric

**Web Element Relocalization in Evolving Web Applications: A Comparative Analysis
and Extension Study.** Kluge, Stocco. `arXiv:2505.16424`, published 2025-05-22,
**v2 2025-12-01**, cs.SE. **A year old and well outside the window** — included
because `OPEN.md` item 2 is this project's #1 open problem and this is the
reference comparative study of the technique class it chose not to use. Verified
absent from the repo: `grep -ri similo` returns nothing.

It replicates **Similo** and **VON Similo** — similarity scoring over many element
properties to relocate an element after the DOM changes — finds VON Similo
produces **more false positives** than Similo, improves Similo by **5.62%** via
parameter optimisation, builds a benchmark **23× larger** than the original, and
proposes **HybridSimilo**, which *"locates 98.8% of elements with broken locators
in realistic testing scenarios."*

**Do not place 98.8% beside our numbers.** This is `MEASUREMENT.md` §4 in its
purest form: Similo-family techniques are **scorers** — they always return a best
candidate — while `descriptor.py` **refuses** when a target cannot be pinned to
exactly one element (PRINCIPLES 7, #49). "Located" and `CORRECT / REFUSED / WRONG`
are not the same partition, and a Similo "location" can be a confident mis-bind.
The comparable figure would be their false-positive rate, which the abstract gives
only qualitatively.

**What it is actually worth to us.** `OPEN.md` item 2 ends *"What would close it:
a declared per-member discriminator the collector does not currently emit"*, and
records geometry as refused because it drifts. Similo's answer to the same problem
is to **score across many weak properties including geometry**, accepting that no
single one is reliable. That is a coherent alternative architecture to the ladder,
it has a published benchmark, and this project has never priced it. It is not
proposed — a scorer that never refuses is the design #49 rejected on purpose — but
"we considered scoring and rejected it for reason X" is a stronger position than
not knowing the literature exists.

A weaker cousin, for completeness: **`arXiv:2603.20358`** (single author,
2026-03-20) proposes a ten-tier priority-ranked locator hierarchy —
`get_by_role` → `data-testid` → ARIA labels → **CSS class fragments** → visible
text. Validated on **one website**, 31 test combinations. Its tiers include two
keys this project measured and rejected (#61: `data-testid` at **2.5%** coverage,
`id` at 6.8%; class down-weighted). Evidence too thin to act on, noted so the
convergence-and-divergence is on record.

---

### 1.7 Two in-window papers say a tool's own annotation is not evidence — and `readOnlyHint` is a declared signal we rely on

Both are single-author cs.SE preprints with no venue; numbers are reported as
theirs, and the *direction* is what I would carry, not the figures.

**Can You Undo It? Reversibility Classes for AI Agent Actions.** Waghmare, Sufi.
`arXiv:2611.22075`, **2026-11-17**, 2 authors. A declared five-level reversibility
vocabulary with argument-sensitive rules and conservative defaults, over **536
tools across 20 MCP servers**. The line that matters here:

> "**native annotation mapping differs from draft registry labels for 118 of 481 comparable tools**"

i.e. a tool's own MCP annotations disagree with careful review for roughly a
quarter of tools. The paper's own limits are unusually well stated: *"It does not
establish registry-wide accuracy, reduced production harm or general recovery
reliability,"* and its single AI-assisted reviewer agreeing on 148 ratings is
explicitly *"not independent agreement."*

**Checking Retry Transparency in Agent Tools.** Li. `arXiv:2611.23307`,
**2026-11-11**, 1 author, 15 pages. Tests recovery guarantees behind a tool's
local idempotence claim over 6 MCP components from 4 repositories — *"Real tests
include file, graph, Git-index, document-update and **browser bindings**."* Its
closing sentence is the transferable one:

> "The contribution is an executable recovery-contract workflow that makes effect granularity, logical identity and completion assumptions testable **rather than inheriting them from a tool annotation**."

**Why this lands on us.** #26 adopted
`annotations.readOnlyHint === false` as *"the declared destructiveness signal #24
deleted the submit wordlists for lacking"* — the page saying so itself, with no
vocabulary involved. That was the right move and these do not undo it: the
alternative was a wordlist, which is worse. What they add is that a **declared
annotation is a claim, not a measurement**, which is PRINCIPLES 18 applied to
someone else's declaration instead of our own comment.

The practical consequence is small and specific: `call_page_tool` returns
`readOnly: !!(t.annotations && t.annotations.readOnlyHint)` and `page_tools`
renders `[read-only]` vs `[CHANGES STATE]`. Both are **the page's claim**, and
the output should say so — `[declared read-only]` costs two words and is the
difference between reporting a fact and reporting an assertion. That is the same
fix #23 applied to `data-testid` and #41 to name provenance: keep using it, and
say where it came from.

A third, adjacent: **Idempotency Is Not Recovery: A Fault-Injection Study of
Language-Model Agent Tool Actions.** Xu. `arXiv:2611.23353`, **2026-11-17**,
1 author. Its distinction is the useful part — **duplicate suppression is not
recovery** — and the measured shape is ours: disabling reconciliation left
*"100/100 known post-effect crash outcomes **ambiguous** despite no observed
duplicates."* That is #56's `NOT DELIVERED` vs *unknown* split and #77's "I could
not see is not there is nothing to see", in a different system. It is the
unreported case that `OPEN.md` item 9 (three unreproducible 30s+ stalls) sits
next to: a stall inside `fill_form(submit=True)` is precisely *"the action may
already have changed an external system without confirmation."* Conceptual
import only; the runtime is bespoke and the numbers are synthetic fault injection.

---

### 1.8 Benchmark demonstrations prefer labelled elements — a selection effect inside the ruler

**Trained on What Screen Readers Cannot Read: Accessibility Debt in the GUI
Corpora Behind Computer-Use Agents.** Kraishan, Jitkajornwanich.
`arXiv:2611.16107`, **2026-11-11**, 2 authors. **Accepted at AISSA 2026**
(Dec 2026). **Android, not web** — applicability is by analogy, and that is stated
rather than smoothed over.

Across **17,373,614 interface elements** in Rico (2017) and AndroidControl (2024):
content-description coverage **17.74%** vs **57.27%**; input controls are the
least-labelled role in both (**2.20%** and **27.21%**); older-corpus descriptions
are **five times** more likely to be placeholders. The authors are careful that
the 39.5-point gap *"does not measure change over time"* — the corpora differ in
app selection, capture method and platform.

**The transferable finding is the last one.** Resolving 26,205 task actions to the
elements they touched:

> "among tappable graphics with no text, **demonstrations operate elements described 9.0 points more often than the others on the screens they visit**, about 3.5 points of it from the choice of element within a screen. **That is a selection effect inside the benchmark.**"

Benchmark demonstrations preferentially touch **well-labelled** elements. Any
recall or findability number measured on such a corpus therefore overstates
performance on the unlabelled population — which is exactly the population
`(unlabeled)`, `near=`, `synthLabel` and #37's icon work exist for.

**How it lands here.** It is the same shape as #73's finding that Mind2Web
snapshots carry no scripts and no CSS and so switch off two of eight admitting
signals — PRINCIPLES 9 again, from an independent direction. It does **not**
touch `lost_identities` (which is derived from the live DOM, not from
demonstrations) or `measure_findability` (which probes every printed identity,
not a demonstrated subset). It **does** touch Mind2Web recall, where the targets
are human demonstrations: if the same selection effect holds there, our ~96%
is measured on a target population biased toward named elements.

Two-coder reliability κ = 0.91 / 0.96, full pipeline released. Worth a sentence
in `MEASUREMENT.md` §6's debts; not worth a measurement, because the obvious
check — compare our recall on named vs unnamed Mind2Web targets — is cheap and
belongs in §6 rather than here.

---

### 1.9 EVIDENT: the metric shape for "did the agent actually observe it", which is the TEXT half of sufficiency

**EVIDENT: Evaluating Evidence Grounding in GUI Agents.** Nam, Cho, Kim, Song,
Yoo, Kim, Lim. `arXiv:2611.20488`, **2026-11-16**, 7 authors, 36 pages.
**Accepted to EACL 2027 Findings.**

220 real-world **English and Korean** tasks, each with human-curated evidence
metadata specifying what must be verified, and three metrics separating
**TSR** (outcome success), **ESR** (required evidence *observed*) and **GSR**
(claim-level evidence *support*). Headline: substantial gaps between surface and
evidence-grounded success, i.e. *"current evaluations can overestimate agent
reliability."*

**Why it is here rather than in §2.** `OPEN.md` item 12 — the TEXT half of
sufficiency — asks whether `get_page_text` / `search_page` / `query_elements`
carry what a task needs, and `SUFFICIENCY.md` §10 measures it through the flow
recorder because a static page load cannot tell "the text surface failed to carry
it" from "the value did not exist yet". **ESR is a cleaner instrument for the same
question**: it asks whether the required evidence was *observed in the
trajectory*, which is decidable from a transcript and does not need the answer to
have existed at load time.

That is a metric shape worth porting, in the same way `MEASUREMENT.md` ports MFS
coverage rather than importing its labels. It is also the only item in this
window whose corpus is **not English-only**, which matters for a project with 36
languages in its own generality corpus.

---

## 2. Findings that confirm existing choices

**2.1 Pre-action verification plus post-action outcome perception, independently
derived.** *UIAnchor*, Zhou et al., `arXiv:2611.20753`, 2026-11-16, 9 authors,
cs.HC, no venue. Mobile. Its in-the-wild failure analysis names **two** dominant
bottlenecks: *"agents often miss or misread actionable UI elements, and they
**execute actions without verifying target correctness or outcomes**."* Their
answer is a meta-controller doing pre-action verification, post-action outcome
perception, per-step state tracking and targeted recovery. That is `OPEN.md`
item 1 (the observe→act gap) and #56's delivery probe, designed from the same
failure. Reported +31.5% over GPT-4o on their hardest tier — a **whole-system**
number with no ablation isolating the verification, so there is nothing to price
against our own measurement (0 extra round trips, 0.5–1.4ms to stamp, 0.29%
false-positive rate on 36 settled sites).

**2.2 A portable, inspectable workflow artefact executed under user-held
authority.** *WebAgents*, Fenoglio, Gjoreski, Langheinrich, Chari, Raskar,
`arXiv:2611.21978`, 2026-11-16. **Presented at IEEE CIC 2026.** A signed
`agent.pkg` carrying portable workflows, skills and schemas, bound at run time to
*"user-controlled models, tools, permissions, and budgets"*, with execution
authority retained in the user's runtime. That is the shape of a `.flow.json` plus
the per-origin gate, argued from the distribution side. **One idea we do not
have: signing.** A flow file is committed plaintext and nothing attests who
recorded it or that it has not been edited — which matters more now that
`record_flow(action="patch")` writes to it. Low urgency, recorded rather than
proposed. ("blocks all 716 injected contract violations while accepting all 295
matched benign controls" is their own controlled suite, not an independent one.)

**2.3 No AccName errata, and no new AccName work.** `w3c/accname` has **0 commits
since 2026-09-01**, and a search for 2026 work on accessible-name computation
returns nothing applicable. The 0.9766 per-site median against Chrome's AX tree
(#108) is not challenged by anything published, and the two disagreement classes
#93/#34 left deliberately open — `chrome-superset`, and title-beating-content —
have no new spec guidance behind them. **This is a clean null for hunting target
3 and it is worth stating as one**: the only moving target in that area is
Chrome's implementation, which `audit_name_correctness.py` already tracks
directly.

---

## 3. Areas searched where nothing new exists — stated explicitly

### 3.1 Page readiness / settle for agents: nothing new in the window

Searched the arXiv API for readiness, settling, staleness and synchronisation
crossed with agents, browsers and GUIs; and for `cat:cs.SE` in the window
filtered for web/UI/test terms. **The only relevant item is `arXiv:2610.39282`,
which this project already cites** (the wait-rule study behind #70's network-idle
reasoning). Nothing published in the window ablates a readiness signal against
task success, which is the specific gap `SURVEY-2026-11.md` §3.2 recorded.

Two adjacent items, neither answering it: `arXiv:2606.00408` *"Masking Stale
Observations Helps Search Agents — Until It Doesn't: A Regime Map and Its
Mechanism"* (2026-05, search agents, not page readiness) and `arXiv:2609.16732v2`
(updated **2026-11-06**), discussed in §5 as a falsification candidate rather
than a readiness result.

**The project's belief stands: no published evidence either way on whether
showing a model a settling signal improves task success.**

### 3.2 Record/replay and locator stability: nothing in the window

The window contains no new work on element relocalisation, locator repair or
record/replay for web agents. The nearest items are §1.5 (one month old) and §1.6
(a year old), both of which the previous survey missed and neither of which is
new. The `w3c/accname`-style null applies here too: `arXiv:2305.08592`
(time-based repair for asynchronous-wait flaky tests) remains the most recent
work on wait-flakiness repair, and it is from 2023.

**`OPEN.md` item 2's 52.6% is not addressed by anything published in this
window**, and the only architectural alternative is the scoring family in §1.6.

### 3.3 A heuristic-free "is this a control?" method: still does not exist

Re-checked, since it is the project's core constraint. Nothing in the window
proposes an admission rule that is not the same declaration set everyone else
uses. WebArena-Pro (§1.3) takes existence from the **accessibility tree**, which
is the same move browser-use's current `ax.py` makes — further evidence that the
A/B framing #78 retired is correctly retired, and that AX-tree-as-existence is
now the field default.

### 3.4 Non-academic: nothing in the window

One `WebSearch` (extended mode) for shipped news on agent-readable DOM
representation in November 2026 returned only general explainers, the oldest
eight months old and the newest ~19 days; the only concrete item was Chrome's
June 2026 Lighthouse "Agentic Browsing" audits, which `SURVEY-2026-11.md` §3.2
already flags as UNVERIFIED practitioner material. Nothing used.

The shipped changes that *did* matter were found by reading release APIs
directly, not by searching: Playwright 1.65.0/1.65.1 (Bun, reporters, test locks
— **nothing on snapshots, refs or readiness**), playwright-mcp v0.0.85/0.0.86
(§1.4), browser-use 1.0.3–1.0.6 (§5).

---

## 4. Checked, did not pay out — and one pattern worth naming

**A cluster of single-author cs.SE preprints in this window whose abstracts
resist extraction.** `arXiv:2611.22835` ("When Passing Checks Do Not Establish
Completion"), `arXiv:2611.22991`, `arXiv:2611.23335` and others share a
distinctive style: no venue, one author, dense nominalised prose, and statistics
whose referents cannot be recovered from the abstract (*"all 122 delivered labels
in a held-out receipt-supply study are correct"*). An undefined proper noun
("Jev") recurs across several otherwise unrelated titles by different authors.

I did not investigate further and make no accusation. The operational decision is
the same either way: **no number from that cluster is imported here.**
`arXiv:2611.22835`'s title alone is tantalising — *passing checks do not establish
completion* is #57/#68/#95's hollow-and-unproven problem in one phrase — and I
could not extract a usable claim from it. Recorded so nobody re-reads it hoping
for more. `arXiv:2611.23307` and `arXiv:2611.23353` are in the same cluster by
these criteria and are reported in §1.7 **for their distinctions, not their
numbers**, which is the strongest form in which they can be used.

**Other items opened and set aside:**

- `arXiv:2610.34634` **AgentProofBench** (reusable verifiers for web agents) —
  conceptually adjacent to flow postconditions; abstract statistics opaque, no
  venue. Not imported.
- `arXiv:2611.23946` (*How Complete Must an Environment Be to Train a Capable GUI
  Agent?*) — about **training** environments and mobile. We do not train.
- `arXiv:2611.18514` (*Can Mechanistic Interpretability Help Explain LLM Agent
  Failures? A Case Study on Web Element Hallucination*, 2026-11-13, 4 authors,
  Qwen2.5-7B) — one line is relevant and no more: *"the probe direction is
  sensitive to prompt formatting, losing much of its steering effect after a minor
  change to **how actions are represented**."* Evidence that representation
  changes an internal mechanism, not only accuracy. Nothing actionable; a 7B model
  and an interpretability method, not an observation-format result.
- `arXiv:2611.18284` (*Clean Tickets, Wrong Orders*) — the "silent error" framing
  matches this project's vocabulary exactly and the content does not: it is a 4-page
  demo of an in-browser 0.8B order parser. Coincidence, not a finding.
- `arXiv:2611.24491`, `arXiv:2611.22971`, `arXiv:2611.16744`, `arXiv:2611.22223`,
  `arXiv:2611.11971` — prompt injection, privacy and agent-security papers in the
  window. Out of scope for this brief; `OPEN.md` item 1 already carries the
  observe→act security citation it needs.

---

## 5. What falsifies or weakens a settled claim

Ranked by how much it moves.

**(a) WEAKENED — "the lever is turns, not tokens" (PRINCIPLES 19 / #38), in its
*corollary*, not its claim.** `arXiv:2611.20873` measures **94.8% of all
API-reported tokens as cached-context re-reads, ~260 per generated token**, on a
billion-token real workload. #38's decomposition is per-call wall clock and is
untouched. What is weakened is the dismissal that follows from it: a listing is
re-read on every subsequent turn, so payload is multiplicative in remaining
turns rather than a one-off ~10% of prefill. **The conclusion — optimise turns —
is reinforced**, because fewer turns means fewer re-reads. See §1.2.

**(b) WEAKENED — relying on `readOnlyHint` as *the* declared destructiveness
signal (#26).** Two in-window preprints independently argue a tool's own
annotation is a claim, not a measurement, with one reporting native annotations
disagreeing with review for **118 of 481** tools. The adoption was still right
(the alternative was a wordlist), and the cheap correction is to **attribute**
it — `[declared read-only]` — rather than to stop using it. See §1.7.

**(c) NARROWED, NOT FALSIFIED — "no benchmark offers live pages + per-step
element labels + intact step values + an agent loop."** WebArena-Pro adds a
reproducible, 20-application, Claude-Code-harnessed substrate with intact step
values — and scores **final reward only**. The conjunction still fails on the
same leg, so `MEASUREMENT.md` §6 stands. What changes is that the *success* half
now has a better route than ComponentBench for our specific question. See §1.3.

**(d) FLAGGED, NOT MEASURED — "the DOM/declaration channel is theme-invariant and
therefore the safer channel" (#79, and `SURVEY-2026-11.md` §2.4).**
`arXiv:2609.16732v2` (updated **2026-11-06**, cs.CR, mobile) exploits the gap
between *human-visible* and *agent-observable* interfaces: display-occluded
regions and low-contrast text mislead screenshot agents at **67.2–77.4%**, and of
**195 participants, none spontaneously noticed** the low-contrast text. That is
the pixel channel. **Our channel has the same class of exposure and nobody has
measured it adversarially**: #78 measured `opacity:0` content at 175 elements
across 21 of 96 sites and recorded DON'T BUILD on *frequency* grounds (0 of 175
declare an ARIA role; 0 identities lost), which is a benign-web measurement, not
an adversarial one. The theme-invariance result says the DOM channel does not read
*colour*; it does not say the DOM channel cannot carry content a human cannot
see. Those are different claims and #79's should not be stretched into the
second.

**(e) ADDS AN AXIS — browser-use 1.0.4, 2026-11-13.** Their note, measured on
their own 200-task bench: batching screenshot pruning so it stops rewriting
earlier messages gave *"same score (76.1 vs 76.0), model cost per task **$0.208
vs $0.434**"*, after one 705-step task read **27.8M input tokens, 1.6M from
cache**. Vendor-reported and on their own harness, so weak evidence — but it is
the same mechanism as (a) from the engineering side, and **cache-stability of the
observation across turns is an axis no ruler in this repo measures.** It does not
apply to ChromeBridge directly (we are a tool provider; Claude Code owns the
history), which is itself worth knowing.

Also from their releases, a divergence rather than a weakening: **1.0.5
(2026-11-14) ships an LLM judge on every run**, filling `result.judgement` with
`success` / `failure_reason` / `gotchas` / `prompt_injection_detected`. This
project holds no LLM key by architecture, so that path is closed to us — noted
because it is the direction the nearest comparable product is moving.

**Nothing in this window falsifies:** the 7.15× AX-tree token cost, the 33.6×
`cleaned_html` cost, the 84.5%-junk decomposition of browser-use's old admission
rule (whose *framing* #78 already retired), existence-by-declaration, or the
12–14% rerun noise floor.

---

## 6. Candidates for `docs/OPEN.md`

Proposed, not applied. Each states what would decide it.

**M1. `call_page_tool` picks the first tool of a given name `MEASURE FIRST` →
actually `FIX`, once the shape is confirmed.** The spec says `getTools()`
aggregates across descendant frames and that callers must disambiguate by
`origin` **and** `window`. Two same-origin subframes registering `search` is a
silent wrong-target bind today. *Decide it by:* a two-frame fixture registering
the same tool name in both, driven through the real router. *The fix is the shape
#24 already uses* — refuse and name the candidates — plus accepting an `origin`
argument to disambiguate. Proposed diff is confined to `_callPageToolPage` and
the tool's schema; **not applied, per brief.**

**M2. Does a WebMCP continuation make our `navigated` report false? `MEASURE
FIRST`.** §1.1(d). *Decide it by:* Chrome 149 with
`about:flags#enable-webmcp-testing`, a page whose tool calls
`options.invocation.requestToken()` and redeems it after a navigation, driven
through `call_page_tool`. Three outcomes are distinguishable: we report
`navigated` (false terminal — the defect), we hang to the bridge timeout (also
wrong, and interacts with the 30s expiry), or the browser's blocking behaviour
carries our await through (no defect). **Do not change code before this runs** —
the whole point is that the behaviour is not derivable from the spec text.

**M3. Does `page_tools` see a same-origin subframe's tools from one top-document
call? `MEASURE FIRST`.** The spec says yes. #94's whole entry exists because four
other tools did not, and the belief that they did went unchecked for months.
Cheap: one fixture, one call. If yes, it is worth recording in `OPEN.md` as a
*measured* difference from the four tools #94 had to fix, rather than an assumed
one.

**M4. Is Mind2Web recall measured on a target population biased toward named
elements? `MEASURE FIRST`.** §1.8 measures exactly this selection effect on
Android. *Decide it by:* splitting our 186 Mind2Web actions on whether the gold
target carries an accessible name and comparing recall across the split. The
data is already local (`temp/mind2web/`), the ruler already exists
(`bench_mind2web.py`), and the answer is one run. If recall is materially lower
on unnamed targets, the ~96% needs that split beside it the way #93's pooled
figure needs its class table.

**M5. WebArena-Pro as the success substrate for item 11 `MEASURE FIRST`.**
§1.3. Its advantage over ComponentBench for *this* question is that the harness
already evaluates Claude Code, so the arm swaps the browser tool surface and
nothing else. Verify at source first, exactly as #78/#79 did for WebPageBench:
the paper is not the artefact, and the per-step-label absence I read from the HTML
should be confirmed against the released code before anyone plans around it.

**M6. Note the 10× subagent token undercount inside item 15.** Not a new item —
a warning to attach to the existing one. If "what our 31 tool schemas cost at
session start" is ever measured from parent-session logs across subagents,
`arXiv:2611.20873` says that number is exposed to a factor-of-ten undercount.

**M7. Attribute `readOnlyHint` in the output.** §1.7(b). `[declared read-only]`
rather than `[read-only]`, the same correction #23 applied to `data-testid` and
#41 to name provenance. Two words; no measurement needed; it changes a reported
assertion into a reported fact.

---

## 7. Bibliography

Ordered by relevance to this project. **(W)** = inside the 2026-11-10 window.

1. **WebMCP specification repository.** `github.com/webmachinelearning/webmcp@main`
   — `index.bs`, `continuations-explainer.md`, `implementation-status.md`;
   PRs #254 (2026-11-02), #380 (2026-11-10), **#382 (2026-11-11)**, #381
   (2026-11-13). **(W)** *States:* `getTools()` returns tools exposed by active
   documents in the same traversable navigable, same-origin by default, with
   cross-origin behind a three-gate opt-in; callers must disambiguate same-named
   tools by `origin` and `window`; `outputSchema` is a new member; continuation
   tokens are implemented in Blink (same-origin, same-tab, 30s expiry, one per
   call) and the browser blocks the agent until the continuation settles.
   Chrome 149 Origin Trial, Edge 150, Brave 1.102.2.

2. **Re-Reading Is Not Free: Token Traces and Cache-Aware Energy Estimation for
   LLM Agents in Software Engineering.** Vartziotis T. et al. (8 authors).
   `arXiv:2611.20873`, 2026-11-16. v1, no venue. **(W)** *Measured:* ~1B tokens
   over 42 sessions / 752 task episodes / ten weeks; cached-context reads are
   94.8% of all API-reported tokens, ~260 cached per generated token; parent
   logs undercount subagent tokens by 10×.

3. **WebArena-Pro: A Heterogeneous, Multimodal, Reproducible Benchmark for Web
   Agents.** Kerboua I., Pesaran Zadeh F., Lù X.H. et al. (22 authors).
   `arXiv:2611.17955`, 2026-11-13. **NeurIPS 2026 D&B Track.** **(W)**
   *Measured:* 300 tasks / 20 self-hosted applications / 6 domains; AXTree +
   vision + audio/video observation; final-reward scoring, **no per-step element
   labels**; Claude Code + Claude Opus 5.5 and Codex + GPT 6.1 Sol both 62.3%.

4. **playwright-mcp release notes v0.0.82–v0.0.86.** `microsoft/playwright-mcp`,
   2026-09-18 to 2026-11-18. **(W for v0.0.85–86)** *States:* `--background`
   leaves the connected tab inactive and the window unfocused (Chrome throttles
   background timers); per-client tab-group ownership, named/coloured sessions,
   token rotation, and refusal of browser-wide permission and cookie changes;
   WebMCP page tools surfaced as first-class `webmcp_<tool>` MCP tools.

5. **Step-Aligned Script Generation with Verification and Recovery for Web
   Automation Testing (TESSARA).** Dhulipala H., Rong X., Yadavally A.,
   Nguyen T.N. `arXiv:2610.25601`, 2026-10-19. cs.SE, 12 pages.
   *Measured:* NL intent → Playwright scripts with goal-state assertions,
   step-level provenance, selective suffix regeneration and reversibility-aware
   backtracking; whole-system gains, no per-mechanism ablation.

6. **Web Element Relocalization in Evolving Web Applications: A Comparative
   Analysis and Extension Study.** Kluge A., Stocco A. `arXiv:2505.16424`
   (v2 2025-12-01). cs.SE. *Measured:* Similo / VON Similo replication,
   +5.62% on the original benchmark, a 23× larger benchmark, and HybridSimilo
   locating **98.8%** of elements with broken locators — a *location* rate, not a
   CORRECT/REFUSED/WRONG partition.

7. **EVIDENT: Evaluating Evidence Grounding in GUI Agents.** Nam Y., Cho M.,
   Kim M., Song S., Yoo H., Kim J., Lim K. `arXiv:2611.20488`, 2026-11-16.
   **EACL 2027 Findings.** **(W)** *Measured:* 220 English/Korean tasks with
   human-curated evidence metadata; TSR / ESR / GSR separate outcome success from
   evidence observation and claim-level support.

8. **Trained on What Screen Readers Cannot Read: Accessibility Debt in the GUI
   Corpora Behind Computer-Use Agents.** Kraishan O., Jitkajornwanich K.
   `arXiv:2611.16107`, 2026-11-11. **AISSA 2026.** **(W)** *Measured:*
   17,373,614 Android elements; content-description coverage 17.74% vs 57.27%;
   demonstrations operate described elements **9.0 points** more often than
   others on the same screens — a selection effect inside the benchmark.

9. **Can You Undo It? Reversibility Classes for AI Agent Actions.** Waghmare D.,
   Sufi S. `arXiv:2611.22075`, 2026-11-17. 2 authors, no venue. **(W)**
   *Measured:* 536 tools across 20 MCP servers; native annotation mapping differs
   from reviewed labels for **118 of 481** comparable tools.

10. **Checking Retry Transparency in Agent Tools.** Li J. `arXiv:2611.23307`,
    2026-11-11. 1 author, no venue. **(W)** *Argues:* recovery contracts must be
    executable and tested rather than inherited from a tool annotation; 6 MCP
    components including browser bindings. Numbers not imported (§4).

11. **Idempotency Is Not Recovery: A Fault-Injection Study of Language-Model
    Agent Tool Actions.** Xu S. `arXiv:2611.23353`, 2026-11-17. 1 author, no
    venue. **(W)** *Distinguishes:* duplicate suppression from recovery;
    disabling reconciliation left 100/100 post-effect crash outcomes **ambiguous**
    with no duplicates. Numbers not imported (§4).

12. **When Agents See Differently: Exposing UI Desynchronization Threats in
    Mobile Agents.** Li H., Zhao F., Geng Z., Yao Z., Yuan W., Luo X.
    `arXiv:2609.16732v2` (v2 2026-11-06). cs.CR. **(W, as v2)** *Measured:*
    546 tasks / 13 applications / 5 frameworks; misleading rates 77.4% static and
    67.2% dynamic via occluded regions and low-contrast text; **0 of 195**
    participants spontaneously noticed the perturbations.

13. **UIAnchor: Anchoring UI Perception and Action Execution for Reliable
    Service-Composed Mobile Task Automation with GUI Agents.** Zhou W. et al.
    (9 authors). `arXiv:2611.20753`, 2026-11-16. cs.HC, no venue. **(W)**
    *Measured:* +31.5% over GPT-4o on L4 tasks with a meta-controller doing
    pre-action verification and post-action outcome perception — whole-system,
    no ablation of the verification.

14. **WebAgents: Unbundling Agent Creation, Hosting, and Execution for an
    Agent-Native Web.** Fenoglio D., Gjoreski M., Langheinrich M., Chari P.,
    Raskar R. `arXiv:2611.21978`, 2026-11-16. **IEEE CIC 2026.** **(W)**
    *Measured:* a signed `agent.pkg` contract blocking 716 injected violations
    while accepting 295 benign controls, with execution authority retained in the
    user's runtime.

15. **browser-use release notes 1.0.3–1.0.6.** `browser-use/browser-use`,
    2026-11-12 to 2026-11-16. **(W)** *States:* batched screenshot pruning
    restored prompt-cache validity for **$0.208 vs $0.434** per task at
    unchanged score (76.1 vs 76.0) on their 200-task bench; 1.0.5 ships a
    per-run LLM judge.

16. **Beyond LLM-based test automation: A Zero-Cost Self-Healing Approach Using
    DOM Accessibility Tree Extraction.** Joseph R.N. `arXiv:2603.20358`,
    2026-03-20. 1 author, validated on **one website**. *Proposes:* a ten-tier
    locator hierarchy including `data-testid` and CSS class fragments — two keys
    this project measured and rejected.

17. **Can Mechanistic Interpretability Help Explain LLM Agent Failures? A Case
    Study on Web Element Hallucination.** Aghzal M., Geva M., Stein G.J., Yao Z.
    `arXiv:2611.18514`, 2026-11-13. **(W)** *Measured:* a last-prompt-token linear
    probe predicts hallucinated actions at 0.80 AUC and steering corrects 85% of
    them — and the probe direction is **sensitive to how actions are
    represented**.
