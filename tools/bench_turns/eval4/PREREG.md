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

**AMENDMENT 3 — 2026-11-15, after the referee and BEFORE any run. Two tasks
dropped, two reclassified, and a disclosed deviation.**

**THE REFEREE SAW THE ANSWER KEY.** Its first command was `cat` on the whole
task file, so it read the author's `**Answer:**` lines before it could filter
them. It disclosed this unprompted, compensated by deriving every value with its
own scripts and actively attacking the author's premises — which found one false
premise and corrected three counts — and named **T7, T20 and T21** as the three
worth re-refereeing blind. Recorded rather than papered over: **its independence
is strong but not blind**, and anyone quoting this eval should know that. A
blind second opinion on those three is owed.

**DROPPED — T15 (MDBG Chinese dictionary).** The host's own footer states
verbatim *"Automated or scripted access is prohibited."* It served us normally
and the lookup is read-only, but this benchmark would drive it repeatedly across
two arms. **That is not a quality judgement and not ours to trade off**, so it
is out. The non-Latin shape drops from 3 tasks to 2, which is a real weakness of
this eval and is stated rather than hidden.

**DROPPED — T18 (jQuery UI datepicker).** The answer is `01/15/2020`, which is
jQuery UI's default `mm/dd/yy` applied to the date named in the task — so an
agent that types the string without touching the calendar produces an
**indistinguishable** result. A task that cannot separate doing the work from
guessing cannot measure turns, which is the only thing this eval measures.
(It would also have needed revisiting ~2031: the year dropdown is a window
centred on the current year.)

**RECLASSIFIED — T7 is not a filter task.** On arrival, "Foundation Foods" is
already the ACTIVE tab, so the filter the task asks for is applied by default
and the answer is visible with **zero interactions**. Verified by polling at
5/10/15/20/25/30/40s with no click at all. The answer is still correct and
unambiguous so the task stays, but it tests **waiting for an SPA**, not
filtering, and is counted under the late-arriving shape. T21's interaction count
is 1, not 2, for the same reason.

**RECLASSIFIED — T13 is not a late-loading task.** The children were already
present 500ms after the click. Its real difficulty is that the clickable target
is the arrow icon rather than the label, so it counts as a custom widget.

**FALSE-DISAGREEMENT RISKS, ranked by the referee and carried into the scorer**
(these are where the two arms will "disagree" without either being wrong):
T9 asks for `Start Order` (**21**), not `Pos` (**3**) — and 3 is also the medal
rank, so the wrong answer looks internally consistent and **must be rejected
explicitly**. T20's Average and Median are both **258** while Max is **271**.
T11's answer is literally `(exact)`, not the numerical value. T16 has `部外 0`
immediately before `总笔画 12`. T2's first table row is `100-0000`, not the
answer. T14 prints Kun readings immediately above the On line.

**AMENDMENT 4 — 2026-11-15, after the blind re-referee and BEFORE any run.**

**The two referees AGREE on all three contested answers**, which closes the
disclosed-blindness debt from Amendment 3: T7 = 19 results, first `Cheese,
cheddar`; T20 Max Magnesium = `271`; T21 Median Sodium = `650`, n = `41`. The
second referee was blind (it extracted only the task lines, never opened the
key) and reached them independently, by three mutually-checking routes — header
geometry, the DOM's own `headers` attribute on each cell, and recomputation from
the raw per-sample values.

**T7's premise is confirmed dead.** Foundation Foods is already the active tab
on arrival; only one tab carries `class="…active"`, the 19 rows already match
its count, and clicking the tab changes nothing but the URL. It also confirmed
the early-read trap with timing: at 0.1s the tab reads `Foundation Foods ()`
with an empty count, every sibling at `(0)`, and **zero rows** — which reads as
"nothing matched". Settled by ~0.9s.

**THE GRADING IS TIGHTENED, because three tasks are partly guessable without
doing the work** and grading on the guessable half would score a guesser as
correct:

| | guessable half | discriminating half |
|---|---|---|
| T7 | `Cheese, cheddar` is the obvious #1 hit for a cheese query | the count **19** |
| T20 | the republished figure for almond magnesium is **~270**; the true Max is **271**, so a knowledge-only guess lands within 1 | exact `271`, no tolerance band |
| T21 | cheddar sodium is cited around 620–660, so "~650" is guessable — and the *most* cited figure is **653**, the SR Legacy value | **n = 41**, unguessable |

Implemented as `require_all` in the ground truth, honoured by `analyse.py`, and
**driven over a guesser/reader/confusable triple for each task before being
trusted** — which is how a real defect was caught: the reject list had harvested
the bare column name `n` from a backtick in the key, and a one-character reject
matched almost any answer, so a correct T21 scored WRONG. That would have read
as the agent failing every run rather than as a broken ruler, which is #48's
falsifier-fires-on-both-arms signature.

**The positional-indexing trap is measured and is the sharpest thing here.** The
nutrient table has 13 `<th>` and 12 `<td>`, because two headers are zero-width
and the row has only one such cell — so `children[n]` is off by one from index 3.
An agent asked for T20's **Max** that indexes positionally returns **258**, which
is simultaneously the Median *and* the Average Amount, so the wrong answer looks
doubly corroborated. It is an explicit reject.

**Also recorded:** both pages carry a portion `<select>` defaulting to `100 g`;
changing it rescales every statistic proportionally (271 → 81.3 at 30 g), so a
portion change produces a wrong answer that is internally consistent. Those
values are rejects too.

**AMENDMENT 5 — 2026-11-15, written BEFORE the gate is armed and before any
run. The consent gate.**

The 15 task origins are not granted, and ChromeBridge refuses the first op on an
ungranted origin **by design** — that is the consent model working, not a
failure. Every CB run would therefore stall on a refusal that the other arm does
not have.

`ALLOW_ALL_ORIGINS` is armed for the duration of the run and restored
immediately after. The justification is the one #47 recorded: per-origin consent
is a **one-time, per-origin** cost, not a per-task turn cost, so counting it
would charge us 20 times for a security feature the comparison is not about.

**Therefore this eval says NOTHING about what the consent model costs, and must
not be quoted as though it did.**

Restore is verified three ways before any number is published: the flag reads
`false` in the source, `git diff` is empty, and `tools/test_permissions.js`
reports 24/24 **with no "gate off" caveat**. A suite that passes while reporting
`not-applicable (gate off)` is a suite that proved nothing, which is why the
caveat is checked and not just the count.

Also recorded: the flag is a module-scope `const`, so the service worker must
restart to pick it up. #47 measured that a flag change does **not** take effect
while the bridge holds the worker alive, and that a flag restored on disk is not
a flag restored in the browser. Whether the arming took is therefore **tested
against a known-ungranted origin before any run**, rather than assumed.

**Known fragilities the author recorded**, carried here so they are not
rediscovered as surprises: T3's expected string contains a **typo the site
itself ships** ("Please select the Paymeny Method") and changes if they fix it;
several tasks carry a deliberate trap that only doing the work survives (T9 asks
for Start Order, not position; T20/T21 ask for Max/Median where Average sits
beside it; T11's answer is literally `(exact)`); shape 5 is three dictionary
look-ups, two of them Chinese, because the Russian site died mid-exercise —
**a genuinely weak group**.
