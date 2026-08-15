// ChromeBridge side panel.
//
// Renders what the service worker publishes to chrome.storage.local:
//   bridge_status         { connected, last_error, since }
//   bridge_last_action    { op, tab_title, tab_url, tab_favicon, tab_id, ts }
//   bridge_action_log     [ ...last 40 actions ]
//   bridge_pending_origin { origin, op, ts }  — the most recent refused origin
//   bridge_debugger_block { tabId, url, extensions, ts }
// and OWNS the two keys the gate reads back — bridge_permissions and
// bridge_paused — plus the connection settings (token / host / port).
//
// This panel is the only place a site can be allowed. background.js never writes
// bridge_permissions: a grant must come from a human clicking in extension UI,
// never from anything reachable over the bridge.
//
// Everything user- or page-supplied (tab titles, URLs, ORIGINS, op names, error
// text) goes in via textContent — a page title is attacker-controlled, an origin
// comes from whatever the agent was pointed at, and this document has extension
// privileges.

const $ = (id) => document.getElementById(id);

const FEED_MAX = 14;          // rows rendered; the SW keeps 40
const PENDING_MS = 6000;      // how long "connecting" survives without an answer

// How many ports the extension knocks on, starting at the configured one. KEEP
// IN SYNC with PORT_RANGE_SPAN in extension/background.js and core/bridge/
// server.py — it is only used to describe the search in words, but describing a
// range nobody probes is worse than saying nothing.
const PORT_RANGE_SPAN = 10;

const PERM_KEY = "bridge_permissions";
const PAUSE_KEY = "bridge_paused";
const PENDING_KEY = "bridge_pending_origin";
const DEBUG_BLOCK_KEY = "bridge_debugger_block";

let pendingTimer = null;      // set while we're optimistically "connecting"
let lastStatus = { connected: false, last_error: "", since: 0 };
let lastAction = null;
let actionLog = [];

let perms = { origins: {} };  // mirror of bridge_permissions
let paused = false;           // mirror of bridge_paused
let permReq = null;           // mirror of bridge_pending_origin
let dbgBlock = null;          // mirror of bridge_debugger_block
// The worker's answer for the tab the user is looking at: { ok, origin } or
// { ok:false, reason }. NOT a URL — see refreshPreGrant.
let preGrant = null;

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
  // The close REASON carries the detail for codes that have one. 4001's is both
  // version numbers, and a mismatch message that doesn't say which halves
  // disagree leaves the user guessing which one to update. Take the parenthetical
  // if there is one — the server's reason restates "protocol mismatch", which
  // this sentence has already said.
  const rawWhy = (s.match(/^closed \(\d+:\s*([\s\S]*)\)$/) || [])[1] || "";
  const why = (rawWhy.match(/\(([^()]*)\)\s*$/) || [])[1] || rawWhy;
  if (m) {
    switch (Number(m[1])) {
      case 1006: return "Couldn't reach the bridge. Check that the MCP server is running — " +
        `the extension tries this port and the ${PORT_RANGE_SPAN - 1} above it.`;
      case 1008: return "The bridge rejected this token. Re-copy BRIDGE_TOKEN from the project's .env.";
      case 1002: return "Handshake failed. Reload the extension, then reconnect.";
      case 1000: return "Replaced by a newer connection — another client took over the bridge.";
      case 1011: return "The bridge errored while completing the handshake. Restart the MCP server.";
      // 4001 is ChromeBridge's own code (core/bridge/server.py): the hello frame's
      // protocol number did not match the server's. It is never transient — the
      // same two builds disagree forever — so the extension stops retrying and
      // this sentence has to carry the fix rather than suggest waiting.
      case 4001: return "This extension and mcp_server.py speak different bridge protocol versions" +
        `${why ? ` (${why})` : ""}. Reload ChromeBridge at chrome://extensions — the installed copy ` +
        "is older or newer than the server it's talking to. Retrying won't help.";
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

// "Up 3m 12s" plus which mcp_server.py answered. The server version is the fact
// you want the moment ops start behaving oddly after either half was updated.
function connSubText() {
  const up = lastStatus.since ? `Up ${duration(lastStatus.since)}` : "Linked to the bridge";
  const v = lastStatus.server && lastStatus.server.version;
  return v ? `${up} · bridge ${v}` : up;
}

function renderStatus() {
  const chip = $("status");
  const text = $("status_text");
  const state = $("conn_state");
  const sub = $("conn_sub");
  const alert = $("conn_alert");
  const action = $("conn_action");

  // Every path through here can change which address is the true one.
  renderEndpoint();

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
    sub.textContent = connSubText();
    action.hidden = true;

    // The server takes the first FREE port of its span, so a second Claude Code
    // session legitimately puts the bridge on 8766 while the Port box still reads
    // 8765. Say so: an unexplained mismatch between the two numbers on this card
    // is indistinguishable from a bug.
    const live = Number(lastStatus.port) || 0;
    const want = Number(lastStatus.configured_port) || 0;
    if (live && want && live !== want) {
      alert.hidden = false;
      alert.className = "alert is-note";
      alert.textContent =
        `Connected on port ${live}. Port ${want} was busy — probably another ChromeBridge ` +
        `session — so the bridge moved up the ${want}-${want + PORT_RANGE_SPAN - 1} range and ` +
        `the extension followed it. Nothing to change.`;
    } else {
      alert.hidden = true;
    }
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
    $("conn_sub").textContent = connSubText();
  }
  document.querySelectorAll("#feed .when").forEach((el) => {
    el.textContent = relTime(Number(el.dataset.ts) || 0);
  });
  // Same for the access cards. The site rows are re-stamped in place rather
  // than re-rendered: rebuilding the list every second would drop focus off a
  // Revoke button mid-keyboard-navigation.
  document.querySelectorAll("#sites .site-when").forEach((el) => {
    const ts = Number(el.dataset.ts) || 0;
    el.textContent = ts ? `allowed ${relTime(ts)}` : "allowed";
  });
  if (permReq) renderPermReq();
  if (dbgBlock) renderBlocked();
}

// --------------------------------------------------------------------------
// access — pause switch, allowed sites, pending request, blocked-input notice
// --------------------------------------------------------------------------

// Bridge op names are the vocabulary of the WebSocket protocol, not of a person
// deciding whether to hand a site over. Say what was attempted in plain words;
// anything unmapped falls back to the raw op name (still via textContent).
const OP_PHRASE = {
  get_interactive_elements: "read this page",
  get_dom_text: "read this page's text",
  screenshot: "take a screenshot of this page",
  page_fingerprint: "inspect this page",
  deep_inspect: "inspect this page",
  click: "click something on this page",
  enter_text: "type into this page",
  press_keys: "press keys on this page",
  fill_field: "fill in a field",
  fill_form: "fill in and submit a form",
  batch_actions: "run a sequence of actions",
  computer: "use mouse and keyboard input",
  javascript_exec: "run JavaScript on this page",
  file_upload: "upload a file",
  navigate: "open this site",
  read_console_messages: "read this page's console",
  read_network_requests: "read this page's network activity",
};
const opPhrase = (op) => OP_PHRASE[op] || `run "${op}"`;

// Tolerate a malformed record rather than throwing mid-render: the gate treats
// anything it can't read as "no origins granted", and the panel must show the
// same thing rather than a stale list the gate is not honouring.
function normPerms(v) {
  const o = v && v.origins;
  return { origins: (o && typeof o === "object" && !Array.isArray(o)) ? o : {} };
}

function renderPause() {
  const btn = $("pause_btn");
  btn.setAttribute("aria-checked", paused ? "true" : "false");
  btn.title = btn.ariaLabel = paused ? "Resume ChromeBridge" : "Pause ChromeBridge";
  $("pause_label").textContent = paused ? "Paused" : "Active";
  document.body.classList.toggle("is-paused", paused);
  $("paused_banner").hidden = !paused;
  $("sites_paused").hidden = !paused || !Object.keys(perms.origins).length;
}

function renderPermReq() {
  const card = $("perm_req");
  const origin = permReq && permReq.origin;
  // Once the site is allowed the request is answered — leaving the card up
  // would offer a grant that already exists.
  if (!origin || perms.origins[origin]) { card.hidden = true; return; }
  card.hidden = false;
  $("perm_origin").textContent = origin;
  $("perm_why").textContent =
    `Claude Code tried to ${opPhrase(permReq.op)} ${relTime(permReq.ts)} and was refused. ` +
    `Allowing this site lets it read and act on every page there, with your session, ` +
    `until you revoke it below.`;
}

// Ask the worker what the GATE would resolve for the current tab. The panel does
// not run chrome.tabs.query itself and does not receive a URL: it gets an origin
// or a reason, because an origin is the only thing it displays and the only thing
// it stores. Routing through background.js's activeTab() + _gateOrigin() also
// makes the stored key identical to the matched key by construction — a private
// copy of that resolution here could drift and grant something unmatchable.
async function refreshPreGrant() {
  let res = null;
  try { res = await chrome.runtime.sendMessage({ kind: "active_origin" }); } catch (e) {}
  preGrant = res || { ok: false, reason: "unreachable" };
  renderPreGrant();
}

// Why there is nothing to allow here. The closed-scheme case is Chrome's rule,
// not ours, and is stated as such wherever it surfaces (see assertOpAllowed).
function preGrantWhy(g) {
  if (g.reason === "no_tab") return "No active tab to allow.";
  if (g.reason === "closed") {
    if (g.blank) {
      return "This tab is blank. Point it at the site you want ChromeBridge to work on, " +
             "then allow it here.";
    }
    return `Chrome closes its own pages (${g.scheme || "chrome:"}) to extensions, so no ` +
           "permission can open one — a browser rule, not a ChromeBridge setting. " +
           "Switch to the site you want to allow.";
  }
  if (g.reason === "unreachable") return "Couldn't read the current tab. Reopen this panel.";
  return "This tab has no site to allow. Switch to an http(s) page.";
}

function renderPreGrant() {
  const card = $("pre_grant");
  const row = $("pre_row");
  const why = $("pre_why");
  const btn = $("pre_allow");
  if (!preGrant) { card.hidden = true; return; }

  // The refusal card is already offering Allow for this exact origin. Two
  // buttons granting the same thing is a worse answer than one.
  if (preGrant.ok && permReq && permReq.origin === preGrant.origin
      && !perms.origins[preGrant.origin]) {
    card.hidden = true;
    return;
  }

  card.hidden = false;
  if (!preGrant.ok) {
    // Never offer a button that cannot work. Hiding the row alone would do it
    // visually and in the a11y tree, but leaving the button "shown" inside a
    // hidden parent is the kind of half-state a later refactor gets wrong.
    row.hidden = true;
    btn.hidden = true;
    why.hidden = false;
    why.textContent = preGrantWhy(preGrant);
    return;
  }

  row.hidden = false;
  why.hidden = true;
  const origin = preGrant.origin;
  const granted = !!perms.origins[origin];
  // The origin comes from whatever the user has open — textContent, never HTML.
  $("pre_origin").textContent = origin;
  $("pre_origin").title = origin;
  // When it is already granted this row repeats an entry in the list below it.
  // That repetition is the point: it answers "is the tab I'm on covered?" without
  // making the user scan a list that may hold a dozen origins.
  $("pre_sub").textContent = granted ? "already allowed" : "the tab you're looking at";
  btn.hidden = granted;
  btn.setAttribute("aria-label", `Allow ChromeBridge to act on ${origin}`);
}

function renderSites() {
  const list = $("sites");
  const empty = $("sites_empty");
  const count = $("sites_count");

  const entries = Object.entries(perms.origins)
    .map(([origin, rec]) => ({ origin, granted: Number(rec && rec.granted) || 0 }))
    .sort((a, b) => b.granted - a.granted);

  count.hidden = !entries.length;
  count.textContent = entries.length ? String(entries.length) : "";

  if (!entries.length) { list.hidden = true; empty.hidden = false; return; }
  list.hidden = false;
  empty.hidden = true;
  list.textContent = "";

  for (const e of entries) {
    const li = document.createElement("li");

    const meta = document.createElement("div");
    meta.className = "site-meta";
    const org = document.createElement("div");
    org.className = "site-origin";
    org.textContent = e.origin;      // origin comes from a page — never innerHTML
    org.title = e.origin;
    const when = document.createElement("div");
    when.className = "site-when";
    when.dataset.ts = String(e.granted);
    when.textContent = e.granted ? `allowed ${relTime(e.granted)}` : "allowed";
    meta.append(org, when);

    const btn = document.createElement("button");
    btn.className = "btn-mini btn-danger";
    btn.textContent = "Revoke";
    btn.setAttribute("aria-label", `Revoke access to ${e.origin}`);
    btn.addEventListener("click", () => revokeOrigin(e.origin));

    li.append(meta, btn);
    list.appendChild(li);
  }
}

function renderBlocked() {
  const card = $("dbg_block");
  if (!dbgBlock || !dbgBlock.ts) { card.hidden = true; return; }
  card.hidden = false;
  const who = Array.isArray(dbgBlock.extensions) && dbgBlock.extensions.length
    ? `another extension (${dbgBlock.extensions.join(", ")})`
    : "another extension";
  // Attribute this to Chrome's rule, not to ChromeBridge, and say what still
  // works — otherwise it reads as "the product broke on this site".
  $("dbg_text").textContent =
    `Chrome refused trusted mouse and keyboard input on ${hostOf(dbgBlock.url) || "a page"} ` +
    `${relTime(dbgBlock.ts)}: ${who} has injected a frame into that tab, and Chrome blocks ` +
    `debugger access to any tab containing another extension's frame. Password managers do ` +
    `this on login pages. Reading the page, filling fields and ordinary clicks still work; ` +
    `for trusted input here, turn that extension off for this site.`;
}

function renderAccess() {
  renderPause();
  renderPermReq();
  renderPreGrant();
  renderSites();
  renderBlocked();
}

// A grant only ever originates from a click in this document. background.js
// never writes bridge_permissions, so nothing reachable over the bridge can
// grant itself a site.
async function allowOrigin(origin) {
  if (!origin) return;
  perms.origins[origin] = { granted: Date.now() };
  await chrome.storage.local.set({ [PERM_KEY]: perms });
  await chrome.storage.local.remove(PENDING_KEY);
  permReq = null;
  renderAccess();
}

async function revokeOrigin(origin) {
  delete perms.origins[origin];
  await chrome.storage.local.set({ [PERM_KEY]: perms });
  renderAccess();
}

async function setPaused(next) {
  paused = !!next;
  renderPause();                 // paint first; the write is the slow part
  await chrome.storage.local.set({ [PAUSE_KEY]: paused });
}

// --------------------------------------------------------------------------
// settings
// --------------------------------------------------------------------------

// While a socket is up this shows the address it ACTUALLY reached, which is not
// always the configured one — the server binds the first free port of a span and
// the extension probes for it. Otherwise it previews whatever is in the fields.
// Typing a new port while connected therefore does not move this line; it follows
// the box again the moment Save & Connect drops the socket.
function renderEndpoint() {
  const host = $("host").value.trim() || "127.0.0.1";
  const port = $("port").value.trim() || "8765";
  const live = lastStatus.connected && lastStatus.port;
  $("endpoint").textContent = live
    ? `ws://${lastStatus.host || host}:${lastStatus.port}`
    : `ws://${host}:${port}`;
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
    PERM_KEY, PAUSE_KEY, PENDING_KEY, DEBUG_BLOCK_KEY,
  ]);
  if (saved.bridge_host) $("host").value = saved.bridge_host;
  if (saved.bridge_port) $("port").value = saved.bridge_port;
  if (saved.bridge_token) $("token").value = saved.bridge_token;

  perms = normPerms(saved[PERM_KEY]);
  paused = !!saved[PAUSE_KEY];
  permReq = saved[PENDING_KEY] || null;
  dbgBlock = saved[DEBUG_BLOCK_KEY] || null;
  renderAccess();
  refreshPreGrant();          // async; the card stays hidden until it answers

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

$("pause_btn").addEventListener("click", () => setPaused(!paused));
$("resume_btn").addEventListener("click", () => setPaused(false));

$("perm_allow").addEventListener("click", () => allowOrigin(permReq && permReq.origin));

// Pre-grant. Deliberately the SAME writer as the refusal card's Allow, so every
// grant in the product is produced by one code path, from a click in this
// document — background.js never writes bridge_permissions.
$("pre_allow").addEventListener("click", () => {
  if (preGrant && preGrant.ok) allowOrigin(preGrant.origin);
});

// "The tab you're looking at" changes when the user switches or navigates a tab,
// and the panel is usually open across both. These fire in this document only
// (it is torn down when the panel closes) and carry no URL into the render — they
// only prompt another ask.
chrome.tabs.onActivated.addListener(() => refreshPreGrant());
chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (tab && tab.active && (info.url || info.status === "complete")) refreshPreGrant();
});

// "Not now" answers the request without granting anything. It clears only the
// pending record — the site stays blocked and the next refused op re-raises it.
$("perm_dismiss").addEventListener("click", async () => {
  permReq = null;
  renderAccess();
  try { await chrome.storage.local.remove(PENDING_KEY); } catch (e) {}
});

$("dbg_dismiss").addEventListener("click", async () => {
  dbgBlock = null;
  renderBlocked();
  try { await chrome.storage.local.remove(DEBUG_BLOCK_KEY); } catch (e) {}
});

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
  // The gate writes bridge_pending_origin the moment it refuses an op, and the
  // panel is usually already open when that happens — this is what turns a
  // refusal into a visible prompt without the user reloading anything.
  let access = false;
  if (changes[PERM_KEY]) { perms = normPerms(changes[PERM_KEY].newValue); access = true; }
  if (changes[PAUSE_KEY]) { paused = !!changes[PAUSE_KEY].newValue; access = true; }
  if (changes[PENDING_KEY]) { permReq = changes[PENDING_KEY].newValue || null; access = true; }
  if (changes[DEBUG_BLOCK_KEY]) { dbgBlock = changes[DEBUG_BLOCK_KEY].newValue || null; access = true; }
  if (access) renderAccess();
});
