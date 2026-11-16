"""The Aero home screen and the theme choice.

As in test_browser_screen.py the methods are cut out of rinkhals-ui.py with
ast and run against stand-in widgets, because the file can't be imported
without LVGL. This checks what the code does (which widgets, where, what a
tap leads to, what happens when building fails); it can not check how the
screen looks.
"""
import ast
import importlib.util
import logging
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

UI = Path(__file__).resolve().parents[1] / 'files/3-rinkhals/opt/rinkhals/ui'
sys.path.insert(0, str(UI))
import home_tools  # noqa: E402

SOURCE = (UI / 'rinkhals-ui.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
APP = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'RinkhalsUiApp')

WANTED = ('layout', 'layout_aero_home', 'home_show_link', 'home_show_update', 'aero_power', 'aero_tick_clock',
          'aero_refresh', 'switch_theme', 'aero_clear', 'aero_glass', 'aero_light', 'aero_orb', 'aero_glyph')


def load_class(lv, lvr):
    wanted = []
    for node in APP.body:
        if isinstance(node, ast.FunctionDef) and node.name in WANTED:
            wanted.append(ast.get_source_segment(SOURCE, node))
        elif isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '').startswith('AERO_'):
            wanted.append(ast.get_source_segment(SOURCE, node))
    code = 'class AeroApp(Base):\n' + '\n'.join('    ' + line for chunk in wanted for line in chunk.split('\n')) + '\n'

    class Base:
        def layout(self):
            pass

    namespace = {
        'Base': Base, 'lv': lv, 'lvr': lvr, 'logging': logging, 'time': time, 'home_tools': home_tools,
        'ASSETS_PATH': '/assets', 'RINKHALS_VERSION': '2611-4-alpha',
        'display_version': lambda v: '2611 4 Alpha', 'ellipsis': lambda t, n: t,
        'printer_ip': lambda: '192.168.1.5', 'run_async': lambda fn: None,
    }
    exec(compile(code, 'rinkhals-ui-aero', 'exec'), namespace)
    return namespace['AeroApp']


class AeroHomeTests(unittest.TestCase):
    def setUp(self):
        self.lv, self.lvr = mock.MagicMock(name='lv'), mock.MagicMock(name='lvr')
        self.App = load_class(self.lv, self.lvr)
        self.tmp = tempfile.TemporaryDirectory()
        home_tools.CLASSIC_UI_FLAG = os.path.join(self.tmp.name, 'classic-ui')
        self.app = self.App()
        self.app.screen_info = mock.Mock(width=800, height=480)
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
        self.app.restart_rinkhals = self.app.reboot_printer = self.app.stop_rinkhals = mock.MagicMock()
        self.app.layout_classic_home = mock.MagicMock()
        self.app.layout_async = mock.MagicMock()
        self.app.modal_selection = object()

    def tearDown(self):
        self.tmp.cleanup()
        home_tools.CLASSIC_UI_FLAG = '/useremain/rinkhals/.classic-ui'

    def orb_taps(self):
        """The handlers of the six orbs, in the order they were created, and the back button's."""
        calls = self.lvr.button_icon.return_value.add_event_cb.call_args_list
        return [c.args[0] for c in calls]

    # --- which look is used ----------------------------------------------------------
    def test_aero_is_used_by_default_on_an_800x480_screen(self):
        self.app.layout()
        self.assertEqual(self.app.home_theme, 'aero')
        self.app.layout_classic_home.assert_not_called()
        self.app.show_screen.assert_called_with(self.app.screen_main)

    def test_other_screens_and_the_classic_choice_use_classic(self):
        self.app.screen_info = mock.Mock(width=480, height=272)
        self.app.layout()
        self.assertEqual(self.app.home_theme, 'classic')
        self.app.layout_classic_home.assert_called_once()

        self.app.layout_classic_home.reset_mock()
        self.app.screen_info = mock.Mock(width=800, height=480)
        home_tools.set_aero(False)
        self.app.layout()
        self.assertEqual(self.app.home_theme, 'classic')
        self.app.layout_classic_home.assert_called_once()

    def test_a_home_that_fails_to_build_falls_back_to_classic(self):
        self.lvr.image.side_effect = RuntimeError('wallpaper could not be loaded')
        with self.assertLogs(level='ERROR'):
            self.app.layout()
        self.assertEqual(self.app.home_theme, 'classic')
        self.app.screen_main.clean.assert_called_once()        # what Aero had added is removed first
        self.app.layout_classic_home.assert_called_once()
        self.app.show_screen.assert_called_with(self.app.screen_main)

    # --- what it shows ------------------------------------------------------------------
    def test_the_taskbar_has_six_orbs_in_the_mockups_places(self):
        self.app.layout()
        orb = self.lvr.button_icon.return_value
        positions = [c.args for c in orb.set_pos.call_args_list]
        self.assertEqual([p for p in positions if p[1] == 410], [(14, 410), (88, 410), (162, 410), (236, 410), (310, 410), (384, 410)])
        sizes = [c.args for c in orb.set_size.call_args_list]
        self.assertEqual(sizes.count((60, 60)), 7)              # six orbs and the back button
        glyphs = [c.args[0] for c in orb.set_text.call_args_list]
        self.assertEqual(glyphs, ['', '', '', '', '', '', ''])

    def test_every_orb_leads_where_its_icon_says(self):
        self.app.layout()
        settings, store, apps, portal, search, power, back = self.orb_taps()
        settings(None); self.app.show_screen.assert_called_with(self.app.screen_advanced)
        store(None); self.app.show_screen.assert_called_with(self.app.screen_store)
        apps(None); self.app.show_screen.assert_called_with(self.app.screen_apps)
        portal(None)
        self.assertEqual(self.app.show_qr_dialog.call_args.args[0], 'http://192.168.1.5:8090')
        search(None); self.app.browser_show.assert_called_once()
        power(None); self.app.show_selection_dialog.assert_called_once()
        back(None); self.app.quit.assert_called_once()

    def test_the_power_orb_asks_before_each_action(self):
        self.app.layout()
        self.orb_taps()[5](None)
        options, chosen = self.app.show_selection_dialog.call_args.args
        self.assertEqual(options, ['Restart Boomslang', 'Reboot printer', 'Switch to stock'])
        for option, action in zip(options, (self.app.restart_rinkhals, self.app.reboot_printer, self.app.stop_rinkhals)):
            self.app.show_text_dialog.reset_mock()
            chosen(option)
            self.assertEqual(self.app.show_text_dialog.call_args.kwargs['callback'], action)   # confirmed first, then done
            action.assert_not_called()

    def test_the_power_orb_before_the_background_build_says_so(self):
        self.app.modal_selection = None
        self.app.aero_power()
        self.app.show_selection_dialog.assert_not_called()
        self.assertIn('loading', self.app.show_text_dialog.call_args.args[0])

    def test_the_web_portal_orb_without_a_network_says_so(self):
        self.app.layout()
        with mock.patch.dict(self.App.home_show_link.__globals__, {'printer_ip': lambda: None}):
            self.orb_taps()[3](None)
        self.app.show_qr_dialog.assert_not_called()
        self.assertIn('no network', self.app.show_text_dialog.call_args.args[0])

    def test_the_update_pill_and_badge_appear_with_a_newer_release(self):
        self.app.layout()
        pill, badge = self.app.aero_pill, self.app.aero_badge
        self.assertIn(mock.call(self.lv.OBJ_FLAG.HIDDEN), pill.add_flag.call_args_list)     # hidden to begin with
        self.assertIn(mock.call(self.lv.OBJ_FLAG.HIDDEN), badge.add_flag.call_args_list)
        shown = mock.call(self.lv.OBJ_FLAG.HIDDEN)
        self.assertNotIn(shown, pill.remove_flag.call_args_list)       # nothing is shown before an update is found
        self.assertNotIn(shown, badge.remove_flag.call_args_list)
        self.app.home_show_update(mock.Mock(version='2611-5-alpha'))
        self.assertIn(shown, pill.remove_flag.call_args_list)
        self.assertIn(shown, badge.remove_flag.call_args_list)
        # and the pill opens the Updates screen
        tap = [c.args[0] for c in pill.add_event_cb.call_args_list][-1]
        tap(None)
        self.app.show_screen.assert_called_with(self.app.screen_ota)

    def test_the_clock_shows_hours_minutes_and_the_date(self):
        self.app.layout()
        moment = time.struct_time((2026, 11, 11, 19, 9, 30, 2, 315, 0))
        with mock.patch.object(time, 'localtime', return_value=moment):
            self.app.aero_tick_clock()
        self.app.aero_label_time.set_text.assert_called_with('19:09')
        self.app.aero_label_date.set_text.assert_called_with('11/11/2026')

    def test_the_wifi_icon_dims_without_a_network(self):
        self.app.layout()
        with mock.patch.dict(self.App.aero_refresh.__globals__, {'printer_ip': lambda: None}):
            self.app.aero_refresh()
        dim = self.lv.color_make.call_args_list
        self.assertIn(mock.call(120, 140, 120), dim)

    # --- Settings > Switch to Classic UI / Aero UI ------------------------------------------
    def test_switching_the_look_is_saved_and_closes_boomslang(self):
        self.app.home_theme = 'aero'
        self.app.switch_theme()
        self.assertTrue(os.path.exists(home_tools.CLASSIC_UI_FLAG))              # Classic from now on
        message = self.app.show_text_dialog.call_args
        self.assertIn('Classic', message.args[0])
        self.assertEqual(message.kwargs['callback'], self.app.quit)
        self.app.quit.assert_not_called()                                         # only after the message is read

        self.app.home_theme = 'classic'
        self.app.switch_theme()
        self.assertFalse(os.path.exists(home_tools.CLASSIC_UI_FLAG))              # Aero again
        self.assertIn('Aero', self.app.show_text_dialog.call_args.args[0])

    def test_a_look_that_cannot_be_saved_changes_nothing(self):
        self.app.home_theme = 'aero'
        with mock.patch.object(home_tools, 'set_aero', side_effect=OSError('read-only')), self.assertLogs(level='ERROR'):
            self.app.switch_theme()
        self.assertIn('Nothing was changed', self.app.show_text_dialog.call_args.args[0])
        self.assertNotIn('callback', self.app.show_text_dialog.call_args.kwargs)


class StartupTests(unittest.TestCase):
    """The home screen must not wait for the other screens to be built."""

    def region(self):
        start = SOURCE.index('    def layout_async(self):')
        return SOURCE[start:SOURCE.index('    def show_screen(self, screen):', start)]

    def test_every_background_screen_is_built_in_its_own_step(self):
        region = self.region()
        self.assertNotIn('with lvr.lock():', region, 'a screen is built under the lock without a pause in front of it')
        self.assertGreaterEqual(region.count('with self.build_step():'), 10)

    def test_the_background_build_waits_for_the_first_frame(self):
        body = self.region().split('\n', 12)
        waits = [i for i, line in enumerate(body) if 'self.first_frame.wait(' in line]
        builds = [i for i, line in enumerate(body) if 'with self.build_step():' in line]
        self.assertTrue(waits and (not builds or waits[0] < builds[0]))

    def test_the_main_loop_announces_the_first_frame(self):
        common = (UI / 'common.py').read_text(encoding='utf-8')
        loop = common[common.index('def loop():'):common.index('if USING_SIMULATOR:\n            loop()')]
        self.assertLess(loop.index('lv.timer_handler()'), loop.index('self.first_frame.set()'))

    def test_a_screen_that_is_not_built_yet_is_explained_not_ignored(self):
        self.assertIn("self.show_text_dialog('Still loading,", SOURCE)


if __name__ == '__main__':
    unittest.main()
