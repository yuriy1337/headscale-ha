# Changelog

## 0.1.26

- Fix auto-login getting stuck when prior attempts left a stale `_ha_al` flag in `sessionStorage`. Replace the persistent flag with a 5-second cookie guard, proactively clear any stale flag, clear an invalid `_hp_auth` cookie before re-auth, and skip auto-login on the logout confirmation page.

## 0.1.0

- Initial release
- Headscale v0.28.0
- Headplane v0.6.1
- Automatic configuration from HA addon options
- Ingress support (HA sidebar)
- Auto-generated API key for Headplane
