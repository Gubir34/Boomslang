"""Logic of the touch screen browser (history, cancelling, errors, limits).

rinkhals-ui.py cannot be imported without the LVGL library, so the browser
methods are cut out of the real file with ast and run against stand-in
widgets. What this does not check is how the screen looks.
"""
import ast
import importlib.util
import logging
import unittest
from pathlib import Path
from unittest import mock

UI = Path(__file__).resolve().parents[1] / 'files/3-rinkhals/opt/rinkhals/ui'
spec = importlib.util.spec_from_file_location('testsupport.reader', UI / 'reader.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def load_browser_class():
    source = (UI / 'rinkhals-ui.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'RinkhalsUiApp')
    wanted = []
    for node in app.body:
        if isinstance(node, ast.FunctionDef) and (node.name.startswith('browser_') or node.name in (
                'layout_browser', 'show_info_dialog')):
            wanted.append(ast.get_source_segment(source, node))
        elif isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '').startswith(('BROWSER_', 'browser_', 'screen_browser')):
            wanted.append(ast.get_source_segment(source, node))
    code = 'class BrowserApp:\n' + '\n'.join('    ' + line for chunk in wanted for line in chunk.split('\n')) + '\n'
    lv, lvr = mock.MagicMock(name='lv'), mock.MagicMock(name='lvr')
    namespace = {'lv': lv, 'lvr': lvr, 'reader': reader, 'logging': logging,
                 'ellipsis': lambda text, n: text if len(text) <= n else text[:n - 1] + '…',
                 'run_async': lambda fn: fn(), 'printer_ip': lambda: '192.168.1.5',
                 'RINKHALS_VERSION': 'test', 'KOBRA_MODEL': 'Kobra', 'KOBRA_VERSION': '1.0'}
    exec(compile(code, 'rinkhals-ui-browser', 'exec'), namespace)
    return namespace['BrowserApp'], lvr, lv


BrowserApp, LVR, LV = load_browser_class()


def page(url, title='T', blocks=None, truncated=False):
    return reader.Page(url, title, blocks if blocks is not None else [{'kind': 'p', 'text': 'body', 'links': []}], truncated)


class BrowserScreenTests(unittest.TestCase):
    def setUp(self):
        LVR.reset_mock()
        LV.reset_mock()
        self.app = BrowserApp()
        self.app.root_screen = mock.MagicMock()
        self.app.screen_main = object()
        self.app.show_screen = mock.MagicMock()
        self.app.show_text_dialog = mock.MagicMock()
        self.app.show_input_text_dialog = mock.MagicMock()
        self.app.layout_browser()
        self.title = self.app.screen_browser.label_title
        self.fetched = []
        self.pages = {}

    def fetch(self, url):
        self.fetched.append(url)
        result = self.pages.get(url)
        if isinstance(result, Exception):
            raise result
        return result or page(url)

    def open(self, target, **kwargs):
        with mock.patch.object(reader, 'fetch', self.fetch):
            self.app.browser_open(target, **kwargs)

    def titles(self):
        return [c.args[0] for c in self.title.set_text.call_args_list]

    def count_buttons(self):
        return LVR.button.call_count

    # --- start page and addresses ---------------------------------------------
    def test_start_page_lists_the_bookmarks(self):
        self.app.browser_show()
        self.app.show_screen.assert_called_once_with(self.app.screen_browser)
        # the "open an address" button plus one per bookmark
        self.assertEqual(self.count_buttons(), 1 + len(BrowserApp.BROWSER_BOOKMARKS))

    def test_the_start_page_is_not_rebuilt_when_returning_to_a_page(self):
        self.app.browser_show()
        buttons = self.count_buttons()
        self.app.browser_show()
        self.assertEqual(self.count_buttons(), buttons)

    def test_typing_words_searches_and_bad_addresses_explain_themselves(self):
        self.open('klipper pressure advance')
        self.assertEqual(self.fetched, [reader.SEARCH_URL + 'klipper+pressure+advance'])
        self.open('file:///etc/passwd')
        self.app.show_text_dialog.assert_called_once()
        self.assertIn('http', self.app.show_text_dialog.call_args.args[0])
        self.assertEqual(len(self.fetched), 1)

    def test_empty_input_does_nothing(self):
        self.open('')
        self.open(None)
        self.assertEqual(self.fetched, [])

    def test_the_address_dialog_opens_what_was_typed(self):
        self.app.browser_ask_address()
        title, initial, is_number, callback = self.app.show_input_text_dialog.call_args.args
        self.assertFalse(is_number)
        with mock.patch.object(reader, 'fetch', self.fetch):
            callback('example.com')
        self.assertEqual(self.fetched, ['https://example.com'])

    # --- history ---------------------------------------------------------------
    def test_following_links_and_going_back(self):
        self.open('https://a.example/')
        self.open('https://b.example/')
        self.open('https://c.example/')
        self.assertEqual(self.app.browser_history, ['https://a.example/', 'https://b.example/'])
        self.assertEqual(self.app.browser_url, 'https://c.example/')

        with mock.patch.object(reader, 'fetch', self.fetch):
            self.app.browser_back()
        self.assertEqual(self.fetched[-1], 'https://b.example/')
        self.assertEqual(self.app.browser_history, ['https://a.example/'])  # going back does not push
        self.assertEqual(self.app.browser_url, 'https://b.example/')

    def test_back_from_the_first_page_shows_the_start_page_and_then_leaves(self):
        self.open('https://a.example/')
        self.assertEqual(self.app.browser_history, [])
        self.app.browser_back()
        self.assertIsNone(self.app.browser_url)
        self.assertEqual(self.title.set_text.call_args.args[0], 'Browser')
        self.app.show_screen.reset_mock()
        self.app.browser_back()
        self.app.show_screen.assert_called_once_with(self.app.screen_main)

    def test_history_is_bounded(self):
        for i in range(45):
            self.open(f'https://site{i}.example/')
        self.assertEqual(len(self.app.browser_history), 30)

    def test_redirects_update_the_current_address(self):
        self.pages['https://short.example/'] = page('https://long.example/final', 'Final')
        self.open('https://short.example/')
        self.assertEqual(self.app.browser_url, 'https://long.example/final')
        self.assertEqual(self.titles()[-1], 'Final')

    # --- errors ----------------------------------------------------------------
    def test_a_failing_page_shows_the_message_and_keeps_history_clean(self):
        self.open('https://a.example/')
        self.pages['https://broken.example/'] = reader.BrowserError('The server answered 404')
        self.open('https://broken.example/')
        self.assertEqual(self.titles()[-1], 'Cannot open page')
        self.assertEqual(self.app.browser_history, [])      # the failure was not pushed
        self.assertEqual(self.app.browser_url, 'https://a.example/')
        shown = [c.args[0] for c in LVR.label.return_value.set_text.call_args_list]
        self.assertTrue(any('404' in text for text in shown))

    def test_an_unexpected_exception_is_reported_not_raised(self):
        self.pages['https://weird.example/'] = RuntimeError('boom')
        with self.assertLogs(level='ERROR'):
            self.open('https://weird.example/')
        self.assertEqual(self.titles()[-1], 'Cannot open page')

    # --- navigating away while a page loads --------------------------------------
    def test_a_slow_page_is_dropped_when_the_user_goes_elsewhere(self):
        self.open('https://a.example/')

        def slow_fetch(url):
            self.app.browser_back()          # the user taps back while it loads
            return page(url, 'Too late')
        with mock.patch.object(reader, 'fetch', slow_fetch):
            self.app.browser_open('https://slow.example/')
        self.assertNotIn('Too late', self.titles())
        self.assertNotEqual(self.app.browser_url, 'https://slow.example/')

    def test_the_newest_request_wins_when_two_are_started(self):
        order = []

        def fetch(url):
            order.append(url)
            if url == 'https://first.example/':
                self.app.browser_open('https://second.example/')   # tapped again before the first finished
            return page(url, url)
        with mock.patch.object(reader, 'fetch', fetch):
            self.app.browser_open('https://first.example/')
        self.assertEqual(self.app.browser_url, 'https://second.example/')

    # --- limits ----------------------------------------------------------------
    def test_link_buttons_are_capped_and_the_rest_is_reported(self):
        blocks = [{'kind': 'p', 'text': f'item {i}', 'links': [(f'link {i}', f'https://x.example/{i}')]} for i in range(150)]
        self.pages['https://big.example/'] = page('https://big.example/', blocks=blocks)
        LVR.reset_mock()
        self.open('https://big.example/')
        self.assertEqual(self.count_buttons(), BrowserApp.BROWSER_MAX_LINK_BUTTONS)
        notes = [c.args[0] for c in LVR.label.return_value.set_text.call_args_list]
        self.assertTrue(any('50 more links' in text for text in notes), notes[-3:])

    def test_pages_are_drawn_in_steps_so_the_screen_keeps_responding(self):
        blocks = [{'kind': 'p', 'text': f'p{i}', 'links': []} for i in range(65)]
        self.pages['https://long.example/'] = page('https://long.example/', blocks=blocks)
        LVR.lock.reset_mock()
        self.open('https://long.example/')
        # one hold for the header, 4 for 65 blocks in steps of 20, one for the notes
        self.assertEqual(LVR.lock.call_count, 1 + 4 + 1)

    def test_empty_and_truncated_pages_get_an_explanation(self):
        self.pages['https://empty.example/'] = page('https://empty.example/', blocks=[])
        self.pages['https://long.example/'] = page('https://long.example/', truncated=True)
        for url, expected in (('https://empty.example/', 'JavaScript'), ('https://long.example/', 'long')):
            LVR.reset_mock()
            self.open(url)
            notes = [c.args[0] for c in LVR.label.return_value.set_text.call_args_list]
            self.assertTrue(any(expected in text for text in notes), (url, notes))

    def test_block_kinds_use_the_matching_widgets(self):
        blocks = [{'kind': 'h1', 'text': 'Big', 'links': []}, {'kind': 'li', 'text': 'item', 'links': []}]
        self.pages['https://k.example/'] = page('https://k.example/', blocks=blocks)
        LVR.reset_mock()
        self.open('https://k.example/')
        self.assertTrue(LVR.title.called)
        texts = [c.args[0] for c in LVR.label.return_value.set_text.call_args_list]
        self.assertIn('• item', texts)

    def test_css_colour_and_alignment_reach_the_widgets(self):
        blocks = [{'kind': 'p', 'text': 'warning', 'links': [], 'color': (255, 80, 80), 'align': 'center'},
                  {'kind': 'p', 'text': 'right', 'links': [], 'color': None, 'align': 'right'},
                  {'kind': 'p', 'text': 'plain', 'links': [], 'color': None, 'align': None}]
        self.pages['https://css.example/'] = page('https://css.example/', blocks=blocks)
        LV.reset_mock()
        self.open('https://css.example/')
        LV.color_make.assert_called_once_with(255, 80, 80)
        label = LVR.label.return_value
        aligns = [c.args[0] for c in label.set_style_text_align.call_args_list]
        self.assertEqual(aligns, [LV.TEXT_ALIGN.CENTER, LV.TEXT_ALIGN.RIGHT])


if __name__ == '__main__':
    unittest.main()
