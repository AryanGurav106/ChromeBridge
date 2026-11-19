# Post 019 — It typed into a button and told me it worked

Status: DRAFT, not posted. Every figure is from CLAUDE.md #97, #98, #99, #101,
#107, #108 and #109, or from the commits those entries cite. The live
reproductions named below are in those entries with the exact strings.

Register: plain. No em-dashes, no bold headers in the body, contractions, short
sentences mixed with long.

**Claims this post is NOT allowed to make.** It must not say the representation
is now correct, or perfect, or finished. It must not quote the generality zeros
as if they prove the absence of this bug class, because those measure presence
and this class is about a tool reporting success. It must not imply the test
suite found any of these, because the suite was green through all of them. It
must not say the fifth one was reproduced live, because it was found by reading
a spec against our source. It must not say the fixes are verified in a user's
browser; they are verified in a throwaway profile. And it must not compare the
0.9766 against 0.9722 as a before/after, because those are different samples
and #108 says in as many words that the gap between them is composition. The
paired number is the only one licensed here.

**Ordering note.** This is a strong post and it is also five admissions in a
row. Do not send it adjacent to 009 or 016. It wants a capability post on
either side of it.

---

## A. The short one

I spent a day hunting one kind of bug. Not "the tool failed". Tools that fail
are easy, they say so. The kind where the tool is wrong about what it just did.

I found five.

The clearest one: I asked the form filler to set a dropdown. It reported
success. It told me the field now read "eu-west-1", which is what I'd asked
for. The field was empty. It had typed text into a button, read back the text
it had just typed, and called that confirmation.

The single-field version of the same tool refused the identical element, in the
same session, with a message explaining exactly why a button can't hold typed
text. One tool knew. The other was the one our own docs call "strongly
preferred".

## B. The long one

Here's why this class is worth a day.

A tool that errors is a tool you can route around. The agent reads the error,
tries something else, the user sees a slower run. A tool that lies costs you
the thing underneath: the agent believes a field is filled, carries on, and
every later step is built on a page that isn't in the state it thinks it is.
If the run was being recorded as a replayable test, the lie gets compiled into
the test as a passing step.

So I went looking. Five, four of them found by driving the thing rather than
reading it:

**The form filler typing into a dropdown trigger** and reading back its own
write. The cause was one line in two places. The part of the system that READS
the page already knew that element opens a menu. It prints "(opens
menu/popup)" for it. The two places that WRITE stopped at an older signal and
fell through to "this is a text field". Both carried a comment saying KEEP IN
SYNC. Both had drifted from the copy that was right.

**The option picker offering a modal's own Cancel button** as one of a field's
choices, under the words "pass one of these exactly". That one fires when a
dropdown fails to open, which is exactly when an agent is already in trouble.
I reproduced it before touching anything, and the worst version of it reported
success for picking a label the field was merely displaying.

**A recorded test binding to the wrong row.** The safeguard that would have
caught it sits three lines below the code that returns, so it was never
reached. Worse: the older, dumber path REFUSED that case. The fix for the
previous version of this bug had introduced the next one.

**A click guard saying "the page did not react"** about clicks that plainly
worked. That's the same family pointed the other way, not a false success but a
false failure, and it still costs the agent a round trip finding out it was
fine. It asked the browser a question (did this tab start a navigation) and
asked it too early. I measured how early: 81, 89 and 91 milliseconds, three
trials. It waits for the answer now instead of sampling for it, and only on the
path where it's about to warn you.

**And one I did not find by driving.** A survey read the current spec against
our source and found that when a page declares its own tools, we were picking
one by name alone. Two frames on a page can each register a tool called
"search". We printed the thing that tells them apart and then threw it away, so
the first one won, silently. The spec's own risk section says to use exactly
the field we were discarding. Two candidates is a refusal that names them now.
I have no live case of this; the page-declared-tools API is new and barely
deployed. I'd rather fix it while it costs nothing.

## C. The part I didn't expect

The measurement that catches this class is an independent one. We compare the
names we derive for elements against Chrome's own accessibility tree, because
everything else we measure scores us against ourselves.

I went to run it after a day of changes. It refused to start.

Its self-test requires a specific disagreement with Chrome to show up, as proof
that the comparison can still detect a difference at all. That disagreement was
a bug of ours. We'd fixed it that morning. So the proof couldn't fire, and the
probe failed on its own success.

That's a real rule and it's easy to miss: if the thing proving your measurement
works is a defect, your measurement expires the day you fix it. I rebased the
proof on a difference we have measured and deliberately not fixed, with a note
saying to rewrite rather than delete it if that one ever closes too.

Then it ran. The right way to read it turned out to be a pairing I hadn't asked
for: an older run of the same probe happened to sit on disk from before the
three commits that touched the name path, so it's a genuine before and after on
one sample. Site by site, 163 sites: agreement with Chrome went 0.9728 to
0.9773. Twenty-six sites improved, 123 unchanged, 14 worse. The specific
mechanism the fix targeted went from 54 cases to 1.

That is not a big number and I'm not going to dress it up. What it says is that
the fixes moved the thing they were aimed at and didn't break the rest.

## D. What this doesn't say

It doesn't say the representation is correct now. Five of these existed this
morning and the suite was green through every one of them. The honest read is
that this class gets found by using the thing, and the suite's job is making
sure a fix stays fixed.

It also doesn't say much about how many are left. I can tell you none of the
five was exotic. The widget that broke the form filler is one of the most
common dropdown shapes on the web.

There was a sixth thing the same day that isn't a code bug at all, and it might
be the one I think about longest. An agent recorded a login, couldn't replay
it, and concluded the feature was unusable from inside a session. It spent four
calls proving that. The mechanism had worked the whole time. The secret goes
in a file the project already reads. The refusal message told it to export an
environment variable and run the command again, which is shell advice to
something with no shell.

Nobody wrote a wrong line of code there. The tool just said something untrue
about itself, confidently, and was believed. Which is the whole post.
