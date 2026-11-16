# Adversarial pattern audit — 2026-11-16

**Scope.** `extension/background.js` (primary), `extension/listener_tag.js`,
`extension/panel.js`, `mcp_server.py`, `core/flows/*.py`. Read-only; no source
was modified.

**The claim under test.** *"Existence is decided only by DECLARATIONS."* An
element should be listed, named, classified or acted on because HTML, ARIA or
CSS declares something about it — never because of a class name, a pixel
threshold, a framework name, a font name, or a natural-language wordlist. The
project also claims **no natural-language wordlist reads page text anywhere**
and **no ASCII-only character class gates page text**.

**Verdict in one line.** The wordlist claim survives — I could not find a
natural-language word list reading page prose anywhere, and
`docs/research/SELF-AUDIT-2026-11-16.md` §3's three specific sub-claims all
check out. **But the claim it is used to support does not.** The hazard class
in this codebase has moved, and the three things that now decide behaviour from
author-controlled or script-dependent input are invisible to
`tools/audit_patterns.py` *and* to the hand sweep in that self-audit:

1. **a class string used as an identity key** (F2, F3),
2. **an ASCII *punctuation* class used as an "is this human prose?" test** (F4, F5),
3. **a UTF-16 character count used as an "is this a label?" test** (F7).

All three are demonstrated below with runnable fixtures. Six of the thirteen
findings reproduce a defect this log already records as fixed, in a different
function.

Twelve of thirteen findings sit in code paths that `tools/audit_patterns.py`
structurally cannot report (F9).

---

## Severity ranking

| # | Finding | Severity | Evidence |
|---|---|---|---|
| F1 | `keepForFind` admits a *subset* of `isInteractive`; five declared control kinds vanish below the fold | **HIGH** | DEMONSTRATED |
| F2 | A state class defeats `_kind`, so the record climb silently reverts to 1 hop for the *selected* item | **HIGH** | DEMONSTRATED + control |
| F3 | A Tailwind colour utility makes a filled combobox report `(unselected)` and erases its value | **HIGH** | DEMONSTRATED |
| F4 | `labelish()` rejects page text containing ASCII `{ } ; < >`, then attaches a **neighbour's** label | **MED-HIGH** | DEMONSTRATED |
| F5 | `synthLabel` discards any `data-*` label containing ASCII `( ) [ ] # >` | **MEDIUM** | DEMONSTRATED |
| F6 | `find`'s "no word separators" script list misses halfwidth katakana and CJK Ext-A / Compat | **MEDIUM** | DEMONSTRATED |
| F7 | UTF-16 counts as label/prose tests: a Japanese news card is demoted where the English one is not | **MEDIUM** | DEMONSTRATED |
| F8 | Existence depends on an HTTP header: under CSP, `<div onpointerdown>` vanishes, `<div onclick>` does not | **MEDIUM** | DEMONSTRATED |
| F9 | **The tripwire cannot fire.** P4 passes because its "is this page text?" test is a regex over *variable names* | **MEDIUM** | MEASURED |
| F10 | "What is this element's parent?" is answered two ways in one function — `composedParent` twice, `parentElement` ~12 times | **MED-LOW** | REASONED |
| F11 | `frozenFade` explains only elements held at **opacity 0**; `transitionProperty !== 'opacity'` is a hardcoded property name | **LOW-MED** | REASONED |
| F12 | `el.options.length > 2` means a 2-option sentinel prompt reports its prompt as a chosen value | **LOW** | REASONED |
| F13 | `/^[\w.:+-]+$/` on declared constraint values: non-Latin bounds are quoted, Latin ones bare | **LOW** | REASONED |

Reproduction scripts and fixtures are under the session scratchpad
(`demo_tw.py`, `demo_kind.py`, `demo_below.py`, `demo_cjk2.py`, `probe.py`,
`wider.py`); each is ~30 lines and extracts the real page-side function with
`tools/_extract.py`, the same technique the browser suites use.

---

## F1 — `keepForFind` re-enumerates a SUBSET of the admitting set — HIGH, DEMONSTRATED

`extension/background.js:7666`

```js
const keepForFind = (structured || !!scopeMmid) && visible && !inViewport && (() => {
  const rr = el.getAttribute('role');
  if (['a', 'button'].includes(tagL) || formyTags.has(tagL) ||
      _roleHit(rr)) return true;
  ...
  if (el.__abClickBound) return true;
  if (el.hasAttribute('onclick') || _hasHandlerProp(el)
      || el.hasAttribute('tabindex')) return true;
  if (getComputedStyle(el).cursor === 'pointer') return true;
  ...
  return false;
})();
```

The comment directly above it says, in capitals: *"AN ELEMENT THAT PASSED
isInteractive IS A CONTROL. This predicate used to be NARROWER than the
interactivity test … The two rules disagreed about what counts as a control."*

**It still is narrower, by five of the eight admitting signals.** `isInteractive`
(`:6645`) admits `summary`, `audio|video[controls]`, `canvas`, `svg`,
`editorHosts` and `isContentEditable`. None of those appears in `keepForFind`,
and none of them reliably carries `tabindex`, `onclick` or `cursor:pointer`.

Measured on a page with a 2000px spacer and one of each below the fold:

```
element id        in STRUCTURED array (what find() searches)
  b_button        YES
  b_link          YES
  b_summary       NO  <-- unreachable by find()
  b_details       NO  <-- unreachable by find()
  b_ce            NO  <-- unreachable by find()
  b_canvas        NO  <-- unreachable by find()     (aria-label="Sales chart")
  b_video         NO  <-- unreachable by find()     (aria-label="Product video")
```

The canvas and the video are the damning rows: **the page supplied an
`aria-label` and the element still disappears.**

**What breaks.** Any long e-commerce product page whose Shipping / Returns
`<details>` accordions sit below the fold — `find("shipping options")` cannot
reach a `<summary>` but reaches an identically-placed `<button>`. A comment box
(`contenteditable`) at the bottom of an article. A labelled chart `<canvas>` on
a dashboard. A code editor on a docs page.

**Why no ruler caught it.** `measure_findability.py`, `bench_mind2web.py` and
`bench_trajectory.py` all score the structured array or the listing, and
Mind2Web's targets are `<a>`/`<button>`/form tags. The five missing kinds are
outside every corpus in the project. #25's rule, pointed at a predicate.

---

## F2 — A state class defeats the record climb — HIGH, DEMONSTRATED WITH CONTROL

`extension/background.js:13360` (`_kind`), `:13379` (`_isRecord`), `:13389` (`_climbTo`)

```js
const _kind = (e) => {
  const c = (typeof e.className === 'string'
    ? e.className.trim().replace(/\s+/g, ' ') : '');
  return c ? e.tagName + '.' + c : _sig(e, 3);
};
const _isRecord = (n) => {
  const p = n.parentElement;
  if (!p || p.children.length < 2) return false;
  const s = _kind(n);
  let k = 0;
  for (const c of p.children) { if (_kind(c) === s && ++k > 1) return true; }
  return false;
};
```

The design argument is sound — *"A class is a statement that these elements are
the same sort of thing"* — but the implementation requires the class lists to be
**equal**, and every UI kit on the web marks the current item by **adding** a
token. The matched element then has no peer, `_isRecord` is false at every
ancestor, and `_climbTo` falls back to one hop.

Fixture is the exact Vuetify shape the comment above `_RECORD` describes: three
`div.menu-btn` rail items, each a label plus a count badge, the third carrying
`class="menu-btn active"` and nothing else different. `search_page(…, context_chars=120)`:

```
query=Orders   context='Orders 12 pending '     <- plain sibling: climb reaches the record
query=Basket   context='Basket'                 <- same markup + "active": climb gives up
```

Control — the identical page with the single word `active` deleted from that one
class attribute:

```
query=Orders   context='Orders 12 pending '
query=Basket   context='Basket 7 items '
```

So the only variable is the state class.

**What breaks.** The *selected* item in any nav rail, tab strip, stepper,
pagination control, filter chip row or cart badge — which is disproportionately
the thing a user asks about ("what's in my basket", "how many on the active
tab"). The eval-6 symptom this code was written to fix (*"asked for 120 context
characters and got 7"*) survives intact for exactly those elements.

**This is a repeat.** #30 records the identical mistake and its fix: *"`shapeOf`
includes the full class list, so the chosen option's extra state class split
three siblings into runs of 2 and 1 … displacing the SELECTED option, the one
member whose position an agent is most likely to trust."* Same defect, new
function, written after that entry.

Secondary, same function: the `_sig(e, 3)` fallback (used when no class is
declared) requires **exact** subtree-shape equality to depth 3, so a product
card list where one card has a "sale" badge and its neighbours do not is not a
record list either.

---

## F3 — A Tailwind colour utility erases a combobox's value — HIGH, DEMONSTRATED

`extension/background.js:7174-7175`

```js
if (!/(^|[_-])placeholder$|^placeholder([_-]|$)/.test(tok)) continue;
if (/^(text|bg|border|fill|stroke|ring|shadow|from|via|to|decoration|outline|caret|accent)-placeholder$/.test(tok)) continue;
```

The comment above it states the bug it is preventing: *"CSS-property utility
classes (Tailwind-style `text-placeholder`, `bg-placeholder`) are STYLING, not
state … Matching them marked a combobox reading 'Ontario' as (unselected), a row
that contradicts its own label."*

**The guard is on the wrong side of the hyphen.** Tailwind's placeholder utility
is `placeholder-{color}` (`placeholder-gray-400`), not `{property}-placeholder`.
The skip list catches the rare custom design token named `placeholder` and misses
the actual framework utility:

```
MARKS PLACEHOLDER placeholder-gray-400     token=true  tailwind-skip=false
MARKS PLACEHOLDER placeholder-transparent  token=true  tailwind-skip=false
MARKS PLACEHOLDER placeholder-opacity-50   token=true  tailwind-skip=false
ignored           text-placeholder         token=true  tailwind-skip=true
ignored           bg-placeholder           token=true  tailwind-skip=true
```

End to end, three byte-identical comboboxes all displaying `Ontario`, differing
only in that colour class:

```
ref_6  | div name="Province A" role=combobox (unselected) (collapsed)
ref_8  | div name="Province B" value="Ontario" role=combobox (collapsed)
ref_10 | div name="Province C" value="Ontario" role=combobox (collapsed)
```

One class token does **both** harms: `_showingPlaceholder` at `:8529` returns
`''` for the value, and at `:8905` sets `(unselected)`. The agent is told the
field is empty *and* shown no contents, on a field that plainly reads "Ontario"
— and `(unselected)` is then enumerated by `fill_form`'s submit failure path as
an unfilled field, and scored as a state word by `find` (#39).

**Two sibling sites have no guard at all**, so even `text-placeholder` trips
them: `:8449` (`w.querySelector('[class*="placeholder"]') || /placeholder/i.test(w.className)`)
and `:8938`. The same question — *"is this node a placeholder marker?"* — is
spelled three ways, and only one spelling has the Tailwind exception. That is
#21's one-concept-two-spellings with a measurable consequence.

**Honest prevalence.** `grep -lE 'class=\\?"[^"]*placeholder-(gray|slate|…)'`
over the 108-site frozen corpus returns **zero** sites. So this is #25's lesson
again — an ablation measures the code against the sample, and this sample does
not contain Tailwind v2's placeholder-colour utilities. The fixture is the
evidence; the corpus is not.

---

## F4 — `labelish()` rejects ASCII punctuation in page text, then attaches a neighbour's label — MED-HIGH, DEMONSTRATED

`extension/background.js:8969`

```js
const labelish = (t) => t && !/[{};<>]/.test(t);
```

This reads **page-authored prose** and decides "this is code, not a label" from
five ASCII punctuation characters. Two routine shapes fail it:

- **Greek.** The Greek question mark is ASCII `;` in practice (U+037E canonically
  decomposes to U+003B). Every interrogative label in Greek contains it.
- **Breadcrumbs and comparisons.** `Home > Products > Shoes`, `Price > $100`.

And the failure is not a missing hint — the walk keeps going outward and takes
the **previous field's** label. Two sibling field groups, English then Greek:

```
first   name='' near='Shipping address'
second  name='' near='Shipping address'      <- its own label is «Ποιος είσαι;»
```

Both unnamed fields now claim the same context. #37's NB1b dedupe does not save
this: it drops a shared hint only from rows that *have* their own identity, and
*"a row with no identity keeps whatever it can get."* `near=` counts as CONTENT
coverage in `find`'s scorer since #27, so an invisible-to-the-page attribution
reaches the **confident** tier — which is W19's end-to-end consequence arriving
by a different route.

**This is newly load-bearing.** The eval-6 heading-walk widening (`:9047`–`:9070`)
explicitly rests on it: *"The existing guards do the limiting, so this adds no
new one: `short()` refuses anything over 60 characters …, `labelish()` refuses
code."* The widened walk was built for Russian «Направление» and still cannot
pick up a Greek or breadcrumb label.

---

## F5 — `synthLabel` discards `data-*` labels containing ASCII brackets — MEDIUM, DEMONSTRATED

`extension/background.js:6925`

```js
if (!v || /[#>{}()\[\]]|->/.test(v)) continue;
```

Intended to reject machine handles (`click->modal#close`). It also rejects any
human label that qualifies its verb with parentheses or brackets — which is most
tooltips. Five icon-only buttons differing only in `data-tooltip`:

```
p1a  label=''                    iconOnly=True    data-tooltip="Delete (permanent)"
p1b  label='Delete permanently'  iconOnly=False   data-tooltip="Delete permanently"
p1c  label='削除（完全に）'        iconOnly=False   data-tooltip="削除（完全に）"
p1d  label=''                    iconOnly=True    data-tooltip="Supprimer (définitif)"
p1e  label=''                    iconOnly=True    data-tooltip="Export to CSV [beta]"
```

The asymmetry is **inverted** from the usual one — CJK fullwidth `（）` passes
and ASCII `()` does not — which is why it has never shown up in this project's
non-Latin work. When `data-*` is the only name source the control is listed as
`(unlabeled)`, which is PRINCIPLE §3.

A cheap structural test exists and is not used: the value contains a space and
no `://`, versus a machine handle which is one token.

---

## F6 — `find`'s no-space script list is a hardcoded block range — MEDIUM, DEMONSTRATED

`mcp_server.py:2692`

```python
if re.search(r"[一-鿿぀-ヿ฀-๿຀-໿ក-៿က-႟]", token):
    return 1.0 if token in text else 0.0
if re.search(r"\b" + re.escape(token) + r"\b", text):
    return 1.0
```

Scripts without word separators are routed to substring matching because Python
`\b` cannot find a boundary inside a run of `\w`. The range list is a chosen set
of Unicode blocks, and three common ones are outside it:

```
script                                      score   verdict
full-width katakana (covered)                 1.0   STRONG
HALF-width katakana  U+FF65-FF9F              0.1   weak/ignored -> fails coverage gate
CJK Ext-A  U+3400-4DBF                        0.1   weak/ignored -> fails coverage gate
CJK Compat U+F900-FAFF                        0.1   weak/ignored -> fails coverage gate
Hangul (spaces - correctly excluded)          1.0   STRONG
```

0.1 is the "buried in a word" weight, below the coverage gate, so the match is
not merely demoted — it stops counting as content coverage.

**What breaks.** Halfwidth katakana (`ｶﾅ`) is not exotic: Japanese bank, address
and enrolment forms *require* a halfwidth-katakana field, and legacy enterprise
UIs render labels in it. A query typed in the same form the page uses scores
0.1 while the full-width spelling of the same word scores 1.0.

Also missing: CJK Extension B+ (supplementary planes, used in personal names),
Katakana Phonetic Extensions, Yi, Tangut.

A declaration-based alternative exists —
`unicodedata.category` / the script property — which would need no list.

---

## F7 — UTF-16 counts as "is this a label / is this prose" tests — MEDIUM, DEMONSTRATED

Every one of these is a *character count* standing in for an *information*
quantity, and the two differ by roughly 4× between Latin and CJK:

| line | code | role |
|---|---|---|
| `:8965` | `(s && s.length <= 60) ? s : ''` | whether a sibling's text may become `near=` |
| `:9930` | `((e.text \|\| e.label \|\| '').length >= 20)` | whether a container counts as a generic wrapper |
| `:9968` | `if (lab && lab.length > 2) residual = residual.split(lab).join('')` | whether a child's label is subtracted |
| `:9972` | `residual.replace(/[\s\|·•,;:.\-—]/g, '').length < 12` | whether a card is demoted to decoration |
| `:6965` | `if (t && t.length <= 80) return t` | whether shadow-slotted text becomes a name |

Two structurally identical news cards, English and Japanese, same meaning, same
markup, `format="flat"`:

```
ref_4 | div "Everything you need to know about the new tariff rules Comments Business Politics"
...
PROBABLY DECORATION — 1 element(s) kept but not detailed … 1 container-suppression (ref_8)
```

`ref_8` is the Japanese card. Its headline 新関税ルールの全容 is gone from the
body of the listing; the English card keeps its row. Nothing about the two
differs except script.

Two of the five thresholds pull in **opposite** directions, which is the clearest
sign none of them measures what it is meant to:

- `:9972`'s punctuation strip is Latin-and-bullet only (`, ; : . - —`). CJK
  `、。「」・`, Arabic `، ؛ ؟` and the Devanagari danda `।` all **count** toward
  the 12, inflating the residual and *sparing* those scripts.
- `:9968`'s `lab.length > 2` skips subtracting any child label of 1–2 UTF-16
  units. Two-character CJK words (政治, 経済, 検索, 設定) are full words, not
  glyphs, so a CJK record's child labels are often **not** subtracted at all.
  My first fixture failed for exactly this reason and needed 4-character labels.

The code's own comment at `:9977` says *"Every number in this pass is chosen
rather than declared."* That is honest about the numbers; it does not say the
numbers mean different things in different scripts.

Severity is bounded by #28 — these demote rather than delete, and `_demoted` is
consumed only by the flat serializer (`:11986`), so the default tree format is
unaffected. `format="flat"` is a documented, supported output.

---

## F8 — Existence depends on an HTTP header — MEDIUM, DEMONSTRATED

`extension/background.js:6695`

```js
if (el.hasAttribute('onclick') || _hasHandlerProp(el)
    || el.hasAttribute('tabindex') || el.isContentEditable) return true;
```

`_hasHandlerProp` checks six events (`onclick`, `onpointerdown`, `onmousedown`,
`ontouchstart`, `onpointerup`, `onmouseup`); the attribute term checks **one**.
The comment two lines above identifies the exact mechanism — *"under a strict CSP
an inline handler attribute is never compiled, so hasAttribute is true while the
property is null, and neither term subsumes the other"* — and then implements
the guard for one sixth of the set.

Same three divs, with and without `<meta http-equiv="Content-Security-Policy"
content="script-src 'self'">`:

```
--- nocsp.html ---          --- csp.html ---
  c1  onclick               c1  onclick
  c2  onpointerdown         (c2 absent)
  c3  onmousedown           (c3 absent)
```

Under a CSP blocking inline script — the overwhelmingly common
`script-src 'self'` — a `<div onpointerdown>` is dropped as `not-interactive`
while a `<div onclick>` survives. The page declared the same thing both times;
only an HTTP header differs.

**Honest prevalence.** I found **zero** real inline `onmousedown=` /
`onpointerdown=` HTML attributes in the 108-site frozen corpus — the 16 and 13
HAR hits are JavaScript source strings, not markup. So the exposure is
unmeasured by any corpus here, and the finding rests on the mechanism.

---

## F9 — The tripwire cannot fire — MEDIUM, MEASURED

`tools/audit_patterns.py:88-101`

```python
TEXTY = re.compile(
    r"innerText|textContent|\btxt\b|\blabel\b|\bname\b|\bvalue\b|placeholder|"
    r"ariaLabel|aria-label|heading|caption|alt\b|title\b|query|\bq\b|\bterm\b", re.I)
...
texty = bool(TEXTY.search(line)) and not NOT_TEXTY.search(line)
if ASCII_CLASS.search(pat) and texty:
    cats.append("ascii-on-text")
```

**P4 ("no ASCII-only character class gates page text") passes because the
detector's "is this page text?" test is a regex over VARIABLE NAMES in the
source line.** I re-ran the auditor's own `ASCII_CLASS` scan with that gate
removed:

```
13 sites carry \w, \b or [a-z].  REPORTED: 0.  INVISIBLE: 13.
```

Every single one is invisible. A one-letter variable (`t`, `v`, `s`, `n`) makes
any ascii-on-text finding unreportable — F13 below is exactly that
(`/^[\w.:+-]+$/.test(v)`, where `v` is a page-authored attribute value).

Three further structural blind spots, each of which hides a finding above:

- **`ASCII_CLASS` matches only `[a-z…]`, `\w`, `\b`** — not punctuation classes.
  F4 (`/[{};<>]/`) and F5 (`/[#>{}()\[\]]/`) read page text with an ASCII
  character class and can never be categorised.
- **Only lines containing a JS regex literal are recorded at all.** So
  `querySelector('[class*="placeholder"]')` (F3's two unguarded sites) is
  structurally unseeable, and so is every `_kind(c) === s` style comparison (F2),
  which has no literal in it.
- **`WORDLIST` requires 3+ alternations of `[A-Za-zÀ-ɏ]{2,}`**, so a two-term
  English test is never a wordlist.

A detector that reports "0 findings" is worth nothing until it has been shown to
fire — the auditor's own docstring says so, and its self-test fires only on the
three historical patterns it ships with, all of which match on the *pattern*
side rather than through the texty gate.

**The self-audit's three sub-claims are correct, and I checked them:**
`classList.contains` → **0 sites** repo-wide (confirmed);
`.includes/.startsWith/.endsWith/.indexOf('<literal>')` in `background.js` →
14 occurrences, all CSS values (`url(`, `pre`, `inline`), ARIA role values
(`menuitem`), attribute-name prefixes (`aria-`, `data-`, `placeholder`) or our
own vocabulary (`__SCOPE_MISS__`, `clip:`, `table-header`, `overlay-banner`,
`(disabled)`) — confirmed; Python `'literal' in variable` → dict keys and
strings this repo emits — confirmed.

What the sweep misses is its own **shape**: it looks for a method call taking an
English literal. None of F2, F3, F4, F5 or F7 has that shape.

---

## F10 — One concept, two spellings: `parentElement` vs `composedParent` — MED-LOW, REASONED

`composedParent` is defined at `:5972` and used for the ancestor walk in two
places, each with a comment explaining why — e.g. `:7400`:

> *"composed, not parentElement: a combobox rendered inside a web component
> (Shoelace/Ionic/Vaadin selects) has its hidden native `<select>` on the far
> side of the shadow boundary, where the walk stopped dead and `backed-by=` /
> `(unselected)` both lost their only language-independent evidence."*

Roughly twelve other ancestor walks in the same function use `parentElement`,
which returns `null` at a shadow boundary. The ones that matter:

| line | walk | consequence inside a shadow root |
|---|---|---|
| `:6738` | cursor-inheritance owner (a **delete** rule) | no owner found → the citation-bracket spans come back as separate controls |
| `:8399` | 2-hop field-wrapper value hoist | a combobox's chosen value is never hoisted — the *same* walk `:7400` was fixed for |
| `:8934` | 2-hop `(unselected)` wrapper probe | the flag never fires |
| `:8996`, `:9047` | `near=` sibling and heading walks (incl. the new eval-6 widening) | no context hint |

#37 records this exact bug class being fixed in `_treeLines`: *"Six walks in
`_treeLines` climbed `parentElement`, which stops dead at a shadow boundary …
One of the six already did the composed walk by hand — #21's
one-concept-two-spellings, in the same function."* Same shape, different
function, still open.

The `:6738` instance fails in the *safe* direction (over-admit). `:8399` and
`:8934` do not — they silently withhold a value and a state flag for any
Shoelace/Ionic/Vaadin/UI5 select.

Not demonstrated: would need a shadow-DOM combobox fixture, which is ~20 minutes
and is the obvious next step.

---

## F11 — `frozenFade` only explains opacity — LOW-MED, REASONED

`extension/background.js:2372-2373`

```js
if (!_a.pending || _a.currentTime) continue;
if (_a.transitionProperty && _a.transitionProperty !== 'opacity') continue;
...
if (getComputedStyle(_t).opacity !== '0') continue;
```

The declared signal (`pending === true` with no start time) is excellent and is
genuinely spec-based. The **explanation** it produces is then narrowed to one
CSS property name by two separate filters.

An entry transition frozen the same way holds the element in its from-state
whatever it animates. The uncovered case is an element rendered **unmeasurable**
rather than transparent — a Bootstrap `.collapsing` accordion or a Headless UI
panel animating `height`/`max-height` from 0, or a `clip-path` reveal. The
collector drops it as not-visible (zero box), `frozenFade` does not count it, and
the agent gets **silence** where the opacity case gets a paragraph telling it to
use `query_elements`.

The `opacity !== '0'` check already does the real work, so the
`transitionProperty` term is a cheap pre-filter that buys little and narrows the
explanation. Severity is bounded: this is an explanation, not existence.

---

## F12 — A 2-option sentinel prompt is reported as a chosen value — LOW, REASONED

`extension/background.js:8872`

```js
if (!unselected && _o && el.selectedIndex === 0 && el.options.length > 2) {
```

#25's sentinel rule (`<option value="-1">Select</option>`) is skipped entirely
for a `<select>` with exactly two options. A minimal country or consent picker —

```html
<select><option value="-1">Select…</option><option value="US">United States</option></select>
```

— reports `value="Select…"` as a chosen value with no `(unselected)`, which is
the Amazon defect #25 was written for, re-opened by a chosen count. The
`seen < 6` sibling cap on the same loop is a second chosen number in the same
rule.

---

## F13 — ASCII class on declared constraint values — LOW, REASONED

`extension/background.js:9493`

```js
p.push(`${a.replace(/^aria-/, '')}=${/^[\w.:+-]+$/.test(v) ? v : JSON.stringify(v)}`);
```

`v` is a page-authored attribute value (`pattern`, `min`, `max`, `step`,
`accept`, `aria-valuenow`). JS `\w` is `[A-Za-z0-9_]`, so a bound written in
Arabic-Indic or Devanagari digits is quoted where the Latin spelling is bare:
`max=100` versus `max="١٠٠"`. Cosmetic only — nothing downstream parses it — but
it is the canonical example of F9's blind spot: the variable is named `v`, so no
version of the auditor can see it.

---

## Checked and CLEAN

A zero in an area is a result, so these were examined and found genuinely sound.

**Existence rules.** `isInteractive` (`:6645`) contains no class name, font name,
framework name or wordlist. The canvas class regex #27 claimed to remove really
is gone from **both** copies (the second one, which drove the `(canvas)` marker,
is now also gone). The pixel thresholds around `<svg>`/`<canvas>` (`:7271`,
`:7298`, `:7348`) only `_note` (demote) — the one `_drop` on that path is
`canvas-measure-failed`, a measurement-error path in L10c's permitted set.

**Wordlists.** No natural-language word list reads page prose anywhere. Every
`new Set([...])` literal in `background.js` is HTML tag names or ARIA roles. The
`_isSentinel` list (`-1|0|default|none|null|undefined`) is attribute-value
convention; the `_boolish` list is the *caller's* vocabulary; `_STOP` /
`_FIELD_STOP` / `_CLIMB_STOP` are HTML tag names; the icon-library prefixes are
attributed on the row when used.

**Duplicate-copy integrity.** `_hasHandlerProp` — 5 copies, byte-identical, and
the event list matches `listener_tag.js`'s `ACTIVATION` set exactly.
`i18n:norm` — 4 copies, byte-identical, and the normalisation is correct:
`\p{Mn}` (not `\p{M}`, which would strip Devanagari matras) with the
U+3099/U+309A kana-voicing exception, and a final NFC. `dup:decoyscope` — 2
copies, behaviourally identical. `dup:fieldstop` — `_FIELD_STOP` (`:6571`) and
`_CLIMB_STOP` (`:13348`) hold the same 13 tags. The placeholder token regex has
exactly **one** copy, so F3 is a hole rather than a drift.

**Digit handling.** The bare-number `near=` rule uses `/^\p{Nd}{1,6}$/u`, not
`\d` — correct for Arabic-Indic, Devanagari, Thai and fullwidth, and the comment
says why.

**`listener_tag.js`.** No pattern matching on page content at all. The only
constants are a DOM event-name set and two ring caps. Clean.

**`panel.js`.** Five regexes, all against our own op names (`^(get_|read_|…)`)
and URL schemes (`^(https?:|data:)`). Nothing reads page text. Note that it
renders page-controlled tab titles and URLs with extension privileges, and it
does so via `textContent` throughout, which is right.

**Python flow layer.** `'literal' in variable` sites are dict keys and strings
this repo emits. `core/flows/model.py:85`'s `[^A-Za-z0-9]+` is a *filesystem*
sanitiser on a flow name (and Python `\w` elsewhere is Unicode-aware), not a
content gate.

---

## What I did not cover

The three subagents covering `background.js:1–6500`, `background.js:10500–end`
and the Python side all terminated on the account's weekly API limit without
returning. They are resumable. Specifically **not** audited by me:

- the op router, permission gate, CDP input path, `_pickOptionPage` /
  `fillDropdown` / `_detectSubmitPage` (lines 1–6500) — note F3's
  `(unselected)` consumers reach into `fill_form`'s unfilled enumeration, so
  that path is worth the pass;
- the tree and flat serializers, the fold signature `shapeOf`, the entry cap and
  the legend (lines 10500–16255), except `_searchTextPage`, which I audited;
- `mcp_server.py` beyond `find`'s `_hit` scorer, and `core/flows/*` beyond the
  literal sweep.

The cheapest high-value follow-ups, in order: a shadow-DOM combobox fixture for
F10; an `isInteractive` ⊇ `keepForFind` assertion for F1 (it is a pure source
property and could be a contract test); and widening `audit_patterns.py` past
the texty gate for F9, which is what would have surfaced F13 without a human.
