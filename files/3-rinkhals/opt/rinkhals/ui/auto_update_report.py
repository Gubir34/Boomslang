"""What the automatic updater did, read for the touch screen's Updates page.

Boomslang Web (autoupdate_report.go) leaves two files:

  .auto-update-status   the last check: up to date, a release waiting for the
                        update hours or for the printer, an error
  .auto-update-history  the automatic installs (the last 20), each with whether
                        the printer came back on the new version

Plain Python and no LVGL, so it is tested on its own.
"""
import json
from datetime import datetime, timezone

from release_assets import display_version

STATUS_PATH = '/useremain/rinkhals/.auto-update-status'
HISTORY_PATH = '/useremain/rinkhals/.auto-update-history'


def _read(path, kind):
    try:
        with open(path) as f:
            value = json.load(f)
        return value if isinstance(value, kind) else None
    except (OSError, ValueError):
        return None


def read_status(path=None):
    return _read(path or STATUS_PATH, dict)


def read_history(path=None):
    history = _read(path or HISTORY_PATH, list) or []
    return [e for e in history if isinstance(e, dict) and e.get('to')]


def _when(stamp, now=None):
    """'14:02' today, 'Yesterday 14:02', else '18 Nov 14:02', in the printer's local time."""
    try:
        moment = datetime.fromisoformat(str(stamp).replace('Z', '+00:00')).astimezone()
    except ValueError:
        return '?'
    now = (now or datetime.now(timezone.utc)).astimezone()
    days = (now.date() - moment.date()).days
    clock = moment.strftime('%H:%M')
    if days == 0:
        return clock
    if days == 1:
        return f'Yesterday {clock}'
    return f'{moment.day} {moment.strftime("%b")} {clock}'


def status_line(status, now=None):
    """The last check, in a few words."""
    if not status:
        return 'Not checked yet'
    state = status.get('state')
    available = display_version(status.get('available') or '')
    checked = _when(status.get('checked'), now)
    if state == 'off':
        return 'Off'
    if state == 'up-to-date':
        return f'Up to date · {checked}'
    if state == 'waiting-hours':
        return f'{available} waits for update hours'
    if state == 'waiting-idle':
        return f'{available} waits for idle printer'
    if state == 'waiting-install':
        return f'{available} waits for an install'
    if state == 'failed':
        return f'{available} failed · {checked}'
    return f'Could not check · {checked}'


def last_update_line(history, now=None):
    if not history:
        return 'None yet'
    last = history[-1]
    mark = 'installed' if last.get('result') == 'installed' else 'failed'
    return f'{display_version(last["to"])} {mark} · {_when(last.get("time"), now)}'


def details(status, history, now=None):
    """Everything, for the dialog behind the summary: the last check and the installs, newest first."""
    lines = [f'Last check: {status_line(status, now)}']
    if status and status.get('message') and status.get('state') not in ('up-to-date', 'off'):
        lines.append(status['message'])
    lines.append('')
    if not history:
        lines.append('No automatic updates yet.')
    for entry in reversed(history[-5:]):
        ok = entry.get('result') == 'installed'
        lines.append(f'{_when(entry.get("time"), now)}: {display_version(entry.get("from") or "?")} to '
                     f'{display_version(entry["to"])} {"installed" if ok else "FAILED"}')
    return '\n'.join(lines)
