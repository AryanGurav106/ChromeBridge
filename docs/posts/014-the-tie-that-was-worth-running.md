# Post 014 — We ran 16 head-to-head tasks and tied. Here's why it was worth it.

Status: DRAFT, not posted. Every figure is from `tools/bench_turns/eval7/`
(pre-registration, five amendments, `score.py`, `CLOSEOUT.md`) or `docs/OPEN.md`.

Register: plain. No em-dashes, no bold headers in the body, contractions, short
sentences mixed with long.

**Claims this post is NOT allowed to make.** It must not present the tie as a
win or bury it. It must not quote a bare accuracy number (queue rules). It must
not imply the eval says anything about per-origin consent — one grant covered
all eight apps and the pre-registration says so.

---

## A. The short one

I spent a day running my browser-agent against Claude-in-Chrome. Eight tasks,
sixteen runs, scored not by me and not by a judge model but by the app's own
business events — the thing it fires internally after the state actually
changes.

Final: 38 conditions to 36. Seven tasks fully completed each. One task of eight
went a different way for the two of them.

That's a tie. On the test I'd written down in advance, p = 1.0.

I'd predicted exactly that, in writing, before any data existed — "no
significant difference, and the two within 15% of each other." It came out at
5.6%. I'm mentioning that not because being right is interesting, but because a
pre-registration nobody checks afterwards is decoration.

So the comparison produced nothing. Here's what the day actually produced.

## B. Twenty-two defects, all mine

Every one from a live run. Eight I fixed the same day. Fifteen I wrote down with
the evidence and fixed after, so that every run of the eval stayed on one build.

Two of them landed on work from *that same session*. I'd added a piece of advice
in the morning after an earlier eval — "when many rows share one label, what
separates them is an attribute, query for it." By the afternoon a different app
had put forty identical buttons on screen with no distinguishing attribute at
all. What separates those is which card they sit in, and none of the tools I'd
pointed at expressed containment.

A fix verified against the thing that produced it is not verified against the
next thing.

## C. The one that no measurement I own can see

A quantity stepper. Minus, a number, plus.

Both buttons came back named `"1"`. The quantity, adopted as the accessible name
of the control on either side of it. Click the wrong one when the quantity is 1
and the item is removed from the cart.

Here's the part that bothers me. I have a metric for exactly this — can every
element be reached by the name we printed for it? It scores 0.9996 across 84
sites. It scores those two buttons as a **hit**. They're present, they're
listed, they're named, they're clickable. Every property it checks is satisfied.

The failure isn't absence. It's two things that do opposite jobs, printed
identically. No corpus-based ruler I have can see that, because every one of them
asks whether an element *survived*.

That's the argument for still running live agents when the offline numbers look
finished.

## D. The bit where the benchmark corrected me

Three of my eight tasks asked for a date the app can't reach. Calendars disable
past days; the task files carried dates from before the run.

I measured that carefully, verified it myself rather than trusting the agent
that reported it, and wrote it up as the benchmark decaying.

Wrong. The repo ships results from 24 published runs by other agents, and one
from September carries a *different* date than its own task file. Their harness
rewrites it. There's a module whose entire job is rolling booking dates forward,
and my generator never called it.

The impossible task was mine. Three runs discarded.

## E. The thing I'd lead with, which isn't in the score

Both agents were told to work in a tab they create and leave existing tabs
alone. Across fifteen runs, neither touched the two unrelated tabs that were
open. Verified at the end by reading them back, not assumed.

The instruction works on both. It's only sufficient because someone wrote it.

The other tool can't batch creating a tab with navigating it, and the shortcut
its own docs advertise navigates "the first tab in the session's group" — which
isn't guaranteed to be one it made. Its agent said so itself: the advertised
fast path is unusable under the exact constraint most real tasks impose. So
obeying costs it a call or two every single task.

Ours threads the tab through automatically. Obeying is free and disobeying is
structurally difficult.

That's a capability difference with a safety consequence attached. It doesn't
show up in a turn count, and it's the one I'd put first.

---

## Notes for whoever sends this

- Do NOT trim section A's admission that the comparison produced nothing. The
  post only works because that's stated plainly and early.
- The 38–36 is conditions, not tasks. Tasks were 7–7. If one number is quoted,
  quote both.
- If asked "so is it better?": on these eight tasks, no measurable difference in
  what got done. Fewer calls (125 v 157), which is real and noisy. The tab
  property in section E is the difference I'd actually defend.
- If asked about the published 38.5% field average on these same eight tasks:
  it bounds difficulty, not performance — their scoring is all-or-nothing per
  task, ours counts conditions. Don't put them in one sentence.
