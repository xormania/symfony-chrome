"""Shared provisioning and native check records for integration suites."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import time
import uuid
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPRedirectHandler, Request, urlopen

if not __debug__:
    raise RuntimeError('Contract assertions require Python optimization to be disabled')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bin'))
from devlib import execute, host_port, load, prepare, require_running, start, stop


class ContractCancelled(BaseException):
    """Cancellation must bypass ordinary provider/filesystem exception handlers."""


class Checks:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.rows = []
        self.context = {}

    def check(self, identity, function):
        started = time.monotonic()
        try:
            detail, assertions = function()
            row = {'id': identity, 'outcome': 'passed', 'assertions': assertions, 'detail': detail}
        except (ContractCancelled, InterruptedError):
            # Cancellation must unwind the owned workspace immediately, rather
            # than continue to the next potentially expensive contract.
            raise
        except Exception as exc:
            row = {'id': identity, 'outcome': 'failed' if isinstance(exc, AssertionError) else 'error',
                   'assertions': 0, 'detail': type(exc).__name__ + ': ' + str(exc)[-4000:]}
        row['duration_s'] = time.monotonic() - started
        self.rows.append(row)
        self.save()
        return row['outcome'] == 'passed'

    def save(self, **metadata):
        self.context.update(metadata)
        (self.directory / 'checks.json').write_text(json.dumps({'schema': 1, 'checks': self.rows, **self.context}, indent=2) + '\n')

    def exit(self):
        return 0 if self.rows and all(row['outcome'] == 'passed' for row in self.rows) else 1


def install_contract_fixture(data):
    app = Path(data['app'])
    source = ROOT / 'tests/fixtures/integration'
    (app / 'src/Ci').mkdir(parents=True, exist_ok=True)
    for name in ('ContractTransport.php', 'LoopbackTransport.php', 'BindingProbe.php'):
        shutil.copy2(source / name, app / 'src/Ci' / name)
    shutil.copy2(source / 'ContractController.php', app / 'src/Controller/ContractController.php')
    config = app / 'config/services.yaml'
    original = config.read_text()
    # Append to the existing top-level services mapping, not another services key.
    original += '\n    App\\Ci\\BindingProbe:\n        public: true\n    App\\Ci\\LoopbackTransport:\n        public: true\n    App\\Ci\\ContractTransport:\n        alias: App\\Ci\\LoopbackTransport\n        public: true\n'
    config.write_text(original)


@contextmanager
def termination_handler():
    """Turn parent timeout cancellation into normal owned-resource unwinding."""
    previous = signal.getsignal(signal.SIGTERM)
    interrupted = False
    def terminate(number, frame):
        nonlocal interrupted
        # A repeated termination request must not bypass an in-progress cleanup.
        # The parent retains its bounded SIGKILL fallback if cleanup stalls.
        if not interrupted:
            interrupted = True
            raise ContractCancelled('Received SIGTERM; cleaning owned integration resources')
    signal.signal(signal.SIGTERM, terminate)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


@contextmanager
def workspace():
    # Only freshly owned disposable applications receive the test-only routes.
    data = prepare('contract-' + uuid.uuid4().hex[:12])
    with termination_handler():
        primary = None
        try:
            # Bootstrap and the first HTTP readiness request must see the final
            # fixture. Mutating routes after PHP starts can leave its live
            # router/container using the preceding application snapshot.
            install_contract_fixture(data)
            start(data, build=False)
            yield data
        except BaseException as exc:
            primary = exc
            raise
        finally:
            cleanup = {'run_id': data['run_id'], 'outcome': 'passed'}
            try:
                stop(data, purge=True)
            except BaseException as exc:
                cleanup.update(outcome='error', detail=str(exc))
                if primary is not None:
                    primary.add_note('Cleanup also failed: ' + str(exc))
                else:
                    raise
            finally:
                (Path(data['evidence']) / 'contract-cleanup.json').write_text(json.dumps(cleanup, indent=2) + '\n')


def http(base, path, *, redirects=True):
    request = Request(base + path)
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *_):
            return None
    try:
        response = urlopen(request, timeout=30) if redirects else build_opener(NoRedirect).open(request, timeout=30)
    except HTTPError as exc:
        response = exc
    with response:
        body = response.read(1024 * 1024 + 1)
        assert len(body) <= 1024 * 1024, 'HTTP diagnostic budget exceeded'
        return {'url': response.url, 'status': response.status,
                'token': response.headers.get('X-Debug-Token'), 'body': body.decode()}


def verify_join(response, profile, marker):
    assert response['status'] == 200 and json.loads(response['body'])['marker'] == marker
    token = response['token']
    assert isinstance(token, str) and len(token) == 6 and all(c in '0123456789abcdef' for c in token)
    assert profile['available'] is True and profile['token'] == token, 'Response/profile token mismatch'
    assert marker in profile['url'] and profile['method'] == 'GET' and profile['status'] == 200, 'Profile belongs to another request'


def correlation(data, evidence):
    base = 'http://127.0.0.1:' + host_port(data)
    markers = ['join-' + uuid.uuid4().hex for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda marker: http(base, '/_ci/observe?marker=' + marker), markers))
    profiles = [json.loads(http(base, '/_ci/profile/' + row['token'])['body']) for row in responses]
    for row, profile, marker in zip(responses, profiles, markers):
        verify_join(row, profile, marker)
    assert responses[0]['token'] != responses[1]['token'], 'Requests reused one profile identity'
    try:
        verify_join(responses[0], profiles[1], markers[0])
    except AssertionError:
        pass
    else:
        raise AssertionError('Swapped request profiles escaped the independent oracle')
    missing = http(base, '/_ci/profile/000000')
    assert missing['status'] == 404 and json.loads(missing['body'])['available'] is False
    redirect = http(base, '/_ci/redirect?marker=' + markers[0], redirects=False)
    assert redirect['status'] == 302 and redirect['token'], 'Redirect response identity absent'
    redirect_profile = json.loads(http(base, '/_ci/profile/' + redirect['token'])['body'])
    assert redirect_profile['token'] == redirect['token'] and redirect_profile['status'] == 302 and markers[0] in redirect_profile['url'], 'Redirect profile belongs to another response'
    (Path(evidence) / 'correlation.json').write_text(json.dumps({'responses': responses, 'profiles': profiles,
        'missing_profile': missing, 'redirect': redirect, 'redirect_profile': redirect_profile, 'parallelism_claim': 'two outstanding clients, no claim of backend parallelism'}, indent=2) + '\n')
    return 'Two response tokens independently joined; swapped identity rejected; missing and redirect cases preserved', 13
