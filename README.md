# symfony-chrome

Reusable Symfony integration for Chrome browser APIs, Chrome DevTools, and MCP. Development diagnostics first, growing into production browser features and managed Chrome operations.

Status: scaffold, 2026-11-09. No package functionality exists yet.

- Specification: [docs/Symfony-Chrome-Scope-Specification-2026-11-07.md](docs/Symfony-Chrome-Scope-Specification-2026-11-07.md)
- Research: [docs/Symfony-Chrome-Background-Examples-Research-2026-11-07.md](docs/Symfony-Chrome-Background-Examples-Research-2026-11-07.md)
- Development environment: [docs/dev-environment.md](docs/dev-environment.md)

Layout:

```
packages/chrome-bundle/            runtime bundle and browser SDK
packages/chrome-devtools-bundle/   development-only diagnostics
fixtures/app/                      minimal Symfony 8.1 consumer, no UXor
bin/dev                            host launcher for the Docker development environment
tools/serena/                      Serena + Mago LSP adapter, patches and lock vendored from mago-serena_v2-poc
tools/mago/                        Mago extension host and wiring config installed into workspaces by mate-prepare
tools/mate/                        Mate runtime-instructions template
private/                           gitignored slot for a private companion repository
```

Package names under `xormania/` are working names pending decision D-01 in the specification.
