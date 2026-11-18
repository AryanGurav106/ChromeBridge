# Principles

The rules this codebase will not break. Every one was earned by a measured
failure, and the entry that earned it is named so you can read the evidence
rather than trust the sentence.

If you are a subagent working on this repo, **read this file before you write
code.** A change that violates one of these is rejected even when it passes the
suites, because the suites encode what we thought of and these encode what we
learned.

The numbered references are entries in `CLAUDE.md`, which is the chronological
ledger. This file is the topical index into it.

---

## I. What the system may claim about a page

### 1. Existence is decided only by declarations

No class name, font name, framework name, pixel size, character count or
wordlist decides whether an element gets a row. The admitting set is exactly:
HTML interactive tags, `audio`/`video[controls]`, `canvas`/`svg`, an ARIA
interactive role, `onclick`/`tabindex`/`contenteditable`, a registered listener
(`__abClickBound`), `cursor:pointer` (the page telling the *user* it is
clickable), and a measured-monospace editor host.

"The page declared nothing about this element" is not a guess about what
matters. Everything else is. — #27, #28

### 2. A heuristic may demote, never delete

Five container rules (parent-child dedup, same-box wrapper collapse,
shadow-host collapse, container suppression, delegation root) used to remove
elements. Converting all five to demotions raised ground-truth presence 0.929 →
0.957 and findability MRR 0.949 → 0.982 for +10.4% tokens. They had been
deleting a third of every listing's entries. — #28

The tripwire is `L10c`: it enumerates the ten rule names permitted to appear in
`dropped` and fails on anything else. A rule that starts deleting is caught by a
test, not by a live agent.

### 3. Nothing may lose an identity

A rendered, genuinely visible, not-declared-hidden control whose name appears
nowhere in the listing or the structured array is the worst defect this system
can have, because it is indistinguishable from the page not having that control.

Measured `lost_identities = 0` across 32 sites and held there. Any change that
removes text from a name is priced against this number before it ships. — #30,
#36, #37

A corollary that cost a week: **the visibility test is the whole measurement.**
A bare `checkVisibility()` checks layout only. With
`{opacityProperty: true, visibilityProperty: true}` a probe reporting 3.81%
identity loss reports 0.00%. — #36

### 4. No natural-language wordlist reads page text

Deleted from the submit picker, the placeholder detector, the destructive-action
test and the tab-state detector. Each was measured as noise or as actively
wrong, and each had been written to look multilingual while matching nothing
outside Latin script. A trailing `\b` after a CJK alternative can never match,
because JS `\w` is `[A-Za-z0-9_]`. — #21, #24, #39, #66

**The distinction that is allowed:** reading the *caller's* query, or our *own*
emitted output, is not reading page text. State words in a `find` query
(`disabled`, `required`) are English because they name our output. Role words
cover ~20 languages because they describe the page. — #39

### 5. Never truncate silently

`value="Acme Corporation Interna"` and a field whose contents really are that
string are the same 24 characters, and one of them is a lie the agent cannot
detect. Every bound on an agent-facing string goes through one `markCut(s, n)`
emitting `…(+N)` with the **true** residual.

Measured: 216,719 characters were vanishing across a 108-site corpus. Marking
every cut costs 0.297% of payload. Per-field caps were then deleted outright
(+3.1% chars) because a label is bounded by human authorship already. The system
now has exactly one bound: the caller's `max_chars`. — #22, #24

### 6. State the fact; list causes as causes; never assert a recovery you have not verified

Three incidents share this shape — a stale-ref message asserting "a navigation
invalidated your refs" on a page that had not navigated; a message asserting a
recovery was impossible that an agent had just performed; a note concluding
"this is most likely a CLOSED menu" while its own output listed an open
`role=menu` two rows below.

`C15` is the tripwire: it flags hedged-assertion vocabulary inside emitted
strings. It fired on its own author twice. — #14, #23, #33

### 7. Refuse rather than guess

The submit picker answers only from what the document declares and **refuses
while naming the candidates** when zero or several qualify. That deletes the
"is this one destructive?" question outright: we never choose between Save and
Delete account, because two candidates is a refusal rather than a coin flip.

Same rule in the flow runner: a target that cannot be pinned to exactly one
element pauses and hands back candidates. — #24, #49

---

## II. How a claim gets believed

### 8. A result that flatters or damns the system gets re-derived before it is believed

This has caught, among others: a benchmark walking only to the nearest
mmid-bearing ancestor (89.4% → 93.6% on fixing the *ruler*); a `^ref_` anchor
matching nothing because tree rows are indented; a probe comparing element
identity where the listing carries concept identity; a 43.6% ceremony figure
produced by the author's own prompt mandating the behaviour; and a
correctness falsifier firing on *both* arms, which is the signature of a broken
grader rather than a broken system. — #16, #18, #33, #45, #48, #55

Damning results get believed too readily. Two live agents agreeing with each
other is not evidence; it is correlated error.

### 9. An ablation measures the code against the sample; it cannot measure the sample

The placeholder wordlist measured as pure noise on the 106-site corpus and was
deleted. A live audit of nine real dropdowns then found it was carrying two
real cases, because **the corpus contained no `<option value="-1">Select</option>`
sentinel** — the older-web norm that runs the largest retail sites. The fix was
structural, not the wordlist back. — #25

Applies to benchmarks as much as corpora: Mind2Web is serialized HTML with most
CSS stripped, so documents are unstyled and tall and far more falls below the
fold than on a real page. A number taken there does not transfer to a styled
site without saying so. — #44

### 10. Measure cost and benefit in the same pass, interleaved

Block-structured A/B measures drift, not behaviour: running all sites for
variant A then all for variant B aligned run-order drift exactly with variant
order, and three of four "CLIFF" verdicts were artefacts. Interleave every
variant on the same page load, rotate the order, and take a drift control (the
same source measured twice) before attributing anything. — #19

And **a cost measured without its benefit cannot tell a targeted rule from an
indiscriminate one.** Off-viewport admission priced at +1.1% median chars looked
Pareto-positive; measured with its recall half it buys +6.9pp for +18.7% tokens
with **70% of the spend landing on tasks that gain nothing**. — #41, #44

### 11. A fixture encodes what you thought of — run it against the pre-fix code

Five vacuous fixtures found this way so far, three of them in one session. A
fixture that passes against the broken code is not a test, and nothing but
watching it fail distinguishes "the fix works" from "the fixture never reached
the code". — #29, #51

Corollaries with their own scars: a check that looks up a missing element
**passes vacuously** (prove presence first); a detector reporting zero findings
is worth nothing until it has been shown to fire; a negative control is what
separates "this works" from "this never fires".

### 12. A live pass before committing

#42 shipped 15 fixes with fixtures and no live pass. Seven regressions followed,
found by a 48-run benchmark. Every entry that went well measured on a corpus or
a live run *before* shipping. A live smoke pass is cheap next to a benchmark
that has to find it for you. — #43

---

## III. Where features die quietly

### 13. The op router and the string contracts are the untested links

Every suite injects page functions directly. Nothing else crosses the
`chrome.scripting` boundary or the string contract between `mcp_server.py` and
the listing the extension emits.

Shipped inert behind green suites: `detail="brief"` (router mapped anything
≠ full to compact), `delta` (server split on `"Act on an element"`, extension
emits `"Act on a row by its ref_N:"` — **dead for its entire life**), the
readiness probe's three declarative signals (injected function called top-level
siblings; every call threw `ReferenceError` into a swallowing catch), and the
flow recording wrapper (refused every batch). — #19, #30

`C11` enumerates all 25 injection targets and fails on a free identifier. `C12`
requires the server's boundary marker to prefix a line the extension emits.

### 14. A declared field needs both halves of its contract

Written but never read, or read but never written: `origin` (empty for every
flow ever recorded), `viewport` (declared, serialized, never populated),
`on_fail="heal"` (declared, never written, never branched on, silently became
`"ask"`), and the bridge's `set_event_handler` (shipped in the first commit with
no caller until #69). — #30, #54, #57, #62, #69

Audit every field of a dataclass against both ends, not against the schema.

### 15. A detector that cannot fire is worse than none

It also asserts that nothing is wrong. The suite-count drift check searched for
`17 suites, (\d+) checks` while the file said 18 and reported clean for
entries. Its own replacement then matched one spelling of three. The
vacuous-fixture tripwire, the pattern auditor scanning a file that does not
exist (`extension/sidepanel.js` — the file is `panel.js`), and a `--check-only`
flag that validated zero files and exited 0 are the same shape. — #30, #39, #66,
#67

**Its sibling is a WAITER that can never finish**, and it has now caught two
different agents in one session, the second of whom had just read the first's
account of it: `until ! pgrep -f <pattern>; do sleep; done`, where the pattern
occurs in the waiter's OWN command line, so `pgrep -f` matches the waiter and
the condition can never clear. Wait on a PID when one is in hand; a pattern is
for when it is not. Two capable agents walking into the identical shell idiom
after reading about it is the evidence that prose does not stop this class. —
#83, #92

### 16. A count is not an inventory

Three instances in three different tools: a decorator binding to a helper made
`sw_info` vanish from the tool surface **while the total stayed at 31**; the
pattern auditor printed "253 sites across 4 files" while scanning three; and
`git log --all` walks local-only refs, so a trailer count described a population
nobody had published. — #64, #66, #67

### 17. One concept, one spelling

The destructive test existed twice in one function, 35 lines apart,
multilingual in one tier and English-only in the other. The placeholder question
had four copies. Injected functions lose their closure so duplication is
*forced*; what was missing was enforcement. `P2` requires every definition
tagged `i18n:<concept>` to be byte-identical to its siblings. — #21

### 18. A comment that asserts a guarantee the code does not have

Principle 6 governs what the system says to the AGENT. This governs what it says
to the next person reading it, and it is more dangerous, because a reviewer who
reads the comment stops checking the claim.

`computerOp`'s dead-click guard reported `NO EFFECT` when a click was delivered
and the page had not changed, and its comment said that requiring
`_delivered === true` established *"same document"*. It does not: the delivery
probe lives on the OLD document's `window` and the readback is one
`executeScript` round trip after `mouseReleased`, so a link click has not
committed yet and both effect snapshots are taken against the page being left.
Eval 9 measured the cost at **5 of 7 of our scored runs** losing calls to the
token firing on clicks that had worked, and on three pairs that was the whole
margin.

`C15` cannot catch this class — it scans emitted STRINGS, and a comment is not
emitted. The only defence is the same one principle 11 gives: write the check
that fails against the current code, and if it passes, find out why before
believing it. A guarantee in a comment is a claim; it needs the same evidence as
a claim in a message. — #81

---

## IV. What the system optimises for

### 19. The lever is turns, not tokens

Measured by differencing so the model turn cancels: model turn ~3.6s
(**92–97% of a tool call**), bridge round trip ~162ms (~4%), DOM collection
~40ms–1.6s (~1%).

Halving the payload saves ~10% of prefill. Halving the round trips saves ~50% of
everything. A year of representation work was real and bought correctness and
reach; it is not the axis that moves wall clock. — #38

This is why `browser_batch` exists, why a page change stops only the steps that
*name a ref*, and why a 0.80ms navigation-settle lookup is asked
unconditionally while a listing is kept viewport-scoped.

### 20. Default deny, per origin

`assertOpAllowed` runs before every op. Storage is read on **every** gated op —
never cached, because a revoke has to take effect on the very next one. Grants
are written **only by the side panel**; a service worker that can grant itself a
site is not a consent model. `navigate` is gated on its destination, not the
tab's current origin.

Connected is not allowed, and the first op on a new origin is *supposed* to
fail. — Permission model

### 21. Never steal the user's focus

A trusted click in a background tab works via
`Emulation.setFocusEmulationEnabled` + `Page.setWebLifecycleState('active')`.
Activating the tab also works, and drags the user out of their work on every
click, which defeats the entire point of driving their real browser. — fix #12

---

## V. Reading the evidence

When an entry in `CLAUDE.md` says something is open, check whether a later entry
closed it. Several headings stayed stale for five entries after their own
retraction, because **a retraction at the bottom of a long entry does not
retract the heading** — the closed-shadow-root claim was wrong in four
user-facing places at once while the fix had shipped. — #67

When an entry names a file, function or flag, verify it still exists before
recommending it.
