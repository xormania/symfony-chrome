# Testing

The shared entry point is `bin/dev test`. CI invokes the same suites and validates
their native results, selected check identities, source commit and retained bytes.

```sh
./bin/dev test --list --json
./bin/dev test --suite fast
./bin/dev test --suite package
./bin/dev test --suite support
./bin/dev test --suite environment
./bin/dev test --profile required
./bin/dev report <printed-run-id>
```

`fast` uses Python 3.12 or later and needs no Docker, PHP, browser or credentials.
`package` uses PHP 8.4 with the locked fixture's extensions and Composer 2.10.3,
or automatically runs the same script through the validated Docker parent when
the native tools are absent; see [package-runtime.md](package-runtime.md).
`support` and `environment` use Docker with Compose v2; the latter builds the
selected development image unless `DEV_SKIP_BUILD=1` selects a prepared image.
Use `DEV_IMAGE` consistently when preparing and exercising a different image.

| Suite | What a pass establishes |
| --- | --- |
| fast | Launcher failure propagation/isolation, result and artifact controls, package metadata controls, current CI aggregation and support-wrapper controls. |
| package | Valid distribution payloads, real bundle/kernel tests, and independent dev/prod archive consumers with real HTTP responses. |
| support | The actual released parent is accepted by current xorder policy and matches the Dockerfile/toolchain/support lock. |
| environment | Locked application installation, actual container/image identity, platform requirements and native Mago quality checks. |

The package consumer installs the archive bytes, rather than the development
path symlinks. Its clean production installation excludes the development
bundle, WebProfilerBundle, Mate, and analysis-only packages. It checks the
compiled kernel and a real request. The bundles currently provide a scaffold;
installation acceptance does not establish an unimplemented browser operation.

## Attempts and diagnosis

Each invocation selects its suite/check identities before execution and creates
`artifacts/<run>/<attempt>/`. `plan.json` records selection and source identity;
`results.json` preserves native exits, normalized checks and timings. Native logs,
JUnit, compact runtime/consumer observations and archive hashes remain alongside
them. Disposable dependency installations live outside this retained evidence.

`report` revalidates the selected identities and the hashes of the retained
native logs/results. Missing, duplicate, skipped, foreign, zero-assertion or
incomplete required results fail. Timeouts and output truncation cannot become
passes. A suite log is bounded to 8 MiB; suite evidence is bounded to 64 MiB.
Required evidence that exceeds a limit fails with a diagnostic.

Runs retain the original failed attempts. They do not automatically retry a
contract test, rewrite a failure as a clean pass, or update screenshot baselines.
Intentional reruns receive new attempt identities.

The process deadline includes descendants that retain stdout after their parent
exits. After the execution deadline, an owned worker has up to 20 seconds
to finish cleanup before its process group is killed. The runner also cleans
its owned process group on normal completion or interruption.
Optimized Python is rejected because it would disable assertion-based contracts.

The controlled red/green and mutation evidence is indexed in
[runner-red-green.md](evidence/runner-red-green.md),
[foundation](evidence/foundation/README.md),
[support-control](evidence/support-control/README.md), and the aggregate proof
under `docs/evidence/aggregate-controls/`.

## Refreshing fixture dependencies

Normal acceptance requires the committed application and consumer locks.
Intentional resolution uses the maintenance command:

```sh
python3 tools/testing/package.py --bootstrap-locks --evidence artifacts/lock-refresh
```

Inspect generated application/configuration and dependency changes, commit their
locks together, then execute package and environment acceptance. The consumer's
embedded repository definitions and locks must match the package manifests in
the actual archives. Stale definitions fail before installation.

## Image selection

The original scaffold selected PHP browser 1.2.4, whose digest was published but
was absent from accepted xorder release groups during qualification. CI selects
the verified 1.2.3 resource in `weekly-2026-11-02`: PHP 8.4.26, the same declared
development capabilities, and a separately pinned owned Chrome for Testing 157.
`toolchain.lock.json`, the Dockerfile, and `xorder-support.lock.json` identify it.

The wrapper acquires a fresh policy snapshot with xorder's pinned stdlib checker
and then checks that snapshot against Docker's actual parent-image observation.
This two-command path avoids the pinned checker's online receipt-clock defect.
The derived development image is recorded separately from its released parent.

Local host runtime results identify their actual PHP version; they do not claim
to have qualified a Docker image. Browser and tool protocol checks are added in
[the browser/tooling suite](TESTING-browser.md), with consumer/compatibility measurements following.

## Browser and tooling integration

Run `./bin/dev test --suite browser` or `--suite tooling` after preparing the
selected image. Both suites use disposable applications and real native protocol
calls; the fast suite includes their protocol/report controls. See
[TESTING-browser.md](TESTING-browser.md) for actual scenario scope and limits.
