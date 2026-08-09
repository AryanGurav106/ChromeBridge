"""Set-of-Mark (SoM) visual analysis skill.

Burns numbered bounding boxes — labelled with each element's `mmid` — onto a
screenshot of the current viewport, then asks a vision model to reason about the
visible UI for the current step. Because the marks use the SAME `mmid` values the
text DOM uses, whatever element the vision model recommends can be acted on
directly with the existing click/enter_text tools (selector `[mmid='N']`).

This is the practical "Set-of-Mark" pattern (Microsoft SoM / WebVoyager): it gives
the agent the spatial/visual layout that the accessibility tree alone discards
(position, what's actually on screen, overlap), while keeping actions deterministic
via `mmid`.
"""

import os
import time
from io import BytesIO
from typing import Annotated

from PIL import Image, ImageDraw, ImageFont

from config import PROJECT_SOURCE_ROOT
from core.utils.dom_helper import wait_for_non_loading_dom_state
from core.utils.logger import Logger
from core.utils.vision import describe_image

logger = Logger()

# Mark only visible, interactive elements that are actually on screen. Cap the
# count so dense pages don't become an unreadable wall of boxes.
_MAX_MARKS = 60

# JS: ensure every relevant element has an `mmid` (deterministic, same order as the
# accessibility-tree injector so ids line up with get_dom_fields), then return the
# visible+interactive ones with their viewport-relative boxes.
_COLLECT_JS = """
() => {
    const tags_to_ignore = ['head','style','script','link','meta','noscript','template','iframe','g','main','c-wiz','path'];
    const ids_to_ignore = ['agentDriveAutoOverlay'];

    // Inject mmids if they are not already present (idempotent / deterministic).
    if (!document.querySelector('[mmid]')) {
        let id = 0;
        document.querySelectorAll('*').forEach(el => {
            const tag = el.tagName.toLowerCase();
            if (tags_to_ignore.includes(tag) || ids_to_ignore.includes(el.id)) return;
            el.setAttribute('mmid', `${++id}`);
        });
    }

    const dpr = window.devicePixelRatio || 1;
    const vw = window.innerWidth || document.documentElement.clientWidth;
    const vh = window.innerHeight || document.documentElement.clientHeight;

    const isInteractive = (el) => {
        const tag = el.tagName.toLowerCase();
        if (['a','button','input','select','textarea'].includes(tag)) return true;
        const role = el.getAttribute('role');
        if (role && ['button','link','menuitem','tab','checkbox','radio','switch','option'].includes(role)) return true;
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

        // Top-element / occlusion test at the center.
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        let clickable = true;
        try {
            const topEl = document.elementFromPoint(cx, cy);
            clickable = !!(topEl && (topEl === el || el.contains(topEl) || topEl.contains(el)));
        } catch (e) {}
        if (!clickable) return;

        let label = (el.getAttribute('aria-label') || el.value || el.innerText || el.getAttribute('placeholder') || el.getAttribute('name') || '').trim();
        label = label.replace(/\\s+/g, ' ').slice(0, 40);

        out.push({
            mmid: el.getAttribute('mmid'),
            x: r.left, y: r.top, w: r.width, h: r.height,
            tag: el.tagName.toLowerCase(),
            label: label,
            dpr: dpr,
        });
    });
    return out;
}
"""


def _draw_marks(png_bytes: bytes, elements: list, dpr: float, out_path: str) -> None:
    """Draw labelled boxes onto the screenshot. Coordinates are CSS px; the
    screenshot is rendered at devicePixelRatio, so scale by dpr."""
    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", max(11, int(11 * dpr)))
    except Exception:
        font = ImageFont.load_default()

    color = (255, 0, 0)
    for el in elements:
        x, y = el["x"] * dpr, el["y"] * dpr
        w, h = el["w"] * dpr, el["h"] * dpr
        draw.rectangle([x, y, x + w, y + h], outline=color, width=2)
        tag = str(el["mmid"])
        # label background for legibility
        try:
            tb = draw.textbbox((0, 0), tag, font=font)
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
        except Exception:
            tw, th = 8 * len(tag), 12
        lx, ly = x, max(0, y - th - 2)
        draw.rectangle([lx, ly, lx + tw + 4, ly + th + 2], fill=color)
        draw.text((lx + 2, ly + 1), tag, fill=(255, 255, 255), font=font)

    img.save(out_path)


async def analyze_marked_screen(
    bc,
    info: Annotated[str, "What the agent wants to find/do on screen"],
    current_step: Annotated[str, "The current step being executed"] = "",
) -> Annotated[str, "Vision-model analysis of the marked screenshot"]:
    """Mark the current viewport with mmid boxes and ask a VLM about it."""
    page = await bc.get_current_page()
    if page is None:
        return "Error: No active page found."

    await wait_for_non_loading_dom_state(page, 2000)

    elements = await page.evaluate(_COLLECT_JS)
    if not elements:
        return "No visible, interactive, on-screen elements were found to mark."

    dpr = float(elements[0].get("dpr", 1) or 1)
    if len(elements) > _MAX_MARKS:
        # Keep the largest (usually most salient) elements.
        elements = sorted(elements, key=lambda e: e["w"] * e["h"], reverse=True)[:_MAX_MARKS]

    png_bytes = await page.screenshot(full_page=False)

    job_dir = getattr(bc, "job_dir", os.path.join(PROJECT_SOURCE_ROOT, "temp"))
    os.makedirs(job_dir, exist_ok=True)
    out_path = os.path.join(job_dir, f"som_{int(time.time())}.png")
    try:
        _draw_marks(png_bytes, elements, dpr, out_path)
    except Exception as e:
        logger.error(f"Failed to draw Set-of-Mark overlay: {e}")
        return f"Failed to render marked screenshot: {e}"

    # A compact legend so the model can cross-reference numbers to elements.
    legend = "\n".join(
        f"  [{e['mmid']}] {e['tag']}" + (f" — \"{e['label']}\"" if e["label"] else "")
        for e in elements
    )

    prompt = (
        "You are looking at a screenshot of a web page. Each interactive element is "
        "outlined with a red box labelled by its numeric element id (mmid).\n\n"
        f"Current step: {current_step}\n"
        f"What I need: {info}\n\n"
        "Element legend (id -> tag/label):\n"
        f"{legend}\n\n"
        "Using the VISUAL layout (positions, grouping, what is actually visible and "
        "on top), answer concisely:\n"
        "1) Which element id(s) are most relevant to the step, and why.\n"
        "2) The exact mmid to click/type into next (state it as mmid=N).\n"
        "3) Any blocking overlay/modal/cookie-banner visible, and which mmid dismisses it.\n"
        "Refer to elements only by their mmid number."
    )

    analysis = await describe_image(out_path, prompt)
    logger.debug(f"Set-of-Mark analysis saved overlay to {out_path}")
    return f"{analysis}\n\n[Set-of-Mark overlay saved to {out_path}; {len(elements)} elements marked.]"
