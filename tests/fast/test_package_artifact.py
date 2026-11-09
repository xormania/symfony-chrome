"""Archive metadata controls: old repository definitions cannot bless new package bytes."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('package_checks', ROOT / 'tools/testing/package.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class ArtifactMetadataTest(unittest.TestCase):
    def test_current_archive_matches_consumer_definition_and_genuine_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            archives = package.build_archives(ROOT, Path(directory) / 'archives')
            package.verify_consumer_metadata(ROOT / 'fixtures/consumer', archives)
            self.assertEqual(len(archives), 2)

    def test_archive_dependency_change_is_rejected_with_old_consumer_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            archives = package.build_archives(ROOT, Path(directory) / 'archives')
            archive = Path(archives[0]['path'])
            with zipfile.ZipFile(archive) as zipped:
                files = {name: zipped.read(name) for name in zipped.namelist()}
            manifest = json.loads(files['composer.json'])
            manifest['require']['controlled/unavailable-package'] = '999.0.0'
            files['composer.json'] = json.dumps(manifest).encode()
            with zipfile.ZipFile(archive, 'w') as zipped:
                for name, contents in files.items():
                    zipped.writestr(name, contents)
            with self.assertRaisesRegex(RuntimeError, 'Stale consumer package metadata'):
                package.verify_consumer_metadata(ROOT / 'fixtures/consumer', archives)


if __name__ == '__main__':
    unittest.main()
