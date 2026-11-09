"""Prepare the exact Chrome for Testing selection for native consumer tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
LIMIT = 256 * 1024 * 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    selected = json.loads((ROOT / 'toolchain.lock.json').read_text())['browser']
    destination = ROOT / '.cache/testing/chrome' / selected['chrome_for_testing']
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Fetch afresh into a temporary directory; a pre-existing arbitrary binary is
    # never accepted merely because a version-named cache directory exists.
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        temporary = Path(temporary)
        archive = temporary / 'chrome.zip'
        digest = hashlib.sha256()
        size = 0
        with urllib.request.urlopen(selected['url'], timeout=60) as response, archive.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > LIMIT:
                    raise ValueError('Chrome archive exceeds 256 MiB')
                digest.update(chunk)
                output.write(chunk)
        with zipfile.ZipFile(archive) as zipped:
            expanded = 0
            for member in zipped.infolist():
                target = temporary / member.filename
                mode = member.external_attr >> 16
                expanded += member.file_size
                if (not target.resolve().is_relative_to(temporary.resolve()) or
                        not member.filename.startswith('chrome-linux64/') or
                        stat.S_ISLNK(mode) or expanded > 1024 * 1024 * 1024):
                    raise ValueError('Invalid Chrome archive member')
                zipped.extract(member, temporary)
                if not member.is_dir() and mode & 0o111:
                    target.chmod(0o755)
        executable = temporary / 'chrome-linux64/chrome'
        observed = subprocess.check_output([str(executable), '--version'], text=True, timeout=20).strip()
        if selected['chrome_for_testing'] not in observed.split():
            raise ValueError('Chrome executable version differs from selected build')
        identity = {'url': selected['url'], 'version': observed, 'archive_sha256': digest.hexdigest(),
                    'binary_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
                    'archive_bytes': size, 'scope': 'Installed binary identity; browser execution is checked by consumer tests'}
        if destination.exists():
            shutil.rmtree(destination)
        (temporary / 'chrome-linux64').rename(destination)
    executable = destination / 'chrome'
    (args.evidence / 'chrome.json').write_text(json.dumps(identity, indent=2) + '\n')
    if os.environ.get('GITHUB_ENV'):
        with open(os.environ['GITHUB_ENV'], 'a') as output:
            output.write('CHROME_PATH=' + str(executable) + '\n')
    print(executable)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
