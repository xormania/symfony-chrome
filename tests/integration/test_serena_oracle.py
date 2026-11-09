import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from serena_oracle import verify_constructor_reference

OWNER = r'App\Ci\BindingProbe'
INTERFACE = r'App\Ci\ContractTransport'


def graph():
    return {'source': {'symbol': r'app\ci\bindingprobe', 'member': '__construct'},
            'references': [{'kind': 'signature', 'target': {'symbol': r'app\ci\contracttransport'}}]}


class SerenaOracleContract(unittest.TestCase):
    def test_native_canonical_lowercase_symbols_match_php_identity(self):
        self.assertEqual(verify_constructor_reference(graph(), OWNER, INTERFACE)['owner'], OWNER.lower())

    def test_original_case_also_matches_php_identity(self):
        value = graph(); value['source']['symbol'] = OWNER
        value['references'][0]['target']['symbol'] = INTERFACE
        self.assertIn(INTERFACE.lower(), verify_constructor_reference(value, OWNER, INTERFACE)['signature_targets'])

    def test_foreign_owner_is_not_a_matching_reference_graph(self):
        value = graph(); value['source']['symbol'] = r'App\Ci\Unrelated'
        with self.assertRaisesRegex(AssertionError, 'another owner'):
            verify_constructor_reference(value, OWNER, INTERFACE)

    def test_other_member_or_class_wide_graph_is_rejected(self):
        for member in ('send', '', None):
            value = graph(); value['source']['member'] = member
            with self.subTest(member=member), self.assertRaisesRegex(AssertionError, 'another member'):
                verify_constructor_reference(value, OWNER, INTERFACE)

    def test_wrong_target_or_reference_kind_is_rejected(self):
        wrong_target = graph(); wrong_target['references'][0]['target']['symbol'] = r'App\Ci\Unrelated'
        wrong_kind = graph(); wrong_kind['references'][0]['kind'] = 'body'
        for value in (wrong_target, wrong_kind):
            with self.subTest(value=value), self.assertRaisesRegex(AssertionError, 'Signature'):
                verify_constructor_reference(value, OWNER, INTERFACE)


if __name__ == '__main__':
    unittest.main()
