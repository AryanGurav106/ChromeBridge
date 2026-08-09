"""Extension-mode harness.

Boots the local WebSocket bridge, waits for the Chrome extension to connect,
then runs the Browser Agent against the user's real Chrome window.
"""

import os
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("LOGFIRE_IGNORE_NO_CONFIG", "1")

from pydantic_ai import Agent  # noqa: E402
from pydantic_ai.settings import ModelSettings  # noqa: E402
from pydantic_ai.usage import UsageLimits  # noqa: E402
from pydantic_ai.exceptions import UsageLimitExceeded  # noqa: E402

from core.agents.browser_agent_extension import (  # noqa: E402
    BA_Deps_Ext, build_browser_agent_via_extension,
)
from core.agents.explainer_agent import EXPLAINER_SYS_PROMPT, ExplainerOutput  # noqa: E402
from core.bridge.driver import ExtensionDriver  # noqa: E402
from core.bridge.server import ExtensionBridge  # noqa: E402
from core.utils.agent_factory import get_text_model_instance  # noqa: E402
from core.utils.logger import Logger  # noqa: E402
from core.utils.recipes import (  # noqa: E402
    RecipeStore, build_recipe, extract_steps_from_messages, replay,
)
from config import PROJECT_SOURCE_ROOT  # noqa: E402

logger = Logger()


class ExtensionAgentHarness:
    def __init__(self,
                 host: str = "127.0.0.1",
                 port: int = 8765,
                 token: Optional[str] = None,
                 request_limit: int = 40,
                 vault_ns: str = "default",
                 job_id: Optional[str] = None,
                 connect_timeout: float = 120.0,
                 keep_history: bool = True):
        self.host = host
        self.port = port
        self.token = token
        self.request_limit = request_limit
        self.vault_ns = vault_ns
        self.job_id = job_id or str(uuid.uuid4())
        self.connect_timeout = connect_timeout
        self.keep_history = keep_history

        self.bridge: Optional[ExtensionBridge] = None
        self.driver: Optional[ExtensionDriver] = None
        self.browser_agent: Optional[Agent] = None
        self.explainer_agent: Optional[Agent] = None
        self.model = None
        # Carries the previous task's messages into the next task so follow-up
        # actions on the same page can skip re-observation. We keep ONE task of
        # context (not the whole session) — large enough for "now click Y" to
        # benefit, bounded enough that token cost doesn't snowball.
        self._history: list = []
        # Last completed task's identity + steps (for /save after the fact).
        self._last_task_text: Optional[str] = None
        self._last_task_url: str = ""
        self._last_task_steps: list[dict] = []
        # Persistent recipe library at temp/recipes/ (gitignored by default).
        self.recipes = RecipeStore(Path(PROJECT_SOURCE_ROOT) / "temp" / "recipes")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def start(self):
        logger.set_job_id(self.job_id)

        # 1. Bridge up first so the user can paste the token before we hang.
        self.bridge = ExtensionBridge(host=self.host, port=self.port, token=self.token)
        await self.bridge.start()
        token = self.bridge.token

        print("\n" + "=" * 60)
        print(" Agentic Browser Bridge — waiting for Chrome extension")
        print("=" * 60)
        print(f"  ws://{self.host}:{self.port}")
        print(f"  token: {token}")
        print(" 1) In Chrome -> chrome://extensions -> Developer mode ON")
        print(" 2) Load unpacked -> point at the 'extension/' folder")
        print(" 3) Open the extension's side panel, paste the token, hit Save & Connect")
        print("=" * 60 + "\n")

        await self.bridge.wait_until_connected(timeout=self.connect_timeout)
        logger.info("Extension connected; building agent.")

        # 2. Driver + model + explainer + agent.
        self.driver = ExtensionDriver(self.bridge, job_id=self.job_id)
        self.model = get_text_model_instance()
        self.explainer_agent = Agent(
            model=self.model,
            system_prompt=EXPLAINER_SYS_PROMPT,
            name="Explainer Agent",
            retries=2,
            model_settings=ModelSettings(temperature=0.1),
            result_type=ExplainerOutput,
            result_tool_name="output_format",
            result_tool_description="Return the grounded ranked elements relevant to the current step.",
        )
        self.browser_agent = build_browser_agent_via_extension(self.model, self.explainer_agent)
        logger.info("Extension-mode harness ready.")
        return self

    async def run_task(self, task: str, current_step: Optional[str] = None) -> str:
        if not self.browser_agent or not self.driver:
            raise RuntimeError("Harness not started.")
        step = current_step or task
        deps = BA_Deps_Ext(current_step=step, driver=self.driver, vault_ns=self.vault_ns)
        ba_prompt = f'plan="{task}" current_step="{step}" '
        logger.info(f"Running task via extension: {task}")
        deps.tt.start_task(task)
        result_obj = None
        try:
            run_kwargs = dict(
                user_prompt=ba_prompt,
                deps=deps,
                usage_limits=UsageLimits(request_limit=self.request_limit),
            )
            if self.keep_history and self._history:
                run_kwargs["message_history"] = self._history
            result_obj = await self.browser_agent.run(**run_kwargs)
            answer = result_obj.data
            # Carry forward only the last few messages of this task into the
            # next one. A single task can produce 20–30 messages (every tool
            # call = 2 messages); carrying all of them re-injects huge
            # 13k-character tool returns on the next task's prompt and snowballs
            # token usage. Keeping the tail preserves "what the user just did"
            # without dragging stale observations along.
            if self.keep_history and result_obj is not None:
                try:
                    msgs = list(result_obj.new_messages())
                    MAX_HISTORY_MESSAGES = 8
                    trimmed = msgs[-MAX_HISTORY_MESSAGES:]
                    # A naive tail-slice can leave a tool-return as the first
                    # message — OpenAI rejects that with "messages with role
                    # 'tool' must be a response to a preceding message with
                    # 'tool_calls'". Drop the head until the first message is
                    # either a user prompt or an assistant message that DOESN'T
                    # start with an orphaned tool-return.
                    def _is_orphan_head(m):
                        parts = getattr(m, "parts", None) or []
                        if not parts: return False
                        head_kind = getattr(parts[0], "part_kind", "")
                        # tool-return part with no preceding tool-call in our slice = orphan
                        return head_kind in ("tool-return", "tool_return")
                    while trimmed and _is_orphan_head(trimmed[0]):
                        trimmed = trimmed[1:]
                    self._history = trimmed
                except Exception:
                    self._history = []
            # Capture this task's action trajectory for /save.
            try:
                msgs = list(result_obj.new_messages()) if result_obj is not None else []
                self._last_task_steps = extract_steps_from_messages(msgs)
            except Exception:
                self._last_task_steps = []
            self._last_task_text = task
            try:
                url_info = await self.driver.get_url()
                self._last_task_url = url_info
            except Exception:
                self._last_task_url = ""
        except UsageLimitExceeded:
            answer = (f"Stopped after {self.request_limit} model requests "
                      "without a final answer.")
            logger.warn(answer)
        finally:
            deps.tt.end_task()
            # Pull LLM-side stats from the RunResult if available.
            try:
                if result_obj is not None:
                    u = getattr(result_obj, "_usage", None) or (
                        result_obj.usage() if hasattr(result_obj, "usage") else None
                    )
                    if u is not None:
                        deps.tt.set_usage(
                            getattr(u, "requests", None),
                            getattr(u, "total_tokens", None),
                            getattr(u, "request_tokens", None),
                            getattr(u, "response_tokens", None),
                        )
            except Exception:
                pass
            try:
                print(deps.tt.summary())
            except Exception:
                pass
        return answer

    def reset_history(self) -> None:
        """Clear the carried-over message history (e.g. on /reset or topic switch)."""
        self._history = []

    # ---- recipes (S3) ----------------------------------------------------
    def save_last_as_recipe(self, name: str) -> str:
        """Persist the just-completed task's action trajectory as a replayable recipe."""
        if not self._last_task_steps:
            return "Nothing to save — no completed task with action steps yet."
        recipe = build_recipe(
            name=name,
            task=self._last_task_text or "",
            url=self._last_task_url or "",
            steps=self._last_task_steps,
        )
        path = self.recipes.save(name, recipe)
        return f"Saved recipe {recipe['name']!r} with {len(recipe['steps'])} steps -> {path}"

    def list_recipes(self) -> list[dict]:
        return self.recipes.list()

    async def run_recipe(self, name: str) -> str:
        """Replay a saved recipe through the bridge — no LLM in the loop."""
        if not self.driver:
            raise RuntimeError("Harness not started.")
        recipe = self.recipes.load(name)
        if not recipe:
            return f"No recipe named {name!r}. List with /recipes."
        logger.info(f"Replaying recipe {recipe['name']!r} ({len(recipe['steps'])} steps)")
        outcomes = await replay(self.driver, recipe)
        ok = sum(1 for o in outcomes if o.get("ok"))
        head = f"Recipe {recipe['name']!r}: {ok}/{len(outcomes)} steps OK."
        lines = [f"  step {i+1}: {o.get('tool')} -> "
                 + ("OK" if o.get('ok') else f"FAILED ({o.get('msg')})")
                 for i, o in enumerate(outcomes)]
        return head + "\n" + "\n".join(lines)

    async def close(self):
        # Best-effort: clear any chrome.debugger attachments so the yellow infobar
        # disappears before we drop the bridge. Don't let a stray detach failure
        # block shutdown.
        if self.driver and self.bridge and self.bridge.connected:
            try:
                await self.driver.detach_debugger()
            except Exception as e:
                logger.warn(f"Debugger detach failed (non-fatal): {e}")
        if self.bridge:
            try:
                await self.bridge.stop()
            except Exception as e:
                logger.warn(f"Bridge stop error: {e}")
            finally:
                self.bridge = None
