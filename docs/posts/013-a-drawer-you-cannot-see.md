# Post 013 — A drawer you cannot see took the whole page

Status: DRAFT, not posted. Every figure is from CLAUDE.md #80, the commit
`b01478a`, `tools/bench_turns/eval6/`, or a probe named below.

Register: plain. No em-dashes, no bold headers in the body, contractions, short
sentences mixed with long.

**Claims this post is NOT allowed to make.** It must not say the fix made things
measurably better on real sites — it did not, and that is in the post. It must
not quote a bare accuracy number (see the queue's rules). It must not present
the eval as a win; the eval was a tie and the defect is the yield.

---

## A. The short one

I was running a small benchmark on my browser-agent project. Five tasks, two
ways of formatting the same page, eight agents, none of them told what was being
compared.

Two of them, on different runs, hours apart, reported the same thing in almost
the same words. The listing they got back for a grocery category page was full
of perfume, a computer monitor, pizza, and parrot food.

The page was about vegetables.

## B. What was actually happening

The listing has a cap. Only so many elements get a full row, and the rest go
into an overflow list at the bottom that keeps every reference but not the
detail. To decide what makes the cut, there is a priority set: things inside a
dialog, required fields, unselected dropdowns, form inputs. The idea being that
those are what's in front of you.

The app had two drawers — a checkout panel and a payment sheet — sitting
off-canvas, parked exactly one viewport to the right, waiting to slide in. They
are real elements. They are rendered. They are not hidden with `display: none`,
because then they couldn't animate in. And they announce themselves as dialogs.

So they got priority. All 150 slots of it. Every single detailed row in the
listing was drawer content, and the category the agent had just navigated to —
its subcategory buttons, all five of its products — was in the overflow.

One of the agents put the diagnosis better than my own first reading:

> it promoted a drawer the listing itself had labelled "off to the side"

That is the part that stung. The listing already said it. Every one of those
rows carried a flag saying it was parked off the side of the screen. And a
separate pass in the same file had already decided, correctly, that no dialog
was open — which is why no "a modal is open" banner was printed. The fact that
disqualified those rows was computed, printed, and then ignored one function
later.

## C. The fix is one condition, and the obvious version of it is wrong

The obvious key is the off-screen flag. Those rows are flagged off-screen, so
don't prioritise off-screen rows.

That breaks the case the rule exists for. A dialog taller than your window has
its lower half off-screen, and those rows *are* its content. The field's own
comment in my code says so: "typically modal scroll content". Keying on it would
fix the drawer and quietly truncate every tall modal on the web.

What actually distinguishes the two is whether a dialog is open at all. That was
already computed. One condition.

## D. The uncomfortable half

I measured it across 40 archived real websites, both versions against the same
page load so run order couldn't be confused with the change.

One site changed. By three rows, against that site's own run-to-run noise of
four. In other words: nothing.

So on 40 real sites this fix is worth zero. It is worth everything on the page
where it was found, and on the test I wrote to pin it — where the old rule shows
0 of 60 page rows and 200 drawer rows, and the new one shows all 60.

I wrote it up as "measured harmless, not measured valuable". The corpus doesn't
contain the pathology. A measurement tells you about your code *against your
sample*; it cannot tell you about your sample. That distinction has bitten this
project enough times that it has its own entry.

## E. What I'd want someone else to take from this

Two things.

**A fact you compute and then don't use is worse than one you never had.** The
flag was right there in the output the agent was reading. Two agents saw it and
reasoned correctly from it. My code printed it and then made the opposite
decision.

**Run the benchmark against yourself, not just against a competitor.** This eval
ended in a dead tie — 34 turns to 34, both arms completing every task. On the
headline metric it was a null result, exactly as the pre-registration predicted
it would be. The eight defects it found were all mine, and none of them were in
the part I'd spent the most time on.

---

## Notes for whoever sends this

- Do not frame the eval as a comparison anyone lost. It was tree-vs-flat
  formatting of our OWN listing, not us versus another product. If asked, say
  that plainly.
- The "both agents found it independently" detail is the strongest thing here
  and should not be oversold into "agents review better than humans". They had
  the symptom in front of them and I did not; that's all it shows.
- If asked for the number: 1 of 40 archived sites changed, by +3/-3 rows against
  that site's own drift of 4, for -0.11% of listing characters overall.
- The one site in the set with a dialog genuinely open is untouched. That's the
  control and it's worth mentioning if anyone asks whether the fix just deletes
  dialog handling.
