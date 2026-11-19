# Is the name we PRINT the RIGHT name? Our AccName against Chrome's own

> **CORRECTION 2026-11-19 (CLAUDE.md #108): `wc_webawesome`'s 28 rows are
> MIS-ATTRIBUTED here.** This paper names that site for the slot defect. A
> paired before/after across the slot fix shows it **byte-identical**, and a
> live probe shows its slots are `display: flex` and VISIBLE
> (`checkVisibility({visibilityProperty: true}) === true`), so `_namable`
> passes them and the slot fix was never involved. The real cause is
> `<wa-icon aria-label="Search">`: **AccName 2F concatenates each descendant's
> NAME, while `_contentName` concatenates descendant TEXT.** Chrome reports
> `ax_from: "contents"` for all 28. That is #34's documented mechanism in its
> degenerate case — the element has no other text, so it lands in `ours-empty`
> rather than `chrome-superset`. Not a new class; the attribution was wrong,
> and it explains why that site did not move.
>
> **Also corrected: the prediction that `leg_tcl`, `w2_berlin` and `gov_au`
> would get WORSE from the title fix.** All three IMPROVED (+0.200, +0.083,
> +0.235). No contradiction — "worse" here was a USEFULNESS judgement about
> particular rows, and this metric measures AGREEMENT WITH CHROME. Keep the two
> apart: a rising agreement rate is not the same as better output for an agent.


**Probe:** `tools/audit_name_correctness.py`
**Reuses:** `tools/audit_stage_generality.py` (#89 — the interaction driver, verbatim) and
`tools/audit_generality_live.py` (#85 — the collector, the sample, the out-of-sample guard)
**Collector under test:** `_collectInteractivePage`, extracted verbatim from
`extension/background.js` at repo `bab8dc4`
**Date:** 2026-11-18

> **Headline.** 251 live out-of-sample sites, **580 reads of which 329 are after an
> interaction**, 155,323 entries, **100,332 rows compared against Chrome's own
> `Accessibility.getFullAXTree`**. Where the collector CLAIMS an accessible name — the
> rows that print `name="…"` — we agree with Chrome **exactly on 0.9134** (18,410 /
> 20,156), **0.9492** once rows Chrome has no name for at all are set aside, and the
> per-site median is **0.9722**. Pooled over every row that prints an identity the figure
> is **0.7519**, and **three quarters of that gap is one population**: 18,486 of the
> 24,892 disagreements are rows where Chrome returns no name because the element's ROLE
> forbids one (`row`, `paragraph`, `generic`, `listitem` — Chrome names **0 of 2,103**
> `row`s and **224 of 4,035** `generic`s, measured) while our row prints the element's own
> TEXT — which is a different claim, and the one #74 proved we must keep making.
>
> **Two defects, both with a one-line diff and a measured A/B: a slotted label is
> invisible to our name derivation (301 rows, at 2.8× the rate after an interaction),
> and `title` is consulted before the host-language `alt` and before name-from-content
> (681 `disjoint` + 304 `ours-superset` + 107 `partial-overlap` rows, surfacing
> photographers' copyright strings and "opens in a new window" where the page declared a
> real label).** The second has an unambiguous half and a harder half; only the
> unambiguous half is proposed as a diff. Together, on the same page load against one
> oracle read: **80 rows improved, 0 rows where a correct name is broken**, +0.15% listing
> characters.
>
> **Is a control revealed BY an interaction named worse? Marginally, and the honest answer
> is smaller than the one I first computed.** 0.6628 against 0.7370 for the control arm on
> the full sample, with most of that residue explained by composition rather than by wrong
> names — and a smaller run with the corrected code built in puts `new` slightly *above*
> `carried`. What IS firmly post-interaction is the slot defect: `(unlabeled)` rows run at
> **0.154% of compared rows at first paint and 0.432% after an interaction, 2.8× higher**,
> because a design system renders its slotted controls when you open something.

---

## The question, and why nothing here could answer it

Every ruler in this project scores our collector against our own tools.

* #89 asks whether a control **survives**: `lost_identities` = 0 across 255 live sites,
  four compounding interactions deep.
* #92 asks whether it can be **reached** by the identity the listing printed: 13,682
  probes, 0 misses — and says in as many words that it scores `find` against the
  collector, *"so a wrong name that both agree on scores a hit"*.

Neither can see a name that is simply **wrong**. The only independent oracle in the
project is #33's `accessible_names`: Chrome implements AccName itself and hands over the
result over CDP. It had been run **once**, on **one page**, at first paint — 49 of 54
agreed — and the five differences were characterised from that single sample. There was
no post-interaction evidence at all, which is exactly the regime #89 and #92 showed
matters: a menu is open, a listbox is rendered in a portal, a design system's shadow DOM
is painting.

---

## Method

### Both halves are reused, not rewritten

The **driver** is `audit_stage_generality`'s, verbatim: `STAGE_PICK` / `_act` /
`STAGE_VERIFY`, the declaration-only tier list (menu-popup, dialog-trigger,
expandable-controls, combobox, details, tab, expandable, select, text-input), and the rule
that a stage counts **only when the page's own declared state flipped**. The **collector**
is `audit_generality_live.COLLECT`, extracted verbatim from `background.js`, so a
disagreement is a disagreement about the shipped code. The **sample** and the
out-of-sample guard are #85's. Forking any of them would let two definitions drift, which
PRINCIPLES 17 forbids and #36 recorded happening.

### The oracle side is #33's `axNamesFor`, over a Playwright CDP session

1. the collector runs **first**, because it is what stamps the `mmid` attributes;
2. `DOM.enable` **and** `Accessibility.enable` — #34 records that `getFullAXTree` returns
   an **empty node list, not an error**, without them, and that this looked exactly like
   "this page has no accessible names";
3. one `DOM.getDocument{depth:-1, pierce:true}` builds `backendNodeId → mmid` (a
   `DOM.resolveNode` per node is a round trip each and unusable at a few hundred);
4. `Accessibility.getFullAXTree`, joined on `backendDOMNodeId`.

### What "our name" is, and the self-check that keeps it honest

The row's **identity** as `_fmtLine` builds it: `name=` when the collector resolved an
accessible name, else the element's own text (or the label when the label strictly
contains the text and is longer — the icon+badge rule). `_fmtLine` is nested inside the
serializer and cannot be extracted, so `ours_identity` restates its 12-line precedence —
and **every single row's answer is checked against the `e.line` the collector really
built**, with `fmt_drift` reported. A non-zero `fmt_drift` voids the numbers rather than
being a footnote.

Three row kinds pose **no** question and are counted in their own buckets, never in the
agreement denominator:

| bucket | n | why |
|---|---|---|
| `not-in-ax-tree` | 11,578 | the element carries an mmid and Chrome's tree has no node for it |
| `chrome-ignored` | 20,676 | Chrome marks the node ignored — a presence disagreement, not a name one |
| `blanked-row` | 9,566 | `subtreeName && !subtreeNameSole`: the listing **removes** the identity on purpose (#74's rule), so there is nothing to be right or wrong about. 3,363 of them have a Chrome name |
| `contents-only-row` | 159 | the row leads with `value=`/`placeholder=` and prints no name field |
| `both-empty` | 13,012 | neither side has a name |
| **compared** | **100,332** | |
| | **155,323** | = every entry collected, exactly |

### The split that decides how to read everything below

`src=name` is the collector saying *"this is the element's ACCESSIBLE NAME"*. `src=text`
is the row printing the element's own text as a bare quoted string, which the legend
spells out as a different thing. **Chrome has no name at all for a role whose naming is
prohibited (`generic`) or author-only (`listitem`)**, so pooling the two makes a
spec-correct silence look like a disagreement. Both are reported.

### Proving the comparator can FIRE

A high agreement rate from a comparison nobody has seen disagree is worth nothing
(PRINCIPLES 11, 15). Three arms, all of which must hold:

* **a genuine spec disagreement** — `<div role=button><span>4</span><span>9秒39</span></div>`
  must be reported, because Chrome concatenates inline element children without a
  separator and we insert one (#28's shape). It is.
* **five CONTROLS must AGREE** — a plain button, a link, an `aria-label`led input, a
  `<label for>`ed password field, an icon button. Without this, a probe that reported
  *everything* as a disagreement would pass the first arm and the agreement rate would
  mean nothing.
* **a PLANTED arm** — after the collector has run, move an element's `aria-label`. Chrome
  reads the DOM as it is now, we read it as it was, so the comparator **must** report
  those. This proves the join and the comparator end to end, independently of whether the
  two derivations happen to differ anywhere on the page. A planted name only counts where
  it reached the **compared** population, which the per-mmid disposition states; the first
  version planted on `[mmid]` in document order and put 22 of 24 sentinels on elements
  that are not entries at all.

**Live:** `--fire` repeats the plant on real sites at the deepest stage reached.
**7 sites, 8 planted each, 56 / 56 reported, 0 missed** (`gov_au`, `leg_perldoc`,
`th_sanook`, `el_in`, `ko_daum`, `wc_webawesome`, `w2_unicode`; an eighth name was asked
for and is not in the `usable85` pool, so `--only` dropped it — worth knowing, because
`--only` intersects with the pool rather than overriding it).

**Out-of-sample guard, shown firing:** `--plant-in-corpus` adds a frozen-corpus host and
the run refuses to start —
`SAMPLE CONTAINS EXCLUDED HOSTS … [('PLANTED_IN_CORPUS', 'news.ycombinator.com')]` —
against 160 excluded hosts (`capture_listings.py` `SITES`, `tools/bench_turns/`,
`tools/bench_flows/`).

---

## Results

### Headline

| | |
|---|---|
| candidates / usable | 265 / **251** |
| reads / **post-interaction** reads | **580** / **329** |
| entries examined | 155,323 |
| **rows compared against Chrome** | **100,332** |
| exact agreement, pooled | **0.7519** |
| …excluding rows Chrome has no name for at all | **0.9217** |
| **`src=name` — where we CLAIM an accessible name** | **0.9134** (18,410 / 20,156) |
| …`src=name`, excluding its 760 `chrome-empty` | **0.9492** |
| **per-site median, `src=name`** | **0.9722** (169 sites with n ≥ 20) |
| `fmt_drift` | see "Mistakes" §1 — the checker's, not the collector's |

### Where our identity came from

| src | compared | exact | agree | dominant disagreement |
|---|---|---|---|---|
| `name` (prints `name="…"`) | 20,156 | 18,410 | **0.9134** | `chrome-empty` 760, `disjoint` 482, `ours-superset` 244 |
| `label` | 3,135 | 2,759 | 0.8801 | `chrome-empty` 261 |
| `text` (bare quoted string) | 76,708 | 54,263 | 0.7074 | **`chrome-empty` 17,465** |
| `unlabeled` / `none` | 309 | 8 | 0.026 | **`ours-empty` 301** |
| `label-contains-text` | 24 | 0 | — | `ours-superset` 24 — the icon+badge rule, by design |

### By stage

| stage | compared | exact | agree |
|---|---|---|---|
| s0 first paint | 47,499 | 36,923 | 0.7773 |
| s1 | 24,014 | 17,626 | 0.7340 |
| s2 | 13,758 | 9,505 | 0.6909 |
| s3 | 8,395 | 6,318 | 0.7526 |
| s4 | 6,666 | 5,068 | 0.7603 |

Depth: **97 of 251** usable sites offered nothing the picker could act on declaratively, 72 reached
one interaction, 29 a second, 13 a third, **40 the fourth** (the cap).

### The sharp question: is a control revealed BY an interaction named worse?

**Slightly, on the full sample — and the one real post-interaction effect is a DEFECT, not
a weakness in the naming. The headline number I first computed here was wrong and is in
"Mistakes" §2.**

| population | compared | exact | agree |
|---|---|---|---|
| `s0` first paint | 47,499 | 36,923 | 0.7773 |
| `post` (all post-interaction rows) | 52,833 | 38,517 | 0.7290 |
| **`new`** — identity never seen at an earlier stage | **3,434** | **2,276** | **0.6628** |
| `carried` — the control arm, always there | 49,171 | 36,241 | **0.7370** |
| `unnamed` — rows with no identity at all, unassignable | 228 | 0 | — |

`new` is keyed on the identity **string**, not the mmid, because mmids are additive and
one re-render mints hundreds of fresh ones (#9) — #89 and #92 use the same definition.
**That keying cannot assign a row whose identity is `""`**, and the first version put all
of them in `new`, which is the bug recorded in "Mistakes" §2. The `new` figure above is
corrected, and the correction is **exact rather than an estimate**: an empty-identity row
is never `exact`, so removing the 228 of them from `new_compared` reproduces precisely
what the fixed code computes.

**The direction is NOT firmly established, and the contrary evidence is reported rather
than buried.** A third run with the corrected code built in — 34 sites, every 7th of the
pool — gives **`new` 0.8150 (282 / 346) against `carried` 0.8001 (6,983 / 8,728)**, i.e.
the opposite sign at a tenth of the sample size and with overlapping Wilson intervals
(0.771–0.852 against 0.792–0.808). The 251-site figure is the one to quote because its
`new` population is 10× larger; the subset is a reminder that a 7pp gap on n=346 is not a
result.

**The composition is what explains it, and most of the gap is NOT a name we got wrong.**
Among the disagreement rows at post-interaction stages, `chrome-empty` is **79.7% of
`new`** against **66.1% of `carried`** — revealed content sits disproportionately inside
generic containers Chrome never names (`generic` 198 / `paragraph` 113 for `new`, against
`generic` 2,046 / `link` 1,553 for `carried`), where our row correctly prints the
element's text. That is a composition effect.
**Those two percentages come from the SAVED example rows, which are capped at 30 per read
in document order** — a head slice of each page, not the population. The class totals in
the tables are exact; this ratio is a sample and is quoted as one.

**What IS a real post-interaction effect is the slot defect, and it is measured
independently of the population code**: `ours-empty` runs at **73 / 47,499 = 0.154%** of
compared rows at first paint and **228 / 52,833 = 0.432%** after an interaction — **2.8×
higher** — because a design system renders its slotted buttons and links when you open
something.

### By script family (`compared`, `agree`)

latin-english 52,219 **0.8038** · latin-other 13,676 0.6355 · kana+han 6,053 0.7864 ·
han-trad 4,001 0.7196 · hebrew (RTL) 3,655 0.5715 · thai 3,662 **0.8127** · hangul 3,135
0.5825 · greek 2,775 0.7049 · vietnamese 2,672 **0.8376** · han-simp 2,548 0.7037 ·
cyrillic 1,921 0.7418 · devanagari 1,776 0.7770 · arabic (RTL) 1,124 **0.8425** ·
bengali 1,115 0.4520.

The spread is **not** a script effect: every low row is dominated by `chrome-empty`
(hebrew 1,364 of 1,566 disagreements; hangul 1,176 of 1,309) or, for bengali, by 270
`punctuation-only` on one site. There is no class in which a non-Latin script loses a
name a Latin one keeps.

---

## The disagreement classes, with a verdict for each

Classes are assigned **mechanically** from the two strings — no narration. The verdict
cites AccName 1.2 §4.3.2 (fetched and quoted, not recalled) or HTML-AAM, and
**"undecidable" is an allowed answer: Chrome is not automatically right** — #37 found
`title` and the HTML `name` attribute mis-ordered by reading the spec, and #28 attributed
its separator change to a spec rule that, read back here, says the opposite.

| class | n | share of compared | who is right |
|---|---|---|---|
| `chrome-empty` | 18,486 | 18.4% | **both** — different questions |
| `punctuation-only` | 2,081 | 2.1% | **Chrome by the spec, us for the reader** |
| `chrome-superset` | 1,742 | 1.7% | **Chrome by the spec, us by the screen** |
| `case-only` | 1,107 | 1.1% | **undecidable**, costs nothing |
| `disjoint` | 681 | 0.7% | **Chrome — OUR DEFECT** |
| `ours-superset` | 304 | 0.3% | **Chrome — same defect** |
| `ours-empty` | 301 | 0.3% | **Chrome — OUR DEFECT** |
| `partial-overlap` | 107 | 0.1% | **Chrome — same defect** |
| `whitespace-only` | 83 | 0.08% | **Chrome — by the spec AND by the screen, 28 of 29** |

### `chrome-empty` — 18,486 — BOTH ARE RIGHT, ABOUT DIFFERENT QUESTIONS

```
gov_tw_moi  a[generic]     ours="訊息快遞"      chrome=""
gov_tw_moi  li[listitem]   ours="115-11-18"    chrome=""
gov_tw_moi  div[generic]   ours="投票日倒數10天 …"  chrome=""
```

ARIA 1.2 gives `generic` **Name From: prohibited** and `listitem` **Name From: author**,
so Chrome returning `""` is the spec working. An `<a>` with no `href` maps to `generic`,
which is most of these. Our row prints the element's own **text** as a bare quoted string,
not as `name=`.

**That is the behaviour #74 exists to protect.** 118 ptable.com element tiles — `<li>`
elements, exactly this shape — were present in every presence metric this project has and
unreachable by their own verbatim printed label until the blanking rule was narrowed. If
we printed nothing where Chrome prints nothing, we would re-create that defect across
17,465 rows.

**Verdict: no action.** This class is why the pooled 0.7519 must never be quoted as "we
get a quarter of names wrong".

### `ours-empty` — 301 — **OUR DEFECT №1: A SLOTTED LABEL IS INVISIBLE TO OUR NAME PATH**

```
gov_au         button  ours=""  chrome="Sign in"
wc_lit         a       ours=""  chrome="Learn more"
wc_webawesome  button  ours=""  chrome="Search" / "Color Scheme" / "Theme" / "Icon Style"
```

The row prints `(unlabeled)` for a control the page has named. **This is the worst
direction a name can fail in**: the listing says the control has no identity when it has
one, and `find` then cannot reach it by that identity.

**The cause, measured rather than reasoned about.** `<my-btn>Sign in</my-btn>` renders
`<button><slot></slot></button>` inside a shadow root; the text arrives through the slot.
`_contentName` walks `node.childNodes`, finds the `<slot>`, and calls `_namable(slot)` —
which asks `checkVisibility({visibilityProperty:true})`. **A `<slot>` is
`display: contents`, which generates no box, so `checkVisibility()` returns `false`:**

```
slot_display            "contents"
slot_checkVisibility    false
slot_assignedNodes      ["Sign in"]
```

So the slot is skipped with `continue`, and **`_deepText`'s `<slot>` branch — which exists
precisely to resolve `assignedNodes({flatten:true})` — is never reached from
`_contentName`.** The correct handling is already in the file and is unreachable.

It is **not only slots**: `<button><span style="display:contents">Label</span></button>`
loses its name the same way, and `display:contents` is ordinary modern CSS.

**THIS IS NOT AN IDENTITY LOSS IN #89'S SENSE, AND THAT IS THE WHOLE REASON BOTH NUMBERS
ARE TRUE AT ONCE.** #89 measures `lost_identities` — a visible control whose name appears
**nowhere** in the listing — and reports 0 across 255 sites. These 301 rows do not
contradict it: the control still owns a row, so the STRICT arm is satisfied, and the words
usually survive somewhere in the listing, so the LENIENT arm is too. What is lost is that
they stop being **this element's NAME**, which is the field `find` scores against and the
one the legend calls identity.

Verified on the fixture rather than asserted, pre-fix rows verbatim:

```
ref_6 | button (unlabeled)                       ← the slotted button itself: no words at all
ref_8 | button (unlabeled) near="Sign in"        ← its NEIGHBOUR picked up ref_6's words
```

So the surviving text can be on a **different row**, attributed to a different control.
A lenient listing-wide substring test cannot tell that from the words being in the right
place. **A presence ruler and a correctness ruler can both be right and still disagree
about whether a page is fine**, which is the argument for this probe existing.

**Verdict: Chrome is right, and this is ours.** AccName computes the name from the
**flattened** tree; `_deepText` already agrees.

#### The diff

```js
// extension/background.js — _namable
   if (_NAME_SKIP[String(n.tagName || '').toUpperCase()]) return false;
-  if (n.checkVisibility && !n.checkVisibility({ visibilityProperty: true })) return false;
+  // `display: contents` generates NO BOX, so checkVisibility() is false for it while its
+  // CHILDREN render normally -- and a <slot> is display:contents by default, so this
+  // rejected every slot before _deepText's slot branch (which exists exactly to resolve
+  // assignedNodes) could ever be reached. Asking the BOX question of a boxless element
+  // answers the wrong question. `visibility` is still asked, because visibility IS
+  // inherited and does hide the children.
+  let _disp = ''; try { _disp = getComputedStyle(n).display; } catch (e) {}
+  if (_disp === 'contents') {
+    try { return getComputedStyle(n).visibility !== 'hidden'; } catch (e) { return true; }
+  }
+  if (n.checkVisibility && !n.checkVisibility({ visibilityProperty: true })) return false;
```

### `disjoint` 681 + `ours-superset` 304 + `partial-overlap` 107 — **OUR DEFECT №2: `title` IS CONSULTED TOO EARLY**

```
w2_oebb     img   ours="© ÖBB / Harald Eisenberger"  chrome="Skiers at Salzburg train station"
                  decl={"title": "© ÖBB / Harald Eisenberger", "alt": "Skiers at Salzburg train station"}
w2_seoul    a     ours="새 창 열림"  chrome="2027학년도 대학수학능력시험 관련 공공와이파이 …"
                  ("새 창 열림" = "opens in a new window")
gov_tw_moi  a     ours="[另開新視窗]內政部臉書"  chrome="內政部臉書"
                  ("[另開新視窗]" = "[opens in a new window]")
leg_tcl     img   ours="Tcl Developer Xchange"  chrome="Tcl Home"   title+alt both declared
gov_au      img   ours="Living arrangements category"  chrome="Person contemplating thoughts …"
```

`accessibleName` resolves `(!hasText ? (title || alt) : '')`. AccName 1.2 §4.3.2 orders
the steps **2E host-language label (for `<img>`, `alt`) → 2F name from content → 2I
tooltip**, and the spec's own note on 2I is explicit:

> *"Tooltip attributes are used only if nothing else, including subtree content, has
> provided results."*

So `title` outranking `alt` is a straight inversion of 2E before 2I, and `title`
outranking a descendant image's alt inverts 2F before 2I.

**The family splits in two, and only one half has an unambiguous fix.** Among the 549
saved `src=name` rows of this family, **106 declare both `title` and `alt` on the SAME
element** — step 2E against step 2I, where the spec is flat — and **283 have a `title`
where Chrome named from CONTENT** (step 2F against 2I), which is the harder half. On
`w2_seoul` the second half puts **"opens in a new window"** in the identity slot for 32
links, and on `gov_tw_moi` **"[opens in a new window]"** for 121; those are **not** fixed
by the diff below.

**The first half, in both directions, because even there it is a trade.** On `w2_oebb` the
current behaviour puts a **photographer's copyright credit** in the identity slot for 21
images; on `w2_hana` it puts a certifying body's name where the alt names the mark. Those
the diff fixes. Against that, `gov_au`'s `title="Living arrangements category"` is
genuinely more useful to an agent than `alt="Person contemplating thoughts looking out a
window"`, `leg_tcl`'s `"Tcl Developer Xchange"` beats `"Tcl Home"`, and `w2_berlin`'s
`"Link zu: Startseite Berlin.de"` is more informative than `"Berlin.de"` — **and the diff
makes all three worse.** The spec and the majority of live instances point one way; the
minority cost is real and is not hidden here.

#### The diff — the half where the spec is unambiguous

```js
// extension/background.js — accessibleName fallback
-  const _titleAlt = ((!hasText ? (el.getAttribute('title') || el.getAttribute('alt')) : '') || '').trim();
+  // HTML-AAM maps `alt` to AccName 1.2's step 2E (host-language label) and `title` to
+  // step 2I (tooltip), whose own note says a tooltip is used "only if nothing else,
+  // including subtree content, has provided results". Reading them the other way round
+  // named 21 oebb images after the photographer's copyright credit rather than after the
+  // alt text describing the photo. It does NOT touch the harder half -- a title beating
+  // name-from-content -- which is measured and deliberately left alone.
+  const _titleAlt = ((!hasText ? (el.getAttribute('alt') || el.getAttribute('title')) : '') || '').trim();
```

**NOT proposed: reordering `title` behind name-from-content.** That is the larger half
(283 of 549 rows) and it is where Chrome's spec-correct answer is often *less* useful than
ours (`影片縮圖` = "video thumbnail" instead of the video's title). It needs its own
measurement of both halves (#41/#44's rule) and a decision about what the `name=` slot is
FOR, which is not a defect to be fixed quietly.

**Deliberately out of scope:** `alt=""` is HTML's declaration that an image is decorative,
and the current code treats it as falsy so it falls through to `title`. The spec says an
empty `alt` ends the computation. Changing that would hide images that currently get a
title-derived name, and needs its own measurement.

### `chrome-superset` — 1,742 — Chrome by the spec, us by the screen; no action

```
gov_au    a  ours="Living arrangements Information to help with housing…"
             chrome="Person contemplating thoughts looking out a window Living arrangements …"
leg_perldoc a  ours="Perldoc Browser"  chrome="Perl Camel Logo Perldoc Browser"
w2_unibo  checkbox  ours="Facebook"  chrome="Facebook OFF"
```

AccName 2F accumulates **every** child's contribution, and HTML-AAM gives a descendant
`<img>` its `alt` as a text alternative. We drop it when the element has text of its own.
**Checked on a fixture, and it is not an identity loss:** a link whose *only* content is
an image does get the alt (`<a><img alt="Download the annual report"></a>` → `a "Download
the annual report"`), and at `detail="full"` the image has its own row.
What is lost is the alt text of a decorative image inside a text-bearing link at compact
detail, which is a cleaner label rather than a wrong one. **No action.**

### `punctuation-only` — 2,081 — Chrome is spec-correct; ours is better for the reader

```
gov_tw_moi  a  ours="歡慶地政節72週年 內政部致敬全國地政夥伴"
               chrome="歡慶地政節72週年 內政部致敬全國地政夥伴 ​"        ← trailing U+200B
w2_unicode  a  ours="Code Charts"   chrome=" Code Charts↗"              ← CSS ::after glyph
w2_unicode  a  ours="About Unicode" chrome="About Unicode ↗"
```

Two sub-causes. **Invisible and exotic characters**: a zero-width space (U+200B), an
ideographic space (U+3000) that our `\s+ → ' '` collapse normalises. **CSS generated
content**: AccName 2F.2.2/2F.2.3 say a user agent **MUST** prepend `::before` and append
`::after` textual content, so Chrome including an icon font's `↗` is mandated. Ours omits
it.

**Verdict: Chrome is spec-correct and we are right for this consumer.** A U+200B in a name
is unqueryable, and an icon glyph identifies nothing. **No action.**

### `case-only` — 1,107 — undecidable, and it costs nothing

```
gov_vn  a  ours="Phạm Gia Túc"  chrome="PHẠM GIA TÚC"   (CSS text-transform: uppercase)
```

Chrome's name carries the **rendered** casing; ours carries the author's. AccName does not
require applying `text-transform`. `find` folds case (#71's `i18n:norm`), so this costs
nothing either way. **No action.**

### `whitespace-only` — 83 — Chrome, and **#28's premise does not survive the spec text**

```
vi_vnexpress  a  ours="HÀ NỘI Bị xét xử vì…"   chrome="HÀ NỘIBị xét xử vì…"
ar_aljazeera  a  ours="الشرق الأوسط 2027 .. حروب"  chrome="الشرق الأوسط 2027.. حروب"
```

CLAUDE.md #28 added an unconditional space between element children, on the stated
grounds that *"Per the spec each child contribution is space-delimited"*. **AccName 1.2
step 2F.4 is "Append the result to the accumulated text"** — no space; the space-appending
steps are 2B.2.3 (labelledby) and 2J (between the top-level steps). The `::before` /
`::after` rules say "without a space" for the same reason: the name is meant to track what
is **rendered**.

Measured on a fixture driven through both derivations, with the element's own `innerText`
as a third oracle:

| markup | screen (`innerText`) | ours | Chrome |
|---|---|---|---|
| `<span>4</span><span>9</span>` inline, adjacent | `49` | **`4 9`** | `49` |
| …with `margin-right` on the first | `49` | **`4 9`** | `49` |
| `display:block` children | `Alpha Beta` | `Alpha Beta` | `Alpha Beta` |
| flex with `gap` | `12 reviews` | `12 reviews` | `12 reviews` |
| whitespace already in the source | `4 9` | `4 9` | `4 9` |

**Chrome matches the screen in 5 of 5; ours in 3 of 5, and the two it misses are exactly
the digit-adjacency case #28 was written for** — our space manufactures `4 9`, a value
that is on no screen and in no DOM. Chrome is display-aware: block and flex children get a
separator because the rendered text has one.

Against that, the live examples above *look* like the opposite case — `<span>HÀ NỘI</span>`
is a styled location badge and a reader does separate it from the sentence. **The screen
oracle on the live corpus says otherwise: of the 29 `whitespace-only` rows with rendered
text, Chrome matches `innerText` on 28 and we match on 1** — our space is inserted where
the page paints none, including inside that badge case.

**That 28/29 is weaker than it looks and the fixture table above is the stronger
evidence.** `innerText` is computed by the same engine as the AX name, so "Chrome's name
matches Chrome's `innerText`" is strong evidence that Chrome's name tracks its own
rendering and only weak evidence about what a human sees. The five-case fixture is where
the two can be told apart, because each case's rendering is known by construction.

**Verdict: Chrome, by the spec and by the screen — but NOT a diff here.** The structurally right answer is to follow
**display** rather than a constant, which is what Chrome does and what `innerText` already
provides. That is a larger change than it looks: it would fail #28's own N5/N5b fixtures,
which assert the unconditional space, so those would have to be rewritten to their
invariant first (#30's TR8d case). 83 rows in 100,332 is not the number that forces it.
Recorded so the next reader does not re-derive #28's spec claim from the entry alone.

---

## Characterisation pass, drift floor, and oracle stability

A second, instrumented pass over every 4th site of the pool, run **twice back to back with
the code held constant**: it carries the exact uncapped per-class × Chrome-role histogram,
the empirical "does Chrome ever name this role" census, the rendered-text oracle, and an
**oracle re-read** that bounds the one confound the design has — the page re-rendering
between the collector run and the CDP read.

67 sites (every 4th of the pool), 63 usable in pass 0 and 59 in pass 1, 29,157 rows
compared. It corroborates the headline on an independent subset: **`src=name` agrees on
0.9238** (4,062 / 4,397) against the main run's 0.9134.

### The self-check passes cleanly: `fmt_drift = 0` in both passes

`ours_identity`'s restatement of `_fmtLine`'s precedence agrees with the row the collector
really built on **every one of 29,157 + 25,076 rows**. The main run's `fmt_drift = 881` is
the checker's escaping assumption and nothing else — see "Mistakes" §1.

### Drift floor

| | |
|---|---|
| sites usable in both passes | **59** |
| pooled agreement, pass 0 / pass 1 | 0.8219 / 0.8204 |
| **pooled absolute delta** | **0.0015** |
| per-site absolute delta, median / p90 | **0.0000 / 0.0062** |
| identical read count across passes | 57 / 59 |

Unlike #92's drift control, this metric is **not** saturated — it sits at 0.82, so a 0.0015
floor is a real bound rather than an arithmetic consequence. Any effect smaller than
~0.2pp pooled, or ~0.6pp on a single site, is noise.

### Oracle stability — the one confound this design has

The collector runs, then `DOM.getDocument` and `getFullAXTree` run tens to hundreds of
milliseconds later. On a live site that is time for a re-render, which would make a name
disagree for a reason that is neither derivation's fault. Re-reading the oracle and
counting how many of the **reported disagreement rows** move is a direct bound on exactly
the rows it would corrupt:

| | |
|---|---|
| rows re-checked | **6,915** |
| rows whose Chrome name moved | **8** |
| | **0.12%** |

### Does Chrome ever name this role? Measured, not transcribed from a table

The biggest class needs this fact, and the honest way to get it is to count rather than to
copy ARIA's role table by hand — **which I got wrong**: my transcription put `row` among
the name-from-content roles, and Chrome names **0 of 2,103** of them.

| Chrome role | rows | Chrome HAS a name | share |
|---|---|---|---|
| `link` | 18,617 | 18,358 | 0.986 |
| `generic` | 4,035 | 224 | **0.056** |
| `image` | 2,174 | 1,494 | 0.687 |
| `row` | 2,103 | 0 | **0.000** |
| `button` | 2,015 | 1,875 | 0.931 |
| `paragraph` | 929 | 0 | **0.000** |
| `heading` | 791 | 791 | 1.000 |
| `cell` | 617 | 602 | 0.976 |
| `listitem` | 276 | 40 | **0.145** |
| `tab` | 221 | 221 | 1.000 |
| `menuitem` | 175 | 175 | 1.000 |
| `article` | 167 | 0 | **0.000** |
| all roles | 33,295 | 24,196 | 0.727 |

`row`, `paragraph` and `article` are **never** named; `generic` and `listitem` almost
never. Those roles ARE the `chrome-empty` population, and the uncapped class × role
histogram confirms it exactly: of its 5,554 rows, `row` 2,103 + `generic` 1,892 +
`paragraph` 896 + `listitem` 130 + `strong` 101 + `emphasis` 100 + `LabelText` 80 +
`time` 53 + `article` 42 + `group` 42 = **5,439 of 5,554 (97.9%)** — all of them rows
where our listing prints the element's own text and Chrome, correctly, has nothing to say.

### Which side matches the SCREEN

A third oracle, fetched only for the rows that disagreed: the element's own rendered
`innerText`. For the classes where neither spec text nor taste settles it, "which of the
two matches what is on the screen" is a measurement.

| class | rows with rendered text | **ours** matches screen | **Chrome** matches screen | neither |
|---|---|---|---|---|
| `whitespace-only` | 29 | **1** | **28** | 0 |
| `case-only` | 303 | 0 | **303** | 0 |
| `ours-superset` | 14 | 0 | **14** | 0 |
| `punctuation-only` | 182 | **179** | 5 | 2 |
| `chrome-empty` | 3,769 | **3,586** | 0 | 183 |
| `chrome-superset` | 416 | **414** | 0 | 2 |
| `partial-overlap` | 14 | **14** | 0 | 0 |
| `disjoint` | 6 | 1 | 0 | 5 |

**Read with its limit, which is not small: `innerText` does not include `::before` /
`::after` generated content.** So on `punctuation-only` — where the difference IS a CSS
icon glyph Chrome is required to include — "Chrome matches the screen 5 of 182" is an
artefact of the oracle, not evidence. It is a faithful oracle for the **separator**
question, and there it is decisive: **Chrome matches the rendered text 28 of 29 times and
we match it once.** It is equally decisive on `ours-superset` (0 / 14), which is defect
№2 — our `title`-derived name is not what the page paints.

`chrome-empty` 3,586 / 3,769 is the other half of the same confirmation: where Chrome has
no name, our row prints **exactly the rendered text**, which is the thing we want it to
print.

---

## Can the two defects be fixed without breaking anything? Measured.

`--candidate-ab` applies both diffs to the **extracted** collector and runs **both arms on
the same page load against ONE oracle read**, so run-order drift cannot align with the arm
and the oracle cannot move between them (MEASUREMENT.md R3). Movement is reported rather
than a level: a row is IMPROVED when the base arm disagreed with Chrome and the candidate
agrees, REGRESSED the other way.

53 sites (every 5th of the pool), 3 stages each, 6 errored:

| | |
|---|---|
| rows compared | 15,504 |
| entries, base → candidate | 22,352 → **22,352** (no element gained or lost a row) |
| listing characters | **+0.15%** |
| names that changed at all | 163 |
| **improved** | **80** |
| …of which Chrome HAS a name | **80 / 80** |
| **regressed** | 83 |
| …of which Chrome has **NO** name at all | **83 / 83** |
| **rows where a CORRECT name is broken** | **0** |

Attribution between the two diffs is clean, because they touch disjoint code paths: of the
163 changed names captured, the slot diff accounts for `label` 22 + `button` 15 + `div` 12
+ `span` 3 + `a` 2, and the alt diff for **4 `img` rows, all four moving straight to
`exact`** (`w2_berlin` `"Link zu: Startseite Berlin.de"` → `"Berlin.de"`, two `w2_hana`
accessibility marks).

**The 83 "regressions" are not wrong names.** Every one is a row where Chrome's role
permits no name (a `<label>`, a `<span>` inside a slot) and our row now prints the
element's TEXT — the same `chrome-empty` population that dominates the baseline and
that #74 requires us to keep printing. **The 80 improvements are all rows where Chrome has a
name and we now produce it exactly.** The first reading of this A/B was `improved 80 /
regressed 83`, a wash; splitting on whether Chrome has a name at all is what made it
readable, and it is the same correction the headline needed.

**The existing fixtures survive.** #37's `_namable` and `title` fixtures — NR1
(`display:none` child), NR1b (`visibility:hidden`), NR1c/NR1d (rendered and sr-only
controls), NR2/NR2b (`<style>`/`<script>` text), NR2c (a RENDERED `<style>`),
TA1/TA1b/TA1c (title over the wire key) — had their markup and their assertions
replicated and driven against **both** arms: **all pass in both**. The `display:contents`
exemption sits *after* `_NAME_SKIP` and still asks `visibility`, so `visibility:hidden` is
still rejected, and `alt || title` only reorders a pair where both exist.

**Both diffs have since been applied to `extension/background.js` by the coordinator, and
the real suite confirms the replication: `test_widgets.py` 258/258 with both in**, with
NR1–NR2c, TA1–TA1c and SH1/SH1b all green. Regression guards were added at the same time:
**NR3** (a slotted label names its host), **NR3b** (a `display:contents` wrapper does too),
**NR3c** (CONTROL: a `visibility:hidden` `display:contents` wrapper still contributes
nothing — the fix exempts the BOX test, not the visibility test), **TA2** (`alt` beats
`title` on one element) and **TA2b** (CONTROL: with no `alt`, `title` is still used).

**A fixture for this defect is vacuous unless it asserts the ROW SHAPE, and three attempts
in this one session got it wrong in three different ways.** Asserting `"Sign in" in
listing` passes PRE-fix, because the words reach the listing through the `near=` fallback;
asserting the quoted `"Sign in"` passes too, because `near="Sign in"` contains that
substring; and asserting `name="Sign in"` **fails in BOTH arms**, because the recovered
name arrives through name-from-content and the row prints it as the bare-text identity.
The rows, dumped rather than reasoned about:

```
PRE-FIX   ref_5 | button (unlabeled)
SHIPPED   ref_5 | button "Sign in"
```

`(unlabeled)` versus the quoted identity is the only thing that separates them — the same
fact as the `lost_identities` reconciliation above, arriving from the fixture side.

**This probe's own A/B arms survive the merge.** `_collector_src` carries BOTH anchors and
decides the direction from the source, so `--candidate-ab` reconstructs the pre-fix arm now
that the fix has shipped — MEASUREMENT.md's rule for a source-patching probe, which
`audit_retext_tier.py` and `audit_retext_prevalence.py` are recorded as having failed hours
earlier. **The first bidirectional version was wrong in exactly the way that rule warns
about**: it matched the shipped `display:contents` rule by *my* spelling of it, which the
shipped version does not use, so it silently decided the source was pre-fix and handed back
the SHIPPED collector as the baseline. It detects the block's SHAPE now and asserts each
marker is on the side it belongs to; nothing but checking the output caught it.

**Verified on a fixture, three improvements and three controls:**

```
   mmid tag     base                     candidate                 chrome
** 5    img     "Photo category"         "A dog on a beach"        "A dog on a beach"
** 7    button  ""                       "Sign in"                 "Sign in"       (slot)
** 9    button  ""                       "Contents wrapper label"  "Contents wrapper label"
   11   button  "Visible part"           "Visible part"            "Visible part"  (display:none child still excluded)
   14   img     "Only alt"               "Only alt"                "Only alt"
   15   img     "Only title"             "Only title"              "Only title"
```

---

## Sample bias, stated plainly

**14 of 265 candidates are UNMEASURED, not passed.** Nine timed out at 45 s navigation
(`w2_cdmx`, `w2_gov_pl`, `w2_osu_courses`, `w2_ntu_tw`, `w2_titech`, `w2_kaist`,
`w2_ug_lib`, `w2_dnb`, `w2_nlc_cn`), one refused the connection (`w2_catb`), and **four
served an AX tree too small to compare** (`w2_extjs_ks` 17 AX nodes against 30 mapped
mmids; `w2_unimelb_hb` 4 against 148; `w2_msu_ru` 4 against 3; `w2_su_se` 552 AX nodes
with 1,609 mapped and only 4 names). Those four are reported as unusable rather than as
zero agreement — #34's lesson applied: an empty AX tree is a silence, not a measurement.

**No user-agent spoofing and no bot-check evasion**, so a site that declines automated
traffic is simply absent.

**The large loss is inherited.** This sample is #89's, which is #85's screening of 445
candidates, so roughly 180 candidates a headless browser could not reach are missing before
this probe starts — 112 of them behind a consent wall or a bot block (banks, ticketing,
several government portals). **The sample is survivorship-biased toward simpler pages.**

**Depth is not uniform.** 97 of 251 usable sites offered nothing the picker could act on
declaratively, so the post-interaction evidence rests on 154 sites and the deepest tier on
40. **Within a site, one path**: a site whose interesting state is behind the *second* menu
is measured on the first.

**Three populations are excluded by construction and are large**: 20,676 rows Chrome
ignores, 11,578 with no AX node at all (frames the tree does not cover, plus nodes it
simply has no entry for), and 9,566 rows the listing deliberately blanks. Nothing here says
anything about those.

**Not reached at all**, inherited from #89: hover-only menus (a CSS `:hover` submenu
declares no state flip, and PRINCIPLES 1 forbids picking it by class or position); closed
shadow roots and same-origin frames are MEASURED but not PICKED FROM; cross-origin frames;
anything behind a login.

**And the question this cannot answer**: whether a name both derivations get wrong is
wrong. Chrome is an independent oracle, not ground truth — on 2,081 `punctuation-only`
rows and 1,107 `case-only` rows ours is the more useful string even though Chrome's is the
spec-correct one. The 83 `whitespace-only` rows are the opposite: the spec and the screen
agree with each other and both say Chrome.

---

## Mistakes made while measuring this

Recorded because the method is the part that transfers.

### 1. `fmt_drift = 881` was my checker's escaping assumption, not a drift

The self-check looks for the chosen identity inside the `e.line` the collector built, and
looked only for the **JSON-escaped** form. `_fmtLine` emits
`name=`/`value=`/`placeholder=`/`near=`/`href=`/`src=` through `JSON.stringify` but builds
the **bare-text identity by raw interpolation** (`` ` "${e.text}"` ``), so a label
containing a double quote lands in the row unescaped:

```
ref_383 | a "หญิงวัย 40 พบ "ไตวายระยะสุดท้าย" หลังสังเกตเห็น "เล็บมือ" ร่วม 4 อาการนี้" section=main
```

All 881 are that one case. The checker now accepts either form, and the characterisation
pass reports a clean figure. **A real finding falls out of it, and it is measured rather
than left as an anecdote — see the next section.**

## A row whose label contains a double quote cannot be parsed back

`_fmtLine` uses **two quoting conventions for the same slot**: `name=` / `value=` /
`placeholder=` / `near=` / `href=` / `src=` go through `JSON.stringify`, while the
bare-text identity is built by raw interpolation (`` ` "${e.text}"` ``). A reader pulling
the identity out of a printed row gets a silently truncated string.

`--quoting` measures it by **parsing each row back the way a consumer would** — the first
JSON-style quoted run after the `ref_N | tag` prefix — and comparing the result to the
identity the collector meant to print. 89 sites (every 3rd of the pool), 85 usable, two
stages each:

| | |
|---|---|
| rows printing an identity | **34,534** (28,420 bare-text, 6,114 JSON-quoted) |
| identities containing a `"` or `\` | 265 bare, **246 JSON-quoted** |
| parse back: ok / truncated / wrong / absent | 34,269 / **264** / 0 / 1 |
| **unparseable-back** | **264 = 0.765% of printed rows, 0.93% of bare rows** |
| …as a share of the bare rows that contain the character | **264 / 265 = 99.6%** |
| **CONTROL: the 246 JSON-quoted rows carrying the same character** | **246 / 246 parse back correctly** |
| sites affected | **11 of 85** |

**The control is what makes this a defect in the emission path rather than a fact about
the character**: the identical character is met 246 times on the other path and costs
nothing there.

**It is an i18n defect, not a curiosity, and that is the part I would not have predicted.**
It concentrates in Hebrew, where the gershayim in an abbreviation is written as a plain
ASCII `"` — standard orthography, not an edge case. `he_ynet` alone carries **202 of the
264** (≈9.9% of its 2,044 rows); the rest are `w2_leumi` 22, `w2_oebb` 12,
`w2_generali` 6, `vi_vnexpress` 6.

```
meant  "נדל\"ן"                                     reader gets  "נדל"
meant  "הבורסה בת\"א עולה בכ-1.5%, מניית קסטרו מזנקת"   reader gets  "הבורסה בת"
meant  "לפיד בשיחה סגורה: \"אסור שנתניהו יהיה רה\"מ…"   reader gets  "לפיד בשיחה סגורה: "
```

The fix is one convention: emit the bare-text identity through `JSON.stringify` like every
other field. It is #21's one-concept-two-spellings, in agent-facing OUTPUT rather than in
logic, and the cost is two characters on rows that contain the character and nothing on
any other row.

### 2. The `new` population collected every unnamed row BY CONSTRUCTION

`new` is keyed on the identity **string** (#92's rule, because mmids are additive). An
`ours-empty` row's identity is `""`, which is never in the seen set — so **every single
`(unlabeled)` row counted as revealed-by-the-interaction and none as carried**, and the
defect class concentrated itself in one arm for no reason at all. Found by re-deriving the
composition of a result that damned the revealed population (PRINCIPLES 8).

The reported `new` figure above is the corrected one: the 228 post-stage `ours-empty` rows
are removed from `new_compared` (they contribute no `exact`, so the numerator is
unchanged), giving 2,276 / 3,434 = **0.6628** against the uncorrected 0.6215. The probe now
puts them in a third `unnamed` bucket so the next run needs no arithmetic — and a run with
that code confirms the correction is exact (`unnamed_compared` equals that run's
post-stage `ours-empty` count, 64 = 64).

**The first draft of this document said "yes — a control revealed by an interaction is
named worse" on the uncorrected 0.6215, and attributed it to the slot defect with
"`ours-empty` is 134 of 726 in `new` and 0 of 5,881 in `carried`". That second sentence is
TAUTOLOGICAL under the bug** — the bug is precisely what put all of them in `new` — and it
read as evidence. A defect class that concentrates itself in one arm by construction is the
most convincing wrong finding there is.

### 3. The first firing proof planted on elements that were never a question

`--fire` tagged the first 8 elements carrying an `mmid` in document order — but the
collector stamps an mmid on far more elements than it lists, so **22 of 24 sentinels landed
on things that are not entries at all** and the proof read `moved 8, reported 0` on two of
three sites while reporting PASS. The candidate set is computed from the entries just
collected now, and the pass bar is "every planted row that **reached the compared
population** reported the sentinel", with the per-mmid disposition printed so the
denominator is readable (PRINCIPLES 16).

### 4. The rendered-text oracle is blind to the thing it was asked to adjudicate

`innerText` does **not** include `::before`/`::after` generated content, so on the
`punctuation-only` class it reports "ours matches the screen, Chrome never does" — which is
an artefact of the oracle, not evidence, because the glyph Chrome included is exactly what
`innerText` cannot see. It is a faithful oracle for the **separator** question (no
generated content involved) and is quoted only there.

### 5. The A/B's first reading was a coherent, mechanism-carrying, WRONG product finding

The first `--candidate-ab` run was taken before the split on "does Chrome have a name at
all", and read as *"the fix is a wash — 80 improved against 83 regressed"*. That is a
publishable-sounding verdict with a direction, which is what makes the class dangerous.
Splitting on whether Chrome has a name at all showed **80/80 improvements real and 83/83
"regressions" not regressions at all** — they are rows moving into the `chrome-empty`
population, which is the thing we are supposed to print. Both runs produced the identical
163/80/83, so it was not noise; it was the wrong denominator.

---

## What this establishes, and what it does not

**Establishes.** Where the collector claims an accessible name, it agrees **exactly** with
Chrome's own AccName implementation on **0.9134** of 20,156 rows across 251 live
out-of-sample sites and 329 post-interaction reads, **0.9492** once rows Chrome has no name
for are set aside, median **0.9722** per site — with a comparator proven to fire on a
fixture, on live markup (56/56 planted), and against the out-of-sample guard. **Two
defects were found, each with a one-line diff, a spec citation, and an A/B measured on the
same page load showing 80 improvements, 0 broken names and +0.15% characters.**

**Does NOT establish that the pooled 0.7519 is an error rate.** 18,486 of the 24,892
disagreements are rows where Chrome's role forbids a name and we print the element's text,
which #74 proves we must keep doing.

**Does not establish that Chrome is ground truth.** On `punctuation-only`, `case-only` and
part of `chrome-superset` — 4,930 rows — our string is the more useful one, and the
verdicts say so.

**Does not establish that the name is USEFUL**, only that it is the same name the browser
computes. Whether a model then picks the right row is #75's question, and #75 found the
benchmark substrate cannot currently carry it.

**Does not settle whether a revealed control is named worse.** The full sample says 7.4pp
worse, a 34-site subset with the corrected code says 1.5pp better, and the residue on the
full sample is dominated by composition. What IS settled is that the slot defect fires
2.8× more often after an interaction.

**Next, if this line is continued.** The two cheapest unmeasured things are the
`title`-versus-name-from-content half of defect №2 (283 of 549 saved rows of that family,
where Chrome's spec-correct answer is often less useful than ours, so it needs both halves
measured before anything moves), and the display-aware separator, which needs #28's N5
fixtures rewritten to their invariant first.
