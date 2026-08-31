#!/usr/bin/env bash
# Container entrypoint: migrate, seed, then serve.
#
# `alembic upgrade head` runs on every start and is idempotent, so an on-prem
# box that was powered off through a release comes back up on the right schema
# without anyone having to remember a step.
set -euo pipefail

cd /app/backend

case "${1:-serve}" in
  serve)
    echo "running migrations"
    alembic upgrade head
    echo "seeding facility"
    python scripts/seed.py
    echo "starting api"
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  seed)
    exec python scripts/seed.py
    ;;
  evaluate)
    exec python -m evaluation.run
    ;;
  *)
    exec "$@"
    ;;
esac
