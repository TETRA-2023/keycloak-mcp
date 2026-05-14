"""Realm SMTP + attribute mutation tools (fork-only).

Adds the realm-level write surface the curated parameter list of
``realm_tools.update_realm_settings`` does not cover: the SMTP block and
arbitrary keys under ``realm.attributes`` (e.g. ``realmDescription``).

Kept as a separate module so ``realm_tools.py`` stays cherry-pickable from
upstream. Surface contract: get-then-PUT the whole realm body, same as the
upstream ``update_realm_settings`` shape — KC's PUT is partial-merge anyway,
but the full-body roundtrip is defensive against KC versions that diverge.

Added 2026-05-14 for the consolidated KC hardening US (Tetra #1114, tasks T20
and T20b — IDP-tier SMTP convention).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..common.server import mcp
from .keycloak_client import KeycloakClient

client = KeycloakClient()


@mcp.tool()
async def update_realm_smtp_settings(
    smtp_server: Dict[str, Any],
    realm: Optional[str] = None,
) -> Dict[str, str]:
    """
    Replace the realm SMTP block.

    Pass the FULL desired ``smtpServer`` dict — KC stores it as a flat
    string-keyed map (host, port, from, user, password, starttls, auth, ssl,
    replyTo, fromDisplayName, envelopeFrom, ...). To clear SMTP entirely,
    pass an empty dict: ``smtp_server={}``. For the clear case
    ``clear_realm_smtp`` is the more self-documenting entry point.

    Args:
        smtp_server: The full smtpServer dict to PUT, or ``{}`` to clear.
        realm: Target realm (uses default if not specified)

    Returns:
        Status message
    """
    current_realm = await client._make_request("GET", "", realm=realm)
    current_realm["smtpServer"] = smtp_server
    await client._make_request("PUT", "", data=current_realm, realm=realm)
    op = "cleared" if smtp_server == {} else "updated"
    return {
        "status": op,
        "message": (f"Realm {realm if realm else client.realm_name} smtpServer {op}"),
    }


@mcp.tool()
async def clear_realm_smtp(
    realm: Optional[str] = None,
) -> Dict[str, str]:
    """
    Clear the realm SMTP block (sets ``smtpServer={}``).

    TETRA fleet convention: SMTP belongs only on IDP-tier realms
    (``tetra``, ``icosa``, ``master``). App realms that broker via
    ``tetra-oidc`` / ``icosa-oidc`` never send email directly — users
    authenticate at the IDP layer where reset/verify mails fire. Use this
    tool to retire dead SMTP config on broker realms.

    Equivalent to ``update_realm_smtp_settings(smtp_server={}, realm=realm)``.

    Args:
        realm: Target realm (uses default if not specified)

    Returns:
        Status message
    """
    return await update_realm_smtp_settings(smtp_server={}, realm=realm)


@mcp.tool()
async def update_realm_attribute(
    attribute_key: str,
    attribute_value: str,
    realm: Optional[str] = None,
) -> Dict[str, str]:
    """
    Set a single key under ``realm.attributes``.

    Use this for fields not exposed by ``update_realm_settings`` that live
    under the realm-level ``attributes`` map — for example
    ``realmDescription``, ``frontendUrl``, ``cibaBackchannelTokenDeliveryMode``,
    ``actionTokenGeneratedByUserLifespan.verify-email``, ``acr.loa.map``.
    KC stores attribute values as strings, so the signature mirrors that.

    Note: top-level realm fields like ``actionTokenGeneratedByAdminLifespan``
    are NOT under ``attributes`` — they live at the realm root. This tool
    does not cover those (see follow-up US for an ``update_realm_token_lifespans``
    tool if T11 needs an MCP path).

    Args:
        attribute_key: Attribute name (e.g. ``"realmDescription"``)
        attribute_value: New string value
        realm: Target realm (uses default if not specified)

    Returns:
        Status message
    """
    current_realm = await client._make_request("GET", "", realm=realm)
    attrs = current_realm.get("attributes") or {}
    attrs[attribute_key] = attribute_value
    current_realm["attributes"] = attrs
    await client._make_request("PUT", "", data=current_realm, realm=realm)
    return {
        "status": "updated",
        "message": (
            f"Realm {realm if realm else client.realm_name} attribute {attribute_key!r} updated"
        ),
    }
