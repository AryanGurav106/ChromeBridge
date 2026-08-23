// ChromeBridge — service worker.
//
// Connects to ws://127.0.0.1:<port>/ (the Python bridge), authenticates with a
// per-session token from chrome.storage.local, then services ops from the
// agent. All page interaction goes through chrome.scripting.executeScript so we
// stay on the user's already-running Chrome with their real profile/cookies.
//
// Operations served: ping, get_active_tab, get_url, get_dom_text,
// get_interactive_elements (string or structured), click, enter_text,
// press_keys, screenshot, navigate, page_fingerprint.

const DEFAULTS = { host: "127.0.0.1", port: 8765, token: "" };

// Wire-protocol version, sent in the hello frame and echoed back in the welcome.
// MUST MATCH PROTOCOL_VERSION in core/bridge/server.py: the server closes with
// 4001 when the two differ, and a hello carrying NO `protocol` field at all is
// read as client=0 and rejected the same way. This extension is installed by hand
// ("Load unpacked"), so a stale copy running against a newer mcp_server.py is the
// normal condition rather than an edge case — bump both halves together whenever
// an op's request/response shape changes incompatibly.
const PROTOCOL_VERSION = 1;

// The server binds the FIRST FREE port in [configured, configured+SPAN), so a
// second Claude Code session lands on 8766 and an extension that only ever tried
// one port would never find it. KEEP IN SYNC with PORT_RANGE_SPAN in
// core/bridge/server.py — widening it there alone strands sessions on ports
// nothing ever knocks on.
const PORT_RANGE_SPAN = 10;

// Gap between two ports of the SAME sweep. A refused loopback connect fails in
// about a millisecond, so this is the only thing standing between ten probes and
// a tight loop. The 1s->15s backoff below applies per SWEEP rather than per port,
// which is what keeps the configured port on the retry cadence it always had.
const PROBE_STEP_MS = 200;

// A port in the span can be held by something that accepts the TCP connection and
// then never answers the WebSocket upgrade — any unrelated local service will do
// that. A refused port fails instantly, but a silent one has no event at all, so
// without a budget the sweep parks on it and the bridge is never found. Generous
// for a loopback handshake; a probe still unwelcomed by then is abandoned.
const HANDSHAKE_TIMEOUT_MS = 3000;

let ws = null;
let reconnectDelayMs = 1000;
// Which port of the span the next attempt uses. 0 is the configured port and
// every sweep restarts there, so the common single-session case is unchanged.
let _probeOffset = 0;
// Non-empty means STOP retrying. Set only for a protocol mismatch: the same two
// builds disagree forever, so a 1s retry loop would just bury the one message
// that says what to do. Cleared by a settings change or the panel's Reconnect.
let _haltReason = "";
// The address the current socket actually used, alongside the port the user
// configured. The panel renders its endpoint line from this, because after a
// probe the two legitimately differ.
let _endpoint = { host: DEFAULTS.host, port: DEFAULTS.port, configuredPort: DEFAULTS.port };
// What the welcome frame said we are talking to: { protocol, version }.
let _server = null;
let lastStatus = { connected: false, last_error: "" };

// Make clicking the toolbar icon open the side panel (otherwise the action
// button is silent and there's no obvious way to reach panel.html).
try {
  chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch((e) => console.warn("[bridge] setPanelBehavior failed:", e));
} catch (e) {
  console.warn("[bridge] sidePanel API not available:", e);
}

// --------------------- WS lifecycle -----------------------------------------
async function getConfig() {
  const stored = await chrome.storage.local.get(["bridge_host", "bridge_port", "bridge_token"]);
  const port = parseInt(stored.bridge_port || DEFAULTS.port, 10);
  return {
    host: stored.bridge_host || DEFAULTS.host,
    // A NaN survives arithmetic, so an unparseable stored port would become
    // ws://host:NaN on every one of the ten probes rather than failing once.
    port: Number.isFinite(port) ? port : DEFAULTS.port,
    token: stored.bridge_token || DEFAULTS.token,
  };
}

// The version we announce in the hello frame — the server logs it, and the panel
// shows it next to the server's own. Read from the manifest rather than written
// out here, because a second copy of a version number is a second thing to
// forget. Guarded: the node:vm harnesses (tools/test_ops.js, test_permissions.js)
// mount this file against a hand-written chrome mock that has no manifest.
function manifestVersion() {
  try {
    const m = chrome.runtime.getManifest();
    return (m && m.version) || "unknown";
  } catch (e) { return "unknown"; }
}

async function setBadge(text, color) {
  try {
    await chrome.action.setBadgeText({ text });
    if (color) await chrome.action.setBadgeBackgroundColor({ color });
  } catch (e) {}
}

// `since` is the moment the CURRENT connection came up (0 when down) — the side
// panel renders it as a live uptime, so it must not be refreshed by later
// setStatus(true) calls for the same socket.
let _connectedSince = 0;
async function setStatus(connected, err) {
  if (connected && !lastStatus.connected) _connectedSince = Date.now();
  if (!connected) _connectedSince = 0;
  lastStatus = {
    connected, last_error: err || "", since: _connectedSince,
    // The address this socket ACTUALLY used, plus the configured one. The panel
    // prints the endpoint from these: showing ws://…:8765 while the socket is on
    // 8766 turns the design (first free port of a span) into a reported bug.
    host: _endpoint.host, port: _endpoint.port,
    configured_port: _endpoint.configuredPort,
    // Which mcp_server.py we are attached to. Only meaningful while up.
    server: connected ? _server : null,
  };
  try { await chrome.storage.local.set({ bridge_status: lastStatus }); } catch (e) {}
  try { chrome.runtime.sendMessage({ kind: "status", status: lastStatus }); } catch (e) {}
  await refreshBadge();
}

// The badge answers "is ChromeBridge going to do anything right now", and PAUSE
// overrides connection for that question: a paused bridge showing "ON" would be
// a lie at the one moment the user most wants to trust the indicator. Kept as its
// own function because the pause flag changes without any status change (see the
// storage.onChanged hook below).
async function refreshBadge() {
  let paused = false;
  try { const s = await chrome.storage.local.get([PAUSE_KEY]); paused = !!s[PAUSE_KEY]; } catch (e) {}
  if (paused) return await setBadge("II", "#b45309");
  return await setBadge(lastStatus.connected ? "ON" : "OFF",
                        lastStatus.connected ? "#16a34a" : "#dc2626");
}

// Rolling op history for the side panel's activity feed. Kept in
// chrome.storage.local because the panel document is destroyed whenever the
// panel closes, and this service worker is evicted on its own schedule — either
// one alone loses the log.
const ACTION_LOG_MAX = 40;
let _lastAction = null;
let _actionLog = [];
let _actionLogLoaded = false;

async function _loadActionLog() {
  if (_actionLogLoaded) return;
  _actionLogLoaded = true;
  try {
    const s = await chrome.storage.local.get(["bridge_action_log"]);
    if (Array.isArray(s.bridge_action_log)) {
      _actionLog = s.bridge_action_log.slice(-ACTION_LOG_MAX);
    }
  } catch (e) {}
}

async function broadcastAction(op, tab) {
  await _loadActionLog();
  _lastAction = {
    op,
    tab_title: tab && tab.title ? tab.title : "",
    tab_url: tab && tab.url ? tab.url : "",
    tab_favicon: tab && tab.favIconUrl ? tab.favIconUrl : "",
    tab_id: tab && tab.id,
    ts: Date.now(),
  };
  _actionLog.push(_lastAction);
  if (_actionLog.length > ACTION_LOG_MAX) {
    _actionLog = _actionLog.slice(-ACTION_LOG_MAX);
  }
  try {
    await chrome.storage.local.set({
      bridge_last_action: _lastAction,
      bridge_action_log: _actionLog,
    });
  } catch (e) {}
  try { chrome.runtime.sendMessage({ kind: "action", action: _lastAction }); } catch (e) {}
}

// --------------------- per-origin permission gate ---------------------------
// This extension holds <all_urls> + debugger, so without a gate every MCP tool
// call could drive ANY tab the user has open — bank, webmail, admin console —
// with trusted CDP input. The gate is the single place that decides whether an
// op may touch a page, and it sits in the op router (handleOp) rather than in
// each op, so that an op added later is refused until someone deliberately
// exempts it. Default deny, fail closed: if the permission store cannot be read
// at all, nothing is allowed.
//
// Storage (chrome.storage.local). The side panel owns every key except the
// pending record, which the gate itself writes when it refuses:
//   bridge_permissions     { origins: { "https://example.com": { granted: <ms epoch> } } }
//   bridge_paused          boolean — global kill switch, checked BEFORE origins
//   bridge_pending_origin  { origin, op, ts } — the most recent denial, so the
//                          panel can offer a one-click Allow for that exact site
//   bridge_debugger_block  { tabId, url, extensions, ts } — see recordDebuggerBlock
const PERM_KEY = "bridge_permissions";
const PAUSE_KEY = "bridge_paused";
const PENDING_KEY = "bridge_pending_origin";
const DEBUG_BLOCK_KEY = "bridge_debugger_block";

// Ops that neither expose page content nor deliver input. EVERYTHING ELSE is
// gated — including ops not listed anywhere here, which is the point: a new op
// is gated by omission rather than ungated by omission.
//
// tabs_context / tabs_create / tabs_close stay open deliberately: listing the
// agent's own tab group is how Claude discovers what is open in order to ask for
// permission on the right site, and refusing it would leave the agent unable to
// name the origin the user is being asked about. get_active_tab / get_url return
// the same url+title the user can already read off their own tab strip.
// resize_window and detach_debugger touch the window/session, never the document.
const UNGATED_OPS = new Set([
  "ping", "sw_info", "debug_targets",
  "tabs_context", "tabs_create", "tabs_close",
  "get_active_tab", "get_url", "resize_window", "detach_debugger",
]);

// Ops that still answer while PAUSED. They read nothing out of the page and
// change nothing in the browser, so they can keep reporting state while
// everything else is frozen — and detach_debugger stays available so pausing can
// still clean up the yellow "is debugging" infobar rather than stranding it.
const PAUSE_EXEMPT_OPS = new Set([
  "ping", "sw_info", "debug_targets",
  "get_url", "get_active_tab", "tabs_context", "detach_debugger",
]);

// Schemes no grant can ever unlock: Chrome refuses extension script injection and
// debugger attach on its own surfaces regardless of what the user allows. These
// must NOT produce the permission message — it would send the user to the side
// panel to grant something that cannot be granted.
const CLOSED_SCHEMES = new Set([
  "chrome:", "chrome-extension:", "chrome-untrusted:", "devtools:",
  "edge:", "about:", "view-source:",
]);

// Resolve the origin a gate decision is made against.
// file:// URLs have origin "null" per the URL spec; key them by scheme so they
// stay deliberately grantable instead of being permanently unreachable (and so
// that granting one local file does not silently grant every other one — the
// whole file: scheme is one decision, and the panel shows it as such).
function _gateOrigin(rawUrl) {
  const url = String(rawUrl || "");
  if (!url) return { url, origin: null, closed: false };
  let u;
  try { u = new URL(url); } catch (e) { return { url, origin: null, closed: false }; }
  if (CLOSED_SCHEMES.has(u.protocol)) return { url, origin: null, closed: true, scheme: u.protocol };
  const origin = (u.origin && u.origin !== "null") ? u.origin : `${u.protocol}//`;
  return { url, origin, closed: false };
}

// Keep the GATE and the navigate op reading the same destination. navigate
// tolerates protocol-less URLs ("example.com"); gating on the raw string while
// the op visits the rewritten one would be a permission check on a URL nobody
// opens.
function normalizeNavUrl(dest) {
  const s = String(dest || "");
  return /^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(s) ? s : `https://${s}`;
}

// Read storage on EVERY gated op instead of caching. A revoke or a pause has to
// take effect on the very next op, and a stale in-memory copy of a permission
// table is exactly how a cache becomes a hole. A storage.local read is
// sub-millisecond next to the executeScript/CDP round-trips that follow it.
// A read that THROWS yields no origins and therefore denies: fail closed.
async function _permState() {
  let s = {};
  try { s = await chrome.storage.local.get([PERM_KEY, PAUSE_KEY]); } catch (e) { s = {}; }
  const rec = s && s[PERM_KEY];
  const origins = (rec && rec.origins && typeof rec.origins === "object") ? rec.origins : {};
  return { paused: !!(s && s[PAUSE_KEY]), origins };
}

// Publish the refused origin so the panel can offer "Allow" for exactly the site
// the agent just tried to use — the first-run interaction. Best effort: this runs
// on a path that is about to throw, and a storage failure must not replace the
// caller's explanation with an unrelated error.
async function _recordPending(origin, op) {
  try { await chrome.storage.local.set({ [PENDING_KEY]: { origin, op, ts: Date.now() } }); }
  catch (e) {}
}

// TRUE only when this file is running as an installed Chrome extension.
// chrome.runtime.id is a non-empty string in every MV3 service worker and cannot
// be absent there, so a FALSE result means background.js is being executed
// outside Chrome entirely — tools/test_ops.js loads it into a node:vm against a
// hand-written `chrome` mock to exercise the op router. Off-browser there is no
// user, no real tab and nothing to protect, and refusing there would make the
// router untestable while protecting nobody.
//
// This is NOT a bypass reachable from a page, a site, or the MCP client: nothing
// any of them can do removes the extension's own runtime id. Every real tab goes
// through the full gate.
function _isInstalledExtension() {
  try { return typeof chrome.runtime.id === "string" && chrome.runtime.id.length > 0; }
  catch (e) { return false; }
}

// Throws (with an explanation the AGENT can act on) when `op` may not run.
// Order matters twice over:
//   - pause is checked before the UNGATED short-circuit, because tabs_create,
//     tabs_close and resize_window need no site grant but still CHANGE the
//     browser. A user hits Pause precisely when something is going wrong, and
//     tabs that keep opening after that make the switch a lie. Only the
//     read-nothing/change-nothing ops in PAUSE_EXEMPT_OPS survive.
//   - pause is checked before origins, because a paused bridge should say
//     "paused" rather than send the user hunting for a site to allow.
// Set true to bypass per-site permission prompts (every origin allowed).
// See the note inside assertOpAllowed for exactly what this gives up.
const ALLOW_ALL_ORIGINS = true;

async function assertOpAllowed(op, params) {
  if (!_isInstalledExtension()) return;

  const st = await _permState();
  if (st.paused && !PAUSE_EXEMPT_OPS.has(op)) {
    throw new Error(
      `ChromeBridge is PAUSED, so nothing was read, clicked or changed (refused op: ${op}). ` +
      `The user paused it from the ChromeBridge side panel and only they can resume it there — ` +
      `ask them to click Resume, then retry.`);
  }
  if (UNGATED_OPS.has(op)) return;

  const tab = await resolveTab(params);
  // navigate is gated on the DESTINATION, not on wherever the tab currently is:
  // the entire point of the op is to leave the current origin, so gating on the
  // old one would turn any granted site into a doorway to every ungranted one.
  // back/forward have no knowable destination, so they are gated on the tab's
  // current origin; whatever they land on still needs its own grant before a
  // single byte of it can be read.
  let raw = tab && tab.url;
  if (op === "navigate") {
    const dest = String((params && params.url) || "");
    if (dest && dest !== "back" && dest !== "forward") raw = normalizeNavUrl(dest);
  }

  const g = _gateOrigin(raw);
  if (g.closed) {
    const blankHint = /^about:blank/i.test(g.url)
      ? ` A tab from tabs_create_mcp is about:blank until you navigate it — call navigate first.`
      : "";
    throw new Error(
      `ChromeBridge cannot act on ${g.url}. Chrome closes its own surfaces ` +
      `(chrome://, chrome-extension://, edge://, about:, devtools://) to extensions, so no ` +
      `permission can grant access here — this is a browser rule, not a ChromeBridge setting. ` +
      `Move to a normal http(s) page first.${blankHint}`);
  }
  if (!g.origin) {
    throw new Error(
      `ChromeBridge could not determine an origin for this tab (url=${JSON.stringify(String(g.url).slice(0, 120))}), ` +
      `so it refused rather than act on a page it cannot identify. Navigate the tab to an ` +
      `http(s) URL and retry.`);
  }
  if (st.origins[g.origin]) return;

  // DEFAULT-ALLOW. Per-site grants are bypassed by ALLOW_ALL_ORIGINS, set for
  // real-world stress testing where an agent must reach arbitrary sites without a
  // human clicking Allow for each one.
  //
  // WHAT THIS TURNS OFF: this gate is the only thing that stops an op acting on
  // a logged-in origin the user never approved — their mail, ticketing, admin
  // dashboards. The PAUSE switch above still works, and Chrome's own closed
  // surfaces (chrome://, devtools://) are still unreachable, but per-site consent
  // is gone. Flip this back to false to restore it; nothing else changed.
  if (ALLOW_ALL_ORIGINS) return;

  await _recordPending(g.origin, op);
  throw new Error(
    `Permission required: ChromeBridge is not allowed to act on ${g.origin}. Ask the user to ` +
    `open the ChromeBridge side panel and click "Allow" for this site, then retry. ` +
    `Nothing was read, clicked or changed (refused op: ${op}).`);
}

// S6 — surface a refused debugger attach (limitation #12). Another extension's
// injected iframe makes Chrome refuse chrome.debugger.attach for the WHOLE tab,
// with an error naming neither the tab nor the cause. The agent already gets the
// full explanation; persist it so the SIDE PANEL can tell the user this is a
// Chrome policy conflict with another extension rather than a broken product.
// Fire and forget on an error path: never let a storage failure replace the
// caller's error.
function recordDebuggerBlock(tabId, url, bad) {
  try {
    const p = chrome.storage.local.set({
      [DEBUG_BLOCK_KEY]: {
        tabId,
        url: String(url || "").slice(0, 200),
        extensions: Array.from(new Set((bad || []).map((b) => b && b.id).filter(Boolean))),
        ts: Date.now(),
      },
    });
    if (p && p.catch) p.catch(() => {});
  } catch (e) {}
}

let reconnectTimer = null;
async function connect() {
  // Don't open a duplicate socket if one is already in flight or open.
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }
  const cfg = await getConfig();
  if (!cfg.token) {
    await setStatus(false, "no token set — open the side panel and paste it");
    return;
  }
  if (_haltReason) {
    // A protocol mismatch is not waited out, it is reloaded out. Re-publish the
    // reason instead of opening a socket that will be closed the same way.
    await setStatus(false, _haltReason);
    return;
  }

  const port = cfg.port + _probeOffset;
  if (!(port >= 1 && port <= 65535)) {
    // Only reachable when the configured port sits within SPAN of the top of the
    // range. Fold the sweep rather than emitting ws://host:65540.
    _probeOffset = 0;
    scheduleReconnect();
    return;
  }
  _endpoint = { host: cfg.host, port, configuredPort: cfg.port };
  const url = `ws://${cfg.host}:${port}`;
  // Bind the socket to a local first and compare identity in every handler: the
  // panel's Reconnect closes the old socket and connects in the same turn, so an
  // old close event can otherwise land AFTER the replacement exists and null out
  // `ws` / schedule a competing retry against a healthy connection.
  let sock;
  try {
    sock = new WebSocket(url);
  } catch (e) {
    await setStatus(false, `bad ws url: ${e}`);
    scheduleReconnect();
    return;
  }
  ws = sock;
  let welcomed = false;
  let settled = false;
  const handshakeTimer = setTimeout(() => {
    if (welcomed) return;
    // Settle DIRECTLY rather than calling sock.close() and waiting for the close
    // event to come back: this timer exists precisely for a socket that is
    // producing no events, so routing its own recovery through one more event
    // would be trusting the thing that just failed to speak.
    try { sock.close(); } catch (e) {}
    settle(`no answer from ${url} within ${Math.round(HANDSHAKE_TIMEOUT_MS / 1000)}s`, null);
  }, HANDSHAKE_TIMEOUT_MS);

  sock.onopen = () => {
    // The FULL hello. A bare {hello: token} is read by the server as protocol 0
    // and closed with 4001, so an under-specified handshake never connects at all.
    sock.send(JSON.stringify({
      hello: cfg.token,
      protocol: PROTOCOL_VERSION,
      client: "chromebridge-extension",
      version: manifestVersion(),
    }));
  };

  sock.onmessage = async (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    if (msg.welcome) {
      welcomed = true;
      clearTimeout(handshakeTimer);
      // Keep what the other half said it is. Two builds one version apart behave
      // differently and look identical unless both numbers are recorded here.
      _server = { protocol: msg.protocol, version: msg.version || "unknown" };
      reconnectDelayMs = 1000;
      await setStatus(true, "");
      return;
    }
    if (msg.id && msg.op) {
      await handleOp(msg);
    }
  };

  sock.onerror = async (ev) => {
    if (sock !== ws || settled) return;
    // The browser always follows this with a close event carrying a real code,
    // and that code is what the decision below is made on — so this only
    // publishes, it never settles. Mid-sweep it would fire once per refused port,
    // and ten "ws error" writes would erase the line saying a search is running.
    if (_probeOffset === 0) await setStatus(false, "ws error");
  };

  sock.onclose = (ev) => {
    settle(ev.reason ? `closed (${ev.code}: ${ev.reason})` : `closed (${ev.code})`, ev.code);
  };

  // The single exit for this socket: whatever ended it (a close from either
  // side, or the handshake budget running out) decides where the search goes
  // next, exactly once.
  async function settle(detail, code) {
    if (settled) return;
    settled = true;
    clearTimeout(handshakeTimer);
    if (sock !== ws) return;
    ws = null;
    _server = null;

    // 4001 — protocol mismatch. NOT transient: retrying every second forever
    // hides the one problem the user can actually fix (reload the extension).
    if (code === 4001) {
      _haltReason = detail;
      _probeOffset = 0;
      await setStatus(false, detail);
      return;                       // deliberately no scheduleReconnect
    }

    // 1008 — bad token. This IS the bridge, holding a different secret; sweeping
    // on from here would replace one accurate error with nine "nothing is
    // listening" ones. Stay on this port and retry it on the normal backoff, so
    // fixing .env and restarting the server still self-heals.
    if (code === 1008) {
      await setStatus(false, detail);
      scheduleReconnect();
      return;
    }

    if (welcomed) {
      // We had a working bridge and lost it. Start the next search at the
      // configured port rather than continuing from wherever this one landed.
      _probeOffset = 0;
      await setStatus(false, detail);
      scheduleReconnect();
      return;
    }

    // Nothing usable answered here — try the next port of the span.
    _probeOffset++;
    if (_probeOffset < PORT_RANGE_SPAN) {
      // One status write per sweep, not one per port: a sweep is a single
      // attempt to find the bridge, and ten near-identical failures would just
      // thrash the panel while it is still looking.
      if (_probeOffset === 1) {
        const base = _endpoint.configuredPort;
        await setStatus(false,
          `looking for the bridge on ports ${base}-${base + PORT_RANGE_SPAN - 1}…`);
      }
      scheduleReconnect(PROBE_STEP_MS);
      return;
    }
    // Span exhausted. The whole sweep is what counts as one failed attempt, so
    // this — and only this — is where the backoff advances.
    _probeOffset = 0;
    await setStatus(false, detail);
    scheduleReconnect();
  }
}

// `delayMs` is a step WITHIN a port sweep: it must not advance the backoff,
// because one pass over the span is ONE attempt to find the bridge. Called with
// no argument (sweep finished, or an ordinary reconnect) it keeps the original
// 1s->15s doubling.
function scheduleReconnect(delayMs) {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  const wait = (delayMs != null) ? delayMs : reconnectDelayMs;
  reconnectTimer = setTimeout(() => { reconnectTimer = null; connect(); }, wait);
  if (delayMs == null) reconnectDelayMs = Math.min(reconnectDelayMs * 2, 15000);
}

// Drop the current socket and start a fresh search at the CONFIGURED port.
// Releasing our reference before close() is what makes the identity guard in the
// handlers work: the old socket's close then sees a different owner of `ws` and
// neither advances the sweep nor schedules a retry racing this one. Without the
// reset, a user who corrects the port and hits Save would have their new value
// skipped, because a half-finished sweep would resume at the port after it.
function restartConnection(delayMs) {
  _probeOffset = 0;
  _haltReason = "";
  reconnectDelayMs = 1000;
  const old = ws;
  ws = null;
  try { old && old.close(); } catch (e) {}
  if (delayMs != null) scheduleReconnect(delayMs);
  else connect();
}

async function reply(id, ok, payload) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  const body = ok ? { id, ok: true, result: payload } : { id, ok: false, error: String(payload) };
  ws.send(JSON.stringify(body));
}

// Boot: connect on install, on browser start, and re-connect if storage changes.
chrome.runtime.onInstalled.addListener(() => { connect(); });
chrome.runtime.onStartup.addListener(() => { connect(); });
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes.bridge_token || changes.bridge_host || changes.bridge_port) {
    // A settings change points the extension at a (possibly different) server,
    // so it clears a protocol halt as well as the sweep position. This now has to
    // schedule the retry itself: the identity guard deliberately silences the
    // old socket's close handler, which is what used to do it.
    restartConnection(PROBE_STEP_MS);
  }
  // Pause is toggled from the side panel, which never touches the socket, so the
  // badge would otherwise keep advertising "ON" while every op is being refused.
  if (changes[PAUSE_KEY]) { refreshBadge(); }
});
// Also kick a connect when the SW first wakes.
connect();

// --------------------- helpers ----------------------------------------------
async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab) throw new Error("no active tab in last-focused window");
  return tab;
}

// MCP-style per-tab routing: ops may carry an explicit tabId; fall back to the
// active tab for backward compatibility with the legacy (active-tab-only) path.
async function resolveTab(params) {
  if (params && params.tabId != null) {
    const id = parseInt(params.tabId, 10);
    if (!Number.isFinite(id)) throw new Error(`invalid tabId: ${params.tabId}`);
    try {
      return await chrome.tabs.get(id);
    } catch (e) {
      throw new Error(`tab ${id} not found (closed?) — call tabs_context_mcp for fresh tab IDs`);
    }
  }
  return await activeTab();
}

async function runInTab(tabId, func, args = [], frameId = null) {
  const target = (frameId !== null && frameId !== undefined)
    ? { tabId, frameIds: [frameId] }
    : { tabId, allFrames: false };
  const [res] = await chrome.scripting.executeScript({
    target,
    world: "MAIN",
    func, args,
  });
  return res && res.result;
}

// --------------------- cross-origin frame routing ---------------------
// Cross-origin iframe contents can't be reached from the top frame's JS, but
// chrome.scripting CAN inject into them per-frameId. Their listing entries
// carry mmid "f<frameId>:<n>"; this strips the prefix back into a frame-local
// selector + target frameId for every action op.
function resolveFrameSelector(selector) {
  const m = /\[mmid=['"]?f(\d+):(\d+)['"]?\]/.exec(selector || '');
  if (!m) return { frameId: null, selector };
  return { frameId: parseInt(m[1], 10), selector: `[mmid='${m[2]}']` };
}
// tabId -> Map(frameId -> {x, y}) — each cross-origin frame's shell offset in
// TOP-document coordinates, captured at collection time. CDP trusted input
// always dispatches in top-document coords, so in-frame rects need this added.
const _frameShells = new Map();

// --------------------- live element highlight (S4) ---------------------
// Pulses a colored outline on whichever element the agent is about to touch,
// so the user can see what's happening on their actual screen in real time —
// instead of staring at a terminal log and wondering which button got clicked.
function _highlightPage(selector, kind) {
  // Registry-first resolve: [mmid='N'] may target an element inside an open
  // shadow root, which document.querySelector cannot reach. window.__mmidReg is
  // rebuilt by every collection walk (see _collectInteractivePage).
  const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
  const el = q(selector);
  if (!el) return false;
  // Inject the style into the element's OWN document — for elements inside
  // same-origin iframes, a top-document stylesheet can't style them.
  const doc = el.ownerDocument || document;
  if (!doc.getElementById('__chromebridge_hl_style__')) {
    const s = doc.createElement('style');
    s.id = '__chromebridge_hl_style__';
    s.textContent = `
      @keyframes __ab_pulse__ {
        0%   { box-shadow: 0 0 0 0   var(--ab-color, rgba(255,64,64,.85)), 0 0 0 0 var(--ab-color, rgba(255,64,64,.85)); }
        50%  { box-shadow: 0 0 0 4px var(--ab-color, rgba(255,64,64,.85)), 0 0 12px 4px var(--ab-color, rgba(255,64,64,.45)); }
        100% { box-shadow: 0 0 0 0   var(--ab-color, rgba(255,64,64,0)),   0 0 0 0 var(--ab-color, rgba(255,64,64,0)); }
      }
      .__ab_highlight__ {
        outline: 2px solid var(--ab-color, rgba(255,64,64,.85)) !important;
        outline-offset: 1px !important;
        animation: __ab_pulse__ 0.9s ease-out 1 !important;
        z-index: 2147483647 !important;
      }`;
    doc.documentElement.appendChild(s);
  }
  const color = ({ click: 'rgba(64,180,255,.9)',
                   type:  'rgba(120,255,64,.9)',
                   submit:'rgba(255,180,64,.95)' })[kind] || 'rgba(255,64,64,.9)';
  el.style.setProperty('--ab-color', color);
  el.classList.add('__ab_highlight__');
  setTimeout(() => { try { el.classList.remove('__ab_highlight__'); } catch (e) {} }, 1000);
  return true;
}

async function highlightInTab(tabId, selector, kind) {
  // Best-effort — never block an action because of UI sugar.
  try {
    const rt = resolveFrameSelector(selector);
    await runInTab(tabId, _highlightPage, [rt.selector, kind], rt.frameId);
  } catch (e) {}
}

// --------------------- MCP tab group ----------------------------------------
// Claude-in-Chrome-style session model: agent tabs live in one dedicated Chrome
// tab group so the user can see (and close) everything the agent owns at once.
let _mcpGroupId = null;

async function _getMcpGroup(create) {
  if (_mcpGroupId == null) {
    try {
      const st = await chrome.storage.local.get("mcp_group_id");
      if (st && st.mcp_group_id != null) _mcpGroupId = st.mcp_group_id;
    } catch (e) {}
  }
  if (_mcpGroupId != null) {
    try {
      await chrome.tabGroups.get(_mcpGroupId);
      return _mcpGroupId;
    } catch (e) { _mcpGroupId = null; } // group was closed
  }
  if (!create) return null;
  // active:false — creating the agent's tab must NOT pull the user away from what they
  // are looking at. Trusted input works on background tabs via ensureInputReady()
  // (Emulation.setFocusEmulationEnabled + Page.setWebLifecycleState), so there is no
  // functional reason to activate it. Reported by the user twice: the view jumping to
  // the newest tab mid-task is exactly the disruption this project exists to avoid.
  const tab = await chrome.tabs.create({ url: "about:blank", active: false });
  const gid = await chrome.tabs.group({ tabIds: [tab.id] });
  try { await chrome.tabGroups.update(gid, { title: "Claude", color: "orange" }); } catch (e) {}
  _mcpGroupId = gid;
  try { await chrome.storage.local.set({ mcp_group_id: gid }); } catch (e) {}
  return gid;
}

async function _mcpGroupTabs(gid) {
  const tabs = await chrome.tabs.query({ groupId: gid });
  return tabs.map(t => ({ id: t.id, url: t.url, title: t.title, active: !!t.active }));
}

// --------------------- chrome.debugger (trusted input) ---------------------
// Lazy, per-tab attach. Used ONLY when an action explicitly asks for trusted
// input (login buttons, payment, file pickers, OAuth, "Continue with Google",
// or a normal click that produced no effect). Chrome will show its yellow
// "ChromeBridge started debugging this browser" infobar on those
// tabs — accepted tradeoff for trusted events.
const _attachedTabs = new Map(); // tabId -> true

// Chrome refuses chrome.debugger.attach for the WHOLE TAB if ANY frame in it is a
// chrome-extension:// URL owned by a DIFFERENT extension: ExtensionMayAttachToURL
// is applied across the entire frame tree, not just the main document. Password
// managers, form fillers and grammar checkers inject exactly such frames — and
// they inject them on LOGIN PAGES, which is precisely where trusted input matters.
//
// MEASURED, after four wrong theories (reload-poisoned tabs, service-worker
// termination, cross-process navigation, our own CDP ordering — all disproved):
// on a saucedemo login tab, Passbolt injected an iframe when the username field
// was focused. The first trusted click succeeded, Chrome then fired onDetach with
// `target_closed`, and every later attach was refused with the cross-extension
// error while the tab's own URL was plainly https. A control run of three trusted
// ops on a page with NO login form kept its session and never detached.
//
// This is Chrome policy. It cannot be recovered by detaching, by retrying, or by
// opening a new tab on the same URL — the other extension injects there too. Say
// so precisely, name the extension, and name what still works.
async function blockingExtensionFrames(tabId) {
  const me = chrome.runtime.id;
  try {
    const frames = await chrome.webNavigation.getAllFrames({ tabId });
    const bad = [];
    for (const f of frames || []) {
      const u = String((f && f.url) || "");
      if (u.indexOf("chrome-extension://") !== 0) continue;
      const host = u.slice("chrome-extension://".length).split("/")[0];
      if (host && host !== me) bad.push({ id: host, url: u.slice(0, 100) });
    }
    return bad;
  } catch (e) { return []; }
}

// The EXPLANATION must not depend on the ENUMERATION succeeding. First cut made
// the good message conditional on blockingExtensionFrames() returning rows, and
// live it returned none — chrome.webNavigation.getAllFrames does not report other
// extensions' frames — so the caller fell through to the old misleading text on
// the one page that proves the bug. Chrome's own error string is already
// conclusive that some other extension owns a frame here; naming which one is a
// bonus, not a precondition.
function crossExtensionAttachError(tabId, where, bad) {
  const ids = Array.from(new Set((bad || []).map((b) => b.id)));
  const who = ids.length
    ? `another extension (${ids.join(", ")}) has injected an iframe into this page`
    : `another extension has injected an iframe into this page (Chrome will not tell ` +
      `us which — likely a password manager, form filler or grammar checker; check ` +
      `chrome://extensions for one active on this site)`;
  const example = bad && bad.length ? ` Example frame: ${bad[0].url}` : "";
  return new Error(
    `Trusted input is unavailable on tab ${tabId}${where}: ${who}, and Chrome refuses ` +
    `chrome.debugger.attach to any tab containing a frame owned by a different ` +
    `extension — it checks the whole frame tree, so the page's own https URL is not ` +
    `the problem.${example}
` +
    `Retrying on THIS tab will not help while the frame is present. A NEW tab on the ` +
    `same URL sometimes does work — the other extension re-injects when a login field ` +
    `is focused, so a fresh tab is clear until that happens (verified live, both ways).
` +
    `STILL WORKS on this tab: read_page, find, get_page_text, form_input and fill_form. ` +
    `Those use chrome.scripting, not the debugger, so they are unaffected — and fill_form ` +
    `falls back to untrusted pointer events internally, which handles most sites.
` +
    `For trusted input here, disable that extension for this site at chrome://extensions.`);
}

// Chrome emits the cross-extension refusal from MORE than debugger.attach — a
// sendCommand on an already-attached session fails with the same string once the
// other extension's iframe appears. Translating it only at the attach site meant
// the good explanation was skipped on the most common live path (measured: the
// raw string still reached the caller through cdpSend's recovery branch). Any
// site that can surface a chrome.debugger error routes through here.
async function asCrossExtensionError(tabId, err) {
  const m = (err && err.message) ? err.message : String(err);
  if (!/different extension/i.test(m)) return null;
  let where = '', url = '';
  try { const t = await chrome.tabs.get(tabId); url = String((t && t.url) || ''); where = ` url=${url.slice(0, 80)}`; } catch (e) {}
  const bad = await blockingExtensionFrames(tabId);
  // S6: the agent gets the explanation in its error, but the USER only ever sees
  // "it stopped working on this page". Persist the refusal for the side panel so
  // the conflict is attributed to Chrome's frame-tree rule and the other
  // extension, not to ChromeBridge.
  recordDebuggerBlock(tabId, url, bad);
  return crossExtensionAttachError(tabId, where, bad);
}

async function attachDebugger(tabId) {
  if (_attachedTabs.get(tabId)) return;
  try {
    await chrome.debugger.attach({ tabId }, "1.3");
  } catch (e) {
    // ORPHANED SESSION RECOVERY. Reloading the extension (constant during
    // development) or an MV3 service-worker restart leaves the PREVIOUS instance's
    // debugger session registered on every tab it had attached. The new instance
    // cannot attach over it.
    //
    // CAUTION: this branch used to also claim ownership of the error "Cannot access
    // a chrome-extension:// URL of different extension" on a plain https tab. That
    // attribution was WRONG and cost two debugging rounds. That error has a
    // completely different cause — another extension's injected iframe — handled
    // below, and it is NOT recoverable by detaching. Do not merge the two.
    //
    // The session belongs to the same extension ID, so THIS instance is allowed to
    // detach it. Do that and attach again.
    let recovered = false;
    try {
      await chrome.debugger.detach({ tabId });
      await chrome.debugger.attach({ tabId }, "1.3");
      recovered = true;
    } catch (e2) {}
    if (!recovered) {
      const m = e && e.message ? e.message : String(e);
      let where = '';
      try { const t = await chrome.tabs.get(tabId); where = ` url=${String(t && t.url).slice(0, 80)}`; } catch (e3) {}
      const xe = await asCrossExtensionError(tabId, e);
      if (xe) throw xe;
      throw new Error(`${m}  [debugger.attach tab=${tabId}${where}; detach+retry also failed — ` +
                      `this tab may hold a debugger session from a previous extension instance. ` +
                      `Open a new tab with tabs_create_mcp and retry there.]`);
    }
    _inputReady.delete(tabId);   // the new session starts without the CDP switches
  }
  _attachedTabs.set(tabId, true);
}

// EVERY CDP call goes through here. `_attachedTabs` is service-worker memory and
// Chrome can drop the real session without telling us — the user dismisses the
// yellow infobar, DevTools takes over, or the extension is reloaded while a tab is
// open. attachDebugger then early-returns on a map that lies, and every subsequent
// command throws "Debugger is not attached to the tab with id: N" — which is what
// happened on the very first live test after this round's reload. Same family as
// the _inputReady bug above: cached state trusted over reality. Recover once,
// silently, instead of surfacing an error the caller cannot act on.
async function cdpSend(tabId, method, params) {
  const label = (e) => {
    const m = e && e.message ? e.message : String(e);
    // NAME THE FAILING CALL. chrome.* rejections carry no stack through our
    // frames, so a bare message named neither the CDP method nor the tab and
    // cost several rounds of blind bisection to locate.
    const err = new Error(`${m}  [cdp ${method} tab=${tabId}]`);
    return err;
  };
  try {
    return await chrome.debugger.sendCommand({ tabId }, method, params);
  } catch (e) {
    // "Detached while handling command" is the SAME class as "not attached" and
    // was not matched here: the session dies mid-flight (another extension injects
    // an iframe, Chrome tears the target down) and the command is lost. Observed
    // live on a login page, where it surfaced raw with no recovery attempted. Retry
    // once through the same path; if re-attach is refused, the caller gets the
    // precise cross-extension explanation instead of this bare string.
    const xe0 = await asCrossExtensionError(tabId, e);
    if (xe0) throw xe0;
    if (!/not attached|detached while handling/i.test(String(e && e.message || e))) throw label(e);
    const first = e && e.message ? e.message : String(e);
    _attachedTabs.delete(tabId);
    _inputReady.delete(tabId);          // its CDP switches died with the session
    try {
      await attachDebugger(tabId);
      await ensureInputReady(tabId);
      return await chrome.debugger.sendCommand({ tabId }, method, params);
    } catch (e2) {
      // Report BOTH. Surfacing only the recovery error hid the real cause: the
      // original was "not attached", and the re-attach failure replaced it with an
      // unrelated-looking permission message.
      const xe2 = await asCrossExtensionError(tabId, e2);
      if (xe2) throw xe2;
      const m2 = e2 && e2.message ? e2.message : String(e2);
      throw new Error(`${first}  [cdp ${method} tab=${tabId}; re-attach also failed: ${m2}]`);
    }
  }
}

async function detachDebugger(tabId) {
  if (!_attachedTabs.get(tabId)) return;
  try { await chrome.debugger.detach({ tabId }); } catch (e) { /* already gone */ }
  _attachedTabs.delete(tabId);
  // CLEAR THE READINESS FLAG TOO. chrome.debugger.onDetach fires only for
  // EXTERNAL detaches (user cancels the infobar, DevTools takes over, tab
  // closes) — never when we detach ourselves. mcp_server sends detach_debugger
  // on every shutdown, which resets the target's CDP emulation state while this
  // set still claimed the tab was ready. On the next session ensureInputReady
  // early-returned, focus emulation was never re-applied, and trusted clicks
  // into the (normally backgrounded) agent tab were silently dropped again while
  // the tool reported success. That is fix #12 exactly, resurrected by one
  // missing line.
  _inputReady.delete(tabId);
}

async function detachAllDebuggers() {
  const ids = Array.from(_attachedTabs.keys());
  await Promise.all(ids.map(detachDebugger));
}

// NO STARTUP DEBUGGER SWEEP. A previous version swept chrome.debugger.getTargets()
// on service-worker start and detached everything already attached, to clear
// sessions orphaned by an extension reload. It was wrong twice over: detaching does
// NOT make a poisoned tab attachable again (measured — detach+attach still fails),
// and because the sweep is async it finished AFTER an in-flight op had attached and
// tore down that op's brand-new session. The symptom was a fresh tab reporting
// "Debugger is not attached" on its first Input command, i.e. the sweep broke the
// working case while failing to fix the broken one.
//
// A tab that held a session from a previous extension instance stays unusable for
// trusted input; attachDebugger detects that and says to open a new tab.

// User hit "Cancel" on the yellow bar, opened DevTools, or the tab closed.
// KEEP THE REASON. Chrome hands us exactly why the session ended — target_closed,
// canceled_by_user, replaced_with_devtools — and this listener discarded it, so
// "the session vanished seconds after a successful click, inside a live service
// worker" had no explanation available anywhere. sw_info reports it now.
let _lastDetach = null;
chrome.debugger.onDetach.addListener((source, reason) => {
  if (source.tabId !== undefined) {
    _lastDetach = { tabId: source.tabId, reason: String(reason), atSec: Math.round((Date.now() - _SW_BORN) / 1000) };
    _attachedTabs.delete(source.tabId);
    _inputReady.delete(source.tabId);
  }
});
chrome.tabs.onRemoved.addListener((tabId) => {
  _attachedTabs.delete(tabId);
  _inputReady.delete(tabId);
  _frameShells.delete(tabId);
  _netBuf.delete(tabId);
  _netOrigin.delete(tabId);
});

// Returns the viewport-relative center point of `selector` (CSS px).
function _rectForPage(selector) {
  const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
  const el = q(selector);
  if (!el) return null;
  // behavior:"instant" is LOAD-BEARING, not cosmetic. Sites that set CSS
  // `scroll-behavior: smooth` (Bootstrap docs, most doc sites) turn
  // scrollIntoView into an ANIMATION: the rect measured on the next line is the
  // pre-scroll one, so a trusted CDP click gets dispatched at coordinates the
  // element no longer occupies. Worse, Chrome throttles smooth-scroll animations
  // in NON-FOCUSED tabs — and the agent's tab is usually in the background — so
  // the scroll never happens at all and the click lands outside the viewport
  // entirely. Observed live: a button at y=2365 in a 1301px viewport stayed at
  // y=2365 (scrollY never left 0) and the click hit nothing.
  // "instant" overrides the CSS and scrolls synchronously.
  try { el.scrollIntoView({ block: "center", inline: "center", behavior: "instant" }); } catch (e) {
    try { el.scrollIntoView({ block: "center", inline: "center" }); } catch (e2) {}
  }
  const r = el.getBoundingClientRect();
  // Same-origin iframe content: the rect is relative to the FRAME's viewport,
  // but CDP Input.dispatchMouseEvent takes TOP-document CSS pixels — add the
  // accumulated frame offsets (incl. iframe border via clientLeft/Top).
  // SCALE-AWARE. Adding frameRect.left to an untransformed inner rect is only
  // correct when the iframe is unscaled. A `transform: scale(.5)` frame — mobile
  // preview panes, page-builder canvases, responsive-embed tricks — made every
  // coordinate inside it wrong by the scale factor while the tool reported
  // success: the same failure family as fixes #10/#11/#12. getBoundingClientRect
  // IS transformed; offsetWidth is not, so their ratio is the accumulated scale.
  let px = r.left, py = r.top, kx = 1, ky = 1;
  try {
    let w = el.ownerDocument ? el.ownerDocument.defaultView : null;
    while (w && w !== window && w.frameElement) {
      const fe = w.frameElement;
      const fr = fe.getBoundingClientRect();
      const ow = fe.offsetWidth || fr.width, oh = fe.offsetHeight || fr.height;
      const sx = ow ? fr.width / ow : 1, sy = oh ? fr.height / oh : 1;
      px = fr.left + (fe.clientLeft || 0) * sx + px * sx;
      py = fr.top + (fe.clientTop || 0) * sy + py * sy;
      kx *= sx; ky *= sy;
      w = w.parent;
    }
  } catch (e) {}
  // OCCLUSION PRE-FLIGHT. The listing's (occluded/blocked) tag is observation-time
  // and cannot protect action time: a consent modal, a toast or a sticky bar that
  // appears AFTER the read means the trusted click lands on whatever is now on
  // top — plausibly that overlay's own "Accept all" — and the tool reports it
  // clicked your element. Deciding this here, in the page, right after the scroll
  // and right before the coordinates are used, is the only moment it is true.
  //
  // Deliberately conservative: refuse ONLY when a different, painting,
  // pointer-events-accepting element is positively on top. An empty hit-stack
  // (point outside the viewport) or any uncertainty proceeds as before, so this
  // cannot invent failures on flows that work today.
  let blockedBy = '';
  try {
    const od = el.ownerDocument || document;
    const cpx = r.left + r.width / 2, cpy = r.top + r.height / 2;
    const stack = od.elementsFromPoint(cpx, cpy) || [];
    const up = (n) => n.parentElement || (n.getRootNode && n.getRootNode().host) || null;
    const rel = (a, b) => { let n = b; while (n) { if (n === a) return true; n = up(n); } return false; };
    for (const t of stack) {
      if (t === el || rel(el, t) || rel(t, el)) break;            // reached us: clear
      let cs2; try { cs2 = getComputedStyle(t); } catch (e2) { break; }
      if (cs2.pointerEvents === 'none') continue;                 // clicks pass through
      if (parseFloat(cs2.opacity || '1') === 0) continue;         // paints nothing
      // A control's OWN label sitting over it is the styled-input pattern, not an
      // obstruction — clicking the label operates the control. (Bootstrap's
      // opacity:0 checkbox lives exactly under its label.)
      if (t.tagName === 'LABEL' && (t.control === el || (el.id && t.getAttribute('for') === el.id))) break;
      blockedBy = t.tagName.toLowerCase() +
        ((t.innerText || '').trim() ? ' "' + (t.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 40) + '"' : '');
      break;
    }
  } catch (e) {}
  return {
    x: px + (r.width * kx) / 2, y: py + (r.height * ky) / 2,
    w: r.width * kx, h: r.height * ky,
    visible: r.width > 0 && r.height > 0,
    blockedBy,
  };
}

// Current top-document offset of a cross-origin frame, re-measured at ACTION time.
// Two bugs live here historically:
//   - Using the offset cached at collection time goes stale the moment the page
//     scrolls between read_page and the click.
//   - Re-matching the cached shell to fresh shells BY SIZE picks the wrong sibling
//     whenever two frames are the same size — which is the normal case for payment
//     forms (Stripe Elements ships expiry and CVC as identically-sized iframes), and
//     was WORSE than the stale cache because it broke even with zero scrolling.
// Match on src (identity), fall back to nearest-position, and only then to size.
async function frameOffsetNow(tabId, frameId) {
  const cached = (_frameShells.get(tabId) || new Map()).get(frameId);
  let fresh = [];
  try { fresh = await runInTab(tabId, _frameShellsPage) || []; } catch (e) {}
  if (!fresh.length) return cached || null;
  if (cached && cached.src) {
    const bySrc = fresh.filter(sh => sh.src && sh.src === cached.src);
    if (bySrc.length === 1) return { x: bySrc[0].x, y: bySrc[0].y };
    if (bySrc.length > 1) {
      // Same src more than once: the one nearest its last known position is ours.
      let best = bySrc[0], bd = Infinity;
      for (const sh of bySrc) {
        const d = Math.abs(sh.x - cached.x) + Math.abs(sh.y - cached.y);
        if (d < bd) { bd = d; best = sh; }
      }
      return { x: best.x, y: best.y };
    }
  }
  if (cached) {
    // No src match (src attr drifted). Position is a better discriminator than size
    // because scrolling moves every frame by the SAME delta, so relative order holds.
    let best = null, bd = Infinity;
    for (const sh of fresh) {
      const d = Math.abs(sh.w - cached.w) + Math.abs(sh.h - cached.h);
      const pd = Math.abs(sh.x - cached.x);   // x rarely changes on vertical scroll
      const score = d * 10 + pd;
      if (score < bd) { bd = score; best = sh; }
    }
    if (best) return { x: best.x, y: best.y };
  }
  return cached || null;
}

// Make a BACKGROUND tab accept trusted input WITHOUT touching the user's focus.
//
// Chrome drops CDP Input.dispatchMouseEvent when the target tab's RenderWidget is hidden
// — proven by instrumenting the page: a click at verified-correct coordinates produced
// ZERO events in a capturing listener while document.visibilityState was "hidden".
//
// The WRONG fix (briefly shipped, immediately reverted) was to activate the tab and focus
// its window. That works, and it is intolerable: it yanks the user out of whatever they
// are doing, every single click. The entire point of this project is to drive the browser
// while the user gets on with something else.
//
// The RIGHT fix is two CDP switches that make the renderer behave as focused and unthrottled
// while the tab stays exactly where it is, in the background:
//   Emulation.setFocusEmulationEnabled — the page believes it holds focus, so input is
//     accepted and :focus/focusin behave normally.
//   Page.setWebLifecycleState('active') — undoes background throttling/freezing, so timers,
//     rAF and (critically) smooth-scroll animations run.
// This is the same mechanism Playwright uses to drive many pages concurrently without
// activating any of them. Both are per-target and cost one round trip on attach.
const _inputReady = new Set();   // tabs whose CDP readiness switches are already set
// SERVICE-WORKER IDENTITY + BIRTH TIME. An MV3 worker is terminated aggressively,
// and when it goes every chrome.debugger session goes with it — which looks
// identical, from the maps, to Chrome having detached us. Both leave _attachedTabs
// empty, so the two causes were indistinguishable while debugging "one trusted
// click per tab". A fresh id here across two consecutive ops proves the worker
// restarted; a stable id proves it did not and the detach came from Chrome.
const _SW_ID = Math.random().toString(36).slice(2, 8);
const _SW_BORN = Date.now();
const swAge = () => `sw=${_SW_ID}+${Math.round((Date.now() - _SW_BORN) / 1000)}s`;
async function ensureInputReady(tabId) {
  if (_inputReady.has(tabId)) return;   // idempotent: these are per-target and sticky
  const dbg = { tabId };
  let _lastErr = '';
  let _focusOk = false;
  try {
    await chrome.debugger.sendCommand(dbg, "Emulation.setFocusEmulationEnabled", { enabled: true });
    _focusOk = true;
  } catch (e) { _lastErr = String(e && e.message || e).slice(0, 90); }
  // NO Page.enable. CDP *commands* do not require their domain to be enabled — only
  // EVENTS do — and enabling Page makes Chrome stream every Page.* event to this service
  // worker over the debugger channel. On a busy page that flood measurably slowed the
  // whole pipeline: a warm Page.captureScreenshot on a Wikipedia article took ~25s with
  // Page.enable in place. setWebLifecycleState works fine without it.
  let _lifecycleOk = false;
  try {
    await chrome.debugger.sendCommand(dbg, "Page.setWebLifecycleState", { state: "active" });
    _lifecycleOk = true;
  } catch (e) { _lastErr = String(e && e.message || e).slice(0, 90); }
  // Only remember success. Both commands were swallowed and the tab marked ready
  // regardless, so ONE transient failure (a command racing a cross-process
  // navigation, a target swap) permanently disabled the background-input fix for
  // that tab — every later click dropped silently and reported success. Retrying
  // costs one round trip; being wrong costs the whole mechanism.
  if (_focusOk || _lifecycleOk) _inputReady.add(tabId);
  // RETURN THE OUTCOME. Swallowing both failures is what let the fix-#12
  // regression hide, and it is also why a session that dies immediately after
  // attach looked like a healthy one until the first Input command failed.
  // Callers can now say what actually happened.
  return { focusOk: _focusOk, lifecycleOk: _lifecycleOk, err: _lastErr };
}

async function clickTrusted(tabId, selector, frameIdOverride = null) {
  // ATTACH FIRST, then measure. Chrome's "extension is debugging this browser"
  // infobar appears on attach and PUSHES THE PAGE CONTENT DOWN by ~32px.
  // If we read getBoundingClientRect before the bar appears, coordinates are
  // stale by the time we dispatch — for short elements (32px option rows) the
  // click lands ABOVE the target and hits empty space. This was the silent
  // failure mode behind Boxsy's combobox options never selecting.
  await attachDebugger(tabId);
  const _ready = await ensureInputReady(tabId);   // background tabs accept input; no focus stealing
  // Give the page one paint to settle after the infobar shifts the viewport.
  await new Promise(r => setTimeout(r, 50));
  const rt = (frameIdOverride !== null && frameIdOverride !== undefined)
    ? { frameId: frameIdOverride, selector }
    : resolveFrameSelector(selector);
  const rect = await runInTab(tabId, _rectForPage, [rt.selector], rt.frameId);
  if (!rect) return { ok: false, msg: `Element ${selector} not found.` };
  if (!rect.visible) return { ok: false, msg: `Element ${selector} is not visible.` };
  if (rect.blockedBy) {
    return { ok: false, msg:
      `Element ${selector} is COVERED by ${rect.blockedBy} — did not click. Something is on top of ` +
      `it at the click point (a modal, consent layer, toast or sticky bar that appeared after you ` +
      `last read the page). Re-observe: the blocker is probably what you need to handle first. ` +
      `Nothing was clicked, so no action was taken on your behalf.` };
  }
  const dbg = { tabId };
  let x = rect.x, y = rect.y;
  // Cross-origin frame: the rect is frame-relative; CDP dispatches in TOP
  // document coordinates — add the frame shell's offset captured at the last
  // collection.
  if (rt.frameId !== null) {
    const off = await frameOffsetNow(tabId, rt.frameId);
    if (!off) {
      // NO GUESS. Without the shell offset these are FRAME-LOCAL coordinates, and
      // dispatching them as top-document ones clicks an arbitrary spot on the host
      // page while reporting success — the fix-#10 family. The cache is
      // service-worker memory and is wiped by any MV3 eviction, so this is a
      // routine state, not an exotic one.
      return { ok: false, msg:
        `Element ${selector} is inside a cross-origin frame whose position is no longer known ` +
        `(the extension's frame cache was cleared). Nothing was clicked. Call read_page on this ` +
        `tab to re-measure the frame, then retry.` };
    }
    x += off.x; y += off.y;
  }
  // CDP Input.dispatchMouseEvent takes viewport-relative CSS pixels.
  // If the session is already gone by here, say what the readiness probes saw —
  // they are the first CDP round trips after attach and therefore the earliest
  // evidence of a session that never really lived.
  try {
    await cdpSend(tabId, "Input.dispatchMouseEvent",
      { type: "mouseMoved",   x, y, button: "none" });
  } catch (e) {
    throw new Error(`${e && e.message ? e.message : e}  [inputReady focus=${_ready && _ready.focusOk} ` +
                    `lifecycle=${_ready && _ready.lifecycleOk}` +
                    `${_ready && _ready.err ? ' firstErr=' + _ready.err : ''}]`);
  }
  await cdpSend(tabId, "Input.dispatchMouseEvent",
    { type: "mousePressed", x, y, button: "left", clickCount: 1, buttons: 1 });
  await cdpSend(tabId, "Input.dispatchMouseEvent",
    { type: "mouseReleased", x, y, button: "left", clickCount: 1, buttons: 0 });
  return { ok: true, msg: `Clicked ${selector} via TRUSTED input at (${Math.round(x)},${Math.round(y)}).` };
}

// --------------------- MCP `computer` op (CDP mouse/keyboard) ---------------
// Coordinate-level trusted input, Claude-in-Chrome style. Reuses the SAME
// attach-then-settle ordering as clickTrusted (fix #10): the debugger infobar
// pushes content down ~32px, so attach FIRST, wait a paint, THEN measure.
const _CDP_MOD_BITS = { alt: 1, ctrl: 2, control: 2, meta: 4, cmd: 4, win: 4, windows: 4, shift: 8 };

function _modBits(modifiers) {
  let bits = 0;
  for (const m of String(modifiers || "").toLowerCase().split("+")) {
    const b = _CDP_MOD_BITS[m.trim()];
    if (b) bits |= b;
  }
  return bits;
}

const _KEYMAP = {
  enter: { key: "Enter", code: "Enter", vk: 13, text: "\r" },
  return: { key: "Enter", code: "Enter", vk: 13, text: "\r" },
  tab: { key: "Tab", code: "Tab", vk: 9, text: "\t" },
  backspace: { key: "Backspace", code: "Backspace", vk: 8 },
  delete: { key: "Delete", code: "Delete", vk: 46 },
  del: { key: "Delete", code: "Delete", vk: 46 },
  escape: { key: "Escape", code: "Escape", vk: 27 },
  esc: { key: "Escape", code: "Escape", vk: 27 },
  space: { key: " ", code: "Space", vk: 32, text: " " },
  up: { key: "ArrowUp", code: "ArrowUp", vk: 38 },
  arrowup: { key: "ArrowUp", code: "ArrowUp", vk: 38 },
  down: { key: "ArrowDown", code: "ArrowDown", vk: 40 },
  arrowdown: { key: "ArrowDown", code: "ArrowDown", vk: 40 },
  left: { key: "ArrowLeft", code: "ArrowLeft", vk: 37 },
  arrowleft: { key: "ArrowLeft", code: "ArrowLeft", vk: 37 },
  right: { key: "ArrowRight", code: "ArrowRight", vk: 39 },
  arrowright: { key: "ArrowRight", code: "ArrowRight", vk: 39 },
  home: { key: "Home", code: "Home", vk: 36 },
  end: { key: "End", code: "End", vk: 35 },
  pageup: { key: "PageUp", code: "PageUp", vk: 33 },
  pagedown: { key: "PageDown", code: "PageDown", vk: 34 },
  insert: { key: "Insert", code: "Insert", vk: 45 },
};
for (let i = 1; i <= 12; i++) _KEYMAP[`f${i}`] = { key: `F${i}`, code: `F${i}`, vk: 111 + i };

function _keyInfo(name) {
  const n = String(name || "").trim();
  const mapped = _KEYMAP[n.toLowerCase()];
  if (mapped) return mapped;
  if (n.length === 1) {
    const ch = n;
    const upper = ch.toUpperCase();
    // PUNCTUATION NEEDS A REAL VK. `ch.toUpperCase().charCodeAt(0)` is correct for
    // letters and digits only by coincidence (VK_A === 'A'). For punctuation it
    // produces the ASCII code, which COLLIDES with control keys: "." -> 46, which
    // is VK_DELETE (the real keyCode is 190), and "-" -> 45 = VK_INSERT. A grid
    // that branches on legacy e.keyCode (older ag-Grid/Handsontable bind 46 to
    // delete-row) received a Delete when the agent typed a full stop — a
    // destructive wrong action, reported as success.
    const P = { '.': [190, 'Period'], ',': [188, 'Comma'], '-': [189, 'Minus'], '=': [187, 'Equal'],
                ';': [186, 'Semicolon'], "'": [222, 'Quote'], '/': [191, 'Slash'], '\\': [220, 'Backslash'],
                '[': [219, 'BracketLeft'], ']': [221, 'BracketRight'], '`': [192, 'Backquote'], ' ': [32, 'Space'] };
    // Shifted US-layout characters map to the same physical key as their base.
    const SH = { '!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6', '&': '7', '*': '8',
                 '(': '9', ')': '0', '_': '-', '+': '=', '{': '[', '}': ']', '|': '\\', ':': ';',
                 '"': "'", '<': ',', '>': '.', '?': '/', '~': '`' };
    if (P[ch]) return { key: ch, code: P[ch][1], vk: P[ch][0], text: ch };
    if (SH[ch]) {
      const base = SH[ch];
      const bp = P[base];
      return { key: ch, code: bp ? bp[1] : `Digit${base}`, vk: bp ? bp[0] : base.charCodeAt(0), text: ch };
    }
    const code = /[a-z]/i.test(ch) ? `Key${upper}` : (/[0-9]/.test(ch) ? `Digit${ch}` : "");
    return { key: ch, code, vk: upper.charCodeAt(0), text: ch };
  }
  // Unknown named key — pass through and hope the page handles `key` alone.
  return { key: n, code: n, vk: 0 };
}

// Editing commands that pages can't see as raw key events when the browser
// consumes them — mirror Playwright/puppeteer by attaching CDP `commands`.
const _KEY_COMMANDS = { "ctrl+a": ["selectAll"], "ctrl+c": ["copy"], "ctrl+v": ["paste"], "ctrl+x": ["cut"], "ctrl+z": ["undo"], "ctrl+y": ["redo"], "ctrl+shift+z": ["redo"], "cmd+a": ["selectAll"], "cmd+c": ["copy"], "cmd+v": ["paste"], "cmd+x": ["cut"], "cmd+z": ["undo"] };

// Press one chord like "Enter" or "ctrl+shift+t" (extra modifier bits OR-ed in).
async function _cdpPressChord(tabId, chord, extraBits) {
  const parts = String(chord).split("+").map(s => s.trim()).filter(Boolean);
  const keyName = parts[parts.length - 1];
  let bits = extraBits | _modBits(parts.slice(0, -1).join("+"));
  const info = _keyInfo(keyName);
  const dbg = { tabId };
  const commands = _KEY_COMMANDS[String(chord).toLowerCase().replace(/\s+/g, "")] || [];
  const hasNonShiftMod = (bits & ~8) !== 0;
  const down = {
    type: (info.text && !hasNonShiftMod) ? "keyDown" : "rawKeyDown",
    modifiers: bits, key: info.key, code: info.code,
    windowsVirtualKeyCode: info.vk, nativeVirtualKeyCode: info.vk,
  };
  if (info.text && !hasNonShiftMod) down.text = bits & 8 ? info.text.toUpperCase() : info.text;
  if (commands.length) down.commands = commands;
  await cdpSend(tabId, "Input.dispatchKeyEvent", down);
  await cdpSend(tabId, "Input.dispatchKeyEvent", {
    type: "keyUp", modifiers: bits, key: info.key, code: info.code,
    windowsVirtualKeyCode: info.vk, nativeVirtualKeyCode: info.vk,
  });
}

// Resolve the action point: explicit coordinate (top-document CSS px) or a
// selector's center (with cross-origin frame shell offsets, like clickTrusted).
async function _computerPoint(tabId, params) {
  if (Array.isArray(params.coordinate) && params.coordinate.length === 2) {
    return { x: +params.coordinate[0], y: +params.coordinate[1] };
  }
  if (params.selector) {
    const rt = resolveFrameSelector(params.selector);
    const rect = await runInTab(tabId, _rectForPage, [rt.selector], rt.frameId);
    if (!rect) throw new Error(`element ${params.selector} not found`);
    if (!rect.visible) throw new Error(`element ${params.selector} is not visible`);
    let x = rect.x, y = rect.y;
    if (rt.frameId !== null) {
      // Same re-measure as clickTrusted — `computer(left_click, ref="f3:7")` was
      // still using the collection-time cache, so after any scroll it landed at the
      // frame's old position while the `click` op landed correctly.
      const off = await frameOffsetNow(tabId, rt.frameId);
      if (off) { x += off.x; y += off.y; }
    }
    return { x, y };
  }
  // default: viewport center (used by scroll without coordinates)
  const vp = await runInTab(tabId, () => ({ w: innerWidth, h: innerHeight }));
  return { x: (vp && vp.w || 800) / 2, y: (vp && vp.h || 600) / 2 };
}

async function computerOp(t, params) {
  const action = String(params.action || "");
  const dbg = { tabId: t.id };

  if (action === "scroll_to") {
    if (!params.selector) throw new Error("scroll_to requires a ref");
    const rt = resolveFrameSelector(params.selector);
    const rect = await runInTab(t.id, _rectForPage, [rt.selector], rt.frameId); // scrollIntoViews
    if (!rect) throw new Error(`element ${params.selector} not found`);
    return `Scrolled ${params.selector} into view (center at ${Math.round(rect.x)},${Math.round(rect.y)}).`;
  }

  // Everything below is trusted CDP input. Fix #10: attach FIRST, settle, then measure.
  // Whether the debugger was ALREADY attached matters for COORDINATE clicks: the
  // "is debugging" infobar appears on attach and pushes page content down ~32px.
  // Selector-based actions re-measure after attaching so they're safe, but a
  // coordinate the model read off a screenshot taken BEFORE the first attach now
  // refers to a layout that has since shifted. We can't retroactively correct a
  // number we didn't produce, so say so instead of silently clicking the wrong row.
  const _wasAttached = _attachedTabs.get(t.id) === true;
  await attachDebugger(t.id);
  await ensureInputReady(t.id);   // background tabs accept input; no focus stealing
  await new Promise(r => setTimeout(r, 50));
  const _actNote = "";
  const _shiftWarn = (!_wasAttached && !params.selector &&
                      (Array.isArray(params.coordinate) || Array.isArray(params.start_coordinate)))
    ? " NOTE: the debugger infobar was attached by this call, which shifts page content down ~32px." +
      " If this coordinate came from a screenshot taken earlier, it may now be off by roughly that much —" +
      " re-screenshot and re-click if the result looks wrong, or use a ref instead (refs are re-measured after attach)."
    : "";
  const bits = _modBits(params.modifiers);

  if (action === "key") {
    const seq = String(params.text || "").trim().split(/\s+/).filter(Boolean);
    if (!seq.length) throw new Error('key requires text, e.g. "Enter" or "ctrl+a"');
    const repeat = Math.min(Math.max(+params.repeat || 1, 1), 100);
    for (let i = 0; i < repeat; i++) {
      for (const chord of seq) await _cdpPressChord(t.id, chord, bits);
    }
    return `Pressed ${seq.join(" ")}${repeat > 1 ? ` x${repeat}` : ""}.`;
  }

  if (action === "type") {
    if (params.selector) {
      // focus the target first so the text lands in the right field
      const rt = resolveFrameSelector(params.selector);
      const focused = await runInTab(t.id, (sel) => {
        const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
        const el = q(sel);
        if (!el) return false;
        try { el.scrollIntoView({ block: "center", behavior: "instant" }); } catch (e) {}
        try { el.focus({ preventScroll: true }); } catch (e) {}
        return true;
      }, [rt.selector], rt.frameId);
      // FAIL LOUDLY when the ref doesn't resolve. This used to focus best-effort and
      // then insert the text ANYWAY — into whatever happened to be focused, usually
      // <body>, where it goes nowhere — while returning "Typed ... into the focused
      // element." Found while diagnosing something else: on a page whose mmids had not
      // been injected, `computer(type, ref=ref_13)` reported success having typed into
      // nothing. Every other ref-taking action already errors on an unresolvable ref.
      if (!focused) {
        throw new Error(
          `element ${params.selector} not found, so nothing was typed. The ref is stale or ` +
          `this page has not been observed yet — call read_page (or find) first to get ` +
          `current refs.`
        );
      }
    }
    await cdpSend(t.id, "Input.insertText", { text: String(params.text || "") });
    // This echo is the only feedback `type` gives, so an unmarked cut cannot be
    // told apart from the FIELD having truncated the input. Two live agents hit
    // exactly that: 119 chars sent, 80 echoed, cut mid-word, no signal.
    const _t = String(params.text || "");
    const _echo = _t.length <= 80 ? _t
      : _t.slice(0, 80) + "…(+" + (_t.length - 80) + ")";
    return `Typed ${JSON.stringify(_echo)} into the focused element.`;
  }

  if (action === "scroll") {
    const pt = await _computerPoint(t.id, params);
    const ticks = Math.min(Math.max(+params.scroll_amount || 3, 1), 10);
    const dirMap = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
    const d = dirMap[String(params.scroll_direction || "down")];
    if (!d) throw new Error(`invalid scroll_direction ${params.scroll_direction}`);
    await cdpSend(t.id, "Input.dispatchMouseEvent", {
      type: "mouseWheel", x: pt.x, y: pt.y,
      deltaX: d[0] * ticks * 120, deltaY: d[1] * ticks * 120,
    });
    return `Scrolled ${params.scroll_direction || "down"} ${ticks} tick(s) at (${Math.round(pt.x)},${Math.round(pt.y)}).${_shiftWarn}`;
  }

  if (action === "hover") {
    const pt = await _computerPoint(t.id, params);
    await cdpSend(t.id, "Input.dispatchMouseEvent",
      { type: "mouseMoved", x: pt.x, y: pt.y, button: "none", modifiers: bits });
    return `Hovering at (${Math.round(pt.x)},${Math.round(pt.y)}).${_shiftWarn}`;
  }

  if (action === "left_click_drag") {
    if (!Array.isArray(params.start_coordinate) || !Array.isArray(params.coordinate)) {
      throw new Error("left_click_drag requires start_coordinate and coordinate");
    }
    const [sx, sy] = params.start_coordinate.map(Number);
    const [ex, ey] = params.coordinate.map(Number);
    await cdpSend(t.id, "Input.dispatchMouseEvent",
      { type: "mouseMoved", x: sx, y: sy, button: "none", modifiers: bits });
    await cdpSend(t.id, "Input.dispatchMouseEvent",
      { type: "mousePressed", x: sx, y: sy, button: "left", clickCount: 1, buttons: 1, modifiers: bits });
    const steps = 12;
    for (let i = 1; i <= steps; i++) {
      await cdpSend(t.id, "Input.dispatchMouseEvent", {
        type: "mouseMoved", x: sx + (ex - sx) * i / steps, y: sy + (ey - sy) * i / steps,
        button: "left", buttons: 1, modifiers: bits,
      });
    }
    await cdpSend(t.id, "Input.dispatchMouseEvent",
      { type: "mouseReleased", x: ex, y: ey, button: "left", clickCount: 1, buttons: 0, modifiers: bits });
    return `Dragged from (${sx},${sy}) to (${ex},${ey}).${_shiftWarn}`;
  }

  const clickKinds = { left_click: ["left", 1], right_click: ["right", 1], double_click: ["left", 2], triple_click: ["left", 3] };
  if (clickKinds[action]) {
    const [button, count] = clickKinds[action];
    const pt = await _computerPoint(t.id, params);
    await cdpSend(t.id, "Input.dispatchMouseEvent",
      { type: "mouseMoved", x: pt.x, y: pt.y, button: "none", modifiers: bits });
    for (let c = 1; c <= count; c++) {
      await cdpSend(t.id, "Input.dispatchMouseEvent",
        { type: "mousePressed", x: pt.x, y: pt.y, button, clickCount: c, buttons: button === "left" ? 1 : 2, modifiers: bits });
      await cdpSend(t.id, "Input.dispatchMouseEvent",
        { type: "mouseReleased", x: pt.x, y: pt.y, button, clickCount: c, buttons: 0, modifiers: bits });
    }
    return `${action} at (${Math.round(pt.x)},${Math.round(pt.y)})${params.selector ? ` on ${params.selector}` : ""}.${_actNote}${_shiftWarn}`;
  }

  throw new Error(`computer: unknown action ${action}`);
}

// --------------------- javascript_exec (CDP Runtime.evaluate) ---------------
// DevTools-console semantics: replMode gives last-expression results and
// tolerates redeclaration; awaitPromise resolves top-level await; and unlike
// MAIN-world `new Function`, CDP evaluation is NOT blocked by the page's CSP.
async function evalInTab(tabId, code) {
  await attachDebugger(tabId);
  const res = await cdpSend(tabId, "Runtime.evaluate", {
    expression: String(code ?? ""),
    replMode: true,
    awaitPromise: true,
    returnByValue: true,
    userGesture: true,
    timeout: 15000,
  });
  if (res && res.exceptionDetails) {
    const ex = res.exceptionDetails;
    const desc = (ex.exception && (ex.exception.description || ex.exception.value)) || ex.text || "evaluation error";
    return { ok: false, error: String(desc).slice(0, 4000) };
  }
  const rv = (res && res.result) || {};
  if (rv.type === "undefined") return { ok: true, result: "undefined" };
  if ("value" in rv) return { ok: true, result: rv.value };
  return { ok: true, result: rv.description || `[${rv.type}]` };
}

// --------------------- network capture (read_network_requests) --------------
// chrome.webRequest listeners buffer request metadata per tab. Listeners are
// registered at SW top level so they survive service-worker respawns (the
// buffer itself does not — best-effort, like Claude-in-Chrome's).
const _netBuf = new Map();    // tabId -> [{url, method, type, statusCode, ...}]
const _netOrigin = new Map(); // tabId -> origin of the current main document
const _NET_CAP = 500;

function _netPush(tabId, entry) {
  if (tabId === undefined || tabId < 0) return;
  let arr = _netBuf.get(tabId);
  if (!arr) { arr = []; _netBuf.set(tabId, arr); }
  arr.push(entry);
  if (arr.length > _NET_CAP) arr.splice(0, arr.length - _NET_CAP);
}

// IN-FLIGHT requests, per tab. The buffer above records only what has FINISHED,
// so nothing in the system could tell that a page was still fetching. That blind
// spot produced four separate live-agent defects: a listing whose x-coordinates
// were all 116px stale because the hero image had not loaded and the layout was
// about to reflow; "Complete visible text" emitted over a spinner; a Wolfram pod
// that streamed in AFTER the read and so simply did not exist in it; and phantom
// refs from lazy-load placeholders that were replaced seconds later. All four
// reported confidently. document.readyState cannot see any of them — it goes
// 'complete' while XHR-driven content is still arriving.
const _netPending = new Map();   // tabId -> Map(requestId -> resourceType)

// Page-side half of the readiness check. Deliberately cheap — it runs on every
// observation — and deliberately structural: aria-busy and role=progressbar are
// the ARIA-standard "this region is updating" signals, so no site-specific
// spinner-class list is involved. Images are counted only when they occupy real
// space, because those are the ones whose load will REFLOW the page and
// invalidate every box() we are about to print.
// SHADOW-AWARE QUERY FOR THE STATE PROBES. `document.querySelectorAll` stops at
// every shadow boundary, so on a web-component app (Lit/Polymer/Shoelace/UI5/LWC)
// a spinner, an aria-busy region, or a whole <sl-dialog> simply does not exist as
// far as these probes are concerned. Proven with a fixture: a visible
// role=progressbar plus an aria-busy region inside one shadow root produced
// {prog: 0, busy: 0} and a "settled" verdict.
// The collector was fixed for this in CLAUDE.md #9 and the readiness probe
// reintroduced it in #15 — same bug, third and fourth homes. Bounded depth so the
// cost stays flat on deeply nested component trees.
function _deepAll(sel, root, depth) {
  const acc = [];
  const visit = (r, d) => {
    if (d > 6) return;
    try { r.querySelectorAll(sel).forEach((e) => acc.push(e)); } catch (e) {}
    try { r.querySelectorAll('*').forEach((e) => { if (e.shadowRoot) visit(e.shadowRoot, d + 1); }); }
    catch (e) {}
    // SAME-ORIGIN FRAMES TOO. A shadow root and a frame are both subtrees the page
    // renders and that `querySelectorAll` cannot see into; descending into one and
    // not the other is an arbitrary line. It made the readiness probe report
    // "settled" while a frame was still spinning — the #15 defect (a mid-load and
    // a settled observation reported with identical confidence) one level down,
    // and the FOURTH home for the scan-blindness class after #25 fixed it for
    // shadow roots. Cross-origin `contentDocument` throws and is skipped: that
    // frame's content is unknowable from here by design, not by omission.
    try {
      r.querySelectorAll('iframe,frame').forEach((f) => {
        let fd = null;
        try { fd = f.contentDocument; } catch (e) { return; }
        if (fd) visit(fd, d + 1);
      });
    } catch (e) {}
  };
  visit(root || document, depth || 0);
  return acc;
}

// A rect in TOP-document coordinates. `getBoundingClientRect` is relative to the
// element's OWN frame viewport, so once `_deepAll` started crossing frames the
// viewport filters below were comparing frame-local coordinates against the top
// window's height — a spinner at frame-y=50 inside a frame scrolled far off
// screen would have counted forever, which is the always-on-warning failure #15
// exists to prevent. Identical to getBoundingClientRect for a top-document
// element (the loop does not run), so nothing that worked before changes.
function _topRectFor(el) {
  const r = el.getBoundingClientRect();
  let x = r.left, y = r.top;
  try {
    let w = el.ownerDocument && el.ownerDocument.defaultView;
    while (w && w !== window && w.frameElement) {
      const fe = w.frameElement;
      const fr = fe.getBoundingClientRect();
      x += fr.left + (fe.clientLeft || 0);
      y += fr.top + (fe.clientTop || 0);
      w = w.parent;
    }
  } catch (e) {}
  return { left: x, top: y, right: x + r.width, bottom: y + r.height,
           width: r.width, height: r.height };
}

function _readinessPage() {
  // PAGE-CONTEXT COPIES. THIS FUNCTION IS INJECTED ALONE. `runInTab` hands it to
  // `chrome.scripting.executeScript({func})`, which stringifies THIS FUNCTION AND
  // NOTHING ELSE — so a call to a top-level sibling like `_deepAll` or
  // `_topRectFor` is a free identifier that does not exist in the page. Every such
  // call threw ReferenceError, each one swallowed by the try/catch around it, and
  // `imgs`/`busy`/`prog` stayed 0 forever. Confirmed in the page context:
  //     deepAll_type: "undefined"   topRectFor_type: "undefined"
  //     busy_error: "ReferenceError: _deepAll is not defined"  -> busy_result: 0
  // while the page plainly held one aria-busy region and one visible progressbar.
  // A read_page on that page emitted NO readiness banner.
  //
  // So the three DECLARATIVE signals — the page stating it is busy — were dead,
  // leaving only document.readyState and the service-worker-side network count.
  // A false "settled" is the worst direction this probe can fail in: the agent
  // reads mid-render and concludes something is absent.
  //
  // CLAUDE.md #25 documents this exact trap ("_deepAll extracted alone throws,
  // every try/catch swallows it, and the readiness probe silently reports
  // settled"), and the codebase already carries the correct pattern at the
  // `dup:deepall` site — a page-context copy. The readiness probe never got one.
  // Worse, tools/test_readiness.py PREPENDED both helpers before injecting, so the
  // suite tested an environment production never has and stayed green at 100%. It
  // now injects this function alone, exactly as runInTab does.
  //
  // Keep these as INNER CLOSURES. Anything this function needs must live inside it.
  const _deepAll = (sel, root, depth) => {
    const acc = [];
    const visit = (r, d) => {
      if (d > 6) return;
      try { r.querySelectorAll(sel).forEach((e) => acc.push(e)); } catch (e) {}
      try { r.querySelectorAll('*').forEach((e) => { if (e.shadowRoot) visit(e.shadowRoot, d + 1); }); }
      catch (e) {}
      try {
        r.querySelectorAll('iframe,frame').forEach((f) => {
          let fd = null;
          try { fd = f.contentDocument; } catch (e) { return; }
          if (fd) visit(fd, d + 1);
        });
      } catch (e) {}
    };
    visit(root || document, depth || 0);
    return acc;
  };
  const _topRectFor = (el) => {
    const r = el.getBoundingClientRect();
    let x = r.left, y = r.top;
    try {
      let w = el.ownerDocument && el.ownerDocument.defaultView;
      while (w && w !== window && w.frameElement) {
        const fe = w.frameElement;
        const fr = fe.getBoundingClientRect();
        x += fr.left + (fe.clientLeft || 0);
        y += fr.top + (fe.clientTop || 0);
        w = w.parent;
      }
    } catch (e) {}
    return { left: x, top: y, right: x + r.width, bottom: y + r.height,
             width: r.width, height: r.height };
  };
  const o = { ready: document.readyState, imgs: 0, busy: 0, prog: 0 };
  try {
    // NEAR THE VIEWPORT ONLY. A lazy image below the fold has complete === false
    // indefinitely — it has not started loading and will not until it is scrolled
    // to — so counting every unloaded image pinned BBC at "14 images still
    // loading" forever, on a page that was completely settled. A permanently-on
    // warning is worse than none: it trains the reader to ignore it. The set that
    // matters is the one that will REFLOW what we are about to print, i.e. images
    // in or just outside the viewport. The margin covers an image straddling the
    // fold whose load still pushes visible content down.
    const vh = window.innerHeight || document.documentElement.clientHeight || 0;
    const vw = window.innerWidth || document.documentElement.clientWidth || 0;
    const M = 200;
    for (const im of _deepAll('img')) {
      if (im.complete) continue;
      const r = _topRectFor(im);
      if (r.width <= 8 || r.height <= 8) continue;
      if (r.bottom < -M || r.top > vh + M || r.right < 0 || r.left > vw) continue;
      o.imgs++;
    }
  } catch (e) {}
  try { o.busy = _deepAll('[aria-busy="true"]').length; } catch (e) {}
  try {
    // Re-derived HERE on purpose: the image probe's vh/vw are const-scoped inside
    // its own try block, so referencing them from this one throws a ReferenceError
    // that the inner catch swallows — turning every progressbar into "not visible"
    // and silently deleting the signal. Caught by running it, not by node --check.
    const pvh = window.innerHeight || document.documentElement.clientHeight || 0;
    const pvw = window.innerWidth || document.documentElement.clientWidth || 0;
    o.prog = _deepAll('[role="progressbar"],progress').filter((n) => {
      try {
        const r = _topRectFor(n);
        if (r.width <= 1 || r.height <= 1) return false;
        // Off-viewport indicators are not evidence THIS view is unsettled.
        // Unbounded, a parked <progress> pinned the banner on permanently,
        // which is the 'always-on warning trains the reader to ignore it'
        // failure #15 already fixed for lazy images.
        if (r.bottom < -200 || r.top > pvh + 200 || r.right < 0 || r.left > pvw) return false;
        // opacity is NOT part of checkVisibility()'s default contract, and idle
        // Material progress bars sit at opacity:0 rather than display:none —
        // so this counted two invisible bars forever and pinned the banner on.
        try { if (parseFloat(getComputedStyle(n).opacity || "1") < 0.05) return false; } catch (e) {}
        return !n.checkVisibility ||
               n.checkVisibility({ opacityProperty: true, visibilityProperty: true });
      } catch (e) { return false; }
    }).length;
  } catch (e) {}
  return o;
}

// Returns '' when the page is settled, or a banner naming exactly what is still
// moving. Stated as one line at the TOP of an observation, because it changes how
// everything below should be read — coordinates, absences and refs alike.
// WebMCP probe result, cached per tab+URL so a read_page on a page already
// probed pays nothing. Keyed by URL because a navigation replaces the document
// and therefore the registered toolset; the `toolchange` event can also change it
// mid-page, which is why page_tools always re-reads and only this NOTICE is
// cached.
const _webmcpSeen = new Map();   // tabId -> { url, n }
async function webmcpNote(tabId) {
  let url = '';
  try { url = (await chrome.tabs.get(tabId)).url || ''; } catch (e) {}
  const hit = _webmcpSeen.get(tabId);
  let n = (hit && hit.url === url) ? hit.n : null;
  if (n === null) {
    n = 0;
    try {
      const r = await runInTab(tabId, _pageToolsPage, []);
      if (r && r.supported) n = (r.tools || []).length;
    } catch (e) {}
    _webmcpSeen.set(tabId, { url, n });
  }
  if (!n) return '';
  return `*** THIS PAGE DECLARES ${n} AGENT TOOL(S) (WebMCP). The site describes these ` +
         `capabilities itself, with names and JSON Schemas — prefer them over driving the UI. ` +
         `Read them with page_tools, run one with call_page_tool. ***\n`;
}

async function readinessNote(tabId) {
  let r = null;
  try { r = await runInTab(tabId, _readinessPage); } catch (e) {}
  const pend = _netPending.get(tabId);
  // Ignore long-lived streams: an open EventSource/WebSocket-ish fetch would
  // otherwise mark a finished page as permanently loading.
  let net = 0;
  if (pend) for (const t of pend.values()) if (t !== 'websocket' && t !== 'media') net++;
  if (!r) return '';
  const bits = [];
  if (r.ready !== 'complete') bits.push(`document.readyState="${r.ready}"`);
  if (r.imgs) bits.push(`${r.imgs} image(s) still loading`);
  if (net) bits.push(`${net} network request(s) in flight`);
  if (r.prog) bits.push(`${r.prog} progress indicator(s) visible`);
  if (r.busy) bits.push(`${r.busy} region(s) marked aria-busy`);
  if (!bits.length) return '';
  // Says "any coordinate" rather than "box() coordinates": box() is opt-in now
  // (`geometry=true`), so naming it would describe a field most reads do not
  // contain, while the warning still applies to a screenshot coordinate or one
  // carried from an earlier geometry read.
  return `*** PAGE IS STILL SETTLING (${bits.join('; ')}). Content may still be arriving, ` +
         `and any coordinate may shift as it does — re-observe before trusting one, ` +
         `and do NOT conclude something is absent from this read alone. Refs are re-measured at ` +
         `click time, so acting BY REF is safe. ***\n`;
}

function _pendDrop(tabId, requestId) {
  const m = _netPending.get(tabId);
  if (m) { m.delete(requestId); if (!m.size) _netPending.delete(tabId); }
}

// SEPARATE try. Registering this inside the block below put it AHEAD of the
// onCompleted/onErrorOccurred registrations, so anything that made it throw took
// the whole network buffer down with it — a readiness nicety disabling a shipped
// feature. Caught by test_ops, which mocks only the listeners it needs.
try {
  chrome.webRequest.onBeforeRequest.addListener((d) => {
    if (d.tabId === undefined || d.tabId < 0) return;
    let m = _netPending.get(d.tabId);
    if (!m) { m = new Map(); _netPending.set(d.tabId, m); }
    m.set(d.requestId, d.type);
    // Never let a dropped/aborted request pin a tab as "loading" forever.
    setTimeout(() => _pendDrop(d.tabId, d.requestId), 15000);
  }, { urls: ["<all_urls>"] });
} catch (e) {}

try {
  chrome.webRequest.onCompleted.addListener((d) => {
    _pendDrop(d.tabId, d.requestId);
    _netPush(d.tabId, { url: d.url, method: d.method, type: d.type, statusCode: d.statusCode, fromCache: !!d.fromCache, ts: d.timeStamp });
  }, { urls: ["<all_urls>"] });
  chrome.webRequest.onErrorOccurred.addListener((d) => {
    _pendDrop(d.tabId, d.requestId);
    _netPush(d.tabId, { url: d.url, method: d.method, type: d.type, error: d.error, ts: d.timeStamp });
  }, { urls: ["<all_urls>"] });
  // Clear the buffer when the tab's main document moves to a different origin
  // (same contract as Claude-in-Chrome's read_network_requests).
  chrome.webNavigation.onCommitted.addListener((d) => {
    if (d.frameId !== 0) return;
    let origin = "";
    try { origin = new URL(d.url).origin; } catch (e) {}
    if (_netOrigin.get(d.tabId) !== origin) {
      _netBuf.delete(d.tabId);
      _netOrigin.set(d.tabId, origin);
    }
  });
} catch (e) { /* webRequest unavailable — read_network_requests will error */ }

// Focus + clear the field, then insert text via CDP so it's trusted (isTrusted=true).
// --------------------- combobox / native-select handling ---------------
// fill_form treats `<button role="combobox">` and native `<select>` as
// dropdowns, not text inputs. Setting .value on a button silently fails
// (we observed this hard on Boxsy: Investor Type / Status / Focus Areas /
// Regions / Stages / Decision Time are all Radix Select triggers — typing
// into them sets nothing, so the form's validation fails on submit).
function _fieldKindPage(selector) {
  const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
  const el = q(selector);
  if (!el) return null;
  const tag = el.tagName.toLowerCase();
  const role = el.getAttribute('role');
  // Combobox classification — KEEP IN SYNC with fill_form's fieldKinds probe.
  // A click-then-pick dropdown announces itself via role=combobox/listbox OR
  // aria-haspopup=listbox/menu/true on a non-typeable trigger (Reach UI and
  // many a11y-first selects use a plain <button aria-haspopup="listbox">,
  // which the old role-only check classified as TEXT — typing into a button
  // silently no-ops). Input-comboboxes (autocomplete) also route to
  // fillDropdown: its click → type-in-search → pick flow commits a selection.
  const hp = (el.getAttribute('aria-haspopup') || '').toLowerCase();
  const popupTrigger = ['listbox', 'menu', 'true'].includes(hp) && tag !== 'input' && tag !== 'textarea';
  return {
    tag, role,
    is_native_select: tag === 'select',
    is_combobox: role === 'combobox' || role === 'listbox' || role === 'menubutton' || popupTrigger,
    is_checkbox_button: role === 'checkbox' || role === 'switch' ||
      (tag === 'input' && (el.type === 'checkbox' || el.type === 'radio')),
  };
}

// Set a checkbox/switch/radio to the requested state. text semantics:
// "checked"/"true"/"yes"/"on"/"1" -> checked; "unchecked"/"false"/"no"/"off"/"0"
// -> unchecked; anything else -> toggle. Was previously mis-routed to the TEXT
// path, which set button.value (a no-op) and reported success — a silent lie.
async function setCheckboxState(tabId, selector, text) {
  const rt = resolveFrameSelector(selector);
  // RADIO + A LABEL: retarget to the option the caller actually named. The ref may
  // be any member of the group (find/read_page hands back whichever one matched),
  // and clicking it regardless selects the wrong option while reporting success.
  if (text) {
    let rm = null;
    try { rm = await runInTab(tabId, _radioMatchPage, [rt.selector, String(text)], rt.frameId); } catch (e) {}
    if (rm && rm.err === 'no-match') {
      return { ok: false, actual: '', msg:
        `no radio in this group is labelled ${JSON.stringify(String(text))}` +
        (rm.options && rm.options.length
          ? `. The options are: ${rm.options.map(o => JSON.stringify(o)).join(', ')}. Pass one of these.`
          : '.') + ' Nothing was clicked.' };
    }
    if (rm && rm.mmid && !rm.same) {
      // Act on the named option instead of the ref we were handed.
      selector = `[mmid='${rm.mmid}']`;
      Object.assign(rt, resolveFrameSelector(selector));
      text = 'true';
    } else if (rm && rm.same) {
      text = 'true';
    }
  }
  const read = () => runInTab(tabId, (sel) => {
    const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
    const el = q(sel);
    if (!el) return null;
    const ac = el.getAttribute('aria-checked');
    return { cur: ac != null ? ac === 'true' : (el.checked === true) };
  }, [rt.selector], rt.frameId);
  const st = await read();
  if (!st) return { ok: false, actual: '', msg: `Element ${selector} not found.` };
  const want = String(text || '').trim().toLowerCase();
  const target = ['1', 'true', 'yes', 'on', 'checked', 'check'].includes(want) ? true
               : ['0', 'false', 'no', 'off', 'unchecked', 'uncheck'].includes(want) ? false
               : ['toggle', 'flip', 'switch'].includes(want) ? null   // explicit toggle
               : undefined;                                            // unrecognised
  // An unrecognised value used to mean "toggle", so a non-English or label-shaped
  // value (the model passing the field's caption, say) would FLIP a checkbox that
  // was already correct — turning a no-op into damage, and reporting success. Only
  // an explicit toggle word toggles now; anything else is refused loudly.
  // RADIOS are not checkboxes. `kind=checkbox` covers input[type=radio] too, and the
  // natural way to drive a radio group is form_input(ref, "Male") — a LABEL, not a
  // state word. Refusing that (the checkbox over-correction) broke every radio group.
  // For a radio, any unrecognised value means "select this one", which is the only
  // sensible action: radios cannot be unchecked by clicking.
  let _isRadio = false;
  try { _isRadio = (await runInTab(tabId, (sel) => {
    const q = (x) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(x || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(x); };
    const e2 = q(sel); if (!e2) return false;
    return (e2.tagName === 'INPUT' && (e2.type || '').toLowerCase() === 'radio') || e2.getAttribute('role') === 'radio';
  }, [rt.selector], rt.frameId)) === true; } catch (e) {}
  const _target = (target === undefined && _isRadio) ? true : target;
  if (_target === undefined) {
    return {
      ok: false,
      actual: st.cur ? 'checked' : 'unchecked',
      msg: `cannot interpret ${JSON.stringify(String(text || ''))} as a checkbox state. ` +
           `Pass true/false (or "checked"/"unchecked"), or "toggle" to invert it. ` +
           `Left as-is (currently ${st.cur ? 'checked' : 'unchecked'}).`,
    };
  }
  if (_target !== null && st.cur === _target) {
    return { ok: true, actual: st.cur ? 'checked' : 'unchecked', msg: `already ${st.cur ? 'checked' : 'unchecked'} — no action needed` };
  }
  await runInTab(tabId, _clickPage, [rt.selector], rt.frameId);
  // Poll for the state flip (React state round-trip)
  let st2 = await read();
  const t0 = Date.now();
  while (st2 && st2.cur === st.cur && Date.now() - t0 < 800) {
    await new Promise(r => setTimeout(r, 100));
    st2 = await read();
  }
  if (!st2 || st2.cur === st.cur) {
    // Synthetic click didn't register — escalate to trusted CDP input.
    try { await clickTrusted(tabId, selector); } catch (e) {}
    await new Promise(r => setTimeout(r, 200));
    st2 = await read();
  }
  const now = st2 ? st2.cur : st.cur;
  const ok = st2 && (_target === null ? now !== st.cur : now === _target);
  return {
    ok: !!ok,
    actual: now ? 'checked' : 'unchecked',
    msg: ok ? `checkbox now ${now ? 'checked' : 'unchecked'}`
            : `checkbox click did not change state (still ${now ? 'checked' : 'unchecked'})`,
  };
}

function _pickOptionPage(text, triggerSel) {
  // Find a visible option in the CURRENTLY-OPEN popover/listbox. Two filters
  // weed out stale options from popovers that just closed (Radix keeps closing
  // portal nodes around briefly during exit transitions; our stable-mmid change
  // also preserves them across re-renders):
  //   1. Exclude any option whose closest [data-state] ancestor is "closed"
  //      (Radix sets data-state="closed" on the way out).
  //   2. Exclude options inside an [aria-hidden="true"] subtree.
  // After filtering, prefer options inside an explicitly OPEN container
  // (data-state="open" or role=listbox/menu that's visible), falling back to
  // any visible option otherwise.
  //
  // FALLBACK FOR CUSTOM PICKERS: many apps (e.g. Boxsy's multi-select Focus
  // Areas) implement their own picker — a popover containing a search input
  // and clickable <div> rows with NO role="option". To handle these without
  // hard-coding the site, we ALSO accept clickable text-bearing rows that
  // live inside a popover-shaped container (data-radix-popper-content-wrapper,
  // or a [role=dialog]/[role=listbox]/[role=menu] that was JUST opened — i.e.
  // its mmid is in the highest range, indicating it's freshly mounted).
  // Deep query: options may render inside an OPEN shadow root (Lit/Shoelace-style
  // selects). Recurse shadow roots; Radix/shadcn/MUI portals are light DOM and
  // come back from the plain document scan anyway.
  const deepQueryAll = (sel) => {
    const acc = [];
    const visit = (root) => {
      try { root.querySelectorAll(sel).forEach(e => acc.push(e)); } catch (e) {}
      root.querySelectorAll('*').forEach(e => { if (e.shadowRoot) visit(e.shadowRoot); });
    };
    visit(document);
    return acc;
  };
  // 0) STRONGEST general signal: the trigger's aria-controls/aria-owns points
  // at the exact listbox it opened (W3C combobox pattern). Search THERE first —
  // no popover-shape guessing, works on every conforming library.
  let scopeRoot = null;
  if (triggerSel) {
    try {
      const qq = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
      const trig = qq(triggerSel);
      const ref = trig && (trig.getAttribute('aria-controls') || trig.getAttribute('aria-owns'));
      if (ref) {
        const idRoot = (trig.getRootNode && trig.getRootNode().getElementById) ? trig.getRootNode() : document;
        scopeRoot = ref.split(/\s+/).map(id => idRoot.getElementById(id)).find(Boolean) || null;
        // A container that CONTAINS the trigger is not the popover — it's the widget's
        // own selection box. select2-style multi-selects point aria-controls at it, and
        // harvesting there clicks a chosen tag (deselecting it) instead of an option.
        try { if (scopeRoot && trig && scopeRoot.contains(trig)) scopeRoot = null; } catch (e) {}
        // dup:decoyscope — A DECLARED SCOPE THAT IS NOT RENDERED IS A DECOY. rc-select
        // (which powers Ant Design, so this is a framework FAMILY not one site) ships a
        // hidden listbox as the aria-controls target and paints the real, role-less
        // options in a separate portal. Honouring the declaration then found zero
        // options and the picker gave up on a dropdown that was plainly open. The test
        // is what the user can see: an element with no box, display:none,
        // visibility:hidden or aria-hidden is not the popup being shown, whatever it
        // claims. Clearing it lets the topmost-visible-popover fallback below run.
        try {
          if (scopeRoot) {
            const _sr = scopeRoot.getBoundingClientRect();
            const _sc = getComputedStyle(scopeRoot);
            if (!(_sr.width > 0 && _sr.height > 0) || _sc.display === 'none' ||
                _sc.visibility === 'hidden' || scopeRoot.getAttribute('aria-hidden') === 'true') {
              scopeRoot = null;
            }
          }
        } catch (e) {}
      }
    } catch (e) {}
  }
  // NO aria-controls (or it was rejected): fall back to the TOPMOST VISIBLE POPOVER as
  // the scope rather than scanning the document. Without this, foreign always-visible
  // options elsewhere on the page (a plan picker, tag chips misusing aria-selected)
  // populate the pool, block the custom-picker harvest, and get offered to the model as
  // "available options" for a widget they have nothing to do with.
  if (!scopeRoot) {
    try {
      // TWO SOURCES OF CANDIDATES: what the document DECLARES, and what the layout
      // SHOWS. The declared half is `role=listbox`/`role=menu`. The rest of the old
      // selector list was three library-specific attribute names
      // (data-radix-popper-content-wrapper, data-popper-placement,
      // data-floating-ui-portal) — a list of the popover libraries someone thought
      // of, which is the shape this project keeps getting burned by. rc-select
      // (Ant Design, and every antd-derived UI) portals to a plain positioned div
      // with none of those attributes and role-less rows, so there was no
      // candidate at all, the scope stayed null, and the role scan below went
      // DOCUMENT-WIDE and offered the site's own nav bar as the field's options.
      //
      // The structural half asks what a popup IS: rendered, out of normal flow or
      // carrying its own stacking level, not containing the trigger, and holding at
      // least two sibling clickable rows. Bounded — portal targets are body
      // children, in-place popups are within a few ancestors of the trigger — so
      // there is no document-wide element sweep.
      const _qtrig = (x) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(x || ''); const r2 = window.__mmidReg; if (m && r2) { const n = r2.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(x); };
      const _tg0 = triggerSel ? _qtrig(triggerSel) : null;
      const _structural = [];
      try {
        const _pool = [];
        for (const c of Array.from(document.body.children)) _pool.push(c);
        let _w = _tg0, _hops = 0;
        while (_w && _hops < 5) {
          for (const c of Array.from(_w.children || [])) _pool.push(c);
          _w = _w.parentElement; _hops++;
        }
        for (const c of _pool) {
          if (!c.getBoundingClientRect) continue;
          let cs; try { cs = getComputedStyle(c); } catch (e) { continue; }
          const stacked = /^(fixed|absolute|sticky)$/.test(cs.position) ||
                          !isNaN(parseInt(cs.zIndex, 10));
          if (!stacked) continue;
          let rows = 0;
          try {
            for (const r of c.querySelectorAll('div, li, span, button, a')) {
              let rc; try { rc = getComputedStyle(r); } catch (e) { continue; }
              const tag = r.tagName.toLowerCase();
              if (!(rc.cursor === 'pointer' || tag === 'button' || tag === 'a' ||
                    r.hasAttribute('onclick') || r.hasAttribute('data-value'))) continue;
              const rr = r.getBoundingClientRect();
              if (rr.width >= 8 && rr.height >= 8 && (r.innerText || '').trim()) rows++;
              if (rows >= 2) break;
            }
          } catch (e) {}
          if (rows >= 2) _structural.push(c);
        }
      } catch (e) {}
      const _declared = Array.from(document.querySelectorAll('[role="listbox"], [role="menu"]'));
      const _named = Array.from(document.querySelectorAll(
        '[data-radix-popper-content-wrapper], [data-popper-placement], [data-floating-ui-portal]'
      ));
      // Instrumented: if the library-name list is never the SOLE source of the
      // chosen scope, it is carrying nothing and can go on the evidence.
      try {
        if (_named.length && !_declared.length && !_structural.length) {
          window.__abNamedPopoverOnly = (window.__abNamedPopoverOnly || 0) + 1;
        }
      } catch (e) {}
      const _seen = new Set();
      const cands = _declared.concat(_structural, _named).filter(c => {
        if (_seen.has(c)) return false;
        _seen.add(c);
        return true;
      }).filter(c => {
        try {
          const r = c.getBoundingClientRect();
          if (!(r.width > 0 && r.height > 0)) return false;
          const cs = getComputedStyle(c);
          if (cs.display === 'none' || cs.visibility === 'hidden') return false;
          const qq2 = (x) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(x || ''); const r2 = window.__mmidReg; if (m && r2) { const n = r2.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(x); };
          const tg = triggerSel ? qq2(triggerSel) : null;
          if (tg && c.contains(tg)) return false;         // selection box, not a popover
          return true;
        } catch (e) { return false; }
      });
      if (cands.length) {
        const zOf = (c) => { let z = 0, w = c; while (w && w !== document.body) { try { const v = parseInt(getComputedStyle(w).zIndex, 10); if (!isNaN(v)) z = Math.max(z, v); } catch (e) {} w = w.parentElement; } return z; };
        cands.sort((a, b) => zOf(a) - zOf(b));
        scopeRoot = cands[cands.length - 1];
      }
    } catch (e) {}
  }
  const OPTION_SEL = '[role="option"], [role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"], [role="treeitem"], li[data-value], [aria-selected]';
  let via = null;   // debug: which discovery path produced the option pool
  let all = [];
  if (scopeRoot) { try { all = Array.from(scopeRoot.querySelectorAll(OPTION_SEL)); if (all.length) via = 'aria-controls-scope'; } catch (e) {} }
  // Scope is a PREFERENCE, not an absolute. Making it absolute (an earlier attempt at
  // this) broke select2: its trigger's aria-controls resolves to a container that does
  // NOT hold the option rows, so scoping hard produced an empty pool and a spurious
  // "no option matched". The cross-widget-contamination problem it was meant to solve
  // is handled at the HARVEST GATE below instead, which asks whether any visible
  // option lives inside the scope rather than whether any exists anywhere.
  if (!all.length) { all = deepQueryAll(OPTION_SEL); if (all.length) via = 'aria-roles-deep'; }
  // A DECLARED PAGE LANDMARK IS NOT A DROPDOWN, and this is where that mattered.
  // The line above is a WHOLE-DOCUMENT query. #29 narrowed the sampleOptions probe
  // for exactly this reason and recorded that "_pickOptionPage has never scanned
  // the document" — which is false, it is the line above, and that sentence is why
  // the real widening survived the fix aimed at it.
  //
  // Measured live on ant.design 6.6.1 (rc-select): the trigger's aria-controls
  // resolves to a HIDDEN decoy listbox, so the scoped query returns nothing, the
  // document-wide fallback runs, and the site header's `<ul role="menu">` items
  // qualify. `inOpen` below then PREFERS them, because their ancestor is a
  // role=menu with no data-state. The result told the agent
  //   'Visible options are: "Design", "Development", "Components", "Blog"…
  //    Pass one of these exactly'
  // for a field whose real options are Jack/Lucy/Tom — and obeying that instruction
  // clicks a nav link and navigates off the page. Zero of the named options
  // belonged to the field.
  //
  // The fallback itself has to stay: making the declared scope absolute was tried
  // and broke select2, whose aria-controls resolves to a container that does not
  // hold its rows. So the fix is not narrower scoping, it is refusing DECLARED PAGE
  // CHROME. A dropdown popover is portaled out of flow; a site navigation lives
  // inside a landmark, which the document states with a sectioning element or a
  // navigation/menubar role. When the widened pass is all that is left, an empty
  // pool is the honest answer ("the list may still be loading") — that is the
  // situation on antd, where find() confirmed the real list had not rendered.
  if (via === 'aria-roles-deep') {
    const _chrome = (o) => {
      try {
        let w = o;
        for (let i = 0; i < 24 && w; i++) {
          w = w.parentElement || (w.getRootNode && w.getRootNode().host) || null;
          if (!w || w === document.body || w === document.documentElement) break;
          const t = (w.tagName || '').toLowerCase();
          const r = (w.getAttribute && w.getAttribute('role')) || '';
          if (t === 'nav' || t === 'header' || t === 'footer' || t === 'aside'
              || r === 'navigation' || r === 'menubar' || r === 'banner'
              || r === 'contentinfo') return true;
        }
      } catch (e) {}
      return false;
    };
    const _kept = all.filter((o) => !_chrome(o));
    if (_kept.length !== all.length) { all = _kept; via = 'aria-roles-deep-no-chrome'; }
  }
  // [aria-selected] also lives on tabs / grid cells / table rows — those are
  // NOT pickable dropdown options; matching them would click page chrome.
  all = all.filter(o => {
    const ro = o.getAttribute && o.getAttribute('role');
    return !ro || !['tab', 'row', 'gridcell', 'columnheader', 'rowheader'].includes(ro);
  });
  const isVisible = (o) => {
    try {
      const r = o.getBoundingClientRect();
      if (!(r.width > 0 && r.height > 0)) return false;
      const cs = getComputedStyle(o);
      if (cs.display === 'none' || cs.visibility === 'hidden') return false;
      // Excluded if ANY ancestor marks the subtree non-interactive:
      // aria-hidden / inert are the W3C-general signals; data-state="closed"
      // is a Radix-specific booster (their exit-transition portals linger).
      let w = o;
      while (w) {
        if (w.getAttribute) {
          if (w.getAttribute('data-state') === 'closed') return false;
          if (w.getAttribute('aria-hidden') === 'true') return false;
          if (w.hasAttribute && w.hasAttribute('inert')) return false;
        }
        w = w.parentElement;
      }
      return true;
    } catch (e) { return false; }
  };
  let vis = all.filter(isVisible);
  // HARVEST FALLBACK GATE — on VISIBLE standard-ARIA options, NOT raw match
  // count. The old `!all.length` gate had a flaky failure mode: a previously
  // closed menu/popover whose portal is still mounted (Radix keeps
  // data-state="closed" nodes around during exit transitions, sometimes
  // longer) leaves 1-2 STALE [aria-selected]/menuitem matches in the page.
  // Those raw matches blocked the fallback entirely, making custom pickers
  // (clickable rows with NO role=option — Boxsy focus areas/regions/stages)
  // unpickable whenever any stale portal existed. Visibility is the real
  // signal for "did the standard-ARIA path find the open popover's options".
  // HARVEST GATE. Previously "any visible ARIA option anywhere on the page" was enough
  // to suppress the custom-picker harvest — so an unrelated open listbox elsewhere
  // hijacked the pick (a second fixture listbox did exactly that to G25). When the
  // trigger told us which container it controls, ask whether any visible option is
  // actually IN it; foreign options must not vouch for this widget.
  const visInScope = scopeRoot ? vis.filter(o => { try { return scopeRoot.contains(o); } catch (e) { return false; } }) : vis;
  if (!visInScope.length) {
    // No standard-ARIA options — try to find a popover-like container and
    // harvest its clickable text rows as candidate options. Container query
    // covers ARIA roles + the major positioning libraries' portal markers
    // (Radix, Floating UI / Popper) as boosters.
    const containers = (scopeRoot ? [scopeRoot] : Array.from(document.querySelectorAll(
      '[data-radix-popper-content-wrapper], [data-popper-placement], [data-floating-ui-portal], [role="listbox"], [role="menu"], [role="dialog"]'
    ))).filter(c => c.getBoundingClientRect().width > 0 && c.getBoundingClientRect().height > 0);
    if (containers.length) {
      // Pick the container that's actually ON TOP: highest effective z-index,
      // DOM order as tie-break. (DOM order alone is wrong for apps that portal
      // popovers to the START of <body>.)
      const zOf = (c) => {
        let z = 0, w = c;
        while (w && w !== document.body) {
          try { const v = parseInt(getComputedStyle(w).zIndex, 10); if (!isNaN(v)) z = Math.max(z, v); } catch (e) {}
          w = w.parentElement;
        }
        return z;
      };
      containers.sort((a, b) => zOf(a) - zOf(b));   // stable: ties keep DOM order
      const pop = containers[containers.length - 1];
      const harvest = (requireClickable) => {
        const rows = Array.from(pop.querySelectorAll('div, li, span, button, a')).filter(r => {
          if (r === pop) return false;
          let cs;
          try { cs = getComputedStyle(r); } catch (e) { return false; }
          if (requireClickable) {
            // clickable-ish: cursor:pointer, real button/link, handler attr,
            // or option-ish markers. NOTE: React/Vue handlers are NOT
            // `onclick` attributes — that's why the relaxed pass exists.
            const clickable = cs.cursor === 'pointer' || r.tagName.toLowerCase() === 'button'
                           || r.tagName.toLowerCase() === 'a' || r.hasAttribute('onclick')
                           || r.hasAttribute('data-value') || r.hasAttribute('aria-selected');
            if (!clickable) return false;
          }
          const t = (r.innerText || '').trim();
          if (!t || t.length < 1 || t.length > 80) return false;
          const rect = r.getBoundingClientRect();
          if (rect.width < 8 || rect.height < 8) return false;
          // Skip the search input wrapper, headers, close buttons — these have
          // short text but aren't options. The good filter: many sibling rows
          // share the same parent. Options come in batches; chrome doesn't.
          return true;
        });
        // Group by parent; the parent with the MOST candidate children is the
        // options list. This filters out lone buttons (Close, Done) automatically.
        const byParent = new Map();
        for (const r of rows) {
          const p = r.parentElement;
          if (!p) continue;
          if (!byParent.has(p)) byParent.set(p, []);
          byParent.get(p).push(r);
        }
        let best = []; let bestSize = 0;
        for (const [, kids] of byParent) {
          if (kids.length > bestSize) { bestSize = kids.length; best = kids; }
        }
        return bestSize >= 2 ? best : [];   // need at least 2 siblings to be a list
      };
      // Pass 1: clickable-ish rows (original behavior). Pass 2: drop the
      // clickability requirement — React rows with default cursor and
      // framework-bound handlers satisfy NONE of the attribute checks, and
      // the sibling-cluster structure is the real signal anyway.
      let h = harvest(true), hv = 'harvest-clickable';
      if (!h.length) { h = harvest(false); hv = 'harvest-relaxed'; }
      // Only ADOPT the harvest when it actually found rows. Falling through with the
      // globally-discovered ARIA options is what keeps select2 working, where the
      // scoped container is empty but real options do exist in an open popover.
      // Harvested rows go FIRST (they came from the scoped/topmost popover, so they win
      // ties) but the ARIA pool is APPENDED rather than discarded: overwriting it meant
      // a wrong-but-nonempty scope threw away the genuine options entirely.
      if (h.length) { const prev = vis; all = h; via = hv; vis = all.filter(isVisible).concat(prev); }
    }
  }
  // Prefer options under a clearly-open container (the popover that just opened
  // is far more likely to be data-state=open than the page-level navigation menu).
  const inOpen = vis.filter(o => {
    let w = o.parentElement;
    while (w) {
      if (w.getAttribute && w.getAttribute('data-state') === 'open') return true;
      if (w.getAttribute && ['listbox','menu','dialog'].includes(w.getAttribute('role'))) {
        // is this container itself currently shown? data-state may be absent
        // on simpler popovers — but if it IS present, must not be closed.
        const ds = w.getAttribute('data-state');
        if (!ds || ds === 'open') return true;
      }
      w = w.parentElement;
    }
    return false;
  });
  const pool = inOpen.length ? inOpen : vis;
  // Locale-robust matching: Unicode NFC (composed accents — "México" typed NFC
  // must match a page rendering NFD), whitespace collapse (icon + label options
  // put newlines in innerText), locale-aware lowercase (Turkish Ä°/Ä±).
  // Ranked: exact > prefix > substring — plain `.includes` alone made "India"
  // match "Indiana" when the exact option existed later in the list.
  const norm = (s) => { try { return (s || '').normalize('NFC').replace(/\s+/g, ' ').trim().toLocaleLowerCase(); } catch (e) { return (s || '').trim().toLowerCase(); } };
  const want = norm(text);
  const dbgO = { via, found: all.length, vis: vis.length, inOpen: inOpen.length, pool: pool.length, scope: scopeRoot ? (scopeRoot.id || scopeRoot.tagName.toLowerCase()) : null };
  let pick = null, tier = null;
  if (want) {
    const labOf = (o) => norm(o.innerText);
    pick = pool.find(o => labOf(o) === want);                      if (pick) tier = 'exact';
    if (!pick) { pick = pool.find(o => labOf(o).startsWith(want)); if (pick) tier = 'prefix'; }
    if (!pick) { pick = pool.find(o => labOf(o).includes(want));   if (pick) tier = 'contains'; }
  }
  // NEVER click an arbitrary option when the requested text didn't match. The old
  // `pick = pool[0]` fallback returned ok:true with msg 'picked option "…"', and
  // fillDropdown's verifier then saw the trigger label CHANGE (to the wrong value)
  // and confirmed success — so a mismatched request silently submitted whatever
  // happened to be first. Common triggers: an AJAX dropdown whose options haven't
  // arrived, or a date-picker misclassified as a combobox (its "options" are then
  // whatever the harvest fallback scraped, possibly the parent dialog's buttons).
  // Failing loudly with the option list lets the model correct itself.
  // NO first-option fallback for an EMPTY request. `form_input(ref, "")` is a
  // natural "clear this field" gesture, and the sibling-cluster harvest can vote a
  // popover's FOOTER as the option row set — so clicking pool[0] pressed "Cancel"
  // and reported 'picked option "Cancel"'. An empty request has no correct pick.
  if (!pick && !want) {
    return { ok: false, actual: '',
      msg: 'no option text was given. A combobox needs the option TEXT to pick; ' +
           'clicking the first row is not a safe guess (it can be a Cancel/Discard control). ' +
           'Nothing was clicked.', dbg: dbgO };
  }
  if (!pick) {
    // These are handed back with 'Pass one of these exactly', so a silent cut
    // makes the recovery instruction impossible to follow — an agent retries the
    // truncated string and gets the identical error. Page context, so markCut is
    // out of scope; dup:markcut keeps this copy identical to the others.
    const _mk = (v, n) => (v.length <= n ? v : v.slice(0, n) + '…(+' + (v.length - n) + ')');
    const avail = pool.slice(0, 8).map(o => _mk((o.innerText || '').trim(), 40)).filter(Boolean);
    return {
      ok: false, actual: '',
      msg: want
        ? `no option matched ${JSON.stringify(text)}` +
          (avail.length ? `. Visible options are: ${avail.map(a => JSON.stringify(a)).join(', ')}` +
                          `. Pass one of these exactly, or re-observe if the list is still loading.`
                        : ' and no visible options were found (the list may still be loading).')
        : 'no visible options to pick',
      dbg: dbgO,
    };
  }
  // ALREADY SELECTED -> DO NOT CLICK. In a multi-select listbox (and in any
  // toggle-style menu) clicking a selected option DESELECTS it, so "make sure X is
  // chosen" silently un-chose it and still reported success. Worse, the false
  // negative in fillDropdown's verifier invites a retry, which toggles it again.
  // Report the desired end state as already true.
  try {
    if (pick.getAttribute('aria-selected') === 'true' || pick.getAttribute('aria-checked') === 'true' ||
        (pick.tagName === 'OPTION' && pick.selected)) {
      return { ok: true, actual: (pick.innerText || '').trim().slice(0, 60),
               msg: `option ${JSON.stringify(text)} was ALREADY selected — left it alone ` +
                    `(clicking it again would have deselected it).`,
               dbg: Object.assign({ alreadySelected: true }, dbgO) };
    }
  } catch (e) {}
  // behavior:'instant' — see _rectForPage: CSS scroll-behavior:smooth makes this
  // async, and a long option list scrolled mid-animation gets clicked at a stale
  // rect (the option rows are ~32px, so even a small drift misses).
  try { pick.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' }); } catch (e) {}
  // Debug: exactly WHAT we are about to click, where, and its container state.
  let pickInfo = { tier };
  try {
    const rr0 = pick.getBoundingClientRect();
    let ds = null, w = pick;
    while (w && ds === null) { ds = w.getAttribute ? w.getAttribute('data-state') : null; w = w.parentElement; }
    pickInfo = {
      tier,
      tag: pick.tagName.toLowerCase(),
      role: pick.getAttribute('role'),
      text: (pick.innerText || '').trim().slice(0, 60),
      rect: { x: Math.round(rr0.left), y: Math.round(rr0.top), w: Math.round(rr0.width), h: Math.round(rr0.height) },
      nearestDataState: ds,
      ariaSelected: pick.getAttribute('aria-selected'),
    };
  } catch (e) {}
  // FULL pointer sequence incl. hover + move — mirrors _clickPage (proven to
  // register on Radix SelectItem where the bare down/up/click sequence was
  // flaky): Radix arms items via pointermove/pointerover before accepting the
  // selection click; custom div pickers often gate on pointerdown only.
  try {
    const rr = pick.getBoundingClientRect();
    const x = rr.left + rr.width / 2, y = rr.top + rr.height / 2;
    const base = { bubbles: true, cancelable: true, composed: true, view: window, clientX: x, clientY: y, screenX: x, screenY: y, button: 0 };
    const ptr  = { ...base, pointerType: 'mouse', pointerId: 1, isPrimary: true };
    pick.dispatchEvent(new PointerEvent('pointerover',  ptr));
    pick.dispatchEvent(new PointerEvent('pointerenter', { ...ptr, bubbles: false }));
    pick.dispatchEvent(new MouseEvent  ('mouseover',    base));
    pick.dispatchEvent(new MouseEvent  ('mouseenter',   { ...base, bubbles: false }));
    pick.dispatchEvent(new PointerEvent('pointermove',  ptr));
    pick.dispatchEvent(new MouseEvent  ('mousemove',    base));
    pick.dispatchEvent(new PointerEvent('pointerdown', { ...ptr, buttons: 1 }));
    pick.dispatchEvent(new MouseEvent  ('mousedown',   { ...base, buttons: 1 }));
    pick.dispatchEvent(new PointerEvent('pointerup',   { ...ptr,  buttons: 0 }));
    pick.dispatchEvent(new MouseEvent  ('mouseup',     { ...base, buttons: 0 }));
  } catch (e) {}
  pick.click();
    {
    // SAY WHEN THE MATCH WAS NOT EXACT. "10" matched "100" by prefix and "male"
    // matched "Female" by contains, both reported as a plain success with the tier
    // buried in dbg (which the driver strips). A wrong quantity or a wrong category
    // committed silently is the worst outcome this function has; naming it costs
    // one clause and lets the model catch it.
    const _picked = (pick.innerText || '').trim().slice(0, 60);
    const _inexact = (tier === 'prefix' || tier === 'contains') && _picked && _picked !== text;
    return { ok: true, actual: _picked,
      msg: _inexact
        ? `no option exactly matched ${JSON.stringify(text)} — picked ${JSON.stringify(_picked)} by ${tier} match. ` +
          `If that is the wrong one, re-read the options and pass the exact text.`
        : `picked option ${JSON.stringify(text)}`,
      dbg: dbgO };
  }
}

// For a RADIO, the caller names the option they want ("Male"); the ref may be any
// member of the group. Clicking the ref regardless silently selects the WRONG
// option — verified: form_input(ref_of_male_radio, "Female") selected Male and
// reported success. Resolve the label against the group and act on the match.
function _radioMatchPage(selector, text) {
  const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg;
    if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {}
    return document.querySelector(s); };
  const el = q(selector);
  if (!el || el.type !== 'radio') return null;
  const norm = (x) => String(x || '').normalize('NFC').replace(/\s+/g, ' ').trim().toLowerCase();
  const want = norm(text);
  if (!want) return null;
  const labelOf = (n) => {
    let t = '';
    try {
      const root = (n.getRootNode && n.getRootNode().querySelector) ? n.getRootNode() : document;
      if (n.id) { const l = root.querySelector(`label[for="${CSS.escape(n.id)}"]`); if (l) t = l.innerText || ''; }
      if (!t) { const w = n.closest && n.closest('label'); if (w) t = w.innerText || ''; }
      if (!t) t = n.getAttribute('aria-label') || '';
    } catch (e) {}
    return norm(t) || norm(n.value);
  };
  const self = labelOf(el);
  if (self === want) return { mmid: el.getAttribute('mmid'), label: self, same: true };
  let group = [];
  try {
    const root = (el.getRootNode && el.getRootNode().querySelectorAll) ? el.getRootNode() : document;
    group = el.name ? Array.from(root.querySelectorAll(`input[type="radio"][name="${CSS.escape(el.name)}"]`)) : [el];
  } catch (e) { group = [el]; }
  const hit = group.find(r => labelOf(r) === want) || group.find(r => labelOf(r).startsWith(want));
  if (hit) return { mmid: hit.getAttribute('mmid'), label: labelOf(hit), same: hit === el };
  return { err: 'no-match', options: group.map(labelOf).filter(Boolean).slice(0, 10) };
}

function _selectNativePage(selector, text) {
  const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
  const el = q(selector);
  if (!el || el.tagName.toLowerCase() !== 'select') return { ok: false, actual: '', msg: 'not a <select>' };
  const norm = (s) => { try { return (s || '').normalize('NFC').replace(/\s+/g, ' ').trim().toLocaleLowerCase(); } catch (e) { return (s || '').trim().toLowerCase(); } };
  const want = norm(text);
  // Disabled options (and options inside a disabled optgroup) are states the user
  // could never reach; assigning one submits a value the form should reject.
  const opts = Array.from(el.options || []).filter(o => {
    try { return !o.disabled && !(o.parentElement && o.parentElement.tagName === 'OPTGROUP' && o.parentElement.disabled); }
    catch (e) { return true; }
  });
  const pick = opts.find(o => norm(o.text) === want)
            || opts.find(o => norm(o.value) === want)
            || opts.find(o => norm(o.text).startsWith(want))
            || opts.find(o => norm(o.text).includes(want));
  if (!pick) return { ok: false, actual: el.value, msg: `no option matching ${JSON.stringify(text)}` };
  el.value = pick.value;
  el.dispatchEvent(new Event('input',  { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return { ok: true, actual: pick.text, msg: `selected "${pick.text}"` };
}

function _countVisibleOptionsPage(triggerSel) {
  // SCOPE-AWARE (its old "same scope discipline as _pickOptionPage" comment was simply
  // false — it had no scope handling at all). Without this, always-visible foreign
  // [aria-selected]/role=option noise elsewhere on the page (a plan picker, tag chips
  // misusing aria-selected) made pollCount non-zero, which suppressed the trusted-open
  // escalation so the real dropdown never opened.
  let _scope = null;
  try {
    const q = (x) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(x || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(x); };
    const trig = triggerSel ? q(triggerSel) : null;
    // THE TRIGGER'S OWN STATE IS THE GATE. If it says closed, nothing on the page can be
    // this widget's open option list — that alone stops a foreign always-visible listbox
    // (a plan picker, tag chips misusing aria-selected) from making a CLOSED combobox
    // look open and suppressing the trusted-open escalation.
    if (trig) {
      const ex = trig.getAttribute('aria-expanded'), ds = trig.getAttribute('data-state');
      if (ex === 'false' || ds === 'closed') return 0;
    }
    const ref = trig && (trig.getAttribute('aria-controls') || trig.getAttribute('aria-owns'));
    if (ref) {
      const idRoot = (trig.getRootNode && trig.getRootNode().getElementById) ? trig.getRootNode() : document;
      _scope = ref.split(/\s+/).map(id => idRoot.getElementById(id)).find(Boolean) || null;
      // A scope containing the trigger is the widget's own selection box, not a popover.
      try { if (_scope && _scope.contains(trig)) _scope = null; } catch (e) {}
    }
  } catch (e) {}
  // Same scope discipline as _pickOptionPage: only count options inside a
  // popover that is actually OPEN right now (not transitioning out). Standard
  // ARIA first; if zero found, fall back to clickable-rows-in-popover heuristic
  // for custom pickers that don't use role=option.
  const _dqa = (sel) => {
    const acc = [];
    const visit = (root) => {
      try { root.querySelectorAll(sel).forEach(e => acc.push(e)); } catch (e) {}
      root.querySelectorAll('*').forEach(e => { if (e.shadowRoot) visit(e.shadowRoot); });
    };
    visit(document);
    return acc;
  };
  // KEEP IN SYNC with _pickOptionPage's queries/filters (page-injected
  // functions are serialized independently — no shared consts).
  const _OPT = '[role="option"], [role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"], [role="treeitem"], li[data-value], [aria-selected]';
  const _scoped = _scope ? Array.from(_scope.querySelectorAll(_OPT)) : [];
  // Preference, not absolute — select2's aria-controls target holds no option rows, so a
  // hard scope counts 0 forever and the whole open/pick chain stalls.
  const standard = (_scoped.length ? _scoped : _dqa(_OPT)).filter(o => {
    try {
      const ro = o.getAttribute && o.getAttribute('role');
      if (ro && ['tab', 'row', 'gridcell', 'columnheader', 'rowheader'].includes(ro)) return false;
      const r = o.getBoundingClientRect();
      if (!(r.width > 0 && r.height > 0)) return false;
      const cs = getComputedStyle(o);
      if (cs.display === 'none' || cs.visibility === 'hidden') return false;
      let w = o;
      while (w) {
        if (w.getAttribute) {
          if (w.getAttribute('data-state') === 'closed') return false;
          if (w.getAttribute('aria-hidden') === 'true') return false;
          if (w.hasAttribute && w.hasAttribute('inert')) return false;
        }
        w = w.parentElement;
      }
      return true;
    } catch (e) { return false; }
  });
  if (standard.length) return standard.length;
  // Fallback: count candidate rows inside the TOPMOST visible popover-container
  // (highest effective z-index; DOM order tie-break).
  // Scope the row-harvest fallback as well. Counting rows in ANY visible popover-shaped
  // container made a closed combobox look open whenever some unrelated listbox existed
  // on the page — which suppressed the trusted-open escalation entirely (zoo W4).
  const containers = ((_scope && _scope.querySelector('div,li,span,button,a')) ? [_scope] : Array.from(document.querySelectorAll(
    '[data-radix-popper-content-wrapper], [data-popper-placement], [data-floating-ui-portal], [role="listbox"], [role="menu"], [role="dialog"]'
  ))).filter(c => c.getBoundingClientRect().width > 0 && c.getBoundingClientRect().height > 0);
  if (!containers.length) return 0;
  const zOf = (c) => {
    let z = 0, w = c;
    while (w && w !== document.body) {
      try { const v = parseInt(getComputedStyle(w).zIndex, 10); if (!isNaN(v)) z = Math.max(z, v); } catch (e) {}
      w = w.parentElement;
    }
    return z;
  };
  containers.sort((a, b) => zOf(a) - zOf(b));
  const pop = containers[containers.length - 1];
  const countRows = (requireClickable) => {
    const rows = Array.from(pop.querySelectorAll('div, li, span, button, a')).filter(r => {
      if (r === pop) return false;
      let cs;
      try { cs = getComputedStyle(r); } catch (e) { return false; }
      if (requireClickable) {
        const clickable = cs.cursor === 'pointer' || r.tagName.toLowerCase() === 'button'
                       || r.tagName.toLowerCase() === 'a' || r.hasAttribute('onclick')
                       || r.hasAttribute('data-value') || r.hasAttribute('aria-selected');
        if (!clickable) return false;
      }
      const t = (r.innerText || '').trim();
      if (!t || t.length > 80) return false;
      const rect = r.getBoundingClientRect();
      return rect.width >= 8 && rect.height >= 8;
    });
    // sibling-cluster heuristic
    const byParent = new Map();
    for (const r of rows) {
      const p = r.parentElement; if (!p) continue;
      byParent.set(p, (byParent.get(p) || 0) + 1);
    }
    let best = 0;
    for (const [, n] of byParent) if (n > best) best = n;
    return best >= 2 ? best : 0;
  };
  return countRows(true) || countRows(false);
}

function _typeIntoOpenPopoverSearchPage(text, triggerSel) {
  // shadcn <Command>, Radix Combobox+Command, MUI Autocomplete and Headless UI all
  // render a searchable input INSIDE the open popover. Find it and type.
  //
  // SCOPED TO THE POPOVER — deliberately NOT a document-wide query. The old version
  // searched the whole document and took visible[0], with a "some ancestor within 8
  // levels contains a [role=listbox]" sanity gate that ANY header search box with
  // autocomplete satisfies (GitHub, MDN, most docs and e-commerce sites). So when a
  // combobox failed to render options in time, this typed the option text into the
  // SITE'S GLOBAL SEARCH, matched a search suggestion, and navigated away mid-form.
  // Resolve the trigger's aria-controls target first (W3C combobox pattern), else
  // the topmost popover-shaped container, and search only inside it.
  let scope = null;
  try {
    const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
    const trig = triggerSel ? q(triggerSel) : null;
    const ref = trig && (trig.getAttribute('aria-controls') || trig.getAttribute('aria-owns'));
    if (ref) {
      const idRoot = (trig.getRootNode && trig.getRootNode().getElementById) ? trig.getRootNode() : document;
      scope = ref.split(/\s+/).map(id => idRoot.getElementById(id)).find(Boolean) || null;
    }
  } catch (e) {}
  if (!scope) {
    const containers = Array.from(document.querySelectorAll(
      '[data-radix-popper-content-wrapper], [data-popper-placement], [data-floating-ui-portal], [role="listbox"], [role="menu"], [role="dialog"]'
    )).filter(c => { const r = c.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
    if (!containers.length) return { ok: false, msg: 'no open popover to type into' };
    const zOf = (c) => { let z = 0, w = c; while (w && w !== document.body) { try { const v = parseInt(getComputedStyle(w).zIndex, 10); if (!isNaN(v)) z = Math.max(z, v); } catch (e) {} w = w.parentElement; } return z; };
    containers.sort((a, b) => zOf(a) - zOf(b));
    scope = containers[containers.length - 1];
  }
  // PRIORITY ORDER, not document order. A comma-separated selector group returns
  // DOCUMENT order, so the implied priority of this list never existed — and with the
  // broad `input:not([type=hidden])` catch-all, a popover whose first input is a
  // "Select all" checkbox got the option text written into it and returned ok:true.
  // Iterate the sub-selectors most-specific-first and take the first VISIBLE hit.
  const INPUT_TIERS = [
    'input[cmdk-input]', '[cmdk-input]',
    'input[role="combobox"]', 'input[role="searchbox"]', 'input[type="search"]',
    'input[aria-autocomplete]',
    // Last resort: any text-ish input. Never a checkbox/radio/button/file — typing an
    // option name into those does nothing useful and silently reports success.
    'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="button"]):not([type="submit"]):not([type="file"]):not([type="range"])',
  ];
  const visibleIn = (root) => {
    for (const sel of INPUT_TIERS) {
      let hits = [];
      try { hits = Array.from(root.querySelectorAll(sel)); } catch (e) { continue; }
      for (const i of hits) {
        try {
          const r = i.getBoundingClientRect();
          const cs = getComputedStyle(i);
          if (r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden') return i;
        } catch (e) {}
      }
    }
    return null;
  };
  let inp = visibleIn(scope);
  // Per the W3C combobox pattern aria-controls names the LISTBOX, not the popover — so
  // widgets that put the filter input BESIDE the listbox (Headless UI Combobox and any
  // conforming hand-rolled picker) have no input inside the scope at all. Widen once to
  // the scope's nearest popover-shaped ancestor before giving up.
  let _widened = false;
  if (!inp) {
    let anc = scope.parentElement, hops = 0;
    while (anc && hops < 4 && !inp) {
      inp = visibleIn(anc);
      if (inp) { _widened = true; break; }
      anc = anc.parentElement; hops++;
    }
  }
  if (!inp) return { ok: false, msg: 'no search input inside the open popover' };
  // WIDENING CAN LEAVE THE WIDGET. Climbing four ancestors to find "a visible
  // input" found a DIFFERENT FORM FIELD on Google Flights: the text landed in the
  // add-another-origin box ("Where else?") while the ref the caller passed still
  // held its old value, and the tool reported success. Measured live; the agent
  // had to reload the page to recover.
  //
  // A filter box inside a picker is anonymous or explicitly search-ish. A peer
  // field carries its own identity — that is exactly what makes it someone else's
  // field. Refuse those, and name what we found either way so a wrong guess is
  // visible in the result instead of silent.
  const _inpName = (() => {
    try {
      const lbl = inp.labels && inp.labels[0];
      return (inp.getAttribute('aria-label') || (lbl && lbl.innerText) ||
              inp.getAttribute('placeholder') || inp.getAttribute('name') || '').trim();
    } catch (e) { return ''; }
  })();
  if (_widened) {
    // A filter box BELONGS to the picker we opened, and says so structurally:
    // aria-autocomplete is the W3C combobox filter signal, and aria-controls/owns
    // names the listbox we are scoped to. Both are language-independent. Do NOT
    // accept a bare role="combobox" — a peer autocomplete field (Flights' "Where
    // else?") carries that too, which is precisely the control we must not touch.
    // The fixture that caught an earlier, stricter version of this rule (W3) is a
    // labelled "Filter people" input beside its listbox: legitimate, and named.
    let _pointsHere = false;
    try {
      const _ac = (inp.getAttribute('aria-controls') || inp.getAttribute('aria-owns') || '').trim();
      _pointsHere = !!_ac && _ac.split(/\s+/).some((id) => {
        const tgt = document.getElementById(id);
        return tgt && (tgt === scope || scope.contains(tgt) || tgt.contains(scope));
      });
    } catch (e) {}
    const searchy = _pointsHere ||
                    !!inp.getAttribute('aria-autocomplete') ||
                    (inp.getAttribute('type') || '').toLowerCase() === 'search' ||
                    (inp.getAttribute('role') || '').toLowerCase() === 'searchbox' ||
                    !_inpName;
    if (!searchy) {
      return { ok: false, msg: `refused: the only input found is a DIFFERENT field ` +
        `(${JSON.stringify(_inpName)}), reached by searching outside this widget — typing ` +
        `there would silently fill the wrong control. Open the picker and choose an option ` +
        `by its text, or pass the ref of the field you actually mean.` };
    }
  }
  const visible = [inp];
  try { inp.focus(); } catch (e) {}
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  setter.call(inp, text || '');
  inp.dispatchEvent(new Event('input', { bubbles: true }));
  inp.dispatchEvent(new Event('change', { bubbles: true }));
  // NAME THE TARGET. "typed into popover search" gave the caller no way to tell
  // which control received the text, which is what let the wrong-field bug above
  // read as success.
  return { ok: true, msg: `typed ${JSON.stringify(text)} into the picker's search input` +
                          (_inpName ? ` (${JSON.stringify(_inpName)})` : ' (unlabeled)') +
                          (_widened ? ' [found outside the popover scope]' : '') };
}

// STRUCTURAL selection evidence for a custom combobox trigger, so decisions don't
// rest on an English wordlist. Returns the trigger's label plus two
// language-independent signals:
//   - hasPlaceholderAttr: [data-placeholder] on the trigger or its value node
//     (Radix/TipTap/shadcn convention) — the trigger is showing hint text.
//   - backing: the hidden native <select>/<input> the widget replaced, if one sits
//     alongside the widget wrapper. Its value is DEFINITIVE: empty means nothing is
//     selected regardless of what the trigger renders, in any language.
function _triggerEvidencePage(sel) {
  const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
  const el = q(sel);
  if (!el) return null;
  // Same structural placeholder test the collector uses (see _phMarked there):
  // the token "placeholder" in a data-* name, a data-* value, or a class list.
  // Kept in step deliberately — this evidence decides whether fillDropdown
  // believes a pick landed, and having the two disagree meant a German or
  // Japanese Chakra/PrimeVue widget was read one way when observed and another
  // way when acted on.
  let hasPlaceholderAttr = false;
  try {
    const txt = (el.innerText || '').trim();
    const marked = (n) => {
      if (!n || !n.attributes) return false;
      for (const a of n.attributes) {
        if (a.name.indexOf('aria-') === 0) continue;
        if (a.name.indexOf('placeholder') !== -1) {
          const v = (a.value || '').trim();
          if (!v || v === 'true' || !txt || v === txt) return true;
          continue;
        }
        if (a.name.indexOf('data-') === 0 && /(^|[\s,_-])placeholder([\s,_-]|$)/.test(a.value)) return true;
      }
      const cn = typeof n.className === 'string' ? n.className : (n.className && n.className.baseVal) || '';
      return /(^|[\s_-])placeholder([\s_-]|$)/.test(cn);
    };
    hasPlaceholderAttr = marked(el);
    if (!hasPlaceholderAttr) {
      for (const c of el.querySelectorAll('*')) {
        const ct = (c.innerText || '').trim();
        if (marked(c) && ct && (!txt || ct === txt)) { hasPlaceholderAttr = true; break; }
      }
    }
  } catch (e) {}
  let backing = null;
  try {
    const isNative = (n) => {
      // A backing control is a native control the library HID to render its own widget.
      // Accepting any <input> was wrong: a hidden CSRF token, a neighbouring quantity
      // field, or a same-row checkbox got adopted as "the backing control" and then drove
      // four separate decisions (unselected, the ok:true short-circuit, backed-by=ref_N,
      // DEAD-DUPLICATE). Require a <select> (always a replaced control in this pattern) or
      // an <input> the page has VISUALLY HIDDEN — libraries always hide the original. A
      // VISIBLE input beside a widget is a different field, never its backing.
      if (!n || n === el) return false;
      if (n.tagName === 'SELECT') return true;
      if (n.tagName !== 'INPUT') return false;
      if (['checkbox','radio','button','submit','file','range'].includes((n.type || '').toLowerCase())) return false;
      try {
        const r = n.getBoundingClientRect();
        // type=hidden is NOT a library-hidden original. A widget library replaces a
        // real control and hides it with CSS (display:none / 1px / sr-only) because it
        // still needs to be focusable and form-serialisable; type=hidden can be neither.
        // Meanwhile type=hidden is exactly what CSRF tokens, ids and nonces use — the
        // zoo's W1 caught this adopting a Rails _token as a select's "backing control".
        if ((n.type || '').toLowerCase() === 'hidden') return false;
        if (r.width <= 4 || r.height <= 4) return true;
        const cs = getComputedStyle(n);
        return cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity || '1') === 0;
      } catch (e) { return false; }
    };
    let w = el;
    for (let d = 0; d < 3 && w && w !== document.body; d++) {
      let cand = null;
      if (isNative(w.previousElementSibling)) cand = w.previousElementSibling;
      else if (isNative(w.nextElementSibling)) cand = w.nextElementSibling;
      else { for (const ch of w.children) { if (ch !== el && isNative(ch)) { cand = ch; break; } } }
      if (cand) {
        const selText = (cand.tagName === 'SELECT' && cand.options && cand.options[cand.selectedIndex])
          ? (cand.options[cand.selectedIndex].text || '').trim() : '';
        backing = { tag: cand.tagName.toLowerCase(), value: String(cand.value || '').trim(), text: selText,
                    weak: cand.tagName !== 'SELECT' };   // a hidden <input> is suggestive, not proof
        break;
      }
      w = w.parentElement;
    }
  } catch (e) {}
  return { label: (el.innerText || el.value || '').trim().slice(0, 80), hasPlaceholderAttr, backing };
}

function _triggerLabelPage(sel) {
  const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
  const el = q(sel);
  if (!el) return '';
  let t = (el.innerText || el.value || '').trim();
  // REACT-SELECT AND FRIENDS RENDER THE CHOICE OUTSIDE THE INPUT. The ref for one
  // of these widgets is the focusable <input>, and on commit the library CLEARS
  // that input and paints the selected value into a SIBLING node
  // (`...singleValue`). Reading only the input therefore returns "" both before
  // and after a successful pick, so the BEFORE/AFTER comparison concluded the
  // click never registered — measured on demoqa, 3 selections out of 3, each one
  // actually applied (`state: "option NCR, selected."`). The message did not
  // hedge either: it asserted "option click did not register", so an agent
  // retries, and on a multi-select a retry toggles the value back OFF.
  // Climb to the widget container and read what the user can SEE, minus the
  // input's own text. Bounded to 3 hops so this cannot wander into page layout.
  if (!t) {
    try {
      let w = el.parentElement;
      for (let d = 0; d < 3 && w; d++, w = w.parentElement) {
        const wr = w.getBoundingClientRect();
        if (wr.width > 600 || wr.height > 200) break;   // no longer the control
        const clone = w.cloneNode(true);
        try { clone.querySelectorAll('input,textarea').forEach((n) => n.remove()); } catch (e) {}
        const wt = (clone.textContent || '').replace(/\s+/g, ' ').trim();
        if (wt) { t = wt; break; }
      }
    } catch (e) {}
  }
  return t;
}

// dup:markcut — page-context copy; these functions are injected and lose closure.
function markCutLite(t, n) {
  t = t || '';
  if (t.length <= n) return t;
  let cut = t.slice(0, n);
  const sp = cut.lastIndexOf(' ');
  if (sp >= n * 0.66) cut = cut.slice(0, sp);
  return cut + '…(+' + (t.length - cut.length) + ')';
}

// Structural submit-button detection inside the current dialog/modal.
// Used (a) when the caller omits submit_mmid, and (b) to RE-RESOLVE an
// orphaned submit selector right before clicking - a disabled->enabled
// submit is typically a NEW React node without the observed mmid.
function _detectSubmitPage(fieldSel) {
  // SCOPE: the field's own <form> first, then an open dialog. Previously this only
  // ever looked inside a dialog, so on an ordinary non-modal page submit auto-detect
  // returned null and `fill_form(submit=true)` filled the fields and quietly did not
  // submit (it said so, but the caller asked for a submit and didn't get one). A
  // <form> is every bit as structural a scope as a dialog, and scoping to the FIELD'S
  // form avoids grabbing a search button from some unrelated form on the page.
  let scoped = null, fieldResolved = false;
  if (fieldSel) {
    try {
      const q = (x) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(x || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(x); };
      const f = q(fieldSel);
      if (f) fieldResolved = true;
      // [role=form] included: React apps very often have NO <form> element at all, which
      // is what made the global-dialog fallback the COMMON path rather than a rare one.
      if (f && f.closest) scoped = f.closest('[role="dialog"], [role="alertdialog"], [aria-modal="true"], dialog, form, [role="form"]');
    } catch (e) {}
  }
  const inside = (host) => {
              // If the field RESOLVED but has no form/dialog ancestor, that is an
              // answer — not a licence to search page-wide. Falling through to a global
              // dialog query let an unrelated one-button toast ("Got it", newsletter)
              // become the submit scope: tier 3 picked its sole button, the trusted
              // click dismissed the toast, and realEffect saw dialogs 1->0 and reported
              // "submit OK; modal closed" for a form that was never submitted.
              const globalDialog = fieldResolved ? null
                : document.querySelector('[role="dialog"], [role="alertdialog"], [aria-modal="true"], dialog');
              const dialog = host || scoped || globalDialog;
              if (!dialog) return null;
              const visible = (b) => {
                try { const r = b.getBoundingClientRect(); const cs = getComputedStyle(b);
                      return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden' && !b.disabled; }
                catch (e) { return false; }
              };
              const _allBtns = Array.from(dialog.querySelectorAll('button, [role="button"], input[type="submit"]'));
              const buttons = _allBtns.filter(visible);
              const pickFrom = (candidates) => {
                if (!candidates.length) return null;
                // Geometry tie-break: bottom action row, end-side button.
                // "End" depends on text direction — RTL dialogs put the primary
                // action on the LEFT.
                const rtl = (document.documentElement.dir === 'rtl') ||
                            (getComputedStyle(document.documentElement).direction === 'rtl');
                candidates.sort((a, b) => {
                  const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect();
                  return (br.top - ar.top) || (rtl ? (ar.left - br.left) : (br.left - ar.left));
                });
                const chosen = candidates[0];
                return {
                  mmid: chosen.getAttribute('mmid'),
                  label: (chosen.innerText || chosen.value || chosen.getAttribute('aria-label') || '').trim().slice(0, 60),
                };
              };
              // STRUCTURE ONLY — NO WORDLISTS. This function presses a button on the
              // user's behalf, and until now two natural-language wordlists decided
              // which one. Both were measured broken in the same invisible way: a
              // trailing \b is an ASCII-only boundary, so every CJK/Hangul/Cyrillic
              // word in the destructive list was dead code while its comment claimed
              // multilingual coverage; and the submit list had no non-English words at
              // all, making the keyword tier a guaranteed no-op on non-English forms.
              // Fixing them made the lists LONGER, not sound — any wordlist is a guess
              // about languages nobody enumerated, and here a wrong guess clicks
              // "Delete account".
              //
              // So auto-detect now answers only when the DOCUMENT says which button
              // submits this form, which HTML defines precisely:
              //   - an explicit type="submit"
              //   - a typeless <button> inside a real <form> (HTML's implicit submit)
              // EXACTLY ONE candidate -> use it. Zero or several -> refuse and NAME
              // them, so the agent (which has the listing and the task) picks with
              // submit_ref. That deletes the "is this one destructive?" question
              // outright: we never choose between Save and Delete account, because two
              // candidates is a refusal, not a coin flip.
              const _label = (b) =>
                ((b.innerText || b.value || b.getAttribute('aria-label') || '').trim());
              const _visible = (b) => {
                try {
                  const r = b.getBoundingClientRect();
                  if (r.width < 1 || r.height < 1) return false;
                  return !b.checkVisibility || b.checkVisibility({ opacityProperty: true, visibilityProperty: true });
                } catch (e) { return true; }
              };
              let pool = buttons.slice();
              // FORM-ASSOCIATED BUTTONS OUTSIDE THE FORM. Per HTML, `<button form="id">`
              // submits that form from anywhere in the document — the standard
              // modal-footer pattern. Querying only INSIDE the scope missed them, so a
              // form whose document DOES declare its submit was refused.
              try {
                const _f = dialog.tagName === 'FORM' ? dialog : (dialog.querySelector && dialog.querySelector('form'));
                const _id = _f && _f.getAttribute('id');
                if (_id) {
                  for (const ext of document.querySelectorAll(
                      `button[form="${CSS.escape(_id)}"], input[form="${CSS.escape(_id)}"]`)) {
                    if (pool.indexOf(ext) === -1) pool.push(ext);
                  }
                }
              } catch (e) {}
              const structural = pool.filter(b =>
                (b.getAttribute('type') || '').toLowerCase() === 'submit');
              const implicit = pool.filter(b =>
                b.tagName === 'BUTTON' && !b.hasAttribute('type') && !!b.closest('form'));
              // An explicit type="submit" outranks the implicit set; they are not pooled.
              const declared = structural.length ? structural : implicit;
              // A HIDDEN declared submit is not a candidate — but it is not nothing
              // either. Google's form declares input[name=btnK][type=submit] at 0x0;
              // refusing to click it is right, and saying "no type=submit exists" is
              // false. Track them so the message can tell the two apart.
              const cands = declared.filter(_visible);
              // Count declared-but-hidden submits from the UNFILTERED set: `buttons` has
              // already dropped them, so measuring there always yields zero. Google's
              // form declares input[name=btnK][type=submit] at 0x0 — refusing to click it
              // is right, and reporting "no type=submit exists" is false.
              let hidden = declared.length - cands.length;
              try {
                const _shown = new Set(cands);
                for (const b of _allBtns) {
                  if (_shown.has(b) || declared.indexOf(b) !== -1) continue;
                  const _t = (b.getAttribute('type') || '').toLowerCase();
                  if (_t === 'submit' && !_visible(b)) hidden++;
                }
              } catch (e) {}
              if (cands.length === 1) return pickFrom(cands);
              if (cands.length > 1) {
                // COLLAPSE STRUCTURALLY INTERCHANGEABLE CANDIDATES. Two submits with the
                // same label and no name/value/formaction/formmethod divergence produce
                // an IDENTICAL submission per HTML — GitHub's advanced search has exactly
                // two `Search` buttons like this. Refusing there asked the agent to pick
                // "the one you mean" between two identical strings, which is circular.
                // This is structural equivalence, not a guess about meaning.
                const key = (b) => [_label(b), b.getAttribute('name') || '',
                                    b.getAttribute('value') || '', b.getAttribute('formaction') || '',
                                    b.getAttribute('formmethod') || ''].join('\u0000');
                const distinct = new Set(cands.map(key));
                if (distinct.size === 1) return pickFrom(cands);
                return { mmid: null, label: '', hidden,
                         // Refs, not just labels: identical labels made the old message
                         // impossible to act on, and `.filter(Boolean)` silently emptied
                         // the list for icon-only submits.
                         ambiguous: cands.map(b => ({
                           mmid: b.getAttribute('mmid') || null,
                           label: _label(b) || '(no label — icon-only)',
                         })) };
              }
              return hidden ? { mmid: null, label: '', hidden, ambiguous: [] } : null;
            };
            return inside();
}

async function fillDropdown(tabId, selector, text) {
  // DEBUG TRACE: every step of the open -> find -> pick -> verify chain is
  // recorded and returned as `dbg`. The Python driver persists the full trace
  // to temp/task_*/fill_form_NN_*.txt on EVERY call (and strips it from the
  // model-facing string), so flaky dropdown failures are diagnosable after
  // the fact instead of needing a live repro.
  const T0 = Date.now();
  const trace = [];
  const tr = (m, d) => { try { trace.push((`+${Date.now() - T0}ms ${m}` + (d !== undefined ? ' ' + JSON.stringify(d) : '')).slice(0, 600)); } catch (e) {} };
  // Normalizer used for all label comparisons: Unicode NFC (composed accents),
  // whitespace collapse, locale-aware lowercase. Language-independent.
  const norm = (s) => { try { return (s || '').normalize('NFC').replace(/\s+/g, ' ').trim().toLocaleLowerCase(); } catch (e) { return (s || '').trim().toLowerCase(); } };

  // 0) capture the trigger's label BEFORE doing anything. Success verification
  // is "the label CHANGED (or now contains the requested option)" — a purely
  // structural test that works in any language, unlike the old English
  // placeholder-word check which reported false success on non-English UIs.
  // Cross-frame routing: resolve ONCE — in-frame scripts get the local
  // selector + frameId; clickTrusted re-resolves, so it gets the original.
  const _rt = resolveFrameSelector(selector);
  const origSelector = selector;
  const fid = _rt.frameId;
  selector = _rt.selector;
  const beforeLabel = await runInTab(tabId, _triggerLabelPage, [selector], fid) || '';
  // Trigger's pre-open state — catches the "popover was ALREADY open, our
  // open-click toggled it closed" failure mode.
  const _trigState = (label) => runInTab(tabId, (sel) => {
    const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
    const el = q(sel);
    if (!el) return null;
    return {
      expanded: el.getAttribute('aria-expanded'),
      state: el.getAttribute('data-state'),
      controls: el.getAttribute('aria-controls'),
      focused: document.activeElement === el,
    };
  }, [selector], fid).then(s => { tr(label, s); return s; }).catch(() => null);
  tr('beforeLabel', beforeLabel);
  await _trigState('trigger-state-before-open');

  // ALREADY-SELECTED SHORT-CIRCUIT: the caller asked for the value the trigger
  // already shows, and that value does not look like an unfilled placeholder.
  // Opening + re-picking is pure risk (React re-render races, Escape-vs-dialog
  // races — both observed live) for zero gain. Language-independent equality;
  // the placeholder-look check (wordlist + ellipsis) is the existing booster.
  // Requires POSITIVE, language-independent evidence that the label is a real
  // selection — not just that it equals the requested text. The old version was
  // gated only on an English wordlist + ellipsis, so a German trigger reading
  // "Bitte wählen" that the model echoed back returned ok:true "already selected"
  // without ever opening the dropdown: never filled, never verified. That also
  // falsified CLAUDE.md's claim that fill-time verification covers the
  // non-English placeholder residual.
  const _ev = text && beforeLabel && norm(text) === norm(beforeLabel)
    ? await runInTab(tabId, _triggerEvidencePage, [selector], fid).catch(() => null)
    : null;
  // i18n:placeholder — ONE spelling, enforced by tools/test_patterns.py.
  // This question (is the trigger showing a HINT rather than a choice?) was
  // asked in four places with four copies of an English-only wordlist.
  // DESTRUCTIVE drifted exactly that way and ended up rejecting 'Abbrechen'
  // in one tier while accepting it in another. These functions are injected
  // into the page and lose their closure, so the duplication is forced —
  // the test asserts every copy is byte-identical.
  // LAST RESORT: _showingPlaceholder / data-placeholder / an empty backing
  // control all run FIRST at every call site. This tier only exists for
  // hand-rolled widgets that mark placeholder state by grey text alone.
  // i18n:placeholder — DELETED, on the measurement. This asked "is the
  // trigger showing a HINT rather than a choice?" with an English-shaped
  // wordlist (select|choose|pick + ~20 translations). Ablated across 45
  // frozen sites with an INTERLEAVED drift control on the same page load:
  // its total effect on (unselected) flags was 14, and the drift floor —
  // the same source measured twice — was also 14. It changes nothing
  // beyond noise, because the structural signals already run FIRST and
  // carry every real case: _showingPlaceholder (the token `placeholder` in
  // a data-* name/value or class list, covering Radix/Chakra/PrimeVue/Ant/
  // select2), an empty backing form control, and a trailing ellipsis.
  // A wordlist that measures as noise is not a fallback, it is a liability:
  // this same shape shipped an ASCII-only \b that silently killed every
  // CJK entry, and "Select All Regions" — a genuine choice — was reported
  // as unselected, sending an agent to re-pick what it had already set.
  // The residual limitation is unchanged and now honest: a hand-rolled
  // non-English combobox marking placeholder state by grey text ALONE is
  // structurally indistinguishable from a chosen value. We no longer
  // pretend a wordlist closes that gap for the languages it happens to list.
  if (_ev) {
    tr('selection-evidence', _ev);
    const looksPlaceholder = _ev.hasPlaceholderAttr ||
      /\.\.\.$|…$/.test(beforeLabel.trim());
    // A backing native control is definitive in BOTH directions and in any
    // language: non-empty value confirms a real selection; empty value proves the
    // trigger is showing placeholder text no matter what it reads.
    // POSITIVE PROOF ONLY. The previous condition (!backedRefutes && !looksPlaceholder)
    // passed on the ABSENCE of refutation, so with no backing control — the normal case
    // for Radix/shadcn/HeadlessUI — it short-circuited on ZERO evidence and the German
    // "Bitte wählen" echo still returned ok:true, exactly the bug the comment claimed to
    // have fixed. A hidden <input> (weak) is not proof either. Opening is cheap and safe
    // now that a mismatch fails loudly instead of clicking pool[0], and `registered`
    // already treats "label unchanged but equals the request" as success, so re-picking
    // a genuinely selected value still passes.
    const backedConfirms = _ev.backing && !_ev.backing.weak && _ev.backing.value !== '';
    const backedRefutes  = _ev.backing && !_ev.backing.weak && _ev.backing.value === '';
    if (backedConfirms && !looksPlaceholder) {
      tr('already-selected short-circuit (no open, no pick)', { basis: backedConfirms ? 'backing-control' : 'trigger-label-only' });
      return {
        ok: true, actual: beforeLabel,
        msg: `already selected ${JSON.stringify(beforeLabel)} — no action needed (confirmed by the widget's backing <${_ev.backing.tag}>, value ${JSON.stringify(_ev.backing.value)})`,
        dbg: trace,
      };
    }
    tr('short-circuit REJECTED — trigger is showing placeholder text, will open and pick', { backedRefutes, looksPlaceholder });
  }

  // Detect when the caller passed the placeholder label back to us (model
  // confusion: "Select focus areas..." is the *unfilled* state, not an option).
  // General signal: requested text === the trigger's current (unfilled) text.
  // The English wordlist remains as a supplementary hint only.
  // EQUALITY ONLY — the bare English wordlist is gone from this gate. It used to
  // fire on any requested text starting with select/choose/pick, so asking for a
  // real option literally named "Select All" was treated as model confusion and
  // SKIPPED the registered-verification below, returning ok:true even when the
  // click never registered. Echo means "you handed me back the text the trigger is
  // already showing", which is exactly label equality and nothing else.
  const placeholderEcho = !!text && !!beforeLabel && norm(text) === norm(beforeLabel);

  // Poll helper: condition-based waiting instead of fixed sleeps — slow popover
  // animations / remote-data options (MUI, Ant showSearch, Select2 AJAX) need
  // longer than any fixed guess, while fast SPAs shouldn't pay the worst case.
  const pollCount = async (timeoutMs) => {
    const t0 = Date.now();
    for (;;) {
      const c = await runInTab(tabId, _countVisibleOptionsPage, [selector], fid);
      if (c) return c;
      if (Date.now() - t0 >= timeoutMs) return 0;
      await new Promise(r => setTimeout(r, 100));
    }
  };

  // 1) click the combobox to open the listbox popover (untrusted first)
  let open = await runInTab(tabId, _clickPage, [selector], fid);
  tr('open-click', open && { ok: open.ok, msg: (open.msg || '').slice(0, 120) });
  if (!open || !open.ok) return { ok: false, actual: '', msg: `couldn't open dropdown: ${open && open.msg}`, dbg: trace };
  let count = await pollCount(1200);
  tr('options-after-open', { count });
  await _trigState('trigger-state-after-open');

  // 2) if no options rendered, try trusted-input open (some triggers gate on
  // real pointer events; this matches our click auto-escalate).
  //
  // BUT FIRST ask the trigger whether it is ALREADY OPEN. "No options after 1.2s"
  // has two very different causes: the open click didn't register (escalate), or the
  // popover IS open and its options are still loading (a 2-3s AJAX round trip on
  // Select2/Ant/MUI Autocomplete is routine, showing a spinner and zero option
  // nodes). In the second case the trusted re-click TOGGLES THE POPOVER CLOSED and
  // the whole chain degrades from there. aria-expanded / data-state was already
  // being captured here for the trace only — now it drives the decision.
  if (!count) {
    const stOpen = await _trigState('trigger-state-before-escalation');
    const alreadyOpen = !!stOpen && (stOpen.expanded === 'true' || stOpen.state === 'open');
    if (alreadyOpen) {
      tr('popover reports OPEN — extending the option poll rather than re-clicking (a re-click would toggle it shut)');
      count = await pollCount(2500);
      tr('options-after-extended-poll', { count });
      if (!count) {
        // ARIA SAYS OPEN BUT NOTHING RENDERED — a HALF-OPEN state. Base UI (and shadcn's
        // Base-UI-backed Select) flips aria-expanded on the untrusted pointer sequence
        // while refusing to MOUNT the popover without a trusted event, so waiting longer
        // never helps. Deferring the escalation was right; SUPPRESSING it was not — that
        // is what this branch originally did, and it made every such widget unusable
        // through form_input/fill_form while a plain `computer` click opened it fine.
        // Reset the half-state with Escape (a trusted click here would just toggle the
        // flag off), then open for real with trusted input.
        tr('half-open state: aria-expanded=true with zero options — resetting and escalating to trusted input');
        // GATED, like the step-5 Escape. In the half-open premise the popover never
        // MOUNTED, so the topmost dismissable layer is whatever else is open — and
        // if this widget sits inside a modal (the common case: a combobox in a
        // form dialog), a document-level Escape closes THE DIALOG and every field
        // already filled in it is gone. Radix Dialog and native <dialog> both close
        // on key without caring about isTrusted. Send it only when no dialog is
        // open, and target the trigger rather than the document so a listening
        // ancestor sees it before the page does.
        try {
          const escaped = await runInTab(tabId, (sel) => {
            const q = (x) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(x || ''); const r = window.__mmidReg;
              if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {}
              return document.querySelector(x); };
            const openDialog = Array.from(document.querySelectorAll('[role="dialog"],[role="alertdialog"],[aria-modal="true"],dialog'))
              .some(d => { const r2 = d.getBoundingClientRect();
                           return r2.width > 0 && r2.height > 0 && getComputedStyle(d).visibility !== 'hidden'; });
            if (openDialog) return 'skipped: a dialog is open and Escape would close it';
            const ev = { key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true };
            const t = q(sel) || document;
            t.dispatchEvent(new KeyboardEvent('keydown', ev));
            t.dispatchEvent(new KeyboardEvent('keyup', ev));
            return 'sent';
          }, [origSelector], fid);
          tr('half-open Escape', escaped);
        } catch (e) {}
        await new Promise(r => setTimeout(r, 120));
        try { await clickTrusted(tabId, origSelector); } catch (e) { tr('clickTrusted threw', String(e).slice(0, 120)); }
        count = await pollCount(1500);
        tr('options-after-halfopen-recovery', { count });
      }
    } else {
      tr('escalating: trusted open click');
      try { await clickTrusted(tabId, origSelector); } catch (e) { tr('clickTrusted threw', String(e).slice(0, 120)); }
      count = await pollCount(1200);
      tr('options-after-trusted-open', { count });
      await _trigState('trigger-state-after-trusted-open');
    }
  }

  // 3) still nothing? Many multi-select popovers (command-palette style) only
  // render options after the user types into the embedded search input.
  if (!count && text) {
    const typed = await runInTab(tabId, _typeIntoOpenPopoverSearchPage, [text, selector], fid);
    tr('typed-into-popover-search', typed && { ok: typed.ok, msg: (typed.msg || '').slice(0, 120) });
    if (typed && typed.ok) {
      count = await pollCount(1000);
      tr('options-after-search-typing', { count });
    }
  }

  // 4) collect a few sample option labels (for caller visibility/debug) then pick.
  // Same logic as _pickOptionPage: try standard ARIA first, fall back to
  // clickable rows inside the topmost popover-container for custom pickers.
  const sampleOptions = await runInTab(tabId, (trigSel) => {
    const filterFresh = (o) => {
      try {
        const r = o.getBoundingClientRect();
        if (!(r.width > 0 && r.height > 0)) return false;
        const cs = getComputedStyle(o);
        if (cs.display === 'none' || cs.visibility === 'hidden') return false;
        let w = o;
        while (w) {
          if (w.getAttribute) {
            if (w.getAttribute('data-state') === 'closed') return false;
            if (w.getAttribute('aria-hidden') === 'true') return false;
          }
          w = w.parentElement;
        }
        return true;
      } catch (e) { return false; }
    };
    // Scope to the trigger's aria-controls container when available — sampling
    // the GLOBAL topmost popover can read a STALE portal's rows and report the
    // wrong dropdown's options to the model. KEEP IN SYNC with _pickOptionPage.
    let scopeRoot = null;
    try {
      const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
      const trig = trigSel ? q(trigSel) : null;
      const ref = trig && (trig.getAttribute('aria-controls') || trig.getAttribute('aria-owns'));
      if (ref) {
        const idRoot = (trig.getRootNode && trig.getRootNode().getElementById) ? trig.getRootNode() : document;
        scopeRoot = ref.split(/\s+/).map(id => idRoot.getElementById(id)).find(Boolean) || null;
        // Both of _pickOptionPage's rejections, which this probe was missing despite
        // the KEEP IN SYNC note: a container holding the trigger is the widget's own
        // selection box, and a container that is not rendered is a decoy.
        try { if (scopeRoot && trig && scopeRoot.contains(trig)) scopeRoot = null; } catch (e) {}
        // dup:decoyscope
        try {
          if (scopeRoot) {
            const _sr = scopeRoot.getBoundingClientRect();
            const _sc = getComputedStyle(scopeRoot);
            if (!(_sr.width > 0 && _sr.height > 0) || _sc.display === 'none' ||
                _sc.visibility === 'hidden' || scopeRoot.getAttribute('aria-hidden') === 'true') {
              scopeRoot = null;
            }
          }
        } catch (e) {}
      }
    } catch (e) {}
    const OPTION_SEL = '[role="option"], [role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"], [role="treeitem"], li[data-value], [aria-selected]';
    const roleOk = (o) => {
      const ro = o.getAttribute && o.getAttribute('role');
      if (ro && ['tab', 'row', 'gridcell', 'columnheader', 'rowheader'].includes(ro)) return false;
      return filterFresh(o);
    };
    let els = [];
    if (scopeRoot) { try { els = Array.from(scopeRoot.querySelectorAll(OPTION_SEL)).filter(roleOk); } catch (e) {} }
    // NEVER WIDEN PAST A DECLARATION. This line scanned the WHOLE DOCUMENT whenever
    // the declared container held no role-bearing options — which is how a site's own
    // nav bar was reported to the model as "other options available" for a select.
    // Anything on the page carrying [aria-selected] or li[data-value] qualified.
    // CORRECTION: the note here used to say "_pickOptionPage has never scanned the
    // document". It does — `deepQueryAll(OPTION_SEL)` — and asserting otherwise is
    // why the widening in the half that matters outlived the fix aimed at it. Both
    // copies now refuse DECLARED PAGE CHROME on the widened pass; see the long note
    // at that site for the ant.design 6.6.1 measurement.
    if (!els.length && !scopeRoot) {
      els = Array.from(document.querySelectorAll(OPTION_SEL)).filter(roleOk).filter((o) => {
        try {
          let w = o;
          for (let i = 0; i < 24 && w; i++) {
            w = w.parentElement || (w.getRootNode && w.getRootNode().host) || null;
            if (!w || w === document.body || w === document.documentElement) break;
            const t = (w.tagName || '').toLowerCase();
            const r = (w.getAttribute && w.getAttribute('role')) || '';
            if (t === 'nav' || t === 'header' || t === 'footer' || t === 'aside'
                || r === 'navigation' || r === 'menubar' || r === 'banner'
                || r === 'contentinfo') return false;
          }
        } catch (e) {}
        return true;
      });
    }
    if (!els.length) {
      const containers = (scopeRoot ? [scopeRoot] : Array.from(document.querySelectorAll(
        '[data-radix-popper-content-wrapper], [data-popper-placement], [data-floating-ui-portal], [role="listbox"], [role="menu"], [role="dialog"]'
      ))).filter(c => c.getBoundingClientRect().width > 0 && c.getBoundingClientRect().height > 0);
      if (containers.length) {
        const zOf = (c) => {
          let z = 0, w = c;
          while (w && w !== document.body) {
            try { const v = parseInt(getComputedStyle(w).zIndex, 10); if (!isNaN(v)) z = Math.max(z, v); } catch (e) {}
            w = w.parentElement;
          }
          return z;
        };
        containers.sort((a, b) => zOf(a) - zOf(b));
        const pop = containers[containers.length - 1];
        const rows = Array.from(pop.querySelectorAll('div, li, span, button, a')).filter(r => {
          if (r === pop) return false;
          let cs; try { cs = getComputedStyle(r); } catch (e) { return false; }
          const clickable = cs.cursor === 'pointer' || r.tagName.toLowerCase() === 'button'
                         || r.tagName.toLowerCase() === 'a' || r.hasAttribute('onclick')
                         || r.hasAttribute('data-value') || r.hasAttribute('aria-selected');
          if (!clickable) return false;
          const t = (r.innerText || '').trim();
          if (!t || t.length > 80) return false;
          const rect = r.getBoundingClientRect();
          return rect.width >= 8 && rect.height >= 8;
        });
        const byParent = new Map();
        for (const r of rows) {
          const p = r.parentElement; if (!p) continue;
          if (!byParent.has(p)) byParent.set(p, []);
          byParent.get(p).push(r);
        }
        let best = []; for (const [, kids] of byParent) if (kids.length > best.length) best = kids;
        if (best.length >= 2) els = best;
      }
    }
    return els.slice(0, 6).map(o => (o.innerText || '').trim().slice(0, 40)).filter(Boolean);
  }, [selector], fid) || [];
  tr('sample-options', sampleOptions);
  const pick = await runInTab(tabId, _pickOptionPage, [text, selector], fid);
  tr('pick', pick);
  // 5) close popover (Escape) — ONLY if it is still open. Multi-select
  // popovers stay open after a pick and would block the next dropdown's
  // open click; single-select popovers AUTO-CLOSE on pick. A blind Escape
  // races the closing popover's unmount: if the popover layer is already
  // gone, the Escape lands on the NEXT topmost dismissable layer — the
  // parent DIALOG — and closes the whole modal mid-form (observed live:
  // every subsequent field "not found"). Synthetic Escape works on
  // Radix/HeadlessUI/MUI/shadcn (their handlers gate on key, not isTrusted).
  await new Promise(r => setTimeout(r, 120));   // let a self-closing popover mark itself closed
  // Authoritative open/closed signal: the trigger's own aria-expanded /
  // data-state (W3C combobox pattern). The option-count heuristic is only a
  // fallback — its popover-shape harvest can mistake the parent dialog's
  // buttons for options and false-positive "still open".
  let stillOpen = false;
  const stAfterPick = await _trigState('trigger-state-after-pick');
  if (stAfterPick && (stAfterPick.expanded === 'true' || stAfterPick.state === 'open')) {
    stillOpen = true;
  } else if (stAfterPick && (stAfterPick.expanded === 'false' || stAfterPick.state === 'closed')) {
    stillOpen = false;
  } else if (stAfterPick) {
    try { stillOpen = (await runInTab(tabId, _countVisibleOptionsPage, [selector], fid)) > 0; } catch (e) {}
  } // trigger gone entirely (re-render / dialog closed) -> never Escape
  if (stillOpen) {
    try {
      await runInTab(tabId, () => {
        const ev = { key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true };
        document.dispatchEvent(new KeyboardEvent('keydown', ev));
        document.dispatchEvent(new KeyboardEvent('keyup',   ev));
        if (document.activeElement) {
          document.activeElement.dispatchEvent(new KeyboardEvent('keydown', ev));
        }
      }, [], fid);
      tr('escape-dispatched (popover still open)', { optionsVisible: stillOpen });
    } catch (e) { tr('escape threw', String(e).slice(0, 120)); }
    await new Promise(r => setTimeout(r, 150));
    // Insurance in the trace: did the Escape take out a dialog layer?
    try {
      const dlgs = await runInTab(tabId, () =>
        document.querySelectorAll('[role="dialog"], [role="alertdialog"], [aria-modal="true"], dialog').length, [], fid);
      tr('dialogs-after-escape', { dialogs: dlgs });
    } catch (e) {}
  } else {
    tr('escape skipped (popover already closed after pick)');
  }

  if (!pick || !pick.ok) {
    const opts = sampleOptions.length ? ` Available options: ${sampleOptions.map(s => JSON.stringify(s)).join(", ")}` : '';
    return { ok: false, actual: '', msg: ((pick && pick.msg) || 'no visible options to pick') + opts, dbg: trace };
  }
  // 6) verify the pick actually REGISTERED, structurally and language-
  // independently: poll the trigger label until it (a) differs from the
  // before-snapshot, or (b) contains the picked option / requested text
  // (covers re-picking an already-selected value, where "unchanged" is fine).
  // The old check (`does the label start with select/choose/pick?`) reported
  // false success on every non-English UI.
  let triggerLabel = '';
  let registered = false;
  {
    const wantN = norm(text), pickedN = norm(pick.actual || '');
    const t0 = Date.now();
    const vPolls = [];
    for (;;) {
      triggerLabel = await runInTab(tabId, _triggerLabelPage, [selector], fid) || '';
      vPolls.push(`+${Date.now() - t0}ms "${triggerLabel.slice(0, 60)}"`);
      const labN = norm(triggerLabel);
      registered = (labN && labN !== norm(beforeLabel)) ||
                   (!!pickedN && labN.includes(pickedN)) ||
                   (!!wantN && labN.includes(wantN));
      if (registered || Date.now() - t0 >= 800) break;
      await new Promise(r => setTimeout(r, 100));
    }
    tr('verify', { beforeLabel: beforeLabel.slice(0, 60), polls: vPolls, registered });
    if (!registered) await _trigState('trigger-state-after-failed-verify');
  }
  const optsHint = sampleOptions.length
    ? ` (other options available: ${sampleOptions.map(s => JSON.stringify(s)).join(", ")})`
    : '';
  if (placeholderEcho) {
    return {
      ok: true,
      actual: pick.actual,
      msg: `picked "${pick.actual}" (NOTE: you passed placeholder text ${JSON.stringify(text)} — harness picked first visible option; pass a real option label next time)${optsHint}`,
      dbg: trace,
    };
  }
  if (!registered) {
    return {
      ok: false,
      actual: triggerLabel,
      msg: `pick reported OK but the trigger label did not change (still ${JSON.stringify(triggerLabel)}) — option click did not register${optsHint}`,
      dbg: trace,
    };
  }
  return { ok: true, actual: pick.actual, msg: `${pick.msg} (trigger now: ${JSON.stringify(triggerLabel)})${optsHint}`, dbg: trace };
}

async function fillField(tabId, selector, text, trusted) {
  const rt = resolveFrameSelector(selector);
  const kind = await runInTab(tabId, _fieldKindPage, [rt.selector], rt.frameId);
  if (kind && kind.is_native_select) {
    return await runInTab(tabId, _selectNativePage, [rt.selector, text || ""], rt.frameId);
  }
  if (kind && kind.is_combobox) {
    return await fillDropdown(tabId, selector, text || "");   // resolves internally
  }
  if (kind && kind.is_checkbox_button) {
    return await setCheckboxState(tabId, selector, text || "");   // resolves internally
  }
  // plain text input / textarea / contenteditable
  return trusted
    ? await enterTextTrusted(tabId, selector, text || "")     // resolves internally
    : await runInTab(tabId, _enterTextPage, [rt.selector, text || ""], rt.frameId);
}

async function enterTextTrusted(tabId, selector, text) {
  const rt = resolveFrameSelector(selector);
  const focused = await runInTab(tabId, (sel) => {
    const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
    const el = q(sel);
    if (!el) return false;
    try { el.scrollIntoView({ block: "center", inline: "center", behavior: "instant" }); } catch (e) {}
    // REFUSE BEFORE DESTROYING ANYTHING. This used to focus, then clear, then let
    // CDP insertText go to document.activeElement — but focus() on a disabled or
    // otherwise unfocusable element is a silent no-op, so the target's existing
    // value was wiped and the new text was typed into whatever had focus BEFORE
    // (verified: a secret landed in a neighbouring field while the tool reported
    // failure on the target and said nothing about the field it actually wrote).
    // A write we cannot aim is a write we must not make.
    if (el.disabled || el.readOnly) return { err: 'disabled-or-readonly' };
    try { el.focus({ preventScroll: true }); } catch (e) {}
    const od = el.ownerDocument || document;
    let ae = od.activeElement;
    // A shadow-hosted control reports its HOST as activeElement.
    while (ae && ae !== el && ae.shadowRoot && ae.shadowRoot.activeElement) ae = ae.shadowRoot.activeElement;
    if (ae !== el) return { err: 'focus-refused' };
    if ('value' in el) {
      const ns = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value')?.set;
      if (ns) ns.call(el, ''); else el.value = '';
      el.dispatchEvent(new Event('input', { bubbles: true }));
    } else if (el.isContentEditable) {
      el.textContent = '';
    }
    return true;
  }, [rt.selector], rt.frameId);
  if (focused && focused.err === 'disabled-or-readonly') {
    return { ok: false, actual: "", msg:
      `Element ${selector} is disabled or readonly — nothing was typed and its existing value is intact.` };
  }
  if (focused && focused.err === 'focus-refused') {
    return { ok: false, actual: "", msg:
      `Element ${selector} would not take focus, so typing would have gone to whatever was focused ` +
      `instead — refused. Nothing was typed and no field was modified. Click the element first, or ` +
      `check whether it is really a text input.` };
  }
  if (!focused) return { ok: false, actual: "", msg: `Element ${selector} not found.` };

  await attachDebugger(tabId);
  // CDP Input.insertText goes to the FOCUSED element — focus set in-frame
  // above works for cross-origin frames too (focus crosses frame boundaries).
  await cdpSend(tabId, "Input.insertText", { text });

  const actual = await runInTab(tabId, (sel) => {
    const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
    const el = q(sel);
    if (!el) return null;
    return ('value' in el) ? el.value : (el.innerText || el.textContent || '');
  }, [rt.selector], rt.frameId);
  return {
    ok: actual === text || (text && actual && actual.includes(text)),
    actual: actual || "",
    msg: `Typed into ${selector} via TRUSTED input.`,
  };
}

// --------------------- INJECTED FUNCTIONS (run in page context) -------------
// Idempotent / deterministic mmid injection — must match the algorithm used by
// the rest of the codebase so element ids line up across observations.
function _ensureMmidsPage() {
  // STABLE mmids across re-renders: assign only to elements that don't already
  // have one, using a persistent document-level counter. React/Vue/Next.js
  // re-renders REPLACE old DOM nodes with new ones (no mmid) but the survivors
  // keep theirs — so a fill_form that referenced mmid=851 still finds the
  // node it was looking at, instead of "element not found" after a mid-form
  // re-render. Counter resets only when the document navigates (new page).
  //
  // SHADOW DOM: the walk recurses into OPEN shadow roots (el.shadowRoot), so
  // web-component UIs (Lit/Stencil/Shoelace/ytd-*) get mmids too. Because
  // document.querySelector("[mmid='N']") cannot see inside shadow roots, every
  // walk also (re)builds window.__mmidReg — a Map of mmid -> live element that
  // the action functions use to resolve selectors across shadow boundaries.
  // NOTE: only true non-content tags here. ('main' and Google's 'c-wiz' were
  // once excluded — that denied mmids to a standard landmark and overfit to
  // one vendor; both removed. SVG internals are handled by decorativeTags.)
  const tags_to_ignore = ['head','style','script','link','meta','noscript','template','g','path'];
  const ids_to_ignore = ['agentDriveAutoOverlay'];
  if (typeof window.__mmidCounter !== 'number') window.__mmidCounter = 0;
  const reg = new Map();
  const visit = (root) => {
    root.querySelectorAll('*').forEach(el => {
      const tag = el.tagName.toLowerCase();
      if (!tags_to_ignore.includes(tag) && !ids_to_ignore.includes(el.id)) {
        if (!el.hasAttribute('mmid')) el.setAttribute('mmid', `${++window.__mmidCounter}`);
        reg.set(el.getAttribute('mmid'), el);
      }
      if (el.shadowRoot) visit(el.shadowRoot);   // pierce open shadow roots
      // SAME-ORIGIN IFRAMES: contentDocument is reachable -> recurse like a
      // shadow root (cross-origin returns null / throws -> stays opaque).
      if (tag === 'iframe' || tag === 'frame') {
        try { if (el.contentDocument) visit(el.contentDocument); } catch (e) {}
      }
    });
  };
  visit(document);
  window.__mmidReg = reg;
  return true;
}

// Enumerate the page's INACCESSIBLE (cross-origin) iframe shells with their
// top-document rects — the anchor points for merging per-frame collections.
function _frameShellsPage() {
  const out = [];
  document.querySelectorAll('iframe, frame').forEach(f => {
    let accessible = false;
    try { accessible = !!f.contentDocument; } catch (e) {}
    if (accessible) return;
    const r = f.getBoundingClientRect();
    if (!(r.width > 30 && r.height > 30)) return;   // skip tracking pixels
    let cs; try { cs = getComputedStyle(f); } catch (e) { return; }
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    out.push({
      src: f.src || '',
      title: f.getAttribute('title') || f.getAttribute('name') || '',
      x: Math.round(r.left), y: Math.round(r.top),
      w: Math.round(r.width), h: Math.round(r.height),
    });
  });
  return out;
}

// Collect + serialize the contents of cross-origin iframes (depth-1) and
// return text to APPEND to the main listing. Each frame's entries act through
// selector [mmid='f<frameId>:<n>'] — resolveFrameSelector routes the ops.
async function collectCrossFrames(tabId, geometry) {
  let frames = [];
  try { frames = await chrome.webNavigation.getAllFrames({ tabId }) || []; } catch (e) { return ''; }
  const children = frames.filter(f => f.frameId !== 0 && f.parentFrameId === 0 &&
                                       f.url && !f.url.startsWith('about:'));
  if (!children.length) return '';
  let shells = [];
  try { shells = await runInTab(tabId, _frameShellsPage) || []; } catch (e) { return ''; }
  if (!shells.length) return '';
  const shellMap = new Map();
  const used = new Set();
  for (const fr of children) {
    // Anchor the frame to its shell: exact src match first, then unique-host.
    let shell = shells.find((s, i) => !used.has(i) && s.src && s.src === fr.url);
    if (!shell) {
      try {
        const host = new URL(fr.url).hostname;
        const cands = shells.filter((s, i) => !used.has(i) && s.src && (() => { try { return new URL(s.src).hostname === host; } catch (e) { return false; } })());
        if (cands.length === 1) shell = cands[0];
      } catch (e) {}
    }
    if (shell) { used.add(shells.indexOf(shell)); shellMap.set(fr.frameId, shell); }
  }
  // GEOMETRIC FALLBACK: exact-src then unique-host matching both fail when a page
  // embeds SEVERAL same-host frames (Stripe Elements ships card/expiry/CVC as three
  // js.stripe.com iframes) or when the live URL has drifted from the src attribute
  // (redirects, hash/query rewrites). Previously those frames were dropped silently
  // — collectCrossFrames returns '' on every failure path, so the agent saw no
  // breadcrumb at all. When the counts line up, document order is a sound pairing.
  if (!shellMap.size && children.length === shells.length && shells.length > 0) {
    // chrome.webNavigation.getAllFrames order is NOT guaranteed to be DOM order, so a
    // raw index pairing can anchor a frame to the wrong shell. Sort both sides by src
    // when every frame has one; only then is the pairing meaningful. Otherwise pair by
    // index but say so, because a silent wrong anchor is worse than an admitted guess.
    const cs = children.slice(), ss = shells.slice();
    if (cs.every(f => f.url) && ss.every(sh => sh.src)) {
      cs.sort((a, b) => String(a.url).localeCompare(String(b.url)));
      ss.sort((a, b) => String(a.src).localeCompare(String(b.src)));
    }
    cs.forEach((fr, i) => shellMap.set(fr.frameId, ss[i]));
  }
  if (!shellMap.size) return '';
  const offsets = new Map();
  let text = '';
  for (const [fid, shell] of shellMap) {
    let raw = null;
    try { raw = await runInTab(tabId, _collectInteractivePage, [true], fid); } catch (e) { continue; }
    if (!Array.isArray(raw) || !raw.length) continue;
    offsets.set(fid, { x: shell.x, y: shell.y, w: shell.w, h: shell.h, src: shell.src || '' });
    let host = '';
    try { host = new URL(shell.src).hostname; } catch (e) {}
    const lines = [];
    // PRIORITISE before capping, then say what was cut. The old code did a blind
    // slice(0,40) and printed the kept count as though it were complete — so a TCF
    // consent frame with dozens of vendor toggles hid its "Save & Exit"/"Accept"
    // buttons past index 40 with no truncation note. The main listing has been
    // scrupulous about this for rounds; this path was not.
    const FRAME_CAP = 40;
    const _pri = (e) => (e.required || e.unselected || e.tag === 'button' ||
                         e.tag === 'input' || e.tag === 'select' || e.tag === 'textarea' ||
                         e.role === 'button' || e.role === 'checkbox' || e.role === 'combobox') ? 0 : 1;
    const ordered = raw.length > FRAME_CAP
      ? raw.slice().sort((a, b) => _pri(a) - _pri(b)).slice(0, FRAME_CAP)
      : raw;
    const frameHidden = raw.length - ordered.length;
    for (const e of ordered) {
      let id = '';
      if (e.name)        id += ` name=${JSON.stringify(e.name)}`;
      if (e.value)       id += ` value=${JSON.stringify(e.value)}`;
      if (e.placeholder) id += ` placeholder=${JSON.stringify(e.placeholder)}`;
      if (!id && e.text) id = ` "${e.text}"`;
      if (!id && e.label) id = ` "${e.label}"`;
      const flags = (e.active ? ` (${e.active})` : '') + (e.required ? ' (required)' : '') +
                    (e.unselected ? ' (unselected)' : '') + (e.disabled ? ' (disabled)' : '');
      const rl = (e.role && e.role !== e.tag) ? ` role=${e.role}` : '';
      // `ref_` , not `mmid=`. The main listing moved to ref_N and tells the agent
      // "Act on a row by its ref_N", while these rows still announced themselves
      // with the internal spelling — two vocabularies for one concept, in the one
      // place (a cross-origin frame) where the agent is already least sure how to
      // address the element. The banner below says "act with ref f<fid>:N"; now
      // the rows agree with it.
      const _xbox = geometry ? ` | box(${e.x + shell.x},${e.y + shell.y},${e.w},${e.h})` : '';
      lines.push(`ref_f${fid}:${e.mmid} | ${e.tag}${id}${rl}${flags}${_xbox}`);
    }
    if (lines.length) {
      text += `\n[CROSS-ORIGIN IFRAME f${fid}${shell.title ? ` "${shell.title}"` : ''}${host ? ` (${host})` : ''} — ` +
              `${lines.length} of ${raw.length} element(s) shown; act with ref f${fid}:N]\n` + lines.join('\n') +
              (frameHidden > 0
                ? `\n... +${frameHidden} more element(s) in this frame not shown (capped at ${FRAME_CAP}; ` +
                  `form fields and buttons were prioritized, but if your target isn't listed it may be ` +
                  `further down inside the frame — scroll within it or act on a more specific region).`
                : '');
    }
  }
  _frameShells.set(tabId, offsets);
  return text;
}

// --------------------- WebMCP: tools the PAGE declares ---------------------
// A page that registers WebMCP tools has described its own capabilities, with a
// name, a description and a JSON Schema. That is strictly better than anything
// we can infer from its markup, and it is the one capability unavailable to every
// Playwright/CDP-launcher agent: WebMCP does not support headless browsing, while
// ChromeBridge is an MV3 extension in the user's real, logged-in Chrome — exactly
// the client the standard targets. Chrome's own model-context-tool-inspector
// extension is the existence proof that an extension can enumerate and invoke
// these.
//
// MAIN world, not a content script: content scripts run isolated, and the spec
// gates visibility with an `exposedTo` origin list. `runInTab` already injects
// with world:"MAIN".
//
// Feature-detected and degrading to `supported:false`, so this costs nothing on
// the ~100% of today's pages that declare nothing. `document.modelContext` is the
// current surface; `navigator.modelContext` was deprecated in Chrome 150 and is
// checked second so an older build still answers.
async function _pageToolsPage() {
  const mc = (typeof document !== 'undefined' && document.modelContext) ||
             (typeof navigator !== 'undefined' && navigator.modelContext) || null;
  if (!mc || typeof mc.getTools !== 'function') return { supported: false, tools: [] };
  let raw = [];
  try { raw = (await mc.getTools()) || []; } catch (e) {
    return { supported: true, error: String((e && e.message) || e), tools: [] };
  }
  const tools = [];
  for (const t of raw) {
    if (!t || !t.name) continue;
    // getTools() returns inputSchema as a JSON STRING; parse it so the agent gets
    // a schema rather than an escaped blob it has to unpack itself.
    let schema = t.inputSchema;
    if (typeof schema === 'string') { try { schema = JSON.parse(schema); } catch (e) {} }
    tools.push({
      name: String(t.name),
      description: String(t.description || ''),
      inputSchema: schema || null,
      // readOnlyHint === false marks a MUTATING tool. This is the declared
      // destructiveness signal that #24 deleted the submit wordlists for lacking:
      // the page saying so itself, with no vocabulary involved.
      // untrustedContentHint marks page-supplied content as a prompt-injection
      // risk, the same posture the side panel already takes toward tab titles.
      annotations: t.annotations || null,
      origin: String(t.origin || (typeof location !== 'undefined' ? location.origin : '')),
    });
  }
  return { supported: true, tools };
}

async function _callPageToolPage(name, argsJson) {
  const mc = (typeof document !== 'undefined' && document.modelContext) ||
             (typeof navigator !== 'undefined' && navigator.modelContext) || null;
  if (!mc || typeof mc.getTools !== 'function') {
    return { ok: false, error: 'this page declares no WebMCP tools (document.modelContext is unavailable here)' };
  }
  let raw = [];
  try { raw = (await mc.getTools()) || []; } catch (e) {
    return { ok: false, error: String((e && e.message) || e) };
  }
  const t = raw.find((x) => x && x.name === name);
  if (!t) {
    // Name the alternatives rather than just refusing — the same rule the submit
    // picker follows when it cannot resolve a single candidate.
    return { ok: false, error: 'no tool named ' + JSON.stringify(String(name)),
             available: raw.map((x) => x && x.name).filter(Boolean) };
  }
  try {
    const res = await mc.executeTool(t, typeof argsJson === 'string' ? argsJson : JSON.stringify(argsJson || {}));
    return { ok: true,
             // executeTool resolves null on navigation, which is a real outcome
             // (the tool worked and moved the page) and not an error.
             navigated: res === null || res === undefined,
             result: (res === null || res === undefined) ? '' : String(res),
             readOnly: !!(t.annotations && t.annotations.readOnlyHint) };
  } catch (e) {
    return { ok: false, error: String((e && e.message) || e) };
  }
}

function _domTextPage(scopeMmid) {
  // SCOPED TEXT. The structured listing only ever contains INTERACTIVE elements,
  // so a table's 195 data cells, a <pre> code block and a Wolfram result pod were
  // all unreachable by ref — three independent live agents hit this from three
  // directions and every one of them had to fall back to javascript_tool. Reading
  // ONE region's text closes it without inventing a new element model: scope to
  // the region you already found, get its text. Whole-document extras (outline,
  // iframe harvest, alt-text appendix) are deliberately skipped when scoped —
  // appending page-level facts to a deliberately narrowed read is the bug that
  // sent a whole Wikipedia main page back with a one-image scoped result.
  let _scopeEl = null;
  if (scopeMmid) {
    try {
      _scopeEl = (window.__mmidReg && window.__mmidReg.get(String(scopeMmid))) ||
                 document.querySelector(`[mmid='${String(scopeMmid).replace(/'/g, "")}']`);
    } catch (e) {}
    if (!_scopeEl) return "__SCOPE_MISS__" + String(scopeMmid);
  }
  const sel = ['#agentDriveAutoOverlay', '#tawebagent-overlay'];
  // Shadow-piercing query. innerText is layout-based so it already includes
  // shadow content, but querySelectorAll does not — which left the DOCUMENT
  // OUTLINE and the alt-text harvest empty on exactly the web-component pages
  // (Lit/Shoelace/Ionic) where the flat text dump is hardest to navigate.
  // Same-origin FRAMES are deliberately not pierced here: their text is already
  // appended below under an explicit [iframe "..."] label, and folding their
  // headings into the host page's outline would misrepresent the structure.
  const deepQuery = (q) => {
    const res = [];
    const walk = (root) => {
      let all;
      try { all = root.querySelectorAll('*'); } catch (e) { return; }
      for (const el of all) {
        try { if (el.matches(q)) res.push(el); } catch (e) {}
        if (el.shadowRoot) walk(el.shadowRoot);
      }
    };
    walk(document);
    return res;
  };
  const saved = [];
  sel.forEach(s => document.querySelectorAll(s).forEach(el => {
    saved.push([el, el.style.visibility]); el.style.visibility = 'hidden';
  }));
  // HIDE EDITOR GUTTERS STRUCTURALLY, before innerText is read. Pattern-matching
  // runs of consecutive integers in the FLAT text cannot tell a line-number
  // gutter from a month calendar — the first version of this deleted all 31 days
  // — and gating on "does the page contain an editor" does not help on a page
  // that has both. Only the DOM knows which numbers live inside an editor.
  // innerText skips visibility:hidden subtrees, so hiding and restoring is exact.
  try {
    const hosts = new Set();
    document.querySelectorAll('.CodeMirror, .cm-editor, .monaco-editor, .ace_editor')
      .forEach(n => hosts.add(n));
    // Structurally-detected editors too (a suppressed textarea's nearest sizeable
    // ancestor), so this is not limited to libraries we can name.
    document.querySelectorAll('textarea').forEach(ta => {
      try {
        const r = ta.getBoundingClientRect(), c = getComputedStyle(ta);
        const hidden = r.width <= 4 || r.height <= 4 || parseFloat(c.opacity || '1') === 0 ||
                       c.visibility === 'hidden' || (parseInt(c.zIndex, 10) || 0) < 0;
        if (!hidden) return;
        let w = ta.parentElement;
        for (let d = 0; d < 5 && w; d++, w = w.parentElement) {
          const wr = w.getBoundingClientRect();
          if (wr.width >= 100 && wr.height >= 40) { hosts.add(w); break; }
        }
      } catch (e) {}
    });
    for (const host of hosts) {
      for (const g of host.querySelectorAll('*')) {
        const t = (g.innerText || '').trim();
        if (!t || !/^\d[\d\s]*$/.test(t)) continue;
        const nums = t.split(/\s+/).map(Number);
        if (nums.length < 2) continue;
        let seq = true;
        for (let i = 1; i < nums.length; i++) if (nums[i] !== nums[0] + i) { seq = false; break; }
        if (!seq) continue;
        saved.push([g, g.style.visibility]);
        g.style.visibility = 'hidden';
        break;                       // one gutter column per editor
      }
    }
  } catch (e) {}
  // COLLAPSED PANELS ARE NOT VISIBLE TEXT. innerText skips display:none and
  // visibility:hidden, but NOT a panel collapsed to ~1px with its content
  // overflowing hidden — the standard way a closed dropdown/accordion parks its
  // markup. checkVisibility() calls those elements visible, so nothing upstream
  // catches them either. Measured on a HuggingFace model card: ~2,300 chars of
  // install snippets from a CLOSED "Use this model" menu came back as page text,
  // and a live agent answered the question with code that is not on the card.
  // Reuse the same hide-read-restore mechanism the gutter strip uses. Walking
  // top-down and NOT descending into a collapsed subtree keeps this O(visible
  // nodes); the text-length floor keeps ordinary 1px spacers out of `saved`.
  try {
    const hideCollapsed = (root, depth) => {
      if (depth > 12 || !root.children) return;
      for (const n of root.children) {
        let r;
        try { r = n.getBoundingClientRect(); } catch (e) { continue; }
        // A GENUINELY COLLAPSED panel has a non-zero but sub-pixel dimension: a
        // closed dropdown parked at ~1px with its content overflowing hidden.
        // An element measuring EXACTLY 0x0 is a different thing entirely — it
        // generates no box of its own (display:contents, or children that are
        // positioned/floated) while its children paint normally.
        //
        // Treating those the same deleted MDN's entire article: <main
        // class="layout__content"> measures 0x0 and holds 31,302 chars, so
        // get_page_text returned 4.8k of sidebar navigation and a confident
        // outline with no prose at all — the silent-omission class this project
        // exists to prevent, introduced by the fix for the opposite problem.
        const slim = (r.width > 0 && r.width < 2) || (r.height > 0 && r.height < 2);
        if (slim && (n.textContent || '').trim().length > 20) {
          saved.push([n, n.style.visibility]);
          n.style.visibility = 'hidden';
          continue;                  // whole subtree is unreadable; do not descend
        }
        // Descend through boxless containers too — their children may well paint.
        hideCollapsed(n, depth + 1);
      }
    };
    if (document.body) hideCollapsed(document.body, 0);
  } catch (e) {}
  if (_scopeEl) {
    let _st = "";
    // TABLES KEEP THEIR GRID. innerText flattens a table into a run of cells with
    // nothing that says which COLUMN a value came from, so the row/column
    // association — the entire content of a table — was lost in the one tool that
    // could reach the data at all. CLAUDE.md #14: a scoped read of a table
    // returned 8 column headers and ZERO data rows, and three separate live
    // agents fell back to javascript_tool from three different directions.
    //
    // Rendered as aligned rows instead, with the header taken from <th> — the
    // DOCUMENT declaring its own column names rather than a heuristic guessing
    // them, which is the same "answer only from what the page declares" rule the
    // submit picker was rewritten around in #24. Tables without <th> still get
    // their grid, just unnamed.
    //
    // HIDE-READ-RESTORE, the mechanism already used here for editor gutters and
    // collapsed panels: the tables are hidden BEFORE innerText so the prose read
    // does not contain them, then re-rendered and appended. Appending without
    // hiding emitted every cell twice, which doubles the cost of the one region
    // the caller explicitly asked for.
    const _tbls = [];
    try {
      if (_scopeEl.tagName === 'TABLE') _tbls.push(_scopeEl);
      _scopeEl.querySelectorAll('table').forEach((t) => { if (_tbls.indexOf(t) < 0) _tbls.push(t); });
    } catch (e) {}
    try {
      for (const t of _tbls) { saved.push([t, t.style.visibility]); t.style.visibility = 'hidden'; }
    } catch (e) {}
    // When the scope IS the table there is no prose to read, and reading it
    // anyway produced garbage: innerText is '' for the hidden subtree, so the
    // textContent fallback fired and returned every cell concatenated with no
    // separators at all — "RegionQ1North1,240東京2,300" — directly above a clean
    // grid of the same data. The fallback is right for a scope that genuinely
    // does not render; it is wrong for one we hid ourselves.
    const _scopeIsTable = _tbls.indexOf(_scopeEl) >= 0;
    if (!_scopeIsTable) {
      try { _st = (_scopeEl.innerText || _scopeEl.textContent || "").trim(); } catch (e) {}
    }
    // Un-hide before reading cells: innerText returns '' for a visibility:hidden
    // subtree, so building the grid while still hidden would emit an empty one —
    // and falling back to textContent instead would leak genuinely hidden cells.
    // `saved` still holds these nodes, so the restore at the end is idempotent.
    try {
      for (const t of _tbls) {
        const s = saved.find((p) => p[0] === t);
        t.style.visibility = s ? s[1] : '';
      }
    } catch (e) {}
    try {
      // A CELL'S TEXT MUST NOT BE ABLE TO INVENT COLUMNS. Hacker News' subtext row
      // holds two cells, the second reading "47 points by x 1 hour ago | hide |
      // 5 comments" with literal pipes, and it rendered as five fields in a table
      // declared to have three columns. Escaped, markdown-style.
      const _cell = (c) => ((c.innerText || c.textContent || '')
        .replace(/\s+/g, ' ').trim().replace(/\|/g, '\\|'));
      const _grids = [];
      for (const t of _tbls.slice(0, 5)) {
        let trs = [];
        try {
          // ONLY THIS TABLE'S OWN ROWS. querySelectorAll('tr') descends into nested
          // tables, which is how a Wikipedia "multiple issues" banner with one real
          // row but three nested tables was counted as 4 rows and promoted to a
          // data table, and how the hint's row count came to disagree with the
          // rendered one on four of five sites.
          trs = Array.from(t.querySelectorAll('tr')).filter((r) => {
            try { return r.closest('table') === t; } catch (e) { return true; }
          });
        } catch (e) {}
        // SPAN EXPANSION. colspan/rowspan were previously ignored and the row
        // right-padded instead, which is not "slightly off" — it silently
        // fabricates records. Measured on Wikipedia's Comparison_of_web_browsers:
        // `Latest release` carries colspan=2, so the header was offset from column
        // 6 for all 207 rows (asking Amaya's License returned its release DATE),
        // and 144 rows of rowspan continuations shifted left, yielding a browser
        // named "iOS" whose Developer was "4.9.0[5]". Tidy, plausible, false —
        // and certified by a `--- | --- |` separator. This is the standard grid
        // algorithm: a cell claims colspan columns on this row, and reserves them
        // on the next rowspan-1 rows.
        const grid = [];
        const carry = [];        // column -> { text, left }
        for (const tr of trs) {
          let cells = [];
          try { cells = Array.from(tr.children).filter((c) => /^(TD|TH)$/.test(c.tagName)); } catch (e) {}
          if (!cells.length) continue;
          const row = [];
          const place = (col, text) => { while (row.length < col) row.push(''); row[col] = text; };
          let col = 0;
          const nextFree = () => { while (carry[col] && carry[col].left > 0) { place(col, carry[col].text); col++; } return col; };
          let allTh = true;
          for (const c of cells) {
            if (c.tagName !== 'TH') allTh = false;
            col = nextFree();
            let cs = 1, rs = 1;
            try { cs = Math.min(50, Math.max(1, parseInt(c.getAttribute('colspan') || '1', 10) || 1)); } catch (e) {}
            try { rs = Math.min(200, Math.max(1, parseInt(c.getAttribute('rowspan') || '1', 10) || 1)); } catch (e) {}
            const txt = _cell(c);
            for (let k = 0; k < cs; k++) {
              place(col + k, txt);
              if (rs > 1) carry[col + k] = { text: txt, left: rs - 1 };
            }
            col += cs;
          }
          nextFree();            // trailing carried columns
          for (let i = 0; i < carry.length; i++) if (carry[i] && carry[i].left > 0) carry[i].left--;
          // A HEADER ROW IS NOT "CONTAINS A TH". A navbox title bar is a single
          // <th colspan=2>, and calling it a header printed `--- | ---` over a
          // title padded with an empty column — a separator promising column
          // semantics that the row does not have.
          let inHead = false;
          try { inHead = !!(tr.closest && tr.closest('thead')); } catch (e) {}
          grid.push({ head: (inHead || allTh) && cells.length >= 2, vals: row });
        }
        if (grid.length < 2) continue;   // not a data grid worth re-rendering
        const wide = grid.reduce((m, r) => Math.max(m, r.vals.length), 0);
        // THE GRID KEPT THE COLUMNS AND DROPPED THE TREE. Three independent live
        // agents called this the highest-risk thing they hit. The Fed's H.15 page
        // has TWO rows labelled `1-year` — 3.82 under "Treasury bills (secondary
        // market)" and 3.99 under "Treasury constant maturities" — and the source
        // conveys that parentage by indentation, which the render discarded. Section
        // headers arrived as ordinary rows with empty cells, so nothing distinguished
        // a group header from a data row with missing values, and picking the wrong
        // `1-year` gives a confidently wrong number that looks perfectly defensible.
        //
        // The rule is structural, not a class or style read: a row with exactly ONE
        // non-empty cell in a table that has three or more columns is not a data row,
        // it is a heading for the rows beneath it. Marked as such, and its followers
        // indented, so row grouping survives alongside column association.
        const out = grid.map((r) => {
          const v = r.vals.slice();
          for (let i = 0; i < wide; i++) if (v[i] === undefined) v[i] = '';
          const filled = v.filter((x) => x !== '').length;
          // MARK THE HEADING, DO NOT GUESS THE DEPTH. Indenting the rows that
          // follow a section looked tidier and asserted something the render cannot
          // know: on the Fed's H.15 page it put "Bank prime loan" under
          // "[section] Financial" when it is a top-level instrument, because the
          // indent flag has no way to learn where a section ENDS. The source encodes
          // that with `class="stub in3"`, and reading a class to infer meaning is the
          // author-habit guessing this whole pass removed. The marker alone
          // disambiguates the two `1-year` rows -- read up to the nearest preceding
          // [section] -- without claiming a nesting level.
          if (wide >= 3 && filled === 1 && !r.head) {
            return '  [section] ' + v.find((x) => x !== '');
          }
          return '  ' + v.join(' | ');
        });
        const hi = grid.findIndex((r) => r.head);
        if (hi >= 0) out.splice(hi + 1, 0, '  ' + Array(wide).fill('---').join(' | '));
        // THE <caption> IS THE TABLE'S OWN TITLE, AND IT CARRIES THE UNIT. Dropping
        // it was the highest-severity finding of the table audit: Wikipedia's GDP
        // table captions itself "GDP forecast or estimate (million US$) by country",
        // and the render began straight at the column headers — so an agent reads
        // `United States | 32,383,920` with nothing anywhere saying millions. A
        // 10^6 error with no signal, in the one view built for reading numbers.
        // The element is declared for exactly this purpose (HTML: "the caption
        // element represents the caption of its parent table"), so there is nothing
        // to infer.
        let _cap = '';
        try {
          const cn = t.querySelector && t.querySelector('caption');
          if (cn && (cn.closest && cn.closest('table')) === t) {
            const ct = ((cn.innerText != null ? cn.innerText : cn.textContent) || '')
              .replace(/\s+/g, ' ').trim();
            if (ct) _cap = '\n  [caption] ' + ct;
          }
        } catch (e) {}
        _grids.push(`--- TABLE (${grid.length} row(s) x ${wide} column(s)) ---${_cap}\n` + out.join('\n'));
      }
      if (_grids.length) _st = (_st ? _st + '\n\n' : '') + _grids.join('\n\n');
      // Skipping the prose read is only correct when a grid REPLACES it. A table
      // below the 2-row grid threshold produced neither: scoping to a one-row
      // table returned "(this region contains no text)" for a region that plainly
      // contains text. Caught by a fixture whose assertion (no grid emitted) was
      // still passing — the check was right and incomplete, so it now asserts the
      // content too.
      else if (_scopeIsTable) {
        try { _st = (_scopeEl.innerText || '').trim(); } catch (e) {}
      }
    } catch (e) {}
    try { saved.forEach(([n, v]) => { n.style.visibility = v; }); } catch (e) {}
    return _st || "(this region contains no text)";
  }
  let text = (document.body && document.body.innerText) || document.documentElement.innerText || "";
  // SHADOW DOM. innerText does NOT cross shadow boundaries, so every web-component
  // page returned only its light-DOM text — silently. Measured on MDN: 79 shadow
  // hosts holding 77,669 chars while body.innerText saw 12,030, which is why an
  // agent reported "get_page_text deletes all code blocks" and concluded the page
  // had no examples. The COLLECTOR has crossed shadow roots for a long time; this
  // tool never did, so the two disagreed about what the page contains.
  //
  // Appended per host in document order rather than interleaved: exact positional
  // splicing would need a full composed-tree text layout, and recovering the
  // content attributed to its host beats losing it. Slotted light-DOM content is
  // already in the base text, so only shadow-ONLY text is added.
  try {
    const seen = text;
    const parts = [];
    const visit = (root, depth) => {
      if (depth > 6) return;
      let els;
      try { els = root.querySelectorAll('*'); } catch (e) { return; }
      for (const el of els) {
        if (!el.shadowRoot) continue;
      // The light-DOM path filters hidden content; this one did not, so a CLOSED
      // dialog's text was reported inside "complete visible text" while
      // read_page correctly raised no modal banner — the two halves of one tool
      // contradicting each other.
      try { if (el.checkVisibility && !el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) continue; } catch (e) {}
      try { const _r = el.getBoundingClientRect(); if (_r.width < 1 || _r.height < 1) continue; } catch (e) {}
        let t = '';
        try {
          t = Array.from(el.shadowRoot.children)
                .map((c) => (c.innerText || '').trim()).filter(Boolean).join('\n').trim();
        } catch (e) {}
        // Skip what the base text already covers (slotted content) and noise.
        //
        // The noise gate was `t.length > 8`, a chosen number, and short shadow-only
        // text is exactly the case worth keeping: a vote count, a price, a
        // timestamp, a badge — the shortest strings on the page are often the
        // ANSWER. Replaced with the question the number was approximating: does
        // this text contain a letter or a digit, in any script? An icon-font glyph
        // sits in the Private Use Area (category Co) and pure punctuation is P/S,
        // so neither passes, while "1,204" and "3 日前" both do. No length, no
        // vocabulary, no script assumption. Repetition is already handled by the
        // indexOf check beside it.
        if (t && /[\p{L}\p{N}]/u.test(t) && seen.indexOf(t.slice(0, 40)) === -1) {
          // TAG first: an id of 'wa-dialog' on an <sl-dialog> named a component that
          // does not exist in the document, in a list where every other entry is a
          // tag name. aria-label is a real name; an id is not.
          const who = el.tagName.toLowerCase()
            + ((el.getAttribute && el.getAttribute('aria-label'))
                ? ' "' + el.getAttribute('aria-label') + '"' : '');
          parts.push(`[${who}] ${t}`);
        }
        visit(el.shadowRoot, depth + 1);
      }
    };
    visit(document, 0);
    if (parts.length) {
      text += `\n\n--- TEXT INSIDE WEB COMPONENTS (shadow DOM; ${parts.length} component(s)) ---\n`
            + parts.join('\n\n');
    }
  } catch (e) {}
  // Same-origin iframes (embedded result panes, editors, legacy widgets) hold
  // real page content the agent otherwise can't read — append it, labeled.
  const harvestFrames = (doc, depth) => {
    if (depth > 3) return;
    // Shadow-aware: _walkInject recurses shadowRoot -> iframe, so a same-origin
    // frame inside a web component is collected structurally but its TEXT was
    // missing here — the two tools disagreeing about the same frame.
    (doc === document ? deepQuery('iframe,frame') : Array.from(doc.querySelectorAll('iframe,frame'))).forEach(f => {
      try {
        const d = f.contentDocument;
        if (d && d.body) {
          const t = (d.body.innerText || '').trim();
          if (t) text += `\n[iframe "${f.title || f.id || f.name || ''}"]: ` + t;
          harvestFrames(d, depth + 1);
        }
      } catch (e) {}
    });
  };
  try { harvestFrames(document, 0); } catch (e) {}
  const alts = deepQuery('img').map(i => i.alt).filter(Boolean).join(' ');
  saved.forEach(([el, v]) => el.style.visibility = v);
  // DOCUMENT OUTLINE — innerText discards ALL hierarchy, so a question like
  // "how many top-level sections does this article have?" is unanswerable from
  // the text dump: a nested subsection reads exactly like a top-level one.
  // Benchmarked twice on a Wikipedia TOC, where the agent had to fall back to
  // reading pixel indentation off a screenshot to avoid over-counting.
  // Emitting depth-tagged headings answers it directly and costs a few lines.
  let outline = '';
  try {
    const hs = deepQuery('h1,h2,h3,h4,h5,h6,[role="heading"]')
      .filter(h => { try { const r = h.getBoundingClientRect(); return r.width > 0 && r.height > 0; } catch (e) { return false; } })
      // An OUTLINE describes the DOCUMENT, not the page chrome. Headings inside
      // navigation landmarks are widget titles, not sections — Wikipedia's TOC
      // sidebar contributes an <h2>Contents</h2> from inside NAV#mw-panel-toc,
      // which inflated this article's top-level count from 11 to 12 (verified:
      // "Contents".closest('nav') is truthy, "History".closest('nav') is not).
      // banner/contentinfo excluded for the same reason; <aside>/complementary
      // deliberately KEPT, since real content legitimately lives there.
      // IMPLICIT landmarks too. Excluding only the ROLE forms let three plain
      // <footer><h3> link-column titles ("Products", "Company", "Resources")
      // count as document sections — the exact Wikipedia-TOC over-count this
      // filter exists to prevent.
      .filter(h => { try { return !h.closest('nav,header,footer,[role="navigation"],[role="banner"],[role="contentinfo"]'); } catch (e) { return true; } })
      // sr-only headings are 1x1 clip boxes and are not part of the visible outline.
      .filter(h => { try { const r = h.getBoundingClientRect(); return r.width > 4 && r.height > 4; } catch (e) { return false; } });
    const lines = [];
    for (const h of hs.slice(0, 120)) {
      const lvl = /^H([1-6])$/.test(h.tagName)
        ? parseInt(h.tagName.slice(1), 10)
        : Math.min(6, Math.max(1, parseInt(h.getAttribute('aria-level') || '2', 10)));
      // Strip the permalink glyph doc generators append to every heading
      // (MkDocs/Sphinx use "¶", many others "#", some a link glyph) — it is
      // anchor chrome, not part of the section name, and it would leak into any
      // comparison the agent makes against a TOC entry or a user-supplied name.
      // ¶ and § are unambiguous permalink glyphs. A trailing '#' is NOT: it is part
      // of the name in "C#", "F#", "Issue #". Strip it only on structural evidence —
      // the heading contains an in-page anchor, i.e. a real permalink affordance.
      // Remove the ANCHOR'S OWN TEXT rather than regex-stripping trailing '#'. The old
      // rule ate the '#' from "Working with C#" on any Docusaurus page, because such
      // pages BOTH contain a hash-link and legitimately end a heading in '#' — the exact
      // ambiguity it was supposed to resolve.
      let t = (h.innerText || '');
      try {
        const a = h.querySelector('a[href^="#"]');
        const at = a && (a.innerText || '').trim();
        if (at && at.length <= 2 && t.trimEnd().endsWith(at)) {
          t = t.trimEnd().slice(0, -at.length);
        }
      } catch (e) {}
      t = t.replace(/\s+/g, ' ').replace(/\s*[¶§]+\s*$/, '');
      t = t.trim().slice(0, 80);
      if (t) lines.push(`${'  '.repeat(lvl - 1)}h${lvl}: ${t}`);
    }
    if (lines.length) {
      outline = `\n\n--- DOCUMENT OUTLINE (${lines.length} headings; indent = nesting depth, h1/h2 are top-level sections) ---\n` + lines.join('\n');
    }
  } catch (e) {}
  // Editor line-number gutters land in innerText as a run of bare numeric lines.
  // read_page strips them from a code editor's value; get_page_text did not, so
  // the two tools disagreed about the same editor and only the structured one was
  // clean. Same structural rule: a run of >=3 consecutive integers, each alone on
  // its line, is a gutter — ordinary prose does not do that.
  return text + " Other Alt Texts in the page: " + alts + outline;
}

function _collectInteractivePage(structured, scopeMmid, detail, ledger, geometry, format) {
  // DROP LEDGER. The collector could not explain its own omissions: ~17 bare
  // `return`s in the element loop and four destructive post-passes removed
  // elements with no record of which rule fired. Every investigation therefore
  // cost an ablation run or a live-agent study — and most recently six DOM-
  // mutation probes plus two invalid diagnostics to discover that three
  // out-of-sample misses were all one rule (container suppression).
  //
  // Opt-in and near-free when off: `_drop` short-circuits on the flag, so the
  // normal path pays one boolean test per drop.
  const LEDGER = !!ledger;
  const _ledger = [];
  // STATEFUL DROP COUNTERS — always on, unlike the ledger. `aria-hidden` and
  // `inert` are not properties of the page, they are properties of the page's
  // CURRENT STATE: a library sets them on everything behind an open menu or
  // dialog and clears them when it closes. Dropping those elements is right;
  // reporting the remainder as if it were the page is not.
  // Measured live on Google Flights: a listbox left open marked the rest of the
  // document aria-hidden, and read_page answered "Visible interactive elements
  // (2 on screen)" for a page holding 39 buttons — same wording, same
  // confidence, as a true count of 2. Reproduced in a fixture: 7 dropped, 2
  // reported, no signal. The collector already knew; it just never said.
  const _stateDrops = { 'aria-hidden': 0, inert: 0, 'aria-hidden-named': 0 };
  // Record what a heuristic WOULD have removed, without removing it. Keeps the
  // drop-ledger's explanatory power while making membership spec-decided only.
  // A heuristic's verdict becomes a PROMINENCE mark, not a delete. The element
  // keeps its ref and stays actionable; the serializer sends it last, compacted.
  // element -> the FIRST rule that judged it decoration, this run only.
  const _demotedRun = new Map();
  const _note = (el, rule) => {
    // FIRST REASON WINS, AND IT IS RECORDED ONCE.
    //
    // This used to overwrite `__abDemoted` and append a ledger entry every time,
    // so an element judged decoration by two rules produced TWO ledger entries
    // and ONE listing row carrying the LAST rule's name. Measured live on
    // react-select.com: the ledger header said "55 element(s) kept (42 of them
    // DEMOTED)" while the decoration tier named exactly 30 refs, and 12 of those
    // 30 were labelled `generic-no-label` when the ledger's own count attributed
    // them to `decorative-svg`. 42 - 30 = 12, the elements demoted twice. The two
    // halves of the same diagnostic were wrong in opposite directions.
    //
    // Keeping the FIRST reason also keeps the more specific one: `decorative-svg`
    // fires before the generic no-label sweep, and "it is a decorative svg" tells
    // the reader more than "it has no label".
    // PER RUN, not per element lifetime. `__abDemoted` was an expando on the DOM
    // node, so it survived between collector runs: a second read of the same page
    // hit this guard, recorded nothing in the ledger, and reported a reason decided
    // by an EARLIER read even if this one would not have demoted the element at
    // all. A Map scoped to this call is the correct lifetime, and it removes the
    // cross-run leak that existed before the guard did.
    if (_demotedRun.has(el)) return;
    try { _demotedRun.set(el, rule); } catch (e) { return; }
    if (LEDGER) { try { _drop(el, rule); } catch (e) {} }
  };
  const _drop = (el, rule) => {
    if (rule in _stateDrops) _stateDrops[rule]++;
    if (LEDGER) {
      try {
        const r = el.getBoundingClientRect();
        _ledger.push({
          mmid: el.getAttribute && el.getAttribute('mmid'), rule,
          tag: (el.tagName || '').toLowerCase(),
          role: (el.getAttribute && el.getAttribute('role')) || null,
          text: (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60),
          w: Math.round(r.width), h: Math.round(r.height),
        });
      } catch (e) {}
    }
    return undefined;          // callers use `return _drop(...)` to exit the callback
  };
  // Post-passes remove by mmid from the output array rather than by element.
  const _dropMmids = (mmids, rule) => {
    if (!LEDGER) return;
    try {
      for (const m of mmids) {
        const el = mmidReg && mmidReg.get ? mmidReg.get(String(m)) : null;
        if (el) _drop(el, rule);
        else _ledger.push({ mmid: m, rule, tag: null, role: null, text: '', w: 0, h: 0 });
      }
    } catch (e) {}
  };
  // Post-pass demotion, carrying `_note`'s FIRST-REASON-WINS rule over to the
  // passes that judge finished ENTRIES rather than elements mid-walk (same-box
  // twins, delegation roots, container suppression). They run in sequence and
  // can each judge the same element; without this the ledger records one `was:`
  // entry per pass for a single listing row, which is precisely the double-count
  // that once had the ledger's header claiming 42 demotions while the decoration
  // tier named 30. Takes the array as a parameter because `out` is declared
  // further down this function.
  const _noteEntries = (arr, mmids, rule) => {
    const fresh = new Set();
    for (const e of arr) {
      if (mmids.has(e.mmid) && !e.demoted) { e.demoted = rule; fresh.add(e.mmid); }
    }
    _dropMmids(fresh, rule);
  };
  // DETAIL LEVELS. `compact` (default) is what every observation gets: identity,
  // state and geometry, with URLs and media deliberately absent. `full` adds the
  // fields that are structurally missing from a compact listing — href, src, and
  // the page's visible media — and is meant to be used WITH ref_id, so the cost
  // is bounded by the region the agent has already narrowed to.
  //
  // Why not just always include them: measured on the corpus, URLs alone add
  // 5.9 KB on Hacker News and 8.7 KB on Amazon — more than tripling Amazon's
  // listing. An agent observes dozens of times per task and needs a URL in a
  // small minority of them, so paying for it by default costs far more than the
  // occasional extra round trip. Reading the attributes is free (getAttribute,
  // no layout); the entire cost of `full` is model input tokens.
  const FULL = detail === 'full';
  // BRIEF: a third point on the rate/retention curve. MEASURED decomposition of
  // what `full` costs over `compact` across 22 frozen sites: +79% chars, of which
  // 91% sits INSIDE href=/src= strings — not in the extra media rows. So the
  // expensive part is URL verbosity, and most of that verbosity carries no
  // information for the agent: the scheme and host repeat on every same-origin
  // link, and query strings are dominated by tracking parameters.
  //
  // `brief` keeps what identifies the destination (host when it differs, path,
  // short query/hash) and drops what does not. A path is resolvable against the
  // page origin, so it is genuinely sufficient to navigate.
  const BRIEF = detail === 'brief';
  const WANT_URLS = FULL || BRIEF;
  const _briefUrl = (u) => {
    const raw = String(u || '');
    if (!raw || raw.slice(0, 5) === 'data:') return raw;   // data: already summarised
    try {
      const a = new URL(raw, location.href);
      if (a.protocol !== 'http:' && a.protocol !== 'https:') return raw;
      let out = a.origin === location.origin ? a.pathname : (a.host + a.pathname);
      if (a.search) {
        if (a.search.length <= 24) out += a.search;
        else {
          const first = a.search.slice(1).split('&')[0];
          out += first && first.length <= 40 ? '?' + first + '&…' : '?…';
        }
      }
      if (a.hash && a.hash.length <= 16) out += a.hash;
      return out || '/';
    } catch (e) { return raw; }
  };
  // Stable, additive mmid injection (see _ensureMmidsPage for rationale).
  // Existing mmids survive across observations and re-renders; only fresh
  // nodes get new high-numbered mmids. This keeps selectors stable during
  // mid-form re-renders (combobox picks, expanding sections).
  //
  // SHADOW DOM PIERCING: the walk recurses into OPEN shadow roots, so controls
  // inside web components (Lit/Stencil/Shoelace/ytd-*) are listed like any
  // other element. Closed roots stay unreachable (would need CDP pierce — rare,
  // mostly Salesforce LWC). Every walk also rebuilds window.__mmidReg
  // (mmid -> live element): document.querySelector can't see into shadow roots,
  // so the action functions resolve [mmid='N'] through this registry first.
  // NOTE: only true non-content tags here. ('main' and Google's 'c-wiz' were
  // once excluded — that denied mmids to a standard landmark and overfit to
  // one vendor; both removed. SVG internals are handled by decorativeTags.)
  const tags_to_ignore = ['head','style','script','link','meta','noscript','template','g','path'];
  const ids_to_ignore = ['agentDriveAutoOverlay'];
  if (typeof window.__mmidCounter !== 'number') window.__mmidCounter = 0;
  const mmidReg = new Map();   // mmid -> element, in composed-tree walk order
  const _walkInject = (root) => {
    root.querySelectorAll('*').forEach(el => {
      const tag = el.tagName.toLowerCase();
      if (!tags_to_ignore.includes(tag) && !ids_to_ignore.includes(el.id)) {
        if (!el.hasAttribute('mmid')) el.setAttribute('mmid', `${++window.__mmidCounter}`);
        mmidReg.set(el.getAttribute('mmid'), el);
      }
      if (el.shadowRoot) _walkInject(el.shadowRoot);
      // SAME-ORIGIN IFRAMES: contentDocument is reachable -> recurse like a
      // shadow root, so embedded same-origin apps (editors, legacy widgets,
      // srcdoc frames) are listed like any other page region. Cross-origin
      // frames return null / throw -> they stay opaque and are surfaced as a
      // single box in the listing instead.
      if (tag === 'iframe' || tag === 'frame') {
        try { if (el.contentDocument) _walkInject(el.contentDocument); } catch (e) {}
      }
    });
  };
  _walkInject(document);
  window.__mmidReg = mmidReg;
  // COMPOSED-TREE QUERY. document.querySelectorAll cannot see into shadow roots
  // or same-origin iframes, so every PAGE-LEVEL scan built on it was blind on
  // web-component apps: a <sl-dialog>/<ion-modal>/Lit dialog would open and the
  // modal banner never fired, no dialog text was extracted, and a Lit app's <h1>
  // produced no "Main heading" — even though the per-element walk (which uses
  // composedParent) correctly tagged those same controls section=dialog. The
  // registry IS the composed walk, in tree order, so filtering it gives the
  // shadow-piercing answer with no extra traversal.
  // Memoised: each call is a full pass over the registry running .matches(), and
  // the dialog selector alone is needed twice (modal detection, then dialog
  // text). On a 20k-element page that is a pass worth not repeating.
  const _acCache = new Map();
  const _allComposed = (sel) => {
    let hit = _acCache.get(sel);
    if (hit) return hit;
    hit = [];
    mmidReg.forEach((el) => { try { if (el.matches && el.matches(sel)) hit.push(el); } catch (e) {} });
    _acCache.set(sel, hit);
    return hit;
  };
  // Record WHICH DOCUMENT the agent has actually observed. Refs are only meaningful
  // against the document they were read from: __mmidCounter resets on navigation, so a
  // stale ref_23 silently resolves to whatever is 23rd on the NEW page. Stamped here
  // (observation) and not in _ensureMmidsPage, because fill_form injects internally and
  // would otherwise re-stamp the marker and hide exactly the mismatch we want to catch.
  try { window.__mmidObservedUrl = location.href; } catch (e) {}
  // Composed-tree parent: crosses shadow boundaries (shadow root -> host) AND
  // same-origin frame boundaries (frame document -> its <iframe> element) so
  // ancestor walks (section, modal, dedup, clipping) see through both.
  const composedParent = (n) => {
    if (n.parentElement) return n.parentElement;
    try {
      if (n.getRootNode && n.getRootNode().host) return n.getRootNode().host;
      const v = n.ownerDocument && n.ownerDocument.defaultView;
      if (v && v.frameElement) return v.frameElement;
    } catch (e) {}
    return null;
  };
  // Top-document viewport offset for elements inside same-origin iframes:
  // their rects are relative to their own frame's viewport, so accumulate the
  // frame elements' offsets (incl. border via clientLeft/Top — a bordered
  // iframe shifts its content). CDP trusted clicks need TOP-document CSS px.
  // Maps a point from an element's own frame coordinates into TOP-document CSS px,
  // accounting for any CSS transform on the frames along the way (see the same
  // fix in _rectForPage). Returns the accumulated scale so widths/heights can be
  // converted too — a listed box() must describe what the user actually sees.
  const framePoint = (el, x, y) => {
    let kx = 1, ky = 1;
    try {
      let w = el.ownerDocument ? el.ownerDocument.defaultView : null;
      while (w && w !== window && w.frameElement) {
        const fe = w.frameElement;
        const fr = fe.getBoundingClientRect();
        const ow = fe.offsetWidth || fr.width, oh = fe.offsetHeight || fr.height;
        const sx = ow ? fr.width / ow : 1, sy = oh ? fr.height / oh : 1;
        x = fr.left + (fe.clientLeft || 0) * sx + x * sx;
        y = fr.top + (fe.clientTop || 0) * sy + y * sy;
        kx *= sx; ky *= sy;
        w = w.parent;
      }
    } catch (e) {}
    return { x, y, kx, ky };
  };

  // CODE-EDITOR HOSTS, resolved ONCE for the whole walk.
  //
  // CodeMirror/Monaco/Ace render a styled text view over an input surface they
  // keep hidden. Neither layer looks like a control on its own, so unless the
  // HOST is recognised the agent is shown a plain <div> full of gutter digits
  // and never learns it can type there. The class list is a FAST PATH for the
  // three libraries we can name; the structural rule beneath it is what makes
  // this general.
  //
  // The shape of a code editor, stated without naming one: a VISUALLY SUPPRESSED
  // <textarea> (the real input) sitting inside an ancestor that is big enough to
  // be an editing surface, actually contains the textarea's position, and renders
  // monospaced or pre-formatted text. That catches renamed forks, in-house
  // editors and rebuilt Ace/Monaco bundles. Rich-text editors are contenteditable
  // and go down the ceRoot path instead, so requiring monospace/pre costs nothing
  // here and keeps ordinary hidden textareas (clipboard helpers, auto-grow shims,
  // honeypots) out.
  //
  // Three details all came from measuring Monaco with its class name ablated,
  // and each is the difference between a general rule and a rule that happens to
  // describe CodeMirror:
  //   - "suppressed" is not "zero-sized". Monaco's .inputarea is 147x48 with
  //     color:transparent and z-index:-10 — invisible because its text does not
  //     paint and it sits behind the render layer, which is the other standard
  //     way to keep an input focusable and form-serialisable while hiding it.
  //   - the monospace evidence is on DESCENDANTS. Monaco's host computes
  //     font-family:-apple-system and white-space:normal; only the line elements
  //     deep inside are monospace/pre, so checking the host and its direct
  //     children finds nothing.
  //   - "readonly" alone does not disqualify. Monaco's mirror is readonly with an
  //     empty value; what identifies the copy-to-clipboard shim a static code
  //     block ships is that its value is a COPY of the text the host renders.
  const editorHosts = new Set();
  {
    try {
      _allComposed('.CodeMirror, .cm-editor, .monaco-editor, .ace_editor, [class*="mq-editable-field"]')
        .forEach(n => editorHosts.add(n));
    } catch (e) {}
    const LANDMARK = new Set(['BODY', 'HTML', 'MAIN', 'FORM', 'HEADER', 'FOOTER', 'NAV', 'ASIDE', 'SECTION', 'ARTICLE']);
    const monoOrPre = (n) => {
      try {
        // Never judge by a form control: Chrome's UA stylesheet gives every
        // <textarea> font-family:monospace, so asking the editor's own hidden
        // input whether it looks like code makes EVERY hidden textarea on the
        // web an editor — a comment box's autogrow shim included.
        if (['TEXTAREA', 'INPUT', 'SELECT', 'BUTTON'].includes(n.tagName)) return false;
        if (!(n.innerText || '').trim()) return false;   // styling with nothing rendered proves nothing
        const c = ((n.ownerDocument && n.ownerDocument.defaultView) || window).getComputedStyle(n);
        if (/^pre/.test(c.whiteSpace || '')) return true;
        // MEASURE MONOSPACE, DO NOT RECOGNISE FONT NAMES. This read
        // /mono|consol|courier|menlo|monaco|code/ against font-family, which is a
        // list of the fonts someone happened to think of: a site shipping "Berkeley
        // Mono" or "Fira Code" matches by luck, one shipping "Iosevka" or a
        // self-hosted `--font-editor` does not, and nothing about the failure is
        // visible. Monospace has an actual definition — every glyph advances the
        // same width — so measure it. General for any font, any name, any language,
        // and it cannot be wrong about a font it has never heard of.
        const _win = (n.ownerDocument && n.ownerDocument.defaultView) || window;
        const _doc = n.ownerDocument || document;
        const probe = _doc.createElement('span');
        probe.style.cssText = 'position:absolute;left:-9999px;top:0;visibility:hidden;white-space:pre;';
        probe.style.font = c.font || ((c.fontSize || '') + ' ' + (c.fontFamily || ''));
        (_doc.body || _doc.documentElement).appendChild(probe);
        let narrow = 0, wide = 0;
        try {
          probe.textContent = 'iiiiiiiiii';
          narrow = probe.getBoundingClientRect().width;
          probe.textContent = 'WWWWWWWWWW';
          wide = probe.getBoundingClientRect().width;
        } finally { probe.remove(); }
        return narrow > 0 && Math.abs(narrow - wide) / Math.max(narrow, wide) < 0.02;
      } catch (e) { return false; }
    };
    // Does this box RENDER code anywhere inside it? Two text-bearing monospace/pre
    // descendants, not one, so a lone inline <code> in prose is not an editor.
    // The scan is bounded — this runs once per suppressed textarea, not per element.
    const rendersCode = (host) => {
      if (monoOrPre(host)) return true;
      try {
        let seen = 0, hits = 0;
        for (const d of host.querySelectorAll('*')) {
          if (++seen > 200) break;
          if (monoOrPre(d) && ++hits >= 2) return true;
        }
      } catch (e) {}
      return false;
    };
    // Fully transparent colour, in any notation the engine may report.
    const _alpha0 = (c) => /^rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*0*(\.0+)?\s*\)$/.test(c || '');
    const alreadyInHost = (n) => { let w = n; while (w) { if (editorHosts.has(w)) return true; w = composedParent(w); } return false; };
    for (const ta of _allComposed('textarea')) {
      try {
        if (alreadyInHost(ta) || ta.disabled) continue;
        const tr = ta.getBoundingClientRect();
        const tcs = ((ta.ownerDocument && ta.ownerDocument.defaultView) || window).getComputedStyle(ta);
        const hiddenInput = tr.width <= 4 || tr.height <= 4 || parseFloat(tcs.opacity || '1') === 0 ||
                            tcs.visibility === 'hidden' || (tcs.clipPath && tcs.clipPath !== 'none') ||
                            _alpha0(tcs.color) ||                       // text does not paint
                            (parseInt(tcs.zIndex, 10) || 0) < 0;        // sits behind the render layer
        if (!hiddenInput) continue;             // a visible textarea IS the control
        // The copy-to-clipboard shim a static code block ships holds a COPY of
        // what the block renders; an editor's mirror holds a scratch buffer.
        const taVal = (ta.value || '').replace(/\s+/g, ' ').trim();
        const cx = tr.left + tr.width / 2, cy = tr.top + tr.height / 2;
        // Collect every qualifying ancestor, then choose. Editors nest their own
        // boxes (Monaco: .overflow-guard inside .monaco-editor, identical rects),
        // and taking the innermost listed the inner box while the outer one
        // survived as a second entry for the same visual editor. Prefer the
        // ancestor that declares an editor ARIA role — role=code/textbox is the
        // standard way to say "this region is the editor", and it is what makes
        // the structural result identical to the class-list one.
        let firstHost = null, ariaHost = null, shim = false;
        let w = composedParent(ta);
        for (let d = 0; d < 5 && w && w.nodeType === 1; d++, w = composedParent(w)) {
          if (LANDMARK.has(w.tagName)) break;
          const wr = w.getBoundingClientRect();
          if (wr.width < 100 || wr.height < 40) continue;
          // Once we've climbed past a box that no longer contains the input, we
          // are looking at page layout, not the editor.
          if (cx < wr.left - 2 || cx > wr.right + 2 || cy < wr.top - 2 || cy > wr.bottom + 2) break;
          if (!rendersCode(w)) continue;
          if (ta.readOnly && taVal &&
              (w.innerText || '').replace(/\s+/g, ' ').trim() === taVal) { shim = true; break; }
          if (!firstHost) firstHost = w;
          const _hr = (w.getAttribute('role') || '').toLowerCase();
          if (!ariaHost && (_hr === 'code' || _hr === 'textbox')) ariaHost = w;
        }
        if (!shim && (ariaHost || firstHost)) editorHosts.add(ariaHost || firstHost);
      } catch (e) {}
    }
  }
  // Line-number gutters. Once innerText is whitespace-collapsed, an editor's
  // text starts with the run "1 2 3 4 …" — that is how Monaco's value came back
  // as "1 2 3 4 // Type your code here". Strip it STRUCTURALLY: the run has to
  // be genuinely consecutive (and start at 1, unless it is long enough that a
  // scrolled gutter is the only sane reading), so ordinary content that happens
  // to begin with numbers survives untouched. No gutter class names involved.
  // Works on RAW innerText (before whitespace collapse), because the two ways a
  // gutter renders are only distinguishable by line breaks:
  //   COLUMN  — the numbers are their own element, so innerText emits the whole
  //             strip first, then the code: "1 / 2 / 3 / const a = 1;" one per
  //             line  (Monaco, Ace)
  //   INLINE  — each line carries its own number: "1const a = 1;" then
  //             "2const b = 2;"  (CodeMirror gutters, Prism line-numbers)
  // Both are stripped only on genuinely consecutive runs — and the inline form
  // additionally requires EVERY line to be numbered — so ordinary content that
  // happens to start with a number survives.
  const stripGutter = (raw) => {
    const NL = String.fromCharCode(10);
    const lines = String(raw || '').split(NL);
    if (lines.length < 2) return raw;
    const seq = (nums) => {
      for (let k = 1; k < nums.length; k++) if (nums[k] !== nums[0] + k) return false;
      return nums[0] === 1 || nums.length >= 4;
    };
    // Blank lines are ignored throughout: an editor styled white-space:pre keeps
    // the source indentation around its markup, so its innerText routinely opens
    // with an empty line and a naive "every line is numbered" test never fires.
    const idx = [];
    for (let k = 0; k < lines.length; k++) if (lines[k].trim()) idx.push(k);
    if (idx.length < 2) return raw;
    let i = 0;
    while (i < idx.length && /^\s*\d{1,6}\s*$/.test(lines[idx[i]])) i++;
    if (i >= 2 && i < idx.length && seq(idx.slice(0, i).map(k => parseInt(lines[k], 10)))) {
      return lines.slice(idx[i]).join(NL);
    }
    const m = idx.map(k => /^\s*(\d{1,6})(?=\D|$)/.exec(lines[k]));
    if (m.every(Boolean) && seq(m.map(x => parseInt(x[1], 10)))) {
      const kept = lines.slice();
      idx.forEach((k, q) => { kept[k] = lines[k].slice(m[q][0].length); });
      return kept.join(NL);
    }
    return raw;
  };

  // Nearest semantic section / container. Lets the model tell apart elements
  // that share a label but live in different parts of the page: a "Investor"
  // <button> inside a <thead> (column sort) vs a "Investor" input inside a
  // <dialog> (form field) are totally different things — without this signal
  // the agent was confusing them and hallucinating form structures from table
  // column headers.
  // True only for SEMANTIC tables — has <thead>, OR explicit role=table/grid,
  // OR uses <th> column headers. Old-school sites (HackerNews etc.) use <table>
  // for layout; we should NOT label every link there as "table-body".
  const _isSemanticTable = (tableEl) => {
    if (!tableEl) return false;
    if (tableEl.querySelector && tableEl.querySelector('thead')) return true;
    if (tableEl.querySelector && tableEl.querySelector('th')) return true;
    const r = tableEl.getAttribute && tableEl.getAttribute('role');
    if (r && ['table','grid','treegrid'].includes(r)) return true;
    return false;
  };
  const _bannerCache = new Map();   // ancestor -> is-overlay-banner (memo)
  const section = (el) => {
    // In-frame elements are tagged section=iframe REGARDLESS of landmarks
    // inside the frame's own document — "this lives in an embedded document"
    // is the signal the agent needs (a GrapesJS-edited page's <header> is the
    // CONTENT's header, not the host page's).
    try { if (el.ownerDocument !== document) return 'iframe'; } catch (e) {}
    let walker = el;
    while (walker && walker !== document.body && walker.tagName) {
      const tag = walker.tagName.toLowerCase();
      const role = walker.getAttribute ? walker.getAttribute('role') : null;
      // DIALOG WINS over the overlay-banner shape: a role=dialog/alertdialog
      // consent sheet anchored at the bottom is still a DIALOG — the modal
      // banner tells the agent to look for section=dialog, so emitting
      // overlay-banner for the same container was an instruction mismatch.
      if (tag === 'dialog' || role === 'dialog' || role === 'alertdialog' ||
          (walker.getAttribute && walker.getAttribute('aria-modal') === 'true')) {
        return 'dialog';
      }
      // Fixed full-width overlays anchored AWAY from the page top are
      // notification/consent banners — not page chrome, even when their markup
      // contains <header>/role=banner (IBM Carbon's cookie bar does). Telling
      // the agent section=header hid that it's a blocking layer to dismiss.
      {
        let isBanner = _bannerCache.get(walker);
        if (isBanner === undefined) {
          isBanner = false;
          try {
            const wcs = getComputedStyle(walker);
            if (wcs.position === 'fixed') {
              const wr = walker.getBoundingClientRect();
              isBanner = wr.width >= vw * 0.6 && wr.top > vh * 0.15 && wr.height < vh * 0.6;
              // A fixed bar that CONTAINS the page's main landmark, or a landmark of
              // its own, is page furniture, not an overlay laid on top of content.
              // Geometry alone matched Spotify's player bar, mobile-style bottom tab
              // bars, and sticky "Add to cart" rows — and the legend then told the
              // agent to dismiss the page's primary controls before doing anything.
              if (isBanner) {
                try {
                  if (walker.querySelector('main, [role="main"], nav, [role="navigation"]')) isBanner = false;
                } catch (e) {}
              }
            }
          } catch (e) {}
          _bannerCache.set(walker, isBanner);
        }
        if (isBanner) return 'overlay-banner';
      }
      // Table-* labels only fire when the surrounding table is actually data.
      if (tag === 'thead') {
        if (_isSemanticTable(walker.parentElement)) return 'table-header';
      } else if (tag === 'tbody') {
        if (_isSemanticTable(walker.parentElement)) return 'table-body';
      } else if (tag === 'table' || role === 'table' || role === 'grid' || role === 'treegrid') {
        if (_isSemanticTable(walker)) return 'table';
      }
      if (tag === 'dialog' || role === 'dialog' || role === 'alertdialog' ||
          (walker.getAttribute && walker.getAttribute('aria-modal') === 'true')) {
        return 'dialog';
      }
      if (tag === 'aside' || role === 'complementary') return 'sidebar';
      if (tag === 'nav'   || role === 'navigation')    return 'nav';
      if (tag === 'header'|| role === 'banner')        return 'header';
      if (tag === 'footer'|| role === 'contentinfo')   return 'footer';
      if (tag === 'main'  || role === 'main')          return 'main';
      if (role === 'tablist' || role === 'tabpanel')   return role;
      if (role === 'menu' || role === 'menubar' || role === 'listbox') return role;
      if (role === 'form' || tag === 'form')           return 'form';
      // Crossing a frame boundary: the element lives inside an embedded frame —
      // a strong disambiguator (embedded editor / widget vs the host page).
      if (tag === 'iframe' || tag === 'frame')         return 'iframe';
      walker = composedParent(walker);   // crosses shadow host + frame boundaries
    }
    return '';
  };

  // Active-state detector. Looks at *attribute*-level signals only (no class
  // sniffing — too many false positives like "activeClass" / "active-deal").
  // Surfaces which tab/nav item the current page actually is so the agent can
  // tell "Investors Database tab" from "Investor Relations Hub sidebar item"
  // when both are present in the listing.
  const activeHint = (el) => {
    try {
      const ac = el.getAttribute('aria-current');
      if (ac && ac !== 'false') return 'current';
      if (el.getAttribute('aria-selected') === 'true') return 'selected';
      if (el.getAttribute('aria-pressed') === 'true') return 'pressed';
      // Radios/checkboxes/switches announce state via aria-checked (custom)
      // or .checked (native) — was missing entirely, so the agent couldn't
      // tell the active option of a segmented toggle or a ticked checkbox.
      if (el.getAttribute('aria-checked') === 'true') return 'checked';
      if (el.checked === true) return 'checked';
      if (el.getAttribute('aria-expanded') === 'true') return 'expanded';
      const ds = el.getAttribute('data-state');
      if (ds === 'active' || ds === 'open' || ds === 'on' || ds === 'checked') return ds;
      // CLASS booster, scoped to tabs/options only (general class sniffing has
      // too many false positives — but a role=tab with an exact "active"/
      // "selected" class token is the de-facto pattern when sites skip
      // aria-selected; lichess's lobby tabs carry no ARIA state at all).
      const _ahRole = el.getAttribute('role');
      if (_ahRole === 'tab' || _ahRole === 'option') {
        // TWO DECLARED SIGNALS FIRST, both from ARIA's own tab pattern, both
        // language- and framework-neutral. They are strictly better evidence than
        // a class name and were simply never used.
        //
        // (1) FUNCTIONAL: the selected tab is the one whose aria-controls panel is
        //     rendered while a sibling tab's panel is not. That is what "selected"
        //     MEANS for a tabset, so it cannot be wrong about a site it has never
        //     seen — no vocabulary is involved.
        // (2) ROVING TABINDEX: the pattern specifies tabindex="0" on the active tab
        //     and tabindex="-1" on the inactive ones. Requiring a sibling to
        //     actually carry -1 is what makes this evidence rather than a guess:
        //     a page that puts tabindex="0" on every tab says nothing by it.
        try {
          const _sibs = [];
          const _tl = el.closest && el.closest('[role="tablist"]');
          if (_tl) {
            for (const t of _tl.querySelectorAll('[role="tab"]')) if (t !== el) _sibs.push(t);
          }
          const _panelShown = (t) => {
            const id = t.getAttribute && t.getAttribute('aria-controls');
            if (!id) return null;
            const pn = document.getElementById(id);
            if (!pn) return null;
            try { return !!(pn.checkVisibility ? pn.checkVisibility() : pn.offsetParent); }
            catch (err) { return null; }
          };
          const _mine = _panelShown(el);
          if (_mine === true && _sibs.some((t) => _panelShown(t) === false)) return 'selected';
          if (_mine === false) return '';
          if (el.getAttribute('tabindex') === '0' &&
              _sibs.some((t) => t.getAttribute('tabindex') === '-1')) return 'selected';
        } catch (err) {}
        // DELETED: an exact `active|selected|current` class token, kept here as a
        // last resort "until measured dead" and instrumented for exactly this
        // decision. It is now measured dead: ablated across 99 live pages with a
        // per-page drift floor, its total effect on the `active` field was ZERO.
        // The corpus includes shadcn_select, chakra, antd, vuetify, ng_material,
        // bootstrap, headlessui, openui5 and react_aria, so the shape it targets —
        // a tab or option carrying a state class — is abundantly present; it simply
        // never decided anything the two declared signals above had not already
        // decided (the selected tab's aria-controls panel being the rendered one,
        // and ARIA's roving tabindex).
        //
        // The first ablation run reported it LOAD-BEARING on premierleague at
        // 8+/22-, which was an artefact: that page has 2,467 entries and live
        // scores, one bracket's drift floor read 0 while the page's own churn was
        // 22, and FIVE unrelated signatures reported the same two numbers
        // alternating. `activeHint` writes a single field and cannot add or remove
        // entries at all, which is what proved the verdict impossible rather than
        // merely surprising. The floor is now the worst bracket on the page.
        //
        // Cost of deletion, stated: a hand-rolled tabset that declares NOTHING —
        // no aria-selected, no aria-controls, no roving tabindex — loses its
        // `(selected)` marker. That is the honest output, because a class name is
        // not a declaration: `active` is equally an animation state or a
        // "current-user" marker, and a WRONG (current) tells the agent not to click
        // the thing it needs. The fan-out measured that failure class directly with
        // `(disabled)`, where 18 Bootstrap rows were flagged inert and one was
        // clicked to prove otherwise. W16c is now the deletion gate.
      }
      if (el.getAttribute('data-active') === 'true') return 'active';
      if (el.getAttribute('data-current') === 'true') return 'current';
    } catch (e) {}
    return '';
  };
  const vw = window.innerWidth || document.documentElement.clientWidth;
  const vh = window.innerHeight || document.documentElement.clientHeight;
  // CANONICAL interactive-role set (W3C ARIA widget roles). Previously this
  // list was hand-copied in 4 places and the copies disagreed — searchbox/
  // textbox were "interactive" but not "strong" (so unlabeled search fields
  // were dropped as noise), the SVG exception omitted switch (SVG-drawn
  // toggles vanished), and slider/spinbutton/treeitem were missing everywhere.
  // ONE set, used by isInteractive, strong-control rescue, the SVG decorative
  // exception, and the cursor-only dedup test. (role=row/gridcell deliberately
  // excluded: data grids set them on EVERY cell — APG roving-tabindex already
  // catches the real interactive ones via hasAttribute('tabindex').)
  const INTERACTIVE_ROLES = new Set(['button','link','menuitem','menuitemcheckbox','menuitemradio',
    'tab','checkbox','radio','switch','option','combobox','searchbox','textbox',
    'slider','spinbutton','treeitem']);
  // NAME FROM CONTENT, SPACE-SEPARATED, per AccName 1.2 step 2F: each child's
  // contribution is APPENDED WITH A SEPARATOR, which is what Chrome's own accname
  // does. We concatenated instead, and on a spaceless script the seam is invisible
  // and the result is a wrong NUMBER. Measured live on Baidu: a hot-search row is
  // <a><span>4</span><span>9秒39!…</span></a> -- rank 4 and a 9.39-second record --
  // and it was reported as "49秒39", i.e. 49.39 seconds. In English the seam shows
  // ("4Global bond selloff") and a reader recovers; in Chinese "49秒39" reads as one
  // natural token and nothing about it looks wrong.
  //
  // Only ELEMENT children get the separator. A pure text node is left alone, so
  // <button>Save</button> is untouched and only nodes with multiple element
  // children change at all.
  // COMPOSED-TREE TEXT. `innerText` and `textContent` both stop at a shadow
  // boundary, so a custom element that renders all of its text inside its own
  // shadow root reads as EMPTY — while the user plainly sees it. The collection
  // walk has always recursed into open shadow roots; text extraction never did,
  // so the two disagreed about the same element. That asymmetry is why GitHub's
  // <relative-time> timestamps and Reddit's vote counts were unreachable by every
  // text tool: "opened <relative-time>3 days ago</relative-time>" came back as
  // "opened", a silently amputated string rather than a missing one.
  //
  // Walks the COMPOSED tree, which is what the user sees: a host with a shadow
  // root renders its shadow content ONLY (light children appear through <slot>),
  // so descending into both would print slotted text twice. Depth-bounded, and it
  // honours checkVisibility so a hidden subtree contributes nothing, matching
  // innerText. Used only as a fallback where innerText came back empty — it does
  // not reproduce innerText's CSS-aware line breaking and must not replace it.
  const _deepText = (node, depth) => {
    const d = depth || 0;
    if (d > 6) return '';
    try {
      if (node.nodeType === 3) return node.nodeValue || '';
      if (node.nodeType !== 1) return '';
      if (node.tagName === 'SLOT' && node.assignedNodes) {
        const an = node.assignedNodes({ flatten: true }) || [];
        let s = '';
        for (const n of an) s += _deepText(n, d + 1);
        if (s) return s;
      }
      try { if (node.checkVisibility && !node.checkVisibility()) return ''; } catch (e) {}
      let s = '';
      const sr = node.shadowRoot;
      if (sr) {
        for (const c of sr.childNodes) s += _deepText(c, d + 1);
        return s;
      }
      for (const c of node.childNodes) s += _deepText(c, d + 1);
      return s;
    } catch (e) { return ''; }
  };
  // THE BOUNDARY OF ONE FIELD'S WIDGET. Two separate passes walk up two wrappers
  // from an <input> — one hoisting the displayed selection into `value=`, one
  // looking for a placeholder node to set `(unselected)` — and NEITHER had a stop
  // condition. On a shallow page two hops reach <body>, so the first could report
  // the whole page's text as a field's contents (only a `length <= 60` test stood
  // in the way, and it held merely because most pages have more than 60 characters)
  // and the second could flag a FILLED field unselected because some unrelated
  // widget elsewhere has a placeholder node.
  //
  // A wrapper holding a SECOND control belongs to a group, not to this field, and
  // body / a landmark / a form / a table is never one field's selection display.
  // Structural, and the same reasoning that keeps form_input's popover-search
  // fallback inside its widget (#14/W10). Defined once because #21's lesson was
  // that one concept spelled twice drifts into two behaviours — and these two had
  // already drifted apart in every other respect.
  const _FIELD_STOP = {
    MAIN: 1, NAV: 1, HEADER: 1, FOOTER: 1, ASIDE: 1, SECTION: 1,
    FORM: 1, FIELDSET: 1, TABLE: 1, UL: 1, OL: 1, BODY: 1, HTML: 1,
  };
  const _inFieldWrapper = (w, el) => {
    try {
      if (!w || _FIELD_STOP[w.tagName]) return false;
      for (const c of w.querySelectorAll('input, select, textarea, [role="combobox"]')) {
        if (c !== el) return false;
      }
      return true;
    } catch (e) { return false; }
  };
  const _contentName = (node) => {
    try {
      const parts = [];
      for (const n of node.childNodes) {
        if (n.nodeType === 3) parts.push(n.nodeValue || '');
        else if (n.nodeType === 1) {
          let t = (n.innerText != null ? n.innerText : n.textContent) || '';
          if (!t.trim()) t = _deepText(n);
          if (t.trim()) parts.push(' ' + t + ' ');
        }
      }
      return parts.join('').replace(/\s+/g, ' ').trim();
    } catch (e) {
      try { return ((node.innerText || node.textContent) || '').replace(/\s+/g, ' ').trim(); }
      catch (e2) { return ''; }
    }
  };
  const isInteractive = (el) => {
    const tag = el.tagName.toLowerCase();
    // <summary> is the native disclosure-widget click target (details/summary).
    if (['a','button','input','select','textarea','summary'].includes(tag)) return true;
    // Media with browser-rendered controls is a real interaction surface.
    if ((tag === 'audio' || tag === 'video') && el.hasAttribute('controls')) return true;
    // Canvas-drawn UIs (editors, charts, signature pads): the DOM can't see
    // inside — surface the canvas as a target so the agent knows it exists and
    // can escalate to analyze_screen. Small unlabeled canvases (sparklines,
    // decorations) are filtered later by size; a viewport-dominating canvas is
    // the APP (Excalidraw/Figma-style) even with zero markup.
    if (tag === 'canvas') return true;
    // REMOVED: a class-name regex, /(^|[\s-])canvas($|[\s_-])/i, that admitted any
    // div or svg whose class contained the word "canvas" -- added for tldraw's
    // .tl-canvas. It was the last hardcoded pattern left in the EXISTENCE path, and
    // it is the shape this project has been burned by repeatedly: it recognises the
    // word one library happened to choose, silently misses every library that chose
    // another, and reads as general while measuring narrow.
    //
    // Nothing replaces it because nothing needs to. A real drawing surface is
    // declared interactive by the platform in ways already tested below: a
    // whiteboard binds pointer handlers (__abClickBound), sets cursor to something
    // other than the default, or carries tabindex/role. If a div declares NONE of
    // those, the page is not telling anyone it is interactive, and guessing from its
    // class name is not evidence.
    // Code-editor hosts (a styled view over a hidden input — neither looks
    // interactive on its own, but the host IS the editor the user sees and types
    // into). Resolved above by library class OR by structure, so an unknown
    // editor is recognised the same way a named one is. CM6's .cm-content is
    // contenteditable and is caught by the contenteditable path instead.
    if (editorHosts.has(el)) return true;
    // Viewport-dominating bare <svg> = a vector editing surface (draw.io's
    // mxGraph canvas) — surfaced like <canvas>, size-gated in the loop.
    if (tag === 'svg') return true;
    const role = el.getAttribute('role');
    if (role && INTERACTIVE_ROLES.has(role)) return true;
    if (el.hasAttribute('onclick') || el.hasAttribute('tabindex') || el.isContentEditable) return true;
    // Tagged by the document_start listener-wrap (extension/listener_tag.js):
    // a JS click/pointer handler was bound via addEventListener — the one
    // signal no static DOM walk can see. (Delegation roots excluded both at
    // the tagger and here — defense in depth.)
    if (el.__abClickBound && tag !== 'body' && tag !== 'html' && tag !== 'main') return true;
    try { if (getComputedStyle(el).cursor === 'pointer') return true; } catch (e) {}
    // REJECTED CANDIDATE — do not re-add without new evidence. A `collapsed`/
    // `expanded` class token was proposed as an accordion-header signal (same
    // cross-library shape as the `placeholder` token rule) to recover three
    // Mind2Web targets the interactivity gate drops. MEASURED, both sides:
    //   out-of-sample recall  44/47 -> 44/47   (recovers ZERO)
    //   dev corpus, 26 sites  +9 entries (+0.17%), and an UNEXPLAINED -3% chars
    // It does flip the classification — the underarmour header stops being
    // `not-interactive` — but the element is then dropped by `outside-viewport`
    // anyway, so nothing reaches the listing. Zero benefit, non-zero footprint,
    // and a size change we could not account for. Rejected on the numbers.
    return false;
  };
  // Decorative SVG-internal tags that bloat the listing without being plausible
  // click targets. Skip unless they carry an explicit interactive ARIA role.
  const decorativeTags = new Set(['svg','rect','path','circle','polyline','polygon','line','ellipse','g','use','defs','symbol']);
  // Track which mmids we've added so we can collapse parent->child same-label
  // chains (`<a>Investor Relations Hub` containing `<span>Investor Relations Hub`).
  const addedMmids = new Set();
  // DELEGATION ROOTS (React/Vue bind every handler on the app container, so that
  // container gets tagged __abClickBound and looks like a control). Candidates are
  // collected during the walk and confirmed/dropped in a post-pass. Must live at
  // FUNCTION scope — CONTAINER_ROLES sits inside the per-element loop.
  const _handlerOnlyWrappers = new Set();
  // Per-ancestor memo for the inner-scroll-container check — siblings share
  // their scroll ancestors, so this turns O(elements × depth) style reads into
  // one read per distinct container.
  const scrollAncCache = new Map();
  const out = [];
  // mmid -> entry. The parent-child dedup below runs a composed ancestor walk
  // for EVERY element and did out.find() at each hop, which is O(elements x
  // depth x listed) for what is a hash lookup — on a dense page (java_api
  // collects ~4.7k entries) that dominated the cost of the walk.
  const outByMmid = new Map();
  // Count of real interactive controls sitting BELOW the current viewport, so we
  // can tell the agent to scroll (it has no other signal that they exist — this
  // is the #1 reason it gives up on long pages / below-fold forms).
  let belowFoldCount = 0;
  // Off-viewport real controls tallied by landmark region, so the "scroll down"
  // hint can say WHERE they are instead of only how many there are.
  const _offRegions = {};
  let aboveFoldCount = 0;   // same idea for controls scrolled ABOVE the viewport
  let sideCount = 0;        // ...and for controls off the LEFT or RIGHT edge
  // Whether tag genuinely needs to be listed even with no visible text label
  // (form inputs are routinely empty but the agent must be able to find them).
  const formyTags = new Set(['input','textarea','select']);
  // <input> types whose `value` is a LABEL rather than user-entered content.
  const BUTTONISH_INPUT = new Set(['submit', 'button', 'reset', 'image']);
  // Roles/tags that are "strong" interactive — a real control the agent will
  // need even when it carries no text label (icon buttons: ✕ close, ⋮ kebab,
  // pencil edit, hamburger, logo-link; unlabeled search fields, sliders).
  // Merely cursor:pointer / tabindex on a generic <div> does NOT qualify —
  // those stay dropped to avoid mystery noise. Same canonical set.
  const strongInteractiveRoles = INTERACTIVE_ROLES;
  // Last-resort handle for a label-less strong control, derived WITHOUT any
  // site-specific knowledge: an inline <svg><title>, an icon's aria-label, a
  // child <img alt>, common automation data-* attributes, or a child title.
  // (self aria-label/title/alt/name are already tried in the AccName chain.)
  // Code-point-safe cut, available to synthLabel (which runs before clip is
  // declared). AUDIT_DOM_GENERALITY.md §4.7 claimed five truncation sites were
  // fixed; synthLabel alone still had seven raw slices, so an emoji at the
  // boundary produced a lone surrogate that serialises as garbage.
  // dup:markcut — synthesized handles are agent-facing labels, so they get the
  // same residual marker as every other bound. Unmarked, a 40-char slice of a
  // 142-char image alt read as a complete product description, and one cut left
  // a trailing ", " that looked like a finished list.
  const _cut = (t, n) => {
    if (!t || t.length <= n) return t;
    const c = t.charCodeAt(n - 1);
    const head = t.slice(0, (c >= 0xD800 && c <= 0xDBFF) ? n - 1 : n);
    return head + '…(+' + (t.length - head.length) + ')';
  };
  // ONE COPY of the icon-library handle lookup. It existed only inside the
  // name-rescue branch, which is gated on `accessibleName.length > 0` — so it was
  // unreachable for a control with NO accessible name, the commonest icon case and
  // the exact one its own comment cites ("an icon+badge collapses to just the badge
  // count, `a \"3\"` for a messages menu"). Now synthLabel consults it too, and the
  // logic is defined once: #21's lesson was that one concept spelled twice drifts
  // into two behaviours.
  //
  // These functions are injected with chrome.scripting and lose their closure, so
  // the duplication this replaces was forced at the file level but not inside one
  // function.
  const _iconClassHandle = (el) => {
    const ICON_SEL = '[class*="fa-"],[class*="bi-"],[class*="icon-"],[class*="lucide-"],'
      + '[class*="ph-"],[class*="ri-"],[class*="ti-"],[class*="mdi-"],[class*="bx-"],'
      + '[class*="octicon-"],[class*="tabler-"],[class*="la-"],[class*="gg-"]';
    const ICON_RE = /(?:^|\s)(?:fa|far|fas|fab|fal|bi|icon|lucide|ph|ri|ti|mdi|bx|bxs|gg|la|las|octicon|tabler)-([a-z][a-z0-9-]{2,})/;
    const ICON_SKIP = /^(sm|lg|xs|xl|[0-9]x|fw|solid|regular|light|bold|thin|fill|duotone|brands|outline|filled|line|spin|pulse)$/;
    try {
      const scope = [];
      try { if (el.getAttribute && el.getAttribute('class')) scope.push(el); } catch (e) {}
      for (const ic of (el.querySelectorAll ? el.querySelectorAll(ICON_SEL) : [])) scope.push(ic);
      for (const ic of scope) {
        const m = ICON_RE.exec((ic.getAttribute && ic.getAttribute('class')) || '');
        if (m && !ICON_SKIP.test(m[1])) return m[1].replace(/-/g, ' ');
      }
    } catch (e) {}
    return '';
  };
  const synthLabel = (el) => {
    try {
      const svgTitle = el.querySelector('svg title, title');
      if (svgTitle && (svgTitle.textContent || '').trim()) return svgTitle.textContent.trim();
      const svgAL = el.querySelector('svg[aria-label], [aria-label]');
      if (svgAL) { const a = (svgAL.getAttribute('aria-label') || '').trim(); if (a) return a; }
      const img = el.querySelector('img[alt]');
      if (img) { const a = (img.getAttribute('alt') || '').trim(); if (a) return a; }
      for (const attr of ['data-testid','data-test-id','data-test','data-tooltip','data-label','data-icon','data-action','data-key']) {
        let v = (el.getAttribute(attr) || '').trim();
        // These are automation/framework attrs, not labels — reject values
        // that are clearly machine handles, not human words: Stimulus action
        // descriptors ("click->modal#close"), selector-ish tokens, hex ids.
        if (!v || /[#>{}()\[\]]|->/.test(v)) continue;
        v = v.replace(/[-_]+/g, ' ').trim();
        // "Has letters" must mean letters in ANY script. /[a-z]/i rejected every
        // Chinese, Japanese, Korean, Arabic, Cyrillic, Greek, Hebrew, Thai and
        // Devanagari label outright — on those sites the fallback silently
        // produced nothing and the control was listed as an unlabeled icon.
        if (!/\p{L}/u.test(v)) continue;                       // no letters -> meaningless
        if (!v.includes(' ') && /^[0-9a-f]{8,}$/i.test(v)) continue;  // hash-like id
        // Record WHERE this came from. A data-* automation hook is not something
        // the page says out loud, and it was landing in the slot the legend calls
        // "the field's IDENTITY" with nothing to distinguish it from a real name.
        try { el.__abSynthAttr = attr; } catch (e) {}
        return v;
      }
      const childTitled = el.querySelector('[title]');
      if (childTitled) { const t = (childTitled.getAttribute('title') || '').trim(); if (t) return t; }
      // An icon library's own token for the glyph. Attributed, so the row says the
      // name came off a class name rather than from anything the page declares.
      const _ich = _iconClassHandle(el);
      if (_ich) {
        try { el.__abSynthAttr = 'icon-class'; } catch (e) {}
        return _ich;
      }
      // SHADOW-SLOTTED text: a link wrapping a web component whose label lives
      // in the component's OPEN shadow root (<a><onboarding-tile/></a> on
      // archive.org) — host.innerText is empty for shadow content, so read the
      // composed text explicitly.
      try {
        const kids = el.querySelectorAll('*');
        for (const n of kids) {
          if (n.shadowRoot) {
            // NOTE: ':scope > *' does NOT match on a ShadowRoot (it's a
            // DocumentFragment, not an element) — iterate .children directly.
            let t = '';
            for (const c of n.shadowRoot.children) {
              const ct = (c.innerText || '').trim();
              if (ct) t = t ? t + ' ' + ct : ct;
            }
            t = t.replace(/\s+/g, ' ').trim();
            if (t && t.length <= 80) return t;
          }
        }
      } catch (e) {}
      // CARD PATTERN: a text-less image/overlay link whose parent card carries
      // a heading ("hero cards" — the visible title sits OUTSIDE the anchor).
      // Only fires for label-less links that dominate their parent's area.
      try {
        const er = el.getBoundingClientRect();
        let p = el.parentElement;
        for (let d = 0; d < 2 && p; d++, p = p.parentElement) {
          const pr = p.getBoundingClientRect();
          // 0.3 not 0.5: tile cards put the caption BELOW the icon-anchor, so
          // the anchor covers well under half the card (archive.org tiles).
          const dominates = pr.width * pr.height > 0 &&
            (er.width * er.height) / (pr.width * pr.height) >= 0.3;
          if (!dominates) continue;
          const h = p.querySelector('h1,h2,h3,h4,h5,h6,[role="heading"]');
          if (h) {
            const ht = (h.innerText || '').trim().replace(/\s+/g, ' ');
            if (ht) return ht;
          }
          // No heading, but the card's own short text labels the tile
          // (archive.org help tiles: image-link + caption outside the <a>).
          const pt = (p.innerText || '').trim().replace(/\s+/g, ' ');
          if (pt && pt.length <= 40) return pt;
        }
      } catch (e) {}
      // CSS ::before/::after content — icon-font ligatures and many buttons put
      // their human label here (e.g. content:"close"). Skip private-use glyphs.
      for (const pseudo of ['::before','::after']) {
        try {
          let c = getComputedStyle(el, pseudo).content;
          if (c && c !== 'none' && c !== 'normal') {
            c = c.replace(/^["']|["']$/g, '').trim();
            if (c && c.length <= 40 && /[\p{L}\p{N}]/u.test(c)) return c;   // any script, not just ASCII
          }
        } catch (e) {}
      }
    } catch (e) {}
    return '';
  };
  // Code-point-safe truncation. String.slice cuts UTF-16 code UNITS, so a label
  // whose 60th unit lands inside a surrogate pair — any emoji, and the astral
  // CJK/Emoji ranges plenty of real buttons use — is cut through the middle of a
  // character, leaving a lone surrogate that serialises into the listing as
  // garbage. Back off one unit in that case.
  const clip = (s, n) => {
    if (!s || s.length <= n) return s;
    const c = s.charCodeAt(n - 1);
    return s.slice(0, (c >= 0xD800 && c <= 0xDBFF) ? n - 1 : n);
  };
  // EVERY bound on a string the agent READS goes through here. A silent cut is
  // not a smaller truth, it is a different one: a 60-char slice of a 900-char
  // editor is indistinguishable from a 60-char document, and a live agent wrote
  // to an editor four times reading back a byte-identical value= each time with
  // no way to tell truncation from a failed write. The residual count is what
  // separates "clipped" from "short" — `x` and `x…(+840)` cannot be confused.
  // Cuts on a word boundary when one is near the end (surrogate-safe via clip),
  // so a multi-byte script is never split mid-character.
  // NO PER-FIELD CAP. Measured on 39 frozen sites: removing every per-field
  // bound costs +3.1% total listing chars, median 1.002x, worst 1.35x — the
  // caps were buying almost nothing because a LABEL is bounded by human
  // authorship already. What they cost was truth: nine separate silent-cut
  // defects this session, all in fields that had no business being bounded.
  // The ONE bound left is the caller's max_chars, which is explicit, chosen by
  // the caller, and reports exactly how many elements it dropped.
  const markCut = (s, n) => {
    s = s || '';
    if (s.length <= n) return s;
    let cut = clip(s, n);
    const sp = cut.lastIndexOf(' ');
    if (sp >= n * 0.66) cut = cut.slice(0, sp);
    return cut + '…(+' + (s.length - cut.length) + ')';
  };
  // i18n:placeholder — ONE spelling, enforced by tools/test_patterns.py.
  // This question (is the trigger showing a HINT rather than a choice?) was
  // asked in four places with four copies of an English-only wordlist.
  // DESTRUCTIVE drifted exactly that way and ended up rejecting 'Abbrechen'
  // in one tier while accepting it in another. These functions are injected
  // into the page and lose their closure, so the duplication is forced —
  // the test asserts every copy is byte-identical.
  // LAST RESORT: _showingPlaceholder / data-placeholder / an empty backing
  // control all run FIRST at every call site. This tier only exists for
  // hand-rolled widgets that mark placeholder state by grey text alone.
  // URL / MEDIA extraction, only populated when detail='full'.
  const _abs = (u, el) => {
    try { return new URL(u, (el.ownerDocument && el.ownerDocument.baseURI) || location.href).href; }
    catch (e) { return u || ''; }
  };
  const _url = (u, el) => {
    if (!u) return '';
    // A truncated data: URI is worse than useless — it looks like a URL the agent
    // can fetch and is not one. Describe it instead.
    if (/^data:/i.test(u)) {
      const mime = (u.slice(5).split(/[;,]/)[0] || 'data');
      return `data:${mime} (inline, ${u.length} chars — not a fetchable URL)`;
    }
    // detail="full" exists to give a URL you can PASTE. A signed link cut at 300
    // with no marker is the one failure this mode must not have: it resolves,
    // it looks whole, and it is wrong. (brief already marks its elisions.)
    return _abs(u, el);
  };
  const _hrefOf = (el) => { try { return _url(el.getAttribute('href'), el); } catch (e) { return ''; } };
  // ALT TEXT IS CONTENT, NOT A LABEL — and a cut that does not look like a cut is
  // worse than a short field. The media rows hard-sliced alt at 60 chars with NO
  // marker, while the accessible-name path does a word-boundary cut and appends
  // '…'. Measured live on Wolfram Alpha, where the answer to a query IS the alt
  // text of a rendered image: the listing showed
  //   name="integral_(-20)^20 sqrt(1 + (-x cos(x) + sin(x))^2/x^4)dx≈40."
  // and the true value was 40.485121134668 — the cut landed after "≈40." so it
  // read as a COMPLETE numeric answer. An agent reporting it would be confidently
  // wrong with no reason to re-check. Bigger budget (alt is the only textual form
  // of an image) plus the same visible marker every other truncation uses.
  // ALT TEXT IS CONTENT AND IS NOT CAPPED. On Wolfram Alpha the alt text IS the
  // answer, and a cut landing after "≈40." read as a finished number when the
  // truth was 40.485121134668. Human-authored, so bounded in practice anyway.
  const _clipAlt = (s) => String(s || '').trim();
  const _srcOf = (el) => {
    try {
      const MED = ['img', 'video', 'audio', 'source', 'embed'];
      const tl = el.tagName.toLowerCase();
      let m = MED.includes(tl) ? el : null;
      // A link or button wrapping an image is how most clickable media is built,
      // so surface the image it contains rather than reporting nothing. But ONLY
      // for genuinely media-ish hosts: hoisting a descendant's src onto any
      // container put the page logo's URL on Baidu's header <div>, and put a
      // plot's data: URI on a Wolfram <section> so one image read as two. A
      // <section> has no src, and printing one invents a fact.
      if (!m && el.querySelector && (tl === 'a' || tl === 'button' || tl === 'picture' || tl === 'figure')) {
        m = el.querySelector('img[src],video[src],source[src]');
      }
      if (!m) return '';
      // currentSrc BEFORE src. With srcset/sizes — the norm on any news or CDN
      // site — src is the fallback candidate, NOT what the browser painted.
      // Measured on BBC: every one of 12 images reported the 480px variant while
      // the page displayed 1536px. The reported URL resolves and returns a real
      // photo, just not the one on screen, so nothing about the answer looks
      // wrong — which is what makes it worse than an omission.
      return _url(m.currentSrc || m.getAttribute('src') || '', m);
    } catch (e) { return ''; }
  };
  // PLACEHOLDER STATE, structurally — "is this trigger showing its hint rather
  // than a chosen value?" without reading the words.
  //
  // Component libraries all answer this in markup, just not in one agreed place:
  //   Radix / TipTap             data-placeholder            (boolean, on the value node)
  //   Ark UI / Chakra v3         data-placeholder-shown      (boolean, on the trigger)
  //   PrimeVue                   class="p-placeholder" + data-p="placeholder"
  //   Ant / select2 / Choices    a child node classed …-placeholder / __placeholder
  // What they share is the TOKEN "placeholder" appearing in a data-* attribute
  // name, a data-* attribute value, or a class list. Matching that token covers
  // all four and reads identically in German, Japanese or Arabic — which the
  // English select|choose|pick wordlist further down cannot. Measured: ablating
  // that wordlist changed combobox state on chakra (18 controls), primevue (18)
  // and vuetify (3), which is exactly what a non-English page gets today.
  //
  // aria-placeholder is deliberately excluded — it is a static description of
  // the field, present whether or not the hint is currently rendered.
  const _phMarked = (n, txt) => {
    try {
      if (!n || !n.attributes) return false;
      for (const a of n.attributes) {
        if (a.name.indexOf('aria-') === 0) continue;
        if (a.name.indexOf('placeholder') !== -1) {
          const v = (a.value || '').trim();
          // Boolean-style marker: the hint IS showing. A marker carrying the hint
          // STRING is configuration — it only proves placeholder state when that
          // string is what's actually on screen (otherwise a real pick that left
          // data-placeholder="Choose a size" behind would read as unselected).
          if (!v || v === 'true' || !txt || v === txt) return true;
          continue;
        }
        if (a.name.indexOf('data-') === 0 && /(^|[\s,_-])placeholder([\s,_-]|$)/.test(a.value)) return true;
      }
      const cn = typeof n.className === 'string' ? n.className : (n.className && n.className.baseVal) || '';
      // CSS-property utility classes (Tailwind-style `text-placeholder`,
      // `bg-placeholder`) are STYLING, not state — they say what colour the thing
      // is, not that a hint is showing. Matching them marked a combobox reading
      // "Ontario" as (unselected), a row that contradicts its own label.
      for (const tok of String(cn).split(/\s+/)) {
        if (!/(^|[_-])placeholder$|^placeholder([_-]|$)/.test(tok)) continue;
        if (/^(text|bg|border|fill|stroke|ring|shadow|from|via|to|decoration|outline|caret|accent)-placeholder$/.test(tok)) continue;
        return true;
      }
      return false;
    } catch (e) { return false; }
  };
  // The marker may sit on the trigger or on the node rendering its text; for a
  // descendant, require that text to be what the trigger actually shows.
  const _showingPlaceholder = (n, txt) => {
    if (_phMarked(n, txt)) return true;
    try {
      for (const c of n.querySelectorAll('*')) {
        if (!_phMarked(c, txt)) continue;
        const ct = (c.innerText || '').trim();
        if (ct && (!txt || ct === txt)) return true;
      }
    } catch (e) {}
    return false;
  };
  // Collapse an exactly-doubled string ("Cooker Cooker", "Shop gaming Shop
  // gaming") — innerText frequently concatenates a screen-reader copy with the
  // visible copy. Halve it only when the two word-halves are identical.
  const collapseDoubled = (s) => {
    const t = (s || '').split(' ');
    // SINGLE-WORD HALVES ONLY. The screen-reader-duplicate pattern this exists for
    // ("Cooker Cooker") is almost always one word repeated. Allowing multi-word
    // halves corrupted genuine names that legitimately repeat: the "New York New
    // York" hotel became "New York", "Louie Louie" became "Louie". Losing the
    // collapse on rarer multi-word duplicates is a cosmetic cost; silently renaming
    // a real link is a correctness one.
    if (t.length === 2 && t[0] && t[0] === t[1]) return t[0];
    return s;
  };
  // Iterate the registry (composed-tree walk order) instead of
  // document.querySelectorAll('[mmid]') — the latter can't see into shadow roots.
  mmidReg.forEach((el) => {
    if (!el.isConnected) return _drop(el, 'not-connected');
    const tagL = el.tagName.toLowerCase();
    // IFRAMES: same-origin frames were walked like shadow roots, so their inner
    // elements are listed individually — skip the frame element itself.
    // Cross-origin frames are opaque to DOM tools: list the FRAME as one box so
    // the agent at least knows an embedded app exists there (Stripe, OAuth,
    // embedded docs) and can escalate to analyze_screen + coordinate clicks.
    let crossFrame = false;
    if (tagL === 'iframe' || tagL === 'frame') {
      let accessible = false;
      try { accessible = !!el.contentDocument; } catch (e) {}
      // Recorded, not silent: its inner elements ARE listed individually, so the
      // frame is a container rather than a control — but an agent asking the
      // ledger why the iframe has no row of its own used to get no answer at
      // all. This was one of the uninstrumented exits L10c cannot see.
      if (accessible) return _drop(el, 'iframe-contents-listed-instead');
      crossFrame = true;
    }
    // A DISABLED CONTROL IS STILL A CONTROL. `isInteractive` asks "can this be
    // operated", which is the wrong question for existence: a control the page has
    // switched off is exactly the thing an agent needs to be told about, because
    // otherwise "this form has no City field" and "the City field unlocks once you
    // pick a State" are the same output. Measured on demoqa across two fan-outs and
    // ~6 agents: the City widget is a 419x38 react-select rendering the visible text
    // "Select City", with a disabled 4x24 <input> inside it, and BOTH were deleted —
    // absent from the listing, from find, and from the decoration tier.
    //
    // The test is the one already used for pointer-events ten lines below: is this a
    // native form control, does it CONTAIN one, or has the page marked it
    // aria-disabled. Structural and spec-anchored — no class names, no library
    // names, no size. Such an element is kept and flagged (disabled), which is a
    // state the listing already has vocabulary for.
    // NARROW ON PURPOSE. My first version also kept anything that CONTAINED a form
    // control, copied from the pointer-events test below — but that test only ever
    // sees elements already known to have pointer-events:none, whereas this one sees
    // every node on the page. So <html>, <body>, <form> and every wrapper div became
    // "controls": mmids landed on containers and actions resolved to them, clicking a
    // container for zero effect and typing into it for no value (test_gaps G2d/G2g,
    // test_shadow light-DOM click). Turning containers into controls is the same
    // defect as losing a control, pointed the other way.
    //
    // What remains is only what the DOCUMENT declares: a native form control (a
    // control per HTML whatever its state), or an element the page itself marked
    // aria-disabled. The disabled <input> inside a react-select is enough — that is
    // the ref an agent acts on, and it carries (disabled).
    const _switchedOffControl = () => {
      try {
        if (['input', 'select', 'textarea', 'button'].includes(tagL)) return true;
        return el.getAttribute('aria-disabled') === 'true';
      } catch (e) { return false; }
    };
    if (!crossFrame && !isInteractive(el) && !_switchedOffControl()) return _drop(el, 'not-interactive');
    if (decorativeTags.has(tagL)) {
      const rr = el.getAttribute('role');
      if (!rr || !INTERACTIVE_ROLES.has(rr)) {
        // Escape hatch: a viewport-dominating bare <svg> is a vector EDITING
        // surface (draw.io's diagram area), not decoration — fall through to
        // the canvas-like handling.
        let bigSvg = false;
        if (tagL === 'svg') {
          try { const sr = el.getBoundingClientRect(); bigSvg = sr.width * sr.height >= 0.25 * vw * vh; } catch (e) {}
        }
        // ...and an svg the page WIRED UP is a control, not ornament. This gate sat
        // immediately after isInteractive and outranked every interactivity signal:
        // a handler-bound, focusable, <title>-named <svg> — a hand-rolled sort arrow,
        // a close-X, a D3 chart control — existed for no tool. listener_tag.js exists
        // precisely to detect that binding; ignoring it here threw the evidence away.
        // Proven with a fixture: __abClickBound === true and the element absent from
        // the listing.
        let wiredSvg = false;
        try {
          wiredSvg = !!el.__abClickBound || el.hasAttribute('onclick')
                     || el.hasAttribute('tabindex')
                     || !!(el.getAttribute && el.getAttribute('role'));
        } catch (e) {}
        if (!bigSvg && !wiredSvg) _note(el, 'was:decorative-svg');
      }
    }
    // Canvas filter: keep when page-labeled (aria-label/role) OR when it
    // dominates the viewport (>=25% area — it's the app's drawing surface);
    // drop unlabeled small ones (chart sparklines, confetti layers).
    let canvasLike = tagL === 'canvas';
    // Viewport-dominating bare <svg> (no interactive role): vector surface.
    if (!canvasLike && tagL === 'svg') {
      const _svgRole = el.getAttribute('role');
      if (!_svgRole || !INTERACTIVE_ROLES.has(_svgRole)) {
        try { const sr = el.getBoundingClientRect(); canvasLike = sr.width * sr.height >= 0.25 * vw * vh; } catch (e) {}
      }
    }
    // REMOVED: `canvasLike = /(^|[\s-])canvas($|[\s_-])/i.test(className)`, with an
    // `!/off-?canvas/i` exception bolted on after it told an agent to use VISION for
    // an entire IRS page of plain HTML (USWDS/Bootstrap name their drawer
    // "off-canvas"). A word-match on a class name, plus a list of the cases where
    // the word means something else, is the exact shape #21-#28 kept being burned
    // by — and #27's commit message already claimed this regex was gone. It was
    // removed from `isInteractive` only; this second copy still drove the (canvas)
    // marker and the "escalate to a screenshot" hint.
    //
    // Nothing replaces it because a drawing surface declares itself: <canvas>, or a
    // viewport-dominating bare <svg>, both handled above. tldraw's `.tl-canvas`
    // CONTAINS a real <canvas>, which is what gets marked. The three guards that
    // used to follow this branch — page-spanning height, >40 chars of text, an
    // accessible inner iframe — existed only to undo its false positives, and are
    // kept for the <svg> path they also cover.
    if (canvasLike && tagL !== 'canvas') {
      // A drawing surface is viewport-sized and pixel-opaque: page-spanning
      // height or real text content means it's an HTML wrapper, not a canvas.
      try {
        const cr0 = el.getBoundingClientRect();
        if (cr0.height > vh * 1.5) canvasLike = false;
        else if ((el.innerText || '').trim().length > 40) canvasLike = false;
      } catch (e) {}
    }
    if (canvasLike && tagL !== 'canvas') {
      // A class-marked "canvas" that CONTAINS an accessible same-origin iframe
      // is NOT pixel-opaque — it's a page-builder surface (GrapesJS) whose
      // inner DOM is walked and listed. The canvas hint would wrongly send the
      // agent to vision when the elements are right there.
      try { const fr = el.querySelector('iframe'); if (fr && fr.contentDocument) canvasLike = false; } catch (e) {}
    }
    if (canvasLike) {
      try {
        const cr = el.getBoundingClientRect();
        const _cArea = cr.width * cr.height;
        // A CLASS-MATCHED "canvas" (a styled div/svg we only SUSPECT is a drawing
        // surface) keeps the viewport-fraction gate: the guess is only safe when the
        // thing dominates the view.
        if (tagL !== 'canvas' && _cArea < 0.25 * vw * vh) _note(el, 'was:canvaslike-below-viewport-fraction');
        if (!(el.getAttribute('aria-label') || el.getAttribute('role'))) {
          // A REAL <canvas> gets an ABSOLUTE floor. A viewport FRACTION says a chart
          // stops existing when the window gets wider, which is exactly what happened:
          // chartjs.org's 800x400 centrepiece is 29.6% of a 1200x900 viewport (kept)
          // and 11.1% of a 2327x1234 one (dropped) — so on a wide monitor the largest
          // thing on the page appeared in no listing at any detail level, leaving an
          // unexplained 400px gap between two rows. Nothing about the element changed.
          // 200x200 is the floor below which a canvas is a sparkline or an avatar.
          const _floor = (tagL === 'canvas') ? 40000 : 0.25 * vw * vh;
          if (_cArea < _floor) _note(el, 'was:canvas-below-minimum-size');
        }
      } catch (e) { return _drop(el, 'canvas-measure-failed'); }
    }
    // The page itself says this element is not for content consumption.
    // Per W3C, aria-hidden excludes the WHOLE subtree — checking only the
    // element itself leaked React Aria's VisuallyHidden native-select mirrors
    // (the select is plain; its 1×1 clip-rect WRAPPER carries aria-hidden).
    // [inert] is the W3C way to say "this subtree cannot be interacted with".
    // The counter for it existed and could never increment, because nothing ever
    // called _drop with it — so a bare inert region (a disabled wizard step, a
    // panel behind a non-dialog overlay) was listed as fully live and clickable.
    try { if (el.closest && el.closest('[inert]')) return _drop(el, 'inert'); } catch (e) {}
    // IS THE HIDDEN THING PLAUSIBLY CONTENT? Recorded alongside the drop, because
    // the banner downstream asserts a CAUSE ("a library marked the page inert
    // behind an open menu — close it and they come back") that is false on every
    // react-select or MUI page. Measured: react-select.com has 43 aria-hidden
    // nodes, all of them the library's own indicator/arrow wrappers, ZERO holding
    // a control; MUI has 216 whose only interactive descendants are 19
    // `MuiSelect-nativeInput` mirrors that are aria-hidden BY DESIGN and already
    // listed via `backed-by=`. A control with no name and no text is scaffolding;
    // one with either is page content the agent might actually be looking for.
    const _ahNamed = () => {
      try {
        return !!((el.getAttribute && (el.getAttribute('aria-label') || el.getAttribute('title')))
                  || (el.textContent || '').trim() || (el.value || ''));
      } catch (e) { return false; }
    };
    try {
      if (el.closest && el.closest('[aria-hidden="true"]')) {
        if (_ahNamed()) _stateDrops['aria-hidden-named']++;
        return _drop(el, 'aria-hidden');
      }
    } catch (e) {
      if (el.getAttribute('aria-hidden') === 'true') {
        if (_ahNamed()) _stateDrops['aria-hidden-named']++;
        return _drop(el, 'aria-hidden');
      }
    }
    // closest() stops at the shadow boundary, so a control inside a web
    // component whose HOST is aria-hidden stayed listed — the same W3C
    // whole-subtree rule the line above enforces, just unenforceable with
    // closest(). Only pay for the composed walk when the element is actually a
    // shadow resident.
    try {
      if (el.getRootNode && el.getRootNode().host) {
        let w = el;
        while (w) {
          if (w.getAttribute && w.getAttribute('aria-hidden') === 'true') {
            return _drop(el, 'aria-hidden');   // instrumented: counts + ledger + note
          }
          w = composedParent(w);
        }
      }
    } catch (e) {}
    // Content INSIDE a rich-text editor (contenteditable region) is the user's
    // DOCUMENT, not page UI — typed paragraphs, links, embeds. Listing those as
    // individual targets duplicates the editor entry and invites the agent to
    // click its own typed text. The editor ROOT (the element that carries the
    // contenteditable attribute) is listed as a single text-entry target;
    // contenteditable="false" islands (embedded widgets) keep isContentEditable
    // false and still get listed normally.
    const ceRoot = el.isContentEditable && el.hasAttribute('contenteditable');
    if (el.isContentEditable && !ceRoot) return _drop(el, 'contenteditable-non-root');
    // VISUALLY-HIDDEN INPUT UNDER A STYLED LABEL — the standard custom radio/
    // checkbox pattern (<label><input class="sr-only"><span>0</span></label>:
    // SurveyJS ratings, Bootstrap/Tailwind custom forms). The 1×1 input is the
    // SEMANTIC control; the label is its visible body. Without this, the
    // page's primary answer widgets are simply absent. Adopt the label's
    // geometry for the input's entry (clicks on the label toggle the input).
    // THE CONTROL'S OWN VISIBLE LABEL. When a page hides a real form control and
    // paints a label/styled surface over it for the user to click, that label is
    // the proof the control is OPERABLE rather than a discarded mirror — and it is
    // what the user (and a click) actually hits.
    const _visibleLabelFor = (n) => {
      try {
        const cands = [];
        const wrap = n.closest && n.closest('label');
        if (wrap) cands.push(wrap);
        if (n.id) {
          const root = (n.getRootNode && n.getRootNode().querySelector) ? n.getRootNode() : document;
          const l = root.querySelector(`label[for="${CSS.escape(n.id)}"]`);
          if (l) cands.push(l);
        }
        for (const l of cands) {
          const lr = l.getBoundingClientRect();
          const lcs = ((l.ownerDocument && l.ownerDocument.defaultView) || window).getComputedStyle(l);
          if (lr.width > 7 && lr.height > 7 && lcs.visibility !== 'hidden' &&
              lcs.display !== 'none' && parseFloat(lcs.opacity || '1') > 0) return l;
        }
      } catch (e) {}
      return null;
    };
    const ownLabel = formyTags.has(tagL) ? _visibleLabelFor(el) : null;
    let labelProxy = null;
    if (formyTags.has(tagL)) {
      try {
        const r0 = el.getBoundingClientRect();
        if (r0.width <= 4 || r0.height <= 4) {
          const wrapLab = el.closest && el.closest('label');
          if (wrapLab && wrapLab.querySelectorAll('input,select,textarea').length === 1) {
            const lr = wrapLab.getBoundingClientRect();
            const lcs = getComputedStyle(wrapLab);
            if (lr.width > 7 && lr.height > 7 && lcs.visibility !== 'hidden' && lcs.display !== 'none') {
              labelProxy = wrapLab;
            }
          }
        }
      } catch (e) {}
    }
    // Same idea for code-editor hosts: everything INSIDE a CodeMirror/Monaco/
    // Ace instance (hidden mirror textarea, line divs, gutters, cursors) is the
    // editor's rendering machinery, not page UI. List the host as ONE editor
    // target; _enterTextPage routes typing to the editor's real input.
    let codeEditor = false;
    try {
      // composed walk, not closest(): an editor mounted inside a web component
      // (Ionic/Lit playgrounds) has its host on the other side of a shadow
      // boundary, where closest() stops and every internal line div leaks in.
      let ceHost = null;
      { let w = el; while (w) { if (editorHosts.has(w)) { ceHost = w; break; } w = composedParent(w); } }
      if (ceHost && ceHost !== el) return _drop(el, 'inside-editor-host');
      // EDITABILITY GATE: real editors carry an input surface (CM5/Ace mirror
      // textarea, CM6 .cm-content contenteditable, Monaco .inputarea). Static
      // syntax-highlighted snippets reuse the same class names — promoting a
      // read-only npm-install block to "type into it with enter_text_tool"
      // sent the agent typing into a wall.
      if (ceHost) {
        codeEditor = !!ceHost.querySelector('textarea, [contenteditable="true"], [contenteditable=""], .cm-content');
      }
    } catch (e) {}
    // Geometry source: the element itself, or its label proxy (hidden-input-
    // under-styled-label pattern — the label's box is where the user clicks).
    const geomEl = labelProxy || el;
    const r = geomEl.getBoundingClientRect();
    // Absolute (top-document) coordinates — identical to r for top-doc elements,
    // shifted by the accumulated frame offsets for same-origin-iframe content.
    // The listing's box() and CDP clicks both need TOP-document coordinates.
    const inFrame = el.ownerDocument !== document;
    const fpt = inFrame ? framePoint(el, r.left, r.top) : { x: r.left, y: r.top, kx: 1, ky: 1 };
    const ax = fpt.x, ay = fpt.y;
    const aw = r.width * fpt.kx, ah = r.height * fpt.ky;
    // getComputedStyle must come from the element's own window for in-frame nodes.
    const cs = ((el.ownerDocument && el.ownerDocument.defaultView) || window).getComputedStyle(geomEl);
    // OWN opacity:0 is not automatically "not there". The comment below explains
    // that opacity-hidden OPERABLE controls must stay listed — but it only ever
    // protected ANCESTOR opacity, so a control with opacity:0 on ITSELF died here.
    // That is the single most deployed custom-form pattern on the web: Bootstrap
    // 4's .custom-control-input (a 16x20 checkbox at opacity:0 behind its styled
    // label) and the styled file upload (opacity:0 input over a pretty button).
    // Both vanished completely — no entry, no name, no ref for file_upload to
    // target. The recall harness could not see it either, because its ground truth
    // filters to visible elements too.
    //
    // The evidence that such a control is OPERABLE rather than a discarded mirror
    // is that the page gave it a visible label to click. No label -> still dropped.
    const _selfOpaque = parseFloat(cs.opacity || '1') > 0;
    // A TRANSPARENT CONTROL THE PLATFORM STILL LETS YOU OPERATE IS NOT ABSENT.
    // `opacity` is presentational. `display:none`, `visibility:hidden` and
    // aria-hidden are the declarations of absence, and Chrome keeps an opacity:0
    // focusable control in its accessibility tree — so dropping one is a
    // deviation from the platform's own statement, not a reading of it. The
    // comment just below already argues exactly this for ANCESTOR opacity (the
    // opacity-0 input[file] under a styled upload button, MUI DateField's
    // sections); SELF opacity was gated on `ownLabel` instead, which deletes any
    // transparent control whose name comes from a neighbouring <label>.
    //
    // Measured live on demoqa: react-select drops its <input> to opacity:0 once a
    // value is committed, so the State field VANISHED from every listing the
    // moment it was successfully filled — "there is no State field" and "State
    // holds NCR" became the same output, the verification read as a failure, and
    // the retry hit City, which had shifted into its slot. Six container
    // heuristics were converted to demotions before this, and none of them was
    // the cause; read_page(ledger=true) named it in one call.
    //
    // FOCUSABILITY IS NOT THE TEST, and P2 is why. A transparent focusable input
    // is equally the shape of a MIRROR or scratch buffer — Monaco's read-only
    // `ime-text-area`, which #24 recorded `form_input` reporting Success into
    // while the editor never changed, and the native `<select>` mirrors MUI ships
    // behind its custom ones. Keeping every focusable one trades this false
    // negative for that false positive, so the test is what the page DECLARES:
    // an interactive ARIA role, or ARIA wiring into a widget. react-select's
    // committed input says `role=combobox` and carries aria-expanded; a decoy
    // mirror declares nothing and stays dropped (P2), which is the same
    // declaration-over-inference rule the rest of the collector runs on.
    // MEASURED INCOMPLETE ON THE FIRST PASS. A live probe set showed a transparent
    // input survived only when a <label> WRAPPED it (that is what fed `ownLabel`):
    //   checkbox opacity:0 in a plain div  -> NOT listed
    //   checkbox opacity:0 in a <label>    -> listed
    //   file     opacity:0 + aria-label    -> NOT listed
    //   file     opacity:0 in a <label>    -> listed
    // So the opacity-0 input[file] under a styled upload button — the case the
    // comment below cites as the reason ANCESTOR opacity is allowed — did not
    // actually work, and an explicit aria-label did not rescue it. For a checkbox
    // the wrapper got listed as a `div`, so `(checked)` was unreadable and kind
    // routing saw a container; for a file input, file_upload() needs the input's own
    // ref and there was none.
    // Three more declarations therefore count, each one the page stating something:
    //  - an explicit accessible name (aria-label / aria-labelledby / title);
    //  - an input TYPE that is inherently a widget rather than a text field. A
    //    checkbox, radio, file or range IS its type — there is no "mirror checkbox"
    //    idiom the way there is a mirror text input, which is what P2 guards;
    //  - a native control that is genuinely form-associated via `name`.
    // The decoy P2 protects — <input type=text> with no role, no name, no aria —
    // still declares nothing and stays dropped.
    let _declaredCtl = false;
    try {
      const _dr = el.getAttribute('role');
      const _wt = (el.getAttribute('type') || '').toLowerCase();
      const _WIDGET_TYPES = ['checkbox', 'radio', 'file', 'range', 'color', 'date',
                             'datetime-local', 'month', 'week', 'time', 'submit',
                             'reset', 'image', 'button'];
      _declaredCtl = !!(_dr && INTERACTIVE_ROLES.has(_dr))
                     || el.hasAttribute('aria-expanded')
                     || el.hasAttribute('aria-autocomplete')
                     || el.hasAttribute('aria-controls')
                     || el.hasAttribute('aria-label')
                     || el.hasAttribute('aria-labelledby')
                     || !!(el.getAttribute('title') || '').trim()
                     || (tagL === 'input' && _WIDGET_TYPES.indexOf(_wt) !== -1);
    } catch (e) {}
    let visible = r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' &&
                    cs.display !== 'none' && (_selfOpaque || !!ownLabel || _declaredCtl);
    // Modern Chromium hides closed-<details> content (and hidden=until-found)
    // via content-visibility, NOT display:none — rects stay non-zero, computed
    // display stays visible, and the old checks leaked those invisible controls
    // into the listing as label-less ghosts. checkVisibility() accounts for
    // content-visibility:hidden ancestors. Deliberately NOT passed:
    //  - contentVisibilityAuto (c-v:auto content is real, just paint-skipped);
    //  - checkOpacity — ancestor opacity:0 is a standard OPERABLE-control
    //    pattern (opacity-0 input[file] under a styled upload button; MUI
    //    DateField's section list is opacity-0 until focused). Those must stay
    //    listed: clicking/typing focuses and reveals them.
    try {
      if (visible && el.checkVisibility &&
          !el.checkVisibility({ checkVisibilityCSS: true })) visible = false;
    } catch (e) {}
    const inViewport = (ay + r.height) > 0 && (ax + r.width) > 0 && ay < vh && ax < vw;
    // Modal/dialog content is the user's focus. Many dialogs are taller than the
    // viewport (long forms) with their submit button at the bottom. Skipping
    // those because of inViewport made the agent unable to find the submit
    // button. So: if the element is inside a dialog, include it regardless of
    // viewport position (it's reachable via in-modal scroll).
    let inModal = false;
    {
      let w = el;
      while (w && w !== document.body && w.tagName) {
        const t = w.tagName.toLowerCase();
        const ro = w.getAttribute ? w.getAttribute('role') : null;
        if (t === 'dialog' || ro === 'dialog' || ro === 'alertdialog' ||
            (w.getAttribute && w.getAttribute('aria-modal') === 'true')) { inModal = true; break; }
        w = composedParent(w);
      }
    }
    // pointer-events:none (computed value already accounts for inheritance) means
    // clicks pass straight through — but for REAL form controls it's how
    // Tailwind/shadcn renders DISABLED state (`disabled:pointer-events-none`).
    // Dropping those hid Boxsy's disabled "Add Investor" submit button and the
    // agent picked Cancel as its submit target. Keep real controls, flagged
    // (disabled); drop only decorative pass-through nodes.
    let peDisabled = false;
    if (visible && cs.pointerEvents === 'none') {
      const _peRole = el.getAttribute('role');
      const _peReal = ['a', 'button', 'input', 'select', 'textarea', 'summary'].includes(tagL) ||
                      (_peRole && INTERACTIVE_ROLES.has(_peRole)) ||
                      // Structural, not a tag list: a wrapper the page explicitly
                      // marked disabled, or one that CONTAINS a real form control
                      // (every react-select/Headless combobox has a hidden input
                      // inside it). Decorative pass-through nodes have neither.
                      el.getAttribute('aria-disabled') === 'true' ||
                      !!(el.querySelector && el.querySelector('input,select,textarea'));
      if (!_peReal) _note(el, 'was:pointer-events-none');
      peDisabled = true;
    }
    // FIND REACH: the STRING listing stays viewport-scoped (token discipline),
    // but the STRUCTURED array — which backs the `find` tool — keeps real
    // controls that are merely scrolled out of view, flagged offscreen.
    // Without this, find() is viewport-bound: a semantically perfect query
    // ("Launch demo modal button") returns 13 wrong answers because the target
    // is 200px below the fold, and the SAME query works after scrolling. Clicks
    // auto-scroll (scrollIntoView in _clickPage/_rectForPage), so these refs are
    // immediately actionable — the agent never needs to engineer a scroll first.
    //
    // THE `structured &&` GATE IS DELIBERATE AND NOW MEASURED. It looks
    // indefensible — element EXISTENCE depending on which output format the
    // caller asked for, so `find` can reach a below-fold button that `read_page`
    // cannot see on the same page in the same instant. It was removed on exactly
    // that argument and `tools/bench_trajectory.py` priced all three variants
    // over Mind2Web's labelled gold paths:
    //
    //   variant                          first-read reachable   tokens to completion
    //   viewport-scoped (this code)                     50.9%                369,028
    //   every offscreen row listed, cap 150             71.1%                558,628
    //   every offscreen row listed, cap lifted          93.6%              1,250,977
    //   offscreen rows only when they FOLD              50.9%                412,665
    //
    // All four end at the SAME 96.0% recoverable, because the listing says what
    // is off-viewport and `find` reaches it by ref. The viewport-scoped listing
    // gets there for a third of the budget — ~1,400 tokens over ~1.5 reads per
    // step against ~6,600 over ~1.1. The compact-only variant was worse than
    // both: offscreen entries consume the 150 entry slots (the cap runs BEFORE
    // folding) and then print nothing, evicting on-screen rows — over_cap steps
    // went 43 -> 69.
    //
    // So the trade CLAUDE.md #6 recorded is real and well priced, and the tidy
    // architectural argument did not survive being measured. Whole-page reach
    // has to get cheaper before it can be afforded, which is what a region index
    // is for — naming an off-viewport region costs one line, listing its
    // contents costs hundreds. Do not remove this gate again without a
    // representation that makes the 1,250,977 column affordable.
    // A SCOPED READ IS NOT VIEWPORT-LIMITED. The whole-page token argument above
    // is about not paying for a page the caller did not ask for. It does not apply
    // when the caller names ONE container: `read_page(ref_id=…)` is a request for
    // that region, and answering it with "nothing here, it is below the fold" made
    // the region index useless — the agent would be told where its target was and
    // then be unable to read it without scrolling anyway. Measured cost of the
    // blind scroll it replaces: 76 of 173 gold-path steps, at a full re-read each.
    const keepForFind = (structured || !!scopeMmid) && visible && !inViewport && (() => {
      const rr = el.getAttribute('role');
      if (['a', 'button'].includes(tagL) || formyTags.has(tagL) ||
          (rr && strongInteractiveRoles.has(rr))) return true;
      // AN ELEMENT THAT PASSED isInteractive IS A CONTROL. This predicate used to
      // be NARROWER than the interactivity test: a handler-bound <div>/<span>/
      // <label> qualified as interactive, then was dropped for being below the
      // fold, while a <button> in the same position was kept. The two rules
      // disagreed about what counts as a control.
      //
      // MEASURED: of 10 out-of-sample Mind2Web targets we missed, SIX were
      // dropped by `outside-viewport` immediately after handler tagging made them
      // interactive — 60% of the entire accuracy gap, from this one asymmetry.
      // Only 2 were recovered by handler tagging alone, which killed the standing
      // "our recall is only a static-HTML floor" explanation.
      //
      // Gated on a real activation signal rather than on tag names, so this
      // widens reach without admitting inert text: an explicit handler, a
      // pointer cursor, or focusability.
      try {
        if (el.__abClickBound) return true;
        if (el.hasAttribute('onclick') || el.hasAttribute('tabindex')) return true;
        if (getComputedStyle(el).cursor === 'pointer') return true;
      } catch (e) {}
      return false;
    })();
    // COUNT ONLY WHAT IS ACTUALLY ABSENT. This tally drives the "N more elements
    // are BELOW the current viewport — scroll down" hint, and it used to run
    // BEFORE the keep decision, predicting the drop rather than following it.
    // In the string path those are the same population, so it read correctly;
    // in the STRUCTURED path they are not, and the count advertised a scroll to
    // reach elements that were in the array already. Following the drop is right
    // in both, and it is what keeps the count honest if the keep rule ever
    // widens again.
    if (visible && !inViewport && !inModal && !keepForFind) {
      const _bfRole = el.getAttribute('role');
      const _real = ['a','button'].includes(tagL) || formyTags.has(tagL) ||
                    (_bfRole && strongInteractiveRoles.has(_bfRole));
      // WHERE, not just how many. "76 more elements are BELOW the viewport" tells
      // the agent to scroll and re-read the whole page — measured at 76 of 173
      // gold-path steps, a full extra listing each. Naming the REGIONS costs a few
      // words and lets it scope straight to one with read_page(ref_id=…), which is
      // now possible because a scoped read is no longer viewport-limited.
      if (_real) {
        // GROUP BY THE CONTAINER ELEMENT, NOT BY ITS LABEL.
        //
        // This bucketed on `section(el)` — a LABEL — and then took the ref from
        // `closest()` on whichever element happened to arrive first in that bucket.
        // Both halves of that are wrong, and three live audits caught it:
        //   - One label spans many containers. Al Jazeera has 20 <footer> elements,
        //     so 34 elements labelled `footer` were counted together while the ref
        //     came from a 1-link card footer. The hint promised `footer(ref_813): 34`
        //     and the scoped read returned ONE row, under a header stating that
        //     elements outside the scope are omitted. The real 33-link footer was
        //     never named at all.
        //   - Many labels resolve to one container. Naver printed
        //     `tabpanel(ref_265): 50, main(ref_265): 20, tablist(ref_265): 12` —
        //     one <div id=container role=main> named three times with three counts.
        //   - And BBC's `main(ref_410): 34` pointed at a card container inside main,
        //     not at main.
        //
        // Keying on the container's own mmid makes the count and the ref describe
        // the same element by construction, and labelling it from THAT element
        // stops the label naming something the ref is not.
        try {
          const _host = el.closest && el.closest('main, nav, header, footer, aside, form, section, article, [role=main], [role=navigation], [role=banner], [role=contentinfo], [role=complementary], [role=search]');
          const _hm = (_host && _host.getAttribute && _host.getAttribute('mmid')) || null;
          if (_hm) {
            const k = 'r' + _hm;
            if (!_offRegions[k]) {
              let _lb = (_host.tagName || '').toLowerCase();
              try { _lb = _host.getAttribute('role') || _lb; } catch (e2) {}
              _offRegions[k] = { n: 0, mmid: String(_hm), label: _lb };
            }
            _offRegions[k].n++;
          } else {
            // No enclosing landmark with a ref. Counted so the totals still add up,
            // but never named with a ref it does not have — the previous version
            // printed `page: 1` inside a sentence that says "using the ref shown".
            if (!_offRegions.__noref) _offRegions.__noref = { n: 0, mmid: null, label: '' };
            _offRegions.__noref.n++;
          }
        } catch (e) {}
      }
      if (_real && ay >= vh) belowFoldCount++;
      else if (_real && (ay + r.height) <= 0) aboveFoldCount++;
      // The viewport has TWO axes. Controls parked off to the side — carousel
      // slides, kanban columns, an RTL page scrolled horizontally — were counted
      // by neither branch and hinted by nothing, so read_page said the page was
      // complete when it was not.
      else if (_real && (ax >= vw || (ax + r.width) <= 0)) sideCount++;
    }
    if (!visible || (!inViewport && !inModal && !keepForFind)) return _drop(el, !visible ? 'not-visible' : 'outside-viewport');
    // Sub-8×8 elements are almost always decoration: SVG path fragments, hover
    // hot-spots, screen-reader spacers. Semantics beat pixels though — a 6×6
    // styled role=checkbox/radio/switch is a real control (dense dashboards,
    // compact toggles); explicit widget roles are exempt along with form tags.
    if (r.width < 8 || r.height < 8) {
      const _szRole = el.getAttribute('role');
      // A NAMED NATIVE CONTROL is semantics at its strongest and outranks its
      // pixel size just as an explicit widget role does. Amazon's header ships
      // its language switcher and account menu as 8x4 <button>s carrying real
      // aria-labels ("Expand to Change Language or Country"); the bare size test
      // dropped both from the listing on .com and .de, so the agent could not
      // reach the site's own language control. Still requires ~3px in the
      // smaller dimension, which keeps genuinely zero-area sr-only anchors and
      // tracking pixels out.
      const _szNamed = ['a', 'button', 'summary'].includes(tagL) &&
        Math.min(r.width, r.height) >= 3 &&
        !!((el.getAttribute('aria-label') || el.getAttribute('title') ||
            (el.innerText || '')).trim());
      // HEURISTIC DEMOTED TO A NON-DECISION. A heuristic may decide PROMINENCE;
      // only a specification may decide EXISTENCE. This predicate is decided by
      // how a page HAPPENS to be built (pixels/ratios/tags), so its accuracy on a
      // site nobody has seen is unknowable — and when it is wrong it is SILENT.
      // Measured: removing the whole family of threshold rules costs +6.8%
      // listing chars (median page +1.8%) against a 3.3% drift floor, while the
      // constant legend block costs 24.4% and buys nothing. The filters were not
      // buying tokens; they were buying unbounded silent failure.
      // Kept as a LEDGER RECORD so `ledger:true` still explains the page.
      if (!formyTags.has(tagL) && !(_szRole && INTERACTIVE_ROLES.has(_szRole)) && !_szNamed) _note(el, 'was:too-small-unnamed');
    }
    // INNER-SCROLL-CONTAINER CLIPPING: an element scrolled out of view inside an
    // overflow:auto/scroll panel (chat sidebar, results list, dropdown body) is
    // NOT "occluded by an overlay" — but the old code let it reach the
    // elementFromPoint test, which flagged it (occluded/blocked) and steered the
    // agent away from a perfectly reachable list row. Detect the real cause:
    // center outside the visible box of a scrollable composed ancestor. Clicks
    // auto-scroll (scrollIntoView in _clickPage), so these stay fully actionable.
    // Is the element ITSELF a scroll container (sidebar nav, chat panel, long
    // dropdown body)? Then (a) it's a region, not a click target — never tag it
    // "scrolled out", and (b) the agent benefits from knowing its content
    // scrolls independently of the page.
    let scrollRegion = false;
    try {
      scrollRegion = (/(auto|scroll)/.test(cs.overflowY) && el.scrollHeight > el.clientHeight + 4) ||
                     (/(auto|scroll)/.test(cs.overflowX) && el.scrollWidth  > el.clientWidth  + 4);
    } catch (e) {}
    let clippedInContainer = false;
    let clipContainerMmid = null;   // which scroll panel clips it (for listing compaction)
    // Guards: container-sized elements (taller/wider than the viewport) have a
    // meaningless center point — they're wrappers, not targets.
    if (inViewport && !inModal && !scrollRegion && r.height < vh && r.width < vw) {
      try {
        // Center coords stay in the CURRENT document's space; when the walk
        // crosses a frame boundary they are re-expressed in the parent
        // document's space, so every comparison is same-space.
        let ccx = r.left + r.width / 2, ccy = r.top + r.height / 2;
        let anc = composedParent(el);
        while (anc && anc !== document.body && anc.nodeType === 1) {
          if (anc.tagName === 'IFRAME' || anc.tagName === 'FRAME') {
            // The frame's viewport clips its content exactly like a scroll
            // container (iframes scroll internally).
            const fch = anc.clientHeight || 0, fcw = anc.clientWidth || 0;
            if (ccx < 0 || ccy < 0 || (fch && ccy > fch) || (fcw && ccx > fcw)) {
              clippedInContainer = true; break;
            }
            const frR = anc.getBoundingClientRect();
            ccx += frR.left + (anc.clientLeft || 0);
            ccy += frR.top + (anc.clientTop || 0);
            anc = composedParent(anc);
            continue;
          }
          let isScroller = scrollAncCache.get(anc);
          if (isScroller === undefined) {
            let acs; try { acs = ((anc.ownerDocument && anc.ownerDocument.defaultView) || window).getComputedStyle(anc); } catch (e) { acs = null; }
            // overflow:hidden deliberately NOT counted: those containers can't
            // be scrolled by the user — they're crops by design, and the 1×1
            // overflow-hidden wrapper is the standard visually-hidden (sr-only)
            // pattern. Telling the agent to "scroll" one is a false trail.
            isScroller = !!acs &&
              ((/(auto|scroll)/.test(acs.overflowY) && anc.scrollHeight > anc.clientHeight + 4) ||
               (/(auto|scroll)/.test(acs.overflowX) && anc.scrollWidth  > anc.clientWidth  + 4));
            scrollAncCache.set(anc, isScroller);
          }
          if (isScroller) {
            // Flag ONLY when scrolling this container could actually reveal the
            // element. CSS-offset a11y patterns (skip-links parked outside their
            // wrapper, clip-rect tricks) put the center outside the box too, but
            // no amount of scrolling brings them "back" — saying "scroll the
            // panel" for those is a false trail.
            const ar = anc.getBoundingClientRect();
            const canReveal =
              (ccy > ar.bottom && anc.scrollTop + anc.clientHeight < anc.scrollHeight - 2) ||
              (ccy < ar.top    && anc.scrollTop > 2) ||
              (ccx > ar.right  && anc.scrollLeft + anc.clientWidth < anc.scrollWidth - 2) ||
              (ccx < ar.left   && anc.scrollLeft > 2);
            if (canReveal) {
              clippedInContainer = true;
              clipContainerMmid = (anc.getAttribute && anc.getAttribute('mmid')) || null;
              break;
            }
          }
          anc = composedParent(anc);
        }
      } catch (e) {}
    }
    // Occlusion test (elementFromPoint) is only meaningful for elements
    // actually inside the current viewport. For below-fold/above-fold items
    // (which we still keep when they're in a modal), elementFromPoint at
    // their coordinates returns null because the point isn't visible -> the
    // element gets falsely labeled "occluded/blocked", and the agent then
    // avoids clicking the perfectly-good submit button at the bottom of the
    // modal. clickable=true for offscreen-but-keepable items.
    let clickable = true;
    let physBlocked = false;   // something (visible or not) is first at every sampled point
    // (pointer-events:none controls are invisible to hit-tests by definition —
    // they'd always read "occluded"; the (disabled) flag is the true story.)
    if (inViewport && !clippedInContainer && !peDisabled) {
      // Hit-test in the element's OWN document (frame-relative coords for
      // in-frame elements — the top document's elementFromPoint would just
      // return the <iframe> shell at those coordinates). Sample the center of
      // the VISIBLE portion (rect ∩ viewport), not the raw rect center —
      // viewport-spanning wrappers have their raw center offscreen, where
      // elementFromPoint returns null and falsely flags them occluded.
      try {
        const ow = (el.ownerDocument && el.ownerDocument.defaultView) || window;
        const ix0 = Math.max(r.left, 0), iy0 = Math.max(r.top, 0);
        const ix1 = Math.min(r.right, ow.innerWidth || vw), iy1 = Math.min(r.bottom, ow.innerHeight || vh);
        const cx = (ix0 + ix1) / 2, cy = (iy0 + iy1) / 2;
        const odoc = el.ownerDocument || document;
        let topEl = odoc.elementFromPoint(cx, cy);
        // Composed-tree containment: for an element INSIDE a shadow root,
        // elementFromPoint returns its outermost HOST, and host.contains(el)
        // is false across the shadow boundary — el.contains/topEl.contains
        // alone would falsely flag every shadow control as occluded. Walk
        // composed parents instead.
        const composedHas = (a, b) => {   // is `a` an ancestor-or-self of `b` in the composed tree
          let n = b;
          while (n) { if (n === a) return true; n = composedParent(n); }
          return false;
        };
        const hits = (t) => !!(t && (t === el || composedHas(el, t) || composedHas(t, el)));
        // Does an occluder actually PAINT anything? Transparent passthrough
        // layers (Habr's full-page misprint-selection overlay) sit on top in
        // hit-testing but render no pixels — clicks behaviorally reach the
        // controls beneath, so they must not flag (occluded/blocked). A real
        // modal backdrop paints (rgba bg) and still blocks.
        const paintsPixels = (n, depth) => {
          try {
            const c = ((n.ownerDocument && n.ownerDocument.defaultView) || window).getComputedStyle(n);
            if (parseFloat(c.opacity || '1') === 0) return false;
            // ANCESTOR-AWARE invisibility: computed opacity is NOT inherited —
            // a content clone inside an opacity-0 overlay (Habr's misprint
            // layer duplicates the page text invisibly) reports opacity 1 on
            // every child. checkVisibility accounts for the ancestor chain.
            if (n.checkVisibility && !n.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false;
            const bg = c.backgroundColor || '';
            if (bg && bg !== 'transparent' && !/rgba\(\s*\d+,\s*\d+,\s*\d+,\s*0\s*\)/.test(bg)) return true;
            if (c.backgroundImage && c.backgroundImage !== 'none') return true;
            const tn = n.tagName;
            if (tn === 'IMG' || tn === 'CANVAS' || tn === 'VIDEO' || tn === 'svg' || tn === 'SVG') return true;
            // Text only paints when its color has alpha (color:transparent
            // clones don't).
            const colTransparent = c.color === 'transparent' || /rgba\(\s*\d+,\s*\d+,\s*\d+,\s*0\s*\)/.test(c.color || '');
            if (!colTransparent) {
              for (const ch of n.childNodes) if (ch.nodeType === 3 && ch.textContent.trim()) return true;
            }
            if (parseFloat(c.borderTopWidth || '0') > 0 && c.borderTopStyle !== 'none') return true;
            // Shadow hosts paint via their SHADOW children (sl-dialog's host is
            // bare; its rgba backdrop lives inside the shadow root).
            if (n.shadowRoot && (depth || 0) < 2) {
              for (const sc of n.shadowRoot.children) if (paintsPixels(sc, (depth || 0) + 1)) return true;
            }
            return false;
          } catch (e) { return true; }
        };
        // TWO-TIER occlusion:
        //  - physBlocked: is something — visible or not — physically first at
        //    every sampled point? Drives the MODAL/OVERLAY heuristics (an
        //    invisible click-blocker like OpenUI5's TrustArc layer IS modality
        //    evidence).
        //  - clickable: paint-aware stack walk that passes through paint-less
        //    layers (Habr's transparent misprint overlay sits over everything
        //    but clicks behaviorally reach the controls). Drives the
        //    per-element (occluded/blocked) flag.
        const rawHit = (px, py) => { try { return hits(odoc.elementFromPoint(px, py)); } catch (e) { return false; } };
        const passHit = (px, py) => {
          let stack = [];
          try { stack = odoc.elementsFromPoint(px, py) || []; } catch (e) { return true; }
          // AN EMPTY STACK IS NOT EVIDENCE OF OCCLUSION. elementsFromPoint returns
          // [] for a point outside the viewport, so an element merely CLIPPED by
          // the fold — centre a few px past the bottom edge — scored "blocked"
          // with nothing painted over it. Two live agents hit this: Reddit
          // sidebar rows (centre y=687, viewport 672) and a Google Flights field
          // scrolled above the top (box y=-47), the latter flagged occluded in
          // the SAME listing that separately and correctly said it was scrolled
          // past. The flag's legend promises "something is painted over it"; a
          // clipped element has no occluder, and telling an agent otherwise makes
          // it skip a control it could click. Unknown must resolve to NOT blocked.
          if (!stack.length) return true;
          for (const t of stack) {
            if (hits(t)) return true;
            if (paintsPixels(t)) return false;
          }
          return false;
        };
        const pts = [[cx, cy],
                     [ix0 + (ix1 - ix0) * 0.25, cy], [ix0 + (ix1 - ix0) * 0.75, cy],
                     [cx, iy0 + (iy1 - iy0) * 0.25], [cx, iy0 + (iy1 - iy0) * 0.75]];
        clickable = pts.some(p => passHit(p[0], p[1]));
        physBlocked = !pts.some(p => rawHit(p[0], p[1]));
      } catch (e) {}
    }
    // PHANTOM MIRRORS: opacity-hidden ancestors are allowed (operable hidden-
    // until-focus controls like MUI DateField sections pass their hit-test).
    // But opacity-hidden AND failing EVERY hit-test = a visually-hidden mirror
    // of a custom widget (React Aria renders hidden native <select>s behind its
    // styled buttons) — a duplicate the agent could waste a turn on. Drop.
    if (clickable === false) {
      try {
        // ...unless the thing covering it is its OWN label. That is the whole
        // point of the styled-control pattern: the label is on top and clicking
        // the label operates the control. Dropping those here undid the fix above.
        if (ownLabel) clickable = true;
        else if (el.checkVisibility && !el.checkVisibility({ checkOpacity: true })) return _drop(el, 'checkVisibility-false');
      } catch (e) {}
    }
    // SEMANTICALLY DISTINCT FIELD METADATA so the model never has to guess
    // whether a string is the field's NAME, its PLACEHOLDER hint, or its
    // current VALUE. The old single-label flattening (label = aria-label ||
    // value || placeholder || innerText) caused the model to misread Boxsy's
    // placeholder "Enter investor or fund name" as either an instruction or
    // a pre-filled value.
    //
    // accessibleName resolution follows the standard AccName algorithm,
    // simplified: aria-labelledby (IDs joined) -> aria-label ->
    // <label for=id> -> wrapping <label> -> name attr / title / alt.
    let accessibleName = '';
    try {
      // IDs are scoped to the element's own tree (document OR its shadow root) —
      // resolve aria-labelledby / label[for] against el.getRootNode(), otherwise
      // every labelled control inside a shadow root loses its name.
      const idRoot = (el.getRootNode && el.getRootNode().getElementById) ? el.getRootNode() : document;
      const ariaLabelledBy = el.getAttribute('aria-labelledby');
      if (ariaLabelledBy) {
        accessibleName = ariaLabelledBy.split(/\s+/)
          .map(id => { const n = idRoot.getElementById(id); return n ? (n.innerText || '').trim() : ''; })
          .filter(Boolean).join(' ');
      }
      if (!accessibleName) accessibleName = (el.getAttribute('aria-label') || '').trim();
      if (!accessibleName && el.id) {
        const lab = idRoot.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (lab) accessibleName = (lab.innerText || '').trim();
      }
      if (!accessibleName) {
        const wrap = el.closest && el.closest('label');
        // WHO THE LABEL BELONGS TO. AccName's "exclude the control's own subtree"
        // rule is written for a LABELABLE form control, and applying it to any
        // element that merely sits inside a <label> makes siblings SWAP names:
        // each one clones the label, removes itself, and is left holding the
        // other's text. Measured live on IKEA's price filters, all five rows —
        //   span "$0.00 - 499.99" @x=119 reported name="28 products28"
        //   span "28 products28"  @x=284 reported name="$0.00 - 499.99"
        // with the BOXES correct, so name and geometry disagreed and nothing
        // said so. A non-labelable element that has its own text is named by
        // that text; one with no text of its own may still adopt the label
        // (an icon-only <span role="checkbox"> legitimately needs it).
        const _labelable = /^(input|select|textarea|button|meter|output|progress)$/.test(tagL);
        let _ownText = '';
        try { _ownText = (el.innerText || '').replace(/\s+/g, ' ').trim(); } catch (e) {}
        if (wrap && (_labelable || !_ownText)) {
          // Per the AccName spec, a wrapping <label>'s name EXCLUDES the
          // control's own subtree — <label>Country <select>…</select></label>
          // must yield "Country", not "Country France". Clone-and-remove,
          // falling back to raw innerText if anything goes sideways.
          try {
            const clone = wrap.cloneNode(true);
            const ownMmid = el.getAttribute('mmid');
            const own = ownMmid && clone.querySelector(`[mmid="${ownMmid}"]`);
            if (own) own.remove();
            else { const sameTag = clone.querySelector(el.tagName.toLowerCase()); if (sameTag) sameTag.remove(); }
            accessibleName = _contentName(clone);
          } catch (e) {
            accessibleName = (wrap.innerText || '').trim();
          }
        }
      }
      // BUTTON-LIKE <input>: per HTML-AAM its accessible name comes from the
      // VALUE attribute — that is the text painted on the button. Without this
      // it fell through to the generic form-field branch below, got named after
      // its HTML `name` ("login-button"), and its visible label "Login" landed
      // in value= — the slot that means CURRENT CONTENTS. That inverts the one
      // distinction the name/value/placeholder split exists to make, on every
      // submit button on the web. Found by an agent reading a live listing, not
      // by any fixture.
      if (!accessibleName && tagL === 'input' && BUTTONISH_INPUT.has((el.getAttribute('type') || '').toLowerCase())) {
        // NO generic "Submit"/"Reset" default here — that is HTML-AAM's LAST
        // resort and applying it at name-resolution time makes an empty-value
        // submit look named, which stops the same-box collapse below from
        // adopting the visible label overlaid on it (G17: a bare
        // input[submit] under a span reading "Apply filters" lost that label
        // entirely). The default is applied after the collapse passes instead.
        accessibleName = (el.value || el.getAttribute('alt') || '').trim();
      }
      if (!accessibleName) {
        // Per AccName, for content elements VISIBLE TEXT outranks the title
        // attribute. Falling back to title while text exists turned Discourse's
        // "Support" link into name="Ask the community for help with…" (its
        // tooltip) — unmatchable for an agent told to "go to Support". Only
        // consult title/alt when the element has no visible text of its own.
        // The HTML `name` attribute is a form-submission key: meaningful
        // identity for form fields (saucedemo's "user-name"), junk on buttons
        // (OSM's name="button") — honor it for form tags only.
        const hasText = !!(el.innerText || '').trim();
        accessibleName = ((formyTags.has(tagL) ? el.getAttribute('name') : '') ||
                          (!hasText ? (el.getAttribute('title') || el.getAttribute('alt')) : '') ||
                          '').trim();
        // Framework templating bugs leak literal "undefined"/"null" into name
        // attributes (seen in the wild: name="undefined" on a Ryanair email
        // field) — actively misleading as an identity. Treat as unnamed so the
        // near=/placeholder fallbacks take over.
        if (accessibleName === 'undefined' || accessibleName === 'null') accessibleName = '';
      }
      // Strip any markup that leaked through (title attributes containing raw
      // HTML were observed verbatim in names on Discourse).
      if (accessibleName.indexOf('<') !== -1) accessibleName = accessibleName.replace(/<[^>]*>/g, ' ');
      // Templating-garbage names from ANY source (weather.com ships a button
      // with aria-label="[object Object]") — worse than no name at all.
      if (/^\[object [A-Za-z]*\]$/.test(accessibleName) ||
          accessibleName === 'undefined' || accessibleName === 'null') accessibleName = '';
    } catch (e) {}
    accessibleName = accessibleName.replace(/\s+/g, ' ').replace(/\s*\*\s*$/, '');
    // Ultra-short resolved names ("1", "X") are usually a shortcut digit or a
    // glyph from a wrapping label; the title attribute often carries the real
    // identity (Excalidraw tools: label text "2" but title "Rectangle — R or 2").
    // ...but only when it carries NO LETTERS. "1-2 chars means a shortcut glyph"
    // is a Latin assumption: 删除 / 确定 / 取消 / 예 are ordinary button labels, and
    // so are "OK" / "Go" / "EN". This rescue was replacing an author's explicit
    // aria-label with the first descendant [title] it could find, so an agent told
    // to click 删除 could not match the listing at all.
    // EMPTY NAME + BARE GLYPH TEXT: take a descendant's aria-label, per AccName's
    // name-from-content rule (a descendant contributes ITS accessible name, not its
    // text). The canonical shape is a date grid:
    //   <div role="gridcell"><div aria-label="Saturday, 29 August 2026">29</div></div>
    // Name resolved EMPTY, so the listing printed the bare text "29" — and the
    // rescue below could not help because it requires a non-empty name. Measured
    // live on Google Flights: eight indistinguishable "29" cells, and find() ranked
    // 29 OCTOBER first for a query that said 29 August 2026, while both data-iso and
    // the child aria-label sat one attribute away. Deliberately narrow — empty name
    // AND short letterless text AND a descendant label that actually says more —
    // so it cannot start renaming ordinary unnamed controls.
    if (!accessibleName) {
      try {
        const _bare = (el.innerText || '').trim();
        if (_bare && _bare.length <= 2 && !/\p{L}/u.test(_bare)) {
          const dl = el.querySelector && el.querySelector('[aria-label], [title]');
          const dt = dl ? (dl.getAttribute('aria-label') || dl.getAttribute('title') || '').trim() : '';
          if (dt.length > _bare.length) accessibleName = dt;
        }
      } catch (e) {}
    }
    if (accessibleName.length > 0 && accessibleName.length <= 2 && !/\p{L}/u.test(accessibleName)) {
      try {
        let tAttr = (el.getAttribute('title') || '').trim();
        if (!tAttr || tAttr.length <= 2) {
          const tc = el.querySelector && el.querySelector('[title], [aria-label]');
          if (tc) tAttr = (tc.getAttribute('title') || tc.getAttribute('aria-label') || '').trim();
        }
        if (tAttr.length > 2) {
          accessibleName = tAttr;
        } else {
          // Icon-sprite class as identity — see _iconClassHandle, which is the
          // single definition and is also reached from synthLabel for controls
          // that have no accessible name at all.
          try {
            const _ic2 = _iconClassHandle(el);
            if (_ic2) {
              accessibleName = _ic2 + ' (' + accessibleName + ')';
              try { el.__abSynthAttr = 'icon-class'; } catch (e2) {}
            }
          } catch (e) {}
        }
      } catch (e) {}
    }
    // Truncate at a WORD boundary with a visible marker — a hard slice cut
    // names mid-word ("…Amazon Deutschland. D") and hid that anything was cut.
    // (label: no cap — see NO PER-FIELD CAP above)

    const placeholderAttr = (el.getAttribute('placeholder') || '').trim();
    // BACKING NATIVE CONTROL for a custom combobox: the hidden <select>/<input> the
    // library replaced. Its value is DEFINITIVE and language-independent, so it beats
    // every text heuristic — non-empty means something IS selected whatever the
    // trigger renders; empty proves placeholder state even in a language we can't
    // read. Hoisted here so the (unselected) flag can consult it and the listing can
    // NAME it: a benchmark agent that received a correct (DEAD-DUPLICATE) verdict
    // still burned three calls verifying it, because a verdict isn't checkable but a
    // ref is.
    let _backing = null;
    {
      const _bRole = el.getAttribute('role');
      const _isCustomCombo = (_bRole === 'combobox' || _bRole === 'listbox' ||
                              (el.getAttribute('aria-haspopup') || '').toLowerCase() === 'listbox') &&
                             !['select', 'textarea'].includes(tagL);
      if (_isCustomCombo) {
        try {
          const isNative = (n) => {
            // A backing control is a native control the library HID to render its own widget.
            // Accepting any <input> was wrong: a hidden CSRF token, a neighbouring quantity
            // field, or a same-row checkbox got adopted as "the backing control" and then drove
            // four separate decisions (unselected, the ok:true short-circuit, backed-by=ref_N,
            // DEAD-DUPLICATE). Require a <select> (always a replaced control in this pattern) or
            // an <input> the page has VISUALLY HIDDEN — libraries always hide the original. A
            // VISIBLE input beside a widget is a different field, never its backing.
            if (!n || n === el) return false;
            if (n.tagName === 'SELECT') return true;
            if (n.tagName !== 'INPUT') return false;
            if (['checkbox','radio','button','submit','file','range'].includes((n.type || '').toLowerCase())) return false;
            try {
              const r = n.getBoundingClientRect();
              // type=hidden is NOT a library-hidden original. A widget library replaces a
              // real control and hides it with CSS (display:none / 1px / sr-only) because it
              // still needs to be focusable and form-serialisable; type=hidden can be neither.
              // Meanwhile type=hidden is exactly what CSRF tokens, ids and nonces use — the
              // zoo's W1 caught this adopting a Rails _token as a select's "backing control".
              if ((n.type || '').toLowerCase() === 'hidden') return false;
              if (r.width <= 4 || r.height <= 4) return true;
              const cs = getComputedStyle(n);
              return cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity || '1') === 0;
            } catch (e) { return false; }
          };
          let w = el;
          for (let d = 0; d < 3 && w && w !== document.body; d++) {
            let cand = null;
            if (isNative(w.previousElementSibling)) cand = w.previousElementSibling;
            else if (isNative(w.nextElementSibling)) cand = w.nextElementSibling;
            else { for (const ch of w.children) { if (isNative(ch)) { cand = ch; break; } } }
            if (cand) {
              const o = (cand.tagName === 'SELECT' && cand.options) ? cand.options[cand.selectedIndex] : null;
              _backing = {
                mmid: cand.getAttribute('mmid') || null,
                tag: cand.tagName.toLowerCase(),
                value: String(cand.value || '').trim(),
                text: o ? (o.text || '').trim().slice(0, 60) : '',
              };
              break;
            }
            // composed, not parentElement: a combobox rendered inside a web
            // component (Shoelace/Ionic/Vaadin selects) has its hidden native
            // <select> on the far side of the shadow boundary, where the walk
            // stopped dead and backed-by= / (unselected) both lost their only
            // language-independent evidence.
            w = composedParent(w);
          }
        } catch (e) {}
      }
    }
    let cePlaceholder = '';   // editor placeholder text rendered as a child node
    const currentValue = (() => {
      try {
        if (tagL === 'input' || tagL === 'textarea') {
          // A button-like input has no contents; its value is the label, and is
          // reported as the accessible name above.
          if (tagL === 'input' && BUTTONISH_INPUT.has((el.getAttribute('type') || '').toLowerCase())) return '';
          // A checkbox/radio has no CONTENTS — it has a checked state, which the
          // (checked) flag already carries. `el.value` is "on" by DOM default even
          // when the page set nothing, so it made an unchecked box read as ON and
          // was identical for checked and unchecked alike. Report the ATTRIBUTE
          // only, which is present exactly when the author chose a submit value.
          if (tagL === 'input' && /^(checkbox|radio)$/.test((el.getAttribute('type') || '').toLowerCase())) {
            return (el.getAttribute('value') || '').trim();
          }
          // An <input> holds one line a person typed — no cap. A <textarea> is
          // genuinely unbounded, so it keeps a generous MARKED bound, and only so
          // that one essay cannot evict every other row from max_chars. That is a
          // budget on unbounded content, not a guess about what matters.
          const _vRaw = (el.value || '').trim();
          const v = tagL === 'textarea' ? markCut(_vRaw, 4000) : _vRaw;
          if (v) return v;
          // INPUT-style comboboxes (Ant/Select2/Chosen pattern): the focusable
          // input stays EMPTY and the displayed selection ("Lucy") is rendered
          // on a sibling node inside the field wrapper — without this hoist the
          // combobox row shows no value and the agent can't tell what's chosen.
          // Walk up to 2 wrappers; take the wrapper's short visible text.
          // If the text-bearing node is class-marked as a placeholder (the
          // cross-library convention: ant-select-selection-placeholder,
          // select2-selection__placeholder, choices__placeholder…) it is a
          // HINT, not a value — return '' and let the unselected flag fire.
          if (tagL === 'input' && el.getAttribute('role') === 'combobox') {
            let w = el.parentElement;
            for (let d = 0; w && d < 2; d++, w = w.parentElement) {
              if (!_inFieldWrapper(w, el)) break;
              // Exclude BUTTON/icon text from the hoist — Naver's empty search
              // box reported value="ê²€ìƒ‰ ê²€ìƒ‰" (its adjacent search buttons'
              // labels). Only the selection-display text counts.
              let t = '';
              try {
                const clone = w.cloneNode(true);
                // Strip LABELS and helper/error prose too, not just controls. The
                // hoist is looking for the widget's SELECTION DISPLAY; a wrapper
                // that also contains <label>Film</label> and a helper <p> handed
                // back value="Film Wählen Sie Ihren Lieblingsfilm" for an EMPTY
                // field — an MUI Autocomplete with helperText is exactly this
                // shape, and the agent then believes a required field is filled.
                clone.querySelectorAll('button, [role="button"], input, select, textarea, svg,' +
                                       ' label, p, small, legend,' +
                // A DECLARED LIVE REGION IS NEVER A FIELD'S VALUE. Stack Overflow's
                // search reported value="Loading…" while the field was empty: the
                // text came from a sibling status node inside the wrapper. A page
                // that marks a node aria-live / role=status / role=alert / output
                // has SAID it is transient announcement text, so no vocabulary is
                // needed to know it is not the contents of an input.
                                       ' [aria-live], [role="status"], [role="alert"],' +
                                       ' [role="log"], [role="progressbar"], output')
                     .forEach(n => n.remove());
                // HELP AND ERROR TEXT, BY DECLARATION rather than by class name.
                // This used to strip [class*="helper"] and [class*="error"] — two
                // English words matched against author-chosen class names, so a
                // German "fehlertext" or a Japanese class matched nothing and the
                // prose landed in value=. HTML already has the association: the
                // field points at its description with aria-describedby and at its
                // error with aria-errormessage. Those ids survive cloneNode, so the
                // referenced nodes can be removed exactly.
                try {
                  const _ids = ((el.getAttribute('aria-describedby') || '') + ' ' +
                                (el.getAttribute('aria-errormessage') || '')).trim().split(/\s+/);
                  // Compared directly rather than built into a selector: an id is
                  // author-controlled text and interpolating it into
                  // querySelector is both an escaping hazard and needless here.
                  const _want = new Set(_ids.filter(Boolean));
                  if (_want.size) {
                    for (const _n of Array.from(clone.querySelectorAll('[id]'))) {
                      if (_want.has(_n.id)) _n.remove();
                    }
                  }
                } catch (e) {}
                t = (clone.textContent || '').trim().replace(/\s+/g, ' ');
              } catch (e) { t = (w.innerText || '').trim().replace(/\s+/g, ' '); }
              if (t && t.length <= 60) {
                try { if (w.querySelector('[class*="placeholder"]') || /placeholder/i.test(w.className || '')) return ''; } catch (e) {}
                // Wrapper text IDENTICAL to the field's accessible name is its
                // label/visual placeholder, not a value (Google Maps' empty
                // search reported value="Search Google Maps" — its own name).
                // CONTAINS, not equals: any leftover that still carries the field's
                // own name is label bleed, not a chosen value.
                if (accessibleName && t.toLowerCase().indexOf(accessibleName.toLowerCase()) !== -1) return '';
                // dup:markcut — this was a bare slice(0, 60): the last unmarked cut
                // in the value path, so a hoisted selection longer than 60 chars was
                // reported as if it were the whole value. #24 removed per-field caps
                // everywhere else; this one survived because it sits inside a
                // fallback nobody re-read. The 60 above is a "is this short enough to
                // be a selection display" TEST, which is a different question from
                // how much of it to print.
                return markCut(t, 4000);
              }
            }
          }
          return '';
        }
        if (tagL === 'select') {
          const o = el.options && el.options[el.selectedIndex];
          // A SELECTED OPTION'S TEXT IS THE FIELD'S CONTENTS — no cap. This was the
          // one survivor of the no-cap sweep: a bare clip() rather than markCut, so
          // a 413-char timezone option came back as 60 chars ending mid-word inside
          // "extended", with no marker, in read_page AND find AND delta — because
          // the cut happens at COLLECTION time and poisons every consumer. In the
          // same tool run form_input's echo of the identical string was correct.
          return o ? (o.text || '').trim() : '';
        }
        // Rich-text / code editor root: its typed text IS the current value.
        // For code editors, read the CONTENT node — the host's innerText
        // includes the line-number gutter, so an EMPTY editor reported
        // value="1" (the gutter) and tricked the agent into "clearing" it.
        if (ceRoot || codeEditor) {
          let src = el;
          if (codeEditor) {
            // Prefer the CONTENT layer over the host — the host's innerText also
            // contains the gutter. Library content classes first (precise), then
            // the general shapes an editor's text layer takes: the
            // contenteditable surface, or an explicit role=code/textbox layer.
            try {
              src = el.querySelector('.cm-content, .CodeMirror-code, .view-lines, .ace_text-layer, [class*="mq-root-block"]') ||
                    el.querySelector('[contenteditable="true"], [contenteditable=""], [role="code"], [role="textbox"]') ||
                    el;
            } catch (e) {}
          }
          // stripGutter is the belt to that braces: whichever layer we ended up
          // with, a run of consecutive line numbers is never the value. It runs
          // BEFORE the whitespace collapse — the line breaks are what tell a
          // gutter column apart from an inline one.
          // Editors hold documents, not field values. Clipping to 60 chars left an
          // agent asking "what code is in this editor?" with no way to get the answer
          // out of read_page at all — it had to dump the whole page via get_page_text,
          // which is exactly what scoping exists to avoid. `full` is opt-in and
          // usually scoped, so it can afford the real text.
          // MARK THE CUT. An unmarked 60-char slice of a code document reads as
          // the whole document: a live agent wrote to an editor four times and
          // saw a byte-identical value= every time, so it could not tell that
          // its writes were not landing. Every other truncation in the listing
          // marks itself; this one did not.
          const _raw = stripGutter(src.innerText || '').trim().replace(/\s+/g, ' ');
          const t = markCut(_raw, FULL ? 40000 : 4000);
          // An EMPTY editor renders its placeholder as a styled CHILD — that
          // text is a HINT, not contents (regex101's CodeMirror reported
          // value="insert your regular expression here"). Route to placeholder.
          try {
            const ph = src.querySelector('.cm-placeholder, [class*="placeholder"]');
            if (ph && (ph.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 60) === t) {
              cePlaceholder = t;
              return '';
            }
          } catch (e) {}
          return t;
        }
        if (el.getAttribute('role') === 'combobox') {
          // The trigger's visible text — but only if it's NOT placeholder-y.
          // Structural signal first: a [data-placeholder] attr on the trigger
          // or its value node marks placeholder state language-independently
          // (Radix/TipTap convention). The English wordlist is a supplement.
          try { if (_showingPlaceholder(el, (el.innerText || '').trim())) return ''; } catch (e) {}
          let t = (el.innerText || '').trim();
          // Display text held in a descendant readonly <input> (Syncfusion).
          if (!t) {
            try { const di = el.querySelector('input'); if (di && di.value) t = di.value.trim(); } catch (e) {}
          }
          if (/\.\.\.$|…$/.test(t)) return '';
          return t;
        }
        return '';
      } catch (e) { return ''; }
    })();
    // De-double BEFORE truncating: slicing first would split the second copy and
    // hide the doubling (e.g. "Explore all products in Kitchen Explore all prod…").
    let buttonText = (!formyTags.has(tagL) && !ceRoot && !codeEditor) ? collapseDoubled(_contentName(el)) : '';
    // Word-boundary truncation with a visible marker — a raw slice cut Habr's
    // article title at "…ÐºÐ°Ðº ÑƒÑÑ‚Ñ€Ð¾ÐµÐ½ Frisbe" (lost "eTube") with no signal.
    // (buttonText: no cap)

    // Single-label fallback for non-form elements and dedup logic that still
    // wants one string to compare on.
    let label = accessibleName || currentValue || placeholderAttr || buttonText;
    label = collapseDoubled(label.replace(/\s+/g, ' '));
    // Label-less element handling. Previously ALL no-label non-form elements were
    // silently dropped — which made real icon controls (✕ close, ⋮ menu, pencil
    // edit, hamburger, logo link, upvote arrow) vanish from the listing with no
    // breadcrumb, so the agent couldn't even know to escalate to analyze_screen.
    // New rule (general, no site code):
    //   - form field (input/textarea/select) -> keep (existing behavior).
    //   - STRONG interactive (real <a>/<button> or explicit interactive role) ->
    //     try to synthesize a handle (svg <title>, icon aria-label, img alt,
    //     data-*). If still nothing, keep it flagged as an unlabeled icon control
    //     so the agent can target its mmid (and knows analyze_screen may help).
    //   - everything else (generic element interactive only via cursor:pointer /
    //     tabindex / onclick, no label) -> still dropped as mystery noise.
    const _elRole = el.getAttribute('role');
    // A SIZEABLE CANVAS IS ALWAYS WORTH A ROW, labelled or not. The (canvas)
    // marker and its legend line already exist and say the right thing — "pixel
    // drawn UI, its contents are NOT in this listing, take a screenshot" — but
    // they were gated on the canvas having a name, i.e. they fired only for the
    // canvas that least needed them. Measured on chartjs.org: an 800x400 chart,
    // the centrepiece of the page, appeared in NO listing at any detail level,
    // leaving an unexplained 400px vertical gap between two rows. The agent
    // concluded the page was a nav sidebar and five buttons. A labelled control
    // announces itself; an unlabelled one is exactly the case the anti-silence
    // machinery exists for.
    const _bigCanvas = canvasLike && (() => {
      try { const _cr = el.getBoundingClientRect(); return _cr.width * _cr.height >= 40000; }
      catch (e) { return false; }
    })();   // ~200x200 and up
    const isStrongInteractive = (tagL === 'a' || tagL === 'button') ||
                                _bigCanvas ||
                                (_elRole && strongInteractiveRoles.has(_elRole));
    // Opaque cross-origin frame with no title/aria-label: its src hostname is
    // the most useful handle the DOM can offer ("js.stripe.com", "youtube.com").
    if (!label && crossFrame) {
      try { label = new URL(el.getAttribute('src') || '', location.href).hostname || ''; } catch (e) {}
    }
    let iconOnly = false;
    if (!label && !formyTags.has(tagL) && !ceRoot && !codeEditor && !crossFrame && !canvasLike) {
      if (isStrongInteractive) {
        label = synthLabel(el);
        iconOnly = !label;            // no synthesizable handle -> unlabeled icon control
      } else if (inModal) {
        // INSIDE an open dialog, even a generic unlabeled clickable matters —
        // modals are small, and the unnamed ✕-glyph close control is sometimes
        // the ONLY dismiss affordance (Godbolt's privacy modal).
        label = synthLabel(el);
        iconOnly = !label;
      } else if (peDisabled) {
        // A DISABLED CONTROL MUST NOT VANISH. This branch drops unlabelled generic
        // clickables as noise, which is right — but a control the page has
        // explicitly DISABLED is not noise, it is a fact about the form's state.
        // Measured live on demoqa: the City field (a react-select <div> wrapper,
        // pointer-events:none until a State is chosen) rendered the visible text
        // "Select City" and was dropped outright — so "there is no city field" and
        // "the city field unlocks after you pick a state" were the same output, and
        // that is what let find() answer a city query with the STATE field.
        // Its visible text is a usable handle even when its accessible name is not.
        label = synthLabel(el) || (el.innerText || '').replace(/\s+/g, ' ').trim();
        iconOnly = !label;
      } else {
        _note(el, 'was:generic-no-label');   // recorded, no longer removed
      }
    }
    // A BADGE IS NOT A NAME. The icon-handle rescue keyed on `accessibleName`,
    // but a link or button whose only content is an icon plus a count has an
    // EMPTY accessible name and a `label` of "3" taken from its text — so neither
    // the rescue (which requires a non-empty name) nor synthLabel (which requires
    // an empty label) was ever reached, and the messages menu listed as `a "3"`.
    // That is the exact failure the icon lookup's own comment describes.
    //
    // Same test as the rescue: a label of one or two characters with no letter in
    // any script is a glyph or a count, not an identity. Attributed, so the row
    // says the name came off a class name.
    if (!iconOnly && label && label.length <= 2 && !/\p{L}/u.test(label)) {
      try {
        const _ib = _iconClassHandle(el);
        if (_ib) {
          label = _ib + ' (' + label + ')';
          try { el.__abSynthAttr = 'icon-class'; } catch (e) {}
        }
      } catch (e) {}
    }
    // Unlabeled splitters/rails are never meaningful click targets, and a
    // fuzzy-matching agent can fire them by accident. Two signals, semantic
    // first: (a) role=separator or a resize cursor (the W3C/CSS way splitters
    // announce themselves) — definite; (b) extreme-sliver geometry (10×845
    // strips) — heuristic for markup-less ones.
    if (iconOnly) {
      const _sepRole = el.getAttribute('role') === 'separator';
      const _resizeCur = /^(col-resize|row-resize|ew-resize|ns-resize)$/.test(cs.cursor || '');
      if (_sepRole || _resizeCur) _note(el, 'was:separator-or-resize-handle');
      if (Math.min(r.width, r.height) <= 14 &&
          Math.max(r.width, r.height) >= 15 * Math.max(1, Math.min(r.width, r.height))) {
        // ...but a REAL control is not decoration however thin it is: an unlabelled
        // role=slider seek bar (600x8) and a thin <button> expander (400x12) are the
        // primary controls of a media player and an accordion. Only unlabelled
        // GENERIC slivers are decoration.
        const _sr = el.getAttribute('role');
        // NOT <a>: a labelless 10x200 anchor is a splitter or a rail, and exempting
        // it re-listed exactly the decoration this rule exists to remove (G15). A
        // <button> or a form control or an explicit interactive role is a control by
        // its own semantics, however thin it is rendered.
        const _realThin = ['button', 'input', 'select', 'textarea'].includes(tagL)
                          || (_sr && INTERACTIVE_ROLES.has(_sr));
        if (!_realThin) _note(el, 'was:sliver-decoration');
      }
    }
    // Parent-child dedup: if an ancestor with the SAME trimmed label is already
    // in the listing, this child is just a redundant inner node (e.g. a <span>
    // inside the <a> we already listed). The click target is the outer one.
    //
    // EXCEPTION: structural container roles (menu, listbox, dialog, tablist,
    // tabpanel, grid, tree, radiogroup, menubar, group) own legitimately distinct
    // children. A role=menu container often inherits the trigger's accessibleName
    // (Radix sets aria-labelledby pointing to the trigger), so its first
    // menuitem may share the same label — we MUST keep both. Without this
    // exception, the first item of every dropdown menu silently disappears
    // from the listing and the agent can't pick it.
    const CONTAINER_ROLES = new Set(['menu','menubar','listbox','dialog','alertdialog','tablist','tabpanel','grid','treegrid','tree','radiogroup','group','toolbar','region']);
    // Is this element interactive ONLY because of cursor:pointer (not a real
    // control by tag/role/onclick/tabindex/contenteditable)? Such elements are
    // almost always styled INNER nodes of a real link/button — the carousel-tile
    // <span>, the doc-card <div>, the inner label <span>. When a real interactive
    // ancestor is already listed, they're redundant noise. This generalizes the
    // same-label dedup to the common case where the child's TEXT differs from the
    // parent's accessible NAME (e.g. <a name="Cooker"><span>Cooker Cooker</span>).
    const _rCur = el.getAttribute('role');
    const cursorOnly = !(['a','button','input','select','textarea'].includes(tagL)
      || (_rCur && INTERACTIVE_ROLES.has(_rCur))
      || el.hasAttribute('onclick') || el.hasAttribute('tabindex') || el.isContentEditable
      || el.__abClickBound);   // a bound JS handler = a real control, not styled noise
    if (label || cursorOnly) {
      // composedParent from the start: el.parentElement is null for a shadow
      // root's direct child, which silently skipped the whole dedup walk.
      let walker = composedParent(el), skip = false;
      while (walker && walker !== document.body) {
        const pMmid = walker.getAttribute && walker.getAttribute('mmid');
        if (pMmid && addedMmids.has(pMmid)) {
          const parentEntry = outByMmid.get(pMmid);
          if (parentEntry) {
            const parentRole = parentEntry.role || '';
            const parentTag  = parentEntry.tag  || '';
            const isContainer = CONTAINER_ROLES.has(parentRole) ||
                                ['dialog','ul','ol','table','form','fieldset','section'].includes(parentTag);
            const parentStrong = ['a','button','input','select','textarea'].includes(parentTag) ||
                                 strongInteractiveRoles.has(parentRole);
            // (A) cursor-only inner node of a real control above it -> redundant.
            // AREA GUARD: a widget-scale wrapper link (daterangepicker's
            // "Click for a Live Demo" anchor laid over its whole widget, ~23%
            // of the viewport) must not swallow the distinct controls beneath
            // it. Ordinary card/tile links sit well under 15%.
            if (cursorOnly && parentStrong && !isContainer &&
                parentEntry.w * parentEntry.h <= 0.15 * vw * vh) { skip = true; break; }
            // (A2) cursor-only cell/fragment inside a listed DATA ROW: the
            // <tr>'s own text already carries every cell value; re-listing each
            // td/span/div tripled CoinMarketCap rows to ~9 entries and burned
            // the cap after 6 rows. Real controls inside the row (links,
            // buttons, inputs) are NOT cursor-only and stay listed.
            if (cursorOnly && (parentTag === 'tr' || parentRole === 'row')) { skip = true; break; }
            // (B) same-label child of a non-container ancestor -> redundant inner node.
            // GUARD: never sacrifice a REAL control (form field / strong role /
            // editor) to a generic styled wrapper — value-hoisting gives an
            // Ant-style combobox input the same label as its wrapper div, and
            // without this guard the dedup kept the div and dropped the input.
            const childIsControl = formyTags.has(tagL) || isStrongInteractive || ceRoot || codeEditor;
            const parentIsControl = parentStrong || formyTags.has(parentTag);
            if (label && parentEntry.label === label && !isContainer &&
                !(childIsControl && !parentIsControl)) { skip = true; break; }
          }
        }
        walker = composedParent(walker);
      }
      // DEMOTE, NOT DELETE. Same-label container suppression is a guess about
      // which of two nested elements the reader means, and a guess must never
      // decide what EXISTS. The tree makes the deletion unnecessary as well as
      // wrong: a flat list cannot say "this one is inside that one", so it had
      // to pick; the tree indents the child under the parent and says it by
      // position. The guard below still protects a real control from being
      // demoted in favour of a generic wrapper.
      if (skip) _note(el, 'was:parent-child-dedup');
    }
    const _mmid = el.getAttribute('mmid');
    // Interactive ONLY via a bound JS handler, with no semantic role/tag of its own:
    // candidate delegation root (React/Vue bind on the app container). Confirmed in
    // the post-pass if it turns out to contain other listed controls.
    try {
      if (el.__abClickBound && !['a','button','input','select','textarea','summary'].includes(tagL) &&
          !el.getAttribute('role') && !el.hasAttribute('onclick') && !el.hasAttribute('tabindex') &&
          !el.isContentEditable) {
        _handlerOnlyWrappers.add(_mmid);
      }
    } catch (e) {}
    addedMmids.add(_mmid);
    // Required-field detection. Checks, in order of reliability:
    //   1. aria-required="true" or `required` attribute on the element
    //   2. aria-required="true" on the closest container
    //   3. The element's resolved <label>'s text ends with "*" (shadcn/MUI pattern:
    //      <Label>Name <span className="text-red-500">*</span></Label> — accessibleName
    //      is "Name *" and we trim the trailing star but remember it). This is
    //      scoped to the ACTUAL label, not a generic 4-level walk-up, so it
    //      can't leak from a neighbouring field's row.
    let required = false;
    try {
      if (el.getAttribute('aria-required') === 'true' || el.hasAttribute('required')) {
        required = true;
      } else {
        // aria-required on a CONTAINER only counts when the container wraps a
        // single control — a group-level aria-required (non-standard but seen)
        // was leaking (required) onto every field inside it.
        const reqAnc = el.closest && el.closest('[aria-required="true"]');
        if (reqAnc && reqAnc.querySelectorAll('input, select, textarea, [role="combobox"]').length <= 1) {
          required = true;
        } else {
          // Inspect the resolved label text (NOT the accessibleName, which we
          // already stripped the trailing "*" from). Both trailing AND leading
          // "*" count — RTL locales (Arabic/Hebrew) place the marker first.
          let labelText = '';
          if (el.id) {
            // IDs are scoped to the element's own tree. The accessible-name path
            // above already resolves against getRootNode(); this one still used
            // `document`, so a required field inside a web component silently
            // lost its (required) flag while its NAME resolved fine.
            const _lRoot = (el.getRootNode && el.getRootNode().querySelector) ? el.getRootNode() : document;
            const lab = _lRoot.querySelector(`label[for="${CSS.escape(el.id)}"]`);
            if (lab) labelText = (lab.innerText || '').trim();
          }
          if (!labelText) {
            const wrap = el.closest && el.closest('label');
            if (wrap) labelText = (wrap.innerText || '').trim();
          }
          if (labelText && (/\*\s*$/.test(labelText) || /^\s*\*/.test(labelText))) required = true;
        }
      }
    } catch (e) {}
    // Unselected-combobox detection. A Radix/shadcn/MUI Select trigger that
    // hasn't been picked yet shows placeholder text ("Select X...", "Choose…",
    // "Pick a Y") instead of a real value. Check the TRIGGER'S VISIBLE TEXT
    // (innerText) — NOT accessibleName, which is the field's identity label
    // (e.g. "Focus Areas") and would never match this heuristic.
    let unselected = false;
    try {
      const isCombo = el.getAttribute('role') === 'combobox'
        || tagL === 'select'
        || (el.getAttribute('aria-haspopup') === 'listbox');
      if (isCombo) {
        if (tagL === 'select') {
          // native select: unselected if nothing is selected, or the selected option
          // is a PROMPT rather than a choice.
          const _o = el.selectedIndex >= 0 ? el.options[el.selectedIndex] : null;
          const _v = _o ? (_o.value || '').trim() : '';
          unselected = !_o || !_v;
          // SENTINEL PROMPTS. "Empty value means prompt" assumes the author wrote
          // value="", and on older/e-commerce widgets they usually did not: Amazon's
          // size dropdown ships <option value="-1">Select</option>, so a page whose
          // own buy box says "To buy, select" reported value="Select" as a CHOSEN
          // size, in German and Japanese alike. Measured across four select-backed
          // prompts on real sites, THREE used a sentinel rather than an empty value
          // (-1, "default", and the prompt text itself) — this is the older-web norm,
          // not one retailer's quirk.
          // Structural and language-independent: it is the FIRST option, and either
          // its value is a conventional sentinel or the value IS the visible text
          // while its siblings' values are not (a real option list uses codes or ids).
          if (!unselected && _o && el.selectedIndex === 0 && el.options.length > 2) {
            const _txt = (_o.text || '').trim();
            const _isSentinel = /^(-1|0|default|none|null|undefined)$/i.test(_v);
            let _siblingsDiffer = false;
            try {
              let same = 0, seen = 0;
              for (let i = 1; i < el.options.length && seen < 6; i++, seen++) {
                const so = el.options[i];
                if ((so.value || '').trim() === (so.text || '').trim()) same++;
              }
              _siblingsDiffer = seen > 0 && same === 0;
            } catch (e) {}
            if (_isSentinel || (_v === _txt && _siblingsDiffer)) unselected = true;
          }
        } else if (tagL !== 'input' && tagL !== 'textarea') {
          // BUTTON/DIV trigger (Radix/shadcn/MUI Select). (unselected) means
          // "click then pick an option." Do NOT flag a text <input role=combobox>
          // (autocomplete/search): those are filled by TYPING, and an empty one is
          // simply blank — marking it (unselected) wrongly steers the agent to
          // open-and-pick instead of typing.
          let triggerText = (el.innerText || '').trim();
          // Span-based comboboxes (Syncfusion e-ddl) keep their display text in
          // a descendant readonly <input> — input.value is NOT innerText, so
          // the trigger looked empty and got a false (unselected).
          if (!triggerText) {
            try { const di = el.querySelector('input'); if (di && di.value) triggerText = di.value.trim(); } catch (e) {}
          }
          // Structural placeholder signal first ([data-placeholder] — language-
          // independent); then empty text; then the English wordlist/ellipsis
          // supplement. NOTE: a non-English text-only placeholder with no
          // ellipsis and no data-placeholder attr is structurally
          // indistinguishable from a chosen value — known residual limitation.
          let hasPlaceholderAttr = false;
          try { hasPlaceholderAttr = _showingPlaceholder(el, triggerText); } catch (e) {}
          if (hasPlaceholderAttr || !triggerText ||
              /\.\.\.$|…$/.test(triggerText)) unselected = true;
          // STRUCTURE BEATS WORDS, in both directions. A genuinely chosen option that
          // happens to start with select/choose/pick ("Select All Regions") was
          // reported as value="" + (unselected), sending the agent to re-pick what it
          // had already set. An empty backing control proves the inverse.
          // An EMPTY backing is weaker evidence than it looks: the sibling walk can
          // adopt an unrelated control. Compiler Explorer's toolbar holds three
          // <select>s, one of them empty, and adopting it flagged (unselected) on a
          // combobox plainly reading "C++" — a self-contradictory row that would send
          // an agent to re-pick a value it already had. Emptiness only counts when the
          // trigger is ALSO not displaying anything.
          if (_backing) {
            // ...but not over an explicit placeholder marker on the trigger. The
            // sibling walk can adopt an unrelated control (flatpickr's altInput
            // leaves a CSS-hidden original WITH a value next to the widget), and
            // trusting its value erased the language-independent data-placeholder
            // evidence this whole path is built on.
            if (_backing.value !== '' && !hasPlaceholderAttr) unselected = false;
            else if (!triggerText || hasPlaceholderAttr) unselected = true;
          }
        } else if (tagL === 'input') {
          // INPUT-style combobox (Ant/Select2/Chosen): flag (unselected) only
          // on STRUCTURAL evidence — empty input value plus a wrapper node
          // class-marked "placeholder" that is actually showing hint text.
          // (A typed-into autocomplete has a value; a chosen one renders the
          // selection without the placeholder node.) Language-independent.
          if (!(el.value || '').trim()) {
            let w = el.parentElement;
            for (let d = 0; w && d < 2; d++, w = w.parentElement) {
              if (!_inFieldWrapper(w, el)) break;
              try {
                const ph = w.querySelector('[class*="placeholder"]');
                if (ph && (ph.innerText || '').trim()) { unselected = true; break; }
              } catch (e) {}
            }
          }
        }
      }
    } catch (e) {}
    // NEARBY-CONTEXT identity for label-less form fields. flatpickr-style demo
    // pages have multiple bare inputs with identical placeholders and ZERO
    // accname markup — indistinguishable in the listing. AccName ends here, so
    // harvest a best-effort hint (rendered as near="...", clearly marked as
    // adjacent text, never claimed as the real name): the preceding inline
    // text ("Date:" before the input) or the nearest preceding heading.
    let nearLabel = '';
    if (!accessibleName && (formyTags.has(tagL) || ceRoot || codeEditor)) {
      try {
        // (trailing "#" = the permalink anchor doc generators append to headings)
        const short = (s) => { s = (s || '').replace(/\s+/g, ' ').replace(/\s*#\s*$/, '').trim(); return (s && s.length <= 60) ? s : ''; };
        // 1) preceding inline text/element within the field's own line.
        // Code-ish text ({};<>) is a snippet, not a label — skip it so the
        // heading walk below provides the hint instead.
        const labelish = (t) => t && !/[{};<>]/.test(t);
        let cur = el;
        for (let d = 0; d < 2 && !nearLabel && cur; d++) {
          let p = cur.previousSibling, hops = 0;
          while (p && hops < 3) {
            // `near=` IS DOCUMENTED AS "nearest VISIBLE text", and this walk read
            // things the user cannot see. `.textContent` on a COMMENT node returns
            // the comment body (unlike element.textContent, which excludes comment
            // descendants), and an element sibling's textContent includes
            // display:none text. Demonstrated live:
            //   <!-- SENTINEL --><select>            -> near="SENTINEL"
            //   <span style="display:none">X</span><input>  -> near="X"
            // and end to end, `<!-- promo code discount coupon --><input>` made
            // find("promo code coupon field") return that input under the confident
            // header `Found 1 element(s) matching` — an agent types its promo code
            // into a field whose only match is a developer's comment. `near=` now
            // counts as CONTENT coverage in find's scorer, so an invisible string
            // can carry a wrong element into the confident results.
            // The newer `_deepText` helper already handles both cases; this is an
            // un-migrated older path.
            if (p.nodeType === 8) { p = p.previousSibling; hops++; continue; }  // comment
            if (p.nodeType === 1) {
              let _vis = true;
              try {
                _vis = p.checkVisibility
                  ? p.checkVisibility({ checkVisibilityCSS: true })
                  : !!p.offsetParent;
              } catch (e) { _vis = true; }
              if (!_vis) { p = p.previousSibling; hops++; continue; }
            }
            const t = short(p.textContent);
            if (labelish(t)) { nearLabel = t; break; }
            if (t) break;   // there WAS preceding text but it's code — try headings
            p = p.previousSibling; hops++;
          }
          cur = cur.parentElement;
        }
        // 2) nearest preceding heading (walking up a few containers).
        if (!nearLabel) {
          let anc = el;
          for (let d = 0; d < 4 && anc && anc !== document.body && !nearLabel; d++, anc = anc.parentElement) {
            let sib = anc.previousElementSibling, k = 0;
            while (sib && k < 4 && !nearLabel) {
              if (/^H[1-6]$/.test(sib.tagName) || sib.getAttribute('role') === 'heading') {
                nearLabel = short(sib.innerText);
              } else if (sib.querySelector) {
                const h = sib.querySelector('h1,h2,h3,h4,h5,h6,[role="heading"]');
                if (h) nearLabel = short(h.innerText);
              }
              sib = sib.previousElementSibling; k++;
            }
          }
        }
      } catch (e) {}
    }
    // Bare-number labels ("338" — a TCF vendor-count button) are meaningless
    // alone; attach the surrounding text as context.
    // (\p{Nd}, not \d — Arabic-Indic and Devanagari digits are digits too.)
    if (!nearLabel && /^\p{Nd}{1,6}$/u.test((accessibleName || buttonText || '').trim())) {
      try {
        const p = el.parentElement;
        const t = p ? (p.innerText || '').replace(/\s+/g, ' ').trim() : '';
        if (t && t !== (accessibleName || buttonText) && t.length <= 60) nearLabel = t;
      } catch (e) {}
    }
    // Membership in a large homogeneous ARIA widget (calendar grid, long
    // listbox, radiogroup): recorded so the formatter can compact 30+ near-
    // identical cell lines into one mmid:label mapping block — pure token
    // savings, every cell keeps its clickable mmid.
    let groupKey = null, groupName = '', groupRole = '';
    {
      // In-page TOC runs: docs sites emit 15-40 `#hash` anchor links in one nav
      // rail ("On this page") that swamp the single real control on the page.
      // Group them so the compactor can fold the run into one mapping line.
      // Anchor jump-links (#hash) AND button-based jump lists (PrimeVue's right
      // rail scrolls via buttons, no href) — both are in-page TOCs. Buttons
      // qualify only when popup/disclosure-free (plain scroll triggers).
      const _tocCandidate = (tagL === 'a' &&
          (el.getAttribute('href') || '').length > 1 && (el.getAttribute('href') || '').startsWith('#')) ||
        // A button only counts as a TOC entry if it lives in a nav-ish rail. Without
        // that, EVERY popup-free button qualified, so any 10 sibling buttons — a
        // keypad, a toolbar, per-row actions — were folded under the banner
        // "in-page TOC", which is simply false and costs them their breadcrumbs.
        (tagL === 'button' && !el.getAttribute('aria-haspopup') && !el.hasAttribute('aria-expanded') &&
         !!(el.closest && el.closest('nav, aside, [role="navigation"], [role="doc-toc"]')));
      if (_tocCandidate) {
        {
          // Group by the OUTERMOST list/nav container: div-based TOC rails
          // (Docusaurus/Ionic) have no <nav> ancestor, and nested <ul>s would
          // otherwise fragment one TOC into many sub-10 groups.
          let anc = el.closest && el.closest('ul, ol, nav, aside, [role="navigation"], [role="doc-toc"]');
          let outermost = anc;
          while (anc && anc.parentElement) {
            anc = anc.parentElement.closest && anc.parentElement.closest('ul, ol, nav, aside, [role="navigation"], [role="doc-toc"]');
            if (anc) outermost = anc;
          }
          if (outermost && outermost.getAttribute('mmid')) {
            groupKey = 'toc:' + outermost.getAttribute('mmid');
            groupRole = 'in-page TOC';
            groupName = (outermost.getAttribute('aria-label') || '').trim().slice(0, 40);
          } else if (!outermost && el.parentElement && el.parentElement.getAttribute('mmid')) {
            // div-based TOC rails with no list/nav markup at all (shadcn's
            // "On This Page"): group hash-anchors by their direct parent.
            groupKey = 'toc:' + el.parentElement.getAttribute('mmid');
            groupRole = 'in-page TOC';
          }
        }
      }
      const _gRole = el.getAttribute('role');
      if (!groupKey && _gRole && ['gridcell','option','treeitem','menuitem','radio','row'].includes(_gRole)) {
        let ganc = composedParent(el);
        while (ganc && ganc !== document.body && ganc.nodeType === 1) {
          const gr = ganc.getAttribute ? ganc.getAttribute('role') : null;
          if (gr && ['grid','treegrid','listbox','tree','menu','menubar','radiogroup'].includes(gr)) {
            groupKey = ganc.getAttribute('mmid') || null;
            groupRole = gr;
            groupName = (ganc.getAttribute('aria-label') || '').trim().slice(0, 40);
            // COLUMN IDENTITY for data-grid cells: a compacted row ends with
            // values whose column can be off-screen — positional counting then
            // misassigns them. aria-colindex → matching columnheader text.
            if (_gRole === 'gridcell') {
              try {
                const ci = el.getAttribute('aria-colindex') ||
                           (el.parentElement && el.parentElement.children ? String([].indexOf.call(el.parentElement.children, el) + 1) : '');
                if (ci) {
                  const hd = ganc.querySelector(`[role="columnheader"][aria-colindex="${ci}"]`) ||
                             ganc.querySelectorAll('[role="columnheader"]')[parseInt(ci, 10) - 1];
                  const ht = hd ? (hd.innerText || '').replace(/\s+/g, ' ').trim() : '';
                  if (ht) nearLabel = nearLabel || ht;
                }
              } catch (e) {}
            }
            break;
          }
          ganc = composedParent(ganc);
        }
      }
    }
    // CUSTOM-WIDGET BACKING (drives dead-duplicate detection in the post-pass).
    // A JS combobox library (select2/chosen/selectize/Ant/…) replaces a native
    // <select> with a span/div widget and hides the original. If the page
    // double-initializes — or a re-render orphans a container — the DOM ends up
    // with TWO structurally identical widgets, only ONE of which is wired to a
    // real form control. Observed live on select2.org: the wired widget had
    // collapsed to 2px (invisible) while the 826px widget the user actually sees
    // was inert. Geometry and pixels both point at the WRONG one, so the only
    // honest signal is "does a native form control belong to this widget?".
    // widgetSig groups structurally-identical widgets; comboBacked records the
    // answer. Neither is acted on here — see the post-pass.
    let comboBacked = null, widgetSig = null;
    {
      const _cbRole = el.getAttribute('role');
      const _isCustomCombo = (_cbRole === 'combobox' || _cbRole === 'listbox' ||
                              (el.getAttribute('aria-haspopup') || '').toLowerCase() === 'listbox') &&
                             !['select', 'input', 'textarea'].includes(tagL);
      if (_isCustomCombo) {
        try {
          // SIGNATURE comes from the TRIGGER'S OWN shape, never from a
          // geometry-based wrapper walk. First attempt derived it by climbing
          // while the parent stayed near the trigger's box — which diverged
          // EXACTLY in the case this detects: the live widget had collapsed to
          // 2px so it stopped at the trigger (sig "span.select2-selection")
          // while the 826px orphan climbed to its container (sig "span.select2").
          // Different sigs -> different groups -> the comparison never ran and
          // the flag silently never fired on the real page.
          const cls0 = (n) => (typeof n.className === 'string' ? n.className.trim().split(/\s+/)[0] : '');
          widgetSig = `${tagL}.${cls0(el)}`;
          // SINGLE SOURCE OF TRUTH. This block used to run its OWN looser walk and
          // reset comboBacked=false first, silently overwriting the strict _backing
          // result computed above — so the DEAD-DUPLICATE comparison ran on the loose
          // answer while the listing's backed-by= used the strict one.
          comboBacked = !!_backing;
        } catch (e) { comboBacked = null; }
      }
    }
    // Inert controls: present but currently non-functional. Keep them listed
    // (the agent should know the control exists) but flagged, so it doesn't
    // burn turns clicking them or misread silence as a bug.
    // `(disabled)` MEANS THE PAGE SAID DISABLED. `pointer-events:none` is not that
    // claim — it is a paint/hit-testing property, and component libraries put it on
    // the real control while routing clicks through a wrapping <label> or an overlay.
    // Measured live, two independent agents:
    //   - Bootstrap's checks-radios page: 18 `.btn-check` rows all flagged
    //     (disabled); only 4 carry the attribute. One was clicked and its `.checked`
    //     went false -> true, so the flag was provably wrong on a working control.
    //   - Vuetify: ~20 rows flagged, including the children of a link marked
    //     `(current)` and of a tab marked `(selected)` — self-refuting on their face
    //     — and `find` reported `ref_3708 (disabled)` moments before `form_input`
    //     wrote to it successfully.
    // The legend promises "inert; clicking does nothing right now", so a wrong
    // (disabled) tells the agent NOT to act on something that works, and it also
    // destroys the marker's value where it is right: demoqa's genuinely disabled
    // City field uses the identical token, so on a Vuetify page the flag decides
    // nothing. The pointer-events observation is still recorded — it demotes the
    // element (`was:pointer-events-none`, visible in the ledger) — which is the
    // right home for an inference: prominence, never a claim about state.
    const disabled = el.disabled === true || el.getAttribute('aria-disabled') === 'true';
    const _entry = {
      mmid: _mmid,
      tag: tagL,
      type: el.getAttribute('type'),
      // A contenteditable/code-editor root with no explicit role IS a textbox.
      role: el.getAttribute('role') || ((ceRoot || codeEditor) ? 'textbox' : null),
      section: section(el),
      label,
      name: accessibleName,
      near: nearLabel,                  // adjacent-text hint for identity-less fields
      // NEAREST PRECEDING HEADING. Five buttons all labelled "Launch demo modal" and all
      // section=main are indistinguishable by name or section; a benchmark agent picked
      // the right one using outside knowledge of the page, not anything we told it. The
      // enclosing section's heading is the breadcrumb a human would use.
      underHeading: (() => {
        try {
          // VISIBLE headings only. A closed modal's own <h5>Modal title</h5> sits earlier
          // in the DOM than the button that opens it, so a naive nearest-preceding walk
          // returned "Modal title" for four different triggers instead of the section
          // they live under ("Live demo", "Grids in modals", ...). An invisible heading
          // is not a breadcrumb — it describes a panel the user cannot currently see.
          const vis = (h) => {
            try {
              if (!h.offsetParent && getComputedStyle(h).position !== 'fixed') return false;
              const r = h.getBoundingClientRect();
              return r.width > 0 && r.height > 0;
            } catch (e) { return false; }
          };
          // NO CAP HERE. This was `.slice(0, 40)` — a bare cut with no marker, in a
          // field an agent reads for context. Measured live on arXiv:
          //   under="Fri, 21 Aug 2026 (showing first 50 of 14"
          // where the heading is "…first 50 of 145 entries )". The count 145 arrived
          // as 14 — a WRONG NUMBER, the exact Wolfram-class failure (#14) where a
          // cut that does not look like a cut reads as a finished value.
          // #24 deleted the per-field caps for this reason and measured the cost at
          // +3.1% chars: a HEADING is bounded by human authorship already, so a cap
          // here buys nothing. The display side (`_q(underHeading, 200)` in
          // mcp_server.py) already marks a cut with its true residual if one is ever
          // needed, so removing the number removes the silence rather than moving it.
          const txt = (h) => (h.innerText || '').replace(/\s+/g, ' ').trim();
          let n = el, hops = 0;
          while (n && hops < 6) {
            let sib = n.previousElementSibling, k = 0;
            while (sib && k < 8) {
              if (/^H[1-6]$/.test(sib.tagName) && vis(sib)) { const t2 = txt(sib); if (t2) return t2; }
              if (sib.querySelectorAll) {
                const hs = Array.from(sib.querySelectorAll('h1,h2,h3,h4,h5,h6')).filter(vis);
                if (hs.length) { const t2 = txt(hs[hs.length - 1]); if (t2) return t2; }
              }
              sib = sib.previousElementSibling; k++;
            }
            n = composedParent(n); hops++;
          }
        } catch (e) {}
        return '';
      })(),
      placeholder: placeholderAttr || cePlaceholder,
      value: currentValue,
      text: buttonText,
      x: Math.round(ax), y: Math.round(ay),
      w: Math.round(aw), h: Math.round(ah),
      clickable,
      active: activeHint(el),
      required,
      unselected,
      disabled,
      synth: (function () { try { return el.__abSynthAttr || ''; } catch (e) { return ''; } })(),
      demoted: (function () { try { return _demotedRun.get(el) || ''; } catch (e) { return ''; } })(),
      newTab: tagL === 'a' && el.getAttribute('target') === '_blank',
      // Only meaningful for an element INSIDE a frame: in the top document a
      // target=_top link is an ordinary same-tab navigation and needs no flag.
      topNav: tagL === 'a' && /^(_top|_parent)$/.test(el.getAttribute('target') || '')
              && (el.ownerDocument || document) !== document,
      crossFrame,                       // opaque cross-origin iframe shell
      canvasLike,                       // pixel/vector drawing surface (canvas or class-marked div/svg)
      physBlocked,                      // physically covered (drives modal/overlay heuristics)
      editable: ceRoot,                 // rich-text editor root — type via enter_text_tool
      codeEditor,                       // CodeMirror/Monaco/Ace host — type via enter_text_tool
      scrollRegion,                     // element's own content scrolls independently
      clippedInContainer,               // scrolled out inside an inner scrollable panel (click auto-scrolls)
      clipContainerMmid,                // the panel that clips it (drives listing compaction)
      // Click-then-pick affordance: a trigger that opens a menu/popup, and
      // disclosure state when the widget reports one (aria-expanded=false).
      // <summary> always toggles a disclosure — same affordance as aria-haspopup
      // (GitHub's filter dropdowns are details/summary with no ARIA at all).
      // aria-expanded + aria-controls without aria-haspopup (Stripe/WordPress
      // mega-menus) is the SAME affordance — click expands in-page content.
      hasPopup: (() => {
        if (tagL === 'summary') return true;
        const hp = el.getAttribute('aria-haspopup');
        if (hp && hp !== 'false') return true;
        return el.hasAttribute('aria-expanded') && el.hasAttribute('aria-controls');
      })(),
      collapsed: el.getAttribute('aria-expanded') === 'false',
      groupKey, groupName, groupRole,   // large-widget membership for listing compaction
      comboBacked, widgetSig,           // custom-combobox wiring (dead-duplicate post-pass)
      backedBy: _backing && _backing.mmid ? _backing.mmid : null,   // checkable evidence, not a verdict
      orphanWidget: false,              // set by that post-pass
      iconOnly,  // strong control with no resolvable text label (render with a hint)
      offscreen: !inViewport,  // included but currently outside viewport (typically modal scroll content)
      href: WANT_URLS ? (BRIEF ? _briefUrl(_hrefOf(el)) : _hrefOf(el)) : '',
      src: WANT_URLS ? (BRIEF ? _briefUrl(_srcOf(el)) : _srcOf(el)) : '',
    };
    out.push(_entry);
    outByMmid.set(_mmid, _entry);
  });
  // WEB-COMPONENT HOST/INTERNAL COLLAPSE: with shadow piercing, a clickable
  // custom-element host (sl-button, ytd-…) AND the real control inside its
  // shadow root often BOTH survive as near-identical boxes — the same visual
  // control listed twice. Keep the INNER real control (it's the better action
  // target: a true <a href>/<button>/<input>), transfer the host's label to it
  // when the inner one is unlabeled (its visible text is usually <slot>ted into
  // the host's light DOM), and drop the host entry.
  {
    const byMmid = new Map(out.map(e => [e.mmid, e]));
    const removedHosts = new Set();
    for (const e of out) {
      const n = mmidReg.get(e.mmid);
      if (!n || !(n.getRootNode && n.getRootNode().host)) continue;  // only shadow residents
      let w = composedParent(n);
      while (w && w !== document.body) {
        const wm = w.getAttribute && w.getAttribute('mmid');
        if (wm && byMmid.has(wm)) {
          const h = byMmid.get(wm);
          if ((h.tag || '').includes('-') &&
              Math.abs(h.x - e.x) <= 4 && Math.abs(h.y - e.y) <= 4 &&
              Math.abs(h.w - e.w) <= 8 && Math.abs(h.h - e.h) <= 8) {
            if (!e.label && h.label) { e.label = h.label; e.iconOnly = false; }
            if (!e.name && h.name) e.name = h.name;
            removedHosts.add(h.mmid);
          }
          break;  // only the nearest LISTED composed ancestor matters
        }
        w = composedParent(w);
      }
    }
    if (removedHosts.size) {
      // DEMOTE, NOT DELETE. "Host and inner control are the same visual thing"
      // is inferred from a 4px/8px box tolerance — a chosen number, so it sets
      // prominence only. The label transfer above still happens, so the inner
      // control keeps the host's slotted text; the host keeps its ref, which
      // matters because a custom element can carry the handler its shadow child
      // does not.
      _noteEntries(out, removedHosts, 'was:shadow-host-collapse');
    }
  }
  // SAME-BOX WRAPPER COLLAPSE (light DOM): one visual control often survives as
  // 2-3 stacked entries — generic styled wrapper divs plus the real control
  // (MUI demo editors: two wrapper divs + the "Edit code" textarea, all at the
  // same box), or a label-overlay span sitting on an unnamed input[submit]
  // (Amazon dialogs: span "Dismiss" + input[submit]). Keep the REAL control,
  // transfer the generic twin's label if the control is unnamed, drop the twin.
  {
    const isRealControl = (e) => formyTags.has(e.tag) || e.tag === 'a' || e.tag === 'button' ||
      e.editable || e.codeEditor || (e.role && strongInteractiveRoles.has(e.role));
    const isGenericTwin = (e) => !isRealControl(e) && !e.role && !e.crossFrame && !e.groupKey &&
      !e.scrollRegion && ['div','span','p','li','td','label','img','ol','ul'].includes(e.tag);
    const sameBox = (a, b) => Math.abs(a.x - b.x) <= 4 && Math.abs(a.y - b.y) <= 4 &&
                              Math.abs(a.w - b.w) <= 8 && Math.abs(a.h - b.h) <= 8;
    // FIELD-WRAPPER variant: Ant/Select2-style comboboxes render the display
    // text on a slightly-LARGER wrapper around the focusable input — not the
    // same box, but the same visual control. Merge when the generic shell
    // tightly wraps a combobox/form control (area within 4×).
    const wrapsControl = (g, c) =>
      (c.role === 'combobox' || c.tag === 'button' || c.tag === 'a' || formyTags.has(c.tag)) &&
      g.x <= c.x + 4 && g.y <= c.y + 4 &&
      g.x + g.w >= c.x + c.w - 8 && g.y + g.h >= c.y + c.h - 8 &&
      g.w * g.h <= 4 * Math.max(1, c.w * c.h);
    const drop = new Set();
    for (const ctl of out) {
      if (!isRealControl(ctl)) continue;
      for (const g of out) {
        if (g === ctl || drop.has(g.mmid) || !isGenericTwin(g)) continue;
        if (!sameBox(ctl, g) && !wrapsControl(g, ctl)) continue;
        if (!ctl.name && !ctl.label && !ctl.text && (g.label || g.name || g.text)) {
          ctl.name = g.name || g.label || g.text;
          ctl.label = ctl.name;
          ctl.iconOnly = false;
        }
        // If the "occluder" at the control's center was this very twin (a label
        // overlay), the control is NOT actually blocked — clicks land fine.
        if (ctl.clickable === false && g.clickable !== false) ctl.clickable = true;
        drop.add(g.mmid);
      }
    }
    // GENERIC-GENERIC same-box pairs (eBay's li "More Expand: More" + inner
    // div "More" — neither is a "real control" tag, both are listed): keep the
    // INNER one (deeper = closer to the actual click handler), drop the shell.
    for (const a of out) {
      if (drop.has(a.mmid) || !isGenericTwin(a)) continue;
      for (const b of out) {
        if (a === b || drop.has(b.mmid) || !isGenericTwin(b)) continue;
        if (!sameBox(a, b)) continue;
        // a is the composed ancestor of b -> merge, KEEPING the richer-named
        // twin. (Naively keeping the inner one regressed Excalidraw: the inner
        // div's text is the shortcut digit "1" while the outer label carried
        // the rescued tool name "Rectangle — R or 2".)
        let n = mmidReg.get(b.mmid);
        n = n && composedParent(n);
        let isAnc = false;
        while (n) { if (n === mmidReg.get(a.mmid)) { isAnc = true; break; } n = composedParent(n); }
        if (isAnc) {
          const richness = (e) => ((e.name || '').length * 2 + (e.label || e.text || '').length);
          if (richness(a) > richness(b)) {
            if (!a.label && b.label) a.label = b.label;
            drop.add(b.mmid);
          } else {
            if (!b.name && a.name) { b.name = a.name; if (!b.label) b.label = a.name; }
            drop.add(a.mmid);
          }
          break;
        }
      }
    }
    if (drop.size) {
      // DEMOTE, NOT DELETE. Which of two same-box twins is "the" control is
      // decided here by a richness score — name length doubled plus label
      // length — i.e. a guess, and this file's own rule is that a guess may
      // set prominence and never existence. The label MERGE above stays: the
      // surviving twin still gets the richer name. The other keeps its ref.
      _noteEntries(out, drop, 'was:same-box-wrapper-collapse');
    }
  }
  // BUTTON-LIKE INPUT FALLBACK NAME, applied only now that every label-adoption
  // pass has had its chance. HTML-AAM's "Submit"/"Reset" default is better than
  // nothing, but worse than the label the page actually paints on the control.
  for (const e of out) {
    if (e.tag !== 'input' || e.name || e.label || e.text) continue;
    const t = (e.type || '').toLowerCase();
    if (t !== 'submit' && t !== 'reset') continue;
    e.name = t === 'submit' ? 'Submit' : 'Reset';
    e.label = e.name;
    e.iconOnly = false;
  }
  // DEAD-DUPLICATE CUSTOM WIDGETS: a JS combobox container left orphaned by
  // double-initialization looks IDENTICAL to the live one in the listing — and
  // on select2.org it is the bigger, fully-visible one while the wired widget
  // has collapsed to a 2px sliver, so both geometry and a screenshot point at
  // the dead control. Two agents independently picked wrong / burned calls on
  // this, so flag it.
  //
  // COMPARATIVE, never absolute: an unbacked widget is only called out when
  // another widget with the SAME wrapper signature on this page IS backed by a
  // native form control. That proves the library normally wires them here, so
  // the unbacked twin is leftover. Radix/shadcn/HeadlessUI/Base UI triggers are
  // never backed by a native control, so no group ever has a backed member and
  // NOTHING is flagged on those pages — the common case stays untouched.
  {
    const bySig = new Map();
    for (const e of out) {
      if (!e.widgetSig || e.comboBacked === null) continue;
      if (!bySig.has(e.widgetSig)) bySig.set(e.widgetSig, []);
      bySig.get(e.widgetSig).push(e);
    }
    for (const [, members] of bySig) {
      if (members.length < 2) continue;
      if (!members.some(m => m.comboBacked)) continue;   // library isn't wiring any -> not a duplicate situation
      for (const m of members) if (!m.comboBacked) m.orphanWidget = true;
    }
  }
  // DELEGATION-ROOT DROP: a handler-only wrapper that CONTAINS other listed controls
  // is the framework's event-delegation container, not something to click.
  if (_handlerOnlyWrappers.size) {
    const drop = new Set();
    for (const e of out) {
      if (!_handlerOnlyWrappers.has(e.mmid)) continue;
      const host = mmidReg.get(e.mmid);
      if (!host) continue;
      let contained = 0;
      for (const o of out) {
        if (o.mmid === e.mmid) continue;
        let n = mmidReg.get(o.mmid);
        while (n) { if (n === host) { contained++; break; } n = composedParent(n); }
        if (contained >= 8) break;
      }
      // >=8, not >=2. App/delegation roots contain HUNDREDS of controls; a threshold of
      // 2 also matched an ordinary handler-only clickable card wrapping two icon buttons
      // (kanban row, list item with edit+delete), removing a legitimate target from both
      // the listing AND find. Also require it to be big: a real delegation root spans a
      // large region, a card does not.
      // The comment above promises "also require it to be big"; that check was
      // never written. A 600x40 clickable table row containing 8 per-cell
      // controls (admin grids, mail/chat rows with checkbox + star + actions) was
      // deleted, and the row's own "open" action is usually the primary target.
      // A real delegation root spans a page region, not a line of text.
      const _big = (e.h >= vh * 0.5) || (e.w * e.h >= 0.25 * vw * vh);
      if (contained >= 8 && _big) drop.add(e.mmid);
    }
    // DEMOTE, NOT DELETE — same rule as parent-child-dedup. Both thresholds
    // here (>=8 contained, >=25% of the viewport) are numbers someone chose;
    // an app shell and a big clickable card differ by degree, not by anything
    // the document declares. So the verdict marks prominence and the element
    // keeps its ref. The entry is already built at this point, so this writes
    // `demoted` on it directly rather than going through `_note`.
    _noteEntries(out, drop, 'was:delegation-root');
  }
  // DUPLICATE-LABEL DISAMBIGUATION: >=3 controls sharing one short label
  // ("More info" ×4 on dashboard stat cards) are indistinguishable by name —
  // give each a near= hint from its card's heading/short text.
  {
    const byLab = new Map();
    for (const e of out) {
      const l = e.name || e.text || '';
      if (l && l.length <= 20) byLab.set(l, (byLab.get(l) || 0) + 1);
    }
    for (const e of out) {
      const l = e.name || e.text || '';
      if (!l || l.length > 20 || (byLab.get(l) || 0) < 3 || e.near || e.groupKey) continue;
      const n = mmidReg.get(e.mmid);
      if (!n) continue;
      let anc = n.parentElement;
      for (let d = 0; d < 3 && anc && anc !== document.body; d++, anc = anc.parentElement) {
        let t = '';
        try {
          const h = anc.querySelector && anc.querySelector('h1,h2,h3,h4,h5,h6,[role="heading"]');
          if (h) t = (h.innerText || '').replace(/\s+/g, ' ').trim();
          if (!t) {
            const at = (anc.innerText || '').replace(/\s+/g, ' ').trim();
            if (at && at.length <= 50 && at !== l) t = at;
          }
        } catch (e2) {}
        if (t && t !== l) { e.near = t; break; }
      }
    }
  }
  // CONTAINER-ENTRY SUPPRESSION: an "interactive" element taller than the
  // viewport whose OWN descendants are already listed is a wrapper (nav-list
  // content, scroller body — they pick up cursor styles or labels), not a
  // click target. Listing it as box(0,-1380,299,4327) just confuses the agent.
  {
    const bigEls = new Map();   // element -> entry, for wrapper candidates
    for (const e of out) {
      if (e.crossFrame || e.editable || e.codeEditor || e.scrollRegion || e.canvasLike || formyTags.has(e.tag)) continue;
      // Wrapper-sized: taller than the viewport, OR covering nearly ALL of it
      // in both dimensions (full-screen app shells listed via a stray label)...
      const viewportSized = e.h >= vh * 1.2 || (e.h >= vh * 0.85 && e.w >= vw * 0.85);
      // ...OR a generic container whose "label" is just its children's text
      // concatenated (WordPress: div "Showcase Plugins Themes Hosting…" above
      // 7 individually-listed nav links). Explicitly NON-WIDGET roles
      // (document/region/presentation — Monaco's focusable workbench shells)
      // count as generic too.
      const genericWrapper = (!e.role || ['document', 'region', 'presentation', 'none', 'group'].includes(e.role)) &&
        ['div', 'ul', 'ol', 'li', 'span', 'nav', 'section', 'article'].includes(e.tag) &&
        ((e.text || e.label || '').length >= 20);
      if (!viewportSized && !genericWrapper) continue;
      const n = mmidReg.get(e.mmid);
      if (n) bigEls.set(n, e);
    }
    if (bigEls.size) {
      const childCount = new Map();
      for (const e of out) {
        let n = mmidReg.get(e.mmid);
        if (!n || bigEls.has(n)) continue;
        n = composedParent(n);
        while (n) {
          if (bigEls.has(n)) {
            const be = bigEls.get(n);
            childCount.set(be, (childCount.get(be) || 0) + 1);
          }
          n = composedParent(n);
        }
      }
      // A wrapper only qualifies if its text really IS its children's text
      // concatenated — which is what the comment above describes but the code
      // never checked. Without this, any clickable CARD (news tile, dashboard
      // tile, list row: handler on the card, a heading plus 3 inner links) was
      // deleted silently, and the card's own click action became unreachable by
      // the listing AND by find(). The delegation pass 50 lines up already
      // learned this lesson and raised its threshold to 8 for the same reason;
      // this pass was re-killing the same shape at 3.
      const drop = new Set();
      for (const [be, n] of childCount) {
        if (n < 3) continue;
        if (be.h >= vh * 1.2 || (be.h >= vh * 0.85 && be.w >= vw * 0.85)) { drop.add(be.mmid); continue; }
        let residual = (be.text || be.label || '');
        for (const o of out) {
          if (o === be) continue;
          let nn = mmidReg.get(o.mmid), inside = false;
          while (nn) { if (nn === mmidReg.get(be.mmid)) { inside = true; break; } nn = composedParent(nn); }
          if (!inside) continue;
          for (const lab of [o.name, o.text, o.label]) {
            if (lab && lab.length > 2) residual = residual.split(lab).join('');
          }
        }
        // Own prose left over -> it is a card with its own content, not a shell.
        if (residual.replace(/[\s|·•,;:.\-—]/g, '').length < 12) drop.add(be.mmid);
      }
      if (drop.size) {
        // DEMOTE, NOT DELETE. Every number in this pass is chosen rather than
        // declared: 3 descendants, 12 residual characters, 1.2x and 0.85x the
        // viewport. The pass had already been caught deleting ordinary clickable
        // CARDS once (see the comment above, and the delegation pass that
        // learned the same lesson at threshold 3); demoting removes the class of
        // failure instead of retuning the number that produced it.
        _noteEntries(out, drop, 'was:container-suppression');
      }
    }
  }
  // Detect whether a TRUE blocking modal is open — if yes, the agent should
  // focus on it and ignore the rest of the page. CRITICAL: do NOT fire this for
  // every role="dialog". Cookie/consent toasts and notification popovers use
  // role="dialog" but are non-blocking corner widgets; treating them as modals
  // makes the agent abandon its real task to "deal with the modal." A real modal
  // is one that is aria-modal="true", a native <dialog> opened via showModal()
  // (matches :modal), OR a dialog large enough to dominate the viewport.
  const dialogOpen = (() => {
    let nodes = [];
    try { nodes = _allComposed('[role="dialog"],[role="alertdialog"],[aria-modal="true"],dialog'); } catch (e) {}
    let anyDialogVisible = false;
    let ariaModalClaim = false;
    for (const d of nodes) {
      const rr = d.getBoundingClientRect();
      if (!(rr.width > 0 && rr.height > 0)) continue;
      let dcs; try { dcs = getComputedStyle(d); } catch (e) { continue; }
      if (dcs.visibility === 'hidden' || dcs.display === 'none') continue;
      anyDialogVisible = true;
      // aria-modal="true" is a CLAIM, verified below — Yahoo Finance marks a
      // passive right-rail widget aria-modal, which hijacked the whole listing.
      if (d.getAttribute('aria-modal') === 'true') ariaModalClaim = true;
      // :modal (native showModal) is browser-enforced inertness — trustworthy.
      try { if (d.matches(':modal')) return true; } catch (e) {}
      // "Dominates viewport" fallback — tightened: must ALSO sit over the
      // viewport CENTER and be overlay-positioned. A tall right-rail widget
      // marked role=dialog (Yahoo Finance's trending panel) passed the bare
      // area test and falsely told the agent the whole page was modal.
      if ((rr.width * rr.height) / (vw * vh) >= 0.5 &&
          rr.left <= vw / 2 && rr.right >= vw / 2 &&
          rr.top <= vh / 2 && rr.bottom >= vh / 2 &&
          /^(fixed|absolute|sticky)$/.test(dcs.position)) return true;
    }
    // ARIA-HIDDEN SIBLINGS — how Radix, HeadlessUI and every focus-trap library
    // actually implement modality. Measured live on radix-ui.com: an open dialog
    // has aria-modal=null, is not native showModal(), uses no inert, and is
    // 500x269 in a 2560x1357 viewport — so ALL five existing signals miss, and the
    // library this project was built around got no MODAL banner while MUI, Ant and
    // Vuetify all did. What Radix DOES do is mark every body sibling
    // aria-hidden="true", which the collector already counts (_stateDrops) but
    // never fed back into modality. If a visible dialog has a sibling subtree the
    // page itself declared hidden, the page is telling us it is modal.
    if (anyDialogVisible) {
      try {
        for (const d of nodes) {
          const dr = d.getBoundingClientRect();
          if (!(dr.width > 0 && dr.height > 0)) continue;
          // Walk up to the level whose siblings the library hid.
          let n = d;
          for (let up = 0; up < 4 && n && n.parentElement; up++, n = n.parentElement) {
            let hiddenSibs = 0, sibs = 0;
            for (const sib of n.parentElement.children) {
              if (sib === n) continue;
              sibs++;
              if (sib.getAttribute && (sib.getAttribute('aria-hidden') === 'true'
                  || sib.hasAttribute('inert'))) hiddenSibs++;
            }
            if (sibs > 0 && hiddenSibs === sibs) return true;
          }
        }
      } catch (e) {}
    }
    // INERT BACKGROUND — the W3C signal, and the one none of the five paths above
    // looks at. A site that opens a sheet with dialog.show() (not showModal())
    // and marks the rest of the page `inert` gets: :modal false, no aria-modal,
    // and a panel that can be under half the viewport and off-centre. NHK's
    // consent sheet is exactly that shape, and the listing came back with 47
    // links flagged (disabled) and NO modal banner — telling the agent the site's
    // whole navigation was broken instead of "dismiss the sheet first". `inert`
    // is why those links were inert, so it is the honest explanation.
    if (anyDialogVisible) {
      try {
        for (const h of _allComposed('[inert]')) {
          const ir = h.getBoundingClientRect();
          if (ir.width * ir.height >= 0.3 * vw * vh) return true;
        }
      } catch (e) {}
    }
    // Verify the aria-modal claim against reality: a REAL modal has a backdrop
    // that blocks the page (our hit-tests measure exactly that). If the page's
    // own controls are essentially all still clickable, the "modal" is a
    // mislabeled passive widget — ignore the claim.
    if (ariaModalClaim) {
      let page = 0, blocked = 0;
      for (const e of out) {
        if (e.section === 'dialog' || e.offscreen) continue;
        page++;
        if (e.physBlocked || e.clickable === false) blocked++;
      }
      if (page < 5 || blocked / page >= 0.2) return true;
    }
    // Zero-height dialog shells (TrustArc's #consent_blackbar is h=0 with the
    // buttons overflowing it) defeat the rect check above — but if controls
    // resolved to section=dialog during collection, a dialog IS visibly open.
    if (!anyDialogVisible) anyDialogVisible = out.some(e => e.section === 'dialog');
    // BEHAVIORAL modality: some frameworks (OpenUI5's block layer, custom
    // overlay shims) make a SMALL dialog modal by covering the page with an
    // invisible click-blocker instead of aria-modal. The hit-tests already
    // know: when a dialog is visible AND a supermajority of the page's own
    // controls are occluded, the page is effectively modal.
    if (anyDialogVisible) {
      let page = 0, blocked = 0;
      for (const e of out) {
        if (e.section === 'dialog' || e.offscreen) continue;
        page++;
        if (e.physBlocked || e.clickable === false) blocked++;
      }
      if (page >= 5 && blocked / page >= 0.6) return true;
    }
    return false;
  })();
  // VIRTUALIZED GRIDS/LISTS: a windowed grid (AG Grid, react-window, TanStack)
  // only mounts the visible rows — without this note the agent concludes "row
  // 500 doesn't exist". aria-rowcount/aria-setsize are the W3C way such widgets
  // declare their TRUE size; compare against what's actually rendered.
  let virtualNote = '';
  try {
    _allComposed('[aria-rowcount]').forEach(g => {
      const total = parseInt(g.getAttribute('aria-rowcount'), 10);
      if (!total || total <= 0) return;                       // -1 = unknown
      const gr = g.getBoundingClientRect();
      if (!(gr.width > 0 && gr.height > 0)) return;
      // tr carries an implicit role=row, so a native <table aria-rowcount="5000">
      // reported 0 rendered rows and the note was suppressed entirely — the agent
      // concludes row 500 does not exist.
      const rendered = g.querySelectorAll('[role="row"], tr').length;
      if (rendered && total > rendered + 1) {
        const nm = (g.getAttribute('aria-label') || '').trim().slice(0, 30);
        virtualNote += `\n[VIRTUALIZED ${g.getAttribute('role') || 'grid'}${nm ? ` "${nm}"` : ''}: ` +
          `declares ${total} total rows but only ${rendered} are rendered in the DOM — ` +
          `rows load as you scroll INSIDE the grid body (not the page).]`;
      }
    });
  } catch (e) {}
  // MAIN HEADING: the page's prominent visible heading is the cheapest
  // "what am I looking at" state signal — after clicking "Next month" the
  // agent can confirm the calendar now says "July 2026" without vision.
  let mainHeading = '';
  try {
    const hs = _allComposed('h1, h2, [role="heading"]');
    for (const h of hs) {
      const hr = h.getBoundingClientRect();
      // >4px, not >0: the standard .visually-hidden/.sr-only pattern is a 1x1 clip
      // box, and an sr-only "Utility navigation" h2 was beating the visible <h1>.
      if (hr.width > 4 && hr.height > 4 && hr.top < vh && hr.bottom > 0) {
        const t = (h.innerText || '').replace(/\s+/g, ' ').trim();
        if (t) { mainHeading = t; break; }
      }
    }
  } catch (e) {}
  // STANDALONE MEDIA (detail='full' only). A plain <img> is not interactive, so
  // it never appears in a listing at any filter level — which means "download
  // that GIF" or "what is the hero image" is unanswerable from read_page no
  // matter how little we filter. This is a MISSING FIELD, not an over-filtering
  // problem, and it is why `full` exists.
  //
  // Added here, after modal detection has already run on the controls alone, so
  // media can never perturb the "is a dialog open" arithmetic; and before the
  // scopeMmid filter, so ref_id scoping applies to it like everything else.
  if (WANT_URLS) {
    const already = new Set(out.map(e => e.mmid));
    // CSS BACKGROUND IMAGES. Hero photos, card art and banners are routinely
    // painted with background-image on a <div>, which has no src, is not an <img>,
    // and is therefore invisible to `find`, to get_page_text, and to every filter
    // level — including the one that promises "non-clickable images". An agent
    // asked for the photos on a docs page, was told there were none, and only
    // found the three 379x300 banners by reaching for getComputedStyle itself.
    // Failing silently on the most common way to put a picture on a page is
    // exactly the omission `full` exists to end.
    //
    // Bounded on purpose: getComputedStyle is not free, so only boxes big enough
    // to be content are consulted, and the scan stops after a fixed budget.
    const bgSeen = new Set();
    let bgBudget = 600;
    mmidReg.forEach((n) => {
      if (bgBudget <= 0) return;
      try {
        const mm = n.getAttribute('mmid');
        if (!mm || already.has(mm) || bgSeen.has(mm)) return;
        const r = n.getBoundingClientRect();
        if (r.width < 80 || r.height < 60) return;                       // not a picture
        if ((r.top + r.height) <= 0 || r.top >= vh || (r.left + r.width) <= 0 || r.left >= vw) return;
        bgBudget--;
        const cs2 = getComputedStyle(n);
        const bg = cs2.backgroundImage || '';
        if (!bg || bg === 'none' || bg.indexOf('url(') === -1) return;
        // Gradients and tiny textures are decoration, not content.
        if (/gradient\(/i.test(bg)) return;
        const u = (/url\(\s*["']?([^"')]+)["']?\s*\)/.exec(bg) || [])[1];
        if (!u) return;
        const srcv2 = _url(u, n);
        if (!srcv2) return;
        bgSeen.add(mm);
        out.push({
          mmid: mm, tag: n.tagName.toLowerCase(), type: null, role: 'media',
          section: section(n), label: '',
          name: _clipAlt(n.getAttribute('aria-label') || n.getAttribute('title') || ''),
          near: '', underHeading: '', placeholder: '', value: '', text: '',
          x: Math.round(r.left), y: Math.round(r.top),
          w: Math.round(r.width), h: Math.round(r.height),
          clickable: true, active: '', required: false, unselected: false, disabled: false,
          newTab: false, topNav: false, synth: '', demoted: '', crossFrame: false, canvasLike: false, physBlocked: false,
          editable: false, codeEditor: false, scrollRegion: false,
          clippedInContainer: false, clipContainerMmid: null,
          hasPopup: false, collapsed: false,
          groupKey: null, groupName: '', groupRole: '',
          comboBacked: null, widgetSig: null, backedBy: null, orphanWidget: false,
          iconOnly: false, offscreen: false, mediaOnly: true, cssBackground: true,
          href: '', src: BRIEF ? _briefUrl(srcv2) : srcv2,
        });
      } catch (e) {}
    });
    for (const m of _allComposed('img, video, audio')) {
      try {
        const mm = m.getAttribute('mmid');
        if (!mm || already.has(mm)) continue;
        const mr = m.getBoundingClientRect();
        // Skip tracking pixels and sprite-sized decoration; keep anything a
        // human would call an image on the page.
        if (mr.width < 24 || mr.height < 24) continue;
        if ((mr.top + mr.height) <= 0 || (mr.left + mr.width) <= 0 || mr.top >= vh || mr.left >= vw) continue;
        const mcs = getComputedStyle(m);
        if (mcs.visibility === 'hidden' || mcs.display === 'none' || parseFloat(mcs.opacity || '1') === 0) continue;
        const srcv = _srcOf(m);
        if (!srcv) continue;
        out.push({
          mmid: mm, tag: m.tagName.toLowerCase(), type: null, role: 'media',
          section: section(m), label: '', name: _clipAlt(m.getAttribute('alt') || ''),
          near: '', underHeading: '', placeholder: '', value: '', text: '',
          x: Math.round(mr.left), y: Math.round(mr.top),
          w: Math.round(mr.width), h: Math.round(mr.height),
          clickable: true, active: '', required: false, unselected: false, disabled: false,
          newTab: false, topNav: false, synth: '', demoted: '', crossFrame: false, canvasLike: false, physBlocked: false,
          editable: false, codeEditor: false, scrollRegion: false,
          clippedInContainer: false, clipContainerMmid: null,
          hasPopup: false, collapsed: false,
          groupKey: null, groupName: '', groupRole: '',
          comboBacked: null, widgetSig: null, backedBy: null, orphanWidget: false,
          iconOnly: false, offscreen: false, mediaOnly: true,
          href: '', src: BRIEF ? _briefUrl(srcv) : srcv,
        });
      } catch (e) {}
    }
  }
  // Pathname + search is the cheap "where am I right now" signal the agent
  // needs to disambiguate sidebar links from in-page tabs that share a name.
  const url = location.pathname + (location.search || '');
  // SUBTREE SCOPING. `read_page(ref_id=...)` accepted this parameter and then ignored it,
  // printing the whole flat listing with an apologetic note — documented as limitation #1
  // for many rounds. Filtering here (rather than during the walk) keeps every dedup,
  // compaction and modal pass operating on full-page context, so a scoped listing says the
  // same things about its elements that an unscoped one would; it just shows fewer of them.
  if (scopeMmid) {
    const host = mmidReg.get(String(scopeMmid));
    if (host) {
      const inHost = (m) => {
        let n = mmidReg.get(m);
        while (n) { if (n === host) return true; n = composedParent(n); }
        return false;
      };
      // WHETHER THE HOST ITSELF IS INCLUDED depends on what scoping MEANS at each
      // detail level, and they are opposites:
      //   compact — "show me what is INSIDE this container". The host is the
      //             thing being looked into, not a result. (Pinned by W9.)
      //   full    — "tell me everything about THIS". The agent has already
      //             located its target and is asking for that element's URL, so
      //             excluding it answers a question nobody asked: scoping to a
      //             plain link returned ZERO rows, and scoping to an
      //             image-wrapping link returned the image and swallowed the
      //             href. Both were found by building the benchmark for this
      //             feature, before it had ever been used in anger.
      // The host is EXCLUDED only when the subtree has something else to show.
      // Original rule: compact scoping means "look inside this container", so the
      // container is not a result (W9). True for a card; false for a leaf. An
      // agent scoped to an <input> it had just found via find(), got an EMPTY
      // listing, and fell back to javascript_tool — the only raw-DOM escape in
      // the whole escalation study, and this rule forced it. Returning nothing
      // for a valid ref is never the useful answer.
      const inner = out.filter(e => e.mmid !== String(scopeMmid) && inHost(e.mmid));
      const kept = (FULL || inner.length === 0) ? out.filter(e => inHost(e.mmid)) : inner;
      out.length = 0;
      Array.prototype.push.apply(out, kept);
    } else if (!structured) {
      // THE REF DOES NOT EXIST IN THIS DOCUMENT. Previously this `if (host)` had no
      // else: the filter was skipped and the FULL page was returned, while the
      // server unconditionally prepended "[scoped to the subtree of ref_N]" — a
      // listing that states it is a subtree and is actually the whole document.
      // Measured live: after fill_form navigated to /inventory.html, a read scoped
      // to ref_17 (a ref from the PREVIOUS page; the new page's lowest mmid is 39)
      // returned all 25 elements under the scoped header. mmids do not survive a
      // navigation, so this is the normal way an agent hits it — carry a ref across
      // a page change and the lie is silent. Fail loudly instead.
      return "__SCOPE_MISS__" + String(scopeMmid);
    }
  }
  // LEDGER MODE returns both halves: what survived and what was removed, with the
  // rule that removed it. Placed before the structured return so it works at any
  // detail level and is unaffected by serialization.
  if (LEDGER) {
    const kept = new Set(out.map((e) => String(e.mmid)));
    // A post-pass can drop an mmid that a later pass re-adds; report only
    // entries that really are absent from the final listing, or the ledger
    // accuses rules of removals that did not stick.
    let absent = _ledger.filter((d) => !kept.has(String(d.mmid)));
    // THE LEDGER MUST ANSWER FOR THE REGION IT WAS ASKED ABOUT. Drops are recorded
    // during the whole-document walk, so a scoped ledger reported every drop on the
    // page: a read scoped to demoqa's City wrapper kept 0 elements and reported 319
    // drops, 137 of them not-visible elements from elsewhere entirely. The one
    // diagnostic that exists to answer "why is THIS element missing" was answering
    // about the whole document, which is how ~6 agents failed to find out what
    // dropped the City control even after running it.
    if (scopeMmid) {
      try {
        const _root = mmidReg.get(String(scopeMmid));
        if (_root) {
          absent = absent.filter((d) => {
            const el = d.mmid ? mmidReg.get(String(d.mmid)) : null;
            if (!el) return false;
            return el === _root || _root.contains(el);
          });
        }
      } catch (e) {}
    }
    // DEMOTION IS NOT A DROP, and an element can be both. `_note` records a
    // heuristic's verdict as `was:<rule>` while LEAVING the element in place, so
    // filing those entries beside real drops made the ledger wrong in the two
    // ways that matter most for the one tool whose whole job is explaining
    // omissions. Measured on gutenberg.org: `was:generic-no-label` 50 and
    // `parent-child-dedup` 104 -> 154 were THE SAME 50 elements — demoted by a
    // heuristic, then genuinely removed in favour of their labelled <a> child.
    // The header therefore claimed 317 dropped out of a pool of 313, the true
    // cause was buried under a rule that no longer removes anything, and a
    // demoted element that IS in the listing (craigslist's 9, rakuten's 7) was
    // reported as absent. Absence is decided by the spec rule alone.
    const hard = new Set(absent.filter((d) => !/^was:/.test(d.rule) && d.mmid)
                               .map((d) => String(d.mmid)));
    const dropped = absent.filter(
      (d) => !/^was:/.test(d.rule) || !(d.mmid && hard.has(String(d.mmid))));
    const tally = (rows) => rows.reduce(
      (acc, d) => { acc[d.rule] = (acc[d.rule] || 0) + 1; return acc; }, {});
    return {
      kept: out.length,
      elements: out,
      dropped,
      byRule: tally(dropped),
      // Kept, sent last as decoration, still actionable by ref. Reported apart
      // so "why is this element missing?" and "why is it in the decoration
      // tier?" are never answered by the same number.
      demoted: _ledger.filter((d) => /^was:/.test(d.rule) && kept.has(String(d.mmid))),
      byRuleDemoted: tally(_ledger.filter(
        (d) => /^was:/.test(d.rule) && kept.has(String(d.mmid)))),
    };
  }
  // ONE FORMATTER. `find` maintained a parallel Python formatter over these same
  // entries, and vocabulary drift between the two produced FIVE of the eleven
  // defects a nine-agent live study found: an unlabelled quoted string that could
  // be name/value/placeholder, non-ASCII escaped to backslash-u, a missing href,
  // and a label silently dropped the moment href was added. `_fmtLine` is pure —
  // it reads only the entry — so the structured path can attach the SAME rendered
  // line the listing would show, leaving nothing to drift.
  //
  // find needs the line attached rather than read out of the listing, because it
  // ranks OFFSCREEN elements too and the string listing is viewport-scoped.
  if (structured) {
    try { out.forEach((e) => { e.line = _fmtLine(e); }); } catch (e) {}
    return out;
  }
  // Spatial reading order — direction-aware: RTL pages (Arabic/Hebrew/Persian)
  // read right-to-left within a row, so "first" must be the rightmost there.
  const _rtl = (() => {
    try {
      return document.documentElement.dir === 'rtl' ||
             getComputedStyle(document.documentElement).direction === 'rtl';
    } catch (e) { return false; }
  })();
  const readingOrder = (a, b) => (a.y - b.y) || (_rtl ? (b.x - a.x) : (a.x - b.x));
  out.sort(readingOrder);
  // Cap the listing for token efficiency, but NEVER silently. The old code did
  // a blind out.slice(0,150) while the banner still reported out.length "on
  // screen" — so on dense pages the bottom of the listing (lower stories, and
  // worse, the bottom-of-form submit + required fields) just disappeared with
  // no breadcrumb. Now: (1) the elements that matter most for completing a task
  // — dialog content, required fields, unselected dropdowns, and form inputs —
  // are NEVER cut; (2) the remaining budget is filled with the rest in spatial
  // order; (3) if anything is left over, we say so explicitly.
  const LISTING_CAP = 150;
  let shown = out, hiddenCount = 0;
  let _capTail = [];
  if (out.length > LISTING_CAP) {
    // mediaOnly rows exist only in `full`, which is only ever requested BECAUSE the
    // agent wants a URL or an image. Letting the cap spend its budget on nav links
    // and truncate before them defeats the request: on a docs page an agent asked
    // for `full`, got 107 header nav entries, and the listing ran out before the
    // article body it cared about.
    const isPriority = (e) => e.section === 'dialog' || e.required || e.unselected || e.editable ||
                              e.mediaOnly || formyTags.has(e.tag);
    const pri = out.filter(isPriority);
    const rest = out.filter(e => !isPriority(e));
    const budget = Math.max(0, LISTING_CAP - pri.length);
    shown = pri.concat(rest.slice(0, budget));
    shown.sort(readingOrder);   // re-impose reading order on the kept subset
    hiddenCount = out.length - shown.length;
    // THE CAP MAY NOT DELETE. Everything else in this collector answers to
    // prominence-not-existence -- a heuristic may decide how loudly an element is
    // announced, never whether it exists -- and the entry cap was the one filter
    // still exempt from it. Measured live: on Hacker News it removed 10 of 30
    // front-page stories, one of them the second-most-commented thread on the
    // page, and an agent proved the advertised recovery impossible (scroll_to
    // reported success and the re-read came back byte-identical, because the cap
    // slices in document order). Two agents answered a "which has the most"
    // question correctly and said in writing that it was luck.
    //
    // So the tail keeps its refs. A ref and a short label is a handful of
    // characters against the ~90 a full row costs, so the whole overflow fits in
    // roughly the space of eight rows -- and nothing on the page is unreachable
    // any more, which is the property that matters.
    try {
      const _shownIds = new Set(shown.map((e) => String(e.mmid)));
      _capTail = out.filter((e) => !_shownIds.has(String(e.mmid)))
        .map((e) => {
          // markCut, not a bare ellipsis. This built `lab.slice(0,40) + '…'`, which
          // says a cut happened but not how big it was — and the whole point of the
          // count is that it decides whether to escalate. Measured live on Hacker
          // News: `693:"Autolith: A programming agent with a liv…"` was missing 8
          // characters and `643:"Figmimic – A bookmarklet to copy any web…"` was
          // missing 33, printed identically. The same titles appeared UNCUT in the
          // fold lines of the same listing, so the inconsistency was visible in one
          // screenful. Sixth home for this bug; markCut exists so a new bounded
          // field cannot reintroduce the silence by hand-rolling the cut.
          const lab = (e.name || e.label || e.text || '').trim();
          return e.mmid + (lab ? ':' + JSON.stringify(markCut(lab, 40)) : '');
        });
    } catch (e) {}
  }
  // Unscoped `full` on a dense page is the failure mode this level invites; name
  // it rather than just emitting the payload.
  const fullScopeNote = (FULL && !scopeMmid && out.length > LISTING_CAP)
    ? `
[detail="full" was requested for the WHOLE page (${out.length} entries, capped at ${LISTING_CAP}). ` +
      `Pass ref_id to scope it to the region you care about — you will get every entry in that region instead of a truncated page.]`
    : "";
  const truncNote = hiddenCount > 0
    ? `\n... +${hiddenCount} more interactive element(s) not shown (listing capped at ${LISTING_CAP}; ` +
      // "SCROLLING WILL NOT HELP ... a scroll plus a re-read returns byte-identical
      // output" was FALSE, and a live agent disproved it by doing it: on Hacker
      // News a scroll moved the folds from 39/52 to 202/214, brought in seven
      // story titles and eight footer links that the first read did not contain,
      // and shifted the omitted list from 421-621 to 614-806. The claim confused
      // two different things — the cap slices in document order, but WHAT REACHES
      // the cap is the viewport-scoped collection, so scrolling changes the input
      // set and therefore the survivors. Telling the agent not to try a recovery
      // that works is the #23 cross-extension defect again: a tool asserting an
      // impossibility a live agent had just performed.
      `dialog/required/dropdown/input fields are prioritized). A larger max_chars will NOT help: ` +
      `this cap counts ENTRIES, not characters. Scrolling changes WHICH entries are collected ` +
      `(this listing is viewport-scoped), so it shifts the window rather than lifting the cap. ` +
      `Prefer narrowing — read_page(ref_id=…) ` +
      `on a smaller region, find (it searches the whole page), or read_page(ref_id=…, filter="all") if ` +
      `the rows you want are in a list or table. A question about the LARGEST or FIRST of something is ` +
      `not answerable from the rows above alone -- but every omitted entry is listed by ref ` +
      `below, so nothing here is unreachable.` +
      (_capTail.length ? `
OMITTED BUT ACTIONABLE (ref:"label", ${_capTail.length} element(s), ` +
        `same order as the page): ${_capTail.join(' ')}` : '')
    : "";
  // The listing is viewport-only. If real controls (form fields, links, buttons)
  // sit below the fold, the agent otherwise has NO signal they exist and gives up
  // on long pages / below-fold forms. Tell it to scroll.
  // Under an open modal, below/above-fold page content is ALSO behind the
  // blocker — advertising it as scroll-reachable contradicts the modal note.
  // Scoped listings must not carry PAGE-WIDE counts. "167 more interactive
  // elements are BELOW the current viewport" is true of the document and
  // meaningless about the one subtree the agent asked for — an agent reading a
  // single-element scoped result flagged it as momentarily confusing.
  const sideNote = (dialogOpen || scopeMmid || !sideCount) ? "" :
    `
[${sideCount} interactive element(s) are outside the viewport HORIZONTALLY (a carousel, ` +
    `a wide table, or side-scrolling columns) — scroll sideways and re-observe, or reach them by ref via find.]`;
  const belowFoldNote = (dialogOpen || scopeMmid) ? "" : (belowFoldCount > 0 || aboveFoldCount > 0)
    ? `\n[${belowFoldCount > 0 ? `${belowFoldCount} more interactive element(s) are BELOW the current viewport` : ''}` +
      `${belowFoldCount > 0 && aboveFoldCount > 0 ? '; ' : ''}` +
      `${aboveFoldCount > 0 ? `${aboveFoldCount} interactive element(s) are ABOVE the viewport` + ((window.scrollY || document.documentElement.scrollTop || 0) > 1 ? ` (you have scrolled past them)` : ` (nothing has been scrolled — these sit at negative coordinates, e.g. an off-screen skip-link)`) : ''}` +
      ` — if you don't see your target, scroll ${belowFoldCount > 0 ? 'down' : 'up'} and re-observe.` +
      // NAME THE REGIONS. A bare count leaves only one move: scroll and re-read
      // the whole page. Saying which landmarks hold the off-viewport controls lets
      // the agent read ONE of them by ref instead — cheaper than a full re-listing,
      // and possible now that a scoped read is not viewport-limited. Sorted by
      // count so the biggest region reads first, and capped so a page with many
      // landmarks does not turn one hint into a paragraph.
      (() => {
        try {
          const ks = Object.keys(_offRegions)
            .filter((k) => _offRegions[k].mmid)
            .sort((a, b) => _offRegions[b].n - _offRegions[a].n);
          const _bare = _offRegions.__noref ? _offRegions.__noref.n : 0;
          if (!ks.length) {
            return _bare ? ` find reaches them by ref, without scrolling first.` : '';
          }
          // A REGION BIGGER THAN THE CAP IS NOT A RECOVERY. Scoping to one returns
          // a capped listing, not the region: measured live at 150 of 380 on eBay
          // and 150 of 199 on Reddit, and on craigslist the biggest region is 740.
          // Sorting by count put that useless one FIRST. Say which are readable in
          // full, and mark the rest rather than recommending them.
          const shown = ks.slice(0, 4)
            .map((k) => `${_offRegions[k].label}(ref_${_offRegions[k].mmid}): ${_offRegions[k].n}`
                        + (_offRegions[k].n > LISTING_CAP ? ' — too big to return in full' : ''))
            .join(', ');
          // COUNT AND SCOPED READ MEASURE DIFFERENT POPULATIONS, so do not imply
          // otherwise. The count is off-viewport controls whose NEAREST enclosing
          // region is this one; a scoped read of it returns everything inside,
          // on-screen rows and nested regions included. Two audits followed the
          // number as a promise (`footer: 9` -> 37 rows, `footer: 4` -> 12) and
          // reported the difference as a defect, which it was — of the wording.
          // find LEADS, because it measured cheapest on every site tried: 527 chars
          // against 19,053 for the scoped read on Reddit (36x), and it was the only
          // recovery that worked on a page whose region exceeded the cap.
          return ` They are in — ${shown}${ks.length > 4 ? `, and ${ks.length - 4} more region(s)` : ''}` +
                 `${_bare ? `, plus ${_bare} outside any region` : ''}.` +
                 ` CHEAPEST recovery: find — it searches the whole page and its refs are clickable` +
                 ` without scrolling. Or read a region with read_page(ref_id=…), which is not` +
                 ` viewport-limited and returns that region in full (its on-screen rows and any` +
                 ` nested region included, so expect more than the count above).`;
        } catch (e) { return ''; }
      })() + `]`
    : "";
  // MODAL FOCUS: when a TRUE modal is open, the underlying page is flagged
  // (occluded/blocked) line by line — accurate, but 40 such lines bury the
  // 5 actionable dialog controls (observed on consent modals). Omit them and
  // say so in one line; the agent's next move is inside the dialog anyway.
  let modalHiddenCount = 0;
  if (dialogOpen) {
    const keep = [];
    for (const e of shown) {
      // Outside the dialog, omit anything not plainly clickable: occluded by
      // the backdrop OR clipped/offscreen (a clipped entry once leaked through
      // with a "clicking auto-scrolls it into view" hint — a trap while a
      // modal is blocking the page).
      if (e.section === 'dialog' ||
          (!e.physBlocked && e.clickable !== false && !e.clippedInContainer && !e.offscreen)) keep.push(e);
      else modalHiddenCount++;
    }
    if (modalHiddenCount > 0) shown = keep;
  }
  // SCROLL-PANEL COMPACTION: >=10 entries clipped inside the SAME inner scroll
  // panel (long doc sidebars, chat lists) collapse into one mapping block via
  // the same machinery as grids — every mmid stays clickable (clicks
  // auto-scroll the panel).
  for (const e of shown) {
    if (!e.groupKey && e.clippedInContainer && e.clipContainerMmid) {
      e.groupKey = 'clip:' + e.clipContainerMmid;
      e.groupRole = 'scroll-panel';
      e.groupName = '';
    }
  }
  // LARGE-WIDGET COMPACTION: a 6×7 ARIA calendar emits 30-42 near-identical
  // role=gridcell lines (~2.5k chars); long listboxes/radiogroups do the same.
  // Collapse any group of >=10 same-container cells into ONE mapping block:
  // strip the labels' common prefix/suffix and emit "41:1 42:2 … 74:30".
  // Nothing is lost — every cell keeps its mmid and stays clickable.
  const compactBlocks = new Map();   // groupKey -> rendered block
  const inCompact = new Set();       // mmids folded into a block
  {
    const groups = new Map();
    for (const e of shown) {
      if (!e.groupKey) continue;
      if (!groups.has(e.groupKey)) groups.set(e.groupKey, []);
      groups.get(e.groupKey).push(e);
    }
    for (const [gk, members] of groups) {
      if (members.length < 10) continue;
      const labs = members.map(m => {
        const base = (m.name || m.text || m.label || '').trim();
        // Data-grid cells carry their COLUMN header in near= — prefix it so a
        // compacted row reads "Status:Active Trustworthiness:Perfect" instead
        // of positionally-ambiguous bare values.
        return (m.role === 'gridcell' && m.near) ? `${m.near}=${base}` : base;
      });
      if (labs.some(l => !l || l.length > 56)) continue;   // need clean, short labels
      // Common prefix/suffix across ALL labels ("June 1, 2026".."June 30, 2026"
      // -> prefix "June " + suffix ", 2026" stripped -> "1".."30").
      let pre = labs[0], suf = labs[0];
      for (const l of labs) {
        while (pre && !l.startsWith(pre)) pre = pre.slice(0, -1);
        while (suf && !l.endsWith(suf)) suf = suf.slice(1);
      }
      if (pre === labs[0]) pre = '';   // identical labels — don't strip to nothing
      if (suf === labs[0]) suf = '';
      if (pre.length + suf.length >= Math.min(...labs.map(l => l.length))) { if (pre.length >= suf.length) suf = ''; else pre = ''; }
      const items = members.map((m, i) => {
        let s = labs[i].slice(pre.length, suf ? labs[i].length - suf.length : undefined) || labs[i];
        if (/[\s|:]/.test(s)) s = JSON.stringify(s);
        const flags = (m.active ? `(${m.active})` : '') + (m.disabled ? '(disabled)' : '') + (m.required ? '(required)' : '');
        return `${m.mmid}:${s}${flags}`;
      }).join(' ');
      const m0 = members[0];
      const nm = m0.groupName ? ` "${m0.groupName}"` : '';
      const strip = (pre || suf)
        ? `label ${pre ? `prefix "${pre}"` : ''}${pre && suf ? ' + ' : ''}${suf ? `suffix "${suf}"` : ''} stripped; `
        : '';
      const kind = m0.role || m0.tag;
      const clipHint = String(gk).startsWith('clip:')
        ? ' — these are scrolled out inside an inner scrollable panel; clicking any auto-scrolls it into view'
        : '';
      compactBlocks.set(gk,
        `${m0.groupRole}${nm} — ${members.length} ${kind} cells as mmid:label (${strip}act on any via its ref)${clipHint}: ${items}`);
      members.forEach(m => inCompact.add(m.mmid));
    }
  }
  // REPEATED-IDENTICAL CONTROLS: dense lists emit one identically-named
  // control PER ROW (40× button "Follow" on Yahoo's tickers, 8× "Actions" on
  // GitLab's project rows). Individually they add nothing beyond an mmid —
  // identical name, identical role. Fold each set into one line; order is
  // top-to-bottom so the Nth mmid belongs to the Nth row.
  {
    const sig = new Map();
    for (const e of shown) {
      if (inCompact.has(e.mmid) || e.section === 'dialog') continue;
      const lab = e.name || e.text || e.label || '';
      if (!lab || lab.length > 40) continue;
      const k = `${e.tag}|${e.role || ''}|${lab}`;
      if (!sig.has(k)) sig.set(k, []);
      sig.get(k).push(e);
    }
    for (const [k, members] of sig) {
      if (members.length < 8) continue;
      // "ordered top-to-bottom" has to be TRUE. Members arrive in collection
      // order, which put y=1124..1259 rows before y=972 ones — the fold's own
      // ordering promise was the only discriminator it offered, and it was wrong.
      members.sort((p1, p2) => (p1.y || 0) - (p2.y || 0));
      const m0 = members[0];
      const lab = m0.name || m0.text || m0.label;
      const kind = (m0.role && m0.role !== m0.tag) ? m0.role : m0.tag;
      // Per-member discriminators, kept because the shared label cannot tell them
      // apart: what makes ref X different from ref Y is its CONTEXT and whether
      // it is on screen at all.
      const _mref = (m) => {
        const off = m.offscreen ? ((m.y || 0) < 0 ? '^' : 'v') : '';
        const ctx = (m.near && m.near !== lab) ? ':' + JSON.stringify(m.near) : '';
        return `${m.mmid}${off}${ctx}`;
      };
      const _anyOff = members.some(m => m.offscreen);
      const _anyCtx = members.some(m => m.near && m.near !== lab);
      compactBlocks.set('rep:' + k,
        `${members.length}× ${kind} ${JSON.stringify(lab)} — one per list row, ordered top-to-bottom; `
        + `refs: ${members.map(_mref).join(' ')}`
        + (_anyOff ? ` [^ = above the viewport, v = below it]` : '')
        + (_anyCtx ? ` [:"..." = that row's near= context, which is what tells these apart]` : ''));
      members.forEach(m => { m.groupKey = 'rep:' + k; inCompact.add(m.mmid); });
    }
    // ICON-GLYPH GRIDS: >=8 unlabeled icon entries of the same tag+section
    // (draw.io's shape palette emitted ~35 identical "icon button — no text
    // label" lines). Indistinguishable individually — fold into one line; the
    // agent uses analyze_screen once to identify them anyway.
    const iconSig = new Map();
    for (const e of shown) {
      if (!e.iconOnly || inCompact.has(e.mmid) || e.section === 'dialog') continue;
      const k = `${e.tag}|${e.section || ''}`;
      if (!iconSig.has(k)) iconSig.set(k, []);
      iconSig.get(k).push(e);
    }
    for (const [k, members] of iconSig) {
      if (members.length < 8) continue;
      compactBlocks.set('ico:' + k,
        `${members.length}× unlabeled ${members[0].tag} icon buttons (a glyph grid/palette — take ONE computer screenshot to identify them, then click by ref; reading order): ${members.map(m => `${m.mmid}@(${m.x},${m.y})`).join(' ')}`);
      members.forEach(m => { m.groupKey = 'ico:' + k; inCompact.add(m.mmid); });
    }
    // REPEATED RECORDS (MDR/DEPTA-style, generalised from the grid and
    // identical-label folds above). Measured on 35 frozen sites: 46% of pages
    // exceed the 150-entry cap, the median capped page loses 124 elements, and
    // **96% of a median listing sits in a structurally repeated group** — 20
    // product cards, 50 search results, a nav column. We were paying full price
    // per row for near-identical rows and then dropping the tail.
    //
    // Folded rows KEEP their own mmid and their href, so nothing becomes
    // unactionable or unanswerable — this is a serialization change only. The
    // structured array is returned untouched above, which is what `find` and
    // every audit consume.
    // TAG PATH, NOT PIXEL SIZE. The signature used to bucket rendered geometry
    // (`round(w/40)`, `round(h/20)`), and BOTH of those are content-determined
    // for text: width is set by how long the label is, and height by how many
    // lines it wraps to. So one semantic class shattered into buckets of one.
    // Measured live on three of five random sites: lite.cnn.com printed ~26
    // headline links individually beside folds of 7 and 6 — one list, one tag,
    // one height, one x-origin, differing only in headline length; rakuten split
    // a single nav at 64x37 and 59x37; gutenberg split 25 identical book rows
    // into 18@113px + 6@106px + 1 orphan, because long titles wrap.
    //
    // The classical answer is to cluster on STRUCTURE — the root-to-node tag
    // path (MDR / DEPTA / tag-path clustering). Members of one repeated record
    // group share their ancestor chain up to the container that repeats them;
    // two different lists do not. It is also the honest criterion: "these are
    // the same kind of thing" is a claim about markup, not about how wide the
    // text happened to render.
    //
    // Bounded depth and a stop at the nearest structural container, so the path
    // discriminates within a page without becoming a whole-document fingerprint
    // (which would make every element unique and fold nothing).
    const _STOP = /^(main|nav|header|footer|aside|form|section|article|ul|ol|table|tbody|thead|tr|dl)$/;
    // CLASS IS PART OF THE PATH. A tag-only path was wrong in the worst possible
    // way — too COARSE — and a live audit of Hacker News proved it: header nav
    // (`span.pagetop > a`), story headlines (`span.titleline > a`) and submitter
    // profiles (`span.subline > a.hnuser`) all reduce to `span<a`, so one fold
    // announced `42× a, same structure` over nav links, headlines and usernames
    // together, with `28:"login"` among them and the header inviting the agent to
    // "act on any via its ref". A fold's shared description has to be true of every
    // member; that one was true of none.
    //
    // Author templates put the same classes on every repeated instance, so classes
    // discriminate KIND without breaking grouping. Sorted, because class order in
    // the attribute is not meaningful. Where classes differ per item (a `selected`
    // or `is-active` state) the group splits — a compression loss, never a
    // correctness one, and splitting is the safe direction: merging two kinds
    // makes the listing lie, while splitting one kind only makes it longer.
    const _clsSig = (n) => {
      try {
        const c = n.getAttribute && n.getAttribute('class');
        if (!c) return '';
        // Bounded: utility-CSS pages carry dozens of classes per node, and the
        // whole string would dominate the signature without adding discrimination.
        const toks = String(c).trim().split(/\s+/).filter(Boolean).sort().slice(0, 4);
        return toks.length ? '.' + toks.join('.') : '';
      } catch (err) { return ''; }
    };
    const _structSig = (el) => {
      const parts = [];
      let n = el;
      for (let d = 0; n && d < 6; d++) {
        const t = (n.tagName || '').toLowerCase();
        if (!t) break;
        let rl = '';
        try { rl = (n.getAttribute && n.getAttribute('role')) || ''; } catch (err) {}
        parts.push((rl ? t + '[' + rl + ']' : t) + _clsSig(n));
        if (_STOP.test(t)) break;
        n = n.parentElement;
      }
      return parts.join('<');
    };
    // POSITION MATTERS, BUT ONLY INSIDE A REPEATED PARENT.
    //
    // A pure tag path is right for lists and wrong for multi-field rows. Both
    // cases are real and they pull in opposite directions:
    //
    //   list   <ul><li><a>Fashion</a></li> x16          -> path identical, one group. GOOD.
    //   record <div><a>title</a><a>domain</a><a>age</a> -> path identical, ONE group of
    //          x10                                         30 mixed things, so the
    //                                                      heterogeneity guard refuses
    //                                                      and nothing folds at all.
    //
    // A sibling ordinal fixes the record case and destroys the list case: a <nav>
    // holding 30 direct <a> children would fragment into 30 groups of one — the
    // exact rakuten defect this rewrite exists to fix.
    //
    // What separates them is not the child count, it is whether the PARENT ITSELF
    // REPEATS. Ten sibling <div> rows sharing one tag path are MDR's "generalized
    // node"; a single <nav> is not. So the ordinal is added only when the parent's
    // own path occurs at more than one parent element. Structural, no threshold.
    //
    // (Found because the old geometry key passed a fixture this one failed: the
    // titles wrapped to two lines at 98x36 while their metadata siblings were
    // 98x16, so `round(h/20)` separated title from metadata BY ACCIDENT. Fixtures
    // encode behaviour, not intent, and that one had been green for the wrong
    // reason.)
    const _cand = [];
    for (const e of shown) {
      if (inCompact.has(e.mmid) || e.section === 'dialog' || e.mediaOnly) continue;
      const label = (e.name || e.label || e.text || '').trim();
      if (!label) continue;                       // unlabeled rows fold badly
      let el = null;
      try { el = mmidReg.get(String(e.mmid)) || null; } catch (err) {}
      _cand.push({ e, el, path: el ? _structSig(el) : '', par: (el && el.parentElement) || null });
    }
    const recSig = new Map();
    for (const c of _cand) {
      const { e } = c;
      let sig = c.path;
      // No element (cross-frame entries live in another document) — fall back to
      // the old geometry bucket rather than folding everything together.
      if (!sig) sig = 'geo:' + Math.round((e.w || 0) / 40) + 'x' + Math.round((e.h || 0) / 20);
      // NO SIBLING ORDINAL. It was added so a no-class fixture modelling Hacker
      // News (title/domain/age as bare sibling <a>s) would separate its three
      // columns, and on real pages it is the same shattering disease the pixel-size
      // key had. Measured live on arXiv: 276 author links, every one
      // `div.list-authors > a`, split into 5 folds plus 12 loose rows by AUTHOR
      // POSITION WITHIN THE PAPER — first authors in one group, second authors in
      // another. Position within a record is not a kind of thing.
      //
      // Class (above) discriminates kind on the real pages the ordinal was
      // standing in for — HN's own markup gives its three link types three
      // different classes. Where a page genuinely offers no class and no structural
      // difference between adjacent fields, the heterogeneity guard refuses the fold
      // and the rows print individually. That is the correct outcome: not folding
      // costs tokens, folding unlike things costs correctness.
      const k = [e.tag, e.role || '', e.section || '', e.href ? 'L' : '', sig].join('|');
      if (!recSig.has(k)) recSig.set(k, []);
      recSig.get(k).push(e);
    }
    // WHAT KIND OF THING IS THIS LABEL? Structural, not lexical. The shape
    // signature is tag/role/section/href/size and knows nothing about what the
    // labels SAY, so on Hacker News one bucket held a story TITLE, site domains,
    // timestamps and comment links — all ~98x16px. A reader gets only the group's
    // shared description, so a front-page story vanished into a metadata pile and
    // the agent's task was structurally unanswerable. The SEMANTIC fold is the best
    // block in the tool; this is the same feature as its evil twin, so the fix is a
    // kind check, not less folding.
    const _kind = (t) => {
      const v = (t || '').trim();
      if (!v) return 'empty';
      if (/^\d[\d.,:%+-]*$/.test(v)) return 'number';
      if (/^[a-z0-9-]+(\.[a-z0-9-]+)+$/i.test(v) && !/\s/.test(v)) return 'domain';
      if (/\d/.test(v) && v.length <= 24 && /^[^.]*$/.test(v) && /\s/.test(v)) return 'timeish';
      return 'prose';
    };
    for (const [k, members] of recSig) {
      if (members.length < 6 || window.__abNoFold) continue;
      try {
        const kinds = new Set(members.map(m => _kind(m.name || m.text || m.label || '')));
        kinds.delete('empty');
        if (kinds.size > 1) continue;   // heterogeneous: leave the rows alone
      } catch (e) {}
      members.sort((p, q) => {
        const pn = parseInt(String(p.mmid).replace(/^.*:/, ''), 10);
        const qn = parseInt(String(q.mmid).replace(/^.*:/, ''), 10);
        return (isFinite(pn) && isFinite(qn)) ? pn - qn : 0;
      });   // below this, folding costs more than it saves
      const m0 = members[0];
      const items = members.map((m) => {
        // markCut already bounded these and stamped the residual count. A second
        // bound cuts the MARKER in half: '…(+1' is valid syntax and reads as one
        // missing character when sixteen are missing. Never re-clip a marked string.
        const lab = (m.name || m.label || m.text || '').trim();
        // FOLDING MUST NOT DELETE STATE. The member format carried only
        // disabled/required/active, so every other flag vanished the moment an
        // element was folded — and its ABSENCE reads as "normal". Live: a
        // `(collapsed)` disclosure button disappeared into an 8-member fold; 61 of
        // 100 rows in one scoped read were below the fold with no marker while the
        // header said "(100 on screen)"; and a fold mixed an in-viewport author
        // link with an off-screen one under identical labels. These are exactly the
        // flags that change what an agent does next, so they travel with the member.
        const flags = (m.disabled ? '(disabled)' : '') + (m.required ? '(required)' : '')
                    + (m.active ? `(${m.active})` : '')
                    + (m.collapsed ? '(collapsed)' : '')
                    + (m.hasPopup ? '(opens menu)' : '')
                    + (m.newTab ? '(new tab)' : '')
                    + (m.clickable === false ? '(occluded)' : '')
                    + (m.offscreen ? ((m.y || 0) < 0 ? '(above-fold)' : '(below-fold)') : '');
        // GEOMETRY REACHES FOLDED MEMBERS TOO. With geometry=true the loose rows
        // gained box() and the folded ones silently did not, so on OpenStreetMap
        // "Zoom In" — which exists ONLY inside a fold — had no coordinate at either
        // detail level, and the only way to get one was a second scoped read per
        // element. The unlabelled-icon fold already carried `@(x,y)`; this is the
        // same notation, so one fold format does not contradict the other.
        const _mb = geometry ? `@(${m.x},${m.y})` : '';
        return `${m.mmid}:${JSON.stringify(lab)}${_mb}${m.href ? '→' + m.href : ''}${flags}`;
      }).join(' ');
      const kind = m0.role || m0.tag;
      const where = m0.section ? ` in section=${m0.section}` : '';
      // The header no longer claims "same shape (~WxH px)". Members are grouped
      // by tag path now, so they can legitimately differ in rendered size — a
      // wrapped two-line title next to a one-line one — and repeating the first
      // member's box as the group's shape would be a false statement about the
      // other N-1. "Same structure" is what is actually being asserted.
      const _ty = members.every((m) => m.type === m0.type) && m0.type ? `[${m0.type}]` : '';
      compactBlocks.set('rec:' + k,
        `${members.length}× ${kind}${_ty}${where}, same structure, in document order` +
        `${m0.href ? ' — each is a link, shown as ref:"label"→href' : ' — shown as ref:"label"'}` +
        ` (act on any via its ref): ${items}`);
      members.forEach((m) => { m.groupKey = 'rec:' + k; inCompact.add(m.mmid); });
    }
  }
  const TREEFMT = format === 'tree';
  // TREE SERIALIZATION. Lives here, inside the collector, for two reasons: an
  // injected function loses its closure so a standalone could never be called in
  // production, and it has to see the SAME `shown` set the flat rows get — post
  // viewport-filter, post entry-cap — or a comparison between the two measures
  // population as well as shape. Measured as a standalone over the whole
  // structured array it scored 96.6% first-read reachability at +1810% tokens,
  // which says nothing about shape at all.
  const _treeLines = () => {
    const LAND = { MAIN: 1, NAV: 1, HEADER: 1, FOOTER: 1, ASIDE: 1, FORM: 1,
                   SECTION: 1, ARTICLE: 1, DIALOG: 1 };
    const ent = new Map();
    for (const e of shown) {
      let el = null;
      try { el = mmidReg.get(String(e.mmid)) || null; } catch (err) {}
      if (el) ent.set(el, e);
    }
    if (!ent.size) return [];
    // How many DISTINCT child paths lead to a kept node. Two or more means this is
    // where the page actually divides — the only structural fact indentation needs.
    const branch = new Map();
    for (const el of ent.keys()) {
      let prev = el;
      for (let n = el.parentElement; n && n !== document.documentElement; n = n.parentElement) {
        if (!branch.has(n)) branch.set(n, new Set());
        branch.get(n).add(prev);
        prev = n;
      }
    }
    const LANDROLE = { main: 1, navigation: 1, banner: 1, contentinfo: 1, complementary: 1,
                       search: 1, form: 1, region: 1, dialog: 1, alertdialog: 1 };
    const keep = new Set(ent.keys());
    for (const [n, ks] of branch) {
      let role = '';
      try { role = (n.getAttribute && n.getAttribute('role')) || ''; } catch (err) {}
      // Actionable, declared as structure by the document, or a branch point.
      // No class, no pixel size, no label text — the three things every failed fold
      // signature was built on. Roles are narrowed to LANDMARKS: accepting any role
      // kept every ARIA wrapper on the page, including role=presentation/none/
      // generic, which explicitly declare the absence of semantics.
      if (ks.size >= 2 || LAND[n.tagName] || LANDROLE[role]) keep.add(n);
    }
    // Nodes this function adds because the DOCUMENT declares them structure, as
    // opposed to nodes that earned a line by branching. The pruning below skips
    // them: it once removed the <table> it had just added and left the
    // parser-inserted <tbody> standing in for it, which names an implementation
    // detail where the document names a table.
    const declared = new Set();
    // A <table> holds no interactive elements on most pages, so it never appears
    // on an entry's ancestor path. It is structure the document declares, and in a
    // tree it belongs where it sits rather than in an out-of-band legend line.
    try {
      // SCOPED READS MUST NOT IMPORT TABLES FROM OUTSIDE THE SCOPE. The guard here
      // was `(!scopeMmid || ent.size)` — true for ANY scoped read that kept a single
      // entry — over a `document.querySelectorAll('table')`. So a read scoped to one
      // <input> came back listing eight of the page's data tables, and a read scoped
      // to one container listed five tables of which four were elsewhere, both under
      // the header "[scoped to the subtree of ref_N — elements outside it are
      // omitted]". Two live agents reported it. Same class as #26's Main-heading and
      // below-fold leaks and #27's craigslist "955 controls" note, and the same fix:
      // a page-level fact belongs to a page-level read.
      let _scopeHost = null;
      try {
        if (scopeMmid && mmidReg && mmidReg.get) _scopeHost = mmidReg.get(String(scopeMmid)) || null;
      } catch (err2) {}
      for (const t of document.querySelectorAll('table')) {
        if (!t.getAttribute('mmid')) continue;
        // Containment via the composed walk, so a table inside a shadow root or a
        // same-origin frame is judged by the same rule as everything else.
        if (scopeMmid) {
          if (!_scopeHost) continue;
          let w = t, inside = false;
          for (let i = 0; i < 40 && w; i++) {
            if (w === _scopeHost) { inside = true; break; }
            w = w.parentElement || (w.getRootNode && w.getRootNode().host) || null;
          }
          if (!inside) continue;
        }
        const rs = Array.from(t.querySelectorAll('tr')).filter((r) => {
          try { return r.closest('table') === t; } catch (err) { return true; }
        }).length;
        if (rs >= 2) { keep.add(t); declared.add(t); }
      }
    } catch (err) {}
    // A NODE THAT DOES NOT DIVIDE ANYTHING EARNS NO LINE. In a chain A > B > C
    // where each has the same kept descendants, the page splits once and the chain
    // merely carries it -- yet every link counted as a "branch point" and got its
    // own indent level. Measured on a car-rental page: 332 structural lines and
    // 36,576 of 45,868 characters were INDENTATION, with single lines running to
    // 245 characters of pure whitespace. Splicing out every non-landmark,
    // non-actionable node with exactly one kept child is information-preserving by
    // definition -- a wrapper with one child and no name of its own says nothing --
    // and it is the collapse this design was supposed to have from the start.
    let pruned = true;
    while (pruned) {
      pruned = false;
      for (const el of Array.from(keep)) {
        if (ent.has(el) || LAND[el.tagName] || declared.has(el)) continue;
        let role = '';
        try { role = (el.getAttribute && el.getAttribute('role')) || ''; } catch (err) {}
        if (LANDROLE[role]) continue;
        let kc = 0;
        for (const other of keep) {
          if (other === el) continue;
          for (let n = other.parentElement; n; n = n.parentElement) {
            if (n === el) { kc++; break; }
            if (keep.has(n)) break;
          }
          if (kc > 1) break;
        }
        if (kc <= 1) { keep.delete(el); pruned = true; continue; }
        // SECOND CLAUSE, same principle from the other end: a node whose nearest
        // kept ANCESTOR has it as that ancestor's only kept child expresses the
        // same division the ancestor already expressed, so it earns no line
        // either. "Exactly one kept child" alone misses this, which is how a
        // parser-inserted <tbody> came to be indented under its own <table> —
        // both branch, but the page divides once. The OUTER one survives, because
        // that is the node the author wrote.
        let anc = null;
        for (let n = el.parentElement; n; n = n.parentElement) { if (keep.has(n)) { anc = n; break; } }
        if (anc) {
          let sib = 0;
          for (const other of keep) {
            if (other === el || other === anc) continue;
            for (let n = other.parentElement; n; n = n.parentElement) {
              if (n === anc) { sib++; break; }
              if (keep.has(n)) break;
            }
            if (sib) break;
          }
          if (!sib) { keep.delete(el); pruned = true; }
        }
      }
    }
    // IDENTICAL NESTED ENTRIES SHARE ONE ROW. Once the container heuristics
    // stopped deleting (#28) a single nav item printed as a chain — span
    // "Elements" > div "Elements" > div "Elements" > span > svg, five lines for
    // one thing. The elements must exist: `find` and a scoped read reach them,
    // and one of them carries the handler. But printing a row whose every
    // PRINTED FIELD already appeared on the row above is not information, and
    // suppressing an exact duplicate is not a guess about what matters — it is
    // the one thing about these chains the DOM does state.
    //
    // Collapse requires EXACT equality of every identity and geometry field and
    // that BOTH ends be undeclared generics: an <a>, <button>, <input> or an
    // element with an interactive ARIA role always keeps its own row, because
    // there the tag IS the information. No tolerance, no size threshold — if the
    // boxes differ by a pixel the rows differ in layout and both print.
    const _GENERIC = { DIV: 1, SPAN: 1, LI: 1, SECTION: 1, P: 1, LABEL: 1 };
    const _plainWrapper = (el) => {
      if (!_GENERIC[el.tagName]) return false;
      try {
        const r = el.getAttribute && el.getAttribute('role');
        if (r && INTERACTIVE_ROLES.has(r)) return false;
      } catch (err) { return false; }
      return true;
    };
    // A DECLARED CONTROL NEVER LOSES ITS NAME. The rollup below drops a label the
    // descendants account for, which is right for a container and wrong for a
    // control: an <a> whose only child wrapper repeats its text had its own name
    // deleted, leaving `ref_7 | a` — a link the agent cannot identify. TR8d
    // caught it. A control's name IS its identity; only a container's label is a
    // summary of what is printed beneath it.
    const _declaredControl = (el) => {
      const t = (el.tagName || '').toLowerCase();
      if (['a', 'button', 'input', 'select', 'textarea', 'summary'].indexOf(t) >= 0) return true;
      try {
        const r = el.getAttribute && el.getAttribute('role');
        if (r && INTERACTIVE_ROLES.has(r)) return true;
      } catch (err) {}
      return false;
    };
    const _sameRow = (a, b) => (
      (a.label || '') === (b.label || '') && (a.name || '') === (b.name || '') &&
      (a.value || '') === (b.value || '') && (a.placeholder || '') === (b.placeholder || '') &&
      a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h);
    // ref -> the refs folded into it, so nothing becomes unreachable from the
    // listing. All of them name the same box and the same label, so they are
    // printed side by side rather than one being called the real one.
    const alsoRefs = new Map();
    let folded = true;
    while (folded) {
      folded = false;
      for (const el of Array.from(keep)) {
        const pe = ent.get(el);
        if (!pe || !_plainWrapper(el)) continue;
        const ks = (function () {
          const acc = [];
          for (const other of keep) {
            if (other === el) continue;
            for (let n = other.parentElement; n; n = n.parentElement) {
              if (n === el) { acc.push(other); break; }
              if (keep.has(n)) break;
            }
            if (acc.length > 1) break;
          }
          return acc;
        })();
        if (ks.length !== 1) continue;
        const kid = ks[0];
        const ke = ent.get(kid);
        if (!ke || !_plainWrapper(kid) || !_sameRow(pe, ke)) continue;
        // The PARENT is the one spliced out: its ref moves onto the child's row,
        // which keeps the tree's indentation anchored to the deepest node and so
        // preserves the nesting of everything below.
        // ELEMENTS, not mmids: `keep` iterates in insertion order, which is the
        // order the ancestor walk happened to add nodes, so a chain can fold
        // inner-first. The refs are sorted into DOCUMENT order at emit time —
        // outermost first — because that is the order the reader is scanning.
        alsoRefs.set(kid, (alsoRefs.get(el) || []).concat([el], alsoRefs.get(kid) || []));
        alsoRefs.delete(el);
        keep.delete(el);
        folded = true;
      }
    }
    // BUILT AFTER BOTH REDUCTION LOOPS, not before. It used to be built first,
    // so anything the loops removed from `keep` still had a parent->children edge
    // and was still walked by `emit` — the removal only took effect for nodes the
    // branch rule had never admitted in the first place. That made the
    // cascade fixpoint above a no-op in exactly the cases it exists for, and it
    // silently swallowed the identical-row fold below.
    const kids = new Map();
    const roots = [];
    for (const el of keep) {
      let par = null;
      for (let n = el.parentElement; n; n = n.parentElement) { if (keep.has(n)) { par = n; break; } }
      if (par) { if (!kids.has(par)) kids.set(par, []); kids.get(par).push(el); }
      else roots.push(el);
    }
    const docOrder = (x, y) => {
      try { return (x.compareDocumentPosition(y) & 4) ? -1 : 1; } catch (err) { return 0; }
    };
    roots.sort(docOrder);
    for (const arr of kids.values()) arr.sort(docOrder);
    const out = [];
    const emit = (el, depth) => {
      // <body>/<html> are on every page and say nothing, so they are walked
      // through rather than printed — otherwise every line pays two spaces for a
      // node carrying no information.
      if (el.tagName === 'BODY' || el.tagName === 'HTML') {
        for (const c of (kids.get(el) || [])) emit(c, depth);
        return;
      }
      const pad = ' '.repeat(depth);
      let _blank = false;
      const e = ent.get(el);
      if (e) {
        // A CONTAINER'S LABEL IS ITS CONTENTS, AND ITS CONTENTS ARE PRINTED BELOW
        // IT. An element's accessible name falls back to the concatenation of its
        // descendants' text, so a page shell reads as the whole page: demoqa's
        // outermost div arrived as a 390-character first row naming every nav
        // item, heading, field and the copyright line — every word of which is on
        // its own row underneath. In a FLAT list that string was the only way to
        // know what the container held; in a tree the nesting says it, so the
        // repetition is redundant by construction rather than by judgement.
        //
        // The test is exact, with no threshold: remove each kept descendant's
        // label from this node's label, then discard everything that is not a
        // letter or a digit in any script. If nothing is left, the descendants
        // account for all of it. A container with prose of its own keeps its
        // label, because that prose survives the subtraction.
        let _e = e;
        try {
          const _own = (e.name || e.label || e.text || '');
          if (_own && !_declaredControl(el) && (kids.get(el) || []).length) {
            // THE SUBTRACTION TEST WAS WRONG ABOUT WHERE THE NAME COMES FROM. It
            // removed each kept DESCENDANT ENTRY's label and required nothing to
            // remain — but an accessible name is built from ALL descendant text
            // (AccName step 2F), and non-interactive text has no entry to subtract.
            // So one ordinary text node anywhere in the subtree defeated the whole
            // rule. Measured live: Dzen printed TWO rows of ~4,000 chars each,
            // consuming ~8,000 of a 12,000-char budget and evicting real rows
            // ("16 more element(s) not shown"), and demoqa's outermost div was the
            // FIRST row at 390 chars — every nav item, field label and the
            // copyright notice — each of which also printed on its own row below.
            // The same blob is why find("State dropdown") answered with the page
            // container under a confident `Found 1 element(s) matching`: a
            // whole-page label matches any query about page text.
            //
            // The rule is now the spec's own: name-from-content is ROLE-GATED.
            // A generic container is not in that role set, so per AccName it has no
            // accessible name from its contents — the string was ours, not the
            // page's. Using content as a label stays where it is the ONLY identity
            // available (a leaf clickable card, an icon control); it goes where the
            // tree already prints the same text one line below, which is decided by
            // whether this node has kept children, not by a threshold.
            //
            // An explicitly DECLARED name is never touched: aria-label,
            // aria-labelledby, title and an associated <label> are the page saying
            // what this thing is called, and they survive regardless of nesting.
            // THE TEST IS THE CONTAINER'S OWN DIRECT TEXT. Two rules were tried and
            // both were wrong in one direction:
            //   - subtract kept descendants' labels and require nothing to remain:
            //     defeated by ONE non-interactive text node anywhere in the subtree,
            //     which is what let Dzen and demoqa print whole-page labels;
            //   - drop any content-derived label on a container: that deleted the
            //     prose in TR10b's card, which the tree prints nowhere else.
            // Both cases are identical under subtraction, so subtraction cannot
            // separate them. What does, with no threshold: does this element have
            // text OF ITS OWN — a direct child text node — as opposed to a name
            // assembled entirely from descendants it does not own?
            //   demoqa/Dzen shell: no direct text (the copyright sits in a nested
            //     div, every other word belongs to a child) -> pure concatenation,
            //     and the tree prints every part of it one line below. Dropped.
            //   TR10b's card: "A quarterly summary…" IS a direct text node -> its
            //     own prose, kept in full.
            //   "Buy the <a>Pro plan</a>": direct text "Buy the " -> kept in full,
            //     so #29's objection to printing a residual ("Buy the") does not
            //     arise; this drops the label or keeps it whole, never a fragment.
            // A DECLARED name (aria-label / aria-labelledby / title / a real
            // <label>) is the page stating what this is called and is never touched.
            let _keepName = false;
            try {
              _keepName = !!(el.getAttribute('aria-label')
                             || el.getAttribute('aria-labelledby')
                             || (el.getAttribute('title') || '').trim()
                             || (el.labels && el.labels.length));
              if (!_keepName) {
                for (const n of el.childNodes) {
                  if (n.nodeType === 3 && /[\p{L}\p{N}]/u.test(n.nodeValue || '')) {
                    _keepName = true;
                    break;
                  }
                }
              }
            } catch (e2) {}
            if (!_keepName) {
              _e = Object.assign({}, e, { name: '', label: '', text: '' });
              _sawRolled = true;
            }
          }
        } catch (err) {}
        // `section=` is exactly what the tree replaces: an ancestor's label,
        // repeated on every row, when the ancestor is now one line above.
        let _row = _fmtLine(_e).replace(/ section=[a-z-]+/g, '');
        const _also = alsoRefs.get(el);
        if (_also && _also.length) {
          // Prepended, not appended: the refs are alternatives for the SAME
          // spot, so they belong in the slot the reader already scans for a ref
          // rather than in a trailing note that reads like a different element.
          const _ids = _also.slice().sort(docOrder)
            .map((n) => (ent.get(n) || {}).mmid).filter((m) => m != null);
          if (_ids.length) {
            _row = _row.replace(/^ref_\d+(?::\d+)? \| /,
              (m) => _ids.map((r) => 'ref_' + r).join(' ') + ' ' + m);
            _sawAlso = true;
          }
        }
        out.push(pad + _row);
      } else {
        const tag = (el.tagName || '').toLowerCase();
        let role = '', nm = '', extra = '';
        try { role = (el.getAttribute && el.getAttribute('role')) || ''; } catch (err) {}
        try {
          nm = (el.getAttribute && (el.getAttribute('aria-label') || el.getAttribute('title'))) || '';
        } catch (err) {}
        if (tag === 'table') {
          try {
            const rs = Array.from(el.querySelectorAll('tr')).filter((r) => {
              try { return r.closest('table') === el; } catch (e2) { return true; }
            }).length;
            const mm = el.getAttribute('mmid');
            extra = ` (${rs} rows${mm ? `, read with ref_${mm}` : ''})`;
          } catch (err) {}
        }
        const _bare = !role && !nm && !extra && (tag === 'div' || tag === 'span' || tag === 'li');
        if (!_bare) {
          out.push(pad + tag + (role && role !== tag ? `[${role}]` : '') + (nm ? ` "${nm}"` : '') + extra);
        } else {
          // A NODE THAT PRINTS NOTHING MUST NOT COST AN INDENT. #27 dropped the
          // word from bare div/span/li wrappers to save characters and left them
          // still incrementing depth, so every descendant row paid a space for a
          // line that is not there — visible as ref_69 at indent 2 with its own
          // child at indent 5. Indentation under an invisible parent also cannot be
          // read: the reader sees a gap, not a grouping, because there is no row at
          // the shallower level to group under.
          _blank = true;
        }
      }
      _emitChildren(kids.get(el) || [], _blank ? depth : depth + 1);
    };
    // IDENTICAL SIBLING SUBTREES COLLAPSE — and this is NOT a signature.
    //
    // The tree removes the fold's classification but not its compression: a
    // 178-cell calendar becomes 178 lines under one parent where the flat listing
    // spent one. Measured, that was the whole gap — most pages came out at
    // 1.02-1.12x and only the fold-heavy ones at 2.2x.
    //
    // The grouping is DERIVED, not guessed: siblings under one parent whose
    // subtree shapes are BYTE-IDENTICAL are the same kind of thing by
    // construction. No feature is selected, weighted or thresholded — it is an
    // equality test. That is what makes it right on both cases four signatures got
    // wrong: Hacker News' title/domain/user carry different classes so their shapes
    // differ and they never merge, while arXiv's 276 author links are identical
    // siblings and merge into one. Where shapes differ at all the answer is "do not
    // merge", which is the safe direction.
    //
    // Only LEAVES of the kept tree collapse. A node with kept children cannot fold
    // without deleting them, which is how folding lost state in the first place.
    const shapeOf = (el, d) => {
      if (d > 3) return '~';
      let k = (el.tagName || '').toLowerCase();
      try { const r = el.getAttribute('role'); if (r) k += '[' + r + ']'; } catch (err) {}
      try {
        const c = el.getAttribute('class');
        if (c) k += '.' + String(c).trim().split(/\s+/).sort().join('.');
      } catch (err) {}
      const cs = [];
      try { for (const ch of el.children) cs.push(shapeOf(ch, d + 1)); } catch (err) {}
      return k + (cs.length ? '(' + cs.join(',') + ')' : '');
    };
    function _emitChildren(list, depth) {
      const pad = ' '.repeat(depth);
      const groups = new Map();
      for (const c of list) {
        const leaf = !(kids.get(c) || []).length;
        const e = ent.get(c);
        // Actionable leaves group by shape, and so do structural CONTAINERS (they
        // collapse positionally below). A structural LEAF has nothing to collapse,
        // so it gets a key nothing else can match.
        const g = (e || !leaf) ? shapeOf(c, 0) : ('#' + out.length + '_' + c.tagName);
        if (!groups.has(g)) groups.set(g, []);
        groups.get(g).push(c);
      }
      // EMIT GROUPS IN DOCUMENT ORDER. Map iteration follows insertion order, so
      // a sibling list mixing collapsible groups with loose rows came out
      // reordered: on arXiv the loose author rows for papers 1, 7 and 11 printed
      // ABOVE the folded groups for papers 2, 3 and 4, and a reader taking the
      // tree top-to-bottom would attribute the wrong authors to the wrong paper.
      // A tree whose reading order is not the page's order is worse than a flat
      // list, because the indentation invites exactly that reading.
      const _ordered = Array.from(groups.values())
        .sort((x, y) => docOrder(x[0], y[0]));
      for (const members of _ordered) {
        // IDENTICAL SIBLING CONTAINERS COLLAPSE POSITIONALLY.
        //
        // Grouping only leaves left the compression gap that made the tree cost
        // +193%: the flat fold groups ACROSS parents, and cross-parent grouping is
        // precisely what needs the signature that failed four times. Collapsing
        // identical sibling CONTAINERS closes it without one — six month-cards on a
        // date picker are identical subtrees, so their contents line up by
        // POSITION, and position within an identical shape is a fact rather than a
        // judgement. This is MDR/DEPTA's data-record rule, and it is what makes a
        // repeated record compact AND complete: every member keeps its own ref.
        if (members.length >= 6 && !ent.get(members[0]) && (kids.get(members[0]) || []).length) {
          const cols = [];
          const walkKept = (el, acc) => {
            for (const c of (kids.get(el) || [])) { acc.push(c); walkKept(c, acc); }
          };
          let ok = true;
          const perMember = members.map((m) => { const a = []; walkKept(m, a); return a; });
          const n0 = perMember[0].length;
          // Identical shapes should yield identical kept counts; if they do not,
          // something differs that the shape key did not see, and the safe answer
          // is to print the members normally rather than align mismatched columns.
          for (const a of perMember) if (a.length !== n0 || !n0) ok = false;
          if (ok) {
            const tag0 = (members[0].tagName || '').toLowerCase();
            _foldGroups++;
            out.push(`${pad}${members.length}× ${tag0}, identical siblings, in document order`
                   + ` — one line per POSITION inside them; act on any ref:`);
            for (let i = 0; i < n0; i++) {
              const rep = perMember[0][i];
              const re = ent.get(rep);
              let head = '';
              if (re) head = `${re.tag}${re.type ? '[' + re.type + ']' : ''}`;
              else {
                head = (rep.tagName || '').toLowerCase();
                if (head === 'table') {
                  try {
                    head += ` (${Array.from(rep.querySelectorAll('tr')).filter((r) => {
                      try { return r.closest('table') === rep; } catch (e2) { return true; }
                    }).length} rows)`;
                  } catch (err) {}
                }
              }
              const cells = perMember.map((a) => {
                const x = a[i], xe = ent.get(x);
                if (!xe) { const mm = x.getAttribute && x.getAttribute('mmid'); return mm ? `ref_${mm}` : '-'; }
                const lab = (xe.name || xe.label || xe.text || '').trim();
                return lab ? `${xe.mmid}:${JSON.stringify(lab)}` : String(xe.mmid);
              }).join(' ');
              cols.push(`${pad}  #${i + 1} ${head}: ${cells}`);
            }
            for (const c of cols) out.push(c);
            continue;
          }
        }
        if (members.length >= 6) {
          const e0 = ent.get(members[0]);
          if (!e0) { for (const m of members) emit(m, depth); continue; }
          const items = members.map((m) => {
            const me = ent.get(m);
            const lab = (me.name || me.label || me.text || '').trim();
            const fl = (me.disabled ? '(disabled)' : '') + (me.required ? '(required)' : '')
                     + (me.active ? `(${me.active})` : '') + (me.collapsed ? '(collapsed)' : '')
                     + (me.hasPopup ? '(opens menu)' : '') + (me.newTab ? '(new tab)' : '')
                     + (me.clickable === false ? '(occluded)' : '')
                     + (me.offscreen ? ((me.y || 0) < 0 ? '(above-fold)' : '(below-fold)') : '');
            const bx = geometry ? `@(${me.x},${me.y})` : '';
            return `${me.mmid}:${JSON.stringify(lab)}${bx}${me.href ? '→' + me.href : ''}${fl}`;
          }).join(' ');
          const _t0 = members.every((m) => ent.get(m).type === e0.type) && e0.type ? `[${e0.type}]` : '';
          _foldGroups++;
          out.push(`${pad}${members.length}× ${e0.role || e0.tag}${_t0}, identical siblings, in document order`
            + `${e0.href ? ' — each a link, ref:"label"→href' : ' — ref:"label"'}`
            + ` (act on any via its ref): ${items}`);
        } else {
          for (const m of members) emit(m, depth);
        }
      }
    }
    _emitChildren(roots, 0);
    return out;
  };
  const lines = [];
  const emittedBlocks = new Set();
  // PROMINENCE, NOT MEMBERSHIP. Everything a heuristic judged to be decoration is
  // still here and still actionable by ref — it just goes last, compacted to one
  // line. That is the whole architectural bet: a heuristic's accuracy on a site
  // nobody has seen is unknowable, so it must never decide whether an element
  // EXISTS for the agent; it may only decide how loudly the element is announced.
  // Measured cost of moving these eight rules out of membership: +6.8% listing
  // chars (median page +1.8%) against a 3.3% drift floor — while the constant
  // legend block, which buys nothing on any accuracy metric, costs 24.4%.
  const _demoted = [];
  // Set by _treeLines when it puts more than one ref on a row, so the legend
  // line explaining that notation appears only when the notation does (#13).
  let _sawAlso = false;
  // Set when a container's label was dropped because its descendants account
  // for all of it — the legend says so only when it happened.
  let _sawRolled = false;
  let _foldGroups = 0;   // how many fold GROUPS this listing printed (see the legend)
  if (TREEFMT) {
    for (const l of _treeLines()) lines.push(l);
  } else
  for (const e of shown) {
    if (inCompact.has(e.mmid)) {
      if (!emittedBlocks.has(e.groupKey)) {
        lines.push(compactBlocks.get(e.groupKey));
        emittedBlocks.add(e.groupKey);
      }
      continue;
    }
    if (e.demoted) { _demoted.push(e); continue; }
    lines.push(_fmtLine(e));
  }
  if (_demoted.length) {
    // One line, refs intact. An agent that finds nothing above can still act on
    // any of these; nothing is hidden, and the reason is named.
    const _by = new Map();
    for (const e of _demoted) {
      const why = String(e.demoted).replace(/^was:/, '');
      if (!_by.has(why)) _by.set(why, []);
      _by.get(why).push(e);
    }
    const _parts = [];
    for (const [why, es] of _by) {
      _parts.push(`${es.length} ${why} (${es.map((e) => 'ref_' + e.mmid).join(' ')})`);
    }
    lines.push(`PROBABLY DECORATION — ${_demoted.length} element(s) kept but not detailed, `
      + `because a size/shape/label heuristic (never a spec rule) judged them non-content. `
      + `They are still actionable by ref if nothing above matches: ${_parts.join('; ')}`);
  }
  function _fmtLine(e) {
    // `button[button]` -> just `button` (the type='button' default is noise).
    // Custom-element tags (web components like `ytd-guide-entry-renderer`) are
    // noise to the model — show the ARIA role instead when present.
    const baseTag = (e.tag.includes('-') && e.role) ? e.role : e.tag;
    const tagtype = (e.type && !(baseTag === 'button' && e.type === 'button')) ? `${baseTag}[${e.type}]` : baseTag;
    // Render NAME / VALUE / PLACEHOLDER as separate fields so the model never
    // has to guess whether a quoted string is the field's identity, its
    // current contents, or a hint. Falls back to button/link text for
    // non-form elements.
    let identity = '';
    if (e.name)        identity += ` name=${JSON.stringify(e.name)}`;
    if (e.value)       identity += ` value=${JSON.stringify(e.value)}`;
    if (e.placeholder) identity += ` placeholder=${JSON.stringify(e.placeholder)}`;
    // For pure buttons/links (no name/value/placeholder), show their text, then
    // fall back to any synthesized label, then to an explicit icon-control hint
    // so a label-less control is still targetable (and the agent knows why it
    // has no text — a candidate for analyze_screen if the icon's purpose is
    // unclear).
    // `text` wins over `label` in general, and must: an earlier ordering bug let a
    // hoisted label suppress an element's own visible text. But when the label
    // strictly CONTAINS the text and is longer, it is the same content plus more —
    // provable from the two strings, not a preference. That is the icon+badge
    // case: text "3", label "search (3)", and printing the text alone gave
    // `a "3"` for a messages menu, which is the failure the icon lookup exists to
    // prevent and could not reach.
    if (!identity && e.text) {
      identity = (e.label && e.label.length > e.text.length && e.label.indexOf(e.text) >= 0)
        ? ` "${e.label}"` : ` "${e.text}"`;
    }
    if (!identity && e.iconOnly) identity = " (unlabeled-icon)";
    else if (!identity && e.label) identity = ` "${e.label}"`;
    // near= is ALWAYS a supplement, never a replacement — an earlier ordering
    // bug let it suppress the element's own visible text (lobste.rs tag "web"
    // rendered as just near="<story title>", unfindable by its label).
    if (e.near && e.near !== e.name && e.near !== e.text) identity += ` near=${JSON.stringify(e.near)}`;
    // detail='full' fields. href/src are what a compact listing structurally
    // cannot express, so they are the whole point of the level.
    if (e.href) identity += ` href=${JSON.stringify(e.href)}`;
    if (e.src)  identity += ` src=${JSON.stringify(e.src)}`;
    const act = e.active ? ` (${e.active})` : "";
    const rl  = (e.role && e.role !== e.tag) ? ` role=${e.role}` : "";
    const sec = e.section ? ` section=${e.section}` : "";
    const req = e.required ? " (required)" : "";
    const uns = e.unselected ? " (unselected)" : "";
    const dis = e.disabled ? " (disabled)" : "";
    const sy  = !e.synth ? ""
      : e.synth === 'icon-class'
        ? ` (name read off an icon-library class name, not an accessible name)`
        : ` (name taken from ${e.synth} — an automation hook, not an accessible name)`;
    const nt  = e.newTab ? " (opens NEW tab)" : "";
    const tp  = e.topNav ? " (REPLACES the whole page, destroying this frame and every f-ref in it)" : "";
    // SHORT TAGS, explained once in the legend. These parentheticals used to
    // carry a full sentence of instructions EACH, re-emitted on every matching
    // row — on an element-dense page that is the single largest block of
    // repeated tokens in the listing.
    const ed  = e.editable ? " (rich-text-editor)" : e.codeEditor ? " (code-editor)" : "";
    // (opens menu/popup): click-then-pick affordance. Suppressed on comboboxes
    // and native selects — their role/tag already says it.
    const pop = (e.hasPopup && e.role !== 'combobox' && e.tag !== 'select') ? " (opens menu/popup)" : "";
    const col = (e.collapsed && !e.active) ? " (collapsed)" : "";
    const sr  = e.scrollRegion ? " (scrollable-region)" : "";
    const cnv = (e.canvasLike || e.tag === 'canvas') ? " (canvas)" : "";
    const xf  = e.crossFrame ? " (cross-origin-iframe)" : "";
    const orph = e.orphanWidget ? " (DEAD-DUPLICATE)" : "";
    // Name the hidden control this widget is wired to, so the agent can CONFIRM which
    // twin is live instead of taking (DEAD-DUPLICATE) on faith.
    const bak = (e.backedBy && !e.orphanWidget) ? ` backed-by=ref_${e.backedBy}` : "";
    const occ = e.clickable === false ? " (occluded/blocked)" : "";
    const clip = e.clippedInContainer ? " (clipped-in-scroll-panel)" : "";
    // DIRECTION MATTERS. `(below-fold)` was printed for anything off-screen,
    // including elements SCROLLED PAST — three agents independently reported
    // y=-5504, y=-2401, y=-1215 all tagged "below-fold", and the accompanying
    // advice ("scroll down and re-observe") sends the agent further away from
    // the target. The sign of y already says which way.
    // DIRECTION, ON ALL THREE AXES THAT EXIST. This read `y < 0 ? above : below`,
    // a two-way answer to a three-way question. Offscreen entries DO reach the
    // string listing — modal scroll content is the common case — and a control
    // parked off to the SIDE (a carousel slide, a kanban column, an RTL page
    // scrolled horizontally) was labelled "(below-fold)", sending the agent
    // scrolling down for something that is sideways. Same shape of defect as
    // CLAUDE.md #23's "you have scrolled past them" asserted at scrollY === 0:
    // a confident direction that is simply the wrong one.
    // `innerWidth`/`innerHeight` are read directly rather than via the outer
    // vw/vh consts — reaching across scopes for those is exactly the swallowed
    // ReferenceError that R8 exists to catch.
    let off = "";
    if (e.offscreen) {
      const _ey = e.y || 0, _ex = e.x || 0;
      if (_ey + (e.h || 0) <= 0) off = " (above-fold)";
      else if (_ey >= innerHeight) off = " (below-fold)";
      else if (_ex >= innerWidth || _ex + (e.w || 0) <= 0) off = " (off to the side — scroll horizontally)";
      else off = " (outside the viewport)";
    }
    const med = e.mediaOnly ? (e.cssBackground ? " (media — CSS background, not an <img>)" : " (media — not a control)") : "";
    // GEOMETRY IS OPT-IN. box(x,y,w,h) was on every row: ~22 characters times
    // 199 rows is ~4,400 on the craigslist listing, and WorkArena
    // (arXiv:2403.07718) measured adding coordinates to an AXTree at 68.2% ->
    // 72.6% on MiniWoB's small pages but 45.5% -> 41.2% on its complex ones —
    // "seemingly harmless features actually degrade performance" once the
    // observation is already large, and dense pages are our case. Refs
    // re-measure at click time (fix #11), so no action needs the number; it
    // exists for the agent's spatial reasoning, which is the use that measured
    // negative. Ours is also partly untrustworthy already: #23 records ~110px
    // drift on loading pages and #25 the same ref reporting clicks 1,097px apart
    // on OpenStreetMap.
    // Spatial STATE survives regardless — (below-fold), (above-fold),
    // (off to the side), (occluded/blocked), (clipped-in-scroll-panel) are all
    // untouched. Only the exact numbers move behind `geometry=true`, and x/y/w/h
    // stay in the structured array unconditionally for find, delta and computer.
    const box = geometry ? ` | box(${e.x},${e.y},${e.w},${e.h})` : '';
    return `ref_${e.mmid} | ${tagtype}${identity}${act}${rl}${sec}${req}${uns}${dis}${orph}${bak}${nt}${tp}${sy}${ed}${pop}${col}${cnv}${xf}${sr}${med}${box}${occ}${clip}${off}`;
  }
  // ROLELESS OVERLAYS: some consent layers (Ryanair's CMP) are plain divs —
  // no role=dialog anywhere, so the modal banner can't anchor. The occlusion
  // pass still knows the truth: nearly everything is blocked except a small
  // cluster (the overlay's own buttons). Say so.
  let overlayLikely = false;
  if (!dialogOpen) {
    let page = 0, blocked = 0;
    for (const e of out) {
      if (e.offscreen) continue;
      page++;
      if (e.physBlocked || e.clickable === false) blocked++;
    }
    const clear = page - blocked;
    if (page >= 8 && blocked / page >= 0.6 && clear >= 1 && clear <= 12) overlayLikely = true;
  }
  // MODAL TEXT. The interactive listing scopes beautifully to an open dialog but shows only
  // its CONTROLS, so "what does this modal say?" required a screenshot or a whole-page text
  // dump — flagged in two separate benchmark rounds. A modal's message is usually the reason
  // it opened, and it is a few dozen characters.
  let dialogText = '';
  if (dialogOpen) {
    try {
      const d = _allComposed('[role="dialog"],[role="alertdialog"],[aria-modal="true"],dialog')
        // Same visibility test dialogOpen uses. Filtering on rect alone let a
        // Bootstrap offcanvas drawer (role=dialog, translateX(-110%),
        // visibility:hidden, full-height rect) outrank the real modal by AREA, so
        // "what does this modal say?" was answered from an invisible element.
        .filter(x => {
          const r = x.getBoundingClientRect();
          if (!(r.width > 0 && r.height > 0)) return false;
          if (r.right <= 0 || r.bottom <= 0 || r.left >= vw || r.top >= vh) return false;
          try {
            const c = getComputedStyle(x);
            if (c.visibility === 'hidden' || c.display === 'none' || parseFloat(c.opacity || '1') === 0) return false;
          } catch (e) {}
          return true;
        })
        .sort((a, b) => (b.getBoundingClientRect().width * b.getBoundingClientRect().height) -
                        (a.getBoundingClientRect().width * a.getBoundingClientRect().height))[0];
      if (d) {
        // Read from the LIVE element, not a detached clone. innerText depends on LAYOUT:
        // on a cloneNode() that is not in the document it silently degrades to textContent,
        // so there are no block newlines to split on and the heading ends up welded to the
        // body ("Modal titleWoo-hoo, you're reading this text in a modal!"). Instead take
        // the live innerText (which does have block breaks) and drop the lines that merely
        // repeat a control's own label, since those are listed individually above.
        const NL = String.fromCharCode(10);
        const ctrlLabels = new Set();
        try {
          // Composed-scoped: a web-component dialog keeps its buttons in its own
          // shadow root, where d.querySelectorAll cannot reach them — their text
          // would then survive as "prose" and the dialog message would read
          // "Are you sure? Cancel Delete".
          const inD = (n) => { let w = n; while (w) { if (w === d) return true; w = composedParent(w); } return false; };
          _allComposed('button, [role="button"], input, select, textarea, a').forEach(function (c) {
            if (!inD(c)) return;
            const lab = (c.innerText || c.value || c.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
            if (lab) ctrlLabels.add(lab);
          });
        } catch (e) {}
        const t = (d.innerText || '').split(NL)
          .map(function (x) { return x.replace(/[ 	]+/g, ' ').trim(); })
          .filter(function (x) {
            if (!x || ctrlLabels.has(x)) return false;
            // Inline controls share a line: two adjacent buttons render as one text run
            // ("CancelDelete"), which matches neither label on its own. Strip every known
            // control label out of the line; if nothing meaningful is left, the line was
            // just buttons.
            let rest = x;
            ctrlLabels.forEach(function (lab) { rest = rest.split(lab).join(''); });
            // Any script. The ASCII form emitted an EMPTY dialog text for every
            // Japanese/Chinese/Korean/Russian/Arabic modal — the one place the
            // agent most needs prose, on the pages where it can least guess it.
            return /[\p{L}\p{N}]/u.test(rest);
          })
          .join(' — ');
        // Dialog text is content: generous, marked once (it used to carry BOTH a
        // cut and a separate ' …(truncated)' suffix, i.e. two markers for one cut).
        if (t) dialogText = 'Dialog text: ' + JSON.stringify(markCut(t, 4000)) + NL;
      }
    } catch (e) {}
  }
  // THE BANNER MUST NAME SOMETHING THE LISTING ACTUALLY PRINTS. It told the agent
  // to "focus on elements with section=dialog" in BOTH formats, and #27 strips
  // `section=` from tree rows on purpose — the tree states containment by position
  // instead. So in the default format `section=dialog` appeared only in the LEGEND
  // describing the notation, never on a row, and the one instruction the agent gets
  // when a modal is open was unfollowable. The information was there the whole time
  // (`div[dialog]` with the dialog's controls indented beneath it); only the wording
  // pointed at the other format. Also fixes the in-frame case for free: a dialog
  // inside a same-origin frame nests correctly in the tree while its rows are
  // tagged `section=iframe`, so naming the nesting is right there too.
  const banner = dialogOpen
    ? (TREEFMT
       // NAME THE MARKER THE ROW ACTUALLY CARRIES. The first version of this said
       // "the row marked [dialog]" — and the tree prints `role=dialog`, never
       // `[dialog]`. Square brackets ARE live notation here (`div[region]`,
       // `input[radio]`), so `[dialog]` reads as a real token of this vocabulary,
       // an agent searching for it gets zero hits, and the reasonable conclusion
       // is that the dialog was not listed. That is the identical
       // instruction-names-an-absent-marker defect this banner was just rewritten
       // to fix, reintroduced in the rewrite and caught by a live agent.
       // ...and the tree has TWO renderings for a dialog, so no single literal is
       // safe to quote: a dialog that earned its own ref prints as an entry
       // (`div name="…" role=dialog`), while one that is only structure prints in
       // the node form (`div[dialog]`). Naming either literal is wrong half the
       // time — the first attempt named `[dialog]` and a live agent searching for
       // it on a page of the other kind found nothing and concluded the dialog was
       // not listed. So the banner describes the ROLE in prose, which is true of
       // both forms, and TR14 asserts the general property: any literal token the
       // banner quotes must appear on a row.
       ? "*** A MODAL/DIALOG IS CURRENTLY OPEN — work inside the dialog node below (the row whose role is dialog, with its controls indented under it); ignore rows outside that subtree unless you need to dismiss the modal. ***\n"
       : "*** A MODAL/DIALOG IS CURRENTLY OPEN — focus on elements with section=dialog (or overlay-banner/menu items nested inside it); ignore underlying-page elements unless you need to dismiss the modal. ***\n")
    : overlayLikely
    ? "*** MOST PAGE ELEMENTS ARE BLOCKED BY AN OVERLAY (likely a consent/notification layer). The few elements WITHOUT (occluded/blocked) are the overlay's own controls — handle those first. ***\n"
    : "";
  // BLANK PAGE: zero interactive elements + (nearly) no text means the page
  // hasn't rendered (bot-gated or still hydrating) — without this note, an
  // empty listing is indistinguishable from "a page with no controls".
  let blankNote = '';
  if (out.length === 0) {
    let txtLen = 0;
    try { txtLen = ((document.body && document.body.innerText) || '').trim().length; } catch (e) {}
    blankNote = txtLen < 80
      ? "\n[PAGE APPEARS BLANK: no interactive elements and almost no text. It may be bot-gated, errored, or still loading — wait and re-observe, or take a computer screenshot to inspect pixels.]"
      // Text exists but ZERO controls — almost always a heavy app still booting
      // (JupyterLite's WASM takes seconds) or content behind an inaccessible
      // frame. Either way the agent must not conclude "nothing to do here".
      : "\n[NO interactive elements found (page has text but zero controls). The app may still be loading or its UI may live in an inaccessible frame — wait and re-observe, or take a computer screenshot.]";
  }
  // LEGEND — flag-driven, not fixed. The old block emitted ~1.5 KB of legend on
  // EVERY observation (even on pages with zero elements), and an agent calls this
  // tool dozens of times per task — pure repeated token cost. Now only the lines
  // whose flags ACTUALLY APPEAR in this listing are included, and the tool names
  // are the real MCP surface (form_input / fill_form / computer), not the retired
  // internal names (enter_text_tool / fill_form_tool / click_tool / analyze_screen)
  // which named tools the agent cannot call.
  const legend = (() => {
    // An unscoped empty page has nothing to explain; a scoped empty result does,
    // and the explanation is built a few lines below — so do not short-circuit past it.
    if (!out.length && !scopeMmid) return '';
    const has = (fn) => { try { return shown.some(fn); } catch (e) { return false; } };
    // A scoped read of one or two elements does not need the notation lecture.
    // The section= line alone is ~700 chars, so on a single-anchor result the
    // legend was roughly 80% of the payload — measured by an agent that scoped
    // to one nav link and got a wall of explanation with it. The agent that
    // scoped already knows what it asked for; keep only how to act on it.
    // AN EMPTY SCOPED LISTING MUST SAY WHY. Five live agents hit this, from four
    // different causes, and every one produced the identical output: the header
    // line and nothing else. That reads as "this container has no controls", which
    // was true in none of the cases — the causes were (a) the container is outside
    // the viewport (a scroll makes the same call work), (b) an ancestor is
    // aria-hidden because a menu is open elsewhere, (c) the element is a canvas or
    // other leaf with nothing inside, (d) it genuinely has no interactive
    // descendants. One agent recorded a wrong diagnosis from it and another had to
    // drop to javascript_tool. The facts that distinguish them are all measurable
    // right here.
    if (scopeMmid && !out.length) {
      const why = [];
      try {
        const host = mmidReg && mmidReg.get ? mmidReg.get(String(scopeMmid)) : null;
        if (host) {
          const hr = host.getBoundingClientRect();
          if (hr.bottom < 0 || hr.top > vh || hr.right < 0 || hr.left > vw) {
            why.push(`it is OUTSIDE the current viewport (box(${Math.round(hr.x)},`
              + `${Math.round(hr.y)},${Math.round(hr.width)},${Math.round(hr.height)}) vs a `
              + `${vw}x${vh} viewport) and the listing is viewport-scoped — `
              + `computer(action="scroll_to", ref="ref_${scopeMmid}") then read again`);
          }
          if (host.closest && host.closest('[aria-hidden="true"]')) {
            why.push(`an ancestor is aria-hidden="true" — usually a library marking the `
              + `page inert behind an OPEN menu or dialog somewhere else; close that and re-read`);
          }
          if (host.hasAttribute && host.hasAttribute('inert')) {
            why.push(`it is inside an [inert] region`);
          }
          const inner = host.querySelectorAll
            ? host.querySelectorAll('a,button,input,select,textarea,[role],[tabindex],[onclick]').length : 0;
          if (!why.length) {
            why.push(inner
              ? `it holds ${inner} candidate element(s), none of which passed the `
                + `interactivity/visibility filters — read with ledger:true to see which rule dropped them`
              : `it genuinely contains no interactive descendants (for its TEXT use `
                + `read_page(ref_id="ref_${scopeMmid}", filter="all"); for pixel content take a screenshot)`);
          }
        } else {
          why.push(`ref_${scopeMmid} is no longer in this document`);
        }
      } catch (e) {}
      return `Scoped listing for ref_${scopeMmid}: 0 elements — NOT necessarily empty. `
           + why.join('; ') + `.
`;
    }
    if (scopeMmid && out.length <= 2) {
      return `Scoped listing (${out.length} element${out.length === 1 ? '' : 's'}). ` +
             `Act on one by its ref — pass ref_<N> for the mmid=<N> below.
`;
    }
    const L = [`Visible interactive elements (${out.length} on screen).`];
    // A COUNT IS ONLY HONEST IF IT SAYS WHAT IT EXCLUDED. aria-hidden is set by
    // libraries on everything BEHIND an open menu or dialog and cleared when it
    // closes, so a large count here does not mean the page is small — it means
    // the page is in a state. Without this line, "(2 on screen)" on a page with
    // 39 buttons is worded and punctuated exactly like a true count of 2, and
    // the recovery (close the menu, re-read) is underivable.
    // HIDDEN-TAB LAYOUT GATING. The agent's tab is hidden by design — fix #12
    // exists precisely so we never activate it and drag the user out of their
    // work — and some sites defer layout until visibilityState flips. Unsplash
    // keeps its entire results grid display:none until then: read_page reported
    // 18 elements on a page holding 88 photo links, while one `computer` call
    // (which attaches CDP and sets the lifecycle state active) flipped the same
    // read to 60. Two tools, two different pages, no signal.
    // Fires on the SYMPTOM, never merely on "the tab is hidden" — that is always
    // true, so an unconditional note would be noise of exactly the kind #15
    // warns about. The symptom is a large gap between the controls the DOM holds
    // and the controls we could see.
    try {
      // NOT ON A SCOPED READ. The signal is a gap between what the DOCUMENT holds
      // and what we collected — which is meaningless once the caller has narrowed
      // the read to one container, where a large gap is the entire point. Observed
      // live: a read scoped to craigslist's footer returned 7 links under
      // "the DOM holds 955 controls but only 7 were collectable", inviting the
      // agent to go hunting for 948 elements it had just excluded on purpose. Same
      // class as #11's page-level facts leaking into scoped reads (Main heading,
      // below-fold counts), and the same fix.
      if (document.visibilityState === 'hidden' && !scopeMmid) {
        let _domCtl = 0;
        try {
          for (const _c of document.querySelectorAll('a[href],button,input,select,textarea')) {
            if (_c.offsetParent !== null || (_c.getClientRects && _c.getClientRects().length)) _domCtl++;
          }
        } catch (e2) { _domCtl = document.querySelectorAll('a[href],button,input,select,textarea').length; }
        if (_domCtl >= 20 && out.length * 3 <= _domCtl) {
          L.push(`  - NOTE: the DOM holds ${_domCtl} controls but only ${out.length} were collectable.`
               + ` This tab is in the BACKGROUND (visibilityState="hidden"), and some sites defer`
               + ` layout until a tab is visible, leaving content display:none. If this page looks`
               + ` emptier than it should: take a computer screenshot (that activates rendering`
               + ` without focusing the tab) and read again.`);
        }
      }
    } catch (e) {}
    // DO NOT ASSERT A CAUSE THIS CANNOT KNOW. The single wording below used to
    // claim a library had marked the page inert behind an OPEN menu and that
    // closing it brings the elements back. Measured live, that is false on every
    // react-select and MUI page: react-select.com raised it for 27 elements when
    // all 43 aria-hidden nodes were the library's own indicator wrappers holding
    // zero controls, and MUI raised it for 195 when its only hidden controls were
    // 19 native-input mirrors that are aria-hidden by design AND already listed
    // as `backed-by=`. A permanent banner naming an impossible recovery is the
    // "always-on warning trains the reader to ignore it" failure #15 fixed for
    // loading images, and it sat at the top of every observation.
    //
    // Split on evidence: an actually-open dialog, or hidden elements that carry a
    // name/text of their own, means content really is being withheld. Otherwise
    // report the fact without the story, and only when the count is large enough
    // to be worth a line at all.
    const _ah = _stateDrops['aria-hidden'], _ahN = _stateDrops['aria-hidden-named'];
    // ONLY ASSERT AN OPEN OVERLAY WHEN ONE IS ACTUALLY OPEN. This branch used to
    // fire on `dialogOpen || _ahN >= 3` — i.e. an element merely HAVING a label
    // was taken as evidence that a menu or dialog was open — and then prescribed
    // "close it (Escape, or click the trigger again) and re-read, and they come
    // back". Four independent live agents reported it on pages with nothing open:
    // NHK 239 elements, Al Jazeera 130, antd 306, Vuetify 168 and 312, Wikipedia
    // 35, every menu trigger on those pages printing `(collapsed)`. On Shoelace
    // the count GREW from 554 to 558 after the one real dialog was dismissed,
    // which disproves the promised recovery outright: closing brought back fewer.
    //
    // An agent that cannot find an element is told a few hundred are recoverable
    // by dismissing an overlay that does not exist, and burns calls pressing
    // Escape while the same output already carries the real recovery (`find`, or a
    // scoped read of a named region). Worst case it manufactures a phantom modal
    // on a clean page. Same rule as #23's cross-extension message and #14's stale
    // ref: state the FACT, list causes as causes, and never assert a recovery the
    // tool has not verified.
    // ...and it is a WHOLE-DOCUMENT count, so it does not belong in a scoped read.
    // `_stateDrops` accumulates over the entire collection walk, so a read scoped to
    // one <button> reported "312 interactive element(s) are NOT listed because an
    // ancestor is aria-hidden" — a number about the page, printed under a header
    // promising that elements outside the scope are omitted. Reported live by two
    // agents, alongside the table leak fixed above; the same #26 class.
    if (scopeMmid) {
      // nothing: the count describes the document, not this subtree
    } else if (_ah >= 3 && dialogOpen) {
      L.push(`  - NOTE: ${_ah} interactive element(s) are NOT listed because an`
           + ` ancestor is aria-hidden="true"${_ahN ? ` (${_ahN} of them carry their own label or text)` : ''}.`
           + ` A dialog IS open (see the banner above), and marking the rest of the page`
           + ` hidden is how focus-trap libraries do that — dismiss it and re-read to see`
           + ` the page again. This is page STATE, not the page's contents.`);
    } else if (_ah >= 3 && _ahN >= 3) {
      L.push(`  - NOTE: ${_ah} interactive element(s) are NOT listed because an`
           + ` ancestor is aria-hidden="true"${_ahN ? ` (${_ahN} of them carry their own label or text)` : ''}.`
           + ` Nothing here indicates an open dialog, so this is most likely a CLOSED`
           + ` menu/panel kept in the DOM, or a library's own duplicate markup. Do not go`
           + ` hunting for something to dismiss: if you are missing a specific element,`
           + ` read_page(ledger=true) names what was dropped and why, and find() reaches`
           + ` elements this viewport-scoped listing omits. This is page STATE, not the`
           + ` page's contents.`);
    } else if (_ah >= 25) {
      L.push(`  - NOTE: ${_ah} interactive element(s) sit under aria-hidden="true" ancestors and are`
           + ` not listed, and NONE of them carry a label or text of their own — on component`
           + ` libraries that is the library's own scaffolding (indicator wrappers, mirror inputs`
           + ` already shown here as backed-by=), not withheld page content. If you expected`
           + ` something here, read_page(ledger=true) names them.`);
    }
    if (_sawAlso)                L.push(`  - ref_A ref_B | ... — one row, several refs: nested elements with the SAME label and the SAME box. Any of them acts on that spot; they are listed together instead of as identical rows.`);
    if (_sawRolled)              L.push(`  - a container row with no text of its own — its label was every label indented beneath it, so it is not repeated here.`);
    // TWO FOLDS ARE NOT TWO COLUMNS OF ONE TABLE. Each group's "in document order"
    // is true OF THAT GROUP, and printing two of them invites reading position N of
    // one against position N of the other. Measured live on Hacker News: a 17-member
    // group of comment counts printed ABOVE a 16-member group of story titles, both
    // claiming document order, and zipping them paired every title with the previous
    // story's count — "The Art and Beauty of Blade Runner" against 50 comments when
    // its real count was 21, all 16 pairs shifted by one, with nothing stating the
    // length mismatch or the offset. #27 cited this as a reason the tree beats a
    // flat list and left it unsaid in the output.
    // The join key is already on every member: refs are assigned in document order,
    // so a title at ref_218 belongs with the count at ref_232, not with the first
    // number in the other line. Saying so costs one line and only when it applies.
    // Kept SHORT deliberately: the first wording ran 277 chars and pushed the tree
    // past the flat listing on TR7's fixture, which is a standing budget guard. The
    // load-bearing facts are that positions do not correspond across groups and that
    // refs do; everything else was explanation.
    if (_foldGroups >= 2)
      L.push(`  - member POSITIONS do not correspond BETWEEN folded groups (one may lack a member another has) — pair by nearby ref number, not by position.`);
    if (has(e => e.name))        L.push(`  - name="..." — IDENTITY (label / accessible name).`);
    if (has(e => e.near))        L.push(`  - near="..." — nearest visible text: a HINT for unnamed fields, never the real name.`);
    if (has(e => e.value))       L.push(`  - value="..." — CURRENT CONTENTS; empty/absent means blank.`);
    if (has(e => e.placeholder)) L.push(`  - placeholder="..." — a format HINT, not a value.`);
    if (has(e => e.active))      L.push(`  - (current)/(selected)/(checked)/(expanded) — already active; don't re-click unless deselecting.`);
    if (has(e => e.required))    L.push(`  - (required) — must be filled for submission.`);
    if (has(e => e.unselected))  L.push(`  - (unselected) — still showing placeholder text; pick a real option with fill_form.`);
    if (has(e => e.disabled))    L.push(`  - (disabled) — inert; clicking does nothing right now.`);
    if (has(e => e.newTab))      L.push(`  - (opens NEW tab) — link leaves this tab.`);
    if (has(e => e.topNav))      L.push(`  - (REPLACES the whole page) — in-frame link with target="_top"/"_parent": navigates the TOP document, invalidating every ref here.`);
    // Short per-row tags, explained here ONCE instead of re-stating a full
    // sentence of instructions on every matching element.
    if (has(e => e.orphanWidget))
      L.push(`  - (DEAD-DUPLICATE) — no backing form control, while an identical widget here has one. Act on the twin; this one is usually inert however visible it looks.`);
    if (has(e => e.clippedInContainer))
      L.push(`  - (clipped-in-scroll-panel) — out of view in an inner scroll panel; clicking auto-scrolls to it.`);
    if (has(e => e.offscreen))
      L.push(`  - (below-fold) — outside the viewport; clicking auto-scrolls to it.`);
    if (has(e => e.canvasLike || e.tag === 'canvas'))
      L.push(`  - (canvas) — pixel-drawn; contents are NOT listed. Screenshot, then click by coordinate — re-read with geometry=true for the box() to convert screenshot pixels against.`);
    if (has(e => e.crossFrame))
      L.push(`  - (cross-origin-iframe) — contents not listed; screenshot + coordinate clicks.`);
    if (has(e => e.editable || e.codeEditor))
      L.push(`  - (rich-text-editor) / (code-editor) — use form_input, not computer.`);
    if (has(e => e.scrollRegion))
      L.push(`  - (scrollable-region) — content scrolls independently of the page.`);
    if (has(e => e.iconOnly))
      L.push(`  - (unlabeled-icon) — real control, no text label; screenshot if its purpose is unclear.`);
    if (has(e => e.clickable === false))
      L.push(`  - (occluded/blocked) — painted over; may not receive clicks.`);
    if (has(e => e.role === 'combobox' || e.tag === 'select'))
      L.push(`  - role=combobox / <select> — a DROPDOWN. Never type into one; pass the option TEXT to fill_form or form_input, which click-then-pick (typing into a BUTTON/DIV combobox fails silently).`);
    // NAME ONLY THE SECTIONS ACTUALLY PRESENT. Every other legend line is gated on
    // the notation appearing; this one alone enumerated all twelve possible values
    // and appended a paragraph about overlay-banners regardless. Measured on the
    // saucedemo login page — three elements, all section=form — it was ~610 of the
    // ~900 chars that a default read returns, which is how a max_chars=900 read cut
    // EVERY element row and returned pure legend. Explaining notation the listing
    // does not use is what pushed out the listing itself.
    // ...AND NOT IN THE TREE, where `_treeLines` strips ` section=` from every row
    // because the enclosing node is printed one line above. The gate above asks
    // whether any ENTRY carries a section, which was true regardless of format, so
    // the default listing explained a notation it then removed — the same "legend
    // describes what the listing does not use" failure this block was written to
    // fix, reintroduced by #27 changing the default format underneath it. The
    // banner had the same bug and is fixed at its own site.
    if (!TREEFMT && has(e => e.section)) {
      const secs = [];
      try {
        shown.forEach((e) => { if (e.section && secs.indexOf(e.section) < 0) secs.push(e.section); });
      } catch (e) {}
      secs.sort();
      let line = `  - section=... — the containing region (${secs.join(' / ')}).`;
      if (secs.indexOf('table-header') >= 0)
        line += ` Use it to disambiguate same-named items: a "Name" button in section=table-header is a column sort, NOT a form field.`;
      else if (secs.length > 1)
        line += ` Use it to disambiguate same-named items.`;
      if (secs.indexOf('overlay-banner') >= 0)
        line += ` overlay-banner = a FIXED bar sitting over the page: often a consent/notification strip worth dismissing first, but it can also be the page's own sticky controls (a media player bar, a sticky "add to cart" row) — read its contents before deciding to dismiss it.`;
      L.push(line);
    }
    // WHAT IS NOT HERE, and how to get it. Filtering is fine; SILENT filtering is
    // not — a compact listing has no href, no image src and no plain <img> at
    // all, and without this line the agent cannot know that, so it either
    // guesses or reports the page doesn't have what it does have. One sentence,
    // stated once, is the entire cost of making the omission recoverable.
    if (WANT_URLS) {
      L.push(`  - href="..." / src="..." — ${BRIEF ? 'destination paths (detail="brief"); host is shown only when it differs from this page, and long query strings are cut to "?…". Re-read with detail="full" if you need a URL verbatim' : 'real URLs (detail="full")'}. (media — not a control) rows are images/video, listed for their src only.`);
    } else {
      // Only advertise the escape hatch when this page actually HAS something it
      // would reveal. The line costs ~250 chars on every observation, and the
      // median listing is under 4 KB — that is a ~6% tax to pay on a form-only
      // page with no links and no images, where the advice is inapplicable.
      // (document.images is a live collection; reading .length costs nothing.)
      let _hasMedia = false;
      try {
        // document.images is light-DOM only and sees no CSS backgrounds — so on a
        // component-heavy or background-image page (precisely why `full` gained a
        // background scan) the line advertising `full` was suppressed, restoring
        // the silent omission it exists to end. Use the composed registry.
        _hasMedia = _allComposed('img, video, audio').length > 0;
        if (!_hasMedia) {
          let budget = 150;
          for (const n of mmidReg.values()) {
            if (budget-- <= 0) break;
            const r2 = n.getBoundingClientRect();
            if (r2.width < 80 || r2.height < 60) continue;
            const bg = getComputedStyle(n).backgroundImage || '';
            if (bg.indexOf('url(') !== -1 && !/gradient\(/i.test(bg)) { _hasMedia = true; break; }
          }
        }
      } catch (e) {}
      const _hasLinks = has(e => e.tag === 'a');
      if (_hasLinks || _hasMedia) {
        // Terse on purpose: this is paid on EVERY observation. The long version
        // measured 200 chars, 4.5% of a median listing; this says the same thing
        // in half that, and the parameter's own schema carries the detail.
        const _what = _hasLinks && _hasMedia ? 'Link URLs and image sources'
                    : _hasLinks ? 'Link URLs' : 'Image/video sources';
        L.push(`  - ${_what} are NOT listed. Need one? re-read with detail="brief" (destination paths — usually enough, and cheaper) or detail="full" (URLs verbatim), ideally with ref_id to scope it.`);
      }
    }
    L.push(`Act on a row by its ref_N: form_input (one field), fill_form (a whole form incl. dropdowns/checkboxes, with optional submit), computer (left_click / hover / scroll_to by ref, or screenshot to look at pixels).`);
    // DATA TABLES, AND THEIR REFS. A <table> is not interactive, so it has no row
    // in the listing and `find` cannot reach it — which meant the columnar table
    // renderer was real and unreachable: verifying it live on the Fed's H.15 page
    // required javascript_tool to look the ref up, which is the exact fallback
    // CLAUDE.md #14 recorded three agents being forced into. A capability the agent
    // cannot discover is not a capability. Same shape as the off-viewport region
    // hint: name the thing and hand over the ref.
    // Unscoped only — inside a scoped read this is a page-level fact (#11).
    if (!scopeMmid) {
      try {
        const _dt = [];
        for (const t of document.querySelectorAll('table')) {
          const rs = t.querySelectorAll('tr').length;
          const cs = t.querySelector('tr') ? t.querySelector('tr').children.length : 0;
          const mm = t.getAttribute('mmid');
          if (rs >= 2 && cs >= 2 && mm) _dt.push(`ref_${mm} (${rs}x${cs})`);
          if (_dt.length >= 6) break;
        }
        if (_dt.length) {
          L.push(`  - ${_dt.length} data table(s), NOT in the rows above: ${_dt.join(', ')}` +
                 ` — read one with read_page(ref_id=…, filter="all") and the cells come back as` +
                 ` aligned columns with their header.`);
        }
      } catch (e) {}
    }
    return L.join('\n') + '\n';
  })();
  return (
    `Current URL: ${url}\n` +
    // Page-level facts are suppressed in a scoped read. An agent that scoped to a
    // single <input> was told the page's Main heading and that "167 more elements
    // are BELOW the current viewport", and reported reading the latter as if those
    // 167 were inside its element.
    ((mainHeading && !scopeMmid) ? `Main heading: ${JSON.stringify(mainHeading)}\n` : '') +
    banner +
    dialogText +
    legend +
    lines.join('\n') +
    truncNote +
    (modalHiddenCount > 0
      ? `\n[${modalHiddenCount} underlying-page element(s) behind the open modal are omitted from this listing — dismiss/close the modal to interact with the page.]`
      : '') +
    virtualNote +
    belowFoldNote +
    sideNote +
    fullScopeNote
  );
}

// Was THIS document ever observed, and was it the same URL the refs came from?
function _refDocCheckPage() {
  try {
    return { observed: window.__mmidObservedUrl || null, now: location.href };
  } catch (e) { return { observed: null, now: '' }; }
}

function _clickPage(selector) {
  // Registry-first resolve so [mmid='N'] targets inside open shadow roots work
  // (document.querySelector can't cross shadow boundaries).
  const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
  const el = q(selector);
  if (!el) return { ok: false, msg: `Element ${selector} not found.` };
  // instant: see _rectForPage. The synthetic pointer sequence below computes
  // clientX/clientY from getBoundingClientRect, so a still-animating (or
  // background-tab-throttled) smooth scroll would aim the events at stale
  // coordinates — and libraries that hit-test the event point would miss.
  try { el.scrollIntoView({ block: "center", inline: "center", behavior: "instant" }); } catch (e) {
    try { el.scrollIntoView({ block: "center", inline: "center" }); } catch (e2) {}
  }
  try { el.focus({ preventScroll: true }); } catch (e) {}
  const cs = getComputedStyle(el);
  if (cs.visibility === 'hidden' || cs.display === 'none') {
    return { ok: false, msg: `Element ${selector} is not visible.` };
  }
  // Full pointer event sequence. Radix DropdownMenu, HeadlessUI Menu, MUI Menu
  // and most modern component libraries register handlers on `pointerdown`
  // (not `click`), so a plain el.click() silently no-ops on the trigger. The
  // sequence pointerdown -> mousedown -> pointerup -> mouseup -> click is what
  // a real mouse produces and is what these libraries gate on. isTrusted will
  // still be false; the (untrusted) auto-escalation path remains the fallback
  // for handlers that ALSO check isTrusted.
  try {
    const r = el.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    const base = { bubbles: true, cancelable: true, composed: true, view: window,
                   clientX: x, clientY: y, screenX: x, screenY: y, button: 0 };
    const ptr  = { ...base, pointerType: 'mouse', pointerId: 1, isPrimary: true };
    el.dispatchEvent(new PointerEvent('pointerover',  ptr));
    el.dispatchEvent(new PointerEvent('pointerenter', ptr));
    el.dispatchEvent(new MouseEvent  ('mouseover',    base));
    el.dispatchEvent(new MouseEvent  ('mouseenter',   base));
    el.dispatchEvent(new PointerEvent('pointerdown',  { ...ptr, buttons: 1 }));
    el.dispatchEvent(new MouseEvent  ('mousedown',    { ...base, buttons: 1 }));
    el.dispatchEvent(new PointerEvent('pointerup',    { ...ptr,  buttons: 0 }));
    el.dispatchEvent(new MouseEvent  ('mouseup',      { ...base, buttons: 0 }));
  } catch (e) {}
  el.click();
  return { ok: true, msg: `Clicked ${selector}.` };
}

function _enterTextPage(selector, text) {
  const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
  let el = q(selector);
  if (!el) return { ok: false, msg: `Element ${selector} not found.` };
  // Code-editor hosts are listed as ONE editor target, but the actual typing
  // surface is internal: CM5/Ace keep a hidden mirror <textarea>; CM6 uses a
  // contenteditable .cm-content; Monaco a .inputarea textarea. Re-target.
  try {
    if (el.matches && el.matches('.CodeMirror, .monaco-editor, .ace_editor, .cm-editor, [class*="mq-editable-field"]')) {
      const inner = el.querySelector('.cm-content[contenteditable], textarea.inputarea, textarea');
      if (inner) el = inner;
    }
  } catch (e) {}
  try { el.focus({ preventScroll: true }); } catch (e) {}
  // Rich-text editors (Lexical/ProseMirror/Quill/Slate/TipTap) keep their own
  // document model: writing textContent directly puts text on screen that the
  // editor's state doesn't know about (lost on next keystroke / not submitted).
  // execCommand('insertText') runs through the real beforeinput->input pipeline
  // those editors listen to, so their model updates like a genuine keystroke.
  if (el.isContentEditable) {
    let ceOk = false;
    try {
      const doc = el.ownerDocument || document;
      const sel = (doc.defaultView || window).getSelection();
      const range = doc.createRange();
      range.selectNodeContents(el);          // select-all -> insert replaces content
      sel.removeAllRanges(); sel.addRange(range);
      ceOk = doc.execCommand('insertText', false, text);
    } catch (e) {}
    if (!ceOk) {                             // editors without execCommand support
      el.textContent = text;
    }
  } else {
    // Clear existing value
    if ('value' in el) {
      const nativeSetter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value')?.set;
      if (nativeSetter) nativeSetter.call(el, '');
      else el.value = '';
    }
    // Type by setting value + dispatching synthetic events (React/Vue friendly)
    if ('value' in el) {
      const nativeSetter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value')?.set;
      if (nativeSetter) nativeSetter.call(el, text);
      else el.value = text;
    }
  }
  el.dispatchEvent(new Event('input',  { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  const actual = ('value' in el) ? el.value : (el.innerText || el.textContent || '');
  return { ok: actual === text || (text && actual.includes(text)),
           actual,
           msg: `Typed into ${selector}.` };
}

function _pressKeysPage(combo) {
  // Combo like "Control+A", "Enter", "Shift+Tab"
  const parts = combo.split('+').map(s => s.trim());
  const key = parts[parts.length - 1];
  const mods = new Set(parts.slice(0, -1).map(s => s.toLowerCase()));
  const opts = {
    key,
    code: key.length === 1 ? `Key${key.toUpperCase()}` : key,
    bubbles: true, cancelable: true,
    ctrlKey:  mods.has('control') || mods.has('ctrl'),
    shiftKey: mods.has('shift'),
    altKey:   mods.has('alt'),
    metaKey:  mods.has('meta') || mods.has('cmd'),
  };
  const target = document.activeElement || document.body;
  target.dispatchEvent(new KeyboardEvent('keydown', opts));
  target.dispatchEvent(new KeyboardEvent('keypress', opts));
  target.dispatchEvent(new KeyboardEvent('keyup', opts));
  return { ok: true, msg: `Dispatched ${combo}.` };
}

function _pageFingerprintPage() {
  return {
    url: location.href,
    textLen: (document.body ? document.body.innerText.length : 0),
    elements: document.querySelectorAll('*').length,
  };
}

// Deep diagnostic: find candidates by label / dump all potentially-interactive
// elements with their viewport rect + each filter's verdict. Lets us see *why*
// the regular interactive listing missed something.
function _deepInspectPage(labels) {
  const vw = window.innerWidth || document.documentElement.clientWidth;
  const vh = window.innerHeight || document.documentElement.clientHeight;

  const filterVerdict = (el) => {
    const tag = el.tagName.toLowerCase();
    const cs = (() => { try { return getComputedStyle(el); } catch (e) { return null; } })();
    const r = el.getBoundingClientRect();
    const isInter =
      ['a','button','input','select','textarea'].includes(tag)
      // KEEP IN SYNC with INTERACTIVE_ROLES in _collectInteractivePage (page-
      // injected functions are serialized independently, so no shared const).
      || (el.getAttribute('role') && ['button','link','menuitem','menuitemcheckbox','menuitemradio','tab','checkbox','radio','switch','option','combobox','searchbox','textbox','slider','spinbutton','treeitem'].includes(el.getAttribute('role')))
      || el.hasAttribute('onclick') || el.hasAttribute('tabindex') || el.isContentEditable
      || (cs && cs.cursor === 'pointer');
    const visible = cs ? (r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity || '1') > 0) : false;
    const inViewport = r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw;
    let clickable = null;
    if (visible && inViewport) {
      try {
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        const topEl = document.elementFromPoint(cx, cy);
        clickable = !!(topEl && (topEl === el || el.contains(topEl) || topEl.contains(el)));
      } catch (e) { clickable = null; }
    }
    return {
      tag, role: el.getAttribute('role'),
      href: el.getAttribute('href'),
      onclick_attr: el.hasAttribute('onclick'),
      tabindex: el.getAttribute('tabindex'),
      cursor: cs ? cs.cursor : null,
      visibility: cs ? cs.visibility : null,
      display: cs ? cs.display : null,
      opacity: cs ? cs.opacity : null,
      text: ((el.innerText || el.textContent || '').trim()).slice(0, 100),
      class: (el.className || '').toString().slice(0, 120),
      mmid: el.getAttribute('mmid'),
      rect: { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) },
      verdict: { isInteractive: !!isInter, visible: !!visible, inViewport: !!inViewport, clickable },
    };
  };

  // 1) find all elements whose direct text matches any keyword exactly OR contains it short-ish.
  const labelLow = (labels || []).map(l => l.toLowerCase());
  const labelMatches = [];
  document.querySelectorAll('*').forEach(el => {
    if (labelMatches.length > 80) return;
    let txt = '';
    try { txt = (el.innerText || '').trim(); } catch (e) { return; }
    if (!txt || txt.length > 120) return;
    const low = txt.toLowerCase();
    if (labelLow.some(kw => low === kw || low.includes(kw))) {
      const v = filterVerdict(el);
      // also walk up to find a clickable ancestor
      let walker = el.parentElement, depth = 0, ancestor = null;
      while (walker && depth < 8) {
        const cs = (() => { try { return getComputedStyle(walker); } catch (e) { return null; } })();
        const tag = walker.tagName.toLowerCase();
        const interactive =
          ['a','button'].includes(tag)
          || (walker.getAttribute && walker.getAttribute('role'))
          || (walker.hasAttribute && walker.hasAttribute('onclick'))
          || (walker.hasAttribute && walker.hasAttribute('tabindex'))
          || (cs && cs.cursor === 'pointer');
        if (interactive) { ancestor = walker; break; }
        walker = walker.parentElement; depth++;
      }
      v.clickAncestor = ancestor ? { ...filterVerdict(ancestor), depth } : null;
      labelMatches.push(v);
    }
  });

  // 2) dump *every* element that COULD be interactive, with verdicts.
  const candSel = "a, button, [role], [onclick], [tabindex], input, select, textarea";
  const cands = Array.from(document.querySelectorAll(candSel)).slice(0, 200);
  const allCandidates = cands.map(filterVerdict);

  // 3) stats
  return {
    viewport: { w: vw, h: vh },
    scroll: { x: window.scrollX, y: window.scrollY },
    counts: {
      total: document.querySelectorAll('*').length,
      mmid: document.querySelectorAll('[mmid]').length,
      a: document.querySelectorAll('a').length,
      button: document.querySelectorAll('button').length,
      role_anything: document.querySelectorAll('[role]').length,
      onclick: document.querySelectorAll('[onclick]').length,
      tabindex: document.querySelectorAll('[tabindex]').length,
    },
    labelMatches,
    allCandidates,
  };
}

// --------------------- file upload (page side) ------------------------------
// Builds File objects from base64, then either sets them on an <input type=file>
// (firing input+change) or dispatches a dragenter/dragover/drop sequence at a
// coordinate / non-input element for drag&drop uploaders.
function _fileUploadPage(selector, coordinate, files) {
  try {
    const mk = (f) => {
      const bin = atob(f.b64);
      const arr = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      return new File([arr], f.name, { type: f.mime });
    };
    const dt = new DataTransfer();
    for (const f of files) dt.items.add(mk(f));
    const names = files.map(f => f.name).join(", ");
    let dropAt = Array.isArray(coordinate) && coordinate.length === 2 ? coordinate : null;
    if (selector) {
      const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
      let el = q(selector);
      if (!el) return { ok: false, msg: `element ${selector} not found` };
      if (!(el.tagName === 'INPUT' && el.type === 'file')) {
        const inner = el.querySelector && el.querySelector('input[type="file"]');
        if (inner) el = inner;
      }
      if (el.tagName === 'INPUT' && el.type === 'file') {
        el.files = dt.files;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return { ok: true, msg: `set ${files.length} file(s) on ${selector}: ${names}` };
      }
      const r = el.getBoundingClientRect();
      dropAt = [r.left + r.width / 2, r.top + r.height / 2];
    }
    if (dropAt) {
      const [x, y] = dropAt;
      const target = document.elementFromPoint(x, y) || document.body;
      for (const type of ['dragenter', 'dragover', 'drop']) {
        const ev = new DragEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y });
        try { Object.defineProperty(ev, 'dataTransfer', { value: dt }); } catch (e) {}
        target.dispatchEvent(ev);
      }
      return { ok: true, msg: `dropped ${files.length} file(s) (${names}) at (${Math.round(x)},${Math.round(y)}) on <${target.tagName.toLowerCase()}>` };
    }
    return { ok: false, msg: "file_upload needs a selector or a coordinate" };
  } catch (e) {
    return { ok: false, msg: String(e && e.message || e) };
  }
}

// Warn when refs are being used against a document that was never observed, or a
// DIFFERENT url than the one they were read from. Advisory rather than a hard refusal:
// plenty of legitimate flows re-use refs after an in-page mutation, and a false refusal
// would be worse than a caveat. fill_form's submit path additionally refuses outright
// when no field resolved, which is the case with real side-effect risk.
// HARD GUARD for mutating ref-based ops: refuse to act on a document the agent has never
// observed. `_ensureMmidsPage` (which fill_form runs internally) makes [mmid='N'] RESOLVE
// on a fresh page, so a stale ref_23 from the previous page silently resolves to whatever
// is 23rd on the new one — and then gets clicked. The advisory note below is right for
// soft cases; acting on a stranger deserves a refusal.
//
// Deliberately tolerant of an inconclusive probe: only refuses when it POSITIVELY
// establishes the document is unstamped. Every observation path (read_page, find — both
// run _collectInteractivePage) stamps, so a legitimate observe-then-act flow never trips
// this; only "act with refs from a page that is no longer loaded" does.
async function assertObservedDocument(tabId, frameId, what) {
  let c = null;
  try { c = await runInTab(tabId, _refDocCheckPage, [], frameId === undefined ? null : frameId); }
  catch (e) { return; }
  if (c && c.observed === null) {
    throw new Error(
      `${what} refused: this document has never been observed, so the ref you passed cannot ` +
      `be trusted. mmids are assigned per document and reset on navigation — a ref from a ` +
      `previous page will resolve to an unrelated element of the same number here, and acting ` +
      `on it can have real side effects (submitting the wrong form, clicking the wrong control). ` +
      `Call read_page or find on this page first, then use the refs it returns.`
    );
  }
}

async function refStalenessNote(tabId, frameId) {
  try {
    const c = await runInTab(tabId, _refDocCheckPage, [], frameId === undefined ? null : frameId);
    if (!c) return "";
    if (!c.observed) {
      return "\nNOTE: this document has not been observed yet (no read_page/find on this page), so any ref you passed came from a different page state. mmids are re-numbered per document, which means a stale ref can resolve to an unrelated element of the same number. Call read_page or find first if anything above looks wrong.";
    }
    if (c.observed !== c.now) {
      return "\nNOTE: the page navigated since it was observed (refs came from " + c.observed + ", now at " + c.now + "). mmids are re-numbered per document, so those refs may point at unrelated elements. Re-observe with read_page before acting further.";
    }
  } catch (e) {}
  return "";
}

// --------------------- op router -------------------------------------------
async function handleOp({ id, op, params }) {
  try {
    let result;
    // PERMISSION GATE — before the broadcast, before the switch, before any tab
    // is touched. It runs FIRST so that a refused op cannot appear in the side
    // panel's activity feed as though something happened: the feed is the user's
    // record of what ChromeBridge did, and a denial is a record of what it did
    // NOT do (the pending-permission prompt is where that surfaces instead).
    // Throwing here lands in the shared catch below and is returned to the agent
    // as an ordinary op error, so a denial fails closed and is never a silent
    // no-op. See assertOpAllowed for the ungated set and the navigate rule.
    await assertOpAllowed(op, params);
    // Broadcast "what the agent is about to touch" to the side panel, except
    // for the silent keepalive ping which would flood the UI.
    if (op !== "ping") {
      try {
        const _t = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
        await broadcastAction(op, _t && _t[0]);
      } catch (e) {}
    }
    switch (op) {
      case "ping":
        result = { pong: Date.now() }; break;
      case "get_active_tab": {
        const t = await resolveTab(params);
        result = { id: t.id, url: t.url, title: t.title, windowId: t.windowId };
        break;
      }
      case "get_url": {
        const t = await resolveTab(params);
        result = { url: t.url, title: t.title }; break;
      }
      case "page_tools": {
        const t = await resolveTab(params);
        result = JSON.stringify(await runInTab(t.id, _pageToolsPage, []));
        break;
      }
      case "call_page_tool": {
        const t = await resolveTab(params);
        result = JSON.stringify(await runInTab(t.id, _callPageToolPage,
          [String(params?.name || ''), params?.args == null ? '{}' :
            (typeof params.args === 'string' ? params.args : JSON.stringify(params.args))]));
        break;
      }
      case "get_dom_text": {
        const t = await resolveTab(params);
        const text = await runInTab(t.id, _domTextPage, [params && params.scopeMmid ? String(params.scopeMmid) : null]);
        // The generic trailer says this read CAN miss loading content; when we can
        // actually SEE that it is happening, say so concretely and up front. This
        // is the case that produced a wrong answer on Baidu, where results were
        // still rendering behind a spinner and the trailer read as reassurance.
        let _rn = "";
        if (typeof text === 'string' && !text.startsWith('__SCOPE_MISS__')) {
          try { _rn = await readinessNote(t.id); } catch (e) {}
        }
        // NOT "complete", and NOT an instruction to stop looking. Two independent
        // live agents were misled by the old trailer: one received code from a
        // CLOSED dropdown (1px-wide <pre> blocks that still pass checkVisibility)
        // presented as "Complete visible text of the current page", the other got a
        // page that was still loading behind a spinner. "if it answers the step,
        // reply now" turns a snapshot into a directive to answer, which is exactly
        // wrong whenever content is still arriving, collapsed, or pixel-only.
        result = _rn + `${text}\n\n[Text snapshot at this moment. It can MISS content that is still loading, inside a closed menu/accordion, rendered as an image, drawn on canvas, generated by CSS (::before/::after content, counter()), or rendered inside a web component's shadow root that this text pass could not reach. If you expected something that is not here, re-read or take a screenshot before concluding the page does not have it.]`;
        break;
      }
      case "get_interactive_elements": {
        const t = await resolveTab(params);
        // scopeMmid narrows the listing to one element's subtree (read_page ref_id).
        const _scopeMmid = params?.scopeMmid != null ? String(params.scopeMmid) : null;
        result = await runInTab(t.id, _collectInteractivePage,
          [!!params?.structured, _scopeMmid, (params?.detail === 'full' || params?.detail === 'brief') ? params.detail : 'compact',
           !!params?.ledger, !!params?.geometry,
           params?.format === 'flat' ? 'flat' : 'tree']);
        // Ledger mode returns an object, not a listing: skip the cross-frame
        // append and the readiness banner, both of which assume a string.
        if (params?.ledger) break;
        // CROSS-ORIGIN IFRAMES (consent CMPs, embedded checkouts): inject the
        // collector per-frame and append their elements with f<frameId>:
        // prefixed mmids — resolveFrameSelector routes the agent's actions.
        if (!params?.structured && typeof result === 'string') {
          try {
            const extra = await collectCrossFrames(t.id, !!params?.geometry);
            // A SCOPED READ MUST NOT IMPORT FRAMES FROM OUTSIDE THE SCOPE. This
            // pass runs AFTER the scope filter and used to append unconditionally,
            // so a read scoped to an <input> in a page header came back carrying a
            // YouTube player, and one scoped to a Reddit post card carried the left
            // rail Google sign-in button — under a header that says, in as many
            // words, "elements outside it are omitted". Two live agents reported it;
            // one noted an agent could act on a sign-in button believing it belonged
            // to the post. An <input> cannot contain an iframe, so appending is
            // never right there.
            // The one case worth keeping is the documented escalation: scoping TO a
            // cross-origin frame shell to read inside it. That listing contains the
            // (cross-origin-iframe) marker, so it is a one-line test.
            if (extra && (!params?.scopeMmid || result.indexOf("(cross-origin-iframe)") !== -1)) {
              result += extra;
            }
          } catch (e) {}
          // Readiness goes FIRST — ahead of the modal banner and the legend —
          // because it qualifies everything after it. Skipped for a __SCOPE_MISS__
          // sentinel, which is an error the server translates, not a listing.
          if (!result.startsWith('__SCOPE_MISS__')) {
            try { result = (await readinessNote(t.id)) + result; } catch (e) {}
            // WEBMCP DISCOVERABILITY. A page that declares its own tools has said
            // what it can do far better than we can infer it, and an agent that is
            // never told will re-derive it from markup instead. One line when
            // there is something to say, nothing at all otherwise — the standing
            // rule from #10's detail legend: never filter silently, but never
            // charge for a notice nobody needs.
            //
            // Probed once per page load and cached, so the extra round trip is
            // paid on the first read of a URL rather than on every observation.
            // On today's web `supported` is false and this is one cache entry.
            try { result = (await webmcpNote(t.id)) + result; } catch (e) {}
          }
        }
        break;
      }
      case "click": {
        const t = await resolveTab(params);
        const urlBefore = t.url || "";
        if (!params || !params.selector) {
          result = `WARNING: click called with no selector (params=${JSON.stringify(params)}).`;
          break;
        }
        await assertObservedDocument(t.id, resolveFrameSelector(params.selector).frameId, "click");
        await highlightInTab(t.id, params.selector, "click");
        // Snapshot a quick page fingerprint (element count + text length) so
        // we can tell whether the click had any DOM effect at all — not just
        // URL navigation. Modals add elements; we want to detect that too.
        const fpBefore = await runInTab(t.id, () => ({
          // dup:deepall — a click that renders into a shadow root moves the light-DOM
          // node count by ZERO, so "click had no detectable effect" fired on clicks
          // that worked. Proven: 6 -> 6 nodes and 0 -> 0 dialogs for a Lit modal.
          n: (function () {
            let c = 0;
            const visit = (r, d) => {
              if (d > 6) return;
              try { const all = r.querySelectorAll('*'); c += all.length;
                    all.forEach((e) => { if (e.shadowRoot) visit(e.shadowRoot, d + 1); }); }
              catch (e) {}
            };
            visit(document, 0);
            return c;
          })(),
          txt: (document.body && document.body.innerText) ? document.body.innerText.length : 0,
        }));

        const doClick = async (trusted) => {
          try {
            const rtc = resolveFrameSelector(params.selector);
            const r = trusted
              ? await clickTrusted(t.id, params.selector)
              : await runInTab(t.id, _clickPage, [rtc.selector], rtc.frameId);
            if (!r || typeof r !== "object" || !("ok" in r)) {
              return { ok: false, msg: `Click returned no result for selector "${params.selector}" (invalid selector or scripting unavailable).` };
            }
            return r;
          } catch (e) {
            return { ok: false, msg: `Click threw: ${e && e.message ? e.message : e}` };
          }
        };

        let r = await doClick(!!params.trusted);
        await new Promise(resolve => setTimeout(resolve, 300));

        // Did anything actually change?
        let urlAfter = urlBefore;
        try { urlAfter = (await chrome.tabs.get(t.id)).url || urlBefore; } catch (e) {}
        // Tolerate a navigating page: if the document is being replaced right now
        // this read throws, and it used to take the whole op down with it — a
        // successful link click reported as "Click threw...". A failed read just
        // means "couldn't measure", so fall back to the before-snapshot; the URL
        // comparison below still detects the navigation.
        const fpRead = async () => {
          try {
            return await runInTab(t.id, () => ({
              // dup:deepall — a click that renders into a shadow root moves the light-DOM
              // node count by ZERO, so "click had no detectable effect" fired on clicks
              // that worked. Proven: 6 -> 6 nodes and 0 -> 0 dialogs for a Lit modal.
              n: (function () {
                let c = 0;
                const visit = (r, d) => {
                  if (d > 6) return;
                  try { const all = r.querySelectorAll('*'); c += all.length;
                        all.forEach((e) => { if (e.shadowRoot) visit(e.shadowRoot, d + 1); }); }
                  catch (e) {}
                };
                visit(document, 0);
                return c;
              })(),
              txt: (document.body && document.body.innerText) ? document.body.innerText.length : 0,
            }));
          } catch (e) { return null; }
        };
        let fpAfter = (await fpRead()) || fpBefore;

        const urlChanged = urlAfter !== urlBefore;
        const elCountChanged = Math.abs((fpAfter.n||0) - (fpBefore.n||0)) >= 2;
        const txtChanged = Math.abs((fpAfter.txt||0) - (fpBefore.txt||0)) > Math.max(20, 0.01 * (fpBefore.txt||0));
        const hadEffect = urlChanged || elCountChanged || txtChanged;

        // Auto-escalate: if an untrusted click had ZERO effect, retry with
        // trusted input. Radix UI / shadcn / Headless UI dialog triggers
        // respond to pointer events, not synthetic click events — el.click()
        // is silently swallowed. Input.dispatchMouseEvent over CDP works.
        let escalated = false;
        let escalateBlocked = "";
        if (r.ok && !hadEffect && !params.trusted) {
          escalated = true;
          try {
            r = await doClick(true);
          } catch (e) {
            // The escalation can be REFUSED outright rather than merely fail to
            // land — Chrome blocks debugger attach on a tab holding another
            // extension's iframe. Reporting only "trusted=true, no effect" sent a
            // reader hunting coordinates for a click that was never dispatched.
            escalated = false;
            const em = String((e && e.message) || e);
            const firstLine = em.split(String.fromCharCode(10))[0];
            escalateBlocked = /Trusted input is unavailable/.test(em)
              ? `\nTrusted retry was REFUSED, not merely ineffective: ${firstLine}`
              : `\nTrusted retry failed to start: ${em.slice(0, 160)}`;
          }
          await new Promise(resolve => setTimeout(resolve, 300));
          try { urlAfter = (await chrome.tabs.get(t.id)).url || urlAfter; } catch (e) {}
          fpAfter = (await fpRead()) || fpAfter;
        }

        const urlChanged2 = urlAfter !== urlBefore;
        const elCountChanged2 = Math.abs((fpAfter.n||0) - (fpBefore.n||0)) >= 2;
        const txtChanged2 = Math.abs((fpAfter.txt||0) - (fpBefore.txt||0)) > Math.max(20, 0.01 * (fpBefore.txt||0));
        const hadEffect2 = urlChanged2 || elCountChanged2 || txtChanged2;

        let nav;
        if (r.ok && urlChanged2) {
          nav = `Navigated: ${urlBefore} -> ${urlAfter}`;
        } else if (r.ok && (elCountChanged2 || txtChanged2)) {
          nav = `URL unchanged but page DOM changed (modal/dropdown likely opened — re-observe with get_dom_fields). elements:${fpBefore.n}->${fpAfter.n}`;
        } else if (r.ok) {
          nav = `WARNING: click had NO detectable effect (URL, DOM, and text are all unchanged). The element may be disabled, hidden behind an overlay, or wired to handlers that don't fire on synthetic events. Already retried with trusted=${escalated ? 'true' : 'false'}.${escalateBlocked}`;
        } else {
          nav = `URL: ${urlAfter}`;
        }
        const esc = escalated ? " [auto-escalated to trusted input]" : "";
        // Put the *outcome line first* — that's the signal the agent needs to
        // decide what to do next. The "Success: clicked X" line is informational.
        result = `${nav}\n` + (r.ok ? `Success: ${r.msg}${esc}` : `WARNING: ${r.msg}${esc}`)
          + ((!r.ok || !hadEffect2) ? await refStalenessNote(t.id, resolveFrameSelector(params.selector).frameId) : "");
        break;
      }
      case "enter_text": {
        const t = await resolveTab(params);
        await assertObservedDocument(t.id, resolveFrameSelector(params.selector).frameId, "enter_text");
        await highlightInTab(t.id, params.selector, "type");
        const rte = resolveFrameSelector(params.selector);
        const r = params?.trusted
          ? await enterTextTrusted(t.id, params.selector, params.text)
          : await runInTab(t.id, _enterTextPage, [rte.selector, params.text], rte.frameId);
        const verify = r.ok
          ? `Verification: field now contains the entered text. [OK]`
          : `WARNING: field value is "${r.actual}" but "${params.text}" was expected.`;
        result = `${r.msg}\n${verify}`;
        break;
      }
      case "debug_targets": {
        // READ-ONLY. chrome.debugger.getTargets() is the only way to see what Chrome
        // thinks a tabId maps to, and who already holds it. NOTE a previous attempt
        // put a getTargets sweep at STARTUP that also DETACHED — being async, it
        // finished after an in-flight op had attached and tore that op's session
        // down. Reading is safe; detaching from here is not. Do not add one.
        const tg = await chrome.debugger.getTargets();
        const want = Number(params && params.tabId);
        const targets = tg
          .filter((t) => !want || t.tabId === want)
          .map((t) => ({ type: t.type, tabId: t.tabId, attached: t.attached,
                         extensionId: t.extensionId, url: String(t.url || "").slice(0, 90) }));
        // Report BOTH views. getTargets() sees other extensions' injected iframes
        // (as type:"other" with no tabId, so they cannot be attributed to a tab);
        // webNavigation.getAllFrames() attributes frames to a tab but does NOT
        // report other extensions' frames at all. Neither alone answers "which
        // extension is blocking THIS tab" — printing both is what makes the gap
        // visible instead of letting an empty list read as "nothing is there".
        let frames = null;
        if (want) {
          try {
            frames = (await chrome.webNavigation.getAllFrames({ tabId: want }) || [])
              .map((f) => ({ frameId: f.frameId, parent: f.parentFrameId,
                             url: String(f.url || "").slice(0, 90) }));
          } catch (e) { frames = `getAllFrames failed: ${e && e.message}`; }
        }
        result = JSON.stringify({ targets, framesForTab: frames });
        break;
      }
      case "sw_info": {
        result = JSON.stringify({ sw: _SW_ID, ageSec: Math.round((Date.now() - _SW_BORN) / 1000),
                                  attached: Array.from(_attachedTabs.keys()),
                                  inputReady: Array.from(_inputReady),
                                  lastDetach: _lastDetach,
                                  // Which half is which, for the version-skew case: the
                                  // extension is hand-installed, so "the server is newer"
                                  // is a live possibility on every op that misbehaves.
                                  bridge: { endpoint: `ws://${_endpoint.host}:${_endpoint.port}`,
                                            configuredPort: _endpoint.configuredPort,
                                            extensionVersion: manifestVersion(),
                                            protocol: PROTOCOL_VERSION,
                                            server: _server } });
        break;
      }
      case "detach_debugger": {
        await detachAllDebuggers();
        result = "Detached debugger from all tabs."; break;
      }
      case "press_keys": {
        const t = await resolveTab(params);
        const r = await runInTab(t.id, _pressKeysPage, [params.combo]);
        result = r.msg; break;
      }
      case "navigate": {
        const t = await resolveTab(params);
        const dest = String(params.url || "");
        if (dest === "back") {
          await chrome.tabs.goBack(t.id);
        } else if (dest === "forward") {
          await chrome.tabs.goForward(t.id);
        } else {
          // Tolerate protocol-less URLs ("example.com") like Claude-in-Chrome.
          // normalizeNavUrl is shared with the permission gate on purpose — the
          // origin that was checked must be the origin that gets opened.
          await chrome.tabs.update(t.id, { url: normalizeNavUrl(dest) });
        }
        // Wait for the target tab to finish loading.
        await new Promise(resolve => {
          // Clear the fallback when the load wins the race. Leaving it armed kept a 15s
          // timer alive after every single navigate — invisible in a service worker that
          // is about to be evicted anyway, but it held a test process open for 15s and it
          // is a leak either way.
          let timer = null;
          const done = () => {
            if (timer !== null) { clearTimeout(timer); timer = null; }
            chrome.tabs.onUpdated.removeListener(lid);
            resolve();
          };
          const lid = (tabId, info) => {
            if (tabId === t.id && info.status === "complete") done();
          };
          chrome.tabs.onUpdated.addListener(lid);
          timer = setTimeout(done, 15000);
        });
        const t2 = await chrome.tabs.get(t.id);
        result = `Navigated to ${t2.url}, title: ${t2.title}`;
        break;
      }
      case "screenshot": {
        const t = await resolveTab(params);
        let dataUrl = null;
        // CDP FIRST. chrome.tabs.captureVisibleTab only ever captures the window's ACTIVE
        // tab and is activeTab-gated — so once agent tabs stopped being created active (so
        // they never steal the user's view), it failed outright with an activeTab error
        // whose suggested remedy ("open a fresh tab") could not possibly help. CDP
        // Page.captureScreenshot targets THIS tab specifically and works while it is in the
        // background, which is the normal condition for this agent.
        // DO NOT CHANGE THE USER'S BROWSER SETTINGS TO TAKE A PICTURE.
        // Page.captureScreenshot resets page zoom in headful Chrome, and nothing
        // put it back. Measured live on openstreetmap.org, where the user had saved
        // 110%: one screenshot took devicePixelRatio 1.1 -> 1.0 and innerWidth 2327
        // -> 2560, the change PERSISTED across navigating away and back, and every
        // box() read before it was then wrong by x1.1 — up to 233px — while both the
        // old and new numbers looked equally plausible. Zoom is per-origin in
        // Chrome's default scope, so this silently overwrote a preference in the
        // user's everyday browser. That is a worse failure than a bad coordinate:
        // an observation tool must not mutate what it observes.
        let _z0 = null;
        try { _z0 = await chrome.tabs.getZoom(t.id); } catch (e) {}
        try {
          await attachDebugger(t.id);
          await ensureInputReady(t.id);   // lifecycle-active: a frozen tab renders stale pixels
          const r = await cdpSend(t.id, "Page.captureScreenshot",
            { format: "png", captureBeyondViewport: false });
          if (r && r.data) dataUrl = "data:image/png;base64," + r.data;
        } catch (e) { /* fall through to the tabs API */ }
        try {
          if (_z0 != null) {
            const _z1 = await chrome.tabs.getZoom(t.id);
            if (Math.abs(_z1 - _z0) > 0.001) await chrome.tabs.setZoom(t.id, _z0);
          }
        } catch (e) {}
        if (!dataUrl) {
          try {
            dataUrl = await chrome.tabs.captureVisibleTab(t.windowId, { format: "png" });
          } catch (e) {
            const msg = String((e && e.message) || e);
            throw new Error(
              "Screenshot failed on both paths. CDP Page.captureScreenshot did not return data " +
              "and chrome.tabs.captureVisibleTab reported: " + msg + ". captureVisibleTab can only " +
              "capture the window's ACTIVE tab, so it cannot serve a background agent tab; the CDP " +
              "path is the one that should work here. If this persists the debugger may be blocked " +
              "(DevTools open on this tab?). Reads (read_page, find, get_page_text) are unaffected."
            );
          }
        }
        let vp = null;
        try { vp = await runInTab(t.id, () => ({ w: innerWidth, h: innerHeight, dpr: devicePixelRatio })); } catch (e) {}
        result = vp && vp.w ? { dataUrl, cssWidth: vp.w, cssHeight: vp.h, dpr: vp.dpr } : dataUrl;
        break;
      }
      case "page_fingerprint": {
        const t = await resolveTab(params);
        result = await runInTab(t.id, _pageFingerprintPage);
        break;
      }
      case "deep_inspect": {
        const t = await resolveTab(params);
        result = await runInTab(t.id, _deepInspectPage, [params?.labels || []]);
        break;
      }
      case "fill_form": {
        // Atomic multi-field fill: one bridge call instead of N. Per-field
        // read-back verification keeps the same accuracy guarantees we have
        // for single-field enter_text.
        const t = await resolveTab(params);
        // SANITIZE: undefined/null in executeScript args throws "Value is
        // unserializable" deep in chrome.scripting. Coerce every field to
        // plain strings and drop entries with no usable selector — the Python
        // tool layer already normalizes/rejects, this is the belt-and-braces.
        const fields = (Array.isArray(params?.fields) ? params.fields : [])
          .map(f => ({
            selector: String((f && (f.selector || (f.mmid != null ? `[mmid='${f.mmid}']` : ''))) || ''),
            text: (f && f.text != null) ? String(f.text) : ((f && f.value != null) ? String(f.value) : ''),
            trusted: !!(f && f.trusted),
          }))
          .filter(f => f.selector);
        let submit_mmid = params?.submit_mmid != null ? String(params.submit_mmid) : null;
        if (submit_mmid && /^\d+$/.test(submit_mmid.trim())) submit_mmid = `[mmid='${submit_mmid.trim()}']`;
        const submit_trusted = !!params?.submit_trusted;
        const out = { fields: [], navigated: false, urlBefore: t.url, urlAfter: t.url };
        const dbg = (m) => { try { console.log("[fill_form]", m); } catch (e) {} };
        dbg(`called with ${fields.length} field(s), submit_mmid=${submit_mmid}, submit_trusted=${submit_trusted}`);
        fields.forEach((f, i) => dbg(`  field[${i}] selector=${f.selector} text=${JSON.stringify(String(f.text||"").slice(0,40))}`));

        // CROSS-FRAME ROUTING: if every field (and the submit) lives in ONE
        // cross-origin frame (a consent form inside a CMP iframe), run the
        // whole flow inside that frame. Mixed-frame calls are rejected with a
        // clear retry hint. ritFF routes every page-script of this op.
        let ffFrame = null;
        {
          const ids = new Set();
          for (const f of fields) {
            const r0 = resolveFrameSelector(f.selector);
            ids.add(r0.frameId);
            f.selector = r0.selector;
          }
          if (submit_mmid) {
            const r0 = resolveFrameSelector(submit_mmid);
            ids.add(r0.frameId);
            submit_mmid = r0.selector;
          }
          const list = [...ids];
          if (list.length === 1) ffFrame = list[0];
          else if (list.some(x => x !== null)) {
            result = "fill_form fields span multiple frames - split into one fill_form call per frame (selectors with the same f<N>: prefix belong together).";
            break;
          }
        }
        const ritFF = (fn, args) => runInTab(t.id, fn, args, ffFrame);

        // ENSURE MMIDS EXIST FIRST. Refs come from a previous observation, but the
        // page may have navigated since (or never been observed at all), in which
        // case NOTHING in this op can resolve [mmid='N']. Two things then failed
        // silently and were only caught by live testing:
        //   1. submit auto-detect returned null (it resolves the field to find its
        //      form/dialog, and reads the chosen button's mmid),
        //   2. the fieldKinds probe reported every field 'missing', so the whole
        //      form fell out of the BATCHED React-safe text write into the
        //      one-field-at-a-time path — which is the exact re-render hazard
        //      fill_form exists to avoid. It still worked here, so nothing looked
        //      wrong; on a React controlled form it would orphan later fields.
        // Injection is additive and idempotent, so this is cheap insurance.
        try { await ritFF(_ensureMmidsPage, []); } catch (e) {}

        // If the caller passed fields but no submit_mmid, try to auto-detect
        // the submit button inside the current modal/form. Models routinely
        // skip submit_mmid for below-fold buttons; we shouldn't need their
        // confidence to find an obvious "Save"/"Submit"/"Add X"/"Create"/etc.
        // SPLIT fields into TEXT and NON-TEXT (combobox, native select, checkbox).
        // Text inputs MUST be batched into a single page-context call because
        // React controlled-input components re-render the whole form on every
        // keystroke — between two separate executeScript calls, React would
        // process its state update and replace all the form DOM nodes, blowing
        // away the mmids the caller passed for subsequent fields. Inside one
        // synchronous script, React batches updates into a single re-render at
        // the end, so all mmids stay valid for the duration of writes.
        const fieldKinds = await ritFF((selectors) => {
          const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
          return selectors.map(sel => {
            const el = q(sel);
            if (!el) return { kind: 'missing' };
            const tag = el.tagName.toLowerCase();
            const role = el.getAttribute('role');
            if (tag === 'select') return { kind: 'native_select' };
            // KEEP IN SYNC with _fieldKindPage's classifier. (input-comboboxes
            // stay 'combobox': fillDropdown's click → type-in-search → pick
            // flow is what commits a selection on autocomplete widgets.)
            const hp = (el.getAttribute('aria-haspopup') || '').toLowerCase();
            const popupTrigger = ['listbox', 'menu', 'true'].includes(hp) && tag !== 'input' && tag !== 'textarea';
            if (role === 'combobox' || role === 'listbox' || role === 'menubutton' || popupTrigger) return { kind: 'combobox' };
            if (role === 'checkbox' || role === 'switch' ||
                (tag === 'input' && (el.type === 'checkbox' || el.type === 'radio'))) return { kind: 'checkbox' };
            return { kind: 'text' };
          });
        }, [fields.map(f => f.selector)]) || fields.map(() => ({ kind: 'text' }));

        // STALE-REF GUARD. __mmidCounter resets on navigation, so hoisting the mmid
        // injection (which fixed the batched-write downgrade) has a sharp edge: a stale
        // ref_23 from the PREVIOUS page now resolves to whatever happens to be 23rd on
        // the new one. Text writes are mostly caught by read-back, but the submit path is
        // not — _detectSubmitPage(randomElement) finds that stranger's real enclosing
        // <form> (site search, newsletter) and the trusted click SUBMITS IT, reported as
        // "submit OK; navigated". Only auto-detect a submit target when the caller's refs
        // demonstrably point at the fields they think they do.
        const _refsResolve = (fieldKinds || []).some(k => k && k.kind && k.kind !== 'missing');
        if (!submit_mmid && fields.length > 0 && !params?.no_submit && _refsResolve) {
          const detected = await ritFF(_detectSubmitPage, [fields.length ? fields[0].selector : null]);
          if (detected && detected.mmid) {
            submit_mmid = `[mmid='${detected.mmid}']`;
            out.submit_auto_detected = { mmid: detected.mmid, label: detected.label };
          } else if (detected && detected.ambiguous && detected.ambiguous.length) {
            // Several buttons DECLARE themselves this form's submit. Choosing between
            // them needs to know which is destructive, and that is a semantic question
            // no structural signal answers — the wordlist that used to answer it was
            // measured wrong in the languages it claimed to cover. Name them instead.
            out.submit_ambiguous = detected.ambiguous;
          }
        }

        // 1) Batched text-input pass — one script, one re-render at the end.
        const textIdx = [];
        fields.forEach((f, i) => { if ((fieldKinds[i] || {}).kind === 'text') textIdx.push(i); });
        let batchResults = {};
        if (textIdx.length) {
          const textJobs = textIdx.map(i => ({ idx: i, selector: fields[i].selector, text: fields[i].text || '' }));
          batchResults = await ritFF((jobs) => {
            const setNative = (el, val) => {
              const desc = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
              if (desc && desc.set) desc.set.call(el, val); else el.value = val;
            };
            const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
            const out = {};
            for (const j of jobs) {
              const el = q(j.selector);
              if (!el) { out[j.idx] = { ok: false, actual: '', msg: `element ${j.selector} not found` }; continue; }
              try {
                el.focus({ preventScroll: true });
                if ('value' in el) {
                  setNative(el, '');
                  el.dispatchEvent(new Event('input', { bubbles: true }));
                  setNative(el, j.text);
                } else if (el.isContentEditable) {
                  // SAME strategy as _enterTextPage (keep in sync): rich-text
                  // editors (Lexical/ProseMirror/Quill) keep their own model —
                  // bare textContent writes are discarded on the next
                  // keystroke. execCommand('insertText') runs the real
                  // beforeinput→input pipeline they listen to.
                  let ceOk = false;
                  try {
                    const doc = el.ownerDocument || document;
                    const sel = (doc.defaultView || window).getSelection();
                    const range = doc.createRange();
                    range.selectNodeContents(el);
                    sel.removeAllRanges(); sel.addRange(range);
                    ceOk = doc.execCommand('insertText', false, j.text);
                  } catch (e) {}
                  if (!ceOk) el.textContent = j.text;
                }
                el.dispatchEvent(new Event('input',  { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                const actual = ('value' in el) ? el.value : (el.innerText || el.textContent || '');
                const ok = String(actual).trim() === String(j.text).trim();
                out[j.idx] = { ok, actual, msg: ok ? `typed ${JSON.stringify(j.text)}` : `read-back mismatch (got ${JSON.stringify(actual)})` };
              } catch (e) {
                out[j.idx] = { ok: false, actual: '', msg: `threw: ${e && e.message || e}` };
              }
            }
            return out;
          }, [textJobs]) || {};
        }

        // 2) Non-text fields one-by-one (comboboxes/native selects/checkboxes
        // have their own async open/pick cycles that can't be batched). Between
        // each, re-inject mmids in case the previous pick triggered a re-render
        // that orphaned subsequent fields.
        for (let i = 0; i < fields.length; i++) {
          const f = fields[i];
          const kind = (fieldKinds[i] || {}).kind;
          if (kind === 'text') {
            const r = batchResults[i] || { ok: false, actual: '', msg: 'no batch result' };
            out.fields.push({ selector: f.selector, text: f.text, ok: r.ok, actual: r.actual, msg: r.msg });
            continue;
          }
          try { await ritFF(_ensureMmidsPage, []); } catch (e) {}
          // Re-prefix for the helpers — they resolve frames internally, and
          // the routing block stripped f.selector to its frame-local form.
          const fSel = ffFrame !== null ? `[mmid='f${ffFrame}:${(/\d+/.exec(f.selector) || [''])[0]}']` : f.selector;
          await highlightInTab(t.id, fSel, "type");
          const r = await fillField(t.id, fSel, f.text || "", !!f.trusted);
          const safeR = (r && typeof r === "object" && "ok" in r)
            ? r : { ok: false, actual: "", msg: `no result for ${f.selector}` };
          // `dbg` = fillDropdown's step trace — persisted by the Python driver,
          // stripped from the model-facing string before the LLM sees it.
          out.fields.push({ selector: f.selector, text: f.text, ok: safeR.ok, actual: safeR.actual, msg: safeR.msg, dbg: safeR.dbg });
        }

        // Same guard for an EXPLICIT submit_mmid: if not a single field landed, the refs
        // are from another page state and clicking anything is a side effect on a page
        // the caller has not actually observed.
        // A PARTIAL FILL MUST NOT SUBMIT. The gate was "any one field landed",
        // so a form that remounts a section when the first field fills (common
        // under synchronously-rendering frameworks) orphaned fields 2..N and the
        // form was submitted with 1 of 3 values — irreversibly, under a success
        // sentence whose only warning was the "1/3" the model had to notice.
        const _allLanded = out.fields.length > 0 && out.fields.every(f => f.ok);
        if (submit_mmid && !_allLanded && out.fields.some(f => f.ok)) {
          const bad = out.fields.filter(f => !f.ok).map(f => f.ref || f.selector).join(', ');
          out.submit = {
            ok: false,
            msg: `submit SKIPPED: only ${out.fields.filter(f => f.ok).length}/${out.fields.length} ` +
                 `field(s) were filled (failed: ${bad}). Submitting a partly-filled form is not ` +
                 `recoverable, so nothing was clicked. Re-observe — the form probably re-rendered ` +
                 `mid-fill — then fill the remaining fields and submit.`,
          };
          submit_mmid = null;
        }
        if (submit_mmid && !out.fields.some(f => f.ok)) {
          out.submit = {
            ok: false,
            msg: "submit SKIPPED: none of the supplied field refs resolved on this page, " +
                 "so the refs are stale (the page probably navigated since you observed it). " +
                 "Nothing was clicked. Re-observe with read_page and retry with fresh refs.",
          };
          submit_mmid = null;
        }
        if (submit_mmid) {
          // RE-RESOLVE the submit target. Its mmid was captured at OBSERVATION
          // time; filling N fields re-renders React forms, and a submit that
          // flips disabled->enabled when the form becomes valid is typically a
          // NEW DOM node WITHOUT the old mmid (observed live: snap() saw
          // btnTxt=null and the "click" hit nothing). If the selector no
          // longer resolves, re-inject mmids and re-detect structurally.
          const _smResolves = await ritFF((sel) => {
            const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
            return !!q(sel);
          }, [submit_mmid]);
          if (!_smResolves) {
            try { await ritFF(_ensureMmidsPage, []); } catch (e) {}
            const re = await ritFF(_detectSubmitPage, [fields.length ? fields[0].selector : null]);
            if (re && re.mmid) {
              dbg(`submit selector ${submit_mmid} orphaned by re-render -> re-resolved to [mmid='${re.mmid}'] ${JSON.stringify(re.label)}`);
              submit_mmid = `[mmid='${re.mmid}']`;
              out.submit_auto_detected = { mmid: re.mmid, label: re.label, reresolved: true };
            }
          }
          await highlightInTab(t.id, submit_mmid, "submit");
          // Submit "success" inside a modal = URL changed OR the modal closed.
          // Loose "DOM count changed" lets validation-error markers count as
          // success, suppressing the trusted-input escalation we need on
          // Radix-style submit buttons.
          const dialogSelector = '[role="dialog"], [role="alertdialog"], [aria-modal="true"], dialog';
          const snap = async () => await ritFF((sel, sm) => {
            let btn = null;
            try {
              const q = (s) => { try { const m = /mmid=['"]?([^'"\]]+)/.exec(s || ''); const r = window.__mmidReg; if (m && r) { const n = r.get(m[1]); if (n && n.isConnected) return n; } } catch (e) {} return document.querySelector(s); };
              btn = q(sm);
            } catch (e) {}
            const _deep = (q) => {
              // dup:deepall — page-context copy; executeScript loses the closure.
              const acc = [];
              const visit = (r, d) => {
                if (d > 6) return;
                try { r.querySelectorAll(q).forEach((e) => acc.push(e)); } catch (e) {}
                try { r.querySelectorAll('*').forEach((e) => { if (e.shadowRoot) visit(e.shadowRoot, d + 1); }); }
                catch (e) {}
              };
              visit(document, 0);
              return acc;
            };
            return {
              url: location.href,
              // Shadow-aware: document.querySelectorAll stops at every shadow
              // boundary, so an <sl-dialog> or a Lit modal never counted and
              // "modal closed" could never fire — a successful submit reported as a
              // validation failure, and a false FAILED gets retried.
              dialogs: _deep(sel).length,
              n: document.querySelectorAll('*').length + _deep('*').length,
              txt: (document.body && document.body.innerText) ? document.body.innerText.length : 0,
              // The submit button's OWN state — label + disabled/busy. An async
              // submit's universal signature is the button mutating in place
              // ("Add Investor" -> "Saving..." + disabled): zero new nodes,
              // modal still open, URL unchanged — invisible to the checks above.
              btnTxt: btn ? (btn.innerText || btn.value || '').trim().slice(0, 80) : null,
              btnBusy: btn ? (btn.disabled === true
                              || btn.getAttribute('aria-disabled') === 'true'
                              || btn.getAttribute('aria-busy') === 'true') : null,
            };
          }, [dialogSelector, submit_mmid]) || { url: "", dialogs: 0, n: 0, txt: 0, btnTxt: null, btnBusy: null };

          const before = await snap();
          const urlBefore = before.url;

          // DEGRADE, don't die. Trusted input can be REFUSED for the whole tab —
          // another extension's injected iframe makes Chrome reject every
          // debugger.attach (see crossExtensionAttachError). Password managers do
          // this on login pages, so the refusal lands on exactly the forms this
          // tool exists to fill. Measured: a fill_form(submit=true) on a real login
          // page threw out of clickTrusted and filled NOTHING, while the untrusted
          // pointer-event path was available and works on most sites. Fall back to
          // it and say so, rather than failing the whole form.
          let submitDegraded = "";
          const doSubmit = async (trusted) => {
            if (!trusted) return await ritFF(_clickPage, [submit_mmid]);
            try {
              return await clickTrusted(t.id, submit_mmid, ffFrame);
            } catch (e) {
              const em = String((e && e.message) || e);
              if (!/Trusted input is unavailable|different extension/i.test(em)) throw e;
              submitDegraded = " (trusted input is blocked on this tab by another " +
                               "extension's injected iframe; used the untrusted " +
                               "pointer-event path instead)";
              return await ritFF(_clickPage, [submit_mmid]);
            }
          };

          const realEffect = (after) =>
            after.url !== before.url                   // navigated
            || (before.dialogs > 0 && after.dialogs < before.dialogs);  // modal closed

          // Async-submit-in-flight: the click DID register and the page is
          // processing (server round-trip, optimistic-UI step, etc.). The
          // button mutating in place is the signal — label changed ("Saving...",
          // "Segmenting...", a spinner swap that unmounts it) or it flipped to
          // disabled/aria-busy. Without this, the old detector reported
          // "NO real effect" and the path re-clicked = double-submit risk.
          const busyEffect = (after) =>
            before.btnTxt !== null && (
              after.btnTxt === null                                  // button unmounted/replaced
              || after.btnTxt !== before.btnTxt                      // label changed in place
              || (after.btnBusy === true && before.btnBusy !== true) // became disabled/busy
            );

          // Modal forms (Radix/HeadlessUI/MUI) frequently ignore synthetic
          // clicks on their submit buttons — handlers gate on isTrusted or
          // pointerdown sequences chrome.scripting.executeScript can't fake.
          // When we know we're inside a dialog, skip the untrusted attempt
          // and go straight to chrome.debugger input. Cheaper than the
          // round-trip + recovery.
          const startTrusted = !!submit_trusted || (before.dialogs > 0);
          dbg(`submit: dialogs=${before.dialogs} startTrusted=${startTrusted}`);
          // Poll for the submit's effect instead of one fixed 400ms snapshot:
          // fast SPAs resolve in ~100ms (don't make them wait), slow server
          // round-trips need 1s+ (a fixed 400ms misread them as "no effect"
          // and triggered a spurious escalation = potential double-submit).
          const settle = async () => {
            const t0 = Date.now();
            let s = await snap();
            let deadline = 1500;
            let sawBusy = false;
            while (!realEffect(s) && Date.now() - t0 < deadline) {
              if (busyEffect(s)) {
                // Async submit detected mid-poll (button went busy) — extend the
                // window so a quick server round-trip resolves to a definitive
                // "modal closed" in THIS call. Bounded at 4s: ops that run longer
                // (Boxsy's segmentation takes 10s+) get the in-flight report
                // anyway, so waiting past this is pure wasted wall-clock.
                if (!sawBusy) { sawBusy = true; deadline = 4000; }
              } else if (sawBusy) {
                // Busy ENDED without navigation/modal-close — the server already
                // responded (validation error or silent failure). Report NOW;
                // the error sweep below will pick up whatever appeared.
                break;
              }
              await new Promise(rsv => setTimeout(rsv, 150));
              s = await snap();
            }
            return s;
          };
          let r = await doSubmit(startTrusted);
          let after = await settle();
          dbg(`submit attempt#1: ok=${r && r.ok} url=${before.url===after.url?'same':'changed'} dialogs=${before.dialogs}->${after.dialogs}`);

          let escalated = false;
          if (r && r.ok && !realEffect(after) && !busyEffect(after) && !startTrusted) {
            // Modal stayed open and URL unchanged — submit didn't actually fire
            // (or was suppressed). Retry with trusted CDP input.
            escalated = true;
            r = await doSubmit(true);
            after = await settle();
            dbg(`submit attempt#2 (escalated): dialogs=${after.dialogs}`);
          }

          const ok = realEffect(after);
          const urlAfter = after.url;
          let msg;
          if (ok && urlAfter !== urlBefore) {
            msg = `submit OK${escalated ? " (auto-escalated to trusted)" : ""}${submitDegraded}; navigated ${urlBefore} -> ${urlAfter}`;
          } else if (ok) {
            msg = `submit OK${escalated ? " (auto-escalated to trusted)" : ""}${submitDegraded}; modal closed (${before.dialogs} -> ${after.dialogs})`;
          } else {
            // Validation likely. Sweep the open dialog (or whole page) for
            // visible error indicators so the agent gets a real diagnosis
            // instead of a generic "modal still open" hint.
            const delta = (after.n || 0) - (before.n || 0);
            const errors = await ritFF((sel) => {
              const scope = document.querySelector(sel) || document;
              const out = [];
              const seen = new Set();
              // ARIA-FIRST (framework-independent): every [aria-invalid="true"]
              // control points at its message via aria-errormessage /
              // aria-describedby — resolve and read those directly. Also read
              // native constraint-validation messages (el.validationMessage).
              try {
                scope.querySelectorAll('[aria-invalid="true"]').forEach(el => {
                  const ref = el.getAttribute('aria-errormessage') || el.getAttribute('aria-describedby');
                  if (ref) ref.split(/\s+/).forEach(id => {
                    const n = (el.getRootNode && el.getRootNode().getElementById)
                      ? el.getRootNode().getElementById(id) : document.getElementById(id);
                    const t = n && (n.innerText || '').trim();
                    if (t && t.length <= 200 && !seen.has(t)) { seen.add(t); out.push(t); }
                  });
                  try {
                    const vm = (el.validationMessage || '').trim();
                    if (vm && !seen.has(vm)) { seen.add(vm); out.push(vm); }
                  } catch (e) {}
                });
              } catch (e) {}
              // CLASS/ROLE sweep: role=alert + live regions are standard; the
              // class list covers the major frameworks' error markup (shadcn/
              // Tailwind, Bootstrap, MUI, Ant, Angular Material, Vuetify) —
              // last-resort hints, not the primary signal.
              const candidates = scope.querySelectorAll(
                '[role="alert"], [aria-live="assertive"], [aria-live="polite"], ' +
                '[aria-invalid="true"], [data-invalid="true"], ' +
                '.error, .invalid, .field-error, .form-error, .text-destructive, ' +
                '.text-red-500, .text-red-600, .text-red-700, [data-state="error"], ' +
                '.invalid-feedback, .is-invalid, .Mui-error, .ant-form-item-explain-error, ' +
                '.mat-error, .error--text, .v-messages__message'
              );
              candidates.forEach(c => {
                const r = c.getBoundingClientRect();
                if (r.width === 0 && r.height === 0) return;
                const cs = getComputedStyle(c);
                if (cs.display === 'none' || cs.visibility === 'hidden') return;
                const t = (c.innerText || c.textContent || '').trim();
                if (!t || t.length > 200) return;
                // Filter false positives: single asterisks, lone digits, and
                // empty-after-strip strings are just required-field markers or
                // counters styled in the "danger" color, not real errors.
                if (/^[\*•\-]+$/.test(t)) return;       // "*", "•", "-"
                if (/^\d{1,4}$/.test(t)) return;             // bare numbers (counters)
                if (seen.has(t)) return;
                seen.add(t);
                out.push(t);
              });
              return out.slice(0, 8);
            }, [dialogSelector]) || [];
            // Visible validation errors are authoritative — report them even if
            // the button also went busy. With NO errors and a busy button, the
            // submit was ACCEPTED and an async operation is still in flight
            // (Boxsy's "Segmenting...", any "Saving..." pattern) — tell the
            // model to wait + re-observe instead of implying it should re-click.
            if (!errors.length && busyEffect(after)) {
              const btnNow = after.btnTxt === null ? "(button unmounted)"
                : `"${after.btnTxt}"${after.btnBusy ? " (disabled)" : ""}`;
              msg = `submit ACCEPTED — async operation in progress: the submit button changed from "${before.btnTxt}" to ${btnNow} after the click. The page is processing (server round-trip); the modal may close on its own. WAIT a few seconds, then re-observe with get_dom_fields. Do NOT click submit again.`;
              out.submit_in_flight = true;
              dbg(`submit in-flight: btn "${before.btnTxt}" -> ${btnNow}`);
            } else {
            const errLine = errors.length
              ? ` Validation errors visible: ${errors.map(e => JSON.stringify(e)).join(" | ")}`
              : ` Could not locate validation messages (they may exist but use markup this scan doesn't recognize) — submit may also be silently disabled or awaiting an async check.`;
            // Also enumerate fields in the dialog that LOOK unfilled (placeholder
            // combobox triggers, empty inputs that are aria-required/required).
            // These are concrete retry targets — the model can fill them and
            // resubmit instead of just bailing.
            // Exclude only fields that actually SUCCEEDED — a field that was
            // attempted but failed (Boxsy's decision-time combobox) must be
            // re-flagged so the retry hint names it.
            const filledSelectors = (out.fields || []).filter(f => f.ok).map(f => f.selector);
            const unfilled = await ritFF((sel, already) => {
              const scope = document.querySelector(sel) || document;
              const rows = [];
              scope.querySelectorAll('input, textarea, select, [role="combobox"], [contenteditable]').forEach(el => {
                const m = el.getAttribute('mmid');
                if (!m) return;
                const selStr = `[mmid='${m}']`;
                if (already.includes(selStr)) return;
                const tag = el.tagName.toLowerCase();
                const role = el.getAttribute('role');
                const isCombo = role === 'combobox' || tag === 'select';
                const r = el.getBoundingClientRect();
                if (r.width === 0 && r.height === 0) return;
                let unsel = false, empty = false;
                const isReq = el.hasAttribute('required') || el.getAttribute('aria-required') === 'true';
                if (tag === 'select') {
                  // Native select: STRUCTURAL emptiness — placeholder option has
                  // empty value. Works in any language.
                  const o = el.options && el.options[el.selectedIndex];
                  if (el.selectedIndex < 0 || !o || !(o.value || '').trim()) unsel = true;
                } else if (isCombo) {
                  // ARIA combobox trigger: structural signals first
                  // ([data-placeholder], empty text), wordlist as supplement.
                  const lab = (el.innerText || el.value || '').trim();
                  // i18n:placeholder — ONE spelling, enforced by tools/test_patterns.py.
                  // This question (is the trigger showing a HINT rather than a choice?) was
                  // asked in four places with four copies of an English-only wordlist.
                  // DESTRUCTIVE drifted exactly that way and ended up rejecting 'Abbrechen'
                  // in one tier while accepting it in another. These functions are injected
                  // into the page and lose their closure, so the duplication is forced —
                  // the test asserts every copy is byte-identical.
                  // LAST RESORT: _showingPlaceholder / data-placeholder / an empty backing
                  // control all run FIRST at every call site. This tier only exists for
                  // hand-rolled widgets that mark placeholder state by grey text alone.
                  // i18n:placeholder — DELETED, on the measurement. This asked "is the
                  // trigger showing a HINT rather than a choice?" with an English-shaped
                  // wordlist (select|choose|pick + ~20 translations). Ablated across 45
                  // frozen sites with an INTERLEAVED drift control on the same page load:
                  // its total effect on (unselected) flags was 14, and the drift floor —
                  // the same source measured twice — was also 14. It changes nothing
                  // beyond noise, because the structural signals already run FIRST and
                  // carry every real case: _showingPlaceholder (the token `placeholder` in
                  // a data-* name/value or class list, covering Radix/Chakra/PrimeVue/Ant/
                  // select2), an empty backing form control, and a trailing ellipsis.
                  // A wordlist that measures as noise is not a fallback, it is a liability:
                  // this same shape shipped an ASCII-only \b that silently killed every
                  // CJK entry, and "Select All Regions" — a genuine choice — was reported
                  // as unselected, sending an agent to re-pick what it had already set.
                  // The residual limitation is unchanged and now honest: a hand-rolled
                  // non-English combobox marking placeholder state by grey text ALONE is
                  // structurally indistinguishable from a chosen value. We no longer
                  // pretend a wordlist closes that gap for the languages it happens to list.
                  let ph = false;
                  try { ph = el.hasAttribute('data-placeholder') || !!el.querySelector('[data-placeholder]'); } catch (e) {}
                  if (ph || !lab || /\.\.\.$|…$/.test(lab)) unsel = true;
                }
                if (tag === 'input' || tag === 'textarea') {
                  if (!el.value && isReq) empty = true;
                } else if (el.isContentEditable && isReq) {
                  if (!(el.textContent || '').trim()) empty = true;
                }
                if (unsel || empty) {
                  const lbl = (el.innerText || el.placeholder || el.getAttribute('aria-label') || '').trim().slice(0, 60);
                  rows.push(`${selStr} ${unsel ? '(unselected)' : '(required-empty)'} "${lbl}"`);
                }
              });
              return rows.slice(0, 12);
            }, [dialogSelector, filledSelectors]) || [];
            const unfilledLine = unfilled.length
              ? ` UNFILLED fields in dialog (retry fill_form including these): ${unfilled.join("; ")}`
              : '';
            msg = `submit had NO real effect${escalated ? " even after trusted retry" : ""}: modal still open, URL unchanged. DOM nodes added=${delta}.${errLine}${unfilledLine}`;
            out.submit_errors = errors;
            out.unfilled = unfilled;
            dbg(`submit failed: ${errors.length} error(s); ${unfilled.length} unfilled field(s) found`);
            }
          }
          out.submit = { ok: ok || !!out.submit_in_flight, msg, urlBefore, urlAfter, escalated, in_flight: !!out.submit_in_flight,
                         dbg: { before, after, startTrusted } };
          out.navigated = urlAfter !== urlBefore;
          out.urlAfter = urlAfter;
          out.modal_closed = before.dialogs > 0 && after.dialogs < before.dialogs;
        }

        // Build a compact human-readable summary first (model-attended).
        const okCount = out.fields.filter(f => f.ok).length;
        const failed = out.fields.filter(f => !f.ok);
        // `out.submit.msg` is already specific and model-attended (built above).
        const submitLine = out.submit
          ? ` Submit: ${out.submit.msg}`
          : (params?.submit === false || params?.no_submit)
            // The caller did not ask to submit. Saying "no submit button was
            // auto-detected" here asserted a search that never ran, on pages whose
            // own listing showed a submit button in the same read.
            ? " (not submitted — you did not ask to)"
            : out.submit_ambiguous
              ? ` (NOT submitted: ${out.submit_ambiguous.length} buttons declare themselves this`
                + ` form's submit — ${out.submit_ambiguous.map(x => JSON.stringify(x)).join(', ')}.`
                + ` Choosing between them would mean guessing which is destructive, so pass`
                + ` submit_ref for the one you mean.)`
              : " (NOT submitted: nothing in the form declares itself the submit button"
                + " — no type=\"submit\" and no implicit submit inside a <form>. Pass"
                + " submit_ref with the button you mean; the listing above names them.)";
        const autoLine = out.submit_auto_detected
          ? ` [submit auto-detected: ${out.submit_auto_detected.label!=='' ? JSON.stringify(out.submit_auto_detected.label) : 'mmid='+out.submit_auto_detected.mmid}]`
          : "";
        const header = `Filled ${okCount}/${out.fields.length} field(s).${submitLine}${autoLine}`;
        const failLines = failed.map(f =>
          `  FAILED ${f.selector}: expected ${JSON.stringify(f.text||"")} got ${JSON.stringify(f.actual||"")} (${f.msg})`
        );
        const _staleNote = (failed.length || (out.submit && !out.submit.ok))
          ? await refStalenessNote(t.id, ffFrame) : "";
        result = [header, ...failLines, "details=" + JSON.stringify(out)].join("\n") + _staleNote;
        break;
      }
      case "batch_actions": {
        // Generic action pipeline. Steps: {op:'click', selector, trusted?},
        // {op:'type', selector, text, trusted?}, {op:'press', combo},
        // {op:'wait', ms}. Sequential, stops on first hard failure.
        const t = await resolveTab(params);
        const steps = Array.isArray(params?.steps) ? params.steps : [];
        const stop_on_fail = params?.stop_on_fail !== false; // default true
        const trace = [];
        const urlBefore = t.url;
        let lastOk = true;
        for (const s of steps) {
          let r, kind = s.op;
          try {
            if (s.op === "click") {
              if (!s.selector) { r = { ok: false, msg: "click missing selector" }; }
              else {
                await highlightInTab(t.id, s.selector, "click");
                r = s.trusted
                  ? await clickTrusted(t.id, s.selector)
                  : await runInTab(t.id, _clickPage, [s.selector]);
              }
            } else if (s.op === "type") {
              if (!s.selector) { r = { ok: false, msg: "type missing selector" }; }
              else {
                await highlightInTab(t.id, s.selector, "type");
                r = s.trusted
                  ? await enterTextTrusted(t.id, s.selector, s.text || "")
                  : await runInTab(t.id, _enterTextPage, [s.selector, s.text || ""]);
              }
            } else if (s.op === "press") {
              r = await runInTab(t.id, _pressKeysPage, [s.combo || ""]);
            } else if (s.op === "wait") {
              await new Promise(rsv => setTimeout(rsv, Math.min(5000, +s.ms || 200)));
              r = { ok: true, msg: `waited ${s.ms || 200}ms` };
            } else {
              r = { ok: false, msg: `unknown op ${s.op}` };
            }
          } catch (e) {
            r = { ok: false, msg: `threw: ${e && e.message ? e.message : e}` };
          }
          if (!r || typeof r !== "object" || !("ok" in r)) {
            r = { ok: false, msg: `no result for ${s.op}` };
          }
          trace.push({ step: s, ok: r.ok, msg: r.msg, actual: r.actual });
          lastOk = r.ok;
          if (!r.ok && stop_on_fail) break;
        }
        await new Promise(rsv => setTimeout(rsv, 300)); // settle for last action
        let urlAfter = urlBefore;
        try { urlAfter = (await chrome.tabs.get(t.id)).url || urlBefore; } catch (e) {}
        const okCount = trace.filter(s => s.ok).length;
        const summary = `Batch: ${okCount}/${steps.length} steps OK${lastOk ? "" : " (stopped on failure)"}` +
                        (urlAfter !== urlBefore ? `. Navigated: ${urlBefore} -> ${urlAfter}.` : "");
        result = summary + "\ntrace=" + JSON.stringify(trace);
        break;
      }
      case "computer": {
        const t = await resolveTab(params);
        result = await computerOp(t, params || {});
        break;
      }
      case "javascript_exec": {
        const t = await resolveTab(params);
        const r = await evalInTab(t.id, params?.code ?? params?.text ?? "");
        if (!r.ok) throw new Error(r.error);
        result = r;
        break;
      }
      case "read_console_messages": {
        const t = await resolveTab(params);
        const r = await runInTab(t.id, (pattern, onlyErrors, limit, clear) => {
          const store = window.__abConsole;
          if (!store) return { available: false, total: 0, messages: [] };
          let out = store.buf.slice();
          if (onlyErrors) out = out.filter(m => m.level === "error");
          if (pattern) {
            try { const re = new RegExp(pattern, "i"); out = out.filter(m => re.test(m.text)); }
            catch (e) { return { available: true, badPattern: String(e.message || e), total: 0, messages: [] }; }
          }
          const total = out.length;
          out = out.slice(-Math.min(Math.max(+limit || 100, 1), 1000));
          if (clear) store.buf.length = 0;
          return { available: true, total, messages: out };
        }, [params?.pattern || "", !!params?.onlyErrors, params?.limit || 100, !!params?.clear]);
        if (!r || !r.available) {
          result = "Console capture not active on this page (it starts at document_start — reload the page once after installing/updating the extension).";
        } else if (r.badPattern) {
          result = `Invalid regex pattern: ${r.badPattern}`;
        } else if (!r.messages.length) {
          result = "No console messages matched.";
        } else {
          const lines = r.messages.map(m => `[${new Date(m.ts).toISOString().slice(11, 23)}] ${m.level.toUpperCase()}: ${m.text}`);
          result = `${r.total} message(s) matched, showing last ${r.messages.length}:\n` + lines.join("\n");
        }
        break;
      }
      case "read_network_requests": {
        const t = await resolveTab(params);
        let arr = (_netBuf.get(t.id) || []).slice();
        const pat = params?.urlPattern ? String(params.urlPattern) : "";
        if (pat) arr = arr.filter(e => e.url && e.url.includes(pat));
        const total = arr.length;
        arr = arr.slice(-Math.min(Math.max(+params?.limit || 100, 1), 1000));
        if (params?.clear) _netBuf.delete(t.id);
        if (!arr.length) {
          result = "No network requests recorded for this tab" + (pat ? ` matching "${pat}"` : "") + ".";
        } else {
          const lines = arr.map(e => e.error
            ? `[${new Date(e.ts).toISOString().slice(11, 23)}] ${e.method} ${e.url} -> ERROR ${e.error} (${e.type})`
            : `[${new Date(e.ts).toISOString().slice(11, 23)}] ${e.method} ${e.url} -> ${e.statusCode}${e.fromCache ? " (cache)" : ""} (${e.type})`);
          result = `${total} request(s), showing last ${arr.length}:\n` + lines.join("\n");
        }
        break;
      }
      case "file_upload": {
        const t = await resolveTab(params);
        const files = (Array.isArray(params?.files) ? params.files : [])
          .map(f => ({
            name: String(f?.name || "file"),
            b64: String(f?.b64 || ""),
            mime: String(f?.mime || "application/octet-stream"),
          }))
          .filter(f => f.b64);
        if (!files.length) throw new Error("file_upload: files (name+b64) required");
        const sel = params?.selector || null;
        const coord = Array.isArray(params?.coordinate) ? params.coordinate.map(Number) : null;
        const rt = sel ? resolveFrameSelector(sel) : { frameId: null, selector: null };
        const r = await runInTab(t.id, _fileUploadPage, [rt.selector, coord, files], rt.frameId);
        if (!r || !r.ok) throw new Error((r && r.msg) || "file upload failed");
        result = `Success: ${r.msg}`;
        break;
      }
      case "fill_field": {
        // Single-field set with full kind routing (text/combobox/native select/
        // checkbox) but NO submit and NO auto-detect — the MCP form_input tool.
        const t = await resolveTab(params);
        if (!params?.selector) throw new Error("fill_field: selector required");
        await assertObservedDocument(t.id, resolveFrameSelector(params.selector).frameId, "form_input");
        await highlightInTab(t.id, params.selector, "type");
        const r = await fillField(t.id, params.selector, params.text != null ? String(params.text) : "", !!params.trusted);
        if (!r || typeof r !== "object") {
          result = `WARNING: fill_field returned no result for ${params.selector}`;
        } else {
          // RE-READ THE FIELD. `r.actual` is what the fill path CHOSE, not what the
          // control ended up holding, and on a combobox those differ: Google Flights
          // reported (value now: "Tokyo, JapanCapital of Japan.Showing 3 nearby
          // locations.") — the option's aria-label — while the field held "Tokyo".
          // A verification field that reports the tool's own intent verifies nothing.
          let _now = null;
          if (r.ok) {
            try {
              const _rt = resolveFrameSelector(params.selector);
              _now = await runInTab(t.id, (sel) => {
                let el = null;
                try { el = document.querySelector(sel); } catch (e) {}
                if (!el) {
                  const m = /\[mmid='([^']+)'\]/.exec(sel);
                  if (m && window.__mmidReg) el = window.__mmidReg.get(m[1]);
                }
                if (!el) return null;
                const tg = (el.tagName || '').toLowerCase();
                const _mk = (v) => (v.length <= 120 ? v
                  : v.slice(0, 120) + '…(+' + (v.length - 120) + ')');
                if (tg === 'select') {
                  // A <select>'s VALUE is a machine code; the caller asked for the
                  // option's TEXT. Reading el.value made the readback compare "Two"
                  // against "2" and declare a landed write failed — three times in one
                  // live audit ("32W / 32L" vs "11,B0G35KJ4BM", "Mug (₹609)" vs an id).
                  // That false alarm is mine, introduced with the readback check; the
                  // check is right, it was reading the wrong field.
                  const _o = el.selectedIndex >= 0 ? el.options[el.selectedIndex] : null;
                  return _mk(_o ? (_o.text || '').trim() : '');
                }
                if (tg === 'input' || tg === 'textarea') {
                  return _mk(String(el.value == null ? '' : el.value));
                }
                // STRIP THE GUTTER, like the listing does. read_page removes an editor's
                // line-number column; this readback did not, so the ONE field whose job
                // is to verify a write reported fabricated leading digits ('1 int foo').
                // Same structural rule: a leading run of consecutive line numbers.
                let _t = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                try {
                  const _w = _t.split(' ');
                  let _n = 0;
                  while (_n < _w.length && _w[_n] === String(_n + 1)) _n++;
                  if (_n >= 1) _t = _w.slice(_n).join(' ');
                } catch (e) {}
                return _mk(_t);
              }, [_rt.selector], _rt.frameId);
            } catch (e) {}
          }
          const _ra = r.actual != null ? String(r.actual) : null;
          const _shown = _now != null ? _now
            : (_ra == null ? null : (_ra.length <= 80 ? _ra
               : _ra.slice(0, 80) + '…(+' + (_ra.length - 80) + ')'));
          // THE VERDICT MUST FOLLOW THE READBACK. Measured on Monaco (godbolt):
          // form_input routed into the editor's READ-ONLY ime-text-area — the IME
          // composition scratch buffer — where the value sticks and reads back, so
          // the write path's own check passed. The tool said "Success" and showed
          // the OLD document in the same sentence, twice in a row. A live agent
          // could not tell that from truncation or lag, and only javascript_tool
          // settled it. If we can see the field and what we asked for is not in
          // it, that is not success, whatever the write path believed.
          let _landed = true, _why = "";
          try {
            const _want = String(params.text == null ? "" : params.text).trim();
            if (r.ok && _want && _shown != null) {
              const _got = String(_shown);
              // Compare on the marked-cut prefix: the readback may be bounded, so a
              // long write can only be checked as far as we can see it.
              const _probe = _want.slice(0, Math.max(0, _got.split("…(+")[0].length));
              if (_probe && _got.indexOf(_probe) === -1) {
                _landed = false;
                _why = ` The field still reads ${JSON.stringify(_got)}, which does not contain what was sent`
                     + ` — the write did not reach this control. Rich editors (Monaco/CodeMirror/Ace) keep a`
                     + ` read-only mirror textarea that accepts text and discards it; use computer`
                     + ` (left_click the editor, key ctrl+a, then type) instead.`;
              }
            }
          } catch (e) {}
          result = (r.ok && _landed
            ? `Success: ${r.msg || `set ${params.selector}`}${_shown != null ? ` (value now: ${JSON.stringify(_shown)})` : ""}`
            : !r.ok
              ? `WARNING: ${r.msg || `could not set ${params.selector}`}`
              : `WARNING: the write reported success but did NOT land.${_why}`)
            + (r.ok && _landed ? "" : await refStalenessNote(t.id, resolveFrameSelector(params.selector).frameId));
        }
        break;
      }
      case "tabs_context": {
        // Find (or, with createIfEmpty, create) the MCP tab group and list its tabs.
        const gid = await _getMcpGroup(!!params?.createIfEmpty);
        if (gid == null) {
          result = { groupId: null, tabIds: [], tabs: [] };
        } else {
          const tabs = await _mcpGroupTabs(gid);
          result = { groupId: gid, tabIds: tabs.map(t => t.id), tabs };
        }
        break;
      }
      case "tabs_create": {
        const gid = await _getMcpGroup(true);
        // _getMcpGroup(true) may have just created a tab along with the group;
        // only add a fresh tab when the group pre-existed.
        const existing = await chrome.tabs.query({ groupId: gid });
        let tab;
        if (existing.length === 1 && existing[0].url === "about:blank" && params?.reuseEmpty !== false) {
          tab = existing[0]; // brand-new group: its seed tab IS the new empty tab
        } else {
          tab = await chrome.tabs.create({ url: "about:blank", active: false });   // never steal the user's view
          await chrome.tabs.group({ tabIds: [tab.id], groupId: gid });
        }
        result = { tabId: tab.id, groupId: gid };
        break;
      }
      case "tabs_close": {
        const id = parseInt(params?.tabId, 10);
        if (!Number.isFinite(id)) throw new Error(`tabs_close: invalid tabId ${params?.tabId}`);
        const gid = await _getMcpGroup(false);
        const tab = await chrome.tabs.get(id).catch(() => null);
        if (!tab) throw new Error(`tab ${id} not found (already closed?)`);
        if (gid == null || tab.groupId !== gid) {
          throw new Error(`tab ${id} is not in the MCP tab group — only group tabs are closable`);
        }
        await chrome.tabs.remove(id);
        result = { closed: id };
        break;
      }
      case "resize_window": {
        const t = await resolveTab(params);
        const width = parseInt(params?.width, 10), height = parseInt(params?.height, 10);
        if (!Number.isFinite(width) || !Number.isFinite(height)) {
          throw new Error("resize_window: width and height (px) are required");
        }
        // Do NOT force state:"normal" — that un-minimizes the user's window. Only resize;
        // if the window is minimized the resize still applies for when they restore it.
        await chrome.windows.update(t.windowId, { width, height });
        const w = await chrome.windows.get(t.windowId);
        result = `Window resized to ${w.width}x${w.height}`;
        break;
      }
      default:
        throw new Error(`unknown op: ${op}`);
    }
    await reply(id, true, result);
  } catch (e) {
    // INCLUDE WHERE IT CAME FROM. A bare chrome.* message like "Cannot access a
    // chrome-extension:// URL of different extension" names no op, no tab and no
    // call site, so neither the agent nor a developer can act on it — I burned
    // three rounds guessing at exactly that. The op name and the first extension
    // stack frames cost a few characters and turn it into something diagnosable.
    let _detail = e && e.message ? e.message : String(e);
    try {
      const frames = String((e && e.stack) || '').split(String.fromCharCode(10))
        .filter(l => l.indexOf('background.js') !== -1)
        .slice(0, 3)
        .map(l => l.trim().replace(/^at\s+/, '').replace(/chrome-extension:\/\/[a-z]+\//, ''))
        .join(' <- ');
      if (frames) _detail += `  [op=${op} ${swAge()} at ${frames}]`;
      else _detail += `  [op=${op} ${swAge()}]`;
    } catch (e2) {}
    await reply(id, false, _detail);
  }
}

// What the GATE would resolve for the tab the user is currently looking at, so
// the side panel can offer a grant BEFORE an op is refused instead of only after.
//
// It answers with an ORIGIN and nothing else — no URL, no title, no path. The
// panel displays and stores an origin, so an origin is all it is given, and the
// string it stores is by construction the string assertOpAllowed matches on: this
// runs the gate's own activeTab() and _gateOrigin(). A second implementation of
// that resolution in panel.js could drift by a trailing slash or a default port
// and silently grant something that never matches anything.
//
// This grants NOTHING. background.js still never writes bridge_permissions; only
// a human click in the panel does (pinned by P21 in tools/test_permissions.js).
async function activeOriginForPanel() {
  let tab = null;
  try { tab = await activeTab(); }
  catch (e) { return { ok: false, reason: "no_tab" }; }
  const g = _gateOrigin(tab && tab.url);
  if (g.closed) {
    return { ok: false, reason: "closed", scheme: g.scheme || "",
             blank: /^about:blank/i.test(String(g.url || "")) };
  }
  if (!g.origin) return { ok: false, reason: "unresolvable" };
  return { ok: true, origin: g.origin };
}

// Allow the side panel to ask for current status without round-tripping the WS.
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.kind === "get_status") {
    sendResponse({ status: lastStatus });
  } else if (msg && msg.kind === "active_origin") {
    activeOriginForPanel()
      .then(sendResponse)
      .catch(() => sendResponse({ ok: false, reason: "unresolvable" }));
  } else if (msg && msg.kind === "reconnect") {
    // The one deliberate human act that clears a protocol halt — the user has
    // presumably just reloaded the extension or restarted the server.
    restartConnection();
    sendResponse({ ok: true });
  } else if (msg && msg.kind === "clear_log") {
    _actionLog = [];
    _actionLogLoaded = true;   // don't let a later load resurrect what we cleared
    _lastAction = null;
    chrome.storage.local
      .set({ bridge_action_log: [], bridge_last_action: null })
      .then(() => sendResponse({ ok: true }))
      .catch(() => sendResponse({ ok: false }));
  }
  return true;
});
