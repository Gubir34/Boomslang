"""Small pieces of the touch UI that need no screen, so they are tested on a PC.

- which installed version "Go back to the previous version" would start
- the one-time message after an automatic update
- the status line on the home screen
- the topic for phone notifications
- the browser's bookmarks
- which look (theme) the home screen uses
"""
import json
import os
import re
import secrets
import time

from release_assets import display_version

CLASSIC_UI_FLAG = '/useremain/rinkhals/.classic-ui'
AERO_SIZE = (800, 480)   # the Aero mockups are drawn for exactly this screen (Kobra S1 and S1 Max)
UPDATE_NOTICE_PATH = '/useremain/rinkhals/.auto-update-notice'
BOOKMARKS_PATH = '/useremain/home/rinkhals/browser-bookmarks.json'
MAX_BOOKMARKS = 30


# --- previous version --------------------------------------------------------

def _read(path):
    try:
        with open(path, 'r') as f:
            return f.read().strip()
    except OSError:
        return ''


def previous_install(base, current_folder):
    """The installed version to go back to: (folder name, version), or None.

    The installer keeps the version it replaced. A folder counts when it is
    complete enough to start (the same files update.sh insists on) and is not
    the running one; the most recently installed of those is the previous one.
    """
    candidates = []
    try:
        entries = list(os.scandir(base))
    except OSError:
        return None
    for entry in entries:
        if not entry.is_dir(follow_symlinks=False) or entry.name == current_folder or entry.name.startswith('.'):
            continue
        version = _read(os.path.join(entry.path, '.version'))
        complete = (version and os.path.isfile(os.path.join(entry.path, 'start.sh')) and
                    os.path.exists(os.path.join(entry.path, 'usr/bin/python')) and
                    os.path.isdir(os.path.join(entry.path, 'opt/rinkhals')))
        if complete:
            candidates.append((os.path.getmtime(os.path.join(entry.path, '.version')), entry.name, version))
    if not candidates:
        return None
    _, folder, version = max(candidates)
    return folder, version


AUTO_UPDATE_TRIED_PATH = '/useremain/rinkhals/.auto-update-tried'


def keep_from_auto_install(version, path=None):
    """Tell the automatic updater not to install this version again.

    Going back from a version would be pointless if the updater put it
    straight back ten minutes later. It can still be installed by hand.
    """
    with open(path or AUTO_UPDATE_TRIED_PATH, 'w') as f:
        f.write((version or '').strip() + '\n')


def select_install(base, folder):
    """Make folder the version that starts at the next boot.

    Written through a temporary file and a rename, so a power cut leaves
    either the old or the new choice, never an empty .version.
    """
    if not folder or '/' in folder or not os.path.isdir(os.path.join(base, folder)):
        raise ValueError(f'{folder} is not an installed version')
    target = os.path.join(base, '.version')
    temporary = target + '.new'
    with open(temporary, 'w') as f:
        f.write(folder + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, target)


# --- message after an automatic update -----------------------------------------

def take_update_notice(current_version, path=None):
    """The message to show once after an automatic update, or None.

    The web portal's updater leaves {"from", "to"} before it installs. The
    file is removed here, so the message is shown a single time.
    """
    path = path or UPDATE_NOTICE_PATH
    try:
        with open(path, 'r') as f:
            notice = json.load(f)
        os.remove(path)
    except (OSError, ValueError):
        return None
    if not isinstance(notice, dict) or not notice.get('to'):
        return None
    old, new = display_version(notice.get('from') or '?'), display_version(notice['to'])
    if notice['to'] == current_version:
        return (f'Boomslang updated itself\nto {new}\n(from {old}).\n\n'
                'What changed is in\nUpdates. Automatic updates\ncan be turned off in Settings.')
    return (f'An automatic update to\n{new}\ndid not complete.\n\n'
            f'The printer is still on\n{display_version(current_version)}.\n'
            'It will not be tried again;\ninstall it from Updates.')


def short_model(model):
    """'Anycubic Kobra S1' -> 'Kobra S1': the header has room for the model and the address,
    and cutting the long name kept 'Anycubic Kobr...1' and lost what tells the printers apart."""
    return re.sub(r'^\s*Anycubic\s+', '', model or '').strip()


# --- home screen status line ---------------------------------------------------

STATUS_QUERY = 'extruder&heater_bed&print_stats&display_status'
STATE_NAMES = {'standby': 'Idle', 'complete': 'Finished', 'cancelled': 'Cancelled', 'printing': 'Printing',
               'paused': 'Paused', 'error': 'Error'}


def _temperature(heater):
    if not isinstance(heater, dict) or not isinstance(heater.get('temperature'), (int, float)):
        return None
    text = f'{heater["temperature"]:.0f}'
    target = heater.get('target')
    if isinstance(target, (int, float)) and target > 0:
        text += f'/{target:.0f}'
    return text + '°C'


def format_status(status):
    """Moonraker's objects/query status -> 'Nozzle 210/215°C · Bed 60°C · Printing 42%'."""
    if not isinstance(status, dict):
        return ''
    parts = []
    for label, key in (('Nozzle', 'extruder'), ('Bed', 'heater_bed')):
        temperature = _temperature(status.get(key))
        if temperature:
            parts.append(f'{label} {temperature}')
    state = (status.get('print_stats') or {}).get('state') or ''
    name = STATE_NAMES.get(state, state.capitalize())
    progress = (status.get('display_status') or {}).get('progress')
    if state in ('printing', 'paused') and isinstance(progress, (int, float)):
        name += f' {max(0, min(100, round(progress * 100)))}%'
    if name:
        parts.append(name)
    return ' · '.join(parts)


def fetch_status(timeout=2):
    """Read the printer status from Moonraker; '' when it can't be read."""
    import urllib.request
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:7125/printer/objects/query?{STATUS_QUERY}', timeout=timeout) as r:
            return format_status(json.loads(r.read(65536)).get('result', {}).get('status'))
    except Exception:
        return ''


# --- phone notifications --------------------------------------------------------

def new_ntfy_topic():
    """A topic nobody can guess: whoever knows it can read the notifications."""
    return 'boomslang-' + secrets.token_hex(10)


def valid_ntfy_topic(topic):
    return bool(re.fullmatch(r'[A-Za-z0-9_-]{1,64}', topic or ''))


def ntfy_link(server, topic):
    return f'{(server or "https://ntfy.sh").rstrip("/")}/{topic}'


# --- browser bookmarks ------------------------------------------------------------

def load_bookmarks(path=None):
    """[(name, url)] saved by the user, oldest first."""
    path = path or BOOKMARKS_PATH
    try:
        with open(path, 'r') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        if (isinstance(item, dict) and isinstance(item.get('url'), str) and
                item['url'].startswith(('http://', 'https://'))):
            out.append((str(item.get('name') or item['url'])[:80], item['url']))
    return out[:MAX_BOOKMARKS]


def save_bookmarks(bookmarks, path=None):
    path = path or BOOKMARKS_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + '.new'
    with open(temporary, 'w') as f:
        json.dump([{'name': name, 'url': url, 'added': int(time.time())} for name, url in bookmarks[:MAX_BOOKMARKS]], f)
    os.replace(temporary, path)


def is_bookmarked(url, path=None):
    return any(u == url for _, u in load_bookmarks(path))


def toggle_bookmark(name, url, path=None):
    """Add the page, or remove it when it is already saved. Returns True when it is now saved."""
    bookmarks = load_bookmarks(path)
    if any(u == url for _, u in bookmarks):
        save_bookmarks([(n, u) for n, u in bookmarks if u != url], path)
        return False
    bookmarks.append(((name or url)[:80], url))
    save_bookmarks(bookmarks[-MAX_BOOKMARKS:], path)
    return True


# --- the look of the home screen ------------------------------------------------

THEME_FILE = '/useremain/rinkhals/.ui-theme'
THEMES = ('classic', 'aero', 'liquid')
THEME_NAMES = {'classic': 'Classic', 'aero': 'Aero', 'liquid': 'Liquid Plastic'}
DEFAULT_THEME = 'aero'


def aero_possible(width, height):
    """Aero and Liquid Plastic are drawn for an 800x480 screen; any other screen keeps the Classic look."""
    return (width, height) == AERO_SIZE


def theme_for(width, height, path=None, legacy=None):
    """Which look the home screen has: 'classic', 'aero' or 'liquid'.

    The choice is the name in THEME_FILE. Before there were three looks,
    Settings > Switch to Classic UI left an empty flag file (CLASSIC_UI_FLAG);
    that still means Classic. With neither file, Aero. A screen the other looks
    are not drawn for is always Classic.
    """
    if not aero_possible(width, height):
        return 'classic'
    try:
        with open(path or THEME_FILE) as f:
            chosen = f.read().strip().lower()
        if chosen in THEMES:
            return chosen
    except OSError:
        pass
    if os.path.exists(legacy or CLASSIC_UI_FLAG):
        return 'classic'
    return DEFAULT_THEME


MODE_FILE = '/useremain/rinkhals/.ui-mode'
MODES = ('dark', 'light')
MODE_NAMES = {'dark': 'Dark', 'light': 'Light'}


def mode(path=None):
    """'dark' (what Boomslang always was, and what an unreadable choice means) or 'light'."""
    try:
        with open(path or MODE_FILE) as f:
            chosen = f.read().strip().lower()
        return chosen if chosen in MODES else 'dark'
    except OSError:
        return 'dark'


def set_mode(name, path=None):
    if name not in MODES:
        raise ValueError(f'unknown mode {name!r}')
    with open(path or MODE_FILE, 'w') as f:
        f.write(name + '\n')


def set_theme(name, path=None, legacy=None):
    if name not in THEMES:
        raise ValueError(f'unknown look {name!r}')
    with open(path or THEME_FILE, 'w') as f:
        f.write(name + '\n')
    try:
        os.remove(legacy or CLASSIC_UI_FLAG)   # the old flag must not be read next to the new choice
    except FileNotFoundError:
        pass
