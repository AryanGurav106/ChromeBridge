"""Generate the ChromeBridge extension icon set into extension/icons/.

    .venv\\Scripts\\python.exe tools\\make_icons.py

The mark is the site's cursor: a bone-white pointer outlined in the canvas
colour, with Claude's orange (#FF6B35) copy offset behind it, on a near-black
tile. Everything is drawn once at 1024px and LANCZOS-downsampled, which is what
keeps the 16px toolbar rendering clean.

The same geometry is inlined as SVG in the side panel header (panel.html):
a 28-unit viewBox, the lucide mouse-pointer path, and the orange copy shifted
by (4.5, 4.5). If you change the numbers here, change them there too.
"""
import os
from PIL import Image, ImageDraw

S = 1024                      # master render size
SIZES = (16, 32, 48, 128)     # what manifest.json declares

TILE_TOP = (30, 30, 34)       # site tile gradient, rgba(30,30,34) -> (16,16,18)
TILE_BOT = (16, 16, 18)
TILE_EDGE = (58, 58, 64)      # the tile's hairline highlight
BONE = (237, 237, 239)        # #EDEDEF
CANVAS = (10, 10, 11)         # #0A0A0B
ACCENT = (255, 107, 53)       # #FF6B35

TILE_INSET = 0.02
TILE_RADIUS = 0.235

# The lucide mouse-pointer path in its own 24-unit space, corners flattened to
# their endpoints (the arcs are ~0.5 units, invisible below 128px).
POINTER = [(4.30, 4.30), (20.69, 10.54), (20.63, 11.48), (14.50, 13.06),
           (13.06, 14.50), (11.48, 20.63), (10.54, 20.69)]
VIEW = 28.0                   # panel.html viewBox
MARK_SCALE = 0.86             # how much of the tile the 28-unit box spans
SHADOW = (4.5, 4.5)           # the orange copy's offset, in path units
OUTLINE = 2.2                 # canvas-coloured stroke, in path units


def tile(size):
    g = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(g)
    for y in range(size):
        t = y / (size - 1)
        d.line([(0, y), (size, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(TILE_TOP, TILE_BOT)))
    m = Image.new("L", (size, size), 0)
    a = TILE_INSET * size
    ImageDraw.Draw(m).rounded_rectangle([a, a, size - a - 1, size - a - 1],
                                        radius=TILE_RADIUS * size, fill=255)
    out = g.convert("RGBA")
    out.putalpha(m)
    edge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(edge).rounded_rectangle([a, a, size - a - 1, size - a - 1],
                                           radius=TILE_RADIUS * size,
                                           outline=TILE_EDGE + (255,), width=max(2, size // 128))
    return Image.alpha_composite(out, edge)


def pointer_pts(size, dx=0.0, dy=0.0):
    k = size * MARK_SCALE / VIEW
    off = size * (1 - MARK_SCALE) / 2
    return [(off + (x + dx) * k, off + (y + dy) * k) for x, y in POINTER]


def build():
    img = tile(S)
    d = ImageDraw.Draw(img)
    k = S * MARK_SCALE / VIEW
    d.polygon(pointer_pts(S, *SHADOW), fill=ACCENT)
    pts = pointer_pts(S)
    # Outline first, fat and round-jointed, then the fill on top of it: the
    # same result as SVG's centred stroke with stroke-linejoin="round".
    w = int(OUTLINE * k)
    d.line(pts + [pts[0]], fill=CANVAS, width=w, joint="curve")
    for x, y in pts:
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=CANVAS)
    d.polygon(pts, fill=BONE)
    return img


def main():
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "extension", "icons")
    os.makedirs(out, exist_ok=True)
    master = build()
    for s in SIZES:
        p = os.path.join(out, f"icon{s}.png")
        master.resize((s, s), Image.LANCZOS).save(p)
        print(f"wrote {p}")


if __name__ == "__main__":
    main()
