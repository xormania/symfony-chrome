"""Inner commands must leave the owning suite time to unwind resources."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bin'))
from processlib import CLEANUP_GRACE, NativeCaptureError, SUITE_DEADLINE, run_captured


class NativeSuiteDeadline(unittest.TestCase):
    def test_exhausted_suite_budget_does_not_start_another_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'unexpected-execution'
            command = [sys.executable, '-c', 'from pathlib import Path;Path(' + repr(str(marker)) + ').write_text("executed")']
            env = {**os.environ, SUITE_DEADLINE: str(time.monotonic() + 1)}
            with self.assertRaises(NativeCaptureError):
                run_captured(command, root / 'evidence', env=env)
            state = json.loads((root / 'evidence/native-capture.json').read_text())
            self.assertIsNone(state['native_exit'])
            self.assertIs(True, state['timed_out'])
            self.assertFalse(marker.exists())

    def test_command_deadline_is_capped_by_remaining_suite_time(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            env = {**os.environ, SUITE_DEADLINE: str(time.monotonic() + CLEANUP_GRACE + 0.4)}
            with self.assertRaises(NativeCaptureError):
                run_captured([sys.executable, '-u', '-c', 'import time;print("ready",flush=True);time.sleep(10)'], evidence, env=env, timeout=30)
            state = json.loads((evidence / 'native-capture.json').read_text())
            self.assertGreater(state['timeout_seconds'], 0)
            self.assertLessEqual(state['timeout_seconds'], 0.4)
            self.assertIs(True, state['timed_out'])


if __name__ == '__main__':
    unittest.main()
