# Install the contract fixture before PHP starts

Hosted run `42565198325` (`8b6e116390eeeb998f7f4f47db137d6931e7b5b2`)
reported a real first-navigation failure. The observed page identity was `1`;
the MCP request navigated to the exact `/_ci/browser` URL, and its first snapshot
was Symfony's HTTP 404 page. The later independently owned borrowed browser and
all seven Playwright cases passed the same fixture route. All five tooling
contracts passed. The exact relevant protocol fields and artifact identity are
retained in `hosted-observation.json`; the snapshot excerpt is truncated after
its URL, status and exception heading.

The integration workspace previously started PHP and served `/_dev/ready`
before copying the test routes/services and running a second cache clear. That
allowed the live runtime to boot against the preceding application. The change
installs the final files before `start()`: `docker/setup` already installs the
locked dependencies and clears Symfony's cache before the server starts. It
therefore removes the post-start cache mutation rather than retrying a failed
navigation. The particular PHP/Symfony cache timing behind the hosted transient
was not separately measured.

`first-request.php` independently compiles the final fixture and handles its
first `/_ci/browser` request using the actual installed locked Symfony 8.1.11
dependency tree under PHP 8.4.24. It returned 200 with the known heading/button
and profiler token (`native-first-request.log`). This local qualification uses
the native kernel; actual Chrome and Docker acceptance remains hosted.

Reproduce the native request with an owned disposable app after installing the
contract files, and an existing matching installed dependency tree:

```sh
php docs/evidence/fixture-bootstrap-order/first-request.php \
  /absolute/path/to/disposable/app /absolute/path/to/vendor/autoload.php
```
