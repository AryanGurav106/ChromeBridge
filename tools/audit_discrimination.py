"""DISCRIMINATION: can a READER tell two rows of the listing apart, at any stage?

WHY THIS EXISTS. CLAUDE.md #117 audited which instrument answers which question and
found three axes covered -- presence (`audit_stage_generality`), name correctness
(`audit_name_correctness`), reachability (`measure_findability_at_stage`) -- and TWO
shapes falling between them. #118 closed one. This is the other, and #117 named it as
the one to build next:

    "DISCRIMINATION -- telling two look-alike rows apart -- whose only instrument runs
     on static snapshots and whose population is the 52% of probes every stage ruler
     sets aside as contested."

The three existing rulers all read CLEAN on a listing that does not determine the
action. Presence counts a look-alike pair present. The name oracle can score BOTH of a
look-alike pair exactly correct. Reachability EXCLUDES them from its denominator by a
documented rule (`measure_findability_at_stage.score_arm`: "contested ... excluded from
the denominator"). Nobody has asked whether a reader could pick the one they meant.

THE SUBTLETY THAT DECIDES WHETHER ANY NUMBER HERE MEANS ANYTHING
----------------------------------------------------------------
Every row carries a unique `ref_N`, so "can they be told apart" is trivially YES and
that answer is worth nothing. The question is whether the listing prints something a
reader could use to pick the INTENDED one -- a field that carries MEANING, not mere
identity. So:

  * `ref_N` is STRIPPED from every key, and `--controls` ships the falsifier that puts
    it back: it must report 1.000 unique at every rung. A ladder reporting ~100% is
    indistinguishable from a ladder that counted the ref.
  * geometry is an OPT-IN rung reported separately (`geometry=true`), for the same
    reason `measure_sufficiency` makes it a control: x/y make every row unique by
    construction and the number drifts (#23: 110px, #25: 1,097px).
  * `href`/`src` are an OPT-IN rung reported separately -- they are absent from the
    shipped default `detail="compact"` (#10), so a caller who did not ask for them
    cannot use them.

WHAT THE FIELD SET IS, AND WHY IT IS NOT THE DESCRIPTOR LADDER
---------------------------------------------------------------
`audit_descriptors.py` measures the FLOW DESCRIPTOR's ladder -- tag/role/type, name,
section, under, near -- which is a MATCHING KEY resolved in Python against the
structured array. Its machinery (cumulative `uniq_<lv>`, the tie-size distribution) is
reused here verbatim in shape. The FIELD SET is different and must be, because this asks
about a READER looking at printed output:

  * `under=` is in the structured array and is NEVER printed by `read_page` -- it is a
    `find` output field. It is in the descriptor ladder and is excluded here.
  * `section=` IS printed, but only in `format="flat"`; `_treeLines` strips it from
    every row and replaces it with indentation (#27). So the default (tree) and the
    flat format get DIFFERENT rungs, reported separately.
  * the state/annotation parentheticals -- `(disabled)`, `(required)`, `(read-only)`,
    `(unselected)`, `(collapsed)`, `(post-key)`, constraints, `options=`, `help=` -- are
    printed on every row and are not in the descriptor ladder at all (descriptor.py
    excludes state deliberately: "identify by them and a step can only find a control
    already in the state the step exists to produce"). A READER has no such constraint.

ONE SPELLING, AND IT IS THE COLLECTOR'S (PRINCIPLES 17)
--------------------------------------------------------
The rung keys are built from the entry's own fields, and every one is then VERIFIED
against `e.line` -- the REAL `_fmtLine` output, which the collector attaches to every
structured entry. `decomp_fail` counts any row whose computed identity is not a prefix
of its own printed line, so a format change under this probe fails loudly instead of
silently mis-attributing. ANCESTRY is not reconstructed at all: it is parsed out of the
printed listing's own indentation, which is exactly what the reader sees, including the
tree's pruning and grouping.

THE RESIDUAL IS CLASSIFIED, NOT POOLED
---------------------------------------
Three outcomes and only the third is a defect, which is `measure_sufficiency`'s own
discriminator (its `ATTR_PROBE` and `_DECLARED` allowlist are imported, not restated):

  INTERCHANGEABLE  acting on any member does the same thing -- same href, or the same
                   element reached twice, or identical declared attributes AND text.
                   #116 measured 29 of these on one site. Costs nothing.
  OURS             the DOM declares a difference the listing does not print. A gap.
  PAGE             the document declares nothing that separates them. No representation
                   could, so this is the page's ambiguity and not ours.

WHAT THIS CANNOT ANSWER -- do not quote a number without these
---------------------------------------------------------------
  * whether a model USES the information. This asks whether the INFORMATION IS PRESENT.
    #75 is the entry where conflating those two wasted a day, and `measure_sufficiency`
    says the same of its own DS: "DECIDABLE means the listing permits a correct choice,
    not that a model makes one."
  * whether AMBIGUOUS is a failure. It is not: the agent can escalate for one model turn
    (~3.6s, #38) or guess 1/N. It is a COST, and the interchangeable class is not even
    that.
  * whether the name is RIGHT (`audit_name_correctness`) or REACHABLE
    (`measure_findability_at_stage`). A wrong name shared by two rows scores contested
    here and says nothing about correctness.
  * hover-only menus, logins, paywalls, cross-origin frames, one path per site --
    inherited wholesale from #89's driver.

Run:
    python tools/audit_discrimination.py --selftest          # fixture firing proofs
    python tools/audit_discrimination.py --fire --only A B   # LIVE firing proof
    python tools/audit_discrimination.py --pool usable85 --conc 6 --stages 4
    python tools/audit_discrimination.py --corpus frozen -n 40
    python tools/audit_discrimination.py --cost -n 106       # BOTH halves of detail="brief"
    python tools/audit_discrimination.py --report temp/discrimination/main/pass0.json

THERE IS NO `--controls` FLAG, and this block named one until it was checked against
`add_argument`. Both falsifiers run on EVERY pass instead and are printed in the report:
`CONTROL +ref_N` must read 100%, and the `+box()` rung is the second one. A flag that
does not exist is #67's `--check-only` -- documented, reassuring, and doing nothing.

Findings: docs/research/DISCRIMINATION-2026-11.md
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import re
import hashlib
import pathlib
import statistics
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
from playwright.async_api import async_playwright  # noqa: E402
import audit_stage_generality as ASG  # noqa: E402  (the interaction driver, verbatim)
import measure_findability_at_stage as MFS  # noqa: E402  (is_blanked / listing_index / _stride)
import measure_sufficiency as MS  # noqa: E402  (ATTR_PROBE / _DECLARED -- the residual verdict)
from core.flows import descriptor as D  # noqa: E402  (_targetable, the actionable pool)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VIEWPORT = ASG.VIEWPORT
OUT = ROOT / "temp" / "discrimination"
FROZEN = ROOT / "temp" / "frozen"
# PROVENANCE. #73's hazard: another process editing `extension/background.js` mid-run
# makes a number un-re-derivable, and #117's probe re-hashes after every arm for exactly
# that reason. Hashed at IMPORT and asserted unchanged before the artefact is written.
_SRC_HASH = hashlib.sha256(
    (MFS.MF.COLLECT + "\n" + (ROOT / "extension" / "listener_tag.js")
     .read_text(encoding="utf-8")).encode("utf-8")).hexdigest()[:16]
_PROBE_HASH = hashlib.sha256(
    pathlib.Path(__file__).read_bytes()).hexdigest()[:16]

MAX_GROUPS_PROBED = 40     # contested groups per stage handed to the attribute probe
MAX_MEMBERS_PROBED = 8     # members of one group compared (a 200-row crowd needs no more)


# ======================================================================================
# COLLECTION. One evaluate per stage. The listing is what a reader sees; the structured
# arrays carry the fields AND `e.line`, which is the real _fmtLine output for that row.
# `brief` is collected ONLY for href -- it is the cheapest detail level that carries one
# (#16b), so pricing the opt-in rung at `full` would price the wrong thing.
# ======================================================================================
def _collect_js():
    return ("(function(){ " + MFS.MF.COLLECT + ";"
            " const listing = _collectInteractivePage(false, null, 'compact', false, false, 'tree');"
            " const flat    = _collectInteractivePage(false, null, 'compact', false, false, 'flat');"
            " const compact = _collectInteractivePage(true,  null, 'compact', false, false, 'tree');"
            " const brief   = _collectInteractivePage(true,  null, 'brief',   false, false, 'tree');"
            " return { listing: String(listing), flat: String(flat), compact: compact,"
            "          brief: brief, url: location.href, title: document.title }; })()")


def _ents(v):
    """Structured mode may answer with a JSON STRING; MFS and ASG carry the same guard."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return []
    return v or []


_NORM_RE = re.compile(r"\s+")


def _norm(s):
    return _NORM_RE.sub(" ", unicodedata.normalize("NFC", s or "")).strip()


def _j(s):
    """JS JSON.stringify, which is what _fmtLine emits. ensure_ascii=False or every
    non-Latin label diverges from the real line and `decomp_fail` fires on the whole
    corpus -- C23's rule, met here as a measurement requirement rather than an output one."""
    return json.dumps(s, ensure_ascii=False)


# ======================================================================================
# THE PRINTED ROW, DECOMPOSED.
#
# _fmtLine concatenates in ONE fixed order:
#   ref_N | tagtype IDENT near href src con dsc opt act role section req uns dis ro
#          orph bak nw nt tp sy ed pop col cnv xf sr med box occ clip off
# so peeling from the front in that order is exact, and whatever remains after the
# peelable prefixes is the STATE block. Every peel is CHECKED against the real line.
# ======================================================================================
_ROLE_RE = re.compile(r" role=[^\s]+")
_SECTION_RE = re.compile(r" section=[a-z-]+")
_BOX_RE = re.compile(r" \| box\([^)]*\)")
# What an IDENTITY looks like at the start of a row's remainder: a quoted string, or one
# of _fmtLine's named identity slots. State tokens start with `(` or a different key.
_IDENT_LEFTOVER = re.compile(r' (?:"|name=|value=|submits=|placeholder=)')


def printed_identity(e, blank=None):
    """The identity slot _fmtLine builds. `blank` selects which of the two shipped rules
    applied: #74's blanking (what the STRUCTURED `e['line']` and therefore `find` use) or
    the raw fields (what the TREE prints, since it runs #29's container-label rollup
    instead). `decompose` tries both and lets the real row decide -- see its docstring
    for the Bootstrap case where the two disagree."""
    if MFS.is_blanked(e) if blank is None else blank:
        e = dict(e, name="", label="", text="")
    parts = []
    for k in ("name", "value", "submits", "placeholder"):
        v = e.get(k)
        if v:
            parts.append(k + "=" + _j(v))
    if not parts and e.get("text"):
        lab, txt = e.get("label") or "", e["text"]
        parts.append(_j(lab if (lab and len(lab) > len(txt) and lab.find(txt) >= 0) else txt))
    if not parts and e.get("iconOnly"):
        parts.append("(unlabeled-icon)" if e.get("iconGraphic") else "(unlabeled)")
    elif not parts and e.get("label"):
        parts.append(_j(e["label"]))
    return " ".join(parts)


# `near=` IS READ OFF THE ROW, NOT OFF THE ENTRY, and that is not a style choice.
# #37 suppresses a hint shared by rows that have their own identity -- so a `near` that
# SURVIVES is one the collector judged to be doing work. That suppression runs on the
# STRING-listing path, and the structured branch `return out`s before it, so the entry
# keeps a `near` the listing never prints. Measured on Bootstrap's nav:
#     e['line']    ref_68 | a "Icons" near="Docs Examples Icons Blog" section=nav …
#     tree row     ref_68 | a "Icons" (opens NEW tab)
# Computing it from the field credited the reader with a discriminator that is not on
# the page in front of them. Caught by the decomposition tripwire, which refused four
# rows rather than quietly scoring them.
_NEAR_RE = re.compile(r' near="(?:[^"\\]|\\.)*"')


def decompose(e, line=None, fail_sink=None):
    """Split the REAL printed row into the segments a reader can use.

    `line` IS THE READER'S ROW AND `e['line']` IS NOT, which cost a rewrite. The entry's
    own `line` is built in the structured branch with #74's blanking applied -- that is
    what `find` prints. The TREE applies its own container-label rollup instead (#29's
    TR10: subtract each kept descendant's label and drop the container's only if nothing
    remains), so the two DISAGREE. Measured on Bootstrap's footer nav:

        e['line']     ref_74 | a section=nav (opens NEW tab) (container — the text here…)
        tree listing  ref_74 | a "GitHub" (opens NEW tab)

    Three social links read as three identical rows under `e['line']` and as GitHub / X /
    Open Collective in the listing a reader is handed. Measuring the first would have
    reported a defect that the shipped output does not have. So the caller passes the row
    out of the listing itself and this peels THAT.

    BOTH IDENTITY RULES ARE TRIED AND THE LINE DECIDES, rather than this probe deciding
    which one the format applied. Returns None when neither peels, which is the tripwire.
    """
    line = (line if line is not None else e.get("line")) or ""
    if " | " not in line:
        if fail_sink is not None:
            fail_sink.append({"mmid": e.get("mmid"), "why": "no-separator", "line": line[:120]})
        return None
    body = line.split(" | ", 1)[1]
    m = re.match(r"\S+", body)
    if not m:
        if fail_sink is not None:
            fail_sink.append({"mmid": e.get("mmid"), "why": "no-tag", "line": line[:120]})
        return None
    tagtype, after = m.group(0), body[m.end():]

    # THE EMPTY CANDIDATE ALWAYS PEELS, WHICH KILLED THE TRIPWIRE. With `""` in this
    # list unconditionally, `chosen` could never be None, so `decomp_fail` read 0 on
    # every corpus whether or not anything had gone wrong -- PRINCIPLES 15, in the probe
    # whose own report prints that counter as evidence. Worse than a dead counter: a row
    # whose identity failed to peel silently got `ident=""` and had its identity text
    # swept into `state`, which moves the IDENTITY rung without moving the full one.
    #
    # `""` is a LEGITIMATE outcome -- #29's container-label rollup drops a container's
    # label when its kept descendants account for all of it, so the tree really does
    # print `ref_7 | div` for a row whose entry carries a name. It is kept, and COUNTED
    # separately (`ident_rolled`) so its size is visible instead of being absorbed.
    chosen, rolled = None, False
    for cand in (printed_identity(e, blank=False), printed_identity(e, blank=True), ""):
        rest = after
        if cand and not rest.startswith(" " + cand):
            continue
        rolled = (not cand) and bool(printed_identity(e, blank=False))
        rest = rest[len(cand) + 1:] if cand else rest
        m2 = _NEAR_RE.match(rest)
        chosen = (cand, m2.group(0).strip() if m2 else "", rest[m2.end():] if m2 else rest)
        break
    ident, near, rest = chosen
    # ...AND THE TRIPWIRE IS REVIVED HERE, because `""` peeling unconditionally is what
    # killed it. A row whose label the tree ROLLED UP prints no identity at all, so what
    # follows the tag is state. A row where this probe computed the WRONG identity leaves
    # the identity TEXT behind, which still looks like one. The two are told apart by
    # exactly that, so a format change fails loudly instead of being absorbed as a
    # rollup and swept into `state`.
    if not ident and _IDENT_LEFTOVER.match(rest):
        if fail_sink is not None:
            fail_sink.append({"mmid": e.get("mmid"), "why": "ident-mismatch",
                              "computed": printed_identity(e, blank=False)[:90],
                              "line": line[:140]})
        return None
    # href/src, when the arm carries them. Peeled so they do not leak into STATE.
    for k in ("href", "src"):
        v = e.get(k)
        if v and rest.startswith(" " + k + "=" + _j(v)):
            rest = rest[len(k) + len(_j(v)) + 2:]
    rm = _ROLE_RE.search(rest)
    role = rm.group(0).strip() if rm else ""
    sm = _SECTION_RE.search(rest)
    section = sm.group(0).strip() if sm else ""
    state = _BOX_RE.sub("", _SECTION_RE.sub("", _ROLE_RE.sub("", rest))).strip()
    return {"tag": tagtype, "role": role, "ident": ident, "near": near,
            "state": state, "section": section, "rolled": rolled}


def fold_member(mmid, line):
    """A FOLD row carries many refs on one line as `N:"label"`. What the reader sees of
    one member is its own quoted label plus the header's shared shape, so that is what
    this returns -- peeling the header as if it were a row would give every member the
    fold's own description and make them identical by construction."""
    m = re.search(r'(?<![0-9])' + re.escape(str(mmid)) + r':("(?:[^"\\]|\\.)*")', line)
    if not m:
        return None
    head = re.split(r'(?<![0-9])\d+:"', line)[0].strip()
    # A FOLD HEADER AND THE CAP'S OVERFLOW LIST ARE DIFFERENT SURFACES AND ARE NAMED
    # SEPARATELY. A fold states the shape its members share (`#1 a:`, `6x button,
    # identical siblings, in document order`); the overflow list states NOTHING about any
    # member beyond its label (#27 -- the refs stay actionable and the detail does not).
    # Pooling them would hide that the weakest surface in the listing is a distinct one.
    kind = "<overflow>" if "OMITTED BUT ACTIONABLE" in head else "<fold>"
    return {"tag": kind, "role": "", "ident": m.group(1), "near": "",
            "state": _norm(head)[:140], "section": "", "rolled": False}


# ======================================================================================
# ANCESTRY, PARSED OUT OF THE PRINTED LISTING'S OWN INDENTATION.
#
# NOT reconstructed from the DOM. `_treeLines` prunes single-kept-child chains, drops
# the tag word from bare wrappers, groups identical siblings POSITIONALLY and sorts
# groups by document position (#27, #29) -- a DOM walk would model none of that and
# would credit the reader with structure the tree does not print. The indentation IS
# the structure the reader sees, so it is read rather than inferred.
# ======================================================================================
_REF_IN_LINE = re.compile(r"\bref_(f?\d+(?::\d+)?)\b")
_FOLD_IN_LINE = re.compile(r'(?<![0-9])(f?\d+(?::\d+)?):"')


def _row_key(line):
    """What a reader can see of a row, for use as an ANCESTOR label. Refs stripped: an
    ancestor identified by its own ref would smuggle the ref back in one level up, which
    is the exact falsifier --controls ships."""
    s = _REF_IN_LINE.sub("ref", line.strip())
    s = _FOLD_IN_LINE.sub('"', s)
    return _norm(s)[:120]


def ancestry_index(listing):
    """mmid -> (tuple of ancestor row keys, outermost first).

    The tree indents one space per level (#29). A row's ancestors are the rows above it
    at strictly decreasing indent. Fold members take their FOLD ROW's ancestry, which is
    correct: they are siblings under one parent.

    A STRUCTURE ROW HAS NO REF AND IS STILL AN ANCESTOR. `main`, `nav`, `form` and
    `table (4 rows, read with ref_5)` are rows a reader sees and groups by, so keying on
    "has a ref" drops exactly the landmark level the tree exists to express -- caught by
    the selftest, which read `('table …',)` where the listing plainly prints `main` above
    it. The body is therefore taken from `_ACT_LINE`, the SAME boundary marker C12 pins
    and `measure_sufficiency` imports, and the only lines skipped inside it are the
    legend/notice convention `- …`. Restating either would be the string-contract break
    that kept `delta` dead for its entire life (#30).
    """
    # TO THE END OF THAT LINE, not to the marker. `_ACT_LINE` is a PREFIX -- the rest of
    # the sentence continues on the same physical line -- so splitting on the marker
    # alone leaves that tail as the body's first "row", at indent 1. Harmless wherever
    # the tree starts at indent 0 and a spurious ancestor for every subtree wherever it
    # does not. Seen on github's issues listing before it could do any damage.
    body = (listing or "").split(MS._ACT_LINE, 1)
    body = body[1] if len(body) > 1 else body[0]
    if "\n" in body:
        body = body.split("\n", 1)[1]
    anc, stack = {}, []        # stack of (indent, row_key)
    for raw in body.split("\n"):
        if not raw.strip():
            continue
        if raw.lstrip().startswith("- "):
            continue           # legend line / notice, never a row
        ind = len(raw) - len(raw.lstrip(" "))
        while stack and stack[-1][0] >= ind:
            stack.pop()
        chain = tuple(k for _, k in stack)
        for r in _REF_IN_LINE.findall(raw) + _FOLD_IN_LINE.findall(raw):
            anc.setdefault(str(r), chain)
        stack.append((ind, _row_key(raw)))
    return anc


# ======================================================================================
# THE LADDER. Cumulative over PRINTED fields, in the order a reader reads a tree row.
# Reported with a LEAVE-ONE-OUT marginal beside it, because a cumulative ladder's
# attribution depends on an order I chose and the marginal does not.
# ======================================================================================
LEVELS = (
    ("tag+role",     ("tag", "role")),
    ("+identity",    ("ident",)),
    ("+ancestry",    ("anc",)),
    ("+near",        ("near",)),
    ("+state",       ("state",)),
)
FULL_FIELDS = tuple(f for _, fs in LEVELS for f in fs)
# Reported SEPARATELY, never folded into the default ladder: a field the caller did not
# ask for is not available to them.
OPTIN = (
    ("+href/src  (detail=\"brief\")", ("href",)),
    ("+box()     (geometry=true)",    ("box",)),
)


def key_of(rec, fields):
    return tuple(rec.get(f, "") for f in fields)


def _uniq_and_ties(recs, fields):
    """Share of rows picked out by this key alone, and the sizes of the crowds that are
    not. Same shape as audit_descriptors.py's uniq_<lv>/tie_med_<lv>."""
    counts = collections.Counter(key_of(r, fields) for r in recs)
    uniq = sum(1 for r in recs if counts[key_of(r, fields)] == 1)
    ties = [counts[key_of(r, fields)] for r in recs if counts[key_of(r, fields)] > 1]
    return uniq, ties


def ladder(recs):
    """The cumulative ladder, the leave-one-out marginals, and the opt-in rungs."""
    n = len(recs)
    if not n:
        return None
    out = {"rows": n, "cum": [], "loo": [], "optin": [], "flat": None}
    fields = []
    for label, fs in LEVELS:
        fields += list(fs)
        uniq, ties = _uniq_and_ties(recs, tuple(fields))
        out["cum"].append({"rung": label, "uniq": uniq, "n": n,
                           "rate": round(uniq / n, 4),
                           "tie_med": statistics.median(ties) if ties else 0,
                           "tie_max": max(ties) if ties else 0,
                           # HOW CROWDED, not just how many. A tie of 2 is resolvable by
                           # one more declared field; a tie of 40 is a repeated record
                           # and wants an ordinal -- audit_descriptors.py's own reason
                           # for carrying the distribution rather than a count.
                           "tie_hist": dict(collections.Counter(ties)),
                           "contested": n - uniq})
    full_uniq, _ = _uniq_and_ties(recs, FULL_FIELDS)
    for f in FULL_FIELDS:
        rest = tuple(x for x in FULL_FIELDS if x != f)
        u, _ = _uniq_and_ties(recs, rest)
        out["loo"].append({"field": f, "without": u, "with": full_uniq,
                           "marginal": round((full_uniq - u) / n, 4)})
    # THE FALSIFIER, computed on every run rather than only in the fixture selftest. If
    # this is not 100% the key is not carrying the ref -- and if the reported rungs ever
    # approach it, that is the first thing to check (the brief's own warning).
    u, _ = _uniq_and_ties(recs, FULL_FIELDS + ("ref",))
    out["control_ref"] = {"uniq": u, "n": n, "rate": round(u / n, 4)}
    for label, fs in OPTIN:
        u, ties = _uniq_and_ties(recs, FULL_FIELDS + fs)
        out["optin"].append({"rung": label, "uniq": u, "n": n,
                             "rate": round(u / n, 4),
                             "gain": round((u - full_uniq) / n, 4),
                             "tie_med": statistics.median(ties) if ties else 0})
    return out


def contested_groups(recs, fields=FULL_FIELDS):
    """The crowds that survive every printed field. Keyed, so members can be compared."""
    g = collections.defaultdict(list)
    for r in recs:
        g[key_of(r, fields)].append(r)
    return {k: v for k, v in g.items() if len(v) > 1}


# ======================================================================================
# THE RESIDUAL VERDICT. measure_sufficiency's discriminator, imported rather than
# restated: if the page declares a difference we do not print, the gap is OURS; if the
# document says nothing that separates them, no representation could.
# ======================================================================================
# A declared difference a READER could act on, against one that is a developer token.
# The split matters for the recommendation and not for the verdict: `id` and the wire
# `name` differ on almost every repeated control (#61 measured `id` coverage at 6.8% and
# REJECTED it as a descriptor rung), so pooling them would call nearly every collision
# our gap and produce a headline that is true and useless.
_HUMAN = {"alt", "title", "aria-label", "aria-labelledby", "value", "placeholder",
          "href", "src", "label", "role", "type"}
_DEVKEY = {"id", "name", "for", "checked", "selected", "disabled", "required",
           "multiple"}


_OPTIN_FIELDS = {"href", "src"}


def _evidence(m, a, atoms):
    """What could tell THIS member apart, as strings a reader might see in the listing.

    WORDS, NOT THE WHOLE STRING, AND THE WHOLE STRING WAS WRONG. A container's
    `textContent` is its children's text CONCATENATED -- `'Show only: Any genre Bibles
    Biographies'` -- and the listing prints those children as separate rows, so that
    string can never appear in it contiguously however complete the listing is. Testing
    it as one substring reported 1,018 rows as "the page declares something that is
    nowhere in the listing" when every word of it was there, one row down. That is the
    damning direction, and only looking at a case caught it (PRINCIPLES 8).

    AUTHORED strings (`title`, `alt`, `aria-label`) are kept WHOLE as well as split: an
    author wrote those as one phrase, so their presence verbatim is the stronger signal.
    A 4-character floor on a word, and a 6-character window for a script that does not
    space its words, so a common short token cannot match the listing by accident.
    """
    out = set(atoms.get(str(m["mmid"])) or [])
    for k in ("title", "alt", "aria-label"):
        v = _norm(a.get(k) or "")
        if len(v) >= 3:
            out.add(v)
    for k in ("__text", "title", "alt", "aria-label"):
        v = _norm(a.get(k) or "")
        if not v:
            continue
        words = [w for w in v.split(" ") if len(w) >= 4]
        if words:
            out |= set(words)
        elif len(v) >= 6:
            out.add(v[:6])          # no spaces: Chinese, Japanese, Thai
    return out

# ONE SPOT REACHED TWICE IS ONE ACTION. Since #28 the container rules DEMOTE rather than
# delete, so one control is routinely two or three nested entries -- HN's upvote arrow is
# a `<div>` inside an `<a>`, and both are listed. Clicking either upvotes. The tree
# collapses them onto one row when label AND box match exactly (#29), but the cap's
# OVERFLOW list prints every ref on its own, so the pair reappears there as a contested
# crowd. Asking the DOM is exact where box containment would only be suggestive.
NEST_PROBE = r"""
(groups) => groups.map(refs => {
  const els = refs.map(m => document.querySelector(`[mmid="${String(m).replace(/"/g,'')}"]`));
  if (els.some(e => !e) || els.length < 2) return false;
  // EVERY pair, not just consecutive ones: three rows are one spot only when all three
  // lie on one ancestor chain.
  return els.every((a, i) => els.every((b, j) =>
      i === j || a.contains(b) || b.contains(a)));
})
"""


def classify(members, attrs, listing_norm="", nested=False):
    """The brief's three outcomes, with OURS split by what it would take to close it.

      INTERCHANGEABLE  acting on any member does the same thing -- PROVABLE, not assumed:
                       one declared destination shared by all of them. A nav link
                       duplicated for a responsive layout, or a logo in header and
                       footer. #116 measured 29 of these on one site. Costs nothing.
      OURS-OPTIN       the only human-meaningful difference is `href`/`src`, which the
                       shipped `detail="brief"` prints (#16b). A RECOVERY EXISTS and is
                       one parameter, so pooling this with a real gap would make the
                       headline true and useless.
      OURS-ELSEWHERE   the difference is text that IS in the listing, on ANOTHER row --
                       the record each member sits in. The information reached the
                       reader; pairing it with this row needs document order, which is
                       exactly what #30 warns about ("position is not rank, merge by
                       ref") rather than something it prints.
      OURS-ABSENT      the page declares something that appears NOWHERE in the listing.
                       The only class here that is unambiguously a gap of ours.
      OURS-DEVKEY      only an internal key (`id`, the wire `name`) differs. #61
                       measured `id` coverage at 6.8% and REJECTED it as a descriptor
                       rung; a human cannot read one off the screen either.
      PAGE             nothing the document declares separates them. No representation
                       could, so this is the page's ambiguity. NOT the same as
                       interchangeable -- they may well do different things and the
                       document simply does not say which is which.

    RECORD TEXT IS THE SHARPEST EVIDENCE AND IT IS NOT RE-SPELLED. `descriptor.atoms_map`
    is the shipped function that answers "what text does this member's own record carry
    that its siblings' do not" (#83, #99), computed from the collector's own
    `recordAtoms`. Writing a second climb here would be #21's one-concept-two-spellings
    on the exact concept `search_page`'s `_climbTo` and the flow witness already share.
    """
    got = [attrs.get(str(m["mmid"])) for m in members]
    if any(a is None for a in got):
        return "unresolved", {}
    if nested:
        return "interchangeable", {"why": "nested in one another — one spot, one action"}
    hrefs = {(a.get("href") or "") for a in got}
    if len(hrefs) == 1 and hrefs != {""}:
        return "interchangeable", {"why": "one declared destination for all of them"}

    declared = {}
    for a in got:
        for k, v in a.items():
            if k in MS._DECLARED and k not in MS._INERT_HERE:
                declared.setdefault(k, set()).add(v)
    differing = {k for k, vs in declared.items() if len(vs) > 1}
    for a in got:                       # present on some, absent on others, is a difference
        for k in MS._DECLARED:
            if k not in MS._INERT_HERE and (k in a) != (k in got[0]):
                differing.add(k)
    human = set(differing & _HUMAN)
    devkey = sorted(differing & _DEVKEY)

    if len({_norm(a.get("__text") or "") for a in got}) > 1:
        human.add("rendered-text")
    atoms = D.atoms_map([{"mmid": m["mmid"], "recordAtoms": m.get("atoms") or []}
                         for m in members])
    has_atoms = len(atoms) == len(members) and len(members) > 1
    if has_atoms:
        human.add("record-text")

    if not human:
        if devkey:
            return "ours-devkey", {"why": "only an internal key differs: "
                                          + ",".join(devkey[:4]), "fields": devkey[:6]}
        classy = {(a.get("class") or "") for a in got}
        return "page", {"why": "nothing the document declares separates them"
                               + (" (class differs)" if len(classy) > 1 else "")}

    fields = sorted(human)
    if human <= _OPTIN_FIELDS:
        return "ours-optin", {"why": 'detail="brief" prints ' + ",".join(fields),
                              "fields": fields}
    # IS THE DISTINGUISHING TEXT IN THE LISTING AT ALL? "present but on another row" and
    # "absent" need different answers, and only one of them is a gap in what we print.
    #
    # AT LEAST ONE piece of evidence per member, not all of it. The first version
    # required every one of a member's record atoms to appear and classified Hacker
    # News' 16 upvote arrows `ours-absent` -- because the RANK (`'2.'`) is not printed
    # while the story title and the domain both are. One printed atom that is unique
    # within the crowd is a discriminator; demanding the rest made a reader's available
    # evidence look absent, in the damning direction (PRINCIPLES 8).
    rest = sorted(human - _OPTIN_FIELDS)
    if listing_norm:
        ev = [_evidence(m, a, atoms) for m, a in zip(members, got)]
        shown = 0
        for i, s in enumerate(ev):
            others = set().union(*(x for j, x in enumerate(ev) if j != i)) if len(ev) > 1 else set()
            # Unique WITHIN the crowd, or it says nothing about which member this is.
            # >=3 chars so a one- or two-character token cannot match the listing by
            # accident and flatter the verdict.
            if any(len(t) >= 3 and t.casefold() in listing_norm for t in (s - others)):
                shown += 1
        if shown == len(ev):
            return "ours-elsewhere", {
                "why": "what separates them IS printed, on another row",
                "fields": fields}
    return "ours-absent", {"why": "the page declares " + ",".join(rest[:4])
                                  + ", and it is nowhere in the listing",
                           "fields": fields, "devkey": devkey[:4]}


# ======================================================================================
# PER-STAGE MEASUREMENT
# ======================================================================================
def build_recs(compact, brief, listing, fails):
    """One record per PRINTED ROW of this listing, from that listing's own rows."""
    idx = MFS.listing_index(listing)
    anc = ancestry_index(listing)
    recs, blanked, n_decomp_fail, n_collapsed, n_rolled = [], 0, 0, 0, 0
    # ONE PRINTED ROW IS ONE ROW. #29's collapse puts several refs on a single row when
    # label AND all four box fields are exactly equal -- one spot, printed once,
    # "outermost first". Counting each ref separately would manufacture a contested pair
    # out of something a reader sees as one line, and inflate the headline in the
    # damning direction. A FOLD line also carries many refs and is NOT folded here,
    # because its members have different boxes and are different elements.
    seen_rows = set()
    for e in compact:
        mm = str(e.get("mmid"))
        if mm not in idx:
            continue                     # not printed: the reader cannot see this row
        rowid = (idx[mm], e.get("x"), e.get("y"), e.get("w"), e.get("h"))
        if rowid in seen_rows:
            n_collapsed += 1
            continue
        seen_rows.add(rowid)
        d = fold_member(mm, idx[mm]) or decompose(e, idx[mm], fails)
        if d is None:
            n_decomp_fail += 1
            continue
        if MFS.is_blanked(e):
            blanked += 1
        if d.get("rolled"):
            n_rolled += 1
        b = brief.get(mm) or {}
        recs.append({
            "mmid": mm, "tag": d["tag"], "role": d["role"], "ident": d["ident"],
            "near": d["near"], "state": d["state"], "section": d["section"],
            "anc": " > ".join(anc.get(mm, ())),
            "href": (b.get("href") or "") + "|" + (b.get("src") or ""),
            "box": "%s,%s,%s,%s" % (e.get("x"), e.get("y"), e.get("w"), e.get("h")),
            "act": bool(D._targetable(e)),
            "atoms": e.get("recordAtoms") or [],   # evidence for the verdict, never a rung
            "ref": mm,                   # ONLY for --controls. Never in a reported rung.
        })
    return recs, {"blanked": blanked, "decomp_fail": n_decomp_fail,
                  "collapsed_refs": n_collapsed, "listing_rows": len(idx),
                  "ident_rolled": n_rolled}


async def measure_stage(page, label, res, site, fails, groups_sink):
    """The TREE is the shipped default and is the primary arm; FLAT is reported beside
    it because the two differ by more than `section=` -- the tree also runs the
    container-label rollup and the identical-nested-row collapse (#29)."""
    listing, compact = res["listing"], _ents(res["compact"])
    brief = {str(e.get("mmid")): e for e in _ents(res["brief"])}
    recs, meta = build_recs(compact, brief, listing, fails)
    frecs, _fm = build_recs(compact, brief, res["flat"], [])
    row = {}

    # #117's DEFINITION, REPRODUCED EXACTLY, so the two numbers can be compared instead
    # of set side by side and left to look like a disagreement. It reports 52% of its
    # PROBES contested; that is a different population in three ways, all pushing the
    # same way: it counts over the WHOLE-PAGE structured array (this one counts rows the
    # listing PRINTS, which is viewport-scoped and capped), it keys on `identity_of`
    # alone (first non-empty of name/label/text/value/placeholder) rather than on every
    # printed field, and it stride-samples. Recomputing their key on this corpus is the
    # only way to say which of the three carries the difference.
    inh_ids = [MFS.MF.identity_of(e) for e in compact
               if len(MFS.MF.identity_of(e)) >= 2 and not MFS.is_blanked(e)]
    inh_counts = collections.Counter(_norm(q).casefold() for q in inh_ids)
    row["inherited_pop"] = len(inh_ids)
    row["inherited_shared"] = sum(1 for q in inh_ids
                                  if inh_counts[_norm(q).casefold()] > 1)

    act = [r for r in recs if r["act"]]
    fact = [r for r in frecs if r["act"]]
    row.update({"stage": label, "entries": len(compact), "printed": len(recs),
                "actionable": len(act), "listing_chars": len(listing), **meta,
                "all": ladder(recs), "actionable_ladder": ladder(act),
                "flat_ladder": ladder(fact)})

    # The residual, classified. Probed on the ACTIONABLE rows: a crowd of media rows or
    # containers is not a choice anyone has to make.
    groups = contested_groups(act)
    row["contested_groups"] = len(groups)
    row["contested_rows"] = sum(len(v) for v in groups.values())
    # WHICH SURFACE the contested rows live on, over EVERY contested group rather than
    # the sampled ones -- the verdict sample is capped and this is not.
    bysurf = collections.Counter()
    for v in groups.values():
        k = ("overflow" if v[0]["tag"] == "<overflow>"
             else "fold" if v[0]["tag"] == "<fold>" else "row")
        bysurf[k] += len(v)
    row["contested_by_surface"] = dict(bysurf)
    allsurf = collections.Counter()
    for r in act:
        allsurf["overflow" if r["tag"] == "<overflow>"
                else "fold" if r["tag"] == "<fold>" else "row"] += 1
    row["rows_by_surface"] = dict(allsurf)
    picked = MFS._stride(sorted(groups.values(), key=lambda v: -len(v)), MAX_GROUPS_PROBED)
    want = []
    for g in picked:
        want += [m["mmid"] for m in g[:MAX_MEMBERS_PROBED]]
    attrs, nest = {}, []
    if want:
        try:
            got = await page.evaluate(MS.ATTR_PROBE, want)
            attrs = {m: a for m, a in zip(want, got) if a is not None}
        except Exception as ex:
            row["attr_error"] = str(ex)[:120]
        try:
            nest = await page.evaluate(
                NEST_PROBE, [[m["mmid"] for m in g[:MAX_MEMBERS_PROBED]] for g in picked])
        except Exception as ex:
            row["nest_error"] = str(ex)[:120]
    verdicts, verdict_rows = collections.Counter(), collections.Counter()
    listing_norm = _norm(listing).casefold()
    for gi, g in enumerate(picked):
        ms = g[:MAX_MEMBERS_PROBED]
        v, why = classify(ms, attrs, listing_norm,
                          nested=bool(nest[gi]) if gi < len(nest) else False)
        verdicts[v] += 1
        verdict_rows[v] += len(g)
        if len(groups_sink) < 400:
            groups_sink.append({"site": site, "stage": label, "verdict": v,
                                "size": len(g), "why": why.get("why", ""),
                                "fields": why.get("fields", []),
                                "ident": ms[0]["ident"][:80], "tag": ms[0]["tag"],
                                "surface": ("overflow" if ms[0]["tag"] == "<overflow>"
                                            else "fold" if ms[0]["tag"] == "<fold>"
                                            else "row"),
                                "refs": [m["mmid"] for m in ms[:6]]})
    row["verdicts"] = dict(verdicts)
    row["verdict_rows"] = dict(verdict_rows)
    row["groups_probed"] = len(picked)
    return row


# ======================================================================================
# THE COST HALF. #41 and #44 both record a change being recommended on a cost measured
# without its benefit, and #44 then measured the benefit and refused the change: 70% of
# the spend landed on tasks that gained nothing. `href` is the one rung here that is
# shipped-but-opt-in, so if anything is to be recommended it is `detail="brief"`, and
# that needs BOTH halves. Both arms come off the SAME page load so run-order drift
# cannot align with an arm (R3).
# ======================================================================================
_COST_JS = ("(function(){ " + MFS.MF.COLLECT + ";"
            " const lc = _collectInteractivePage(false, null, 'compact', false, false, 'tree');"
            " const lb = _collectInteractivePage(false, null, 'brief',   false, false, 'tree');"
            " const sc = _collectInteractivePage(true,  null, 'compact', false, false, 'tree');"
            " const sb = _collectInteractivePage(true,  null, 'brief',   false, false, 'tree');"
            " return { lc: String(lc), lb: String(lb), sc: sc, sb: sb }; })()")


def cost_row(name, res):
    sc, sb = _ents(res["sc"]), _ents(res["sb"])
    bmap = {str(e.get("mmid")): e for e in sb}
    rc, _ = build_recs(sc, {}, res["lc"], [])
    rb, _ = build_recs(sb, bmap, res["lb"], [])
    rc = [r for r in rc if r["act"]]
    rb = [r for r in rb if r["act"]]
    if len(rc) < 10 or len(rb) < 10:
        return None
    uc, _ = _uniq_and_ties(rc, FULL_FIELDS)
    # The brief arm's key INCLUDES href, because in that arm the listing prints it.
    ub, _ = _uniq_and_ties(rb, FULL_FIELDS + ("href",))
    return {"site": name, "rows_c": len(rc), "rows_b": len(rb),
            "uniq_c": uc, "uniq_b": ub,
            "rate_c": round(uc / len(rc), 4), "rate_b": round(ub / len(rb), 4),
            "chars_c": len(res["lc"]), "chars_b": len(res["lb"]),
            "cost": round(len(res["lb"]) / max(1, len(res["lc"])), 4)}


def frozen_sites(n):
    """`SITES` rows are `(name, url)` OR `(name, url, settle_ms)`. ONE spelling of that
    unpack, because I wrote it twice and both copies raised `ValueError: too many values
    to unpack` at index 59 -- the second one while I was fixing the first. PRINCIPLES 17,
    and the same failure `RECORD-ATOMS-RECONCILIATION` records killing all four existing
    descriptor probes at the same site of the same corpus."""
    from capture_listings import SITES
    items = sorted(SITES.items()) if isinstance(SITES, dict) else list(SITES)
    out = []
    for it in items[:n]:
        out.append((it[0], it[1], it[2] if len(it) > 2 else 1200))
    return out


async def run_cost(n):
    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for i, (name, url, settle) in enumerate(frozen_sites(n), 1):
            har = FROZEN / f"{name}.har"
            if not har.exists():
                continue
            ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True)
            try:
                await ctx.add_init_script(path=ASG.TAG_JS)
                await ctx.route_from_har(str(har), not_found="abort")
                page = await ctx.new_page()
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                except Exception:
                    continue
                await page.wait_for_timeout(settle)
                r = cost_row(name, await page.evaluate(_COST_JS))
                if r:
                    rows.append(r)
                    print(f"  [{i:>3}] {name:<22} rows {r['rows_c']:<5} "
                          f"uniq {r['rate_c']:.3f} -> {r['rate_b']:.3f}   "
                          f"chars x{r['cost']:.2f}")
            except Exception as e:
                print(f"  [{i:>3}] {name:<22} ERROR {str(e)[:50]}")
            finally:
                try:
                    await ctx.close()
                except Exception:
                    pass
        await browser.close()
    if not rows:
        print("no sites measured")
        return 1
    gains = [r["rate_b"] - r["rate_c"] for r in rows]
    costs = [r["cost"] for r in rows]
    tot_c = sum(r["rows_c"] for r in rows)
    tot_uc = sum(r["uniq_c"] for r in rows)
    tot_b = sum(r["rows_b"] for r in rows)
    tot_ub = sum(r["uniq_b"] for r in rows)
    helped = sum(1 for g in gains if g > 0.001)
    print(f"\n{'=' * 78}\nCOST AND BENEFIT OF detail=\"brief\" — {len(rows)} frozen sites"
          f"\n{'=' * 78}")
    print(f"  discrimination  pooled {tot_uc}/{tot_c} = {tot_uc/tot_c:.1%}"
          f"  ->  {tot_ub}/{tot_b} = {tot_ub/tot_b:.1%}")
    print(f"  per-site gain   median {statistics.median(gains):+.2%}   "
          f"mean {statistics.fmean(gains):+.2%}   max {max(gains):+.2%}")
    print(f"  listing chars   median x{statistics.median(costs):.2f}   "
          f"mean x{statistics.fmean(costs):.2f}   worst x{max(costs):.2f}")
    print(f"  sites that GAIN anything: {helped}/{len(rows)}; "
          f"sites that pay >10% more chars: {sum(1 for c in costs if c > 1.1)}/{len(rows)}")
    waste = sum(1 for r in rows if r["cost"] > 1.05 and r["rate_b"] - r["rate_c"] <= 0.001)
    print(f"  sites that PAY >5% and GAIN nothing: {waste}/{len(rows)}   "
          f"<- #44's ratio, the number that killed the last change like this")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cost.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT / 'cost.json'}")
    return 0


# ======================================================================================
# LIVE STAGED RUN -- #89's driver, verbatim.
# ======================================================================================
async def one(browser, name, url, arch, lang, nstages):
    t0 = time.time()
    ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True,
                                    user_agent=None, locale="en-US")
    base = {"site": name, "url": url, "archetype": arch, "lang": lang}
    try:
        await ctx.add_init_script(path=ASG.TAG_JS)
        page = await ctx.new_page()
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=ASG.GOTO_MS)
            status = resp.status if resp else None
        except Exception as e:
            return dict(base, error="goto: " + str(e)[:120])
        try:
            await page.wait_for_load_state("networkidle", timeout=7000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)

        fails, groups, stages = [], [], []

        async def go(label):
            res = await page.evaluate(_collect_js())
            return await measure_stage(page, label, res, name, fails, groups)

        try:
            stages.append(await go("s0"))
        except Exception as e:
            return dict(base, error="evaluate: " + str(e)[:160], status=status)
        out = dict(base, status=status, stages=stages, decomp_fails=fails[:40],
                   groups=groups)

        used, picks, attempts = collections.Counter(), [], 0
        while len(stages) <= nstages and attempts < nstages + 3:
            attempts += 1
            i = len(stages)
            step = {"n": i, "attempt": attempts}
            try:
                pick = await page.evaluate(
                    "(" + ASG.STAGE_PICK.strip() + ")(" + json.dumps(
                        {"usedKinds": dict(used), "maxPerKind": ASG.MAX_PER_KIND}) + ")")
            except Exception as e:
                step["error"] = "pick: " + str(e)[:120]
                picks.append(step)
                break
            if not pick:
                step["none_left"] = True
                picks.append(step)
                break
            step.update({k: pick[k] for k in ("kind", "tag", "nested", "name") if k in pick})
            before = page.url
            try:
                step["mechanism"] = await ASG._act(page, pick)
            except Exception as e:
                step["act_error"] = str(e).split("\n")[0][:110]
            await page.wait_for_timeout(ASG.SETTLE_MS)
            if page.url.split("#")[0] != before.split("#")[0]:
                step["navigated"] = True
                picks.append(step)
                break
            try:
                v = await page.evaluate(ASG.STAGE_VERIFY)
            except Exception as e:
                step["error"] = "verify: " + str(e)[:120]
                picks.append(step)
                break
            used[pick["kind"]] += 1
            step["flipped"] = bool(v.get("flipped"))
            if not step["flipped"]:
                picks.append(step)
                continue
            try:
                r = await go("s%d" % i)
            except Exception as e:
                step["error"] = "measure: " + str(e)[:120]
                picks.append(step)
                break
            r["kind"] = pick["kind"]
            stages.append(r)
            picks.append(step)
        out["picks"] = picks
        out["seconds"] = round(time.time() - t0, 1)
        return out
    finally:
        try:
            await ctx.close()
        except Exception:
            pass


def usable(r):
    """ASG's bar, applied to this probe: a read with under 10 printed rows cannot say
    anything about whether rows can be told apart."""
    return ("error" not in r and r.get("stages")
            and r["stages"][0]["printed"] >= 10)


# ======================================================================================
# FROZEN CORPUS -- first paint only, no interactions. A cheap deterministic cross-check
# on real styled pages; NOT the headline, because it is the corpus development tuned on
# (PRINCIPLES 9) and it has no stages.
# ======================================================================================
async def one_frozen(browser, name, url, settle=1200):
    har = FROZEN / f"{name}.har"
    if not har.exists():
        return {"site": name, "url": url, "error": "no har"}
    ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True)
    try:
        await ctx.add_init_script(path=ASG.TAG_JS)
        await ctx.route_from_har(str(har), not_found="abort")
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:
            return {"site": name, "url": url, "error": "goto: " + str(e)[:90]}
        await page.wait_for_timeout(settle)
        fails, groups = [], []
        res = await page.evaluate(_collect_js())
        st = await measure_stage(page, "s0", res, name, fails, groups)
        return {"site": name, "url": url, "lang": "en", "archetype": "frozen",
                "stages": [st], "decomp_fails": fails[:40], "groups": groups}
    finally:
        try:
            await ctx.close()
        except Exception:
            pass


# ======================================================================================
# AGGREGATION
# ======================================================================================
def _merge(recs_counters, key):
    return sum(c.get(key, 0) for c in recs_counters)


def aggregate(rs):
    ok = [r for r in rs if usable(r)]
    per_stage = collections.defaultdict(lambda: collections.defaultdict(int))
    cum = collections.defaultdict(lambda: collections.defaultdict(int))
    loo = collections.defaultdict(lambda: collections.defaultdict(int))
    optin = collections.defaultdict(lambda: collections.defaultdict(int))
    flat = collections.defaultdict(int)
    ctrl = collections.defaultdict(int)
    verdicts = collections.Counter()
    verdict_rows = collections.Counter()
    surf_cont, surf_all = collections.Counter(), collections.Counter()
    tot = collections.Counter()
    per_site_rate = []
    ties_all = []
    tie_hist = collections.Counter()
    for r in ok:
        site_rows = site_uniq = 0
        for st in r["stages"]:
            L = st.get("actionable_ladder") or st.get("all")
            if not L:
                continue
            s = st["stage"]
            per_stage[s]["rows"] += L["rows"]
            per_stage[s]["reads"] += 1
            per_stage[s]["contested"] += L["cum"][-1]["contested"]
            per_stage[s]["uniq"] += L["cum"][-1]["uniq"]
            for c in L["cum"]:
                cum[c["rung"]]["uniq"] += c["uniq"]
                cum[c["rung"]]["n"] += c["n"]
                if c["tie_med"]:
                    ties_all.append((c["rung"], c["tie_med"], c["tie_max"]))
                if c["rung"] == LEVELS[-1][0]:
                    for sz, k in (c.get("tie_hist") or {}).items():
                        tie_hist[int(sz)] += k
            for c in L["loo"]:
                loo[c["field"]]["without"] += c["without"]
                loo[c["field"]]["with"] += c["with"]
                loo[c["field"]]["n"] += L["rows"]
            for c in L["optin"]:
                optin[c["rung"]]["uniq"] += c["uniq"]
                optin[c["rung"]]["n"] += c["n"]
            ctrl["uniq"] += L["control_ref"]["uniq"]
            ctrl["n"] += L["control_ref"]["n"]
            F = st.get("flat_ladder")
            if F:
                flat["uniq"] += F["cum"][-1]["uniq"]
                flat["n"] += F["rows"]
            site_rows += L["rows"]
            site_uniq += L["cum"][-1]["uniq"]
            for k in ("entries", "printed", "actionable", "blanked", "decomp_fail",
                      "listing_rows", "contested_groups", "contested_rows",
                      "groups_probed", "collapsed_refs", "ident_rolled",
                      "inherited_pop", "inherited_shared"):
                tot[k] += st.get(k, 0)
            tot["reads"] += 1
            surf_cont.update(st.get("contested_by_surface") or {})
            surf_all.update(st.get("rows_by_surface") or {})
            verdicts.update(st.get("verdicts") or {})
            verdict_rows.update(st.get("verdict_rows") or {})
        if site_rows:
            per_site_rate.append(site_uniq / site_rows)
    return {"sites_ok": len(ok), "sites_total": len(rs),
            "unusable": [{"site": r["site"], "why": r.get("error", "too few rows")}
                         for r in rs if not usable(r)],
            "totals": dict(tot), "per_stage": {k: dict(v) for k, v in per_stage.items()},
            "cum": {k: dict(v) for k, v in cum.items()},
            "loo": {k: dict(v) for k, v in loo.items()},
            "optin": {k: dict(v) for k, v in optin.items()},
            "flat": dict(flat), "control_ref": dict(ctrl),
            "verdicts": dict(verdicts), "verdict_rows": dict(verdict_rows),
            "surface_contested": dict(surf_cont), "surface_rows": dict(surf_all),
            "tie_hist_at_full": dict(sorted(tie_hist.items())),
            "per_site_median": round(statistics.median(per_site_rate), 4) if per_site_rate else None,
            "per_site_worst": round(min(per_site_rate), 4) if per_site_rate else None,
            "tie_med_at_full": round(statistics.median(
                [t for rung, t, _ in ties_all if rung == LEVELS[-1][0]]), 2)
            if any(rung == LEVELS[-1][0] for rung, _, _ in ties_all) else None}


def report(agg, rs=None):
    L = []
    t = agg["totals"]
    L.append("=" * 86)
    L.append("DISCRIMINATION — can a reader tell two printed rows apart?")
    L.append("=" * 86)
    L.append(f"sites usable {agg['sites_ok']}/{agg['sites_total']}   reads {t.get('reads',0)}"
             f"   entries {t.get('entries',0)}   PRINTED rows {t.get('printed',0)}"
             f"   actionable {t.get('actionable',0)}")
    L.append(f"blanked rows (identity removed by #74's rule) {t.get('blanked',0)}"
             f"   refs sharing a row with another (#29 collapse) {t.get('collapsed_refs',0)}"
             f"   decomposition failures {t.get('decomp_fail',0)}"
             f"   rows whose label the tree ROLLED UP {t.get('ident_rolled',0)}")
    if t.get("inherited_pop"):
        L.append(f"#117's definition recomputed on this corpus: "
                 f"{t['inherited_shared']}/{t['inherited_pop']} = "
                 f"{t['inherited_shared']/t['inherited_pop']:.1%} of WHOLE-PAGE entries "
                 f"share an identity_of (it reports 52% of its stride-sampled probes)")
    L.append("")
    L.append("THE LADDER — cumulative, over PRINTED fields, actionable rows")
    L.append(f"  {'rung':<34}{'unique':>10}{'contested':>12}{'rate':>9}")
    order = [lbl for lbl, _ in LEVELS]
    for rung in order:
        c = agg["cum"].get(rung)
        if not c or not c["n"]:
            continue
        L.append(f"  {rung:<34}{c['uniq']:>10}{c['n']-c['uniq']:>12}"
                 f"{c['uniq']/c['n']:>9.1%}")
    L.append("")
    L.append("LEAVE-ONE-OUT at the full default rung (order-independent)")
    for f, c in sorted(agg["loo"].items(), key=lambda kv: -(kv[1]["with"] - kv[1]["without"])):
        if not c["n"]:
            continue
        L.append(f"  drop {f:<28}{c['without']:>10} vs {c['with']:<10}"
                 f" marginal {(c['with']-c['without'])/c['n']:>7.2%}")
    L.append("")
    L.append("OPT-IN rungs — NOT in the shipped default, reported apart")
    for rung, c in agg["optin"].items():
        if not c["n"]:
            continue
        L.append(f"  {rung:<34}{c['uniq']:>10}{'':>12}{c['uniq']/c['n']:>9.1%}")
    if agg["flat"].get("n"):
        f = agg["flat"]
        L.append(f"  {'format=flat (section=)':<34}{f['uniq']:>10}{'':>12}{f['uniq']/f['n']:>9.1%}")
    c = agg.get("control_ref") or {}
    if c.get("n"):
        L.append(f"  {'CONTROL +ref_N (falsifier)':<34}{c['uniq']:>10}{'':>12}"
                 f"{c['uniq']/c['n']:>9.1%}   <- must be 100%")
    L.append("")
    L.append("BY STAGE (actionable rows)")
    L.append(f"  {'stage':<8}{'reads':>7}{'rows':>9}{'unique':>9}{'contested':>11}{'rate':>9}")
    for s in sorted(agg["per_stage"]):
        v = agg["per_stage"][s]
        L.append(f"  {s:<8}{v['reads']:>7}{v['rows']:>9}{v['uniq']:>9}"
                 f"{v['contested']:>11}{v['uniq']/max(1,v['rows']):>9.1%}")
    L.append("")
    L.append(f"per-site median {agg['per_site_median']}   worst {agg['per_site_worst']}"
             f"   median tie size at the full rung {agg['tie_med_at_full']}")
    th = agg.get("tie_hist_at_full") or {}
    if th:
        tot_r = sum(k * v for k, v in ((int(a), b) for a, b in th.items())) or 1
        small = sum(b for a, b in th.items() if int(a) <= 3)
        L.append("  tie sizes at the full rung: "
                 + "  ".join(f"{a}x{b}" for a, b in list(th.items())[:10])
                 + (" …" if len(th) > 10 else "")
                 + f"   (crowds of <=3: {small} of {sum(th.values())} rows-in-ties)")
    sa, sc = agg.get("surface_rows") or {}, agg.get("surface_contested") or {}
    if sa:
        L.append("")
        L.append("BY SURFACE — where in the listing a contested row lives")
        L.append(f"  {'surface':<12}{'rows':>9}{'contested':>11}{'rate':>9}")
        for k in ("row", "fold", "overflow"):
            if sa.get(k):
                L.append(f"  {k:<12}{sa[k]:>9}{sc.get(k,0):>11}"
                         f"{sc.get(k,0)/sa[k]:>9.1%}")
    L.append("")
    L.append("THE RESIDUAL — contested crowds classified (groups, not rows)")
    tv = sum(agg["verdicts"].values()) or 1
    tr = sum(agg.get("verdict_rows", {}).values()) or 1
    L.append(f"  {'':<18}{'groups':>7}{'':>9}{'rows':>8}")
    for k in ("interchangeable", "page", "ours-optin", "ours-elsewhere",
              "ours-absent", "ours-devkey", "unresolved"):
        n = agg["verdicts"].get(k, 0)
        r = agg.get("verdict_rows", {}).get(k, 0)
        L.append(f"  {k:<18}{n:>7}{n/tv:>9.1%}{r:>8}{r/tr:>9.1%}")
    L.append(f"  (probed {t.get('groups_probed',0)} of {t.get('contested_groups',0)} "
             f"contested groups covering {t.get('contested_rows',0)} rows)")
    return "\n".join(L)


# ======================================================================================
# FIRING PROOFS. PRINCIPLES 5 / 15: a ladder that reports everything unique because of a
# bug looks exactly like a system with no problem, so the probe must be SEEN to report a
# collision before any number is believed.
# ======================================================================================
# THE FIRST VERSION OF THIS FIXTURE WAS THE CANONICAL AMBIGUOUS SHAPE AND THE LISTING
# SOLVES IT. Four `Remove` buttons in an invoice table came back 4/4 UNIQUE, because the
# collector prints `near="INV-1001 Remove"` on each row -- #37's `near=` doing exactly
# its job. The fixture encoded my belief that a table of identical buttons is ambiguous
# (PRINCIPLES 11), and only running it said otherwise. It is KEPT, as the control that
# the ladder credits `near=` where `near=` is what separates the rows -- which is a more
# useful check than the one I meant to write.
FIXTURE_NEAR_SAVES = """
<main><h1>Invoices</h1>
<table><tbody>
 <tr><td>INV-1001</td><td><button type=button>Remove</button></td></tr>
 <tr><td>INV-1002</td><td><button type=button>Remove</button></td></tr>
 <tr><td>INV-1003</td><td><button type=button>Remove</button></td></tr>
 <tr><td>INV-1004</td><td><button type=button>Remove</button></td></tr>
</tbody></table></main>
"""
# GENUINELY INDISTINGUISHABLE: same name, same ancestry, no neighbouring text to become
# a `near=`, nothing declared that differs. #23's "13 identical 구독 buttons belonging to
# 13 different outlets" with the discriminator removed.
FIXTURE_COLLIDING = """
<main><ul>
 <li><button type=button>Star</button></li>
 <li><button type=button>Star</button></li>
 <li><button type=button>Star</button></li>
 <li><button type=button>Star</button></li>
 <li><button type=button>Star</button></li>
 <li><button type=button>Star</button></li>
</ul></main>
"""
# CONTESTED, AND THE DOCUMENT DOES SAY WHICH IS WHICH -- it is on `title`, which the
# listing does not print once a name is present. The verdict must be OURS.
FIXTURE_OURS = """
<main><ul>
 <li><button type=button title="Star facebook/react">Star</button></li>
 <li><button type=button title="Star vuejs/core">Star</button></li>
 <li><button type=button title="Star sveltejs/svelte">Star</button></li>
 <li><button type=button title="Star angular/angular">Star</button></li>
</ul></main>
"""
FIXTURE_DISTINCT = """
<main><h1>Settings</h1>
<button type=button>Save profile</button>
<button type=button>Delete account</button>
<button type=button>Export data</button>
<button type=button>Invite teammate</button>
</main>
"""
# THE SAME PARENT, DELIBERATELY. The first version put the two links in `<header>` and
# `<footer>` and produced NO contested group at all -- the ancestry rung separates them,
# which is the tree working. To exercise the INTERCHANGEABLE branch the crowd has to
# survive every printed field first, so the duplicates sit in one container.
FIXTURE_SAME_HREF = """
<main><div>
 <a href="/pricing">Pricing</a>
 <a href="/pricing">Pricing</a>
</div></main>
"""


async def _fixture(browser, html):
    ctx = await browser.new_context(viewport=VIEWPORT)
    await ctx.add_init_script(path=ASG.TAG_JS)
    page = await ctx.new_page()
    # add_init_script only affects documents created AFTER it, and set_content reuses the
    # existing about:blank -- C14's tripwire, and the reason for the goto (#31).
    await page.goto("about:blank")
    await page.set_content("<!doctype html><meta charset=utf-8><body>" + html)
    await page.wait_for_timeout(250)
    return ctx, page


async def selftest():
    fails, notes = [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # 1. A real collision MUST be reported. If this reads unique the ladder is broken
        #    in the direction that makes the system look perfect.
        ctx, page = await _fixture(browser, FIXTURE_COLLIDING)
        res = await page.evaluate(_collect_js())
        st = await measure_stage(page, "s0", res, "fixture-colliding", [], [])
        L = st["actionable_ladder"]
        final = L["cum"][-1]
        notes.append({"check": "colliding fixture", "rows": L["rows"],
                      "contested_at_full": final["contested"],
                      "rate": final["rate"], "verdicts": st["verdicts"]})
        if final["contested"] < 6:
            fails.append("six identical Star buttons were not reported contested "
                         f"(contested={final['contested']} of {L['rows']})")
        if st["verdicts"].get("page", 0) < 1:
            fails.append("a crowd the DOM declares nothing about was not classified "
                         f"'page': {st['verdicts']}")
        await ctx.close()

        # 1b. THE NEAR CONTROL, and it is the check the first version of 1 accidentally
        #     was. The same shape WITH neighbouring text must come back separated, or a
        #     ladder that reports everything contested would satisfy 1 and mean nothing.
        ctx, page = await _fixture(browser, FIXTURE_NEAR_SAVES)
        res = await page.evaluate(_collect_js())
        stn = await measure_stage(page, "s0", res, "fixture-near", [], [])
        Ln = stn["actionable_ladder"]
        notes.append({"check": "near= resolves the invoice table (CONTROL)",
                      "rows": Ln["rows"],
                      "identity_only": Ln["cum"][1]["uniq"],
                      "with_near": Ln["cum"][3]["uniq"],
                      "contested_at_full": Ln["cum"][-1]["contested"]})
        if Ln["cum"][1]["uniq"] != 0:
            fails.append("the invoice buttons were separated BEFORE near= was added, so "
                         "this fixture does not test what it claims to")
        if Ln["cum"][-1]["contested"] != 0:
            fails.append("near= did not separate four rows it plainly prints an invoice "
                         f"number on: {Ln['cum']}")
        await ctx.close()

        # 1c. OURS must be reachable, or every collision would read as the page's fault
        #     and the recommendation would be "nothing to do" by construction.
        ctx, page = await _fixture(browser, FIXTURE_OURS)
        res = await page.evaluate(_collect_js())
        sto = await measure_stage(page, "s0", res, "fixture-ours", [], [])
        notes.append({"check": "declared-but-unprinted title", "verdicts": sto["verdicts"],
                      "contested": sto["actionable_ladder"]["cum"][-1]["contested"]})
        if sto["verdicts"].get("ours-absent", 0) < 1:
            fails.append("a crowd the page separates with `title` was not classified "
                         f"'ours': {sto['verdicts']}")
        await ctx.close()

        # 2. THE CONTROL. Distinct names must NOT be reported contested, or "report
        #    everything contested" would satisfy check 1 while measuring nothing.
        ctx, page = await _fixture(browser, FIXTURE_DISTINCT)
        res = await page.evaluate(_collect_js())
        st2 = await measure_stage(page, "s0", res, "fixture-distinct", [], [])
        L2 = st2["actionable_ladder"]
        notes.append({"check": "distinct fixture (CONTROL)", "rows": L2["rows"],
                      "contested_at_full": L2["cum"][-1]["contested"],
                      "identity_rate": L2["cum"][1]["rate"]})
        if L2["cum"][1]["rate"] < 1.0:
            fails.append("four distinctly-named buttons were not separated by identity "
                         f"alone: {L2['cum'][1]}")
        await ctx.close()

        # 3. THE REF FALSIFIER. Adding ref_N to the key must make everything unique. This
        #    is what proves the reported rungs are NOT counting the ref -- the single
        #    way this measurement could read ~100% for a reason that means nothing.
        ctx, page = await _fixture(browser, FIXTURE_COLLIDING)
        res = await page.evaluate(_collect_js())
        compact = _ents(res["compact"])
        idx = MFS.listing_index(res["listing"])
        recs = []
        for e in compact:
            mm = str(e.get("mmid"))
            if mm not in idx or not D._targetable(e):
                continue
            d = fold_member(mm, idx[mm]) or decompose(e, idx[mm])
            if d:
                recs.append({"mmid": mm, "ref": mm, "anc": "", "href": "", "box": "", **d})
        u_ref, _ = _uniq_and_ties(recs, FULL_FIELDS + ("ref",))
        u_noref, _ = _uniq_and_ties(recs, FULL_FIELDS)
        notes.append({"check": "ref falsifier", "with_ref": u_ref, "without_ref": u_noref,
                      "rows": len(recs)})
        if u_ref != len(recs):
            fails.append("the ref falsifier did not make every row unique — the control "
                         "cannot discriminate, so it proves nothing")
        if u_noref >= len(recs):
            fails.append("the reported key is already unique on four identical buttons: "
                         "it is counting the ref or something equivalent to it")

        # 4. INTERCHANGEABLE must be reachable, or every collision would read as a defect.
        ctx2, page2 = await _fixture(browser, FIXTURE_SAME_HREF)
        res2 = await page2.evaluate(_collect_js())
        st4 = await measure_stage(page2, "s0", res2, "fixture-same-href", [], [])
        notes.append({"check": "same-href fixture", "verdicts": st4["verdicts"]})
        if st4["verdicts"].get("interchangeable", 0) < 1:
            fails.append("two links to the same destination were not classified "
                         f"interchangeable: {st4['verdicts']}")
        await ctx2.close()
        await ctx.close()

        # 5. The decomposition tripwire must be CLEAN on a real page, or every number
        #    above is attributed to the wrong rung.
        ctx, page = await _fixture(browser, FIXTURE_COLLIDING + FIXTURE_DISTINCT)
        res = await page.evaluate(_collect_js())
        sink = []
        idx2 = MFS.listing_index(res["listing"])
        for e in _ents(res["compact"]):
            mm = str(e.get("mmid"))
            if mm in idx2 and not fold_member(mm, idx2[mm]):
                decompose(e, idx2[mm], sink)
        notes.append({"check": "decomposition", "failures": len(sink),
                      "sample": sink[:3]})
        if sink:
            fails.append(f"decomposition failed on {len(sink)} fixture rows: {sink[:2]}")
        await ctx.close()
        await browser.close()
    print(json.dumps({"failures": fails, "notes": notes}, indent=2, ensure_ascii=False))
    print("SELFTEST", "FAIL" if fails else "PASS")
    return 1 if fails else 0


async def fire(sites, nstages, k=8):
    """LIVE firing proof. On a real page at the deepest stage reached, REWRITE k controls'
    accessible names to one shared string and re-measure: the contested count must rise by
    about k. A fixture is what you thought of (PRINCIPLES 11); this is not."""
    rows = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for name, url, arch, lang in sites:
            ctx = await browser.new_context(viewport=VIEWPORT, ignore_https_errors=True)
            try:
                await ctx.add_init_script(path=ASG.TAG_JS)
                page = await ctx.new_page()
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=ASG.GOTO_MS)
                except Exception as e:
                    rows.append({"site": name, "error": str(e)[:90]})
                    continue
                await page.wait_for_timeout(2500)
                res = await page.evaluate(_collect_js())
                clean = await measure_stage(page, "s0", res, name, [], [])
                if not clean.get("actionable_ladder"):
                    # UNMEASURED, never a pass: a page with no actionable rows cannot
                    # demonstrate that the probe fires, and counting it as if it had
                    # would be a clean number over an empty denominator.
                    rows.append({"site": name, "error": "no actionable rows"})
                    print(f"  {name:<22} UNMEASURED (no actionable rows)")
                    continue
                # AT THE RUNG THE PLANT ACTS ON. Scoring the FULL rung marked two sites
                # as "did not fire" that were the ladder working correctly: the plant
                # collides the IDENTITY, and `near=` or a state token may then
                # legitimately separate the rows again. Testing the full rung asks
                # whether the page has any other discriminator, which is a different
                # question from whether this probe can see a collision.
                before = clean["actionable_ladder"]["cum"][1]["contested"]
                before_full = clean["actionable_ladder"]["cum"][-1]["contested"]
                clean_recs = [r for r in build_recs(
                    _ents(res["compact"]), {}, res["listing"], [])[0] if r["act"]]
                # THE PLANT HAS TO MAKE SIBLINGS COLLIDE. The first version spread it
                # across the whole document and fired on 0 of 9 sites -- correctly, and
                # that is the point: elements in different parts of the page are already
                # separated by the ANCESTRY rung, so overwriting their names collides
                # nothing. A plant that does not reach the code under test proves
                # nothing (PRINCIPLES 11), so this takes the largest run of VISIBLE
                # siblings and gives them one name.
                # THE PLANT HAS TO REACH ROWS THAT ARE ACTUALLY PRINTED, AND HAS TO MAKE
                # SIBLINGS COLLIDE. Two earlier versions fired on 0 and 1 of 10 sites:
                # the first spread the plant across the document, where the ANCESTRY rung
                # already separates the targets so nothing collides; the second chose
                # siblings off any `[mmid]`, most of which are not printed rows at all
                # (the listing is viewport-scoped and capped). Both were plants that
                # never reached the code under test, which is PRINCIPLES 11 one level up
                # -- and a firing proof that does not fire looks exactly like a probe
                # with nothing to find. This plants on the mmids THIS RUN just measured
                # as printed and actionable.
                printed = [r["mmid"] for r in clean_recs]
                planted = await page.evaluate(
                    """([ids, k]) => {
                       const by = new Map();
                       for (const m of ids) {
                         const e = document.querySelector(`[mmid="${m}"]`);
                         if (!e || !e.parentElement) continue;
                         const p = e.parentElement;
                         if (!by.has(p)) by.set(p, []);
                         by.get(p).push(e);
                       }
                       let best = [];
                       for (const v of by.values()) if (v.length > best.length) best = v;
                       const take = best.slice(0, k);
                       for (const e of take) e.setAttribute('aria-label', 'ZZPLANTCOLLIDEZZ');
                       return take.length; }""", [printed, k])
                res2 = await page.evaluate(_collect_js())
                dirty = await measure_stage(page, "s0", res2, name, [], [])
                after = dirty["actionable_ladder"]["cum"][1]["contested"]
                after_full = dirty["actionable_ladder"]["cum"][-1]["contested"]
                # THE PLANTED GROUP ITSELF, which is the only churn-proof question.
                # Differencing a whole-page contested COUNT scored three live sites as
                # "did not fire" because the page re-rendered between the two reads
                # (gov_au's identity-rung count went 22 -> 16 while the plant landed).
                # A difference of two numbers taken seconds apart on the live web is a
                # measurement of the web; asking whether the rows we planted are
                # reported as one contested crowd is a measurement of the probe.
                drecs = [r for r in build_recs(
                    _ents(res2["compact"]), {}, res2["listing"], [])[0] if r["act"]]
                mine = [r for r in drecs if "ZZPLANTCOLLIDEZZ" in r["ident"]]
                ident_groups = contested_groups(drecs, ("tag", "role", "ident"))
                caught = max((len(v) for k, v in ident_groups.items()
                              if "ZZPLANTCOLLIDEZZ" in (k[2] or "")), default=0)
                # DID THE PLANT REACH THE OUTPUT? Two things that are not a failure of
                # this probe look identical to one if they are not separated: a page
                # offering fewer than two printed siblings to collide (bank_bbl_th gave
                # ONE), and a plant the collector did not print (a row whose identity
                # comes from somewhere aria-label does not override). Both are
                # UNMEASURED and NAMED, never counted as a pass either.
                landed = "ZZPLANTCOLLIDEZZ" in res2["listing"]
                if planted < 2 or not landed:
                    rows.append({"site": name, "planted": planted, "landed": landed,
                                 "unmeasured": "only %d printed sibling(s)" % planted
                                 if planted < 2 else "the plant never reached the listing"})
                    print(f"  {name:<22} UNMEASURED ({rows[-1]['unmeasured']})")
                    continue
                if len(mine) < 2:
                    rows.append({"site": name, "planted": planted, "printed_plants": len(mine),
                                 "unmeasured": "only %d planted row(s) reached the "
                                               "listing" % len(mine)})
                    print(f"  {name:<22} UNMEASURED ({rows[-1]['unmeasured']})")
                    continue
                rows.append({"site": name, "planted": planted, "printed_plants": len(mine),
                             "caught_as_one_crowd": caught,
                             "ident_before": before, "ident_after": after,
                             "full_before": before_full, "full_after": after_full,
                             "rows": dirty["actionable_ladder"]["rows"],
                             "fired": caught >= 2})
                print(f"  {name:<22} planted={planted} printed={len(mine)}  "
                      f"reported as one contested crowd of {caught}   "
                      f"(full rung {before_full} -> {after_full})  "
                      f"{'FIRED' if rows[-1]['fired'] else 'DID NOT FIRE'}")
            finally:
                try:
                    await ctx.close()
                except Exception:
                    pass
        await browser.close()
    ok = sum(1 for r in rows if r.get("fired"))
    meas = [r for r in rows if "fired" in r]
    un = [r for r in rows if r.get("unmeasured") or r.get("error")]
    print(f"\n--fire: {ok}/{len(meas)} measurable sites fired; "
          f"{len(un)} UNMEASURED ({', '.join(r['site'] for r in un) or '-'})")
    for r in meas:
        if not r.get("fired"):
            print(f"  DID NOT FIRE: {r['site']} planted={r['planted']} "
                  f"printed={r['printed_plants']} caught={r['caught_as_one_crowd']}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "fire.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return 0 if ok and ok == len([r for r in rows if "before" in r]) else 1


# ======================================================================================
async def run_live(sites, conc, nstages):
    sem = asyncio.Semaphore(conc)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        async def go(s):
            async with sem:
                try:
                    return await asyncio.wait_for(one(browser, *s, nstages), 200)
                except Exception as e:
                    return {"site": s[0], "url": s[1], "archetype": s[2], "lang": s[3],
                            "error": "timeout/" + str(e)[:80]}
        out = []
        tasks = [asyncio.create_task(go(s)) for s in sites]
        done = 0
        for t in asyncio.as_completed(tasks):
            r = await t
            done += 1
            out.append(r)
            st = r.get("stages") or []
            L = st[0].get("actionable_ladder") if st else None
            print(f"  [{done:>3}/{len(sites)}] {r['site']:<22} "
                  + (f"ERR {r['error'][:50]}" if "error" in r else
                     f"stages={len(st)} rows={L['rows'] if L else 0} "
                     f"uniq={L['cum'][-1]['rate']:.2f}" if L else "no rows"))
        await browser.close()
    return out


async def run_frozen(n):
    out = []
    sites = frozen_sites(n)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for i, (name, url, settle) in enumerate(sites, 1):
            try:
                r = await one_frozen(browser, name, url, settle)
            except Exception as e:
                r = {"site": name, "url": url, "error": str(e)[:90]}
            out.append(r)
            st = r.get("stages") or []
            L = st[0].get("actionable_ladder") if st else None
            print(f"  [{i:>3}/{len(sites)}] {name:<22} "
                  + (f"ERR {r['error'][:40]}" if "error" in r else
                     f"rows={L['rows'] if L else 0} uniq={L['cum'][-1]['rate']:.2f}"
                     if L else "no rows"))
        await browser.close()
    return out


async def amain():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--fire", action="store_true")
    ap.add_argument("--corpus", default="live", choices=("live", "frozen"))
    ap.add_argument("--pool", default="usable85", choices=("usable85", "all"))
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--conc", type=int, default=6)
    ap.add_argument("--stages", type=int, default=4)
    ap.add_argument("-n", type=int, default=40)
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--out", default=str(OUT / "main"))
    ap.add_argument("--report")
    ap.add_argument("--cost", action="store_true")
    args = ap.parse_args()

    if args.report:
        data = json.loads(Path(args.report).read_text(encoding="utf-8"))
        print(report(data.get("aggregate") or aggregate(data["sites"]), data.get("sites")))
        return 0
    if args.selftest:
        return await selftest()
    if args.cost:
        return await run_cost(args.n)
    if args.fire:
        sites = ASG._pool(args.pool, args.only)[: args.n]
        return await fire(sites, args.stages, args.k)

    if args.corpus == "frozen":
        rs = await run_frozen(args.n)
    else:
        sites = ASG._pool(args.pool, args.only)
        bad = ASG._check_sample(sites)
        if bad:
            print("REFUSED: sample contains excluded hosts:", bad)
            return 1
        print(f"{len(sites)} sites, conc={args.conc}, stages<={args.stages}")
        rs = await run_live(sites, args.conc, args.stages)

    agg = aggregate(rs)
    d = Path(args.out)
    d.mkdir(parents=True, exist_ok=True)
    post = hashlib.sha256(
        (MFS.MF.COLLECT + "\n" + (ROOT / "extension" / "listener_tag.js")
         .read_text(encoding="utf-8")).encode("utf-8")).hexdigest()[:16]
    if post != _SRC_HASH:
        print(f"REFUSED TO WRITE: the collector changed under this run "
              f"({_SRC_HASH} -> {post}); the numbers are not attributable")
        return 1
    out_name = args.out.rstrip("/").split("/")[-1]
    (d / "pass0.json").write_text(
        json.dumps({"sites": rs, "aggregate": agg, "collector": _SRC_HASH,
                    "probe": _PROBE_HASH, "label": out_name},
                   indent=1, ensure_ascii=False),
        encoding="utf-8")
    print(f"collector {_SRC_HASH}   probe {_PROBE_HASH}")
    print()
    print(report(agg, rs))
    print(f"\nwrote {d / 'pass0.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))
