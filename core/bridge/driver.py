"""Extension-backed driver: same logical operations as the Playwright skills,
but executed by the Chrome extension on the user's real browser.

This is the bridge's Python-side API. The agent's tools call into a driver
instance; the PlaywrightDriver wraps the existing skills, the ExtensionDriver
forwards to the WebSocket bridge. Both have the same async surface so the
browser agent itself doesn't care which one is in use.
"""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Optional

from config import PROJECT_SOURCE_ROOT
from core.bridge.server import ExtensionBridge
from core.utils.logger import Logger

logger = Logger()


class ExtensionDriver:
    """Routes the agent's actions through the Chrome extension."""

    def __init__(self, bridge: ExtensionBridge, job_id: str = ""):
        self.bridge = bridge
        self.job_id = job_id
        # mimic PlaywrightManager attributes that the existing skills/marked_screenshot
        # touch, so we can reuse helpers like the Set-of-Mark renderer.
        self.job_ID = job_id
        self.job_dir = os.path.join(PROJECT_SOURCE_ROOT, "temp", f"task_{job_id}") if job_id else os.path.join(PROJECT_SOURCE_ROOT, "temp")
        os.makedirs(self.job_dir, exist_ok=True)

    # ---- observation ------------------------------------------------------
    async def get_dom_text(self) -> str:
        return await self.bridge.call("get_dom_text")

    async def get_interactive_elements(self, only_clickable: bool = False) -> str:
        return await self.bridge.call("get_interactive_elements", only_clickable=only_clickable)

    async def get_dom_fields(self, current_step: str, info: str) -> str:
        """No Explainer / AX tree pipeline through the extension yet — fall back
        to the deterministic interactive-elements listing, which already carries
        mmid + box + clickability and is plenty for solo tasks."""
        return await self.bridge.call("get_interactive_elements")

    async def get_url(self) -> str:
        info = await self.bridge.call("get_url")
        if isinstance(info, dict):
            url = info.get("url", "")
            title = info.get("title", "")
            return f"Current Page: {url}, Title: {title}"
        return str(info)

    # ---- actions ---------------------------------------------------------
    async def click(self, selector: str, wait_before_execution: float = 0.0,
                    trusted: bool = False) -> str:
        if wait_before_execution > 0:
            import asyncio
            await asyncio.sleep(wait_before_execution)
        import time as _t
        _t0 = _t.monotonic()
        result = await self.bridge.call("click", selector=selector, trusted=trusted)
        _elapsed = (_t.monotonic() - _t0) * 1000.0
        _gap = _elapsed - self.bridge.last_call_ms
        if _gap > 30:
            logger.info(
                f"[driver.click] elapsed={_elapsed:.0f}ms bridge={self.bridge.last_call_ms:.0f}ms "
                f"gap={_gap:.0f}ms (post-await scheduling/logging cost)"
            )
        return result

    async def enter_text(self, selector: str, text: str, trusted: bool = False) -> str:
        return await self.bridge.call("enter_text", selector=selector, text=text, trusted=trusted)

    async def detach_debugger(self) -> str:
        """Detach chrome.debugger from all tabs (removes the yellow infobar)."""
        return await self.bridge.call("detach_debugger")

    async def press_keys(self, combo: str) -> str:
        return await self.bridge.call("press_keys", combo=combo)

    async def open_url(self, url: str, timeout: int = 10) -> str:
        return await self.bridge.call("navigate", url=url)

    # ---- visual / vision -------------------------------------------------
    async def screenshot_png_bytes(self) -> bytes:
        b64 = await self.bridge.call("screenshot")
        # Newer extension builds return {dataUrl, cssWidth, cssHeight, dpr} so the
        # server can normalise device px -> CSS px; older ones a bare data URL.
        if isinstance(b64, dict):
            b64 = b64.get("dataUrl") or ""
        # extension returns a data URL or raw base64
        if isinstance(b64, str) and b64.startswith("data:"):
            b64 = b64.split(",", 1)[1]
        return base64.b64decode(b64)

    async def list_interactive_elements_raw(self) -> list[dict]:
        """Structured list (with box, label, clickability) used by the
        Set-of-Mark renderer. The extension returns JSON in `_raw` mode."""
        return await self.bridge.call("get_interactive_elements", structured=True)

    async def page_fingerprint(self) -> dict:
        return await self.bridge.call("page_fingerprint")

    async def deep_inspect(self, labels: list[str]) -> dict:
        """Diagnostic dump: for each label, find DOM nodes whose text matches and
        report tag/role/href/cursor/rect + filter verdicts + nearest clickable
        ancestor. Also dumps the first 200 candidate-interactive elements globally."""
        return await self.bridge.call("deep_inspect", labels=labels)

    # ---- macro tools (S1, S2) -------------------------------------------
    async def fill_form(self, fields: list[dict], submit_mmid: str | None = None,
                        submit_trusted: bool = False) -> str:
        """Atomically type N fields and optionally click submit, in one bridge call."""
        try:
            from core.utils.logger import Logger
            _lg = Logger()
            preview = ", ".join(
                f"{(f.get('selector') or '?')}={(str(f.get('text',''))[:24])!r}"
                for f in (fields or [])
            )
            _lg.info(f"[fill_form] -> {len(fields or [])} field(s) submit_mmid={submit_mmid} submit_trusted={submit_trusted}")
            _lg.info(f"[fill_form] -> params: {preview}")
        except Exception:
            pass
        result = await self.bridge.call(
            "fill_form", fields=fields, submit_mmid=submit_mmid,
            submit_trusted=submit_trusted,
        )
        try:
            head = (str(result).splitlines() or [""])[0]
            _lg.info(f"[fill_form] <- {head}")
        except Exception:
            pass
        # Persist the FULL result (incl. per-field fillDropdown debug traces and
        # submit before/after snapshots) to one file per call — never overwritten,
        # so every run of every task is diagnosable after the fact.
        try:
            self._ff_seq = getattr(self, "_ff_seq", 0) + 1
            fname = f"fill_form_{self._ff_seq:02d}_{time.strftime('%H%M%S')}.txt"
            fpath = os.path.join(self.job_dir, fname)
            pretty = str(result)
            lines = pretty.splitlines()
            if lines and lines[-1].startswith("details="):
                try:
                    detail = json.loads(lines[-1][len("details="):])
                    pretty = "\n".join(lines[:-1]) + "\ndetails=\n" + json.dumps(detail, indent=2, ensure_ascii=False)
                except Exception:
                    pass
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(pretty)
            _lg.info(f"[fill_form] full result + debug trace saved to {fpath}")
        except Exception:
            pass
        # Strip the bulky debug traces from the MODEL-facing string — they are
        # for post-mortem analysis on disk, not for the LLM's context window.
        try:
            lines = str(result).splitlines()
            if lines and lines[-1].startswith("details="):
                detail = json.loads(lines[-1][len("details="):])
                for fld in detail.get("fields", []) or []:
                    fld.pop("dbg", None)
                if isinstance(detail.get("submit"), dict):
                    detail["submit"].pop("dbg", None)
                lines[-1] = "details=" + json.dumps(detail, ensure_ascii=False)
                result = "\n".join(lines)
        except Exception:
            pass
        return result

    async def batch_actions(self, steps: list[dict], stop_on_fail: bool = True) -> str:
        """Run a list of {click/type/press/wait} steps sequentially in one round-trip."""
        return await self.bridge.call("batch_actions", steps=steps, stop_on_fail=stop_on_fail)

    # ---- minimal compatibility shims so existing helpers work -------------
    async def notify_user(self, *args, **kwargs):
        return None  # the extension's own side panel handles user-facing notices

    async def highlight_element(self, *args, **kwargs):
        return None
