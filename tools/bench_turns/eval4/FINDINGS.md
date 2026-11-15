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

---

## T8/cic — the same two defects as T6 and T7, which makes them a PATTERN

cic 8 turns. Its own report:

> `read_page(filter="interactive")` listed only ref_1..ref_21 **with no
> truncation note and no off-viewport count**, yet a later `find` resolved
> ref_137 for the brand checkbox — so the listing was silently incomplete and
> the entire "By brand:" filter sidebar was undiscoverable from it.

and

> `get_page_text` on /product/… returned a page that looked complete — header,
> "Related products", footer all present — but silently omitted the whole
> product detail block (no name, brand, or price), with nothing indicating the
> page was still rendering; **a finished-looking page and a half-rendered one
> were byte-indistinguishable.**

Both are repeats. The incomplete listing is T6/cic's third defect on the same
site; the unmarked partial text is T7/cic's. Three sightings across three
tasks, two distinct mechanisms, one shared shape:

> **The control arm has no signal for "this listing is bounded" and no signal
> for "this page is still rendering", so a bounded result and a complete one
> are the same bytes.**

Those are the two things this project spent #13/#22/#27 and #15/#43/#70 on
respectively, and they are the reason our arm's extra round trips in this eval
(T6, T7, T8) cost a turn instead of an answer. The honest framing: **our
agents also hit mid-render pages on these same sites — the difference is that
ours were told.** T7/cb: "the readiness banner correctly flagged it as
mid-render, but it still cost a re-read." Being told costs one round trip.
Not being told costs correctness, and on this eval it did not — because their
agents were careful enough to cross-check with screenshots — which is the
right thing to say rather than claiming a correctness win we did not observe.

What this does NOT show: nothing here is evidence about our listing's
completeness. That is measured by `lost_identities` (0 across 32 sites, #36)
and Mind2Web (~96%, #73), not by another tool's failures.

---

## T8 — a TIE at 8-8, and the settle has a gap the navigation fix does not cover

Both correct (Washers, $3.55).

**Ours, and it is the clearest statement yet of #51's boundary.** Our agent
chained `search_page` after a product-link click inside one batch. Both
searches missed on a page where both strings are present. The batch's
post-click settle waits for the NEW DOCUMENT's DOM, and on this Angular SPA
that lands before the content XHRs resolve. So the settle did exactly what it
promises and the promise is narrower than the case.

> It failed LOUD, not silently: the readiness banner led both results with
> "THE DOM IS STILL CHANGING ... do NOT conclude something is absent", which is
> exactly why I re-checked instead of reporting absence.

That is the right outcome and it still cost a round trip. It is `OPEN.md` item
6 (a CSS transition is not waited for) widened: **the settle covers document
commit, not content arrival**, and the mutation signal from #70 is the thing
that could answer it. Not attempted mid-eval. Logged **E4-D5**.

**Second, ours, and smaller.** The off-viewport region hint named
`form(ref_164): 3`, our agent scoped to it expecting the brand filters, and it
was the SEARCH BOX form. The hint names regions by TAG, not by purpose, so two
unrelated `<form>`s are indistinguishable in it. #26 built that hint so the
recovery would be one small scoped read instead of a scroll plus a re-listing;
when it names the wrong form the recovery costs a read and returns nothing.
Logged **E4-D6**.

## T9 — cb 5, correct

The blocker was the agent's own tool choice (`search_page` greps rendered text
and returns no href, so finding the Athletics URL needed `query_elements`),
which is a docstring question rather than a defect.

**And a real question about #70 that this raises, stated correctly rather
than as a false positive.** The agent quoted
"THE DOM IS STILL CHANGING … 3 image requests in flight, readyState=interactive"
on a results table it judged fully rendered. Read against the source, that IS
the structural tier — the network and readyState bits arrive in its `; also`
clause — so genuine childList or characterData records were in the window.

On a freshly navigated document they would be: **parsing the document IS a
childList mutation**, and the window is 3000ms. So a read taken within three
seconds of a navigation will essentially always raise the structural banner,
whether or not the page is actually incomplete.

That is not a bug and it is not nothing. The window was set to 3000ms on
measurement — R23 found a 1000ms window **50.7% false-quiet** at a 2s commit
interval, and false quiet is the worst direction this probe can fail in. The
cost of that choice is a trailing edge, and the trailing edge lands on exactly
the commonest read there is.

**Three for three in this eval so far**: T7/cb, T8/cb and T9/cb all raised it
on a post-navigation read. In T7 and T8 the page genuinely was incomplete and
the banner saved a wrong answer. In T9 it was complete and the banner cost
nothing only because the agent cross-checked against the race narrative in the
same read.

**The measurement this owes, and it is new debt created by this morning's
work:** of post-navigation reads that raise the structural banner, what
fraction were genuinely incomplete? If it is low, the banner is training its
reader to ignore it, which is the #15 noise failure arriving through a door
#43 did not close. Not measurable mid-eval — it needs the browser. Logged
**E4-D7**, and it belongs in `OPEN.md` item 5 when the run ends.

## T9/cic — #46's wrong-tab defect, observed doing harm

cb 5, cic 9. Both correct (21).

Their agent's first defect, in its own words:

> inside `browser_batch`, `tabs_create_mcp` made tab 1711644955 but the
> following `navigate` (no tabId) drove a DIFFERENT, pre-existing tab
> 1711644948 instead — **the newly created tab sat unused at chrome://newtab
> while an unrelated tab I did not open was navigated away from its content**

That is #46 exactly, and it is the first time in four evals that the defect has
been caught DOING the harm rather than merely costing a turn. #46's entry
describes it as the batch navigating the USER'S OWN TAB silently while
reporting success, and the reason it is structural rather than a wording
problem: a created tab is `active: false` on purpose, `resolveTab` falls back
to the ACTIVE tab, and nothing threaded the new id into the later steps. On our
side a batch's later steps inherit the tab the create just made, and B11b/B11d
are the controls that an explicit tabId still wins and that steps BEFORE the
create do not inherit.

Four independent sightings of the opening-ceremony cost on their arm now, in
three evals: #47's T8 ("navigate inside browser_batch requires an explicit
tabId"), this eval's T5 (same), T6 ("No tab available" aborting the batch), and
now T9 (the navigate silently driving someone else's tab).

Their second defect is NOT ours, and I checked rather than assuming: their
`find` returned `href` inline on one call and omitted it on an identical kind
of link on the next, costing a `read_page(ref_id=…)` just to learn a link
target. Ours fetches `detail="full"` unconditionally (`mcp_server.py`:2316) so
`href` is always computed, and emits it whenever the element has one
(`if el.get("href")`, :2788) rather than conditionally on anything. Pinned by
F17 and F18, the second of which exists because adding `href` to the identity
block once deleted the label beside it. **E4-D8 closed, not ours.**

## T10 — cb 3, cic 4. The readiness banner stated its counts and was right.

Both correct (A000108, OFFSET `0,3`).

Direct evidence on **E4-D7**, from our agent on this page:

> The readiness banner fired on the first read ("195 change(s) in the last
> 3000ms: 192 structural") and was accurate — the page was still building.

So on OEIS the structural tier fired with a real count on a genuinely
incomplete page. That does not settle T9's case, where the agent did not quote
a count, but it does say the signal is reporting measured numbers rather than
firing on a constant. The measurement E4-D7 asks for is still owed.

**A cost worth recording on both sides.** OEIS returns the full 125k-character
A000108 entry inline on the SEARCH RESULTS url. Their arm pulled 50,000
characters of it; ours pulled 29,130. Both truncated, and ours itemised where
the budget went, which is #42's reconciliation fix doing its job. But neither
is the right tool for a one-field question — `search_page` answers it in a few
hundred characters, and our agent did use it, which is why this is 3 against 4
rather than further apart.

**A small one of ours.** `search_page("OFFSET")` is case-insensitive by
default, so 7 of 8 hits were prose uses of "offset" in the COMMENTS and FORMULA
sections, each carrying a `…(+14463)` residual marker. The right hit
(`<div "OFFSET"@0> OFFSET | 0,3`) was first and unambiguous, so it cost
nothing. Not a defect: case-insensitive is the right default, `case_sensitive`
exists, and the residual markers are #22's work being loud rather than silent.
Recorded because a reader of the raw output could mistake eight hits for
ambiguity.

## T11/cb — E4-D9: the settle races the navigation's own ANNOUNCEMENT, second sighting

cb 6 turns, correct (`(exact)`).

Our agent observed the settle behaving differently for two clicks in the same
run:

> In the batch `[form_input, computer(left_click on the Search submit button),
> get_page_text]` the settle did NOT engage: the `get_page_text` returned the
> old index page verbatim while its own readiness banner said "1 network
> request(s) in flight (main_frame)". In the later batch
> `[computer(left_click on a link), get_page_text]` the settle DID engage and
> reported "waited 344ms for the navigation step 0 started".

**This is #63's recorded race, confirmed a second time and sharpened.** #63
wrote it as: *"`_settle` is asked before every step from `i > 0`; it asked
before `get_url` and answered idle, and `get_url` one round trip later reported
IN FLIGHT. #51 deliberately ASKS rather than predicts, and this is the cost:
`onBeforeNavigate` can land in the gap between the probe and the step it
protects, and two ops over one socket cannot be made atomic."*

What is new is that it was not flaky — a link click was caught and a submit
click was not, in the same session on the same site. That suggests a mechanism
rather than pure chance, and gives a testable hypothesis: **clicking
`input[type=submit]` announces its navigation LATER than clicking an `<a>`,
because form validation and serialization sit between the mouseup and
`onBeforeNavigate`.** Unverified.

**Candidate fix, recorded and not built.** The batch already tracks `_acted` —
whether an earlier step named a ref and ran. When the previous step ACTED and
the probe answers idle, that is precisely the case where the announcement may
not have landed yet, and a second lookup a moment later would close it. The
objection is that "a moment" is a chosen number, which is the thing this
codebase removes from paths that decide things. The counter is that it is a
grace period for an EVENT to arrive, not a threshold for judging readiness, and
it would be bounded by the step having acted rather than applied to every step.
**Measure first: how long after a trusted click on `input[type=submit]` does
`onBeforeNavigate` land, against the same for an `<a>`?** That number decides
whether this is a grace of 5ms or of 200ms, and the second would not be
acceptable.

**It failed loud, as designed.** The readiness banner named the in-flight
`main_frame` request, which is the only reason the stale read was caught rather
than answered from. Cost: one round trip.

## T11/cic — cb 6, cic 7. #46 reported in its own words for the FIFTH time.

Both correct (`(exact)`).

> `navigate` inside `browser_batch` requires an explicit tabId, so
> `tabs_create_mcp` could not be fused with the first navigate and the tab id
> had to be learned in its own turn

Five sightings now across three evals (#47's T8; this eval's T5, T6, T9, T11),
from five different agents, none prompted to look for it. #46 argued
structurally that no docstring could remove a turn the plumbing required, and
chose a structural check over the A/B that had been planned instead. This is
what that check was predicting, observed five times.

**Their second note is about naming and is worth sitting with, because it is a
question we could be asked about ours.** Their `find("search box input field")`
returned the NIST search input as `textbox "(unnamed)"` with no name and no
placeholder, so the only confirmation available was the surrounding form. Our
answer to that shape is `near=` (#37 — assigned only where it DISCRIMINATES,
dropped when every candidate would carry the same string) plus `(post-key)`
(#41 — the HTML `name` attribute shown as what the field POSTS under, marked so
it is not mistaken for a label). Whether ours actually named that specific
field is not established by this run and should not be claimed from it: our arm
reached the field by a different route and never printed it.

## T12/cic — the wrong-tab defect did real damage, and a confound I have to declare

cic 5 turns, correct.

> `navigate` called without a tabId hijacked a PRE-EXISTING unrelated tab
> (tabId 1711644948, which held "Olympedia – Marathon, Men") instead of
> creating a new one, **destroying that page**. The same result then asserted
> "Tabs in this group were opened for this task and are yours to clean up" —
> false for that tab, and **acting on it would have closed a tab belonging to
> the user.**

Second time in this eval (T9 was the first) and the worse of the two, because
the message that followed the hijack invited the agent to close someone else's
tab. It also contradicted itself inside one result: the "Available tabs" list
showed that tab already at the Met URL while the `tabs_context_mcp` block in
the SAME output still showed it as Olympedia.

**THE CONFOUND, declared rather than buried.** The tab it destroyed was left
open by T9 of this eval, because my prompt says "Do not close any tab you did
not open". So my protocol accumulates tabs, and an accumulated tab is something
only an arm that navigates the ACTIVE tab can trip over. Three things about
that, and the third is why I am not changing the protocol:

1. It did **not** cost turns here — 5 is a good run — so it has not moved any
   number in this eval.
2. The defect does not require accumulation. In a browser holding one tab, a
   tabId-less `navigate` hijacks the user's only tab just the same. The
   leftovers make it VISIBLE, they do not make it happen.
3. Changing the protocol after 12 pairs is the move that invalidates a
   pre-registration. It stays as written, and this paragraph stands instead.

What I will not claim: that this is evidence about turns. It is evidence about
a user's tabs, which is a different and in some ways more serious thing, and it
belongs in the qualitative half of the write-up rather than the table.

## T13/cb — E4-D10: two contradictory state flags for one node, and the rule is right

cb 7 turns, correct (Child 1 and Child 2).

> After Root 1 was successfully expanded, `read_page` still flagged its anchor
> row `ref_151 | a "Root 1" role=treeitem (collapsed)` while the toggle on the
> row above read `ref_150 | i (expanded)` and the two children were listed
> nested beneath it — two contradictory state markers for one node in one
> listing.

**Checked the derivation rather than accepting the agent's diagnosis.** It
proposed that we derive the anchor's state from the wrong element. We do not:
`collapsed` is strictly `el.getAttribute('aria-expanded') === 'false'` ON THAT
ELEMENT (`background.js`:8968), which is what ARIA says — an ABSENT
`aria-expanded` means not-expandable, never collapsed, and we correctly print
nothing in that case. So each flag is individually spec-correct and the
contradiction is in the page.

**But the representation question survives the diagnosis, and it is the right
one for this project.** Our listing printed two contradictory states for one
visual node and said nothing about it, so the reader had to go and verify a
third way. We already hold the fact that resolves it: **the element declared
`aria-expanded="false"` while kept descendants of its own subtree were being
listed underneath it.** That is a containment check against our own output, not
a guess about the widget, and it is exactly the shape of rule this codebase
prefers — provable from two things we already have, no framework name, no
threshold.

**What is NOT yet established, and must be before anything is built:** whether
the anchor really still read `aria-expanded="false"` after the expand, or
whether that row came from a read taken before it. The agent's own run had a
mid-build race in the same batch (its defect 2), so a stale row is live
possibility. Resolving it means looking at the real DOM on that page, which
needs the browser, which is busy.

Queued as **E4-D10**, with the measurement first: on jstree.com after an
expand, what does the anchor's `aria-expanded` actually say?

**Its second defect is the known one.** `query_elements("#demo_root_1 > ul >
li > a.jstree-anchor")` returned no match while a broader selector in the SAME
batch returned both children — the settle covering document commit and not
content arrival, which is E4-D5 from T8. Same mechanism, third sighting.
Banner fired and said not to conclude absence, which is why it cost a round
trip and not an answer.

## T13/cic — WE LOSE THIS ONE, 7 to 5, and their report partly dissolves E4-D10

Both correct (Child 1, Child 2). First decided pair against us in this eval.

**The loss is ours and the cause is not the representation.** Our 7 turns
included one read that landed mid-load and one DOUBLE-CLICK on the anchor that
did not expand the node, costing a `read_page` to find the real toggle arrow.
Their 5 had neither. No part of our extra spend was the listing failing to
carry something.

**And their note reframes E4-D10 substantially:**

> on the jsTree demo page's "Basic AJAX demo" tree, **Root 1 is already
> expanded by default on page load** — its `<li>` carries class "jstree-open"

If Root 1 is open when the page loads, our agent's double-click plausibly
CLOSED it, and the later toggle click re-opened it. A read taken anywhere in
that sequence would legitimately show a transitional or genuinely-collapsed
anchor. So the contradictory pair our agent reported is at least as consistent
with "the node really was mid-toggle" as with a derivation defect, and the
derivation is already confirmed spec-correct.

**E4-D10 downgraded from a defect to a question**, and the question is still
only answerable by looking at the live DOM. What would make it a real defect:
the anchor reading `aria-expanded="false"` on a SETTLED page whose subtree is
rendered. Nothing observed so far establishes that.

**Where our representation did win, and it did not show up in the turn
column.** Their scoped read on the same node could not answer the question it
exists for:

> `read_page(ref_id="ref_28", filter="all")` on the "Root 1" treeitem returned
> only the anchor plus one "presentation" child — **no subtree at all** — so
> the one tool aimed at the parent/child question could not answer it; I had to
> fall back to `javascript_tool`.

Ours nested the two children under the parent in the ordinary listing, which is
what #27's tree format is for. They still won the pair, because our agent spent
its advantage elsewhere. **That is the honest shape of this result and it is
worth more than the table row**: a better representation does not win a task by
itself, and reporting a loss as a loss is what makes the wins mean anything.

Their defect (1) is the wrong-tab hijack for the THIRD time in this eval,
destroying the Met page from T12 this time, with the same false "yours to clean
up" footer.

## T14/cic — three defects, and each one names a thing this project built

cic 10 turns, correct (29 strokes, On ウツ).

Their agent's three, in its own words:

1. > `get_page_text` returned "No text content found. Page may contain only
   > images, videos, or canvas-based content." on a fully text-rich jisho.org
   > search results page — wrong and misleading, and **it failed identically
   > after a 2s wait, so it was not a load race.**

   A false absence asserted with a CAUSE attached, and the cause is wrong. That
   is the exact class C15 was built to catch in our own output (#33: a note
   that picks a cause, after three incidents — the stale-ref message asserting
   a navigation, the cross-extension message asserting an impossible recovery,
   the aria-hidden note concluding "most likely a CLOSED menu" with an open
   menu two rows below). Ours now states the fact and lists causes as causes.

2. > `read_page` spent roughly **10,000 characters of its budget emitting ~270
   > empty `listitem` entries** from the radical-picker widget, which pushed
   > the actual kanji entry past the truncation boundary.

   This is the single clearest example in the whole eval of what the listing
   work is FOR. We have three separate answers to that shape: #7 compacts an
   ARIA grid or listbox of 10+ cells to one `mmid:label` mapping line, #27's
   tree folds identical sibling subtrees positionally, and #13 makes truncation
   drop the legend before it drops rows and report how many elements it could
   not show. Their budget was consumed by content that carries no identity and
   the thing being looked for fell off the end **without the result saying so**.

3. > `find` located the "On:" label and the "On reading compounds" heading but
   > **returned no values**, so it could not answer the question.

   Ours hit this in #11(b): find emitted ONE unlabelled quoted string that
   could be a name, a value, a placeholder or text, and on Baidu an agent read
   a placeholder as the field's contents. It now uses read_page's
   `name=`/`value=`/`placeholder=`/`src=` vocabulary.

**The honest caveat before any of this is used as a claim:** these are their
defects on one page, and our arm's number for the same task is not in yet.
Three of their failures matching three things we fixed is a good story and is
NOT evidence our listing handled this page well. That is decided by what our
own run cost, which follows.

## T14/cb — 2 turns against 10, the widest margin in the eval

One `browser_batch`, one read, answered. No blockers, no defects.

So the three failures their arm had on this page (a false "no text content" on
a text-rich page, ~270 empty `listitem` entries eating 10,000 characters of
budget, and `find` returning labels with no values) are now paired with a run
that did not meet any of them. **That makes the comparison on this page fair to
state** — the caveat written one section above is discharged by our own number
rather than assumed away.

It is also the best single illustration in the eval of what the listing work
buys, because the page is adversarial in exactly the way the work anticipated:
a Japanese dictionary whose radical-picker widget is hundreds of identity-free
cells sitting between the agent and the answer.

**One thing in our own result worth not over-reading.** The readiness banner
fired with "THE DOM IS STILL CHANGING, 128 structural changes" on a read whose
content was complete, and the agent said so explicitly: it cost no round trip
and did not mislead. That is a fourth data point for **E4-D7** — the banner
firing on a post-navigation read where the page was in fact usable. Useful
here, arguably noise, and still unmeasured. It is now the single most-repeated
observation in this eval and should be the first thing measured when the
browser is free.

## T16/cb — 2 turns, and E4-D7 finally has a SHAPE

Correct (总笔画 12, 注音 ㄉㄧㄥˇ), and the agent additionally caught the trap the
referee planted: 康熙笔画 is 13 and is the Kangxi count, not 总笔画.

**The fifth E4-D7 sighting is the one that explains the other four**, because
this agent said precisely what was wrong with it:

> the readiness banner fired ("THE DOM IS STILL CHANGING ... 21 images still
> loading"), **true of the glyph images but not of the server-rendered info
> table the answer came from**

So the banner is not firing falsely. It is firing DOCUMENT-WIDE about a region
that is not the region being read. On a page whose churn is confined to glyph
images, ad slots or a carousel while the answer sits in static server-rendered
markup, "the DOM is still changing" is true and irrelevant, and a reader who
meets that often enough stops reading it.

**This is already a named, designed, unbuilt thing**: `OPEN.md` item 5 and
`READINESS.md` §5(b) — per-subtree attribution, described as "designed, not
built". #70 chose the kind-split (`40 @style` vs `40 structural`) as the
cheaper answer to the same problem and recorded that scoped attribution was
the proper one. Five independent sightings in one eval is the evidence that it
is worth building, and it converts E4-D7 from "measure whether the banner is
noise" into "scope the banner to what was read". The measurement is still
owed first, because it decides whether this is worth the complexity.

**E4-D4, second sighting.** `navigate` on `www.zdic.net` -> `zdic.net`:

> correctly flagged the host-stripping redirect, but "this is not the page you
> requested" is strong wording for a bare www redirect

T7 saw the same thing for a trailing slash. Two sightings, one shape: a
redirect that differs only by a `www.` prefix or a trailing slash is a
NORMALISATION, and announcing it in the words used for a substantive redirect
costs a re-check every time. Both are decidable from the two URLs with no
guessing. Small, general, and queued.

## T16/cic — cb 2, cic 7. Sixth sighting, and a new ceremony defect beside it.

Both correct.

> `navigate` inside `browser_batch` requires an explicit tabId and **does not
> inherit a tab created earlier in the same batch**, so tab creation could not
> be folded into the batch; that cost one round trip.

Sixth independent sighting across three evals. The sentence is now almost
verbatim #46's own description of the bug it fixed.

Two more from the same run, both fixed-overhead rather than page handling:

> `tabs_context_mcp{createIfEmpty:true}` returned two pre-existing tabs from
> unrelated sessions and **created nothing**, so a separate `tabs_create_mcp`
> call was still needed — the flag's name suggests otherwise.

> `tabs_close_mcp` was not in the core ToolSearch set the skill recommends
> even though the same skill **mandates closing tabs you opened**, costing a
> second ToolSearch.

The second is the shape #45 found on our side and closed through
`instructions=`: the guidance an agent reads BEFORE choosing tools has to name
the tools its own rules will require, or the agent pays a round trip learning
them. Worth noting ours could regress the same way — C20b exists precisely
because our `instructions=` names eight tools in a `select:` line, and a rename
would turn it into a request for a phantom.

**Running ceremony totals, which is the cleanest number in the whole eval:**
16 tasks in, our arm has spent **0** turns on tab discovery or creation and
theirs has spent **11**. Nothing in either prompt mentions tabs. #45 could not
separate that cost from its own prompt mandate and downgraded the claim to a
measurement design; #46 argued structurally instead that the plumbing, not the
wording, was what forced the turn. This eval's prompt says nothing about tabs,
and the gap is 11 to 0.

## T17 — cb 6, cic 8. E4-D2 confirmed precisely, and it is #18's asymmetry again.

Both correct ($500). The jQuery UI slider demo runs in a CROSS-ORIGIN iframe.

> `read_page` surfaced the iframe's input and slider handle as ordinary refs
> (ref_448, ref_450) and its earlier page-text trailer explicitly said
> "read_page DOES reach them"; `query_elements`, run moments later on the same
> page, reported "No element matches … in the rendered document. The selector
> itself is valid."

So two observation tools, one page, one instant, opposite answers about whether
an element exists. That is exactly the asymmetry #18 measured at 60% of an
accuracy gap (`isInteractive` and `keepForFind` disagreeing about what a
control is), and #30 and #48 each found another instance (`near=` and
`include_text` not migrated to the composed walk). This is the fourth.

**Credit where the message did its job**: the agent noted the cause list DID
include "it is rendered by a frame this query did not reach", so it was not
misleading and it did not produce a wrong answer. But the HEADLINE sentence
reads as absence, and nothing in the tool's description warns of the limit
before you spend the call. Cost: one round trip.

The fix shape is already proven elsewhere in the codebase — the cross-origin
collection path (`collectCrossFrames` + `resolveFrameSelector`) exists and
`read_page` uses it. `query_elements` was simply never migrated. Queued as
**E4-D2**, now with a precise reproduction.

**Sixth E4-D7 sighting, and the most damning one**, because the page is static:

> the readiness banner reported "THE DOM IS STILL CHANGING" on all three early
> observations of a **static demo page** (77 structural changes on first load,
> then 45, then 7 + 10 @style) — each read was in fact usable and correct, so
> it fired without changing what I did.

Decaying counts across three reads is consistent with parse plus jQuery UI
initialising its widgets, so the signal is measuring something real each time.
It still fired three times on a page that was usable every time. Six sightings
now, and together with T16's "true of the glyph images but not of the table I
read" they point at one answer rather than at the window length: **scope the
signal to the subtree that was read** (`OPEN.md` item 5, designed, unbuilt).

## T19/cb — E4-D11, THE MOST IMPORTANT FINDING IN THIS EVAL, and NOT YET VERIFIED

cb 6 turns, correct (Noble gases; 2, 8, 18, 8).

> `find` could not reach the periodic-table cells even though they ARE
> actionable — clicking ref_922 selected Krypton and populated the panel, so
> the cell responds to clicks, yet find reported "No elements matched Krypton"
> and its census (383 elements: 153 li, 62 div, 59 input, 43 a, 34 select,
> 22 svg, 3 img, 3 text…) **accounted for none of the 118 element tiles.**

If that reading is right, it contradicts the strongest claim this project
makes. `lost_identities = 0 across 32 sites` (#36) means **no rendered,
visible, not-declared-hidden control has its name absent from the listing**.
118 clickable element tiles missing would be a direct counterexample, and
`ptable.com` is not in the 32-site corpus.

**I am NOT recording that as a finding, because two readings fit the same
evidence and I cannot separate them from here:**

- **(a) a real existence failure** — the tiles are not collected at all.
- **(b) a NAMING miss, not an existence miss** — the agent acted on `ref_922`,
  an `<em>` INSIDE a cell, so something in that cell WAS collected. A tile
  renders the symbol `Kr` and the number `36`; the word "Krypton" may appear
  only in a title, a hidden label, or not at all. Then `find("Krypton")`
  correctly finds no match on the collected NAME while the element exists, and
  `search_page` wins because it greps RENDERED text. The census's `153 li` is
  also large enough to contain all 118 tiles, which would make "accounted for
  none of them" the agent's inference rather than an observation.

(b) is the more likely reading and it is still worth fixing — a tile a human
reads as "Krypton" that we name `Kr` is a findability gap. But (a) and (b)
need different responses and the difference is exactly what #16 says to
re-derive before believing.

**VERIFICATION, to run as the first thing after the eval ends** (it needs the
browser, which is busy):
1. `read_page(ledger=true)` scoped to the table — are the 118 tiles present,
   and if absent, under which of the ten permitted drop rules?
2. `query_elements("[id]", …)` on the tile container — what does a tile's
   markup actually declare, and what is its accessible name?
3. If the tiles ARE listed under names like `Kr`, this is a naming/findability
   item. If they are NOT listed, it is a `lost_identities` counterexample and
   the headline claim needs qualifying in the README the same day.

**Seventh E4-D7 sighting**, and this one is arguably correct: the banner fired
with 213 changes on a post-CLICK read, and the click itself caused the churn.
The agent still cross-checked rather than trusting the read, which is the cost.

## T19/cic — WE LOSE, 6 to 4, and unlike T13 the representation shares the blame

Both correct. Second decided pair against us.

Our 6 included two wasted turns: `find("Krypton")` missed, and the agent's own
follow-up guess `query_elements("#Kr")` also missed. `search_page("Krypton")`
then found it immediately. Their 4 went to screenshots and never asked the
question that failed for us.

**T13's loss was the agent spending its lead. This one is not, or not only.**
`find` is the tool whose entire job is "locate the thing by its label", the
query was the element's own name as a human reads it off the page, and it
returned nothing. Whichever reading of E4-D11 turns out to be right — the
tiles are not collected, or they are collected and named `Kr` — **the tool
that exists for this question could not answer it, and that is a
representation cost, not an agent cost.**

Recording it that way deliberately. The easy move is to file this under "our
agent chose badly" the way T13 genuinely was, and that would be a flattering
misreading of a pair we lost.

Their own defect this round is their tab context contradicting itself inside
one result for the THIRD time (T5, T12, now T19): the "Available tabs" list
showed a tab already at ptable.com while the `tabs_context_mcp` JSON in the
SAME output still showed it as jsTree. Cost them nothing here, because the
agent screenshotted instead of trusting it.
