# Security Policy

## Supported versions

Only the `:stable` tag receives security updates. `:latest` tracks `main` and
may include unreleased changes.

## Reporting a vulnerability

Open a private security advisory via GitHub on this repository. For upstream
Keycloak admin-API or wrapper bugs that affect every consumer of the upstream
project, prefer the upstream issue tracker.

## Scope

This wrapper exposes the Keycloak Admin REST API as MCP tools. It enforces:

- **Bearer-token middleware** on HTTP transports (`MCP_BEARER_TOKEN`
  recommended in any production deployment). 401 is returned with a uniform
  body regardless of which check failed — clients cannot distinguish
  "missing header" from "wrong token".
- **No credential logging** — `pydantic.SecretStr` is used for
  `KEYCLOAK_CLIENT_SECRET`, `KEYCLOAK_PASSWORD`, and `MCP_BEARER_TOKEN`.

## Out of scope

- Keycloak's own RBAC. Authorisation for individual admin tools is enforced
  upstream by the service account's role grants (e.g. `view-realm`,
  `query-users`). The wrapper does not gate by tool name — a client that can
  reach the wrapper can attempt every tool, and authorisation is decided by
  Keycloak when the call is made.
