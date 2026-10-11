<div align="center">

<img src="extension/icons/icon128.png" width="76" alt="">

# ChromeBridge

### Starts as you.

Let Claude Code drive your **real Chrome** — with your logins, cookies and
extensions already there.

`Open source` · `Apache-2.0` · `No API keys`

[![CI](https://github.com/AryanGurav106/ChromeBridge/actions/workflows/ci.yml/badge.svg)](https://github.com/AryanGurav106/ChromeBridge/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20–%203.13-blue.svg)](pyproject.toml)
[![Tools](https://img.shields.io/badge/MCP-31%20tools-FF6B35.svg)](#what-claude-gets)
[![Checks](https://img.shields.io/badge/tests-1%2C042%20checks-success.svg)](#running-the-tests)

</div>

---

Other agents start logged out. A Playwright or Puppeteer agent opens a fresh,
empty Chromium — so it cannot touch the apps that matter: your CRM, your
dashboards, your internal tools, your email.

ChromeBridge attaches to the browser you already use.

```
> find the default gzip_comp_level in the nginx docs

  browser_batch   tabs_create_mcp → navigate(nginx.org/…/ngx_http_gzip_module)
                  → search_page("gzip_comp_level")
  ⟵  <a "gzip_comp_level"@0>  Syntax: gzip_comp_level level;  |  Default: gzip_comp_level 1;

  The default is 1.                                             2 turns · 4.1 s
```

Claude Code **is** the agent loop, so every model call runs on your Claude
subscription and this server holds no LLM key of its own.

<br>

|  | Playwright / Puppeteer agent | **ChromeBridge** |
|---|---|---|
| Browser | fresh Chromium, logged out | the one you are signed into |
| Acts as | nobody | **you** — the same trusted-input path as Claude-in-Chrome |
| Model key | yours to supply | none; it is your Claude Code session |
| Consent | all or nothing | per origin, revocable, with a pause switch |
| Re-running a known flow | re-prompt the model | replay a recorded file, for nothing |

It works on framework-heavy SPAs — Radix, shadcn, HeadlessUI, MUI — with no
site-specific code: full pointer-event sequences, automatic escalation to
trusted CDP input when an untrusted click has no effect, and atomic React-safe
form fills. Clicks land in a background tab without stealing your focus.

---

## As accurate, and faster. All measured.

Pre-registered head-to-head against Claude-in-Chrome. 19 tasks across 7
archetypes, 38 runs, one at a time, arm order rotated. Tasks were written blind
and ground truth was re-derived by an independent referee.

| | Claude-in-Chrome | **ChromeBridge** | |
|---|---|---|---|
| Turns | 240 | **117** | 15/17 decided pairs, **p = 0.0023** |
| Wall clock | 3,674 s | **1,662 s** | 17/19 pairs, **p = 0.0007** |
| Turns to first page content | 4 | **2** | 2 on all 19 runs, no spread |
| Correctness | 19/19 | **19/19** | tie — and that is the point |

> **Read these caveats before quoting the numbers.**
> **Correctness cannot discriminate.** Both arms are the same model, so the
> ceiling is Claude's, not the tool's; it is recorded as a *falsifier* — had
> ours dropped below theirs, the turn result would have been rejected outright.
> **A large share of the margin is the other arm's own defects**, not our
> representation; excluding its four worst runs the totals are 72 v 127.
> **On the one archetype where both arms ran clean we are level.** Three
> earlier pre-registered evals came back ties. The consent gate was off during
> the runs, so these numbers say nothing about what consent costs.
> → **[BENCHMARK.md](BENCHMARK.md)** · harness in `tools/bench_turns/`

And on how the page is *represented* — same labelled actions, one metric
definition, 16 sites never used in development:

| representation | target recall | median tokens | size |
|---|---|---|---|
| **ChromeBridge** | **96.0%** | **1,242** | **1.00×** |
| Chrome accessibility tree | 100.0% | 8,886 | 7.15× |
| MindAct `cleaned_html` | 100.0% | 41,716 | 33.59× |

Four points behind on recall for a seventh of the tokens — and the
accessibility tree needs a debugger attach that Chrome refuses outright on
password-manager pages.

---

## Install

**You need** Python 3.10+ (3.12 is what this is developed against), Google
Chrome, and Claude Code. Node 22 and Playwright are needed *only* to run the
test suites.

```bash
git clone https://github.com/AryanGurav106/ChromeBridge.git
cd ChromeBridge
```

**1 · Install the Python side**

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .      # Windows
```
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .              # macOS / Linux
```

Use the **editable** install. A plain `pip install .` copies `mcp_server.py`
into `site-packages`, where it resolves `.env` and the repo `.venv` relative to
its own file — and never finds them.

**2 · Load the extension**

`chrome://extensions` → **Developer mode** → **Load unpacked** → select
`extension/`. Pin ChromeBridge; its icon opens the side panel.

**3 · Pair it with the server, once**

Start Claude Code in this folder. On first run the server **generates a
`BRIDGE_TOKEN` into your `.env`**. Copy that value into the side panel's Token
field → **Save & Connect**. The pill turns green. Both sides remember it.

The project-scope `.mcp.json` registers the server automatically, so opening
Claude Code here is enough. If your layout is unusual, see **Registering the
server by hand** near the bottom.

**4 · Allow the first site**

**Connected is not allowed.** The first op on a new origin is *supposed* to be
refused — that is the consent model working, not a failure. The side panel
raises **Permission requested — Allow this site**; click it and tell Claude to
retry. Grants are per origin, listed with a **Revoke** button, and written only
by the panel. **Pause** freezes everything instantly.

---

## What Claude gets

**31 MCP tools.** The names and schemas mirror Claude-in-Chrome, so a model
that knows one knows the other.

| | |
|---|---|
| **Observe** | `read_page` · `get_page_text` · `find` · `read_interactive_elements` |
| **Ask exactly** | `query_elements` — CSS query and counting, the total never capped · `search_page` — grep over rendered text · `accessible_names` |
| **Act** | `navigate` · `computer` — trusted click/drag/scroll/key/type, screenshot · `form_input` · `fill_form` · `file_upload` · `upload_image` · `resize_window` |
| **Record** | `record_flow` — start / stop / **patch** · `run_flow` |
| **Tabs** | `tabs_context_mcp` · `tabs_create_mcp` · `tabs_close_mcp` · `get_url` |
| **Inspect** | `javascript_tool` · `read_console_messages` · `read_network_requests` · `debug_targets` · `sw_info` |
| **Page-declared** | `page_tools` · `call_page_tool` — WebMCP · `save_as_pdf` · `dismiss_dialog` |
| **Compose** | `browser_batch` · `gif_creator` |

`query_elements` and `search_page` exist so "how many rows does this table
have" returns a real count rather than an estimate.

Three tools have no Claude-in-Chrome equivalent:

**`fill_form`** fills an entire multi-field form — text, comboboxes,
checkboxes — and optionally submits, in **one** call. Every text write is
batched into a single page-context script, because typing into field A
re-renders a React form and orphans the references to B through N. Submit
detection is **structure-only**: `type="submit"`, or HTML's implicit submit. If
the document declares nothing it refuses and names the candidates, because two
candidates is a question, not a coin flip between *Save* and *Delete account*.

**`browser_batch`** chains calls in one round trip and pre-flights every step
before running any. A page change stops only the steps that name a stale
element reference; observations keep running, so `navigate → read_page` is one
turn rather than two.

**`record_flow` / `run_flow`** — below.

---

## Record once. It keeps testing itself.

Asking Claude to do something costs a model call per step. Asking again
tomorrow costs the same again. A flow is that run turned into a test you can
replay **for nothing**.

```
record_flow("start", "signup")          … drive the browser normally …
record_flow("stop")                     → flows/signup.flow.json · 5 steps, 4 asserted

run_flow("signup")                      PASSED 5/5 in 0.31 s
```

**It records the agent, not you.** Every other record-and-replay tool watches a
*person* click, and a demonstration says what was done and nothing about what
should then be true — which is why they all make you write the checks by hand.
Claude already checks its own work as it goes: it reads the page back, counts
the rows, searches for the text it expected. Those checks *are* the assertions,
so the test arrives with them already in it.

**A step cannot store "the third button."** Buttons move and frameworks
renumber on every render, so a step stores what the page *declares* — tag,
role, accessible name, the landmark and heading above it, and a link's
destination as a fallback. On replay it works down that ladder until exactly
one element answers. Measured across 26 sites and 2,726 descriptors under six
kinds of page change: **0% resolved to the wrong element.** The rungs are
measured, not chosen — 37 frozen sites and 12,030 controls decided which fields
earn a place.

**When the page moves, it says so.** A suite that quietly fixes itself is worth
less than no suite, because you stop finding out when your app changed. So the
repair is a conversation:

```
run_flow("records-tab")
   PASSED 2/2 in 9.19 s
   step 1 matched on its declared destination — the page's labels have moved.
   Proposed: 'Records 43' → 'Records 44'
   Apply with record_flow("patch", …) — nothing is written until you do.

record_flow("patch", "records-tab")     ← your call, as its own turn in your transcript
   Updated flows/records-tab.flow.json — 1 target rewritten

run_flow("records-tab")                 PASSED 2/2 in 4.70 s
```

**What it refuses to do:** guess between two matches; take a position after the
crowd around it changed; relax an assertion to make a step pass; or store a
password — a password field becomes a named environment variable, and replay
refuses to run rather than type an empty string.

---

## Why you might not want this

The honest list. Several are Chrome policy, not bugs we can fix.

- **Trusted input dies on password-manager login pages.** Chrome refuses
  `chrome.debugger.attach` for a whole tab if *any* frame in it belongs to
  another extension — and password managers inject exactly there. Reading,
  `find`, `fill_form` and untrusted clicks all keep working; the error names
  the offending extension.
- **A tab can lose trusted input permanently** after an input op that
  navigates. Not ours — Playwright's own mouse fails identically on the same
  tab. The tool detects it and names the verified recovery rather than
  reporting a click that never landed.
- **Linux has never driven a real Chrome.** CI runs every suite there; Windows
  and macOS are both exercised end to end. The docs say *untested*, not
  *unsupported*.
- **One Chrome, one bridge, one session.** A second Claude Code session gets a
  live server nobody talks to.
- **A yellow "is debugging" infobar** appears whenever the debugger is
  attached. Chrome does not allow suppressing it.
- **Chrome's own surfaces can never be driven** — `chrome://`, other
  extensions' pages, `devtools://`. No grant unlocks them.
- **`find` is lexical, not semantic.** Given a descriptor it puts the target in
  the top 3 about 75% of the time; given a *goal* it scores exactly zero.
  Reading the listing and choosing is the model's job.
- **Readiness on a chatty SPA** is a document-level signal. An app that has
  committed its document and is still painting rows is outside what it
  measures.

Every one of these is below in **Known issues and limitations, in detail** —
with what was measured, and what the recovery is.

---

## Two small parts. Everything stays local.

```
┌──────────────┐  stdio MCP  ┌───────────────┐ ws://127.0.0.1:8765-74 ┌──────────────────┐
│  Claude Code │ ◄─────────► │ mcp_server.py │ ◄────────────────────► │ Chrome extension │ → your real tabs
└──────────────┘   JSON-RPC  └───────────────┘  token + protocol v1   └──────────────────┘
   the agent loop                31 tools           single client        per-origin gate ↑
```

`read_page` runs in the page context, tags every interactive element and
returns an indented tree under the page's own structure, with repeated records
folded positionally. What an element *is* comes only from what the document
declares — HTML interactive tags, ARIA roles, registered listeners,
`cursor: pointer`. **No class name, font name, framework name, pixel size or
wordlist decides whether an element exists.** That rule is enforced by a test,
not by convention.

---

## Running the tests

```powershell
.venv\Scripts\python.exe tools\run_tests.py            # Windows
```
```bash
.venv/bin/python tools/run_tests.py                    # POSIX (run on macOS; CI runs it on Linux)
```

**19 suites, 1,042 checks, about 90 seconds.** Nine are browser-free; the other
ten drive headless Chromium and need two packages that are deliberately not
runtime dependencies:

```bash
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install chromium
```

Without them the browser group is **skipped with a reason**, not failed.
`--list` prints the real inventory, `--group unit` runs only the browser-free
suites, and `--strict` turns a skip into a failure (CI uses it).

One more is worth running by hand, because it is the only suite that crosses
every boundary at once — a real Chrome, the real unpacked extension, the real
WebSocket bridge, the real op router and the real MCP tool functions:

```bash
.venv/bin/python tools/run_flows.py --playground --local-only
.venv/bin/python tools/run_flows.py --check-only     # no browser; validates every flow file
```

It starts its own fixture app and grants the origin inside a **throwaway Chrome
profile it creates and destroys** — the gate is satisfied, never bypassed.
Every other suite injects page functions directly, which is exactly why three
features in this project's history shipped broken behind green fixtures.

---

## You decide where Claude can act

- The bridge binds **127.0.0.1 only** and speaks to at most one client.
- A shared `BRIDGE_TOKEN` gates the handshake; a mismatch closes with 1008, a
  protocol-version mismatch with 4001.
- Ops are **default-deny per origin**. Anything not on the small ungated list
  (ping, diagnostics, tab create/close/list, url, window resize, debugger
  detach) needs a grant for that exact origin. **New ops are gated by
  omission** — the intended failure direction.
- The permission table is read from storage on **every** op, so a revoke or a
  pause takes effect on the very next one; a table that cannot be read denies.
- `navigate` is gated on its **destination**, not the tab's current URL —
  otherwise any granted site would be a doorway to every ungranted one.
- Grants are written **only** by the side panel. The service worker cannot
  grant itself a site.
- `type="password"` values are never printed into a listing: the field shows as
  occupied, contents withheld.
- The server holds no LLM key and makes no network calls of its own.

Pinned by 22 checks in `tools/test_permissions.js`.

---

## More reading

| | |
|---|---|
| **[BENCHMARK.md](BENCHMARK.md)** | the head-to-head, its methodology and every caveat |
| **[EXTENSION_SETUP.md](EXTENSION_SETUP.md)** | extension install, pairing and troubleshooting in detail |
| **[CLAUDE.md](CLAUDE.md)** | the engineering log — architecture, every numbered fix, and what was measured and rejected. Read this first if you are changing the code |
| **[FLOW_RECORDER_PLAN.md](FLOW_RECORDER_PLAN.md)** | the flow design, the prior art, and the alternatives rejected with numbers |
| **[AUDIT_DOM_GENERALITY.md](AUDIT_DOM_GENERALITY.md)** | does the collector generalise? measured across 106 live sites |
| **[CHROME_ATTACH_PLAN.md](CHROME_ATTACH_PLAN.md)** | why an extension, and not `--remote-debugging-port` |
| **[tools/README.md](tools/README.md)** | every test suite and measurement probe |
| **[flows/](flows/)** | the recorded flows — small JSON files meant to be read in a diff |

---

<details>
<summary><b>Registering the server by hand</b></summary>

<br>

`.mcp.json` is deliberately portable — no machine's absolute venv path is baked
in:

```json
"chromebridge": {
  "command": "${CHROMEBRIDGE_PYTHON:-python}",
  "args": ["${CHROMEBRIDGE_ROOT:-.}/mcp_server.py"]
}
```

Facts measured about that expansion, each one an afternoon if assumed wrong:

- `${VAR:-default}` **does** expand.
- A bare unset `${VAR}` does **not** — the server simply fails to start.
- `${CLAUDE_PROJECT_DIR}` does **not** expand in `.mcp.json`.
- The default `.` resolves against **the directory Claude Code was launched
  from**, not the directory `.mcp.json` lives in.

So the defaults work when you launch Claude Code from the repo root with a
`python` on PATH. If either is untrue for you:

```powershell
$env:CHROMEBRIDGE_PYTHON = "C:\path\to\ChromeBridge\.venv\Scripts\python.exe"
$env:CHROMEBRIDGE_ROOT   = "C:\path\to\ChromeBridge"
```
```bash
export CHROMEBRIDGE_PYTHON="/path/to/ChromeBridge/.venv/bin/python"
export CHROMEBRIDGE_ROOT="/path/to/ChromeBridge"
```

You do not usually need `CHROMEBRIDGE_PYTHON`: if the interpreter that launched
`mcp_server.py` cannot `import mcp`, the server re-execs itself under this
repo's `.venv` once and carries on. Verified on macOS — a Homebrew `python3`
with no `mcp` installed hands over and serves all 31 tools.

To register globally instead of per-project:

```powershell
claude mcp add chromebridge -- "C:\path\to\ChromeBridge\.venv\Scripts\python.exe" "C:\path\to\ChromeBridge\mcp_server.py"
```
```bash
claude mcp add chromebridge -- "/path/to/ChromeBridge/.venv/bin/python" "/path/to/ChromeBridge/mcp_server.py"
```

</details>

<details>
<summary><b>Known issues and limitations, in detail</b></summary>

<br>

### Trusted input dies on pages where another extension injects an iframe

**Chrome policy, not a ChromeBridge bug.** Chrome applies its "may this
extension attach here" check across a tab's *entire frame tree*. If any frame
is a `chrome-extension://` URL belonging to a **different** extension,
`chrome.debugger.attach` is refused for the whole tab — with the message
*"Cannot access a chrome-extension:// URL of different extension"*, on a tab
whose own URL is plainly `https`.

Measured with Passbolt: it injects its iframe **when a login field is focused**.
So the first trusted click on a login page works, Chrome then detaches, and
every attach after that is refused. Password managers inject on exactly the
login pages where an agent most needs trusted input.

- **Not** recoverable by detaching, retrying, or opening a new tab on the same URL.
- Still works: `read_page`, `find`, `get_page_text`, `form_input`, `fill_form`,
  and ordinary untrusted clicks. Most sites need nothing more.
- The tool error names the offending extension; `debug_targets` prints Chrome's
  own target table.
- **Workaround:** turn the other extension off for that site while the agent works.

### A tab can lose trusted input permanently

After an input op whose effect navigates, a tab can stop delivering synthetic
input entirely: Chrome accepts the command and the page records no event.
**This is not ours** — Playwright's own mouse fails identically on the same tab,
and it survives detach-and-reattach, a forced focus-emulation re-apply, and a
mouse release.

The click path arms a capturing counter before dispatching and reads it after,
so it reports `*** NOT DELIVERED ***` and names the verified recovery (a new
tab) instead of reporting a click that never landed. A click that *navigates*
destroys the probe along with the document, and there it claims nothing.

### Printed coordinates drift while a page is still loading

On a page that has not settled, printed coordinates were measured **~110 px
stale**. Element references are safe — they are re-measured at click time. What
is not safe is a coordinate copied out of a listing, which will miss silently.
Every observation leads with a readiness banner when in-flight requests,
near-viewport unloaded images, `aria-busy` or a visible progressbar say the
page is still changing.

### An `<svg>` `<title>` names the control, but never appears in page *text*

`<button><svg><title>Delete item</title></svg></button>` and a bare wired
`<svg tabindex=0><title>Sort by date</title></svg>` both list with that name —
SVG2 makes a direct `<title>` child the element's accessible name.

What it is **not** in is `get_page_text`: an `<svg>` `<title>` is a tooltip and
an accessible name, not rendered text, so a page whose only mention of a word
is inside one will not match `search_page` either. Reach it through `read_page`
or `find`, which do see it.

### `find` is lexical, not semantic

Given a descriptor ("blue search box in the header") it puts the target in the
top 3 about 75% of the time. Given a *goal* ("book a mid-range hotel in Paris")
it scores exactly zero, because there is no lexical overlap between a goal and
the control that achieves it. Reading the `read_page` listing and choosing is
the model's job, not the scorer's. Its `under=` heading attribution is a
nearest-preceding-heading guess — a hint, never page structure.

### `listener_tag.js` is injected into every page, before any grant

The manifest registers it as a `document_start`, MAIN-world content script on
`<all_urls>`, and a manifest content script cannot be conditioned on a runtime
grant — that is the whole reason it can beat page scripts to
`addEventListener`.

What it does there is bounded: it wraps `EventTarget.addEventListener` to tag
elements that have click handlers (the one element class no DOM walk can see),
wraps `attachShadow` so closed roots stay reachable without a debugger, and
mirrors `console.*` into a capped 500-entry in-page ring buffer. **Nothing
leaves the page** — reading that buffer requires the `read_console_messages`
op, which *is* gated. If injecting at all is unacceptable to you, remove the
`content_scripts` block from `extension/manifest.json`; you lose handler-tagged
elements, closed shadow roots and console capture, and nothing else.

### A recorded flow is a test, and tests need a known starting state

- **A flow that creates something is not re-runnable in place.** It recorded
  "4 rows before, 5 after"; run it twice without resetting and the second run
  legitimately finds 6. `tools/run_flows.py --playground` resets first. The
  failure names the previous run among its causes rather than diagnosing it,
  because a changed dataset and a real regression look the same from inside.
- **An element's identity can be live data.** A nav tab whose accessible name
  is "Records 43" is named that because the count is inside it; add a record
  and it stops matching. The replay falls back to the link's `href`, reports
  the drift, and proposes a patch.
- **How long a step may take comes from the recording**, not from a constant:
  each step stores the settle time it actually needed. An app much slower on
  the day than when it was recorded can still time out.
- **Coordinate clicks are deliberately not recordable.** A point is not an
  element: there is nothing to describe and nothing to re-resolve.

### One Chrome, one bridge

The server binds the first free port in a 10-port span (8765-8774 by default)
and the extension sweeps the same span, so you never adjust the port by hand.
What that does **not** buy you is two agents on one browser: the sweep stops at
the first server that answers, so a second session gets a healthy server nobody
talks to and its tools report "Chrome extension is not connected". When the
first session exits, the extension re-sweeps and picks up the second.

If you move `BRIDGE_PORT`, move it in the side panel too — the span is defined
in `core/bridge/server.py`, `extension/background.js` and `extension/panel.js`,
and they are meant to agree.

### Smaller ones

- **The yellow "is debugging this browser" infobar** appears whenever
  `chrome.debugger` is attached — trusted clicks, `computer`, `javascript_tool`.
  The server detaches at shutdown. Chrome does not allow suppressing it.
- **Chrome's own surfaces can never be driven**: `chrome://`, other extensions'
  pages, `devtools://`, `view-source:`, `about:`. No grant unlocks them. A tab
  from `tabs_create_mcp` is `about:blank` until you navigate it.
- **Closed shadow roots are reached without a debugger**, because
  `listener_tag.js` wraps `attachShadow` at `document_start`. Open roots,
  same-origin iframes and cross-origin iframes all work too. Everyone else's
  answer to this is a CDP attach, which the first limitation above refuses on
  exactly the login pages that need it.
- **Console capture misses browser-generated messages.** CSP violations and
  network errors never route through `console.*`. Network failures do show in
  `read_network_requests`. Both buffers are best-effort and are lost when
  Chrome evicts the service worker.
- **`read_page` is viewport-scoped on purpose** for token discipline, with
  off-viewport counts naming the region and its reference, so the recovery is
  one small scoped read. A scoped read is *not* viewport-limited. `find`
  reaches the whole page, and its references auto-scroll when clicked.
- **A batch runs its steps in one round trip**, so observations chained after a
  click can read the page before a CSS transition finishes. The batch waits on
  *navigations* — Chrome announces those — but not on animations. Take the
  click as its own call.

</details>

<details>
<summary><b>Benchmarks and audits need a corpus that is not in the repo</b></summary>

<br>

Everything under `temp/` is **gitignored and roughly 1.2 GB**, so a fresh clone
can run the test suites but **cannot** run the measurement harnesses until it
rebuilds that data. Nothing is silently missing-and-fine: the harnesses simply
find no input.

| Harness | Needs | Rebuild with |
|---|---|---|
| `measure_retention.py`, `audit_thresholds.py` | `temp/frozen/` — 106 recorded HAR sites (~1.1 GB) | `python tools/freeze_corpus.py` (network, tens of minutes) |
| `bench_mind2web.py`, `bench_trajectory.py` | `temp/mind2web/` — held-out human-labelled targets (~110 MB) | `python tools/fetch_mind2web.py` |
| `test_gaps.py` | `temp/dom_audit/` | created for you by `tools/run_tests.py` |

The corpus *definition* is in git — the 106 URLs live in
`tools/capture_listings.py` as the single source of truth. Only the recordings
are missing. `--verify` replays each site twice and reports stability, because
18 of the 106 are genuinely non-deterministic and no exact-match invariant
should be asserted on them.

`tools/bench_turns/` holds the live head-to-head harness: the pre-registration,
the blind-written tasks, the referee's ground truth, every prompt, the
transcript scorer and the analysis. It is in the repo because six earlier
head-to-heads were run out of session scratchpads and are not reproducible —
the numbers survived, the means of re-deriving them did not.

</details>

<details>
<summary><b><code>legacy/</code> — what this was before</b></summary>

<br>

Before this was an MCP server it was a self-contained pydantic-ai agent loop
that needed your own OpenAI key. That code — the `run_extension.py` REPL, the
Playwright path, model profiles, recipes, vision — is preserved verbatim in
`legacy/` as a historical record.

**It does not import cleanly any more.** Its modules reference `core.*`
submodules that no longer exist in this repo, so `legacy/run_extension.py`
fails at import with a `ModuleNotFoundError`. It is reference material, not a
second entry point; the only entry point is `mcp_server.py`.

</details>

---

<div align="center">

**Apache-2.0** · [LICENSE](LICENSE)

</div>
