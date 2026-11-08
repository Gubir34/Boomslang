"""Crash-safety of the stock binary patch/restore sequence (issue #198).

Runs files/3-rinkhals/opt/rinkhals/scripts/native-binaries.sh with /bin/sh in a
temporary directory, using small fake binaries and a fake patch script with
the same MD5 header format create-patch.py writes.
"""
import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'files/3-rinkhals/opt/rinkhals/scripts/native-binaries.sh'

STOCK = b'\x7fELF stock gkapi ' * 64
PATCHED = STOCK + b'PATCHED'
OTHER_STOCK = b'\x7fELF stock gkapi from another firmware ' * 64


def md5(data):
    return hashlib.md5(data).hexdigest()


class NativeBinariesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.patch = self.dir / 'gkapi.KS1_test.sh'
        self.write_patch_script(PATCHED)

    def tearDown(self):
        self._tmp.cleanup()

    def write_patch_script(self, result):
        # Mimics the generated scripts: skip when already patched, refuse an
        # unknown input, otherwise produce the patched bytes.
        (self.dir / 'patched.bin').write_bytes(result)
        self.patch.write_text(
            '#!/bin/sh\n'
            f'# Before MD5: {md5(STOCK)}\n'
            f'# After MD5: {md5(PATCHED)}\n'
            'TARGET=$1\n'
            'MD5=$(md5sum $TARGET | awk \'{print $1}\')\n'
            f'[ "$MD5" = "{md5(PATCHED)}" ] && exit 0\n'
            f'[ "$MD5" != "{md5(STOCK)}" ] && exit 1\n'
            f'cat {self.dir}/patched.bin > $TARGET\n'
        )
        self.patch.chmod(0o755)

    def run_sh(self, command):
        return subprocess.run(
            ['sh', '-c', f'. "{SCRIPT}"; {command}'],
            cwd=self.dir, capture_output=True, text=True, timeout=30,
        )

    def files(self):
        return {
            p.name: p.read_bytes()
            for p in self.dir.iterdir()
            if p.name.startswith('gkapi') and p != self.patch
        }

    def write(self, name, data):
        (self.dir / name).write_bytes(data)

    def boot(self):
        """A full startup: patch, then restore once the binary is running."""
        patched = self.run_sh(f'native_patch gkapi {self.patch}')
        self.assertEqual(patched.returncode, 0, patched.stdout + patched.stderr)
        self.assertEqual(self.files()['gkapi'], PATCHED)
        self.assertTrue(os.access(self.dir / 'gkapi', os.X_OK))
        self.assertEqual(self.files()['gkapi.original'], STOCK)
        self.run_sh('native_restore gkapi')
        self.assertEqual(self.files()['gkapi'], STOCK)
        self.assertNotIn('gkapi.original', self.files())

    def test_normal_boot_patches_then_restores_stock(self):
        self.write('gkapi', STOCK)
        self.boot()
        self.assertEqual(self.files()['gkapi.patch'], PATCHED)
        self.boot()  # and again on the next boot

    def test_power_loss_after_patching_keeps_stock(self):
        # Previous boot lost power while the patched binary was in place.
        self.write('gkapi', PATCHED)
        self.write('gkapi.original', STOCK)
        self.boot()

    def test_truncated_patched_binary_is_replaced_by_stock(self):
        # The #198 state: a partial patched file and the stock .original.
        self.write('gkapi', PATCHED[:100])
        self.write('gkapi.original', STOCK)
        self.boot()

    def test_power_loss_during_restore_keeps_stock(self):
        # Lost power between moving the patched binary away and restoring stock.
        self.write('gkapi.patch', PATCHED)
        self.write('gkapi.original', STOCK)
        self.boot()

    def test_leftover_new_file_is_discarded(self):
        self.write('gkapi', STOCK)
        self.write('gkapi.new', PATCHED[:10])
        self.boot()
        self.assertNotIn('gkapi.new', self.files())

    def test_unknown_binary_without_stock_copy_is_left_alone(self):
        self.write('gkapi', b'something else')
        self.write('gkapi.original', b'not stock either')
        before = self.files()
        result = self.run_sh(f'native_patch gkapi {self.patch}')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.files(), before)
        self.run_sh('native_restore gkapi')  # must not make things worse
        self.assertEqual(self.files()['gkapi'], b'not stock either')

    def test_failed_patch_leaves_stock_in_place(self):
        self.write('gkapi', STOCK)
        self.write_patch_script(STOCK + b'wrong')
        result = self.run_sh(f'native_patch gkapi {self.patch}')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.files(), {'gkapi': STOCK})

    def test_stale_original_from_other_firmware_is_not_restored(self):
        # After an Anycubic update the current binary is the new stock one;
        # an old .original must not replace it.
        self.write('gkapi', STOCK)
        self.write('gkapi.original', OTHER_STOCK)
        self.boot()

    def test_patch_script_without_md5_header_is_refused(self):
        self.write('gkapi', STOCK)
        self.patch.write_text('#!/bin/sh\nexit 0\n')
        result = self.run_sh(f'native_patch gkapi {self.patch}')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.files(), {'gkapi': STOCK})

    def test_restore_without_original_does_nothing(self):
        self.write('gkapi', STOCK)
        self.run_sh('native_restore gkapi')
        self.assertEqual(self.files(), {'gkapi': STOCK})


if __name__ == '__main__':
    unittest.main()
