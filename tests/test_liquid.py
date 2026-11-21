"""Liquid Plastic: the layout numbers, the widgets, the home screen, the quick settings panel.

As in test_aero_home.py the methods are cut out of rinkhals-ui.py with ast and run against
stand-in widgets. That checks what is built, where, and what a tap does; it can not check
how it looks. The pictures are checked against the layout so that the two can't drift apart.
"""
import ast
import logging
import os
import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

UI = Path(__file__).resolve().parents[1] / 'files/3-rinkhals/opt/rinkhals/ui'
sys.path.insert(0, str(UI))
import home_tools  # noqa: E402
import liquid_layout as L  # noqa: E402
import liquid_ui  # noqa: E402

SOURCE = (UI / 'rinkhals-ui.py').read_text(encoding='utf-8')
APP = next(n for n in ast.parse(SOURCE).body if isinstance(n, ast.ClassDef) and n.name == 'RinkhalsUiApp')
METHODS = ('layout_liquid_home', 'layout_liquid_panel', 'liquid_open_panel', 'liquid_panel_refresh', 'liquid_brightness',
           'liquid_toggle_sounds', 'liquid_toggle_updates', 'liquid_read_updates', 'home_clear', 'home_glyph', 'home_tick_clock',
           'home_refresh', 'home_ink', 'home_ink_off', 'print_entry', 'home_show_update', 'home_show_link', 'home_power', 'aero_light')
ATTRIBUTES = ('MUTE_SOUNDS_FILE', 'WEB_APP')


def load_class(lv, lvr, **extra):
    wanted = []
    for node in APP.body:
        if isinstance(node, ast.FunctionDef) and node.name in METHODS:
            wanted.append(ast.get_source_segment(SOURCE, node))
        elif isinstance(node, ast.Assign) and (getattr(node.targets[0], 'id', '') in ATTRIBUTES or
                                               getattr(node.targets[0], 'id', '').startswith('AERO_')):
            wanted.append(ast.get_source_segment(SOURCE, node))
    code = 'class LiquidApp:\n' + '\n'.join('    ' + line for chunk in wanted for line in chunk.split('\n')) + '\n'
    namespace = dict({
        'lv': lv, 'lvr': lvr, 'os': os, 'time': time, 'logging': logging, 'liquid_layout': L, 'liquid_ui': liquid_ui,
        'ASSETS_PATH': '/assets', 'RINKHALS_VERSION': '2611-6-alpha', 'display_version': lambda v: '2611 6 Alpha',
        'ellipsis': lambda t, n: t, 'printer_ip': lambda: '192.168.1.5', 'run_async': lambda fn: fn(),
        'get_app_property': mock.MagicMock(return_value='auto'), 'set_app_property': mock.MagicMock(),
    }, **extra)
    exec(compile(code, 'rinkhals-ui-liquid', 'exec'), namespace)
    return namespace['LiquidApp'], namespace


def read_bin(path):
    """An LVGL RGB565 image file -> (width, height, function (x, y) -> (r, g, b))."""
    data = Path(path).read_bytes()
    magic, cf, flags, w, h, stride, _ = struct.unpack('<BBHHHHH', data[:12])
    assert (magic, cf) == (0x19, 0x12), 'not an RGB565 LVGL image'
    assert len(data) == 12 + stride * h

    def pixel(x, y):
        v, = struct.unpack_from('<H', data, 12 + y * stride + x * 2)
        return (((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)
    return w, h, pixel


def average(pixel, rect):
    x, y, w, h = rect
    total = [0, 0, 0]
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            for i, c in enumerate(pixel(xx, yy)):
                total[i] += c
    n = w * h
    return tuple(t / n for t in total)


class LayoutTests(unittest.TestCase):
    def test_everything_that_is_drawn_is_on_the_screen(self):
        for name in ('BAR', 'CLOCK', 'BACK', 'TRAY', 'TAB_TITLE_ROW', 'TAB_VERSION_ROW', 'PANEL_SLIDER', 'PANEL_CLOSE', 'PANEL_HANDLE'):
            self.assertTrue(L.inside(getattr(L, name)), name)
        for rect in L.PANEL_CHIPS + L.PANEL_BUTTONS + tuple(L.orb_rect(i) for i in range(6)):
            self.assertTrue(L.inside(rect), rect)
        # the tab and the panel hang from the top edge: only the part below y=0 is on the screen
        for name in ('TAB', 'PANEL'):
            x, y, w, h = getattr(L, name)
            self.assertLess(y, 0)
            self.assertTrue(x >= 0 and x + w <= L.SCREEN[0], name)
        self.assertEqual(L.PANEL[1] + L.PANEL[3], L.PANEL_VISIBLE_BOTTOM)
        self.assertEqual(L.TAB[1] + L.TAB[3], 90)

    def test_the_taskbar_parts_are_centred_in_it_and_evenly_spaced(self):
        bar_centre = L.BAR[1] + L.BAR[3] / 2
        for rect in [L.orb_rect(i) for i in range(6)] + [L.CLOCK]:
            self.assertEqual(rect[1] + rect[3] / 2, bar_centre, rect)
            self.assertTrue(L.contains(L.BAR, rect), rect)
        gaps = {L.ORB_X[i + 1] - (L.ORB_X[i] + L.ORB_SIZE) for i in range(5)}
        self.assertEqual(len(gaps), 1, 'the orbs are not evenly spaced')
        # the same margin to the bar's edge above, below and at the left of the first orb
        self.assertEqual(L.ORB_Y - L.BAR[1], L.BAR[1] + L.BAR[3] - (L.ORB_Y + L.ORB_SIZE))
        self.assertEqual(L.BAR[0] + L.BAR[2] - (L.CLOCK[0] + L.CLOCK[2]), L.ORB_X[0] - L.BAR[0])
        # the bar is as far from the bottom edge as from the sides
        self.assertEqual(L.SCREEN[1] - (L.BAR[1] + L.BAR[3]), L.BAR[0])

    def test_the_tray_icons_have_equal_margins_all_round(self):
        size = L.TRAY_ICON_SIZE
        xs = sorted({x for x, _ in L.TRAY_ICONS})
        ys = sorted({y for _, y in L.TRAY_ICONS})
        for axis in (xs, ys):
            self.assertEqual(axis[0], L.TRAY[2] - (axis[1] + size), axis)

    def test_the_panel_holds_its_controls_without_overlaps(self):
        visible = (L.PANEL[0], 0, L.PANEL[2], L.PANEL_VISIBLE_BOTTOM)
        controls = [L.PANEL_SLIDER, L.PANEL_CLOSE] + list(L.PANEL_CHIPS) + list(L.PANEL_BUTTONS)
        for rect in controls:
            self.assertTrue(L.contains(visible, rect), rect)
        for i, a in enumerate(controls):
            for b in controls[i + 1:]:
                overlap = a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
                self.assertFalse(overlap, (a, b))
        # controls are thumb-sized
        for rect in list(L.PANEL_CHIPS) + list(L.PANEL_BUTTONS):
            self.assertGreaterEqual(rect[3], 48)

    def test_every_orb_has_a_glyph_and_the_power_orb_is_last(self):
        self.assertEqual(len(L.ORBS), len(L.ORB_X))
        self.assertEqual(L.ORBS[L.POWER_ORB][2], 'Power')
        self.assertEqual(len({glyph for _, glyph, _ in L.ORBS}), 6)


class PicturesMatchTheLayout(unittest.TestCase):
    """The panes are drawn into the pictures. If the layout moves and the pictures are not made
    again, the live parts end up beside their panes: this is what catches it."""

    SUFFIXES = ('', '-light')        # dark and light mode each have their own pictures

    def test_the_pictures_have_the_screens_size_and_format(self):
        for name in ('liquid-home', 'liquid-panel', 'liquid-home-light', 'liquid-panel-light'):
            w, h, _ = read_bin(UI / 'assets' / f'{name}.bin')
            self.assertEqual((w, h), L.SCREEN)

    def edge_x(self, pixel, x, y, search_from, search_to, light=False):
        """Where a pane's left edge is in the picture: the first place along a row where it gets much
        brighter than what is left of it. On the light wallpaper the white panes are hardly brighter
        than the mint behind them, but their green rim is darker than both. Their soft shadow starts
        darkening a pixel or two early, so there the edge may be up to 2 px off."""
        base = sum(average(pixel, (search_from - 4, y - 4, 4, 8)))
        for xx in range(search_from, search_to):
            value = sum(pixel(xx, y))
            if (value < base - 25) if light else (value > base + 60):
                return xx
        return None

    def test_every_pane_of_the_home_is_in_its_place(self):
        for suffix in self.SUFFIXES:
            with self.subTest(suffix or 'dark'):
                self.panes_in_place(suffix)

    def panes_in_place(self, suffix):
        _, _, pixel = read_bin(UI / f'assets/liquid-home{suffix}.bin')
        light = bool(suffix)
        near = 2 if light else 1
        # The edges of the panes in the picture are where the layout says (to a pixel or two),
        # so the live icons and touch areas sit on their panes
        for i in range(1, 6):
            x, y, w, h = L.orb_rect(i)
            found = self.edge_x(pixel, x, y + h // 2, x - 6, x + 12, light)
            self.assertIsNotNone(found, f'orb {i}: no edge found')
            self.assertLessEqual(abs(found - x), near, f'orb {i}: layout x {x}, picture x {found}')
        x, y, w, h = L.BACK
        self.assertLessEqual(abs(self.edge_x(pixel, x, y + h // 2, x - 6, x + 12, light) - x), near, 'the back button')
        x, y, w, h = L.CLOCK
        self.assertLessEqual(abs(self.edge_x(pixel, x, y + h // 2, x - 6, x + 12, light) - x), near, 'the clock')
        # the taskbar's top edge: the row near it that is most brighter than the one above (its lit
        # rim), in a place with no orb
        column = 560
        rim = max(range(L.BAR[1] - 8, L.BAR[1] + 8), key=lambda yy: sum(pixel(column, yy)) - sum(pixel(column, yy - 1)))
        self.assertLessEqual(abs(rim - L.BAR[1]), 1, f'the bar: layout y {L.BAR[1]}, picture y {rim}')
        # the power orb is red
        x, y, w, h = L.orb_rect(L.POWER_ORB)
        r, g, b = average(pixel, (x + w // 2 - 6, y + h // 2 - 6, 12, 12))
        self.assertGreater(r, g + 30)

    def test_the_open_panel_picture_has_the_panel_and_its_chips(self):
        for suffix in self.SUFFIXES:
            with self.subTest(suffix or 'dark'):
                self.panel_picture(suffix)

    def panel_picture(self, suffix):
        _, _, home = read_bin(UI / f'assets/liquid-home{suffix}.bin')
        _, _, panel = read_bin(UI / f'assets/liquid-panel{suffix}.bin')
        # the panel darkens the home: a place in the middle of the screen is darker than in the home picture
        middle = (60, 200, 30, 30)
        self.assertLess(sum(average(panel, middle)), sum(average(home, middle)))
        # a chip is lighter than the panel between the chips
        x, y, w, h = L.PANEL_CHIPS[0]
        between = (x + w + 4, y + 10, 12, 12)
        self.assertGreater(sum(average(panel, (x + 40, y + 10, 12, 12))) - sum(average(panel, between)), 6)


class BrightnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def files(self, value, maximum=None):
        Path(self.base, 'brightness').write_text(f'{value}\n')
        if maximum is not None:
            Path(self.base, 'max_brightness').write_text(f'{maximum}\n')

    def test_reading_is_a_percent_of_the_maximum(self):
        self.files(255, 255)
        self.assertEqual(liquid_ui.read_brightness(self.base), 100)
        self.files(128, 255)
        self.assertEqual(liquid_ui.read_brightness(self.base), 50)
        self.files(50, 100)
        self.assertEqual(liquid_ui.read_brightness(self.base), 50)
        self.files(200)                                                   # no max_brightness: 255
        os.remove(os.path.join(self.base, 'max_brightness'))
        self.assertEqual(liquid_ui.read_brightness(self.base), 78)

    def test_it_is_never_reported_or_set_darker_than_the_floor(self):
        self.files(0, 255)
        self.assertEqual(liquid_ui.read_brightness(self.base), liquid_ui.MIN_BRIGHTNESS)
        for asked in (0, 1, -50):
            self.assertEqual(liquid_ui.set_brightness(asked, self.base), liquid_ui.MIN_BRIGHTNESS)
            self.assertGreaterEqual(int(Path(self.base, 'brightness').read_text()), 255 * liquid_ui.MIN_BRIGHTNESS // 100 - 1)

    def test_setting_writes_the_value_for_the_screens_maximum(self):
        self.files(255, 255)
        self.assertEqual(liquid_ui.set_brightness(50, self.base), 50)
        self.assertEqual(Path(self.base, 'brightness').read_text(), '128')
        self.files(10, 100)
        liquid_ui.set_brightness(70, self.base)
        self.assertEqual(Path(self.base, 'brightness').read_text(), '70')
        self.assertEqual(liquid_ui.set_brightness(500, self.base), 100)   # no brighter than the maximum
        self.assertEqual(Path(self.base, 'brightness').read_text(), '100')

    def test_a_screen_without_a_backlight_is_not_an_error_to_read(self):
        self.assertIsNone(liquid_ui.read_brightness(os.path.join(self.base, 'nothing')))
        Path(self.base, 'brightness').write_text('garbage')
        self.assertIsNone(liquid_ui.read_brightness(self.base))
        with self.assertRaises(OSError):
            liquid_ui.set_brightness(50, os.path.join(self.base, 'nothing'))

    def test_the_auto_update_setting(self):
        for value, on in (('auto', True), ('release', True), ('alpha', True), ('', True), (None, True), ('off', False), (' OFF ', False)):
            self.assertEqual(liquid_ui.auto_update_on(value), on, value)


class WidgetTests(unittest.TestCase):
    def setUp(self):
        self.lv, self.lvr = mock.MagicMock(name='lv'), mock.MagicMock(name='lvr')
        self.glass = liquid_ui.Glass(self.lv, self.lvr)
        self.parent = mock.MagicMock(name='parent')

    def handlers(self, widget):
        return {call.args[1]: call.args[0] for call in widget.add_event_cb.call_args_list}

    def test_a_touch_area_is_see_through_and_lights_the_pane_when_pressed(self):
        taps = []
        button = self.glass.touch(self.parent, (16, 407, 58, 58), 29, lambda: taps.append(1), glyph='X')
        button.set_size.assert_called_with(58, 58)
        button.set_pos.assert_called_with(16, 407)
        button.set_style_bg_opa.assert_any_call(self.lv.OPA.TRANSP, self.lv.STATE.DEFAULT)
        button.set_style_bg_opa.assert_any_call(70, self.lv.STATE.PRESSED)
        button.set_text.assert_called_with('X')
        self.handlers(button)[self.lv.EVENT_CODE.CLICKED](None)
        self.assertEqual(taps, [1])

    def test_a_touch_area_without_a_glyph_has_no_text_or_icon(self):
        button = self.glass.touch(self.parent, (0, 0, 10, 10), 5, None)
        self.lvr.button.assert_called_once()
        button.set_text.assert_called_with('')
        button.set_icon.assert_called_with('')
        button.add_event_cb.assert_not_called()

    def test_the_slider_has_its_range_value_and_reports_changes(self):
        changes, releases = [], []
        slider = self.glass.slider(self.parent, L.PANEL_SLIDER, 15, 100, 60, changes.append, releases.append)
        slider.set_range.assert_called_with(15, 100)
        slider.set_value.assert_called_with(60, 0)
        slider.set_size.assert_called_with(L.PANEL_SLIDER[2], 10)
        # centred in its rectangle
        x, y, w, h = L.PANEL_SLIDER
        slider.set_pos.assert_called_with(x, y + (h - 10) // 2)
        slider.get_value.return_value = 42
        handlers = self.handlers(slider)
        handlers[self.lv.EVENT_CODE.VALUE_CHANGED](None)
        handlers[self.lv.EVENT_CODE.RELEASED](None)
        self.assertEqual((changes, releases), ([42], [42]))
        # the three parts are styled with their part number (an int), not a state
        parts = {call.args[1] for call in slider.set_style_bg_color.call_args_list}
        self.assertEqual(parts, {liquid_ui.PART_MAIN, liquid_ui.PART_INDICATOR, liquid_ui.PART_KNOB})

    def test_a_toggle_flips_and_tells_the_caller(self):
        seen = []
        toggle = liquid_ui.Toggle(self.glass, self.parent, L.PANEL_CHIPS[0], L.PANEL_CHIP_RADIUS, 'G', 'Sounds', True, seen.append)
        self.assertTrue(toggle.on)
        toggle.tint.set_style_bg_opa.assert_called_with(110, self.lv.STATE.DEFAULT)
        # the tap is the touch area's
        self.handlers(self.lvr.button.return_value)[self.lv.EVENT_CODE.CLICKED](None)
        self.assertEqual((toggle.on, seen), (False, [False]))
        toggle.tint.set_style_bg_opa.assert_called_with(self.lv.OPA.TRANSP, self.lv.STATE.DEFAULT)
        toggle.set(True)                                  # showing a state is not a change
        self.assertEqual((toggle.on, seen), (True, [False]))

    def test_the_drop_panel_opens_closes_and_asks_for_fresh_values_when_opened(self):
        opened = []
        panel = liquid_ui.DropPanel(self.glass, self.parent, '/assets/panel.bin', (110, 0, 580, 350), L.PANEL_CLOSE, lambda: opened.append(1))
        layer = panel.layer
        layer.add_flag.assert_called_with(self.lv.OBJ_FLAG.HIDDEN)               # closed to begin with
        self.assertFalse(panel.open)
        panel.show()
        self.assertEqual((panel.open, opened), (True, [1]))
        layer.remove_flag.assert_called_with(self.lv.OBJ_FLAG.HIDDEN)
        layer.move_foreground.assert_called_once()
        panel.hide()
        self.assertFalse(panel.open)
        # a tap on the layer outside the panel closes it
        panel.show()
        self.handlers(layer)[self.lv.EVENT_CODE.CLICKED](None)
        self.assertFalse(panel.open)
        self.lvr.image.return_value.set_src.assert_called_with('/assets/panel.bin')


class LiquidHomeTests(unittest.TestCase):
    def setUp(self):
        self.lv, self.lvr = mock.MagicMock(name='lv'), mock.MagicMock(name='lvr')
        self.lvr.light.return_value = getattr(self, 'LIGHT', False)
        self.App, self.names = load_class(self.lv, self.lvr)
        self.tmp = tempfile.TemporaryDirectory()
        self.App.MUTE_SOUNDS_FILE = os.path.join(self.tmp.name, 'mute-sounds')
        self.app = self.App()
        self.app.screen_main = mock.MagicMock(name='screen_main')
        self.app.screen_current = None
        self.app.screen_composition = None
        self.app.screen_advanced, self.app.screen_store = object(), object()
        self.app.screen_apps, self.app.screen_ota = object(), object()
        self.app.show_screen = mock.MagicMock()
        self.app.show_text_dialog = mock.MagicMock()
        self.app.show_qr_dialog = mock.MagicMock()
        self.app.show_selection_dialog = mock.MagicMock()
        self.app.browser_show = mock.MagicMock()
        self.app.quit = mock.MagicMock()
        self.app.modal_selection = object()
        self.app.layout_liquid_home()

    def tearDown(self):
        self.tmp.cleanup()

    def clicks(self, widget):
        return [c.args[0] for c in widget.add_event_cb.call_args_list]

    def test_the_wallpaper_is_the_picture_with_the_panes_in_it(self):
        sources = [c.args[0] for c in self.lvr.image.return_value.set_src.call_args_list]
        self.assertEqual(sources[0], '/assets/liquid-home.bin')
        self.assertIn('/assets/liquid-panel.bin', sources)

    def test_the_panes_ink_is_white_on_the_dark_glass(self):
        self.assertEqual(self.app.liquid_glass.ink, liquid_ui.WHITE)
        self.assertFalse(self.app.liquid_glass.light)

    def test_the_touch_areas_are_where_the_panes_are(self):
        positions = [c.args for c in self.lvr.button_icon.return_value.set_pos.call_args_list]
        self.assertEqual(positions[:6], [(x, L.ORB_Y) for x in L.ORB_X])
        self.assertEqual(positions[6], (L.BACK[0], L.BACK[1]))
        glyphs = [c.args[0] for c in self.lvr.button_icon.return_value.set_text.call_args_list]
        self.assertEqual(glyphs, [g for _, g, _ in L.ORBS] + [chr(0xe166)])

    def test_every_orb_leads_where_its_icon_says(self):
        settings, store, apps, portal, search, power, back = self.clicks(self.lvr.button_icon.return_value)
        settings(None); self.app.show_screen.assert_called_with(self.app.screen_advanced)
        store(None); self.app.show_screen.assert_called_with(self.app.screen_store)
        apps(None); self.app.show_screen.assert_called_with(self.app.screen_apps)
        portal(None); self.assertEqual(self.app.show_qr_dialog.call_args.args[0], 'http://192.168.1.5:8090')
        search(None); self.app.browser_show.assert_called_once()
        power(None); self.app.show_selection_dialog.assert_called_once()
        back(None); self.app.quit.assert_called_once()

    def test_the_tab_opens_the_quick_settings(self):
        tab = self.clicks(self.lvr.button.return_value)[0]
        self.assertFalse(self.app.liquid_panel.open)
        with mock.patch.object(liquid_ui, 'read_brightness', return_value=40):
            tab(None)
        self.assertTrue(self.app.liquid_panel.open)
        self.lv.slider.return_value.set_value.assert_called_with(40, 0)            # it shows the brightness now

    def test_opening_the_panel_shows_what_is_true_now(self):
        self.names['get_app_property'].return_value = 'off'
        open(self.App.MUTE_SOUNDS_FILE, 'wb').close()
        self.app.liquid_open_panel()
        self.assertFalse(self.app.liquid_sounds.on)
        self.assertFalse(self.app.liquid_updates.on)
        os.remove(self.App.MUTE_SOUNDS_FILE)
        self.names['get_app_property'].return_value = 'auto'
        self.app.liquid_panel.hide()
        self.app.liquid_open_panel()
        self.assertTrue(self.app.liquid_sounds.on)
        self.assertTrue(self.app.liquid_updates.on)

    def test_the_sounds_toggle_mutes_and_unmutes(self):
        self.app.liquid_sounds.toggle()                                            # on -> off: muted
        self.assertTrue(os.path.exists(self.App.MUTE_SOUNDS_FILE))
        self.app.liquid_sounds.toggle()
        self.assertFalse(os.path.exists(self.App.MUTE_SOUNDS_FILE))

    def test_a_sounds_change_that_fails_is_not_shown_as_done(self):
        self.App.MUTE_SOUNDS_FILE = os.path.join(self.tmp.name, 'missing-folder', 'mute-sounds')
        was = self.app.liquid_sounds.on
        with self.assertLogs(level='ERROR'):
            self.app.liquid_sounds.toggle()
        self.assertEqual(self.app.liquid_sounds.on, was)

    def test_the_auto_update_toggle_sets_the_property_off_the_screens_thread(self):
        self.app.liquid_updates.toggle()
        self.names['set_app_property'].assert_called_with('65-rinkhals-web', 'auto_update', 'off')
        self.app.liquid_updates.toggle()
        self.names['set_app_property'].assert_called_with('65-rinkhals-web', 'auto_update', 'auto')

    def test_the_auto_update_toggle_keeps_the_channel_chosen_in_settings(self):
        self.names['get_app_property'].return_value = 'release'
        self.app.liquid_open_panel()                  # reads the setting: on, following Release
        self.app.liquid_updates.toggle()
        self.names['set_app_property'].assert_called_with('65-rinkhals-web', 'auto_update', 'off')
        self.app.liquid_updates.toggle()
        self.names['set_app_property'].assert_called_with('65-rinkhals-web', 'auto_update', 'release')

    def test_brightness_is_written_at_most_every_50_ms_but_the_last_value_always(self):
        with mock.patch.object(liquid_ui, 'set_brightness') as write:
            self.app.liquid_brightness(80)
            self.app.liquid_brightness(70)                      # right after: skipped while dragging
            self.app.liquid_brightness(60)
            self.assertEqual([c.args[0] for c in write.call_args_list], [80])
            self.app.liquid_brightness(55, final=True)          # the release always writes
            self.assertEqual([c.args[0] for c in write.call_args_list], [80, 55])

    def test_a_brightness_that_cannot_be_written_is_logged_not_raised(self):
        with mock.patch.object(liquid_ui, 'set_brightness', side_effect=OSError('read-only')), self.assertLogs(level='ERROR'):
            self.app.liquid_brightness(50, final=True)

    def test_the_panels_buttons_close_it_and_go_on(self):
        taps = self.clicks(self.lvr.button.return_value)
        # creation order: tab, update pill, close handle, sounds, auto update, web portal, settings
        web, settings = taps[-2], taps[-1]
        self.app.liquid_open_panel()
        web(None)
        self.assertFalse(self.app.liquid_panel.open)
        self.assertEqual(self.app.show_qr_dialog.call_args.args[0], 'http://192.168.1.5:8090')
        self.app.liquid_open_panel()
        settings(None)
        self.assertFalse(self.app.liquid_panel.open)
        self.app.show_screen.assert_called_with(self.app.screen_advanced)

    def test_it_has_what_aero_has_so_the_shared_parts_work(self):
        # the clock, the update pill, the badge and the status line are the same attributes
        for name in ('home_label_time', 'home_label_date', 'home_pill', 'home_badge', 'home_wifi', 'home_label_status'):
            self.assertTrue(hasattr(self.app, name), name)
        self.app.home_theme = 'liquid'
        self.app.home_show_update(mock.Mock(version='2611-7-alpha'))
        self.assertIn(mock.call(self.lv.OBJ_FLAG.HIDDEN), self.app.home_pill.remove_flag.call_args_list)



class AutoUpdateToggleTests(unittest.TestCase):
    def test_off_is_off(self):
        self.assertEqual(liquid_ui.auto_update_value(False, 'release'), 'off')

    def test_on_goes_back_to_the_channel_chosen_before(self):
        self.assertEqual(liquid_ui.auto_update_value(True, 'release'), 'release')
        self.assertEqual(liquid_ui.auto_update_value(True, 'beta'), 'beta')

    def test_on_is_auto_when_there_was_no_choice(self):
        for previous in (None, '', '  ', 'off', 'OFF'):
            self.assertEqual(liquid_ui.auto_update_value(True, previous), 'auto')


class BindingPartsTests(unittest.TestCase):
    """liquid_ui can't use lv.PART (the binding defines it twice); its own values must match LVGL's."""

    def test_the_part_values_are_the_ones_of_the_binding(self):
        import ast
        source = (Path(__file__).resolve().parents[1] /
                  'files/3-rinkhals/opt/rinkhals/ui/lvgl/__init__.py').read_text(encoding='utf-8')
        parts = [node for node in ast.parse(source).body if isinstance(node, ast.ClassDef) and node.name == 'PART']
        values = {}
        for node in parts:
            for item in node.body:
                if isinstance(item, ast.Assign) and isinstance(item.value, ast.Constant):
                    values.setdefault(item.targets[0].id, item.value.value)
        self.assertEqual(liquid_ui.PART_MAIN, values['MAIN'])
        self.assertEqual(liquid_ui.PART_INDICATOR, values['INDICATOR'])
        self.assertEqual(liquid_ui.PART_KNOB, values['KNOB'])


class LightLiquidHomeTests(LiquidHomeTests):
    """Light mode: its own pictures, and dark green ink on the white glass."""
    LIGHT = True

    def test_the_wallpaper_is_the_picture_with_the_panes_in_it(self):
        sources = [c.args[0] for c in self.lvr.image.return_value.set_src.call_args_list]
        self.assertEqual(sources[0], '/assets/liquid-home-light.bin')
        self.assertIn('/assets/liquid-panel-light.bin', sources)

    def test_the_panes_ink_is_white_on_the_dark_glass(self):
        self.assertEqual(self.app.liquid_glass.ink, (24, 56, 30))
        self.assertTrue(self.app.liquid_glass.light)


if __name__ == '__main__':
    unittest.main()
