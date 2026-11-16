"""Touch UI pieces that need no screen: previous version, update notice, status line, bookmarks."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'files/3-rinkhals/opt/rinkhals/ui'))
import home_tools  # noqa: E402


class PreviousInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, folder, version=None, age=0, complete=True):
        root = Path(self.base) / folder
        (root / 'usr/bin').mkdir(parents=True)
        (root / 'opt/rinkhals').mkdir(parents=True)
        if complete:
            (root / 'start.sh').write_text('x')
            (root / 'usr/bin/python').write_text('x')
        (root / '.version').write_text((version or folder) + '\n')
        stamp = time.time() - age
        os.utime(root / '.version', (stamp, stamp))

    def test_the_most_recently_installed_other_version(self):
        self.install('2611-1-alpha', age=3000)
        self.install('2611-2-alpha', age=2000)
        self.install('2611-3-alpha', age=10)          # running
        self.assertEqual(home_tools.previous_install(self.base, '2611-3-alpha'), ('2611-2-alpha', '2611-2-alpha'))

    def test_a_folder_named_differently_from_its_version(self):
        self.install('2611-2-alpha-2', version='2611-2-alpha', age=50)   # a re-install lands in <name>-2
        self.install('2611-3-alpha')
        self.assertEqual(home_tools.previous_install(self.base, '2611-3-alpha'), ('2611-2-alpha-2', '2611-2-alpha'))

    def test_incomplete_installs_and_other_folders_are_not_offered(self):
        self.install('2611-2-alpha', complete=False)  # an interrupted copy
        self.install('2611-3-alpha')
        (Path(self.base) / 'tmp').mkdir()
        (Path(self.base) / '.current').mkdir()
        self.assertIsNone(home_tools.previous_install(self.base, '2611-3-alpha'))
        self.assertIsNone(home_tools.previous_install(self.base + '/missing', 'x'))

    def test_selecting_writes_the_folder_name_whole(self):
        self.install('2611-2-alpha')
        (Path(self.base) / '.version').write_text('2611-3-alpha\n')
        home_tools.select_install(self.base, '2611-2-alpha')
        self.assertEqual((Path(self.base) / '.version').read_text(), '2611-2-alpha\n')
        self.assertFalse((Path(self.base) / '.version.new').exists())
        for bad in ('', 'nope', '../etc', '2611-2-alpha/usr'):
            with self.assertRaises(ValueError):
                home_tools.select_install(self.base, bad)
        self.assertEqual((Path(self.base) / '.version').read_text(), '2611-2-alpha\n')

    def test_the_version_left_behind_is_kept_from_the_automatic_updater(self):
        path = os.path.join(self.base, 'tried')
        home_tools.keep_from_auto_install('2611-3-alpha', path)
        self.assertEqual(Path(path).read_text().strip(), '2611-3-alpha')


class UpdateNoticeTests(unittest.TestCase):
    def notice(self, content, current):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'notice')
            if content is not None:
                Path(path).write_text(content)
            message = home_tools.take_update_notice(current, path)
            return message, os.path.exists(path)

    def test_shown_once_after_an_update(self):
        message, left = self.notice(json.dumps({'from': '2611-2-alpha', 'to': '2611-3-alpha'}), '2611-3-alpha')
        self.assertIn('updated itself', message)
        self.assertIn('2611 3 Alpha', message)
        self.assertIn('2611 2 Alpha', message)
        self.assertFalse(left)

    def test_an_update_that_did_not_take(self):
        message, _ = self.notice(json.dumps({'from': '2611-2-alpha', 'to': '2611-3-alpha'}), '2611-2-alpha')
        self.assertIn('did not complete', message)
        self.assertIn('still on', message)

    def test_nothing_to_say(self):
        self.assertEqual(self.notice(None, '2611-3-alpha'), (None, False))
        self.assertIsNone(self.notice('not json', '2611-3-alpha')[0])
        self.assertIsNone(self.notice('[]', '2611-3-alpha')[0])
        self.assertIsNone(self.notice('{"from": "a"}', '2611-3-alpha')[0])


class StatusLineTests(unittest.TestCase):
    def test_idle_with_heaters_off(self):
        status = {'extruder': {'temperature': 24.6, 'target': 0}, 'heater_bed': {'temperature': 23.9, 'target': 0},
                  'print_stats': {'state': 'standby'}}
        self.assertEqual(home_tools.format_status(status), 'Nozzle 25\u00b0C \u00b7 Bed 24\u00b0C \u00b7 Idle')

    def test_printing_with_targets_and_progress(self):
        status = {'extruder': {'temperature': 209.7, 'target': 215}, 'heater_bed': {'temperature': 60.2, 'target': 60},
                  'print_stats': {'state': 'printing'}, 'display_status': {'progress': 0.4239}}
        self.assertEqual(home_tools.format_status(status),
                         'Nozzle 210/215\u00b0C \u00b7 Bed 60/60\u00b0C \u00b7 Printing 42%')

    def test_missing_pieces_are_left_out(self):
        self.assertEqual(home_tools.format_status({'print_stats': {'state': 'error'}}), 'Error')
        self.assertEqual(home_tools.format_status({'extruder': {'temperature': None}}), '')
        self.assertEqual(home_tools.format_status(None), '')
        self.assertEqual(home_tools.format_status({'print_stats': {'state': 'complete'}, 'display_status': {'progress': 1}}),
                         'Finished')

    def test_no_moonraker_means_an_empty_line(self):
        import urllib.request
        original = urllib.request.urlopen

        def refuse(*args, **kwargs):
            raise OSError('connection refused')
        urllib.request.urlopen = refuse
        try:
            self.assertEqual(home_tools.fetch_status(timeout=0.2), '')
        finally:
            urllib.request.urlopen = original


class NotificationTopicTests(unittest.TestCase):
    def test_topics_are_random_and_valid(self):
        topics = {home_tools.new_ntfy_topic() for _ in range(50)}
        self.assertEqual(len(topics), 50)
        self.assertTrue(all(home_tools.valid_ntfy_topic(t) and len(t) >= 28 for t in topics))

    def test_validation_and_link(self):
        for bad in ('', None, 'has space', 'a/b', 'x' * 65):
            self.assertFalse(home_tools.valid_ntfy_topic(bad), bad)
        self.assertEqual(home_tools.ntfy_link('', 'topic'), 'https://ntfy.sh/topic')
        self.assertEqual(home_tools.ntfy_link('https://push.example/', 'topic'), 'https://push.example/topic')


class BookmarkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, 'sub', 'bookmarks.json')

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_list_remove(self):
        self.assertEqual(home_tools.load_bookmarks(self.path), [])
        self.assertTrue(home_tools.toggle_bookmark('Klipper docs', 'https://www.klipper3d.org/', self.path))
        self.assertTrue(home_tools.toggle_bookmark('', 'https://example.com/a', self.path))
        self.assertEqual(home_tools.load_bookmarks(self.path),
                         [('Klipper docs', 'https://www.klipper3d.org/'), ('https://example.com/a', 'https://example.com/a')])
        self.assertTrue(home_tools.is_bookmarked('https://example.com/a', self.path))
        self.assertFalse(home_tools.toggle_bookmark('x', 'https://example.com/a', self.path))
        self.assertFalse(home_tools.is_bookmarked('https://example.com/a', self.path))

    def test_the_list_is_bounded_and_keeps_the_newest(self):
        for i in range(home_tools.MAX_BOOKMARKS + 5):
            home_tools.toggle_bookmark(f'page {i}', f'https://example.com/{i}', self.path)
        saved = home_tools.load_bookmarks(self.path)
        self.assertEqual(len(saved), home_tools.MAX_BOOKMARKS)
        self.assertEqual(saved[-1][1], f'https://example.com/{home_tools.MAX_BOOKMARKS + 4}')

    def test_a_damaged_file_is_an_empty_list(self):
        os.makedirs(os.path.dirname(self.path))
        for content in ('not json', '{"a": 1}', '[1, "x", {"url": "ftp://x"}, {"url": 5}]'):
            Path(self.path).write_text(content)
            self.assertEqual(home_tools.load_bookmarks(self.path), [])



class ThemeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.theme = os.path.join(self.tmp.name, 'ui-theme')
        self.legacy = os.path.join(self.tmp.name, 'classic-ui')

    def tearDown(self):
        self.tmp.cleanup()

    def look(self, width=800, height=480):
        return home_tools.theme_for(width, height, self.theme, self.legacy)

    def test_aero_is_the_default_on_the_screen_it_is_drawn_for(self):
        self.assertEqual(self.look(), 'aero')
        self.assertTrue(home_tools.aero_possible(800, 480))

    def test_other_screens_keep_the_classic_look_whatever_was_chosen(self):
        home_tools.set_theme('liquid', self.theme, self.legacy)
        for size in ((480, 272), (272, 480), (800, 600), (1024, 600)):
            self.assertEqual(self.look(*size), 'classic', size)
            self.assertFalse(home_tools.aero_possible(*size), size)

    def test_every_look_can_be_chosen_and_is_remembered(self):
        for name in home_tools.THEMES:
            home_tools.set_theme(name, self.theme, self.legacy)
            self.assertEqual(self.look(), name)
        self.assertEqual(set(home_tools.THEMES), {'classic', 'aero', 'liquid'})
        self.assertEqual(home_tools.THEME_NAMES['liquid'], 'Liquid Plastic')

    def test_an_unknown_look_is_refused_and_a_damaged_file_is_ignored(self):
        with self.assertRaises(ValueError):
            home_tools.set_theme('neon', self.theme, self.legacy)
        self.assertFalse(os.path.exists(self.theme))
        for content in ('', 'neon\n', '\x00\x01'):
            with open(self.theme, 'w') as f:
                f.write(content)
            self.assertEqual(self.look(), 'aero', repr(content))      # falls back to the default

    def test_the_old_classic_flag_still_means_classic(self):
        # Before there were three looks, "Switch to Classic UI" left an empty file
        open(self.legacy, 'w').close()
        self.assertEqual(self.look(), 'classic')
        # a choice made since then wins, and removes the old flag so the two never disagree
        home_tools.set_theme('liquid', self.theme, self.legacy)
        self.assertFalse(os.path.exists(self.legacy))
        self.assertEqual(self.look(), 'liquid')



if __name__ == '__main__':
    unittest.main()
