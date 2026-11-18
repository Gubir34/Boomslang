"""The parts of LemSearch Lite that need no screen, so they are tested on a PC.

- PageCache: the last pages and searches, so Back shows them at once
- Settings: text size, history, recent searches and the sites that refuse
  simple browsers, kept in one small file
- find_block: finding words in a page
- QUICK_SEARCHES: searches inside the sites a printer owner reads most
- download_print_file: a .gcode link saved into the printer's files, with
  every check that keeps a printer safe (size, free space, not while printing)
"""
import json
import os
import re
import time
from collections import OrderedDict
from urllib.parse import unquote, urlparse

SETTINGS_PATH = '/useremain/home/rinkhals/lemsearch.json'
GCODE_DIR = '/useremain/app/gk/gcodes'          # bind-mounted where Moonraker and the printer see it

MAX_HISTORY = 30
MAX_SEARCHES = 10
MAX_BLOCKED = 200
TEXT_SCALES = (0.85, 1.0, 1.15, 1.3, 1.5)       # A- / A+ steps


# --- 1. Back shows pages from memory ------------------------------------------------

class PageCache:
    """The last few pages (or search results) by address, newest kept.

    A page is a few hundred small dicts, so a handful costs little; reading one
    again costs seconds of download and parsing on the printer.
    """

    def __init__(self, size=5, max_age=600, clock=time.monotonic):
        self.size, self.max_age, self.clock = size, max_age, clock
        self._items = OrderedDict()

    def get(self, url):
        item = self._items.get(url)
        if item is None:
            return None
        stored, value = item
        if self.clock() - stored > self.max_age:
            del self._items[url]
            return None
        self._items.move_to_end(url)
        return value

    def put(self, url, value):
        self._items[url] = (self.clock(), value)
        self._items.move_to_end(url)
        while len(self._items) > self.size:
            self._items.popitem(last=False)

    def clear(self):
        self._items.clear()

    def __len__(self):
        return len(self._items)


# --- 2, 5, 6. What is kept between visits ----------------------------------------------

def domain_of(url):
    host = urlparse(url or '').netloc.lower().split('@')[-1].split(':')[0]
    return host[4:] if host.startswith('www.') else host


class Settings:
    """lemsearch.json: text size, history, recent searches, refusing sites.

    Every change is written at once, through a temporary file and a rename,
    so a power cut leaves the old file or the new one, never half of one.
    A missing or broken file reads as nothing saved yet.
    """

    def __init__(self, path=None):
        self.path = path or SETTINGS_PATH
        self.data = self._load()

    def _load(self):
        try:
            with open(self.path, 'r') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            temporary = self.path + '.new'
            with open(temporary, 'w') as f:
                json.dump(self.data, f)
            os.replace(temporary, self.path)
        except OSError:
            pass   # a full or read-only disk must not break browsing

    # text size
    def text_scale(self):
        value = self.data.get('text_scale', 1.0)
        return value if value in TEXT_SCALES else 1.0

    def change_text_scale(self, step):
        """step -1 or +1. Returns the new scale (unchanged at either end)."""
        index = TEXT_SCALES.index(self.text_scale())
        index = max(0, min(len(TEXT_SCALES) - 1, index + step))
        self.data['text_scale'] = TEXT_SCALES[index]
        self._save()
        return TEXT_SCALES[index]

    # history
    def history(self):
        """[(title, url)], newest first."""
        items = self.data.get('history') or []
        return [(str(i[0])[:80], i[1]) for i in items
                if isinstance(i, list) and len(i) == 2 and str(i[1]).startswith(('http://', 'https://'))]

    def add_history(self, title, url):
        if not str(url).startswith(('http://', 'https://')):
            return
        items = [[t, u] for t, u in self.history() if u != url]
        self.data['history'] = [[(title or url)[:80], url]] + items[:MAX_HISTORY - 1]
        self._save()

    def searches(self):
        return [str(s)[:120] for s in (self.data.get('searches') or []) if isinstance(s, str) and s.strip()]

    def add_search(self, words):
        words = (words or '').strip()
        if not words:
            return
        items = [s for s in self.searches() if s.lower() != words.lower()]
        self.data['searches'] = [words[:120]] + items[:MAX_SEARCHES - 1]
        self._save()

    def clear_history(self):
        self.data['history'] = []
        self.data['searches'] = []
        self._save()

    # sites that refuse simple browsers
    def blocked(self):
        return set(d for d in (self.data.get('blocked') or []) if isinstance(d, str))

    def is_blocked(self, url):
        return domain_of(url) in self.blocked()

    def remember_blocked(self, url):
        domain = domain_of(url)
        if not domain or domain in self.blocked():
            return
        items = [d for d in (self.data.get('blocked') or []) if isinstance(d, str)]
        self.data['blocked'] = (items + [domain])[-MAX_BLOCKED:]
        self._save()

    def forget_blocked(self, url):
        """A site that opened after all (it changed its mind)."""
        domain = domain_of(url)
        items = [d for d in (self.data.get('blocked') or []) if isinstance(d, str)]
        if domain in items:
            self.data['blocked'] = [d for d in items if d != domain]
            self._save()


# --- 4. Find in page ---------------------------------------------------------------------

def find_block(blocks, words, after=-1):
    """Index of the first block after `after` whose text has the words (any case), else None.

    Searching again from the last match finds the next one; after the last
    match it starts over from the top.
    """
    words = (words or '').strip().lower()
    if not words:
        return None
    for start, stop in ((after + 1, len(blocks)), (0, min(after + 1, len(blocks)))):
        for i in range(start, stop):
            if words in (blocks[i].get('text') or '').lower():
                return i
    return None


def count_matches(blocks, words):
    words = (words or '').strip().lower()
    return sum(1 for b in blocks if words and words in (b.get('text') or '').lower())


# --- 7. Searches inside the sites a printer owner reads ---------------------------------------

QUICK_SEARCHES = (
    ('Klipper docs', 'klipper3d.org'),
    ('Anycubic Wiki', 'wiki.anycubic.com'),
    ('Mainsail docs', 'docs.mainsail.xyz'),
    ('Moonraker docs', 'moonraker.readthedocs.io'),
)


def quick_search_words(site, words):
    """'pressure advance' in klipper3d.org -> 'site:klipper3d.org pressure advance'."""
    words = (words or '').strip()
    return f'site:{site} {words}'.strip() if words else ''


# --- 8. Print files from the web ----------------------------------------------------------

PRINT_EXTENSIONS = ('.gcode', '.gco', '.g')
MAX_PRINT_FILE_BYTES = 200 * 1024 * 1024    # bigger than any print a Kobra makes in practice
FREE_MARGIN_BYTES = 100 * 1024 * 1024       # left free on the disk after the download


class DownloadError(Exception):
    """A reason, fine to show on the touch screen, why a file was not saved."""


def is_print_file(url):
    path = unquote(urlparse(url or '').path).lower()
    return path.endswith(PRINT_EXTENSIONS)


def print_file_name(url, existing=()):
    """A safe name for the file in the printer's folder, not overwriting one that is there.

    Only letters, digits, - _ . and spaces; no folders, no hidden files.
    """
    name = os.path.basename(unquote(urlparse(url or '').path)) or 'download.gcode'
    stem, ext = os.path.splitext(name)
    stem = re.sub(r'[^\w\- .]', '_', stem).strip(' .') or 'download'
    ext = ext.lower() if ext.lower() in PRINT_EXTENSIONS else '.gcode'
    stem = stem[:80]
    candidate, n = stem + ext, 2
    taken = set(existing)
    while candidate in taken:
        candidate = f'{stem} ({n}){ext}'
        n += 1
    return candidate


MOONRAKER_PRINT_STATE = 'http://127.0.0.1:7125/printer/objects/query?print_stats'


def printer_busy(fetch=None):
    """True while printing or paused, and also when that can't be told.

    A download writes megabytes to the printer's disk and keeps its single
    weak CPU busy; during a print that risks the print. When Moonraker does
    not answer, nobody can say the printer is idle, so the download waits.
    fetch() returns Moonraker's JSON answer (tests pass their own).
    """
    if fetch is None:
        def fetch():
            import urllib.request
            with urllib.request.urlopen(MOONRAKER_PRINT_STATE, timeout=2) as r:
                return json.loads(r.read(65536))
    try:
        state = fetch()['result']['status']['print_stats']['state']
    except Exception:
        return True
    return str(state).lower() in ('printing', 'paused')


def free_bytes(path):
    stat = os.statvfs(path)
    return stat.f_bavail * stat.f_frsize


def download_print_file(url, folder=None, get=None, printing=lambda: False, free=free_bytes,
                        progress=None, user_agent='LemSearchLite', name_for=None, max_bytes=None):
    """Save a print file into the printer's files. Returns the path.

    Refused (DownloadError) while printing, when the file is too big or the
    disk would be left with less than FREE_MARGIN_BYTES. Written to a hidden
    temporary file first and renamed at the end, so the printer never lists a
    half-downloaded file; a failed download leaves nothing behind.
    progress(done, total) is called as it goes (total may be None).
    """
    folder = folder or GCODE_DIR
    name_for = name_for or print_file_name
    max_bytes = max_bytes or MAX_PRINT_FILE_BYTES
    if printing():
        raise DownloadError('The printer is printing. Download the file when it is done.')
    if get is None:
        import requests
        get = requests.get
    if not os.path.isdir(folder):
        raise DownloadError('The printer\'s file folder was not found.')
    try:
        response = get(url, stream=True, timeout=(6, 30), headers={'User-Agent': user_agent})
    except Exception as e:
        raise DownloadError(f'Could not reach the file: {type(e).__name__}')
    temporary = None
    try:
        if response.status_code >= 400:
            raise DownloadError(f'The server answered {response.status_code}')
        kind = (response.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        if kind.startswith('text/html'):
            raise DownloadError('This link leads to a web page, not to a print file.')
        total = response.headers.get('Content-Length')
        total = int(total) if total and str(total).isdigit() else None
        if total and total > max_bytes:
            raise DownloadError(f'The file is too big ({total // (1024 * 1024)} MB).')
        room = free(folder) - FREE_MARGIN_BYTES
        if total and total > room:
            raise DownloadError('There is not enough free space on the printer for this file.')
        name = name_for(url, os.listdir(folder))
        temporary = os.path.join(folder, f'.{name}.part')
        done = 0
        with open(temporary, 'wb') as f:
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                done += len(chunk)
                if done > max_bytes:
                    raise DownloadError('The file is too big.')
                if done > room:
                    raise DownloadError('There is not enough free space on the printer for this file.')
                f.write(chunk)
                if progress:
                    progress(done, total)
        if total and done < total:
            raise DownloadError('The download was cut off. Try again.')
        if printing():
            raise DownloadError('A print started while downloading; the file was not kept.')
        target = os.path.join(folder, name)
        os.replace(temporary, target)
        temporary = None
        return target
    finally:
        if temporary and os.path.exists(temporary):
            os.remove(temporary)
        close = getattr(response, 'close', None)
        if close:
            close()
