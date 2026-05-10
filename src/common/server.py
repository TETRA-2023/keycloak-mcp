"""FastMCP container plus the ``/health`` route registered on its
streamable-HTTP app.

``mcp`` is shared by every tool module via ``from ..common.server import mcp``.
The host/port read here are consulted by FastMCP only when running an HTTP
transport — stdio ignores them.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

from .config import settings

mcp = FastMCP(
    "Keycloak MCP Server",
    host=settings.host,
    port=settings.port,
)


@mcp.custom_route("/health", methods=["GET"])
async def health(_request) -> JSONResponse:
    """Liveness probe — returns 200 once the streamable-HTTP app is bound.

    Bypasses the bearer middleware (registered with ``skip_paths=("/health",)``)
    so Docker / Compose / mesh-side curl can probe without a token.
    """
    return JSONResponse({"status": "ok", "service": "keycloak-mcp"})
