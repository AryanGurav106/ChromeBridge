"""Flat, token-efficient DOM serialization for the browser agent.

Background / why this exists
----------------------------
The original pipeline serialized the enriched accessibility tree with
``str(enhanced_tree)`` — a stringified Python dict. That is the most
token-expensive representation possible (quotes, braces, repeated keys, nesting)
and degrades long-context accuracy.

The 2024-2026 SOTA (Skyvern, browser-use, AgentOccam, Stagehand) converged on a
**flat, indexed, HTML-ish line format** keyed by a stable integer id. Skyvern
measured the exact migration (verbose JSON/dict -> inline HTML lines):
~20-27% fewer tokens, ~11% lower cost/task, +3.9pp task success.

This module does two things:

1. ``flatten_tree`` — walk the enriched AX tree (the dict produced by
   ``__fetch_dom_info``) into a *flat registry*: one dict per element that has an
   ``mmid``. This is the candidate set the filter + grounder operate over.
2. ``serialize_elements`` — render a list of registry elements as compact
   HTML-ish lines, e.g.::

       [114]<button "Sign in">
       [115]<input type=text placeholder="Email" name=q>
       [210]<a "Pricing"> (offscreen)
       *[233]<button "Accept cookies"> (occluded)

   ``*`` marks elements newly appeared since the previous snapshot (delta cue,
   browser-use style); ``(occluded)`` / ``(offscreen)`` come from the geometry
   signals already computed in the JS enrichment pass.
"""

from typing import Any, Iterable, Optional

# Attributes worth surfacing on an element line, in priority order for the label.
_LABEL_KEYS = ("name", "aria-label", "placeholder", "text", "description", "title")

# Tags that are inherently actionable; used to decide whether a node is worth
# emitting even when it carries little text.
_INTERACTIVE_TAGS = {"input", "button", "a", "select", "textarea", "option"}


def _clean(value: Any, limit: int = 80) -> str:
    """Collapse whitespace and clip a value to a token-friendly length."""
    if value is None:
        return ""
    s = str(value).replace("\n", " ").replace("\r", " ")
    s = " ".join(s.split())
    if len(s) > limit:
        s = s[: limit - 1].rstrip() + "..."
    return s


def _best_label(node: dict[str, Any]) -> str:
    """Pick the most informative human-readable label for an element."""
    for key in _LABEL_KEYS:
        val = node.get(key)
        if val and str(val).strip():
            return _clean(val)
    return ""


def flatten_tree(tree: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten the enriched AX tree into a list of element records (one per mmid).

    Each record keeps only the fields the filter/grounder/serializer need, so the
    downstream stages never touch the heavy nested structure again.
    """
    if not tree:
        return []

    out: list[dict[str, Any]] = []
    seen: set[int] = set()

    def visit(node: Any):
        if not isinstance(node, dict):
            return
        mmid = node.get("mmid")
        if mmid is not None:
            try:
                mmid_int = int(mmid)
            except (TypeError, ValueError):
                mmid_int = None
            if mmid_int is not None and mmid_int not in seen:
                seen.add(mmid_int)
                out.append(_to_record(node, mmid_int))
        for child in node.get("children", []) or []:
            visit(child)

    visit(tree)
    return out


def _to_record(node: dict[str, Any], mmid: int) -> dict[str, Any]:
    """Project a raw AX node onto a compact, serialization-ready record."""
    tag = (node.get("tag") or node.get("role") or "div") or "div"
    role = node.get("role")
    label = _best_label(node)

    box = node.get("box") or {}
    record: dict[str, Any] = {
        "mmid": mmid,
        "tag": str(tag).lower(),
        "role": str(role).lower() if role else None,
        "label": label,
        # geometry / visibility signals (already computed in the JS pass)
        "visible": bool(node.get("visible", True)),
        "in_viewport": bool(node.get("in_viewport", True)),
        "clickable_at_point": node.get("clickable_at_point"),
        "is_clickable": bool(node.get("is_clickable", False)),
        "box": {
            "x": box.get("x"),
            "y": box.get("y"),
            "w": box.get("w"),
            "h": box.get("h"),
        } if box else None,
        # input specifics
        "type": node.get("tag_type") or node.get("type"),
        "placeholder": node.get("placeholder"),
        "aria_label": node.get("aria-label"),
        "name": node.get("name"),
        # extra haystack material for the filter (kept out of the serialized line)
        "class": _clean(node.get("class"), 120),
        "testid": node.get("data-testid") or node.get("test-id"),
    }

    # carry select <option> / listbox children compactly (used by the agent to choose)
    options = node.get("options")
    if isinstance(options, list) and options:
        record["options"] = [
            {"mmid": o.get("mmid"), "text": _clean(o.get("text"), 40), "value": o.get("value")}
            for o in options[:25]
        ]
    return record


def is_interactive(record: dict[str, Any]) -> bool:
    """Whether a flattened record is something the agent can act on."""
    if record["tag"] in _INTERACTIVE_TAGS:
        return True
    if record.get("is_clickable"):
        return True
    role = record.get("role") or ""
    if role in {
        "button", "link", "menuitem", "menuitemcheckbox", "menuitemradio",
        "tab", "checkbox", "radio", "switch", "option", "combobox",
        "searchbox", "textbox", "slider", "spinbutton",
    }:
        return True
    return False


def _attrs_for_line(r: dict[str, Any]) -> str:
    """Build the inline attribute string for a serialized element line."""
    parts: list[str] = []
    if r["tag"] == "input" and r.get("type"):
        parts.append(f'type={r["type"]}')
    if r.get("placeholder"):
        parts.append(f'placeholder="{_clean(r["placeholder"], 40)}"')
    # role only when it adds information beyond the tag
    role = r.get("role")
    if role and role != r["tag"] and role not in ("generic", "none"):
        parts.append(f"role={role}")
    return (" " + " ".join(parts)) if parts else ""


def serialize_element_line(r: dict[str, Any], new: bool = False) -> str:
    """Render a single element as one HTML-ish line."""
    label = r.get("label") or ""
    label_str = f' "{label}"' if label else ""
    flags = []
    if not r.get("in_viewport", True):
        flags.append("offscreen")
    # clickable_at_point is None when not measured; only flag a definite False
    if r.get("clickable_at_point") is False and r.get("in_viewport", True):
        flags.append("occluded")
    flag_str = (" (" + ", ".join(flags) + ")") if flags else ""
    prefix = "*" if new else ""
    return f'{prefix}[{r["mmid"]}]<{r["tag"]}{_attrs_for_line(r)}{label_str}>{flag_str}'


def serialize_elements(
    elements: Iterable[dict[str, Any]],
    new_mmids: Optional[set[int]] = None,
    include_options: bool = True,
) -> str:
    """Render an iterable of element records as compact HTML-ish lines.

    ``new_mmids`` are prefixed with ``*`` to cue the model to newly-appeared
    elements (cheap delta signal). Returns a newline-joined string.
    """
    new_mmids = new_mmids or set()
    lines: list[str] = []
    for r in elements:
        lines.append(serialize_element_line(r, new=r["mmid"] in new_mmids))
        if include_options and r.get("options"):
            for o in r["options"]:
                if o.get("mmid"):
                    lines.append(f'    [{o["mmid"]}]<option "{o.get("text", "")}">')
    return "\n".join(lines)
