"""Runtime selection and native PHPUnit identity controls."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('package_execution', ROOT / 'tools/testing/package.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)
CLASS = 'BundleKernelTest'
METHOD = 'testBundlesAreRegisteredAndRealRequestIsHandled'


class NativeInventoryTest(unittest.TestCase):
    def files(self, directory):
        file = Path(directory) / 'BundleKernelTest.php'
        listing = Path(directory) / 'inventory.xml'
        tree = ET.Element('testSuite', xmlns='https://xml.phpunit.de/testSuite')
        case = ET.SubElement(ET.SubElement(tree, 'tests'), 'testClass', name=CLASS, file=str(file))
        ET.SubElement(case, 'testMethod', id=CLASS + '::' + METHOD, name=METHOD)
        ET.ElementTree(tree).write(listing)
        result = Path(directory) / 'junit.xml'
        root = ET.Element('testsuites')
        ET.SubElement(root, 'testcase', {'class': CLASS, 'name': METHOD, 'file': str(file), 'assertions': '5'})
        ET.ElementTree(root).write(result)
        return listing, result, file

    def test_native_inventory_matches_actual_passing_case(self):
        with tempfile.TemporaryDirectory() as directory:
            listing, result, file = self.files(directory)
            self.assertEqual(package.validate_phpunit_result(package.phpunit_inventory(listing, file), result), 5)

    def test_same_count_substitutions_and_nonexecution_are_rejected(self):
        for fault in ['class', 'method', 'file', 'dataset', 'duplicate', 'missing', 'zero', 'skipped']:
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                listing, result, file = self.files(directory)
                inventory = package.phpunit_inventory(listing, file)
                tree = ET.parse(result)
                root = tree.getroot()
                case = root.find('testcase')
                if fault == 'class':
                    case.set('class', 'UnrelatedPassingTest')
                elif fault == 'method':
                    case.set('name', 'testUnrelatedPass')
                elif fault == 'file':
                    case.set('file', str(Path(directory) / 'Unrelated.php'))
                elif fault == 'dataset':
                    case.set('name', METHOD + ' with data set "unselected"')
                elif fault == 'duplicate':
                    root.append(ET.fromstring(ET.tostring(case)))
                elif fault == 'missing':
                    root.remove(case)
                elif fault == 'zero':
                    case.set('assertions', '0')
                else:
                    ET.SubElement(case, 'skipped')
                tree.write(result)
                with self.assertRaises(RuntimeError):
                    package.validate_phpunit_result(inventory, result)

    def test_required_kernel_contract_must_be_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            listing, _, file = self.files(directory)
            tree = ET.parse(listing)
            method = tree.find('.//{*}testMethod')
            method.set('name', 'testUnrelatedPass')
            method.set('id', CLASS + '::testUnrelatedPass')
            tree.write(listing)
            with self.assertRaisesRegex(RuntimeError, 'Required bundle/kernel contract'):
                package.phpunit_inventory(listing, file)

    def test_named_dataset_identity_keeps_quotes_and_delimiters(self):
        with tempfile.TemporaryDirectory() as directory:
            listing, result, file = self.files(directory)
            label = 'quoted "input" with data set marker'
            tree = ET.parse(listing)
            test_class = tree.find('.//{*}testClass')
            ET.SubElement(test_class, 'testMethod', id=CLASS + '::testProvider#' + label, name='testProvider')
            tree.write(listing)
            tree = ET.parse(result)
            ET.SubElement(tree.getroot(), 'testcase', {'class': CLASS, 'name': 'testProvider with data set "' + label + '"', 'file': str(file), 'assertions': '2'})
            tree.write(result)
            self.assertEqual(package.validate_phpunit_result(package.phpunit_inventory(listing, file), result), 7)


class DockerFallbackTest(unittest.TestCase):
    def test_input_view_keeps_candidate_code_and_excludes_private_local_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repo'
            root.mkdir()
            subprocess.run(['git', 'init', '--quiet'], cwd=root, check=True)
            (root / '.gitignore').write_text('private/\nartifacts/\nvendor/\n.env.local\n')
            for name in ['tools/testing/package.py', 'packages/chrome-bundle/composer.json', 'packages/chrome-bundle/.env.local', 'private/sentinel', 'artifacts/sentinel', 'packages/chrome-bundle/vendor/sentinel']:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('controlled input')
            view = package.readonly_checkout(root, Path(directory) / 'view')
            self.assertTrue((view / 'tools/testing/package.py').is_file())
            self.assertTrue((view / 'packages/chrome-bundle/composer.json').is_file())
            self.assertFalse((view / '.git').exists())
            self.assertFalse(any(path.name in {'sentinel', '.env.local'} for path in view.rglob('*')))

    def test_tracked_input_under_replaced_directory_cannot_export_private_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repo'
            root.mkdir()
            subprocess.run(['git', 'init', '--quiet'], cwd=root, check=True)
            source = root / 'packages/chrome-bundle'
            source.mkdir(parents=True)
            (source / 'composer.json').write_text('public input')
            subprocess.run(['git', 'add', 'packages/chrome-bundle/composer.json'], cwd=root, check=True)
            (root / '.gitignore').write_text('packages/chrome-bundle\n')
            (source / 'composer.json').unlink()
            source.rmdir()
            outside = Path(directory) / 'private'
            outside.mkdir()
            (outside / 'composer.json').write_text('controlled private sentinel')
            source.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, 'link|outside'):
                package.readonly_checkout(root, Path(directory) / 'view')

    def test_same_script_uses_read_only_checkout_and_owned_writable_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repo'
            evidence = Path(directory) / 'evidence'
            root.mkdir(); evidence.mkdir()
            (root / 'toolchain.lock.json').write_text(json.dumps({'images': {'base': 'pinned@sha256:base'}}))
            observed = [{'Id': 'sha256:base', 'RootFS': {'Layers': ['parent']}}, {'Id': 'sha256:derived', 'RootFS': {'Layers': ['parent', 'project']}}]
            calls = []
            def native(argv, **kwargs):
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 1 if argv[:3] == ['docker', 'container', 'inspect'] else 0)
            def inspect(argv, **kwargs):
                return b'toolchain.lock.json\0' if argv[0] == 'git' else json.dumps(observed)
            with mock.patch.dict(os.environ, {'DEV_IMAGE': 'prepared:local'}, clear=True), mock.patch.object(package.shutil, 'which', return_value='/usr/bin/docker'), mock.patch.object(package, 'command') as support, mock.patch.object(package.subprocess, 'check_output', side_effect=inspect), mock.patch.object(package.subprocess, 'run', side_effect=native):
                self.assertEqual(package.docker_fallback(root, evidence), 0)
            support.assert_called_once()
            argv = next(row for row in calls if row[:2] == ['docker', 'run'])
            self.assertTrue(any(row.startswith('type=bind,src=') and row.endswith(',dst=/repo,readonly') for row in argv))
            self.assertNotIn(f'type=bind,src={root},dst=/repo,readonly', argv)
            self.assertIn(f'type=bind,src={evidence},dst=/evidence', argv)
            self.assertIn('--native-only', argv)
            self.assertIn('sha256:derived', argv)
            self.assertNotIn('prepared:local', argv)
            self.assertEqual(argv[-4:], ['/repo/tools/testing/package.py', '--native-only', '--evidence', '/evidence'])
            self.assertEqual(json.loads((evidence / 'package-runtime.json').read_text())['actual_image_id'], 'sha256:derived')

    def test_explicit_unavailable_image_never_silently_runs_the_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'toolchain.lock.json').write_text(json.dumps({'images': {'base': 'pinned@sha256:base'}}))
            calls = []
            def native(argv, **kwargs):
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 1)
            with mock.patch.dict(os.environ, {'DEV_IMAGE': 'missing:local'}, clear=True), mock.patch.object(package.shutil, 'which', return_value='/usr/bin/docker'), mock.patch.object(package, 'command'), mock.patch.object(package.subprocess, 'run', side_effect=native):
                with self.assertRaisesRegex(RuntimeError, 'explicitly selected DEV_IMAGE is unavailable'):
                    package.docker_fallback(root, root)
            self.assertFalse(any(row[:2] == ['docker', 'run'] for row in calls))

    def test_failed_support_preflight_never_starts_a_container(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(package.shutil, 'which', return_value='/usr/bin/docker'), mock.patch.object(package, 'command', side_effect=RuntimeError('unsupported parent')), mock.patch.object(package.subprocess, 'run') as native:
            with self.assertRaisesRegex(RuntimeError, 'unsupported parent'):
                package.docker_fallback(Path(directory), Path(directory))
            native.assert_not_called()

    def test_native_only_failure_cannot_recurse_into_docker(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(package.shutil, 'which', return_value=None), mock.patch.object(package, 'docker_fallback') as fallback:
            self.assertEqual(package.main(['--evidence', directory, '--native-only']), 2)
            fallback.assert_not_called()


if __name__ == '__main__':
    unittest.main()
