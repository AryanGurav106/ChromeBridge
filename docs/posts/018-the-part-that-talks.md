# Post 018 — I stress-tested the part of my agent that reads pages. Both bugs were in the part that talks.

Status: DRAFT, not posted. Figures from CLAUDE.md #89, #88 and #90, and
`docs/research/STAGE-GENERALITY-2026-11.md`.

Register: plain. No em-dashes, no bold headers in the body, contractions, short
sentences mixed with long.

**Claims this post is NOT allowed to make.**
It must not say the DOM reader is finished or perfect. The measurement covers
what SURVIVES, not whether the right name is on the right element, and that
second question is open and named in the body.
It must not quote the sample as representative. Roughly 180 candidate sites
never reach the probe because a headless browser cannot get past their consent
or bot walls, and those are unmeasured, not passed. Say so.
It must not present "0 lost" without the strict/lenient distinction, which is
the whole point of the middle section.
It must not imply we found these by being clever. A subagent found them, and
the ablation is what stopped me shipping a fixture that proved nothing.

---

## The post

My browser agent reads a page and hands the model a listing of what it can act
on. I've spent months making sure nothing goes missing from that listing. The
number I had was good: 260 live sites we'd never tuned on, zero controls lost.

Then I looked at how that number was produced and it was one read, of each
page, at first paint. Nothing opened. Nothing clicked. Which is not how anyone
uses a browser.

So I had an agent go and measure the other thing. 255 sites, up to four
interactions deep, each one opening something on top of what the last one
opened. 580 reads, 325 of them after an interaction. 73,274 controls.

Nothing lost. Across fourteen writing systems, including Arabic and Hebrew
right-to-left, Thai, Devanagari, Bengali, Korean, both Chinese scripts.

That's the headline and it's the least interesting part of this.

## The number I'd been quoting was weaker than it read

There are two ways to ask "did we lose this control". The loose one is: does
its name appear anywhere in the output. The strict one is: does it have a row
of its own that you could act on.

I'd been reporting the loose one. I knew it was weaker. I had never measured
how much weaker.

So the agent mutilated real listings, live, and watched both numbers move. On
one government site, deleting 67 of 133 entries moved the loose metric by one.
The strict one moved by 27.

The loose number is nearly worthless as a guarantee. Both are zero here, which
is why the result stands. But every earlier time I quoted only the loose one, I
was saying less than people heard.

I'd rather say that out loud than have someone work it out later.

## Both bugs were somewhere I wasn't looking

Here's the thing I actually want to tell you.

The collector, the part that decides what exists on a page, came through clean.
Two defects came out of the run and neither of them was in it. Both were in the
layer that *describes* the page to the model.

The first one. There's a thing called a `<dialog>` element. You can open it two
ways: `showModal()`, which makes the rest of the page inert, or `show()`, which
doesn't. The browser will tell you which, via `:modal`.

A component library opens a small popover using a `<dialog>` sized to the whole
viewport, because that's a convenient way to position something. Opened with
`show()`. Not modal. The browser says so.

And my code asked the browser, got told "not modal", and then overruled it with
a size check. So an ordinary tooltip announced A MODAL IS OPEN and told the
model to ignore the rest of a page you could click on perfectly well.

The size check exists for elements that declare nothing at all, where geometry
is the only signal left. Applying it to something that had just answered the
question is backwards.

The second one is worse in a quieter way. When controls are hidden from the
accessibility tree, the listing says so and suggests why. It said: a dialog is
open, focus-trap libraries hide the page that way, dismiss it and re-read.

Counted on the actual page: 50 elements hidden before the dialog opened, 50
while it was open, 49 after it closed. They were decorative icons, hidden
permanently, like icons always are. The dialog had nothing to do with it, and
"dismiss it and re-read" brings back one element.

There's a comment twelve lines above that code saying never to assert a cause
you haven't verified. The code under it did exactly that. The neighbouring
branch, for the non-dialog case, gets it right.

## Same week, same shape

While that was running, another agent found this: the DOM implements
`element.textContent = "..."` by removing the old text node and inserting a new
one. Which arrives as a *structural* change notification, identical to an
element being added or removed.

So every clock, every live price, every status line on the web was making my
readiness check say "the page is still changing, don't conclude anything is
missing". Permanently. On pages that had finished loading minutes ago.

Three separate things, one pattern. The part that reads pages is in good shape.
The part that explains them to the model is where the bugs moved to, and I
wasn't watching it.

## The bit where I was the problem

I wrote a test for the dialog bug. It passed.

I then ran it against the broken code, which is the rule, and it passed there
too. Which means it was testing nothing.

A `<dialog>` has `width: fit-content` in the browser's own stylesheet. I'd
written the test element to stretch edge to edge, and it hadn't. It was 52
pixels by 21. The size check it was supposed to trigger needs half the
viewport.

The comment twenty lines above my test says, in as many words, that the first
version of *that* test had the same problem and proved nothing. I read it. I
did it again anyway, in the same file, the same day.

This is the eighth test in this project that passed for the wrong reason. The
only thing that has ever caught one is deliberately breaking the code and
checking the test notices.

## What I'm not claiming

Around 180 of the sites I wanted to measure never rendered, because a headless
browser can't get past their consent walls or bot checks. Banks, ticketing,
government portals. I didn't spoof a user agent to get in. Those sites are
unmeasured, not passed, and the sample leans easier than the real web because
of it.

And every number here is about whether a control *survives*. None of them asks
whether the right name ended up on the right element. That's a different
question, it's open, and I know how I'd measure it.
