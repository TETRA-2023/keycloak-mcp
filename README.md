# keycloak-mcp

MCP server for Keycloak administration. Fork of
[`idoyudha/mcp-keycloak`](https://github.com/idoyudha/mcp-keycloak) v1.2.2 with
bearer-token middleware, a `/health` route, OAuth2 `client_credentials` grant,
and KC v17+ URL-prefix support.

## Features

- 78 Keycloak admin-API tools (users, clients, realms, roles, groups,
  authentication-management flows).
- Two transports: `stdio` for local clients, `streamable-http` for clients
  reaching the wrapper over HTTP.
- Bearer-token middleware on HTTP transports (`MCP_BEARER_TOKEN`).
- `/health` route for Docker / Compose / external liveness probes.
- Two auth modes: OAuth2 `client_credentials` (preferred) or legacy `password`
  grant against `admin-cli`.

## Quickstart

```bash
git clone https://github.com/tetra-2023/keycloak-mcp
cd keycloak-mcp
cp .env.example .env  # set KEYCLOAK_URL, KEYCLOAK_CLIENT_ID/SECRET, MCP_BEARER_TOKEN
uv sync
uv run python -m src
```

## Docker

```bash
docker run --rm \
  -p 8000:8000 \
  -e KEYCLOAK_URL=https://auth.example.com \
  -e KEYCLOAK_REALM=master \
  -e KEYCLOAK_CLIENT_ID=mcp-svc \
  -e KEYCLOAK_CLIENT_SECRET=... \
  -e MCP_BEARER_TOKEN=... \
  ghcr.io/tetra-2023/keycloak-mcp:stable
```

This image is intended to run behind an authenticating MCP gateway (e.g. a
LiteLLM-style broker, an mTLS proxy, or anything that fronts streamable-HTTP
MCP). It exposes the full Keycloak admin surface — including mutating and
destructive operations — by design. Do not expose port 8000 to untrusted
networks; always front it with bearer auth or equivalent. Authorisation for
individual admin operations is enforced by Keycloak via the service account's
role grants (e.g. `view-realm`, `query-users`); the wrapper does not gate by
tool name.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `KEYCLOAK_URL` | `http://localhost:8080` | Keycloak base URL (no trailing slash). |
| `KEYCLOAK_BASE_PATH` | `` (empty) | Set to `/auth` for legacy `--http-relative-path=/auth` deployments. |
| `KEYCLOAK_REALM` | `master` | Realm in which the SA client lives. |
| `KEYCLOAK_CLIENT_ID` | — | Service-account client_id (preferred). |
| `KEYCLOAK_CLIENT_SECRET` | — | Service-account client secret. |
| `KEYCLOAK_USERNAME` | — | Legacy: admin username (uses `admin-cli`). |
| `KEYCLOAK_PASSWORD` | — | Legacy: admin password. |
| `TRANSPORT` | `stdio` | `stdio`, `streamable-http`, or `sse`. The Docker image overrides to `streamable-http`. |
| `MCP_HOST` | `127.0.0.1` | Bind address. The Docker image overrides to `0.0.0.0`. |
| `MCP_PORT` | `8000` | Bind port. |
| `MCP_BEARER_TOKEN` | — | Bearer token enforced on HTTP transports. Recommended for write-capable deployments. |
| `LOG_LEVEL` | `INFO` | Standard Python log level. |

## License

MIT — see [LICENSE](LICENSE) and [NOTICE](NOTICE) for upstream attribution.
