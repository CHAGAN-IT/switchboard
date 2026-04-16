# Switchboard -- multi-target Dockerfile
# Usage:
#   docker build --target gateway -t switchboard-gateway .
#   docker build --target admin-api -t switchboard-admin-api .
#
# Source: https://docs.astral.sh/uv/guides/integration/docker/

# --- shared base layer ---
FROM python:3.12-slim AS base

# Copy uv binary from official distroless image (reproducible, no install script)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Dependency layer -- cached independently from source changes
# bind-mount keeps config files out of the final image layer
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Copy source and install project into the venv
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# --- gateway target ---
FROM base AS gateway

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/.well-known/oauth-protected-resource')"

CMD ["uv", "run", "uvicorn", "switchboard.gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]

# --- admin-api target ---
FROM base AS admin-api

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/servers')"

CMD ["uv", "run", "uvicorn", "switchboard.admin.app:app", "--host", "0.0.0.0", "--port", "8000"]
