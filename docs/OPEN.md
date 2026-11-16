# Open questions, ranked

The single working list. Each entry carries its evidence, because an open item
without evidence is a rumour and this project has had to delete several.

**When something closes, delete it from here** and leave the history in
`CLAUDE.md`. A stale open item sends the next reader to re-derive something
already done — and a retraction at the bottom of a long entry does not retract
the heading (#67).

Status key: `OPEN` · `IN FLIGHT` (being fixed now) · `MEASURE FIRST` (do not
build until the number exists) · `ACCEPTED` (a limit we are choosing to keep,
documented rather than fixed).

Closed this session and deleted from here: a variable reaching the input and
the assertion but **not the target** (a flow acting on the thing it just
created bound to the record a PREVIOUS run left and reported PASSED), and an
assertion tool that was REFUSED or RAISED being reported as a failed assertion
rather than as a check that never ran. Both in `FLOWS-FAILURE-SURFACE.md`
(2.6, 5.6), both pinned by checks that fail against the pre-fix code.

Last reviewed: 2026-11-15. Closed and deleted from here since the last
review: `query_elements`' missing visibility count (Q6c-Q6f), and the
readiness window measured in an unthrottled regime (R23/R23b — a 1000ms
window is 50.7% false-quiet at a 2s commit interval; 3000ms is 0.0%). Closed this session and deleted from here:
the kana fold collision, silent truncation loss in the default format,
`require` never firing, resume binding the wrong target, the handler-property
blindness, and the locale hazard (which did NOT reproduce) — all in `CLAUDE.md`
#71, #72 and #73; **item 14 (`opacity:0`)** — measured and CLOSED as DON'T
BUILD (#78): 175 elements across 21/96 sites, **0 declare any ARIA role**, **0
identities lost**, and Chrome keeps 149 of them but the only interactive ones are
14 skip links and 2 back-to-top buttons, transparent precisely because the page
is not offering them; on the text half the risk surface is **505 characters
corpus-wide** (in-viewport AND not aria-hidden) against 22,252 if you cut on
opacity alone, with **0 of 434 sampled strings matching the success/error
vocabulary** that motivated the question. Probe kept at
`tools/audit_opacity.py`. And **`query(scope,…)` as dead code** — WIRED rather than
deleted, on a measurement (`CLAUDE.md` #76, `READINESS.md` §5b). Its residual is
narrower and lives in `READINESS.md`'s own open list: landmark attribution for
an UNSCOPED read is still unbuilt and is a different problem, needing a rule for
which landmark owns a record and a way to print several at once.

---

## Tier 1 — a wrong answer reaches the user

### 0. Reachability by name — MEASURED at 0.9996, residual is ONE element — CLOSED
Every ruler here measures PRESENCE — presence, `lost_identities`, Mind2Web
recall, and item 12's own DS. CLAUDE.md #74 found 118 elements that were
present in all of them and unreachable by `find`, on a page the readiness probe
called settled, including by their VERBATIM label. The listing was correct
throughout; the tool reading it was not.

Three of this session's defects were in the tools that READ the listing rather
than in the listing (the `find` blanking, the table column misalignment, the
submit verdict), and **no offline measurement in this repo could have caught
any of them**. A ruler that scores `find` against the labels the collector
emitted — ask for each entry's own printed identity and check it comes back —
is now built: `tools/measure_findability.py`. **811/824 = 0.9842** across 34
frozen sites, with contested identities (shared by several entries, so the
probed one can fall outside find's bounded result set) counted separately.

**And the claim that it would have caught #74 is FALSE on this corpus** —
ablating the fix gives the identical number, because none of these 34 sites has
#74's shape. `--self-test` builds it synthetically and DOES fail against the
pre-fix scorer, with a known-miss control passing in both arms; that is the
guard, and the corpus run is the population number. Two different jobs.

**Residual: 13 misses, all one shape, none an app shell** — a label joined to a
badge (`span "Search Cmd+K"`, `a "Issues 5k+"`, `ul "4.1.0 25.9k 6.1k"`). The
name is assembled, so it is blanked, and unlike ptable's tile some contributors
ARE kept entries, so it is not a sole carrier. **The metric is therefore
stricter than the agent's real situation**: find("Issues") returns the inner
span, and clicking it does what clicking the link would, which is the same
reasoning #18/#73 use to credit a descendant on Mind2Web. Deciding whether to
credit a descendant here should be taken on its own merits, NOT while looking
at the misses it would erase.

**#75 THEN REPORTED THAT A DESCENDANT-CREDIT ARM ADDED 0 AT 95 SITES, AND THAT
IS RETRACTED — it had measured a closed browser.** `one()` closed its Playwright
context in a `finally` BEFORE the probe loop ran, and `_descendant_returned`
ended `except Exception: return False` — so every call evaluated against a dead
page, swallowed the error, and answered "no descendant". The arm was 0 BY
CONSTRUCTION, and the refutation it was taken to be was an artefact. The helper
no longer catches: a question that could not be ASKED is not an answer of no.

**Re-measured with the arm alive, 84 frozen sites, 2,661 unique identities:
0.9797 strict -> 0.9996 with descendant credit. 53 of the 54 misses are the
label+badge shape**, so the explanation above was right all along and is now a
number rather than a theory.

**The single element reachable by NEITHER is `carbon`'s `div "All about Carbon
What's happening Designing Dev…"`** — a container whose accessible name is a
page section's worth of concatenated text, with its contributors all kept as
their own entries. That is precisely what the blanking rule exists for (#34,
#35, #74): `find` declining to confidently return a div wrapping half the page
is the rule working, not a defect. **This item is closed as measured; what is
left is one element, and it is the intended behaviour.**



### 1. The observe→act gap is unguarded `OPEN`
We re-measure refs at click time but never compare what is there **now** against
what was **observed**. The model turn in between is ~3.6s (#38), which is the
whole exposure window.

Evidence: [arXiv:2603.00476](https://arxiv.org/abs/2603.00476) — **all 10
evaluated browser agents vulnerable, 100% trigger ratio**, prompt-only
mitigation gave no improvement; a MutationObserver (into shadow roots and
same-origin iframes) **plus a ResizeObserver**, checked immediately before
execution, gives **0% trigger at <0.05s**.
[arXiv:2610.39282](https://arxiv.org/abs/2610.39282) measures stale clicks at
**0.4% on a settled page vs 17% at DOM-ready**, and its break-even formula puts
the worthwhile-check threshold at **≈1.2% for an irreversible action** — i.e.
`fill_form(submit=True)`.

What we have: #51's `page_fingerprint` ref-resolution check is the machinery.
What we lack: a **ResizeObserver** (an overlay that shifts a box without
touching the DOM is invisible to a ref check, and `(occluded/blocked)` is
computed at listing time, not action time), and observation **through** the
model turn rather than at step boundaries.

### 2. 59.4% of ordinal-bearing descriptors cannot be witnessed `ACCEPTED`
The re-sort mis-bind is **closed on the `resort` arm, for the witnessed
minority** (#72): `resort` on a witnessed descriptor is **0.0% WRONG at 94.3%
CORRECT**, for +0.2pp refusals on the six pre-existing mutations. What remains
is crowds identical in every declared field *and* in their surroundings, where
nothing the collector emits separates the members. They are no worse than
before and no better.

**Two corrections to how that was written down**, both checkable and both now
carried in `FLOWS-FAILURE-SURFACE.md` 3.3a. The witnessed set is a **minority**,
not a majority — 212 of 558 (38.0%) on resort, 238 of 586 (40.6%) on reorder,
which is the same fact as the 59.4% in this heading. And the closure number is
from the `resort` arm alone: on the adversarial `reorder` arm a **witnessed**
descriptor is **71.4% WRONG** (#72's own table; re-derived at 55.6% on a
different 6-site sample). An anchor-only witness stays put while its element
moves, so whichever member arrives at the recorded anchor is bound confidently
and reported as a successful `moved` re-bind. #72 dismisses that arm as not
physically realisable, which is an argument rather than a measurement.

Refusing them was rejected deliberately: it would pause ~14% of all descriptors
on an **unchanged** page, which is not a safety cost but losing the feature. The
recorder warns at record time instead, and the step carries a `review` line.

**Flows recorded before #72 carry no witness** and keep the old behaviour until
re-recorded.

What would close it: a declared per-member discriminator the collector does not
currently emit. Geometry would do it (87.3% coverage, measured) and is refused —
it drifts, so the safeguard would fire on every reflow.

### 2c. Starting state: the precondition reaches 1 flow in 20 — CLOSED
`require` is derived from the observations between the landing navigation and
the first action, and `_checks` understands exactly three tools: `get_url`,
`search_page`, `query_elements`. The opening every agent is taught (#45's
`instructions=`, #46's `browser_batch` description) is
`tabs_create_mcp → navigate → read_page`, and **`read_page` contributes
nothing**. Measured across `flows/*.flow.json`: **1 of 20 carries a `require`**,
and that one was recorded to demonstrate the feature.

Not a one-liner: `read_page`'s first line is
`Current URL: <pathname + search>` while `expect.url` compares against
`get_url`'s ABSOLUTE url, so deriving one from the other would put two
spellings of one fact into the file (rule 17). Either a path-shaped check kind
or a reconstruction from the flow's origin, and both are schema-level.

**CLOSED, with the first of those two.** `path` is now a check kind: the
recorder takes `read_page`'s first line and nothing else from a listing (the
rest is prose, which the `_checks` docstring is explicit must never become a
check), and the runner reduces the live `get_url` the same way
(`urlsplit` -> `path + '?' + query`) so both halves of the comparison are one
spelling of one fact. **The reconstruction was the wrong one of the two
options**: it drops a `#fragment` the live `get_url` carries, and by the time a
path reaches us a page with a hash is indistinguishable from one without.
`path` is also the better check for the job — a flow recorded against
`localhost:8787` must not fail because the port moved, which is the argument #61
used for preferring a same-origin href as a bare path (FR24c).
When `get_url` WAS called, `url` wins and `path` is dropped rather than asserted
twice (FP11c). FP11/FP11b/FR24 fail against the pre-fix recorder with `require`
coming back `{}` — the exact symptom. Flows already on disk are unchanged; they
acquire a precondition only when re-recorded, which is why this is HALF closed:
**the mechanism now reaches the opening every agent is taught, and the 20 files
in `flows/` still carry what they carried.**

Compounding it, and unlisted until now: nothing isolates one replay from the
next. `run_flow(stop_after=N)` ends mid-flow by design, `run_flows.py` creates
ONE tab for a whole batch, and `_pg_reset` runs only under `--playground` — so
the `ev-*` flows replay back-to-back in one tab with no isolation. Every flow on
disk happens to begin with a `navigate`, which is what has hidden it.
`FLOWS-FAILURE-SURFACE.md` 6.5–6.7.

**THE SECOND HALF IS CLOSED TOO, and the two halves are complementary rather
than redundant.** `run_flows.py` now creates a tab PER FLOW and closes it after
(best effort — a flow that navigated itself into a tab of its own, #58, leaves
the outer one closable, and a tab already gone is not worth failing a suite
over). That PREVENTS the coupling; the `path` precondition above CATCHES it when
it happens anyway.

**Demonstrated rather than asserted**, by building the shape no flow on disk
has — a real recorded flow with its leading `navigate` stripped, so it can only
work on state someone else left:

```
FAIL  zz-no-navigate-probe   0/2 step(s) in 6.09s
      the app is not in the state this flow starts from: path is 'about:blank',
      recorded '/logout'. Stopped before step 0 (fill_form). Nothing was run.
```

Both halves visible in one line: the tab was fresh, and the precondition named
the mismatch instead of filling a login form on whatever page was there.

**Building that probe found a defect in the `path` work itself**, two hours
old: `validate_expect` special-cased `url` as a bare string and let `path` fall
through to the mapping branch, so **a flow whose recorder had written a path
check could not be loaded at all**. FP11 drives the recorder, FO7 drives the
validator, and nothing drove one through the other — #19/#30's untested link, at
the load boundary. **FO8 closes it generically**: for every kind the schema
declares, round-trip a recorder-shaped value through `from_json`, so a new kind
that is not taught to the validator fails there rather than on someone's first
real flow. It fails against the pre-fix validator with the live error, and
`FO8[url]` passes in both arms as the control.

### 4. `no_effect` and the hollow/unproven classifier — CLOSED
They now compose. The dead-click guard gated on `not step.expect`, and a
hollow assertion is a TRUTHY dict, so the guard skipped exactly the population
#57 and #68 exist to identify: a check that was already true before the step
cannot catch a click that did nothing, and nothing else was looking.

`Step.review` was persisted by #72 and read by nobody — the half-contract
shape this project keeps finding. The recorder now marks the fully-unevidenced
case at RECORD time (`unevidenced:`), because it already knows which checks
were hollow or unproven and re-deriving that from prose at replay would be a
second spelling of a fact we hold (#21). The runner keys on that prefix alone.

Unevidenced is still NOT a failure on its own (#68) — it only decides the tie
when the tool ALSO reports it did nothing. FR21 fails against the pre-fix
runner; FR21b and FR21c pass in both arms, which is what makes them controls,
and they assert WHICH PATH stopped the step rather than the fixture's row
count.


### 4b. The off-viewport region hint names regions by TAG, not identity — CLOSED (twice)
#26 built the region hint so a caller can recover an off-viewport target with
one scoped read instead of a scroll plus a full re-listing, and measured all 76
off-viewport steps recovering that way. It names each region by its TAG:

    form(ref_212): 8, section(ref_274): 36, article(ref_177): 6, main(ref_71): 4

**Measured live in eval 6.** An agent told to fill in a hotel search scoped to
`ref_212` — the only `form` on the page, and the task was "fill in a search
form". It is the **newsletter signup at the bottom of the page**. The actual
search widget is not a `<form>` at all; it is plain divs inside `section`. One
wasted call, and the agent said the hint "would have been decisive if it carried
the region's accessible name or its first heading" — `form "Путешествуйте
выгоднее!"` would have said instantly that it was the wrong one.

The collector already resolves accessible names and already finds the main
heading (#30's declared-rank rule), so the information exists.

**CLOSED in #80.** The hint now carries aria-label, aria-labelledby text or the
region's first heading, clipped with `markCut`, so the same line reads
`form "Путешествуйте выгоднее!"(ref_212): 8`. RG2b pins it and RG2c is the
control that a region declaring no identity is still listed rather than dropped.
Cost: the honest pairing is free on a corpus that lacks the shape and proven on
a fixture that has it — my first two attempts to price it measured nothing,
because the pages I priced it on never produce a per-region hint at all.

**REOPENED by eval 7, where TWO agents wasted a call on the same hint on the
same page.** The hotels search page has exactly one `<form>` and it is the
NEWSLETTER SIGNUP; the search widget is not a form at all. Both scoped to
`form(ref_212)` because a search widget is visually a form, and both got
`input[email] placeholder="example@mail.ru"` and `button "Подписаться"`.

**The #80 fix is working as designed and its sources are insufficient here**:
that form declares no `aria-label`, no `aria-labelledby`, and contains no
heading, so RG2c's control path fires and it falls back to the tag. The page
declares nothing the current rule reads.

**What it DOES declare is inside the region**: a submit button labelled
«Подписаться», and a placeholder naming an email. A form's submit button names
what the form DOES, which is exactly what separates a newsletter signup from a
search — and it is declared content, not a guess about layout.

**CLOSED.** A `<form>` that declares none of the three sources is now named by
its submit — HTML's own `type="submit"`, the same declaration #24's submit
picker reads, so no wordlist and no layout. Prefixed `submits: …` because it
names the ACTION rather than the region: `form "Подписаться"` would read as the
form's own title and it is not one.
**Priced with #80's own pairing, both arms on the same page load across 30
frozen sites: +0.026% chars, firing on 2 — `bootstrap_forms` and `chakra`,
which are exactly the pages where a form is worth naming.** Free where the shape
is absent, proven on the fixture that has it. RG2d fails pre-fix; RG2b and RG2c
pass in both arms, so the three declared sources and the
a-region-with-no-name-is-still-listed rule are untouched.

### 4c. A visible label not wired to its input is unreachable by `find` `OPEN`
Same eval-6 run. The page renders «Направление» two lines above the destination
field; the input's accessible name is EMPTY and its placeholder is «Город, отель
или аэропорт». So the one word the TASK ITSELF uses is unreachable by `find`,
which is the first query any reader would try.

This is the page's defect — an unlabelled input — and `find` behaving correctly:
it is a lexical matcher over resolved identities (#20), and there is no identity
to match. **What rescued the agent was find's own miss census**, which pushed it
to `query_elements("input")`. So the #39 census earned its keep on its first
live outing.

The open question is whether `near=` should have carried «Направление» here. It
is designed for exactly this (a HINT for unnamed fields) and did not appear.
**Measure before changing anything:** #37 tightened `near=` because it was
firing where it distinguished nothing, and loosening it back is the move that
needs a number, not an anecdote.

### 4d. `search_page`'s climb is a no-op against same-text wrappers `MEASURE FIRST`
#42 states the rule as a condition about SUFFICIENCY — climb whenever the
element's own text cannot supply the `context_chars` the caller asked for — and
the implementation applies it ONCE, because #43 measured multi-hop climbing
quoting whole lists and set the fallback to exactly one hop.

Against a chain of wrappers that all carry the same string, one hop is a no-op
and the condition is still unmet. **Measured live in eval 6**, on the grocery
cart widget, six levels up from the matched node:

    ref_603 div.label        innerText "Корзина"
    ref_601 span.v-btn__content         "Корзина"
    ref_598 button.v-btn                "Корзина"
    ref_597 div.v-badge__wrapper        "Корзина"
    ref_596 div.v-badge                 "Корзина"
    ref_595 div.menu-btn                "Корзина"   <- the count badge lives here

The agent asked for 120 context chars and got 7. It reported the answer as "one
DOM hop away"; it is six, which is why the climb firing correctly still helped
nobody. (The badge is `display:none` while the count is 0, so the same search on
an untouched page is correctly silent — the symptom only exists once the cart
has something in it.)

**The obvious fix re-opens #43.** "Keep climbing while the ancestor adds no new
text" walks a link through its sole-child wrapper straight into the LIST, which
is the aozora defect #43 was written to end.

**The candidate worth measuring** is the rule this codebase already has a
spelling for: `_inFieldWrapper` from #29 — climb while the ancestor still
corresponds to ONE control, stop at the first that holds a second. That is
exactly what separates the two cases: the badge is part of one widget, the
aozora siblings are separate records. Two things to settle before it ships:
the corpus cost of both halves (#41, #44), and that `_searchTextPage` is
injected standalone, so it needs a forced byte-identical copy with an OC7-style
tripwire rather than a sibling call (#30's C11 class).

### 4e. A hit on a SIBLING reads as "you missed", and the click works — CLOSED
The hit-test echo distinguishes "you hit the inside of your own target" (silent,
the normal case for any control with inner markup) from "something else is in
the way" (MISMATCH). It has no third case, and eval 7 found one.

On a rail seat map, both seat clicks returned:

    MISMATCH: you named ref_1381, but the renderer hit-tests an element with no
    ref of its own (nearest listed ancestor: ref_1378 <svg>) — something not in
    the current listing is on top at that point

**Both clicks landed.** The hit node is an SVG `<text>` label painted over the
seat, a SIBLING of the seat `<g>` rather than a descendant, so `_inChain` is
correctly false — and the event still bubbles to the common `<svg>` where the
handler is delegated. The agent: *"the message gives no way to separate 'this
still landed on your element' from 'this hit the wrong thing'. I nearly spent a
verification call."* What saved it was an unrelated signal, a badge count.

The message also asserts exactly two causes — "something is on top, or the
layout moved" — and this is a third. #33's class, in the echo.

**The shape of a fix, and why it is not a guess.** `h.chain` already carries the
HIT element's ancestor refs. Walking the NAMED ref's ancestors the same way and
intersecting gives a listed common ancestor as a FACT, so the echo can say "you
hit a sibling; both are inside ref_1378" instead of naming two causes neither of
which applies. It must NOT claim the click worked — whether a handler sits on
that ancestor is not knowable from geometry, though `__abClickBound` is a
declared signal that could narrow it.

**Compounding it (#23's open item, reported again):** both seat clicks printed
the identical coordinate, because acting by ref centres the target. Two
different seats, two identical coordinates, two MISMATCH warnings reads exactly
like clicking the same thing twice.

**CLOSED, and ADDITIVELY — the first version of the fix was wrong.** It replaced
MISMATCH with "a SIBLING, not something on top of you", which is FALSE for a
transparent veil — and a veil is also a sibling sharing a listed ancestor. Both
candidates overlap the click point or neither would have been hit, so geometry
cannot separate "a label painted inside the widget" from "a layer covering your
target"; telling them apart by relative AREA would be a threshold in a path that
reports facts. So the shared ancestor is STATED, both readings are named, and
neither is chosen (#33).
`_hitTestPage` now takes the named selector, resolves it and intersects the two
ancestor chains — the nearest ref on both is where the event bubbles either way.
X10c/X10d fail pre-fix; **X10e is the control that a hit with NO listed ancestor
in common gains no sibling clause**, which is the veil, still on the plain
MISMATCH branch. The fixture needed a new shape — two overlapping children of
one listed container — because the existing veil page has no common listed
ancestor and could not reach the branch.

### 4f. A run of identical siblings whose meaning is in undeclared text `MEASURED, NOT FIXABLE WITHOUT A GUESS`
Eval 7, a three-month calendar. `read_page` listed ~236 day cells; the three
month titles are bare `<div class="month-title">` — no `<h1>`–`<h6>`, no
`role=heading`, no `aria-label` — so they are not interactive, not entries, and
the container holding title + grid has ONE kept child subtree and is pruned by
#27's single-kept-child rule. The agent got `1:"1" 2:"2" 3:"3"…` and could not
tell November from January, and spent a call on `read_page(ref_id=…,
filter="all")` to recover the headings.

That call IS the designed recovery and it worked. What is not available is any
way to know in advance that it was needed.

**Reading the class name is the fix this project does not take** (#27, #28, and
the owner's brief). The page declares nothing about those three strings, which
puts this in the same class as #79's nine Mind2Web misses and eval 6's unlabeled
add-to-cart control: the measured price of "existence and structure are decided
only by declarations". Recorded so it is not re-derived as a bug.

What WOULD be defensible is the shape #26 used for data tables — the listing
names them and hands over their refs, because a `<table>` is not interactive and
has no row of its own. Generalising that to "a folded run preceded by text"
needs a threshold, which is the thing being avoided. Not built.

### 4g. `_truncate` returns more than `max_chars` — MEASURED, NOT FIXED `ACCEPTED`
Every return path in `_truncate` slices to `max_chars` and then APPENDS its
trailer, so the result runs over by the trailer's own length. Swept on a 190-row
listing across budgets from 300 to 3000: **55–83 chars over on committed code**,
and more once a trailer grows a clause.

#42 reserved room for exactly this in `get_page_text`, where the note was ~560
chars and was crowding out the body it explained. Here it is tens of characters
against a budget the caller chose, and the trailer is the thing that makes the
cut honest (#13: the payload is what must never go).

**An attempt is recorded because it failed in an instructive way.** Threading a
separate slice point through, so the note prints the caller's number while the
slice lands short of it, does not converge: the three return paths switch
between the legend-dropping fallback and the ordinary slice as the budget
shrinks, so the trailer's length jumps rather than settling. Three iterations
still left **88 of 386 swept budgets over**, and it broke T22. Reverted.

What shipped instead is that `read_page`'s own `max_chars` description now says
the bound is on the LISTING and the trailer is added past it, and T27b asserts
the overshoot stays bounded by the trailer rather than being unbounded. A
meaningful fix means building each path's note before its slice, which is a
restructure of the most heavily-tested function in the project and wants its own
pass rather than a mid-eval edit.

### 4h. `near=` named a DIFFERENT option than the row's own value — CLOSED (collector half)
Eval 7, on a payment-method radio group. `find("ОПЛАТИТЬ Банковская карта")`
returned:

```
ref_2380  [input]  [radio] value="yoomoney" near="Банковская карта"  under="Способ оплаты"
```

A **yoomoney** radio advertised as `near="Банковская карта"` — and the radio
that genuinely IS Банковская карта (`ref_2376`) **was not returned at all**,
though the query matches its label. Acting on the returned ref selects the wrong
payment method.

Two halves, and they live in different files:
- **The row is internally contradictory**, which is the collector's: `near=` is
  the nearest visible text and it picked the neighbouring option's label. #37
  already drops a `near=` shared by rows that have their own identity; a radio's
  `value=` is a WIRE KEY rather than a label (the same class #41 marked
  `(post-key)` for), so the "has its own identity" test does not fire here.
- **`find` ranked it confidently**, which is the scorer's. #27 made `near=`
  count as CONTENT coverage deliberately, and it fixed two failures pointing in
  opposite directions, so demoting it is not a free change.

**The collector half is CLOSED, and the measurement the entry asked for is the
one that decided it.** `near=` is the nearest VISIBLE text, which in a radio
group is routinely a NEIGHBOURING option's label. `submits=` (4m) is what the
member posts — written by the author, different per member by construction. So
when a checkbox/radio declares a submit value, the adjacency guess is dropped:
a declared per-member discriminator beats a guess at adjacency, which is #37's
own reasoning with a second way for a hint to fail to earn its place.
A member declaring NOTHING keeps the hint, because there it is the only thing
the listing can say (NRQ1c, and it passes in both arms).
**Priced across 30 frozen sites, both arms on the same page load: +0.000% —
byte-identical, so the shape does not occur there at all.** Free where it is
absent, proven on the fixture that has it: NRQ1 fails pre-fix and reproduces the
live row in English — `input[radio] submits="yoomoney" near="Bank card"`.

**`find`'s half is deliberately NOT touched.** #27 made `near=` count as CONTENT
coverage and that fixed two failures pointing in opposite directions; changing
it needs checking against F4/F15/F25/F29, which are the regressions #27 and #39
recorded when this scorer was last touched. With the collector half fixed, the
contradictory row no longer exists for the scorer to rank.

### 4i. A `(disabled)` submit names no blocker — MEASURED, DON'T BUILD
Eval 7: «ОФОРМИТЬ ЗАКАЗ» stayed `(disabled)` with every visible field filled.
The blocker was a required `(unselected)` combobox per passenger that only
materialises AFTER a passenger is chosen and had scrolled above the fold, so the
viewport-scoped listing never showed it. `query_elements("input:invalid,
[aria-invalid='true'], .error")` returned nothing — the disable is Vue-driven,
not HTML validation.

What cracked it was a scoped read, which is not viewport-limited, where the rows
read `(unselected)` with the legend already explaining them. So the information
was reachable in one call and the agent needed two to think of it.

`fill_form` already enumerates unfilled `(required)`/`(unselected)` fields in its
result when a submit fails (#4). **A standalone disabled button has no
equivalent path**, and that asymmetry is the whole item: the same question, asked
about the same page, answered in one place and not the other.

**THE ASYMMETRY IS REAL AND THE BINDING IT NEEDS DOES NOT EXIST.**
`tools/audit_disabled_gate.py`, 105 frozen live-captured sites, self-tested
first because the headline is a zero and a detector reporting zero is worth
nothing until it has been seen to fire:

| | |
|---|---|
| visible DISABLED buttons | **74** |
| of them a DECLARED submit (`type=submit`, or implicit submit in a `<form>`) | **0** |
| with a form owner — what `fill_form` binds to | **0** |
| with `aria-controls` | 8 |
| with `aria-describedby` | 1 |
| with NO declared association of any kind | **65** |
| required-and-empty fields corpus-wide | 9, on 7/105 sites |

**Porting `fill_form`'s scope rule ships a feature that fires zero times.** Its
scope is `btn.form`, and across 105 pages not one disabled button has one.

**And a note on the disabled buttons that DO occur would be wrong on every one
of them.** They are `«`, `‹`, `Previous`, `Today`, `Save`, `Code Generator`,
`Recents`, `Select framework` — pagination at a boundary, toolbar states with
nothing selected, premium-gated features. Nothing is blocking them and nothing
can unblock them, so "here is what is blocking this" is a false sentence 74
times out of 74. That is #15's always-on warning, measured rather than
predicted, and the generic version of the advice costs ~195 characters on the
~70% of pages that hold a disabled control (≈3.8% of a median listing, against
the 2.6% the detail legend was accepted at).

**The eval-7 page is outside what any of this could reach.** Its checkout is a
Vue widget with no `<form>`, so `el.form` is null and `type=submit` is absent —
the same answer `fill_form` gives there, which #4 already settled as the honest
one. HTML and ARIA define no other link between a button and the fields it
gates; `aria-controls` is the closest and on all 8 instances here it points at
the table a pager controls, not at a blocker.

**What the agent actually needed was already printed.** The off-viewport note
reports BOTH directions, the magnitude in viewport-heights, and the regions with
their refs — and a scoped read is not viewport-limited, which is exactly what
cracked it. The residual gap is a reasoning step (connect a disabled control to
the regions that note names), not a missing fact, and this project does not fix
reasoning steps by adding a sentence that is false on 74 of 74 measured cases.

**What would reopen it:** not another attribute — those were tested. A corpus of
real checkout flows, where the population is disabled SUBMITS rather than
disabled pagers, and where the 0/74 might not hold. #25's rule applies in full:
this ablation measures the code against the sample and cannot measure the
sample.

### 4j. The aria-hidden note promises refs `query_elements` cannot give — CLOSED
The listing's aria-hidden note sends callers to `query_elements` and says
verbatim *"it queries the RENDERED document rather than this listing, so it
returns aria-hidden elements and its refs act normally."*

**The second half is false for anything rendered since the last `read_page`.**
mmids are stamped by the COLLECTOR (#32), so a suggestion list, a just-opened
menu or a fresh row carries none. Measured live in eval 7: an agent followed
that note, typed a destination, queried the suggestion button that had just
appeared, and got `<button> "Дубай ОАЭ" class="opt active"` with no ref. It
spent a whole call running `read_page` purely to make the collector stamp, then
re-queried. Its words: *"for a suggestion list — i.e. anything that appears in
response to typing, which is the normal case — `query_elements` alone is a dead
end, and nothing in that note says so."*

**HALF CLOSED, server-side.** Both sibling renderers now say it, and both fire
on ANY ref-less row rather than only when every row lacks one — the mixed case
(one read has run, the new half has not been stamped) is the common shape and an
all-or-nothing guard was silent for it. C36/C36b, with C36c the control that a
fully-stamped result says nothing. `search_page` carried the all-or-nothing form
since #32 and had the same hole.

**The note itself still over-promises** and is in `background.js`, held under
eval 7's Amendment 2 (one build per arm). Two candidate fixes, neither free:
drop the "its refs act normally" clause, or have the query op stamp what it
returns — which makes a read tool mutate the page's mmid registry, and that is a
contract change wanting its own measurement.

### 4k. A small `max_chars` is the only way to say "collect, do not print" `OPEN`
Same run. The agent called `read_page(max_chars=300)` deliberately, purely to
trigger mmid stamping without paying for output, and got the `NOTHING could be
shown` branch — which is #34's message working exactly as designed, and reads as
an error for what was a successful use. There is no sanctioned way to ask the
collector to run without rendering a listing.

Related to 4j and probably resolved by the same decision: if `query_elements`
stamped, neither this nor 4j's extra call would exist.

### 4l. A stepper's +/- both took the quantity as their name — CLOSED
Eval 7, on a product page. After adding to the cart:

```
ref_1151 | button "1" (just appeared)
ref_1154 | button "1" (just appeared)
```

Minus and plus, both named `"1"` — the stepper's quantity VALUE adopted as the
accessible name of both buttons. **Clicking the wrong one at quantity 1 removes
the item**, so this cannot be guessed. The agent spent a call on
`query_elements(attributes=["class","aria-label","title"])`, which did not
settle it either (`class="qty-btn"` on both, no aria-label), and resolved it
only with a screenshot.

**The same control on the CART page lists perfectly**, which is what makes this
a defect rather than a limit:

```
ref_3687 | button "minus"  (name read off an icon-library class name, not an accessible name)
ref_3693 | button "plus"
```

So the collector names these when an icon-library class is present, and on the
product page it instead ADOPTED A SIBLING'S TEXT. **A name that is confidently
wrong is worse than `(unlabeled-icon)`** — the latter sends the reader straight
to a screenshot with no detour through a dead-end attribute query.

This is the "two rows that mean opposite things, printed identically" class
named in eval 6, and **no presence-based ruler can see it**: both elements are
present, listed, named and clickable. `measure_findability` would score them a
hit.

**CLOSED.** The cause is `synthLabel`'s CARD-PATTERN branch, written for a card
whose caption sits OUTSIDE its one anchor — it adopts a PARENT's text for a
label-less control that covers >=30% of it. A stepper is three controls in one
tight parent, so both buttons took the same string. The guard is #29's
`_inFieldWrapper` rule one layer over: **a parent holding a SECOND control is a
GROUP, and its text labels the group**. Decided from the declared control set,
not from size or class names.
Priced on 30 frozen sites, both arms on the same page load: **0 names lost,
+0.00% chars**, 1 listing differing and that one a replay #16 names as
non-deterministic. Measured-harmless, with the value evidence in QS1 and the
live run. QS1 fails pre-fix with the live symptom exactly (`button "1"` twice);
**QS1b is the control that the card pattern still works where it was written
for**, and my first fixture missed the branch entirely at 23% area coverage —
the vacuous-fixture problem, eighth instance.

### 4m. A checkbox's `value=` reads as its state — CLOSED
Same run: `ref_3566 | input[checkbox] name="Выбрать все" value="true"` while
`query_elements(attributes=["checked"])` says `checked="false"` on all four.

The legend defines `value=` as CURRENT CONTENTS, so `value="true"` on a checkbox
reads exactly like "this is ticked". It is the literal HTML `value` attribute —
what the box POSTS when checked, which is the wire-key class #41 marks
`(post-key)` for, not its state. The row's state is carried correctly by the
presence or absence of `(checked)`; the `value=` beside it contradicts that.

#23 fixed the sibling case (`value="on"`, the DOM default never written by the
page). This is a page that genuinely writes `value="true"`, so suppressing it
outright would drop authored content — the fix is to put it in a slot that does
not mean state.

**CLOSED.** It moves to its own key: `submits="true"`, with a legend line that
says in as many words that it is NOT state and that the `(checked)` flag is.
Printing it is still worth doing — `OPEN.md` 4h is a radio group where the value
is the only honest identity — so this keeps the information and changes what the
key MEANS.
CB1/CB1b/CB1d fail pre-fix and reproduce the live symptom exactly
(`value="true"` on an unchecked box). **CB1c is the control and passes in both
arms**: a text input's `value=` IS its contents and is untouched. My first
version of that control also asserted the `submits=` count, which is zero
pre-fix — so it failed ablated and was not a control at all; that half is CB1d.

### 4n. A FILTERED miss reads exactly like a silent page — CLOSED
**Found on the OTHER arm in eval 7, and ours has it in two tools.** Worth
recording how it arrived: the eval's value is not only the comparison. An agent
driving the competing toolset reported a defect in its network reader, and
checking ours against the description found the same shape.

```
extension/background.js:
  "No network requests recorded for this tab" + (pat ? ` matching "${pat}"` : "") + "."
  "No console messages matched."
```

Neither states how many requests or messages ARE held. So *"your filter matched
nothing"* and *"this page did nothing"* render almost identically, and the
second is a far stronger claim than the buffer can support.

**What it cost on the other arm, and would cost on ours.** The agent filtered on
`lab-reports` to check a download, got `No requests matching "lab-reports"`,
concluded nothing had fired — and four `POST /event/add` requests confirming the
action were sitting in the same buffer. It then **clicked the download link a
second time to "make it fire"**, on an app whose entire purpose is recording
what you do. A real side effect, caused purely by a message that could not
distinguish its two meanings.

**The fix is one number and it is already in hand**: `total` is computed before
the filter is applied in both branches, so
`No requests matching "lab-reports" (4 recorded for this tab)` costs nothing.
`read_console_messages` is worse — it does not say whether a pattern was even
in play.

This is #16's rule as an OUTPUT contract rather than a measurement one: an
absence is only evidence when the thing doing the looking says what it looked
at. `search_page` already carries that discipline (#39's settled-state note);
these two did not.

**CLOSED.** Both now name the unfiltered total and say the pattern excluded
them, and point at re-running without it. NF1 fails pre-fix; **NF2 is the
control that a genuinely empty buffer claims nothing about a filter**, without
which the note would fire everywhere and mean nothing (#15).

### 4o. A navigate gets the COMMIT wait, not the CONTENT wait — CLOSED
`browser_batch` waits twice and for different things: `_settle` after a
navigation (Chrome's own `onDOMContentLoaded`, #51) and `_quiet` after an ACTION
(mutations stopping, #51). The second is gated on a step having ACTED, and a
`navigate` is not an act by that rule — so `click -> read_page` settles and
`navigate -> read_page` does not.

**On a client-rendered app, commit is not content.** Measured live in eval 7:
an opening `[tabs_create_mcp, navigate, read_page]` returned a listing holding
only the 7 nav buttons, with page text reading `debug_msg: Going to first step`
— the Vue router had not run yet — and the whole main content absent. One
wasted call. The agent put the diagnosis exactly: *"the machinery exists and
works well; it just doesn't fire after `navigate` … For an SPA the first paint
happens strictly after the point `navigate` returns."*

**CLOSED.** `_quiet`'s gate is now `_acted or _navigated`, and `_navigated` is
read off the SAME `_settle` reply that already decides the document wait — asked
rather than predicted (#51), so it costs no extra round trip and it catches a
CLICK that navigated, which a step's own input cannot reveal.
Free where it is not wanted: `await_quiet` returns immediately on a settled page
and prints nothing, so a server-rendered navigation pays one bridge op.
B18 fails pre-fix; **B18b is the control that an observation after an
observation still waits for nothing**, without which "wait on everything" would
satisfy B18 while taxing every batch (#38).

### 4p. A download click has no page-side consequence, and nothing says so — CLOSED
Eval 7, the files task. After clicking a `download` anchor: URL unchanged, DOM
re-read byte-identical, click output `landed at (1214,350)` — which confirms
the CLICK, not the DOWNLOAD. **The default verification instinct, re-reading the
page, is structurally incapable of confirming this action**, and nothing in the
click result or the anchor's row hints at what would be.

Both arms met it. Ours went to a shell `ls` and found the file;
`read_network_requests` is the in-tooling answer and nothing points at it.

**CLOSED.** A click whose target declares `download` now says that the URL, the
DOM and a re-read are identical whether or not the file arrived, and names
`read_network_requests` as the check that can see it. Declared attribute, no
guess — and resolved up to the nearest `<a>`, because the ref is routinely a
span inside the link. It rides the AGREEING branch, which is otherwise silent,
because silence is exactly the problem here.
X10f fails pre-fix; **X11b is the control that an ordinary agreeing click still
says nothing**, so this did not become per-click noise.

### 4q. `search_page` reports the TEXT's ref and no route to the ACTION — CLOSED
The last run of eval 7, and the only overhead call in an 8-call task.

`search_page("оливк")` returned `<div ref_1285 …> Оливки Доставка, без косточки
| 330 г | 229 ₽`. The agent needed the «Добавить» button, `ref_1291` — a
SIBLING, one level up and over. Neither route reaches it:
`read_page(ref_id="ref_1285")` scopes to the title div's own subtree, which
holds no button; and nothing names the parent card.

**What makes this fixable rather than inherent: `search_page` already knows the
record.** Its own context string IS the card, joined with the declared-boundary
marker — it climbed there to build it (#47's `_climbTo`) and then reported only
the leaf's ref. The agent put it exactly: *"it climbed to the card to build that
string and then reported only the leaf's ref. Naming the record's ref alongside
the match ref would have let me go straight to `read_page(ref_id=<card>)`."*

Attribution must not change — #32's rule is that the hit belongs to the element
whose own text first contains the match, or an ancestor reports every child's
hit. This is an ADDITIONAL field, not a replacement.

**CLOSED.** The climb already STANDS ON the record when it re-slices the
context, so `recordRef`/`recordTag` are stamped there — a fact in hand, not a
second walk — and the row prints `[record: ref_N <article>]` only when it
differs from the match's own element. The hit's own node is kept on the pending
object as `self`, because the first version compared via `hits.indexOf` which is
O(n) per hit per ancestor.
RC1 fails pre-fix; **RC1b is the control that a match whose own element already
supplies the context names none**. Two wrong versions of that control first: a
match that FILLS its element has nothing either side, so `_wants` asks for more
and the one-hop fallback fires — what stops the climb is real text on BOTH
sides. And both new calls passed POSITIONAL arguments to
`_searchTextPage(pattern, opts)`, so every option was ignored and
`contextChars` silently took its 150 default. The suite's own helper gets this
right; hand-written calls did not.

### 4r. CT1c's advice cannot answer the page it was written for — CLOSED
**This lands on advice added THIS SESSION**, in response to eval 6, and eval 7
showed it does not cover the case. The cap notice says:

> When many rows share ONE label, neither of those separates them… What
> distinguishes them is an ATTRIBUTE — `query_elements(selector,
> attributes=["href","value","title"])`

On a grocery catalogue every card has an identically-named «Добавить» and **none
of them carries a distinguishing attribute** — no href, no value, no title, and
no class name to build a selector from. What distinguishes them is **DOM
CONTAINMENT**: which card the button sits in. None of the three tools the notice
names expresses containment, and the one that does — `read_page(ref_id=…)` —
needs the card's ref, which is exactly 4q's missing piece.

So the advice pointed at `query_elements` when the real answer was "read the
listing and infer from ref ordering", which the agent did and flagged as
inference rather than fact: *"on a page where every card has an identically-named
«Добавить», a wrong inference silently adds the wrong product."*

**The honest reading of eval 6 → eval 7:** CT1c was right about the eval-6 page
(18 download links separated by `href`) and is incomplete as a general rule.
Containment is the other half and it belongs in the same notice, which means 4q
first.

**CLOSED, now that 4q supplies the missing ref.** `search_page` reports the
RECORD's ref beside the match, standing on the card it had already climbed to in
order to build the context string — so the recovery is two facts the tools
already produce rather than a new capability. The notice now carries both
halves: an ATTRIBUTE when one exists (the eval-6 answer, untouched), and
otherwise WHICH RECORD each row sits in, with the route named — `search_page`
the record's own text, then `read_page(ref_id=…)` on the card it names. It also
says plainly not to infer the pairing from ref ORDER, which is what the eval-7
agent did and flagged itself: *"a wrong inference silently adds the wrong
product."*

**Priced across 40 frozen sites, both arms on the same page load: +0.745%
corpus-wide, worst capped site +3.112%, and it prints on only 6/40 — the pages
where the cap has ALREADY dropped ~51 entries.** A first draft restructured the
sentence and cost +1.085% / +4.488%; rewriting it as a pure APPEND to the
existing one got both figures down with no loss. Cheap for the failure it
prevents, which is a wrong ACTION rather than a wasted call.
CT1d/CT1e fail pre-fix; **CT1c passes in both arms**, which is what proves the
eval-6 half was not traded away for the eval-7 one.

### 4s. The cheaper format drops the relationship that disambiguates — CLOSED
Same run. The agent chose `format="flat"` to reduce size and then needed the
containment the tree states by indentation:

> `format="tree"` would have nested it unambiguously; I had chosen
> `format="flat"` *to reduce size*, so the cheaper format is the one that drops
> exactly the containment relationship that disambiguates identical buttons.

`format`'s description sells flat on size and on "you only need a single named
control". Here the agent needed a single control whose name was shared by ~40
others, and nothing in the parameter's own text names that trade. #27 shipped
the tree as default for exactly this reason ("a flat list cannot express a
row"); the description of the escape hatch never caught up.

**CLOSED.** The condition was the wrong one: "you only need a single named
control" was SATISFIED on that page and the advice was still wrong. It now reads
*"worth passing when the control you want has a name that is UNIQUE on the
page"*, and names what flat drops — when several rows share one label, flat
cannot say which record each belongs to, and that containment is the only thing
telling them apart. A trade a parameter does not name is one the caller cannot
weigh. C20e pins it and fails pre-fix with the old sentence quoted.

### 5. SPA readiness, the remaining half `OPEN`
The mutation-recency signal (#70) separates "still building" from "ready but
chatty" — measured 9–18ms vs 907–3514ms with no overlap. Still open:
- ~~**scoped attribution.**~~ **BUILT (#76).** A scoped read now scopes the
  readiness answer to the same subtree: measured at `since=4013ms / 0 structural`
  for the table a caller scoped to, at the instant the document read
  `since=48ms / 110 structural`. It also covers a case the kind-split provably
  does NOT — a ticker updating via `textContent` arrives as `childList`, not as
  an attribute write, so `@style` damping never saw it (measured: 25 structural,
  0 text, for a clock). **Residual: landmark attribution for an UNSCOPED read**,
  which is a different problem (which landmark owns a record, and how to print
  several), tracked in `READINESS.md`'s own list.
- **a per-ref primitive.** Playwright's actionability has one — *same bounding
  box for two consecutive animation frames* — and it is the cheapest readiness
  check anywhere. We have nothing equivalent.
- **nobody has measured whether telling the model helps.** We and browser-use
  are the only two projects that expose a settling signal to the model, and
  there is no published evidence it improves anything. A cheap A/B with
  `bench_turns`.

### 6. A CSS transition is not waited for `OPEN`
#51's settle covers **navigations**. A `browser_batch` of four observations after
a click all read the page before a ~300ms Bootstrap fade and came back empty on
a click that had worked. A fixed transition duration would be a chosen number;
the mutation signal from #70 may answer it properly, and that has not been
tried.

### 6b. A flow replayed against a LOCALISED app names no cause `OPEN`
The descriptor's identity rung IS the accessible name, so changing the app's
language invalidates every step at once. The playground already ships a `ja`
chaos flag whose own comment says "the whole descriptor design rests on the
accessible name" — and the failure surface had no entry for it.

Measured: a target recorded as `name='Sign in'`, replayed against a Japanese
render, reports *"no element on the page matches this step's target:
tag='button' name='Sign in'"* and nothing else, while the SAME failure at a
different viewport width appends *"The window is also a different WIDTH…"*.
The page declares the fact (`<html lang>`); the recorded half is missing, and
`Flow` has no `lang` field. `viewport` is populated by `mcp_server` at stop
time, so closing this needs a writer there as well as a reader in the runner —
both halves or neither (rule 14).

### 7. Page-level scans and the iframe boundary `MEASURE FIRST`
**HALF THIS ITEM WAS WRONG and is corrected (#78).** Same-origin frames ARE
reached: `dialogOpen` queries `_allComposed`, which iterates `mmidReg`, and the
collection walk stamps mmids across same-origin frame boundaries; `_readinessPage`
already merges same-origin frames (#70/R19). The real decomposition is:
- **cross-origin frames are invisible to all three page-level scans.**
  `collectCrossFrames` runs AFTER the banner is built and merely appends rows, so
  no cross-frame dialog can ever raise it. Nine constructed fixtures (two ports,
  so cross-origin is real): a cross-origin CMP as a full-page fixed overlay gets
  NO banner, **0 rows flagged `(occluded/blocked)`**, and no dialog text — while
  the same-origin version raises the banner and names what it omitted.
- **`section=dialog` is on 0 rows in all 9 fixtures**, including the three where
  the banner correctly fires: an in-frame dialog's controls resolve to
  `section=iframe`. Extends #23's open `section=` item across the boundary.
- ~~same-origin geometry~~ **FIXED (#78, MV4).**

**FREQUENCY IS NOT ANSWERABLE ON THIS CORPUS, and the zero is verified real.**
42/96 sites have a child frame (128 frames), 17/96 have a RENDERED one, and
**0 of 128 declare any page-level trigger**. Probe firing confirmed by a control
over the same pages' TOP documents: 91 dialog nodes, 15 visible, 7 `aria-modal`,
6/96 raising the banner. The corpus cannot hold the shape because **HARs are
captured after consent**, 21/128 frames no longer replay, and the one CMP-shaped
frame present declares its `role=dialog aria-modal` wrapper in the TOP document.

**THE COST ASSUMPTION IN THIS ITEM WAS ALSO WRONG.** `collectCrossFrames`
already injects the collector into **27 of 33 rendered frames (81.8%)** on every
unscoped string read, so the per-frame round trip is ALREADY PAID — it just calls
the structured arm (no modal verdict) and appends after the banner. Per-frame
injection is median 14ms against a 66ms top-level collect. The "free"
same-origin-only variant reaches **12/33 (36.4%)** and misses exactly where CMPs
live.

**Do not build on this evidence** — #26's rule needs both halves and the benefit
half is unmeasured. What makes it answerable: re-freeze a corpus slice with
cookies cleared so the CMP shape exists, or a live pass. If it is ever built, the
design the cost data points at is zero-round-trip: have the existing per-frame
call return each frame's verdict and feed it back before the banner is built.
Probe: `tools/audit_frames.py` (`--fixtures` serves the 9 shapes from two ports).

### 8. Coordinate trust on canvas-dominated pages `ACCEPTED`
On OpenStreetMap the same ref reported clicks 1,097px apart, and a missed click
hits the map, so there is no symptom. Refs re-measure and are safe; the printed
coordinate is not.

### 9. Three unreproducible 30s+ stalls `OPEN`
Every page-injecting op hangs together while `get_url`/`sw_info`/`navigate`
answer in milliseconds — a blocked page main thread rather than a dead
extension; navigating recovers it. Not reproducible across four attempts. The
bridge's timeout ring (#50) now gives the next sighting its evidence. **Cannot
be fixed by guessing at it.**

---

## Tier 3 — measurement debts

### 10. Which Mind2Web positive we score against `MEASURE FIRST`
The headline itself was audited in #73 and **stands** (~96%, reproduced three
ways, zero label defects across 186 actions). What remains is upstream of it:
`fetch_mind2web.py` keeps only **`pos_candidates[0]`**, and the original ~590MB
shards were not retained. If Mind2Web marks several nodes positive per action,
our ruler uses one of them and may be stricter or looser than MindAct's.

**This is the largest unaudited choice in the measurement spine** and it sits
under every number derived from it. Closing it means re-downloading from
HuggingFace.

**CLOSED — the three small debts #73 left.** The false comment is gone, the
snapshot is repaired before it is rendered (`tools/_m2w_ruler.py`), and the
ancestor credit path carries the same area bound as the descendant path. One
denominator now, all 186 actions: **177/186 = 95.2%**, exact 161/186 = 86.6%.
`--no-repair` reproduces the pre-#73 arm (166/173 = 96.0% of the targets that
resolved) so both figures stay obtainable from the tool rather than from memory.
Three things #73 got wrong, each found by running rather than by arithmetic:

- the repair "fixes the ikea credit for free" is true only of the FAITHFUL
  repair (every non-void self-closed tag), not of the RAWTEXT-only one that
  yields the 96.2% #73 headlines — so the two sentences in its closing
  paragraph cannot both hold;
- "mirroring the cap gives 165/173 = 95.4%" is **166/173 = 96.0%**: refusing an
  ancestor credit is not losing the row, and that one falls through to the
  target's own `<input>`, which is sound by bubbling. **The bound costs zero
  recall on either arm** and removes the one credit #73 called false;
- the minimal repair also leaves two further ancestor credits standing
  (sixflags, underarmour) whose "wrapping anchor" the raw bytes show is a
  self-closed `<a … bounding_box_rect="-1,-1,-1,-1"/>` — empty and rendering
  nothing in the original page.

The faithful repair was chosen on a signal independent of recall: it is the only
arm with **zero cloned nodes** (the unrepaired parse re-creates unclosed
formatting elements, emitting several DOM nodes under one `backend_node_id` on
**137 of 186 samples**, up to 2.48×), and it never recovers fewer distinct ids
than the other arms. Residue, stated: a median 99.8% of each snapshot's ids
parse, worst 43.4%, because Mind2Web nests a frame's whole document inside the
`<iframe>` element. No labelled target is among them.

### 11. No task-success measurement for our own ladder — A ROUTE EXISTS `MEASURE FIRST`
`detail` and `format` are priced on recall and tokens, never on end-to-end
success with a strong model.

**"The literature disagrees with itself" was wrong and is withdrawn (#78).**
Verified at source: EconWebArena's −10.2pp arm is **o4-mini**, and its 36.7%
figure is labelled `- use_ax_tree + use_html`, i.e. raw HTML *replacing* the
AXTree. A small reasoning model degrading on raw HTML is exactly what
[arXiv:2604.01535](https://arxiv.org/abs/2604.01535) predicts. Both support ONE
capability-dependent model, and 2604.01535 raises the format confound itself and
controls it — the effect survives, and is *larger* under indentation (+20.9),
which is our format.

**THE ROUTE: WebPageBench ([arXiv:2609.35026](https://arxiv.org/abs/2609.35026),
Apache-2.0).** Verified from the released artefact rather than the paper
(`tools/audit_webpagebench.py` exits nonzero if any claim fails and self-tests
against three planted violations): 152 tasks / 65 canonical + 87 variants, 6
sites, 19 event types, 521 conditions, all exact; **no judge model** — `check()`
imports only `requests/os/json/re/datetime` and the oracle is a semantic event
emitted by business logic AFTER the state mutation, so it cannot see how the
agent acted or what it was shown; and the control swap keeps prompt AND success
conditions **byte-identical on 87/87**. Design in `docs/WEBPAGEBENCH.md`.

**Caveats that must travel with any number from it.** It is a **v1 preprint, 5
authors, no venue, not peer reviewed**. It is a **Russian-language benchmark** —
152/152 prompts are Cyrillic, which no description of it mentioned. The sites are
**synthetic**, which is the real missing leg; it is softened but not removed by
the fact that our only out-of-sample number today comes from stripped static
snapshots with no CSS and no scripts. Per-step element ground truth is **absent**
(end-of-task only), so this measures SUCCESS, not element recall. Hotels is 30%
of the set, so leave-one-site-out is mandatory.

**Build M-B first even though M-A is the question as asked**, because it needs
one arm instead of two: the same task re-rendered through a different date
picker or combobox, with identical success conditions, which is a direct test of
"works on framework-heavy SPAs without site-specific code". **The benchmark
ships its own negative control** — 12 `theme_dark` variants change colour only,
so a structural representation must score identically on them; if dark theme
moves the number, the instrument is wrong before any result is believed.

**The confound to design out:** our surface has escape hatches. An agent that
reaches the state via `javascript_tool` or by typing a URL measures Claude's
ingenuity, not the listing. Pin the toolset and report the fallback rate beside
every number, as #27 pinned `filter="interactive"`.

**THE SITE IS UP AND BOTH UNVERIFIED ITEMS ARE NOW CHECKED (#79).** The oracle
fires end to end (`Added event: event_name=state_changed`, `POST /event/add
200`, from a plain page load). The `href` prediction was HALF WRONG and it
narrows the measurement: hrefs exist, so Mind2Web's 0-of-40 collapse does not
reproduce, but they are distributed INVERSELY to aria by domain — books and shop
have **0 anchors and 37–43 aria-labels**, hotels and rail have **12–18 anchors
and 1–3 aria-labels**. So the `detail` ladder is measurable on at most 2 of 6
domains, which is #73's Mind2Web finding reappearing in the benchmark chosen to
escape it. `format` is unaffected.

**FIRST RESULT, and it is the instrument check rather than one of the three
measurements: 12/12 theme pairs, 0 changed lines, same-arm floor 0**
(`tools/measure_wpb_invariance.py`). The listing is byte-identical under a
colour-only change on every pair across all six domains. Narrow and stated
narrowly — it establishes that the representation does not read COLOUR, not
invariance to the other eight control keys, which is M-B. The 0 floor is a
second result: these pages render deterministically, so later measurements have
no drift to subtract.

### 12. Sufficiency: the TEXT half is now MEASURED `OPEN`
The CONTROL half was already closed: **`DS | reachable` = 0.933**, LOSO
0.921–0.951, both negative controls passing, the accessible name carrying
51.7pp and the tree's ancestry path 11.2pp.

**THE TEXT HALF IS NOW MEASURED** (`tools/measure_text_flows.py`,
`SUFFICIENCY.md` §10). It is the half the source paper ranks FIRST (30.5 / 59.5
coverage drop when ablated, against 4.8–13.6 for any control type), and it was
unmeasured because a static page load cannot tell "the text surface failed to
carry it" from "the value did not exist yet". The route through the flow
recorder — replay to the step before the answer, then ask — closes that, and
`run_flow(stop_after=N)` became usable over the wire only this session.

| | live corpus |
|---|---|
| required values scored | **1,133** (985 prose, 148 table rows) |
| TEXT-DEPENDENT (controls-only listing does not carry them) | 1,047 (0.924) |
| **TS — carried by SOME text surface** | **1,047 / 1,047 = 1.000** |
| lost by every arm | **0** |

Per arm over the 1,047: `read_page(filter="all")` 0.983 · `search_page` 0.841 ·
`query_elements` 0.764 · `get_page_text` 0.761 — **and `get_page_text` at a
raised budget 1.000.** Every shortfall at default settings is the caller's
BUDGET and nothing else: 250 values missed at the 30k default are carried at
250k, **0 missed at both**, and the tool says so (`body truncated at 27225 of
62148 chars … spent as 27225 body + 332 readiness banner + 1834 outline`).

Drift floor **0.00%** on all seven verdict fields over two replicates, both
corpora. Live states come from the 8 `ev-*` recordings made by agents in
#63/#64 who were told nothing about any text measurement, plus todomvc — which
is the answer to "you chose the states". Stopping happens at EVERY step index,
deduped by content hash, because choosing the stop point is choosing the sample.
"Text-only" is measured per item as absence from `read_page(filter="interactive")`,
not asserted.

**WHAT KEEPS IT OPEN, and the first is the big one:**
1. **Not task-weighted.** Items are everything the page renders, a superset of
   what a task needs. Same bound item 2 accepts for DS, and the larger gap.
2. **Association is measured and is NOT 1.000.** Ordered-correctly in
   `read_page(all)` 139/148 = 0.939; the scoped aligned renderer 129/148 =
   0.872. The table half of the paper's "Text" row lives here, and presence does
   not measure it.
3. **The discovery path is narrower than the tool.** The data-table hint names
   the first 6 of jawiki's **44** tables, and it is the only route to the
   aligned renderer, which scores 0.885 once reached.
4. **20 live states, one page a fifth of them**, and 1 in 5 replays lost to five
   weeks of site drift.

**FOUR PROBE BUGS, THREE OF THEM DAMNING THE SYSTEM — LOST went 55 → 34 → 0 and
every step was the ruler**, which is this project's most repeated lesson landing
on its newest measurement. (a) `search_page` misses were detected with
`startswith("No match")` and the miss path PREPENDS the readiness note (#39), so
every miss read as a hit — the nonce control caught it on its first run. (b) A
table row had to be recovered on ONE LINE, and 44 of the 54 rows scored LOST had
a cell whose own text spans lines: unrecoverable by construction. (c) The
data-table hint regex anchored on `page:` while the hint reads `…on this page,
first 6 by document order:`, so the scoped arm was EMPTY and #26's renderer
scored 0 on the only state with real tables. (d) `innerText || textContent` in
the sweep invented values Chrome does not paint (#37).

### 13. The browser-use A/B measures a path that is no longer theirs `RETIRE THE FRAMING`
The 84.5%-junk figure (#33) was measured against their `ClickableElementDetector`.
**Confirmed by reading their current source (#78): the AX-tree path is now the
DEFAULT** — their README documents `mode='ultrafast'` acting on accessibility-tree
ids as the default on `bu-fast`, and `bu-fast` is their stated default. So this is
past "going stale": the comparison describes code that is no longer the thing it
names, and **re-running it would measure the same obsolete path again.**

The CONCLUSION is unaffected and still earned — we did not import their admission
rules, and the measurement of why is in #33. What must stop is the FRAMING "we
are more disciplined than browser-use about existence", which is now a claim
about a path they do not take.

**One thing from their current source is worth more than the re-run would be:**
they split opacity BY PURPOSE, with a reason on each side — `checkOpacity: true`
for the text surface, because "the AX tree keeps opacity:0 text (pre-rendered
success banners), which agents then report as success", and OFF for action-target
validation, because "custom-styled widgets often keep an opacity-0 native select
underneath". That is the distinction item 14 was reaching for, and our own
measurement found **0 of 434 sampled opacity:0 strings matching success/error
vocabulary** — so their stated hazard has zero instances on our corpus while
their counter-case (the hidden native control) is exactly what our
`_declaredCtl` exemption already rescues.

### 15. What our 31 tool schemas cost at session start `MEASURE FIRST`
Playwright MCP's own README now steers people toward CLI+skills over MCP on
token grounds. That is Microsoft's assertion with no published measurement, and
#38 says turns dominate tokens — but we have never measured our own schema
prefill.

---

## Settled — do not re-open without new evidence

- **Off-viewport admission.** +6.9pp first-read reachability for +18.7% tokens,
  **70% of the spend on tasks that gain nothing**, and the waste fraction does
  not move under two narrower predicates (#44). Three independent 2026 results
  now agree the problem is not that the model cannot see off-viewport content
  but that it does not execute the reveal — IGG measures **+3.1pp for telling
  the agent vs +48pp for doing it for it**, which is the sharpest argument for
  the region hint and against "scroll down".
- **browser-use's admission rules** — 84.5% of the gap is `cursor-pointer` and a
  10–50px icon rule; their own samples include a Hacker News rank number.
- **The Chrome AX tree** — 7.15× tokens for 4pp recall, and needs an attach that
  #12 proves gets refused on password-manager pages.
- **`find` for goal→element** — 0% with a human's task phrasing. That is
  semantic inference, not retrieval.
- **`id` / `data-testid` as a descriptor rung** — 6.8% / 2.5% coverage, perfect
  where present. Reopens only with a corpus of the internal apps this feature
  actually runs against.
- **Self-healing locators.** Unanimity across independent models is a valid
  signal for *which surviving element is this* and **actively anti-correlated**
  for *does it still exist*: 34/34 unanimous verdicts on deleted elements were
  **false heals**, and growing the model pool 3→7 did not reduce it. Keep the
  absence test structurally separate from the identity test. Never let a
  fallback rung answer "it's gone".
- **MHTML for corpus freezing** — 0% element retention.
