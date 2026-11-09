"""Non-secret build identity, captured inside the image at build time."""
import hashlib
import json
import subprocess
from pathlib import Path


def version(*args):
    return subprocess.check_output(args, text=True).splitlines()[0]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


lock = json.loads(Path('/opt/dev/toolchain.lock.json').read_text())
chrome_version = Path('/opt/chrome-version').read_text().strip()
if chrome_version != lock['browser']['chrome_for_testing']:
    raise RuntimeError(f'Installed Chrome {chrome_version} differs from toolchain.lock.json')

print(json.dumps({
    'lock': lock,
    'php': version('php', '-v'),
    'composer': version('composer', '--version'),
    'node': version('node', '--version'),
    'chrome_for_testing': version('/opt/chrome-linux64/chrome', '--version'),
    'chromium_base': version('/usr/bin/chromium', '--version'),
    'symfony_cli': version('symfony', 'version', '--no-ansi'),
    'chrome_binary_sha256': sha('/opt/chrome-linux64/chrome'),
    'chrome_devtools_mcp': json.loads(Path('/usr/local/lib/node_modules/chrome-devtools-mcp/package.json').read_text())['version'],
}, indent=2))
