"""Native PHP HTTP regression: public/lab assets must not shadow Symfony /lab routes."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = Path(os.environ.get('CONSUMER_TEST_ROOT', Path(__file__).resolve().parents[2]))
spec = importlib.util.spec_from_file_location('consumer', ROOT / 'tools/testing/consumer.py')
consumer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(consumer)


class NativeHttpRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('php'):
            raise RuntimeError('Native HTTP regression requires PHP; it cannot be skipped as a pass')
        cls.temporary = tempfile.TemporaryDirectory(prefix='symfony-chrome-router-')
        cls.process = None
        cls.log = None
        cls.addClassCleanup(cls.cleanup)
        cls.checkout = Path(cls.temporary.name)
        public = cls.checkout / 'demo/public'
        (public / 'lab').mkdir(parents=True)
        # Reproduce the pinned UXor filesystem boundary: public/lab/slow.css and a front controller.
        (public / 'lab/slow.css').write_text('body { color: green; }\n')
        (public / 'index.php').write_text(
            '<?php header("Content-Type: application/json"); echo json_encode(['
            '"front_controller" => true, "uri" => $_SERVER["REQUEST_URI"]]);')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            cls.port = listener.getsockname()[1]
        cls.log = (cls.checkout / 'server.log').open('w')
        cls.process = subprocess.Popen(shlex.split(consumer.web_server_command(cls.port)),
            cwd=cls.checkout, stdout=cls.log, stderr=subprocess.STDOUT,
            env={key: value for key, value in os.environ.items() if key != 'PHP_CLI_SERVER_WORKERS'})
        cls.url = f'http://127.0.0.1:{cls.port}'
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if cls.process.poll() is not None:
                raise RuntimeError('PHP server exited before the regression request')
            try:
                with urllib.request.urlopen(cls.url + '/lab/slow.css', timeout=0.5):
                    break
            except (urllib.error.URLError, OSError):
                time.sleep(0.02)
        else:
            raise RuntimeError('PHP server did not start')

    @classmethod
    def cleanup(cls):
        if cls.process is not None:
            cls.process.terminate()
            try:
                cls.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.process.kill()
                cls.process.wait(timeout=5)
        if cls.log is not None:
            cls.log.close()
        cls.temporary.cleanup()

    def test_lab_route_beneath_existing_public_directory_reaches_front_controller(self):
        with urllib.request.urlopen(self.url + '/lab/live-modal', timeout=2) as response:
            data = json.load(response)
        self.assertEqual({'front_controller': True, 'uri': '/lab/live-modal'}, data)

    def test_static_css_remains_a_static_response(self):
        with urllib.request.urlopen(self.url + '/lab/slow.css', timeout=2) as response:
            self.assertEqual(b'body { color: green; }\n', response.read())

    def test_missing_route_uses_front_controller(self):
        with urllib.request.urlopen(self.url + '/application-route', timeout=2) as response:
            self.assertTrue(json.load(response)['front_controller'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
