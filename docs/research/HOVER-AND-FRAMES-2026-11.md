# Hover-revealed content, and cross-origin iframes

**Probes:** `tools/audit_hover_stage.py`, `tools/audit_frames_live.py`
**Date:** 2026-11-18
**Under test:** `extension/background.js` @ `74eb147d351434f0` (sha256[:16]), repo `0a35600`

> **Attribution, because another agent was committing to this repo during the session.**
> #73 records a `background.js` hash changing mid-run and the resulting number being
> unreproducible, so it was checked rather than assumed: `extension/background.js` was last
> written at **18:27**, before the first measurement at 18:39, has **no uncommitted diff**,
> and hashes `74eb147d351434f0` throughout. The one concurrent commit (`999e175`, 18:41)
> touches **zero** lines of it. Every number here attributes to one collector version.

> These are the two page states `docs/research/STAGE-GENERALITY-2026-11.md` lists under
> "Still unmeasured". Neither is unmeasurable; one of them was being skipped for a reason
> that is about the PRODUCT and was then applied to the PROBE, and the other was being
> skipped on a claim this repository already contained the counter-example to.

---

## 0. The headline

| | |
|---|---|
| **Playwright cannot exercise the cross-origin path** (CLAUDE.md #2) | **FALSE.** It runs end to end here: real extension, real `chrome.webNavigation.getAllFrames`, real `chrome.scripting.executeScript({frameIds, world:"MAIN"})`, real bridge, real MCP tools. `tools/run_flows.py` has been doing it in CI since #50. |
| cross-origin frame at **depth 1** | collected, named, actionable, **0 identities lost**; same-origin frames, late-created frames and three same-host frames (the Stripe shape) all clean |
| cross-origin frame at **depth ≥ 2**, or under a same-origin frame | **every control silently absent** — and TWO messages promise `read_page` reaches it, while a third points at `query_elements`, which cannot either |
| a row the listing prints inside a cross-origin frame | **unreachable by `find`, `search_page` and `query_elements`**; `query_elements` returns a **silently partial count** (reported 1, DOM holds 2) |
| a click on a cross-origin frame row | **lands, and is reported `*** NOT DELIVERED ***`** — with a top-document click in the same tab reporting correctly, which is the control |
| the one notation written **for** a cross-frame row (`target="_top"`) | **cannot appear on one** — 21 element facts the main listing prints are dropped by a second, drifted row formatter |
| a password field inside a cross-origin frame | **still redacted** — the one thing that would have been serious is safe |
| **hover-revealed controls**, 115 live out-of-sample sites, 63 reveals, 493 scored | **0 own no row**, 0 unstamped, and `audit_generality_live`'s own arms are 0 post-hover too. **No hover defect found.** Four ruler bugs of mine had to be removed first (§7) |

---

## PART A — CROSS-ORIGIN IFRAMES

## 1. The claim, and why it was wrong

CLAUDE.md #2 says of the cross-origin path:

> the cross-origin path uses chrome.* APIs — validated by review + syntax, runtime-verifiable
> only in the live extension (Playwright can't exercise it)

`STAGE-GENERALITY` inherited it verbatim ("cross-origin iframes: measured by neither arm,
because neither this probe nor the collector can read into one"), and `tools/test_frames.py`
opens by repeating it and then carving out the one part it could reach:

> That is true of `collectCrossFrames` itself, but NOT of the part that actually broke: the
> GEOMETRY.

**All three sentences are about `page.evaluate()`, and none of them is about Playwright.**
Playwright cannot reach `chrome.*` from a page context — true, and a different statement from
"Playwright cannot exercise the extension". `launch_persistent_context(args=["--load-extension=…"])`
loads the real unpacked extension into a real Chromium, where `chrome.*` is simply *present*.

And this repo already did it. `tools/run_flows.py` (#50) launches exactly that, seeds a
throwaway profile with host/port/token and a **granted** origin, waits for the real WebSocket
bridge, and drives the **real MCP tool functions** — in CI, on every push. Its own docstring
says so:

> it drives the WHOLE stack — a real Chrome, the real unpacked extension, the real WebSocket
> bridge, the real op router, the real MCP tool functions

So the genuinely untested surface was never "cross-origin frames". It was "anything needing
the extension", and the harness for that shipped eight entries ago and was not connected to
this question. `audit_frames_live.py` is `run_flows`'s launch path pointed at frame fixtures.

This is the §V reading failure in `PRINCIPLES.md` — *when an entry says something is open,
check whether a later entry closed it* — with the twist that the later entry did not mention
frames, so nobody looked.

### It is in four places, and in one of them it stopped a capability being built

| where | what it says |
|---|---|
| `CLAUDE.md` #2 | the origin: "runtime-verifiable only in the live extension (Playwright can't exercise it)" |
| `docs/research/STAGE-GENERALITY` §"what this does not measure" | "measured by neither arm, because neither this probe **nor the collector** can read into one" — the second half is wrong too; the collector reaches them by per-frame injection |
| `tools/test_frames.py` docstring | repeats it and carves out the geometry |
| **`mcp_server.py:2505-2512`** | **a decision**: "Querying INTO those frames is the real fix and is **deliberately not attempted here**: the cross-origin path … is runtime-verifiable only in a live extension, and this project has already paid for a batch of fixtured-but-unexercised changes. Recorded as E4-D2." |

The fourth is the one that matters. The belief did not merely sit in a doc — it is the stated
reason a capability was not built, and the caution behind it is sound (#43's lesson about
fixtured-but-unexercised changes is exactly right). What was missing is that the harness which
removes that objection already existed.

A fifth, adjacent: `tools/README.md:96` says **"No suite requires the live extension or the
WebSocket bridge. The things that do are the `diag_*` probes"** — also stale since #50, and
the same wrong model of what can be driven.

PRINCIPLES §V records the closed-shadow-root claim being wrong in four user-facing places at
once. This is the same shape, and it was found the same way: by running the thing.

### What is still genuinely unreachable

Honest, and short:

* **Chrome's own scheduling of `getAllFrames`.** We observe what it returns; we cannot make
  it return late, out of order, or mid-navigation on demand. #2's note that frame order "is
  NOT guaranteed to be DOM order" stays an assumption about Chrome, correctly defended by
  `collectCrossFrames`'s sort-by-src fallback, and not exercised here.
* **The user's real browser.** This is a throwaway profile with no extensions, no password
  manager and no sessions, so limitation #12 (another extension's injected iframe refusing
  `chrome.debugger.attach` tab-wide) cannot occur and is not measured.
* **Real third-party frames.** Stripe Elements, a TCF CMP and an embedded checkout are
  *shapes* reproduced here from local servers; their real markup is not.

---

## 2. Method

Three local HTTP servers on three OS-assigned ports. **Three ports are three real origins** —
the same-origin policy keys on scheme+host+**port** — so `contentDocument` genuinely throws
and `collectCrossFrames` takes the path it takes on the web. No public network, no
user-agent spoofing, no bot-check evasion; there is nothing here to evade.

The consent gate is **granted, not bypassed**, via `run_flows._grant`: a profile this script
creates and destroys, on bridge port 8913 (outside both the default 8765-8774 span and
`run_flows`' 8901), so the user's own Chrome never sees it. `ALLOW_ALL_ORIGINS` is untouched.

### The metric

For each frame, a census runs **inside that frame** (the only place a cross-origin frame's
DOM is readable) and is scored against the **real top-level listing** the agent received:

| arm | question |
|---|---|
| **lenient** | the control's identity string appears somewhere in the listing or the entry blob |
| **strict** | the control **owns a row**, matched by the ref its frame's rows use (`f<frameId>:<mmid>` cross-origin, bare `<mmid>` same-origin) |
| **capped** | absent, *but the listing said so* — `collectCrossFrames` prints "N of M element(s) shown" plus a truncation note |
| **SILENT** | `strict − capped`: absent, with nothing saying so. **This is the number that matters.** |

Visibility is `checkVisibility({opacityProperty: true, visibilityProperty: true})`, because
#36 measured a bare call reporting 3.81% identity loss that was not there.

**One ruler bug of my own, caught by its own negative control.** The first census used
`innerText` as a `<select>`'s identity — which is *its option list*, the one string #37
records AccName forbidding as a name — and duly reported every `<select>` in every scenario
as a lenient loss. A defect in the ruler wearing the costume of a defect in the collector
(PRINCIPLES 8). Labelable controls now take their wrapping `<label>`, which is what the
collector resolves and therefore what it prints.

### Proving it fires

`--selftest` requires the detector to report loss on three controls that are genuinely there
and SHOULD be missing (S3's depth-2 leaf, S4's cross-origin-under-same-origin leaf, S7's
over-the-cap tail) **and** to report zero on the four scenarios the collector does reach.
`--lossy` deletes the cross-frame rows from a real listing, holds the census fixed, and
requires both arms to rise.

```
LOSSY FIRING PROOF (cut 235 chars of real cross-frame rows):
    clean {'lenient': 0, 'strict': 0} -> mutilated {'lenient': 3, 'strict': 3}   FIRED
SELFTEST  fires where it must: {'S3 depth-2 nested': 3, 'S4 x-under-same-origin': 3,
                                'S7 over the frame cap': 16}
          silent where it must be: {'S1': 0, 'S2': 0, 'S5': 0, 'S6': 0}
          PASSED
```

---

## 3. Results

| scenario | frames | blocks | cand | lenient | strict | capped | **SILENT** |
|---|---|---|---|---|---|---|---|
| S1 depth-1 cross-origin | 1 | 1 | 4 | 0 | 0 | 0 | **0** |
| S2 same-origin frame | 1 | 0 | 3 | 0 | 0 | 0 | **0** |
| S3 nested: cross-origin in cross-origin | 2 | 1 | 4 | 3 | 3 | 0 | **3** |
| S4 cross-origin under same-origin | 2 | 0 | 3 | 3 | 3 | 0 | **3** |
| S5 frame added after a click | 1 | 1 | 4 | 0 | 0 | 0 | **0** |
| S6 three same-host frames (Stripe shape) | 3 | 3 | 10 | 0 | 0 | 0 | **0** |
| S7 frame over the 40-entry cap | 1 | 1 | 56 | 16 | 16 | 16 | **0** |
| S8 hover menu, through the real stack | — | — | 3 | 0 | 0 | 0 | **0** |

### What works, and it is most of it

**Depth-1 cross-origin frames are fully carried.** S1's three controls are collected, named,
and given routable refs:

```
ref_5 | button "TOPLEVEL s1 button"
ref_6 | iframe name="payment frame" (cross-origin-iframe)
[CROSS-ORIGIN IFRAME f6 "payment frame" (127.0.0.1) — 4 of 4 element(s) shown; act with ref f6:N]
ref_f6:5 | button "XORIGINB button"
ref_f6:6 | input placeholder="XORIGINB field"
ref_f6:8 | select name="XORIGINB choice" value="alpha"
ref_f6:12 | a "XORIGINB escape-hatch"
```

The last row is A5's planted `target="_top"` link: listed, actionable, and carrying **none**
of the warning the main listing would have given it.

**A same-origin frame is walked inline** (S2) with no `f<id>:` prefix and no loss — the
composed walk, as documented.

**A frame created by a click is picked up** (S5) with no special handling, because
`getAllFrames` is asked at read time.

**Three same-host frames stay distinct** (S6) — the Stripe Elements shape that broke
size-based matching. All three get their own block and their own refs.

**The 40-entry frame cap is announced, not silent** (S7): `40 of 56 element(s) shown`, the
`Accept all` button **prioritised to the top of the block** ahead of 55 decorative links, and
a truncation note naming the cap. That is PRINCIPLES 5 honoured, so those 16 are counted as
`capped`, not as lost.

**A password field inside a cross-origin frame is still redacted.** Worth stating because the
canonical cross-origin frame is a payment or login widget and this is the one field where a
leak would be serious: the redaction lives in `_collectInteractivePage` at **collection**
time (line ~8912), and the collector is what runs inside the frame, so a cross-origin frame
inherits it rather than depending on the frame serializer to remember. **That is structural
luck worth naming** — §4's A2 shows the frame serializer forgetting 29 other things the
collector computed, and this one is safe only because it is applied one layer earlier.

**And a hover menu, driven through the same real stack (S8), is carried end to end.** Three
revealed rows listed, `find` reaches them, and **no MODAL banner** is raised by the popover —
the #51 class (a banner from something that is not modal) does not fire here.

```
before hover: HOVERONLY present=False
menu still open when the listing was taken: True
after hover: rows=3, find reaches a revealed row: True
  ref_9 | a "HOVERONLY alpha"   ref_11 | a "HOVERONLY beta"   ref_13 | button "HOVERONLY gamma"
```

**`(just appeared)` fires on 0 of those 3, and that is CORRECT — measured, not assumed.**
The obvious reading is a defect, so it was checked: a collection with the menu CLOSED already
stamps `mmid` on the hidden items and registers them in `__mmidReg` (`stamped: 2, total: 2,
regHas: 2`). #42 seeds the novelty seen-set from the **registry**, so those controls were
seen before the hover. The flag's own contract (#31) is *"did my action CREATE this"*, and a
CSS hover menu **reveals** rather than creates. So the flag is right, and the honest statement
is the limitation rather than the bug: **nothing in the listing tells an agent that a hover
opened a menu** — it must diff two reads itself, or ask for `delta=true`. Recorded because
#42's own D19 retraction is the mirror of this mistake, read in the other direction.

---

## 4. Defects

### A1 — a cross-origin frame below depth 1 is silently absent, and the notice promises it is not

`collectCrossFrames` filters `f.frameId !== 0 && f.parentFrameId === 0`, so **only frames
whose parent is the top document are collected.** Two real shapes fail:

* **S3**, cross-origin inside cross-origin — a consent frame that embeds a vendor frame, an
  embedded checkout that embeds a 3-D Secure frame.
* **S4**, cross-origin inside *same-origin* — the ordinary "wrap the third-party widget in
  our own layout frame" pattern.

In both, three rendered, visible, named controls appear in no row, under no block, with no
marker. Measured, not inferred: `XORIGINC button`, `XORIGINC field`, `XORIGINC choice`.

**The sharper half is the message.** `_domTextPage`'s cross-origin notice ends:

> read_page DOES reach them — their refs look like `ref_f<frameId>:<n>` — so scope a read
> there if the answer is inside one.

**S4 is where this bites hardest, and the mechanism is worth stating.** `harvestFrames`
recurses through **same-origin** frames, so it finds the cross-origin frame nested inside the
same-origin wrapper and names it by host and path — while `collectCrossFrames` filters it out
for having `parentFrameId !== 0`. The two passes disagree about one frame, and the one that
disagrees *louder* is the one that is wrong: the notice fires **naming that exact frame** and
promises a recovery that does not exist. `read_page` does not reach it at any detail, scope or
format. PRINCIPLES 6 is explicit — *never assert a
recovery you have not verified* — and `C15` cannot catch this one because the sentence is
declarative rather than hedged, which is the same blind spot #82's menubar note fell into.

**The one diagnostic that exists to answer "why is this missing" cannot.** `read_page(ledger=true)`
returns before the cross-frame append (`if (params?.ledger) break;`), and the top-level
collector never walked into the frame, so there is no `_drop` record to find. An agent that
does everything right ends with no explanation.

Secondary, same root cause: S3's inner frame is listed **inside** the outer frame's block as

```
ref_f8:6 | iframe name="inner xorigin"
```

with **no `(cross-origin-iframe)` marker**, so it is indistinguishable from a same-origin
frame whose contents were listed inline. See A2 for why.

**Proposed fix.** Two options, and the cheap one is not the right one.

*(a) Minimal — widen the filter one level.* Replace the depth-1 filter with a parent-chain
walk, keeping a bounded depth, and prefix refs with the full chain. `runInTab` already takes
a `frameId`, so the injection works unchanged; the shell anchoring is what gets harder,
because a depth-2 frame's shell rect must be composed through its parent's. **Geometry can be
declined without declining collection** — `box()` is opt-in since #26 and refs re-measure at
click time, so a depth-2 frame could be collected with no `box()` and still be fully
actionable. That is the smaller, safer change.

*(b) Say so, unconditionally, whatever (a) does.* The notice must not promise `read_page`
reaches a frame that got no block. The data for an exact sentence is already in hand at that
point — `getAllFrames` knows every frame's `parentFrameId`, and `collectCrossFrames` knows
which ones it emitted a block for. A frame with content and no block should be *named*:

```diff
-  read_page DOES reach them — their refs look like ref_f<frameId>:<n> — so scope a read
-  there if the answer is inside one.
+  read_page reaches the ones whose parent is this document (refs look like
+  ref_f<frameId>:<n>). N frame(s) here are nested inside another frame and are reached by
+  NEITHER tool: <list>. Their contents are not in this listing and their absence is not
+  evidence of absence.
```

(b) is required even if (a) ships, because (a) will still have a depth bound.

### A2 — the cross-origin frame row serializer is a second `_fmtLine`, and it has drifted

`collectCrossFrames` builds its rows by hand:

```js
lines.push(`ref_f${fid}:${e.mmid} | ${e.tag}${id}${rl}${flags}${_xbox}`);
```

Counted mechanically against `_fmtLine`, over the **same entry objects**:

| | `_fmtLine` | frame serializer |
|---|---|---|
| entry fields read | 46 | 17 |
| flag notations emitted | 21 | 3 (`required`, `unselected`, `disabled`) |
| `key=` fields | 7 | 3 (`name`, `value`, `placeholder`) |

**29 entry fields the main listing prints are never read for a cross-origin frame's rows**,
and every one of them is *already on the entry*, because the collector computed it inside
that frame. Split by whether the omission is arguable, so the number is not overstated:

**Pure element facts — transfer with no further thought (21 of the 29):**

| field | what the agent does not get |
|---|---|
| `readonly` | `(read-only)`. #40 added it because "an agent offered only (disabled) or nothing cannot tell a field it may read from one it may not". |
| `href` | a link's declared destination — #61's descriptor rung. |
| `src` | media URLs. |
| `type` | `input[email]` vs `input[password]`; #31 made it part of the fold shape because "it decides how you interact with them". |
| `constraints` | #31's `pattern` / `min` / `max` / `step` / `format` / `maxlength` / `inputmode`. |
| `options` | a `<select>`'s declared enumeration and `count=`. |
| `describedBy` | `help=` and `error=` (#37) — a payment frame's validation message. |
| `crossFrame` | `(cross-origin-iframe)` — A1's missing marker. |
| `topNav` | see **A5**, which is the sharpest instance. |
| `newTab` | `(opens NEW tab)`. |
| `hasPopup` | `(opens menu/popup)`. |
| `collapsed` | `(collapsed)`. |
| `editable` / `codeEditor` | `(rich-text-editor)` / `(code-editor)`. |
| `iconOnly` / `iconGraphic` | `(unlabeled)` / `(unlabeled-icon)` — #37's "icon is a fact". |
| `orphanWidget` | `(DEAD-DUPLICATE)`. |
| `canvasLike` | `(canvas)`. |
| `mediaOnly` / `cssBackground` | `(media — …)`. |
| `isNew` | `(just appeared)` — a control a frame created since the last read. |

**Frame-relative — the fix needs a decision, not just a field (5):** `offscreen`,
`clippedInContainer`, `scrollRegion`, `clickable` (`(occluded/blocked)`), `near`. All of them
are computed against the *frame's* viewport and the main listing's wording assumes the top
one. They are real information and the right wording is a judgement.

**Arguably not applicable (3):** `section` (stripped from the tree format since #27, and
every in-frame row is already announced as being in a frame), `backedBy` and `synth`
(cross-row references that would need the `f<id>:` prefix rewritten).

This is PRINCIPLES 17 — one concept, one spelling — and **this exact function has drifted
before**: the source carries a comment recording that its rows "still announced themselves
with the internal spelling" `mmid=` after the main listing moved to `ref_`, "two vocabularies
for one concept, in the one place where the agent is already least sure how to address the
element". It was fixed for refs and not for anything else.

**The duplication is FORCED and the obvious fix is wrong.** `_fmtLine` is nested *inside*
`_collectInteractivePage` (line 12690, inside the function beginning at 6157) and must be,
because the collector is injected via `chrome.scripting` and a top-level sibling would be a
free identifier — the exact class `C11` exists for and #30 measured leaving the readiness
probe dead for a release. So `collectCrossFrames`, a service-worker function, genuinely
cannot call `_fmtLine`.

**Proposed fix — delete the second formatter rather than sync it.** `collectCrossFrames`
already injects the collector into each frame in **structured** mode and uses the result only
to build lines and count them. Ask the frame for its **own formatted listing** instead and
rewrite the refs:

```diff
-    try { raw = await runInTab(tabId, _collectInteractivePage, [true], fid); } catch (e) { continue; }
-    if (!Array.isArray(raw) || !raw.length) continue;
+    // ONE FORMATTER. _fmtLine is nested inside the collector (it must be: a
+    // top-level sibling is a free identifier across the chrome.scripting
+    // boundary, C11). So instead of a second serializer that has now drifted
+    // twice, ask the FRAME to format its own rows and re-prefix the refs.
+    let rawText = null;
+    try { rawText = await runInTab(tabId, _collectInteractivePage,
+                                   [false, null, detail, false, geometry, format], fid); }
+    catch (e) { continue; }
```

then `rawText.replace(/\bref_(\d+)\b/g, 'ref_f' + fid + ':$1')` over the frame's own row
block, with the frame's legend/banner lines stripped.

Costs, stated rather than buried, because this is the bigger change:

* The frame's listing is **viewport-scoped to the frame's own viewport**, where today every
  entry is listed and then capped at 40. That is arguably more correct and is a behaviour
  change that needs its own before/after on the same page load (PRINCIPLES 10).
* The cap and its prioritisation would move from entries to lines, and must keep saying
  "N of M" — S7 is the regression guard.
* `box()` coordinates come out frame-relative and need the shell offset added, which is the
  one thing the hand-rolled path does correctly today (`_xbox`).
* Round-trip count is **unchanged** — it replaces the structured call rather than adding one.

**And a tripwire, because this function has now drifted twice and prose did not stop it**
(PRINCIPLES 15). A check in `tools/test_contracts.py`:

```python
def _c13_frame_rows_carry_what_the_listing_carries():
    """C13: the cross-origin frame path must read every entry field _fmtLine reads.

    _fmtLine is NESTED inside the injected collector and a service-worker
    function cannot call it (C11's rule), so the duplication is forced and only
    enforcement can keep it honest. It has drifted twice: `mmid=` vs `ref_`
    (fixed), and then 29 fields (this check). FRAME_RELATIVE is the explicit
    exemption list -- adding a name to it is a decision someone has to write
    down, which is the point.
    """
    fmt   = extract("_fmtLine", BG, verify=True)
    frame = extract("collectCrossFrames", BG, verify=True)
    FRAME_RELATIVE = {"offscreen", "clippedInContainer", "scrollRegion",
                      "clickable", "near", "section", "backedBy", "synth"}
    reads = lambda s: set(re.findall(r"\be\.([A-Za-z_]\w*)", s))
    missing = reads(fmt) - reads(frame) - FRAME_RELATIVE
    return not missing, f"frame rows drop {sorted(missing)}"
```

It fires today on 21 fields, which is its firing proof; with A2's structural fix it passes
because the frame formats its own rows with `_fmtLine` and the two sets are the same set.

### A3 — a click into a cross-origin frame lands and is reported `*** NOT DELIVERED ***`

Measured, with the control that separates it from a harness artefact:

| | says NOT DELIVERED |
|---|---|
| click on `ref_f6:5` (cross-origin frame) — **verified landed**, the frame's own `#got` read `CLICKED` | **true** |
| click on `ref_5` (top document), same tab, same instant, same browser | **false** |

So this is the cross-frame path, not headless, not a background tab, and not #56's dead input
channel — all of which would have made the control fire too.

**Cause.** `computerOp` arms and reads the delivery probe with

```js
_armed = await runInTab(t.id, _inputProbePage, [true]);          // no frameId
_delivered = await runInTab(t.id, _inputProbePage, [false, 'mouse']);
```

and `runInTab` with no `frameId` targets `{tabId, allFrames: false}` — **the top document.**
The capturing listener is installed on the top document; the click lands inside a
cross-origin child frame, whose events do not propagate across the boundary; the top probe
counts zero; `_delivered === false`; the note fires.

`computerOp` already resolves the frame two lines away for the rect and the focus
(`resolveFrameSelector(params.selector).frameId`), so the information is in hand.

This is #81's defect in a second place and the same cost: an over-warn that spends a model
turn, on exactly the page family — payment and consent widgets — where an agent is least able
to tell a false alarm from a real one. #81 measured the equivalent at 5 of 7 scored runs.

**Proposed fix.**

```diff
+    // The probe must live in the frame the click will LAND in. runInTab with no
+    // frameId targets the top document, and a cross-origin frame's events do not
+    // cross the boundary -- so a click into a payment/consent frame armed a
+    // listener in the wrong document, counted zero, and reported NOT DELIVERED on
+    // a click that worked. #81's defect, one frame over.
+    const _probeFid = params.selector ? resolveFrameSelector(params.selector).frameId : null;
-    try { _armed = !!(await runInTab(t.id, _inputProbePage, [true])); } catch (e) {}
+    try { _armed = !!(await runInTab(t.id, _inputProbePage, [true], _probeFid)); } catch (e) {}
...
-      try { _delivered = await runInTab(t.id, _inputProbePage, [false, 'mouse']); } catch (e) {}
+      try { _delivered = await runInTab(t.id, _inputProbePage, [false, 'mouse'], _probeFid); } catch (e) {}
```

**The four other probe sites need a different answer, and it is the more interesting one.**
`_armedK`/`_delK` (~1955, ~1966) and `_armedT`/`_delT` (~1999, ~2009) have the same bug —
after a cross-frame click the focus is inside that frame — but `key` and `type` often carry
**no selector**, so there is nothing to resolve a frame from. From the top document, *which
frame holds focus is not knowable* across an origin boundary.

So the rule is not "pass a frameId", it is: **`_delivered === false` only means anything if
the probe was armed in the document the input went to.** Two ways to honour it:

*(a) Arm and read in EVERY frame.* `chrome.scripting.executeScript({target:{tabId,
allFrames:true}})` returns one result per frame; `delivered` is `true` if **any** frame saw
the event. Correct for all five sites with no selector reasoning, and the same number of round
trips — `runInTab` would need a sibling that returns the whole array instead of `[0]`.

*(b) Degrade to UNKNOWN when the target frame cannot be established.* A selector gives the
frame; no selector plus ≥1 cross-origin frame on the page means the answer is unknown, and
unknown must claim nothing — the rule #56 already applies when a navigation destroys the probe
(`ID3`), and the one #77 applied to the readiness probe's scoped answer.

(a) is better and (b) is the floor. Shipping neither leaves a false negative that fires on
exactly the pages where trusted input matters most.

**And the `NO EFFECT` guard is dead on this path for the same reason**, one layer further:

```js
_fxB = await runInTab(t.id, _clickEffectPage, [params.selector]);   // no frameId,
                                                                    // AND the unstripped ref
```

`params.selector` is `[mmid='f6:5']`, which cannot resolve in the top document at all, so
`_fxB` is `null` and the whole `_noEffect` branch is skipped. A cross-frame click that does
nothing is therefore never reported as doing nothing. Same two-part fix: pass `_probeFid` and
pass `resolveFrameSelector(...).selector`.

**Regression control for any fix:** the top-document click must keep reporting
`NOT DELIVERED: false`, and #56's genuinely-dead-channel case must keep reporting it true —
otherwise this becomes "never warn", which would pass the frame test while deleting the
guard. That is `ID9b`'s shape.

### A4 — a cross-origin frame's contents are unreachable by every tool except `read_page`

The listing prints `ref_f6:5 | button "XORIGINB button"`. Handed that row's own identity:

| tool | result |
|---|---|
| `find` | **MISSES** |
| `search_page` | **MISSES** |
| `query_elements` | **MISSES** |
| `read_interactive_elements` | reaches |

**The first measurement of this scored three of four tools as REACHING, and it was my probe
that was wrong** — `search_page` quotes the caller's pattern in its miss message (#42) and
`find` echoes the query, so `needle in result` was satisfied by the echo. A false credit in
the flattering direction, from the person writing the probe, which is precisely PRINCIPLES 8.
The test is now the **ref**: a hit emits it, an echo cannot.

**Cause, exactly.** The cross-frame append is gated on the string path:

```js
if (!params?.structured && typeof result === 'string') { ... collectCrossFrames ... }
```

`find` asks `get_interactive_elements(structured=True, detail="full")` (`mcp_server.py`:2778)
and `read_interactive_elements` does not (`:3475`), which is the whole difference.
`query_elements` and `search_page` run their own page-context pass in the top document and
cannot cross the boundary at all.

This is #74's shape — present in the listing, unreachable by the tool whose job is reading it
— and `find`'s own source already carries a comment about this same `!params?.structured`
guard, from #39, in the context of the readiness banner. The guard was understood; its effect
on frames was not.

**The sharpest form of this is `query_elements`, because COUNTING is what it is for.** `total`
is documented as never capped and never filtered, and #32 built it so an agent could ask "how
many rows does this table have". On S1 the DOM holds **2** buttons — one in the top document,
one in the cross-origin frame — and:

```
query_elements('button') reported 1, the DOM across all frames holds 2
    partial = True,  warned about frames = False
```

A confident wrong number, silently. The existing frame notice **is gated on the zero-match
path**, which is the case where the agent is already suspicious; when the top document
supplies *some* matches it says nothing at all. That gate is the wrong one: the condition
that should raise it is "this page has frames I did not look in", which is true whatever the
count came back as.

**The two tools in the same position also give different advice**, which is the cheap half of
the fix already written once. `query_elements` has the notice (`mcp_server.py:2522`, "E4-D2"):

> This page contains N frame(s), and THIS QUERY DID NOT LOOK INSIDE THEM — a cross-origin
> frame is a separate document. `read_page` does reach them, so if the element is in one it
> will have a ref there.

`search_page` has **none**, although it is the tool `instructions=` names for "does this page
mention X" and a consent frame is exactly where the answer hides. Its miss message lists
pagination, lazy-loading, collapsed sections, closed menus, unopened tabs and typographic
characters — every cause except the one it is structurally incapable of overcoming — and it
then says *"count with query_elements — those reach rows this cannot"*, which is **false for a
cross-origin frame**: measured above, `query_elements` misses it too.

So A1's false promise appears a **second** time here (`read_page` does reach them), and
`search_page` additionally points at a sibling that cannot help.

**Proposed fix — the cheap half first.**

* **Move `query_elements`' notice off the zero-match gate.** Raise it whenever the page has a
  frame this query did not enter, whatever the count. A partial count delivered confidently
  is worse than a zero, because a zero prompts a second look.
* `search_page`: give it the same notice. It is one bridge op on the miss path only (#38's
  rule: take a round trip exactly where its answer can change what happens next), and the
  code exists — **one spelling, used by both** (PRINCIPLES 17), rather than a second copy that
  will drift the way A2's did.
* Correct the promise in both, and in `_domTextPage`, per A1(b): `read_page` reaches the
  frames whose parent is the top document, and names the ones it does not.
* Delete `search_page`'s "count with query_elements — those reach rows this cannot" for the
  frame case, or qualify it. It asserts a recovery that was measured not to work.
* The fuller fix is to let `collectCrossFrames` contribute to the **structured** array with
  `mmid: "f<fid>:<n>"` — `find` already prints `ref_` + `e.mmid`, and `resolveFrameSelector`
  already routes that shape, so it would work end to end. It costs `find` the per-frame
  injection on every call, measured by `audit_frames.py` at **median 14 ms, p90 18 ms** per
  frame — cheap against a ~3.6 s model turn (#38), but it should be priced on both axes
  before it ships (PRINCIPLES 10), because `find` is already the fallback tool and OPEN item
  17 flags it as already unbounded in entries × tokens.

**A2 and `docs/OPEN.md` item 7 want the same change.** That item's cost analysis already
established that `collectCrossFrames` "injects the collector into 27 of 33 rendered frames on
every unscoped string read, so the per-frame round trip is ALREADY PAID", and names the design
it points at: *"have the existing per-frame call return each frame's verdict and feed it back
before the banner is built."* Asking the frame for its own **formatted listing** (A2) is that
same call, and it would carry the modal verdict item 7 wants, the 21 dropped element facts,
A5's `topNav`, and A1's `(cross-origin-iframe)` marker — for **zero extra round trips**.

### A5 — the one notation written FOR a cross-frame row cannot appear on one

`_fmtLine` carries this flag:

```js
const tp = e.topNav ? " (REPLACES the whole page, destroying this frame and every f-ref in it)" : "";
```

and its legend line reads *"**in-frame link** with `target="_top"`/`"_parent"`: navigates the
TOP document, invalidating every ref here."* Both sentences were written for a row inside a
cross-origin frame — `f-ref` is that path's own vocabulary — and **neither can ever be emitted
there**, because A2's hand-rolled serializer never runs `_fmtLine`.

Measured, by planting `<a href="/elsewhere" target="_top">` inside the cross-origin leaf:

| | |
|---|---|
| the row is listed | **true** |
| `(REPLACES the whole page)` on it | **false** |
| the legend line present | **false** |

`topNav` is set at line 10159 inside `_collectInteractivePage`, which is what runs in the
frame, so **the entry carries the fact and only the formatter drops it.** The consequence is
the one the flag's author anticipated: a `target="_top"` link inside a consent or payment
frame replaces the whole page and invalidates every `f<id>:N` ref on it, and the agent is told
nothing. This is #30's "shipped inert" class, and it is the single strongest argument for
A2's structural fix over patching fields one at a time — a field-by-field patch would have
had to notice this one specifically, and two previous passes over this function did not.

### A6 — the ledger cannot explain a cross-frame absence

Measured on S3 and S4: `read_page(ledger=true)` returns **no cross-frame rows and no drop
record** for the missing controls. The router returns before the append
(`if (params?.ledger) break;`) and the top-level collector never walked into the frame, so
there is nothing to record. An agent that does exactly the right thing — "the element is
missing, ask the ledger why" — gets silence.

Not separately ranked: it is A1's consequence, and A1's message fix is what repairs it. But
`L10c`'s premise is that *recorded* deletes are the whole delete set (#29 recorded the ledger
having a silent exit for same-origin frames and adding
`iframe-contents-listed-instead` to the permitted set), and this is a second unrecorded path.

---

## 5. Drift

The frame matrix is deterministic by construction (local servers, fixed markup). Run three
times with the code held constant, the scenario shape — frames present, blocks emitted,
candidates, every loss count, the reachability verdicts, the action-routing verdict and both
`topnav` answers — is identical. The only values that move between runs are the OS-assigned
ports and Chrome's internal frame ids (`f6` → `f12` → `f6`), neither of which any assertion
depends on.

**Drift floor for this half: 0.** A difference of one in any column is signal.

---

## PART B — HOVER-REVEALED CONTENT

## 6. Why it was unmeasured, and why that did not block a probe

`audit_stage_generality` chooses its interactions from **declarations only** and counts a
stage only when the page's own declared state flipped. A CSS `:hover` submenu declares none
of `aria-expanded`, `aria-haspopup`, `aria-controls`, `<details>` or `role=tab`, so that
picker cannot choose one — correctly, because PRINCIPLES 1 forbids the **product** inferring
that an element is a menu root from anything the page did not declare.

**That is a rule about what the product may INFER, not about what a probe may DRIVE.**
Nothing here asks the collector to detect a hover menu. The probe puts the mouse somewhere
deliberately, observes whether anything appeared, and asks whether the collector saw it. The
first question was closed; the second was never asked.

### What is driven

Three tiers, all read off the page rather than guessed:

| tier | how a candidate is chosen |
|---|---|
| `css-hover` | the page's **own CSS**: a rule whose selector contains `:hover` and whose declarations set `display` / `visibility` / `opacity` / `transform` / `height` / `max-height` / `pointer-events` / `clip` / position. Same-origin sheets only — a cross-origin sheet throws on `.cssRules` and is counted as unreadable, never as "declares nothing". |
| `hidden-children` | an element that currently contains 2–60 controls of which **none** are visible — a closed submenu, whatever produced it. This is the tier that reaches JS `mouseenter` menus, which declare nothing in CSS and are most of the modern web. |
| `nav-item` | a top-level item of a `<nav>` / `role=navigation`. The crudest tier, for the mega-menu shape when neither of the others fires. |

### Detection is by observation, not assumption

The before-set is a `Set` of **element references** held in page memory, diffed against the
visible set after the mouse lands. Element identity, not names: two controls can share a name,
and a name diff would both miss those and invent changes when a label re-renders.

**Nothing is written to the DOM.** `audit_stage_generality` records its first version tagging
the target with `data-ab-stage-target` and the readiness probe duly reporting the attribute
write as page activity ~18 ms before every measurement (#70's lesson, rebuilt by someone who
had read #70). The target here is a live element reference on `window`, and
`probe_attrs_clean` is asserted on every measurement.

The probe also records whether the hover **survived the measurement** (`:hover` re-tested on
the root after the listing was taken), because a zero scored after the menu closed is a zero
for the wrong reason.

### Proving it fires

`--selftest` drives a fixture with both a CSS `:hover` submenu and a JS `mouseenter` menu:

```
  tiers reached: ['css-hover', 'hidden-children', 'nav-item']
    [css-hover]       revealed 3 (['REVEALED alpha', 'REVEALED beta', 'REVEALED gamma']) cand=3
                      clean(lenient,strict)=(0, 0)  mutilated=(3, 3)
    [hidden-children] revealed 2 (['JSREVEALED one', 'JSREVEALED two'])                  cand=2
                      clean(lenient,strict)=(0, 0)  mutilated=(2, 2)
  1. a CSS :hover submenu is DRIVEN and its 3 controls are seen to appear: YES
  2. a JS mouseenter menu (declares nothing in CSS) is reached too:        YES
  3a. NEGATIVE CONTROL — on the real listing both arms report 0:           YES
  3b. with the revealed rows DELETED, the metric reports them lost:        YES
SELF-TEST PASSED
```

3a is the half that makes 3b worth anything: the same census and the same scoring on the
unmutilated listing reports zero, so the probe distinguishes a complete listing from a
mutilated one rather than reporting loss everywhere.

## 7. Four ruler bugs of mine, and the two numbers that caught them

The first live pass reported **19,324 of 19,618 hover-revealed controls (98.5%) owning no
row**. That damns the system, which is exactly when PRINCIPLES 8 says to re-derive before
believing. All four causes were mine, and **every one of them is a definition I restated
instead of reusing** — which is PRINCIPLES 17, committed four times in one file by someone
quoting PRINCIPLES 17 in that file's own docstring.

**(i) Two definitions of "a visible control".** The picker's `box()` required the element to
be IN THE VIEWPORT; the diff's required only non-zero size. So the before-set was
viewport-bounded and the after-set was not, and **every below-fold control on the page counted
as newly appeared** the moment anything was hovered. What that measured is the listing's
deliberate viewport scoping (#6, #26 — priced and rejected twice), not hover. There is now
one definition, a Python constant interpolated into both snippets so they cannot diverge, and
off-screen arrivals are counted separately (8,373 of them) and never scored as losses.

**(ii) A third definition of "owns a row".** `audit_generality_live`'s strict arm harvests ids
from the structured **blob** as well as from the listing's refs and folded rows. Mine parsed
the listing alone — stricter than the project's own strict arm. #36 records the
permitted-drop-reason set drifting exactly this way and producing a false "a rule started
deleting again" on six sites.

Those two took the headline to **22 of 526 strict (4.2%)** — and left `lenient_lost` at
**154 of 526 (29%)**, with the *weaker* arm losing seven times more than the stronger one.
That is arithmetically impossible for a real loss (a control that owns a row must have its
identity in the listing, unless the row prints a *different* identity), and it is what exposed
the remaining two.

**(iii) Raw `innerText` compared against a collapsed AccName.** AccName collapses whitespace
runs, and #28's step-2F rule space-delimits each element child's contribution, so the listing
prints `DBS Singapore's leading consumer bank` where raw `innerText` holds
`DBS\nSingapore's leading consumer bank`. 100+ of the 154 were that. Both sides are now
whitespace-normalised — the same rule #63 settled on for flow assertions, for the same stated
reason: *HTML collapses whitespace runs when it paints.*

**(iv) No `aria-hidden`/`inert` exclusion.** `audit_generality_live`'s arms skip elements the
page declares absent from the accessibility tree; mine did not, so a mega-menu that marks its
closed panels `aria-hidden` would have scored every one of them as a loss. Dropping those is
the documented behaviour (PRINCIPLES 1 and 3), and they are now counted separately rather than
scored.

**None of the four is visible in the self-test**, because the fixture is one screen tall, its
revealed controls are all on screen, its labels are single-line and nothing is `aria-hidden`.
A fixture encodes what you thought of (PRINCIPLES 11). What caught them was the size of the
number, and then the *direction* of the second number.

The residue is now explained rather than asserted: every remaining strict miss is joined to
the collector's own ledger reason, which is the correction #73 had to make to #26's
characterisation of the Mind2Web misses — ask the ledger instead of inferring.

## 8. Results

120 out-of-sample sites (the pool is `audit_stage_generality`'s `usable85`, checked against
the frozen corpus, `bench_turns` and `bench_flows`; the run refuses to start on a hit),
**115 usable**, 5 blocked or empty and reported as **UNMEASURED, not as passes**.

| | |
|---|---|
| hover attempts | **456** |
| …that actually revealed something | **63**, on **38 of 115 sites (33%)** |
| controls revealed **on screen** | **528** |
| …scored (named, still present) | **493** |
| arrivals **below/beside the fold** (counted, never scored) | 8,373 |
| the page declared absent (`aria-hidden`/`inert`) | 22 |
| the menu closed under us before the read | 7 |
| **HOVER-REVEALED CONTROLS OWNING NO ROW** | **0** |
| …never stamped with an `mmid` | **0** |
| **`audit_generality_live`'s own arms, whole page, first paint** | `lost_core 0, lost_deep 0, strict 0` |
| **…after a hover** | `lost_core 0, lost_deep 0, strict 1` — and that 1 **did not reproduce** (see Drift) |
| reachable by `find` using the identity the listing printed | **295/323 = 0.913** |
| drop reasons outside `SPEC_DELETES` | **none** |

**The headline is a clean negative result: a hover menu's controls are collected and own
their own rows.** The project's own lenient arms — the ones #85 and #92 report — are **0** at
first paint and **0** across all 63 post-hover reads, and the hover-restricted strict arm is
**0 of 493**.

### By tier, and the honest denominator

| tier | tried | revealed | controls | scored | no row |
|---|---|---|---|---|---|
| `css-hover` | 258 | 38 | 248 | 235 | **0** |
| `hidden-children` | 107 | 20 | 262 | 255 | **0** |
| `nav-item` | 91 | 5 | 18 | 3 | **0** |

456 attempts for 63 reveals is the honest ratio and it is low on purpose: a candidate whose
hover changes nothing is an **attempt**, not a reveal, and is not counted as one. The
`hidden-children` tier is the one that reaches JS `mouseenter` menus — it produced **262 of
the 528 controls** from 107 attempts, which is the half a CSS-only picker cannot see.

### By script

Reveals are thin outside English, so the per-script rows are reported as evidence of coverage
rather than as per-script measurements: latin-english 28 reveals / 324 controls, latin-other 4
/ 59, kana+han 7 / 37, cyrillic 4 / 35, vietnamese 4 / 25, han-trad 2 / 15, han-simp 2 / 12,
greek 2 / 7, arabic 2 / 4, hebrew 3 / 4, hangul 3 / 3, thai 2 / 3, bengali and devanagari 0.
**Zero controls owning no row in every one of them.**

### Two things that are not defects, and one residue

**`find` reaches 295 of 323 (91.3%).** `measure_findability` reports **0.9774** on frozen
sites, so this is lower — but the populations differ (a hover menu's items are short,
repeated labels like "Visit Site" where ties are common) and #74's metric already records
that a tie is not a failure. It is reported, not explained away, and it is not a hover defect.

**The MODAL banner fired on 2 hover reads (both `ar_aljazeera`).** Not the #51 class: the
same measurement recorded `dialogs_visible = 2`, so the page really was rendering two visible
`role=dialog`/`aria-modal` elements at that instant. The banner is reporting what the page
declares, which is PRINCIPLES 1. A banner raised with `dialogs_visible = 0` would have been
the defect, and there were none.

**The one apparent residue did not reproduce, so it is noise.** AGL's whole-page strict arm
reported `strict_norow_named = 1` on `vi_vnexpress` after a `hidden-children` hover (1,203
entries, both lenient arms 0). The drift pass reports **0** on the same site with the same
code. One non-reproducing control is below this instrument's floor and is **not** recorded as
a finding — naming it as one would be the mistake PRINCIPLES 8 exists for, pointed at a
damning result instead of a flattering one.

### The hover has to survive the read, and 7 times it did not

`:hover` was re-tested on the root **after** the listing was taken: **56 survived, 7 did
not**. Those 7 are counted and their controls are excluded as `closed_under_us`, because a
zero scored after the menu shut is a zero for the wrong reason — the failure mode #15 names
(a probe that stopped looks identical to a settled page) applied to a hover.

### Drift

The same 120 sites, run twice back to back with the code held constant:

| | pass 1 | pass 2 |
|---|---|---|
| usable sites | 115 | 116 |
| hover attempts | 456 | 452 |
| …that revealed something | 63 | 60 |
| sites with a reveal | 38 | 36 (36 of 38 shared; 2 only in pass 1) |
| controls revealed | 528 | 531 |
| scored candidates | 493 | 505 |
| the page declared absent | 22 | 20 |
| closed under us | 7 | 0 |
| **controls owning no row** | **0** | **0** |
| never stamped with an `mmid` | **0** | **0** |
| `find` reached | 295/323 = 0.913 | 288/320 = 0.900 |
| MODAL banner raised by a hover | 2 | 2 |
| AGL whole-page arms, first paint | `0 / 0 / 0` | `0 / 0 / 0` |
| AGL whole-page arms, post-hover | `0 / 0 / 1` | `0 / 0 / 0` |

**The sample moves and the result does not.** Reveal counts drift ~5% and `find` by 1.3pp —
which is what a live-web sample does, and it is why neither of those is quoted as a precise
figure. **The identity number's floor is exactly 0 in both passes**, as it was in
`STAGE-GENERALITY`, so a single control owning no row would be signal. The one that appeared
in pass 1 did not appear in pass 2, which is how it was disqualified.

**One honesty note about this floor.** The frames probe (a local-fixture browser, ~2 min) ran
concurrently with pass 1 and not with pass 2. That can only add CPU contention to pass 1, so
if it biased anything it inflated the measured drift — the conservative direction for a
claim that 0 is signal.

## 9. Ranked defects

**Every defect is in the frame half. The hover half came back clean**, and that is reported as
a result rather than padded: 493 revealed controls across 38 sites and 14 script families, 0
owning no row, 0 unstamped, no drop reason outside `SPEC_DELETES`, no false MODAL banner, with
a detector shown to fire on a mutilated listing and on a JS menu that declares nothing in CSS.
The limits that qualify it are in §11 and they are real — above all that a hover menu needing
a sustained pointer path never opens for this probe and is counted as "nothing appeared".

| # | defect | severity | why that rank |
|---|---|---|---|
| **A1** | a cross-origin frame below depth 1 is **silently** absent, and two messages promise `read_page` reaches it | **high** | PRINCIPLES 3 (an identity the listing does not carry) **and** PRINCIPLES 6 (an unverified recovery, asserted). The blast radius is consent and payment flows, and the ledger (A6) cannot explain it. |
| **A3** | a click into a cross-origin frame **lands** and is reported `*** NOT DELIVERED ***` | **high** | #81 measured the identical token costing calls on 5 of 7 scored benchmark runs. Over-warn, so the safe direction — but on the page family where an agent can least afford to distrust a true result. Four more probe sites (`key`/`type`) share the cause, and the `NO EFFECT` guard is dead on this path entirely. |
| **A4** | a cross-origin frame row is unreachable by `find`, `search_page` and `query_elements` — and **`query_elements` returns a silently partial COUNT** | **medium-high** | #74's shape: present in the listing, unreachable by the tools that read it. The counting half is the worst part and is arguably high: `query_elements` exists to count, reported 1 where the DOM holds 2, and its frame notice is gated on the zero-match path so it said nothing. `read_page` still carries the rows, so an agent that stays on `read_page` is fine. |
| **A2** | the frame row serializer is a second `_fmtLine` and has dropped **21 transferable element facts** | **medium** | No identity is lost — every row is there. What is lost is `(read-only)`, `href`, `type`, constraints, options, `help=`/`error=`. Ranked below A1/A3 because the agent can still act; ranked above cosmetic because `(read-only)` and `href` change what an agent *does*. |
| **A5** | `(REPLACES the whole page, destroying this frame and every f-ref in it)` cannot appear on the rows it was written for | **medium** | A2's sharpest instance and the argument for fixing A2 structurally. A `target="_top"` link in a payment frame invalidates every `f<id>:N` ref with no warning. |
| **A6** | `read_page(ledger=true)` cannot explain a cross-frame absence | **low** | A consequence of A1 rather than an independent defect, but it is a second unrecorded delete path and `L10c`'s premise is that recorded deletes are the whole set. |

**Not defects, investigated and rejected** — recorded so they are not re-opened:

* **`(just appeared)` fires on 0 of 3 hover-revealed rows.** Correct by the flag's own
  contract; the collector stamps hidden menu items at the first read and #42 seeds the
  seen-set from the registry. Measured (§3), not reasoned.
* **The 40-entry frame cap drops 16 of 56 controls (S7).** Announced — "40 of 56 element(s)
  shown", the `Accept all` button prioritised to the top, a truncation note. That is
  PRINCIPLES 5 honoured, and counting it as loss would damn a bound the system states out
  loud.
* **The MODAL banner fired after 2 of 63 hover reads.** Not a false positive: the same
  measurement recorded `dialogs_visible = 2` on that page, so a visible `role=dialog`
  really was present and the banner reports what the page declares. The #51 class would
  be a banner with `dialogs_visible = 0`, and there were none.

## 10. Reproducing this

```bash
# frames — local only, ~2 min, deterministic. Starts and stops its own servers,
# creates and destroys its own Chrome profile, grants its own origins.
python tools/audit_frames_live.py --selftest --lossy
python tools/audit_frames_live.py --drift            # run the matrix twice

# hover — prove the detector fires first, then the live sample
python tools/audit_hover_stage.py --selftest
python tools/audit_hover_stage.py --sites 120 --drift --tag passC
```

Both compose with the existing probes by **import**, never by forking:
`audit_generality_live` supplies the metric, the sample and the exclusion guard;
`audit_stage_generality` supplies the stage row and the readiness summary;
`measure_findability` supplies `identity_of`, the fake bridge and the real `find`;
`run_flows` supplies the whole extension launch path. The exclusion guard is shown firing by
`_pool()` raising `SAMPLE CONTAMINATED` on any host in the frozen corpus, `bench_turns` or
`bench_flows`.

Neither probe writes anything to any page's DOM. `probe_attrs_clean` is asserted on every
hover measurement, for the reason `audit_stage_generality` records: a probe's own attribute
write shows up in the readiness signal as page activity (#70).

## 11. What remains unmeasurable, and why

**For frames:**

* **Chrome's scheduling of `getAllFrames`.** We see what it returns; we cannot make it return
  late, out of order, or mid-navigation. `collectCrossFrames`' sort-by-src fallback defends an
  assumption about Chrome that is not exercised here.
* **Limitation #12.** A throwaway profile has no other extension to inject a
  `chrome-extension://` iframe, so the tab-wide `chrome.debugger.attach` refusal cannot occur
  and the interaction between it and frames is unmeasured.
* **Real third-party frames.** Stripe Elements, a TCF CMP and a 3-D Secure step are *shapes*
  reproduced from local servers. The frozen corpus cannot supply the real thing either —
  `audit_frames.py` records that HARs are captured **after** consent and 21 of 128 frames no
  longer replay.

**For hover:**

* **Anything behind a bot wall.** Sites that blocked us are reported as UNMEASURED and counted
  as such. No user-agent spoofing and no bot-check evasion was used, deliberately: a
  measurement that required evading a site's own controls is not one this project would quote.
* **Hover menus that need a real pointer path.** Playwright's `mouse.move` is two synthetic
  moves; a menu that opens only on a sustained `mousemove` sequence, on `pointerenter` with
  pointer-type checks, or after a hover-intent delay longer than the settle window will not
  open, and that is counted as "nothing appeared" rather than as a failure of the collector.
* **Touch and keyboard equivalents.** `:focus-within` menus and touch-device long-press menus
  are different states with the same visual result and are not driven.
* **Whether the right name is on the right element.** This measures presence and reach, not
  correctness — #74's class. `tools/measure_findability.py` and
  `tools/audit_name_correctness.py` ask that question.
* **Whether a model then picks the right row.** #75 established the benchmark substrate
  cannot carry that question at all.
* **Cross-origin stylesheets.** Tier 1 reads `document.styleSheets`, and a cross-origin sheet
  throws on `.cssRules`. Those are counted as *unreadable* (`sheets_blocked`), never as "the
  page declares no hover rule" — but a hover menu declared only in a cross-origin sheet is
  reachable by tiers 2 and 3 or not at all.

