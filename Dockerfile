# syntax=docker/dockerfile:1.7
# Development image for writing the Symfony-Chrome package.
# Base: xorder php-browser 8.4-trixie v1.2.4 (PHP 8.4.27, Composer, Symfony CLI, Chromium 156 + runtime libs,
# PUID/PGID entrypoint, HOME=/home/dev, workspace /workspace). This file adds Node 22, Chrome for Testing
# (the browser chrome-devtools-mcp officially supports) and chrome-devtools-mcp. Pins: toolchain.lock.json.
# Candidate for a dedicated xorder line once the contract settles.

FROM docker.io/library/node:22-trixie@sha256:77d0c7953e80648137a237496c8edbcb3a14bedc5c5298b93a6d0dfa6c3e1271 AS node

FROM ghcr.io/xormania/php-browser:8.4-trixie-v1.2.4@sha256:628021c4e31dbd226183aefb2186b363849475bcba8a5e176e684e7491054ee7
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

COPY docker /opt/dev/docker
COPY toolchain.lock.json /opt/dev/toolchain.lock.json
RUN python3 /opt/dev/docker/identity.py > /opt/dev/image-identity.json \
    && mkdir -p /evidence /packages /private && chown dev:dev /evidence

ENV CHROME_PATH=/usr/local/bin/chrome \
    CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS=1 \
    CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS=1 \
    DEV_EVIDENCE=/evidence
WORKDIR /workspace
# Base entrypoint handles PUID/PGID and drops privileges with gosu.
CMD ["php", "-S", "0.0.0.0:8000", "-t", "public", "/opt/dev/docker/router.php"]
