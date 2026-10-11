# Flow generality eval — pre-registration

Written BEFORE the app list exists and before any run. #45's headline had to be
withdrawn when the prompt turned out to mandate the behaviour it measured, and
that was only catchable because the prompt file still existed. So: this file
first, apps second, runs third.

## The question

Everything measured about this feature so far measures the LOCATOR — can a
descriptor pick out one element on an arbitrary page. That is 37 frozen sites,
12,030 controls, 23 sites and 2,376 descriptors under six mutations at 0% WRONG.

The LOOP — record an agent's run, compile it, replay it — is demonstrated on
**five** apps, two of which I wrote, and CI replays **one**. This eval measures
the loop.

## Design

- **8 apps**, named by an agent told only to describe short public browser
  interactions, with no knowledge that any feature is under test and no
  knowledge of this file.
- **Serial**, one recording agent at a time. #39 recorded six parallel agents
  on one Chrome corrupting each other's tab groups.
- Each agent: create a tab, record a 3-5 step flow, STOP, replay it once, report.
- **Scored from ARTEFACTS** — the saved `*.flow.json` and the `run_flow` output —
  never from the agent's own prose. #47 found a scorer counting the handback as
  a turn and an answer-extractor returning null, both by a self-report
  disagreeing with the transcript.
- The permission gate stays ON and per-origin. `ALLOW_ALL_ORIGINS` stays `false`.
  Origins are granted by the user in the side panel, which is the product's
  real first-run path. An eval that disables the consent model measures a
  product nobody runs.

## Metrics

| | |
|---|---|
| **M1 PRIMARY** | flows that REPLAY GREEN immediately after recording |
| **M2** | flows that replay green AGAIN on a second replay (idempotence) |
| **M3 FALSIFIER** | a step that binds to the WRONG element and reports success. **Target 0.** Any occurrence invalidates the feature, not the eval |
| **M4** | recordings where #57's witness check fires (an assertion already true) |
| **M5** | distinct DEFECT CLASSES found that no existing fixture models |

## Predictions, fixed now

- **P1** M1 ≥ 6/8. The locator is measured; failures should be in the loop.
- **P2** The failures cluster in three places: SPA settle timing, a postcondition
  that is not reproducible (a clock, a counter, a rotating item), and a popup or
  dialog left open changing the start state (#49 recorded exactly that).
- **P3** M5 ≥ 2. Six of the last eight log entries found something live that no
  fixture modelled; there is no reason this one is different.
- **P4** M4 ≥ 1. A naive recording asserting something already true is the
  easiest mistake this feature allows, and I made it twice myself.
- **P5** M3 = 0.

## What counts as a pass

M1 counts a replay reported `PASSED` by `run_flow` with at least one step
carrying a postcondition. A flow with zero assertions is recorded as such and
does NOT count toward M1 — it can only detect a control going missing, which is
not what this feature claims.

## What would make me report this as a failure

- M3 > 0 — a silent mis-bind is the #10/#11/#12 family and is disqualifying.
- M1 < 4/8 — the loop does not generalise and the five-app demonstration was
  the sample flattering itself (#25).

---

## AMENDMENT 1 — the gate is armed off for the run

Recorded BEFORE any app is driven. The section above says the gate stays on
and the user grants eight origins by hand; the user asked instead to allow all
origins for the duration. Changing an instrument after data exists is the move
that invalidates a pre-registration, so this is written while there is no data,
and the defence has to be checkable rather than asserted (#47's AMENDMENT 2
set this precedent and its reasoning is reused).

**Why it does not touch any metric here.** M1-M5 ask whether a recorded flow
replays, whether it binds to the right element, and whether the recording
asserts anything real. The gate decides only whether the FIRST op on a new
origin is refused; it has no path into descriptor resolution, postcondition
evaluation or the recorder's compile. Contrast #47, where the same decision
needed defending because the metric was TURNS and a refusal costs one.

**What this eval therefore cannot say.** Nothing whatever about the consent
model, its first-run path, or what per-origin granting costs. It must not be
quoted as evidence about any of those.

**Restore, verified three ways** (#47 found a flag restored on disk is NOT
restored in the browser while the bridge holds a live socket, because the MV3
worker is never evicted to re-read it):

1. `ALLOW_ALL_ORIGINS` back to `false` in `extension/background.js`
2. `git diff` on that file empty
3. `node tools/test_permissions.js` reporting 22/22 with NO "gate off" caveat

and an extension RELOAD, which is the only thing that makes the worker re-read
the flag. The window is the eval and nothing else.

---

## AMENDMENT 2 — round two, after the fixes

Recorded before any re-recording. Round one found 20 defects; 13 are fixed.
This round re-records the SAME eight apps with the fixed recorder, plus
several flows against the Boxsy staging app, to answer one question:

**Do the fixed assertions actually bite on a real app?**

**The prediction, fixed now: M1 should get WORSE, not better.** Round one's
7/8 included flows whose assertions could not fail — `#combo1 == 1` on the two
steps that pick an option, a Close step with no `expect` at all, three typing
steps with nothing that checks what was typed. Those now compile into `text`
assertions, absence assertions and readable values. **A flow that silently did
nothing and passed should now fail.** If M1 comes back 8/8 with no change in
what is asserted, the fixes did not reach real recordings and this round says
so.

Same scoring: from the saved `*.flow.json` and `run_flow`'s output, never from
an agent's prose. The gate is armed off again at the user's request, for the
same reason and with the same restriction as AMENDMENT 1 — it touches no
metric here, and this round says nothing about the consent model.
