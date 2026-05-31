#!/bin/sh
set -eu

auto_migrate="$(printf '%s' "${DATABASE_AUTO_MIGRATE:-true}" | tr '[:upper:]' '[:lower:]')"

case "$auto_migrate" in
  1|true|yes|on)
    echo "Applying database migrations before starting Orbis API..."
    python -m app.migration_runner
    export DATABASE_AUTO_MIGRATE=false
    ;;
esac

exec "$@"
