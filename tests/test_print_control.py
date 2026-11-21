"""The print screen's requests: what is read, what is sent, and what is refused."""
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

UI = Path(__file__).resolve().parents[1] / 'files/3-rinkhals/opt/rinkhals/ui'
sys.path.insert(0, str(UI))
import print_control as pc  # noqa: E402


class FakeMoonraker:
    def __init__(self, answers=None, fail=False):
        self.answers, self.fail, self.sent = answers or {}, fail, []

    def __call__(self, method, path, timeout=4):
        self.sent.append((method, path))
        if self.fail:
            raise OSError('connection refused')
        for prefix, answer in self.answers.items():
            if path.startswith(prefix):
                return answer
        return {'result': 'ok'}


STATUS = {'result': {'status': {
    'print_stats': {'state': 'printing', 'filename': 'Benchy.gcode', 'print_duration': 600,
                    'info': {'current_layer': 12, 'total_layer': 120}},
    'display_status': {'progress': 0.25}, 'extruder': {'temperature': 209.6, 'target': 210},
    'heater_bed': {'temperature': 60.2, 'target': 60}}}}


class ReadTests(unittest.TestCase):
    def test_the_status_as_plain_values(self):
        s = pc.read_status(FakeMoonraker({'/printer/objects/query': STATUS}))
        self.assertEqual((s['state'], s['file'], s['progress'], s['layer'], s['layers']), ('printing', 'Benchy.gcode', 0.25, 12, 120))
        self.assertTrue(pc.busy(s))
        self.assertEqual(pc.remaining(s), 1800)
        self.assertEqual(pc.duration_text(pc.remaining(s)), '30 min')
        self.assertEqual(pc.duration_text(5400), '1 h 30 min')
        self.assertEqual(pc.temperature_text(s['nozzle'], s['nozzle_target']), '210/210°C')
        self.assertEqual(pc.temperature_text(25.0, 0), '25°C')

    def test_no_moonraker_is_none_not_a_crash(self):
        self.assertIsNone(pc.read_status(FakeMoonraker(fail=True)))
        self.assertIsNone(pc.remaining(None))

    def test_files_newest_first_without_hidden_ones(self):
        listing = {'result': [{'path': 'old.gcode', 'size': 10, 'modified': 1}, {'path': 'new.gcode', 'size': 20, 'modified': 5},
                              {'path': '.slice-x/out.gcode', 'modified': 9}, {'path': 'model.stl', 'modified': 9}]}
        self.assertEqual([f[0] for f in pc.list_files(FakeMoonraker({'/server/files/list': listing}))], ['new.gcode', 'old.gcode'])
        with self.assertRaises(pc.PrintError):
            pc.list_files(FakeMoonraker(fail=True))


class SendTests(unittest.TestCase):
    def test_a_print_starts_only_when_idle(self):
        fake = FakeMoonraker()
        pc.start('My part.gcode', printer_busy=lambda: False, http=fake)
        method, path = fake.sent[-1]
        self.assertEqual((method, urlparse(path).path), ('POST', '/printer/print/start'))
        self.assertEqual(parse_qs(urlparse(path).query)['filename'], ['My part.gcode'])
        for bad in ('../etc/passwd', '/abs.gcode', ''):
            with self.assertRaises(pc.PrintError):
                pc.start(bad, printer_busy=lambda: False, http=fake)
        with self.assertRaises(pc.PrintError):
            pc.start('x.gcode', printer_busy=lambda: True, http=fake)
        self.assertEqual(len(fake.sent), 1)

    def test_pause_resume_cancel(self):
        fake = FakeMoonraker()
        for action in ('pause', 'resume', 'cancel'):
            pc.command(action, http=fake)
        self.assertEqual([p for _, p in fake.sent], ['/printer/print/pause', '/printer/print/resume', '/printer/print/cancel'])
        with self.assertRaises(ValueError):
            pc.command('reboot', http=fake)

    def test_temperatures_are_capped(self):
        fake = FakeMoonraker()
        pc.set_temperatures(*pc.PRESETS['PLA'], http=fake)
        self.assertEqual(parse_qs(urlparse(fake.sent[-1][1]).query)['script'], ['M104 S210\nM140 S60'])
        pc.set_temperatures(0, 0, http=fake)
        for nozzle, bed in ((300, None), (None, 130), (-5, None)):
            with self.assertRaises(pc.PrintError):
                pc.set_temperatures(nozzle, bed, http=fake)
        self.assertEqual(len(fake.sent), 2)


if __name__ == '__main__':
    unittest.main()
