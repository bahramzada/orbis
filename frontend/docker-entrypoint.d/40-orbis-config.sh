#!/bin/sh
set -eu

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

api_base_url="$(json_escape "${VITE_API_BASE_URL:-}")"
backend_origin="$(printf '%s' "${VITE_API_BASE_URL:-}" | sed -E 's#^(https?://[^/]+).*$#\1#')"
if [ -z "$backend_origin" ]; then
  backend_origin="'self'"
fi

cat > /usr/share/nginx/html/config.js <<EOF
globalThis.__ORBIS_CONFIG__ = {
  apiBaseUrl: "${api_base_url}"
};
EOF

cat > /etc/nginx/orbis-security-headers.conf <<EOF
add_header Content-Security-Policy "default-src 'self'; connect-src 'self' ${backend_origin}; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self';" always;
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
EOF
