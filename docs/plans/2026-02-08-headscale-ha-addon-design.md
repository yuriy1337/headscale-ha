# Headscale Home Assistant Add-on Design

## Overview

A single Home Assistant add-on that runs Headscale (self-hosted Tailscale control server) and Headplane (feature-complete web UI) in one container. Users install it, set their server URL, and manage their entire Tailscale network from the HA sidebar.

## Architecture

```
┌─ HA Add-on Container ─────────────────────┐
│                                            │
│   s6-overlay (process supervisor)          │
│   ├── headscale server  (port 8080)        │
│   └── headplane UI      (port 3000)        │
│                                            │
│   /data/headscale/       (persistent)      │
│   /data/headscale/config.yaml              │
│   /data/headscale/db.sqlite                │
└────────────────────────────────────────────┘
         │                    │
    port 8080            HA Ingress
    (headscale API)      (Headplane UI in sidebar)
```

- **Headscale**: Tailscale-compatible coordination server (Go binary)
- **Headplane**: Feature-complete web UI for managing headscale (TypeScript + Go)
- **s6-overlay**: Process supervisor (included in HA base images)
- **Target architectures**: `amd64`, `aarch64`

Headscale handles node registration, key exchange, and discovery. Actual VPN traffic is peer-to-peer via WireGuard — the server is lightweight (~30-50 MB RAM).

## Repository Structure

```
headscale-ha/
├── repository.yaml
├── headscale/
│   ├── config.yaml
│   ├── Dockerfile
│   ├── rootfs/
│   │   ├── etc/
│   │   │   └── s6-overlay/s6-rc.d/
│   │   │       ├── headscale/
│   │   │       │   ├── run
│   │   │       │   ├── finish
│   │   │       │   └── type
│   │   │       ├── headplane/
│   │   │       │   ├── run
│   │   │       │   ├── finish
│   │   │       │   └── type
│   │   │       └── init-headscale/
│   │   │           ├── run
│   │   │           ├── up
│   │   │           └── type
│   │   └── usr/local/bin/
│   │       └── generate-config.sh
│   ├── DOCS.md
│   └── CHANGELOG.md
└── README.md
```

## User-Facing Configuration

Exposed in HA's Configuration tab:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `server_url` | string | (required) | Public URL for headscale (e.g., `https://headscale.example.com`) |
| `headscale_port` | int | `8080` | Internal port headscale listens on |
| `dns_base_domain` | string | `tailnet.local` | MagicDNS base domain |
| `dns_nameservers` | list | `["1.1.1.1", "8.8.8.8"]` | Upstream DNS servers |
| `log_level` | string | `info` | Log verbosity (`trace`, `debug`, `info`, `warn`, `error`) |

## Port Mapping

```yaml
ports:
  8080/tcp: 8080    # headscale server (for reverse proxy)
```

Headplane UI is accessible via HA Ingress (sidebar panel) on internal port 3000. Optional external access via separate port mapping.

## Boot Sequence

1. **init-headscale** (oneshot):
   - Reads HA addon options via Bashio
   - Creates `/data/headscale/` directory structure
   - Generates headscale `config.yaml`
   - Initializes SQLite database on first run
   - Creates API key for Headplane if first run, stores in `/data/headscale/api_key`

2. **headscale** (longrun):
   - Starts headscale server
   - Depends on init-headscale completing

3. **headplane** (longrun):
   - Starts Headplane web UI
   - Connects to headscale using auto-generated API key
   - Depends on headscale being ready

## Dockerfile Strategy

Multi-stage build:
1. **Stage 1**: Download headscale binary from official GitHub release for target arch
2. **Stage 2**: Download/build Headplane for target arch
3. **Stage 3**: Final image based on HA base image — copy binaries, add rootfs overlay

## First Run Experience

1. User installs addon from repository
2. Sets `server_url` in Configuration tab
3. Starts the addon
4. Init script generates config, creates API key automatically
5. User clicks "Headscale" in HA sidebar → Headplane loads
6. Create first user, register first device

No manual API key setup or config file editing required.

## Configuration Changes

When user changes options and restarts:
- `generate-config.sh` regenerates headscale config from new options
- Database, API key, and all node registrations preserved
- Only config values change

## Backups

HA's built-in backup includes `/data/`, covering:
- Headscale config, database, private keys
- All registered nodes, users, ACLs
- Headplane API key

Full restore = everything works, no re-registration.

## External Access (TLS)

The addon runs headscale on HTTP internally. Users handle TLS externally via:
- **Nginx Proxy Manager** (recommended) — proxy `headscale.domain.com` → `localhost:8080` with Let's Encrypt
- Or any reverse proxy: Caddy, Traefik, Cloudflare Tunnel, etc.

## Publishing

1. **Phase 1**: Standalone GitHub repository, users add as custom addon repository
2. **Phase 2**: Submit to Community Add-ons (hassio-addons) once stable

CI/CD via GitHub Actions:
- Build multi-arch Docker images on push/tag
- Publish to GitHub Container Registry
- Lint and validate addon structure
