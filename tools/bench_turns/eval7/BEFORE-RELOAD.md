# The live BEFORE state, captured on the shipped build

Taken through a real Chrome on the running benchmark, **after** the fixes were
written and **before** the reload that makes them live. The point is that
#43's rule — fixtures encode what you thought of, so a live pass is owed —
needs a baseline that is not my memory of an agent's report.

Worker `p5fcai`, the build eval 7 ran on. Server likewise stale (Amendment 5).

---

## 4l — a stepper's `−` and `+` both named by the quantity

`/e7_cb_shop3/item_714958775/bench_catalog_item`, after adding to the cart:

```
ref_1146 | button "В корзине Перейти" section=main
ref_1151 | button "1" section=main
ref_1154 | button "1" section=main
ref_1156 | button name="Добавить в избранное" section=main
```

**Same ref numbers the eval agent reported** (1151, 1154). Minus and plus, both
named `"1"`, with the item's quantity between them. Clicking the wrong one at
quantity 1 removes the item.

AFTER should be: neither carries `"1"` as a name; both read `(unlabeled-icon)`
with `near="1"`, which is honest.

## 4q — `search_page` names the leaf and no route to the action

`/e7_cb_grocat/produkty_11/bench_grocery_category`, after a `read_page` so
mmids exist:

```
1 match(es) for "Оливки":
  <div ref_1285 "Оливки"@0> Оливки Доставка, без косточки | 330 г | 229 ₽
  (`"text"@N` is the match and its character offset in the context quoted on that line; …)
```

**Again the same ref the agent saw** (1285). No `[record: ref_N]`, and the
trailer does not say the ref owns the MATCH rather than the whole context.

AFTER should be: a `[record: ref_N <div>]` on the row, and the trailer's
"the ref owns the MATCH" clause.

## 4n — a filtered miss reads as a quiet tab

```
read_network_requests(urlPattern="nothing-will-match-this")
→ No network requests recorded for this tab matching "nothing-will-match-this".
```

No count of what IS held, so this is the same sentence a genuinely silent tab
produces.

AFTER should be: `No network requests matching "…" for this tab (N request(s)
recorded — the pattern excluded them, it is not that the tab was quiet). Re-run
without urlPattern to see them.`

## Already working, and worth recording as such

- **The region hint names a region that declares one.** The same page printed
  `They are in — main "Доставка и возврат"(ref_18): 16` — #80's fix working,
  which is the half 4b did NOT break. 4b's gap is a `<form>` declaring nothing,
  and that fixture is RG2d.
- **The readiness banner's tense defers to `since`** (#80's R-TENSE): every read
  above carried "the age above says when the last one was, and it is the number
  to judge by", not a bare present tense.
- **The batch settle fired on every click→read**, e.g. `waited 258ms for the DOM
  to stop changing after step 0 acted`. The reworded version is server-side and
  not live, so this is the OLD wording — which is itself the 4-run finding.
