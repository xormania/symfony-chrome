"""Controls for project selection binding, without reproducing xorder policy logic."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('project_support', ROOT / 'tools/testing/support.py')
support = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(support)


class SupportSelectionContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.digest = 'sha256:' + 'a' * 64
        self.toolchain = {'images': {'base': 'ghcr.io/example/image:v1@' + self.digest},
                          'xorder_support': {'source_rev': 'b' * 40}}
        self.lock = {'schema_version': 1, 'group': 'fixture', 'resources': [
            {'identity': 'ghcr.io/example/image@' + self.digest, 'service': 'php-base',
             'platform': 'linux/amd64', 'line_id': 'example/line', 'version': '1'}]}

    def write(self):
        (self.root / 'toolchain.lock.json').write_text(json.dumps(self.toolchain))
        (self.root / 'xorder-support.lock.json').write_text(json.dumps(self.lock))
        (self.root / 'Dockerfile').write_text('FROM ' + self.toolchain['images']['base'] + '\n')

    def test_healthy_selection_preserves_actual_tagged_digest_reference(self):
        self.write()
        self.assertEqual(support.selected_base(self.root),
                         ('b' * 40, self.toolchain['images']['base'], 'php-base'))

    def test_unrelated_locked_repository_cannot_satisfy_selected_parent(self):
        self.lock['resources'][0]['identity'] = 'ghcr.io/other/image@' + self.digest
        self.write()
        with self.assertRaisesRegex(ValueError, 'does not select'):
            support.selected_base(self.root)

    def test_mutable_source_ref_and_unpinned_parent_are_rejected(self):
        for revision, image in [('master', self.toolchain['images']['base']),
                                ('b' * 40, 'ghcr.io/example/image:latest')]:
            with self.subTest(revision=revision, image=image):
                self.toolchain['xorder_support']['source_rev'] = revision
                self.toolchain['images']['base'] = image
                self.write()
                with self.assertRaises(ValueError):
                    support.selected_base(self.root)

    def test_dockerfile_parent_must_match_the_selected_support_resource(self):
        self.write()
        (self.root / 'Dockerfile').write_text('FROM ghcr.io/other/image:v1@' + self.digest + '\n')
        with self.assertRaisesRegex(ValueError, 'Dockerfile FROM'):
            support.selected_base(self.root)

    def test_modified_checker_is_rejected_before_execution(self):
        checkout = self.root / 'checker'
        checkout.mkdir()
        evidence = self.root / 'evidence'
        evidence.mkdir()
        subprocess.run(['git', 'init', '--quiet', str(checkout)], check=True)
        subprocess.run(['git', '-C', str(checkout), 'config', 'user.name', 'xor'], check=True)
        subprocess.run(['git', '-C', str(checkout), 'config', 'user.email',
                        '127287135+xormania@users.noreply.github.com'], check=True)
        script = checkout / 'scripts/xorder/downstream.py'
        script.parent.mkdir(parents=True)
        script.write_text('print("fixture")\n')
        subprocess.run(['git', '-C', str(checkout), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(checkout), 'commit', '--quiet', '-m', 'test: add checker fixture'], check=True)
        revision = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
        support.verify_checkout(checkout, revision, evidence)
        script.write_text('print("changed")\n')
        with self.assertRaisesRegex(ValueError, 'modified or untracked'):
            support.verify_checkout(checkout, revision, evidence)

    def test_failed_fetch_does_not_publish_a_partial_cached_checkout(self):
        evidence = self.root / 'evidence'
        evidence.mkdir()
        def fail_fetch(command, directory, name, **kwargs):
            return (1 if name == 'checker-fetch' else 0), ''
        with mock.patch.object(support, 'native', side_effect=fail_fetch):
            with self.assertRaisesRegex(RuntimeError, 'checker-fetch failed'):
                support.acquire_checker(self.root, 'b' * 40, evidence)
        self.assertFalse((self.root / 'workspaces/xorder-checker' / ('b' * 40)).exists())
        self.assertEqual(list((self.root / 'workspaces/xorder-checker').iterdir()), [])

    def test_successful_command_does_not_leave_background_children(self):
        evidence = self.root / 'evidence'
        evidence.mkdir()
        code = ('import subprocess,sys; p=subprocess.Popen([sys.executable,"-c",'
                '"import time; time.sleep(60)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL);'
                'print(p.pid,flush=True)')
        result, output = support.native(['python3', '-c', code], evidence, 'background', timeout=5)
        self.assertEqual(result, 0)
        pid = int(output.strip())
        try:
            status = Path(f'/proc/{pid}/stat')
            deadline = time.monotonic() + 2
            while status.exists() and status.read_text().split()[2] != 'Z' and time.monotonic() < deadline:
                time.sleep(0.01)
            if status.exists():
                self.assertEqual(status.read_text().split()[2], 'Z', 'Background child remains running')
        finally:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


if __name__ == '__main__':
    unittest.main()
