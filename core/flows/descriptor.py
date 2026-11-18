"""Naming a control by what the document DECLARES, so a recorded step survives.

A recorded flow step cannot store a ref. mmids are per-document and additive
(limitation #1, fix #5), so the number means nothing on the next run -- it does
not even mean "not found", it means "some other element". Every other
record-and-replay tool therefore stores a DOM path instead: Midscene an XPath,
Chrome's Recorder a CSS/ARIA/text tuple. A path breaks on exactly the re-render
that fix #5 exists to survive.

This module stores DECLARATIONS instead -- tag, role, accessible name, the
landmark it sits in, the heading above it -- which is possible here and nowhere
else because since #28 the collector already decides existence from declarations
alone, and already computes every one of these fields per entry.

MEASURED, by tools/audit_descriptors.py, over the frozen corpus -- because this
was a design preference until it was a number:

  * descriptors REGENERATE IDENTICALLY across two fresh contexts. That is the
    floor under everything else here.
  * tag+role alone is useless (<1% unique, ties of ~167).
  * +name reaches ~58% unique; +section/heading reaches ~78%.
  * +near buys ~1pp and is NOT used -- #37 measured `near=` frequently
    distinguishing nothing (six column headers carrying one identical row of
    text) and now suppresses it where it does not discriminate.
  * the ~20% that stay ambiguous have a MEDIAN TIE OF 2. Small crowds, not
    chaos -- which is why an ordinal finishes the job instead of a longer
    descriptor.

WHAT IS DELIBERATELY EXCLUDED, each for a reason this log already paid for:

  value           CURRENT CONTENTS (#6), and the flow is about to change it.
                  Identity built on it dissolves at the moment of use.
  state flags     (disabled)/(required)/(unselected)/(checked) are what a step
                  ASSERTS. Identify by them and a step can only find a control
                  already in the state the step exists to produce.
  geometry        #26 made box() opt-in after WorkArena measured coordinates
                  HURTING on dense pages; ours drifts (#23: 110px, #25: 1097px).
  class / framework / font names, pixel sizes
                  #27 and #28 took these out of the path that decides
                  existence. Putting them here puts them back one layer up.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

# WHICH DOCUMENT AN ENTRY LIVES IN, as the extension declares it.
# `collectCrossFrames` prefixes a cross-origin frame's mmid `f<frameId>:` and
# `resolveFrameSelector` routes on that spelling, so it is a declaration rather
# than a guess. Defined HERE, in the leaf module, because `recorder.py` already
# carries a private second copy of this pattern and two spellings of one
# concept is what rule 17 exists to stop -- that import replaces it.
CROSS_FRAME_REF = re.compile(r"^f(\d+):")


def frame_of(entry: dict) -> str:
    """The frame id an entry belongs to; '' for the top document."""
    m = CROSS_FRAME_REF.match(str(entry.get("mmid") or ""))
    return m.group(1) if m else ""

# Cumulative strengths. A recorded step stores the CHEAPEST one that resolves,
# not the strongest: every field added is another thing that can change
# innocently and fail the step. A heading rename should not break a click on a
# button whose name was already unique.
#
# THE LADDER IS MEASURED, not chosen. audit_descriptors.py over 37 frozen sites
# and 12,008 targetable controls:
#
#   tag+role                    0.9% unique   (median tie 92 — a base, not a key)
#   +identity                  59.5%
#   +section/under             84.7%          (median tie falls to 2)
#   +near                      86.1% median ... and +9.6pp on mui_autocomplete
#
# `type` and `placeholder` as their own rung were DELETED: they beat identity
# alone on 3 of 37 sites by at most 0.9pp. `type` survives folded into the base
# because for input/button HTML's enum decides what the control IS (#31/W25),
# and `placeholder` survives as an identity fallback, which is where it was
# actually doing the work -- 8% of controls carry no accessible name at all.
#
# `near` was nearly deleted on its +1.4pp MEDIAN and kept on its distribution:
# it helps 17 of 37 sites and is worth 9.6pp on component-heavy pages. #25's
# rule, arriving on this module: an ablation measures the code against the
# sample, it cannot measure the sample, and a median is an ablation over sites.
LEVELS: tuple[tuple[str, ...], ...] = (
    ("tag", "role", "type"),
    ("tag", "role", "type", "name"),
    ("tag", "role", "type", "name", "section", "under"),
    ("tag", "role", "type", "name", "section", "under", "near"),
)
FULL = len(LEVELS) - 1

# THE ALTERNATE KEY, and it is NOT a rung. #59 recorded the failure it exists
# for: on a real app a nav tab's accessible name is "Records 38", because
# AccName 2F concatenates descendant text and the badge is a descendant. The
# identity rung is therefore DATA-DEPENDENT -- adding a record made it
# "Records 43" and a flow that had passed minutes earlier stopped resolving,
# and a rebind can only ever propose another count-bearing name that breaks
# again at 44. A link's `href` is declared and does not move, so it was the
# obvious fix.
#
# IT IS NOT THE OBVIOUS FIX, and tools/audit_href_rung.py is why. 28 frozen
# sites, 4,069 linked controls of 10,151 targetable:
#
#   coverage (targetable controls declaring an href)   40.1%
#   unique by tag+role+type+href                       62.1% median (worst 28%)
#   unique by tag+role+type+name                       79.2% median (worst 35%)
#   href stable across two loads of one source        100.0% median
#   name stable across two loads of one source        100.0% median
#   href resolves where name CANNOT                     4.15%
#   name resolves where href CANNOT                    12.83%
#   the two keys land on DIFFERENT elements             0.00%
#
# So href is a WORSE primary key -- lower on 22 of 28 sites -- and promoting it
# ahead of the identity rung would trade a 79% hit rate for a 62% one in order
# to fix a minority case. What the numbers DO license is a fallback: the two
# keys never disagree, so where href is unique it names the same element the
# name would have, and it is exactly as stable. Recorded only where it is
# unique AT RECORD TIME, and tried only after the recorded descriptor has
# failed, so it can convert a REFUSAL into a resolution and can never change a
# step that already worked.
#
# RESTRICTED TO <a>/<area> by HTML's own rule: href on those elements IS the
# hyperlink destination. Any element may carry the attribute; on a <div> it
# declares nothing, and admitting it there would be the class-substring guess
# #27/#28 took out of the paths that decide things.
ALT: tuple[str, ...] = ("tag", "role", "type", "href")
_LINK_TAGS = ("a", "area")

# THE WITNESS, and it exists because the crowd-check cannot see a PERMUTATION.
#
# `nth` of `of` is a POSITIONAL claim, and a positional claim is only worth
# anything while the order holds. Every mutation the shipped audit knew about
# changes the crowd's COMPOSITION -- a rename, a deletion, an inserted twin, a
# bumped counter -- and `len(hits) != of` catches all of them. A re-sorted
# table changes none of it: same elements, same declarations, same count, a
# different one at position N. MEASURED by adding that mutation to
# tools/audit_flow_resolve.py, which had never had it:
#
#   descriptors carrying an ordinal          574 of 2496   23.0%
#   under a reorder, BEFORE this existed:    5.6% CORRECT / 0.0% REFUSED
#                                            94.4% WRONG  <- silent mis-bind
#
# The live shape is a flow that clicks Delete on the first invoice row; the
# table's default sort flips to newest-first; the replay deletes a different
# invoice and reports PASSED, because "one fewer row" still holds. That is the
# #10/#11/#12 family -- act somewhere else, report success.
#
# SO THE ORDINAL NEEDS A WITNESS THAT A PERMUTATION DESTROYS, and by
# construction it cannot be any field in LEVELS: the crowd IS the set that
# matches on all of them. What is left is a field the descriptor deliberately
# ignores, or something OUTSIDE the crowd. Both are measured over the 300
# ordinal-bearing descriptors of 24 frozen sites, scoring a candidate by
# whether it is UNIQUE within the tied crowd (the condition under which
# checking it refuses every wrong binding):
#
#   self.href                17.3%     self.ALL (the five together)   22.7%
#   self.value                3.3%     anchor, 1 preceding control    51.7%
#   self.text                 4.0%     anchor, 2 preceding controls   58.7%
#   self.label/placeholder    0.0%     anchor, 3 preceding controls   59.3%
#   geometry (x, y)          87.3%     self.ALL + anchor              61.3%
#
# GEOMETRY WINS AND IS NOT USED, which is the one line worth not skipping.
# It is excluded from identity because it DRIFTS -- #23 measured 110px, #25
# measured 1,097px -- so a witness built on it would refuse on every reflow,
# every lazy image and every responsive break. A witness that fires on
# innocent change is #15's noise with a safety label on it.
#
# What ships is `self` plus the ANCHOR: the identities of the nearest
# preceding controls that are NOT in the crowd. That is how a human says which
# Delete button they mean -- the one next to invoice 1001 -- and it is a
# declared fact (document order plus accessible names), not a heuristic.
#
# THE RESIDUE IS STATED RATHER THAN HIDDEN: ~39% of tied crowds have members
# that are identical in every declared field AND sit in identical surroundings.
# Nothing the collector emits separates them, so no witness is recorded and the
# ordinal is taken exactly as before. Those steps are no worse than they were
# and no better; `Recorder.before` now says so at record time, which is the
# only moment it is cheap to act on.
_WITNESS_FIELDS = ("href", "value", "text", "label", "placeholder")
WITNESS_K = 3


def _name_of(entry: dict) -> str:
    """The identity slot, in the collector's own order of preference.

    `name` is the accessible name and `label` the resolved <label> -- both are
    identity. Then `placeholder`, and this is a deliberate departure from #6,
    which is emphatic that a placeholder is a format HINT and never a value or
    a name. That rule governs what is REPORTED to an agent, where crossing the
    slots was a real defect (#11: an input[submit] reporting its value in the
    name slot). This is a MATCHING KEY, not a report, and 8% of targetable
    controls carry no accessible name at all -- for those the placeholder is
    the only declaration there is, and a human reading the page would use it
    for exactly the same reason. `text` is last because an icon with a badge
    reads "3".
    """
    for k in ("name", "label", "placeholder"):
        v = (entry.get(k) or "").strip()
        if v:
            return v
    return (entry.get("text") or "").strip()


def fields(entry: dict) -> dict:
    """Every declared field a descriptor may draw on, normalised."""
    return {
        "tag": (entry.get("tag") or "").lower(),
        "role": entry.get("role") or "",
        "type": entry.get("type") or "",
        "name": _name_of(entry),
        "section": entry.get("section") or "",
        "under": (entry.get("underHeading") or "").strip(),
        # #37 suppresses a hint shared by rows that have their own identity, so
        # a `near` that SURVIVES is one that discriminates. That is why it earns
        # a rung here while adding nothing on pages where it is noise.
        "near": (entry.get("near") or "").strip(),
        # NOT a rung -- see ALT below. Carried in `fields` only so `matches()`
        # can test it, which means no existing descriptor changes shape.
        "href": (entry.get("href") or "").strip(),
    }


def at_level(entry: dict, level: int) -> dict:
    f = fields(entry)
    return {k: f[k] for k in LEVELS[level]}


def matches(target: dict, entry: dict) -> bool:
    """Does this entry satisfy the descriptor?

    EXACT equality on every field the descriptor carries. Not fuzzy, not
    ranked. #20 measured `find`'s lexical scorer at 0% when given a goal rather
    than a descriptor, and ranking here would reintroduce the thing #24 removed
    from the submit picker: choosing between candidates instead of refusing.
    """
    f = fields(entry)
    return all(f.get(k) == v for k, v in target.items())


def _targetable(entry: dict) -> bool:
    """Could a flow step act on this entry at all?

    Asked of what the collector already decided, never of a second tag list --
    #18 measured two rules disagreeing about what a control is as 60% of the
    whole accuracy gap, and #37 found the same asymmetry a third time.
    """
    return bool(entry.get("clickable") or entry.get("editable"))


def _identity(entry: dict) -> str:
    """What a NEIGHBOUR is called, for the anchor. Tag and role so a link and a
    button reading the same word are not the same anchor."""
    f = fields(entry)
    return f'{f["tag"]}|{f["role"]}|{f["name"]}'


def witness_map(entries: list[dict], crowd: list[dict]) -> dict:
    """mmid -> witness, for every member of `crowd`, in ONE pass.

    Built once over the document rather than per member, because a crowd can
    be hundreds of rows and the anchor needs what sits in front of each one.

    THE ANCHOR WINDOW IS RECORD-LOCAL, and that is the difference between a
    witness that survives a re-sort and one that does not. The first version
    took the last N named controls in front of the member, wherever they came
    from -- so after a sort the SAME element saw a different window (it now
    had neighbours in front of it that it did not have when it was first on
    the page) and the witness it had been recorded with no longer matched. The
    window resets at every crowd member, which makes it exactly the controls
    of that member's own record, and a record travels with its contents.

    THE FIRST MEMBER HAS NO PREDECESSOR TO BOUND IT, so it would otherwise
    collect the page header. It is given the shape of the NEXT member -- the
    records of a list are structurally alike, which is MDR/DEPTA's data-record
    assumption and the one #27 already uses to decide repetition.

    A crowd member is never an anchor for another crowd member: they are
    identical by construction, so they say nothing about which is which.
    """
    ids = {str(e.get("mmid")) for e in crowd}
    windows: dict = {}
    order: list = []
    recent: list = []
    for e in entries:
        mm = str(e.get("mmid"))
        if mm in ids:
            windows[mm] = recent[-WITNESS_K:]
            order.append(mm)
            recent = []
        elif _targetable(e) and _name_of(e):
            recent.append(_identity(e))
    if len(order) >= 2:
        n = len(windows[order[1]])
        windows[order[0]] = windows[order[0]][-n:] if n else []

    out: dict = {}
    for e in crowd:
        mm = str(e.get("mmid"))
        w: dict = {}
        own = {k: v for k in _WITNESS_FIELDS
               if (v := str(e.get(k) or "").strip())}
        if own:
            w["self"] = own
        if windows.get(mm):
            w["after"] = list(windows[mm])
        if w:
            out[mm] = w
    return out


def atoms_map(crowd: list[dict]) -> dict:
    """mmid -> the record-text atoms UNIQUE to that member of `crowd`.

    WHY A CONTENT WITNESS AND NOT A BETTER ORDINAL. A step that can only say
    "the 3rd Delete button" is correct until the list re-sorts, and then it
    deletes the wrong invoice and reports PASSED. Measured on 39 frozen sites,
    over the descriptors that HAVE one: under a re-sort the shipped self+anchor
    witness is 11.6% WRONG and 23.4% refused, where a content witness is 0.4%
    and 8.2%; when a DIFFERENT record is deleted it is 13.8% correct against
    96.3%.

    UNIQUE WITHIN THE CROWD, which is the same rule `build` applies to the
    self+anchor witness and to `alt`. An atom two members share cannot say which
    one was meant, so recording it would put a field in the file that looks like
    a safeguard and is not.

    SEPARATE FROM `witness`, deliberately. `build` tests the self+anchor witness
    for uniqueness by comparing whole dicts; folding atoms in would make that
    comparison trivially unique and silently delete the test.

    TEXT ONLY, and that is a measured refusal rather than an omission. Admitting
    ATTRIBUTE atoms raises coverage and mis-bound 4 of 120 descriptors with NO
    mutation at all, because Angular Material's `id="mat-select-value-3"` is
    unique, looks declared, and is a PER-LOAD counter -- and a two-load
    stability check passes while that hazard stays.
    """
    have = {str(e.get("mmid")): set(e.get("recordAtoms") or []) for e in crowd}
    out: dict = {}
    for mm, mine in have.items():
        if not mine:
            continue
        others: set = set()
        for other, theirs in have.items():
            if other != mm:
                others |= theirs
        uniq = mine - others
        if uniq:
            out[mm] = sorted(uniq)
    return out


def build(entry: dict, entries: Iterable[dict]) -> dict:
    """Describe `entry` as cheaply as it can be described unambiguously.

    Returns the descriptor plus, when no level disambiguates, the ordinal that
    does: `nth` of `of`. `of` is recorded so that replay can tell "the same
    crowd, pick the 3rd" from "a different crowd, do not guess" -- a change
    signal that costs no extra call, which is the whole reason it is stored
    rather than derived.
    """
    entries = list(entries)
    pool = [e for e in entries if _targetable(e)]
    full_desc = at_level(entry, FULL)
    alt = _alt_of(entry, pool)

    for level in range(1, len(LEVELS)):          # level 0 is never unique
        desc = at_level(entry, level)
        hits = [e for e in pool if matches(desc, e)]
        if len(hits) == 1:
            # BOTH are stored, and the cheap one alone was not enough.
            # MEASURED by audit_flow_resolve.py's twin-elsewhere mutation --
            # add a control with the target's name in another landmark and
            # 54% of cheap descriptors went AMBIGUOUS. They refused rather
            # than mis-binding, which is the right failure direction, but a
            # refusal costs a model turn (~3.6s, #38) and avoiding those is
            # the entire point of recording a flow. Carrying the full
            # descriptor as a tie-break buys that back for nothing: cheap
            # first, so a heading rename does not break a step whose name was
            # already unique; full second, so new ambiguity is narrowed
            # instead of escalated.
            out = {"level": level, "desc": desc, "full": full_desc}
            if alt:
                out["alt"] = alt
            return out

    desc = full_desc
    hits = [e for e in pool if matches(desc, e)]
    try:
        nth = next(i for i, e in enumerate(hits)
                   if str(e.get("mmid")) == str(entry.get("mmid")))
    except StopIteration:
        # The entry is not in its own pool: it is not targetable. Describe it
        # anyway rather than raising -- the caller gets a descriptor that will
        # fail to resolve LOUDLY at replay, which is better than a recording
        # that silently omits a step.
        return {"level": FULL, "desc": desc, "untargetable": True}
    out = {"level": FULL, "desc": desc, "nth": nth, "of": len(hits)}
    # ONLY HERE, and only when it is UNIQUE. A descriptor that resolved
    # without an ordinal makes no positional claim, so there is nothing for a
    # permutation to break and nothing to witness.
    #
    # Unique AT RECORD TIME is the whole test, exactly as it is for ALT: a
    # witness shared with another member of the crowd cannot say which one was
    # meant, so storing it would put a field in the file that looks like a
    # safeguard and is not. MEASURED, and this is why the rule is uniqueness
    # rather than mere presence: an `after` anchor exists for almost every
    # control on a page (something named nearly always precedes it), so a
    # presence test recorded a witness for 100% of tied crowds while only
    # ~61% of them had one that discriminates. The other ~39% would have
    # carried false comfort and silenced the record-time warning that is the
    # only honest answer for them.
    wm = witness_map(entries, hits)
    mine = wm.get(str(entry.get("mmid")))
    if mine and sum(1 for e in hits
                    if wm.get(str(e.get("mmid"))) == mine) == 1:
        out["witness"] = mine
    # THE CONTENT WITNESS, recorded beside the positional one rather than instead
    # of it. A step with atoms is decided by them at replay and never falls back
    # to the ordinal -- falling back would reinstate exactly the silent mis-bind
    # they exist to stop.
    am = atoms_map(hits)
    a = am.get(str(entry.get("mmid")))
    if a:
        out["atoms"] = a
    if alt:
        out["alt"] = alt
    return out


def unwitnessed_ordinal(target: dict) -> bool:
    """Does this step rest on a position with nothing to confirm it?

    Read by the recorder so an agent is told at RECORD time, which is the one
    moment the answer is cheap to act on: adding any distinguishing control to
    the row, or scoping the step differently, costs nothing while the agent is
    still driving and costs a re-record afterwards.

    EITHER WITNESS COUNTS, and leaving `atoms` out of this test made the warning
    LIE. Caught on the first live recording after atoms shipped: a step that had
    recorded `["Acme Ltd", "INV-1001"]` was still told it "is pinned by POSITION
    alone", which is the class C15 exists for -- a message asserting something
    the code can check and did not. The two witnesses answer the same question
    by different evidence (the surroundings, versus the record's own content),
    so either one answers it.
    """
    return (target.get("of") is not None
            and not target.get("witness") and not target.get("atoms"))


def _alt_of(entry: dict, pool: list[dict]) -> Optional[dict]:
    """The link's declared destination, when that alone names one element.

    Unique AT RECORD TIME is the whole test. An href shared by two links says
    nothing more than the name did, and storing it would only produce a second
    ambiguous refusal after the first one.
    """
    f = fields(entry)
    if f["tag"] not in _LINK_TAGS or not f["href"]:
        return None
    desc = {k: f[k] for k in ALT}
    hits = [e for e in pool if matches(desc, e)]
    return desc if len(hits) == 1 else None


class Unresolved(Exception):
    """A step's target could not be pinned to exactly one element.

    Carries the reason and the candidates, because #24 established the rule
    this class enforces: when zero or several match, REFUSE AND NAME THEM.
    `find`'s miss path (#39) establishes the second half -- a refusal has to
    hand over enough to act on, or it just costs a turn.

    AND WHICH TARGET IT WAS, which it did not carry and which made the whole
    escalation path unusable on a multi-target step. `fill_form` names one
    target per field; the runner walked them in order and gave the agent's
    answer to the FIRST, which was never the one that failed. Measured on a
    login step whose Email resolved and whose Password was ambiguous: the bind
    landed on Email, Password failed identically on every attempt so the run
    could never be resumed past the step, and the proposed patch rewrote
    EMAIL's descriptor to the password box -- which `record_flow(action=
    "patch")` would then have written to disk, making the flow type the user's
    email into a password field for ever. `resolve()` does not know the path
    (it is handed one descriptor), so the runner stamps it on the way out; the
    attribute exists here so there is one declared shape rather than an
    attribute invented at the raise site.
    """

    def __init__(self, reason: str, candidates: Optional[list] = None,
                 path: Optional[str] = None):
        super().__init__(reason)
        self.reason = reason
        self.candidates = candidates or []
        self.path = path


def resolve(target: dict, entries: list[dict],
            notes: Optional[list] = None, allow_alt: bool = True) -> str:
    """Descriptor -> the ONE mmid it names, or raise Unresolved.

    The rule, and every branch of it is load-bearing:

      1 match                exactly what was recorded. Use it.
      0 matches              the control this step names is not on the page.
      N matches, N == `of`   the same crowd as at record time -> the ordinal
                             means what it meant, so take it.
      N matches, N != `of`   the crowd CHANGED. Never guess: a row added above
                             the target silently shifts every ordinal, and the
                             step would click a different thing and report
                             success -- the #10/#11/#12 failure shape.

    Document order is the ordinal's basis and the collector emits in composed
    walk order (#37 fixed the overflow list for exactly this reason).

    A step whose target declares a hyperlink destination gets ONE more chance
    after all of that fails -- see ALT. `notes`, when given, is appended to
    whenever that fallback is what resolved the step, because a run that
    matched on a different key than it recorded is not quite a clean pass and
    the caller has to be able to say so.

    `allow_alt=False` asks the RECORDED descriptor alone. The runner uses it
    for every attempt inside its settle window, because a name that has not
    RENDERED yet is not a name that CHANGED -- offering the destination early
    collapses the two things that window exists to tell apart (#59), and the
    patch it then proposes is a mid-render reading.
    """
    try:
        return _resolve_recorded(target, entries, notes)
    except Unresolved as exc:
        alt = target.get("alt") if allow_alt else None
        if not alt:
            raise
        pool = [e for e in entries if _targetable(e)]
        hits = [e for e in pool if matches(alt, e)]
        if len(hits) != 1:
            raise
        if notes is not None:
            notes.append({"via": "href", "alt": dict(alt),
                          "was": dict(target.get("desc") or {}),
                          "mmid": str(hits[0].get("mmid")),
                          "reason": exc.reason})
        return str(hits[0].get("mmid"))


def _resolve_recorded(target: dict, entries: list[dict],
                      notes: Optional[list] = None) -> str:
    desc = target.get("desc") or {}
    full = target.get("full") or desc
    pool = [e for e in entries if _targetable(e)]
    want, nth = target.get("of"), target.get("nth")
    # The ordinal was counted against the FULL descriptor's hit list, so the
    # crowd it refers to is that one. Reading it against the cheap descriptor
    # would compare a position to a different population -- #22's rule, which
    # once reported a marker cost of 78.7% by dividing one population by
    # another.
    hits = [e for e in pool if matches(full if want is not None else desc, e)]

    # ORDER IS LOAD-BEARING HERE, and getting it wrong is not a near miss.
    #
    # The obvious shape puts `if len(hits) == 1: return hits[0]` first, because
    # one match looks like the easy case. It is the DANGEROUS case for a step
    # that recorded an ordinal: "the 1st of 2" against a page that now holds
    # one match means ONE OF THE TWO IS GONE, and nothing says the survivor is
    # the one that was recorded. MEASURED by tools/audit_flow_resolve.py with
    # that shortcut in place: deleting or renaming the target bound to the
    # WRONG element 7.9% of the time, silently, and reported success -- the
    # #10/#11/#12 family, reached by an ordering mistake rather than a
    # measurement one. The crowd-check therefore runs FIRST whenever the step
    # recorded a crowd, exactly as the gate checks Pause before UNGATED_OPS.
    # ATOMS FIRST, AND THAT ORDERING IS SAFE FOR THE REASON THE BLOCK BELOW IS
    # NOT. Everything below tests the crowd's COMPOSITION and then its ORDER,
    # and it has to, because an ordinal means nothing once either has moved. A
    # content witness makes no positional claim at all: it names the member by
    # text its own record carries, so neither a re-sort nor a row being added or
    # removed touches it. That is where the measured difference lives -- when a
    # DIFFERENT record is deleted the positional path is 13.8% correct and 85.6%
    # refused, where this one is 96.3% correct, because it never needed the
    # crowd to still be the same size.
    #
    # INTERSECTION, NOT EQUALITY. One cell of a row changing (a status flipping,
    # a total being recalculated) must not break a step whose other atoms still
    # name it; requiring the whole set to match would refuse on every edit. The
    # atoms were UNIQUE within the crowd when recorded, so a single carrier is
    # the member that was recorded.
    #
    # AND IT NEVER FALLS BACK TO THE ORDINAL. Zero or several carriers means the
    # thing that identified this element is gone or is no longer its alone --
    # and the position is not evidence of anything in either case. Falling
    # through to `nth` there would reinstate precisely the silent mis-bind the
    # atoms exist to stop, so this refuses and names the candidates instead.
    atoms = target.get("atoms")
    if atoms:
        want_a = set(atoms)
        cand = [e for e in hits if want_a & set(e.get("recordAtoms") or [])]
        # THE COMPOSITION GATE, and it is the ONE place this branch reads `of`.
        #
        # Everything above was written on the premise that a content witness
        # makes no positional claim, so neither a re-sort nor a row being added
        # or removed touches it. That is true of a re-sort and of a DIFFERENT
        # record being deleted -- which are the two arms it was measured on --
        # and FALSE when the target's own record is gone, because the resolver
        # then has to tell "my row lost a cell" from "my row is gone and a
        # stranger shares a word". It binds on INTERSECTION, so one shared
        # token decides it. MEASURED: a step recording
        # ['Acme Ltd', 'INV-1001', 'Paid'] binds to an unrelated customer's
        # invoice because that row also renders `Paid`, and when the survivor
        # happens to land at the recorded index it emits no note either, so the
        # flow reports PASSED having deleted the wrong record. Worse, the
        # ordinal path REFUSED that case before atoms existed
        # (`len(hits) != of`), so this was a regression introduced by the fix
        # for the previous silent mis-bind. tools/audit_atoms_safety.py.
        #
        # THE RULE IS EXACT AND THERE IS NO THRESHOLD IN IT. Composition
        # unchanged -> a SUBSET still identifies the member, which is the
        # tolerance the intersection rule exists for (a status flipping, a
        # total recalculated). Composition CHANGED -> the record must be wholly
        # present, because a missing record and an edited cell are otherwise
        # the same evidence and the page declares nothing that separates them.
        # "All of them" and "the same number as before" are facts, not chosen
        # numbers.
        #
        # THE TOLERANT VARIANT IS REJECTED, and it is the one that looks
        # better: requiring only the atoms still present ANYWHERE in the crowd
        # would survive a simultaneous edit, and it re-admits the defect --
        # with the target's record gone the only surviving recorded atom IS
        # `Paid`, so "all present atoms" is `{Paid}` and the stranger carries
        # all of it.
        gated = want is not None and len(hits) != want
        if gated:
            cand = [e for e in cand
                    if want_a <= set(e.get("recordAtoms") or [])]
        if len(cand) != 1:
            raise Unresolved(
                (f"{len(hits)} element(s) match {_describe(desc)} but {want} did when "
                 f"this flow was recorded, so the crowd CHANGED — and {len(cand)} of "
                 f"them still carry the whole of the text that identified this one "
                 f"({', '.join(repr(x) for x in atoms[:3])}"
                 f"{', …' if len(atoms) > 3 else ''}). Exactly one must. When a row "
                 f"has been added or removed, a record that carries only PART of that "
                 f"text is as consistent with a different record sharing a word as it "
                 f"is with this one having changed a cell, and the recorded position "
                 f"is not evidence either"
                 if gated else
                 f"{len(hits)} element(s) match {_describe(desc)}, and {len(cand)} of "
                 f"them carry the text that identified this one when the flow was "
                 f"recorded ({', '.join(repr(x) for x in atoms[:3])}"
                 f"{', …' if len(atoms) > 3 else ''}). Exactly one must. Its record "
                 f"was removed, its text changed, or another record now carries the "
                 f"same text — and the recorded position is not evidence of which "
                 f"element was meant in any of those cases"),
                _candidates(hits))
        if nth is not None and 0 <= nth < len(hits) \
                and str(cand[0].get("mmid")) != str(hits[nth].get("mmid")):
            # Resolved, and NOT where it was recorded. Deterministic, but the
            # list moved under the flow and the caller has to be able to say so
            # — the same reason the href fallback reports itself (#61).
            if notes is not None:
                notes.append({"via": "atoms",
                              "was": dict(desc), "nth": nth,
                              "now": hits.index(cand[0]),
                              "mmid": str(cand[0].get("mmid"))})
        return str(cand[0].get("mmid"))

    # AN ORDINAL ACROSS FRAMES HAS NO BASIS. The ordinal's declared basis is
    # DOCUMENT ORDER -- "the collector emits in composed walk order", a few
    # lines up. A crowd spanning frames has no single document: cross-frame
    # entries are CONCATENATED after the top document's, in whatever order
    # `chrome.webNavigation.getAllFrames` returned the frames, and nothing in
    # the platform declares that to be stable.
    #
    # This became reachable on 2026-11-18 (97efc75, #94): the structured array
    # the recorder describes from now carries cross-frame entries, where before
    # it did not and the step was dropped at compile. `collectCrossFrames`
    # forces `section: e.section || 'iframe'`, so every cross-frame control on
    # a page collapses into ONE landmark bucket -- and `section` is the rung
    # that takes a descriptor from 59.5% to 84.7% unique. A page embedding the
    # same widget twice (a saved-card and a new-card payment frame; one CMP
    # mounting in two frames) therefore produces a crowd of identical
    # descriptors whose only discriminator is the enumeration order, and
    # swapping it binds the other frame and reports success.
    #
    # REFUSE RATHER THAN GUESS (#24, #49): the frame is declared by the mmid's
    # own form, so this needs no new field and no threshold. The cost on the
    # frozen corpus is ZERO -- #78 measured 0 of 128 frames cross-origin there
    # -- and on a real page it is a pause exactly where the alternative is a
    # coin flip between two payment frames.
    #
    # NOT applied to the atoms branch above, deliberately: a content witness
    # names the member by text its own record carries, which is as true inside
    # a frame as outside it. This guards the paths that rest on ORDER, and the
    # self+anchor witness is inside it because `witness_map` builds its window
    # by walking `entries` in that same concatenated order.
    if want is not None and nth is not None \
            and len({frame_of(e) for e in hits}) > 1:
        raise Unresolved(
            f"the {len(hits)} element(s) matching {_describe(desc)} are spread across "
            f"several frames, so there is no document order to count position "
            f"{nth} in — cross-origin frames are listed after the top document in "
            f"whatever order the browser enumerated them, which is not something "
            f"the page declares. Name the one you mean",
            _candidates(hits))

    if want is not None and nth is not None:
        if len(hits) != want:
            raise Unresolved(
                f"{len(hits)} element(s) match {_describe(desc)} but {want} did "
                f"when this flow was recorded, so position {nth} is no longer the "
                f"same element — the page changed around this step",
                _candidates(hits))
        if not 0 <= nth < len(hits):
            raise Unresolved(
                f"ordinal {nth} is outside the {len(hits)} matches",
                _candidates(hits))
        # THE CROWD IS THE SAME CROWD; IS IT IN THE SAME ORDER? Everything
        # above tests composition, and a permutation changes none of it. See
        # the WITNESS block at the top for the measurement: before this, a
        # re-sorted crowd mis-bound 94.4% of the time with no signal at all.
        #
        # The witness was unique when it was recorded, so ONE member carrying
        # it is the member that was recorded -- at whatever position it now
        # sits, which is how a re-sort resolves correctly instead of costing a
        # turn. Zero or several means the thing that identified it is gone,
        # and then the position is not evidence of anything.
        wit = target.get("witness")
        if wit:
            wm = witness_map(entries, hits)
            cand = [e for e in hits if wm.get(str(e.get("mmid"))) == wit]
            if len(cand) != 1:
                raise Unresolved(
                    f"the {len(hits)} element(s) matching {_describe(desc)} are the "
                    f"same crowd that was recorded, but {len(cand)} of them now carry "
                    f"what identified this one ({_witness_text(wit)}) — so position "
                    f"{nth} is no longer evidence of which one this step meant. A "
                    f"re-sorted list, a row removed while another was added, and a "
                    f"rename of the controls around it all produce this",
                    _candidates(hits))
            if str(cand[0].get("mmid")) != str(hits[nth].get("mmid")):
                # Resolved, and NOT where it was recorded. Deterministic -- the
                # witness names exactly one element -- but the list has moved
                # under the flow and the caller has to be able to say so, the
                # same reason the href fallback reports itself (#61).
                if notes is not None:
                    notes.append({"via": "position",
                                  "was": dict(desc), "nth": nth,
                                  "now": hits.index(cand[0]),
                                  "mmid": str(cand[0].get("mmid"))})
            return str(cand[0].get("mmid"))
        return str(hits[nth].get("mmid"))

    # No ordinal was recorded, which means the descriptor was unique at record
    # time. It has to still be unique now, or we do not know what it meant.
    if len(hits) == 1:
        return str(hits[0].get("mmid"))

    if not hits:
        raise Unresolved(
            "no element on the page matches this step's target: " + _describe(desc))

    # The cheap descriptor went ambiguous. Narrow with the full one before
    # escalating -- a control with this name appearing elsewhere on the page
    # is the commonest way that happens, and the landmark separates them.
    if full is not desc:
        narrowed = [e for e in pool if matches(full, e)]
        if len(narrowed) == 1:
            return str(narrowed[0].get("mmid"))
        if narrowed:
            hits = narrowed

    raise Unresolved(
        f"{len(hits)} elements match {_describe(desc)} and the step records no "
        f"ordinal, so which one it meant is not recoverable",
        _candidates(hits))


def _witness_text(w: Optional[dict]) -> str:
    if not w:
        return "nothing distinguishing"
    bits = []
    if w.get("self"):
        bits.append(" ".join(f"{k}={v!r}" for k, v in w["self"].items()))
    if w.get("after"):
        bits.append("after " + " / ".join(repr(a) for a in w["after"]))
    return "; ".join(bits) or "nothing distinguishing"


def _describe(desc: dict) -> str:
    bits = [f'{k}={v!r}' for k, v in desc.items() if v]
    return " ".join(bits) if bits else "(an empty descriptor)"


def _candidates(hits: list[dict]) -> list[str]:
    out = []
    for e in hits[:12]:
        f = fields(e)
        out.append(f'ref_{e.get("mmid")} | {f["tag"]}'
                   + (f' role={f["role"]}' if f["role"] else "")
                   + (f' name="{f["name"]}"' if f["name"] else "")
                   + (f' under="{f["under"]}"' if f["under"] else ""))
    if len(hits) > 12:
        out.append(f"... and {len(hits) - 12} more")
    return out
