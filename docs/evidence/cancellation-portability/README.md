# Cancellation must bypass recoverable filesystem errors

Hosted C run `42563511687`, fast job `128984891733`, exposed a real cancellation
window. The healthy termination control timed out; all other 112 controls passed.
B's simultaneous fast job `128984850509` passed, consistent with the timing window.

The readiness marker was published before `Checks.__init__` called
`Path.mkdir(exist_ok=True)`. If SIGTERM raises `InterruptedError` after directory
creation, `Path.mkdir` can catch it as an `OSError` and return because the directory
exists. The termination handler then considers the signal handled while the
contract continues. This can affect production workspace operations as well as
the test's setup, so moving the marker alone is insufficient.

The revised control publishes readiness from inside the active blocking contract,
after construction. A new deterministic case wraps the actual `os.mkdir`: it
creates the probe directory, then delivers a real SIGTERM before returning to
`Path.mkdir`. No cancellation result or assertion is mocked.

Against the original implementation, that case exits 0 and fails the required
exit-130 assertion: cancellation was swallowed. The fixed implementation raises
`ContractCancelled`, a dedicated `BaseException` subclass. It escapes the
recoverable `OSError` path and ordinary check failure collection, unwinds owned
cleanup, and prevents subsequent contract execution.

The exact deterministic test is red on the parent and green on the candidate.
All three termination controls then passed 50 repetitions (150 control
executions) on Python 3.12.14. They retain cleanup, primary-interruption,
no-later-contract, and exit-status assertions; subprocess teardown remains
bounded. Source/test hashes, each repetition's native outcome, the real hosted
failure excerpt, and artifact identity are retained alongside this note.

```sh
TEST_SUBJECT_ROOT=/absolute/path/to/candidate python3 -m unittest discover \
  -s tests/integration -p test_termination.py -v
```

These controls use actual subprocesses and signals with controlled owned-workspace
boundaries; they do not claim to execute Docker or browser integration.
