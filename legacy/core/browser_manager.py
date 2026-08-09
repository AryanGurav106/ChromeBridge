"""PlaywrightManager — the browser agent's runtime harness.

This is the standalone, LOCAL-ONLY variant. Compared with the original it has the
remote-browser providers (Browserbase / Steel.dev) and their cloud session
plumbing removed; it always launches a local Chromium/Chrome via Playwright.
Everything the browser agent's skills rely on (page access, screenshots, the DOM
mutation observer, the optional on-page overlay) is preserved.
"""

import asyncio
import os
import tempfile
import time
from enum import Enum
from typing import Optional

from dotenv import load_dotenv
from playwright.async_api import async_playwright as playwright
from playwright.async_api import BrowserContext
from playwright.async_api import Page

from core.utils.custom_exceptions import BrowserNavigationError
from core.utils.notification import NotificationManager
from core.utils.ui_manager import UIManager
from core.utils.dom_mutation_observer import dom_mutation_change_detected
from core.utils.dom_mutation_observer import handle_navigation_for_mutation_observer
from core.utils.js_helper import beautify_plan_message
from core.utils.js_helper import escape_js_message
from core.utils.message_type import MessageType
from config import PROJECT_SOURCE_ROOT

from core.utils.logger import Logger

logger = Logger()

load_dotenv()

# Ensures that playwright does not wait for font loading when taking screenshots.
# Reference: https://github.com/microsoft/playwright/issues/28995
os.environ["PW_TEST_SCREENSHOT_NO_FONTS_READY"] = "1"


class CaptchaType(Enum):
    """Enum for supported CAPTCHA types"""
    HCAPTCHA = "hcaptcha"
    RECAPTCHA = "recaptcha"
    CLOUDFLARE = "cloudflare"


class PlaywrightManager:
    """
    Manages a local Playwright Chromium/Chrome instance and browser context.

    Attributes:
        browser_type (str): The type of browser to use ('chromium').
        isheadless (bool): Flag to launch the browser in headless mode or not.
    """

    def __init__(self,
                 browser_type: str = "chromium",
                 headless: bool = False,
                 gui_input_mode: bool = True,
                 screenshots_dir: str = "",
                 take_screenshots: bool = True,
                 video_dir: str = "",
                 record_video: bool = True,
                 job_ID: str = "",
                 prefix: str = "task",
                 start_url: str = "https://google.com",
                 user_data_dir: Optional[str] = None):
        """
        Initializes the PlaywrightManager.

        Args:
            user_data_dir: Optional path to a persistent Chrome profile directory.
                If None, a throwaway temp profile is used for each run. Set this to
                your real Chrome profile (chrome://version/ -> "Profile Path") to
                reuse existing logins. Can also be supplied via BROWSER_STORAGE_DIR.
        """
        self._homepage = start_url
        self._instance = None
        self._playwright = None
        self._browser = None
        self._browser_context = None
        self.__async_initialize_done = False
        self._take_screenshots = False
        self._screenshots_dir = None
        self._record_video = True
        self._video_dir = None
        self.prefix = prefix

        self.browser_type = browser_type
        self.isheadless = headless
        self.notification_manager = NotificationManager()
        self.user_response_event = asyncio.Event()
        self.ui_manager = None

        self._user_data_dir = user_data_dir or os.getenv("BROWSER_STORAGE_DIR") or None

        # Remote providers are intentionally unsupported in the standalone build.
        # These attributes are kept (always None) so legacy code paths stay inert.
        self.steeldev = None
        self.steeldev_client = None
        self.steel_live_url = None
        self.browserbase = None
        self.browserbase_client = None
        self.bb_live_url = None

        if gui_input_mode:
            self.ui_manager = UIManager()
        self.job_ID = job_ID

        # Set up temp directory for all file storage
        temp_dir = os.path.join(PROJECT_SOURCE_ROOT, "temp")
        os.makedirs(temp_dir, exist_ok=True)

        # Create job-specific directory if job_ID is provided
        if self.job_ID:
            self.job_dir = os.path.join(temp_dir, f"{self.prefix}_{self.job_ID}")
        else:
            self.job_dir = temp_dir
        os.makedirs(self.job_dir, exist_ok=True)

        # Set screenshot directory
        self.set_take_screenshots(take_screenshots)
        self.set_screenshots_dir(os.path.join(temp_dir, "screenshots"))

        # Local video recording
        self.set_video_recording(record_video)
        self.set_video_dir(self.job_dir)

    def set_video_recording(self, record_video: bool):
        self._record_video = record_video

    def get_video_recording(self):
        return self._record_video

    def set_video_dir(self, video_dir: str):
        self._video_dir = video_dir

    def get_video_dir(self):
        return self._video_dir

    async def async_initialize(self):
        """Asynchronously initialize necessary components and handlers."""
        try:
            if self.__async_initialize_done:
                return

            await self.start_playwright()
            await self.ensure_browser_context()
            await self.setup_handlers()
            await self.go_to_homepage()

            self.__async_initialize_done = True
            logger.info("PlaywrightManager initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize PlaywrightManager: {str(e)}")
            raise RuntimeError(f"Failed to initialize PlaywrightManager: {str(e)}") from e

    async def ensure_browser_context(self):
        """Ensure that a browser context exists, creating it if necessary."""
        if self._browser_context is None:
            await self.create_browser_context()

    async def setup_handlers(self):
        """Setup handlers after the browser context has been ensured.

        The DOM-mutation observer is always installed (the click/enter-text skills
        depend on it to detect newly-appearing elements). The overlay handlers are
        only installed when the on-page GUI overlay is enabled.
        """
        await self.set_navigation_handler()
        if self.ui_manager:
            await self.set_overlay_state_handler()
            await self.set_user_response_handler()

    async def start_playwright(self):
        """Starts the Playwright instance if it hasn't been started yet. Idempotent."""
        try:
            if not self._playwright:
                logger.info("Starting new playwright instance")
                self._playwright = await playwright().start()
                if not self._playwright:
                    raise RuntimeError("Failed to start playwright")
                logger.info("Playwright instance started successfully")
        except Exception as e:
            logger.error(f"Failed to start playwright: {str(e)}")
            raise RuntimeError(f"Failed to start playwright: {str(e)}") from e

    async def stop_playwright(self):
        """Stops the Playwright instance and cleans up resources."""
        logger.info("Beginning Playwright cleanup process...")
        try:
            if self._browser_context is not None:
                try:
                    logger.info("Cleaning up browser context...")
                    await self._browser_context.close()
                    logger.info("Browser context cleaned up successfully")
                except Exception as e:
                    logger.warn(f"Non-critical error during context cleanup: {str(e)}")
                finally:
                    self._browser_context = None

            if getattr(self, "_browser", None):
                try:
                    logger.info("Closing browser instance...")
                    await self._browser.close()
                    logger.info("Browser instance closed successfully")
                except Exception as e:
                    logger.warn(f"Non-critical error during browser cleanup: {str(e)}")

            if self._playwright is not None:
                try:
                    logger.info("Stopping Playwright instance...")
                    await self._playwright.stop()
                    logger.info("Playwright instance stopped successfully")
                except Exception as e:
                    logger.warn(f"Non-critical error during playwright cleanup: {str(e)}")
                finally:
                    self._playwright = None
        except Exception as e:
            logger.error(f"Error during Playwright cleanup: {str(e)}")
        finally:
            logger.info("Playwright cleanup process completed")

    async def navigate_to_url(self, url: str):
        """Navigate to the specified URL."""
        try:
            url = "https://" + url if not url.startswith(("http://", "https://")) else url
            page = await self.get_current_page()
            await page.goto(url)
            logger.debug(f"Successfully navigated to {url}")
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {str(e)}")
            raise

    async def create_browser_context(self):
        """Creates a new local browser context."""
        try:
            if not self._playwright:
                await self.start_playwright()
            if not self._playwright:
                raise RuntimeError("Failed to initialize Playwright")

            user_dir = self._user_data_dir or tempfile.mkdtemp()

            record_video_options = {}
            if self._record_video and self._video_dir:
                os.makedirs(self._video_dir, exist_ok=True)
                record_video_options = {
                    "record_video_dir": self._video_dir,
                    "record_video_size": {"width": 640, "height": 480},
                }
                logger.info("Local video recording enabled", video_dir=self._video_dir)

            if self.browser_type != "chromium":
                raise ValueError(f"Unsupported browser type: {self.browser_type}")

            logger.debug(f"Launching local browser with profile dir: {user_dir}")
            await self._launch_local_browser_with_retry(user_dir, record_video_options)

        except Exception as e:
            logger.error(f"Browser context creation failed: {str(e)}")
            raise

    async def _launch_local_browser_with_retry(self, initial_user_dir: str, record_video_options: dict):
        """Local browser launch with directory + channel fallback logic."""
        try:
            self._browser_context = await self._launch_local_browser(initial_user_dir, record_video_options)
        except Exception as e:
            msg = str(e)
            if "Target page, context or browser has been closed" in msg:
                new_user_dir = tempfile.mkdtemp()
                logger.warn(f"Retrying with new profile directory: {new_user_dir}")
                if not self._playwright:
                    await self.start_playwright()
                self._browser_context = await self._launch_local_browser(new_user_dir, record_video_options)
            elif "is not found" in msg or "channel" in msg.lower() or "executable doesn't exist" in msg.lower():
                # Installed Chrome ("chrome" channel) not available — fall back to the
                # Chromium that ships with Playwright (`playwright install chromium`).
                logger.warn("Chrome channel unavailable, falling back to bundled Chromium")
                self._browser_context = await self._launch_local_browser(
                    initial_user_dir, record_video_options, use_chrome_channel=False
                )
            else:
                raise

    async def _launch_local_browser(self, user_dir: str, record_video_options: dict,
                                     use_chrome_channel: bool = True) -> BrowserContext:
        """Launch a local Chrome/Chromium persistent context."""
        if not self._playwright:
            raise RuntimeError("Playwright not initialized")

        launch_kwargs = dict(
            bypass_csp=True,
            headless=self.isheadless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-session-crashed-bubble",
                "--disable-infobars",
            ],
            no_viewport=True,
            **record_video_options,
        )
        if use_chrome_channel:
            launch_kwargs["channel"] = "chrome"

        return await self._playwright.chromium.launch_persistent_context(user_dir, **launch_kwargs)

    async def get_browser_context(self):
        """Returns the existing browser context, creating one if needed."""
        await self.ensure_browser_context()
        return self._browser_context

    async def get_current_url(self) -> Optional[str]:
        try:
            current_page: Page = await self.get_current_page()
            return current_page.url
        except Exception:
            pass
        return None

    async def get_current_page(self) -> Page:
        """Get the current page of the browser with error handling."""
        try:
            browser: BrowserContext = await self.get_browser_context()
            pages = [page for page in browser.pages if not page.is_closed()]
            page = pages[-1] if pages else None
            logger.debug(f"Current page: {page.url if page else None}")
            if page is not None:
                return page
            page = await browser.new_page()
            return page
        except Exception:
            logger.error("Browser context was closed. Creating a new one.")
            try:
                page = await browser.new_page()
                return page
            except Exception as e:
                logger.error(f"Failed to create new page: {e}")
                raise BrowserNavigationError("Browser context was closed or new page creation failed")

    async def close_all_tabs(self, keep_first_tab: bool = True):
        browser_context = await self.get_browser_context()
        pages = browser_context.pages
        pages_to_close = pages[1:] if keep_first_tab else pages
        for page in pages_to_close:
            await page.close()

    async def close_except_specified_tab(self, page_to_keep: Page):
        browser_context = await self.get_browser_context()
        for page in browser_context.pages:
            if page != page_to_keep:
                await page.close()

    async def go_to_homepage(self):
        await self.navigate_to_url(self._homepage)

    async def set_navigation_handler(self):
        page: Page = await self.get_current_page()
        if self.ui_manager:
            page.on("domcontentloaded", self.ui_manager.handle_navigation)
        page.on("domcontentloaded", handle_navigation_for_mutation_observer)
        await page.expose_function("dom_mutation_change_detected", dom_mutation_change_detected)

    async def set_overlay_state_handler(self):
        logger.debug("Setting overlay state handler")
        context = await self.get_browser_context()
        await context.expose_function("overlay_state_changed", self.overlay_state_handler)
        await context.expose_function("show_steps_state_changed", self.show_steps_state_handler)

    async def overlay_state_handler(self, is_collapsed: bool):
        if not self.ui_manager:
            return
        page = await self.get_current_page()
        self.ui_manager.update_overlay_state(is_collapsed)
        if not is_collapsed:
            await self.ui_manager.update_overlay_chat_history(page)

    async def show_steps_state_handler(self, show_details: bool):
        if not self.ui_manager:
            return
        page = await self.get_current_page()
        await self.ui_manager.update_overlay_show_details(show_details, page)

    async def set_user_response_handler(self):
        context = await self.get_browser_context()
        await context.expose_function("user_response", self.receive_user_response)

    async def notify_user(self, message: str, message_type: MessageType = MessageType.STEP):
        if not self.ui_manager:
            return
        logger.info(f"Notify user: {message}", message_type=str(message_type))

        if message.startswith(":"):
            message = message[1:]
        if message.endswith(","):
            message = message[:-1]

        if message_type == MessageType.PLAN:
            message = beautify_plan_message(message)
            message = "Plan:\n" + message
        elif message_type == MessageType.STEP:
            if "confirm" in message.lower():
                message = "Verify: " + message
            else:
                message = "Next step: " + message
        elif message_type == MessageType.QUESTION:
            message = "Question: " + message
        elif message_type == MessageType.ANSWER:
            message = "Response: " + message

        safe_message = escape_js_message(message)
        self.ui_manager.new_system_message(safe_message, message_type)

        if self.ui_manager.overlay_show_details is False:
            if message_type not in (MessageType.PLAN, MessageType.QUESTION, MessageType.ANSWER, MessageType.INFO):
                return
        if self.ui_manager.overlay_show_details is True:
            if message_type not in (MessageType.PLAN, MessageType.QUESTION, MessageType.ANSWER,
                                    MessageType.INFO, MessageType.STEP):
                return

        safe_message_type = escape_js_message(message_type.value)
        try:
            js_code = f"addSystemMessage({safe_message}, is_awaiting_user_response=false, message_type={safe_message_type});"
            page = await self.get_current_page()
            await page.evaluate(js_code)
        except Exception as e:
            logger.error(f'Failed to notify user with message "{message}". '
                         f"This usually resolves after the page loads: {e}")

        self.notification_manager.notify(message, message_type.value)

    async def highlight_element(self, selector: str, add_highlight: bool):
        try:
            page: Page = await self.get_current_page()
            if add_highlight:
                await page.eval_on_selector(selector, '''e => {
                            let originalBorderStyle = e.style.border;
                            e.classList.add('tawebagent-ui-automation-highlight');
                            e.addEventListener('animationend', () => {
                                e.classList.remove('tawebagent-ui-automation-highlight')
                            });}''')
                logger.debug(f"Applied highlight to {selector}")
            else:
                await page.eval_on_selector(selector, "e => e.classList.remove('tawebagent-ui-automation-highlight')")
                logger.debug(f"Removed highlight from {selector}")
        except Exception:
            pass

    async def receive_user_response(self, response: str):
        self.user_response = response
        logger.debug(f"Received user response to system prompt: {response}")
        self.user_response_event.set()

    async def prompt_user(self, message: str) -> str:
        if not self.ui_manager:
            return ""
        logger.debug(f'Prompting user with message: "{message}"')
        page = await self.get_current_page()
        await self.ui_manager.show_overlay(page)
        self.log_system_message(message, MessageType.QUESTION)
        safe_message = escape_js_message(message)
        js_code = f"addSystemMessage({safe_message}, is_awaiting_user_response=true, message_type='question');"
        await page.evaluate(js_code)
        await self.user_response_event.wait()
        result = self.user_response
        logger.info(f'User prompt response to "{message}": {result}')
        self.user_response_event.clear()
        self.user_response = ""
        self.ui_manager.new_user_message(result)
        return result

    def set_take_screenshots(self, take_screenshots: bool):
        self._take_screenshots = take_screenshots

    def get_take_screenshots(self):
        return self._take_screenshots

    def set_screenshots_dir(self, screenshots_dir: str):
        if not screenshots_dir:
            screenshots_dir = os.path.join(PROJECT_SOURCE_ROOT, "temp", "screenshots")
        screenshots_dir = os.path.abspath(screenshots_dir)
        os.makedirs(screenshots_dir, exist_ok=True)
        self._screenshots_dir = screenshots_dir
        logger.debug(f"Screenshots directory set to: {screenshots_dir}")

    def get_screenshots_dir(self):
        return self._screenshots_dir

    async def take_screenshots(self, name: str, page: Optional[Page], full_page: bool = True,
                               include_timestamp: bool = True, load_state: str = "domcontentloaded",
                               take_snapshot_timeout: int = 15 * 1000):
        """Take screenshots with stability and state handling."""
        if not self._take_screenshots or not self._screenshots_dir:
            return
        if page is None:
            page = await self.get_current_page()

        screenshot_name = name
        if include_timestamp:
            screenshot_name = f"{int(time.time_ns())}_{screenshot_name}"
        screenshot_name += ".png"
        screenshot_path = os.path.join(self._screenshots_dir, screenshot_name)

        try:
            await page.wait_for_load_state(state=load_state, timeout=take_snapshot_timeout)
            await asyncio.sleep(0.5)

            max_retries = 2
            retry_delay = 1
            for attempt in range(max_retries):
                try:
                    await page.wait_for_load_state(state=load_state, timeout=take_snapshot_timeout)
                    await asyncio.sleep(0.5)
                    await page.screenshot(
                        path=screenshot_path,
                        full_page=full_page,
                        timeout=take_snapshot_timeout,
                        caret="initial",
                        scale="device",
                        animations="disabled",
                        mask_color="#FF000000",
                    )
                    logger.debug(f"Screenshot saved to: {screenshot_path}")
                    return screenshot_path
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warn(f"Screenshot attempt {attempt + 1} failed. Retrying... Error: {e}")
                        await asyncio.sleep(retry_delay)
                        await page.reload()
                        continue
                    logger.error(f"Failed to take screenshot after {max_retries} attempts: {e}")
                    return None
        except Exception as e:
            logger.error(f'Failed to take screenshot and save to "{screenshot_path}". Error: {e}')
            return None

    def log_user_message(self, message: str):
        if not self.ui_manager:
            return
        self.ui_manager.new_user_message(message)

    def log_system_message(self, message: str, type: MessageType = MessageType.STEP):
        if not self.ui_manager:
            return
        self.ui_manager.new_system_message(message, type)

    async def update_processing_state(self, processing_state: str):
        if not self.ui_manager:
            return
        page = await self.get_current_page()
        await self.ui_manager.update_processing_state(processing_state, page)

    async def command_completed(self, command: str, elapsed_time: Optional[float] = None):
        if not self.ui_manager:
            return
        logger.debug(f'Command "{command}" completed.')
        page = await self.get_current_page()
        await self.ui_manager.command_completed(page, command, elapsed_time)
