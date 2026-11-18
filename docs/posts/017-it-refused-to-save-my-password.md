# Post 017 — my own tool refused to save my password, and it was right to

Status: DRAFT, not posted. Every figure is from CLAUDE.md #86,
`flows/acme-invoices-drilldown.flow.json`, and the run logs in this session.

Register: plain. No em-dashes, no bold headers in the body, contractions, short
sentences mixed with long.

**Claims this post is NOT allowed to make.**
It must not imply the flow proves anything about real websites. It runs against
a fixture app in this repo, which I wrote, and that is stated in the body.
It must not quote "0.71s" as a comparison against anything. It is a replay time
on a local server and means nothing next to another tool's number.
It must not present the CI story as a disaster averted. Nothing shipped broken
to a user. What was broken was the public repo's build, for three days, and the
honest framing is that I wasn't looking.
It must not claim the review fix makes recorded flows more correct. It fixes
what the recorder SAYS about its assertions, not the assertions themselves.

---

## The post

I spent today trying to break my own record-and-replay feature, and the first
thing that happened is it refused to do what I asked.

The idea of the feature, quickly. You drive a browser once with Claude. It
watches, and compiles what you did into a replayable test. The part people
don't expect is that the checks Claude made along the way become the
assertions. You don't write them. If Claude read the row count after clicking
submit, that row count is now what the test asserts.

So I recorded something harder than usual. Log into an app, get redirected to
the login page first, sign in, land on an invoices table, filter it, sort it by
clicking a column header, click into one row, and read a reference number off
the detail page. Six steps. Real state at every one of them.

Then I called stop, and it told me it had thrown away my login.

    step 1 (fill_form) dropped. field(s) ['fields.0','fields.1'] carry a typed
    value addressed by CSS selector, whose declared type cannot be read, so this
    recorder cannot tell a password from any other value.

I'd filled the form by CSS selector instead of by element reference. A selector
doesn't tell you the input's type. The recorder's rule is that what counts as
secret has to be declared, not guessed, because a guess fails in both
directions at once. A wordlist would miss a field called `kennwort` and redact
one called `password_hint`. So with no declaration available, it refused the
step rather than writing my password into a file whose entire purpose is to be
committed to git.

That's the right call and I didn't like it for about ten seconds. I re-recorded
addressing the fields by reference, the type came through as `password`, and
the saved file has this where the value should be:

    "${CHROMEBRIDGE_SECRET:CB_SECRET_ACME_INVOICES_DRILLDOWN_PASSWORD}"

grep for the actual password in that file returns zero.

## Then I read the file instead of the summary

The replay works. Six steps, five of them asserting something, and it runs
clean. That's the demo everyone wants and it's also the least interesting part.

What I did next was open the JSON and read it, rather than trusting the summary
the recorder prints. Five of the six steps carried this line:

    unevidenced: every check on this step is hollow or unproven, so none of
    them is known to be able to fail

That line exists for a real reason. The worst thing this feature can produce
isn't a flow that fails, it's a flow that passes because its assertions were
already true before the step ran. I shipped that bug twice while building this,
so there's now an analysis that reads back over the recording and asks, for
every check, whether anything in the session ever saw it hold a different
value. If nothing did, it says so.

Except step 3 asserted the URL path, and the path had plainly changed. It went
from `?q=Corp&sort=id` to `?q=Corp&sort=amount` between the two observations.
That check could obviously fail.

The cause was dull in the way these usually are. The path check is the newest
of the four kinds of assertion this thing records, and the function that grades
assertions was written before it existed. It knew about three kinds. The fourth
fell through a gap and counted as neither evidence nor a warning.

So it was wrong in two directions at once. Loudly: it told me to distrust the
soundest line on the step. Quietly, and this is the worse one: a path check that
genuinely couldn't fail would never have been flagged at all, which is the
entire job of that warning.

## Proving it instead of arguing it

I could have just fixed it. Instead I ran the flow with one variable
overridden, swapping the filter from "Corp" to "Ltd", which makes the page
land on a different URL.

    FAIL  acme-invoices-drilldown  3/6 step(s)
          step 3 (fill_form): path is '/invoices?q=Ltd&sort=id&dir=asc',
                              recorded '/invoices?q=Corp&sort=id&dir=asc'

It fails on exactly the check the review had called incapable of failing. That's
better evidence than my reading of the code, and it took one command.

There are three new tests now, and the thing that makes them worth having is
that I ran all three against the old code first and watched them fail. That
sounds obvious. It isn't. This project has found seven tests that passed for
the wrong reason, each one written by someone who was sure it was testing what
they thought. The only way to know is to break the code and check the test
notices.

## And then CI, which I hadn't looked at in three days

While chasing all this I ran the flow suite, saw an unrelated failure, and
followed it to GitHub Actions. Red since the 16th. Two separate reasons.

The first one is the funniest bug I've written in a while. A few days ago I
fixed a crash where a page containing an unpaired UTF-16 surrogate would kill
the server process. Real bug, real fix. And I wrote a docstring explaining it,
which spells out the character it's about:

    a page keeps them (`textContent` and `document.title` both preserve
    `\ud83d` in Chromium)

That's an ordinary Python string, not a raw one. So the docstring didn't
describe a lone surrogate. It contained one. And from Python 3.13 the compiler
refuses to compile a docstring holding one, because it encodes it while
tidying the indentation.

Seven test suites died at import on the 3.13 leg of CI. All of them passed on
3.10 and on the 3.12 I actually develop on. The project runs CI on two Python
versions precisely to catch this class of thing. The machinery worked fine. I
just never read the result.

The second reason was a flag that meant "loopback" when it should have meant
"a server this test harness can actually start". A flow pointed at a local
benchmark server on port 8080 was being kept and then failing every build,
because the build has no such server.

Both fixed. There's a new check that scans every docstring in the project for
this, with a planted violation to prove the check can fire, because a scan
that has never been seen to find anything is also asserting that nothing is
wrong.

## What I'd take from today

Two things, and they're not about browsers.

The tool refusing me was the best outcome available. It didn't try to be clever
about which field looked like a password. It said what it couldn't determine
and stopped.

And the defect came from reading the artefact rather than the summary. The
summary said six steps, five asserted, which is true and reads like success.
The file said something else.
