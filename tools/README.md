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
  19 passed, 0 failed, 0 skipped of 19 suite(s); 1040 checks; 90.4s
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

**No suite requires the live extension or the WebSocket bridge.** The things
that do are the `diag_*` probes, and the pattern for writing one is in
CLAUDE.md under "Test-harness pattern".

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
