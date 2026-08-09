import json
import os
import re
import traceback
from typing import Annotated
from typing import Any
from config import PROJECT_SOURCE_ROOT
from playwright.async_api import Page
import aiofiles
import time  # Add this for timestamp tracking
from core.browser_manager import PlaywrightManager
from core.utils.logger import Logger
logger = Logger()

space_delimited_mmid = re.compile(r'^[\d ]+$')


def is_space_delimited_mmid(s: str) -> bool:
    """
    Check if the given string matches the the mmid pattern of number space repeated.

    Parameters:
    - s (str): The string to check against the pattern.

    Returns:
    - bool: True if the string matches the pattern, False otherwise.
    """
    # Use fullmatch() to ensure the entire string matches the pattern
    return bool(space_delimited_mmid.fullmatch(s))


async def __inject_attributes(page: Page):
    last_mmid = await page.evaluate("""() => {
        const tags_to_ignore = ['head', 'style', 'script', 'link', 'meta', 'noscript', 'template', 'iframe', 'g', 'main', 'c-wiz', 'path'];
        const ids_to_ignore = ['agentDriveAutoOverlay'];
        const allElements = document.querySelectorAll('*');
        let id = 0;
        allElements.forEach(element => {
            const tagName = element.tagName.toLowerCase();
            if (tags_to_ignore.includes(tagName) || ids_to_ignore.includes(element.id)) return;
            const origAriaAttribute = element.getAttribute('aria-keyshortcuts');
            const mmid = `${++id}`;
            element.setAttribute('mmid', mmid);
            element.setAttribute('aria-keyshortcuts', mmid);
            const origAriaHidden = element.getAttribute('aria-hidden');
            if (origAriaHidden) {
                element.setAttribute('data-orig-aria-hidden', origAriaHidden);
                element.removeAttribute('aria-hidden');
            }
            const origTabIndex = element.getAttribute('tabindex');
            if (origTabIndex === '-1') {
                element.setAttribute('data-orig-tabindex', origTabIndex);
                element.removeAttribute('tabindex');
            }
            if (tagName === 'button') {
                element.removeAttribute('aria-hidden');
                if (origTabIndex === '-1') element.removeAttribute('tabindex');
            }
            if (origAriaAttribute) element.setAttribute('orig-aria-keyshortcuts', origAriaAttribute);
        });
        return id;
    }""")
    logger.debug(f"Added MMID into {last_mmid} elements")




async def __fetch_dom_info(page: Page, accessibility_tree: dict[str, Any], only_input_fields: bool):
    dom_data = await page.evaluate("""() => {
        const allElements = document.querySelectorAll('[mmid]');
        const elementsData = {};
        const attributes = ['name', 'aria-label', 'placeholder', 'mmid', 'id', 'for', 'data-testid', 'role', 'class', 'tabindex', 'test-id', 'aria-hidden'];

        const isClickable = (el) => {
            if (!el) return false;
            try {
                if (el.tagName.toLowerCase() === 'button' || el.tagName.toLowerCase() === 'a') return true;
                if (el.onclick != null) return true;
                if (el.getAttribute('role') === 'button' || el.getAttribute('role') === 'link' || el.getAttribute('role') === 'tab') return true;
                if (el.hasAttribute('tabindex')) return true;
                const className = (el.className || '').toLowerCase();
                if (className.includes('trigger') || className.includes('clickable')) return true;
                if (el.querySelector('svg') !== null) return true;
                const style = window.getComputedStyle(el);
                if (style.cursor === 'pointer') return true;
                return false;
            } catch (e) {
                console.error('Error checking clickability:', e);
                return false;
            }
        };

        allElements.forEach(element => {
            const mmid = element.getAttribute('mmid');
            if (!mmid) return;
            const tagName = element.tagName.toLowerCase();
            let data = { 'tag': tagName };

            if (isClickable(element)) {
                data['is_clickable'] = true;
                data['class'] = element.className;
                const svgElement = element.querySelector('svg');
                if (svgElement) {
                    data['has_svg'] = true;
                    data['role'] = data['role'] || 'button';
                }
            }

            if (tagName === 'input') {
                data['tag_type'] = element.type;
            } else if (tagName === 'select') {
                data['options'] = Array.from(element.options).map(option => ({
                    'mmid': option.getAttribute('mmid'),
                    'text': option.text,
                    'value': option.value,
                    'selected': option.selected
                }));
            }

            attributes.forEach(attr => {
                const value = element.getAttribute(attr);
                if (value) data[attr] = value;
            });

            if (!data['role']) {
                const elementRole = element.getAttribute('role') || element.role;
                if (elementRole) data['role'] = elementRole;
            }

            data['description'] = element.innerText;

            const role = element.getAttribute('role');
            if (role === 'listbox' || tagName === 'ul') {
                const children = Array.from(element.children).filter(child => child.getAttribute('role') === 'option');
                const attributes_to_include = ['mmid', 'role', 'aria-label', 'value'];
                data['additional_info'] = children.map(child => {
                    const child_data = {};
                    attributes_to_include.forEach(attr => {
                        const value = child.getAttribute(attr);
                        if (value) child_data[attr] = value;
                    });
                    return child_data;
                });
            }

            if (tagName === 'button' && element.innerText.trim() === '') {
                const children = element.children;
                const attributes_to_exclude = ['width', 'height', 'path', 'class', 'viewBox', 'mmid'];
                data['additional_info'] = Array.from(children).map(child => {
                    const child_data = {};
                    for (const attr of child.attributes) {
                        if (!attributes_to_exclude.includes(attr.name)) {
                            child_data[attr.name] = attr.value;
                        }
                    }
                    return child_data;
                });
            }

            // --- UI / spatial signals the accessibility tree alone does not capture ---
            // These give the agent layout, on-screen visibility, and true clickability.
            try {
                const rect = element.getBoundingClientRect();
                const cs = window.getComputedStyle(element);
                const vw = window.innerWidth || document.documentElement.clientWidth;
                const vh = window.innerHeight || document.documentElement.clientHeight;

                const visible = rect.width > 0 && rect.height > 0 &&
                                cs.visibility !== 'hidden' && cs.display !== 'none' &&
                                parseFloat(cs.opacity || '1') > 0;
                const inViewport = rect.bottom > 0 && rect.right > 0 &&
                                   rect.top < vh && rect.left < vw;

                data['box'] = {
                    x: Math.round(rect.left), y: Math.round(rect.top),
                    w: Math.round(rect.width), h: Math.round(rect.height)
                };
                data['visible'] = visible;
                data['in_viewport'] = inViewport;
                if (cs.cursor === 'pointer') data['cursor_pointer'] = true;

                // True clickability: is THIS element (or a child/ancestor) the top hit
                // target at its own center? Catches overlays/modals/cookie banners that
                // visually cover an element so the agent doesn't try to click through them.
                if (visible && inViewport) {
                    const cx = rect.left + rect.width / 2;
                    const cy = rect.top + rect.height / 2;
                    const topEl = document.elementFromPoint(cx, cy);
                    if (topEl) {
                        data['clickable_at_point'] = (
                            topEl === element || element.contains(topEl) || topEl.contains(element)
                        );
                    }
                }
            } catch (e) { /* geometry is best-effort; never fail the whole snapshot */ }

            elementsData[mmid] = data;
        });
        return elementsData;
    }""")

    logger.debug("DOM data fetched, processing accessibility tree")

    # Process the tree using the pre-fetched data
    def process_node(node: dict[str, Any]):
        if 'children' in node:
            for child in node['children']:
                process_node(child)

        mmid_temp: str = node.get('keyshortcuts')
        if mmid_temp and is_space_delimited_mmid(mmid_temp):
            mmid_temp = mmid_temp.split(' ')[-1]

        try:
            mmid = int(mmid_temp)
        except (ValueError, TypeError):
            return node.get('name')

        if node['role'] == 'menuitem':
            return node.get('name')

        if node.get('role') == 'dialog' and node.get('modal') == True:
            node["important information"] = "This is a modal dialog. Please interact with this dialog and close it to be able to interact with the full page (e.g. by pressing the close button or selecting an option)."

        if mmid:
            if 'keyshortcuts' in node:
                del node['keyshortcuts']
            node["mmid"] = mmid
            element_data = dom_data.get(str(mmid))
            if element_data:
                node.update(element_data)
                # Apply the same cleanup logic as the original.
                # `name`/`description`/`aria-label` may be present but None on some
                # AX nodes, so normalize to strings before any .replace()/`in` checks.
                _name = node.get('name'); _name = _name if isinstance(_name, str) else ''
                _desc = node.get('description'); _desc = _desc if isinstance(_desc, str) else ''
                _aria = node.get('aria-label'); _aria = _aria if isinstance(_aria, str) else ''
                if node.get('name') == str(mmid) and node.get('role') != "textbox":
                    node.pop('name', None)
                if 'name' in node and 'description' in node and (_name == _desc or _name == _desc.replace('\n', ' ') or _desc.replace('\n', '') in _name):
                    node.pop('description', None)
                if 'name' in node and 'aria-label' in node and _aria in _name:
                    node.pop('aria-label', None)
                if 'name' in node and 'text' in node and node['name'] == node['text']:
                    node.pop('text', None)
                if node.get('tag') == "select":
                    node.pop("children", None)
                    node.pop("role", None)
                    node.pop("description", None)
                if node.get('role') == node.get('tag'):
                    node.pop('role', None)
                if node.get("aria-label") and node.get("placeholder") and node.get("aria-label") == node.get("placeholder"):
                    node.pop("aria-label", None)
                if node.get("role") == "link":
                    node.pop("role", None)
                    if node.get("description"):
                        node["text"] = node["description"]
                        node.pop("description", None)
                attributes_to_delete = ["level", "multiline", "haspopup"]
                for attr in attributes_to_delete:
                    node.pop(attr, None)
            else:
                logger.debug(f"No data found for mmid: {mmid}, marking for deletion")
                node["marked_for_deletion_by_mm"] = True

    process_node(accessibility_tree)
    pruned_tree = __prune_tree(accessibility_tree, only_input_fields)
    logger.debug("Reconciliation complete")
    return pruned_tree



async def __cleanup_dom(page: Page):
    """
    Restores original attributes modified during injection.
    """
    logger.debug("Cleaning up the DOM's previous injections")
    await page.evaluate("""() => {
        const allElements = document.querySelectorAll('*[mmid]');
        allElements.forEach(element => {
            element.removeAttribute('aria-keyshortcuts');
            const origAriaAttribute = element.getAttribute('orig-aria-keyshortcuts');
            if (origAriaAttribute) {
                element.setAttribute('aria-keyshortcuts', origAriaAttribute);
                element.removeAttribute('orig-aria-keyshortcuts');
            }

            // Restore aria-hidden
            const origAriaHidden = element.getAttribute('data-orig-aria-hidden');
            if (origAriaHidden !== null) {
                element.setAttribute('aria-hidden', origAriaHidden);
                element.removeAttribute('data-orig-aria-hidden');
            }

            // Restore tabindex
            const origTabIndex = element.getAttribute('data-orig-tabindex');
            if (origTabIndex !== null) {
                element.setAttribute('tabindex', origTabIndex);
                element.removeAttribute('data-orig-tabindex');
            }
        });
    }""")
    logger.debug("DOM cleanup complete")


def __prune_tree(node: dict[str, Any], only_input_fields: bool) -> dict[str, Any] | None:
    """
    Recursively prunes a tree starting from `node`, based on pruning conditions and handling of 'unraveling'.

    The function has two main jobs:
    1. Pruning: Remove nodes that don't meet certain conditions, like being marked for deletion.
    2. Unraveling: For nodes marked with 'marked_for_unravel_children', we replace them with their children,
       effectively removing the node and lifting its children up a level in the tree.

    This happens in place, meaning we modify the tree as we go, which is efficient but means you should
    be cautious about modifying the tree outside this function during a prune operation.

    Args:
    - node (Dict[str, Any]): The node we're currently looking at. We'll check this node, its children,
      and so on, recursively down the tree.
    - only_input_fields (bool): If True, we're only interested in pruning input-related nodes (like form fields).
      This lets you narrow the focus if, for example, you're only interested in cleaning up form-related parts
      of a larger tree.

    Returns:
    - dict[str, Any] | None: The pruned version of `node`, or None if `node` was pruned away. When we 'unravel'
      a node, we directly replace it with its children in the parent's list of children, so the return value
      will be the parent, updated in place.

    Notes:
    - 'marked_for_deletion_by_mm' is our flag for nodes that should definitely be removed.
    - Unraveling is neat for flattening the tree when a node is just a wrapper without semantic meaning.
    - We use a while loop with manual index management to safely modify the list of children as we iterate over it.
    """
    if "marked_for_deletion_by_mm" in node:
        return None

    if 'children' in node:
        i = 0
        while i < len(node['children']):
            child = node['children'][i]
            if 'marked_for_unravel_children' in child:
                # Replace the current child with its children
                if 'children' in child:
                    node['children'] = node['children'][:i] + child['children'] + node['children'][i+1:]
                    i += len(child['children']) - 1  # Adjust the index for the new children
                else:
                    # If the node marked for unraveling has no children, remove it
                    node['children'].pop(i)
                    i -= 1  # Adjust the index since we removed an element
            else:
                # Recursively prune the child if it's not marked for unraveling
                pruned_child = __prune_tree(child, only_input_fields)
                if pruned_child is None:
                    # If the child is pruned, remove it from the children list
                    node['children'].pop(i)
                    i -= 1  # Adjust the index since we removed an element
                else:
                    # Update the child with the pruned version
                    node['children'][i] = pruned_child
            i += 1  # Move to the next child

        # After processing all children, if the children array is empty, remove it
        if not node['children']:
            del node['children']

    # Apply existing conditions to decide if the current node should be pruned
    return None if __should_prune_node(node, only_input_fields) else node


def __should_prune_node(node: dict[str, Any], only_input_fields: bool):
    """
    Determines if a node should be pruned based on its 'role' and 'element_attributes'.

    Args:
        node (dict[str, Any]): The node to be evaluated.
        only_input_fields (bool): Flag indicating whether only input fields should be considered.

    Returns:
        bool: True if the node should be pruned, False otherwise.
    """
    # `name` may be present but None (some AX nodes have null names); normalize
    # to a string so the .strip()/.replace() calls below never blow up.
    name_val = node.get('name')
    name_str = name_val if isinstance(name_val, str) else ''

    if node.get('aria-hidden') == 'true' or node.get('tabindex') == '-1':
        return False
    if node.get('role') == 'text' and name_str.strip().isdigit():
        return False
    if node.get("role") != "WebArea" and only_input_fields and not (node.get("tag") in ("input", "button", "textarea") or node.get("role") == "button"):
        return True

    if node.get('role') == 'generic' and 'children' not in node and not ('name' in node and node.get('name')):  # The presence of 'children' is checked after potentially deleting it above
        return True

    if node.get('role') in ['separator', 'LineBreak']:
        return True
    processed_name = ""
    if 'name' in node:
        processed_name:str = name_str # type: ignore
        processed_name = processed_name.replace(',', '')
        processed_name = processed_name.replace(':', '')
        processed_name = processed_name.replace('\n', '')
        processed_name = processed_name.strip()
        if len(processed_name) <3:
            processed_name = ""

    if node.get('role') == 'text' and processed_name.isdigit():
        return False
    
    #check if the node only have name and role, then delete that node
    if len(node) == 2 and 'name' in node and 'role' in node and not (node.get('role') == "text" and processed_name != ""):
        return True
    return False

async def get_node_dom_element(page: Page, mmid: str):
    return await page.evaluate("""
        (mmid) => {
            return document.querySelector(`[mmid="${mmid}"]`);
        }
    """, mmid)


async def get_element_attributes(page: Page, mmid: str, attributes: list[str]):
    return await page.evaluate("""
        (inputParams) => {
            const mmid = inputParams.mmid;
            const attributes = inputParams.attributes;
            const element = document.querySelector(`[mmid="${mmid}"]`);
            if (!element) return null;  // Return null if element is not found

            let attrs = {};
            for (let attr of attributes) {
                attrs[attr] = element.getAttribute(attr);
            }
            return attrs;
        }
    """, {"mmid": mmid, "attributes": attributes})




async def do_get_accessibility_info(page: Page, browser_manager: PlaywrightManager, only_input_fields: bool = False):
    """
    Retrieves the accessibility information of a web page and saves it as JSON files.
    """
    start_time = time.time()
    logger.debug(f"[{time.strftime('%H:%M:%S')}] Starting new DOM accessibility info capture")

    await __inject_attributes(page)
    inject_time = time.time()
    logger.debug(f"[{time.strftime('%H:%M:%S')}] Injection complete, took {inject_time - start_time:.2f} seconds")

    accessibility_tree = await page.accessibility.snapshot(interesting_only=True)
    snapshot_time = time.time()
    logger.debug(f"[{time.strftime('%H:%M:%S')}] Got fresh accessibility snapshot, took {snapshot_time - inject_time:.2f} seconds")

    async with aiofiles.open(os.path.join(PROJECT_SOURCE_ROOT, 'temp', f'task_{browser_manager.job_ID}', 'json_accessibility_dom.json'), 'w', encoding='utf-8') as f:
        await f.write(json.dumps(accessibility_tree, indent=2))
    write_raw_time = time.time()
    logger.debug(f"[{time.strftime('%H:%M:%S')}] Completed writing json_accessibility_dom.json, took {write_raw_time - snapshot_time:.2f} seconds")

    await __cleanup_dom(page)
    cleanup_time = time.time()
    logger.debug(f"[{time.strftime('%H:%M:%S')}] DOM cleanup complete, took {cleanup_time - write_raw_time:.2f} seconds")

    try:
        enhanced_tree = await __fetch_dom_info(page, accessibility_tree, only_input_fields)
        enhance_time = time.time()
        logger.debug(f"[{time.strftime('%H:%M:%S')}] Enhanced tree processing complete, took {enhance_time - cleanup_time:.2f} seconds")

        async with aiofiles.open(os.path.join(PROJECT_SOURCE_ROOT, 'temp', f'task_{browser_manager.job_ID}', 'json_accessibility_dom_enriched.json'), 'w', encoding='utf-8') as f:
            await f.write(json.dumps(enhanced_tree, indent=2))
        write_enhanced_time = time.time()
        logger.debug(f"[{time.strftime('%H:%M:%S')}] Completed writing json_accessibility_dom_enriched.json, took {write_enhanced_time - enhance_time:.2f} seconds")

        total_time = write_enhanced_time - start_time
        logger.debug(f"[{time.strftime('%H:%M:%S')}] All DOM processing and file writes complete, total time: {total_time:.2f} seconds")
        # Return the enriched tree as a dict so callers can flatten/serialize it
        # efficiently (the old behaviour returned str(enhanced_tree), a
        # token-heavy Python-dict dump). See core/utils/dom_serializer.py.
        return enhanced_tree
    except Exception as e:
        logger.error(f"Error while fetching DOM info: {e}", exc_info=True)
        return None