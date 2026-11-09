#!/usr/bin/env python3
"""Replay healthy stdio tests and reject a deliberately removed identity check."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True)
    args = parser.parse_args()
    evidence = Path(args.evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix='stdio-controls-') as tmp:
        root = Path(tmp)
        for name in ('protocol.py', 'test_protocol.py'):
            shutil.copy2(ROOT / 'tests/integration' / name, root / name)
        for kind in ('healthy', 'foreign-response-accepted'):
            if kind != 'healthy':
                source = root / 'protocol.py'
                content = source.read_text()
                before = "if answer.get('id') != identity:"
                assert content.count(before) == 1
                source.write_text(content.replace(before, 'if False:  # deliberate identity-check mutation'))
                shutil.rmtree(root / '__pycache__', ignore_errors=True)
            run = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(root), '-v'], capture_output=True, text=True)
            (evidence / (kind + '.log')).write_text(run.stdout + run.stderr)
            records.append({'control': kind, 'exit': run.returncode,
                            'expected': 'pass' if kind == 'healthy' else 'foreign-response identity assertion fails'})
            if kind == 'healthy':
                assert run.returncode == 0, run.stderr
            else:
                assert run.returncode != 0 and 'test_foreign_response_identity_is_rejected' in run.stderr and 'not raised' in run.stderr, run.stderr
    (evidence / 'controls.json').write_text(json.dumps({'schema': 1, 'kind': 'deliberate_mutation_red_green', 'records': records}, indent=2) + '\n')
    print(json.dumps(records))


if __name__ == '__main__':
    main()
