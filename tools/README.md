# tools/

Two kinds of thing live here, and the difference matters:

- **Suites** (`test_*.py`, `test_*.js`) — deterministic, offline, pass/fail.
  They are the regression net around `extension/background.js` (443 KB) and
  `mcp_server.py`. Run them as a set with `run_tests.py`.
- **Probes** (`audit_*`, `bench_*`, `measure_*`, `diag_*`, `freeze_corpus.py`,
  `fetch_mind2web.py`) — measurement harnesses. They hit live sites, a frozen
  HAR corpus or the running extension, they take minutes to hours, and their
  output is a number to interpret, not a verdict. **Not run by CI.**

## Run everything

```powershell
.venv\Scripts\python.exe tools\run_tests.py
```

```
  SUITE       GROUP    STATUS      TIME  CHECKS
  --------------------------------------------------
  delta       unit     PASS        3.3s  10/10
  ...
  21 passed, 0 failed, 0 skipped of 21 suite(s); 1603 checks; 153s
  ALL GREEN
```

`--list` is the authoritative inventory — it is generated from the filesystem,
so it cannot drift the way the tables below can.

Exit code is non-zero if any suite fails. Useful flags:

| Flag | Effect |
|------|--------|
| `--only find,truncate` | just those suites (short names, as in `--list`) |
| `--skip pixels` | everything except those |
| `--group unit` | the browser-free suites only |
| `--skip-browser` | same thing, spelled as an intent |
| `-q` / `--quiet` | summary table and total only |
| `-v` / `--verbose` | stream each suite's full log as it runs |
| `--strict` | a SKIPPED suite counts as a failure (CI uses this) |
| `--list` | the inventory below, generated from the filesystem |
| `--timeout SEC` | per-suite cap (default 300s; the slowest suite is ~8s) |

Discovery is by source inspection, not a hardcoded list — add a
`tools/test_yours.py` and it is picked up with no edit to `run_tests.py`.

## Groups

**`unit`** — no browser, no network, no extension.

| Suite | Runner | Pins |
|-------|--------|------|
| `batch` | python | `browser_batch`: the pre-flight, the two page-change guards, tab threading |
| `contracts` | python | the boundaries nothing else crosses — injected functions are self-contained, the server and extension agree on a string, agent-facing prose names real tools, the README states what is served |
| `delta` | python | delta reads: what changed since the last listing, and when to refuse |
| `find` | python | `find`'s scorer and formatter (coverage gate, non-ASCII, href/src vocabulary) |
| `flows` | python | recorded flows: the descriptor ladder, variables, preconditions, the repair loop that proposes and never writes |
| `ops` | node | `handleOp` — the service worker's op router, in a `node:vm` with a mocked `chrome` |
| `patterns` | python | no `\b` beside a non-ASCII alternative, no ASCII class gating page text, and the auditor still fires |
| `permissions` | node | the extension's permission/consent gate |
| `steer` | python | the steering channel: a side-panel message rides the next tool result, exactly once, fenced as the user's words — and never drains where it would be buried |
| `truncate` | python | `_truncate` and `get_page_text`: truncation must never remove the payload |

**`browser`** — headless Chromium via Playwright. Each suite extracts the real
page-side functions verbatim from `extension/background.js` (via `_extract.py`)
and runs them against a fixture, so what is tested is the shipped code.

| Suite | Pins |
|-------|------|
| `folding` | repeated-record folding compresses without costing a ref or an href |
| `frames` | cross-origin iframe geometry: frame-local coords + shell offset == true position |
| `gaps` | 48-probe inventory over `gap_fixture.html` (see the caveat below) |
| `generality` | non-Latin labels, shadow DOM, editors, detail levels, media |
| `ledger` | the drop ledger: every removed element carries a rule id |
| `panel` | the side panel itself, rendered with `chrome.*` stubbed — the steering composer, its three delivery states, and that the card renders without throwing |
| `pixels` | device-pixel to CSS-pixel screenshot normalisation at 1.0 / 1.25 / 2.0 |
| `readiness` | the page-readiness probe (in-flight requests, `aria-busy`, progressbars) |
| `shadow` | open **and closed** shadow roots: collect, click and type through `window.__mmidReg` |
| `submit` | the submit picker — the only function here that presses a button, answering only from what the document declares |
| `widgets` | `widget_zoo.html` — combobox/popover/`aria-controls` shapes that broke live |

Everything the browser group needs is served locally (`file://`, `page.route`
interception, or an ephemeral `127.0.0.1` HTTP server), so it runs offline and
in CI. It needs two things `requirements.txt` does not provide:

```powershell
.venv\Scripts\python.exe -m pip install playwright
.venv\Scripts\python.exe -m playwright install chromium
```

Without them the group is **skipped with a reason**, not failed — so a
developer who has not installed Playwright still gets a useful run. CI passes
`--strict` so that a skip there is a failure.

**No suite requires the live extension or the WebSocket bridge.** The things **CORRECTED (#94): `run_flows.py` has required both since #50, and `audit_frames_live.py` now does too — that is how the cross-origin path is exercised at all.**
that do are the `diag_*` probes, and the pattern for writing one is in
CLAUDE.md under "Test-harness pattern".

## Probes that carry a self-test

A probe is not a suite — `run_tests.py` does not run these, and a number from
one is worth nothing until the probe has been shown to DETECT something.
`audit_patterns.py` self-tests against three historical bugs for that reason;
all three had passed code review before they were measured.

| probe | self-test | what it proves |
|---|---|---|
| `audit_patterns.py` | built in | fires on the three historical pattern bugs in their pre-fix form |
| `audit_window_declarations.py` | `--fire`, plus `--drift N` | answers two questions nothing else here asks: does ANY declaration separate "row 3 of the rendered WINDOW" from "row 3 of the DATASET" (`aria-setsize`/`aria-rowcount` against rendered peers), and WHAT is the unwitnessable ordinal residue made of. `--fire` plants a positive for every detector AND for every Q2 bucket, with a plain `<ul>` of identical buttons as the negative control that must report 0 windowed. Answer: **1 of 2,531 tied crowds on 1 of 93 sites**, `aria-rowcount` on zero — see `docs/research/FLOW-SILENT-BIND-2026-11.md` §4.3 |
| `audit_atoms_safety.py` | `--self-test` | the arm `audit_record_witness.py` does not have: **removing the TARGET's record**, where the only correct outcome is a refusal. Seven cases, and three of them are the controls that stop "refuse whenever the crowd changed size" from passing — a re-sort, a DIFFERENT record removed, and a cell edited on an unchanged crowd must all still RESOLVE. It also reports the coverage of the SHIPPED `recordAtoms` (`closest('tr,li,dl,article,figure,fieldset')`), which is not the structural definition `audit_record_witness.py` measured. See `docs/research/FLOW-SILENT-BIND-2026-11.md` |
| `measure_findability.py --self-test` | `--self-test` | **FAILS against the pre-#74 scorer** and passes against the fix, with a known-miss control (a deliberately blanked app shell) passing in both arms |
| `audit_opacity.py` | built in | the `probe` arm wraps the gate in a recorder that returns the SAME value, so `probe == base` entry counts prove observing changed nothing; and `ablate − base` must never EXCEED the recorded population, which would mean the recorder missed elements |
| `audit_frames.py` | `--fixtures`, plus a built-in control | the corpus returns **0 of 128 frames** declaring a page-level trigger; the SAME census over those pages' TOP documents returns 91 dialog nodes on 31 sites, which is what proves the zero is the sample rather than the probe. `--fixtures` builds the shapes the corpus cannot hold (HARs are captured after consent) from two ports, so cross-origin is real |
| `audit_cmp_frames.py` | `--selftest` (four cases, both directions) | the FREQUENCY half of `audit_frames.py`'s correctness gap, which the frozen corpus cannot answer because its HARs were captured AFTER consent. Live sites in a FRESH profile with consent never given, through the real extension (`audit_frames_live.Rig`), guarded out-of-sample by `audit_generality_live.EXCLUDED`. `--selftest` needs all four: a cross-origin blocking sheet FIRES and gets no banner (the gap), an ordinary cross-origin frame is SILENT (or the detector reports everything), the same sheet served SAME-ORIGIN does raise the banner (the control arm works, so the variable is the boundary), and a corner chat frame fires but classifies INCIDENTAL (the blocking split discriminates). Answer: **0 of 143 live sites**, with the mechanism — see `docs/research/CMP-FRAMES-2026-11.md` |
| `measure_findability_at_stage.py` | `--selftest`, plus `--fire` on LIVE markup | the same question as `measure_findability` but AFTER up to four declared interactions, composing #89's driver with #74's metric. `--selftest` drives a fixture through a real interaction and requires five things: a control revealed by it is reachable by its printed identity; #74's sole-carrier shape is too; **the generic plant** — the same control with its identity moved off it — scores a MISS; **#74's own defect reproduced** — stripping `subtreeNameSole` from the entry puts `find` back in its pre-#74 state without touching the extension, and the same tile must then score `zero-match`; and a row the listing BLANKS is routed to its own question instead of being asked for a string the listing never printed. `--fire` repeats the plant on five live sites at the deepest stage reached (5/5 fired, 8/8 hits → 0). `bridge_races` must read 0: `find` reads its bridge from a module global, and with sites running concurrently one site's query was briefly being scored against another's entries |
| `audit_name_correctness.py` | `--selftest`, plus `--fire` on LIVE markup and `--plant-in-corpus` | the only question no other ruler here can ask: is the name we PRINT the RIGHT name? It scores our AccName derivation against **Chrome's own** `Accessibility.getFullAXTree`, joined by `backendNodeId` from one `DOM.getDocument{pierce:true}`, at first paint and after up to four declared interactions (#89's driver, reused). `--selftest` requires three things: the comparator FIRES on a genuine spec disagreement (AccName step 2F's separator, #28's shape); five CONTROLS must AGREE, without which a probe reporting everything as a disagreement would pass; and a PLANTED arm moves an element's `aria-label` after collection so the join-and-compare path is proven independently of what the collector happens to do. A planted name only counts where it reached the COMPARED population, which the per-mmid disposition states. `--candidate-ab` runs both collectors on the SAME page load against ONE oracle read, so run-order drift cannot align with the arm, and its arms are BIDIRECTIONAL -- each candidate carries both anchors and the direction is decided from the source, so it reconstructs the pre-fix arm after the fix ships instead of expiring the way `audit_retext_*` did. `--quoting` parses every printed row back the way a consumer would and counts the ones that come back truncated |
| `measure_text_flows.py` | `--controls` (always on), `--replicates` | a random nonce must be found by NO arm (it was found by `search_page` on 8 states out of 8 until the miss detector was fixed — the readiness note prepends to the miss sentence, so a `startswith("No match")` test reports every miss as a hit); the text-ablated listing must be a SUBSET of the full one; a state with no required values at all is named rather than scored 1.000; and two replicates on identical code must agree item for item |

`measure_findability` exists because every other ruler here measures PRESENCE
and #74 found 118 elements that were present in all of them and unreachable by
their own printed label. **It is a population measurement, not a regression
guard**: ablating the #74 fix and re-running over 8 frozen sites gives the
identical number, because that corpus does not contain #74's shape. The guard
is `F40`/`F40b` in `test_find.py` plus the `--self-test` above. Running it with
no browser:

```
python tools/measure_findability.py --self-test     # no corpus, no browser
python tools/measure_findability.py --n 20          # the population number
```

## Caveat: `test_gaps.py` has no exit code

It is an inventory, not a pass/fail suite — it ends with `asyncio.run(main())`
and no `sys.exit`, so it returns 0 even when it reports `MISSED` probes. Its
invariant (CLAUDE.md limitation #2) is "48 checks, 0 MISS", which nothing
enforced.

`run_tests.py` guards it by pattern instead, declared in the `OVERRIDES` table
with its reasoning: any non-zero `N MISSED` fails the run, and `N PARTIAL`
prints a warning. The suite itself is not modified — a runner does not edit the
tests it runs. The same table also creates `temp/dom_audit/`, which the suite
writes to without creating; `temp/` is gitignored, so on a fresh clone (every
CI run) that would otherwise be a `FileNotFoundError` after all 48 probes had
already passed.

If `test_gaps.py` ever grows a real exit code, delete its entry from
`OVERRIDES`.

## CI

`.github/workflows/ci.yml` runs on push and pull request:

- **extension** — `node --check` on `background.js`, `panel.js`,
  `listener_tag.js`, and a `manifest.json` parse. Seconds, and catches the
  breakage no Python suite can see (nothing imports `background.js` as JS
  except `test_ops.js`).
- **tests** — Python 3.12 + Node 22, every suite, `--strict`.
- **unit-floor** — the `unit` group on Python 3.10 and 3.13, which is the range
  `pyproject.toml` advertises and nothing else checks.
