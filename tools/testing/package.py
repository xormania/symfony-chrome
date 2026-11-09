#!/usr/bin/env python3
"""Build distributions and verify independent Symfony consumers through native tools."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = {'chrome-bundle': 'src/ChromeBundle.php', 'chrome-devtools-bundle': 'src/ChromeDevtoolsBundle.php'}


def readonly_checkout(root, destination):
    """Export current test inputs without ignored dependencies, private state or Git metadata."""
    selected = ['fixtures/app', 'fixtures/consumer', 'packages', 'tests/consumers', 'tools/testing/package.py', 'LICENSE', 'toolchain.lock.json']
    names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard', '--', *selected], cwd=root).split(b'\0')
    for value in filter(None, names):
        relative = Path(os.fsdecode(value))
        if relative.is_absolute() or '..' in relative.parts or not any(relative == Path(name) or Path(name) in relative.parents for name in selected):
            raise RuntimeError('Invalid package runtime input path')
        if any(part in {'vendor', 'var', 'node_modules', '__pycache__'} for part in relative.parts) or relative.name == '.env.local' or relative.name.endswith('.local.php') or relative.name.endswith('.local'):
            continue
        source = root / relative
        if (not source.resolve().is_relative_to(root.resolve()) or
                any(root.joinpath(*relative.parts[:count]).is_symlink() for count in range(1, len(relative.parts) + 1))):
            raise RuntimeError(f'Package runtime input must not link outside the input view: {relative}')
        if source.is_file():
            target = destination / relative
            if not target.resolve().is_relative_to(destination.resolve()):
                raise RuntimeError('Package runtime output path escapes the input view')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return destination


def docker_fallback(root, evidence):
    """Run this identical package entry point using the supported PHP parent."""
    if not shutil.which('docker'):
        raise RuntimeError('Package tests require PHP 8.4 and Composer, or Docker for the pinned PHP runtime')
    support = evidence / 'support'
    command([sys.executable, str(root / 'tools/testing/support.py'), '--evidence', str(support)], root, evidence / 'support.log', timeout=900)
    base = json.loads((root / 'toolchain.lock.json').read_text())['images']['base']
    image = base
    requested = os.environ.get('DEV_IMAGE')
    if requested:
        if subprocess.run(['docker', 'image', 'inspect', requested], capture_output=True, check=False).returncode != 0:
            raise RuntimeError('The explicitly selected DEV_IMAGE is unavailable; prepare that image before acceptance')
        image = requested
    observed = json.loads(subprocess.check_output(['docker', 'image', 'inspect', base, image], text=True))
    base_info, selected = observed[0], observed[-1]
    layers = base_info['RootFS']['Layers']
    if selected['RootFS']['Layers'][:len(layers)] != layers:
        raise RuntimeError('The selected prepared DEV_IMAGE does not derive from the validated parent filesystem')
    (evidence / 'package-runtime.json').write_text(json.dumps({'mode': 'docker', 'selected_image': image, 'actual_image_id': selected['Id'], 'released_parent': base, 'actual_parent_id': base_info['Id']}, indent=2) + '\n')
    name = 'symfony-chrome-package-' + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix='symfony-chrome-inputs-') as temporary:
        checkout = readonly_checkout(root, Path(temporary))
        argv = ['docker', 'run', '--rm', '--init', '--name', name,
                '--mount', f'type=bind,src={checkout},dst=/repo,readonly',
                '--mount', f'type=bind,src={evidence},dst=/evidence',
                '--tmpfs', '/tmp:rw,mode=1777', '--tmpfs', '/home/dev:rw,mode=1777',
                '-e', f'PUID={os.getuid()}', '-e', f'PGID={os.getgid()}',
                '-e', 'HOME=/home/dev', '-e', 'COMPOSER_HOME=/home/dev/.composer',
                '-w', '/repo', selected['Id'], 'python3', '/repo/tools/testing/package.py',
                '--native-only', '--evidence', '/evidence']
        def interrupted(signum, frame):
            raise InterruptedError('Package container execution interrupted')
        previous_handler = signal.signal(signal.SIGTERM, interrupted)
        try:
            return subprocess.run(argv, check=False, timeout=1200).returncode
        finally:
            signal.signal(signal.SIGTERM, previous_handler)
            if subprocess.run(['docker', 'container', 'inspect', name], capture_output=True, check=False, timeout=20).returncode == 0:
                command(['docker', 'rm', '--force', name], root, evidence / 'container-cleanup.log', timeout=20)


def phpunit_inventory(path, required_file):
    """Read native discovery before execution; keep dataset IDs rather than counts."""
    tree = ET.parse(path)
    if tree.findall('.//{*}phpt'):
        raise RuntimeError('PHPT inventory requires an explicit result adapter')
    selected = set()
    for test_class in tree.findall('.//{*}testClass'):
        class_name = test_class.attrib['name']
        file = str(Path(test_class.attrib['file']).resolve())
        for method in test_class.findall('{*}testMethod'):
            key = (class_name, method.attrib['id'], file)
            prefix = class_name + '::' + method.attrib['name']
            if key in selected or not (method.attrib['id'] == prefix or method.attrib['id'].startswith(prefix + '#')):
                raise RuntimeError('Duplicate or inconsistent PHPUnit discovery identity')
            selected.add(key)
    required = ('BundleKernelTest', 'BundleKernelTest::testBundlesAreRegisteredAndRealRequestIsHandled', str(required_file.resolve()))
    if required not in selected:
        raise RuntimeError('Required bundle/kernel contract is absent from PHPUnit selection')
    return selected


def validate_phpunit_result(inventory, path):
    observed = set()
    assertions = 0
    for case in ET.parse(path).findall('.//testcase'):
        class_name = case.attrib.get('class', case.attrib.get('classname', ''))
        if 'class' in case.attrib and 'classname' in case.attrib and case.attrib['class'] != case.attrib['classname']:
            raise RuntimeError('PHPUnit class and classname disagree')
        name = case.attrib.get('name', '')
        method, separator, encoded = name.partition(' with data set ')
        if separator:
            if encoded.startswith('#') and re.fullmatch(r'-?\d+', encoded[1:]):
                dataset = encoded[1:]
            elif len(encoded) >= 2 and encoded.startswith('"') and encoded.endswith('"'):
                dataset = encoded[1:-1]
            else:
                raise RuntimeError('Unrecognized PHPUnit dataset identity')
            identifier = class_name + '::' + method + '#' + dataset
        else:
            identifier = class_name + '::' + name
        file = case.attrib.get('file')
        key = (class_name, identifier, str(Path(file).resolve()) if file else '')
        count = int(case.attrib.get('assertions', '0'))
        if key in observed or key not in inventory or count <= 0 or any(c.tag in {'failure', 'error', 'skipped'} for c in case):
            raise RuntimeError('PHPUnit returned a duplicate, foreign, failed, skipped, or zero-assertion test identity')
        observed.add(key)
        assertions += count
    if observed != inventory:
        raise RuntimeError('PHPUnit result inventory does not match the pre-execution selection')
    return assertions


def build_archives(root: Path, destination: Path) -> list[dict]:
    """Build exact distribution bytes with an independent payload allowlist."""
    destination.mkdir(parents=True, exist_ok=True)
    output = []
    for name, expected in PACKAGES.items():
        source = root / 'packages' / name
        manifest = json.loads((source / 'composer.json').read_text())
        if not (source / expected).is_file() or not manifest['autoload']['psr-4']:
            raise RuntimeError(f'Missing required package source/autoload in {name}')
        archive = destination / f'{name}.zip'
        paths = [source / 'composer.json', *sorted((source / 'src').rglob('*.php'))]
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
            for path in paths:
                if not path.is_file() or path.is_symlink():
                    raise RuntimeError(f'Unexpected archive input {path}')
                info = zipfile.ZipInfo(path.relative_to(source).as_posix(), (1980, 1, 1, 0, 0, 0))
                info.external_attr = 0o100644 << 16
                zipped.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
            info = zipfile.ZipInfo('LICENSE', (1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            zipped.writestr(info, (root / 'LICENSE').read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(archive) as zipped:
            names = set(zipped.namelist())
            if not {'composer.json', 'LICENSE', expected} <= names or not all(p in {'composer.json', 'LICENSE'} or p.startswith('src/') for p in names):
                raise RuntimeError(f'Invalid distribution payload: {name}')
        output.append({'name': manifest['name'], 'version': '0.1.x-dev', 'path': str(archive), 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'manifest': manifest})
    return output


def command(argv, cwd, log, env=None, timeout=600):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('w') as stream:
        result = subprocess.run(argv, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}): {argv!r}\n{log.read_text(errors="replace")[-6000:]}')


def seed_layout(root: Path, destination: Path, fixture: str, archives=None):
    app = destination / 'fixtures' / fixture
    shutil.copytree(root / 'fixtures' / fixture, app, ignore=shutil.ignore_patterns('vendor', 'var', '.env.local', '.phpunit.cache'))
    packages = destination / 'packages'
    packages.mkdir(exist_ok=True)
    if fixture == 'app':
        for name in PACKAGES:
            (packages / name).symlink_to(root / 'packages' / name, target_is_directory=True)
        if (root / 'packages/tests').exists():
            (packages / 'tests').symlink_to(root / 'packages/tests', target_is_directory=True)
    else:
        for archive in archives or []:
            shutil.copy2(archive['path'], packages / Path(archive['path']).name)
    return app


def prepare_consumer(root: Path, destination: Path, archives, *, mode='prod', symfony='8.1.*', install=True):
    app = seed_layout(root, destination, 'consumer', archives)
    verify_consumer_metadata(app, archives)
    if symfony != '8.1.*':
        manifest = json.loads((app / 'composer.json').read_text())
        for name in ['symfony/framework-bundle', 'symfony/yaml', 'symfony/console']:
            manifest['require'][name] = symfony
        (app / 'composer.json').write_text(json.dumps(manifest, indent=4) + '\n')
        (app / 'composer.lock').unlink(missing_ok=True)
        if install:
            command(['composer', 'update', '--no-interaction', '--no-progress', '--no-scripts', '--prefer-dist', '--no-cache'], app, destination / 'resolve.log')
    if install:
        if not (app / 'composer.lock').is_file():
            raise RuntimeError('Consumer composer.lock missing; use explicit --bootstrap-locks maintenance')
        argv = ['composer', 'install', '--no-interaction', '--no-progress', '--prefer-dist', '--no-cache']
        if mode == 'prod':
            argv.append('--no-dev')
        command(argv, app, destination / 'install.log')
    return app


def verify_consumer_metadata(app, archives):
    """Reject a stale embedded package definition before resolving or installing it."""
    manifest = json.loads((app / 'composer.json').read_text())
    repositories = {row['package']['name']: row['package'] for row in manifest['repositories'] if row['type'] == 'package'}
    locked = {}
    if (app / 'composer.lock').is_file():
        lock = json.loads((app / 'composer.lock').read_text())
        locked = {row['name']: row for row in lock['packages'] + lock.get('packages-dev', [])}
    for archive in archives:
        with zipfile.ZipFile(archive['path']) as zipped:
            actual = json.loads(zipped.read('composer.json'))
        definition = dict(repositories[archive['name']])
        definition.pop('version', None)
        definition.pop('dist', None)
        if actual != definition:
            raise RuntimeError(f'Stale consumer package metadata for {archive["name"]}; refresh consumer definition and genuine lock')
        if locked:
            for field in ['require', 'autoload']:
                if locked.get(archive['name'], {}).get(field, {}) != actual.get(field, {}):
                    raise RuntimeError(f'Consumer lock does not bind current {archive["name"]} {field}')


def http_probe(app: Path, mode: str, log: Path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    env = {**os.environ, 'APP_ENV': mode, 'APP_DEBUG': '0'}
    with log.open('w') as stream:
        process = subprocess.Popen(['php', '-S', f'127.0.0.1:{port}', '-t', 'public', 'public/index.php'], cwd=app, env=env, stdout=stream, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 30
            error = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f'PHP server exited: {log.read_text()[-4000:]}')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/_ci/ready', timeout=2) as response:
                        return json.load(response)
                except (urllib.error.URLError, OSError) as exc:
                    error = exc
                    time.sleep(0.1)
            raise RuntimeError(f'Consumer HTTP readiness failed: {error}; {log.read_text()[-4000:]}')
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def installed_packages(app):
    installed = json.loads((app / 'vendor/composer/installed.json').read_text())
    return {p['name']: p for p in installed.get('packages', installed) if isinstance(p, dict)}


def bootstrap_locks(root: Path, evidence: Path):
    """Intentional resolution path; normal acceptance always requires existing locks."""
    archives = build_archives(root, evidence / 'archives')
    with tempfile.TemporaryDirectory(prefix='symfony-chrome-locks-') as temp:
        for fixture in ['app', 'consumer']:
            app = seed_layout(root, Path(temp) / fixture, fixture, archives)
            command(['composer', 'update', '--no-interaction', '--no-progress', '--prefer-dist', '--no-scripts', '--no-install'], app, evidence / f'{fixture}-resolve.log')
            for name in ['composer.lock', 'symfony.lock']:
                if (app / name).is_file():
                    shutil.copy2(app / name, root / 'fixtures' / fixture / name)
            generated = evidence / 'generated' / fixture
            shutil.copytree(app, generated, ignore=shutil.ignore_patterns('vendor', 'var', '.git', 'node_modules'))
            if json.loads((root / 'fixtures' / fixture / 'composer.json').read_text()) != json.loads((app / 'composer.json').read_text()):
                raise RuntimeError(f'Composer/Flex changed {fixture}/composer.json; inspect {generated} before accepting lock')
    return archives


def main(argv=None):
    def interrupted(signum, frame):
        raise InterruptedError('Acceptance worker interrupted by signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--bootstrap-locks', action='store_true')
    parser.add_argument('--native-only', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    rows = []
    try:
        missing = [executable for executable in ['php', 'composer'] if not shutil.which(executable)]
        if missing:
            if args.native_only or args.bootstrap_locks:
                raise RuntimeError(f'Native package execution requires {", ".join(missing)}')
            return docker_fallback(ROOT, evidence)
        if args.bootstrap_locks:
            archives = bootstrap_locks(ROOT, evidence)
            rows.append({'id': 'maintenance.locks', 'outcome': 'passed', 'assertions': 4, 'detail': 'Genuine Composer resolution; maintenance only, not acceptance.'})
        else:
            archives = build_archives(ROOT, evidence / 'archives')
            for name in PACKAGES:
                command(['composer', 'validate', '--strict', '--no-check-publish'], ROOT / 'packages' / name, evidence / f'{name}-validate.log')
            rows.append({'id': 'package.archives', 'outcome': 'passed', 'assertions': 8, 'detail': 'Both distribution payloads independently checked.'})
            for name in ['app', 'consumer']:
                if not (ROOT / 'fixtures' / name / 'composer.lock').is_file():
                    raise RuntimeError(f'{name}/composer.lock missing; use explicit --bootstrap-locks maintenance')
            with tempfile.TemporaryDirectory(prefix='symfony-chrome-package-') as temp:
                base = Path(temp)
                app = seed_layout(ROOT, base / 'app', 'app')
                command(['composer', 'install', '--no-interaction', '--no-progress', '--prefer-dist', '--no-scripts'], app, evidence / 'fixture-install.log')
                command(['composer', 'check-platform-reqs'], app, evidence / 'platform.log')
                listing = evidence / 'phpunit-inventory.xml'
                command(['php', 'vendor/bin/phpunit', '--configuration', 'phpunit.xml.dist', '--list-tests-xml', str(listing)], app, evidence / 'phpunit-discovery.log')
                inventory = phpunit_inventory(listing, ROOT / 'packages/tests/BundleKernelTest.php')
                junit = evidence / 'phpunit.xml'
                command(['php', 'vendor/bin/phpunit', '--configuration', 'phpunit.xml.dist', '--log-junit', str(junit)], app, evidence / 'phpunit.log', env={**os.environ, 'APP_ENV': 'test', 'APP_DEBUG': '0'})
                assertions = validate_phpunit_result(inventory, junit)
                rows.append({'id': 'package.kernel', 'outcome': 'passed', 'assertions': assertions, 'detail': f'{len(inventory)} native PHPUnit tests; discovered identities and exact JUnit retained.'})
                for mode in ['prod', 'dev']:
                    consumer = prepare_consumer(ROOT, base / mode, archives, mode=mode)
                    env = {**os.environ, 'APP_ENV': mode, 'APP_DEBUG': '0'}
                    command(['php', 'bin/console', 'cache:clear', '--no-warmup'], consumer, evidence / f'{mode}-compile.log', env)
                    command(['php', str(ROOT / 'tests/consumers/production-check.php')], consumer, evidence / f'{mode}-kernel.json', env)
                    data = http_probe(consumer, mode, evidence / f'{mode}-http.log')
                    (evidence / f'{mode}-response.json').write_text(json.dumps(data, indent=2) + '\n')
                    native_assertions = json.loads((evidence / f'{mode}-kernel.json').read_text())['assertions']
                    if not data['ready'] or data['environment'] != mode or 'ChromeBundle' not in data['bundles']:
                        raise RuntimeError(f'Wrong consumer response: {data}')
                    packages = installed_packages(consumer)
                    if packages['xormania/chrome-bundle']['installation-source'] != 'dist' or (consumer / 'vendor/xormania/chrome-bundle').is_symlink():
                        raise RuntimeError('Consumer did not install the archive as a distribution')
                    for archive in archives:
                        if archive['name'] not in packages:
                            continue
                        installed = consumer / 'vendor' / archive['name']
                        with zipfile.ZipFile(archive['path']) as zipped:
                            if any(not (installed / name).is_file() or (installed / name).read_bytes() != zipped.read(name) for name in zipped.namelist()):
                                raise RuntimeError(f'Installed distribution differs from current archive {archive["name"]}')
                    if mode == 'prod':
                        absent = {'xormania/chrome-devtools-bundle', 'symfony/web-profiler-bundle', 'symfony/ai-mate', 'carthage-software/mago', 'byte-kitsune/mago-symfony-wiring'}
                        if not absent.isdisjoint(packages) or 'ChromeDevtoolsBundle' in data['bundles']:
                            raise RuntimeError(f'Development packages leaked: {absent & packages.keys()}')
                    elif 'ChromeDevtoolsBundle' not in data['bundles']:
                        raise RuntimeError('Dev consumer did not register ChromeDevtoolsBundle')
                    rows.append({'id': f'consumer.{mode}', 'outcome': 'passed', 'assertions': native_assertions, 'detail': 'Native kernel assertions retained; additional Python checks verify archive bytes, dependency sets and real HTTP response.'})
        result = 0
    except (RuntimeError, AssertionError, OSError, subprocess.SubprocessError, ValueError, ET.ParseError) as exc:
        rows.append({'id': 'package.execution', 'outcome': 'error', 'assertions': 0, 'detail': str(exc)})
        print(str(exc), file=sys.stderr)
        result = 2
    (evidence / 'checks.json').write_text(json.dumps({'schema': 1, 'checks': rows, 'archives': locals().get('archives', [])}, indent=2) + '\n')
    return result


if __name__ == '__main__':
    sys.exit(main())
