"""Logging filters used by the streamable-HTTP runner to mute known-benign
upstream noise.

Pure log hygiene — these neither change behaviour nor mask real errors, only
drop specific records the operator can do nothing useful with.
"""

from __future__ import annotations

import logging

import anyio


class StandaloneSseWriterRaceFilter(logging.Filter):
    """Drop the ``mcp.server.streamable_http`` ERROR record that fires on
    session teardown when ``GET /mcp`` SSE writers race against ``DELETE
    /mcp`` cleanup.

    The upstream MCP SDK logs a full ``ClosedResourceError`` traceback from
    ``standalone_sse_writer`` every time a stateful client opens an SSE stream
    and immediately terminates the session — which, for any gateway-brokered
    setup, is every call. The DELETE itself returns 200, the session ends
    cleanly, the client gets its response; the trace is purely log noise.

    Filter is intentionally narrow: only drops records whose exact message
    matches and whose ``exc_info`` is an ``anyio.ClosedResourceError`` (or
    subclass). Every other ERROR from the same logger passes through unchanged.
    """

    _MESSAGE = "Error in standalone SSE writer"

    def filter(self, record: logging.LogRecord) -> bool:
        if record.getMessage() != self._MESSAGE:
            return True
        if not record.exc_info:
            return True
        exc_type = record.exc_info[0]
        if exc_type is None:
            return True
        try:
            return not issubclass(exc_type, anyio.ClosedResourceError)
        except TypeError:
            return True
