"""Page operations must use an identity observed from the controlled MCP session."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(os.environ.get('TEST_SUBJECT_ROOT', Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(ROOT / 'tests/integration'))
spec = importlib.util.spec_from_file_location('chrome_identity_subject', ROOT / 'tools/testing/browser.py')
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)


class ChromeIdentityContract(unittest.TestCase):
    def test_owned_page_operations_use_the_observed_nondefault_identity(self):
        for observed_id in (37, 904):
            with self.subTest(observed_page_id=observed_id), tempfile.TemporaryDirectory() as temporary:
                calls = []
                class Provider:
                    def __init__(self, command, directory, **kwargs):
                        self.directory = Path(directory)
                        self.directory.mkdir(parents=True)
                        self.listed = False

                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        (self.directory / 'transport.json').write_text('{"closed":true}')

                    def initialize(self):
                        return {'serverInfo': {'name': 'chrome-devtools-mcp', 'version': '1.12.0'}}

                    def request(self, method):
                        assert method == 'tools/list'
                        return {'result': {'tools': [{'name': name} for name in
                                                    ('list_pages', 'navigate_page', 'take_snapshot')]}}

                    def call(self, name, arguments):
                        calls.append((name, arguments))
                        if name == 'list_pages':
                            self.listed = True
                            text = f'# list_pages response\n## Pages\n{observed_id}: about:blank [selected]\n'
                        else:
                            assert self.listed, 'page operation happened before observing a page identity'
                            assert arguments.get('pageId') == observed_id, (
                                f'{name} must receive observed pageId {observed_id}, got {arguments!r}')
                            if name == 'navigate_page' and arguments.get('type') != 'url':
                                return {'error': {'code': -32602, 'message': 'invalid navigation type'}}
                            text = 'Symfony Chrome contract\nLocal action' if name == 'take_snapshot' else 'navigated'
                        return {'result': {'content': [{'type': 'text', 'text': text}]}}

                with patch.object(browser, 'StdioClient', Provider), \
                        patch.object(browser, 'chrome_processes', return_value=set()), \
                        patch.object(browser, 'environment', return_value={}):
                    browser.chrome({'run_id': 'controlled'}, temporary)
                operations = [(name, args) for name, args in calls if name != 'list_pages']
                self.assertEqual(['navigate_page', 'take_snapshot', 'navigate_page'], [name for name, _ in operations])
                self.assertTrue(all(args['pageId'] == observed_id for _, args in operations))

    def test_controlled_page_selector_preserves_native_identity(self):
        from chrome_oracle import controlled_page_id
        for page_id, suffix in ((0, ''), (37, ' [selected]'), (904, '')):
            with self.subTest(page_id=page_id):
                native = f'# list_pages response\n## Pages\n{page_id}: about:blank{suffix}\n'
                self.assertEqual(page_id, controlled_page_id(native))

    def test_ambiguous_or_foreign_page_lists_do_not_select_a_target(self):
        from chrome_oracle import controlled_page_id
        candidates = [
            '', '# hints\n37: about:blank\n', '## Pages\n',
            '## Pages\n37: https://unrelated.invalid/\n',
            '## Pages\n37: about:blank\n904: about:blank\n',
            '## Pages\n37: about:blank\n904: https://unrelated.invalid/\n',
            '## Pages\nnot-an-id: about:blank\n',
            '## Pages\n37: about:blank#different\n',
            '## Pages\n37: about:blank\n## Pages\n904: about:blank\n',
        ]
        for native in candidates:
            with self.subTest(native=native), self.assertRaises((AssertionError, ValueError)):
                controlled_page_id(native)


if __name__ == '__main__':
    unittest.main()
