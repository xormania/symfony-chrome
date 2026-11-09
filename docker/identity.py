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

serena_facade = Path('/opt/venv/lib/python3.12/site-packages/serena/repl/api/lsp_api.py')
serena_patch = json.loads(Path('/opt/dev/serena-patch.json').read_text())

print(json.dumps({
    'lock': lock,
    'php': version('php', '-v'),
    'composer': version('composer', '--version'),
    'node': version('node', '--version'),
    'chrome_for_testing': version('/opt/chrome-linux64/chrome', '--version'),
    'chromium_base': version('/usr/bin/chromium', '--version'),
    'symfony_cli': version('symfony', 'version', '--no-ansi'),
    'mago': version('mago', '--version'),
    'mago_binary_sha256': sha('/usr/local/bin/mago'),
    'mago_baseline': version('mago-baseline', '--version'),
    'mago_baseline_binary_sha256': sha('/usr/local/bin/mago-baseline'),
    'mago_source_sha': Path('/opt/dev/mago-source.sha').read_text().strip(),
    'mago_patch_sha256': Path('/opt/dev/mago-patch.sha256').read_text().split()[0],
    'mago_cargo_lock_sha256': Path('/opt/dev/mago-cargo-lock.sha256').read_text().split()[0],
    'mago_rust_version': Path('/opt/dev/mago-rust-version.txt').read_text().strip(),
    'python': version('/usr/local/bin/python3', '--version'),
    'uv': version('uv', '--version'),
    'serena': serena_patch,
    'serena_facade_sha256': sha(serena_facade),
    'serena_uv_lock_sha256': sha('/opt/dev/serena/uv.lock'),
    'chrome_binary_sha256': sha('/opt/chrome-linux64/chrome'),
    'chrome_devtools_mcp': json.loads(Path('/usr/local/lib/node_modules/chrome-devtools-mcp/package.json').read_text())['version'],
}, indent=2))
