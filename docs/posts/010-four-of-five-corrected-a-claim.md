# Post 010 — I pointed five agents at my own work. Four corrected a claim, not a bug.

Status: DRAFT, not posted. Every figure below is from CLAUDE.md #77–#79 or the
commit it cites.

Register: plain. No em-dashes, no bold headers inside the post body,
contractions, short sentences mixed with long.

**Claims this post is NOT allowed to make.** It must not read as "my process is
rigorous, look at me". The useful content is the specific shape of what they
found, which is transferable. Cut any sentence that is about me rather than
about the finding. It also must not quote a bare accuracy number — see the
queue's rules.

---

## A. The short one

I spent a day pointing agents at my own browser-agent project instead of at
features. Five of them, in parallel, each on something different. One reviewing
code I'd written that morning, one closing debts an old audit had left, one
measuring two questions I'd marked "measure before you build", one attacking the
record-and-replay feature, one reading the literature.

Four of the five came back having corrected a *claim* rather than found a bug.

That ratio is the thing I'd want someone else to take from this.

**The reviewer** was given the code and deliberately not my reasoning. It found
six paths where a readiness probe would report "nothing is changing" when the
honest answer was "I couldn't see". The sharpest: a read scoped into an iframe
reported silence while that frame was painting four thousand rows. My own
comment, two lines above the bug, named that exact hazard and then shipped it.

It also proved two of my brand-new tests were worthless. Ablating a fifteen-line
helper to `return true` — or `return false`, either — left all ten of my checks
green, because not one fixture contained an iframe. I'd written twelve lines of
comment about that function.

**The literature agent** found that a differentiation claim I'd been making for
months was false. I'd written that a certain browser capability was "the one
thing no Playwright-based agent can have". Playwright shipped it on the 7th of
October. Both halves of my justification were wrong too.

**The audit-debt agent** found four errors in my own previous audit, including
an arithmetic one, and a probe of its own that reported 1,706 where the real
number was 1 — which is verbatim the bug that same audit records catching in an
*earlier* probe, two pages up.

**The measurement agent** found that half of one of my open questions was simply
wrong in its premise, and that the cost assumption attached to it was wrong in
the other direction: the expensive thing I'd been avoiding was already being
paid on every read.

The flow agent found a replay that passed five steps out of five having operated
on the wrong record.

## B. The one that moved a number the wrong way

The headline accuracy figure for this project had read 96% for about a year. It's
95.2% now.

The benchmark was scoring 173 actions out of a dataset of 186. The other 13 were
excluded by a line of my own code that said their targets were "absent from the
saved snapshot entirely".

They weren't absent. The dataset serialises XML-style, so an empty element comes
back as `<a/>` or `<textarea/>`. HTML has no self-closing syntax for those. The
tag opens, and a raw-text element then swallows the rest of the document. One
page went from 4,115 identifiers in the string to 744 in the DOM.

Fix the parse and all 13 come back as exact hits. One denominator. 95.2%.

I shipped the repair that makes the number *worse*. The minimal version gives
96.2% and leaves 137 of 186 samples with cloned nodes, because HTML's error
recovery re-creates unclosed formatting elements — so one "the human clicked
this" label ends up pointing at several different elements. A ruler that's
ambiguous on three quarters of its samples isn't a ruler.

## C. Why I think this works, and the part that isn't comfortable

The agents weren't better than me. Three of the five shipped a probe bug that
damned the system before they caught it themselves. One watched its own
measurement go from "55 losses" to "34 losses" to "zero", and every single step
was a bug in its own ruler, not a change to the product.

What they had was no attachment to the claim. I'd written "this is a structural
lower bound" three times across three months and never once checked what it was
worth. An agent with the same sentence in front of it asked how much, measured
it at 59.7%, and that turned a comforting phrase into a number.

The uncomfortable part: almost everything they found was in something I'd
already tested and already written up confidently. The code was green the whole
time. 1,313 automated checks, all passing, while a scoped read had never once
shown a readiness banner at any budget anyone would actually use.

## D. The one-liner

If you want to know whether your own claims hold, the cheapest thing you can do
is hand them to something that has no stake in them, and ask it to check rather
than to agree.

---

## Notes for whoever sends this

- Do not name the other product in section A's Playwright paragraph as a
  competitor being caught out. They shipped a feature; we had a stale claim.
  The error is ours.
- Section C is the point of the post. If it gets cut for length, cut B instead.
- The 59.7% figure needs its scope if anyone asks: it is the share of listing
  rows that depend on a registered event listener or a CSS pointer cursor,
  measured on six synthetic apps. It does not transfer to the web as a
  percentage; the mechanism does.
- If asked "did the agents write the fixes": they proposed, I read every diff,
  and two of their suggested fixes were wrong in ways I caught by running them.
  Say that plainly rather than implying either full autonomy or full control.
