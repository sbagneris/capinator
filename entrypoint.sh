#!/bin/sh
# Apply DB migrations, then run the web app. Postgres may take a moment to accept
# connections even after Compose reports it healthy, so retry the migration briefly.
set -e

n=0
until alembic upgrade head; do
  n=$((n + 1))
  if [ "$n" -ge 10 ]; then
    echo "alembic upgrade head failed after $n attempts; giving up." >&2
    exit 1
  fi
  echo "database not ready (attempt $n/10) — retrying in 2s…" >&2
  sleep 2
done

# The DigiKey worker runs as its own service (python -m webapp.worker), so the web tier can
# scale: WEB_CONCURRENCY sets the uvicorn worker count (default 1). --proxy-headers so the
# app trusts Caddy's X-Forwarded-* (correct scheme for Secure cookies / redirects).
exec uvicorn webapp.main:app \
  --host 0.0.0.0 --port "${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-1}" --proxy-headers --forwarded-allow-ips="*"
