# Evals — the head-to-head protocol

Harness: `tools/bench_turns/` (pre-registration, task list, referee key,
prompts, generator, scorer, analysis). `analyse.py` reproduces every published
table from `runs.tsv` on a fresh checkout.

**That harness is in the repo because six earlier head-to-heads are not.** Every
one lived in a session scratchpad under `/tmp` and died with the session. A
result nobody can re-derive is an anecdote with a p-value — and #45's headline
had to be withdrawn when its prompt turned out to mandate the behaviour it
measured, which was only catchable because that prompt file happened to survive.

---

## 1. The protocol, and why each rule is there

| Rule | The failure it prevents |
|---|---|
| Tasks written by an agent told only "write N varied two-hop browser tasks", given a deny-list of every domain used before, and **no knowledge that any toolset is under test** | #39's first comparison had tasks I wrote myself, on home ground |
| Ground truth **re-derived independently** by a referee driving headless Chromium, never taken from the task writer | #48's referee dropped two tasks before any run — an "address form" that is an error page with zero `<form>` elements, and a question whose own footnote contradicted it |
| Runs **strictly serial**, arm order **rotated per task** | #39: six parallel agents shared one Chrome and corrupted each other's tab groups |
| The other arm's code **unchanged**, as a drift control | #35: the control arm improved 47s and 5 calls with no code change. Without it I would have claimed a win |
| Scored **from transcripts**, never from self-reports | #47 found two scorer defects that way — the harness's own reply mechanism counted as a turn, and answer extraction returned null for any agent that handed back without a final text block |
| The bar fixed **before any data exists** | #40 set 9/10 (p=0.021 at n=10) in advance and then honoured it when the result came in at 8/10 |
| Report **achievable p** beside p | #47's six-strong subset went 4/4 — and **the best p reachable at n=4 is 0.125**, so it could not have cleared with a perfect sweep. Underpowered is not the same as disagreeing |
| Wall clock reported only above the drift floor | ~47s/task (#35, #41). #48 is the only eval where it cleared |
| Correctness is a **falsifier**, not a headline | Both arms are the same model, so accuracy saturates. 38/38 and 30/30 are ceilings, not wins |

---

## 2. What the published results actually say

| Eval | Design | Result |
|---|---|---|
| #39–#41 | 4 and 10 tasks | **tie, three times.** p=0.51, p=0.125 |
| #43 | 24 tasks | 15/20 pairs, p=0.0414 — and **weaker than its own baseline** (19/21, p=0.0002). #42's fixes narrowed the lead |
| #47 | 9 tasks, ×2 | 7/7 then 9/9, p=0.0156 then p=0.0039 |
| #48 | **19 tasks, 7 archetypes** | **15/17 pairs, p=0.0023. 117 turns vs 240. Wall clock 1,662s vs 3,674s, p=0.0007** |

**#48 is the one to quote**, and its own honest reading is not the flattering
one. The archetype breakdown:

| archetype | CB/CIC turns | ratio |
|---|---|---|
| G SPA | 14 / 49 | **0.29** |
| B search-flow | 18 / 52 | 0.35 |
| D data-table | 10 / 23 | 0.43 |
| E drill-down | 18 / 40 | 0.45 |
| A doc-lookup | 9 / 15 | 0.60 |
| F non-Latin | 25 / 35 | 0.71 |
| **C form-lookup** | **23 / 26** | **0.88** |

G is widest because **their arm could not render caniuse at all** (0×0 viewport,
31 turns). So the ranking is driven by where *their* tooling fails, not by where
our representation helps — and **the one archetype where both arms worked
cleanly is the one where we are level.** Say that; it is not the flattering
sentence and it is the true one.

Excluding the four runs where their arm broke down entirely, totals are
**72 v 127 = 57%**, so the result survives removing its own outliers. The sign
test is immune to them by construction, which is why the bar is set there.

---

## 3. The instrument's ceiling, and the next task set

#39 recorded it first: when both arms solve everything in one round trip there
is nothing left for the representation to differ about. #48 widened the task set
and found the fixed-cost share fell from 54–58% to **31% startup / 69%
in-task** — longer tasks amortise a constant.

**The next eval must be interaction-heavy, because that is where we are level
and where the claim is therefore weakest.** Designing it around our strengths
would be #25's rule applied to a benchmark: a sample containing only the shape
you are best at cannot measure generality.

Target archetypes, in priority order:

1. **Multi-step stateful forms** — a flow where step 3 depends on a value
   entered at step 1, with validation that rejects and must be corrected.
   Archetype C is our weakest measured band (0.88); this is the honest place to
   push.
2. **Filter → sort → paginate → extract** — where `query_elements`' uncapped
   `total` and the declared `aria-rowcount` should matter, and where #35 found
   a wrong answer from counting rendered rows.
3. **A page that is still building when first read** — the archetype no existing
   eval contains, and the one the #70 readiness work exists for. Both arms get
   the same page; the question is whether either notices.
4. **Non-Latin interaction, not just lookup** — #48's F band (0.71) is lookup
   only. Writing and reading back a non-Latin value exercises a different path.
5. **Shadow DOM / closed roots** — a measured capability gap in a competitor's
   own published benchmark, which scored **0/21** on iframes and closed shadow
   roots.

---

## 4. The thing no turn count can show

Record-and-replay is not a speed difference, it is a capability the other arm
structurally does not have — and the turn metric cannot express it, because the
comparison is "N turns" against "cannot".

So it needs its own demonstration, with its own honest framing:

- **The honest claim** is *do the task once, get a replayable test with
  assertions derived from the checks the agent already made*, replaying with
  **zero model calls per step**. Measured: a 2-step flow recorded from 4 agent
  turns replays in **0.25–0.33s**.
- **The honest caveats**, which must travel with it: a flow that creates
  something is not re-runnable without a fixture reset; a descriptor's identity
  can be live data (a tab named `Records 43`); coordinate steps are deliberately
  unrecordable; and the assertions are **as good as the agent's own
  observations**, which is why `hollow` / `unproven` / `unwitnessed_absence`
  exist.
- **Do not claim it cannot break.** It can, and `OPEN.md` Tier 1 lists how.
  Claim instead that every way it breaks is named, measured and pinned by a
  check — which is a stronger statement than a clean demo, and is true.

### The demonstration, captured

One command, reproducible on a fresh clone:
`python tools/run_flows.py --playground --local-only [--chaos FLAG]`.
A green replay only proves it ran; the interesting cases are the other three.

**1. Replay. No model call per step.**
```
PASS  acme-create-project   4/4 step(s) in 4.52s
PASS  acme-nav-badge        4/4 step(s) in 0.41s
PASS  acme-precondition     2/2 step(s) in 0.26s
3/3 flow(s) passed                                            exit=0
```

**2. `--chaos ja` — the app is localised, so the login form is no longer the one
the flow starts from.** It stops *before acting*:
```
FAIL  acme-precondition     1/2 step(s) in 6.15s
      the app is not in the state this flow starts from:
      search_page('Work email') found 0, recorded at least 1.
      Stopped before step 1 (fill_form). Only the 1 navigation step(s) ran.
                                                              exit=1
```

**3. `--chaos badge` — a count badge moves and the link is untouched. This is
the one to lead with.** The recorded accessible name was `Projects 4`; it is now
`Projects 5`. The flow **passes and says why**:
```
PASS  acme-nav-badge        4/4 step(s) in 6.59s
      step 3 computer: name 'Projects 4' is gone; matched href='/projects'
                                                              exit=0
```
A label changed, the test still ran, and it reported the drift instead of either
failing spuriously or silently healing. That is the behaviour the self-healing
literature says is hard — and the reason it is safe here is that `href` is a
second *declared* key for a surviving element, never an answer to "is it gone".

**4. `--chaos insert` — a row is added, so the recorded count is wrong.** A real
regression, named precisely, with causes that need different answers:
```
FAIL  acme-create-project   1/4 step(s) in 6.36s
      step 1 (fill_form): query_elements('table tbody tr') counted 5,
      recorded exactly 4. The count GREW. Causes that need different
      answers: a previous run left its own rows behind; the data changed
      underneath; or the page really does render more now.
                                                              exit=1
```

Exit codes are real, so each of these is a CI outcome rather than a message.
**Read the exit code without a pipe** — `echo $?` after `| tail` reports `tail`,
which this project has misread twice.

---

## 5. Rules for publishing a number

- Quote the eval, the n, and the pre-registered bar. "p = 0.0023" without
  "15/17 pairs, bar fixed at 9/10 before any data" is not a result.
- Name the archetype where we are **level**. Every published claim so far has
  done this and it has cost nothing.
- Never quote wall clock below the drift floor.
- Never quote correctness as a win — both arms are the same model.
- A gate that was armed for a run (`ALLOW_ALL_ORIGINS`) must be stated as an
  amendment **before** the run and restored after, verified three ways. #47 did
  this and recorded that the eval therefore **says nothing about the cost of the
  consent model** and must not be quoted as though it did.
