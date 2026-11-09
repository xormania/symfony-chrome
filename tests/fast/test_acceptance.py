"""Independent downloaded-job evidence controls for the required CI aggregate."""
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

OWN_ROOT = Path(__file__).resolve().parents[2]
SUBJECT_ROOT = Path(os.environ.get('TEST_SUBJECT_ROOT', OWN_ROOT))
sys.path.insert(0, str(SUBJECT_ROOT / 'tools/testing'))
AGGREGATE_ROOT = Path(os.environ.get('TEST_AGGREGATE_ROOT', OWN_ROOT))
spec = importlib.util.spec_from_file_location('acceptance_subject', AGGREGATE_ROOT / 'tools/ci/acceptance.py')
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


class AcceptanceContract(unittest.TestCase):
    source = 'a' * 40
    workflow_run = '12345'
    workflow_attempt = '2'

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.evidence = self.root / 'downloaded'
        self.evidence.mkdir()
        self.mapping = {'fast': ['fast'], 'package': ['package'], 'integration': ['support', 'environment']}
        self.jobs = {job: {'result': 'success'} for job in self.mapping}
        names = ['fast', 'package', 'support', 'environment', 'browser']
        self.manifest = {'schema': 1, 'profiles': {'required': ['fast', 'package', 'support', 'environment']},
                         'suites': {name: {'checks': [name + '.executed']} for name in names}}
        self.manifest_path = self.root / 'manifest.json'
        self.save(self.manifest_path, self.manifest)
        self.manifest_patch = patch.object(acceptance, 'MANIFEST_PATH', self.manifest_path)
        self.manifest_patch.start()
        self.addCleanup(self.manifest_patch.stop)
        self.directories = {}
        for job, suites in self.mapping.items():
            for suite in suites:
                self.directories[suite] = self.produce(job, suite)

    @staticmethod
    def save(path, value):
        path.write_text(json.dumps(value, sort_keys=True) + '\n')

    def produce(self, job, suite, run_suffix=''):
        run_id = 'test-' + suite + run_suffix
        attempt_id = hashlib.sha256(run_id.encode()).hexdigest()[:32]
        directory = self.evidence / f'{job}-{self.workflow_run}-{self.workflow_attempt}' / run_id / attempt_id
        native = directory / suite
        native.mkdir(parents=True)
        checks = [{'id': suite + '.executed', 'outcome': 'passed', 'assertions': 2}]
        self.save(native / 'checks.json', {'schema': 1, 'checks': checks})
        (native / 'native.log').write_text('controlled native execution completed\n')
        inventory = [{'path': f'{suite}/{path.name}', 'size': path.stat().st_size,
                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(native.iterdir())]
        source = {'commit': self.source, 'dirty': False, 'inputs_sha256': 'b' * 64}
        plan = {'schema': 1, 'run_id': run_id, 'attempt_id': attempt_id, 'source': source,
                'github_run': self.workflow_run, 'github_attempt': self.workflow_attempt,
                'selected': [suite], 'expected_checks': {suite: [suite + '.executed']}}
        report = {key: deepcopy(plan[key]) for key in ('schema', 'run_id', 'attempt_id', 'source')}
        report['results'] = [{'suite_id': suite, 'native_exit': 0, 'outcome': 'passed',
                              'checks': checks, 'artifacts': inventory, 'timed_out': False, 'truncated': False}]
        self.save(directory / 'plan.json', plan)
        self.save(directory / 'results.json', report)
        return directory

    def validate(self, jobs=None, mapping=None):
        return acceptance.validate_jobs(self.jobs if jobs is None else jobs, self.evidence,
                                        self.mapping if mapping is None else mapping, self.source,
                                        self.workflow_run, self.workflow_attempt)

    def mutate(self, suite, name, change):
        path = self.directories[suite] / name
        value = json.loads(path.read_text())
        change(value)
        self.save(path, value)

    def test_all_current_required_suites_across_separate_attempts_pass(self):
        self.assertEqual([], self.validate())

    def test_exact_required_jobs_must_succeed(self):
        for status in ('failure', 'skipped', 'cancelled', None, 'unknown'):
            with self.subTest(status=status):
                jobs = deepcopy(self.jobs)
                jobs['integration']['result'] = status
                self.assertTrue(self.validate(jobs))
        for change in ('missing', 'extra'):
            with self.subTest(change=change):
                jobs = deepcopy(self.jobs)
                if change == 'missing':
                    del jobs['fast']
                else:
                    jobs['unrequested'] = {'result': 'success'}
                self.assertTrue(self.validate(jobs))

    def test_successful_conclusions_without_execution_evidence_fail(self):
        shutil.rmtree(self.evidence / f'package-{self.workflow_run}-{self.workflow_attempt}')
        self.assertTrue(self.validate())

    def test_missing_native_report_cannot_be_hidden_by_success(self):
        (self.directories['environment'] / 'results.json').unlink()
        self.assertTrue(self.validate())

    def test_wrong_source_and_stale_workflow_identity_fail(self):
        for key, value in (('source', {'commit': 'c' * 40}), ('github_run', '12344'), ('github_attempt', '1')):
            with self.subTest(key=key):
                path = self.directories['support'] / 'plan.json'
                original = path.read_bytes()
                self.mutate('support', 'plan.json', lambda plan: plan.update({key: value}))
                self.assertTrue(self.validate())
                path.write_bytes(original)

    def test_matching_foreign_plan_report_still_fail_actual_directory_identity(self):
        for name in ('plan.json', 'results.json'):
            self.mutate('fast', name, lambda value: value.update(run_id='foreign-run', attempt_id='0' * 32))
        self.assertTrue(self.validate())

    def test_same_count_suite_substitution_and_duplicate_attempts_fail(self):
        environment = self.directories['environment']
        shutil.rmtree(environment.parent)
        self.produce('integration', 'browser')
        self.assertTrue(self.validate(), 'optional browser replaced required environment at the same result count')

    def test_duplicate_suite_in_another_valid_attempt_fails(self):
        self.produce('integration', 'support', '-duplicate')
        self.assertTrue(self.validate())

    def test_current_manifest_check_inventory_is_independent_of_downloaded_plan(self):
        suite = 'fast'
        directory = self.directories[suite]
        alternate = [{'id': 'fast.some-other-check', 'outcome': 'passed', 'assertions': 2}]
        self.save(directory / suite / 'checks.json', {'schema': 1, 'checks': alternate})
        self.mutate(suite, 'plan.json', lambda plan: plan.update(expected_checks={suite: ['fast.some-other-check']}))
        def change_report(report):
            report['results'][0]['checks'] = alternate
            for item in report['results'][0]['artifacts']:
                path = directory / item['path']
                item.update(size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.mutate(suite, 'results.json', change_report)
        self.assertTrue(self.validate())

    def test_workflow_mapping_cannot_omit_a_new_required_suite(self):
        self.manifest['profiles']['required'].append('browser')
        self.save(self.manifest_path, self.manifest)
        self.assertTrue(self.validate(), 'workflow omitted browser after manifest made it required')

    def test_corrupted_or_deleted_artifact_inventory_cannot_pass(self):
        (self.directories['package'] / 'package/checks.json').write_text('{"corrupt":true}')
        self.mutate('package', 'results.json', lambda report: report['results'][0].update(artifacts=[]))
        self.assertTrue(self.validate())

    def test_native_failure_and_incomplete_execution_cannot_pass(self):
        path = self.directories['fast'] / 'results.json'
        original = path.read_bytes()
        for update in ({'native_exit': 17}, {'timed_out': True}, {'truncated': True}, {'outcome': 'skipped'}):
            with self.subTest(update=update):
                self.mutate('fast', 'results.json', lambda report: report['results'][0].update(update))
                self.assertTrue(self.validate())
                path.write_bytes(original)

    def test_artifact_name_is_bound_to_current_workflow(self):
        selected = self.evidence / f'fast-{self.workflow_run}-{self.workflow_attempt}'
        selected.rename(self.evidence / 'fast-99999-1')
        self.assertTrue(self.validate())

    def test_additional_required_job_is_valid_only_when_declared_and_complete(self):
        self.mapping['compatibility'] = ['browser']
        self.jobs['compatibility'] = {'result': 'success'}
        self.manifest['profiles']['required'].append('browser')
        self.save(self.manifest_path, self.manifest)
        self.produce('compatibility', 'browser')
        self.assertEqual([], self.validate())

    def test_public_cli_uses_real_needs_and_job_suites_environment(self):
        args = [sys.executable, str(AGGREGATE_ROOT / 'tools/ci/acceptance.py'), '--evidence', str(self.evidence),
                '--source', self.source, '--run', self.workflow_run, '--attempt', self.workflow_attempt,
                '--manifest', str(self.manifest_path)]
        env = {**os.environ, 'PYTHONPATH': str(SUBJECT_ROOT / 'tools/testing'),
               'REQUIRED_JOBS': json.dumps(self.jobs), 'JOB_SUITES': json.dumps(self.mapping)}
        result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.jobs['fast']['result'] = 'skipped'
        result = subprocess.run(args, env={**env, 'REQUIRED_JOBS': json.dumps(self.jobs)},
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['errors'])


if __name__ == '__main__':
    unittest.main()
