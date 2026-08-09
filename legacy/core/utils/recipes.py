"""Local trajectory / site-recipe store.

A "recipe" is a recorded sequence of tool calls that completed a task. The user
saves it with /save NAME after a successful run; later they /run NAME and the
exact tool sequence replays through the bridge — no LLM in the loop, near-
instant on repeat tasks. Claude-in-Chrome cannot do this: they have no
per-user/per-site memory.

This first version is manual (record-by-name + replay-by-name). Automatic
recording with parameterization is a natural extension; the schema here is
forward-compatible with it (each step carries `args` separately so swapping in
new field values for the next run is trivial).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Optional


def _safe(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_\- ]+", "", (name or "").strip()).strip().replace(" ", "_")
    return s.lower() or "recipe"


class RecipeStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        return self.root / f"{_safe(name)}.json"

    def list(self) -> list[dict]:
        out = []
        for p in sorted(self.root.glob("*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                out.append({
                    "name": d.get("name") or p.stem,
                    "path": str(p),
                    "task": d.get("task"),
                    "url": d.get("url"),
                    "steps": len(d.get("steps", [])),
                    "saved_at": d.get("saved_at"),
                })
            except Exception:
                pass
        return out

    def load(self, name: str) -> Optional[dict]:
        p = self.path(name)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save(self, name: str, payload: dict) -> str:
        p = self.path(name)
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(p)

    def delete(self, name: str) -> bool:
        p = self.path(name)
        if p.exists():
            p.unlink()
            return True
        return False


# ---------- trajectory extraction --------------------------------------
# Pulls a compact, replayable "steps" list out of a pydantic-ai RunResult.
# We only keep tool calls (not the model's internal text). Each entry is:
#   {"tool": "<name>", "args": {...}}
# At replay time we map tool name -> driver method and call it.

_REPLAY_MAP_EXTENSION = {
    "click_tool":           ("click",          ["selector", "trusted"]),
    "enter_text_tool":      ("enter_text",     ["selector", "text", "trusted"]),
    "press_key_combination_tool": ("press_keys", ["keys"]),
    "open_url_tool":        ("open_url",       ["url"]),
    "fill_form_tool":       ("fill_form",      ["fields", "submit_mmid", "submit_trusted"]),
    "batch_actions_tool":   ("batch_actions",  ["steps", "stop_on_fail"]),
    # Observations are skipped at replay time — recipes are about acting,
    # not re-fetching DOM. The agent's job is selecting WHICH recipe; the
    # recipe's job is to execute it.
}


def extract_steps_from_messages(messages: list) -> list[dict]:
    """Walk a pydantic-ai message list and emit a list of (tool, args) for the
    action tools we replay (clicks, types, fill_form, batch_actions). Non-action
    tools (get_dom_*, analyze_screen) are skipped."""
    steps: list[dict] = []
    for m in messages:
        for part in getattr(m, "parts", []) or []:
            if getattr(part, "part_kind", "") != "tool-call":
                continue
            name = getattr(part, "tool_name", "")
            if name not in _REPLAY_MAP_EXTENSION:
                continue
            args = None
            try:
                if hasattr(part, "args"):
                    a = part.args
                    if hasattr(a, "args_dict") and a.args_dict:
                        args = a.args_dict
                    elif hasattr(a, "args_json") and a.args_json:
                        args = json.loads(a.args_json)
            except Exception:
                args = None
            if not isinstance(args, dict):
                continue
            steps.append({"tool": name, "args": args})
    return steps


async def replay(driver, recipe: dict) -> list[dict]:
    """Replay a recipe's steps through an ExtensionDriver. Returns per-step
    outcomes. Stops on a hard failure of an action step."""
    results = []
    steps = recipe.get("steps", [])
    for s in steps:
        tool = s.get("tool")
        args = s.get("args", {}) or {}
        if tool not in _REPLAY_MAP_EXTENSION:
            results.append({"tool": tool, "ok": False, "msg": "unknown tool in recipe"})
            break
        method_name, allowed = _REPLAY_MAP_EXTENSION[tool]
        kwargs = {k: args[k] for k in allowed if k in args}
        try:
            fn = getattr(driver, method_name)
            res = await fn(**kwargs)
            results.append({"tool": tool, "ok": True, "result": str(res)[:200]})
        except Exception as e:
            results.append({"tool": tool, "ok": False, "msg": str(e)})
            break
    return results


def build_recipe(name: str, task: str, url: str, steps: list[dict]) -> dict:
    return {
        "name": _safe(name),
        "task": task,
        "url": url,
        "steps": steps,
        "saved_at": int(time.time()),
        "schema_version": 1,
    }
