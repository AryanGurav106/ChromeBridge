# ChromeBridge

**Open-source Claude-in-Chrome.** A Chrome MV3 extension plus a local MCP stdio
server that let **Claude Code drive your real Chrome window** — your existing
logins, cookies and extensions — through trusted Chrome DevTools Protocol input.

- **Zero API keys.** Claude Code *is* the agent loop; every model call runs on
  your Claude subscription. This server holds no LLM key.
- **Your real browser.** Playwright/Puppeteer agents launch a fresh Chromium
  with no auth state. ChromeBridge attaches to the browser you already use, so
  it can act *as you* on apps you are already signed into.
- **Works on framework-heavy SPAs.** Radix, shadcn, HeadlessUI, MUI — full
  pointer-event sequences, auto-escalation to trusted input, atomic
  React-safe form fills. No site-specific code.
- **You grant access per site.** Nothing is read or clicked on an origin you
  have not allowed in the extension's side panel, and one click pauses
  everything.
- **A run can become a test.** `record_flow` turns what Claude just did into a
  replayable file that runs with **no model calls** — seconds instead of
  minutes — and it arrives with the assertions already in it, because the
  observations Claude made along the way *are* the postconditions.

```
┌──────────────┐  stdio MCP  ┌───────────────┐ ws://127.0.0.1:8765-74 ┌──────────────────┐
│  Claude Code │ ◄─────────► │ mcp_server.py │ ◄────────────────────► │ Chrome extension │ → your real tabs
└──────────────┘   JSON-RPC  └───────────────┘  token + protocol v1   └──────────────────┘
                                                                       per-origin gate ↑
```

## Status

Alpha, and honest about it:

- Developed on **Windows 11** and since driven end to end on **macOS**
  (Darwin 25.6, Python 3.12): a real Chrome, the unpacked extension, trusted
  clicks, and recorded flows replayed against eight public sites and a live
  staging app. CI runs the suites on Linux. **Linux has not driven a real
  Chrome**, so the setup section says so where it matters.
- One Chrome, one extension, one bridge. Multi-browser and multi-window
  orchestration are out of scope.
- Read [Known issues and limitations](#known-issues-and-limitations) before you
  conclude something is broken. Several of the sharp edges are Chrome policy,
  not bugs we can fix.

## Requirements

- Python **3.10+** (3.12 is what this is developed against)
- Google Chrome (or a Chromium with MV3 side panel support)
- Claude Code (the CLI)
- Node 22+ and Playwright — **only** to run the test suites, not to use it

## Setup

### 1. Install the Python side

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
```

macOS / Linux (macOS is exercised end to end; **Linux has not driven a real Chrome**):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Use the **editable** install (`-e`). A plain `pip install .` copies
`mcp_server.py` into `site-packages`, and the server resolves `.env`, the repo
`.venv` and everything else relative to its own file — so an installed copy
would look for your `.env` next to the installed module and never find it.

If you would rather not install the project at all, the dependencies alone are
enough:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt   # Windows
.venv/bin/python -m pip install -r requirements.txt           # POSIX
```

### 2. Load the extension

1. Open `chrome://extensions`.
2. Turn on **Developer mode** (top right).
3. **Load unpacked** → select the `extension/` folder in this repo.
4. Pin **ChromeBridge** to the toolbar; clicking its icon opens the side panel.

### 3. Register the MCP server with Claude Code

The repo ships a project-scope `.mcp.json`, so **opening Claude Code in this
folder is enough**. Its server entry is deliberately portable — no machine's
absolute venv path is baked in:

```json
"chromebridge": {
  "command": "${CHROMEBRIDGE_PYTHON:-python}",
  "args": ["${CHROMEBRIDGE_ROOT:-.}/mcp_server.py"]
}
```

Facts that were measured about that file, because each one is a way to lose an
afternoon:

- `${VAR:-default}` **does** expand.
- A bare `${VAR}` that is unset does **not** — the server simply fails to start.
- `${CLAUDE_PROJECT_DIR}` does **not** expand in `.mcp.json`.
- The default `.` resolves against **the directory Claude Code was launched
  from**, not the directory `.mcp.json` lives in.

So the defaults work when you launch Claude Code from the repo root with a
`python` on PATH. If either is untrue for you, set the escape hatches:

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
with no `mcp` installed hands over to `.venv/bin/python` and serves all 31
tools.

To register it globally instead of per-project:

```powershell
claude mcp add chromebridge -- "C:\path\to\ChromeBridge\.venv\Scripts\python.exe" "C:\path\to\ChromeBridge\mcp_server.py"
```

```bash
claude mcp add chromebridge -- "/path/to/ChromeBridge/.venv/bin/python" "/path/to/ChromeBridge/mcp_server.py"
```

### 4. Pair the extension with the server (once)

`BRIDGE_TOKEN` is a shared secret that gates the local WebSocket so no other
process on your machine can drive your browser through it.

1. Copy `.env.example` to `.env`. Leave `BRIDGE_TOKEN` empty.
2. Start Claude Code in this folder. On first run the server **generates a
   token and writes it into your `.env`**, and prints it to stderr.
3. Open `.env`, copy the `BRIDGE_TOKEN` value.
4. Open the ChromeBridge side panel → paste it into **Token** → **Save &
   Connect**. The status pill turns green.

Both sides remember it; you do this once. (You can also put your own random
string in `.env` before the first start.)

### 5. Allow the first site

Connected is not the same as allowed. **ChromeBridge refuses every op on an
origin you have not granted**, so the first-run sequence is:

1. Ask Claude to do something: *"open example.com and tell me what's on it"*.
2. Claude can create a tab and list your tab group (those need no grant), then
   the `navigate` is **refused** and the refusal names the origin.
3. The side panel shows **Permission requested — Allow this site**. Click it.
4. Tell Claude to retry.

Grants are per-origin (`https://example.com`), listed in the panel with a
**Revoke** button, and only ever written by that panel — the service worker
cannot grant itself a site. The panel's **Pause** switch freezes everything
immediately; only status-reporting ops keep answering while paused.

## What Claude gets

31 MCP tools. The names and schemas mirror Claude-in-Chrome so a model that
knows one knows the other:

| | |
|---|---|
| **Tabs** | `tabs_context_mcp`, `tabs_create_mcp`, `tabs_close_mcp`, `get_url` |
| **Observe** | `read_page` (`filter`, `ref_id` subtree scoping, `detail="full"` for `href`/`src`/media, `max_chars`), `get_page_text`, `find`, `read_interactive_elements` |
| **Act** | `navigate` (incl. `back`/`forward`), `computer` (trusted click/drag/scroll/hover/key/type, screenshot, zoom), `form_input`, `fill_form`, `file_upload`, `upload_image`, `resize_window` |
| **Inspect** | `javascript_tool` (CSP-proof REPL eval), `read_console_messages`, `read_network_requests`, `debug_targets`, `sw_info` |
| **Ask exactly** | `query_elements` (CSS query + counting; the total is never capped), `search_page` (grep over rendered text), `accessible_names` |
| **Record** | `record_flow` (start / stop / **patch**), `run_flow` |
| **Page-declared** | `page_tools`, `call_page_tool` (WebMCP), `save_as_pdf`, `dismiss_dialog` |
| **Compose** | `browser_batch`, `gif_creator` |

Three of those are ChromeBridge power-tools that Claude-in-Chrome does not have:

- **`record_flow` / `run_flow`** — turn a run into a replayable test. Drive the
  browser normally, say stop, and you get a file that replays with **no model
  calls**: a five-step flow takes about a second where recording it took an
  agent minutes. Every element reference is rewritten into a description built
  from what the page DECLARES (a raw ref is per-document and means nothing on
  the next run), and the checks Claude made along the way become the
  assertions — which is why the test arrives with them already in it rather
  than asking you to write them. When the page moves, a replay resolves what it
  can, reports what changed, and **proposes** a patch; `record_flow("patch")`
  applies it only because you asked. A replay never writes to your test.

- **`fill_form`** — fill an entire multi-field form (text + comboboxes +
  checkboxes) and optionally submit, in **one** call. It batches every text
  write into a single page-context script, which is what keeps element refs
  valid across a React controlled-input re-render, and it reports validation
  errors and unfilled required fields back to the model.
- **`read_interactive_elements`** — the raw deterministic listing, with
  `name=` / `value=` / `placeholder=` kept as three separate signals plus
  modal, fold, occlusion and readiness flags.

Deliberately not implemented (claude.ai-cloud features with no local analog):
`shortcuts_list` / `shortcuts_execute`, `list_connected_browsers`,
`select_browser`, `switch_browser`.

## Known issues and limitations

### Trusted input dies on pages where another extension injects an iframe

This is the one most likely to look like a broken product. **It is a Chrome
policy, not a ChromeBridge bug.**

Chrome applies its "may this extension attach here" check across a tab's
*entire frame tree*. If any frame in the tab is a `chrome-extension://` URL
belonging to a **different** extension, `chrome.debugger.attach` is refused for
the whole tab — with the message *"Cannot access a chrome-extension:// URL of
different extension"*, on a tab whose own URL is plainly `https`.

Measured with Passbolt: it injects its iframe **when a login field is focused**.
So the first trusted click on a login page works, Chrome then detaches, and
every attach after that is refused. Password managers inject on exactly the
login pages where an agent most needs trusted input.

- **Not** recoverable by detaching, retrying, or opening a new tab on the
  same URL.
- Still works: `read_page`, `find`, `get_page_text`, `form_input`, `fill_form`,
  and ordinary untrusted clicks. Most sites need nothing more.
- The tool error names the offending extension; the side panel shows a notice
  saying which one; `debug_targets` prints Chrome's own target table.
- **Workaround:** turn the other extension off for that site (or entirely)
  while the agent works there.

### Printed coordinates drift while a page is still loading

`read_page` prints a `box()` for each element. On a page that has not settled,
those numbers were measured **~110px stale** (an unloaded hero image was about
to reflow the layout).

Element **refs are safe** — they are re-measured at click time. What is not
safe is `computer(coordinate=[x, y])` copied out of a listing, which will miss
silently. Every observation now leads with a readiness banner when in-flight
requests, near-viewport unloaded images, `aria-busy`, a visible progressbar or
`document.readyState` say the page is still changing; wait for it to clear
before trusting printed coordinates.

### An `<svg>` `<title>` names the control, but never appears in page *text*

`<button><svg><title>Delete item</title></svg></button>` and a bare wired
`<svg tabindex=0><title>Sort by date</title></svg>` both list with that name —
SVG2 makes a direct `<title>` child the element's accessible name, and the
collector reads it as a declaration like any other.

What it is **not** in is `get_page_text`: an `<svg>` `<title>` is a tooltip and
an accessible name, not rendered text, so a page whose only mention of a word
is inside one will not match `search_page` either. Reach it through `read_page`
or `find`, which do see it.

### `find`'s `under=` can name the wrong heading

`find` annotates results with the section they appear under. That attribution
is a nearest-preceding-heading guess and can name the heading *before* the
element's real section. Treat it as a hint, never as page structure.

Related, and by design: **`find` is a lexical matcher, not a semantic one.**
Given a descriptor ("blue search box in the header") it puts the target in the
top 3 about 75% of the time; given a *goal* ("book a mid-range hotel in
Paris") it scores exactly zero, because there is no lexical overlap between a
goal and the control that achieves it. Reading the `read_page` listing and
choosing is the model's job, not the scorer's.

### `listener_tag.js` is injected into every page, before any grant

The manifest registers `extension/listener_tag.js` as a `document_start`,
MAIN-world content script on `<all_urls>`, and a manifest content script cannot
be conditioned on a runtime permission grant. So it runs on pages you have
never allowed.

What it does there is bounded: it wraps `EventTarget.addEventListener` to tag
elements that have click handlers (the one element class no DOM walk can see),
and mirrors `console.*` into a capped 500-entry in-page ring buffer. **Nothing
leaves the page.** Reading that buffer requires the `read_console_messages` op,
which *is* gated on a per-origin grant like everything else. If injecting at
all is not acceptable to you, remove the `content_scripts` block from
`extension/manifest.json`; you lose handler-tagged elements and console
capture, and nothing else.

### A recorded flow is a test, and tests need a known starting state

`run_flow` replays with no model calls, which is the point and also the
constraint: it does exactly what was recorded.

- **A flow that creates something is not re-runnable in place.** It recorded
  "4 rows before, 5 after"; run it twice without resetting the app and the
  second run legitimately finds 6. That is what any create-a-record test needs a
  fixture reset for — `tools/run_flows.py --playground` does one. The failure
  names the previous run among its causes rather than diagnosing it, because a
  changed dataset and a real regression look the same from inside.
- **An element's identity can be live data.** A nav tab whose accessible name
  is "Investors 43" is named that because the count is inside it; add a record
  and the descriptor stops matching. The replay falls back to the link's `href`,
  reports the drift and **proposes** a patch — `record_flow(action="patch")`
  applies it. A replay never edits your flow file on its own.
- **How long a step may take is taken from the recording**, not chosen: each
  step stores the settle time it actually needed. An app that is much slower on
  the day than it was when recorded can still time out and report FAILED for an
  action that worked.
- **Coordinate clicks are deliberately not recordable.** A point is not an
  element: there is nothing to describe and nothing to re-resolve.

### One Chrome, one bridge

The server binds the first free port in a 10-port span (`BRIDGE_PORT`
..`BRIDGE_PORT+9`, default 8765-8774), so a second Claude Code session no longer
dies with "address already in use", and the extension sweeps the same span so it
finds the bridge wherever it landed. You do not have to adjust the port by hand.

What that does **not** buy you is two agents driving one browser. There is one
Chrome with one extension holding one socket: the sweep stops at the first
server that answers, so a second session gets a healthy server nobody talks to
and its tools report "Chrome extension is not connected". When the first session
exits, the extension re-sweeps and picks up the second. Run one at a time.

If you move `BRIDGE_PORT`, move it in the side panel too — the span is defined
in three places (`core/bridge/server.py`, `extension/background.js`,
`extension/panel.js`) and they are meant to agree.

### Smaller ones

- **The yellow "is debugging this browser" infobar** appears whenever
  `chrome.debugger` is attached — trusted clicks, `computer`, `javascript_tool`.
  The server detaches at shutdown. Chrome does not allow suppressing it.
- **Chrome's own surfaces can never be driven**: `chrome://`, other extensions'
  pages, `devtools://`, `view-source:`, `about:`. No grant unlocks them. A tab
  from `tabs_create_mcp` is `about:blank` until you navigate it.
- **Closed shadow roots are reached without a debugger.** `listener_tag.js`
  wraps `attachShadow` at `document_start`, so nothing can create a closed root
  without handing the extension a reference to it. Open roots, same-origin
  iframes and cross-origin iframes all work too. Everyone else's answer to this
  is a CDP attach, which the limitation above refuses on exactly the login pages
  that need it.
- **Console capture misses browser-generated messages.** CSP violations and
  network errors never route through `console.*`. Network failures do show up
  in `read_network_requests`. Both buffers are best-effort and are lost when
  Chrome evicts the service worker (console also on page reload).
- **`read_page` is viewport-scoped on purpose** for token discipline, with
  below-fold counts telling the model where to scroll. `find` is not — it
  reaches the whole page, and its refs auto-scroll when clicked.

## Running the tests

```powershell
.venv\Scripts\python.exe tools\run_tests.py            # Windows
```

```bash
.venv/bin/python tools/run_tests.py                    # POSIX (run on macOS; CI runs it on Linux)
```

19 suites, 1,039 checks, about 90 seconds. Nine are browser-free; the other ten
drive headless Chromium and need two extra packages that are deliberately not
runtime dependencies:

```powershell
.venv\Scripts\python.exe -m pip install playwright
.venv\Scripts\python.exe -m playwright install chromium
```

Without them the browser group is **skipped with a reason** rather than failed.
`--list` prints the real inventory, `--group unit` runs only the browser-free
suites, and `--strict` turns a skip into a failure (CI uses it).
`tools/README.md` documents each suite; `.github/workflows/ci.yml` runs all of
them plus `node --check` on the extension scripts.

One more suite is worth running by hand, because it is the only one that
crosses every boundary at once — a real Chrome, the real unpacked extension,
the real WebSocket bridge, the real op router and the real MCP tool functions:

```bash
.venv/bin/python tools/run_flows.py --playground --local-only
.venv/bin/python tools/run_flows.py --check-only     # no browser; validates every flow file
```

It starts its own fixture app, grants the origin inside a **throwaway Chrome
profile it creates and destroys** (the gate is satisfied, never bypassed), and
replays the recorded flows in `flows/`. Every other suite injects page
functions directly, which is exactly why three features in this project's
history shipped broken behind green fixtures. CI runs both, plus a third pass
with a nav label deliberately rewritten, which is what proves the href fallback
carries a flow whose target was renamed.

## Benchmarks and audits need a corpus that is not in the repo

Everything under `temp/` is **gitignored and roughly 1.2 GB**, so a fresh clone
can run the test suites but **cannot** run the measurement harnesses until it
rebuilds that data. Nothing is silently missing-and-fine here: the harnesses
will simply find no input.

| Harness | Needs | Rebuild with |
|---|---|---|
| `tools/measure_retention.py`, `tools/audit_thresholds.py` | `temp/frozen/` — 106 recorded HAR sites (~1.1 GB) | `python tools/freeze_corpus.py` (network, tens of minutes) |
| `tools/bench_mind2web.py` | `temp/mind2web/` — held-out human-labelled targets (~110 MB) | `python tools/fetch_mind2web.py` |
| `tools/test_gaps.py` | `temp/dom_audit/` | created for you by `tools/run_tests.py` |

The corpus *definition* is in git — the 106 URLs live in `tools/capture_listings.py`
as the single source of truth, and `freeze_corpus.py` reads them from there. Only
the recordings are missing. `--verify` replays each site twice and reports
stability, because 18 of the 106 are genuinely non-deterministic and no
exact-match invariant should be asserted on them.

`BENCHMARK.md`, `AUDIT_DOM_GENERALITY.md` and `AUDIT_GENERALITY.md` hold the
numbers these produced.

`tools/bench_turns/` is the LIVE head-to-head harness — the pre-registration,
the blind-written tasks, the referee's ground truth, every prompt, the transcript
scorer and the analysis, for the comparison `BENCHMARK.md` now leads with. It is
in the repo because six earlier head-to-heads were run out of session scratchpads
and are not reproducible: the numbers survived, the means of re-deriving them did
not.

## `legacy/`

Before this was an MCP server it was a self-contained pydantic-ai agent loop
that needed your own OpenAI key. That code — the `run_extension.py` REPL, the
Playwright path, model profiles, recipes, vision — is preserved verbatim in
`legacy/` as a historical record.

**It does not import cleanly any more.** Its modules reference `core.*`
submodules (`core.utils.model_profiles` and friends) that no longer exist in
this repo, so `legacy/run_extension.py` fails at import with a
`ModuleNotFoundError`. It is reference material, not a second entry point; the
only entry point is `mcp_server.py`.

## Security model, briefly

- The bridge binds **127.0.0.1 only** and speaks to at most one client.
- A shared `BRIDGE_TOKEN` gates the handshake; a mismatch is closed with code
  1008. A protocol-version mismatch is closed with 4001, which is what a stale
  hand-loaded extension looks like.
- Ops are **default-deny per origin**. An op that is not on the small ungated
  list (ping, diagnostics, tab create/close/list, url, window resize, debugger
  detach) needs a grant for that exact origin. New ops are gated by omission.
  The permission table is read from storage on **every** op, so a revoke or a
  pause takes effect on the very next one, and a table that cannot be read at
  all denies.
- `navigate` is gated on its **destination**, not on where the tab currently
  is — otherwise any granted site would be a doorway to every ungranted one.
- Grants are written **only** by the side panel.
- The server holds no LLM key and makes no network calls of its own.

## More reading

- `CLAUDE.md` — architecture, the op inventory, the numbered list of fixes that
  make this work on real apps, and debugging starting points. Read this first
  if you are changing the code.
- `EXTENSION_SETUP.md` — extension install and troubleshooting in detail.
- `CHROME_ATTACH_PLAN.md` — why an extension, and not `--remote-debugging-port`.
- `tools/README.md` — the test suites and measurement probes.
- `FLOW_RECORDER_PLAN.md` — the design behind `record_flow`/`run_flow`: the
  descriptor ladder, what was measured before it shipped, and the alternatives
  that were rejected with numbers.
- `flows/` — the recorded flows themselves. They are small JSON files meant to
  be read and reviewed in a diff.

## License

Apache-2.0. See `LICENSE`.
