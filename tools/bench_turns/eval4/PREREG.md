# PRE-REGISTRATION — EVAL 4, the interaction eval
# Written BEFORE the tasks exist (the author agent is still running) and before
# any run. Nothing below is revised after data.

## Why a fourth eval

Eval 3 (CLAUDE.md #48) cleared cleanly — 15/17 decided pairs, p=0.0023, 117
turns against 240, and wall clock cleared its own drift floor for the first time
(p=0.0007). Two things in its own archetype table say what to do next, and
neither is flattering:

| archetype | CB/CIC turns | ratio |
|---|---|---|
| G SPA | 14 / 49 | 0.29 |
| B search-flow | 18 / 52 | 0.35 |
| … | | |
| **C form-lookup** | **23 / 26** | **0.88** |

1. **The widest band was driven by the other arm failing, not by us helping.**
   Their arm could not render caniuse at all (0×0 viewport, 31 turns). So the
   ranking measures where *their* tooling breaks. The one archetype where both
   arms worked cleanly — form-lookup — is the one where we are **level**.
2. **Interaction is the weakest measured band and the least tested.** Eval 3's
   tasks were overwhelmingly navigate-and-read. A task set that contains mostly
   the shape we are best at cannot measure generality (#25, applied to a
   benchmark).

So this eval is deliberately aimed at the band where our claim is weakest.
**If the margin disappears on interaction-heavy tasks, that is the result**, and
it is the one worth knowing.

## Design

- **~20 tasks**, written by an agent told only to write varied browser tasks
  across seven interaction shapes, given a deny-list of every domain used in
  evals 1–3 and #39–#48, and **no knowledge that any toolset is under
  comparison**. Each task verified by that author against the live page before
  submission; unverifiable tasks are dropped rather than guessed.
- **Shapes, ~3 each**: multi-step form with a dependency; filter/sort/paginate
  then extract; drill-down ≥2 levels; content that arrives after the initial
  HTML; non-Latin **with interaction** (typing, not just reading); a non-native
  widget (custom dropdown, date picker, combobox, tree); a data table where the
  answer needs a value related to its column header.
- Ground truth re-derived **independently of the task author** by a referee
  driving headless Chromium, before any run.
- **Strictly serial**, arm order rotated per task.
- Prompts identical modulo the namespace, asserted programmatically. Nothing
  about tabs (#45's headline had to be withdrawn when its prompt turned out to
  mandate the behaviour it measured).
- The other arm's code **unchanged** — it is the drift control.
- Scored from **transcripts**, never self-reports (#47 found two scorer defects
  that way).

## PRE-REGISTERED BARS — fixed now, before any data

**H1 PRIMARY.** Paired two-tailed exact sign test on decided pairs, p<0.05,
recomputed exactly at whatever n survives ties. At n=20 that is 15/20
(p=0.0414). `analyse.py` prints the **achievable p** beside the p, because at
small n a perfect sweep can be unable to clear (#47's six-task subset went 4/4
and the best reachable p at n=4 is 0.1250).

**H2 REPLICATION.** Turns-to-first-page-content: CB median ≤ 2 and strictly
below the other arm's. Held on all 36 runs across evals 1–3. If it fails on
interaction-heavy tasks, the earlier result was task-shape-specific.

**H3.** Fraction of CB runs opening with a single batch that creates a tab,
navigates and reads. 19/19 in eval 3.

**H4 — NEW, AND THE ONE THIS EVAL EXISTS FOR.** On the **interaction-only
subset** (multi-step form, non-native widget, non-Latin-with-typing), CB turns
≤ the other arm's on a majority of decided pairs. **This is pre-registered as a
test we may well fail**: eval 3 measured form-lookup at 0.88, essentially level.
A null here is a publishable result and must be reported as prominently as a
win.

**FALSIFIER.** Correctness. Both arms run the same model, so accuracy is
expected to saturate; any task where the arms **disagree** on a referee-verified
answer invalidates that pair and is reported, not dropped silently.

**NOT A BAR.** Wall clock, unless the per-task median gap exceeds the ~47s/task
drift floor (#35, #41). Eval 3 is the only one where it did.

## Stated in advance

- **Consent gate.** The task origins will not be granted, so every CB run would
  stall on a refusal. If `ALLOW_ALL_ORIGINS` is armed for the duration it is
  recorded as an amendment **here, before any run**, restored after, and
  verified three ways (flag `false`, `git diff` empty, `test_permissions.js`
  24/24 with no "gate off" caveat). **The eval then says nothing about what
  consent costs** and must not be quoted as though it did (#47's precedent).
- **Reporting.** The archetype where we are level gets named in the summary,
  not buried. Every published eval so far has done this and it has cost nothing.
- **Reproducibility.** `runs.tsv` + `analyse.py` must regenerate every table on
  a fresh checkout. Six head-to-heads before `bench_turns/` existed are
  unreproducible, and #45's headline had to be withdrawn.

## Amendments

**AMENDMENT 1 — 2026-11-15, written after the tasks arrived and BEFORE any
run. Sample concentration, stated up front.**

22 tasks across **16 distinct hosts**, but three hosts supply three tasks each —
`jqueryui.com`, `practicesoftwaretesting.com`, `fdc.nal.usda.gov` — so the
**top three hosts are 41% of the sample**. #73 had just finished measuring
exactly this failure on Mind2Web (one widget was 17% of 173 actions, and
leave-one-site-out moved the headline from 95.1% to 98.1%), so it would be
indefensible not to say it here before seeing any data.

Consequences, fixed now:
- `analyse.py` must report **leave-one-host-out** alongside the headline, and
  the summary must quote the range rather than only the point.
- The author flagged `practicesoftwaretesting.com` as a deliberately
  bug-bearing sandbox and it carries three tasks. If any of those three
  produces a disagreement between the arms, **the site is suspect before
  either arm is**.
- H4's interaction-only subset draws on `jqueryui.com` for two of its members.
  That is a narrower base than H4 deserves and is a stated weakness of this
  eval, not something to discover afterwards.

**AMENDMENT 2 — the author verified their own answers; the protocol requires an
independent referee.** Ground truth is re-derived by a referee that does not see
the author's answer key, and any task where the two disagree is **dropped, not
adjudicated**. Eval 3 dropped two tasks at this step — an "address form" that is
an error page with no `<form>` on it, and a question contradicted by its own
page's footnote — and that step is why the rest is trustworthy.

**Known fragilities the author recorded**, carried here so they are not
rediscovered as surprises: T3's expected string contains a **typo the site
itself ships** ("Please select the Paymeny Method") and changes if they fix it;
several tasks carry a deliberate trap that only doing the work survives (T9 asks
for Start Order, not position; T20/T21 ask for Max/Median where Average sits
beside it; T11's answer is literally `(exact)`); shape 5 is three dictionary
look-ups, two of them Chinese, because the Russian site died mid-exercise —
**a genuinely weak group**.
