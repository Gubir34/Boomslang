"""3D models on the printer: STL and 3MF sizes, sliced 3MF plates, and never G-code for another printer."""
import json
import os
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / 'files/3-rinkhals/opt/rinkhals/ui'
sys.path.insert(0, str(UI))
import model_files  # noqa: E402


def binary_stl(path, triangles, extra=b''):
    with open(path, 'wb') as f:
        f.write(b'solid but really binary'.ljust(80, b' '))     # binary files may start with "solid" too
        f.write(struct.pack('<I', len(triangles)))
        for tri in triangles:
            f.write(struct.pack('<12f2x', 0, 0, 0, *[c for v in tri for c in v]))
        f.write(extra)


CUBE = [((0, 0, 0), (20, 0, 0), (20, 10, 0)), ((0, 0, 0), (20, 10, 5), (0, 10, 5))]


def threemf(path, sliced_for=None, plates=(), vertices=((0, 0, 0), (30, 40, 10))):
    with zipfile.ZipFile(path, 'w') as z:
        verts = ''.join(f'<vertex x="{x}" y="{y}" z="{zz}"/>' for x, y, zz in vertices)
        z.writestr('3D/3dmodel.model',
                   '<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources>'
                   f'<object id="1"><mesh><vertices>{verts}</vertices><triangles><triangle v1="0" v2="1" v3="0"/>'
                   '</triangles></mesh></object></resources></model>')
        if sliced_for is not None:
            z.writestr('Metadata/project_settings.config', json.dumps({'printer_model': sliced_for}))
        info = ''.join(f'<plate><metadata key="index" value="{i}"/><metadata key="prediction" value="{t}"/>'
                       f'<metadata key="weight" value="{w}"/><filament id="1" type="PLA"/></plate>'
                       for i, t, w in plates)
        if plates:
            z.writestr('Metadata/slice_info.config', f'<config>{info}</config>')
        for i, _, _ in plates:
            z.writestr(f'Metadata/plate_{i}.gcode', f'; plate {i}\nG28\n' * 10)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, name):
        return os.path.join(self.dir, name)


class StlTests(Base):
    def test_binary_stl_size_and_triangles(self):
        binary_stl(self.path('a.stl'), CUBE)
        self.assertEqual(model_files.stl_info(self.path('a.stl')), {'kind': 'stl', 'triangles': 2, 'size': (20, 10, 5)})

    def test_binary_stl_with_bytes_at_the_end(self):
        binary_stl(self.path('a.stl'), CUBE, extra=b'\0' * 7)
        self.assertEqual(model_files.stl_info(self.path('a.stl'))['size'], (20, 10, 5))

    def test_ascii_stl(self):
        Path(self.path('a.stl')).write_text('solid x\n facet normal 0 0 1\n outer loop\n'
                                            '  vertex 0 0 0\n  vertex 1.5e1 0 0\n  vertex 0 8 3\n endloop\n endfacet\nendsolid\n')
        self.assertEqual(model_files.stl_info(self.path('a.stl')), {'kind': 'stl', 'triangles': 1, 'size': (15, 8, 3)})

    def test_not_an_stl(self):
        Path(self.path('a.stl')).write_text('hello')
        with self.assertRaises(model_files.ModelError):
            model_files.stl_info(self.path('a.stl'))


class ThreeMfTests(Base):
    def test_an_unsliced_3mf_gives_its_size(self):
        threemf(self.path('m.3mf'))
        info = model_files.threemf_info(self.path('m.3mf'))
        self.assertFalse(info['sliced'])
        self.assertEqual((info['size'], info['objects']), ((30, 40, 10), 1))

    def test_a_sliced_3mf_lists_its_plates(self):
        threemf(self.path('m.gcode.3mf'), 'Anycubic Kobra S1', plates=((1, 3720, 12.5), (2, 600, 3)))
        info = model_files.threemf_info(self.path('m.gcode.3mf'))
        self.assertTrue(info['sliced'])
        self.assertEqual(info['printer_model'], 'Anycubic Kobra S1')
        self.assertEqual([(p['index'], p['time'], p['weight'], p['filament']) for p in info['plates']],
                         [(1, 3720, 12.5, 'PLA'), (2, 600, 3, 'PLA')])
        lines = model_files.describe(info, 'KS1')
        self.assertIn('Plate 1 · 1 h 2 min · 12.5 g · PLA', lines)

    def test_not_a_3mf(self):
        Path(self.path('m.3mf')).write_text('nope')
        with self.assertRaises(model_files.ModelError):
            model_files.threemf_info(self.path('m.3mf'))


class PrinterTests(unittest.TestCase):
    def test_fits_and_turning_by_90_degrees(self):
        self.assertEqual(model_files.fits((200, 200, 100), 'KS1'), (True, ''))
        self.assertEqual(model_files.fits((240, 100, 10), 'K2P')[0], False)          # 220 x 220 bed
        self.assertTrue(model_files.fits((100, 400, 10), 'K3M')[0])                  # 426 x 420: fits turned
        self.assertFalse(model_files.fits((10, 10, 300), 'KS1')[0])                 # too tall
        self.assertFalse(model_files.fits((10, 10, 10), 'NOPE')[0])

    def test_only_g_code_sliced_for_this_printer_is_accepted(self):
        self.assertIsNone(model_files.sliced_for_problem({'printer_model': 'Anycubic Kobra S1'}, 'KS1'))
        self.assertIsNone(model_files.sliced_for_problem({'printer_model': 'anycubic kobra s1'}, 'KS1'))
        for other in ('Anycubic Kobra S1 Max', 'Bambu Lab X1 Carbon', 'Anycubic Kobra 3', ''):
            self.assertIsNotNone(model_files.sliced_for_problem({'printer_model': other}, 'KS1'), other)
        self.assertIsNotNone(model_files.sliced_for_problem({'printer_model': 'Anycubic Kobra S1'}, 'NOPE'))

    def test_kinds_and_safe_names(self):
        self.assertEqual(model_files.model_kind('https://x/Benchy.STL?dl=1'), 'stl')
        self.assertEqual(model_files.model_kind('https://x/a.gcode.3mf'), 'gcode.3mf')
        self.assertEqual(model_files.model_kind('https://x/a.3mf'), '3mf')
        self.assertIsNone(model_files.model_kind('https://x/a.obj'))
        self.assertEqual(model_files.model_file_name('https://x/..%2Fevil.gcode.3mf'), 'evil.gcode.3mf')
        self.assertEqual(model_files.model_file_name('https://x/Benchy.stl', ['Benchy.stl']), 'Benchy (2).stl')


class ExtractTests(Base):
    def setUp(self):
        super().setUp()
        self.gcodes = os.path.join(self.dir, 'gcodes')
        os.makedirs(self.gcodes)
        threemf(self.path('Benchy.gcode.3mf'), 'Anycubic Kobra S1', plates=((1, 60, 1), (2, 60, 1)))

    def extract(self, plate=2, model='KS1', **kwargs):
        kwargs.setdefault('free', lambda path: 10 * 1024 ** 3)
        return model_files.extract_plate(self.path('Benchy.gcode.3mf'), plate, model, self.gcodes, **kwargs)

    def test_a_plate_is_copied_whole_into_the_printers_files(self):
        path = self.extract()
        self.assertEqual(os.path.basename(path), 'Benchy-plate2.gcode')
        self.assertTrue(Path(path).read_text().startswith('; plate 2'))
        self.assertEqual(os.listdir(self.gcodes), ['Benchy-plate2.gcode'])

    def test_refused_for_another_printer_while_printing_or_without_room(self):
        for kwargs in ({'model': 'KS1M'}, {'printing': lambda: True}, {'free': lambda path: 0}, {'plate': 9}):
            with self.assertRaises(model_files.ModelError, msg=kwargs):
                self.extract(**kwargs)
        self.assertEqual(os.listdir(self.gcodes), [])

    def test_a_print_that_starts_while_copying_drops_the_file(self):
        calls = iter([False, True])
        with self.assertRaises(model_files.ModelError):
            self.extract(printing=lambda: next(calls))
        self.assertEqual(os.listdir(self.gcodes), [])
