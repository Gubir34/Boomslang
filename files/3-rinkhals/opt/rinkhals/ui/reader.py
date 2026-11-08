"""A tiny reader-mode web browser engine for the printer's touch screen.

It fetches a page and turns the HTML into a flat list of blocks (headings,
paragraphs, list items, preformatted text), each with the links found in it.
There is no JavaScript, CSS or layout: the touch UI draws the blocks as text
and link buttons. That is enough for wikis, documentation, forums and search
results, and it keeps memory use small, which matters on a printer with
about 200 MB of RAM that must also keep printing.

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


class BrowserError(Exception):
    """An error with a message that is fine to show on the touch screen."""


class Page:
    def __init__(self, url, title, blocks, truncated=False):
        self.url = url
        self.title = title
        self.blocks = blocks          # list of dicts: kind, text, links
        self.truncated = truncated


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
SKIPPED = {'script', 'style', 'noscript', 'svg', 'template', 'iframe', 'canvas', 'select', 'option'}


class _Extractor(HTMLParser):
    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.title = ''
        self.blocks = []
        self.truncated = False
        self._kind = 'p'
        self._text = []
        self._links = []
        self._skip = 0
        self._in_title = False
        self._pre = False
        self._href = None
        self._a_text = []
        self._main = 0

    # --- blocks -------------------------------------------------------------
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
        chunks = [text]
        while len(chunks[-1]) > MAX_BLOCK_CHARS:
            last = chunks.pop()
            cut = last.rfind(' ', 0, MAX_BLOCK_CHARS)
            cut = cut if cut > MAX_BLOCK_CHARS // 2 else MAX_BLOCK_CHARS
            chunks += [last[:cut].rstrip(), last[cut:].lstrip()]
        for i, chunk in enumerate(chunks):
            self.blocks.append({'kind': self._kind, 'text': chunk, 'main': self._main > 0,
                                'links': links if i == len(chunks) - 1 else []})

    # --- parser callbacks -----------------------------------------------------
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in SKIPPED:
            self._skip += 1
            return
        if self._skip:
            return
        if tag == 'title':
            self._in_title = True
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
        if tag in SKIPPED:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
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

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
            return
        self._text.append(data)
        if self._href:
            self._a_text.append(data)

    def _resolve(self, href):
        href = href.strip()
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
    return Page(base_url, title, blocks, extractor.truncated)


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
    """Download and parse a page. Raises BrowserError with a readable message.

    get is requests.get unless a test passes its own.
    """
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
