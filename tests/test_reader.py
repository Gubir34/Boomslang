"""The touch screen browser engine: parsing, addresses, limits and errors."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'testsupport.reader',
    Path(__file__).resolve().parents[1] / 'files/3-rinkhals/opt/rinkhals/ui/reader.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def kinds(page):
    return [(b['kind'], b['text']) for b in page.blocks]


class ParseTests(unittest.TestCase):
    def test_headings_paragraphs_and_lists(self):
        page = reader.parse_html(
            '<html><head><title> My  page </title></head><body>'
            '<h1>Big</h1><p>Hello   <b>bold</b>\n world</p><h2>Sub</h2><h5>Small</h5>'
            '<ul><li>one</li><li>two</li></ul></body></html>', 'https://example.com/')
        self.assertEqual(page.title, 'My page')
        self.assertEqual(kinds(page), [('h1', 'Big'), ('p', 'Hello bold world'), ('h2', 'Sub'),
                                       ('h3', 'Small'), ('li', 'one'), ('li', 'two')])

    def test_scripts_styles_and_svg_are_dropped_but_noscript_is_shown(self):
        # nothing runs JavaScript here, so what <noscript> offers is what there is to read
        page = reader.parse_html(
            '<p>Visible</p><script>var x = "secret";</script><style>.z{color:red}</style>'
            '<noscript>needs js</noscript><svg><text>logo</text></svg><p>Also visible</p>',
            'https://example.com/')
        self.assertEqual([t for _, t in kinds(page)], ['Visible', 'needs js', 'Also visible'])

    def test_preformatted_text_keeps_its_lines(self):
        page = reader.parse_html('<pre>line one\n  indented\nline three</pre>', 'https://example.com/')
        self.assertEqual(kinds(page), [('pre', 'line one\n  indented\nline three')])

    def test_broken_markup_does_not_crash_and_keeps_what_was_read(self):
        page = reader.parse_html('<p>start <b>unclosed <i>tags <a href="/x">link</p><div>more', 'https://example.com/')
        texts = ' '.join(t for _, t in kinds(page))
        self.assertIn('start unclosed tags link', texts)
        self.assertIn('more', texts)

    def test_long_paragraphs_are_split(self):
        page = reader.parse_html('<p>' + 'word ' * 1000 + '</p>', 'https://example.com/')
        self.assertGreater(len(page.blocks), 1)
        self.assertTrue(all(len(b['text']) <= reader.MAX_BLOCK_CHARS for b in page.blocks))
        self.assertEqual(sum(len(b['text'].split()) for b in page.blocks), 1000)

    def test_block_count_is_capped(self):
        page = reader.parse_html('<p>x</p>' * (reader.MAX_BLOCKS + 50), 'https://example.com/')
        self.assertEqual(len(page.blocks), reader.MAX_BLOCKS)
        self.assertTrue(page.truncated)

    def test_title_falls_back_to_the_host(self):
        self.assertEqual(reader.parse_html('<p>x</p>', 'https://example.com/a').title, 'example.com')


class LinkTests(unittest.TestCase):
    def test_links_are_resolved_and_attached_to_their_block(self):
        page = reader.parse_html(
            '<p>See <a href="/docs">the docs</a> and <a href="https://other.org/x#frag">other</a>, '
            '<a href="rel/page">relative</a>.</p>', 'https://example.com/a/b')
        self.assertEqual(page.blocks[0]['links'], [
            ('the docs', 'https://example.com/docs'),
            ('other', 'https://other.org/x'),
            ('relative', 'https://example.com/a/rel/page')])

    def test_unusable_links_are_ignored(self):
        page = reader.parse_html(
            '<p><a href="javascript:alert(1)">js</a><a href="mailto:a@b.c">mail</a>'
            '<a href="#top">top</a><a href="ftp://x/y">ftp</a><a>no href</a>'
            '<a href="tel:123">phone</a></p>', 'https://example.com/')
        self.assertEqual(page.blocks[0]['links'], [])

    def test_image_links_use_the_alt_text_and_empty_links_the_host(self):
        page = reader.parse_html(
            '<p><a href="/home"><img src="l.png" alt="Home logo"></a><a href="https://x.org/y"></a></p>',
            'https://example.com/')
        self.assertEqual(page.blocks[0]['links'], [('Home logo', 'https://example.com/home'), ('x.org', 'https://x.org/y')])

    def test_duplicate_links_and_link_floods_are_limited(self):
        html = '<p>' + '<a href="/same">again</a>' * 5 + ''.join(f'<a href="/p{i}">p{i}</a>' for i in range(30)) + '</p>'
        links = reader.parse_html(html, 'https://example.com/').blocks[0]['links']
        self.assertEqual(len(links), reader.MAX_LINKS_PER_BLOCK)
        self.assertEqual(len({u for _, u in links}), len(links))

    def test_search_result_redirects_are_unwrapped(self):
        wrapped = '//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fpage%3Fa%3D1&rut=abc'
        page = reader.parse_html(f'<p><a href="{wrapped}">result</a></p>', 'https://html.duckduckgo.com/html/')
        self.assertEqual(page.blocks[0]['links'], [('result', 'https://example.org/page?a=1')])


class AddressTests(unittest.TestCase):
    def test_addresses(self):
        n = reader.normalize_url
        self.assertEqual(n('example.com'), 'https://example.com')
        self.assertEqual(n('  en.wikipedia.org/wiki/Snake '), 'https://en.wikipedia.org/wiki/Snake')
        self.assertEqual(n('192.168.1.102:8090'), 'http://192.168.1.102:8090')
        self.assertEqual(n('localhost:7125/server/info'), 'http://localhost:7125/server/info')
        self.assertEqual(n('printer.local'), 'http://printer.local')
        self.assertEqual(n('https://example.com/x'), 'https://example.com/x')

    def test_anything_else_is_a_search(self):
        self.assertEqual(reader.normalize_url('klipper pressure advance'),
                         reader.SEARCH_URL + 'klipper+pressure+advance')
        self.assertEqual(reader.normalize_url('snake'), reader.SEARCH_URL + 'snake')
        self.assertEqual(reader.normalize_url('what is a boomslang?'), reader.SEARCH_URL + 'what+is+a+boomslang%3F')

    def test_unsupported_and_empty_addresses(self):
        for bad in ('file:///etc/passwd', 'ftp://host/x', 'javascript:alert(1)'.replace('javascript:', 'javascript://'), '', '   '):
            with self.subTest(bad=bad), self.assertRaises(reader.BrowserError):
                reader.normalize_url(bad)


class MainContentTests(unittest.TestCase):
    def test_only_the_main_content_is_kept_when_the_page_marks_it(self):
        page = reader.parse_html(
            '<nav><ul><li>Menu one</li><li>Menu two</li></ul></nav><header><h1>Site</h1></header>'
            '<main><h1>Article</h1><p>The text.</p></main><footer><p>Copyright</p></footer>',
            'https://example.com/')
        self.assertEqual(kinds(page), [('h1', 'Article'), ('p', 'The text.')])

    def test_pages_without_main_content_markers_keep_everything(self):
        page = reader.parse_html('<div><p>One</p><p>Two</p></div>', 'https://example.com/')
        self.assertEqual([t for _, t in kinds(page)], ['One', 'Two'])

    def test_articles_inside_a_list_page_are_kept_and_chrome_dropped(self):
        page = reader.parse_html('<p>Top bar</p><article><p>Post 1</p></article><article><p>Post 2</p></article>',
                                 'https://example.com/')
        self.assertEqual([t for _, t in kinds(page)], ['Post 1', 'Post 2'])


class FakeResponse:
    def __init__(self, body=b'<p>hi</p>', status=200, ctype='text/html; charset=utf-8', url='https://example.com/',
                 encoding='utf-8'):
        self.body, self.status_code, self.url, self.encoding = body, status, url, encoding
        self.headers = {'Content-Type': ctype}
        self.closed = False
        self.bytes_served = 0

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self.body), chunk_size):
            chunk = self.body[i:i + chunk_size]
            self.bytes_served += len(chunk)
            yield chunk

    def close(self):
        self.closed = True


def fetching(response, free_kb=500000):
    return reader.fetch('https://example.com/', get=lambda *a, **k: response, available_kb=lambda: free_kb)


class FetchTests(unittest.TestCase):
    def test_a_normal_page(self):
        response = FakeResponse('<title>T</title><p>Çay ve şeker</p>'.encode('utf-8'))
        page = fetching(response)
        self.assertEqual((page.title, kinds(page)), ('T', [('p', 'Çay ve şeker')]))
        self.assertTrue(response.closed)

    def test_the_final_url_after_redirects_is_the_base_for_links(self):
        page = fetching(FakeResponse(b'<p><a href="x">x</a></p>', url='https://www.example.org/dir/'))
        self.assertEqual(page.url, 'https://www.example.org/dir/')
        self.assertEqual(page.blocks[0]['links'], [('x', 'https://www.example.org/dir/x')])

    def test_big_pages_stop_downloading_at_the_limit(self):
        response = FakeResponse(b'<p>' + b'a' * (3 * reader.MAX_BYTES) + b'</p>')
        fetching(response)
        self.assertLessEqual(response.bytes_served, reader.MAX_BYTES + 16384)
        self.assertTrue(response.closed)

    def test_plain_text_is_shown_as_preformatted_text(self):
        page = fetching(FakeResponse(b'a <b> & c\nsecond', ctype='text/plain'))
        self.assertEqual(kinds(page), [('pre', 'a <b> & c\nsecond')])

    def test_errors_have_readable_messages(self):
        cases = [
            (FakeResponse(status=404), '404'),
            (FakeResponse(ctype='application/pdf'), 'pdf'),
            (FakeResponse(ctype='image/png'), 'image/png'),
            (FakeResponse(url='ftp://example.com/'), 'unsupported'),
        ]
        for response, expected in cases:
            with self.subTest(expected=expected), self.assertRaises(reader.BrowserError) as ctx:
                fetching(response)
            self.assertIn(expected, str(ctx.exception))

    def test_network_failures_become_browser_errors(self):
        def boom(*a, **k):
            raise ConnectionError('no route')
        with self.assertRaises(reader.BrowserError) as ctx:
            reader.fetch('https://example.com/', get=boom, available_kb=lambda: 500000)
        self.assertIn('ConnectionError', str(ctx.exception))

    def test_low_memory_refuses_before_any_download(self):
        called = []
        with self.assertRaises(reader.BrowserError) as ctx:
            reader.fetch('https://example.com/', get=lambda *a, **k: called.append(1),
                         available_kb=lambda: reader.MIN_FREE_MEMORY_KB - 1)
        self.assertIn('memory', str(ctx.exception))
        self.assertEqual(called, [])

    def test_unknown_memory_does_not_block(self):
        self.assertEqual(fetching(FakeResponse(), free_kb=None).blocks[0]['text'], 'hi')

    def test_invalid_or_wrong_charset_does_not_crash(self):
        page = fetching(FakeResponse(b'<p>caf\xe9 \xff\xfe</p>', ctype='text/html; charset=bogus', encoding='bogus'))
        self.assertIn('caf', page.blocks[0]['text'])


def texts(page):
    return [b['text'] for b in page.blocks]


class CssTests(unittest.TestCase):
    def test_elements_hidden_by_the_pages_own_rules_are_left_out(self):
        page = reader.parse_html(
            '<style>.cookie-banner { display: none } #popup{visibility:hidden} li.skip{display:none!important}</style>'
            '<div class="cookie-banner"><p>Accept cookies</p></div><div id="popup">Subscribe</div>'
            '<ul><li>keep</li><li class="skip">drop</li><li class="other skip">drop too</li></ul><p>Text</p>',
            'https://example.com/')
        self.assertEqual(texts(page), ['keep', 'Text'])

    def test_inline_style_and_the_hidden_attribute_hide_too(self):
        page = reader.parse_html(
            '<p style="display:none">no</p><p hidden>no</p><div style="color:red"><p>yes</p></div>'
            '<span style="visibility: hidden">gone</span><p>end</p>', 'https://example.com/')
        self.assertEqual(texts(page), ['yes', 'end'])

    def test_hiding_covers_the_whole_subtree_and_ends_with_the_element(self):
        page = reader.parse_html(
            '<div style="display:none"><div><p>deep <b>in</b> it</p><ul><li>x</li></ul></div></div>'
            '<p>after</p><div hidden><p>one</p></div><p>last</p>', 'https://example.com/')
        self.assertEqual(texts(page), ['after', 'last'])

    def test_hidden_void_elements_and_misnested_tags_keep_the_stack_balanced(self):
        page = reader.parse_html(
            '<div style="display:none"><br><img src=x alt=pic><input><p>gone</div>'
            '<p>visible <b>one</p><div hidden>x</i></div><p>visible two</p>', 'https://example.com/')
        self.assertEqual(texts(page), ['visible one', 'visible two'])

    def test_rules_are_simple_and_unsupported_selectors_do_nothing(self):
        css = ('@media (max-width:600px){.a{display:none}} @import url(x.css);'
               'div p{display:none} a:hover{display:none} .b > .c{display:none} p.keep{color:#ffd700} ,{}')
        rules = reader.parse_css(css)
        self.assertEqual([(t, c, i) for t, c, i, _ in rules], [('p', ['keep'], None)])

    def test_media_query_rules_are_ignored(self):
        page = reader.parse_html('<style>@media print{.hide{display:none}}</style><p class="hide">shown</p>',
                                 'https://example.com/')
        self.assertEqual(texts(page), ['shown'])

    def test_colour_and_centring_reach_the_block(self):
        page = reader.parse_html(
            '<style>.warn{color:#ff5050} .mid{text-align:center}</style>'
            '<p class="warn">red</p><div class="mid"><p>centred</p></div><p>plain</p>', 'https://example.com/')
        self.assertEqual([(b['text'], b['color'], b['align']) for b in page.blocks],
                         [('red', (255, 80, 80), None), ('centred', None, 'center'), ('plain', None, None)])

    def test_dark_colours_are_ignored_on_the_dark_screen(self):
        page = reader.parse_html('<p style="color:#222">dark</p><p style="color:navy">navy</p><p style="color:#ccc">light</p>',
                                 'https://example.com/')
        self.assertEqual([b['color'] for b in page.blocks], [None, None, (204, 204, 204)])

    def test_colour_parsing(self):
        c = reader.parse_color
        self.assertEqual(c('#ffd700'), (255, 215, 0))
        self.assertEqual(c('#fff'), (255, 255, 255))
        self.assertEqual(c('rgb(200, 200, 200)'), (200, 200, 200))
        self.assertEqual(c('rgba(200,200,200,0.5)'), (200, 200, 200))
        self.assertEqual(c('orange'), (255, 165, 0))
        for unusable in ('', None, 'black', '#000', 'inherit', 'var(--x)', 'rgb(1,2,3)'):
            self.assertIsNone(c(unusable), unusable)

    def test_huge_stylesheets_are_bounded(self):
        css = ''.join(f'.c{i}{{display:none}}' for i in range(reader.MAX_CSS_RULES * 3))
        self.assertLessEqual(len(reader.parse_css(css)), reader.MAX_CSS_RULES)


class RedirectTests(unittest.TestCase):
    def test_meta_refresh(self):
        page = reader.parse_html('<meta http-equiv="Refresh" content="0; url=/new/place">', 'https://example.com/old')
        self.assertEqual(page.redirect, 'https://example.com/new/place')
        slow = reader.parse_html('<meta http-equiv="refresh" content="60; url=/later">', 'https://example.com/')
        self.assertIsNone(slow.redirect)
        reload_only = reader.parse_html('<meta http-equiv="refresh" content="5">', 'https://example.com/')
        self.assertIsNone(reload_only.redirect)

    def test_a_script_that_only_redirects(self):
        for script in ('window.location = "/go"', "location.href='/go';", 'window.location.href = "/go";',
                       'document.location="/go"', 'top.location.replace("/go")', 'location.assign( "/go" );'):
            with self.subTest(script=script):
                page = reader.parse_html(f'<script>{script}</script><p>Redirecting</p>', 'https://example.com/a')
                self.assertEqual(page.redirect, 'https://example.com/go')

    def test_scripts_with_logic_are_never_guessed_at(self):
        for script in ('if (mobile) { location.href = "/m" }', 'setTimeout(function(){ location = "/x" }, 100)',
                       'var u = "/x"; location = u', 'location.href = base + "/x"', 'console.log(1)',
                       'location = "/a" + suffix',            # would go to /a, not where the script means
                       'location.href = "/x"; track();',      # does more than redirect
                       'location.replace("/x") || fallback()'):
            with self.subTest(script=script):
                page = reader.parse_html(f'<script>{script}</script><p>text</p>', 'https://example.com/')
                self.assertIsNone(page.redirect)

    def test_unusable_redirect_targets_are_dropped(self):
        for target in ('javascript:void(0)', 'mailto:a@b.c', 'ftp://x/y'):
            page = reader.parse_html(f'<meta http-equiv="refresh" content="0;url={target}">', 'https://example.com/')
            self.assertIsNone(page.redirect, target)

    def test_script_text_does_not_leak_into_the_page(self):
        page = reader.parse_html('<script>window.location = "/go"</script><p>Hello</p>', 'https://example.com/')
        self.assertEqual(texts(page), ['Hello'])


class FollowRedirectTests(unittest.TestCase):
    def serve(self, pages):
        calls = []

        def get(url, **kwargs):
            calls.append(url)
            return FakeResponse(pages[url].encode(), url=url)
        return get, calls

    def test_fetch_follows_a_redirect_to_the_real_page(self):
        get, calls = self.serve({
            'https://a.example/': '<meta http-equiv="refresh" content="0;url=https://b.example/home">',
            'https://b.example/home': '<title>Real</title><p>content</p>'})
        page = reader.fetch('https://a.example/', get=get, available_kb=lambda: None)
        self.assertEqual((page.title, page.url, calls), ('Real', 'https://b.example/home', ['https://a.example/', 'https://b.example/home']))

    def test_redirect_loops_stop(self):
        get, calls = self.serve({
            'https://a.example/': '<meta http-equiv="refresh" content="0;url=https://b.example/">',
            'https://b.example/': '<meta http-equiv="refresh" content="0;url=https://a.example/">'})
        page = reader.fetch('https://a.example/', get=get, available_kb=lambda: None)
        self.assertEqual(calls, ['https://a.example/', 'https://b.example/'])
        self.assertEqual(page.url, 'https://b.example/')

    def test_long_redirect_chains_stop_at_the_limit(self):
        pages = {f'https://s{i}.example/': f'<meta http-equiv="refresh" content="0;url=https://s{i + 1}.example/">'
                 for i in range(10)}
        get, calls = self.serve(pages)
        reader.fetch('https://s0.example/', get=get, available_kb=lambda: None)
        self.assertEqual(len(calls), reader.MAX_REDIRECTS + 1)

    def test_memory_is_checked_before_every_hop(self):
        get, calls = self.serve({'https://a.example/': '<meta http-equiv="refresh" content="0;url=https://b.example/">'})
        readings = iter([500000, 1000])
        with self.assertRaises(reader.BrowserError):
            reader.fetch('https://a.example/', get=get, available_kb=lambda: next(readings))
        self.assertEqual(calls, ['https://a.example/'])


if __name__ == '__main__':
    unittest.main()
