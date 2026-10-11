# Flow generality eval — results

8 apps, 8 recording agents run serially, 44 steps, 16 replays. Scored from the
saved `*.flow.json` and from `run_flow`'s own output; no metric here comes from
what an agent said about its own work.

## Against the pre-registered bars

| | predicted | actual | |
|---|---|---|---|
| **M1** replays green | >= 6/8 | **7/8** | **MET** |
| **M2** green again on a second run | — | 7/8 | |
| **M3** a step binding to the WRONG element and reporting success | **0** | **0** | **MET** |
| **M4** witness check fires | >= 1 | 1/8 | MET |
| **M5** defect classes no fixture models | >= 2 | **15** | MET, by a lot |

**P1, P3, P4 and P5 all hit. P2 was wrong**, and usefully: I predicted the
failures would cluster in SPA settle timing, non-reproducible postconditions
and a popup left open. None of those happened. The single failure was a settle
problem of a different kind — a stale pre-navigation url baked into the
recording — and the other two never occurred at all.

## The result in one line

**The part that was measured held. The part that was never measured broke in
fifteen ways.**

M3 = 0 across 8 apps, 44 steps and 16 replays. Every descriptor resolved to the
element it was recorded for — on a React SPA, a Japanese MediaWiki skin that
swaps its search input for a Vue combobox on focus, an ARIA combobox with no
native `<select>`, a client-filtered data table and a docs sidebar. That is the
locator, and it is the thing 37 frozen sites and 2,726 descriptors under six
mutations already said was sound. Eight unseen apps did not contradict them.

Every single defect found is in the LOOP AROUND the locator: what gets
asserted, what gets discarded, and what the tools say about it.

## The one failure, and it is ours

`ev-arxiv-advanced-search` fails deterministically (27s, 28s, identical
message). The batch `[click(Search), get_url, search_page]` asked the settle
probe BEFORE the browser had announced the navigation the click caused, so
`get_url` read the document being replaced — and the recorder kept that stale
read as the step's postcondition. The assertion is wrong, not the app. See D3.

## What an assertion is actually worth, reviewed by hand

Across 44 steps the flows carry 26 `query` assertions, 10 `url` and 8 `search`.
Of the 26 query assertions, **six assert something that cannot change**:

| flow | step | assertion | why it cannot fail |
|---|---|---|---|
| apg-combobox | 2 | `#combo1 == 1` | an id matches 1 whatever it displays — **verified live on an untouched page** |
| apg-combobox | 4 | `#combo1 == 1` | same |
| httpbin-form | 1 | `input[name="custname"] == 1` | the field exists whether or not it was typed into |
| arxiv-search | 1 | `input#terms-0-term == 1` | same |
| jawiki | 2 | `input[name="search"] == 2` | same |
| datatables | 5 | `select option:checked == 1` | a single-select always has exactly one |

Counted by hand, deliberately: an automated rule got this wrong in BOTH
directions on the first attempt — it called `.todo-list li == 1` then `== 2`
vacuous (it is not; the count moves with the action) and called
`select option:checked == 1` falsifiable (it is not). A measurement that needs
judgement should say so rather than be dressed up as a metric (#16).

**Three of the six are attached to a TYPING step** — httpbin 1, arxiv 1,
jawiki 2 — so those steps are reported as "asserted" while nothing about what
was typed is checked. That is D1 and D17 meeting: the one action a UI test
performs most often is the one this feature cannot verify, and the attempt to
verify it produces an assertion that always passes.

## The defect list

Full write-ups in `FINDINGS.md`. Ranked by what they cost:

| | defect | sightings |
|---|---|---|
| **D13** | a DISAPPEARANCE cannot be asserted — zero is falsy, so "it's gone" is discarded | 1, decisive |
| **D17** | `query_elements` compiles to selector+count; the text that was read is thrown away | 2 |
| **D1** | `query_elements(attributes=["value"])` reads the ATTRIBUTE, so a typed value is invisible | 3 apps |
| **D3** | the settle races the navigation's ANNOUNCEMENT, and the stale read is baked in | 1, caused the only failure |
| **D5** | `expect` has one slot per kind and `setdefault` keeps the FIRST | 2 |
| **D14** | `settle_ms` measures the AGENT's turn, not the page's — corrects #60 | 1 |
| **D10** | `navigate` reports a REDIRECT that did not happen, on every non-ASCII url | 1 |
| **D11** | `get_url` escapes non-ASCII to `\uXXXX` — 4th instance of one bug | 1 |
| **D15/D4** | a `search_page` miss never considers a character-level mismatch (en dash, curly quote) | 2 apps |
| **D18** | `query_elements` and `search_page` disagree about one element's text by a space | 1 |
| **D7** | a call that warned and changed nothing is recorded as a STEP | 1 |
| **D6** | an integer option value arrives as a float and matches nothing | 1 |
| **D9** | the stop message does not say WHICH steps ended up unasserted | 3 agents |
| **D16** | every ref click reports the same coordinate | 1 |
| **D19/D20** | a scroll direction nobody can interpret; a TOC reachable only via `mmid:label` prose | 2 |

Three of these land on work shipped the same day: D14 corrects #60, D11 is in a
function #61 edited two hours earlier, and D7 is #62's refusal guard needing a
seventh marker and a second home in the recorder.

## What this eval cannot say

- **Nothing about the consent model.** AMENDMENT 1 armed the gate off for the
  run. Per-origin granting was not exercised and must not be quoted from here.
- **Nothing about long flows.** The longest recording is 7 steps.
- **Nothing about flows that mutate shared state.** Every app was read-only,
  localStorage-only, or echoed a POST back to the caller — chosen that way on
  purpose, so teardown and idempotence under real mutation are untested here.
- **n = 8.** The shapes were varied deliberately, but eight apps is eight apps.
