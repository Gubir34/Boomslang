#!/usr/bin/env python3
"""Make everything of the Liquid Plastic look that is drawn rather than coded.

    python3 branding/make-liquid.py        (needs Pillow and Firefox; the mockups also fetch fonts)

From the positions in files/3-rinkhals/opt/rinkhals/ui/liquid_layout.py it makes

  branding/ui-mockups/html/Liquid.html, LiquidPanel.html and png/Liquid.png,
  png/LiquidPanel.png     the mockups: the home screen, and with the quick settings open
  .../ui/assets/liquid-home.bin     the home screen's wallpaper with its glass panes in it
  .../ui/assets/liquid-panel.bin    the same with the quick settings panel open

The look is "liquid glass": clear curved panes that blur and tint what is behind
them, lit from the top left, with a thin rim that is bright where the light hits
it. LVGL can't blur what is behind a widget and the printer's CPU could not do it
every frame anyway. But the panes sit on a fixed wallpaper, so the browser draws
them into the wallpaper once, here, and the printer only shows the picture. What
changes (icons, text, the clock, the slider, a pressed pane) is drawn live on top,
in the places liquid_layout.py names.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
UI = HERE.parent / 'files/3-rinkhals/opt/rinkhals/ui'
sys.path.insert(0, str(UI))
sys.path.insert(0, str(HERE))

import liquid_layout as L  # noqa: E402
from rgb565 import convert  # noqa: E402

MOCKUPS = HERE / 'ui-mockups'

CSS = """
  html, body { margin: 0; background: #000; }
  .ic { font-family: 'Material Symbols Rounded'; font-weight: normal; font-style: normal; line-height: 1; letter-spacing: normal; white-space: nowrap; font-feature-settings: 'liga'; }
  #screen { width: 800px; height: 480px; position: relative; overflow: hidden; box-sizing: border-box; font-family: Inter, sans-serif; color: #fff; background: #05140b; }
  svg.world { position: absolute; left: 0; top: 0; }
  .lg { position: absolute; isolation: isolate;
    background:
      radial-gradient(70% 55% at 22% 8%, rgba(255,255,255,.34) 0%, rgba(255,255,255,0) 70%),
      linear-gradient(160deg, rgba(255,255,255,.20) 0%, rgba(255,255,255,.05) 45%, rgba(255,255,255,.12) 100%);
    backdrop-filter: blur(14px) saturate(1.9) brightness(1.12);
    -webkit-backdrop-filter: blur(14px) saturate(1.9) brightness(1.12);
    box-shadow: 0 14px 28px rgba(0,0,0,.38), 0 2px 6px rgba(0,0,0,.25), inset 0 0 22px rgba(255,255,255,.10), inset 0 1.5px 1px rgba(255,255,255,.55), inset 0 -1.5px 1px rgba(255,255,255,.22); }
  .lg::before { content: ''; position: absolute; inset: 0; border-radius: inherit; padding: 1.6px; pointer-events: none;
    background: conic-gradient(from 215deg, rgba(255,255,255,.95), rgba(255,255,255,.08) 22%, rgba(255,255,255,.55) 50%, rgba(255,255,255,.06) 72%, rgba(255,255,255,.95));
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor;
    mask: linear-gradient(#000 0 0) content-box exclude, linear-gradient(#000 0 0); }
  .lg > * { position: relative; z-index: 1; }
  .tint { background:
      radial-gradient(70% 55% at 22% 8%, rgba(255,255,255,.55) 0%, rgba(255,255,255,0) 70%),
      linear-gradient(160deg, rgba(214,255,140,.95) 0%, rgba(150,225,100,.78) 100%) !important; }
  .warm { background:
      radial-gradient(70% 55% at 22% 8%, rgba(255,255,255,.45) 0%, rgba(255,255,255,0) 70%),
      linear-gradient(160deg, rgba(255,140,120,.85) 0%, rgba(235,70,55,.80) 100%) !important; }
  .center { display: grid; place-items: center; }
  .txt-shadow { text-shadow: 0 1px 5px rgba(0,0,0,.35); }
  /* when the page is made into the printer's wallpaper, only the panes stay */
  body.bake .txt, body.bake img, body.bake .slider { visibility: hidden; }
  body.bake-home .ic { visibility: hidden; }
  body.bake .pill, body.bake .badge { display: none; }
"""

WORLD = """
  <svg class="world" width="800" height="480" viewBox="0 0 800 480" aria-hidden="true">
    <defs>
      <radialGradient id="lime" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#c8f56e"/><stop offset="1" stop-color="#c8f56e" stop-opacity="0"/></radialGradient>
      <radialGradient id="leaf" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#3fcf5c"/><stop offset="1" stop-color="#3fcf5c" stop-opacity="0"/></radialGradient>
      <radialGradient id="teal" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#27d6b0"/><stop offset="1" stop-color="#27d6b0" stop-opacity="0"/></radialGradient>
      <radialGradient id="deep" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#0f5a2a"/><stop offset="1" stop-color="#0f5a2a" stop-opacity="0"/></radialGradient>
      <linearGradient id="ribbon" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#e6ffa8" stop-opacity="0"/><stop offset=".5" stop-color="#e6ffa8" stop-opacity=".95"/><stop offset="1" stop-color="#e6ffa8" stop-opacity="0"/></linearGradient>
    </defs>
    <rect width="800" height="480" fill="#06170c"/>
    <circle cx="130" cy="90" r="210" fill="url(#leaf)" opacity=".85"/>
    <circle cx="640" cy="60" r="190" fill="url(#lime)" opacity=".75"/>
    <circle cx="420" cy="300" r="230" fill="url(#deep)" opacity=".9"/>
    <circle cx="720" cy="400" r="190" fill="url(#teal)" opacity=".7"/>
    <circle cx="60" cy="420" r="170" fill="url(#lime)" opacity=".55"/>
    <circle cx="330" cy="40" r="120" fill="url(#teal)" opacity=".45"/>
    <path d="M-40 380 C 150 260, 300 330, 470 230 S 720 70, 860 110" fill="none" stroke="url(#ribbon)" stroke-width="14" opacity=".55"/>
    <path d="M-40 430 C 170 320, 320 380, 480 280 S 730 110, 860 150" fill="none" stroke="url(#ribbon)" stroke-width="4" opacity=".8"/>
    <path d="M-40 460 C 190 390, 340 430, 500 330 S 740 170, 860 200" fill="none" stroke="url(#ribbon)" stroke-width="2" opacity=".6"/>
  </svg>
"""


def box(rect, radius=None, extra=''):
    x, y, w, h = rect
    style = f'left:{x}px;top:{y}px;width:{w}px;height:{h}px'
    if radius is not None:
        style += f';border-radius:{radius}'
    return f'style="{style}{extra}"'


def pane(rect, radius, classes='', inner='', extra=''):
    px = f'{radius}px' if isinstance(radius, int) else radius
    return f'<div class="lg {classes}" {box(rect, px, extra)}>{inner}</div>'


def home(icons, text, with_tab=True, with_clock=True):
    """The home screen's panes, with their icons and/or text. While the quick settings panel is
    open the tab is left out (the panel is the tab, grown), and so is the clock (its time is live,
    so it can not be part of a picture); the icons stay, dimmed with the rest, because they are
    live parts that the picture of the open panel covers."""
    mock = text
    out = [pane(L.BAR, L.BAR_RADIUS)]
    for i, (name, _glyph, label) in enumerate(L.ORBS):
        icon = f'<span class="ic txt-shadow" style="font-size:29px" aria-label="{label}">{name}</span>' if icons else ''
        out.append(pane(L.orb_rect(i), L.ORB_SIZE // 2, ('warm center' if i == L.POWER_ORB else 'center'), icon))
    clock = ('<div class="txt" style="text-align:center;line-height:1.05"><div class="txt-shadow" style="font-size:22px;font-weight:700">19:09</div>'
             '<div style="font-size:11px;font-weight:500;opacity:.9">11/11/2026</div></div>') if mock else ''
    if with_clock:
        out.append(pane(L.CLOCK, L.CLOCK_RADIUS, 'center', clock))
    out.append(pane(L.BACK, L.BACK_RADIUS, 'center', '<span class="ic txt-shadow" style="font-size:30px">undo</span>' if icons else ''))
    tx, ty, tw, th = L.TAB
    tab = ''
    if mock:
        tab = (f'<div style="position:absolute;left:0;right:0;top:{10 - ty}px;display:flex;justify-content:center;align-items:center;gap:10px">'
               '<img src="boomslang-logo.svg" alt="" style="width:32px;height:32px;filter:drop-shadow(0 2px 4px rgba(0,0,0,.35))">'
               '<span class="txt-shadow" style="font-size:24px;font-weight:700">Boomslang</span></div>'
               f'<div style="position:absolute;left:0;right:0;top:{49 - ty}px;display:flex;justify-content:center;align-items:center;gap:10px">'
               '<span style="font-size:14px;opacity:.92">2611 6 Alpha</span>'
               '<span class="lg tint pill center" style="position:relative;display:inline-grid;height:26px;padding:0 16px;border-radius:13px;font-size:13px;font-weight:700;color:#0e3d14;box-shadow:0 4px 10px rgba(0,0,0,.3),inset 0 1px 1px rgba(255,255,255,.7)">Update</span></div>')
    if with_tab:
        out.append(pane(L.TAB, f'0 0 {L.TAB_RADIUS}px {L.TAB_RADIUS}px', '', tab))
    tray = ''
    if icons:
        names = ('wifi', 'swap_vert', 'notifications', 'print')
        tray = ''.join(f'<span class="ic" style="position:absolute;left:{x}px;top:{y}px;font-size:{L.TRAY_ICON_SIZE}px">{n}</span>'
                       for n, (x, y) in zip(names, L.TRAY_ICONS))
    if mock:
        tray += ('<span class="lg warm center badge" style="position:absolute;left:33px;top:47px;width:18px;height:18px;border-radius:50%;'
                 'font-size:11px;font-weight:700">1</span>')
    out.append(pane(L.TRAY, L.TRAY_RADIUS, '', tray))
    return '\n'.join(out)


def panel(mock):
    """The quick settings panel, with the home dimmed behind it."""
    out = [f'<div style="position:absolute;inset:0;background:rgba(0,0,0,{L.DIM / 255:.3f})"></div>']
    px, py, pw, ph = L.PANEL
    out.append(pane(L.PANEL, f'0 0 {L.PANEL_RADIUS}px {L.PANEL_RADIUS}px'))
    for rect in L.PANEL_CHIPS + L.PANEL_BUTTONS:
        out.append(pane(rect, L.PANEL_CHIP_RADIUS))
    hx, hy, hw, hh = L.PANEL_HANDLE
    out.append(f'<div style="position:absolute;left:{hx}px;top:{hy}px;width:{hw}px;height:{hh}px;border-radius:3px;background:rgba(255,255,255,.55)"></div>')
    if mock:
        tx, ty = L.PANEL_TITLE
        out.append(f'<div class="txt txt-shadow" style="position:absolute;left:{tx}px;top:{ty}px;font-size:20px;font-weight:700">Quick settings</div>')
        for (x, y), name in zip(L.PANEL_SLIDER_ICONS, ('brightness_low', 'brightness_high')):
            out.append(f'<span class="ic" style="position:absolute;left:{x}px;top:{y + 2}px;font-size:26px">{name}</span>')
        sx, sy, sw, sh = L.PANEL_SLIDER
        mid = sy + sh // 2
        out.append(f'<div class="slider" style="position:absolute;left:{sx}px;top:{mid - 5}px;width:{sw}px;height:10px;border-radius:5px;background:rgba(255,255,255,.30)">'
                   f'<div style="width:70%;height:100%;border-radius:5px;background:linear-gradient(90deg,#9be86a,#d8ff8c)"></div>'
                   f'<div style="position:absolute;left:calc(70% - 14px);top:-9px;width:28px;height:28px;border-radius:50%;background:radial-gradient(circle at 35% 25%,#fff,#e4efe0);box-shadow:0 3px 8px rgba(0,0,0,.4)"></div></div>')
        chips = (('volume_up', 'Sounds', True), ('system_update', 'Auto update', True))
        buttons = (('qr_code_2', 'Web portal'), ('settings', 'Settings'))
        for rect, (icon, text, on) in zip(L.PANEL_CHIPS, chips):
            x, y, w, h = rect
            tint = f'<div class="lg tint" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;border-radius:{L.PANEL_CHIP_RADIUS}px;opacity:.55;box-shadow:none"></div>' if on else ''
            out.append(tint + _row(rect, icon, text))
        for rect, (icon, text) in zip(L.PANEL_BUTTONS, buttons):
            out.append(_row(rect, icon, text))
    return '\n'.join(out)


def _row(rect, icon, text):
    x, y, w, h = rect
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;display:flex;align-items:center;gap:14px;padding-left:22px;box-sizing:border-box">'
            f'<span class="ic txt-shadow" style="font-size:26px">{icon}</span><span class="txt txt-shadow" style="font-size:16px;font-weight:600">{text}</span></div>')


def page(mode):
    bake = mode.startswith('bake')
    fonts = '' if mode == 'bake-home' else ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
                             '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&amp;family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,500,1,0" rel="stylesheet">')
    opened = mode in ('panel', 'bake-panel')
    # a picture of the home keeps no icons (they are live); a picture of the open panel keeps the
    # home's icons (dimmed), because the picture covers the live ones
    body = home(icons=(not bake) or opened, text=not bake, with_tab=not opened, with_clock=not opened or not bake)
    if opened:
        body += '\n' + panel(not bake)
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>Liquid Plastic UI</title>\n{fonts}\n<style>{CSS}</style>\n</head>\n'
            f'<body class="{("bake " + mode) if bake else ""}">\n<div id="screen">\n{WORLD}\n{body}\n</div>\n</body>\n</html>\n')


def render(html_path, png_path):
    profile = tempfile.mkdtemp(prefix='liquid-firefox-')
    subprocess.run(['firefox', '--headless', '--no-remote', '--profile', profile, '--window-size=800,480',
                    '--screenshot', str(png_path), f'file://{html_path}'], check=True, capture_output=True, timeout=180)
    from PIL import Image
    Image.open(png_path).convert('RGB').crop((0, 0, 800, 480)).save(png_path, optimize=True)


def main():
    work = Path(tempfile.mkdtemp(prefix='liquid-'))
    for mode, name in (('home', 'Liquid'), ('panel', 'LiquidPanel')):
        html_path = MOCKUPS / 'html' / f'{name}.html'
        html_path.write_text(page(mode), encoding='utf-8')
        render(html_path, MOCKUPS / 'png' / f'{name}.png')
        print(f'mockup {name}: png/{name}.png')
    for mode, name in (('bake-home', 'liquid-home'), ('bake-panel', 'liquid-panel')):
        html_path = work / f'{name}.html'
        html_path.write_text(page(mode), encoding='utf-8')
        png_path = work / f'{name}.png'
        render(html_path, png_path)
        target = UI / 'assets' / f'{name}.bin'
        print(f'{target.relative_to(HERE.parent)}: {convert(png_path, target)} bytes')


if __name__ == '__main__':
    main()
