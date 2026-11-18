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
| **working anywhere in this repo** | `PRINCIPLES.md` — non-negotiable, 21 rules |
| **delegating any of this to a sub-agent** | `ORCHESTRATION.md` — serial browser work, propose-don't-apply, and the three agent headlines this project had to correct before shipping them. Half of what agents hand back needs checking, and the first bad brief in it was mine |
| asking "does this work on sites we never tuned on" | `docs/research/GENERALITY-LIVE-2026-11.md` → CLAUDE.md **#85**. 260 live out-of-sample sites, 34,913 visible controls, **0 identities lost** — and 0 again in a state reached by OPENING a disclosure, which is the first measurement here of anything but first paint. Read its "still unmeasured" section before quoting it: real legacy enterprise UI is still absent, and 152 of 369 candidates never rendered |
| asking "does it still work once the page has been USED" | `docs/research/STAGE-GENERALITY-2026-11.md` → CLAUDE.md **#89**. 255 live out-of-sample sites, **325 post-interaction reads**, up to 4 compounding interactions, **0 identities lost on the STRICT definition**. Read the strict-vs-lenient section before quoting any "0 lost" figure anywhere in this repo: deleting 67 of 133 entries moves lenient by 1 and strict by 27 |
| asking whether a control can be REACHED after the page has been used | `docs/research/FINDABILITY-AT-STAGE-2026-11.md` -> CLAUDE.md **#92**. 13,682 probes across 254 live sites, **0 misses**, and the population revealed BY an interaction is no harder to reach than one always present. Read its blanked-arm section before quoting the 1.0000: rows whose identity the listing deliberately removes are scored separately at 0.8916 |
| asking whether the name we print is the RIGHT name | `docs/research/NAME-CORRECTNESS-2026-11.md` -> CLAUDE.md **#93**. 100,332 rows against Chrome's own AX tree across 251 live sites — the only INDEPENDENT oracle here, since every other ruler scores the collector against our own tools. **Read its class table before quoting any figure**: the pooled 0.7519 is not an error rate, and Chrome is an oracle rather than ground truth |
| touching cross-origin frames, or anything needing the LIVE extension | `docs/research/HOVER-AND-FRAMES-2026-11.md` -> CLAUDE.md **#94**. **Read it before writing "Playwright cannot exercise this"** — that belief sat in five places, stopped a capability being built, and `run_flows.py` had been the counter-example since #50. `tools/audit_frames_live.py --selftest` is a CI step |
| asking whether a CONSENT SHEET in a cross-origin frame goes unnoticed | `docs/research/CMP-FRAMES-2026-11.md` -> `docs/OPEN.md` item 7, closed **DON'T BUILD**. The correctness gap is real and **does not occur**: 95 of 143 live sites render a cross-origin frame (710 of them) and **0** carry a dialog the page-level scan would fire on, because iframe CMPs declare `role=dialog aria-modal` in the TOP document and put only the content behind the boundary. **Read its probe-defect section before trusting any live frame count**: a per-run Playwright handle race reported zero frames on 56 rows while every MCP-side field looked healthy, and the firing proof did not catch it |
| touching the readiness tiers | `docs/research/READINESS-RESIDUE-2026-11.md` → CLAUDE.md **#88**. Why `textContent =` is a re-text and not a structural change, the three tiers, and the one false quiet recorded as DON'T BUILD with the number that kills it |
| asking how record/replay BREAKS | `docs/research/FLOWS-CONCEPTUAL-BREAKS-2026-11.md` → CLAUDE.md **#90**/**#91**. 15 modes with DETECTED / SILENT / REFUSED each. Read M4 before trusting any green flow suite: it is the case CI structurally cannot catch |
| asking whether a regex or a wordlist will break on an unfamiliar site | `docs/research/AUDIT-PATTERNS-2026-11.md` — the adversarial audit of PRINCIPLES 1 itself; the "no natural-language wordlist reads page text" claim SURVIVED it. Pair it with `docs/research/PATTERN-SURFACE-2026-11.md` -> CLAUDE.md **#82**, which measures what `tools/audit_patterns.py` CANNOT see: it reads regex literals only, so 789 further `.includes` / `classList` / `.slice` / threshold sites sat outside its reach, and a lone UTF-16 surrogate in one of them killed the server process |
| hardening record/replay against a SILENT wrong answer | **Start at `docs/research/FLOW-SILENT-BIND-2026-11.md`** — the ranked list of what can still bind to the wrong element and report PASS, and read it before trusting the two papers below, because its first entry is a regression INTRODUCED by the fix the second one proposes. Then `docs/research/FLOW-FRAGILITY-2026-11.md` — ranked by (likelihood on a real business app) x (false PASS vs false FAIL), because a false PASS is far worse than a false FAIL. Then `docs/research/FLOW-UNBREAKABLE-2026-11.md` -> CLAUDE.md **#83**, the ordinal-witness measurement, the attribute-atom trap a two-load stability check cannot catch, and the one thing Playwright's row-scoping still does better than us |
| acting on a ref you observed earlier | `docs/research/OBSERVE-ACT-2026-11.md` -> `docs/OPEN.md` item 1. Most of what the literature worries about is ALREADY refused by `_rectForPage`'s action-time pre-flight; the residue is a label flipping in place and a React-unkeyed re-sort. Designed and priced, deliberately NOT shipped — it gates irreversible actions and that deserves a live pass |
| reading the readiness matrix and its false quiets | `docs/research/READINESS-ADVERSARIAL-2026-11.md` — 18 hostile shapes at 4 offsets. **It opens with its own STATUS banner telling you to read RESIDUE first**, because both of its top-ranked defects have since shipped and its totals describe a build nobody runs any more |
| wanting to know what the field published | `docs/research/SURVEY-2026-11.md` — every claim read off the arXiv page rather than a search-result summary, and §4 NAMES two figures that search summaries attributed to papers and that are not in the source, so nobody re-imports them |
| reviewing work you did yourself | `docs/research/SELF-AUDIT-2026-11-16.md` — read its second paragraph first. It says in as many words that it is NOT an independent review, because the same person wrote the code and the audit; it is the measurement half, which does not depend on who runs it |
| catching up on the most recent work | CLAUDE.md **#86–#104**, then `tools/bench_turns/eval9/CLOSEOUT.md` — the head-to-head that came back a TIE because of a guard shipped hours before it ran, and `eval9/PREREG.md`'s nine amendments, four of which record a mistake in the eval's own setup or scorer. Then #82–#85: five parallel audits, eight defects, and the generality number above. Then #86–#94: CI red for three days on two breaks invisible on the version developed against, five post-interaction measurements, and three claims in this repo's own literature corrected — one of which had been used to decline building a capability. #95 closes the last open item in the DOM representation as a MEASURED DON'T BUILD, and carries the sharpest measurement lesson in the log: a passing firing proof does not establish that the probe worked on the run that produced the numbers |
| changing the DOM collector | `PRINCIPLES.md` → `REPRESENTATION.md` → CLAUDE.md #27, #28, #29, #37 |
| changing what the listing *says* | `REPRESENTATION.md` → CLAUDE.md #13, #22, #24 (truncation and silence) |
| touching readiness / settling | `READINESS.md` — this is the active open problem |
| changing the flow recorder | `FLOWS.md` → `FLOWS-FAILURE-SURFACE.md` (every way record/replay can break, by stage, with a status each) → CLAUDE.md #49, #57, #61, #68 |
| adding or changing a measurement | `MEASUREMENT.md` — **read this before you quote a number** |
| asking whether the listing is *enough*, not just complete | `SUFFICIENCY.md` → `tools/measure_sufficiency.py` |
| asking whether an element can be REACHED, not just whether it survived | `tools/measure_findability.py` → CLAUDE.md #74, #75. Nearly every ruler here scores PRESENCE; #74 found 118 elements present in all of them and unreachable by their own printed label |
| running a head-to-head | `EVALS.md` → `tools/bench_turns/` → **read eval7's AND eval9's PREREG amendments before designing one.** eval7: a generator that merges a task file must be read against the harness that normally consumes it, and both arms can read the other's server instructions. eval9: fix the bar before any data exists and do not move it; a task both arms can shortcut by recalling a URL is excluded, not scored; and the scorer is as capable of a detector-that-cannot-fire as the product is |
| about to claim the representation is COMPLETE | **you cannot, from any ruler in this repo.** Every one scores PRESENCE — presence, `lost_identities`, Mind2Web recall, sufficiency DS, findability. `docs/OPEN.md` 4l is a control whose two buttons were present, listed, named, clickable and carried OPPOSITE meanings, and `measure_findability` scores it a hit at 0.9996. Live agents are the only thing that has ever caught that class |
| about to claim something is general | `PRINCIPLES.md` §I → `tools/audit_patterns.py` |

## The pages

| File | What it holds |
|---|---|
| `PRINCIPLES.md` | The 21 invariant rules, each with the failure that earned it |
| `REPRESENTATION.md` | What the listing is: existence, identity, state, presentation, and every number with its ruler |
| `READINESS.md` | "Accurate at any stage" — the one open structural gap, its evidence and the design |
| `FLOWS.md` | Record and replay: descriptors, assertions, the oracle problem, the runtime |
| `MEASUREMENT.md` | The rulers. What each one can and cannot see, and how each has lied |
| `SUFFICIENCY.md` | The one ruler that is not about presence: is the element a task needs *distinguishable*? What it cannot answer, and why it is not circular |
| `EVALS.md` | The head-to-head protocol and the results index |
| `OPEN.md` | The single ranked list of open questions, each with its evidence |
| `SHOWCASE.md` | Content written for posting, with the claims it is not allowed to make |
| `research/` | **Dated audits and surveys.** One file per investigation, named `<TOPIC>-<YYYY-MM>.md`. These are the working papers a `CLAUDE.md` entry cites; they hold the full matrix, the per-site rows and the rejected candidates that an entry only summarises. They are NOT superseded when the entry is written — the entry is the claim, this is the evidence |

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

0. **A long investigation writes its working paper in `docs/research/` as it
   goes**, dated, with the full matrix and every candidate it rejected and the
   number that rejected it. An entry in `CLAUDE.md` summarises; the working
   paper is what someone re-deriving the result actually needs, and it is the
   difference between a claim and evidence.
1. **A finding goes in `CLAUDE.md`**, chronologically, with its evidence
   and with what you got wrong on the way. That entry is the citation.
2. **Then update the topical page**, pointing at the new entry number.
3. **`OPEN.md` is a working list, not an archive** — when something closes,
   delete it from there and leave the history in `CLAUDE.md`. A stale open item
   sends the next reader to re-derive something already done.

A retraction at the bottom of a long entry does not retract its heading. When
you close something, fix every place that claims it is open — the
closed-shadow-root limitation was disclaimed in four user-facing documents for
five entries after it shipped working.
