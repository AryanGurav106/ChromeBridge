# Post 009 — we audited our headline number and it went down

Status: DRAFT, not posted. Every figure re-derived from `tools/bench_mind2web.py`
on this machine before this was written. Sources: CLAUDE.md #73 and #78,
`tools/_m2w_ruler.py`, `tools/audit_mind2web_labels.py`.

Register: plain. No em-dashes, no bold headers inside the post body,
contractions, short sentences mixed with long.

**Claims this post is NOT allowed to make.** It must not present the new number
as an improvement. It is lower. The improvement is in the denominator and in
what the labels mean, and if that doesn't come across the post has failed. It
must also not quote a point estimate with a confidence interval — the actions
come from 22 trajectories and leave-one-site-out moves it several points.

---

## A. The short one

My browser agent has quoted the same accuracy number for about a year. 96%
target recall on Mind2Web, which is the standard benchmark of human-labelled
click targets.

I audited it this week. It's 95.2%.

The number went down and I'm more confident in it than I was in the higher one,
which sounds like a thing people say to spin a bad result, so here's the actual
mechanism.

The benchmark was scoring 173 actions. The dataset has 186. The other 13 were
excluded by a line in my own code that said their targets were "absent from the
saved snapshot entirely".

They were not absent. Every one of those 13 ids is sitting in the snapshot
string. They disappear when Chrome re-parses it.

Mind2Web serialises its pages XML-style. So an empty element comes back looking
like this:

    <a/>
    <iframe/>
    <textarea/>

HTML has no self-closing syntax for those tags. The slash is ignored. The tag
opens. And `<iframe>` and `<textarea>` are raw-text elements, which means one of
them swallows the entire rest of the document as plain text.

On ESPN's page that took it from 4,115 ids in the string to 744 in the DOM. All
three of that site's targets were sitting after the broken tag.

So the number wasn't 96% of the targets. It was 96% of the targets that happened
to survive a parser bug, and the 13 that didn't were being quietly dropped out of
the denominator with a comment explaining it as a property of the data.

Fix the parse and all 13 come back as exact hits. One denominator now: 186.
177 of them. 95.2%.

The element-itself figure, not counting an ancestor or descendant we surfaced
instead, went the other way: 85.5% up to 86.6%.

## B. The part that decided which fix to use

There were two ways to repair it.

The minimal one patches only the two raw-text tags that cause the document to be
eaten. It's about four lines and it produces 96.2%, which is higher than the
number I'd been quoting.

The faithful one patches every non-void tag. It produces 95.2%.

I shipped the one that makes my number worse, and not out of modesty. Here's the
measurement that chose it, run over all 186 snapshots with every arm on the same
page load:

    arm                 distinct ids    duplication    samples with CLONED nodes
    unrepaired          99.0%           1.021          137 / 186
    minimal fix         99.8%           1.021          137 / 186
    faithful fix        99.8%           1.000            0 / 186

That last column is the one. HTML's error recovery doesn't just drop unclosed
formatting elements, it re-creates them further down the document. So a single
`backend_node_id` ends up on several different DOM nodes. In 137 of 186 samples,
the label that says "the human clicked this element" was pointing at more than
one element.

A ruler whose labels are ambiguous on three quarters of its samples isn't a
ruler. The minimal fix leaves that intact and gives you a prettier number on top
of it.

It also leaves three specific false credits standing, which I only found because
the faithful fix removed them. One of them was an IKEA label credited to a link
eleven levels up holding 638 elements and 90% of the viewport. Clicking that is a
skip link. The dataset's own recorded geometry for two of the others is
`-1,-1,-1,-1`, meaning they rendered nothing at all.

## C. Four things my own audit got wrong

I wrote an audit of this number a few weeks ago. The audit was itself wrong in
four places, found when someone went to close the work it had left open.

One was arithmetic. I'd written that bounding the credit rule "gives 165 of 173".
It gives 166. Refusing to credit an oversized ancestor doesn't lose the row — it
falls through to a descendant. My table had no way to express that, so it counted
the refusal as a miss.

Two were claims that can't both be true. I'd said the minimal repair gives 96.2%
and that it "also fixes the IKEA credit for free". It doesn't fix it. Only the
faithful one does. I had written both sentences in the same paragraph.

And the audit's own probe reported "1,706 ancestor credits refused by the cap"
when the real number is 1 — it was counting every oversized ancestor that merely
existed, including rows that were already credited directly. Which is verbatim
the bug that same audit records catching in an earlier probe, two pages up.

## D. What I'd take from this if I were reading it

The benchmark number was never the risk. The risk was a line of code that
explained away 7% of the dataset, in a comment, confidently, and was wrong.

Nothing automated was going to catch that. The suite was green. The number
reproduced exactly, three different ways, for a year. What caught it was someone
asking why those 13 were excluded and then checking, instead of reading the
comment.

If you are quoting a number from your own tooling, the thing worth auditing
isn't the computation. It's the denominator, and specifically anything your code
decided not to count.

---

## Notes for whoever sends this

- Quote **~95%**, never 95.2% bare, and never the superseded 96.0%. The actions
  come from 22 trajectories and leave-one-site-out moves it by several points.
- `tools/bench_mind2web.py --no-repair` still prints the historical 96.0%/173,
  labelled as what it is. That's worth mentioning if anyone wants to reproduce
  the old figure.
- The nine remaining misses are all elements that declare nothing clickable in
  static markup — no role, no handler, no href, no tabindex. These snapshots
  carry no scripts and no CSS, so two of our eight admitting signals measure
  0/186 and cannot fire at all. It's a structural floor, not a ceiling.
- Do not frame section C as self-flagellation. It's there because an audit that
  reports only other people's errors isn't an audit.
