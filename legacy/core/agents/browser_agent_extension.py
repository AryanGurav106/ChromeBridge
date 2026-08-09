"""Extension-mode Browser Agent wiring.

Same system prompt, same `mmid` mental model, same tools — but every action is
routed through the Chrome extension over the local WebSocket bridge instead of
launching a Playwright Chromium. This lets the agent drive the user's
already-open Chrome with their real profile.

The Playwright-mode wiring in `browser_agent.py` is intentionally untouched.
"""

from __future__ import annotations

import os
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings

from core.agents.browser_agent import BA_SYS_PROMPT
from core.bridge.driver import ExtensionDriver
from core.skills.hashicorp import get_keys, get_secret
from core.skills.marked_screenshot import _draw_marks, _MAX_MARKS
from core.skills.pdf_text_extractor import extract_text_from_pdf
from core.utils.action_memory import ActionMemory
from core.utils.logger import Logger
from core.utils.timing import TimingTracker
from core.utils.vision import describe_image

logger = Logger()


class BA_Deps_Ext(BaseModel):
    """Extension-mode deps. Mirrors BA_Deps but with an ExtensionDriver."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    current_step: str
    driver: ExtensionDriver
    vault_ns: str = "default"
    mem: Any = Field(default_factory=ActionMemory)
    tt: Any = Field(default_factory=TimingTracker)


def build_browser_agent_via_extension(model, explainer_agent: Agent) -> Agent:
    """Build the Browser Agent with tools that act through the extension bridge."""

    BA_agent = Agent(
        model=model,
        system_prompt=BA_SYS_PROMPT,
        deps_type=BA_Deps_Ext,
        name="Browser Agent (extension mode)",
        retries=3,
        model_settings=ModelSettings(temperature=0.5),
    )

    # Helper that snapshots bridge time before/after a tool body so per-tool
    # timing can attribute the WS portion precisely.
    def _tt_begin(ctx: RunContext[BA_Deps_Ext], name: str):
        idx = ctx.deps.tt.begin(name)
        bm0 = ctx.deps.driver.bridge.total_bridge_ms
        return idx, bm0

    def _tt_end(ctx: RunContext[BA_Deps_Ext], idx: int, bm0: float):
        ctx.deps.tt.end(idx, bridge_ms=ctx.deps.driver.bridge.total_bridge_ms - bm0)

    # Persist tool outputs to disk + log a preview, so "the model said X wasn't
    # there" is debuggable — you can read what the model actually received.
    def _dump_tool_output(ctx: RunContext[BA_Deps_Ext], name: str, content: str) -> None:
        try:
            path = os.path.join(ctx.deps.driver.job_dir, f"last_{name}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            # ALSO keep a sequential copy — last_*.txt is overwritten on every
            # call, which loses the history needed to debug a failed run. The
            # numbered trace_NNN_* files preserve every observation in order.
            seq = getattr(ctx.deps.driver, "_dump_seq", 0) + 1
            ctx.deps.driver._dump_seq = seq
            spath = os.path.join(ctx.deps.driver.job_dir, f"trace_{seq:03d}_{name}.txt")
            with open(spath, "w", encoding="utf-8") as f:
                f.write(content)
            preview = content[:500].replace("\n", " \\n ")
            logger.info(
                f"[{name}] {len(content)} chars saved to {path}\n"
                f"[{name}] preview: {preview!r}"
            )
        except Exception as e:
            logger.warn(f"[{name}] dump failed: {e}")

    # -- observation -------------------------------------------------------
    @BA_agent.tool
    async def get_dom_text(ctx: RunContext[BA_Deps_Ext], prompt: str) -> str:
        idx, bm0 = _tt_begin(ctx, "get_dom_text")
        try:
            text = await ctx.deps.driver.get_dom_text()
            n = ctx.deps.mem.record("obs:get_dom_text")
            out = text + ctx.deps.mem.observe_note("get_dom_text", n)
            _dump_tool_output(ctx, "get_dom_text", out)
            return out
        finally:
            _tt_end(ctx, idx, bm0)

    @BA_agent.tool
    async def get_dom_fields(ctx: RunContext[BA_Deps_Ext], prompt: str) -> str:
        # Extension mode uses the deterministic interactive-elements listing
        # (no separate AX-tree + Explainer pipeline yet). Same mmid space.
        idx, bm0 = _tt_begin(ctx, "get_dom_fields")
        try:
            text = await ctx.deps.driver.get_dom_fields(ctx.deps.current_step, prompt)
            n = ctx.deps.mem.record("obs:get_dom_fields")
            out = text + ctx.deps.mem.observe_note("get_dom_fields", n)
            _dump_tool_output(ctx, "get_dom_fields", out)
            return out
        finally:
            _tt_end(ctx, idx, bm0)

    @BA_agent.tool
    async def get_interactive_elements(ctx: RunContext[BA_Deps_Ext], only_clickable: bool = False) -> str:
        idx, bm0 = _tt_begin(ctx, "get_interactive_elements")
        try:
            text = await ctx.deps.driver.get_interactive_elements(only_clickable=only_clickable)
            n = ctx.deps.mem.record("obs:get_interactive_elements")
            out = text + ctx.deps.mem.observe_note("get_interactive_elements", n)
            _dump_tool_output(ctx, "get_interactive_elements", out)
            return out
        finally:
            _tt_end(ctx, idx, bm0)

    @BA_agent.tool
    async def get_url(ctx: RunContext[BA_Deps_Ext]) -> str:
        idx, bm0 = _tt_begin(ctx, "get_url")
        try:
            return await ctx.deps.driver.get_url()
        finally:
            _tt_end(ctx, idx, bm0)

    # -- actions -----------------------------------------------------------
    @BA_agent.tool
    async def click_tool(ctx: RunContext[BA_Deps_Ext], selector: str,
                         trusted: bool = False) -> str:
        """Click the element matched by `selector` (use [mmid='N']).
        Set trusted=True ONLY when normal clicks don't work — login buttons,
        payment, file pickers, OAuth/"Continue with Google" popups, or a click
        that previously had no detectable effect. Trusted clicks attach Chrome's
        debugger and surface the yellow "Agentic Browser Bridge is debugging
        this browser" infobar for that tab — that's expected. Do not pass any
        wait/delay parameter; the harness already auto-waits.

        TIME-SAVER: when the click changes the page (modal/menu opened,
        navigation), the FRESH element listing is attached to the result
        automatically — act on it directly; do NOT call get_dom_fields again.
        """
        import time as _t
        t0 = _t.monotonic()
        idx, bm0 = _tt_begin(ctx, "click_tool")
        t1 = _t.monotonic()
        try:
            result = await ctx.deps.driver.click(
                selector, wait_before_execution=0.0, trusted=trusted,
            )
            t2 = _t.monotonic()
            n = ctx.deps.mem.record(f"click:{selector}")
            had_effect = "WARNING" not in result
            ret = result + ctx.deps.mem.click_note(selector, n, had_effect)
            # AUTO-OBSERVE: the click already told us the page changed — fetching
            # the listing here (~30ms bridge call) saves the model a whole
            # observe round-trip (LLM request + re-sent context ≈ 2s each).
            if "DOM changed" in result or "navigated" in result.lower():
                try:
                    import asyncio as _aio
                    await _aio.sleep(0.35)   # let modal/menu mount animations finish
                    listing = await ctx.deps.driver.get_dom_fields(ctx.deps.current_step, "")
                    ret += (
                        "\n\n[AUTO-OBSERVED — fresh element listing AFTER this click. "
                        "Act on it directly (mmids below are current); do NOT call get_dom_fields:]\n"
                        + listing
                    )
                except Exception:
                    pass
            _dump_tool_output(ctx, "click_tool", f"selector={selector} trusted={trusted}\n{ret}")
            t3 = _t.monotonic()
            logger.info(
                f"[click_tool] tt_begin={1000*(t1-t0):.0f}ms "
                f"driver_click={1000*(t2-t1):.0f}ms "
                f"post={1000*(t3-t2):.0f}ms"
            )
            return ret
        finally:
            _tt_end(ctx, idx, bm0)

    @BA_agent.tool
    async def enter_text_tool(ctx: RunContext[BA_Deps_Ext], selector: str,
                              text: str, trusted: bool = False) -> str:
        """Type text into an element. Set trusted=True for login/password/payment
        fields or any input that rejects synthetic events. Trusted typing
        attaches Chrome's debugger (yellow infobar) and uses real keyboard
        events via CDP Input.insertText."""
        idx, bm0 = _tt_begin(ctx, "enter_text_tool")
        try:
            result = await ctx.deps.driver.enter_text(selector, text, trusted=trusted)
            _dump_tool_output(ctx, "enter_text_tool", f"selector={selector} text={text!r} trusted={trusted}\n{result}")
            return result
        finally:
            _tt_end(ctx, idx, bm0)

    @BA_agent.tool
    async def press_key_combination_tool(ctx: RunContext[BA_Deps_Ext], keys: str) -> str:
        idx, bm0 = _tt_begin(ctx, "press_key_combination_tool")
        try:
            return await ctx.deps.driver.press_keys(keys)
        finally:
            _tt_end(ctx, idx, bm0)

    @BA_agent.tool
    async def open_url_tool(ctx: RunContext[BA_Deps_Ext], url: str, timeout: int = 10) -> str:
        idx, bm0 = _tt_begin(ctx, "open_url_tool")
        try:
            return await ctx.deps.driver.open_url(url, timeout=timeout)
        finally:
            _tt_end(ctx, idx, bm0)

    @BA_agent.tool
    async def fill_form_tool(
        ctx: RunContext[BA_Deps_Ext],
        fields: list[dict],
        submit_mmid: str | None = None,
        submit_trusted: bool = False,
    ) -> str:
        """STRONGLY PREFERRED for any multi-field form. One call, one round-trip,
        atomically types all fields with per-field read-back verification, and
        clicks submit at the end.

        fields: list of dicts, each {"selector": "[mmid='42']", "text": "value",
                "trusted": false (optional)}.
                CRITICAL — include every field that needs input, ESPECIALLY:
                  - every (required) field, and
                  - every (unselected) combobox (placeholder text like "Select X..."
                    means nothing has been picked yet — most forms silently fail
                    submit if these are left blank, with no `*` to warn you).
                For comboboxes/selects, `text` should be the option label to pick
                (e.g. "Series A"), not a free-form value.
        submit_mmid: selector of the submit button to click after fields are filled
                     (e.g. "[mmid='99']"). The submit button is often at the
                     BOTTOM of the dialog and may be tagged "(below-fold; modal
                     will auto-scroll to it on action)" — INCLUDE IT ANYWAY,
                     the harness will scroll to it. Look for buttons labeled
                     Submit/Save/Add X/Create/Confirm/Done in section=dialog.
                     If you omit submit_mmid, the harness auto-detects the
                     submit button by label and clicks it for you — but
                     including it explicitly is more reliable.
        submit_trusted: usually leave False — the harness AUTO-ESCALATES to
                        trusted input automatically when an untrusted submit
                        click doesn't close the modal. Only pass True if you
                        know upfront the button requires trusted input.

        Use this instead of multiple enter_text_tool calls — it is roughly
        10x faster (1 LLM turn + 1 round-trip vs N turns + N round-trips) and
        avoids re-observing between fields.

        IF submit fails: the result includes both "Validation errors visible:"
        (what the page is complaining about) AND "UNFILLED fields in dialog:"
        (concrete selectors you missed, with their (unselected)/(required-empty)
        tag and label). When you see those, RETRY fill_form once including the
        listed selectors with sensible values — don't conclude the task failed.
        """
        idx, bm0 = _tt_begin(ctx, "fill_form_tool")
        try:
            # NORMALIZE the field schema. Models occasionally invent key names
            # ({"mmid": N, "value": ...} instead of {"selector", "text"}) — raw
            # undefined then reaches chrome.scripting.executeScript args and
            # blows up with "Value is unserializable". Accept the common
            # synonyms, wrap bare mmid numbers, and reject anything else with
            # an instructive message instead of a cryptic Chrome error.
            norm_fields, bad = [], []
            for f in (fields or []):
                if not isinstance(f, dict):
                    bad.append(repr(f)[:80]); continue
                sel = f.get("selector")
                if not sel and f.get("mmid") is not None:
                    sel = f"[mmid='{f['mmid']}']"
                if sel is not None:
                    sel = str(sel).strip()
                    if sel.isdigit():
                        sel = f"[mmid='{sel}']"
                txt = f.get("text")
                if txt is None:
                    txt = f.get("value", f.get("option"))
                if not sel or txt is None:
                    bad.append(str({k: str(v)[:30] for k, v in f.items()})[:100]); continue
                nf = {"selector": sel, "text": str(txt)}
                if f.get("trusted"):
                    nf["trusted"] = True
                norm_fields.append(nf)
            if bad:
                return (
                    f"fill_form_tool REJECTED — {len(bad)} field(s) use wrong keys: {'; '.join(bad[:4])}. "
                    "Each field MUST be {\"selector\": \"[mmid='N']\", \"text\": \"value to type or option label to pick\"}. "
                    "Fix the field dicts and call fill_form_tool again."
                )
            sm = submit_mmid
            if sm is not None:
                sm = str(sm).strip()
                if sm.isdigit():
                    sm = f"[mmid='{sm}']"
            return await ctx.deps.driver.fill_form(
                fields=norm_fields, submit_mmid=sm, submit_trusted=submit_trusted,
            )
        finally:
            _tt_end(ctx, idx, bm0)

    @BA_agent.tool
    async def batch_actions_tool(
        ctx: RunContext[BA_Deps_Ext],
        steps: list[dict],
        stop_on_fail: bool = True,
    ) -> str:
        """Run a sequence of actions in ONE round-trip. Use for any multi-step
        operation on the same page state (open a menu → click an item → confirm).

        steps: list of dicts, one of:
          {"op": "click", "selector": "[mmid='N']", "trusted": false}
          {"op": "type",  "selector": "[mmid='N']", "text": "...", "trusted": false}
          {"op": "press", "combo": "Enter" | "Control+A" | "Shift+Tab"}
          {"op": "wait",  "ms": 200}

        Prefer this over chained click_tool/enter_text_tool calls — it cuts
        latency by ~3-5x because there is one model turn for the whole sequence
        instead of one turn per action. For pure form filling, use
        fill_form_tool instead — it is more specialized.
        """
        idx, bm0 = _tt_begin(ctx, "batch_actions_tool")
        try:
            return await ctx.deps.driver.batch_actions(steps=steps, stop_on_fail=stop_on_fail)
        finally:
            _tt_end(ctx, idx, bm0)

    # -- visual grounding --------------------------------------------------
    @BA_agent.tool
    async def analyze_screen(ctx: RunContext[BA_Deps_Ext], prompt: str) -> str:
        """Set-of-Mark: screenshot the current tab, burn numbered mmid boxes,
        ask the VLM which mmid to act on."""
        idx_tt, bm0 = _tt_begin(ctx, "analyze_screen")
        try:
            return await _analyze_screen_impl(ctx, prompt)
        finally:
            _tt_end(ctx, idx_tt, bm0)

    async def _analyze_screen_impl(ctx: RunContext[BA_Deps_Ext], prompt: str) -> str:
        driver = ctx.deps.driver
        elements = await driver.list_interactive_elements_raw()
        if not elements:
            return "No visible interactive elements were found to mark."

        png = await driver.screenshot_png_bytes()

        if len(elements) > _MAX_MARKS:
            elements = sorted(elements, key=lambda e: e["w"] * e["h"], reverse=True)[:_MAX_MARKS]

        out_path = os.path.join(driver.job_dir, f"som_{int(time.time())}.png")
        try:
            _draw_marks(png, elements, dpr=1.0, out_path=out_path)
        except Exception as e:
            logger.error(f"Failed to render SoM overlay: {e}")
            return f"Failed to render marked screenshot: {e}"

        legend = "\n".join(
            f"  [{e['mmid']}] {e['tag']}" + (f" — \"{e['label']}\"" if e.get("label") else "")
            for e in elements
        )
        vlm_prompt = (
            "You are looking at a screenshot of a web page. Each interactive element is "
            "outlined with a red box labelled by its numeric element id (mmid).\n\n"
            f"Current step: {ctx.deps.current_step}\n"
            f"What I need: {prompt}\n\n"
            "Element legend (id -> tag/label):\n"
            f"{legend}\n\n"
            "Using the visual layout, answer concisely:\n"
            "1) Which mmid(s) are most relevant, and why.\n"
            "2) The exact mmid to act on next (state it as mmid=N).\n"
            "3) Any blocking overlay/modal/cookie-banner visible, and which mmid dismisses it.\n"
            "Refer to elements only by their mmid number."
        )
        analysis = await describe_image(out_path, vlm_prompt)
        return f"{analysis}\n\n[Set-of-Mark overlay saved to {out_path}; {len(elements)} elements marked.]"

    # -- auxiliary (browser-independent) -----------------------------------
    @BA_agent.tool
    async def extract_text_from_pdf_tool(ctx: RunContext[BA_Deps_Ext], pdf_url: str) -> str:
        return await extract_text_from_pdf(bc=ctx.deps.driver, pdf_url=pdf_url)

    @BA_agent.tool
    async def get_keys_tool(ctx: RunContext[BA_Deps_Ext]) -> str:
        return await get_keys(ctx.deps.vault_ns)

    @BA_agent.tool
    async def get_secret_tool(ctx: RunContext[BA_Deps_Ext], key: str) -> str:
        return await get_secret(vault_ns=ctx.deps.vault_ns, key=key)

    return BA_agent
