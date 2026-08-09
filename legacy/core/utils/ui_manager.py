import os
import traceback
import json
from playwright.async_api import Frame
from playwright.async_api import Page

from config import PROJECT_SOURCE_ROOT
from core.utils.js_helper import escape_js_message
from core.utils.message_type import MessageType
from core.utils.logger import Logger
logger = Logger()

class UIManager:
    """
    Manages the UI overlay for this application. The application uses playwright for the browser driver.
    This includes handling navigation events, showing or hiding overlays, and maintaining
    a conversation history within the UI overlay.

    Attributes:
        overlay_is_collapsed (bool): Indicates if the overlay is currently collapsed.
        conversation_history (list[dict[str, str]]): The chat history between user and system. Each entry contains 'from' and 'message' keys.
        __update_overlay_chat_history_running (bool): A flag to prevent concurrent updates to the chat history.
    """

    overlay_is_collapsed: bool = True

    overlay_processing_state: str = "init"  #init: initialised, processing: processing is ongoing, done: processing is done
    overlay_show_details:bool = True

    conversation_history:list[dict[str, str]] = []
    __update_overlay_chat_history_running: bool = False


    def __init__(self):
        """
        Initializes the UIManager instance by adding default system messages to the conversation history.
        """
        self.add_default_system_messages()


    async def handle_navigation(self, frame: Frame):
        """
        Handles navigation events by injecting JavaScript code into the frame to manage the overlay state
        and updating the overlay chat history.

        Args:
            frame (Frame): The Playwright Frame object to inject JavaScript into and manage.
        """
        try:
            await frame.wait_for_load_state("load")
            overlay_injection_file = os.path.join(PROJECT_SOURCE_ROOT,"core", "utils", "ui", "injectOverlay.js") 
            with open(overlay_injection_file, 'r') as file:  # noqa: UP015
                js_code = file.read()

            # Inject the JavaScript code into the page
            await frame.evaluate(js_code)
            js_bool = str(self.overlay_show_details).lower()
            if self.overlay_is_collapsed:
                await frame.evaluate(f"showCollapsedOverlay('{self.overlay_processing_state}', {js_bool});")
            else:
                await frame.evaluate(f"showExpandedOverlay('{self.overlay_processing_state}', {js_bool});")

            #update chat history in the overlay
            await self.update_overlay_chat_history(frame)

        except Exception as e:
            if "Frame was detached" not in str(e):
                raise e


    async def show_overlay(self, page: Page):
        """
        Displays the overlay in an expanded state on the given page if it's currently collapsed.

        Args:
            page (Page): The Playwright Page object on which to show the overlay.
        """
        if not self.overlay_is_collapsed:
            logger.debug("Overlay is already expanded, ignoring show_overlay call")
            return
        await page.evaluate("showExpandedOverlay();")
        self.overlay_is_collapsed = True


    def update_overlay_state(self, is_collapsed: bool):
        """
        Updates the state of the overlay to either collapsed or expanded.

        Args:
            is_collapsed (bool): True to collapse the overlay, False to expand it.
        """
        self.overlay_is_collapsed = is_collapsed



    async def update_overlay_show_details(self, show_details: bool, page: Page):
        """
        Updates the state of the overlay to either show steps or not.

        Args:
            show_steps (bool): True to show steps, False to hide them.
        """
        self.overlay_show_details = show_details
        await self.update_overlay_chat_history(page)


    async def update_processing_state(self, state: str, page: Page):
        """
        Updates the processing state of the overlay.

        Args:
            state (str): The processing state to update.
        """
        self.overlay_processing_state = state
        try:
            js_bool = str(self.overlay_is_collapsed).lower()
            await page.evaluate(f"updateOverlayState('{self.overlay_processing_state}', {js_bool});")
        except Exception as e:
            logger.debug(f"JavaScript error: {e}")



    async def update_overlay_chat_history(self, frame_or_page: Frame | Page):
        if self.overlay_is_collapsed:
            logger.debug("Overlay is collapsed, not updating chat history")
            return
        if self.__update_overlay_chat_history_running:
            logger.debug("update_overlay_chat_history is already running, returning" + frame_or_page.url)
            return

        self.__update_overlay_chat_history_running = True
        try:
            await frame_or_page.evaluate("clearOverlayMessages();")
            for message in self.conversation_history:
                try:
                    if not isinstance(message, dict) or "message" not in message or "from" not in message:
                        logger.warn(f"Invalid message format: {message}")
                        continue

                    # Properly escape the message content for JavaScript
                    message_content = json.dumps(str(message["message"]))
                    
                    if message["from"] == "user":
                        try:
                            js_code = f"addUserMessage({message_content});"
                            await frame_or_page.evaluate(js_code)
                        except Exception as e:
                            logger.error(f"Failed to add user message: {e}")
                        continue

                    message_type = message.get("message_type", MessageType.STEP.value)
                    message_type_json = json.dumps(str(message_type))

                    # Only filter system messages, not user messages
                    if not self.overlay_show_details and message_type == MessageType.STEP.value:
                        continue

                    # Create JavaScript code with proper JSON string literals
                    try:
                        js_code = f"addSystemMessage({message_content}, false, {message_type_json});"
                        await frame_or_page.evaluate(js_code)
                    except Exception as e:
                        logger.error(f"Failed to evaluate system message: {e}\nCode: {js_code}")
                        try:
                            # Try fallback with default message type
                            fallback_code = f"addSystemMessage({message_content}, false, 'step');"
                            await frame_or_page.evaluate(fallback_code)
                        except Exception as fallback_error:
                            logger.error(f"Fallback also failed: {fallback_error}")

                except Exception as msg_error:
                    logger.error(f"Error processing message: {msg_error}")
                    continue
            
            logger.debug("Chat history updated in overlay, removing update lock flag")
        except Exception as e:
            logger.error(f"Error in update_overlay_chat_history: {e}")
            traceback.print_exc()
        finally:
            self.__update_overlay_chat_history_running = False


    def clear_conversation_history(self):
        """
        Clears the conversation history.
        """
        self.conversation_history = []
        self.add_default_system_messages()

    def get_conversation_history(self):
        """
        Returns the current conversation history.

        Returns:
            list[dict[str, str]]: The conversation history.
        """
        return self.conversation_history


    def new_user_message(self, message: str):
        """
        Adds a new user message to the conversation history.

        Args:
            message (str): The message text to add.
        """

        self.conversation_history.append({"from":"user", "message":message})


    def new_system_message(self, message: str, type:MessageType=MessageType.STEP):
        """
        Adds a new system message to the conversation history.

        Args:
            message (str): The message text to add.
        """

        self.conversation_history.append({"from":"system", "message":message, "message_type":type.value})
        print(f"Adding system message: {message}")

    def add_default_system_messages(self):
        """
        Adds default system messages to the conversation history to greet the user or provide initial instructions.
        """
        pass

    async def command_completed(self, page: Page, command: str, elapsed_time: float|None = None):
        """
        Handles the completion of a command, focusing on the overlay input and indicating that the command has finished.

        Args:
            page (Page): The Playwright Page object where the command was executed.
            command (str): The command that was completed.
            elapsed_time (float | None, optional): The time taken to complete the command, if relevant.
        """
        if not self.overlay_is_collapsed:
            await page.evaluate("focusOnOverlayInput();")
            await page.evaluate("commandExecutionCompleted();")