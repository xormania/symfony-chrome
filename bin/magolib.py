"""Run-bound Mago commands: native profile with evidence, and the Symfony-enriched profile. Ported from mago-serena_v2-poc."""
import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

from devlib import ROOT, compose, environment, execute, load, require_running, sha, write_json

MAGO_REV = '46df50c96d93d0ac3655c116c375574277cf0b30'
WIRING_REV = '28c3f54065b71fe046a7474ced401aeadc941b0f'
PHP_TARGET = '8.4'
NATIVE_COMMANDS = ('analyze', 'lint', 'format', 'guard', 'cst', 'config', 'list-files', 'extension', 'fix', 'version', 'help')


def selected(run_id):
    data = load(run_id)
    require_running(data)
    return data


def tool_identity(data):
    identity = json.loads(execute(data, 'cat', '/opt/dev/image-identity.json', capture_output=True, text=True).stdout)
    assert identity['mago_source_sha'] == MAGO_REV, 'Unexpected Mago executable; rebuild the pinned image'
    assert (Path(data['app']) / 'vendor/autoload.php').is_file(), 'Application dependencies absent; run ./bin/dev up first'
    assert (Path(data['app']) / 'mago.toml').is_file(), 'Native mago.toml missing from the workspace'
    return {'config': '/workspace/mago.toml', 'config_sha256': sha(Path(data['app']) / 'mago.toml'),
            'version': identity['mago'], 'revision': identity['mago_source_sha'],
            'binary_sha256': identity['mago_binary_sha256'], 'php_target': PHP_TARGET,
            'composer_lock_sha256': sha(Path(data['app']) / 'composer.lock') if (Path(data['app']) / 'composer.lock').is_file() else None}


def validate_write_scope(data, argv):
    """Formatter and fixer operands must be explicit workspace-relative PHP files."""
    command, args = argv[0], argv[1:]
    if command != 'format' and not (command in ('lint', 'analyze') and '--fix' in args):
        return
    message = 'Formatting/fixing requires explicit existing workspace-relative PHP file targets only'
    flags = {'--check', '-c', '--dry-run', '--diff', '-d'} if command == 'format' else {
        '--fix', '--fail-on-remaining', '--unsafe', '--potentially-unsafe', '--format-after-fix', '--fmt',
        '--dry-run', '--diff', '-d', '--sort', '--ignore-baseline', '--fail-on-out-of-sync-baseline'}
    values = set()
    if command in ('lint', 'analyze'):
        values = {'--reporting-format', '--reporting-target', '--minimum-fail-level', '-m', '--minimum-report-level', '--retain-code'}
        if command == 'lint':
            flags |= {'--pedantic', '--semantics', '-s'}
            values |= {'--only', '-o'}
        else:
            flags |= {'--no-stubs', '--skip-ignores'}
            values |= {'--slow-file-warning-threshold-ms'}
    paths, index, operands = [], 0, False
    while index < len(args):
        arg = args[index]
        if arg == '--' and not operands:
            operands = True
        elif arg.startswith('-') and not operands:
            if arg in ('--help', '-h'):
                return
            option, separator, value = arg.partition('=')
            if option in values:
                if not separator:
                    index += 1
                    if index >= len(args) or args[index].startswith('-'):
                        raise ValueError(message + '; missing value for ' + option)
                elif not value:
                    raise ValueError(message + '; missing value for ' + option)
            elif option not in flags or separator:
                raise ValueError(message + '; unsupported scoped option: ' + arg)
        else:
            paths.append(arg)
        index += 1
    if not paths:
        raise ValueError(message)
    app = Path(data['app']).resolve()
    for operand in paths:
        path = Path(operand)
        candidate = app / path
        if (path.is_absolute() or '..' in path.parts or path.suffix != '.php' or not candidate.is_file()
                or not candidate.resolve().is_relative_to(app)):
            raise ValueError(message + '; rejected target: ' + operand)


def run_native(data, argv, *, echo=False):
    assert argv and argv[0] in NATIVE_COMMANDS, 'Unsupported Mago command'
    assert not any(x.split('=', 1)[0] in ('--workspace', '--config', '--php-version') for x in argv), \
        'Workspace/config/PHP target are selected by the run'
    validate_write_scope(data, argv)
    if argv[0] == 'fix':
        raise ValueError('Use a scoped lint/analyze --fix invocation and inspect its diff')
    identity = tool_identity(data)
    directory = Path(data['evidence']) / 'mago/invocations' / uuid.uuid4().hex
    directory.mkdir(parents=True)
    command = compose(data, 'exec', '-T', '-w', '/workspace', 'php', 'mago', '--workspace', '/workspace',
                      '--config', identity['config'], '--php-version', PHP_TARGET, '--colors', 'never', *argv)
    started = time.monotonic()
    result = subprocess.run(command, env=environment(data), capture_output=True)
    (directory / 'stdout').write_bytes(result.stdout)
    (directory / 'stderr').write_bytes(result.stderr)
    write_json(directory / 'invocation.json', {'run_id': data['run_id'], 'host_workspace': data['app'], 'argv': command,
               'exit': result.returncode, 'elapsed_s': round(time.monotonic() - started, 6), 'tool': identity,
               'evidence': str(directory)})
    if echo:
        sys.stdout.buffer.write(result.stdout)
        sys.stderr.buffer.write(result.stderr)
    return result.returncode


def selected_symbols(symbols):
    symbols = list(symbols) if symbols else [r'App\Controller\ReadyController']
    if (not 1 <= len(symbols) <= 8 or len(set(symbols)) != len(symbols)
            or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\\[A-Za-z_][A-Za-z0-9_]*)*', name) or len(name) > 200 for name in symbols)):
        raise ValueError('Supply one to eight distinct fully qualified class names with --symbol')
    return symbols


def enriched_identity(data):
    app = Path(data['app'])
    for name in ('extensions.php', 'wiring.toml'):
        target = app / '.mago' / name
        assert target.is_file() and sha(target) == sha(ROOT / 'tools/mago' / name), 'Enriched configuration differs from tools/mago: ' + name
    identity = tool_identity(data)
    installed = json.loads((app / 'vendor/composer/installed.json').read_text())
    packages = {p['name']: p for p in installed['packages']}
    for name, revision in (('carthage-software/mago', MAGO_REV), ('byte-kitsune/mago-symfony-wiring', WIRING_REV)):
        assert packages.get(name, {}).get('source', {}).get('reference') == revision, 'Installed ' + name + ' does not match the pinned toolchain'
    return {**identity, 'config': '/workspace/.mago/wiring.toml', 'config_sha256': sha(app / '.mago/wiring.toml'),
            'extension_config_sha256': sha(app / '.mago/extensions.php'), 'sdk_source': MAGO_REV,
            'extension_source': WIRING_REV, 'backend': 'php'}


def run_enriched(data, argv, *, symbols=(), echo=False, wiring_enabled=True):
    """Analyze with the real extension host against freshly prepared Symfony facts. Exit 3 means stale or tool failure, never clean."""
    from matelib import fresh
    if not argv or argv[0] != 'analyze':
        raise ValueError('The Symfony profile accepts analyze; use the native profile for other commands')
    if any(arg.split('=', 1)[0] in ('--workspace', '--config', '--php-version') for arg in argv):
        raise ValueError('Workspace/config/PHP target are selected by the run')
    validate_write_scope(data, argv)
    symbols = selected_symbols(symbols)
    directory = Path(data['evidence']) / 'mago/enriched' / uuid.uuid4().hex
    directory.mkdir(parents=True)
    row = {'schema': 1, 'kind': 'symfony_enriched_mago_analysis', 'run_id': data['run_id'], 'host_workspace': data['app'],
           'requested_argv': argv, 'symbols': symbols, 'wiring_enabled': wiring_enabled, 'exit': 3, 'native_exit': None,
           'status': 'stale_preparation', 'preparation_id': None, 'evidence': str(directory),
           'observation': str(directory / 'graph.json')}
    stdout, stderr = b'', b''
    started = time.monotonic()
    try:
        try:
            prepared = fresh(data)
            identity = enriched_identity(data)
        except (AssertionError, OSError, ValueError, KeyError) as exc:
            row['reason'] = str(exc) + '; refresh with ./bin/dev mate-prepare --run ' + data['run_id']
            stderr = ('mago-enriched: ' + row['reason'] + '\n').encode()
            return row
        row.update(preparation_id=prepared['preparation_id'], application_sha256=prepared['application_sha256'],
                   compiled_metadata=prepared['metadata'], wiring_reference_sha256=prepared['wiring_reference_sha256'], tool=identity)
        observation = '/evidence/' + str((directory / 'graph.json').relative_to(Path(data['evidence'])))
        command = compose(data, 'exec', '-T', '-w', '/workspace', 'php', 'env',
                          'DEV_WIRING=' + ('1' if wiring_enabled else '0'), 'DEV_WIRING_SYMBOLS=' + json.dumps(symbols),
                          'DEV_WIRING_OBSERVATION=' + observation, 'mago', '--workspace', '/workspace',
                          '--config', identity['config'], '--php-version', PHP_TARGET, '--threads', '1', '--colors', 'never', *argv)
        row['argv'] = command
        process = subprocess.run(command, env=environment(data), capture_output=True)
        stdout, stderr = process.stdout, process.stderr
        row.update(exit=process.returncode, native_exit=process.returncode, status='tool_failure')
        path = directory / 'graph.json'
        if process.returncode in (0, 1) and path.is_file():
            graph = json.loads(path.read_text())
            assert graph['observer'] == 'symfony-chrome/wiring-observer' and graph['wiring_enabled'] is wiring_enabled
            assert set(graph['symbols']) == set(symbols), 'Observer returned different selected symbols'
            if '--reporting-format=json' in argv or any(a == '--reporting-format' and argv[i + 1:i + 2] == ['json'] for i, a in enumerate(argv)):
                report = json.loads(stdout)
                attestations = [i for i in report['issues'] if i['code'] == 'byte-kitsune/symfony-wiring/analysis-attestation']
                assert len(attestations) == int(wiring_enabled), 'Wiring completion attestation differs'
                if wiring_enabled:
                    note = next((n for n in attestations[0]['notes'] if n.startswith('extension-attestation: ')), '')
                    attestation = json.loads(note.removeprefix('extension-attestation: '))
                    assert attestation['complete'] is True
                    row['extension_attestation'] = attestation
            row['status'] = 'findings' if process.returncode else 'clean'
            row['analyzed_files'] = len(graph['files'])
        else:
            row['reason'] = 'Mago did not complete its after-analysis observer; inspect native stderr'
        return row
    except (AssertionError, OSError, ValueError, KeyError) as exc:
        row.update(status='tool_failure', reason=str(exc))
        return row
    finally:
        if row['status'] == 'tool_failure':
            if row['exit'] in (0, 1):
                row['exit'] = 3
            stderr += ('mago-enriched: ' + row.get('reason', 'Enriched analysis failed') + ' (native exit ' + str(row['native_exit']) + ')\n').encode()
        (directory / 'stdout').write_bytes(stdout)
        (directory / 'stderr').write_bytes(stderr)
        row['elapsed_s'] = round(time.monotonic() - started, 6)
        write_json(directory / 'invocation.json', row)
        if echo:
            sys.stdout.buffer.write(stdout)
            sys.stderr.buffer.write(stderr)
            print('Enriched evidence: ' + str(directory), file=sys.stderr)
