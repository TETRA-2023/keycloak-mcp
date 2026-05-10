FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Create non-root user
RUN groupadd --system appgroup && useradd --system --gid appgroup appuser

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies only (reproducible from lockfile)
RUN uv sync --frozen --no-install-project

# Copy application source
COPY src/ src/

# Install the project itself (non-editable) so uv run doesn't need to write at runtime
RUN uv sync --frozen --no-editable

ENV UV_CACHE_DIR=/tmp/uv-cache \
    PYTHONUNBUFFERED=1 \
    TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

USER appuser

EXPOSE 8000

# Liveness probe — hits the /health route the app registers on the streamable-http transport.
# No-op for stdio mode (the route only exists when the HTTP transport is bound), but Docker
# will report unhealthy in that case which is the correct semantic.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["/app/.venv/bin/python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

ENTRYPOINT ["/app/.venv/bin/python", "-m", "src"]
