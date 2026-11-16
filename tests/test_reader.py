"""The touch screen browser engine: parsing, addresses, limits and errors."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'files/3-rinkhals/opt/rinkhals/ui'))   # reader imports reader_css
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

    def test_unwrapped_search_results_are_decoded_only_once(self):
        # The target's own escapes (%26 = &, %23 = #, %2B = +) must survive:
        # decoding twice turned q=a%26b into q=a&b, a different query
        target = 'https://example.org/s?q=a%26b%2Bc%23d'
        from urllib.parse import quote
        wrapped = 'https://duckduckgo.com/l/?uddg=' + quote(target, safe='')
        self.assertEqual(reader.clean_link(wrapped), target)

    def test_unclosed_options_do_not_hide_the_rest_of_the_page(self):
        # </option> is optional in HTML, so pages often leave it out
        page = reader.parse_html(
            '<p>before</p><select><option>A<option>B</select><p>after one</p><p>after two</p>',
            'https://example.com/')
        self.assertEqual([b['text'] for b in page.blocks], ['before', 'after one', 'after two'])


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

    def test_meta_charset_is_used_when_the_header_names_none(self):
        body = '<meta charset="windows-1254"><p>Çay şeker ığ</p>'.encode('cp1254')
        page = fetching(FakeResponse(body, ctype='text/html', encoding='ISO-8859-1'))
        self.assertEqual(kinds(page), [('p', 'Çay şeker ığ')])

    def test_repeated_css_matches_give_the_same_result(self):
        html = '<style>.w{color:#ff5050}</style>' + '<p class="w">a</p>' * 3 + '<p class="w" style="text-align:center">b</p>'
        page = reader.parse_html(html, 'https://example.com/')
        self.assertEqual([b['color'] for b in page.blocks], [(255, 80, 80)] * 4)
        self.assertEqual(page.blocks[3]['align'], 'center')
        self.assertIsNone(page.blocks[0]['align'])

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

    def test_unsupported_selectors_do_nothing(self):
        # Applying a :hover or sibling rule to everything would hide what the page shows
        css = ('@import url(x.css); a:hover{display:none} p::before{display:none} li:nth-child(2){display:none} '
               'h1 + p{display:none} h1 ~ p{display:none} p.keep{color:#ffd700} ,{} @font-face{font-family:x}')
        rules = reader.parse_css(css)
        self.assertEqual([(t, c, i) for t, c, i, _ in rules], [('p', ['keep'], None)])

    def test_rules_without_anything_of_use_are_not_kept(self):
        rules = reader.parse_css('.a{margin:0;padding:4px} .b{border:1px solid red} .c{font-family:x;color:#fff}')
        self.assertEqual([(c, props) for _, c, _, props in rules], [(['c'], {'color': '#fff'})])

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
                       'document.location="/go"', 'top.location.replace("/go")', 'location.assign( "/go" );',
                       # the only thing inside a short timer or onload
                       'setTimeout(function(){ location = "/go" }, 100)', 'setTimeout(() => { location.href="/go"; }, 0);',
                       'window.onload = function() { window.location.replace("/go"); };'):
            with self.subTest(script=script):
                page = reader.parse_html(f'<script>{script}</script><p>Redirecting</p>', 'https://example.com/a')
                self.assertEqual(page.redirect, 'https://example.com/go')

    def test_scripts_with_logic_are_never_guessed_at(self):
        for script in ('if (mobile) { location.href = "/m" }', 'setTimeout(function(){ location = "/x" }, 60000)',
                       'setTimeout(function(){ if (a) location = "/x" }, 100)',
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



def html(style, body):
    return reader.parse_html(f'<style>{style}</style>{body}', 'https://example.com/')


class CssSelectorTests(unittest.TestCase):
    def test_descendant_and_child_selectors(self):
        page = html('nav a{display:none} .card > p{display:none} #side ul li.x{display:none}',
                    '<nav><ul><li><a href="/a">menu</a></li></ul></nav><p><a href="/b">kept link</a></p>'
                    '<div class="card"><p>direct child</p><div><p>grandchild stays</p></div></div>'
                    '<div id="side"><ul><li class="x">gone</li><li>stays</li></ul></div>'
                    '<ul><li class="x">outside the sidebar</li></ul>')
        self.assertEqual(texts(page), ['kept link', 'grandchild stays', 'stays', 'outside the sidebar'])

    def test_compound_and_attribute_selectors(self):
        page = html('p.a.b{display:none} [aria-hidden=true]{display:none} a[href^="/ad"]{display:none} '
                    'div[data-role~=banner]{display:none} [hidden-ish]{display:none}',
                    '<p class="a">only a</p><p class="b a c">a and b</p><span aria-hidden="true">icon</span>'
                    '<p><a href="/ads/1">ad</a> <a href="/page">page</a></p>'
                    '<div data-role="top banner">banner</div><div data-role="bannerish">not a banner</div>'
                    '<p hidden-ish>flagged</p><p>end</p>')
        self.assertEqual(texts(page), ['only a', 'page', 'not a banner', 'end'])
        self.assertEqual(page.blocks[1]['links'], [('page', 'https://example.com/page')])

    def test_specificity_beats_source_order(self):
        page = html('#intro{display:block} p.note{display:block} .note{display:none} p{display:none}',
                    '<p id="intro">id wins</p><p class="note">class with tag wins</p><p>plain is hidden</p>'
                    '<div class="note">only the class rule applies</div>')
        self.assertEqual(texts(page), ['id wins', 'class with tag wins'])

    def test_important_beats_specificity_and_inline_style(self):
        page = html('p{display:none !important} #a{display:block} .c{color:#ff5050!important}',
                    '<p id="a">hidden anyway</p><p style="display:block">inline loses too</p>'
                    '<div class="c" style="color:#00ff00">forced red</div>'
                    '<div style="color:#00ff00 !important" class="c">inline important wins</div>')
        self.assertEqual([(b['text'], b['color']) for b in page.blocks],
                         [('forced red', (255, 80, 80)), ('inline important wins', (0, 255, 0))])

    def test_later_rule_wins_at_equal_specificity(self):
        page = html('.x{display:none} .x{display:block} .y{display:block} .y{display:none}',
                    '<p class="x">shown</p><p class="y">hidden</p>')
        self.assertEqual(texts(page), ['shown'])

    def test_root_and_universal_selectors(self):
        page = reader.parse_html('<html><head><style>:root{color:#ffd700} * {text-align:center}</style></head>'
                                 '<body><p>text</p></body></html>', 'https://example.com/')
        self.assertEqual((page.blocks[0]['color'], page.blocks[0]['align']), ((255, 215, 0), 'center'))

    def test_rules_filed_under_an_id_still_check_their_classes(self):
        page = html('#box.closed{display:none}', '<div id="box" class="open">open</div><p>end</p>')
        self.assertEqual(texts(page), ['open', 'end'])


class CssMediaAndVariableTests(unittest.TestCase):
    def test_the_screen_is_a_small_dark_one(self):
        m = reader.media_matches
        for query in ('screen', 'all', 'only screen and (max-width: 600px)', '(min-width: 320px)',
                      '(prefers-color-scheme: dark)', 'print, screen', 'not print', '(width <= 600px)',
                      '(hover: none)', 'screen and (min-width:20em) and (max-width:40em)'):
            self.assertTrue(m(query), query)
        for query in ('print', '(min-width: 768px)', '(prefers-color-scheme: light)', 'speech',
                      'screen and (min-width: 1024px)', 'not screen', '(width >= 900px)',
                      '(600px <= width)', '(some-new-feature: yes)'):
            self.assertFalse(m(query), query)

    def test_phone_layout_rules_apply_and_desktop_ones_do_not(self):
        page = html('@media (max-width: 600px){ .desktop-menu{display:none} } '
                    '@media (min-width: 900px){ .mobile-note{display:none} } '
                    '@media print { p{display:none} } @supports (display:grid){ .old{display:none} }',
                    '<div class="desktop-menu">big menu</div><p class="mobile-note">shown on phones</p>'
                    '<p class="old">old browsers only</p><p>text</p>')
        self.assertEqual(texts(page), ['shown on phones', 'text'])

    def test_a_pages_dark_mode_is_used(self):
        page = html('p{color:#111} @media (prefers-color-scheme: dark){ p{color:#eeeeee} }', '<p>readable</p>')
        self.assertEqual(page.blocks[0]['color'], (238, 238, 238))

    def test_style_elements_for_print_are_skipped(self):
        page = reader.parse_html('<style media="print">p{display:none}</style><p>shown</p>', 'https://example.com/')
        self.assertEqual(texts(page), ['shown'])

    def test_variables(self):
        page = html(':root{--accent:#ffd700; --quiet: var(--missing, #cccccc)} '
                    '.a{color:var(--accent)} .b{color:var(--quiet)} .c{color:var(--nope, orange)} .d{color:var(--nope)}',
                    '<p class="a">a</p><p class="b">b</p><p class="c">c</p><p class="d">d</p>')
        self.assertEqual([b['color'] for b in page.blocks], [(255, 215, 0), (204, 204, 204), (255, 165, 0), None])

    def test_comments_and_nested_blocks_do_not_confuse_the_parser(self):
        page = html('/* .x{display:none} */ @keyframes spin{from{opacity:0}to{opacity:1}} '
                    '@media screen{ @media (max-width:900px){ .y{display:none} } } } .z{display:none}',
                    '<p class="x">x</p><p class="y">y</p><p class="z">z</p><p>end</p>')
        self.assertEqual(texts(page), ['x', 'end'])


class CssEffectTests(unittest.TestCase):
    def test_visually_hidden_text_is_left_out(self):
        page = html('.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)} '
                    '.off{position:absolute;left:-9999px} .gone{opacity:0} .zero{height:0;overflow:hidden} '
                    '.clip{position:absolute;clip-path:inset(50%)} .faint{opacity:0.5} .low{left:-5px;position:absolute}',
                    '<a class="sr-only" href="#main">Skip to content</a><p class="off">off screen</p>'
                    '<p class="gone">transparent</p><div class="zero">collapsed</div><span class="clip">clipped</span>'
                    '<p class="faint">half visible</p><p class="low">nudged</p>')
        self.assertEqual(texts(page), ['half visible', 'nudged'])

    def test_text_transform(self):
        page = html('.u{text-transform:uppercase} .l{text-transform:lowercase} .c{text-transform:capitalize}',
                    '<p class="u">Make me loud</p><p class="l">QUIET Please</p><p class="c">the printer\'s own page</p>'
                    '<div class="u"><p>inherited</p></div>')
        self.assertEqual(texts(page), ['MAKE ME LOUD', 'quiet please', "The Printer's Own Page", 'INHERITED'])

    def test_decoration_background_and_size(self):
        page = html('.old{text-decoration:line-through} .u{text-decoration-line:underline} '
                    '.note{background-color:#fff3cd} .big{font-size:28px} .em{font-size:2em} .small{font-size:12px} '
                    'body{background:#ffffff}',
                    '<p class="old">old price</p><p class="u">underlined</p><p class="note">a notice</p>'
                    '<p class="big">large</p><p class="em">also large</p><p class="small">small</p>'
                    '<p><a href="/x" style="text-decoration:underline">a link is not underlined text</a></p>')
        blocks = page.blocks
        self.assertEqual(blocks[0].get('decor'), 'strike')
        self.assertEqual(blocks[1].get('decor'), 'underline')
        self.assertEqual(blocks[2].get('bg'), (255, 243, 205))
        self.assertTrue(blocks[3].get('big') and blocks[4].get('big'))
        self.assertFalse(blocks[5].get('big'))
        self.assertIsNone(blocks[6].get('decor'))
        self.assertTrue(all('bg' not in b for b in blocks if b is not blocks[2]))   # the body's white is not used

    def test_white_space_pre_keeps_lines(self):
        page = html('.code{white-space:pre}', '<div class="code">line one\n  line two</div><div>line one\n  line two</div>')
        self.assertEqual(page.blocks[0]['kind'], 'pre')
        self.assertEqual(texts(page), ['line one\n  line two', 'line one line two'])

    def test_display_changes_what_starts_a_new_line(self):
        menu = html('nav li{display:inline}', '<nav><ul><li><a href="/a">Home</a></li><li><a href="/b">Docs</a></li>'
                    '<li><a href="/c">About</a></li></ul></nav>')
        self.assertEqual(texts(menu), ['Home Docs About'])         # one line, not three
        self.assertEqual(len(menu.blocks[0]['links']), 3)
        blocks = html('span.row{display:block}', '<p><span class="row">first</span><span class="row">second</span></p>')
        self.assertEqual(texts(blocks), ['first', 'second'])
        heading = html('h2{display:inline-block}', '<h2>Title</h2><p>text</p>')
        self.assertEqual(texts(heading), ['Title', 'text'])           # headings stay blocks


class StylesheetLinkTests(unittest.TestCase):
    def test_only_screen_stylesheets_are_found_and_only_a_few(self):
        head = ('<link rel="stylesheet" href="/a.css"><link rel=stylesheet href=b.css media="print">'
                '<link rel="icon" href="/favicon.ico"><link href="https://cdn.example/c.css?v=1&amp;x=2" rel="stylesheet">'
                '<link rel="alternate stylesheet" href="/alt.css"><link rel="stylesheet" href="/d.css">'
                '<link rel="stylesheet" href="data:text/css,x">')
        self.assertEqual(reader.stylesheet_links(head, 'https://example.com/dir/page'),
                         ['https://example.com/a.css', 'https://cdn.example/c.css?v=1&x=2'])

    def test_external_stylesheets_are_fetched_and_applied(self):
        calls = []

        def get(url, **kwargs):
            calls.append(url)
            if url.endswith('.css'):
                return FakeResponse(b'.cookie{display:none} p{color:#ffd700}', ctype='text/css')
            return FakeResponse(b'<link rel="stylesheet" href="/site.css"><div class="cookie">Accept?</div><p>Hello</p>')
        page = reader.fetch('https://example.com/', get=get, available_kb=lambda: None)
        self.assertEqual(calls, ['https://example.com/', 'https://example.com/site.css'])
        self.assertEqual([(b['text'], b['color']) for b in page.blocks], [('Hello', (255, 215, 0))])

    def test_a_stylesheet_that_fails_does_not_break_the_page(self):
        def get(url, **kwargs):
            if url.endswith('.css'):
                raise OSError('timeout')
            return FakeResponse(b'<link rel="stylesheet" href="/site.css"><p>Hello</p>')
        page = reader.fetch('https://example.com/', get=get, available_kb=lambda: None)
        self.assertEqual(texts(page), ['Hello'])


class ScriptTests(unittest.TestCase):
    def test_document_write_of_a_fixed_string(self):
        page = reader.parse_html(
            '<p>before</p><script>document.write("<p>written <b>text<\\/b> &amp; \\"more\\"</p>");</script>'
            "<script>document.write('<p>single \\u00e9</p>')</script>"
            '<script>document.write("<p>" + name + "</p>")</script><p>after</p>', 'https://example.com/')
        self.assertEqual(texts(page), ['before', 'written text & "more"', 'single é', 'after'])

    def test_onclick_navigation_becomes_a_link(self):
        page = reader.parse_html(
            '<p><button onclick="location.href=\'/download\'">Download</button></p>'
            '<div onclick="window.location = \'/card\'"><span>Open the card</span></div>'
            '<p><a href="javascript:void(0)" onclick="window.open(\'/popup\')">Popup</a></p>'
            '<p><input type="button" value="Next page" onclick="location.assign(\'/next\')"></p>'
            '<p><button onclick="doSomething()">No link</button></p>', 'https://example.com/')
        links = [link for b in page.blocks for link in b['links']]
        self.assertEqual(links, [('Download', 'https://example.com/download'), ('Open the card', 'https://example.com/card'),
                                 ('Popup', 'https://example.com/popup'), ('Next page', 'https://example.com/next')])

    def test_pages_drawn_by_scripts_show_the_text_in_their_data(self):
        article = 'The quick brown fox jumps over the lazy dog and keeps running through the forest until night falls. ' * 2
        page = reader.parse_html(
            '<div id="root"></div><script type="application/ld+json">'
            + json.dumps({'@type': 'NewsArticle', 'headline': 'A fox on the run', 'articleBody': article + '\n\nSecond paragraph of the article, also long enough to count as real prose for the reader.',
                          'url': 'https://example.com/a', 'image': {'url': 'https://example.com/i.jpg'}})
            + '</script>', 'https://example.com/')
        self.assertTrue(page.from_data)
        self.assertEqual(page.blocks[0], {'kind': 'h2', 'text': 'A fox on the run', 'main': False, 'links': [],
                                          'color': None, 'align': None})
        self.assertEqual(len(page.blocks), 3)
        self.assertTrue(page.blocks[2]['text'].startswith('Second paragraph'))

    def test_next_data_and_state_assignments(self):
        body = 'This printer profile has been tuned for fast and quiet printing of small parts at a low layer height. '
        nextjs = reader.parse_html(
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps({'props': {'pageProps': {'post': {'title': 'Tuned profile', 'content': '<p>' + body + '</p>'},
                                                    'token': 'x' * 300}}})
            + '</script>', 'https://example.com/')
        self.assertEqual(texts(nextjs), ['Tuned profile', body.strip()])
        state = reader.parse_html(
            '<script>window.__INITIAL_STATE__ = ' + json.dumps({'items': [{'name': 'Item', 'description': body}]}) + ';</script>',
            'https://example.com/')
        self.assertEqual(texts(state), ['Item', body.strip()])

    def test_data_is_not_used_when_the_page_has_its_own_text(self):
        long = 'Real page text that is certainly long enough to stand on its own without any help. ' * 8
        page = reader.parse_html(
            f'<p>{long}</p><script type="application/ld+json">'
            + json.dumps({'description': 'A description that would only repeat what the page already says in its text. ' * 2})
            + '</script>', 'https://example.com/')
        self.assertFalse(page.from_data)
        self.assertEqual(len(page.blocks), 1)

    def test_broken_or_huge_data_is_ignored(self):
        page = reader.parse_html('<script type="application/json">{not json</script>'
                                 '<script type="application/json">' + json.dumps({'t': 'word ' * 80000}) + '</script><p>ok</p>',
                                 'https://example.com/')
        self.assertEqual(texts(page), ['ok'])


class FormTests(unittest.TestCase):
    def test_a_search_form_becomes_a_block_and_builds_the_address(self):
        page = reader.parse_html(
            '<form action="/w/index.php?stale=1" method="get"><input type="hidden" name="title" value="Special:Search">'
            '<input type="search" name="search" placeholder="Search Wikipedia"><input type="checkbox" name="fulltext" checked>'
            '<input type="checkbox" name="off"><input type="submit" value="Go"></form><p>text</p>',
            'https://en.example.org/wiki/Main')
        form = page.blocks[0]
        self.assertEqual((form['kind'], form['text']), ('form', 'Search Wikipedia'))
        self.assertEqual(reader.submit_url(form['form'], 'pressure advance & more'),
                         'https://en.example.org/w/index.php?title=Special%3ASearch&fulltext=on&search=pressure+advance+%26+more')

    def test_forms_that_change_things_or_have_nothing_to_type_are_left_out(self):
        page = reader.parse_html(
            '<form action="/login" method="post"><input name="user"><input type="password" name="p"></form>'
            '<form action="/vote"><input type="hidden" name="id" value="1"><input type="submit"></form>'
            '<form style="display:none" action="/hidden"><input name="q"></form><p>text</p>', 'https://example.com/')
        self.assertEqual([b['kind'] for b in page.blocks], ['p'])

    def test_a_form_without_an_action_searches_the_page_it_is_on(self):
        page = reader.parse_html('<form><input name="q"></form>', 'https://example.com/find?old=1')
        self.assertEqual(reader.submit_url(page.blocks[0]['form'], 'x'), 'https://example.com/find?q=x')

    def test_the_search_form_outside_the_main_content_is_kept(self):
        page = reader.parse_html('<header><form action="/s"><input name="q"></form><p>menu</p></header>'
                                 '<main><p>article</p></main>', 'https://example.com/')
        self.assertEqual([(b['kind'], b['text']) for b in page.blocks], [('form', 'Search'), ('p', 'article')])


class SpeedTests(unittest.TestCase):
    def test_a_large_page_with_a_large_stylesheet_stays_fast(self):
        # 1500 kept rules and 6000 elements. Looking at every rule for every
        # element (9 million checks) took seconds on a PC; filed by class it
        # is a few thousand dictionary lookups.
        import time
        css = ''.join(f'.c{i}{{color:#ffd700}} .w{i} .inner{{display:none}} ' for i in range(900))
        body = ''.join(f'<div class="c{i % 900} extra"><p class="inner">row {i}</p></div>' for i in range(3000))
        started = time.perf_counter()
        page = reader.parse_html(f'<style>{css}</style>{body}', 'https://example.com/')
        elapsed = time.perf_counter() - started
        self.assertEqual(len(page.blocks), reader.MAX_BLOCKS)
        self.assertEqual(page.blocks[5]['color'], (255, 215, 0))
        self.assertLess(elapsed, 2.0, f'took {elapsed:.2f}s')

if __name__ == '__main__':
    unittest.main()
