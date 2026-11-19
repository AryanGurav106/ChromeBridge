# Eval 14 — BLOCKED, and the cause is not what the arm reported

Status 2026-11-19. The pre-registration stands; no data was collected for
either arm, so nothing here may be quoted as a result.

## What happened

The Claude-in-Chrome arm could not reach the fixture. Its agent navigated to
`http://localhost:8787/`, got a success line back, and then every page-touching
tool failed with `Failed to read page: Frame with ID 0 is showing error page`.
It ran four controls — a second navigate, `127.0.0.1` instead of `localhost`, a
wait-then-retry, and `http://example.com` — and concluded the fixture was not
running.

**That conclusion is wrong, and the arm had no way to know it.** The fixture
was serving throughout: `curl` returned 200, the process was alive, and
ChromeBridge had read the same app minutes earlier.

## The decisive control, which only a second toolset could run

Same browser, same minute, same URL:

| | result |
|---|---|
| ChromeBridge | `Navigated to http://localhost:8787/, title: Sign in · Acme Ops`, and `search_page` returns the page's own text |
| Claude-in-Chrome | `Frame with ID 0 is showing error page` |

So it is not the fixture, not the port, not the host spelling, not the network
and not the browser. It is specific to that extension on this origin.

**The cause is NOT established and is deliberately not guessed at here.** Two
candidates, both checkable by the user and neither by us: that extension's own
site-access configuration may not cover `localhost`, or Brave's localhost-access
shield may be blocking it for that extension. Its failure renders as a Chrome
network-error page rather than a permission message, which is what makes the
two indistinguishable from outside.

## Why this is recorded rather than worked around

Moving the task to a public site is not a fix: it would change the experiment
and it is blocked anyway, because the four candidate public origins are
ungranted for ChromeBridge. The symmetric unblock is the user granting that
extension access to `localhost`, exactly as they grant origins for ours.

## Two things the blocked run established anyway

- **An arm with one toolset cannot distinguish "nothing is listening" from
  "this toolset cannot reach it".** The agent's controls were well chosen and
  all four are consistent with both explanations. This is a general limit on
  single-arm diagnosis and it is why the cross-check above is worth running
  before believing any "the environment is broken" report.
- **`mcp__claude-in-chrome__navigate` reported `Navigated to
  http://localhost:8787/` for a navigation that did not load a page**, and the
  failure had to be discovered from a different tool two calls later. That is
  the same class as our own #40 (`NAVIGATION DID NOT COMMIT`), which cost ~9
  calls across two eval tasks before it was fixed. Recorded as an observation
  about the other arm, from one sighting, not offered as a measurement.
