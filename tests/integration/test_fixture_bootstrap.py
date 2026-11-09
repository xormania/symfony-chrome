"""The first bootstrap must see actual installed CI routes and service bindings."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(os.environ.get('TEST_SUBJECT_ROOT', Path(__file__).resolve().parents[2]))
spec = importlib.util.spec_from_file_location('fixture_bootstrap_subject', ROOT / 'tests/integration/contracts.py')
contracts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contracts)


class FixtureBootstrapContract(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.app = self.root / 'app'
        (self.app / 'src/Controller').mkdir(parents=True)
        (self.app / 'config').mkdir()
        self.original_services = 'services:\n    _defaults:\n        autowire: true\n        autoconfigure: true\n'
        (self.app / 'config/services.yaml').write_text(self.original_services)
        evidence = self.root / 'evidence'
        evidence.mkdir()
        self.data = {'run_id': 'controlled-first-bootstrap', 'app': str(self.app), 'evidence': str(evidence)}
        self.stopped = []
        self.observed = []

    def first_runtime_view(self, data, *, build):
        self.assertEqual(self.data, data)
        self.assertFalse(build)
        controller = self.app / 'src/Controller/ContractController.php'
        self.assertTrue(controller.is_file(), 'first runtime bootstrap has no CI controller/routes')
        routes = set(re.findall(r"#\[Route\('([^']+)'", controller.read_text()))
        self.assertTrue({'/_ci/browser', '/_ci/script.js', '/_ci/icon.svg', '/_ci/observe'} <= routes,
                        'first runtime route input is incomplete')
        services = (self.app / 'config/services.yaml').read_text()
        self.assertTrue(services.startswith(self.original_services), 'application-owned service configuration was replaced')
        self.assertEqual(['services'], re.findall(r'^([A-Za-z_][\w.-]*):', services, re.MULTILINE))
        declarations = set(re.findall(r'^    (App\\Ci\\[A-Za-z]+):$', services, re.MULTILINE))
        self.assertEqual({'App\\Ci\\BindingProbe', 'App\\Ci\\LoopbackTransport', 'App\\Ci\\ContractTransport'}, declarations)
        alias = re.search(r'^    App\\Ci\\ContractTransport:\n((?:        .*\n)+)', services, re.MULTILINE)
        self.assertIsNotNone(alias)
        self.assertIn('        alias: App\\Ci\\LoopbackTransport\n', alias.group(1))
        self.assertIn('        public: true\n', alias.group(1))
        for filename, declaration in [('BindingProbe.php', 'class BindingProbe'),
                                      ('LoopbackTransport.php', 'class LoopbackTransport'),
                                      ('ContractTransport.php', 'interface ContractTransport')]:
            path = self.app / 'src/Ci' / filename
            self.assertTrue(path.is_file(), f'first runtime has no {filename}')
            self.assertIn(declaration, path.read_text())
        selected = [controller, self.app / 'config/services.yaml', *(self.app / 'src/Ci').glob('*.php')]
        self.observed.append({str(path.relative_to(self.app)): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in selected})

    def stop(self, data, *, purge):
        self.stopped.append((dict(data), purge))

    def context(self, start):
        return patch.multiple(contracts, prepare=lambda *args, **kwargs: self.data,
                              start=start, stop=self.stop,
                              execute=lambda *args, **kwargs: self.fail(
                                  'fixture installation executed a container command before startup bootstrap'))

    def test_first_bootstrap_sees_complete_fixture_without_post_start_mutation(self):
        with self.context(self.first_runtime_view):
            with contracts.workspace() as data:
                self.assertEqual(self.data, data)
                self.assertEqual(1, len(self.observed))
                after = {name: hashlib.sha256((self.app / name).read_bytes()).hexdigest()
                         for name in self.observed[0]}
                self.assertEqual(self.observed[0], after, 'route/service inputs changed after bootstrap')
        self.assertEqual([(self.data, True)], self.stopped)
        cleanup = json.loads((Path(self.data['evidence']) / 'contract-cleanup.json').read_text())
        self.assertEqual({'run_id': self.data['run_id'], 'outcome': 'passed'}, cleanup)

    def test_failed_bootstrap_keeps_primary_error_and_cleans_owned_workspace(self):
        def fail_bootstrap(data, *, build):
            self.first_runtime_view(data, build=build)
            raise RuntimeError('controlled startup failure after reading complete fixture')
        with self.context(fail_bootstrap), self.assertRaisesRegex(RuntimeError, 'controlled startup failure'):
            with contracts.workspace():
                self.fail('failed bootstrap yielded a running workspace')
        self.assertEqual(1, len(self.observed))
        self.assertEqual([(self.data, True)], self.stopped)
        cleanup = json.loads((Path(self.data['evidence']) / 'contract-cleanup.json').read_text())
        self.assertEqual('passed', cleanup['outcome'])


if __name__ == '__main__':
    unittest.main()
