# xorder image requirements for symfony-chrome

**Date:** 2026-11-09, UTC
**Status:** Requirements for images to be authored in [xormania/xorder](https://github.com/xormania/xorder). Nothing here is built yet.
**Consumers:** this repository's `bin/dev` environment, its CI, and later UXor when it adopts the package.

## 1. What the image replaces

`Dockerfile` in this repository is an overlay on `ghcr.io/xormania/php-browser:8.4-trixie-v1.2.4`. It adds the
patched Mago language server compiled from Rust, Python 3.12 with uv and the pinned Serena, Node 22, Chrome for
Testing and `chrome-devtools-mcp`, and Mago's release binary. The Rust build and the Serena install are minutes
and gigabytes per developer and per CI run. Everything in that overlay is toolchain, not project behavior, so it
belongs in xorder. After publication, this repository's Dockerfile reduces to a `FROM` line plus the
`docker/` scripts, and `compose.yaml` can pull the image directly with no build step.

Pins in this document match `toolchain.lock.json` at the time of writing. The lock file is the source of truth
when they diverge.

## 2. Line layout

Two lines, so the slow layer stays stable while the fast-moving browser pins can refresh independently.

| Line | Parent | Purpose |
| --- | --- | --- |
| `php-mago-serena/8.4-trixie` | `php-browser/8.4-trixie` | PHP 8.4 development plus Mago (release and patched LSP build), Python 3.12, uv, Serena v2 with the Mago SolidLSP adapter. |
| `php-chrome-dev/8.4-trixie` | `php-mago-serena/8.4-trixie` | Adds Node 22, Chrome for Testing, and `chrome-devtools-mcp`. The image this project runs on. |

An `8.5-trixie` pair can follow the same definitions when a consumer needs it. The PoC verified the Mago and
Serena tuple on PHP 8.5; this project targets 8.4 because UXor declares PHP `>=8.4` and Symfony `8.1.*`.

`php-browser` is the parent rather than `php-dev` because its Chromium runtime libraries are exactly what Chrome
for Testing needs, and Panther stays available for consumers who want it.

## 3. Inherited from the parent

From the `php-browser/8.4-trixie` v1.2.4 release record, and required to remain true:

- PHP 8.4.x CLI on Debian trixie, with `intl`, `mbstring`, `curl`, `zip`, `bcmath`, `dom`, `xml`, `pdo_sqlite`,
  `pdo_pgsql`, `pdo_mysql`, `gd`, `redis`, `sockets`, `pcntl`, `xdebug` (off by default), `pcov` (off by default).
- Composer 2.x, Symfony CLI, Infection, `library-php-tests`, `library-php-coverage`, `phpstan-isolated`.
- Debian Chromium with chromedriver and `PANTHER_CHROME_BINARY` set.
- `bash`, `git`, `gh`, `curl`, `jq`, `rg`, `psql`, `python3` (3.13, Debian's).
- User `dev` uid 1000, `HOME=/home/dev`, `COMPOSER_HOME=/home/dev/.composer`, workspace `/workspace`.
- `library-entrypoint` honoring `PUID`/`PGID`, dropping privileges with `gosu`, and `LIBRARY_CA_FILE` for proxy CAs.

## 4. Line `php-mago-serena/8.4-trixie`

### Capabilities

`mago`, `mago-lsp-extensions`, `mago-sdk-compatible`, `python-3.12`, `uv`, `serena-v2-repl`, `serena-mago-adapter`.

### Locked inputs

| Input | Value | Notes |
| --- | --- | --- |
| Mago release binary | `1.58.2`, `mago-1.58.2-x86_64-unknown-linux-gnu.tar.gz`, sha256 `80b6e6ed3cd2fe2da348f9cd83d23e638f2ccd44988d48bebd766c20ccd30dc2` | Installed as `/usr/local/bin/mago-baseline`. |
| Mago source revision | `46df50c96d93d0ac3655c116c375574277cf0b30` | Same revision as the release. MANA worker protocol 2.1. |
| Mago LSP extension patch | `mago-lsp-extensions.patch`, sha256 `ca955e0db6023a997fe708d46d3bd0b92e6dd91237aee7c206f13768effdea11` | From mago-serena_v2-poc. Adds external analyzer workers and `mago/symbolReferences`. |
| Rust toolchain image | `rust:1.99.0-bookworm@sha256:114c7a4425406451c2866b6aafe69fe29b1b298832db1277d411ac73c82d04d6` | Build stage only. `cargo build --locked --release`. |
| Python image | `python:3.12.12-slim-trixie@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c` | Serena's lock requires `3.12.*`. Copied from this image; `/usr/local/bin/python3` becomes 3.12. |
| uv | `ghcr.io/astral-sh/uv:0.12.8@sha256:d1cbaeadc234fe19c0d93daabcf5e98738cd93c6d1dd4918ef6aa30735feb23a` | |
| Serena source revision | `9e1cced0c34ed48d668e179f7c56c77b4d14a3e3` | `serena-agent` from git, via the uv lock. |
| Serena facade patch | `serena-symbol-references.patch`, sha256 `57385a9e49d8a490e696f49b3c62d16e8685703d9531899372a3c41a28270051` | Adds `get_symbol_references` to the REPL LSP facade. |
| uv lock | `tools/serena/uv.lock` in this repository | Root project name `mago-serena-poc`; keep it so `--frozen` resolves. |
| Adapter | `tools/serena/adapter`, `serena-mago-adapter 0.1.0` | Registers `ExternalLanguageServerId("mago")`. |

### Build steps

1. Fetch Mago at the revision, verify, apply the patch with `git apply --check` then `git apply`, assert
   `Cargo.lock`, `composer/` and `crates/extension/src/protocol.rs` are unchanged, build with `--locked`.
   Record `Cargo.lock` sha256, patch sha256, source sha, `rustc --version`.
2. Install the release tarball as `mago-baseline` after sha256 check. Install the patched build as `mago`.
3. Copy Python 3.12 `/usr/local` and `uv`. `uv sync --frozen --no-dev` into `/opt/venv` with
   `UV_PYTHON_DOWNLOADS=never`. Run `apply_serena.py`, which checks source, patch and result hashes and is
   idempotent. Record its JSON output.
4. Keep Mago's and Serena's licenses under `/opt/licenses/`.

### Filesystem and environment contract

| Path or variable | Value |
| --- | --- |
| `/usr/local/bin/mago` | patched build |
| `/usr/local/bin/mago-baseline` | upstream release build |
| `/opt/venv/bin/serena` | Serena CLI; `/opt/venv/bin` is on `PATH` |
| `/opt/xorder/serena/config/serena_config.yml` | global config seed: dashboard off, REPL agent interface, `ls_specific_settings.mago.ignore_vendor: false` |
| `/opt/xorder/serena/config/project.yml` | project template: `language_servers: [mago]` |
| `SERENA_HOME` | `/home/dev/serena`; the entrypoint seeds `serena_config.yml` there if absent |
| `MAGO_EXPERIMENTAL_SERVER` | `1` |
| `PYTHONUNBUFFERED` | `1` |

### Verification in xorder's publication run

- `mago --version` prints `mago 1.58.2`; `mago-baseline --version` matches.
- `sha256sum /usr/local/bin/mago` is recorded; the PoC recorded `5cfaa051b9cb23f63cbcd8ec1703538c1f2789ff21ad068b239678631f701e46` for the same inputs on a different builder. Byte equality across builders is not required; the value is retained.
- `serena --version` runs from `/opt/venv`. `python -c "import serena_mago"` succeeds.
- The patched Mago responds to `initialize` over stdio with `MAGO_EXPERIMENTAL_SERVER=1` on a one-file PHP workspace, and advertises the `mago/symbolReferences` capability the patch adds.
- Serena starts `start-mcp-server --project <tmp> --transport stdio --agent-interface REPL` against a one-file PHP project with `language_servers: [mago]` and answers `initial_instructions`.
- The Mago native regression test the PoC ran, `cargo test -p mago --bin mago language_server::tests::external_analyzers`, as an optional build target behind a build argument.

## 5. Line `php-chrome-dev/8.4-trixie`

### Capabilities

`node`, `npm`, `chrome-for-testing`, `chrome-devtools-mcp`, `chromium` (inherited), `panther` (inherited).

### Locked inputs

| Input | Value | Notes |
| --- | --- | --- |
| Node | `node:22-trixie@sha256:77d0c7953e80648137a237496c8edbcb3a14bedc5c5298b93a6d0dfa6c3e1271` | Same digest xorder's `php-browser` record pins. Copy `/usr/local/bin/node` and `/usr/local/lib/node_modules`, symlink `npm` and `npx`. |
| Chrome for Testing | `157.0.8103.38` linux64, `https://storage.googleapis.com/chrome-for-testing-public/157.0.8103.38/linux64/chrome-linux64.zip` | The CfT index publishes no checksum. Record the installed binary sha256 at build. Stable channel on 2026-11-09. |
| chrome-devtools-mcp | npm `1.12.0` | Installed globally. Node engines `^20.19.0 || ^22.12.0 || >=23`. |

Chrome for Testing is installed in addition to the parent's Debian Chromium because `chrome-devtools-mcp` states
it supports Google Chrome and Chrome for Testing only. Chrome 157 satisfies `--autoConnect` (144+) and the
WebMCP tool category (150+ with `--enable-features=WebMCP`).

### Filesystem and environment contract

| Path or variable | Value |
| --- | --- |
| `/opt/chrome-linux64/chrome`, symlink `/usr/local/bin/chrome` | Chrome for Testing |
| `/opt/chrome-version` | the CfT version string |
| `/usr/local/bin/chrome-devtools-mcp` | npm global bin |
| `CHROME_PATH` | `/usr/local/bin/chrome` |
| `CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS` | `1` |
| `CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS` | `1` |

### Verification in xorder's publication run

- `node --version` is `v22.x`; `npm --version` works.
- `chrome --version` prints the locked CfT version; `chromium --version` still prints the parent's version.
- `chrome --headless=new --no-sandbox --disable-gpu --dump-dom about:blank` exits 0 with `shm_size` 1g or
  `--disable-dev-shm-usage`.
- `chrome-devtools-mcp --headless --isolated --executablePath /usr/local/bin/chrome` answers an MCP
  `initialize` and `tools/list` over stdio, and `list_pages` returns one page. Run with `CI=1` so no usage
  statistics are sent.
- With `--categoryExperimentalThirdParty`, `tools/list` includes `list_3p_developer_tools` and
  `execute_3p_developer_tool`.

## 6. Image identity record

Both lines write `/opt/xorder/image-identity.json` at build time, in addition to xorder's release record. The
Mago SolidLSP adapter reads the Mago binary hash from this file and refuses to start a mismatched executable.
Required keys:

```
php, composer, node, chrome_for_testing, chromium_base, symfony_cli,
mago, mago_binary_sha256, mago_baseline, mago_baseline_binary_sha256,
mago_source_sha, mago_patch_sha256, mago_cargo_lock_sha256, mago_rust_version,
python, uv, serena (apply_serena.py output), serena_facade_sha256, serena_uv_lock_sha256,
chrome_binary_sha256, chrome_devtools_mcp
```

Until the image exists, this repository writes the same record at `/opt/dev/image-identity.json`. The adapter
path moves with it.

## 7. Entrypoint and runtime contract

- Keep `library-entrypoint` as the entrypoint. `PUID`/`PGID` remap the `dev` user; `--user` is not used by this
  project's compose file.
- Provide a chained second-stage entrypoint hook, or accept `/opt/xorder/serena/entrypoint` as the `CMD`
  wrapper, that creates `SERENA_HOME` and seeds `serena_config.yml` when absent. It must run after privileges
  drop so the seeded file is owned by the mapped user.
- Default `CMD` is `bash`. This project overrides it with PHP's built-in server.
- No daemons, no Docker socket, no credentials in the image. `/workspace`, `/home/dev`, `/evidence` and
  `/packages` are bind mounts supplied by the consumer; the image only creates them empty.
- `/dev/shm`: document that Chrome needs `shm_size: 1gb` or `--disable-dev-shm-usage`.

## 8. CI usage

Jobs this repository will run on `php-chrome-dev/8.4-trixie`, pulled by digest, no image build in CI:

| Job | What it runs | Network it needs |
| --- | --- | --- |
| identity | `cat /opt/xorder/image-identity.json`, compare pins to `toolchain.lock.json` | none |
| fixture install | copy `fixtures/app`, `composer install` from lock, `cache:clear`, readiness probe | Packagist, GitHub for the two package repositories |
| mago native | `analyze`, `lint`, `guard --structural`, `format --check` | none |
| mate-prepare and enriched | `bin/dev mate-prepare`, `bin/mago --profile symfony` on and `--extension-off`, compare graph and attestation | none after install |
| serena smoke | start Serena MCP over stdio against the fixture, `initial_instructions`, `s.info("lsp")`, one `find_symbol` | none |
| chrome owned mode | `bin/chrome-mcp` against the fixture served in the same container, `list_pages`, one `navigate_page`, one `take_snapshot` | none |
| phpunit | `vendor/bin/phpunit` in the fixture | none |

Needs from the image for CI specifically:

- Pull by digest with `docker/login-action` to GHCR as today; public pull is fine.
- Layer size matters for runner time. Keep the Rust build artifacts out of the final image. Remove uv and npm
  caches. Target under 2.5 GB compressed for `php-chrome-dev`.
- The `PUID`/`PGID` remap must work with GitHub's runner uid 1001.
- Chrome must run with `--no-sandbox` where the runner forbids user namespaces. The MCP server passes Chrome
  flags through `--chromeArg`; document the exact invocation.
- `CI=1` disables `chrome-devtools-mcp` usage statistics by itself. Keep the env defaults anyway.

Hosts the build itself touches, for xorder's own allowlist: `github.com`, `api.github.com`,
`objects.githubusercontent.com`, `storage.googleapis.com`, `registry.npmjs.org`, `pypi.org`,
`files.pythonhosted.org`, `crates.io`, `static.crates.io`, `index.crates.io`, `deb.debian.org`,
`security.debian.org`, `ghcr.io`, `registry-1.docker.io`.

## 9. Limitations to state in the definitions

- Serena here is the Mago-backed variant. It is distinct from `php-serena`, which is PHPactor-backed and 8.5 only.
- `mago-baseline` is the upstream release build, not a local unpatched build of the same revision.
- The Mago LSP patch is a repository extension, not an upstream API. The PoC recorded an unfixed external-edit
  span defect in this path with a restart workaround.
- The Mago PHP SDK a consumer installs must be at the same source revision (MANA 2.1). Mago 1.59 moved to
  MANA 2.2 and is incompatible with this pin.
- Chrome for Testing has no published checksum; provenance is the recorded binary hash plus the version URL.
- Browser built-in AI APIs (Summarizer, Prompt) are not testable in this image. They need an eligible device
  and model download; headless Chrome for Testing in a container does not establish their availability.
- Linux amd64 only.

## 10. Refresh policy

- `php-mago-serena` refreshes when Mago or Serena pins change deliberately, with the patches re-validated
  against the new base. Expect this to be rare and reviewed.
- `php-chrome-dev` refreshes with Chrome DevTools MCP releases (roughly monthly) and Chrome for Testing stable.
  Each refresh records the new CfT version, binary hash and MCP version in the release record.
- This repository adopts a refreshed digest only after `./bin/dev up`, `mate-prepare`, the enriched analysis
  and the two MCP smoke checks pass on it, then updates `toolchain.lock.json` and the `FROM` line together.
- Adopt xorder's downstream support check before 2026-11-11 08:00 UTC.

## 11. Migration in this repository once published

1. Replace the multi-stage `Dockerfile` with `FROM ghcr.io/xormania/php-chrome-dev:8.4-trixie-vX.Y.Z@sha256:…`
   plus `COPY docker /opt/dev/docker` and the `CMD`. Or drop the Dockerfile and set `image:` in `compose.yaml`
   directly, moving `router.php` and `setup` into a bind mount.
2. Point `tools/serena/adapter` at `/opt/xorder/image-identity.json`, or have the image set
   `DEV_IMAGE_IDENTITY` and read that.
3. Remove `tools/serena/patches`, `uv.lock`, `pyproject.toml` and `adapter` from this repository once xorder
   owns them, keeping only `config/` and a pointer to the xorder revision that holds them.
4. Update `toolchain.lock.json` to reference the xorder release record instead of individual upstream digests.
