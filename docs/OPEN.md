# Open questions, ranked

The single working list. Each entry carries its evidence, because an open item
without evidence is a rumour and this project has had to delete several.

**When something closes, delete it from here** and leave the history in
`CLAUDE.md`. A stale open item sends the next reader to re-derive something
already done — and a retraction at the bottom of a long entry does not retract
the heading (#67).

Status key: `OPEN` · `IN FLIGHT` (being fixed now) · `MEASURE FIRST` (do not
build until the number exists) · `ACCEPTED` (a limit we are choosing to keep,
documented rather than fixed).

Closed this session and deleted from here: a variable reaching the input and
the assertion but **not the target** (a flow acting on the thing it just
created bound to the record a PREVIOUS run left and reported PASSED), and an
assertion tool that was REFUSED or RAISED being reported as a failed assertion
rather than as a check that never ran. Both in `FLOWS-FAILURE-SURFACE.md`
(2.6, 5.6), both pinned by checks that fail against the pre-fix code.

Last reviewed: 2026-11-15. Closed and deleted from here since the last
review: `query_elements`' missing visibility count (Q6c-Q6f), and the
readiness window measured in an unthrottled regime (R23/R23b — a 1000ms
window is 50.7% false-quiet at a 2s commit interval; 3000ms is 0.0%). Closed this session and deleted from here:
the kana fold collision, silent truncation loss in the default format,
`require` never firing, resume binding the wrong target, the handler-property
blindness, and the locale hazard (which did NOT reproduce) — all in `CLAUDE.md`
#71, #72 and #73; **item 14 (`opacity:0`)** — measured and CLOSED as DON'T
BUILD (#78): 175 elements across 21/96 sites, **0 declare any ARIA role**, **0
identities lost**, and Chrome keeps 149 of them but the only interactive ones are
14 skip links and 2 back-to-top buttons, transparent precisely because the page
is not offering them; on the text half the risk surface is **505 characters
corpus-wide** (in-viewport AND not aria-hidden) against 22,252 if you cut on
opacity alone, with **0 of 434 sampled strings matching the success/error
vocabulary** that motivated the question. Probe kept at
`tools/audit_opacity.py`. And **`query(scope,…)` as dead code** — WIRED rather than
deleted, on a measurement (`CLAUDE.md` #76, `READINESS.md` §5b). Its residual is
narrower and lives in `READINESS.md`'s own open list: landmark attribution for
an UNSCOPED read is still unbuilt and is a different problem, needing a rule for
which landmark owns a record and a way to print several at once.

---

## Tier 1 — a wrong answer reaches the user

> **FIVE PARALLEL AUDITS LANDED 2026-11-17 — see `CLAUDE.md` #82 and the
> working papers in `docs/research/`.** Read those before re-deriving anything
> below. What shipped from them: a FALSE QUIET in the readiness signal (a
> ShadowRoot has no `parentElement`, so direct appends into one were
> unattributable), a lone UTF-16 surrogate that KILLED the server process, a
> one-character logographic query that could not reach its own control, and a
> `data-*` state marker that now names its source. What was measured and
> REJECTED: per-landmark readiness attribution (item 5), and ResizeObserver for
> the observe→act guard (item 1). The headline is a negative result —
> `lost_identities` = 0 across 40 live out-of-sample sites — with its sample
> bias stated in #82 rather than buried.


### 0. Reachability by name — MEASURED at 0.9996, residual is ONE element — CLOSED
Every ruler here measures PRESENCE — presence, `lost_identities`, Mind2Web
recall, and item 12's own DS. CLAUDE.md #74 found 118 elements that were
present in all of them and unreachable by `find`, on a page the readiness probe
called settled, including by their VERBATIM label. The listing was correct
throughout; the tool reading it was not.

Three of this session's defects were in the tools that READ the listing rather
than in the listing (the `find` blanking, the table column misalignment, the
submit verdict), and **no offline measurement in this repo could have caught
any of them**. A ruler that scores `find` against the labels the collector
emitted — ask for each entry's own printed identity and check it comes back —
is now built: `tools/measure_findability.py`. **811/824 = 0.9842** across 34
frozen sites, with contested identities (shared by several entries, so the
probed one can fall outside find's bounded result set) counted separately.

**And the claim that it would have caught #74 is FALSE on this corpus** —
ablating the fix gives the identical number, because none of these 34 sites has
#74's shape. `--self-test` builds it synthetically and DOES fail against the
pre-fix scorer, with a known-miss control passing in both arms; that is the
guard, and the corpus run is the population number. Two different jobs.

**Residual: 13 misses, all one shape, none an app shell** — a label joined to a
badge (`span "Search Cmd+K"`, `a "Issues 5k+"`, `ul "4.1.0 25.9k 6.1k"`). The
name is assembled, so it is blanked, and unlike ptable's tile some contributors
ARE kept entries, so it is not a sole carrier. **The metric is therefore
stricter than the agent's real situation**: find("Issues") returns the inner
span, and clicking it does what clicking the link would, which is the same
reasoning #18/#73 use to credit a descendant on Mind2Web. Deciding whether to
credit a descendant here should be taken on its own merits, NOT while looking
at the misses it would erase.

**#75 THEN REPORTED THAT A DESCENDANT-CREDIT ARM ADDED 0 AT 95 SITES, AND THAT
IS RETRACTED — it had measured a closed browser.** `one()` closed its Playwright
context in a `finally` BEFORE the probe loop ran, and `_descendant_returned`
ended `except Exception: return False` — so every call evaluated against a dead
page, swallowed the error, and answered "no descendant". The arm was 0 BY
CONSTRUCTION, and the refutation it was taken to be was an artefact. The helper
no longer catches: a question that could not be ASKED is not an answer of no.

**Re-measured with the arm alive, 84 frozen sites, 2,661 unique identities:
0.9797 strict -> 0.9996 with descendant credit. 53 of the 54 misses are the
label+badge shape**, so the explanation above was right all along and is now a
number rather than a theory.

**The single element reachable by NEITHER is `carbon`'s `div "All about Carbon
What's happening Designing Dev…"`** — a container whose accessible name is a
page section's worth of concatenated text, with its contributors all kept as
their own entries. That is precisely what the blanking rule exists for (#34,
#35, #74): `find` declining to confidently return a div wrapping half the page
is the rule working, not a defect. **This item is closed as measured; what is
left is one element, and it is the intended behaviour.**



### 1. The observe→act gap — BOTH HALVES LIVE-VERIFIED (#84 NOTE, #87 REFUSAL)
> **NOTE half, #84.** A click on a control whose identity moved since the read
> reports it and acts. Live-verified.
>
> **REFUSAL half, now shipped.** Measured first
> (`tools/audit_stale_refusal.py`, 92 frozen sites, 35,750 controls, a real
> 3.6s model turn): all controls move on ANY field at 1.491%, on IDENTITY alone
> at **0.081%**, and DECLARED SUBMITS at **0 of 54** — which tightens the bound
> from ~30% to ~5.6% and is why #84 was right to hold it until there was a
> number. `rec` is excluded for a STRUCTURAL reason rather than the noise
> figure: it is the surrounding record's text, and `fill_form` fills the form
> before submitting, so refusing on it would refuse on success.
>
> **IT WAS UNVERIFIABLE FOR A WHILE, AND THAT GAP IS WHY `sw_info` NOW REPORTS
> THE EXTENSION'S AGE.** The refusal was committed at 13:22 while the service
> worker running in the user's Chrome had started 23:33 the previous night, so
> for several hours it was shipped, fixtured, headed CLOSED, and had never
> executed in a browser. A `/mcp` reconnect does NOT fix that; only a reload at
> chrome://extensions does, and nothing said so. `sw_info` now reports
> `extension_code_changed_since_worker_start` so the next reader does not have
> to work it out from commit times (#87).
>
> **BOTH HALVES ARE NOW LIVE, each in both directions.** The NOTE half in #84.
> The REFUSAL half in #87, after the reload: on the fixture's login page with
> the submit's label changed between the read and the click, `REFUSED:
> [mmid='24'] is declared a SUBMIT by this page, and it is not the control you
> read — name "Sign in" -> "Delete everything". NOTHING was clicked.` With the
> stamp refreshed and nothing drifted, the same click PROCEEDED — which is the
> control, since a guard that refuses everything would satisfy the first half
> alone. #81's dead-click guard then reported `NO EFFECT` honestly on that
> second click, because HTML validation blocked the empty form and the page
> genuinely did not react: two guards verified in one call.
>
> It lives in `clickTrusted` as an opt-in, because the rect it needs is already
> in hand there. The first attempt took a second `_rectForPage` round trip from
> `fill_form` and could not be made to fire under the mock; moving it is both
> cheaper and the thing that works. The only caller that opts in is the submit.
> SB1 fails against the pre-fix code; SB2 and SB3 pass in both arms.
>
> **The SECOND irreversible case shipped too**: a click on a control HTML itself
> declares a submit (`type=submit|image`, or a `<button>` with no type inside a
> real `<form>` — #24's rule). SB4 fails pre-fix; SB5 and SB6 keep it scoped.
>
> **THE THIRD IS DELIBERATELY NOT SHIPPED.** The design also named a WebMCP tool
> declaring `readOnlyHint:false`. It is a DIFFERENT mechanism: there is no
> element and no stamp, so the comparison would be between what `page_tools`
> reported and what the page declares at call time — a tool redeclaring itself,
> not a control being swapped. **The 0-of-54 measurement says nothing about that
> population**, and shipping a refusal on the strength of an analogy is the move
> this project does not make. `MEASURE FIRST`, and the probe that settles it:
> cache each tool's name, schema and annotations at `page_tools`, re-read them
> at `call_page_tool`, and count how often any of the three differ across a real
> model turn on pages that declare tools at all. Today that is **zero corpus
> pages** (WM1 pins that the line costs nothing on the current web), so the
> probe needs a fixture that redeclares, and the honest answer may be that the
> population is too small to bound.

### 2. 52.6% of ordinal-bearing descriptors cannot be witnessed `MEASURED CANDIDATE`
> **A VIRTUALISED LIST IS THE WORST INSTANCE AND IT IS NEW (2026-11-18).** The
> crowd an ordinal was counted against is the rendered WINDOW, whose size does
> not change when it scrolls -- so `len(hits) != of`, the composition check that
> catches a row being added or removed, **can never fire at all**. Measured live
> on a 200-record list with a ten-row window: recorded REC-1003, replayed
> REC-1053, no refusal and no note, and `recordAtoms` was `None` because the rows
> render no distinguishing text. The same page with its per-row code restored is
> SAFE -- the descriptor reaches `near="REC-1003 Select"`, needs no ordinal, and
> refuses after the scroll -- so this is about rows that declare nothing, not
> about virtualisation. Not fixable from declarations: the scroller is not an
> interactive element, the rows report `clipContainerMmid: None` and
> `scrollRegion: False`, and ARIA's `aria-setsize`/`aria-posinset` are present on
> 3.8% of controls (#83). The `positional:` warning now names it as a third
> mechanism beside a re-sort and churn.
> `docs/research/FLOWS-CONCEPTUAL-BREAKS-2026-11.md` M1.
> **Re-measured in #83 on 39 sites against #72's 24.** The unwitnessed share is
> **52.6%**, not 59.4%, and the shipped witness covers 47.4%. #72's claim that
> the shipped witness is ~11.6% WRONG on a re-sort is mostly #72's own mutation:
> under a FAITHFUL whole-record move it was 0 of 112 WRONG on Hacker News.
> A candidate now exists with numbers — the record's own rendered TEXT, taking
> shipped-OR-record coverage to **69.0%** and cutting re-sort WRONG from 11.6%
> to 0.4%. Attribute atoms raise coverage further and are REJECTED: Angular
> Material mis-bound 4 of 120 with no mutation at all, on a per-load generated
> `id` that a two-load stability check does not catch.
>
> **SHIPPED AND LIVE-VERIFIED (#83), and this blockquote said "Not applied" for
> a day after it was** — the stale-heading class #67 names, in the file that
> exists to stop it. `atoms_map` is in `descriptor.py`, `build()` stores the
> text atoms unique to each crowd member, and `_resolve_recorded` decides by
> them FIRST, ignoring `of` and never falling back to the ordinal.
> `flows/live-atoms-resort.flow.json` carries one (`['Acme Ltd', 'INV-1001']`)
> and was proved in BOTH directions against three rows identical in every
> declared field and in their surroundings: with atoms it deleted INV-1001 and
> said so; with the atoms stripped from the same file it deleted INV-1003 — the
> wrong invoice — and only the postcondition caught it. That second row
> understates the danger: the recorder reports ~23% of recorded steps carry no
> postcondition at all, and such a step would have reported PASSED.
> The heading's 52.6% is still the right number for what is LEFT.
The re-sort mis-bind is **closed on the `resort` arm, for the witnessed
minority** (#72): `resort` on a witnessed descriptor is **0.0% WRONG at 94.3%
CORRECT**, for +0.2pp refusals on the six pre-existing mutations. What remains
is crowds identical in every declared field *and* in their surroundings, where
nothing the collector emits separates the members. They are no worse than
before and no better.

**Two corrections to how that was written down**, both checkable and both now
carried in `FLOWS-FAILURE-SURFACE.md` 3.3a. The witnessed set is a **minority**,
not a majority — 212 of 558 (38.0%) on resort, 238 of 586 (40.6%) on reorder,
which is the same fact as the 52.6% in this heading. And the closure number is
from the `resort` arm alone: on the adversarial `reorder` arm a **witnessed**
descriptor is **71.4% WRONG** (#72's own table; re-derived at 55.6% on a
different 6-site sample). An anchor-only witness stays put while its element
moves, so whichever member arrives at the recorded anchor is bound confidently
and reported as a successful `moved` re-bind. #72 dismisses that arm as not
physically realisable, which is an argument rather than a measurement.

Refusing them was rejected deliberately: it would pause ~14% of all descriptors
on an **unchanged** page, which is not a safety cost but losing the feature. The
recorder warns at record time instead, and the step carries a `review` line.

**Flows recorded before #72 carry no witness** and keep the old behaviour until
re-recorded.

**THE VIRTUALISED SUB-CASE: the REFUSAL is DON'T BUILD, and the silence is
closed anyway.** The refusal was the wrong thing to be solving for. The
recorder already writes a `positional:` line naming the three mechanisms, and
since this entry the RUNNER says it too — a step pinned by position that
PASSES now reports that it was, because a pass there is not evidence the right
element was acted on. **In BOTH renderers**: `run_flows.py` printed `reason`
only on a FAILURE, so the note shipped and CI — where nearly every replay
happens — never showed it. It has its own result key now.
**And the stored review line is RE-CHECKED, not trusted**: a `positional:` line
records what was true at RECORD time, so a flow written before the content
witness existed carries one on a step the witness now resolves.
`live-atoms-resort.flow.json` is exactly that — the line AND
`atoms=['Acme Ltd','INV-1001']` on one target — and reporting it would have
announced "pinned by POSITION alone" about a witnessed step. The descriptor is
asked instead, which self-corrects every flow already on disk. That costs no collector field, no round trip and no
threshold: it reads a decided fact off the step, the way the `unevidenced:`
guard already does, and it is silent when no step carries one (FR28/FR28b).
So "silently wrong" is now "stated at replay"; what remains unbuilt is only
the automatic REFUSAL, priced below.

**THE REFUSAL ITSELF: measured and DON'T BUILD.** #90's one remaining
silently-wrong case is a crowd that IS a rendered window — its size does not
change when it scrolls, so `len(hits) != of` can never fire. The recorder
already warns (`positional:` names the scrolling window and says the
composition check cannot fire there); what is missing is a REFUSAL at replay.

The candidate was the page's own geometry: a declared `overflow: auto|scroll`
ancestor whose content is taller than its box is a WINDOW onto something
larger, which is exactly when an ordinal means a screen position.
`tools/audit_scroll_window.py`, 96 frozen sites:

| | |
|---|---|
| tied crowds | 854 |
| unwitnessed (the population #72 left on position) | **135** |
| …inside a declared scroller with overflowing content | **8** |
| …as a share of unwitnessed | **5.9%**, on 6 of 96 sites |

A refusal keyed on it reaches **5.9% of ~14% of all descriptors, i.e. under 1%**,
in exchange for three halves of plumbing — a collector field, a descriptor
field and a runner branch. Not worth it, and the recorder's warning already
covers the artefact.

**AND THE FIRST READING SAID THE OPPOSITE, which is the part worth keeping.**
At 19 sites it was **3 of 18 = 16.7%**, which would have justified building.
The full corpus is 5.9%. A small-n reading that flatters a change you already
want to make is the exact shape #16 exists for, and the only thing that caught
it was running wider before acting.

**What would reopen it:** not another geometric signal. The corpus does contain
a little of the shape — `syncfusion_grid` and `adminlte` contribute 2 each — so
this is not "the sample lacks the population" (#25) but "the population is
genuinely rare here". A corpus of the internal admin tools this feature
actually runs against could move it, and that is the same corpus `OPEN.md`
item 2's main entry already asks for. Measure once, for both.

What would close it: a declared per-member discriminator the collector does not
currently emit. Geometry would do it (87.3% coverage, measured) and is refused —
it drifts, so the safeguard would fire on every reflow.

### 2c. Starting state: the precondition reaches 1 flow in 20 — CLOSED
`require` is derived from the observations between the landing navigation and
the first action, and `_checks` understands exactly three tools: `get_url`,
`search_page`, `query_elements`. The opening every agent is taught (#45's
`instructions=`, #46's `browser_batch` description) is
`tabs_create_mcp → navigate → read_page`, and **`read_page` contributes
nothing**. Measured across `flows/*.flow.json`: **1 of 20 carries a `require`**,
and that one was recorded to demonstrate the feature.

Not a one-liner: `read_page`'s first line is
`Current URL: <pathname + search>` while `expect.url` compares against
`get_url`'s ABSOLUTE url, so deriving one from the other would put two
spellings of one fact into the file (rule 17). Either a path-shaped check kind
or a reconstruction from the flow's origin, and both are schema-level.

**CLOSED, with the first of those two.** `path` is now a check kind: the
recorder takes `read_page`'s first line and nothing else from a listing (the
rest is prose, which the `_checks` docstring is explicit must never become a
check), and the runner reduces the live `get_url` the same way
(`urlsplit` -> `path + '?' + query`) so both halves of the comparison are one
spelling of one fact. **The reconstruction was the wrong one of the two
options**: it drops a `#fragment` the live `get_url` carries, and by the time a
path reaches us a page with a hash is indistinguishable from one without.
`path` is also the better check for the job — a flow recorded against
`localhost:8787` must not fail because the port moved, which is the argument #61
used for preferring a same-origin href as a bare path (FR24c).
When `get_url` WAS called, `url` wins and `path` is dropped rather than asserted
twice (FP11c). FP11/FP11b/FR24 fail against the pre-fix recorder with `require`
coming back `{}` — the exact symptom. Flows already on disk are unchanged; they
acquire a precondition only when re-recorded, which is why this is HALF closed:
**the mechanism now reaches the opening every agent is taught, and the 20 files
in `flows/` still carry what they carried.**

Compounding it, and unlisted until now: nothing isolates one replay from the
next. `run_flow(stop_after=N)` ends mid-flow by design, `run_flows.py` creates
ONE tab for a whole batch, and `_pg_reset` runs only under `--playground` — so
the `ev-*` flows replay back-to-back in one tab with no isolation. Every flow on
disk happens to begin with a `navigate`, which is what has hidden it.
`FLOWS-FAILURE-SURFACE.md` 6.5–6.7.

**THE SECOND HALF IS CLOSED TOO, and the two halves are complementary rather
than redundant.** `run_flows.py` now creates a tab PER FLOW and closes it after
(best effort — a flow that navigated itself into a tab of its own, #58, leaves
the outer one closable, and a tab already gone is not worth failing a suite
over). That PREVENTS the coupling; the `path` precondition above CATCHES it when
it happens anyway.

**Demonstrated rather than asserted**, by building the shape no flow on disk
has — a real recorded flow with its leading `navigate` stripped, so it can only
work on state someone else left:

```
FAIL  zz-no-navigate-probe   0/2 step(s) in 6.09s
      the app is not in the state this flow starts from: path is 'about:blank',
      recorded '/logout'. Stopped before step 0 (fill_form). Nothing was run.
```

Both halves visible in one line: the tab was fresh, and the precondition named
the mismatch instead of filling a login form on whatever page was there.

**Building that probe found a defect in the `path` work itself**, two hours
old: `validate_expect` special-cased `url` as a bare string and let `path` fall
through to the mapping branch, so **a flow whose recorder had written a path
check could not be loaded at all**. FP11 drives the recorder, FO7 drives the
validator, and nothing drove one through the other — #19/#30's untested link, at
the load boundary. **FO8 closes it generically**: for every kind the schema
declares, round-trip a recorder-shaped value through `from_json`, so a new kind
that is not taught to the validator fails there rather than on someone's first
real flow. It fails against the pre-fix validator with the live error, and
`FO8[url]` passes in both arms as the control.

### 4. `no_effect` and the hollow/unproven classifier — CLOSED
They now compose. The dead-click guard gated on `not step.expect`, and a
hollow assertion is a TRUTHY dict, so the guard skipped exactly the population
#57 and #68 exist to identify: a check that was already true before the step
cannot catch a click that did nothing, and nothing else was looking.

`Step.review` was persisted by #72 and read by nobody — the half-contract
shape this project keeps finding. The recorder now marks the fully-unevidenced
case at RECORD time (`unevidenced:`), because it already knows which checks
were hollow or unproven and re-deriving that from prose at replay would be a
second spelling of a fact we hold (#21). The runner keys on that prefix alone.

Unevidenced is still NOT a failure on its own (#68) — it only decides the tie
when the tool ALSO reports it did nothing. FR21 fails against the pre-fix
runner; FR21b and FR21c pass in both arms, which is what makes them controls,
and they assert WHICH PATH stopped the step rather than the fixture's row
count.


### 4b. The off-viewport region hint names regions by TAG, not identity — CLOSED (twice)
#26 built the region hint so a caller can recover an off-viewport target with
one scoped read instead of a scroll plus a full re-listing, and measured all 76
off-viewport steps recovering that way. It names each region by its TAG:

    form(ref_212): 8, section(ref_274): 36, article(ref_177): 6, main(ref_71): 4

**Measured live in eval 6.** An agent told to fill in a hotel search scoped to
`ref_212` — the only `form` on the page, and the task was "fill in a search
form". It is the **newsletter signup at the bottom of the page**. The actual
search widget is not a `<form>` at all; it is plain divs inside `section`. One
wasted call, and the agent said the hint "would have been decisive if it carried
the region's accessible name or its first heading" — `form "Путешествуйте
выгоднее!"` would have said instantly that it was the wrong one.

The collector already resolves accessible names and already finds the main
heading (#30's declared-rank rule), so the information exists.

**CLOSED in #80.** The hint now carries aria-label, aria-labelledby text or the
region's first heading, clipped with `markCut`, so the same line reads
`form "Путешествуйте выгоднее!"(ref_212): 8`. RG2b pins it and RG2c is the
control that a region declaring no identity is still listed rather than dropped.
Cost: the honest pairing is free on a corpus that lacks the shape and proven on
a fixture that has it — my first two attempts to price it measured nothing,
because the pages I priced it on never produce a per-region hint at all.

**REOPENED by eval 7, where TWO agents wasted a call on the same hint on the
same page.** The hotels search page has exactly one `<form>` and it is the
NEWSLETTER SIGNUP; the search widget is not a form at all. Both scoped to
`form(ref_212)` because a search widget is visually a form, and both got
`input[email] placeholder="example@mail.ru"` and `button "Подписаться"`.

**The #80 fix is working as designed and its sources are insufficient here**:
that form declares no `aria-label`, no `aria-labelledby`, and contains no
heading, so RG2c's control path fires and it falls back to the tag. The page
declares nothing the current rule reads.

**What it DOES declare is inside the region**: a submit button labelled
«Подписаться», and a placeholder naming an email. A form's submit button names
what the form DOES, which is exactly what separates a newsletter signup from a
search — and it is declared content, not a guess about layout.

**CLOSED.** A `<form>` that declares none of the three sources is now named by
its submit — HTML's own `type="submit"`, the same declaration #24's submit
picker reads, so no wordlist and no layout. Prefixed `submits: …` because it
names the ACTION rather than the region: `form "Подписаться"` would read as the
form's own title and it is not one.
**Priced with #80's own pairing, both arms on the same page load across 30
frozen sites: +0.026% chars, firing on 2 — `bootstrap_forms` and `chakra`,
which are exactly the pages where a form is worth naming.** Free where the shape
is absent, proven on the fixture that has it. RG2d fails pre-fix; RG2b and RG2c
pass in both arms, so the three declared sources and the
a-region-with-no-name-is-still-listed rule are untouched.

### 4c. A visible label not wired to its input is unreachable by `find` — CLOSED
Same eval-6 run. The page renders «Направление» two lines above the destination
field; the input's accessible name is EMPTY and its placeholder is «Город, отель
или аэропорт». So the one word the TASK ITSELF uses is unreachable by `find`,
which is the first query any reader would try.

This is the page's defect — an unlabelled input — and `find` behaving correctly:
it is a lexical matcher over resolved identities (#20), and there is no identity
to match. **What rescued the agent was find's own miss census**, which pushed it
to `query_elements("input")`. So the #39 census earned its keep on its first
live outing.

The open question is whether `near=` should have carried «Направление» here. It
is designed for exactly this (a HINT for unnamed fields) and did not appear.
**Measure before changing anything:** #37 tightened `near=` because it was
firing where it distinguished nothing, and loosening it back is the move that
needs a number, not an anecdote.

**MEASURED, and the gap is precise rather than general.** Six real shapes of
"unlabelled input, visible label above it" put through the collector: **four
already worked** — a sibling `<div>`, a label inside a wrapper sibling, an
unwired `<label>`, a preceding heading. The two misses share one cause: the
hint has TWO walks, and the second (the ancestor walk, which is the only one
with reach) accepted **headings only**. So a label three containers above its
input, written as a `<div>`, was unreachable — which is how every grid-based
form puts a label above a field, and is eval 6's «Направление».

**No new guard was added, because the existing ones do the limiting.**
`short()` refuses anything over 60 characters, so a container's whole text can
never become a label; `labelish()` refuses code; and #37's two drop passes still
delete a hint shared by rows that have their own identity. Priced across 40
frozen sites, both arms on the same page load: **+77 hints, of which +68 land on
rows with NO identity of their own** — the inverse of the DataTables profile
#37 was fixing (18 of 28 on already-named rows, zero on the nine that needed
one) — **for +0.031% of listing characters.**

**AND THE SAME PROBE FOUND W19 ALIVE IN THE HALF W19 NEVER MIGRATED.** #30 fixed
the SIBLING walk — `near=` is documented as "nearest VISIBLE text" and was
reading comment bodies and `display:none` spans — and left the HEADING walk with
no visibility test of any kind. Measured: a `display:none` `<h3>`, and a visible
container holding a hidden `<h3>`, both produced `near="GHOSTLABEL"`. `near=`
counts as CONTENT coverage in find's scorer since #27, so an invisible string
carries a wrong element into the CONFIDENT results — W19's exact end-to-end
consequence. One `_nearVis` helper now serves both walks.

NB3/NB3b fail pre-fix with an empty hint; **NB3c/NB3d fail pre-fix with
`near='GHOSTLABEL'`**, reproducing the leak rather than describing it.
The end-to-end link was already pinned: F25/F26 cover `near=` as content
coverage, so a field whose only identity is its hint is reachable by it.

### 4d. `search_page`'s climb is a no-op against same-text wrappers — CLOSED
#42 states the rule as a condition about SUFFICIENCY — climb whenever the
element's own text cannot supply the `context_chars` the caller asked for — and
the implementation applies it ONCE, because #43 measured multi-hop climbing
quoting whole lists and set the fallback to exactly one hop.

Against a chain of wrappers that all carry the same string, one hop is a no-op
and the condition is still unmet. **Measured live in eval 6**, on the grocery
cart widget, six levels up from the matched node:

    ref_603 div.label        innerText "Корзина"
    ref_601 span.v-btn__content         "Корзина"
    ref_598 button.v-btn                "Корзина"
    ref_597 div.v-badge__wrapper        "Корзина"
    ref_596 div.v-badge                 "Корзина"
    ref_595 div.menu-btn                "Корзина"   <- the count badge lives here

The agent asked for 120 context chars and got 7. It reported the answer as "one
DOM hop away"; it is six, which is why the climb firing correctly still helped
nobody. (The badge is `display:none` while the count is 0, so the same search on
an untouched page is correctly silent — the symptom only exists once the cart
has something in it.)

**The obvious fix re-opens #43.** "Keep climbing while the ancestor adds no new
text" walks a link through its sole-child wrapper straight into the LIST, which
is the aozora defect #43 was written to end.

**The candidate worth measuring** is the rule this codebase already has a
spelling for: `_inFieldWrapper` from #29 — climb while the ancestor still
corresponds to ONE control, stop at the first that holds a second. That is
exactly what separates the two cases: the badge is part of one widget, the
aozora siblings are separate records. Two things to settle before it ships:
the corpus cost of both halves (#41, #44), and that `_searchTextPage` is
injected standalone, so it needs a forced byte-identical copy with an OC7-style
tripwire rather than a sibling call (#30's C11 class).

**CLOSED, and the candidate above was MEASURED AND REJECTED — it is the one
that counts CONTROLS.** Across 40 frozen sites it improved 19 of 269 unmet
matches, and one of them climbed adminlte's message list into FOUR messages
(max gain 244 chars). The reason is #18's defect exactly: a `<div>` row with a
handler is in nobody's control SELECTOR, so `_ctlCount` undercounts and the
container reads as "still one widget". A second, narrower opinion about what a
control is was measured at 60% of a whole accuracy gap once already.

**WHAT SHIPPED reads the repetition instead, which is the tree's own rule for
the same question (#27): a record is one of SEVERAL SIBLINGS OF THE SAME
KIND.** "Same kind" is tag+class where the author DECLARES a class — a class is
a statement that these elements are the same sort of thing — and exact subtree
shape where none is declared. Both branches are load-bearing and each is pinned
by a fixture the other cannot satisfy:
- the Vuetify twins hold DIFFERENT contents (a cart and a profile link), so
  subtree equality calls them different and misses the case entirely (Q1aa);
- a card's inner wrapper and its price are BOTH bare `<div>`, so tag alone makes
  them look like peer records and stops one level short of the card — the eval-7
  grocery shape (Q1ab).

**MEASURED, 40 frozen sites, 326 matches taken from each page's own controls:
25 improve, median +57 chars, max gain 147 — and max context UNCHANGED at 314
with ZERO contexts over 1200, i.e. no whole-list leak.** Strictly better than
the control-count candidate on every axis including the one that matters most:
more gains, larger median, SMALLER maximum. The gains are what the item asked
for — `'Market Cap'` → `'Market Cap | $2.21T | 0.13%'`, and a flight row that
was a bare `'Mumbai | New Delhi'` now carries its date, stops and price.
**Timing, interleaved on one page load: 0.27ms median against 0.31ms for the
old climb — FASTER**, because a record list now stops at hop 1 instead of
scanning four hops for a tag that is not there.

#47's declared-record rule is UNCHANGED and still wins outright within 4 hops,
so Q1n/Q1n2/Q1o/Q1o2/Q1p/Q1q are untouched. The stop set is the forced copy the
item predicted: `dup:fieldstop`, with C38 pinning it equal to `_FIELD_STOP` —
and **MC2 failed on the first version because I tagged only one of the two
sites**, which is the tripwire working on its author.

### 4e. A hit on a SIBLING reads as "you missed", and the click works — CLOSED
The hit-test echo distinguishes "you hit the inside of your own target" (silent,
the normal case for any control with inner markup) from "something else is in
the way" (MISMATCH). It has no third case, and eval 7 found one.

On a rail seat map, both seat clicks returned:

    MISMATCH: you named ref_1381, but the renderer hit-tests an element with no
    ref of its own (nearest listed ancestor: ref_1378 <svg>) — something not in
    the current listing is on top at that point

**Both clicks landed.** The hit node is an SVG `<text>` label painted over the
seat, a SIBLING of the seat `<g>` rather than a descendant, so `_inChain` is
correctly false — and the event still bubbles to the common `<svg>` where the
handler is delegated. The agent: *"the message gives no way to separate 'this
still landed on your element' from 'this hit the wrong thing'. I nearly spent a
verification call."* What saved it was an unrelated signal, a badge count.

The message also asserts exactly two causes — "something is on top, or the
layout moved" — and this is a third. #33's class, in the echo.

**The shape of a fix, and why it is not a guess.** `h.chain` already carries the
HIT element's ancestor refs. Walking the NAMED ref's ancestors the same way and
intersecting gives a listed common ancestor as a FACT, so the echo can say "you
hit a sibling; both are inside ref_1378" instead of naming two causes neither of
which applies. It must NOT claim the click worked — whether a handler sits on
that ancestor is not knowable from geometry, though `__abClickBound` is a
declared signal that could narrow it.

**Compounding it (#23's open item, reported again):** both seat clicks printed
the identical coordinate, because acting by ref centres the target. Two
different seats, two identical coordinates, two MISMATCH warnings reads exactly
like clicking the same thing twice.

**CLOSED, and ADDITIVELY — the first version of the fix was wrong.** It replaced
MISMATCH with "a SIBLING, not something on top of you", which is FALSE for a
transparent veil — and a veil is also a sibling sharing a listed ancestor. Both
candidates overlap the click point or neither would have been hit, so geometry
cannot separate "a label painted inside the widget" from "a layer covering your
target"; telling them apart by relative AREA would be a threshold in a path that
reports facts. So the shared ancestor is STATED, both readings are named, and
neither is chosen (#33).
`_hitTestPage` now takes the named selector, resolves it and intersects the two
ancestor chains — the nearest ref on both is where the event bubbles either way.
X10c/X10d fail pre-fix; **X10e is the control that a hit with NO listed ancestor
in common gains no sibling clause**, which is the veil, still on the plain
MISMATCH branch. The fixture needed a new shape — two overlapping children of
one listed container — because the existing veil page has no common listed
ancestor and could not reach the branch.

### 4f. A run of identical siblings whose meaning is in undeclared text `MEASURED, NOT FIXABLE WITHOUT A GUESS`
Eval 7, a three-month calendar. `read_page` listed ~236 day cells; the three
month titles are bare `<div class="month-title">` — no `<h1>`–`<h6>`, no
`role=heading`, no `aria-label` — so they are not interactive, not entries, and
the container holding title + grid has ONE kept child subtree and is pruned by
#27's single-kept-child rule. The agent got `1:"1" 2:"2" 3:"3"…` and could not
tell November from January, and spent a call on `read_page(ref_id=…,
filter="all")` to recover the headings.

That call IS the designed recovery and it worked. What is not available is any
way to know in advance that it was needed.

**Reading the class name is the fix this project does not take** (#27, #28, and
the owner's brief). The page declares nothing about those three strings, which
puts this in the same class as #79's nine Mind2Web misses and eval 6's unlabeled
add-to-cart control: the measured price of "existence and structure are decided
only by declarations". Recorded so it is not re-derived as a bug.

What WOULD be defensible is the shape #26 used for data tables — the listing
names them and hands over their refs, because a `<table>` is not interactive and
has no row of its own. Generalising that to "a folded run preceded by text"
needs a threshold, which is the thing being avoided. Not built.

### 4g. `_truncate` returns more than `max_chars` — MEASURED, NOT FIXED `ACCEPTED`
Every return path in `_truncate` slices to `max_chars` and then APPENDS its
trailer, so the result runs over by the trailer's own length. Swept on a 190-row
listing across budgets from 300 to 3000: **55–83 chars over on committed code**,
and more once a trailer grows a clause.

#42 reserved room for exactly this in `get_page_text`, where the note was ~560
chars and was crowding out the body it explained. Here it is tens of characters
against a budget the caller chose, and the trailer is the thing that makes the
cut honest (#13: the payload is what must never go).

**An attempt is recorded because it failed in an instructive way.** Threading a
separate slice point through, so the note prints the caller's number while the
slice lands short of it, does not converge: the three return paths switch
between the legend-dropping fallback and the ordinary slice as the budget
shrinks, so the trailer's length jumps rather than settling. Three iterations
still left **88 of 386 swept budgets over**, and it broke T22. Reverted.

What shipped instead is that `read_page`'s own `max_chars` description now says
the bound is on the LISTING and the trailer is added past it, and T27b asserts
the overshoot stays bounded by the trailer rather than being unbounded. A
meaningful fix means building each path's note before its slice, which is a
restructure of the most heavily-tested function in the project and wants its own
pass rather than a mid-eval edit.

### 4h. `near=` named a DIFFERENT option than the row's own value — CLOSED (collector half)
Eval 7, on a payment-method radio group. `find("ОПЛАТИТЬ Банковская карта")`
returned:

```
ref_2380  [input]  [radio] value="yoomoney" near="Банковская карта"  under="Способ оплаты"
```

A **yoomoney** radio advertised as `near="Банковская карта"` — and the radio
that genuinely IS Банковская карта (`ref_2376`) **was not returned at all**,
though the query matches its label. Acting on the returned ref selects the wrong
payment method.

Two halves, and they live in different files:
- **The row is internally contradictory**, which is the collector's: `near=` is
  the nearest visible text and it picked the neighbouring option's label. #37
  already drops a `near=` shared by rows that have their own identity; a radio's
  `value=` is a WIRE KEY rather than a label (the same class #41 marked
  `(post-key)` for), so the "has its own identity" test does not fire here.
- **`find` ranked it confidently**, which is the scorer's. #27 made `near=`
  count as CONTENT coverage deliberately, and it fixed two failures pointing in
  opposite directions, so demoting it is not a free change.

**The collector half is CLOSED, and the measurement the entry asked for is the
one that decided it.** `near=` is the nearest VISIBLE text, which in a radio
group is routinely a NEIGHBOURING option's label. `submits=` (4m) is what the
member posts — written by the author, different per member by construction. So
when a checkbox/radio declares a submit value, the adjacency guess is dropped:
a declared per-member discriminator beats a guess at adjacency, which is #37's
own reasoning with a second way for a hint to fail to earn its place.
A member declaring NOTHING keeps the hint, because there it is the only thing
the listing can say (NRQ1c, and it passes in both arms).
**Priced across 30 frozen sites, both arms on the same page load: +0.000% —
byte-identical, so the shape does not occur there at all.** Free where it is
absent, proven on the fixture that has it: NRQ1 fails pre-fix and reproduces the
live row in English — `input[radio] submits="yoomoney" near="Bank card"`.

**`find`'s half is deliberately NOT touched.** #27 made `near=` count as CONTENT
coverage and that fixed two failures pointing in opposite directions; changing
it needs checking against F4/F15/F25/F29, which are the regressions #27 and #39
recorded when this scorer was last touched. With the collector half fixed, the
contradictory row no longer exists for the scorer to rank.

### 4i. A `(disabled)` submit names no blocker — MEASURED, DON'T BUILD
Eval 7: «ОФОРМИТЬ ЗАКАЗ» stayed `(disabled)` with every visible field filled.
The blocker was a required `(unselected)` combobox per passenger that only
materialises AFTER a passenger is chosen and had scrolled above the fold, so the
viewport-scoped listing never showed it. `query_elements("input:invalid,
[aria-invalid='true'], .error")` returned nothing — the disable is Vue-driven,
not HTML validation.

What cracked it was a scoped read, which is not viewport-limited, where the rows
read `(unselected)` with the legend already explaining them. So the information
was reachable in one call and the agent needed two to think of it.

`fill_form` already enumerates unfilled `(required)`/`(unselected)` fields in its
result when a submit fails (#4). **A standalone disabled button has no
equivalent path**, and that asymmetry is the whole item: the same question, asked
about the same page, answered in one place and not the other.

**THE ASYMMETRY IS REAL AND THE BINDING IT NEEDS DOES NOT EXIST.**
`tools/audit_disabled_gate.py`, 105 frozen live-captured sites, self-tested
first because the headline is a zero and a detector reporting zero is worth
nothing until it has been seen to fire:

| | |
|---|---|
| visible DISABLED buttons | **74** |
| of them a DECLARED submit (`type=submit`, or implicit submit in a `<form>`) | **0** |
| with a form owner — what `fill_form` binds to | **0** |
| with `aria-controls` | 8 |
| with `aria-describedby` | 1 |
| with NO declared association of any kind | **65** |
| required-and-empty fields corpus-wide | 9, on 7/105 sites |

**Porting `fill_form`'s scope rule ships a feature that fires zero times.** Its
scope is `btn.form`, and across 105 pages not one disabled button has one.

**And a note on the disabled buttons that DO occur would be wrong on every one
of them.** They are `«`, `‹`, `Previous`, `Today`, `Save`, `Code Generator`,
`Recents`, `Select framework` — pagination at a boundary, toolbar states with
nothing selected, premium-gated features. Nothing is blocking them and nothing
can unblock them, so "here is what is blocking this" is a false sentence 74
times out of 74. That is #15's always-on warning, measured rather than
predicted, and the generic version of the advice costs ~195 characters on the
~70% of pages that hold a disabled control (≈3.8% of a median listing, against
the 2.6% the detail legend was accepted at).

**The eval-7 page is outside what any of this could reach.** Its checkout is a
Vue widget with no `<form>`, so `el.form` is null and `type=submit` is absent —
the same answer `fill_form` gives there, which #4 already settled as the honest
one. HTML and ARIA define no other link between a button and the fields it
gates; `aria-controls` is the closest and on all 8 instances here it points at
the table a pager controls, not at a blocker.

**What the agent actually needed was already printed.** The off-viewport note
reports BOTH directions, the magnitude in viewport-heights, and the regions with
their refs — and a scoped read is not viewport-limited, which is exactly what
cracked it. The residual gap is a reasoning step (connect a disabled control to
the regions that note names), not a missing fact, and this project does not fix
reasoning steps by adding a sentence that is false on 74 of 74 measured cases.

**What would reopen it:** not another attribute — those were tested. A corpus of
real checkout flows, where the population is disabled SUBMITS rather than
disabled pagers, and where the 0/74 might not hold. #25's rule applies in full:
this ablation measures the code against the sample and cannot measure the
sample.

### 4j. The aria-hidden note promises refs `query_elements` cannot give — CLOSED
The listing's aria-hidden note sends callers to `query_elements` and says
verbatim *"it queries the RENDERED document rather than this listing, so it
returns aria-hidden elements and its refs act normally."*

**The second half is false for anything rendered since the last `read_page`.**
mmids are stamped by the COLLECTOR (#32), so a suggestion list, a just-opened
menu or a fresh row carries none. Measured live in eval 7: an agent followed
that note, typed a destination, queried the suggestion button that had just
appeared, and got `<button> "Дубай ОАЭ" class="opt active"` with no ref. It
spent a whole call running `read_page` purely to make the collector stamp, then
re-queried. Its words: *"for a suggestion list — i.e. anything that appears in
response to typing, which is the normal case — `query_elements` alone is a dead
end, and nothing in that note says so."*

**HALF CLOSED, server-side.** Both sibling renderers now say it, and both fire
on ANY ref-less row rather than only when every row lacks one — the mixed case
(one read has run, the new half has not been stamped) is the common shape and an
all-or-nothing guard was silent for it. C36/C36b, with C36c the control that a
fully-stamped result says nothing. `search_page` carried the all-or-nothing form
since #32 and had the same hole.

**The note itself still over-promises** and is in `background.js`, held under
eval 7's Amendment 2 (one build per arm). Two candidate fixes, neither free:
drop the "its refs act normally" clause, or have the query op stamp what it
returns — which makes a read tool mutate the page's mmid registry, and that is a
contract change wanting its own measurement.

### 4k. A small `max_chars` is the only way to say "collect, do not print" — HALF CLOSED
Same run. The agent called `read_page(max_chars=300)` deliberately, purely to
trigger mmid stamping without paying for output, and got the `NOTHING could be
shown` branch — which is #34's message working exactly as designed, and reads as
an error for what was a successful use. There is no sanctioned way to ask the
collector to run without rendering a listing.

Related to 4j and probably resolved by the same decision: if `query_elements`
stamped, neither this nor 4j's extra call would exist.

**HALF CLOSED, server-side.** The message now states the one fact that makes
the deliberate use legible: **only the PRINTING was cut — the collection ran**,
so every element the walk reached carries a ref and a following
`query_elements` / `search_page` / `find` returns refs even though no row
printed. Verified rather than asserted: `_queryElementsPage` reads the `mmid`
ATTRIBUTE off the DOM, so the refs really are live. T24b pins it.

**The other half is a CONTRACT CHANGE and is not taken on reasoning.** Making
`query_elements` stamp would close this and 4j's remainder at once, and it makes
a READ tool mutate the page's mmid registry. The specific hazard, found by
reading what depends on it rather than by assuming: the collector assigns mmids
in DOCUMENT ORDER, and CT1 asserts the overflow list's refs come back sorted —
so an out-of-order stamp breaks an invariant the listing currently relies on,
even though #80's own cap notice already tells agents not to infer pairing from
ref order. Needs the measurement AND a live pass, which is the next thing owed
after the extension reload.

### 4l. A stepper's +/- both took the quantity as their name — CLOSED
Eval 7, on a product page. After adding to the cart:

```
ref_1151 | button "1" (just appeared)
ref_1154 | button "1" (just appeared)
```

Minus and plus, both named `"1"` — the stepper's quantity VALUE adopted as the
accessible name of both buttons. **Clicking the wrong one at quantity 1 removes
the item**, so this cannot be guessed. The agent spent a call on
`query_elements(attributes=["class","aria-label","title"])`, which did not
settle it either (`class="qty-btn"` on both, no aria-label), and resolved it
only with a screenshot.

**The same control on the CART page lists perfectly**, which is what makes this
a defect rather than a limit:

```
ref_3687 | button "minus"  (name read off an icon-library class name, not an accessible name)
ref_3693 | button "plus"
```

So the collector names these when an icon-library class is present, and on the
product page it instead ADOPTED A SIBLING'S TEXT. **A name that is confidently
wrong is worse than `(unlabeled-icon)`** — the latter sends the reader straight
to a screenshot with no detour through a dead-end attribute query.

This is the "two rows that mean opposite things, printed identically" class
named in eval 6, and **no presence-based ruler can see it**: both elements are
present, listed, named and clickable. `measure_findability` would score them a
hit.

**CLOSED.** The cause is `synthLabel`'s CARD-PATTERN branch, written for a card
whose caption sits OUTSIDE its one anchor — it adopts a PARENT's text for a
label-less control that covers >=30% of it. A stepper is three controls in one
tight parent, so both buttons took the same string. The guard is #29's
`_inFieldWrapper` rule one layer over: **a parent holding a SECOND control is a
GROUP, and its text labels the group**. Decided from the declared control set,
not from size or class names.
Priced on 30 frozen sites, both arms on the same page load: **0 names lost,
+0.00% chars**, 1 listing differing and that one a replay #16 names as
non-deterministic. Measured-harmless, with the value evidence in QS1 and the
live run. QS1 fails pre-fix with the live symptom exactly (`button "1"` twice);
**QS1b is the control that the card pattern still works where it was written
for**, and my first fixture missed the branch entirely at 23% area coverage —
the vacuous-fixture problem, eighth instance.

### 4m. A checkbox's `value=` reads as its state — CLOSED
Same run: `ref_3566 | input[checkbox] name="Выбрать все" value="true"` while
`query_elements(attributes=["checked"])` says `checked="false"` on all four.

The legend defines `value=` as CURRENT CONTENTS, so `value="true"` on a checkbox
reads exactly like "this is ticked". It is the literal HTML `value` attribute —
what the box POSTS when checked, which is the wire-key class #41 marks
`(post-key)` for, not its state. The row's state is carried correctly by the
presence or absence of `(checked)`; the `value=` beside it contradicts that.

#23 fixed the sibling case (`value="on"`, the DOM default never written by the
page). This is a page that genuinely writes `value="true"`, so suppressing it
outright would drop authored content — the fix is to put it in a slot that does
not mean state.

**CLOSED.** It moves to its own key: `submits="true"`, with a legend line that
says in as many words that it is NOT state and that the `(checked)` flag is.
Printing it is still worth doing — `OPEN.md` 4h is a radio group where the value
is the only honest identity — so this keeps the information and changes what the
key MEANS.
CB1/CB1b/CB1d fail pre-fix and reproduce the live symptom exactly
(`value="true"` on an unchecked box). **CB1c is the control and passes in both
arms**: a text input's `value=` IS its contents and is untouched. My first
version of that control also asserted the `submits=` count, which is zero
pre-fix — so it failed ablated and was not a control at all; that half is CB1d.

### 4n. A FILTERED miss reads exactly like a silent page — CLOSED
**Found on the OTHER arm in eval 7, and ours has it in two tools.** Worth
recording how it arrived: the eval's value is not only the comparison. An agent
driving the competing toolset reported a defect in its network reader, and
checking ours against the description found the same shape.

```
extension/background.js:
  "No network requests recorded for this tab" + (pat ? ` matching "${pat}"` : "") + "."
  "No console messages matched."
```

Neither states how many requests or messages ARE held. So *"your filter matched
nothing"* and *"this page did nothing"* render almost identically, and the
second is a far stronger claim than the buffer can support.

**What it cost on the other arm, and would cost on ours.** The agent filtered on
`lab-reports` to check a download, got `No requests matching "lab-reports"`,
concluded nothing had fired — and four `POST /event/add` requests confirming the
action were sitting in the same buffer. It then **clicked the download link a
second time to "make it fire"**, on an app whose entire purpose is recording
what you do. A real side effect, caused purely by a message that could not
distinguish its two meanings.

**The fix is one number and it is already in hand**: `total` is computed before
the filter is applied in both branches, so
`No requests matching "lab-reports" (4 recorded for this tab)` costs nothing.
`read_console_messages` is worse — it does not say whether a pattern was even
in play.

This is #16's rule as an OUTPUT contract rather than a measurement one: an
absence is only evidence when the thing doing the looking says what it looked
at. `search_page` already carries that discipline (#39's settled-state note);
these two did not.

**CLOSED.** Both now name the unfiltered total and say the pattern excluded
them, and point at re-running without it. NF1 fails pre-fix; **NF2 is the
control that a genuinely empty buffer claims nothing about a filter**, without
which the note would fire everywhere and mean nothing (#15).

### 4o. A navigate gets the COMMIT wait, not the CONTENT wait — CLOSED
`browser_batch` waits twice and for different things: `_settle` after a
navigation (Chrome's own `onDOMContentLoaded`, #51) and `_quiet` after an ACTION
(mutations stopping, #51). The second is gated on a step having ACTED, and a
`navigate` is not an act by that rule — so `click -> read_page` settles and
`navigate -> read_page` does not.

**On a client-rendered app, commit is not content.** Measured live in eval 7:
an opening `[tabs_create_mcp, navigate, read_page]` returned a listing holding
only the 7 nav buttons, with page text reading `debug_msg: Going to first step`
— the Vue router had not run yet — and the whole main content absent. One
wasted call. The agent put the diagnosis exactly: *"the machinery exists and
works well; it just doesn't fire after `navigate` … For an SPA the first paint
happens strictly after the point `navigate` returns."*

**CLOSED.** `_quiet`'s gate is now `_acted or _navigated`, and `_navigated` is
read off the SAME `_settle` reply that already decides the document wait — asked
rather than predicted (#51), so it costs no extra round trip and it catches a
CLICK that navigated, which a step's own input cannot reveal.
Free where it is not wanted: `await_quiet` returns immediately on a settled page
and prints nothing, so a server-rendered navigation pays one bridge op.
B18 fails pre-fix; **B18b is the control that an observation after an
observation still waits for nothing**, without which "wait on everything" would
satisfy B18 while taxing every batch (#38).

### 4p. A download click has no page-side consequence, and nothing says so — CLOSED
Eval 7, the files task. After clicking a `download` anchor: URL unchanged, DOM
re-read byte-identical, click output `landed at (1214,350)` — which confirms
the CLICK, not the DOWNLOAD. **The default verification instinct, re-reading the
page, is structurally incapable of confirming this action**, and nothing in the
click result or the anchor's row hints at what would be.

Both arms met it. Ours went to a shell `ls` and found the file;
`read_network_requests` is the in-tooling answer and nothing points at it.

**CLOSED.** A click whose target declares `download` now says that the URL, the
DOM and a re-read are identical whether or not the file arrived, and names
`read_network_requests` as the check that can see it. Declared attribute, no
guess — and resolved up to the nearest `<a>`, because the ref is routinely a
span inside the link. It rides the AGREEING branch, which is otherwise silent,
because silence is exactly the problem here.
X10f fails pre-fix; **X11b is the control that an ordinary agreeing click still
says nothing**, so this did not become per-click noise.

### 4q. `search_page` reports the TEXT's ref and no route to the ACTION — CLOSED
The last run of eval 7, and the only overhead call in an 8-call task.

`search_page("оливк")` returned `<div ref_1285 …> Оливки Доставка, без косточки
| 330 г | 229 ₽`. The agent needed the «Добавить» button, `ref_1291` — a
SIBLING, one level up and over. Neither route reaches it:
`read_page(ref_id="ref_1285")` scopes to the title div's own subtree, which
holds no button; and nothing names the parent card.

**What makes this fixable rather than inherent: `search_page` already knows the
record.** Its own context string IS the card, joined with the declared-boundary
marker — it climbed there to build it (#47's `_climbTo`) and then reported only
the leaf's ref. The agent put it exactly: *"it climbed to the card to build that
string and then reported only the leaf's ref. Naming the record's ref alongside
the match ref would have let me go straight to `read_page(ref_id=<card>)`."*

Attribution must not change — #32's rule is that the hit belongs to the element
whose own text first contains the match, or an ancestor reports every child's
hit. This is an ADDITIONAL field, not a replacement.

**CLOSED.** The climb already STANDS ON the record when it re-slices the
context, so `recordRef`/`recordTag` are stamped there — a fact in hand, not a
second walk — and the row prints `[record: ref_N <article>]` only when it
differs from the match's own element. The hit's own node is kept on the pending
object as `self`, because the first version compared via `hits.indexOf` which is
O(n) per hit per ancestor.
RC1 fails pre-fix; **RC1b is the control that a match whose own element already
supplies the context names none**. Two wrong versions of that control first: a
match that FILLS its element has nothing either side, so `_wants` asks for more
and the one-hop fallback fires — what stops the climb is real text on BOTH
sides. And both new calls passed POSITIONAL arguments to
`_searchTextPage(pattern, opts)`, so every option was ignored and
`contextChars` silently took its 150 default. The suite's own helper gets this
right; hand-written calls did not.

### 4r. CT1c's advice cannot answer the page it was written for — CLOSED
**This lands on advice added THIS SESSION**, in response to eval 6, and eval 7
showed it does not cover the case. The cap notice says:

> When many rows share ONE label, neither of those separates them… What
> distinguishes them is an ATTRIBUTE — `query_elements(selector,
> attributes=["href","value","title"])`

On a grocery catalogue every card has an identically-named «Добавить» and **none
of them carries a distinguishing attribute** — no href, no value, no title, and
no class name to build a selector from. What distinguishes them is **DOM
CONTAINMENT**: which card the button sits in. None of the three tools the notice
names expresses containment, and the one that does — `read_page(ref_id=…)` —
needs the card's ref, which is exactly 4q's missing piece.

So the advice pointed at `query_elements` when the real answer was "read the
listing and infer from ref ordering", which the agent did and flagged as
inference rather than fact: *"on a page where every card has an identically-named
«Добавить», a wrong inference silently adds the wrong product."*

**The honest reading of eval 6 → eval 7:** CT1c was right about the eval-6 page
(18 download links separated by `href`) and is incomplete as a general rule.
Containment is the other half and it belongs in the same notice, which means 4q
first.

**CLOSED, now that 4q supplies the missing ref.** `search_page` reports the
RECORD's ref beside the match, standing on the card it had already climbed to in
order to build the context string — so the recovery is two facts the tools
already produce rather than a new capability. The notice now carries both
halves: an ATTRIBUTE when one exists (the eval-6 answer, untouched), and
otherwise WHICH RECORD each row sits in, with the route named — `search_page`
the record's own text, then `read_page(ref_id=…)` on the card it names. It also
says plainly not to infer the pairing from ref ORDER, which is what the eval-7
agent did and flagged itself: *"a wrong inference silently adds the wrong
product."*

**Priced across 40 frozen sites, both arms on the same page load: +0.745%
corpus-wide, worst capped site +3.112%, and it prints on only 6/40 — the pages
where the cap has ALREADY dropped ~51 entries.** A first draft restructured the
sentence and cost +1.085% / +4.488%; rewriting it as a pure APPEND to the
existing one got both figures down with no loss. Cheap for the failure it
prevents, which is a wrong ACTION rather than a wasted call.
CT1d/CT1e fail pre-fix; **CT1c passes in both arms**, which is what proves the
eval-6 half was not traded away for the eval-7 one.

### 4s. The cheaper format drops the relationship that disambiguates — CLOSED
Same run. The agent chose `format="flat"` to reduce size and then needed the
containment the tree states by indentation:

> `format="tree"` would have nested it unambiguously; I had chosen
> `format="flat"` *to reduce size*, so the cheaper format is the one that drops
> exactly the containment relationship that disambiguates identical buttons.

`format`'s description sells flat on size and on "you only need a single named
control". Here the agent needed a single control whose name was shared by ~40
others, and nothing in the parameter's own text names that trade. #27 shipped
the tree as default for exactly this reason ("a flat list cannot express a
row"); the description of the escape hatch never caught up.

**CLOSED.** The condition was the wrong one: "you only need a single named
control" was SATISFIED on that page and the advice was still wrong. It now reads
*"worth passing when the control you want has a name that is UNIQUE on the
page"*, and names what flat drops — when several rows share one label, flat
cannot say which record each belongs to, and that containment is the only thing
telling them apart. A trade a parameter does not name is one the caller cannot
weigh. C20e pins it and fails pre-fix with the old sentence quoted.

### 5. SPA readiness — all three false-quiets now answered `CLOSED`
> The adversarial audit left three unscoped false-quiets. All three now have an
> answer, two of them a measurement rather than a fix.
>
> **(a) Per-landmark attribution — DON'T BUILD** (#82). Fixes 3 of 6
> steady-state false-busies, leaves every false quiet, costs 3.0–3.6ms per read
> against 0.002–0.006ms, and forces an ownership rule the design exists to
> avoid. Re-confirmed 2026-11-18 at 2.88–2.91ms against 0.002–0.006ms doc-wide
> and 0.022ms scoped.
>
> **(d) THE SIX STEADY-STATE FALSE BUSIES — measured, and a diff exists that is
> NOT applied.** `docs/research/READINESS-RESIDUE-2026-11.md`. Five of the six
> are one misclassification: a `textContent =` arrives as a `childList` record,
> and the ring filed it as *structural*, so a clock and a live price tripped the
> "do NOT conclude something is absent" banner for ever. `Node.nodeType` decides
> it — the ring's `text` kind already existed — and the renderer gains a third
> tier. 9 flips / 0 losses on 21 shapes, **it cannot produce silence by
> construction**, cost inside the A/A floor at 40,000 mutations in one batch,
> and 4.8% of frozen-corpus reads change tier at 4s with **0.0% at 1.5s** (so a
> page that is building is never demoted). The sixth row was never a defect —
> the window there genuinely still covers 280 element appends. The patch is
> APPLIED and live-verified 2026-11-18 (#88); the commit is the diff, which
> has been deleted so nobody re-applies it. **Before it was applied the
> readiness suite is red by 2 (R35, R36), deliberately.** No live pass yet.
>
> **(b) Cross-origin frames — SHIPPED.** A quiet verdict now names the frames it
> could not see into. Priced at **6.9%** of pages first, so 93% pay nothing.
>
> **(c) A late paint after a silent gap — MEASURED, DON'T BUILD.** The idea was
> sound and the mechanism works: wrap `setTimeout`/`setInterval` at
> document_start the way `listener_tag.js` already wraps `addEventListener` and
> `attachShadow`, and "the page has work booked" becomes a FACT it declared.
> The control confirms it separates the cases — the late-paint fixture reports 1
> pending timer, the settled fixture 0.
> **It does not survive the real web.** `tools/audit_pending_timers.py`, 29
> frozen sites, counted 4s after load:
>
> | window | settled pages that would carry the line |
> |---|---|
> | timers due within 2000ms | **55.2%** |
> | timers due within 300ms | **31.0%** |
>
> More than half of settled pages have work booked, because polling is normal.
> That is the always-on warning #15 priced and #43 deleted `readyState` for.
> **And tightening the window does not rescue it — it removes the point.** The
> shape this exists to catch paints 2,500ms out, so a 300ms window misses it
> while still firing on a third of pages: strictly worse on both axes at once.
>
> What remains is a genuine limit, stated rather than papered over: a page that
> is silent, has no network in flight, and will paint from a timer is
> indistinguishable from one that has finished. The probe is kept so the next
> person does not re-derive it.

### 6. A CSS transition is not waited for — PREMISE INVERTED, MEASURED

**THE ITEM WAS WRONG ABOUT WHICH WAY THE PROBLEM POINTS.** It read: a
`browser_batch` of four observations after a click all read the page before
Bootstrap's ~300ms fade, so a CSS-transition settle is wanted but would be a
chosen duration. Measured in the AGENT'S OWN TAB, which is hidden by design
(#12, and activating it was tried and rejected because it drags the user out of
their work):

| probe | result |
|---|---|
| `requestAnimationFrame` in 2.6s | **0 callbacks** (60fps would give ~120) |
| `setTimeout(16ms)` in 2.6s | **3 ticks** — clamped to roughly 1Hz |
| `transition: left 1200ms` | moved **0px in 1.5s**, never arrived |
| `transition: opacity 300ms` from 0 | computed opacity `"0"` for the whole 2s |
| `checkVisibility({opacityProperty:true})` on it — the COLLECTOR'S OWN test | **false at every sample** |

So there is no fade to wait for. **A dialog, toast or dropdown that fades in is
absent from `read_page` INDEFINITELY**, and waiting would have waited for ever.
#66's diagnosis of its own symptom was the opposite of the cause.

**It also closes #5's per-ref primitive bullet.** Playwright's actionability
check is *the same bounding box across two consecutive animation frames*. In
this regime there are no animation frames — not slower, zero — so that
primitive is not something we have failed to build, it is something the regime
forbids. A timer-based substitute costs ~1s per sample at the clamped rate,
which is unaffordable on the commonest op there is.

**WHAT SHIPPED is a named fact, not a wait.** The signal is the Web Animations
API's own declaration: `pending === true` with `startTime === null` means the
animation has not been given a start time — it is waiting for a frame that is
not coming — while `playState` still reads `"running"`. No class name, no
framework name, no threshold. `document.getAnimations()` measured at **0.01ms**,
and the cheap declared fields are filtered before any style resolve, so there is
no cost bound to choose.

The sentence appends to whatever the readiness note otherwise says INCLUDING the
empty string, because the usual case is a page that is completely settled while
the fade sits frozen — folding it into the "if I wait, will this change?" list
would be a lie by placement, since the answer here is no.

**The recovery is verified rather than asserted:** an `opacity: 0` element still
takes pointer events (unlike `visibility:hidden`), and `query_elements` queries
the RENDERED document by selector instead of applying the collector's visibility
rule — so it reaches what the listing omits.

R33 fails pre-fix (`frozenFade=None`); R33b passes in both arms.

**NOT taken: admitting opacity-0 elements to the listing.** #78 measured that
across 96 sites — 175 elements, 0 identities lost, and the interactive ones were
exhaustively 14 skip links and 2 back-to-top buttons. That verdict stands; this
is a different question with a different answer.

### 6b-original. The old framing, kept for the record `SUPERSEDED`
#51's settle covers **navigations**. A `browser_batch` of four observations after
a click all read the page before a ~300ms Bootstrap fade and came back empty on
a click that had worked. A fixed transition duration would be a chosen number;
the mutation signal from #70 may answer it properly, and that has not been
tried.

### 6b. A flow replayed against a LOCALISED app names no cause — CLOSED
The descriptor's identity rung IS the accessible name, so changing the app's
language invalidates every step at once. The playground already ships a `ja`
chaos flag whose own comment says "the whole descriptor design rests on the
accessible name" — and the failure surface had no entry for it.

Measured: a target recorded as `name='Sign in'`, replayed against a Japanese
render, reports *"no element on the page matches this step's target:
tag='button' name='Sign in'"* and nothing else, while the SAME failure at a
different viewport width appends *"The window is also a different WIDTH…"*.
The page declares the fact (`<html lang>`); the recorded half is missing, and
`Flow` has no `lang` field. `viewport` is populated by `mcp_server` at stop
time, so closing this needs a writer there as well as a reader in the runner —
both halves or neither (rule 14).

**CLOSED, both halves.** `<html lang>` rides `page_fingerprint`, the round trip
the caller was already taking — the same justification `vw`/`vh` shipped on —
so the writer costs nothing, and the runner's two notes now share ONE fetch
between them rather than one each (#38). The note follows `_viewport_note`'s
three rules exactly: no threshold, only on a resolve FAILURE where the reader
is already looking for causes, and a CAUSE rather than a diagnosis, because a
page can be translated without every name moving and a name can move for other
reasons (#33).

**Compared on the PRIMARY SUBTAG only.** BCP 47 makes `en-GB` and `en-US` both
English and a region switch does not retranslate a UI, so the full tag would
fire on a page that merely changed locale — the noise #15 priced, and the same
mistake the viewport note's HEIGHT half made until #59 corrected it. Caught
here before it could ship rather than after. FLG4 is that control.

A flow recorded before this existed carries `""` and makes no claim (FLG5).

### 7. Page-level scans and the iframe boundary `MEASURED -- DON'T BUILD`
**HALF THIS ITEM WAS WRONG and is corrected (#78).** Same-origin frames ARE
reached: `dialogOpen` queries `_allComposed`, which iterates `mmidReg`, and the
collection walk stamps mmids across same-origin frame boundaries; `_readinessPage`
already merges same-origin frames (#70/R19). The real decomposition is:
- **cross-origin frames are invisible to all three page-level scans.**
  `collectCrossFrames` runs AFTER the banner is built and merely appends rows, so
  no cross-frame dialog can ever raise it. Nine constructed fixtures (two ports,
  so cross-origin is real): a cross-origin CMP as a full-page fixed overlay gets
  NO banner, **0 rows flagged `(occluded/blocked)`**, and no dialog text — while
  the same-origin version raises the banner and names what it omitted.
- **`section=dialog` is on 0 rows in all 9 fixtures**, including the three where
  the banner correctly fires: an in-frame dialog's controls resolve to
  `section=iframe`. Extends #23's open `section=` item across the boundary.
- ~~same-origin geometry~~ **FIXED (#78, MV4).**

**FREQUENCY IS NOT ANSWERABLE ON THIS CORPUS, and the zero is verified real.**
42/96 sites have a child frame (128 frames), 17/96 have a RENDERED one, and
**0 of 128 declare any page-level trigger**. Probe firing confirmed by a control
over the same pages' TOP documents: 91 dialog nodes, 15 visible, 7 `aria-modal`,
6/96 raising the banner. The corpus cannot hold the shape because **HARs are
captured after consent**, 21/128 frames no longer replay, and the one CMP-shaped
frame present declares its `role=dialog aria-modal` wrapper in the TOP document.

**THE COST ASSUMPTION IN THIS ITEM WAS ALSO WRONG.** `collectCrossFrames`
already injects the collector into **27 of 33 rendered frames (81.8%)** on every
unscoped string read, so the per-frame round trip is ALREADY PAID — it just calls
the structured arm (no modal verdict) and appends after the banner. Per-frame
injection is median 14ms against a 66ms top-level collect. The "free"
same-origin-only variant reaches **12/33 (36.4%)** and misses exactly where CMPs
live.

**Do not build on this evidence** — #26's rule needs both halves and the benefit
half is unmeasured. What makes it answerable: re-freeze a corpus slice with
cookies cleared so the CMP shape exists, or a live pass. If it is ever built, the
design the cost data points at is zero-round-trip: have the existing per-frame
call return each frame's verdict and feed it back before the banner is built.
Probe: `tools/audit_frames.py` (`--fixtures` serves the 9 shapes from two ports).

**MEASURED 2026-11-18, AND THE ANSWER IS DON'T BUILD -- the shape exists and is
COMMON, and the gap does not occur.** `tools/audit_cmp_frames.py` ran the live
pass this entry asked for: 203 candidates, **143 measured**, fresh throwaway
profile, consent never given, through the real extension. **95 of 143 sites
(66.4%) render a cross-origin frame -- 710 frames -- and 0 of them carry a
dialog a frame-aware `dialogOpen` would fire on.** Blocking: 0. The gap itself
(a trigger with no banner): **0**, against a bar of >=5% of sites or >=20% of
sheet-showing sites fixed before the data was complete.

**The reason is architectural, which is why the zero is worth more than a
count.** 18 cross-origin frames DO block the page, and **17 of the 18 are
wrapped by a `role=dialog aria-modal` container in the TOP document** -- the
Sourcepoint shape, so the page-level scan already sees them and all 17 raise the
banner today. The consent CONTENT is behind the boundary; the dialog SEMANTICS
are in front of it. The 18th is an empty PerimeterX anti-bot overlay (0
characters, 0 controls), not a sheet.

**Geo is not what produced the zero:** 55 of 143 sites showed a visible sheet
(38.5%) from a non-EEA vantage point, so the conditional rate is **0 of 55**.
And the residue of sheets that get NO banner today -- 18 sites -- is **entirely
SAME-ORIGIN**, mostly bottom bars under the modality threshold. So what is
actually missing banners is a modality question in the top document, which this
change would not touch.

**And the fix is not free:** every incidental trigger is a page whose listing the
banner suppresses (#80 lost 150 of 150 entry slots on that mechanism), so a
change buying 0 real banners can only lose rows.

Drift: the 24 blocking sites re-measured in a second session, **24/24 identical
verdicts, 0 triggers**. What would reopen it: an EEA/UK vantage point, a vendor
that declares its dialog INSIDE the frame (none of the families sampled does),
or the shape appearing after an interaction (this is one read at first paint).
Full numbers, the probe-defect incident that produced a false zero before it was
caught, and the unmeasured set: `docs/research/CMP-FRAMES-2026-11.md`.

### 8. Coordinate trust on canvas-dominated pages `ACCEPTED`
On OpenStreetMap the same ref reported clicks 1,097px apart, and a missed click
hits the map, so there is no symptom. Refs re-measure and are safe; the printed
coordinate is not.

### 17. `find` is unbounded in query tokens x entries x fields `MEASURE FIRST`
> `find` scores every query token against every entry across every field, with
> no bound on either. Measured incidentally while #92 ran: **144 seconds** on
> ynet's 29,422-character `<body>` accessible name against 3,293 entries, and
> ~5s at 500 tokens.
>
> **Flagged, NOT called a defect**, which is the honest status: neither input is
> reachable by a query an agent would plausibly type. The long side comes from a
> blanked container's concatenated-paragraph identity, which is a probe's query,
> not an agent's.
>
> It is here because the cost model has a hole. #38 priced the model turn
> (~3,600ms), the bridge leg (~162ms) and collection (40ms–1.6s) and **never
> priced `find` itself**, so a tool that can take 144s sits inside a system whose
> published arithmetic assumes every server-side step is free.
>
> **What would settle it:** the distribution of real query lengths and entry
> counts from the eval transcripts in `tools/bench_turns/`, against which the
> tail is either unreachable (record it and move on) or not (bound it). Do that
> before adding any bound, because a cap chosen without the distribution is the
> kind of number #27/#28 removed from every deciding path.

### 16. `_flow_entries` does not say WHICH tab it read `MEASURE FIRST`
> The residue of #90's popup case: a tab the PAGE opened steals `active`, and a
> flow step that names no `tabId` then reads it. The explicit half is closed
> (recorded tabIds are checked at compile) and the declared half is closed
> (`target="_blank"` is read off the collector's own output). What is left is a
> popup that steals focus while **no call names a tab at all**, which
> `core/flows` structurally cannot see — it hands `tabId=None` down and gets a
> list back.
>
> **NOT BUILT, and the reason is the shape rather than the cost.** Making
> `_flow_entries` report its resolved tab is a PRODUCER; without a consumer in
> the recorder it is a declared field nothing reads, which is the half-contract
> this project has now deleted five times (`origin` #54, `viewport` #57,
> `on_fail:"heal"` #62, `delta` #30, the `pause`/`resume` pair in #70). Both
> halves or neither.
>
> **The design, so it is not re-derived.** `get_interactive_elements` returns a
> bare array, so the resolved tab is not in the response and adding it is an
> extension change plus a protocol shape change. The cheap route needs neither:
> when `tabId is None` — which is EXACTLY the ambiguous case — call the ungated,
> worker-side `get_active_tab` first and return a `list` subclass carrying
> `.tab`, so every existing `isinstance(ents, list)` and all list usage keep
> working. One extra round trip, only in the case that is ambiguous, at the
> ~24ms the bridge leg costs (#38) rather than the ~3,600ms of a model turn.
> The consumer is a review line when the resolved tab differs from the flow's
> starting tab.
>
> **What would close it:** both halves in one change, with a fixture that fails
> pre-fix (a recording whose active tab moves under it) and the control that a
> flow whose tab never moves acquires no review line.

### 21. `(post-key)` can be a STALE claim about where a name came from `MEASURE FIRST`

**Verified by hand, not inherited from a report: `__abSynthAttr` is set at
FIVE sites in `extension/background.js` and cleared at NONE.** It is a DOM
expando, so it survives between collector runs on the same document — the same
class #27 records for `_note`, where an overwritten expando survived a second
read and made the ledger report a reason decided by an earlier one.

**Why it matters more than it looks.** #41 added `(post-key)` so an agent could
DISCOUNT a name: the string shown is the HTML `name` attribute, i.e. the key
the form posts under, not a label a human wrote. A control that is read once
before its label exists — an SPA rendering it, a `<label>` arriving with a
fetch, a field unlocking — carries `__abSynthAttr` for the life of that
document. On every later read the name resolves correctly from the real label
AND the row still says `(post-key)`. That is a false provenance claim in the
one field whose entire purpose is provenance, and it points the wrong way: it
tells an agent to distrust a name that is now authored and correct.

**#113's label fix makes the population bigger, not smaller.** Before it, a
`<label>` wrapping an element child resolved to `''` and the row fell through
to the wire key — so controls that SHOULD have had a real name were getting
`(post-key)` legitimately. Now they get the label. Any control read in the
window before its label exists still acquires the expando.

**NOT FIXED, deliberately, and the agent that found it was right not to.**
Clearing it unconditionally at the top of each collection is the obvious move
and it is unmeasured in both directions: nobody knows how often a control is
read before its label arrives (the prevalence), and nobody has checked that
the five set sites all want the same lifetime. **What it needs is a TWO-READ
fixture** — read, render the label, read again, assert the marker is gone —
plus a prevalence number from the corpus. Both halves before it ships
(#41/#44's rule).

**The falsifier, so this is not re-opened on a hunch:** if a corpus pass finds
zero controls whose name provenance CHANGES between two reads of one document,
this is a latent defect with no instances and should be recorded as such rather
than fixed. `docs/research/NAME-RESIDUE-2026-11.md` section 9.

### 20. The Claude-in-Chrome arm cannot run — DEREGISTRATION CLEARED, a NEW block `BLOCKED ON THE USER`

> **UPDATE 2026-11-19: the deregistration is GONE.** After the user's reload,
> `list_connected_browsers` returns a live browser and `tabs_context_mcp`
> answers in normal time, where it returned `[]` three times before.
>
> **A different and narrower block replaced it, with its cause measured rather
> than guessed:** that extension cannot reach `http://localhost:8787`, where
> every fixture flow and the eval-14 task live. Its `navigate` reports success
> and then every page-touching tool fails with `Frame with ID 0 is showing
> error page`. The decisive control is in
> `tools/bench_turns/eval14/BLOCKED.md` — **same browser, same minute, same
> URL: ChromeBridge loads it and reads the page, Claude-in-Chrome gets an error
> page** — so it is not the fixture, the port, the host spelling, the network or
> the browser. The cause is NOT established: either that extension's own site
> access does not cover localhost, or Brave's localhost shield blocks it for
> that extension, and its failure renders as a network-error page rather than a
> permission message, which is exactly what makes the two indistinguishable
> from outside. **The symmetric unblock is the user granting it localhost
> access, as they grant origins for ours.**
>
> Moving the task to a public site is not a workaround: the four candidate
> public origins are ungranted for ChromeBridge, so that trades one block for
> another and changes the experiment as well.
> `tools/bench_turns/eval13` has one arm and no comparison because the other
> toolset never answered a single command — 8 calls, every one a timeout, 0
> productive. Four things were ruled out, each by a measurement rather than a
> guess:
>
> | ruled out | how |
> |---|---|
> | the app being down | no page was ever touched |
> | a permission refusal | ChromeBridge's are fast explicit messages, never timeouts |
> | the machine or Chrome being asleep | **ChromeBridge's `sw_info` answered in 7.6ms with `recent_timeouts: []`, same browser, same minute** |
> | browser selection | `list_connected_browsers` returned one local browser, `inUse: true` |
>
> **And it has since got worse, which is the useful part.** Re-checked ~40
> minutes later: `tabs_context_mcp` now reports *"Selected Chrome extension
> disconnected"* rather than timing out, and **`list_connected_browsers` returns
> `[]`** where it returned one healthy entry before. So the extension has
> DEREGISTERED, not merely wedged — which closes the last unexplored path, since
> `select_browser` has nothing to select. Everything reachable from this side has
> been tried: retry, the lightest op (`createIfEmpty:false`, which creates
> nothing and touches no page), the diagnostic, and re-selection.
>
> **Nothing on this side can evict an MV3 worker another extension owns.** It
> needs a hand reload at `chrome://extensions`. Recorded here so the next reader
> does not repeat the four calls that establish it.
>
> Worth keeping from the same run: `inUse: true` reads as a working channel and
> reflects REGISTRATION only — a browser can be registered, local and selected
> while its extension answers nothing. That was the one signal pointing
> optimistically the wrong way.

### 19. The fixture's edge-case LAB has no recorded flow at all `OPEN`
> `tools/saas_playground.py` serves `/lab/frames`, `/lab/shadow`, `/lab/virtual`,
> `/lab/confirm` and `/lab/popup` — the five shapes this project has spent the
> most effort on — and **not one of the 14 tracked flows touches any of them**.
> Every flow drives the ordinary app: login, table, modal, filter, sort,
> drill-down.
>
> That matters most for `/lab/virtual`. CLAUDE.md #90 measured a virtualised
> list binding to the WRONG record with NO refusal (recorded `REC-1003`,
> replayed `REC-1053`), because the crowd IS the window, its size is constant,
> and so the `len(hits) != of` composition check can never fire. #99 re-measured
> the declaration that would fix it and recorded **DON'T BUILD** — `aria-rowcount`
> on 0 of 2,531 tied crowds. So the hazard is known, priced and deliberately
> unfixed, and there is no flow that DEMONSTRATES it. A recorded flow against
> `/lab/virtual` would turn a paragraph into a reproduction.
>
> **NOT recorded now, deliberately.** Recording goes through the MCP server into
> the user's own Chrome, and at the time of writing BOTH halves of that stack
> are stale: the extension predates #97/#98/#101/#102, and `sw_info` reports
> `core/flows/descriptor.py` and `core/flows/secrets.py` changed since the server
> imported them. `build()` lives in `descriptor.py`, so the witnesses and atoms
> in a flow recorded now would be written by code that is not what ships — the
> "stale server writes a slightly older format" trap #59 paid three reconnects
> to learn. Record these after a reload and a `/mcp` reconnect, and check a
> saved artefact before trusting the result.

### 18. A navigate PASSED and the tab was `about:blank` one step later `OPEN`
> **CI-ONLY, ONE SIGHTING, NOT REPRODUCIBLE LOCALLY.** The `--chaos badge` arm
> of the flow replay failed on `live-atoms-resort` with:
>
> ```
> FAIL  live-atoms-resort            1/3 step(s) in 0.03s
>       step 1 (javascript_tool) raised: ChromeBridge cannot act on about:blank
> ```
>
> Step 0 is `navigate` to `http://localhost:8787/` and it **PASSED**. The whole
> flow took 0.03s, which is far too fast for a real commit.
>
> **What is already excluded, by reading rather than guessing.** The runner sets
> `inp["tabId"] = self.cur_tab` on EVERY step unconditionally, so steps 0 and 1
> ran in the same tab and the obvious wrong-tab theory is out. And
> `NAVIGATION DID NOT COMMIT` is one of the refusal markers the runner stops on
> (#62/FD19), so had navigate reported a non-commit the flow would have failed
> AT STEP 0 naming it. It did not: navigate claimed success.
>
> **So what remains is two possibilities nothing printed could separate:**
> navigate reported a commit that never happened (#40's class, under CI timing
> the #40 fix was not measured against), or the document went away between the
> two steps.
>
> **IT IS A FLAKE, AND THAT IS MEASURED RATHER THAN ASSUMED: re-running the
> SAME commit with NO code change came back green on all four jobs** (attempt
> 2 of run 44340479809). A re-run passing is the only evidence that
> distinguishes a flake from a deterministic CI-only defect, and it is worth
> more than any amount of local passing.
>
> **Not reproducible:** `--playground --local-only --chaos badge` is **12/12
> locally including this flow**, and the flow alone under the same flag is 3/3.
> The chaos arm itself is working — `acme-nav-badge` passes in the same CI run
> and reports `name 'Projects 4' is gone; matched href='/projects'`, which is
> #61's fallback doing exactly its job — so this is not the badge chaos.
>
> **Per #50 it is not guessed at; it is made to leave a trace.** A raise now
> carries what the step before it returned, so the next occurrence reads
> `... raised: ... [step 0 (navigate) had returned: Navigated to ...]` and says
> on its face which of the two it is. Pinned by FR29, with FR29b the control
> that a raise on step 0 claims nothing about a step before it. **Do not
> "fix" this from the two theories above — wait for a sighting that carries
> the navigate's own words.**

### 9. Three unreproducible 30s+ stalls `OPEN`
> **A FOURTH, CAUGHT LIVE 2026-11-18 WITH THE EVIDENCE #50 BUILT FOR IT.**
> Previous sightings were memories. This one arrived with its op and its
> neighbours, because `sw_info`'s timeout ring did its job:
>
> ```
> recent_timeouts: [{op: page_fingerprint,          after_s: 30, ago_s: 39.5},
>                   {op: get_interactive_elements,  after_s: 30, ago_s:  4.9}]
> ```
>
> **What was measured, in the order the timeout message itself prescribes:**
> `sw_info` answered in **5.9ms**, the worker was the same id at 141s and had
> NOT been evicted, `get_url` on the stuck tab returned the correct url and
> title instantly, and `dismiss_dialog` reported `no_dialog` — so it is not a
> blocking dialog, not a dead extension, and not a worker restart. Every
> page-INJECTING op into that one tab was stuck while everything worker-side
> answered. That is the shape the message describes, and this is the first time
> all four probes were run on a live instance.
>
> **The new fact, and it narrows the search away from the extension:** a
> SECOND, freshly created tab navigated to the SAME origin also landed on an
> error page (`title: "localhost"` — Chrome's url-display fallback, #42's
> shape) **while `curl` to that origin returned 200 from the shell**. So at the
> moment of the stall, Chrome could not load a page that the server was serving
> fine. Whatever this is, it is not confined to the already-wedged tab's
> renderer and it is visible to a tab that never ran any of our code.
>
> **Recovery:** closing the wedged tabs and creating a new one restored normal
> service immediately — clean load, full listing, no reload of the extension
> and no restart of the server. **Stated carefully: the new tab was created
> AFTER the close, so "closing it fixed it" and "a few seconds passed" are not
> separated by this observation.** Do not record the close as the cure.
>
> **What would close this:** the next sighting should additionally run
> `debug_targets` (is a foreign CDP session on that tab?) and `curl` the origin
> from the shell AT THE SAME MOMENT rather than afterwards, since the curl here
> was taken after recovery had begun. Both are one call each and neither was
> taken this time.
Every page-injecting op hangs together while `get_url`/`sw_info`/`navigate`
answer in milliseconds — a blocked page main thread rather than a dead
extension; navigating recovers it. Not reproducible across four attempts. The
bridge's timeout ring (#50) now gives the next sighting its evidence. **Cannot
be fixed by guessing at it.**

---

## Tier 3 — measurement debts

### 10. Which Mind2Web positive we score against `MEASURE FIRST`
The headline itself was audited in #73 and **stands** (~96%, reproduced three
ways, zero label defects across 186 actions). What remains is upstream of it:
`fetch_mind2web.py` keeps only **`pos_candidates[0]`**, and the original ~590MB
shards were not retained. If Mind2Web marks several nodes positive per action,
our ruler uses one of them and may be stricter or looser than MindAct's.

**This is the largest unaudited choice in the measurement spine** and it sits
under every number derived from it. Closing it means re-downloading from
HuggingFace.

**CLOSED — the three small debts #73 left.** The false comment is gone, the
snapshot is repaired before it is rendered (`tools/_m2w_ruler.py`), and the
ancestor credit path carries the same area bound as the descendant path. One
denominator now, all 186 actions: **177/186 = 95.2%**, exact 161/186 = 86.6%.
`--no-repair` reproduces the pre-#73 arm (166/173 = 96.0% of the targets that
resolved) so both figures stay obtainable from the tool rather than from memory.
Three things #73 got wrong, each found by running rather than by arithmetic:

- the repair "fixes the ikea credit for free" is true only of the FAITHFUL
  repair (every non-void self-closed tag), not of the RAWTEXT-only one that
  yields the 96.2% #73 headlines — so the two sentences in its closing
  paragraph cannot both hold;
- "mirroring the cap gives 165/173 = 95.4%" is **166/173 = 96.0%**: refusing an
  ancestor credit is not losing the row, and that one falls through to the
  target's own `<input>`, which is sound by bubbling. **The bound costs zero
  recall on either arm** and removes the one credit #73 called false;
- the minimal repair also leaves two further ancestor credits standing
  (sixflags, underarmour) whose "wrapping anchor" the raw bytes show is a
  self-closed `<a … bounding_box_rect="-1,-1,-1,-1"/>` — empty and rendering
  nothing in the original page.

The faithful repair was chosen on a signal independent of recall: it is the only
arm with **zero cloned nodes** (the unrepaired parse re-creates unclosed
formatting elements, emitting several DOM nodes under one `backend_node_id` on
**137 of 186 samples**, up to 2.48×), and it never recovers fewer distinct ids
than the other arms. Residue, stated: a median 99.8% of each snapshot's ids
parse, worst 43.4%, because Mind2Web nests a frame's whole document inside the
`<iframe>` element. No labelled target is among them.

### 11. No task-success measurement for our own ladder — A ROUTE EXISTS `MEASURE FIRST`

**A SECOND ROUTE, found by the 2026-11 survey (`docs/research/SURVEY-2026-11.md`):
ComponentBench, [arXiv:2608.18307](https://arxiv.org/abs/2608.18307), COLM 2026,
code and data released.** 2,910 tasks over 97 canonical component types from the
widely used component libraries, shipped as GENERATED interactive Next.js apps —
deterministic and replayable — each with a PROGRAMMATIC oracle rather than an LLM
judge, and **target values hidden in React closures**. That last detail is what
makes it worth more than WebPageBench for this particular question: it fixes all
three things that defeated #75's attempt on Mind2Web at once — the leaked answer
(Mind2Web's `backend_node_id` ordering put the gold target anomalously early, and
a blind judge found it three for three), the missing CSS, and the stripped step
values. Its headline is that observation/action space ALONE moves success by more
than 30 points (GPT-5 mini 83.1% AX-tree → 48.9% pixel-only), and four arms are
already implemented including browser-use.

~~And it is centred on exactly the Radix / shadcn / HeadlessUI / MUI families this
project was built around — fix #1 in CLAUDE.md exists because Radix gates on
`pointerdown`.~~

**VERIFIED AT SOURCE, and two sentences above are REFUTED.** See
`docs/research/COMPONENTBENCH-VERIFICATION-2026-11.md` and
`tools/audit_componentbench.py` (exits nonzero on any failed claim; `--self-test`
plants five violations and catches all five). What CONFIRMS: 2,910 / 912 tasks,
97 canonical types, 14 families, a genuinely programmatic oracle
(`benchmark/core/task.py` imports no model client and never reads
`chat_messages`), benchmark mode rendering no goal text, the task API stripping
the answer key by default, and the success predicate as a literal in the React
component. What is REFUTED:

- **It ships Ant Design (1,000), Mantine (970) and MUI (910). Radix, shadcn and
  HeadlessUI are ABSENT from `site/package.json`.** Only MUI overlaps. The
  conclusion survives for a better reason — antd is the family behind our worst
  dropdown failures (#25, #29, #97, #98) and is 34% of the set, so the
  relevance is adversarial rather than familiar — but the sentence was wrong.
- **It DOES carry per-step ELEMENT ground truth**, undocumented, in
  `runs_lite/human0_20260312_clean/episodes.tar` (14.7 MB): **7,773 steps over
  2,910 episodes**, each with the target's tag / id / classes / data-testid /
  role / name / bbox, plus the step VALUE on all 764 `type` steps — the field
  `SUCCESS-RETENTION.md` records Mind2Web's loader discarding. 3,976 of 5,817
  click+drag steps carry a testid or a name, on 2,191 of 2,910 tasks. The
  released `data/human_traces/*.jsonl` carries only counts and kinds, which is
  why reading the repo answered "no".
  **It is NOT usable as-is:** all 7,773 steps were recorded in
  `mode=presentation` at four viewports, none of them the harness's 1280×720,
  so a ruler must RE-RESOLVE by identity. Measured statically, 83.0% of
  identifiable targets have their testid or name in the rendering component;
  **59.7% carry a name that survives the production build**, which is the key
  that matters because `next.config.js` strips `data-testid` in production and
  production is the documented evaluation path.

**READ §3 OF THE PAPER BEFORE PLANNING AN ARM.** `data-testid` is present on a
dev build and stripped in production, and #23 has us presenting testids as
attributed names — so a dev-build arm reads `antd-btn-generate-report` where
the AX-tree arm reads nothing, which the authors' own comment calls cheating.
Dev mode also pays a 1–2 minute compile per task page.

**Feasibility: one arm, modelled on `scripts/browser_use/run_and_pack.py` (a
standalone 827-line script, not a BrowserGym mode).** Oracle is
`query_elements("#cb-success-banner")`, so unlike every published arm ours
needs no API key. Self-hosted on `localhost:3002`, so the gate is granted in a
throwaway profile exactly as `run_flows.py` does. Estimated ~2.5 h serial per
arm over 278 tasks; ~1.5–2.5 GB of `node_modules` (estimate, not measured).
**Do not clone the HuggingFace dataset: 86.3 GB.** The subset to pre-register
is shipped: `site/src/recording-subset-278.json`, 278 ids, one per
(canonical_type × library), seeded, with a stated difficulty deviation — the
same set the human traces were recorded against.

**One figure to NOT import.** A search summary attributed "17.3% of tasks
flipping between identical runs" to ComponentBench; the surveying agent checked
the paper and **that figure is not in it**. The verification probe checked the
ARTEFACT and the string `17.3` appears nowhere in it either. Do not place it
beside [arXiv:2608.06171](https://arxiv.org/abs/2608.06171)'s measured 12–14%
rerun noise floor as if it were a second data point.
`detail` and `format` are priced on recall and tokens, never on end-to-end
success with a strong model.

**"The literature disagrees with itself" was wrong and is withdrawn (#78).**
Verified at source: EconWebArena's −10.2pp arm is **o4-mini**, and its 36.7%
figure is labelled `- use_ax_tree + use_html`, i.e. raw HTML *replacing* the
AXTree. A small reasoning model degrading on raw HTML is exactly what
[arXiv:2604.01535](https://arxiv.org/abs/2604.01535) predicts. Both support ONE
capability-dependent model, and 2604.01535 raises the format confound itself and
controls it — the effect survives, and is *larger* under indentation (+20.9),
which is our format.

**THE ROUTE: WebPageBench ([arXiv:2609.35026](https://arxiv.org/abs/2609.35026),
Apache-2.0).** Verified from the released artefact rather than the paper
(`tools/audit_webpagebench.py` exits nonzero if any claim fails and self-tests
against three planted violations): 152 tasks / 65 canonical + 87 variants, 6
sites, 19 event types, 521 conditions, all exact; **no judge model** — `check()`
imports only `requests/os/json/re/datetime` and the oracle is a semantic event
emitted by business logic AFTER the state mutation, so it cannot see how the
agent acted or what it was shown; and the control swap keeps prompt AND success
conditions **byte-identical on 87/87**. Design in `docs/WEBPAGEBENCH.md`.

**Caveats that must travel with any number from it.** It is a **v1 preprint, 5
authors, no venue, not peer reviewed**. It is a **Russian-language benchmark** —
152/152 prompts are Cyrillic, which no description of it mentioned. The sites are
**synthetic**, which is the real missing leg; it is softened but not removed by
the fact that our only out-of-sample number today comes from stripped static
snapshots with no CSS and no scripts. Per-step element ground truth is **absent**
(end-of-task only), so this measures SUCCESS, not element recall. Hotels is 30%
of the set, so leave-one-site-out is mandatory.

**Build M-B first even though M-A is the question as asked**, because it needs
one arm instead of two: the same task re-rendered through a different date
picker or combobox, with identical success conditions, which is a direct test of
"works on framework-heavy SPAs without site-specific code". **The benchmark
ships its own negative control** — 12 `theme_dark` variants change colour only,
so a structural representation must score identically on them; if dark theme
moves the number, the instrument is wrong before any result is believed.

**The confound to design out:** our surface has escape hatches. An agent that
reaches the state via `javascript_tool` or by typing a URL measures Claude's
ingenuity, not the listing. Pin the toolset and report the fallback rate beside
every number, as #27 pinned `filter="interactive"`.

**THE SITE IS UP AND BOTH UNVERIFIED ITEMS ARE NOW CHECKED (#79).** The oracle
fires end to end (`Added event: event_name=state_changed`, `POST /event/add
200`, from a plain page load). The `href` prediction was HALF WRONG and it
narrows the measurement: hrefs exist, so Mind2Web's 0-of-40 collapse does not
reproduce, but they are distributed INVERSELY to aria by domain — books and shop
have **0 anchors and 37–43 aria-labels**, hotels and rail have **12–18 anchors
and 1–3 aria-labels**. So the `detail` ladder is measurable on at most 2 of 6
domains, which is #73's Mind2Web finding reappearing in the benchmark chosen to
escape it. `format` is unaffected.

**FIRST RESULT, and it is the instrument check rather than one of the three
measurements: 12/12 theme pairs, 0 changed lines, same-arm floor 0**
(`tools/measure_wpb_invariance.py`). The listing is byte-identical under a
colour-only change on every pair across all six domains. Narrow and stated
narrowly — it establishes that the representation does not read COLOUR, not
invariance to the other eight control keys, which is M-B. The 0 floor is a
second result: these pages render deterministically, so later measurements have
no drift to subtract.

### 12. Sufficiency: the TEXT half is now MEASURED `OPEN`
The CONTROL half was already closed: **`DS | reachable` = 0.933**, LOSO
0.921–0.951, both negative controls passing, the accessible name carrying
51.7pp and the tree's ancestry path 11.2pp.

**THE TEXT HALF IS NOW MEASURED** (`tools/measure_text_flows.py`,
`SUFFICIENCY.md` §10). It is the half the source paper ranks FIRST (30.5 / 59.5
coverage drop when ablated, against 4.8–13.6 for any control type), and it was
unmeasured because a static page load cannot tell "the text surface failed to
carry it" from "the value did not exist yet". The route through the flow
recorder — replay to the step before the answer, then ask — closes that, and
`run_flow(stop_after=N)` became usable over the wire only this session.

| | live corpus |
|---|---|
| required values scored | **1,133** (985 prose, 148 table rows) |
| TEXT-DEPENDENT (controls-only listing does not carry them) | 1,047 (0.924) |
| **TS — carried by SOME text surface** | **1,047 / 1,047 = 1.000** |
| lost by every arm | **0** |

Per arm over the 1,047: `read_page(filter="all")` 0.983 · `search_page` 0.841 ·
`query_elements` 0.764 · `get_page_text` 0.761 — **and `get_page_text` at a
raised budget 1.000.** Every shortfall at default settings is the caller's
BUDGET and nothing else: 250 values missed at the 30k default are carried at
250k, **0 missed at both**, and the tool says so (`body truncated at 27225 of
62148 chars … spent as 27225 body + 332 readiness banner + 1834 outline`).

Drift floor **0.00%** on all seven verdict fields over two replicates, both
corpora. Live states come from the 8 `ev-*` recordings made by agents in
#63/#64 who were told nothing about any text measurement, plus todomvc — which
is the answer to "you chose the states". Stopping happens at EVERY step index,
deduped by content hash, because choosing the stop point is choosing the sample.
"Text-only" is measured per item as absence from `read_page(filter="interactive")`,
not asserted.

**WHAT KEEPS IT OPEN, and the first is the big one:**
1. **Not task-weighted.** Items are everything the page renders, a superset of
   what a task needs. Same bound item 2 accepts for DS, and the larger gap.
2. **Association is measured and is NOT 1.000.** Ordered-correctly in
   `read_page(all)` 139/148 = 0.939; the scoped aligned renderer 129/148 =
   0.872. The table half of the paper's "Text" row lives here, and presence does
   not measure it.
3. **The discovery path is narrower than the tool.** The data-table hint names
   the first 6 of jawiki's **44** tables, and it is the only route to the
   aligned renderer, which scores 0.885 once reached.
4. **20 live states, one page a fifth of them**, and 1 in 5 replays lost to five
   weeks of site drift.

**FOUR PROBE BUGS, THREE OF THEM DAMNING THE SYSTEM — LOST went 55 → 34 → 0 and
every step was the ruler**, which is this project's most repeated lesson landing
on its newest measurement. (a) `search_page` misses were detected with
`startswith("No match")` and the miss path PREPENDS the readiness note (#39), so
every miss read as a hit — the nonce control caught it on its first run. (b) A
table row had to be recovered on ONE LINE, and 44 of the 54 rows scored LOST had
a cell whose own text spans lines: unrecoverable by construction. (c) The
data-table hint regex anchored on `page:` while the hint reads `…on this page,
first 6 by document order:`, so the scoped arm was EMPTY and #26's renderer
scored 0 on the only state with real tables. (d) `innerText || textContent` in
the sweep invented values Chrome does not paint (#37).

### 13. The browser-use A/B measures a path that is no longer theirs `RETIRE THE FRAMING`
The 84.5%-junk figure (#33) was measured against their `ClickableElementDetector`.
**Confirmed by reading their current source (#78): the AX-tree path is now the
DEFAULT** — their README documents `mode='ultrafast'` acting on accessibility-tree
ids as the default on `bu-fast`, and `bu-fast` is their stated default. So this is
past "going stale": the comparison describes code that is no longer the thing it
names, and **re-running it would measure the same obsolete path again.**

The CONCLUSION is unaffected and still earned — we did not import their admission
rules, and the measurement of why is in #33. What must stop is the FRAMING "we
are more disciplined than browser-use about existence", which is now a claim
about a path they do not take.

**One thing from their current source is worth more than the re-run would be:**
they split opacity BY PURPOSE, with a reason on each side — `checkOpacity: true`
for the text surface, because "the AX tree keeps opacity:0 text (pre-rendered
success banners), which agents then report as success", and OFF for action-target
validation, because "custom-styled widgets often keep an opacity-0 native select
underneath". That is the distinction item 14 was reaching for, and our own
measurement found **0 of 434 sampled opacity:0 strings matching success/error
vocabulary** — so their stated hazard has zero instances on our corpus while
their counter-case (the hidden native control) is exactly what our
`_declaredCtl` exemption already rescues.

### 15. What our 31 tool schemas cost at session start `MEASURE FIRST`
Playwright MCP's own README now steers people toward CLI+skills over MCP on
token grounds. That is Microsoft's assertion with no published measurement, and
#38 says turns dominate tokens — but we have never measured our own schema
prefill.

---

## Settled — do not re-open without new evidence

- **Off-viewport admission.** +6.9pp first-read reachability for +18.7% tokens,
  **70% of the spend on tasks that gain nothing**, and the waste fraction does
  not move under two narrower predicates (#44). Three independent 2026 results
  now agree the problem is not that the model cannot see off-viewport content
  but that it does not execute the reveal — IGG measures **+3.1pp for telling
  the agent vs +48pp for doing it for it**, which is the sharpest argument for
  the region hint and against "scroll down".
- **browser-use's admission rules** — 84.5% of the gap is `cursor-pointer` and a
  10–50px icon rule; their own samples include a Hacker News rank number.
- **The Chrome AX tree** — 7.15× tokens for 4pp recall, and needs an attach that
  #12 proves gets refused on password-manager pages.
- **`find` for goal→element** — 0% with a human's task phrasing. That is
  semantic inference, not retrieval.
- **`id` / `data-testid` as a descriptor rung** — 6.8% / 2.5% coverage, perfect
  where present. Reopens only with a corpus of the internal apps this feature
  actually runs against.
- **Self-healing locators.** Unanimity across independent models is a valid
  signal for *which surviving element is this* and **actively anti-correlated**
  for *does it still exist*: 34/34 unanimous verdicts on deleted elements were
  **false heals**, and growing the model pool 3→7 did not reduce it. Keep the
  absence test structurally separate from the identity test. Never let a
  fallback rung answer "it's gone".
- **MHTML for corpus freezing** — 0% element retention.
