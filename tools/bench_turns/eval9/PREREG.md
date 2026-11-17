# Eval 9 — pre-registration

Written and committed BEFORE any task exists and before any run. Eval 4's
headline had to be withdrawn when its prompt turned out to mandate the
behaviour it measured; eval 7 lost three runs to a generator bug; eval 8 was
void before it started. Each was only catchable because the design was on disk
first.

## Why this one is on PUBLIC sites, which eval 8 learned the hard way

Eval 8 used a locally-hosted benchmark for its exact event oracle, and the
claude-in-chrome arm scored 0/4 because **it is not driving a browser on this
machine**. Measured directly (eval 8, Amendment 3): `localhost:8080` gives an
error page, `https://example.com` loads fine, and this host's LAN address
reports a successful `navigate` while the tab stays where it was. Its tab ids
are `1662410xxx`; ChromeBridge's are `1711645xxx`.

So the trade is forced, and it is the whole reason this design looks like
eval 3's: **a local benchmark buys an exact oracle and costs the other arm
entirely; public sites buy a fair comparison and cost the oracle.** Scoring
here is a short exact string against ground truth a referee establishes
independently.

**A property eval 8 did NOT have, which falls out of the same fact:** the arms
are in different browsers, so cross-arm tab contamination is impossible. #39's
reason for running serially does not apply BETWEEN arms. It still applies
WITHIN an arm, so no two tasks of the same arm run at once.

## Design

- **Tasks written blind.** An authoring agent was told only to write two-hop
  browser tasks with short exact answers and a named distractor, given a
  deny-list of every domain used in evals 1–8, and told nothing about any
  toolset. It verified each answer against the live page or dropped the task.
  Its output is `tasks.json`, committed before any run.
- **Ground truth re-derived by a referee** — headless Chromium, deterministic,
  no model — not taken from the task author. Where the referee and the author
  disagree, the task is DROPPED, not adjudicated.
- **One independent agent per (task, arm).** No shared context.
- **Prompts from one template**, namespace substituted, then asserted identical
  with the namespace normalised away. A difference is a blocking error.
- **Both arms of a task launched together** (different browsers, so no
  cross-talk); tasks run one pair at a time.

## Bars, fixed now

- **H1 (primary)** — paired sign test on tool calls per task, ties excluded.
  At n=6 the best achievable two-sided p is **0.031**, so the bar is reachable:
  **p < 0.05**, i.e. 6/6. 5/6 is p = 0.219 and is a TIE. If tasks are dropped
  and n falls below 6, H1 cannot clear and will be reported as underpowered
  with the achievable p stated beside it.
- **Falsifier** — correctness against the referee's value. If either arm scores
  below 4/6 this is reported as a tooling failure, not a comparison.
- **Noise** — arXiv:2608.06171 measures a 12–14% rerun floor. A totals
  difference inside that band is not a result.
- **Wall clock is not a bar.** #35 and #41 both measured a ~47s/task drift floor
  that swallows it.

## What this cannot show

Both arms are the same model, so correctness saturates and is a falsifier
rather than a metric. And a tool-call count is not a quality measure: an arm
can be fast and wrong, which is what the falsifier is for.

---

## AMENDMENT 1 — two pairs per wave, not one. Written at launch.

The design above says "no two tasks of the same arm run at once". I am running
**two pairs per wave** (4 agents), so two tasks of the same arm DO overlap.

Reason, and the evidence for it: eval 8 ran four chromebridge agents
concurrently and all four completed, each in its own tab. The within-arm hazard
is specifically the one two of eval 8's claude-in-chrome agents reported —
`tabs_context_mcp(createIfEmpty)` handing out a tab another agent then
navigated — and every brief here carries the same instruction, identical in
both arms: *"Work in a tab you open yourself, and leave any tab that was
already open exactly as it is."*

**The risk this accepts, stated plainly:** if an agent reports an anomaly that
looks like another agent moving its tab, that pair is dropped rather than
scored, and the drop is recorded. It is not adjudicated and it is not quietly
kept.

Cross-arm contamination remains impossible for the reason in the design: the
arms are in different browsers (eval 8, Amendment 3).

Waves: `T3,T5` · `T6,T7` · `T8,T9` · `T10,T11`.

---

## AMENDMENT 2 — wave 1 blocked on CONSENT, which is the gate working

Both chromebridge agents in wave 1 returned UNOBTAINABLE after ONE call:

```
Permission required: ChromeBridge is not allowed to act on https://gml.noaa.gov
Permission required: ChromeBridge is not allowed to act on https://www.gesetze-im-internet.de
```

Neither read a page, neither retried, and both said so. That is default-deny
per origin behaving exactly as specified — the first op on a new site is
SUPPOSED to be refused — and it is the one thing in this comparison that is a
real product difference rather than a measurement artefact.

**It is a genuine asymmetry and it is recorded as one.** ChromeBridge pays a
one-time, per-origin consent cost that the other arm does not pay at all. Eval 7
handled this by arming `ALLOW_ALL_ORIGINS` for the duration under a dated
amendment, on the reasoning that per-origin consent is a setup cost rather than
a per-task turn cost, so counting it would charge us once per site for a safety
property the other arm lacks.

**I am NOT re-arming that flag on my own.** It was authorised once, for one
eval, by the user, and an approval for one run does not carry to the next. The
8 origins need granting in the side panel, or this eval reports as blocked.

Origins the run needs:
`gml.noaa.gov` · `gesetze-im-internet.de` · `postgresql.org` ·
`rfc-editor.org` · `federalreserve.gov` · `kubernetes.io` · `boe.es` ·
`nobelprize.org`

Wave 1 (T3, T5) is **not scored**: neither arm's number means anything when one
of them never reached a page. Both will be re-run once the origins are granted.

---

## AMENDMENT 3 — `ALLOW_ALL_ORIGINS` armed for this run, by the user, 2026-11-17

Asked and answered before touching anything: the user chose "Arm
ALLOW_ALL_ORIGINS for the run" over granting the 8 origins by hand or reporting
the eval blocked. Same treatment as eval 4's Amendment 5 and eval 7's
Amendment 2.

**Scope.** For the duration of eval 9's runs only, and restored immediately
after, verified three ways: the flag back to `false`, `git diff` empty, and
`node tools/test_permissions.js` reporting a full pass with **no "gate off"
caveat** — a suite that cannot exercise the consent half is not evidence for
it, which is why the caveat is the thing checked rather than the exit code.

**Known hazard, from eval 7's own notes:** a live MV3 worker does not
necessarily pick up a flag change, because our persistent WebSocket stops it
being evicted. Eval 7 measured the arming taking effect without a reload and
the RESTORE not taking effect for minutes. So the arming is VERIFIED by probing
a refused origin, and the restore will be verified the same way rather than
assumed from the file.

**What this run therefore cannot say.** Per-origin consent is a one-time cost
per site, not a per-task turn cost, so counting it would charge us eight times
for a safety property the other arm does not have. But with the gate off, this
eval says NOTHING about the cost of the consent model and must never be quoted
as though it did. That is the same sentence eval 7 recorded, and it is repeated
here because the temptation to quote it is exactly as strong.

## AMENDMENT 4 — the build the runs actually execute against

Caught by the user, not by me. I armed the flag, probed one refused origin, saw
it load, and took that as proof the environment was current. It proved only
that the FLAG had landed. Everything else changed in `background.js` today —
the record-climb intersection fix, the `keepForFind` deletion, the dead-click
guard in `computerOp`, the aria-hidden advice — and `mcp_server.py` had been
reported STALE by `sw_info` for hours, so the subagents would have driven an
old server.

Verified before the runs rather than assumed, both halves:

```
sw 5dsnvt, ageSec 23          -> extension freshly reloaded
bridge_ms_total 16.7          -> the stdio server respawned, not just re-handshook
server_code_changed_since_start: absent -> the server IS the code on disk
```

`bridge_ms_total` resetting is the load-bearing one: a `/mcp` that re-handshakes
without restarting the process leaves it non-zero, which is exactly how eval 8's
runner fix was found not to be live.

## AMENDMENT 5 — the two-hop requirement, and how a shortcut is handled

Written while wave 1 was still running, before any pair was scored.

Both arms on T5 reported reaching the answer by constructing the deep URL from
prior knowledge rather than navigating from the start page:

- `T5:cic` — *"I guessed the paragraph URL directly (after loading the start
  page) instead of clicking through the site."*
- `T5:cb` — *"I went straight to the /bgb/__195.html URL inside one
  browser_batch … instead of starting at the site root."*

Both then READ the answer off a real page, so neither answered from memory —
the brief's rule held. But a task solved that way measures URL recall, not
navigation, and this eval exists to compare how two representations let an
agent find things on a page.

**Rule, fixed now rather than at closeout: a pair in which EITHER agent reports
bypassing the navigation is marked SHORTCUT and excluded from H1.** It is not
scored for either side. A 1-call "win" earned by remembering a URL is not a
property of a DOM representation, and including it would flatter whichever arm
happened to guess.

This is eval 3's instrument ceiling arriving early — *"when both sides solve
everything in one round trip there is nothing left for the representation to
differ about"* — and it costs n. Every exclusion is named in the closeout with
the agent's own words, and if n falls below 6 the achievable p is stated beside
the result.
