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
