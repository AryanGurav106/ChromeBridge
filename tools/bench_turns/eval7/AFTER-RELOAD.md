# The live AFTER state, on the reloaded build

Taken through the same real Chrome, on the same benchmark pages, against
`BEFORE-RELOAD.md`. #43's rule: fifteen fixtured fixes with no live pass
produced seven regressions, so the baseline exists precisely so this is a
comparison and not my memory of one.

Worker `rvr3no`, age 53s at the start of the pass, `bridge_ms_total` reset to
7.4 — which is what proves the stdio server respawned rather than the client
merely re-handshaking. `server_code_changed_since_start` silent, so both halves
are the code on disk.

---

## 4l — a stepper's `−` and `+` both named by the quantity

`/e7_cb_shop3/item_714958775/bench_catalog_item`, item in the cart.

| | |
|---|---|
| **before** | `ref_1151 \| button "1"` and `ref_1154 \| button "1"` |
| **after** | `ref_235 \| button (unlabeled-icon) near="В корзинеПерейти"`<br>`ref_238 \| button (unlabeled-icon) near="1"` |

The false name is gone — `synthLabel`'s card-pattern branch no longer adopts a
parent's text when that parent holds a SECOND control, because then its text
labels the GROUP. And the two are now DISTINGUISHABLE, which the before state
was not: the `near=` hints place one before the quantity and one after it, so
minus and plus are separable without a screenshot. Clicking the wrong one at
quantity 1 removes the item, so this is the case that could not be guessed.

`query_elements('.qty-btn', attributes=["class","aria-label"])` returns
`(no text) class="qty-btn"` for both — i.e. the page itself declares nothing
that separates them, which is what made the old row a fabrication rather than
a reading.

## 4q + 4d — the match's record, and the climb that reaches it

`/e7_cb_grocat/produkty_11/bench_grocery_category`.

| | |
|---|---|
| **before** | `<div ref_1285 "Оливки"@0> Оливки Доставка, без косточки \| 330 г \| 229 ₽` |
| **after** | `<div ref_627 "Оливки"@11> Консервы \| Оливки Доставка, без косточки \| 330 г \| 229 ₽  [record: ref_620 <div>]` |

Two changes in one row. `[record: ref_620 <div>]` is 4q — the climb already
stood on the card to build the context and reported only the leaf. And the
match offset moved from `@0` to `@11` because the climb now reaches the card
itself, so the context quotes from BEFORE the match too (`Консервы |`).

**And the route is actionable, which is the whole claim:**

```
read_page(ref_id="ref_620")
 ref_623 | div "Оливки Доставка, без косточки 330 г 229 ₽" role=button
  ...
   ref_633 | button name="Добавить" near="229 ₽"
```

That is the button the eval-7 agent needed and could not reach. It had to pair
the title with the button by REF ORDER and said so: *"a wrong inference
silently adds the wrong product."* It is now two calls and deterministic, and
the `near="229 ₽"` on the button is today's `near=` work separating one
«Добавить» from the forty others on the page.

## 4n — a filtered miss reads as a quiet tab

| | |
|---|---|
| **before** | `No network requests recorded for this tab matching "…".` |
| **after** | `No network requests matching "nothing-will-match-this" for this tab (53 request(s) recorded — the pattern excluded them, it is not that the tab was quiet). Re-run without urlPattern to see them.` |

Exactly the AFTER the baseline predicted.

---

## Confirmed working, unasked

- **The readiness split (#70) and its scoped bound (#80).** A mid-build read
  gave `*** THE DOM IS STILL CHANGING (last change 0ms ago; 60 change(s) in the
  last 3000ms: 54 structural, 2 text, 3 @class, 1 @data-v-app …) ***` and a
  `search_page` in the same batch correctly found nothing and SAID not to
  conclude absence — which is the banner earning its keep rather than a
  regression. Once settled the same page read `*** DOM STABLE, NETWORK BUSY.
  No DOM change for 3712ms; separately 8 image(s) still loading. ***`, the
  two-sentence split, with `imgs` reported page-wide per #77.
- **The scoped UNKNOWN bound.** Every scoped read returned *"nothing inside a
  page can have changed more recently than the page did — so your subtree has
  been quiet for AT LEAST that long"* with a real number (12s, 15s, 35s), which
  is #80's entailment replacing the wasted "re-read unscoped" call.
- **The one-turn batch start (#46)** and the tree format throughout.

## One cosmetic observation, not chased

`near="В корзинеПерейти"` has no space between the two inline spans it
concatenates. `near=` is innerText-based rather than AccName, so #28's
separator rule does not apply to it; the string is still usable as a position
hint, which is all the legend claims for it. Recorded rather than fixed,
because changing a hint's joining is a measurement (#37 priced this family at
0.031%) and nothing here is wrong — only slightly harder to read.
