"""Slicing on the printer: the engine's settings, the start and end of a print, and the safety check.

The real engine is an ARM binary, so here a stand-in writes the G-code; the
real one was run under qemu-arm for all six printers when this was written.
"""
import os
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / 'files/3-rinkhals/opt/rinkhals/ui'
sys.path.insert(0, str(UI))
import slicer  # noqa: E402
import model_files  # noqa: E402

CUBE_V = [(0, 0, 0), (20, 0, 0), (20, 20, 0), (0, 20, 0), (0, 0, 20), (20, 0, 20), (20, 20, 20), (0, 20, 20)]
CUBE_F = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
          (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]


def cube_stl(path, scale=1.0):
    with open(path, 'wb') as f:
        f.write(b'cube'.ljust(80, b' '))
        f.write(struct.pack('<I', len(CUBE_F)))
        for a, b, c in CUBE_F:
            pts = [tuple(v * scale for v in CUBE_V[i]) for i in (a, b, c)]
            f.write(struct.pack('<12f2x', 0, 0, 0, *pts[0], *pts[1], *pts[2]))


def gcode(start, end, body):
    return start + ';LAYER:0\n' + body + ';LAYER:1\nG1 X101 Y101 E2\n' + end


GOOD_BODY = 'G0 F9000 X100 Y100 Z0.2\nG1 F1200 X120 Y100 E1.0\n'


class StartAndEndTests(unittest.TestCase):
    def test_every_printer_ends_its_start_in_absolute_extrusion(self):
        for code, profile in slicer.PROFILES.items():
            start = slicer.start_gcode(code, profile).strip().splitlines()
            self.assertTrue(start[-2].startswith('M82'), code)
            self.assertEqual(start[-1], 'G92 E0', code)

    def test_anycubic_start_macro_and_the_kobra_2_pro_purge(self):
        self.assertTrue(slicer.start_gcode('KS1', slicer.PROFILES['KS1']).startswith('G9111 bedTemp=55 extruderTemp=215'))
        k2p = slicer.start_gcode('K2P', slicer.PROFILES['K2P'])
        self.assertIn('M109 S220', k2p)
        self.assertIn('G28', k2p)
        self.assertIn('M900 K0.07', k2p)

    def test_the_end_turns_everything_off(self):
        for code in slicer.PROFILES:
            end = slicer.end_gcode(code)
            for word in ('M140 S0', 'M104 S0', 'M107', 'M84'):
                self.assertIn(word, end, code)
            self.assertTrue(end.startswith(slicer.END_MARK))

    def test_the_model_is_centred_on_the_bed(self):
        settings = slicer.engine_settings('K3M', slicer.PROFILES['K3M'])
        self.assertEqual((settings['posx'], settings['posy']), (213000, 210000))


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, 'out.gcode')
        self.start = slicer.start_gcode('KS1', slicer.PROFILES['KS1'])
        self.end = slicer.end_gcode('KS1')

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, text, code='KS1'):
        Path(self.path).write_text(text)
        return slicer.check_gcode(self.path, code)

    def test_a_good_file_passes_and_the_start_and_end_are_not_judged(self):
        self.assertIsNone(self.check(gcode(self.start, self.end, GOOD_BODY)))       # end parks at Y270
        k2p = gcode(slicer.start_gcode('K2P', slicer.PROFILES['K2P']), slicer.end_gcode('K2P'), GOOD_BODY)
        self.assertIsNone(self.check(k2p, 'K2P'))                                    # purge at Y226

    def test_moves_outside_the_printer_fail(self):
        for body in ('G1 X251 Y100 E1\n', 'G1 X100 Y-1 E1\n', 'G0 Z251\n', 'G0 X100 Y100 Z0\n'):
            self.assertIsNotNone(self.check(gcode(self.start, self.end, GOOD_BODY + body)), body)

    def test_the_wrong_extrusion_mode_fails(self):
        relative_after = gcode(self.start, self.end, GOOD_BODY + 'M83\n')
        self.assertIn('relative', self.check(relative_after))
        no_absolute = gcode('G9111 bedTemp=55 extruderTemp=215\n', self.end, GOOD_BODY)
        self.assertIn('absolute', self.check(no_absolute))

    def test_unsafe_temperatures_fail(self):
        self.assertIsNotNone(self.check(gcode(self.start, self.end, 'M104 S300\n' + GOOD_BODY)))
        self.assertIsNotNone(self.check(gcode(self.start, self.end, 'M140 S130\n' + GOOD_BODY)))

    def test_no_layers_fails(self):
        self.assertIsNotNone(self.check(self.start + self.end))


class ThreeMfTests(unittest.TestCase):
    def test_the_build_transform_is_applied(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, 'm.3mf')
            verts = ''.join(f'<vertex x="{x}" y="{y}" z="{z}"/>' for x, y, z in CUBE_V)
            tris = ''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in CUBE_F)
            with zipfile.ZipFile(source, 'w') as z:
                z.writestr('3D/3dmodel.model',
                           '<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources>'
                           f'<object id="1"><mesh><vertices>{verts}</vertices><triangles>{tris}</triangles></mesh></object>'
                           '<object id="2"><components><component objectid="1" transform="1 0 0 0 1 0 0 0 1 30 0 0"/>'
                           '</components></object></resources><build>'
                           '<item objectid="1" transform="1 0 0 0 1 0 0 0 2 100 80 5"/>'
                           '<item objectid="2"/></build></model>')
            target = os.path.join(tmp, 'm.stl')
            self.assertEqual(slicer.threemf_to_stl(source, target), 24)
            # the first cube spans x 100..120, y 80..100, z 5..45 (stretched twice in z); the second,
            # a component moved 30 mm, spans x 30..50, y 0..20, z 0..20: together 90 x 100 x 45 mm
            self.assertEqual(model_files.stl_info(target)['size'], (90.0, 100.0, 45.0))


class SliceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.folder = os.path.join(self.dir, 'gcodes')
        os.makedirs(self.folder)
        self.model = os.path.join(self.dir, 'Box.stl')
        cube_stl(self.model)
        self.engine = os.path.join(self.dir, 'CuraEngine')
        Path(self.engine).write_text('')
        self.body = GOOD_BODY

    def tearDown(self):
        self.tmp.cleanup()

    def run_engine(self, command, **kwargs):
        """Stand-in for the engine: writes G-code with the start and end it was given."""
        args = dict(zip(command[::1], command[1:]))
        settings = {}
        for i, word in enumerate(command):
            if word == '-s':
                key, _, value = command[i + 1].partition('=')
                settings[key] = value
        self.command = command
        self.kwargs = kwargs
        out = command[command.index('-o') + 1]
        Path(out).write_text(gcode(settings['startCode'], settings['endCode'], self.body))

        class Result:
            returncode = 0
            stdout = ''
            stderr = 'Print time: 900\n'
        return Result()

    def slice(self, model=None, code='KS1', **kwargs):
        kwargs.setdefault('free', lambda path: 10 * 1024 ** 3)
        kwargs.setdefault('available_kb', lambda: 150 * 1024)
        return slicer.slice_model(model or self.model, code, folder=self.folder, run=self.run_engine,
                                  engine=self.engine, **kwargs)

    def test_a_model_is_sliced_into_the_printers_files(self):
        path, seconds = self.slice()
        self.assertEqual(os.listdir(self.folder), ['Box-PLA.gcode'])        # no work folder left behind
        self.assertEqual(seconds, 900)
        text = Path(path).read_text()
        self.assertTrue(text.startswith('G9111'))
        self.assertIn('M104 S205 ; printing temperature', text)              # after the first layer
        self.assertIn('-v', self.command)
        # low CPU priority and first for the out of memory killer, never the printer's services
        self.assertIs(self.kwargs['preexec_fn'], slicer._engine_priority)

    def test_refused_while_printing_without_a_profile_or_when_too_big(self):
        big = os.path.join(self.dir, 'Big.stl')
        cube_stl(big, scale=12.2)                                           # 244 mm: no room for the skirt on an S1
        for kwargs in ({'printing': lambda: True}, {'code': 'XYZ'}, {'model': big}, {'available_kb': lambda: 20 * 1024}):
            with self.assertRaises(slicer.SliceError, msg=kwargs):
                self.slice(**kwargs)
        self.assertEqual(os.listdir(self.folder), [])

    def test_a_result_that_fails_the_check_is_not_kept(self):
        self.body = GOOD_BODY + 'G1 X400 Y100 E3\n'
        with self.assertRaises(slicer.SliceError) as error:
            self.slice()
        self.assertIn('safety check', str(error.exception))
        self.assertEqual(os.listdir(self.folder), [])

    def test_an_engine_that_fails_or_is_missing(self):
        def failing(command, **kwargs):
            class Result:
                returncode = 1
                stdout = stderr = ''
            return Result()
        with self.assertRaises(slicer.SliceError):
            slicer.slice_model(self.model, 'KS1', folder=self.folder, run=failing, engine=self.engine,
                               free=lambda path: 10 ** 10)
        with self.assertRaises(slicer.SliceError):
            slicer.slice_model(self.model, 'KS1', folder=self.folder, engine=os.path.join(self.dir, 'nope'))
        self.assertEqual(os.listdir(self.folder), [])

    def test_a_sliced_3mf_is_not_sliced_again(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_model_files import threemf
        sliced = os.path.join(self.dir, 'x.gcode.3mf')
        threemf(sliced, 'Anycubic Kobra S1', plates=((1, 60, 1),))
        with self.assertRaises(slicer.SliceError):
            self.slice(model=sliced)
