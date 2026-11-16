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
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from rgb565 import convert  # noqa: E402
SOURCE = HERE / 'aero-wallpaper.png'
TARGET = HERE.parent / 'files/3-rinkhals/opt/rinkhals/ui/assets/aero-wallpaper.bin'

if __name__ == '__main__':
    size = convert(SOURCE, TARGET)
    print(f'{TARGET.relative_to(HERE.parent)}: {size} bytes')
