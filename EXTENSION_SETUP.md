# Drive your real Chrome — extension mode

This lets ChromeBridge act inside your **already-open Chrome window**, on
your **active tab**, with your real cookies/sessions — no relaunch, no profile
copy. The Python agent stays exactly the same; it just sends actions through a
tiny local-only WebSocket bridge to a Chrome extension that does the actual DOM
work.

> Local-only and gated: the bridge binds `127.0.0.1` and requires a per-session
> token (printed at startup) for the extension's handshake. Nothing reaches the
> internet from the extension itself.

## One-time install (≈ 1 minute)

1. In Chrome, open `chrome://extensions`. Toggle **Developer mode** (top-right).
2. Click **Load unpacked** and pick the `extension/` folder inside this repo.
3. The extension appears as **ChromeBridge**. Pin it (puzzle icon →
   pin) so its side panel is one click away.

> Note: the "Each run" section below predates the MCP server and still describes
> the retired `run_extension.py` loop (now in `legacy/`). The current entry point
> is `mcp_server.py`, driven by Claude Code — see `CLAUDE.md`. The install step
> above and the troubleshooting section are still accurate.

## Each run

1. Start the bridge + agent (this is the new entry point):
   ```powershell
   python run_extension.py "Open my GitHub notifications and tell me how many are unread"
   ```
   You'll see something like:
   ```
   ============================================================
    ChromeBridge — waiting for Chrome extension
   ============================================================
     ws://127.0.0.1:8765
     token: rL2Pq9Y1m...   <- copy this
   ```
2. Open the **ChromeBridge** side panel in Chrome (click the
   extension icon). Paste the **token**, hit **Save & Connect**. The pill
   should turn green ("connected").
3. The task starts running on **whichever tab you're currently focused on**.
   The agent's tools (read DOM, click, type, navigate, screenshot, Set-of-Mark)
   all execute inside that tab.

For interactive use, run with no arguments and type tasks one per line:
```powershell
python run_extension.py
```

## What the extension does (and doesn't)

**Does**
- Read the page's DOM, build a list of visible interactive elements with
  on-screen positions and a true clickability check (`mmid` ids, same scheme as
  the Playwright mode).
- Click and type (untrusted-event path; works for the vast majority of
  controls — links, buttons, normal inputs, textareas).
- Capture viewport screenshots (used by Set-of-Mark visual grounding).
- Navigate, press key combinations, return URL/title.

**Does (Phase E2 just landed)**
- **Trusted input** via `chrome.debugger`: when the agent passes `trusted=True`
  to a click or type (it does so for logins/payments/OAuth/file-pickers, or
  after a normal click had no effect), the extension lazy-attaches the debugger
  to that tab and dispatches **real** `Input.dispatchMouseEvent` /
  `Input.insertText` events. Chrome shows a yellow "ChromeBridge
  started debugging this browser" infobar on those tabs while it's attached —
  that's expected. The harness detaches on shutdown so the bar disappears.

**Still on the list**
- Full-page screenshots (`Page.captureScreenshot` with `captureBeyondViewport`).
- Cross-origin iframe access (needs host permissions per origin).

## What stays the same

- Your **Playwright** path is untouched. `python run.py "..."` still works the
  way it did and launches a fresh Chromium.
- Same `mmid` model, same `analyze_screen`, same `get_interactive_elements`,
  same agent system prompt, same action verification + memory.
- Same `.env`, same model selection (OpenAI / Anthropic).

## Troubleshooting

- **Pill stays red after Save & Connect**: token mismatch or wrong port. Re-copy
  the token from the terminal; check the host/port in the panel; click
  **Reconnect**.
- **"no active tab" error**: switch to a real web tab (the extension's own
  side-panel page or `chrome://...` URLs aren't drivable).
- **A click "succeeded" but nothing happened** on a login button: that page
  requires trusted input. The agent can retry with `trusted=True` (it should do
  this automatically when a click had no detectable effect); that lazy-attaches
  `chrome.debugger` to the tab — Chrome will show its yellow "X is debugging
  this browser" infobar while the debugger is attached, and detach when the
  harness exits.
- **Extension page errors / odd state**: `chrome://extensions` → the extension →
  **service worker → inspect** to see logs. Click **Reload** on the extension
  card to restart it cleanly.

## Why this exists (the short version)

A normally-started Chrome on Windows in 2025-2026 cannot be driven externally
without an extension: (1) it doesn't open a CDP listener; (2) Chrome 136+
silently strips `--remote-debugging-port` when paired with the default
`User Data` dir; (3) the singleton lock prevents launching a second debug-mode
Chrome on the same profile while the first is running. An extension runs
**inside** the real Chrome, so it sidesteps all three. See `CHROME_ATTACH_PLAN.md`
for the full research write-up.
