# Eval 13 — result: INCOMPLETE. One arm measured, one arm null.

**There is no comparison in this eval and none is claimed** — one arm never
ran. Reporting it as a
win would be dishonest in the most obvious way available.

| arm | pass 1 | pass 2 | correct | |
|---|---|---|---|---|
| ChromeBridge | 9 calls | 5 calls | **yes** (`REF-3381`, Wayne Ent) | |
| Claude-in-Chrome | **NULL** | **NULL** | n/a | extension never answered |

## The pre-registered prediction FAILED, and that is the finding

`PREREG.md` M1 said: *"the arm with replay should make pass 2 cheaper than pass
1. If it does not, that is the finding and it gets reported as the headline,
not buried."*

**It did not.** The agent recorded a flow and then could not replay it. The
recorder correctly refuses to write a password into a file whose purpose is to
be committed, and names an environment variable instead — and the agent has no
shell, so `run_flow` refused twice and the four calls spent on it were wasted.
It finished the task by driving it again ref-free in a single `browser_batch`.

So on this task **the record/replay capability cost 4 calls and returned
nothing.** The mechanism is sound and the redaction is right; what was missing
was that nothing told the reader the value can be supplied through the project's
own gitignored `.env`, which the server already loads. Verified directly, fixed
in the refusal message, pinned by `FS8` (which fails against the old wording).

## ...AND THE CAPABILITY ITSELF WORKS, measured after the fix

The prediction failed **for the agent**, and that is a real usability result.
It is not the whole truth about the feature, and reporting only half would be
the mirror of reporting only the flattering half.

Re-run with the secret supplied the way the corrected message describes
(`run_flows` derives it for a fixture flow, so this needed no reconnect):

    PASS  acme-top-invoice   7/7 step(s) in 0.56s

**Seven steps, four of them asserted, 0.56 seconds, zero model calls.** Against
a pass-1 cost of 9 tool calls — roughly 7 model turns, and #38 prices a model
turn at ~3.6s and 92-97% of a tool call's wall clock. So the replay is one tool
call where the first run was nine, and the difference between that and what the
agent experienced was entirely that it could not discover how to supply the
secret.

Both numbers are the result: **the capability delivers what it claims, and it
was undiscoverable from inside a session until the refusal message was fixed.**

## Arm B was a NULL RUN, verified independently

8 calls, every one a timeout, 0 productive. Not a slow arm — no arm.

I reproduced it myself rather than taking the report: `tabs_context_mcp`
with `createIfEmpty:false` — which creates nothing and touches no page — timed
out for me too.

**The decisive control, taken in the same browser at the same moment:**
ChromeBridge's `sw_info` answered in **7.6 ms with `recent_timeouts: []`**. So
Chrome was awake, the machine was fine, the app was fine, and consent was not
involved (ChromeBridge refusals are fast explicit messages, never timeouts).
What was wedged was the other extension's service worker, which nothing on this
side can evict while a connection holds it.

**This is n=1 and it is NOT offered as a reliability claim.** One extension was
unresponsive on one evening. It is recorded because the control makes the cause
unambiguous, and because it is the reason this eval has no comparison in it.

## What the run did yield

1. The prediction failure above, and the fix that came out of it.
2. **`NO EFFECT` reproduced on a FORM-SUBMIT navigation** (POST to `/logout`),
   where `_navSeq` did not fire — a sharper lead than `OPEN.md` had.
3. **A seventh independent sighting** of the readiness banner firing on reads
   that were settled: *"I ignored it each time and was right to."*
4. Two messages in the OTHER toolset that name unreachable recoveries — its
   timeout advises `get_page_text`, which needs a `tabId`, which only the timing-
   out tool yields. That is CLAUDE.md #51's defect, in the other product.
5. `inUse: true` from `list_connected_browsers` reads as a working channel and
   reflects registration only — the one signal pointing optimistically the wrong
   way, and what made the first four timeouts hard to attribute.

## To re-run

Reload the Claude-in-Chrome extension at `chrome://extensions`, then dispatch
both arms again, serially, ChromeBridge first. The ChromeBridge arm should also
be re-run with `CB_SECRET_ACME_TOP_INVOICE_PASSWORD` set in `.env`, which is the
configuration the fixed message now describes and the one that actually tests
whether replay is cheaper.
