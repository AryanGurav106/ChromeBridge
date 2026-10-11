# Round two — do the fixed assertions bite on a real app?

AMENDMENT 2 predicted M1 would get WORSE, because round one's greens included
assertions that could not fail. Round-one artefacts were snapshotted before any
re-recording so the comparison is exact.

## ev-apg-select-only-combobox

**The cleanest evidence available, because step 3 used the IDENTICAL selector
in both rounds and only the new field differs.**

| | step 3 assertion |
|---|---|
| round 1 | `{"selector": "#combo1[aria-expanded=\"true\"]", "count": 1}` |
| round 2 | `{"selector": "#combo1[aria-expanded=\"true\"]", "count": 1, "text": "Durian"}` |

Round one's version holds whenever the combobox is OPEN — whether or not
anything was picked. Round two's requires it to read "Durian". The added field
is attributable entirely to the fix; nothing else about that step changed.

**Verified against an untouched page**, which is what "cannot fail" means:

```
#combo1                        -> 1 element(s) match: <div> "Choose a Fruit"   (round 1 step 2: TRUE with no interaction)
#combo1-7[aria-selected=true]  -> No element matches                           (round 2: FALSE with no interaction)
```

**`settle_ms` collapsed from `[5821, 2895, 9346, 2643, 4520]` to `[0,0,0,0,0]`.**
Same app, same interaction, same code path — the earlier numbers were my own
model turns (#63/D14) and the app never actually made a check change its
answer, so the margin is correctly nothing.

Replays green in 1.16s, 5/5 steps asserted.

**Honest attribution:** the agent also chose a better selector this round
(`#combo1-7[aria-selected="true"]` where round one used `#combo1`). That is
agent variation, not the fix, and is not claimed as evidence. The two things
that ARE the fix: `text` exists at all, and `settle_ms` is no longer inflated.

## ev-bootstrap-modal-demo — the fix works, and it brought two new defects

**D13 landed, visibly.** The Close step went from nothing to something that
can fail:

| | step 2 (Close) |
|---|---|
| round 1 | `null` — the replay passed if Close did nothing |
| round 2 | `{"query": {"selector": ".modal.show", "count": 0}}` |

**D5 landed too**: step 1's `search` is now a LIST of two checks where round one
kept one. Replays green, 3/3 asserted (round one: 2/3).

### R2-D1 — a MISTYPED search is promoted to a permanent contract

The agent searched for the straight-apostrophe form, got zero because the page
renders a curly one, then corrected itself. Both were recorded:

```json
"search": [
  {"pattern": "Woo-hoo, you're reading this text in a modal!", "absent": true},
  {"pattern": "Woo-hoo, you’re reading this text in a modal!", "min": 1}
]
```

**A typo became a requirement that the straight-apostrophe form must never
appear.** It passes today and it asserts nothing anyone meant. This is the
direct cost of D13's fix: once a zero is an answer, every mistyped search
during recording is an absence assertion.

The rule that separates them is already in the recording and is #57's:
**an absence is only evidence if the thing was SEEN earlier.** `.modal.show`
was observed at 1 before the Close, so `count: 0` after it witnesses a real
disappearance. The straight-apostrophe pattern was never seen non-zero
anywhere, so its absence witnesses nothing — it is an unwitnessed absence and
should be dropped and NAMED, not compiled.

### R2-D2 — `settle_ms` is still agent-dominated when a retry crosses a turn

Step 1 recorded `settle_ms: 22550`. The D14 rule fired correctly — the check
genuinely CHANGED answer, because the agent's post-click `query_elements`
raced Bootstrap's fade-in and returned "No element matches", and the re-check
found it. But the two observations sat either side of a model turn, so the
measured gap is 22.5s for a CSS transition of a few hundred milliseconds.

This is inherent rather than a slip: the recorder can only measure between
observations, and observations are separated by model turns (~3.6s, #38), so
`settle_ms` is an upper bound that includes at least one turn whenever a retry
happened. D14 removed the case where NOTHING changed; it cannot remove this
one. What it can do is SAY so — a 22.5s margin baked into a replay means a
genuinely broken modal takes 22.5s to report it, and right now nothing tells
the agent that number came from its own latency.

### Also seen

- The batch's post-click settle covers NAVIGATIONS only, so three consecutive
  observations read the page before a CSS fade-in finished and "No element
  matches" was byte-identical to a failed click. #51's settle is about
  documents; a modal open is a transition, and nothing covers it.
- The new typographic hint fired and was correct: *"this pattern contains a
  straight apostrophe (pages often render ’)"* — the agent named it as the
  reason it recovered in one retry.
- The footer Close is pinned by ORDINAL (`nth: 1, of: 2`) because the header ×
  shares its accessible name. Working as designed (#49), and worth noting that
  a dialog with two identically-named Close buttons is the common case.

## ev-arxiv-advanced-search — the round-one failure is fixed, and a new one took its place

**D3 landed on the exact flow it was diagnosed from.** The agent hit the
identical race — it reported `A navigation to … is IN FLIGHT (pending). The url
and title above belong to the document being REPLACED` — and this time the
recorder refused to compile that read:

| | the recorded url |
|---|---|
| round 1 | `https://arxiv.org/search/advanced` — the page being LEFT. Failed every replay. |
| round 2 | `https://arxiv.org/search/advanced?advanced=&terms-0-term=quantum+computing&classification-computer_science=y&…` |

The url assertion now PASSES; the replay gets past it and fails on the next
check. `settle_ms` went from `[None, 22516, 10, 7, 20319]` to all zero.

### R2-D3 — a `search_page` assertion keeps only its PATTERN

The flow still fails, for something round one never exposed:

```
step 3: search_page('Showing 1[–-]50 of [\d,]+ results') found 0, recorded at least 1
```

The agent called `search_page(pattern=…, regex=True)` and got one match. The
recorder stores `{"pattern": …}` and the runner replays

```python
self.call("search_page", {"tabId": …, "pattern": s["pattern"]})
```

— no `regex`, no `css_scope`, no `case_sensitive`. **A regex recorded as an
assertion is replayed as a literal and can never match.** The same drop hit
the modal flow silently: that agent scoped its search to `#exampleModalLive`
and the replay searched the whole page, which passed for the wrong reason —
a weaker assertion than the one the agent made.

Round one never saw it because that agent happened to use a plain literal.
This is the same one-half-of-a-contract shape as `delta` (#30), `origin`
(#54) and `viewport` (#57): the parameter exists on the tool, the recording
drops it, and nothing says so.

**It also argues for recording a regex at all** — the agent reached for one
deliberately, because the header carries a result COUNT that will drift
(`Showing 1–50 of 1,325 results`), and a literal assertion on that line would
break the moment arXiv indexes another paper. A flow feature that silently
downgrades the robust form to the brittle one is working against the person
using it.

### Also

- D9's new line fired: `NOT asserted, so a regression in these steps cannot be
  caught: step 0 navigate.` The agent read it and noted it had placed a
  `read_page` after the navigate, which does not become an assertion — true,
  stated in `record_flow`'s docstring, and evidently not where an agent looks.

## boxsy-contacts-drilldown — a new shape on the user's own app, read-only

3 steps, 3 with assertions, on a React SPA against a live staging app. The D5
multi-check fix is visible: step 2's `query` is a LIST of two, and the second
carries `text` from the mailto link.

### R2-D4 — the witness warning over-claims when only SOME checks are hollow

```
WARNING: step 2's url assertion was ALREADY TRUE before that step ran, so it
does not witness it — this flow would pass even if the step did nothing.
```

The first clause is correct and useful: clicking a contact row opens a SIDE
PANEL and does not change the url, so folding a url check into that step adds
nothing. **The second clause is false.** Step 2 also asserts
`[role=dialog] == 1`, `[role=dialog] a[href^='mailto'] == 1` and a content
search for the Master Title — the first of those fails outright if the panel
never opens.

#57 was written when a step carried at most one check of each kind, so "some
checks were already true" and "this step is unwitnessed" were the same
statement. Since the D5 fix a step can hold several, and the message now
asserts something it has not established — #33's class, in the warning
written to catch exactly that class of defect.

The fix is a distinction the data already supports: ALL of a step's checks
already true means the flow would pass regardless; SOME means the named check
adds nothing while the others still witness the step. The agent spotted this
itself and added that it had no way to drop the useless url check even having
been told about it.

### Also, and this is the most-repeated complaint of the whole eval

Three separate waits on this app, each a blind `computer(wait, 3s)`, because
nothing says when a client-side render has finished. The readiness banner
reported **MORE** requests in flight on the second read (7) than the first (2)
while the listing was by then complete and correct, so it could not separate
"not ready" from "ready but chatty". #15's banner answers "is the DOCUMENT
settling"; an SPA that has committed its document and is still painting rows
is outside what it measures.

## boxsy-investors-filter — a filter round trip, read-only

3 steps, 3 with assertions, replays green in 6.05s. 25 rows → filter → 6 rows →
clear → 25 rows, with a CONTENT check at each stage (every remaining row
contains the term; a row the filter had removed is back afterwards). The D5
multi-check fix is carrying both the count and the content on the same step,
which is exactly the case round one dropped.

### R2-D5 — D8 is now pinned down, and it is the CLIENT

Round one left this as "attribution unclear". This agent produced the
discriminator:

```
form_input(ref_320, value="")               -> InputValidationError:
    {"ref": "ref_320", "value": , "tabId": 1711639349}
browser_batch([{form_input, value: ""}])    -> Success. (value now: "")
```

**The same empty string survives when NESTED inside another tool's argument
object and is dropped at the top level.** That is the client serialising the
call, not our schema — `Union[str, bool, float]` accepts `""`, and nothing
server-side can rescue malformed JSON. Clearing a text field is an ordinary
thing to want, so the useful response is to say so in the tool description
and name the two forms that work (`fill_form`, or the same call inside a
batch), rather than to pretend it is ours or that it does not happen.

### Also

- `search_page` returned a ref on one call and not on a later identical one,
  on the same page — correct (the filter re-rendered the rows and new nodes
  carry no mmid until a `read_page` stamps them) and the note says exactly
  that, but the inconsistency within one session reads as a tool being
  unreliable.
- The table renders 25 rows while the tab label says "Investors 44". Q8's
  declared-total warning cannot fire because this table declares neither
  `aria-rowcount` nor `aria-setsize` — the undeclared case #35 recorded and
  deliberately did not guess at. The agent flagged the ambiguity unprompted,
  which is the evidence that the gap is real rather than theoretical.
- The blind-wait complaint again, and the banner again reporting MORE requests
  in flight (4) on the read that was usable than on the one that was not (1).

## ev-httpbin-pizza-form — the step count improved and the typing steps did NOT

Round one: 7 steps, **4** with assertions, the three typing steps carrying
nothing. Round two: 7 steps, **6** with assertions. That reads like the fix
working, and for the radio and the checkbox it is — `input[name=size]:checked`
and `input[name=topping]:checked` are genuinely falsifiable.

**For the three typing steps it is not.** What they actually assert:

```json
{"query": {"selector": "input[name=custname]",   "count": 1}}
{"query": {"selector": "input[name=custemail]",  "count": 1}}
{"query": {"selector": "textarea[name=comments]","count": 1}}
```

The field exists whether or not anything was typed into it. **These are the
same existence checks round one had — they just stopped being absent.**

### R2-D6 — my two fixes were designed separately and do not meet

D1 made a typed value READABLE: the agent called
`query_elements('input[name=custname]', attributes=["value"])` and got back
`value="Ada Lovelace"`, which round one could not do at all.

D17 made a single-match query keep what it read — but it keeps `text`, via
`query_first_text`. **An `<input>` has no text.** Its value came back in the
ATTRIBUTES, and the recorder drops attributes exactly as it drops `regex`
(R2-D3).

So the value is visible to the agent and invisible to the recording, and the
commonest action in any UI test still cannot be verified at the step that
performs it. The agent did everything right, twice over, and the artefact
records existence.

This is the same one-half-of-a-contract shape as R2-D3, and the two want one
fix: an assertion should keep WHAT WAS READ — text and attributes both —
rather than only the half that happens to be a text node.

**It is also the sharpest argument for scoring from artefacts.** `6 of 7
completed step(s) had their postconditions checked` is the best line this flow
has ever printed, and three of those six cannot fail.

## ev-datatables-zero-config — content checks survive now, and D9's message misled

Round one asserted a row COUNT where the agent had checked the rows' CONTENT,
because only the first query per step survived. Round two keeps both, and the
agent's content checks are in the file:

```
step 1: search "Edinburgh" min 1 observed 9  +  query #example tbody tr == 9
step 2: search "Quinn Flynn" min 1           +  query td:nth-child(4) == 9
step 6: search "Tokyo" min 1 observed 3      +  query #example tbody tr == 25
```

Step 2's is the good one: row 2 was Dai Rios before the sort, so searching for
Quinn Flynn in `tbody tr:nth-child(2)` detects the SORT specifically rather
than that the table still has rows.

### R2-D7 — a step is named by its INDEX and its TOOL, which an agent cannot map back

D9's new line fired correctly:

```
NOT asserted … step 0 navigate, step 4 form_input, step 5 computer
```

and the agent disputed it: *"The stop message says step 5 is unasserted even
though I made two observations immediately after it … I already did."*

**The message was right and the agent was wrong**, which makes this a message
defect rather than a compile one. The flow has THREE `form_input` steps and
THREE `computer` steps; step 4 is the single-space workaround and step 5 the
`triple_click`, not the dropdown and the delete the agent had in mind. Naming
a step by position and tool alone is not enough to find it in your own
transcript — the target is right there in the descriptor and would settle it
(`step 4 form_input into "Search:"`).

### Also

- **D8/R2-D5 cost this agent two extra steps.** `form_input(value="")` failed
  three times, the agent worked around it with a single SPACE — which did not
  clear the field, it typed a space — and then needed `triple_click` + `key
  Delete`. The flow now carries a space-typing step whose value was
  parameterised into a variable called `search_2`, plus two unasserted
  `computer` steps, where one `form_input` would have done.
- The flow file stores `{"value": 25.0}` for the dropdown step. The D6 fix
  normalises at dispatch so the replay sends "25" and passes, but the RECORDED
  value is still the coerced float — the fix is in the tool and not in what
  the recording shows you.
- `search_page` scoped to `#example tbody` reported 8 of its 9 hits under one
  ref and the 9th under another, on rows that are plainly different elements.
  Counts and content were right. Not chased; recorded.

## ev-jawiki-tokyo-tower and ev-todomvc-react

Both replay green (3.01s, 0.64s).

### D11 confirmed on the language it was found in

The agent checked for mangling explicitly because it was asked to, and found
none anywhere: the url `…/wiki/メインページ` percent-encoded correctly, `read_page`
printing `name="Wikipedia内を検索"` and `Main heading: "選り抜き記事"` intact,
`find("履歴を表示")` matching on the Japanese label including the を that defeated
round one's `find("履歴表示")`, `search_page("東京タワー")` returning 318 matches
with CJK context quoted correctly, and `「東京タワー」の変更履歴` matched including
the corner brackets. **No `\uXXXX` escapes anywhere.**

And the clearest single line, which needed BOTH fixes to exist:

```
computer(type, "東京タワー")  →  query_elements("input[type=search]", attributes=["value"])  →  value="東京タワー"
```

D1 made the typed value readable at all; D11 stopped it being escaped. Round
one could do neither. (The recorder still drops the attribute from the
assertion — R2-D6 — so this read the right thing and recorded existence.)

### The Vector-2022 combobox swap, again, and handled correctly

`computer(left_click, ref_90)` landed and the NEXT step in the same batch
failed: `element [mmid='90'] not found, so nothing was typed. The ref is stale
… call read_page (or find) first`. Wikipedia's header replaces the plain
`<input type=search>` with a Vue combobox the moment it is focused, so **the
element was destroyed by its own click**. No navigation and no large element-
count change, so neither batch guard applies; the op refused rather than
typing somewhere else, the message named the recovery, and the errored call
was correctly DROPPED at compile (`dropped: 1 failed call(s)`). That is three
separate safety properties working on one event.

### TodoMVC — 9 steps, 4 asserted, and now you can SEE which

The agent batched `click → form_input → key → query_elements`, so the
intermediate click and write absorbed no assertion of their own. The stop
message named all five: `step 0 navigate, step 1 computer, step 2 form_input,
step 4 computer, step 5 form_input`. Round one reported `7 step(s), 4 with
assertions` and said nothing about which — the agent could only have found out
by reading the file. The agent read the list and accepted it, which is D9
doing its job.

## ev-python-docs-controlflow and boxsy-rounds-tab

5/5 and 3/3 asserted, both green (1.65s, 5.76s). Round one's python-docs was
4/5 with no content check; this one asserts `Search finished, found 58 pages`
and a sentence from the match-statement section.

### R2-D8 — an in-page HASH CHANGE is treated as a navigation

```
computer SKIPPED: the page navigated to …/controlflow.html#the-range-function,
and this step names a ref or coordinate planned against the PREVIOUS page, so
it is now STALE and may address something else. Nothing was dispatched.
```

Two queued clicks were dropped. **The document was never replaced** — same
page, same anchors, same mmids — and re-issuing the identical refs one batch
later worked unchanged. Cost two round trips, and left two duplicate `get_url`
observations attached to the first click.

Cause, confirmed in source:

```python
if _after.get("url") != _before.get("url"):
    _stale_why = f"the page navigated to {_after.get('url')}"
```

A raw string compare, fragment included. **HTML defines a fragment change as a
SAME-DOCUMENT navigation**: the document is not replaced, so no ref can have
been invalidated by it. Comparing the url with the fragment stripped is a
declared fact rather than a heuristic.

Safe for hash-routed SPAs too, because the staleness question is "are these
refs still valid", and #51's ref-resolution check answers that independently —
a hash-routed app that really does destroy its rows is caught there, by
whether each named mmid still resolves, not by the url string.

### Also

- `query_elements("table tbody tr")` and `[role=row]` both missed on the Boxsy
  Rounds view, which renders Name/Amount/Started columns with no table markup
  at all. Two wasted round trips, and the agent recovered with `h3`. Nothing
  to fix — the page declares no table — but it is the clearest case yet for
  why `read_page`'s data-table hint exists and why its absence is information.
- The readiness banner fired on both Boxsy views AFTER an explicit 3s wait,
  reporting `4 progress indicator(s) visible` while the content was complete
  and verified. Fifth agent to say the banner cannot separate "not ready" from
  "ready but chatty" on an SPA.

---

# Round two: result

11 flows recorded (the 8 eval apps re-recorded, plus 3 against a live staging
app), 10 replay green. AMENDMENT 2 predicted M1 would get WORSE and it did —
round one scored 7/8 on the eval apps with assertions that could not fail;
round two's single failure is a defect the fixes EXPOSED rather than caused.

| fixed in #63 | confirmed on a real app in round two |
|---|---|
| D13 zero is an answer | modal Close: `expect: null` → `{".modal.show", count: 0}` |
| D17 keep what was read | combobox step 3: same selector + `text: "Durian"` |
| D5 one slot per kind | DataTables and Boxsy now carry count AND content |
| D3 stale read not compiled | arXiv records the RESULTS url, not the one it left |
| D14 settle_ms | `[None, 22516, 10, 7, 20319]` → zero |
| D1 + D11 | `value="東京タワー"` read back byte-exact, unescaped |
| D9 name the unasserted | agents read the list; one disputed it (R2-D7) |

**Eight new defects, three of them caused by the fixes** — R2-D1 (a typo
promoted to a contract), R2-D6 (`text` cannot hold a field's value), R2-D3
(search flags dropped). All three are now fixed, plus R2-D4, R2-D7, R2-D8 and
the two tooling defects. R2-D2 (settle_ms as an upper bound) and the SPA
readiness gap are recorded and deliberately not guessed at.

**The method note.** Every one of the eight was found by reading an ARTEFACT
or a source line, never by accepting a summary — including four times when the
summary was mine. `6 of 7 steps had their postconditions checked` and `5 of 5`
were both true and both concealed assertions that could not fail.
