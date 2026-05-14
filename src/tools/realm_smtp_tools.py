"""Fork-only realm mutation tools.

Covers realm-level fields the curated parameter list of
``realm_tools.update_realm_settings`` does not expose: the ``smtpServer``
block, arbitrary keys under ``realm.attributes``, action-token lifespans,
and the WebAuthn-passwordless policy fields.

Kept as a separate module so ``realm_tools.py`` stays cherry-pickable from
upstream. Surface contract: GET-then-PUT the whole realm body, same as the
upstream ``update_realm_settings`` shape — KC's PUT is partial-merge anyway,
but the full-body roundtrip is defensive against KC versions that diverge.

Added 2026-05-14 for the consolidated KC hardening US (Tetra #1114):
- v1.4.0: ``update_realm_smtp_settings`` / ``clear_realm_smtp`` /
  ``update_realm_attribute`` — T20 / T20b (IDP-tier SMTP convention).
- v1.5.0: ``update_realm_action_token_lifespans`` /
  ``update_realm_webauthn_passwordless_policy`` — T11 / T17 (admin token
  lifespan standardisation + passkey-config revert).
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
    are NOT under ``attributes`` — they live at the realm root. See
    ``update_realm_action_token_lifespans`` for those.

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


@mcp.tool()
async def update_realm_action_token_lifespans(
    action_token_generated_by_admin_lifespan: Optional[int] = None,
    action_token_generated_by_user_lifespan: Optional[int] = None,
    realm: Optional[str] = None,
) -> Dict[str, str]:
    """
    Update realm-level action-token lifespans (seconds).

    These are top-level integer fields on the realm body, not under
    ``attributes``. Only the parameters explicitly provided are written;
    omitted parameters leave the existing value untouched.

    - ``actionTokenGeneratedByAdminLifespan``: how long admin-issued action
      tokens (reset password, verify email, etc.) remain valid. KC default
      43200 (12 h). TETRA convention is 43200 across the fleet; some realms
      had drifted to 604800 (7 d).
    - ``actionTokenGeneratedByUserLifespan``: same shape for user-initiated
      tokens. KC default 300 (5 min).

    Args:
        action_token_generated_by_admin_lifespan: seconds, or None to skip.
        action_token_generated_by_user_lifespan: seconds, or None to skip.
        realm: Target realm (uses default if not specified)

    Returns:
        Status message with the fields written.
    """
    current_realm = await client._make_request("GET", "", realm=realm)
    written = []
    if action_token_generated_by_admin_lifespan is not None:
        current_realm["actionTokenGeneratedByAdminLifespan"] = (
            action_token_generated_by_admin_lifespan
        )
        written.append(
            f"actionTokenGeneratedByAdminLifespan={action_token_generated_by_admin_lifespan}"
        )
    if action_token_generated_by_user_lifespan is not None:
        current_realm["actionTokenGeneratedByUserLifespan"] = (
            action_token_generated_by_user_lifespan
        )
        written.append(
            f"actionTokenGeneratedByUserLifespan={action_token_generated_by_user_lifespan}"
        )
    if not written:
        return {
            "status": "noop",
            "message": "No fields provided; nothing written.",
        }
    await client._make_request("PUT", "", data=current_realm, realm=realm)
    return {
        "status": "updated",
        "message": (
            f"Realm {realm if realm else client.realm_name} updated: " + ", ".join(written)
        ),
    }


@mcp.tool()
async def update_realm_webauthn_passwordless_policy(
    require_resident_key: Optional[str] = None,
    user_verification_requirement: Optional[str] = None,
    realm: Optional[str] = None,
) -> Dict[str, str]:
    """
    Update the realm's WebAuthn-passwordless policy fields.

    Top-level realm fields, not under ``attributes``. KC's UI exposes more
    knobs than these two; this tool covers the audit-flagged pair plus the
    minimum needed to revert a half-configured policy back to the unset
    state.

    Accepted values match the KC admin REST API enum strings:
    - ``require_resident_key`` ∈ {"not specified", "Yes", "No"}
    - ``user_verification_requirement`` ∈ {"not specified", "required",
      "preferred", "discouraged"}

    To revert a half-configured realm to baseline, pass:
        require_resident_key="not specified",
        user_verification_requirement="not specified"

    Args:
        require_resident_key: webAuthnPolicyPasswordlessRequireResidentKey
        user_verification_requirement:
            webAuthnPolicyPasswordlessUserVerificationRequirement
        realm: Target realm (uses default if not specified)

    Returns:
        Status message with the fields written.
    """
    current_realm = await client._make_request("GET", "", realm=realm)
    written = []
    if require_resident_key is not None:
        current_realm["webAuthnPolicyPasswordlessRequireResidentKey"] = require_resident_key
        written.append(f"webAuthnPolicyPasswordlessRequireResidentKey={require_resident_key!r}")
    if user_verification_requirement is not None:
        current_realm["webAuthnPolicyPasswordlessUserVerificationRequirement"] = (
            user_verification_requirement
        )
        written.append(
            "webAuthnPolicyPasswordlessUserVerificationRequirement="
            f"{user_verification_requirement!r}"
        )
    if not written:
        return {
            "status": "noop",
            "message": "No fields provided; nothing written.",
        }
    await client._make_request("PUT", "", data=current_realm, realm=realm)
    return {
        "status": "updated",
        "message": (
            f"Realm {realm if realm else client.realm_name} updated: " + ", ".join(written)
        ),
    }
