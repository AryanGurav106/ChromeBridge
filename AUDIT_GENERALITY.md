# Generality audit — ChromeBridge

**Question asked:** where is the code secretly site-specific, scenario-specific, or
otherwise not general — logic that happens to work on the pages it was developed
against but will silently do the wrong thing on a different site?

**Scope audited:** `extension/background.js` (4,871 lines — collector, action
pipeline, `fill_form`, `computerOp`, `clickTrusted`, `_domTextPage`),
`mcp_server.py`, `extension/listener_tag.js`, `core/bridge/server.py`,
`core/bridge/driver.py`. All read in full.
**Explicitly out of scope:** `legacy/`, `temp/`, `tools/` (test harnesses — local
brittleness there is acceptable).

Conducted 2026-07-26 against the post-round-27 build.

---

## Verdict

The codebase is substantially more general than typical "worked on my test site"
automation code. The Round-5 generality claims in `CLAUDE.md` mostly hold up:
label-diff dropdown verification, `aria-controls`-first option scoping, RTL
awareness, NFC-normalized matching, aria-modal-as-verified-claim, and paint-aware
occlusion are all real. The documented library signatures (Radix `data-state`,
`cmdk-input`, CodeMirror/Monaco/Ace class names, Floating-UI/Popper portal attrs)
are genuinely *boosters beside* general paths, as claimed — not sole gates.

**However, the real violations cluster in the most dangerous category: paths that
return `ok: true` after doing the wrong thing.** The three worst are a dropdown
fallback that clicks an arbitrary option when nothing matches and reports success,
a device-pixel/CSS-pixel mismatch that silently skews every screenshot-derived
coordinate click on any display scaled ≠ 100% (i.e. most Windows laptops), and a
fixed 30 s bridge timeout that makes large forms report failure while the extension
keeps filling and submitting — a double-submit machine.

Several English wordlists also survive in load-bearing positions despite the
"booster only" claim, and one of them **bypasses exactly the fill-time verification
that `CLAUDE.md` says covers the non-English residual.**

---

## Findings

| # | Location | What's hardcoded/assumed | Site that breaks it | Sev | Confidence |
|---|---|---|---|---|---|
| 1 | `mcp_server.py:154`, `background.js:4172`, `computerOp:566` | Screenshots are device px; `computer` clicks are CSS px; nothing converts | Any site on a Windows laptop at 125%/150% scale, or any browser-zoomed page | **H** | High |
| 2 | `background.js:908` `_pickOptionPage` | No text match → click `pool[0]` anyway, return `ok:true, "picked option…"` | Any dropdown whose option isn't rendered/matched (AJAX select still loading; date-picker misclassified as combobox) | **H** | High |
| 3 | `core/bridge/server.py:35` + `fill_form` as one op | Whole multi-dropdown form + submit must finish in 30 s | 10-field insurance/job-application form with slow comboboxes → Python times out, extension keeps going and submits → retry = double submit | **H** | High |
| 4 | `background.js:1061-1078` `_typeIntoOpenPopoverSearchPage` | "The search input near a listbox is the popover's search"; `visible[0]` first-match; **document-wide query** | Any site with header autocomplete (GitHub, MDN, most docs/e-commerce): a failed dropdown open types into the **global site search** and picks a suggestion | M-H | Med-High |
| 5 | `background.js:1203-1216, 1422` `fillDropdown` | `/^(select\|choose\|pick)\b/i` + ellipsis are the only placeholder signals gating the already-selected short-circuit and the verify-skip | German UI "Bitte wählen" → `ok:true "already selected"`, never opened. Inverse: real option "Select All" skips verification | M-H | High |
| 6 | `background.js:1598, 1567-1585` `collectCrossFrames` | Per-frame listing silently capped at 40 (count reported as complete); shells matched by exact `src` or unique host; depth-1 only | TCF consent iframe with 300 vendor toggles — "Save & Exit" beyond #40, invisible, no truncation note. Stripe Elements (3 same-host iframes) → ambiguous, all silently dropped | M | High (cap) / Med (shells) |
| 7 | `background.js:1794-1803` `section()` | `fixed` + width ≥ 60% vw + top > 15% vh + height < 60% vh ⇒ "consent banner — usually dismiss it first" | Spotify player bar, mobile-style bottom tab bar, sticky "Add to cart" bar — the page's **primary control row** labelled as chrome to dismiss | M | High |
| 8 | `background.js:1235-1247` `fillDropdown` | Options must render within 1200 ms or the trigger gets a trusted **re-click** | Select2/Ant AJAX dropdown at 2–3 s: re-click **toggles the open popover closed** | M | High |
| 9 | `mcp_server.py:332-349` `find` scorer | Tokenizer `[^a-z0-9]+` and `\b` boundaries — **ASCII-only** | Russian/Japanese/Chinese page: every token dies, find degrades to substring-on-full-query or returns nothing; "büro" shreds into fragments | M | High |
| 10 | `background.js:493, 566` `computerOp` | Coordinate clicks attach the debugger (infobar reflows layout) but use pre-attach screenshot coords verbatim — **fix #10 applied only to ref-based clicks** | First coordinate click of a session on a vertically-centered modal: infobar shrinks viewport, dialog shifts ~16 px, click misses a 32 px row | M | Medium |
| 11 | `background.js:4072` click op | Post-click fingerprint `runInTab` sits **outside** `doClick`'s try; a page navigating at +300 ms throws | Any ordinary link click whose navigation is mid-flight → whole op errors ("Click threw…") though the click succeeded | M-L | Medium |
| 12 | `background.js:1129, 1134` `_detectSubmitPage` | Tier 1 checks the `type` **attribute**, so implicit submits (`<button>` in a `<form>`, no attribute) fall to the English keyword tier; tier 3 doesn't exclude non-English cancel words | German dialog `Abbrechen` + `Speichern`, neither typed → all tiers fail, or re-resolution clicks a keyword false-positive | M-L | High |
| 13 | `background.js:2626, 2837` | Combobox values starting Select/Choose/Pick or ending "…" treated as placeholders | A chosen value "Select All Regions" listed as `value=""` + `(unselected)` → wasted re-pick turns | L | High |
| 14 | `background.js:1615, 361` `_frameShells` | Cross-origin frame offsets captured at collection time, reused for CDP clicks later | Consent iframe mid-page; agent scrolls between `read_page` and click → trusted click at stale top-doc coords | L-M | Medium |
| 15 | `background.js:689-691` `setCheckboxState` | English state words; **unknown word ⇒ toggle** | Model passes a non-English/label value → unconditional toggle can uncheck an already-correct box | L | High |
| 16 | `background.js:2032` `collapseDoubled` | Any exactly-doubled word sequence assumed to be a screen-reader duplicate | "New York New York" hotel → listed as "New York"; "Louie Louie" → "Louie" | L | High |
| 17 | `background.js:1671` `_domTextPage` outline | Trailing `¶ # §` stripped as permalink chrome | Microsoft Learn heading "C#" → outline says "C" |  L | High |
| 18 | `listener_tag.js:31` | Delegation-root exclusion is only BODY/HTML/MAIN | React 17+ binds on the root container `<div id="root">` → tagged as a control; container suppression usually saves it, but a small embedded React widget's root leaks in as a bogus target | L | Medium |

---

## Detail — top 8

### 1. Device-pixel screenshots vs CSS-pixel clicks (H)

The `zoom` action already scales for exactly this, proving the authors knew:

```python
# mcp_server.py ~596 (zoom)
# region is in CSS px; the capture is in device px — scale by their ratio.
vp = await b.call("javascript_exec", code="({w: innerWidth, h: innerHeight})", ...)
scale = img.width / max(vw, 1.0)
```

But plain screenshots (`_take_screenshot`, `background.js:4172` `captureVisibleTab`)
are returned to the model **unscaled**, and `computerOp` (`background.js:566-575`)
dispatches `Input.dispatchMouseEvent` at the model's coordinates verbatim — CDP
expects CSS px.

**Break:** Windows 11 laptop at 125% scale (the default on most 1080p+ laptops).
Viewport is 1536 CSS px wide; the screenshot is 1920 device px. The model sees a
button centred at image-x = 1200 and calls
`computer(left_click, coordinate=[1200, …])`; CDP clicks CSS-x = 1200 — the target
is at CSS-x = 960. Every screenshot-derived click lands ~25% off toward the
bottom-right, with no error. Ref-based clicks are unaffected, which makes the
failure look random.

> **Cross-validated by the benchmark.** Claude-in-Chrome agents hit precisely this
> in all three rounds — "`read_page` reported Viewport 1920×997 but screenshots
> come back 1512×785 (≈0.7875 scale)" — and one coordinate click missed outright.
> ChromeBridge has the same bug and escaped only because its agents clicked by ref.

**Minimal fix:** in `_take_screenshot`, read `devicePixelRatio` (or `innerWidth` vs
`img.width`, as `zoom` already does) and downscale the PNG to CSS-pixel dimensions
before returning — one `img.resize`. Alternatively scale incoming `coordinate`s in
`computerOp`.

---

### 2. `_pickOptionPage` clicks the first option when nothing matches (H)

```js
// background.js:904-909
pick = pool.find(o => labOf(o) === want);                      if (pick) tier = 'exact';
if (!pick) { pick = pool.find(o => labOf(o).startsWith(want)); if (pick) tier = 'prefix'; }
if (!pick) { pick = pool.find(o => labOf(o).includes(want));   if (pick) tier = 'contains'; }
}
if (!pick) { pick = pool[0] || null; if (pick) tier = 'first-option'; }
```

**Break:** an Ant/Select2 dropdown whose remote options for "Ontario" haven't
loaded, or a `button[aria-haspopup=true]` date-picker misclassified as a combobox by
`_fieldKindPage`. `pool` holds whatever the popover currently shows — or, via
`harvest-relaxed` (`background.js:812-814`), whatever text rows the topmost
`role=dialog` container has, **which can be the parent form dialog** when the
custom popover carries no role/popper markers.

No label matches → the code clicks `pool[0]`, an arbitrary element, and returns
`ok: true, msg: picked option "…"`. `fillDropdown`'s verify pass then sees the
trigger label *changed* (to the wrong value) and confirms success
(`registered = labN !== norm(beforeLabel)`, line 1410). `fill_form` counts the field
as filled. **The wrong value is submitted.**

The `actual` / `trigger now:` text does name the wrong option, so a very attentive
model *could* notice — but `ok: true` is a lie.

**Minimal fix:** when `tier === 'first-option'` and `want` is non-empty, return
`ok: false` with `sampleOptions` instead of clicking. Keep click-first-option only
for the empty-text case.

---

### 3. 30-second bridge timeout vs `fill_form` as one op → double submit (H)

`core/bridge/server.py:35`: `DEFAULT_REQUEST_TIMEOUT_SEC = 30.0`.
`mcp_server.py:498` sends the entire form as **one** `fill_form` bridge call.

Per combobox, `fillDropdown` can legitimately spend ~5 s (open poll 1200 ms →
trusted retry + poll 1200 ms → search-type + poll 1000 ms → settle 120 + 150 ms →
verify 800 ms). The submit settle adds up to 4 s (`background.js:4457-4480`).

**Break:** a 10-dropdown form (insurance quote, job application, admin config) on a
mid-speed connection ≈ 50 s of legitimate work. At t = 30 s `bridge.call` raises
`TimeoutError` → the MCP tool errors → the model concludes the fill failed.
Meanwhile the extension's `handleOp` **continues to completion, including the
auto-detected submit** (`submit_trusted=True` is hardwired at `mcp_server.py:502`).
The model retries `fill_form` → **the record is created twice.**

The tuning fits the ~6-field CRM form it was debugged on; it does not fit bigger
forms.

**Minimal fix:** pass a per-op timeout scaled to field count
(e.g. `10 + 6*len(fields) + 10` s), or accept a `timeout` kwarg in `call()` and use
it from the `fill_form` tool.

---

### 4. Popover-search fallback can type into the page's global search (M-H)

```js
// background.js:1061-1078
const inputs = Array.from(document.querySelectorAll(
  'input[cmdk-input], [cmdk-input], input[role="combobox"], input[role="searchbox"], input[type="search"], input[aria-autocomplete]'
));
...
let p = i.parentElement, depth = 0;
while (p && depth < 8) {
  if (p.querySelector('[role="listbox"], [role="option"]')) return true;
  ...
const inp = visible[0];
```

The query is **document-wide**, and the "sanity" gate — an ancestor within 8 levels
containing a `[role=listbox]` — is satisfied by any header search box with ARIA
autocomplete suggestions (GitHub, MDN, most docs sites, most e-commerce headers).

**Break:** step 3 fires whenever `count === 0` (`background.js:1251`). On such a
site, a combobox that fails to render options within the poll budget causes the
fallback to type the option text ("Ontario") into the **site's global search box**;
the suggestion list mounts real `[role=option]` nodes; `pollCount` goes non-zero;
`_pickOptionPage` clicks a **search suggestion**; the page navigates to a search
result. Reported as a successful pick or a verify-failure — either way the page
state is now wrecked mid-form.

**Minimal fix:** scope the input query to the currently-open popover container (the
one `_countVisibleOptionsPage`/harvest already computes, or the trigger's
`aria-controls` target), and require the listbox/option check to be *inside that
container*, not merely near the input.

---

### 5. English wordlist gates defeat the verification meant to cover non-English (M-H)

```js
// background.js:1203-1207
if (text && beforeLabel && norm(text) === norm(beforeLabel) &&
    !/^(select|choose|pick)\b/i.test(beforeLabel.trim()) &&
    !/\.\.\.$|…$/.test(beforeLabel.trim())) {
  return { ok: true, actual: beforeLabel, msg: `already selected ...` };
```

`CLAUDE.md`'s own residual note says a non-English text-only placeholder "can't be
flagged `(unselected)` at observation time — **fill-time verification catches it
instead**." **This short-circuit falsifies that claim.**

**Break:** German form, trigger shows "Bitte wählen" (no ellipsis, no
`data-placeholder`). The model — exactly as observed doing with English
placeholders — echoes "Bitte wählen" as the value. `norm(text) === norm(beforeLabel)`,
the English wordlist doesn't fire → return
`ok: true, "already selected 'Bitte wählen' — no action needed"`. The dropdown is
never opened, never verified, stays unfilled, and the failure surfaces only at
submit, if at all.

**Inverse bug:** `placeholderEcho` (lines 1214-1216) treats any requested text
starting with select/choose/pick as model confusion — so asking for a real option
literally named "Select All" makes the function **skip the registered-verification**
and return `ok: true` (line 1422) even when the click didn't register.

**Minimal fix:** for the short-circuit, additionally require positive evidence of a
selection (non-placeholder `data-*` state, or the element wasn't flagged
`unselected` at collection) — or drop the short-circuit and rely on the existing
verified re-pick path. For `placeholderEcho`, only treat it as echo when
`norm(text) === norm(beforeLabel)`, never on the bare wordlist.

---

### 6. Cross-origin iframe listing: silent 40-element cap, fragile shell matching (M)

```js
// background.js:1598
for (const e of raw.slice(0, 40)) {
```

The header then reports `${lines.length} element(s)` — i.e. "40 element(s)"
presented as a complete inventory, **with no "+N more" marker**. Contrast the main
listing's `LISTING_CAP`, which is scrupulous about truncation (line 3416).

**Break:** an IAB TCF consent iframe (in-frame Sourcepoint/OneTrust) with dozens of
purpose/vendor toggles before the footer buttons — "Save & Exit"/"Accept" fall
beyond index 40 and simply don't exist as far as the agent knows. There's also no
prioritization pass like the main listing has.

Separately, `background.js:1577-1584` anchors frames to shells by exact `src` match
or **unique** hostname. Multiple same-host frames — Stripe Elements ships
card/expiry/CVC as three `js.stripe.com` iframes — fail the uniqueness test whenever
URLs drift from the `src` attribute (redirects, hash/query rewrites), and those
frames vanish with zero breadcrumb (`collectCrossFrames` returns `''` on every
failure path).

**Minimal fix:** apply the main listing's priority-then-budget-then-note pattern (or
at minimum append `… +N more in this frame`); for shells, fall back to geometric
matching (frame count == shell count → pair by document order) when host matching is
ambiguous.

---

### 7. `overlay-banner` heuristic fires on persistent bottom bars (M)

```js
// background.js:1796-1798
if (wcs.position === 'fixed') {
  const wr = walker.getBoundingClientRect();
  isBanner = wr.width >= vw * 0.6 && wr.top > vh * 0.15 && wr.height < vh * 0.6;
}
```

Anything fixed, wide, and not at the very top is a "banner" — and the legend
instructs: *"overlay-banner = a consent/notification bar laid OVER the page —
usually dismiss it first."*

**Break:** Spotify web player's playback bar, a mobile-style bottom tab bar, or an
e-commerce product page's sticky "Add to cart" bar — all fixed, full-width,
bottom-anchored. On the product page the **primary task control** is labelled as
chrome the agent should dismiss; on Spotify, the play/pause/next controls are. The
shape was tuned to IBM Carbon's cookie bar (per the comment) and over-matches the
extremely common sticky-footer pattern.

**Minimal fix:** require an overlay signal beyond geometry — the container is a
late-DOM sibling of main content, or it *occludes* elements beneath it
(`physBlocked` evidence is already computed), or it contains dismiss affordances.
Alternatively rename to neutral ("fixed bottom bar") and drop "dismiss it first"
from the legend.

---

### 8. 1.2 s option budget → trusted re-click toggles slow dropdowns closed (M)

```js
// background.js:1235-1246
let count = await pollCount(1200);
...
if (!count) {
  tr('escalating: trusted open click');
  try { await clickTrusted(tabId, origSelector); } catch (e) { ... }
  count = await pollCount(1200);
```

The escalation assumes "no options after 1.2 s" means "the open click didn't
register."

**Break:** Select2/Ant/MUI Autocomplete with remote options on a slow API (2–3 s is
routine). The popover *is* open, showing a spinner with zero option nodes. The
trusted re-click on the trigger **toggles the popover closed** (standard combobox
behaviour). The second 1.2 s poll again sees nothing; step 3 then types into a
popover search that no longer exists — or, worse, into a global one (finding 4).

The code already captures `aria-expanded` in `_trigState` before/after (lines
1184-1194) **but only for the trace** — the decision ignores it.

**Minimal fix:** before escalating, check the state already in hand: if
`aria-expanded === 'true'` / `data-state === 'open'`, skip the re-click and extend
the poll. Two-line change.

---

## Already general — checked and cleared

So the reader knows what was inspected rather than skipped:

- **Dropdown pick verification** (`fillDropdown` step 6) — BEFORE/AFTER trigger-label
  comparison is language-independent and polls rather than sleeping; the English
  wordlist there is truly supplementary (except the two gate positions in finding 5).
- **`_pickOptionPage` scoping order** — `aria-controls`/`aria-owns` resolved first
  (W3C combobox pattern), roles second, harvest last. Stale-portal exclusion uses
  `aria-hidden`/`inert` (standard) with `data-state="closed"` as a booster only.
  Matching is NFC-normalized, whitespace-collapsed, `toLocaleLowerCase`, and ranked
  exact > prefix > contains (the India/Indiana fix is real).
- **Topmost-popover selection by effective z-index** with DOM-order tie-break —
  correctly handles portals prepended to `<body>`; better than "last in DOM wins".
- **RTL awareness** is real in all three places it matters: reading order
  (`background.js:3389`), submit-button end-side geometry (`_detectSubmitPage:1112`),
  and leading-`*` required markers (`background.js:2796`).
- **Modal detection** (`background.js:3291-3348`) — `aria-modal` treated as a *claim*
  verified against hit-test evidence; `:modal` trusted; the Yahoo-Finance false-modal
  and TrustArc zero-height cases both handled behaviourally, not by site name.
- **Occlusion** two-tier design (`physBlocked` vs paint-aware `clickable`) with
  `elementsFromPoint` stack walks, shadow-composed containment, and multi-point
  sampling — no layout-specific constants beyond the defensible 8×8 decoration floor
  (with role exemptions).
- **AccName resolution** (`background.js:2450-2513`) — follows spec order, excludes
  the control's own subtree from wrapping labels, resolves IDs against the element's
  root node (shadow-safe); garbage-name filters (`[object Object]`, `undefined`) are
  string-shape checks, not site checks.
- **mmid stability** (additive counter, registry rebuild per walk) and the
  composed-parent walk across shadow and same-origin frame boundaries.
- **`fill_form` submit-error sweep** — ARIA-first (`aria-invalid` →
  `aria-errormessage`/`aria-describedby`/`validationMessage`), framework class list
  demonstrably last-resort. Native-select emptiness is structural (empty option
  value), any language.
- **Main-listing truncation honesty** — priority-preserving cap with explicit
  "+N not shown", below/above-fold counters, blank-page disambiguation. (The
  cross-*frame* path is the exception — finding 6.)
- **`_ref_to_selector` / `resolveFrameSelector`** round-trip cleanly including the
  `f<frameId>:<n>` form; no ordering or format assumptions beyond the documented
  contract.
- **`core/bridge/server.py`** — token handshake, newer-wins eviction, keepalive, and
  the `.state`-based connected check are environment-general. No findings besides the
  shared 30 s timeout (finding 3).
- **`listener_tag.js` console capture** — wrapping plus `error`/`unhandledrejection`
  listeners is standard; the documented gap (browser-generated messages) is
  disclosed, not silent.

---

## Suggested fix order

**Tier 1 — silent wrong answers.** These undercut the product's core
differentiator (trustworthy action results) and are all small, local changes:
**#2** (first-option fallback), **#3** (timeout/double-submit), **#5** (wordlist
gates bypassing verification).

**Tier 2 — measurable correctness.** **#1** (pixel scaling — one `img.resize`),
then **#4** and **#8** (both are "check state you already captured before
escalating").

**Tier 3 — honesty and breadth.** **#6** (silent frame cap), **#7**
(overlay-banner over-match), **#9** (ASCII-only tokenizer), **#10**–**#12**.

**Tier 4 — cosmetic.** **#13**–**#18**.

Cross-reference: `BENCHMARK.md` documents that Claude-in-Chrome's *observed* worst
failure mode across 15 runs was ref-clicks reporting success while doing nothing
(7 occurrences). Findings 2, 3 and 5 are the same disease in this codebase, found by
reading rather than by being bitten.

---

## Resolution status

All 18 findings were fixed and the suites extended to 48 gap checks (from 42) + 11 shadow checks,
0 missed. Implementation notes are in `temp/dom_audit/FINDINGS.md` rounds 29-30.

Live-verified on real pages: #2 (unmatched option fails loudly), #13 + the `backed-by=ref_N`
evidence line, #3 (timeout budget, happy path), plus the two extras below.
Unit-verified only: #1 (this machine reports `devicePixelRatio: 1`, so the downscale branch cannot
fire here — proven at 125%/200% against synthetic captures, still unproven against a real scaled
display).
Fixture-verified only: #4, #6, #7, #8, #10-#12, #14-#18.

### Found while verifying — not in the original 18

19. **Submit auto-detect never worked outside a dialog** (`_detectSubmitPage`). Scope was a dialog
    query with `if (!dialog) return null`, so `fill_form(submit=true)` on any ordinary non-modal
    form filled the fields and did not submit. Invisible across 30 benchmark runs because agents
    that submitted always passed `submit_ref`. Now scopes to the field's own `<form>` first.
20. **`fill_form` silently downgraded off its batched write.** On a page not observed in the current
    document no mmids exist, so every field probed as `missing` and the form fell into the
    per-field path — losing the single-re-render React safety that is the tool's reason to exist.
    Only tell was the message format. Fixed by injecting mmids at the top of the op.
21. **`_pickOptionPage` scanned the whole document even when `aria-controls` had resolved** — so a
    second, unrelated listbox on the page could hijack the pick. Fixed at the harvest gate (scope
    is a preference; the gate asks whether a visible option is *inside* the scope).

### Caveat on method

Two fixes in this cycle were **green on fixtures and wrong on real pages** (the dead-duplicate
detector, and an over-strict `aria-controls` scoping that broke select2). The fixture suite catches
regressions in the behaviours it models; it does not catch a wrong model. Weight live verification
accordingly.
