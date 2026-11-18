"""Where everything is on the Liquid Plastic screens (800x480, in real pixels).

One place for the numbers, used twice:

  - branding/make-liquid.py draws the glass panes into the wallpaper images
    with them, and the mockups
  - rinkhals-ui.py puts the live parts (icons, text, touch areas, the slider)
    on top of the same places

If a number changes here, run branding/make-liquid.py again and the picture
and the live parts move together. tests/test_liquid_layout.py checks that
nothing is off the screen or overlapping where it should not.

Rectangles are (x, y, width, height). Radii are for the glass pane.
"""
SCREEN = (800, 480)

# --- Home --------------------------------------------------------------------------
BAR = (8, 400, 784, 72)                  # the taskbar capsule: 8 px from the bottom and the sides
BAR_RADIUS = 36
ORB_SIZE = 58
ORB_Y = 407                              # centred in the bar: 400 + (72 - 58) / 2
ORB_X = (16, 88, 160, 232, 304, 376)     # pitch 72
ORBS = (                                 # (icon name in the mockup font, glyph in the printer's font, what it is)
    ('settings', '', 'Settings'),
    ('local_mall', '', 'App Store'),
    ('widgets', '', 'Apps'),
    ('qr_code_2', '', 'Web portal'),
    ('search', '', 'LemSearch Lite'),
    ('power_settings_new', '', 'Power'),
)
POWER_ORB = 5                            # the one tinted red
CLOCK = (688, 407, 96, 58)
CLOCK_RADIUS = 29
BACK = (14, 14, 60, 60)
BACK_RADIUS = 30
TAB = (236, -34, 328, 124)               # hangs from the top edge: 0..90 is on the screen
TAB_RADIUS = 44
TAB_TOUCH = (236, -54, 328, 144)         # tapping it opens the quick settings panel (its pressed shade has the pane's shape: the top corners are above the screen)
TRAY = (696, 14, 90, 90)
TRAY_RADIUS = 34
TRAY_ICONS = ((15, 15), (51, 15), (15, 51), (51, 51))   # inside the tray: equal margins all round
TRAY_ICON_SIZE = 24

# --- Quick settings: the panel that drops down from the tab -------------------------------
PANEL = (110, -30, 580, 380)             # on the screen: y 0..350
PANEL_RADIUS = 44
PANEL_VISIBLE_BOTTOM = 350
PANEL_TITLE = (140, 22)                  # top left of the title text
CHIP_PAD_LEFT, CHIP_GAP = 22, 14         # inside a chip or a button: the icon from the left edge, then the
                                         # text; both centred top to bottom (fonts grow with the screen's dpi)
TAB_TITLE_ROW = (236, 10, 328, 32)       # logo and name, centred in this row
TAB_VERSION_ROW = (236, 49, 328, 26)     # version and the Update pill
PANEL_SLIDER = (196, 92, 388, 28)        # the brightness slider (the track is drawn live). The knob
                                         # reaches 14 px past each end, so it stops short of the bright sun
PANEL_SLIDER_ICONS = ((138, 92), (616, 92))   # dim sun, bright sun
PANEL_CHIPS = ((130, 146, 260, 58), (410, 146, 260, 58))      # two toggles
PANEL_BUTTONS = ((130, 220, 260, 58), (410, 220, 260, 58))    # two plain buttons
PANEL_CHIP_RADIUS = 29
PANEL_CLOSE = (350, 304, 100, 40)        # the handle at the bottom: tap to close
PANEL_HANDLE = (374, 322, 52, 6)

DIM = 90                                 # how dark the home gets behind the open panel (0..255)


def inside(rect, screen=SCREEN):
    x, y, w, h = rect
    return x >= 0 and y >= 0 and x + w <= screen[0] and y + h <= screen[1]


def contains(outer, inner):
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return ix >= ox and iy >= oy and ix + iw <= ox + ow and iy + ih <= oy + oh


def orb_rect(index):
    return (ORB_X[index], ORB_Y, ORB_SIZE, ORB_SIZE)
