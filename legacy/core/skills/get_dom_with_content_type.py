import os
import time
from typing import Annotated
from typing import Any
import json
from playwright.async_api import Page
import re
from pydantic_ai import Agent
# from core.agents.explainer_agent import explainer_agent
from core.browser_manager import PlaywrightManager
from core.utils.dom_helper import wait_for_non_loading_dom_state, get_page_fingerprint
from core.utils.get_detailed_accessibility_tree import do_get_accessibility_info
from core.utils.dom_serializer import flatten_tree, serialize_elements
from core.utils.element_filter import filter_elements
from core.utils.ui_messagetype import MessageType
from core.utils.openai_msg_parser import AgentConversationHandler, ConversationStorage
from core.utils.openai_msg_parser import extract_explainer_data
from core.skills.marked_screenshot import analyze_marked_screen

# Per-job memory of the previous snapshot's mmids, so we can mark newly-appeared
# elements with `*` (a cheap delta cue, browser-use style).
_last_mmids: dict[str, set] = {}

# How many candidate elements to hand the grounder. Generous top-K protects
# recall (Prune4Web reports Recall@20 > 95%); 30 leaves headroom.
_TOP_K = 30
# _explainer_storage = ConversationStorage(job_id=browser_manager.job_ID, file_name="explainer.json")

from config import PROJECT_SOURCE_ROOT

from core.utils.logger import Logger
logger = Logger()
_explainer_conversation_handler = AgentConversationHandler()


def get_explainer_storage(bc: PlaywrightManager) -> ConversationStorage:
    return ConversationStorage(job_id=bc.job_ID, file_name="explainer.json")


def _should_escalate_to_vision(grounded) -> bool:
    """Decide whether to back the text grounder with a Set-of-Mark vision pass.

    Escalate when the cheap text grounder is uncertain:
      - it errored / returned nothing (grounded is None),
      - it explicitly raised the `needs_vision` flag (target looks visual/ambiguous),
      - it found no usable candidate fields.
    This keeps the (more expensive) vision call to the cases where it actually helps.
    """
    if grounded is None:
        return True
    if getattr(grounded, "needs_vision", False):
        return True
    if not getattr(grounded, "fields", None):
        return True
    return False


def _fp_key(fp: dict) -> str:
    """Stable string key for a page fingerprint."""
    return f"{fp.get('url')}|{fp.get('textLen')}|{fp.get('elements')}"


def _obs_cache(bc, fp_key: str) -> dict:
    """Return a per-session observation cache scoped to the current page state.

    The cache lives on the PlaywrightManager. When the page changes (fingerprint
    differs), the whole cache is dropped — so only the current page state is ever
    held (bounded memory) and stale observations are never served.
    """
    cache = getattr(bc, "_obs_cache_store", None)
    if cache is None or cache.get("_key") != fp_key:
        cache = {"_key": fp_key}
        bc._obs_cache_store = cache
    return cache

def extract_and_parse_json(response_str):
    # First try parsing the entire string as JSON
    try:
        return json.loads(response_str)
    except json.JSONDecodeError:
        # If that fails, try to extract JSON using regex
        try:
            # Pattern to find JSON objects containing "expected_field_info"
            pattern = r'(\{(?:[^{}]|(?:\{[^{}]*\}))*"expected_field_info"(?:[^{}]|(?:\{[^{}]*\}))*\})'
            json_match = re.search(pattern, response_str)
            
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
        except (AttributeError, json.JSONDecodeError) as e:
            logger.error(f"Error extracting JSON with regex: {e}")
    
    # If all parsing attempts fail, return default empty structure
    return {"expected_field_info": {}}



async def get_dom_texts_func(bc:PlaywrightManager) -> Annotated[str | None, "The text content of the DOM"]:
    """
    Retrieves the text content of the active page's DOM.

    Parameters
    ----------
    current_step : str
        The current step in the workflow being executed. This helps track and log the context 
        of the DOM extraction operation.

    Returns
    -------
    str | None
        The text content of the page including image alt texts.

    Raises
    ------
    ValueError
        If no active page is found.
    """
    logger.debug("Executing Get DOM Text Command")
    
    start_time = time.time()

    # Create and use the PlaywrightManager
    browser_manager = bc
    page = await browser_manager.get_current_page()
    if page is None:
        raise ValueError('No active page found. OpenURL command opens a new page.')

    await wait_for_non_loading_dom_state(page, 2000)

    # Observation cache: if the page hasn't changed since we last read its text,
    # return the cached content instead of re-extracting.
    cache = _obs_cache(browser_manager, _fp_key(await get_page_fingerprint(page)))
    if "text" in cache:
        logger.debug("get_dom_text cache hit (page unchanged)")
        return cache["text"]

    # Get filtered text content including alt text from images
    text_content = await get_filtered_text_content(page)
    cache["text"] = text_content
    file_path = os.path.join(PROJECT_SOURCE_ROOT, 'temp', f'task_{browser_manager.job_ID}', 'text_only_dom.txt')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(text_content)

    elapsed_time = time.time() - start_time
    logger.debug(f"Get DOM Text Command executed in {elapsed_time:.2f} seconds")
    await browser_manager.notify_user(
        f"Fetched the text content of the DOM and saved to {file_path}",
        message_type=MessageType.ACTION
    )
    
    return text_content


def _format_grounding_result(out, candidates: list[dict]) -> str:
    """Render the grounder's structured output into a compact, agent-friendly string.

    `out` is an ExplainerOutput (or None on failure). `candidates` is the
    fallback shortlist so the agent is never left blind.
    """
    by_mmid = {c["mmid"]: c for c in candidates}
    lines: list[str] = []

    fields = getattr(out, "fields", None) if out is not None else None
    if fields:
        lines.append("Relevant elements (most relevant first):")
        for f in fields:
            # only trust mmids that actually exist in the candidate set
            c = by_mmid.get(f.mmid)
            if c is None:
                continue
            label = f.label or c.get("label") or ""
            role = f.role or c.get("role") or c.get("tag")
            conf = f"{f.confidence:.2f}"
            occ = ""
            if c.get("clickable_at_point") is False and c.get("in_viewport", True):
                occ = " [occluded - handle overlay first]"
            elif not c.get("in_viewport", True):
                occ = " [offscreen - scroll to it]"
            rat = f" - {f.rationale}" if f.rationale else ""
            lines.append(
                f"  mmid={f.mmid} | {role} \"{label}\" | action={f.action} "
                f"| confidence={conf}{occ}{rat}"
            )

    if not lines:
        # grounder returned nothing usable — fall back to the raw shortlist
        lines.append(
            "No grounded selection returned; here are the top on-screen "
            "interactive candidates (act by [mmid='N']):"
        )
        lines.append(serialize_elements(candidates[:15]))

    notes = getattr(out, "notes", "") if out is not None else ""
    if notes:
        lines.append(f"Note: {notes}")
    if out is not None and getattr(out, "needs_vision", False):
        lines.append(
            "Hint: the target may be visual or ambiguous — consider analyze_screen "
            "to disambiguate."
        )
    if out is not None and getattr(out, "no_match", False):
        lines.append(
            "Hint: none of the candidates clearly matched this step — you may need to "
            "scroll, open a menu, or revise what you are looking for."
        )

    lines.append(
        "\nAct on an element with click_tool/enter_text_tool using selector [mmid='N']."
    )
    return "\n".join(lines)


async def get_dom_field_func(
    bc,
    current_step: Annotated[str, "The current step in the workflow being executed"],
    info: Annotated[str, "The information requested by the tool call"],
    screenshot_path: Annotated[str | None, "Path to the pre-action screenshot"] = None,
    custom_prompt: Annotated[str | None, "Custom prompt to be passed to the explainer agent"] = None,
    agent: Annotated[Agent, "The explainer (grounding) agent instance"] = None
) -> Annotated[str | None, "Ranked relevant interactive fields from the DOM"]:
    """Grounding cascade: snapshot -> flatten -> task-conditioned filter -> grounder.

    Instead of dumping the whole DOM into the Explainer, this:
      1. captures the enriched accessibility tree (geometry + visibility),
      2. flattens it to a compact element registry,
      3. filters to the top-K task-relevant candidates (deterministic, LLM-free),
      4. asks the grounding agent to rank/select among those candidates and
         report confidence + escalation flags.
    """
    logger.debug(f"[{time.strftime('%H:%M:%S')}] Executing Get DOM Fields Command (cascade)")
    start_time = time.time()

    browser_manager = bc
    page = await browser_manager.get_current_page()
    if page is None:
        raise ValueError('No active page found. OpenURL command opens a new page.')

    await wait_for_non_loading_dom_state(page, 2000)
    wait_time = time.time()

    # Observation cache, scoped to the current page state (auto-invalidated on change).
    cache = _obs_cache(browser_manager, _fp_key(await get_page_fingerprint(page)))

    # Exact-repeat shortcut: same page + same step/info/prompt -> skip BOTH the AX
    # snapshot and the grounder LLM call entirely.
    result_key = ("fields", current_step or "", info or "", custom_prompt or "")
    if result_key in cache:
        logger.info("[cascade] dom_fields cache hit (page unchanged, same step/info) — skipped AX snapshot + grounder LLM")
        return cache[result_key]

    # 1. Capture enriched AX tree (dict) — reuse across different step/info on the
    #    same page state (the snapshot is the costliest non-LLM part).
    if "tree" in cache:
        tree = cache["tree"]
        logger.debug("[cascade] reusing cached AX snapshot (page unchanged)")
    else:
        tree = await do_get_accessibility_info(page, browser_manager, only_input_fields=False)
        cache["tree"] = tree
    capture_time = time.time()
    logger.debug(f"[{time.strftime('%H:%M:%S')}] AX ready in {capture_time - wait_time:.2f}s")

    # 2. Flatten to a registry of element records.
    registry = flatten_tree(tree)

    # delta: which mmids are new since the last snapshot for this job?
    job = getattr(bc, "job_ID", "default")
    current_mmids = {r["mmid"] for r in registry}
    new_mmids = current_mmids - _last_mmids.get(job, set())
    _last_mmids[job] = current_mmids

    # 3. Task-conditioned filter -> top-K candidates (deterministic, no LLM).
    candidates = filter_elements(registry, current_step, info, custom_prompt or "", top_k=_TOP_K)
    filter_time = time.time()

    if not candidates:
        logger.warning("No interactive candidates found on the page.")
        return "No interactive elements were found on the current page."

    candidate_block = serialize_elements(candidates, new_mmids=new_mmids)

    # --- Cascade telemetry (INFO so it's visible in an end-to-end run) ---
    # Shows the representation/token win and that the deterministic filter fired
    # before any LLM call. `raw_dump_chars` is what the OLD code would have sent.
    raw_dump_chars = len(str(tree))
    cand_chars = len(candidate_block)
    reduction = (1 - cand_chars / raw_dump_chars) * 100 if raw_dump_chars else 0.0
    logger.info(
        f"[cascade] elements={len(registry)} -> candidates={len(candidates)} "
        f"(new={len(new_mmids)}) | grounder input {cand_chars} chars "
        f"vs old dump {raw_dump_chars} chars ({reduction:.1f}% smaller) | "
        f"snapshot {capture_time - wait_time:.2f}s, filter {filter_time - capture_time:.3f}s"
    )

    # 4. Grounding agent ranks/selects among the shortlist.
    prompt = (
        f"CURRENT STEP: {current_step}\n"
        f"WHAT THE AGENT IS LOOKING FOR: {info}\n"
        f"{('EXTRA: ' + custom_prompt) if custom_prompt else ''}\n\n"
        f"CANDIDATE ELEMENTS (mmid is verbatim — never invent one):\n"
        f"{candidate_block}"
    )

    explainer_agent = agent
    grounded = None
    try:
        explainer_response = await explainer_agent.run(prompt)
        grounded = explainer_response.data
    except Exception as e:
        logger.error(f"Grounding agent failed: {e}", exc_info=True)
    explainer_time = time.time()

    # Log what the grounder actually selected (top 3) + escalation flags.
    if grounded is not None and getattr(grounded, "fields", None):
        picks = ", ".join(
            f"mmid={f.mmid}({f.action},{f.confidence:.2f})" for f in grounded.fields[:3]
        )
        flags = []
        if getattr(grounded, "needs_vision", False):
            flags.append("needs_vision")
        if getattr(grounded, "no_match", False):
            flags.append("no_match")
        flag_str = f" flags=[{','.join(flags)}]" if flags else ""
        logger.info(
            f"[cascade] grounder picked [{picks}]{flag_str} in {explainer_time - filter_time:.2f}s"
        )
    else:
        logger.info(
            f"[cascade] grounder returned no usable fields in "
            f"{explainer_time - filter_time:.2f}s (falling back to raw shortlist)"
        )

    result_text = _format_grounding_result(grounded, candidates)

    # Auto-escalate to the Set-of-Mark vision channel when the text grounder is
    # uncertain. This joins the cheap text cascade to the visual channel so the
    # agent gets a grounded mmid recommendation from pixels when the DOM alone
    # was not enough — without the agent having to decide to call analyze_screen.
    if _should_escalate_to_vision(grounded):
        try:
            logger.info("[cascade] text grounder uncertain -> escalating to Set-of-Mark vision")
            vision = await analyze_marked_screen(bc, info=info, current_step=current_step)
            result_text += (
                "\n\nVISUAL ANALYSIS (Set-of-Mark, auto-escalated because text "
                "grounding was uncertain):\n" + vision
            )
        except Exception as e:
            logger.error(f"Vision escalation failed: {e}", exc_info=True)

    cache[result_key] = result_text  # memoize for exact repeats on this page state

    # Persist for post-mortem (storage stores the assistant content as a string).
    try:
        _explainer_conversation_handler.add_explainer_message(result_text, prompt)
        messages = _explainer_conversation_handler.get_conversation_history()
        explainer_storage = ConversationStorage(job_id=bc.job_ID, file_name="explainer.json")
        saved_path = explainer_storage.save_conversation(messages, prefix="task")
        logger.info(f"Saved Explainer Agent messages to: {saved_path}")
    except Exception as e:
        logger.error(f"Failed to save Explainer Agent messages: {str(e)}", exc_info=True)

    total_time = time.time() - start_time
    logger.debug(f"[{time.strftime('%H:%M:%S')}] Get DOM Fields (cascade) total {total_time:.2f}s")
    return result_text


async def get_filtered_text_content(page: Page) -> str:
    """Helper function to get filtered text content from the page."""
    text_content = await page.evaluate("""
        () => {
            // Array of query selectors to filter out
            const selectorsToFilter = ['#tawebagent-overlay'];

            // Store the original visibility values to revert later
            const originalStyles = [];

            // Hide the elements matching the query selectors
            selectorsToFilter.forEach(selector => {
                const elements = document.querySelectorAll(selector);
                elements.forEach(element => {
                    originalStyles.push({ element: element, originalStyle: element.style.visibility });
                    element.style.visibility = 'hidden';
                });
            });

            // Get the text content of the page
            let textContent = document?.body?.innerText || document?.documentElement?.innerText || "";

            // Get all the alt text from images on the page
            let altTexts = Array.from(document.querySelectorAll('img')).map(img => img.alt);
            altTexts = "Other Alt Texts in the page: " + altTexts.join(' ');

            // Revert the visibility changes
            originalStyles.forEach(entry => {
                entry.element.style.visibility = entry.originalStyle;
            });
            
            return textContent + " " + altTexts;
        }
    """)
    return text_content


def prompt_constructor(inputs: str) -> str:
    """Helper function to construct a prompt string with system prompt and inputs."""
    return f"Inputs :\n{inputs}"