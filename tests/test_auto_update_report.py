"""The Updates page's automatic update rows: what Boomslang Web's updater left, in a few words."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / 'files/3-rinkhals/opt/rinkhals/ui'
sys.path.insert(0, str(UI))
import auto_update_report as report  # noqa: E402

NOW = datetime(2026, 11, 19, 15, 0, tzinfo=timezone.utc).astimezone()


def stamp(hours_ago):
    return (NOW - timedelta(hours=hours_ago)).isoformat()


class StatusTests(unittest.TestCase):
    def line(self, **status):
        return report.status_line(status or None, NOW)

    def test_each_state_in_a_few_words(self):
        clock = (NOW - timedelta(hours=1)).strftime('%H:%M')
        self.assertEqual(self.line(), 'Not checked yet')
        self.assertEqual(self.line(state='off'), 'Off')
        self.assertEqual(self.line(state='up-to-date', checked=stamp(1)), f'Up to date · {clock}')
        self.assertEqual(self.line(state='waiting-hours', available='2611-9-beta'), '2611 9 Beta waits for update hours')
        self.assertEqual(self.line(state='waiting-idle', available='2611-9-beta'), '2611 9 Beta waits for idle printer')
        self.assertTrue(self.line(state='error', checked=stamp(1)).startswith('Could not check'))

    def test_dates_further_back(self):
        self.assertTrue(report._when(stamp(30), NOW).startswith(('Yesterday', '17 Nov', '18 Nov')))
        self.assertIn('Nov', report._when(stamp(24 * 5), NOW))
        self.assertEqual(report._when('garbage', NOW), '?')


class HistoryTests(unittest.TestCase):
    def test_the_last_install_and_the_details(self):
        history = [{'time': stamp(48), 'from': '2611-7-alpha', 'to': '2611-8-alpha', 'result': 'installed'},
                   {'time': stamp(2), 'from': '2611-8-alpha', 'to': '2611-9-alpha', 'result': 'failed',
                    'message': 'The printer started on 2611 8 Alpha again'}]
        self.assertTrue(report.last_update_line(history, NOW).startswith('2611 9 Alpha failed · '))
        self.assertEqual(report.last_update_line([], NOW), 'None yet')
        text = report.details({'state': 'up-to-date', 'checked': stamp(1)}, history, NOW)
        self.assertLess(text.index('2611 9 Alpha FAILED'), text.index('2611 8 Alpha installed'))   # newest first

    def test_files_that_are_missing_or_broken_read_as_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            status, history = os.path.join(tmp, 's'), os.path.join(tmp, 'h')
            self.assertIsNone(report.read_status(status))
            self.assertEqual(report.read_history(history), [])
            Path(status).write_text('{broken')
            Path(history).write_text(json.dumps([{'to': '2611-9-beta'}, 'junk', {'from': 'x'}]))
            self.assertIsNone(report.read_status(status))
            self.assertEqual(report.read_history(history), [{'to': '2611-9-beta'}])
            self.assertIn('No automatic updates yet', report.details(None, [], NOW))


if __name__ == '__main__':
    unittest.main()
