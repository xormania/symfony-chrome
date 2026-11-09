"""Independent UTF-16/file/edit expectations calibrate usable-rename claims."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from external_spans import verify_rename

ROOT = Path('/tmp/rename-oracle')
TARGET = '🧪 target();\n'
CALLER = 'target();\n'


def edit():
    # The astral symbol is two UTF-16 units; these expected coordinates are
    # literal fixture facts, not computed with the oracle's conversion helper.
    return {'changes': {
        (ROOT / 'Target.php').as_uri(): [{'range': {'start': {'line': 0, 'character': 3}, 'end': {'line': 0, 'character': 9}}, 'newText': 'renamed'}],
        (ROOT / 'Caller.php').as_uri(): [{'range': {'start': {'line': 0, 'character': 0}, 'end': {'line': 0, 'character': 6}}, 'newText': 'renamed'}],
    }}


class RenameOracleContract(unittest.TestCase):
    def test_exact_changes_map_is_usable(self):
        self.assertEqual(verify_rename(edit(), ROOT, TARGET, CALLER)['identifier_edits'], 2)

    def test_exact_document_changes_are_usable(self):
        document = {'documentChanges': [{'textDocument': {'uri': uri, 'version': None}, 'edits': edits}
                                      for uri, edits in reversed(list(edit()['changes'].items()))]}
        self.assertEqual(verify_rename(document, ROOT, TARGET, CALLER)['identifier_edits'], 2)

    def test_null_or_empty_successful_results_are_rejected(self):
        for value in (None, {}, {'changes': {}}, {'documentChanges': []}):
            with self.subTest(value=value), self.assertRaises(AssertionError):
                verify_rename(value, ROOT, TARGET, CALLER)

    def test_wrong_replacement_is_rejected(self):
        candidate = edit()
        next(iter(candidate['changes'].values()))[0]['newText'] = 'wrong'
        with self.assertRaisesRegex(AssertionError, 'independent fixture oracle'):
            verify_rename(candidate, ROOT, TARGET, CALLER)

    def test_codepoint_range_is_not_a_utf16_range(self):
        candidate = edit()
        row = candidate['changes'][(ROOT / 'Target.php').as_uri()][0]
        row['range'] = {'start': {'line': 0, 'character': 2}, 'end': {'line': 0, 'character': 8}}
        with self.assertRaises(AssertionError):
            verify_rename(candidate, ROOT, TARGET, CALLER)

    def test_foreign_file_substitution_is_rejected(self):
        candidate = edit()
        candidate['changes'][(ROOT / 'Unrelated.php').as_uri()] = candidate['changes'].pop((ROOT / 'Caller.php').as_uri())
        with self.assertRaisesRegex(AssertionError, 'unexpected document'):
            verify_rename(candidate, ROOT, TARGET, CALLER)

    def test_missing_duplicate_and_additional_edits_are_rejected(self):
        missing = edit(); missing['changes'].pop((ROOT / 'Caller.php').as_uri())
        duplicate = edit(); duplicate['changes'][(ROOT / 'Target.php').as_uri()] *= 2
        resource = {'documentChanges': [{'kind': 'delete', 'uri': (ROOT / 'Target.php').as_uri()}]}
        mixed = {**edit(), 'documentChanges': []}
        for candidate in (missing, duplicate, resource, mixed):
            with self.subTest(candidate=candidate), self.assertRaises(AssertionError):
                verify_rename(candidate, ROOT, TARGET, CALLER)


if __name__ == '__main__':
    unittest.main()
