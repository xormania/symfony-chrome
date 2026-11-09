"""Real pipe peers calibrate stdio identity, framing, bounds, and cleanup."""
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from protocol import ProtocolError, StdioClient

PEER = r'''
import json,sys,time
mode=sys.argv[1]
for line in sys.stdin:
 request=json.loads(line)
 if 'id' not in request: continue
 if mode=='timeout': time.sleep(5);continue
 if mode=='eof': sys.exit(0)
 if mode=='malformed': print('not json',flush=True);continue
 if mode=='oversized': print('x'*8192,flush=True);continue
 if mode=='stderr': print('e'*20000,file=sys.stderr,flush=True)
 value={'jsonrpc':'2.0','id':request['id']+(1 if mode=='wrong-id' else 0),'result':{'received':request['method']}}
 if mode=='initialize': value['result']={'protocolVersion':'2025-06-18','serverInfo':{'name':'controlled-peer','version':'1'}}
 print(json.dumps(value),flush=True)
'''


FRAMED_PEER = r'''import json,sys
while True:
 header=sys.stdin.buffer.readline()
 if not header: break
 length=int(header.split(b':',1)[1]);sys.stdin.buffer.readline()
 row=json.loads(sys.stdin.buffer.read(length))
 answer={'jsonrpc':'2.0','id':row['id'],'result':row.get('params')}
 body=json.dumps(answer,ensure_ascii=False).encode()
 if sys.argv[1]=='oversized': wire=b'Content-Length: 99999999\r\n\r\n'
 else: wire=('Content-Length: '+str(len(body))+'\r\n\r\n').encode()+body
 sys.stdout.buffer.write(wire);sys.stdout.buffer.flush()
'''


class ProtocolContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def client(self, mode, **kwargs):
        return StdioClient([sys.executable, '-u', '-c', PEER, mode], self.root / mode, **kwargs)

    def test_lsp_content_length_frames_use_utf8_byte_counts(self):
        with StdioClient([sys.executable, '-u', '-c', FRAMED_PEER, 'healthy'], self.root / 'lsp', framing='content-length') as client:
            answer = client.request('textDocument/hover', {'value': '🧪 café'})
            self.assertEqual(answer['result'], {'value': '🧪 café'})

    def test_lsp_declared_oversized_frame_is_rejected_before_body_read(self):
        with StdioClient([sys.executable, '-u', '-c', FRAMED_PEER, 'oversized'], self.root / 'lsp-bound', framing='content-length') as client:
            with self.assertRaisesRegex(ProtocolError, 'content length'):
                client.request('textDocument/hover', {})

    def test_real_peer_returns_matching_request_and_retains_evidence(self):
        with self.client('healthy') as client:
            result = client.request('tools/list')
            self.assertEqual(result['id'], 1)
            self.assertEqual(result['result'], {'received': 'tools/list'})
        rows = [json.loads(line) for line in (self.root / 'healthy/protocol.jsonl').read_text().splitlines()]
        self.assertEqual([row['direction'] for row in rows], ['send', 'receive'])
        self.assertTrue(json.loads((self.root / 'healthy/transport.json').read_text())['closed'])

    def test_foreign_response_identity_is_rejected(self):
        with self.client('wrong-id') as client:
            with self.assertRaisesRegex(ProtocolError, 'another request'):
                client.request('tools/list')

    def test_non_json_output_is_not_a_successful_empty_response(self):
        with self.client('malformed') as client:
            with self.assertRaisesRegex(ProtocolError, 'non-JSON'):
                client.request('tools/list')

    def test_oversized_message_is_rejected(self):
        with self.client('oversized', max_bytes=4096) as client:
            with self.assertRaisesRegex(ProtocolError, 'byte budget'):
                client.request('tools/list')

    def test_timeout_closes_the_owned_process(self):
        with self.client('timeout', timeout=0.1) as client:
            with self.assertRaises(TimeoutError):
                client.request('tools/list')
        self.assertIsNotNone(client.process.poll())

    def test_early_eof_is_not_a_success(self):
        with self.client('eof') as client:
            with self.assertRaisesRegex(ProtocolError, 'exited'):
                client.request('tools/list')

    def test_initialize_records_actual_server_identity(self):
        with self.client('initialize') as client:
            self.assertEqual(client.initialize()['serverInfo']['name'], 'controlled-peer')

    def test_stderr_is_drained_with_a_retained_bound(self):
        with self.assertRaisesRegex(ProtocolError, 'evidence incomplete'):
            with self.client('stderr', max_bytes=4096) as client:
                self.assertEqual(client.request('tools/list')['id'], 1)
        metadata = json.loads((self.root / 'stderr/transport.json').read_text())
        self.assertTrue(metadata['stderr_truncated'])
        self.assertEqual((self.root / 'stderr/stderr.log').stat().st_size, 4096)


if __name__ == '__main__':
    unittest.main()
