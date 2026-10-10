# Recorded flows — research findings & plan

Goal: **record a happy path once, replay it deterministically as a frontend
regression test, and let the agent back in only where a decision actually
needs one** — including letting it propose repairs to the flow when the
frontend has moved underneath it.

The motivating number is #38's: a model turn is ~3.6s and **92–97% of a tool
call's wall clock**. Driving a 12-step signup flow through the agent loop costs
minutes and a turn of context per step. That is the right price to pay the
first time, when nobody knows what the flow is. It is the wrong price to pay on
every commit, when the flow is already known and the only question is whether
it still works.

So the shape is: **the agent is the compiler, not the runtime.**

---

## PART 1 — What the field converged on

Five independent products and one paper arrived at the same three-stage shape:
record → replay without inference → escalate to the model only on failure.
They disagree on exactly two things, and those two disagreements are the whole
design space.

| | locator stored | replay | on failure | writes repairs back |
|---|---|---|---|---|
| **Stagehand** (Browserbase) | an `Action` from `observe()` | `act(Action)` — no inference, no snapshot, no DOM-settle wait | `selfHeal` re-infers **once** | no |
| **workflow-use** (browser-use) | recorded DOM step | deterministic workflow + variables | hands the step to the Browser Use agent | roadmap only |
| **Midscene.js** | **XPath**, keyed on the locate prompt | validates the XPath still resolves, then uses it | falls back to the model | no |
| **Chrome DevTools Recorder** | multi-selector step (CSS / ARIA / text / XPath) | `@puppeteer/replay` | nothing — it fails | no |
| **Momentic** | **nothing** — re-locates every run | step cache replays resolutions | model re-locates | n/a |
| **ReUseIt** (IUI '26) | n/a (Playwright under an LLM) | guarded steps | retry ≤3 with fallbacks, then ask the user | **yes — user guidance is parsed back into the workflow** |

### The four findings worth stealing

**1. A replayed step must still be checked.** Stagehand practitioners' warning
is the sharp one: a self-heal can quietly bind to the *wrong* control, and the
step then reports success. That is #10/#11/#12 exactly — an action landing
somewhere other than the target while the tool says it worked — which this
project already treats as its most serious bug class. The mitigation is the
same one it reached independently: **flag re-inferred steps, and always require
the original postcondition to pass.**

**2. Assertions must never be cached or healed.** Midscene caches planning and
location, and deliberately never caches `aiAssert` / `aiQuery` / `aiBoolean`.
That is the difference between a test suite and a liar: if the check is allowed
to adapt to what it finds, it cannot fail. Compare #15 — *"a probe that never
fires looks identical to all settled"* — and #43, which deleted `readyState`
as a readiness trigger for firing on six settled pages and never once being the
useful catch.

**3. Self-healing is the hard part and everyone says so.** workflow-use's own
README calls its LLM fallback *"currently really bad"* and lists self-healing
as unchecked roadmap. That is an honest signal from the closest open-source
implementation, and it is the reason this plan makes healing **propose a patch
rather than apply one**.

**4. Guards are generated from the runs, not written by hand.** ReUseIt is the
only one with numbers: **24.2% → 70.1%** success across fifteen tasks. Its
mechanism is two kinds of *execution guard* — **condition checks** (pre/post,
"before/after doing X, ensure Y") and **fallback actions** (recovery steps) —
synthesised by reading **failed** runs for the checks and **successful** runs
for the fallbacks. At runtime: check → on failure retry ≤3 with fallbacks →
re-check → otherwise tell the user *where* it failed, *why*, and what to do,
and parse their answer back into the workflow.

Its limitations are as instructive as its result: the LLM judge agreed with a
human at only **κ = 0.528** (moderate), synthesis took **15–52 minutes per task
family**, variance was huge (one task 50% ± 41.6%), and it was tested on one
model with nine users. A judge that is only moderately reliable is not allowed
to silently rewrite a test.

---

## PART 2 — What ChromeBridge already has

Most of this feature is built. It has never been joined up.

**1. The script format already exists.** `browser_batch(actions=[{name, input}])`
is a list of typed tool calls executed sequentially in one round trip, with a
pre-flight that refuses the whole batch if any step is malformed (#32). A
recorded flow *is* an actions array. Replay *is* that runner. Nothing new to
invent at the transport layer.

**2. Durable identity is already computed, and this is the real advantage.**
Every other tool stores a DOM path — Midscene an XPath, Recorder a CSS/ARIA
tuple — and a path breaks on the re-render that fix #5 exists to survive. The
collector already emits, per element:

```
tag, type, role, section, label, name, near, underHeading,
placeholder, value, text, required, disabled, unselected, …
```

and since #28 **existence is decided only by what the document declares** — no
class names, no font names, no framework names, no pixel sizes. So a recorded
target can be a *descriptor made of declarations* rather than a path through
the DOM. `button[role=combobox] name="Select a model" under="Playground"` keeps
meaning the same thing after a refactor that renames every class and reorders
every wrapper. An XPath does not.

**3. Staleness detection already exists.** `page_fingerprint`, Layer 1's
`_plans_against_page` / `_terminates` and Layer 2's element-count comparison
(#38, #48), plus the readiness banner's five structural signals (#15).

**4. Assertion primitives already exist and are cheap.** `query_elements`
reports a `total` that is **never capped** — the only way to ask "how many
rows" — and `search_page` greps rendered text for a few hundred characters
where `get_page_text` costs tens of thousands (#32). A postcondition should
cost ~24ms of bridge time, not a full read.

**5. A headless Chrome + real extension + real bridge harness now exists.**
`chromebridge-site/tools/shoot_panel.py` launches Chrome with the unpacked
extension under Playwright, starts a real `ExtensionBridge` on a port outside
the default span, and gets a genuine handshake. That is 90% of a CI runner and
it is already written and working.

**6. The permission gate scopes a run.** A flow can only touch origins the user
granted. No other runner has that property.

---

## PART 3 — The one idea that is ours

Everyone else records **a human**. Chrome's Recorder watches clicks. Midscene
watches prompts. A human demonstration tells you *what was done* and nothing
about *what should then be true*, which is why every one of these tools makes
you write assertions by hand or does without them.

**We record an agent — and an agent narrates its own postconditions for free.**

When Claude clicks Submit and then calls `read_page`, or `search_page("Thanks
for signing up")`, or `query_elements("tr", …)`, that observation **is** the
expected state. The exploratory calls that look like noise in a recording are
the assertion material. ReUseIt spends 15–52 minutes per task family
synthesising guards by re-running variations; we get a first draft of the same
thing out of a single honest run, because the agent already had to check its
work to proceed.

So recording is not transcription. It is a **compile** step:

```
raw tool calls  ──►  drop observations that changed nothing
                ──►  keep state-changing steps
                ──►  promote the observations that FOLLOWED them into postconditions
                ──►  rewrite every ref into a declared descriptor
                ──►  flow file
```

And the inverse of #45's lesson applies: the agent's failed attempts in the
recording are exactly ReUseIt's "failed runs", i.e. where the condition checks
should go.

---

## PART 4 — The flow file

JSON, because it is what `browser_batch` already takes, it diffs cleanly in
review, and a machine writes it. One step:

```jsonc
{
  "step": 4,
  "name": "form_input",
  "input": { "value": "Draft a changelog entry" },

  // Replaces the ref. mmids are per-document (#1), so storing the NUMBER
  // stores nothing. Every field here is a declaration the page makes.
  "target": {
    "tag": "textarea", "role": "textbox",
    "name": null, "placeholder": "Write a tagline for an ice cream shop",
    "section": "main", "under": "Playground",
    "nth": 0, "of": 1
  },

  // Derived from what the agent observed NEXT during recording.
  // Evaluated live on every run. Never cached, never healed.
  "expect": {
    "url": "unchanged",
    "query": { "selector": "textarea", "total": 1 },
    "search": "Draft a changelog entry"
  },

  "on_fail": "heal"          // "fail" | "heal" | "ask"
}
```

Plus a header carrying the origin (so the gate's answer is predictable), the
viewport it was recorded at, variables extracted from typed values, and the
commit the recording was made against.

---

## PART 5 — Resolution: the load-bearing rule

> Match the descriptor against the **current** listing and require **exactly
> one** match. Zero is a failure. **Two or more is a failure, never
> first-match.**

This is both the research's rule and already this codebase's idiom: #24's
submit picker answers only from what the document declares, uses it when
exactly one candidate exists, and **refuses while naming the candidates** when
zero or several do — precisely so it never chooses between Save and Delete
account. #25 then validated that on 12 real forms: 7 resolve, **0 wrong
resolutions**.

Scoring uses declared signals only. No class substrings (#29 deleted those), no
XPath, no pixel geometry (#26 made it opt-in and WorkArena measured coordinates
*hurting* on dense pages). `find`'s scorer is the wrong tool here and #20 says
why: given a human's goal it finds the target **0%** of the time. A descriptor
is not a goal, so this is exact matching over declared fields, not ranking.

---

## PART 6 — The three escalation levels

This is the "hook to evoke himself for a decision" part, made concrete.

| `on_fail` | resolution fails | postcondition fails | writes back |
|---|---|---|---|
| **`fail`** | FAIL the flow | FAIL the flow | never |
| **`heal`** | one model call: hand it the current listing + the descriptor, take a ref back, act, **then run the original postcondition unchanged** | FAIL — a failed check is a *result*, not a thing to heal | emits a **patch proposal**, never an in-place edit |
| **`ask`** | stop and ask the agent, with the listing | stop and ask | as above |

Three rules that are not negotiable:

1. **A heal must pass the ORIGINAL postcondition.** If healing could also
   relax the check, the flow can pass while the app is broken. This is the one
   failure mode that makes the whole feature worse than nothing.
2. **A healed step is MARKED in the run report**, so a green run that required
   three heals does not read like a green run that required none.
3. **Healing proposes; a human disposes.** ReUseIt's judge is κ=0.528 and
   workflow-use calls its fallback "really bad". A proposed patch is also the
   more useful artefact: the diff *is* the report that the frontend changed.
   `--accept-heals` exists for people who want the other trade, and it is off.

`ask` is the deliberate decision point — "is this the right screen", "which of
these three rows is the one I created" — recorded as a step by the agent when
it knows a judgement is involved. It costs a turn, and it should: it is the
only place the flow spends one on purpose.

---

## PART 7 — Running them

Two runners, same flow files:

- **In-session**, over MCP, for authoring and iteration. One new tool pair:
  `record_flow(action=…)` and `run_flow(path, mode=…)`.
- **Headless**, `tools/run_flows.py`, launching its own Chrome with the
  unpacked extension and its own `ExtensionBridge` on a port outside the
  8765–8774 span — the `shoot_panel.py` pattern, which is proven. Fits the
  existing `run_tests.py` idiom (`--list` is truth, `--strict` for CI).

---

## PART 8 — What to measure before believing any of it

The project's own standard (#16: a result that flatters or damns the system
should be re-derived before it is believed; #25: an ablation measures the code
against the sample, it cannot measure the sample).

1. **The actual claim**: replay wall-clock vs agent-driven wall-clock for the
   same flow. Expect the win to be large and to come from turns, not from the
   bridge (#38: the bridge is ~4% of a tool call).
2. **The falsifier, and this is the one that matters**: deliberately break the
   frontend — rename a button, delete a field, invert a redirect — and confirm
   the flow **FAILS**. A suite that cannot fail is worth less than no suite,
   because it also asserts that nothing is wrong (#39's drift-check defect, in
   a tool written to prevent exactly that).
3. **Heal precision**: of N heals, how many bound to the control a human would
   have picked. Needs labelled ground truth; without it "self-healing" is a
   vendor claim.
4. **Drift**: replay an unchanged flow against an unchanged app twice. The
   patch proposal must be empty both times.

---

## PART 9 — What will go wrong

- **Silent wrong-binding on heal** — the #10/#11/#12 family. Mitigated by the
  postcondition rule and by marking healed steps, not by hoping.
- **Postconditions too weak to fail.** `url: unchanged` passes on a page that
  rendered an error. Measurement #2 is the only defence.
- **Incidental state recorded as expected state** — timestamps, generated ids,
  row counts that grow. Needs variable extraction, and the first version should
  *refuse* to assert on anything that differed between two recordings rather
  than guess which half was incidental.
- **The batch guard firing on a change the batch itself caused** — #48, still
  open, datalist case. A fill-then-submit flow is the commonest flow there is
  and it hits this today.
- **A blocking `alert()` is indistinguishable from a dead extension** (#48).
  A flow that trips one hangs for the full timeout.
- **Recording captures the agent's fumbling.** The compile step has to drop
  dead ends without dropping the observation that proved a step worked.
