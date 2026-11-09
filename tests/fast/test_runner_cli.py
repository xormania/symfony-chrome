"""Run real CLI suites in disposable repositories and corrupt retained evidence."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SUBJECT_ROOT = Path(os.environ.get('TEST_SUBJECT_ROOT', Path(__file__).resolve().parents[2]))


class RunnerCliContract(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'checkout'
        self.root.mkdir()
        shutil.copytree(SUBJECT_ROOT / 'bin', self.root / 'bin')
        shutil.copy2(SUBJECT_ROOT / 'toolchain.lock.json', self.root / 'toolchain.lock.json')
        (self.root / 'tools/testing').mkdir(parents=True)
        shutil.copy2(SUBJECT_ROOT / 'tools/testing/runner.py', self.root / 'tools/testing/runner.py')
        (self.root / 'tests').mkdir()
        (self.root / '.gitignore').write_text('artifacts/\n**/__pycache__/\n')
        manifest = {'schema': 1, 'profiles': {'required': ['native-contract']}, 'suites': {
            'native-contract': {'script': 'tests/native.py', 'timeout': 5, 'checks': ['fixture.boot']}}}
        (self.root / 'tests/manifest.json').write_text(json.dumps(manifest))
        (self.root / 'tests/native.py').write_text('''import argparse, json, os, sys
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--evidence', required=True); a=p.parse_args()
mode=os.environ.get('TEST_NATIVE_MODE', 'healthy')
if mode != 'missing':
    check='different.boot' if mode == 'substitution' else 'fixture.boot'
    data={'schema':1, 'checks':[{'id':check, 'outcome':'passed', 'assertions':2}]}
    Path(a.evidence, 'checks.json').write_text(json.dumps(data))
print('native fixture executed')
sys.exit(int(os.environ.get('TEST_NATIVE_EXIT', '0')))
''')
        self.git('init', '-q')
        self.git('add', '.')
        self.git('-c', 'user.name=xor', '-c', 'user.email=127287135+xormania@users.noreply.github.com',
                 'commit', '-qm', 'test fixture')
        self.env = dict(os.environ)
        self.env.pop('TEST_NATIVE_MODE', None)
        self.env.pop('TEST_NATIVE_EXIT', None)

    def git(self, *args):
        subprocess.run(['git', *args], cwd=self.root, capture_output=True, check=True)

    def invoke(self, *args, **environment):
        return subprocess.run([sys.executable, str(self.root / 'bin/dev'), *args], cwd=self.root,
                              env={**self.env, **environment}, capture_output=True, text=True, timeout=15)

    def attempt(self, run_id):
        run = self.root / 'artifacts' / run_id
        attempt_id = json.loads((run / 'latest.json').read_text())['attempt_id']
        return run / attempt_id

    def healthy(self, run_id='contract'):
        result = self.invoke('test', '--suite', 'native-contract', '--run', run_id)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return self.attempt(run_id)

    def test_healthy_public_run_and_retained_report(self):
        attempt = self.healthy()
        plan = json.loads((attempt / 'plan.json').read_text())
        report = json.loads((attempt / 'results.json').read_text())
        self.assertEqual(['native-contract'], plan['selected'])
        self.assertEqual(0, report['results'][0]['native_exit'])
        result = self.invoke('report', 'contract')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_missing_and_substituted_evidence_fail_a_native_zero(self):
        for mode in ('missing', 'substitution'):
            with self.subTest(mode=mode):
                result = self.invoke('test', '--suite', 'native-contract', '--run', mode, TEST_NATIVE_MODE=mode)
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                report = json.loads((self.attempt(mode) / 'results.json').read_text())
                self.assertEqual(0, report['results'][0]['native_exit'])
                self.assertTrue(report['errors'])
                self.assertNotEqual(0, self.invoke('report', mode).returncode)

    def test_native_failure_is_retained_despite_passing_check_record(self):
        result = self.invoke('test', '--suite', 'native-contract', '--run', 'native-failure', TEST_NATIVE_EXIT='17')
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        report = json.loads((self.attempt('native-failure') / 'results.json').read_text())
        self.assertEqual(17, report['results'][0]['native_exit'])
        self.assertEqual('passed', report['results'][0]['checks'][0]['outcome'])
        self.assertTrue(report['errors'])

    def test_retained_artifact_hash_and_presence_are_checked(self):
        for mutation in ('changed', 'missing', 'escape'):
            with self.subTest(mutation=mutation):
                attempt = self.healthy(mutation)
                if mutation == 'changed':
                    (attempt / 'native-contract/checks.json').write_text('{"changed":true}')
                elif mutation == 'missing':
                    (attempt / 'native-contract/native.log').unlink()
                else:
                    report_path = attempt / 'results.json'
                    report = json.loads(report_path.read_text())
                    outside = attempt.parent / 'outside.txt'
                    outside.write_text('outside attempt')
                    report['results'][0]['artifacts'][0]['path'] = '../outside.txt'
                    report_path.write_text(json.dumps(report))
                result = self.invoke('report', mutation)
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)

    def test_deleting_artifact_inventory_cannot_hide_corrupted_native_checks(self):
        attempt = self.healthy('inventory-deleted')
        (attempt / 'native-contract/checks.json').write_text('{"changed":true}')
        report_path = attempt / 'results.json'
        report = json.loads(report_path.read_text())
        report['results'][0]['artifacts'] = []
        report_path.write_text(json.dumps(report))
        result = self.invoke('report', 'inventory-deleted')
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)

    def test_matching_plan_and_report_must_still_belong_to_requested_attempt(self):
        for key, foreign in (('run_id', 'foreign-run'), ('attempt_id', '0' * 32)):
            with self.subTest(identity=key):
                run_id = 'folder-' + key.replace('_', '-')
                attempt = self.healthy(run_id)
                for name in ('plan.json', 'results.json'):
                    path = attempt / name
                    data = json.loads(path.read_text())
                    data[key] = foreign
                    path.write_text(json.dumps(data))
                result = self.invoke('report', run_id)
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)

    def test_rerun_retains_the_original_attempt(self):
        first = self.healthy('rerun')
        original = (first / 'results.json').read_bytes()
        second = self.healthy('rerun')
        self.assertNotEqual(first, second)
        self.assertEqual(original, (first / 'results.json').read_bytes())
        self.assertTrue((first / 'native-contract/checks.json').is_file())

    def test_unknown_or_zero_match_selection_never_executes_a_suite(self):
        for selector in (('--suite', 'unknown'), ('--scenario', 'not-registered'), ('--profile', 'unknown')):
            with self.subTest(selector=selector):
                result = self.invoke('test', *selector)
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertFalse((self.root / 'artifacts').exists())

    def test_list_is_side_effect_free(self):
        result = self.invoke('test', '--list', '--json')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(['native-contract'], list(json.loads(result.stdout)['suites']))
        self.assertFalse((self.root / 'artifacts').exists())
        self.assertFalse((self.root / 'workspaces').exists())


if __name__ == '__main__':
    unittest.main()
