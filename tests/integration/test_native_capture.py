"""Native peers qualify collection bounds before output becomes Python objects."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


ROOT = Path(os.environ.get('TEST_SUBJECT_ROOT', Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(ROOT / 'bin'))
from processlib import NativeCaptureError, run_captured
import devlib


LIMIT = 8 * 1024 * 1024


class NativeCaptureContract(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='native-capture-control-')
        self.directory = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def execute(self, source, name='native', **kwargs):
        evidence = self.directory / name
        return evidence, run_captured([sys.executable, '-u', '-c', source], evidence, **kwargs)

    def metadata(self, evidence):
        return json.loads((evidence / 'native-capture.json').read_text())

    def test_json_stdout_and_diagnostic_stderr_remain_separate(self):
        source = "import json,sys; print(json.dumps({'marker':'native-json','value':37})); print('native diagnostic',file=sys.stderr)"
        evidence, result = self.execute(source)
        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(0, result.returncode)
        self.assertEqual({'marker': 'native-json', 'value': 37}, json.loads(result.stdout))
        self.assertEqual(b'native diagnostic\n', result.stderr)
        self.assertEqual(result.stdout, (evidence / 'stdout').read_bytes())
        self.assertEqual(result.stderr, (evidence / 'stderr').read_bytes())
        state = self.metadata(evidence)
        self.assertEqual(0, state['native_exit'])
        self.assertIs(False, state['timed_out'])
        self.assertIs(False, state['truncated'])

    def test_text_mode_and_nonzero_native_exit_preserve_subprocess_semantics(self):
        source = "import sys; print('native café'); print('native stderr',file=sys.stderr); sys.exit(7)"
        evidence, result = self.execute(source, text=True, encoding='utf-8', check=False)
        self.assertEqual(7, result.returncode)
        self.assertEqual('native café\n', result.stdout)
        self.assertEqual('native stderr\n', result.stderr)
        self.assertEqual(7, self.metadata(evidence)['native_exit'])
        with self.assertRaises(subprocess.CalledProcessError) as failure:
            self.execute(source, name='checked', check=True)
        self.assertEqual(7, failure.exception.returncode)
        self.assertEqual(b'native caf\xc3\xa9\n', failure.exception.stdout)
        self.assertEqual(b'native stderr\n', failure.exception.stderr)

    def test_nine_mib_stdout_cannot_pass_through_capture_output(self):
        evidence = self.directory / 'stdout-overflow'
        source = "import sys; sys.stdout.buffer.write(b'x'*(9*1024*1024)); sys.stdout.buffer.flush()"
        with self.assertRaises(NativeCaptureError):
            run_captured([sys.executable, '-u', '-c', source], evidence, check=False, timeout=5)
        state = self.metadata(evidence)
        self.assertIs(True, state['truncated'])
        self.assertLessEqual((evidence / 'stdout').stat().st_size + (evidence / 'stderr').stat().st_size, LIMIT)
        self.assertGreater((evidence / 'stdout').stat().st_size, 0)

    def test_stdout_and_stderr_share_one_byte_budget(self):
        evidence = self.directory / 'combined-overflow'
        source = "import sys; sys.stdout.buffer.write(b'o'*(5*1024*1024)); sys.stdout.buffer.flush(); sys.stderr.buffer.write(b'e'*(5*1024*1024)); sys.stderr.buffer.flush()"
        with self.assertRaises(NativeCaptureError):
            run_captured([sys.executable, '-u', '-c', source], evidence, check=False, timeout=5)
        state = self.metadata(evidence)
        self.assertIs(True, state['truncated'])
        sizes = [(evidence / name).stat().st_size for name in ('stdout', 'stderr')]
        self.assertTrue(all(size > 0 for size in sizes), sizes)
        self.assertLessEqual(sum(sizes), LIMIT)

    def test_devlib_execute_bounds_the_original_inner_capture_boundary(self):
        state = self.directory / 'state'
        evidence = self.directory / 'evidence'
        data = {'state': str(state), 'evidence': str(evidence)}
        command = [sys.executable, '-u', '-c', "import sys; sys.stdout.buffer.write(b'x'*(9*1024*1024))"]
        with patch.object(devlib, 'exec_command', return_value=command), \
                patch.object(devlib, 'environment', return_value=os.environ.copy()):
            with self.assertRaises(NativeCaptureError):
                devlib.execute(data, 'controlled-native-command', capture_output=True, check=False, timeout=5)
        statuses = list(evidence.rglob('*.json'))
        self.assertEqual(1, len(statuses))
        self.assertIs(True, json.loads(statuses[0].read_text())['truncated'])
        self.assertLessEqual(sum(path.stat().st_size for path in state.rglob('*') if path.is_file()), LIMIT)

    def test_devlib_private_capture_does_not_publish_payload_or_command(self):
        state = self.directory / 'private-state'
        evidence = self.directory / 'public-evidence'
        data = {'state': str(state), 'evidence': str(evidence)}
        marker = 'controlled-private-container-value-37'
        source = "import sys; print(" + repr(marker) + "); print('private stderr',file=sys.stderr)"
        command = [sys.executable, '-u', '-c', source]
        with patch.object(devlib, 'exec_command', return_value=command), \
                patch.object(devlib, 'environment', return_value=os.environ.copy()):
            result = devlib.execute(data, 'controlled-private-command', capture_output=True, text=True)
        self.assertEqual(marker + '\n', result.stdout)
        self.assertEqual('private stderr\n', result.stderr)
        raw = list(state.rglob('stdout'))
        self.assertEqual(1, len(raw))
        self.assertEqual(result.stdout, raw[0].read_text())
        statuses = list(evidence.rglob('*.json'))
        self.assertEqual(1, len(statuses))
        self.assertEqual('private_ephemeral', json.loads(statuses[0].read_text())['log_visibility'])
        for path in evidence.rglob('*'):
            if path.is_file():
                self.assertNotIn(marker.encode(), path.read_bytes())
                self.assertNotIn(b'private stderr', path.read_bytes())
                self.assertNotIn(b'controlled-private-command', path.read_bytes())

    def test_native_timeout_is_an_error_even_when_exit_checks_are_disabled(self):
        evidence = self.directory / 'timeout'
        started = time.monotonic()
        with self.assertRaises(NativeCaptureError):
            run_captured([sys.executable, '-u', '-c', "import time; print('before-timeout',flush=True); time.sleep(5)"],
                         evidence, check=False, timeout=0.5)
        self.assertLess(time.monotonic() - started, 4)
        self.assertIs(True, self.metadata(evidence)['timed_out'])
        self.assertIn(b'before-timeout', (evidence / 'stdout').read_bytes())

    def test_exited_parent_cannot_leave_a_descendant_holding_diagnostic_pipes(self):
        evidence = self.directory / 'descendant'
        marker = self.directory / 'descendant-ready.json'
        child = "import json,os,pathlib,time; pathlib.Path(" + repr(str(marker)) + ").write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp()})); print('descendant-ready',flush=True); time.sleep(5)"
        parent = "import subprocess,sys; subprocess.Popen([sys.executable,'-u','-c'," + repr(child) + "]); sys.exit(0)"
        started = time.monotonic()
        try:
            with self.assertRaises(NativeCaptureError):
                run_captured([sys.executable, '-u', '-c', parent], evidence, check=False, timeout=0.8)
            self.assertLess(time.monotonic() - started, 4)
            self.assertTrue(marker.is_file(), 'native descendant never established its readiness handshake')
            identity = json.loads(marker.read_text())
            self.assertNotEqual(os.getpgrp(), identity['pgid'], 'native command must own an isolated process group')
            self.assertIs(True, self.metadata(evidence)['timed_out'])
            state = Path('/proc') / str(identity['pid']) / 'stat'
            deadline = time.monotonic() + 1
            while True:
                try:
                    status = state.read_text().split(') ', 1)[1].split()[0]
                except (FileNotFoundError, ProcessLookupError):
                    status = None
                if status in (None, 'Z') or time.monotonic() >= deadline:
                    break
                time.sleep(0.01)
            self.assertIn(status, (None, 'Z'), 'owned native descendant is still running')
        finally:
            if marker.is_file():
                identity = json.loads(marker.read_text())
                try:
                    if identity['pgid'] != os.getpgrp():
                        os.killpg(identity['pgid'], signal.SIGKILL)
                    else:
                        os.kill(identity['pid'], signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == '__main__':
    unittest.main()
