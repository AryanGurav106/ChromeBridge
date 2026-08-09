# Driving the user's real Chrome — research findings & plan

Goal: run the ChromeBridge agent against the user's **already-open
Chrome window** (with their existing tabs, logins, cookies, extensions) — the
Claude-in-Chrome experience but driven from local Python.

Two parallel research streams (CDP attach mechanics + Chrome extension
architectures) converged on the same answer. The short version is uncomfortable,
so it deserves a clear write-up.

---

## The headline finding

> **You cannot drive a normally-started Chrome externally on Windows in 2025-2026
> without an extension AND without relaunching it.**

Three specific facts, each independently fatal to "just attach":

1. **A vanilla `chrome.exe` started by double-click does not listen on CDP.** The
   `--remote-debugging-port` flag must be on the launching command line. There is
   no runtime toggle, no in-page JS, no `chrome://` URL that flips it on. By
   design — CDP gives full cookie/password/session access, so Google refuses a
   runtime switch. (Chrome 146 ships an experimental "Allow remote debugging"
   toggle behind DevTools → Settings → Experiments → "MCP", but it's rolling out
   gradually 2025–2026 and asks the user to approve each connection.)
   Source: [Chrome dev blog, March 2025](https://developer.chrome.com/blog/remote-debugging-port).

2. **Chrome 136 (May 2025) actively blocks `--remote-debugging-port` against the
   default user-data-dir.** The flag is silently ignored if `--user-data-dir`
   points at `%LOCALAPPDATA%\Google\Chrome\User Data`. You **must** use a
   non-default directory. This was Google's response to infostealers abusing
   CDP-on-real-profile.
   Sources: [Chrome blog](https://developer.chrome.com/blog/remote-debugging-port),
   [browser-use#1520](https://github.com/browser-use/browser-use/issues/1520),
   [chrome-devtools-mcp#1830](https://github.com/ChromeDevTools/chrome-devtools-mcp/issues/1830).

3. **Windows Chrome singleton enforcement.** If the user's normal Chrome is
   running, a second `chrome.exe --user-data-dir="<same dir>"` finds the existing
   process via `FindWindowEx`, forwards its command line to it via `WM_COPYDATA`,
   and **exits**. The first (debug-less) Chrome stays running; the second never
   starts. No 9222 port appears.
   Source: [Chromium `process_singleton_win.cc`](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/browser/process_singleton_win.cc).

Net effect on the "attach to my real Chrome with my real cookies, no relaunch"
dream: **doesn't work** without either an extension or accepting real friction.

---

## Why even Claude-in-Chrome is an extension

Anthropic's own Claude-in-Chrome bundles **15 permissions** including
`debugger`, `scripting`, `tabs`, `tabGroups`, `sidePanel`. From their own
docs: *"debugger — this is what allows Claude to actually control your browser
– clicking buttons, typing text, and taking screenshots; scripting — allows
reading webpage text."* Same architecture across the field:

- **Claude in Chrome** — extension, side panel UI, uses `chrome.debugger` for
  trusted input + `chrome.scripting` for DOM reads. Accepts the yellow "X is
  debugging this browser" infobar.
- **Browser-Use (Chrome Web Store extension)** — extension acts as a local bridge
  to `ws://127.0.0.1:37777` so multiple agents can share one Chrome.
- **OpenAI Atlas** — *not* an extension; it's a **forked Chromium** in a SwiftUI
  shell. OpenAI rejected the extension route entirely.
- **Sider/Monica/MaxAI** — extensions, but `chrome.scripting`-only. They read &
  summarize; they don't synthesize trusted input.

The reason these are extensions is the only one that matters here: an extension
runs **inside** the user's already-open Chrome, with the real profile and the
real cookies. No relaunch, no profile copy. That's the entire value prop.

Sources:
[Claude for Chrome announcement](https://www.anthropic.com/news/claude-for-chrome) ·
[Permissions help center](https://support.claude.com/en/articles/12012173-getting-started-with-claude-for-chrome) ·
[Browser-Use extension](https://chromewebstore.google.com/detail/browser-use-for-ai-agents/jhlkcgimglagkgfknhbdkenkmpanalji) ·
[Atlas/OWL architecture](https://openai.com/index/building-chatgpt-atlas/).

---

## The four options, scored

| | A. Relaunch real Chrome with `--remote-debugging-port` | B. Separate Chrome on a copy of the profile | C. Build a minimal extension + local Python WebSocket | D. Hybrid: extension default, CDP fallback |
|---|---|---|---|---|
| **Works on Chrome 136+ default profile** | **No** — flag silently ignored | Yes (non-default dir) | Yes | Yes |
| **No relaunch / closes existing Chrome** | No — must kill user's Chrome first | Partially — runs separate Chrome alongside | **Yes** | Yes (extension path) |
| **Uses real cookies / SSO / extensions** | Yes if user lets us replace their session | No — copy diverges; passwords break (DPAPI app-bound encryption) | **Yes** | Yes (extension path) |
| **Side-panel chat UI inside Chrome** | No | No | **Yes** (`chrome.sidePanel`) | Yes |
| **Trusted input (real `isTrusted` events)** | Yes (free with CDP) | Yes | Yes only via `chrome.debugger` → yellow bar | Yes |
| **Implementation effort** | ~50 LOC (already mostly there) | ~150 LOC (profile-copy + singleton handling) | ~300 LOC extension + ~150 LOC Python WS layer | A + C |
| **User install friction** | Must close all Chrome windows on every run | One-time profile copy, then a separate Chrome window | One-time sideload (`chrome://extensions` → Developer mode → Load unpacked) | Same as C when present |
| **Longevity** | Brittle — Google keeps tightening | Stable but increasingly divergent | Stable (MV3 is steady state) | Stable |

**Option A**'s big problem is now (3) above plus the user-experience cost of
killing their Chrome. **Option B** loses saved passwords (Chrome 127+ app-bound
encryption is keyed to the original `User Data` path under DPAPI) and the
"agent profile" silently drifts from the user's real one. Neither is what you
described you want.

---

## Recommendation: **Option D (hybrid)** with the extension as the primary path

Concretely:

### Primary (default): a minimal Chrome extension + local WebSocket bridge

```
extension/
  manifest.json          (~40 lines)
  background.js          (service worker, ~150 lines)
  content_inject.js      (~80 lines)
  panel.html / panel.js  (~50 lines, side-panel UI)
```

- **`chrome.scripting`** does 90% of actions — DOM walk, `mmid` injection
  (identical algorithm to our current JS), `getBoundingClientRect`, `element.click()`,
  set `.value` + dispatch input/change events, `getInteractiveElements`, page-text
  extraction. **No yellow bar.**
- **`chrome.debugger` is attached lazily and per-tab** only when an action needs
  trusted input (file picker, OAuth popup, payment, login flows that reject
  untrusted clicks). The yellow bar appears only for those flows — which is
  actually a *good* UX signal ("the agent is about to log in for you").
- **`chrome.sidePanel`** gives a persistent chat surface inside Chrome.
- **`chrome.tabs.captureVisibleTab`** for viewport screenshots (no debugger
  needed). Full-page screenshots upgrade to `Page.captureScreenshot` via
  `chrome.debugger` when needed.
- **Bridge**: `ws://127.0.0.1:<port>` between the extension's service worker and
  a tiny `websockets` server in the Python agent. Per-session token from
  `chrome.storage.local` for auth. (We can upgrade to `chrome.runtime.connectNative`
  later for production distribution — no exposed TCP port, registry-installed
  host. Native messaging is the modern "local desktop AI" standard, but WS is
  fine for dev / single-user.)

**Protocol** (JSON over WS, request/response with `id`):

```
{ id, op: "get_dom_text" | "get_interactive_elements" | "get_dom_fields" }
{ id, op: "click",      params: { mmid } }
{ id, op: "type",       params: { mmid, text } }
{ id, op: "screenshot", params: { fullPage? } }
{ id, op: "navigate",   params: { url } }
{ id, op: "tabs.list" | "tabs.activate" | "tabs.new" }
```

Python side: a `websockets` server in the harness, with each `op` mapped to the
same logical operations our current Playwright skills implement. The Python
"brain" stays intact; the extension is purely the "hands" — what changes is
*who actually touches the page*.

### Fallback (CLI / power users / CI): keep the current Playwright path

The existing `BROWSER_STORAGE_DIR` / `--profile` flag stays. Users who want the
no-extension path can do the Chrome-for-Testing recipe (separate browser binary,
non-default `--user-data-dir`, debugging port) — that's Google's blessed
automation route.

### Why not just Option A
Because (a) Chrome 136+ kills it on the default profile, (b) it requires closing
the user's existing Chrome on every run, and (c) it gives nothing the hybrid
doesn't.

### Why not just Option B
Because the agent ends up driving a *separate* Chrome with stale cookies and
without the user's saved passwords. That's not "drive my open Chrome."

---

## What the extension does *not* solve

- **`chrome.debugger`'s yellow infobar.** When we use it for trusted input,
  Chrome shows "Browser Agent started debugging this browser" with a Cancel
  button that, if clicked, detaches the debugger immediately. The bar reappears
  per attached tab. Workarounds: launch Chrome with `--silent-debugger-extension-api`
  (requires relaunch, which defeats the purpose) or enterprise policy. We have
  to accept the bar for trusted-input flows. Claude-in-Chrome accepts it too.
- **Cross-origin iframes** still require host permissions per origin.
- **A small-but-real attack surface**: a local WebSocket port is reachable by
  any local process. Mitigated by a per-session token + binding 127.0.0.1, but
  native messaging is strictly better and we should move to it before any
  distribution beyond ourselves.

---

## Concrete plan if greenlit

**Phase E1 — Extension scaffolding & WS bridge (1–2 days)**
- `extension/` directory with `manifest.json`, background SW, side-panel HTML,
  content-script injector (port of our existing `mmid` + geometry pass).
- Python `extension_bridge.py`: `websockets` server, request-id mux, surfaces
  the same operations as our skills.
- A new harness mode `--via-extension` (or auto-detect): when set, the agent's
  tools call the bridge instead of Playwright. Tools' input/output stays
  identical so the agent code doesn't change.

**Phase E2 — Trusted-input upgrade path (~1 day)**
- Lazy `chrome.debugger.attach(tab)` on demand for clicks/types that need
  `isTrusted`. Detach on `chrome.debugger.onDetach`. Listen for the user
  hitting Cancel and surface a "reconnect" CTA in the side panel.

**Phase E3 — Side-panel chat UI (~1 day)**
- Minimal side panel that shows current step, last action, a Pause/Resume,
  and a "Stop debugger" toggle. Optional — power users may not want it.

**Phase E4 — Hardening for distribution (later, only if shipping)**
- Migrate WS → `chrome.runtime.connectNative` with a Windows registry-installed
  native-messaging host. Adds an installer step but removes the TCP port.
- Web Store packaging if/when we want to distribute publicly.

**Open questions for you before I start:**
1. **Yellow-bar tolerance.** Are we OK accepting Chrome's yellow "debugging this
   browser" infobar during login/payment-like flows? (Yes from me — Claude
   accepts it; the alternative is worse.)
2. **Distribution.** For your own use only, or do you want it Web-Store-shippable
   at some point? Decides whether to invest in native messaging early.
3. **CDP-fallback retention.** Keep the current Playwright-launched mode as a
   `--cdp` CLI option, or drop it once the extension works? (I recommend keep
   it: dev/CI use, and it's already built.)

If those answer the way I think they do (yes / not yet / keep), I'll start with
Phase E1 and have a working extension + bridge end-to-end before stopping.

---

## Key sources

- [Chrome: Changes to remote debugging switches (Mar 2025)](https://developer.chrome.com/blog/remote-debugging-port)
- [Playwright `BrowserType.connect_over_cdp` (Python)](https://playwright.dev/python/docs/api/class-browsertype)
- [browser-use #1520 — Chrome v136 default profile restriction](https://github.com/browser-use/browser-use/issues/1520)
- [Chromium `process_singleton_win.cc`](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/browser/process_singleton_win.cc)
- [Anthropic — Claude for Chrome](https://www.anthropic.com/news/claude-for-chrome) · [permissions](https://support.claude.com/en/articles/12012173-getting-started-with-claude-for-chrome)
- [`chrome.debugger` API](https://developer.chrome.com/docs/extensions/reference/api/debugger) · [`chrome.scripting`](https://developer.chrome.com/docs/extensions/reference/api/scripting) · [`chrome.sidePanel`](https://developer.chrome.com/docs/extensions/reference/api/sidePanel) · [Native messaging](https://developer.chrome.com/docs/apps/nativeMessaging)
- [Browser-Use Chrome extension listing](https://chromewebstore.google.com/detail/browser-use-for-ai-agents/jhlkcgimglagkgfknhbdkenkmpanalji)
- [OpenAI Atlas — Building ChatGPT Atlas](https://openai.com/index/building-chatgpt-atlas/)
