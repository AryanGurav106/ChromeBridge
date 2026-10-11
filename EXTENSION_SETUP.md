# The ChromeBridge extension — install, pairing, permissions, troubleshooting

This is the browser half of ChromeBridge. It acts inside your **already-open
Chrome window**, on tabs you already have, with your real cookies and sessions —
no relaunch, no profile copy, no second Chromium.

The other half is `mcp_server.py`, an MCP stdio server that Claude Code starts
for you. See `README.md` for the whole install; this file covers the extension
and the failure modes you will actually hit.

> **Local-only and gated three ways.** The bridge binds `127.0.0.1`, the
> handshake requires a shared `BRIDGE_TOKEN`, and every op that touches a page
> is refused unless you have allowed that exact origin in the side panel.
> Nothing reaches the internet from the extension itself.

---

## 1. Install (about a minute)

1. In Chrome, open `chrome://extensions`. Turn on **Developer mode** (top right).
2. Click **Load unpacked** and pick the `extension/` folder inside this repo.
3. The extension appears as **ChromeBridge**. Pin it (puzzle icon → pin) so the
   side panel is one click away. Clicking the toolbar icon opens the panel.

It is a normal unpacked MV3 extension: a service worker (`background.js`), a
side panel (`panel.html` / `panel.js`) and one `document_start` content script
(`listener_tag.js`).

## 2. Pair it with the server (once)

`BRIDGE_TOKEN` is the shared secret that stops any other local process from
driving your browser through the bridge port.

1. Copy `.env.example` to `.env` and leave `BRIDGE_TOKEN` empty.
2. Start Claude Code in the repo folder. The server generates a token on first
   run, **writes it into your `.env`**, and prints it to stderr.
3. Open `.env` and copy the `BRIDGE_TOKEN` value.
4. In the side panel, expand **Connection settings**, paste it into **Token**,
   click **Save & Connect**.

The status pill turns green and shows an uptime. Both sides remember the token
across restarts — you do this once.

Host and port are in the same settings block. The defaults (`127.0.0.1`,
`8765`) are almost always right: the server takes the first free port in a
10-port span starting there, and the extension sweeps the same span to find it,
so a busy 8765 needs no intervention from you.

## 3. Allow the sites Claude may act on

**Connected is not allowed.** ChromeBridge is default-deny per origin, so the
first thing you will see is a refusal, and that is working as intended.

The first-run loop:

1. Ask Claude to do something on a page.
2. Listing your tab group and creating a tab need no grant, so those succeed;
   the `navigate` (or the first read) is **refused**, and the refusal names the
   origin so Claude can tell you what to allow.
3. The side panel raises **Permission requested — `https://example.com` —
   Allow this site**. Click **Allow this site**.
4. Tell Claude to retry.

Notes on how grants behave:

- A grant covers **one origin** (scheme + host + port). `https://example.com`
  does not grant `https://app.example.com`.
- `file://` URLs have no origin per the URL spec, so the whole `file:` scheme is
  one decision and the panel shows it as such.
- `navigate` is checked against its **destination**, not the tab's current URL.
  Otherwise one granted site would be a doorway to every ungranted one.
- **Sites ChromeBridge can act on** lists every grant with a **Revoke** button.
- Grants are written **only** by this panel. The service worker cannot grant
  itself a site.
- The permission table is re-read on every single op, so a revoke or a pause
  takes effect on the very next one.

## 4. Pause

The **Pause** switch at the top of the panel is a kill switch. While paused,
every op that reads a page, changes it, opens a tab or resizes a window is
refused — including the ones that need no site grant — and the toolbar badge
stops advertising that ChromeBridge is live. Only status-reporting ops
(`ping`, `sw_info`, `debug_targets`, `get_url`, `get_active_tab`,
`tabs_context`) keep answering, plus `detach_debugger` so that pausing can still
clean up the yellow debugging infobar instead of stranding it.

Only you can resume it, from this panel.

## 5. What the panel shows

| Section | What it is for |
|---|---|
| Connection | Green/red pill, uptime, the `ws://host:port` endpoint, and a translated close-code message when it drops |
| Permission requested | The most recent refused origin, with one-click Allow |
| Sites ChromeBridge can act on | Every grant, when it was made, and Revoke |
| Recent operations | The last 40 ops with tab title, URL and favicon — what the agent actually did |
| Trusted input blocked | Appears when Chrome refused a debugger attach because of another extension (see below) |
| Connection settings | Token, host, port, Save & Connect, Reconnect. Collapsed by default; auto-opens when no token is set |

The operation log lives in `chrome.storage.local` rather than in either process,
because both ends are disposable: the panel document is destroyed when the panel
closes, and Chrome evicts the service worker on its own schedule.

---

## What the extension does

**Observation**

- Injects `mmid` attributes and returns a deterministic listing of interactive
  elements with accessible names, current values, placeholders, on-screen boxes,
  and flags for required / disabled / below-fold / occluded / in-dialog /
  in-iframe / offscreen.
- Recurses into open **and closed** shadow roots, same-origin iframes
  (including `srcdoc`) and cross-origin iframes. Closed roots are reached
  because `listener_tag.js` wraps `attachShadow` at `document_start`, so
  nothing can create one without handing the extension a reference — no
  debugger attach, which matters because the limitation below refuses that
  attach on exactly the login pages that need it.
- Reads page text, with collapsed subtrees hidden and code-editor gutters
  stripped.
- Leads an observation with a readiness banner when the page is still changing
  (in-flight requests, near-viewport unloaded images, `aria-busy`, a visible
  progressbar, `document.readyState`).

**Action**

- Untrusted path: a full pointer-event sequence
  (`pointerover` → … → `pointerdown` → `mousedown` → `pointerup` → `mouseup` →
  `click`), because Radix/HeadlessUI/MUI gate on `pointerdown` and a bare
  `el.click()` silently does nothing on those.
- Trusted path via `chrome.debugger` CDP: `Input.dispatchMouseEvent`,
  `mouseWheel`, `dispatchKeyEvent`, `insertText`. Used by the `computer` tool
  directly, and reached automatically when an untrusted click had **zero
  detectable effect** (URL, DOM and text all unchanged).
- Atomic multi-field form fill with combobox handling and submit-error capture.
- Navigation, screenshots, file upload, window resize, JS evaluation, console
  and network buffers.

**Trusted input works in a background tab.** Chrome silently drops CDP mouse
input to a hidden render widget, which is the normal condition — your tab is
hidden the moment you look at something else. ChromeBridge handles that with
focus emulation rather than by activating the tab. It will not steal your
window, switch your tab, or un-minimize anything; that would defeat the point.

## What it does not do

- Chrome's own surfaces: `chrome://`, other extensions' pages, `devtools://`,
  `view-source:`, `about:`. No grant can unlock these — Chrome refuses script
  injection and debugger attach there.
- Browser-generated console messages (CSP violations, network errors) never pass
  through `console.*` and so are not captured. Network failures do appear in
  `read_network_requests`.
- Multi-window orchestration beyond the tab's own window.

---

## Troubleshooting

**Pill stays red after Save & Connect.**
Token mismatch or nothing listening. Re-copy `BRIDGE_TOKEN` from `.env` (not
`.env.example`), check host and port against what the server printed on stderr,
click **Reconnect**. The panel translates close codes rather than echoing them:
*1008* is a bad token, *1006* means nothing is listening on that port at all,
*4001* is a protocol-version mismatch.

**Close code 4001 / "protocol mismatch".**
The loaded extension is out of step with `mcp_server.py`. Go to
`chrome://extensions` and hit the reload arrow on the ChromeBridge card — a
hand-loaded extension going stale against a newer server is the normal
condition, which is exactly why the handshake is versioned.

**Everything is refused with "Permission required".**
The origin is not granted. Open the panel and click **Allow this site** on the
Permission requested card. If the card is not there, the refusal happened on a
different origin than you think — the refusal message names it.

**Everything is refused with "ChromeBridge is PAUSED".**
Someone hit Pause. Resume it in the panel.

**"no active tab" / "cannot act on chrome://…".**
Switch to a real web tab. The extension's own pages and `chrome://` URLs are not
drivable by any extension. A tab from `tabs_create_mcp` is `about:blank` until
it is navigated, which is also refused for the same reason.

**A click "succeeded" but nothing happened on a login button.**
That page needs trusted input. ChromeBridge escalates automatically when a click
has no detectable effect, which lazy-attaches `chrome.debugger` to the tab —
that is what the yellow *"ChromeBridge started debugging this browser"* infobar
means. It detaches on server shutdown. Chrome does not allow hiding it.

**Trusted input works exactly once on a tab, then fails with "Cannot access a
chrome-extension:// URL of different extension".**
This is Chrome policy, not a ChromeBridge bug, and it is the sharpest edge in
the project. Chrome checks attach permission across a tab's **entire frame
tree**, so one frame belonging to a *different* extension refuses the attach for
the whole tab — on a tab whose own URL is plainly `https`.

Measured with Passbolt: it injects its iframe **when a login field is focused**,
so the first trusted click on a login page works and every one after it is
refused. Password managers inject on exactly the pages where an agent needs
trusted input most.

- Not recoverable by detaching, retrying, or opening a new tab on the same URL.
- Still fine: `read_page`, `find`, `get_page_text`, `form_input`, `fill_form`
  and ordinary untrusted clicks.
- The panel shows a notice naming the offending extension, and the
  `debug_targets` tool prints Chrome's own target table.
- Fix: disable the other extension for that site while the agent works there.

**`read_console_messages` says capture is not active.**
`listener_tag.js` runs at `document_start`, so a page loaded *before* the
extension was installed or reloaded has no buffer. Reload the page once.

**Two sessions, one extension.**
The server binds the first free port in `BRIDGE_PORT`..`BRIDGE_PORT+9`
(8765-8774 by default) so a second Claude Code session does not die with
"address already in use", and the extension **sweeps that same span** — one pass
over all ten ports counts as one connection attempt, so the 1s→15s backoff
applies per sweep, not per port. You never have to correct the port by hand.

What you cannot do is drive one Chrome from two sessions. The sweep stops at the
first server that answers, so the second session gets a healthy bridge nobody is
connected to and its tools report "Chrome extension is not connected". Close the
first session and the extension re-sweeps and finds the second.

**Extension errors / odd state.**
`chrome://extensions` → ChromeBridge → **service worker → inspect** for its
logs. **Reload** on the card restarts it cleanly. MV3 workers are evicted for
idleness routinely; the bridge sends an app-level ping every 20s to keep it
awake while connected, and the extension reconnects with 1s→15s backoff, so it
normally self-heals within seconds of the server coming up.

---

## Why an extension at all

A normally-started Chrome on Windows in 2025-2026 cannot be driven externally
without one:

1. It does not open a CDP listener.
2. Chrome 136+ silently strips `--remote-debugging-port` when it is paired with
   the default `User Data` directory.
3. The profile singleton lock prevents launching a second debug-mode Chrome on
   the same profile while the first is running.

An extension runs **inside** the real Chrome, so it sidesteps all three — and it
is the same mechanism (`chrome.debugger`) Claude-in-Chrome uses. The full
research write-up is in `CHROME_ATTACH_PLAN.md`.
