"""Verify native Playwright identities and every attempt, not aggregate totals."""
EXPECTED = {
    'real input changes state without creating a request',
    'clean navigation keeps all runtime guards quiet',
    *('guard detects deliberate ' + name + ' fault' for name in ('console', 'page', 'http', 'request', 'csp')),
}


def specifications(report):
    found = []
    def visit(suite):
        found.extend(suite.get('specs', []))
        for child in suite.get('suites', []):
            visit(child)
    for suite in report.get('suites', []):
        visit(suite)
    return found


def verify(discovery, report):
    planned, actual = specifications(discovery), specifications(report)
    assert len(planned) == len(actual) == len(EXPECTED), 'Missing/extra native browser test identities'
    assert {row['title'] for row in planned} == {row['title'] for row in actual} == EXPECTED, 'Native browser test identity substituted'
    expected_ids = {row['id'] for row in planned}
    assert len(expected_ids) == len(planned) and {row['id'] for row in actual} == expected_ids, 'Duplicate/foreign native test ID'
    assert not report.get('errors'), 'Playwright global/setup errors'
    for spec in actual:
        assert spec['file'].endswith('contracts.spec.mjs') and spec['ok'] is True
        assert len(spec['tests']) == 1, 'Unexpected project/test expansion'
        case = spec['tests'][0]
        assert case['expectedStatus'] == 'passed' and case['status'] == 'expected'
        assert len(case['results']) == 1, 'Unexpected missing/retried attempt'
        assert case['results'][0]['status'] == 'passed' and not case['results'][0].get('errors')
    stats = report['stats']
    assert stats['expected'] == len(EXPECTED) and stats['unexpected'] == stats['skipped'] == stats['flaky'] == 0
    return len(actual)
