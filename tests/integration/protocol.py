"""Bounded newline-delimited JSON-RPC client for real stdio MCP servers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import threading
import time


class ProtocolError(RuntimeError):
    pass


class StdioClient:
    def __init__(self, argv, evidence, *, timeout=60, max_bytes=8 * 1024 * 1024, env=None, framing='newline', cwd=None):
        self.directory = Path(evidence)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.timeout, self.max_bytes = timeout, max_bytes
        assert framing in ('newline', 'content-length')
        self.framing = framing
        self.counter, self.total, self.buffer = 0, 0, b''
        self.log = (self.directory / 'protocol.jsonl').open('xb')
        self.stderr = (self.directory / 'stderr.log').open('xb')
        self.stderr_bytes, self.stderr_truncated = 0, False
        try:
            self.process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, start_new_session=True, env=env, cwd=cwd)
        except BaseException:
            self.log.close()
            self.stderr.close()
            raise
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.drain = threading.Thread(target=self._drain_stderr, daemon=True)
        self.drain.start()

    def _drain_stderr(self):
        while chunk := self.process.stderr.read(4096):
            remaining = max(0, self.max_bytes - self.stderr_bytes)
            self.stderr.write(chunk[:remaining])
            self.stderr_bytes += min(remaining, len(chunk))
            self.stderr_truncated |= len(chunk) > remaining

    def _record(self, direction, message):
        data = (json.dumps({'direction': direction, 'message': message}, ensure_ascii=True) + '\n').encode()
        self.total += len(data)
        if self.total > self.max_bytes:
            raise ProtocolError('Protocol evidence exceeds its byte budget; result is incomplete')
        self.log.write(data)
        self.log.flush()

    def _write(self, message):
        payload = json.dumps(message).encode()
        wire = payload + b'\n' if self.framing == 'newline' else f'Content-Length: {len(payload)}\r\n\r\n'.encode() + payload
        self.process.stdin.write(wire)
        self.process.stdin.flush()

    def _extract(self):
        if self.framing == 'newline':
            if b'\n' not in self.buffer:
                return None
            line, self.buffer = self.buffer.split(b'\n', 1)
            return line
        marker = self.buffer.find(b'\r\n\r\n')
        if marker < 0:
            if len(self.buffer) > 8192:
                raise ProtocolError('LSP header exceeds byte budget')
            return None
        headers = self.buffer[:marker].decode('ascii').split('\r\n')
        lengths = [int(row.split(':', 1)[1].strip()) for row in headers if row.lower().startswith('content-length:')]
        if len(lengths) != 1 or not 0 < lengths[0] <= self.max_bytes:
            raise ProtocolError('Invalid/bounded LSP content length')
        end = marker + 4 + lengths[0]
        if len(self.buffer) < end:
            return None
        body, self.buffer = self.buffer[marker + 4:end], self.buffer[end:]
        return body

    def notify(self, method, params=None):
        message = {'jsonrpc': '2.0', 'method': method}
        if params is not None:
            message['params'] = params
        self._record('send', message)
        self._write(message)

    def request(self, method, params=None):
        self.counter += 1
        identity = self.counter
        message = {'jsonrpc': '2.0', 'id': identity, 'method': method}
        if params is not None:
            message['params'] = params
        self._record('send', message)
        self._write(message)
        deadline = time.monotonic() + self.timeout
        while True:
            while (line := self._extract()) is not None:
                if not line.strip():
                    continue
                try:
                    answer = json.loads(line)
                except (ValueError, UnicodeDecodeError) as exc:
                    raise ProtocolError('Server emitted non-JSON protocol output') from exc
                self._record('receive', answer)
                if not isinstance(answer, dict) or answer.get('jsonrpc') != '2.0':
                    raise ProtocolError('Malformed JSON-RPC envelope')
                if 'method' in answer:
                    if 'id' in answer:
                        if self.framing == 'newline' and answer['method'] != 'ping':
                            raise ProtocolError('Unexpected server request: ' + str(answer['method']))
                        reply = {'jsonrpc': '2.0', 'id': answer['id'], 'result': {} if answer['method'] == 'ping' else None}
                        self._record('send', reply)
                        self._write(reply)
                    continue
                if answer.get('id') != identity:
                    raise ProtocolError('Response belongs to another request')
                if ('result' in answer) == ('error' in answer):
                    raise ProtocolError('Response must contain exactly one of result/error')
                return answer
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('MCP request timed out: ' + method)
            if not self.selector.select(remaining):
                raise TimeoutError('MCP request timed out: ' + method)
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise ProtocolError('MCP server exited before answering ' + method)
            self.buffer += chunk
            if len(self.buffer) > self.max_bytes:
                raise ProtocolError('Protocol message exceeds its byte budget')

    def initialize(self):
        response = self.request('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                             'clientInfo': {'name': 'symfony-chrome-contract', 'version': '1'}})
        if 'error' in response:
            raise ProtocolError('MCP initialize rejected: ' + json.dumps(response['error']))
        result = response['result']
        if not result.get('protocolVersion') or not isinstance(result.get('serverInfo'), dict):
            raise ProtocolError('MCP initialize omitted server identity')
        self.notify('notifications/initialized')
        return result

    def call(self, name, arguments):
        return self.request('tools/call', {'name': name, 'arguments': arguments})

    def close(self):
        try:
            if self.process.stdin and not self.process.stdin.closed:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGTERM)
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=3)
        finally:
            # A child may outlive a peer that already exited; this group belongs
            # to this transport, never an independently owned attached browser.
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.selector.close()
            self.drain.join(timeout=3)
            self.process.stdout.close()
            self.process.stderr.close()
            self.log.close()
            self.stderr.close()
            (self.directory / 'transport.json').write_text(json.dumps({
                'schema': 1, 'pid': self.process.pid, 'exit': self.process.returncode,
                'protocol_bytes': self.total, 'stderr_bytes': self.stderr_bytes,
                'stderr_truncated': self.stderr_truncated, 'closed': self.process.poll() is not None,
            }, indent=2) + '\n')
            if self.stderr_truncated:
                raise ProtocolError('Server stderr exceeded diagnostic budget; evidence incomplete')

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        try:
            self.close()
        except Exception as cleanup:
            if error is None:
                raise
            error.add_note('Transport cleanup also failed: ' + str(cleanup))
        return False


def text_of(response):
    if 'error' in response:
        raise ProtocolError('MCP error: ' + json.dumps(response['error']))
    result = response['result']
    if result.get('isError'):
        raise ProtocolError('Tool rejected invocation: ' + json.dumps(result))
    return '\n'.join(row['text'] for row in result.get('content', []) if row.get('type') == 'text')
