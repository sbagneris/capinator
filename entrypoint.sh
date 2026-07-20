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

# One worker only: the in-process background thread serializes DigiKey calls (the shared
# API key's rate limit). --proxy-headers so the app trusts Caddy's X-Forwarded-* (correct
# scheme for Secure cookies / redirects).
exec uvicorn webapp.main:app \
  --host 0.0.0.0 --port "${PORT:-8000}" \
  --workers 1 --proxy-headers --forwarded-allow-ips="*"
