"""Keycloak MCP Server entry point.

Supports stdio and streamable-HTTP transports. HTTP mode wraps the FastMCP
streamable_http_app with bearer-token middleware (when MCP_BEARER_TOKEN is
set) and routes ``/health`` past it for unauthenticated liveness probes.

Diverges from upstream:
- Default transport is ``streamable-http`` (not ``stdio``) for the wrapper image.
- Bind defaults to ``0.0.0.0`` so the published port is reachable from outside
  the container.
- CORS/Origin-validation middleware dropped — superseded by bearer enforcement
  when the wrapper is fronted by an authenticating gateway.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Ensure ``src.*`` imports resolve when invoked as ``python -m src``.
_PKG_ROOT = Path(__file__).parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from src.common.config import settings  # noqa: E402
from src.common.server import mcp  # noqa: E402

# Import all tool modules to register their @mcp.tool() definitions.
from src.tools import (  # noqa: E402, F401
    authentication_management_tools,
    client_tools,
    group_tools,
    realm_tools,
    role_tools,
    user_tools,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger(__name__)


VALID_TRANSPORTS = ("stdio", "streamable-http", "sse")


def _resolve_transport() -> str:
    """Resolve transport from CLI args or env. CLI wins over env."""
    if "--stdio" in sys.argv:
        return "stdio"
    if "--streamable-http" in sys.argv or "--http" in sys.argv:
        return "streamable-http"
    if "--sse" in sys.argv:
        return "sse"

    raw = (settings.transport or "stdio").lower().replace("_", "-")
    # Accept ``http`` as an alias for ``streamable-http`` (upstream env name).
    if raw == "http":
        return "streamable-http"
    if raw in VALID_TRANSPORTS:
        return raw
    logger.warning("Unknown TRANSPORT=%r, falling back to stdio", raw)
    return "stdio"


def _run_http(transport: str) -> None:
    """Run streamable-HTTP (or SSE) transport: bearer middleware (when
    configured), ``/health`` bypass, log filter.
    """
    import uvicorn

    from src.common.logging_filters import StandaloneSseWriterRaceFilter
    from src.middleware.auth import BearerAuthMiddleware

    # Mute the upstream SDK's ClosedResourceError noise on session teardown.
    sdk_logger = logging.getLogger("mcp.server.streamable_http")
    if not any(isinstance(f, StandaloneSseWriterRaceFilter) for f in sdk_logger.filters):
        sdk_logger.addFilter(StandaloneSseWriterRaceFilter())

    app = mcp.streamable_http_app() if transport == "streamable-http" else mcp.sse_app()

    if settings.has_bearer_token:
        app = BearerAuthMiddleware(
            app,
            expected_token=settings.get_bearer_token_value(),
            skip_paths=("/health",),
        )
        logger.info("Bearer-token middleware enabled for %s transport", transport)
    else:
        logger.warning(
            "MCP_BEARER_TOKEN not set — %s transport accepts unauthenticated requests",
            transport,
        )

    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
    logger.info("Listening on http://%s:%d/mcp/", settings.host, settings.port)
    uvicorn.Server(config).run()


def main() -> None:
    transport = _resolve_transport()
    logger.info("Starting Keycloak MCP server with %s transport", transport)
    logger.info("Auth mode: %s, realm: %s", settings.auth_mode, settings.realm)

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        _run_http(transport)


if __name__ == "__main__":
    main()
