# THE TURNS EVAL — result

18 runs, 9 tasks x 2 arms, strictly serial, arm order rotated per task. Scored
from TRANSCRIPTS, never from self-reports. Bar fixed in PREREG.md + AMENDMENT 1
before any run existed. ChromeBridge build = post-#46; the other arm's code is
UNCHANGED, so it measures drift directly.

| task | CB | CIC | | CB first-content | CIC first-content |
|---|---|---|---|---|---|
| T1  | 4 | 9  | CB  | 2 | 4 |
| T3  | 5 | 10 | CB  | 2 | 4 |
| T4  | 6 | 10 | CB  | 2 | 4 |
| T5  | 7 | 10 | CB  | 2 | 4 |
| T6  | 5 | 5  | tie | 2 | 4 |
| T7  | 4 | 4  | tie | 2 | 3 |
| T8  | 3 | 8  | CB  | 2 | 5 |
| T9  | 3 | 10 | CB  | 2 | 5 |
| T10 | 3 | 7  | CB  | 2 | 4 |
| **total** | **40** | **73** | | | |

## H1 — PRIMARY: CLEARS THE BAR

**7 of 7 decided pairs to ChromeBridge, 2 ties, p = 0.0156.** The pre-registered
bar is a two-tailed exact sign test at p<0.05 on decided pairs, computed at
whatever n survives. **This is the first of the five head-to-heads in this log to
clear its own bar.** #40, #41 and #39 all reported ties; #43 cleared at p=0.0414
but was WEAKER than its own baseline.

## H1 — SECONDARY (6 strong tasks): does NOT clear, and is UNDERPOWERED

4/4 decided to CB, p = 0.1250. It fails p<0.05 -- but **the best p reachable at
n=4 is 0.1250**, so this subset could not have cleared even with a perfect
sweep, which it got. That is not a disagreement with the primary: the direction
is identical and there are ZERO losses in it. AMENDMENT 1 said a disagreement
would itself be the result; this is an underpowered subset, which is a different
statement, and saying "the secondary failed" without the achievable-p line would
be the more misleading of the two readings.

Stated plainly because it cuts the other way too: T1, T8 and T9 -- the three
tasks marked WEAK for having memorable hop-2 URLs -- are 3 of the 7 wins, and
two of them are the widest margins in the eval (T8 3v8, T9 3v10). The primary
leans on tasks whose shortcut-ability was flagged in advance.

## H2 — MET, and it is the cleanest signal here

turns-to-first-page-content: **CB median 2, CIC median 4.** Bar was "CB <= 2 AND
strictly lower". CB scored EXACTLY 2 on all nine runs -- no spread at all. CIC
ranged 3-5.

## H3 — descriptive, and it fired on every run

**9/9 CB runs opened with a browser_batch containing tabs_create_mcp** (the #46
threading path). **CB spent 0 tab-ceremony calls across all nine runs; CIC spent
6.** H3 explains H2: the entire first-content gap is fixed overhead.

## The falsifiers, both checked

- CORRECTNESS: **18/18 correct, both arms.** Saturated, as predicted (same model
  both sides), so it discriminates nothing -- it was pre-registered as a
  falsifier and did not fire. Every distractor named in advance was avoided:
  Jessica (T3), the Vollzitat date (T4), the ~30 building-floor rows (T5), 28947
  (T6), 3.8.0.1/.2 (T8), `cy` (T9).
- #46 WRONG-TAB: **zero events on the ChromeBridge arm.** (The other arm hijacked
  a pre-existing unrelated tab in 5 separate runs and asserted those tabs were
  "yours to clean up" -- that is their defect, not our falsifier, and the fact
  that it is the SAME defect #46 fixed on our side is the point below.)

## THE INDEPENDENT CONFIRMATION OF #46 IS IN THE OTHER ARM'S OWN WORDS

#45 could not price the tab half of the ceremony because my own eval prompt had
MANDATED it (1.02 tabs_create/run where named, 0.05 where not). #46 then argued
structurally that no docstring could remove a turn the plumbing required. This
eval's prompt says NOTHING about tabs, and the control agent on T8 reported:

> tabs_create_mcp could not be fused with navigate because navigate inside
> browser_batch requires an explicit tabId, so the tab id had to be learned in
> its own turn.

That is exactly the defect #46 fixed, observed live on an arm that still has it,
with no prompt mandating anything. It is the confound-free evidence the #45
transcript-mining could not produce.

## WHAT THIS DOES NOT SHOW

- A large share of the other arm's cost is ITS OWN product defects, not our
  representation: ref clicks reporting success without navigating (3 runs),
  read_page returning an empty listing with `Viewport: 0x0` on loaded pages (3
  runs), find omitting href (2 runs), screenshot timing out at 30s (2 runs).
  Those are real costs to a real user of that tool and belong in a turn count,
  but they are NOT evidence that #45/#46 worked. The evidence for those is H2/H3
  and the T8 quote above.
- Wall clock is not reported as a result. #35/#41 measured a ~47s/task drift
  floor that swallows changes this size.
- The per-origin consent gate was OFF (AMENDMENT 2). This says NOTHING about the
  cost of the consent model; a first-time user still pays 9 Allow clicks that
  these numbers do not contain.
- n=7 decided pairs is small, and 2 of 9 tasks could not discriminate at all --
  #39's instrument ceiling, still present.

## THE DEFECT THIS EVAL FOUND IN OUR OWN CODE, AND IT COST US A PAIR

`search_page`'s one-hop ancestor climb stops INSIDE the record whenever the match
sits in a cell. **Four independent sightings, four sites, four markup shapes:**

| run | markup | asked | got |
|---|---|---|---|
| T1/cb | `<code>` in a table cell, code in sibling cell | 120 | no context |
| T5/cb | `{code,name,kana}` row, code cell never included | 200 | name+kana only |
| T7/cb | `<th><a>Module Identifier:</a></th><td>info_module</td>` | 300 | 21 chars |
| T10/cb | `<dl>`: `<dt>Content model</dt><dd>…</dd>` | 200 | 14 chars |

**The third and fourth were PREDICTED by the diagnosis written after the second**
-- a mechanism that forecasts the next instance, not a count of agents who
agreed (#42 retracted a defect two agents agreed on).

#43 set this dial to one hop arguing "one hop IS the record -- from a cell the
ROW, from a link the LIST ITEM". It derived that from LINK cases (aozora,
gov.uk) and generalised it to cells it had not tested. From a text node inside a
`<td>` or a `<dt>`, one hop reaches a FIELD; the record is two. That is #43's own
"one dial set two ways" lesson pointing back at #43.

Cost: one extra round trip on T1, T5, T7. **On T7 it is the whole margin -- CB
would have finished in 3 and taken the pair; instead it tied at 4.** Our own
defect suppressed the result this eval was measuring.

Second, smaller: nothing told the caller the climb had stopped short. Asking for
300 context chars and silently receiving 21 is #22's silent-bound class alive
inside search_page.

**NOT FIXED YET, deliberately.** #43's process lesson is that 15 fixtured fixes
with no live pass produced 7 regressions. The fix is almost certainly NOT "two
hops" -- that reinstates the whole-list leak #43 removed -- but a STRUCTURAL
stopping rule (climb to the nearest ancestor that is a record: `<tr>`, `<li>`, a
`<dl>` pair), which is the threshold-to-declaration move of #27/#28. Reproduce
offline against all four markup shapes, keep Q1n/Q1n2 green, then re-run.
