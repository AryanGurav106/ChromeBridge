"""Fast, deterministic interactive-element listing.

A lightweight alternative to `get_dom_fields`: a single JS pass returns the
visible, on-screen interactive elements with their `mmid`, tag, label, geometry,
and true clickability — with NO accessibility-tree snapshot and NO Explainer-LLM
round-trip. This is the cheap text counterpart to the `analyze_screen` (Set-of-Mark)
vision channel; both key off the same `mmid` so actions stay deterministic.

Use `get_dom_fields` when you need the Explainer to reason about a complex/ambiguous
page; use this when you just want a quick, structured list of what you can act on.
"""

import time
from typing import Annotated

from core.utils.dom_helper import wait_for_non_loading_dom_state
from core.utils.logger import Logger

logger = Logger()

_MAX_ELEMENTS = 120

# Inject mmids if absent (deterministic, same order as the AX-tree injector so ids
# line up with get_dom_fields / analyze_screen), then return visible interactive ones.
_JS = """
() => {
    const tags_to_ignore = ['head','style','script','link','meta','noscript','template','iframe','g','main','c-wiz','path'];
    const ids_to_ignore = ['agentDriveAutoOverlay'];

    if (!document.querySelector('[mmid]')) {
        let id = 0;
        document.querySelectorAll('*').forEach(el => {
            const tag = el.tagName.toLowerCase();
            if (tags_to_ignore.includes(tag) || ids_to_ignore.includes(el.id)) return;
            el.setAttribute('mmid', `${++id}`);
        });
    }

    const vw = window.innerWidth || document.documentElement.clientWidth;
    const vh = window.innerHeight || document.documentElement.clientHeight;

    const isInteractive = (el) => {
        const tag = el.tagName.toLowerCase();
        if (['a','button','input','select','textarea'].includes(tag)) return true;
        const role = el.getAttribute('role');
        if (role && ['button','link','menuitem','menuitemcheckbox','menuitemradio','tab','checkbox','radio','switch','option','combobox','searchbox','textbox'].includes(role)) return true;
        if (el.hasAttribute('onclick') || el.hasAttribute('tabindex') || el.isContentEditable) return true;
        try { if (getComputedStyle(el).cursor === 'pointer') return true; } catch (e) {}
        return false;
    };

    const out = [];
    document.querySelectorAll('[mmid]').forEach(el => {
        if (!isInteractive(el)) return;
        const r = el.getBoundingClientRect();
        const cs = getComputedStyle(el);
        const visible = r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' &&
                        cs.display !== 'none' && parseFloat(cs.opacity || '1') > 0;
        const inViewport = r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw;
        if (!visible || !inViewport) return;

        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        let clickable = true;
        try {
            const topEl = document.elementFromPoint(cx, cy);
            clickable = !!(topEl && (topEl === el || el.contains(topEl) || topEl.contains(el)));
        } catch (e) {}

        const tag = el.tagName.toLowerCase();
        let label = (el.getAttribute('aria-label') || el.value || el.getAttribute('placeholder') ||
                     el.innerText || el.getAttribute('name') || el.getAttribute('title') || '').trim();
        label = label.replace(/\\s+/g, ' ').slice(0, 60);
        const type = el.getAttribute('type');

        out.push({
            mmid: el.getAttribute('mmid'), tag, type, label,
            x: Math.round(r.left), y: Math.round(r.top),
            w: Math.round(r.width), h: Math.round(r.height),
            clickable
        });
    });
    return out;
}
"""


async def get_interactive_elements_func(
    bc,
    only_clickable: Annotated[bool, "If true, only return elements not occluded by an overlay"] = False,
) -> Annotated[str, "Compact list of visible interactive elements on the current page"]:
    """Return a compact, structured list of on-screen interactive elements."""
    page = await bc.get_current_page()
    if page is None:
        return "Error: No active page found."

    start = time.time()
    await wait_for_non_loading_dom_state(page, 2000)
    elements = await page.evaluate(_JS)

    if not elements:
        return "No visible, interactive, on-screen elements were found."

    if only_clickable:
        elements = [e for e in elements if e.get("clickable")]

    # Sort top-to-bottom, left-to-right (reading order) and cap.
    elements.sort(key=lambda e: (e["y"], e["x"]))
    truncated = len(elements) > _MAX_ELEMENTS
    elements = elements[:_MAX_ELEMENTS]

    lines = []
    for e in elements:
        tagtype = e["tag"] + (f"[{e['type']}]" if e.get("type") else "")
        label = f' "{e["label"]}"' if e["label"] else ""
        occluded = "" if e.get("clickable") else " (occluded/blocked)"
        lines.append(
            f"mmid={e['mmid']} | {tagtype}{label} | box({e['x']},{e['y']},{e['w']},{e['h']}){occluded}"
        )

    header = (
        f"Visible interactive elements ({len(elements)}"
        f"{'+' if truncated else ''} on screen). "
        "Act on one with click_tool/enter_text_tool using selector [mmid='N']. "
        "Elements marked (occluded/blocked) are covered by an overlay — handle that first.\n"
    )
    logger.debug(f"get_interactive_elements took {time.time() - start:.2f}s, {len(elements)} elements")
    return header + "\n".join(lines)
