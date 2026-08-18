# Research: Better Page Representation & a Faster/More-Accurate Browser Harness

A deep survey of the 2023–2026 state of the art for two questions, written specifically
against **this codebase's** current design:

- **Today's observation** (`core/utils/get_detailed_accessibility_tree.py` + `core/skills/get_dom_with_content_type.py`): inject an `mmid` integer onto every element via JS → take Playwright's `page.accessibility.snapshot()` → merge per-element attributes via a second JS pass → prune the tree → an Explainer LLM filters it. Plus a separate full-page text extract and optional screenshots. Elements are acted on by `mmid`.
- **Today's harness** (`core/browser_manager.py` + `core/skills/click_using_selector.py`): async Playwright, local persistent Chromium, **clicks via JS `dispatchEvent` on a CSS selector**, a DOM mutation observer to detect new elements.

This is the **Agent-E / WebVoyager-text lineage**. Its proven strength is a cheap, deterministic text channel. Its two weaknesses are exactly what you named: (1) the accessibility tree is a *semantic* projection that **discards visual/spatial layout** ("misses the UI part"), and (2) JS-dispatch clicks + full re-snapshot per step make actions **flaky and slow**.

---

# PART 1 — Better DOM fetch, optimization & representation

## 1.1 The core problem, precisely stated

The accessibility (AX) tree tells you *what* an element is (role, name) but not:
- **where** it is on screen (no bounding box / spatial layout),
- whether it's **actually visible** in the viewport or scrolled off,
- whether it's **occluded** by an overlay (cookie banner, modal) — i.e. "is this pixel actually clickable",/
- whether a styled `<div>`/`<span>` with a click handler is really a **button** (custom widgets the AX tree silently drops),
- **visual state** (active/selected/disabled rendered only in CSS), and it can't see **canvas/WebGL/SVG** content at all.

The market today is "DOM + screenshot." The cutting edge is **fusing them with a shared element ID**, plus pruning the text channel hard. Below, ranked by ROI for your stack.

## 1.2 Techniques (what each adds, with evidence)

### A. Enrich every element with geometry + visibility (highest ROI, pure JS)
Alongside `mmid`, compute in the same injection pass:
- `getBoundingClientRect()` → `{x,y,w,h}` per element (foundation for everything visual).
- **viewport flag** — non-zero size, intersecting the viewport, not `display:none`/`visibility:hidden`/`opacity:0`. Prunes huge off-screen AX subtrees.
- **true clickability** — `document.elementFromPoint(cx, cy)` at the element center; if it returns the element (or a descendant), it's the real top hit-target. *This is the single test that catches modal/cookie-banner overlays that visually cover content* — the most common "the agent clicked the wrong thing" bug.
- **interactivity heuristics** — `cursor:pointer`, `pointer-events`, ARIA role, `tabindex`, `contenteditable`.

This directly closes the "missing UI" gap, filters the AX tree to what's truly on screen, and is *days of work in your existing JS injection* (`__inject_attributes` / `__fetch_dom_info` in `get_detailed_accessibility_tree.py`). MDN: `getBoundingClientRect`.

### B. Set-of-Mark (SoM) screenshot channel keyed by `mmid`
Origin: Microsoft *"Set-of-Mark Prompting Unleashes Extraordinary Visual Grounding in GPT-4V"* (arXiv:2310.11441). For web you don't need SAM — you already know the interactables. Draw **numbered bounding boxes** (label = `mmid`) for the *visible, non-occluded* elements from (A) onto the screenshot, and give the VLM both the marked image and the AX text. The model says "click 42"; you act via `mmid` 42.
- **WebVoyager** (arXiv:2401.13919) uses exactly this and hits **59.1%** on its live benchmark.
- **VisualWebArena** (arXiv:2401.13649): GPT-4V text-only AXTree 7.25% → +captions 12.75% → +image 15.05% → **+SoM 16.37%**, larger gains on visually dense sites.
- **Caveat 1:** SoM only helps a *strong* VLM (GPT-4o/Claude-class); weaker VLMs saw no gain.
- **Caveat 2 (important):** SeeAct found *naive* SoM underperforms on dense web pages — so **mark only viewport-visible, non-occluded elements** (from step A) to avoid label clutter, and keep the AX text as a parallel channel rather than replacing it.

### C. Distill / prune the text channel (AgentOccam)
*AgentOccam* (arXiv:2410.13825, ICLR'25) is the strongest evidence that **representation engineering beats added machinery**: with *no vision, no training, no search*, just by pruning the observation and simplifying the action space, it set WebArena SOTA at **43.1%** (+9.8 abs / +29.4% over prior SOTA; +161% over a comparable plain agent). Concrete moves to copy in your pruning step:
- merge a label/description node with the interactive element that shares its text (dedup),
- render tables/lists as **Markdown** to kill repetitive structural tokens,
- drop empty/redundant/decorative AX nodes; keep `role + accessible-name + state + mmid`,
- prefer "load page content as state" over emitting hover/scroll actions.
Cheap, model-agnostic, frees token budget for the SoM image.

### D. Programmatic, task-conditioned pruning (Prune4Web)
*Prune4Web* (arXiv:2511.21398, recent/unverified numbers) has the planner LLM **write a small Python scoring function** to shortlist DOM elements per sub-goal instead of reading the whole tree. Reported **25–50× fewer candidate elements** and grounding accuracy **46.8% → 88.3%**. Your Explainer agent already does a soft version of this; making it emit a *filter/score* over `mmid` nodes (return top 10–40) is a natural, high-leverage upgrade.

### E. Detect custom interactive elements via CDP `getEventListeners`
The AX tree drops framework `div`/`span` widgets that only have JS click handlers. `browser-use`'s detector uses CDP `getEventListeners` (catches `click`/`mousedown`/`mouseup`), plus ARIA roles, `cursor:pointer`, and attribute-keyword heuristics, then assigns sequential highlight indices and **prefixes newly-appeared elements with `*`** so the model notices modals/AJAX content. This is the biggest source of "the agent can't see the button."

### F. Layout-preserving text fallback (Tarsier)
`reworkd/tarsier` tags interactables with typed bracketed IDs **burned onto the screenshot** (`[#id]` input, `[@id]` link, `[$id]` other), and crucially produces an **OCR-driven "ASCII-art" string that preserves 2-D layout** so even a text-only LLM gets spatial structure. Their internal result: *GPT-4 + Tarsier-text beat GPT-4V + Tarsier-screenshot by 10–20%* — layout-preserving text can beat raw vision. Useful as a cheap/text-only fallback.

### G. Transition-focused state summaries (World-Model agents)
*WMA* (arXiv:2410.13232, ICLR'25) feeds the LLM a short NL **diff of what changed** after each action rather than re-serializing the whole page — cheaper and better for long-horizon tracking. You already have a DOM mutation observer; emitting "what changed" deltas to the model is a natural fit.

## 1.3 The frontier: dedicated visual grounding models
When the target is **visual-only** (icon with no accessible name, canvas, pixel-positioned), a grounding VLM maps a *text description + screenshot* → a **pixel coordinate**. Then reconcile that pixel back to a DOM element (see Part 1.4). Open, Apache-2.0, self-hostable on one 24 GB GPU via vLLM, ranked by practicality:

| Model | Params | ScreenSpot | ScreenSpot-Pro | Notes |
|---|---|---|---|---|
| **UGround-V1-7B** (OSU) | 7B | 86.3% | 31.1 | Cleanest "describe → (x,y)" contract; pairs with SeeAct-V planner |
| **UI-TARS-1.5-7B** (ByteDance) | 7B | — | **~56–62%** | Strongest open grounder on hard/high-res pro UIs; can also be a full native agent |
| **MolmoPoint-GUI-8B** (Ai2) | 8B | — | 61.1 | Fully open data+weights; native "pointing" |
| **OS-Atlas-Base-7B** | 7B | SOTA@release | — | 13M-element cross-platform corpus |
| **OmniParser v2** (front-end, not agent) | — | — | 39.6 (w/ GPT-4o) | Screenshot → boxed element list + captions; YOLO part is **AGPL** (commercial caveat) |

Context: ScreenSpot is largely **saturated** (top models 85–90%+); **ScreenSpot-Pro** (arXiv:2504.07981, 1,581 tasks, pro apps, full-res) is the hard benchmark where open 7–8B grounders now **beat** Claude computer-use (27.7%) and OpenAI CUA (23.4%), and frontier closed models (GPT-5.x-class) reach ~86%. **Grounding is no longer the bottleneck it was in 2024.**

## 1.4 The winning pattern: hybrid, DOM-first, vision-fallback, with coordinate→`mmid` reconciliation
This is what SeeAct-V, WebVoyager, OmniTool, and Operator effectively do:
1. Build the candidate set from the AX tree + geometry (1.2.A) — each element has `mmid` + a bounding box. This is your ground-truth registry.
2. **DOM path (most steps):** if the target maps unambiguously to an `mmid` by role/name, act directly. Fast, deterministic, no extra VLM call.
3. **Vision fallback (the hard ~10–20%):** when the target is visual-only or ambiguous, either
   - **SoM over your own `mmid` boxes** (zero new infra — reuse your boxes, ask the VLM to "pick #N"), or
   - call a grounding model → get `(x,y)`.
4. **Reconcile coordinate → `mmid` (hit-testing):** never blind-click a raw pixel — find the `mmid` whose box contains `(x,y)` (or `document.elementFromPoint(x,y)` → nearest registered ancestor) and click *that element's center* via Playwright. Recovers determinism + exact-center clicking. Only fall back to raw `mouse.click(x,y)` when no DOM element exists there (true canvas).

Net: vision-level coverage with DOM precision/determinism/auditability, VLM fired only when needed.

---

# PART 2 — Faster & more accurate browser harness

## 2.1 What the leading harnesses do
- **browser-use** — your closest analog. Injected `buildDomTree.js` walking the DOM (predicates: interactive? visible? top-element via `elementFromPoint`?) assigning a `highlightIndex` (≈ your `mmid`). It hit the **same 5–6 s/large-page** cost you have, then **dropped Playwright for raw CDP in 2025**: motivation was Playwright's "second network hop through a Node.js server" and **state drift across three runtimes**; going CDP-native "massively increased the speed of element extraction, screenshots, and all default actions" and gave event-driven (not polled) updates + real cross-origin iframe support.
- **Stagehand** (Browserbase) — primitives `act()/observe()/extract()/agent()`; recommended **observe-then-act** (plan once, replay deterministically). v3 went CDP-native (**44% faster** on iframe/shadow-DOM). Headline technique: **action-level selector caching + self-healing** — cache key = hash of `{method, normalized URL, DOM hash, action}`; on hit, validate a page fingerprint and run the cached selector with **zero LLM calls**; on drift, re-resolve and re-cache. **Up to ~80% speedup** on repeat flows.
- **Skyvern** — screenshot + DOM in parallel, each interactable gets an ID shown both in a DOM list and as a labeled box on the screenshot; multimodal LLM picks the ID. Resilient to layout change; costs a screenshot + vision per step.
- **Agent-E** — Planner (DOM-insulated) + Browser-Nav agent, **DOM distillation**, and **post-action state-change feedback** (explicit action-effect verification). 73–81% on WebVoyager.
- **BrowserGym/AgentLab** — research harness with DOM+AXTree+screenshot obs. Load-bearing empirical finding: **the AX tree is the most important signal; screenshots help but cannot replace it** — which validates keeping your AX-centric design and *adding* vision rather than replacing.

## 2.2 Playwright vs raw CDP
- The cost is the **double RPC**: client → Node Playwright server (WebSocket) → CDP → browser, paid on every micro-check, with state drift across runtimes. Native CDP is ~15–20% faster raw and far faster for bulk observation.
- **CDP wins for observation specifically:**
  - `DOMSnapshot.captureSnapshot({computedStyles, includeDOMRects:true})` returns, in **one call**, the flattened DOM (incl. iframes/shadow/template), whitelisted computed styles, **and layout boxes + text positions** — replacing your per-element `getBoundingClientRect`/`getComputedStyle` JS injection entirely.
  - `Accessibility.getFullAXTree` returns the whole AX tree in one call.
  - Together: semantics + geometry + visibility **without injecting any JS per element** (also harder to bot-detect).
- **You don't have to abandon Playwright.** In Python: `page.context.new_cdp_session(page)` gives a raw CDP session *alongside* Playwright. Use CDP for the heavy observation call; keep Playwright's launch + auto-wait for actions. This is the pragmatic middle ground (full CDP-native, à la browser-use/Stagehand v3, is a bigger rewrite you can defer).

## 2.3 The #1 accuracy fix: stop using JS `dispatchEvent` for clicks
`click_using_selector.py` clicks by dispatching synthetic mouse events in JS. That **skips every safety check**, so it fires on hidden, moving, disabled, or **overlay-covered** elements and "succeeds" without a real interaction. Playwright's `locator.click()` auto-waits for **Visible, Stable (animations settled), Receives-Events (hit-test: target is the top element at the click point), Enabled**; `fill()` waits Visible/Enabled/Editable. Switching `mmid → Playwright Locator → .click()/.fill()/.press()` is the single biggest reliability win (kills overlay/cookie-banner/animation flakiness) and removes most manual waiting. Keep JS-dispatch only behind a `force=True` fallback for genuinely synthetic cases.

## 2.4 Other speed/accuracy levers
- **Incremental / diff observation** — you already run a mutation observer; use it to re-snapshot lazily and send the LLM only the *changed* subtree (browser-use caches the selector map, invalidating on nav/tab-switch).
- **Locator caching + observe-then-act** — cache resolved selectors per `{normalized URL, DOM fingerprint, action}`; skip the LLM on hits; re-resolve + re-cache on drift (Stagehand). Up to ~80% fewer LLM calls on repeat flows.
- **Verify each action's effect** — diff AX/URL/DOM-fingerprint before vs after; if nothing changed, trigger a bounded retry/self-correct loop (Agent-E).
- **Re-resolve `mmid` after each action** — AX+`mmid` is brittle under DOM mutation; re-snapshot and re-map before the next click rather than caching stale handles.
- **Record per-step CDP traces/screenshots locally** for post-mortem of flaky actions (the one Browserbase/Steel primitive worth copying offline).

## 2.5 Action-accuracy research (if you go further)
- **Value-guided look-ahead on risky steps** — *Tree Search for LM Agents* (arXiv:2407.01476): for irreversible actions (submit/purchase/delete) generate 2–3 candidates and score with a value model before committing (+28–40% relative on (Visual)WebArena).
- **Self-correction + memory** — Reflexion (arXiv:2303.11366): on failure, produce a verbal critique, retry, and persist the failure to avoid loops.
- **RL fine-tuning (durable, needs training infra)** — WebRL (arXiv:2411.02337) took open 8–9B models from ~5% to **42–43%** on WebArena-Lite, *beating GPT-4o*, via online curriculum + an outcome reward model; DigiRL (arXiv:2406.11896) similar for device control. The most durable path to reliability for a fixed set of target sites.

---

# Implemented — Phase 1 grounding cascade (2026-05)

The `get_dom_fields` path was rewritten from "dump the whole AX tree as a stringified
Python dict into a free-form Explainer" into a **task-conditioned grounding cascade**.
Motivated by: Skyvern's measured JSON/dict→flat-HTML win (−20-27% tokens, +3.9pp),
LineRetriever's finding that **dense embeddings over DOM text fail** (7-19%, worse than
truncation — so the unused `semantic_dom_filter.py` cosine approach was *not* adopted),
and Prune4Web's tiered lexical filter (grounding 46.8%→88.3%, Recall@20 >95%).

New/changed files:
- `core/utils/dom_serializer.py` — `flatten_tree()` turns the enriched AX tree into a flat
  element registry; `serialize_elements()` renders compact HTML-ish lines keyed by `mmid`
  (`[114]<button "Sign in">`, `*` = newly-appeared, `(occluded)`/`(offscreen)` from the
  geometry signals). **Measured on live Hacker News: `str(tree)` 50,566 chars → flat 7,180
  → filtered candidates 235 chars** (the grounder prompt shrank to <900 chars).
- `core/utils/element_filter.py` — `filter_elements()`: deterministic, LLM-free tiered
  scorer (exact>phrase>word>fuzzy × visible-text>aria>other-attrs) + interactivity/
  visibility priors → top-K (30). Replaces cosine embeddings; recall-safe fallback.
- `core/agents/explainer_agent.py` — Explainer is now a **structured grounder**:
  `ExplainerOutput{fields:[{mmid,label,role,action,confidence,rationale}], needs_vision,
  no_match, notes}` over a *pre-filtered candidate list* (SeeAct two-stage pattern),
  with confidence + vision/replan escalation flags. Same export names for `harness.py`.
- `core/skills/get_dom_with_content_type.py` — `get_dom_field_func` runs snapshot →
  flatten → filter → grounder → ranked text result; tracks per-job new mmids for the `*`
  delta cue. `do_get_accessibility_info` now returns the tree dict (not `str(dict)`).

Still TODO (Phase 2+ below): CDP `getEventListeners` custom-widget detection, SoM-over-
candidates vision fallback wired to the `needs_vision` flag, coordinate→mmid reconciliation,
post-action verify+Reflexion retry, one-shot CDP `DOMSnapshot.captureSnapshot`.

# Phased upgrade roadmap (mapped to this repo)

**Phase 1 — quick, high-ROI, no new infra (days)**
1. `click_using_selector.py`: replace JS-dispatch with `mmid → Playwright Locator → .click()` (auto-wait/actionability). Keep JS dispatch behind `force=True`. *(biggest accuracy win)*
2. `get_detailed_accessibility_tree.py`: in the existing JS pass, add per-element **bounding box + viewport-visible flag + `elementFromPoint` clickability**, and **filter the tree to on-screen, non-occluded** elements. *(closes the "missing UI" gap, kills overlay mis-clicks)*
3. Prune the text channel AgentOccam-style (dedup label/control pairs, Markdown tables, drop decorative nodes).

**Phase 2 — visual fusion (1–2 weeks)**
4. Add a **Set-of-Mark screenshot channel** keyed by `mmid` (reuse the boxes from step 2); feed marked image + pruned AX text to the VLM; act by `mmid`. Mark only visible/non-occluded elements.
5. Detect **custom interactive elements via CDP `getEventListeners`**; flag newly-appeared elements with `*`.
6. Have the Explainer emit a **task-conditioned shortlist/score** over `mmid` nodes (Prune4Web-style) instead of returning everything.

**Phase 3 — speed + robustness (1–2 weeks)**
7. Open a CDP session alongside Playwright; replace per-element JS injection with one `DOMSnapshot.captureSnapshot` (+ `getFullAXTree`) to get text+boxes+styles+tree in 1–2 calls. *(biggest speed win)*
8. Locator caching + observe-then-act; incremental diff observation off the mutation observer; post-action state-diff verification with bounded retry.

**Phase 4 — frontier (optional, when 1–3 plateau)**
9. Add a self-hosted grounding model (UGround-V1-7B or UI-TARS-1.5-7B on vLLM) as a **vision fallback**, with coordinate→`mmid` reconciliation (1.4), for visual-only/canvas targets.
10. Value-guided look-ahead on irreversible actions; Reflexion-style self-correction + memory. Consider WebRL-style RL only if you have training infra and a fixed target-site set.

---

# Key sources
**Representation:** Set-of-Mark arXiv:2310.11441 · WebVoyager arXiv:2401.13919 · VisualWebArena arXiv:2401.13649 · AgentOccam arXiv:2410.13825 · SeeAct arXiv:2401.01614 · Prune4Web arXiv:2511.21398 · DOM Downsampling arXiv:2508.04412 · WMA arXiv:2410.13232 · Tarsier github.com/reworkd/tarsier · browser-use element detection (deepwiki) · Skyvern blog · Stagehand (browserbase blog).
**Grounding models:** UGround/SeeAct-V arXiv:2410.05243 · OS-Atlas arXiv:2410.23218 · UI-TARS arXiv:2501.12326 · OmniParser github.com/microsoft/OmniParser · Molmo allenai.org/blog/molmopoint · ScreenSpot-Pro arXiv:2504.07981 · Claude computer use / OpenAI CUA docs.
**Harness:** browser-use "Playwright→CDP" (browser-use.com/posts/playwright-to-cdp) · Stagehand v3 + caching (browserbase.com/blog) · Playwright actionability (playwright.dev/docs/actionability) · CDP DOMSnapshot & Accessibility (chromedevtools.github.io/devtools-protocol) · Agent-E arXiv:2407.13032 · BrowserGym arXiv:2412.05467.
**Action accuracy:** Tree Search arXiv:2407.01476 · LATS arXiv:2310.04406 · WebRL arXiv:2411.02337 · DigiRL arXiv:2406.11896 · Reflexion arXiv:2303.11366.
**Benchmarks/surveys:** Online-Mind2Web arXiv:2504.01382 · WebArena arXiv:2307.13854 · AssistantBench arXiv:2407.15711 · WebGames arXiv:2502.18356 · GAIA arXiv:2311.12983 · GUI-agents survey arXiv:2504.13865.

*Caveat: a few aggregator leaderboard figures and some very recent (2025-11+/2026) arXiv IDs could not be independently verified; their numbers are flagged in-text and excluded from core claims.*

---

# PART 3 — The 2026 observation-space literature, read against the MCP architecture (2026-08)

PARTS 1–2 were written against the retired Playwright/pydantic-ai loop and are kept
for provenance. This part is written against `mcp_server.py` + `extension/background.js`
as they stand, and against the measured numbers in CLAUDE.md #16/#17/#22.

**Two of these findings say a decision we already shipped is probably wrong.** That is
the useful part; the confirmations are listed for completeness but change nothing.

*Sourcing caveat, applied throughout:* these were read via fetched abstracts/HTML with a
summarizing model, not by working through the PDFs. Treat every number below as
second-hand until it is re-derived on our own harness — which is the same rule CLAUDE.md
#16 already imposes on our own flattering results.

## 3.1 The finding most likely to mean we are wrong: reduction is model-capability-dependent

*Read More, Think More: Revisiting Observation Reduction for Web Agents* (arXiv:2604.01535)
reports that observation reduction is **not universally beneficial** — it helps
low-capability models and **hurts high-capability ones**, with higher-capability models
gaining up to **+17.5pp from raw HTML over an accessibility tree**. The mechanism is
specific and testable: strong models exploit layout and **CSS `z-index`** for grounding,
so "intercepted element" errors (clicked the wrong thing) *fell* for strong models given
more detail, while "not-found" errors (hallucinated ids) rose only for weak ones.

ChromeBridge's consumer is **always** frontier-class — Claude Code is the agent loop, by
design, with no weak-model mode to serve. And we default to `compact`.

Our own measurements already pointed here and we read them the other way:

| detail | tokens (frozen corpus) | presence | answerability |
|---|---|---|---|
| `compact` (default) | ~1,300 | 0.94 | **0.50** |
| `brief` | ~2,265 | — | **0.792** |
| `full` | ~2,741 | 0.96 | 0.793 |

We priced the loss at *half the answerable facts a page can pose* (#16), shipped the
lossy setting as the default, and treated the gap as something the agent escalates out of
per-call. The literature says the escalation should be the exception, not the standing
state.

**Proposal:** make `brief` the default; keep `compact` as an explicit budget mode. Cost
+74% tokens on a median page for +0.29 answerability — and `brief` exists precisely
because it was measured to carry `full`'s information for 17% fewer tokens.

**What would falsify it:** our answerability is derived from the DOM, so it measures
*information present*, not *task success*. Their +17.5pp is HTML-vs-AXTree, and `brief`
is neither. This is convergent evidence, not a settled result — adjudicate it with 3.5.

## 3.2 Hierarchy is the feature we discard most confidently, and the literature ranks it first

*Beyond Pixels: Exploring DOM Downsampling for LLM-Based Web Agents* (arXiv:2508.04412,
already in PART 1's sources but not its argument) ablates three features — hierarchy,
text, attributes — and finds **hierarchy the strongest**: the configuration with the most
hierarchical downsampling scored lowest (65% vs 73% / 71%). Its explicit criticism:
"element extraction renders low-dimensional element arrays, disregarding hierarchy as a
UI feature."

That is a description of our output. We emit a **flat, y-sorted list of rows**; `section=`
(nearest landmark) is the only structural signal, and CLAUDE.md #23 already records it
resolving *past* a dialog boundary — so it is not even a reliable region marker.

**Our 96.0% Mind2Web recall does not refute this.** Recall answers "was the target
listed", not "did the agent pick the right one out of 199". D2Snap and Region4Web measure
task success. The claim is **untested by us, not disproven** — and #17's head-to-head
table has the same limit: it compares recall-per-token, so a representation that improves
*choosing* would score identically.

*Region4Web: Rethinking Observation Space Granularity for Web Agents* (arXiv:2605.07134)
is the constructive version. It reorganises the AXTree into **functional regions** via
bottom-up merge/cut edge classification over node features (**role, depth, subtree size,
child count**), then attaches each region a *purpose* and a *state summary*. Reported:
**−43% tokens (6,437 → 3,671) and +2.3pp success** across four backbones; regions alone
moved 48.5% → 50.3%.

The bridge to what we already ship: **our fold rows are already primitive regions.**
`13× button "구독" — one per list row, ordered top-to-bottom` states a purpose and a
member set. Generalising folds *into* named regions is the same move Region4Web makes,
minus the fine-tuned Qwen3-0.6B — every edge feature they classify on is computable
structurally, which is the form this project requires anyway (no server-side model).

This is the biggest open architectural question in the project. It should be attempted
**after** 3.5, because tokens-vs-answerability cannot adjudicate it.

## 3.3 The fold-bucket bug has a twenty-year-old answer: cluster tag paths, not widths

Measured today on five sites: the shape-bucket key includes `Math.round(w/40)`, and width
is **content-determined** for text, so one semantic class shatters into buckets of one —
lite.cnn.com printed ~26 headline links individually beside two folds of 7 and 6, all one
list of `a` at height 17 and x=65; rakuten split one nav into 64×37 and 59×37; gutenberg
split 25 identical book rows into 18@113px + 6@106px + 1 orphan.

The classical family solves exactly this by keying on **structure**:

- **MDR** (Mining Data Records) — repeated adjacent sibling "generalized nodes".
  Documented weakness: assumes DOM **adjacency**, so it breaks on records interleaved
  with unrelated elements.
- **DEPTA** — segmentation then **partial tree alignment**; tolerates non-contiguous
  records.
- **Tag-path clustering** — cluster distinct root-to-leaf **tag paths** by how they
  co-occur and intersperse; the record structure is the cluster.
- **STEM** — suffix-tree formulation of the same idea.

Our fold is *already* non-contiguity-tolerant (it groups by shape across the document,
not by sibling runs), which is MDR's documented failure mode. So the fix is to change
**only the key** — shape → structural signature (tag path / ancestor chain) — keeping the
grouping semantics we have. That is strictly a gain over MDR, not a rewrite.

Cheap to validate: folding is **serialization-only** (the structured array is returned
before the pass), so out-of-sample recall cannot move by construction. Only tokens need
measuring.

## 3.4 Truncation should downsample, not decapitate

**AdaptiveD2Snap** infers downsampling parameters to hit a **token budget** (default
4,096) rather than cutting content. We do the opposite: keep full-detail rows and drop
the tail — craigslist at `max_chars=3200` dropped **122 of 199** elements.

Our own architecture already contains the right rule one level up. `_truncate` drops the
legend before it drops rows (#13), and the whole filtering overhaul rests on *a heuristic
may decide prominence, never existence*. Extend the same principle to the budget:
**degrade detail before dropping existence.** A natural order — `box()` coordinates →
label length → fold harder → step down the detail level → only then drop elements.

We do *announce* the drop, which is better than the field's silent pruning. But an
announced absence is still an absence, and 122 is most of the page.

## 3.5 The metric to steal: Minimal Failure Set coverage

*Revisiting Observation Reduction for Web Agents: Comprehensive Evaluation with a
Lightweight Framework* (arXiv:2605.29397) defines coverage as **the fraction of instances
in which a reduction method fully retains the Minimal Failure Set** — the minimal set of
elements whose removal makes the task fail.

That is sharper than our `presence` metric in exactly the way we need: `presence` is
task-agnostic (is the element listed at all), while MFS coverage is conditioned on what
the task actually required, and sits directly on the catastrophic-loss axis the
asymmetric-loss framing is built around. Mind2Web's labels give us a single-element MFS
today, and the definition generalises to multi-element sets.

**This is the ruler 3.1 and 3.2 both need.** Hierarchy and detail level change
*grounding*; tokens-vs-answerability measures *presence*. We cannot adjudicate a
grounding change with a presence metric, which is why both questions are currently
un-decidable on our own harness.

## 3.6 Delta is probably the wrong thing to have made opt-in

Playwright's MCP server ships incremental diffs with `[unchanged]` markers for roughly a
**94% payload reduction**, and the reported empirical distribution is the striking part:
**52.9% of steps exhibit zero change, and 74.4% stay under 5% DOM change** — changes are
typically a dropdown expanding or a tooltip appearing.

We have `read_page(delta=true)` measured at **−96%** (6,300 → 220 chars), but it is
opt-in, so the majority case pays full price by default. Independently, 2604.01535
recommends **diff-based observation history** as the token-efficient alternative to
reduction — i.e. the way to afford *more* detail per observation. That composes directly
with 3.1: **`brief` + delta may dominate `compact` without delta on both axes at once.**

The existing refusals (no prior read, tiny page, wholesale change, scoped read,
navigation) are correct and should stay. The change is to *attempt* delta automatically on
a repeat read of an unchanged URL and say when it engaged.

## 3.7 Where this project is ahead, and should not trade it away

- **Nobody in this literature measures whether the representation lies.** The
  hallucination work — HalluClear's *Element Existence* class (arXiv:2604.17284), UI-CUBE
  (arXiv:2511.17131), the PING taxonomy — treats a missing element as a **model** failure
  to be detected downstream by verifiers and judges. Our `markCut` / no-silent-omission /
  prominence-not-existence / drop-ledger program treats it as a **representation-supply**
  failure, which is where it is actually fixable. #22's *216,719 characters hidden across
  66% of sites, priced at 0.297% to disclose* is the kind of number nobody else appears to
  be producing.
- **The drop ledger has no analog.** Region4Web, D2Snap and Prune4Web all prune without a
  record; none can explain its own omissions. Ours corrected the container-suppression
  hypothesis in one call after six DOM-mutation probes had failed to.
- **HAR replay over MHTML.** NEXT-EVAL (arXiv:2505.17125) builds its eval sets from MHTML
  snapshots. We measured MHTML at **0% element retention** under Playwright (it does not
  execute JS) and rejected it (#20); our corpus keeps JS running.
- **Caveat in the other direction:** UI-CUBE reports agents at 68–87% of human performance
  on simple tasks but only **15–32% on complex workflows**, attributed to memory,
  hierarchical planning and state coordination. Representation is not the binding
  constraint on long-horizon reliability. Do not over-attribute what better DOM output
  can buy.

## 3.8 Ranked next actions

1. **Fold key: shape → structural signature** (3.3). Contained, serialization-only,
   fixes a defect measured on three of five sites today.
2. **Degrade-before-drop truncation** (3.4). The principle is already shipped one level
   up; this applies it to the budget.
3. **MFS coverage in `measure_retention.py` / `bench_mind2web.py`** (3.5). Builds the
   ruler the next two need.
4. **Flip the default to `brief`** (3.1). After 3.5 can adjudicate it.
5. **Delta on repeat reads of an unchanged URL** (3.6).
6. **Functional regions** (3.2). Largest, last, and gated on 3.5.

## Sources added in this part

Region4Web arXiv:2605.07134 · Read More, Think More arXiv:2604.01535 · Revisiting
Observation Reduction (MFS coverage) arXiv:2605.29397 · Beyond Pixels / D2Snap
arXiv:2508.04412 (+ webfuse.com/blog/dom-downsampling-for-llm-based-web-agents for
AdaptiveD2Snap) · NEXT-EVAL arXiv:2505.17125 · HalluClear arXiv:2604.17284 · UI-CUBE
arXiv:2511.17131 · LineRetriever arXiv:2507.00210 · tag-path clustering / MDR / DEPTA /
STEM (Liu 2003, Zhai & Liu 2005, Miao 2009, Springer KAIS 10.1007/s10115-017-1062-0) ·
VIPS (MSR TR-2003-79, still the segmentation baseline per an 8,490-page comparison) ·
Playwright ARIA snapshots + MCP incremental diffs (playwright.dev/docs/aria-snapshots).

---

# PART 4 — PRESENTATION: how a page should be rendered to an agent (2026-08)

PART 3 is about *which elements survive*. That is a small, downstream question. This part
is about the one nobody in this project has examined: **ChromeBridge presents a web page as
a flat inventory of controls, and every other design decision follows from that choice.**

```
ref_52 | a "post" section=header | box(2218,0,44,44)
```

One row per control, sorted by `y`, with annotations appended. It is a good inventory. But
an inventory is only one of at least five presentation stances available, and we use no
other. The literature below is organised by stance, not by paper.

*Sourcing caveat as in PART 3: read via fetched abstracts/HTML with a summarizing model.
Every number is second-hand until re-derived on our own harness.*

## 4.1 Present at the granularity you ACT at

We have an asymmetry nobody noticed because the two halves were built at different times:

- **We act at form granularity.** `fill_form(fields, submit, submit_ref)` is atomic — all
  text writes in one page-context script, comboboxes clicked-and-picked, submit resolved
  structurally. The tool takes a form as one thing.
- **We observe at element granularity.** The same form arrives as 5–30 unrelated rows
  scattered through a y-sorted list, and the agent has to reassemble it.

*Build the web for agents, not agents for the web* (arXiv:2506.10953) makes this its
central design claim: agent interfaces should offer **"unified higher-level actions"**
rather than click/type primitives, under six AWI principles of which one is verbatim our
problem — *optimal representations: efficient, task-relevant observations without
superfluous information*. *Web Verbs* (arXiv:2602.17245) proposes the same unit from the
other end: typed, semantically documented functions as the thing an agent discovers.

Concretely, the observation should look like the call:

```
form "Search apartments / housing for rent"  → fill_form(submit=ref_68)
    q       input[text]   placeholder="search apartments / housing for rent"
    min/max input[text]   price
    beds    select        value="all" (unselected)
```

Shorter than five independent rows, and it names the call the agent is about to make. Our
own `find` docstring already tells the agent to pass option TEXT to `fill_form` — the tool
surface is form-shaped and the observation is not.

## 4.2 Structure beats coordinates — and coordinates have *measured* harm on dense pages

This is the most uncomfortable finding in the survey, because it is a direct measurement
against a field we print on every single row.

WorkArena (arXiv:2403.07718) added coordinates/bounding boxes to an AXTree observation:

| observation | MiniWoB (small pages) | WorkArena (complex pages) |
|---|---|---|
| AXTree baseline | 68.2% | **45.5%** |
| AXTree + coordinates | **72.6%** | **41.2%** |
| vision-augmented | 67.7% | 41.8% |

Coordinates helped on simple pages and **cost 4.3pp on complex ones**. The authors'
explanation: *"the prompt becomes longer and seems to overwhelm the LLM… seemingly harmless
features… actually degrade performance"*, because the tree is already large and extra
fields distract.

`box(x,y,w,h)` is ~22 characters × 199 rows ≈ **4,400 characters on the craigslist listing**
— and craigslist is precisely the complex-page case where the measurement went negative.
Worse, we already know the field is partly untrustworthy: #23 records printed `box()`
drifting ~110px on loading pages, and #25 records the same ref reporting clicks 1,097px
apart on OpenStreetMap. **Refs re-measure at click time, so the coordinate is not needed to
act** — it exists for the agent's spatial reasoning, which is exactly the use the WorkArena
number calls into question.

What the same literature says to spend that budget on instead:

- **Hierarchy.** D2Snap's ablation ranks it the strongest of three features (PART 3 §3.2).
  We convey none — no nesting, no indentation, `section=` only.
- **Layout as arrangement, not as numbers.** Tarsier renders a page to whitespace-structured
  ASCII preserving 2D position, and reports **unimodal GPT-4 on Tarsier text beating GPT-4V
  on Tarsier screenshots by 10–20%** (internal benchmark, unpublished — treat as directional).
  The signal that helped was *relative arrangement*, which four numbers per row do not give.

**Proposal:** `box()` becomes opt-in (`geometry=true`), and the freed budget buys nesting.
The test is a matched comparison at equal token count: indented-without-boxes vs
flat-with-boxes.

## 4.3 Repeated records want columns, not quoted prose

Our fold row collapses a repeated group correctly and then throws away the structure inside
each member:

```
75:"Moby Dick; Or, The Whale Herman Melville 206001 downloads"
```

Title, author and download count are all there, concatenated into one quoted string. We had
them separated in the DOM and re-flattened them, so the agent must re-segment prose we
already had structured. On gutenberg that is 25 rows of it.

The format literature is unusually consistent here:

- **ONTO** (arXiv:2604.17512) — columnar encoding of repeated records, **20–40% fewer tokens
  than JSON with accuracy maintained**; header amortises over record count. Its stated
  limitation is *heterogeneous* records — which is exactly what our `_kind()` shape guard
  already screens for.
- **Notation Matters** (arXiv:2605.29676) — TOON/TRON beat JSON/XML specifically on
  **tabular and repeated records**.
- Markdown/CSV-family notation is the most token-efficient of the readable formats (34–38%
  under JSON); **XML is worst on both axes** (14% above JSON in tokens, lowest comprehension
  at 67.1%) — worth recording so nobody proposes tags.

So:

```
25× book row | ref | title                      | author          | downloads
        75   | Moby Dick; Or, The Whale         | Herman Melville | 206001
        93   | A Room with a View               | E. M. Forster   | 153005
```

**This is also the missing answer to a defect we have carried since #14:** a table's 195
data values were unreachable by ref, `read_page(ref_id=<table>, filter="all")` returned 8
column headers and zero data, and three separate agents fell back to `javascript_tool`. A
table is the canonical columnar case. One mechanism fixes the fold *and* gives tables a
representation they have never had.

## 4.4 A page is a table of contents, not a document

Progressive disclosure is the consensus long-context pattern — *Is Progressive Disclosure
All You Need for Long-Context Agents?* (arXiv:2607.17598), and the index → summary → detail
→ source layering now standard in agent context design. Region4Web (PART 3 §3.2) is its web
instance.

**We already have the drill mechanism, already measured: `ref_id` scoping returned an href
in 924 characters instead of 13,575.** What we do not have is the right default — the agent
pays for the whole document first and can only scope *afterwards*, so the cheap path is
reachable only once the expensive one has been taken.

Inverted:

```
Page: apartments / housing for rent — 199 controls in 4 regions
  header        12 controls  nav, account
  search form    9 controls  submit=ref_68
  results       25 rows      columnar: title, price, beds, location
  filters       31 controls  13 checkboxes, 10 ranges, 4 dropdowns
Expand: read_page(ref_id=…). Full listing: read_page(regions=false).
```

This is the change with the largest possible upside and the most honest risk: it adds a
round trip, so it must be judged on **tokens-to-task-completion, not tokens-per-observation**.
A region index that sends the agent back for three expansions has lost.

It also composes with everything above — a region is where a purpose label lives, where a
columnar fold attaches, and the unit at which a delta is cheap.

## 4.5 WebMCP: the page may already describe itself, and we are the only kind of client that can read it

Chrome is shipping a standard for pages to declare their own capabilities as callable tools,
which makes the entire DOM-inference problem moot wherever it is adopted.

**The API** (Chrome for Developers, `developer.chrome.com/docs/ai/webmcp`; W3C Web Machine
Learning CG, accepted Sept 2025; early preview Chrome 146, origin trial from 149,
`chrome://flags/#enable-webmcp-testing` for local work — version details differ across
sources, verify before building):

```javascript
await document.modelContext.registerTool({          // navigator.modelContext deprecated in Chrome 150
  name: 'addTodo',
  description: "Add a new item to the to-do list",
  inputSchema: { type: "object", properties: { text: { type: "string" } } },
  execute: async ({ text }) => `Added to-do: ${text}`,
  annotations: { readOnlyHint: false, untrustedContentHint: true },
});
```

Consumption side: `document.modelContext.getTools()` returns `{name, description,
inputSchema, annotations, origin, window}`; `document.modelContext.executeTool(tool,
inputJsonString)` invokes one; a `toolchange` event fires when the set changes. A
declarative variant annotates ordinary HTML forms. There is also a testing surface,
`navigator.modelContextTesting`, with `listTools()` / `executeTool()`.

**Feasibility is already proven by an extension.** The Chrome team ships
`beaufortfrancois/model-context-tool-inspector`, an extension that enumerates a page's
registered tools and executes them. We reach the main world through CDP `Runtime.evaluate`
already (`javascript_tool`), so `getTools()` is inside existing plumbing. *Caveat to check:
content scripts run in an isolated world and the spec has an `exposedTo` origin list, so
enumerate from the MAIN world, not from a content script.*

**We are structurally advantaged, uniquely.** WebMCP explicitly does not support headless
browsing. ChromeBridge is an MV3 extension in the user's real, logged-in Chrome — the exact
client this standard is for. Every Playwright/CDP-launcher competitor sits on the wrong side
of that line, and this is the first capability where our architecture wins by construction
rather than by effort.

Two further connections worth recording:

- **`annotations.readOnlyHint` is the declared destructiveness signal that #24 deleted the
  wordlists for lacking.** We replaced natural-language guessing with "answer only from what
  the document declares"; WebMCP *is* the document declaring it. The same principle extends
  with no new machinery.
- **`untrustedContentHint`** is a prompt-injection marker on page-supplied content, which
  belongs in the same place our panel already treats tab titles as attacker-controlled.

**Presentation consequence:** where a page declares tools, the best presentation of that page
is *not a DOM listing at all*. `read_page` should lead with the declared tools and their
schemas, and a `call_page_tool` op should exist. The listing stays the fallback for
undeclared pages — which is nearly all of them today and will remain the majority for years,
so this is strictly additive.

**Cheapest first step, worth doing regardless of adoption rate:** detect and report. One
conditional line — *"this page declares 4 agent tools; read them with page_tools()"* — costs
zero on pages without them and is unambiguously better than re-deriving intent from markup.

## 4.6 The counterweight, and the rule it implies

WorkArena's finding is not only about coordinates. It is that *seemingly harmless features
degrade performance* once the observation is already large. We ship roughly eighteen distinct
annotation tags — `(required)` `(unselected)` `(current)` `(below-fold)` `(occluded/blocked)`
`(disabled)` `(opens NEW tab)` `(opens menu/popup)` `(collapsed)` `(scrollable region)`
`(unlabeled-icon)` `(image/media)` `(code-editor)` `(canvas)` … — plus `name=` `value=`
`placeholder=` `near=` `under=` `section=` `role=` and a legend.

Our defence is real but has never been written as a rule: **almost every tag traces to a
specific live-agent failure it prevents** (#11, #14, #23, #25). That is the correct bar, and
it should be stated as one — *an annotation must be earned by a measured failure it prevents,
and priced against the listing*. It is the same discipline #22 applied to truncation markers
(0.297%) and #10 to the detail legend (2.6%).

The legend itself **fails that bar today**: measured at 24.4% of listing tokens with no
measured accuracy contribution. That is the cheapest available win and is already queued.

The rule also argues against §4.4: a purpose string per region is a new field, and it must be
paid for by what the region index removes.

## 4.7 Confirmed, no action

- **Our row notation is a good choice.** Pipe-delimited compact rows sit in the
  markdown/CSV-family that measures most token-efficient; XML is the worst on both tokens
  and comprehension. No format migration is warranted.
- **Integer `ref_N` handles are right.** Tarsier's `[23]`, browser-use's indices,
  Set-of-Mark's marks and our mmids all converge independently on small integer handles
  rather than selectors or XPath. Already done.

## 4.8 Ranked

1. **Columnar folds** (§4.3) — subsumes PART 3's fold-key fix, fills the table hole open
   since #14, serialization-only so out-of-sample recall cannot move.
2. **`box()` opt-in** (§4.2) — the largest single token line item in the listing, and the
   only field with published evidence of *harm* on exactly our kind of page.
3. **WebMCP detect-and-report** (§4.5) — cheap, additive, and the one place our architecture
   wins by construction.
4. **Form-unit presentation** (§4.1) — aligns the observation with the action we already ship.
5. **Region index as the default** (§4.4) — biggest upside, real risk; judge on
   tokens-to-completion.
6. **Kill the legend** (§4.6) — queued, unblocked, 24.4%.

## Sources added in this part

Build the web for agents, not agents for the web arXiv:2506.10953 · Web Verbs
arXiv:2602.17245 · WorkArena arXiv:2403.07718 (coordinate/feature ablation) · ONTO
arXiv:2604.17512 · Notation Matters arXiv:2605.29676 · Is Progressive Disclosure All You
Need for Long-Context Agents? arXiv:2607.17598 · Signifiers as a First-class Abstraction
arXiv:2302.06970 · Tarsier github.com/reworkd/tarsier · WebMCP: developer.chrome.com/docs/ai/webmcp
(+ /imperative-api), W3C webmachinelearning/webmcp, model-context-tool-inspector
(github.com/beaufortfrancois) · BrowserGym observation formats browsergym.readthedocs.io.
