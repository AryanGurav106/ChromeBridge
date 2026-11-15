# Post 004 — your agent is reading a page that is still being built

Status: DRAFT, not posted. Every number below is from an artefact in this repo.
Sources: CLAUDE.md #70 and #76, `docs/READINESS.md`, `tools/test_readiness.py`
R11–R29, and a live session against ptable.com on 2026-11-15.

Register: plain. No em-dashes, no bold headers inside the post body,
contractions, short sentences mixed with long.

**Claims this post is NOT allowed to make.** The scoped-readiness fix has been
live-verified in ONE direction only: the defect was reproduced on the shipped
extension in a real browser. The fixed build has not been loaded yet, so the
post must not say the fix is confirmed live. Everything below is either a
fixture measurement, or a live observation of the BROKEN behaviour, and it says
which.

---

## A. The short one (Reddit / HN / LinkedIn body)

Five different agents, across two rounds of testing, told me the same thing in
almost the same words. My browser agent couldn't tell "this page is still
loading" apart from "this page is done and just chatty".

They were right, and the reason is a bit embarrassing once you see it.

Everything I was measuring answered a different question. Requests in flight,
images not loaded, aria-busy, readyState. All of those answer "is something
arriving". What the agent actually wants to know is "if I wait, will what I'm
reading change". On an old-fashioned page those are the same question. On
anything built this decade they come apart, in both directions.

Here's the first direction. One fetch that resolves instantly, then 400 rows
painted over about two seconds in chunks, which is just what a framework does
when it commits in slices.

    at 300ms:   64 of 400 rows painted
                readyState complete, aria-busy 0, progressbar 0
                network in flight: 0

Every signal I had read zero. The agent gets handed a 64-row table that is
about to become a 400-row table, with no warning of any kind. If it concludes
the row it wanted isn't there, it's wrong, and nothing told it.

Second direction, same page, different timing. 400 rows painted synchronously
and finished before the first read, then a 120ms poll and an analytics beacon.

    at 3500ms:  400 of 400 rows, done, finished three seconds ago
                network in flight: 6

So the banner fires forever on a page that was complete before anybody looked
at it. That's worse than useless. A warning that's always on is a warning
people learn to skip, and then it's not there on the one read where it's true.

The thing that separates them was sitting right there and I wasn't recording
it: when did the DOM last actually change.

    still building:  last change 9 to 18ms ago
    done:            last change 907 to 3514ms ago

No overlap. Which matters more than the specific numbers, because it means I
don't have to pick a threshold. Anything between 50 and 500ms works. So I don't
pick one. The number goes in the output and the agent decides.

Cost of recording it: a MutationObserver with a bounded ring buffer. Measured
at 0.1 to 2.7ms across mutation rates up to 10,000, against a drift floor of
1.7%. Reading it per observation is under Chrome's 0.1ms timer granularity.
Against a model turn of about 3.6 seconds there's nothing here to optimise.

One thing I nearly got wrong and only caught by measuring the ugly case first.
The Guardian runs about 7 ad-driven DOM mutations in a two-to-four second
window. A banner
keyed on "did anything move" fires permanently on a page that is completely
readable. I had just finished deleting a signal for exactly that failure, and I
rebuilt it one unit over without noticing. What saved it was checking the ad
case before shipping instead of after.

The fix isn't a quiet-period threshold, it's that the kind of change is the
fact that matters. The browser already tells you: childList, characterData,
attributes. 40 style changes on a carousel and 40 structural changes on the
table you're reading are opposite facts, and they get opposite sentences.

    DOM changing, structural -> "elements are being added or removed right now,
                                 don't conclude something is absent"
    DOM changing, attributes -> "nothing was added, removed or re-texted, so
                                 the listing is structurally current"
    DOM quiet, network busy  -> "what's rendered now is not being rewritten.
                                 Whether MORE arrives is what those requests
                                 decide."
    both quiet               -> nothing at all

That third one took a few goes. An earlier draft said "stable and safe to
read", which is a judgement, not a measurement. Whether this read is good
enough depends on what the caller is looking for, and the caller knows that and
I don't.

## B. The longer one, with the part I like better

The above is the feature. This is what happened when I went to verify it in a
real browser, three months later, and it's the better story.

I'd added a refinement: when you read one region of a page instead of the whole
thing, the readiness answer should describe that region, not the document. A
clock ticking in a header and a table rebuilding are the same number and
opposite facts.

Measured it on a page with a live ticker beside a table that had finished:

    document-wide         last change 48ms ago,   110 structural
    scoped to the table   last change 4013ms ago,   0 structural

Good. Three controls to make sure it isn't just "always say quiet when scoped":
scope to the ticker and it still reports churn, scope to a region still being
built and it never reports quiet, scope to something rendering inside a shadow
root and it's still seen. All held.

Then I went to the live browser to capture the before-and-after, and the before
didn't make sense. The scoped read showed no banner. On the OLD code, where
scoped and unscoped are literally the same call.

I had three decent explanations within about a minute, all of them about
timing. All three were wrong.

What was actually happening: the server prepends a line to the listing that
says "scoped to the subtree of ref_5". It was putting that line in front of the
banner. The function that protects the banner from truncation matches at
position zero. So the banner stopped being a banner, became ordinary body text,
and got cut.

    max_chars 300:   no banner
    max_chars 420:   no banner
    max_chars 700:   no banner
    max_chars 50000: banner appears, below the scope header

The readiness signal had never been visible on a scoped read at any budget
anyone would actually use. And a scoped read is the documented way to look
deep into a page, so it was missing from precisely the reads that go deepest.
Fourteen hundred automated checks, all green, the whole time. They test the
function. They don't test what the server does with its output.

While I was there, a second thing. My first probe drove the test with a
setInterval ticker, and it stopped dead after 45 ticks.

    before: T45
    after:  T45
    ms since last DOM change: 19993

The agent's tab is hidden on purpose, because the whole point is to not drag
you out of what you're doing. Chrome intensively throttles a hidden page's
timers. So the ad-ticker case I'd partly built this for is rarer in my actual
situation than on a page you're looking at, and a synthetic timer can't drive a
live test here at all. I had to drive it with a real page action instead.

That one's not a bug. It's just a thing about the environment that I'd have
kept getting wrong.

## C. The one-liner if someone asks what the point is

Most agent frameworks hand the model a snapshot and say nothing about whether
it's finished. Mine says which of four states it's in, prints the number it
decided from, and recommends nothing, because what counts as ready depends on
what you're looking for.

---

## Notes for whoever sends this

- Do not say the scoped fix is confirmed in a live browser. It isn't yet. The
  live observation in section B is of the BROKEN behaviour, which is a stronger
  claim anyway because it's a defect found rather than a feature asserted.
- The 9–18ms vs 907–3514ms figures are from the fixture probe reproduced in
  `tools/test_readiness.py` R11–R13. The 0.1–2.7ms cost figures and the 1.7%
  drift floor are from the interleaved A/B in CLAUDE.md #70.
- The ptable numbers (300/420/700/50000) are from a live session and are in
  CLAUDE.md #76.
- If anyone asks for the threshold: there isn't one. The window is 3000ms and
  that number IS measured (a 1000ms window is 50.7% false-quiet when a page
  commits every 2s, which is what a throttled hidden tab does), but the window
  only bounds how far back we look. Nothing in the output decides "ready".
