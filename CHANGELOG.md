# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] — Initial fork

First release of the TETRA fork over upstream `idoyudha/mcp-keycloak` v1.2.2.

### Added

- Bearer-token middleware on HTTP transports (`src/middleware/auth.py`).
- `/health` liveness route on the streamable-HTTP transport, bypassing the
  bearer middleware.
- OAuth2 `client_credentials` grant alongside the upstream `password` grant —
  selected automatically when `KEYCLOAK_CLIENT_SECRET` is set.
- Configurable URL prefix via `KEYCLOAK_BASE_PATH`. Defaults to empty for
  KC v17+ deployments; set to `/auth` for legacy.
- `pydantic-settings`-based configuration with `SecretStr` handling.
- `StandaloneSseWriterRaceFilter` logging filter — mutes the benign
  `ClosedResourceError` traceback on streamable-HTTP session teardown.
- `authentication_management_tools` (31 tools) registered via
  `tools/__init__.py` — upstream defines but never imports them, so the
  effective surface goes from 47 to 78 tools.

### Changed

- Dockerfile: Python 3.12 (was 3.13), non-root user, layer-cached
  `uv sync --frozen`, `HEALTHCHECK`, `EXPOSE 8000`.
- Default transport flipped to `streamable-http` (upstream defaulted to
  `stdio`); default bind address `0.0.0.0` (was `127.0.0.1`) so the published
  port is reachable from outside the container.
- Tool surface registration consolidated so `python -m src` loads all 78 tools.

### Removed

- CORS and Origin-validation middleware — the upstream defaults rejected
  anything that wasn't `localhost:8000`, breaking containerised deployment.
  Bearer enforcement at the wrapper edge supersedes origin checking when the
  wrapper is fronted by an authenticating gateway.
- PyPI publishing workflow — distribution is via GHCR images only.
