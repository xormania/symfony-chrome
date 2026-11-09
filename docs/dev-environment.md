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
| `private/` if present, gitignored | `/private`, read-write, only when the directory exists |

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

The first `up` builds the image, copies `fixtures/app/` into `workspaces/dev/app/`, resolves Composer
dependencies, and runs Symfony Flex recipes because the fixture has no lock yet. When it is ready, copy the
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

The structural guard rule encodes spec PKG-02: nothing under the runtime bundle namespace may use the Profiler
or the devtools bundle. Exit `1` with a report means findings, not a broken tool. Whether Mago accepts the
symlinked `vendor/xormania/...` entries in `paths` is unverified until the first run; if it refuses, analyze the
packages from `/packages/<name>` with their own configuration instead.

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

Clone your private repository to `private/` at the checkout root. It is gitignored and, when present, mounted at
`/private` in the container. Nothing in this repository reads from it; wiring (Composer path repository, npm
workspace, or otherwise) is decided in that repository.

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
