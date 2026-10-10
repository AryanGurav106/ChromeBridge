# PRE-REGISTRATION — EVAL 3, the generality eval
# Written BEFORE the tasks exist (the author agent is still running) and before
# any run. Nothing below is revised after data.

## Why a third eval at all

Evals 1 and 2 (CLAUDE.md #47) both cleared: 7/7 p=0.0156, then 9/9 p=0.0039.
Two weaknesses make that less conclusive than the numbers look:

  1. **n is small and fragile.** At n=9 the bar is 8/9, so ONE bad task breaks
     the result. A finding that one task can overturn is not a finding.
  2. **The tasks were all one archetype.** Every task in both evals was a
     two-hop navigate-and-read documentation lookup. That is precisely where our
     measured advantage lives -- the decomposition says 54-58% of the gap is
     FIXED STARTUP overhead, which a navigate-heavy task maximises. A task set
     that only contains the shape we are best at cannot measure generality.
     #25's rule, applied to a benchmark instead of a corpus: an ablation
     measures the code against the sample and cannot measure the sample.

## Design

  - **20 tasks**, written by an agent told only to write varied two-hop browser
    tasks, with a deny-list of every domain used in evals 1-2 and #39-#43, and
    no knowledge that any toolset is under comparison.
  - **7 archetypes, ~3 each**: doc-lookup, search-flow, form-lookup, data-table,
    drill-down, non-Latin, SPA/dynamic. The three INTERACTION-heavy ones
    (form-lookup, SPA, search-flow) are deliberately included because they are
    where our advantage should be SMALLEST.
  - Ground truth established INDEPENDENTLY of the task author, by a referee
    using a headless browser, before any run.
  - **40 runs, strictly serial**, arm order rotated per task (odd tasks CB
    first, even tasks the other arm first).
  - Identical prompts both arms except the namespace. Nothing about tabs.
  - The other arm's code is UNCHANGED, so it is the drift control.
  - Scored from TRANSCRIPTS by `score.py`, never from self-reports.

## PRE-REGISTERED BARS — fixed now

  H1 PRIMARY. Paired two-tailed exact sign test on DECIDED pairs, p<0.05.
     At n=20 that is **15 of 20** (p=0.0414); the test is recomputed exactly at
     whatever n survives ties. **This tolerates up to 5 losses**, which is the
     entire reason for going to 20 tasks: a result that survives losses is worth
     more than a sweep that one task can break.

  H2. turns-to-first-page-content. **BAR: CB median <= 2 AND strictly lower than
     the other arm's median.** This replicated exactly across both prior evals
     (CB median 2 on all 18 runs, CIC median 4), so it is a REPLICATION test: if
     it fails here, the earlier result was task-shape-specific.

  H3. Fraction of CB runs whose first browser turn is a batch containing
     tabs_create_mcp. Descriptive, no bar. Was 9/9 and 9/9.

## THE PREDICTION THAT MATTERS, AND IT IS THE ONE THAT COULD EMBARRASS US

The decomposition of both prior evals says the advantage is ~55% FIXED STARTUP
and ~45% in-task, and that in eval 1 the other arm actually beat us IN-TASK on
2 of 9 tasks. If that is the true picture, then on this task set:

  **P-GEN: the per-archetype margin will be LARGEST on doc-lookup / drill-down
  (navigate-heavy, startup-dominated) and SMALLEST — possibly zero or negative —
  on form-lookup / SPA / search-flow (interaction-heavy, where the startup turn
  is amortised over more in-task work).**

This is registered so it cannot be explained away afterwards:
  - If P-GEN HOLDS and H1 still clears, the honest headline is **"fewer turns
    overall, driven by startup; parity in interaction-heavy work"** -- NOT "we
    are better across the board".
  - If P-GEN FAILS because we win everywhere by similar margins, that is a
    STRONGER result than predicted and says the advantage is not merely startup.
  - If P-GEN fails because we LOSE the interaction archetypes outright, H1 may
    still clear on volume while the general claim does not, and that must be
    reported as the finding.
Per-archetype n is ~3, far too small for significance. It is reported
DESCRIPTIVELY with margins, never with a p-value, and the achievable-p line is
printed beside every test so an underpowered stratum cannot be read as a null.

## FALSIFIERS

  - CORRECTNESS: expected to saturate (same model both arms; 36/36 across evals
    1-2). **If CB correctness drops below the other arm's, the turn result is
    rejected outright** -- fewer turns bought by a wrong answer is not a saving.
  - WRONG TAB: any CB run acting on a tab it did not create rejects #46.
  - A task whose premise is false (the page does not contain the field) is
    DROPPED, and dropped BEFORE its runs if the referee catches it, exactly as
    T2 was in eval 1. Dropping after seeing results is forbidden.

## Known limits, stated before the numbers

  - Both arms are the SAME MODEL, so correctness saturates and this measures the
    tool surface, not reasoning.
  - **The instrument is noisy**: evals 1-2 measured single tasks swinging 4-5
    turns between identical runs on unchanged code. n=20 is partly a response to
    that. Aggregate totals are reported with that caveat and per-task deltas are
    NOT attributed to anything without a pre-registered mechanism.
  - The per-origin consent gate is OFF for the runs, on the same terms and for
    the same reason as eval 1's AMENDMENT 2, and restored and verified after.
    **These numbers therefore say NOTHING about the cost of the consent model.**
  - Live sites. A site that is down or has changed invalidates that PAIR.

---

# AMENDMENT 1 — after REFEREE, before ANY run. No outcome data exists.

## T7 DROPPED — false premise, exactly the T2 case from eval 1

`sec.gov/cgi-bin/browse-edgar?action=getcompany` returns HTTP 200 whose body is
"The value you submitted is not valid. Please try a different selection." —
zero <form>, zero <input>. The task says "In the EDGAR company search form…";
there is no form. Confirmed three ways by the referee (two UAs + WebFetch).
Secondary: sec.gov 403s declared-automated traffic. NOT patched to a different
start URL, because the referee could not render the replacement either and a
task nobody has walked is how T2 happened.

## T18 REWORDED — ambiguity removed BEFORE data, answer unchanged

The task asked for the first Safari version "listed as having FULL support".
The support table colours 14–15.6 Partial and 16.0 Supported, BUT footnote 3 on
the same page reads verbatim: "Safari 14.0 – 15.6 has full support of WebP, but
requires macOS 11 Big Sur or later." An agent that reads the footnotes — which
is CAREFUL behaviour, not careless — can defensibly answer 14. A task with two
defensible answers measures which agent read the footnote, not which toolset is
better. Reworded to key on the declared legend instead of the phrase:
  "...report the first Safari (desktop) version whose cell is GREEN (Supported)
   in the support table — not the greenish-yellow Partial ones."
Answer is unambiguously 16.0 and the Safari-14 trap survives. Recorded rather
than silently edited, because rewording a task after seeing it is a liberty and
only permissible before any run exists.

## n = 19, and the bar recomputed exactly

Two-tailed exact sign test, p<0.05, on decided pairs:
  n=19 -> 15 needed (p=0.0192);  14/19 = 0.0636 FAILS.
**This tolerates 4 losses.**

## THREE TASKS MARKED WEAK, with a pre-specified sensitivity analysis

T5 (Companies House), T16 (MOE dict), T17 (Korean dict): in each, the SEARCH
RESULTS page already prints the answer, so the final "open the entry" click is
optional and the task is one hop in effect. They satisfy the stated criterion
(the answer is not on the START page) so they are KEPT, but the analysis is
pre-specified now, as eval 1 did for its three weak tasks:
    PRIMARY    all 19
    SECONDARY  the 16 strong (all but T5, T16, T17)
Both reported whatever they say.

## Referee notes carried forward, NOT changed

  - T14's path is one level deeper than the task implies (Felidae -> Felinae ->
    Felis -> nigripes; the Felidae record's direct children are the two
    subfamilies). The task names a DESTINATION, not a path, so it is left as
    written — discovering the intervening subfamily is legitimate navigation.
  - T17's "원어" is not a visible field label; the Hanja renders as 학교(學校)
    beside the headword. The task's "(the Hanja origin)" already disambiguates.
  - T10: an agent may open "Uranus Fact Sheet" first, which has NO "Mean
    Temperature (C)" row but does print -197 C. Row+column wording disambiguates.
  - T19 (PubChem) and T13 (legislation.gov.uk) serve bot walls to headless
    clients; both render in a real browser, which is what both arms use.
  - T20's answer exists in the start page's raw HTML inside a preloaded JSON
    blob, but is NOT rendered text — so a text search of the start page will not
    surface it, while a javascript_tool/view-source approach could. Noted
    because it is a legitimate path difference between the arms, not a defect.
