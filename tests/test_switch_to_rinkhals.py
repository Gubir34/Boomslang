"""Settings > Switch to Rinkhals: every step must be confirmed before anything changes.

As in test_browser_screen.py, the methods are cut out of rinkhals-ui.py with
ast and run against stand-in widgets.
"""
import ast
import importlib.util
import unittest
from pathlib import Path
from unittest import mock

UI = Path(__file__).resolve().parents[1] / 'files/3-rinkhals/opt/rinkhals/ui'
spec = importlib.util.spec_from_file_location('testsupport.release_assets', UI / 'release_assets.py')
release_assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_assets)


def load_switch_class(namespace):
    source = (UI / 'rinkhals-ui.py').read_text(encoding='utf-8')
    app = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == 'RinkhalsUiApp')
    wanted = [ast.get_source_segment(source, node) for node in app.body
              if (isinstance(node, ast.FunctionDef) and node.name.startswith('switch_to_rinkhals')) or
              (isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') in ('SWITCH_CONFIRM_WORD', 'switch_search'))]
    code = 'class SwitchApp:\n' + '\n'.join('    ' + line for chunk in wanted for line in chunk.split('\n')) + '\n'
    exec(compile(code, 'rinkhals-ui-switch', 'exec'), namespace)
    return namespace['SwitchApp']


class Version:
    version = '20261101_01'
    changes = '| Kobra S1 | `2.7.0.9` `2.7.2.7` |'


class SwitchToRinkhalsTests(unittest.TestCase):
    def setUp(self):
        self.lookups = []
        self.versions = [Version()]

        self.on_lookup = None

        def get_available_versions(**kwargs):
            self.lookups.append(kwargs)
            if self.on_lookup:
                self.on_lookup()
            return self.versions

        lvr = mock.MagicMock(name='lvr')
        self.lv = mock.MagicMock(name='lv')
        namespace = {
            'lv': self.lv, 'lvr': lvr, 'run_async': lambda fn: fn(), 'KOBRA_VERSION': '2.7.3.7',
            'RINKHALS_REPO': 'rinkhals-community/Rinkhals',
            'Rinkhals': mock.MagicMock(get_available_versions=get_available_versions),
            'switch_warning_text': release_assets.switch_warning_text,
        }
        self.app = load_switch_class(namespace)()
        self.app.show_text_dialog = mock.MagicMock()
        self.app.show_input_text_dialog = mock.MagicMock()
        self.app.show_ota_rinkhals_modal = mock.MagicMock()
        self.app.root_modal = mock.MagicMock()
        self.app.root_modal.has_flag.return_value = False   # the "looking" dialog is still open

    def tap_action(self):
        """Tap the button of the dialog on screen."""
        callback = self.app.show_text_dialog.call_args.kwargs['callback']
        callback()

    def type_word(self, text):
        title, initial, is_number, callback = self.app.show_input_text_dialog.call_args.args
        callback(text)

    def test_the_whole_path_ends_in_the_install_dialog_with_a_warning(self):
        self.app.switch_to_rinkhals_start()
        self.assertIn('WARNING', self.app.show_text_dialog.call_args.args[0])
        self.tap_action()
        second = self.app.show_text_dialog.call_args.args[0]
        self.assertIn('ARE YOU SURE', second)
        self.assertIn('2.7.3.7', second)           # names the printer's firmware
        self.assertIn('USB', second)               # says how to come back
        self.tap_action()
        self.assertIn('RINKHALS', self.app.show_input_text_dialog.call_args.args[0])
        self.assertEqual(self.lookups, [])         # nothing fetched before the word is typed
        self.type_word(' rinkhals ')
        self.assertEqual(self.lookups, [{'include_test': False, 'limit': 1,
                                         'repo': 'rinkhals-community/Rinkhals', 'compressed': False}])
        version = self.app.show_ota_rinkhals_modal.call_args.args[0]
        self.assertIn('NOT listed', version.switch_warning)   # 2.7.3.7 is not in the notes

    def test_a_wrong_word_changes_nothing(self):
        self.app.switch_to_rinkhals_typed('rinkhal')
        self.assertIn('not changed', self.app.show_text_dialog.call_args.args[0])
        self.assertEqual(self.lookups, [])
        self.app.show_ota_rinkhals_modal.assert_not_called()

    def test_cancelling_the_search_shows_nothing_later(self):
        self.on_lookup = self.tap_action          # Cancel while GitHub answers
        self.app.switch_to_rinkhals_typed('RINKHALS')
        self.app.show_ota_rinkhals_modal.assert_not_called()

    def test_tapping_the_search_dialog_away_also_cancels(self):
        self.app.root_modal.has_flag.return_value = True
        self.app.switch_to_rinkhals_typed('RINKHALS')
        self.app.show_ota_rinkhals_modal.assert_not_called()

    def test_no_release_found(self):
        self.versions = []
        self.app.switch_to_rinkhals_typed('RINKHALS')
        self.assertIn('not changed', self.app.show_text_dialog.call_args.args[0])
        self.app.show_ota_rinkhals_modal.assert_not_called()


if __name__ == '__main__':
    unittest.main()
