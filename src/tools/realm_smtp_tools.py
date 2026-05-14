"""Fork-only realm mutation tools.

Covers realm-level fields the curated parameter list of
``realm_tools.update_realm_settings`` does not expose: the ``smtpServer``
block, arbitrary keys under ``realm.attributes``, action-token lifespans,
WebAuthn-passwordless policy fields, internationalisation, and the
brute-force fields upstream omits.

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
- v1.6.0: ``update_realm_i18n`` / ``update_realm_brute_force_extra`` —
  T15 / T18 (i18n convergence on [en, fr] + maxTemporaryLockouts gap).
- v1.7.0: ``update_realm_password_policy`` / ``delete_realm`` —
  T05/T06/T21 (passwordPolicy as a top-level string) + T12/T13 follow-up
  (realm lifecycle completeness for the Ansible enforce role).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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


@mcp.tool()
async def update_realm_i18n(
    enabled: Optional[bool] = None,
    supported_locales: Optional[List[str]] = None,
    default_locale: Optional[str] = None,
    realm: Optional[str] = None,
) -> Dict[str, str]:
    """
    Update realm internationalisation: enabled flag, supported locales list,
    and default locale.

    Top-level realm fields, not under ``attributes``. Note that the upstream
    ``update_realm_settings`` already exposes ``default_locale`` standalone;
    this tool covers the two companion fields it omits. Pass all three here
    when flipping a realm from disabled to enabled in one go.

    TETRA fleet convention: ``enabled=True``,
    ``supported_locales=["en", "fr"]``, ``default_locale="en"``.

    Args:
        enabled: internationalizationEnabled boolean.
        supported_locales: list of locale codes (e.g. ``["en", "fr"]``).
        default_locale: default locale code (e.g. ``"en"``).
        realm: Target realm (uses default if not specified)

    Returns:
        Status message with the fields written.
    """
    current_realm = await client._make_request("GET", "", realm=realm)
    written = []
    if enabled is not None:
        current_realm["internationalizationEnabled"] = enabled
        written.append(f"internationalizationEnabled={enabled}")
    if supported_locales is not None:
        current_realm["supportedLocales"] = supported_locales
        written.append(f"supportedLocales={supported_locales!r}")
    if default_locale is not None:
        current_realm["defaultLocale"] = default_locale
        written.append(f"defaultLocale={default_locale!r}")
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
async def update_realm_brute_force_extra(
    max_temporary_lockouts: Optional[int] = None,
    realm: Optional[str] = None,
) -> Dict[str, str]:
    """
    Update brute-force fields not exposed by ``update_realm_settings``.

    Specifically ``maxTemporaryLockouts`` — the count of temporary lockouts
    a user can accumulate before KC promotes them to permanent lockout (when
    ``permanentLockout=True``). KC default 0 (no permanent escalation); TETRA
    convention is 1 on the realms where we want strict admin-grade lockout
    (master / tetra; SAI inherited the same).

    The companion ``permanent_lockout`` field IS exposed by
    ``update_realm_settings``; pair the two when flipping a realm to the
    "one temporary then permanent" posture.

    Args:
        max_temporary_lockouts: int, or None to skip.
        realm: Target realm (uses default if not specified)

    Returns:
        Status message with the fields written.
    """
    current_realm = await client._make_request("GET", "", realm=realm)
    written = []
    if max_temporary_lockouts is not None:
        current_realm["maxTemporaryLockouts"] = max_temporary_lockouts
        written.append(f"maxTemporaryLockouts={max_temporary_lockouts}")
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
async def update_realm_password_policy(
    password_policy: str,
    realm: Optional[str] = None,
) -> Dict[str, str]:
    """
    Set the realm-level ``passwordPolicy``.

    KC stores password policy as a single string with policies separated by
    `` and `` — e.g. ``length(12) and upperCase(1) and lowerCase(1) and
    digits(1) and specialChars(1) and notUsername and passwordHistory(3)``.

    KC's serialiser normalises ``notUsername`` (which takes no arg) to
    ``notUsername(undefined)`` in the stored form — functionally equivalent.

    TETRA fleet convention:
    ``length(12) and upperCase(1) and lowerCase(1) and digits(1) and
    specialChars(1) and notUsername and passwordHistory(3)``

    Args:
        password_policy: Full replacement policy string.
        realm: Target realm (uses default if not specified)

    Returns:
        Status message.
    """
    current_realm = await client._make_request("GET", "", realm=realm)
    current_realm["passwordPolicy"] = password_policy
    await client._make_request("PUT", "", data=current_realm, realm=realm)
    return {
        "status": "updated",
        "message": (f"Realm {realm if realm else client.realm_name} passwordPolicy updated"),
    }


@mcp.tool()
async def delete_realm(realm: str) -> Dict[str, str]:
    """
    Delete a realm. DESTRUCTIVE — cascades to users, clients, IDPs, mappers,
    groups, roles, and federated identity records.

    The ``realm`` argument is required here (no default-realm fallback) to
    reduce the risk of unintended deletion via the wrapper's default-realm
    shortcut. Always snapshot the realm with the structural GETs
    (``get_realm_info`` / ``list_users`` / ``list_clients`` /
    ``list_identity_providers``) before calling. The KC postgres Duplicati
    backup is the full-restore path if the structural snapshot is
    insufficient (credentials / TOTP seeds not captured by the wrapper).

    Args:
        realm: Realm name to delete. Required.

    Returns:
        Status message.
    """
    await client._make_request("DELETE", "", realm=realm)
    return {
        "status": "deleted",
        "message": f"Realm {realm!r} deleted",
    }
