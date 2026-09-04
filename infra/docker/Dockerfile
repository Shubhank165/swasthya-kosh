# syntax=docker/dockerfile:1
#
# One image, three roles: the API, the OCR worker, and the pre-deploy migration
# job. They differ by environment and by the argument passed to the entrypoint,
# never by content — an image that has been smoke-tested as the API is the same
# bytes that later runs the migration, so "it worked in staging" means
# something.
#
# Two stages. The builder carries a compiler and the Postgres headers because
# some wheels still need them; the runtime carries neither, which is both
# smaller and a smaller thing to attack.

# --- build ------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

# A self-contained virtualenv, copied wholesale into the runtime stage. Nothing
# is installed into the system interpreter, so the runtime image has no build
# metadata and no pip.
RUN uv venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

# Dependencies resolve against pyproject alone, so editing a source file does
# not re-resolve the tree. `gcp` is included: the cloud deployment needs it and
# the local one ignores it, and one image means one dependency set.
WORKDIR /build
COPY backend/pyproject.toml /build/pyproject.toml
RUN mkdir -p /build/app && touch /build/app/__init__.py \
 && uv pip install --no-cache '.[gcp]'

# --- runtime ----------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH=/app/backend

# libpq for asyncpg's fallback paths and `curl` for the compose health check.
# No compiler.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY backend /app/backend
# Clinical content is version-controlled alongside the code and shipped inside
# the image, so a deployed build and the pathways, templates and interaction
# table it runs can never drift apart.
COPY clinical /app/clinical

# Runs unprivileged: this container handles patient data. The uploads directory
# is only used by STORAGE_BACKEND=local — in the cloud the store is GCS and
# nothing writes to the container filesystem.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin medikiosk \
 && mkdir -p /app/backend/uploads \
 && chown -R medikiosk:medikiosk /app/backend/uploads \
 && chmod +x /app/backend/infra-entrypoint.sh
USER medikiosk

# Cloud Run overrides this with $PORT; compose and local runs use the default.
ENV PORT=8000
EXPOSE 8000

ENTRYPOINT ["/app/backend/infra-entrypoint.sh"]
CMD ["serve"]
