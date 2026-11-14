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
| catching up on the most recent work | CLAUDE.md **#70** (readiness), **#71** (the generality audit), **#72** (the ordinal/witness problem), **#73** (the Mind2Web audit) |
| changing the DOM collector | `PRINCIPLES.md` → `REPRESENTATION.md` → CLAUDE.md #27, #28, #29, #37 |
| changing what the listing *says* | `REPRESENTATION.md` → CLAUDE.md #13, #22, #24 (truncation and silence) |
| touching readiness / settling | `READINESS.md` — this is the active open problem |
| changing the flow recorder | `FLOWS.md` → CLAUDE.md #49, #57, #61, #68 |
| adding or changing a measurement | `MEASUREMENT.md` — **read this before you quote a number** |
| running a head-to-head | `EVALS.md` → `tools/bench_turns/` |
| about to claim something is general | `PRINCIPLES.md` §I → `tools/audit_patterns.py` |

## The pages

| File | What it holds |
|---|---|
| `PRINCIPLES.md` | The 20 invariant rules, each with the failure that earned it |
| `REPRESENTATION.md` | What the listing is: existence, identity, state, presentation, and every number with its ruler |
| `READINESS.md` | "Accurate at any stage" — the one open structural gap, its evidence and the design |
| `FLOWS.md` | Record and replay: descriptors, assertions, the oracle problem, the runtime |
| `MEASUREMENT.md` | The rulers. What each one can and cannot see, and how each has lied |
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
