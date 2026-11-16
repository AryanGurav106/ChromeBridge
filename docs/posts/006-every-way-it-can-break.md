# Post 006 — I wrote down every way my own feature can break

Status: DRAFT, not posted. Everything here is from `docs/FLOWS-FAILURE-SURFACE.md`
and the CLAUDE.md entries it cites. No number in this post is new.

Register: plain. No em-dashes, no bold headers in the body, contractions, short
sentences mixed with long.

**Claims this post is NOT allowed to make.** It must not imply the feature is
reliable because the list exists. The list is the opposite claim. It must not
quote the flow-descriptor zero-wrong figure without its qualifier (see the
queue's rules). It must not present `INHERENT` entries as things I plan to fix.

---

## A. The short one

My browser agent can record what it did and replay it later as a test. You drive
it through a task once, it writes a small JSON file, and from then on that file
runs in under a second with no model call at all.

Someone asked me to make it so it "conceptually would never break".

Nothing reaches that. So I did the honest version: I sat down and enumerated
every way it can break, by the stage it breaks at. Seven stages, about forty
entries, each with its evidence and one of four statuses.

CLOSED means fixed, with a test that fails against the old code. BOUNDED means
it cannot be fixed but the failure announces itself. OPEN means open. INHERENT
means it is a property of the problem, not of my implementation, and no amount
of engineering inside this feature reaches it.

A gap with no entry on that list is a gap nobody has thought about. That is the
only kind that's genuinely dangerous.

## B. The one I can't fix, and why saying so matters

Here is entry 1.7.

The assertions in a recorded flow come free, because I record an *agent* rather
than a human. A human demonstration tells you what was done and nothing about
what should then be true, which is why every other recorder makes you write the
checks by hand. An agent narrates its own expectations as it works: the search
it ran after clicking Submit *is* the postcondition.

That's the good part. Here's the bad part.

If the agent misread the page, the flow enshrines the misreading. The check is
false, stable, and green forever. Nobody notices, because a passing test is not
a thing anyone looks at.

That is the oracle problem, and it is not solvable inside the recorder. The
recorder has no access to the truth the agent was looking at. I could add a
second model to grade the first, and then I'd have two models that can be wrong
together and a false sense that they can't.

What I did instead was narrow the surface where it hides. The recorder already
catches two weaker siblings: an assertion that was *already true before the
step* (so the step could do nothing and still pass), and an assertion that
nothing was ever observed to contradict. The second one isn't wrong — it just
carries no evidence — so it gets named rather than dropped, and those lines are
marked in the file.

Which means the real answer to "who re-grades the assertions" is: a person,
reading a small JSON diff. That's weaker than a test oracle and I say so. What
changed is that the review is now *targeted* — the lines that could be quietly
wrong are the ones flagged, instead of all of them looking the same.

## C. Three of these were found by a test that passed

The entries marked CLOSED are closed because something *ran*, not because
something was read. A live task, an ablation against the old code, or a
measurement with its noise floor taken first.

Three of them were found by taking a test I'd just written, running it against
the broken version of the code, and watching it pass anyway.

That is the single cheapest habit in this project and it keeps paying. A test
encodes what you *thought* the cause was. The only way to tell that apart from
the actual cause is to watch it fail.

## D. What's genuinely not covered

Six things, and they're in the document under that heading, not buried:

the oracle problem above; a page that reports itself settled and isn't; a
category of element locator that has nothing to distinguish it from its
neighbours, which is 59.4% of the ones that need distinguishing; no headless
runner for arbitrary recorded flows; nothing isolating one replay from the next
within a batch; and the app being rendered in a different language, which
invalidates every locator at once and is the one environment change that
produces no explanatory message.

## E. The point

A feature list tells you what something does when it works. It is the easy
document and everybody writes it.

The list of how it breaks is the one that tells you whether to trust it, and
writing it is the only way to find out that six of the entries have no fix.
I'd rather publish that than a number.

---

## Notes for whoever sends this

- Link `docs/FLOWS-FAILURE-SURFACE.md` directly. The post is an invitation to
  read the list, not a replacement for it.
- If asked "so is it reliable?": the honest answer is that it replays in under a
  second with no model call, that every CLOSED entry has a test that fails
  against the old code, and that the six uncovered items are the reason I would
  not call it reliable without qualification.
- Do not pair this post with a benchmark table. It is the method post and the
  numbers belong elsewhere in the queue.
