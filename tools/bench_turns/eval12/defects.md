# Defects reported by eval agents (verbatim, unverified)

Recorded as REPORTS, not findings. #42 retracted two defects that two agents
agreed on; #41 recorded an agent misattributing a marker from a neighbouring row.
Each needs an offline reproduction before it is believed, and that happens AFTER
the runs so nothing touches the browser mid-eval.

## T1/cb — `search_page` returned NO context for a match that fills its element

Reported: `search_page("serialization_failure", context_chars=120)` on
postgresql.org/docs/current/errcodes-appendix.html returned the match with no
surrounding text — `<code> serialization_failure` — on a TWO-COLUMN TABLE ROW
whose sibling cell holds the SQLSTATE code. Also reported "No refs yet", so
there was no ref to scope a follow-up read to. Cost one extra round trip.

Why this is interesting rather than obvious: this is exactly the shape the
ancestor climb exists for (#32's Q1b, #42's "the element's own text cannot
supply the context the caller asked for", #43's one-hop setting — from a CELL
the ROW). From a `<code>` inside a `<td>`, one hop reaches the `<td>`, which is
still only the condition name; the ROW is two hops. #43 set the dial to one hop
because two hops reached the COLLECTION on a list page. A table cell and a list
item are not the same shape, and this is the case where one hop is too few.

DO NOT fix from this paragraph. Reproduce offline against the real markup first
and check what Q1n/Q1n2 (the sibling-leak control) say about a 2-hop climb,
because #43's whole point was that 4 hops quoted the entire page.

## T5/cb — SECOND INDEPENDENT SIGHTING, different site, same shape

`search_page("霞が関")` on post.japanpost.jp returned 76 CORRECT matches, every
one quoted as `霞が関（…） | カスミガセキ(…)` -- the name cell and its kana reading
-- with the POSTAL CODE CELL OF THE SAME ROW never included at context_chars=200.
The record on that page is {code, name, kana}; the climb landed INSIDE it.
Forced a full `get_page_text`.

Two sightings now, two different sites, two different scripts, one mechanism:
**#43 set the climb to one hop on the argument that one hop IS the record ("from
a cell the ROW, from a link the LIST ITEM"). That argument is wrong for a cell.**
From a `<code>` or a text node inside a `<td>`, one hop reaches the `<td>` -- a
SINGLE CELL, which is a FIELD of the record, not the record. The row is two hops.
#43 derived the one-hop rule from LINK cases (aozora, gov.uk), where one hop
genuinely does reach the `<li>`, and generalised it to cells it had not tested.

This is #43's own lesson pointed at #43: one dial set two ways. The fix is almost
certainly NOT "two hops everywhere" -- that reinstates exactly the whole-list
leak #43 removed. It is that the stopping rule should be structural (stop at the
nearest ancestor that is a RECORD: a `<tr>`, an `<li>`, a `<dl>` pair) rather
than a hop count, which is a threshold of the kind #27/#28 removed from the
collector.

STILL REPRODUCE BEFORE FIXING. #42 retracted a defect two agents agreed on.

## T7/cb — THIRD SIGHTING, and it was PREDICTED by the diagnosis above

httpd.apache.org module page. Markup is
`<th><a>Module Identifier:</a></th><td>info_module</td>`.
`search_page("Module Identifier", context_chars=300)` returned
`<a "Module Identifier"@0> Module Identifier:` -- the label alone. From the `<a>`
one hop is the `<th>`, whose entire text IS the match, so the 300 requested chars
produced nothing and the `<td>` holding the ANSWER was never reachable.

Three sightings, three sites, three markup shapes (`<code>` in a cell, a
`{code,name,kana}` row, an `<a>` in a `<th>`), ONE mechanism, and the third was
predicted by the diagnosis written after the second. That is the evidence
standard this log asks for -- a mechanism that predicts the next instance rather
than a count of agents who agreed.

A fourth thing this sighting adds: the hint line said "No refs yet…", which
addresses ACTING on a match. **Nothing anywhere said the climb had stopped
short**, so a caller asking for 300 chars and receiving 21 has no signal that the
number was not honoured -- #22's silent-bound class, in `search_page`'s context
window. Whatever the stopping rule becomes, a context that could not reach the
requested size should SAY so.

Cost across the three: one extra round trip each (T1, T5, T7 all fell back to a
full `get_page_text`). T7 is the one where it plausibly cost the pair.

## RERUN T4/cb — an observation chained after a CLICK races the navigation

`browser_batch([... click(ref), search_page(...)])`: the click triggered a
navigation, the ref-free `search_page` kept running by design (#38), and it ran
against the MID-NAVIGATION page -- returning `No match for
'Bundesdatenschutzgesetz'. 91 text block(s) were searched.` on a page that
plainly contains it.

Why #38's rule does not cover it: Layer 1 (`_terminates`) knows `navigate`
TERMINATES, and #40 made `navigate` wait for the commit. A CLICK that navigates
is not in that set -- it cannot be, since whether a click navigates is not
decidable from its input, which is the whole basis of #38/#42's
"decide from the step's own input" rule. Layer 2 (`page_fingerprint`) is only
taken when the NEXT step names a ref, and an observation names none. So the
observation fires into the gap.

NOT A SILENT FAILURE, and that distinction is the #15 payoff: the result led
with `PAGE IS STILL SETTLING (1 network request in flight)` and said not to
conclude absence from that read, so the agent re-checked instead of reporting
"the string is not there". Cost one round trip rather than a wrong answer.

CANDIDATE FIX, NOT YET MEASURED: after a step that MAY have navigated (a ref
click), a following observation could wait for quiescence the way `navigate`
does. Risk to weigh first: that reintroduces a wait on every click-then-read
batch, which is the commonest batch there is, and #38 priced the whole
fingerprint round trip at ~2-3ms against a ~24ms read -- a settle wait is far
more expensive than either. Measure the wait cost against the false-negative
rate before shipping; do not assume the banner is insufficient, because here it
worked.

## BOTH EVALS, T9/cb — two correct hits that are byte-identical

`search_page("Welsh")` on loc.gov returns `2 match(es)` as two lines identical in
every printed field: same tag, same `@22` offset, same context string. Reported
independently by the first eval's T9 agent (who checked the page and correctly
concluded it renders the table twice) and by the rerun's T9 agent (who stopped to
verify it was not one hit printed twice).

**This is #42's D30 with the fix applied one level too shallow.** D30 was exactly
this complaint -- "silently missing rows and double-reporting others" -- and was
RETRACTED as a count defect and fixed as a PRESENTATION defect by printing
`match@offset`. That offset is the position WITHIN the attributed element, so it
separates two hits inside one `<pre>` (which is what D30 was) and cannot separate
two hits in two different elements, which is this. The count is right both times;
what is missing is any field that differs.

Not costed a round trip in either sighting, but it cost both agents a re-check,
and "I had to stop and confirm the tool was not double-reporting" is the same
trust failure #33 recorded for `find`.

CANDIDATE: the two hits DO differ in their ref (different elements, different
mmids) -- but on a page where read_page has not run there is no ref yet, which is
exactly when this is reported. A document-order index, or the ancestor that
differs, would separate them without needing refs. NOT YET MEASURED; the cost is
a field on every hit line, which #22 priced at 0.297% for markCut and is the
right order of magnitude to check against.

## EVAL 3 T6/cb — THE MODAL BANNER FIRES ON A DIALOG THE COLLECTOR KNOWS IS INVISIBLE

Rijksmuseum. `read_page` emitted `*** A MODAL/DIALOG IS CURRENTLY OPEN ***` for
`ref_73 | aside name="Cookie usage" role=dialog` and SUPPRESSED the page:
"[32 underlying-page element(s) behind the open modal are omitted]". A
screenshot showed no banner on screen at all.

**The contradiction is inside our own output, which is what makes it serious:**
  - `read_page(ref_id=ref_73)` -> "0 elements ... it holds 3 candidate
    element(s), none of which passed the interactivity/visibility filters"
  - clicking its Accept button -> "element [mmid='83'] is not visible"
So the visibility filter correctly rejects the whole subtree, while the
modality pass treats the same node as an open modal. Two passes over one
element disagreeing -- #21's one-concept-two-spellings, in the pass that
DECIDES WHETHER TO SHOW THE PAGE.

Cost ~4 round trips (scoped read, query_elements, a failed click batch, a
screenshot to prove the banner was not there) and it is the expensive half:
suppression hid the real page and sent the agent hunting a dismiss button that
does not exist. #25 added the aria-hidden-siblings signal for Radix; this looks
like a dialog that is present-but-not-rendered satisfying a modality signal
without being checked against the SAME visibility test the collector already
applied to its contents.

## EVAL 3 T6/cb — fill_form typed nothing into a search box and blamed the refs

`<input type="search" role="combobox">` was routed down the DROPDOWN path:
"no option matched \"The Milkmaid\" and no visible options were found", then
**"submit SKIPPED: none of the supplied field refs resolved on this page"**.
That is FALSE -- the debug trail shows the ref resolved and was clicked twice
including a trusted escalation, and the SAME ref worked unchanged on the next
call via computer(click)+type+Enter. The recovery it suggested ("mmids are
per-document ... re-observe with read_page and retry with fresh refs") names a
cause that did not apply, which is the #33/C15 class in a message that C15 does
not scan because the sentence is declarative.

The routing question is the real one: `role=combobox` sent it to the dropdown
path, but `type="search"` is a TEXT input per HTML's own enum -- the same
declared-writability source #40's W21 used. A combobox that is also a text input
must be typed into, not picked from.

## EVAL 3 T8/cb — THE BATCH GUARD TREATS A CSS SELECTOR AS A REF (cost us the pair)

`browser_batch` skipped `fill_form(fields=[{"selector":"#mnuYear1","value":"2012"}])`
after a `navigate`, saying "navigate always changes the page, and this step names
a ref or coordinate planned against the PREVIOUS page". It does not. A CSS
SELECTOR is resolved at dispatch time against the LIVE document -- it is
precisely the ref-FREE way to address a form across a page change, and
`fill_form`'s own docstring advertises selectors in `fields`.

**So the guard contradicts the parameter it is guarding.** #38's rule is "decide
from the step's own input"; the implementation reads `fields` and concludes REF,
because when it was written fill_form's keys WERE refs (#38: "fill_form's fields,
whose keys are refs"). A selector key is the counterexample that rule never had.

FIX SHAPE: a `fields` entry keyed `selector` is not a ref and must not trip the
guard; keyed `ref`/mmid it must. This is decidable from the entry, which keeps
#42's no-whitelist property.
Cost 2 round trips on T8/cb -- and T8 is the pair we LOST, 19 to 18.

## EVAL 3 T8/cb — A BLOCKING JS DIALOG LOOKS EXACTLY LIKE A DEAD EXTENSION

Clicking Go with the model unset raised `alert()`. Every page-script op
(read_page, query_elements, computer, fill_form) then timed out at 30-41s with
"extension did not respond to <op> within 30s ... re-observe with read_page or
get_url first" -- **advising a recovery that is itself one of the ops that
cannot answer.** Nothing named a modal JS dialog as a cause.
`computer(key,"Escape")` reported "Pressed Escape." and did nothing, because CDP
Input cannot reach a JS dialog: a success report for an action with no effect,
the #10/#11/#12 family again. Only `navigate` (worker-level) cleared it.
CANDIDATE: when a page op times out while `get_url`/`sw_info` still answer, the
worker is alive and a blocked renderer is the leading cause -- say so, and
consider exposing `Page.handleJavaScriptDialog`. NOT YET MEASURED.
(Our own system guidance warns agents not to trigger dialogs; this is what
happens when a PAGE raises one unprompted.)

## EVAL 3 T8/cb — two smaller ones
- The hidden-control note recommended "take a computer screenshot ... and read
  again" for controls that are NOT IN THAT DOCUMENT AT ALL (query_elements
  ("select") returned zero on the home page; the form lives on findacar.shtml).
  A recovery that cannot work, recommended first among listed causes.
- `fill_form`'s verdict is true only at the instant of the write: it returned
  ok:true actual:"Toyota", then the page's own async year handler reset the
  select, and the next fill failed with "no option matching Prius" with nothing
  suggesting the make had been wiped. The LISTING had it right
  (`value="Select Make" ... (unselected)`); only the fill_form result disagreed.

## EVAL 3 T11/cb — search_page MISSES A STRING BROKEN BY <br> (clean mechanism)

`search_page("Mean (deg. C)")` returned "No match ... 2834 text block(s) were
searched" on hko.gov.hk's normals page, and `read_page(ref_id=3973,filter=all)`
printed that EXACT header string in its aligned table one call later.

Mechanism, and it is general: the header cell contains a `<br>`, so #39's
post-order walk builds the rendered text as `Mean\n(deg. C)` -- correct, that IS
what the browser renders -- and a query written with a literal SPACE cannot
match it. `<br>` inside a table header is one of the commonest shapes on the
web, and the person searching has no way to know the space they see is a
newline.

**It is also the exact failure mode the tool exists to prevent:** a miss that is
byte-identical to "the page does not say this". The caller asked whether a
string they could see is present and was told no.

CANDIDATE, NOT YET MEASURED: treat a run of whitespace in a NON-REGEX pattern as
matching any whitespace run including newlines (i.e. compile the literal with
`\s+` between tokens). That keeps regex mode exact, changes no true positive,
and is decidable from the pattern. Check the cost against Q1g, which pins that a
newline-anchored REGEX still stops at the <pre>'s own line break.

Second, unexplained: `search_page("Normals")` on climat.htm also returned No
match across 1855 blocks while `query_elements` returned the Normals links in
the SAME batch. Not diagnosed -- do not fold it into the <br> story until it is
reproduced, since the <br> mechanism does not explain a single word.

Minor, same run: a scoped read led with "0 elements — NOT necessarily empty ...
computer(scroll_to) then read again" and then printed the complete table text
directly below it. The advice contradicts the output under it.

## EVAL 3 T15/cb — THE DATA-TABLE HINT AND THE TABLE RENDERER DISAGREE ON COLUMN COUNT

JMA 年ごとの値 page. `read_page`'s data-table hint advertised `ref_94 (155x11)`;
the scoped read of THAT EXACT REF rendered
`--- TABLE (155 row(s) x 28 column(s)) ---`.

Mechanism: the hint counts the header row's `<th>` ELEMENTS; the renderer
EXPANDS COLSPANS. Both numbers are defensible in isolation and only one can be
right for the caller, whose question is "which column do I count across to".
On a table where the answer is the 4th column of a colspanned two-row header,
an 11-vs-28 mismatch is exactly the number that sends an agent to the wrong
cell. The agent re-derived the mapping from the two header rows before trusting
1590.0 -- i.e. it cost a verification, not a wrong answer, this time.

Same class as #35's Q8: a COUNT presented to a caller who asked "how many"
must be the count they can act on. There the fix was to lead with the declared
total when it disagrees with the rendered one; here the two producers are both
OURS and simply have to agree. Colspan-expanded is the actionable one, since
that is what the renderer prints and what a reader counts across.

NOT YET FIXED. Check which other hints derive a shape from header `<th>` counts.

## EVAL 3 T16/cb — THE BATCH GUARD FIRES ON A CHANGE THE BATCH ITSELF CAUSED

`[form_input(search box), click(submit ref_67)]`: the fill opened the input's own
`list=dictL` AUTOCOMPLETE DATALIST, the fingerprint went 1007 -> 1012 elements,
and the click was dropped as STALE. The ref was fine -- reissuing the identical
click in the next call worked first try. Cost one round trip.

**#43 already fixed this exact shape one layer over** and the reasoning carries:
"A click does not invalidate the keystrokes it was issued for ... the page change
was caused by the batch's OWN preceding step" (B5h2). Here a FILL into a form
invalidates a click on that same form's submit button. Filling a field is the
canonical thing you do before submitting; a datalist opening is the page
RESPONDING to the fill, not the page becoming a different page.

Note what is NOT wrong: Layer 2 is doing what it was told -- the element count
really did change. The rule is too coarse, not misfiring. #43's answer was to ask
WHO caused the change; the same question answers this. A candidate shape: a ref
that still RESOLVES and whose element is still in the same form as the preceding
step's target is not stale. Must be measured against B10c, which pins that a
change early in a batch is still caught at the ref step -- the guard has to keep
catching real staleness.

Minor, same run: `navigate` said "the page declares no <title>" for an entry page
that has one (the ~600ms title wait firing before a JS-set title lands, #42's N7
shape); and an off-viewport hint said "the PAGE itself does not scroll vertically"
on a page whose footer is plainly below the fold. Neither cost a call; neither
re-verified.

## EVAL 3 T18/cb — query_elements(include_text) DOES NOT CROSS A SHADOW BOUNDARY

caniuse. `query_elements("ciu-browser-support", include_text=true)` returned only
`<ciu-browser-support ref_337> "Safari"` -- the column heading -- although each
element visibly renders ~6 rows ("3.1 - 13.1 : Not supported",
"16.0 - 26.6 : Supported", ...). A scoped `read_page(ref_id=ref_337)` returned
the cell text fine.

**The two tools disagree about the same subtree**, and read_page is the one that
is right: #29's SH1 taught the NAME path to cross shadow boundaries via
`_deepText`, and #37 extended it, but `query_elements`'s `include_text` was never
migrated -- it is an un-migrated older path, the same shape #30 found in `near=`.
caniuse is the exact site #37 used to justify SH1 ("ciu-version-support ... the
version and the verdict -- the entire content of a support matrix -- on no row at
all"), so this is that fix present in one tool and absent in its sibling.

Cost one round trip, and the dangerous half is that an agent trusting
`include_text` concludes the column holds nothing but a heading.
