"""Subprocess signals must unwind the public owned-workspace context."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

MODULES = Path(__file__).resolve().parent

CHILD = r'''
import json,pathlib,sys,time
sys.path.insert(0,sys.argv[1])
import contracts
root=pathlib.Path(sys.argv[2]);root.mkdir(exist_ok=True)
evidence=root/'evidence';evidence.mkdir()
data={'run_id':'controlled-signal','evidence':str(evidence)}
contracts.prepare=lambda *args,**kwargs:data
contracts.start=lambda *args,**kwargs:None
contracts.install_contract_fixture=lambda *args:None
def stop(value,purge=False):
 (root/'stop.json').write_text(json.dumps({'run_id':value['run_id'],'purge':purge}))
 if sys.argv[3]=='cleanup-error': raise RuntimeError('controlled cleanup failure')
contracts.stop=stop
try:
 with contracts.workspace():
  (root/'ready').write_text('owned context entered')
  checks=contracts.Checks(root/'native-checks')
  checks.check('controlled-blocking-contract',lambda:(time.sleep(60),1))
  (root/'continued').write_text('unexpected next-contract path')
  time.sleep(60)
except InterruptedError:
 sys.exit(130)
'''


class TerminationContract(unittest.TestCase):
    def exercise(self, mode):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            process = subprocess.Popen([sys.executable, '-u', '-c', CHILD, str(MODULES), str(root), mode],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 5
                while not (root / 'ready').exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue((root / 'ready').exists(), 'Controlled context did not start')
                process.send_signal(signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=5)
                self.assertTrue((root / 'stop.json').exists(), 'SIGTERM bypassed owned-workspace stop')
                self.assertEqual(json.loads((root / 'stop.json').read_text()), {'run_id': 'controlled-signal', 'purge': True})
                self.assertEqual(process.returncode, 130, stderr.decode())
                self.assertFalse((root / 'continued').exists(), 'Interrupted check continued to the next contract')
                cleanup = json.loads((root / 'evidence/contract-cleanup.json').read_text())
                self.assertEqual(cleanup['outcome'], 'error' if mode == 'cleanup-error' else 'passed')
                if mode == 'cleanup-error':
                    self.assertIn('controlled cleanup failure', cleanup['detail'])
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)

    def test_sigterm_runs_owned_stop_and_records_cleanup(self):
        self.exercise('healthy')

    def test_cleanup_error_preserves_original_interruption(self):
        self.exercise('cleanup-error')


if __name__ == '__main__':
    unittest.main()
