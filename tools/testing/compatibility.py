#!/usr/bin/env python3
"""Run independent archive consumers at selected declared framework boundaries."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def run(evidence: Path, selected: str | None = None) -> dict:
    from package import build_archives, prepare_consumer, http_probe

    evidence.mkdir(parents=True, exist_ok=True)
    cells = json.loads((ROOT / 'tests/consumers/compatibility.json').read_text())['cells']
    if selected:
        cells = [row for row in cells if row['id'] == selected]
    if not cells:
        raise ValueError('Compatibility selector matched no cells')
    archives = build_archives(ROOT, evidence / 'archives')
    checks, results = [], []
    for cell in cells:
        target = evidence / cell['id']
        target.mkdir()
        try:
            # Installed application trees never become uploaded evidence.
            with tempfile.TemporaryDirectory(prefix='symfony-chrome-compatibility-') as temporary:
                base = Path(temporary)
                app = prepare_consumer(ROOT, base / 'consumer', archives, mode=cell['mode'], symfony=cell['symfony'])
                script = ROOT / 'tests/consumers/production-check.php'
                if not script.is_file():
                    raise RuntimeError('PR-A production consumer oracle is missing')
                env = {**os.environ, 'APP_ENV': cell['mode'], 'APP_DEBUG': '0'}
                from runner import capture
                native = target / 'kernel'
                native.mkdir()
                code, timed_out, truncated = capture(['php', str(script)], native, 120, cwd=app, env=env)
                if code or timed_out or truncated:
                    raise RuntimeError(f'Native runtime consumer failed: exit={code}, timeout={timed_out}, truncated={truncated}')
                response = http_probe(app, cell['mode'], target / 'http.log')
                if not response.get('ready') or response.get('environment') != cell['mode']:
                    raise RuntimeError('Unexpected independent runtime HTTP response')
                lock = json.loads((app / 'composer.lock').read_text())
                installed = {row['name']: row['version'] for row in lock['packages'] + lock.get('packages-dev', [])}
                wanted = cell['symfony'].rstrip('*')
                framework = installed.get('symfony/framework-bundle', '').lstrip('v')
                if not framework.startswith(wanted):
                    raise RuntimeError('Installed framework does not match selected boundary: ' + framework)
                shutil.copy2(app / 'composer.lock', target / 'resolved-composer.lock')
                for path in (base / 'consumer').glob('*.log'):
                    shutil.copy2(path, target / path.name)
            checks.append({'id': 'compatibility.' + cell['id'], 'outcome': 'passed', 'assertions': 3,
                           'detail': 'Independent archive consumer boots with expected framework; native production oracle passed'})
            results.append({**cell, 'installed': installed, 'input_mode': 'intentional resolution within selected boundary'})
        except InterruptedError:
            raise  # The temporary consumer is cleaned before propagating cancellation; do not start another cell.
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            checks.append({'id': 'compatibility.' + cell['id'], 'outcome': 'error', 'assertions': 0, 'detail': str(exc)})
            results.append({**cell, 'error': str(exc)})
    return {'schema': 1, 'checks': checks, 'cells': results}


def main():
    def interrupted(signum, frame):
        raise InterruptedError('Compatibility execution interrupted by signal ' + str(signum))

    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--cell')
    args = parser.parse_args()
    args.evidence = args.evidence.resolve()
    try:
        result = run(args.evidence, args.cell)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        result = {'schema': 1, 'checks': [{'id': 'compatibility.execution', 'outcome': 'error', 'assertions': 0, 'detail': str(exc)}]}
    args.evidence.mkdir(parents=True, exist_ok=True)
    (args.evidence / 'checks.json').write_text(json.dumps(result, indent=2) + '\n')
    return 0 if result['checks'] and all(row['outcome'] == 'passed' for row in result['checks']) else 1


if __name__ == '__main__':
    sys.exit(main())
