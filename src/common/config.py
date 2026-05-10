"""Configuration management for Keycloak MCP server.

Replaces the upstream module-level dict (``KEYCLOAK_CFG``) with a typed
:class:`pydantic_settings.BaseSettings` instance. The ``KEYCLOAK_CFG`` dict is
re-exported for backwards compatibility with tools that import it directly.

Auth modes
----------
* ``client_credentials`` — preferred. Set ``KEYCLOAK_CLIENT_ID`` +
  ``KEYCLOAK_CLIENT_SECRET``. Requires a service-account-enabled client in the
  configured realm.
* ``password`` — legacy. Set ``KEYCLOAK_USERNAME`` + ``KEYCLOAK_PASSWORD``.
  The token is fetched against the built-in ``admin-cli`` client.

If both are configured, ``client_credentials`` wins.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"

load_dotenv(dotenv_path=ENV_FILE_PATH)


class KeycloakSettings(BaseSettings):
    """Keycloak MCP server settings."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # ── Keycloak server ──
    url: str = Field(
        default="http://localhost:8080",
        alias="KEYCLOAK_URL",
        description="Keycloak base URL (no trailing slash).",
    )
    base_path: str = Field(
        default="",
        alias="KEYCLOAK_BASE_PATH",
        description="URL prefix; empty for KC v17+ default, '/auth' for legacy.",
    )
    realm: str = Field(
        default="master",
        alias="KEYCLOAK_REALM",
        description="Realm in which the SA client lives.",
    )

    # ── Auth: client_credentials (preferred) ──
    client_id: Optional[str] = Field(
        default=None,
        alias="KEYCLOAK_CLIENT_ID",
        description="Service-account client_id.",
    )
    client_secret: Optional[SecretStr] = Field(
        default=None,
        alias="KEYCLOAK_CLIENT_SECRET",
        description="Service-account client secret.",
    )

    # ── Auth: password (legacy) ──
    username: Optional[str] = Field(default=None, alias="KEYCLOAK_USERNAME")
    password: Optional[SecretStr] = Field(default=None, alias="KEYCLOAK_PASSWORD")

    # ── MCP transport / wrapper ──
    transport: str = Field(default="stdio", alias="TRANSPORT")
    host: str = Field(default="127.0.0.1", alias="MCP_HOST")
    port: int = Field(default=8000, alias="MCP_PORT")
    bearer_token: Optional[SecretStr] = Field(
        default=None,
        alias="MCP_BEARER_TOKEN",
        description=(
            "Bearer token enforced on HTTP transports. Recommended for write-capable "
            "wrappers fronted by an authenticating gateway."
        ),
    )

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def auth_mode(self) -> str:
        """Resolve which OAuth2 flow to use at token-fetch time."""
        if self.client_secret is not None and self.client_id:
            return "client_credentials"
        if self.password is not None and self.username:
            return "password"
        return "none"

    @property
    def has_bearer_token(self) -> bool:
        return self.bearer_token is not None

    def get_bearer_token_value(self) -> str:
        if self.bearer_token is None:
            raise ValueError("MCP_BEARER_TOKEN is not set")
        return self.bearer_token.get_secret_value()

    def get_client_secret_value(self) -> Optional[str]:
        if self.client_secret is None:
            return None
        return self.client_secret.get_secret_value()

    def get_password_value(self) -> Optional[str]:
        if self.password is None:
            return None
        return self.password.get_secret_value()


settings = KeycloakSettings()

# Backwards-compat shim for existing tool modules that read KEYCLOAK_CFG.
# Returns plain strings (secrets unwrapped) — these are passed straight to KeycloakClient,
# which holds them in memory only and never logs them.
KEYCLOAK_CFG = {
    "server_url": settings.url,
    "base_path": settings.base_path,
    "username": settings.username,
    "password": settings.get_password_value(),
    "realm_name": settings.realm,
    "client_id": settings.client_id,
    "client_secret": settings.get_client_secret_value(),
}


def mask_credential(value: Optional[str], visible_chars: int = 2) -> str:
    """Mask a credential for safe logging."""
    if not value:
        return "<empty>"
    if len(value) <= visible_chars * 2:
        return "*" * len(value)
    return (
        f"{value[:visible_chars]}{'*' * (len(value) - visible_chars * 2)}{value[-visible_chars:]}"
    )
