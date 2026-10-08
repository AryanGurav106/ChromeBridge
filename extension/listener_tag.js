// Runs in the MAIN world at document_start (see manifest content_scripts).
//
// PURPOSE: the one element class invisible to any DOM walk is the bare
// <div>/<span> with a JS click handler and NO other signal (no role, no
// cursor:pointer, no tabindex, no onclick attribute). Frameworks bind these
// via addEventListener, which leaves zero static trace. We wrap
// EventTarget.prototype.addEventListener before any page script runs and tag
// the element with a non-enumerable expando the collector can read.
//
// Notes:
//  - An expando (not an attribute) keeps the page's DOM untouched — no
//    selector, MutationObserver, or serializer can see it.
//  - React/Vue delegate most handlers to the root, so per-element tagging
//    can't see THOSE — but framework components virtually always carry
//    cursor/role styling that the collector already detects. This targets
//    hand-rolled vanilla-JS handler elements.
//  - CDP DOMDebugger.getEventListeners would be equivalent but requires the
//    debugger attached (yellow infobar) on every observation; this is free.
(() => {
  try {
    const orig = EventTarget.prototype.addEventListener;
    if (!orig || orig.__abWrapped) return;
    const ACTIVATION = new Set(['click', 'pointerdown', 'mousedown', 'touchstart', 'pointerup', 'mouseup']);
    const wrapped = function (type, listener, options) {
      try {
        if (listener && ACTIVATION.has(String(type)) && this && this.nodeType === 1) {
          // DELEGATION ROOTS are not click targets: frameworks bind one
          // handler on body/html/#root and route by event.target — tagging
          // them produced giant body-sized "controls" (Wikipedia).
          const tn = this.tagName;
          if (tn !== 'BODY' && tn !== 'HTML' && tn !== 'MAIN') {
            // Non-enumerable so page code iterating own props never sees it.
            if (!this.__abClickBound) {
              Object.defineProperty(this, '__abClickBound', { value: true, configurable: true });
            }
          }
        }
      } catch (e) {}
      return orig.call(this, type, listener, options);
    };
    try { Object.defineProperty(wrapped, '__abWrapped', { value: true }); } catch (e) {}
    EventTarget.prototype.addEventListener = wrapped;
  } catch (e) {}
})();

// CLOSED SHADOW ROOTS, with no debugger attach — limitation #2's last open case.
//
// A closed root is unreachable from any page-context walk: `el.shadowRoot` is null
// and there is no other handle. browser-use solves this with CDP
// `DOM.getDocument{pierce:true}`, which is strictly more capable AND strictly less
// available: limitation #12 means the attach is refused tab-wide whenever another
// extension has injected an iframe, i.e. on exactly the password-manager login
// pages where an agent most needs to read the form. `chrome.dom.openOrClosedShadowRoot`
// would also work but only from the ISOLATED world, and the collector must run in
// MAIN — that is how it reads `__abClickBound` above, which #18 measured as 60% of
// the accuracy gap.
//
// The same trick as the wrap above closes it for free: attachShadow cannot create a
// root without calling this, and at document_start in MAIN world nothing beats us to
// it, so we hold a reference to every closed root the page will ever make.
//
// TWO DELIBERATE CHOICES:
//  - `Element.prototype.shadowRoot` is NOT redefined, though it would make all ~15
//    existing traversal sites pierce with no other change. That getter returning
//    null is how a page feature-detects its OWN encapsulation, and silently changing
//    an observable page behaviour is a different and much worse class of risk than
//    adding an invisible expando. The wrap above is semantics-preserving; that would
//    not be.
//  - The reference lands on a non-enumerable expando, so no selector, serializer or
//    property enumeration sees it. It does make the page's closed root reachable to
//    other script IN THAT PAGE — but that is the page's own same-origin data, which
//    it created and can already reach through the closure that made it.
(() => {
  try {
    const orig = Element.prototype.attachShadow;
    if (!orig || orig.__abWrapped) return;
    const wrapped = function (init) {
      const root = orig.apply(this, arguments);
      try {
        if (init && init.mode === 'closed' && !this.__abClosedRoot) {
          Object.defineProperty(this, '__abClosedRoot', { value: root, configurable: true });
        }
      } catch (e) {}
      return root;
    };
    try { Object.defineProperty(wrapped, '__abWrapped', { value: true }); } catch (e) {}
    Element.prototype.attachShadow = wrapped;
  } catch (e) {}
})();

// --------------------- console capture (read_console_messages) --------------
// Wrap console.* from document_start into a bounded page-global ring buffer the
// background's read_console_messages op reads via chrome.scripting. No debugger
// attach needed. Browser-generated messages (CSP violations, network errors)
// are NOT routed through console.* and therefore aren't captured here.
(() => {
  try {
    if (window.__abConsole) return;
    const CAP = 500;
    const store = { buf: [], dropped: 0 };
    Object.defineProperty(window, '__abConsole', { value: store, configurable: true });
    const fmt = (a) => {
      try {
        if (typeof a === 'string') return a;
        if (a instanceof Error) return a.stack || String(a);
        return JSON.stringify(a, (k, v) => {
          if (v instanceof Node) return `[${v.nodeName}]`;
          if (typeof v === 'function') return '[function]';
          return v;
        });
      } catch (e) { try { return String(a); } catch (e2) { return '[unserializable]'; } }
    };
    const push = (level, args) => {
      try {
        const text = Array.prototype.map.call(args, fmt).join(' ').slice(0, 2000);
        store.buf.push({ level, text, ts: Date.now(), url: String(location.href).slice(0, 300) });
        if (store.buf.length > CAP) { store.buf.splice(0, store.buf.length - CAP); store.dropped++; }
      } catch (e) {}
    };
    for (const level of ['log', 'info', 'warn', 'error', 'debug']) {
      const orig = console[level];
      if (typeof orig !== 'function') continue;
      console[level] = function (...args) { push(level, args); return orig.apply(this, args); };
    }
    // Uncaught exceptions / promise rejections count as error-level messages.
    window.addEventListener('error', (e) => {
      push('error', [`Uncaught ${e.message || 'error'} at ${e.filename || '?'}:${e.lineno || '?'}`]);
    }, true);
    window.addEventListener('unhandledrejection', (e) => {
      push('error', [`Unhandled promise rejection: ${e.reason && (e.reason.stack || e.reason.message) || e.reason}`]);
    }, true);
  } catch (e) {}
})();
