# Browser and development-tool contract suites

The browser and tooling suites use real providers against a freshly copied,
owned Symfony fixture. They create test-only routes/services in that disposable
application; the checked-in fixture and package sources are not changed.

Build/select the development image first. The common runner and native suite
commands use the same implementation:

```sh
./bin/dev test --suite browser
./bin/dev test --suite tooling
python3 tools/testing/browser.py --evidence artifacts/manual-browser
python3 tools/testing/tooling.py --evidence artifacts/manual-tooling
python3 tools/testing/browser.py --contract browser.request-profile --evidence artifacts/profile-only
```

Set `DEV_IMAGE` consistently with the image under test. Native suites start with
`--no-build`; they fail when that image or Docker is unavailable. The common
runner records the candidate source identity and native process exits.

## Contracts

| Suite / check | What executes |
| --- | --- |
| `browser.chrome-mcp` | Real MCP initialize/discovery, observed controlled page-ID selection for navigation/snapshot and invalid-mode response; an external `/proc` observation checks owned Chrome cleanup. |
| `browser.borrowed-endpoint` | A separate owner starts Chrome on a loopback endpoint. MCP attaches, navigates and detaches. The owner verifies that its process and endpoint survive, then cleans up its own resources. |
| `browser.request-profile` | Two outstanding HTTP clients obtain distinct exact response tokens. Raw Symfony profile metadata independently verifies each marker, URL, method and status. Swapping profiles is rejected. Missing-profile and redirect records are retained. Client concurrency is not a claim of backend parallelism. |
| `browser.guards` | Seven native Playwright cases: real input/client-only behavior, clean load, and deliberately injected console, page, HTTP, request and CSP failures. Unexpected errors fail teardown; expected companion messages are scoped to the exact fixture URL/message. |
| `tooling.mate` | Real profile/compiled-service reads; exact old profile archived byte-for-byte against hashes captured before refresh; stale source rejected before invocation; explicit recovery; invalid token rejected. |
| `tooling.native-mago` | Native analyzer diagnostics identify a deliberate undefined variable in a disposable source; unscoped formatting is rejected. |
| `tooling.enriched-mago` | Compiled interface-to-concrete binding contributes a known Body graph edge only with wiring enabled; real graph and attestation results are retained. |
| `tooling.serena-mago` | Real Serena REPL discovery, known symbol/body and constructor-reference queries through the Mago backend. |
| `tooling.external-spans` | A direct native LSP external-edit observation plus independent fresh-process UTF-16/rename control. A usable rename requires exactly the two known identifier edits in Target.php and Caller.php, at the known UTF-16 ranges and with the requested replacement; null, empty, substituted or extra edits fail. A reproduced existing defect is labeled as such; a healthy tuple is reported as not reproduced. Neither claims complete external-edit support. |

`--contract` selects one named check. Each invocation still creates and cleans
its own workspace, making it suitable for bounded repeated experiments without
copying assertion code.

## Evidence and failure semantics

The requested evidence directory contains `checks.json`, bounded protocol logs,
transport closure records, browser identity/process observations, request/profile
records, native Playwright discovery/results, failure traces, and LSP observations.
`checks.json` also identifies the disposable workspace's native evidence tree,
where the existing Mate/Mago wrappers retain their invocation records. Workspace
cleanup preserves that evidence and records cleanup failures without replacing
an earlier failure. SIGTERM raises a dedicated BaseException-derived ContractCancelled inside the owned workspace, so ordinary filesystem OSError handlers cannot swallow it; the check collector re-raises it so cleanup runs immediately instead of continuing later contracts. The CLI then records an explicit interruption in partial evidence and exits 130. The parent runner must allow its configured cleanup grace before its hard-kill fallback.

Playwright runs the selected `/usr/local/bin/chrome`, with no automatic retries.
Its result verifier compares exact titles and native IDs against discovery and
checks every result attempt, global errors and skip/flaky counts. Equal totals
alone cannot pass a substituted test.

Chrome MCP 1.12 requires explicit page IDs for navigation and snapshots. The suite derives the ID from the actual single controlled about:blank listing and uses that identity for every subsequent operation, including the invalid-mode control. It never assumes that the initial ID is 1.

Chrome 157 may omit console location for its CSP diagnostic. That companion is allowed only when the exact message contains the known blocked script's SHA-256 and an independent native CSP event identifies the controlled document, inline script, script-src-elem directive and enforcement disposition. Unrelated errors remain unexpected. Native Node helper controls run inside the existing browser phase alongside the seven Playwright cases.

The JSON-RPC client uses byte/time limits, validates response identity/envelopes,
and owns only its process group. Missing, malformed, timed-out or oversized
responses fail. Truncated stderr is recorded and makes the diagnostic contract
incomplete. The direct LSP probe uses Content-Length framing and UTF-16 positions;
MCP uses newline framing.

## Fast controls and red proof

These checks run without Docker, PHP, browser downloads or credentials:

```sh
python3 -m unittest discover -s tests/integration -p 'test_*.py' -v
python3 tests/integration/prove_controls.py --evidence artifacts/protocol-controls
python3 tests/integration/prove_rename_controls.py --evidence artifacts/rename-controls
```

The stdio tests execute real controlled pipe peers. The proof runner copies the
client/tests to a temporary directory, runs the healthy suite, removes the
response-ID guard in that copy, and requires the identity test to fail because
its expected exception is no longer raised. This is a deliberate mutation proof,
not a claim of a previously shipped bug. The original source is preserved.

Rename-oracle controls reject null/empty successful RPC results, wrong files, UTF-16 ranges, replacement text, duplicated edits and resource operations. The mutation proof removes exact-edit verification in a temporary copy and requires the wrong-replacement test to go red. Archive controls reject changed profile bytes even when the archive supplies a matching newly generated hash.

Subprocess SIGTERM controls interrupt a real public workspace/check context, observe that owned stop/purge and cleanup recording execute, and verify that a cleanup error preserves the original interruption.

The existing HTTP, failed-request and CSP fault cases also inject unrelated console errors containing the same generic fragments (503, ERR_FAILED and CSP wording). Each must remain unexpected under the companion allowance before that exact observed control message is explicitly allowed.

Report-verifier controls also reject same-total test substitution, duplicate
native IDs, skips hidden behind passing totals and global setup errors.

## Scope of claims

Controlled endpoint attachment is distinct from host Chrome autoConnect discovery
and consent. The existing `bin/dev mcp-config --mode host` remains the local path
for that separate, explicitly selected browser session. No personal profile is
used by these automatic tests.

These suites qualify the existing development integrations and the test fixture.
They do not claim that the still-unimplemented package correlation/session API,
built-in browser AI, WebMCP, or a fresh adaptive agent session was exercised.
Those product contracts attach to the shared fixture as their implementations
arrive.
