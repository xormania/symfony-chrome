"""Direct Mago external-edit observation with an independent fresh-process control.

Adapted from the owner's Mago/Serena PoC; this is deterministic LSP evidence.
"""
import argparse
import json
import os
from pathlib import Path
import tempfile

from protocol import StdioClient


def probe(binary, root, evidence, target, caller, *, warm):
    with StdioClient([binary, 'language-server'], evidence, framing='content-length',
                     env={**os.environ, 'MAGO_EXPERIMENTAL_SERVER': '1'}, cwd=root) as client:
        def request(method, params):
            row = client.request(method, params)
            if 'error' in row:
                raise RuntimeError(json.dumps(row['error']))
            return row['result']
        request('initialize', {'processId': os.getpid(), 'rootUri': root.as_uri(),
                'workspaceFolders': [{'uri': root.as_uri(), 'name': root.name}],
                'capabilities': {'general': {'positionEncodings': ['utf-16']},
                    'textDocument': {'documentSymbol': {'hierarchicalDocumentSymbolSupport': True}},
                    'workspace': {'workspaceEdit': {'documentChanges': True}}}})
        client.notify('initialized', {})
        def opened(name):
            path = root / name
            client.notify('textDocument/didOpen', {'textDocument': {'uri': path.as_uri(),
                'languageId': 'php', 'version': 1, 'text': path.read_text()}})
        if warm:
            opened('Target.php')
            request('textDocument/documentSymbol', {'textDocument': {'uri': (root / 'Target.php').as_uri()}})
            client.notify('textDocument/didClose', {'textDocument': {'uri': (root / 'Target.php').as_uri()}})
            request('textDocument/documentSymbol', {'textDocument': {'uri': (root / 'Caller.php').as_uri()}})
            (root / 'Target.php').write_text(target)
            client.notify('workspace/didChangeWatchedFiles', {'changes': [{'uri': (root / 'Target.php').as_uri(), 'type': 2}]})
        opened('Caller.php')
        params = {'textDocument': {'uri': (root / 'Caller.php').as_uri()},
                  'position': {'line': 0, 'character': caller.index('target()')}}
        references = request('textDocument/references', {**params, 'context': {'includeDeclaration': True}})
        declarations = [row for row in references if row['uri'] == (root / 'Target.php').as_uri()]
        assert len(declarations) == 1, 'Missing/ambiguous known native declaration'
        result = {'utf16_column': declarations[0]['range']['start']['character']}
        try:
            result['rename'] = request('textDocument/rename', {**params, 'newName': 'renamed'})
            result['rename_outcome'] = 'completed'
        except RuntimeError as exc:
            result.update(rename_outcome='error', rename_error=str(exc))
        request('shutdown', None)
        client.notify('exit')
        return result



def verify_rename(edit, root, target, caller):
    """Exact fixture oracle, independent of the server's result/counts."""
    assert isinstance(edit, dict), 'Rename must return a nonempty WorkspaceEdit'
    representations = [name for name in ('changes', 'documentChanges') if edit.get(name) is not None]
    assert len(representations) == 1, 'Rename needs exactly one edit representation'
    expected = set()
    for name, text in (('Target.php', target), ('Caller.php', caller)):
        assert text.count('target()') == 1, 'Ambiguous fixture rename target'
        prefix = text[:text.index('target()')]
        line = prefix.count('\n')
        column = len(prefix.rsplit('\n', 1)[-1].encode('utf-16-le')) // 2
        expected.add(((root / name).as_uri(), line, column, line, column + 6, 'renamed'))
    if representations[0] == 'changes':
        changes = edit['changes']
        assert isinstance(changes, dict), 'Invalid changes map'
        documents = list(changes.items())
    else:
        changes = edit['documentChanges']
        assert isinstance(changes, list), 'Invalid documentChanges list'
        documents = []
        for document in changes:
            assert isinstance(document, dict) and 'kind' not in document, 'Only fixture text edits are allowed'
            assert isinstance(document.get('textDocument'), dict), 'Missing text document identity'
            documents.append((document['textDocument'].get('uri'), document.get('edits')))
    actual = []
    expected_uris = {row[0] for row in expected}
    for uri, edits in documents:
        assert uri in expected_uris and isinstance(edits, list), 'Rename changed an unexpected document'
        for row in edits:
            assert isinstance(row, dict) and isinstance(row.get('range'), dict), 'Missing rename edit range'
            start, end = row['range'].get('start'), row['range'].get('end')
            assert isinstance(start, dict) and isinstance(end, dict), 'Malformed rename edit range'
            actual.append((uri, start.get('line'), start.get('character'), end.get('line'), end.get('character'), row.get('newText')))
    assert len(actual) == 2, 'Rename must change exactly the two known identifiers'
    assert set(actual) == expected, 'Rename identifiers, UTF-16 ranges or replacement text differ from the independent fixture oracle'
    return {'documents': sorted(expected_uris), 'identifier_edits': 2, 'new_text': 'renamed'}


def run(evidence, binary='mago'):
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='mago-span-') as tmp:
        root = Path(tmp)
        original = '<?php class CloseTarget { public function target(): int { return 7; } }\n'
        updated = original.replace('public function', '/* 🧪 */ public function')
        caller = '<?php function use_target(CloseTarget $x): int { return $x->target(); }\n'
        (root / 'Target.php').write_text(original)
        (root / 'Caller.php').write_text(caller)
        (root / 'mago.toml').write_text('version = "1.58.2"\nphp-version = "8.4"\n[source]\npaths = ["."]\n')
        expected = len(updated[:updated.index('target()')].encode('utf-16-le')) // 2
        warm = probe(binary, root, evidence / 'warm', updated, caller, warm=True)
        fresh = probe(binary, root, evidence / 'fresh', updated, caller, warm=False)
        assert fresh['utf16_column'] == expected and fresh['rename_outcome'] == 'completed', 'Restart control did not match known source'
        fresh['rename_verified'] = verify_rename(fresh['rename'], root, updated, caller)
        stale = warm['utf16_column'] != expected
        if stale:
            assert warm['rename_outcome'] == 'error' and 'out of date' in warm.get('rename_error', ''), 'External-edit defect changed shape; investigate'
        else:
            assert warm['rename_outcome'] == 'completed', 'Correct position but unusable rename'
            warm['rename_verified'] = verify_rename(warm['rename'], root, updated, caller)
        result = {'schema': 1, 'expected_utf16_column': expected, 'warm': warm, 'fresh': fresh,
                  'classification': 'known_external_edit_span_defect' if stale else 'not_reproduced_on_this_tuple',
                  'recovery_verified': True, 'full_external_edit_support_claim': False}
        (evidence / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--binary', default='mago')
    args = parser.parse_args()
    run(args.evidence, args.binary)
