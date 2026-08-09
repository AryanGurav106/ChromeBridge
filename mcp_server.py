"""ChromeBridge MCP server — Claude-in-Chrome-compatible tool surface, zero API keys.

Exposes the ChromeBridge extension (the user's REAL Chrome window, with their
logins) as an MCP stdio server. Claude Code is the agent: every model call runs
on the user's Claude subscription — this server holds NO LLM key. Screenshots
are returned as MCP ImageContent so Claude sees the page natively (replaces the
old analyze_screen / vision-key path entirely).

Run (registered via .mcp.json or `claude mcp add`):
    .venv\\Scripts\\python.exe mcp_server.py

IMPORTANT: stdio transport — stdout belongs to JSON-RPC. Never print() here;
all human logging goes to stderr (core.utils.logger already does).
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import mimetypes
import os
import re
import sys
import time
import unicodedata
from contextlib import asynccontextmanager
from typing import Annotated, Any, Optional, Union

# Make repo-root imports work no matter what cwd Claude Code launches us with.
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(_ROOT, ".env"))

from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent
from pydantic import Field

from core.bridge.server import ExtensionBridge

# ----------------------------------------------------------------------------
# globals
# ----------------------------------------------------------------------------

HOST = os.getenv("BRIDGE_HOST", "127.0.0.1")
PORT = int(os.getenv("BRIDGE_PORT", "8765"))
TOKEN = os.getenv("BRIDGE_TOKEN")

NOT_CONNECTED = (
    "Chrome extension is not connected to the bridge. In Chrome: load the unpacked "
    "extension (chrome://extensions -> Developer mode -> Load unpacked -> point at "
    "the extension/ folder), open its side panel, paste the BRIDGE_TOKEN from .env "
    "and click Save & Connect. The extension auto-reconnects within seconds."
)

STATE: dict[str, Any] = {"bridge": None}

# LAST LISTING PER TAB, for delta reads. After an action, most of a page is
# unchanged and we re-send all of it — ~1k tokens per observation, dozens of
# observations per task. Keyed by tabId; the stored URL guards against diffing
# across a navigation, where every ref is invalid anyway.
LAST_READ: dict[int, dict[str, Any]] = {}

# imageId -> png bytes (screenshots / zooms captured this session)
IMAGES: dict[str, bytes] = {}
_IMG_SEQ = 0

# GIF recorder state (server-side; frames are PIL Images)
GIF: dict[str, Any] = {"recording": False, "frames": [], "labels": []}

_TEMP_DIR = os.path.join(_ROOT, "temp")


def _log(msg: str) -> None:
    sys.stderr.write(f"[chromebridge-mcp] {msg}\n")
    sys.stderr.flush()


@asynccontextmanager
async def _lifespan(_server: FastMCP):
    bridge = ExtensionBridge(host=HOST, port=PORT, token=TOKEN)
    try:
        await bridge.start()
    except OSError as e:
        _log(
            f"FATAL: cannot bind ws://{HOST}:{PORT} ({e}). Is another ChromeBridge "
            "process (old run_extension.py REPL or a second mcp_server) running?"
        )
        raise
    STATE["bridge"] = bridge
    _log(f"bridge listening on ws://{HOST}:{PORT}; waiting for the Chrome extension to connect")
    try:
        yield {"bridge": bridge}
    finally:
        try:
            if bridge.connected:
                await bridge.call("detach_debugger")
        except Exception:
            pass
        await bridge.stop()
        STATE["bridge"] = None
        _log("bridge stopped")


mcp = FastMCP("chromebridge", lifespan=_lifespan)

# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------


async def _bridge() -> ExtensionBridge:
    b: Optional[ExtensionBridge] = STATE.get("bridge")
    if b is None:
        raise RuntimeError("bridge not started (server still initializing)")
    if not b.connected:
        try:
            await b.wait_until_connected(timeout=8.0)
        except Exception:
            raise RuntimeError(NOT_CONNECTED)
    return b


def _q(v: Any, limit: int) -> str:
    """Quote a label for display WITHOUT escaping non-ASCII.

    json.dumps defaults to ensure_ascii=True, so every Chinese, Japanese, Arabic
    or Cyrillic label find() printed came out as backslash-u escapes — unreadable,
    silently undoing the collector's whole non-Latin story in the one tool that
    reports elements as text. read_page is unaffected: it formats in the page with
    JSON.stringify, which does not escape.
    """
    t = str(v)
    # Mark the cut. A signed CDN URL sliced mid-query-string is visually
    # indistinguishable from a complete one, and an agent that reports or fetches
    # it fails somewhere else entirely.
    return json.dumps(t if len(t) <= limit else t[:limit] + "…(truncated)", ensure_ascii=False)


def _line_ident(line: str) -> str:
    """A listing row's identity, ignoring its mmid.

    mmids are assigned per pass and are additive, so comparing on them turns one
    framework re-render into hundreds of phantom add/remove pairs — a trap the
    ablation audit already hit and had to solve the same way. Everything after
    the mmid is the element's actual description.
    """
    line = re.sub(r"^mmid=\S+\s*\|\s*", "", line).strip()
    # FOLDED GROUP LINES embed their refs inline (`18:"Hacker News"->/news`), so a
    # re-render that renumbers mmids would change the whole line and every folded
    # group would read as "changed". Normalise those refs out too — the labels and
    # hrefs are the identity, the numbers are not.
    line = re.sub(r"(^|\s)\d+:(?=[\"'])", r"\1REF:", line)
    # STRIP GEOMETRY. box(x,y,w,h) is where a row is, not what it is. A live
    # agent expanding a Bootstrap accordion saw 7 rows in NEW and the SAME 7 in
    # GONE, byte-identical apart from y=63 -> y=10: nothing had been removed,
    # the page had simply moved down 53px. Including coordinates made deltas
    # both wrong and barely smaller than a full read on any scrolling page.
    return re.sub(r"\s*\|\s*box\([^)]*\)", "", line).strip()


def _delta_listing(prev: list[str], cur: list[str]) -> Optional[str]:
    """Render cur as a change-set against prev, or None if that is a bad trade.

    Returns None (meaning: send the full listing) when the page has changed so
    much that a delta would be no smaller, or when there is nothing to compare.
    A delta that is 90% of the listing costs the reader the diff-reading effort
    for no saving, which is worse than just sending the page.
    """
    if not prev:
        return None
    prev_idents = {}
    prev_text = {}          # ident -> the row as the agent originally saw it
    for ln in prev:
        _i = _line_ident(ln)
        prev_idents[_i] = prev_idents.get(_i, 0) + 1
        prev_text.setdefault(_i, ln)

    added, unchanged = [], 0
    seen: dict[str, int] = {}
    for ln in cur:
        ident = _line_ident(ln)
        seen[ident] = seen.get(ident, 0) + 1
        if seen[ident] <= prev_idents.get(ident, 0):
            unchanged += 1
        else:
            added.append(ln)

    cur_idents = set(seen)
    removed = [i for i in prev_idents if i not in cur_idents]

    # Not worth it if most rows changed anyway.
    if unchanged < max(4, 0.25 * len(cur)):
        return None
    if len(added) + len(removed) > 0.6 * len(cur):
        return None

    head = [f"[DELTA — {unchanged} row(s) unchanged since the last observation of this "
            f"page and omitted here; their refs are still valid]"]
    if added:
        head.append(f"NEW OR CHANGED ({len(added)}):")
        head.extend("  + " + ln for ln in added)
    if removed:
        head.append(f"NO LONGER LISTED ({len(removed)}) — these left the listing. They were "
                    f"either removed from the page OR merely scrolled out of the viewport, so a "
                    f"ref may still work; re-read without delta to be sure:")
        head.extend("  - " + prev_text.get(i, i)[:110] for i in removed[:25])
        if len(removed) > 25:
            head.append(f"  - …and {len(removed) - 25} more")
    if not added and not removed:
        head.append("Nothing changed since your last read of this page.")
    return "\n".join(head)


def _ref_to_selector(ref: Union[str, int]) -> str:
    """ref_12 / 12 / f3:7 / ref_f3:7 / [mmid='12'] -> [mmid='...'] selector."""
    r = str(ref).strip()
    if r.startswith("["):
        return r
    m = re.fullmatch(r"(?:ref_)?((?:f\d+:)?\d+)", r)
    if not m:
        raise ValueError(
            f"invalid ref {ref!r} — expected a ref id like 'ref_12' from read_page/find"
        )
    return f"[mmid='{m.group(1)}']"


def _store_image(png: bytes) -> str:
    global _IMG_SEQ
    _IMG_SEQ += 1
    image_id = f"img_{_IMG_SEQ}"
    IMAGES[image_id] = png
    return image_id


def _png_from_data_url(data_url: str) -> bytes:
    b64 = data_url.split(",", 1)[1] if data_url.startswith("data:") else data_url
    return base64.b64decode(b64)


def _image_content(png: bytes) -> ImageContent:
    return ImageContent(
        type="image", data=base64.b64encode(png).decode("ascii"), mimeType="image/png"
    )


def _to_css_pixels(png: bytes, css_w: Optional[float]) -> bytes:
    """Downscale a device-pixel capture to CSS pixels.

    captureVisibleTab returns DEVICE pixels; every `computer` click goes out as CDP
    Input.dispatchMouseEvent, which takes CSS pixels. On a 125%-scaled display (the
    Windows laptop default) a 1536-CSS-px viewport captures as 1920 px, so a button
    the model reads at image-x=1200 gets clicked at CSS-x=1200 when it actually sits
    at 960 — every screenshot-derived click lands ~25% off toward the bottom-right,
    with no error. Ref-based clicks are unaffected, which makes it look random.
    Normalising the image here makes screenshot space and click space identical.
    """
    if not css_w or css_w <= 0:
        return png
    try:
        from PIL import Image as PILImage

        img = PILImage.open(io.BytesIO(png))
        if abs(img.width - css_w) <= 1:
            return png  # already 1:1
        h = max(1, round(img.height * (css_w / img.width)))
        img = img.resize((int(round(css_w)), h), PILImage.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        _log(f"css-pixel normalisation failed, returning raw capture: {e}")
        return png


async def _take_screenshot(tab_id: Optional[int]) -> tuple[bytes, str]:
    b = await _bridge()
    # A first capture on a fresh tab pays debugger attach + CDP domain setup, which can
    # exceed the 30s default and did so in benchmarking. Generous but bounded.
    res = await b.call("screenshot", tabId=tab_id, request_timeout=60.0)
    # The extension returns {dataUrl, cssWidth, ...}; older builds returned a bare
    # data URL, so accept both.
    if isinstance(res, dict):
        png = _png_from_data_url(res.get("dataUrl") or "")
        png = _to_css_pixels(png, res.get("cssWidth"))
    else:
        png = _png_from_data_url(res)
    image_id = _store_image(png)
    if GIF["recording"]:
        _gif_add_frame(png, "screenshot")
    return png, image_id


def _gif_add_frame(png: bytes, label: str) -> None:
    try:
        from PIL import Image as PILImage

        img = PILImage.open(io.BytesIO(png)).convert("RGB")
        if img.width > 800:  # bound RAM for long recordings
            img = img.resize((800, int(img.height * 800 / img.width)))
        if len(GIF["frames"]) < 300:
            GIF["frames"].append(img)
            GIF["labels"].append(label)
    except Exception as e:  # recording must never break the action itself
        _log(f"gif frame capture failed: {e}")


async def _record_action_frame(tab_id: Optional[int], label: str) -> None:
    """Capture a GIF frame after a page-mutating action (only while recording)."""
    if not GIF["recording"]:
        return
    try:
        b = await _bridge()
        res = await b.call("screenshot", tabId=tab_id)
        raw = res.get("dataUrl") if isinstance(res, dict) else res
        _gif_add_frame(_png_from_data_url(raw or ""), label)
    except Exception as e:
        _log(f"gif action frame failed: {e}")


_BANNER_RE = re.compile("\\A((?:\\*\\*\\*.*?\\*\\*\\*\\n)+)", re.S)


def _split_banner(text: str) -> tuple[str, str]:
    """Peel a leading `*** ... ***` banner off, so truncation cannot bisect it."""
    m = _BANNER_RE.match(text or "")
    return (m.group(1), text[m.end():]) if m else ("", text or "")


def _truncate(text: str, max_chars: int, hint: str = "") -> str:
    """Truncate with advice the caller has not already taken.

    The old message always said "pass a larger max_chars or filter='interactive'
    to narrow" — including to callers who had just passed filter='interactive'.
    An agent reported that as a loop invitation: the tool suggests the exact knob
    it is already turning. Callers now supply the advice that actually applies.
    """
    banner, text = _split_banner(text)
    if banner:
        # Reserve the banner's room, truncate the rest, then put it back.
        inner = _truncate(text, max(200, max_chars - len(banner)), hint)
        return banner + inner
    if max_chars and len(text) > max_chars:
        # NEVER TRUNCATE AWAY THE PAYLOAD. A blind head-slice cuts the tail, and the
        # element rows ARE the tail — the legend explaining the notation comes first.
        # Measured live: read_page(max_chars=900) on the saucedemo login page (three
        # elements) returned legend only, zero rows, so a ref got clicked twice
        # without ever being identified. If the budget cannot hold both, the
        # notation lecture is what goes; an agent can act on rows it cannot fully
        # decode far better than on a decoder ring with nothing to decode.
        rows = [ln for ln in text.split("\n") if ln.startswith("mmid=")]
        if rows and len(text[:max_chars].split("\n")[-1]) >= 0 and not any(
            ln.startswith("mmid=") for ln in text[:max_chars].split("\n")
        ):
            head = text.split("\n", 1)[0]          # "Current URL: ..." keeps context
            kept, body = [], 0
            budget = max(0, max_chars - len(head) - 1)
            for ln in rows:
                if body + len(ln) + 1 > budget:
                    break
                kept.append(ln)
                body += len(ln) + 1
            dropped = len(rows) - len(kept)
            return (
                head + "\n" + "\n".join(kept)
                + f"\n\n[output truncated at {max_chars} chars — the notation legend was"
                + " dropped to make room for elements"
                + (f"; {dropped} more element(s) not shown" if dropped else "")
                + (f" — {hint}" if hint else "")
                + "]"
            )
        return (
            text[:max_chars]
            + f"\n\n[output truncated at {max_chars} chars"
            + (f" — {hint}" if hint else "")
            + "]"
        )
    return text


# ----------------------------------------------------------------------------
# tabs
# ----------------------------------------------------------------------------


@mcp.tool()
async def tabs_context_mcp(
    createIfEmpty: Annotated[
        bool,
        Field(description="Create a new MCP tab group with one empty tab if none exists."),
    ] = False,
) -> str:
    """Get context information about the current MCP tab group. Returns all tab IDs
    inside the group. CRITICAL: call this at least once before other browser tools
    so you know what tabs exist. Prefer creating a new tab per conversation."""
    b = await _bridge()
    res = await b.call("tabs_context", createIfEmpty=createIfEmpty)
    return json.dumps(res)


@mcp.tool()
async def tabs_create_mcp() -> str:
    """Create a new empty tab in the MCP tab group (creates the group if needed)."""
    b = await _bridge()
    res = await b.call("tabs_create")
    return json.dumps(res)


@mcp.tool()
async def tabs_close_mcp(
    tabId: Annotated[int, Field(description="ID of the tab to close (must be in the MCP group).")],
) -> str:
    """Close a tab in the MCP tab group by its ID."""
    b = await _bridge()
    res = await b.call("tabs_close", tabId=tabId)
    return json.dumps(res)


# ----------------------------------------------------------------------------
# navigation & observation
# ----------------------------------------------------------------------------


@mcp.tool()
async def navigate(
    url: Annotated[
        str,
        Field(
            description='URL to open (protocol optional, defaults to https). Use "back" or "forward" for history navigation.'
        ),
    ],
    tabId: Annotated[int, Field(description="Tab ID to navigate.")],
) -> str:
    """Navigate to a URL, or go forward/back in browser history."""
    b = await _bridge()
    res = await b.call("navigate", url=url, tabId=tabId)
    await _record_action_frame(tabId, f"navigate {url}")
    return str(res)


@mcp.tool()
async def read_page(
    tabId: Annotated[int, Field(description="Tab ID to read from.")],
    filter: Annotated[
        str,
        Field(description='"interactive" for buttons/links/inputs only, "all" to also include the page text.'),
    ] = "all",
    max_chars: Annotated[int, Field(description="Maximum characters of output (default 50000).")] = 50000,
    ref_id: Annotated[
        Optional[str],
        Field(description="Ref of a container to scope the listing to — only elements inside that subtree are returned. Use it to read one dialog/panel/table without the rest of the page."),
    ] = None,
    detail: Annotated[
        str,
        Field(description='"compact" (default) omits URLs and images. "brief" adds href=/src= as destination PATHS plus non-clickable images — use this when you need a link target or image source; it carries the same information as "full" for ~17% fewer tokens. "full" is the same but with URLs verbatim — use it only when you need a URL you can paste (signed links, meaningful query strings). Pair either with ref_id: whole-page detail is several times larger.'),
    ] = "compact",
    depth: Annotated[int, Field(description="Accepted for compatibility; the listing is flat (ref_id scoping IS applied).")] = 15,
    delta: Annotated[
        bool,
        Field(description="Return only what CHANGED since your last read of this page, instead of the whole listing. Use after a click/fill when you expect a small change (a dialog opened, a row was added) — unchanged rows and their refs stay valid from the previous read. Falls back to the full listing automatically when the page changed too much for a delta to be smaller, or after a navigation."),
    ] = False,
) -> str:
    """Get a structured representation of the page's elements. Interactive elements
    carry ref ids (ref_N) usable with form_input, computer (scroll_to / ref clicks),
    file_upload and upload_image. Flags like (required)/(unselected)/(below-fold),
    section=dialog and role=combobox tell you where to act.

    The default listing has NO link URLs, NO image sources and no non-clickable
    images — those are omitted for size, not because the page lacks them. Pass
    detail="full" (with ref_id) to get them."""
    b = await _bridge()
    # ref_id now REALLY scopes the listing to that element's subtree. It used to be
    # accepted and silently ignored — the tool returned the whole page with an
    # apologetic note, which is worse than rejecting it would have been.
    scope_mmid = None
    if ref_id:
        _m = re.search(r"mmid='([^']+)'", _ref_to_selector(ref_id))
        scope_mmid = _m.group(1) if _m else None
        if scope_mmid is None:
            # Accepted-then-ignored is the worst outcome: the agent believes it
            # read one subtree and actually read the whole document, with no
            # banner and no note. A bracket selector like "[id='sidebar']" took
            # exactly that path.
            raise ValueError(
                f"ref_id={ref_id!r} is not a ref from read_page/find. Pass a ref like 'ref_12' "
                "(a CSS selector cannot be scoped to — refs are mmid-based)."
            )
    # THREE points on the rate/retention curve, not two. Measured on 21 frozen
    # sites: compact 0.512 answerability @ ~1634 tok; brief 0.792 @ ~2265;
    # full 0.793 @ ~2741. `brief` therefore carries FULL's information for 17%
    # fewer tokens — the scheme+host repeated on every same-origin link and the
    # tracking query strings were pure cost. `full` is kept only for the case
    # brief cannot serve: a URL you need verbatim (signed CDN links, anything
    # where the query string is the point).
    _d = str(detail).lower()
    _detail = _d if _d in ("full", "brief") else "compact"
    listing = await b.call("get_interactive_elements", tabId=tabId,
                           scopeMmid=scope_mmid, detail=_detail)
    out = str(listing)
    if out.startswith("__SCOPE_MISS__"):
        # The ref is well-formed but absent from THIS document — almost always a ref
        # carried across a navigation, since mmids are per-document. Raising beats
        # the old behaviour (whole page returned under a "scoped" header) and beats
        # silently dropping the scope, because the agent's next action would be
        # aimed at elements it believes are inside a container it never read.
        try:
            # get_url returns {"url":..., "title":...}; str() on the dict printed the
            # whole repr inside the sentence, which reads as noise exactly where the
            # agent is looking for the page it is actually on.
            _u = await b.call("get_url", tabId=tabId)
            _cur = (_u.get("url") if isinstance(_u, dict) else None) or str(_u)
        except Exception:
            _cur = "unknown"
        # STATE THE FACT, OFFER THE CAUSES. The first version asserted "a
        # navigation invalidated your refs" — and a live agent hit it on BBC with
        # NO navigation at all: a lazy-loading placeholder had simply been
        # replaced, while a sibling ref from the same listing still resolved. The
        # message sent them re-reading the whole page for the wrong reason. We
        # know the ref is gone; we do NOT know why.
        raise ValueError(
            f"ref_id={ref_id!r} is not on the current page ({_cur}). Refs are per-document "
            "and additive, so this one is gone for one of several reasons: the page "
            "navigated, a framework re-rendered that subtree, or the element was a "
            "placeholder that has since been replaced (lazy-loaded images and skeleton "
            "rows do this seconds after load, with no navigation). Other refs from the "
            "same listing may still be valid. Call read_page or find again for current refs."
        )
    if scope_mmid:
        out = f"[scoped to the subtree of ref_{scope_mmid} — elements outside it are omitted]\n" + out
    if filter == "all":
        # ref_id scopes the ELEMENT listing; get_dom_text is whole-document, so
        # appending it to a scoped read hands back the entire page an agent just
        # deliberately narrowed away from. Observed live: a read scoped to one
        # image link came back with all of Wikipedia's main page attached.
        if scope_mmid:
            # NOW SCOPED, not refused. The listing holds only INTERACTIVE elements,
            # so a table's data cells, a code block and a result pod were all
            # unreachable by ref — three independent live agents were forced into
            # javascript_tool by this. The worst case was a standings table:
            # read_page(ref_id=<table>, filter="all") returned 8 column headers and
            # ZERO of 195 values, then pointed the caller at a whole-document tool.
            # Region text is exactly the missing half, and it composes with the ref
            # the agent already has.
            rtext = str(await b.call("get_dom_text", tabId=tabId, scopeMmid=scope_mmid))
            if rtext.startswith("__SCOPE_MISS__"):
                out += (f"\n\n[text for ref_{scope_mmid} unavailable — the element went "
                        "away between the two reads. Re-read for current refs.]")
            else:
                out += f"\n\n--- TEXT INSIDE ref_{scope_mmid} ---\n" + rtext
        else:
            text = await b.call("get_dom_text", tabId=tabId)
            out = out + "\n\n--- PAGE TEXT ---\n" + str(text)
    # DELTA. Line-based on purpose: diffing structured entries would mean a THIRD
    # formatter, and vocabulary drift between the two that already exist produced
    # five of the eleven defects a live-agent study found. Diffing the exact rows
    # the agent already reads has no such failure mode.
    _cur_url = ""
    try:
        _u = await b.call("get_url", tabId=tabId)
        if isinstance(_u, dict):
            _cur_url = _u.get("url") or ""
        else:
            # The bridge hands this back as a JSON STRING; the dict branch only
            # ever fires in unit tests, so live we were keying on the whole
            # '{"url":..., "title":...}' blob — which also folds the page TITLE
            # into page identity, so a title change alone would kill the delta.
            try:
                _cur_url = (json.loads(str(_u)) or {}).get("url") or str(_u)
            except Exception:
                _cur_url = str(_u)
    except Exception:
        pass
    def _content_rows(text: str) -> list[str]:
        """Every line that carries elements, however it is formatted.

        Selecting only `mmid=`-prefixed lines missed folded group lines entirely —
        on Hacker News that meant 36 links lived in ONE line the extractor did not
        see, so a page with 185 elements looked like a 1-row page and the delta
        correctly refused. Compaction blocks (grids, icon palettes) have the same
        shape and the same problem.
        """
        rows, started = [], False
        for ln in text.split("\n"):
            if not started:
                if ln.startswith("Act on an element"):
                    started = True
                continue
            t = ln.strip()
            if not t or t.startswith("- ") or t.startswith("["):
                continue
            # EXPLODE FOLDED GROUPS. A group line packs dozens of elements into one
            # string, so ONE changed label rewrites the whole line and the delta
            # sees a wholesale change. Measured live on Hacker News, where
            # "13 hours ago" ticking to "14 hours ago" and comment counts moving
            # made three group lines cover most of the page and every delta refuse.
            # Comparing per element restores the property folding was hiding.
            toks = re.findall(r"(?:^|\s)(\d+:\"[^\"]*\"\S*)", ln)
            if len(toks) >= 3:
                head = ln[:22]          # short, distinctive group tag; identity only
                rows.extend(f"{head}~ {tk}" for tk in toks)
            else:
                rows.append(ln)
        return rows

    _rows = _content_rows(out)
    _prev = LAST_READ.get(tabId) or {}
    if delta and not scope_mmid and _prev.get("url") == _cur_url and _prev.get("rows"):
        _d = _delta_listing(_prev["rows"], _rows)
        if _d is not None:
            # Keep the page-level preamble (URL, modal banner, readiness) — those
            # describe the page NOW and are not part of the row set.
            # PREAMBLE = everything before the "Act on an element" boundary, the
            # same split _content_rows uses. Filtering on "not a mmid= line"
            # instead let FOLDED GROUP LINES back in, re-emitting the very rows
            # the delta had just omitted — the identical blind spot that made the
            # row extractor see a 185-element page as one row.
            _all = out.split("\n")
            try:
                _cut = next(i for i, ln in enumerate(_all) if ln.startswith("Act on an element"))
            except StopIteration:
                _cut = min(3, len(_all))
            _pre = [ln for ln in _all[:_cut] if ln and not ln.strip().startswith("- ")]
            out = "\n".join(_pre[:4] + [_d])
        else:
            out = ("*** DELTA NOT USED: the page changed too much for a delta to be "
                   "smaller. Full listing returned. ***\n") + out
    elif delta:
        # SAY WHY. A silently-ignored parameter is the exact failure this project
        # keeps rediscovering (ref_id accepted-then-ignored, detail never reaching
        # the router). If the caller asked for a delta and got a full page, the
        # reason must be in the output.
        if scope_mmid:
            _why = "the read is scoped with ref_id, and deltas apply to whole-page reads"
        elif not _prev:
            _why = "this is the first read of this tab (nothing to compare against yet)"
        elif _prev.get("url") != _cur_url:
            _why = f"the page navigated since your last read ({_prev.get('url')!r} -> {_cur_url!r}), so every previous ref is invalid"
        else:
            _why = "the previous read produced no comparable rows"
        out = "*** DELTA NOT USED: " + _why + ". Full listing returned. ***\n" + out
    if _rows:
        LAST_READ[tabId] = {"url": _cur_url, "rows": _rows}

    # Advice the caller has not already taken.
    if scope_mmid:
        # Checked FIRST: a scoped read has no page text to drop, so advising
        # filter='interactive' there recommends a knob that does nothing.
        hint = "raise max_chars — this listing is already scoped"
    elif filter == "all":
        hint = "pass filter='interactive' to drop the page text, or scope with ref_id"
    else:
        hint = "scope with ref_id, or raise max_chars"
    return _truncate(out, max_chars, hint)


@mcp.tool()
async def debug_targets(
    tabId: Annotated[int, Field(description="Tab to inspect; 0 lists all debuggable targets.")] = 0,
) -> str:
    """Diagnostic: Chrome's own debugger target table — what a tabId actually maps to,
    and whether some other extension already holds a session on it. Read-only."""
    b = await _bridge()
    return str(await b.call("debug_targets", tabId=tabId))


@mcp.tool()
async def sw_info(
    tabId: Annotated[int, Field(description="Any tab id (unused; the answer is per-extension).")] = 0,
) -> str:
    """Diagnostic: the extension service worker's id, age, and which tabs it holds a
    debugger session for. A CHANGED id between two calls means the MV3 worker was
    terminated and restarted — which silently destroys every trusted-input session."""
    b = await _bridge()
    return str(await b.call("sw_info", tabId=tabId))


@mcp.tool()
async def get_url(
    tabId: Annotated[int, Field(description="Tab ID to read the address bar of.")],
) -> str:
    """Get a tab's CURRENT url and title. Use after an action that may have
    navigated (form submit, search, link click) to confirm where you actually
    ended up — action results report what they did, not where the page went."""
    b = await _bridge()
    res = await b.call("get_url", tabId=tabId)
    return json.dumps(res)


@mcp.tool()
async def get_page_text(
    tabId: Annotated[int, Field(description="Tab ID to extract text from.")],
    max_chars: Annotated[int, Field(description="Maximum characters to return (default 30000). The DOCUMENT OUTLINE is always kept, even when the body is truncated.")] = 30000,
) -> str:
    """Extract raw text content from the page (articles, posts, text-heavy pages).
    Plain text without HTML formatting, followed by a DOCUMENT OUTLINE of the page's
    headings with nesting depth."""
    b = await _bridge()
    res = str(await b.call("get_dom_text", tabId=tabId))
    if max_chars and len(res) > max_chars:
        # Keep the OUTLINE even when truncating the body — it is small, it is usually the
        # most useful part for orienting, and it lives at the END of the payload so naive
        # truncation would always throw it away. S5 needed two sentences and a section
        # list and was handed a 30k-char article with no way to bound it.
        marker = "--- DOCUMENT OUTLINE"
        # rfind, not find: the collector appends the outline LAST, but a page that
        # merely DISPLAYS this string (docs quoting the tool, a source viewer) made
        # find() treat the whole body as outline and keep it — a 1000-char cap
        # returned 3170 chars.
        _bnr, res = _split_banner(res)
        if _bnr:
            max_chars = max(200, max_chars - len(_bnr))
        i = res.rfind(marker)
        outline = res[i:] if i != -1 else ""
        # A heading-dense page (a spec, a long API reference) can have an outline
        # bigger than the cap on its own. Keeping it is right — it is the part that
        # orients you — but returning more than was asked for silently is not.
        if len(outline) + 120 >= max_chars:
            # _bnr goes back on EVERY return of this branch. Peeling it and then
            # forgetting to restore it made the banner vanish entirely — a
            # regression on the very fix meant to stop it being cut in half.
            # Reserving room for something and then dropping it is worse than
            # never reserving the room at all.
            return (_bnr + res[:max(0, max_chars - 200)] +
                    f"\n\n[the DOCUMENT OUTLINE alone is {len(outline)} chars, over the {max_chars} "
                    f"requested; it is kept whole and the body dropped. Raise max_chars for body text.]\n" +
                    outline)
        keep = max(0, max_chars - len(outline) - 120)
        orig_len = i if i != -1 else len(res)
        note = "\n\n[body truncated at {} of {} chars — raise max_chars for more]\n\n".format(keep, orig_len)
        res = _bnr + res[:keep] + note + outline
    return res


@mcp.tool()
async def find(
    query: Annotated[
        str,
        Field(description='Natural language description of what to find (e.g. "search bar", "add to cart button").'),
    ],
    tabId: Annotated[int, Field(description="Tab ID to search in.")],
) -> str:
    """Find elements on the page using natural language. Returns up to 20 matching
    elements with refs usable with other tools (form_input, computer, ...)."""
    b = await _bridge()
    # detail="full" so IMAGES are in the search space. find() was interactive-only:
    # a perfect query for a photograph returned 17 anchor tags and zero images, with
    # nothing to say images were outside its search space — a dead end that looks
    # like a negative result. Cost is server-side only; find formats its own output.
    raw = await b.call("get_interactive_elements", tabId=tabId, structured=True, detail="full")
    if not isinstance(raw, list):
        raise RuntimeError("structured element listing unavailable on this page")

    # Stopwords: filler that matches everything and skews ranking. "box"/"field"
    # /"button" are NOT stopwords — they carry real role intent.
    _STOP = {"the", "a", "an", "of", "for", "to", "in", "on", "at", "with", "and",
             "or", "my", "this", "that", "please", "click", "find", "get"}
    # UNICODE-AWARE. `[^a-z0-9]+` discarded every non-ASCII character, so a Russian,
    # Greek, or Japanese query lost all its tokens and find() silently degraded to a
    # substring test on the whole query — or returned "No elements matched" on a page
    # full of matches. `\W` with str patterns is Unicode-aware in Python, and
    # casefold() beats lower() for non-ASCII (ß -> ss, Turkish dotted I).
    # NFC-normalise BOTH sides. A label carrying "café" in NFD (macOS filenames,
    # some CMS pipelines, copy-paste chains) never matched the NFC "café" an agent
    # types — a total miss on a page with a perfect match. The extension-side
    # option matcher already normalises; this scorer above it did not.
    def _nfc(x):
        return unicodedata.normalize("NFC", str(x or ""))
    query = _nfc(query)
    tokens = [t for t in re.split(r"\W+", query.casefold(), flags=re.UNICODE)
              if len(t) > 1 and t not in _STOP]
    q_full = query.strip().casefold()

    def _hit(token: str, text: str) -> float:
        """WORD-AWARE match weight. A bare `token in text` substring test ranked
        'Duffield Memorial' and 'Fields Medal' as matches for the token 'field'
        (observed twice in benchmarking). Whole-word and prefix matches are what
        people mean; a match buried inside a longer word is nearly worthless."""
        if not text:
            return 0.0
        # Scripts without word separators (Chinese/Japanese/Thai) have no \b to find
        # — every match there is legitimately a substring match, so scoring them at
        # the buried-in-a-word weight would make find() useless on those pages.
        # Arabic and Hebrew DO have word boundaries; the old class (Latin/Greek/
        # Cyrillic only) dropped them into the no-boundary branch and inflated their
        # scores. CJK/Thai genuinely have no spaces and belong there.
        # DENYLIST the scripts that genuinely have no word separators, rather than
        # allow-listing the ones we happened to think of. The old class covered
        # Latin/Greek/Cyrillic/Hebrew/Arabic only, so Hangul and every Indic
        # script fell into the "no boundaries" branch and scored BURIED matches at
        # full weight: query 검색 ranked the decoy 이검색어저장소 above the real
        # button 상품 검색. Those scripts use spaces and Python \b works for them.
        # Bare digits land here too, so "42" no longer matches "item 3427" at 1.0.
        if re.search(r"[\u4e00-\u9fff\u3040-\u30ff\u0e00-\u0e7f\u0e80-\u0eff\u1780-\u17ff\u1000-\u109f]", token):
            return 1.0 if token in text else 0.0
        if re.search(r"\b" + re.escape(token) + r"\b", text):
            return 1.0          # whole word: "search" in "search box"
        if re.search(r"\b" + re.escape(token), text):
            return 0.5          # word prefix: "combo" in "combobox"
        if token in text:
            return 0.1          # buried in a word: "field" in "Duffield"
        return 0.0

    def score(el: dict) -> float:
        label = _nfc(el.get("label")).casefold()
        tag = str(el.get("tag") or "").casefold()
        role = str(el.get("role") or "").casefold()
        placeholder = _nfc(el.get("placeholder")).casefold()
        name = _nfc(el.get("name")).casefold()
        near = _nfc(el.get("near")).casefold()
        s = 0.0
        _cov = set()
        _covText = set()      # tokens that matched this element's TEXT, not its type
        for t in tokens:
            _before = s
            _hl, _hn, _hp = _hit(t, label), _hit(t, name), _hit(t, placeholder)
            s += 3.0 * _hl + 3.0 * _hn + 2.0 * _hp
            # near= is adjacent-text context, not identity — worth something but
            # it must never outweigh the element's own name.
            s += 0.75 * _hit(t, near)
            # A WORD-LEVEL hit, not any hit. `_hit` grades matches, and the 0.1
            # buried-substring weight is not evidence of identity: counting it
            # let "field" inside "Duffield Memorial" outrank a real search box
            # whose only signal was the role word — the exact inversion F4 exists
            # to prevent, reintroduced by the coverage rule above it.
            if max(_hl, _hn, _hp) >= 0.5:
                _covText.add(t)
            if t == role or t == tag:
                s += 1.0
            if s > _before:
                _cov.add(t)
        # Spaceless scripts cannot be tokenised, so "搜索按钮" (search + button)
        # stayed one token and scored 0 against a label reading just "搜索" —
        # a confident "No elements matched" on a page with the exact control.
        # If the query STARTS WITH a label, that is a noun+role-word query.
        for t in tokens:
            if len(t) >= 2 and not re.search(r"[^一-鿿぀-ヿ가-힯]", t):
                for fld, wt in ((label, 3.0), (name, 3.0)):
                    if fld and len(fld) >= 2 and (t.startswith(fld) or fld.startswith(t)):
                        s += wt
        if q_full and (q_full == label or q_full == name):
            s += 6.0
        elif q_full and (_hit(q_full, label) >= 0.5 or _hit(q_full, name) >= 0.5):
            # WORD-AWARE, like _hit itself. A raw `q_full in label` substring test
            # here undid the whole reason _hit exists: the query "field" scored
            # +2.0 on "Duffield Memorial" and ranked it ABOVE the actual input
            # field — the exact failure the token-level scorer was written to stop,
            # reintroduced two lines below it.
            s += 2.0
        # role-word hints in the query ("button", "link", "input", ...)
        # ROLE-WORD HINTS. These are how a query reaches an element whose own text
        # is in another language or absent entirely: "search box" against a Baidu
        # textarea whose only label is a rotating Chinese headline scored ZERO and
        # returned "No elements matched" — for a search box, on a query that is
        # find()'s own documented example.
        kind_words = (tag, role, str(el.get("type") or "").casefold())
        for hint, kinds in (
            ("button", ("button", "submit")),
            ("link", ("a", "link")),
            ("input", ("input", "textbox", "textarea", "searchbox")),
            ("field", ("input", "textbox", "textarea", "searchbox")),
            ("box", ("input", "textbox", "textarea", "searchbox", "combobox")),
            ("bar", ("input", "textbox", "textarea", "searchbox")),
            ("search", ("search", "searchbox")),
            ("textarea", ("textarea",)),
            ("checkbox", ("checkbox",)),
            ("dropdown", ("select", "combobox", "listbox")),
            ("select", ("select", "combobox", "listbox")),
            ("tab", ("tab",)),
            ("radio", ("radio",)),
            ("toggle", ("switch", "checkbox")),
            ("switch", ("switch",)),
            ("slider", ("slider", "range")),
            ("option", ("option",)),
            ("combobox", ("combobox", "select")),
            ("menu", ("menu", "menuitem")),
            # Media kinds — without these an image is unreachable by the words
            # people actually use for one.
            ("image", ("media", "img")),
            ("img", ("media", "img")),
            ("photo", ("media", "img")),
            ("photograph", ("media", "img")),
            ("picture", ("media", "img")),
            ("graphic", ("media", "img")),
            ("banner", ("media", "img")),
            ("video", ("media", "video")),
            # NON-ENGLISH role words. The hint table was the only path to a control
            # whose own text does not contain the query, and it spoke one language —
            # so a Chinese query for Baidu's search button ("搜索按钮", whose button
            # actually reads 百度一下) had no signal at all and returned a confident
            # "No elements matched". These are matched by CONTAINMENT below, because
            # spaceless scripts do not tokenise: "搜索按钮" arrives as one token.
            ("按钮", ("button", "submit")), ("ボタン", ("button", "submit")),
            ("버튼", ("button", "submit")), ("кнопка", ("button", "submit")),
            ("botón", ("button", "submit")), ("bouton", ("button", "submit")),
            ("schaltfläche", ("button", "submit")),
            ("搜索", ("search", "searchbox", "input", "textbox", "textarea")),
            ("検索", ("search", "searchbox", "input", "textbox", "textarea")),
            ("검색", ("search", "searchbox", "input", "textbox", "textarea")),
            ("поиск", ("search", "searchbox", "input", "textbox", "textarea")),
            ("búsqueda", ("search", "searchbox", "input", "textbox", "textarea")),
            ("recherche", ("search", "searchbox", "input", "textbox", "textarea")),
            ("suche", ("search", "searchbox", "input", "textbox", "textarea")),
            ("输入框", ("input", "textbox", "textarea")), ("文本框", ("input", "textbox", "textarea")),
            ("入力", ("input", "textbox", "textarea")),
            ("链接", ("a", "link")), ("リンク", ("a", "link")), ("링크", ("a", "link")),
            ("ссылка", ("a", "link")),
            ("下拉", ("select", "combobox", "listbox")), ("选择", ("select", "combobox", "listbox")),
            ("复选框", ("checkbox",)), ("图片", ("media", "img")), ("画像", ("media", "img")),
        ):
            # Exact token match, OR containment for spaceless scripts where the
            # whole query is one token ("搜索按钮" contains "按钮").
            _hinted = hint in tokens
            if not _hinted and not hint.isascii():
                _hinted = any(hint in t for t in tokens)
            if _hinted and any(k in kinds for k in kind_words if k):
                s += 2.0
                # A role-word hit IS coverage: "search box" naming a control whose
                # only label is Chinese explains the query as well as a literal
                # word match would.
                _cov.update(t for t in tokens if hint in t or t == hint)
        if el.get("clickable") is False:
            s -= 1.0
        if (el.get("w") or 0) < 12 or (el.get("h") or 0) < 8:
            s -= 1.0
        # A widget the collector proved is a dead duplicate (no backing form
        # control while an identical one has one) must never outrank the live
        # twin — on select2.org the dead one is the BIGGER, fully visible one,
        # so geometry alone ranks it first.
        if el.get("orphanWidget"):
            s -= 5.0
        _COV[id(el)] = len(_cov)
        _COVTEXT[id(el)] = len(_covText)
        return s

    _COV: dict = {}
    _COVTEXT: dict = {}
    scored = sorted(((score(el), el) for el in raw), key=lambda p: -p[0])
    # STRONG vs WEAK, reported as different things. The fallback used to promote
    # any positive score — including pure buried-substring noise around 0.1 — into
    # the same confident "Found 17 element(s) matching" header. Live, a perfect
    # query for a photograph returned 17 nav anchors scoring on "Images", and an
    # agent reasonably read that as "these are the matches". A weak match is still
    # worth showing; presenting it as a match is what was wrong.
    # COVERAGE, not just magnitude. `s >= 1.0` is satisfied by ONE hit on ONE
    # token, so a ten-word natural-language query made "About the BBC" (matching
    # only "about") and eight org avatars (matching nothing but ranking on a media
    # boost) land under the same confident "Found N element(s) matching" header as
    # the real answer. Three independent live agents flagged exactly this. A
    # confident match must explain a real share of what was asked for.
    # Only LONG queries are gated. With one or two words, matching one of them IS
    # full coverage; the pathology is a ten-word question where a single common
    # word ("about") carries footer boilerplate into the confident list.
    _need = 2 if len(tokens) >= 4 else 1
    # ROLE WORDS FILTER A TYPE; CONTENT WORDS IDENTIFY AN ELEMENT. The query
    # "classList documentation link" reported 792 confident matches on MDN,
    # because "link" is a role word that matches every <a> and one matched token
    # clears the bar on a short query. Ranking was fine — the right element was
    # first — but a confident count of 792 is the overconfidence the strong/weak
    # split exists to prevent.
    #
    # So: if ANY element on the page matched a query word in its TEXT, require
    # that of every confident match. When NOTHING matches by text — a Chinese-only
    # page where "search box" can only land via the role word — fall back, which
    # is the case F8/F14 protect.
    _text_possible = any(_COVTEXT.get(id(el), 0) > 0 for _sc, el in scored)
    def _ok(el):
        if _COV.get(id(el), 0) < _need:
            return False
        return (not _text_possible) or _COVTEXT.get(id(el), 0) > 0
    strong_all = [(sc, el) for sc, el in scored if sc >= 1.0 and _ok(el)]
    _demoted = [(sc, el) for sc, el in scored if sc >= 1.0 and not _ok(el)]
    strong = strong_all[:20]
    weak = ([(s, el) for s, el in scored if 0 < s < 1.0] + _demoted)[:5]
    hits = strong or weak
    if not hits:
        return (
            f'No elements matched "{query}". Call read_page(filter="interactive") to see '
            "everything that is on the page."
        )
    if strong:
        # Say when the list was CUT. "Found 20 element(s)" on a table with 31
        # matching row buttons reads as "the page has exactly 20 rows".
        more = len(strong_all) - len(strong)
        lines = [f'Found {len(strong_all)} element(s) matching "{query}"'
                 + (f' — showing the top {len(strong)}, {more} more not listed' if more else '') + ':']
    else:
        lines = [f'NO CONFIDENT MATCH for "{query}". The {len(hits)} below matched only '
                 f"weakly — a partial word, or adjacent text rather than the element's own "
                 f"name. Check them, or call read_page to see the page for yourself."]
    for s, el in hits:
        ref = f"ref_{el.get('mmid')}"
        kind = el.get("role") or el.get("tag") or "element"
        # SAME DISAMBIGUATION read_page uses. find() emitted ONE unlabelled quoted
        # string that could be the accessible name, the current value, the
        # placeholder or the visible text, with nothing saying which. On Baidu it
        # showed a search box's placeholder and an agent read it as the box's
        # CONTENTS — the exact confusion the name/value/placeholder split exists to
        # prevent, reintroduced in the other tool that reports elements.
        # IDENTITY vs ATTRIBUTES are tracked separately. The text fallback below
        # fires when the element has no IDENTITY — but href/src are attributes,
        # not identity, and once href was added to this block it made `ident`
        # non-empty and silently suppressed the fallback. A live agent got
        # `ref_1363 [a] href="..." section=main` with no label at all and had to
        # infer which link was which by reading the API name out of the URL.
        # Adding a field must not delete another.
        ident = ""
        attrs = ""
        if el.get("name"):
            ident += f" name={_q(el['name'], 80)}"
        if el.get("value"):
            ident += f" value={_q(el['value'], 80)}"
        if el.get("placeholder"):
            ident += f" placeholder={_q(el['placeholder'], 80)}"
        if el.get("src"):
            attrs += f" src={_q(el['src'], 120)}"
        # href was NEVER emitted. find() showed image src but not link targets, so
        # on a task literally about URLs a live agent got an anchor with no name, no
        # text and no href — the one attribute that says where it goes was the one
        # missing, while read_page(detail="full") had it all along.
        if el.get("href"):
            attrs += f" href={_q(el['href'], 120)}"
        if not ident:
            txt = (el.get("text") or el.get("label") or "").strip()[:120]
            ident = f' "{txt}"' if txt else " (unlabeled)"
        ident += attrs
        # POSITIONAL / STRUCTURAL CONTEXT. Without this, five identically-named
        # "Launch demo modal" buttons were distinguishable only by guessing that
        # the lowest ref came first in the DOM — correct, but on no positive
        # signal. section= and near= are already computed per element; they just
        # never reached this tool. y= disambiguates repeats down a long page.
        ctx = ""
        if el.get("section"):
            ctx += f"  section={el['section']}"
        if el.get("underHeading"):
            ctx += f"  under={_q(el['underHeading'], 40)}"
        if el.get("near") and el.get("near") != el.get("name"):
            ctx += f"  near={_q(el['near'], 40)}"
        if el.get("y") is not None:
            ctx += f"  y={el.get('y')}"
        flags = ctx
        # find() reaches BELOW THE FOLD (the string listing deliberately does not).
        # Say so, so the agent trusts the ref instead of engineering a scroll first.
        if el.get("offscreen"):
            flags += "  (outside the current viewport — clicking or scroll_to auto-scrolls it into view)"
        if el.get("orphanWidget"):
            flags += "  (DEAD DUPLICATE — no backing form control; prefer the identical backed widget)"
        if el.get("disabled"):
            flags += "  (disabled)"
        if el.get("mediaOnly"):
            flags += "  (image/media — not a control)"
        lines.append(f"  {ref}  [{kind}] {ident}{flags}")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# actions
# ----------------------------------------------------------------------------


@mcp.tool()
async def form_input(
    ref: Annotated[str, Field(description="Element ref from read_page/find (e.g. \"ref_12\").")],
    value: Annotated[
        Union[str, bool, float],
        Field(description="Value to set. Checkboxes: boolean. Selects/comboboxes: option text. Inputs: string/number."),
    ],
    tabId: Annotated[int, Field(description="Tab ID to act in.")],
) -> str:
    """Set the value of a form element (text input, textarea, select, ARIA combobox,
    checkbox, radio, rich editor) by ref. Handles Radix/shadcn/HeadlessUI/MUI
    dropdowns and React controlled inputs correctly."""
    b = await _bridge()
    selector = _ref_to_selector(ref)
    text = ("true" if value else "false") if isinstance(value, bool) else str(value)
    res = await b.call("fill_field", selector=selector, text=text, tabId=tabId)
    await _record_action_frame(tabId, f"form_input {ref}")
    return str(res)


@mcp.tool()
async def fill_form(
    fields: Annotated[
        list[dict],
        Field(description='Fields to fill atomically: [{"ref": "ref_12", "value": "text"}, ...] (selector/mmid/text also accepted).'),
    ],
    tabId: Annotated[int, Field(description="Tab ID to act in.")],
    submit_ref: Annotated[
        Optional[str],
        Field(description="Optional ref of the submit button to click after filling (auto-detected if omitted and submit=true)."),
    ] = None,
    submit: Annotated[bool, Field(description="Click the submit button after filling.")] = False,
) -> str:
    """ChromeBridge power-tool: atomically fill an ENTIRE multi-field form (text,
    dropdowns, checkboxes) in ONE call, with per-field verification, React-safe
    batched writes, validation-error capture and unfilled-field reporting.
    Strongly preferred over many form_input calls for multi-field forms."""
    b = await _bridge()
    norm: list[dict] = []
    for f in fields:
        sel = f.get("selector") or (f.get("ref") and _ref_to_selector(f["ref"])) or (
            f.get("mmid") is not None and f"[mmid='{f['mmid']}']"
        )
        if not sel:
            raise ValueError(f"field missing ref/selector/mmid: {f!r}")
        val = f.get("value", f.get("text", ""))
        text = ("true" if val else "false") if isinstance(val, bool) else str(val)
        norm.append({"selector": sel, "text": text, "trusted": bool(f.get("trusted"))})
    submit_mmid = None
    if submit_ref:
        m = re.search(r"mmid='([^']+)'", _ref_to_selector(submit_ref))
        submit_mmid = m.group(1) if m else None
    # The extension auto-detects the submit button when submit_mmid is omitted;
    # no_submit suppresses that when the caller only wants the fields filled.
    # Budget the timeout to the actual work: each non-text field can legitimately
    # burn ~5s in fillDropdown's open/retry/search/verify chain, and the submit adds
    # up to ~4s of settling. The old flat 30s made large forms time out on the Python
    # side while the extension carried on and submitted — the model then retried and
    # double-submitted. Generous, still bounded.
    ff_timeout = 20.0 + 6.0 * len(norm) + (15.0 if (submit or submit_ref) else 0.0)
    res = await b.call(
        "fill_form",
        request_timeout=ff_timeout,
        fields=norm,
        submit_mmid=submit_mmid,
        submit_trusted=True,
        no_submit=not (submit or submit_ref),
        tabId=tabId,
    )
    await _record_action_frame(tabId, "fill_form")
    return str(res)


@mcp.tool()
async def read_interactive_elements(
    tabId: Annotated[int, Field(description="Tab ID to read from.")],
) -> str:
    """ChromeBridge power-tool: the raw interactive-element listing with mmid refs,
    name/value/placeholder separation and modal/below-fold/occlusion flags.
    Same data as read_page(filter='interactive')."""
    b = await _bridge()
    res = await b.call("get_interactive_elements", tabId=tabId)
    return str(res)


_COMPUTER_ACTIONS = (
    "left_click right_click double_click triple_click type key screenshot wait "
    "scroll left_click_drag zoom scroll_to hover"
).split()


@mcp.tool()
async def computer(
    action: Annotated[
        str,
        Field(description="One of: left_click, right_click, double_click, triple_click, type, key, screenshot, wait, scroll, left_click_drag, zoom, scroll_to, hover."),
    ],
    tabId: Annotated[int, Field(description="Tab ID to execute the action on.")],
    coordinate: Annotated[
        Optional[list[float]],
        Field(description="(x, y) viewport CSS pixels for click/scroll/hover; end position for left_click_drag."),
    ] = None,
    text: Annotated[
        Optional[str],
        Field(description='Text to type (action "type") or key(s) to press (action "key", e.g. "Enter", "ctrl+a", space-separated sequence).'),
    ] = None,
    modifiers: Annotated[
        Optional[str],
        Field(description='Modifier keys for clicks: "ctrl", "shift", "alt", "cmd"/"meta" — combinable with "+".'),
    ] = None,
    ref: Annotated[
        Optional[str],
        Field(description="Element ref alternative to coordinate for clicks/hover; required for scroll_to."),
    ] = None,
    region: Annotated[
        Optional[list[float]],
        Field(description="(x0, y0, x1, y1) rectangle for zoom."),
    ] = None,
    start_coordinate: Annotated[
        Optional[list[float]],
        Field(description="(x, y) start position for left_click_drag."),
    ] = None,
    duration: Annotated[
        Optional[float], Field(description="Seconds to wait (action 'wait', max 10).")
    ] = None,
    scroll_direction: Annotated[
        Optional[str], Field(description='"up", "down", "left", "right" (action "scroll").')
    ] = None,
    scroll_amount: Annotated[
        Optional[int], Field(description="Scroll wheel ticks 1-10 (default 3).")
    ] = None,
    repeat: Annotated[
        Optional[int], Field(description="Repeat count 1-100 for the key action.")
    ] = None,
) -> list:
    """Use a mouse and keyboard to interact with the page, and take screenshots.
    Clicks are TRUSTED Chrome DevTools Protocol input (isTrusted=true) — they work
    on login/OAuth/payment flows. Consult a screenshot before clicking coordinates;
    prefer refs from read_page/find when you have them."""
    if action not in _COMPUTER_ACTIONS:
        raise ValueError(f"unknown action {action!r} — must be one of {_COMPUTER_ACTIONS}")

    if action == "screenshot":
        _t0 = time.monotonic()
        png, image_id = await _take_screenshot(tabId)
        _ms = (time.monotonic() - _t0) * 1000.0
        return [_image_content(png), TextContent(
            type="text",
            text=f"screenshot captured (imageId: {image_id}, {len(png) // 1024} KB, capture took {_ms:.0f} ms)")]

    if action == "wait":
        secs = min(float(duration or 1.0), 10.0)
        await asyncio.sleep(secs)
        return [TextContent(type="text", text=f"waited {secs:g}s")]

    if action == "zoom":
        if not region or len(region) != 4:
            raise ValueError("zoom requires region=[x0,y0,x1,y1]")
        from PIL import Image as PILImage

        b = await _bridge()
        png, _ = await _take_screenshot(tabId)
        img = PILImage.open(io.BytesIO(png))
        # region is in CSS px; the capture is in device px — scale by their ratio.
        try:
            vp = await b.call("javascript_exec", code="({w: innerWidth, h: innerHeight})", tabId=tabId)
            vw = float(vp.get("result", {}).get("w") or vp.get("w") or img.width)
        except Exception:
            vw = float(img.width)
        scale = img.width / max(vw, 1.0)
        x0, y0, x1, y1 = [max(0, v * scale) for v in region]
        crop = img.crop((int(x0), int(y0), int(min(x1, img.width)), int(min(y1, img.height))))
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        zoom_png = buf.getvalue()
        image_id = _store_image(zoom_png)
        return [_image_content(zoom_png), TextContent(type="text", text=f"zoomed region {region} (imageId: {image_id})")]

    # everything else is a real input action — handled by the extension over CDP
    b = await _bridge()
    params: dict[str, Any] = {"action": action, "tabId": tabId}
    if coordinate:
        params["coordinate"] = coordinate
    if start_coordinate:
        params["start_coordinate"] = start_coordinate
    if text is not None:
        params["text"] = text
    if modifiers:
        params["modifiers"] = modifiers
    if ref:
        params["selector"] = _ref_to_selector(ref)
    if scroll_direction:
        params["scroll_direction"] = scroll_direction
    if scroll_amount:
        params["scroll_amount"] = scroll_amount
    if repeat:
        params["repeat"] = repeat
    res = await b.call("computer", **params)
    await _record_action_frame(tabId, f"{action}")
    return [TextContent(type="text", text=str(res))]


# ----------------------------------------------------------------------------
# debugging: javascript / console / network
# ----------------------------------------------------------------------------


@mcp.tool()
async def javascript_tool(
    action: Annotated[str, Field(description='Must be "javascript_exec".')],
    text: Annotated[
        str,
        Field(description="JavaScript to run in the page (MAIN world) with REPL semantics: top-level await works and the last expression's value is returned."),
    ],
    tabId: Annotated[int, Field(description="Tab ID to execute in.")],
) -> str:
    """Execute JavaScript in the page context. Can read/modify the DOM, call page
    functions and use page variables. Returns the last expression's value."""
    if action != "javascript_exec":
        raise ValueError('action must be "javascript_exec"')
    b = await _bridge()
    res = await b.call("javascript_exec", code=text, tabId=tabId)
    if isinstance(res, dict) and "result" in res:
        val = res["result"]
        return val if isinstance(val, str) else json.dumps(val, default=str)
    return res if isinstance(res, str) else json.dumps(res, default=str)


@mcp.tool()
async def read_console_messages(
    tabId: Annotated[int, Field(description="Tab ID to read console messages from.")],
    pattern: Annotated[
        Optional[str],
        Field(description="Regex filter — always provide one to avoid floods (e.g. 'error|warning', 'MyApp')."),
    ] = None,
    onlyErrors: Annotated[bool, Field(description="Only error/exception messages.")] = False,
    limit: Annotated[int, Field(description="Max messages to return (default 100).")] = 100,
    clear: Annotated[bool, Field(description="Clear the buffer after reading.")] = False,
) -> str:
    """Read browser console messages (console.log/warn/error...) from a tab.
    Captured from document_start by the page-world wrapper; browser-generated
    messages (CSP violations, network errors) are not included."""
    b = await _bridge()
    res = await b.call(
        "read_console_messages",
        tabId=tabId,
        pattern=pattern,
        onlyErrors=onlyErrors,
        limit=limit,
        clear=clear,
    )
    return res if isinstance(res, str) else json.dumps(res)


@mcp.tool()
async def read_network_requests(
    tabId: Annotated[int, Field(description="Tab ID to read network requests from.")],
    urlPattern: Annotated[
        Optional[str],
        Field(description="Only requests whose URL contains this string (e.g. '/api/')."),
    ] = None,
    limit: Annotated[int, Field(description="Max requests to return (default 100).")] = 100,
    clear: Annotated[bool, Field(description="Clear the buffer after reading.")] = False,
) -> str:
    """Read HTTP requests (XHR/fetch/documents/images...) made by a tab: URL, method,
    type, status and timing. Buffered in the extension via chrome.webRequest."""
    b = await _bridge()
    res = await b.call(
        "read_network_requests", tabId=tabId, urlPattern=urlPattern, limit=limit, clear=clear
    )
    return res if isinstance(res, str) else json.dumps(res)


# ----------------------------------------------------------------------------
# window / uploads / gif
# ----------------------------------------------------------------------------


@mcp.tool()
async def resize_window(
    width: Annotated[int, Field(description="Target window width in pixels.")],
    height: Annotated[int, Field(description="Target window height in pixels.")],
    tabId: Annotated[int, Field(description="Tab whose window to resize.")],
) -> str:
    """Resize the browser window (e.g. for responsive testing)."""
    b = await _bridge()
    res = await b.call("resize_window", width=width, height=height, tabId=tabId)
    return str(res)


@mcp.tool()
async def file_upload(
    paths: Annotated[list[str], Field(description="Absolute paths of files to upload (combined < 10 MB).")],
    ref: Annotated[str, Field(description="Ref of the <input type=file> element from read_page/find.")],
    tabId: Annotated[int, Field(description="Tab ID where the file input lives.")],
) -> str:
    """Upload one or more local files to a file input. Do NOT click file-picker
    buttons (the native dialog is invisible to you) — find the input element and
    use this tool with its ref."""
    files = []
    total = 0
    for p in paths:
        if not os.path.isfile(p):
            raise ValueError(f"not a file: {p}")
        size = os.path.getsize(p)
        total += size
        if total > 10 * 1024 * 1024:
            raise ValueError("combined file size exceeds the 10 MB limit")
        with open(p, "rb") as fh:
            data = fh.read()
        files.append(
            {
                "name": os.path.basename(p),
                "b64": base64.b64encode(data).decode("ascii"),
                "mime": mimetypes.guess_type(p)[0] or "application/octet-stream",
            }
        )
    b = await _bridge()
    res = await b.call("file_upload", selector=_ref_to_selector(ref), files=files, tabId=tabId)
    await _record_action_frame(tabId, "file_upload")
    return str(res)


@mcp.tool()
async def upload_image(
    imageId: Annotated[str, Field(description="ID of a previously captured screenshot/zoom (returned by the computer tool).")],
    tabId: Annotated[int, Field(description="Tab ID where the target element is.")],
    ref: Annotated[
        Optional[str],
        Field(description="Ref of the file input / target element. Provide ref OR coordinate."),
    ] = None,
    coordinate: Annotated[
        Optional[list[float]],
        Field(description="(x, y) drop target for drag&drop uploads (e.g. Google Docs)."),
    ] = None,
    filename: Annotated[str, Field(description="Filename for the uploaded file.")] = "image.png",
) -> str:
    """Upload a previously captured screenshot to a file input (ref) or drop it at a
    visible location (coordinate)."""
    png = IMAGES.get(imageId)
    if png is None:
        raise ValueError(f"unknown imageId {imageId!r} — take a screenshot first (computer action=screenshot)")
    if (ref is None) == (coordinate is None):
        raise ValueError("provide exactly one of ref or coordinate")
    b = await _bridge()
    file_payload = [{"name": filename, "b64": base64.b64encode(png).decode("ascii"), "mime": "image/png"}]
    if ref is not None:
        res = await b.call("file_upload", selector=_ref_to_selector(ref), files=file_payload, tabId=tabId)
    else:
        res = await b.call("file_upload", coordinate=coordinate, files=file_payload, tabId=tabId)
    await _record_action_frame(tabId, "upload_image")
    return str(res)


@mcp.tool()
async def gif_creator(
    action: Annotated[str, Field(description='"start_recording", "stop_recording", "export" or "clear".')],
    tabId: Annotated[int, Field(description="Tab the recording applies to.")],
    filename: Annotated[Optional[str], Field(description="Filename for the exported GIF.")] = None,
    download: Annotated[bool, Field(description="Accepted for compatibility; the GIF is written to the project temp/ folder.")] = False,
    options: Annotated[Optional[dict], Field(description="Export options (quality 1-30; overlay options accepted but not rendered).")] = None,
) -> str:
    """Record browser actions as an animated GIF. start_recording -> act (frames are
    captured automatically after each action + every screenshot) -> stop_recording ->
    export. Returns the absolute path of the exported GIF."""
    if action == "start_recording":
        GIF["recording"] = True
        GIF["frames"], GIF["labels"] = [], []
        await _record_action_frame(tabId, "start")
        return "Recording started — frames will be captured after each browser action. Take a screenshot now to seed the first frame."
    if action == "stop_recording":
        await _record_action_frame(tabId, "end")
        GIF["recording"] = False
        return f"Recording stopped with {len(GIF['frames'])} frame(s) buffered. Use action='export' to write the GIF."
    if action == "clear":
        GIF["recording"] = False
        n = len(GIF["frames"])
        GIF["frames"], GIF["labels"] = [], []
        return f"Discarded {n} buffered frame(s)."
    if action == "export":
        frames = GIF["frames"]
        if len(frames) < 2:
            raise RuntimeError(f"only {len(frames)} frame(s) buffered — record some actions first")
        os.makedirs(_TEMP_DIR, exist_ok=True)
        name = filename or f"recording-{int(time.time())}.gif"
        if not name.lower().endswith(".gif"):
            name += ".gif"
        out_path = os.path.join(_TEMP_DIR, name)
        frames[0].save(
            out_path,
            save_all=True,
            append_images=frames[1:],
            duration=700,
            loop=0,
            optimize=True,
        )
        return f"GIF exported: {out_path} ({len(frames)} frames)"
    raise ValueError('action must be one of "start_recording", "stop_recording", "export", "clear"')


# ----------------------------------------------------------------------------
# batch
# ----------------------------------------------------------------------------

_BATCHABLE = {}  # name -> coroutine fn; populated below


@mcp.tool()
async def browser_batch(
    actions: Annotated[
        list[dict],
        Field(description='Tool calls to run sequentially: [{"name": "navigate", "input": {"url": "...", "tabId": 1}}, ...]. Stops on the first error. Cannot be nested.'),
    ],
) -> list:
    """Execute a sequence of browser tool calls in ONE round trip. Each item is
    {name, input} with input exactly what you'd pass to that tool standalone.
    Use whenever you can predict two or more steps ahead. Coordinates in this
    batch refer to the screenshot taken BEFORE the batch."""
    out: list = []
    for i, item in enumerate(actions):
        name = item.get("name")
        fn = _BATCHABLE.get(name)
        if fn is None:
            out.append(TextContent(type="text", text=f"[{i}] ERROR: unknown or non-batchable tool {name!r}"))
            break
        try:
            res = await fn(**(item.get("input") or {}))
        except Exception as e:
            out.append(TextContent(type="text", text=f"[{i}] {name} ERROR: {e} — batch stopped"))
            break
        if isinstance(res, list):
            out.append(TextContent(type="text", text=f"[{i}] {name}:"))
            out.extend(res)
        else:
            out.append(TextContent(type="text", text=f"[{i}] {name}: {res}"))
    return out


_BATCHABLE.update(
    {
        "tabs_context_mcp": tabs_context_mcp,
        "tabs_create_mcp": tabs_create_mcp,
        "tabs_close_mcp": tabs_close_mcp,
        "navigate": navigate,
        "read_page": read_page,
        "get_url": get_url,
        "get_page_text": get_page_text,
        "find": find,
        "form_input": form_input,
        "fill_form": fill_form,
        "read_interactive_elements": read_interactive_elements,
        "computer": computer,
        "javascript_tool": javascript_tool,
        "read_console_messages": read_console_messages,
        "read_network_requests": read_network_requests,
        "resize_window": resize_window,
        "file_upload": file_upload,
        "upload_image": upload_image,
    }
)


if __name__ == "__main__":
    mcp.run()  # stdio transport — stdout is JSON-RPC, logs go to stderr
