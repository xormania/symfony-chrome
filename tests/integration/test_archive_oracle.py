import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from archive_oracle import snapshot_profile, verify_archive


class ArchiveOracleContract(unittest.TestCase):
    def test_retained_profile_matches_original_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); app = root / 'app'; archive = root / 'archive'
            relative = 'var/cache/dev/profiler/ef/cd/abcdef'
            source = app / relative; source.parent.mkdir(parents=True); source.write_bytes(b'exact request profile')
            before = snapshot_profile(app, 'abcdef')
            retained = archive / relative; retained.parent.mkdir(parents=True); retained.write_bytes(source.read_bytes())
            manifest = {relative: {'sha256': hashlib.sha256(retained.read_bytes()).hexdigest()}}
            self.assertEqual(verify_archive(before, manifest, archive)['profile_files'], 1)

    def test_tampered_bytes_and_matching_new_manifest_do_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); app = root / 'app'; archive = root / 'archive'
            relative = 'var/cache/dev/profiler/ef/cd/abcdef'
            source = app / relative; source.parent.mkdir(parents=True); source.write_bytes(b'exact original request profile')
            before = snapshot_profile(app, 'abcdef')
            retained = archive / relative; retained.parent.mkdir(parents=True); retained.write_bytes(b'another profile with the same filename')
            manifest = {relative: {'sha256': hashlib.sha256(retained.read_bytes()).hexdigest()}}
            with self.assertRaisesRegex(AssertionError, 'independent pre-refresh'):
                verify_archive(before, manifest, archive)


if __name__ == '__main__':
    unittest.main()
