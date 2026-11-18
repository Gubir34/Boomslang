"""The live parts of the Liquid Plastic look: buttons, toggles, a slider and a drop-down panel.

The glass itself is not drawn here. It is part of the wallpaper pictures
(branding/make-liquid.py), because LVGL can't blur what is behind a widget.
What this builds sits on top of the panes, in the places liquid_layout.py
names:

  touch()      a see-through button over a pane. Pressing it lights the pane up.
  Toggle       a pane that can be on or off (on = tinted)
  slider()     a track, a filled part and a round knob
  DropPanel    a layer that opens over the home screen: a picture of the open
               panel, the controls on it, and a tap outside it closes it

The LVGL module and the printer's own widget helpers are passed in, so this
file can be tested on a PC with stand-in widgets.

Also the brightness of the screen, which the quick settings panel sets.
"""
import os

from liquid_layout import CHIP_ICON_X, CHIP_ICON_Y, CHIP_TEXT_X, CHIP_TEXT_Y, SCREEN

WHITE = (255, 255, 255)
LIME = (170, 235, 110)
LIME_LIGHT = (216, 255, 140)

BACKLIGHT = '/sys/class/backlight/backlight'
MIN_BRIGHTNESS = 15          # percent. The screen is never set darker: black can't be undone by touch.


# --- screen brightness --------------------------------------------------------------

def _max_brightness(base):
    """The backlight's highest value, 255 when it can't be read (or reads 0)."""
    try:
        with open(os.path.join(base, 'max_brightness')) as f:
            return int(f.read().strip()) or 255
    except (OSError, ValueError):
        return 255


def read_brightness(base=None):
    """Brightness of the screen in percent (MIN_BRIGHTNESS..100), or None when it can't be read."""
    base = base or BACKLIGHT
    try:
        with open(os.path.join(base, 'brightness')) as f:
            value = int(f.read().strip())
    except (OSError, ValueError):
        return None
    return max(MIN_BRIGHTNESS, min(100, round(value * 100 / _max_brightness(base))))


def set_brightness(percent, base=None):
    """Set the brightness of the screen. Returns the percent that was set (never below MIN_BRIGHTNESS)."""
    base = base or BACKLIGHT
    percent = max(MIN_BRIGHTNESS, min(100, int(round(percent))))
    with open(os.path.join(base, 'brightness'), 'w') as f:
        f.write(str(round(_max_brightness(base) * percent / 100)))
    return percent


def auto_update_on(value):
    """Whether the auto_update setting of Boomslang Web means "install updates by itself"."""
    return (value or '').strip().lower() != 'off'


def auto_update_value(on, previous):
    """The auto_update setting to write when the toggle is switched.

    Off is 'off'. On goes back to the choice there was before it was turned
    off (a channel picked in Settings, like 'release'), and to 'auto' only
    when there was none, so the toggle never changes which channel is followed.
    """
    if not on:
        return 'off'
    previous = (previous or '').strip()
    return previous if previous and previous.lower() != 'off' else 'auto'


# --- widgets ---------------------------------------------------------------------------

class Glass:
    def __init__(self, lv, lvr):
        self.lv = lv
        self.lvr = lvr

    def color(self, rgb):
        return self.lv.color_make(*rgb)

    def clear(self, widget, radius=0):
        """No background, border, padding or scrolling: a see-through container."""
        lv = self.lv
        widget.set_style_bg_opa(lv.OPA.TRANSP, lv.STATE.DEFAULT)
        widget.set_style_border_width(0, lv.STATE.DEFAULT)
        widget.set_style_pad_all(0, lv.STATE.DEFAULT)
        widget.set_style_radius(radius, lv.STATE.DEFAULT)
        widget.set_style_shadow_width(0, lv.STATE.DEFAULT)
        widget.remove_flag(lv.OBJ_FLAG.SCROLLABLE)
        return widget

    def container(self, parent, rect, radius=0, clickable=True):
        """A see-through object of the rectangle's size and place.

        Clickable (the default) it takes the taps that fall on it, which keeps them from
        reaching what is behind it. Not clickable, taps go through to what is behind.
        """
        widget = self.clear(self.lv.obj(parent), radius)
        x, y, w, h = rect
        widget.set_size(w, h)
        widget.set_pos(x, y)
        if not clickable:
            widget.remove_flag(self.lv.OBJ_FLAG.CLICKABLE)
        return widget

    def touch(self, parent, rect, radius, callback=None, glyph=None):
        """A see-through button over a pane. Pressing it lights the pane up; a glyph is drawn white in it."""
        lv = self.lv
        button = (self.lvr.button_icon if glyph else self.lvr.button)(parent)
        x, y, w, h = rect
        button.set_size(w, h)
        button.set_pos(x, y)
        self.clear(button, radius)
        button.set_style_bg_color(self.color(WHITE), lv.STATE.PRESSED)
        button.set_style_bg_opa(70, lv.STATE.PRESSED)
        button.set_style_text_color(self.color(WHITE), lv.STATE.DEFAULT)
        if glyph:
            button.set_text(glyph)
        else:
            button.set_icon('')
            button.set_text('')
        if callback:
            button.add_event_cb(lambda e: callback(), lv.EVENT_CODE.CLICKED, None)
        return button

    def label(self, parent, text, x, y, glyph=False):
        """White text (or an icon, with glyph=True) at a place."""
        lv, lvr = self.lv, self.lvr
        label = lv.label(parent)
        label.set_text(text)
        if glyph:
            label.set_style_text_font(lvr.get_font_icon_small(), lv.STATE.DEFAULT)
        label.set_style_text_color(self.color(WHITE), lv.STATE.DEFAULT)
        label.set_pos(x, y)
        return label

    def slider(self, parent, rect, minimum, maximum, value, on_change=None, on_release=None):
        """A slider in the rectangle: a thin track, a filled part and a round knob."""
        lv = self.lv
        part = lambda p: p.value  # noqa: E731  (an int: a part and a state are combined as one number)
        x, y, w, h = rect
        track = 10
        slider = lv.slider(parent)
        slider.set_size(w, track)
        slider.set_pos(x, y + (h - track) // 2)
        slider.set_range(minimum, maximum)
        slider.set_value(value, 0)

        main, indicator, knob = part(lv.PART.MAIN), part(lv.PART.INDICATOR), part(lv.PART.KNOB)
        slider.set_style_bg_color(self.color(WHITE), main)
        slider.set_style_bg_opa(80, main)
        slider.set_style_radius(track // 2, main)
        slider.set_style_pad_all(0, main)
        slider.set_style_border_width(0, main)
        slider.set_style_shadow_width(0, main)

        slider.set_style_bg_color(self.color(LIME_LIGHT), indicator)
        slider.set_style_bg_grad_color(self.color(LIME), indicator)
        slider.set_style_bg_grad_dir(lv.GRAD_DIR.HOR, indicator)
        slider.set_style_bg_opa(lv.OPA.COVER, indicator)
        slider.set_style_radius(track // 2, indicator)

        slider.set_style_bg_color(self.color(WHITE), knob)
        slider.set_style_bg_opa(lv.OPA.COVER, knob)
        slider.set_style_radius(1000, knob)
        slider.set_style_pad_all(9, knob)                  # the knob is as big as the track plus this on each side
        slider.set_style_border_width(0, knob)
        slider.set_style_shadow_width(10, knob)
        slider.set_style_shadow_color(lv.color_black(), knob)
        slider.set_style_shadow_opa(110, knob)

        if on_change:
            slider.add_event_cb(lambda e: on_change(slider.get_value()), lv.EVENT_CODE.VALUE_CHANGED, None)
        if on_release:
            slider.add_event_cb(lambda e: on_release(slider.get_value()), lv.EVENT_CODE.RELEASED, None)
        return slider


class Toggle:
    """A pane that is either on (tinted green) or off, with an icon and a name."""

    def __init__(self, glass, parent, rect, radius, glyph, text, on=False, on_change=None):
        lv = glass.lv
        x, y, w, h = rect
        self.glass, self.on, self.on_change = glass, bool(on), on_change
        # the tint comes first, so that the icon, the text and the touch area are above it
        self.tint = glass.container(parent, rect, radius, clickable=False)   # only the touch area on top takes taps
        self.tint.set_style_bg_color(glass.color(LIME), lv.STATE.DEFAULT)
        glass.label(parent, glyph, x + CHIP_ICON_X, y + CHIP_ICON_Y, glyph=True)
        glass.label(parent, text, x + CHIP_TEXT_X, y + CHIP_TEXT_Y)
        glass.touch(parent, rect, radius, self.toggle)
        self.set(self.on)

    def set(self, on):
        """Show on or off (without calling on_change)."""
        self.on = bool(on)
        self.tint.set_style_bg_opa(110 if self.on else self.glass.lv.OPA.TRANSP, self.glass.lv.STATE.DEFAULT)

    def toggle(self):
        self.set(not self.on)
        if self.on_change:
            self.on_change(self.on)


class DropPanel:
    """A layer over the home screen: the picture of the open panel, and what is put on it.

    Tapping outside the panel, or its handle, closes it. Tapping the panel itself
    does nothing: the controls on it have their own taps.
    """

    def __init__(self, glass, parent, image_path, panel_rect, close_rect, on_open=None):
        lv, lvr = glass.lv, glass.lvr
        self.glass, self.on_open, self.open = glass, on_open, False
        self.layer = glass.container(parent, (0, 0) + SCREEN)
        self.layer.add_flag(lv.OBJ_FLAG.HIDDEN)
        self.layer.add_event_cb(lambda e: self.hide(), lv.EVENT_CODE.CLICKED, None)
        picture = lvr.image(self.layer)
        picture.set_src(image_path)
        picture.set_pos(0, 0)
        picture.remove_flag(lv.OBJ_FLAG.CLICKABLE)
        # a tap on the panel must not reach the layer behind it (that would close it)
        glass.container(self.layer, panel_rect)
        glass.touch(self.layer, close_rect, 20, self.hide)

    def show(self):
        if self.on_open:
            self.on_open()
        self.layer.remove_flag(self.glass.lv.OBJ_FLAG.HIDDEN)
        self.layer.move_foreground()
        self.open = True

    def hide(self):
        self.layer.add_flag(self.glass.lv.OBJ_FLAG.HIDDEN)
        self.open = False
