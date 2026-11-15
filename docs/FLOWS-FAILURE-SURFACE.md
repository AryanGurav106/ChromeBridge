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

## Stage 3 — LOCATE: binding a descriptor to an element

| # | Failure | Status |
|---|---|---|
| 3.1 | A DOM path breaks on the first re-render | `CLOSED` by design — we store a DECLARED descriptor, not a path, measured on 37 sites / 12,030 controls (#49). |
| 3.2 | A crowd of identical controls, resolved by ordinal, after a RE-SORT | `CLOSED` for the witnessed majority — 94.4% wrong with 0% refusals before, 0.0% wrong at 94.3% correct after (#72). The measurement that said "0% WRONG on every mutation" had no reorder arm, which is the lesson. |
| 3.3 | …and 59.4% of ordinal-bearing descriptors have nothing to witness them | `OPEN`, deliberately accepted. Refusing them would pause ~14% of descriptors on an UNCHANGED page, which is losing the feature, not a safety cost. Geometry would cover 87.3% and is refused because it drifts (#23: 110px, #25: 1,097px) and the safeguard would fire on every reflow. |
| 3.4 | Identity is live data (`Records 43` → `Records 44`) | `BOUNDED` — a LINK recovers on its declared destination and says so (#61); a BUTTON with a badge still pauses, because nothing else is declared. |
| 3.5 | The control has not RENDERED yet, reported as absent | `CLOSED` — target resolution gets the same bounded settle window as a postcondition (#59), and the recorded descriptor gets its WHOLE window before the alternate is offered, or a mid-render name gets written into the flow (#61). |
| 3.6 | A responsive layout at a different width genuinely lacks the control | `BOUNDED` — reported as a CAUSE on a resolve failure, width only, no threshold (#57, #59). |
| 3.7 | **A descriptor unique at record time becomes ambiguous later** | `CLOSED` — the cheap and the full descriptor are both stored, cheap-first with full as tie-break: 54% → 0% refusals, still 0% wrong (#49). |

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

## Stage 6 — ENVIRONMENT: state the flow assumes

| # | Failure | Status |
|---|---|---|
| 6.1 | The app is not in the state the flow starts from | `CLOSED` — preconditions derived from what was observed before the first non-navigational action, checked BEFORE anything runs, proven live in both directions (#50, #72). Nothing else in the space does preconditions. |
| 6.2 | One fixture reset per RUN poisons every flow after the first | `CLOSED` — reset is per flow, which is what a per-test fixture means (#61). |
| 6.3 | A credential named one flow at a time goes stale | `CLOSED` — derived from the flows being run (#61). |
| 6.4 | The server is stale and silently writes an older format | `BOUNDED` — `sw_info` reports which server files changed since the process imported them (#61). It cannot reload itself. |

---

## What is genuinely not covered

1. **The oracle problem (1.7).** A flow records what the agent believed. If the
   agent misread the page, the flow enshrines it and goes green for ever. No
   amount of engineering inside the recorder reaches this; it is why `review`
   exists and why a flow file is deliberately small enough to read in a diff.
2. **Settled-but-wrong (5.5).** Measured live, no structural fix available.
3. **The unwitnessed 59.4% (3.3).** Accepted with its number, not hidden.
4. **No headless CI runner for arbitrary flows** beyond `run_flows.py`'s
   fixture-and-local set, and **no variable extraction beyond typed values**, so
   a flow asserting on a generated id or a timestamp is brittle by construction.

## The rule this list is really about

Every entry above that is `CLOSED` was closed because something RAN, not
because something was read: a live eval, an ablation against the pre-fix code,
or a measurement with its drift floor taken first. Three of them were found by
a fixture being run against the broken code and passing anyway. The next
failure on this surface will be found the same way, which is the argument for
keeping the live passes rather than trusting the suite.
