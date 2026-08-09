// DOM-filtration probe — instrumented reimplementation of background.js
// `_collectInteractivePage`. Faithfully reproduces every filter predicate, but
// for EACH interactive candidate records whether it was kept and, if dropped,
// the exact reason. Lets us answer: "does the agent's page view miss real
// navigation targets, and how much noise does it carry?"
//
// Run it by pasting the file body as the `text` of the claude-in-chrome
// javascript_tool (it is one big IIFE expression — the tool returns its value).
//
// NOTE: for a FAITHFUL capture of the agent-facing listing, use
// tools/capture_listings.py, which extracts and runs the REAL
// `_collectInteractivePage` straight from background.js (no divergence risk).
// THIS probe is the drops-WITH-REASONS diagnostic; it reproduces the filter
// predicates but may lag background.js by a round of fixes — treat its drop
// classification as indicative, not authoritative.
(function () {
  const tags_to_ignore = ['head','style','script','link','meta','noscript','template','iframe','g','main','c-wiz','path'];
  const ids_to_ignore = ['agentDriveAutoOverlay'];
  if (typeof window.__mmidCounter !== 'number') window.__mmidCounter = 0;
  document.querySelectorAll('*').forEach(el => {
    const tag = el.tagName.toLowerCase();
    if (tags_to_ignore.includes(tag) || ids_to_ignore.includes(el.id)) return;
    if (el.hasAttribute('mmid')) return;
    el.setAttribute('mmid', `${++window.__mmidCounter}`);
  });

  const _isSemanticTable = (tableEl) => {
    if (!tableEl) return false;
    if (tableEl.querySelector && tableEl.querySelector('thead')) return true;
    if (tableEl.querySelector && tableEl.querySelector('th')) return true;
    const r = tableEl.getAttribute && tableEl.getAttribute('role');
    if (r && ['table','grid','treegrid'].includes(r)) return true;
    return false;
  };
  const section = (el) => {
    let walker = el;
    while (walker && walker !== document.body && walker.tagName) {
      const tag = walker.tagName.toLowerCase();
      const role = walker.getAttribute ? walker.getAttribute('role') : null;
      if (tag === 'thead') { if (_isSemanticTable(walker.parentElement)) return 'table-header'; }
      else if (tag === 'tbody') { if (_isSemanticTable(walker.parentElement)) return 'table-body'; }
      else if (tag === 'table' || role === 'table' || role === 'grid' || role === 'treegrid') {
        if (_isSemanticTable(walker)) return 'table';
      }
      if (tag === 'dialog' || role === 'dialog' || role === 'alertdialog' ||
          (walker.getAttribute && walker.getAttribute('aria-modal') === 'true')) return 'dialog';
      if (tag === 'aside' || role === 'complementary') return 'sidebar';
      if (tag === 'nav'   || role === 'navigation')    return 'nav';
      if (tag === 'header'|| role === 'banner')        return 'header';
      if (tag === 'footer'|| role === 'contentinfo')   return 'footer';
      if (tag === 'main'  || role === 'main')          return 'main';
      if (role === 'tablist' || role === 'tabpanel')   return role;
      if (role === 'menu' || role === 'menubar' || role === 'listbox') return role;
      if (role === 'form' || tag === 'form')           return 'form';
      walker = walker.parentElement;
    }
    return '';
  };

  const vw = window.innerWidth || document.documentElement.clientWidth;
  const vh = window.innerHeight || document.documentElement.clientHeight;

  // isInteractive, but also report WHICH signal matched (to detect cursor-only noise).
  const interactiveReason = (el) => {
    const tag = el.tagName.toLowerCase();
    if (['a','button','input','select','textarea'].includes(tag)) return 'tag';
    const role = el.getAttribute('role');
    if (role && ['button','link','menuitem','menuitemcheckbox','menuitemradio','tab','checkbox','radio','switch','option','combobox','searchbox','textbox'].includes(role)) return 'role';
    if (el.hasAttribute('onclick')) return 'onclick';
    if (el.hasAttribute('tabindex')) return 'tabindex';
    if (el.isContentEditable) return 'contenteditable';
    try { if (getComputedStyle(el).cursor === 'pointer') return 'cursor'; } catch (e) {}
    return null;
  };

  const decorativeTags = new Set(['svg','rect','path','circle','polyline','polygon','line','ellipse','g','use','defs','symbol']);
  const formyTags = new Set(['input','textarea','select']);
  const CONTAINER_ROLES = new Set(['menu','menubar','listbox','dialog','alertdialog','tablist','tabpanel','grid','treegrid','tree','radiogroup','group','toolbar','region']);
  const strongInteractiveRoles = new Set(['button','link','tab','menuitem','menuitemcheckbox','menuitemradio','checkbox','radio','switch','combobox','option']);
  const synthLabel = (el) => { try { const st = el.querySelector('svg title, title'); if (st && (st.textContent||'').trim()) return st.textContent.trim().slice(0,40); const al = el.querySelector('svg[aria-label],[aria-label]'); if (al) { const a=(al.getAttribute('aria-label')||'').trim(); if(a) return a.slice(0,40); } const img = el.querySelector('img[alt]'); if (img){const a=(img.getAttribute('alt')||'').trim(); if(a) return a.slice(0,40);} for (const at of ['data-testid','data-test-id','data-test','data-tooltip','data-label','data-icon','data-action','data-key']){const v=(el.getAttribute(at)||'').trim(); if(v) return v.replace(/[-_]+/g,' ').slice(0,40);} const ct=el.querySelector('[title]'); if(ct){const t=(ct.getAttribute('title')||'').trim(); if(t) return t.slice(0,40);} } catch(e){} return ''; };

  const addedMmids = new Set();
  const out = [];
  const dropped = [];
  const drop = (el, reason, extra) => {
    const r = el.getBoundingClientRect();
    dropped.push(Object.assign({
      mmid: el.getAttribute('mmid'), tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || null,
      text: ((el.innerText || el.textContent || '').trim().replace(/\s+/g,' ')).slice(0, 50),
      ariaLabel: el.getAttribute('aria-label') || null,
      reason, box: { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) },
    }, extra || {}));
  };

  document.querySelectorAll('[mmid]').forEach(el => {
    const ir = interactiveReason(el);
    if (!ir) return;                       // not an interactive candidate at all
    const tagL = el.tagName.toLowerCase();

    if (decorativeTags.has(tagL)) {
      const rr = el.getAttribute('role');
      if (!rr || !['button','link','tab','menuitem','checkbox','radio','combobox','option','menuitemcheckbox','menuitemradio'].includes(rr)) { drop(el, 'decorative-svg', {via: ir}); return; }
    }
    if (el.getAttribute('aria-hidden') === 'true') { drop(el, 'aria-hidden', {via: ir}); return; }

    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const visible = r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' &&
                    cs.display !== 'none' && parseFloat(cs.opacity || '1') > 0;
    const inViewport = r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw;
    let inModal = false;
    { let w = el;
      while (w && w !== document.body && w.tagName) {
        const t = w.tagName.toLowerCase();
        const ro = w.getAttribute ? w.getAttribute('role') : null;
        if (t === 'dialog' || ro === 'dialog' || ro === 'alertdialog' ||
            (w.getAttribute && w.getAttribute('aria-modal') === 'true')) { inModal = true; break; }
        w = w.parentElement;
      } }
    if (!visible) { drop(el, 'invisible', {via: ir}); return; }
    if (!inViewport && !inModal) { drop(el, 'offscreen', {via: ir}); return; }
    if (r.width < 8 || r.height < 8) { if (!formyTags.has(tagL)) { drop(el, 'tiny', {via: ir}); return; } }

    let clickable = true;
    if (inViewport) {
      const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      try { const topEl = document.elementFromPoint(cx, cy);
        clickable = !!(topEl && (topEl === el || el.contains(topEl) || topEl.contains(el))); } catch (e) {}
    }

    // accessibleName (AccName, simplified)
    let accessibleName = '';
    try {
      const ariaLabelledBy = el.getAttribute('aria-labelledby');
      if (ariaLabelledBy) accessibleName = ariaLabelledBy.split(/\s+/).map(id => { const n = document.getElementById(id); return n ? (n.innerText || '').trim() : ''; }).filter(Boolean).join(' ');
      if (!accessibleName) accessibleName = (el.getAttribute('aria-label') || '').trim();
      if (!accessibleName && el.id) { const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (lab) accessibleName = (lab.innerText || '').trim(); }
      if (!accessibleName) { const wrap = el.closest && el.closest('label'); if (wrap) accessibleName = (wrap.innerText || '').trim(); }
      if (!accessibleName) accessibleName = (el.getAttribute('name') || el.getAttribute('title') || el.getAttribute('alt') || '').trim();
    } catch (e) {}
    accessibleName = accessibleName.replace(/\s+/g, ' ').replace(/\s*\*\s*$/, '').slice(0, 60);
    const placeholderAttr = (el.getAttribute('placeholder') || '').trim().slice(0, 50);
    const currentValue = (() => { try {
      if (tagL === 'input' || tagL === 'textarea') return (el.value || '').trim().slice(0, 60);
      if (tagL === 'select') { const o = el.options && el.options[el.selectedIndex]; return o ? (o.text || '').trim().slice(0, 60) : ''; }
      if (el.getAttribute('role') === 'combobox') { const t = (el.innerText || '').trim(); if (/^(select|choose|pick)\b/i.test(t) || /\.\.\.$|…$/.test(t)) return ''; return t.slice(0, 60); }
      return ''; } catch (e) { return ''; } })();
    const buttonText = !formyTags.has(tagL) ? (el.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 60) : '';
    let label = accessibleName || currentValue || placeholderAttr || buttonText;
    label = label.replace(/\s+/g, ' ').slice(0, 60);

    // Mirrors background.js: strong-interactive no-label controls are rescued
    // (synth label or kept as iconOnly); only generic no-label noise is dropped.
    let iconOnly = false;
    if (!label && !formyTags.has(tagL)) {
      const _r = el.getAttribute('role');
      const isStrong = (tagL === 'a' || tagL === 'button') || (_r && strongInteractiveRoles.has(_r));
      if (isStrong) { label = synthLabel(el); iconOnly = !label; }
      else { drop(el, 'no-label', {via: ir}); return; }
    }

    if (label) {
      let walker = el.parentElement, skip = false, skipParent = null;
      while (walker && walker !== document.body) {
        const pMmid = walker.getAttribute && walker.getAttribute('mmid');
        if (pMmid && addedMmids.has(pMmid)) {
          const parentEntry = out.find(o => o.mmid === pMmid);
          if (parentEntry && parentEntry.label === label) {
            const parentRole = parentEntry.role || '', parentTag = parentEntry.tag || '';
            const isContainer = CONTAINER_ROLES.has(parentRole) || ['dialog','ul','ol','table','form','fieldset','section'].includes(parentTag);
            if (!isContainer) { skip = true; skipParent = pMmid; break; }
          }
        }
        walker = walker.parentElement;
      }
      if (skip) { drop(el, 'dedup', {via: ir, parentMmid: skipParent}); return; }
    }

    const _mmid = el.getAttribute('mmid');
    addedMmids.add(_mmid);
    let active = ''; try { const ac = el.getAttribute('aria-current'); if (ac && ac !== 'false') active='current'; else if (el.getAttribute('aria-selected')==='true') active='selected'; else if (el.getAttribute('aria-pressed')==='true') active='pressed'; else if (el.getAttribute('aria-expanded')==='true') active='expanded'; else { const ds=el.getAttribute('data-state'); if(['active','open','on','checked'].includes(ds)) active=ds; } } catch(e){}
    let required = false; try { if (el.getAttribute('aria-required')==='true'||el.hasAttribute('required')) required=true; else if (el.closest&&el.closest('[aria-required="true"]')) required=true; } catch(e){}
    let unselected = false; try { const isCombo = el.getAttribute('role')==='combobox'||tagL==='select'||el.getAttribute('aria-haspopup')==='listbox'; if(isCombo){ if(tagL==='select'){unselected=el.selectedIndex<0||!el.options[el.selectedIndex]||!(el.options[el.selectedIndex].value||'').trim();} else {const tt=(el.innerText||'').trim(); if(!tt||/^(select|choose|pick)\b/i.test(tt)||/\.\.\.$|…$/.test(tt)) unselected=true;} } } catch(e){}
    out.push({ mmid: _mmid, tag: tagL, type: el.getAttribute('type'), role: el.getAttribute('role'),
      section: section(el), label, name: accessibleName, placeholder: placeholderAttr,
      value: currentValue, text: buttonText, clickable, via: ir, iconOnly, active, required, unselected,
      x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height),
      offscreen: !inViewport });
  });

  // ----- analysis ---------------------------------------------------------
  const byReason = {};
  dropped.forEach(d => { byReason[d.reason] = (byReason[d.reason] || 0) + 1; });

  // Drops that LOOK like real navigation targets (have text/label/aria or are a real control).
  const suspiciousDrops = dropped.filter(d =>
    (d.text && d.text.length > 0) || d.ariaLabel ||
    ['a','button','input','select','textarea'].includes(d.tag) ||
    (d.role && ['button','link','tab','menuitem','checkbox','radio','combobox','option'].includes(d.role))
  ).filter(d => d.reason !== 'offscreen');  // offscreen is by-design (no scroll-find)

  // Kept elements that qualified ONLY via cursor:pointer (most likely noise).
  const cursorOnlyKept = out.filter(e => e.via === 'cursor');

  // ----- faithful agent-facing listing (mirrors background.js formatter) ----
  const dialogOpen = out.some(e => e.section === 'dialog');
  const url = location.pathname + (location.search || '');
  out.sort((a,b) => (a.y - b.y) || (a.x - b.x));
  const LISTING_CAP = 150;
  let shown = out, hiddenCount = 0;
  if (out.length > LISTING_CAP) {
    const isP = (e) => e.section === 'dialog' || e.required || e.unselected || formyTags.has(e.tag);
    const pri = out.filter(isP), rest = out.filter(e => !isP(e));
    shown = pri.concat(rest.slice(0, Math.max(0, LISTING_CAP - pri.length)));
    shown.sort((a,b) => (a.y - b.y) || (a.x - b.x));
    hiddenCount = out.length - shown.length;
  }
  const truncNote = hiddenCount > 0 ? `\n... +${hiddenCount} more interactive element(s) not shown (listing capped at ${LISTING_CAP}; all dialog / required / dropdown / input fields ARE shown).` : '';
  const lines = shown.map(e => {
    const tagtype = (e.type && !(e.tag === 'button' && e.type === 'button')) ? `${e.tag}[${e.type}]` : e.tag;
    let identity = '';
    if (e.name) identity += ` name=${JSON.stringify(e.name)}`;
    if (e.value) identity += ` value=${JSON.stringify(e.value)}`;
    if (e.placeholder) identity += ` placeholder=${JSON.stringify(e.placeholder)}`;
    if (!identity && e.text) identity = ` "${e.text}"`;
    if (!identity && e.iconOnly) identity = " (icon button — no text label)";
    else if (!identity && e.label) identity = ` "${e.label}"`;
    const act = e.active ? ` (${e.active})` : "", rl = (e.role && e.role !== e.tag) ? ` role=${e.role}` : "";
    const sec = e.section ? ` section=${e.section}` : "", req = e.required ? " (required)" : "", uns = e.unselected ? " (unselected)" : "";
    const occ = e.clickable === false ? " (occluded/blocked)" : "", off = e.offscreen ? " (below-fold)" : "";
    return `mmid=${e.mmid} | ${tagtype}${identity}${act}${rl}${sec}${req}${uns} | box(${e.x},${e.y},${e.w},${e.h})${occ}${off}`;
  });
  const banner = dialogOpen ? "*** A MODAL/DIALOG IS CURRENTLY OPEN — focus on section=dialog. ***\n" : "";
  const listing = `Current URL: ${url}\n` + banner + `Visible interactive elements (${out.length} on screen).\n` + lines.join('\n') + truncNote;

  return {
    url: location.href, viewport: { w: vw, h: vh },
    totals: { allEls: document.querySelectorAll('*').length, candidates: out.length + dropped.length, kept: out.length, dropped: dropped.length },
    over150: out.length > 150, hiddenByCap: hiddenCount, dropReasons: byReason,
    suspiciousDropCount: suspiciousDrops.length,
    listing,
  };
})()
