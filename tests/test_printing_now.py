"""Touch screen installs stop for a print or a heater, but not when Moonraker is away."""
import ast
import json
import logging
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / 'files/3-rinkhals/opt/rinkhals/ui'
SOURCE = (UI / 'common.py').read_text(encoding='utf-8')
NODE = next(n for n in ast.parse(SOURCE).body if isinstance(n, ast.FunctionDef) and n.name == 'printing_now')
NAMESPACE = {'json': json, 'logging': logging}
exec(compile(ast.Module([NODE], []), 'common-printing_now', 'exec'), NAMESPACE)
printing_now = NAMESPACE['printing_now']


def answer(state='standby', nozzle=0, bed=0, reading=False):
    return lambda: {'result': {'status': {'print_stats': {'state': state}, 'extruder': {'target': nozzle},
                                          'heater_bed': {'target': bed}, 'virtual_sdcard': {'is_active': reading}}}}


class PrintingNowTests(unittest.TestCase):
    def test_clear_signs_stop_the_install(self):
        for fetch in (answer('printing'), answer('paused'), answer('standby', nozzle=220), answer('', bed=60),
                      answer('complete', reading=True), answer('leveling')):
            self.assertTrue(printing_now(fetch))

    def test_idle_or_no_moonraker_lets_it_run(self):
        def down():
            raise OSError('connection refused')
        for fetch in (answer('standby'), answer('complete'), down, lambda: {'result': {}}):
            self.assertEqual(printing_now(fetch), '')


if __name__ == '__main__':
    unittest.main()
