"""Verify required job conclusions and their downloaded native execution evidence."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/testing'))
from runner import validate_report, verify_artifacts  # noqa: E402

MANIFEST_PATH = ROOT / 'tests/manifest.json'
BASE_JOBS = {'fast', 'package', 'integration'}
FOUNDATION_SUITES = {'fast': ['fast'], 'package': ['package'], 'integration': ['support', 'environment']}


def read_object(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('missing, linked, or oversized JSON evidence')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('JSON evidence must be an object')
    return value


def validate_jobs(jobs, evidence_root, expected_suites, source_sha, run_id, run_attempt):
    """Return errors; every required job, suite, assertion, and artifact must agree."""
    errors = []
    if (not isinstance(expected_suites, dict) or not BASE_JOBS.issubset(expected_suites) or
            any(not isinstance(job, str) or not job for job in expected_suites)):
        return errors + ['Invalid required job/suite mapping']
    required_jobs = set(expected_suites)
    if not isinstance(jobs, dict) or set(jobs) != required_jobs:
        errors.append('Job conclusions must name exactly the expected required jobs')
    if not source_sha or not run_id or not run_attempt:
        return errors + ['Missing current source or workflow identity']
    try:
        manifest = read_object(MANIFEST_PATH)
        if type(manifest.get('schema')) is not int or manifest['schema'] != 1:
            raise ValueError('unknown manifest schema')
        definitions = manifest['suites']
        selected_all = []
        for job, suites in expected_suites.items():
            if (not isinstance(suites, list) or not suites or
                    any(not isinstance(suite, str) for suite in suites) or len(set(suites)) != len(suites)):
                raise ValueError('empty or duplicate required suite selection: ' + job)
            selected_all.extend(suites)
            for suite in suites:
                checks = definitions[suite]['checks']
                if (not isinstance(checks, list) or not checks or
                        any(not isinstance(check, str) or not check for check in checks) or
                        len(set(checks)) != len(checks)):
                    raise ValueError('invalid current check inventory: ' + suite)
        required = manifest['profiles']['required']
        if (not isinstance(required, list) or not required or
                any(not isinstance(suite, str) for suite in required) or
                len(set(required)) != len(required) or Counter(selected_all) != Counter(required)):
            raise ValueError('job/suite mapping must execute the complete current required profile exactly once')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return errors + ['Current manifest is invalid: ' + str(exc)]

    root = Path(evidence_root)
    if root.is_symlink() or not root.is_dir():
        return errors + ['Downloaded job evidence is missing']
    grouped = {job: [] for job in required_jobs}
    for item in sorted(root.iterdir()):
        job = next((name for name in sorted(required_jobs, key=len, reverse=True) if item.name.startswith(name + '-')), None)
        if (job is None or not item.name.endswith(f'-{run_id}-{run_attempt}') or
                item.is_symlink() or not item.is_dir()):
            errors.append('Unknown, foreign, or invalid artifact directory: ' + item.name)
            continue
        grouped[job].append(item)

    for job in sorted(required_jobs):
        status = jobs.get(job) if isinstance(jobs, dict) else None
        status = status.get('result') if isinstance(status, dict) else status
        if status != 'success':
            errors.append(f'{job}: required job did not succeed ({status})')
        seen = []
        plans = [path for artifact in grouped[job] for path in sorted(artifact.rglob('plan.json'))]
        if not plans:
            errors.append(job + ': successful status has no execution evidence')
        for plan_path in plans:
            label = job + '/' + plan_path.parent.name
            try:
                directory = plan_path.parent
                if not directory.resolve().is_relative_to(root.resolve()):
                    raise ValueError('execution evidence escapes downloaded artifact root')
                plan = read_object(plan_path)
                report = read_object(directory / 'results.json')
                if plan.get('run_id') != directory.parent.name or plan.get('attempt_id') != directory.name:
                    errors.append(label + ': plan identity disagrees with its actual attempt directory')
                if not isinstance(plan.get('source'), dict) or plan['source'].get('commit') != source_sha:
                    errors.append(label + ': source commit is not the actual checked-out CI source')
                if (plan.get('github_run') != str(run_id) or
                        plan.get('github_attempt') != str(run_attempt)):
                    errors.append(label + ': stale or foreign workflow run/attempt')
                selected = plan.get('selected')
                if not isinstance(selected, list) or any(not isinstance(suite, str) for suite in selected):
                    raise ValueError('invalid selected suite identities')
                seen.extend(selected)
                if any(suite not in expected_suites[job] for suite in selected):
                    errors.append(label + ': suite is outside the required job selection')
                current = {suite: definitions[suite]['checks'] for suite in selected}
                if plan.get('expected_checks') != current:
                    errors.append(label + ': execution plan does not match the current manifest checks')
                reference = {**plan, 'expected_checks': current}
                native_errors = validate_report(reference, report)
                errors.extend(label + ': ' + error for error in native_errors)
                if not native_errors:
                    errors.extend(label + ': ' + error for error in verify_artifacts(directory, report))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(label + ': invalid or incomplete execution evidence: ' + str(exc))
        if Counter(seen) != Counter(expected_suites[job]):
            errors.append(job + ': missing, duplicated, or substituted required suite execution')
    return errors


def main(argv=None):
    global MANIFEST_PATH
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--source', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--manifest', type=Path, default=MANIFEST_PATH)
    parser.add_argument('--job-suites', default=os.environ.get('JOB_SUITES', json.dumps(FOUNDATION_SUITES)))
    args = parser.parse_args(argv)
    MANIFEST_PATH = args.manifest
    try:
        errors = validate_jobs(json.loads(os.environ.get('REQUIRED_JOBS', '{}')), args.evidence,
                               json.loads(args.job_suites), args.source, args.run, args.attempt)
    except (OSError, ValueError, TypeError) as exc:
        errors = ['Invalid aggregate inputs: ' + str(exc)]
    print(json.dumps({'source': args.source, 'run': args.run, 'attempt': args.attempt, 'errors': errors}, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
