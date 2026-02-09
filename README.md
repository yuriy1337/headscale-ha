# Headscale HA - Home Assistant Add-on

A Home Assistant add-on that runs [Headscale](https://headscale.net/) (self-hosted Tailscale control server) with [Headplane](https://github.com/tale/headplane) web UI.

## What is this?

This add-on turns your Home Assistant device into a Tailscale-compatible VPN control plane. Manage your own private mesh VPN network directly from the Home Assistant sidebar.

## Features

- **Headscale** — Self-hosted Tailscale control server
- **Headplane** — Feature-complete web UI with ACL, DNS, and OIDC support
- **HA Integration** — Configurable via HA addon settings, accessible via sidebar
- **Automatic Setup** — Config generation, API key creation, database initialization
- **Backup Support** — All data included in HA backups

## Installation

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**
2. Click the **⋮** menu → **Repositories**
3. Add this repository URL
4. Install **Headscale**
5. Configure your `server_url` and start the add-on

## Requirements

- Home Assistant OS or Supervised
- A domain name with SSL (via Nginx Proxy Manager or similar)
- Port 443 forwarded to your reverse proxy

## Supported Architectures

- `amd64` (x86-64)
- `aarch64` (Raspberry Pi 3/4/5, ARM servers)
