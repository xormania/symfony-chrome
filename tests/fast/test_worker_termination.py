"""Real SIGTERM delivery must unwind owned-resource cleanup and stop selection."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


SUBJECT_ROOT = Path(os.environ.get('TEST_SUBJECT_ROOT', Path(__file__).resolve().parents[2]))


class WorkerTerminationContract(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'checkout'
        (self.root / 'tools/testing').mkdir(parents=True)
        (self.root / 'control').mkdir()
        self.processes = []
        self.child_pids = []
        self.addCleanup(self.kill_remaining)

    def kill_remaining(self):
        # Native runner workers create their own sessions. Always clean both the
        # driver and any observed worker group, including when a regression fails.
        for pid in [process.pid for process in self.processes] + self.child_pids:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for process in self.processes:
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=3)

    def start(self, command, env=None):
        process = subprocess.Popen(command, cwd=self.root, env=env, start_new_session=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.processes.append(process)
        return process

    def await_ready(self, path, process):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if path.is_file():
                value = json.loads(path.read_text())
                self.child_pids.append(value['pid'])
                return value
            if process.poll() is not None:
                output, error = process.communicate()
                self.fail('Worker exited before the controlled setup handshake: ' + output + error)
            time.sleep(0.02)
        self.fail('Worker did not reach the controlled setup handshake')

    @staticmethod
    def process_state(pid):
        status = Path('/proc') / str(pid) / 'stat'
        return status.read_text().rsplit(')', 1)[1].split()[0] if status.exists() else None

    def test_environment_sigterm_runs_cleanup_after_setup_started(self):
        shutil.copy2(SUBJECT_ROOT / 'tools/testing/environment.py', self.root / 'tools/testing/environment.py')
        (self.root / 'bin').mkdir()
        cleanup = self.root / 'control/environment-cleanup.json'
        ready = self.root / 'control/environment-ready.json'
        (self.root / 'bin/docker').write_text('#!/bin/sh\nexit 0\n')
        (self.root / 'bin/docker').chmod(0o755)
        (self.root / 'bin/dev').write_text('''#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
run_id=sys.argv[sys.argv.index('--run')+1]
workspace=root/'workspaces'/run_id
workspace.mkdir(parents=True)
evidence=root/'artifacts'/run_id
evidence.mkdir(parents=True)
data={'run_id':run_id,'evidence':str(evidence)}
(workspace/'run.json').write_text(json.dumps(data))
(root/'control/environment-ready.json').write_text(json.dumps({'pid':os.getpid(),'run_id':run_id}))
while True:
    time.sleep(1)
''')
        (self.root / 'bin/dev').chmod(0o755)
        (self.root / 'bin/devlib.py').write_text('''import json, os, shutil, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(run_id):
    return json.loads((ROOT/'workspaces'/run_id/'run.json').read_text())
def compose(data, *args):
    return [sys.executable,'-c','print("controlled container log")']
def container_id(data):
    return 'controlled-container'
def environment(data):
    return dict(os.environ)
def exec_command(data, *args):
    raise AssertionError('setup must be interrupted before runtime probes')
def stop(data, purge=False):
    (ROOT/'control/environment-cleanup.json').write_text(json.dumps({'run_id':data['run_id'],'purge':purge}))
    if purge:
        shutil.rmtree(ROOT/'workspaces'/data['run_id'])
''')
        evidence = self.root / 'control/environment-evidence'
        env = {**os.environ, 'PATH': str(self.root / 'bin') + os.pathsep + os.environ['PATH']}
        process = self.start([sys.executable, 'tools/testing/environment.py', '--evidence', str(evidence)], env)
        observed = self.await_ready(ready, process)
        process.send_signal(signal.SIGTERM)
        output, error = process.communicate(timeout=8)
        self.assertNotEqual(0, process.returncode, output + error)
        self.assertTrue(cleanup.is_file(), 'SIGTERM bypassed the environment worker finally/stop boundary')
        self.assertEqual({'run_id': observed['run_id'], 'purge': True}, json.loads(cleanup.read_text()))
        self.assertFalse((self.root / 'workspaces' / observed['run_id']).exists())
        self.assertIn(self.process_state(observed['pid']), (None, 'Z'), 'the setup child survived interruption')

    def test_runner_sigterm_stops_owned_worker_and_does_not_start_later_suite(self):
        shutil.copytree(SUBJECT_ROOT / 'bin', self.root / 'bin', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(SUBJECT_ROOT / 'toolchain.lock.json', self.root / 'toolchain.lock.json')
        shutil.copy2(SUBJECT_ROOT / 'tools/testing/runner.py', self.root / 'tools/testing/runner.py')
        (self.root / 'tests').mkdir()
        (self.root / '.gitignore').write_text('artifacts/\ncontrol/\n**/__pycache__/\n')
        manifest = {'schema': 1, 'profiles': {'required': ['blocked', 'later']}, 'suites': {
            'blocked': {'script': 'tests/blocked.py', 'checks': ['blocked.work'], 'timeout': 60},
            'later': {'script': 'tests/later.py', 'checks': ['later.work'], 'timeout': 5}}}
        (self.root / 'tests/manifest.json').write_text(json.dumps(manifest))
        (self.root / 'tests/blocked.py').write_text('''import argparse,json,os,signal,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--evidence');a=p.parse_args()
root=Path(__file__).resolve().parents[1]
def interrupted(signum,frame):
    raise InterruptedError('controlled worker interrupted')
signal.signal(signal.SIGTERM,interrupted)
try:
    (root/'control/runner-ready.json').write_text(json.dumps({'pid':os.getpid()}))
    while True:
        time.sleep(1)
finally:
    (root/'control/runner-cleanup.json').write_text(json.dumps({'pid':os.getpid()}))
''')
        (self.root / 'tests/later.py').write_text('''import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--evidence');a=p.parse_args()
(Path(__file__).resolve().parents[1]/'control/later-started').write_text('started')
Path(a.evidence,'checks.json').write_text(json.dumps({'schema':1,'checks':[{'id':'later.work','outcome':'passed','assertions':1}]}))
''')
        for command in (['git', 'init', '-q'], ['git', 'add', '.'],
                        ['git', '-c', 'user.name=xor', '-c', 'user.email=127287135+xormania@users.noreply.github.com',
                         'commit', '-qm', 'test fixture']):
            subprocess.run(command, cwd=self.root, capture_output=True, check=True)
        process = self.start([sys.executable, 'bin/dev', 'test', '--profile', 'required', '--run', 'terminated'])
        observed = self.await_ready(self.root / 'control/runner-ready.json', process)
        process.send_signal(signal.SIGTERM)
        output, error = process.communicate(timeout=8)
        cleanup = self.root / 'control/runner-cleanup.json'
        self.assertTrue(cleanup.is_file(), 'runner termination did not unwind its owned native worker')
        self.assertEqual(130, process.returncode, output + error)
        self.assertEqual(observed['pid'], json.loads(cleanup.read_text())['pid'])
        self.assertFalse((self.root / 'control/later-started').exists(), 'later suite started after cancellation')
        self.assertIn(self.process_state(observed['pid']), (None, 'Z'), 'the native worker survived interruption')
        run = self.root / 'artifacts/terminated'
        attempt = json.loads((run / 'latest.json').read_text())['attempt_id']
        report = json.loads((run / attempt / 'results.json').read_text())
        self.assertEqual(['blocked', 'later'], [row['suite_id'] for row in report['results']])
        self.assertTrue(all(row['outcome'] == 'cancelled' and row['native_exit'] == 130 for row in report['results']))
        self.assertTrue(report['errors'])


if __name__ == '__main__':
    unittest.main()
