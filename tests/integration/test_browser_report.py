import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_report import EXPECTED, verify


def report():
    specs = [{'id': str(i), 'title': title, 'file': 'contracts.spec.mjs', 'ok': True,
              'tests': [{'expectedStatus': 'passed', 'status': 'expected', 'results': [{'status': 'passed', 'errors': []}]}]}
             for i, title in enumerate(sorted(EXPECTED))]
    return {'suites': [{'specs': specs}], 'errors': [], 'stats': {'expected': 7, 'unexpected': 0, 'skipped': 0, 'flaky': 0}}


class BrowserReportContract(unittest.TestCase):
    def test_complete_native_inventory_passes(self):
        self.assertEqual(verify(report(), report()), 7)

    def test_same_total_substitution_fails(self):
        candidate = report()
        candidate['suites'][0]['specs'][0]['title'] = 'unrelated passing browser test'
        with self.assertRaisesRegex(AssertionError, 'substituted'):
            verify(report(), candidate)

    def test_duplicate_native_identity_fails(self):
        candidate = report()
        candidate['suites'][0]['specs'][1]['id'] = candidate['suites'][0]['specs'][0]['id']
        with self.assertRaisesRegex(AssertionError, 'foreign'):
            verify(report(), candidate)

    def test_skipped_test_cannot_hide_behind_pass_counts(self):
        candidate = report()
        candidate['suites'][0]['specs'][0]['tests'][0]['results'][0]['status'] = 'skipped'
        with self.assertRaises(AssertionError):
            verify(report(), candidate)

    def test_global_setup_failure_is_not_a_test_pass(self):
        candidate = report()
        candidate['errors'] = [{'message': 'global setup failed'}]
        with self.assertRaisesRegex(AssertionError, 'global'):
            verify(report(), candidate)


if __name__ == '__main__':
    unittest.main()
