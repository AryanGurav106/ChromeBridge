# Post 003 — four defects in one session, and none of them were in the product

Status: DRAFT, not posted. Every number below was re-derived from
`tools/bench_turns/eval4/PREREG.md` (Amendments 5, 6, 7 and 7-addendum) before
this was written, not quoted from memory.

Register: plain. No em-dashes, no bold headers inside the post body,
contractions, short sentences mixed with long.

**Claims this post is NOT allowed to make.** It must not present the eval's
headline as the point. The point is the ruler. If it quotes the result at all
it quotes it the way `docs/EVALS.md` §5 requires, with the leave-one-host-out
range, and it must say the gate was armed for the run.

---

## A. The short one

I ran a 20-task benchmark comparing my browser agent against another one. Four
things broke during it. All four were in the measuring apparatus. Zero were in
the thing being measured.

That ratio is the only part of this worth your time.

**One. The scorer was reading the wrong column.**

Each run writes a row to a TSV. Column 4 is supposed to hold an agent id, which
the scorer uses to go and read that agent's actual transcript. What was landing
there was the agent's own seven-line summary of what it did.

So every row would have scored "no transcript". It didn't fail loudly, it just
would have produced nothing.

When I re-scored properly from the transcripts, two of the first five pairs
changed. One went from a tie to a win. One went from a margin of 1 to a margin
of 2. Both moved for the same reason: an agent had under-counted its own calls,
because it forgot to count a setup step its own server instructions require.

Which is the whole argument for not trusting self-reports. The agent wasn't
lying. It just didn't know.

**Two. The answer key couldn't be matched by any answer.**

The correctness check fired on 5 of the first 12 runs, including both arms on
two tasks. I checked all 12 transcripts by hand. Every single answer was right.

There's a rule I'd written down after a previous eval: a failure that damns both
arms identically is the signature of a broken ruler, not a broken system. That's
the only reason I looked instead of celebrating.

The key was built by splitting the reference answer on " and ", ";" and " / ",
then stripping backticks off the ends. Two things compounded. Internal
backticks survived, so one needle was the literal string

    Regice`, Sp. Def `200

which no agent could ever emit. And a comma-joined answer was never split at
all, so the whole phrase had to appear verbatim. "Third row is Regice, with a
Sp. Def of 200" cannot match that. It's a correct answer and the ruler said no.

**Three. The rejects were firing on correct answers.**

I had a step that auto-harvested "wrong" values to reject. It got 3 of 30 runs
wrong, including both arms on the same task again.

| what got rejected | what it actually was |
|---|---|
| `ForgeFlex Tools` | the brand the task tells you to filter by |
| `总笔画 12` | the literal correct answer |
| `部外 0` | an unrelated field in the same table |

The second row is the one I think about. The thing that disqualified the
answer was the answer.

Inspecting the rest, one task was carrying rejects that belonged to five other
tasks.

I deleted the whole harvest rather than fixing it. Three failure modes in one
mechanism is a mechanism that's wrong, not a mechanism with bugs.

**Four. The curated rejects were wrong the same way**, on an answer whose crime
was quoting the row it had read.

## B. What I actually changed, since "be careful" isn't a fix

Three things, and only the last one is interesting.

The TSV is now rebuilt mechanically from the run metadata, so the wrong value
can't get into that column. And the analysis refuses to start if column 4 isn't
an agent id, naming the problem, instead of dying three stack frames down in
something unrelated.

The key is now built from the backticked spans on the reference answer line.
Not comma-splitting, because one answer is `2, 8, 18, 8` — a single value
containing commas. Spans are atomic. I checked all 22 answer lines: the referee
backticks exactly the load-bearing values and nothing else.

The interesting one is the part that makes any of this admissible.

Changing an instrument after you've seen data is the move that invalidates a
pre-registration. You can always find a reason the ruler was unfair to you. So
the defence has to be checkable by someone else, not asserted by me:

- the fix was applied to BOTH arms and re-run over all of them, not just the
  ones that looked wrong
- it was written down as a dated amendment in the pre-registration, with the
  before and after, where it sits next to the hypothesis it could have
  corrupted
- the superseded table is marked superseded rather than quietly replaced
- the original self-reports are still in the repo, in their own file

That last one matters more than it sounds. The reason you can check me is that
I kept the thing that was wrong.

## C. The part I got wrong twice, in public

Having fixed the scoring, I then quoted two numbers in conversation that came
from the self-reports I'd just finished declaring unreliable. One task's call
count was 8, not 7. Another figure was 17, not 11.

Same source, same defect, after I'd personally written the amendment
explaining why that source was wrong.

I corrected both in the pre-registration where they'd done the damage. But the
honest lesson isn't "be more careful". It's that a fixed pipeline doesn't
retroactively fix the numbers already in your head, and the only defence is to
re-derive a number at the moment you use it rather than at the moment you
learned it.

## D. The one-liner

Across one benchmark session the measuring apparatus was wrong four times and
the product was wrong twice. Every one of the four was caught because something
ran, not because something was read.

---

## Notes for whoever sends this

- The result itself is deliberately not in this post. If someone asks, quote it
  per `docs/EVALS.md` §5, with the leave-one-host-out range, and say the
  consent gate was armed for the run and restored after — the eval says nothing
  about the cost of per-origin consent and must not be presented as if it does.
- Amendment 1 is worth mentioning if anyone pushes on sample quality: the top
  three hosts are 41% of the 22 tasks, and that was written down before any run,
  not discovered afterwards.
- Do not imply the other agent is bad. Three of these four defects would have
  mis-scored BOTH arms, which is exactly why they were found.
