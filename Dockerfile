# syntax=docker/dockerfile:1.7
# Development image for writing the Symfony-Chrome package.
# Base: xorder php-browser 8.4-trixie v1.2.3 (PHP 8.4.26, Composer, Symfony CLI, Chromium 155 + runtime libs,
# PUID/PGID entrypoint, HOME=/home/dev, workspace /workspace). This file adds Node 22, Chrome for Testing
# (the browser chrome-devtools-mcp officially supports) and chrome-devtools-mcp. Pins: toolchain.lock.json.
# Candidate for a dedicated xorder line once the contract settles.

FROM docker.io/library/node:22-trixie@sha256:77d0c7953e80648137a237496c8edbcb3a14bedc5c5298b93a6d0dfa6c3e1271 AS node
FROM docker.io/library/python:3.12.12-slim-trixie@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c AS python
FROM ghcr.io/astral-sh/uv:0.12.8@sha256:d1cbaeadc234fe19c0d93daabcf5e98738cd93c6d1dd4918ef6aa30735feb23a AS uv

# Patched Mago language server, ported from mago-serena_v2-poc: exact upstream revision plus the
# repository's LSP extension patch (external analyzer workers, mago/symbolReferences). Several minutes, GBs.
FROM docker.io/library/rust:1.99.0-bookworm@sha256:114c7a4425406451c2866b6aafe69fe29b1b298832db1277d411ac73c82d04d6 AS mago-build
ARG MAGO_REV=46df50c96d93d0ac3655c116c375574277cf0b30
ARG MAGO_BUILD_JOBS=4
WORKDIR /src
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export GIT_SSL_CAINFO=/run/secrets/proxy_ca; fi; \
    git init . && git remote add origin https://github.com/carthage-software/mago.git \
    && git fetch --depth 1 origin "$MAGO_REV" && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "$MAGO_REV"
COPY tools/serena/patches/mago-lsp-extensions.patch /candidate.patch
RUN echo 'ca955e0db6023a997fe708d46d3bd0b92e6dd91237aee7c206f13768effdea11  /candidate.patch' | sha256sum --check --strict \
    && git apply --check /candidate.patch && git apply /candidate.patch \
    && git diff --exit-code -- Cargo.lock composer crates/extension/src/protocol.rs
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/src/target \
    --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export CARGO_HTTP_CAINFO=/run/secrets/proxy_ca; fi; \
    cargo build --locked --release -j "$MAGO_BUILD_JOBS" && cp target/release/mago /mago \
    && sha256sum Cargo.lock > /mago-cargo-lock.sha256 && sha256sum /candidate.patch > /mago-patch.sha256 \
    && git rev-parse HEAD > /mago-source.sha && rustc --version > /mago-rust-version.txt

FROM ghcr.io/xormania/php-browser:8.4-trixie-v1.2.3@sha256:ad37c8138c4aacdbba8c64f0436669104e0e57dd206aa6f5099c512440f65a3e
ARG CHROME_VERSION=157.0.8103.38
ARG CHROME_MCP_VERSION=1.12.0

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# Owned browser for container-side runs. Debian Chromium from the base stays available for Panther.
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export CURL_CA_BUNDLE=/run/secrets/proxy_ca; fi; \
    curl --fail --location --retry 3 -o /tmp/chrome.zip \
      "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chrome-linux64.zip" \
    && unzip -q /tmp/chrome.zip -d /opt && rm /tmp/chrome.zip \
    && ln -s /opt/chrome-linux64/chrome /usr/local/bin/chrome \
    && printf '%s\n' "$CHROME_VERSION" > /opt/chrome-version

RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm install -g --no-fund --no-audit "chrome-devtools-mcp@${CHROME_MCP_VERSION}" \
    && npm cache clean --force

# Python 3.12 for the pinned Serena (its lock requires 3.12.*; the base ships 3.13) and uv.
COPY --from=python /usr/local /usr/local
RUN ldconfig
COPY --from=uv /uv /usr/local/bin/uv

# Mago: PHP analyzer, linter, formatter and structural guard. Upstream release binary, hash-pinned.
ARG MAGO_VERSION=1.58.2
ARG MAGO_SHA256=80b6e6ed3cd2fe2da348f9cd83d23e638f2ccd44988d48bebd766c20ccd30dc2
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export CURL_CA_BUNDLE=/run/secrets/proxy_ca; fi; \
    curl --fail --location --retry 3 -o /tmp/mago.tar.gz \
      "https://github.com/carthage-software/mago/releases/download/${MAGO_VERSION}/mago-${MAGO_VERSION}-x86_64-unknown-linux-gnu.tar.gz" \
    && echo "${MAGO_SHA256}  /tmp/mago.tar.gz" | sha256sum --check --strict \
    && tar -xzf /tmp/mago.tar.gz -C /opt && rm /tmp/mago.tar.gz \
    && install -m 0755 "/opt/mago-${MAGO_VERSION}-x86_64-unknown-linux-gnu/mago" /usr/local/bin/mago \
    && mkdir -p /opt/licenses/mago \
    && cp "/opt/mago-${MAGO_VERSION}-x86_64-unknown-linux-gnu/LICENSE-MIT" "/opt/mago-${MAGO_VERSION}-x86_64-unknown-linux-gnu/LICENSE-APACHE" /opt/licenses/mago/ \
    && rm -rf "/opt/mago-${MAGO_VERSION}-x86_64-unknown-linux-gnu"

# The upstream release becomes the unpatched comparison executable; the patched build is primary.
RUN mv /usr/local/bin/mago /usr/local/bin/mago-baseline
COPY --from=mago-build /mago /usr/local/bin/mago
COPY --from=mago-build /mago-patch.sha256 /mago-cargo-lock.sha256 /mago-source.sha /mago-rust-version.txt /opt/dev/

# Serena v2 at the pinned revision with the REPL facade patch and the Mago SolidLSP adapter.
COPY tools/serena /opt/dev/serena
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca GIT_SSL_CAINFO=/run/secrets/proxy_ca; fi; \
    cd /opt/dev/serena && uv sync --frozen --no-dev --python /usr/local/bin/python3 \
    && /opt/venv/bin/python /opt/dev/serena/patches/apply_serena.py > /opt/dev/serena-patch.json \
    && rm -rf /root/.cache/uv

COPY docker /opt/dev/docker
COPY toolchain.lock.json /opt/dev/toolchain.lock.json
RUN /opt/venv/bin/python /opt/dev/docker/identity.py > /opt/dev/image-identity.json \
    && mkdir -p /evidence /packages /private && chown dev:dev /evidence

ENV PATH=/opt/venv/bin:$PATH \
    SERENA_HOME=/home/dev/serena \
    MAGO_EXPERIMENTAL_SERVER=1 \
    PYTHONUNBUFFERED=1 \
    CHROME_PATH=/usr/local/bin/chrome \
    CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS=1 \
    CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS=1 \
    DEV_EVIDENCE=/evidence
WORKDIR /workspace
# Base entrypoint handles PUID/PGID and drops privileges with gosu, then ours seeds Serena's config.
ENTRYPOINT ["bash", "/usr/local/bin/library-entrypoint", "/opt/dev/docker/entrypoint"]
CMD ["php", "-S", "0.0.0.0:8000", "-t", "public", "/opt/dev/docker/router.php"]
