#!/usr/bin/env python3
"""Make the LemSearch icon for the printer: a thick "L" with a small magnifier in its corner.

    python3 branding/make-lemsearch-icon.py        (needs Pillow)

The icon is not in the Material Icons font, so it is an image. It is drawn
from the same geometry as the SVG in branding/ui-mockups/html/LemSearch.html
(a 32 x 32 box), eight times larger, then made smaller so the edges are
smooth, and written as an LVGL 9 A8 image: only how much each pixel covers.
LVGL paints an A8 image in the style's image recolor colour, so the one file
is green on Classic, dark on Aero and white on Liquid Plastic, like the icon
font it stands next to.

It is made at a few sizes, and the screen uses the one closest to its icon
font without scaling: LVGL's scaling of a small image left jagged edges.

Writes files/3-rinkhals/opt/rinkhals/ui/assets/lemsearch-icon-<size>.bin and,
for looking at, branding/lemsearch-icon.png.
"""
import struct
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / 'files/3-rinkhals/opt/rinkhals/ui/assets'
SIZES = (22, 26, 30, 34)    # pixels: about 0.85 x the icon font on the printers' screens (dpx(32) at 130 and 180 dpi)
SIZE = 30
SUPER = 8          # drawn this many times larger, then made smaller: smooth edges


def draw(size=SIZE):
    big = size * SUPER
    k = big / 32                     # one unit of the SVG's 32 x 32 box
    image = Image.new('L', (big, big), 0)
    pen = ImageDraw.Draw(image)

    def box(x0, y0, x1, y1):
        pen.rectangle([x0 * k, y0 * k, x1 * k, y1 * k], fill=255)

    # the L: path M8 4 V26 H20, 6 wide, square ends and a mitred corner
    box(5, 1, 11, 29)
    box(5, 23, 23, 29)
    # the magnifier: a ring around (19, 12), radius 4.5, 2.5 wide...
    outer, inner = 4.5 + 1.25, 4.5 - 1.25
    pen.ellipse([(19 - outer) * k, (12 - outer) * k, (19 + outer) * k, (12 + outer) * k], fill=255)
    pen.ellipse([(19 - inner) * k, (12 - inner) * k, (19 + inner) * k, (12 + inner) * k], fill=0)
    # ...and its handle from (22.2, 15.2) to (25.8, 18.8), 2.5 wide with round ends
    width = 2.5 * k
    pen.line([(22.2 * k, 15.2 * k), (25.8 * k, 18.8 * k)], fill=255, width=round(width))
    for x, y in ((22.2, 15.2), (25.8, 18.8)):
        r = width / 2
        pen.ellipse([x * k - r, y * k - r, x * k + r, y * k + r], fill=255)
    return image.resize((size, size), Image.LANCZOS)


def write_a8(image, target):
    """LVGL 9 image: header (magic 0x19, colour format 0x0E = A8, flags, w, h, stride, 0), then one byte a pixel."""
    width, height = image.size
    header = struct.pack('<BBHHHHH', 0x19, 0x0E, 0, width, height, width, 0)
    Path(target).write_bytes(header + image.tobytes())
    return len(header) + width * height


def main():
    for size in SIZES:
        target = ASSETS / f'lemsearch-icon-{size}.bin'
        print(f'{target.relative_to(HERE.parent)}: {write_a8(draw(size), target)} bytes')
    icon = draw(SIZE)
    preview = Image.new('RGB', icon.size, (255, 255, 255))
    preview.paste((16, 33, 15), mask=icon)
    preview.resize((SIZE * 4, SIZE * 4), Image.NEAREST).save(HERE / 'lemsearch-icon.png')


if __name__ == '__main__':
    main()
