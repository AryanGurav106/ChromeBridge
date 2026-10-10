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
    steps: list = field(default_factory=list)
    recorded_at: str = ""
    viewport: Optional[dict] = None
    schema: int = SCHEMA

    def to_json(self) -> dict:
        return {
            "schema": self.schema, "name": self.name, "origin": self.origin,
            "recorded_at": self.recorded_at, "viewport": self.viewport,
            "steps": [s.to_json() for s in self.steps],
        }

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


def ref_paths(name: str, inp: dict) -> list:
    """Every place in this call's input that names a per-document handle."""
    out = [k for k in REF_KEYS if (inp or {}).get(k) is not None]
    if name == "fill_form":
        for i, f in enumerate((inp or {}).get("fields") or []):
            if isinstance(f, dict) and any(f.get(k) is not None for k in FIELD_REF_KEYS):
                out.append(f"fields.{i}")
    return out
