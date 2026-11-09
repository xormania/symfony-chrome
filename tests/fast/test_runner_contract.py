"""Acceptance controls: native success alone cannot establish verified execution."""
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest


ROOT = Path(os.environ.get('TEST_SUBJECT_ROOT', Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('runner_subject', ROOT / 'tools/testing/runner.py')
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


class ReportContract(unittest.TestCase):
    def setUp(self):
        self.plan = {'schema': 1, 'run_id': 'run-a', 'attempt_id': 'attempt-a',
                     'source': {'commit': 'a' * 40, 'dirty': False},
                     'selected': ['unit', 'consumer']}
        self.report = {'schema': 1, 'run_id': 'run-a', 'attempt_id': 'attempt-a',
                       'source': deepcopy(self.plan['source']), 'results': [
                           {'suite_id': suite, 'native_exit': 0, 'outcome': 'passed',
                            'checks': [{'id': suite + '.boot', 'outcome': 'passed', 'assertions': 2}],
                            'artifacts': []}
                           for suite in self.plan['selected']]}

    def assertRejected(self, report=None, plan=None):
        errors = runner.validate_report(self.plan if plan is None else plan,
                                        self.report if report is None else report)
        self.assertIsInstance(errors, list)
        self.assertTrue(errors, 'invalid acceptance evidence was accepted')

    def test_complete_matching_execution_is_accepted(self):
        self.assertEqual([], runner.validate_report(self.plan, self.report))

    def test_report_order_is_not_execution_identity(self):
        self.report['results'].reverse()
        self.assertEqual([], runner.validate_report(self.plan, self.report))

    def test_missing_duplicated_and_substituted_suites_are_rejected(self):
        for mutation in ('missing', 'duplicate', 'same-count-substitution', 'unexpected'):
            with self.subTest(mutation=mutation):
                report = deepcopy(self.report)
                if mutation == 'missing':
                    report['results'].pop()
                elif mutation == 'duplicate':
                    report['results'][1] = deepcopy(report['results'][0])
                elif mutation == 'same-count-substitution':
                    report['results'][1]['suite_id'] = 'different-consumer'
                else:
                    report['results'].append({**deepcopy(report['results'][0]), 'suite_id': 'extra'})
                self.assertRejected(report)

    def test_foreign_run_attempt_source_and_schema_are_rejected(self):
        for key, value in (('run_id', 'run-b'), ('attempt_id', 'attempt-b'),
                           ('source', {'commit': 'b' * 40, 'dirty': False}), ('schema', 42)):
            with self.subTest(key=key):
                report = deepcopy(self.report)
                report[key] = value
                self.assertRejected(report)

    def test_matching_unknown_schema_is_not_a_valid_identity(self):
        for schema in (42, True, '1', None):
            with self.subTest(schema=schema):
                plan = {**self.plan, 'schema': schema}
                report = {**self.report, 'schema': schema}
                self.assertRejected(report, plan)

    def test_empty_or_duplicated_selection_cannot_pass(self):
        for selected in ([], ['unit', 'unit']):
            with self.subTest(selected=selected):
                plan = {**self.plan, 'selected': selected}
                report = {**self.report, 'results': [] if not selected else self.report['results']}
                self.assertRejected(report, plan)

    def test_missing_and_duplicate_check_identity_cannot_pass(self):
        for checks in ([], [{'id': 'boot', 'outcome': 'passed', 'assertions': 1}] * 2):
            with self.subTest(checks=checks):
                report = deepcopy(self.report)
                report['results'][0]['checks'] = checks
                self.assertRejected(report)

    def test_discovered_check_inventory_rejects_same_count_substitution(self):
        self.plan['expected_checks'] = {'unit': ['unit.boot'], 'consumer': ['consumer.boot']}
        self.assertEqual([], runner.validate_report(self.plan, self.report))
        self.report['results'][1]['checks'][0]['id'] = 'different-consumer.boot'
        self.assertRejected()

    def test_native_or_assertion_failure_cannot_be_hidden_by_passed_label(self):
        mutations = [('native_exit', 7), ('native_exit', None), ('outcome', 'failed'),
                     ('outcome', 'error'), ('outcome', 'skipped')]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                report = deepcopy(self.report)
                report['results'][0][key] = value
                self.assertRejected(report)
        for outcome in ('failed', 'error', 'skipped', 'unavailable', 'not_started'):
            with self.subTest(check_outcome=outcome):
                report = deepcopy(self.report)
                report['results'][0]['checks'][0]['outcome'] = outcome
                self.assertRejected(report)

    def test_timeout_or_truncation_cannot_be_hidden_by_native_zero(self):
        for flag in ('timed_out', 'truncated'):
            with self.subTest(flag=flag):
                report = deepcopy(self.report)
                report['results'][0][flag] = True
                self.assertRejected(report)

    def test_zero_missing_invalid_and_boolean_assertion_counts_cannot_pass(self):
        for count in (0, -1, None, '2', True, False, 1.5):
            with self.subTest(count=count):
                report = deepcopy(self.report)
                report['results'][0]['checks'][0]['assertions'] = count
                self.assertRejected(report)
        report = deepcopy(self.report)
        del report['results'][0]['checks'][0]['assertions']
        self.assertRejected(report)

    def test_input_records_are_not_repaired_or_mutated_by_validation(self):
        before = deepcopy((self.plan, self.report))
        runner.validate_report(self.plan, self.report)
        self.assertEqual(before, (self.plan, self.report))


class CaptureContract(unittest.TestCase):
    def test_parent_exit_does_not_waive_descendant_output_deadline(self):
        with tempfile.TemporaryDirectory() as temporary:
            child_file = Path(temporary) / 'child.pid'
            command = [sys.executable, '-c',
                       'import subprocess,sys; from pathlib import Path; '
                       'child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(8)"]); '
                       f'Path({str(child_file)!r}).write_text(str(child.pid)); '
                       'print("parent completed",flush=True)']
            started = time.monotonic()
            native_exit, timed_out, truncated = runner.capture(command, Path(temporary), 0.2)
            elapsed = time.monotonic() - started
            child_pid = int(child_file.read_text())
            state_file = Path('/proc') / str(child_pid) / 'stat'
            state = state_file.read_text().rsplit(')', 1)[1].split()[0] if state_file.exists() else None
        self.assertTrue(timed_out, f'parent exit {native_exit} was accepted while stdout remained open for {elapsed:.2f}s')
        self.assertLess(elapsed, 4.0, 'a descendant retained the output pipe beyond the suite deadline and cleanup grace')
        self.assertFalse(truncated)
        self.assertIn(state, (None, 'Z'), 'the timed-out descendant still runs after capture returns')


if __name__ == '__main__':
    unittest.main()
