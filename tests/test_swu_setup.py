"""Unpacking update packages: standard (setup.tar.gz) and compressed (setup.tar.xz)."""
import hashlib
import importlib.util
import io
import lzma
import os
import tarfile
import tempfile
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / 'files/3-rinkhals/opt/rinkhals/ui'
spec = importlib.util.spec_from_file_location('testsupport.swu_setup', UI / 'swu_setup.py')
swu_setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(swu_setup)

FILES = {
    'update.sh': b'#!/bin/sh\necho installing\n',
    'rinkhals/.version': b'2611-3-alpha\n',
    # Compressible and larger than one output step, to exercise the bounded loop
    'rinkhals/usr/lib/big.bin': b'boomslang ' * 400_000,
}


def tar_bytes():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as tar:
        for name, data in FILES.items():
            info = tarfile.TarInfo('./' + name)
            info.size = len(data)
            info.mode = 0o755 if name.endswith('.sh') else 0o644
            tar.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo('./rinkhals/usr/lib/link.bin')
        link.type = tarfile.SYMTYPE
        link.linkname = 'big.bin'
        tar.addfile(link)
    return buffer.getvalue()


class UnpackSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data, md5=True):
        path = os.path.join(self.dir, name)
        with open(path, 'wb') as f:
            f.write(data)
        if md5:
            with open(path + '.md5', 'w') as f:
                f.write(hashlib.md5(data).hexdigest() + '\n')
        return path

    def assert_unpacked(self):
        for name, data in FILES.items():
            with open(os.path.join(self.dir, name), 'rb') as f:
                self.assertEqual(f.read(), data, name)
        self.assertTrue(os.access(os.path.join(self.dir, 'update.sh'), os.X_OK))
        self.assertEqual(os.readlink(os.path.join(self.dir, 'rinkhals/usr/lib/link.bin')), 'big.bin')

    def test_compressed_package(self):
        # The same settings as build/tools.sh prepare_txz
        data = lzma.compress(tar_bytes(),
                             filters=[{'id': lzma.FILTER_LZMA2, 'preset': 9 | lzma.PRESET_EXTREME,
                                       'dict_size': 16 * 1024 * 1024}])
        archive = self.write('setup.tar.xz', data)
        self.assertEqual(swu_setup.unpack_setup(self.dir), 'setup.tar.xz')
        self.assert_unpacked()
        self.assertFalse(os.path.exists(archive), 'the archive is removed to free space')

    def test_standard_package_is_unpacked_as_before(self):
        import gzip
        archive = self.write('setup.tar.gz', gzip.compress(tar_bytes()))
        self.assertEqual(swu_setup.unpack_setup(self.dir), 'setup.tar.gz')
        self.assert_unpacked()
        self.assertTrue(os.path.exists(archive))

    def test_compressed_is_preferred_when_both_are_present(self):
        import gzip
        self.write('setup.tar.gz', gzip.compress(b'not a tar'))
        self.write('setup.tar.xz', lzma.compress(tar_bytes()))
        self.assertEqual(swu_setup.unpack_setup(self.dir), 'setup.tar.xz')

    def test_wrong_md5_stops_before_unpacking(self):
        self.write('setup.tar.xz', lzma.compress(tar_bytes()), md5=False)
        with open(os.path.join(self.dir, 'setup.tar.xz.md5'), 'w') as f:
            f.write('0' * 32)
        with self.assertRaisesRegex(swu_setup.SetupError, 'md5'):
            swu_setup.unpack_setup(self.dir)
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'update.sh')))

    def test_truncated_download_is_an_error(self):
        data = lzma.compress(tar_bytes())
        self.write('setup.tar.xz', data[:len(data) // 2])
        with self.assertRaises(swu_setup.SetupError):
            swu_setup.unpack_setup(self.dir)

    def test_corrupt_data_is_an_error(self):
        data = bytearray(lzma.compress(tar_bytes()))
        data[200:260] = b'\xff' * 60
        self.write('setup.tar.xz', bytes(data))
        with self.assertRaises(swu_setup.SetupError):
            swu_setup.unpack_setup(self.dir)

    def test_huge_dictionary_is_refused(self):
        # A file asking for more memory than the build ever uses is not ours
        # (shown with a lowered limit: the default preset's 8 MiB dictionary
        # against 1 MiB, instead of building a gigantic test file)
        self.write('setup.tar.xz', lzma.compress(tar_bytes()))
        saved = swu_setup.XZ_MEMLIMIT
        swu_setup.XZ_MEMLIMIT = 1024 * 1024
        try:
            with self.assertRaisesRegex(swu_setup.SetupError, 'decompressed'):
                swu_setup.unpack_setup(self.dir)
        finally:
            swu_setup.XZ_MEMLIMIT = saved

    def test_no_archive(self):
        with self.assertRaisesRegex(swu_setup.SetupError, 'no setup archive'):
            swu_setup.unpack_setup(self.dir)

    def test_command_line(self):
        self.write('setup.tar.xz', lzma.compress(tar_bytes()))
        self.assertEqual(swu_setup.main(['swu_setup.py', self.dir]), 0)
        self.assert_unpacked()
        self.assertEqual(swu_setup.main(['swu_setup.py', self.dir]), 1)   # nothing left to unpack
        self.assertEqual(swu_setup.main(['swu_setup.py']), 2)


if __name__ == '__main__':
    unittest.main()
