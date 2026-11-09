# First runtime bootstrap sees the complete integration fixture

The hosted browser run observed a 404 on the first owned MCP request to the
correct `/_ci/browser` URL, while later borrowed/Playwright requests to the same
URL passed. The integration workspace started PHP and its readiness request
before copying test routes and service bindings into the application.

The independent controls in `tests/integration/test_fixture_bootstrap.py` invoke
the actual fixture installer against an empty temporary application. The first
`start`/bootstrap boundary reads the actual controller route attributes, copied
service files, and Symfony service configuration. It verifies that browser,
script, icon, and observation routes exist, that the transport interface binds
to the loopback service, and that application-owned configuration remains intact.
No post-start fixture mutation or pre-start container execution is permitted.

A second control raises a startup failure after observing complete inputs and
verifies that the original failure survives while owned cleanup executes with
`purge=True` and produces a cleanup record. There are no sleeps or retries.

The exact same two controls fail against parent `0f293f9` because the first
runtime sees no CI controller/routes. Both pass against candidate `2250ab1`,
which installs fixture files before startup and lets normal startup bootstrap
perform dependency/cache preparation before HTTP service begins.

`proof.json` retains exact revisions, source/fixture/test hashes, commands, and
native outcomes. The two logs retain the actual assertion results. These tests
verify the startup input boundary; real Symfony compilation and first HTTP
execution are separately established by the native/hosted integration evidence.

```sh
TEST_SUBJECT_ROOT=/absolute/path/to/candidate python3 -m unittest discover \
  -s tests/integration -p test_fixture_bootstrap.py -v
```
