#!/usr/bin/env python3
"""Make the Aero wallpapers for the touch screen: assets/aero-wallpaper.bin and
assets/aero-wallpaper-light.bin (light mode's own wallpaper).

The source is branding/aero-wallpaper.png (800x480, the wallpaper of
ui-mockups/html/Aero.html without any chrome). The result is an LVGL image
file in raw RGB565, the format of the screen itself:

  - nothing has to be decoded when the screen is redrawn. A PNG would be
    decoded again for every redraw if the image cache is off, and on the
    printer's single slow core that makes every touch feel late.
  - dithered, because RGB565 has only 32 to 64 levels per colour and a dark
    gradient would otherwise show bands.

    python3 branding/make-aero-wallpaper.py        (needs Pillow; node with Playwright to
                                                     redraw aero-wallpaper-light.png from its .svg)

File layout (LVGL 9, 12 byte header, then rows of 16 bit pixels):
  magic 0x19, color format 0x12 (RGB565), flags 0, width, height, stride, 0
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from rgb565 import convert  # noqa: E402
ASSETS = HERE.parent / 'files/3-rinkhals/opt/rinkhals/ui/assets'
WALLPAPERS = ((HERE / 'aero-wallpaper.png', ASSETS / 'aero-wallpaper.bin'),
              (HERE / 'aero-wallpaper-light.png', ASSETS / 'aero-wallpaper-light.bin'))

RENDER = """
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 800, height: 480 } });
  await page.goto(process.argv[1]);
  await page.screenshot({ path: process.argv[2] });
  await browser.close();
})();
"""


def draw_light():
    """aero-wallpaper-light.png from aero-wallpaper-light.svg, when node and Playwright are there."""
    import shutil
    import subprocess
    svg = HERE / 'aero-wallpaper-light.svg'
    if shutil.which('node'):
        subprocess.run(['node', '-e', RENDER, f'file://{svg}', str(WALLPAPERS[1][0])], check=True, timeout=120)


if __name__ == '__main__':
    draw_light()
    for source, target in WALLPAPERS:
        size = convert(source, target)
        print(f'{target.relative_to(HERE.parent)}: {size} bytes')
