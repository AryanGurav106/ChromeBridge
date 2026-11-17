# Post 016 — I lost my own benchmark to a comment I'd written that morning

Status: DRAFT, not posted. Every figure is from `tools/bench_turns/eval9/`
(pre-registration, nine amendments, `analyse.py`, `CLOSEOUT.md`) or CLAUDE.md
#81.

Register: plain. No em-dashes, no bold headers in the body, contractions, short
sentences mixed with long.

**Claims this post is NOT allowed to make.** It must not present the tie as a
win, and it must not use the 58-v-68 totals as the headline, because the sign
test is what was pre-registered and it says nothing. It must not quote a bare
accuracy number (queue rules). It must not imply the eval says anything about
per-origin consent, which was armed for the run under a dated amendment. It
must not claim the fix is verified live, because at the time of writing it is
fixtured and ablated and the extension has not been reloaded.

**Ordering note.** This is the second tie post after 014. Send it well apart
from 014, and after 009, or the series reads as a run of self-flagellation
rather than a method.

---

## A. The short one

I ran eight browser tasks, two agents each, mine against Claude-in-Chrome. I'd
written the pass bar down before the tasks existed. We needed 6 of 7 pairs.

We got 4. p equals 1.0, which is the least informative number the test can
produce.

Then I counted why, and five of my seven runs had lost calls to the same thing:
my own tool telling the agent a click had done nothing, on clicks that had just
navigated to the right page. I'd shipped that guard about four hours before the
benchmark ran.

The guard itself wasn't the interesting part. The comment above it was.

## B. The long one

### What the guard does

When the agent clicks something, I want to know whether anything happened. Not
whether Chrome accepted the command. Whether the page reacted.

So the click path does three things. It arms a listener on the page, dispatches
the click, then reads the listener back to find out if the page saw the event at
all. If it saw it, we take a snapshot of the page before and after and compare
them. Same element count, same text, same state on the target, and the page
genuinely did nothing. Then we say so.

That last bit matters because a click that silently does nothing is the worst
failure a browser agent has. The agent thinks it's on the next page. Everything
it reads after that is about the wrong document. I'd built the guard exactly to
stop that.

### What the comment said

There's a condition on the guard. It only reports when the readback comes back
true, meaning the listener survived and saw the event. And I'd written a comment
explaining why:

> Requiring `true` means: same document, the page received the event, and
> nothing changed.

Read that and you stop checking. I did. Everyone who reviewed it did.

It's wrong. The listener lives on the old page's `window`. The readback is one
round trip after the click, a few milliseconds. A click on a link hasn't
finished navigating by then. So the listener is still alive, it answers true,
and both snapshots get taken against the page we're in the middle of leaving.

Identical. Every time. For every link on the web.

### How it showed up

Not as a crash. Not as a wrong answer. The agents all got the right answer, all
sixteen runs, both tools. It showed up as agents doing extra work.

An agent clicks a link. The tool says the click had no effect. The agent, quite
reasonably, goes and checks where it is. That's a round trip, which is about
three and a half seconds of model time, which is almost the entire cost of a
tool call. Do that twice on a task and you've lost the task.

On three of the seven pairs, that was the whole margin.

### The bit I nearly got wrong

My first version of the analysis script counted the problem by searching my own
notes for phrases. It reported the competitor had this kind of bug once and we
had it five times.

Except their second instance is sitting right there in the notes. I'd written
"did not navigate" in one row and my search was looking for "never navigat".

A search over prose you wrote yourself isn't a detector. It's a thing that
agrees with you. I've caught this exact shape in other people's code twice this
month and wrote it into my own scorer anyway. The counts come from an explicit
column now.

And while I'm at it, one of their failures is worse than mine and I should say
so plainly. Mine over-warns: it says nothing happened when something did, and
the agent spends a round trip finding out it was fine. Theirs reported success
on clicks that never navigated. That one costs the agent its belief about which
page it's standing on, which is the failure I built my guard for in the first
place.

There's also one run where my agent's own write-up couldn't tell the two apart.
It said clicks "reported success or NO EFFECT without navigating". If the first
half is real, I produced a false success too. I logged it with a question mark
rather than reading the ambiguity my way, because deciding that in my own favour
is the one thing a person scoring their own benchmark doesn't get to do.

### The fix

Stop inferring, start asking.

Chrome announces every main-frame navigation the instant it starts, before the
old page has gone anywhere. That announcement lands in the extension's worker.
So "did this tab start navigating since the click" is a counter comparison
against a fact, not a guess from a probe that outlives the thing it's measuring.

Four checks. One fails against the old code and reproduces the symptom exactly.
Three are controls: a genuinely dead click still gets reported, a different tab
navigating doesn't buy an excuse, a subframe doesn't either.

My first version of that first check passed. It shouldn't have. A helper wasn't
in scope, the stub threw, the error got swallowed, and the check went green over
a guard that had never run. The two controls failing is the only reason I
looked.

That's what controls are for. A check that only ever passes is telling you about
your confidence, not your code.

### Why I'm posting a loss

Because the alternative was available and I could see it. The totals were 58
calls to 68. That's a 14.7% gap in my favour, it's just outside the published
noise floor for this kind of comparison, and I could have led with it.

But I'd pre-registered a sign test, specifically because it ignores one
blow-out pair, and switching to totals after seeing the data is picking the
statistic. If I do that once, every number I've published becomes a number
someone has to re-derive.

So: a tie, a fixed bug, and a new rule written down.

The rule is that a comment claiming a guarantee is a claim, and it needs the
same evidence as a claim in an error message. I already had a tripwire that
scans the strings my tools print to agents for exactly this, for sentences that
assert a cause they can't know. It can't see comments. Comments aren't printed.

The only defence is the boring one. Write the test that fails against what's
there now. If it passes, find out why before you believe it.

---

## C. The one-liner, if a thread needs a hook

Shipped a guard at 9am that tells my agent when a click did nothing. Benchmarked
at 1pm, lost, spent an hour working out why. The guard was firing on clicks that
had worked. The reason nobody caught it is the comment above it said it couldn't.

---

## Checkable claims in this post

| Claim | Where |
|---|---|
| 4 of 7 decided pairs, p = 1.0000, bar was p<0.05 | `eval9/analyse.py`, `CLOSEOUT.md` |
| best achievable p at n=7 is 0.0156 | printed by `analyse.py` beside the result |
| 5 of 7 of our runs hit the guard | `eval9/runs.tsv` `defect` column, tallied by `analyse.py` |
| totals 58 v 68, gap 14.7% | `analyse.py` |
| correctness 0 wrong of 16 | `analyse.py`, graded against the referee's key |
| the competitor's opposite failure, twice | `runs.tsv` T9/cic and T11/cic notes |
| the model turn is ~3.6s, 92-97% of a tool call | CLAUDE.md #38, measured by differencing |
| ID9 fails against the pre-fix guard | ablate the `navSeq` clause, run `node tools/test_ops.js` |
| the comment rule is principle 18 | `docs/PRINCIPLES.md` |
