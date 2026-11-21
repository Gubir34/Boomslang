"""The print screen's talk with the printer, through Moonraker (off by default).

Moonraker on Boomslang already runs prints on the Kobras: its Kobra component turns
SDCARD_PRINT_FILE into the printer's own print command, the same path Mainsail uses.
This module only reads the state, lists the printer's files and sends the few
requests the screen needs. Plain Python and no LVGL, so it is tested on its own.

Safety: a print starts only when the printer is idle and cool enough to be told
(browser_tools.printer_busy); cancelling asks first (on the screen); temperatures
are capped at the same limits the slicer's safety check uses.
"""
import json
import urllib.parse

MOONRAKER = 'http://127.0.0.1:7125'
STATUS_QUERY = 'print_stats&display_status&extruder&heater_bed&virtual_sdcard'
MAX_NOZZLE = 260
MAX_BED = 110
PRESETS = {'PLA': (210, 60), 'PETG': (240, 75), 'ABS': (250, 100)}
FILE_SUFFIXES = ('.gcode', '.gco', '.g')


class PrintError(Exception):
    """Shown on the screen as it is."""


def _http(method, path, timeout=4):
    import urllib.request
    request = urllib.request.Request(MOONRAKER + path, method=method, data=b'' if method == 'POST' else None)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(1 << 20) or b'{}')


def _number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def read_status(http=_http):
    """The printer now, as plain values; None when Moonraker can't be read."""
    try:
        status = http('GET', f'/printer/objects/query?{STATUS_QUERY}')['result']['status']
    except Exception:
        return None
    stats = status.get('print_stats') or {}
    extruder, bed = status.get('extruder') or {}, status.get('heater_bed') or {}
    progress = _number((status.get('display_status') or {}).get('progress'))
    if progress is None:
        progress = _number((status.get('virtual_sdcard') or {}).get('progress'))
    info = stats.get('info') if isinstance(stats.get('info'), dict) else {}
    return {
        'state': str(stats.get('state') or '').lower(),
        'file': str(stats.get('filename') or ''),
        'progress': max(0.0, min(1.0, progress)) if progress is not None else None,
        'elapsed': _number(stats.get('print_duration')),
        'layer': info.get('current_layer'), 'layers': info.get('total_layer'),
        'nozzle': _number(extruder.get('temperature')), 'nozzle_target': _number(extruder.get('target')),
        'bed': _number(bed.get('temperature')), 'bed_target': _number(bed.get('target')),
    }


def busy(status):
    return bool(status) and status['state'] in ('printing', 'paused')


def remaining(status):
    """Seconds left from the time printed so far and the progress, or None early on."""
    if not status or not status.get('elapsed') or not status.get('progress') or status['progress'] < 0.02:
        return None
    return status['elapsed'] * (1 - status['progress']) / status['progress']


def duration_text(seconds):
    if seconds is None:
        return ''
    minutes = int(seconds // 60)
    return f'{minutes // 60} h {minutes % 60} min' if minutes >= 60 else f'{minutes} min'


def temperature_text(actual, target):
    if actual is None:
        return '-'
    return f'{actual:.0f}/{target:.0f}°C' if target else f'{actual:.0f}°C'


def list_files(http=_http, limit=40):
    """The printer's print files, newest first: [(path, size in bytes, modified)]."""
    try:
        items = http('GET', '/server/files/list?root=gcodes')['result']
    except Exception:
        raise PrintError('Could not read the printer\'s files.')
    files = [(f.get('path') or f.get('filename'), f.get('size') or 0, f.get('modified') or 0)
             for f in items if isinstance(f, dict)]
    files = [f for f in files if isinstance(f[0], str) and f[0].lower().endswith(FILE_SUFFIXES)
             and not any(part.startswith('.') for part in f[0].split('/'))]
    return sorted(files, key=lambda f: f[2], reverse=True)[:limit]


def start(path, printer_busy, http=_http):
    """Print a file from the printer's files. printer_busy() must say the printer is idle."""
    if not path or path.startswith('/') or '..' in path.split('/'):
        raise PrintError('That is not one of the printer\'s files.')
    if printer_busy():
        raise PrintError('The printer is busy or heating. Try again when it is idle.')
    try:
        http('POST', '/printer/print/start?' + urllib.parse.urlencode({'filename': path}))
    except Exception:
        raise PrintError('The printer did not take the print.')


def command(action, http=_http):
    """pause, resume or cancel the running print."""
    if action not in ('pause', 'resume', 'cancel'):
        raise ValueError(action)
    try:
        http('POST', f'/printer/print/{action}')
    except Exception:
        raise PrintError(f'The printer did not {action}.')


def set_temperatures(nozzle=None, bed=None, http=_http):
    """Set targets in °C (0 turns a heater off), within the printer's safe limits."""
    lines = []
    for value, limit, code in ((nozzle, MAX_NOZZLE, 'M104'), (bed, MAX_BED, 'M140')):
        if value is None:
            continue
        if not isinstance(value, (int, float)) or value < 0 or value > limit:
            raise PrintError(f'{value} °C is outside 0 to {limit} °C.')
        lines.append(f'{code} S{int(value)}')
    if not lines:
        return
    try:
        http('POST', '/printer/gcode/script?' + urllib.parse.urlencode({'script': '\n'.join(lines)}))
    except Exception:
        raise PrintError('The printer did not take the temperature.')
