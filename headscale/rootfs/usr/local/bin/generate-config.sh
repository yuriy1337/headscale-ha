#!/usr/bin/with-contenv bash
# shellcheck shell=bash
# Generates headscale and headplane configuration from HA addon options

# Source bashio for logging if available
if command -v _log_info &>/dev/null; then
    _log_info() { _log_info "$@"; }
    _log_fatal() { bashio::log.fatal "$@"; }
    _log_error() { _log_error "$@"; }
    _log_warning() { bashio::log.warning "$@"; }
else
    _log_info() { echo "[INFO] $*"; }
    _log_fatal() { echo "[FATAL] $*"; }
    _log_error() { echo "[ERROR] $*"; }
    _log_warning() { echo "[WARNING] $*"; }
fi

# Read config: try bashio (HA Supervisor), fall back to /data/options.json
_config() {
    local key="$1"
    if command -v bashio::config &>/dev/null && [[ -n "${SUPERVISOR_TOKEN:-}" ]]; then
        bashio::config "$key"
    elif [ -f /data/options.json ]; then
        jq -r ".$key" /data/options.json
    else
        echo ""
    fi
}

# Read config array values (one per line)
_config_array() {
    local key="$1"
    if command -v bashio::config &>/dev/null && [[ -n "${SUPERVISOR_TOKEN:-}" ]]; then
        bashio::config "$key"
    elif [ -f /data/options.json ]; then
        jq -r ".${key}[]" /data/options.json
    fi
}

_log_info "Generating configuration..."

# Read addon options
SERVER_URL=$(_config 'server_url')
HEADSCALE_PORT=$(_config 'headscale_port')
DNS_BASE_DOMAIN=$(_config 'dns_base_domain')
LOG_LEVEL=$(_config 'log_level')

# Validate required options
if [ -z "${SERVER_URL}" ]; then
    _log_fatal "server_url is required. Please configure it in the addon settings."
    exit 1
fi

# Create data directories
mkdir -p /data/headscale
mkdir -p /var/lib/headplane/agent

# Build DNS nameservers list
DNS_NAMESERVERS=""
for server in $(_config_array 'dns_nameservers'); do
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

_log_info "Headscale config written to /data/headscale/config.yaml"
_log_info "Generated config:"
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
    _log_info "Default ACL policy created (allow all)"
fi

# Generate API key for Headplane on first run
API_KEY_FILE="/data/headscale/api_key"
if [ ! -f "${API_KEY_FILE}" ]; then
    _log_info "First run detected, will generate API key after headscale starts..."

    # Write a helper script that runs after headscale is up
    cat > /usr/local/bin/generate-api-key.sh << 'KEYSCRIPT'
#!/usr/bin/with-contenv bash
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
    echo "[INFO] API key generated and stored"
else
    echo "[ERROR] Failed to generate API key: ${API_KEY}"
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
EOF

_log_info "Headplane config written to /etc/headplane/config.yaml"

# Also set env var as backup
printf "/etc/headplane/config.yaml" > /var/run/s6/container_environment/HEADPLANE_CONFIG

_log_info "Configuration generation complete"
