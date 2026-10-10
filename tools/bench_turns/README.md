# bench_turns — the LIVE head-to-head harness

Every other benchmark in `tools/` is offline and deterministic: `bench_mind2web`
scores labelled click targets, `bench_trajectory` walks recorded trajectories,
`measure_retention` replays a frozen corpus. **This one drives a real Chrome and
a real agent loop**, which is why it cannot be a single script — a run is a
subagent, and the harness is a protocol plus a scorer.

It is in the repo because it was not, and that was a defect. CLAUDE.md #39-#48
report six live head-to-heads, and until this directory existed every one of
them lived in a session scratchpad under `/tmp` and died with the session. A
result nobody can re-derive is an anecdote with a p-value. #45 is the concrete
cost of that: its headline finding had to be withdrawn when the prompt that
produced it turned out to mandate the behaviour being measured, and the only
reason that was catchable is that the prompt file happened to still exist.

```
eval3/    the generality eval — 19 tasks, 7 archetypes (CLAUDE.md #48)
eval12/   the two 9-task turn evals that preceded it (CLAUDE.md #47)
```

## What a run is

One task, one arm, one FRESH subagent with no memory of any other run. The
subagent gets `prompts/<TASK>_<arm>.txt` verbatim and nothing else. The two arms
differ ONLY in the tool namespace; `gen.py` asserts that and refuses to write
prompts that differ in any other byte.

## Re-running eval 3

```bash
python tools/bench_turns/eval3/gen.py        # writes prompts/ + run_order.json
                                             # + ground_truth.json, asserts arms identical
```

Then, for each `[task, arm]` in `run_order.json`, **strictly serially**:

1. spawn a fresh agent with that prompt file as its entire instruction
2. wait for it to finish before starting the next

Serial is not a convenience. #39 records six parallel agents corrupting each
other's tab groups, and the fix has to be out of band — the earlier harness
solved it by ORDERING AGENTS TO DO TAB CEREMONY IN THE PROMPT, which is exactly
the confound #45 had to withdraw a finding over. A harness problem gets a
harness answer.

Then:

```bash
python tools/bench_turns/eval3/score.py <agentId> ...   # one JSON line per run
python tools/bench_turns/eval3/analyse.py               # H1/H2/H3 + archetypes
```

`runs.tsv` maps each ordinal to the agent id of the run that produced the
numbers in #48. Those ids resolve only inside the session that produced them,
so the file is a RECORD, not a re-entry point: a fresh run writes its own.

## Rules that are load-bearing, not stylistic

- **Score from the TRANSCRIPT, never from the agent's self-report.** `score.py`
  reads the JSONL. Agents mis-count themselves: eval 3 had self-reports of 29
  against a true 31, and 16 against 17, in both directions.
- **A TURN is one assistant message containing tool_use, not one tool call.**
  That is the unit #38 priced at ~3.6s and 92-97% of a tool call's wall clock.
  A 7-step `browser_batch` is ONE turn. Raw call count is recorded beside it
  because the pre-#47 evals reported calls and the two must not be conflated.
- **Fix the bar before the data exists**, in `PREREG.md`, and recompute the
  exact sign test at whatever n survives dropped tasks. #40 records calling a
  genuine 8/8 "drift" and having to reverse it; the bar exists so that cannot
  happen in either direction.
- **The other arm's code must be UNCHANGED**, so it measures drift directly.
  #35 measured the control arm improving 47s/task on untouched code.
- **Tasks are written BLIND** by an agent told only to write varied two-hop
  tasks, with a deny-list of domains used before and no knowledge that anything
  is under test. #39 records the author writing tasks on home ground.
- **Ground truth is re-derived INDEPENDENTLY of the task author.** The eval-3
  referee broke one task outright (an EDGAR "search form" that is an error page
  with zero `<form>` elements) and found a second with two defensible answers.
  Both were dropped or reworded BEFORE any run — after is forbidden.
- **The sign test is on DIRECTION, deliberately.** Eval 3's losing arm produced
  four runs of 18-31 turns from one broken input path; those cannot inflate H1,
  only the turn totals. Report both and say which is which.

## Known limits, carried from PREREG

Both arms are the SAME MODEL, so correctness saturates (38/38 in eval 3) and
cannot discriminate — it is a FALSIFIER, not a win condition. The per-origin
consent gate is OFF during runs (see eval 1 AMENDMENT 2 for why and what that
gives up), so **these numbers say nothing about the cost of the consent model**.
Per-archetype n is ~3, reported descriptively with no p-values; `analyse.py`
prints the best p REACHABLE at each n beside each test so an underpowered
stratum cannot be misread as a null.
