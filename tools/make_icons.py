"""Generate the ChromeBridge extension icon set into extension/icons/.

    .venv\\Scripts\\python.exe tools\\make_icons.py

The mark is a bridge span: two anchor nodes joined by a cable arc, white on an
indigo->violet diagonal gradient squircle. Everything is drawn once at 1024px
and LANCZOS-downsampled, which is what keeps the 16px toolbar rendering clean --
earlier variants with thinner strokes or a smaller mark turned to mush there.

The same geometry is inlined as SVG in the side panel header (panel.html), so
if you change the numbers here, change them there too.
"""
import os
from PIL import Image, ImageDraw

S = 1024                      # master render size
SIZES = (16, 32, 48, 128)     # what manifest.json declares
C0 = (79, 70, 229)            # indigo-600
C1 = (147, 51, 234)           # purple-600

# --- mark geometry, normalized 0..1 (mirrored in panel.html's inline SVG) -----
NODE_Y   = 0.685
NODE_LX  = 0.200
NODE_RX  = 0.800
NODE_R   = 0.130
ARC_BOX  = (0.200, 0.335, 0.800, 1.035)   # ellipse bbox; top half is the cable
ARC_W    = 0.105
TILE_INSET  = 0.02
TILE_RADIUS = 0.235


def gradient(size):
    """Diagonal linear gradient, top-left C0 -> bottom-right C1."""
    g = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(g)
    for i in range(2 * size):
        t = i / (2.0 * size - 1)
        d.line([(i, 0), (0, i)],
               fill=(int(C0[0] + (C1[0] - C0[0]) * t),
                     int(C0[1] + (C1[1] - C0[1]) * t),
                     int(C0[2] + (C1[2] - C0[2]) * t)),
               width=2)
    return g


def squircle_mask(size):
    m = Image.new("L", (size, size), 0)
    a = TILE_INSET * size
    ImageDraw.Draw(m).rounded_rectangle(
        [a, a, size - a - 1, size - a - 1], radius=TILE_RADIUS * size, fill=255)
    return m


def mark_mask(size):
    layer = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(layer)
    u = lambda v: v * size
    d.arc([u(ARC_BOX[0]), u(ARC_BOX[1]), u(ARC_BOX[2]), u(ARC_BOX[3])],
          180, 360, fill=255, width=int(u(ARC_W)))
    for cx in (NODE_LX, NODE_RX):
        d.ellipse([u(cx - NODE_R), u(NODE_Y - NODE_R),
                   u(cx + NODE_R), u(NODE_Y + NODE_R)], fill=255)
    return layer


def build():
    base = gradient(S).convert("RGBA")
    base.putalpha(squircle_mask(S))
    fg = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    fg.putalpha(mark_mask(S))
    return Image.alpha_composite(base, fg)


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
