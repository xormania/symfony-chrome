#!/usr/bin/env python3
"""Real Mate, native/enriched Mago and Serena/Mago integration contracts."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/integration'))
from contracts import ContractCancelled, Checks, http, workspace
from archive_oracle import snapshot_profile, verify_archive
from serena_oracle import verify_constructor_reference
from protocol import StdioClient, text_of
sys.path.insert(0, str(ROOT / 'bin'))
from devlib import environment, host_port
import magolib
import matelib

OWNER = r'App\Ci\BindingProbe'
INTERFACE = r'App\Ci\ContractTransport'
CONCRETE = r'App\Ci\LoopbackTransport'


def mate(data, evidence):
    base = 'http://127.0.0.1:' + host_port(data)
    response = http(base, '/_ci/observe?marker=mate-before-prepare')
    assert response['token'], 'Real request has no profiler token'
    original_profiles = snapshot_profile(data['app'], response['token'])
    prepared = matelib.prepare(data)
    archive = Path(prepared['evidence']) / 'runtime-before-refresh.json'
    archived = json.loads(archive.read_text())
    archive_verified = verify_archive(original_profiles, archived['files'], Path(prepared['evidence']) / 'runtime-before-refresh')
    (Path(evidence) / 'mate-profile-oracle.json').write_text(json.dumps({'token': response['token'], **archive_verified}, indent=2) + '\n')
    current = http(base, '/_ci/observe?marker=mate-exact-request')
    row = matelib.call(data, ['tools:call', 'symfony-profiler-get', '--token=' + current['token'], '--format=json'])
    assert row.returncode == 0, 'Mate exact-profile read failed'
    profile = json.loads(row.stdout)['untrusted_data']
    assert profile['token'] == current['token'] and 'mate-exact-request' in profile['url'] and profile['status_code'] == 200, 'Mate returned another request profile'
    compiled = ['tools:call', 'symfony-service-detail', '--id=' + OWNER, '--context=inspection-dev', '--format=json']
    row = matelib.call(data, compiled)
    assert row.returncode == 0 and 'BindingProbe' in row.stdout.decode()
    source = Path(data['app']) / 'src/Ci/LoopbackTransport.php'
    original = source.read_bytes()
    try:
        source.write_bytes(original + b'\n// Controlled stale-source contract.\n')
        before = set((Path(data['evidence']) / 'mate/invocations').glob('*/invocation.json'))
        try:
            matelib.call(data, compiled)
        except AssertionError as exc:
            assert 'changed' in str(exc).lower(), str(exc)
            assert set((Path(data['evidence']) / 'mate/invocations').glob('*/invocation.json')) == before, 'Stale read invoked the tool before rejecting it'
        else:
            raise AssertionError('Compiled Mate read accepted stale source')
    finally:
        source.write_bytes(original)
    matelib.prepare(data)
    assert matelib.call(data, compiled).returncode == 0
    try:
        matelib.call(data, ['tools:call', 'symfony-profiler-get', '--token=not-a-token', '--format=json'])
    except AssertionError:
        pass
    else:
        raise AssertionError('Broad/invalid profiler token escaped runtime guard')
    return 'Real exact profile and compiled service reads; archive-before-clear, stale-source rejection and explicit recovery', 8


def native(data, evidence):
    source = Path(data['app']) / 'src/Ci/FindingProbe.php'
    source.write_text('<?php\nnamespace App\\Ci;\nfinal class FindingProbe { public function value(): string { return $neverDefined; } }\n')
    before = set((Path(data['evidence']) / 'mago/invocations').glob('*/invocation.json'))
    try:
        code = magolib.run_native(data, ['analyze', '--reporting-format', 'json', 'src/Ci/FindingProbe.php'])
        added = set((Path(data['evidence']) / 'mago/invocations').glob('*/invocation.json')) - before
        assert code == 1 and len(added) == 1, 'Mago did not classify the intentional source finding'
        report = json.loads(next(iter(added)).with_name('stdout').read_text())
        assert any('FindingProbe.php' in json.dumps(issue.get('annotations', [])) for issue in report['issues']), 'Mago finding does not identify planted source'
        try:
            magolib.run_native(data, ['format'])
        except ValueError:
            pass
        else:
            raise AssertionError('Unscoped formatting escaped the wrapper')
    finally:
        source.unlink()
    matelib.prepare(data)
    return 'Real analyzer finds undefined-variable source; explicit source annotation verified; unscoped write rejected', 4


def enriched(data, evidence):
    outputs = {}
    for enabled in (False, True):
        row = magolib.run_enriched(data, ['analyze'], symbols=[OWNER], wiring_enabled=enabled)
        assert row['status'] in ('clean', 'findings') and row['exit'] == row['native_exit'] in (0, 1), row
        graph = json.loads((Path(row['evidence']) / 'graph.json').read_text())
        refs = graph['symbols'][OWNER]['references']
        outputs[str(enabled)] = {'invocation': row, 'references': refs}
        assert any(ref['target'].lower() == INTERFACE.lower() for ref in refs), 'Known constructor interface absent'
    def has_binding(item):
        return any(ref['target'].lower() == CONCRETE.lower() and ref['kind'].lower() == 'body' for ref in item['references'])
    assert not has_binding(outputs['False']) and has_binding(outputs['True']), 'Wiring on/off did not change known concrete binding'
    (Path(evidence) / 'enriched-comparison.json').write_text(json.dumps(outputs, indent=2) + '\n')
    return 'Real extension enabled/disabled; known interface and concrete compiled contribution independently asserted', 5


def serena(data, evidence):
    command = [str(ROOT / 'bin/serena-mcp'), '--run', data['run_id']]
    with StdioClient(command, Path(evidence) / 'serena-mcp', timeout=120, env=environment(data)) as client:
        client.initialize()
        tools = client.request('tools/list')['result']['tools']
        assert {'initial_instructions', 'serena_repl'} <= {row['name'] for row in tools}
        instructions = text_of(client.call('initial_instructions', {}))
        match = re.search(r'session(?:\s+id)?[^\n]{0,40}?[`\'\"]([a-zA-Z0-9_-]+)[`\'\"]', instructions, re.I)
        assert match, 'Serena initial instructions omitted session identity'
        session = match[1]
        info = text_of(client.call('serena_repl', {'session': session, 'code': 's.info("lsp")'}))
        assert 'find_symbol' in info, 'No semantic LSP facade'
        symbol = text_of(client.call('serena_repl', {'session': session,
            'code': 's.lsp.find_symbol("BindingProbe", relative_path="src/Ci/BindingProbe.php", include_body=True)'}))
        assert 'BindingProbe' in symbol and 'ContractTransport' in symbol, symbol
        text_of(client.call('serena_repl', {'session': session, 'code': 'import json'}))
        refs = text_of(client.call('serena_repl', {'session': session,
            'code': 'json.dumps(s.lsp.get_symbol_references("src/Ci/BindingProbe.php", "App\\\\Ci\\\\BindingProbe", "__construct"))'}))
        verified = verify_constructor_reference(json.loads(refs), OWNER, INTERFACE)
        (Path(evidence) / 'serena-reference-oracle.json').write_text(json.dumps(verified, indent=2) + '\n')
    return 'Real Serena REPL resolves known symbol/body and Mago constructor reference; no model session claimed', 5



def external_spans(data, evidence):
    from devlib import execute
    target = Path(data['app']) / '.ci/lsp'
    target.mkdir(parents=True, exist_ok=True)
    for name in ('protocol.py', 'external_spans.py'):
        shutil.copy2(ROOT / 'tests/integration' / name, target / name)
    response = execute(data, 'python3', '/workspace/.ci/lsp/external_spans.py',
                       '--evidence', '/workspace/.ci/lsp/results', check=False, capture_output=True)
    (Path(evidence) / 'external-spans.log').write_bytes(response.stdout + response.stderr)
    if (target / 'results').exists():
        shutil.copytree(target / 'results', Path(evidence) / 'external-spans', dirs_exist_ok=True)
    assert response.returncode == 0, 'Direct native LSP span observation/restart control failed'
    result = json.loads((target / 'results/result.json').read_text())
    assert result['recovery_verified'] is True
    return result['classification'] + '; fresh-process UTF-16 position and rename control passed', 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--contract', choices=['tooling.mate', 'tooling.native-mago', 'tooling.enriched-mago', 'tooling.serena-mago', 'tooling.external-spans'], help='Run one named contract in a fresh owned workspace')
    args = parser.parse_args()
    checks = Checks(args.evidence)
    cancelled = False
    try:
        with workspace() as data:
            checks.context.update(workspace_run_id=data['run_id'], native_evidence=data['evidence'])
            if args.contract in (None, 'tooling.mate'):
                checks.check('tooling.mate', lambda: mate(data, args.evidence))
            if args.contract in (None, 'tooling.native-mago'):
                checks.check('tooling.native-mago', lambda: native(data, args.evidence))
            if args.contract in (None, 'tooling.enriched-mago'):
                checks.check('tooling.enriched-mago', lambda: enriched(data, args.evidence))
            if args.contract in (None, 'tooling.serena-mago'):
                checks.check('tooling.serena-mago', lambda: serena(data, args.evidence))
            if args.contract in (None, 'tooling.external-spans'):
                checks.check('tooling.external-spans', lambda: external_spans(data, args.evidence))
    except ContractCancelled as exc:
        cancelled = True
        checks.rows.append({'id': 'tooling.environment', 'outcome': 'error', 'assertions': 0,
                            'detail': 'ContractCancelled: ' + str(exc)})
    except Exception as exc:
        checks.rows.append({'id': 'tooling.environment', 'outcome': 'error', 'assertions': 0,
                            'detail': type(exc).__name__ + ': ' + str(exc)[-4000:]})
    checks.save(execution_interrupted=cancelled, capability_scope={'requested_mode': 'deterministic_real_protocol_calls', 'fresh_agent_session': False,
                                 'external_edit_support_claim': False})
    return 130 if cancelled else checks.exit()


if __name__ == '__main__':
    raise SystemExit(main())
