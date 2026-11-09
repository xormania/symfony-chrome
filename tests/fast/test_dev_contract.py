"""Public launcher behavior at the Docker process boundary; no daemon required."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SUBJECT_ROOT = Path(os.environ.get('TEST_SUBJECT_ROOT', Path(__file__).resolve().parents[2]))


class LauncherContract(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'checkout'
        self.root.mkdir()
        shutil.copytree(SUBJECT_ROOT / 'bin', self.root / 'bin')
        shutil.copy2(SUBJECT_ROOT / 'toolchain.lock.json', self.root / 'toolchain.lock.json')
        (self.root / 'fixtures/app').mkdir(parents=True)
        (self.root / 'fixtures/app/input.txt').write_text('checked-in fixture\n')
        (self.root / 'tools/serena/config').mkdir(parents=True)
        (self.root / 'tools/serena/config/project.yml').write_text('language_servers: [mago]\n')
        (self.root / 'compose.yaml').write_text('services: {}\n')
        self.events = Path(self.temporary.name) / 'docker-events.jsonl'
        fake = Path(self.temporary.name) / 'docker'
        fake.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ['TEST_DOCKER_EVENTS']).open('a') as stream:
    stream.write(json.dumps({'argv': args, 'app_env': os.environ.get('DEV_APP_ENV')}) + '\\n')
if 'check-platform-reqs' in args:
    print('platform requirements checked')
    sys.exit(int(os.environ.get('TEST_PLATFORM_EXIT', '0')))
if 'port' in args:
    print('127.0.0.1:18765')
elif 'ps' in args:
    print('controlled-container-id')
elif 'cat' in args:
    print('{"fixture": "test-image"}')
''')
        fake.chmod(0o755)
        self.env = {**os.environ, 'DEV_DOCKER': str(fake), 'TEST_DOCKER_EVENTS': str(self.events)}
        self.env.pop('DEV_IMAGE', None)

    def workspace(self, run_id='contract', app_env='dev', image='symfony-chrome-dev:local'):
        base = self.root / 'workspaces' / run_id
        for child in ('app', 'state', 'trusted'):
            (base / child).mkdir(parents=True, exist_ok=True)
        evidence = self.root / 'artifacts' / run_id
        evidence.mkdir(parents=True)
        data = {'schema': 1, 'run_id': run_id, 'repository': str(self.root),
                'project': 'contract-' + run_id, 'app': str(base / 'app'),
                'state': str(base / 'state'), 'trusted': str(base / 'trusted'),
                'evidence': str(evidence), 'port': 0, 'app_env': app_env,
                'private': None, 'image': image}
        (base / 'run.json').write_text(json.dumps(data))
        return data

    def invoke(self, *args, **environment):
        return subprocess.run([sys.executable, str(self.root / 'bin/dev'), *args],
                              cwd=self.root, env={**self.env, **environment},
                              capture_output=True, text=True, timeout=15)

    def docker_events(self):
        return [json.loads(line) for line in self.events.read_text().splitlines()] if self.events.exists() else []

    def test_doctor_preserves_platform_check_failure(self):
        self.workspace()
        result = self.invoke('doctor', '--run', 'contract', TEST_PLATFORM_EXIT='73')
        self.assertEqual(73, result.returncode, result.stdout + result.stderr)
        self.assertTrue(any('check-platform-reqs' in row['argv'] for row in self.docker_events()))

    def test_doctor_healthy_platform_control(self):
        self.workspace()
        result = self.invoke('doctor', '--run', 'contract', TEST_PLATFORM_EXIT='0')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('host port: 18765', result.stdout)

    def test_existing_run_never_silently_uses_another_environment(self):
        self.workspace(app_env='dev')
        result = self.invoke('up', '--run', 'contract', '--env', 'prod', '--no-build')
        marker = json.loads((self.root / 'workspaces/contract/run.json').read_text())
        if result.returncode == 0:
            self.assertEqual('prod', marker['app_env'], 'successful up ignored the requested production mode')
            self.assertTrue(self.docker_events(), 'successful up never invoked the selected environment')
            self.assertTrue(all(row['app_env'] == 'prod' for row in self.docker_events()))
        else:
            self.assertEqual('dev', marker['app_env'])
            self.assertEqual([], self.docker_events(), 'mode rejection happened after starting the wrong workload')

    def test_existing_run_accepts_its_recorded_environment(self):
        self.workspace(app_env='prod')
        result = self.invoke('up', '--run', 'contract', '--env', 'prod', '--no-build')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue(self.docker_events())
        self.assertTrue(all(row['app_env'] == 'prod' for row in self.docker_events()))

    def test_image_override_mismatch_never_starts_a_workload(self):
        self.workspace(image='recorded:one')
        result = self.invoke('up', '--run', 'contract', '--no-build', DEV_IMAGE='different:two')
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], self.docker_events())

    def test_foreign_workspace_marker_is_rejected_before_docker(self):
        data = self.workspace()
        data['repository'] = str(self.root / 'another-checkout')
        (self.root / 'workspaces/contract/run.json').write_text(json.dumps(data))
        result = self.invoke('doctor', '--run', 'contract')
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], self.docker_events())

    def test_unsafe_run_ids_do_not_create_or_start_workspaces(self):
        for run_id in ('../outside', '/absolute', 'has space', 'UPPER', 'a' * 81):
            with self.subTest(run_id=run_id):
                result = self.invoke('up', '--run', run_id, '--no-build')
                self.assertNotEqual(0, result.returncode)
        self.assertFalse((self.root / 'workspaces').exists())
        self.assertEqual([], self.docker_events())

    def test_purge_removes_only_its_workspace_and_keeps_evidence(self):
        first = self.workspace('first')
        self.workspace('second')
        evidence = Path(first['evidence']) / 'failed-attempt.json'
        evidence.write_text('{"outcome":"failed"}\n')
        original = (self.root / 'fixtures/app/input.txt').read_bytes()
        result = self.invoke('down', '--run', 'first', '--purge')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertFalse((self.root / 'workspaces/first').exists())
        self.assertTrue((self.root / 'workspaces/second/run.json').is_file())
        self.assertEqual('{"outcome":"failed"}\n', evidence.read_text())
        self.assertEqual(original, (self.root / 'fixtures/app/input.txt').read_bytes())


if __name__ == '__main__':
    unittest.main()
