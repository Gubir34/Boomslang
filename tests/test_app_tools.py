"""The touch UI's Python app helpers must answer exactly like tools.sh.

Builds a fake Boomslang root and home with built-in and user apps, then
compares app_tools.AppTools against the real tools.sh functions run with
/bin/sh and jq.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS_SH = REPO / 'files/3-rinkhals/tools.sh'
spec = importlib.util.spec_from_file_location(
    'testsupport.app_tools', REPO / 'files/3-rinkhals/opt/rinkhals/ui/app_tools.py')
app_tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_tools)


class AppToolsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.root = base / 'root'
        self.home = base / 'home'
        self.tmp_apps = base / 'tmp-apps'
        builtin = self.root / 'home/rinkhals/apps'
        user = self.home / 'apps'
        for path in (builtin, user, self.tmp_apps):
            path.mkdir(parents=True)

        def app(parent, name, properties=None, raw=None):
            (parent / name).mkdir()
            if raw is not None:
                (parent / name / 'app.json').write_text(raw)
            elif properties is not None:
                (parent / name / 'app.json').write_text(json.dumps({'properties': properties}))
            return parent / name

        app(builtin, '10-hostname-dns', {'hostname': {'default': 'kobra'},
                                         'dhcp': {'default': True}})
        app(builtin, '25-mainsail', {'port': {'default': 4409}})
        app(builtin, '40-moonraker', {'mode': {'default': None}})
        app(builtin, '9-early', {})
        app(builtin, '100-late', {})
        overridden = app(builtin, '60-shared', {'who': {'default': 'builtin'}})
        app(user, '60-shared', {'who': {'default': 'user'}})
        app(user, 'octoeverywhere', {'token': {'default': ''}})
        app(user, 'comments', raw='{ // not JSON\n "properties": {} }')
        (user / 'not-an-app.config').write_text('{}')

        # Enabled / disabled markers in both places tools.sh looks
        (overridden / '.enabled').touch()
        (builtin / '25-mainsail' / '.enabled').touch()
        (user / '10-hostname-dns.enabled').touch()
        (user / '40-moonraker.enabled').touch()
        (user / '40-moonraker.disabled').touch()
        (user / 'octoeverywhere' / '.enabled').touch()

        # Configs: user and temporary, including values jq formats itself
        (user / '10-hostname-dns.config').write_text(json.dumps({'hostname': 'printer  one', 'empty': ''}))
        (self.tmp_apps / '10-hostname-dns.config').write_text(json.dumps({'hostname': None}))
        (user / '25-mainsail.config').write_text(json.dumps({'port': 80, 'ratio': 0.5, 'list': [1, 2]}))
        (self.tmp_apps / '25-mainsail.config').write_text(json.dumps({'port': 8080}))
        (user / 'octoeverywhere.config').write_text('not json at all')

        self.tools = app_tools.AppTools(str(self.root), str(self.home),
                                        shell_fallback=self.shell, temporary_app_path=str(self.tmp_apps))

    def tearDown(self):
        self._tmp.cleanup()

    def shell(self, function, *args):
        script = (f'. "{TOOLS_SH}" > /dev/null 2>&1; '
                  f'RINKHALS_ROOT="{self.root}"; RINKHALS_HOME="{self.home}"; '
                  f'BUILTIN_APP_PATH="$RINKHALS_ROOT/home/rinkhals/apps"; USER_APP_PATH="$RINKHALS_HOME/apps"; '
                  f'TEMPORARY_APP_PATH="{self.tmp_apps}"; '
                  f'{function} ' + ' '.join(f'"{a}"' for a in args))
        result = subprocess.run(['sh', '-c', script], capture_output=True, text=True, timeout=30)
        return result.stdout.strip()

    def assertSameAsShell(self, function, *args):
        with self.subTest(function=function, args=args):
            self.assertEqual(getattr(self.tools, function)(*args), self.shell(function, *args))

    def test_list_apps(self):
        self.assertSameAsShell('list_apps')
        self.assertEqual(self.tools.list_apps().split()[:2], ['9-early', '10-hostname-dns'])

    def test_get_app_root(self):
        for app in ('60-shared', '25-mainsail', 'octoeverywhere', 'missing'):
            self.assertSameAsShell('get_app_root', app)

    def test_is_app_enabled(self):
        for app in self.tools.list_apps().split() + ['missing']:
            self.assertSameAsShell('is_app_enabled', app)

    @unittest.skipUnless(shutil.which('jq'), 'jq is needed to compare with tools.sh')
    def test_get_app_property(self):
        cases = [
            ('10-hostname-dns', 'hostname'),   # temporary null -> user value, spaces collapsed
            ('10-hostname-dns', 'dhcp'),       # default boolean
            ('10-hostname-dns', 'empty'),      # empty user value -> no default -> empty
            ('25-mainsail', 'port'),           # temporary wins
            ('25-mainsail', 'ratio'),          # float: answered by the shell
            ('25-mainsail', 'list'),           # array: answered by the shell
            ('40-moonraker', 'mode'),          # null default
            ('60-shared', 'who'),              # user app shadows the built-in one
            ('octoeverywhere', 'token'),       # broken config: answered by the shell
            ('comments', 'anything'),          # app.json with comments: answered by the shell
            ('missing', 'anything'),
        ]
        for app, prop in cases:
            self.assertSameAsShell('get_app_property', app, prop)

    def test_property_names_that_are_not_plain_go_to_the_shell(self):
        calls = []
        tools = app_tools.AppTools(str(self.root), str(self.home),
                                   shell_fallback=lambda *a: calls.append(a) or 'x',
                                   temporary_app_path=str(self.tmp_apps))
        self.assertEqual(tools.get_app_property('25-mainsail', 'a.b'), 'x')
        self.assertEqual(calls, [('get_app_property', '25-mainsail', 'a.b')])

    def test_are_apps_enabled_matches_is_app_enabled(self):
        expected = {app: self.shell('is_app_enabled', app) for app in self.shell('list_apps').split()}
        self.assertEqual(self.tools.are_apps_enabled(), expected)


if __name__ == '__main__':
    unittest.main()
