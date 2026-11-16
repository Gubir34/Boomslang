"""The printer configuration Boomslang ships must not use regular Klipper's macro syntax.

Anycubic's GoKlipper renders macros with pongo2, not Jinja2 as Klipper does.
A macro it can't compile stops GoKlipper at boot: the printer shows error
11407 and Boomslang turns itself off. That happened with Moonraker's Spoolman
macros (#221) and again with release 2611 2 Alpha, which shipped untested fan
and M600 macros. Nothing here can prove a macro works on the printer; it only
refuses the forms known not to.
"""
import re
import unittest
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / 'files/3-rinkhals/home/rinkhals/printer_data/config'

KLIPPER_ONLY = {
    r'\|\s*\w+\s*\(': 'a filter called with brackets, e.g. |default(1.0); pongo2 writes |default:1.0',
    r'\|\s*int\b': 'the |int filter; pongo2 calls it |integer',
    r'action_\w+': 'Klipper action_* helpers, which pongo2 does not have',
    r'(?<![{%])\{\s*[A-Za-z_][\w.]*\s*\}(?!\})': 'a {name} substitution; pongo2 writes {{ name }}',
    r'\bprinter\[': "printer['object'] lookups in Klipper's style",
}


def macros(text):
    """{name: body} for every gcode_macro section."""
    return {m.group(1): m.group(2)
            for m in re.finditer(r'^\[gcode_macro ([^\]]+)\]\n(.*?)(?=^\[|\Z)', text, re.M | re.S)}


class PrinterConfigTests(unittest.TestCase):
    def test_shipped_macros_avoid_klipper_only_syntax(self):
        files = sorted(CONFIG.glob('*.cfg'))
        self.assertTrue(files)
        for path in files:
            for name, body in macros(path.read_text()).items():
                code = '\n'.join(line for line in body.split('\n') if not line.lstrip().startswith('#'))
                for pattern, why in KLIPPER_ONLY.items():
                    found = re.search(pattern, code)
                    self.assertIsNone(found, f'{path.name} [{name}] uses {why}: {found.group(0) if found else ""}')

    def test_the_check_recognises_the_macros_that_broke_the_boot(self):
        broken = ('[gcode_macro SET_AIR_FILTER]\ngcode:\n'
                  '    {% set speed = params.SPEED|default(1.0)|float %}\n'
                  '    SET_FAN_SPEED FAN=air_filter_fan SPEED={speed}\n')
        body = macros(broken)['SET_AIR_FILTER']
        hits = [why for pattern, why in KLIPPER_ONLY.items() if re.search(pattern, body)]
        self.assertEqual(len(hits), 2, hits)

    def test_the_known_good_form_passes(self):
        good = '[gcode_macro SET_PRESSURE_ADVANCE]\ngcode:\n    M900 K{{ params.ADVANCE }}\n'
        body = macros(good)['SET_PRESSURE_ADVANCE']
        self.assertFalse([p for p in KLIPPER_ONLY if re.search(p, body)])


if __name__ == '__main__':
    unittest.main()
