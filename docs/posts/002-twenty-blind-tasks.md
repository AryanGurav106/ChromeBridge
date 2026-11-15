# Post 002 — the head-to-head

Status: DRAFT, not posted. Every number re-derived from `analyse.py` on the
committed `runs.tsv` before this was written, not from memory.
Source: `tools/bench_turns/eval4/` (pre-registration, task list, referee key,
40 prompts, scorer, analysis).

---

## LinkedIn / Reddit version

I spent today running ChromeBridge against Claude-in-Chrome on twenty browser
tasks. The result was 110 turns against 176.

The number I care about more is a different one, so let me do the setup first,
because a benchmark you designed yourself is worth almost nothing.

The tasks were written by someone told only to write twenty varied two-hop
browser tasks. They did not know any toolset was being compared, and they were
handed a deny-list of every site used in earlier runs. An independent referee
then re-derived every answer by driving a headless browser, and rejected two
tasks before anything ran: one pointed at a page that no longer had a form on
it, and one asked about a value the site's own footnote contradicted. Two
defensible answers is worse than no task.

The bar was fixed before any data existed, including a subset I said we might
lose. Runs were strictly serial with the order of the two tools rotated per
task, and every count came from the raw transcripts rather than from the
agents' own reports, which matters more than it sounds like.

Results. 14 of 16 decided pairs, p = 0.0042. Drop any single host and it lands
between 86% and 93% of decided pairs, so quote the range and not the point.
Both tools answered all forty runs correctly, which is expected and uninteresting:
they are the same model, so correctness is a falsifier, not a headline.

The subset I said we might lose, we lost. On interaction-heavy tasks it is 7 of
9 and does not clear. Both of our two losses are in there. That was written
down before the data existed and it gets the same prominence as the rest.

Now the number I actually care about.

Four of the defects this eval found were in **our own measuring apparatus**,
against two in the product. The answer key was matching against strings with
markdown backticks stuck in the middle, so it marked five correct answers
wrong, including both tools on the same task twice. I had also been writing
each agent's self-report into the column the scorer reads transcript IDs from,
so the first table I produced was built from agents counting their own tool
calls, which is the one thing the scorer's own docstring forbids. Re-scoring
from transcripts moved two pairs.

Every one of those was caught because something ran and the output refused to
make sense, not because anyone read the code.

The two product defects are the ones worth having found. Our table renderer
silently misaligned every column after a hidden one, so asking a nutrient table
for the Max value handed back the Median with nothing indicating a problem. And
our form-submit reported failure on a search that had worked, citing a modal
that does not exist on that page, and advised a retry that would have changed
the sort order. Both are fixed, both have a test that fails against the old
code and reproduces the live symptom exactly.

If I had been willing to call this finished in the morning, both would still be
in there.

Repo and harness: github.com/AryanGurav106/ChromeBridge

---

## Short version

Twenty browser tasks written by someone who did not know two tools were being
compared, answers re-derived by an independent referee, bar fixed before any
data, runs serial with order rotated, every count taken from raw transcripts
rather than from what the agents said about themselves. 110 turns against 176,
14 of 16 decided pairs, p = 0.0042. The pre-registered subset I said we might
lose, we lost. And four of the defects it turned up were in my own measuring
apparatus against two in the product, which is the part I would want to know.

---

## CHECK BEFORE POSTING

- [ ] Re-run `analyse.py`; quote the leave-one-host-out RANGE, never 14/16 alone.
- [ ] Do NOT let this imply anything about the consent model. The gate was
      ARMED for the run and the pre-registration says the eval is silent on
      what it costs.
- [ ] H4 stays in. A pre-registered test we failed, reported as a failure, is
      the thing that makes the rest believable.
- [ ] Do not name the other tool's defects. They are in FINDINGS.md and they
      are real, but a post that lists a competitor's bugs reads as a hit piece
      and the turn count already carries the argument.
