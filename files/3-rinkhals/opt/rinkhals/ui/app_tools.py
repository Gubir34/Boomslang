"""Read-only app helpers in Python, mirroring tools.sh.

The touch UI used to call every tools.sh helper through a new shell that
sourced tools.sh first, which itself runs realpath, cat and sed on every
load. Listing the apps and their properties meant dozens of process spawns
on a single-core printer, which is a large part of why the UI felt slow.

These read the same files with the same rules as tools.sh (list_apps,
get_app_root, is_app_enabled, get_app_property). Anything they cannot read
the way jq would falls back to the shell version, so the result is never
different from before, only faster. Helpers that change state (enable_app,
start_app, set_app_property, ...) stay in tools.sh.
"""
import json
import os
import re


class AppTools:
    def __init__(self, rinkhals_root, rinkhals_home, shell_fallback=None,
                 temporary_app_path='/tmp/rinkhals/apps'):
        self.builtin_app_path = f'{rinkhals_root}/home/rinkhals/apps'
        self.user_app_path = f'{rinkhals_home}/apps'
        self.rinkhals_home = rinkhals_home
        self.temporary_app_path = temporary_app_path
        self.shell_fallback = shell_fallback

    # list_apps: directory names from both app paths, sort -uV, space separated
    def list_apps(self):
        names = set()
        for path in (self.builtin_app_path, self.user_app_path):
            try:
                with os.scandir(path) as entries:
                    names.update(e.name for e in entries if e.is_dir(follow_symlinks=False))
            except OSError:
                pass
        return ' '.join(sorted(names, key=_version_key))

    def get_app_root(self, app):
        user_root = f'{self.user_app_path}/{app}'
        if os.path.exists(user_root):
            return user_root
        return f'{self.builtin_app_path}/{app}'

    def is_app_enabled(self, app):
        root = self.get_app_root(app)
        home = f'{self.rinkhals_home}/apps/{app}'
        enabled = os.path.isfile(f'{root}/.enabled') or os.path.isfile(f'{home}.enabled')
        disabled = os.path.isfile(f'{root}/.disabled') or os.path.isfile(f'{home}.disabled')
        return '1' if enabled and not disabled else '0'

    def are_apps_enabled(self):
        return {app: self.is_app_enabled(app) for app in self.list_apps().split()}

    def get_app_property(self, app, property):
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', str(property)):
            return self._fallback('get_app_property', app, property)

        try:
            value = _read_property(f'{self.temporary_app_path}/{app}.config', [property])
            if value in ('', 'null'):
                value = _read_property(f'{self.user_app_path}/{app}.config', [property])
            if value == 'null':
                value = ''
            if value == '':
                value = _read_property(f'{self.get_app_root(app)}/app.json',
                                       ['properties', property, 'default'])
                if value == 'null':
                    value = ''
        except _NotLikeJq:
            return self._fallback('get_app_property', app, property)

        # tools.sh ends with an unquoted `echo $VALUE`, which collapses whitespace
        return ' '.join(value.split())

    def _fallback(self, function, *args):
        if not self.shell_fallback:
            return ''
        return self.shell_fallback(function, *args)


class _NotLikeJq(Exception):
    """The file exists but can't be read the way `jq -r` would read it."""


def _read_property(path, keys):
    """`cat path | jq -r .a.b.c` for a missing file, an object path or null."""
    try:
        with open(path, 'r') as f:
            text = f.read()
    except FileNotFoundError:
        return ''
    except OSError:
        raise _NotLikeJq()

    if not text.strip():
        return ''
    try:
        value = json.loads(text)
    except ValueError:
        raise _NotLikeJq()

    for key in keys:
        if value is None:
            return 'null'
        if not isinstance(value, dict):
            raise _NotLikeJq()
        value = value.get(key)

    return _jq_raw(value)


def _jq_raw(value):
    if value is None:
        return 'null'
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    # Floats, arrays and objects: jq's formatting differs from Python's in
    # small ways, let the shell answer
    raise _NotLikeJq()


def _version_key(name):
    # GNU/BusyBox `sort -V` compares runs of digits numerically
    return [(0, int(part), '') if part.isdigit() else (1, 0, part)
            for part in re.split(r'(\d+)', name) if part != '']
