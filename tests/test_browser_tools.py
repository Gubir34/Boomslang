"""LemSearch Lite without a screen: cache, saved settings, find in page, quick searches, print files."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'testsupport.browser_tools', Path(__file__).resolve().parents[1] / 'files/3-rinkhals/opt/rinkhals/ui/browser_tools.py')
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)


class PageCacheTests(unittest.TestCase):
    def test_keeps_the_newest_and_forgets_the_oldest(self):
        cache = bt.PageCache(size=2)
        cache.put('a', 1)
        cache.put('b', 2)
        cache.get('a')                 # a is used again: b is now the oldest
        cache.put('c', 3)
        self.assertEqual((cache.get('a'), cache.get('b'), cache.get('c')), (1, None, 3))

    def test_old_pages_are_not_shown(self):
        now = [0]
        cache = bt.PageCache(size=5, max_age=60, clock=lambda: now[0])
        cache.put('a', 1)
        now[0] = 59
        self.assertEqual(cache.get('a'), 1)
        now[0] = 200
        self.assertIsNone(cache.get('a'))


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, 'sub', 'lemsearch.json')

    def tearDown(self):
        self.tmp.cleanup()

    def test_nothing_saved_reads_as_defaults_and_a_broken_file_too(self):
        settings = bt.Settings(self.path)
        self.assertEqual((settings.text_scale(), settings.history(), settings.searches(), settings.blocked()),
                         (1.0, [], [], set()))
        os.makedirs(os.path.dirname(self.path))
        Path(self.path).write_text('{broken')
        self.assertEqual(bt.Settings(self.path).history(), [])

    def test_text_size_steps_stop_at_the_ends_and_are_kept(self):
        settings = bt.Settings(self.path)
        for _ in range(10):
            settings.change_text_scale(+1)
        self.assertEqual(settings.text_scale(), bt.TEXT_SCALES[-1])
        for _ in range(10):
            settings.change_text_scale(-1)
        self.assertEqual(bt.Settings(self.path).text_scale(), bt.TEXT_SCALES[0])

    def test_history_is_newest_first_without_repeats_and_capped(self):
        settings = bt.Settings(self.path)
        for i in range(bt.MAX_HISTORY + 5):
            settings.add_history(f'Page {i}', f'https://example.com/{i}')
        settings.add_history('Page 3 again', 'https://example.com/3')
        history = bt.Settings(self.path).history()
        self.assertEqual(len(history), bt.MAX_HISTORY)
        self.assertEqual(history[0], ('Page 3 again', 'https://example.com/3'))
        self.assertEqual(sum(1 for _, u in history if u == 'https://example.com/3'), 1)
        settings.add_history('x', 'javascript:alert(1)')
        self.assertNotIn('javascript:alert(1)', [u for _, u in bt.Settings(self.path).history()])

    def test_recent_searches(self):
        settings = bt.Settings(self.path)
        for words in ('benchy', 'pressure advance', 'BENCHY', '  '):
            settings.add_search(words)
        self.assertEqual(settings.searches(), ['BENCHY', 'pressure advance'])
        settings.clear_history()
        self.assertEqual((settings.searches(), settings.history()), ([], []))

    def test_refusing_sites_are_remembered_by_domain(self):
        settings = bt.Settings(self.path)
        settings.remember_blocked('https://www.printables.com/model/3161')
        self.assertTrue(bt.Settings(self.path).is_blocked('https://printables.com/other'))
        self.assertFalse(settings.is_blocked('https://www.klipper3d.org/'))
        settings.forget_blocked('https://printables.com/')
        self.assertFalse(bt.Settings(self.path).is_blocked('https://www.printables.com/'))

    def test_a_disk_that_can_not_be_written_does_not_break_browsing(self):
        settings = bt.Settings('/proc/forbidden/lemsearch.json')
        settings.add_search('still works')
        self.assertEqual(settings.searches(), ['still works'])


class FindTests(unittest.TestCase):
    BLOCKS = [{'text': 'Intro'}, {'text': 'Pressure advance tuning'}, {'text': 'other'},
              {'text': 'More on PRESSURE advance'}]

    def test_finds_the_next_match_and_wraps_around(self):
        self.assertEqual(bt.find_block(self.BLOCKS, 'pressure advance'), 1)
        self.assertEqual(bt.find_block(self.BLOCKS, 'pressure advance', after=1), 3)
        self.assertEqual(bt.find_block(self.BLOCKS, 'pressure advance', after=3), 1)
        self.assertEqual(bt.count_matches(self.BLOCKS, 'pressure'), 2)

    def test_nothing_to_find(self):
        self.assertIsNone(bt.find_block(self.BLOCKS, 'benchy'))
        self.assertIsNone(bt.find_block(self.BLOCKS, '  '))
        self.assertIsNone(bt.find_block([], 'x'))


class QuickSearchTests(unittest.TestCase):
    def test_words_are_searched_inside_the_site(self):
        self.assertEqual(bt.quick_search_words('klipper3d.org', ' pressure advance '),
                         'site:klipper3d.org pressure advance')
        self.assertEqual(bt.quick_search_words('klipper3d.org', ''), '')


class FakeResponse:
    def __init__(self, body=b'G1 X0\n' * 100, status=200, ctype='application/octet-stream', length=True):
        self.body, self.status_code = body, status
        self.headers = {'Content-Type': ctype}
        if length:
            self.headers['Content-Length'] = str(len(body))
        self.closed = False

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self.body), chunk_size):
            yield self.body[i:i + chunk_size]

    def close(self):
        self.closed = True


class PrintFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def download(self, url='https://files.example/benchy.gcode', response=None, **kwargs):
        response = response or FakeResponse()
        kwargs.setdefault('free', lambda path: 10 * 1024 ** 3)
        return bt.download_print_file(url, self.folder, get=lambda *a, **k: response, **kwargs), response

    def test_print_file_links_are_known(self):
        self.assertTrue(bt.is_print_file('https://x.example/files/Benchy%20v2.gcode?dl=1'))
        self.assertFalse(bt.is_print_file('https://x.example/benchy.stl'))
        self.assertFalse(bt.is_print_file('https://x.example/gcode-guide'))

    def test_names_are_safe_and_do_not_overwrite(self):
        self.assertEqual(bt.print_file_name('https://x/a/..%2F..%2Fetc%2Fpasswd.gcode'), 'passwd.gcode')
        self.assertEqual(bt.print_file_name('https://x/.hidden.gcode'), 'hidden.gcode')
        self.assertEqual(bt.print_file_name('https://x/Benchy.GCODE', existing=['Benchy.gcode']), 'Benchy (2).gcode')
        self.assertEqual(bt.print_file_name('https://x/'), 'download.gcode')

    def test_a_file_is_saved_whole(self):
        path, response = self.download()
        self.assertEqual(path, os.path.join(self.folder, 'benchy.gcode'))
        self.assertEqual(Path(path).read_bytes(), response.body)
        self.assertEqual(os.listdir(self.folder), ['benchy.gcode'])
        self.assertTrue(response.closed)

    def test_never_while_printing(self):
        with self.assertRaises(bt.DownloadError):
            self.download(printing=lambda: True)
        self.assertEqual(os.listdir(self.folder), [])

    def test_a_print_that_starts_during_the_download_drops_the_file(self):
        calls = iter([False, True])
        with self.assertRaises(bt.DownloadError):
            self.download(printing=lambda: next(calls))
        self.assertEqual(os.listdir(self.folder), [])

    def test_too_big_or_no_room_leaves_nothing(self):
        big = FakeResponse(body=b'x' * 10)
        big.headers['Content-Length'] = str(bt.MAX_PRINT_FILE_BYTES + 1)
        with self.assertRaises(bt.DownloadError):
            self.download(response=big)
        with self.assertRaises(bt.DownloadError):
            self.download(free=lambda path: bt.FREE_MARGIN_BYTES + 10)       # 10 bytes of room for 600
        # no Content-Length: stopped while writing, the part file removed
        with self.assertRaises(bt.DownloadError):
            self.download(response=FakeResponse(length=False), free=lambda path: bt.FREE_MARGIN_BYTES + 10)
        self.assertEqual(os.listdir(self.folder), [])

    def test_a_web_page_or_an_error_is_not_saved(self):
        with self.assertRaises(bt.DownloadError):
            self.download(response=FakeResponse(b'<html>', ctype='text/html; charset=utf-8'))
        with self.assertRaises(bt.DownloadError):
            self.download(response=FakeResponse(status=404))
        self.assertEqual(os.listdir(self.folder), [])

    def test_a_cut_download_is_not_kept(self):
        response = FakeResponse(body=b'G1\n' * 10)
        response.headers['Content-Length'] = '9999'
        with self.assertRaises(bt.DownloadError):
            self.download(response=response)
        self.assertEqual(os.listdir(self.folder), [])

    def test_progress_is_reported(self):
        seen = []
        self.download(progress=lambda done, total: seen.append((done, total)))
        self.assertEqual(seen[-1], (600, 600))


class PrinterBusyTests(unittest.TestCase):
    def answer(self, state, nozzle=0, bed=0, reading=False):
        return lambda: {'result': {'status': {'print_stats': {'state': state},
                                              'extruder': {'temperature': 25, 'target': nozzle},
                                              'heater_bed': {'temperature': 25, 'target': bed},
                                              'virtual_sdcard': {'is_active': reading}}}}

    def test_standby_with_a_heater_on_or_a_file_being_read_is_busy(self):
        # GoKlipper can say standby mid-print: the heaters tell the truth
        self.assertTrue(bt.printer_busy(self.answer('standby', nozzle=220)))
        self.assertTrue(bt.printer_busy(self.answer('standby', bed=60)))
        self.assertTrue(bt.printer_busy(self.answer('complete', reading=True)))
        self.assertTrue(bt.printer_busy(self.answer('')))                      # no state
        self.assertTrue(bt.printer_busy(self.answer('leveling')))              # not translated
        self.assertTrue(bt.printer_busy(lambda: {'result': {'status': {'print_stats': {'state': 'standby'}}}}))

    def test_printing_or_paused_is_busy_idle_states_are_not(self):
        for state in ('printing', 'paused', 'PRINTING'):
            self.assertTrue(bt.printer_busy(self.answer(state)), state)
        for state in ('standby', 'complete', 'cancelled', 'error'):
            self.assertFalse(bt.printer_busy(self.answer(state)), state)

    def test_when_it_can_not_be_told_it_counts_as_busy(self):
        def down():
            raise OSError('connection refused')
        self.assertTrue(bt.printer_busy(down))
        self.assertTrue(bt.printer_busy(lambda: {'result': {}}))
