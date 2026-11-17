# Non-regex pattern surface — classification and defects — 2026-11-17

**Scope.** The nine files `tools/audit_patterns.py` scans (imported from its
`FILES`, not restated): `extension/background.js`, `extension/listener_tag.js`,
`extension/panel.js`, `mcp_server.py`, `core/flows/{descriptor,recorder,runner,model,secrets}.py`.
Read-only: no source file was modified. Patches below are diffs for the owner to apply.
Working tree was `5d3752b` plus other agents' uncommitted edits, so **line numbers drift;
every site is quoted so it can be found by text.**

**What was built.** `tools/audit_pattern_surface.py` — enumerates the pattern surface that
`audit_patterns.py` cannot see (it reads regex literals only; this adds `.includes` /
`.indexOf` / `.startsWith` / `.endsWith` / `.has`, `classList`, `getAttribute('data-…')`,
`x === 'literal'`, CSS selector strings in `querySelector*`/`matches`/`closest`, word-list
constants, `.slice`/`.substring` cuts, numeric thresholds, case-fold comparisons, and the
regex literals only for the modes the old tool lacks: `\d`/`[0-9]` and `\b`-beside-non-ASCII).
`--self-test` plants 22 historical bugs from #21/#24/#28/#29/#37/#71 in pre-fix form and
asserts each fires, plus 9 negative controls that must stay quiet, plus a corpus-size floor
(a detector scanning nothing is silent too). **Result: 22/22 fire, 9/9 quiet.**

**Baseline.** `node --check extension/background.js` OK. `audit_patterns.py`: 293 regex sites,
self-test 3/3. `test_patterns.py` 18/18. This tool adds **860 non-regex sites**, so the regex
auditor was seeing 293 of ~1,153 (25%), matching #71's ~26%.

---

## Headline

1. **One high-severity defect, and it is not a pattern the project already tracks:** an
   unpaired UTF-16 surrogate in *any* string a tool returns **kills the MCP server process**.
   It needs no cut by us — a page's own text, `document.title`, or a site that truncated an
   emoji with `.slice()` is enough (D1). Reproduced end to end.
2. **Five medium/low defects reproduced** with a concrete input (D2–D5, D9), and **three
   latent/unproven** (D6, D7, D8).
3. **The project's headline claims survive.** No natural-language wordlist reads page text
   (25 `english-wordlist` sites, all attribute names, the caller's own vocabulary, or our
   protocol). `locale-dependent` = 0 sites (OC6 holds). `attr-vs-property` = 0 sites (F1
   from #71 is closed everywhere). Every `ascii-on-text` site is ASCII by spec or by our own
   syntax.
4. **A correction to #71.** #71 F5 says ARIA role matching is ASCII-case-insensitive and
   Chrome resolves `role="BUTTON"` to `button`. **Measured on Chrome 153, it does not**:
   `role="BUTTON"` and `role="Combobox"` are `text` in Chrome's own AX tree; token lists
   (`"button link"`) and leading whitespace are honoured. So the token-list half of F5 is
   real and the case-insensitivity half is wrong — and `_roleHit`'s `.toLowerCase()`
   *over-admits* things Chrome ignores. See D6.

---

## Counts

A site may carry several modes; the table counts a site once per mode it carries.
`risky` = at least one non-benign mode.

```
860 non-regex-surface sites across 9 files (294 carry at least one risky mode)

mode                  sites
ascii-on-text             8
english-wordlist         25
framework-name           23
class-substring          15
fixed-threshold         114
latin-digit              18
surrogate-unsafe         37
locale-dependent          0
exact-role-string        90
attr-vs-property          0
data-attr                25
benign-css-value         38
benign-spec-list        424
benign-structural       104

file                         ascii-on- english-w framework class-sub fixed-thr latin-dig surrogate locale-de exact-rol attr-vs-p data-attr   risky
extension/background.js              0        19        23        13        92        12        36         0        90         0        24     253
extension/listener_tag.js            0         0         0         0         1         0         1         0         0         0         0       1
extension/panel.js                   0         2         0         2         0         2         0         0         0         0         1       7
mcp_server.py                        3         2         0         0        11         0         0         0         0         0         0      16
core/flows/descriptor.py             0         2         0         0         2         0         0         0         0         0         0       4
core/flows/recorder.py               3         0         0         0         6         2         0         0         0         0         0       9
core/flows/runner.py                 0         0         0         0         1         0         0         0         0         0         0       1
core/flows/model.py                  2         0         0         0         0         2         0         0         0         0         0       2
core/flows/secrets.py                0         0         0         0         1         0         0         0         0         0         0       1
```

`benign-spec-list` (424) is dominated by tag lists, ARIA roles, input types and CSS
keywords; `benign-css-value` (38) by `cs.position === 'fixed'`-style tests;
`benign-structural` (104) by own-marker tests and variable arguments.

**Verdict provenance, stated plainly.** 294 sites are risky. The rows tagged
`REPRODUCED` below (D1–D5, D9, plus the D3 divergence) were run with a concrete input. The
`known`/`benign`/`diag` rows in the appendix are **group verdicts assigned by a rule table
keyed on the quoted line**, each naming the spec/CSS fact or the in-repo entry it reads; I
read the surrounding code for every group but did **not** reproduce each individual row.
Nothing is left `UNREVIEWED`.

---

## Ranked defects

### D1 — an unpaired surrogate in any tool result crashes the MCP server — HIGH — REPRODUCED

**Where.** There is no scrub anywhere between `core/bridge/server.py:344`
(`msg = json.loads(raw)`) and the tool return. The surrogate-unsafe cuts in
`background.js` (37 sites, 21 non-diagnostic) can *create* one, but are not needed:
**a page can contain one natively.**

**Reproduction (four independent steps, all run).**

1. A browser keeps one: `document.getElementById('a').textContent = 'ab\ud83d'` →
   `innerText.length === 3`, `charCodeAt(2) === 0xd83d`; `document.title = 'hi\ud83d'` the same.
   `JSON.stringify` emits the well-formed escape `"ab\ud83d"`, so it crosses the WebSocket.
2. The bridge's `json.loads` rebuilds an **unpaired surrogate `str`**.
3. Through the real tool functions with a fake bridge returning that: `get_url` returns
   `'{"url": "https://x.test/", "title": "hi\ud83d"}'` and `get_page_text` returns
   `'Product name \ud83d\nPrice 5'` — both then fail `TextContent(...).model_dump_json()` with
   `PydanticSerializationError: UnicodeEncodeError: 'utf-8' codec can't encode character
   '\ud83d' ... surrogates not allowed`.
4. Over the real stdio transport (same `mcp` version as `.venv`): a tool returning
   `"ab\ud83c"` → `ExceptionGroup: unhandled errors in a TaskGroup` →
   **the process dies and the next `tools/call` in the same session is never answered.**

`mcp_server.py` deliberately uses `json.dumps(..., ensure_ascii=False)` (C23, #63) so
non-Latin text is not escaped. With the default `ensure_ascii=True` a lone surrogate would
have been escaped harmlessly; the C23 tripwire is correct and is what lets this through.

**Not demonstrated:** a *tab title* carrying a lone surrogate through `chrome.tabs` (Chrome
may sanitise it); page text and `document.title` are demonstrated at the DOM level.
Real sites produce lone surrogates routinely (truncated snippets, `substr` on emoji).

**Replacement (reads a declaration: "is this valid UTF-8").** Scrub at the single ingress,
`core/bridge/server.py` after `json.loads`:

```diff
@@ core/bridge/server.py  (module level)
+def _scrub(o):
+    """Replace UNPAIRED surrogates with U+FFFD. A valid pair is already one astral
+    code point in a Python str after json.loads, so it is untouched."""
+    if isinstance(o, str):
+        try:
+            o.encode("utf-8")
+            return o
+        except UnicodeEncodeError:
+            return o.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
+    if isinstance(o, list):
+        return [_scrub(x) for x in o]
+    if isinstance(o, dict):
+        return {_scrub(k): _scrub(v) for k, v in o.items()}
+    return o
@@ line 344
-                    msg = json.loads(raw)
+                    msg = _scrub(json.loads(raw))
```

Verified in isolation (`scratchpad/p_scrub.py`): `'hi\ud83d'` → `'hi�'`, a valid
`😀` pair survives as `😀`, nested keys/values scrubbed, and the result
serialises. A test belongs beside C23: feed the bridge a frame containing `\ud83d` and
assert a tool result round-trips through `TextContent(...).model_dump_json()`. Fixing the
cut sites at the source (swap each bare `.slice(0, N)` for the existing `markCut`) is
worthwhile but secondary — **it cannot fix the page-native case.** Not run against the full
suite.

---

### D2 — the fallback option picker rejects any row longer than 80 UTF-16 units — MEDIUM — REPRODUCED

`extension/background.js:3597`, `:4036`, `:4801` (three copies):

```js
const t = (r.innerText || '').trim();
if (!t || t.length < 1 || t.length > 80) return false;   // 4036/4801: if (!t || t.length > 80) return false;
```

**Reproduction** (`scratchpad/p_opt80.py`, real `_pickOptionPage` extracted with
`_extract`). A role-less popover of three clickable `div` rows, one target:

| row length | result |
|---|---|
| 40 | `ok: True` |
| 70 | `ok: True` |
| 90 | `ok: False` — `no option matched …` |
| 130 | `ok: False` |

An 80-*unit* cliff means Latin rows (address autocompletes, timezone/plan descriptions; #25
already recorded a 413-char timezone option) silently stop being pickable, while 80 units of
CJK is ~80 words and passes. The number is not declared by any document. The length test is
doing the job of "is this a leaf row, not the wrapper holding all the rows".

**Replacement (structure instead of a number — a row is a leaf).**

```diff
-          const t = (r.innerText || '').trim();
-          if (!t || t.length < 1 || t.length > 80) return false;
+          const t = (r.innerText || '').trim();
+          if (!t) return false;
@@ after the .filter(...) that builds `rows`, before `const byParent = new Map();`
+        // a wrapper that CONTAINS another candidate row is a container, not an option
+        for (let i = rows.length - 1; i >= 0; i--)
+          if (rows.some(o => o !== rows[i] && rows[i].contains(o))) rows.splice(i, 1);
```

Verified on the same fixture: 40 / 70 / 90 / 130-unit rows all `ok: True`. **Not run against
`test_widgets.py`**; the existing sibling-cluster rule (`bestSize >= 2`) and the W17 decoy
checks are the ones to run before applying.

---

### D3 — two copies of the "is the placeholder showing" rule diverged — MEDIUM — REPRODUCED (consequence read, not run)

`_triggerEvidencePage.marked` (`background.js:4206`, feeds `hasPlaceholderAttr` into
`fillDropdown`'s pick verification) versus the collector's `_phMarked` (`:7244`). The
comment at the first says *"Kept in step deliberately — this evidence decides whether
fillDropdown believes a pick landed"*. They are not in step: `_phMarked` skips CSS-property
utilities (`text-placeholder`, `bg-placeholder`, …), `marked` ends in
`return /(^|[\s_-])placeholder([\s_-]|$)/.test(cn)`.

**Reproduction** (`scratchpad/p_ph.py`), same markup in both:

```
<button class="text-placeholder" role="combobox" aria-haspopup="listbox">Ontario</button>
collector listing:           button value="Ontario" role=combobox            (correct)
_triggerEvidencePage():      hasPlaceholderAttr = True                       (wrong)
```

This is the F3 defect from `AUDIT-PATTERNS-2026-11.md` fixed in one copy only: **#21's
"one concept, two spellings"** with a comment asserting the copies agree. Consequence (read,
not run): a filled Tailwind combobox is judged to still show its hint, so `fillDropdown`'s
before/after comparison mis-reads a successful pick; a retry on a multi-select toggles it
back off (#25).

**Replacement.** One copy, byte-identical, enforced like P2: port the exclusion into
`marked` and tag both `i18n:placeholder`-style so `test_patterns.py` P2 fails on drift.

```diff
@@ extension/background.js  _triggerEvidencePage, after `const cn = ...`
-      return /(^|[\s_-])placeholder([\s_-]|$)/.test(cn);
+      for (const tok of String(cn).split(/\s+/)) {
+        if (!/(^|[_-])placeholder$|^placeholder([_-]|$)/.test(tok)) continue;
+        if (/^(text|bg|border|fill|stroke|ring|shadow|from|via|to|decoration|outline|caret|accent)-placeholder$/.test(tok)) continue;
+        return true;
+      }
+      return false;
```

(The utility-prefix list is itself a framework-name list — the audit's own D-class — but it
is the *existing* shipped rule, and the two copies must at least agree.)

---

### D4 — page-author `data-*` attributes printed as state tokens — MEDIUM-LOW — REPRODUCED

`background.js:6418` (`data-state` ∈ `active|open|on|checked`), `:6486`
(`data-active === 'true'` → `(active)`), `:6487` (`data-current === 'true'` → `(current)`),
all inside `activeHint`, which writes the row's state token.

**Reproduction** (`scratchpad/p_state.py`, real collector):

```
<a href="/a" data-current="true">Home</a>      ->  a "Home" (current)
<a href="/b" data-active="true">Blog</a>       ->  a "Blog" (active)
<button data-state="on">Save</button>          ->  button "Save" (on)
```

None is ARIA, HTML or a CSS value. `data-state` is a Radix/Headless convention;
`data-active`/`data-current` are invented by no spec and no major library. #29 deleted the
class-token equivalent *because a wrong `(current)` tells the agent not to click the thing it
needs*, and measured it dead (0 effect across 99 pages) — but the `data-*` spellings survived
that deletion. The wider caveat from #80 applies: the corpus is what it is.

**Replacement.** Delete 6486–6487 outright (no declaration reads them). For `data-state`,
gate on the library actually using it: only when the same element declares the paired ARIA
(`aria-expanded` for open, `aria-checked` for checked) or is inside `[role=tablist]`, i.e.
let the declared signal speak and use `data-state` only as a tiebreak, exactly as #29's
tabs rule orders its signals. Measure with the `__abNamedPopoverOnly`-style counter first
(see D7) so the deletion is evidence-based.

---

### D5 — names are accepted only if short — LOW-MEDIUM — REPRODUCED for one of three

`background.js:7057` (shadow-slotted text `<= 80`), `:7110` (card caption `<= 40`),
`:7120` (`::before`/`::after` `content` `<= 40`). `synthLabel` takes a declared name **only
if** it is under a bound; otherwise the control is `(unlabeled)`.

**Reproduction** (`scratchpad/p_label.py`, real collector, `.x::before{content:"…"}` on an
empty `<button>`):

```
 5 units  -> button "Close"
28 units  -> button "Close this dialog and return"
53 units  -> button (unlabeled-icon)                       <-- Chrome names this from ::before
26 CJK    -> button "关闭此对话框并返回上一页面然后继续浏览其他内容吧好的"   (still named: 26 units)
```

Chrome's AccName includes generated content (2F.iii), so the 53-unit control has a
declared name and we print none. This is #24's "no per-field truncation" decision
(`markCut` deleted, 0.3% cost) not having reached `synthLabel`'s *rejection* bounds — the
earlier sweep removed caps that *cut*, and these *refuse*. The 80/40 shadow and caption
branches have the same shape but were **not individually reproduced**.

**Replacement.** Drop the bound; keep the `\p{L}\p{N}` guard (a declared name, any script):

```diff
-            if (c && c.length <= 40 && /[\p{L}\p{N}]/u.test(c)) return c;
+            if (c && /[\p{L}\p{N}]/u.test(c)) return c;
```

For the card caption (`pt.length <= 40`) the bound is standing in for "this is a caption,
not the card's whole body"; the `_peers` group guard just above it already answers that
structurally. Both need a corpus A/B (#19, interleaved) before shipping — the cost half is
not measured here.

---

### D9 — `find` drops one-character tokens and hard-codes three CJK ranges — LOW — REPRODUCED

`mcp_server.py:2669` (`if len(t) > 1 and t not in _STOP`) and `:2822`
(`not re.search(r"[^一-鿿぀-ヿ가-힯]", t)`).

**Reproduction** (`scratchpad/p_find.py`, real `find` with a fake bridge):

```
label "猫"  query "猫"        -> NO CONFIDENT MATCH ... only weakly     (2-char "猫猫" -> Found 1)
label "车票" query "车 票"    -> No elements matched
label "ค้นหา" (Thai) query "ค้นหากล่อง" -> No elements matched
"㐀㐁" (CJK Ext-A) / "ｶﾀｶﾅ" (halfwidth) prefix queries -> No elements matched
```

A single Han/Kana/Hangul character is a *word*; the `> 1` test is English-shaped (it exists
to drop "a"/"I"). Thai/Khmer/Lao have the same no-spaces problem the 2822 branch solves for
Han and are outside its ranges (`AUDIT-PATTERNS-2026-11.md` F6). **Only the 1-char drop is
proven to change an outcome; the range gaps are shown to produce "No elements matched" but I
did not isolate them from `find`'s other gates.**

```diff
-              if len(t) > 1 and t not in _STOP]
+              if (len(t) > 1 or unicodedata.name(t, "").startswith(
+                      ("CJK", "HIRAGANA", "KATAKANA", "HANGUL"))) and t not in _STOP]
```

Verified in `scratchpad/p_find.py --patched`: `猫`→Found 1, `车 票`→Found 1, `猫 按钮`→Found
1 (was Found 2), 1-char Latin control unchanged. Not run against `test_find.py` (needs
`import unicodedata`). The Unicode *category* of the script, not a hand-kept range list, is
the structural replacement for 2822 too: `unicodedata.category(c)[0] == "L"` with
`unicodedata.name` prefixes, or the `regex` module's `\p{Script=…}`.

---

### D6 — `role` compared as one raw string at ~60 sites — LOW (latent; 0 observed) — REPRODUCED shape

90 sites read `getAttribute('role')` or compare `role === '…'`. Only `_roleHit`
(`background.js:6542`) tokenises. Measured in Chrome 153 (`scratchpad/p_role.py`,
`aria_snapshot`):

```
role="combobox"            -> combobox        _fieldKindPage.is_combobox True
role="Combobox"            -> text            is_combobox False   (we agree with Chrome)
role="combobox listbox"    -> combobox        is_combobox False   (we disagree)
role=" combobox"           -> combobox        is_combobox False   (we disagree)
```

So `fill_form`'s kind probe (`_fieldKindPage`, `:3120`; twin at `:15462`) types text into a
dropdown Chrome says is a combobox when the author wrote a token list or padding — the
failure its own header comment describes ("typing into them sets nothing"). **#71 found 0 of
6,632 real `role=` attributes carrying a token list or padding, so this is a spec
divergence with no observed instance.** One helper fixes all 90: return the first token
Chrome would accept, case-sensitively:

```js
const _roleOf = (el) => { const v = el.getAttribute('role'); if (!v) return '';
  for (const t of v.trim().split(/\s+/)) if (ARIA_ROLES.has(t)) return t; return ''; };
```

and `_roleHit` should drop its `.toLowerCase()` (over-admits `role="BUTTON"`, which Chrome
treats as plain text). **That second half is a behaviour change on a spec question; decide it
deliberately** — admitting more than the browser's own AX tree is the safe direction.

---

### D7 — library portal selectors: 4 of 5 copies cannot prove they are dead — LOW — READ

`'[data-radix-popper-content-wrapper], [data-popper-placement], [data-floating-ui-portal]'`
appears at `background.js:3377`, `:3564`, `:4009`, `:4076`, `:4778`. #29 replaced the
candidate list with structure and instrumented the first copy
(`window.__abNamedPopoverOnly`, `:3384`) so that if the name list is never the sole source it
can be deleted "on the evidence". **Only that one copy carries the counter**, and the other
four are the same list in `_pickOptionPage`/`fillDropdown` paths. An ablation of one copy
says nothing about the rest (#21). Replace with one shared structural helper (rendered,
out-of-flow or stacked, not containing the trigger — the test #29 already wrote at 3377) and
delete the names; or instrument all five before deciding. Not reproduced — it is a
provability gap, not an observed failure.

---

### D8 — validation errors are found by a class-name list — LOW-MEDIUM — READ, not reproduced

`background.js:~15838–15845`, fill_form's submit-error sweep:
`.error, .invalid, .field-error, .form-error, .text-destructive, .text-red-500, .text-red-600,
.text-red-700, [data-state="error"], .invalid-feedback, .is-invalid, .Mui-error,
.ant-form-item-explain-error, .mat-error, .error--text, .v-messages__message`.
What it returns is reported to the agent as *visible validation errors*. The comment calls
it a last-resort hint. It cannot see a site using other class names (`fehler`, `erreur`, any
CSS-module hash) and can report non-error text styled with `.error`/`.invalid`.
The declared signals already exist and #37 prints them per field: `aria-invalid="true"`,
`aria-errormessage`, `aria-describedby`, `role=alert`, `aria-live`. **Replacement:** take the
union of those only (they are already the first half of the same selector), and ablate the
class half over the corpus the way #24 ablated `_phWord`. I did not run the ablation, so
whether the class half "carries nothing" is unmeasured.

---

## Investigated and REJECTED / INCONCLUSIVE

* **`toLocale*Case` locale hazard.** Not present: `locale-dependent` = 0 sites, and the
  detector fires on a planted `toLocaleLowerCase()` with no locale. OC6 holds. (#71 already
  retracted the V8 behaviour.)
* **`hasAttribute('on…')` without the handler property (#71 F1).** `attr-vs-property` = 0
  sites — every attribute read has the property read beside it. The detector fires on the
  planted pre-fix form and stays quiet on the control.
* **A natural-language wordlist reading page text.** None. All 25 `english-wordlist` sites
  are: the caller's boolean/toggle vocabulary (`'true','yes','on','checked'` — #66
  dispositioned it), attribute *names* (`placeholder`, `data-`, `aria-`), HTML element/input
  lists, or our own protocol vocabulary (`msg.kind === 'steer'`).
* **Default English names `Submit`/`Reset` for `<input type=submit|reset>` with no value
  (`background.js:9827`).** Chrome's real default label is localised, so a non-English UI
  would disagree with our hard-coded English. **Could not demonstrate**: headless Chromium
  (`--lang=de-DE`, `locale='de-DE'`) reports `button "Submit"` regardless, because the
  Playwright build ships en-US strings only. Left as an unproven low-severity suspicion.
* **Fold/compaction minimums (`members.length < 6|8|10`, `l.length > 56`).** Presentation
  only — every member keeps its own ref and label, and #19 measured `fold-min-members` as a
  gentle 4.3% slope. Not an existence decision.
* **Latin-digit regexes (18).** Gutter/line-number tests hit ASCII digits by construction;
  the rest are CSS colour syntax, URL schemes, `ref_N`, env-var names. The only non-Latin
  exposure is the bare-counter filter `^\d{1,4}$` at `:15858`, which would pass an
  Eastern-Arabic counter into the error list — LOW, folded into D8.
* **`find`'s role-word `isascii()` proxy (3 sites).** Decides "spaced vs spaceless script"
  for the containment rule (#25). It mis-sorts ASCII-free *non-CJK* spaceless scripts (Thai)
  but is a ranking proxy, not an existence gate — folded into D9.
* **CJK range gap as a standalone defect.** Han `搜索框` (not a role word) is also only a
  *weak* match, so the Han-versus-Thai comparison does not isolate the range gate. Only the
  1-char token drop is claimed.
* **Hostile `document.title` via `chrome.tabs`.** The DOM keeps the lone surrogate
  (demonstrated) but I did not confirm `chrome.tabs.get().title` preserves it. D1 does not
  depend on it — page text does.

## What the tool cannot see (so "0 findings" is bounded)

`switch (x) { case 'lit': }` string cases; selectors built by concatenation; wordlists held
in an object keyed by text (`MAP[text]`); `Set.has(variable)` where the Set is defined in
another function (only literal-set *definitions* are scanned); template-literal
interpolations (treated as strings, as `_extract.code_mask` does); Python `in` with a
variable right-hand tuple. Sites reached only through those are counted as zero. The
self-test proves each *detector* fires; it does not prove coverage of the surface.

---

## Appendix — every risky site

Format: `file:line` **mode** · tag · verdict · quoted line. Tags: `DEFECT:Dn` (see above),
`known` (documented in CLAUDE.md or an in-file comment, low), `benign`, `diag` (diagnostic
path). Group verdicts, not row-by-row reproduction, except where the verdict says REPRODUCED.


### surrogate-unsafe (37)

- `extension/background.js:433` **diag** — diagnostic / url text. JSON.stringify escapes a lone surrogate to the ASCII text \udXXX, so nothing invalid leaves the page; but the string still reaches Python as an unpaired surrogate if the server relays it (D1).
  `'ChromeBridge could not determine an origin for this tab (url=${JSON.stringify(String(g.url).slice(0, 120))}), ' +`
- `extension/background.js:861` **diag** — diagnostic / url text. JSON.stringify escapes a lone surrogate to the ASCII text \udXXX, so nothing invalid leaves the page; but the string still reaches Python as an unpaired surrogate if the server relays it (D1).
  `if (host && host !== me) bad.push({ id: host, url: u.slice(0, 100) });`
- `extension/background.js:909` **diag** — diagnostic / url text. JSON.stringify escapes a lone surrogate to the ASCII text \udXXX, so nothing invalid leaves the page; but the string still reaches Python as an unpaired surrogate if the server relays it (D1).
  `try { const t = await chrome.tabs.get(tabId); url = String((t && t.url) || ''); where = ' url=${url.slice(0, 80)}'; } catch (e) {}`
- `extension/background.js:946` **diag** — diagnostic / url text. JSON.stringify escapes a lone surrogate to the ASCII text \udXXX, so nothing invalid leaves the page; but the string still reaches Python as an unpaired surrogate if the server relays it (D1).
  `try { const t = await chrome.tabs.get(tabId); where = ' url=${String(t && t.url).slice(0, 80)}'; } catch (e3) {}`
- `extension/background.js:1143` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `((t.innerText || '').trim() ? ' "' + (t.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 40) + '"' : '');`
- `extension/background.js:1274` **diag** — diagnostic / url text. JSON.stringify escapes a lone surrogate to the ASCII text \udXXX, so nothing invalid leaves the page; but the string still reaches Python as an unpaired surrogate if the server relays it (D1).
  `} catch (e) { _lastErr = String(e && e.message || e).slice(0, 90); }`
- `extension/background.js:1284` **diag** — diagnostic / url text. JSON.stringify escapes a lone surrogate to the ASCII text \udXXX, so nothing invalid leaves the page; but the string still reaches Python as an unpaired surrogate if the server relays it (D1).
  `} catch (e) { _lastErr = String(e && e.message || e).slice(0, 90); }`
- `extension/background.js:2153` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `return { ok: false, error: String(desc).slice(0, 4000) };`
- `extension/background.js:3810` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `return { ok: true, actual: (pick.innerText || '').trim().slice(0, 60),`
- `extension/background.js:3830` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `text: (pick.innerText || '').trim().slice(0, 60),`
- `extension/background.js:3863` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `const _picked = (pick.innerText || '').trim().slice(0, 60);`
- `extension/background.js:4271` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `return { label: (el.innerText || el.value || '').trim().slice(0, 80), hasPlaceholderAttr, backing };`
- `extension/background.js:4369` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `label: (chosen.innerText || chosen.value || chosen.getAttribute('aria-label') || '').trim().slice(0, 60),`
- `extension/background.js:4607` **diag** — diagnostic / url text. JSON.stringify escapes a lone surrogate to the ASCII text \udXXX, so nothing invalid leaves the page; but the string still reaches Python as an unpaired surrogate if the server relays it (D1).
  `tr('open-click', open && { ok: open.ok, msg: (open.msg || '').slice(0, 120) });`
- `extension/background.js:4666` **diag** — diagnostic / url text. JSON.stringify escapes a lone surrogate to the ASCII text \udXXX, so nothing invalid leaves the page; but the string still reaches Python as an unpaired surrogate if the server relays it (D1).
  `try { await clickTrusted(tabId, origSelector); } catch (e) { tr('clickTrusted threw', String(e).slice(0, 120)); }`
- `extension/background.js:4672` **diag** — diagnostic / url text. JSON.stringify escapes a lone surrogate to the ASCII text \udXXX, so nothing invalid leaves the page; but the string still reaches Python as an unpaired surrogate if the server relays it (D1).
  `try { await clickTrusted(tabId, origSelector); } catch (e) { tr('clickTrusted threw', String(e).slice(0, 120)); }`
- `extension/background.js:4683` **diag** — diagnostic / url text. JSON.stringify escapes a lone surrogate to the ASCII text \udXXX, so nothing invalid leaves the page; but the string still reaches Python as an unpaired surrogate if the server relays it (D1).
  `tr('typed-into-popover-search', typed && { ok: typed.ok, msg: (typed.msg || '').slice(0, 120) });`
- `extension/background.js:4815` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `return els.slice(0, 6).map(o => (o.innerText || '').trim().slice(0, 40)).filter(Boolean);`
- `extension/background.js:4853` **diag** — diagnostic / url text. JSON.stringify escapes a lone surrogate to the ASCII text \udXXX, so nothing invalid leaves the page; but the string still reaches Python as an unpaired surrogate if the server relays it (D1).
  `} catch (e) { tr('escape threw', String(e).slice(0, 120)); }`
- `extension/background.js:5124` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `? raw.slice().sort((a, b) => _pri(a) - _pri(b)).slice(0, FRAME_CAP)`
- `extension/background.js:5918` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `text: (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60),`
- `extension/background.js:8433` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `text: o ? (o.text || '').trim().slice(0, 60) : '',`
- `extension/background.js:8624` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `if (ph && (ph.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 60) === t) {`
- `extension/background.js:9249` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `groupName = (ganc.getAttribute('aria-label') || '').trim().slice(0, 40);`
- `extension/background.js:10309` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `const nm = (g.getAttribute('aria-label') || '').trim().slice(0, 30);`
- `extension/background.js:13256` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `try { if (el.value != null && typeof el.value === 'string') parts.push('v:' + el.value.length + ':' + el.value.slice(0, 24)); } catch (e) {}`
- `extension/background.js:14248` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `name: nm.trim().slice(0, 300),`
- `extension/background.js:14421` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `text: ((el.innerText || el.textContent || '').trim()).slice(0, 100),`
- `extension/background.js:14422` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `class: (el.className || '').toString().slice(0, 120),`
- `extension/background.js:14864` **diag** — diagnostic / url text. JSON.stringify escapes a lone surrogate to the ASCII text \udXXX, so nothing invalid leaves the page; but the string still reaches Python as an unpaired surrogate if the server relays it (D1).
  `: '\nTrusted retry failed to start: ${em.slice(0, 160)}';`
- `extension/background.js:14941` **diag** — diagnostic / url text. JSON.stringify escapes a lone surrogate to the ASCII text \udXXX, so nothing invalid leaves the page; but the string still reaches Python as an unpaired surrogate if the server relays it (D1).
  `extensionId: t.extensionId, url: String(t.url || "").slice(0, 90) }));`
- `extension/background.js:14953` **diag** — diagnostic / url text. JSON.stringify escapes a lone surrogate to the ASCII text \udXXX, so nothing invalid leaves the page; but the string still reaches Python as an unpaired surrogate if the server relays it (D1).
  `url: String(f.url || "").slice(0, 90) }));`
- `extension/background.js:15402` **diag** — diagnostic / url text. JSON.stringify escapes a lone surrogate to the ASCII text \udXXX, so nothing invalid leaves the page; but the string still reaches Python as an unpaired surrogate if the server relays it (D1).
  `fields.forEach((f, i) => dbg('  field[${i}] selector=${f.selector} text=${JSON.stringify(String(f.text||"").slice(0,40))}'));`
- `extension/background.js:15699` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `btnTxt: btn ? (btn.innerText || btn.value || '').trim().slice(0, 80) : null,`
- `extension/background.js:15968` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `const lbl = (el.innerText || el.placeholder || el.getAttribute('aria-label') || '').trim().slice(0, 60);`
- `extension/background.js:16307` **DEFECT:D1** — agent-facing or compared text cut by UTF-16 unit with no surrogate guard. Can emit an unpaired surrogate; Python then crashes the stdio server on it (D1). Neutralised wholesale by the D1 ingress scrub; the source fix is the existing surrogate-safe `markCut`.
  `: _ra.slice(0, 80) + '…(+' + (_ra.length - 80) + ')'));`
- `extension/listener_tag.js:380` **diag** — diagnostic / url text. JSON.stringify escapes a lone surrogate to the ASCII text \udXXX, so nothing invalid leaves the page; but the string still reaches Python as an unpaired surrogate if the server relays it (D1).
  `store.buf.push({ level, text, ts: Date.now(), url: String(location.href).slice(0, 300) });`

### exact-role-string (90)

- `extension/background.js:1650` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `try { out.role = n.getAttribute('role') || ''; } catch (e) {}`
- `extension/background.js:1664` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `try { out.role = el.getAttribute('role') || ''; } catch (e) {}`
- `extension/background.js:3125` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const role = el.getAttribute('role');`
- `extension/background.js:3138` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `is_combobox: role === 'combobox' || role === 'listbox' || role === 'menubutton' || popupTrigger,`
- `extension/background.js:3139` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `is_checkbox_button: role === 'checkbox' || role === 'switch' ||`
- `extension/background.js:3199` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `return (e2.tagName === 'INPUT' && (e2.type || '').toLowerCase() === 'radio') || e2.getAttribute('role') === 'radio';`
- `extension/background.js:3199` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `return (e2.tagName === 'INPUT' && (e2.type || '').toLowerCase() === 'radio') || e2.getAttribute('role') === 'radio';`
- `extension/background.js:3409` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _cr = c.getAttribute && c.getAttribute('role');`
- `extension/background.js:3411` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _tr = tg.getAttribute('role');`
- `extension/background.js:3470` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const r = (w.getAttribute && w.getAttribute('role')) || '';`
- `extension/background.js:3484` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const ro = o.getAttribute && o.getAttribute('role');`
- `extension/background.js:3514` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _tr = _tg.getAttribute('role');`
- `extension/background.js:3645` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (_tg3 && _tg3.getAttribute('role') === 'combobox'`
- `extension/background.js:3645` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (_tg3 && _tg3.getAttribute('role') === 'combobox'`
- `extension/background.js:3649` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const r4 = n.getAttribute && n.getAttribute('role');`
- `extension/background.js:3667` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (w.getAttribute && ['listbox','menu','dialog'].includes(w.getAttribute('role'))) {`
- `extension/background.js:3829` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `role: pick.getAttribute('role'),`
- `extension/background.js:3985` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const ro = o.getAttribute && o.getAttribute('role');`
- `extension/background.js:4162` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `(inp.getAttribute('role') || '').toLowerCase() === 'searchbox' ||`
- `extension/background.js:4745` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const ro = o.getAttribute && o.getAttribute('role');`
- `extension/background.js:4768` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const r = (w.getAttribute && w.getAttribute('role')) || '';`
- `extension/background.js:5122` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `e.role === 'button' || e.role === 'checkbox' || e.role === 'combobox') ? 0 : 1;`
- `extension/background.js:5917` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `role: (el.getAttribute && el.getAttribute('role')) || null,`
- `extension/background.js:6223` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _hr = (w.getAttribute('role') || '').toLowerCase();`
- `extension/background.js:6287` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const r = tableEl.getAttribute && tableEl.getAttribute('role');`
- `extension/background.js:6301` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const role = walker.getAttribute ? walker.getAttribute('role') : null;`
- `extension/background.js:6306` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (tag === 'dialog' || role === 'dialog' || role === 'alertdialog' ||`
- `extension/background.js:6344` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `} else if (tag === 'table' || role === 'table' || role === 'grid' || role === 'treegrid') {`
- `extension/background.js:6347` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (tag === 'dialog' || role === 'dialog' || role === 'alertdialog' ||`
- `extension/background.js:6351` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (tag === 'aside' || role === 'complementary') return 'sidebar';`
- `extension/background.js:6352` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (tag === 'nav'   || role === 'navigation')    return 'nav';`
- `extension/background.js:6368` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (role === 'banner')      return 'header';`
- `extension/background.js:6369` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (role === 'contentinfo') return 'footer';`
- `extension/background.js:6377` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (tag === 'main'  || role === 'main')          return 'main';`
- `extension/background.js:6378` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (role === 'tablist' || role === 'tabpanel')   return role;`
- `extension/background.js:6379` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (role === 'menu' || role === 'menubar' || role === 'listbox') return role;`
- `extension/background.js:6384` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (role === 'form' || tag === 'form') {`
- `extension/background.js:6424` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _ahRole = el.getAttribute('role');`
- `extension/background.js:6771` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const role = el.getAttribute('role');`
- `extension/background.js:6836` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const nr = n.getAttribute('role');`
- `extension/background.js:7356` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const rr = el.getAttribute('role');`
- `extension/background.js:7377` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `|| !!(el.getAttribute && el.getAttribute('role'));`
- `extension/background.js:7388` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _svgRole = el.getAttribute('role');`
- `extension/background.js:7432` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (!(el.getAttribute('aria-label') || el.getAttribute('role'))) {`
- `extension/background.js:7648` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _dr = el.getAttribute('role');`
- `extension/background.js:7689` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const ro = w.getAttribute ? w.getAttribute('role') : null;`
- `extension/background.js:7703` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _peRole = el.getAttribute('role');`
- `extension/background.js:7867` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `try { _lb = _host.getAttribute('role') || _lb; } catch (e2) {}`
- `extension/background.js:7950` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _szRole = el.getAttribute('role');`
- `extension/background.js:8390` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _bRole = el.getAttribute('role');`
- `extension/background.js:8505` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (tagL === 'input' && el.getAttribute('role') === 'combobox') {`
- `extension/background.js:8505` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (tagL === 'input' && el.getAttribute('role') === 'combobox') {`
- `extension/background.js:8631` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (el.getAttribute('role') === 'combobox') {`
- `extension/background.js:8631` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (el.getAttribute('role') === 'combobox') {`
- `extension/background.js:8671` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _elRole = el.getAttribute('role');`
- `extension/background.js:8773` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _sepRole = el.getAttribute('role') === 'separator';`
- `extension/background.js:8773` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _sepRole = el.getAttribute('role') === 'separator';`
- `extension/background.js:8782` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _sr = el.getAttribute('role');`
- `extension/background.js:8841` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _rCur = el.getAttribute('role');`
- `extension/background.js:8903` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `!el.getAttribute('role') && !el.hasAttribute('onclick') &&`
- `extension/background.js:8958` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const isCombo = el.getAttribute('role') === 'combobox'`
- `extension/background.js:8958` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const isCombo = el.getAttribute('role') === 'combobox'`
- `extension/background.js:9158` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (/^H[1-6]$/.test(sib.tagName) || sib.getAttribute('role') === 'heading') {`
- `extension/background.js:9158` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (/^H[1-6]$/.test(sib.tagName) || sib.getAttribute('role') === 'heading') {`
- `extension/background.js:9241` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _gRole = el.getAttribute('role');`
- `extension/background.js:9245` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const gr = ganc.getAttribute ? ganc.getAttribute('role') : null;`
- `extension/background.js:9284` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _cbRole = el.getAttribute('role');`
- `extension/background.js:9369` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `role: el.getAttribute('role') || ((ceRoot || codeEditor) ? 'textbox' : null),`
- `extension/background.js:9761` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `(c.role === 'combobox' || c.tag === 'button' || c.tag === 'a' || formyTags.has(c.tag)) &&`
- `extension/background.js:10310` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `virtualNote += '\n[VIRTUALIZED ${g.getAttribute('role') || 'grid'}${nm ? ' "${nm}"' : ''}: ' +`
- `extension/background.js:11020` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `return (m.role === 'gridcell' && m.near) ? '${m.near}=${base}' : base;`
- `extension/background.js:11199` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `try { rl = (n.getAttribute && n.getAttribute('role')) || ''; } catch (err) {}`
- `extension/background.js:11427` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `try { role = (n.getAttribute && n.getAttribute('role')) || ''; } catch (err) {}`
- `extension/background.js:11492` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `try { role = (el.getAttribute && el.getAttribute('role')) || ''; } catch (err) {}`
- `extension/background.js:11545` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const r = el.getAttribute && el.getAttribute('role');`
- `extension/background.js:11560` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const r = el.getAttribute && el.getAttribute('role');`
- `extension/background.js:11793` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `try { role = (el.getAttribute && el.getAttribute('role')) || ''; } catch (err) {}`
- `extension/background.js:11843` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `try { const r = el.getAttribute('role'); if (r) k += '[' + r + ']'; } catch (err) {}`
- `extension/background.js:12021` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `try { const r = c.getAttribute('role'); if (r) k += '[' + r + ']'; } catch (err) {}`
- `extension/background.js:12219` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const pop = (e.hasPopup && e.role !== 'combobox' && e.tag !== 'select') ? " (opens menu/popup)" : "";`
- `extension/background.js:12508` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `+ '${(_pop.getAttribute('role') || _pop.tagName.toLowerCase())} IS rendered on '`
- `extension/background.js:12857` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (has(e => e.role === 'combobox' || e.tag === 'select'))`
- `extension/background.js:13121` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const _r = (el.getAttribute && el.getAttribute('role')) || '';`
- `extension/background.js:14407` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `tag, role: el.getAttribute('role'),`
- `extension/background.js:14447` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `|| (walker.getAttribute && walker.getAttribute('role'))`
- `extension/background.js:15462` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const role = el.getAttribute('role');`
- `extension/background.js:15469` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (role === 'combobox' || role === 'listbox' || role === 'menubutton' || popupTrigger) return { kind: 'combobox' };`
- `extension/background.js:15470` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `if (role === 'checkbox' || role === 'switch' ||`
- `extension/background.js:15915` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const role = el.getAttribute('role');`
- `extension/background.js:15916` **DEFECT:D6** — role compared as one raw string. Chrome 153 (measured) honours a token list and trims whitespace (`role=" combobox"`, `role="combobox listbox"` -> combobox) and does NOT honour case (`role="Combobox"` -> text). Real-corpus instances: 0 of 6,632 (#71). `_roleHit` is the one tokenising site (and over-admits case variants Chrome ignores). One `_roleOf(el)` helper fixes all sites.
  `const isCombo = role === 'combobox' || tag === 'select';`

### data-attr (23)

- `extension/background.js:3367` **known** — `data-value` as an option-row marker in the fallback harvest, alongside cursor:pointer/handlers/aria-selected; #29 removed the document-wide widening, this is the scoped booster. LOW.
  `r.hasAttribute('data-value'))) continue;`
- `extension/background.js:3377` **DEFECT:D7** — library portal attributes in a candidate-container selector; only 1 of 5 copies is instrumented (D7).
  `const _named = Array.from(document.querySelectorAll(`
- `extension/background.js:3534` **known** — Radix `data-state` as a booster: exclude closed / prefer open popovers. Sits behind aria-hidden/inert/aria-expanded, which are checked first; a false exclusion needs a non-Radix ancestor with data-state=closed. Documented (fix #3). LOW.
  `if (w.getAttribute('data-state') === 'closed') return false;`
- `extension/background.js:3564` **DEFECT:D7** — library portal attributes in a candidate-container selector; only 1 of 5 copies is instrumented (D7).
  `const containers = (scopeRoot ? [scopeRoot] : Array.from(document.querySelectorAll(`
- `extension/background.js:3593` **known** — `data-value` as an option-row marker in the fallback harvest, alongside cursor:pointer/handlers/aria-selected; #29 removed the document-wide widening, this is the scoped booster. LOW.
  `|| r.hasAttribute('data-value') || r.hasAttribute('aria-selected');`
- `extension/background.js:3666` **known** — Radix `data-state` as a booster: exclude closed / prefer open popovers. Sits behind aria-hidden/inert/aria-expanded, which are checked first; a false exclusion needs a non-Radix ancestor with data-state=closed. Documented (fix #3). LOW.
  `if (w.getAttribute && w.getAttribute('data-state') === 'open') return true;`
- `extension/background.js:3825` **known** — Radix `data-state` as a booster: exclude closed / prefer open popovers. Sits behind aria-hidden/inert/aria-expanded, which are checked first; a false exclusion needs a non-Radix ancestor with data-state=closed. Documented (fix #3). LOW.
  `while (w && ds === null) { ds = w.getAttribute ? w.getAttribute('data-state') : null; w = w.parentElement; }`
- `extension/background.js:3953` **known** — Radix `data-state` as a booster: exclude closed / prefer open popovers. Sits behind aria-hidden/inert/aria-expanded, which are checked first; a false exclusion needs a non-Radix ancestor with data-state=closed. Documented (fix #3). LOW.
  `const ex = trig.getAttribute('aria-expanded'), ds = trig.getAttribute('data-state');`
- `extension/background.js:3994` **known** — Radix `data-state` as a booster: exclude closed / prefer open popovers. Sits behind aria-hidden/inert/aria-expanded, which are checked first; a false exclusion needs a non-Radix ancestor with data-state=closed. Documented (fix #3). LOW.
  `if (w.getAttribute('data-state') === 'closed') return false;`
- `extension/background.js:4009` **DEFECT:D7** — library portal attributes in a candidate-container selector; only 1 of 5 copies is instrumented (D7).
  `const containers = ((_scope && _scope.querySelector('div,li,span,button,a')) ? [_scope] : Array.from(document.querySelectorAll(`
- `extension/background.js:4032` **known** — `data-value` as an option-row marker in the fallback harvest, alongside cursor:pointer/handlers/aria-selected; #29 removed the document-wide widening, this is the scoped booster. LOW.
  `|| r.hasAttribute('data-value') || r.hasAttribute('aria-selected');`
- `extension/background.js:4076` **DEFECT:D7** — library portal attributes in a candidate-container selector; only 1 of 5 copies is instrumented (D7).
  `const containers = Array.from(document.querySelectorAll(`
- `extension/background.js:4501` **known** — Radix `data-state` as a booster: exclude closed / prefer open popovers. Sits behind aria-hidden/inert/aria-expanded, which are checked first; a false exclusion needs a non-Radix ancestor with data-state=closed. Documented (fix #3). LOW.
  `state: el.getAttribute('data-state'),`
- `extension/background.js:4707` **known** — Radix `data-state` as a booster: exclude closed / prefer open popovers. Sits behind aria-hidden/inert/aria-expanded, which are checked first; a false exclusion needs a non-Radix ancestor with data-state=closed. Documented (fix #3). LOW.
  `if (w.getAttribute('data-state') === 'closed') return false;`
- `extension/background.js:4778` **DEFECT:D7** — library portal attributes in a candidate-container selector; only 1 of 5 copies is instrumented (D7).
  `const containers = (scopeRoot ? [scopeRoot] : Array.from(document.querySelectorAll(`
- `extension/background.js:4798` **known** — `data-value` as an option-row marker in the fallback harvest, alongside cursor:pointer/handlers/aria-selected; #29 removed the document-wide widening, this is the scoped booster. LOW.
  `|| r.hasAttribute('data-value') || r.hasAttribute('aria-selected');`
- `extension/background.js:6418` **DEFECT:D4** — `data-state` (Radix/Headless convention) printed as a state token for ANY element. REPRODUCED: `<button data-state="on">Save</button>` -> `button "Save" (on)`. Only meaningful on a library that uses it; unconditional here.
  `const ds = el.getAttribute('data-state');`
- `extension/background.js:6486` **DEFECT:D4** — page-author `data-active`/`data-current` read as `(active)`/`(current)`. REPRODUCED: `<a data-current="true">` -> `a "Home" (current)`. Not a spec signal and not a library convention; a wrong (current) tells the agent not to click.
  `if (el.getAttribute('data-active') === 'true') return 'active';`
- `extension/background.js:6487` **DEFECT:D4** — page-author `data-active`/`data-current` read as `(active)`/`(current)`. REPRODUCED: `<a data-current="true">` -> `a "Home" (current)`. Not a spec signal and not a library convention; a wrong (current) tells the agent not to click.
  `if (el.getAttribute('data-current') === 'true') return 'current';`
- `extension/background.js:15839` **DEFECT:D8** — see D8: fill_form submit-error sweep selector list.
  `const candidates = scope.querySelectorAll(`
- `extension/background.js:15959` **known** — the `placeholder` convention token in a data-* attribute; #29's structural placeholder signal, language-neutral. benign-by-design.
  `try { ph = el.hasAttribute('data-placeholder') || !!el.querySelector('[data-placeholder]'); } catch (e) {}`
- `extension/background.js:15959` **known** — the `placeholder` convention token in a data-* attribute; #29's structural placeholder signal, language-neutral. benign-by-design.
  `try { ph = el.hasAttribute('data-placeholder') || !!el.querySelector('[data-placeholder]'); } catch (e) {}`
- `extension/panel.js:843` **benign** — the extension panel's OWN marker.
  `document.querySelectorAll("details[data-fold]").forEach((d) => {`

### framework-name (8)

- `extension/background.js:3670` **known** — Radix data-state booster (open/closed popover preference), behind aria-expanded/aria-hidden. LOW.
  `const ds = w.getAttribute('data-state');`
- `extension/background.js:5298` **known** — code-editor library class selectors. Gutter strip and editor-value reads. #9/#27 replaced the EXISTENCE gate with measured glyph width; these remain as boosters on the READ paths. Failure = an unnamed editor library is read as a div of gutter digits on those paths (the structural textarea branch beside 5298 covers most).
  `document.querySelectorAll('.CodeMirror, .cm-editor, .monaco-editor, .ace_editor')`
- `extension/background.js:7569` **known** — code-editor library class selectors. Gutter strip and editor-value reads. #9/#27 replaced the EXISTENCE gate with measured glyph width; these remain as boosters on the READ paths. Failure = an unnamed editor library is read as a div of gutter digits on those paths (the structural textarea branch beside 5298 covers most).
  `codeEditor = !!ceHost.querySelector('textarea, [contenteditable="true"], [contenteditable=""], .cm-content');`
- `extension/background.js:8598` **known** — code-editor library class selectors. Gutter strip and editor-value reads. #9/#27 replaced the EXISTENCE gate with measured glyph width; these remain as boosters on the READ paths. Failure = an unnamed editor library is read as a div of gutter digits on those paths (the structural textarea branch beside 5298 covers most).
  `src = el.querySelector('.cm-content, .CodeMirror-code, .view-lines, .ace_text-layer, [class*="mq-root-block"]') ||`
- `extension/background.js:13088` **known** — code-editor library class selectors. Gutter strip and editor-value reads. #9/#27 replaced the EXISTENCE gate with measured glyph width; these remain as boosters on the READ paths. Failure = an unnamed editor library is read as a div of gutter digits on those paths (the structural textarea branch beside 5298 covers most).
  `if (el.matches && el.matches('.CodeMirror, .monaco-editor, .ace_editor, .cm-editor, [class*="mq-editable-field"]')) {`
- `extension/background.js:13089` **known** — code-editor library class selectors. Gutter strip and editor-value reads. #9/#27 replaced the EXISTENCE gate with measured glyph width; these remain as boosters on the READ paths. Failure = an unnamed editor library is read as a div of gutter digits on those paths (the structural textarea branch beside 5298 covers most).
  `const inner = el.querySelector('.cm-content[contenteditable], textarea.inputarea, textarea');`
- `extension/background.js:15839` **known** — Radix data-state booster (open/closed popover preference), behind aria-expanded/aria-hidden. LOW.
  `const candidates = scope.querySelectorAll(`
- `extension/background.js:15839` **DEFECT:D8** — fill_form's submit-error sweep: a class-name list (Bootstrap, MUI, Ant, Angular Material, Vuetify, Tailwind red utilities) decides which on-page text is reported to the agent as a VALIDATION ERROR. Declarations exist and #37 already prints them per field (`aria-invalid`, `aria-errormessage`). Candidate for ablation.
  `const candidates = scope.querySelectorAll(`

### class-substring (11)

- `extension/background.js:4217` **known** — reads className to build a structural fold/signature key or to test the `placeholder` token; author-chosen text, language-neutral, no existence decision (#27 shape key). LOW.
  `const cn = typeof n.className === 'string' ? n.className : (n.className && n.className.baseVal) || '';`
- `extension/background.js:7260` **known** — reads className to build a structural fold/signature key or to test the `placeholder` token; author-chosen text, language-neutral, no existence decision (#27 shape key). LOW.
  `const cn = typeof n.className === 'string' ? n.className : (n.className && n.className.baseVal) || '';`
- `extension/background.js:8556` **DEFECT:D3** — `placeholder` convention token on class text. The collector copy (`_phMarked`) excludes CSS-property utilities (`text-placeholder`); the copies here do not — see D3.
  `try { if (w.querySelector('[class*="placeholder"]') || /placeholder/i.test(w.className || '')) return ''; } catch (e) {}`
- `extension/background.js:8623` **DEFECT:D3** — `placeholder` convention token on class text. The collector copy (`_phMarked`) excludes CSS-property utilities (`text-placeholder`); the copies here do not — see D3.
  `const ph = src.querySelector('.cm-placeholder, [class*="placeholder"]');`
- `extension/background.js:9045` **DEFECT:D3** — `placeholder` convention token on class text. The collector copy (`_phMarked`) excludes CSS-property utilities (`text-placeholder`); the copies here do not — see D3.
  `const ph = w.querySelector('[class*="placeholder"]');`
- `extension/background.js:9298` **known** — reads className to build a structural fold/signature key or to test the `placeholder` token; author-chosen text, language-neutral, no existence decision (#27 shape key). LOW.
  `const cls0 = (n) => (typeof n.className === 'string' ? n.className.trim().split(/\s+/)[0] : '');`
- `extension/background.js:13499` **known** — reads className to build a structural fold/signature key or to test the `placeholder` token; author-chosen text, language-neutral, no existence decision (#27 shape key). LOW.
  `const s = e.tagName + '.' + (typeof e.className === 'string'`
- `extension/background.js:13530` **known** — reads className to build a structural fold/signature key or to test the `placeholder` token; author-chosen text, language-neutral, no existence decision (#27 shape key). LOW.
  `return (typeof e.className === 'string'`
- `extension/background.js:15839` **DEFECT:D8** — see D8 (class-name sweep for validation errors).
  `const candidates = scope.querySelectorAll(`
- `extension/panel.js:323` **benign** — the extension's OWN panel DOM (class names we author).
  `document.querySelectorAll("#feed .when").forEach((el) => {`
- `extension/panel.js:329` **benign** — the extension's OWN panel DOM (class names we author).
  `document.querySelectorAll("#sites .site-when").forEach((el) => {`

### english-wordlist (25)

- `core/flows/descriptor.py:70` **benign** — tool-argument / own-schema vocabulary (the caller's `format`, `navigate` url keywords, flow descriptor keys).
  `("tag", "role", "type"),`
- `core/flows/descriptor.py:111` **benign** — tool-argument / own-schema vocabulary (the caller's `format`, `navigate` url keywords, flow descriptor keys).
  `ALT: tuple[str, ...] = ("tag", "role", "type", "href")`
- `extension/background.js:3182` **benign** — the CALLER's boolean/toggle vocabulary passed to form_input (`true|yes|on|checked`...). Reads the caller's argument, not page text (#66 dispositioned it).
  `const target = ['1', 'true', 'yes', 'on', 'checked', 'check'].includes(want) ? true`
- `extension/background.js:3183` **benign** — the CALLER's boolean/toggle vocabulary passed to form_input (`true|yes|on|checked`...). Reads the caller's argument, not page text (#66 dispositioned it).
  `: ['0', 'false', 'no', 'off', 'unchecked', 'uncheck'].includes(want) ? false`
- `extension/background.js:3183` **benign** — the CALLER's boolean/toggle vocabulary passed to form_input (`true|yes|on|checked`...). Reads the caller's argument, not page text (#66 dispositioned it).
  `: ['0', 'false', 'no', 'off', 'unchecked', 'uncheck'].includes(want) ? false`
- `extension/background.js:3184` **benign** — the CALLER's boolean/toggle vocabulary passed to form_input (`true|yes|on|checked`...). Reads the caller's argument, not page text (#66 dispositioned it).
  `: ['toggle', 'flip', 'switch'].includes(want) ? null   // explicit toggle`
- `extension/background.js:3184` **benign** — the CALLER's boolean/toggle vocabulary passed to form_input (`true|yes|on|checked`...). Reads the caller's argument, not page text (#66 dispositioned it).
  `: ['toggle', 'flip', 'switch'].includes(want) ? null   // explicit toggle`
- `extension/background.js:4209` **known** — attribute NAME convention (`placeholder` / `data-*`), not page text; #29's declared placeholder signal. Two copies, one without the Tailwind exclusion (D3).
  `if (a.name.indexOf('aria-') === 0) continue;`
- `extension/background.js:4210` **known** — attribute NAME convention (`placeholder` / `data-*`), not page text; #29's declared placeholder signal. Two copies, one without the Tailwind exclusion (D3).
  `if (a.name.indexOf('placeholder') !== -1) {`
- `extension/background.js:4215` **known** — attribute NAME convention (`placeholder` / `data-*`), not page text; #29's declared placeholder signal. Two copies, one without the Tailwind exclusion (D3).
  `if (a.name.indexOf('data-') === 0 && /(^|[\s,_-])placeholder([\s,_-]|$)/.test(a.value)) return true;`
- `extension/background.js:6717` **benign** — our own protocol vocabulary / sentinel (not page text).
  `let t = (typeof n.innerText === 'string') ? n.innerText : _deepText(n);`
- `extension/background.js:7248` **known** — attribute NAME convention (`placeholder` / `data-*`), not page text; #29's declared placeholder signal. Two copies, one without the Tailwind exclusion (D3).
  `if (a.name.indexOf('aria-') === 0) continue;`
- `extension/background.js:7249` **known** — attribute NAME convention (`placeholder` / `data-*`), not page text; #29's declared placeholder signal. Two copies, one without the Tailwind exclusion (D3).
  `if (a.name.indexOf('placeholder') !== -1) {`
- `extension/background.js:7258` **known** — attribute NAME convention (`placeholder` / `data-*`), not page text; #29's declared placeholder signal. Two copies, one without the Tailwind exclusion (D3).
  `if (a.name.indexOf('data-') === 0 && /(^|[\s,_-])placeholder([\s,_-]|$)/.test(a.value)) return true;`
- `extension/background.js:7267` **benign** — Tailwind colour-utility exclusion list (the FIX for D3's family, on one copy only).
  `if (/^(text|bg|border|fill|stroke|ring|shadow|from|via|to|decoration|outline|caret|accent)-placeholder$/.test(tok)) continue;`
- `extension/background.js:13116` **benign** — HTML element/input-type lists.
  `_writable = _NONTEXT.indexOf(String(el.type || 'text').toLowerCase()) < 0;`
- `extension/background.js:13256` **benign** — our own protocol vocabulary / sentinel (not page text).
  `try { if (el.value != null && typeof el.value === 'string') parts.push('v:' + el.value.length + ':' + el.value.slice(0, 24)); } catch (e) {}`
- `extension/background.js:14290` **benign** — our own protocol vocabulary / sentinel (not page text).
  `if (!m || typeof m.query !== 'function') {`
- `extension/background.js:14668` **benign** — our own protocol vocabulary / sentinel (not page text).
  `if (typeof text === 'string' && !text.startsWith('__SCOPE_MISS__')) {`
- `extension/background.js:16483` **benign** — our own protocol vocabulary / sentinel (not page text).
  `} else if (msg && msg.kind === "reconnect") {`
- `extension/background.js:16488` **benign** — our own protocol vocabulary / sentinel (not page text).
  `} else if (msg && msg.kind === "steer") {`
- `extension/panel.js:798` **benign** — our own protocol vocabulary / sentinel (not page text).
  `if (msg.kind === "status") { endPending(); paintStatus(msg.status); }`
- `extension/panel.js:799` **benign** — our own protocol vocabulary / sentinel (not page text).
  `if (msg.kind === "action") {`
- `mcp_server.py:1528` **benign** — own vocabulary.
  `format=("flat" if str(format).lower() == "flat" else "tree"))`
- `mcp_server.py:3942` **benign** — tool-argument / own-schema vocabulary (the caller's `format`, `navigate` url keywords, flow descriptor keys).
  `return str(inp.get("url") or "").strip().lower() in ("back", "forward")`

### latin-digit (18)

- `core/flows/model.py:85` **benign** — variable/secret NAME grammar (`{{name}}`, env-var names) — ASCII by POSIX/our own syntax; `slug()` falls back to position for non-Latin labels (model.py docstring).
  `out = re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", s or "")).strip("_")`
- `core/flows/model.py:375` **benign** — variable/secret NAME grammar (`{{name}}`, env-var names) — ASCII by POSIX/our own syntax; `slug()` falls back to position for non-Latin labels (model.py docstring).
  `VAR_RE = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")`
- `core/flows/recorder.py:622` **benign** — variable/secret NAME grammar (`{{name}}`, env-var names) — ASCII by POSIX/our own syntax; `slug()` falls back to position for non-Latin labels (model.py docstring).
  `used = sorted(set(re.findall(r"\{\{([A-Za-z0-9_]+)\}\}", after))`
- `core/flows/recorder.py:854` **benign** — variable/secret NAME grammar (`{{name}}`, env-var names) — ASCII by POSIX/our own syntax; `slug()` falls back to position for non-Latin labels (model.py docstring).
  `_vars_in = re.findall(r"\{\{([A-Za-z0-9_]+)\}\}", _pat)`
- `extension/background.js:335` **benign** — ASCII BY SPEC: CSS colour syntax, URL scheme grammar, our own `ref_N` format, DOM key names, icon-font class tokens, a close-code string we author.
  `return /^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(s) ? s : 'https://${s}';`
- `extension/background.js:1432` **benign** — ASCII BY SPEC: CSS colour syntax, URL scheme grammar, our own `ref_N` format, DOM key names, icon-font class tokens, a close-code string we author.
  `const code = /[a-z]/i.test(ch) ? 'Key${upper}' : (/[0-9]/.test(ch) ? 'Digit${ch}' : "");`
- `extension/background.js:5318` **known** — line-number gutter / bare-counter tests. Editor gutters use ASCII digits; the counter filter (`^\d{1,4}$`) would let an Eastern-Arabic counter through as an error string. LOW.
  `if (!t || !/^\d[\d\s]*$/.test(t)) continue;`
- `extension/background.js:6187` **benign** — ASCII BY SPEC: CSS colour syntax, URL scheme grammar, our own `ref_N` format, DOM key names, icon-font class tokens, a close-code string we author.
  `const _alpha0 = (c) => /^rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*0*(\.0+)?\s*\)$/.test(c || '');`
- `extension/background.js:6261` **known** — line-number gutter / bare-counter tests. Editor gutters use ASCII digits; the counter filter (`^\d{1,4}$`) would let an Eastern-Arabic counter through as an error string. LOW.
  `while (i < idx.length && /^\s*\d{1,6}\s*$/.test(lines[idx[i]])) i++;`
- `extension/background.js:6265` **known** — line-number gutter / bare-counter tests. Editor gutters use ASCII digits; the counter filter (`^\d{1,4}$`) would let an Eastern-Arabic counter through as an error string. LOW.
  `const m = idx.map(k => /^\s*(\d{1,6})(?=\D|$)/.exec(lines[k]));`
- `extension/background.js:6991` **benign** — ASCII BY SPEC: CSS colour syntax, URL scheme grammar, our own `ref_N` format, DOM key names, icon-font class tokens, a close-code string we author.
  `const ICON_RE = /(?:^|\s)(?:fa|far|fas|fab|fal|bi|icon|lucide|ph|ri|ti|mdi|bx|bxs|gg|la|las|octicon|tabler)-([a-z][a-z0-9-]{2,})/;`
- `extension/background.js:6992` **benign** — ASCII BY SPEC: CSS colour syntax, URL scheme grammar, our own `ref_N` format, DOM key names, icon-font class tokens, a close-code string we author.
  `const ICON_SKIP = /^(sm|lg|xs|xl|[0-9]x|fw|solid|regular|light|bold|thin|fill|duotone|brands|outline|filled|line|spin|pulse)$/;`
- `extension/background.js:8100` **benign** — ASCII BY SPEC: CSS colour syntax, URL scheme grammar, our own `ref_N` format, DOM key names, icon-font class tokens, a close-code string we author.
  `if (bg && bg !== 'transparent' && !/rgba\(\s*\d+,\s*\d+,\s*\d+,\s*0\s*\)/.test(bg)) return true;`
- `extension/background.js:8106` **benign** — ASCII BY SPEC: CSS colour syntax, URL scheme grammar, our own `ref_N` format, DOM key names, icon-font class tokens, a close-code string we author.
  `const colTransparent = c.color === 'transparent' || /rgba\(\s*\d+,\s*\d+,\s*\d+,\s*0\s*\)/.test(c.color || '');`
- `extension/background.js:11784` **benign** — ASCII BY SPEC: CSS colour syntax, URL scheme grammar, our own `ref_N` format, DOM key names, icon-font class tokens, a close-code string we author.
  `_row = _row.replace(/^ref_\d+(?::\d+)? \| /,`
- `extension/background.js:15858` **known** — line-number gutter / bare-counter tests. Editor gutters use ASCII digits; the counter filter (`^\d{1,4}$`) would let an Eastern-Arabic counter through as an error string. LOW.
  `if (/^\d{1,4}$/.test(t)) return;             // bare numbers (counters)`
- `extension/panel.js:90` **benign** — ASCII BY SPEC: CSS colour syntax, URL scheme grammar, our own `ref_N` format, DOM key names, icon-font class tokens, a close-code string we author.
  `const m = s.match(/closed \((\d+)/);`
- `extension/panel.js:96` **benign** — ASCII BY SPEC: CSS colour syntax, URL scheme grammar, our own `ref_N` format, DOM key names, icon-font class tokens, a close-code string we author.
  `const rawWhy = (s.match(/^closed \(\d+:\s*([\s\S]*)\)$/) || [])[1] || "";`

### ascii-on-text (4)

- `core/flows/recorder.py:178` **known** — find's role-word tables: `isascii()` decides 'spaced vs spaceless script' for the containment rule (#25). Proxy, not a gate on existence; mis-sorts spaceless scripts that are ASCII-free but not CJK (Thai/Khmer/Lao) — see D9.
  `_ATTR = re.compile(r'\s([A-Za-z_][\w:.@-]*)=(?=")')`
- `mcp_server.py:1105` **known** — find's role-word tables: `isascii()` decides 'spaced vs spaceless script' for the containment rule (#25). Proxy, not a gate on existence; mis-sorts spaceless scripts that are ASCII-free but not CJK (Thai/Khmer/Lao) — see D9.
  `_ROLE_WORDS_INTL = frozenset(_fold(h) for h, _k in _ROLE_HINTS if not h.isascii())`
- `mcp_server.py:1127` **known** — find's role-word tables: `isascii()` decides 'spaced vs spaceless script' for the containment rule (#25). Proxy, not a gate on existence; mis-sorts spaceless scripts that are ASCII-free but not CJK (Thai/Khmer/Lao) — see D9.
  `if tok.isascii():`
- `mcp_server.py:2846` **known** — find's role-word tables: `isascii()` decides 'spaced vs spaceless script' for the containment rule (#25). Proxy, not a gate on existence; mis-sorts spaceless scripts that are ASCII-free but not CJK (Thai/Khmer/Lao) — see D9.
  `if not _hinted and not hint.isascii():`

### fixed-threshold (78)

- `core/flows/descriptor.py:277` **benign** — count of OUR OWN collections (rows/frames/notes/steps), or a resource bound (GIF frames). No page judgement.
  `if len(order) >= 2:`
- `core/flows/descriptor.py:592` **benign** — count of OUR OWN collections (rows/frames/notes/steps), or a resource bound (GIF frames). No page judgement.
  `if len(hits) > 12:`
- `core/flows/recorder.py:568` **benign** — count of OUR OWN collections (rows/frames/notes/steps), or a resource bound (GIF frames). No page judgement.
  `unproven.append((_n, k[0], k[1] if len(k) > 1 else "", _n == 0))`
- `core/flows/recorder.py:728` **benign** — count of OUR OWN collections (rows/frames/notes/steps), or a resource bound (GIF frames). No page judgement.
  `_ident = [t for t in _ident if len(t) >= 2]`
- `core/flows/recorder.py:781` **benign** — count of OUR OWN collections (rows/frames/notes/steps), or a resource bound (GIF frames). No page judgement.
  `_names = {str(k[1]) if len(k) > 1 and k[1] is not None else str(k[0])`
- `core/flows/recorder.py:1067` **benign** — count of OUR OWN collections (rows/frames/notes/steps), or a resource bound (GIF frames). No page judgement.
  `exp["search"] = list(_s.values()) if len(_s) > 1 else next(iter(_s.values()))`
- `core/flows/recorder.py:1069` **benign** — count of OUR OWN collections (rows/frames/notes/steps), or a resource bound (GIF frames). No page judgement.
  `exp["query"] = list(_q.values()) if len(_q) > 1 else next(iter(_q.values()))`
- `core/flows/recorder.py:1160` **benign** — count of OUR OWN collections (rows/frames/notes/steps), or a resource bound (GIF frames). No page judgement.
  `exp[kind] = items if len(items) > 1 else items[0]`
- `core/flows/runner.py:375` **benign** — count of OUR OWN collections (rows/frames/notes/steps), or a resource bound (GIF frames). No page judgement.
  `if len(step.targets) > 1 and unresolved.path:`
- `core/flows/secrets.py:109` **benign** — count of OUR OWN collections (rows/frames/notes/steps), or a resource bound (GIF frames). No page judgement.
  `plural = "s" if len(uniq) > 1 else ""`
- `extension/background.js:217` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `text: t.length > 2000 ? t.slice(0, 2000) + "…(clipped)" : t,`
- `extension/background.js:470` **known** — presentation cap with `…(+N)`/marker or a diagnostic dump.
  `url: String(url || "").slice(0, 200),`
- `extension/background.js:3597` **DEFECT:D2** — option-row eligibility in the fallback picker harvest: a row whose text exceeds 80 UTF-16 units is never an option. REPRODUCED (see D2).
  `if (!t || t.length < 1 || t.length > 80) return false;`
- `extension/background.js:4036` **DEFECT:D2** — option-row eligibility in the fallback picker harvest: a row whose text exceeds 80 UTF-16 units is never an option. REPRODUCED (see D2).
  `if (!t || t.length > 80) return false;`
- `extension/background.js:4801` **DEFECT:D2** — option-row eligibility in the fallback picker harvest: a row whose text exceeds 80 UTF-16 units is never an option. REPRODUCED (see D2).
  `if (!t || t.length > 80) return false;`
- `extension/background.js:4812` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (best.length >= 2) els = best;`
- `extension/background.js:5320` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (nums.length < 2) continue;`
- `extension/background.js:5358` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (slim && (n.textContent || '').trim().length > 20) {`
- `extension/background.js:5508` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `grid.push({ head: (inHead || allTh) && cells.length >= 2, vals: row });`
- `extension/background.js:5510` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (grid.length < 2) continue;   // not a data grid worth re-rendering`
- `extension/background.js:5783` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (at && at.length <= 2 && t.trimEnd().endsWith(at)) {`
- `extension/background.js:5984` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (a.search.length <= 24) out += a.search;`
- `extension/background.js:5987` **known** — bounded-evidence tests: `near=`/selection-display/url-fragment shortening. A candidate longer than the bound is not used as a HINT (never identity, #37) or is shortened with a marker. LOW.
  `out += first && first.length <= 40 ? '?' + first + '&…' : '?…';`
- `extension/background.js:5990` **known** — bounded-evidence tests: `near=`/selection-display/url-fragment shortening. A candidate longer than the bound is not used as a HINT (never identity, #37) or is shortened with a marker. LOW.
  `if (a.hash && a.hash.length <= 16) out += a.hash;`
- `extension/background.js:6249` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (lines.length < 2) return raw;`
- `extension/background.js:6252` **known** — output budget / noise bound on text WE emit or a structural run-length test (gutter numbering). Presentation; marked cut with residual where it truncates.
  `return nums[0] === 1 || nums.length >= 4;`
- `extension/background.js:6259` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (idx.length < 2) return raw;`
- `extension/background.js:7057` **DEFECT:D5** — synthLabel ACCEPTS a name only if short; longer declared text falls through to (unlabeled). REPRODUCED for ::before (see D5).
  `if (t && t.length <= 80) return t;`
- `extension/background.js:7110` **DEFECT:D5** — synthLabel ACCEPTS a name only if short; longer declared text falls through to (unlabeled). REPRODUCED for ::before (see D5).
  `if (pt && pt.length <= 40) return pt;`
- `extension/background.js:7120` **DEFECT:D5** — synthLabel ACCEPTS a name only if short; longer declared text falls through to (unlabeled). REPRODUCED for ::before (see D5).
  `if (c && c.length <= 40 && /[\p{L}\p{N}]/u.test(c)) return c;   // any script, not just ASCII`
- `extension/background.js:7414` **known** — #28 DEMOTION signals (`was:` notes); these rules cannot delete since #28 and L10c is the tripwire.
  `else if ((el.innerText || '').trim().length > 40) canvasLike = false;`
- `extension/background.js:7431` **known** — #28 DEMOTION signals (`was:` notes); these rules cannot delete since #28 and L10c is the tripwire.
  `if (tagL !== 'canvas' && _cArea < 0.25 * vw * vh) _note(el, 'was:canvaslike-below-viewport-fraction');`
- `extension/background.js:8036` **benign** — 2px scroll-position tolerance (sub-pixel rounding), not a content judgement.
  `(ccy < ar.top    && anc.scrollTop > 2) ||`
- `extension/background.js:8038` **benign** — 2px scroll-position tolerance (sub-pixel rounding), not a content judgement.
  `(ccx < ar.left   && anc.scrollLeft > 2);`
- `extension/background.js:8345` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (_bare && _bare.length <= 2 && !/\p{L}/u.test(_bare)) {`
- `extension/background.js:8352` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (accessibleName.length > 0 && accessibleName.length <= 2 && !/\p{L}/u.test(accessibleName)) {`
- `extension/background.js:8355` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (!tAttr || tAttr.length <= 2) {`
- `extension/background.js:8359` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (tAttr.length > 2) {`
- `extension/background.js:8555` **known** — bounded-evidence tests: `near=`/selection-display/url-fragment shortening. A candidate longer than the bound is not used as a HINT (never identity, #37) or is shortened with a marker. LOW.
  `if (t && t.length <= 60) {`
- `extension/background.js:8758` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (!iconOnly && label && label.length <= 2 && !/\p{L}/u.test(label)) {`
- `extension/background.js:8979` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (!unselected && _o && el.selectedIndex === 0 && el.options.length > 2) {`
- `extension/background.js:9072` **known** — bounded-evidence tests: `near=`/selection-display/url-fragment shortening. A candidate longer than the bound is not used as a HINT (never identity, #37) or is shortened with a marker. LOW.
  `const short = (s) => { s = (s || '').replace(/\s+/g, ' ').replace(/\s*#\s*$/, '').trim(); return (s && s.length <= 60) ? s : ''; };`
- `extension/background.js:9195` **known** — bounded-evidence tests: `near=`/selection-display/url-fragment shortening. A candidate longer than the bound is not used as a HINT (never identity, #37) or is shortened with a marker. LOW.
  `if (t && t !== (accessibleName || buttonText) && t.length <= 60) nearLabel = t;`
- `extension/background.js:9852` **known** — fold/compaction group minimums. Presentation only (SERIALIZATION; every member keeps its ref); #19 measured fold-min-members as a gentle 4.3% slope.
  `if (members.length < 2) continue;`
- `extension/background.js:9961` **known** — bounded-evidence tests: `near=`/selection-display/url-fragment shortening. A candidate longer than the bound is not used as a HINT (never identity, #37) or is shortened with a marker. LOW.
  `if (at && at.length <= 50 && at !== l) t = at;`
- `extension/background.js:10037` **known** — #28 DEMOTION signals (`was:` notes); these rules cannot delete since #28 and L10c is the tripwire.
  `((e.text || e.label || '').length >= 20);`
- `extension/background.js:10075` **known** — #28 DEMOTION signals (`was:` notes); these rules cannot delete since #28 and L10c is the tripwire.
  `if (lab && lab.length > 2) residual = residual.split(lab).join('');`
- `extension/background.js:10079` **known** — #28 DEMOTION signals (`was:` notes); these rules cannot delete since #28 and L10c is the tripwire.
  `if (residual.replace(/[\s|·•,;:.\-—]/g, '').length < 12) drop.add(be.mmid);`
- `extension/background.js:10961` **benign** — presentation cap on OUR region hint, with an explicit .
  `return ' They are in — ${shown}${ks.length > 4 ? ', and ${ks.length - 4} more region(s)' : ''}' +`
- `extension/background.js:11014` **known** — fold/compaction group minimums. Presentation only (SERIALIZATION; every member keeps its ref); #19 measured fold-min-members as a gentle 4.3% slope.
  `if (members.length < 10) continue;`
- `extension/background.js:11022` **known** — grid/icon fold eligibility needs 'clean short labels'; presentation only (members stay individually listed otherwise).
  `if (labs.some(l => !l || l.length > 56)) continue;   // need clean, short labels`
- `extension/background.js:11083` **known** — grid/icon fold eligibility needs 'clean short labels'; presentation only (members stay individually listed otherwise).
  `if (!lab || lab.length > 40) continue;`
- `extension/background.js:11089` **known** — fold/compaction group minimums. Presentation only (SERIALIZATION; every member keeps its ref); #19 measured fold-min-members as a gentle 4.3% slope.
  `if (members.length < 8) continue;`
- `extension/background.js:11130` **known** — fold/compaction group minimums. Presentation only (SERIALIZATION; every member keeps its ref); #19 measured fold-min-members as a gentle 4.3% slope.
  `if (members.length < 8) continue;`
- `extension/background.js:11294` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (/\p{Nd}/u.test(v) && v.length <= 24 && /^[^.]*$/.test(v) && /\s/.test(v)) return 'timeish';`
- `extension/background.js:11344` **known** — fold/compaction group minimums. Presentation only (SERIALIZATION; every member keeps its ref); #19 measured fold-min-members as a gentle 4.3% slope.
  `if (members.length < 6 || window.__abNoFold) continue;`
- `extension/background.js:11995` **known** — fold/compaction group minimums. Presentation only (SERIALIZATION; every member keeps its ref); #19 measured fold-min-members as a gentle 4.3% slope.
  `if (members.length >= 6 && !ent.get(members[0]) && (kids.get(members[0]) || []).length) {`
- `extension/background.js:12060` **known** — fold/compaction group minimums. Presentation only (SERIALIZATION; every member keeps its ref); #19 measured fold-min-members as a gentle 4.3% slope.
  `if (members.length >= 6) {`
- `extension/background.js:12538` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (scopeMmid && out.length <= 2) {`
- `extension/background.js:12975` **known** — fold/compaction group minimums. Presentation only (SERIALIZATION; every member keeps its ref); #19 measured fold-min-members as a gentle 4.3% slope.
  `if (_dt.length < 6) _dt.push('ref_${mm} (${rs}x${cs})');`
- `extension/background.js:13559` **known** — #28 DEMOTION signals (`was:` notes); these rules cannot delete since #28 and L10c is the tripwire.
  `if (!p || p.children.length < 2) return false;`
- `extension/background.js:13934` **known** — fold/compaction group minimums. Presentation only (SERIALIZATION; every member keeps its ref); #19 measured fold-min-members as a gentle 4.3% slope.
  `if (idxs.length < 2) continue;`
- `extension/background.js:14433` **diag** — diagnostic op (filter verdict probe), not on a tool path.
  `if (labelMatches.length > 80) return;`
- `extension/background.js:14436` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (!txt || txt.length > 120) return;`
- `extension/background.js:15827` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (t && t.length <= 200 && !seen.has(t)) { seen.add(t); out.push(t); }`
- `extension/background.js:15853` **known** — small structural counts (>=2 siblings to be a list/group; <=2 glyph-only name test paired with \p{L}). Structural minimums, not text length judgements; the glyph test is script-aware via \p{L}.
  `if (!t || t.length > 200) return;`
- `extension/background.js:16306` **known** — output budget / noise bound on text WE emit or a structural run-length test (gutter numbering). Presentation; marked cut with residual where it truncates.
  `: (_ra == null ? null : (_ra.length <= 80 ? _ra`
- `mcp_server.py:506` **known** — find scorer tuning constants (inflection prefix, coverage gate), documented in-line (#25/#27); lexical ranking, not existence.
  `if len(toks) >= 3:`
- `mcp_server.py:648` **benign** — count of OUR OWN collections (rows/frames/notes/steps), or a resource bound (GIF frames). No page judgement.
  `if len(removed) > 25:`
- `mcp_server.py:741` **benign** — count of OUR OWN collections (rows/frames/notes/steps), or a resource bound (GIF frames). No page judgement.
  `if len(GIF["frames"]) < 300:`
- `mcp_server.py:1194` **benign** — count of OUR OWN collections (rows/frames/notes/steps), or a resource bound (GIF frames). No page judgement.
  `if (_ROW_LINE.match(_l) or "ref_".startswith(_l[:4]) and _l[:1] == "r")                     and len(out_lines) > 1:`
- `mcp_server.py:1522` **benign** — count of OUR OWN collections (rows/frames/notes/steps), or a resource bound (GIF frames). No page judgement.
  `if len(rows) > 60:`
- `mcp_server.py:2669` **DEFECT:D9** — see D9 (one-character tokens dropped from find).
  `if len(t) > 1 and t not in _STOP]`
- `mcp_server.py:2708` **known** — find scorer tuning constants (inflection prefix, coverage gate), documented in-line (#25/#27); lexical ranking, not existence.
  `if len(token) >= 5:`
- `mcp_server.py:2822` **DEFECT:D9** — see D9 (hard-coded CJK ranges).
  `if len(t) >= 2 and not re.search(r"[^一-鿿぀-ヿ가-힯]", t):`
- `mcp_server.py:2824` **known** — find scorer tuning constants (inflection prefix, coverage gate), documented in-line (#25/#27); lexical ranking, not existence.
  `if fld and len(fld) >= 2 and (t.startswith(fld) or fld.startswith(t)):`
- `mcp_server.py:3670` **benign** — count of OUR OWN collections (rows/frames/notes/steps), or a resource bound (GIF frames). No page judgement.
  `if len(frames) < 2:`
- `mcp_server.py:4569` **benign** — count of OUR OWN collections (rows/frames/notes/steps), or a resource bound (GIF frames). No page judgement.
  `if len(notes) > 1:`

