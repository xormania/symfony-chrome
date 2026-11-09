"""Discover and execute the Docker-free contract tests, preserving native identities."""
import argparse
import json
from pathlib import Path
import sys
import signal
import unittest

ROOT = Path(__file__).resolve().parents[2]


def cases(suite):
    for case in suite:
        if isinstance(case, unittest.TestSuite):
            yield from cases(case)
        else:
            yield case


class Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.identities = []

    def addError(self, test, err):
        super().addError(test, err)
        if issubclass(err[0], InterruptedError):
            self.stop()

    def startTest(self, test):
        self.identities.append(test.id())
        super().startTest(test)


def main(argv=None):
    def interrupted(signum, frame):
        raise InterruptedError('Acceptance worker interrupted by signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args(argv)
    args.evidence.mkdir(parents=True, exist_ok=True)
    suite = unittest.TestSuite()
    for directory in ('fast', 'integration'):
        suite.addTests(unittest.TestLoader().discover(str(ROOT / 'tests' / directory)))
    expected = [case.id() for case in cases(suite)]
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(suite)
    passed = bool(expected) and result.wasSuccessful() and not result.skipped and result.identities == expected
    value = {'schema': 1, 'checks': [{'id': 'fast.contracts', 'outcome': 'passed' if passed else 'failed',
             'assertions': result.testsRun if passed else 0, 'detail': 'Native unittest identities reconciled'}],
             'selected': expected, 'executed': result.identities, 'skipped': [str(x) for x in result.skipped]}
    (args.evidence / 'checks.json').write_text(json.dumps(value, indent=2) + '\n')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
