# Eval 4 — defects found BY the eval

Logged as they arrive. **Nothing here is fixed while the eval is running**: the
two arms must face the same code, so changing the thing under test mid-run
invalidates the comparison (#19's interleaving discipline, applied to a
head-to-head instead of a threshold sweep).

---

## E4-D1 — `NOT DELIVERED` is a FALSE NEGATIVE for an in-iframe click (T1/cb)

`computer` left_click inside a same-origin iframe reported:

> `*** NOT DELIVERED: Chrome accepted the input command and the page recorded
> no event, so nothing landed. This tab's trusted-input channel is dead …
> VERIFIED RECOVERY: open a new tab`

**The click landed.** In the same batch the field went ¥5 → ¥30 and
`aria-valuenow` 5 → 30 (exactly one step of 25), and the read's own readiness
banner reported `1 @aria-valuenow` change.

Cause: #56's delivery probe arms a capturing listener on the **top** document,
and an event dispatched into a nested browsing context is not observable there.
So the probe reports "no event" for every in-iframe coordinate click.

Severity is higher than a wrong label, because the message **asserts a recovery
it has not verified** — "open a new tab" — which is #33's class and precisely
what `C15` exists to catch, inside the check added to stop a different silent
failure. #56's own `ID3` control says an unknown answer must claim nothing; an
iframe click produces a *confident* wrong answer instead.

Fix shape: arm the probe in the frame the click is dispatched into (the
coordinate resolver already knows the frame via `_frameShells` /
`resolveFrameSelector`), or — if the frame cannot be reached — fall back to
UNKNOWN and say nothing, which is the behaviour `ID3` already pins for the
navigating case.

## E4-D2 — `query_elements` does not reach into iframes (T1/cb)

`.ui-spinner input` and `.ui-spinner a` matched **nothing**, while an
iframe-scoped `read_page(ref_id=…)` listed those same elements. Two tools
disagreeing about one page, with nothing saying which is blind — the same shape
as #30's `near=` and #48's `include_text`, both of which were un-migrated older
paths.

`_queryElementsPage` walks the composed tree for shadow roots (and #48 taught
`include_text` to do so), but does not cross a frame boundary the way the
collector's `collectCrossFrames` does.

---

## T1 result — cb 7 calls, cic 19. Both answered ¥30 (referee: ¥30).

This is a **custom-widget** task, i.e. H4's interaction subset — the band
pre-registered as the one where we might be level or behind.

**What the OTHER arm hit**, recorded because the eval is also a survey of the
field and because a turn count alone hides it: its `find` returned a ref
described confidently as *"the currency select element with id 'currency'"* and
`form_input` on that exact ref failed twice with `Element type "SPAN" is not a
supported form input` — the ref resolves to a different element than the
description. Its `read_page` returned **no iframe content at all**, with nothing
indicating anything had been skipped, while its own `find` could see it. Its
`computer(action="key")` reported `Pressed 3 keys: Down Down Return` while the
select stayed unchanged — a success report for input that did not land, which
is the #10/#11/#12 family. And its `read_page` never reports a spinbutton's
current value, so the answer had to come from a zoomed screenshot rather than
the structured listing.

Ours hit the same iframe and cost 1 extra round trip to it (plus 1 to a
still-loading demo frame); theirs cost roughly 8 and required navigating
directly to the embedded document to make the select operable at all.

---

## T2/cic — a ref bound to the WRONG element and reported success

Worth recording in full, because it is the exact failure our own #72 witness
work exists to prevent, observed happening to the other arm on a real site:

> `computer left_click` on `ref_1141`, which `find` had identified as the link
> 千代田区, reported success but actually opened 利島村一円 (〒100-0301) — a row
> **two positions below** the target in the same list. Only reading the
> resulting page title revealed it.

And `find` had returned **exactly one** element for that query, so the ref was
unreliable rather than ambiguous — there was no signal of any kind. That is the
shape #72 measured on our side at 94.4% wrong under a re-sort with 0% refusals,
and it is why the fix there was a witness that REFUSES rather than a ranking
that guesses.

Two more from the same run: `navigate` reported `Navigated to …` while the tab
context still showed `chrome://newtab`, and the next call errored — success
reported before the tab moved, which is our own #40 one arm over. And a
separate ref click reported `Clicked on element ref_1046` with no navigation or
state change.

Answer was correct (〒100-0001), reached in 18 calls.

---

## T3/cb — the visibility count shipped THIS SESSION prevented a wrong answer

Unprompted, in the agent's own words:

> `query_elements` flagged that 1 of 5 matched feedback elements was not
> rendered, so I confirmed the payment-method message with `search_page`
> (rendered text only) before reporting it.

That is `OPEN.md`'s old Tier 1 item — `query_elements` reporting `total` with no
visibility signal, so one `display:none` hid an entire app and every count
assertion still passed — closed a few hours earlier and immediately load-bearing
on a real task. The page carries five validation-feedback nodes of which one is
not rendered; without the `visible` count the agent had no way to know which
message was actually on screen.

It also hit the `browser_batch` tabId rule correctly and paid one round trip for
it: inheritance applies only to steps after a `tabs_create_mcp` in the SAME
batch, so a second batch omitting tabId was refused by the pre-flight with
**nothing run** (#32), rather than firing blind at the user's active tab (#46).
A cost, and the right one.

---

## T3 — CORRECTED: not a tie. cb 5, cic 6 turns.

**This section originally read "T3 is a TIE" on the agents' self-reports.** The
transcript says cb 5 turns / 5 calls, cic **6 turns / 7 calls** — the control
agent under-counted itself by two calls. See the HARNESS DEFECT section below.

Their six turns: `ToolSearch`, `Skill`, `ToolSearch + Skill`,
`tabs_context_mcp`, then two `browser_batch`. So **4 of 6 turns were fixed
overhead** — two ToolSearches and two invocations of the skill their own
server instructions require — and only **2 did browser work**, against our 4.
**On pure browser work they were still more efficient on this task**, and that
remains the honest half.

That is #48's warning arriving: fixed overhead was 31% of that eval's gap, and
on a short task it is the entire story. A headline built on total calls would
read this as parity when the underlying shapes differ, and a headline built on
browser calls alone would read it as a loss. Both numbers are in `runs.tsv`;
neither is quoted without the other.

---

## T4/cic — a click that reported success and delivered nothing, with no detector

> The tool reported `Clicked at (335, 785)` and the page stayed on the form …
> no error, no indication it had missed, so it was indistinguishable from a
> click that landed on a button that did not respond; only re-reading the page
> revealed the URL had not changed.

This is the #10/#11/#12 family — a trusted click landing somewhere other than
the element while the tool reports success — and the honest comparison is NOT
"we are immune". We are not: T1 showed our own `NOT DELIVERED` detector gives a
FALSE NEGATIVE inside an iframe, and worse, asserts a recovery it has not
verified.

The difference is that we have a detector at all, so the failure is reported
and bounded; here there is nothing, and the agent found it only by re-reading
the page. Both facts belong in any write-up.

Its `read_page(filter="interactive")` also omitted **every radio button and the
submit button**, with no truncation notice, on a form whose whole purpose is
those controls. `find` located the submit immediately, so the elements were
reachable — the listing simply did not carry them, which is an absence that
reads as "not there".

---

## E4-D3 — `section=` attribution INVERTED on a real form (T4/cb)

`find("Search button submit")` returned NO CONFIDENT MATCH for the search
form's own submit button and tagged it `section=footer` (ref_308), while
tagging the site-wide FOOTER search input and button as `section=form`
(ref_354/ref_355). All three inverted. The agent had to deduce the right
control from y-position and the form's own header/footer structure instead of
reading it off the listing.

CLAUDE.md #23 already records that `section=` resolves to the nearest landmark
without stopping at a dialog boundary. This is worse than that entry describes:
the attribution is not merely coarse, it is **swapped**, so the field actively
misleads rather than under-informing. Open; not fixed mid-eval.

## T4 — the readiness work earned its keep on a real site

The first post-submit `get_page_text` returned `Showing 0 earthquakes`, a
transiently wrong count. The banner fired — `THE DOM IS STILL CHANGING … 1
progress indicator(s) visible … do NOT conclude something is absent from it` —
so it **failed loud rather than answering 0**. It still cost a round trip, which
is the honest cost, and the alternative was a confidently wrong answer.

cb 5 calls, cic 12. Both correct (1 result, 29.0 km).

---

## T5/cic — the other arm described #46's defect in its own words, again

> `navigate` inside `browser_batch` requires an explicit tabId, so the opening
> navigation could not be fused with a read and cost its own turn

This is the **second** independent time a control agent has reported that
limitation unprompted (#47's T8 agent was the first, and that quote is what
gave #46 its evidence — a structural check that beat the A/B that had been
planned instead of it). Threading a created tab's id into later steps of the
same batch is what removed it on our side.

It also reported a stale self-contradicting tab context: the `navigate` result
said it had navigated tabId 1711644942 while the `tabs_context_mcp` listing in
the SAME output described that tab as a previous task's page. The agent had to
re-verify which tab it was acting on before reading anything.

cb 5, cic 7 turns (transcript; the control self-reported 6). Both correct.

---

## T6/cic — three defects in one run, and one of them is our #39 verbatim

The control arm reported all three itself, unprompted:

1. **`tabs_create_mcp` inside `browser_batch` errored "No tab available"** and
   aborted the whole batch. A tab-creation step cannot require a pre-existing
   tab. This is the THIRD independent sighting of the opening-ceremony cost on
   that arm (#47's T8, this eval's T5, now T6) and the second distinct
   mechanism — T5 was "navigate requires an explicit tabId", this is the create
   step itself failing.

2. **`find` asserted an absence with no readiness signal.** Run right after a
   navigate, before the Angular SPA had rendered, it answered that "No checkbox
   elements or category filters related to 'Chisels' are present" and suggested
   they might be on a different page. The filter exists. This is CLAUDE.md #39
   exactly — `find` was the one tool with no settling signal, so
   `NO CONFIDENT MATCH` and "not there yet" were byte-identical — and #35
   predicted it before #39 fixed it. Fetching the readiness note on the FAILURE
   paths only is what closed it on our side.

3. **Their `read_page(filter="interactive")` omitted every category and brand
   filter checkbox** on a page where their own `find` located ref_105
   "Chisels" moments later. Same page, same instant, two tools disagreeing
   about what exists — the #18 asymmetry, on the other arm.

Worth stating plainly: these are THEIR defects and they are not evidence for
our representation beyond the turn column. What (2) does show is that the
problem #39 fixed is real rather than theoretical — another implementation hit
it on a live site in this very eval.

cic 8 calls.

---

## HARNESS DEFECT (mine): I reported a table built from self-reports

`score.py` takes an AGENT ID and reads the JSONL transcript. Its docstring says
why, in the first line: *"Score one eval run from its TRANSCRIPT, never from
what the agent reported. An agent counting its own tool calls is a self-report
inside the thing being measured."* `analyse.py` calls `score(ag)` on the fourth
column of `runs.tsv`.

I had been writing the agent's seven-line REPORT into that column. So every row
would have returned `{"error": "no transcript"}` and `analyse.py` would have
died on the first `cb["turns"]` — and in the meantime the table I reported
live was assembled from the `TOOL_CALLS:` line each agent wrote about itself.
The header said `agent_report`; the consumer wanted `agent_id`. A declared
column and the code that reads it disagreeing is the same half-contract shape
this project keeps finding (#30 `delta`, #54 `origin`, #57 `viewport`, #62
`on_fail`, #69 the event channel) — this time in the measurement harness, which
is the worst place for it.

Nothing was lost: all twelve transcripts are on disk and the agent ids were
recovered MECHANICALLY from the subagent meta files by description, never
transcribed. `runs.tsv` now carries ids; the self-reports are kept in
`self_reports.archive.tsv` for provenance.

**Re-scored from transcripts, two of five pairs change, both in the direction
that had UNDERSTATED our margin:**

| task | self-reported | transcript TURNS | effect |
|---|---|---|---|
| T3 | cb 5, cic 5 — tie | **cb 5, cic 6** | tie becomes a CB win |
| T5 | cb 5, cic 6 | **cb 5, cic 7** | margin doubles |

Both control runs under-counted themselves by one, and the sequence says why:
each opened `ToolSearch, Skill, ToolSearch+Skill` — the claude-in-chrome server
instructions require a skill invocation the prompt never asks for, and the
agent did not count it. That is a real fixed cost on their side and it is now
measured instead of being taken on the agent's word. #47 found two scorer
defects the same way, by a self-report DISAGREEING with the transcript.

**A scorer caveat I am recording rather than fixing.** `one_turn_start` checks
whether the first browser turn's batch CONTAINED `tabs_create_mcp` — not
whether it worked. T6/cic scores True on a batch that aborted with "No tab
available". The fix would flip that row to False, which moves H3 in OUR favour,
so changing the instrument now would be self-serving. The bar stays as
pre-registered and H3 is reported with this caveat attached.

---

## T6 — a TIE, and the honest finding is a LIMIT of the readiness work

cb 8 turns, cic 8 turns. Both correct (Swiss Woodcarving Chisels, $22.96).

Our arm's two costs were its own: it under-loaded the opening `ToolSearch` and
paid a second one, and it re-read after the first `read_page` landed mid-render
on the Angular app (the banner flagged that correctly, so it cost a round trip
rather than a wrong answer — the same trade T4 shows).

**The finding worth keeping is the one against us.** The agent set the Chisels
checkbox and the sort select in ONE atomic `fill_form`. The page came back
showing the three Chisels products in UNSORTED order ($12.96, $45.23, $22.96)
while the select itself reported `value="price,desc"`. The next observation
carried `DOM STABLE, NETWORK BUSY. No DOM change for 12617ms` — a confident
settled verdict over a page in the wrong state — and a second `get_page_text`
twelve seconds later returned the identical wrong order, so repetition did not
expose it either.

The cause is app-side: the category-filter XHR and the sort XHR race, and the
category one returned last and discarded the sort. The DOM genuinely had
stopped changing. So the signal was not wrong — but this is the boundary of
what it can claim, and it needs saying in those words:

> **#70's mutation signal answers "is the DOM still being rewritten". It does
> NOT answer "is the page in the state you asked for".** A page that settles
> into an incorrect state is indistinguishable, to that signal, from one that
> settled into a correct one.

That is not a defect to patch — nothing structural distinguishes "settled
wrong" from "settled right", and a signal that tried would be guessing. What it
argues for is the agent-side discipline the run then used: the agent caught it
only because the order was arithmetically inconsistent with the sort it had
just applied, re-applied the sort after the filter had settled, and verified by
running Low-High and checking the ordering reversed exactly. **Verifying a sort
by reversing it is a control, not ceremony.**

Second, smaller: `fill_form` reported `ok:true` with `actual="Price (High -
Low)"`. Truthful about the CONTROL, and it reads as "the sort is applied" when
the list beneath it is not sorted. The readback verifies the field, which is
what #24 built it to do; it cannot verify the app's response to the field.

---

## T7 — a `get_page_text` that returned 3 lines of a 19-row page, on their side

cb 3 turns, cic 9 (transcript-scored below). Both correct: 19 results, first is
`Cheese, cheddar`.

Their agent's own words on the defect that cost it the task:

> `get_page_text` (call 4) returned only ~3 lines — the "Foundation Foods"
> description blurb it picked as "Source element: `<article>`" — and none of
> the search-results table, the page's actual content. It reported no
> truncation and no error, so the output read like a complete page extraction
> of a page that has 19 result rows on it. **Every value in this answer had to
> be read off screenshots instead.**

That is the silent-bound class #22 built `markCut` for, in the tool whose whole
job is to hand over page text: a bounded result that gives no sign of being
bounded. Picking one `<article>` as "the source element" and reporting it as
the page is the same shape as #37's eBay defect, where a closed mega-menu's
text became a nav item's identity — an extraction choosing a subtree and not
saying so.

**Ours, and it is a real wording defect.** `navigate` reported:

> REDIRECTED: you asked for `…/food-search?query=cheese` and the server sent
> you here, so this is not the page you requested

for what is only a trailing-slash normalisation (`…/food-search/?query=cheese`).
The agent re-checked it was on the right page. Same family as #63's defect where
`_same` compared a decoded request against an encoded landing url and claimed a
redirect on every non-Latin url: a path-normalising redirect is not a
substantive one, and asserting it is costs a re-check every time. Logged as
**E4-D4**; not fixed mid-run.

Both agents independently noted the task's own premise is soft — that URL
already lands on the Foundation Foods tab, so the restriction needs no click.
Each confirmed the restriction was in effect from the tab count, the heading and
the row count agreeing, rather than assuming it. The referee's value (19,
Cheese cheddar) is unaffected.
