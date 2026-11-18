# Running sub-agents on this repo

Most of this project's recent findings came from agents, and roughly half of
what they handed back needed correcting before it could ship. Both halves are
the point: delegation is how the heavy lifting gets done here, and an agent's
report is **evidence to check, never a result to relay**.

Everything below is a rule that cost something to learn, with what it cost.

---

## 1. Verify the headline yourself. Every time.

Three agent reports in one session had a wrong or overstated headline, and all
three looked completely reasonable:

| what the report said | what checking found |
|---|---|
| "the option picker fails on this widget" (**my brief**, handed to an agent) | `_pickOptionPage` does not click; the opening click is `fillDropdown` step 1. My probe drove it against a `display:none` popover. **The defect did not exist.** |
| "any recorded flow containing a login is un-replayable from an agent session" | `mcp_server.py` calls `load_dotenv`, so a `CB_SECRET_…` line in `.env` already works. The MECHANISM was fine; only the refusal message was wrong. |
| "0% WRONG on every mutation" (an earlier session) | True of the harness. Its mutation set had **no reorder arm**; adding one measured 94.4% WRONG. |

The checking is usually cheap — reading one function, running the agent's own
probe against shipped code, hashing a before/after. It changed what shipped all
three times. **A report that flatters or damns the system gets re-derived before
it is believed** (PRINCIPLES, and `docs/MEASUREMENT.md`), and that rule does not
relax because the claim came from an agent rather than from you.

Note the first row: the bad brief was MINE. Verifying protects the agent from
your mistakes as much as it protects you from theirs.

## 2. Browser work is SERIAL. Always.

Six parallel agents corrupted each other's tab groups once (CLAUDE.md #39) and
the eval had to be thrown away. One agent touches the browser at a time.

This shapes how you decompose: give the browser to one agent and give the other
work that needs no browser (reading, measuring a frozen corpus, writing a
harness). When two arms of a comparison must each drive, run them one after the
other and say so in the pre-registration.

**A probe with its own throwaway browser is NOT the shared one.**
`audit_frames_live.Rig` and `run_flows.py` launch their own Chrome with the
repo's unpacked extension on a non-default port. Those can run while the user's
Chrome is busy — and they are also how you live-verify a change when the user's
own extension is stale, which it usually is.

## 3. Never let an agent edit product code

Brief it to return a **diff**. Then read the diff before applying it — all of it.

This is not distrust, it is the only point at which the "is this a declaration
or a guess?" question gets asked by someone with the whole codebase in view. One
patch this session was sound; checking it still meant verifying that its
`data-state === 'closed'` clause mirrored a rule already shipped in
`_countVisibleOptionsPage` rather than introducing a framework convention.

Agents MAY add fixtures, and should be told that any new check must FAIL against
current code with a control that passes in both arms.

## 4. `git add -A` while an agent is writing sweeps its work into your commit

Happened this session: a commit whose message describes a picker fix also
carries a research paper and two probes. Nothing was lost and no agent product
code went in, but the message is not the whole truth about the commit, and it
was already pushed.

Either stage explicit paths, or check `git status` immediately before
committing and describe what is actually there.

## 5. The brief is the experiment

- **Say what is already ruled out.** The brief that disproved a defect worked
  because it carried the exact reproduction, the constraints a fix had to
  satisfy, and what had already been rejected with numbers.
- **Never reveal the comparison.** CLAUDE.md #45's headline had to be WITHDRAWN
  when its prompt turned out to mandate the behaviour it measured. If one arm
  has a feature, the prompt must name no feature of either arm and must not say
  a comparison is happening. The capability has to show itself.
- **Ask for what you will score, in the units you will score it in.** "Report
  the exact number of tool calls each pass took" produces a number; "report how
  it went" produces prose.
- **Ask what the sample could not model.** The most valuable paragraph in
  several reports was the one listing what the corpus does not contain.

## 6. Score from artefacts, not from the report

Saved `*.flow.json`, `runs.tsv`, the transcript. An earlier eval found two
scorer defects by noticing a self-report disagreeing with the transcript, and
this session an agent's own count was right while its conclusion was not.

## 7. A refused spawn is information

One spawn this session was denied because it involved standing up arbitrary
third-party software. That is a reasonable thing to refuse. The answer is to
**narrow the task** so it needs no new software — not to find another route to
the same action.

## 8. Agents inherit your blind spots

Two agents independently reported the same readiness banner as noise, which is
the signal seven have now reported. If several agents converge on something you
have been explaining away, that is data about the product, not about the agents.

---

## Where the rest of the literature lives

`docs/README.md` routes by task — it is the index, and `C47` fails the suite if
a paper under `docs/research/` is not reachable from it. `PRINCIPLES.md` holds
the non-negotiable rules, `MEASUREMENT.md` the ways an instrument here has lied,
`CLAUDE.md` the numbered log, and `docs/OPEN.md` what is deliberately unbuilt
and why. A brief that names the two or three of these a task touches saves the
agent from re-deriving a decision that already has a number against it.
