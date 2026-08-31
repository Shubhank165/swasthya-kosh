# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Dependencies first, so a source change does not re-resolve the whole tree.
COPY backend/pyproject.toml /app/backend/pyproject.toml
WORKDIR /app/backend
RUN uv pip install --system --no-cache .

COPY backend /app/backend
# Clinical content is version-controlled alongside the code and shipped with it,
# so a deployed image and the pathways it runs can never drift apart.
COPY clinical /app/clinical

# Re-install now that the source is present. The first install resolved the
# package list against a directory that held only pyproject.toml, so `app` was
# not importable — the container migrated and then failed to seed.
RUN uv pip install --system --no-cache --no-deps -e .

# Runs unprivileged: this container handles patient data.
RUN useradd --create-home --uid 10001 medikiosk \
 && mkdir -p /app/backend/uploads \
 && chown -R medikiosk:medikiosk /app
USER medikiosk

EXPOSE 8000
ENTRYPOINT ["/app/backend/infra-entrypoint.sh"]
CMD ["serve"]
