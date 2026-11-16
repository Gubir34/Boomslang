"""A tiny reader-mode web browser engine for the printer's touch screen.

It fetches a page and turns the HTML into a flat list of blocks (headings,
paragraphs, list items, preformatted text, search forms), each with the links
found in it. There is no real layout: the touch UI draws the blocks as text
and link buttons.

CSS: the page's own stylesheets are honoured where they change what is read:
hidden elements, text colour and alignment, a few text effects, and which
elements start a new line. See reader_css.py for what is understood and how
it is kept fast.

JavaScript: there is no JavaScript engine, and there will not be one here. A
real one needs a native library and a whole DOM behind it, far more memory
than a printer with about 200 MB of RAM that must keep printing can give.
Instead the common things scripts are used for are recognised and done
directly:

  - redirects: meta refresh, location = "...", location.replace("..."), also
    inside setTimeout(...) or window.onload
  - document.write("...") of a fixed string
  - onclick="location.href='...'" buttons, which become links
  - pages drawn by scripts from data they carry (JSON-LD, __NEXT_DATA__,
    window.__INITIAL_STATE__ ...): when a page has almost no text of its own,
    the readable text in that data is shown instead

Everything here is plain Python with no LVGL, so it is tested on a PC.
"""
import json
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, urldefrag, urlencode, urljoin, urlparse, urlunparse

import reader_css
from reader_css import (MAX_CSS_BYTES, MAX_CSS_RULES, NAMED_COLORS, Stylesheet, media_matches,  # noqa: F401
                        parse_color, parse_css, parse_declarations, parse_length, parse_rgb)

MAX_BYTES = 512 * 1024      # bytes of HTML read from one page
MAX_BLOCKS = 2000           # blocks kept from one page (the touch UI shows them in parts)
MAX_BLOCK_CHARS = 1200      # longer paragraphs are split
MAX_LINKS_PER_BLOCK = 8
MAX_FORMS = 4
MIN_FREE_MEMORY_KB = 30 * 1024
SEARCH_URL = 'https://html.duckduckgo.com/html/?q='
USER_AGENT = 'Mozilla/5.0 (X11; Linux armv7l) Boomslang-Reader/1.0'

MAX_STYLESHEETS = 2         # external stylesheets fetched for one page
MAX_REDIRECTS = 3
MAX_REFRESH_SECONDS = 5
MAX_DATA_BYTES = 256 * 1024  # of script data looked at for text
MAX_DATA_BLOCKS = 150
THIN_PAGE_CHARS = 400       # a page with less text than this probably needs JavaScript


# --- JavaScript that can be understood without running it -----------------------

_REDIRECT_JS = re.compile(
    r"""^\s*(?:(?:window|document|top|self)\.)?location(?:\.href)?\s*=\s*(['"])(.+?)\1\s*;?\s*$|"""
    r"""^\s*(?:(?:window|document|top|self)\.)?location\.(?:replace|assign)\(\s*(['"])(.+?)\3\s*\)\s*;?\s*$""",
    re.S)
_WRAPPED_JS = re.compile(
    r"""^\s*(?:setTimeout\(\s*(?:function\s*\(\s*\)|\(\s*\)\s*=>)\s*\{(?P<timer>.*)\}\s*,\s*(?P<ms>\d+)\s*\)\s*;?|"""
    r"""window\.onload\s*=\s*function\s*\(\s*\)\s*\{(?P<onload>.*)\}\s*;?)\s*$""", re.S)
_CLICK_JS = re.compile(
    r"""(?:(?:window|document|top|self)\.)?location(?:\.href)?\s*=\s*(['"])(.+?)\1|"""
    r"""(?:(?:window|document|top|self)\.)?location\.(?:replace|assign)\(\s*(['"])(.+?)\3\s*\)|"""
    r"""window\.open\(\s*(['"])(.+?)\5""")
_DOCUMENT_WRITE = re.compile(
    r"""<script[^>]*>\s*document\.write(?:ln)?\(\s*(["'])((?:\\.|(?!\1).)*)\1\s*\)\s*;?\s*</script>""", re.I | re.S)
_JS_ESCAPE = re.compile(r'\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)', re.S)
_STATE_JS = re.compile(r'^\s*(?:window\.|self\.|var\s+|let\s+|const\s+)?[\w$.]*(?:STATE|DATA|PROPS|data|state|props)[\w$]*(?:__)?\s*=\s*(?=[{\[])')


def js_redirect_target(script):
    """The URL of a script that does nothing but redirect, else None.

    Only a lone `location = "..."`, `location.href = "..."` or
    `location.replace("...")` counts, by itself or as the only thing inside
    a short setTimeout or window.onload. Anything with conditions or other
    code is left alone: without a JavaScript engine guessing would send
    people to the wrong place.
    """
    script = script or ''
    wrapped = _WRAPPED_JS.match(script)
    if wrapped:
        if wrapped.group('ms') and int(wrapped.group('ms')) > MAX_REFRESH_SECONDS * 1000:
            return None
        script = wrapped.group('timer') if wrapped.group('timer') is not None else wrapped.group('onload')
    m = _REDIRECT_JS.match(script)
    return (m.group(2) or m.group(4)) if m else None


def js_click_target(code):
    """Where onclick="location.href='...'" (or window.open) leads, else None."""
    if not code or ('location' not in code and 'open(' not in code):
        return None
    m = _CLICK_JS.search(code)
    return (m.group(2) or m.group(4) or m.group(6)) if m else None


def _unescape_js(text):
    def replace(m):
        code = m.group(1)
        if code[0] in 'ux' and len(code) > 1:
            return chr(int(code[1:], 16))
        return {'n': '\n', 't': '\t', 'r': '', 'b': '', 'f': ''}.get(code, code)
    return _JS_ESCAPE.sub(replace, text)


def inline_document_write(html):
    """Replace <script>document.write("fixed text")</script> with that text."""
    if 'document.write' not in html:
        return html
    return _DOCUMENT_WRITE.sub(lambda m: _unescape_js(m.group(2)), html, count=30)


def meta_refresh_target(content):
    """'0; url=/next' -> '/next' when the delay is short, else None."""
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*;\s*url\s*=\s*['\"]?([^'\"]+)", content or '', re.I)
    return m.group(2).strip() if m and float(m.group(1)) <= MAX_REFRESH_SECONDS else None


# --- text carried as data by pages that are drawn by scripts ---------------------

_TAGS = re.compile(r'<[^>]+>')
_TITLE_KEYS = ('headline', 'title', 'name')
_TEXT_KEYS = ('articleBody', 'text', 'description', 'content', 'body', 'summary', 'excerpt')


def _is_prose(value):
    if len(value) < 80 or value.count(' ') < 10:
        return False
    return not value.startswith(('http://', 'https://', 'data:', '{', '['))


def data_blocks(scripts):
    """Readable text found in a page's script data, as blocks."""
    blocks, seen = [], set()

    def add(kind, text):
        text = re.sub(r'[ \t\r\f\v]+', ' ', unescape(_TAGS.sub(' ', text)))
        for paragraph in re.split(r'\s*\n\s*', text):
            paragraph = paragraph.strip()
            if len(paragraph) < 3 or paragraph in seen or len(blocks) >= MAX_DATA_BLOCKS:
                continue
            seen.add(paragraph)
            while paragraph:
                blocks.append({'kind': kind, 'text': paragraph[:MAX_BLOCK_CHARS], 'main': False, 'links': [],
                               'color': None, 'align': None})
                paragraph = paragraph[MAX_BLOCK_CHARS:]

    def walk(node, depth=0):
        if depth > 14 or len(blocks) >= MAX_DATA_BLOCKS:
            return
        if isinstance(node, dict):
            prose = [(key, value) for key, value in node.items() if isinstance(value, str) and _is_prose(value)]
            # Known text fields first, in reading order
            prose.sort(key=lambda item: _TEXT_KEYS.index(item[0]) if item[0] in _TEXT_KEYS else len(_TEXT_KEYS))
            if prose:
                for key in _TITLE_KEYS:
                    title = node.get(key)
                    if isinstance(title, str) and 3 < len(title) < 200 and not _is_prose(title):
                        add('h2', title)
                        break
                for _, value in prose:
                    add('p', value)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value, depth + 1)
        elif isinstance(node, list):
            for item in node[:200]:
                if isinstance(item, (dict, list)):
                    walk(item, depth + 1)
                elif isinstance(item, str) and _is_prose(item):
                    add('p', item)

    for text in scripts:
        text = text.strip().rstrip(';')
        try:
            walk(json.loads(text))
        except ValueError:
            continue
    return blocks


class BrowserError(Exception):
    """An error with a message that is fine to show on the touch screen."""


class Page:
    def __init__(self, url, title, blocks, truncated=False, redirect=None):
        self.url = url
        self.title = title
        # list of dicts: kind, text, links, color, align and optionally
        # decor ('underline' / 'strike'), bg (r, g, b), big, form
        self.blocks = blocks
        self.truncated = truncated
        self.redirect = redirect      # where a meta refresh or script redirect sends the reader
        self.from_data = False        # the text came from script data, see data_blocks


def normalize_url(text):
    """What was typed in the address bar -> a URL, or a web search."""
    text = (text or '').strip()
    if not text:
        raise BrowserError('Type an address or something to search for')
    if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', text):
        scheme = text.split('://', 1)[0].lower()
        if scheme not in ('http', 'https'):
            raise BrowserError(f'Only http and https pages can be opened ({scheme} is not supported)')
        return text
    looks_like_host = (' ' not in text and
                       (re.match(r'^[\w-]+(\.[\w-]+)+(:\d+)?([/?#].*)?$', text) or
                        re.match(r'^(localhost|[\w-]+\.local)(:\d+)?([/?#].*)?$', text, re.I)))
    if looks_like_host:
        host = re.split(r'[/?#:]', text, maxsplit=1)[0].lower()
        plain = host == 'localhost' or host.endswith('.local') or re.match(r'^\d+(\.\d+){3}$', host)
        return ('http://' if plain else 'https://') + text
    return SEARCH_URL + quote_plus(text)


def clean_link(url):
    """Unwrap search-engine redirect links so a result opens its real page."""
    parsed = urlparse(url)
    if parsed.netloc.endswith('duckduckgo.com') and parsed.path.startswith('/l/'):
        target = parse_qs(parsed.query).get('uddg')
        if target:
            return target[0]   # parse_qs already decoded it; decoding again breaks %26, %23, %2B
    return url


def submit_url(form, value):
    """The address a search form opens for what was typed (GET forms only)."""
    fields = list(form.get('fields') or []) + [(form['name'], value)]
    parts = urlparse(form['action'])
    # As in a browser, the form's fields replace the action's own query
    return urlunparse(parts._replace(query=urlencode(fields), fragment=''))


KIND = {'h1': 'h1', 'h2': 'h2', 'h3': 'h3', 'h4': 'h3', 'h5': 'h3', 'h6': 'h3',
        'li': 'li', 'dt': 'h3', 'blockquote': 'quote', 'pre': 'pre'}
BREAKING = {'p', 'div', 'section', 'article', 'header', 'footer', 'main', 'nav', 'aside', 'ul', 'ol',
            'table', 'tr', 'form', 'figure', 'figcaption', 'dl', 'dt', 'dd', 'blockquote', 'pre',
            'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'details', 'summary', 'address'}
# Elements a page may turn into running text with display:inline (menus made
# of list items, tag clouds). Headings, paragraphs and tables stay blocks.
SOFT_BREAKING = {'div', 'li', 'ul', 'ol', 'nav', 'section', 'header', 'footer', 'aside', 'dl', 'dt', 'dd', 'address'}
BLOCK_DISPLAYS = {'block', 'flex', 'grid', 'list-item', 'table', 'flow-root'}
# <option> is not listed: its end tag is optional, so counting it would hide
# the rest of the page after <select><option>A<option>B</select>. The
# <select> around it already hides it.
SKIPPED = {'script', 'svg', 'template', 'iframe', 'canvas', 'select'}
VOID = {'br', 'img', 'hr', 'input', 'meta', 'link', 'area', 'base', 'col', 'embed', 'source', 'track', 'wbr'}
TEXT_INPUTS = {'', 'text', 'search', 'email', 'url', 'tel', 'number'}
PRE_WHITE_SPACE = {'pre', 'pre-wrap', 'pre-line', 'break-spaces'}
BIG_FONT_PX = 22
_HIDDEN_ENTRY_KEYS = {'hides': False, 'color': None, 'align': None, 'id': None, 'classes': (), 'breaking': None,
                      'transform': None, 'decor': None, 'space': None}


class _Extractor(HTMLParser):
    def __init__(self, base_url, stylesheets=()):
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.title = ''
        self.blocks = []
        self.truncated = False
        self.redirect = None
        self.data = []            # JSON found in scripts, for pages drawn by JavaScript
        self._data_bytes = 0
        self._kind = 'p'
        self._text = []
        self._links = []
        self._skip = 0
        self._in_title = False
        self._pre = False
        self._href = None
        self._a_text = []
        self._click = None        # [tag, depth] of a non-anchor element acting as a link
        self._main = 0
        self._sheet = Stylesheet()
        for css in stylesheets:
            self._sheet.add(css)
        self._css = None          # text of the <style> being read
        self._css_use = True
        self._script = None       # text of the inline <script> being read
        self._script_data = False
        self._stack = []          # open elements, outermost first
        self._hidden = 0          # how many open elements are hidden
        self._form = None         # the <form> being read
        self._forms = 0
        self._block_bg = None     # background and size of the block being collected
        self._block_big = False

    # --- blocks -------------------------------------------------------------
    def _style(self):
        color = align = transform = decor = None
        for entry in reversed(self._stack):
            color = color or entry['color']
            align = align or entry['align']
            transform = transform or entry['transform']
            decor = decor or entry['decor']
            if color and align and transform and decor:
                break
        return color, (align if align in ('center', 'right') else None), transform, decor

    def _flush(self):
        raw = ''.join(self._text)
        links, self._links = self._links, []
        self._text = []
        if self._kind == 'pre':
            text = '\n'.join(line.rstrip() for line in raw.strip('\n').split('\n'))
        else:
            text = re.sub(r'\s+', ' ', raw).strip()
        if not text and not links:
            return
        if len(self.blocks) >= MAX_BLOCKS:
            self.truncated = True
            return
        color, align, transform, decor = self._style()
        if transform == 'uppercase':
            text = text.upper()
        elif transform == 'lowercase':
            text = text.lower()
        elif transform == 'capitalize':
            text = re.sub(r'(?<![\w\'])\w', lambda m: m.group(0).upper(), text)
        chunks = [text]
        while len(chunks[-1]) > MAX_BLOCK_CHARS:
            last = chunks.pop()
            cut = last.rfind(' ', 0, MAX_BLOCK_CHARS)
            cut = cut if cut > MAX_BLOCK_CHARS // 2 else MAX_BLOCK_CHARS
            chunks += [last[:cut].rstrip(), last[cut:].lstrip()]
        for i, chunk in enumerate(chunks):
            block = {'kind': self._kind, 'text': chunk, 'main': self._main > 0,
                     'color': color, 'align': align,
                     'links': links if i == len(chunks) - 1 else []}
            if decor:
                block['decor'] = decor
            if self._block_bg:
                block['bg'] = self._block_bg
            if self._block_big:
                block['big'] = True
            self.blocks.append(block)

    # --- styles ---------------------------------------------------------------
    def _declarations(self, tag, attrs, ancestors=None):
        class_attr = attrs.get('class')
        classes = tuple(class_attr.split()) if class_attr else ()
        element_id = attrs.get('id') or None
        declared, forced = self._sheet.declarations(tag, element_id, classes, attrs,
                                                    self._stack if ancestors is None else ancestors)
        style = attrs.get('style')
        if style or 'hidden' in attrs:
            declared = dict(declared)   # the stylesheet's answer is shared, don't change it
            if style:
                important = set()
                for key, value in parse_declarations(style, important).items():
                    # inline style wins, except over an !important rule
                    if key not in forced or key in important:
                        declared[key] = value
            if 'hidden' in attrs:
                declared['display'] = 'none'
        return declared, element_id, classes

    def _text_style(self, entry, tag, declared):
        entry['color'] = parse_color(self._value(declared, 'color'))
        entry['align'] = declared.get('text-align')
        entry['transform'] = declared.get('text-transform')
        entry['space'] = declared.get('white-space')
        decoration = declared.get('text-decoration-line') or declared.get('text-decoration')
        entry['decor'] = None
        if decoration:
            entry['decor'] = ('strike' if 'line-through' in decoration else
                              'underline' if 'underline' in decoration and tag != 'a' else None)

    def _restyle_open(self):
        """Apply a stylesheet that was just read to the elements already open.

        A <style> in <head> is read after <html> was opened, so a colour set
        on :root or html would otherwise be missed. Only what text inherits
        is refreshed; there are a handful of open elements at most.
        """
        for index, entry in enumerate(self._stack):
            attrs = entry.get('attrs')
            if attrs is not None and not entry['hides']:
                declared, _, _ = self._declarations(entry['tag'], attrs, self._stack[:index])
                self._text_style(entry, entry['tag'], declared)

    def _value(self, declared, key):
        value = declared.get(key)
        if value and 'var(' in value:
            value = self._sheet.resolve(value)
        return value

    def _pop(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i]['tag'] == tag:
                for entry in self._stack[i:]:
                    if entry['hides']:
                        self._hidden -= 1
                del self._stack[i:]
                return

    def _entry(self, tag):
        for entry in reversed(self._stack):
            if entry['tag'] == tag:
                return entry
        return None

    # --- links, forms -----------------------------------------------------------
    def _finish_link(self):
        if self._href:
            label = re.sub(r'\s+', ' ', ''.join(self._a_text)).strip()
            if not label:
                label = urlparse(self._href).netloc or self._href
            if (len(self._links) < MAX_LINKS_PER_BLOCK and
                    not any(url == self._href for _, url in self._links)):
                self._links.append((label[:80], self._href))
        self._href = None
        self._a_text = []
        self._click = None

    def _input(self, attrs):
        kind = (attrs.get('type') or '').lower()
        name = attrs.get('name')
        if kind in ('button', 'submit') and attrs.get('onclick'):
            target = self._resolve(js_click_target(attrs.get('onclick')))
            label = (attrs.get('value') or '').strip()
            if target and label and len(self._links) < MAX_LINKS_PER_BLOCK:
                self._links.append((label[:80], target))
            return
        if self._form is None or not name:
            return
        if kind == 'hidden':
            self._form['fields'].append((name, attrs.get('value') or ''))
        elif kind in TEXT_INPUTS and not self._form.get('name'):
            self._form['name'] = name
            self._form['label'] = (attrs.get('placeholder') or attrs.get('aria-label') or
                                   attrs.get('title') or '').strip()[:60]
        elif kind in ('checkbox', 'radio'):
            if 'checked' in attrs:
                self._form['fields'].append((name, attrs.get('value') or 'on'))

    def _finish_form(self):
        form, self._form = self._form, None
        if not form or not form.get('name') or form['method'] != 'get' or not form['action']:
            return   # nothing to type into, or a form that changes something (POST)
        if self._forms >= MAX_FORMS or len(self.blocks) >= MAX_BLOCKS:
            return
        self._forms += 1
        self.blocks.append({'kind': 'form', 'text': form.get('label') or 'Search', 'main': self._main > 0,
                            'color': None, 'align': None, 'links': [],
                            'form': {'action': form['action'], 'name': form['name'], 'fields': form['fields']}})

    # --- parser callbacks -----------------------------------------------------
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'style' and not self._skip and not self._hidden:
            self._css = []
            media = attrs.get('media')
            self._css_use = not media or media_matches(media, self._sheet.width)
            return
        if tag == 'script':
            self._skip += 1
            self._script = [] if not attrs.get('src') else None
            self._script_data = 'json' in (attrs.get('type') or '').lower() or attrs.get('id') == '__NEXT_DATA__'
            return
        if tag in SKIPPED:
            self._skip += 1
            return
        if self._skip:
            return
        if tag == 'meta':
            if (attrs.get('http-equiv') or '').lower() == 'refresh' and not self.redirect:
                target = meta_refresh_target(attrs.get('content'))
                self.redirect = self._resolve(target) if target else None
            return
        if tag == 'title':
            self._in_title = True
            return
        if self._hidden:
            if tag not in VOID:
                self._stack.append(dict(_HIDDEN_ENTRY_KEYS, tag=tag))
            return
        declared, element_id, classes = self._declarations(tag, attrs)
        hides = bool(declared) and reader_css.hides(declared)

        breaking = tag in BREAKING
        if declared:
            display = declared.get('display')
            if display:
                if display in BLOCK_DISPLAYS:
                    breaking = True
                elif tag in SOFT_BREAKING and display.startswith('inline'):
                    breaking = False
                    self._text.append(' ')   # still a word boundary: "Home Docs", not "HomeDocs"

        if tag not in VOID:
            entry = {'tag': tag, 'hides': hides, 'id': element_id, 'classes': classes, 'breaking': breaking,
                     'color': None, 'align': None, 'transform': None, 'decor': None, 'space': None, 'attrs': attrs}
            if declared and not hides:
                self._text_style(entry, tag, declared)
            self._stack.append(entry)
            if hides:
                self._hidden += 1
        if hides:
            if breaking:
                self._flush()
            return
        if tag in ('main', 'article'):
            self._flush()
            self._main += 1
        if breaking:
            self._flush()
            self._kind = KIND.get(tag, 'p')
            self._pre = tag == 'pre'
            self._block_bg = None
            self._block_big = False
            if declared:
                if declared.get('white-space') in PRE_WHITE_SPACE:
                    self._kind, self._pre = 'pre', True
                background = self._value(declared, 'background-color') or self._value(declared, 'background')
                if background and tag not in ('html', 'body'):
                    self._block_bg = parse_rgb(background) or parse_rgb(background.split()[0])
                size = declared.get('font-size')
                if size and self._kind == 'p':
                    pixels = parse_length(size)
                    self._block_big = size in ('x-large', 'xx-large', 'xxx-large') or (pixels or 0) >= BIG_FONT_PX
            if tag == 'form' and self._form is None:
                action = self._resolve(attrs.get('action') or self.base) or self.base
                self._form = {'action': action, 'method': (attrs.get('method') or 'get').lower(), 'fields': []}
        elif tag == 'br':
            self._text.append('\n' if self._pre else ' ')
        elif tag in ('td', 'th'):
            self._text.append(' ')
        elif tag == 'input':
            self._input(attrs)
            return
        elif tag == 'textarea':
            self._input(dict(attrs, type='text'))
        elif tag == 'img':
            alt = (attrs.get('alt') or '').strip()
            if alt and len(alt) < 80:
                self._text.append(f'[{alt}]')
                self._a_text.append(alt)

        if tag == 'a':
            self._finish_link()
            href = attrs.get('href')
            target = self._resolve(href) if href else None
            if not target:   # href="javascript:..." or only an onclick
                target = self._resolve(js_click_target(attrs.get('onclick') or href))
            self._href = target
        elif self._click and self._click[0] == tag:
            self._click[1] += 1
        elif not self._href and tag != 'input' and attrs.get('onclick'):
            target = self._resolve(js_click_target(attrs.get('onclick')))
            if target and tag not in VOID:
                self._href, self._a_text, self._click = target, [], [tag, 1]

    def handle_endtag(self, tag):
        if tag == 'style' and self._css is not None:
            if self._css_use and self._sheet.count < MAX_CSS_RULES:
                self._sheet.add(''.join(self._css))
                self._restyle_open()
            self._css = None
            return
        if tag == 'script':
            if self._script is not None:
                text = ''.join(self._script)
                if self._script_data:
                    self._keep_data(text)
                else:
                    if not self.redirect:
                        target = js_redirect_target(text)
                        self.redirect = self._resolve(target) if target else None
                    state = _STATE_JS.match(text)
                    if state:
                        self._keep_data(text[state.end():])
            self._script = None
            self._skip = max(0, self._skip - 1)
            return
        if tag in SKIPPED:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if self._hidden:
            self._pop(tag)
            return
        if tag == 'title':
            self._in_title = False
            return
        if tag == 'a':
            self._finish_link()
        elif self._click and self._click[0] == tag:
            self._click[1] -= 1
            if self._click[1] <= 0:
                self._finish_link()
        entry = self._entry(tag)
        breaking = entry['breaking'] if entry else tag in BREAKING
        if not breaking and tag in SOFT_BREAKING:
            self._text.append(' ')
        if breaking:
            if self._click:
                self._finish_link()   # the clickable element was not closed properly
            self._flush()
            self._kind = 'p'
            self._pre = False
            self._block_bg = None
            self._block_big = False
            if tag in ('main', 'article'):
                self._main = max(0, self._main - 1)
            if tag == 'form':
                self._finish_form()
        self._pop(tag)

    def handle_data(self, data):
        if self._css is not None:
            self._css.append(data)
            return
        if self._skip:
            if self._script is not None:
                self._script.append(data)
            return
        if self._hidden:
            return
        if self._in_title:
            self.title += data
            return
        self._text.append(data)
        if self._href:
            self._a_text.append(data)

    def _keep_data(self, text):
        if self._data_bytes + len(text) <= MAX_DATA_BYTES and len(self.data) < 8:
            self.data.append(text)
            self._data_bytes += len(text)

    def _resolve(self, href):
        href = (href or '').strip()
        if not href or href.startswith(('javascript:', 'mailto:', 'tel:', 'data:', '#')):
            return None
        url = clean_link(urldefrag(urljoin(self.base, href))[0])
        return url if urlparse(url).scheme in ('http', 'https') else None


def parse_html(html, base_url, stylesheets=()):
    """HTML text -> Page. stylesheets: the text of the page's external stylesheets."""
    extractor = _Extractor(base_url, stylesheets)
    try:
        extractor.feed(inline_document_write(html))
        extractor.close()
    except Exception:
        pass  # keep whatever was read before the broken markup
    extractor._flush()
    if extractor._form:
        extractor._finish_form()
    blocks = extractor.blocks
    # Pages that mark their main content: leave out menus, headers and footers
    # (a search form is kept wherever it is)
    if any(b['main'] for b in blocks):
        blocks = [b for b in blocks if b['main'] or b['kind'] == 'form']
    title = re.sub(r'\s+', ' ', extractor.title).strip() or urlparse(base_url).netloc
    page = Page(base_url, title, blocks, extractor.truncated, extractor.redirect)
    # Hardly any text: the page is drawn by JavaScript. Show what its data says.
    if extractor.data and sum(len(b['text']) for b in blocks if b['kind'] != 'form') < THIN_PAGE_CHARS:
        found = data_blocks(extractor.data)
        if found:
            page.blocks = blocks + found
            page.from_data = True
    return page


def memory_available_kb(meminfo='/proc/meminfo'):
    try:
        with open(meminfo) as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1])
    except (OSError, ValueError):
        pass
    return None


def fetch(url, get=None, available_kb=memory_available_kb):
    """Download and parse a page, following meta refresh and script redirects.

    Raises BrowserError with a readable message. get is requests.get unless a
    test passes its own. At most MAX_REDIRECTS redirects are followed and a
    page is never fetched twice, so redirect loops end on the last page.
    """
    seen = {url}
    for hop in range(MAX_REDIRECTS + 1):
        page = _fetch_once(url, get, available_kb)
        target = page.redirect
        if not target or target in seen or hop == MAX_REDIRECTS:
            return page
        seen.add(target)
        url = target


_LINK_TAG = re.compile(r'<link\b[^>]*>', re.I)
_ATTRIBUTE = re.compile(r'''([\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))''')


def stylesheet_links(html, base_url):
    """Addresses of the page's own stylesheets, the first few that apply to a screen."""
    links = []
    head = html[:64 * 1024]
    if 'stylesheet' not in head:
        return links
    for tag in _LINK_TAG.findall(head):
        attrs = {m.group(1).lower(): m.group(2) or m.group(3) or m.group(4) or '' for m in _ATTRIBUTE.finditer(tag)}
        if 'stylesheet' not in attrs.get('rel', '').lower().split() or 'alternate' in attrs.get('rel', '').lower():
            continue
        if attrs.get('media') and not media_matches(attrs['media']):
            continue
        url = urljoin(base_url, unescape(attrs.get('href', '')).strip())
        if urlparse(url).scheme in ('http', 'https') and url not in links:
            links.append(url)
            if len(links) >= MAX_STYLESHEETS:
                break
    return links


def _fetch_stylesheets(html, base_url, get):
    """The text of the page's stylesheets. A stylesheet that can't be read is skipped."""
    sheets = []
    for url in stylesheet_links(html, base_url):
        try:
            response = get(url, stream=True, timeout=(4, 6), allow_redirects=True,
                           headers={'User-Agent': USER_AGENT, 'Accept': 'text/css,*/*;q=0.1'})
        except Exception:
            continue
        try:
            kind = (response.headers.get('Content-Type') or 'text/css').split(';')[0].strip().lower()
            if response.status_code >= 400 or kind not in ('text/css', 'text/plain', ''):
                continue
            parts, size = [], 0
            for chunk in response.iter_content(chunk_size=16384):
                parts.append(chunk)
                size += len(chunk)
                if size >= MAX_CSS_BYTES:
                    break
            sheets.append(b''.join(parts)[:MAX_CSS_BYTES].decode('utf-8', errors='replace'))
        except Exception:
            continue
        finally:
            close = getattr(response, 'close', None)
            if close:
                close()
    return sheets


def _fetch_once(url, get, available_kb):
    free = available_kb()
    if free is not None and free < MIN_FREE_MEMORY_KB:
        raise BrowserError(f'Not enough free memory ({free // 1024} MB) to open a page safely')
    if get is None:
        import requests
        get = requests.get
    try:
        response = get(url, stream=True, timeout=(6, 12), allow_redirects=True,
                       headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,text/plain;q=0.9,*/*;q=0.1',
                                'Accept-Language': 'en,tr;q=0.8'})
    except Exception as e:
        raise BrowserError(f'Could not reach the page: {type(e).__name__}')
    try:
        final = getattr(response, 'url', url) or url
        if urlparse(final).scheme not in ('http', 'https'):
            raise BrowserError('The page redirected to an unsupported address')
        if response.status_code >= 400:
            raise BrowserError(f'The server answered {response.status_code}')
        kind = (response.headers.get('Content-Type') or 'text/html').split(';')[0].strip().lower()
        if kind not in ('text/html', 'application/xhtml+xml', 'text/plain', ''):
            raise BrowserError(f'This is a {kind} file, not a web page')
        parts, size = [], 0
        for chunk in response.iter_content(chunk_size=16384):
            parts.append(chunk)
            size += len(chunk)
            if size >= MAX_BYTES:
                break
        data = b''.join(parts)[:MAX_BYTES]
        # Use the charset the server states, otherwise UTF-8 (undecodable
        # bytes become replacement characters instead of an error)
        header = response.headers.get('Content-Type') or ''
        if 'charset' in header.lower() and response.encoding:
            encoding = response.encoding
        else:
            # No charset in the header: trust <meta charset> (Turkish sites often use windows-1254)
            found = re.search(rb'<meta[^>]+charset\s*=\s*["\']?\s*([\w-]+)', data[:4096], re.I)
            encoding = found.group(1).decode('ascii', 'ignore') if found else 'utf-8'
        try:
            text = data.decode(encoding, errors='replace')
        except LookupError:
            text = data.decode('utf-8', errors='replace')
    finally:
        close = getattr(response, 'close', None)
        if close:
            close()
    if kind == 'text/plain':
        escaped = text.replace('&', '&amp;').replace('<', '&lt;')
        return parse_html(f'<pre>{escaped}</pre>', final)
    return parse_html(text, final, _fetch_stylesheets(text, final, get))
