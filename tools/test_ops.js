// test_ops.js — Node-based test harness for extension/background.js's op router.
//
// Run:  node tools/test_ops.js        (exits non-zero on failure)
//
// WHAT THIS COVERS (and the Playwright suites do not): handleOp — the service
// worker's op router — and every chrome.*-dependent orchestration decision in
// it: fill_form's ensure-mmids-then-probe-then-detect ordering, the batched
// React-safe text write, the stale-ref submit guard, submit escalation,
// frameOffsetNow's shell re-matching, ensureTabVisibleForInput ordering,
// batch_actions stop-on-fail, MCP tab-group policy, network buffers.
//
// APPROACH: background.js is loaded verbatim into a `node:vm` context with a
// mocked `chrome` object and a mocked `WebSocket`. handleOp is invoked
// DIRECTLY (function declarations land on the vm's global object), and replies
// are captured through the mocked WebSocket's send() — reply() writes there
// once ws.readyState === WebSocket.OPEN. Module-level `let`/`const` state
// (ws, _frameShells, _attachedTabs, _mcpGroupId, _netBuf) is reached via an
// exporter snippet run in the same context (scripts share the global lexical
// environment).
//
// Page-side functions (executed in real life via chrome.scripting.executeScript)
// are NOT run against a DOM here — the mock dispatches on the function's name
// (or, for inline anonymous functions, a source-signature classification) to
// per-test stubs. We are testing the ROUTER's orchestration, not the DOM logic;
// the DOM logic is covered by tools/test_gaps.py / test_shadow.py / test_widgets.py.
//
// RULE honored: no product files modified; no dependencies beyond Node built-ins.

"use strict";

const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");

const BACKGROUND = path.join(__dirname, "..", "extension", "background.js");
const DEBUG = !!process.env.TEST_OPS_DEBUG;

// ---------------------------------------------------------------------------
// check/reporting plumbing
// ---------------------------------------------------------------------------
let passCount = 0, failCount = 0;
const failures = [];
function check(name, cond, detail) {
  if (cond) { passCount++; console.log(`PASS ${name}`); }
  else {
    failCount++; failures.push(name);
    console.log(`FAIL ${name}${detail ? ` — ${String(detail).slice(0, 400)}` : ""}`);
  }
}
async function test(name, fn) {
  try { await fn(); }
  catch (e) {
    check(`${name}: test body threw`, false,
      String((e && e.stack) || e).split("\n").slice(0, 4).join(" | "));
  }
}

// ---------------------------------------------------------------------------
// Shared mutable mock state (reset per test)
// ---------------------------------------------------------------------------
const state = {
  tabs: [],            // {id,url,title,windowId,active,groupId}
  windows: {},         // id -> {focused,width,height}
  groups: new Set(),   // existing tabGroup ids
  storage: {},         // chrome.storage.local backing store
  frames: {},          // tabId -> getAllFrames() result
  nextTabId: 500,
  nextGroupId: 700,
};
const callLog = [];            // ordered record of every chrome.* side effect
let currentStubs = {};         // page-func name -> stub (value or fn(...args))

function log(entry) { entry.n = callLog.length; callLog.push(entry); return entry; }
const allOf = (pred) => callLog.filter(pred);
const idxOf = (pred) => callLog.findIndex(pred);
const execCalls = (name) => allOf((e) => e.kind === "exec" && e.name === name);
const cdpCalls = (method) => allOf((e) => e.kind === "cdp" && e.method === method);
function setStubs(stubs) { currentStubs = stubs; }

// Event listener registries (populated once at load; invoked manually by tests)
const listeners = {
  tabsUpdated: new Set(), tabsRemoved: new Set(),
  netCompleted: [], netError: [], navCommitted: [],
};
function emitTabsUpdated(tabId, info) {
  for (const fn of [...listeners.tabsUpdated]) { try { fn(tabId, info); } catch (e) {} }
}
function emitTabsRemoved(tabId) {
  for (const fn of [...listeners.tabsRemoved]) { try { fn(tabId); } catch (e) {} }
}

// ---------------------------------------------------------------------------
// Inline (anonymous) page-function classification by source signature.
// Named page functions dispatch by fn.name; the router also inlines several
// anonymous arrow functions into executeScript — recognize them by content.
// ---------------------------------------------------------------------------
function classifyFunc(fn) {
  if (fn && fn.name) return fn.name;
  const src = String(fn);
  if (src.includes("native_select")) return "inline:fieldKindsProbe";   // fill_form kind probe
  if (src.includes("setNative")) return "inline:batchTextWrite";        // fill_form batched writer
  if (src.includes("return !!q(sel)")) return "inline:submitResolves";  // fill_form submit re-resolve check
  if (src.includes("btnTxt")) return "inline:submitSnap";               // fill_form submit snapshot
  if (src.includes("aria-invalid")) return "inline:errorSweep";         // fill_form validation sweep
  if (src.includes("required-empty")) return "inline:unfilledSweep";    // fill_form unfilled enumeration
  if (src.includes("__abConsole")) return "inline:consoleRead";         // read_console_messages
  if (src.includes("querySelectorAll('*')")) return "inline:fingerprint"; // click-op page fingerprint
  if (src.includes("innerWidth")) return "inline:viewport";
  if (src.includes("focus")) return "inline:focusTarget";
  return "inline:unknown";
}

// ---------------------------------------------------------------------------
// chrome.* mock
// ---------------------------------------------------------------------------
function scheduleComplete(tabId) {
  setTimeout(() => emitTabsUpdated(tabId, { status: "complete" }), 10);
}

const chromeMock = {
  sidePanel: { setPanelBehavior: () => Promise.resolve() },
  action: {
    setBadgeText: async () => {},
    setBadgeBackgroundColor: async () => {},
  },
  storage: {
    local: {
      get: async (keys) => {
        const ks = typeof keys === "string" ? [keys] : Array.isArray(keys) ? keys : Object.keys(keys || {});
        const out = {};
        for (const k of ks) if (k in state.storage) out[k] = state.storage[k];
        return out;
      },
      set: async (obj) => { Object.assign(state.storage, obj); },
    },
    onChanged: { addListener: () => {} },
  },
  runtime: {
    sendMessage: () => undefined,
    onInstalled: { addListener: () => {} },
    onStartup: { addListener: () => {} },
    onMessage: { addListener: () => {} },
  },
  tabs: {
    query: async (q) => {
      if (q && q.groupId !== undefined) return state.tabs.filter((t) => t.groupId === q.groupId);
      if (q && q.active) return state.tabs.filter((t) => t.active);
      return state.tabs.slice();
    },
    get: async (id) => {
      const t = state.tabs.find((t) => t.id === id);
      if (!t) throw new Error(`No tab with id: ${id}.`);
      return t;
    },
    update: async (id, props) => {
      const t = state.tabs.find((t) => t.id === id);
      if (!t) throw new Error(`No tab with id: ${id}.`);
      log({ kind: "tabs.update", id, props: { ...props } });
      if (props.active) state.tabs.forEach((x) => { x.active = x.id === id; });
      if (props.url) { t.url = props.url; t.title = "loaded:" + props.url; scheduleComplete(id); }
      return t;
    },
    create: async (props) => {
      const t = {
        id: state.nextTabId++, url: props.url || "about:blank",
        title: "", windowId: 10, active: !!props.active, groupId: -1,
      };
      if (t.active) state.tabs.forEach((x) => { x.active = false; });
      state.tabs.push(t);
      log({ kind: "tabs.create", id: t.id, url: t.url, props });
      return t;
    },
    remove: async (id) => {
      log({ kind: "tabs.remove", id });
      const i = state.tabs.findIndex((t) => t.id === id);
      if (i >= 0) state.tabs.splice(i, 1);
      emitTabsRemoved(id);
    },
    group: async ({ tabIds, groupId }) => {
      const gid = groupId != null ? groupId : state.nextGroupId++;
      state.groups.add(gid);
      for (const id of tabIds) {
        const t = state.tabs.find((t) => t.id === id);
        if (t) t.groupId = gid;
      }
      log({ kind: "tabs.group", tabIds: tabIds.slice(), gid });
      return gid;
    },
    goBack: async (id) => { log({ kind: "tabs.goBack", id }); scheduleComplete(id); },
    goForward: async (id) => { log({ kind: "tabs.goForward", id }); scheduleComplete(id); },
    captureVisibleTab: async () => "data:image/png;base64,TESTPNG",
    onUpdated: {
      addListener: (fn) => listeners.tabsUpdated.add(fn),
      removeListener: (fn) => listeners.tabsUpdated.delete(fn),
    },
    onRemoved: {
      addListener: (fn) => listeners.tabsRemoved.add(fn),
      removeListener: (fn) => listeners.tabsRemoved.delete(fn),
    },
  },
  tabGroups: {
    get: async (gid) => {
      if (!state.groups.has(gid)) throw new Error(`No group with id: ${gid}.`);
      return { id: gid };
    },
    update: async (gid, props) => { log({ kind: "tabGroups.update", gid, props: { ...props } }); },
  },
  windows: {
    get: async (id) => {
      const w = state.windows[id] || { focused: true, width: 1280, height: 800 };
      return { id, focused: w.focused, width: w.width || 1280, height: w.height || 800 };
    },
    update: async (id, props) => {
      log({ kind: "windows.update", id, props: { ...props } });
      const w = state.windows[id] || (state.windows[id] = { focused: true });
      if (props.focused) w.focused = true;
      if (props.width) w.width = props.width;
      if (props.height) w.height = props.height;
      return { id, ...w };
    },
  },
  debugger: {
    attach: async ({ tabId }) => { log({ kind: "cdp.attach", tabId }); },
    detach: async ({ tabId }) => { log({ kind: "cdp.detach", tabId }); },
    sendCommand: async (target, method, params) => {
      log({ kind: "cdp", tabId: target.tabId, method, params: params ? JSON.parse(JSON.stringify(params)) : params });
      return {};
    },
    onDetach: { addListener: () => {} },
  },
  scripting: {
    executeScript: async (spec) => {
      const name = classifyFunc(spec.func);
      // Record BEFORE stub lookup so ordering assertions hold even when the
      // caller swallows a missing-stub error (e.g. the best-effort ensureMmids).
      log({
        kind: "exec", name,
        args: spec.args ? JSON.parse(JSON.stringify(spec.args)) : [],
        target: spec.target ? JSON.parse(JSON.stringify(spec.target)) : {},
      });
      const stub = currentStubs[name];
      if (stub === undefined) {
        throw new Error(`TEST-MOCK: no page stub registered for "${name}" ` +
          `(source head: ${String(spec.func).slice(0, 100)})`);
      }
      let result = typeof stub === "function" ? stub(...(spec.args || [])) : stub;
      if (result && typeof result.then === "function") result = await result;
      return [{ result }];
    },
  },
  webRequest: {
    onCompleted: { addListener: (fn) => listeners.netCompleted.push(fn) },
    onErrorOccurred: { addListener: (fn) => listeners.netError.push(fn) },
  },
  webNavigation: {
    onCommitted: { addListener: (fn) => listeners.navCommitted.push(fn) },
    getAllFrames: async ({ tabId }) => state.frames[tabId] || [],
  },
};

// ---------------------------------------------------------------------------
// WebSocket mock — reply() writes here once readyState === WebSocket.OPEN.
// ---------------------------------------------------------------------------
class MockWebSocket {
  constructor(url) { this.url = url; this.readyState = MockWebSocket.CONNECTING; this.sent = []; }
  send(s) { this.sent.push(s); }
  close() { this.readyState = MockWebSocket.CLOSED; }
}
MockWebSocket.CONNECTING = 0;
MockWebSocket.OPEN = 1;
MockWebSocket.CLOSING = 2;
MockWebSocket.CLOSED = 3;

// ---------------------------------------------------------------------------
// Load background.js into the vm context
// ---------------------------------------------------------------------------
const silentConsole = DEBUG ? console : { log() {}, warn() {}, error() {}, info() {}, debug() {} };
const sandbox = {
  chrome: chromeMock,
  WebSocket: MockWebSocket,
  setTimeout, clearTimeout, setInterval, clearInterval,
  console: silentConsole,
  URL,
};
vm.createContext(sandbox);
const code = fs.readFileSync(BACKGROUND, "utf8");
vm.runInContext(code, sandbox, { filename: "background.js" });

// Reach module-level let/const state (scripts share the global lexical scope).
vm.runInContext(`
  globalThis.__priv = {
    setWs: (w) => { ws = w; },
    getWs: () => ws,
    frameShells: _frameShells,
    attachedTabs: _attachedTabs,
    netBuf: _netBuf,
    netOrigin: _netOrigin,
    setMcpGroup: (v) => { _mcpGroupId = v; },
  };
`, sandbox, { filename: "test_ops_exporter.js" });
const priv = sandbox.__priv;

// Install a connected mock socket so reply() delivers.
const wsMock = new MockWebSocket("ws://test");
wsMock.readyState = MockWebSocket.OPEN;
priv.setWs(wsMock);

let opSeq = 0;
async function callOp(op, params) {
  const before = wsMock.sent.length;
  await sandbox.handleOp({ id: `t${++opSeq}`, op, params });
  const raw = wsMock.sent.slice(before);
  if (!raw.length) return null;
  return JSON.parse(raw[raw.length - 1]);
}

function resetState() {
  callLog.length = 0;
  currentStubs = {};
  state.tabs = [{ id: 1, url: "https://app.example/form", title: "Form", windowId: 10, active: true, groupId: -1 }];
  state.windows = { 10: { focused: true, width: 1280, height: 800 } };
  state.groups = new Set();
  state.storage = {};
  state.frames = {};
  state.nextTabId = 500;
  state.nextGroupId = 700;
  priv.attachedTabs.clear();
  priv.frameShells.clear();
  priv.netBuf.clear();
  priv.netOrigin.clear();
  priv.setMcpGroup(null);
  wsMock.sent.length = 0;
}

const FIELDS3 = () => ([
  { selector: "[mmid='11']", text: "Alice" },
  { selector: "[mmid='12']", text: "alice@example.com" },
  { selector: "[mmid='13']", text: "Investor" },
]);

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
(async () => {

  // Give the top-level connect() (no token -> early return) a tick to settle.
  await new Promise((r) => setImmediate(r));

  await test("ping", async () => {
    resetState();
    const r = await callOp("ping", {});
    check("ping: pong reply over mocked ws", r && r.ok === true && r.result && typeof r.result.pong === "number", JSON.stringify(r));
  });

  await test("resolveFrameSelector", async () => {
    const a = sandbox.resolveFrameSelector("[mmid='f12:34']");
    check("resolveFrameSelector: cross-frame ref split into frameId + local selector",
      a.frameId === 12 && a.selector === "[mmid='34']", JSON.stringify(a));
    const b = sandbox.resolveFrameSelector("[mmid='7']");
    check("resolveFrameSelector: plain ref passes through with frameId=null",
      b.frameId === null && b.selector === "[mmid='7']", JSON.stringify(b));
  });

  // ---- 1+2: fill_form happy path (also the fieldKinds-TDZ crash regression guard)
  await test("fill_form happy path", async () => {
    resetState();
    let snapI = 0;
    const snaps = [
      { url: "https://app.example/form", dialogs: 0, n: 100, txt: 1000, btnTxt: "Save", btnBusy: false },
      { url: "https://app.example/done", dialogs: 0, n: 80, txt: 900, btnTxt: null, btnBusy: null },
    ];
    setStubs({
      _ensureMmidsPage: () => true,
      "inline:fieldKindsProbe": (sels) => sels.map((s) => (s === "[mmid='13']" ? { kind: "native_select" } : { kind: "text" })),
      _detectSubmitPage: () => ({ mmid: "99", label: "Save" }),
      "inline:batchTextWrite": (jobs) => Object.fromEntries(jobs.map((j) => [j.idx, { ok: true, actual: j.text, msg: `typed ${JSON.stringify(j.text)}` }])),
      _highlightPage: () => true,
      _fieldKindPage: () => ({ tag: "select", role: null, is_native_select: true, is_combobox: false, is_checkbox_button: false }),
      _selectNativePage: () => ({ ok: true, actual: "Investor", msg: 'selected "Investor"' }),
      "inline:submitResolves": () => true,
      "inline:submitSnap": () => snaps[Math.min(snapI++, 1)],
      _clickPage: (sel) => ({ ok: true, msg: `clicked ${sel}` }),
      _refDocCheckPage: () => null,
    });
    const reply = await callOp("fill_form", { tabId: 1, fields: FIELDS3() });
    check("fill_form happy: op completed ok (fieldKinds TDZ crash regression guard)",
      reply && reply.ok === true && !/ReferenceError|before initialization/.test(JSON.stringify(reply)),
      JSON.stringify(reply).slice(0, 300));
    const res = String((reply && reply.result) || "");
    check("fill_form happy: reports Filled 3/3", res.startsWith("Filled 3/3"), res.split("\n")[0]);

    const iEnsure = idxOf((e) => e.kind === "exec" && e.name === "_ensureMmidsPage");
    const iProbe = idxOf((e) => e.kind === "exec" && e.name === "inline:fieldKindsProbe");
    const iDetect = idxOf((e) => e.kind === "exec" && e.name === "_detectSubmitPage");
    const iBatch = idxOf((e) => e.kind === "exec" && e.name === "inline:batchTextWrite");
    check("fill_form happy: _ensureMmidsPage runs BEFORE the fieldKinds probe",
      iEnsure !== -1 && iProbe !== -1 && iEnsure < iProbe, `ensure@${iEnsure} probe@${iProbe}`);
    check("fill_form happy: _ensureMmidsPage runs BEFORE submit auto-detect",
      iEnsure !== -1 && iDetect !== -1 && iEnsure < iDetect, `ensure@${iEnsure} detect@${iDetect}`);
    check("fill_form happy: kind probe runs BEFORE the batched write",
      iProbe !== -1 && iBatch !== -1 && iProbe < iBatch, `probe@${iProbe} batch@${iBatch}`);

    const batches = execCalls("inline:batchTextWrite");
    check("fill_form happy: ONE batched executeScript carries BOTH text jobs",
      batches.length === 1 && batches[0].args[0].length === 2 &&
      batches[0].args[0].map((j) => j.selector).join(",") === "[mmid='11'],[mmid='12']",
      JSON.stringify(batches.map((b) => b.args)));
    check("fill_form happy: per-field _enterTextPage NEVER used for text fields",
      execCalls("_enterTextPage").length === 0);

    const det = execCalls("_detectSubmitPage")[0];
    check("fill_form happy: _detectSubmitPage called with the FIRST field's selector",
      det && det.args[0] === "[mmid='11']", det && JSON.stringify(det.args));
    check("fill_form happy: native select routed through _selectNativePage",
      execCalls("_selectNativePage").length === 1);
    check("fill_form happy: auto-detected submit label surfaced in result",
      res.includes("submit auto-detected") && res.includes("Save"), res.split("\n")[0]);

    const clicks = execCalls("_clickPage");
    check("fill_form happy: submit clicked via the auto-detected selector",
      clicks.length === 1 && clicks[0].args[0] === "[mmid='99']", JSON.stringify(clicks.map((c) => c.args)));
    check("fill_form happy: reports submit OK; navigated",
      res.includes("submit OK") && res.includes("-> https://app.example/done"));
    check("fill_form happy: untrusted submit outside a dialog (zero CDP mouse events)",
      cdpCalls("Input.dispatchMouseEvent").length === 0);
  });

  await test("fill_form zero fields", async () => {
    resetState();
    setStubs({
      _ensureMmidsPage: () => true,
      "inline:fieldKindsProbe": (sels) => sels.map(() => ({ kind: "text" })),
    });
    const r = await callOp("fill_form", { tabId: 1, fields: [] });
    check("fill_form: zero-field call completes without crashing",
      r && r.ok === true && String(r.result).startsWith("Filled 0/0"), JSON.stringify(r).slice(0, 200));
  });

  // ---- 3: silent-downgrade / stale-ref guard
  await test("fill_form stale refs", async () => {
    resetState();
    setStubs({
      _ensureMmidsPage: () => true,
      "inline:fieldKindsProbe": (sels) => sels.map(() => ({ kind: "missing" })),
      _highlightPage: () => true,
      _fieldKindPage: () => null,
      _enterTextPage: () => ({ ok: false, actual: "", msg: "element not found" }),
      _refDocCheckPage: () => null,
      _detectSubmitPage: () => ({ mmid: "99", label: "Search" }), // must NOT be consulted
    });
    // Run A: no submit_mmid — auto-detect must be suppressed entirely.
    const a = await callOp("fill_form", { tabId: 1, fields: FIELDS3() });
    check("stale refs: submit auto-detect suppressed when NO field ref resolves",
      execCalls("_detectSubmitPage").length === 0);
    // The old wording asserted a search that had not run ("no submit button
    // auto-detected"). With the wordlist tiers gone the message states the
    // STRUCTURAL fact instead — nothing in the form declares itself the submit —
    // and names the recovery, which is what an agent can act on.
    check("stale refs: reports NOT submitted, and says what would make it possible",
      String(a.result).includes("NOT submitted")
      && String(a.result).includes("submit_ref"), String(a.result).split("\n")[0]);
    check("stale refs: reports Filled 0/3", String(a.result).startsWith("Filled 0/3"));

    // Run B: EXPLICIT submit_mmid — must be skipped, not clicked.
    const b = await callOp("fill_form", { tabId: 1, fields: FIELDS3(), submit_mmid: "55" });
    check("stale refs: explicit submit SKIPPED with a stale-refs explanation",
      String(b.result).includes("submit SKIPPED") && String(b.result).includes("Nothing was clicked"),
      String(b.result).split("\n")[0]);
    check("stale refs: submit target never clicked (no _clickPage, no CDP mouse input)",
      execCalls("_clickPage").length === 0 && cdpCalls("Input.dispatchMouseEvent").length === 0);
    check("stale refs: submit snapshot machinery never engaged",
      execCalls("inline:submitSnap").length === 0);
  });

  // ---- 4: frameOffsetNow shell re-matching
  await test("frameOffsetNow", async () => {
    resetState();
    // Two SAME-SIZE sibling iframes (the Stripe Elements expiry/CVC shape).
    priv.frameShells.set(1, new Map([[7, { x: 100, y: 200, w: 300, h: 40, src: "https://js.stripe.com/expiry" }]]));
    setStubs({
      _frameShellsPage: () => [
        { src: "https://js.stripe.com/cvc", x: 50, y: 500, w: 300, h: 40 },
        { src: "https://js.stripe.com/expiry", x: 50, y: 560, w: 300, h: 40 },
      ],
    });
    const r1 = await sandbox.frameOffsetNow(1, 7);
    check("frameOffsetNow: src identity beats first same-size sibling (Stripe regression)",
      r1 && r1.x === 50 && r1.y === 560, JSON.stringify(r1));

    // Duplicate src: nearest last-known position wins.
    priv.frameShells.set(1, new Map([[7, { x: 52, y: 558, w: 300, h: 40, src: "S" }]]));
    setStubs({
      _frameShellsPage: () => [
        { src: "S", x: 50, y: 500, w: 300, h: 40 },
        { src: "S", x: 50, y: 560, w: 300, h: 40 },
      ],
    });
    const r2 = await sandbox.frameOffsetNow(1, 7);
    check("frameOffsetNow: duplicate src resolved by nearest position",
      r2 && r2.x === 50 && r2.y === 560, JSON.stringify(r2));

    // Cached shell has no src: geometry fallback must prefer x-position, not first entry.
    priv.frameShells.set(1, new Map([[7, { x: 100, y: 200, w: 300, h: 40, src: "" }]]));
    setStubs({
      _frameShellsPage: () => [
        { src: "a", x: 400, y: 900, w: 300, h: 40 },
        { src: "b", x: 100, y: 900, w: 300, h: 40 },
      ],
    });
    const r3 = await sandbox.frameOffsetNow(1, 7);
    check("frameOffsetNow: src absent -> sane size+x-position fallback",
      r3 && r3.x === 100 && r3.y === 900, JSON.stringify(r3));

    // src drifted (no fresh match): same geometry fallback.
    priv.frameShells.set(1, new Map([[7, { x: 100, y: 200, w: 300, h: 40, src: "https://old.example/x" }]]));
    const r4 = await sandbox.frameOffsetNow(1, 7);
    check("frameOffsetNow: src drift falls back to geometry",
      r4 && r4.x === 100 && r4.y === 900, JSON.stringify(r4));

    // Fresh re-measure empty: return the cached offset, not null/garbage.
    setStubs({ _frameShellsPage: () => [] });
    const r5 = await sandbox.frameOffsetNow(1, 7);
    check("frameOffsetNow: empty re-measure falls back to cached offset",
      r5 && r5.x === 100 && r5.y === 200, JSON.stringify(r5));

    // No cache at all: null (never guess).
    setStubs({
      _frameShellsPage: () => [{ src: "a", x: 1, y: 2, w: 3, h: 4 }],
    });
    const r6 = await sandbox.frameOffsetNow(1, 99);
    check("frameOffsetNow: no cached shell -> null, no guess", r6 === null, JSON.stringify(r6));
  });

  // ---- 5: hidden-tab guard (+ fix #10 ordering)
  // NOTE: the guard's implementation changed from ensureTabVisibleForInput
  // (activate tab + focus window) to ensureInputReady (CDP focus emulation +
  // lifecycle un-throttle, deliberately WITHOUT stealing the user's focus).
  // These checks pin the CURRENT contract: a background tab must be made
  // input-ready via CDP switches before any mouse event, and the user's
  // tab/window focus must NOT be touched.
  await test("hidden-tab guard", async () => {
    resetState();
    state.tabs = [{ id: 3, url: "https://x.example/", title: "x", windowId: 10, active: false, groupId: -1 }];
    state.windows[10] = { focused: false };
    setStubs({ _rectForPage: () => ({ x: 120, y: 80, w: 20, h: 20, visible: true }) });
    const r = await sandbox.clickTrusted(3, "[mmid='9']");
    check("hidden tab: clickTrusted succeeded on a background tab", r && r.ok === true, JSON.stringify(r));

    const iMouse = idxOf((e) => e.kind === "cdp" && e.method === "Input.dispatchMouseEvent");
    const iFocusEmu = idxOf((e) => e.kind === "cdp" && e.method === "Emulation.setFocusEmulationEnabled" &&
      e.params && e.params.enabled === true && e.tabId === 3);
    const iLifecycle = idxOf((e) => e.kind === "cdp" && e.method === "Page.setWebLifecycleState" &&
      e.params && e.params.state === "active" && e.tabId === 3);
    check("hidden tab: focus emulation enabled BEFORE any Input.dispatchMouseEvent",
      iFocusEmu !== -1 && iMouse !== -1 && iFocusEmu < iMouse, `focusEmu@${iFocusEmu} mouse@${iMouse}`);
    check("hidden tab: lifecycle forced 'active' (un-throttled) BEFORE any mouse input",
      iLifecycle !== -1 && iLifecycle < iMouse, `lifecycle@${iLifecycle} mouse@${iMouse}`);
    check("hidden tab: user focus NOT stolen (no tabs.update(active) / windows.update(focused))",
      allOf((e) => e.kind === "tabs.update" && e.props.active === true).length === 0 &&
      allOf((e) => e.kind === "windows.update" && e.props.focused === true).length === 0);

    const iAttach = idxOf((e) => e.kind === "cdp.attach");
    const iRect = idxOf((e) => e.kind === "exec" && e.name === "_rectForPage");
    check("hidden tab: attach BEFORE input-ready switches (they need the debugger)",
      iAttach !== -1 && iFocusEmu !== -1 && iAttach < iFocusEmu, `attach@${iAttach} focusEmu@${iFocusEmu}`);
    check("hidden tab: fix #10 — debugger attached BEFORE coordinates measured",
      iAttach !== -1 && iRect !== -1 && iAttach < iRect, `attach@${iAttach} rect@${iRect}`);

    const mouse = cdpCalls("Input.dispatchMouseEvent");
    check("hidden tab: press+release dispatched at the measured center (120,80)",
      mouse.some((m) => m.params.type === "mousePressed" && m.params.x === 120 && m.params.y === 80) &&
      mouse.some((m) => m.params.type === "mouseReleased" && m.params.x === 120 && m.params.y === 80),
      JSON.stringify(mouse.map((m) => m.params)));
    check("hidden tab: mouseMoved -> mousePressed -> mouseReleased order",
      mouse.map((m) => m.params.type).join(",") === "mouseMoved,mousePressed,mouseReleased");
  });

  await test("computer left_click", async () => {
    resetState();
    const r = await callOp("computer", { tabId: 1, action: "left_click", coordinate: [10, 20] });
    check("computer left_click: CDP press/release at requested coordinate",
      r && r.ok === true &&
      cdpCalls("Input.dispatchMouseEvent").some((m) => m.params.type === "mousePressed" && m.params.x === 10 && m.params.y === 20),
      JSON.stringify(r));
    check("computer left_click: infobar-shift warning on FIRST attach with raw coordinates",
      /debugger infobar/.test(String(r && r.result)), String(r && r.result).slice(0, 200));
    const iFocusEmu = idxOf((e) => e.kind === "cdp" && e.method === "Emulation.setFocusEmulationEnabled");
    const iPress = idxOf((e) => e.kind === "cdp" && e.method === "Input.dispatchMouseEvent" && e.params.type === "mousePressed");
    check("computer left_click: input-ready (focus emulation) precedes the click on this path too",
      iFocusEmu !== -1 && iPress !== -1 && iFocusEmu < iPress, `focusEmu@${iFocusEmu} press@${iPress}`);
    const r2 = await callOp("computer", { tabId: 1, action: "left_click", coordinate: [10, 20] });
    check("computer left_click: no shift warning once already attached",
      r2 && r2.ok === true && !/debugger infobar/.test(String(r2.result)), String(r2 && r2.result).slice(0, 200));
  });

  // ---- 6: batch_actions stop-on-failure
  await test("batch_actions", async () => {
    resetState();
    let pressRan = 0;
    setStubs({
      _highlightPage: () => true,
      _clickPage: () => ({ ok: true, msg: "clicked" }),
      _enterTextPage: () => ({ ok: false, actual: "", msg: "nope" }),
      _pressKeysPage: () => { pressRan++; return { ok: true, msg: "pressed" }; },
    });
    const steps = [
      { op: "click", selector: "[mmid='1']" },
      { op: "type", selector: "[mmid='2']", text: "x" },
      { op: "press", combo: "Enter" },
    ];
    const r = await callOp("batch_actions", { tabId: 1, steps });
    check("batch_actions: failing step HALTS the sequence (press never ran)", pressRan === 0);
    check("batch_actions: summary reports 1/3 OK (stopped on failure)",
      /1\/3 steps OK \(stopped on failure\)/.test(String(r.result)), String(r.result).split("\n")[0]);
    const traceMatch = /trace=(\[.*\])$/s.exec(String(r.result));
    const trace = traceMatch ? JSON.parse(traceMatch[1]) : null;
    check("batch_actions: trace contains exactly the 2 executed steps",
      Array.isArray(trace) && trace.length === 2 && trace[0].ok === true && trace[1].ok === false,
      JSON.stringify(trace));

    const r2 = await callOp("batch_actions", { tabId: 1, steps, stop_on_fail: false });
    check("batch_actions: stop_on_fail=false runs ALL steps (2/3 OK)",
      pressRan === 1 && /2\/3 steps OK/.test(String(r2.result)), String(r2.result).split("\n")[0]);
  });

  // ---- 7: MCP tab-group lifecycle + tabs_close policy
  await test("tab group ops", async () => {
    resetState();
    const c0 = await callOp("tabs_context", { createIfEmpty: false });
    check("tabs_context: no group and createIfEmpty=false -> groupId null, nothing created",
      c0.ok && c0.result.groupId === null && c0.result.tabIds.length === 0 &&
      allOf((e) => e.kind === "tabs.create").length === 0, JSON.stringify(c0.result));

    const c1 = await callOp("tabs_context", { createIfEmpty: true });
    check("tabs_context: createIfEmpty creates a group with one seed tab",
      c1.ok && c1.result.groupId != null && c1.result.tabIds.length === 1, JSON.stringify(c1.result));
    const gUpd = allOf((e) => e.kind === "tabGroups.update")[0];
    check("tabs_context: group titled 'Claude'", gUpd && gUpd.props.title === "Claude", JSON.stringify(gUpd));
    const gid = c1.result.groupId;
    const seed = c1.result.tabIds[0];

    const createsBefore = allOf((e) => e.kind === "tabs.create").length;
    const c2 = await callOp("tabs_create", {});
    check("tabs_create: reuses the brand-new group's about:blank seed tab",
      c2.ok && c2.result.tabId === seed && allOf((e) => e.kind === "tabs.create").length === createsBefore,
      JSON.stringify(c2.result));

    state.tabs.find((t) => t.id === seed).url = "https://somewhere.example/";
    const c3 = await callOp("tabs_create", {});
    check("tabs_create: adds a fresh tab into the existing group once the seed navigated",
      c3.ok && c3.result.tabId !== seed && c3.result.groupId === gid &&
      state.tabs.find((t) => t.id === c3.result.tabId).groupId === gid, JSON.stringify(c3.result));

    // NEVER STEAL THE USER'S VIEW. Creating an agent tab with active:true yanks the
    // browser to it mid-task; the user hit this twice and it is precisely the disruption
    // this project exists to avoid. Trusted input works on background tabs via
    // ensureInputReady(), so there is no functional reason to activate anything.
    const allCreates = allOf((e) => e.kind === "tabs.create");
    check("tab creation NEVER activates the tab (no focus stealing)",
      allCreates.length > 0 && allCreates.every((e) => e.props && e.props.active === false),
      JSON.stringify(allCreates.map((e) => e.props)));
    check("no tab was ever switched to via tabs.update({active})",
      allOf((e) => e.kind === "tabs.update" && e.props && e.props.active === true).length === 0);
    check("no window was ever focused or un-minimized",
      allOf((e) => e.kind === "windows.update" && e.props &&
                   (e.props.focused === true || e.props.state === "normal")).length === 0);

    state.tabs.push({ id: 900, url: "https://user.example/", title: "user tab", windowId: 10, active: false, groupId: -1 });
    const c4 = await callOp("tabs_close", { tabId: 900 });
    check("tabs_close: REFUSES a tab outside the MCP group",
      c4.ok === false && /not in the MCP tab group/.test(String(c4.error)), JSON.stringify(c4));
    check("tabs_close: refused tab was NOT removed",
      state.tabs.some((t) => t.id === 900) && allOf((e) => e.kind === "tabs.remove" && e.id === 900).length === 0);

    const c5 = await callOp("tabs_close", { tabId: c3.result.tabId });
    check("tabs_close: closes a tab inside the MCP group",
      c5.ok && c5.result.closed === c3.result.tabId && !state.tabs.some((t) => t.id === c3.result.tabId),
      JSON.stringify(c5));

    const c6 = await callOp("tabs_close", { tabId: "abc" });
    check("tabs_close: invalid tabId rejected", c6.ok === false && /invalid tabId/.test(String(c6.error)), JSON.stringify(c6));

    const c7 = await callOp("tabs_close", { tabId: 424242 });
    check("tabs_close: unknown tab reported as not found", c7.ok === false && /not found/.test(String(c7.error)), JSON.stringify(c7));
  });

  // ---- cross-frame routing in fill_form
  await test("fill_form frame routing", async () => {
    resetState();
    setStubs({});
    const r = await callOp("fill_form", {
      tabId: 1,
      fields: [{ selector: "[mmid='f3:1']", text: "a" }, { selector: "[mmid='f4:2']", text: "b" }],
    });
    check("fill_form: mixed-frame fields rejected with a split hint",
      r.ok && /span multiple frames/.test(String(r.result)), String(r.result).slice(0, 160));
    check("fill_form: mixed-frame rejection executes NOTHING in the page",
      allOf((e) => e.kind === "exec").length === 0);

    setStubs({
      _ensureMmidsPage: () => true,
      "inline:fieldKindsProbe": (sels) => sels.map(() => ({ kind: "text" })),
      "inline:batchTextWrite": (jobs) => Object.fromEntries(jobs.map((j) => [j.idx, { ok: true, actual: j.text, msg: "typed" }])),
    });
    const r2 = await callOp("fill_form", {
      tabId: 1,
      fields: [{ selector: "[mmid='f3:5']", text: "4242" }],
      no_submit: true,
    });
    check("fill_form: single-frame call reports Filled 1/1", r2.ok && String(r2.result).startsWith("Filled 1/1"),
      String(r2.result).split("\n")[0]);
    const execs = allOf((e) => e.kind === "exec");
    check("fill_form: EVERY page script of a single-frame call targets frameIds=[3]",
      execs.length > 0 && execs.every((e) => Array.isArray(e.target.frameIds) && e.target.frameIds[0] === 3),
      JSON.stringify(execs.map((e) => [e.name, e.target])));
    const batch = execCalls("inline:batchTextWrite")[0];
    check("fill_form: in-frame selector stripped to its frame-local form",
      batch && batch.args[0][0].selector === "[mmid='5']", batch && JSON.stringify(batch.args));
  });

  // ---- fill_form submit inside a dialog goes straight to trusted input
  await test("fill_form dialog submit", async () => {
    resetState();
    let snapI = 0;
    const snaps = [
      { url: "https://app.example/form", dialogs: 1, n: 100, txt: 1000, btnTxt: "Save", btnBusy: false },
      { url: "https://app.example/form", dialogs: 0, n: 90, txt: 900, btnTxt: null, btnBusy: null },
    ];
    setStubs({
      _ensureMmidsPage: () => true,
      "inline:fieldKindsProbe": (sels) => sels.map(() => ({ kind: "text" })),
      "inline:batchTextWrite": (jobs) => Object.fromEntries(jobs.map((j) => [j.idx, { ok: true, actual: j.text, msg: "typed" }])),
      _highlightPage: () => true,
      "inline:submitResolves": () => true,
      "inline:submitSnap": () => snaps[Math.min(snapI++, 1)],
      _rectForPage: () => ({ x: 200, y: 300, w: 80, h: 32, visible: true }),
      _clickPage: () => ({ ok: true, msg: "should not have been used" }),
      _refDocCheckPage: () => null,
    });
    const r = await callOp("fill_form", { tabId: 1, fields: [{ selector: "[mmid='21']", text: "X" }], submit_mmid: "40" });
    check("dialog submit: goes STRAIGHT to trusted CDP click (press at measured center)",
      cdpCalls("Input.dispatchMouseEvent").some((m) => m.params.type === "mousePressed" && m.params.x === 200 && m.params.y === 300),
      JSON.stringify(cdpCalls("Input.dispatchMouseEvent").map((m) => m.params)));
    check("dialog submit: NO untrusted _clickPage attempt on the submit",
      execCalls("_clickPage").length === 0);
    check("dialog submit: reports modal closed (1 -> 0)",
      r.ok && /modal closed \(1 -> 0\)/.test(String(r.result)), String(r.result).split("\n")[0]);
  });

  // ---- fill_form submit escalation + validation sweep
  await test("fill_form submit escalation", async () => {
    resetState();
    setStubs({
      _ensureMmidsPage: () => true,
      "inline:fieldKindsProbe": (sels) => sels.map(() => ({ kind: "text" })),
      "inline:batchTextWrite": (jobs) => Object.fromEntries(jobs.map((j) => [j.idx, { ok: true, actual: j.text, msg: "typed" }])),
      _highlightPage: () => true,
      "inline:submitResolves": () => true,
      // No dialog, nothing ever changes -> untrusted try, then trusted retry, then error sweep.
      "inline:submitSnap": () => ({ url: "https://app.example/form", dialogs: 0, n: 100, txt: 1000, btnTxt: "Save", btnBusy: false }),
      _clickPage: () => ({ ok: true, msg: "synthetic click reported ok" }),
      _rectForPage: () => ({ x: 10, y: 10, w: 50, h: 30, visible: true }),
      "inline:errorSweep": () => ["Name is required"],
      "inline:unfilledSweep": () => ["[mmid='21'] (required-empty) \"Name\""],
      _refDocCheckPage: () => null,
    });
    const r = await callOp("fill_form", { tabId: 1, fields: [{ selector: "[mmid='21']", text: "X" }], submit_mmid: "40" });
    const iUntrusted = idxOf((e) => e.kind === "exec" && e.name === "_clickPage");
    const iTrusted = idxOf((e) => e.kind === "cdp" && e.method === "Input.dispatchMouseEvent" && e.params.type === "mousePressed");
    check("submit escalation: untrusted click first, trusted CDP retry after",
      iUntrusted !== -1 && iTrusted !== -1 && iUntrusted < iTrusted, `untrusted@${iUntrusted} trusted@${iTrusted}`);
    check("submit escalation: reports failure even after trusted retry + surfaces validation error",
      /NO real effect even after trusted retry/.test(String(r.result)) && /Name is required/.test(String(r.result)),
      String(r.result).split("\n")[0]);
    check("submit escalation: unfilled required fields enumerated as retry targets",
      /UNFILLED fields in dialog/.test(String(r.result)) && /required-empty/.test(String(r.result)));
  });

  // ---- fill_form orphaned submit selector re-resolution
  await test("fill_form submit re-resolve", async () => {
    resetState();
    let snapI = 0;
    setStubs({
      _ensureMmidsPage: () => true,
      "inline:fieldKindsProbe": (sels) => sels.map(() => ({ kind: "text" })),
      "inline:batchTextWrite": (jobs) => Object.fromEntries(jobs.map((j) => [j.idx, { ok: true, actual: j.text, msg: "typed" }])),
      _highlightPage: () => true,
      "inline:submitResolves": () => false,          // the given submit ref is orphaned
      _detectSubmitPage: () => ({ mmid: "77", label: "Create" }),
      "inline:submitSnap": () => (snapI++ === 0
        ? { url: "https://a.example/f", dialogs: 0, n: 1, txt: 1, btnTxt: "Create", btnBusy: false }
        : { url: "https://a.example/done", dialogs: 0, n: 1, txt: 1, btnTxt: null, btnBusy: null }),
      _clickPage: (sel) => ({ ok: true, msg: "clicked " + sel }),
      _refDocCheckPage: () => null,
    });
    const r = await callOp("fill_form", { tabId: 1, fields: [{ selector: "[mmid='21']", text: "X" }], submit_mmid: "40" });
    const clicks = execCalls("_clickPage");
    check("submit re-resolve: orphaned selector re-detected and the NEW target clicked",
      clicks.length === 1 && clicks[0].args[0] === "[mmid='77']", JSON.stringify(clicks.map((c) => c.args)));
    const iResolves = idxOf((e) => e.kind === "exec" && e.name === "inline:submitResolves");
    const iDetect = idxOf((e) => e.kind === "exec" && e.name === "_detectSubmitPage");
    check("submit re-resolve: detection runs only AFTER the resolve probe failed",
      iResolves !== -1 && iDetect !== -1 && iResolves < iDetect, `resolves@${iResolves} detect@${iDetect}`);
    check("submit re-resolve: reresolved flag reported in details",
      r.ok && /"reresolved":true/.test(String(r.result)), String(r.result).slice(0, 200));
  });

  // ---- click op auto-escalation
  await test("click auto-escalation", async () => {
    resetState();
    setStubs({
      _highlightPage: () => true,
      "inline:fingerprint": () => ({ n: 100, txt: 1000 }),   // never changes -> zero effect
      _clickPage: () => ({ ok: true, msg: "clicked" }),
      _rectForPage: () => ({ x: 60, y: 40, w: 20, h: 20, visible: true }),
      _refDocCheckPage: () => null,
    });
    const r = await callOp("click", { tabId: 1, selector: "[mmid='5']" });
    const iSynthetic = idxOf((e) => e.kind === "exec" && e.name === "_clickPage");
    const iCdp = idxOf((e) => e.kind === "cdp" && e.method === "Input.dispatchMouseEvent");
    check("click: zero-effect synthetic click auto-escalates to trusted CDP input",
      /auto-escalated to trusted input/.test(String(r.result)) &&
      iSynthetic !== -1 && iCdp !== -1 && iSynthetic < iCdp,
      String(r.result).slice(0, 200));
    check("click: still warns when even the trusted retry had no effect",
      /NO detectable effect/.test(String(r.result)));
  });

  // ---- navigate
  await test("navigate", async () => {
    resetState();
    const r = await callOp("navigate", { tabId: 1, url: "example.com" });
    const upd = allOf((e) => e.kind === "tabs.update" && e.props.url).pop();
    check("navigate: protocol-less URL gets https:// prefix",
      upd && upd.props.url === "https://example.com", JSON.stringify(upd));
    check("navigate: reports the final URL after load completes",
      r.ok && /Navigated to https:\/\/example\.com/.test(String(r.result)), String(r.result));
    const r2 = await callOp("navigate", { tabId: 1, url: "back" });
    check("navigate: url='back' routes to tabs.goBack",
      r2.ok && allOf((e) => e.kind === "tabs.goBack").length === 1, JSON.stringify(r2));
  });

  // ---- network capture buffers
  // ---- read_page detail levels: the op router is the ONLY untested link in the
  // chain. Every other detail-level test injects the collector directly, so a
  // param that never reaches _collectInteractivePage would look perfect offline
  // and silently return `compact` for every detail="full" call in production.
  await test("get_interactive_elements: detail level reaches the collector", async () => {
    resetState();
    currentStubs["_collectInteractivePage"] = () => "LISTING";
    currentStubs["_ensureMmidsPage"] = () => true;

    const argsOf = () => {
      const e = [...callLog].reverse().find((l) => l.kind === "exec" && l.name === "_collectInteractivePage");
      return e ? e.args : null;
    };

    await callOp("get_interactive_elements", { tabId: 1 });
    let a = argsOf();
    check("read_page: default detail is compact",
      !!a && a[2] === "compact", JSON.stringify(a));

    callLog.length = 0;
    await callOp("get_interactive_elements", { tabId: 1, detail: "full" });
    a = argsOf();
    check("read_page: detail='full' is forwarded to the collector",
      !!a && a[2] === "full", JSON.stringify(a));

    // 'brief' shipped with the collector and mcp_server updated but NOT the
    // router, so every detail="brief" call silently returned compact. Found on a
    // live page, not by any offline test — which is precisely what the comment
    // above predicted would happen again.
    callLog.length = 0;
    await callOp("get_interactive_elements", { tabId: 1, detail: "brief" });
    a = argsOf();
    check("read_page: detail='brief' is forwarded to the collector",
      !!a && a[2] === "brief", JSON.stringify(a));

    callLog.length = 0;
    await callOp("get_interactive_elements", { tabId: 1, detail: "nonsense" });
    a = argsOf();
    check("read_page: an unknown detail falls back to compact",
      !!a && a[2] === "compact", JSON.stringify(a));

    callLog.length = 0;
    await callOp("get_interactive_elements", { tabId: 1, scopeMmid: "42", detail: "full" });
    a = argsOf();
    check("read_page: ref_id scoping and detail compose (the intended usage)",
      !!a && a[1] === "42" && a[2] === "full", JSON.stringify(a));

    callLog.length = 0;
    await callOp("get_interactive_elements", { tabId: 1, detail: "everything" });
    a = argsOf();
    check("read_page: an unrecognised detail value fails safe to compact",
      !!a && a[2] === "compact", JSON.stringify(a));

    // `geometry` is the 5th positional. Same class of gap as detail="brief":
    // every offline geometry test calls the collector directly, so a flag that
    // never reached it would look perfect here and drop box() from every
    // geometry=true call in production.
    callLog.length = 0;
    await callOp("get_interactive_elements", { tabId: 1 });
    a = argsOf();
    check("read_page: geometry defaults to false (box() is opt-in)",
      !!a && a[4] === false, JSON.stringify(a));

    callLog.length = 0;
    await callOp("get_interactive_elements", { tabId: 1, geometry: true });
    a = argsOf();
    check("read_page: geometry=true is forwarded to the collector",
      !!a && a[4] === true, JSON.stringify(a));

    callLog.length = 0;
    await callOp("get_interactive_elements", { tabId: 1, geometry: true, detail: "brief", scopeMmid: "7" });
    a = argsOf();
    check("read_page: geometry composes with detail and ref_id scoping",
      !!a && a[4] === true && a[2] === "brief" && a[1] === "7", JSON.stringify(a));

    // `format` is the 6th positional — same shape as geometry and detail="brief",
    // both of which shipped inert because the router was the one untested link.
    callLog.length = 0;
    await callOp("get_interactive_elements", { tabId: 1 });
    a = argsOf();
    check("read_page: format defaults to tree", !!a && a[5] === "tree", JSON.stringify(a));

    callLog.length = 0;
    await callOp("get_interactive_elements", { tabId: 1, format: "flat" });
    a = argsOf();
    check("read_page: format='flat' is forwarded to the collector",
      !!a && a[5] === "flat", JSON.stringify(a));

    // An unknown value now falls back to the DEFAULT, which is tree. Same
    // fail-safe rule as detail="nonsense" -> compact: an unrecognised value gets
    // the documented default, never a silently different surface.
    callLog.length = 0;
    await callOp("get_interactive_elements", { tabId: 1, format: "nonsense" });
    a = argsOf();
    check("read_page: an unknown format fails safe to the default (tree)",
      !!a && a[5] === "tree", JSON.stringify(a));
  });

  await test("read_network_requests", async () => {
    resetState();
    const fire = (arr, d) => arr.forEach((fn) => fn(d));
    fire(listeners.netCompleted, { tabId: 1, url: "https://api.example/data", method: "GET", type: "xmlhttprequest", statusCode: 200, fromCache: false, timeStamp: Date.now() });
    fire(listeners.netError, { tabId: 1, url: "https://cdn.example/x.js", method: "GET", type: "script", error: "net::ERR_FAILED", timeStamp: Date.now() });
    fire(listeners.netCompleted, { tabId: 2, url: "https://other.example/only-tab2", method: "GET", type: "xmlhttprequest", statusCode: 200, fromCache: false, timeStamp: Date.now() });
    const r = await callOp("read_network_requests", { tabId: 1 });
    const res = String(r.result);
    check("network: per-tab buffer (tab 1 sees its 2 requests, not tab 2's)",
      r.ok && res.includes("api.example") && res.includes("net::ERR_FAILED") && !res.includes("only-tab2"),
      res.slice(0, 200));
    const rf = await callOp("read_network_requests", { tabId: 1, urlPattern: "cdn.example" });
    check("network: urlPattern filters the listing",
      rf.ok && String(rf.result).includes("cdn.example") && !String(rf.result).includes("api.example") &&
      /1 request\(s\)/.test(String(rf.result)), String(rf.result).slice(0, 200));
    fire(listeners.navCommitted, { frameId: 0, tabId: 1, url: "https://elsewhere.example/" });
    const r2 = await callOp("read_network_requests", { tabId: 1 });
    check("network: cross-origin main-frame commit clears the tab's buffer",
      r2.ok && /No network requests recorded/.test(String(r2.result)), String(r2.result).slice(0, 120));
  });

  // ---- read_console_messages formatting
  await test("read_console_messages", async () => {
    resetState();
    setStubs({ "inline:consoleRead": () => ({ available: false, total: 0, messages: [] }) });
    const r1 = await callOp("read_console_messages", { tabId: 1 });
    check("read_console_messages: reports capture inactive when the tag never ran",
      r1.ok && /capture not active/i.test(String(r1.result)), String(r1.result).slice(0, 120));
    setStubs({
      "inline:consoleRead": () => ({
        available: true, total: 2,
        messages: [{ ts: 0, level: "error", text: "boom" }, { ts: 0, level: "log", text: "hello" }],
      }),
    });
    const r2 = await callOp("read_console_messages", { tabId: 1 });
    check("read_console_messages: formats buffered messages with level + count",
      r2.ok && /2 message\(s\) matched/.test(String(r2.result)) && /ERROR: boom/.test(String(r2.result)),
      String(r2.result).slice(0, 200));
  });

  // ---- unknown op
  await test("unknown op", async () => {
    resetState();
    const r = await callOp("bogus_op", {});
    check("unknown op: error reply, not a crash",
      r && r.ok === false && /unknown op: bogus_op/.test(String(r.error)), JSON.stringify(r));
  });

  // ---- WebMCP ops through the ROUTER. Every offline check of the page functions
  // calls them directly, which is exactly the gap CLAUDE.md #19 describes: a param
  // that never reaches the page would look perfect there and be inert in
  // production. These assert the wiring, not the WebMCP logic.
  await test("page_tools / call_page_tool reach the page with the right arguments", async () => {
    resetState();
    currentStubs["_pageToolsPage"] = () => ({ supported: true, tools: [{ name: "t1" }] });
    currentStubs["_callPageToolPage"] = () => ({ ok: true, result: "done" });

    const argsOf = (fn) => {
      const e = [...callLog].reverse().find((l) => l.kind === "exec" && l.name === fn);
      return e ? e.args : null;
    };

    let r = await callOp("page_tools", { tabId: 1 });
    check("page_tools: routed to the page and the reply is JSON",
      r && r.ok !== false && /"supported":true/.test(String(r.result)), JSON.stringify(r).slice(0, 120));

    callLog.length = 0;
    r = await callOp("call_page_tool", { tabId: 1, name: "addToCart", args: '{"sku":"A-1"}' });
    let a = argsOf("_callPageToolPage");
    check("call_page_tool: name and args JSON are forwarded verbatim",
      !!a && a[0] === "addToCart" && a[1] === '{"sku":"A-1"}', JSON.stringify(a));

    // An object is accepted and serialized, so a caller passing a dict is not
    // silently turned into "[object Object]" for the page to choke on.
    callLog.length = 0;
    await callOp("call_page_tool", { tabId: 1, name: "x", args: { sku: "B-2" } });
    a = argsOf("_callPageToolPage");
    check("call_page_tool: an object argument is serialized, not stringified to [object Object]",
      !!a && a[1] === '{"sku":"B-2"}', JSON.stringify(a));

    callLog.length = 0;
    await callOp("call_page_tool", { tabId: 1, name: "x" });
    a = argsOf("_callPageToolPage");
    check("call_page_tool: omitted args become an empty JSON object",
      !!a && a[1] === "{}", JSON.stringify(a));
  });

  // -------------------------------------------------------------------------
  console.log(`\n${passCount} passed, ${failCount} failed, ${passCount + failCount} total checks`);
  if (failCount) {
    console.log("Failed checks:");
    for (const f of failures) console.log(`  - ${f}`);
  }
  // Explicit exit: background.js's navigate op leaves a 15s fallback timer
  // pending (it never clears it after the load completes), which would
  // otherwise keep this process alive for up to 15 extra seconds.
  process.exit(failCount ? 1 : 0);
})().catch((e) => {
  console.error("FATAL harness error:", e && e.stack || e);
  process.exit(1);
});
