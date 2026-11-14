# The representation — what the listing is, and why

The question underneath everything in this directory: **a page is a tree of
tens of thousands of nodes, and a model gets a few thousand tokens of it. What
survives, and who decides?**

This project's answer, arrived at by deleting things rather than adding them:

> **The page decides what exists. We decide only how to present it.**

History: CLAUDE.md #26 (presentation overhaul), #27 (the tree), #28 (zero
heuristics decide existence), #29, #37 (seven matchers replaced by
declarations).

---

## 1. The four questions, kept separate

Almost every defect in this project's log came from one of these answering
another's question.

| | Question | Answered by |
|---|---|---|
| **Existence** | does this element get a row? | the page's own declarations — nothing else |
| **Identity** | what is it called? | AccName, then declared fallbacks, each attributed |
| **State** | what is true of it right now? | HTML/ARIA properties, printed as flags |
| **Presentation** | how is it laid out in the output? | our judgement, freely |

Only the last is ours. That split is the whole design, and the reason it holds
is that **presentation is reversible and existence is not** — a badly folded
listing is annoying, a deleted element is indistinguishable from a page that
does not have it.

### Existence: the admitting set, entire

HTML interactive tags · `audio`/`video[controls]` · `canvas`/`svg` · an ARIA
interactive role · `onclick`/`tabindex`/`contenteditable` · a registered
listener (`__abClickBound`) · `cursor:pointer` — the page telling the *user* it
is clickable · a measured-monospace editor host.

What may **remove** an element is exactly: the page not rendering it, the page
declaring it absent (`aria-hidden`, `inert`), the complement of the set above,
an inheritance correction (`contenteditable` is inherited, so only the root is
the control), the caller's own `max_chars`, and one measurement-error path.

**No class name, font name, framework name, pixel size, character count or
wordlist gates whether an element exists.** That is checked mechanically:
`L10c` enumerates the ten rule names permitted to appear in `dropped` and fails
on anything else.

### The two measurements that forced this

**Heuristics that delete cost 2.8pp of ground truth.** Converting five container
rules (parent-child dedup, same-box wrapper collapse, shadow-host collapse,
container suppression, delegation root) from *delete* to *demote*, on 34
live-captured pages:

| | before | after |
|---|---|---|
| compact entries | 148 | **223.5 (+51%)** |
| presence (ground truth derived independently of the collector) | 0.929 | **0.957** |
| findability MRR | 0.949 | **0.982** |
| compact tokens | 996 | 1,099.5 (+10.4%) |

They had been deleting a third of every listing's entries. **And on Mind2Web the
same change measured as free and pointless** — recall and reachability unchanged
to the digit, three of five rules never firing — because Mind2Web is static HTML
with no CSS, so a rule keyed on box geometry has nothing to trip on. That is
PRINCIPLES §9 in one experiment: the corpus you measure on decides what you can
see.

**The tree is why the deletions were never needed.** `parent-child-dedup` exists
because a flat list cannot say "this one is inside that one", so it had to pick
one and drop the other. The tree indents the child under the parent and says it
by position. Repetition is decided by **exact equality of sibling subtree
shape**, not a weighted feature set — the fold signature was rewritten four
times in one day and every version was right on the sites checked and wrong on
the next, until the question stopped being asked. *"Are these the same kind of
thing?"* has no heuristic answer and does not need one, because the DOM states
it.

---

## 2. What it costs, with every ruler's caveat

| | |
|---|---|
| **Mind2Web target recall** (173 labelled actions, 16 untuned sites) | **96.0% at 1,242 median tokens** |
| Chrome accessibility tree, same pages, same metric | 100% at 8,886 tokens (**7.15×**) |
| MindAct `cleaned_html`, same pages | 100% at 41,716 tokens (**33.6×**) |
| recall per 1k tokens | **0.773** vs AX tree's 0.113 — **6.8×** |
| `lost_identities` across 32 sites | **0** |
| tree over flat | **1.09× median** (mean 1.83× on component-heavy SPAs) |
| first-read reachability | **51.4%** — viewport-scoped by design |

**Read the last row with its argument.** Four variants were measured:
viewport-scoped **50.9% / 369k tokens**; every offscreen row listed **71.1% /
559k**; cap lifted **93.6% / 1,251k**; offscreen-only-when-folded **50.9% /
413k**. All four end at the same 96.0% *recoverable*, and the viewport-scoped
listing gets there for a third of the budget. Whole-page reach was then made
cheap instead — a scoped read is **not** viewport-limited, and the off-viewport
hint names the regions **and their refs**, so the recovery is one small scoped
read rather than a scroll and a full re-listing.

Three independent 2026 results now support that choice, the sharpest being IGG:
**+3.1pp from telling an agent what reveals the target, +48pp from performing
the reveal for it.** A hint the agent can act on in one call is worth far more
than one it must translate into a scroll. `read_page(ref_id=<region>)` is on the
right side of that line; "scroll down" is on the wrong side.

And the cost figures above described the **flat** listing for most of this
project's life, because `measure_retention` called the collector with three
positionals and `format` was undefined. See `MEASUREMENT.md` §3.

---

## 3. What was deleted, and what each deletion bought

| Removed | Why |
|---|---|
| every natural-language wordlist that read page text | each was written to look multilingual and matched nothing outside Latin script — a trailing `\b` after a CJK alternative can never match, because JS `\w` is `[A-Za-z0-9_]` |
| the submit picker's two wordlists | it answers only from `type="submit"` or HTML's implicit submit, and **refuses while naming candidates** when zero or several qualify. That deletes the "is this one destructive?" question: we never choose between Save and Delete account |
| per-field truncation caps | ablated at **+3.1% total chars**, against nine silent-cut defects in one session, six of which were the same bug in a different function |
| a class-name regex admitting anything containing "canvas" | recall unchanged at 96.0%, so it was carrying nothing |
| a font-name list for editor detection | replaced by **measuring glyph advance width**, so a self-hosted `--font-editor` works as well as the six names someone thought of |
| `active|selected|current` class tokens for tab state | replaced by the selected tab's `aria-controls` panel being the rendered one, or ARIA's roving tabindex |
| three library popover-attribute names | replaced by a structural test: rendered, out of flow or stacked, not containing the trigger, ≥2 sibling clickable rows |
| `[class*="helper"]`, `[class*="error"]` | English words on author-chosen class names — a German "fehlertext" landed in the field. Replaced by `aria-describedby` / `aria-errormessage` |

The pattern is the same every time: **a matcher that reads as general and
measures as narrow, replaced by something the page states out loud.** It is
audited mechanically by `tools/audit_patterns.py` because reading does not catch
it — the three historical bugs it self-tests against all passed code review
before they were measured.

---

## 4. Where it is measured against the alternatives

**browser-use's admission rule**, ported and run over 18 frozen sites: they
admit 11,510 elements, we list 7,995, and the gap decomposes as `cursor-pointer`
**53.6%** and a 10–50px "icon" rule **30.9%** — **84.5% from two rules whose own
samples convict them** (a Hacker News rank number, a datepicker separator
`span "MM/"`). Meanwhile **we list 825 elements they would never admit.**

*Caveat, and it is current:* that was measured against their
`ClickableElementDetector`. Their shipped `ax.py` now takes existence from the
Chrome AX tree. The conclusion is unaffected; the framing "we are more
disciplined than browser-use about existence" is going stale. `OPEN.md` #19.

**Convergence is the other half of the story.** In the last eight weeks
Playwright shipped `ariaSnapshot({mode:"ai"})` + `getByRef()` — an indented tree
of role and accessible name with `[ref=e2]` handles, `--snapshot-boxes` **opt-in
and off by default**, a `browser_find` that searches the snapshot because it is
"cheaper than capturing the whole snapshot", scoped snapshots by ref, and a
1.65 change excluding unrendered text from accessible names. Those are #26,
#27, #32, #37's `_namable` and `ref_id`, independently reinvented by the
Playwright team.

That is validation, and it moves the differentiation argument. **One difference
is real and worth holding:** their `browser_find` searches the snapshot; our
`search_page` searches **rendered text**, so it reaches prose and table data
that is in no listing. Given that text ablation is the single largest coverage
drop in the MFS study (30.5% / 59.5%), that is not a small difference.

---

## 5. The honest state

**Solid.** Existence decided only by declarations, verified mechanically.
`lost_identities` 0/32 including RTL, CJK, Hangul, Cyrillic, data grids, canvas
apps and framesets. Zero domain- or hostname-keyed logic. Non-Latin write
round-trips byte-identical 6/6. Closed shadow roots reachable with **no
debugger**, which beats CDP `pierce` precisely where #12 refuses the attach.

**The known holes**, each in `OPEN.md` with its evidence: a handler on the
`onclick` **property** is invisible to every tool; `role` is matched as an exact
raw string where ARIA defines a case-insensitive token list; the fold label
stripper can emit lone surrogates on emoji; `_kind`'s number guard is inert on
every non-Latin-digit page; page-level scans never cross an iframe boundary.
Four of those five are being fixed as this is written.

**The hole that is structural, not a bug** — the one the user's "at any stage"
names — is readiness. The listing is correct about the page *as it is at that
instant*; nothing told the agent whether that instant was worth reading. See
`READINESS.md`.

**The question we have never asked.** Every ruler here measures **presence** —
could the element be reached. None measures **sufficiency** — was what survived
*enough*. `MEASUREMENT.md` §2.
