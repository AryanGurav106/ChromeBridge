# Where a recorded flow breaks CONCEPTUALLY

The brief was "conceptually it would never break". `docs/FLOWS-FAILURE-SURFACE.md`
is the answer to that for the shapes someone had already met. This is the pass
that went looking for the shapes nobody had: **a target inside a frame or a
shadow root, a virtualised list, a native dialog, a tab the page opened, a drag,
an upload, a session that dies mid-run, a localised render, a clock.**

Read `FLOWS.md` for what the feature is and `FLOWS-FAILURE-SURFACE.md` first —
this extends it rather than replacing it, and a mode listed there is not
repeated here.

**The only unacceptable outcome is SILENT**: the replay acts on something other
than what was recorded and reports a pass. Three of the modes below were that,
and one of them had disarmed a guard the failure surface lists as CLOSED.

| | |
|---|---|
| verdicts | `SILENT` (acted wrongly, reported a pass) · `DETECTED` (failed honestly) · `REFUSED` (declined and named candidates) · `BOUNDED` (cannot be fixed; announced) · `INHERENT` |
| new checks | 22 in `tools/test_flows.py`, each shown to FAIL against `git archive HEAD` |
| controls | 22, which pass in BOTH arms — without them "warn always" or "drop always" would satisfy the positives and delete the feature |
| suite | 297/297 green; `run_flows.py --playground --local-only` 12/12; `--check-only` 30/30 |

---

## 1. The findings, by verdict

### 1.1 Was SILENT, now closed

| # | Mode | Before | After |
|---|---|---|---|
| **C1** | A step performed in a tab the **PAGE** opened (`target="_blank"`, a payment popup, an OAuth window) | **SILENT** — recorded in tab 9, replayed in tab 7, **PASSED 3/3** having clicked a different document's button | Dropped at compile, naming both tabs and the recovery (`FT5`, `FT5b`, `FT5c`) |
| **C2** | A click the extension itself reported as **`*** NOT DELIVERED`** (#56's dead trusted-input channel) | **SILENT** — `refused()` could not see it, `dropped: 0 failed call(s)`, the step compiled in as a real action | Dropped, like every other refusal (`FD24`) |
| **C3** | A flow that compiled down to **zero steps** | **SILENT** — `passed 0/0`, a false green for ever | `FAILED`, naming why a recording compiles to nothing (`FR25`) |

### 1.2 Was quiet, now named at RECORD time

| # | Mode | Before | After |
|---|---|---|---|
| **C4** | The click that OPENS such a tab, where no `tabId` can catch it | nothing | `opens-new-tab:` review, only when the recording continued past it (`FW14`) |
| **C5** | A step whose tool reported **`NO EFFECT:`** | read only by the RUNNER | `no-effect:` review at record time, the one moment it is cheap (`FW15`) |
| **C6** | A `coordinate` or an `imageId` — inputs that are never re-resolved | nothing, while `model.py`'s comment claimed "the recorder marks it" (principle 18) | `opaque-input:` review (`FW16`) |
| **C7** | A ref into a **cross-origin iframe** | "not in the current listing" — nonsense to an agent that had just read it out of one | names the frame boundary (`FD22`) |
| **C8** | A recording whose surviving steps are **all navigations** | nothing | named (`FW17`) |

### 1.3 Was a wrong diagnosis, now a cause

| # | Mode | Before | After |
|---|---|---|---|
| **C9** | A **session that expires mid-flow** and bounces to a sign-in page | "no element on the page matches this step's target: name='Delete record'" | …plus the path the tab is actually on (`FR26`) |
| **C10** | A **consent sheet that appears only on the replay** and declares no role | nothing — `_surface_note` looked for `role=dialog` | reads the collector's own `section=dialog` verdict (`FR27`) |

### 1.4 Load-time silences

| # | Mode | Before | After |
|---|---|---|---|
| **C11** | `{"min": 0}`, `{"selector": "tr"}` alone, `{"pattern": "x"}` alone | accepted; the step reports a postcondition and has none | refused at load, naming what to write (`FO9`) |
| **C12** | `dismiss_dialog` classified as an **observation** | a happy path through a `confirm()` had its completing call folded away as scenery | it is an action (`FD23`) |
| **C13** | A tool `MUTATES` keeps that `_flow_call` cannot dispatch | nothing held the two tables together | permitted-set tripwire (`FD25`) |

### 1.5 Reviewing the review

| # | Mode | Before | After |
|---|---|---|---|
| **C14** | A check that MOVES to `require` leaves its **review line behind** on a step whose `expect` is now `{}` | the reviewer is pointed at a line that is not there — and `unproven` is *trivially* true of a precondition, so the line is meaningless in the one place it could belong | filtered by step INDEX between the move and the review loops (`FW18`) |
| **C15** | `require` is reviewed by **nothing at all** — the three loops walk `kept` | an absence in a precondition can never be witnessed, so a mistyped pattern passes for ever | named on the step it guards, and deliberately NOT dropped (`FW19`) |

### 1.6 Measured and found SOUND — no change

| # | Mode | Verdict | Evidence |
|---|---|---|---|
| **S1** | Target inside an **open shadow root** | works | live: collected, descriptor at level 1, click lands, page reacts |
| **S2** | Target inside a **closed shadow root** | works | same, with no debugger attached (#31's `attachShadow` wrap) |
| **S3** | Target inside a **same-origin iframe** | works | live: `section=iframe`, `under="Frame alpha"`, re-resolves across a reload with new frameIds |
| **S4** | A virtualised list whose rows carry **their own text** | REFUSED correctly after a scroll | live: the descriptor reached `near="REC-1003 Select"`, resolved with no ordinal, and refused once the window moved |
| **S5** | A flow replayed against a **localised** app | BOUNDED, already closed | `Flow.lang` + `_lang_note`; `FLOWS-FAILURE-SURFACE` 3.8 still says OPEN and is stale |
| **S6** | A flow that spans tabs via **`tabs_create_mcp`** | works | #58 for the runner; `FT7` is the recorder's half of the same rule |
| **S7** | **Drag and drop** | `BOUNDED` | there is nothing to describe: `coordinate` is a point. Now MARKED (C6) rather than silently literal |
| **S8** | **`file_upload(paths=…)`** | `DETECTED` | absolute machine-specific paths, recorded verbatim; replay elsewhere errors honestly. No warning added — it would fire on every upload (#15) |

### Index — every shape the brief named, and where it landed

| the brief asked about | rows |
|---|---|
| same-origin iframe · cross-origin iframe | S3 · M2 |
| shadow root, open and closed | S1, S2 |
| virtualised / infinite-scroll list | M1 (the dangerous half), S4 (the safe half) |
| native `alert`/`confirm` · focus-trapping modal · consent banner at replay | C12 + §5 · C10 · C10 |
| multi-tab / popup (`target="_blank"`) | **C1**, C4, S6 |
| drag and drop · file upload | S7/C6 · S8 |
| date/time-dependent assertions · timezone | §4.3 (`INHERENT`, and why it is not built) |
| localisation | S5 |
| auth expiry mid-flow | **C9** |
| a re-render that reuses nodes between read and act | §4.4 (#82) |
| an assertion non-deterministic by nature | §4.3, §4.5 |

---

## 2. The three that mattered, with their measurements

### C1 — a tab the page opened

`#58` taught the runner to follow a tab the FLOW creates with
`tabs_create_mcp`. A tab the PAGE creates is a different thing: it joins the
Claude group, becomes **active**, and has no name a recording can carry.

Reproduced live against `/lab/popup` (`target="_blank"`): the click produced tab
`1649395660` beside the flow's `1649395659`, and `tabs_context_mcp` reported the
new one `"active": true`.

Reproduced as a loop against a fake bridge, which is where the verdict comes
from — the popup carries the same app shell, so both tabs have a `Download`:

```
recorded   navigate(tab 7) -> click "Open report"(tab 7) -> click "Download"(tab 9)
replayed   navigate(tab 7) -> click ref_1      (tab 7) -> click ref_2 (tab 7)
result     PASSED 3/3
```

A different element, in a different document, reported as a clean pass — the
#10/#11/#12 family. Where the original tab has no match it merely pauses, so
whether it is loud or silent is a property of the page.

**Decided from the recording alone**: every call carries the `tabId` it was made
with, `tabs_create_mcp` announces the one tab it made, and a call naming any
other tab is a call the replay cannot reproduce. Dropped and named, like the two
other things a recording cannot carry. **Observations go too** — one made in the
popup becomes the previous action's postcondition, so leaving them in asserts the
other tab's state against this one (`FT5b` fails pre-fix with
`{'url': 'https://app.test/report'}` on the wrong step).

`created_tab()` moved to `model.py` so the recorder and the runner read a created
tab the same way (rule 17).

**The residue is the implicit half**, and it has its own answer. If the agent
omits `tabId` entirely, the popup is active and the call goes THERE while the
replay stays here — with no tabId in the recording to compare. Nothing inside
`core/flows` can see that. What IS declared is the CLICK: the collector already
emits `newTab` (`target="_blank"` read off the element), so `FW14` names it,
gated on the recording having continued past that step.

### C2 — the recorder could not read the result of a click

Found by the live pass, not by a fixture.

An MCP tool answers with a string **or with a list of content objects**, and
`computer` — every click, drag, scroll and keystroke — answers with the list.
`Recorder.after` stored `result if isinstance(result, str) else ""`.

```
stored result   : ''
refused(stored) : None
refused(raw)    : '*** NOT DELIVERED:'
compiled steps  : ['computer']   dropped_err: 0
```

So the record-time guard that `FLOWS-FAILURE-SURFACE` 1.1 calls CLOSED —
"a step that silently did nothing is compiled in as a real step" — **has only
ever worked for the fill family**, which returns strings. For the tool that does
the clicking it has never fired once.

**That last sentence is a claim about the whole history of a contract, so here
is how it was established rather than asserted.** Three measurements, not a
reading of `after()`:

1. The probe above, RUN against a `computer`-shaped result (a list of content
   objects) — `stored ''`, `refused() None`, step kept, `dropped_err 0`.
2. `git log -S 'result if isinstance(result, str) else ""' -- core/flows/recorder.py`
   returns **exactly one commit**: `aec922a`, the commit that created the file
   (2026-10-10). The predicate has never been edited since.
3. `git show aec922a:mcp_server.py` — `computer`'s click path ended
   `return [TextContent(type="text", text=str(res))]` **in that same commit**.

So both halves held on the day the recorder shipped, and neither moved. This is
the same rule applied to `dismiss_dialog` in §5, pointed at a claim that flatters
the finding instead of one that would have damned it.

The RUNNER saw the same markers **by accident**: it passes the live object to
`refused()`, which stringified it, and a list's repr happens to contain its
items' text. Two halves of one project reading one result two different ways,
with the blind half being the one that WRITES THE FILE.

One `result_text()` now answers "the text a tool returned" for `after()`,
`refused()` and `no_effect()` alike. **Text parts only, never the repr**:
`computer(action="screenshot")` answers with an `ImageContent` whose repr carries
the whole base64 payload, and the recorder holds every raw call for the length of
the recording (`FD24d`).

### C3 — a flow with no steps reported PASSED

Four separate rules drop a step — an errored call, a tool that said it did not
act, a ref that could not be described, a typed value addressed by selector — so
a recording where every one applied compiles to nothing, saves, and replays green
for ever. `start(Flow(steps=[]), …)` returned `passed 0/0` with an empty reason.

It is not theoretical. Recording a Delete that goes through a native `confirm()`
produced, live, **a one-step flow containing only the `navigate`**: the click
timed out behind the dialog, was dropped as an error, and the saved flow asserts
the landing path and nothing else.

Zero steps is refused outright. The shape one above it — every surviving step is
a navigation — is NAMED rather than refused, because a landing-page smoke test is
a legitimate if weak thing to want (`FW17`). **0 of the 30 flows on disk are
navigation-only**, so the note discriminates.

---

## 3. Measured, NOT fixed, with the number

### M1 — a virtualised list defeats the ordinal's own safety check

This is the sharpest open case and it is a sub-case of `OPEN.md` item 2 (the
52.6% of ordinal-bearing descriptors that cannot be witnessed), with one property
the general case does not have.

Measured live on `/lab/virtual?plain=1` — 200 records, ten rows ever in the DOM,
rows carrying nothing but the button:

```
window at top   10 rows, mmids 11,13,…,29
descriptor      level 3, nth=3, of=10        recordAtoms: None
record-time     click -> selected REC-1003
scroll to 1500  10 rows, mmids 32,34,…,50
replay resolve  -> 38        (NO REFUSAL)
replay click    -> selected REC-1053
```

**The crowd check can never fire.** In an ordinary list, adding or removing a row
changes `len(hits)` and the step refuses; in a virtualised one the window's size
is constant by construction, so composition is identical while every member is a
different record. And `recordAtoms` is `None` — the content witness #83 shipped
has nothing to work with, because the rows render no distinguishing text.

**The same page with its per-row code restored is SAFE** (`S4`): the descriptor
reaches `near="REC-1003 Select"`, needs no ordinal, and refuses after the scroll.
So this is about rows that declare nothing, not about virtualisation as such.

**Not fixable from declarations.** The scroller is not an interactive element, so
it is not in the entries; the rows report `clipContainerMmid: None`,
`clippedInContainer: False`, `scrollRegion: False` and `near: ''`. ARIA declares
exactly this with `aria-setsize`/`aria-posinset`, and #83 measured those present
on **3.8%** of controls. What changed is the warning's own text: the `positional:`
review used to name a re-sort and churn, and now names the scrolling window as a
third mechanism — the one that needs no data change and no user at all.

### M2 — a cross-origin iframe is unrecordable, and now says so

`read_page` appends cross-frame elements as `f<frameId>:<n>`; the STRUCTURED
array a recording is described from is built before that pass and never carries
them (`background.js`: `if (!params?.structured && typeof result === 'string')`).

Live, with the page on `127.0.0.1:8787` and one frame on `localhost:8787` — the
same server under a different origin:

```
FRAMES :: 3 entries
  mmid='14' tag=button sec='iframe' name='Approve alpha'   <- same-origin
  mmid='23' tag=button sec='iframe' name='Approve beta'    <- same-origin
  mmid='25' tag=iframe sec='iframe' name='gamma frame'     <- the SHELL only
  !! Approve gamma: NOT COLLECTED
```

So an agent can read a consent dialog, click it, and have the recorder answer
*"ref_f12:3 is not in the current listing"* about a ref it had just read out of
one. The step was already dropped; what was missing was the reason. The ref FORM
is declared by the extension, so naming it costs a regex (`FD22`), and `FD22b` is
the control that an ordinary missing ref keeps the plain message.

**Closing it properly is a collector change, not a flow change**: `_flow_entries`
would have to carry cross-frame entries, which means `collectCrossFrames`
returning structured rows. Out of scope here and recorded in §6.

### M4 — a recorded `imageId` uploads a DIFFERENT file, silently

`upload_image(imageId=…)` is the second opaque input (C6), and the mark says the
id "resolves in a later session to a DIFFERENT image". **That was an inference
when it was written and is now a reproduction**, because an inelegance is not a
defect and the difference decides whether it is worth changing.

`_IMG_SEQ = 0` at module load and `_store_image` returns `f"img_{_IMG_SEQ}"`
after incrementing, so the Nth screenshot of EVERY process is `img_N`. Run with
two module instances — which is exactly what a server restart is, since the
registry is module state — and a stub bridge that captures the payload:

```
session A ids: img_1, img_2  -> the recording stores 'img_2'
session B ids: img_1, img_2
replay of imageId='img_2' -> 'uploaded'
bytes actually uploaded: b'SESSION-B-SHOT-2-UNRELATED'
VERDICT: SILENT WRONG FILE

fewer-screenshots arm: ValueError: unknown imageId 'img_2' …   <- loud
```

**The condition is exact: the replay session has taken at least as many
screenshots as the recording had before its upload.** Below that it raises and
the flow fails honestly; at or above it, a different file is uploaded and the
step reports success. A `run_flows.py` replay takes no screenshots at all (they
are observations, dropped at compile), so CI is always in the loud arm — and an
MCP session where the agent has been looking at the page is routinely in the
silent one.

Content-addressing the id (a hash of the png) makes a stale id MISS instead,
which is the honest failure. That is `mcp_server.py` and is §6 item 3.

### M3 — `MUTATES` and `_BATCHABLE` had drifted

`MUTATES` decides what survives a recording; `mcp_server._BATCHABLE` decides what
`_flow_call` can dispatch. Nothing held them together. Measured:

```
MUTATES names the flow runner cannot dispatch: ['call_page_tool', 'dismiss_dialog']
replay of a recorded dismiss_dialog -> RuntimeError :
    flow step names 'dismiss_dialog', which is not a runnable tool
```

`call_page_tool` has been in that position since WebMCP shipped: **a flow driving
a page-declared tool records cleanly and cannot be replayed.** It fails LOUDLY,
naming the step and the tool, which is why this is a documented gap rather than a
defect — but it is a gap a recording can walk into with no warning.

`FD25` is a permitted-SET tripwire, the same shape as `L10c`: the set may shrink
(the gap closed) and may not grow (a new tool that records and cannot replay).

**CLOSED in `mcp_server.py` (`_KNOWN_UNDISPATCHABLE` is now `set()`), and the
closing found a defect in the diff this paper proposed.** `dismiss_dialog` is
defined ~300 lines BELOW the `_BATCHABLE.update({…})` literal, so adding it there
raises `NameError` at import and every suite that imports `mcp_server` dies. It
is registered beside its own definition instead
(`_BATCHABLE["dismiss_dialog"] = dismiss_dialog`); `call_page_tool` is defined
above the table and went in normally. The set is kept rather than deleted so the
next gap is still reported WITH ITS NAME, and a tool that genuinely cannot be
dispatched can be named deliberately instead of by removing the check.

---

## 3b. Found after the first pass — the review of the review, and a false cause of my own

### C14/C15 — a warning about a check that is not there

Reported by the coordinator from a live re-recording and reproduced here both
ways. `compile()` moves the landing checks off the navigational step onto
`require`, and the three review lists are COMPUTED before that move and WRITTEN
after it. `flows/acme-invoices-drilldown.flow.json`, recorded live by the
pre-fix recorder, carries the evidence on disk:

```
require : {"path": "/login"}
step 1  : navigate   expect={}   review=["unproven: location was first observed
                                          AFTER this step, so nothing here says
                                          it would have failed before"]
```

Filtered by step INDEX between the move and the loops, not stripped by a prefix
list afterwards — `("hollow:", "unproven:", "dropped:")` is the hand-kept list
this project keeps deleting, and it would go stale the next time a review line is
added. `FW18b` is the control that a step which KEEPS its expect keeps its review
lines, so this is not "clear review everywhere".

**Live-verified** by recording the shape that produced it — the opening
`instructions=` and `browser_batch` both teach — through the real MCP path:

```
require : {"path": "/login"}
step 0  : tabs_create_mcp  expect={}  review=[]
step 1  : navigate         expect={}  review=[]
step 2  : fill_form        expect={"query": …}  review=["unproven: query …", "unevidenced: …"]
```

Asking why only those three lists led to C15: **`require` is subject to no
analysis of any kind**, because all three loops walk `kept`. `hollow` and
`unproven` are meaningless there for the reason above. An unwitnessed ABSENCE is
not — #64's rule is that a search which found nothing becomes a permanent "this
must never appear" — and in a precondition *no* absence can ever be witnessed,
because nothing precedes a landing state. So the rule cannot be applied as a
drop: it would delete every one of them, and "the cart is empty when this flow
starts" is only expressible as an absence. One flow on disk
(`bench-grocery-add-to-cart`) uses exactly that shape, with
`query {"selector": "[aria-label=\"Убрать\"]", "count": 0}`. It is NAMED instead,
on the step it guards.

---

### A false cause I shipped for twenty minutes, and what caught it

`C9`'s first version also read a `navigate` step's own url as a fallback for
"where the recording was". That is an **intent**, not an observation. Running the
chaos arm — not reading the code — showed it decorating a genuine failure on
`acme-nav-badge`, which navigates to `/logout`, a route that redirects to
`/login`:

```
no element on the page matches this step's target: … name='Sign in'
The tab is also at a different PATH than the recording was when it performed
this step: 'http://127.0.0.1:8787/login' now against '/logout' then.
```

A false cause, on a flow doing exactly what it recorded, that would have fired on
every login flow, every canonical redirect and every trailing-slash rewrite —
principle 6 violated inside the note written to serve principle 6. The scan now
reads OBSERVED locations only (`expect.url` / `expect.path` / `require`); a
navigate still terminates it, because an earlier step's location describes a page
the flow has since left. `FR26d` is the control, and it is honest about what it
controls for: it passes against HEAD too, because HEAD has no note at all. It
fails against **my own intermediate state**, which is the arm it was written for.

---

## 4. Still silently wrong, or unreachable

1. **An unwitnessed ordinal in a scrolling window (M1).** Warned at record time;
   nothing refuses it. Closing it needs a per-member discriminator the collector
   does not emit. Geometry would cover it and is refused because it drifts
   (#23: 110px, #25: 1,097px).
2. **A popup driven with no explicit `tabId` (C1's residue).** The `newTab`
   review names the mechanism; the calls themselves are invisible to
   `core/flows`. The server diff in §6 closes it exactly.
3. **An assertion that decays with the clock** — a date, "3 days ago", a rate
   quoted today. `FLOWS-FAILURE-SURFACE` 6.8 calls this INHERENT and it is.
   **Deliberately not built**: the recorder holds its own timestamp, so testing
   the ISO rendering against an asserted string is exact — but covering
   `18 November 2026` and `11/18/2026` needs a date-FORMAT list, which is
   principle 4's wordlist class. A detector that fires on one format and not the
   others is worse than none, because its silence reads as a verdict.
4. **A re-render that REUSES nodes between the read and the act.** `_bind`
   resolves a descriptor to an mmid and the tool call is one bridge hop later.
   #82 measured this class live and shipped the note; the refusal half is
   measured and deliberately unshipped. Nothing here changes it.
5. **A `query.selector` or `css_scope` naming a per-load id.** The playground
   regenerates every id and class on every load by design, and a recorded
   selector is the one thing in the file that is not a declaration-based
   descriptor. It fails HONESTLY (0 matches), so it is `DETECTED` and listed
   only so nobody expects otherwise.
6. **`file_upload(paths=…)`** records absolute machine-specific paths. Replay on
   another machine errors, which is honest; no warning was added because it
   would fire on every upload (#15's always-on noise).

---

## 5. Could not be reproduced

**A blocking `alert()`/`confirm()` under this harness is confounded, so no
verdict is recorded for `dismiss_dialog` itself.**

Playwright auto-dismisses a JS dialog unless a handler owns it, so by default a
`confirm()` never blocks: the click returned in 0.1s with `NO EFFECT` and
`dismiss_dialog` correctly answered *"No JavaScript dialog is open"*. With a
handler registered that does nothing, the dialog stays up and:

```
click RAISED after 30.0s: TimeoutError: extension did not respond to computer within 30s
get_url while blocked   : {"url": ".../lab/confirm", "title": "Confirm · lab"}   (instant)
dismiss_dialog RAISED   : TimeoutError
```

`get_url` answering instantly while every page op hangs is #51 working exactly as
documented. **`dismiss_dialog` timing out is NOT attributable**: Playwright holds
its own CDP session on that tab with the `Page` domain enabled and owns the
dialog event, so a second `chrome.debugger` session asking
`Page.handleJavaScriptDialog` is not a clean test of the shipped path. Stated
rather than banked, per #50: an unreproducible intermittent cannot be fixed by
guessing at it.

What IS attributable from that run, because it is pure compile logic, is C3: the
timed-out click was dropped as an error and the flow saved as one `navigate`.

---

## 6. Owed to `mcp_server.py` (not edited; another agent holds it)

Three one-line changes, in order of value:

**Item 1 is DONE** — see M3. `call_page_tool` went into the
`_BATCHABLE.update({…})` literal; `dismiss_dialog` is registered beside its own
definition, because it is declared below that literal and putting it in the
table raises `NameError` at import. `_KNOWN_UNDISPATCHABLE` is now `set()`.
**Item 3's reproduction is in M4**, so it is no longer MEASURE FIRST.

```python
# 2. _flow_entries — return WHICH tab was read, so the recorder can see a popup
#    that stole `active` even when no call names a tabId (C1's residue, §4.2).
#    Today it answers with a bare list and the resolved tab is discarded.

# 3. IMAGES / _store_image — `img_<n>` is a per-session SEQUENTIAL counter, so a
#    replay in a session that happens to have taken more screenshots resolves a
#    recorded id to a DIFFERENT image and uploads it successfully. A content
#    hash makes a stale id MISS instead, which is the honest failure.
```

---

## 7. How to re-derive any of this

Fixtures live in `tools/saas_playground.py` under `/lab/`, deliberately outside
the session so a probe does not have to log in first:

| page | shape |
|---|---|
| `/lab/frames` | two same-origin iframes and one cross-origin (`localhost` vs `127.0.0.1`, same server) |
| `/lab/shadow` | an OPEN and a CLOSED shadow root, each holding a real control |
| `/lab/virtual` | 200 records, ten in the DOM; `?plain=1` strips the per-row code |
| `/lab/confirm` | a Delete whose happy path goes through `window.confirm()` |
| `/lab/popup` | a `target="_blank"` link and an Acknowledge button on both sides |

```bash
python tools/test_flows.py                            # 297 checks
python tools/run_flows.py --playground --local-only   # the live CI suite, 12/12
python tools/run_flows.py --check-only                # every file, no browser, 30/30

# the ablation that makes the 22 new checks worth anything
git archive HEAD | tar -x -C /tmp/ablate
cp tools/test_flows.py /tmp/ablate/tools/
cd /tmp/ablate && python tools/test_flows.py          # 275/297
```

The live record→replay probes used a lab harness that starts the real bridge,
launches Chromium with the unpacked extension, grants the origin into a throwaway
profile, and drives tools **through `mcp._tool_manager._tools[name].fn`** — the
registry, not the module globals, because the recording wrappers are installed
there and a probe that calls the globals records nothing (#49, #55, twice).
That is `tools/run_flows.py`'s stack plus the recording half; it is not checked
in, because `run_flows.py` already covers the replay half in CI and a second
harness would be a second spelling of it.
