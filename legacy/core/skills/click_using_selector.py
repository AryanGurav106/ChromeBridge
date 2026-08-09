import asyncio
import inspect
import traceback
from typing import Annotated

from playwright.async_api import ElementHandle
from playwright.async_api import Page

from core.browser_manager import PlaywrightManager
from core.utils.dom_helper import get_element_outer_html
from core.utils.dom_helper import get_page_fingerprint, page_state_changed
from core.utils.dom_mutation_observer import subscribe  # type: ignore
from core.utils.dom_mutation_observer import unsubscribe  # type: ignore
from core.utils.ui_messagetype import MessageType

from core.utils.logger import Logger
logger = Logger()

async def click(bc, selector: Annotated[str, "The properly formed query selector string to identify the element for the click action (e.g. [mmid='114']). When \"mmid\" attribute is present, use it for the query selector."],
                wait_before_execution: Annotated[float, "Optional wait time in seconds before executing the click event logic.", float] = 0.0) -> Annotated[str, "A message indicating success or failure of the click."]:
    """
    Executes a click action on the element matching the given query selector string within the currently open web page.
    If there is no page open, it will raise a ValueError. An optional wait time can be specified before executing the click logic. Use this to wait for the page to load especially when the last action caused the DOM/Page to load.

    Parameters:
    - selector: The query selector string to identify the element for the click action.
    - wait_before_execution: Optional wait time in seconds before executing the click event logic. Defaults to 0.0 seconds.

    Returns:
    - Success if the click was successful, Appropropriate error message otherwise.
    """
    logger.debug(f"Executing ClickElement with \"{selector}\" as the selector")

    # Initialize PlaywrightManager and get the active browser page
    browser_manager = bc
    page = await browser_manager.get_current_page()

    if page is None: # type: ignore
        raise ValueError('No active page found. OpenURL command opens a new page.')

    function_name = inspect.currentframe().f_code.co_name # type: ignore


    await browser_manager.highlight_element(selector, True)

    dom_changes_detected=None
    def detect_dom_changes(changes:str): # type: ignore
        nonlocal dom_changes_detected
        dom_changes_detected = changes # type: ignore

    subscribe(detect_dom_changes)
    fp_before = await get_page_fingerprint(page)
    result = await do_click(page, selector, wait_before_execution)
    await asyncio.sleep(0.1) # sleep for 100ms to allow the mutation observer to detect changes
    unsubscribe(detect_dom_changes)
    fp_after = await get_page_fingerprint(page)

    if dom_changes_detected:
        return f"Success: {result['summary_message']}.\n As a consequence of this action, new elements have appeared in view: {dom_changes_detected}. This means that the action to click {selector} is not yet executed and needs further interaction. Get all_fields DOM to complete the interaction."

    # Action-effect verification: if the click reported success but the page did not
    # change at all (no DOM mutation, same URL, same content), the click likely missed
    # its intended target. Tell the agent so it can self-correct instead of moving on.
    if not page_state_changed(fp_before, fp_after):
        return (
            f"{result['detailed_message']}\n"
            f"WARNING: clicking {selector} produced NO detectable change on the page "
            "(URL, content and DOM are unchanged). The click may not have hit the intended "
            "element. Re-check the element (get_interactive_elements or analyze_screen), "
            "verify it is the right target and not occluded, and try a different mmid if needed."
        )
    return result["detailed_message"]


async def do_click(page: Page, selector: str, wait_before_execution: float) -> dict[str, str]:
    """
    Executes the click action on the element with the given selector within the provided page.

    Parameters:
    - page: The Playwright page instance.
    - selector: The query selector string to identify the element for the click action.
    - wait_before_execution: Optional wait time in seconds before executing the click event logic.

    Returns:
    dict[str,str] - Explanation of the outcome of this operation represented as a dictionary with 'summary_message' and 'detailed_message'.
    """
    logger.debug(f"Executing ClickElement with \"{selector}\" as the selector. Wait time before execution: {wait_before_execution} seconds.")

    # Wait before execution if specified
    if wait_before_execution > 0:
        await asyncio.sleep(wait_before_execution)

    # Wait for the selector to be present and ensure it's attached and visible. If timeout, try javascript click
    try:
        logger.debug(f"Executing ClickElement with \"{selector}\" as the selector. Waiting for the element to be attached and visible.")

        element = await asyncio.wait_for(
            page.wait_for_selector(selector, state="attached", timeout=2000),
            timeout=2000
        )
        if element is None:
            raise ValueError(f"Element with selector: \"{selector}\" not found")

        logger.debug(f"Element with selector: \"{selector}\" is attached. scrolling it into view if needed.")
        try:
            await element.scroll_into_view_if_needed(timeout=200)
            logger.debug(f"Element with selector: \"{selector}\" is attached and scrolled into view. Waiting for the element to be visible.")
        except Exception:
            # If scrollIntoView fails, just move on, not a big deal
            pass

        try:
            await element.wait_for_element_state("visible", timeout=200)
            logger.debug(f"Executing ClickElement with \"{selector}\" as the selector. Element is attached and visibe. Clicking the element.")
        except Exception:
            # If the element is not visible, try to click it anyway
            pass

        element_tag_name = await element.evaluate("element => element.tagName.toLowerCase()")
        element_outer_html = await get_element_outer_html(element, page, element_tag_name)


        if element_tag_name == "option":
            element_value = await element.get_attribute("value") # get the text that is in the value of the option
            parent_element = await element.evaluate_handle("element => element.parentNode")
            # await parent_element.evaluate(f"element => element.select_option(value=\"{element_value}\")")
            await parent_element.select_option(value=element_value) # type: ignore

            logger.debug(f'Select menu option "{element_value}" selected')

            return {"summary_message": f'Select menu option "{element_value}" selected',
                    "detailed_message": f'Select menu option "{element_value}" selected. The select element\'s outer HTML is: {element_outer_html}.'}


        # Prefer Playwright's actionable click: it auto-waits for the element to be
        # Visible, Stable, Enabled, and to actually Receive Events (a hit-test ensures
        # the element itself — not an overlay/cookie-banner — is the top target at the
        # click point). This is what prevents silent mis-clicks on hidden, moving, or
        # covered elements. Only if it fails do we fall back to the legacy JS-dispatch.
        msg = await perform_actionable_click(page, selector)
        return {"summary_message": msg, "detailed_message": f"{msg} The clicked element's outer HTML is: {element_outer_html}."} # type: ignore
    except Exception as e:
        logger.error(f"Unable to click element with selector: \"{selector}\". Error: {e}")
        traceback.print_exc()
        msg = f"Unable to click element with selector: \"{selector}\" since the selector is invalid. Proceed by retrieving DOM again."
        return {"summary_message": msg, "detailed_message": f"{msg}. Error: {e}"}


async def is_element_present(page: Page, selector: str) -> bool:
    """
    Checks if an element is present on the page.

    Parameters:
    - page: The Playwright page instance.
    - selector: The query selector string to identify the element.

    Returns:
    - True if the element is present, False otherwise.
    """
    element = await page.query_selector(selector)
    return element is not None


async def perform_playwright_click(element: ElementHandle, selector: str):
    """
    Performs a click action on the element using Playwright's click method.

    Parameters:
    - element: The Playwright ElementHandle instance representing the element to be clicked.
    - selector: The query selector string of the element.

    Returns:
    - None
    """
    logger.debug(f"Performing first Step: Playwright Click on element with selector: {selector}")
    await element.click(force=False, timeout=200)


async def perform_actionable_click(page: Page, selector: str, timeout: int = 5000) -> str:
    """
    Clicks via Playwright's Locator API, which performs actionability checks
    (visible, stable, enabled, receives-events/hit-test) and auto-waits.

    Falls back to the legacy JavaScript-dispatch click only if the actionable
    click fails (e.g. a genuinely synthetic/non-standard element). The fallback
    is noted in the returned message so the agent/critique can see it happened.

    Parameters:
    - page: The Playwright page instance.
    - selector: Query selector identifying the element (e.g. [mmid='114']).
    - timeout: Max time (ms) to wait for the element to become actionable.

    Returns:
    - str: A message describing the outcome.
    """
    locator = page.locator(selector).first
    try:
        await locator.click(timeout=timeout)
        logger.debug(f"Actionable Playwright click succeeded on: {selector}")
        return f"Executed Playwright click (with actionability checks) on element: {selector}"
    except Exception as e:
        logger.warn(
            f"Actionable click failed for \"{selector}\" ({e}); falling back to JS-dispatch click."
        )
        js_msg = await perform_javascript_click(page, selector)
        return f"{js_msg} (Note: actionability checks did not pass; used JS fallback.)"


async def perform_javascript_click(page: Page, selector: str):
    """
    Performs a click action on the element using JavaScript with enhanced hidden element handling.
    """
    js_code = """(selector) => {
        let element = document.querySelector(selector);
        
        if (!element) {
            console.log(`perform_javascript_click: Element with selector ${selector} not found`);
            return `Element with selector ${selector} not found`;
        }

        const clickElement = (el) => {
            // Store original attributes
            const originalAriaHidden = el.getAttribute('aria-hidden');
            const originalTabIndex = el.getAttribute('tabindex');
            
            // Temporarily remove accessibility blockers
            el.removeAttribute('aria-hidden');
            el.removeAttribute('tabindex');
            
            // Create full click sequence
            const events = [
                new MouseEvent('mousedown', { bubbles: true }),
                new MouseEvent('mouseup', { bubbles: true }),
                new MouseEvent('click', { bubbles: true, cancelable: true })
            ];
            
            // Execute click sequence
            events.forEach(event => el.dispatchEvent(event));
            
            // Restore attributes after 500ms
            setTimeout(() => {
                if (originalAriaHidden) el.setAttribute('aria-hidden', originalAriaHidden);
                if (originalTabIndex) el.setAttribute('tabindex', originalTabIndex);
            }, 500);
        };

        if (element.tagName.toLowerCase() === "option") {
            // Existing option handling remains unchanged
            let value = element.text;
            let parent = element.parentElement;
            parent.value = element.value;
            let event = new Event('change', { bubbles: true });
            parent.dispatchEvent(event);
            return "Select menu option: "+ value+ " selected";
        }
        else {
            // Enhanced click handling for hidden elements
            let isHiddenElement = element.hasAttribute('aria-hidden') || 
                                element.getAttribute('tabindex') === '-1' ||
                                window.getComputedStyle(element).visibility === 'hidden';
            
            if (isHiddenElement) {
                console.log("Detected hidden element, using enhanced click");
                clickElement(element);
                return "Executed enhanced JavaScript Click on hidden element with selector: "+selector;
            }
            else {
                // Existing standard click handling
                if (element.tagName.toLowerCase() === "a") {
                    element.target = "_self";
                }
                let ariaExpandedBefore = element.getAttribute('aria-expanded');
                element.click();
                let ariaExpandedAfter = element.getAttribute('aria-expanded');
                
                if (ariaExpandedBefore === 'false' && ariaExpandedAfter === 'true') {
                    return "Executed JavaScript Click on element. Important: Menu appeared - get DOM to continue.";
                }
                return "Executed standard JavaScript Click on element: "+selector;
            }
        }
    }"""
    
    try:
        logger.debug(f"Executing enhanced JavaScript click on: {selector}")
        result: str = await page.evaluate(js_code, selector)
        return result
    except Exception as e:
        logger.error(f"Error clicking element {selector}: {e}")
        traceback.print_exc()
        return f"Failed to click element: {str(e)}"
