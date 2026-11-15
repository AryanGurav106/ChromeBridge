"""The parts of the Mind2Web ruler that decide things — shared, and testable
without a browser.

`bench_mind2web.py` produces the only out-of-sample number in this project.
Two of its rules were restated rather than shared: `bench_trajectory.py` reuses
its PROBE with a comment saying a second copy of the credit rule "would drift
away from them silently", and then writes one inline four lines below. One
concept, two spellings, which is the shape CLAUDE.md #21 exists to stop. Both
rules live here now, in Python, where a unit test can drive them.

--------------------------------------------------------------------------
1. SERIALIZATION REPAIR — the snapshots are XML, and Chromium parses HTML
--------------------------------------------------------------------------
Mind2Web serializes the recorded DOM XML-style, so an EMPTY element comes back
as `<a/>`, `<i/>`, `<iframe/>`. HTML has no self-closing syntax for a non-void
element: the slash is ignored and the tag OPENS. Two consequences, one loud and
one quiet, and the quiet one is the dangerous one:

  LOUD   `<iframe/>` and `<textarea/>` are RAWTEXT/RCDATA, so everything after
         one of them becomes TEXT. espn parses 744 ids where its snapshot holds
         4,115. Thirteen labelled targets were plainly in the saved string and
         absent from the DOM, and the benchmark excluded them saying the target
         was "absent from the saved snapshot entirely" — which was false.

  QUIET  a self-closed `<a/>`, `<i/>` or `<div/>` simply stays OPEN and adopts
         the markup that follows, and HTML's adoption agency then RE-CREATES it
         at every block boundary. Measured across all 186 snapshots: the
         unrepaired parse emits CLONES — nodes sharing one `backend_node_id` —
         on **137 of 186 samples**, up to 2.48 nodes per distinct id. Repairing
         every non-void self-closed tag takes that to **0 of 186**, and never
         recovers fewer distinct ids than the unrepaired or RAWTEXT-only parse
         (better on 23, worse on 0). Coverage of the record's ids goes
         99.0% -> 99.8% median.

That measurement is why the repair is FAITHFUL (every non-void tag) rather than
minimal (RAWTEXT only). It is not a free choice: the minimal repair fixes the
13 targets and leaves three ancestor credits standing that the raw bytes show
are artefacts — on sixflags, underarmour and ikea the "wrapping anchor" is a
self-closed `<a ... bounding_box_rect="-1,-1,-1,-1"/>`, i.e. an element Mind2Web
itself recorded as EMPTY and rendering nothing. Choosing the repair that keeps
those credits because it prints a higher number would be choosing the ruler for
the answer.

Residue, stated because a bound nobody can see is indistinguishable from no
bound: after repair, a median 99.8% of each snapshot's ids parse, worst 43.4%.
The worst case is Mind2Web nesting a frame's whole document INSIDE the
`<iframe>` element, which is rawtext whatever the slash does — unrepairable
without rewriting the tag, which would change what the collector is shown. No
labelled target is among them: all 186 resolve to exactly one node after repair.

--------------------------------------------------------------------------
2. CREDIT — and the asymmetry #73 found in it
--------------------------------------------------------------------------
A target counts as recalled if we listed the element itself, an ancestor, or a
descendant. The indirect paths are sound for different reasons:

  DESCENDANT  by event bubbling — a click inside the target passes through it.
  ANCESTOR    only if ACTIVATING the ancestor does the one thing the target did.

The descendant path was capped by area so a page-sized container cannot claim
credit for its contents (#18). The ancestor path had NO bound at all — and that
is the direction where a false credit is structurally possible, because an
ancestor is by construction at least as large as its target. Measured: the cap
has never fired on the descendant side (0 of 173 targets reach 40% of the
viewport) while the ancestor side carried a credit from a `<label>` to an `<a>`
eleven levels up holding 638 elements and 90% of the viewport.

One rule, both directions: **the element standing in may not be page-sized.**
For a descendant credit the containing element is the TARGET; for an ancestor
credit it is the ANCESTOR. Same constant, so they cannot drift.
"""

from __future__ import annotations

import re

# HTML's void elements: `<img/>` really is self-closing, the rest are not.
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
# RAWTEXT / RCDATA. A self-closed one of these does not merely nest wrongly, it
# turns every byte after it into TEXT.
RAWTEXT = {"textarea", "title", "script", "style", "iframe", "noscript",
           "noframes", "xmp", "plaintext"}
# Attribute values may contain `/>`, so the scan tracks quoting rather than
# stopping at the first `>`.
SELF_CLOSED = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*?)/>")

# A stand-in this large is not standing in for anything: it is the page. Used in
# BOTH credit directions (see §2) — the one number is the point.
CREDIT_AREA_CAP = 0.4


def repair_serialization(html: str, only: set | None = None) -> str:
    """Turn `<tag ... />` back into `<tag ...></tag>` for non-void elements.

    `only` limits the repair to a tag set — `RAWTEXT` is the minimal fix that
    recovers the 13 lost targets and nothing else, kept so the arms can be
    compared. The default repairs every non-void element, which is the faithful
    XML->HTML reconstruction and the one the benchmark ships; §1 has the
    measurement that chose it.
    """
    def sub(m: re.Match) -> str:
        t = m.group(1).lower()
        if t in VOID or (only is not None and t not in only):
            return m.group(0)
        return f"<{m.group(1)}{m.group(2)}></{m.group(1)}>"
    return SELF_CLOSED.sub(sub, html)


def credit_refs(probe: dict, cap: float = CREDIT_AREA_CAP) -> list[tuple[str, str]]:
    """Every ref an agent could act on to do what the human did, best first.

    Returns `(mmid, path)` pairs ordered own -> ancestor -> descendant, which is
    the precedence the benchmark has always used. The caller intersects them
    with what was actually listed; nothing here knows about the listing, so the
    rule can be driven from a unit test with a hand-built probe.

    `cap` is the knob only so that a caller can ask what the UNCAPPED rule would
    have said — which is the only honest way to report what the cap cost.
    """
    out: list[tuple[str, str]] = []
    if probe.get("own"):
        out.append((str(probe["own"]), "own"))
    for a in probe.get("ancs") or []:
        if (a.get("area") or 0.0) < cap:
            out.append((str(a["mmid"]), "ancestor"))
    # The container here is the TARGET: a page-sized target cannot be credited
    # with everything inside it.
    if (probe.get("area") or 0.0) < cap:
        for d in probe.get("descs") or []:
            out.append((str(d), "descendant"))
    return out


def cap_withdrew(probe: dict, listed) -> bool:
    """Did the cap change this row's verdict?

    NOT "does an oversized ancestor exist" — #73 caught its own probe reporting
    8 capped credits where the truth was 1, because it counted rows where a big
    ancestor merely existed, including rows already credited via `own`. The only
    number worth printing is the one where the capped and uncapped rules
    DISAGREE about what this action was credited to.
    """
    def first(cap):
        return next(((r, v) for r, v in credit_refs(probe, cap) if r in listed),
                    (None, "none"))
    return first(CREDIT_AREA_CAP) != first(1.0)
