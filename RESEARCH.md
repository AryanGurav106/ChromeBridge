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
