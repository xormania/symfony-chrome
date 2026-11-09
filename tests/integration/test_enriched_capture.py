"""A bounded native failure must survive enriched-wrapper finalization."""
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(os.environ.get('TEST_SUBJECT_ROOT', Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(ROOT / 'bin'))
import magolib
import matelib


class EnrichedCaptureFailure(unittest.TestCase):
    def test_enriched_finally_keeps_partial_native_streams_and_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            data = {'run_id': 'native-failure', 'app': str(evidence / 'app'), 'evidence': str(evidence)}
            prepared = {'preparation_id': 'controlled', 'application_sha256': 'source', 'metadata': {}, 'wiring_reference_sha256': 'reference'}
            command = [sys.executable, '-u', '-c', 'import sys;sys.stdout.buffer.write(b"x"*(9*1024*1024));sys.stdout.flush()']
            with mock.patch.object(matelib, 'fresh', return_value=prepared), mock.patch.object(magolib, 'enriched_identity', return_value={'config': 'controlled'}), mock.patch.object(magolib, 'exec_command', return_value=command), mock.patch.object(magolib, 'environment', return_value=dict(os.environ)):
                row = magolib.run_enriched(data, ['analyze'])
            self.assertEqual('tool_failure', row['status'])
            self.assertEqual(3, row['exit'])
            self.assertIs(True, row['truncated'])
            retained = Path(row['evidence'])
            metadata = json.loads((retained / 'native-capture.json').read_text())
            size = (retained / 'stdout').stat().st_size
            self.assertGreater(size, 0, 'Wrapper finally erased the bounded native failure evidence')
            self.assertEqual(metadata['retained_bytes']['stdout'], size)
            self.assertEqual(metadata['native_exit'], row['native_exit'])
            self.assertIs(True, json.loads((retained / 'invocation.json').read_text())['truncated'])

    def test_cancellation_propagates_without_erasing_native_streams(self):
        class ControlledCancellation(BaseException):
            pass
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            data = {'run_id': 'native-interruption', 'app': str(evidence / 'app'), 'evidence': str(evidence)}
            prepared = {'preparation_id': 'controlled', 'application_sha256': 'source', 'metadata': {}, 'wiring_reference_sha256': 'reference'}
            command = [sys.executable, '-u', '-c', 'import os,signal,time;print("before-cancellation",flush=True);os.kill(os.getppid(),signal.SIGUSR1);time.sleep(10)']
            def interrupted(signum, frame):
                raise ControlledCancellation('controlled native interruption')
            previous = signal.signal(signal.SIGUSR1, interrupted)
            try:
                with mock.patch.object(matelib, 'fresh', return_value=prepared), mock.patch.object(magolib, 'enriched_identity', return_value={'config': 'controlled'}), mock.patch.object(magolib, 'exec_command', return_value=command), mock.patch.object(magolib, 'environment', return_value=dict(os.environ)):
                    with self.assertRaisesRegex(ControlledCancellation, 'controlled native interruption'):
                        magolib.run_enriched(data, ['analyze'])
            finally:
                signal.signal(signal.SIGUSR1, previous)
            retained = next((evidence / 'mago/enriched').iterdir())
            self.assertIn(b'before-cancellation', (retained / 'stdout').read_bytes())
            metadata = json.loads((retained / 'native-capture.json').read_text())
            self.assertEqual('ControlledCancellation', metadata['capture_error'])
            self.assertEqual((retained / 'stdout').stat().st_size, metadata['retained_bytes']['stdout'])
            self.assertIs(True, json.loads((retained / 'invocation.json').read_text())['incomplete_capture'])


if __name__ == '__main__':
    unittest.main()
