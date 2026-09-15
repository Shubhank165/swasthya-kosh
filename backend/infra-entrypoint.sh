#!/usr/bin/env bash
# Container entrypoint. One image, several roles, selected by argument.
#
#   serve     the API (and, where PUBSUB_PUSH_ENABLED is set, the OCR worker)
#   migrate   alembic upgrade head
#   seed      the demo facility and the terminology tables
#
# `serve` does not migrate. It used to, and that was wrong: with min-instances 0
# and Cloud Run's concurrency, a burst of cold starts runs `alembic upgrade
# head` several times at once against one database, and the first migration to
# take the lock decides what the others see. Worse, it means a rollback of the
# application is not a rollback â€” the schema has already moved. Migrations are a
# pre-deploy step with one runner: `make migrate`, or the migrate job in
# compose, or `infra/gcp/40-deploy.sh` before it shifts traffic.
set -euo pipefail

cd /app/backend

case "${1:-serve}" in
  serve)
    # Cloud Run injects $PORT and may change it between revisions; never hardcode.
    exec uvicorn app.main:app \
      --host 0.0.0.0 \
      --port "${PORT:-8000}" \
      --proxy-headers \
      --forwarded-allow-ips '*'
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  seed)
    exec python scripts/seed.py
    ;;
  *)
    exec "$@"
    ;;
esac
