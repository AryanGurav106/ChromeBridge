# Post 001 — record and replay

Status: DRAFT, not posted. Every number below is from an artefact in this repo.
Sources: `flows/todomvc-add-items.flow.json`, `tools/bench_turns/eval4/`,
CLAUDE.md #49, #55, #57, #60, #72.

---

## LinkedIn / Reddit version

Most browser automation tools let you record a demonstration and replay it.
You click through the thing once, it saves what you did, and you get a script.

The problem with that has always been the same. A demonstration tells you what
somebody did. It tells you nothing about what should then be true. So every one
of those tools makes you go back and write the assertions by hand, and most
people don't, and you end up with a test that passes as long as the clicks land
somewhere.

ChromeBridge records Claude instead of recording you.

That sounds like a small difference and it isn't, because an agent narrates its
own postconditions for free. When Claude clicks a button and then checks how
many rows the table has, that check IS the expected state. It was going to make
that observation anyway to decide what to do next. We keep it.

So you drive the thing once, in English, and what comes out the other end is a
test with real assertions in it that nobody had to write.

Here is one I recorded against a TodoMVC app. Five steps. Two items typed in.
The assertions are `.todo-list li` is 1 after the first, then 2 after the
second, plus a text search for the item itself. Nothing in there was authored.
It replays in 0.31 seconds with zero model calls.

The two strings I typed were lifted into named variables automatically, so
running it with different text changes what gets typed AND what the assertion
looks for. That second half took a fix: the first version typed the new value
and then asserted on the old one, which is a test that reports red on a correct
run, which is worse than no test.

What I care about more than the speed is what it does when it is not sure.

A recorded step does not store a DOM path, because a path breaks the first time
React re-renders. It stores a description of what the thing IS, built from what
the page declares about it, and resolves that fresh every run. When that
description matches exactly one element, it acts. When it matches several, it
stops and hands the candidates back rather than picking one.

I measured that on 26 real sites, 2,726 recorded steps, under six kinds of page
change. Zero wrong bindings. Then I found the measurement had a hole in it: I
had never tested a re-sorted list. A re-sort leaves every element identical and
only moves the order, so every check passed and the step bound to a different
row. 94% wrong, no warning. The fix stores a witness alongside the position, and
on a realistic re-sort it is back to zero wrong, with the honest residue written
down: 59% of ambiguous steps have nothing available to witness them, and those
are no better than before.

That is the part I would want to know about if I were picking a tool, so it is
in the README rather than in a footnote.

Repo: github.com/AryanGurav106/ChromeBridge

---

## Short version (for a comment or a reply)

Browser automation that records a demonstration can't know what should be true
afterwards, so you write the assertions yourself. We record Claude instead, and
an agent already states its postconditions out loud while it works, so the
assertions come free. A 5-step flow against TodoMVC replays in 0.31s with zero
model calls, and the assertions in it (`.todo-list li` == 1, then == 2, plus a
text search) were never authored by anyone.

---

## NOT in the post, and why

- Eval 4's 110-vs-176 turn result. It is the strongest evidence here but the
  brief is "not just numbers", and leading a record-and-replay post with a
  head-to-head buries the feature.
- The sufficiency number (0.933). Same reason, and it needs more context than a
  post can carry.
- Anything about the consent model. It is the best-argued part of the project
  and it is a separate post.

## CHECK BEFORE POSTING

- [ ] Re-run the flow and confirm the 0.31s still holds, and say "about a third
      of a second" rather than a decimal if it drifts.
- [ ] The 2,726 / 26-site / zero-wrong figures are CLAUDE.md #49 and #72.
      Re-read #72 before posting: the zero is for WITNESSED descriptors on a
      realistic re-sort, not for all of them, and the post must not round that
      off.
