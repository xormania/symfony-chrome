#!/usr/bin/env python3
"""Install candidate package archives into pinned UXor and run its native Live tests."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PIN = ROOT / 'tests/consumers/uxor.json'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def web_server_command(port: int) -> str:
    """Route application URLs even when their first segment is a public directory."""
    return shlex.join(['php', '-S', f'127.0.0.1:{port}', '-t', 'demo/public',
                       str(ROOT / 'tests/consumers/http-router.php')])


def native_results(report: dict, expected: list[dict], checkout: Path) -> list[dict]:
    """Require each selected native test identity once, with an executed assertion result."""
    found = []

    def walk(suites):
        for suite in suites:
            for spec in suite.get('specs', []):
                for test in spec.get('tests', []):
                    found.append((spec.get('file', suite.get('file', '')), spec.get('title'), test))
            walk(suite.get('suites', []))

    walk(report.get('suites', []))
    if report.get('errors'):
        raise ValueError('Playwright reported a setup/global error')
    expected_pairs = {(row['file'], row['title']) for row in expected}
    source_root = checkout.resolve()
    test_root = source_root / 'tests/e2e'
    recorded_root = Path(report.get('config', {}).get('rootDir', '')).resolve()
    if recorded_root != test_root:
        raise ValueError('Native report belongs to another consumer test root')
    pairs = []
    for file, title, _ in found:
        path = Path(file)
        if not path.is_absolute():
            path = source_root / path if file.startswith('tests/') else test_root / path
        pairs.append((path.resolve().relative_to(source_root).as_posix(), title))
    if len(pairs) != len(expected_pairs) or set(pairs) != expected_pairs:
        raise ValueError(f'Native test inventory mismatch: expected {sorted(expected_pairs)!r}, received {pairs!r}')
    checks = []
    for file, title, test in found:
        attempts = test.get('results', [])
        if test.get('expectedStatus', 'passed') != 'passed' or len(attempts) != 1:
            raise ValueError('Native consumer tests must execute once without expected failures/retries')
        result = attempts[0]
        if result.get('status') != 'passed' or result.get('errors') or test.get('status') not in (None, 'expected'):
            raise ValueError(f'Native consumer test failed or did not execute: {title}')
        checks.append({'id': 'consumer.uxor.' + ('modal' if 'modal' in file else 'validation'),
                       'outcome': 'passed', 'assertions': 1, 'detail': title})
    return checks


def add_archives(original: dict, archives: list[dict]) -> dict:
    """Add package artifacts while preserving every existing consumer constraint."""
    result = json.loads(json.dumps(original))
    repositories = result.setdefault('repositories', [])
    if not isinstance(repositories, list):
        raise ValueError('Expected an ordered Composer repository list')
    for archive in archives:
        name = archive['name']
        target = 'require-dev' if name.endswith('/chrome-devtools-bundle') else 'require'
        if name in result.get('require', {}) or name in result.get('require-dev', {}):
            raise ValueError('Pinned consumer already declares the candidate package: ' + name)
        path = Path(archive['path']).resolve()
        if not path.is_file() or sha(path) != archive['sha256']:
            raise ValueError('Candidate archive identity mismatch: ' + name)
        package = json.loads(json.dumps(archive['manifest']))
        package['version'] = archive['version']
        package['dist'] = {'type': 'zip', 'url': path.as_uri()}
        package.pop('source', None)
        repositories.insert(0, {'type': 'package', 'package': package})
        result.setdefault(target, {})[name] = archive['version']
    return result


def run(evidence: Path) -> dict:
    from package import build_archives

    evidence.mkdir(parents=True, exist_ok=True)
    config = json.loads(PIN.read_text())
    if not re.fullmatch('[0-9a-f]{40}', config['revision']):
        raise ValueError('Consumer revision must be an exact commit')
    workspace_parent = ROOT / 'workspaces'
    workspace_parent.mkdir(exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix='consumer-', dir=workspace_parent))
    checkout = workspace / 'uxor'
    checks = []
    phases = []
    env = {**os.environ, 'APP_ENV': 'dev', 'APP_DEBUG': '1', 'CI': '1'}

    def execute(name, argv, cwd=ROOT, timeout=600):
        from runner import capture

        directory = evidence / name
        directory.mkdir()
        code, timed_out, truncated = capture(argv, directory, timeout, cwd=cwd, env=env)
        phases.append({'phase': name, 'native_exit': code, 'timed_out': timed_out,
                       'truncated': truncated, 'log': f'{name}/native.log'})
        if code or timed_out or truncated:
            raise RuntimeError(f'{name} failed: exit={code}, timeout={timed_out}, truncated={truncated}; inspect {directory}')

    try:
        execute('http-routing-regression', [sys.executable, str(ROOT / 'tests/consumers/test_http_router.py')])
        execute('checkout-init', ['git', 'init', str(checkout)])
        execute('checkout-remote', ['git', 'remote', 'add', 'origin', config['repository']], checkout)
        execute('checkout-fetch', ['git', 'fetch', '--depth=1', 'origin', config['revision']], checkout)
        execute('checkout', ['git', 'checkout', '--detach', config['revision']], checkout)
        actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip()
        if actual != config['revision']:
            raise RuntimeError('Consumer checkout identity mismatch')
        archives = build_archives(ROOT, evidence / 'archives')
        app = checkout / 'demo'
        original_path = app / 'composer.json'
        original = json.loads(original_path.read_text())
        original_lock_hash = sha(app / 'composer.lock')
        original_path.write_text(json.dumps(add_archives(original, archives), indent=4) + '\n')
        # Native consumer requirements, including Mate, remain byte-for-byte equivalent values.
        bundle_file = app / 'config/bundles.php'
        bundles = bundle_file.read_text()
        if bundles.count('];') != 1:
            raise ValueError('Unknown pinned consumer bundle configuration shape')
        bundle_file.write_text(bundles.replace('];',
            "    Xormania\\ChromeBundle\\ChromeBundle::class => ['all' => true],\n"
            "    Xormania\\ChromeDevtoolsBundle\\ChromeDevtoolsBundle::class => ['dev' => true, 'test' => true],\n];"))
        execute('sync-recipes', ['php', 'tools/sync-demo'], checkout)
        execute('candidate-install', ['composer', 'update', 'xormania/chrome-bundle',
            'xormania/chrome-devtools-bundle', '--with-dependencies', '--no-scripts', '--no-interaction', '--prefer-dist'], app)
        execute('composer-validate', ['composer', 'validate', '--strict', '--no-check-publish'], app)
        execute('consumer-setup', ['composer', 'run-script', 'post-install-cmd', '--no-interaction'], app)
        execute('bundle-registration', ['php', str(ROOT / 'tests/consumers/runtime-check.php')], app)
        checks.append({'id': 'consumer.uxor.install', 'outcome': 'passed', 'assertions': 3,
                       'detail': 'Candidate archives installed; original constraints retained; both bundles booted'})
        installed = json.loads((app / 'composer.lock').read_text())
        identities = {'schema': 1, 'consumer_revision': actual, 'source_revision': subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'source_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
            'original_lock_sha256': original_lock_hash, 'resolved_lock_sha256': sha(app / 'composer.lock'),
            'original_constraints': {'require': original.get('require', {}), 'require-dev': original.get('require-dev', {})},
            'installed': {row['name']: row['version'] for row in installed['packages'] + installed.get('packages-dev', [])},
            'archives': [{key: row[key] for key in ('name', 'version', 'sha256')} for row in archives],
            'coverage': config['coverage']}
        (evidence / 'identity.json').write_text(json.dumps(identities, indent=2) + '\n')
        shutil.copy2(app / 'composer.lock', evidence / 'resolved-composer.lock')
        execute('npm-install', ['npm', 'ci', '--no-fund', '--no-audit'], checkout)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        browser = shutil.which(os.environ.get('CHROME_PATH', 'chrome'))
        if not browser:
            raise RuntimeError('Selected Chrome executable is unavailable; consumer browser test did not execute')
        identities['runtime'] = {name: subprocess.check_output(argv, text=True).splitlines()[0]
            for name, argv in [('php', ['php', '--version']), ('node', ['node', '--version']),
                               ('chrome', [browser, '--version'])]}
        expected_browser = json.loads((ROOT / 'toolchain.lock.json').read_text())['browser']['chrome_for_testing']
        if expected_browser not in identities['runtime']['chrome'].split():
            raise RuntimeError('Actual consumer Chrome differs from the selected locked build')
        (evidence / 'identity.json').write_text(json.dumps(identities, indent=2) + '\n')
        report_path = evidence / 'playwright.json'
        cfg = checkout / 'symfony-chrome.config.mjs'
        cfg.write_text("import { defineConfig } from '@playwright/test';\nexport default defineConfig(" + json.dumps({
            'globalSetup': './tools/prepare-tests.mjs', 'testDir': './tests/e2e',
            'testMatch': [row['file'].rsplit('/', 1)[1] for row in config['tests']],
            'forbidOnly': True, 'retries': 0, 'workers': 1,
            'reporter': [['list'], ['json', {'outputFile': str(report_path)}]],
            'use': {'baseURL': f'http://127.0.0.1:{port}', 'browserName': 'chromium',
                    'launchOptions': {'executablePath': browser}, 'trace': 'retain-on-failure'},
            'webServer': {'command': web_server_command(port),
                          'url': f'http://127.0.0.1:{port}/lab/live-modal', 'timeout': 120000,
                          'reuseExistingServer': False},
            'outputDir': str(evidence / 'playwright-output')}, indent=2) + ');\n')
        # Playwright starts webServer before globalSetup. UXor needs built CSS to render the readiness page.
        execute('prepare-browser-assets', ['node', 'tools/prepare-tests.mjs'], checkout)
        execute('browser', ['npx', '--no-install', 'playwright', 'test', '--config', str(cfg)], checkout, 600)
        checks.extend(native_results(json.loads(report_path.read_text()), config['tests'], checkout))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        checks.append({'id': 'consumer.uxor.execution', 'outcome': 'error', 'assertions': 0, 'detail': str(exc)})
    finally:
        try:
            shutil.rmtree(workspace)
            phases.append({'phase': 'cleanup', 'outcome': 'passed'})
        except OSError as exc:
            checks.append({'id': 'consumer.uxor.cleanup', 'outcome': 'error', 'assertions': 0, 'detail': str(exc)})
    return {'schema': 1, 'checks': checks, 'phases': phases,
            'coverage': config['coverage'], 'consumer_revision': config['revision']}


def main():
    def interrupted(signum, frame):
        raise InterruptedError('Consumer execution interrupted by signal ' + str(signum))

    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    args = parser.parse_args()
    args.evidence = args.evidence.resolve()
    result = run(args.evidence)
    (args.evidence / 'checks.json').write_text(json.dumps(result, indent=2) + '\n')
    return 0 if result['checks'] and all(row['outcome'] == 'passed' for row in result['checks']) else 1


if __name__ == '__main__':
    sys.exit(main())
