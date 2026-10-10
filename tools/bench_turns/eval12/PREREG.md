# PRE-REGISTRATION — the turns eval
# Written BEFORE the tasks existed and before any run. Nothing below is revised
# after data. #40's precedent: the bar was fixed first precisely because earlier
# the same day I had called a genuine 8/8 "drift" and then had to reverse it.

## What is under test

Two changes shipped this session, both ChromeBridge-only:
  #45  MCP server `instructions=` set for the first time (we had none; the other
       arm has always shipped them). Says: batch ToolSearch into ONE call, chain
       with browser_batch, which tool answers which question.
  #46  browser_batch threads a tab created by `tabs_create_mcp` into later steps
       that name no tabId, so [create, navigate, read] is ONE turn. Before this
       it was not merely slower -- it drove the USER'S OWN tab.

The other arm's code is UNCHANGED, so it measures drift directly (#41's design,
which #35 wanted and the two earlier benchmarks lacked).

## THE CONFOUND THIS EVAL EXISTS TO REMOVE

Every prior eval used `bench25/PROMPT_TEMPLATE.md`, which I wrote, and which
ordered every agent:

    1. Call tabs_context_mcp ... as a call ON ITS OWN (do not batch it with
       anything).  2. Call tabs_create_mcp as a call ON ITS OWN.

So the tab ceremony those evals measured was MANDATED BY THE HARNESS. Split by
whether a run's prompt carried that mandate, `tabs_create_mcp` ran 1.02/run where
named and 0.05/run where not. **The prompt here says NOTHING about tabs.**

That mandate existed for a real reason -- #39 records six parallel agents
corrupting each other's tab groups -- so isolation is solved OUT OF BAND
instead: runs are STRICTLY SERIAL, one agent at a time. A harness problem gets a
harness answer, not a product requirement.

## Primary metric: TURNS

Tool calls per run, counted from the transcript, NOT self-reported. Wall clock is
NOT the primary metric: #35 and #41 measured a ~47s/task drift floor that
swallows real changes, and #35 records the control arm improving 47s on unchanged
code.

## PRE-REGISTERED BARS — fixed now, not moved later

  H1 (head-to-head, the standing question): paired two-tailed exact sign test on
     DECIDED pairs (ties dropped). At n=10, 9/10 gives p=0.021 and 8/10 gives
     p=0.109. **BAR: 9 of 10 decided pairs.** Below that is reported a TIE,
     whatever the totals look like.

  H2 (the ceremony, which is what #45/#46 actually target): turns spent before
     the first call that returns PAGE CONTENT ("turns-to-first-content").
     **BAR: ChromeBridge median <= 2 AND strictly lower than the other arm's
     median.** Pre-registered as a median because one stuck run should not carry
     it.

  H3 (did the shipped path get used at all): the fraction of ChromeBridge runs
     whose FIRST browser call is a browser_batch containing tabs_create_mcp.
     **This is descriptive, with NO bar** -- it cannot fail the eval, it explains
     H2. A high H2 with a low H3 would mean agents found a different short path,
     which is a finding, not a failure.

  CORRECTNESS is expected to saturate and CANNOT discriminate: both arms are the
  same model, so the ceiling is Claude's, not the tool's (#41, 60 runs, 30/30
  each). It is recorded as a FALSIFIER, not a win condition: **if ChromeBridge
  correctness drops below the other arm's, the turn saving is rejected outright**,
  because fewer turns bought by a wrong answer is not a saving.

  FALSIFIER, specific to #46: any run reporting a wrong-tab error, or acting on a
  tab it did not create. One such event rejects the threading change.

## Design

  - 10 tasks, written by an agent told only "write 10 two-hop browser tasks",
    with no knowledge that any toolset is under test, and given a deny-list of
    domains over-used in prior evals.
  - Ground truth established INDEPENDENTLY of the task writer and of both arms.
  - STRICTLY SERIAL. Arm order ROTATED per task (odd tasks CB first, even tasks
    the other arm first) so run order cannot align with arm (#19: a
    block-structured A/B measures drift, not behaviour).
  - Identical prompt both arms except the namespace. NOTHING about tabs.

## Known limits, stated before the numbers

  - n=10 is small; the bar is set accordingly.
  - Both arms are the same model, so this measures the REPRESENTATION and the
    TOOL SURFACE, not reasoning.
  - #39 recorded the instrument's ceiling: when both arms solve a task in one
    batch there is nothing left to differ about. Two-hop tasks are the attempt to
    stay above that floor; if most pairs come back tied at the same turn count,
    the honest report is "the instrument could not discriminate", not a tie that
    sounds like parity.
  - The tasks are live sites. A site that is down or has changed invalidates that
    PAIR, not the run that happened to hit it.

---

# AMENDMENT 1 — made after GROUND TRUTH, before ANY run exists

No run has been executed. No outcome data exists. This amendment is therefore a
design decision, not a selection on results; it is written down so that it cannot
later be mistaken for one.

## T2 is DROPPED: ungradeable as written

The independent referee found NIST's HTML "Frequently used constants" view is a
bare list of NAMES with no symbol and no value column -- symbols exist only in
the gif/pdf renderings. So "find the row whose symbol is k" cannot be performed
in HTML at all; an agent must already know k = Boltzmann. The value page is also
a frameset and the field is labelled "Numerical value", not "Value". A task whose
premise is false measures the agent's prior knowledge, not the toolset.
(The author had flagged T2 and T5 as risky. T5 turned out FINE -- plain
server-rendered lists, opaque city id, a genuine two-hop. The guess about which
was broken was wrong, which is why it was checked rather than assumed.)

n is therefore 9.

## The bar restated exactly, NOT loosened

The pre-registration's bar was "9 of 10 decided pairs", which is the n=10
instantiation of **two-tailed exact sign test, p < 0.05, on DECIDED pairs**. That
test is what carries over, computed exactly at whatever n survives:
    n=10 -> 9 needed (p=0.021);  n=9 -> 8 needed (p=0.039);  n=8 -> 7 (p=0.070,
    FAILS, so at n=8 the bar is 8/8).
Anything short of p<0.05 is reported a TIE, as before.

## THREE TASKS ARE MARKED WEAK, with a PRE-SPECIFIED sensitivity analysis

T1 (`errcodes-appendix.html`, 40001), T8 (`sqlite.org/changes.html`) and T9
(`code_list.php`, wel/cym) have hop-2 URLs that are fixed, famous, and plausibly
in the model's memory -- an agent could skip page 1. #39 recorded the instrument's
ceiling precisely here: a comparison cannot discriminate on a task both arms can
shortcut. They are KEPT, because dropping them would also drop whatever they do
measure, and the analysis is pre-specified instead:
    PRIMARY    all 9 tasks
    SECONDARY  the 6 strong ones (T3, T4, T5, T6, T7, T10), whose hop-2 URLs are
               opaque, POST-only, or require a real search/mapping step
Both are reported whatever they say. If they disagree, that disagreement IS the
result and gets reported as such rather than the friendlier of the two.

## Grading hazards recorded in advance, so scoring cannot drift

  T5  the label is `霞が関（次のビルを除く・霞が関ビル）` = 100-0013; ~30 building-floor
      rows `霞が関霞が関ビル（N階）` = 100-6010..100-6090 are NOT the answer.
  T6  an identically-titled Verne audiobook record exists at ebooks/28947.
      Accept 103 only.
  T8  3.8.0.1 (2013-08-29) and 3.8.0.2 (2013-09-03) are distractors.
  T9  `cy` on the same row is a distractor; B=wel, T=cym.
  T10 the TOC also lists "15.5.14 The meter element" (rendering.html, no Content
      model); the `button` element on the same page has a similar longer line.
  T3  female rank 1 = Jessica is the wrong-column distractor.
  T4  "30. Juni 2017" appears in the Vollzitat; only 30.06.2017 is correct.

---

# AMENDMENT 2 — the per-origin gate is OFF for the duration of these runs

Still before any run. No outcome data exists.

All 9 task origins (postgresql.org, ssa.gov, gesetze-im-internet.de,
post.japanpost.jp, gutenberg.org, httpd.apache.org, sqlite.org, loc.gov,
html.spec.whatwg.org) are ungranted, so the FIRST navigate of every ChromeBridge
run would be refused until a human clicked Allow in the side panel. That refusal
is the consent model working (CLAUDE.md "Permission model": connected is not
allowed, and the first op on a new origin is SUPPOSED to fail).

`ALLOW_ALL_ORIGINS` is therefore set `true` in `extension/background.js` for the
duration of this eval and restored to `false` immediately afterwards. The
precedent is #39, which armed the same flag so the permissions suite could
exercise the claim it asserts, then restored it.

WHY, stated so it is not mistaken for convenience: the metric is TURNS. Per-origin
consent is a ONE-TIME, PER-ORIGIN, PER-USER cost paid once in a real installation
and never again -- it is not a per-task turn cost. Counting it here would charge
ChromeBridge nine times for a deliberate security feature the other arm does not
have at all, and would measure the consent model rather than the thing #45/#46
changed.

WHAT THIS GIVES UP, stated plainly: this eval therefore says NOTHING about the
cost of the consent model, and must not be quoted as though it did. A user meeting
these nine sites for the first time pays nine Allow clicks that these numbers do
not contain.

While the flag is true, `node tools/test_permissions.js` reports its origin checks
as "not-applicable (gate off)" and the loaded extension is NOT "default deny, per
origin". The suite saying so on every run is how #32 caught the flag having been
left armed; the restore is verified by that suite reporting 22/22 again.

---

# SCORING CLARIFICATION — made after run 1 of 18, recorded because it is a change

`score.py` counted `SubagentHandback` -- the harness's own reply mechanism -- as
a turn and a call, so run 1 scored 5 against a self-reported 4. Excluded now.

This is stated rather than done quietly because changing an instrument after data
exists is exactly the move that invalidates a pre-registration. It is admissible
here for a reason that is checkable rather than asserted: the handback appears
EXACTLY ONCE in EVERY run of BOTH arms, so it is a constant added to both sides
of every pair. It therefore cannot change the direction of any pair (H1), cannot
change `first_content_turn` (H2, which is an index of an EARLIER turn), and has
nothing to do with H3. It changes only the absolute turn total, which it was
making wrong.

If that reasoning is ever found not to hold -- e.g. a run that hands back twice
-- the affected pairs get re-scored both ways and both numbers reported.

---

# AMENDMENT 3 — THE RERUN, with its result PREDICTED before it is run

Written after run 1 of the rerun does not exist. The first eval is complete and
its numbers are frozen above. What changed in between is ONE thing: #47's
`search_page` record-climb fix. The other arm's code is again UNCHANGED, so it
remains the drift control (#41's design).

## This is a PREDICTION, not a hypothesis to be fitted afterwards

The mechanism says exactly where the turns go, so the honest thing is to say so
first and let it be wrong. During the first eval the under-climb forced a
`get_page_text` fallback on exactly three runs -- T1/cb, T5/cb, T7/cb. T10/cb
ALSO hit the defect but had batched the search alongside the call that answered,
so it paid nothing.

  P1  CB drops ~3 turns, 40 -> ~37, and the drop is CONCENTRATED ON T1, T5, T7
      (one turn each). A drop that shows up anywhere else is drift, not the fix.
  P2  T7 goes 4 -> 3 and FLIPS from tie to a CB win.
  P3  T10 does NOT improve (it never paid for the defect).
  P4  CIC stays within drift of 73. It is the control; a large move means
      conditions changed and the comparison is about conditions.
  P5  H2 is UNCHANGED (CB median 2). The fix is post-content and cannot touch
      turns-to-first-content. If H2 moves, something other than the fix did it.

## The bar does NOT move, and the n question is answered in advance

Same test: two-tailed exact sign test, p<0.05, on decided pairs. If T6 ties
again and T7 flips, n=8 and the bar is 8/8 (p=0.0078). If T7 does not flip, n=7
and the bar is 7/7. **A rerun that produces a WORSE result than the original is
reported as such** -- #43 is the precedent, where the rerun of a fix round came
back weaker than its own baseline and that was the finding.

## Known weakness of a rerun, stated rather than discovered later

The tasks are no longer novel to the measurement: I now know what each answer is
and roughly how each arm behaves. The AGENTS are fresh (every run is a new
subagent with no memory of the first eval), so the runs themselves are clean, but
my own expectations are not, which is exactly why P1-P5 are written down BEFORE
the runs instead of being read off the results afterwards.

The per-origin gate is off again for the same reason and on the same terms as
AMENDMENT 2, and restored and verified the same way.
