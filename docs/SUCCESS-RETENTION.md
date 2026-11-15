# Success retention vs full HTML — ATTEMPTED, NOT MEASURED

**Status: no number. The benchmark is unsound and the reason is contamination
in the industry-standard arm.** Written up rather than abandoned, because the
contamination is a real property of a widely-used dataset and the next person
to try this will hit it.

## The question

Every ruler in this project measures retention of ELEMENTS — recall, presence,
`lost_identities`, findability. None measures retention of SUCCESS. The field's
own benchmark says they come apart: [arXiv:2605.29397](https://arxiv.org/html/2605.29397)
evaluates 11 extractive reduction methods and its best retains **84% of success
on WorkArena and 89% on WebLinx**. We are a reduction method. So: given our
listing instead of the full page, does a model still pick the right element?

## Why there is no answer yet

### The baseline arm leaks the gold target

Mind2Web's `cleaned_html` carries `backend_node_id` attributes. Those ids are
**not in document order**, and the clicked target is allocated anomalously
early — apparently because the recorder resolved the clicked node over CDP
before snapshotting the DOM.

Measured across the 20 sampled actions:

| | |
|---|---|
| gold id allocated BEFORE `<html>`'s own id | **12 / 20 (60%)** |
| of those, gold among the first handful of ids on the page | 8 |

A judge found it independently, three for three by inspection, and **disclosed
it instead of using it** — noting that on one item the leak had changed its
answer from what task reasoning alone suggested.

Neither other arm has such a channel: our refs are a fresh document-order
counter and AX ids start at 1. So the baseline is scoreable from a signal that
is not the representation's content, and any comparison against it is void.

**Corroborating symptom, noticed before the cause was known:** the baseline
climbed 0.250 → 0.375 → 0.545 as successive judges worked through it, which is
what exploiting a partial side channel looks like. Its absolute level was
already suspicious — full cleaned HTML scores ~1.00 on element RECALL, so
0.375 was a signal about the instrument.

**FIXED, and it was not enough.** The ids were renumbered in document order
and verified: the gold precedes `<html>` in **0 of 16** pages, down from 12 of
20. The arm was then re-judged from scratch. What that bought was a fair
baseline on a substrate that still cannot carry the experiment — see below.

### The substrate defeats ALL THREE arms, each differently

This is the finding, and it is bigger than the leak.

| arm | how Mind2Web's snapshots break it |
|---|---|
| cleaned-html | leaked the target through id ordering (fixed) |
| ax-tree | **0 of 40 samples contain a single `href`** — the dataset strips them, so every `<a>` is AX-ignored and collapses to `generic` or is dropped. **14 of 20 AX pages contain no `link` role at all.** Targets are literally unaddressable |
| chromebridge | viewport-scoped by design, so a single-read test cannot follow the "scope into this region" the listing itself prints |

And two that hit everything equally:

* **No step VALUE.** `"CLICK"` with no target text leaves several items with no
  determinate answer for any representation. A judge on a Discogs item called
  it "a genuine ~50/50" between opening the account menu and clicking Lists,
  and declined rather than coin-flipping.
* **No CSS, so responsive duplicates are indistinguishable.** Six Flags ships
  FOUR identical copies of its utility nav; a judge located "Investors"
  correctly, picked the first of four in document order, and was wrong by
  construction. On an AMC item another judge answered the nav link when the
  gold was the menu BUTTON that opens the panel — it flagged that exact
  possibility itself, because open-state is unknowable without CSS.

**Three independent blind judges found three different ways the material
defeats the measurement, and each refused to guess rather than produce a
number I could have tabulated.** That is why there is no table here.

**This applies to published comparisons on this corpus too.** Anyone
benchmarking observation formats on Mind2Web snapshots is, to some degree,
measuring the corpus.

### A third, upstream limit

`fetch_mind2web.py` stores the operation as a bare `"CLICK"` / `"TYPE"` with no
VALUE. On a form with four empty fields the step is under-determined for EVERY
representation. A judge raised it unprompted. Same shape as #73's finding that
the fetcher keeps only `pos_candidates[0]`: the loader discarded data nobody
noticed was needed. Fixing needs a re-download.

## What the attempt did establish

- **Our viewport scoping is what would cost us on a single-read benchmark.**
  Repeatedly, our misses were the target sitting below the fold with the
  listing correctly naming the region and saying to scope into it. A live agent
  recovers in one call; a one-shot reader cannot. One judge put it exactly: on
  the same task, "the AX file has the form's content and no identifier; the
  ChromeBridge file has identifiers and not the form."
- **The comparable literature number comes from an agent LOOP**, so a fair
  version of this test must give each arm the follow-up call its own output
  asks for. Scoring one read is not the same experiment.

## Eight harness defects, six found by the judges

1. the judge file contained the arm label
2. …and the gold answer
3. page filenames leaked the arm
4. the AX arm was rendered with **no identifiers at all**, so it was
   unanswerable — two judges proved it independently and both warned that
   scoring it as-is would hand us a win "for a reason unrelated to
   representation quality"
5. the renderer was fixed and the pages were not rebuilt, so judges kept
   reading the broken files
6. matched pairs landed in the same batch, so a judge could compare
   representations directly
7. **our arm had no ref→id mapping and scored 0 by construction** — the
   scorer's docstring promised the mapping and the builder never wrote it
8. the first mapping read Chrome's runtime `backendNodeId` (a per-session
   counter) instead of the `backend_node_id` ATTRIBUTE in the saved HTML

Had 7 and 8 gone unnoticed, this would have published "ChromeBridge: 0%
success against full HTML".

## The rule this is an instance of

A result that flatters or damns the system gets re-derived before it is
believed (#16). Here it damned us, twice, and both times the cause was in the
instrument. The judges — blind, and told that an honest UNSURE beats a lucky
guess — were a better instrument than the instrument.
