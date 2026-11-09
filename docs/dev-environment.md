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
