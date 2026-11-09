"""Bounded native process capture shared by development tooling and CI workers."""
from __future__ import annotations

import json
import locale
import math
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

LOG_LIMIT = 8 * 1024 * 1024
DEFAULT_TIMEOUT = 180
SUITE_DEADLINE = 'SYMFONY_CHROME_TEST_DEADLINE'
CLEANUP_GRACE = 20


class NativeCaptureError(RuntimeError):
    def __init__(self, metadata, path):
        self.native_exit = metadata['native_exit']
        self.timed_out = metadata['timed_out']
        self.truncated = metadata['truncated']
        self.metadata = metadata
        reason = 'deadline' if self.timed_out else 'aggregate output budget'
        super().__init__(f'Native capture exceeded its {reason}; retained status: {path}')


def terminate(process):
    """The owned session can outlive its original process and retain pipe writers."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=CLEANUP_GRACE)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def capture(command, directory, timeout, cwd=None, env=None, *, separate=False,
            limit=LOG_LIMIT, metadata_path=None, visibility='caller_owned', **popen_kwargs):
    """Drain bounded streams without buffering the producer's arbitrary output in RAM.

    The byte budget is aggregate across stdout/stderr. The deadline includes
    descendant pipe writers after a parent exits. The legacy merged native.log
    mode remains the suite runner's default; JSON clients select separate files.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    metadata_path = Path(metadata_path) if metadata_path else directory / 'native-capture.json'
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    timeout = float(timeout)
    if not math.isfinite(timeout) or timeout < 0 or type(limit) is not int or limit < 1:
        raise ValueError('Native capture requires a finite deadline and positive byte budget')
    paths = {'stdout': directory / ('stdout' if separate else 'native.log')}
    if separate:
        paths['stderr'] = directory / 'stderr'
    for path in paths.values():
        path.write_bytes(b'')
    started = time.monotonic()
    state = {'native_exit': None, 'timed_out': timeout == 0, 'truncated': False,
             'limit_bytes': limit, 'timeout_seconds': timeout,
             'retained_bytes': {name: 0 for name in paths}, 'observed_bytes_lower_bound': 0,
             'log_visibility': visibility,
             'log_lifecycle': 'purged_with_workspace' if visibility == 'private_ephemeral' else 'caller_owned_retained'}
    process = None
    threads = []
    overflow = threading.Event()
    lock = threading.Lock()
    errors = []
    remaining = limit

    def pump(name, pipe):
        nonlocal remaining
        try:
            with paths[name].open('wb') as output:
                while True:
                    chunk = pipe.read(65536)
                    if not chunk:
                        return
                    with lock:
                        state['observed_bytes_lower_bound'] += len(chunk)
                        retained = chunk[:remaining]
                        output.write(retained)
                        state['retained_bytes'][name] += len(retained)
                        remaining -= len(retained)
                        if len(retained) != len(chunk):
                            overflow.set()
                            return
        except BaseException as exc:
            with lock:
                errors.append(exc)

    try:
        if timeout == 0:
            return None, True, False
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE if separate else subprocess.STDOUT,
                                   start_new_session=True, **popen_kwargs)
        for name in paths:
            pipe = process.stdout if name == 'stdout' else process.stderr
            thread = threading.Thread(target=pump, args=(name, pipe), daemon=True)
            threads.append(thread)
            thread.start()
        deadline = started + timeout
        while process.poll() is None or any(thread.is_alive() for thread in threads):
            if overflow.is_set() or errors:
                terminate(process)
                break
            if time.monotonic() >= deadline:
                state['timed_out'] = True
                terminate(process)
                break
            time.sleep(0.02)
        if errors:
            raise OSError('Native output capture failed') from errors[0]
    except BaseException as exc:
        state['capture_error'] = type(exc).__name__
        if process is not None:
            terminate(process)
        raise
    finally:
        for thread in threads:
            thread.join(timeout=3)
        if process is not None:
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
            state['native_exit'] = process.returncode
            terminate(process)
        state['truncated'] = overflow.is_set()
        state['duration_seconds'] = time.monotonic() - started
        metadata_path.write_text(json.dumps(state, indent=2) + '\n')
    return state['native_exit'], state['timed_out'], state['truncated']


def run_captured(args, evidence, *, check=False, text=None, encoding=None, errors=None,
                 timeout=DEFAULT_TIMEOUT, cwd=None, env=None, metadata_path=None,
                 visibility='caller_owned', capture_output=True, **kwargs):
    """Return bounded CompletedProcess streams; incomplete capture always raises.

    check=False permits a genuine native nonzero result, never incomplete output.
    No argv or payload is added to public metadata by this shared helper.
    """
    if not capture_output or any(kwargs.get(name) is not None for name in ('stdout', 'stderr')):
        raise ValueError('run_captured owns stdout/stderr; use the streaming path otherwise')
    kwargs.pop('stdout', None)
    kwargs.pop('stderr', None)
    universal = kwargs.pop('universal_newlines', None)
    if text is not None and universal is not None and bool(text) != bool(universal):
        raise ValueError('text and universal_newlines disagree')
    text_mode = bool(text or universal or encoding is not None or errors is not None)
    effective = DEFAULT_TIMEOUT if timeout is None else float(timeout)
    parent_environment = os.environ if env is None else env
    deadline = parent_environment.get(SUITE_DEADLINE)
    if deadline is not None:
        deadline = float(deadline)
        if not math.isfinite(deadline):
            raise ValueError('Suite deadline must be finite')
        remaining = deadline - time.monotonic() - CLEANUP_GRACE
        effective = max(0.0, min(effective, remaining))
    code, timed_out, truncated = capture(args, evidence, effective, cwd=cwd, env=env,
        separate=True, metadata_path=metadata_path, visibility=visibility, **kwargs)
    status_path = Path(metadata_path) if metadata_path else Path(evidence) / 'native-capture.json'
    if timed_out or truncated:
        raise NativeCaptureError(json.loads(status_path.read_text()), status_path)
    stdout = (Path(evidence) / 'stdout').read_bytes()
    stderr = (Path(evidence) / 'stderr').read_bytes()
    if text_mode:
        decode = encoding or locale.getpreferredencoding(False)
        stdout = stdout.decode(decode, errors or 'strict').replace('\r\n', '\n').replace('\r', '\n')
        stderr = stderr.decode(decode, errors or 'strict').replace('\r\n', '\n').replace('\r', '\n')
    result = subprocess.CompletedProcess(args, code, stdout, stderr)
    if check:
        result.check_returncode()
    return result
