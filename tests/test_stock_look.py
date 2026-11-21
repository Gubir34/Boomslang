"""The stock screen look library (build/stock-look): its colour swaps, and, where PyQt5
is installed, the real thing: Qt's setStyleSheet answered through LD_PRELOAD.

The printer's build (ARM) can't run here; this machine's build of the same source
is tested instead.
"""
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build/stock-look/build.sh'
LOOKS = ('liquid', 'liquid-light', 'aero', 'aero-light')
PRINTER_LIBS = [ROOT / f'files/3-rinkhals/opt/rinkhals/lib/libboomslang-stock-look-{look}.so' for look in LOOKS]

# Qt is loaded into the global scope, as it is for the stock screen (which links it
# directly); Python's own RTLD_LOCAL would hide it from dlsym(RTLD_NEXT)
PROBE = r'''
import os, sys
sys.setdlopenflags(os.RTLD_GLOBAL | os.RTLD_NOW)
from PyQt5.QtWidgets import QApplication, QWidget
app = QApplication([])
app.setStyleSheet("QWidget { background: #1C1C1C; }")
w = QWidget()
w.setStyleSheet(sys.argv[1])
print(app.styleSheet())
print(w.styleSheet())
'''


@unittest.skipUnless(shutil.which('gcc'), 'needs gcc')
class StockLookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.libs = {}
        for look in LOOKS:
            cls.libs[look] = os.path.join(cls.tmp.name, f'stock-look-{look}.so')
            subprocess.run(['sh', str(BUILD), 'host', look, cls.libs[look]], check=True)
        cls.lib = cls.libs['liquid']
        cls.swap_fns = {look: ctypes.CDLL(path).boomslang_stock_look_swap for look, path in cls.libs.items()}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def swap(self, text, look='liquid'):
        units = text.encode('utf-16-le')
        buf = (ctypes.c_ushort * (len(units) // 2)).from_buffer_copy(units)
        count = self.swap_fns[look](buf, len(buf))
        return bytes(buf).decode('utf-16-le'), count

    def test_stock_colours_become_liquid_plastic_whatever_the_case(self):
        out, count = self.swap('QPushButton { background-color: #3D3D3D; color:#999999; border-radius: 10px }')
        self.assertEqual(out, 'QPushButton { background-color: #1d4a2e; color:#a9c4ae; border-radius: 18px }')
        self.assertEqual(count, 3)
        self.assertEqual(self.swap('background: rgb(28, 28, 28); border: 1px solid #438dff')[0],
                         'background: rgb(11, 36, 20); border: 1px solid #4fb548')

    def test_other_colours_and_longer_hex_codes_are_left_alone(self):
        for text in ('color: #9999ff', 'color: #ff7538', 'background: #ffffff', 'no colours here', ''):
            self.assertEqual(self.swap(text), (text, 0), text)
        self.assertEqual(self.swap('color:#999;')[0], 'color:#ace;')

    def test_each_look_has_its_own_colours(self):
        sheet = 'QPushButton { background-color: #3D3D3D; color: #FFFFFF } QLabel { color: #999999 }'
        seen = {look: self.swap(sheet, look)[0] for look in LOOKS}
        self.assertEqual(len(set(seen.values())), 4)
        for look in LOOKS:
            self.assertEqual(len(seen[look]), len(sheet))
        # dark looks keep white text; light looks make it dark and the buttons light
        self.assertIn('#FFFFFF', seen['liquid'])
        self.assertIn('#FFFFFF', seen['aero'])
        self.assertIn('background-color: #ffffff; color: #18381e', seen['liquid-light'])
        self.assertIn('background-color: #f4faf0; color: #143a18', seen['aero-light'])
        self.assertIn('#7ec44e', self.swap('border: 1px solid #438dff', 'aero')[0])

    def test_the_printer_builds_are_arm_and_need_only_dlsym(self):
        for lib in PRINTER_LIBS:
            with self.subTest(lib.name):
                self.check_printer_lib(lib)

    def check_printer_lib(self, PRINTER_LIB):
        data = PRINTER_LIB.read_bytes()
        self.assertEqual(data[:4], b'\x7fELF')
        self.assertEqual(data[4], 1)                                  # 32 bit
        self.assertEqual(int.from_bytes(data[18:20], 'little'), 40)   # EM_ARM
        flags = int.from_bytes(data[36:40], 'little')
        self.assertTrue(flags & 0x400)                                # hard float
        nm = shutil.which('arm-linux-gnueabihf-nm')
        if nm:
            undefined = subprocess.run([nm, '-D', '--undefined-only', str(PRINTER_LIB)], capture_output=True,
                                       text=True, check=True).stdout.split()
            self.assertEqual([w for w in undefined if w != 'U'], ['dlsym'])

    def test_real_qt_through_ld_preload(self):
        try:
            import PyQt5  # noqa: F401
        except ImportError:
            self.skipTest('needs PyQt5')
        env = dict(os.environ, LD_PRELOAD=self.lib, QT_QPA_PLATFORM='offscreen')
        sheet = 'QPushButton { background-color: #3D3D3D; border-radius: 10px; color: #FFFFFF }'
        out = subprocess.run([sys.executable, '-c', PROBE, sheet], env=env, capture_output=True, text=True,
                             timeout=60, check=True).stdout.splitlines()
        self.assertEqual(out[0], 'QWidget { background: #0b2414; }')
        self.assertEqual(out[1], 'QPushButton { background-color: #1d4a2e; border-radius: 18px; color: #FFFFFF }')
        # and without the library, Qt keeps the stock colours (the probe itself is right)
        env.pop('LD_PRELOAD')
        plain = subprocess.run([sys.executable, '-c', PROBE, sheet], env=env, capture_output=True, text=True,
                               timeout=60, check=True).stdout.splitlines()
        self.assertEqual(plain[1], sheet)


SCRIPT = ROOT / 'files/3-rinkhals/opt/rinkhals/scripts/stock-look.sh'


class StartTests(unittest.TestCase):
    """start_stock_screen in a real shell, with a stand-in K3SysUi and start.sh."""

    def run_start(self, choice, screen_lives, library=True):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'K3SysUi').write_text('#!/bin/sh\necho "LD_PRELOAD=$LD_PRELOAD" > "$(dirname "$0")/started"\n'
                                         + ('sleep 30\n' if screen_lives else 'exit 1\n'))
            (tmp / 'K3SysUi').chmod(0o755)
            (tmp / 'start.sh').write_text('#!/bin/sh\ntouch "$(dirname "$0")/restarted"\n')
            (tmp / 'start.sh').chmod(0o755)
            if library:
                for look in LOOKS:
                    (tmp / f'libboomslang-stock-look-{look}.so').write_text('')
            if choice is not None:
                (tmp / 'choice').write_text(choice + '\n')
            script = SCRIPT.read_text().replace('/useremain/rinkhals/.stock-ui-look', str(tmp / 'choice')) \
                .replace('STOCK_LOOK_LIB_DIR=/opt/rinkhals/lib', f'STOCK_LOOK_LIB_DIR={tmp}') \
                .replace('STOCK_LOOK_TRIAL=60', 'STOCK_LOOK_TRIAL=6')
            (tmp / 'stock-look.sh').write_text(script)
            driver = (f'cd {tmp}; RINKHALS_LOGS={tmp}; RINKHALS_ROOT={tmp}; log() {{ echo "$@" >> {tmp}/log; }}\n'
                      f'. ./stock-look.sh\nstart_stock_screen\nsleep 8\n')
            subprocess.run(['sh', '-c', driver], timeout=60, check=True)
            subprocess.run(['pkill', '-f', str(tmp / 'K3SysUi')], check=False)
            read = lambda name: (tmp / name).read_text() if (tmp / name).exists() else None
            return read('started'), read('choice'), (tmp / 'restarted').exists(), read('log') or ''

    def test_off_by_default_and_for_anything_but_liquid(self):
        for choice in (None, 'off', 'neon'):
            started, _, restarted, _ = self.run_start(choice, screen_lives=True)
            self.assertEqual(started.strip(), 'LD_PRELOAD=', choice)
            self.assertFalse(restarted)

    def test_on_preloads_the_library(self):
        for look in ('liquid', 'aero-light'):
            started, choice, restarted, log = self.run_start(look, screen_lives=True)
            self.assertTrue(started.strip().endswith(f'libboomslang-stock-look-{look}.so'), started)
            self.assertEqual(choice.strip(), look)
            self.assertFalse(restarted)
            self.assertIn(look, log)

    def test_a_screen_that_does_not_stay_up_turns_the_look_off_and_restarts(self):
        started, choice, restarted, log = self.run_start('aero', screen_lives=False)
        self.assertTrue(started.strip().endswith('libboomslang-stock-look-aero.so'))
        self.assertEqual(choice.strip(), 'off')
        self.assertTrue(restarted)
        self.assertIn('look is off again', log)

    def test_a_missing_library_means_off(self):
        started, _, restarted, _ = self.run_start('liquid', screen_lives=True, library=False)
        self.assertEqual(started.strip(), 'LD_PRELOAD=')


if __name__ == '__main__':
    unittest.main()
