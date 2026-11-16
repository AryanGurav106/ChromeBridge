# Record and replay: the failure surface

The brief was "handle complex and edge cases in such a way that conceptually it
would never break". No system reaches that, so this is the honest version of
it: **every way this feature can break, enumerated by the stage it breaks at,
each with its evidence and its status.** A gap with no entry here is a gap
nobody has thought about, which is the only kind that is genuinely dangerous.

Read `FLOWS.md` first for what the feature is. This is the adversarial pass.

Status: `CLOSED` (fixed + a check that fails against the old code) ·
`BOUNDED` (cannot be fixed, but the failure is announced) ·
`OPEN` · `INHERENT` (a property of the problem, not of this implementation).

---

## Stage 1 — RECORD: what gets captured

| # | Failure | Status |
|---|---|---|
| 1.1 | A step that silently did nothing is compiled in as a real step | `CLOSED` — the extension emits `NOT DONE:` / `NO EFFECT:` tokens from the ok/not-ok branch itself, so a new refusal wording cannot appear without one (#66, #72). An enumeration of wordings was always one wording behind. |
| 1.2 | An assertion that was already true before the step | `CLOSED` — flagged at `record_flow(stop)`, the one moment it is cheap, scanning back ACROSS actions for the latest prior value (#57). It is a warning, never a refusal: an idempotent step legitimately leaves state alone. |
| 1.3 | An assertion nothing was ever observed to contradict | `CLOSED` — `unproven`, named rather than dropped, since unevidenced is not wrong (#68). |
| 1.4 | A mistyped search that found nothing, frozen in as `absent: true` | `CLOSED` — an absence is only kept when the thing was SEEN present earlier, otherwise dropped and named (#64). |
| 1.5 | A content check compiled into a mere existence check | `CLOSED` — a single-match query keeps the TEXT it read, and a typed field keeps its `value` (#63, #64). |
| 1.6 | The first observation after a navigation wins, so a stale read is baked in | `CLOSED` — last-wins, and an in-flight read is not compiled (#63). |
| 1.7 | **A check that is WRONG rather than weak** — the agent read the number, and read it wrong | `INHERENT` — this is the oracle problem. Nothing in the recorder can know the truth the agent was looking at. The honest answer is that a flow is a small JSON file read in a diff, and `review` now puts the lines that carry no evidence in front of the reviewer so that review is targeted rather than uniform (#68, #72). |
| 1.8 | `settle_ms` measures the agent's think time, not the app's | `CLOSED` — it is the last moment a check CHANGED its answer, not the last contributing observation (#63). Residual: when a retry crossed a model turn, that turn is inside the number. `BOUNDED` — the recorder can only measure between observations. |

## Stage 2 — COMPILE: what survives into the file

| # | Failure | Status |
|---|---|---|
| 2.1 | Only one observation per kind survives, and the dropped one was the real check | `CLOSED` — several checks of one kind all survive (#63). |
| 2.2 | A regex assertion silently downgraded to a literal | `CLOSED` — flags and `css_scope` travel with the assertion (#64). |
| 2.3 | A declared field nothing populates or nothing reads | `CLOSED` four times and worth watching forever: `origin` (#54), `viewport` (#57), `on_fail: heal` (#62, deleted rather than implemented), `review` (#72, read by the runner only as of this session). **This shape recurs; assume the next one exists.** |
| 2.4 | An unknown key in `expect` asserts nothing, silently | `CLOSED` — validated at load from both entry points (#72). |
| 2.5 | A secret written in plaintext into a file meant to be committed | `CLOSED` — `type=password` values become `${CHROMEBRIDGE_SECRET:NAME}` and replay refuses rather than typing an empty string. |
| 2.6 | **A variable reaches the input and the assertion but NOT the TARGET** | `CLOSED` this session — see below. #54 connected input↔assertion and left input↔target disconnected, which is the same defect one field over (rule 17) and the more dangerous half, because a target decides what is ACTED ON. |
| 2.7 | A valid key that cannot fail: `{"min": 0}` | `OPEN`, small. `validate_expect` accepts it and `tot < 0` is never true, so it is an assertion that asserts nothing — 2.4's hole wearing a legal key. Only reachable by hand edit; the recorder never emits `min` for a query and only emits `min: 1` for a search. |

## Stage 3 — LOCATE: binding a descriptor to an element

| # | Failure | Status |
|---|---|---|
| 3.1 | A DOM path breaks on the first re-render | `CLOSED` by design — we store a DECLARED descriptor, not a path, measured on 37 sites / 12,030 controls (#49). |
| 3.2 | A crowd of identical controls, resolved by ordinal, after a RE-SORT | `CLOSED` **for the witnessed minority and for the `resort` arm only** — 0.0% wrong at 94.3% correct, against 94.4% wrong with 0% refusals before (#72). The measurement that said "0% WRONG on every mutation" had no reorder arm, which is the lesson. **This row said "the witnessed majority" and that is arithmetically wrong** — see 3.3a. |
| 3.3 | …and 59.4% of ordinal-bearing descriptors have nothing to witness them | `OPEN`, deliberately accepted. Refusing them would pause ~14% of descriptors on an UNCHANGED page, which is losing the feature, not a safety cost. Geometry would cover 87.3% and is refused because it drifts (#23: 110px, #25: 1,097px) and the safeguard would fire on every reflow. |
| 3.3a | **The witness is sound on the `resort` arm and NOT on the `reorder` arm, and 3.2 quoted only the first** | `OPEN`, and it is a reporting defect in this document rather than a new code defect. #72's own table: `resort` witnessed **0.0% WRONG**, `reorder` witnessed **71.4% WRONG**. Re-derived here on a different 6-site sample (`audit_flow_resolve.py --sites 8`): resort witnessed 0.0%, reorder witnessed **55.6%** WRONG. The `reorder` arm permutes the crowd inside a FIXED scaffold, so an ANCHOR-only witness stays put while its element moves and the member that arrives at the recorded anchor is bound CONFIDENTLY and reported as a successful `moved` re-bind. #72 dismisses that arm as not physically realisable ("a renderer cannot move the buttons and leave their rows") — **that is an argument, not a measurement**, and the number quoted as the closure belongs to the other arm. Also: "the witnessed majority" is false on #72's own data — witnessed is 212 of 558 (**38.0%**) on resort and 238 of 586 (**40.6%**) on reorder, which is what 3.3's own 59.4% says two lines later. |
| 3.4 | Identity is live data (`Records 43` → `Records 44`) | `BOUNDED` — a LINK recovers on its declared destination and says so (#61); a BUTTON with a badge still pauses, because nothing else is declared. |
| 3.5 | The control has not RENDERED yet, reported as absent | `CLOSED` — target resolution gets the same bounded settle window as a postcondition (#59), and the recorded descriptor gets its WHOLE window before the alternate is offered, or a mid-render name gets written into the flow (#61). |
| 3.6 | A responsive layout at a different width genuinely lacks the control | `BOUNDED` — reported as a CAUSE on a resolve failure, width only, no threshold (#57, #59). |
| 3.7 | **A descriptor unique at record time becomes ambiguous later** | `CLOSED` — the cheap and the full descriptor are both stored, cheap-first with full as tie-break: 54% → 0% refusals, still 0% wrong (#49). |
| 3.8 | **The page is rendered in a different LANGUAGE than when it was recorded** | `OPEN`. The identity rung IS the accessible name, so a localised app invalidates every descriptor at once — the playground ships a `ja` chaos flag whose own comment says "the whole descriptor design rests on the accessible name", and this surface had no entry for it. Measured: a target recorded as `name='Sign in'` against a Japanese render reports *"no element on the page matches this step's target: tag='button' name='Sign in'"* and **names no cause**, while the same failure at a different viewport WIDTH appends *"The window is also a different WIDTH…"*. The page declares the fact (`<html lang>`); what is missing is the recorded half — `Flow` has no `lang`, and `viewport` is populated by `mcp_server` at stop time, so closing this needs a writer there as well as the reader here (rule 14). |

## Stage 4 — ACT: the action landing

| # | Failure | Status |
|---|---|---|
| 4.1 | A trusted click reports success and the page receives nothing | `BOUNDED` — not ours (Playwright's own mouse fails identically on that tab), now DETECTED by arming a capturing counter before dispatch and reading it after, with the one verified recovery named (#56). A navigating click destroys the probe, and that is reported as UNKNOWN, never as failure. |
| 4.2 | A flow that must span tabs cannot | `CLOSED` — a recorded `tabs_create_mcp` sets the current tab, same rule as the batch (#58), and an unreadable id STOPS rather than silently continuing in the old tab. |
| 4.3 | A popup left open by a previous step makes the next target unreachable | `BOUNDED` — the runner looks for the popup surface in its OWN listing and names it, saying nothing when there is none (#49). |
| 4.4 | An action whose effect is a CSS transition or late-arriving content, not a navigation | `CLOSED` — `await_quiet` waits for the DOM to stop being rewritten after an ACTING step, which is #70's mutation signal answering the question it was built for. Structural and text changes only, because an ad page runs attribute churn for ever. The quiet window is not a chosen number: #70 measured mid-build at 9–18ms and finished at 907–3514ms with NO overlap, so any cut in between separates them. B15/B15b/B15e fail without it; B15c and B15d are the controls that a quiet page says nothing and an observation-only batch asks nothing. |

## Stage 5 — VERIFY: the postcondition judging correctly

| # | Failure | Status |
|---|---|---|
| 5.1 | The runner asks before the SPA has painted | `CLOSED` — a bounded window to BECOME true (#55), plus the per-step `settle_ms` the recording demonstrated (#60). Not a weakening: it must still become true. |
| 5.2 | A mutating flow is not re-runnable in place | `INHERENT` — a flow that creates something changes the count it recorded. Any create-a-record test needs a fixture reset; the message names it among three causes that need different answers (#54). |
| 5.3 | `text` compared with `in`, so `Approved` passes against `Not Approved` | `CLOSED` — whitespace-normalised equality, justified by a declared fact (HTML collapses whitespace runs) rather than a chosen amount of slack (#72). |
| 5.4 | A dead click on a step whose only checks cannot fail | `CLOSED` this session — the guard and the hollow/unproven classifier did not compose, because a hollow assertion is a truthy `expect`. |
| 5.5 | **The postcondition passes and the app is in the wrong state anyway** | `INHERENT`, and eval 4 produced the live case: a filter and a sort set in one atomic fill, the app's two XHRs raced, the page settled showing the wrong order under a banner correctly reporting the DOM stable for 12 seconds. Nothing structural separates "settled right" from "settled wrong". The answer is agent-side discipline — verify a sort by reversing it — and that is a recording-quality question, not a runner one. |
| 5.6 | **An assertion tool that could not ANSWER, reported as an assertion that FAILED** | `CLOSED` this session — see below. A failed check is a fact about the page; a check that never ran is the absence of one, and the runner conflated them four different ways. |
| 5.7 | A failed replay leaves the app PARTLY mutated, and the reason does not say so | `BOUNDED`. `log` carries one entry per completed step and `at`/`of` carry the position, so it is derivable — but the sentence a reader sees first does not say "steps 0-3 already changed the app", which on an irreversible flow is the first question. No rollback exists and none is planned: a flow is a script, not a transaction. |

## Stage 6 — ENVIRONMENT: state the flow assumes

| # | Failure | Status |
|---|---|---|
| 6.1 | The app is not in the state the flow starts from | `CLOSED` — preconditions derived from what was observed before the first non-navigational action, checked BEFORE anything runs, proven live in both directions (#50, #72). Nothing else in the space does preconditions. |
| 6.2 | One fixture reset per RUN poisons every flow after the first | `CLOSED` — reset is per flow, which is what a per-test fixture means (#61). |
| 6.3 | A credential named one flow at a time goes stale | `CLOSED` — derived from the flows being run (#61). |
| 6.4 | The server is stale and silently writes an older format | `BOUNDED` — `sw_info` reports which server files changed since the process imported them (#61). It cannot reload itself. |
| 6.5 | **A flow with NO precondition inherits whatever the last run left, and 19 of 20 recorded flows have none** | `OPEN`, and the number is the finding. 6.1 is correct about the mechanism and silent about its reach: `require` is derived from the observations between the landing navigation and the first action, and `_checks` understands exactly three tools — `get_url`, `search_page`, `query_elements`. The tool `instructions=` (#45) and `browser_batch`'s description (#46) teach every agent to open with is **`read_page`**, which contributes nothing. Measured across `flows/*.flow.json`: **1 of 20 carries a `require`**, and that one was recorded deliberately to demonstrate the feature. The obvious fix is not a one-liner: `read_page`'s first line is `Current URL: <pathname + search>` while `expect.url` compares against `get_url`'s ABSOLUTE url, so deriving one from the other would put two spellings of one fact in the file (rule 17). |
| 6.6 | `run_flow(stop_after=N)` deliberately leaves a PARTIAL state that the next flow inherits | `OPEN`. The flag exists so a measurement can read a page that only exists after interaction (`OPEN.md` item 12), and by construction it ends mid-flow with a modal open, a filter applied or a half-filled form. Nothing resets between `run_flow` calls in a session, and by 6.5 the next flow usually has no precondition to notice. |
| 6.7 | Every flow in one `run_flows.py` batch shares ONE tab, and only the fixture flows are reset | `OPEN`. `tabs_create_mcp` is called once outside the loop; `_pg_reset` runs per flow but only under `--playground`, so the `ev-*` flows replay back-to-back in one tab with no isolation of any kind. Every flow on disk happens to begin with a `navigate`, which is what has hidden this — a flow recorded from an already-open page would inherit its predecessor's document. |
| 6.8 | An assertion on content that is a function of the CLOCK | `INHERENT`. `query.text` and `search.pattern` record what was rendered, and a date, a relative timestamp ("3 days ago") or a rate quoted today is red tomorrow. Distinct from 1.7: there the agent read it wrong, here the agent read it right and it decayed. The recorder cannot tell a stable string from a decaying one without guessing at its shape, which is the wordlist class (rule 4). |

## Stage 7 — REPORT: what the caller is told

The stage this document did not have, and principle 13 says it is where
features die: *the op router and the string contracts are the untested links.*
Everything above is reachable by `tools/test_flows.py`, which drives the runner
directly and never crosses into `mcp_server`'s renderer.

| # | Failure | Status |
|---|---|---|
| 7.1 | **`run_flow(stop_after=N)` cannot be rendered at all** | `OPEN`, and it has never worked over the wire. `_flow_report`'s `head` is a three-key dict lookup — `passed` / `failed` / `needs_decision` — and the runner's fourth status is `stopped_early`. Reproduced against **git HEAD**, not against anyone's working tree: `_flow_report({... "status": "stopped_early" ...})` raises `KeyError: 'stopped_early'`. FR22/FR22b/FR22c pin the RUNNER and pass; nothing pins the renderer. The fix is one dict entry in `mcp_server.py`, which is why it is not fixed here (that file is held by another agent this session); the check that should land with it is in the handover notes. |
| 7.2 | A `stop_after` at the LAST index reports `passed`, not `stopped_early` | Working as intended, recorded so it is not re-filed: every step ran and every assertion was checked, so there is nothing partial to announce. Callers key on the `stopped_early` flag, which is absent in exactly that case. |

---

## Closed this session, with the measurement each one took

### 2.6 — the override reached the input and the assertion and not the target

The headline use of variables is "run the same flow with a different name".
The shape that breaks it is the commonest one there is: **type a name, submit,
then act on the thing the app just made** — whose accessible name IS the value
that was typed. The input took the override, the assertion took it since #54,
and the TARGET kept the literal.

Measured both directions against a fake bridge before the fix:

| the app | before | after |
|---|---|---|
| clean | PAUSED — *"no element on the page matches this step's target: name='atlas-svc'"*, a false description of what happened, since the flow itself renamed it | acts on the new record; the run then fails on the **url** assertion, which contains the value as a SUBSTRING and therefore legitimately stays literal (the documented cost of exact-equality) |
| still holding the record a PREVIOUS run made (5.2, `INHERENT`) | **PASSED, having clicked the OLD record** — and the url postcondition, stale in exactly the same way, confirmed it | acts on the record THIS run made |

The second row is the #10/#11/#12 family: act somewhere else, report success.

**And then LIVE, because #43's rule is that fixtures encode what you thought
of.** A flow was RECORDED through the real extension, bridge, op router and
`mcp_server` tool functions against `saas_playground` — log in, create a
project, then click the record it just made — and replayed with
`vars={"project_name": "zeta-svc"}` against the app still holding `atlas-svc`
from the recording. Only `core/flows` differed between the arms:

| arm | recorded target | replay | opened |
|---|---|---|---|
| pre-fix | `name: "atlas-svc"` | **PASSED 5/5** | `/projects/5` — **atlas-svc**, the record the PREVIOUS run made |
| fixed | `name: "{{project_name}}"` | failed 4/5 | `/projects/6` — **zeta-svc**, the record THIS run made |

A clean green pass on the wrong record became a true red on the right one. The
`failed 4/5` is honest and worth naming: that step's postcondition is the
recorded url `…/projects/5`, which CONTAINS the record's id rather than equal-
ling a variable, so exact-equality cannot reach it. Previously the stale url
matched because the step had opened the stale record — the two errors cancelled.
A flow of this shape needs a fixture reset (5.2) or an assertion that is not
id-bearing.

**It is also on disk, not hypothetical.** `crm-records-filter.flow.json`, recorded
live against a real app, has step 2 targeting `name='ZZ Flow'` — the text step 1
types, which became that input's accessible name once the typed value displaced
the placeholder. The flow's own variable breaks the flow.

The fix parameterises the target with the same exact-equality rule as the
assertion half, **restricted to variables an EARLIER step typed**: a target
exists before its own step runs, so it cannot have been named by a value that
step has not typed yet, and the recording's own order says which. The residual
— type "Save", then click an unrelated "Save" — is named in `review` rather than
hidden, and under an override it fails loudly rather than silently. Two further
halves came with it: an undeclared `{{name}}` in an **assertion** was resolved
with the missing names discarded and the placeholder then searched for
literally, where the input path had refused one since FV4; and a proposed patch,
built from the page, would have hard-coded this run's value and deleted the
parameterisation the recorder had just written (rule 14, reached from the repair
end).

Checks: FV7–FV9b. FV7, FV7b, FV7d, FV8, FV9 fail against the pre-fix code; FV7c
(a target coinciding with a value typed LATER keeps its literal), FV7e (a plain
replay binds to exactly what it recorded), FV8b and FV9b pass in both arms.

### 5.6 — a tool that could not answer, reported as a page that failed

Every way a verification call can go wrong was handled on the ACT path since
FR16 and on **neither** VERIFY path. Measured with a fake bridge:

| | before | after |
|---|---|---|
| the gate refuses `search_page` | *"could not read a hit count out of search_page for 'Welcome' — the result-string contract moved"* | *"search_page was REFUSED, so it never looked … and this assertion did not run"*, quoting the tool |
| the user hits PAUSE mid-run | the same sentence, after a 6s poll | the same as above, immediately |
| the gate refuses `get_url` | *"url is 'Permission required: ChromeBridge is not allowed to act on …', recorded 'https://…'"* | as above |
| the bridge drops | an **uncaught** `RuntimeError` out of `start()`, with no step named, no `at`, no `log` and no elapsed, on a flow whose earlier steps had already mutated the app | `FAILED`, naming the step and saying it RAN while its postcondition could not be evaluated |

The first three name a cause nobody verified and send the reader hunting for a
parser mismatch that does not exist — principle 6, and `recorder.query_total`'s
own docstring records that exact sentence being printed for an expired session,
then fixed the ZERO case and left the REFUSED one. The fourth is FR16's defect
in the two places FR16 did not reach.

The refusal check is asked **only when the parse failed**, which is what makes
it free of false positives: a tool that answered normally parses, so a page
whose own text contains one of the markers (`search_page` quotes the context it
matched) never reaches it. An `Unanswerable` is **not retried** inside the
settle window — a gate refusal and a kill switch are decisions by the user, and
re-asking for six seconds spends the window on an answer that cannot change.

Checks: FR23–FR23f. FR23, FR23b, FR23c, FR23d fail against the pre-fix code;
FR23e (a merely unreadable result still reports the contract, which is right for
the case that message was written for) and FR23f (an assertion that was
evaluated and failed still reports the comparison) pass in both arms — without
them, "call every failure Unanswerable" would satisfy the other four while
deleting the distinction the change exists to make.

## What is genuinely not covered

1. **The oracle problem (1.7).** A flow records what the agent believed. If the
   agent misread the page, the flow enshrines it and goes green for ever. No
   amount of engineering inside the recorder reaches this; it is why `review`
   exists and why a flow file is deliberately small enough to read in a diff.
2. **Settled-but-wrong (5.5).** Measured live, no structural fix available.
3. **The unwitnessed 59.4% (3.3), and the arm split above it (3.3a).** Accepted
   with their numbers, not hidden.
4. **No headless CI runner for arbitrary flows** beyond `run_flows.py`'s
   fixture-and-local set, and **no variable extraction beyond typed values**, so
   a flow asserting on a generated id or a timestamp is brittle by construction
   (6.8).
5. **Starting state (6.5–6.7) — CLOSED, except for the files already on
   disk.** The precondition now reaches the opening every agent is taught
   (`read_page`'s first line became a `path` check), and `run_flows.py` gives
   each flow its own tab, so one replay cannot inherit the previous one's page.
   Demonstrated with a flow whose leading `navigate` was stripped: it stops
   before step 0 naming both paths. What remains is that the 20 files recorded
   before this acquire a precondition only when re-recorded.
6. **The language the app is rendered in (3.8).** The one environment variable
   that invalidates every descriptor at once, and the only one with no cause
   note.

## The rule this list is really about

Every entry above that is `CLOSED` was closed because something RAN, not
because something was read: a live eval, an ablation against the pre-fix code,
or a measurement with its drift floor taken first. Three of them were found by
a fixture being run against the broken code and passing anyway. The next
failure on this surface will be found the same way, which is the argument for
keeping the live passes rather than trusting the suite.
