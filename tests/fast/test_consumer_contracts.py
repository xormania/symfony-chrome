"""Controls for native consumer identity and dependency preservation."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(os.environ.get('CONSUMER_TEST_ROOT', Path(__file__).resolve().parents[2]))
spec = importlib.util.spec_from_file_location('consumer', ROOT / 'tools/testing/consumer.py')
consumer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(consumer)


class ConsumerContracts(unittest.TestCase):
    def setUp(self):
        self.expected = [{'file': 'tests/e2e/lab.live-modal.spec.ts', 'title': 'dialog replacement'},
                         {'file': 'tests/e2e/lab.live-form.spec.ts', 'title': 'field validation'}]
        self.checkout = Path('/tmp/pinned-consumer')
        self.report = {'config': {'rootDir': str(self.checkout / 'tests/e2e')}, 'suites': [{'specs': [
            {'file': row['file'].split('/')[-1], 'title': row['title'], 'tests': [
                {'status': 'expected', 'expectedStatus': 'passed', 'results': [{'status': 'passed', 'errors': []}]}]}
            for row in self.expected]}]}

    def test_selected_native_tests_are_accepted(self):
        checks = consumer.native_results(self.report, self.expected, self.checkout)
        self.assertEqual(['consumer.uxor.modal', 'consumer.uxor.validation'], [row['id'] for row in checks])

    def test_same_total_with_foreign_test_cannot_pass(self):
        self.report['suites'][0]['specs'][1]['title'] = 'unrelated passing test'
        with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
            consumer.native_results(self.report, self.expected, self.checkout)

    def test_report_from_another_checkout_cannot_pass(self):
        self.report['config']['rootDir'] = '/tmp/other/tests/e2e'
        with self.assertRaisesRegex(ValueError, 'another consumer'):
            consumer.native_results(self.report, self.expected, self.checkout)

    def test_missing_duplicate_skipped_retried_and_global_error_fail(self):
        mutations = [
            lambda r: r['suites'].clear(),
            lambda r: r['suites'][0]['specs'].append(r['suites'][0]['specs'][0]),
            lambda r: r['suites'][0]['specs'][0]['tests'][0]['results'][0].update(status='skipped'),
            lambda r: r['suites'][0]['specs'][0]['tests'][0]['results'].append({'status': 'passed'}),
            lambda r: r.update(errors=[{'message': 'setup failed'}]),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                report = json.loads(json.dumps(self.report))
                mutate(report)
                with self.assertRaises(ValueError):
                    consumer.native_results(report, self.expected, self.checkout)

    def test_artifact_install_preserves_original_constraints(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'candidate.zip'
            archive.write_bytes(b'archive identity test')
            original = {'minimum-stability': 'stable', 'require': {'symfony/framework-bundle': '8.1.*'},
                        'require-dev': {'symfony/ai-mate': '^0.14'}}
            before = json.loads(json.dumps(original))
            entry = {'name': 'xormania/chrome-bundle', 'version': 'dev-ci', 'path': str(archive),
                     'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                     'manifest': {'name': 'xormania/chrome-bundle', 'require': {'php': '>=8.4'}}}
            result = consumer.add_archives(original, [entry])
            self.assertEqual(before, original)
            self.assertEqual('^0.14', result['require-dev']['symfony/ai-mate'])
            self.assertEqual('8.1.*', result['require']['symfony/framework-bundle'])
            self.assertEqual('stable', result['minimum-stability'])
            archive.write_bytes(b'tampered archive')
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                consumer.add_archives(original, [entry])


if __name__ == '__main__':
    unittest.main()
