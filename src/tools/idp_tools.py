"""Identity Provider management tools (fork-only).

Wraps the KC admin REST API at
``/admin/realms/{realm}/identity-provider/instances``. Different URL
namespace from realm-level mutations (``realm_smtp_tools.py``), so kept in
its own module for conceptual clarity.

Added 2026-05-14 for the consolidated KC hardening US (Tetra #1114),
specifically T01 (defaultScope groups sweep across 17 IDPs / 12 realms,
closes Tetra issue #912), T02 (plain-``oidc`` → ``keycloak-oidc`` flip),
T03 (``tetra/tetra-oidc`` self-loop investigation), T04 (per-class broker
smoke verification).

Surface contract: GET-then-PUT for updates; KC preserves the stored
``config.clientSecret`` when the GET response's ``"**********"``
placeholder is echoed back on PUT.

KC v26 gotcha discovered during T02 smoke (2026-05-14): the IDP
``providerId`` field is immutable. PUT with a new providerId returns
HTTP 200 but silently no-ops on that one field while accepting every
other change in the same PUT body. To change providerId, delete +
recreate via ``delete_identity_provider`` / ``create_identity_provider``
(added in v1.8.0).

Second KC v26 gotcha (2026-05-14): IDP mappers live at a separate URL
namespace (``.../instances/{alias}/mappers``) and are NOT included in
the IDP body returned by ``get_identity_provider``. So a delete+recreate
of an IDP cascades the delete to its mappers but the recreate body
doesn't restore them — the post-recreate IDP has zero mappers, breaking
first-broker-login attribute propagation. Use ``list_idp_mappers`` to
snapshot mappers BEFORE delete, then ``create_idp_mapper`` to replay
them onto the new IDP (v1.9.0).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..common.server import mcp
from .keycloak_client import KeycloakClient

client = KeycloakClient()


@mcp.tool()
async def list_identity_providers(
    realm: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    List all identity provider instances configured on a realm.

    Returns the full per-IDP body for each: ``alias``, ``providerId``,
    ``enabled``, ``trustEmail``, ``syncMode``, ``firstBrokerLoginFlowAlias``,
    nested ``config`` dict (URLs, clientId, redacted clientSecret,
    defaultScope, etc.).

    Use for auditing IDP configurations across realms — defaultScope sweep,
    providerId compliance check, syncMode / trustEmail drift detection.

    Args:
        realm: Target realm (uses default if not specified)

    Returns:
        List of IDP instance dicts.
    """
    return await client._make_request("GET", "/identity-provider/instances", realm=realm)


@mcp.tool()
async def get_identity_provider(
    alias: str,
    realm: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get a single identity provider instance by alias.

    Returns the full IDP body. ``config.clientSecret`` is redacted to
    ``"**********"`` in the response — KC preserves the actual stored secret
    on subsequent PUTs that echo back the placeholder, so the GET-then-PUT
    pattern in ``update_identity_provider`` is safe.

    Args:
        alias: IDP alias (e.g. ``"tetra-oidc"``, ``"icosa-oidc"``).
        realm: Target realm (uses default if not specified)

    Returns:
        IDP instance dict.
    """
    return await client._make_request("GET", f"/identity-provider/instances/{alias}", realm=realm)


@mcp.tool()
async def update_identity_provider(
    alias: str,
    default_scope: Optional[str] = None,
    provider_id: Optional[str] = None,
    sync_mode: Optional[str] = None,
    trust_email: Optional[bool] = None,
    enabled: Optional[bool] = None,
    hide_on_login: Optional[bool] = None,
    realm: Optional[str] = None,
) -> Dict[str, str]:
    """
    Update key fields on an identity provider instance.

    GET-then-PUT pattern: fetches current IDP body, mutates only the
    parameters provided, PUTs the full body back. KC preserves the stored
    ``config.clientSecret`` when the redacted ``"**********"`` placeholder
    is echoed back, so no special handling is needed for the secret.

    Fields exposed:
    - ``default_scope``: stored under ``config.defaultScope``. TETRA
      convention is ``"openid profile email groups"`` for ``tetra-oidc`` /
      ``icosa-oidc`` broker IDPs — the ``groups`` scope is required for
      group-membership claims to propagate to the downstream app realm.
    - ``provider_id``: ``"oidc"`` (generic) or ``"keycloak-oidc"`` (KC-aware,
      preferred for KC-to-KC brokering — adds back-channel logout +
      ``sendIdTokenOnLogout`` support). Not all KC versions allow in-place
      providerId change; if the PUT 4xxs, fall back to delete+recreate via
      the KC admin UI.
    - ``sync_mode``: ``"FORCE"`` / ``"LEGACY"`` / ``"IMPORT"``. TETRA
      convention is ``"FORCE"`` so downstream attributes are re-synced from
      the broker on every login.
    - ``trust_email``: ``true`` for KC-to-KC brokers where the upstream
      realm is the canonical email source.
    - ``enabled``: disable an IDP without deleting (test/debug).
    - ``hide_on_login``: hide the IDP button on the realm's login page —
      useful for ICOSA SSO on non-ICOSA-eligible apps where the button
      exists for the broker plumbing but shouldn't be shown to users.

    Args:
        alias: IDP alias to update.
        default_scope / provider_id / sync_mode / trust_email / enabled /
            hide_on_login: see above. ``None`` (omitted) leaves the existing
            value untouched.
        realm: Target realm (uses default if not specified)

    Returns:
        Status message listing the fields written.
    """
    current = await client._make_request(
        "GET", f"/identity-provider/instances/{alias}", realm=realm
    )
    written = []
    if default_scope is not None:
        config = current.get("config") or {}
        config["defaultScope"] = default_scope
        current["config"] = config
        written.append(f"config.defaultScope={default_scope!r}")
    if provider_id is not None:
        current["providerId"] = provider_id
        written.append(f"providerId={provider_id!r}")
    if sync_mode is not None:
        current["syncMode"] = sync_mode
        written.append(f"syncMode={sync_mode!r}")
    if trust_email is not None:
        current["trustEmail"] = trust_email
        written.append(f"trustEmail={trust_email}")
    if enabled is not None:
        current["enabled"] = enabled
        written.append(f"enabled={enabled}")
    if hide_on_login is not None:
        current["hideOnLogin"] = hide_on_login
        written.append(f"hideOnLogin={hide_on_login}")
    if not written:
        return {
            "status": "noop",
            "message": "No fields provided; nothing written.",
        }
    await client._make_request(
        "PUT",
        f"/identity-provider/instances/{alias}",
        data=current,
        realm=realm,
    )
    return {
        "status": "updated",
        "message": (
            f"IDP {alias!r} on realm {realm if realm else client.realm_name} "
            f"updated: " + ", ".join(written)
        ),
    }


@mcp.tool()
async def create_identity_provider(
    body: Dict[str, Any],
    realm: Optional[str] = None,
) -> Dict[str, str]:
    """
    Create a new identity provider instance.

    POST /admin/realms/{realm}/identity-provider/instances

    Pass a full IDP body — at minimum ``alias``, ``providerId``, and a
    ``config`` dict containing the upstream OIDC URLs + clientId +
    clientSecret. Read-only fields are stripped automatically:
    ``internalId`` (KC assigns a fresh UUID), ``types`` (KC metadata).

    **Canonical replay-after-delete recipe** for flipping a KC v26 IDP's
    immutable ``providerId`` (e.g. ``oidc`` → ``keycloak-oidc``):

    1. ``original = await get_identity_provider(realm, alias)``
    2. ``upstream_clients = await list_clients(upstream_realm,
       client_id=original["config"]["clientId"])``
    3. ``secret_resp = await get_client_secret(upstream_realm,
       upstream_clients[0]["id"])``
    4. Build the new body::

           new_body = {**original, "providerId": "keycloak-oidc"}
           new_body["config"] = {
               **original["config"],
               "clientSecret": secret_resp["value"],
           }

    5. ``await delete_identity_provider(realm, alias)``
    6. ``await create_identity_provider(new_body, realm=realm)``

    The actual ``clientSecret`` MUST be substituted in step 4 — the GET
    response's ``"**********"`` placeholder works for PUT (KC preserves
    on update) but NOT for POST (KC stores the literal placeholder string,
    breaking the broker handshake).

    Args:
        body: Full IDP body. Required.
        realm: Target realm (uses default if not specified)

    Returns:
        Status message with the created alias.
    """
    body = {k: v for k, v in body.items() if k not in ("internalId", "types")}
    await client._make_request("POST", "/identity-provider/instances", data=body, realm=realm)
    alias = body.get("alias", "<unknown>")
    return {
        "status": "created",
        "message": (f"IDP {alias!r} created on realm {realm if realm else client.realm_name}"),
    }


@mcp.tool()
async def delete_identity_provider(
    alias: str,
    realm: Optional[str] = None,
) -> Dict[str, str]:
    """
    Delete an identity provider instance. DESTRUCTIVE.

    DELETE /admin/realms/{realm}/identity-provider/instances/{alias}

    Cascades to the IDP's mappers (KC handles this server-side) but does
    NOT touch the upstream broker client (which lives in a different
    realm). Existing users with ``federated_identity`` records pointing
    at this IDP get orphaned — recoverable by re-linking via
    first-broker-login on a subsequent SSO attempt.

    Always snapshot via ``get_identity_provider`` before calling. KC
    postgres Duplicati backup is the full-restore path if needed.

    Args:
        alias: IDP alias to delete.
        realm: Target realm (uses default if not specified)

    Returns:
        Status message.
    """
    await client._make_request("DELETE", f"/identity-provider/instances/{alias}", realm=realm)
    return {
        "status": "deleted",
        "message": (f"IDP {alias!r} deleted from realm {realm if realm else client.realm_name}"),
    }


@mcp.tool()
async def list_idp_mappers(
    alias: str,
    realm: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    List all attribute / role / group mappers attached to an identity
    provider instance.

    GET /admin/realms/{realm}/identity-provider/instances/{alias}/mappers

    For KC-to-KC OIDC brokering, the TETRA fleet baseline is 3 attribute
    mappers per IDP (``email``, ``firstName``, ``lastName``) using the
    ``oidc-user-attribute-idp-mapper`` type. Some realms also have
    hardcoded group/role mappers via ``oidc-hardcoded-group-idp-mapper``
    or ``oidc-hardcoded-role-idp-mapper``.

    Use this to snapshot mappers before a delete+recreate IDP cycle
    (the recreate doesn't restore mappers — see module docstring).

    Args:
        alias: IDP alias.
        realm: Target realm (uses default if not specified)

    Returns:
        List of mapper dicts, each with ``id``, ``name``,
        ``identityProviderAlias``, ``identityProviderMapper``, ``config``.
    """
    return await client._make_request(
        "GET", f"/identity-provider/instances/{alias}/mappers", realm=realm
    )


@mcp.tool()
async def create_idp_mapper(
    alias: str,
    body: Dict[str, Any],
    realm: Optional[str] = None,
) -> Dict[str, str]:
    """
    Create a mapper on an identity provider instance.

    POST /admin/realms/{realm}/identity-provider/instances/{alias}/mappers

    Pass a mapper body containing at minimum:

    - ``name``: human label (e.g. ``"email"``)
    - ``identityProviderAlias``: must match the URL alias param
    - ``identityProviderMapper``: KC v26 mapper type — for OIDC IDPs use the
      ``oidc-`` prefixed variants:

      * ``oidc-user-attribute-idp-mapper`` — claim-to-attribute mapping
      * ``oidc-hardcoded-group-idp-mapper`` — assign a fixed group
      * ``oidc-hardcoded-role-idp-mapper`` — assign a fixed role
      * ``oidc-advanced-group-idp-mapper`` — claim-value-conditional group

      ⚠️ KC v26 NPE gotcha: non-prefixed forms (e.g.
      ``user-attribute-idp-mapper``) are accepted by the API and saved
      to the DB but trigger an NPE at runtime in
      ``IdentityBrokerService.preprocessFederatedIdentity``, blocking
      all logins through that IDP. See ``BM:
      reference/keycloak-setup-realms-security-baseline-identity-brokering``.

    - ``config``: dict of mapper-type-specific keys. For attribute
      mappers: ``claim`` (upstream claim name), ``user.attribute``
      (local attribute name), ``syncMode``
      (``"INHERIT"`` / ``"FORCE"`` / ``"LEGACY"``).

    Auto-strips ``id`` from the body (KC assigns).

    Args:
        alias: IDP alias the mapper attaches to.
        body: Mapper body (see above).
        realm: Target realm (uses default if not specified)

    Returns:
        Status message.
    """
    body = {k: v for k, v in body.items() if k != "id"}
    await client._make_request(
        "POST",
        f"/identity-provider/instances/{alias}/mappers",
        data=body,
        realm=realm,
    )
    mapper_name = body.get("name", "<unknown>")
    return {
        "status": "created",
        "message": (
            f"IDP mapper {mapper_name!r} created on {alias!r} in realm "
            f"{realm if realm else client.realm_name}"
        ),
    }


@mcp.tool()
async def delete_idp_mapper(
    alias: str,
    mapper_id: str,
    realm: Optional[str] = None,
) -> Dict[str, str]:
    """
    Delete a mapper from an identity provider instance.

    DELETE /admin/realms/{realm}/identity-provider/instances/{alias}/mappers/{mapper_id}

    Args:
        alias: IDP alias.
        mapper_id: Mapper internal UUID (from ``list_idp_mappers``).
        realm: Target realm (uses default if not specified)

    Returns:
        Status message.
    """
    await client._make_request(
        "DELETE",
        f"/identity-provider/instances/{alias}/mappers/{mapper_id}",
        realm=realm,
    )
    return {
        "status": "deleted",
        "message": (
            f"IDP mapper {mapper_id!r} deleted from {alias!r} in realm "
            f"{realm if realm else client.realm_name}"
        ),
    }
