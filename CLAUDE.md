# CLAUDE.md — keycloak-mcp

## Project Overview

MCP server for Keycloak administration. Fork of `idoyudha/mcp-keycloak` v1.2.2
with bearer-token middleware, `/health`, OAuth2 `client_credentials` grant,
and KC v17+ URL-prefix support. Exposes 81 admin-API tools as MCP `@tool()`
definitions, suitable for any client that brokers MCP over streamable-HTTP.

- **Package**: `keycloak-mcp`
- **Python**: >= 3.12
- **Registry**: `ghcr.io/tetra-2023/keycloak-mcp`
- **Upstream**: https://github.com/idoyudha/mcp-keycloak (MIT)

## Architecture

```
src/
  __main__.py                — `python -m src` entry
  main.py                    — transport resolution, HTTP runner with bearer/health/log filter
  common/
    server.py                — FastMCP container + /health route
    config.py                — pydantic-settings (KEYCLOAK_*, MCP_*, MCP_BEARER_TOKEN)
    const.py                 — DEFAULT_REALM, DEFAULT_REQUEST_TIMEOUT
    logging_filters.py       — StandaloneSseWriterRaceFilter (mutes SSE teardown noise)
  middleware/
    auth.py                  — BearerAuthMiddleware (pure ASGI, streaming-safe)
  tools/
    keycloak_client.py       — async httpx client (client_credentials | password grants)
    user_tools.py            — 9 tools
    client_tools.py          — 9 tools
    realm_tools.py           — 9 tools (upstream, cherry-pick lane)
    realm_smtp_tools.py      — 3 tools (fork-only: SMTP + attributes)
    role_tools.py            — 11 tools
    group_tools.py           — 9 tools
    authentication_management_tools.py  — 31 tools (registered via __init__.py)
```

## Auth modes

- **`client_credentials`** (preferred): set `KEYCLOAK_CLIENT_ID` +
  `KEYCLOAK_CLIENT_SECRET`. Service-account client must have role grants for
  the admin operations the LLM is permitted to call. A read-only baseline is
  `view-realm`, `view-users`, `view-clients`, `query-users`, `query-clients`,
  `query-groups`; promote to `manage-*` only when explicitly required.
- **`password`** (legacy): set `KEYCLOAK_USERNAME` + `KEYCLOAK_PASSWORD`. Uses
  the built-in `admin-cli` client.

If both are set, `client_credentials` wins.

## Keycloak URL prefix

KC v17+ removed `/auth/` from default paths. Leave `KEYCLOAK_BASE_PATH` empty
unless the deployment was configured with `--http-relative-path=/auth`.

## Development setup

```bash
uv sync --all-extras --dev
cp .env.example .env  # Configure KEYCLOAK_URL, KEYCLOAK_CLIENT_ID/SECRET, MCP_BEARER_TOKEN
```

## Running

```bash
uv run python -m src                    # streamable-http (default per Dockerfile env)
TRANSPORT=stdio uv run python -m src    # stdio
uv run python -m src --stdio            # stdio (CLI override)
```

Environment variables: see `.env.example`.

## Testing

```bash
uv run pytest tests/ -v
uv run pytest tests/ -m integration  # requires live Keycloak
```

## Code Conventions

- **Linter/formatter**: ruff (`line-length=100`, `target=py312`, rules: E, F, W, I)
- **Commits**: Conventional Commits — `python-semantic-release` derives the version
- **Secrets**: `pydantic.SecretStr`. Never log token/password/client_secret values
- **Tool pattern**: `@mcp.tool()` → `client._make_request(method, endpoint)` → return JSON

## Fork hygiene

The fork tracks upstream selectively. Keep the fork-divergent surface minimal
so upstream fixes can be cherry-picked cleanly:

- Fork-only files: `src/middleware/auth.py`, `src/common/logging_filters.py`,
  `src/tools/realm_smtp_tools.py`, `NOTICE`, `CHANGELOG.md`, this file,
  `.github/workflows/{ci,release}.yml`.
- Modified upstream files: `src/main.py`, `src/common/{server,config}.py`,
  `src/tools/{__init__,keycloak_client}.py`, `Dockerfile`, `pyproject.toml`,
  `.env.example`.
- Untouched upstream files (cherry-pick freely):
  `src/tools/{user,client,realm,role,group,authentication_management}_tools.py`,
  `src/common/const.py`.
