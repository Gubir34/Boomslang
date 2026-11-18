"""What the touch UI shows for an app's settings, worked out from its app.json without a screen.

An app's "properties" in app.json describe its settings:

    "interval_hours": {"display": "Back up every N hours", "type": "number", "default": "24"}
    "include_database": {"display": "...", "type": "enum", "options": ["False", "True"], "default": "True"}
    "status": {"display": "Last backup", "type": "report"}
    "advanced": true                                   (on any of them: shown under "Advanced")

setting_rows() turns them into rows that say which control each one gets:

    switch    an enum of exactly False/True (any case): an on/off switch
    choice    any other enum: the value, and a list to pick from
    number    the value, with - and + buttons, and a keypad
    text      the value, and a keyboard
    report    a value the app writes, read only (hidden while it is empty)
    qr        a link the app writes, shown as a QR code (hidden while it is empty)

Kept free of LVGL so it is tested on a PC (tests/test_app_settings.py).
"""

KINDS = ('switch', 'choice', 'number', 'text', 'report', 'qr')
EDITABLE = ('switch', 'choice', 'number', 'text')


def is_switch(options):
    """Whether an enum's options are exactly False and True, in any case and order."""
    return isinstance(options, (list, tuple)) and len(options) == 2 and \
        sorted(str(o).strip().lower() for o in options) == ['false', 'true']


def is_on(value):
    return str(value or '').strip().lower() == 'true'


def switch_value(options, on):
    """The option to store for a switch, spelled the way app.json spells it ("True", "true" ...)."""
    wanted = 'true' if on else 'false'
    for option in options or ():
        if str(option).strip().lower() == wanted:
            return str(option)
    return 'True' if on else 'False'


def setting_rows(properties, get_value):
    """The rows of an app's settings screen, in app.json's order.

    get_value(key) is the value saved for the app ('' or None when there is
    none); the default from app.json is shown then. A property of an unknown
    type, or that is not an object, is left out rather than breaking the screen.
    """
    rows = []
    if not isinstance(properties, dict):
        return rows
    for key, spec in properties.items():
        if not isinstance(spec, dict):
            continue
        kind = spec.get('type')
        options = [str(o) for o in (spec.get('options') or [])]
        if kind == 'enum':
            kind = 'switch' if is_switch(options) else 'choice'
        if kind not in KINDS:
            continue
        default = spec.get('default')
        saved = get_value(key)
        value = saved if saved not in (None, '', 'null') else default
        rows.append({
            'key': key,
            'title': str(spec.get('display') or key),
            'kind': kind,
            'value': '' if value is None else str(value),
            'default': '' if default is None else str(default),
            'options': options,
            'advanced': bool(spec.get('advanced')),
        })
    return rows


def visible(row):
    """Reports and QR codes are only shown once the app has written something."""
    return row['kind'] in EDITABLE or bool(row['value'])


def split_advanced(rows):
    """(the everyday rows, the advanced ones), both without hidden rows."""
    shown = [row for row in rows if visible(row)]
    return [row for row in shown if not row['advanced']], [row for row in shown if row['advanced']]


def step_number(value, delta):
    """value + delta, as text. Whole numbers stay whole; text that is not a number starts from 0."""
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        number = 0.0
    result = number + delta
    if result == int(result) and '.' not in str(value or '').strip():
        return str(int(result))
    return f'{result:.10g}'


def value_text(row):
    """How a row's value reads on screen."""
    if row['kind'] == 'switch':
        return 'On' if is_on(row['value']) else 'Off'
    return row['value'] if row['value'] != '' else 'Not set'


def status_text(enabled, started, version=''):
    """The line under an app's name in the list: 'Running · v1.2', 'Stopped', 'Off'."""
    if started:
        state = 'Running'
    elif enabled:
        state = 'Stopped'
    else:
        state = 'Off'
    version = str(version or '').strip()
    return f'{state} · v{version}' if version else state
