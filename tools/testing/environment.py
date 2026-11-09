#!/usr/bin/env python3
"""Verify the actual Docker development environment and native Mago quality path."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import signal
import tarfile
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]


def prepare_mago(destination):
    """Install the hash-pinned release for native quality checks, never as patched LSP."""
    lock = json.loads((ROOT / 'toolchain.lock.json').read_text())['mago']
    data = urllib.request.urlopen(lock['url'], timeout=60).read(64 * 1024 * 1024 + 1)
    if len(data) > 64 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != lock['sha256']:
        raise RuntimeError('Mago release exceeds limit or fails the locked SHA-256')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        candidates = [m for m in archive.getmembers() if m.isfile() and Path(m.name).name == 'mago']
        if len(candidates) != 1:
            raise RuntimeError('Release archive must contain exactly one mago executable')
        member = candidates[0]
        if member.size > 128 * 1024 * 1024:
            raise RuntimeError('Mago executable exceeds size bound')
        payload = archive.extractfile(member).read()
    destination.mkdir(parents=True, exist_ok=True)
    executable = destination / 'mago-baseline'
    executable.write_bytes(payload)
    executable.chmod(0o755)
    return executable


def main(argv=None):
    def interrupted(signum, frame):
        raise InterruptedError('Acceptance worker interrupted by signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--prepare-tools', action='store_true')
    args = parser.parse_args(argv)
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    if args.prepare_tools:
        executable = prepare_mago(ROOT / '.cache/testing/bin')
        if os.environ.get('GITHUB_PATH'):
            with open(os.environ['GITHUB_PATH'], 'a') as stream:
                stream.write(str(executable.parent) + '\n')
        print(executable)
        return 0
    rows = []
    run_id = 'ci-' + uuid.uuid4().hex[:12]
    sys.path.insert(0, str(ROOT / 'bin'))
    from devlib import compose, container_id, environment, exec_command, load, stop
    env = os.environ.copy()
    try:
        if not shutil.which('docker'):
            raise RuntimeError('Docker is required for the real environment suite')
        command = [str(ROOT / 'bin/dev'), 'up', '--run', run_id]
        if os.environ.get('DEV_SKIP_BUILD') == '1':
            command.append('--no-build')
        with (evidence / 'up.log').open('w') as output:
            subprocess.run(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=2400, check=True)
        data = load(run_id)
        def execute(*argv, name, expected_exit=0):
            result = subprocess.run(exec_command(data, *argv), env=environment(data), capture_output=True, text=True, timeout=300)
            (evidence / name).write_text(result.stdout + result.stderr)
            if result.returncode != expected_exit:
                raise RuntimeError(f'{argv!r} exited {result.returncode}: {(result.stdout + result.stderr)[-4000:]}')
            return result.stdout
        identity = json.loads(execute('cat', '/opt/dev/image-identity.json', name='image-identity.json'))
        expected = json.loads((ROOT / 'toolchain.lock.json').read_text())
        if identity['lock'] != expected:
            raise RuntimeError('Running image toolchain selection differs from the checkout')
        actual_container = container_id(data)
        actual_image = subprocess.check_output(['docker', 'inspect', '--format', '{{.Image}}', actual_container], text=True).strip()
        selected_image = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', data['image']], text=True).strip()
        if actual_image != selected_image:
            raise RuntimeError('Actual container image differs from the selected built image')
        (evidence / 'runtime.json').write_text(json.dumps({'container': actual_container, 'actual_image': actual_image, 'selected_image': selected_image}, indent=2) + '\n')
        rows.append({'id': 'environment.identity', 'outcome': 'passed', 'assertions': 2, 'detail': 'Observed running container/image and in-image selection match the checkout.'})
        response = json.loads(execute('curl', '-fsS', 'http://127.0.0.1:8000/_dev/ready', name='readiness.json'))
        if response != {'ready': True, 'chrome_bundle': True, 'chrome_devtools_bundle': True, 'profiler': True}:
            raise RuntimeError(f'Unexpected fixture response {response}')
        execute('php', 'bin/console', 'lint:container', name='container.log')
        rows.append({'id': 'environment.fixture', 'outcome': 'passed', 'assertions': 5, 'detail': 'Real response and compiled Symfony container verified.'})
        execute('composer', 'validate', '--strict', '--no-check-publish', name='composer-validate.log')
        execute('composer', 'check-platform-reqs', name='platform.log')
        rows.append({'id': 'environment.platform', 'outcome': 'passed', 'assertions': 2, 'detail': 'Locked dependencies and actual PHP extension/platform requirements pass.'})
        for name, arguments in [('analyze', ['analyze']), ('lint', ['lint']), ('guard', ['guard', '--perimeter']), ('format', ['format', '--check'])]:
            execute('mago-baseline', *arguments, name=f'mago-{name}.log')
        # Native substitution proves the symlinked runtime package is part of the guard's
        # actual source set without editing the checked-out package mounted at /packages.
        original = ROOT / 'packages/chrome-bundle/src/ChromeBundle.php'
        marker = '    public function getPath()'
        if marker not in original.read_text():
            raise RuntimeError('Architecture control target changed; update the focused substitution')
        fault = Path(data['app']) / '.ci-guard-control.php'
        fault.write_text(original.read_text().replace(marker, '    public function forbidden(\\Symfony\\Bundle\\WebProfilerBundle\\WebProfilerBundle $profiler): void {}\n\n' + marker))
        report = json.loads(execute('mago-baseline', 'guard', '--perimeter', '--substitute',
            '/workspace/vendor/xormania/chrome-bundle/src/ChromeBundle.php=/workspace/.ci-guard-control.php',
            '--reporting-format', 'json', name='mago-dependency-control.json', expected_exit=1))
        if not any(issue.get('code') == 'disallowed-parameter-type' and 'WebProfilerBundle' in issue.get('message', '') for issue in report.get('issues', [])):
            raise RuntimeError('Guard did not identify the deliberately forbidden runtime dependency')
        rows.append({'id': 'environment.mago', 'outcome': 'passed', 'assertions': 5, 'detail': 'Native quality checks pass; actual runtime package source coverage is proved by a forbidden-dependency fault detected through native substitution.'})
        result = 0
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        rows.append({'id': 'environment.execution', 'outcome': 'error', 'assertions': 0, 'detail': str(exc)})
        print(str(exc), file=sys.stderr)
        result = 2
    finally:
        marker = ROOT / 'workspaces' / run_id / 'run.json'
        if marker.is_file():
            try:
                data = load(run_id)
                # Keep compact native setup/build diagnostics, never vendor/workspaces.
                for name in ['setup.log', 'build.log']:
                    source = Path(data['evidence']) / name
                    if source.is_file():
                        shutil.copy2(source, evidence / name)
                try:
                    with (evidence / 'container.log.txt').open('w') as output:
                        subprocess.run(compose(data, 'logs', '--no-color', 'php'), env=environment(data), stdout=output, stderr=subprocess.STDOUT, timeout=5, check=False)
                finally:
                    # Diagnostic collection must not suppress owned-resource cleanup.
                    stop(data, purge=True)
            except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
                rows.append({'id': 'environment.cleanup', 'outcome': 'error', 'assertions': 0, 'detail': str(exc)})
                result = 2
    (evidence / 'checks.json').write_text(json.dumps({'schema': 1, 'checks': rows}, indent=2) + '\n')
    return result


if __name__ == '__main__':
    sys.exit(main())
