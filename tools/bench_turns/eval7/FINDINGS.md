# EVAL 7 — findings as they land

Pre-registration and its three amendments are in `PREREG.md`; nothing here
revises them. Scores come from `score.py` against the oracle, call counts from
each run's transcript, and quotes are verbatim from the agents' reports.

**Read the amendments first if you are quoting any number from this file.** Runs
1–3 of the first attempt were discarded, for a reason that is the most useful
thing the eval has produced so far.

---

## What the setup cost before any result existed

**Amendment 1 — three of the eight tasks asked for an impossible date.** The
app's calendars disable past days, the task files carry dates from before the
run, and the picker has exactly one navigation control pointing forward. I
measured that carefully and attributed it to the benchmark decaying.

**Amendment 3 — that attribution was wrong, and the benchmark's own published
leaderboard said so.** `liderboard/results/raw/*/results.json` ships
per-condition results for 24 model×harness runs. One started **2026-09-16**
carries `select_date {"date": "2026-09-17"}` for the task whose file says
`2026-09-04`. Their harness rewrites the date; `bench_eval/task_dates.py` rolls
booking dates and the prompt text forward together, precisely because the
calendars disable past days. **My generator merged the task file verbatim and
never called it.**

The impossible task was mine. `make_tracks.py` now calls their function and
refuses to generate tracks if it cannot import it.

**What it cost:** three runs. They were incomparable anyway — one
Claude-in-Chrome agent declined to reach the date by editing the app's URL
(*"the task required completing through the page's own UI"*) and another did
(*"reaching the requested date required the URL parameter"*), so scoring them
against each other would have compared three different tasks.

**The reusable lesson:** #48's eval had a referee validate every task before any
run and it dropped two. Eval 7 had no such pass, and a run found this instead. A
generator that merges a task file should be read against the harness that
normally consumes it; the answer was in a file called `task_dates.py` the whole
time.

## The external baseline, recorded before our numbers existed

Published pass rates from those same 24 runs, on exactly these eight tasks:
**74/192 = 38.5%**, against a best published whole-benchmark run of
**125/152 = 82.2%**. The rail two-passenger task is **0/24**.

So this is a hard subset, chosen for condition count rather than difficulty,
and the metric has room to move instead of saturating the way every previous
head-to-head here did. **Two caveats before anyone quotes a comparison:** those
runs are scored all-conditions-or-fail while this eval's primary metric is
conditions satisfied, and they ran against their own rolled-forward dates, which
is different task text from ours. They bound difficulty, not performance.

---

## Pair 1 — rail2p (10 conditions)

| | conditions | browser calls |
|---|---|---|
| ChromeBridge | **9** | 21 |
| Claude-in-Chrome | 7 | **18** |

**Both arms lost the same condition for the same reason, and it is the task's
own ambiguity.** `basket_add` fires on «ОФОРМИТЬ ЗАКАЗ», and both agents
deliberately stopped before it. Ours: *"the remaining button is ОФОРМИТЬ ЗАКАЗ
('place the order'), which is checkout — a step past 'добавь в корзину'."*
Theirs: *"placing the order is an irreversible step beyond the request."* Both
saw the app print «добавлена в корзину» and reasoned from it. The published
0/24 on this task is consistent with that being the trap.

**The two conditions we are ahead on are real work, not scoring.** Our agent
assigned both passenger identities; theirs left both dropdowns unset, writing
*"no passenger identities were specified in the task"*.

**What their agent reported about its own listing, unprompted** — this is the
clearest representational difference the eval has produced:

> The date field, the return-date field and the passenger selector are **not in
> that listing at all** — yet they sit physically between «Куда» and «НАЙТИ» in
> the same form bar. … They're click-handled `generic` divs, and `interactive`
> only admits recognised tags/roles. **The failure is silent** — the listing
> reads as a complete inventory of what I can act on, with nothing saying "N
> clickable elements were collected but not shown".

That is #18 and #71's territory from the other side: a handler on a property or
via `addEventListener` is an admitting signal for us, and the eval did not ask
either agent about it.

### What it found in ours

- **`filter="all"` could cut the text block entirely and say nothing.** The
  agent called `read_page(ref_id=…, filter="all", max_chars=3000)` to learn
  three month headings a calendar's day cells do not carry, got 190 interactive
  rows and no text, and fell back to a whole-page read. *"It reports dropped
  elements and says nothing about having dropped the entire text section —
  which, with filter='all', is the half I explicitly asked for."* **FIXED**
  (T27); #22's silent-cut class at section granularity.
- **Two true sentences in one response that read as a contradiction.** The
  batch's `waited 256ms … this step read the settled page` sat directly above
  the read's `*** THE DOM IS STILL CHANGING (last change 283ms ago) ***`. The
  wait ends after 250ms of no structural change; the banner reports a fixed
  3000ms lookback and still counts the churn the wait sat out. The agent:
  *"I learned to ignore it — which is the bad outcome, because then it can't
  warn me when it matters."* **FIXED**; the same run records the banner
  correctly catching a mid-build first read, which is why training the reader
  past it is the real cost.
- **A MISMATCH warning that was a false alarm on both seat clicks**, already
  recorded as `docs/OPEN.md` 4e from eval 6 and now seen twice.
- **A calendar whose month titles are bare `<div class="month-title">`** —
  no heading tag, no role, no label — so ~90 day cells are indistinguishable.
  `docs/OPEN.md` 4f: reading the class name is the fix this project does not
  take, so it is the measured price of deciding structure only by declarations.

## Pair 2 — railpay (8 conditions), Claude-in-Chrome half only

**8/8, a full pass including the payment step, in 54 browser calls.** Credit
where it is due: only 1 of 24 published runs passed this task.

**11 of those calls were `javascript_tool` used as a substitute for
`read_page`.** Their agent's own summary:

> I used `javascript_tool` **11 times purely as a substitute for `read_page`**,
> hand-rolling my own element locator via `getBoundingClientRect()`. An agent
> without JS access could not have finished this task.

It also hit **our limitation #12 on their stack** — a password manager injecting
a `chrome-extension://` iframe when the card field is focused, which makes
Chrome refuse the debugger attach tab-wide. Their error:

> `Failed to execute JavaScript: Cannot access a chrome-extension:// URL of
> different extension`

> The message names **neither the tab, nor the offending extension, nor the
> cause, nor what still works**.

That is the same Chrome policy #12 documents, and #12's `attachDebugger` names
the offending extension, explains the frame-tree rule and lists what still
works. Worth stating carefully: this is a shared platform limitation, and the
difference is only in what the message tells you.



**The ChromeBridge half: 8/8 as well, in 28 browser calls.** A tie on the
oracle, and the call gap is the whole difference on this pair.

Its own event-log verification is worth quoting, because it is the kind of
evidence a self-report cannot fake:

```
basket_add:     train 022 "ТВЕРСК", departure_date "2026-11-16",
                seats [carriage 03 seat 1, carriage 03 seat 2],
                passengers [Ярославцев Сергей Александрович, Мария Сидорова]
submit_payment: result "success", amount 10000
```

It also hit limitation #12 on the card page and **named the degradation rather
than failing**: *"trusted input is blocked on this tab by another extension's
injected iframe; used the untrusted pointer-event path instead"*, and the
payment went through. Same Chrome policy that stopped the other arm's CDP
entirely; the difference is the fallback and the sentence.

---

## Pair 3 — hoteldxb (6 conditions): TIE, 6/6 each, 19 calls each

**The most informative pair so far, because both arms struggled on the same
page for OPPOSITE reasons.**

**Theirs got the controls and not their identities.** Verbatim from its report:

```
textbox "Город, отель или аэропорт" [ref_10]
button [ref_11]  button [ref_12]  button [ref_13]  button [ref_14]
```

> `ref_11`–`ref_14` are **Заезд**, **Выезд**, the guests selector, and
> **Найти**. No name, no text, no value, on any of them … four buttons that
> differ only in what they say, listed as four buttons that say nothing.

Every interaction from that point ran on screenshot pixels, and it never used
`form_input` at all.

**Ours got the identities and not the controls.** The whole widget sits under
`aria-hidden`, so the listing dropped it — and named the recovery, which worked
and cost calls.

### What it found in ours

- **`4j` — our aria-hidden note promises refs `query_elements` cannot give.**
  It says *"its refs act normally"*; mmids are stamped by the COLLECTOR, so
  anything rendered since the last `read_page` carries none. The agent followed
  our own advice, queried a suggestion button that had just appeared, and got a
  row with no ref. **HALF FIXED**: both sibling renderers now say so, and both
  fire on ANY ref-less row rather than only when every row lacks one — the mixed
  case is the common shape and the all-or-nothing guard `search_page` has
  carried since #32 was silent for it.
- **`4b` REOPENED, by two agents on the same hint.** The page's only `<form>` is
  the NEWSLETTER SIGNUP; both scoped to it expecting the search widget. #80's
  fix is working as designed and its sources (aria-label, aria-labelledby, first
  heading) are all absent there.

## Pair 4 — hotel2rm (5 conditions): TIE, 5/5 each, 13 calls to 10

Their most efficient run of the eval. Ours spent ~3 calls on the same
aria-hidden recovery as pair 3.

- **A banner of ours printed TWICE in one response**, differing only by a
  counter ticking between two observations. #77 decided that duplicate by EXACT
  STRING EQUALITY so that nothing would be a judgement; exact equality loses to
  a counter. **FIXED** — decided by the banner's TIER, read off the marker
  phrase this codebase emits (#39's rule: our own notation, not the page's).
- Their agent compared its tool to **ours**, quoting our server instructions,
  which is how Amendment 4 came to exist.

## Pair 5 — shop3 (3 conditions): TIE, 3/3 each, 16 calls to 18

### The joint finding: one widget that defeats BOTH representations

The product card's quantity stepper is a custom `−  N  +`. Both arms failed on
it, differently, and **both noted that the CART page lists the same concept
perfectly**:

| | on the product card | in the cart |
|---|---|---|
| **ChromeBridge** | `button "1"` and `button "1"` — the quantity VALUE adopted as the accessible name of BOTH buttons | `button "minus"` / `button "plus"`, correctly |
| **Claude-in-Chrome** | `button [ref_62]`, `button [ref_63]` — anonymous, and the quantity invisible entirely | `textbox "3"`, readable |

Ours is the worse failure of the two and it is recorded as such
(`docs/OPEN.md` 4l): **a name that is confidently wrong is worse than
`(unlabeled-icon)`**, because clicking the wrong one at quantity 1 removes the
item, and the agent had to spend a call on an attribute query that could not
settle it either before resorting to a screenshot. Theirs at least sends you
straight to the screenshot.

**No presence-based ruler can see this.** Both elements are present, listed,
named and clickable; `measure_findability` would score them a hit. It is the
"two rows that mean opposite things, printed identically" class named in eval 6,
and it is the strongest argument in this eval for why live runs still find what
corpora cannot.

### Also from this pair

- **`back` was skipped for a DOM change the batch itself caused** — 324 → 331
  elements from a click swapping a button for a stepper, no navigation. **FIXED**:
  history is moved by navigation, not by a re-render. The message was wrong too,
  saying the step *"names a ref or coordinate"* when `navigate(url="back")`
  names neither; there are four ways to address the old page and both the inline
  message and the end-of-batch summary named two.
- **`4m`**: a checkbox printing `value="true"` in the slot our legend defines as
  CURRENT CONTENTS, while its actual state is unchecked.
- **An app bug both arms met**: the catalogue reuses card state by list
  POSITION, so after adding Felix ×3 an unrelated product's card showed a
  stepper reading 3. Their agent caught it only by opening the cart; ours never
  hit it because it navigated into each product page. Neither toolset can
  distinguish "3 of these are in your cart" from "this card is showing another
  product's leftover state" — the page declares nothing either way.

## Pair 6 — filespdf (3 conditions): TIE, 3/3 each, **6 calls to 11**

Our cheapest run of the eval. Theirs spent four calls on a tool that could not
distinguish its own two meanings (see below); ours spent one on resolving which
of two identically-named download links was the PDF.

- **`4n` — a FILTERED miss reads exactly like a silent page. Found on THEIR
  arm, and ours has it in two tools.** Their agent filtered its network reader
  for `lab-reports`, got `No requests matching`, concluded nothing had fired —
  while four `POST /event/add` requests confirming the action sat in the same
  buffer. It then **clicked the download a second time to make it fire**, on an
  app whose entire purpose is recording what you do. Ours says
  `"No network requests recorded for this tab matching \"X\"."` and
  `"No console messages matched."` — neither states the unfiltered total, which
  is already computed one line above. **Worth noting the mechanism: the eval's
  value is not only the comparison. An agent on the other toolset described a
  defect, and checking ours against the description found the same shape.**
- **`4o` — a navigate gets the COMMIT wait, not the CONTENT wait.** `click ->
  read_page` settles inside a batch and `navigate -> read_page` does not,
  because `_quiet` is gated on a step having ACTED. On a Vue app the opening
  batch returned a listing holding only the 7 nav buttons. The agent:
  *"the machinery exists and works well; it just doesn't fire after navigate …
  For an SPA the first paint happens strictly after the point navigate returns."*
- **`4p` — a download click has no page-side consequence**, so re-reading the
  page is structurally incapable of confirming it. Both arms hit it.
- **Two download links with byte-identical accessible names**, separable only by
  `href`. Our `detail="brief"` recovered it in one call and the legend named the
  exact parameter. The agent's observation is the general one:
  *"the gate appears to ask 'does this row have a name'; the question that
  decides whether I can act is 'does this name distinguish it from its
  siblings'."* #37 already drops a `near=` that is shared across rows; the
  inverse — ADD one when the NAME is shared — is the missing half.

## Pair 7 — booksexp (2 conditions): TIE, 2/2 each, 14 calls to 15

The hardest task conceptually: "the most expensive book by this author" cannot
be answered by locating a string, and #20 measured `find` at 0% on goal→element
precisely because there is no lexical overlap between a goal and the control
that achieves it. Both arms solved it the same way — search, paginate, read the
prices as TEXT, then act.

Both also hit the same trap and both avoided it: two cards with identical title,
author, rating and review count, differing only in price (689 / 639 ₽). The
distinguishing fact — audio versus text edition — **is not on the card at all**.
Ours resolved it with one `search_page` returning both refs and both prices;
theirs with two scoped reads in one batch. Neither was fooled, and the app's own
cart line proves the data exists upstream of the card.

### THE SHARPEST ARCHITECTURAL CONTRAST IN THE EVAL, stated fairly

Their `find` returned, verbatim:

> `ref_377: button "Добавить в корзину" (button) - Add-to-cart button for
> "Медный вензель над тихой рекой" book card (first occurrence)`

A quoted accessible name and a confident role description. A scoped read of the
same card at the same instant returned `button [ref_377] type="button"` — **no
accessible name at all.** It was the favourites heart. The agent clicked it,
**wrote to the user's favourites list**, and spent 3 of its 15 calls
discovering and undoing that.

Its own diagnosis is the useful part: *"a miss would have made me look harder,
whereas a confident wrong answer made me click … if find is deriving labels from
an LLM reading the page rather than from the DOM, the quoted-string format is
actively misleading — a quoted `"…"` reads as an accessible name and should only
ever be one."*

**Ours cannot do that, and the reason is structural rather than clever.** #20
established `find` is a LEXICAL matcher over what the collector emitted; it
ranks entries and cannot invent a name that is not in the listing. A name it
prints is a name the collector derived, from something the page declared.

**And that is not immunity, which this eval also demonstrated.** `OPEN.md` 4h,
from pair 2 of this same run: our `find` returned a payment radio advertised as
`near="Банковская карта"` whose own `value` read `yoomoney`, and the radio that
genuinely is that option was not returned at all. Acting on it selects the wrong
payment method.

So: **two different failure modes, neither immune.** Theirs can surface a label
that exists nowhere; ours can only surface something the collector derived —
which means our wrong answers trace back to a derivation that can be measured,
ablated and fixed, and 4h names exactly which one. That is the whole argument
for deciding from declarations rather than from inference, and it is worth
making with our own failure attached to it.

---

## The safety property, checked rather than assumed

Both arms were given the identical instruction to work in a tab they create and
leave pre-existing tabs alone. #47 recorded the other arm hijacking an unrelated
tab in **5 of 9 runs** when nothing told it not to, and its agents asserted
those tabs were "yours to clean up".

**Under the instruction, across 15 runs, zero hijacks on either arm.** The two
tabs that were open when the eval started — an ETH course catalogue and an OEIS
page — are still open at their original URLs, checked at the end rather than
assumed.

**One hijack did happen and it was mine, before the eval began.** My very first
Claude-in-Chrome call to test reachability was
`[tabs_create_mcp, navigate, read_page]` with no tabId, and it navigated the
ETH tab rather than the one it had just created. I restored it by hand. That is
the defect #46 fixed on our side, observed once more, in the one place I was
not running an experiment.

Two things follow, and the second matters more:

1. **The instruction works.** Telling an agent to stay in its own tab is
   sufficient on both arms.
2. **It is only sufficient when someone writes it.** Their agent could not
   batch the create with the navigate — `navigate` requires an explicit tabId
   inside a batch, and the standalone shortcut its own docs advertise navigates
   "the first tab in the session's group", which is not guaranteed to be one it
   made. Its own words: *"the advertised fast path is unusable under the exact
   constraint most of these tasks impose."* So on their arm obeying the
   instruction costs 1–2 calls per task; on ours the tab threading makes
   obeying it free, and makes disobeying it structurally difficult.

That is a capability difference with a safety consequence rather than a turn
count, and it is the one I would put first.
