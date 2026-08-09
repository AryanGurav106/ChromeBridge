// ChromeBridge side panel.
//
// Renders three things the service worker publishes to chrome.storage.local:
//   bridge_status      { connected, last_error, since }
//   bridge_last_action { op, tab_title, tab_url, tab_favicon, tab_id, ts }
//   bridge_action_log  [ ...last 40 actions ]
// and owns the connection settings (token / host / port).
//
// Everything user- or page-supplied (tab titles, URLs, op names, error text)
// goes in via textContent — a page title is attacker-controlled and this
// document has extension privileges.

const $ = (id) => document.getElementById(id);

const FEED_MAX = 14;          // rows rendered; the SW keeps 40
const PENDING_MS = 6000;      // how long "connecting" survives without an answer

let pendingTimer = null;      // set while we're optimistically "connecting"
let lastStatus = { connected: false, last_error: "", since: 0 };
let lastAction = null;
let actionLog = [];

// --------------------------------------------------------------------------
// formatting
// --------------------------------------------------------------------------

function relTime(ts) {
  if (!ts) return "—";
  const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return new Date(ts).toLocaleDateString();
}

function duration(sinceTs) {
  const s = Math.max(0, Math.round((Date.now() - sinceTs) / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${sec}s`;
  return `${sec}s`;
}

function prettyUrl(url) {
  if (!url) return "";
  return url.replace(/^https?:\/\//, "").replace(/\/$/, "");
}

function hostOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch (e) { return prettyUrl(url); }
}

// Turn a raw socket error into something actionable. The codes are the ones
// core/bridge/server.py actually closes with, plus 1006 (no listener at all,
// which is by far the common case: the MCP server simply isn't running).
function humanError(raw) {
  const s = String(raw || "");
  const m = s.match(/closed \((\d+)/);
  if (m) {
    switch (Number(m[1])) {
      case 1006: return "Couldn't reach the bridge. Check that the MCP server is running on this host and port.";
      case 1008: return "The bridge rejected this token. Re-copy BRIDGE_TOKEN from the project's .env.";
      case 1002: return "Handshake failed. Reload the extension, then reconnect.";
      case 1000: return "Replaced by a newer connection — another client took over the bridge.";
      case 1011: return "The bridge errored while completing the handshake. Restart the MCP server.";
    }
  }
  if (/^ws error$/i.test(s)) return "The WebSocket failed before it opened. Is anything listening on this port?";
  return s;
}

// Colour family for an op badge. Prefix matching rather than an exhaustive
// list, so ops added to background.js later still land somewhere sensible.
function opKind(op) {
  const o = String(op || "");
  if (/^(get_|read_|screenshot|page_fingerprint|tabs_context|sw_info|debug_targets|ping)/.test(o)) return "k-read";
  if (/^(click|enter_text|press_keys|fill_|computer|file_upload|upload_)/.test(o)) return "k-act";
  if (/^(navigate|tabs_create|tabs_close|resize_window)/.test(o)) return "k-nav";
  if (/^javascript_/.test(o)) return "k-exec";
  return "";
}

// --------------------------------------------------------------------------
// status
// --------------------------------------------------------------------------

function paintStatus(s) {
  lastStatus = s || { connected: false, last_error: "", since: 0 };
  if (pendingTimer) return;           // a connect attempt is mid-flight; leave it
  renderStatus();
}

function renderStatus() {
  const chip = $("status");
  const text = $("status_text");
  const state = $("conn_state");
  const sub = $("conn_sub");
  const alert = $("conn_alert");
  const action = $("conn_action");

  if (pendingTimer) {
    chip.className = "chip is-wait";
    text.textContent = "connecting";
    state.textContent = "Connecting…";
    sub.textContent = "Waiting for the bridge to answer";
    alert.hidden = true;
    action.hidden = true;
    return;
  }

  if (lastStatus.connected) {
    chip.className = "chip is-ok";
    text.textContent = "live";
    state.textContent = "Connected";
    sub.textContent = lastStatus.since ? `Up ${duration(lastStatus.since)}` : "Linked to the bridge";
    alert.hidden = true;
    action.hidden = true;
    return;
  }

  chip.className = "chip is-bad";
  text.textContent = "offline";
  state.textContent = "Disconnected";

  const noToken = !$("token").value.trim();
  sub.textContent = noToken ? "No token set" : "Not linked to the bridge";

  alert.hidden = false;
  alert.className = noToken ? "alert is-hint" : "alert";
  alert.textContent = "";
  if (noToken) {
    const b = document.createElement("b");
    b.textContent = "Paste your bridge token below. ";
    alert.appendChild(b);
    alert.appendChild(document.createTextNode(
      "It's the BRIDGE_TOKEN value in the project's .env file."));
    $("settings").open = true;
  } else if (lastStatus.last_error) {
    alert.appendChild(document.createTextNode(humanError(lastStatus.last_error)));
  } else {
    alert.appendChild(document.createTextNode(
      "The bridge isn't reachable. Start the MCP server, then reconnect."));
  }
  // Reconnecting without a token can only fail — the token field is the CTA.
  action.hidden = noToken;
}

function beginPending() {
  if (pendingTimer) clearTimeout(pendingTimer);
  pendingTimer = setTimeout(() => { pendingTimer = null; renderStatus(); }, PENDING_MS);
  renderStatus();
}

function endPending() {
  if (!pendingTimer) return;
  clearTimeout(pendingTimer);
  pendingTimer = null;
}

// --------------------------------------------------------------------------
// active tab + feed
// --------------------------------------------------------------------------

function paintFavicon(a) {
  const box = $("favicon");
  box.textContent = "";
  const letter = document.createElement("span");
  letter.textContent = (hostOf(a.tab_url)[0] || "?").toUpperCase();

  if (a.tab_favicon && /^(https?:|data:)/.test(a.tab_favicon)) {
    const img = document.createElement("img");
    img.alt = "";
    img.referrerPolicy = "no-referrer";
    img.onerror = () => { box.textContent = ""; box.appendChild(letter); };
    img.src = a.tab_favicon;
    box.appendChild(img);
  } else {
    box.appendChild(letter);
  }
}

function paintAction(a) {
  lastAction = a || null;
  const empty = $("tab_empty");
  const live = $("tab_live");
  if (!lastAction) { empty.hidden = false; live.hidden = true; return; }

  empty.hidden = true;
  live.hidden = false;
  $("tab_title").textContent = lastAction.tab_title || "(untitled tab)";
  $("tab_url").textContent = prettyUrl(lastAction.tab_url) || "(no url)";
  $("last_op").textContent = lastAction.op || "—";
  $("last_op").className = `op ${opKind(lastAction.op)}`;
  $("last_ts").textContent = relTime(lastAction.ts);
  paintFavicon(lastAction);
}

function paintFeed() {
  const feed = $("feed");
  const empty = $("feed_empty");
  const clear = $("clear_log");

  if (!actionLog.length) {
    feed.hidden = true;
    empty.hidden = false;
    clear.hidden = true;
    return;
  }
  feed.hidden = false;
  empty.hidden = true;
  clear.hidden = false;

  const rows = actionLog.slice(-FEED_MAX).reverse();
  feed.textContent = "";
  rows.forEach((a, i) => {
    const li = document.createElement("li");
    if (i === 0) li.className = "is-latest";

    const op = document.createElement("span");
    op.className = `op ${opKind(a.op)}`;
    op.textContent = a.op || "—";

    // Consecutive ops are nearly always on the same host; repeating it on every
    // row is noise that also ragged-edges the column. Print it only when it
    // changes, which turns the feed into visible per-site groups.
    const host = hostOf(a.tab_url);
    const prev = i > 0 ? hostOf(rows[i - 1].tab_url) : null;
    const where = document.createElement("span");
    where.className = "where";
    where.textContent = host && host !== prev ? host : "";

    const when = document.createElement("span");
    when.className = "when";
    when.dataset.ts = String(a.ts || 0);
    when.textContent = relTime(a.ts);

    li.append(op, where, when);
    feed.appendChild(li);
  });
}

// Re-stamp everything time-derived once a second so "12s ago" and the uptime
// stay honest while the panel sits open.
function tick() {
  if (lastAction) $("last_ts").textContent = relTime(lastAction.ts);
  if (lastStatus.connected && lastStatus.since && !pendingTimer) {
    $("conn_sub").textContent = `Up ${duration(lastStatus.since)}`;
  }
  document.querySelectorAll("#feed .when").forEach((el) => {
    el.textContent = relTime(Number(el.dataset.ts) || 0);
  });
}

// --------------------------------------------------------------------------
// settings
// --------------------------------------------------------------------------

function renderEndpoint() {
  const host = $("host").value.trim() || "127.0.0.1";
  const port = $("port").value.trim() || "8765";
  $("endpoint").textContent = `ws://${host}:${port}`;
}

async function save() {
  const btn = $("save");
  const token = $("token").value.trim();
  const host = $("host").value.trim() || "127.0.0.1";
  const port = parseInt($("port").value || "8765", 10);

  await chrome.storage.local.set({ bridge_token: token, bridge_host: host, bridge_port: port });

  // Writing storage alone is NOT enough to connect: background.js's
  // storage.onChanged handler only closes an existing socket, and with no token
  // there was never a socket nor a scheduled reconnect. Ask for the connect
  // explicitly so a first-time token paste actually links up.
  try { await chrome.runtime.sendMessage({ kind: "reconnect" }); } catch (e) {}

  btn.textContent = "Saved — connecting…";
  btn.disabled = true;
  setTimeout(() => { btn.textContent = "Save & Connect"; btn.disabled = false; }, 1600);
  beginPending();
}

// --------------------------------------------------------------------------
// boot
// --------------------------------------------------------------------------

(async function init() {
  const saved = await chrome.storage.local.get([
    "bridge_host", "bridge_port", "bridge_token",
    "bridge_status", "bridge_last_action", "bridge_action_log",
  ]);
  if (saved.bridge_host) $("host").value = saved.bridge_host;
  if (saved.bridge_port) $("port").value = saved.bridge_port;
  if (saved.bridge_token) $("token").value = saved.bridge_token;

  renderEndpoint();
  actionLog = Array.isArray(saved.bridge_action_log) ? saved.bridge_action_log : [];
  paintFeed();
  paintAction(saved.bridge_last_action);
  paintStatus(saved.bridge_status);

  // Stored status can be stale if the worker was evicted while connected — ask
  // the worker for the truth (this also wakes it, which retries the socket).
  try {
    const res = await chrome.runtime.sendMessage({ kind: "get_status" });
    if (res && res.status) paintStatus(res.status);
  } catch (e) {}

  setInterval(tick, 1000);
})();

// --------------------------------------------------------------------------
// events
// --------------------------------------------------------------------------

$("save").addEventListener("click", save);

$("reconnect").addEventListener("click", async () => {
  try { await chrome.runtime.sendMessage({ kind: "reconnect" }); } catch (e) {}
  beginPending();
});

$("clear_log").addEventListener("click", async () => {
  try { await chrome.runtime.sendMessage({ kind: "clear_log" }); } catch (e) {}
  actionLog = [];
  paintFeed();
  paintAction(null);
});

$("toggle_token").addEventListener("click", () => {
  const input = $("token");
  const btn = $("toggle_token");
  const reveal = input.type === "password";
  input.type = reveal ? "text" : "password";
  btn.classList.toggle("is-revealed", reveal);
  btn.title = btn.ariaLabel = reveal ? "Hide token" : "Show token";
});

$("copy_endpoint").addEventListener("click", async () => {
  const btn = $("copy_endpoint");
  try {
    await navigator.clipboard.writeText($("endpoint").textContent);
    btn.classList.add("is-done");
    setTimeout(() => btn.classList.remove("is-done"), 1400);
  } catch (e) {}
});

["host", "port"].forEach((id) => $(id).addEventListener("input", renderEndpoint));

// Typing a token clears the "No token set" hint the moment it stops being true.
$("token").addEventListener("input", () => { if (!lastStatus.connected) renderStatus(); });

chrome.runtime.onMessage.addListener((msg) => {
  if (!msg) return;
  if (msg.kind === "status") { endPending(); paintStatus(msg.status); }
  if (msg.kind === "action") {
    endPending();
    paintAction(msg.action);
    actionLog.push(msg.action);
    paintFeed();
  }
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes.bridge_status) { endPending(); paintStatus(changes.bridge_status.newValue); }
  if (changes.bridge_last_action) paintAction(changes.bridge_last_action.newValue);
  if (changes.bridge_action_log) {
    actionLog = Array.isArray(changes.bridge_action_log.newValue)
      ? changes.bridge_action_log.newValue : [];
    paintFeed();
  }
});
