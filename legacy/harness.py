"""Browser Agent harness.

A minimal, local runtime that stands the Browser Agent up against a local
Chromium/Chrome instance — no orchestrator, planner, critique, database, vault,
object storage or remote-browser provider required.

Responsibilities:
  * build the LLM model instance from environment variables
  * build the Explainer agent (the Browser Agent depends on it for DOM analysis)
  * launch and own the PlaywrightManager (the browser)
  * run a natural-language task and return the agent's final text answer
  * clean up the browser

Usage:
    from harness import BrowserAgentHarness

    async with BrowserAgentHarness(start_url="https://google.com") as h:
        answer = await h.run_task("Search for the price of an iPhone 15 and report it")
        print(answer)
"""

import os
import uuid
from typing import Optional

from dotenv import load_dotenv

# Load env BEFORE importing anything that reads it at import time.
load_dotenv()

# pydantic-ai ships optional Logfire instrumentation; without a Logfire account it
# prints a "not configured" warning. Silence it for this local, telemetry-free build.
os.environ.setdefault("LOGFIRE_IGNORE_NO_CONFIG", "1")

from pydantic_ai import Agent  # noqa: E402
from pydantic_ai.settings import ModelSettings  # noqa: E402
from pydantic_ai.usage import UsageLimits  # noqa: E402
from pydantic_ai.exceptions import UsageLimitExceeded  # noqa: E402

from core.agents.browser_agent import build_browser_agent, BA_Deps  # noqa: E402
from core.agents.explainer_agent import EXPLAINER_SYS_PROMPT, ExplainerOutput  # noqa: E402
from core.browser_manager import PlaywrightManager  # noqa: E402
from core.utils.agent_factory import get_text_model_instance  # noqa: E402
from core.utils.logger import Logger  # noqa: E402

logger = Logger()


class BrowserAgentHarness:
    def __init__(self,
                 start_url: str = "https://google.com",
                 headless: bool = False,
                 show_overlay: bool = True,
                 take_screenshots: bool = True,
                 record_video: bool = False,
                 vault_ns: str = "default",
                 user_data_dir: Optional[str] = None,
                 request_limit: int = 40,
                 job_id: Optional[str] = None):
        self.start_url = start_url
        self.headless = headless
        self.show_overlay = show_overlay
        self.take_screenshots = take_screenshots
        self.record_video = record_video
        self.vault_ns = vault_ns
        self.user_data_dir = user_data_dir
        self.request_limit = request_limit
        self.job_id = job_id or str(uuid.uuid4())

        self.model = None
        self.explainer_agent: Optional[Agent] = None
        self.browser_agent: Optional[Agent] = None
        self.pm: Optional[PlaywrightManager] = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def start(self):
        logger.set_job_id(self.job_id)
        logger.info(f"Starting Browser Agent harness (job {self.job_id})")

        # 1. Model
        self.model = get_text_model_instance()

        # 2. Explainer / grounding agent (used by the get_dom_fields tool).
        # It now returns a structured ExplainerOutput (ranked candidates with
        # mmid + confidence + escalation flags) rather than a free-form string.
        self.explainer_agent = Agent(
            model=self.model,
            system_prompt=EXPLAINER_SYS_PROMPT,
            name="Explainer Agent",
            retries=2,
            model_settings=ModelSettings(temperature=0.1),
            result_type=ExplainerOutput,
            result_tool_name="output_format",
            result_tool_description=(
                "Return the grounded, ranked elements relevant to the current step."
            ),
        )

        # 3. Browser agent
        self.browser_agent = build_browser_agent(self.model, self.explainer_agent)

        # 4. Browser
        self.pm = PlaywrightManager(
            headless=self.headless,
            gui_input_mode=self.show_overlay,
            take_screenshots=self.take_screenshots,
            record_video=self.record_video,
            job_ID=self.job_id,
            start_url=self.start_url,
            user_data_dir=self.user_data_dir,
        )
        await self.pm.async_initialize()
        logger.info("Harness ready.")
        return self

    async def run_task(self, task: str, current_step: Optional[str] = None) -> str:
        """Run a natural-language task to completion and return the final answer.

        The Browser Agent (via pydantic-ai) internally loops over tool calls —
        reading the DOM, clicking, typing, navigating — until it produces a final
        text answer through its `output_format` tool.
        """
        if not self.browser_agent or not self.pm:
            raise RuntimeError("Harness not started. Call start() or use 'async with'.")

        step = current_step or task
        deps = BA_Deps(current_step=step, pm=self.pm, vault_ns=self.vault_ns)
        ba_prompt = f'plan="{task}" current_step="{step}" '

        logger.info(f"Running task: {task}")
        try:
            result = await self.browser_agent.run(
                user_prompt=ba_prompt,
                deps=deps,
                usage_limits=UsageLimits(request_limit=self.request_limit),
            )
            answer = result.data
        except UsageLimitExceeded:
            answer = (
                f"Stopped after reaching the step limit ({self.request_limit} model "
                "requests) without producing a final answer. Try a more specific task, "
                "raise request_limit, or break the task into smaller steps."
            )
            logger.warn(answer)
        logger.info(f"Task finished. Answer: {answer}")
        return answer

    async def close(self):
        if self.pm:
            try:
                await self.pm.stop_playwright()
            except Exception as e:
                logger.warn(f"Error during browser cleanup: {e}")
            finally:
                self.pm = None
