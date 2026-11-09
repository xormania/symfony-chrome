"""Local/CI suite runner: native outcomes, selected identities and retained attempts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
LOG_LIMIT = 8 * 1024 * 1024


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def validate_report(plan, report):
    """Return acceptance errors; a native zero alone never establishes a pass."""
    errors = []
    if not isinstance(plan, dict) or not isinstance(report, dict):
        return ['plan and report must be objects']
    if type(plan.get('schema')) is not int or plan.get('schema') != 1 or type(report.get('schema')) is not int or report.get('schema') != 1:
        errors.append('Unknown schema; expected version 1')
    for key in ('schema', 'run_id', 'attempt_id', 'source'):
        if key not in plan or report.get(key) != plan[key]:
            errors.append(f'{key}: missing or foreign identity')
    selected = plan.get('selected')
    if not isinstance(selected, list) or not selected or any(not isinstance(x, str) for x in selected):
        return errors + ['selection must contain suite identities']
    if len(selected) != len(set(selected)):
        errors.append('duplicate suite selection')
    results = report.get('results')
    if not isinstance(results, list):
        return errors + ['results missing']
    ids = [x.get('suite_id') for x in results if isinstance(x, dict)]
    if len(ids) != len(results) or any(not isinstance(x, str) for x in ids) or len(set(str(x) for x in ids)) != len(ids) or set(str(x) for x in ids) != set(selected):
        errors.append('missing, duplicate or unexpected suite result')
    if 'source_after' in report and report['source_after'] != plan.get('source'):
        errors.append('Relevant source inputs changed during execution')
    for row in results:
        if not isinstance(row, dict):
            errors.append('invalid result row')
            continue
        suite = row.get('suite_id')
        if not isinstance(suite, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,79}', suite):
            errors.append('Invalid suite identity')
            continue
        if row.get('timed_out', False) is not False or row.get('truncated', False) is not False:
            errors.append(f'{suite}: timeout or truncated execution')
        if type(row.get('native_exit')) is not int or row.get('native_exit') != 0 or row.get('outcome') != 'passed':
            errors.append(f'{suite}: native failure or incomplete execution')
        checks = row.get('checks')
        if not isinstance(checks, list) or not checks:
            errors.append(f'{suite}: no executed assertions')
            continue
        check_ids = []
        for check in checks:
            if not isinstance(check, dict):
                errors.append(f'{suite}: invalid check')
                continue
            check_id = check.get('id')
            if not isinstance(check_id, str) or not check_id:
                errors.append(f'{suite}: missing check identity')
            check_ids.append(check_id)
            if check.get('outcome') != 'passed' or type(check.get('assertions')) is not int or check['assertions'] < 1:
                errors.append(f'{suite}/{check_id}: assertion failed, skipped or not executed')
        if len(set(str(x) for x in check_ids)) != len(check_ids):
            errors.append(f'{suite}: duplicate check identity')
        expected = plan.get('expected_checks', {}).get(suite)
        if expected is not None and (not isinstance(expected, list) or set(str(x) for x in check_ids) != set(str(x) for x in expected)):
            errors.append(f'{suite}: missing or unexpected check identities')
    return errors


def manifest():
    value = json.loads((ROOT / 'tests/manifest.json').read_text())
    if value.get('schema') != 1 or not isinstance(value.get('suites'), dict):
        raise ValueError('invalid test manifest')
    return value


def select(config, suites=(), scenario=None, profile=None):
    if scenario:
        names = [name for name, entry in config['suites'].items() if scenario in entry.get('checks', [])]
        if len(names) != 1:
            raise ValueError('scenario must identify exactly one suite; zero matches are not acceptance')
    elif profile:
        if profile not in config.get('profiles', {}):
            raise ValueError(f'Unknown profile {profile!r}')
        names = config['profiles'][profile]
    else:
        names = list(suites)
    names = list(dict.fromkeys(names))
    if not names or any(name not in config['suites'] for name in names):
        raise ValueError('Unknown or empty test selection')
    return names


def source_identity():
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    # Hash relevant bytes, including uncommitted/untracked source, without storing diffs.
    paths = sorted(set(git('ls-files', '--cached', '--others', '--exclude-standard').splitlines()))
    digest = hashlib.sha256()
    for name in paths:
        path = ROOT / name
        digest.update(name.encode() + b'\0')
        if path.is_symlink():
            digest.update(b'<symlink>' + os.readlink(path).encode())
        elif path.is_file():
            digest.update(path.read_bytes())
        else:
            digest.update(b'<missing>')
    return {'commit': git('rev-parse', 'HEAD'), 'dirty': bool(git('status', '--porcelain')),
            'inputs_sha256': digest.hexdigest()}


def terminate(process):
    # The session can outlive its parent; kill its group even after parent exit.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def capture(command, directory, timeout, cwd=None, env=None):
    """The deadline covers parent, descendants, and output draining."""
    process = subprocess.Popen(command, cwd=cwd or ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               start_new_session=True)
    truncated = threading.Event()
    def pump():
        remaining = LOG_LIMIT
        with (directory / 'native.log').open('wb') as stream:
            while True:
                chunk = process.stdout.read(65536)
                if not chunk:
                    break
                stream.write(chunk[:remaining])
                overflow = len(chunk) > remaining
                remaining = max(0, remaining - len(chunk))
                if overflow:
                    truncated.set()
                    terminate(process)
                    break
    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    timed_out = False
    deadline = time.monotonic() + timeout
    try:
        while process.poll() is None or thread.is_alive():
            if time.monotonic() >= deadline:
                timed_out = True
                terminate(process)
                break
            time.sleep(0.02)
    except BaseException:
        terminate(process)
        raise
    finally:
        thread.join(timeout=3)
        process.stdout.close()
    native_exit = process.returncode
    terminate(process)
    return native_exit, timed_out, truncated.is_set()


def artifacts(directory):
    rows = []
    total = 0
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise ValueError('artifact symlinks are not allowed')
        if path.is_file():
            total += path.stat().st_size
            if total > 64 * 1024 * 1024:
                raise ValueError('Suite evidence exceeds 64 MiB; workspaces/dependencies must remain outside artifacts')
            data = path.read_bytes()
            rows.append({'path': path.relative_to(directory.parent).as_posix(), 'size': len(data),
                         'sha256': hashlib.sha256(data).hexdigest()})
    return rows


def verify_artifacts(directory, report):
    errors = []
    for row in report.get('results', []):
        suite = row['suite_id']
        inventory = row.get('artifacts', [])
        paths = [item.get('path') for item in inventory]
        required = {suite + '/native.log', suite + '/checks.json'}
        if not required.issubset(paths) or len(paths) != len(set(paths)):
            errors.append('required native evidence missing or duplicated: ' + suite)
        native_path = directory / suite / 'checks.json'
        try:
            native = json.loads(native_path.read_text())
            if native.get('schema') != 1 or native.get('checks') != row.get('checks'):
                errors.append('native and normalized checks disagree: ' + suite)
        except (OSError, ValueError):
            errors.append('invalid native evidence: ' + suite)
        for artifact in inventory:
            path = directory / artifact['path']
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()) or not path.is_file():
                errors.append('artifact missing or outside attempt')
                continue
            data = path.read_bytes()
            if len(data) != artifact.get('size') or hashlib.sha256(data).hexdigest() != artifact.get('sha256'):
                errors.append('artifact content changed: ' + artifact['path'])
    return errors


def run_suites(args):
    config = manifest()
    names = select(config, args.suite, args.scenario, args.profile)
    run_id = args.run or 'test-' + uuid.uuid4().hex[:16]
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', run_id):
        raise ValueError('Invalid run id')
    attempt_id = uuid.uuid4().hex
    directory = ROOT / 'artifacts' / run_id / attempt_id
    directory.mkdir(parents=True, exist_ok=False)
    plan = {'schema': 1, 'run_id': run_id, 'attempt_id': attempt_id, 'source': source_identity(),
            'selected': names, 'expected_checks': {name: config['suites'][name]['checks'] for name in names},
            'started_at': time.time(), 'github_run': os.environ.get('GITHUB_RUN_ID'),
            'github_attempt': os.environ.get('GITHUB_RUN_ATTEMPT')}
    write_json(directory / 'plan.json', plan)
    results = []
    for name in names:
        entry = config['suites'][name]
        evidence = directory / name
        evidence.mkdir()
        started = time.monotonic()
        row = {'suite_id': name, 'outcome': 'error', 'native_exit': None, 'checks': []}
        try:
            command = [sys.executable, entry['script'], '--evidence', str(evidence)]
            code, timed_out, truncated = capture(command, evidence, entry.get('timeout', 900))
            row.update(native_exit=code, timed_out=timed_out, truncated=truncated)
            native = json.loads((evidence / 'checks.json').read_text())
            if native.get('schema') != 1:
                raise ValueError('Unknown native check schema')
            row['checks'] = native['checks']
            row['outcome'] = 'passed' if code == 0 and not timed_out and not truncated else 'failed'
        except Exception as exc:
            row['detail'] = str(exc)
        row['duration_seconds'] = time.monotonic() - started
        try:
            row['artifacts'] = artifacts(evidence)
        except (OSError, ValueError) as exc:
            row.update(outcome='error', detail=str(exc), artifacts=[])
        results.append(row)
    report = {key: plan[key] for key in ('schema', 'run_id', 'attempt_id', 'source')}
    report.update(results=results, ended_at=time.time())
    errors = validate_report(plan, report)
    if not errors:
        errors += verify_artifacts(directory, report)
    report['source_after'] = source_identity()
    if report['source_after'] != plan['source']:
        errors.append('Relevant source inputs changed during execution')
    report['errors'] = errors
    write_json(directory / 'results.json', report)
    write_json(directory.parent / 'latest.json', {'attempt_id': attempt_id})
    summary = f"Run {run_id}, attempt {attempt_id}: {'FAIL' if errors else 'PASS'}\n"
    summary += '\n'.join(f"- {x['suite_id']}: {x['outcome']} ({x['duration_seconds']:.2f}s)" for x in results)
    summary += '\n' + '\n'.join(errors) + '\n'
    (directory / 'summary.md').write_text(summary)
    print(summary)
    print(f'Evidence: {directory}')
    return 1 if errors else 0


def report_run(run_id):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', run_id):
        raise ValueError('Invalid run id')
    root = ROOT / 'artifacts' / run_id
    attempt = json.loads((root / 'latest.json').read_text())['attempt_id']
    if not re.fullmatch(r'[a-f0-9]{32}', attempt):
        raise ValueError('Invalid attempt identity')
    directory = root / attempt
    plan = json.loads((directory / 'plan.json').read_text())
    report = json.loads((directory / 'results.json').read_text())
    if plan.get('run_id') != run_id or plan.get('attempt_id') != attempt:
        raise ValueError('Foreign run or attempt stored at requested evidence path')
    errors = validate_report(plan, report)
    if not errors:
        errors += verify_artifacts(directory, report)
    print(json.dumps({'run_id': run_id, 'attempt_id': attempt, 'errors': errors}, indent=2))
    return 1 if errors else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', action='append', default=[])
    parser.add_argument('--profile')
    parser.add_argument('--scenario')
    parser.add_argument('--run')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        if sys.flags.optimize or os.environ.get('PYTHONOPTIMIZE', '') not in ('', '0'):
            raise ValueError('Optimized Python disables contract assertions; unset PYTHONOPTIMIZE for acceptance')
        if args.list:
            print(json.dumps(manifest(), indent=2))
            return 0
        return run_suites(args)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f'test runner: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
