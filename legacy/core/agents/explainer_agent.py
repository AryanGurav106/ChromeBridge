"""The Explainer Agent — redesigned as a structured *grounding* sub-agent.

What changed and why
--------------------
The original Explainer read the *entire* serialized DOM on every call and
returned a free-form ``{"expected_field_info": "<prose/JSON blob>"}`` string —
no ranking, no confidence, no recovery signal, and (despite the prompt claiming
to use screenshots) no image was ever passed.

The 2024-2026 literature is unanimous that this is the wrong shape:

* SeeAct (arXiv:2401.01614) shows planning ≠ grounding, and that grounding over
  a **closed candidate set** with text choices (48.9%) massively beats free-text
  or naive image-mark grounding (15.1%) on dense web pages.
* The grounder should receive a **pre-filtered shortlist** (Prune4Web,
  Mind2Web DMR) — never the whole DOM — and emit a **ranked list with mmid +
  confidence + rationale** plus explicit escalation flags.

So the Explainer is now a grounder: given the step + a small candidate list
(already filtered by ``element_filter``), it returns ``ExplainerOutput`` —
ranked ``GroundedField``s, a ``needs_vision`` flag (hand off to the Set-of-Mark
/ ``analyze_screen`` vision channel when the target is visual or the text is
ambiguous), and a ``no_match`` flag (tell the planner to re-plan rather than
guess). Confidence lets the caller gate direct action vs. escalation.

The export names (``EXPLAINER_SYS_PROMPT``, ``ExplainerOutput``) are unchanged so
``harness.py`` keeps wiring it the same way.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from core.utils.agent_factory import get_text_model_instance


class GroundedField(BaseModel):
    """One element the grounder believes is relevant to the current step."""
    mmid: int = Field(description="The mmid of the element, taken verbatim from a candidate line.")
    label: str = Field(default="", description="Short human-readable label/text of the element.")
    role: Optional[str] = Field(default=None, description="Role or tag, e.g. button, link, textbox.")
    action: Literal["click", "type", "select", "read", "other"] = Field(
        default="other",
        description="The action the agent would most likely take on this element.",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="0-1 confidence that this element matches the step's intent.",
    )
    rationale: str = Field(default="", description="A few words on why this element matches.")


class ExplainerOutput(BaseModel):
    """Structured grounding result returned to the Browser Agent."""
    fields: List[GroundedField] = Field(
        default_factory=list,
        description="Relevant elements, MOST relevant first.",
    )
    needs_vision: bool = Field(
        default=False,
        description=(
            "True if the target is visual (icon with no text, canvas, ambiguous "
            "layout) or no candidate clearly matches — the agent should use "
            "analyze_screen (Set-of-Mark vision) to disambiguate."
        ),
    )
    no_match: bool = Field(
        default=False,
        description="True if NONE of the candidates plausibly satisfy the step.",
    )
    notes: str = Field(
        default="",
        description="Optional one-line note for the agent (e.g. an overlay must be closed first).",
    )


# System prompt for the Explainer / grounding sub-agent.
EXPLAINER_SYS_PROMPT = """
<role>
You are a Grounding Agent for a web automation system. You are given the CURRENT STEP
the agent must perform and a SHORTLIST of candidate interactive elements from the live
page (already pre-filtered for relevance). Each candidate is one line:

    [mmid]<tag attrs "label"> (flags)

Your ONLY job: select and RANK the elements that are relevant to the current step, most
relevant first, and report your confidence. You do not perform the action — you tell the
agent which element(s) to act on.
</role>

<rules>
1. Use ONLY mmids that appear in the candidate list. NEVER invent an mmid.
2. Return the most relevant element FIRST. Include a few strong alternatives if they
   plausibly match; do not pad the list with unrelated elements.
3. Set `action` to what the agent would do with each element (click/type/select/read).
4. `confidence` is 0-1: how sure you are this element matches the step's intent. Be
   honest — low confidence is a useful signal, not a failure.
5. A flag `(occluded)` means the element is covered by an overlay/modal/cookie-banner.
   If the element the step wants is occluded, still return it, but put a one-line `notes`
   telling the agent to deal with the overlay first (and prefer ranking a visible
   accept/close control highly if one is present).
6. A flag `(offscreen)` means the element is outside the current viewport — usable, but
   the agent may need to scroll.
7. Set `needs_vision=true` when the right target is visual (an icon/image with no useful
   text label), the candidates are genuinely ambiguous, or nothing matches well — the
   agent will then use the screenshot-based vision tool to disambiguate.
8. Set `no_match=true` ONLY if none of the candidates could plausibly satisfy the step.
9. Be concise. `rationale` is a few words, not a sentence. Do not restate the whole label.
</rules>

<output>
Return the structured result via the provided result tool: a `fields` list of
{mmid, label, role, action, confidence, rationale}, plus `needs_vision`, `no_match`,
and an optional `notes`. The `fields` list must not be empty unless `no_match` is true.
</output>
"""


# Module-level instance kept for backward compatibility / standalone use.
# (harness.py builds its own Agent from EXPLAINER_SYS_PROMPT + ExplainerOutput.)
explainer_agent = Agent(
    model=get_text_model_instance(),
    system_prompt=EXPLAINER_SYS_PROMPT,
    name="Explainer Agent",
    result_type=ExplainerOutput,
    retries=2,
    model_settings=ModelSettings(temperature=0.1),
)
