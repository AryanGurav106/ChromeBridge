# Flow record/replay — conceptual fragility review

**Brief:** find where "conceptually would never break" is not true. Adversarial,
not reassuring. Ranked by (likelihood on a real business app) × (false PASS vs
false FAIL). A false PASS is far worse than a false FAIL.

**Method:** read `FLOW_RECORDER_PLAN.md`, `core/flows/*`, the 28 files in
`flows/`, and `tools/test_flows.py` (229 checks, all green at the start of this
review). Then probe. Eleven cases were **demonstrated** by driving the real
`core/flows/runner.py` — in several cases against the real recorded flow files —
with a fake bridge returning the result-string shapes the real tools return. One
was measured on the frozen corpus with a new mutation arm added to
`tools/audit_flow_resolve.py`'s model. No source file was modified; every probe
is under
`/private/tmp/claude-501/-Users-aryangurav-Desktop-ChromeBridge/b86bef56-47ca-4359-99a5-97b83519d3e0/scratchpad/probes/`.

**Already taken, not re-reported:** the `unscoped:` rule's own motivating case
(`SELF-AUDIT-2026-11-16.md` §4), unwitnessed ordinals under a *re-sort*,
data-dependent accessible names, localised render, viewport width, the
fixture-reset requirement, unrecordable coordinates, `hollow` / `unproven`,
`settle_ms`. §2 below attacks the `unscoped:` rule itself.

---

## 0. The ranking

| # | finding | demonstrated | direction | likelihood | severity |
|---|---|---|---|---|---|
| **1** | the dead-click guard can never fire on any op a flow uses | **yes** | **false PASS** | certain — true of all 28 flows today | high |
| **2** | an assertion need only be true for an *instant*, at machine speed | **yes** ×4 | **false PASS** | high on any SPA | high |
| **3** | `search` presence is page-wide `min:1`; the error message satisfies it | **yes**, on a real flow | **false PASS** | high | high |
| **4** | list churn silently redirects an ordinal — **not in the mutation set** | **yes**, 100% WRONG / 0% refused on 132 corpus targets | **false PASS** | high on any recency list | high |
| **5** | a multi-element `query` asserts cardinality and nothing else | **yes**, on a real flow | **false PASS** | certain — 34 of 66 query checks | medium |
| **6** | a resume binding is accepted unvalidated, including off-page and destructive refs | **yes** | **false PASS** + writes a bad patch | low | maximal |
| **7** | `require` has no way to say *who* or *which tenant/page* | **yes** | **false PASS** | medium-high | maximal |
| **8** | `fill_form(submit=true)` with no `submit_ref` describes nothing | measured: 9 of 15 | **false PASS** | medium | high |
| **9** | the `unscoped:` rule fires on 62% of real targets, and goes silent on a page-wide search | **yes** ×3 | noise + **missed catch** | certain | medium |
| **10** | observations are attributed by time, never by tab | **yes** | false FAIL (mostly) | low | low |
| **11** | chosen numbers that decide pass/fail | listed | both | — | medium |
| **12** | the tool's own words — the only stated cause — are cut at 400 chars, unmarked | listed | diagnosis | certain | low |

---

## 1. FALSE PASSES

### F1 — the dead-click guard can never fire on any op a flow uses

**DEMONSTRATED.** `probes/falsepass.py` CASE 1.

`runner.go()` stops a step that "reported NO DETECTABLE EFFECT" when the step
asserts nothing or every check is `unevidenced:`. That is the only thing
standing between an unguarded step and a silent pass. It keys on
`recorder.NO_EFFECT = "NO EFFECT: "`.

Measured:

```
grep -c 'NO EFFECT' extension/background.js   ->  one emission site, line 14646
                                                  inside  case "click":
mcp_server.py ops actually requested          ->  computer, fill_field, fill_form,
                                                  navigate, …  — 'click' is NOT
                                                  among them
extract("computerOp", background.js)          ->  "NO EFFECT" in it: False
```

`computerOp`'s click path returns
`` `${action} on ${sel} — landed at (x,y)…` + _dead + _hitEcho + _actNote + … ``
and performs **no before/after comparison at all**. The only thing it can
report is `*** NOT DELIVERED` (#56's dead input *channel*), which is a different
fact. The effect comparison lives in the untrusted `click` op, which no MCP tool
reaches.

Across `flows/*.flow.json`: 47 `computer` steps, 39 of them `left_click`, **zero
steps route to the `click` op**. Feeding the runner the *real* result shape:

```
no_effect(<real computerOp click result>) = False
no_effect(<FR18's hand-written fixture>)  = True
replay of an UNASSERTED click, real shape -> PASSED
```

**Population:** 11 of 110 recorded steps are a `computer` click that is either
unasserted or marked `unevidenced:` — i.e. exactly what this guard exists for —
spread across 11 different flows, including `acme-create-project#2`,
`txt-pg-validation#2` and `ev-todomvc-react#1`.

**Why the suite is green:** FR18's fixture *hand-writes* the token as the
`computer` tool's return, and FD19e pins that the token is **present in
`background.js`** — which it is, in a function the consumer cannot reach. This is
#30's class (a string contract pinned against a file whose emitting path the
reader never reaches) inside a check written to prevent #30's class, and #19's
class (a stub that shares your assumptions) inside a suite whose header quotes
#19.

**What a fix has to decide:** whether the effect comparison belongs in
`computerOp` (it has `fpBefore`/`fpAfter` machinery available in the sibling op),
or whether the runner should take its own fingerprint around an unasserted step.
The cheap mechanical half is a contract check that the token is reachable from an
op `mcp_server` actually calls — `FD19e` as written cannot distinguish "present"
from "reachable".

---

### F2 — an assertion need only be true for one *instant*, at machine speed

Four demonstrations, one root cause. `_await_checks` loops
`bad = await self._verify(exp); if not bad … return bad` — it returns **the first
moment every check holds** and never re-asserts. The recorder captured a state
the agent observed *after it had settled*, seconds later. Those are different
predicates and the replay asserts the weaker one.

**F2a — optimistic UI rollback.** `probes/falsepass.py` CASE 2. Recorded
`tbody tr == 4` after a delete. Live: the row is removed optimistically, the
server rejects, the row returns. The bridge answers 4 on the first `query` and 5
thereafter → **PASSED**. Every SPA that does optimistic updates has this shape.

**F2b — the postcondition is answered by the page being LEFT.**
`probes/falsepass2.py` CASE 7. `browser_batch` waits on Chrome's own navigation
announcement before a chained step (#51). The flow runner does not:

```python
async def _flow_call(tool, inp):
    fn = _BATCHABLE.get(tool)
    return await fn(**inp)      # no await_navigation, no fingerprint, no settle
```

So a check issued right after a navigating click races the commit. Bridge: the
OLD page has the recorded 5 rows, the new page has none → **PASSED**, asserted
against the document being replaced.

**F2c — an absence check is evaluated at t=0.** `probes/falsepass.py` CASE 6.
The settle window makes a *presence* check stronger and an *absence* check
weaker: it is satisfied at the earliest, least-settled instant. `[role=dialog]`
is 0 at t=0 and 1 from then on → **PASSED**. The recorder's own comment states
this asymmetry; the mitigation (add the url as a co-assertion) only applies when
*every* check on the step is an absence, and a url is true immediately too.

**F2d — the replay runs ~100× faster than the recording, so time-boxed UI from
the previous step satisfies this step.** `probes/falsepass3.py` CASE 11. The
recording has a model turn between steps (~3.6s, #38); the replay has a bridge
hop (~25ms). Toasts, "Copied!" flashes, spinners and highlights live 3–5s. Step
0 clicks Save and asserts `.toast == 1`; step 1 clicks a broken "Add row" and
asserts `.toast == 1`; at record time those were two different toasts seconds
apart, at replay it is one toast that never left → **PASSED 2/2**.

**What a fix has to decide:** whether a postcondition means "became true" or
"is stably true". Stability needs a second evaluation after a quiet period,
which is a *second* chosen duration — and the project removes those. The
decidable half: the `page_readiness`/`await_quiet` ops already exist and are
already called by `browser_batch`; `_flow_call` using them would close F2b
outright and narrow F2a and F2d without inventing a number.

---

### F3 — `search` presence is page-wide `min:1`, and the error message satisfies it

**DEMONSTRATED on a real recorded flow.** `probes/falsepass.py` CASE 3.

`flows/crm-add-record.flow.json` was recorded against a live staging app. Its
final step's **only** assertion is:

```json
"expect": { "search": { "pattern": "{{investor_name}}", "min": 1, "observed": 1 } }
```

Replay where the Add silently fails and the app renders
`Could not add ZZ Flow Watch Two: an investor with that name already exists`:
**PASSED, 5/5 steps.** The record was not created.

The recorder's reasoning for `min: 1` over an exact tally is sound ("a toast
saying Created X legitimately turns 1 hit into 2"). The consequence is that the
assertion asks *does this string appear anywhere on this page*, and a failure
notice naming the thing that failed answers yes. So does a validation message, a
"recently viewed" list, a still-open modal's heading, an autocomplete echo, and a
breadcrumb.

**Scale:** all 37 search checks in the corpus are presence checks (`min: 1`);
none is an absence.

**What a fix has to decide:** a text search cannot be scoped by the recorder
without guessing. What *is* decidable: `search_page` already takes `css_scope`,
and the recorder already preserves it when the agent passed one (#63 R2-D3). A
search check with **no** `css_scope` is page-wide *by construction* — that is a
structural fact, not a judgement — and could be reported as such. See §2, where
the same fact would also repair the `unscoped:` rule's substring test.

---

### F4 — list **churn** silently redirects an ordinal, and it is not in the mutation set

**MEASURED on the frozen corpus.** `probes/audit_churn.py`, 20 scored sites,
built on pass A, resolved against a mutated pass B, same model and same ground
truth as `tools/audit_flow_resolve.py`.

The shipped set has eight mutations. Every one changes the crowd's
**composition** (rename / counter / delete / insert-twin / twin-elsewhere) or its
**order** (reorder / resort), or changes something outside it (rename-neighbour).
`churn` changes neither: a recency-ordered list gains one record at the top and
drops its oldest. `of` is unchanged, the surviving members are in the same
relative order, and every one of them has shifted down by one index.

| churn | n | correct | refused | **WRONG** |
|---|---|---|---|---|
| all | 237 | 43.5% | 0.8% | **55.7%** |
| witnessed | 105 | 98.1% | 1.9% | 0.0% |
| **UNWITNESSED** | **132** | 0.0% | **0.0%** | **100.0%** |

Per-site WRONG: craigslist 100%, gov_uk 100%, wikipedia_ar 100%, webdev 100%,
mui_datepicker 82%, ng_material 77%, mdn_select 71%, gh_issues 75%.

**Why this is not the documented residue.** The documented residue is
"unwitnessed ordinals break under a **re-sort**", and `Recorder.before` tells the
recording agent, in these words: *"If that list is ever **re-sorted** the step
will act on a different one."* A re-sort needs somebody to click a column header
or an app to change its default. **Churn needs nobody to do anything** — an
Inbox, a Recent activity feed, a Notifications list, a Latest invoices table and
an audit log all churn between any two CI runs, with no user and no deploy. An
agent reading that warning and reasoning "this list is never re-sorted, so this
step is fine" reaches the wrong conclusion. The `resort` arm's unwitnessed half
is 94.2% WRONG, so the *number* is not new; the **trigger** is, and it is the one
that fires by itself.

Composed with F5 (a list assertion is a count), churn is a complete false PASS:
the step dismisses/deletes/edits the wrong record and "one fewer row" still holds.

**The strongest form of this finding is the arm itself.** `mut_churn` is written
and runs against the existing harness; it reuses `mut_resort`'s own record model
verbatim, declines where the target is the oldest record, and re-stamps mmids by
position exactly as `mut_resort` does so the ruler and the address cannot agree
by accident.

**Also measured, and it is good news that should be stated:** the witness
generalises beyond the re-sort it was built for — 98.1% correct under churn, with
no new code. That is a stronger result than §72 claims for it.

**What a fix has to decide:** nothing in the resolver. The decidable change is
the *wording* of the record-time warning (the ordinal breaks when the list's
**contents move**, not when it is re-sorted) and adding the arm so the number is
reported against a mutation that happens unattended.

---

### F5 — a multi-element `query` asserts cardinality and nothing else

**DEMONSTRATED on a real recorded flow.** `probes/falsepass2.py` CASE 4.

`_checks` records `text`/`attrs` **only when the query matched exactly one
element** ("across several the text belongs to no particular one"). Replaying
`flows/acme-create-project.flow.json` against a bridge that returns the recorded
row counts with every cell reading `"undefined undefined undefined"`:
**PASSED 4/4.**

34 of the corpus's 66 query checks match more than one element and carry no
content at all. The one place content *is* captured (a single match) is where it
matters least.

**What a fix has to decide:** what to record for N>1 — the first element's text
is a real choice (`max_results: 1` is already what the runner asks for), a joined
digest is another, and both are weaker than they look if the list re-orders. This
is a trade, not a bug; it is listed because the corpus-wide consequence — *no
flow in this repo checks the contents of any list* — is not stated anywhere.

---

### F6 — a resume binding is accepted unvalidated

**DEMONSTRATED.** Probe inline; reproduced twice.

A step pauses with two "Save" candidates and hands back `['ref_7 | button
name="Save"', 'ref_8 | button name="Save"']`. Then:

```
resume(run_id, "ref_4242")   # an mmid that is on no page at all
  -> PASSED, dispatched {'action': 'left_click', 'ref': 'ref_4242', 'tabId': 1}

resume(run_id, "ref_9")      # ref_9 is  button name="Delete account"
  -> PASSED, dispatched ref_9
  -> patch proposed:  was {name: "Save"}  ->  now {name: "Delete account"}
```

`_bind` strips `ref_` and uses the string. There is no check that it names an
element in `entries`, no check that it is one of the candidates the runner itself
just computed, and no check that its tag/role matches the recorded descriptor's
base. `_propose_patch` returns early when the entry is absent, so the off-page
ref is dispatched with no patch and no comment.

The `Unresolved` docstring records fixing the *path* half of this exact
hazard — a binding landing on the wrong target and the patch then rewriting
"EMAIL's descriptor to the password box, which `record_flow(action='patch')`
would then have written to disk". The *value* half is still unchecked, and the
proposed patch in the second case is precisely that artefact: apply it and the
flow's Save step becomes a Delete account step, permanently.

Rule 3 — "healing proposes; a human disposes" — is what makes escalation safe,
and this is the one place the human's answer enters.

**What a fix has to decide:** whether a binding must be *in the candidate list*
(strict, and would block a legitimate answer the runner failed to list) or merely
*present in the current entries* (weak, and would still accept Delete account).
Reporting a base mismatch — the bound element's tag/role/type differs from the
recorded descriptor's — is decidable and costs nothing, and would have flagged
both cases.

---

### F7 — `require` cannot say *who*, *which tenant*, or *which page of a list*

**DEMONSTRATED.** `probes/falsepass3.py` CASE 12. See also §3.

`EXPECT_KINDS = ("url", "path", "search", "query")`. All four describe the
*shape* of a page. A flow with `require = {path: "/org/projects", query: tbody tr
== 4}`, replayed against a **different organisation at the same path**, passes
its precondition, resolves `button name="Delete project"`, deletes, and passes
`tbody tr == 3`. **PASSED.** Every layer agreed and a project was deleted in the
wrong tenant.

3 of 28 flows carry a `require` at all, and all three describe the landing page's
shape:

```
acme-precondition  : url + search('Work email')
bench-grocery      : path + search('Оливки') + query(cart empty)
txt-pg-login-error : query(form == 1, text='Work email Password …')
```

---

### F8 — `fill_form(submit=true)` with no `submit_ref` describes nothing

**MEASURED.** `probes/falsepass2.py` CASE 8. Of 15 `fill_form` steps with
`submit: true`, **6 carry a recorded `submit_ref` descriptor and 9 do not** —
e.g. `txt-pg-detail#1`, `txt-pg-login-error#1`, `txt-pg-members#1`,
`txt-pg-modal#1`, `txt-pg-new-project#1`, `txt-pg-new-project#3`.

For those 9, **which button is pressed is decided at replay time** by the
extension's structural submit picker (#24), from the form as it is now. Nothing
about that element is recorded, so the descriptor ladder — the feature's whole
answer to "the frontend moved" — does not cover the one element in the step that
performs the irreversible action. If the form's declared submit becomes a
different button (a `type="submit"` moved onto "Delete", a modal footer
re-ordered so `<button form=…>` resolves elsewhere), the replay presses it and
reports success.

The picker's own refusal behaviour is the mitigation and it is good: zero or
several candidates → refuse and name them → `NOT DONE:` → the runner stops. The
gap is exactly the *one declared candidate that is now a different button*.

**What a fix has to decide:** whether to record a descriptor for the button the
picker chose at record time and verify the live pick against it (cheap, and it
turns a silent substitution into a refusal), or to accept that `submit: true` is
a structural re-derivation by design and say so.

---

### F9/F10 — smaller

**Observations are attributed by TIME, never by TAB** (`probes/falsepass.py`
CASE 5). `_checks` never looks at `tabId`. An agent that opens a second tab to
confirm something — a very normal move — has those observations compiled into
the previous step's postcondition and replayed against `self.cur_tab`.
Demonstrated: `get_url` on tab 9 became step 0's `url` check; the step ran in tab
5. Mostly a false FAIL.

**Semantic dead ends are kept.** `compile()` drops calls that *errored* or that
returned a refusal marker. An action the agent performed and then undid — click
Add by mistake, click Remove, do the real thing — is three kept steps. The plan
names this ("the compile step has to drop dead ends without dropping the
observation that proved a step worked") and only the error half is implemented.

---

## 2. ATTACKING THE NEW `unscoped:` RULE

Three attacks, all demonstrated: `probes/attack_unscoped.py`.

### A1 — the gate it documents is not the gate it implements

The comment says the rule is gated on the target having **needed
disambiguation**, and explains that warning on a target that resolved on its own
name "would fire on the commonest shape there is — click Submit, assert the url
changed. That is #15's always-on warning."

The implementation reads:

```python
_d = _t.get("full") or _t.get("desc") or {}
_needed = _t.get("of") is not None or bool(
    (_d.get("under") or "").strip() or (_d.get("near") or "").strip())
```

`build()` **always** stores `full = at_level(entry, FULL)` beside the cheap
descriptor, and `full` always carries `section`/`under`/`near`. So `_needed` is
reading *"does this page have a heading above this control"*, not *"did the
ladder have to reach for one"*.

Applying the rule's exact predicate to the 28 recorded flows:

| rung the descriptor was STORED at | targets with an assertion | `unscoped:` fires |
|---|---|---|
| level 1 (unique on its own name) | 69 | **42 (61%)** |
| level 2 | 4 | 2 (50%) |
| level 3+ | 1 | 1 |
| ordinal | 2 | 2 |
| **total** | **76** | **47 (62%)** |

Examples, all level 1 — i.e. unique on their own name, needing no
disambiguation at all:

```
acme-create-project#1 submit_ref  level=1  ident=['Sign in', 'Sign in']
acme-create-project#1 fields.0    level=1  ident=['Work email', 'Sign in']
acme-create-project#3 fields.0    level=1  ident=['Project name', 'New project']
```

That is the always-on warning the comment is written to avoid, at 62% of the
corpus. It is self-defeating in the specific way #15 priced: a reviewer who sees
`unscoped:` on `fill_form(Work email, Password)` learns to skip the line, and
skips it on the Добавить/Убрать step too.

**`FW10c` is vacuous and does not catch it.** Its `_uniq` fixture is
`{"name": "Place the order", "section": "main"}` with **no `under`** — so it
passes because the fixture's page has no heading, not because the gate reads the
rung. Add a heading, change nothing else:

```
FW10c's fixture (level 2, full has NO `under`)   fires: False
the same control under a heading 'Checkout'      fires: True
  -> unscoped: … none of what identifies it ('Place the order', 'Checkout') …
```

This is the eighth vacuous fixture in this project's history and the same shape
as the seven before it.

**The fix is one field name,** and it is measured:

```
gate reads `full`:  fires on 47/76 targets (62%)
gate reads `desc`:  fires on  5/76 targets ( 7%)
```

`desc` is the rung actually stored, so `under`/`near` appear in it only when the
ladder had to reach for them — which is what the comment says the gate is for.
The motivating Добавить case stores `under="Консервы"` in `desc` (it resolved at
that rung), so it still fires.

### A2 — a page-wide search containing the token silences it

The test is `any(t in json.dumps(expect) for t in _ident)` — a substring test
over the serialized `expect`. So the rule is satisfied by *any* occurrence,
including one in an assertion that scopes nothing:

```
assertion = query [aria-label='Remove'] == 1     unscoped fires: True
assertion = search_page('Canned goods') min 1    unscoped fires: False
```

The second is **strictly weaker** than the first. `Canned goods` is the section
heading — a fact about the page, true before the step ran, and true if the click
landed on any of the three neighbours. It contains the identity token, so the
rule goes quiet on the weaker assertion and fires on the stronger one.

This is reachable by ordinary recording: `_checks` compiles any `search_page` the
agent happened to run, and an agent orienting itself on a category page searches
for the category.

**What a fix has to decide:** "does this assertion scope to the record" is not
answerable by substring. One structural half *is* decidable and needs no
judgement: a `search` check with no `css_scope` is page-wide **by construction**,
so it cannot scope anything and should not count as satisfying the rule. A
`query` whose selector contains the token is a real scope; a `search` pattern
that merely contains it is not.

### A3 — short identities are dropped

`_ident = [t for t in _ident if len(t) >= 2]` and then `if not _ident: continue`.
A target whose only identity is a one-character name — common in CJK UI (买,
删, 検) — produces an empty `_ident` and the rule is silent. Minor, and in the
safe direction only by accident.

---

## 3. STATE AND ORDER — where `require` breaks

`require` is the only start-state guard and it is **derived**: it is whatever the
agent happened to observe between the landing navigation and the first action.
3 of 28 flows have one.

**a. Identity is outside the language.** F7. No check kind can express user,
role, tenant, feature flags or locale. On a business app that is most of what
"start state" means. A flow recorded as an admin in org A and replayed as an
admin in org B passes every layer and acts on the wrong data.

**b. A sticky server-side view defeats it, and that is where it meets F4.**
`require.path` is `pathname + search`, and `url`/`path` cannot see a cookie, a
`localStorage` preference or a server-side "last view" that decides *which page
of a list* and *in what order* the app renders. An app that remembers "page 3,
sorted by date desc" serves a completely different crowd at an identical path.
`require` passes; an ordinal-bearing step then binds into a crowd it has never
seen, which §F4 measures at 100% WRONG with 0% refusals when unwitnessed. The
precondition and the descriptor each assume the other covers this.

**c. It is checked once and latches.** `probes/falsepass3.py` CASE 13.
`_require_at` is the index of the first non-`NAVIGATIONAL` step and
`checked_require` is a one-shot. A flow `navigate → click → navigate → confirm`
has `_require_at == 1`: steps 2 and 3 get no precondition for the state they land
in. The recorder cannot produce one either — `_require_before` scans only the
leading prefix. Mid-flow navigation into a second app area, an SSO hop, or a
click that navigates are all unguarded.

**d. An exact `count` in `require` is a concurrency race.** The same `grew`
reasoning the runner applies to postconditions applies here and is not said:
another user adding a row fails the precondition before anything has run. That is
the safe direction, and it makes the suite flaky, which is the failure mode that
destroys trust in a regression suite.

**e. Time-dependent data.** `require.query(count=N)` over "today's" rows, or a
`search` for a date, changes at midnight with nobody touching the app. Neither
the recorder nor the runner has any notion of volatility; the plan's PART 9 names
this ("timestamps, generated ids, row counts that grow … the first version should
*refuse* to assert on anything that differed between two recordings") and only
values the **flow itself typed** are parameterised. Anything the **server**
generated — an id, a slug, a timestamp — is baked in as a literal.

**f. Caching.** A replay served a cached document satisfies `path`, `search` and
`query` and is stale. Nothing in the four check kinds can see freshness.

---

## 4. THE MUTATION SET

Covered in §F4. The arm is `mut_churn` in
`probes/audit_churn.py`, written against the existing harness so it can be lifted
into `tools/audit_flow_resolve.py` as-is. Two further arms were run and are
reported here because their results are worth having even though neither is a
defect:

| arm | n | correct | refused | WRONG |
|---|---|---|---|---|
| `churn` | 237 | 43.5% | 0.8% | **55.7%** |
| `disable-target` | 2088 | **100.0%** | 0.0% | 0.0% |
| `retag-target` | 232 | 0.0% | **100.0%** | 0.0% |

**`disable-target`** — the control is still there, still named, and is now
`disabled`. Resolution is unaffected (state flags are excluded from identity by
design, for a stated and correct reason). So a step whose target has become
disabled resolves, clicks, and does nothing, and the *only* things that can catch
it are the postcondition and `*** NOT DELIVERED` — the latter only for a *native*
disabled control, which does not dispatch events. A custom disabled control
(`aria-disabled` div, `pointer-events:none` wrapper whose child still receives)
delivers the events, returns a plain "Clicked", and composes with F1 into a
silent pass. Worth stating in the docs rather than fixing.

**`retag-target`** — `<button name=X>` becomes `<a role=button name=X>`, the
commonest single change in a design-system migration. 100% refused, 0% wrong:
the safe direction, and every step in the flow fails at once. The gap is the
*message*: a language change and a viewport change both append a named cause
(`_lang_note`, `_viewport_note`), and this one says only "no element on the page
matches this step's target: tag='button' … name='Save'" while an `<a>` with that
exact name is on the page. Re-matching on name alone when zero match, and saying
"an element with this name exists but is an `<a>`, not a `<button>`", is
decidable from data already in hand.

---

## 5. CHOSEN NUMBERS

| site | literal | what it decides |
|---|---|---|
| `runner.py:781` | `SETTLE_MS = 6000` | **how long any check or target may take to become true** |
| `runner.py:782` | `POLL_MS = 400` | re-ask interval |
| `descriptor.py:165` | `WITNESS_K = 3` | how many preceding controls anchor a witness |
| `descriptor.py:586` | `hits[:12]` | candidates shown on a refusal |
| `runner.py:419, 456, 864` | `[:400]` | the tool's own words — the only stated cause |
| `recorder.py:893` | `split("\n", 6)[:6]` | head searched for `Current URL:` |
| `mcp_server.py:4450` | `[:120]` | flow filename bound |

`SETTLE_MS = 6000` is the one that decides pass/fail. `settle_ms` is measured per
step and **added** to it, so the measured part sits on a chosen floor: an app
slower than 6s on a step whose recording happened to be fast fails, and an app
faster than 6s is given 6s of slack inside which a transient can satisfy a check
(§F2). `WITNESS_K = 3` is at least chosen from a measured curve (51.7 / 58.7 /
59.3% at 1 / 2 / 3).

`[:400]` is a **silent cut on an agent-facing string**, which is the one thing
#22 removed from this codebase: `markCut` exists so that `x` and `x…(+840)`
cannot be confused. These three sites carry the entire explanation a failed
replay gives (`the tool said: …`), and a `fill_form` refusal enumerating unfilled
`(required)` fields and the page's own validation errors routinely exceeds 400
characters — so the part naming *which field* is the part dropped.

---

## 6. WHAT I CHECKED AND FOUND SOUND

- **The crowd-check ordering.** `_resolve_recorded` runs the crowd-check before
  the single-match fast path. FD8c pins it and the audit's own ablation measured
  7.9% silent mis-binds with the shortcut in place. Correct, and the comment
  explaining why is accurate.
- **The witness is better than it is claimed to be.** Built for a re-sort; under
  `churn` — a mutation it has never been tested against — it is **98.1% correct
  on 105 targets, 0% wrong**. The anchor being record-local is what makes that
  work, and that choice is documented as having been got wrong once first.
- **`retag-target` and `delete-target` fail in the safe direction**, 0% wrong.
- **Secrets.** A flow whose `${CHROMEBRIDGE_SECRET:…}` is unset refuses to run
  and names the variable. I hit this by accident mid-probe, which is the right
  way to find out it works.
- **`validate_expect` at load.** An unknown `expect` kind or a misspelt field is
  refused by name. The silent-fallthrough hazard #62 closed for `on_fail` is
  genuinely closed for `expect` too.
- **`_paramize` uses exact equality, never substring**, in both directions, and
  `_reparam` puts the placeholder back before a patch is proposed so applying one
  cannot hard-code this run's `vars`.
- **The `alt` href key re-checks uniqueness at replay**, so it can convert a
  refusal into a resolution and cannot change a step that already worked.
- **`_await_checks` is one spelling used by the precondition, the postcondition
  and target resolution.** The #21 risk is genuinely handled here.
- **A hypothesis of mine was refuted by measurement and is recorded as such.** I
  expected `near=` and `under=` to carry live data (prices, counts, dates) and so
  to be a second data-dependent matching key with no alternate and no witness —
  #55 records saucedemo resolving on `near="$29.99 Add to cart"`. Measured over
  14 frozen sites / 5,368 descriptors: **0 of 526 ordinal-bearing descriptors
  carry a `near` at all** (a tied crowd shares its surroundings by construction,
  and #37 suppresses a `near` that discriminates nothing), and of the 126
  descriptors that do store a `near`, 12 contain a digit — as do 12 of the 1,209
  storing an `under`. The data-dependent field is the **name**, at 12.6% of all
  descriptors, which is the already-known issue. The `near` theory is wrong and
  is not reported as a finding.

---

## 7. THE SHAPE OF THE RESIDUE

Three of the four highest-ranked findings are the same sentence in different
places: **the recording and the replay are not asking the same question.**

- The recorder observed a page that had **settled**, seconds after the action,
  through an agent that had already decided the step worked. The runner asks
  whether the check was true at **any instant** inside a window, at machine
  speed, with no navigation settle. (F2a–d)
- The recorder had the agent's **judgement**; it keeps a url, a hit count, a row
  count, and — only for a single match — a string. The richest observations an
  agent makes (`read_page`, `get_page_text`, `find`) contribute **nothing**.
  (F3, F5)
- The recorder knows which element the step **meant**; the assertion is evaluated
  **page-wide** against whatever document is current. (F3, F5, F9)

That is the oracle problem in its real shape here, and it is sharper than "one of
those observations might have been wrong": the *reason the agent was satisfied*
is discarded and replaced by a proxy, and the proxy is invariant under most of
the ways the app can be broken. `hollow`, `unproven` and `unscoped` all measure
properties of the **check**; none of them measures the gap between the check and
the judgement it replaced.

The honest claim the feature can make is narrower than "conceptually would never
break", and it is still a strong one: **a recorded flow cannot bind to the wrong
element without a signal, except where the ordinal is unwitnessed** — which is
measured, bounded, and reported at record time. What it cannot claim is that a
green replay means the app did the right thing.
