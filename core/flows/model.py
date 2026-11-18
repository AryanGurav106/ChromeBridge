"""The flow file: what a recorded step is, and how it is read back.

A flow is a list of MCP tool calls with every per-document handle replaced by a
declared descriptor, plus the postcondition that was observed to hold after the
step when it was recorded.

The format is JSON because `browser_batch` already takes exactly this shape --
`[{name, input}]` -- so a flow is a persisted actions array and replay is the
runner that already exists. It also diffs cleanly in review, which matters
because a healed step proposes a PATCH rather than rewriting itself.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

SCHEMA = 1

# Input keys that carry a PER-DOCUMENT handle and therefore cannot be recorded
# verbatim. Kept here rather than imported from mcp_server because the
# dependency runs the other way; tools/test_flows.py FD16 pins that this list
# and browser_batch's `_REF_KEYS` stay identical, which is the enforcement #21
# asks for when one concept has to be spelled in two places.
#
# `coordinate` is deliberately ABSENT. A point is not an element: there is
# nothing to describe and nothing to re-resolve, so a recorded coordinate is
# fragile by construction and the recorder marks it rather than pretending
# otherwise. #26 made geometry opt-in for the same reason, and #23/#25 measured
# ours drifting 110px and 1097px.
REF_KEYS = ("ref", "ref_id", "submit_ref")

# fill_form's `fields` is a LIST whose entries address the page by `ref`,
# `mmid` OR `selector`. Only the first two are per-document (#48/B12).
FIELD_REF_KEYS = ("ref", "mmid")

# Does this tool change the page? Unlike #42's deleted `_OBSERVES` whitelist,
# which gated a SAFETY decision and silently skipped real steps when it went
# stale, this gates only how a recording is COMPILED: misclassifying a tool
# yields a slightly worse flow, never a wrong click. It is still derived from
# the call's own input where that is possible -- `computer` is decided by its
# action, not by its name.
MUTATES = {
    "navigate", "form_input", "fill_form", "file_upload", "upload_image",
    "call_page_tool", "javascript_tool", "tabs_create_mcp", "tabs_close_mcp",
    "resize_window",
    # ACCEPTING A confirm() TAKES THE ACTION BEHIND IT -- `dismiss_dialog`'s own
    # parameter documentation says so in as many words. It was classified as an
    # OBSERVATION, so a happy path that goes through a native dialog had the one
    # call that completes it folded away as scenery: measured on a fixture whose
    # Delete asks first, the recording kept `navigate` + the click and dropped
    # the dismissal, leaving a flow that stops at a dialog nothing will answer.
    # The classification is what was wrong; a dialog that is dismissed rather
    # than accepted changes nothing on the page, but the op is the same op and
    # the decision belongs to the recording, not to a guess about its argument.
    "dismiss_dialog",
}
COMPUTER_OBSERVES = {"screenshot", "wait", "zoom"}

# A PER-DOCUMENT HANDLE THAT IS NOT A REF, AND THEREFORE NOT RE-RESOLVED.
#
#   coordinate    a point, not an element: nothing to describe and nothing to
#                 re-resolve, so a recorded one is fragile by construction.
#                 #26 made geometry opt-in for the same reason and #23/#25
#                 measured ours drifting 110px and 1097px.
#   imageId       `img_<n>`, a SEQUENTIAL counter into the server's in-memory
#                 screenshot registry (mcp_server._IMG_SEQ). It means nothing in
#                 a later process -- and the dangerous case is not that it
#                 misses: a replay in a session that happens to have taken more
#                 screenshots resolves `img_3` to a DIFFERENT image and uploads
#                 it successfully.
#
# The comment above REF_KEYS has claimed since it was written that "the recorder
# marks it rather than pretending otherwise". Nothing marked it: a drag step
# compiled to literal pixels with no target, no review line and no note, which
# is principle 18 -- a comment asserting a guarantee the code does not have.
# `Recorder.compile` reads this and names each one on the step that carries it.
UNRESOLVABLE_INPUTS = {
    "coordinate": ("a COORDINATE, which is a point rather than an element: "
                   "nothing describes it and nothing re-resolves it, so this "
                   "step replays at the same pixels whatever the page does"),
    "imageId": ("an IMAGE ID, which is a counter into the screenshot registry of "
                "the session that recorded it. A later session resolves the same "
                "id to a DIFFERENT image, or to none at all"),
}


def created_tab(result):
    """The tab id `tabs_create_mcp` just made, or None if it cannot be read.

    ONE SPELLING, because both ends need it: the RUNNER follows a tab the flow
    creates (#58) and the RECORDER has to know the same thing to tell a step
    that merely names a tab apart from one that names a tab the replay will
    never have. Two copies would drift and each would be exercised by half the
    tests (rule 17).

    The tool answers with JSON, and a result-string contract is exactly what
    kept `delta` dead for its whole life (#30) -- so the parsed shape is
    accepted as well, and neither being there is an answer of None rather than
    a guess.
    """
    if isinstance(result, dict):
        v = result.get("tabId")
        return int(v) if v is not None else None
    try:
        return int((json.loads(result) or {}).get("tabId"))
    except Exception:
        pass
    m = re.search(r'"tabId"\s*:\s*(\d+)', str(result or ""))
    return int(m.group(1)) if m else None

# Calls that establish WHERE the flow acts rather than changing the app. They
# mutate the browser and not the page, which is why `MUTATES` has to keep
# them and why the PRECONDITION has to skip them.
#
# `require` is the state a flow expects to start from, and it was derived from
# everything the agent observed before its first MUTATING call -- which made
# it structurally unreachable, because the `instructions=` field (#45) and
# browser_batch's description (#46) both teach an agent to open with
# `tabs_create_mcp -> navigate -> read_page`. The first call is therefore
# always mutating, so the derivation always stopped before any observation,
# so `require` is `{}` in all 19 recorded flows and has never once fired.
# #50's headline capability ("nothing in the space does preconditions") had a
# reader and no writer -- rule 14, and the fifth instance of it.
NAVIGATIONAL = {"navigate", "tabs_create_mcp", "tabs_close_mcp"}


def mutates(name: str, inp: dict) -> bool:
    if name == "computer":
        return str((inp or {}).get("action") or "") not in COMPUTER_OBSERVES
    return name in MUTATES


def slug(s: str, upper: bool = False) -> str:
    """An ASCII identifier, or '' when nothing survives.

    Shared by the VARIABLE names and the SECRET env-var names so one concept
    has one spelling (#21). The ASCII allowlist is correct for both and wrong
    for a filename: a variable is referenced as {{name}} in JSON and a secret
    is an environment variable, which POSIX fixes at [A-Za-z_][A-Za-z0-9_]*.
    A filename may be in any script, which is why _flow_path strips only what
    a filesystem forbids (#32, #49). Callers fall back to a field's POSITION
    when a non-Latin label leaves nothing, rather than emitting an empty name.
    """
    out = re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", s or "")).strip("_")
    return out.upper() if upper else out.lower()


# WHAT A STEP DOES WHEN ITS TARGET CANNOT BE RESOLVED. Exactly two answers,
# and the third one that used to be declared here was DELETED rather than
# implemented.
#
#   "ask"   stop, hand back the reason and the candidates, and let the agent
#           answer with run_flow(resume_id=…, bind="ref_N"). The decision then
#           appears in the transcript, costs a visible turn, and proposes a
#           patch it never applies.
#   "fail"  stop and report. For a step whose absence IS the result.
#
# `"heal"` was in this enum from the first commit, nothing ever wrote it, and
# the runner only ever branched on "fail" -- so a flow asking for it silently
# got "ask". Closing that gap by IMPLEMENTING it was never available: an
# automatic heal means ranking the candidates and binding to the winner, which
# is precisely what the three rules at the top of runner.py forbid, and what
# #24 removed from the submit picker. ReUseIt's own LLM judge agreed with a
# human at kappa=0.528 and workflow-use calls its fallback "currently really
# bad"; a value promising that is a promise this design will not keep. So it
# is gone, and an unknown value is now REFUSED at load rather than quietly
# becoming "ask" -- which was the actual danger, and the same silent
# fallthrough that kept `delta` dead for its whole life (#30).
#
# WHAT WOULD ADD A THIRD VALUE: a recorded flow containing a step that is
# CONDITIONALLY PRESENT -- a consent banner, an onboarding tooltip -- where
# "not there" is a normal outcome rather than a drift. That is `"skip"`, it is
# a different idea from healing, and it is not built because no flow recorded
# so far has needed it. Shipping an enum value before its case exists is how
# this entry happened.
ON_FAIL = ("ask", "fail")

# WHAT AN `expect` MAY SAY, validated at LOAD for the same reason `on_fail` is
# (#62): an unrecognised key asserts NOTHING and does it in silence. `on_fail`
# was the one field anything validated; `expect` -- the half of the file that
# decides whether a replay can FAIL AT ALL -- was validated nowhere. Measured
# through the real runner:
#
#   {"querry": {...count 99}}                 -> PASSED, zero assertion tools called
#   {"console": {...}}                        -> PASSED, zero assertion tools called
#   {"query": {"selector": "tr", "Count": 99}} -> PASSED (the query ran, nothing compared)
#   {"query": {"selctor": "tr", "count": 99}} -> raised KeyError: 'selector'
#
# The first three are the exact silent fallthrough #62 closed, reachable by a
# hand edit, a merge, a format change or record_flow(action="patch"). The
# fourth is the same hole wearing an unreadable error. A flow file is meant to
# be edited by people, so the answer is the one #62 used: refuse at load,
# name the valid set, and let --check-only find it with no browser.
# `path` is "url" reduced to pathname+search, and it exists because of what the
# agents are TAUGHT to open with. `require` is derived from the observations
# between the landing navigation and the first action, and the opening in both
# `instructions=` (#45) and `browser_batch`'s description (#46) is
# `tabs_create_mcp -> navigate -> read_page` -- so the one observation that is
# always there contributed NOTHING, and `require` reached 1 flow in 20.
# NOT reconstructed into an absolute url from the flow's `origin`: that drops a
# `#fragment` the live `get_url` would carry, and a page with a hash is
# indistinguishable from one without by the time it reaches us. Comparing the
# PATH to the PATH is one fact in one spelling (rule 17), and it is the more
# robust check anyway -- the same argument #61 used for preferring a same-origin
# href as a bare path, since a host or port change should not fail a step.
EXPECT_KINDS = ("url", "path", "search", "query")
EXPECT_FIELDS = {
    "search": ("pattern", "absent", "min", "observed",
               "regex", "css_scope", "case_sensitive"),
    "query": ("selector", "count", "min", "text", "attrs"),
}
EXPECT_REQUIRED = {"search": "pattern", "query": "selector"}


def validate_expect(where: str, exp: Optional[dict]) -> None:
    """Raise ValueError naming the offending key. Used for a step's `expect`
    AND for a flow's `require`, which is the same shape asked at a different
    moment -- two copies would drift and each would be exercised by half the
    tests (#21)."""
    if not exp:
        return
    if not isinstance(exp, dict):
        raise ValueError(f"{where} must be a mapping of "
                         f"{'/'.join(EXPECT_KINDS)}, not {type(exp).__name__}")
    for kind, val in exp.items():
        if kind not in EXPECT_KINDS:
            raise ValueError(
                f"{where} declares a check of kind {kind!r}, which this build "
                f"does not implement, so it would assert NOTHING and say so to "
                f"nobody. Valid: {', '.join(EXPECT_KINDS)}.")
        # `url` and `path` are both bare STRINGS, so they share this branch
        # rather than `url` being special-cased and `path` falling through to
        # the mapping check. It did fall through, and a flow whose recorder had
        # written a path check could not be loaded at all:
        #   ValueError: require.path must be a mapping (or a list of them),
        #              not str
        # Found by building a flow that depends on inherited page state, not by
        # reading -- FP11 drives the RECORDER and FO7 drives the VALIDATOR and
        # nothing drove one through the other, which is #19/#30's untested link
        # at the load boundary. Adding a kind now means adding it HERE too, and
        # FO8 is the check that fails if it is not.
        if kind in ("url", "path"):
            if not isinstance(val, str):
                raise ValueError(
                    f"{where}.{kind} must be the string that was observed, "
                    f"not {type(val).__name__}")
            continue
        for item in (val if isinstance(val, list) else [val]):
            if not isinstance(item, dict):
                raise ValueError(
                    f"{where}.{kind} must be a mapping (or a list of them), "
                    f"not {type(item).__name__}")
            need = EXPECT_REQUIRED[kind]
            if not item.get(need):
                raise ValueError(
                    f"{where}.{kind} has no {need!r}, so there is nothing for "
                    f"it to look at. Keys present: "
                    f"{', '.join(sorted(item)) or '(none)'}.")
            bad = sorted(set(item) - set(EXPECT_FIELDS[kind]))
            if bad:
                raise ValueError(
                    f"{where}.{kind} declares {', '.join(repr(b) for b in bad)}, "
                    f"which this build does not read — a misspelt field is an "
                    f"assertion that silently checks nothing. Valid: "
                    f"{', '.join(EXPECT_FIELDS[kind])}.")
            # ...AND A LEGAL KEY CAN STILL ASSERT NOTHING, which is the same
            # silence wearing a valid name. `{"min": 0}` passes every check
            # above and `tot < 0` is never true, so the step reports a
            # postcondition and has none -- and a flow that cannot fail is the
            # worst thing a test runner can produce. `count: 0` is NOT this: it
            # is a disappearance, which is half of what a UI test checks
            # (#63/D13). Only the floor that no page can fall below is refused.
            _floor = item.get("min")
            if _floor is not None and (not isinstance(_floor, int)
                                       or isinstance(_floor, bool) or _floor < 1):
                raise ValueError(
                    f"{where}.{kind} declares min={_floor!r}. A floor below 1 is "
                    f"satisfied by every page including a blank one, so this "
                    f"check cannot fail — use count for an exact observation, or "
                    f"min>=1 for presence.")
            if kind == "query" and not any(
                    k in item for k in ("count", "min", "text", "attrs")):
                raise ValueError(
                    f"{where}.query names a selector and nothing to compare it "
                    f"against, so it runs the query and asserts nothing. Add "
                    f"count, min, text or attrs.")
            if kind == "search" and not item.get("absent") and "min" not in item:
                raise ValueError(
                    f"{where}.search names a pattern and neither absent nor min, "
                    f"so it searches the page and asserts nothing. Add min (it is "
                    f"there) or absent (it is not).")


@dataclass
class Step:
    name: str                                   # the MCP tool to call
    input: dict                                 # its arguments, refs removed
    targets: dict = field(default_factory=dict)  # input path -> descriptor
    expect: dict = field(default_factory=dict)   # checked LIVE, never healed
    on_fail: str = "ask"                        # see ON_FAIL
    # WHY THIS STEP IS HERE, in a human's words. Written by a person editing
    # the file -- the recorder has nothing to say that belongs here -- and
    # READ by the runner, which repeats it whenever the step fails or pauses.
    # It had no reader at all until then, which made it the kind of declared
    # field rule 14 is about: a person could write one and nothing would ever
    # show it to anybody. The moment a step breaks is exactly when "why is
    # this step here" is the question being asked.
    note: str = ""
    # WHAT THE RECORDING COULD NOT VOUCH FOR, one line per check. #68 made the
    # compile say which assertions carry no evidence -- and then printed it
    # ONCE, at stop, into a transcript. The person who re-grades a recorded
    # assertion is a human reading a small JSON diff, and that is precisely
    # where it was not. Persisted so it survives into the diff, into
    # --check-only and into CI.
    review: list = field(default_factory=list)
    # HOW LONG THIS APP ACTUALLY TOOK, measured at record time rather than
    # chosen. A fixed window cannot fit every app: 6s was too short for a real
    # one whose create -> table-refresh cycle took ~11s, and the flow reported
    # FAILED for an action that had SUCCEEDED. The recording already knows the
    # answer, because it timestamps every call.
    settle_ms: int = 0

    def to_json(self) -> dict:
        d = {"name": self.name, "input": self.input}
        if self.targets:
            d["targets"] = self.targets
        if self.expect:
            d["expect"] = self.expect
        d["on_fail"] = self.on_fail
        if self.settle_ms:
            d["settle_ms"] = self.settle_ms
        if self.note:
            d["note"] = self.note
        if self.review:
            d["review"] = list(self.review)
        return d

    @staticmethod
    def from_json(d: dict) -> "Step":
        of = d.get("on_fail") or "ask"
        if of not in ON_FAIL:
            # LOUDLY, at LOAD, naming the valid set. The alternative is what
            # shipped: an unrecognised value fell through to "ask" and the
            # flow ran, so a file asking for behaviour this build does not
            # have was indistinguishable from one that did not ask.
            raise ValueError(
                f"step {d.get('name')!r} declares on_fail={of!r}, which this "
                f"build does not implement. Valid: {', '.join(ON_FAIL)}. "
                f"(\"heal\" was removed: an automatic rebind means ranking "
                f"candidates, which this runner refuses to do — \"ask\" hands "
                f"the choice to the agent and records it.)")
        validate_expect(f"step {d.get('name')!r} expect", d.get("expect"))
        return Step(name=d["name"], input=d.get("input") or {},
                    targets=d.get("targets") or {}, expect=d.get("expect") or {},
                    on_fail=of, note=d.get("note") or "",
                    review=list(d.get("review") or []),
                    settle_ms=int(d.get("settle_ms") or 0))


@dataclass
class Flow:
    name: str
    origin: str = ""
    # Declared PARAMETERS: every value typed into a form field, with what was
    # recorded as its default. workflow-use extracts variables from forms the
    # same way; what it buys here is that replaying with a different project
    # name is a run_flow argument rather than a re-record.
    vars: dict = field(default_factory=dict)
    # The state this flow EXPECTS TO START FROM, checked before step 0. Nothing
    # else in this space has these -- ReUseIt's condition checks are per-step
    # and judged by a model on a screenshot; ours are exact, because the page
    # declares the things we check. Without it a flow run against the wrong
    # starting state fails deep inside with a confusing message about one
    # element, instead of saying the app is not where the flow begins.
    require: dict = field(default_factory=dict)
    steps: list = field(default_factory=list)
    recorded_at: str = ""
    viewport: Optional[dict] = None
    # The document's declared language AT RECORD TIME. Read, like `viewport`,
    # only to name a CAUSE when a target cannot be resolved -- the descriptor's
    # identity rung is the accessible name, so a localised render invalidates
    # every step at once and "no element matches" is then true and useless.
    # A flow recorded before this existed carries "" and makes no claim.
    lang: str = ""
    schema: int = SCHEMA

    def to_json(self) -> dict:
        d = {
            "schema": self.schema, "name": self.name, "origin": self.origin,
            "recorded_at": self.recorded_at, "viewport": self.viewport,
        }
        if self.lang:
            d["lang"] = self.lang
        if self.vars:
            d["vars"] = self.vars
        if self.require:
            d["require"] = self.require
        d["steps"] = [s.to_json() for s in self.steps]
        return d

    @staticmethod
    def from_json(d: dict) -> "Flow":
        got = int(d.get("schema") or 0)
        if got != SCHEMA:
            # A silently-accepted older file would replay with fields the
            # runner no longer reads -- the shape of every stale-contract bug
            # in #30. Refuse and say both numbers, like the 4001 close code.
            raise ValueError(
                f"flow file schema {got} but this build reads schema {SCHEMA} — "
                f"re-record it, or edit the file to the current shape")
        validate_expect(f"flow {d.get('name')!r} require", d.get("require"))
        return Flow(name=d.get("name") or "", origin=d.get("origin") or "",
                    recorded_at=d.get("recorded_at") or "",
                    viewport=d.get("viewport"), lang=d.get("lang") or "",
                    vars=d.get("vars") or {}, require=d.get("require") or {},
                    steps=[Step.from_json(s) for s in d.get("steps") or []])


def save(flow: Flow, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(flow.to_json(), indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return path


def load(path: Path) -> Flow:
    return Flow.from_json(json.loads(Path(path).read_text(encoding="utf-8")))


# --------------------------------------------------------------------------
# Input paths. A step may carry several targets -- fill_form maps many refs to
# many values -- so each is addressed by where it sits in the input.
#   "ref"        -> input["ref"]
#   "fields.2"   -> input["fields"][2]["ref"]
# --------------------------------------------------------------------------
def get_ref(inp: dict, path: str):
    if path.startswith("fields."):
        i = int(path.split(".", 1)[1])
        f = (inp.get("fields") or [])[i]
        for k in FIELD_REF_KEYS:
            if f.get(k) is not None:
                return f[k]
        return None
    return inp.get(path)


def set_ref(inp: dict, path: str, ref: str) -> None:
    if path.startswith("fields."):
        i = int(path.split(".", 1)[1])
        fields_ = [dict(f) for f in (inp.get("fields") or [])]
        for k in FIELD_REF_KEYS:
            fields_[i].pop(k, None)
        fields_[i]["ref"] = ref
        inp["fields"] = fields_
        return
    inp[path] = ref


VAR_RE = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")


def resolve_vars(obj, values: dict):
    """Substitute {{name}} throughout a step's input. -> (input, missing names).

    Walks the structure rather than knowing where values live, so it covers
    form_input's `value`, fill_form's `fields[].value` and computer's `text`
    with no third list of locations to keep in sync (#21) -- the same shape as
    secrets.resolve, which runs after it.
    """
    missing: list = []

    def walk(v):
        if isinstance(v, str):
            def sub(m):
                nm = m.group(1)
                if nm not in values:
                    missing.append(nm)
                    return m.group(0)
                return str(values[nm])
            return VAR_RE.sub(sub, v)
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v

    return walk(obj), missing


def get_value(inp: dict, path: str):
    if path.startswith("fields."):
        i = int(path.split(".", 1)[1])
        return ((inp.get("fields") or [])[i] or {}).get("value")
    return inp.get("value")


def set_value(inp: dict, path: str, v) -> None:
    """Write the VALUE that goes with the target at `path`.

    form_input carries one `value`; fill_form carries one per field entry.
    Kept beside set_ref so a caller never has to know which shape it has.
    """
    if path.startswith("fields."):
        i = int(path.split(".", 1)[1])
        fields_ = [dict(f) for f in (inp.get("fields") or [])]
        fields_[i]["value"] = v
        inp["fields"] = fields_
        return
    inp["value"] = v


def value_paths(name: str, inp: dict) -> list:
    """Every place in this call's input that carries a VALUE the user typed.

    SEPARATE FROM `ref_paths` ON PURPOSE, and the lack of that separation was a
    secret-leak defect. `ref_paths` answers "which inputs name a per-document
    handle", which is a STALENESS question, and `FIELD_REF_KEYS` deliberately
    excludes `selector` because #48/B12 established that a selector is resolved
    at dispatch time and is therefore the ref-FREE way to address a form.

    The recorder was using that same answer to decide which fields to
    TYPE-CHECK for a password. So a field addressed by `selector` -- which
    `fill_form` advertises, and which the batch guard was taught to respect --
    produced no path at all: never type-checked, never redacted, never
    parameterised. MEASURED: a recording made that way wrote a live credential
    in PLAINTEXT into seven flow files. One function was answering two
    different questions, which is #21 in reverse.

    This names every value-bearing position regardless of HOW the element is
    addressed, so the caller can decide what to do about one it cannot check.
    """
    out = ["value"] if (inp or {}).get("value") is not None else []
    if name == "fill_form":
        for i, f in enumerate((inp or {}).get("fields") or []):
            if isinstance(f, dict) and f.get("value") is not None:
                out.append(f"fields.{i}")
    return out


def ref_paths(name: str, inp: dict) -> list:
    """Every place in this call's input that names a per-document handle."""
    out = [k for k in REF_KEYS if (inp or {}).get(k) is not None]
    if name == "fill_form":
        for i, f in enumerate((inp or {}).get("fields") or []):
            if isinstance(f, dict) and any(f.get(k) is not None for k in FIELD_REF_KEYS):
                out.append(f"fields.{i}")
    return out
