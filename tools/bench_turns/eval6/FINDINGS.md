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

## Pair 2 complete — books

| arm | calls | oracle |
|---|---|---|
| tree | **7** | **PASS** |
| flat | **7** | **PASS** |

Dead level. **Both agents independently hit the decoy and both resolved it the
same way** — the site's own `Формат → Аудио` facet — which is corroboration no
single report could give.

### The sharpest finding of the eval, and it is a DECIDED trade-off, not a bug

The flat agent noticed something the tree agent did not: on the product page the
`Текст` / `Аудио` toggle carried **no selected marker of any kind** in the
listing, so nothing said which edition the «Добавить в корзину» button was bound
to. They inferred `Аудио` from four other facts (the breadcrumb, a duration
field, a narrator field, and the price matching the filtered result) and said
so plainly:

> had the toggle defaulted to Текст I would have had no row-level signal and
> would have added the wrong item **while reporting success**.

**MEASURED on the live page rather than assumed.** The two buttons declare
nothing — no `role`, no `aria-selected`, no `aria-pressed`, no `aria-current`,
no `aria-controls`, no `tabindex`, no inline style, no distinguishing `data-*`.
They share six class tokens and differ by exactly one:

    Текст : (no extra token)
    Аудио : "active"

So the ONLY signal on the page is a class name.

**And a rule that would have caught it existed and was DELETED on evidence.**
#29 kept an exact `active|selected|current` class token as an instrumented last
resort "until measured dead", and it was then measured dead: ablated across 99
live pages with a per-page drift floor, **its total effect on the `active` field
was ZERO**, because the two declared signals — the selected tab's
`aria-controls` panel being the rendered one, and ARIA's roving tabindex —
always decided first. That corpus includes shadcn, chakra, antd, **vuetify**,
ng_material, bootstrap, headlessui, openui5 and react_aria.

This page is Vuetify and declares neither signal. So the deletion was correct
about its corpus and the corpus did not contain this shape — **#25's rule
exactly: an ablation measures the code against the sample, it cannot measure the
sample.**

**NOT REINSTATED, and the decision is the owner's rather than mine.**
Reinstating a class-name wordlist is precisely what the brief forbids ("dont
hardcode, add regex, pattern matching stuff that may break") and what #27/#28
removed from every path that decides something. The measured cost of keeping it
out is now concrete and is recorded here rather than argued: **on a page whose
only state signal is a class token, an agent can add the wrong item and report
success.** That is the silent-WRONG-answer shape, which no presence metric in
this project can catch — the second instance of it in one pair.

### Also reported by BOTH books agents, unprompted

**The readiness banner fired on every single read, including reads the batch had
already declared settled.** One of them: *"the full `*** THE DOM IS STILL
CHANGING ***` paragraph printed on reads where the batch had ALREADY reported
`waited 256ms … this step read the settled page`"*; the other: *"I ignored it
each time and was right to, which is the failure mode where an always-on warning
trains you to skip it."*

Two true statements that read as contradictory, and it is the exact failure #15
priced and #43 deleted `readyState` for. **It is also plausibly caused by my own
#70/#77 work**, so it needs measuring rather than defending: how often does the
banner fire on a read the batch has just settled, and is the DOM genuinely still
changing at that instant? Recorded as a thing to measure.

### Two smaller ones

- **An unprinted ref was accepted** (`ref_1713`, inferred as "parent of 1714"
  from the numbering). It resolved. Refs are additive per document so a
  neighbouring integer often IS real; nothing warns that it was never shown.
- **The cap is spent on duplicates of one record.** One book card consumed
  ~8 entries — the clickable card, then its title div, author div, rating div
  TWICE (two refs carrying the same `"4.8 365"`), plus two spans splitting the
  rating into `4.8` and `365`. 168 on screen, capped at 150. The cap is being
  paid for repetition of one record rather than for distinct books.
