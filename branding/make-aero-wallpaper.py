#!/usr/bin/env python3
"""Make the Aero wallpaper for the touch screen: assets/aero-wallpaper.bin.

The source is branding/aero-wallpaper.png (800x480, the wallpaper of
ui-mockups/html/Aero.html without any chrome). The result is an LVGL image
file in raw RGB565, the format of the screen itself:

  - nothing has to be decoded when the screen is redrawn. A PNG would be
    decoded again for every redraw if the image cache is off, and on the
    printer's single slow core that makes every touch feel late.
  - dithered, because RGB565 has only 32 to 64 levels per colour and a dark
    gradient would otherwise show bands.

    python3 branding/make-aero-wallpaper.py        (needs Pillow)

File layout (LVGL 9, 12 byte header, then rows of 16 bit pixels):
  magic 0x19, color format 0x12 (RGB565), flags 0, width, height, stride, 0
"""
import struct
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'aero-wallpaper.png'
TARGET = HERE.parent / 'files/3-rinkhals/opt/rinkhals/ui/assets/aero-wallpaper.bin'

def to_rgb565(image):
    """Floyd-Steinberg error diffusion, per channel: the colours stay right on average.

    (A fixed pattern used for all three channels left tinted patches in the
    dark areas, because red and blue have 32 levels and green 64.)
    """
    width, height = image.size
    source = image.convert('RGB').load()
    levels = (31, 63, 31)
    shifts = (11, 5, 0)
    out = bytearray()
    # error carried to the next pixel and to the row below, per channel
    below = [[0.0] * 3 for _ in range(width + 2)]
    for y in range(height):
        current = below
        below = [[0.0] * 3 for _ in range(width + 2)]
        carry = [0.0, 0.0, 0.0]
        for x in range(width):
            value = 0
            pixel = source[x, y]
            for c in range(3):
                wanted = pixel[c] * levels[c] / 255 + current[x + 1][c] + carry[c]
                chosen = min(levels[c], max(0, int(wanted + 0.5)))
                error = wanted - chosen
                carry[c] = error * 7 / 16
                below[x][c] += error * 3 / 16
                below[x + 1][c] += error * 5 / 16
                below[x + 2][c] += error * 1 / 16
                value |= chosen << shifts[c]
            out += struct.pack('<H', value)
    return bytes(out)


def build():
    image = Image.open(SOURCE)
    width, height = image.size
    header = struct.pack('<BBHHHHH', 0x19, 0x12, 0, width, height, width * 2, 0)
    assert len(header) == 12
    return header + to_rgb565(image)


if __name__ == '__main__':
    data = build()
    TARGET.write_bytes(data)
    print(f'{TARGET.relative_to(HERE.parent)}: {len(data)} bytes')
