# Readiness — "accurate at any stage"

**Status: OPEN. This is the one structural gap in the representation.**
Everything else in `REPRESENTATION.md` is about describing a page correctly.
This is about knowing whether *this instant* is one worth describing.

History: CLAUDE.md #15 (the probe), #23, #25 (shadow-blind), #30 (three signals
dead in production), #43 (`readyState` demoted), #51 (navigation settle), #64,
#65 (resource types).

---

## 1. The complaint, in the words it arrived in

Five independent live agents across two eval rounds reported the same thing:
the readiness banner **cannot separate "page still building" from "page ready
but chatty"**. One reported it firing after an explicit 3-second wait on content
that was complete and verified. One reported MORE requests in flight on the
usable read than on the blank one.

That is two opposite failures, and they have one cause:

> **We measure the network. The agent's question is about the DOM.**

The agent is not asking "is the network idle". It is asking **"if I wait, will
what I am reading change?"** Those come apart in both directions on any
single-page application.

## 2. Both failures, reproduced

`scratchpad/probe_false_negative.py`. Two synthetic pages, each the minimal
shape of a real complaint, interrogated at four moments with every signal asked
at once.

**A — still building, network silent.** One fetch that resolves immediately,
then 400 rows painted over ~2s in `setTimeout` chunks, exactly as a framework
commits in slices.

**B — ready but chatty.** 400 rows painted synchronously and finished, then a
120ms poll and a 200ms beacon keeping requests permanently pending.

| scenario | rows painted | `readyState` | aria-busy | progressbar | **net in flight** | **ms since DOM change** | mutations/500ms |
|---|---|---|---|---|---|---|---|
| A @300ms | 64 / 400 | complete | 0 | 0 | **0** | **18** | 334 |
| A @900ms | 192 / 400 | complete | 0 | 0 | **0** | **9** | 512+ |
| A @1500ms | 316 / 400 | complete | 0 | 0 | **0** | **18** | 512+ |
| A @3500ms | **400 done** | complete | 0 | 0 | 0 | **1622** | **0** |
| B @300ms | **400 done** | complete | 0 | 0 | **3** | **304** | 43 |
| B @900ms | 400 done | complete | 0 | 0 | **5** | **907** | **0** |
| B @1500ms | 400 done | complete | 0 | 0 | **5** | **1511** | **0** |
| B @3500ms | 400 done | complete | 0 | 0 | **6** | **3514** | **0** |

Read the two highlighted columns against each other.

**Every signal we ship today is silent through all of scenario A** — the agent
is handed a 64-row table that is going to become a 400-row table, with no
caveat of any kind. And **every signal we ship today fires through all of
scenario B**, on a page that was finished before the first observation, for
ever. An always-on warning is the noise CLAUDE.md #15 priced and #43 deleted
`readyState` for being; we reintroduced it one signal over.

DOM-mutation recency separates them with **no overlap**: 9–18ms while building,
907–3514ms when done. Any cut between 50 and 500ms works, which is the point —
**we do not have to pick one, because we report the number rather than a
verdict.**

## 3. Is it affordable, and is the signal real on real pages

`scratchpad/probe_mutation_cost.py`. Interleaved A/B on the same page load,
three replicates, order rotated, drift control first (CLAUDE.md #19).

**Cost** — a document-wide `MutationObserver` with `subtree: true`, recording a
timestamp and a coarse target identity, bounded to a 32-record prefix per
callback:

| synthetic churn | no observer | observer | overhead |
|---|---|---|---|
| 200 mutations | 1.3ms | 1.2ms | −7.7% |
| 2,000 mutations | 14.2ms | 13.4ms | −5.6% |
| 10,000 mutations | 78.2ms | 83.0ms | +6.1% |

Drift control (same arm twice): **2.4% floor**. Re-measured against the shipped
file with 9 replicates and a 1.7% floor: **+0.10ms / +1.40ms / +2.70ms** at
200 / 2,000 / 10,000 mutations.

**It is not "free at any rate", which is what this said first.** Re-derived
further out by an independent audit: **+63ms at 40,000 mutations in one batch**,
against a 0.0% A/A drift floor at that size. The cost is **superlinear** — 4×
the mutations for 17× the cost — and a 2,000-row grid render reaches it. It
stays a caveat rather than a refutation for two measured reasons: an
**empty-callback** observer with the same options costs essentially the same at
40k, so this is the inherent price of a document-wide subtree observer and not
of our callback; and +63ms is **1.7% of a model turn**, so the conclusion
survives even though the wording did not.

**And so is the per-read query**, which is a separate claim and was separately
measured — "the observer is free" says nothing about the scan every observation
now runs (1,024 ring slots plus a same-origin frame walk). At ring saturation
(3,009 recorded mutations, saturated buffer, one child frame), over 60 calls:
**median below Chrome's 0.1ms timer granularity, p95 0.1ms, max 0.4ms.**

**Signal on real pages** — cumulative mutations counted in windows after
DOMContentLoaded:

| site | 250–500ms | 500–1s | 1–2s | 2–4s | 4–8s |
|---|---|---|---|---|---|
| news.ycombinator.com | 0 | 0 | 0 | 0 | 0 |
| github.com (issues) | 0 | 0 | 0 | 0 | 0 |
| react.dev | 0 | 0 | 1 | 0 | 0 |
| theguardian.com (ad-heavy) | 1 | 0 | 2 | 7 | 0 |

HN did 1,302 mutations during load and then **stopped dead**. GitHub did 3,072
and stopped dead. The contrast between "building" and "settled" is roughly
**100×**, and all four of these pages have network requests in flight the whole
time — which is precisely the false positive we ship today.

## 4. What the Guardian row proves, and it is the important one

7 mutations in a 2–4s window, from advertising. Document-wide
"ms since last change" would read ~200ms on a page that is **entirely
readable**, and we would have rebuilt the same false positive in a new unit.

So recency alone is not the answer. **The attribution is load-bearing**: a clock
in a header and a table rebuilding are the same number and opposite facts. The
signal has to answer *"has the part I am about to describe stopped changing"*,
not *"has anything on this page stopped changing"*.

This also makes it compose correctly with scoped reads, which are already the
recommended way to reach deep into a page.

## 5. The design

Three parts. Nothing in it chooses a threshold, waits, or costs a round trip.

**(a) Record, at `document_start`, in the MAIN world.** `listener_tag.js`
already wraps `addEventListener` and `attachShadow` there, which is the same
move for the same reason — you cannot observe mutations that happened before you
installed. A ring of `{timestamp, WeakRef(target)}`, bounded, with a 32-record
prefix per callback so a burst costs 32 and not 10,000.

**(b) Attribute at read time, not at record time.** For a scoped read, walk the
ring, deref, and test composed-tree containment against the scope. For an
unscoped read, attribute each to its nearest landmark. 512 derefs and
`contains()` calls is microseconds, and it keeps the hot path (the observer
callback) doing nothing but a timestamp.

**(c) Report the measurement, never a verdict** — and in **two tiers**, decided
by the three `MutationRecord` types, which the spec declares so no list of
"important" attributes is needed.

| what was measured | what is said |
|---|---|
| `childList` or `characterData` in the window | **THE DOM IS STILL CHANGING** — elements are being added, removed or re-texted, so do not conclude absence |
| attributes only | **Minor DOM activity** — nothing was added, removed or re-texted, so the listing is structurally current. The attribute *names* are printed |
| DOM quiet, network busy | **DOM STABLE, NETWORK BUSY** — what is rendered is not being rewritten; whether more arrives is what those requests decide |
| both quiet | **nothing at all** |
| **no recorder at all** | the pre-#70 **PAGE IS STILL SETTLING** banner, unchanged |

That last row is the degradation path and it still ships: when
`listener_tag.js` did not run (a page open since before the extension was
installed or reloaded), there is no recency reading, so the old network-only
banner is used verbatim. **Unknown is never rendered as quiet** — `R17` pins the
probe reporting `null`, and the branch guard keys on `since >= 0` rather than on
`total >= 0`, because an empty ring returns `since = -1` and that is "never
observed", not a duration. The first version printed `No DOM change for -1ms`.

**The two tiers exist because the first version rebuilt the bug it was fixing.**
A banner keyed on "anything moved" fires forever on any ad-supported page —
theguardian.com's ~7 mutations per 2s make `moved > 0` permanently true, so a
perfectly readable page is permanently told it may be incomplete. That is #15's
always-on warning, reconstructed one unit over. Caught by measuring the ad case
*before* shipping.

Attribute names are printed rather than filtered because `@style` on a carousel
and `@disabled` on a form unlocking are both attribute-only and need opposite
responses. The reader can tell them apart from the name; we cannot.

This is the same move as #65's resource types and #60's recorded `settle_ms`:
state what was measured, leave the judgement with the caller. It replaces a
sentence that asserts readiness — which is #33's class, and which `C15` exists
to catch.

**(d) Merge same-origin frames.** `listener_tag.js` has `all_frames: true` so
every frame keeps its own ring, and `runInTab` passes `allFrames: false` so the
probe runs in the top frame only — the child rings were written and never read.
A page whose content lives in an iframe therefore reported **quiet** while that
frame painted. `since` merges by **minimum**, because it is "ms since the last
change" and taking the max would report the quietest frame, which is this bug
again pointing the other way. Cross-origin frames stay unreachable and are **not
counted as quiet**: the walk yields only what it can read, so a consent CMP
churning cross-origin is a stated limit rather than a silent zero.

### What this does NOT do, deliberately

- **It does not wait.** A bounded wait for a first quiet window is a separate,
  later question and would need its own pricing against #38's arithmetic (a
  model turn is ~3.6s, so a 500ms wait is cheap — but a wait that fires on every
  read is not). Retrospective recency needs no wait at all and should be built
  first.
- **It does not replace the network signal.** In-flight requests with their
  resource types (#65) answer a different question — *is more data coming* — and
  a page can be DOM-quiet while still fetching the rows it will paint. Both
  facts get reported; neither is a verdict.
- **It does not decide.** There is no `ready: true`.

### The constraint it must respect

`listener_tag.js` is a manifest content script and **injects into every page
before any grant** (CLAUDE.md #17). What runs pre-grant today is bounded and
documented, and **has now been updated in `README.md` and CLAUDE.md #17 to
include this recorder** — it was stale in three places for several hours and an
independent audit found it, which is the failure this paragraph predicted. The
pre-#70 bound was the `addEventListener` wrap, the `attachShadow` wrap and a
500-entry console ring. A
mutation ring is the same class — it stays in the page, and reading it is
gated — but **the README's statement of that bound must be updated in the same
change**, or we have a documented guarantee that is quietly false.

## 6. Prior art — and the one finding that corrects our framing

Researched Nov 2026. Full survey in `RESEARCH.md`.

### The complaint is a property of the commercial web, not a defect in our probe

**"What Does 'Now' Mean to Your Computer-Use Agent?"**
([arXiv:2610.39282](https://arxiv.org/abs/2610.39282), 29 Oct 2026). 31 public
pages, ~1,300 targets per state. A click is "stale" if the target moved,
vanished or was covered by the time it landed.

| | stale clicks |
|---|---|
| fully loaded page | **0.4%** |
| at DOM-ready, within 1s | **17%** |

Wait rules, reimplemented from ten agents' source: no wait 14.4%, fixed 0.5s
2.5%, load event 3.0%, layout-stable 2.8%, boxes-stable 1.8%, **network idle
(no requests for 500ms) 0.46%** — the only rule under 1%.

**So network idle is the best settling predictor measured, which is the opposite
of what I assumed when I started.** What makes it unusable is not accuracy, it
is arrival: quiet is reached within 3s on only **15% of booking/buying home
pages** and 19% of e-commerce, median time-to-quiet 7.4s. Five agents told us
the banner never clears on real apps; this says that is the web, not us.

Two consequences for the design above:
- **The network signal is not demoted and must not be.** Reporting both facts
  separately (§5c) is right; replacing one with the other would have been wrong.
  Our implementation reports both, with the DOM-quiet case stated as *stable to
  read now* rather than suppressed.
- **The stale-click numbers justify #51's post-navigation settle to the digit**
  (0.4% vs 17%), which was built on reasoning.

**Read it with its own caveats, which are large:** v1 preprint, unreviewed,
single author, 31 non-commercial pages, three days, one browser. The author
preregistered fourteen hypotheses and **eight were refuted**, including its own
crawl→stale transfer check (Spearman ρ = −0.12, CI −0.56 to 0.32). Its text says
"eight of ten" agents exceed 1% stale while its table shows nine. **Do not set a
threshold from its numbers without re-deriving on our own corpus.**

### The architectural correction: the gap that matters is at the ACTION, not the read

The paper's own conclusion is to stop perfecting the wait and add a cheap check
immediately before acting. Measured on 1,064 stale clicks: a pixel check at the
target position detects 82% at 4% false alarms in 312ms; a frontier model 83% at
12% in 2.4s. In a live loop it cut stale clicks from 65–69% to 9–11%.

Its break-even formula gives p* ≈ 10% for an ordinary click and **≈1.2% for an
irreversible one** — which maps directly onto `fill_form(submit=True)`.

**"Atomicity for Agents: ... TOCTOU Vulnerabilities in Browser-Use Agents"**
([arXiv:2603.00476](https://arxiv.org/abs/2603.00476), 28 Feb 2026) measures the
same gap as a correctness bug: **all 10 evaluated open-source browser agents
vulnerable, 100% trigger ratio**, and a prompt-only mitigation gave no
improvement. Their fix is a MutationObserver extended into shadow roots and
same-origin iframes, **plus a ResizeObserver** on visible elements, running
*during planning* and aborting if any records exist at execution time: **0%
trigger across 14 cases, <0.05s overhead.**

> **This is the next piece of work, and it is bigger than the banner.** We
> re-measure refs at click time but never compare what is there now against what
> was observed. #51's `page_fingerprint` ref-resolution check is the machinery,
> and the two things we do not do are the **ResizeObserver** (an overlay that
> shifts a box without touching the DOM is invisible to a ref check, and
> `(occluded/blocked)` is computed at listing time, not action time) and
> observing **continuously through the model turn**, which at ~3.6s (#38) is the
> whole exposure window.

### What others ship

| | settling mechanism |
|---|---|
| `chrome-devtools-mcp` v1.13.0 | MutationObserver on `document.body`, debounced 100ms, 3s cap. **No network signal at all.** Ignores `sameDocument` navigations — our #64 finding, same conclusion. Its code comments name the paused-renderer/dialog hazard, which is our #51. |
| browser-use `ax.py` (Nov 2026) | `settle(cap_ms, quiet_ms=80)`: `readyState != loading` AND DOM quiet AND network not busy. **Ignores in-flight requests older than 1.5s** as long-poll/analytics — their answer to "ready but chatty". Exposes `loading: N` to the model. |
| Playwright MCP 0.0.85 | a fixed `--timeout-settle`, **default 500ms** — which the paper above measures at 2.5% stale, five times network idle's rate. |
| Playwright actionability | per-element: stable = **same bounding box for two consecutive animation frames**. The cheapest per-ref readiness primitive anywhere, and we have no equivalent. |

**Playwright's `networkidle` is DISCOURAGED, and that does not transfer to us.**
Their rationale is specific to testing: *"Don't use this method for testing, rely
on web assertions to assess readiness instead."* A test knows what it expects and
can assert it. An agent deciding whether an observation is worth reading has no
expectation to assert — which is exactly why the paper above can measure network
idle as best-in-class **for agents** while Playwright discourages it **for
tests**. Do not quote Playwright's position as applying here.

**Nobody else exposes a settling signal to the model.** browser-use is the only
other project doing it, and **nobody has measured whether it helps.** Our
readiness banner is, as far as the literature goes, an unvalidated hypothesis —
and a cheap A/B with `tools/bench_turns/`.

### Two refinements taken from browser-use, and one deliberately not

Taken: **an attribute write whose value did not change is not a change**
(their comment: "Google Flights rewrites a class every frame"). Without it one
such page pins this signal busy for ever.

Not taken: their damping of `style` mutations to once per element per 200ms.
200ms is a chosen number, and the kind-split reporting already discriminates —
"40 @style" and "40 structural" read as the opposite facts they are.

### A bug this predicted that we do NOT have — checked, so nobody re-derives it

browser-use's `network_idle.py` documents that a naive CDP request count *"ran
to its 10s cap on any page with a Web Worker or an out-of-process (cross-site:
ad, captcha, chat) iframe"*, because those requests complete on a **different
CDP target**. That would present exactly as "the banner never clears on ad-heavy
pages", which is the complaint — so it was worth checking rather than assuming.

**It does not apply.** `_netPending` is fed by `chrome.webRequest`, not CDP.
`onBeforeRequest` / `onCompleted` / `onErrorOccurred` are browser-level and fire
for every request attributed to the tab whatever process serves it, so an
out-of-process iframe's completion is seen. There is also a 15s `setTimeout`
drop per request so an aborted one cannot pin a tab for ever. Checked at
`background.js` `_pendDrop` and the three listeners around it.

**One related thing is real and is now handled.** A long-poll `xmlhttprequest`
is counted for up to 15s (`websocket` and `media` are skipped by type;
long-polls are not). browser-use ignores anything older than 1.5s for this
reason — by *suppressing* it. We do not suppress: the DOM-quiet branch in §5c
reports it as *"the DOM has been unchanged for Xms, so what is on the page now
is stable… separately, N requests in flight"*, which is the honest version of
the same fix and the one PRINCIPLES rule 6 asks for.

## 7. What is done, and what is still open

**Closed while building it**, each with a check that fails against the pre-fix
code (R11–R21 in `tools/test_readiness.py`):

- shadow roots, via the `attachShadow` wrap that already exists (R16)
- same-origin frames, by merging child rings with `since` taken as the minimum
  (R19)
- the collector's own `mmid` stamping excluded **at record time**, so it does
  not evict real records — filtering is one string compare, storing allocates,
  and conflating the two bounds leaked the exclusion at exactly the rate a burst
  exceeded the prefix (R14/R15)
- the ad-page false positive, via the two-tier split (R20/R20b)
- the page cannot blind the recorder: non-enumerable, non-writable, and
  `pause()`/`resume()` deleted rather than hardened (R18)
- unknown degrades to **unknown**, never to quiet (R17)
- no attribute filter at all, so there is no list to drift from what the listing
  prints; the attribute name is kept per record instead

**Still open:**

- **Live verification under the extension.** Everything above ran under
  Playwright against sliced-out functions. The *before* half IS captured live —
  on the shipped build, a page 10% painted returned no banner at all — but the
  fix has not been seen in a real Chrome. #30 is the precedent: this exact
  probe's three declarative signals were dead in production for a release while
  the suite read 10/10, because `executeScript({func})` stringifies one function
  and a sibling call becomes a free identifier whose ReferenceError lands in a
  swallowing catch.
- **Per-subtree attribution** (§5b). Designed, not built. The kind-split covers
  the dominant case; scope would cover the rest.
- **Cross-origin frames** are not reachable and are deliberately not counted as
  quiet, which is a stated limit rather than a fix.
- **A per-ref readiness primitive.** Playwright's actionability has one — *the
  same bounding box for two consecutive animation frames* — and it is the
  cheapest readiness check anywhere. We have nothing equivalent, and it is what
  the observe→act gap in `OPEN.md` #1 actually needs.
- **Whether telling the model helps at all.** We and browser-use are the only
  two projects exposing a settling signal to the model, and there is no
  published evidence it improves anything. A cheap A/B with `bench_turns`.
