# EVAL 6 — findings as they come in

Scored from the ORACLE (`score.py`, `POST /event/get`) and from the agents' own
counted tool calls. Self-reported SUCCESS is not used; the oracle decides.

## Pair 1 — hotels, «укажи направление: Токио, Япония»

| arm | calls | oracle |
|---|---|---|
| tree | **8** | **PASS** (`bench_hotel_select_city`) |
| flat | **9** | **PASS** (`bench_hotel_select_city`) |

Descriptive only, per the pre-registration: n=5 cannot clear H1, and one run per
cell sits inside the measured 12–14% rerun noise floor for this kind of A/B.

### Both agents, independently and in both arms, hit the same defect

**The off-viewport region hint names regions by TAG.** It read
`form(ref_212): 8, section(ref_274): 36, …`, and both agents scoped to the only
`<form>` because the task is "fill in a search form". It is the **newsletter
signup at the bottom of the page**; the hotel search widget is not a `<form>` at
all. **One fully wasted call in each arm** — so it cost the comparison nothing
and cost both agents the same, which is the only reason the pair is still
usable. Recorded as `OPEN.md` 4b. Two independent agents reporting the identical
wrong turn is stronger evidence than either report alone.

### The finding that was worth more than the turn count

**The aria-hidden note offered a recovery that structurally cannot work.** The
entire hotel search widget sat under an `aria-hidden="true"` ancestor, so
`read_page` listed 11 elements and none of them was the destination field. The
note said *"find() reaches elements this viewport-scoped listing omits"* — but
`find` searches what the COLLECTOR KEPT, and an aria-hidden element is dropped
AT collection, not filtered to the viewport. Two different drop reasons, one
sentence, and the recovery belonged to the other one.

**Verified before changing anything**, on the live page, settled:

    read_page(filter="interactive")  -> 11 elements, destination field absent
    find("Город, отель или аэропорт") -> "No elements matched"   (its EXACT placeholder)
    query_elements("input")           -> ref_92, that placeholder — and the ref CLICKS

So `query_elements` is the recovery and `find` cannot be. Fixed; `AH5` fails
against the old note, `AH5b` passes in both arms as the control that the ledger
is still named. This is #33's class inside the note written to end #33's class.

### Three more, recorded not yet fixed

- **The documented one-turn opener is unreliable on an SPA.** `[tabs_create_mcp,
  navigate, read_page]` came back with only 7 nav buttons and *THE DOM IS STILL
  CHANGING*, because the batch's settle covers the navigation COMMIT (#51,
  DOMContentLoaded) and not a client-side mount that happens after it. Cost one
  call in the flat arm. The readiness banner did fire, so it was loud rather
  than silent — the agent said it was the reason they did not conclude the
  section was missing.
- **The widget declares nothing queryable.** No `role=option` on the suggestion
  rows, no `role=listbox`, no `aria-expanded`/`aria-controls` on the input, and
  the row `<button>` has no accessible name. The agent was reduced to guessing
  class substrings and said so: *"which happened to hit, but only by luck"*.
  That is the page's defect and the honest limit of a declaration-only rule.
- **`computer(action="type")` reads as a reprimand when the ref is obvious.**
  *"Typed … into whatever holds editing focus — pass a ref"* fired on a batch
  whose IMMEDIATELY PRECEDING step clicked the target ref. The warning is right
  in general (#56: `insertText` targets the editing context, not
  `activeElement`) and wrong in tone here, and the batch has the information to
  know better.

## Pair 2 — books, «найди аудиокнигу … и добавь в корзину» (tree arm in)

| arm | calls | oracle |
|---|---|---|
| tree | **7** | **PASS** (`apply_filter`, `basket_add`, …) |

### The most serious finding of the eval so far, and it is not about turns

**A decoy pair that the listing cannot resolve.** The search returned two cards
with the SAME title, author, rating and cover text, differing only by price:

    ref_1714 | div "ТОНКИЙ ФАРФОР У ЗАКРЫТОЙ СТАНЦИИ ЭШВУД Г. … 4.8 544 599 ₽" role=button
    ref_1735 | div "ТОНКИЙ ФАРФОР У ЗАКРЫТОЙ СТАНЦИИ ЭШВУД Г. … 4.8 544 569 ₽" role=button

The TASK WORD is «аудиокнигу» — audiobook — and format is the one thing not
surfaced at any detail level. The agent resolved it by using the site's own
Формат → Аудио facet, which cost an extra round trip and was the right move.

**This is the silent-WRONG-answer shape, not the silent-missing-element shape**,
and it is worth separating from everything else in this log. An agent that
trusted the listing alone has a **coin flip here and would never know it had
lost**. Every guardrail this project has built — `lost_identities`, presence,
recall, findability, the sufficiency DS — scores PRESENCE, and both cards are
present. The agent said so unprompted, and it is right.

It is also not obviously OUR defect: if the cards declare their format only in a
class name or a URL, then the page does not state it and a declaration-only rule
cannot surface it. `detail="brief"` might have given differing hrefs, which the
agent explicitly declined to guess at. **What to measure before changing
anything:** whether the two cards differ in any DECLARED attribute at all. If
they do, that is a real gap in what we surface. If they do not, the honest
answer is that the page is ambiguous and the facet is the only route — and the
listing should arguably say that two rows are indistinguishable rather than
print them as if they were different.

### Three smaller ones

- **An unprinted ref was accepted.** The agent passed `ref_id="ref_1713"`,
  inferred as "parent of ref_1714" from the numbering. It resolved. It was
  never in any listing. Their own words: *"that was luck … an agent doing this
  systematically would be building on sand."* Refs are additive per document so
  a neighbouring integer often IS a real element; nothing warns that it was
  never shown.
- **The entry cap fired on the Books landing page** — 168 on screen, capped at
  150, `18 OMITTED BUT ACTIONABLE` plus `123 BELOW the current viewport`. Cost
  nothing here because the target was high in the listing, and the agent noted
  the OMITTED-BUT-ACTIONABLE tail is what made it harmless (#27).
- **The readiness banner fired on all six reads and was right every time** — and
  the agent still flagged it: the full `*** THE DOM IS STILL CHANGING ***`
  paragraph printed on reads where the batch had ALREADY reported `waited 256ms
  … this step read the settled page`. Two true statements that read as
  contradictory, ~6 × 500 characters of caveat already paid for in wall clock.
  Worth a look: the batch knows it waited and the banner does not.
