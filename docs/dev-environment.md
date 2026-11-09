# Development environment

Created 2026-11-09. Adapted from the launcher, workspace, and evidence conventions of
[mago-serena_v2-poc](https://github.com/xormania/mago-serena_v2-poc), reduced to what writing this package needs.

## What runs where

| Host | Container (`php` service) |
| --- | --- |
| `bin/dev` launcher, your editor, your own Chrome, an MCP client | xorder `php-browser` 8.4 base (PHP 8.4.27, Composer, Symfony CLI, Chromium) plus Node 22, Chrome for Testing, `chrome-devtools-mcp` |
| `packages/` edited in place | mounted at `/packages`, symlinked into the fixture's `vendor/` |
| `workspaces/<run>/app/` disposable copy of `fixtures/app/` | `/workspace`, served by PHP's built-in server on port 8000 |
| `workspaces/<run>/state/` | `/home/dev`: Composer and npm caches, `$HOME` |
| `artifacts/<run>/` | `/evidence`: build and setup logs, image identity, later run records |
| `private/` gitignored | `/private`, only for runs created with `up --private` (read-only) or `up --private-rw` |

Pins are in `toolchain.lock.json`. The image records its own identity at build time; `bin/dev doctor` prints it.
The first build compiles the patched Mago in Rust: allow several minutes and several GB of memory and disk.
`MAGO_BUILD_JOBS` is a build argument, default 4.

## Base image from xorder

The Dockerfile starts from `ghcr.io/xormania/php-browser:8.4-trixie-v1.2.4` by digest and adds three things:
Node 22 (copied from the node image xorder's own record pins), Chrome for Testing 157, and `chrome-devtools-mcp` 1.12.0.
Chrome for Testing is added rather than reusing the base's Debian Chromium because the MCP server states it
supports Google Chrome and Chrome for Testing only. The base's PUID/PGID entrypoint is kept; compose passes
`PUID`/`PGID` instead of `user:`.

When the contract settles, this overlay is a candidate xorder line, roughly `php-chrome-mcp/8.4-trixie` with
parent `php-browser/8.4-trixie`, capabilities `node`, `chrome-for-testing`, `chrome-devtools-mcp`, and the two
pinned versions as locked inputs. Until then the overlay lives here so the project can move without a release cycle.

## Requirements

Git, Python 3 on the host, Docker with Compose v2. No host PHP, Composer, or Node is needed. Linux or WSL2; the
launchers use POSIX user and group IDs so files in `workspaces/` and `packages/` stay owned by you.

## First start

```sh
./bin/dev up
./bin/dev doctor
```

The first `up` builds the image, copies `fixtures/app/` into `workspaces/dev/app/`, then bootstraps the copy in a
one-off container: Composer resolves dependencies and Symfony Flex generates the skeleton, including `public/`,
because the fixture has no lock yet. Only then does the service start PHP's built-in server. When it is ready, copy the
generated skeleton and `composer.lock` back into `fixtures/app/` and commit them. Later workspaces install
from that lock.

`up` reruns setup every time. It reinstalls dependencies and clears the cache. It does not delete source edits
in the workspace.

## Daily commands

```sh
./bin/dev composer -- require some/package
./bin/dev console -- debug:container
./bin/dev exec -- php vendor/bin/phpunit
./bin/dev up --run prodcheck --env prod --no-build   # second workspace, prod mode
./bin/dev down --run prodcheck --purge
```

A run id other than `dev` gets a Docker-assigned host port; `up` prints the URL.

## Mago: analysis, lint, format, guard

Mago 1.58.2 is in the image as the upstream release binary, hash-pinned. The fixture's `mago.toml` analyzes the
app and, through the Composer path symlinks under `vendor/xormania`, both packages. Each package also has a
standalone `mago.toml` for lint and format without vendor context.

```sh
./bin/dev mago -- analyze --reporting-format json
./bin/dev mago -- lint --reporting-format json
./bin/dev mago -- guard --structural --reporting-format json
./bin/dev mago -- format --check vendor/xormania/chrome-bundle/src/ChromeBundle.php
```

`bin/dev mago` and `bin/mago` are the same wrapper. It fixes workspace, config and PHP target, refuses the
generic `fix` command, requires explicit workspace-relative `.php` targets for `format` and `--fix`, and
records each invocation under `artifacts/<run>/mago/invocations/`.

The structural guard rule encodes spec PKG-02: nothing under the runtime bundle namespace may use the Profiler
or the devtools bundle. Exit `1` with a report means findings, not a broken tool. Whether Mago accepts the
symlinked `vendor/xormania/...` entries in `paths` is unverified until the first run; if it refuses, analyze the
packages from `/packages/<name>` with their own configuration instead.

## Symfony development setup

The fixture is a dev-oriented Symfony 8.1 application. Beyond the runtime packages it carries, in `require-dev`:
WebProfilerBundle and DebugBundle, MonologBundle (all environments), MakerBundle, VarDumper, PHPUnit,
BrowserKit and CssSelector, and Symfony AI Mate 0.15.0 with its Symfony and Monolog extensions. The base image
also supplies the `symfony` CLI, Xdebug (off by default, `XDEBUG_MODE=debug` to enable) and PCOV.

Mate reads this application's recorded dev data through the `inspection-dev` context defined in
`mate/config.php`: container metadata from `var/cache/dev`, profiles from `var/cache/dev/profiler`, logs from
`var/log`. Profiler and Monolog reads are exact-request joins, which is what spec DIAG-01 and DIAG-04 need.

```sh
./bin/dev mate -- tools:list --format=json
./bin/dev mate -- tools:call symfony-profiler-list --context=inspection-dev --limit=20 --url=MARKER --format=json
./bin/dev mate -- tools:call symfony-profiler-get --token=HEX6 --format=json
./bin/dev mate -- resources:read symfony-profiler://profile/HEX6/request --format=json
./bin/dev mate -- tools:call monolog-search --term=MARKER --environment=dev --kernelContext=inspection-dev --limit=20 --format=json
./bin/dev mate -- tools:call symfony-service-detail --id='App\Controller\ReadyController' --context=inspection-dev --format=json
```

Use the exact response's `X-Debug-Token`; the health check creates profiles too. Mate's `server-info` describes
its own CLI process, not the HTTP request.

### Preparation and freshness

`bin/dev mate` and `bin/mate` are the same guarded wrapper, ported from the PoC. Mate commands fall into three
classes. Discovery (`tools:list`, `tools:inspect`, `init`, `discover`, help) runs anytime. Runtime reads
(`symfony-profiler-*`, `monolog-*`, `server-info`, exact `symfony-profiler://` resources) need the runtime
marker and exact parameters: `--context=inspection-dev`, six-hex tokens, limits 1 to 100. Compiled reads, and
any unknown or abbreviated command, need a fresh preparation.

```sh
./bin/dev mate-prepare --run dev
```

Preparation archives existing profiles and logs under `artifacts/<run>/mate/prepare-*/runtime-before-refresh/`,
installs a managed runtime-instructions block into the workspace `AGENTS.md`, runs `mate init`, dump-autoload,
`mate discover` and `cache:clear --env=dev`, installs `.mago/extensions.php` and `.mago/wiring.toml` from
`tools/mago/`, exports the two `debug:container` JSON views privately into `/home/dev`, runs the wiring package's
exporter to produce the sanitized `.mago/container-reference.dev.json`, and seals a preparation record in
`workspaces/<run>/trusted/`. The record binds application source, manifests, lock, config, compiled
`DebugContainer.xml`, the reference and the container id. Any change to those makes compiled reads and enriched
analysis exit 3 with a refresh instruction. Every invocation leaves stdout, stderr and an `invocation.json`
under `artifacts/<run>/mate/invocations/`.

### Symfony-enriched Mago analysis

The fixture declares the Mago PHP SDK at the same source revision as the executable and the Byte-Kitsune
Symfony wiring extension at its pinned snapshot, both as Composer package repositories. The wiring extension
reads the sanitized container reference and contributes compiled autowiring edges to Mago's dependency graph.

```sh
./bin/mago --run dev --profile symfony --symbol 'App\Controller\ReadyController' -- analyze --reporting-format json
./bin/mago --run dev --profile symfony --extension-off -- analyze --reporting-format json
```

Results land under `artifacts/<run>/mago/enriched/<id>/` as `graph.json`, `invocation.json`, stdout and stderr.
`status` is `clean`, `findings`, `stale_preparation` or `tool_failure`; a native exit of 0 or 1 without the
observer's graph or the wiring attestation is a wrapper failure, exit 3, never a clean result. The Symfony profile
always reports JSON because the attestation is read from the report; other formats are available through the
native profile. The preparation fingerprint includes the live `packages/*` trees, so editing a package invalidates
compiled reads until the next `mate-prepare`. `--extension-off`
is the comparison control on the same preparation. The observer only reads Mago's final graph; it adds no edges.
This enriches CLI analysis only. LSP enrichment through Serena needs the workspace opt-in described in the
PoC's `MAGO-LSP-EXTENSIONS.md` and is not configured here.

Version note: UXor declares Mate `^0.14`. The fixture pins 0.15.0, which the PoC verified. The package's Mate
integration must be checked against both before claiming UXor compatibility (spec §4, DIAG section).

Symfony Docker (dunglas) and FrankenPHP: not adopted. The fixture runs PHP's built-in server, which is enough
for request/profile correlation. xorder's `php-frankenphp` and `uxor-dev` lines are the route if a worker-mode
or Caddy-fronted fixture becomes necessary, for example for Mercure or HTTP/2 behavior.

## Serena with the Mago language server

Ported from mago-serena_v2-poc and vendored under `tools/serena/`: Serena v2 at its pinned revision with the
REPL facade patch, the `serena-mago-adapter` that registers Mago as a SolidLSP backend, and Mago built from the
same upstream revision as the release binary plus the PoC's LSP extension patch. The patched build is
`/usr/local/bin/mago`; the upstream release binary stays at `/usr/local/bin/mago-baseline` for comparison.

Each new workspace gets `.serena/project.yml` from `tools/serena/config/`. Connect a client over stdio:

```sh
./bin/dev mcp-config
```

The printed JSON carries both servers, `chrome` and `serena`. The Serena entry runs `bin/serena-mcp --run <id>`,
which bridges `serena start-mcp-server --project /workspace --agent-interface REPL` out of the container. Call
`initial_instructions`, keep the session token, then `s.info("lsp")` before using the facade. The PoC's
`WORKFLOWS.md` and `MAGO-LSP-EXTENSIONS.md` remain the reference for REPL usage and the opt-in Symfony
wiring contribution, which is not wired here yet.

Known from the PoC and carried over unchanged: an unfixed external-edit span defect in the Mago LSP path with a
restart workaround, and the fact that `mago-baseline` here is the upstream release build rather than a local
unpatched build of the same revision.

## Two Chrome attachment modes

These map onto RUN-01 in the specification: an owned browser and an explicitly attached existing session.

**Host Chrome, attached.** Your own Chrome 144+ with remote debugging enabled at `chrome://inspect/#remote-debugging`.
Chrome DevTools MCP runs on the host via `npx` and attaches to it. The app is at the host port.

```sh
./bin/dev mcp-config --mode host
```

**Owned Chrome for Testing, headless, in the container.** The MCP server runs inside the container and is bridged
over stdio by `bin/chrome-mcp`. Isolated profile, deleted on exit. The app is at `http://127.0.0.1:8000` from the
browser's point of view.

```sh
./bin/dev mcp-config --mode owned
```

Paste the printed JSON into your MCP client. Both modes pin `chrome-devtools-mcp` to the locked version and disable
its usage statistics and CrUX lookups.

## Private companion repository

Clone your private repository to `private/` at the checkout root. It is gitignored. It is never mounted unless the
run was created with `./bin/dev up --private` (read-only at `/private`) or `--private-rw` (read-write, for a
trusted editing session). The choice is recorded in the run's `run.json`; create a new run to change it. The
bootstrap container that runs Composer and Flex recipes never sees `private/`, so a compromised dependency
resolved on first install cannot reach it. Nothing in this repository reads from `private/`; wiring (Composer path
repository, npm workspace, or otherwise) is decided in that repository.

## Proxy certificates

Build with a CA secret when a proxy intercepts TLS:

```sh
docker buildx build --secret id=proxy_ca,src=/absolute/path/ca-bundle.pem --load -t symfony-chrome-dev:local .
./bin/dev up --no-build
```

## Not yet verified

This scaffold was written without a Docker daemon available. The image build, the first Flex-generated install,
and both MCP attachment modes have not been executed. Treat the first `up` as the verification step and record
what fails in `artifacts/dev/`.
