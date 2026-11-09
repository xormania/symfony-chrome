"""Compare archived exact-token profile bytes with a pre-refresh observation."""
import hashlib
from pathlib import Path


def snapshot_profile(app, token):
    app = Path(app)
    profiles = app / 'var/cache/dev/profiler'
    expected = {}
    for path in profiles.rglob(token):
        assert path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(profiles.resolve()), 'Exact profile is not a contained file'
        expected[str(path.relative_to(app))] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert expected, 'Exact token profile bytes absent before preparation'
    return expected


def verify_archive(expected, manifest, archive_root):
    assert expected, 'No independent pre-refresh profile observation'
    archive_root = Path(archive_root).resolve()
    for name, original_hash in expected.items():
        assert name in manifest, 'Exact pre-refresh profile missing from archive manifest'
        path = archive_root / name
        assert path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(archive_root), 'Archived profile absent or escaped'
        retained_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        assert retained_hash == original_hash, 'Archived bytes differ from independent pre-refresh profile observation'
        assert manifest[name]['sha256'] == original_hash, 'Archive manifest differs from independent pre-refresh observation'
    return {'profile_files': len(expected), 'original_sha256': expected}
