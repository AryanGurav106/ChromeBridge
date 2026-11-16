# The posting queue

The brief was to post REGULARLY so people get the idea, "not just numbers".
One draft is not a cadence, so this is the pipeline: each post below is already
backed by an artefact in this repo, so writing it is an hour, not a project.

**Six are drafted now (001, 002, 003, 004, 009, 010).** At one a week that is over a
month of cadence already sitting in the repo, which was the point of building a
queue rather than writing one post well.

**Ordering note for the first four sends.** 009 should go EARLY, not last. It is
the only one whose headline is a number moving against us, and a series that
opens with wins and buries the correction reads as marketing however true each
post is. 001 (capability) then 009 (the correction) then 002 (the comparison) is
the order that earns the third one.

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
| 002 | We ran 20 blind tasks against Claude-in-Chrome. 110 turns vs 176. | `tools/bench_turns/eval4/` — prereg, tasks, referee key, analyse.py | **DRAFTED**, needs sending |
| 003 | Four defects in one session, and none of them were in the product | eval 4 Amendments 5, 6, 7 and 7-addendum | **DRAFTED**, needs sending |
| 004 | Your agent is reading a page that is still being built, and nothing tells it | CLAUDE.md #70 and #76, `docs/READINESS.md`, R11–R29 | **DRAFTED**, needs sending |
| 005 | A table with a hidden column handed back the wrong number, silently | this session's TB15, `tools/audit_table_hidden_cells.py` | material complete |
| 006 | Every way record-and-replay can break, by stage | `docs/FLOWS-FAILURE-SURFACE.md` | material complete |
| 007 | "Nothing went missing" is not "what is left is enough" | `docs/SUFFICIENCY.md`, DS 0.933 | material complete |
| 008 | A feature can be dead in production behind a green suite, and only a live run will say so | CLAUDE.md #30 (two such), #76 (the scoped banner), `delta` dead for its whole life | material complete |
| 009 | We audited our headline number and it went down | CLAUDE.md #73 and #78, `tools/_m2w_ruler.py` | **DRAFTED**, needs sending |
| 010 | I pointed five agents at my own work. Four corrected a claim, not a bug. | CLAUDE.md #77, #78, #79 | **DRAFTED**, needs sending |
| 011 | We called our benchmark number "a structural lower bound" for three months. Here is what that was worth. | CLAUDE.md #79, `tools/measure_static_floor.py` — 59.7% | material complete |
| 012 | The same task, re-rendered through a different date picker, 65 times | CLAUDE.md #79, `tools/measure_wpb_variants.py` | material complete |

## What each post must NOT do

- **Quote a bare "96%".** It is **~95%** since #78 — 177/186 = 95.2%, one
  denominator — and the element-itself figure is 86.6%. The old 96.0% was over
  173 actions, excluding 13 the benchmark wrongly called absent. Quote ~95%,
  never a point estimate, and never the superseded 96.0%.
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
