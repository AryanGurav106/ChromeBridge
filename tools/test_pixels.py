"""Verify the device-pixel -> CSS-pixel screenshot normalisation on a REALLY scaled display.

Why this exists: `captureVisibleTab` returns DEVICE pixels while CDP
`Input.dispatchMouseEvent` (every `computer` click) takes CSS pixels. On a display scaled
to 125% — the Windows laptop default — every screenshot-derived coordinate click lands
~25% off toward the bottom-right, silently, while ref-based clicks keep working, which
makes the failure look random. `mcp_server._to_css_pixels` normalises the image so
screenshot space and click space are the same space.

That fix was previously verified only against synthetic solid-colour PNGs, because the
development machine reports `devicePixelRatio: 1` and the downscale branch never fires
there. Playwright can emulate a scaled display (`device_scale_factor`), so this test
exercises the branch against a REAL browser capture at 1.0 / 1.25 / 2.0, and — the part
that actually matters — checks that a coordinate measured on the normalised image maps
back to the element's CSS-pixel box.

Run:  python tools/test_pixels.py
"""

import asyncio
import importlib.util
import io
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent

# Import mcp_server for the real _to_css_pixels (module only defines things at import).
_spec = importlib.util.spec_from_file_location("ms", ROOT / "mcp_server.py")
_ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ms)

PAGE = """
<!DOCTYPE html><meta charset="utf-8">
<body style="margin:0">
  <div style="height:300px"></div>
  <button id="t" style="position:absolute;left:400px;top:300px;width:120px;height:40px">Target</button>
</body>
"""

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _extract import extract as _shared_extract  # noqa: E402

_BG = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
HIT = _shared_extract("_hitTestPage", _BG, verify=True)
ECHO = _shared_extract("_hitEcho", _BG, verify=True)

# The page a coordinate click can get wrong in every way that matters. The veil is
# TRANSPARENT on purpose: it paints nothing, so a pixel comparison asking "is the
# button there?" sees the button and concludes the click will land — while every
# click in that region goes to the veil. Only the renderer's own hit test knows,
# which is the argument for doing this with elementsFromPoint rather than pixels.
_HIT_PAGE = """<!doctype html><meta charset=utf-8><body style="margin:0">
<button id=want mmid="7" style="position:absolute;left:40px;top:40px;width:120px;height:30px">Add to cart</button>
<div id=veil mmid="9" style="position:absolute;left:0;top:0;width:400px;height:200px;background:transparent"></div>
<button id=clear mmid="11" style="position:absolute;left:40px;top:300px;width:120px;height:30px">Clear target</button>
<div id=host mmid="13" style="position:absolute;left:40px;top:400px;width:120px;height:30px"></div>
<button id=outer mmid="21" style="position:absolute;left:40px;top:480px;width:160px;height:34px">
  <span id=inner mmid="23">Save changes</span></button>
<script>
window.__mmidReg = new Map([["7",document.getElementById('want')],
  ["9",document.getElementById('veil')],["11",document.getElementById('clear')],
  ["13",document.getElementById('host')],["21",document.getElementById('outer')],
  ["23",document.getElementById('inner')]]);
document.getElementById('host').attachShadow({mode:'open'}).innerHTML =
  '<button style="width:120px;height:30px">Inside shadow</button>';
</script></body>"""


async def _hit_echo_checks(browser, check):
    """The coordinate path's only observation of where a click actually goes.

    A ref action re-measures at click time and refuses when a foreign element is on
    top; a coordinate action dispatched blind and reported its own input back, which
    is why every failure in the #10/#11/#12 family looked like success. These pin
    the echo that closes it — including the case pixels provably cannot catch.
    """
    pg = await browser.new_page(viewport={"width": 800, "height": 600})
    await pg.set_content(_HIT_PAGE)
    await pg.wait_for_timeout(120)

    async def hit(x, y):
        return await pg.evaluate("(function(){ " + HIT + "; return _hitTestPage("
                                 + str(x) + "," + str(y) + "); })()")

    async def echo(x, y, sel):
        arg = '"' + sel + '"' if sel else "null"
        return await pg.evaluate("(function(){ " + HIT + ";" + ECHO
                                 + "; return _hitEcho(_hitTestPage(" + str(x) + ","
                                 + str(y) + "), " + arg + "); })()")

    h = await hit(100, 55)
    check("X10 a TRANSPARENT overlay is reported as the hit target, which pixels cannot see",
          h["ref"] == "9", "ref=" + repr(h["ref"]) + " (9 is the veil, 7 is the button under it)")
    m = await echo(100, 55, "[mmid='7']")
    check("X10b ...and naming the covered ref produces an explicit MISMATCH",
          "MISMATCH" in m and "ref_7" in m and "ref_9" in m, m.strip()[:130])

    h = await hit(100, 315)
    check("X11 an unobstructed control resolves to its own ref, with its label",
          h["ref"] == "11" and "Clear target" in (h["label"] or ""),
          "ref=" + repr(h["ref"]) + " label=" + repr(h["label"]))
    _agree = await echo(100, 315, "[mmid='11']")
    check("X11b ...and agreement on a named ref says NOTHING (no per-click noise)",
          _agree.strip() == "", repr(_agree))
    _bare = await echo(100, 315, None)
    check("X11c ...while a BARE coordinate is handed the ref to act on instead",
          "ref_11" in _bare, _bare.strip()[:120])

    h = await hit(100, 415)
    check("X12 the hit test pierces a shadow root, as a real click does",
          h["ref"] == "13" and h["deep"] >= 1,
          "ref=" + repr(h["ref"]) + " deep=" + repr(h["deep"]))

    # X15/X15b: YOUR OWN SUBTREE IS NOT AN OCCLUDER. Reported live an hour after the
    # echo shipped: naming ref_115 produced
    #   "MISMATCH: you named ref_115, but the renderer hit-tests ref_117 <slot>
    #    (inside a shadow root) — something is on top, or the layout moved"
    # while ref_117 was ref_115's OWN CHILD, indented under it in the same listing.
    # Nothing was on top, nothing had moved, and the click worked. A false MISMATCH
    # is worse than no echo at all: it tells the agent its aim is wrong when it is
    # right, and the natural response is to go hunting coordinates. Any control with
    # inner markup — a <slot>, an icon <span>, a label — hits its own inside.
    h = await hit(120, 497)
    check("X15 clicking the inside of a control resolves to the INNERMOST ref",
          h["ref"] == "23", "ref=" + repr(h["ref"]) + " (23 is the inner span of button 21)")
    _own = await echo(120, 497, "[mmid='21']")
    check("X15b ...and naming the OUTER control is NOT a mismatch — the event bubbles"
          " to it, which is what clicking it means",
          _own.strip() == "" and "MISMATCH" not in _own, repr(_own[:110]))
    _real = await echo(100, 55, "[mmid='11']")
    check("X15c ...while a ref that is genuinely NOT in the chain still mismatches"
          " (the guard did not blanket-silence the echo)",
          "MISMATCH" in _real, _real.strip()[:110])

    h = await hit(700, 550)
    check("X13 a point over no control names what IS there rather than shrugging",
          h["ref"] is None and h["tag"] == "html",
          "ref=" + repr(h["ref"]) + " tag=" + repr(h["tag"]))

    h = await hit(900, 55)
    check("X14 a point outside the viewport is reported as such, not as a hit",
          h["oob"] is True and h["ref"] is None,
          "oob=" + repr(h["oob"]) + " ref=" + repr(h["ref"]))
    _oob = await echo(900, 55, None)
    check("X14b ...in words", "outside the viewport" in _oob, _oob.strip()[:90])
    await pg.close()


results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for dsf in (1.0, 1.25, 2.0):
            ctx = await browser.new_context(viewport={"width": 800, "height": 600},
                                            device_scale_factor=dsf)
            page = await ctx.new_page()
            await page.set_content(PAGE)
            await page.wait_for_timeout(80)

            shot = await page.screenshot()          # DEVICE pixels, like captureVisibleTab
            css_w = await page.evaluate("innerWidth")
            dev_w = Image.open(io.BytesIO(shot)).width

            # Precondition: Playwright really is emulating the scale we asked for.
            check(f"dsf={dsf}: capture is device-pixel width ({dev_w} == {css_w}*{dsf})",
                  abs(dev_w - css_w * dsf) <= 1, f"capture={dev_w} css={css_w}")

            norm = _ms._to_css_pixels(shot, css_w)
            nimg = Image.open(io.BytesIO(norm))
            check(f"dsf={dsf}: normalised image is CSS-pixel width",
                  nimg.width == css_w, f"normalised={nimg.width} expected={css_w}")

            # The point of the whole exercise: a coordinate read off the NORMALISED image
            # must be the coordinate CDP needs. Locate the button in the normalised image
            # by its own CSS box and confirm the pixel there belongs to the button.
            box = await page.evaluate(
                "() => { const r = document.getElementById('t').getBoundingClientRect();"
                " return {x: r.left + r.width/2, y: r.top + r.height/2}; }")
            cx, cy = int(box["x"]), int(box["y"])
            # Button is default-styled (grey-ish) against a white page; sample and compare.
            px = nimg.convert("RGB").getpixel((cx, cy))
            white = px[0] > 240 and px[1] > 240 and px[2] > 240
            check(f"dsf={dsf}: CSS coords ({cx},{cy}) hit the button in the normalised image",
                  not white, f"pixel={px} (white would mean we sampled empty page)")

            # And the un-normalised image must FAIL that same test at 125%/200% — proof the
            # bug was real rather than the normalisation being a no-op dressed up as a fix.
            if dsf != 1.0:
                oimg = Image.open(io.BytesIO(shot)).convert("RGB")
                opx = oimg.getpixel((cx, cy))
                owhite = opx[0] > 240 and opx[1] > 240 and opx[2] > 240
                check(f"dsf={dsf}: RAW capture does NOT hit the button at CSS coords (bug reproduced)",
                      owhite, f"pixel={opx}")

            await ctx.close()
        # The hit-echo checks reuse this browser: they need no display scaling, only
        # a page whose layout is known, so they run once rather than per DPR.
        await _hit_echo_checks(browser, check)
        await browser.close()

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} pixel-scaling checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
