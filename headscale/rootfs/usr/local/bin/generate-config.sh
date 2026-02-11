#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
# Generates headscale and headplane configuration from HA addon options

bashio::log.info "Generating configuration..."

# Read addon options
SERVER_URL=$(bashio::config 'server_url')
HEADSCALE_PORT=$(bashio::config 'headscale_port')
DNS_BASE_DOMAIN=$(bashio::config 'dns_base_domain')
LOG_LEVEL=$(bashio::config 'log_level')

# Validate required options
if bashio::var.is_empty "${SERVER_URL}"; then
    bashio::log.fatal "server_url is required. Please configure it in the addon settings."
    bashio::exit.nok
fi

# Create data directories
mkdir -p /data/headscale
mkdir -p /var/lib/headplane/agent

# Build DNS nameservers list
DNS_NAMESERVERS=""
for server in $(bashio::config 'dns_nameservers'); do
    DNS_NAMESERVERS="${DNS_NAMESERVERS}
      - \"${server}\""
done

# Generate headscale config
cat > /data/headscale/config.yaml << EOF
server_url: "${SERVER_URL}"
listen_addr: "0.0.0.0:${HEADSCALE_PORT}"
metrics_listen_addr: "127.0.0.1:9090"
grpc_listen_addr: "127.0.0.1:50443"
grpc_allow_insecure: false

private_key_path: /data/headscale/private.key
noise:
  private_key_path: /data/headscale/noise_private.key

prefixes:
  v4: "100.64.0.0/10"
  v6: "fd7a:115c:a1e0::/48"

database:
  type: sqlite
  sqlite:
    path: /data/headscale/db.sqlite

log:
  level: "${LOG_LEVEL}"

dns:
  base_domain: "${DNS_BASE_DOMAIN}"
  magic_dns: true
  nameservers:
    global:${DNS_NAMESERVERS}

policy:
  mode: file
  path: /data/headscale/acl.json

derp:
  server:
    enabled: false
  urls:
    - "https://controlplane.tailscale.com/derpmap/default"
  auto_update_enabled: true
  update_frequency: "24h"
EOF

bashio::log.info "Headscale config written to /data/headscale/config.yaml"
bashio::log.info "Generated config:"
cat /data/headscale/config.yaml

# Create default ACL policy if it doesn't exist
if [ ! -f /data/headscale/acl.json ]; then
    cat > /data/headscale/acl.json << 'EOF'
{
  "acls": [
    {
      "action": "accept",
      "src": ["*"],
      "dst": ["*:*"]
    }
  ]
}
EOF
    bashio::log.info "Default ACL policy created (allow all)"
fi

# Generate API key for Headplane on first run
API_KEY_FILE="/data/headscale/api_key"
if [ ! -f "${API_KEY_FILE}" ]; then
    bashio::log.info "First run detected, will generate API key after headscale starts..."

    # Write a helper script that runs after headscale is up
    cat > /usr/local/bin/generate-api-key.sh << 'KEYSCRIPT'
#!/usr/bin/with-contenv bashio
# Wait for headscale to be ready
for i in $(seq 1 60); do
    if /usr/local/bin/headscale --config /data/headscale/config.yaml apikeys list > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Generate the API key
API_KEY=$(/usr/local/bin/headscale --config /data/headscale/config.yaml apikeys create --expiration 876000h 2>&1)
if [ $? -eq 0 ]; then
    echo "${API_KEY}" > /data/headscale/api_key
    bashio::log.info "API key generated and stored"
else
    bashio::log.error "Failed to generate API key: ${API_KEY}"
fi
KEYSCRIPT
    chmod +x /usr/local/bin/generate-api-key.sh
fi

# Generate Headplane config
COOKIE_SECRET=$(head -c 32 /dev/urandom | base64 | head -c 32)
# Persist cookie secret so sessions survive restarts
if [ -f /data/headscale/cookie_secret ]; then
    COOKIE_SECRET=$(cat /data/headscale/cookie_secret)
else
    echo "${COOKIE_SECRET}" > /data/headscale/cookie_secret
fi

# Read API key if it exists
HEADPLANE_API_KEY=""
if [ -f "${API_KEY_FILE}" ]; then
    HEADPLANE_API_KEY=$(cat "${API_KEY_FILE}")
fi

# Write Headplane config to the default location it expects
mkdir -p /etc/headplane
cat > /etc/headplane/config.yaml << EOF
server:
  host: "127.0.0.1"
  port: 3001
  base_url: "http://localhost:3001"
  cookie_secret: "${COOKIE_SECRET}"
  cookie_secure: false
  cookie_max_age: 86400
  data_path: /var/lib/headplane

headscale:
  url: "http://127.0.0.1:${HEADSCALE_PORT}"
  config_path: /data/headscale/config.yaml
  config_strict: false

integration:
  proc:
    enabled: true

oidc:
  disable_api_key_login: false
  issuer: "https://unused.example.com"
  client_id: "unused"
  token_endpoint_auth_method: "client_secret_basic"
EOF

bashio::log.info "Headplane config written to /etc/headplane/config.yaml"

# Also set env var as backup
printf "/etc/headplane/config.yaml" > /var/run/s6/container_environment/HEADPLANE_CONFIG

bashio::log.info "Configuration generation complete"
