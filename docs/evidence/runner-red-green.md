# Launcher regression and acceptance controls

## Launcher regressions

The same eight tests in `tests/fast/test_dev_contract.py` ran against the parent
launcher and the candidate launcher. They invoke the public `bin/dev` command
in disposable checkouts with a controlled Docker executable. No Docker daemon,
PHP runtime, browser, or external service is used by these tests.

| Subject | Native test exit | Result |
| --- | --- | --- |
| Parent source | 1 | Exactly the two intended regressions fail; six healthy controls pass. |
| Candidate source | 0 | All eight tests pass. |

The parent returns success when Composer's platform check exits 73. It also
returns success for a request to start an existing development run with
`--env prod`, while the stored and executed application environment remains
development. The candidate propagates the platform failure and rejects the
environment mismatch before invoking Docker.

The controls also cover the healthy doctor response, reuse of the recorded
environment, image mismatch, foreign ownership marker, unsafe identifiers,
and deleting only the selected workspace while retaining failed evidence.

The source revision, exact test hash, candidate source hashes, native exits,
and logs are retained in `launcher-controls/proof.json`, `parent.log`, and
`candidate.log`. The parent revision is the local source reconstruction of the
inspected GitHub snapshot; the candidate was tested before its implementation
commit and is identified by the retained source hashes.

Replay against a selected source tree:

```sh
TEST_SUBJECT_ROOT=/absolute/path/to/subject python3 -m unittest discover \
  -s tests/fast -p test_dev_contract.py -v
```

These controls establish launcher behavior at the process boundary. Actual
image installation, platform compatibility, and browser/tool operation need
their real integration suites.

## Acceptance-report controls

`tests/fast/test_runner_contract.py` independently builds complete execution
records and mutates their suite/check identities, run/attempt/source bindings,
native results, assertion counts, and selection completeness.
`tests/fast/test_runner_cli.py` executes the public test/report commands, then
removes, corrupts, or substitutes retained evidence in disposable repositories.

The review exposed three runner defects. Their unchanged regression checks
failed before the fixes: a parent exit of zero bypassed its descendant/output
deadline and waited eight seconds; timeout/truncation flags were ignored by
report validation; and deleting an artifact inventory hid corrupted native
checks. `runner-controls/pre-fix.log` and `pre-fix.json` retain these failures.

Two additional identity controls failed against an exact pre-fix runner from
commit `f3888bb`, reconstructed in a disposable source copy: an unknown schema
was accepted when the plan/report agreed, and foreign plan/report run/attempt
identities were accepted under another requested attempt directory. Their red
evidence is `identity-pre-fix.log` and `identity-pre-fix.json`.

The candidate passes all 30 independent launcher, report, capture, and CLI tests.
The capture control verifies both the deadline and that its descendant process
has terminated. Two deliberate source mutations then disable report validation
or artifact verification in separate disposable copies. Each mutation causes the
same control suite to fail with native exit 1; the intact candidate exits 0.

`runner-controls/proof.json` retains candidate/test/mutant hashes, commands, and
native outcomes. The corresponding `candidate.log`, `validator-bypass.log`,
`artifact-bypass.log`, and small mutation patches make the controls reviewable.
The mutations were never applied to the shared implementation or its assertions.

## Required CI aggregate

`tools/ci/acceptance.py` checks successful GitHub job conclusions against actual
downloaded execution evidence. Fifteen independent controls cover complete
multi-attempt integration evidence; missing, failed, skipped, cancelled, or extra
jobs; missing reports; stale workflow/source identities; same-count suite/check
substitution; duplicate attempts; changed artifact inventories; and omissions
from the current required profile. The public CLI is exercised with real needs
and job-to-suite environment values.

The intact aggregate passes these controls. An isolated mutation bypassing its
verdict causes the same controls to fail with native exit 1, including the CLI's
skipped-job check. Source/test hashes, native outcomes, logs, and the small bypass
patch are retained under `aggregate-controls/`. These are synthetic downloaded
job fixtures; hosted acceptance still has to execute on the candidate PR.

## SIGTERM cleanup

Two subprocess controls in `tests/fast/test_worker_termination.py` deliver an
actual SIGTERM after an explicit worker-ready handshake. The environment
control invokes its public entry point with controlled Docker/devlib boundaries
and verifies that `finally` calls cleanup with `purge=True`. The runner control
invokes public `bin/dev test`, verifies its owned native worker's cleanup marker
and terminated process state, verifies later selected work never starts, and
requires cancelled execution records and native exit 130.

The exact same tests fail against parent `c828a9a` because default SIGTERM
termination bypasses both cleanup paths. They pass against the candidate.
Every test also kills any remaining controlled process groups in teardown, so
the red run does not leave workers behind. `termination-controls/proof.json`
records the test/source hashes and native outcomes; `parent.log` and
`candidate.log` retain the actual assertion results. These controls verify signal
handling at process and Docker-call boundaries, without running a Docker daemon.
