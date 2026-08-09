# ChromeBridge

**Open-source Claude-in-Chrome.** A Chrome MV3 extension + a local MCP server that
let **Claude Code drive your real Chrome window** — with your existing logins,
cookies and extensions — through trusted Chrome DevTools Protocol input.

- **Zero API keys.** Claude Code is the agent; every model call runs on your
  Claude subscription. The server holds no LLM key at all.
- **Your real browser.** Unlike Playwright/Puppeteer agents that launch a fresh
  Chromium with no auth state, ChromeBridge attaches to your everyday Chrome and
  acts *as you* on apps you're already logged into.
- **Works on framework-heavy SPAs.** Radix, shadcn, HeadlessUI, MUI — full
  pointer-event sequences, trusted-input auto-escalation, atomic React-safe
  form fills. No site-specific code.

```
┌──────────────┐  stdio MCP  ┌───────────────┐  ws://127.0.0.1:8765  ┌──────────────────┐
│  Claude Code │ ◄─────────► │ mcp_server.py │ ◄───────────────────► │ Chrome extension │ → your real tabs
└──────────────┘             └───────────────┘                       └──────────────────┘
```

## Setup (5 minutes)

1. **Install deps** (Python 3.10+):
   ```powershell
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
2. **Load the extension**: `chrome://extensions` → enable *Developer mode* →
   *Load unpacked* → select the `extension/` folder.
3. **Set the token**: copy `.env.example` to `.env`, put any random string as
   `BRIDGE_TOKEN`. Open the extension's side panel in Chrome, paste the same
   token, *Save & Connect*. (One time — both sides remember it.)
4. **Register the MCP server** with Claude Code — the included `.mcp.json` does
   this automatically for sessions opened in this folder, or register globally:
   ```powershell
   claude mcp add chromebridge -- "<repo>\.venv\Scripts\python.exe" "<repo>\mcp_server.py"
   ```
5. Open Claude Code and ask it to browse:
   > open my dashboard, add an investor called carrot bunny and submit the form

## Tools exposed to Claude

Same surface as Claude-in-Chrome: `tabs_context_mcp`, `tabs_create_mcp`,
`tabs_close_mcp`, `navigate` (incl. back/forward), `read_page`, `find`,
`form_input`, `computer` (trusted clicks/drag/scroll/keys/screenshots/zoom),
`get_page_text`, `javascript_tool` (DevTools-grade REPL eval, CSP-proof),
`read_console_messages`, `read_network_requests`, `resize_window`,
`file_upload`, `upload_image`, `gif_creator`, `browser_batch` —
**plus** two ChromeBridge power-tools Claude-in-Chrome doesn't have:

- `fill_form` — atomically fill an entire multi-field form (text + dropdowns +
  checkboxes) in one call, React-re-render-safe, with validation-error capture.
- `read_interactive_elements` — the raw deterministic element listing with
  `name=` / `value=` / `placeholder=` separation and modal/fold/occlusion flags.

## Notes

- The yellow *"is debugging this browser"* infobar appears whenever trusted
  input is in use; it detaches when the server shuts down. Chrome doesn't allow
  suppressing it.
- Agent tabs are kept in a dedicated **"Claude" tab group** so you always see
  what the agent owns.
- Exported GIFs land in `temp/`.
- The pre-MCP standalone agent (pydantic-ai + your own OpenAI/Anthropic key)
  is preserved in `legacy/`.

See `CLAUDE.md` for architecture details, the op inventory, critical fixes
(#1–#10) and debugging starting points.
