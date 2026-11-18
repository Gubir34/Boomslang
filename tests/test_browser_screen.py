"""Logic of the touch screen browser (history, cancelling, errors, limits).

rinkhals-ui.py cannot be imported without the LVGL library, so the browser
methods are cut out of the real file with ast and run against stand-in
widgets. What this does not check is how the screen looks.
"""
import ast
import importlib.util
import sys
import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

UI = Path(__file__).resolve().parents[1] / 'files/3-rinkhals/opt/rinkhals/ui'
sys.path.insert(0, str(UI))   # reader imports reader_css
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
    import home_tools
    # Bookmarks go to a folder of this test run, not to the printer's path
    home_tools.BOOKMARKS_PATH = str(Path(tempfile.mkdtemp()) / 'bookmarks.json')
    namespace = {'lv': lv, 'lvr': lvr, 'reader': reader, 'logging': logging, 'home_tools': home_tools,
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
        self.app.show_qr_dialog = mock.MagicMock()
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

    def search(self, url):
        self.fetched.append(url)
        result = self.pages.get(url, [])
        if isinstance(result, Exception):
            raise result
        return result

    def open(self, target, **kwargs):
        with mock.patch.object(reader, 'fetch', self.fetch), mock.patch.object(reader, 'search', self.search):
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
        self.assertEqual(self.title.set_text.call_args.args[0], 'LemSearch Lite')
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
            if url == 'https://slow.example/':
                self.app.browser_back()      # the user taps back while it loads
                return page(url, 'Too late')
            return page(url, 'Page A')
        with mock.patch.object(reader, 'fetch', slow_fetch):
            self.app.browser_open('https://slow.example/')
        self.assertNotIn('Too late', self.titles())
        # back returned to the page the link was tapped on, not past it
        self.assertEqual(self.app.browser_url, 'https://a.example/')
        self.assertEqual(self.titles()[-1], 'Page A')
        self.assertEqual(self.app.browser_history, [])

    def test_back_after_a_failed_link_returns_to_the_page_it_was_tapped_on(self):
        self.open('https://a.example/')
        self.open('https://b.example/')
        self.pages['https://broken.example/'] = reader.BrowserError('The server answered 500')
        self.open('https://broken.example/')
        self.fetched.clear()
        with mock.patch.object(reader, 'fetch', self.fetch):
            self.app.browser_back()
        self.assertEqual(self.fetched, ['https://b.example/'])   # not a.example, one page too far
        self.assertEqual(self.app.browser_history, ['https://a.example/'])
        with mock.patch.object(reader, 'fetch', self.fetch):
            self.app.browser_back()
        self.assertEqual(self.fetched[-1], 'https://a.example/')

    def test_try_again_after_a_failed_link_keeps_the_history(self):
        self.open('https://a.example/')
        self.pages['https://flaky.example/'] = reader.BrowserError('Could not reach the page: Timeout')
        self.open('https://flaky.example/')
        retry = [c for c in LVR.button.return_value.add_event_cb.call_args_list][-1].args[0]
        del self.pages['https://flaky.example/']
        with mock.patch.object(reader, 'fetch', self.fetch):
            retry(None)
        self.assertEqual(self.app.browser_url, 'https://flaky.example/')
        self.assertEqual(self.app.browser_history, ['https://a.example/'])

    def test_a_render_that_lost_the_race_draws_nothing(self):
        # The page arrived, then a tap started another navigation before the
        # render thread got the lock: nothing may be added to the old panel
        self.open('https://a.example/')
        stale_gen = self.app.browser_gen
        self.app.browser_gen += 1
        labels_before = LVR.label.call_count
        self.app.browser_render(page('https://late.example/', 'Late'), None, 'https://late.example/', True, stale_gen)
        self.assertEqual(LVR.label.call_count, labels_before)
        self.assertNotIn('Late', self.titles())
        self.assertEqual(self.app.browser_url, 'https://a.example/')

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
        self.assertEqual(self.count_buttons(), BrowserApp.BROWSER_MAX_LINK_BUTTONS + 1)   # + the bookmark button
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
        for url, expected in (('https://empty.example/', 'full browser'), ('https://long.example/', 'long')):
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


    # --- long pages, forms, bookmarks ---------------------------------------------
    def button_texts(self):
        return [c.args[0] for c in LVR.button.return_value.set_text.call_args_list]

    def test_a_long_page_is_shown_in_parts(self):
        per_part = BrowserApp.BROWSER_BLOCKS_PER_PART
        blocks = [{'kind': 'p', 'text': f'paragraph {i}', 'links': []} for i in range(per_part * 2 + 10)]
        self.pages['https://long.example/'] = page('https://long.example/', blocks=blocks)
        LVR.reset_mock()
        self.open('https://long.example/')
        shown = [c.args[0] for c in LVR.label.return_value.set_text.call_args_list]
        self.assertIn('paragraph 0', shown)
        self.assertNotIn(f'paragraph {per_part}', shown)                 # the next part is not drawn yet
        self.assertIn('Continue reading (part 2 of 3)', self.button_texts())
        self.assertNotIn('Bookmark this page', self.button_texts())      # that comes at the end of the page

        LVR.reset_mock()
        self.app.browser_show_part(per_part)
        shown = [c.args[0] for c in LVR.label.return_value.set_text.call_args_list]
        self.assertIn(f'paragraph {per_part}', shown)
        self.assertNotIn('paragraph 0', shown)
        self.assertIn('Previous part (1 of 3)', self.button_texts())
        self.assertIn('Continue reading (part 3 of 3)', self.button_texts())
        self.assertEqual(self.app.browser_history, [])                   # moving inside a page is not history

        LVR.reset_mock()
        self.app.browser_show_part(per_part * 2)
        self.assertIn('Bookmark this page', self.button_texts())
        self.assertNotIn('Continue reading (part 4 of 3)', self.button_texts())

    def test_a_search_form_asks_for_text_and_opens_the_result(self):
        form = {'action': 'https://wiki.example/w/index.php', 'name': 'search', 'fields': [('title', 'Special:Search')]}
        self.pages['https://wiki.example/'] = page('https://wiki.example/', blocks=[
            {'kind': 'form', 'text': 'Search the wiki', 'links': [], 'form': form}, {'kind': 'p', 'text': 'x', 'links': []}])
        self.open('https://wiki.example/')
        self.assertIn('Search the wiki...', self.button_texts())
        self.app.browser_form(form, 'Search the wiki')
        title, initial, is_number, callback = self.app.show_input_text_dialog.call_args.args
        self.assertEqual(title, 'Search the wiki')
        with mock.patch.object(reader, 'fetch', self.fetch):
            callback('pressure advance')
            callback('')                                                 # nothing typed: nothing opened
        self.assertEqual(self.fetched[-1], 'https://wiki.example/w/index.php?title=Special%3ASearch&search=pressure+advance')
        self.assertEqual(len(self.fetched), 2)

    def test_bookmarking_a_page_puts_it_on_the_start_page(self):
        import home_tools
        home_tools.save_bookmarks([])
        self.pages['https://docs.example/'] = page('https://docs.example/', title='The docs')
        self.open('https://docs.example/')
        self.assertEqual(self.app.browser_bookmark_text('https://docs.example/'), 'Bookmark this page')
        home_tools.toggle_bookmark('The docs', 'https://docs.example/')
        self.assertEqual(self.app.browser_bookmark_text('https://docs.example/'), 'Remove bookmark')
        LVR.reset_mock()
        self.app.browser_start_page()
        self.assertEqual(self.button_texts()[1], 'The docs')             # right after "Open an address"
        self.assertEqual(self.count_buttons(), 2 + len(BrowserApp.BROWSER_BOOKMARKS))
        home_tools.toggle_bookmark('The docs', 'https://docs.example/')
        self.assertEqual(home_tools.load_bookmarks(), [])

    def test_a_default_bookmark_saved_by_the_user_is_not_listed_twice(self):
        import home_tools
        name, url = BrowserApp.BROWSER_BOOKMARKS[0]
        home_tools.save_bookmarks([(name, url)])
        LVR.reset_mock()
        self.app.browser_start_page()
        self.assertEqual(self.count_buttons(), 1 + len(BrowserApp.BROWSER_BOOKMARKS))
        home_tools.save_bookmarks([])

    def test_pages_read_from_script_data_say_so(self):
        data_page = page('https://app.example/')
        data_page.from_data = True
        self.pages['https://app.example/'] = data_page
        LVR.reset_mock()
        self.open('https://app.example/')
        shown = [c.args[0] for c in LVR.label.return_value.set_text.call_args_list]
        self.assertTrue(any('JavaScript' in text for text in shown))

    def test_page_styles_reach_the_label(self):
        blocks = [{'kind': 'p', 'text': 'old price', 'links': [], 'decor': 'strike'},
                  {'kind': 'p', 'text': 'notice', 'links': [], 'bg': (255, 243, 205)},
                  {'kind': 'p', 'text': 'large', 'links': [], 'big': True}]
        self.pages['https://styled.example/'] = page('https://styled.example/', blocks=blocks)
        LVR.reset_mock()
        LV.reset_mock()
        self.open('https://styled.example/')
        label = LVR.label.return_value
        label.set_style_text_decor.assert_called_once_with(LV.TEXT_DECOR.STRIKETHROUGH, LV.STATE.DEFAULT)
        label.set_style_bg_color.assert_called_once()
        LV.color_make.assert_any_call(255, 243, 205)
        LV.color_make.assert_any_call(0, 0, 0)                           # dark text on the light box
        self.assertIn(mock.call('large'), LVR.title.return_value.set_text.call_args_list)

if __name__ == '__main__':
    unittest.main()

    # --- LemSearch Lite: results as cards, the phone for sites that refuse simple browsers ---

    def test_search_results_are_cards_that_open_their_page(self):
        url = reader.SEARCH_URL + 'benchy'
        self.pages[url] = [{'title': 'Benchy', 'url': 'https://www.3dbenchy.com/', 'domain': 'www.3dbenchy.com',
                            'snippet': 'The jolly torture test'}]
        LVR.reset_mock()
        self.open('benchy')
        self.assertEqual(self.fetched, [url])
        texts = [c.args[0] for c in LVR.label.return_value.set_text.call_args_list]
        self.assertIn('Benchy', texts)
        self.assertEqual(self.app.browser_url, url)
        # tapping the card opens the result's page
        card = LVR.button.return_value
        callbacks = [c.args[0] for c in card.add_event_cb.call_args_list]
        with mock.patch.object(reader, 'fetch', self.fetch):
            callbacks[-1](None)
        self.assertEqual(self.fetched[-1], 'https://www.3dbenchy.com/')

    def test_an_empty_search_says_so(self):
        LVR.reset_mock()
        self.open('zzqx nothing')
        notes = [c.args[0] for c in LVR.label.return_value.set_text.call_args_list]
        self.assertTrue(any('Nothing found' in n for n in notes), notes)

    def test_a_site_that_refuses_simple_browsers_offers_the_phone(self):
        self.pages['https://www.printables.com/'] = reader.BlockedError('This site does not let simple browsers in (403).')
        self.open('https://www.printables.com/')
        self.assertIn('Needs a full browser', self.titles())
        buttons = LVR.button.return_value
        labels = [c.args[0] for c in buttons.set_text.call_args_list]
        self.assertIn('Open on your phone', labels)
        phone = [c.args[0] for c in buttons.add_event_cb.call_args_list]
        for callback in phone:
            callback(None)
        self.app.show_qr_dialog.assert_called()
        self.assertEqual(self.app.show_qr_dialog.call_args.args[0], 'https://www.printables.com/')
