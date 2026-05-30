#!/bin/sh
set -eu

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

api_base_url="$(json_escape "${VITE_API_BASE_URL:-}")"
api_token="$(json_escape "${VITE_ORBIS_API_TOKEN:-}")"

cat > /usr/share/nginx/html/config.js <<EOF
globalThis.__ORBIS_CONFIG__ = {
  apiBaseUrl: "${api_base_url}",
  apiToken: "${api_token}"
};
EOF
