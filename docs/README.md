# docs/ — the literature

`CLAUDE.md` is the **chronological ledger** — each entry a measured
finding, written as it happened. (No count is
stated here on purpose: a number in a second place is a number that drifts.) It is the primary source and nothing here
replaces it.

This directory is the **topical index into it**. It exists because a long
chronological log is excellent history and useless onboarding — a subagent asked to work on
the collector should not have to read nine months of entries to learn the four
rules that govern it.

Every page here points back at the entry that earned each claim. If a page and
`CLAUDE.md` disagree, `CLAUDE.md` is right and the page is stale — say so and
fix it.

---

## Reading order, by what you are about to do

| You are… | Read, in order |
|---|---|
| **working anywhere in this repo** | `PRINCIPLES.md` — non-negotiable, 20 rules |
| catching up on the most recent work | CLAUDE.md **#76–#80**, then `tools/bench_turns/eval7/CLOSEOUT.md` — the head-to-head that came back a TIE and produced 22 defects, and `tools/bench_turns/eval7/PREREG.md`'s five amendments, three of which record a mistake in the eval's own setup |
| changing the DOM collector | `PRINCIPLES.md` → `REPRESENTATION.md` → CLAUDE.md #27, #28, #29, #37 |
| changing what the listing *says* | `REPRESENTATION.md` → CLAUDE.md #13, #22, #24 (truncation and silence) |
| touching readiness / settling | `READINESS.md` — this is the active open problem |
| changing the flow recorder | `FLOWS.md` → `FLOWS-FAILURE-SURFACE.md` (every way record/replay can break, by stage, with a status each) → CLAUDE.md #49, #57, #61, #68 |
| adding or changing a measurement | `MEASUREMENT.md` — **read this before you quote a number** |
| asking whether the listing is *enough*, not just complete | `SUFFICIENCY.md` → `tools/measure_sufficiency.py` |
| asking whether an element can be REACHED, not just whether it survived | `tools/measure_findability.py` → CLAUDE.md #74, #75. Nearly every ruler here scores PRESENCE; #74 found 118 elements present in all of them and unreachable by their own printed label |
| running a head-to-head | `EVALS.md` → `tools/bench_turns/` → **read eval7's PREREG.md amendments before designing one**: a generator that merges a task file must be read against the harness that normally consumes it, and both arms can read the other's server instructions |
| about to claim the representation is COMPLETE | **you cannot, from any ruler in this repo.** Every one scores PRESENCE — presence, `lost_identities`, Mind2Web recall, sufficiency DS, findability. `docs/OPEN.md` 4l is a control whose two buttons were present, listed, named, clickable and carried OPPOSITE meanings, and `measure_findability` scores it a hit at 0.9996. Live agents are the only thing that has ever caught that class |
| about to claim something is general | `PRINCIPLES.md` §I → `tools/audit_patterns.py` |

## The pages

| File | What it holds |
|---|---|
| `PRINCIPLES.md` | The 20 invariant rules, each with the failure that earned it |
| `REPRESENTATION.md` | What the listing is: existence, identity, state, presentation, and every number with its ruler |
| `READINESS.md` | "Accurate at any stage" — the one open structural gap, its evidence and the design |
| `FLOWS.md` | Record and replay: descriptors, assertions, the oracle problem, the runtime |
| `MEASUREMENT.md` | The rulers. What each one can and cannot see, and how each has lied |
| `SUFFICIENCY.md` | The one ruler that is not about presence: is the element a task needs *distinguishable*? What it cannot answer, and why it is not circular |
| `EVALS.md` | The head-to-head protocol and the results index |
| `OPEN.md` | The single ranked list of open questions, each with its evidence |
| `SHOWCASE.md` | Content written for posting, with the claims it is not allowed to make |

## Documents at the repo root (older, still current)

| File | What it holds |
|---|---|
| `CLAUDE.md` | The ledger. Primary source. |
| `README.md` | The front door, for someone deciding whether to use this |
| `RESEARCH.md` | External prior art surveys, by date |
| `BENCHMARK.md` | The head-to-head numbers |
| `AUDIT_DOM_GENERALITY.md` | The ablation study that disproved "library signatures are boosters, never gates" |
| `AUDIT_GENERALITY.md` | The eight-audit generality sweep |
| `FLOW_RECORDER_PLAN.md` | The flow feature's design and rejected alternatives |
| `EXTENSION_SETUP.md` | Loading the extension |
| `tools/README.md` | Per-suite inventory; `run_tests.py --list` is the authority |

---

## How to add to this literature

1. **A finding goes in `CLAUDE.md` first**, chronologically, with its evidence
   and with what you got wrong on the way. That entry is the citation.
2. **Then update the topical page**, pointing at the new entry number.
3. **`OPEN.md` is a working list, not an archive** — when something closes,
   delete it from there and leave the history in `CLAUDE.md`. A stale open item
   sends the next reader to re-derive something already done.

A retraction at the bottom of a long entry does not retract its heading. When
you close something, fix every place that claims it is open — the
closed-shadow-root limitation was disclaimed in four user-facing documents for
five entries after it shipped working.
