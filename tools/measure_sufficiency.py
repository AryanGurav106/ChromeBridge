"""SUFFICIENCY: is the element the task needs DISTINGUISHABLE in the listing?

WHAT THIS ANSWERS THAT NOTHING ELSE DOES
----------------------------------------
Every other ruler here measures PRESENCE. `bench_mind2web` asks whether the
labelled target got a row; `inspect_site`'s `lost_identities` asks whether a
visible control's name went missing; `measure_retention` asks whether a key fact
survived. All three can read perfect on a listing that still does not tell the
agent WHICH ref to pass, because the target prints exactly like eleven of its
neighbours.

    DECISION SUFFICIENCY (DS), per human-labelled action:
      ABSENT     the target has no row at all          (presence — already measured)
      AMBIGUOUS  it has a row, and so does a look-alike that prints identically
      DECIDABLE  it has a row and is uniquely described

    DS | reachable = DECIDABLE / (DECIDABLE + AMBIGUOUS)   <- quote this one

Design, limits and the MFS provenance: `docs/SUFFICIENCY.md`. Read it before
quoting anything from here. The short version of the honesty argument:

  * ground truth is a HUMAN label on 16 untuned sites, so the collector does not
    get a vote on which step counts;
  * the identity EXCLUDES `ref` and geometry — a ref is the answer the agent is
    trying to produce, and geometry drifts (#23: 110px, #25: 1,097px), so either
    would make every row unique and DS 100% by construction. Both are shipped as
    negative controls (`--controls`) rather than argued about;
  * the metric is gameable by printing per-element noise, so the field ablation
    reports WHICH class of printed field carries the discrimination. A DS that
    rises with no field carrying it is a defect, not a win.

WHAT IT CANNOT ANSWER — do not quote a number without these
-----------------------------------------------------------
  * DS is NECESSARY, not sufficient. DECIDABLE means the listing permits a
    correct choice, not that a model makes one.
  * AMBIGUOUS is not failure — the agent can guess 1/N or escalate. The honest
    cost is one model turn (~3.6s, 92-97% of a tool call, #38).
  * It prices CONTROLS. The source paper's largest single finding is that TEXT
    dominates the minimal failure set; our prose lives behind get_page_text /
    search_page / query_elements and is not measured here at all.
  * Mind2Web is serialized HTML with no scripts and no CSS (#73), so pages run
    unstyled and tall and far more falls below the fold than on a real page.
    `--corpus frozen` measures real styled pages and has NO LABELS, so it can
    only report density. Neither corpus carries the claim alone.

Run:
    python tools/measure_sufficiency.py                      # Mind2Web, all arms
    python tools/measure_sufficiency.py --limit 40           # smoke
    python tools/measure_sufficiency.py --controls           # + the falsifiers
    python tools/measure_sufficiency.py --corpus frozen -n 20 --replicates 2
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "temp" / "mind2web"
FROZEN = ROOT / "temp" / "frozen"
OUT = ROOT / "temp" / "sufficiency"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
COLLECT = extract("_collectInteractivePage", BG, verify=True)
TAG_JS = str(ROOT / "extension" / "listener_tag.js")
VIEWPORT = {"width": 1280, "height": 1600}

# Reuse the existing rulers' target probe and ref harvest rather than writing a
# sixth spelling of either (PRINCIPLES §17). `listing_refs` in particular knows
# all five actionable ref shapes; counting only ordinary rows would score every
# folded member unreachable and make folding look catastrophic.
_spec = importlib.util.spec_from_file_location("bt", ROOT / "tools" / "bench_trajectory.py")
bt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bt)
PROBE = bt.PROBE
listing_refs = bt.listing_refs

# The boundary marker C12 pins: the server splits the listing here and the
# extension emits exactly this prefix. Restating it would be the string-contract
# break that kept `delta` dead for its entire life (#30).
_ACT_LINE = "Act on a row by its ref_N:"

# WHOSE AMBIGUITY IS IT? A collision where every rival is the SAME LINK FOUR
# TIMES (a responsive nav duplicated in markup) costs nothing -- clicking any of
# them does the job. A collision between four different products is a wrong
# answer. The metric cannot tell them apart on its own, and the honest
# discriminator is DECLARED attributes: if the page declares a difference our
# listing does not print, the gap is OURS; if the document itself says nothing
# that separates them, no representation could and the ambiguity is the page's.
# Derived from the DOM, independently of the collector.
ATTR_PROBE = r"""
(refs) => refs.map(m => {
  const el = document.querySelector(`[mmid="${String(m).replace(/"/g,'')}"]`);
  if (!el) return null;
  const o = {};
  for (const a of el.attributes) {
    const n = a.name.toLowerCase();
    if (n === 'mmid' || n === 'backend_node_id' || n === 'bounding_box_rect') continue;
    o[n] = a.value;
  }
  // The CONTENT NAME, not raw text. Compared raw, `<a><img alt="Find a
  // Theatre"></a>` and `<a>Find a Theatre</a>` differ -- textContent is "" for
  // the first -- and the diagnosis called that a declared difference our
  // listing failed to print. It is the SAME declared name arriving by two
  // AccName paths, which is what the listing correctly shows. Inspected
  // element by element before this was changed, because the change moves a
  // verdict in the flattering direction (#16).
  o['__name_src'] = (el.getAttribute('alt') || el.getAttribute('title') ||
                     el.getAttribute('value') ||
                     (el.textContent || '')).replace(/\s+/g, ' ').trim().slice(0, 120);
  o['__text'] = (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60);
  return o;
})
"""
# ALLOWLIST, not a blacklist. The first version of this diagnosis compared every
# attribute and reported 6 of 6 collisions as OUR gap -- because Mind2Web's
# capture harness writes its own attributes into the snapshot, and
# `data_pw_testid_buckeye` ("pw" = playwright, "buckeye" = the dataset's
# university) appears on all 16 unrelated sites. A damning result, and wrong
# (#16: damning results get believed too readily). `is_clickable`,
# `input_value`, `option_selected`, `input_checked` and `text_value` are the
# same harness, on 13-16 sites each.
#
# A blacklist of those names would go stale the moment the dataset changes, the
# way `_OBSERVES` did three times in one day (#42). So this enumerates what a
# page AUTHOR declares, and everything else -- including every `data-*` -- is
# ignored for the verdict and reported so the choice is auditable.
_DECLARED = {
    "id", "name", "value", "type", "role", "alt", "title", "placeholder",
    "label", "for", "href", "src", "checked", "selected", "disabled",
    "required", "multiple", "aria_role",
    "aria-label", "aria-labelledby", "aria-describedby",
}
# `__name_src` and `__text` are RECORDED and deliberately NOT compared. Both
# attempts to compare them were wrong in the same way: `<a><img alt="Find a
# Theatre"></a>` and `<a>Find a Theatre</a>` differ in raw text AND in a
# one-level alt lookup, while the page declares the SAME name for both and the
# listing correctly prints it once each. Getting that right means descending
# the way AccName does -- a second naming implementation, which is exactly the
# duplication PRINCIPLES §17 exists to stop. Whether our AccName agrees with
# the page is a real question and it belongs to `accessible_names` (#33/#34,
# measured there at 49/54), not to this probe. Inspected element by element
# before dropping, because dropping flatters the result (#16).
# DECLARED ON A REAL PAGE, INERT ON THIS CORPUS. Mind2Web rewrites hyphenated
# ARIA attributes to underscores: 17,272 `aria_label` against 1 `aria-hidden`
# across 186 snapshots. `aria_label` is not `aria-label` and has no ARIA
# meaning, so NO spec-conformant AccName implementation reads it -- not ours and
# not Chrome's. A difference there would be our gap on a real site and is a
# dataset artefact here, so it gets its own verdict instead of being counted
# either way.
_INERT_HERE = {"aria_label", "aria_labelledby", "aria_describedby"}
# `class` is reported apart from the rest: the source paper prices it at 7-10%
# and the locator literature down-weights it, and a framework's state classes
# differ on elements that are otherwise identical, so folding it in would call
# almost every collision "ours".
_CLASSY = {"class"}

_MMID = r"(?:f\d+:\d+|\d+)"
_REF_TOK = re.compile(r"\bref_(" + _MMID + r")")
_FOLD_MEMBER = re.compile(r"(?:^|\s)(" + _MMID + r'):"((?:[^"\\]|\\.)*)"')
_ICON_MEMBER = re.compile(r"(?:^|\s)(" + _MMID + r")@\(")
_BARE_REFS = re.compile(r"(?:^|\s)(" + _MMID + r")(?=\s|$)")


# --------------------------------------------------------------------------
# ARMS. Spelled out as the op router sends them -- structured, scopeMmid,
# detail, ledger, geometry, format -- because passing fewer positionals and
# letting them default is how a benchmark drifts off the shipped path (#19).
# --------------------------------------------------------------------------
ARMS: dict[str, str] = {
    "tree-compact": "false, null, 'compact', false, false, 'tree'",   # the shipped default
    "tree-brief":   "false, null, 'brief',   false, false, 'tree'",
    "tree-full":    "false, null, 'full',    false, false, 'tree'",
    "flat-compact": "false, null, 'compact', false, false, 'flat'",
    # CONTROL: byte-identical arguments to the shipped default. Any difference
    # between this and `tree-compact` is the collector's own non-determinism
    # across two calls in one page load, not a property of the page.
    "ctrl":         "false, null, 'compact', false, false, 'tree'",
}
PRIMARY = "tree-compact"


# --------------------------------------------------------------------------
# Parsing the agent-facing surface.
#
# NOT the structured array, and not each entry's `line` field. Measured before
# building on it: `line` is the FLAT row and appears verbatim in a TREE listing
# for 0-6 of 300-800 entries, because the tree strips `section=`, re-indents,
# and drops the tag word from bare wrappers. Keying on `line` would have scored
# a surface the agent is not shown -- PRINCIPLES §13, one layer out.
# --------------------------------------------------------------------------
class Slot:
    """One thing the agent can act on, as the listing describes it.

    A slot is not a ref. A row carrying several refs (#29's identical-nested
    collapse: `ref_4 ref_5 ref_6 | div "x"`) is ONE slot, because those refs are
    one spot and counting them as a collision would invent an ambiguity the
    agent does not experience.
    """

    __slots__ = ("sid", "path", "desc", "refs")

    def __init__(self, sid: int, path: tuple, desc: str, refs: set):
        self.sid, self.path, self.desc, self.refs = sid, path, desc, refs


# `(just appeared)` is #31's novelty flag and it is MONOTONIC per tab, so the
# same collector call made twice in one page load emits it the first time and
# not the second. Leaving it in the identity makes the control arm report a
# difference caused by our own measurement order. It is also transient, and no
# task can name it. `box(...)` and refs go for the reasons in SUFFICIENCY.md §4.
_STRIP = [
    (re.compile(r"\(just appeared\)"), ""),
    (re.compile(r"\bbox\([^)]*\)"), ""),
    (re.compile(r"\bref_" + _MMID), ""),
]


def _norm(s: str) -> str:
    for rx, rep in _STRIP:
        s = rx.sub(rep, s)
    return re.sub(r"\s+", " ", s).strip(" |").strip()


def parse_listing(text: str) -> tuple[dict, list]:
    """-> (ref -> Slot, [Slot]). Works for both tree and flat.

    Indentation is the tree's own structure, so the ancestor stack is read off
    it rather than re-derived from the DOM; in `flat` every row sits at indent 0
    and the path is empty, which is exactly the difference between the formats.
    """
    if not text:
        return {}, []
    lines = text.splitlines()
    start = next((i for i, L in enumerate(lines) if L.startswith(_ACT_LINE)), -1)
    body = lines[start + 1:] if start >= 0 else []

    slots: list[Slot] = []
    ref2slot: dict[str, Slot] = {}
    stack: list[tuple[int, str]] = []          # (indent, normalised line)
    sid = 0

    for raw in body:
        stripped = raw.lstrip(" ")
        if not stripped:
            continue
        indent = len(raw) - len(stripped)
        # Page-level notes are not rows and must not become ancestors -- but the
        # off-viewport note carries the REGION INDEX (`footer(ref_471): 12,
        # main(ref_51): 11`), and those refs are printed, described and scopable.
        # Skipping them outright put the parser 4.3% below bench_trajectory's ref
        # harvest, and a missing slot cannot collide with anything, so the error
        # was in the FLATTERING direction (#16). Each comma-chunk is its own slot.
        if stripped.startswith("[") or stripped.startswith("***"):
            for chunk in stripped.split(","):
                for ref in _REF_TOK.findall(chunk):
                    if ref in ref2slot:
                        continue
                    sid += 1
                    sl = Slot(sid, (), _norm(chunk), {ref})
                    slots.append(sl)
                    ref2slot[ref] = sl
            continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = tuple(x[1] for x in stack)
        norm = _norm(stripped)

        row_refs = set(_REF_TOK.findall(stripped))
        fold_members = _FOLD_MEMBER.findall(stripped)
        icon_members = set(_ICON_MEMBER.findall(stripped))
        bare: set[str] = set()
        if "refs:" in stripped:
            bare = set(_BARE_REFS.findall(stripped.split("refs:", 1)[1]))

        if fold_members or icon_members or bare:
            # A FOLD. Its header is shared; what (if anything) distinguishes the
            # members is printed per member. `N:"label"` gives each member its
            # own label; an icon fold gives a coordinate (geometry -- excluded,
            # so those members correctly collide); `refs: 1 2 3` gives nothing.
            head = _norm(re.split(r"ref:\"label\"[^:]*:|refs:", stripped)[0])
            for ref, lbl in fold_members:
                sid += 1
                sl = Slot(sid, path, f"{head} :: {lbl}", {ref})
                slots.append(sl)
                ref2slot[ref] = sl
            for ref in sorted(icon_members | bare):
                if ref in ref2slot:
                    continue
                sid += 1
                sl = Slot(sid, path, head, {ref})
                slots.append(sl)
                ref2slot[ref] = sl
            # The decoration tier prints `9 generic-no-label (ref_17 ref_23)` --
            # row_refs are its members, not a row of their own.
            for ref in row_refs:
                if ref not in ref2slot:
                    sid += 1
                    sl = Slot(sid, path, head, {ref})
                    slots.append(sl)
                    ref2slot[ref] = sl
        elif row_refs:
            sid += 1
            sl = Slot(sid, path, norm, set(row_refs))
            slots.append(sl)
            for ref in row_refs:
                ref2slot[ref] = sl
        # Every line can be a parent of deeper ones -- a row line frequently is.
        stack.append((indent, norm))
    return ref2slot, slots


# --------------------------------------------------------------------------
# FIELD ABLATION -- the source paper's Table 3, computed against our own
# printed fields instead of against generic HTML tag names.
#
# Subtractive on the PRINTED description, in a fixed order: the keyed `k="v"`
# pairs are removed by name, and `identity` is whatever quoted string is left
# that no key owns. Each ablation reports how many descriptions it CHANGED,
# because an ablation that fires on nothing is a detector that cannot fire
# (PRINCIPLES §15) and would read as "this field carries nothing".
# --------------------------------------------------------------------------
_KEYED = {
    "near":    re.compile(r'\bnear="[^"]*"'),
    "value":   re.compile(r'\b(?:value|placeholder)="[^"]*"'),
    "url":     re.compile(r'\b(?:href|src)="[^"]*"'),
    "enum":    re.compile(r'(?:\boptions=\[[^\]]*\]|\bcount=\d+|'
                          r'\b(?:pattern|minlength|maxlength|min|max|step|accept|'
                          r'inputmode|list|format)="[^"]*")'),
    "type":    re.compile(r'(?:\brole=[\w-]+|\bsection=[\w-]+|\[[\w-]+\])'),
    "state":   re.compile(r'\([^)]*\)'),
}
# THE IDENTITY IS PRINTED IN TWO FORMS and the first version of this ablation
# only removed one: a bare quoted string after the tag (`button "Update search"`,
# 47 of 173 target rows) and `name="..."` (`select name="type"`, 17 of 173).
# Both are the row's IDENTITY per the listing's own legend; `name=` carries the
# `(post-key)` caveat (#41) and is still the identity shown. Removing one and
# not the other made the ablation mean different things on different row shapes
# and undercounted what the name carries. Caught by reading real rows, not by
# reading the regex.
_UNKEYED_QUOTED = re.compile(r'(?<![=\w])"[^"]*"')
_NAMED_IDENTITY = re.compile(r'\bname="[^"]*"')


def ablate(desc: str, path: tuple, which: str) -> tuple[str, tuple]:
    if which == "none":
        return desc, path
    if which == "ancestry":
        return desc, ()
    if which == "identity":
        d = desc
        for rx in _KEYED.values():                 # protect the keyed pairs
            d = rx.sub(lambda m: "\x00" * len(m.group(0)), d)
        d = _NAMED_IDENTITY.sub("", _UNKEYED_QUOTED.sub("", d))
        return re.sub(r"\x00+", " ", d), path
    if which == "label+near":
        # audit_dom_quality.py's existing `ambiguous` key, for comparison: the
        # label plus the near=/under= breadcrumb, nothing else, no ancestry.
        keep = " ".join(_UNKEYED_QUOTED.findall(desc) +
                        _NAMED_IDENTITY.findall(desc) +
                        _KEYED["near"].findall(desc))
        return keep, ()
    rx = _KEYED.get(which)
    return (rx.sub("", desc) if rx else desc), path


ABLATIONS = ["none", "identity", "near", "value", "url", "enum", "type",
             "state", "ancestry", "label+near"]
# Negative controls: the two keys whose answers are known in advance. If `+ref`
# is not 100% the parser is losing refs; if `empty` is not ~0% collisions are
# not being detected at all. Either failing means every other number here is
# worthless (SUFFICIENCY.md §6).
CONTROLS = ["+ref", "empty"]


def ds_for(ref2slot: dict, slots: list, target_refs: list, which: str) -> dict:
    """Decision sufficiency for one target under one key."""
    sl = next((ref2slot[r] for r in target_refs if r in ref2slot), None)
    if sl is None:
        return {"status": "ABSENT"}

    def key(s: Slot):
        if which == "+ref":
            return (s.sid,)
        if which == "empty":
            return ("",)
        d, p = ablate(s.desc, s.path, which)
        return (re.sub(r"\s+", " ", d).strip(), p)

    groups: dict[tuple, list] = defaultdict(list)
    for s in slots:
        groups[key(s)].append(s)
    g = groups[key(sl)]
    return {"status": "DECIDABLE" if len(g) == 1 else "AMBIGUOUS",
            "collisions": len(g),
            "desc": sl.desc[:110],
            "path": " > ".join(sl.path[-2:])[:60],
            "rival": next((x.desc[:90] for x in g if x.sid != sl.sid), ""),
            "group_refs": sorted({r for x in g for r in x.refs})[:12],
            # UNCAPPED on purpose: this is the exclusion set for the diagnosis
            # below, and a truncated exclusion set lets a collapsed sibling back
            # in as a "rival".
            "self_refs": sorted(sl.refs)}


def whose_ambiguity(attrs: list, self_refs: list, group_refs: list) -> dict:
    """Did the PAGE declare a difference we failed to print, or declare none?"""
    recs = [a for a in attrs if a]
    if len(recs) < 2:
        return {"verdict": "unknown", "why": "attributes unreadable"}
    mine = recs[0]
    diff_real, diff_class, diff_inert, ignored = set(), set(), set(), set()
    for other in recs[1:]:
        for k in set(mine) | set(other):
            if mine.get(k) == other.get(k) or k in ("__text", "__name_src"):
                continue
            if k in _CLASSY:
                diff_class.add(k)
            elif k in _INERT_HERE:
                diff_inert.add(k)
            elif k in _DECLARED:
                diff_real.add(k)
            else:
                ignored.add(k)
    ig = sorted(ignored)[:6]
    if diff_real:
        return {"verdict": "ours", "why": sorted(diff_real)[:6], "ignored": ig}
    if diff_inert:
        return {"verdict": "inert-here", "why": sorted(diff_inert), "ignored": ig}
    if diff_class:
        return {"verdict": "class-only", "why": sorted(diff_class), "ignored": ig}
    return {"verdict": "page", "why": "no declared attribute separates them", "ignored": ig}


def changed_count(slots: list, which: str) -> int:
    """How many descriptions this ablation actually altered."""
    n = 0
    for s in slots:
        d, p = ablate(s.desc, s.path, which)
        if (re.sub(r"\s+", " ", d).strip(), p) != (re.sub(r"\s+", " ", s.desc).strip(), s.path):
            n += 1
    return n


# --------------------------------------------------------------------------
# Mind2Web: the labelled half.
# --------------------------------------------------------------------------
def load_samples(limit: int) -> list[dict]:
    rows: list[dict] = []
    for f in sorted(DATA.glob("samples_shard*.jsonl")):
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    if not limit:
        return rows
    by_site: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_site[r.get("website") or "?"].append(r)
    out, i = [], 0
    while len(out) < limit:
        added = False
        for site in sorted(by_site):
            if i < len(by_site[site]):
                out.append(by_site[site][i])
                added = True
                if len(out) >= limit:
                    break
        if not added:
            break
        i += 1
    return out


async def score_action(page, s: dict, idx: int, controls: bool) -> dict:
    r: dict = {"website": s.get("website"), "action_uid": s.get("action_uid"),
               "annotation_id": s.get("annotation_id"), "op": s.get("operation"),
               "task": (s.get("task") or "")[:80]}
    await page.set_content(s["html"], wait_until="domcontentloaded")
    await page.wait_for_timeout(120)

    structured = await page.evaluate(
        "(function(){ " + COLLECT + "; return _collectInteractivePage(true, null, 'full'); })()")
    probe = await page.evaluate(PROBE, s.get("target_backend_node_id"))
    if not probe.get("found"):
        r["status"] = "target_not_in_html"
        return r

    by_mmid = {str(e.get("mmid")): e for e in (structured or [])}
    credited = [x for x in ([probe.get("own")] + (probe.get("ancs") or [])
                            + (probe.get("descs") or [])) if x]
    target_refs = [c for c in credited if c in by_mmid]
    r["recall_structured"] = bool(target_refs)
    r["rendered"] = bool(probe.get("rendered"))
    r["target_tag"] = probe.get("tag")
    r["target_text"] = probe.get("text")
    r["reduction_vs_html"] = None

    # ARM ORDER IS ROTATED PER ACTION (#19/R3). It is not ceremonial here: the
    # novelty flag is monotonic per tab, so a fixed order would put the same arm
    # in the privileged first position every time.
    names = list(ARMS)
    order = names[idx % len(names):] + names[:idx % len(names)]

    arms: dict[str, dict] = {}
    for name in order:
        listing = await page.evaluate(
            "(function(){ " + COLLECT + "; return _collectInteractivePage("
            + ARMS[name] + "); })()")
        listing = listing if isinstance(listing, str) else ""
        ref2slot, slots = parse_listing(listing)
        shown = listing_refs(listing)
        a: dict = {
            "chars": len(listing),
            "slots": len(slots),
            # CROSS-CHECK: two independent harvests of the same listing. If the
            # parser and the established `listing_refs` disagree about which
            # refs are actionable, this ruler is broken, not insightful.
            "refs_parser": len(ref2slot),
            "refs_known": len(shown),
            "refs_missed": sorted(shown - set(ref2slot))[:5],
            # CORPUS CAPABILITY CENSUS. The probe states its own blind spots
            # from measurement rather than from the author's memory: if the
            # corpus never prints href=/src=, no ablation of them means
            # anything, and neither does any `detail` comparison taken here.
            # Counted in the SLOTS, never in the raw listing: the legend itself
            # contains the literal `href="..."` as a notation explainer, so a
            # whole-text count reported 2 per page on a corpus with no hrefs at
            # all -- a census that cannot read zero (#16, on my own probe).
            "href_n": sum(s.desc.count('href="') for s in slots),
            "src_n": sum(s.desc.count('src="') for s in slots),
        }
        in_listing = [c for c in target_refs if c in shown]
        a["reachable"] = bool(in_listing)
        wants = ABLATIONS + (CONTROLS if controls else [])
        for which in wants:
            a[which] = ds_for(ref2slot, slots, target_refs, which)
        a["ablation_fired"] = {w: changed_count(slots, w) for w in ABLATIONS if w != "none"}
        # Density, the unlabelled statistic -- what the frozen half reports too.
        keys = Counter()
        for sl in slots:
            keys[(sl.desc, sl.path)] += 1
        a["dup_slots"] = sum(v for v in keys.values() if v > 1)
        # THE SELECTION EFFECT, BOUNDED. `DS | reachable` conditions on the
        # target being in a VIEWPORT-SCOPED listing, and if off-screen rows are
        # more repetitive (product grids, long nav lists) then conditioning
        # picks the easy ones and the headline is optimistic. Split the density
        # by the `(below-fold)` flag the listing already prints, so the
        # direction and size of the bias are measured rather than asserted.
        for tag, want in (("onscreen", False), ("belowfold", True)):
            sub = [s for s in slots if ("(below-fold)" in s.desc) == want]
            k2 = Counter((s.desc, s.path) for s in sub)
            a[f"dup_{tag}"] = sum(v for v in k2.values() if v > 1)
            a[f"n_{tag}"] = len(sub)
        arms[name] = a
    r["arms"] = arms
    # Diagnose the primary arm's collisions against the DOM's own declarations.
    p0 = arms[PRIMARY]["none"]
    if p0.get("status") == "AMBIGUOUS":
        # EVERY ref of the target's own slot is excluded, not just the first.
        # #29's identical-nested collapse puts several refs on one row, and they
        # are one spot; comparing the target against its own collapsed sibling
        # would manufacture a declared difference between an element and its
        # wrapper and report it as our gap.
        own = set(p0.get("self_refs") or [])
        self_r = next(iter(sorted(own)), None)
        rivals = [x for x in p0.get("group_refs", []) if x not in own][:6]
        try:
            attrs = await page.evaluate(ATTR_PROBE, [self_r] + rivals)
            r["whose"] = whose_ambiguity(attrs, [self_r], rivals)
        except Exception as e:
            r["whose"] = {"verdict": "unknown", "why": str(e)[:60]}
    if s.get("cleaned_html"):
        base = len(s["cleaned_html"])
        r["reduction_vs_html"] = round(arms[PRIMARY]["chars"] / base, 5) if base else None
    r["status"] = "ok"
    return r


# --------------------------------------------------------------------------
# Frozen corpus: the unlabelled half. DENSITY ONLY -- there are no task labels,
# so no DS number can come from here, and saying so is the point (R2).
# --------------------------------------------------------------------------
def load_sites() -> list[tuple[str, str]]:
    src = (ROOT / "tools" / "capture_listings.py").read_text(encoding="utf-8")
    body = src[src.index("SITES = ["):src.index("\nOUT = ")]
    return re.findall(r'\(\s*"([a-z_0-9]+)"\s*,\s*"(https?://[^"]+)"', body)


async def density_site(browser, name: str, url: str, idx: int) -> dict:
    ctx = await browser.new_context(viewport=VIEWPORT)
    try:
        await ctx.add_init_script(path=TAG_JS)
        har = FROZEN / f"{name}.har"
        if not har.exists():
            return {"name": name, "skipped": "no recording"}
        await ctx.route_from_har(str(har), not_found="abort")
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        try:
            await page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass
        await page.wait_for_timeout(900)
        names = [PRIMARY, "ctrl", "flat-compact"]
        order = names[idx % len(names):] + names[:idx % len(names)]
        out: dict = {"name": name}
        for arm in order:
            listing = await page.evaluate(
                "(function(){ " + COLLECT + "; return _collectInteractivePage("
                + ARMS[arm] + "); })()")
            listing = listing if isinstance(listing, str) else ""
            _, slots = parse_listing(listing)
            keys = Counter()
            for sl in slots:
                keys[(sl.desc, sl.path)] += 1
            dup = sum(v for v in keys.values() if v > 1)
            out[arm] = {"slots": len(slots), "dup": dup,
                        "dup_rate": round(dup / len(slots), 4) if slots else None,
                        "chars": len(listing)}
        return out
    except Exception as e:
        return {"name": name, "skipped": str(e)[:110]}
    finally:
        await ctx.close()


# --------------------------------------------------------------------------
def summarise(rows: list[dict], controls: bool) -> dict:
    scored = [r for r in rows if r.get("status") == "ok"]
    if not scored:
        print("nothing scored")
        return {}
    sites = sorted({r["website"] for r in scored})
    print(f"\n=== DECISION SUFFICIENCY  ({len(scored)} labelled actions, "
          f"{len({r['annotation_id'] for r in scored})} trajectories, {len(sites)} sites) ===")

    # --- the parser cross-check comes FIRST. A ruler is not quoted before it
    # has agreed with the ruler it replaces about the OLD question.
    miss = sum(a["refs_known"] - a["refs_parser"]
               for r in scored for a in r["arms"].values())
    tot = sum(a["refs_known"] for r in scored for a in r["arms"].values())
    print(f"parser cross-check: {tot - miss}/{tot} refs harvested by both the parser "
          f"and bench_trajectory.listing_refs ({(tot-miss)/max(1,tot):.3%})")
    if miss:
        ex = [a["refs_missed"] for r in scored for a in r["arms"].values() if a["refs_missed"]]
        print(f"   UNPARSED EXAMPLES: {ex[:3]}")

    # --- WHAT THIS CORPUS CANNOT SHOW, measured rather than recalled.
    hb = sum(r["arms"]["tree-brief"]["href_n"] + r["arms"]["tree-brief"]["src_n"]
             for r in scored)
    hf = sum(r["arms"]["tree-full"]["href_n"] + r["arms"]["tree-full"]["src_n"]
             for r in scored)
    print(f"corpus capability: href=/src= printed {hb} time(s) at brief, {hf} at full, "
          f"across {len(scored)} listings")
    if hb + hf < len(scored):
        print("   => the `detail` ladder is a NEAR NO-OP on this corpus and the `url` "
              "ablation cannot fire.\n      Mind2Web's snapshots carry no href and no "
              "src at all (verified: 0 of 61,709 <a>,\n      0 of 6,454 <img>, in the "
              "raw HTML, in cleaned_html, and in the rendered DOM).\n      A third and "
              "fourth structurally-absent signal beyond the two CLAUDE.md #73 names.")

    out: dict = {"n": len(scored), "sites": sites, "arms": {},
                 "href_src_printed": {"brief": hb, "full": hf}}
    print(f"\n{'arm':<13} {'chars':>7} {'slots':>6} {'reach':>7} "
          f"{'DECID':>6} {'AMBIG':>6} {'ABSENT':>7} {'DS|reach':>9} {'DS':>7}")
    for arm in ARMS:
        a = [r["arms"][arm] for r in scored]
        st = Counter(x["none"]["status"] for x in a)
        reach = sum(1 for x in a if x["reachable"])
        d, m = st["DECIDABLE"], st["AMBIGUOUS"]
        out["arms"][arm] = {
            "median_chars": statistics.median(x["chars"] for x in a),
            "median_slots": statistics.median(x["slots"] for x in a),
            "reachable": reach, "decidable": d, "ambiguous": m, "absent": st["ABSENT"],
            "ds_cond": round(d / max(1, d + m), 4), "ds_all": round(d / len(a), 4),
        }
        o = out["arms"][arm]
        print(f"{arm:<13} {o['median_chars']:>7} {o['median_slots']:>6} "
              f"{reach:>7} {d:>6} {m:>6} {st['ABSENT']:>7} "
              f"{o['ds_cond']:>9.3f} {o['ds_all']:>7.3f}")

    # --- CONTROL ARM. Identical arguments, same page load.
    base, ctl = out["arms"][PRIMARY], out["arms"]["ctrl"]
    agree = sum(1 for r in scored
                if r["arms"][PRIMARY]["none"]["status"] == r["arms"]["ctrl"]["none"]["status"])
    print(f"\nCONTROL (identical args, same page load): "
          f"DS|reach {base['ds_cond']:.3f} vs {ctl['ds_cond']:.3f}  "
          f"(delta {abs(base['ds_cond']-ctl['ds_cond'])*100:.2f}pp)   "
          f"per-action agreement {agree}/{len(scored)} = {agree/len(scored):.1%}")
    out["control_delta_pp"] = round(abs(base["ds_cond"] - ctl["ds_cond"]) * 100, 3)
    out["control_agreement"] = round(agree / len(scored), 4)

    # --- the field ablation: the paper's Table 3, our fields.
    # Run on TWO arms. `url` can only fire where href=/src= are printed, so
    # reporting it from `compact` alone would read as "href carries nothing"
    # when the truth is that nothing printed it -- a detector that cannot fire
    # (PRINCIPLES §15). A class whose ablation changed ZERO rows is printed as
    # `n/a` rather than as a drop of 0.0.
    out["ablation"] = {}
    for arm in (PRIMARY, "tree-brief"):
        print(f"\nFIELD ABLATION on {arm} — remove one printed field class from the "
              f"identity, re-measure.\n(the drop is that class's MFS membership "
              f"frequency; 'fired' is how many rows the ablation changed)")
        print(f"  {'ablated':<12} {'DS|reach':>9} {'drop pp':>8} {'AMBIG':>6} "
              f"{'fired/slots':>14}")
        base_cond = out["arms"][arm]["ds_cond"]
        out["ablation"][arm] = {}
        for which in ABLATIONS:
            a = [r["arms"][arm][which] for r in scored]
            st = Counter(x["status"] for x in a)
            d, m = st["DECIDABLE"], st["AMBIGUOUS"]
            cond = d / max(1, d + m)
            fired = sum(r["arms"][arm]["ablation_fired"].get(which, 0) for r in scored)
            slots = sum(r["arms"][arm]["slots"] for r in scored)
            out["ablation"][arm][which] = {"ds_cond": round(cond, 4), "ambiguous": m,
                                           "fired": fired, "slots": slots}
            if which != "none" and fired == 0:
                print(f"  {which:<12} {'n/a':>9} {'n/a':>8} {m:>6} "
                      f"{fired:>7}/{slots:<6}   <- NOT PRINTED on this corpus; "
                      f"unmeasurable, not zero")
                continue
            tag = "   <- baseline" if which == "none" else ""
            print(f"  {which:<12} {cond:>9.3f} {(base_cond-cond)*100:>8.1f} {m:>6} "
                  f"{fired:>7}/{slots:<6}{tag}")

    if controls:
        print("\nNEGATIVE CONTROLS (SUFFICIENCY.md §6) — these decide whether anything "
              "above is worth reading:")
        for which, want in (("+ref", "100%"), ("empty", "~0%")):
            a = [r["arms"][PRIMARY][which] for r in scored]
            st = Counter(x["status"] for x in a)
            d, m = st["DECIDABLE"], st["AMBIGUOUS"]
            cond = d / max(1, d + m)
            verdict = ("OK" if (which == "+ref" and cond > 0.999)
                       or (which == "empty" and cond < 0.001) else "*** BROKEN ***")
            print(f"  key={which:<6} DS|reach {cond:.3f}  (expected {want})  {verdict}")
            out.setdefault("controls", {})[which] = round(cond, 4)

    # --- the selection effect the headline is conditional on.
    on_d = sum(r["arms"][PRIMARY]["dup_onscreen"] for r in scored)
    on_n = sum(r["arms"][PRIMARY]["n_onscreen"] for r in scored)
    bf_d = sum(r["arms"][PRIMARY]["dup_belowfold"] for r in scored)
    bf_n = sum(r["arms"][PRIMARY]["n_belowfold"] for r in scored)
    print(f"\nSELECTION EFFECT — `DS | reachable` conditions on the target being in a "
          f"VIEWPORT-SCOPED listing.\nIf off-screen rows are more repetitive, the headline "
          f"is optimistic. Measured on the rows we DO show:")
    print(f"  on-screen rows   {on_d}/{on_n} = {on_d/max(1,on_n):.1%} share a printed "
          f"identity with another row")
    print(f"  (below-fold) rows {bf_d}/{bf_n} = {bf_d/max(1,bf_n):.1%}")
    out["selection_effect"] = {"onscreen": [on_d, on_n], "belowfold": [bf_d, bf_n]}

    # --- leave-one-site-out. 16 sites, one widget is 17% of the sample (#73),
    # so a point estimate overstates what 186 actions can support.
    los = []
    for site in sites:
        sub = [r for r in scored if r["website"] != site]
        st = Counter(r["arms"][PRIMARY]["none"]["status"] for r in sub)
        d, m = st["DECIDABLE"], st["AMBIGUOUS"]
        los.append(d / max(1, d + m))
    print(f"\nleave-one-site-out DS|reach: {min(los):.3f} – {max(los):.3f}  "
          f"(16 folds; quote the range, not the point)")
    out["loso"] = [round(min(los), 4), round(max(los), 4)]

    # --- the paper's other axis: coverage against reduction ratio.
    red = [r["reduction_vs_html"] for r in scored if r.get("reduction_vs_html")]
    if red:
        print(f"reduction ratio (listing chars / Mind2Web cleaned_html): "
              f"median {statistics.median(red):.4f}  "
              f"i.e. ~{1/statistics.median(red):.0f}x smaller")
        out["reduction_median"] = round(statistics.median(red), 5)

    # --- per-op and per-site, because an aggregate hides where it lands.
    by_op = defaultdict(lambda: [0, 0])
    for r in scored:
        s = r["arms"][PRIMARY]["none"]["status"]
        if s in ("DECIDABLE", "AMBIGUOUS"):
            by_op[r["op"]][1] += 1
            by_op[r["op"]][0] += (s == "DECIDABLE")
    print("per-op DS|reach: " + "  ".join(
        f"{k}={v[0]}/{v[1]}" for k, v in sorted(by_op.items())))
    out["by_op"] = {k: v for k, v in by_op.items()}

    amb = [r for r in scored if r["arms"][PRIMARY]["none"]["status"] == "AMBIGUOUS"]
    if amb:
        v = Counter((r.get("whose") or {}).get("verdict", "unknown") for r in amb)
        print(f"\nWHOSE AMBIGUITY IS IT? ({len(amb)} AMBIGUOUS targets, diagnosed "
              f"against the DOM's declared attributes)")
        print(f"  ours        {v['ours']:>3}  the page declares a difference our listing "
              f"does not print  <- the only actionable class")
        print(f"  inert-here  {v['inert-here']:>3}  only `aria_label` differs — Mind2Web "
              f"renames hyphenated ARIA attributes,\n                  so NO AccName "
              f"implementation (ours or Chrome's) can read it. Our gap on a\n"
              f"                  real site; a dataset artefact here.")
        print(f"  class-only  {v['class-only']:>3}  only `class` differs; the source "
              f"paper prices class at 7-10% and the locator literature down-weights it")
        print(f"  page        {v['page']:>3}  NO declared attribute separates them — "
              f"usually one link duplicated in markup;\n                  no "
              f"representation could tell them apart and clicking any may well be correct")
        print(f"  unknown     {v['unknown']:>3}")
        out["whose"] = dict(v)
        print(f"\nAMBIGUOUS examples — the target and a rival that prints the same thing "
              f"in the same place:")
        for r in amb[:12]:
            x = r["arms"][PRIMARY]["none"]
            w = r.get("whose") or {}
            print(f"  {r['website']:<13} n={x['collisions']:<3} {w.get('verdict','?'):<10} "
                  f"{str(w.get('why',''))[:46]:<48} [{x['path'][:34]}]")
            print(f"      target {x['desc'][:88]!r}")
            print(f"      rival  {x['rival'][:88]!r}")
    out["ambiguous_examples"] = [
        {"site": r["website"], "op": r["op"], "task": r["task"],
         "n": r["arms"][PRIMARY]["none"]["collisions"],
         "whose": r.get("whose"),
         "desc": r["arms"][PRIMARY]["none"]["desc"],
         "rival": r["arms"][PRIMARY]["none"]["rival"]} for r in amb]
    return out


def summarise_density(rows: list[dict], reps: list[list[dict]]) -> dict:
    ok = [r for r in rows if "skipped" not in r]
    # A COUNT IS NOT AN INVENTORY (PRINCIPLES §16). `len(ok)` includes sites
    # whose HAR replays EMPTY -- freeze_corpus records 106 and only 97 replay
    # non-empty -- and those contribute no rate at all, so printing it as the
    # sample size overstates the sample by the number of recordings that failed.
    scored = [r for r in ok if (r.get(PRIMARY) or {}).get("dup_rate") is not None]
    empty = [r["name"] for r in ok if r not in scored]
    if not scored:
        print("no sites scored")
        return {}
    print(f"\n=== AMBIGUITY DENSITY (frozen corpus, {len(scored)} real styled pages "
          f"with a non-empty replay; {len(rows) - len(ok)} skipped, "
          f"{len(empty)} replayed EMPTY: {', '.join(empty) or '-'}) ===")
    print("NO TASK LABELS EXIST HERE, so this is DENSITY and never DS: it says how "
          "many\nrows print identically to another row, not whether any task needed one."
          "\nThe Mind2Web half measures both on one corpus, and they differ by ~4x.")
    out: dict = {"n": len(scored), "skipped": len(rows) - len(ok), "empty": empty,
                 "arms": {}}
    for arm in (PRIMARY, "ctrl", "flat-compact"):
        rates = [r[arm]["dup_rate"] for r in scored
                 if r.get(arm, {}).get("dup_rate") is not None]
        if not rates:
            continue
        out["arms"][arm] = {"median": round(statistics.median(rates), 4),
                            "mean": round(statistics.fmean(rates), 4),
                            "worst": round(max(rates), 4)}
        print(f"  {arm:<13} indistinguishable rows: median {statistics.median(rates):.1%}  "
              f"mean {statistics.fmean(rates):.1%}  worst {max(rates):.1%}")
    # DRIFT FLOOR: the same arm measured twice. On replayed HARs this is real --
    # 18 recordings are named non-deterministic (#16) -- so it must be known
    # before any delta here is attributed to anything.
    if reps:
        spreads = []
        for a, b in zip(rows, reps[0]):
            if "skipped" in a or "skipped" in b or a not in scored:
                continue
            ra, rb = a.get(PRIMARY, {}).get("dup_rate"), b.get(PRIMARY, {}).get("dup_rate")
            if ra is not None and rb is not None:
                spreads.append((abs(ra - rb), a["name"]))
        if spreads:
            w = max(spreads)
            print(f"  DRIFT FLOOR (same arm, whole page re-replayed): worst "
                  f"{w[0]*100:.2f}pp on {w[1]}, median "
                  f"{statistics.median(s for s, _ in spreads)*100:.2f}pp")
            out["drift_floor_pp"] = round(w[0] * 100, 3)
    else:
        print("  DRIFT FLOOR: not measured (pass --replicates 2). Any delta here is "
              "UNVALIDATED.")
    return out


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", choices=("mind2web", "frozen"), default="mind2web")
    ap.add_argument("--limit", type=int, default=0, help="mind2web actions (0 = all)")
    ap.add_argument("-n", type=int, default=0, help="frozen sites (0 = all)")
    ap.add_argument("--replicates", type=int, default=1)
    ap.add_argument("--controls", action="store_true",
                    help="also score the +ref / empty negative controls")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--tag", default="latest")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    if args.corpus == "frozen":
        sites = load_sites()
        if args.n:
            sites = sites[: args.n]
        runs: list[list[dict]] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            for rep in range(max(1, args.replicates)):
                rows = []
                for i, (name, url) in enumerate(sites):
                    r = await density_site(browser, name, url, i + rep)
                    rows.append(r)
                    tagk = r.get(PRIMARY, {})
                    print(f"  [{rep}][{i+1:>3}/{len(sites)}] {name:<22} "
                          + (r["skipped"] if "skipped" in r
                             else f"slots {tagk.get('slots'):>4}  dup "
                                  f"{(tagk.get('dup_rate') or 0):.1%}"))
                runs.append(rows)
            await browser.close()
        summary = summarise_density(runs[0], runs[1:])
        payload = {"mode": "frozen", "runs": runs, "summary": summary,
                   "seconds": round(time.time() - t0, 1)}
    else:
        samples = load_samples(args.limit)
        if not samples:
            print("no samples — run tools/fetch_mind2web.py first")
            return 1
        rows = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(viewport=VIEWPORT)
            await ctx.add_init_script(path=TAG_JS)
            page = await ctx.new_page()
            for i, s in enumerate(samples):
                try:
                    r = await score_action(page, s, i, args.controls)
                except Exception as e:
                    r = {"website": s.get("website"), "status": "error", "err": str(e)[:140]}
                rows.append(r)
                if (i + 1) % 20 == 0 or i + 1 == len(samples):
                    ok = [x for x in rows if x.get("status") == "ok"]
                    st = Counter(x["arms"][PRIMARY]["none"]["status"] for x in ok)
                    d, m = st["DECIDABLE"], st["AMBIGUOUS"]
                    print(f"  [{i+1:>3}/{len(samples)}] DS|reach so far "
                          f"{d}/{d+m} = {d/max(1,d+m):.1%}")
            await browser.close()
        summary = summarise(rows, args.controls)
        payload = {"mode": "mind2web", "rows": rows, "summary": summary,
                   "seconds": round(time.time() - t0, 1)}

    (OUT / f"{args.tag}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if args.baseline:
        (OUT / "baseline.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print("\nbaseline written -> temp/sufficiency/baseline.json")
    print(f"\n{round(time.time()-t0)}s  -> temp/sufficiency/{args.tag}.json")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
