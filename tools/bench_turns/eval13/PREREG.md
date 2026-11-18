# Eval 13 — repeatability on a local app

Written BEFORE either arm reported. Ground truth derived BEFORE the prompt
existed. Arm A had run; **nothing below was changed after seeing its result.**

## Why this exists, and what it is not

Evals 3, 5, 7, 9, 10 and 12 all need PUBLIC origins, and ChromeBridge's
per-origin consent gate refuses them until the owner clicks Allow. Four are
pending. **That blocks a public-site comparison and does not block this one:**
both toolsets reach `localhost` — verified this session, ChromeBridge is granted
there and Claude-in-Chrome navigated there.

**n=1 task. There is no statistical bar and none is claimed.** At one task no
sign test can reach p<0.05, so a p-value would be theatre. The question it CAN
answer is the one `eval10/PREREG.md` argues for and that no eval has yet run:
**what does it cost to do a completed task AGAIN?** One arm has record and
replay; the other has no record, no replay and no assertion.

## The task — identical prompt both arms, modulo the tool namespace

Sign in at `http://localhost:8787` as `ada@acme.test` / `demo-pass-1234`, open
Invoices, order by largest amount, open the highest, report its reference code
and customer name. **Then do the whole task a second time, using whatever the
toolset offers to make the second pass cheaper.**

The prompt names NO feature of either toolset, does not say a comparison is
happening, and does not hint that one side has a replay mechanism — the
capability has to show itself. Eval 4's headline had to be WITHDRAWN when its
prompt turned out to mandate the behaviour it measured.

## Ground truth, derived independently

Over plain HTTP with `urllib`, never by driving either arm:

    INV-1008 · Wayne Ent · 31,990 · REF-3381

The list is PAGINATED — 12 invoices, 5 rows a page — so the largest is not on
page one as it loads. A run that reads page one and answers is WRONG, which is
what makes the task need more than one hop.

## Measured

- **M1 (primary).** Tool calls for PASS 2, each arm.
- **M2.** Tool calls for PASS 1 — reported, not the headline; evals 9/10/12
  settled that axis and it sits inside the 12–14% rerun noise floor
  arXiv:2608.06171 measures for observation-format A/Bs.
- **M3 (falsifier).** Correctness against the ground truth above. If either arm
  is wrong this is a tooling failure, not a comparison.
- **M4.** Any point where a tool told the agent something false. Scored from the
  agent's own report AND from the transcript, never the report alone.

## Stated before the data, because they are the reasons to discount it

1. **Home turf.** `tools/saas_playground.py` is this project's own fixture. No
   generality claim is made. It was chosen because four public origins are
   ungranted, not because it flatters anyone.
2. **n=1, one run per arm, no drift control.**
3. **Arms run SERIALLY** — six parallel agents corrupted each other's tab groups
   in an earlier eval.
4. **The ChromeBridge arm ran against the SHIPPED extension in the owner's
   Chrome, which predates this session's fixes.** The task is read-only and
   touches no combobox, so those code paths are not exercised — stated rather
   than assumed away.
5. **Not a fair fight and not meant to be.** One arm has the feature. The honest
   claim is "this capability exists and here is what it did", never "we browse
   better".
6. **A prediction that could fail, recorded before arm B ran:** the arm with
   replay should make pass 2 cheaper than pass 1. **If it does not, that is the
   finding and it gets reported as the headline, not buried.**
