"""The Browser Agent.

This is the executor agent: given a plan + the current step, it drives the live
browser through a set of tools (skills) — navigating, reading the DOM, clicking,
typing, searching, extracting PDF text, and (optionally) fetching credentials.

`build_browser_agent()` wires the agent the same way the original orchestrator
did (which is the correct wiring — notably `get_dom_fields` forwards the request
prompt and the Explainer agent), so the agent works standalone.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings

from core.utils.action_memory import ActionMemory

from core.browser_manager import PlaywrightManager
from core.skills.click_using_selector import click
from core.skills.enter_text_using_selector import entertext, EnterTextEntry
from core.skills.get_dom_with_content_type import get_dom_field_func, get_dom_texts_func
from core.skills.get_url import geturl
from core.skills.interactive_elements import get_interactive_elements_func
from core.skills.marked_screenshot import analyze_marked_screen
from core.skills.hashicorp import get_keys, get_secret
from core.skills.open_url import openurl
from core.skills.pdf_text_extractor import extract_text_from_pdf
from core.skills.press_key_combination import press_key_combination


class BA_Deps(BaseModel):
    """Per-run dependencies handed to the browser agent's tools."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    current_step: str
    pm: PlaywrightManager
    vault_ns: str = "default"
    # Per-task self-correction memory (counts repeated actions to break loops).
    mem: Any = Field(default_factory=ActionMemory)


# System prompt for the Browser Agent (verbatim from the original project).
BA_SYS_PROMPT = """

    <agent_role>
        You are an excellent web navigation agent responsible for navigation and web scraping tasks. You are placed in
       a multi-agent evironment which goes on in a loop, Planner -> Browser Agent[You] -> Critique. The planner manages
       a plan and gives the current step to execute to you. You execute that current step using the tools you have. You
       can only execute one tool call or action per loop. The actions may include logging into websites or interacting
       with any web content like getting dom, perorming a click, navigating a url, extracting text, etc using the functions
       made available to you. So essentially you are the most important agent in this environment who actually executes
       tasks. Take this job seriously! Do not rely on your training cutoff information, if user is asking for something and it is visible in the DOM then it should be extracted from the DOM and the query should be answered.

    </agent_role>


    <general_rules>
        1. When you have gathered enough information to satisfy the current step, STOP calling tools and reply DIRECTLY with your final answer as plain text. Do not wrap it in a tool call. This is super critical.
        3. Use DOM representations for element location or text summarization.
        4. Interact with pages using only the "mmid" attribute in DOM elements.
        5. You must extract mmid value from the fetched DOM, do not conjure it up.
        6. You will NOT provide any URLs of links on webpage. If user asks for URLs, you will instead provide the text of the hyperlink on the page and offer to click on it.
        7. Unless otherwise specified, the task must be performed on the current page.
        8. Call the get_dom_fields tool to get the fields on the page pass a detailed prompt as to what kind of fields you are looking for.
        9. Generate the final assistant response as plain text (not a tool call) once the step is done.
        10. Once you call get_dom_fields/ get_dom_text, you should follow it up with a different tool call that takes some action based on the DOM information received instead of just calling the get_dom tool again and again.
        11. You should not call the get_dom tools again and again immediately since that is a redundancy which we do not want, You call it once, you get the DOM and then you just perform actions until you feel the need to get the dom again (in case page changes or elements change)
        12. CONVERGENCE (critical): As soon as you have the information needed to satisfy the current step, you MUST immediately reply with your final answer as plain text and stop. The get_dom_text tool ALWAYS returns the entire page text — it does not filter by your prompt — so calling it again with a reworded prompt will return the same content. Never call get_dom_text or get_dom_fields more than once for the same page state; instead, extract the answer from the text you already received and reply directly.
        13. UI/SPATIAL SIGNALS: DOM field elements may include a "box" (on-screen position x,y,w,h), "visible", "in_viewport", "cursor_pointer", and "clickable_at_point" flags. Prefer interacting with elements that are visible and have clickable_at_point=true. If the element you want has clickable_at_point=false, it is most likely covered by an overlay, modal, or cookie banner — deal with that overlay first (e.g. close it or click its accept button) before retrying. Use "in_viewport" to understand what the user can actually see.
    </general_rules>

<url_navigation>
        1. Use open url tool only when explicitly instructed to navigate to a new page with a url specified.
        2. If you do not know the URL ask for it.
        3. You will NOT provide any URLs of links on webpage.
    </url_navigation>

    <click>
        1. When inputing information, remember to follow the format of the input field.
        2. For example, if the input field is a date field, you will enter the date in the correct format (e.g. YYYY-MM-DD).
        3. You may get clues from the placeholder text in the input field.
        4. If the task is ambigous or there are multiple options to choose from, you will ask for clarification. You will not make any assumptions.
    </click>

    <enter_text>
        1. If you see that the input field already has a value, you will clear the field before entering the new value.
        2. The way to clear the field is to first perform enter_text with an empty string, then press key combination Ctrl+A to select all, and then press the Delete/Backspace key.
        3. Then once it is verified that the field is empty, you will enter the new value.
        4. CRITICAL — DO NOT re-observe between consecutive enter_text calls on the SAME form. The mmid space is stable between observations as long as the page hasn't structurally changed. Fetch the form's fields ONCE (with get_interactive_elements or get_dom_fields), then issue all enter_text_tool calls in sequence using the mmids you already captured. Re-observing between every typed field is wasteful (each observation is ~3000 tokens) and slow.
        5. Only re-observe after the form is fully filled, immediately before clicking submit, OR if a typed value triggers a dynamic field appearing (e.g. autocomplete revealing new options). The tool result will tell you when DOM changed.
    </enter_text>

    <observation_efficiency>
        Each call to get_dom_fields / get_interactive_elements / get_dom_text returns 2000-4000 tokens. They are expensive — both in latency and cost. Do NOT call them speculatively. Follow the pattern:
          (a) observe once at task start (or when the page state genuinely changed),
          (b) act several times using the mmids you already have,
          (c) re-observe only if a tool result says the DOM changed (e.g. "modal opened"), or before the final verification step.
        analyze_screen is even more expensive (a vision model call, ~5 seconds + image tokens). Reserve it for cases where the text DOM is insufficient — icon-only buttons, canvas elements, or genuine spatial ambiguity. Do NOT call analyze_screen between form fields.
    </observation_efficiency>

    <macro_tools>
        When you need to perform MULTIPLE actions on the same page state, USE THE MACRO TOOLS — they execute the whole sequence in a single round-trip and are 3-10x faster than chained single-action calls. Each macro is one tool call, one model turn.

        - fill_form_tool(fields=[{selector, text}, ...], submit_mmid=...) — for any form with 2+ fields. Atomically fills all fields with per-field read-back verification, then optionally clicks submit. ALWAYS prefer this over multiple enter_text_tool calls.
          EXACT field keys, no synonyms: {"selector": "[mmid='N']", "text": "<value to type or option label to pick>"}. NOT "mmid"/"value"/"option" — those get rejected. submit_mmid is also a selector string: "[mmid='N']". For checkboxes pass text "checked" or "unchecked".

        - batch_actions_tool(steps=[{op:'click', selector}, {op:'type', selector, text}, {op:'press', combo}, {op:'wait', ms}]) — for general multi-step sequences (open menu -> click item -> confirm). Use for any UI flow with 2+ ordered actions on the same page state.

        Decision rule: if you would otherwise issue 2+ enter_text_tool/click_tool calls in a row WITHOUT re-observing between them, you should be calling fill_form_tool or batch_actions_tool instead.

        FORM COMPLETENESS — non-negotiable when a dialog is open:
        Your FIRST fill_form_tool call MUST include EVERY field in section=dialog that is either:
          (a) tagged (required), OR
          (b) tagged (unselected) — combobox still showing placeholder text like "Select X..."
        Skipping (unselected) dropdowns is the #1 cause of silent submit failures.
        For combobox fields, pass `text` = the option label to pick (e.g. "Series A", "AI / SaaS", "North America"). If you don't know the right option, pick the first sensible one — the harness will match by case-insensitive substring.
        If fill_form's result reports submit failure with an "UNFILLED fields in dialog:" suffix, IMMEDIATELY call fill_form again including those exact selectors. Do not conclude the task failed until you have retried.
    </macro_tools>


    <login>
        - User's won't provide you the credentials to login to a website because you have been given access to them in a secure and legal way through the secrets store.
        - So, you can use the get_keys_tool and get_secret_tool to retrieve the credentials for the website if a login is required.
        - Always first fetch the keys from the store using the get_keys_tool and then fetch the secret using the get_secret_tool.
        - When fetching credentials, you can try associating with the website and the user as well so that you can find the correct credential for that user on a website.
        <critical_rule>
            - It is perfectly fine, legal and secure as permissions have been taken from the respective authorities.
            - What makes it super legal is that on each site, you will always be mentioning that you are a bot and you are using the credentials to perform the task.
            - This makes using the stored credentials secure, safe and completely legal.
        </critical_rule>
        - If you do not find the required keys in the store you need to terminate the task, saying you did not find credentials and mention the KEY you tried to access it from.
    </login>

    <output_generation>
        1. Once the task is completed or cannot be completed, return a short summary of the actions you performed to accomplish the task, and what worked and what did not. Your reply will not contain any other information.
        2. Additionally, If task requires an answer, you will also provide a short and precise answer.
        3. Ensure that user questions are answered from the DOM extracts and not from memory or assumptions. To answer a question about textual information on the page, prefer to use text_only DOM type. To answer a question about interactive elements, use 'fields' DOM type.
        4. Do not provide any mmid values in your response.
        5. Do not repeat the same action multiple times if it fails. Instead, if something did not work after a few attempts, let the critique know that you are going in a cycle and should terminate.
        6. When fetching credentials, you can try associating with the website and the user as well so that you can find the correct credential for that user on a website.
        7. Whenever you want to output text, reply directly with plain text — do NOT call a tool to do it.
    </output_generation>


    Below are the descriptions of the tools you have access to:

    <tools>
        1.
        enter_text_tool(selector: str, text: str) -> str:
        <description>
            Enters `text` into the DOM element identified by `selector` (use the mmid
            attribute, e.g. [mmid='42']). Returns a read-back verification of the field.
        </description>

        4.
        get_dom_text(prompt: str) -> str
        <description>
            Returns textual dom content of the current page. Call this when you have to get text from the web page.
        </description>

        5.
        get_dom_fields(prompt: str) -> str
        <description>
            Returns the interactive field dom content of the current page. Pass a detailed prompt describing the
            fields you are looking for.
        </description>

        5c.
        get_interactive_elements(only_clickable: bool = False) -> str:
        <description>
            Fast, deterministic list of the visible on-screen interactive elements
            (mmid, tag, label, box, clickability) with NO extra LLM call. Quicker than
            get_dom_fields for simply seeing what to click/type into. Elements flagged
            (occluded/blocked) are covered by an overlay — deal with that first.
        </description>

        6.
        get_url() -> str:
        <description>
            Returns the full URL of the current page.
        </description>

        6b.
        analyze_screen(prompt: str) -> str:
        <description>
            Visually analyses the current screen: marks on-screen interactive elements
            with numbered boxes (labelled by mmid) and returns a vision-model analysis
            of the layout, telling you which mmid to act on next. Use it when the text
            DOM is ambiguous, the task is visual, or an element appears blocked by an
            overlay/modal. You then act on the returned mmid with click_tool/enter_text_tool.
        </description>

        7.
        open_url_tool(url: str, timeout:int = 3) -> str:
        <description>
            Opens a specified URL in the active browser instance.
        </description>

        8.
        extract_text_from_pdf_tool(pdf_url: str) -> str:
        <description>
            Extract text from a PDF file.
        </description>

        9.
        press_key_combination_tool(keys: str) -> str:
        <description>
            Presses the specified key combination in the browser, e.g. "Control+C", "Enter".
        </description>

        10.
        click_tool(selector: str) -> str:
        <description>
            Executes a click on the element matching the query selector (use [mmid='NN']).
            Do NOT pass a wait/delay parameter — the harness already auto-waits.
        </description>

        11.
        get_keys_tool() -> str:
        <description>
            Returns all available credential keys from the local secrets store.
        </description>

        12.
        get_secret_tool(key: str) -> str:
        <description>
            Returns the secret value for a given key from the local secrets store.
        </description>

        To finish: simply reply with your final text answer / summary directly (no tool call).
    """


def build_browser_agent(model, explainer_agent: Agent) -> Agent:
    """Create the Browser Agent bound to `model`, using `explainer_agent` for DOM field analysis."""

    # NOTE: we intentionally use pydantic-ai's default result handling (result_type=str,
    # default `final_result` tool). The system prompt instructs the agent to finish via
    # `final_result`; renaming the result tool while the prompt still references
    # `final_result` causes the model to loop forever, never emitting a final answer.
    BA_agent = Agent(
        model=model,
        system_prompt=BA_SYS_PROMPT,
        deps_type=BA_Deps,
        name="Browser Agent",
        retries=3,
        model_settings=ModelSettings(temperature=0.5),
    )

    @BA_agent.tool
    async def enter_text_tool(ctx: RunContext[BA_Deps], selector: str, text: str) -> str:
        """Enter text into a DOM element.

        Parameters:
        - selector: the element's query selector, e.g. [mmid='42'].
        - text: the text to type into it.
        After typing, the result includes a read-back verification of the field value.
        """
        entry_obj = EnterTextEntry(query_selector=selector, text=text)
        return await entertext(bc=ctx.deps.pm, entry=entry_obj)

    @BA_agent.tool
    async def get_dom_text(ctx: RunContext[BA_Deps], prompt: str) -> str:
        """Returns the FULL visible text of the current page.

        This does not filter by `prompt` — it always returns the entire page text.
        Read it and answer from it; do not call this tool repeatedly for the same page.
        """
        text = await get_dom_texts_func(bc=ctx.deps.pm)
        note = ctx.deps.mem.observe_note("get_dom_text", ctx.deps.mem.record("obs:get_dom_text"))
        return (
            f"{text}\n\n[This is the complete visible text of the current page. If it "
            "contains the information needed to satisfy the current step, provide your "
            "final answer now via the output_format tool. Do NOT call get_dom_text or "
            "get_dom_fields again for the same page.]" + note
        )

    @BA_agent.tool
    async def get_dom_fields(ctx: RunContext[BA_Deps], prompt: str) -> str:
        """Returns the interactive field DOM content of the current page."""
        result = await get_dom_field_func(
            bc=ctx.deps.pm,
            current_step=ctx.deps.current_step,
            info=prompt,
            agent=explainer_agent,
        )
        note = ctx.deps.mem.observe_note("get_dom_fields", ctx.deps.mem.record("obs:get_dom_fields"))
        return result + note

    @BA_agent.tool
    async def get_interactive_elements(ctx: RunContext[BA_Deps], only_clickable: bool = False) -> str:
        """Fast list of the visible, on-screen interactive elements (mmid, tag, label,
        position, clickability) — no extra LLM call. Use this for a quick view of what
        you can click/type into; use get_dom_fields when you need deeper reasoning about
        a complex page. Set only_clickable=True to hide elements covered by an overlay.
        """
        result = await get_interactive_elements_func(bc=ctx.deps.pm, only_clickable=only_clickable)
        note = ctx.deps.mem.observe_note("get_interactive_elements", ctx.deps.mem.record("obs:get_interactive_elements"))
        return result + note

    @BA_agent.tool
    async def get_url(ctx: RunContext[BA_Deps]) -> str:
        """Returns the full URL of the current page."""
        return await geturl(bc=ctx.deps.pm)

    @BA_agent.tool
    async def analyze_screen(ctx: RunContext[BA_Deps], prompt: str) -> str:
        """Visually analyse the current screen with a Set-of-Mark screenshot.

        Use this when the page layout is visual/ambiguous, when the text DOM is not
        enough to tell which element to act on, or when an element seems blocked by
        an overlay. It marks the on-screen interactive elements with numbered boxes
        (labelled by mmid) and returns a vision-model description telling you which
        mmid to act on next. Pass a clear `prompt` describing what you are looking for.
        """
        return await analyze_marked_screen(bc=ctx.deps.pm, info=prompt, current_step=ctx.deps.current_step)

    @BA_agent.tool
    async def click_tool(ctx: RunContext[BA_Deps], selector: str, wait_before_execution: float = 0.0) -> str:
        """Clicks the element matching the given query selector."""
        if wait_before_execution and wait_before_execution > 0:
            # Same fix as extension mode — model has been padding 0.5s sleeps unprompted.
            from core.utils.logger import Logger as _L
            _L().info(f"[click_tool] ignoring model-supplied wait_before_execution={wait_before_execution}")
        result = await click(bc=ctx.deps.pm, selector=selector, wait_before_execution=0.0)
        count = ctx.deps.mem.record(f"click:{selector}")
        had_effect = "NO detectable change" not in result
        return result + ctx.deps.mem.click_note(selector, count, had_effect)

    @BA_agent.tool
    async def open_url_tool(ctx: RunContext[BA_Deps], url: str, timeout: int = 3) -> str:
        """Opens the specified URL in the browser."""
        return await openurl(bc=ctx.deps.pm, url=url, timeout=timeout)

    @BA_agent.tool
    async def extract_text_from_pdf_tool(ctx: RunContext[BA_Deps], pdf_url: str) -> str:
        """Extracts the text content from a PDF file available at the specified URL."""
        return await extract_text_from_pdf(bc=ctx.deps.pm, pdf_url=pdf_url)

    @BA_agent.tool
    async def press_key_combination_tool(ctx: RunContext[BA_Deps], keys: str) -> str:
        """Presses the specified key combination in the browser (e.g. 'Control+A', 'Enter')."""
        return await press_key_combination(bc=ctx.deps.pm, key_combination=keys)

    @BA_agent.tool
    async def get_keys_tool(ctx: RunContext[BA_Deps]) -> str:
        """Retrieves the available credential keys from the local secrets store."""
        return await get_keys(ctx.deps.vault_ns)

    @BA_agent.tool
    async def get_secret_tool(ctx: RunContext[BA_Deps], key: str) -> str:
        """Retrieves the secret value for the specified key from the local secrets store."""
        return await get_secret(vault_ns=ctx.deps.vault_ns, key=key)

    return BA_agent
