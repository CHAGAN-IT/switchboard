# Ping MCP reference server
# Source: https://docs.astral.sh/uv/guides/integration/docker/
FROM python:3.12-slim

# Copy uv binary from official distroless image (reproducible, no install script)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Dependency layer -- cached independently from source changes
# bind-mount keeps config files out of the final image layer
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Copy source and install project into the venv
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# Documentation only -- no host port mapping enforced
EXPOSE 8000

CMD ["uv", "run", "python", "server.py"]
