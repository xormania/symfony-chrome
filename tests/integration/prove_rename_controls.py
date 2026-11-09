#!/usr/bin/env python3
"""A healthy rename oracle passes; omitting exact-edit verification must go red."""
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
    with tempfile.TemporaryDirectory(prefix='rename-controls-') as tmp:
        root = Path(tmp)
        for name in ('protocol.py', 'external_spans.py', 'test_external_spans.py'):
            shutil.copy2(ROOT / 'tests/integration' / name, root / name)
        for state in ('healthy', 'exact-edit-check-removed'):
            if state != 'healthy':
                source = root / 'external_spans.py'
                original = source.read_text()
                needle = 'assert set(actual) == expected,'
                assert original.count(needle) == 1
                source.write_text(original.replace(needle, 'assert True,'))
                shutil.rmtree(root / '__pycache__', ignore_errors=True)
            run = subprocess.run([sys.executable, '-m', 'unittest', 'test_external_spans.RenameOracleContract.test_wrong_replacement_is_rejected', '-v'], cwd=root, capture_output=True, text=True)
            (evidence / (state + '.log')).write_text(run.stdout + run.stderr)
            records.append({'control': state, 'exit': run.returncode})
            if state == 'healthy':
                assert run.returncode == 0, run.stderr
            else:
                assert run.returncode != 0 and 'AssertionError not raised' in run.stderr, run.stderr
    (evidence / 'controls.json').write_text(json.dumps({'schema': 1, 'kind': 'rename_oracle_mutation_red_green', 'records': records}, indent=2) + '\n')
    print(json.dumps(records))


if __name__ == '__main__':
    main()
