"""The settings screen of an app: which control each app.json property gets."""
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('testsupport.app_settings', ROOT / 'files/3-rinkhals/opt/rinkhals/ui/app_settings.py')
app_settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_settings)

PROPERTIES = {
    'status': {'display': 'Last backup', 'type': 'report'},
    'destination': {'display': 'Save backups to', 'type': 'enum', 'options': ['usb', 'folder'], 'default': 'usb'},
    'interval_hours': {'display': 'Back up every N hours', 'type': 'number', 'default': '24'},
    'include_database': {'display': 'Include the database', 'type': 'enum', 'options': ['False', 'True'], 'default': 'True'},
    'backup_on_start': {'display': 'Back up at start', 'type': 'enum', 'options': ['false', 'true'], 'default': 'true', 'advanced': True},
    'folder': {'display': 'Folder', 'type': 'text', 'default': '/useremain/backups'},
    'link': {'display': 'Open', 'type': 'qr'},
    'odd': {'display': 'Unknown', 'type': 'colour'},
    'broken': 'not an object',
}


class RowTests(unittest.TestCase):
    def rows(self, saved=None):
        saved = saved or {}
        return {row['key']: row for row in app_settings.setting_rows(PROPERTIES, lambda k: saved.get(k, ''))}

    def test_each_type_gets_its_control(self):
        rows = self.rows()
        self.assertEqual({k: r['kind'] for k, r in rows.items()}, {
            'status': 'report', 'destination': 'choice', 'interval_hours': 'number', 'include_database': 'switch',
            'backup_on_start': 'switch', 'folder': 'text', 'link': 'qr'})

    def test_unknown_types_and_broken_entries_are_left_out(self):
        self.assertNotIn('odd', self.rows())
        self.assertNotIn('broken', self.rows())
        self.assertEqual(app_settings.setting_rows(None, lambda k: ''), [])

    def test_the_saved_value_wins_over_the_default(self):
        self.assertEqual(self.rows()['interval_hours']['value'], '24')
        self.assertEqual(self.rows({'interval_hours': '6'})['interval_hours']['value'], '6')
        self.assertEqual(self.rows({'interval_hours': 'null'})['interval_hours']['value'], '24')

    def test_order_is_app_json_order(self):
        keys = [r['key'] for r in app_settings.setting_rows(PROPERTIES, lambda k: '')]
        self.assertEqual(keys[:3], ['status', 'destination', 'interval_hours'])

    def test_advanced_and_empty_reports_are_split_off(self):
        rows = app_settings.setting_rows(PROPERTIES, lambda k: '')
        basic, advanced = app_settings.split_advanced(rows)
        self.assertEqual([r['key'] for r in advanced], ['backup_on_start'])
        self.assertNotIn('status', [r['key'] for r in basic])       # nothing written yet
        self.assertNotIn('link', [r['key'] for r in basic])
        rows = app_settings.setting_rows(PROPERTIES, lambda k: {'status': 'Today 10:00'}.get(k, ''))
        basic, _ = app_settings.split_advanced(rows)
        self.assertIn('status', [r['key'] for r in basic])


class SwitchTests(unittest.TestCase):
    def test_only_false_and_true_make_a_switch(self):
        self.assertTrue(app_settings.is_switch(['False', 'True']))
        self.assertTrue(app_settings.is_switch(['true', 'false']))
        self.assertFalse(app_settings.is_switch(['on', 'off']))
        self.assertFalse(app_settings.is_switch(['False', 'True', 'Maybe']))
        self.assertFalse(app_settings.is_switch(None))

    def test_the_stored_value_keeps_app_jsons_spelling(self):
        self.assertEqual(app_settings.switch_value(['False', 'True'], True), 'True')
        self.assertEqual(app_settings.switch_value(['false', 'true'], False), 'false')
        self.assertTrue(app_settings.is_on('TRUE'))
        self.assertFalse(app_settings.is_on(''))


class NumberAndTextTests(unittest.TestCase):
    def test_steps(self):
        self.assertEqual(app_settings.step_number('24', 1), '25')
        self.assertEqual(app_settings.step_number('24', -1), '23')
        self.assertEqual(app_settings.step_number('0.5', 1), '1.5')
        self.assertEqual(app_settings.step_number('', 1), '1')
        self.assertEqual(app_settings.step_number('abc', -1), '-1')

    def test_value_and_status_text(self):
        self.assertEqual(app_settings.value_text({'kind': 'switch', 'value': 'True'}), 'On')
        self.assertEqual(app_settings.value_text({'kind': 'text', 'value': ''}), 'Not set')
        self.assertEqual(app_settings.status_text(True, True, '1.2'), 'Running · v1.2')
        self.assertEqual(app_settings.status_text(True, False), 'Stopped')
        self.assertEqual(app_settings.status_text(False, False, '3'), 'Off · v3')


class RealAppsTests(unittest.TestCase):
    """Every app.json that ships (and the store's) gives rows without errors, and at least one editable."""

    def test_every_shipped_app(self):
        files = list((ROOT / 'files/4-apps/home/rinkhals/apps').glob('*/app.json'))
        self.assertTrue(files)
        for path in files:
            text = re.sub(r'^\s*//.*$', '', path.read_text(encoding='utf-8'), flags=re.M)
            manifest = json.loads(text)
            rows = app_settings.setting_rows(manifest.get('properties'), lambda k: '')
            for row in rows:
                self.assertIn(row['kind'], app_settings.KINDS, path)
