# EVAL 7 — CLOSEOUT

16 runs, 8 tasks, 39 oracle conditions per arm, scored by the app's own business
events. Re-derivable from `tracks.json` + `runs.tsv` with `score.py` against a
live WebPageBench; raw verdicts in `scores.json`.

**Read `PREREG.md`'s five amendments before quoting anything here.** Three runs
of the first attempt were discarded and the reason is the most transferable
thing the eval produced.

## The result

| task | conds | CB met | CB calls | CIC met | CIC calls |
|---|---|---|---|---|---|
| rail2p | 10 | **9** | 21 | 7 | 18 |
| railpay | 8 | 8 | 28 | 8 | 54 |
| hoteldxb | 6 | 6 | 19 | 6 | 19 |
| hotel2rm | 5 | 5 | 13 | 5 | 10 |
| shop3 | 3 | 3 | 16 | 3 | 18 |
| filespdf | 3 | 3 | **6** | 3 | 11 |
| booksexp | 2 | 2 | 14 | 2 | 15 |
| grocat | 2 | 2 | **8** | 2 | 12 |
| **total** | **39** | **38** | **125** | **36** | **157** |

**H1 (PRIMARY — conditions satisfied): NULL.** One decided task of eight,
p = 1.0000 against a bar of p < 0.05. Reported as descriptive, per the
pre-registration's own rule for fewer than six decided pairs.

**H2 (tasks fully passed): 7/8 each.** The metric every previous head-to-head
here saturated on, saturating again — which the pre-registration named in
advance as itself a finding.

**H3 (turns): 125 to 157, −20%.** Descriptive only and explicitly subordinate:
#47 established this metric's noise exceeds the effects it gets used on.

**H4 (THE FALSIFIER) did not fire.** ChromeBridge satisfied no fewer conditions
in total and failed no task the other arm passed.

**H5 was a prediction that could have been wrong, and was right.** It said:
*"no significant difference on H1, and the two arms land within 15% of each
other on conditions."* 38 against 36 is **5.6%**. Recorded because a
pre-registration whose predictions are never checked is decoration.

## What that means, stated narrowly

**On these eight tasks the two toolsets are equally capable.** Both reached 7 of
8 complete, both satisfied 36+ of 39 conditions, and the one decided pair turned
on a judgement call about passenger identities rather than on anything a
representation can fix.

It does NOT say the representations are interchangeable — the per-pair reports
show them failing in different places for different reasons, and the call gap is
real even if it is noisy. It also says nothing about the consent model: one
grant covered all eight apps, so per-origin consent was never charged to either
arm.

**Difficulty is bounded externally.** The benchmark's own published leaderboard
gives these exact eight tasks at **74/192 = 38.5%** across 24 model×harness
runs, against a best published whole-benchmark run of 82.2%. `rail_book_to_cart
_2_passengers` is **0/24** there. So this is a hard subset, chosen for condition
count rather than difficulty, and the metric had room to move rather than
saturating. Both arms substantially outperform the published field — with the
caveat that those runs are scored all-conditions-or-fail while this eval's
primary metric is conditions satisfied, so the numbers are not directly
comparable.

## What the eval actually bought

**22 findings against ChromeBridge, every one from a live run.**

**Fixed during the eval, server-side, each ablated against the pre-fix code:**
the batch settle wording that contradicted the banner beside it; `filter="all"`
cutting its text block in silence; ref-less rows undisclosed in two sibling
renderers; a duplicate banner defeated by a ticking counter; `back` skipped for
a DOM change that cannot move history; a batch refusal that would not name the
tab the server had just made; delta rows with no parent context; `search_page`'s
ref and context printed as one unit.

**Recorded with evidence and held** (`docs/OPEN.md` 4b, 4d–4s): fifteen items,
most in `background.js` and held deliberately so every ChromeBridge run was one
build (Amendment 2).

**Two findings landed on work from THIS session**, which is the part worth
keeping: CT1c's cap advice, added after eval 6, cannot answer the page eval 7
put in front of it (4r); and #77's scoped-UNKNOWN note recommended a wasted call
three times in one run. A fix verified against the eval that produced it is not
verified against the next one.

**One finding arrived via the other arm.** Their agent described a defect in its
network reader; checking ours against the description found the same shape in
two tools (4n). The comparison is not the only thing a head-to-head produces.

**The defect no ruler here can see.** A quantity stepper whose `−` and `+` were
BOTH named `"1"` — the value adopted as the accessible name of both buttons,
where clicking the wrong one at quantity 1 removes the item. Both elements are
present, listed, named and clickable, so `measure_findability` scores them a hit
at 0.9996. That is the strongest argument in this eval for why live runs still
find what corpora cannot, and it is why "the representation is done" is not a
claim this closeout makes.

## The safety property

Both arms were instructed to work in a tab they create. **Across 15 runs, zero
hijacks on either arm**, verified by reading the two pre-existing tabs back at
their original URLs. The one hijack of the session was mine, in a setup call
before the eval, and was restored by hand.

The instruction is sufficient on both arms — and only because someone wrote it.
Their agent cannot batch a tab creation with a navigation, and the standalone
shortcut its own docs advertise navigates "the first tab in the session's
group", which is not guaranteed to be one it made: *"the advertised fast path is
unusable under the exact constraint most of these tasks impose."* Obeying costs
them 1–2 calls per task; our tab threading (#46) makes obeying free and
disobeying structurally difficult. **That is the capability difference with a
consequence attached, and it is not in the turn column.**

## Weaknesses, restated after the data

Everything the pre-registration listed still holds. n=8 with one run per cell,
against a measured **12–14% rerun noise floor** for observation-format A/Bs.
Six synthetic Russian-language apps from one team, v1 preprint, not peer
reviewed. Both arms can read the other's server instructions (Amendment 4) —
biased against the arm that tries the other's documented pattern, which is
theirs. And three runs were lost to a generator defect of mine that the
benchmark's own published results, not my reading of my own code, corrected
(Amendment 3).

**No server-side fix in this eval has been verified live** (Amendment 5). They
are fixtured and ablated; the live pass is owed and is the first thing after
this.
