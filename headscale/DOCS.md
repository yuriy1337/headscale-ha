# Headscale - Home Assistant Add-on

## About

This add-on runs [Headscale](https://headscale.net/), an open-source self-hosted
implementation of the Tailscale control server, along with
[Headplane](https://github.com/tale/headplane), a feature-complete web UI for
managing your network.

With this add-on, your Home Assistant device becomes the control plane for your
own private Tailscale-compatible VPN network.

## Prerequisites

- A domain name pointing to your Home Assistant's public IP address
- A reverse proxy with SSL (e.g., the Nginx Proxy Manager add-on)
- Port 443 forwarded on your router to the reverse proxy

## Installation

1. Add this repository to your Home Assistant add-on store
2. Install the **Headscale** add-on
3. Go to the **Configuration** tab and set your `server_url`
   (e.g., `https://headscale.example.com`)
4. Start the add-on

## Reverse Proxy Setup (Nginx Proxy Manager)

1. Install the **Nginx Proxy Manager** add-on if you haven't already
2. Add a new proxy host:
   - **Domain**: `headscale.example.com`
   - **Forward Host**: `localhost` (or your HA IP)
   - **Forward Port**: `8080`
   - Enable **SSL** with Let's Encrypt
   - Enable **WebSocket Support**
3. Ensure port 443 is forwarded on your router to your HA device

## First Run

On first start, the add-on will:

1. Generate the Headscale configuration from your settings
2. Initialize the database
3. Create an API key for the web UI automatically

Once started, click **Headscale** in your Home Assistant sidebar to open the
management interface.

## Registering Your First Device

1. Install [Tailscale](https://tailscale.com/download) on the device you want
   to connect
2. Run:
   ```
   tailscale up --login-server=https://headscale.example.com
   ```
3. Open the Headplane UI from the HA sidebar
4. Create a user and approve the device registration

## Configuration Options

### `server_url` (required)

The public URL where clients will reach your Headscale server.
Must include the protocol (e.g., `https://headscale.example.com`).

### `headscale_port` (default: `8080`)

The internal HTTP port Headscale listens on. Point your reverse proxy to this
port.

### `dns_base_domain` (default: `tailnet.local`)

The base domain for MagicDNS. Devices on your network will be reachable at
`<hostname>.<base_domain>`.

### `dns_nameservers` (default: `["1.1.1.1", "8.8.8.8"]`)

Upstream DNS servers used for resolving non-MagicDNS queries.

### `log_level` (default: `info`)

Log verbosity. Options: `trace`, `debug`, `info`, `warn`, `error`.

## Data & Backups

All data is stored in `/data/headscale/`:

- `config.yaml` — Generated Headscale configuration
- `db.sqlite` — Node registrations, users, keys
- `private.key` / `noise_private.key` — Server identity keys
- `acl.json` — Access control policy
- `api_key` — API key for Headplane

This data is included in Home Assistant backups automatically. Restoring a
backup will restore your entire VPN configuration and all registered nodes.

## Troubleshooting

### Clients can't connect

- Verify your domain resolves to your public IP
- Check that port 443 is forwarded through your router
- Verify the reverse proxy is forwarding to port 8080
- Check the add-on logs for errors

### Web UI shows connection error

- The Headscale server may still be starting — wait 10-15 seconds and refresh
- Check the add-on logs for startup errors

### Nodes can't reach each other

- Check if direct connections work (Tailscale uses peer-to-peer by default)
- DERP relays are configured by default using Tailscale's public relay servers
- Review your ACL policy in the Headplane UI

## Advanced

### Custom ACL Policy

The default ACL policy allows all traffic between all nodes. Edit the policy
through the Headplane UI or modify `/data/headscale/acl.json` directly.

### DERP Relay Servers

By default, the add-on uses Tailscale's public DERP relay servers. For better
performance or privacy, you can set up your own DERP server and modify the
headscale configuration.
