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

from typing import Any, Iterable, Optional

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


def build(entry: dict, entries: Iterable[dict]) -> dict:
    """Describe `entry` as cheaply as it can be described unambiguously.

    Returns the descriptor plus, when no level disambiguates, the ordinal that
    does: `nth` of `of`. `of` is recorded so that replay can tell "the same
    crowd, pick the 3rd" from "a different crowd, do not guess" -- a change
    signal that costs no extra call, which is the whole reason it is stored
    rather than derived.
    """
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
    if alt:
        out["alt"] = alt
    return out


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
    """

    def __init__(self, reason: str, candidates: Optional[list] = None):
        super().__init__(reason)
        self.reason = reason
        self.candidates = candidates or []


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
        return _resolve_recorded(target, entries)
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


def _resolve_recorded(target: dict, entries: list[dict]) -> str:
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
