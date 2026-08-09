import asyncio

from playwright.async_api import ElementHandle
from playwright.async_api import Page
from core.utils.logger import Logger
logger = Logger()
async def wait_for_non_loading_dom_state(page: Page, max_wait_millis: int):
    max_wait_seconds = max_wait_millis / 1000

    # If a navigation is in flight (e.g. a search was just submitted), evaluating
    # JS races the execution context being destroyed. Let Playwright settle the
    # navigation first; this is best-effort and safe if nothing is navigating.
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=max_wait_millis)
    except Exception:
        pass

    end_time = asyncio.get_event_loop().time() + max_wait_seconds
    while asyncio.get_event_loop().time() < end_time:
        try:
            dom_state = await page.evaluate("document.readyState")
        except Exception as e:
            # "Execution context was destroyed, most likely because of a
            # navigation" — wait for the new document, then retry rather than
            # crashing the whole task.
            logger.debug(f"readyState eval raced a navigation ({e}); waiting for load.")
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=max_wait_millis)
            except Exception:
                pass
            await asyncio.sleep(0.1)
            continue
        if dom_state != "loading":
            logger.debug(f"DOM state is not 'loading': {dom_state}")
            break  # Exit the loop if the DOM state is not 'loading'

        await asyncio.sleep(0.05)


async def get_page_fingerprint(page: Page) -> dict:
    """Cheap snapshot of page state used to detect whether an action had any effect.

    Returns url + visible-text length + element count. Compared before/after an
    action: if nothing changed (and no DOM mutation fired), the action likely
    didn't do what the agent intended, so we can tell the agent to self-correct.
    """
    try:
        data = await page.evaluate(
            """() => ({
                url: location.href,
                textLen: (document.body ? document.body.innerText.length : 0),
                elements: document.querySelectorAll('*').length
            })"""
        )
        return data or {}
    except Exception:
        return {}


def page_state_changed(before: dict, after: dict) -> bool:
    """True if the two fingerprints differ meaningfully."""
    if not before or not after:
        return True  # be permissive when we couldn't measure
    if before.get("url") != after.get("url"):
        return True
    # treat a >2% swing in text length or any element-count change as a real change
    bt, at = before.get("textLen", 0), after.get("textLen", 0)
    if abs(at - bt) > max(20, 0.02 * max(bt, 1)):
        return True
    if before.get("elements") != after.get("elements"):
        return True
    return False


async def get_element_outer_html(element: ElementHandle, page: Page, element_tag_name: str|None = None) -> str:
    """
    Constructs the opening tag of an HTML element along with its attributes.

    Args:
        element (ElementHandle): The element to retrieve the opening tag for.
        page (Page): The page object associated with the element.
        element_tag_name (str, optional): The tag name of the element. Defaults to None. If not passed, it will be retrieved from the element.

    Returns:
        str: The opening tag of the HTML element, including a select set of attributes.
    """
    tag_name: str = element_tag_name if element_tag_name else await page.evaluate("element => element.tagName.toLowerCase()", element)

    attributes_of_interest: list[str] = ['id', 'name', 'aria-label', 'placeholder', 'href', 'src', 'aria-autocomplete', 'role', 'type',
                                         'data-testid', 'value', 'selected', 'aria-labelledby', 'aria-describedby', 'aria-haspopup']
    opening_tag: str = f'<{tag_name}'

    for attr in attributes_of_interest:
        value: str = await element.get_attribute(attr) # type: ignore
        if value:
            opening_tag += f' {attr}="{value}"'
    opening_tag += '>'

    return opening_tag
