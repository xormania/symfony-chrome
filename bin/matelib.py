"""Symfony AI Mate preparation and guarded invocation for one selected run. Ported from mago-serena_v2-poc.

Compiled service facts, recorded runtime observations and discovery have different lifetimes.
Compiled reads require a fresh preparation; runtime reads require the configured context; discovery needs neither.
"""
import csv
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from devlib import ROOT, compose, container_id, environment, execute, load, require_running, sha, write_json

CONTEXT = 'inspection-dev'
RUNTIME_TOOLS = {
    'symfony-profiler-list': {'limit', 'method', 'url', 'ip', 'statusCode', 'context', 'from', 'to'},
    'symfony-profiler-get': {'token'},
    'monolog-search': {'term', 'regex', 'level', 'channel', 'environment', 'from', 'to', 'limit', 'kernelContext'},
    'monolog-context-search': {'key', 'value', 'level', 'environment', 'limit', 'kernelContext'},
    'monolog-tail': {'limit', 'level', 'environment', 'channel', 'kernelContext'},
    'monolog-list-files': {'environment', 'kernelContext'},
    'monolog-list-channels': {'kernelContext'},
    'server-info': set(),
}
GLOBAL_FLAGS = {'--silent', '--quiet', '--verbose', '--ansi', '--no-ansi', '--no-interaction', '-q', '-v', '-vv', '-vvv', '-n'}
INDEPENDENT = {'help', 'list', 'init', 'discover', 'tools:list', 'tools:inspect', 'resources:list', 'resources:inspect',
               'resources:templates:list', 'debug:capabilities', 'debug:extensions', '--help', '-h', '--version', '-V'}
RUNTIME_MAX_FILES = 4096
RUNTIME_MAX_BYTES = 128 * 1024 * 1024
SOURCE_DIRS = ('src', 'tests', 'config', 'mate', '.mago')
SOURCE_FILES = ('composer.json', 'composer.lock', 'mago.toml', '.env')


def selected(run_id):
    data = load(run_id)
    require_running(data)
    return data


def invocation(data):
    return shlex.join([str(ROOT / 'bin/mate'), '--run', data['run_id'], '--'])


def application_state(app):
    """Hash of everything a compiled read depends on: manifests, lock, source, config, Mago and Mate configuration."""
    app = Path(app)
    files = {}
    for name in SOURCE_FILES:
        if (app / name).is_file():
            files[name] = sha(app / name)
    for base in SOURCE_DIRS:
        for path in sorted((app / base).rglob('*')):
            if path.is_file() and not path.is_symlink():
                files[str(path.relative_to(app))] = sha(path)
    return files


def metadata_hashes(app):
    app = Path(app)
    paths = sorted((app / 'var/cache/dev').glob('*DebugContainer.xml'))
    assert len(paths) == 1 and paths[0].is_file(), 'Dev metadata absent or ambiguous; run ./bin/dev mate-prepare'
    return {str(p.relative_to(app)): sha(p) for p in paths}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def fresh(data):
    marker = Path(data['trusted']) / 'mate-preparation.json'
    assert marker.is_file(), 'Metadata unprepared; run ./bin/dev mate-prepare --run ' + data['run_id']
    record = json.loads(marker.read_text())
    assert record.get('run_id') == data['run_id'] and record.get('workspace') == data['app'], 'Preparation belongs to another workspace'
    assert record.get('application_sha256') == digest(application_state(data['app'])), 'Application/dependencies changed; run mate-prepare explicitly'
    assert record.get('metadata') == metadata_hashes(data['app']), 'Compiled metadata changed; run mate-prepare explicitly'
    assert record.get('container_id') == container_id(data), 'Container replaced; run mate-prepare explicitly'
    reference = Path(data['app']) / '.mago/container-reference.dev.json'
    assert reference.is_file() and sha(reference) == record['wiring_reference_sha256'], 'Wiring reference absent/changed; run mate-prepare explicitly'
    return record


def command_policy(argv):
    """Classify discovery, runtime reads and compiled reads. Unknown or abbreviated commands count as compiled."""
    index = 0
    while index < len(argv) and argv[index] in GLOBAL_FLAGS:
        index += 1
    if index == len(argv):
        return {'kind': 'compiled'}
    name = argv[index]
    if name in INDEPENDENT:
        return {'kind': 'discovery', 'command': name}
    if name == 'resources:read' and index + 1 < len(argv):
        match = re.fullmatch(r'symfony-profiler://profile/([0-9a-f]{6})(?:/([a-zA-Z0-9_.-]+))?', argv[index + 1])
        if match:
            for option in argv[index + 2:]:
                assert option in GLOBAL_FLAGS or option in ('--format=json', '--format=pretty', '--format=toon'), \
                    'Profiler resources accept only an exact URI and --format=VALUE'
            return {'kind': 'runtime', 'command': name, 'uri': argv[index + 1], 'token': match[1],
                    'collector': match[2], 'parameters': {}}
    if name != 'tools:call' or index + 1 >= len(argv) or argv[index + 1] not in RUNTIME_TOOLS:
        return {'kind': 'compiled', 'command': name}
    tool = argv[index + 1]
    params, bag = {}, {}
    tokens = argv[index + 2:]
    i = 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if token in GLOBAL_FLAGS:
            continue
        assert token.startswith('--') and token != '--', 'Runtime tools require TOOL followed by long options; inspect the installed schema'
        key, equal, value = token[2:].partition('=')
        if not equal:
            if i < len(tokens) and (not tokens[i].startswith('-') or tokens[i][:2] == '-1'):
                value = tokens[i]
                i += 1
            else:
                value = True
        assert key not in params, 'Repeated runtime option: ' + key
        params[key] = value
    if 'json' in params:
        raw = params.pop('json')
        assert isinstance(raw, str), 'Runtime --json requires a JSON object value'
        bag = json.loads(raw)
        assert isinstance(bag, dict), 'Runtime --json must be an object'
    if 'format' in params:
        assert params.pop('format') in ('json', 'pretty', 'toon'), 'Unsupported Mate output format'
    params = {**bag, **params}
    assert set(params) <= RUNTIME_TOOLS[tool], 'Unknown runtime tool parameter; inspect ' + tool
    if 'limit' in RUNTIME_TOOLS[tool]:
        limit = params.get('limit', 20 if tool == 'symfony-profiler-list' else 100)
        assert not isinstance(limit, bool) and str(limit).isdigit() and 1 <= int(limit) <= 100, 'Runtime limit must be between 1 and 100'
    if tool == 'symfony-profiler-list':
        assert params.get('context') == CONTEXT, 'Profiler list requires --context=' + CONTEXT
    if tool.startswith('monolog-'):
        assert params.get('kernelContext') == CONTEXT, 'Log inspection requires --kernelContext=' + CONTEXT
        if 'environment' in RUNTIME_TOOLS[tool]:
            assert params.get('environment') == 'dev', 'Log inspection requires --environment=dev'
    if tool == 'symfony-profiler-get':
        assert isinstance(params.get('token'), str) and re.fullmatch(r'[0-9a-f]{6}', params['token']), 'Expected an exact six-character profiler token'
    return {'kind': 'runtime', 'command': name, 'tool': tool, 'parameters': params, 'token': params.get('token')}


def runtime_files(data, names, *, missing_ok=False):
    app = Path(data['app'])
    found, size = [], 0
    for name in names:
        target = app / name
        if not target.exists():
            assert missing_ok, 'Runtime data directory missing: ' + name
            continue
        assert target.is_dir() and not target.is_symlink(), 'Runtime data path is not a plain directory: ' + name
        for path in target.rglob('*'):
            assert not path.is_symlink(), 'Runtime evidence contains a symlink: ' + str(path)
            if path.is_file():
                found.append(path)
                size += path.stat().st_size
                assert len(found) <= RUNTIME_MAX_FILES and size <= RUNTIME_MAX_BYTES, \
                    'Runtime evidence exceeds the bounded budget (4096 files / 128 MiB); rotate it explicitly'
    return found


def runtime_identity(data, policy):
    marker = Path(data['trusted']) / 'mate-runtime.json'
    assert marker.is_file(), 'Runtime inspection unconfigured; run ./bin/dev mate-prepare once in a healthy workspace'
    record = json.loads(marker.read_text())
    assert record.get('run_id') == data['run_id'] and record.get('workspace') == data['app'], 'Runtime configuration belongs to another workspace'
    config = Path(data['app']) / 'mate/config.php'
    assert config.is_file() and sha(config) == record.get('config_sha256'), 'mate/config.php changed; reconcile it explicitly'
    assert record.get('container_id') == container_id(data), 'Runtime container replaced; run mate-prepare explicitly'
    tool = policy.get('tool', '')
    paths = [] if tool == 'server-info' else ['var/log'] if tool.startswith('monolog-') else ['var/cache/dev/profiler']
    runtime_files(data, paths)
    observations = []
    if policy.get('token'):
        index = Path(data['app']) / 'var/cache/dev/profiler/index.csv'
        if index.is_file():
            with index.open(newline='') as stream:
                for row in csv.reader(stream):
                    if len(row) >= 7 and row[0] == policy['token']:
                        observations.append({'token': row[0], 'method': row[2], 'url': row[3],
                                             'request_time_unix': int(row[4]), 'status_code': row[6]})
    return {**record, 'observations': observations, 'read_paths': paths}


def preserve_runtime(data, evidence):
    """An explicit refresh may delete profiles: archive them first."""
    files = runtime_files(data, ['var/cache/dev/profiler', 'var/log'], missing_ok=True)
    destination = Path(evidence) / 'runtime-before-refresh'
    manifest = {}
    for path in files:
        name = str(path.relative_to(data['app']))
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        manifest[name] = {'sha256': sha(target), 'bytes': target.stat().st_size}
    write_json(Path(evidence) / 'runtime-before-refresh.json', {'run_id': data['run_id'], 'workspace': data['app'],
               'environment': 'dev', 'context': CONTEXT, 'historical': True, 'files': manifest})
    return manifest


def call(data, argv):
    policy = command_policy(argv)
    runtime = runtime_identity(data, policy) if policy['kind'] == 'runtime' else None
    record = fresh(data) if policy['kind'] == 'compiled' else None
    directory = Path(data['evidence']) / 'mate/invocations' / uuid.uuid4().hex
    directory.mkdir(parents=True)
    command = compose(data, 'exec', '-T', '-w', '/workspace', 'php', 'env', 'APP_ENV=dev', 'APP_DEBUG=1',
                      'php', 'vendor/bin/mate', *argv)
    started = time.monotonic()
    result = subprocess.run(command, env=environment(data), capture_output=True, timeout=180)
    (directory / 'stdout').write_bytes(result.stdout)
    (directory / 'stderr').write_bytes(result.stderr)
    write_json(directory / 'invocation.json', {
        'run_id': data['run_id'], 'workspace': data['app'], 'argv': command, 'environment': 'dev', 'context': CONTEXT,
        'exit': result.returncode, 'elapsed_s': round(time.monotonic() - started, 6), 'policy': policy,
        'observed_at_unix': time.time(),
        'runtime': None if not runtime else {
            'historical': policy.get('tool') != 'server-info',
            'scope': 'mate_cli_process' if policy.get('tool') == 'server-info' else 'recorded_application_observation',
            'current_application_state': False, 'observations': runtime['observations'],
            'read_paths': runtime['read_paths'], 'container_id': runtime['container_id']},
        'preparation_id': record['preparation_id'] if record else None,
        'application_sha256': record['application_sha256'] if record else None})
    return result


def invoke(data, argv):
    result = call(data, argv)
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    return result.returncode


def compiled_reference(data, evidence):
    """Export the two Console container views privately, then the package's sanitized reference."""
    evidence = Path(evidence)
    views = {}
    for name, extra in (('types', ['--types']), ('services', [])):
        argv = ['env', 'APP_ENV=dev', 'APP_DEBUG=1', 'php', 'bin/console', 'debug:container', '--env=dev',
                '--format=json', '--no-interaction', *extra]
        response = execute(data, *argv, capture_output=True, check=False)
        (evidence / (name + '.stderr')).write_bytes(response.stderr)
        assert response.returncode == 0, 'Compiled container export failed: ' + name
        path = Path(data['state']) / ('wiring-' + name + '.json')
        path.write_bytes(response.stdout)
        path.chmod(0o600)
        views[name] = {'argv': argv, 'exit': response.returncode, 'sha256': sha(path)}
    argv = ['php', 'vendor/byte-kitsune/mago-symfony-wiring/bin/create-container-reference.php',
            '--types=/home/dev/wiring-types.json', '--services=/home/dev/wiring-services.json',
            '--autoload=/workspace/vendor/autoload.php']
    response = execute(data, *argv, capture_output=True, check=False)
    (evidence / 'reference.stderr').write_bytes(response.stderr)
    write_json(evidence / 'export-invocations.json', {'views': views, 'exporter': {'argv': argv, 'exit': response.returncode}})
    assert response.returncode == 0, 'Compiled wiring sanitization failed; see reference.stderr'
    value = json.loads(response.stdout)
    assert value['environment'] == 'dev' and value['scope'] == 'compiled_container_autowiring'
    assert value['definitions'], 'Empty compiled service set'
    target = Path(data['app']) / '.mago/container-reference.dev.json'
    target.write_bytes(response.stdout)
    (evidence / 'container-reference.dev.json').write_bytes(response.stdout)
    return target


def install_runtime_instructions(owner, instructions):
    """Replace only the managed block; owner-written text stays byte for byte."""
    owner = Path(owner)
    existing = owner.read_text() if owner.exists() else ''
    begin, end = '<!-- DEV RUNTIME BEGIN -->', '<!-- DEV RUNTIME END -->'
    block = begin + '\n' + instructions.rstrip('\n') + '\n' + end
    if begin in existing:
        before, rest = existing.split(begin, 1)
        assert end in rest, 'Incomplete managed runtime block preserved'
        _, after = rest.split(end, 1)
        content = before + block + after
    else:
        assert end not in existing, 'Incomplete managed runtime block preserved'
        separator = '' if not existing else '\n' if existing.endswith('\n') else '\n\n'
        content = existing + separator + block + '\n'
    owner.write_text(content)


def prepare(data):
    data = selected(data['run_id'])
    app = Path(data['app'])
    attempt = 'prepare-' + uuid.uuid4().hex
    evidence = Path(data['evidence']) / 'mate' / attempt
    evidence.mkdir(parents=True)
    marker = Path(data['trusted']) / 'mate-preparation.json'
    marker.unlink(missing_ok=True)
    assert (app / 'vendor/autoload.php').is_file(), 'Application dependencies absent; run ./bin/dev up first'
    for name in ('vendor/bin/mate', 'vendor/byte-kitsune/mago-symfony-wiring/bin/create-container-reference.php'):
        assert (app / name).is_file(), 'Missing ' + name + '; the fixture composer.json declares it, reinstall dependencies'
    preserve_runtime(data, evidence)
    config = app / 'mate/config.php'
    assert config.is_file(), 'mate/config.php missing from the workspace'
    instructions = (ROOT / 'tools/mate/runtime-instructions.md.in').read_text().replace('__DEV_INVOCATION__', invocation(data))
    install_runtime_instructions(app / 'AGENTS.md', instructions)
    write_json(Path(data['trusted']) / 'mate-runtime.json', {'run_id': data['run_id'], 'workspace': data['app'],
               'environment': 'dev', 'context': CONTEXT, 'container_id': container_id(data), 'config_sha256': sha(config)})
    for name, argv in (
        ('init', ('php', 'vendor/bin/mate', 'init', '--no-interaction')),
        ('autoload', ('composer', 'dump-autoload', '--no-plugins', '--no-scripts', '--no-interaction')),
        ('discover', ('php', 'vendor/bin/mate', 'discover', '--no-interaction')),
        ('metadata', ('env', 'APP_ENV=dev', 'APP_DEBUG=1', 'php', 'bin/console', 'cache:clear', '--env=dev', '--no-interaction')),
    ):
        execute(data, *argv, log=evidence / (name + '.log'))
    mago = app / '.mago'
    mago.mkdir(exist_ok=True)
    for name in ('extensions.php', 'wiring.toml'):
        source, destination = ROOT / 'tools/mago' / name, mago / name
        if destination.exists():
            assert destination.read_bytes() == source.read_bytes(), 'Existing .mago/' + name + ' differs from tools/mago; reconcile it explicitly'
        else:
            shutil.copy2(source, destination)
    reference = compiled_reference(data, evidence)
    (evidence / 'installed-packages.json').write_text(
        execute(data, 'composer', 'show', '--format=json', capture_output=True, text=True).stdout)
    record = {'schema': 1, 'run_id': data['run_id'], 'workspace': data['app'], 'environment': 'dev', 'context': CONTEXT,
              'preparation_id': attempt, 'preparation_exit': 0,
              'application_sha256': digest(application_state(app)), 'metadata': metadata_hashes(app),
              'container_id': container_id(data), 'wiring_reference_sha256': sha(reference),
              'invocation': invocation(data), 'evidence': str(evidence)}
    write_json(evidence / 'preparation.json', record)
    write_json(marker, record)
    return record
