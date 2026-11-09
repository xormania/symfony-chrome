"""Outcome-aware measurements must retain failures and incompatible identities."""
import importlib.util
import os
from pathlib import Path
import tempfile
import sys
import unittest

ROOT = Path(os.environ.get('CONSUMER_TEST_ROOT', Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(ROOT / 'tools/testing'))
spec = importlib.util.spec_from_file_location('performance', ROOT / 'tools/testing/performance.py')
performance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(performance)


class PerformanceContracts(unittest.TestCase):
    def test_failed_attempt_is_counted_alongside_successes(self):
        rows = [{'attempt': 1, 'outcome': 'passed', 'native_exit': 0, 'seconds': 1},
                {'attempt': 2, 'outcome': 'failed', 'native_exit': 9, 'seconds': 10},
                {'attempt': 3, 'outcome': 'timed_out', 'native_exit': -15, 'seconds': 30}]
        summary = performance.summarize(rows)
        self.assertEqual((3, 1, 1, 1), tuple(summary[k] for k in ('attempts', 'passed', 'failed', 'timed_out')))
        self.assertFalse(summary['native_success'])
        self.assertEqual(10, summary['all_attempts_median_seconds'])
        self.assertEqual(1, summary['successful_median_seconds'])

    def test_missing_and_duplicate_attempts_and_invalid_measurements_fail(self):
        for row in [{'attempt': 2, 'outcome': 'passed', 'native_exit': 0, 'seconds': 1},
                    {'attempt': 1, 'outcome': 'passed', 'native_exit': 7, 'seconds': 1},
                    {'attempt': 1, 'outcome': 'passed', 'native_exit': 0, 'seconds': float('nan')}]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                performance.summarize([row])

    def test_incompatible_or_failed_baseline_is_not_compared(self):
        samples = [{'attempt': 1, 'outcome': 'passed', 'native_exit': 0, 'seconds': 1}]
        baseline = {'schema': 1, 'measurement': {'runner': 'hosted', 'harness': performance.HARNESS, 'planned_attempts': 1, 'toolchain_lock_sha256': 'a' * 64},
                    'samples': samples, 'summary': performance.summarize(samples),
                    'source': {'inputs_sha256': 'known'}, 'source_after': {'inputs_sha256': 'known'}}
        candidate = {**baseline, 'measurement': {**baseline['measurement'], 'runner': 'local'}}
        with self.assertRaisesRegex(ValueError, 'configurations differ'):
            performance.compare(candidate, baseline)
        candidate['measurement'] = {**baseline['measurement'], 'toolchain_lock_sha256': 'b' * 64}
        with self.assertRaisesRegex(ValueError, 'configurations differ'):
            performance.compare(candidate, baseline)
        candidate['measurement'] = baseline['measurement']
        candidate['summary'] = {**baseline['summary'], 'native_success': False}
        with self.assertRaisesRegex(ValueError, 'disagrees'):
            performance.compare(candidate, baseline)

    def test_missing_samples_cannot_be_replaced_by_a_successful_summary(self):
        record = {'schema': 1, 'measurement': {'harness': performance.HARNESS, 'toolchain_lock_sha256': 'a' * 64, 'planned_attempts': 30},
                  'samples': [], 'summary': {'native_success': True, 'successful_median_seconds': 0.001}}
        with self.assertRaisesRegex(ValueError, 'inventory is incomplete'):
            performance.compare(record, record)

    def test_native_failure_retains_every_actual_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = performance.experiment([sys.executable, '-c', 'raise SystemExit(7)'], Path(tmp),
                label='failure-control', runner='unittest', warm_state='unspecified', attempts=3)
            self.assertEqual(3, result['summary']['failed'])
            self.assertEqual([7, 7, 7], [row['native_exit'] for row in result['samples']])
            self.assertEqual(3, len((Path(tmp) / 'samples.jsonl').read_text().splitlines()))
            with self.assertRaisesRegex(ValueError, 'already exists'):
                performance.experiment([sys.executable, '-c', 'pass'], Path(tmp),
                    label='overwrite-control', runner='unittest', warm_state='unspecified')


if __name__ == '__main__':
    unittest.main()
