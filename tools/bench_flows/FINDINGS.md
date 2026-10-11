# Defect classes found by the flow generality eval

Each is recorded as it was found and NOT fixed mid-eval — changing the
instrument while it runs is what invalidates a result. Fixes come after the
eighth app.

---

## D1 — `query_elements(attributes=[...])` reads the ATTRIBUTE, except for two names

**Found on:** app 1, httpbin form. Reported by the recording agent, confirmed
in the source before being believed.

`query_elements('input[name="custname"]', attributes=["value"])` on a field
holding typed text returns `<input ref_6> (no text)` — nothing where the value
should be. The cause is one line:

```js
let v = (name === 'href' || name === 'src') && el[name] != null ? el[name] : _attr;
```

Only `href` and `src` fall back to the DOM property. A typed value is a
property; the page never sets a `value` *attribute*, so `getAttribute` returns
null and the field prints nothing. It works for a radio and a checkbox, where
`value="medium"` really is an authored attribute — **so the tool answers for
some controls and not others, with nothing distinguishing "has no value" from
"I only looked at the attribute".** That is #18's asymmetry (two rules
disagreeing about one concept) and #21's one-concept-two-spellings together,
and the comment block directly beneath that line shows a RELATED silence —
present-and-empty vs absent, for boolean attributes — already found and fixed
once without anyone noticing this one.

**The consequence is worse than the missing value, and the artefact shows it.**
The agent's intended confirmation became a *passing* assertion that cannot
fail. `query_elements` answered `1 element(s) match 'input[name="custname"]'`,
so the recorder stored `count: 1` — true whether or not the typing worked. The
flow replays green with the field empty.

**And #57's witness check could not catch it**, correctly: it compares a check
against its own value BEFORE the step, and this selector had no prior value, so
there was no claim to make (FW3's rule). It catches "already true before the
step", not "true regardless of the step".

**Underneath both:** there is no observation tool that can assert a typed text
field's contents. `search_page` cannot (an input's value is not rendered text),
`query_elements` cannot (this defect), and `read_page` is not one of the two
tools the recorder turns into a postcondition. On this form the typed text is
verifiable only AFTER submit, from the echoed JSON — so a regression that
silently failed to type would be caught at the end of the flow, not at the step
that typed.

---

## D2 — a `search_page` postcondition cannot follow a variable it quotes inside a longer string

**Found on:** app 1, while falsifying the flow deliberately.

`run_flow(vars={"customer_name": "Grace Hopper"})` typed Grace Hopper and then
asserted `search_page('"custname": "Ada Lovelace"')`, which found 0 and failed
the run. #54 substitutes a variable into an expectation by EXACT EQUALITY
only, and recorded that this is the cost: *"`search_page("Created atlas-svc")`
keeps the literal and still needs a re-record."*

So this is a KNOWN limitation rather than a new defect — but it is worth the
entry, because the FIRST app of the eval hit it without trying, which is
evidence the documented cost is a common case rather than an edge one.

It also demonstrates the flow is genuinely falsifiable overall: the end-to-end
submit assertion caught a changed input even though the per-typing-step
assertions could not.

---

## D3 — the settle races the navigation's own ANNOUNCEMENT, and the recorder bakes the stale read in

**Found on:** app 2, arXiv. The single most consequential finding so far,
because it does not merely confuse a read — it writes a wrong assertion into
the flow file, and that flow then fails on every replay for ever.

In the batch `[click(Search), get_url, search_page]` the agent saw the settle
fire before step 2 but NOT before step 1. Verified in the source rather than
accepted: `_settle` IS asked before every step from `i > 0`, so it was asked
before `get_url` and answered **idle**. `get_url` itself, one bridge round trip
(~3ms) later, reported `A navigation to … is IN FLIGHT (pending)`.

So the settle asked **before the browser had announced the navigation the click
caused.** #51 is deliberately built to ASK rather than predict — "whether a
click navigates is not in its input" — and this is the cost of that choice: the
announcement (`onBeforeNavigate`) can land in the gap between the probe and the
step it protects. Those are two separate ops over one socket; there is no way
to make them atomic.

**The consequence is in the artefact.** The recorder folds observations into
the preceding action's assertions and keeps the FIRST of each kind, so step 4
recorded `url: https://arxiv.org/search/advanced` — the page being REPLACED —
rather than the results url the agent re-read a moment later. The flow now
fails deterministically on replay (27s and 28s, same message both times) with
`url is '…?advanced=&terms-0-term=quantum+computing…', recorded
'https://arxiv.org/search/advanced'`. The assertion is wrong, not the app.

Two defects, and they should be fixed separately:

1. **The recorder keeps the FIRST same-kind observation after an action.** The
   LAST is strictly better evidence: later means more settled, and anything
   before the next action still belongs to the same step. Nothing argues for
   first-wins here; it is simply what `setdefault` did.
2. **The settle can be asked before the announcement exists.** Every candidate
   fix that waits "a moment longer" is a THRESHOLD, which #27/#28 removed from
   the paths that decide things. The one non-threshold idea worth measuring:
   the CLICK op already does a post-dispatch round trip (#56's delivery
   counter), so by the time it returns it could report whether a navigation had
   been announced — a fact already in hand rather than a guess, and the batch
   could use it.

**It failed LOUD, and that is #61 paying for itself hours after shipping.**
`get_url` said the url belonged to the document being replaced, on a site
neither #51 nor #61 was built for. Without that note the agent would have had
no way to know the read was stale.

---

## D4 — a `search_page` miss does not consider that the LITERAL may differ from the rendered character

**Found on:** app 2, arXiv.

`search_page("Showing 1-50 of")` returned `No match … 1603 text block(s) were
searched` on a page whose header reads exactly that phrase — because arXiv
renders an EN DASH (`Showing 1–50 of 1,325 results`), not a hyphen. The miss
message offers closed menus, frames, still-building pages and genuine absence,
and does not mention the one that was true.

This is #33's class (a note listing causes that exclude the actual one) on a
family that is common in rendered text: en/em dashes, curly quotes,
non-breaking spaces, ligatures. #52 already made a literal pattern match any
whitespace where it has a space, for the same reason and with the same
argument — a miss that reads identically to absence is the silent-failure
class. Whether the matching should normalise dashes and quotes is a separate
question with a real argument on both sides; the MESSAGE naming the
possibility is cheap and unambiguous.

Recovered by the agent with `regex=true` and `Showing 1.50 of [0-9,]+ results`,
which is also the right shape for a header carrying a number that will drift.

---

## D5 — `expect` has ONE slot per kind, and `setdefault` makes the FIRST win

**Found on:** app 3, DataTables — and it is the same two lines that produced
D3, which is why these are one finding with two faces.

```python
exp.setdefault("url",    …)
exp.setdefault("search", …)
exp.setdefault("query",  {"selector": sel, "count": tot})
```

**Face one, a stale observation beats a fresh one (D3).** After a navigating
click the first `get_url` read the document being replaced; the agent re-read
it a moment later and got the right one. `setdefault` kept the first. Nothing
argues for first-wins: everything before the next ACTION still belongs to this
step, and later is strictly more settled.

**Face two, a second check of the same kind is silently discarded.** The agent
made two `query_elements` calls after step 1 — `#example tbody tr` (9 rows) and
`#example tbody tr td:nth-child(3)` (9 cells, every one "Edinburgh"). Only the
first survives. Confirmed in the artefact: step 1's expect holds the row COUNT
and nothing about the content, and step 2 kept `th[aria-sort]` while the
ascending-age check vanished.

**So the recording asserts a count where the agent had checked the content.**
A regression returning 9 rows from the wrong office passes step 1. The agent
did the right thing and the recorder threw half of it away.

And the stop message says `9 observation(s) folded in or discarded` without
separating the two, so an agent cannot tell from the message which of its
checks survived — it has to read the file. That wording is doing the same job
as a capped number presented as a total (#36).

---

## D6 — an integer option value arrives as a float and matches nothing

**Found on:** app 3.

`form_input(ref_166, 25)` on a `<select>` returned `WARNING: no option matching
"25.0"`, twice. The signature is `value: Union[str, bool, float]`, so an
integer is coerced to `25.0`, stringified to `"25.0"`, and compared against the
option text `"25"`. `fill_form` with `"25"` worked first try.

The defect is not the coercion alone — it is that **the warning IS the whole
result.** No error, no failure status, nothing saying the write did not land.
The agent only knew because it happened to have the option list from an earlier
`read_page`.

---

## D7 — a call that warned and changed nothing is recorded as a STEP

**Found on:** app 3, and it is D6's consequence.

Both failed `form_input(25.0)` calls are in the saved flow as steps 3 and 4,
`expect: null`, while the stop message reports `dropped: 0 failed call(s)`. The
recorder drops calls that ERRORED; a call that returns a warning and does
nothing is not an error, so two dead steps now replay for ever and warn again
each time.

This is #62's refusal guard, one layer earlier. That guard taught the RUNNER to
stop on six strings the tool surface emits when it did not act; `WARNING: no
option matching` is a seventh, and the RECORDER should drop such a call rather
than compile it into the test. The two belong together: a string that means
"this did not happen" should mean the same thing at record time and at replay.

---

## D8 — observed, attribution unclear: `form_input(value="")` never left the client

`form_input(ref_175, value="")` was rejected before dispatch, twice:
`InputValidationError … You sent (first 50 of 50 bytes): {"ref": "ref_175",
"value": , "tabId": 1711639327}` — the empty string serialised to nothing at
all. `value: Union[str, bool, float]` accepts `""`, so the malformed JSON was
produced client-side and this may not be ours. Recorded because clearing a text
field is an ordinary thing to want and the agent had to reach for `fill_form`
to do it; NOT counted as a confirmed product defect without evidence of the
cause.

---

## D9 — the stop message does not say WHICH steps ended up unasserted

**Found on:** app 4, TodoMVC — the cleanest run of the four, which is why this
was the only thing left to find.

`record_flow(stop)` reported `7 step(s), 4 with assertions` and `8
observation(s) folded in or discarded`. The agent could not reconcile either
number against the calls it had made, and — the part that matters — could not
tell WHICH three steps carry nothing, so it had no way to check whether an
action it cared about went unverified.

**I guessed the answer and was wrong, which is the point.** I assumed the
unasserted steps were the two `Enter` presses — benign. The artefact says they
are step 0 `navigate` and steps 1 and 3, **both `form_input`**: the two typing
steps. That is D1 again, on a third app. The agent confirmed each typed value
with `form_input`'s own `(value now: "…")` line and with a later
`query_elements` on the row that appeared — neither of which can become a
postcondition for the typing step itself.

So across apps 1, 2 and 4 the steps that end up unasserted are the SAME ones
every time, for the same reason, and `4 of 7 had their postconditions checked`
hides exactly that.

Same family as D5's `folded in or discarded`, and the same fix shape #42
applied to `get_page_text`'s truncation note (T25): make the parts add up and
NAME them. "4 of 7 have assertions" invites the question it then refuses to
answer, and the answer costs one line.

**Also recorded, and NOT a defect:** the agent wanted to assert "the URL
changed with no full page load" and found no tool that answers it. That is a
fair want on a hash-routing SPA and there is no declaration to read — the
closest honest evidence is that a ref resolved both before and after, which the
agent noticed itself. Not built, no evidence it is worth a tool.

**Worth stating for the write-up:** this flow is idempotent because the APP
resets. A fresh navigate shows zero todos, so the build does not persist to
localStorage, and each replay starts from an empty list. The app supplies the
fixture reset that #54 otherwise requires a harness to provide.

---

## D10 — `navigate` reports a REDIRECT that did not happen, on every non-ASCII url

**Found on:** app 5, Japanese Wikipedia. Confirmed in the source before being
believed.

```
Navigated to https://ja.wikipedia.org/wiki/%E3%83%A1%E3%82%A4%E3%83%B3%E3%83%9A%E3%83%BC%E3%82%B8,
title: Wikipedia — REDIRECTED: you asked for https://ja.wikipedia.org/wiki/メインページ
and the server sent you here, so this is not the page you requested.
Anything you assert now is about …%E3%83%A1%E3%82%A4%E3%83%B3…
```

Same page. The comparison is

```js
const _same = (a, b) => String(a||"").replace(/\/+$/,"") === String(b||"").replace(/\/+$/,"");
```

— raw strings, trailing slash stripped, **no percent-decoding**. The requested
url is the decoded form and the landing url is the encoded one, so they never
match and the clause fires on EVERY navigate to a non-ASCII url.

The redirect notice is right to exist (an auth guard bouncing `/login` to
`/projects` is the case it was written for) and C15 would pass it, because the
sentence is conditional on something it believes it measured. What it measured
is an encoding difference. **It tells the agent its assertions are about a
different page when they are about the right one**, which is the inverse of the
defect it was built to prevent, and it fires on an entire class of the web.

---

## D11 — `get_url` escapes non-ASCII to `\uXXXX`. FOURTH instance of one bug.

**Found on:** app 5.

```json
{"url": "https://ja.wikipedia.org/wiki/%E6%9D%B1%E4%BA%AC%E3%82%BF%E3%83%AF%E3%83%BC",
 "title": "東京タワー - Wikipedia"}
```

The agent had to decode the title by hand to know what page it was on, while
`search_page`, `query_elements` and `find` all returned the same Japanese
unescaped in the same session. Cause: `return json.dumps(res)` with no
`ensure_ascii=False`.

**The docstring of `_q`, 600 lines above it in the same file, describes this
exact bug** — "every Chinese, Japanese, Arabic or Cyrillic label find() printed
came out as backslash-u escapes … silently undoing the collector's whole
non-Latin story". It was fixed for `find` (#11d), fixed again for
`query_elements` (#42), and `get_url` has it anyway.

**And I edited this function two hours ago** (#61, the in-flight navigation
note) without noticing — and added a second unescaped `json.dumps` while I was
there. A rule written in a docstring is a rule a human has to remember;
#30/#39's answer to that is a tripwire, and there is none for this one.

---

## D12 — `find` cannot survive a one-particle difference in an agglutinative label

**Found on:** app 5.

`find("履歴表示")` returned `No elements matched`. The rendered label is
**履歴を表示** — one inserted particle (を). `query_elements("#ca-history a")`
found it immediately.

This is not a defect in the scorer so much as a measured LIMIT of a lexical
matcher on a language with no spaces: #20 established `find` is lexical and
must be given words that appear on the page, but in Japanese the "word" is the
whole string, so a near-miss is all-or-nothing rather than degrading. Mis-
remembering a particle is an ordinary way to be slightly wrong.

**The miss path did its job** — #39's census (`2869 elements: 2291 a, …`) sent
the agent to `query_elements`, which answered in one call. Recorded as a limit
with its mitigation working, not as something to fix in the scorer; #20
explicitly rejected ranking here.

---

## Also seen on app 5, all working as designed

- **D1 for the third time**: `query_elements('input[name="search"]',
  attributes=["value"])` returned `(no text)` for a field holding 東京タワー.
- **A ref went stale with no navigation** and the message named the three
  causes without picking one; the agent diagnosed the real one (Vector 2022
  swaps the plain `<input>` for a Vue combobox on focus, so the re-fetched
  element was a different one). That is #14's stale-ref message working exactly
  as intended, and the recorder correctly DROPPED the failed call.
- 318 `search_page` matches and 50 `#pagehistory li` rows, all Japanese text
  rendered correctly everywhere except `get_url`.

---

## D13 — A DISAPPEARANCE CANNOT BE ASSERTED. Zero is falsy.

**Found on:** app 6, Bootstrap modal. The most consequential defect in the
eval, because it silently removes the second half of what a UI test asserts.

```python
if hits and pat:   exp.setdefault("search", …)
if tot  and sel:   exp.setdefault("query",  {"selector": sel, "count": tot})
```

A zero count is falsy, so **an observation that something is GONE is
discarded.** The agent confirmed the modal had closed three separate ways —
`query_elements("#exampleModalLive.show")` no match, `query_elements(".modal.show")`
no match, `search_page(…)` no match — and all three were thrown away. The saved
step 2 has no `expect` at all: **the replay passes if Close does nothing.**

**The parsers were deliberately fixed to make this possible and the consumer
throws it away.** `query_total`'s own docstring says so:

> ZERO IS AN ANSWER. query_elements reports a miss in prose … so reading only
> the numeric line conflates "nothing matched" with "I could not parse this"

It returns `0` for a miss and `None` for an unreadable result, precisely so the
two can be told apart — and then `if tot` collapses them again one function
later. Same one-half-of-a-contract shape as #30's `delta`, #54's `origin` and
#57's `viewport`: both halves exist, nothing connects them.

Half of all UI assertions are disappearances — a dialog closed, an error
cleared, a row deleted, a spinner gone. None of them can currently be recorded.

---

## D14 — `settle_ms` measures the AGENT'S turn, not the page's. #60 corrected.

**Found on:** app 6, and it corrects something I shipped today.

The saved file carries `settle_ms: 18548` for a navigate and `16465` for a
click that opens a modal in well under a second. #60 claimed the number was
"measured, not chosen … the number the system demonstrates". It is not:

```python
base = live[i].get("ts")              # the ACTION's timestamp
...                                    # every model turn in between
last = max(last, r.get("ts"))          # the LAST contributing observation
```

The gap is dominated by the agent's own think time (~3.6s per turn, #38), not
by the page. **So the Boxsy figures #60 reported — navigate 9,896ms, submit
13,077ms — are not what that entry says they are**, and every replay now allows
up to ~18s of slack on steps that need none. It fails in the safe direction (a
passing flow is unaffected; a genuinely broken step just takes longer to say
so), which is why nothing caught it.

**The fixture encoded the shape I thought of and the code generalised past
it.** FS6 models an agent that checks, gets nothing, waits, checks again — a
FAILING observation followed by a passing one. The implementation generalised
that to "the last observation that contributed a check", which on a real
recording is simply whenever the agent got round to looking. FS6c, the control
that "an instant app earns no margin", holds only because the fixture's
timestamps are synthetic and equal.

The fix follows from the fixture: the app has demonstrated it is slow only when
an earlier observation of the SAME check was seen to FAIL. Measure the retry,
not the latency; with no failed observation, the margin is zero.

---

## D15 — a `search_page` miss ignores character-level mismatch. SECOND sighting.

**Found on:** app 6, independently of app 2.

`search_page("Woo-hoo, you're reading this text in a modal!")` returned
`No match … 11 text block(s) were searched` on a page that renders exactly that
sentence — with a CURLY apostrophe (U+2019) where the agent typed a straight
one. App 2 hit the same wall with an EN DASH. **Two of six apps so far, two
different character classes, two agents who could not see why.**

That promotes D4 from an incident to a pattern: typographic substitution
(curly quotes, en/em dashes, non-breaking spaces) is what a CMS does to
ordinary prose, so the strings an agent is most likely to type are exactly the
ones most likely to be transformed. The miss message names four causes and not
this one.

---

## Also on app 6

- **D5 for the second time**: two `query_elements` after the open-click,
  only the first kept. The dropped one (`.modal-body`) was the one carrying the
  body text the task asked to confirm.
- The `aria-hidden` note fired with no modal open and said "WHY it did is not
  knowable from here", which the agent could not act on. It suggested `find`,
  which worked. Honest, and still a dead end at the moment it fires.

---

## D16 — every ref click reports the SAME coordinate, so the number says nothing

**Found on:** app 7, the ARIA combobox.

Four clicks on four different elements (the combobox twice, then two different
options) each reported `left_click at (324,406)`. The clicks all landed —
every one was followed by the expected state change — but the coordinate is
identical because each click scrolls its target into view first, and
`scrollIntoView` centres it. **A number that is the same whatever you click
cannot distinguish one click from another**, which is what a coordinate in a
result line is for.

#23 already records a related defect — `computer` reports the PRE-dispatch
coordinate, measured 343px off — and decided the REPORT misleads while the
click lands. This is the same family seen from the other side: post-scroll the
coordinate is accurate and useless. The ref is already in the same line
(`on [mmid='111']`) and is what actually identifies the target.

Low severity; recorded because it is an honest-looking number carrying no
information, which this log treats as worse than no number (#36's capped count
presented as a total).

---

## D9 again, third sighting

`9 observation(s) folded in or discarded` — the agent made 8 observation calls
and could not reconcile the number or tell which of its checks survived. Said
on apps 3, 4 and 7 by three different agents, independently.

---

## D17 — `query_elements` compiles to SELECTOR + COUNT, discarding what was read

**Found on:** app 7, by checking a flow I had just called the cleanest in the
eval. It is the precise statement of what D5 only gestured at.

App 7 records `5 steps, 5 with assertions` — the only flow here where every
step carries a postcondition. Steps 2 and 4, the two that actually PICK an
option, assert:

```json
{"query": {"selector": "#combo1", "count": 1}}
```

`#combo1` is the combobox itself. It matches exactly one element whether it
displays "Choose a Fruit", "Durian" or nothing — **verified on a fresh page
with no interaction at all: `1 element(s) match '#combo1': <div> "Choose a
Fruit"`.** So the two steps the flow exists to test assert a tautology.

The agent did everything right. Its call returned
`<div> "Durian" aria-expanded="false"` — the text was IN the result. The
recorder stores the selector and the tally and throws the content away.

**And #57's witness check cannot catch this class, correctly.** It compares a
check against its own value BEFORE the step; `#combo1` had no prior value
because the agent's earlier query used a different selector, so there was no
claim to make (FW3). #57 catches "already true before this step". This is
"true regardless of any step", which is a different and larger hole.

The signal needed to fix it is already in hand: the tool returned the text, and
`attributes=[…]` returns attributes. An assertion built from what was READ —
`#combo1` contains "Durian" — would be falsifiable. An assertion built from how
MANY matched can only ever test existence.

**This is why the eval scores from artefacts.** "5 of 5 steps had their
postconditions checked" is the strongest line any flow printed here, and two of
those five cannot fail.

---

## What app 7 still proves, which is worth as much as the defects

Both replays green (0.95s, 0.47s), and the hard part genuinely worked.

This is the hardest widget family in the project's history: #25 recorded Ant
Design v6 defeating the option picker entirely ("presented the site's own nav
bar as the field's options"), and #29 rebuilt the picker around what the page
DECLARES rather than library attribute names. Here, on the W3C's own reference
implementation of a select-only combobox — a `div[role=combobox]` controlling a
`div[role=listbox]`, no native `<select>` anywhere — the full open → pick →
reopen → pick cycle recorded and replayed with every state change asserted via
`aria-expanded` and `aria-selected`.

The agent reached it with `query_elements('[role=combobox]')` after the
whole-page `read_page` did not show it (below the fold, viewport-scoped by
design). That is #39's routing working: a lexical listing could not reach it,
the agent translated the goal into something the document declares, and asked
exactly.

---

## D18 — `query_elements` and `search_page` disagree about one element's text by one space

**Found on:** app 8, Python docs.

`query_elements("#search-results ul.search li")` returned the first result as
`"enumerate (Python function, in Built-in functions)"`. `search_page` for that
exact string, scoped to the same container, returned `No match … 264 text
block(s) were searched`. The rendered text has NO space after the link:
`enumerate(Python function, in Built-in functions)`.

Cause, confirmed in source: `query_elements` takes

```js
t = ((el.innerText != null ? el.innerText : el.textContent) || '')
      .replace(/\s+/g, ' ').trim();
```

while `search_page` builds rendered text with #39's post-order walk, which
joins inline boxes WITHOUT inserting a separator because the source whitespace
between tags already carries the spaces. Here there is no source whitespace
between `</a>` and `(`, so the walk is right and `innerText` has inserted a
space the screen does not show.

**Two tools describing the same element differently, with nothing saying
which is the screen.** That is the same class as #30's `near=`, #48's
`include_text` and #52's `<br>` — each one found when a string from one tool
would not match in the other. The practical cost here is exactly that: a
pattern copied out of `query_elements` cannot be pasted into `search_page`.

---

## D19 — a scroll note reports a direction the reader cannot interpret

**Found on:** app 8.

Clicking a LATER table-of-contents anchor reported `NOTE: this scrolled the
page 208px up` and then `190px up`. The agent wrote "I could not act on that
and do not understand which quantity 'up' refers to." X18's note exists to say
that viewport flags and printed coordinates are now stale, which it does — but
the direction is measured against the element being scrolled to, and a reader
holding a document-order mental model reads it as the page moving the other
way. Low severity, and the actionable half of the note is correct.

---

## D20 — the in-page TOC had no ordinary row, only a folded `mmid:label` line

**Found on:** app 8, and said in nearly the same words on app 7.

The sidebar TOC entries the agent needed were reachable only inside
`in-page TOC "Main" — 23 a cells as mmid:label`, with no `ref_N | a "…"` row
for any of them. App 7 said the same of a 13-option listbox. Both agents got
what they needed by parsing `mmid:label` pairs out of prose, and both remarked
that it is a different shape from every other row in the listing.

That compaction is #7's deliberate token-discipline trade for ARIA grids and
listboxes ≥10 cells, and it is not obviously wrong — but two independent agents
flagged the same friction, and one noted that a reader scanning for ordinary
rows would conclude the entries were not listed at all.
