# Showcase drafts

Content written for posting, kept in the repo so the claims and the evidence
stay in one place. `docs/EVALS.md` §5 holds the rules for quoting a number.

Register note: these are written plainly on purpose — short sentences, no
heavy formatting, contractions. They are meant to read like a person wrote
them, because a person did.


Every number here was re-derived by an independent audit that was not told what
I believed. What it confirmed: the descriptor result reproduces within corpus
noise, the Mind2Web numbers reproduce essentially perfectly, ~65 new checks fail
against pre-fix code, and no new check passes in both arms without being a
declared control.

What it did NOT confirm, and is therefore not claimed below: the readiness work
has not run in a real browser yet.

Written in the plain register, not the polished one. No em-dashes, no bold
headers inside the post, contractions, short sentences mixed with long.

---

## A. The short one (Reddit / HN comment, or a LinkedIn post body)

Spent today on the part of my browser agent I'd been avoiding.

The idea is you drive the browser once with Claude, and it saves what you did
as a replayable test. The useful bit isn't the replay, it's that the checks
Claude made along the way become the assertions. You don't write them.

The thing I actually wanted to show is what happens when the app changes
underneath it.

So: a nav link whose label is "Projects 4", because the accessible name
includes a count badge. Add a project and it's "Projects 5". The recorded
descriptor no longer matches.

    PASS  acme-nav-badge  4/4 step(s) in 6.59s
          step 3 computer: name 'Projects 4' is gone; matched href='/projects'

It passed, and it told me why. The label moved, the link's href didn't, so it
resolved on the href and reported the drift instead of either failing for no
reason or quietly healing and saying nothing.

That second one is the trap. There's a measurement I keep coming back to: when
you ask several independent models to repair a broken locator, and the element
has actually been DELETED, they agree with each other and they're wrong. 34 out
of 34 unanimous verdicts were false heals, and growing the pool from 3 models to
7 didn't help. Agreement is a decent signal for "which of these surviving
elements is the one I meant" and it's worse than useless for "is it still
there". So the href is only ever a second declared key for an element that still
exists. It is never allowed to answer "it's gone".

Other three cases, same command, one flag each:

    the app is in the wrong state  -> stops BEFORE acting, exit 1
    a row was added, count is wrong -> fails naming the step and both numbers
    nothing broken                  -> 3/3 pass, 0.26s to 4.5s, zero model calls

Repo's open source if you want to find holes in it. I'd genuinely like someone
to.

---

## B. The honest-engineering one (longer, for a blog or a LinkedIn article)

Today I measured something I'd been asserting for months, and it was wrong.

The feature records a browser session as a replayable test. Element targets are
stored as declarations rather than DOM paths, so a re-render doesn't break them.
I had a number for that: 2,726 descriptors across 26 sites, 100% correct, 0%
wrong under every mutation. Six mutations: rename the target, rename a
neighbour, delete it, insert a twin, put a twin elsewhere, move a counter into
its name.

Someone pointed out the mutation set has no reorder.

A re-sorted list is the one change that beats the design. The crowd of
candidate elements is identical. Same elements, same declarations, same count.
Only the order differs, and the ordinal is the only thing left distinguishing
them. So it binds to a different row.

Measured once the arm existed: 23% of stored descriptors carry an ordinal, and
under a permutation 94% of those bind to the wrong element. The number that
actually matters isn't the 94%, it's that refusals were 0%. There was no signal
of any kind. A flow that clicks Delete on the first invoice row, replayed after
the default sort flips to newest-first, deletes a different invoice and reports
PASSED, because "one fewer row" is still true.

"100% correct on every mutation" was a statement about my test harness that I
had been reading as a statement about the world.

The fix is a witness: the identity fields the descriptor deliberately ignores,
plus the nearest preceding elements that aren't part of the ambiguous group.
Recorded only where it's unique at record time. On a realistic re-sort, a
witnessed descriptor is now 0% wrong at 94% correct, costing 0.2 percentage
points of extra refusals on the six original mutations.

Two things I want to flag because they were the interesting decisions.

Geometry was the best witness by a distance. Element position uniquely
identified 87% of members, against 61% for everything else combined. It's not
used. Position is excluded from identity in the first place because it drifts,
and a safeguard built on a drifting signal fires on every reflow and every lazy
image. A safety check that goes off constantly is noise wearing a safety label,
and people turn those off.

And 59% of ambiguous descriptors still can't be witnessed at all. Groups that
are identical in every declared field and in their surroundings. I could get to
0% wrong everywhere by refusing those too, and that would pause about 14% of all
recorded steps on a page where nothing had changed. That isn't a safety cost,
it's just losing the feature. So the recorder warns at record time instead, and
I'm saying the number out loud rather than quoting the clean one.

---

## C. One-liner options

- "Recorded a browser flow, changed the app underneath it, and the test told me
  which label moved instead of failing or silently healing."
- "My locator safety number was 100% correct on every mutation. The mutation set
  didn't have a reorder. It was 94% wrong on reorder, with zero refusals."
- "Geometry was the best signal available and I didn't use it, because a
  safeguard that fires on every reflow is noise with a safety label."

---

## What NOT to claim

- Do not say it cannot break. It can, and `docs/OPEN.md` Tier 1 lists how.
  The defensible claim is that every way it breaks is named, measured and
  pinned by a check.
- Do not quote the Mind2Web recall as "96.0%". It is ~96%, from 22
  trajectories, and leave-one-site-out spans 95.1-98.1%.
- Do not compare turn counts against Claude-in-Chrome from eval 3 without
  saying the one archetype where both tools worked cleanly is the one where we
  are level.
- Do not claim the readiness work is shipped until it has run in a real
  browser. As of this draft it has not — it is measured under Playwright
  against the real extracted functions, which is not the same thing, and this
  project has had that exact probe dead in production for a release behind a
  green suite.
- Do not quote the eval-3 turn counts as a general speed claim. Its widest band
  came from the other tool failing to render a page at all, and the one
  archetype where both worked cleanly is the one where we are level.
