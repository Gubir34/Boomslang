"""A tiny reader-mode web browser engine for the printer's touch screen.

It fetches a page and turns the HTML into a flat list of blocks (headings,
paragraphs, list items, preformatted text), each with the links found in it.
There is no JavaScript engine and no real layout: the touch UI draws the
blocks as text and link buttons. A little CSS is honoured (elements hidden by
the page's own rules, text colour and centring) and a little JavaScript is
understood (meta refresh and one-line location redirects). That is enough for
wikis, documentation, forums and search results, and it keeps memory use
small, which matters on a printer with about 200 MB of RAM that must also keep
printing.

Everything here is plain Python with no LVGL, so it is tested on a PC.
"""
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, unquote, urldefrag, urljoin, urlparse

MAX_BYTES = 512 * 1024      # bytes of HTML read from one page
MAX_BLOCKS = 400            # blocks kept from one page
MAX_BLOCK_CHARS = 1200      # longer paragraphs are split
MAX_LINKS_PER_BLOCK = 8
MIN_FREE_MEMORY_KB = 30 * 1024
SEARCH_URL = 'https://html.duckduckgo.com/html/?q='
USER_AGENT = 'Mozilla/5.0 (X11; Linux armv7l) Boomslang-Reader/1.0'


MAX_CSS_BYTES = 100 * 1024
MAX_CSS_RULES = 600
MAX_REDIRECTS = 3
MAX_REFRESH_SECONDS = 5

NAMED_COLORS = {
    'white': (255, 255, 255), 'silver': (192, 192, 192), 'gray': (128, 128, 128), 'grey': (128, 128, 128),
    'red': (255, 80, 80), 'orange': (255, 165, 0), 'yellow': (255, 215, 0), 'gold': (255, 215, 0),
    'lime': (0, 255, 0), 'green': (60, 190, 60), 'teal': (0, 170, 170), 'cyan': (0, 255, 255),
    'aqua': (0, 255, 255), 'blue': (90, 140, 255), 'purple': (190, 110, 230), 'magenta': (255, 0, 255),
    'pink': (255, 150, 190), 'lightgray': (211, 211, 211), 'lightgrey': (211, 211, 211),
}
INTERESTING = ('display', 'visibility', 'color', 'text-align')


def parse_declarations(text):
    """'color: red; display:none !important' -> {'color': 'red', 'display': 'none'} (only what we use)."""
    out = {}
    for part in (text or '').split(';'):
        key, sep, value = part.partition(':')
        key = key.strip().lower()
        if sep and key in INTERESTING:
            out[key] = re.sub(r'\s*!important\s*$', '', value.strip(), flags=re.I).strip().lower()
    return out


def parse_color(value):
    """CSS colour -> (r, g, b), or None when unknown or too dark to read on the dark touch screen."""
    value = (value or '').strip().lower()
    rgb = NAMED_COLORS.get(value)
    m = re.fullmatch(r'#([0-9a-f]{3}|[0-9a-f]{6})', value)
    if m:
        h = m.group(1)
        h = ''.join(c * 2 for c in h) if len(h) == 3 else h
        rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r'rgba?\(\s*(\d+)\s*[, ]\s*(\d+)\s*[, ]\s*(\d+)[^)]*\)', value)
    if m:
        rgb = tuple(min(255, int(g)) for g in m.groups())
    if not rgb:
        return None
    luminance = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255
    return rgb if luminance >= 0.30 else None


_SELECTOR = re.compile(r'\s*([a-zA-Z][\w-]*)?((?:\.[\w-]+)*)(?:#([\w-]+))?((?:\.[\w-]+)*)\s*')


def parse_css(css):
    """Simple rules only: tag, .class and #id selectors (no combinators, pseudo classes or @media).

    Returns [(tag or None, [classes], id or None, {property: value})] in source order.
    """
    css = re.sub(r'/\*.*?\*/', '', (css or '')[:MAX_CSS_BYTES], flags=re.S)
    rules, i, n = [], 0, len(css)
    while i < n and len(rules) < MAX_CSS_RULES:
        brace = css.find('{', i)
        if brace < 0:
            break
        prelude = css[i:brace]
        depth, j = 1, brace + 1
        while j < n and depth:
            depth += {'{': 1, '}': -1}.get(css[j], 0)
            j += 1
        body = css[brace + 1:j - 1]
        i = j
        prelude = prelude.rsplit(';', 1)[-1].strip()   # drop a preceding @import ...;
        if not prelude or prelude.startswith('@'):
            continue
        props = parse_declarations(body)
        if not props:
            continue
        for selector in prelude.split(','):
            m = _SELECTOR.fullmatch(selector)
            if m and (m.group(1) or m.group(2) or m.group(3) or m.group(4)):
                classes = [c for c in (m.group(2) + m.group(4)).split('.') if c]
                rules.append(((m.group(1) or '').lower() or None, classes, m.group(3), props))
    return rules


_REDIRECT_JS = re.compile(
    r"""^\s*(?:(?:window|document|top|self)\.)?location(?:\.href)?\s*=\s*(['"])(.+?)\1\s*;?\s*$|"""
    r"""^\s*(?:(?:window|document|top|self)\.)?location\.(?:replace|assign)\(\s*(['"])(.+?)\3\s*\)\s*;?\s*$""",
    re.S)


def js_redirect_target(script):
    """The URL of a script that does nothing but redirect, else None.

    Only a lone `location = "..."`, `location.href = "..."` or
    `location.replace("...")` counts. Anything with conditions or other code is
    left alone: without a JavaScript engine guessing would send people to the
    wrong place.
    """
    m = _REDIRECT_JS.match(script or '')
    return (m.group(2) or m.group(4)) if m else None


def meta_refresh_target(content):
    """'0; url=/next' -> '/next' when the delay is short, else None."""
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*;\s*url\s*=\s*['\"]?([^'\"]+)", content or '', re.I)
    return m.group(2).strip() if m and float(m.group(1)) <= MAX_REFRESH_SECONDS else None


class BrowserError(Exception):
    """An error with a message that is fine to show on the touch screen."""


class Page:
    def __init__(self, url, title, blocks, truncated=False, redirect=None):
        self.url = url
        self.title = title
        self.blocks = blocks          # list of dicts: kind, text, links, color, align
        self.truncated = truncated
        self.redirect = redirect      # where a meta refresh or script redirect sends the reader


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
            return unquote(target[0])
    return url


KIND = {'h1': 'h1', 'h2': 'h2', 'h3': 'h3', 'h4': 'h3', 'h5': 'h3', 'h6': 'h3',
        'li': 'li', 'dt': 'h3', 'blockquote': 'quote', 'pre': 'pre'}
BREAKING = {'p', 'div', 'section', 'article', 'header', 'footer', 'main', 'nav', 'aside', 'ul', 'ol',
            'table', 'tr', 'form', 'figure', 'figcaption', 'dl', 'dt', 'dd', 'blockquote', 'pre',
            'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'details', 'summary', 'address'}
SKIPPED = {'script', 'svg', 'template', 'iframe', 'canvas', 'select', 'option'}
VOID = {'br', 'img', 'hr', 'input', 'meta', 'link', 'area', 'base', 'col', 'embed', 'source', 'track', 'wbr'}


class _Extractor(HTMLParser):
    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.title = ''
        self.blocks = []
        self.truncated = False
        self.redirect = None
        self._kind = 'p'
        self._text = []
        self._links = []
        self._skip = 0
        self._in_title = False
        self._pre = False
        self._href = None
        self._a_text = []
        self._main = 0
        self._rules = []          # simple CSS rules from <style>
        self._css = None          # text of the <style> being read
        self._script = None       # text of the inline <script> being read
        self._stack = []          # open elements: tag, hides, colour, alignment
        self._hidden = 0          # how many open elements are hidden

    # --- blocks -------------------------------------------------------------
    def _style(self):
        color = align = None
        for entry in reversed(self._stack):
            color = color or entry['color']
            align = align or entry['align']
            if color and align:
                break
        return color, (align if align in ('center', 'right') else None)

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
        color, align = self._style()
        chunks = [text]
        while len(chunks[-1]) > MAX_BLOCK_CHARS:
            last = chunks.pop()
            cut = last.rfind(' ', 0, MAX_BLOCK_CHARS)
            cut = cut if cut > MAX_BLOCK_CHARS // 2 else MAX_BLOCK_CHARS
            chunks += [last[:cut].rstrip(), last[cut:].lstrip()]
        for i, chunk in enumerate(chunks):
            self.blocks.append({'kind': self._kind, 'text': chunk, 'main': self._main > 0,
                                'color': color, 'align': align,
                                'links': links if i == len(chunks) - 1 else []})

    # --- styles ---------------------------------------------------------------
    def _declarations(self, tag, attrs):
        classes = (attrs.get('class') or '').split()
        element_id = attrs.get('id') or ''
        declared = {}
        for rule_tag, rule_classes, rule_id, props in self._rules:
            if rule_tag and rule_tag != tag:
                continue
            if rule_id and rule_id != element_id:
                continue
            if any(c not in classes for c in rule_classes):
                continue
            declared.update(props)
        declared.update(parse_declarations(attrs.get('style')))
        if 'hidden' in attrs:
            declared['display'] = 'none'
        return declared

    def _pop(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i]['tag'] == tag:
                for entry in self._stack[i:]:
                    if entry['hides']:
                        self._hidden -= 1
                del self._stack[i:]
                return

    # --- parser callbacks -----------------------------------------------------
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'style' and not self._skip and not self._hidden:
            self._css = []
            return
        if tag == 'script':
            self._skip += 1
            self._script = [] if not attrs.get('src') else None
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
                self._stack.append({'tag': tag, 'hides': False, 'color': None, 'align': None})
            return
        declared = self._declarations(tag, attrs)
        hides = declared.get('display') == 'none' or declared.get('visibility') in ('hidden', 'collapse')
        if tag not in VOID:
            self._stack.append({'tag': tag, 'hides': hides, 'color': parse_color(declared.get('color')),
                                'align': declared.get('text-align')})
            if hides:
                self._hidden += 1
        if hides:
            if tag in BREAKING:
                self._flush()
            return
        if tag in ('main', 'article'):
            self._flush()
            self._main += 1
        if tag in BREAKING:
            self._flush()
            self._kind = KIND.get(tag, 'p')
            self._pre = tag == 'pre'
        elif tag == 'br':
            self._text.append('\n' if self._pre else ' ')
        elif tag in ('td', 'th'):
            self._text.append(' ')
        elif tag == 'a':
            href = attrs.get('href')
            self._href = self._resolve(href) if href else None
            self._a_text = []
        elif tag == 'img':
            alt = (attrs.get('alt') or '').strip()
            if alt and len(alt) < 80:
                self._text.append(f'[{alt}]')
                self._a_text.append(alt)

    def handle_endtag(self, tag):
        if tag == 'style' and self._css is not None:
            if len(self._rules) < MAX_CSS_RULES:
                self._rules += parse_css(''.join(self._css))
            self._css = None
            return
        if tag == 'script':
            if self._script is not None and not self.redirect:
                target = js_redirect_target(''.join(self._script))
                self.redirect = self._resolve(target) if target else None
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
        elif tag in BREAKING:
            self._flush()
            self._kind = 'p'
            self._pre = False
            if tag in ('main', 'article'):
                self._main = max(0, self._main - 1)
        elif tag == 'a' and self._href:
            label = re.sub(r'\s+', ' ', ''.join(self._a_text)).strip()
            if not label:
                label = urlparse(self._href).netloc or self._href
            if (len(self._links) < MAX_LINKS_PER_BLOCK and
                    not any(url == self._href for _, url in self._links)):
                self._links.append((label[:80], self._href))
            self._href = None
            self._a_text = []
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

    def _resolve(self, href):
        href = (href or '').strip()
        if href.startswith(('javascript:', 'mailto:', 'tel:', 'data:', '#')):
            return None
        url = clean_link(urldefrag(urljoin(self.base, href))[0])
        return url if urlparse(url).scheme in ('http', 'https') else None


def parse_html(html, base_url):
    """HTML text -> Page."""
    extractor = _Extractor(base_url)
    try:
        extractor.feed(html)
        extractor.close()
    except Exception:
        pass  # keep whatever was read before the broken markup
    extractor._flush()
    blocks = extractor.blocks
    # Pages that mark their main content: leave out menus, headers and footers
    if any(b['main'] for b in blocks):
        blocks = [b for b in blocks if b['main']]
    title = re.sub(r'\s+', ' ', extractor.title).strip() or urlparse(base_url).netloc
    return Page(base_url, title, blocks, extractor.truncated, extractor.redirect)


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
        data = b''
        for chunk in response.iter_content(chunk_size=16384):
            data += chunk
            if len(data) >= MAX_BYTES:
                data = data[:MAX_BYTES]
                break
        # Use the charset the server states, otherwise UTF-8 (undecodable
        # bytes become replacement characters instead of an error)
        header = response.headers.get('Content-Type') or ''
        encoding = response.encoding if 'charset' in header.lower() and response.encoding else 'utf-8'
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
    return parse_html(text, final)
