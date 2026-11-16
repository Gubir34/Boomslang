"""PNG -> LVGL raw RGB565 image file (shared by make-aero-wallpaper.py and make-liquid.py).

LVGL 9 format: a 12 byte header (magic 0x19, color format 0x12 = RGB565,
flags 0, width, height, stride, 0) and then rows of little-endian 16 bit
pixels. Nothing has to be decoded when the screen is redrawn, which matters
because with LVGL's image cache off a PNG is decoded again on every redraw.
"""
import struct

from PIL import Image


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


def convert(source, target):
    """Write source (a PNG) as an LVGL RGB565 image to target. Returns the size in bytes."""
    image = Image.open(source)
    width, height = image.size
    header = struct.pack('<BBHHHHH', 0x19, 0x12, 0, width, height, width * 2, 0)
    assert len(header) == 12
    data = header + to_rgb565(image)
    with open(target, 'wb') as f:
        f.write(data)
    return len(data)
