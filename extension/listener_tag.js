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
// --------------------- DOM mutation recency (readiness) ---------------------
// The readiness probe used to measure the NETWORK, and the agent's question is
// about the DOM. Measured, both directions, in scratchpad/probe_false_negative:
//
//   STILL BUILDING, network silent (an SPA painting 400 rows in setTimeout
//   chunks): readyState=complete, 0 aria-busy, 0 progressbars, 0 requests in
//   flight. EVERY signal we shipped said "settled" while the table went from 64
//   rows to 400. The agent reads a third of a table and concludes.
//
//   READY BUT CHATTY (painted and done, with a 120ms poll and a beacon):
//   3-6 requests permanently in flight, so the banner fired for ever on a page
//   that finished before the first read. An always-on warning is the noise #15
//   priced and #43 deleted readyState for being.
//
// DOM-mutation recency separates them with no overlap -- 9-18ms while building
// against 907-3514ms when done -- so we do not have to choose a threshold,
// because we report the NUMBER and not a verdict (#33, #65, #60).
//
// WHY IT LIVES HERE. You cannot observe mutations that already happened, so the
// observer has to be installed before any page script runs. That is the same
// reason the two wraps above are here, and document_start MAIN world is the only
// place it can be.
//
// COST, interleaved A/B on the same page load, order rotated, 9 replicates:
// +0.10ms / +1.40ms / +2.70ms at 200 / 2,000 / 10,000 mutations against a 1.7%
// drift floor. The callback does nothing but record -- only 32 survivors per
// batch are STORED, though every record is INSPECTED -- and all attribution is
// deferred to read time.
//
// IT IS NOT "FREE AT ANY RATE", WHICH IS WHAT THIS COMMENT USED TO SAY. An
// independent audit re-derived it further out: **+63ms at 40,000 mutations in
// one batch**, against a 0.0% A/A drift floor at that size. The cost is
// SUPERLINEAR -- 4x the mutations for 17x the cost -- and a 2,000-row grid
// render lands there. Two things keep it a caveat rather than a refutation: an
// EMPTY-callback observer with the same options costs essentially the same at
// 40k, so this is the inherent price of a document-wide subtree observer rather
// than of this implementation; and +63ms is 1.7% of a model turn (#38), so the
// conclusion ("nothing here to optimise") survives even though the words did
// not. 2,000 shadow-root registrations add ~+1.0ms at 10k.
//
// NO ATTRIBUTE FILTER, deliberately. A filter is a list that drifts from what the
// listing actually prints (#21's one-concept-two-spellings). Instead every record
// keeps its attribute NAME and the reader is told what changed: "40 style, 0
// structural" and "0 style, 40 structural" are opposite facts and a filtered
// count cannot tell them apart.
//
// SHADOW ROOTS. A MutationObserver on `document` does not see into one. #25
// records this exact bug class in this exact probe ("shadow-blind -- fourth home
// for a bug class fixed twice"), so every root the page creates is registered
// below from inside the attachShadow wrap -- open AND closed, since nothing can
// create a closed root without going through it.
(() => {
  try {
    if (window.__abMut) return;
    const CAP = 1024;
    const ts = new Float64Array(CAP);     // performance.now() per record
    const kd = new Uint8Array(CAP);       // 1 structural, 2 re-text, 3 attributes
    // A `textContent =` ASSIGNMENT IS A RE-TEXT, AND THE RING WAS FILING IT AS
    // STRUCTURAL. The DOM implements it by removing the old Text node and
    // inserting a new one, so it arrives as a `childList` record -- which made
    // every clock tick, live price and status line trip the STRONG "elements
    // were added, removed or re-texted ... do NOT conclude something is absent"
    // banner, for ever. READINESS.md 5(b) names this as the case the #70
    // kind-split provably does not cover, and the adversarial audit measured the
    // consequence at SIX steady-state reads warning about content that never
    // changes again -- the always-on warning #15 priced and #43 deleted
    // `readyState` for.
    //
    // THIS IS A MISCLASSIFICATION, NOT A NEW RULE. The ring's own vocabulary
    // already has a `text` kind, and the banner's own words define `structural`
    // as ELEMENTS being added or removed. `Node.nodeType` decides which one a
    // childList record is: a declaration, with no threshold, class name, framework
    // name or wordlist (PRINCIPLES 1).
    //
    // IT CANNOT PRODUCE SILENCE, by construction rather than by measurement: a
    // reclassified record moves from `structural` to `text`, and both are
    // non-zero tiers, so a read that warned before still warns. What changes is
    // WHICH warning.
    //
    // STRICTLY nodeType === 3. A comment node, a CDATA section or anything else
    // stays structural, which OVER-warns -- the safe direction. And a
    // `textContent =` that destroys real ELEMENTS still carries them in
    // removedNodes, so it stays structural: measured as shape 20 of the
    // adversarial audit, where ten buttons are removed by one textContent
    // assignment and the verdict is correctly STRONG.
    //
    // COST, against the unpatched ring, interleaved on the same page load with an
    // A/A floor taken in the same sequence (PRINCIPLES 10), at 40,000 mutations
    // in ONE batch -- the 2,000-row grid regime #70's own cost note names:
    //   append      9.3ms -> 9.3ms   (A/A floor 0.00%)
    //   retext     14.8ms -> 15.0ms  (+1.35%, A/A floor 0.68%)
    //   attributes 10.1ms -> 10.0ms  (A/A floor 0.00%)
    // Every reading is inside its own drift floor. The scan early-exits on the
    // first non-Text node, so an element append pays one nodeType read.
    const _allText = (r) => {
      try {
        const a = r.addedNodes, b = r.removedNodes;
        if (!a.length && !b.length) return false;
        for (let i = 0; i < a.length; i++) if (a[i].nodeType !== 3) return false;
        for (let i = 0; i < b.length; i++) if (b[i].nodeType !== 3) return false;
        return true;
      } catch (e) { return false; }
    };
    const an = new Array(CAP);            // attribute name, or null
    const tg = new Array(CAP);            // WeakRef(target), or null
    let n = 0;                            // monotonic total; slot = n % CAP
    let wrote = 0;                        // slots actually written -- NOT n
    let obs = null;

    const rec = (recs) => {
      // OUR OWN WRITES ARE NOT THE PAGE CHANGING. The collector stamps a real
      // `mmid` ATTRIBUTE on every interactive element, so without an exclusion
      // an observation would report ITSELF as churn -- worst on the first read
      // of a page, one record per control. That exclusion is by NAME at record
      // time, below.
      //
      // THERE IS DELIBERATELY NO pause()/resume() PAIR. The first version had
      // one and nothing ever called it, which is half a contract (#30, #54,
      // #57, #62) -- and worse, it was reachable from the page, so one call to
      // pause() would have blinded this signal for the life of the document
      // with nothing reporting that it had. An exclusion that cannot be
      // switched off cannot be switched off BY THE PAGE EITHER.
      const t = performance.now();
      // TWO SEPARATE BOUNDS, because the two costs are different by orders of
      // magnitude. FILTERING is one string compare, so every record is
      // inspected; STORING allocates a WeakRef and walks a target, so only the
      // first 32 survivors are kept. Conflating them was a real defect: a single
      // callback carrying 50 mmid stamps skipped 32 in the loop and then added
      // the remaining 18 to the total anyway, so the exclusion leaked at exactly
      // the rate the burst exceeded the prefix.
      // NET-ZERO WITHIN ONE BATCH IS NOT A CHANGE. A MutationObserver callback
      // is a microtask, so one synchronous script's worth of mutations arrives
      // as a single batch -- and `get_page_text` performs a hide-read-restore
      // (set display:none, read innerText, put it back) to strip editor gutters
      // and collapsed subtrees. MEASURED: 12 <details> elements produce 24
      // `style` records whose net effect on the DOM is exactly nothing, so a
      // read_page within the window afterwards reported OUR OWN instrumentation
      // as page activity. That is the same defect the `mmid` exclusion exists to
      // prevent, one attribute over.
      //
      // This is the per-record "a write whose value did not change" rule applied
      // at the right granularity: if an attribute starts a batch at X and ends it
      // at X, nothing changed. It is a FACT about the two values, not a guess
      // about intent — and it correctly also drops a page's own toggle-and-
      // restore within one tick, which likewise leaves the listing untouched.
      let netZero = null;
      for (let i = 0; i < recs.length; i++) {
        const r = recs[i];
        if (r.type !== 'attributes' || !r.target) continue;
        if (!netZero) netZero = new Map();
        let per = netZero.get(r.target);
        if (!per) { per = new Map(); netZero.set(r.target, per); }
        // ONLY the FIRST record's oldValue is needed: the test is whether the
        // attribute ENDS the batch at the value it STARTED with, and the live
        // value supplies the other end. An earlier version also stored `last`
        // and never read it -- a dead field in the block whose own comment
        // cites the both-halves-of-a-contract rule.
        if (!per.has(r.attributeName)) per.set(r.attributeName, r.oldValue);
      }
      if (netZero) {
        for (const [el, per] of netZero) {
          for (const [name, firstOld] of per) {
            let now = null;
            try { now = el.getAttribute(name); } catch (x) {}
            // Unchanged across the whole batch -> drop every record for this
            // (element, attribute) pair, not just the last one.
            per.set(name, now === firstOld);
          }
        }
      }

      let kept = 0;
      for (let i = 0; i < recs.length; i++) {
        const r = recs[i];
        if (r.type === 'attributes' && netZero) {
          const per = netZero.get(r.target);
          if (per && per.get(r.attributeName) === true) continue;
        }
        // `mmid` is OURS, and dropping it HERE rather than at read time is the
        // difference between a clean ring and a useless one: a page with 500
        // controls would otherwise evict half the buffer on its first read.
        // Filtered by name because a stamp can land inside a page script's own
        // microtask ordering, where a pause window would miss it.
        if (r.attributeName === 'mmid') continue;
        // NOTE there is deliberately no SECOND, per-record "did the value
        // change" test here. The batch test above subsumes it and the
        // per-record one is actively WRONG once a pair has more than one
        // record: for class A -> B -> A the records carry oldValue A and B
        // against a current value of A, so a per-record test drops the first
        // and keeps the second -- reporting half of a net-zero change. The
        // batch test compares the current value against the FIRST old value
        // and drops both, which is the only answer that matches what the DOM
        // actually did.
        //
        // The rule itself comes from browser-use's ax.py, whose comment names
        // Google Flights rewriting a class every frame. Their other damping --
        // `style` limited to once per element per 200ms -- is deliberately NOT
        // taken: 200ms is a chosen number, and the kind-split reporting already
        // discriminates, since "40 @style" and "40 structural" read as the
        // opposite facts they are.
        kept++;
        if (kept > 32) continue;   // counted, not stored
        const s = n % CAP;
        ts[s] = t;
        kd[s] = r.type === 'childList' ? (_allText(r) ? 2 : 1)
          : (r.type === 'characterData' ? 2 : 3);
        an[s] = r.attributeName || null;
        // A ShadowRoot HAS NO parentElement, and that made every direct append
        // into one unattributable. A ShadowRoot is a DocumentFragment (nodeType
        // 11) whose `parentNode` is null -- it hangs off `host`, not off a
        // parent -- so the fallback resolved to null, the record was stored with
        // no target, and a SCOPED read could never attribute it. Measured: a
        // read scoped to `main` while a shadow root painted 400 rows directly
        // into itself reported `since=4032, structural=0`, i.e. QUIET, against a
        // true recency of 7ms. That is a FALSE QUIET, which is the worst
        // direction this signal can fail in, on the normal Lit/Shoelace shape.
        // R25 could not see it: its fixture mutates an Element INSIDE the root,
        // whose parentElement resolves fine. Open and closed roots alike (#31's
        // attachShadow wrap is what lets us observe a closed one at all).
        const el = r.target && r.target.nodeType === 1 ? r.target
          : (r.target && (r.target.parentElement || r.target.host || null));
        try { tg[s] = el ? new WeakRef(el) : null; } catch (e) { tg[s] = null; }
        n++; wrote++;
      }
      // A burst beyond the prefix still COUNTS -- losing the count would make a
      // flood look like quiet, which is the direction that misleads.
      if (kept > 32) n += kept - 32;
    };

    // `attributeOldValue` IS REQUIRED, not optional detail: without it every
    // MutationRecord.oldValue is null, so the net-zero test above compares the
    // live value against null, never matches, and the whole exclusion is inert.
    // It was inert when first written, and only measuring it said so — the
    // hide-read-restore still produced its full 24 records.
    const OPTS = { childList: true, subtree: true, characterData: true,
                   attributes: true, attributeOldValue: true };
    try { obs = new MutationObserver(rec); obs.observe(document, OPTS); } catch (e) {}

    // Composed containment: `contains()` stops at a shadow boundary, and the
    // collector walks the composed tree, so the scope test has to as well or a
    // scoped read of a custom element would report its own contents as external.
    const inScope = (el, scope) => {
      let cur = el;
      for (let hops = 0; cur && hops < 200; hops++) {
        if (cur === scope) return true;
        cur = cur.parentNode || (cur.host || null);
        if (cur && cur.nodeType === 11) cur = cur.host || null;
      }
      return false;
    };

    const api = {
      watch(root) { try { if (obs && root) obs.observe(root, OPTS); } catch (e) {} },
      // scope: an Element to restrict to, or null for the whole document.
      // winMs: the window to count within. Returns FACTS, never a verdict.
      query(scope, winMs) {
        const now = performance.now();
        const cut = now - (winMs || 1000);
        // `saturated` means THE RING WRAPPED, so it must count slots WRITTEN.
        // Keying it on `n` was wrong: n also counts records that were
        // inspected and discarded past the 32-per-batch store bound, so one
        // large burst reported a wrapped ring while only 32 slots were used.
        const out = { total: n, saturated: wrote > CAP, since: -1, sinceAny: -1,
                      structural: 0, text: 0, attrs: {}, win: winMs || 1000 };
        const seen = Math.min(n, CAP);
        for (let i = 0; i < seen; i++) {
          const t = ts[i];
          if (!t) continue;
          if (out.sinceAny < 0 || t > out.sinceAny) out.sinceAny = t;
          let hit = true;
          if (scope) {
            const el = tg[i] && tg[i].deref ? tg[i].deref() : null;
            hit = !!el && inScope(el, scope);
          }
          if (!hit) continue;
          if (out.since < 0 || t > out.since) out.since = t;
          if (t < cut) continue;
          if (kd[i] === 1) out.structural++;
          else if (kd[i] === 2) out.text++;
          else { const k = an[i] || 'attr'; out.attrs[k] = (out.attrs[k] || 0) + 1; }
        }
        out.since = out.since < 0 ? -1 : Math.round(now - out.since);
        out.sinceAny = out.sinceAny < 0 ? -1 : Math.round(now - out.sinceAny);
        return out;
      },
    };
    // NON-ENUMERABLE, NON-WRITABLE AND **NON-CONFIGURABLE**. The first version
    // left `configurable: true`, which blocks `window.__abMut = x` and does NOT
    // block `Object.defineProperty(window, '__abMut', …)` -- so any page could
    // substitute a `query()` that always answers "quiet" while repainting, which
    // is the false-quiet direction this whole probe exists to avoid. Measured
    // in a real page: viaAssign false, **viaDefine true**, spoofed reading
    // `{since: 999999, structural: 0}`.
    //
    // The check written for it passed anyway, because it only exercised the
    // ASSIGNMENT path -- a check that cannot fire on the thing its own title
    // asserts. R18 now drives both paths.
    //
    // `configurable: false` is safe here: this runs at document_start before any
    // page script, and the guard above means we never define it twice.
    try {
      Object.defineProperty(window, '__abMut',
        { value: api, enumerable: false, writable: false, configurable: false });
    } catch (e) { /* leave undefined: the probe treats absent as UNKNOWN, never quiet */ }
  } catch (e) {}
})();

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
      // Register the root with the mutation recorder. A MutationObserver on
      // `document` is blind to shadow content, and this wrap is the one place
      // that sees EVERY root the page will ever make, open or closed.
      try { if (window.__abMut) window.__abMut.watch(root); } catch (e) {}
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
