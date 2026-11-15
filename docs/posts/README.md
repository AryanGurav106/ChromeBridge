# The posting queue

The brief was to post REGULARLY so people get the idea, "not just numbers".
One draft is not a cadence, so this is the pipeline: each post below is already
backed by an artefact in this repo, so writing it is an hour, not a project.

**The rule that makes this sustainable:** a post ships only when its claim can
be checked against something committed here. Every number in post 001 was
re-derived from the file it describes before the draft was committed. That is
slower than writing from memory and it is why none of these will need a
correction later.

**Ordering principle:** lead with a capability nobody else has, then the
evidence, then the method. A post that opens with a benchmark table buries the
thing being shown, which is why 001 leaves the head-to-head out entirely.

| # | Post | Source already in repo | Status |
|---|---|---|---|
| 001 | Record and replay: the assertions come free because we record the AGENT, not a human | `flows/todomvc-add-items.flow.json`, CLAUDE.md #49/#55/#60/#72 | **DRAFTED**, needs sending |
| 002 | We ran 20 blind tasks against Claude-in-Chrome. 110 turns vs 176. | `tools/bench_turns/eval4/` — prereg, tasks, referee key, analyse.py | material complete |
| 003 | Four defects in one session, and none of them were in the product | eval 4 Amendments 6 & 7: the ruler was broken four ways | material complete |
| 004 | Your agent is reading a page that is still being built, and nothing tells it | CLAUDE.md #70, `docs/READINESS.md`, R11–R23 | material complete |
| 005 | A table with a hidden column handed back the wrong number, silently | this session's TB15, `tools/audit_table_hidden_cells.py` | material complete |
| 006 | Every way record-and-replay can break, by stage | `docs/FLOWS-FAILURE-SURFACE.md` | material complete |
| 007 | "Nothing went missing" is not "what is left is enough" | `docs/SUFFICIENCY.md`, DS 0.933 | material complete |

## What each post must NOT do

- **Quote a bare "96%".** It is a band, 95.1–98.1 leave-one-site-out, and the
  element-itself figure is 85.5%. CLAUDE.md #73 says quote ~96%, never 96.0%.
- **Quote eval 4's zero-wrong on flow descriptors without its qualifier.** That
  zero is for WITNESSED descriptors on a realistic re-sort. 59.4% have no
  witness and are unchanged (#72).
- **Imply the head-to-head says anything about the consent model.** The gate was
  armed for the run and the pre-registration says so explicitly.
- **Present a pre-registered subset we FAILED as a win.** H4, the
  interaction-heavy subset, is 7/9 and does not clear. It was named as a test we
  might fail before any data existed and it gets the same prominence.

## The honest framing for the series as a whole

The interesting thing here is not that the numbers are good. It is that the
measurement apparatus was wrong more often than the product this session —
four ruler defects against two product defects — and all four were caught
because something RAN rather than because something was read. That is the
story worth telling repeatedly, and it is the one that will still be true in a
year.
