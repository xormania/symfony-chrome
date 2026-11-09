#!/usr/bin/env python3
"""Measure a declared native command, preserving failed and timed-out attempts."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import signal
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
HARNESS = 2


def summarize(samples: list[dict]) -> dict:
    if not samples:
        raise ValueError('An experiment must contain attempts')
    ids = [row['attempt'] for row in samples]
    if ids != list(range(1, len(samples) + 1)):
        raise ValueError('Attempt inventory is missing, duplicated, or out of order')
    for row in samples:
        if row['outcome'] not in {'passed', 'failed', 'timed_out', 'error', 'cancelled'}:
            raise ValueError('Unknown sample outcome')
        if not isinstance(row['seconds'], (int, float)) or not math.isfinite(row['seconds']) or row['seconds'] < 0:
            raise ValueError('Invalid sample duration')
        if row['outcome'] == 'passed' and row.get('native_exit') != 0:
            raise ValueError('Passed sample does not have a successful native exit')
    successful = [row['seconds'] for row in samples if row['outcome'] == 'passed']
    all_times = [row['seconds'] for row in samples]
    return {'attempts': len(samples), 'passed': len(successful),
            'failed': sum(row['outcome'] == 'failed' for row in samples),
            'timed_out': sum(row['outcome'] == 'timed_out' for row in samples),
            'errors': sum(row['outcome'] == 'error' for row in samples),
            'cancelled': sum(row['outcome'] == 'cancelled' for row in samples),
            'all_attempts_median_seconds': statistics.median(all_times),
            'successful_median_seconds': statistics.median(successful) if successful else None,
            'successful_min_seconds': min(successful) if successful else None,
            'successful_max_seconds': max(successful) if successful else None,
            'successful_mad_seconds': statistics.median(abs(value - statistics.median(successful))
                                                       for value in successful) if successful else None,
            'timing_gate': 'advisory', 'native_success': len(successful) == len(samples)}


def compare(current: dict, baseline: dict) -> dict:
    if current.get('measurement') != baseline.get('measurement'):
        raise ValueError('Measurement configurations differ; no timing comparison is valid')
    for value in (current, baseline):
        samples = value.get('samples', [])
        planned = value.get('measurement', {}).get('planned_attempts')
        lock_identity = value.get('measurement', {}).get('toolchain_lock_sha256', '')
        if value.get('measurement', {}).get('harness') != HARNESS or len(lock_identity) != 64 or any(char not in '0123456789abcdef' for char in lock_identity):
            raise ValueError('Measurement harness/toolchain identity is missing or incompatible')
        if value.get('schema') != 1 or type(planned) is not int or len(samples) != planned:
            raise ValueError('Experiment sample inventory is incomplete')
        actual = summarize(samples)
        if any(value.get('summary', {}).get(key) != expected for key, expected in actual.items()):
            raise ValueError('Experiment summary disagrees with retained samples')
        if not value.get('source') or value.get('source') != value.get('source_after'):
            raise ValueError('Experiment source identity is missing or changed')
    before = baseline.get('summary', {})
    after = current.get('summary', {})
    if not before.get('native_success') or not after.get('native_success') or not before.get('source_stable', True) or not after.get('source_stable', True):
        raise ValueError('A failed or partial experiment is not a successful timing baseline')
    previous = before.get('successful_median_seconds')
    value = after.get('successful_median_seconds')
    if not isinstance(previous, (int, float)) or previous <= 0 or not isinstance(value, (int, float)):
        raise ValueError('Missing/nonpositive baseline median')
    return {'median_ratio': value / previous, 'baseline_median_seconds': previous,
            'current_median_seconds': value, 'verdict': 'advisory',
            'limitation': 'Same declared measurement configuration; no claim of statistical significance'}


def experiment(argv: list[str], evidence: Path, *, label: str, runner: str, warm_state: str,
               attempts: int = 30, timeout: float = 120) -> dict:
    from runner import capture, source_identity as current_source

    if not argv or attempts < 1 or timeout <= 0:
        raise ValueError('A command, positive attempt count, and positive timeout are required')
    evidence.mkdir(parents=True, exist_ok=True)
    ledger = evidence / 'samples.jsonl'
    if ledger.exists():
        raise ValueError('Experiment evidence already exists; choose a fresh attempt directory')
    measurement = {'harness': HARNESS, 'label': label, 'runner_configuration': runner, 'planned_attempts': attempts,
                   'warm_state': warm_state, 'timeout_seconds': timeout, 'command': argv,
                   'system': platform.system(), 'architecture': platform.machine(),
                   'python': platform.python_version(), 'cpu_count': os.cpu_count(),
                   'instrumentation': 'monotonic wall time around native subprocess; output captured',
                   'instrumentation_overhead': 'not separately measured',
                   'toolchain_lock_sha256': hashlib.sha256((ROOT / 'toolchain.lock.json').read_bytes()).hexdigest(),
                   'toolchain_identity_scope': 'Declared locked inputs; actual nested scenario runtime evidence retained separately'}
    samples = []
    source_before = current_source()
    with ledger.open('x') as output:
        for attempt in range(1, attempts + 1):
            directory = evidence / f'attempt-{attempt:03}'
            directory.mkdir()
            log = directory / 'native.log'
            started = time.monotonic()
            row = {'attempt': attempt, 'started_at': datetime.now(timezone.utc).isoformat(),
                   'log': f'{directory.name}/native.log', 'native_exit': None}
            try:
                native_argv = [str(directory / 'scenario') if arg == '{attempt_evidence}' else arg for arg in argv]
                code, timed_out, truncated = capture(native_argv, directory, timeout, cwd=ROOT)
                row.update(native_exit=code, output_truncated=truncated,
                           outcome='timed_out' if timed_out else 'error' if truncated else 'passed' if code == 0 else 'failed')
            except (KeyboardInterrupt, InterruptedError) as exc:
                log.touch(exist_ok=True)
                row.update(outcome='cancelled', detail=str(exc), output_truncated=False)
            except OSError as exc:
                log.touch(exist_ok=True)
                row.update(outcome='error', detail=str(exc), output_truncated=False)
            row['seconds'] = time.monotonic() - started
            row['output_bytes'] = log.stat().st_size
            row['log_sha256'] = hashlib.sha256(log.read_bytes()).hexdigest()
            samples.append(row)
            output.write(json.dumps(row) + '\n')
            output.flush()
            os.fsync(output.fileno())
            if row['outcome'] == 'cancelled':
                break
    source_after = current_source()
    result = {'schema': 1, 'measurement': measurement, 'source': source_before,
              'source_after': source_after, 'samples': samples, 'summary': summarize(samples)}
    result['summary']['source_stable'] = source_before == source_after
    (evidence / 'performance.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    def interrupted(signum, frame):
        raise InterruptedError('Performance execution interrupted by signal ' + str(signum))

    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--label', required=True)
    parser.add_argument('--runner', required=True, help='Named runner configuration, separate local and hosted populations')
    parser.add_argument('--warm-state', choices=['cold', 'warm', 'unspecified'], default='unspecified')
    parser.add_argument('--attempts', type=int, default=30)
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    evidence = args.evidence.resolve()
    # Claim this invocation's output before any handler may write checks. The
    # shared runner can already own native.log in an otherwise fresh directory.
    try:
        evidence.mkdir(parents=True, exist_ok=True)
        outputs = {'samples.jsonl', 'performance.json', 'comparison.json', 'summary.md', 'checks.json'}
        if any(path.name in outputs or path.name.startswith('attempt-') for path in evidence.iterdir()):
            raise FileExistsError('Experiment evidence already exists; choose a fresh attempt directory')
        (evidence / '.performance-owner').touch(exist_ok=False)
    except OSError as exc:
        print(f'Cannot claim performance evidence: {exc}', file=sys.stderr)
        return 1
    checks = []
    try:
        result = experiment(command, evidence, label=args.label, runner=args.runner,
                            warm_state=args.warm_state, attempts=args.attempts, timeout=args.timeout)
        success = result['summary']['native_success'] and result['summary']['source_stable']
        checks.append({'id': 'performance.native-attempts', 'outcome': 'passed' if success else 'failed',
                       'assertions': len(result['samples']), 'detail': json.dumps(result['summary'])})
        if args.baseline:
            comparison = compare(result, json.loads(args.baseline.read_text()))
            (evidence / 'comparison.json').write_text(json.dumps(comparison, indent=2) + '\n')
        summary = result['summary']
        (evidence / 'summary.md').write_text(
            f"# {args.label}\n\n{summary['passed']}/{summary['attempts']} native attempts passed. "
            f"Failures: {summary['failed']}; timeouts: {summary['timed_out']}; errors: {summary['errors']}; "
            f"cancelled: {summary['cancelled']}.\n\n"
            f"Successful median: {summary['successful_median_seconds']} s; MAD: {summary['successful_mad_seconds']} s. "
            "Timing is advisory. Every attempt is retained in samples.jsonl.\n")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        evidence.mkdir(parents=True, exist_ok=True)
        checks.append({'id': 'performance.execution', 'outcome': 'error', 'assertions': 0, 'detail': str(exc)})
    (evidence / 'checks.json').write_text(json.dumps({'schema': 1, 'checks': checks}, indent=2) + '\n')
    return 0 if checks and all(row['outcome'] == 'passed' for row in checks) else 1


if __name__ == '__main__':
    sys.exit(main())
