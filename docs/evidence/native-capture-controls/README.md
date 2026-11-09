# Native capture bounds before parsing

Eight independent controls execute real native Python subprocesses. Healthy
JSON stdout remains separate from diagnostic stderr; byte/text streams, native
nonzero exits and `check=True` retain `CompletedProcess` semantics. A 9 MiB
stdout producer and a 5 MiB stdout plus 5 MiB stderr producer must fail against
one aggregate 8 MiB budget. Timeout remains an error with `check=False`. An
already exited parent cannot leave a live descendant holding the output pipes.

Two controls exercise the original `devlib.execute(capture_output=True)` seam.
Only Docker argv/environment construction is replaced with a controlled native
peer; process execution and byte collection are real. Overflow fails before the
caller can parse output. Healthy captured payloads remain in private ephemeral
state; public evidence contains status without the payload or command.

The intact implementation passes all eight controls. A disposable mutation
doubles the default aggregate budget while preserving the engine and tests.
The same three overflow controls then fail because no capture error is raised.
This is a behavioral red result, rather than an import or setup failure.

`proof.json` retains source/test hashes, command and native outcomes. The small
mutation and logs are adjacent; local source paths in logs are replaced with
`<candidate>` or `<mutant>`. These controls qualify native collection and cleanup,
not Docker or hosted browser acceptance.

```sh
python3 -m unittest discover -s tests/integration -p test_native_capture.py -v
```
