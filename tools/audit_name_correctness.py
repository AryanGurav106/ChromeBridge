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

Run:  python tools/audit_name_correctness.py --selftest
      python tools/audit_name_correctness.py --fire --only gov_au leg_perldoc
      python tools/audit_name_correctness.py --pool usable85 --conc 6 --stages 4
      python tools/audit_name_correctness.py --compare --only ...     # drift floor
      python tools/audit_name_correctness.py --report temp/name_correctness/main/pass0.json

Findings: docs/research/NAME-CORRECTNESS-2026-11.md
"""
import argparse
import asyncio
import collections
import json
import re
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
                    recheck=False):
    """ONE read: collector -> declarations -> Chrome AX tree -> compare. The collector runs
    FIRST because it is what stamps the mmid attributes the join uses."""
    res = await page.evaluate(_collect_js())
    ents = json.loads(res["blob"])
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
    return {
        "stage": label, "entries": len(ents), "ax_info": info, "fmt_drift": fmt_drift,
        "counts": dict(counts), "by_src": {k: dict(v) for k, v in by_src.items()},
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
    moved = []
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
                if oa != ob:
                    tot["name_changed"] += 1
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
                    if len(moved) < 25:
                        moved.append({"mmid": mm, "tag": A[mm].get("tag"),
                                      "base": oa[:120], "cand": ob[:120],
                                      "chrome": theirs[:120], "cls": [ca, cb]})
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
                "stages": stage}
    finally:
        try:
            await ctx.close()
        except Exception:
            pass


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
        #    `chrome-superset` is #34's measured shape -- Chrome's name absorbs a
        #    nested control's `aria-label` where ours stops at the link's own
        #    text, and per AccName 2F Chrome is right and we stop short. It is
        #    recorded as a characterisation of the gap, not a bug queued for
        #    fixing, so it is a disagreement that should still be here. If it is
        #    ever closed, this proof expires too -- rewrite it rather than
        #    deleting it, and say what replaced it.
        if not any(row["cls"] == "chrome-superset"
                   and "Deadline" in (row["ours"] or "") for row in r["rows"]):
            fails.append("the comparator reported NO genuine disagreement on a "
                         "shape that is known to disagree (#34's nested-label "
                         "case): %s"
                         % [(x["ours"], x["theirs"], x["cls"]) for x in r["rows"]][:6])
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
        "disagreements": [{k: x[k] for k in ("ours", "theirs", "cls", "tag", "src")}
                          for x in report_rows],
        "planted_moved": len(r2["planted"]), "planted_reported": len(planted_rows),
        "planted_disposition": r2["planted_disposition"],
        "failures": fails}, indent=1, ensure_ascii=False))
    return 0 if not fails else 1


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
    if a.selftest:
        return asyncio.run(_selftest())
    if a.report:
        print(report(a.report))
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
        for r in res:
            agg.update(r.get("counts") or {})
        (out / "candidate_ab.json").write_text(
            json.dumps({"totals": dict(agg), "sites": res}, indent=1, ensure_ascii=False),
            encoding="utf-8")
        print("CANDIDATE A/B over %d sites (%d errored):" % (
            len(res), sum(1 for r in res if "error" in r)))
        print(json.dumps(dict(agg), indent=1))
        if agg["compared"]:
            print("agree base %.4f -> cand %.4f ; improved %d regressed %d ; chars %+.2f%%" % (
                agg["exact_base"] / agg["compared"], agg["exact_cand"] / agg["compared"],
                agg["improved"], agg["regressed"],
                100.0 * (agg["chars_cand"] - agg["chars_base"]) / max(1, agg["chars_base"])))
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
