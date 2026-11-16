# Self-audit of this session's seven commits

Three agents were spawned to attack this work — a pattern hunt, a
flow-fragility review, and a deliberately uninformed review of the diff. All
three died partway on the account's weekly API limit. This is the part of their
brief I could run myself, since local tools (the suites, the frozen corpus,
Playwright, the live browser) need no API call.

**What this is NOT:** an independent review. I wrote the code and I wrote this,
so it carries the bias the agents existed to remove. It is measurement, which is
the half of their job that does not depend on who runs it. The three agents are
resumable and should still run.

---

## 1. Vacuous-fixture sweep — CLEAN

The hazard: a check that passes against the broken code it claims to test. This
project has found seven of those, and the only way to know is to run each one
against the code it predates.

Method: `git archive 25cb8d9` (the commit before this session) into a shadow
tree, copy **every** current `tools/test_*` over it, run the whole suite there.
Every check added this session must appear as a failure; every control must not.

| added this session | pre-session result |
|---|---|
| `CT1d`, `CT1e` (cap notice names containment) | **FAIL** |
| `C20e` (`format` names its trade) | **FAIL** |
| `C38` (climb stop set == field stop set) | **FAIL** |
| `C39` (a step whose tool takes no tabId) | **FAIL**, with the live error verbatim |
| `T24b` (a listing that printed nothing still stamped) | **FAIL** |
| `Q1aa`, `Q1ab` (the record climb) | **FAIL**, `context='Korzina'` / `'Olives'` |
| `NB3`, `NB3b` (a label three containers up) | **FAIL**, `near=''` |
| `NB3c`, `NB3d` (the W19 leak) | **FAIL**, `near='GHOSTLABEL'` |
| `NRQ1` (`near=` vs a declared submit value) | **FAIL** |
| `FLG1`–`FLG5` (recorded language) | **AttributeError: 'Flow' object has no attribute 'lang'** — cannot construct at all |

And the controls — `C39b`, `Q1ab2`, `Q1ac`, `Q1ad`, `Q1ae`, `NRQ1b`, `NRQ1c`,
`CT1c` — are absent from the failure list, which is what makes them controls:
they pass in **both** arms. `CT1c` matters most of those, because it is the
eval-6 answer that the eval-7 fix had to not trade away.

**Nothing added this session passes against the code it was written for.**

## 2. The climb's cost on a hostile page — MEASURED, no cap added

`_isRecord` computes a depth-3 subtree signature for every sibling until it
finds a second of the same kind. The shape that could hurt is a parent with
thousands of children, none matching, so every scan runs to completion — per
hop, per hit, up to 8 hops.

Three arms on one page load, order rotated per replicate (#19), 25 hits per run:

| page | old climb | new climb | delta |
|---|---|---|---|
| 4000 IDENTICAL siblings (a real record list) | 20.46ms | 20.54ms | **+0.08ms** |
| 800 UNIQUE siblings, each ~73 nodes deep | 28.36ms | 31.50ms | **+3.14ms** |
| 4000 UNIQUE siblings, shallow — worst found | 20.68ms | 32.28ms | **+11.60ms** |

Two things the numbers say that reading the code did not. The dominant term is
sibling **count**, not subtree depth — `_sig`'s depth bound is doing its job,
and the deep case is *cheaper* than the wide one. And the early exit makes a
real record list free **regardless of where in it the hit sits**, because the
first two children already match the kind, so position never enters it.

11.86ms is half a bridge hop and about 0.3% of a model turn (#38).

**No cap was added, deliberately.** Capping the sibling scan would make a record
list longer than the cap stop being recognised — a wrong answer bought with a
chosen number. #77 records that exact trade going bad on the mutation ring,
where a per-batch store bound meant to control cost ended up deciding answers.

## 3. The pattern surface beyond regex literals — ONE FINDING

`tools/audit_patterns.py` reports **292 sites across 9 files**: 10 `wordlist`
(all CSS values, HTML tag names, icon-library class prefixes, Tailwind tokens,
option sentinels and the caller's own boolean vocabulary) and 4
`class-substring` (three of which are `/\s+/` whitespace splits — two of those
are mine, from `_sig`/`_kind`, and are shape normalisation, not matching).

It sees **regex literals only**, so I swept the rest by hand:

| scan | result |
|---|---|
| `.includes/.startsWith/.endsWith/.indexOf('<english>')` in `background.js` | 6 hits — all against an ARIA role VALUE (`menuitem`), an ATTRIBUTE NAME (`placeholder`, `data-`, `aria-`), or our own section vocabulary |
| `classList.contains(...)` anywhere | **0 sites** |
| a text/label/name variable matched against a literal | 1 hit: `accessibleName.indexOf('<')`, a structural character, not a word |
| Python `'literal' in variable` across `mcp_server.py` + `core/flows/*` | 8 hits — dict keys, a parameter name, and strings **this repo itself emits** |

**So the standing claim holds under a wider scan than the auditor performs: no
natural-language matcher reads PAGE text anywhere.** The only English-string
matching left is against strings we emit, which is a different and much weaker
hazard — the string can be reworded, and then the reader silently stops reading.

**The finding.** `FD19` pins the six NOT-DONE and NO-EFFECT markers against the
file that emits them, precisely so a reword fails a test instead of disarming a
guard. There is a **seventh** marker of the same kind and it was pinned by
nothing: `core/flows/recorder.py` watches `get_url`'s result for `"IN FLIGHT"`
so it does not compile a read taken mid-navigation into a flow. Its only other
occurrence was a FIXTURE supplying its own copy of the string — which pins
nothing, because rewording the emitter leaves the fixture green while the real
path breaks. `FD19g` closes it, and fires on a planted reword
(`mcp_server emits=False`).

## 4. What I did NOT audit

Named so the resumed agents do not assume it was covered:

- The wider pattern surface. `audit_patterns.py` sees regex literals only — a
  previous audit put that at ~26% of the real surface — and the `.includes` /
  `.startsWith` / `classList.contains` sweep was the dead agent's brief.
- Conceptual fragility of record/replay: false PASS scenarios, the oracle
  problem, and what DOM mutation a real app performs that
  `audit_flow_resolve.py` does not model.
- An uninformed read of the diff. Everything above was measured by the person
  who wrote the thing being measured.
