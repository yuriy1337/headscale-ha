ARG BUILD_FROM=ghcr.io/hassio-addons/base:20.0.1

# Stage 1: Get headscale binary
FROM ghcr.io/juanfont/headscale:0.28.0 AS headscale

# Stage 2: Build Headplane Go components
FROM golang:1.25.1 AS headplane-go
ARG TARGETARCH

ADD https://github.com/tale/headplane/archive/refs/tags/v0.6.1.tar.gz /tmp/headplane.tar.gz
RUN tar xzf /tmp/headplane.tar.gz -C /tmp && mv /tmp/headplane-0.6.1 /src
WORKDIR /src

RUN ls -la /src/ && head -1 /src/build.sh && GOOS=linux GOARCH=$TARGETARCH CGO_ENABLED=0 \
    sh ./build.sh --wasm --agent --fake-shell --healthcheck \
        --wasm-output /bin/hp_ssh.wasm \
        --agent-output /bin/hp_agent \
        --fake-shell-output /bin/fake-sh \
        --healthcheck-output /bin/hp_healthcheck

RUN chmod +x /bin/hp_ssh.wasm /bin/hp_agent /bin/fake-sh /bin/hp_healthcheck
RUN mkdir -p /var/lib/headplane/agent

# Stage 3: Build Headplane JS app with root prefix
FROM node:22.16-slim AS headplane-js

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
RUN corepack enable

ADD https://github.com/tale/headplane/archive/refs/tags/v0.6.1.tar.gz /tmp/headplane.tar.gz
RUN tar xzf /tmp/headplane.tar.gz -C /tmp && mv /tmp/headplane-0.6.1 /src
WORKDIR /src

# Patch: serve from / instead of /admin
RUN sed -i 's|basename: "/admin/"|basename: "/"|' react-router.config.ts

COPY --from=headplane-go /bin/hp_ssh.wasm /src/app/hp_ssh.wasm
COPY --from=headplane-go /bin/wasm_exec.js /src/app/wasm_exec.js

# Set prefix to empty so vite base becomes "/"
ENV __INTERNAL_PREFIX=""
RUN sh ./build.sh --app --app-install-only
RUN sh ./build.sh --app --skip-pnpm-prune

# Prune dev dependencies
RUN pnpm prune --prod

# Stage 4: Final image
# hadolint ignore=DL3006
FROM ${BUILD_FROM}

# Install Node.js (required for Headplane)
RUN apk add --no-cache \
    nodejs \
    bash \
    curl

# Copy headscale binary
COPY --from=headscale /ko-app/headscale /usr/local/bin/headscale
RUN chmod +x /usr/local/bin/headscale

# Copy headplane application (built from source with root prefix)
COPY --from=headplane-js /src/build /opt/headplane/build
COPY --from=headplane-js /src/drizzle /opt/headplane/drizzle
COPY --from=headplane-js /src/node_modules /opt/headplane/node_modules
COPY --from=headplane-go /bin/hp_agent /usr/libexec/headplane/agent

# Create data directories
RUN mkdir -p /data/headscale /var/lib/headplane/agent

# Copy root filesystem
COPY rootfs /

# Build arguments
ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_DESCRIPTION
ARG BUILD_NAME
ARG BUILD_REF
ARG BUILD_REPOSITORY
ARG BUILD_VERSION

# Labels
LABEL \
    io.hass.name="${BUILD_NAME}" \
    io.hass.description="${BUILD_DESCRIPTION}" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version=${BUILD_VERSION} \
    org.opencontainers.image.title="${BUILD_NAME}" \
    org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
    org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.created=${BUILD_DATE} \
    org.opencontainers.image.revision=${BUILD_REF} \
    org.opencontainers.image.version=${BUILD_VERSION}
