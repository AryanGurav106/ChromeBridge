# WebPageBench — verified, and the verdict is BUILD

`docs/SUCCESS-RETENTION.md` is a worked negative result: the attempt to measure
whether our DOM reduction preserves task **success** rather than element
**presence** died on the substrate, in four named ways. This document records
whether WebPageBench can carry that measurement, what it actually is, and the
design if it can.

**Verdict: BUILD.** All four failure modes are addressed, three of them
structurally rather than by patching. The missing leg — synthetic rather than
live sites — is real, is a generalisation caveat rather than an
instrument-invalidating one, and buys a controlled experiment that live sites
can never provide.

Everything below marked PASS is re-derived from the released data by
`tools/audit_webpagebench.py`, which exits nonzero if any claim fails and has a
`--self-test` showing its invariance check firing on three planted violations.
The paper is not the source for anything load-bearing here (MEASUREMENT.md R1).

---

## 1. What it actually is

**WebPageBench: Event-Level Verification and Controlled UI-Variant Generation
for Web Agents.** [arXiv:2609.35026](https://arxiv.org/abs/2609.35026),
submitted 28 Sep 2026. Anton Emelyanov, Maria Tikhonova, Zaven Martirosian,
Sergei Averkiev, Alena Fenogenova (5 authors, ai-forever / SberAI).
cs.AI, cs.CL. Code: `github.com/ai-forever/WebPageBench`, Apache-2.0.

**Status: v1 preprint. No comments field, no venue, no acceptance, not peer
reviewed. 3 GitHub stars, 0 forks at the time of checking.** This repo already
records a preprint's eight refuted preregistered hypotheses alongside its
headline (#70); treat this the same way. The mitigation is that the claims we
depend on are *checkable from the released artefact*, and were checked.

### Verified from the data, not the paper

| claim | result |
|---|---|
| 152 tasks | **PASS** — 152 task JSONs |
| 65 canonical + 87 UI variants | **PASS** |
| 6 sites | **PASS** — hotels 45, shop 32, rail 26, books 21, files 18, grocery 10 |
| 19 event types, 521 conditions | **PASS** — exactly |
| 9 control keys, 33 registered implementations | **PASS** |
| event-log oracle with **no judge model** | **PASS** — `lib/src/agent_bench/client.py` imports only `requests`, `os`, `json`, `re`, `datetime`; `check()` fetches the log and the config and matches conditions. Deterministic. |
| control swap keeps prompt + conditions identical | **PASS — 87/87 byte-identical on both.** Only `ui_variants` / `ui_variant_profile` differ. |
| per-step element-level ground truth | **ABSENT** — success is end-of-task from the log |

### The oracle is representation-independent, which is the whole point

Semantic events are emitted by the app's **business logic after the state
mutation**, not by a DOM listener. In `views/bench/shop/Item.vue`:

```js
incrementShopBasketItem(user, this.basketKey, 1); this.refreshBasket();
_logActivity(this, { type: 'basket_add', item_id: this.basketKey, amount });
```

A generic click tracker exists in `common/tracker.js`, but the 19 condition
event types do not come from it. So the oracle cannot see *how* the agent caused
the state change — click, keystroke, coordinate — and cannot see what the agent
was shown. That is exactly the property a representation comparison needs.

### Two things no description of it mentioned

1. **It is a Russian-language benchmark.** 152/152 prompts contain Cyrillic.
   Not a blocker — this project has extensive non-Latin work (#21, #24, #37's
   Naver title, #71's kana fold) and this independently exercises it — but the
   agent prompt will be Russian and that must be stated wherever a number from
   it is quoted.
2. **33 implementations is the registry, not the tested surface.** The task set
   exercises **17 of 33**. Quote 33 as what the site can render and 17 as what
   the released tasks actually cover.

The survey that surfaced this described it as "152 tasks across six instrumented
mock sites". Both halves are true, but the paper's abstract says "six
browser/DOM harness configurations" — a *different* six (the agent frameworks
they evaluated: browser-use, ouroboros ×3, openmanus, openhands). Two
unrelated sixes, one sentence apart, and conflating them would have had us
looking for a harness-plugin interface that is not the mechanism.

---

## 2. The verdict, against our four named failure modes

`docs/SUCCESS-RETENTION.md` named four ways Mind2Web's snapshots defeated the
measurement, plus our own arm's single-read problem.

| # | failure mode on Mind2Web | on WebPageBench |
|---|---|---|
| 1 | **baseline leaked the gold target** through `backend_node_id` ordering — gold preceded `<html>` in 12/20 pages | **STRUCTURALLY GONE.** There is no serialized snapshot and no precomputed id space. Both arms render a live DOM themselves, and there is no "gold element" to leak: the oracle is a typed event with parameters the task prompt already states. Nothing is scoreable from a side channel because the side channel does not exist. |
| 2 | **no `href` anywhere** — 0/40 samples; 14/20 AX pages had no `link` role, so targets were literally unaddressable | **GONE.** A live Vue + Vuetify SPA with a real router. Real anchors, real roles, real ARIA. *Unverified until the site is stood up — see §5.* |
| 3 | **no step VALUE** — bare `"CLICK"` left items with no determinate answer; a judge called one "a genuine ~50/50" and declined | **GONE.** Tasks are full natural-language instructions carrying their own values, and success is 521 typed conditions with parameters (`item_id`, `cityId`, dates, counts). Median 3 conditions per task, max 10. There is nothing to adjudicate. |
| 4 | **no CSS** — Six Flags shipped four identical utility navs and a judge was wrong by construction | **GONE.** Real rendered app, real stylesheet, real viewport. Our visibility machinery (`checkVisibility({opacityProperty, visibilityProperty})`, PRINCIPLES #3) operates as designed instead of against a stripped document. |
| 5 | **our arm is viewport-scoped and a single read cannot follow up** — "the AX file has the form's content and no identifier; the ChromeBridge file has identifiers and not the form" | **GONE, and this is the big one.** WebPageBench is agentic by construction: the runner hands the agent a URL and waits for it to stop. The "scope into this region, here is its ref" recovery our listing prints is a follow-up call a loop makes and a one-shot reader cannot. SUCCESS-RETENTION's own closing note — "the comparable literature number comes from an agent LOOP, so a fair version must give each arm the follow-up call its own output asks for" — is satisfied. |

A fifth hazard, found here rather than inherited: routes are
`/:track_id/:state_id/<name>`, so `state_changed` conditions are deep-linkable
and an agent could in principle pass by typing URLs without touching a control.
**Measured: 0 of 152 tasks have only navigational conditions.** 62.5% have none
at all; the other 37.5% are mixed. Every task requires at least one real state
mutation. The loophole does not bite.

---

## 3. What it costs us — the caveats that must travel with any number

- **Synthetic sites, not live.** This is the honest missing leg. Two things
  soften it and neither removes it: our only out-of-sample number today comes
  from *stripped static snapshots with no CSS and no scripts* (#73), so a live
  DOM with real CSS and a real agent loop is strictly closer to reality than
  what we already quote; and Vuetify is a mainstream component framework in the
  same family as the Radix/MUI/PrimeVue targets this project was built against.
  It is still six apps written by one team, and a result here is **evidence
  about a controlled environment, not about the web**.
- **152 tasks are not 152 observations.** 65 independent donors + 87 controlled
  re-renders. Hotels is **30%** of the set and 37 of its 45 are variants. This
  is #73's correction to our own headline arriving in advance: report
  leave-one-site-out, and never quote 152 as a sample size.
- **Russian prompts.** Fine, and a bonus test, but it must be said.
- **It cannot replace `bench_mind2web.py`.** No per-step element ground truth,
  so it scores no element recall. The two instruments answer different
  questions and neither substitutes for the other.
- **The leaderboard is not comparable to us.** Different models, different
  harnesses. Any number we produce must come from our own both-arms run; citing
  their table beside ours would be the "numbers computed by different people on
  different samples" problem #17 exists to have ended.

---

## 4. The design

Three measurements, in the order they should be built. **M-B is first to build
even though M-A is the question as asked**, because it needs one arm instead of
two, is immune to between-arm drift, and tests a claim nothing in this repo has
ever measured.

Shared machinery for all three: stand up the site, `create_track(task_config)` →
drive one agent to the returned URL → `check(track_id)` → EMS (binary: all
conditions hold). Modelled on `tools/bench_turns/`, which already does
pre-registration, serial runs, rotated order and transcript-based scoring.

### M-B — generality under control swap  ·  *new capability, cheapest, build first*

The project's headline claim is that it works on framework-heavy SPAs **without
site-specific code**, and PRINCIPLES #1 says existence is decided only by
declarations. That predicts something sharp and falsifiable: **success on a task
should not depend on which implementation of a control is rendered**, because
every implementation declares itself.

The variant axis tests exactly that, and it is a genuine controlled experiment —
verified 87/87, the prompt and the success conditions are byte-identical and
only the control implementation changes.

- **Unit: 25 donor families** (not 87 variants, not 152 tasks).
- **Coverage is even**: 5 families per control key, `date` 10, `theme` 12.
- **What it stresses, concretely**: `date` ∈ {`native_input`, `text_input`,
  `inline_calendar`, `single_popup`} walks our native-control path, our typed
  path, and an ARIA grid (#7's ≥10-cell fold) for one unchanged task;
  `counter_guests` ∈ {`inline_stepper`, `pill_buttons`, `compact_select`} walks
  the counter and `(unselected)` machinery; `select_city` ∈ {`autocomplete`,
  `native_select`} is the combobox chain (#29's decoy-listbox work) against a
  plain `<select>`.
- **The negative control ships with the benchmark.** 12 `theme_dark` variants
  change colour only. A structural representation must score the same on these
  as on their donors. **If dark theme moves the number, the instrument (or we)
  are wrong and no other variant result should be believed yet.** MEASUREMENT.md
  R3 demands a drift control; here it is free.
- **Falsifier, pre-registered**: a material gap between implementations of the
  same control, on the same task, with the same conditions, is a measured
  counterexample to the generality claim. That is a result worth having in
  either direction — and unlike a token or recall number, it cannot be explained
  away as a trade.

### M-A — our own ladder on success  ·  *closes `OPEN.md` item 11*

OPEN item 11: "`detail` and `format` are priced on recall and tokens, never on
end-to-end success with a strong model. The literature disagrees with itself
about which way this cuts." One toolchain, one arm, vary only our own
parameters: `format` ∈ {tree, flat}, `detail` ∈ {compact, brief, full}.

- **Unit: the 65 canonical donors**, variants excluded (they are not
  independent).
- This is an ablation of our own code against a fixed sample, so R2 applies in
  full: it measures the ladder against *these six apps*, and cannot measure the
  sample.
- It is the first time `format="tree"` would be priced on anything but tokens —
  #27 shipped it on an explicitly NULL A/B result, because no metric there could
  read a listing the way an agent does.

### M-C — cross-representation head-to-head  ·  *the SUCCESS-RETENTION question, most expensive, last*

ChromeBridge vs Claude-in-Chrome, **same model**, same tasks, same oracle — the
established `bench_turns` design with EMS as the outcome instead of turns.
65 donors × 2 arms. Do this only after M-B and M-A, because it is the most
expensive and the most exposed to drift.

### The confound that must be designed out, in all three

**Our tool surface has escape hatches.** If an agent reaches the state with
`javascript_tool`, or by typing a URL, the run stops measuring the listing and
starts measuring Claude's ingenuity. #27's A/B pinned `filter="interactive"` so
that the listing was the thing under test; the same discipline applies here:

- pin the toolset, and **exclude or separately account for `javascript_tool`**;
- record per-run which tools were called, as a covariate, and report the
  fallback rate beside every number — a result with a high fallback rate is
  about the agent, not the representation;
- the URL loophole is already measured as harmless for *scoring* (0/152), but
  an agent skipping navigation by URL still skips controls, so navigation-by-URL
  must be recorded too.

Secondary readouts worth collecting on the same runs, free: turns to success
(comparable to `bench_turns`), and the paper's own gap metric — agent declares
done vs log confirms done, which they measure at **41 points** and which is a
direct read on whether our observation surface lets an agent *know* it
succeeded.

---

## 5. What it would take to run

1. **Serve the sites.** `cd site && docker compose -f docker-compose.local.yml
   up` → port 8080. The Docker daemon must be started (it was not, here). The
   alternative is `site/backend` (Flask, 235 lines, needs only `flask` +
   `flask-cors` — the heavy `datasets`/`huggingface-hub` lines in its
   `requirements.txt` are not imported by `main.py`) plus `cd site/frontend &&
   npm ci && npm run dev`. There is **no prebuilt `dist/`**, so the frontend
   must be built either way.
2. **`pip install -e lib/`** into a throwaway venv for `create_track` /
   `get_track` / `check`. **No API key, no model access, none of their harness
   submodules.** We need their site and their oracle, nothing else — their eval
   stack exists to drive *their* agents.
3. **Grant `localhost:8080` once in the side panel.** All six sites live under
   one origin, so **one grant covers the entire eval and the consent model stays
   fully armed.** This removes a stated debt: #47 had to set
   `ALLOW_ALL_ORIGINS=true` for its nine origins and recorded it as something
   the eval could say nothing about.
4. **A runner under `tools/bench_turns/`**, reusing its pre-registration,
   rotation and transcript scoring. Runs must be **serial** — one Chrome, one
   extension, one socket, and #39 records six parallel agents corrupting each
   other's tab groups.
5. **Budget.** Their own numbers are 131 s median per task per agent. M-B is
   25 families × (1 donor + its variants) ≈ 112 runs; M-A is 65 × the ladder
   points measured; M-C is 130. **This is a large eval and the bar must be fixed
   before any data exists**, per MEASUREMENT.md §5 — 9/10 was declared once and
   honoured when the result came in at 8/10.

---

## 6. What is NOT established

Stated plainly, because a verification that overstates itself is the defect this
document exists to avoid.

- **The site has never been stood up here.** Docker's daemon was down and
  starting it was not mine to do; the frontend has no prebuilt `dist`. Claim 2
  in §2 (real `href`, real roles) is *expected* from a Vue router app and
  **unverified**.
- **The oracle has never fired end to end.** `check()` was read and is judge-free
  by inspection of its imports, but no `create_track → events → check` loop was
  run. That is the first thing to do after §5.1, and it is cheap.
- **No arm was run. There is no number in this document**, and nothing here says
  what our success retention is.
- **The paper's own leaderboard was not reproduced** and should not be quoted
  beside anything we produce.
- A minor discrepancy left standing: the paper describes 87 variants "across 20
  profiles"; the released filenames carry **15** distinct profile suffixes. Not
  load-bearing for any design above, but it means the paper and the artefact
  disagree somewhere and the artefact is what we would run.

---

## 7. If it had been DON'T BUILD

Recorded because the alternative was costed before the verdict was taken, and
because a future reader may need it if the site turns out not to run.

With what is already in the repo, success retention is **not** measurable, and
the reason is specific: every in-repo instrument scores a *representation* or a
*single observation*, and none owns an environment whose state can be checked.

- The **frozen 106-site corpus** is HAR replay. Replay is read-only — a click
  that would add to a basket has no server to talk to — so there is no success
  to check. It measures presence, and does so well; it cannot be made to measure
  success.
- **`tools/bench_turns/`** has the loop, the pre-registration and the discipline,
  but its outcome is graded against hand-written answer keys on live public
  pages. It scores *information retrieval*, and its correctness metric has been
  saturated at 100% in four consecutive evals because both arms are the same
  model. It cannot discriminate.
- **The flow recorder** is the closest thing we own to an event oracle, and it
  is genuinely close: `run_flow` replays a recorded path and checks
  postconditions. But its assertions are recorded from *our own tool output*, so
  grading our representation with it would be marking our own homework — and
  `docs/FLOWS-FAILURE-SURFACE.md` plus #57's hollow/unproven classifier exist
  precisely because recorded assertions can be true regardless of what the step
  did.
- The only in-repo route would be **`tools/saas_playground.py`** — our own
  fixture app — extended with an event log. That is building WebPageBench badly:
  one app, written by us, tuned to us, with no control-swap axis and no external
  validity whatsoever.

So the honest fallback would have been: **the question stays open**, and the
reason is that measuring success needs an environment with checkable state, we
do not own one, and building one ourselves would produce a number that only
measures our own fixture.

That is what makes WebPageBench worth the setup cost: not the task count, but
the event log and the control-swap axis — one gives a judge-free outcome the
representation cannot influence, and the other gives a controlled experiment on
the exact claim this project leads with.

---

## Verified by standing the site up — 2026-11-16

The assessment above was made from the released code without running it, and
left two things explicitly unverified. Both were checked. One confirms, one
corrects the assessment, and the correction changes what this benchmark can
measure.

**How it was stood up.** `docker compose -f site/docker-compose.local.yml build`
then `up -d`; the site serves on :8080. A runnable track is NOT a task file — it
is `tests/bench/config.json` **merged with** one of the 152 task files (the merge
is in their `tests.py`), POSTed to `/track/create` as a form plus file upload.
A track created from a task file alone renders `State Not Found — не найден шаг
state_id в конфиге`. The merge was done in plain stdlib rather than by running
their code; nothing was pip-installed outside the container.

**CONFIRMED: the oracle fires end to end.** Server log, unprompted, on a plain
page load: `Added event: track_id=cb2 event_name=state_changed`, `POST
/event/add 200`. So the "no judge model" claim is not only true of `check()`'s
imports — the event pipeline it reads really does run.

**CONFIRMED: the task prompts are Russian.** `"На %HOST% в «Книги» найди самую
дорогую книгу Полины Шустовой и добавь в избранное."` The `%HOST%` placeholder
is the benchmark's own, substituted per track.

**CORRECTED: "a Vue router app will have real href and roles" is half right, and
the half that is wrong matters.** Measured across four of the six domains on one
track, after the app had fully rendered:

| domain | `<a href>` | buttons | inputs | aria-labelled | distinct roles |
|---|---|---|---|---|---|
| books | **0** | 78 | 1 | 37 | 4 |
| shop | **0** | 65 | 1 | 43 | 3 |
| hotels | **12** | 24 | 6 | 3 | 2 |
| rail | **18** | 11 | 2 | 1 | 0 |

Mind2Web's failure (0 `href` across 40 samples, so 14 of 20 AX pages had no
`link` role at all) does NOT reproduce — hrefs exist. But they are
**heterogeneous by domain and distributed INVERSELY to aria**: the domains that
navigate by link carry almost no `aria-label`, and the domains that carry
`aria-label` navigate by `<button>`.

**Three consequences, and the first is a scope reduction.**
1. **The `detail` ladder is measurable on at most 2 of 6 domains.** `brief` and
   `full` differ from `compact` by `href=`/`src=`; with zero anchors there is
   nothing for them to add. This is #73's Mind2Web finding ("no `detail`
   comparison taken on Mind2Web means anything") reappearing in the benchmark
   chosen to escape it — narrower here, since it is 2 of 6 rather than 0 of 16,
   but **M-A must report `detail` on hotels/rail only and say so.**
2. **`format` (tree vs flat) is unaffected** and remains fully measurable, which
   matters because #27 shipped the tree on an explicitly NULL A/B.
3. **Per-domain reporting is not optional.** A number pooled across these six
   would blend two structurally different page families, and which family a task
   lands in is decided by the benchmark rather than by us. This is on top of the
   leave-one-site-out requirement the sampling already imposes.

**Still not established:** the full `create_track → agent acts → check()` loop
has not been run against a real agent, and no arm has been run. There is still
no number anywhere in this work.

---

## FIRST RESULT — theme invariance, 2026-11-16

`tools/measure_wpb_invariance.py`. This is not one of the three measurements
designed above; it is the INSTRUMENT CHECK that has to pass before any of them
is believed, and it is the cheapest real test of this project's headline claim.

WebPageBench ships 12 `__theme_dark` variants whose task text and success
conditions are **byte-identical** to their canonical twin — verified by the probe
before it measures anything, and it refuses rather than running if they differ —
and which vary only by `ui_variants: {"theme": "dark"}`. A representation built
on what the DOCUMENT DECLARES must produce the same listing for both. One built
on presentation will not.

Arms interleaved light / dark / light per pair, so run-order drift cannot align
with the arm (#19) and the same-arm difference is the floor measured in the same
window. Refs are normalised away because `mmid`s are additive per document and
comparing them would measure the counter rather than the page.

| | result |
|---|---|
| pairs measured | **12 / 12**, across all six domains |
| rows per listing | 14 (files) to 136 (books) |
| **changed lines, dark vs light** | **0** |
| same-arm drift floor | **0** |

**The listing is byte-identical under a colour-only change, on every pair.**
That is a narrow property stated narrowly: it establishes that the
representation does not read COLOUR. It does not establish invariance to the
other eight control keys, which is M-B and is a different measurement.

The floor being 0 everywhere is a second, unlooked-for result: these pages
render deterministically across loads, so the later measurements have no drift
to subtract. The frozen 106-site corpus has 18 named non-deterministic replays
and a 0.5% token floor; this has neither.

**AND THE FIRST RUN OF THIS PROBE REPORTED THE OPPOSITE**, with a number that
read exactly like a real finding: **2 changed lines on every pair against a
floor of 0** — deterministic, consistent across pairs, in the direction that
would have invalidated the benchmark. It was the harness. The two arms are
necessarily different tracks, so the `Current URL:` line differs by the track
id and nothing else. Found by printing the diff instead of trusting the count,
which is #16's rule, and the normaliser now strips it. A probe that damns the
system gets re-derived before it is believed, and this one would have been
reported as "the representation reads presentation" by anyone who stopped at
the summary line.
