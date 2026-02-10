ARG BUILD_FROM=ghcr.io/hassio-addons/base:20.0.1

# Stage 1: Get headscale binary
FROM ghcr.io/juanfont/headscale:0.28.0 AS headscale

# Stage 2: Get headplane build artifacts
FROM ghcr.io/tale/headplane:0.6.1-shell AS headplane

# Stage 3: Final image
# hadolint ignore=DL3006
FROM ${BUILD_FROM}

# Install Node.js (required for Headplane)
RUN apk add --no-cache \
    nodejs \
    nginx \
    bash \
    curl

# Copy headscale binary
COPY --from=headscale /ko-app/headscale /usr/local/bin/headscale
RUN chmod +x /usr/local/bin/headscale

# Copy headplane application
COPY --from=headplane /app/build /opt/headplane/build
COPY --from=headplane /app/drizzle /opt/headplane/drizzle
COPY --from=headplane /app/node_modules /opt/headplane/node_modules
COPY --from=headplane /usr/libexec/headplane/agent /usr/libexec/headplane/agent

# Patch Headplane to serve from / instead of /admin
# and make asset paths relative for HA ingress compatibility
RUN find /opt/headplane/build -type f \( -name '*.js' -o -name '*.html' \) -exec \
    sed -i 's|/admin/|/|g; s|"/admin"|"/"|g; s|href="/assets/|href="assets/|g; s|src="/assets/|src="assets/|g; s|"/assets/|"assets/|g' {} +

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
