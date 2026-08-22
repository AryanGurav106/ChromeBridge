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
        await browser.close()

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} pixel-scaling checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
