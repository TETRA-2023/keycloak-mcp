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
