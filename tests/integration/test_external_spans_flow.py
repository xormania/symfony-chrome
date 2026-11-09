"""Fault replies must not certify recovery merely because JSON-RPC succeeded."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import external_spans


class RecoveryVerdictContract(unittest.TestCase):
    def rejected(self, rename):
        def controlled_success(binary, root, evidence, target, caller, *, warm):
            prefix = target[:target.index('target()')]
            return {'utf16_column': len(prefix.encode('utf-16-le')) // 2,
                    'rename_outcome': 'completed', 'rename': copy.deepcopy(rename)}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(external_spans, 'probe', side_effect=controlled_success):
                with self.assertRaises(AssertionError):
                    external_spans.run(Path(directory))

    def test_successful_rpc_with_null_rename_cannot_certify_recovery(self):
        self.rejected(None)

    def test_successful_rpc_with_empty_rename_cannot_certify_recovery(self):
        self.rejected({'changes': {}})


if __name__ == '__main__':
    unittest.main()
