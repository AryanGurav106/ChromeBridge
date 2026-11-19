"""Is the name we PRINT the RIGHT name for that element? Our AccName against Chrome's.

WHY THIS EXISTS, AND WHY IT IS THE ONE QUESTION NOTHING HERE ANSWERS.
`audit_stage_generality` (#89) measures whether a control SURVIVES -- 0 identities lost
across 255 live sites, four compounding interactions deep. `measure_findability_at_stage`
(#92) measures whether it can be REACHED by the identity the listing printed -- 13,682
probes, 0 misses. Both score our collector against OUR OWN tools, and #92 says so in as
many words: it scores `find` against the collector, so **a wrong name that both agree on
scores a hit**. Neither can see a name that is simply wrong.

The only independent oracle in the project is #33's `accessible_names`: Chrome implements
AccName itself and will hand over its result over CDP. It has been run ONCE, on one page,
at first paint -- 49 of 54 agreed. That is n=1 page and no post-interaction evidence at
all, which is exactly the regime #89/#92 showed matters (a menu is open, a listbox is
rendered in a portal, a field holds typed text).

WHAT IS REUSED, NOT REWRITTEN (PRINCIPLES 17; #36 recorded a restated copy drifting):
  * the interaction DRIVER -- `audit_stage_generality.STAGE_PICK` / `_act` /
    `STAGE_VERIFY` / `MAX_PER_KIND` / `SETTLE_MS`, declarations only, counted only when
    the page's own declared state flipped;
  * the SAMPLE and the out-of-sample guard -- `audit_generality_live.SITES`/`SITES2`,
    `EXCLUDED` (frozen corpus + bench_turns + bench_flows), `VIEWPORT`, `TAG_JS`,
    `SCRIPT_OF`, and `audit_stage_generality._usable85`;
  * the COLLECTOR -- `audit_generality_live.COLLECT`, extracted verbatim from
    extension/background.js, so a disagreement is a disagreement about the shipped code.

WHAT IS NEW: the ORACLE SIDE, which is #33's `axNamesFor` reproduced over a Playwright CDP
session rather than over the extension's debugger. `DOM.enable` AND `Accessibility.enable`
first -- #34 records that `getFullAXTree` returns an EMPTY node list, not an error, without
them, and that this looked exactly like "this page has no accessible names". The join is by
`backendNodeId` from ONE `DOM.getDocument{depth:-1, pierce:true}`; a `DOM.resolveNode` per
node is a round trip each and unusable at a few hundred elements.

WHAT "OUR NAME" MEANS HERE. The row's IDENTITY as `_fmtLine` builds it: `name=` when the
collector resolved one, else the element's own text (or the label when the label strictly
contains the text and is longer -- the icon+badge rule). A row whose identity the collector
BLANKS on purpose (`subtreeName && !subtreeNameSole`, #74's rule) poses no question and is
counted in its own bucket, never in the agreement denominator -- the same split #92 makes.
`ours_identity` is a 12-line restatement of that precedence, so it is checked against
`e.line` on every single row and `fmt_drift` is reported; a non-zero there means the
restatement has drifted from the code and the numbers are void.

CHROME IS NOT AUTOMATICALLY RIGHT. #28 found Chrome concatenating sibling element children
with no separator (a wrong NUMBER in the identity slot); #37 found `title` and the HTML
`name` attribute mis-ordered, by reading the spec. So every disagreement class is given a
verdict with the spec rule named (AccName 1.2 / HTML-AAM), and "undecidable" is an allowed
answer.

PROVING THE COMPARATOR CAN FIRE (PRINCIPLES 11, 15). A high agreement rate from a
comparison nobody has seen disagree is worth nothing. Two arms:
  * `--selftest` plants markup where the two derivations genuinely differ by spec
    interpretation, plus a CONTROL that must agree, plus a PLANTED arm that moves an
    element's `aria-label` after collection so the join-and-compare path is proven end to
    end independently of what the collector happens to do;
  * `--fire` does the planted arm on LIVE pages at the deepest stage reached, because a
    fixture is what you thought of.

A/B-ING A CANDIDATE FIX. `--candidate-ab` runs BOTH collectors on the SAME page load and
scores them against ONE oracle read, so run-order drift cannot align with the arm (R3) and
the oracle cannot move between them. It reports MOVEMENT rather than a level: `improved`,
`regressed`, and the one number that would stop a change -- `BREAKS_A_CORRECT_NAME`, a row
where Chrome HAS a name, we had it right, and the candidate breaks it. It also grades the
BENEFIT, which a rate cannot show: every row that GAINS an identity is bucketed by where
that name was in the BASE listing -- `inside` the control (a click bubbles, so the cost
today is low), `elsewhere` (attributed to the wrong control), or `nowhere` (the only
outright loss, and #74's defect class). Both halves in one pass is what #41/#44 require.

A ZERO FROM `BREAKS_A_CORRECT_NAME` IS ONLY WORTH SOMETHING ONCE IT HAS FIRED
(PRINCIPLES 15). Two sabotage candidates exist for that and are never shipped;
`sabotage-drop-name-arialabel` is the one that lands in the compared population.

Run:  python tools/audit_name_correctness.py --selftest
      python tools/audit_name_correctness.py --fire --only gov_au leg_perldoc
      python tools/audit_name_correctness.py --pool usable85 --conc 6 --stages 4
      python tools/audit_name_correctness.py --compare --only ...     # drift floor
      python tools/audit_name_correctness.py --report temp/name_correctness/main/pass0.json
      python tools/audit_name_correctness.py --candidate-ab --ab-only child-declared-name \
             --ab-arm guarded --conc 5 --stages 4 --out temp/accname2f/guarded
      python tools/audit_name_correctness.py --candidate-ab \
             --ab-only sabotage-drop-name-arialabel --every 9    # the counter fires

Findings: docs/research/NAME-CORRECTNESS-2026-11.md
"""
import argparse
import asyncio
import collections
import json
import re
import statistics
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from playwright.async_api import async_playwright  # noqa: E402
import audit_generality_live as AGL  # noqa: E402  (sample, exclusions, collector)
import audit_stage_generality as ASG  # noqa: E402  (the interaction driver)
# THE HOVER DRIVER, REUSED RATHER THAN RESTATED (PRINCIPLES 17). #94 built the picker,
# the before/after element-identity diff and the did-the-hover-survive check, and #117
# named "name correctness on hover-revealed content" as a gap because THIS probe has no
# hover arm -- not because that driver was missing. Writing a third picker here is the
# failure #36 and #37 both record, and #117 found an instance of it this week.
import audit_hover_stage as AHS  # noqa: E402  (HOVER_PICK / HOVER_DIFF / APPEARED_MMIDS)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VIEWPORT = AGL.VIEWPORT
TAG_JS = AGL.TAG_JS
GOTO_MS = ASG.GOTO_MS
OUT = ROOT / "temp" / "name_correctness"
PLANT = "ZZQPLANTEDNAME"          # no page contains this; see _plant


# --------------------------------------------------------------------------------------
# OUR SIDE. One evaluate: the real collector (structured), plus the DECLARATIONS each
# element carries, so a disagreement can be grouped by what the page actually said rather
# than by a story about it.
# --------------------------------------------------------------------------------------
DECLS_JS = r"""
(function () {
  const out = {};
  let budget = 4000;
  function walk(root, depth) {
    let all; try { all = root.querySelectorAll('[mmid]'); } catch (e) { return; }
    for (const el of all) {
      if (--budget < 0) return;
      const mm = el.getAttribute('mmid');
      if (!mm || out[mm]) continue;
      let ownText = '';
      try {
        for (const n of el.childNodes) if (n.nodeType === 3) ownText += (n.nodeValue || '');
      } catch (e) {}
      // Does any ELEMENT child render as a block? That is the documented reason Chrome
      // joins some children with a space and others without, and it is the evidence the
      // separator class needs (AccName 1.2 step 2F / HTML-AAM).
      let blockChild = false, elemChildren = 0;
      try {
        for (const c of el.children) {
          elemChildren++;
          const d = getComputedStyle(c).display;
          if (d && d !== 'inline' && d !== 'contents' && d !== 'none') blockChild = true;
        }
      } catch (e) {}
      let labelled = 0;
      try { labelled = (el.labels && el.labels.length) || 0; } catch (e) {}
      out[mm] = {
        ariaLabel: el.getAttribute('aria-label') || '',
        ariaLabelledby: el.getAttribute('aria-labelledby') || '',
        ariaDescribedby: el.getAttribute('aria-describedby') || '',
        title: el.getAttribute('title') || '',
        alt: el.getAttribute('alt') || '',
        nameAttr: el.getAttribute('name') || '',
        placeholder: el.getAttribute('placeholder') || '',
        valueAttr: el.getAttribute('value') || '',
        roleAttr: el.getAttribute('role') || '',
        typeAttr: el.getAttribute('type') || '',
        ownText: ownText.replace(/\s+/g, ' ').trim().slice(0, 120),
        blockChild: blockChild, elemChildren: elemChildren, labels: labelled,
        html: (el.outerHTML || '').replace(/\s+/g, ' ').slice(0, 260),
      };
    }
    if (depth > 6) return;
    let every; try { every = root.querySelectorAll('*'); } catch (e) { return; }
    let b = 6000;
    for (const e of every) {
      if (--b < 0) break;
      const sr = e.shadowRoot || e.__abClosedRoot;
      if (sr) walk(sr, depth + 1);
      if (e.tagName === 'IFRAME') { try { const d = e.contentDocument; if (d) walk(d, depth + 1); } catch (x) {} }
    }
  }
  walk(document, 0);
  return out;
})()
"""


# --------------------------------------------------------------------------------------
# THE CANDIDATE ARM. Two one-line diffs, applied to the EXTRACTED collector so the before
# and after are both reproducible from the repo without touching extension/.
#
# MEASUREMENT.md's rule for a probe that patches source: construct the arm that does NOT
# exist yet, and assert the anchor so the patch cannot silently match nothing and measure
# a build nobody runs. Both anchors are asserted at module import of this arm.
CANDIDATES = [
    (
        "alt-before-title",
        # HTML-AAM maps `alt` to AccName 1.2 step 2E (host-language label) and `title` to
        # step 2I (tooltip), whose own note says a tooltip is used "only if nothing else,
        # including subtree content, has provided results". Reading them the other way
        # round named 21 oebb images after the photographer's copyright credit.
        r"el\.getAttribute\('title'\) \|\| el\.getAttribute\('alt'\)",   # WITHOUT the fix
        r"el\.getAttribute\('alt'\) \|\| el\.getAttribute\('title'\)",   # WITH the fix
        "el.getAttribute('title') || el.getAttribute('alt')",
        "el.getAttribute('alt') || el.getAttribute('title')",
    ),
    (
        "contents-is-not-invisible",
        # `display: contents` generates NO BOX, so checkVisibility() is false for it while
        # its CHILDREN render normally -- and a <slot> is display:contents by default, so
        # this rejected every slot before _deepText's slot branch (which exists exactly to
        # resolve assignedNodes) could ever be reached. `visibility` is still asked,
        # because visibility IS inherited and does hide the children.
        #
        # THE "WITH THE FIX" SIDE IS A REGEX, not my exact text. The shipped version is
        # worded and laid out differently from the one this probe proposed, and matching my
        # own spelling silently failed to detect it -- so the reverse arm returned the
        # SHIPPED collector while calling itself the baseline, and the forward arm would
        # have inserted a second copy of the rule. Detect the SHAPE, not the prose.
        r"^(?P<i>[ \t]*)if \(n\.checkVisibility && !n\.checkVisibility\(\{ visibilityProperty: true \}\)\) return false;",
        r"^[ \t]*let _disp = '';?[^\n]*\n(?:.*\n)*?[ \t]*if \(_disp === 'contents'\) \{\n(?:.*\n)*?[ \t]*\}\n",
        None,
        None,
    ),
    (
        # A WRAPPING <label>'S NAME WAS COMPUTED ON A DETACHED CLONE.
        #
        # The clone exists to implement AccName's "the labelled control's own subtree is
        # not traversed". But `_contentName` applies `_namable` to every element child,
        # and `_namable` asks `checkVisibility()` -- which a DETACHED node fails, because
        # it has no box. Measured on a clone: `checkVisibility({visibilityProperty:true})`
        # is false for a plainly-visible <span> and `getComputedStyle(n).display` comes
        # back "". So only the label's DIRECT TEXT NODES survived, and
        # `<label><input><span>Text</span></label>` -- the ordinary way to style a radio
        # or checkbox label -- resolved to '' and fell through to the HTML `name`
        # attribute, which is the POST KEY and shared by every member of a radio group.
        #
        # Excluding the control by IDENTITY on the LIVE tree is what the spec rule
        # actually says, and it keeps `_namable` asking its real question of real nodes.
        # Several anchors, applied as one unit: this is a single behavioural change.
        "live-label-not-clone",
        None,
        None,
        [
            "  const _deepText = (node, depth) => {\n    const d = depth || 0;\n"
            "    if (d > 6) return '';\n    try {\n"
            "      if (node.nodeType === 3) return node.nodeValue || '';",
            "  const _contentName = (node) => {",
            "        const _own = _deepText(node).replace(/\\s+/g, ' ').trim();",
            "          // See `_namable`: a non-rendered child contributes nothing, and its\n"
            "          // innerText is NOT what is on screen \u2014 it is textContent.\n"
            "          if (!_namable(n)) continue;",
            "          let t = (typeof n.innerText === 'string') ? n.innerText : _deepText(n);",
            "            const _d = _deepText(n);",
            "          try {\n"
            "            const clone = wrap.cloneNode(true);\n"
            "            const ownMmid = el.getAttribute('mmid');\n"
            "            const own = ownMmid && clone.querySelector(`[mmid=\"${ownMmid}\"]`);\n"
            "            if (own) own.remove();\n"
            "            else { const sameTag = clone.querySelector(el.tagName.toLowerCase()); if (sameTag) sameTag.remove(); }\n"
            "            accessibleName = _contentName(clone);\n"
            "          } catch (e) {\n"
            "            accessibleName = (wrap.innerText || '').trim();\n"
            "          }",
        ],
        [
            "  const _deepText = (node, depth, skip) => {\n    const d = depth || 0;\n"
            "    if (d > 6) return '';\n    try {\n"
            "      if (skip && node === skip) return '';\n"
            "      if (node.nodeType === 3) return node.nodeValue || '';",
            "  const _contentName = (node, skip) => {",
            "        const _own = _deepText(node, 0, skip).replace(/\\s+/g, ' ').trim();",
            "          // The excluded control, skipped by IDENTITY on the LIVE tree.\n"
            "          if (skip && n === skip) continue;\n"
            "          // See `_namable`: a non-rendered child contributes nothing, and its\n"
            "          // innerText is NOT what is on screen \u2014 it is textContent.\n"
            "          if (!_namable(n)) continue;",
            "          let t;\n"
            "          if (skip && n.contains && n.contains(skip)) {\n"
            "            // innerText cannot omit a descendant; the composed walk can.\n"
            "            t = _deepText(n, 0, skip);\n"
            "          } else {\n"
            "            t = (typeof n.innerText === 'string') ? n.innerText : _deepText(n, 0, skip);\n"
            "          }",
            "            const _d = _deepText(n, 0, skip);",
            "          try {\n"
            "            accessibleName = _contentName(wrap, el);\n"
            "          } catch (e) {\n"
            "            accessibleName = (wrap.innerText || '').trim();\n"
            "          }",
        ],
    ),
    (
        # `aria-labelledby` RESOLVED WITH `innerText`, WHICH AN SVG ELEMENT DOES NOT HAVE.
        #
        # #37 established this for `_contentName` -- "an SVG element has no innerText at
        # all, so the name path fell through to textContent and swallowed the stylesheet"
        # -- and fixed it THERE. The aria-labelledby resolver is the same question in a
        # second spelling (PRINCIPLES 17) and was left behind. Measured offline against
        # the shipped collector:
        #     <a><svg aria-labelledby=d><desc id=d>handshake icon</desc></svg></a>
        #       ours   (unlabeled-icon)        chrome   "handshake icon"
        # 40 rows on one live site, all of them a design system's icon set. The row
        # prints NO identity for a control the page named, which is the worst direction.
        #
        # `textContent` and NOT `_deepText`, for a reason the fixture pins: AccName 1.2
        # step 2A excludes a hidden node UNLESS it is DIRECTLY REFERENCED, and an
        # `aria-labelledby` target is directly referenced. `_deepText` applies `_namable`,
        # and an SVG <desc>/<title> is `checkVisibility() === false` -- so the composed
        # walk returns '' and the fix would not work. The HTML branch is untouched, which
        # is what keeps `<button aria-labelledby=hidden-span>` working.
        "labelledby-non-html",
        None,
        None,
        ["          .map(id => { const n = idRoot.getElementById(id); return n ? "
         "(n.innerText || '').trim() : ''; })"],
        ["          .map(id => { const n = idRoot.getElementById(id); return n ? "
         "((typeof n.innerText === 'string' ? n.innerText : n.textContent) || '').trim() : ''; })"],
    ),
    (
        # A <br> RENDERS A LINE BREAK AND CONTRIBUTES NOTHING, so the two runs either
        # side FUSE.  `document.querySelector('br').innerText === ''`, measured.
        #
        # This is #52's defect in a second function. #52 fixed `search_page`'s walk for
        # exactly this -- "<br> has no children, so walk() returned '' and add() dropped
        # it -- FUSING the lines" -- and `_contentName` has the identical hole. The screen
        # oracle settles it: `innerText` of the element is
        # "3420 Walnut Street\nPhiladelphia, PA 19104-6206", Chrome's name has the
        # separator, and ours is "3420 Walnut StreetPhiladelphia, PA 19104-6206".
        #
        # `'\n'` rather than `' '` because that is what a <br> IS; `parts.join('')` is
        # `\s+`-collapsed immediately afterwards, so the name slot gets a space either
        # way. _deepText gets the same line because it answers the same question for the
        # composed/shadow path.
        "br-is-a-separator",
        None,
        None,
        [
            "      if (!_namable(node)) return '';\n      let s = '';\n"
            "      const sr = node.shadowRoot || node.__abClosedRoot;",
            "          if (!_namable(n)) continue;\n          // \"EMPTY\" IS THE WRONG TRIGGER.",
        ],
        [
            "      if (!_namable(node)) return '';\n"
            "      // A <br> renders a line break and has no text -- see `_contentName`.\n"
            "      if (node.tagName === 'BR') return '\\n';\n"
            "      let s = '';\n"
            "      const sr = node.shadowRoot || node.__abClosedRoot;",
            "          if (!_namable(n)) continue;\n"
            "          // A <br> RENDERS A LINE BREAK AND CONTRIBUTES NO TEXT.\n"
            "          // `document.querySelector('br').innerText === ''` (measured), so it\n"
            "          // was dropped by the `if (t.trim())` gate below and the two runs\n"
            "          // either side FUSED: `3420 Walnut Street<br>Philadelphia` came back\n"
            "          // as one word. #52's defect in a second function -- it fixed\n"
            "          // `search_page`'s walk for exactly this. The screen settles it: the\n"
            "          // element's own innerText and Chrome's accessible name both carry\n"
            "          // the break. `'\\n'` rather than `' '` because that is what a <br>\n"
            "          // IS; the join below collapses it, so the name gets a space anyway.\n"
            "          if (n.tagName === 'BR') { parts.push('\\n'); continue; }\n"
            "          // \"EMPTY\" IS THE WRONG TRIGGER.",
        ],
    ),
]

_CONTENTS_BLOCK = (
    "      let _disp = ''; try { _disp = getComputedStyle(n).display; } catch (e) {}\n"
    "      if (_disp === 'contents') {\n"
    "        try { return getComputedStyle(n).visibility !== 'hidden'; } catch (e) { return true; }\n"
    "      }\n")


# --------------------------------------------------------------------------------------
# ACCNAME 2F TAKES EACH CHILD'S *NAME*; `_contentName` TAKES ITS *TEXT*.  (#34, #115)
#
# For almost all markup those are the same string, which is why this survived from the
# first commit. They come apart when a child's identity is an ATTRIBUTE and it renders no
# text -- an icon. Reproduced live against the shipped collector before anything was
# written:
#
#     <wa-button>                                   <- host, LIGHT dom
#       <wa-icon aria-label="Search"></wa-icon>
#     shadowRoot:
#       <button part="base"><slot></slot></button>  <- the row we print
#
#       btn.innerText                  ''
#       btn.textContent                ''
#       btn.querySelector('[aria-label]')   FALSE      <- synthLabel's rescue, see below
#       slot.assignedNodes({flatten:true})  [WA-ICON[aria-label=Search]]
#       ours  `button (unlabeled)`     chrome  "Search"
#
# THE MECHANISM IS NARROWER THAN "WE TAKE TEXT", and measuring it is what showed that.
# `synthLabel` ALREADY rescues an icon-only control by `querySelector('[aria-label]')`,
# which is why `<button><span aria-label=Search></span></button>` prints "Search" today.
# A `querySelector` does not cross a SLOT boundary, and `_deepText` -- which does cross it
# -- is looking for text, of which an icon has none. So what is missing is exactly: a
# node that contributes no TEXT may still DECLARE a name, and the composed tree is where
# to look for it.
#
# NO RECURSION, THEREFORE NO DEPTH BOUND. Measured on a three-deep slot-forwarding chain
# (x-outer -> x-mid -> x-inner): `assignedNodes({flatten:true})` returns the FINAL
# assigned node and never a slot, so this reads attributes off nodes one hop away and
# there is no cycle to close. A chosen depth number would have been an argument against
# the fix; there is none to choose.
#
# A CHILD THAT IS ITSELF A DECLARED CONTROL IS NOT ITS CONTAINER'S LABEL -- the `guarded`
# arm, and a deliberate divergence from AccName, which recurses into controls too and is
# why Chrome names `<a>Read the report <button aria-label="Dismiss this card">x</button></a>`
# "Read the report Dismiss this card". This codebase has already decided that question
# once, in `synthLabel`: *"A PARENT HOLDING A SECOND CONTROL IS A GROUP, AND ITS TEXT
# LABELS THE GROUP, NOT THIS CONTROL"* -- measured live in eval 7 on a quantity stepper
# where both buttons came back named after the QUANTITY. Using the same rule here is
# PRINCIPLES 17 rather than a new judgement; the guard sits INSIDE `_declName` so it
# applies to a slot-assigned node and a direct child in one spelling.
_DECL_CTL_GUARD = (
    "      if (_DECL_CTL_TAG[n.tagName] || _roleHit(n.getAttribute('role'))) return '';\n")
_DECL_CTL_TAGS = (
    "  const _DECL_CTL_TAG = { A: 1, BUTTON: 1, INPUT: 1, SELECT: 1, TEXTAREA: 1, SUMMARY: 1 };\n")

#
# ACCNAME STEP 2A: A HIDDEN NODE CONTRIBUTES NOTHING, AND `aria-hidden="true"` IS HIDDEN.
# `_namable` asks the RENDERING question (`checkVisibility`), which an `aria-hidden` icon
# passes -- it is painted, it is just declared absent from the accessibility tree. Found
# by the one counter that would stop this change: `BREAKS_A_CORRECT_NAME` read 5, all of
# them one element on one site, and reading the live markup rather than guessing gave
#     <i aria-label="icon: search" class="anticon anticon-search" aria-hidden="true">
# inside the <label> of a search field, so the field's name became
# "Search Keyword(s) icon: search" where Chrome says "Search Keyword(s)". Ant Design's
# `anticon` ships `aria-label` and `aria-hidden` on the SAME element, so this is a whole
# library's idiom rather than one page's mistake.
#
# The node's OWN attribute is enough and an ancestor walk is not needed, because the only
# descent this helper makes is through a <slot>, and the slot branch re-enters here -- so
# every node whose attributes are read has been through this test.
_DECLNAME_DEF = (
    "  const _declName = (n) => {\n"
    "    try {\n"
    "      if (!n || n.nodeType !== 1) return '';\n"
    "      if (n.getAttribute('aria-hidden') === 'true') return '';\n"
    "      if (n.tagName === 'SLOT' && n.assignedNodes) {\n"
    "        let s = '';\n"
    "        for (const a of (n.assignedNodes({ flatten: true }) || [])) {\n"
    "          if (!a || a.nodeType !== 1 || !_namable(a)) continue;\n"
    "          const d = _declName(a);\n"
    "          if (d) s = s ? s + ' ' + d : d;\n"
    "        }\n"
    "        return s;\n"
    "      }\n"
    "      const lb = n.getAttribute('aria-labelledby');\n"
    "      if (lb) {\n"
    "        const r = (n.getRootNode && n.getRootNode().getElementById) ? n.getRootNode() : document;\n"
    "        const s = lb.split(/\\s+/)\n"
    "          .map((id) => { const q = r.getElementById(id); return q ? ((typeof q.innerText === 'string' ? q.innerText : q.textContent) || '').trim() : ''; })\n"
    "          .filter(Boolean).join(' ');\n"
    "        if (s) return s;\n"
    "      }\n"
    "      return (n.getAttribute('aria-label') || '').trim();\n"
    "    } catch (e) { return ''; }\n"
    "  };\n")

# ONLY WHEN THE CHILD CONTRIBUTES NO TEXT -- the NARROW arm, and the one proposed.
_DECLNAME_NARROW = (
    "          if (!t.trim()) t = _declName(n);\n")
# THE SPEC'S OWN ORDER: a declared name outranks the child's content -- the BROAD arm,
# measured so the narrow one is a choice with a number rather than a preference. This is
# the arm that absorbs a nested control's label into its container.
_DECLNAME_BROAD = (
    "          { const _dn = _declName(n); if (_dn) t = _dn; }\n")

_DECL_ANCHOR_PRE = (
    "          if (!t.trim() || _hasShadow) {\n"
    "            const _d = _deepText(n, 0, skip);\n"
    "            if (_d && _d.trim().length > t.trim().length) t = _d;\n"
    "          }\n")

# Two anchors, applied as ONE change: the helper's definition and its single call site.
# `_DECL_POST[1]` is swapped in place by `--ab-broad`, so which arm ran is a property of
# the run rather than of the reader's memory.
_DECL_PRE = ["  const _contentName = (node, skip) => {", _DECL_ANCHOR_PRE]
_DECL_POST = [_DECLNAME_DEF + "  const _contentName = (node, skip) => {",
              _DECL_ANCHOR_PRE + _DECLNAME_NARROW]

CANDIDATES.append(("child-declared-name", None, None, _DECL_PRE, _DECL_POST))


def _set_arm(arm):
    """Which of the three arms `child-declared-name` means, recorded in the output so it
    is never inferred. `narrow` is the proposal; the other two exist so that it is a
    choice with a number beside it rather than a preference (#41/#44)."""
    defn = _DECLNAME_DEF
    if arm == "guarded":
        # AFTER the aria-hidden line, not before it, so the arm this probe measures is
        # byte-identical to the proposed patch. Both are early returns with no side
        # effects, so the order cannot change behaviour -- but "functionally identical"
        # is the kind of claim PRINCIPLES 18 is about, and `verify_patch` compares bytes.
        defn = _DECL_CTL_TAGS + defn.replace(
            "      if (n.getAttribute('aria-hidden') === 'true') return '';\n",
            "      if (n.getAttribute('aria-hidden') === 'true') return '';\n" + _DECL_CTL_GUARD)
    _DECL_POST[0] = defn + "  const _contentName = (node, skip) => {"
    _DECL_POST[1] = _DECL_ANCHOR_PRE + (
        _DECLNAME_BROAD if arm == "broad" else _DECLNAME_NARROW)

# A SABOTAGE ARM FOR `BREAKS_A_CORRECT_NAME`. A zero from a counter nobody has seen fire
# is worth nothing (PRINCIPLES 15), and #114 earned this the same way: it planted a
# candidate that discards every wrapping-label name and watched the counter read 2.
# This one discards the name `synthLabel` recovers from a descendant's `aria-label` --
# the path that today carries the icon-only controls this fix is about, so it breaks
# exactly the population the real candidate touches. NEVER SHIPPED; `--ab-only
# sabotage-drop-aria-label` is the firing proof and nothing else selects it.
CANDIDATES.append((
    "sabotage-drop-aria-label",
    None, None,
    ["      const svgAL = el.querySelector('svg[aria-label], [aria-label]');"],
    ["      const svgAL = null && el.querySelector('svg[aria-label], [aria-label]');"],
))

# ...AND IT DID NOT FIRE, WHICH IS A FACT ABOUT THE INSTRUMENT WORTH KEEPING.
# Over 30 sites and 7,673 compared rows it moved `chars` by +0.08% and `name_changed` by
# ZERO: `synthLabel`'s aria-label rescue fires on controls that have no name from any
# other source, and Chrome mostly IGNORES those rows, so the damage landed outside the
# compared population entirely. A sabotage that changes nothing the comparator looks at
# is not a firing proof, so it is kept (the null is the evidence for the sentence above)
# and a second one is aimed at the population the counter actually watches: the
# `aria-label` read in `accessibleName`, which is the commonest name source on the web.
CANDIDATES.append((
    "sabotage-drop-name-arialabel",
    None, None,
    ["      if (!accessibleName) accessibleName = (el.getAttribute('aria-label') || '').trim();"],
    ["      if (!accessibleName) accessibleName = '' && (el.getAttribute('aria-label') || '').trim();"],
))


def _collector_src(with_fix, only=None):
    """`with_fix=False` returns the collector WITHOUT these changes, `True` WITH them --
    whichever side of the fix `extension/background.js` currently sits on.

    `only` names the candidates to MOVE; every other one is left exactly as the source has
    it. Without it an A/B run while two fixes are already shipped and a third is not would
    silently measure all three at once -- which is not an isolation of anything, and is the
    same "a count is not an inventory" shape one level up (PRINCIPLES 16).

    MEASUREMENT.md's rule for a probe whose arms come from patching source: it must
    construct the arm that does NOT exist yet, or it expires the moment the fix ships and
    the next reader who wants to re-derive the number finds an AssertionError instead.
    `audit_retext_tier.py` and `audit_retext_prevalence.py` are recorded as having expired
    exactly that way, in this repo, hours before this probe was written. So each candidate
    carries BOTH anchors and the direction is decided from the source.

    THE RESULT IS ASSERTED, not assumed: the two arms must differ, and each marker must be
    on exactly the side it belongs to. The first bidirectional version matched the shipped
    `display:contents` rule by my own spelling of it, which the shipped version does not
    use -- so it silently decided the source was pre-fix and handed back the SHIPPED
    collector as the baseline. Nothing but checking the output caught it."""
    src = AGL.COLLECT
    for name, pre_re, post_re, pre_txt, post_txt in CANDIDATES:
        if only is not None and name not in only:
            continue
        if isinstance(pre_txt, list):
            # A MULTI-ANCHOR CANDIDATE IS ONE CHANGE. Every anchor must be on the same
            # side, and the direction is taken from the LAST one (the behavioural line);
            # a mixed state means the source is half-patched and measuring it would be
            # measuring a build nobody runs.
            sides = []
            for a, b in zip(pre_txt, post_txt):
                nb = src.count(b)
                # THE UNFIXED TEXT OFTEN SURVIVES INSIDE THE FIXED BLOCK -- a candidate
                # that INSERTS a line keeps the line it inserted before. Counting raw
                # occurrences then reports pre=1 post=1 and the direction is undecidable.
                # The same special case already exists for `contents-is-not-invisible`;
                # this is it, generalised rather than written a second time (PRINCIPLES 17).
                na = src.count(a) - nb * b.count(a)
                if na == 1 and nb == 0:
                    sides.append("pre")
                elif nb == 1 and na == 0:
                    sides.append("post")
                else:
                    raise AssertionError(
                        "candidate %r anchor %d: pre=%d post=%d -- the patch would "
                        "measure a build nobody runs" % (name, len(sides), na, nb))
            if len(set(sides)) != 1:
                raise AssertionError("candidate %r is half-applied in the source: %s"
                                     % (name, sides))
            if sides[0] == "pre" and with_fix:
                for a, b in zip(pre_txt, post_txt):
                    src = src.replace(a, b)
            elif sides[0] == "post" and not with_fix:
                for a, b in zip(pre_txt, post_txt):
                    src = src.replace(b, a)
            continue
        has_pre = len(re.findall(pre_re, src, re.M))
        has_post = len(re.findall(post_re, src, re.M))
        if name == "contents-is-not-invisible":
            # The unfixed line survives INSIDE the fixed block, so presence of the block is
            # what decides the direction rather than presence of the line.
            if has_post == 1:
                if not with_fix:
                    src = re.sub(post_re, "", src, count=1, flags=re.M)
            elif has_pre == 1:
                if with_fix:
                    src = re.sub(pre_re, lambda m: _CONTENTS_BLOCK + m.group(0), src,
                                 count=1, flags=re.M)
            else:
                raise AssertionError("candidate %r: pre=%d post=%d -- the patch would "
                                     "measure a build nobody runs" % (name, has_pre, has_post))
            continue
        if has_pre == 1 and has_post == 0:
            if with_fix:
                src = src.replace(pre_txt, post_txt)
        elif has_post == 1 and has_pre == 0:
            if not with_fix:
                src = src.replace(post_txt, pre_txt)
        else:
            raise AssertionError("candidate %r: pre=%d post=%d -- the patch would measure "
                                 "a build nobody runs" % (name, has_pre, has_post))
    want = {
        "alt-before-title": "el.getAttribute('alt') || el.getAttribute('title')",
        "contents-is-not-invisible": "if (_disp === 'contents')",
        "live-label-not-clone": "accessibleName = _contentName(wrap, el);",
        "labelledby-non-html": "typeof n.innerText === 'string' ? n.innerText : n.textContent",
        "br-is-a-separator": "parts.push('\\n'); continue;",
        "child-declared-name": "const _declName = (n) => {",
        "sabotage-drop-aria-label": "const svgAL = null &&",
        "sabotage-drop-name-arialabel": "accessibleName = '' && (el.getAttribute('aria-label')",
    }
    for name, marker in want.items():
        if only is not None and name not in only:
            continue
        present = marker in src
        assert present == bool(with_fix), (
            "arm with_fix=%s came back %s the %r marker" % (with_fix,
                                                            "WITH" if present else "WITHOUT",
                                                            name))
    return src


# The MAIN measurement always runs the SHIPPED collector, whatever side of the fix the
# source is on. It used to run `_collector_src(False)`, which was the same thing while the
# fix was unmerged and became "silently measure the UNFIXED build" the moment it landed --
# the arm-expiry trap one step along. `_collector_src` is for the A/B and nothing else.
RECHECK = False


def _collect_js():
    """The shipped collector, structured + compact, exactly as audit_generality_live calls
    it. Array.prototype.toJSON is neutralised for the one stringify (#85's kebhana.com)."""
    return ("(function(){ " + AGL.COLLECT + ";"
            " const ents = _collectInteractivePage(true, null, 'compact', false, false, 'tree');"
            " const _tj = Array.prototype.toJSON; try { delete Array.prototype.toJSON; } catch (e) {}"
            " const blob = (typeof ents === 'string') ? ents : JSON.stringify(ents);"
            " if (_tj) Array.prototype.toJSON = _tj;"
            " return { blob: blob, url: location.href, title: document.title }; })()")


def ours_identity(e):
    """What the ROW presents as this element's identity, with `_fmtLine`'s precedence.

    RESTATED, NOT FORKED -- `_fmtLine` is nested inside the serializer and cannot be
    extracted, so every row's answer is checked against `e.line` by the caller and
    `fmt_drift` is reported. A non-zero fmt_drift voids the numbers rather than being a
    footnote."""
    if e.get("subtreeName") and not e.get("subtreeNameSole"):
        return "", "blanked"
    if e.get("name"):
        return e["name"], "name"
    # When the row leads with value=/placeholder=/submits= it prints NO name field; the
    # element's own text is deliberately not shown there.
    if e.get("value") or e.get("submits") or e.get("placeholder"):
        return "", "contents-only"
    t = e.get("text") or ""
    lab = e.get("label") or ""
    if t:
        if lab and len(lab) > len(t) and t in lab:
            return lab, "label-contains-text"
        return t, "text"
    if e.get("iconOnly"):
        return "", "unlabeled"
    if lab:
        return lab, "label"
    return "", "none"


_CUT = re.compile(r"…\(\+\d+\)$")


def _nfc(s):
    try:
        return unicodedata.normalize("NFC", s or "")
    except Exception:
        return s or ""


def _ws(s):
    return re.sub(r"\s+", " ", _nfc(s)).strip()


def _squash(s):
    return re.sub(r"\s+", "", _nfc(s)).strip()


_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def _alnum(s):
    return re.sub(r"[^\w]", "", _nfc(s), flags=re.UNICODE).lower()


def classify(ours, theirs):
    """Mechanical. No narration: the grouping is a property of the two strings, and the
    verdict per class is argued once in the write-up against a named spec rule."""
    a, b = _ws(ours), _ws(theirs)
    if a == b:
        return "exact"
    cut_a = bool(_CUT.search(a))
    if cut_a:
        stem = _CUT.sub("", a).rstrip("… ")
        if stem and b.startswith(stem[: max(0, len(stem) - 2)]):
            return "ours-marked-cut"
    if _squash(a) == _squash(b):
        return "whitespace-only"
    if a.lower() == b.lower():
        return "case-only"
    if not a and b:
        return "ours-empty"
    if a and not b:
        return "chrome-empty"
    if _alnum(a) == _alnum(b):
        return "punctuation-only"
    if _alnum(a) and _alnum(a) in _alnum(b):
        return "chrome-superset"
    if _alnum(b) and _alnum(b) in _alnum(a):
        return "ours-superset"
    ta = set(w for w in re.split(r"\W+", a.lower(), flags=re.UNICODE) if w)
    tb = set(w for w in re.split(r"\W+", b.lower(), flags=re.UNICODE) if w)
    if ta and tb and (ta & tb):
        return "partial-overlap"
    return "disjoint"


# ARIA 1.2's own table of roles whose accessible name MAY come from the element's
# contents. For every other role the spec says the name comes from the author only (or is
# prohibited outright, as for `generic`), so Chrome returning "" is CORRECT there and is a
# different fact from a name we got wrong. Used ONLY in the analysis, to group the biggest
# class -- no product code reads it.
NAME_FROM_CONTENT = {
    "button", "cell", "checkbox", "columnheader", "gridcell", "heading", "link",
    "menuitem", "menuitemcheckbox", "menuitemradio", "option", "radio", "row",
    "rowheader", "switch", "tab", "tooltip", "treeitem",
    # HTML-AAM adds these host-language mappings
    "DisclosureTriangle", "Legend", "Caption", "LabelText", "ListMarker",
}

DISAGREE = ("whitespace-only", "case-only", "punctuation-only", "ours-empty",
            "chrome-empty", "chrome-superset", "ours-superset", "partial-overlap",
            "disjoint", "ours-marked-cut")


# --------------------------------------------------------------------------------------
# CHROME'S SIDE. #33's axNamesFor, over a Playwright CDP session.
# --------------------------------------------------------------------------------------
async def ax_names(cdp):
    """Returns {mmid: {name, role, ignored}} plus the three counts that make a zero
    DIAGNOSABLE rather than a silence (#34): axNodes=0 means the domain produced no tree,
    mapped=0 means nothing carried an mmid, both non-zero with names={} means the
    backendNodeId join is wrong."""
    info = {"axNodes": 0, "mapped": 0, "named": 0, "ignored": 0, "error": None}
    try:
        await cdp.send("DOM.enable")
    except Exception:
        pass
    try:
        await cdp.send("Accessibility.enable")
    except Exception:
        pass
    by = {}
    try:
        doc = await cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})
    except Exception as e:
        info["error"] = "DOM.getDocument: " + str(e)[:120]
        return {}, info

    stack = [doc.get("root")]
    while stack:
        n = stack.pop()
        if not n:
            continue
        a = n.get("attributes") or []
        for i in range(0, len(a) - 1, 2):
            if a[i] == "mmid":
                by[n.get("backendNodeId")] = str(a[i + 1])
                break
        for c in (n.get("children") or []):
            stack.append(c)
        for s in (n.get("shadowRoots") or []):
            stack.append(s)
        if n.get("contentDocument"):
            stack.append(n["contentDocument"])
    info["mapped"] = len(by)
    try:
        ax = await cdp.send("Accessibility.getFullAXTree")
    except Exception as e:
        info["error"] = "getFullAXTree: " + str(e)[:120]
        return {}, info
    nodes = ax.get("nodes") or []
    info["axNodes"] = len(nodes)
    out = {}
    for node in nodes:
        mm = by.get(node.get("backendDOMNodeId"))
        if not mm:
            continue
        ig = bool(node.get("ignored"))
        nm = ((node.get("name") or {}).get("value")) if not ig else None
        src = ""
        try:
            srcs = (node.get("name") or {}).get("sources") or []
            for s in srcs:
                if s.get("value") is not None and s.get("value", {}).get("value"):
                    src = s.get("type") or s.get("attribute") or ""
                    break
        except Exception:
            pass
        rec = {"name": nm if isinstance(nm, str) else None, "ignored": ig,
               "role": ((node.get("role") or {}).get("value") or ""), "from": src}
        # An element can appear more than once (a label and its control share a backend
        # node in no case, but a frame boundary can repeat); first non-ignored wins.
        if mm in out and out[mm].get("name"):
            continue
        out[mm] = rec
    info["named"] = sum(1 for v in out.values() if v.get("name"))
    info["ignored"] = sum(1 for v in out.values() if v.get("ignored"))
    return out, info


# --------------------------------------------------------------------------------------
async def read_once(page, cdp, label, seen_names, want_examples, plant=False,
                    recheck=False, hov_fn=None, plant_only=None):
    """ONE read: collector -> declarations -> Chrome AX tree -> compare. The collector runs
    FIRST because it is what stamps the mmid attributes the join uses.

    `hov_fn` is an awaitable returning the mmids of the elements a HOVER was OBSERVED to
    reveal (#94's before/after element-identity diff, held in page memory). It is called
    HERE, between the collector and the compare loop, because those mmids do not exist
    until the collector has stamped them and must exist before the loop that tallies them
    -- the ordering #94's own `APPEARED_MMIDS` comment states. A failure is RECORDED as
    `hov_error`, never swallowed into an empty set: a driver that silently revealed
    nothing would otherwise produce a clean rate over an empty population, which is the
    exact shape PRINCIPLES 15 is about.
    """
    res = await page.evaluate(_collect_js())
    ents = json.loads(res["blob"])
    hov_mmids, hov_error = set(), None
    if hov_fn is not None:
        try:
            hov_mmids = {str(m) for m in (await hov_fn()) if m}
        except Exception as e:
            hov_error = str(e)[:140]
    decls = await page.evaluate(DECLS_JS)
    planted = []
    if plant:
        # PLANT ONLY ON ROWS THAT WOULD BE COMPARED. The collector stamps an mmid on far
        # more elements than it lists, so planting on `[mmid]` in document order put 22 of
        # 24 sentinels on elements that are not entries at all -- a firing proof whose
        # denominator was almost entirely "not a question". The candidate set is computed
        # from the entries just collected.
        cand = [str(e.get("mmid")) for e in ents
                if ours_identity(e)[1] in ("name", "text", "label", "label-contains-text")
                and ours_identity(e)[0]]
        # RESTRICTED TO A NAMED SET WHEN ONE IS GIVEN. The hover firing proof has to plant
        # on rows the HOVER revealed, not on whatever the page happens to list first: a
        # sentinel that lands on the page header proves the comparator works and says
        # nothing about the hover arm, which is the population whose emptiness is the
        # hazard here.
        if plant_only is not None:
            keep = {str(m) for m in plant_only}
            cand = [m for m in cand if m in keep]
        planted = await page.evaluate(_PLANT_JS, {"sentinel": PLANT, "mmids": cand[:400]})
    chrome, info = await ax_names(cdp)

    rows = []
    counts = collections.Counter()
    # SPLIT BY WHERE OUR IDENTITY CAME FROM, because the two halves make different claims.
    # `src=name` is the collector saying "this is the element's ACCESSIBLE NAME" and prints
    # `name="..."`; `src=text`/`label` is the row printing the element's OWN TEXT as a bare
    # quoted string, which is a weaker claim the legend spells out. Chrome has no name at
    # all for a role whose naming is prohibited (`generic`) or author-only (`listitem`), so
    # pooling the two makes a spec-correct silence look like a disagreement.
    by_src = collections.defaultdict(collections.Counter)
    # POPULATION x SRC x CLASS, EXACT AND UNCAPPED -- the join `per_pop` could not make.
    #
    # #93 asked whether a control REVEALED by an interaction is named worse, got 0.6628
    # against 0.7370, said most of it was composition, and left it unsettled; a smaller
    # run with corrected code reversed the sign. Two things stopped that question being
    # answerable, and both are shape rather than sample:
    #
    #   1. `per_pop` carries only `compared`/`exact` POOLED over every site, so one large
    #      site dominates both arms and the comparison is between two different mixtures
    #      of pages. The paired per-READ comparison is the one that removes that, and it
    #      needs these counts to exist per read.
    #   2. `per_pop`'s class breakdown is taken from `rd["rows"]`, which is CAPPED and in
    #      document order -- a head slice of each page (PRINCIPLES 16). And it is not
    #      split by `src` at all, so the HEADLINE population (`src=name`, the one
    #      0.9766 quotes) has never been compared between revealed and carried.
    #
    # Keys are "pop|src" and "pop|src|cls" so this stays JSON-serialisable and rolls up
    # by splitting, rather than becoming a third nesting level nobody walks (#107 records
    # a rollup that existed only three levels down being read as missing data).
    by_pop = collections.Counter()
    # THE SAME SPLIT ON A SECOND, TIGHTER AXIS: `hov` is an element a hover was WATCHED to
    # reveal (element identity, before and after, in page memory), `pre` is everything
    # else in THIS READ. Both arms therefore come from one read of one page, which is the
    # design #115 used to settle revealed-vs-carried and the only one that removes
    # composition by construction rather than by argument.
    #
    # IT IS KEPT ALONGSIDE `by_pop` RATHER THAN REPLACING IT, because the two answer
    # different questions and have disagreed before. `by_pop`'s `new` is keyed on the
    # IDENTITY STRING (#89/#92's definition, because mmids are additive) and so counts a
    # control that was always on the page but whose identity happened not to appear at s0
    # as "revealed"; `hov` is keyed on an observation. Reporting both is what makes the
    # difference between them readable instead of a choice made silently.
    by_hov = collections.Counter()
    # EXACT, UNCAPPED role histogram per disagreement class. The `rows` list is capped for
    # file size and is in document order, so counting roles from it would be a head slice
    # of each page -- a count that is not an inventory (PRINCIPLES 16). Chrome's ROLE is
    # what decides whether a name is even permitted (ARIA: `generic` prohibits naming,
    # `listitem` is name-from-author-only), so this is the evidence the biggest class needs.
    cls_roles = collections.Counter()
    role_named = collections.Counter()
    fmt_drift = 0
    # EVERY row's disposition, for the planted mmids only: a planted name that was never
    # in the compared population proves nothing either way, and counting it as a failure
    # would make the firing proof depend on the page's shape rather than on the comparator.
    track = set(planted)
    disp = {}
    all_ours = []
    for e in ents:
        mm = str(e.get("mmid"))
        ours, src = ours_identity(e)
        if ours:
            all_ours.append(ours)
        # SELF-CHECK of the precedence restatement against the row the collector really
        # built. A silent drift here would make every number below meaningless.
        #
        # BOTH QUOTING FORMS ARE ACCEPTED, and that is a finding rather than a loophole:
        # `_fmtLine` emits `name=`/`value=`/`placeholder=`/`near=`/`href=`/`src=` through
        # JSON.stringify but builds the BARE-TEXT identity by raw interpolation
        # (` "${e.text}"`), so a label containing a double quote lands in the row
        # unescaped. The first version of this check only looked for the escaped form and
        # reported 341 "drifts" that were all that one case -- my own checker's assumption,
        # not a drift (MEASUREMENT.md Sec.3's class, on the probe rather than the product).
        line = e.get("line") or ""
        if ours and (json.dumps(ours, ensure_ascii=False)[1:-1] not in line
                     and ours not in line):
            fmt_drift += 1
        ax = chrome.get(mm)
        if ax is None:
            counts["not-in-ax-tree"] += 1
            if mm in track:
                disp[mm] = "not-in-ax-tree"
            continue
        if ax.get("ignored"):
            counts["chrome-ignored"] += 1
            if mm in track:
                disp[mm] = "chrome-ignored"
            continue
        theirs = ax.get("name") or ""
        # EMPIRICAL, NOT A LIST. "Is Chrome even permitted a name for this role?" is
        # answerable from the data: count, per role, how often Chrome produced one. A role
        # that essentially never carries a name is one where `chrome-empty` is the ARIA
        # role table working rather than a name we got wrong -- measured instead of
        # asserted from a table someone transcribed.
        role_named[(ax.get("role") or "?") + "|" + ("named" if theirs.strip() else "empty")] += 1
        if src == "blanked":
            counts["blanked-row"] += 1
            counts["blanked-chrome-named"] += 1 if theirs.strip() else 0
            if mm in track:
                disp[mm] = "blanked-row"
            continue
        if src == "contents-only":
            counts["contents-only-row"] += 1
            if mm in track:
                disp[mm] = "contents-only-row"
            continue
        if not ours and not theirs:
            counts["both-empty"] += 1
            if mm in track:
                disp[mm] = "both-empty"
            continue
        cls = classify(ours, theirs)
        counts["compared"] += 1
        counts[cls] += 1
        by_src[src]["compared"] += 1
        by_src[src][cls] += 1
        # NEW / CARRIED tallied HERE, over the same compared rows the agreement rate uses,
        # so the numerator and the denominator come from one population (#22).
        #
        # A ROW WITH NO IDENTITY CANNOT BE ASSIGNED, and the first version of this put all
        # of them in NEW: the population is keyed on the identity STRING (#92's rule,
        # because mmids are additive) and "" is never in the seen set, so every single
        # `ours-empty` row counted as revealed-by-the-interaction and none as carried. That
        # is a defect class concentrating itself in one arm BY CONSTRUCTION -- exactly the
        # clean, plausible, wrong number MEASUREMENT.md Sec.3 lists. Third bucket.
        if not ours:
            pop = "unnamed"
        elif seen_names is None:
            pop = "carried"
        else:
            pop = "new" if ours not in seen_names else "carried"
        counts[pop + "_compared"] += 1
        if cls == "exact":
            counts[pop + "_exact"] += 1
        # The same three populations, now carrying `src` and `cls` so the headline
        # `src=name` slice can be compared arm to arm and a difference can be attributed
        # to a CLASS rather than left as a bare rate gap.
        by_pop[pop + "|" + src + "|compared"] += 1
        if cls == "exact":
            by_pop[pop + "|" + src + "|exact"] += 1
        else:
            by_pop[pop + "|" + src + "|c:" + cls] += 1
        if hov_fn is not None:
            hp = "hov" if mm in hov_mmids else "pre"
            by_hov[hp + "|" + src + "|compared"] += 1
            if cls == "exact":
                by_hov[hp + "|" + src + "|exact"] += 1
            else:
                by_hov[hp + "|" + src + "|c:" + cls] += 1
        if mm in track:
            disp[mm] = "compared:" + cls + (":SENTINEL" if PLANT in theirs else "")
        if cls != "exact":
            cls_roles[cls + "|" + (ax.get("role") or "?") + "|" + src] += 1
            d = decls.get(mm) or {}
            rows.append({
                "stage": label, "mmid": mm, "cls": cls, "ours": ours[:200],
                "theirs": theirs[:200], "src": src,
                "tag": e.get("tag"), "role": e.get("role") or d.get("roleAttr") or "",
                "ax_role": ax.get("role"), "ax_from": ax.get("from"),
                "synth": e.get("synth") or "", "subtreeName": bool(e.get("subtreeName")),
                "decl": {k: v for k, v in d.items() if k != "html" and v not in ("", 0, False)},
                "html": d.get("html", "")[:260],
                "new": (seen_names is not None and ours not in seen_names),
                "hov": (mm in hov_mmids),
            })
    # IS THE ORACLE ITSELF STABLE? The collector runs, then DOM.getDocument and
    # getFullAXTree run -- tens to hundreds of milliseconds later on a big page. On a live
    # site that is time for a re-render, which would make a name disagree for a reason that
    # is neither derivation's fault. Re-reading the oracle and counting how many of the
    # REPORTED rows move is a direct bound on that confound, taken on exactly the rows it
    # would corrupt. Off by default because it doubles the CDP cost per read.
    if recheck and rows:
        try:
            chrome2, _i2 = await ax_names(cdp)
            moved = 0
            for r in rows:
                a2 = chrome2.get(r["mmid"]) or {}
                if (a2.get("name") or "") != r["theirs"][:200]:
                    moved += 1
            counts["oracle_rows_rechecked"] += len(rows)
            counts["oracle_rows_moved"] += moved
        except Exception:
            pass
    # A THIRD ORACLE, FETCHED ONLY FOR THE ROWS THAT DISAGREED: what the element actually
    # RENDERS. Where the two derivations differ about whitespace or about a decorative
    # glyph, neither spec text nor our preference settles it -- but "which of the two
    # matches what is on the screen" is a measurement, and it is the question an agent's
    # reader is really asking. Lazy because innerText forces layout per call and a page can
    # carry thousands of mmid elements.
    if rows:
        try:
            rend = await page.evaluate(_RENDERED_JS, [r["mmid"] for r in rows[:want_examples]])
            for r in rows[:want_examples]:
                r["rendered"] = (rend.get(r["mmid"]) or "")[:200]
        except Exception:
            pass
    # A planted mmid that never appeared in the entry list is stamped in the DOM but is
    # not a ROW (a <label>, a hidden aria-labelledby target). Recorded explicitly rather
    # than being absent, so the firing proof's denominator is readable (PRINCIPLES 16 --
    # a count is not an inventory).
    for mm in track:
        disp.setdefault(mm, "not-an-entry")
    out_hov = {}
    if hov_fn is not None:
        ent_mm = {str(e.get("mmid")) for e in ents}
        # THE POPULATION'S OWN FUNNEL, so a clean rate can never be read without the size
        # it came from. `revealed` is what the diff observed, `as_entries` what the
        # collector listed, and the `hov|*|compared` keys what reached the oracle. #117's
        # brief asks for exactly this and PRINCIPLES 16 is why it is three numbers rather
        # than one.
        out_hov = {"by_hov": dict(by_hov), "hov_error": hov_error,
                   "hov_revealed": len(hov_mmids),
                   "hov_as_entries": len(hov_mmids & ent_mm)}
    return {
        "stage": label, "entries": len(ents), "ax_info": info, "fmt_drift": fmt_drift,
        "counts": dict(counts), "by_src": {k: dict(v) for k, v in by_src.items()},
        "by_pop": dict(by_pop), **out_hov,
        # NAME PROVENANCE PER ELEMENT, for `OPEN.md` item 21's falsifier -- which names a
        # corpus pass over TWO READS OF ONE DOCUMENT, and that is exactly what a staged
        # run is (the driver breaks on a url change, so every stage reads one document).
        #
        # `__abSynthAttr` is set at five sites in the collector and cleared at none, so a
        # control read once before its label exists keeps `(post-key)` for the life of the
        # document -- a FALSE PROVENANCE CLAIM in the one field whose purpose is
        # provenance, pointing the wrong way: it tells an agent to distrust a name that is
        # now authored and correct. Item 21 says it needs a prevalence number before
        # anything is changed, and records the falsifier: zero controls whose provenance
        # changes between two reads means a latent defect with no instances.
        #
        # Only entries that HAVE a synth marker are kept, so this is a few percent of
        # entries rather than all of them; keyed by mmid, which is stable for an element
        # already stamped in this document.
        "synth_map": {str(e.get("mmid")): (e.get("synth") or "") + "|" + (ours_identity(e)[0] or "")[:60]
                      for e in ents if e.get("synth")},
        "cls_roles": dict(cls_roles), "role_named": dict(role_named),
        "rows": rows[:want_examples], "rows_total": len(rows),
        "planted": planted, "planted_disposition": disp, "_all_ours": all_ours,
    }


# --------------------------------------------------------------------------------------
# THE QUOTING MEASUREMENT. `_fmtLine` emits name=/value=/placeholder=/near=/href=/src=
# through JSON.stringify but builds the BARE-TEXT identity by raw interpolation
# (` "${e.text}"`), so a label containing a double quote lands in the row unescaped and a
# reader parsing the row back gets a truncated string with no sign that it was truncated.
# This is not an opinion about style: it is measured by PARSING the row the way a consumer
# would and comparing the result to the identity the collector meant to print.
PARSE_RE = re.compile(r'"(?:[^"\\]|\\.)*"')


def parse_back(line):
    """What a reader gets when it pulls the identity out of a printed row.

    The first JSON-style quoted run after the `ref_N | tag` prefix IS the identity for both
    emission paths -- `name="..."` leads with it, and the bare-text form is the first quoted
    thing on the row. Later fields (near=, href=, src=, options=) come after it."""
    body = line.split("|", 1)[1] if "|" in line else line
    m = PARSE_RE.search(body)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


QUOTING_KEYS = ("rows", "bare", "bare_escapable", "json_quoted", "json_quoted_escapable",
                "parse_ok", "parse_truncated", "parse_wrong", "parse_absent")


def quoting_tally(ents):
    c = collections.Counter()
    ex = []
    for e in ents:
        ours, src = ours_identity(e)
        line = e.get("line") or ""
        if not ours or not line:
            continue
        c["rows"] += 1
        bare = src in ("text", "label", "label-contains-text")
        escapable = ('"' in ours) or ("\\" in ours)
        c["bare" if bare else "json_quoted"] += 1
        if escapable:
            c[("bare_escapable" if bare else "json_quoted_escapable")] += 1
        got = parse_back(line)
        if got is None:
            c["parse_absent"] += 1
        elif got == ours:
            c["parse_ok"] += 1
        elif ours.startswith(got):
            c["parse_truncated"] += 1
            if len(ex) < 12:
                ex.append({"src": src, "tag": e.get("tag"), "meant": ours[:120],
                           "reader_gets": got[:120], "line": line[:180]})
        else:
            c["parse_wrong"] += 1
            if len(ex) < 12:
                ex.append({"src": src, "tag": e.get("tag"), "meant": ours[:120],
                           "reader_gets": got[:120], "line": line[:180], "wrong": True})
    return c, ex


async def quoting_site(browser, name, url, arch, lang, nstages):
    ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True, locale="en-US")
    try:
        await ctx.add_init_script(path=TAG_JS)
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=GOTO_MS)
        except Exception as e:
            return {"site": name, "error": "goto: " + str(e)[:110]}
        try:
            await page.wait_for_load_state("networkidle", timeout=7000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)
        tot = collections.Counter()
        ex = []
        used = collections.Counter()
        for stage in range(nstages + 1):
            res = await page.evaluate(_collect_js())
            c, e = quoting_tally(json.loads(res["blob"]))
            tot.update(c)
            if len(ex) < 6:
                ex += e[: 6 - len(ex)]
            if stage >= nstages:
                break
            pick = await page.evaluate("(" + ASG.STAGE_PICK.strip() + ")(" + json.dumps(
                {"usedKinds": dict(used), "maxPerKind": ASG.MAX_PER_KIND}) + ")")
            if not pick:
                break
            before = page.url
            try:
                await ASG._act(page, pick)
            except Exception:
                pass
            await page.wait_for_timeout(ASG.SETTLE_MS)
            if page.url.split("#")[0] != before.split("#")[0]:
                break
            v = await page.evaluate(ASG.STAGE_VERIFY)
            used[pick["kind"]] += 1
            if not v.get("flipped"):
                break
        return {"site": name, "lang": lang, "counts": dict(tot), "examples": ex}
    finally:
        try:
            await ctx.close()
        except Exception:
            pass


async def candidate_ab(browser, name, url, arch, lang, nstages, only=None):
    """BOTH COLLECTORS ON THE SAME PAGE LOAD, scored against ONE oracle read.

    MEASUREMENT.md R3: block-structured A/B aligns run-order drift exactly with variant
    order. Here the two arms are two `page.evaluate` calls milliseconds apart against the
    same DOM, and Chrome's AX tree is read ONCE and used for both, so the oracle cannot
    move between them either.

    Reports movement rather than a level: a row is IMPROVED when the base arm disagreed
    with Chrome and the candidate agrees, REGRESSED the other way. A candidate that only
    improves is Pareto-positive; one that trades is a decision, not a fix (#41/#44)."""
    ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True,
                                    locale="en-US")
    base_src, cand_src = _collector_src(False, only), _collector_src(True, only)

    def js(src):
        return ("(function(){ " + src + ";"
                " const ents = _collectInteractivePage(true, null, 'compact', false, false, 'tree');"
                " const listing = _collectInteractivePage(false, null, 'compact', false, false, 'tree');"
                " const _tj = Array.prototype.toJSON; try { delete Array.prototype.toJSON; } catch (e) {}"
                " const blob = (typeof ents === 'string') ? ents : JSON.stringify(ents);"
                " if (_tj) Array.prototype.toJSON = _tj;"
                " return { blob: blob, chars: String(listing).length }; })()")

    tot = collections.Counter()
    # THE SAME A/B, ATTRIBUTED TO THE STAGE IT HAPPENED AT. `tot` pools every stage, so
    # "is this fix worth more after an interaction?" could not be read off it -- and that
    # is the question these three candidates exist to answer: #114's `display:contents`
    # hunk was measured firing 2.8x more post-interaction than at first paint, because
    # design systems render slotted controls when you OPEN something. Same rows, same
    # oracle read, one extra key.
    by_stage = collections.Counter()
    moved = []
    gained = []
    try:
        await ctx.add_init_script(path=TAG_JS)
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=GOTO_MS)
        except Exception as e:
            return {"site": name, "error": "goto: " + str(e)[:110]}
        try:
            await page.wait_for_load_state("networkidle", timeout=7000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)
        cdp = await ctx.new_cdp_session(page)
        used = collections.Counter()
        stage = 0
        while True:
            a = await page.evaluate(js(base_src))
            b = await page.evaluate(js(cand_src))
            chrome, info = await ax_names(cdp)
            A = {str(e["mmid"]): e for e in json.loads(a["blob"])}
            B = {str(e["mmid"]): e for e in json.loads(b["blob"])}
            tot["entries_base"] += len(A)
            tot["entries_cand"] += len(B)
            tot["chars_base"] += a["chars"]
            tot["chars_cand"] += b["chars"]
            tot["joined"] += len(set(A) & set(B))
            for mm in set(A) & set(B):
                ax = chrome.get(mm)
                # IDENTITY GAINS OUTSIDE THE COMPARED POPULATION STILL COUNT FOR THE
                # AGENT. The buckets below are scored only where Chrome also has a name,
                # which is the conservative subset: there a gain is VERIFIED correct. But
                # a row that stops saying `(unlabeled)` is a gain to the reader whether or
                # not Chrome has an opinion, and Chrome IGNORES a great many icon
                # controls -- so the graded figure is a LOWER bound and this counter is
                # what says by how much.
                _oa, _sa = ours_identity(A[mm])
                _ob, _sb = ours_identity(B[mm])
                if not _oa.strip() and _ob.strip():
                    tot["gained_identity_any"] += 1
                    if not ax or ax.get("ignored"):
                        tot["gained_identity_chrome_ignores"] += 1
                if not ax or ax.get("ignored"):
                    continue
                theirs = ax.get("name") or ""
                oa, sa = ours_identity(A[mm])
                ob, sb = ours_identity(B[mm])
                if sa in ("blanked", "contents-only") or sb in ("blanked", "contents-only"):
                    continue
                if not (oa or ob or theirs):
                    continue
                ca, cb = classify(oa, theirs), classify(ob, theirs)
                tot["compared"] += 1
                tot["exact_base"] += 1 if ca == "exact" else 0
                tot["exact_cand"] += 1 if cb == "exact" else 0
                sk = "s%d|" % stage
                by_stage[sk + "compared"] += 1
                if oa != ob:
                    tot["name_changed"] += 1
                    by_stage[sk + "name_changed"] += 1
                    _named = bool((theirs or "").strip())
                    if ca != "exact" and cb == "exact":
                        by_stage[sk + ("improved_chrome_named" if _named
                                       else "improved_chrome_empty")] += 1
                    elif ca == "exact" and cb != "exact":
                        by_stage[sk + ("BREAKS_A_CORRECT_NAME" if _named
                                       else "regressed_chrome_empty")] += 1
                    # SPLIT ON WHETHER CHROME HAS A NAME AT ALL. A row where Chrome's role
                    # permits no name (ARIA: `generic` prohibits it, most roles are
                    # author-only) cannot be "named wrongly" -- our row prints the
                    # element's TEXT there, which is a different claim. Counting those as
                    # regressions is what made the first reading of this A/B a wash.
                    named = bool((theirs or "").strip())
                    if ca != "exact" and cb == "exact":
                        tot["improved"] += 1
                        tot["improved_chrome_named" if named else "improved_chrome_empty"] += 1
                    elif ca == "exact" and cb != "exact":
                        tot["regressed"] += 1
                        tot["regressed_chrome_named" if named else "regressed_chrome_empty"] += 1
                    else:
                        tot["moved_neither"] += 1
                    # The one number that would stop this: a row where Chrome HAS a name,
                    # we had it right, and the candidate breaks it.
                    if named and ca == "exact" and cb != "exact":
                        tot["BREAKS_A_CORRECT_NAME"] += 1
                    # THE BENEFIT, GRADED. A row that had no identity and now has one is
                    # the only shape where the agent's row changes from `(unlabeled)` to
                    # something actionable; everything else is a wording change. Collect
                    # them and ask WHERE that name was in the BASE listing.
                    if not oa.strip() and ob.strip():
                        gained.append({"mmid": mm, "name": ob, "tag": A[mm].get("tag"),
                                       "chrome": theirs, "stage": stage})
                    if len(moved) < 25:
                        moved.append({"mmid": mm, "tag": A[mm].get("tag"),
                                      "base": oa[:120], "cand": ob[:120],
                                      "chrome": theirs[:120], "cls": [ca, cb]})
            if gained:
                others = []
                for k, e in A.items():
                    i, _s = ours_identity(e)
                    if i.strip():
                        others.append({"mmid": k, "id": i})
                try:
                    where = await page.evaluate(_WHERE_JS, {
                        "rows": [{"mmid": g["mmid"], "name": g["name"]}
                                 for g in gained if g.get("stage") == stage],
                        "others": others})
                except Exception:
                    where = {}
                for g in gained:
                    if g.get("stage") != stage or "where" in g:
                        continue
                    g["where"] = where.get(g["mmid"], "unresolved")
                    tot["where_" + g["where"]] += 1
                    by_stage["s%d|where_%s" % (stage, g["where"])] += 1
            stage += 1
            if stage > nstages:
                break
            pick = await page.evaluate("(" + ASG.STAGE_PICK.strip() + ")(" + json.dumps(
                {"usedKinds": dict(used), "maxPerKind": ASG.MAX_PER_KIND}) + ")")
            if not pick:
                break
            before = page.url
            try:
                await ASG._act(page, pick)
            except Exception:
                pass
            await page.wait_for_timeout(ASG.SETTLE_MS)
            if page.url.split("#")[0] != before.split("#")[0]:
                break
            v = await page.evaluate(ASG.STAGE_VERIFY)
            used[pick["kind"]] += 1
            if not v.get("flipped"):
                break
        return {"site": name, "lang": lang, "counts": dict(tot), "moved": moved,
                "gained": gained[:60], "by_stage": dict(by_stage), "stages": stage}
    finally:
        try:
            await ctx.close()
        except Exception:
            pass


# WHERE WAS THE NAME BEFORE? -- the benefit half, graded rather than counted.
#
# A row that GAINS an identity is not uniformly valuable. #115 graded the same class by
# composed-tree containment and found the three buckets cost an agent very different
# amounts:
#   INSIDE    the name already sat on a row nested within this control, so an agent that
#             acted on it still hit the right thing -- a click bubbles. Low cost.
#   ELSEWHERE the name was on some unrelated row. Reachable by `find`, attributed to the
#             wrong control: #93's "the words survive on a NEIGHBOURING row".
#   NOWHERE   the name was in the listing nowhere at all. This is the only outright loss,
#             and it is #74's defect class with live instances.
# Graded against the BASE listing, because that is the one the agent would have been
# handed. `__mmidReg` is the collector's own registry, so containment is asked of the
# elements it actually stamped rather than re-derived from a selector (#99's lesson).
_WHERE_JS = r"""
(req) => {
  // mmid -> element by WALKING, not from `window.__mmidReg`. The collector runs inside a
  // `(function(){...})()` in this evaluate, so its registry is not on `window` here and
  // the first version of this grading returned `unresolved` for 100% of rows -- a clean,
  // plausible, entirely wrong benefit figure. `_RENDERED_JS` below already walks; this is
  // the same walk rather than a second idea (PRINCIPLES 17).
  const reg = {};
  (function walk(root, d) {
    let all; try { all = root.querySelectorAll('[mmid]'); } catch (e) { return; }
    for (const el of all) { const m = el.getAttribute('mmid'); if (m && !reg[m]) reg[m] = el; }
    if (d > 6) return;
    let every; try { every = root.querySelectorAll('*'); } catch (e) { return; }
    let budget = 20000;
    for (const e of every) {
      if (--budget < 0) break;
      const sr = e.shadowRoot || e.__abClosedRoot;
      if (sr) walk(sr, d + 1);
      if (e.tagName === 'IFRAME') { try { const doc = e.contentDocument; if (doc) walk(doc, d + 1); } catch (x) {} }
    }
  })(document, 0);
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  // Composed-tree containment: `contains` does not cross a shadow boundary, so walk up
  // through hosts the way the collector's own `composedParent` does.
  const inside = (anc, el) => {
    let n = el, hops = 0;
    while (n && hops++ < 200) {
      if (n === anc) return true;
      n = n.parentNode || null;
      if (n && n.nodeType === 11) n = n.host || null;      // DocumentFragment -> host
    }
    return false;
  };
  const out = {};
  for (const r of (req.rows || [])) {
    const el = reg[r.mmid];
    const want = norm(r.name);
    if (!el || !want) { out[r.mmid] = 'unresolved'; continue; }
    let verdict = 'nowhere';
    for (const o of (req.others || [])) {
      if (String(o.mmid) === String(r.mmid)) continue;
      if (norm(o.id).indexOf(want) === -1) continue;
      const oe = reg[o.mmid];
      if (oe && inside(el, oe)) { verdict = 'inside'; break; }
      verdict = 'elsewhere';
    }
    out[r.mmid] = verdict;
  }
  return out;
}
"""


_RENDERED_JS = r"""
(mmids) => {
  const want = new Set(mmids || []), out = {};
  function walk(root, depth) {
    let all; try { all = root.querySelectorAll('[mmid]'); } catch (e) { return; }
    for (const el of all) {
      const mm = el.getAttribute('mmid');
      if (!mm || !want.has(mm) || out[mm] !== undefined) continue;
      let t = '';
      try { t = (typeof el.innerText === 'string' ? el.innerText : el.textContent) || ''; } catch (e) {}
      out[mm] = t.replace(/\s+/g, ' ').trim();
    }
    if (depth > 9) return;
    let every; try { every = root.querySelectorAll('*'); } catch (e) { return; }
    let b = 20000;
    for (const e of every) {
      if (--b < 0) break;
      const sr = e.shadowRoot || e.__abClosedRoot;
      if (sr) walk(sr, depth + 1);
      if (e.tagName === 'IFRAME') { try { const d = e.contentDocument; if (d) walk(d, depth + 1); } catch (x) {} }
    }
  }
  walk(document, 0);
  return out;
}
"""


_PLANT_JS = r"""
(opts) => {
  const sentinel = opts.sentinel, want = new Set(opts.mmids || []);
  // FIRING PROOF, LIVE. After the collector has stamped mmids and built its entries, move
  // a handful of elements' accessible names: Chrome reads the DOM as it is NOW, we read it
  // as it WAS, so the comparator MUST report a disagreement for exactly these. It proves
  // the join and the comparator end to end, independently of whether the two derivations
  // happen to differ anywhere on this page.
  const out = [];
  let all;
  try { all = document.querySelectorAll('[mmid]'); } catch (e) { return out; }
  for (const el of all) {
    if (out.length >= 8) break;
    const mm = el.getAttribute('mmid');
    if (!mm || !want.has(mm)) continue;
    let r; try { r = el.getBoundingClientRect(); } catch (e) { continue; }
    if (r.width < 8 || r.height < 8) continue;
    try { el.setAttribute('aria-label', sentinel + '-' + mm); } catch (e) { continue; }
    out.push(mm);
  }
  return out;
}
"""


# --------------------------------------------------------------------------------------
async def one(browser, name, url, arch, lang, nstages, examples, plant_at_end):
    t0 = time.time()
    ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True,
                                    user_agent=None, locale="en-US")
    base = {"site": name, "url": url, "archetype": arch, "lang": lang}
    try:
        await ctx.add_init_script(path=TAG_JS)
        page = await ctx.new_page()
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=GOTO_MS)
            status = resp.status if resp else None
        except Exception as e:
            return dict(base, error="goto: " + str(e)[:120])
        try:
            await page.wait_for_load_state("networkidle", timeout=7000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)
        cdp = await ctx.new_cdp_session(page)

        try:
            r0 = await read_once(page, cdp, "s0", None, examples, recheck=RECHECK)
        except Exception as e:
            return dict(base, error="read: " + str(e)[:160], status=status)
        out = dict(base, status=status, reads=[r0])
        # NEW is keyed on the identity STRING, not the mmid: mmids are additive, so one
        # re-render mints hundreds of fresh ones for elements that did not change (#9).
        # #89 and #92 both use the name-set definition; keep it.
        seen_names = _names_of(r0)
        r0.pop("_all_ours", None)          # not persisted: it is every identity on the page

        used = collections.Counter()
        picks = []
        attempts = 0
        while len(out["reads"]) <= nstages and attempts < nstages + 3:
            attempts += 1
            i = len(out["reads"])
            step = {"n": i, "attempt": attempts}
            try:
                pick = await page.evaluate(
                    "(" + ASG.STAGE_PICK.strip() + ")(" + json.dumps(
                        {"usedKinds": dict(used), "maxPerKind": ASG.MAX_PER_KIND}) + ")")
            except Exception as e:
                step["error"] = "pick: " + str(e)[:110]
                picks.append(step)
                break
            if not pick:
                step["none_left"] = True
                picks.append(step)
                break
            step.update({k: pick[k] for k in ("kind", "tag", "role", "nested") if k in pick})
            url_before = page.url
            try:
                step["mechanism"] = await ASG._act(page, pick)
            except Exception as e:
                step["act_error"] = str(e).split("\n")[0][:110]
            await page.wait_for_timeout(ASG.SETTLE_MS)
            if page.url.split("#")[0] != url_before.split("#")[0]:
                step["navigated"] = True
                picks.append(step)
                break
            try:
                v = await page.evaluate(ASG.STAGE_VERIFY)
            except Exception as e:
                step["error"] = "verify: " + str(e)[:110]
                picks.append(step)
                break
            used[pick["kind"]] += 1
            step["flipped"] = bool(v.get("flipped"))
            if not step["flipped"]:
                picks.append(step)
                continue
            try:
                r = await read_once(page, cdp, "s%d" % i, seen_names, examples,
                                    recheck=RECHECK)
            except Exception as e:
                step["error"] = "read: " + str(e)[:110]
                picks.append(step)
                break
            r["kind"] = pick["kind"]
            # Mark each disagreement row as NEW when its OURS identity was never seen at
            # an earlier stage -- the population that exists only because of the click.
            nm = _names_of(r)
            for row in r["rows"]:
                row["new"] = (row["ours"] not in seen_names)
            # The denominator for NEW must be counted the same way, over EVERY compared
            # row rather than only the disagreements, or the NEW agreement rate would be
            # a ratio whose halves come from different populations (#22's lesson).
            r["new_names"] = len(nm - seen_names)
            seen_names |= nm
            r.pop("_all_ours", None)
            out["reads"].append(r)
            picks.append(step)
        out["picks"] = picks

        if plant_at_end:
            try:
                out["fire"] = await read_once(page, cdp, "fire", set(), 12, plant=True)
            except Exception as e:
                out["fire"] = {"error": str(e)[:160]}
        out["seconds"] = round(time.time() - t0, 1)
        return out
    finally:
        try:
            await ctx.close()
        except Exception:
            pass


# --------------------------------------------------------------------------------------
# THE HOVER ARM. #117 named "name correctness on hover-revealed content" as one of two
# shapes that fall between the three stage rulers: #94 drives hover for PRESENCE and
# REACHABILITY (528 revealed controls on 38 sites, 0 owning no row, find at 0.913) and
# the name ORACLE has never driven hover at all. So for every control that exists only
# while something is hovered, nobody has asked whether the name we print is the name
# Chrome computes -- and that population is the one most likely to be odd, because a
# hover menu is built by a component library at the moment of hover.
#
# WHY THIS IS NOT A THIRD DRIVER. `AHS.HOVER_PICK` / `HOVER_DIFF` / `APPEARED_MMIDS` /
# `MAX_HOVERS` / `SETTLE_MS` are #94's, used verbatim. The only thing written here is the
# sequencing: hover -> verify something appeared -> read_once (which is the oracle) ->
# resolve the revealed mmids. #94's docstring makes the rule this rests on explicit -- a
# CSS `:hover` submenu declares no state flip so the PRODUCT must not guess at one
# (PRINCIPLES 1), but a PROBE may put the mouse somewhere deliberately and then ask what
# happened.
# --------------------------------------------------------------------------------------
async def hover_one(browser, name, url, arch, lang, examples, plant=False):
    t0 = time.time()
    ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True,
                                    user_agent=None, locale="en-US")
    base = {"site": name, "url": url, "archetype": arch, "lang": lang}
    try:
        await ctx.add_init_script(path=TAG_JS)
        page = await ctx.new_page()
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=GOTO_MS)
            status = resp.status if resp else None
        except Exception as e:
            return dict(base, error="goto: " + str(e)[:120])
        try:
            await page.wait_for_load_state("networkidle", timeout=7000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)
        cdp = await ctx.new_cdp_session(page)
        try:
            r0 = await read_once(page, cdp, "s0", None, examples, recheck=RECHECK)
        except Exception as e:
            return dict(base, error="read: " + str(e)[:160], status=status)
        out = dict(base, status=status, reads=[r0], hovers=[])
        seen_names = _names_of(r0)
        r0.pop("_all_ours", None)

        async def still_hovered():
            try:
                return await page.evaluate(
                    "() => { const r = window.__abHover && window.__abHover.el;"
                    " try { return !!(r && r.matches(':hover')); } catch (e) { return null; } }")
            except Exception:
                return None

        done = 0
        for attempt in range(AHS.MAX_HOVERS):
            h = {"attempt": attempt}
            try:
                pick = await page.evaluate(AHS.HOVER_PICK + "(" + json.dumps({}) + ")")
            except Exception as e:
                h["pick_error"] = str(e)[:140]
                out["hovers"].append(h)
                break
            if not pick or pick.get("none"):
                h["no_candidates"] = True
                h.update({k: pick.get(k) for k in ("sheetsRead", "sheetsBlocked", "cssRoots")}
                         if pick else {})
                out["hovers"].append(h)
                break
            h.update({"tier": pick["tier"], "why": pick.get("why"), "tag": pick.get("tag"),
                      "sheets_read": pick.get("sheetsRead"),
                      "sheets_blocked": pick.get("sheetsBlocked")})
            # Mark used BEFORE moving, so a crash cannot loop on one element (#94).
            await page.evaluate("() => { if (window.__abHover) "
                                "window.__abHoverUsed.push(window.__abHover.el); }")
            try:
                await page.mouse.move(pick["x"], pick["y"])
                await page.wait_for_timeout(120)
                await page.mouse.move(pick["x"] + 1, pick["y"] + 1)
            except Exception as e:
                h["hover_error"] = str(e)[:110]
                out["hovers"].append(h)
                continue
            await page.wait_for_timeout(AHS.SETTLE_MS)
            try:
                diff = await page.evaluate(AHS.HOVER_DIFF)
            except Exception as e:
                h["diff_error"] = str(e)[:110]
                out["hovers"].append(h)
                continue
            h.update({"appeared": len(diff["appeared"]), "n_before": diff["nBefore"],
                      "n_now": diff["nNow"],
                      "off_screen_arrivals": diff.get("offScreenArrivals", 0),
                      "root_still_hovered": diff["rootStillHovered"],
                      "in_root": sum(1 for d in diff["appeared"] if d["inRoot"])})
            if not diff["appeared"]:
                # NOTHING APPEARED IS RECORDED, NOT SKIPPED. A run whose reveals all came
                # back empty must be visible as such rather than as a clean small sample
                # -- #94's own reason for counting this, and the failure mode PRINCIPLES 15
                # describes for a detector that cannot fire.
                h["nothing_appeared"] = True
                out["hovers"].append(h)
                continue

            # SOMETHING APPEARED. Measure while the mouse is still there. The hover is
            # asked of the DOM both before and after the read, because `read_once` runs a
            # collector evaluate, a declarations evaluate and two CDP calls, which on a
            # large page is hundreds of milliseconds -- long enough for a menu to shut.
            h["hover_before_read"] = await still_hovered()
            raw = {}

            async def _hov():
                mm = await page.evaluate(AHS.APPEARED_MMIDS)
                raw["mm"] = mm
                # UNFILTERED ON PURPOSE. Filtering to elements still visible NOW would
                # quietly drop any element whose menu shut between the collector run and
                # this call, shrinking the population instead of reporting that it did --
                # a zero for the wrong reason. Visibility and connectedness are recorded
                # beside the set so a diluted read is detectable at aggregation time.
                return [m.get("mmid") for m in mm if m.get("mmid")]

            try:
                r = await read_once(page, cdp, "h%d" % done, seen_names, examples,
                                    recheck=RECHECK, hov_fn=_hov)
            except Exception as e:
                h["read_error"] = str(e)[:140]
                out["hovers"].append(h)
                continue
            h["hover_after_read"] = await still_hovered()
            mm = raw.get("mm") or []
            h.update({"revealed_with_mmid": sum(1 for m in mm if m.get("mmid")),
                      "revealed_connected": sum(1 for m in mm if m.get("connected")),
                      "revealed_visible": sum(1 for m in mm if m.get("visible")),
                      "hov_as_entries": r.get("hov_as_entries"),
                      "hov_error": r.get("hov_error"),
                      "tier_used": pick["tier"]})
            r["hover"] = h
            for row in r["rows"]:
                row["new"] = (row["ours"] not in seen_names)
            seen_names |= _names_of(r)
            r.pop("_all_ours", None)
            out["reads"].append(r)
            out["hovers"].append(h)
            done += 1
            if plant:
                # THE LIVE FIRING PROOF FOR THIS ARM, planted on the HOVER-REVEALED rows
                # only. A sentinel on an arbitrary row proves the comparator fires and
                # says nothing about whether this driver ever reached the population.
                hv = [m.get("mmid") for m in mm if m.get("mmid")]
                try:
                    out.setdefault("fire", []).append(
                        await read_once(page, cdp, "fire%d" % done, set(), 12,
                                        plant=True, plant_only=hv))
                except Exception as e:
                    out.setdefault("fire", []).append({"error": str(e)[:160]})
            try:
                await page.mouse.move(2, VIEWPORT["height"] - 2)
                await page.wait_for_timeout(350)
            except Exception:
                pass
            if done >= 2:
                break
        out["seconds"] = round(time.time() - t0, 1)
        return out
    finally:
        try:
            await ctx.close()
        except Exception:
            pass


def _names_of(r):
    """Every identity this read compared or would have compared -- used only to decide the
    NEW population, so it must not depend on whether the row agreed."""
    s = set()
    for row in r.get("rows") or []:
        if row.get("ours"):
            s.add(row["ours"])
    s |= set(r.get("_all_ours") or [])
    return s


def usable(r):
    if "error" in r or not r.get("reads"):
        return False
    r0 = r["reads"][0]
    if (r0.get("ax_info") or {}).get("axNodes", 0) <= 0:
        return False
    return r0.get("counts", {}).get("compared", 0) >= 5


# --------------------------------------------------------------------------------------
def aggregate(rs):
    ok = [r for r in rs if usable(r)]
    tot = collections.Counter()
    per_stage = collections.defaultdict(collections.Counter)
    per_pop = collections.defaultdict(collections.Counter)
    per_script = collections.defaultdict(collections.Counter)
    per_kind = collections.defaultdict(collections.Counter)
    cls_rows = collections.defaultdict(list)
    per_src = collections.defaultdict(collections.Counter)
    # PER STAGE x SRC, and PER POPULATION x SRC x CLASS. `per_stage` rolls up `counts`,
    # which pools every `src` together, so the figure the headline quotes (`src=name`)
    # could not be read per stage at all -- it had to be recomputed by walking three
    # levels of the artefact. Both rollups live here now so the stage table and the
    # revealed/carried table come from the same place as every other number.
    per_stage_src = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    per_pop_src = collections.Counter()
    # PAIRED WITHIN-READ, which is the design the pooled comparison cannot have. Both
    # arms come from ONE read of ONE page, so site composition, page weight and the depth
    # a site happened to reach cancel by construction rather than by argument.
    paired_reads = []
    cls_role_tot = collections.Counter()
    role_named_tot = collections.Counter()
    fmt_drift = 0
    ax_fail = []
    for r in ok:
        script = AGL.SCRIPT_OF.get(r["lang"], r["lang"])
        for idx, rd in enumerate(r["reads"]):
            c = collections.Counter(rd["counts"])
            tot.update(c)
            per_stage[rd["stage"]].update(c)
            per_script[script].update(c)
            if idx > 0:
                per_kind[rd.get("kind") or "?"].update(c)
            fmt_drift += rd.get("fmt_drift", 0)
            for k, v in (rd.get("by_src") or {}).items():
                per_src[k].update(v)
                per_stage_src[rd["stage"]][k].update(v)
            per_pop_src.update(rd.get("by_pop") or {})
            cls_role_tot.update(rd.get("cls_roles") or {})
            role_named_tot.update(rd.get("role_named") or {})
            if (rd.get("ax_info") or {}).get("error"):
                ax_fail.append((r["site"], rd["stage"], rd["ax_info"]["error"]))
            # THREE POPULATIONS, the same split #92 uses: s0, `new` (the identity never
            # appeared at an earlier stage, so the control exists because of the click)
            # and `carried` (the control arm -- always there, page now interacted with).
            # If `new` and `carried` fall together the cause is the page after
            # interaction; if only `new` falls, it is the revealed control itself.
            if idx == 0:
                per_pop["s0"]["compared"] += c.get("compared", 0)
                per_pop["s0"]["exact"] += c.get("exact", 0)
            else:
                per_pop["post"]["compared"] += c.get("compared", 0)
                per_pop["post"]["exact"] += c.get("exact", 0)
                for pop in ("new", "carried", "unnamed"):
                    per_pop[pop]["compared"] += c.get(pop + "_compared", 0)
                    per_pop[pop]["exact"] += c.get(pop + "_exact", 0)
                bp = rd.get("by_pop") or {}
                paired_reads.append({
                    "site": r["site"], "stage": rd["stage"], "kind": rd.get("kind") or "?",
                    "new_c": c.get("new_compared", 0), "new_e": c.get("new_exact", 0),
                    "car_c": c.get("carried_compared", 0), "car_e": c.get("carried_exact", 0),
                    "new_name_c": bp.get("new|name|compared", 0),
                    "new_name_e": bp.get("new|name|exact", 0),
                    "car_name_c": bp.get("carried|name|compared", 0),
                    "car_name_e": bp.get("carried|name|exact", 0),
                    # `chrome-empty` is the permanent floor (#114: 51% of the residue is
                    # a role that forbids a name, where printing the author's string is
                    # what #74 requires). Carried separately so a rate gap can be shown
                    # to be the floor's SHARE moving rather than names getting worse.
                    "new_name_ce": bp.get("new|name|c:chrome-empty", 0),
                    "car_name_ce": bp.get("carried|name|c:chrome-empty", 0),
                })
            for row in rd["rows"]:
                if idx > 0:
                    per_pop["new" if row.get("new") else "carried"][row["cls"]] += 1
                if len(cls_rows[row["cls"]]) < 60:
                    cls_rows[row["cls"]].append(dict(row, site=r["site"]))
    # PER-SITE `src` ROLLUP. The comparable statistic for this probe is the
    # per-SITE median, not the pooled rate -- #93 measured 0.9134 pooled against
    # 0.9722 median on ONE corpus, a 7pp gap from composition alone, so a pooled
    # figure cannot be compared across two samples. That rollup existed only
    # inside `sites[].reads[].by_src`, so computing it meant walking three
    # levels, and the obvious first attempt (`site["per_src"]`) returned "0
    # sites" and read as missing data rather than as the wrong path. #107.
    for r in ok:
        acc: dict = {}
        for rd in r.get("reads") or []:
            for k, v in (rd.get("by_src") or {}).items():
                tgt = acc.setdefault(k, collections.Counter())
                tgt.update(v)
        r["per_src"] = {k: dict(v) for k, v in sorted(acc.items())}
    _med = []
    for r in ok:
        n = (r.get("per_src") or {}).get("name") or {}
        if n.get("compared", 0) >= 20:
            _med.append(n["exact"] / n["compared"])
    _med.sort()
    return {
        "sites_attempted": len(rs), "sites_usable": len(ok),
        "name_rate_per_site_median": (
            None if not _med else
            (_med[len(_med) // 2] if len(_med) % 2
             else (_med[len(_med) // 2 - 1] + _med[len(_med) // 2]) / 2)),
        "name_rate_sites_counted": len(_med),
        "totals": dict(tot), "per_stage": {k: dict(v) for k, v in sorted(per_stage.items())},
        "per_pop": {k: dict(v) for k, v in per_pop.items()},
        "per_src": {k: dict(v) for k, v in sorted(per_src.items())},
        "per_stage_src": {st: {k: dict(v) for k, v in sorted(d.items())}
                          for st, d in sorted(per_stage_src.items())},
        "per_pop_src": dict(per_pop_src),
        "paired_reads": paired_reads,
        "cls_roles": dict(cls_role_tot.most_common()),
        "role_named": dict(role_named_tot.most_common()),
        "per_script": {k: dict(v) for k, v in sorted(per_script.items())},
        "per_kind": {k: dict(v) for k, v in sorted(per_kind.items())},
        "fmt_drift": fmt_drift, "ax_failures": ax_fail[:20],
        "examples": {k: v for k, v in cls_rows.items()},
        "unusable": [{"site": r["site"], "why": r.get("error") or "ax/compared too small: %s"
                      % json.dumps((r.get("reads") or [{}])[0].get("ax_info", {}))}
                     for r in rs if not usable(r)],
    }


def _wilson(k, n, z=1.96):
    """A proportion needs an interval, and the rule of three is NOT it unless k is 0 --
    quoting a rule-of-three bound beside a non-zero count would be the twelfth way an
    instrument here has lied (MEASUREMENT.md Sec.3)."""
    if not n:
        return (0.0, 1.0)
    phat = k / n
    d = 1 + z * z / n
    c = (phat + z * z / (2 * n)) / d
    h = z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, c - h), min(1.0, c + h))


def _rate(c):
    comp = c.get("compared", 0)
    if not comp:
        return None
    return round(c.get("exact", 0) / comp, 4)


def stage_report(paths):
    """THE NAME AXIS AT STAGE > 0, on the HEADLINE population and PAIRED.

    `report()` already prints a `by stage` table and a `new`/`carried` row. Neither can
    answer the two questions this mode exists for, and the reason is shape:

      * `by stage` rolls up `counts`, which POOLS every `src`. The headline statistic is
        `src=name` -- `src=text` is a row printing the element's own text, a weaker claim
        the legend spells out, and Chrome has no name at all for the roles most of those
        carry. A pooled stage table therefore moves with the text/name MIX per stage and
        says nothing about the number 0.9766 quotes.
      * `new` vs `carried` is POOLED over every site and read, so the arms are two
        different mixtures of pages. #93 reported 0.6628 against 0.7370 from exactly that
        shape, said most of it was composition, and could not settle it; a 34-site rerun
        with corrected code reversed the sign.

    So both tables here are built to remove composition rather than to argue about it:
    the stage gradient is PAIRED PER SITE (a site's own s0 against its own deepest read,
    so only sites that reached that depth contribute to both arms), and revealed/carried
    is PAIRED PER READ (both arms from one read of one page). A pooled figure is printed
    beside each one so the size of the composition effect is visible rather than implied.
    """
    rs = []
    for p in paths:
        rs += json.loads(Path(p).read_text(encoding="utf-8"))["sites"]
    agg = aggregate(rs)
    ok = [r for r in rs if usable(r)]
    o = ["usable %d of %d attempted; fmt_drift=%d; ax_failures=%d" % (
        agg["sites_usable"], agg["sites_attempted"], agg["fmt_drift"],
        len(agg["ax_failures"]))]

    pss = agg.get("per_stage_src") or {}
    if not pss:
        o.append("\n*(artefact predates `per_stage_src`; recomputing from reads)*")
        pss = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
        for r in ok:
            for rd in r.get("reads") or []:
                for k, v in (rd.get("by_src") or {}).items():
                    pss[rd["stage"]][k].update(v)

    # PER-SITE MEDIAN PER STAGE, beside the pooled rate. #93 measured a 7pp gap between
    # pooled and per-site median on ONE corpus, from composition alone, so a pooled figure
    # cannot be compared across stages either -- the stages are different site mixtures.
    med = collections.defaultdict(list)
    for r in ok:
        for rd in r.get("reads") or []:
            n = (rd.get("by_src") or {}).get("name") or {}
            if n.get("compared", 0) >= 20:
                med[rd["stage"]].append(n["exact"] / n["compared"])

    def _median(xs):
        if not xs:
            return None
        xs = sorted(xs)
        h = len(xs) // 2
        return xs[h] if len(xs) % 2 else (xs[h - 1] + xs[h]) / 2

    o.append("\n### `src=name` per stage (pooled -- read with the paired table below)\n")
    o.append("| stage | reads | name compared | name exact | **name agree (pooled)** | "
             "**per-site median** | sites n>=20 | text compared | text agree |")
    o.append("|---|---|---|---|---|---|---|---|---|")
    nreads = collections.Counter(rd["stage"] for r in ok for rd in r.get("reads") or [])
    for st in sorted(pss):
        n = dict((pss[st].get("name") or {}))
        t = dict((pss[st].get("text") or {}))
        m = _median(med.get(st) or [])
        o.append("| %s | %d | %d | %d | **%s** | **%s** | %d | %d | %s |" % (
            st, nreads.get(st, 0), n.get("compared", 0), n.get("exact", 0),
            _rate(n), "n/a" if m is None else "%.4f" % m, len(med.get(st) or []),
            t.get("compared", 0), _rate(t)))

    # CLASS HISTOGRAM PER STAGE, on the headline population. The rate alone cannot say
    # WHICH disagreement moved, and `chrome-empty` is the permanent floor (#114) rather
    # than a defect -- so a stage where the floor's share rises is not a stage where names
    # got worse.
    o.append("\n### `src=name` disagreement classes per stage (exact, uncapped)\n")
    classes = [c for c in DISAGREE if any((pss[st].get("name") or {}).get(c)
                                          for st in pss)]
    o.append("| stage | disagree | %s |" % " | ".join(classes))
    o.append("|" + "---|" * (len(classes) + 2))
    for st in sorted(pss):
        n = dict((pss[st].get("name") or {}))
        dis = n.get("compared", 0) - n.get("exact", 0)
        o.append("| %s | %d | %s |" % (
            st, dis, " | ".join(str(n.get(c, 0)) for c in classes)))

    # THE STAGE GRADIENT, PAIRED. Deeper stages are reached by FEWER and DIFFERENT sites,
    # so a pooled decline across the stage column is the sample changing under the
    # statistic. Pairing a site against ITSELF is what separates the two.
    pairs = []
    for r in ok:
        rds = r.get("reads") or []
        if len(rds) < 2:
            continue
        def _nm(rd):
            n = (rd.get("by_src") or {}).get("name") or {}
            return n.get("compared", 0), n.get("exact", 0)
        c0, e0 = _nm(rds[0])
        cL, eL = _nm(rds[-1])
        if c0 >= 20 and cL >= 20:
            pairs.append((r["site"], rds[-1]["stage"], e0 / c0, eL / cL))
    o.append("\n### the stage gradient, PAIRED per site (s0 vs that site's deepest read)\n")
    if pairs:
        diffs = [p[3] - p[2] for p in pairs]
        w = sum(1 for x in diffs if x > 1e-9)
        l = sum(1 for x in diffs if x < -1e-9)
        o.append("| | |\n|---|---|")
        o.append("| sites with >=20 `src=name` rows at both ends | %d |" % len(pairs))
        o.append("| deeper read BETTER | %d |" % w)
        o.append("| s0 better | %d |" % l)
        o.append("| identical | %d |" % (len(pairs) - w - l))
        o.append("| median difference | %+.4f |" % statistics.median(diffs))
        o.append("| mean difference | %+.4f |" % statistics.mean(diffs))
        worst = sorted(pairs, key=lambda p: p[3] - p[2])[:5]
        o.append("\nLargest falls: " + ", ".join(
            "`%s` %s %.3f->%.3f" % (p[0], p[1], p[2], p[3]) for p in worst))
    else:
        o.append("*(no site had >=20 `src=name` rows at both ends)*")

    # REVEALED vs CARRIED, PAIRED PER READ.
    pr = agg.get("paired_reads")
    o.append("\n### is a control REVEALED by an interaction named worse? (paired per read)\n")
    if not pr:
        o.append("*(artefact predates `paired_reads` -- re-run to get this table)*")
    else:
        # The `src=name` arm uses a LOWER per-read threshold than the all-src arm, and the
        # reason is power rather than taste: a read carries ~9 revealed rows in total and
        # only a fraction of those resolve an accessible name, so a >=10 cut would report
        # n=0 and read as "no effect" when it means "not measured". The count at each
        # threshold is printed so the reader can see which it is (PRINCIPLES 15 -- a
        # comparison that cannot fire also asserts that nothing is wrong).
        for label, kc, ke, cc, ce, floor, thr in (
                ("all `src`", "new_c", "new_e", "car_c", "car_e", None, 10),
                ("`src=name` only", "new_name_c", "new_name_e",
                 "car_name_c", "car_name_e", ("new_name_ce", "car_name_ce"), 5)):
            rows = [x for x in pr if x[kc] >= thr and x[cc] >= thr]
            avail = {t: sum(1 for x in pr if x[kc] >= t and x[cc] >= t)
                     for t in (3, 5, 10, 20)}
            o.append("\n**%s**, reads with >=%d rows in BOTH arms: n=%d "
                     "(reads available at >=3/5/10/20: %d/%d/%d/%d)\n"
                     % (label, thr, len(rows),
                        avail[3], avail[5], avail[10], avail[20]))
            if not rows:
                o.append("*(none)*")
                continue
            diffs = [x[ke] / x[kc] - x[ce] / x[cc] for x in rows]
            w = sum(1 for x in diffs if x > 1e-9)
            l = sum(1 for x in diffs if x < -1e-9)
            nc = sum(x[kc] for x in rows); ne = sum(x[ke] for x in rows)
            cc_ = sum(x[cc] for x in rows); ce_ = sum(x[ce] for x in rows)
            o.append("| | |\n|---|---|")
            o.append("| revealed BETTER than carried, in the same read | %d |" % w)
            o.append("| carried better | %d |" % l)
            o.append("| identical | %d |" % (len(rows) - w - l))
            o.append("| **median paired difference** | **%+.4f** |" % statistics.median(diffs))
            o.append("| mean paired difference | %+.4f |" % statistics.mean(diffs))
            o.append("| sign test, two-tailed | p = %.4f |" % _sign_p(w, l))
            o.append("| pooled over these reads: revealed | %d/%d = %.4f |" % (ne, nc, ne / nc))
            o.append("| pooled over these reads: carried | %d/%d = %.4f |" % (ce_, cc_, ce_ / cc_))
            if floor:
                fn = sum(x[floor[0]] for x in rows); fc = sum(x[floor[1]] for x in rows)
                dn = nc - ne; dcar = cc_ - ce_
                o.append("| `chrome-empty` share of the revealed disagreements | %s |"
                         % ("%d/%d = %.1f%%" % (fn, dn, 100 * fn / dn) if dn else "n/a"))
                o.append("| `chrome-empty` share of the carried disagreements | %s |"
                         % ("%d/%d = %.1f%%" % (fc, dcar, 100 * fc / dcar) if dcar else "n/a"))
        pp = agg.get("per_pop") or {}
        o.append("\n**The pooled figures for the same question** (what #93 reported), "
                 "so the size of the composition effect is readable:\n")
        o.append("| population | compared | exact | agree |\n|---|---|---|---|")
        for k in ("s0", "post", "new", "carried", "unnamed"):
            v = pp.get(k) or {}
            if v.get("compared"):
                o.append("| %s | %d | %d | %s |" % (k, v["compared"], v["exact"], _rate(v)))

    # IS THERE A DISAGREEMENT CLASS THAT ONLY APPEARS AFTER AN INTERACTION?
    #
    # A control revealed by opening a menu or a dialog can be named through a path that
    # never runs at first paint -- an `aria-labelledby` pointing into a portal, a dialog
    # naming itself from its own heading. Nobody has looked, and the rate tables above
    # cannot show it: they are rates, and a brand-new mechanism with 40 instances moves a
    # rate by nothing while being exactly the thing worth finding.
    #
    # Counted from `cls_roles` (class x Chrome-role x src), which the read function builds
    # UNCAPPED, rather than from `rows`, which is capped per read and in document order --
    # a head slice of each page would make a mechanism's absence at s0 unfalsifiable
    # (PRINCIPLES 16).
    s0c, postc = collections.Counter(), collections.Counter()
    s0n = postn = 0
    for r in ok:
        for idx, rd in enumerate(r.get("reads") or []):
            tgt = s0c if idx == 0 else postc
            tgt.update(rd.get("cls_roles") or {})
            if idx == 0:
                s0n += (rd.get("counts") or {}).get("compared", 0)
            else:
                postn += (rd.get("counts") or {}).get("compared", 0)
    if s0n and postn:
        o.append("\n### a disagreement shape that is NEW after an interaction?\n")
        o.append("Rate per 10,000 compared rows, so the two columns are comparable "
                 "despite s0 being read on every site. "
                 "`compared` s0=%d post=%d.\n" % (s0n, postn))
        o.append("| class \\| Chrome role \\| src | s0 n | s0 /10k | post n | post /10k | ratio |")
        o.append("|---|---|---|---|---|---|")
        rows_ = []
        for k in set(s0c) | set(postc):
            a_, b_ = s0c.get(k, 0), postc.get(k, 0)
            if a_ + b_ < 25:
                continue
            ra, rb = 10000.0 * a_ / s0n, 10000.0 * b_ / postn
            rows_.append((rb / ra if ra else float("inf"), k, a_, ra, b_, rb))
        for ratio, k, a_, ra, b_, rb in sorted(rows_, reverse=True)[:12]:
            o.append("| `%s` | %d | %.2f | %d | %.2f | %s |" % (
                k, a_, ra, b_, rb, "inf" if ratio == float("inf") else "%.2fx" % ratio))

    # OPEN.md ITEM 21: does a name's declared PROVENANCE go stale across two reads?
    # Its falsifier, verbatim: "if a corpus pass finds zero controls whose name provenance
    # CHANGES between two reads of one document, this is a latent defect with no instances
    # and should be recorded as such rather than fixed." A staged run IS that pass.
    have_synth = any(rd.get("synth_map") for r in ok for rd in r.get("reads") or [])
    if have_synth:
        stale = []          # synth stayed, the NAME under it changed
        cleared = 0         # the marker went away by itself
        kept_same = 0
        seen_twice = 0      # THE DENOMINATOR. Without it this prints "0 of 0", which is
                            # vacuous and reads exactly like "0 of many" -- the falsifier
                            # only fires if the population it ran over is non-empty
                            # (PRINCIPLES 15, 16).
        for r in ok:
            rds = r.get("reads") or []
            if len(rds) < 2:
                continue
            first = {}
            for idx, rd in enumerate(rds):
                sm = rd.get("synth_map") or {}
                for mm, v in sm.items():
                    s, _, ident = v.partition("|")
                    if mm not in first:
                        first[mm] = (idx, s, ident)
                        continue
                    i0, s0_, id0 = first[mm]
                    seen_twice += 1
                    if s == s0_ and ident != id0:
                        kept_same += 1
                        if len(stale) < 40:
                            stale.append((r["site"], rds[idx]["stage"], s, id0, ident))
                    elif s != s0_:
                        cleared += 1
        o.append("\n### `OPEN.md` item 21: does a `(post-key)` claim go STALE across reads?\n")
        o.append("| | |\n|---|---|")
        o.append("| sites with >= 2 reads of one document | %d |"
                 % sum(1 for r in ok if len(r.get("reads") or []) > 1))
        o.append("| elements carrying a synth marker, seen at 2+ reads | %d |" % seen_twice)
        o.append("| **marker UNCHANGED while the name under it CHANGED** | **%d** |" % kept_same)
        o.append("| marker itself changed between reads | %d |" % cleared)
        if stale:
            o.append("\nExamples (site, stage, marker, name then -> name now):\n")
            for s in stale[:8]:
                o.append("- `%s` %s `%s`: %r -> %r" % s)
        else:
            o.append("\n**Zero instances** — item 21's own falsifier fires: a latent "
                     "defect with no instances on this corpus, to be recorded rather "
                     "than fixed.")

    # PER-POPULATION x SRC, pooled but EXACT (not the head-sliced `rows` list).
    pps = agg.get("per_pop_src") or {}
    if pps:
        o.append("\n### population x src, exact and uncapped\n")
        o.append("| population | src | compared | exact | agree | top disagreement classes |")
        o.append("|---|---|---|---|---|---|")
        seen = sorted({(k.split("|")[0], k.split("|")[1]) for k in pps})
        for pop, src in seen:
            n = pps.get("%s|%s|compared" % (pop, src), 0)
            e = pps.get("%s|%s|exact" % (pop, src), 0)
            if n < 20:
                continue
            cls = sorted(((k.split("|")[2][2:], v) for k, v in pps.items()
                          if k.startswith("%s|%s|c:" % (pop, src))),
                         key=lambda x: -x[1])[:3]
            o.append("| %s | %s | %d | %d | %.4f | %s |" % (
                pop, src, n, e, e / n if n else 0,
                ", ".join("%s %d" % c for c in cls) or "-"))
    return "\n".join(o)


# --------------------------------------------------------------------------------------
# THE HOVER REPORT. Every table here is built from `by_hov`, which is exact and uncapped
# and whose two arms come from ONE read of ONE page -- so site composition, page weight
# and which sites happened to offer a hover menu cancel by construction. #115 established
# that design after its own pooled revealed-vs-carried table compared two different
# mixtures of pages, and #93's version of the same question reversed sign between runs.
# --------------------------------------------------------------------------------------
def _hov_cell(bh, arm, src):
    """compared / exact / per-class, for one arm and one src, out of a `by_hov` dict."""
    pre = arm + "|" + src + "|"
    comp = bh.get(pre + "compared", 0)
    ex = bh.get(pre + "exact", 0)
    cls = {k[len(pre) + 2:]: v for k, v in bh.items()
           if k.startswith(pre + "c:")}
    return comp, ex, cls


def _hov_reads(sites):
    """Every read that carries a hover population, with its funnel intact.

    Gated on the project's own `usable()` for the same reason the funnel is: a site that
    rendered three elements is not a site this ruler measured."""
    out = []
    for s in sites:
        if not usable(s):
            continue
        for r in s.get("reads") or []:
            if "by_hov" not in r:
                continue
            out.append((s, r))
    return out


def hover_report(paths):
    o = []
    sites = []
    for p in paths:
        sites += json.loads(Path(p).read_text(encoding="utf-8")).get("sites") or []
    attempted = len(sites)
    errored = [s for s in sites if "error" in s]
    # `usable` IS THE PROJECT'S, NOT A LOOSER ONE WRITTEN HERE. The first version of this
    # report used `"error" not in s`, which counts a site that rendered three elements as
    # a pass -- a restated definition drifting from the one every other table in this file
    # uses (PRINCIPLES 17; #36 records the permitted-drop-reason set drifting exactly this
    # way, and #117 found an instance this week).
    ok = [s for s in sites if usable(s)]
    thin = [s for s in sites if "error" not in s and not usable(s)]
    reads = _hov_reads(sites)
    with_reveal = {s["site"] for s, _r in reads}
    # ------------------------------------------------------------------ the funnel
    # PRINTED FIRST AND NEVER FOLDED INTO THE RATE. #117's brief asks how big the
    # measurable population actually is, and a rate over a population nobody stated is the
    # shape PRINCIPLES 16 is about. #94 reached 63 reveals on 38 of 120 sites; if the
    # oracle arm reaches a fraction of that, this table is why the reader knows.
    nothing = sum(1 for s in ok for h in (s.get("hovers") or []) if h.get("nothing_appeared"))
    nocand = sum(1 for s in ok for h in (s.get("hovers") or []) if h.get("no_candidates"))
    revealed = sum(r.get("hov_revealed", 0) for _s, r in reads)
    as_ent = sum(r.get("hov_as_entries", 0) for _s, r in reads)
    hov_err = [(_s["site"], r.get("hov_error")) for _s, r in reads if r.get("hov_error")]
    fmt_drift = sum(r.get("fmt_drift", 0) for s in ok for r in (s.get("reads") or []))
    axf = sum(1 for s in ok for r in (s.get("reads") or [])
              if (r.get("ax_info") or {}).get("error"))
    o.append("## The measurable population\n")
    o.append("| | |")
    o.append("|---|---|")
    o.append("| sites attempted | %d |" % attempted)
    o.append("| sites UNMEASURED -- goto/read failed, named below | %d |" % len(errored))
    o.append("| sites that rendered too little to compare (not a pass) | %d |" % len(thin))
    o.append("| sites usable (`usable()`, the same rule every other table here uses) | %d |"
             % len(ok))
    o.append("| **sites where a hover revealed something** | **%d** |" % len(with_reveal))
    o.append("| **reveals measured (one oracle read each)** | **%d** |" % len(reads))
    o.append("| hover attempts that revealed nothing | %d |" % nothing)
    o.append("| sites offering no hover candidate at all | %d |" % nocand)
    o.append("| **controls observed to appear** | **%d** |" % revealed)
    o.append("| ...of those, listed as entries by the collector | %d |" % as_ent)
    _hovc = sum(v for _s, r in reads for k, v in (r.get("by_hov") or {}).items()
                if k.startswith("hov|") and k.endswith("|compared"))
    # THE GAP IS STATED AND ITS CAUSES LISTED, never attributed (PRINCIPLES 6). An entry
    # drops out of the COMPARED population for reasons `read_once` already counts but does
    # not split by this axis: the row's identity is blanked on purpose (#74's rule), the
    # row leads with value=/placeholder= so it shows no identity, Chrome ignores the node,
    # or neither side produced a string. Which one applies here is not measured.
    o.append("| ...of those, reaching the COMPARED population | %d |" % _hovc)
    if as_ent > _hovc:
        o.append("| &nbsp;&nbsp;the %d-row gap: blanked identity, contents-only row, "
                 "Chrome-ignored node, or both sides empty — NOT attributed here | |"
                 % (as_ent - _hovc))
    o.append("| `fmt_drift` (non-zero voids every number below) | %d |" % fmt_drift)
    o.append("| reads whose AX call errored | %d |" % axf)
    # THE TALLY RECONCILES, PRINTED RATHER THAN LEFT TO BE RE-DERIVED. For every arm and
    # every `src`, `compared` must equal `exact` plus the sum of the per-class counts --
    # the numerator and the denominator of every rate below come from one population, and
    # #22 records a figure going wrong because they did not. A mismatch here voids the
    # tables the same way a non-zero `fmt_drift` does.
    tot = collections.Counter()
    for _s, r in reads:
        tot.update(r.get("by_hov") or {})
    recon_bad = []
    for arm in ("hov", "pre"):
        for src in {k.split("|")[1] for k in tot}:
            c = tot.get("%s|%s|compared" % (arm, src), 0)
            e = tot.get("%s|%s|exact" % (arm, src), 0)
            cl = sum(v for k, v in tot.items() if k.startswith("%s|%s|c:" % (arm, src)))
            if c != e + cl:
                recon_bad.append("%s|%s %d != %d" % (arm, src, c, e + cl))
    o.append("| **compared == exact + classes, every arm x src** | **%s** |"
             % ("OK" if not recon_bad else "*** MISMATCH: %s ***" % recon_bad))
    if hov_err:
        o.append("| **hov_fn ERRORS (population is understated)** | %s |" % hov_err[:6])
    # THE ONE CONFOUND THIS DRIVER HAS, QUANTIFIED RATHER THAN ARGUED. The before/after
    # set is every visible on-screen control, so anything that arrives during the 900ms
    # settle for a reason OTHER than the hover -- a lazy-load, a carousel advancing -- is
    # counted as revealed. An element INSIDE the hovered root cannot be that. The share
    # is therefore a bound on how much of the population is really the hover, and it is
    # printed because the alternative is a sentence saying it is probably fine.
    inroot = sum(r["hover"].get("in_root", 0) for _s, r in reads if r.get("hover"))
    app = sum(r["hover"].get("appeared", 0) for _s, r in reads if r.get("hover"))
    o.append("| **appeared INSIDE the hovered element** (bound on the lazy-load confound) "
             "| **%d of %d = %.1f%%** |" % (inroot, app, 100.0 * inroot / max(1, app)))
    tiers = collections.Counter(r["hover"]["tier_used"] for _s, r in reads
                                if r.get("hover", {}).get("tier_used"))
    o.append("| tier that produced the reveal | %s |" % json.dumps(dict(tiers)))
    surv = collections.Counter(
        "after=%s" % r.get("hover", {}).get("hover_after_read") for _s, r in reads)
    o.append("| hover still held AFTER the oracle read | %s |" % json.dumps(dict(surv)))

    # ---------------------------------------------------------------- the `src` MIX
    # PRINTED BEFORE THE RATES, because it is the first thing that can explain a gap
    # between them and #115 had to refute exactly this reading of its own pooled table
    # (its answer was 21.8% against 23.4%, i.e. not a mix effect). It is also how big the
    # HEADLINE population is: `src=name` is the only arm 0.9766 quotes, and if a hover
    # menu is made of plain links named by their own text then that population is small
    # by NATURE rather than by sampling, which is a different sentence.
    mix = {"hov": collections.Counter(), "pre": collections.Counter()}
    for _s, r in reads:
        for k, v in (r.get("by_hov") or {}).items():
            arm, src, rest = k.split("|", 2)
            if rest == "compared":
                mix[arm][src] += v
    if mix["hov"]:
        o.append("\n## Where the identity came from, in each arm\n")
        o.append("| `src` | hover n | hover share | carried n | carried share |")
        o.append("|---|---|---|---|---|")
        th, tp = sum(mix["hov"].values()), sum(mix["pre"].values())
        for src in sorted(set(mix["hov"]) | set(mix["pre"]),
                          key=lambda k: -mix["hov"].get(k, 0)):
            o.append("| `%s` | %d | %.1f%% | %d | %.1f%% |" % (
                src, mix["hov"].get(src, 0), 100.0 * mix["hov"].get(src, 0) / max(1, th),
                mix["pre"].get(src, 0), 100.0 * mix["pre"].get(src, 0) / max(1, tp)))
        o.append("| **total compared** | **%d** | | **%d** | |" % (th, tp))

    # ------------------------------------------------- the headline, within-read paired
    o.append("\n## `src=name` on hover-revealed rows, against the carried rows of the SAME read\n")
    for src in ("name", "text"):
        hc = he = pc = pe = 0
        hcls, pcls = collections.Counter(), collections.Counter()
        # SITES PER CLASS, exact (taken from `by_hov`, not from the capped `rows`). A
        # ratio produced by ONE site is a site effect wearing a population effect's
        # clothes -- #115 caught exactly that reading `live-label-not-clone`'s 16-of-31 at
        # one depth as a stage premium. Printing the site count beside every ratio makes
        # that unmissable instead of a thing the reader has to go and check.
        hcls_sites = collections.defaultdict(set)
        per_site = collections.defaultdict(lambda: [0, 0, 0, 0])
        paired = []
        for s, r in reads:
            bh = r.get("by_hov") or {}
            a, b, ac = _hov_cell(bh, "hov", src)
            c, d, cc = _hov_cell(bh, "pre", src)
            hc += a; he += b; pc += c; pe += d
            hcls.update(ac); pcls.update(cc)
            for k in ac:
                hcls_sites[k].add(s["site"])
            ps = per_site[s["site"]]
            ps[0] += a; ps[1] += b; ps[2] += c; ps[3] += d
            if a >= 5 and c >= 5:
                paired.append((b / a, d / c))
        if not hc:
            o.append("**no `src=%s` rows in the hover arm at all** -- nothing to report.\n" % src)
            continue
        lo, hi = _wilson(he, hc)
        plo, phi = _wilson(pe, pc)
        o.append("### src=%s\n" % src)
        o.append("| arm | compared | exact | **agree** | 95% CI |")
        o.append("|---|---|---|---|---|")
        o.append("| **hover-revealed** | %d | %d | **%.4f** | %.4f-%.4f |" % (hc, he, he / hc, lo, hi))
        o.append("| carried (same reads) | %d | %d | **%.4f** | %.4f-%.4f |" % (
            pc, pe, pe / pc if pc else 0.0, plo, phi))
        o.append("| difference | | | **%+.4f** | |" % ((he / hc) - (pe / pc if pc else 0)))
        # AND THE SAME RATE WITH THE DISPOSITIONED CLASSES REMOVED FROM BOTH ARMS. #114
        # took the whole residue apart class by class: `chrome-empty` is Chrome's ROLE
        # forbidding a name while we print the author's string (#74 requires that),
        # `punctuation-only` is a `::before` glyph or a zero-width mark where ours is the
        # better string for this reader, and `case-only` is CSS `text-transform`, which
        # `find` folds. None of the three is a wrong name. Removing them from the
        # DENOMINATOR as well as the numerator is what makes this a rate rather than a
        # credit, and it is EXACT because the class totals are uncapped.
        _ND = ("chrome-empty", "punctuation-only", "case-only")
        hnd = sum(hcls.get(k, 0) for k in _ND)
        pnd = sum(pcls.get(k, 0) for k in _ND)
        if (hc - hnd) > 0 and (pc - pnd) > 0:
            o.append("| **excluding `chrome-empty`/`punctuation-only`/`case-only`** "
                     "(#114: none is a wrong name) | | | | |")
            o.append("| &nbsp;&nbsp;hover | %d | %d | **%.4f** | |"
                     % (hc - hnd, he, he / (hc - hnd)))
            o.append("| &nbsp;&nbsp;carried | %d | %d | **%.4f** | |"
                     % (pc - pnd, pe, pe / (pc - pnd)))
        # PER-SITE MEDIAN, because #93 measured a 7pp pooled-vs-median gap from composition
        # alone and the project's headline quotes the median.
        meds_h = [v[1] / v[0] for v in per_site.values() if v[0] >= 20]
        meds_p = [v[3] / v[2] for v in per_site.values() if v[2] >= 20]
        if meds_h:
            o.append("| per-site median, hover (n>=20 rows) | %d sites | | **%.4f** | |"
                     % (len(meds_h), statistics.median(meds_h)))
        if meds_p:
            o.append("| per-site median, carried (n>=20 rows) | %d sites | | **%.4f** | |"
                     % (len(meds_p), statistics.median(meds_p)))
        # LEAVE-ONE-SITE-OUT, AND IT IS NOT OPTIONAL HERE. A pooled rate over an arm whose
        # rows come from a handful of sites is a measurement of those sites. #73 quotes
        # Mind2Web's headline with a LOSO span for the same reason, and #115's own history
        # on revealed-vs-carried is a sign that reversed between runs. This drops the
        # largest contributing sites one at a time and prints what happens: if the
        # difference survives, it is a population effect; if it inverts, it is those sites.
        order = sorted(per_site, key=lambda k: -per_site[k][0])
        if len([k for k in order if per_site[k][0]]) >= 2:
            o.append("\n**Leave-one-site-out** (the hover arm's rows come from %d site(s); "
                     "the top 3 carry %.1f%% of them):\n"
                     % (len([k for k in order if per_site[k][0]]),
                        100.0 * sum(per_site[k][0] for k in order[:3]) / max(1, hc)))
            o.append("| dropped | hover n | hover | carried | difference |")
            o.append("|---|---|---|---|---|")
            for n in range(0, min(4, len(order))):
                drop = set(order[:n])
                a = sum(per_site[k][0] for k in per_site if k not in drop)
                b = sum(per_site[k][1] for k in per_site if k not in drop)
                c = sum(per_site[k][2] for k in per_site if k not in drop)
                dd = sum(per_site[k][3] for k in per_site if k not in drop)
                if not a or not c:
                    continue
                o.append("| %s | %d | %.4f | %.4f | **%+.4f** |" % (
                    ("none" if not n else ", ".join("`%s`" % x for x in order[:n])),
                    a, b / a, dd / c, b / a - dd / c))
        if paired:
            w = sum(1 for a, b in paired if a > b)
            l = sum(1 for a, b in paired if a < b)
            t = sum(1 for a, b in paired if a == b)
            o.append("\n**Paired within one read** (both arms >=5 `src=%s` rows): "
                     "hover better %d, carried better %d, identical %d, "
                     "median paired difference %+.4f, sign test p = %.4f\n"
                     % (src, w, l, t,
                        statistics.median([a - b for a, b in paired]), _sign_p(w, l)))
        # AND THE SAME TEST AT SITE LEVEL, because two reads of one site are not two
        # independent pairs: the CARRIED arm is the same page both times, so pooling reads
        # treats one site's agreement as two observations. A sign test over correlated
        # pairs reports a p-value it has not earned.
        sp = [(v[1] / v[0], v[3] / v[2]) for v in per_site.values() if v[0] >= 5 and v[2] >= 5]
        if sp:
            w = sum(1 for x, y in sp if x > y)
            l = sum(1 for x, y in sp if x < y)
            o.append("**Paired per SITE** (both arms >=5 rows): hover better %d, "
                     "carried better %d, identical %d, median %+.4f, p = %.4f\n"
                     % (w, l, len(sp) - w - l,
                        statistics.median([x - y for x, y in sp]), _sign_p(w, l)))
        # ------------------------------------------------------- the class histogram
        o.append("\n| class | hover n | **hover sites** | hover /10k | carried n | carried /10k | ratio |")
        o.append("|---|---|---|---|---|---|---|")
        for cls in sorted(set(hcls) | set(pcls),
                          key=lambda k: -(hcls.get(k, 0) / max(1, hc))):
            a, c = hcls.get(cls, 0), pcls.get(cls, 0)
            ra = 10000.0 * a / hc
            rc = 10000.0 * c / pc if pc else 0.0
            o.append("| `%s` | %d | **%d** | %.1f | %d | %.1f | %s |" % (
                cls, a, len(hcls_sites.get(cls, ())), ra, c, rc,
                ("%.2fx" % (ra / rc)) if rc else ("inf" if ra else "-")))
        o.append("")
    # ------------------------------------------------ over-representation, ALL src pooled
    # The rate tables above cannot show a brand-new MECHANISM: 40 instances of one move a
    # rate by nothing while being the thing worth finding (#115's section 8). This is the
    # same cut on class x Chrome-role, which is where a component library's shape shows up.
    o.append("\n## Classes over-represented on hover-revealed content (all `src`, per 10k)\n")
    hall = pall = 0
    hk, pk = collections.Counter(), collections.Counter()
    hk_sites = collections.defaultdict(set)
    for _s, r in reads:
        bh = r.get("by_hov") or {}
        for k, v in bh.items():
            arm, src, rest = k.split("|", 2)
            tgt_n = (hk, pk)[arm == "pre"]
            if rest == "compared":
                if arm == "hov":
                    hall += v
                else:
                    pall += v
                continue
            if rest.startswith("c:"):
                tgt_n[rest[2:] + "|" + src] += v
                if arm == "hov":
                    hk_sites[rest[2:] + "|" + src].add(_s["site"])
    if hall and pall:
        o.append("| class \\| src | hover n | **sites** | hover /10k | carried /10k | ratio |")
        o.append("|---|---|---|---|---|---|")
        rows = []
        for k in set(hk) | set(pk):
            ra = 10000.0 * hk.get(k, 0) / hall
            rc = 10000.0 * pk.get(k, 0) / pall
            rows.append((ra / rc if rc else (1e9 if ra else 0), k, hk.get(k, 0), ra, rc))
        for ratio, k, n, ra, rc in sorted(rows, reverse=True)[:14]:
            o.append("| `%s` | %d | **%d** | %.1f | %.1f | %s |" % (
                k, n, len(hk_sites.get(k, ())), ra, rc,
                ("%.2fx" % ratio) if rc else ("inf" if ra else "-")))
        o.append("\nhover compared (all src) %d, carried %d\n" % (hall, pall))
        # EXAMPLES FOR THE TOP CLASSES, from the saved rows, LABELLED AS A SAMPLE. The
        # rows list is capped and in document order, so this is an illustration of a
        # mechanism and never a count -- the two are kept apart throughout (#114's rule).
        # WHAT THE DIFFERENCE IS MADE OF. A class name says which SHAPE the two strings
        # are in, not which side is right -- #114 dispositioned `punctuation-only` as OURS
        # BETTER precisely because the characters Chrome adds there are `::before` glyphs
        # and zero-width marks that identify nothing. So the characters are the evidence,
        # and categorising them is what separates "a class is over-represented because we
        # are right more often here" from "a new defect concentrates here". Computed over
        # the saved rows, so it is a SAMPLE of the mechanism and never a count of it.
        def _chars(s):
            k = collections.Counter()
            for ch in s:
                o_ = ord(ch)
                if 0xE000 <= o_ <= 0xF8FF or 0xF0000 <= o_ <= 0x10FFFD:
                    k["private-use glyph (an icon font's ::before)"] += 1
                elif ch in "​‌‍﻿ 　":
                    k["invisible/space mark"] += 1
                elif ch.isspace():
                    k["whitespace"] += 1
                elif unicodedata.category(ch).startswith(("P", "S")):
                    k["punctuation/symbol"] += 1
                else:
                    k["letter or digit"] += 1
            return k
        mech = collections.defaultdict(collections.Counter)
        msites = collections.defaultdict(set)
        for s, r in reads:
            for x in r.get("rows") or []:
                if not x.get("hov"):
                    continue
                a, bq = _ws(x["ours"]), _ws(x["theirs"])
                extra = bq.replace(a, "") if a and a in bq else ""
                missing = a.replace(bq, "") if bq and bq in a else ""
                key = x["cls"] + "|" + x["src"]
                msites[key].add(s["site"])
                if extra:
                    for kk, v in _chars(extra).items():
                        mech[key]["CHROME HAS, we do not: " + kk] += v
                elif missing:
                    for kk, v in _chars(missing).items():
                        mech[key]["WE HAVE, Chrome does not: " + kk] += v
                else:
                    mech[key]["neither string contains the other"] += 1
        if mech:
            o.append("\n### What the hover-arm disagreements are MADE OF "
                     "(saved rows: a sample of the mechanism, not a count)\n")
            for key in sorted(mech, key=lambda k: -sum(mech[k].values())):
                o.append("* `%s` (%d site(s)): %s" % (
                    key, len(msites[key]),
                    json.dumps(dict(mech[key].most_common(4)), ensure_ascii=False)))
        o.append("\n### Example hover-revealed disagreements (saved rows: a SAMPLE, not a census)\n")
        seen_eg = collections.Counter()
        for s, r in reads:
            for x in r.get("rows") or []:
                if not x.get("hov"):
                    continue
                key = x["cls"] + "|" + x["src"]
                if seen_eg[key] >= 2:
                    continue
                seen_eg[key] += 1
                o.append("* `%s` `%s` **%s** ours=%r theirs=%r" % (
                    x["cls"], x["src"], s["site"], x["ours"][:60], x["theirs"][:60]))
    # ---------------------------------------------------- the LIVE firing proof (--fire)
    # The fixture proof (`--hover-selftest`) shows the arm can fire; this shows it firing
    # on REAL pages, on rows a REAL hover revealed. A planted name only proves something
    # when it reached the COMPARED population -- one Chrome ignores, or one the row
    # blanks, was never a question -- so the bar is "every comparable planted row reported
    # the sentinel, and at least one row somewhere was comparable" (PRINCIPLES 15).
    fires = [(s["site"], f) for s in sites for f in (s.get("fire") or [])]
    if fires:
        moved = reached = 0
        missed, errs = [], []
        for site, f in fires:
            if "error" in f:
                errs.append(site)
                continue
            disp = f.get("planted_disposition") or {}
            moved += len(f.get("planted") or [])
            rr = [m for m, dd in disp.items() if dd.startswith("compared:")]
            reached += len(rr)
            missed += [(site, m) for m in rr if "SENTINEL" not in disp[m]]
        ok = reached > 0 and not missed and not errs
        o.append("\n## LIVE firing proof (`--fire`): sentinels planted on HOVER-REVEALED rows\n")
        o.append("| | |")
        o.append("|---|---|")
        o.append("| reveals carrying a plant | %d |" % len(fires))
        o.append("| rows whose name was moved | %d |" % moved)
        o.append("| ...of those, reaching the COMPARED population | %d |" % reached)
        o.append("| **sentinels the comparator FAILED to report** | **%d** %s |"
                 % (len(missed), missed[:5]))
        o.append("| errored reveals | %d %s |" % (len(errs), errs[:4]))
        o.append("| **verdict** | **%s** |" % ("PASS" if ok else "FAIL"))

    # ------------------------------------------------------------- what was not measured
    if errored:
        o.append("\n## UNMEASURED, named (PRINCIPLES: a refused site is never a pass)\n")
        for s in errored[:60]:
            o.append("* `%s` -- %s" % (s["site"], s["error"][:100]))
    return "\n".join(o)


def _sign_p(w, l):
    """Two-tailed sign test. Reported beside every paired count because a 38/38 split and
    a 38/8 split read the same way in prose and are not the same evidence."""
    n = w + l
    if n == 0:
        return 1.0
    import math
    k = min(w, l)
    c = sum(math.comb(n, i) for i in range(k + 1))
    return min(1.0, 2 * c / (2 ** n))


def report(paths):
    rs = []
    for p in paths:
        rs += json.loads(Path(p).read_text(encoding="utf-8"))["sites"]
    agg = aggregate(rs)
    ok = [r for r in rs if usable(r)]
    o = ["usable %d of %d attempted; fmt_drift=%d" % (
        agg["sites_usable"], agg["sites_attempted"], agg["fmt_drift"])]
    t = agg["totals"]
    o.append("\n### headline\n")
    o.append("| | |\n|---|---|")
    for k in ("compared", "exact", "not-in-ax-tree", "chrome-ignored", "blanked-row",
              "blanked-chrome-named", "contents-only-row", "both-empty",
              "oracle_rows_rechecked", "oracle_rows_moved"):
        o.append("| %s | %d |" % (k, t.get(k, 0)))
    o.append("| **exact agreement** | **%s** |" % _rate(t))

    def tab(title, d, keycol="group"):
        o.append("\n### " + title + "\n")
        cols = ["compared", "exact"] + [c for c in DISAGREE if any(v.get(c) for v in d.values())]
        o.append("| %s | %s | agree |" % (keycol, " | ".join(cols)))
        o.append("|" + "---|" * (len(cols) + 2))
        for k, v in sorted(d.items()):
            o.append("| %s | %s | %s |" % (
                k, " | ".join(str(v.get(c, 0)) for c in cols), _rate(v)))

    # THE SHARP QUESTION. If `new` and `carried` fall together the cause is the page after
    # an interaction; if only `new` falls, it is the revealed control itself (#92's split).
    o.append("\n### population: is a control revealed BY an interaction named worse?\n")
    o.append("| population | compared | exact | agree | 95% CI (Wilson) |")
    o.append("|---|---|---|---|---|")
    for k in ("s0", "post", "new", "carried", "unnamed"):
        v = agg["per_pop"].get(k) or {}
        n, e = v.get("compared", 0), v.get("exact", 0)
        if not n:
            continue
        lo, hi = _wilson(e, n)
        o.append("| %s | %d | %d | %s | %.4f-%.4f |" % (k, n, e, _rate(v), lo, hi))
    tab("by WHERE OUR IDENTITY CAME FROM", agg["per_src"], "src")
    tab("by stage", agg["per_stage"], "stage")
    tab("by interaction kind (stage >= 1)", agg["per_kind"], "kind")
    tab("by script family", agg["per_script"], "script")
    # WHICH SIDE MATCHES THE SCREEN. For the classes where neither spec text nor taste
    # settles it (a separator, a decorative glyph), the element's rendered text is a third
    # oracle that is a measurement rather than an opinion. Only the sampled example rows
    # carry it, and that is stated rather than smoothed over.
    all_rows = collections.defaultdict(list)
    for r in ok:
        for rd in r["reads"]:
            for row in rd["rows"]:
                all_rows[row["cls"]].append(row)
    o.append("\n### adjudicated against the RENDERED text (every SAVED row, not the capped examples)\n")
    o.append("NOTE: `innerText` does NOT include ::before/::after generated content, so for a")
    o.append("class whose difference IS a CSS icon glyph this column is an artefact of the oracle,")
    o.append("not evidence. It is faithful for the separator and the title-vs-content questions.\n")
    o.append("| class | rows with rendered text | ours matches screen | chrome matches screen | neither |")
    o.append("|---|---|---|---|---|")
    for c in DISAGREE:
        ex = [r for r in all_rows.get(c, []) if r.get("rendered")]
        if not ex:
            continue
        a = sum(1 for r in ex if _ws(r["ours"]) == _ws(r["rendered"]))
        bb = sum(1 for r in ex if _ws(r["theirs"]) == _ws(r["rendered"]))
        n = sum(1 for r in ex if _ws(r["ours"]) != _ws(r["rendered"])
                and _ws(r["theirs"]) != _ws(r["rendered"]))
        o.append("| %s | %d | %d | %d | %d |" % (c, len(ex), a, bb, n))
    roles = agg.get("cls_roles") or {}
    if roles:
        # IS CHROME EVEN ALLOWED TO HAVE A NAME HERE? ARIA 1.2 says a role outside the
        # name-from-content table takes its name from the AUTHOR only, and `generic`
        # prohibits naming altogether -- so a `chrome-empty` on such a role is the spec
        # working, not a name we got wrong.
        g = collections.Counter()
        for k, v in roles.items():
            cls, role, src = k.split("|")
            g[(cls, "name-from-content" if role in NAME_FROM_CONTENT
               else "author-only/prohibited")] += v
        o.append("\n### is Chrome even PERMITTED a name here? (ARIA 1.2 role table)\n")
        o.append("| class | role permits name-from-content | n |")
        o.append("|---|---|---|")
        for (cls, kind), v in sorted(g.items(), key=lambda kv: -kv[1]):
            o.append("| %s | %s | %d |" % (cls, kind, v))
        o.append("\n### disagreement class x CHROME'S ROLE x our identity source (exact, uncapped)\n")
        o.append("| class | chrome role | our src | n |")
        o.append("|---|---|---|---|")
        for k, v in sorted(roles.items(), key=lambda kv: -kv[1])[:40]:
            o.append("| %s | %s |" % (" | ".join(k.split("|")), v))
    o.append("\n### disagreement classes\n")
    o.append("| class | n | share of compared |")
    o.append("|---|---|---|")
    comp = t.get("compared", 0) or 1
    for c in DISAGREE:
        if t.get(c):
            o.append("| %s | %d | %.4f |" % (c, t[c], t[c] / comp))
    for c in DISAGREE:
        ex = agg["examples"].get(c) or []
        if not ex:
            continue
        o.append("\n#### %s (%d)\n" % (c, t.get(c, 0)))
        for r in ex[:8]:
            o.append("- `%s` %s[%s] ours=%s chrome=%s screen=%s src=%s decl=%s" % (
                r["site"], r["tag"], r.get("ax_role") or "", json.dumps(r["ours"], ensure_ascii=False),
                json.dumps(r["theirs"], ensure_ascii=False),
                json.dumps(r.get("rendered", ""), ensure_ascii=False)[:60], r["src"],
                json.dumps(r["decl"], ensure_ascii=False)[:160]))
    o.append("\nunusable / not measured:")
    for u in agg["unusable"]:
        o.append("- %s: %s" % (u["site"], u["why"]))
    return "\n".join(o)


def drift(a_rs, b_rs):
    A = {r["site"]: r for r in a_rs if usable(r)}
    B = {r["site"]: r for r in b_rs if usable(r)}
    both = sorted(set(A) & set(B))
    per = {}
    ta = collections.Counter()
    tb = collections.Counter()
    deltas = []
    for n in both:
        ca = collections.Counter()
        cb = collections.Counter()
        for rd in A[n]["reads"]:
            ca.update(rd["counts"])
        for rd in B[n]["reads"]:
            cb.update(rd["counts"])
        ta.update(ca)
        tb.update(cb)
        ra, rb = _rate(ca), _rate(cb)
        if ra is not None and rb is not None:
            deltas.append(abs(ra - rb))
        per[n] = {"compared": [ca.get("compared", 0), cb.get("compared", 0)],
                  "agree": [ra, rb], "reads": [len(A[n]["reads"]), len(B[n]["reads"])]}
    deltas.sort()
    return {
        "sites_compared": len(both),
        "pooled_agree": [_rate(ta), _rate(tb)],
        "pooled_delta": (round(abs((_rate(ta) or 0) - (_rate(tb) or 0)), 5)
                         if both else None),
        "per_site_abs_delta_median": deltas[len(deltas) // 2] if deltas else None,
        "per_site_abs_delta_p90": deltas[int(len(deltas) * 0.9)] if deltas else None,
        "same_read_count": sum(1 for v in per.values() if v["reads"][0] == v["reads"][1]),
        "per_site": per,
    }


# --------------------------------------------------------------------------------------
# THE FIRING PROOF. A fixture that makes the two derivations differ BY SPEC, a control that
# must agree, and a planted arm that cannot depend on the collector's behaviour at all.
# --------------------------------------------------------------------------------------
SELFTEST_HTML = r"""
<!doctype html><meta charset=utf-8><title>name fixture</title>
<style>.blk{display:block}</style>
<!-- CONTROLS: these must AGREE, or the probe reports disagreement on everything -->
<button id=c1>Save changes</button>
<a href="#x" id=c2>Documentation</a>
<input id=c3 aria-label="Email address">
<label for=c4>Password</label><input id=c4 type=password>
<button id=c5 aria-label="Close dialog">x</button>

<!-- SEPARATOR: AccName 1.2 step 2F. Chrome concatenates inline element children with no
     separator; we space-delimit (#28). A wrong NUMBER in the identity slot. -->
<div role=button tabindex=0 id=d1><span>4</span><span>9秒39</span></div>
<div role=button tabindex=0 id=d2><span class=blk>Alpha</span><span class=blk>Beta</span></div>

<!-- NESTED CONTROL'S LABEL: #34's measured shape -- Chrome's name absorbs a nested
     button's aria-label where ours stops at the link's own text. -->
<a href="#z" id=d3>Deadline <button aria-label="Why this deadline: it is fixed">?</button></a>

<!-- TITLE vs the HTML name ATTRIBUTE (#37): title is an AccName source, `name` is the key
     the form posts under and is not one at all. -->
<input id=d4 name="query" title="検索語を入力してください">

<!-- aria-labelledby pointing at HIDDEN text: AccName says the referenced text IS used. -->
<button id=d5 aria-labelledby="hid">Visible text</button><span id=hid hidden>Hidden name wins</span>

<!-- #114'S CLASS F -- `title` against name-from-content, where the content is an icon
     font's generated glyph. The element renders NO text of its own, so we take the
     title and are USEFUL; Chrome takes the content and is SPEC-CORRECT and useless.
     Measured at 139 elements, ALL of which render no text, 22 of them (16%) a
     Private-Use-Area glyph exactly like this one -- which is why #114 recorded the class
     as a DECIDED don't-build rather than a deferred item. The `font-family` is left
     alone deliberately: setting it to `none` suppresses the generated box and Chrome's
     name comes back EMPTY, which turns a two-sided disagreement into a one-sided one
     and the proof into something weaker than it looks. -->
<style>.ico::before{content:"\e978"} .ico{display:inline-block;width:20px;height:20px}</style>
<a href="#f" id=d6 class=ico title="Facebook"></a>
"""


async def _selftest():
    fails = []
    report_rows = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport=VIEWPORT)
        await ctx.add_init_script(path=TAG_JS)
        pg = await ctx.new_page()
        await pg.set_content(SELFTEST_HTML)
        await pg.wait_for_timeout(250)
        cdp = await ctx.new_cdp_session(pg)

        r = await read_once(pg, cdp, "s0", None, 60)
        ax = r["ax_info"]
        if ax.get("axNodes", 0) <= 0:
            fails.append("getFullAXTree returned NO nodes -- the domains were not enabled "
                         "(#34), so every zero below is a silence rather than a measurement")
        if ax.get("mapped", 0) <= 0:
            fails.append("no element carried an mmid: the collector did not run")
        if r["fmt_drift"]:
            fails.append("fmt_drift=%d -- ours_identity has drifted from _fmtLine" % r["fmt_drift"])
        if not r["counts"].get("compared"):
            fails.append("nothing was compared at all")
        by_ours = {row["ours"]: row for row in r["rows"]}
        report_rows = r["rows"]

        # 1. THE COMPARATOR FIRES ON A GENUINE SPEC DISAGREEMENT -- one we have
        #    MEASURED AND DELIBERATELY NOT FIXED, which is the only kind that
        #    can serve as a standing firing proof.
        #
        #    THIS CHECK EXPIRED ONCE AND THAT IS WHY IT IS WORDED THIS WAY. It
        #    used to require the AccName SEPARATOR case (`<span>4</span>
        #    <span>9秒39</span>`, #28's shape) to come back `whitespace-only`.
        #    #93 made `_contentName` display-aware so inline children
        #    concatenate exactly as Chrome does -- and the two now AGREE, so the
        #    row vanished and the selftest FAILED on its own success. Verified
        #    before rewriting rather than assumed: on this fixture both
        #    separator shapes, inline and block, produce no row at all, and the
        #    comparison is 11 compared / 10 exact. That is `MEASUREMENT.md`'s
        #    probe-lifetime rule: an A/B whose firing proof is a DEFECT expires
        #    when the defect ships a fix.
        #
        #    IT HAS NOW BEEN REWRITTEN A SECOND TIME, FOR THE SAME REASON ONE
        #    STEP EARLIER. It stood on #34's `chrome-superset` shape -- Chrome's
        #    name absorbs a nested control's `aria-label` where ours stops at the
        #    link's own text. #34 is exactly the gap `child-declared-name` closes,
        #    so standing the proof on it meant the proof's life was tied to a
        #    change already in flight. MEASURED rather than assumed, by running
        #    `_selftest` with AGL.COLLECT swapped for each candidate arm:
        #
        #        shipped   PASS   chrome-superset  'Deadline ?'
        #        narrow    PASS   chrome-superset  'Deadline ?'
        #        guarded   PASS   chrome-superset  'Deadline ?'
        #        broad     FAIL   -- no disagreement at all
        #
        #    So the NARROW arm would have left it standing and the SPEC-FAITHFUL
        #    one kills it. "It happens to survive the arm we shipped" is not a
        #    property to rely on.
        #
        #    THE ANCHOR IS NOW #114'S CLASS F, and the reason it is the right one
        #    is that it can never be closed. Class F is `title` against
        #    name-from-content where the content is an icon font's PUA glyph:
        #    following the spec there would replace a real identity ("Facebook")
        #    with a character that identifies nothing, on a sixth of the class,
        #    which #114 measured and recorded as a DECIDED don't-build. A proof
        #    anchored on a decision outlives a proof anchored on a backlog item.
        #    It is also the same permanent floor #114 names: a metric reading
        #    1.000 here would mean we had stopped printing identities that #74
        #    requires, so this disagreement is load-bearing rather than residual.
        #
        #    #34's shape is still in the fixture and still REPORTED, because it
        #    is the shape the next reader will want to see, and because losing it
        #    silently is how the first expiry went unnoticed. It is no longer
        #    what the pass depends on.
        _classf = [x for x in r["rows"]
                   if "Facebook" in (x["ours"] or "") and (x["theirs"] or "").strip()]
        if not _classf:
            fails.append("the comparator reported NO genuine disagreement on a "
                         "shape that is known to disagree AND decided not to fix "
                         "(#114's class F, `title` against an icon-font glyph): %s"
                         % [(x["ours"], x["theirs"], x["cls"]) for x in r["rows"]][:6])
        _nested = [x for x in r["rows"] if "Deadline" in (x["ours"] or "")]
        report_nested = [(x["ours"], x["theirs"], x["cls"]) for x in _nested]
        # 2. THE CONTROLS MUST AGREE. Without this a probe that reports EVERYTHING as a
        #    disagreement would pass check 1 and the agreement rate would be meaningless.
        for want in ("Save changes", "Documentation", "Email address", "Password", "Close dialog"):
            if want in by_ours:
                fails.append("control %r was reported as a disagreement (%s vs %s)"
                             % (want, by_ours[want]["ours"], by_ours[want]["theirs"]))
        # 3. THE PLANTED ARM: independent of what the collector happens to do.
        r2 = await read_once(pg, cdp, "plant", None, 60, plant=True)
        if not r2["planted"]:
            fails.append("the planted arm tagged nothing")
        planted_rows = [x for x in r2["rows"] if PLANT in x["theirs"]]
        # ONLY the planted mmids that REACHED the compared population can prove anything;
        # one that Chrome ignores or that the row blanks was never a question. Counting
        # those as failures would make the firing proof depend on the fixture's shape.
        disp = r2["planted_disposition"]
        reached = [m for m, d in disp.items() if d.startswith("compared:")]
        missed = [m for m in reached if "SENTINEL" not in disp[m]]
        if len(reached) < 3:
            fails.append("the planted arm reached only %d compared rows (need >= 3): %s"
                         % (len(reached), disp))
        if missed:
            fails.append("PLANTED NAMES DID NOT FIRE for %s -- %s"
                         % (missed, {m: disp[m] for m in missed}))
        await b.close()

    print("selftest", "PASS" if not fails else "FAIL")
    print(json.dumps({
        "ax_info": ax, "counts": r["counts"],
        # REPORTED, NOT REQUIRED -- see check 1. #34's nested-control shape is the one a
        # reader will look for, and it is the one `child-declared-name` is about, so it
        # is printed whether or not it still disagrees.
        "nested_label_34": report_nested,
        "disagreements": [{k: x[k] for k in ("ours", "theirs", "cls", "tag", "src")}
                          for x in report_rows],
        "planted_moved": len(r2["planted"]), "planted_reported": len(planted_rows),
        "planted_disposition": r2["planted_disposition"],
        "failures": fails}, indent=1, ensure_ascii=False))
    return 0 if not fails else 1


HOVER_SELFTEST_HTML = r"""
<!doctype html><meta charset=utf-8><title>hover name fixture</title>
<style>
  /* TIER 1 fires on this: the page's OWN CSS says hovering #menu changes `display`. */
  #menu ul { display: none; position: absolute; left: 10px; top: 60px;
             list-style: none; margin: 0; padding: 0; background: #fff; }
  #menu:hover ul { display: block; }
  #menu { padding: 20px; display: inline-block; border: 1px solid #ccc; }
  /* #114's CLASS F, on a HOVER-REVEALED row: `title` against name-from-content where the
     content is an icon font's Private-Use-Area glyph. A DECIDED don't-build, so a proof
     anchored on it cannot expire the way this file's main selftest expired twice. */
  .ico::before { content: "\e978" }
  .ico { display: inline-block; width: 22px; height: 22px }
  /* THE NEGATIVE CONTROL. Tier 1 picks this too (the rule touches `opacity`), the mouse
     lands on it, and NOTHING is revealed. Without it a driver that silently reveals
     nothing is indistinguishable from one that works -- which is the specific hazard of
     this arm, since an empty population yields a beautiful clean rate. */
  #decoy:hover { opacity: 0.6 }
  #decoy { padding: 14px; margin-top: 140px; border: 1px dashed #999 }
</style>
<nav id=menu><span>Products</span>
  <ul>
    <li><a href="#a" id=r1>Revealed Alpha</a></li>
    <li><a href="#b" id=r2 aria-label="Revealed Beta">beta</a></li>
    <li><a href="#c" id=r3 class=ico title="Revealed Facebook"></a></li>
  </ul>
</nav>
<button id=p1>Page Button</button>
<div id=decoy>Decoy, reveals nothing</div>
"""


async def _hover_selftest():
    """PROVE THE HOVER ARM FIRES, which a clean rate over an empty population cannot.

    Four checks, and the two controls are the point:
      1. a CSS `:hover` submenu is DRIVEN and its controls reach the COMPARED population
         under the `hov` arm -- not merely "a read happened";
      2. the comparator reports a genuine disagreement on a HOVER-REVEALED row
         (#114's class F, decided don't-build, so it cannot expire);
      3. CONTROL -- the hover-revealed rows whose names agree are NOT reported as
         disagreements, or a probe that flags everything would pass check 2;
      4. CONTROL -- a hover that reveals nothing is reported as `nothing_appeared`
         rather than producing a clean read over zero rows.
    """
    fails, notes = [], {}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport=VIEWPORT)
        await ctx.add_init_script(path=TAG_JS)
        pg = await ctx.new_page()
        await pg.route("https://hover.invalid/**", lambda r: asyncio.ensure_future(
            r.fulfill(status=200, content_type="text/html; charset=utf-8",
                      body=HOVER_SELFTEST_HTML)))
        # A REAL NAVIGATION, not set_content: `add_init_script` only affects documents
        # created after it and set_content reuses the existing about:blank, which is the
        # vacuous-fixture shape C14 exists for (#31 found 25 pages in that state).
        await pg.goto("https://hover.invalid/fixture")
        await pg.wait_for_timeout(250)
        cdp = await ctx.new_cdp_session(pg)

        r0 = await read_once(pg, cdp, "s0", None, 60)
        seen = _names_of(r0)
        got, nothing, planted = [], 0, None
        for _i in range(AHS.MAX_HOVERS):
            pick = await pg.evaluate(AHS.HOVER_PICK + "({})")
            if not pick or pick.get("none"):
                break
            await pg.evaluate("() => { if (window.__abHover) "
                              "window.__abHoverUsed.push(window.__abHover.el); }")
            await pg.mouse.move(pick["x"], pick["y"])
            await pg.wait_for_timeout(120)
            await pg.mouse.move(pick["x"] + 1, pick["y"] + 1)
            await pg.wait_for_timeout(AHS.SETTLE_MS)
            diff = await pg.evaluate(AHS.HOVER_DIFF)
            if not diff["appeared"]:
                nothing += 1
                await pg.mouse.move(2, VIEWPORT["height"] - 2)
                await pg.wait_for_timeout(250)
                continue
            raw = {}

            async def _hov():
                mm = await pg.evaluate(AHS.APPEARED_MMIDS)
                raw["mm"] = mm
                return [m.get("mmid") for m in mm if m.get("mmid")]

            r = await read_once(pg, cdp, "h%d" % len(got), seen, 60, hov_fn=_hov)
            r["_hovmm"] = [m.get("mmid") for m in (raw.get("mm") or []) if m.get("mmid")]
            got.append(r)
            # THE PLANT HAPPENS WHILE THE MOUSE IS STILL HELD, and the first version of
            # this did not: moving away first shuts the menu, every revealed element
            # measures 0x0, `_PLANT_JS`'s size guard skips all of them and the arm reports
            # "tagged nothing". That read as a broken plant and was a broken FIXTURE --
            # the vacuous-fixture class pointed at the firing proof itself.
            if planted is None:
                planted = await read_once(pg, cdp, "fire", set(), 60, plant=True,
                                          plant_only=r["_hovmm"])
            await pg.mouse.move(2, VIEWPORT["height"] - 2)
            await pg.wait_for_timeout(250)

        # ---- 1. the arm reached the compared population
        hov_comp = sum(v for r in got for k, v in (r.get("by_hov") or {}).items()
                       if k.startswith("hov|") and k.endswith("|compared"))
        notes["reveals"] = len(got)
        notes["hov_compared"] = hov_comp
        notes["hov_revealed"] = [r.get("hov_revealed") for r in got]
        notes["hov_as_entries"] = [r.get("hov_as_entries") for r in got]
        if not got:
            fails.append("no hover revealed anything at all -- the driver never fired")
        if hov_comp < 2:
            fails.append("the hover arm reached only %d compared rows (need >= 2): "
                         "a rate over this population would be meaningless" % hov_comp)

        # ---- 1b. THE COMPARATOR ARM EXISTS TOO. Every number this arm produces is a
        #      hover-vs-carried comparison taken inside one read, so an empty `pre` arm
        #      would leave the headline with nothing to compare against while every check
        #      above still passed.
        pre_comp = sum(v for r in got for k, v in (r.get("by_hov") or {}).items()
                       if k.startswith("pre|") and k.endswith("|compared"))
        notes["pre_compared"] = pre_comp
        if pre_comp < 1:
            fails.append("the CARRIED arm is empty -- the hover rate would have no "
                         "comparator inside its own read")

        # ---- 2. the comparator fires ON A HOVER-REVEALED ROW
        hrows = [x for r in got for x in r["rows"] if x.get("hov")]
        # `theirs` IS PRINTED AS repr. The class-F anchor's Chrome name is a Private-Use-Area
        # glyph (U+E978), which renders as nothing at all in a terminal -- so with
        # ensure_ascii=False this row looked like `"theirs": ""` and the check that passed on
        # it read exactly like a check that should have failed. Re-derived rather than
        # believed (PRINCIPLES 8), on a PASS rather than on a failure.
        notes["hover_disagreements"] = [
            {"ours": x["ours"], "theirs": repr(x["theirs"]), "cls": x["cls"], "tag": x["tag"]}
            for x in hrows]
        if not [x for x in hrows if "Facebook" in (x["ours"] or "") and (x["theirs"] or "").strip()]:
            fails.append("the comparator reported NO disagreement on a hover-revealed row "
                         "that is KNOWN to disagree (#114's class F): %s" % notes["hover_disagreements"])

        # ---- 3. CONTROL: the agreeing revealed rows are not flagged
        bad = [x["ours"] for x in hrows if x["ours"] in ("Revealed Alpha", "Revealed Beta")]
        if bad:
            fails.append("hover-revealed controls %s were reported as disagreements -- a "
                         "probe that flags everything would pass check 2" % bad)

        # ---- 4. CONTROL: a hover that reveals nothing is SEEN to reveal nothing
        notes["nothing_appeared"] = nothing
        if nothing < 1:
            fails.append("the decoy hover (which reveals nothing) was never reported as "
                         "such -- an empty reveal and a real one are indistinguishable")

        # ---- 5. the planted arm, restricted to HOVER-REVEALED rows
        if got:
            rp = planted or {"planted": [], "planted_disposition": {}}
            disp = rp["planted_disposition"]
            reached = [m for m, d in disp.items() if d.startswith("compared:")]
            missed = [m for m in reached if "SENTINEL" not in disp[m]]
            notes["planted"] = {"moved": len(rp["planted"]), "reached": len(reached),
                                "disposition": disp}
            if not rp["planted"]:
                fails.append("the planted arm tagged NO hover-revealed row")
            if not reached:
                fails.append("no planted hover-revealed row reached the compared "
                             "population -- the plant proves nothing")
            if missed:
                fails.append("PLANTED NAMES DID NOT FIRE on hover-revealed rows: %s" % missed)
        await b.close()
    print("hover selftest", "PASS" if not fails else "FAIL")
    print(json.dumps({**notes, "failures": fails}, indent=1, ensure_ascii=False))
    return 0 if not fails else 1


async def run_hover(sites, conc, examples, plant):
    sem = asyncio.Semaphore(conc)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        async def go(s):
            async with sem:
                try:
                    return await asyncio.wait_for(
                        hover_one(browser, *s, examples, plant), 200)
                except Exception as e:
                    return {"site": s[0], "url": s[1], "archetype": s[2], "lang": s[3],
                            "error": "timeout/" + str(e)[:80]}
        out = await asyncio.gather(*(go(s) for s in sites))
        await browser.close()
    return out


# --------------------------------------------------------------------------------------
def _check_sample(sites):
    bad = []
    for n, u, *_ in sites:
        h = re.sub(r"^www\.", "", urlparse(u).netloc.lower())
        if h in AGL.EXCLUDED:
            bad.append((n, h))
    return bad


async def run_pass(sites, conc, nstages, examples, plant_at_end):
    sem = asyncio.Semaphore(conc)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        async def go(s):
            async with sem:
                try:
                    return await asyncio.wait_for(
                        one(browser, *s, nstages, examples, plant_at_end), 200)
                except Exception as e:
                    return {"site": s[0], "url": s[1], "archetype": s[2], "lang": s[3],
                            "error": "timeout/" + str(e)[:80]}
        out = await asyncio.gather(*(go(s) for s in sites))
        await browser.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--hover", action="store_true",
                    help="drive a HOVER reveal (#94's picker and before/after diff, reused) "
                         "and ask the oracle about the controls it revealed, against the "
                         "carried rows of the SAME read. #117 named this gap: the hover "
                         "probe has no oracle arm and the oracle has never driven hover.")
    ap.add_argument("--hover-selftest", action="store_true",
                    help="the firing proof for the hover arm specifically -- a driver that "
                         "silently reveals nothing gives a clean rate over an empty population")
    ap.add_argument("--hover-report", nargs="+")
    ap.add_argument("--fire", action="store_true",
                    help="LIVE firing proof: plant names on real pages at the deepest stage")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--pool", default="usable85", choices=("usable85", "all"))
    ap.add_argument("--stages", type=int, default=4)
    ap.add_argument("--conc", type=int, default=6)
    ap.add_argument("--examples", type=int, default=40)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--every", type=int, default=0,
                    help="take every Nth site of the pool -- a STRIDE, not a head "
                         "slice, because the pool is grouped by archetype and a head "
                         "slice would be one archetype")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--report", nargs="+")
    ap.add_argument("--stage-report", nargs="+",
                    help="the name axis AFTER an interaction: `src=name` per stage, the "
                         "stage gradient PAIRED per site, and revealed-vs-carried PAIRED "
                         "per read -- the comparisons the pooled tables cannot make")
    ap.add_argument("--quoting", action="store_true",
                    help="measure the two quoting conventions in _fmtLine by PARSING "
                         "each printed row back the way a reader would")
    ap.add_argument("--candidate-ab", action="store_true",
                    help="both collectors on the SAME page load, one oracle read, "
                         "reporting improved/regressed rather than a level")
    ap.add_argument("--ab-only", nargs="*", default=None,
                    choices=[c[0] for c in CANDIDATES],
                    help="isolate ONE candidate: every other one stays exactly as the "
                         "source has it. Without this, an A/B run while two fixes are "
                         "already shipped and a third is not measures all three at once.")
    ap.add_argument("--ab-arm", default="guarded",
                    choices=("narrow", "guarded", "broad"),
                    help="which arm `child-declared-name` means. `narrow`: a child's "
                         "DECLARED name is used only when that child contributes no text. "
                         "`guarded`: ...and the child is not itself a declared control, "
                         "which is synthLabel's existing group rule in a second place. "
                         "`broad`: AccName's own order -- a declared name outranks the "
                         "child's text, which is the arm that absorbs a nested control's "
                         "label into its container. Measuring all three is how the "
                         "proposal becomes a choice with a number (#41/#44). The "
                         "DEFAULT is `guarded` because that is what the write-up "
                         "proposes -- a reader re-deriving the published figure with no "
                         "flag must get the arm the figure describes.")
    ap.add_argument("--oracle-recheck", action="store_true",
                    help="re-read Chrome's AX tree after each comparison and count how "
                         "many REPORTED rows moved -- a direct bound on the page "
                         "re-rendering between the collector run and the oracle read")
    ap.add_argument("--plant-in-corpus", action="store_true",
                    help="prove the out-of-sample guard fires, by planting a frozen-corpus host")
    ap.add_argument("--out", default=str(OUT / "main"))
    a = ap.parse_args()
    global RECHECK
    RECHECK = bool(a.oracle_recheck)
    _set_arm(a.ab_arm)
    if a.selftest:
        return asyncio.run(_selftest())
    if a.hover_selftest:
        return asyncio.run(_hover_selftest())
    if a.hover_report:
        print(hover_report(a.hover_report))
        return 0
    if a.report:
        print(report(a.report))
        return 0
    if a.stage_report:
        print(stage_report(a.stage_report))
        return 0
    sites = ASG._pool(a.pool, a.only)
    if a.plant_in_corpus:
        sites = list(sites) + [("PLANTED_IN_CORPUS", "https://news.ycombinator.com/", "x", "en")]
    bad = _check_sample(sites)
    if bad:
        print("SAMPLE CONTAINS EXCLUDED HOSTS (frozen corpus / bench_turns / bench_flows):", bad)
        return 2
    if a.every:
        sites = sites[::a.every]
    if a.limit:
        sites = sites[:a.limit]
    if a.list:
        for s in sites:
            print(*s, sep="\t")
        print(len(sites), "sites;", len(AGL.EXCLUDED), "excluded hosts checked")
        return 0
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.quoting:
        async def go_q():
            sem = asyncio.Semaphore(a.conc)
            async with async_playwright() as p:
                br = await p.chromium.launch(headless=True)

                async def g(st):
                    async with sem:
                        try:
                            return await asyncio.wait_for(quoting_site(br, *st, a.stages), 200)
                        except Exception as e:
                            return {"site": st[0], "error": "timeout/" + str(e)[:80]}
                r = await asyncio.gather(*(g(st) for st in sites))
                await br.close()
                return r
        res = asyncio.run(go_q())
        agg = collections.Counter()
        sites_hit = 0
        for r in res:
            agg.update(r.get("counts") or {})
            if (r.get("counts") or {}).get("parse_truncated") or (r.get("counts") or {}).get("parse_wrong"):
                sites_hit += 1
        (out / "quoting.json").write_text(
            json.dumps({"totals": dict(agg), "sites_affected": sites_hit, "sites": res},
                       indent=1, ensure_ascii=False), encoding="utf-8")
        ok_sites = [r for r in res if "error" not in r]
        print("QUOTING over %d sites (%d errored), %d sites affected:" % (
            len(res), len(res) - len(ok_sites), sites_hit))
        print(json.dumps({k: agg[k] for k in QUOTING_KEYS}, indent=1))
        if agg["rows"]:
            print("unparseable-back share of printed rows: %.4f%%" % (
                100.0 * (agg["parse_truncated"] + agg["parse_wrong"]) / agg["rows"]))
        for r in ok_sites:
            for e in (r.get("examples") or [])[:1]:
                print(" eg", r["site"], json.dumps(e, ensure_ascii=False)[:230])
        return 0
    if a.candidate_ab:
        async def go_ab():
            sem = asyncio.Semaphore(a.conc)
            async with async_playwright() as p:
                br = await p.chromium.launch(headless=True)

                async def g(s):
                    async with sem:
                        try:
                            return await asyncio.wait_for(
                                candidate_ab(br, *s, a.stages, a.ab_only), 200)
                        except Exception as e:
                            return {"site": s[0], "error": "timeout/" + str(e)[:80]}
                r = await asyncio.gather(*(g(s) for s in sites))
                await br.close()
                return r
        res = asyncio.run(go_ab())
        agg = collections.Counter()
        agg_stage = collections.Counter()
        for r in res:
            agg.update(r.get("counts") or {})
            agg_stage.update(r.get("by_stage") or {})
        (out / "candidate_ab.json").write_text(
            json.dumps({"totals": dict(agg), "by_stage": dict(agg_stage),
                        "arm": a.ab_arm,
                        "only": a.ab_only, "sites": res},
                       indent=1, ensure_ascii=False),
            encoding="utf-8")
        print("CANDIDATE A/B over %d sites (%d errored)  arm=%s only=%s:" % (
            len(res), sum(1 for r in res if "error" in r),
            a.ab_arm.upper(), a.ab_only))
        print(json.dumps(dict(agg), indent=1))
        if agg["compared"]:
            print("agree base %.4f -> cand %.4f ; improved %d regressed %d ; chars %+.2f%%" % (
                agg["exact_base"] / agg["compared"], agg["exact_cand"] / agg["compared"],
                agg["improved"], agg["regressed"],
                100.0 * (agg["chars_cand"] - agg["chars_base"]) / max(1, agg["chars_base"])))
        # WHERE THE FIX PAYS. Rows improved per 1,000 rows compared, by stage -- a RATE,
        # because s0 is read on every site and s4 on the few that go that deep, so raw
        # counts fall with depth whatever the fix does.
        stages = sorted({k.split("|")[0] for k in agg_stage})
        if stages:
            print("\n%-5s %9s %9s %9s %9s   %s" % (
                "stage", "compared", "changed", "improved", "breaks", "improved/1k"))
            for st in stages:
                c = agg_stage.get(st + "|compared", 0)
                ch = agg_stage.get(st + "|name_changed", 0)
                im = (agg_stage.get(st + "|improved_chrome_named", 0)
                      + agg_stage.get(st + "|improved_chrome_empty", 0))
                bk = agg_stage.get(st + "|BREAKS_A_CORRECT_NAME", 0)
                print("%-5s %9d %9d %9d %9d   %9.2f" % (
                    st, c, ch, im, bk, 1000.0 * im / c if c else 0.0))
        # THE BENEFIT, GRADED. Only `nowhere` is an outright loss today; `inside` is a row
        # an agent could already act on, because a click bubbles.
        g = {k: agg.get("where_" + k, 0) for k in
             ("inside", "elsewhere", "nowhere", "unresolved")}
        if sum(g.values()):
            print("\nROWS THAT GAIN AN IDENTITY, by where that name was in the BASE listing:")
            print(" ", json.dumps(g), " total", sum(g.values()))
        for r in res:
            for e in (r.get("gained") or [])[:3]:
                print("  gained %-16s %-9s %-5s %r" % (
                    r["site"], e.get("where"), e.get("tag"), (e.get("name") or "")[:60]))
        return 0
    if a.hover:
        res = asyncio.run(run_hover(sites, a.conc, a.examples, a.fire))
        (out / "hover0.json").write_text(
            json.dumps({"sites": res}, indent=1, ensure_ascii=False), encoding="utf-8")
        print(hover_report([str(out / "hover0.json")]))
        if a.compare:
            res2 = asyncio.run(run_hover(sites, a.conc, a.examples, a.fire))
            (out / "hover1.json").write_text(
                json.dumps({"sites": res2}, indent=1, ensure_ascii=False), encoding="utf-8")
            print("\n\n==== SECOND PASS (drift control) ====\n")
            print(hover_report([str(out / "hover1.json")]))
        return 0
    runs = [asyncio.run(run_pass(sites, a.conc, a.stages, a.examples, a.fire))]
    if a.compare:
        runs.append(asyncio.run(run_pass(sites, a.conc, a.stages, a.examples, a.fire)))
    for i, rs in enumerate(runs):
        agg = aggregate(rs)
        (out / f"pass{i}.json").write_text(
            json.dumps({"aggregate": agg, "sites": rs}, indent=1, ensure_ascii=False),
            encoding="utf-8")
        t = agg["totals"]
        print("pass %d: usable %d/%d compared=%d exact=%d agree=%s fmt_drift=%d" % (
            i, agg["sites_usable"], agg["sites_attempted"], t.get("compared", 0),
            t.get("exact", 0), _rate(t), agg["fmt_drift"]))
        print("   classes:", json.dumps({k: t[k] for k in DISAGREE if t.get(k)}))
    if a.fire:
        fired = []
        for r in runs[0]:
            f = r.get("fire") or {}
            if "error" in f:
                fired.append({"site": r["site"], "error": f["error"]})
                continue
            disp = f.get("planted_disposition") or {}
            reached = [m for m, d in disp.items() if d.startswith("compared:")]
            missed = [m for m in reached if "SENTINEL" not in disp[m]]
            fired.append({"site": r["site"], "moved": len(f.get("planted") or []),
                          "reached_compared": len(reached), "missed": missed,
                          "reads": len(r.get("reads") or []),
                          "disposition": collections.Counter(
                              d.split(":")[0] if not d.startswith("compared") else
                              ("compared+SENTINEL" if "SENTINEL" in d else "compared-NO-SENTINEL")
                              for d in disp.values())})
        (out / "fire.json").write_text(json.dumps(fired, indent=1, default=dict),
                                       encoding="utf-8")
        # A planted name only proves something when it reached the COMPARED population;
        # one Chrome ignores, or one the row blanks, was never a question. The pass bar is
        # therefore "every planted row that was comparable reported the sentinel", plus at
        # least one such row somewhere -- a run where nothing was comparable proves nothing
        # and must not read as a pass (PRINCIPLES 15).
        bad = [f for f in fired if f.get("missed") or "error" in f]
        if not any(f.get("reached_compared") for f in fired):
            bad.append({"site": "(none reached the compared population)"})
        for f in fired:
            print("FIRE", json.dumps(f))
        print("FIRE:", "PASS" if fired and not bad else "FAIL", "failed:", [f["site"] for f in bad])
    if a.compare:
        d = drift(runs[0], runs[1])
        (out / "drift.json").write_text(json.dumps(d, indent=1), encoding="utf-8")
        print("DRIFT:", json.dumps({k: v for k, v in d.items() if k != "per_site"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
