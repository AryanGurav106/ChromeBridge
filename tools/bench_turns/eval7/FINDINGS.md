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
