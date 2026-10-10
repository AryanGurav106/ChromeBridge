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
}
COMPUTER_OBSERVES = {"screenshot", "wait", "zoom"}


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


@dataclass
class Step:
    name: str                                   # the MCP tool to call
    input: dict                                 # its arguments, refs removed
    targets: dict = field(default_factory=dict)  # input path -> descriptor
    expect: dict = field(default_factory=dict)   # checked LIVE, never healed
    on_fail: str = "ask"                        # fail | heal | ask
    note: str = ""                              # why this step is here

    def to_json(self) -> dict:
        d = {"name": self.name, "input": self.input}
        if self.targets:
            d["targets"] = self.targets
        if self.expect:
            d["expect"] = self.expect
        d["on_fail"] = self.on_fail
        if self.note:
            d["note"] = self.note
        return d

    @staticmethod
    def from_json(d: dict) -> "Step":
        return Step(name=d["name"], input=d.get("input") or {},
                    targets=d.get("targets") or {}, expect=d.get("expect") or {},
                    on_fail=d.get("on_fail") or "ask", note=d.get("note") or "")


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
    schema: int = SCHEMA

    def to_json(self) -> dict:
        d = {
            "schema": self.schema, "name": self.name, "origin": self.origin,
            "recorded_at": self.recorded_at, "viewport": self.viewport,
        }
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
        return Flow(name=d.get("name") or "", origin=d.get("origin") or "",
                    recorded_at=d.get("recorded_at") or "",
                    viewport=d.get("viewport"),
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


def ref_paths(name: str, inp: dict) -> list:
    """Every place in this call's input that names a per-document handle."""
    out = [k for k in REF_KEYS if (inp or {}).get(k) is not None]
    if name == "fill_form":
        for i, f in enumerate((inp or {}).get("fields") or []):
            if isinstance(f, dict) and any(f.get(k) is not None for k in FIELD_REF_KEYS):
                out.append(f"fields.{i}")
    return out
