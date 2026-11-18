# Cross-origin consent frames: how often is the page-level scan blind, and does it matter?

**Probe:** `tools/audit_cmp_frames.py` (composes `audit_frames_live.Rig` — #94's
real-Chrome/real-extension harness — and `audit_generality_live.EXCLUDED` — the
out-of-sample guard)
**Under test:** `dialogOpen` @ `b97c6f79a6392163` (`extension/background.js` @
`f8fc3706f4591646`, repo `c090dac`)
**Date:** 2026-11-18

> **RESULTS ARE IN "The numbers" BELOW.** This section states the question and
> the method; nothing in it depends on the outcome.

---

## The question, and why the frozen corpus could not answer it

`docs/OPEN.md` item 7 records a correctness gap, proved by nine constructed
fixtures: the MODAL banner, the dialog-text pass and `section=dialog` are all
computed inside `_collectInteractivePage`, while `collectCrossFrames` runs
**after** the listing is built and merely appends rows. So a consent sheet
served from a CMP vendor's origin in an iframe can raise no banner, while the
identical sheet served same-origin does.

What was unknown was **frequency**, and item 7 is explicit about why the frozen
corpus cannot supply it:

> **FREQUENCY IS NOT ANSWERABLE ON THIS CORPUS, and the zero is verified real.**
> 42/96 sites have a child frame (128 frames), 17/96 have a RENDERED one, and
> **0 of 128 declare any page-level trigger**. … The corpus cannot hold the
> shape because **HARs are captured after consent**.

A corpus recorded after someone clicked "Accept" contains no consent sheets. The
only way to see them is a **fresh profile on live sites**, which is what this
is.

---

## Method

**The rig is not new.** `audit_frames_live.Rig` launches a real Chrome with the
real unpacked extension, a real WebSocket bridge and the real MCP tool
functions — the path `run_flows.py` has used in CI since #50, and which #94
established is available at all after a belief to the contrary had sat in five
places. This probe points it at live sites instead of fixtures.

**The profile is fresh and consent is never given.** Playwright's
`user_data_dir=""` mints a throwaway profile per launch; the probe asserts the
cookie jar is empty at startup and prints the count; and it **never clicks a
consent button**, so every sheet that is going to appear, appears and stays.

**The gate is granted, not bypassed.** Grants are written into that throwaway
profile's own `chrome.storage.local`, on bridge port 8915 — outside the default
8765–8774 span and outside `run_flows`' 8901 — so the user's own Chrome is never
involved and `ALLOW_ALL_ORIGINS` is not touched.

**No spoofing, no evasion.** No user-agent override, no proxy, no `navigator`
patching, no consent-banner clicking. A site that blocks the probe is
**UNMEASURED**, counted and named, never folded into a zero.

**The detector is a port of `dialogOpen`, evaluated inside each frame.** Five of
its seven rules are ported verbatim and run against the frame's **own** window —
which is #78/MV4's correction, that a rect lives in the coordinate space of the
view it came from:

| # | rule | ported |
|---|---|---|
| 1 | collect `[role=dialog],[role=alertdialog],[aria-modal=true],dialog` | yes (composed walk: open shadow roots and #31's `__abClosedRoot`) |
| 2 | visible: rect > 0 **and** `checkVisibility({opacityProperty, visibilityProperty})` | yes, identically — #36 priced a bare `checkVisibility()` at 3.81% phantom identity loss |
| 3 | `:modal` (native `showModal`) | yes |
| 4 | dominates the viewport, covers its centre, overlay-positioned, not a `<dialog>` | yes |
| 5 | all siblings `aria-hidden`/`inert` (Radix's modality, #25) | yes |
| 6 | an `[inert]` background ≥ 30% of the viewport (NHK's sheet) | yes |
| 7 | verify the `aria-modal` claim against how many page controls are blocked | **no** — reads the collector's `out` array |
| 8 | behavioural modality: a supermajority of controls occluded | **no** — same |

Rules 7 and 8 can only turn a `false` into a `true`, so omitting them makes the
"would trigger" count a **lower bound**. In the other direction the node
collection is a *superset* of the product's (`_allComposed` iterates the stamped
`mmidReg`; this walks the composed tree directly). Both are stated rather than
buried, because a probe that silently drops two of seven rules is reporting a
number about itself.

**Blocking vs incidental** is decided by three facts about the frame's shell in
the **top** document: ≥ 50% of the viewport, covers its centre, and — the one
that is not a threshold at all — `elementFromPoint` at the centre lands on that
frame. The split is not a refinement of the benefit, it is a **cost term**: the
modal-focus pass tells the agent to ignore rows outside the dialog subtree, and
#80 measured an off-canvas drawer taking all 150 entry slots on exactly this
mechanism. Every incidental trigger is a page the proposed fix would damage.

---

## The firing proof, before any count

PRINCIPLES 5/11/15: a zero from a detector nobody has watched fire is worth
nothing, and a detector that reports everything distinguishes nothing. Four
fixtures on **two local ports**, so cross-origin is real (Chrome's same-origin
policy keys on scheme + host + **port**), driven through the real extension:

| case | shape | detector | shell | banner today |
|---|---|---|---|---|
| **P** | cross-origin frame holding a full-viewport consent sheet | **FIRES** (`dominates-viewport`) | 1280×1000, frac 1.00, wins hit-test → **BLOCKING** | **false** ← the gap, reproduced live |
| **N** | cross-origin frame, ordinary content | silent | 422×202, frac 0.07 | false |
| **C** | the *same sheet* served **same-origin** | — | — | **true** ← the control arm works |
| **I** | the same sheet inside a 360×520 corner chat frame | **FIRES** | frac 0.15 → **incidental** | false |

`P` vs `C` isolates the boundary as the variable. `N` proves the detector is not
simply reporting loss everywhere. `I` proves the blocking split discriminates.
Reproduce with `python tools/audit_cmp_frames.py --selftest`.

---

## Two defects in the probe, both caught by a number contradicting data already on screen

PRINCIPLES 8, twice, on this probe's author:

1. **`_is_blocking` required `position: fixed|absolute|sticky` on the iframe**,
   mirroring `dialogOpen`'s own overlay test. But the common CMP layout is a
   `static` iframe sized 100%×100% **inside** a `fixed` wrapper — so the rule
   missed **every real CMP frame in the sample** while passing the fixture,
   whose iframe is itself `fixed`. The hit-test makes the term unnecessary: a
   frame that wins at the viewport centre is on top however it got there. The
   fixture's 0.07 and 0.15 cases stay incidental on area alone.
2. **`"{scheme}//{netloc}"` drops the colon** — `urlparse` returns `https`, not
   `https:` — so frame origins were spelled `https//host` while the JS side's
   `new URL(src).origin` spells them `https://host`. Cross-origin *detection*
   survived it (both sides malformed identically), but the "does the top
   document wrap this frame" comparison could never match and that count was
   structurally pinned at zero, with the wrapper origins sitting in the same
   record.

Both were found because a printed count disagreed with rows I had already
looked at, not by reading the code.

---

## What this probe cannot see

- **The vantage point is not the EEA.** This machine's timezone is
  `Asia/Kolkata`. GDPR/UK-GDPR consent sheets are frequently geo-gated to the
  EEA/UK and CPRA notices to California, and spoofing geolocation is exactly the
  bot-check evasion this project refuses. The probe therefore reports the
  **conditional** rate — cross-origin as a share of sites that show a sheet at
  all — which is far less geo-dependent, because an IP decides *whether* a CMP
  fires while the site's vendor choice decides *whether it is an iframe*. The
  absolute rate is a floor, not an estimate.
- **The agent's tab is hidden by design** (#12), and Chrome throttles timers
  there — #70 measured a 1.8 s paint stretching to 4.5 s. A CMP that appears
  late may be missed. This bounds the absolute rate and **not** the ratio,
  because `read_page` and the frame probes observe the same instant.
- **A 6 s settle, fixed for every site**, including the ones that will show
  nothing. A per-site "wait until something appears" budget would give every
  positive more time than every negative and manufacture the result.
- **Bot walls return HTTP 200.** A challenge interstitial would otherwise score
  as "a site with no cross-origin consent sheet", i.e. as a zero. Pages whose
  top document holds ≤ 3 controls **and** under 400 characters are counted as
  **THIN** and excluded from every figure; each is named below.
- **One read per site, at first paint.** A sheet that appears only after an
  interaction is out of scope, as is anything behind a login.

---

## The decision rule, fixed before the data was complete

Written after the firing proof passed and after a 6-site smoke test, with 24 of
203 rows on disk and none of them showing a cross-origin trigger — so it was
written knowing the result was *trending* toward zero, which is stated rather
than hidden. What it fixes in advance is the **threshold** and the
**direction**, which is the part that becomes unfalsifiable once the totals are
on screen (#40).

- **BUILD** if blocking cross-origin triggers reach **≥5% of sites measured**,
  or **≥20% of sites that show any consent sheet at all**. The second form is
  the one that matters, because the vantage point is non-EEA and geo bounds the
  absolute rate but not the ratio.
- **DON'T BUILD** at zero.
- In between: DON'T BUILD, and record the instances by name, because a handful
  of instances is not a frequency.

**The asymmetry that makes a low number decisive rather than merely weak.** A
missing banner costs the agent a caveat. A **false** banner costs it the page:
the modal-focus pass tells the agent to ignore rows outside the dialog subtree,
and #80 measured an off-canvas drawer taking all 150 entry slots on exactly that
mechanism. So the incidental/blocking split is not a refinement of the benefit,
it is a **cost term** — every incidental trigger is a page the fix would damage.
Therefore if triggers exist while none of them blocks, that is not "a small
benefit", it is a **negative** expected value.

---

## The numbers

203 candidates, one read each, fresh profile, no consent ever given.

| | | |
|---|---|---|
| candidates attempted | **203** | |
| UNMEASURED — navigate/read/gate | 14 | named below |
| UNMEASURED — loaded a THIN page (a challenge wall, not the site) | 46 | named below |
| **A — sites actually measured** | **143** | |
| **B — with ≥1 cross-origin frame** | **95 (66.4%)** | **710 frames** |
| **C — a cross-origin frame WOULD trigger a page-level scan** | **0 (0.0%)** | |
| **D — of C, blocking** | **0** | |
| — of C, incidental | 0 | |
| **E — CONTROL: raises the MODAL banner today** | **37 (25.9%)** | |
| **F — the gap itself: in C and no banner today** | **0** | |

**Cross-origin frames are not rare — they are on two thirds of the measured web,
710 of them. Not one carried a dialog the page-level scan would have fired on.**

### The geo check, and why the conditional rate is the one to read

| | |
|---|---|
| sites showing ANY visible dialog/sheet | **55 (38.5% of A)** |
| of those, served cross-origin | **0 (0.0%)** |
| of those, already caught by the page-level scan today | 37 (67.3%) |

A 38.5% absolute consent rate from a non-EEA vantage point means the sample is
**not** geo-suppressed into vacuity: sheets appeared, in quantity, and the
question "cross-origin or not" had a real population to answer over. The
conditional rate is **0 of 55**.

### Why — the mechanism, which is what survives a change of sample

| | |
|---|---|
| sites whose TOP-document dialog node WRAPS a cross-origin iframe | **17** |
| of those 17, raise the banner today | **17** |

Every blocking cross-origin frame in the sample, classified by **where the
dialog is declared** (n=18 frames):

| | n | |
|---|---|---|
| (a) the FRAME declares a dialog and would trigger | **0** | ← item 7's gap |
| (b) the frame declares a visible dialog that does not trigger | 0 | |
| (c1) the frame declares nothing; the TOP DOCUMENT wraps it in `role=dialog`/`aria-modal` | **17** | already seen today |
| (c2) nothing declares a dialog anywhere | 1 | see below |

**This is the finding.** The iframe CMPs in this sample — Sourcepoint and its
white-labelled hosts (`sp-spiegel-de.spiegel.de`, `consent.up.welt.de`,
`consent.faz.net`, `consent-cdn.sueddeutsche.de`, `cmp-sp.handelsblatt.com`,
`cmp.vg.no`, `cmp.aftenposten.no`, `cmp.aftonbladet.se`, `cdn.privacy-mgmt.com`,
…) put the **content** behind the boundary and the **dialog semantics** in front
of it. Verified element by element on spiegel, aftonbladet and hs.fi:

```
top document : role=dialog aria-modal=true, 1280x1000, frac 1.00, innerText length 0
               -> dialogOpen fires on `dominates-viewport`
the frame    : 0 dialog nodes, body 2121 / 1894 / 1774 chars, 13 / 14 / 9 controls
               (the actual consent UI, in German / Swedish / Finnish)
```

The wrapper's `innerText` is **empty** because its only child is the iframe. So
the page-level scan already sees exactly what it needs to, and the boundary is
not where the sheet is declared.

The single **(c2)** instance is `target` + `js.px-cloud.net` — a PerimeterX
anti-bot overlay that is full-viewport, wins the hit-test, and contains **0
characters and 0 controls**. It is an empty overlay, not a consent sheet, so the
"category next door" has zero real CMP instances here either.

### The residue of uncaught sheets is same-origin, not cross-origin

18 sites show a visible sheet and get no banner today. **All 18 are
same-origin** (`wrapped_xorigin_iframes = 0`), and 17 of the 18 are small
bottom-bar banners well under the modality threshold (`biggest_frac` 0.06–0.35:
nzz 0.35, rte 0.22, theverge 0.16, cnet 0.14, ikea 0.15, pwc 0.20, novartis
0.16, aljazeera_ar 0.11 …). The one full-viewport outlier is `airtable`
(`frac 1.00`, visible, same-origin, still `trigger: false`).

**So the thing that is actually missing banners is a modality question in the
top document, and item 7 would not touch any of it.**

### Drift control

The 24 sites that showed a blocking cross-origin frame, re-measured end to end
in a second browser session: **24/24 identical verdicts** on
(cross-origin frames / blocking / banner / triggers), **0 cross-origin triggers
in pass 2**.

### By bucket

| bucket | measured | with x-frame | C | blocking | banner today |
|---|---|---|---|---|---|
| eu_news | 42 | 34 | 0 | 0 | 19 |
| enterprise (TrustArc country) | 18 | 7 | 0 | 0 | 5 |
| adsupported (Funding Choices country) | 17 | 12 | 0 | 0 | 1 |
| us_news | 16 | 13 | 0 | 0 | 1 |
| saas (chat widgets) | 12 | 8 | 0 | 0 | 3 |
| nonlatin | 11 | 9 | 0 | 0 | 0 |
| gov_ref | 9 | 2 | 0 | 0 | 0 |
| eu_tabloid | 8 | 7 | 0 | 0 | 6 |
| shop | 6 | 2 | 0 | 0 | 0 |
| travel | 4 | 1 | 0 | 0 | 2 |

Wave 2 exists because PRINCIPLES 9 says an ablation measures the code against
the sample and cannot measure the sample: wave 1 is publisher-heavy, which is
Sourcepoint country, so a second sample was drawn for the two vendor families
most likely to put the whole sheet behind the boundary — enterprise/corporate
(TrustArc) and ad-supported content (Google Funding Choices). **Both returned
zero as well.**

---

## A defect in this probe that produced a false zero, and how it was caught

**The drift control found a probe defect, not drift** — which is the strongest
argument for running one.

`_page_for_tab` resolved the Playwright handle **once per run**, by taking the
last non-extension page. A persistent context opens with its own `about:blank`
and `tabs_create_mcp` adds a page Playwright may not have registered yet, so
that is a race — and **losing it does not look like a failure**. The MCP tools
keep working, because they address the tab by id: `navigate` commits, `read_page`
returns a real listing, the MODAL banner is real. Only `page.frames` is empty,
which this probe reports as **zero cross-origin frames** — a false zero pointing
exactly at the conclusion being drawn.

It is resolved **per run**, not per site, so a lost race poisons an entire wave:
**56 rows across the whole of wave 2 and the first drift arm**. Wave 1 was
clean. Detected because the drift arm returned `frames=0/0x` on 24 sites that
had just reported frames, with `banner_today=True` beside it — an impossible
combination.

**The firing proof could have caught it and did not**, because the race is a
per-run coin flip that the selftest won on every one of its runs. That is worth
stating plainly: a passing firing proof does not establish that the probe was
working on the run that produced the numbers.

Two changes, and the second matters more than the first:
1. the handle is resolved **per site**, matched on the landing **host**, with
   `about:blank` explicitly excluded;
2. **a handle that is not this page makes the row UNMEASURED**, naming what it
   got and what it wanted — because "I could not see" must never render as
   "there is nothing to see" (#77's structural root, PRINCIPLES 15).

Wave 2 was re-run from scratch with the fix; all 56 poisoned rows are replaced,
and the fixed run sees frames where the poisoned one saw none (`as_com` went
`0/0x` → `12/3x`). The firing proof was re-run after the fix and after the
`_is_blocking` widening, and passes in all four directions both times.

A second, smaller one: `_is_blocking` originally required
`position: fixed|absolute|sticky` on the iframe, mirroring `dialogOpen`'s own
overlay test. The common CMP layout is a **`static` iframe sized 100%×100%
inside a `fixed` wrapper**, so that term missed **every real CMP frame in the
sample** while passing the fixture, whose iframe is itself `fixed`. The hit-test
makes the term unnecessary.

---

## Verdict: **DON'T BUILD**

Against the rule fixed in advance: blocking cross-origin triggers are **0 of 143
measured sites** and **0 of the 55 that showed a consent sheet**. Both bars
(≥5%, ≥20%) are missed by the whole of their range.

**The correctness gap item 7 describes is real — nine fixtures and this probe's
own `P` case prove it — and it does not occur in practice**, for an
architectural reason rather than a statistical one: the iframe CMPs that exist
declare their dialog in the top document, where the scan already sees it. That
mechanism is what makes the zero worth trusting more than a bare count would be,
because it predicts the result on samples this run did not draw.

And the fix would not be free. Every incidental trigger is a page whose listing
the banner suppresses (#80 measured 150 of 150 entry slots lost on exactly that
mechanism), so a change that buys **0** real banners can only lose rows.

**What would reopen it**, stated so it is not re-derived:
- a run from an **EEA/UK vantage point**, where more CMPs fire and the vendor
  mix may differ. The conditional rate (0 of 55) is the geo-robust number, but
  it is not geo-proof.
- a **CMP vendor that declares its dialog inside the frame**. None of the
  families sampled does. One instance would be worth recording by name against
  these 17 counter-examples.
- the shape appearing **after an interaction** — this is one read per site at
  first paint, so a consent sheet opened from a "Privacy settings" link is
  untested.

If it is ever built, the design is still the zero-round-trip one item 7 names:
have the existing per-frame call return its verdict and feed it back before the
banner is built. `collectCrossFrames` already injects into those frames on every
unscoped read, so the round trip is paid.

---

## What was not measured

- **14 sites UNMEASURED by navigate/read/gate**, named in the probe output. Two
  are the consent gate refusing a cross-origin redirect (`edition.cnn.com`,
  `www2.hm.com`) — the permission model working, not a failure.
- **46 sites loaded a THIN page** — ≤3 controls and <400 characters in the top
  document, i.e. a challenge interstitial rather than the site. Named
  individually in the output (telegraph, dailymail, latimes, skynews, zara,
  asos, reuters, tripadvisor, forbes, etsy, …). These are **not** counted as
  zeros, per the brief. The rate is consistent with the ~180 bot-walled
  candidates this project's probes have already accumulated (#85).
- **One read per site at first paint**, after a fixed 6 s settle. A CMP that
  appears later, or only after an interaction, is missed — this bounds the
  absolute rate and not the ratio, because `read_page` and the frame probes
  observe the same instant.
- **The agent's tab is hidden by design** (#12) and Chrome throttles its timers,
  so a timer-driven sheet is slower here than on a visible page.
- **No logins, no second page per site, no EEA vantage point.**
