# Consumer, compatibility, and performance checks

The consumer suite installs both candidate distribution archives into a disposable
checkout of UXor at the exact revision in `tests/consumers/uxor.json`. It preserves
the original consumer's Composer constraints, including Mate's version constraint,
and records the original and resolved lock identities. No source symlinks stand
in for installed candidate distributions.

```sh
python3 tools/testing/consumer.py --evidence artifacts/local-consumer/attempt-1
python3 tools/testing/compatibility.py --evidence artifacts/local-compatibility/attempt-1
```

These entry points also run through `bin/dev test` when selected by the shared
manifest. PHP, Composer, Node/npm, Git, and the selected Chrome executable must
actually be available. Missing prerequisites are execution errors; they never
produce a passing skip.

The UXor suite executes the consumer's original Live modal replacement and Live
form validation specs. Its own shared Playwright fixtures guard console, page,
HTTP, network, and CSP behavior. The local adapter supplies only selection,
browser/server configuration, artifact installation, and report validation.
Native test identities must match exactly, execute once, and pass. Missing,
substituted, skipped, retried, or globally failed reports cannot establish a pass.
This is coverage of those selected native assertions, not certification of an
entire dialog requirement profile.

The consumer invokes UXor's native `node tools/prepare-tests.mjs` before
Playwright starts its HTTP server. Its CSS must exist for the readiness page to
render; Playwright's later `globalSetup` alone is too late. The native setup is
idempotent, so the original global setup remains enabled as well.

The installed checkout, vendor directory, and npm dependencies live outside
evidence and are removed in cleanup. Logs, the resolved Composer lock, candidate
archives, provenance, native JSON results, and retained browser failure artifacts
are evidence. The report records candidate/archive identities, the consumer
revision, actual dependency versions, and PHP/Node/Chrome versions. A failure
remains visible even if cleanup also fails.

`tests/consumers/compatibility.json` selects the Symfony 7.3 runtime boundary in an
independent production consumer. It reuses the package suite's distribution
builder and production kernel/HTTP oracle. The package suite already owns the
Symfony 8.1 reference production consumer, so compatibility does not execute that
same expensive case a second time. A lower-bound resolution remains labeled as
intentional dependency resolution, with its actual resolved lock retained; it is
not described as the locked Symfony 8.1 regression baseline. A conflict fails the
selected cell instead of rewriting package constraints.

## Performance experiments

```sh
python3 tools/testing/performance.py \
  --evidence artifacts/feedback-experiment/attempt-1 \
  --label fast-suite-feedback --runner local-linux-amd64 \
  --warm-state unspecified --attempts 30 --timeout 120 \
  -- python3 -m unittest discover -s tests/fast
```

Run this manual experiment on one named runner configuration. It measures native
command wall time including process startup and output capture. It does not
measure Chrome interaction latency or INP. `--warm-state` describes the declared
scenario state; it does not infer a warmed browser from an image cache.

For a scenario that writes evidence, pass the literal argument
`'{attempt_evidence}'`. The harness substitutes a fresh owned scenario directory
for each attempt, so repeated runs do not overwrite one another. For example,
the command tail `-- python3 tools/testing/browser.py --evidence
'{attempt_evidence}'` measures the existing browser acceptance scenario, including
its setup and cleanup, without copying its assertions.

The experiment retains every actual attempt in `samples.jsonl`, with native exit,
timeout/truncation, duration, and log identity. It uses the common runner's bounded
capture/process cleanup. Each native attempt has an 8 MiB output limit; hitting
the limit is an error, not a passing shortened log. Evidence directories cannot
be overwritten by a rerun. Cancellation retains a partial, unsuccessful
experiment rather than manufacturing the remaining samples.

`performance.json` records the measurement configuration, source identity before
and after, every sample, outcome counts, median, median absolute deviation, and
successful range. Failed and timed-out attempts remain in the all-attempt
statistics. Timing remains advisory; any native command failure fails the
experiment's correctness check. A source change during measurement prevents
acceptance. Local and hosted runner configurations are separate populations.

`--baseline PATH` emits a comparison only when measurement configurations match
and both experiments passed with stable sources. The measurement records the
toolchain lock digest, so a changed Chrome/MCP/toolchain selection cannot silently
be compared as the same population. Actual nested browser/tooling identities stay
in their scenario evidence; the lock digest alone does not claim those tools ran.
Harness changes require a fresh compatible baseline. The ratio is advisory and does
not claim statistical significance. No latency threshold is enforced until a
stable baseline and a justified tolerance have been established.

## Failure controls

The fast tests cover dependency preservation and archive tampering, exact native
test identity, missing/skipped/retried results, failure retention, incomplete
attempt inventories, and incompatible baseline populations. Deliberate mutants
that accept a same-total substituted test or hide a failed attempt make the same
regression tests fail. Actual native failure experiments retain every exit-7
attempt, alongside clean controls. These are implementation fault controls;
failure merely because an unimplemented function is missing is not red proof.
