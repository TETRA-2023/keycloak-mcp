"""Keycloak Admin REST client.

Diverges from upstream:
- Adds OAuth2 ``client_credentials`` grant (preferred for service accounts).
- Makes the URL prefix configurable: KC v17+ dropped the ``/auth/`` segment by
  default; legacy deployments configured with ``--http-relative-path=/auth``
  set ``KEYCLOAK_BASE_PATH=/auth``.
- Lazy-init ``httpx.AsyncClient`` per tool call sequence (matches upstream).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from ..common.config import KEYCLOAK_CFG
from ..common.const import DEFAULT_REALM, DEFAULT_REQUEST_TIMEOUT


class KeycloakClient:
    def __init__(self) -> None:
        self.server_url: str = KEYCLOAK_CFG["server_url"].rstrip("/")
        # Empty for KC v17+ default; "/auth" for legacy ``--http-relative-path=/auth``.
        self.base_path: str = (KEYCLOAK_CFG.get("base_path") or "").rstrip("/")
        self.username: Optional[str] = KEYCLOAK_CFG.get("username")
        self.password: Optional[str] = KEYCLOAK_CFG.get("password")
        self.realm_name: str = KEYCLOAK_CFG.get("realm_name") or DEFAULT_REALM
        self.client_id: Optional[str] = KEYCLOAK_CFG.get("client_id")
        self.client_secret: Optional[str] = KEYCLOAK_CFG.get("client_secret")
        self.token: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=DEFAULT_REQUEST_TIMEOUT)
        return self._client

    def _token_url(self) -> str:
        return (
            f"{self.server_url}{self.base_path}"
            f"/realms/{self.realm_name}/protocol/openid-connect/token"
        )

    def _admin_url(self, endpoint: str, *, skip_realm: bool, realm: Optional[str]) -> str:
        if skip_realm:
            return f"{self.server_url}{self.base_path}/admin{endpoint}"
        target_realm = realm if realm is not None else self.realm_name
        return f"{self.server_url}{self.base_path}/admin/realms/{target_realm}{endpoint}"

    async def _get_token(self) -> str:
        """Fetch an access token. Uses client_credentials when a client secret
        is configured, otherwise falls back to the legacy password grant
        against the built-in ``admin-cli`` client.
        """
        if self.client_secret and self.client_id:
            data = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        elif self.password and self.username:
            data = {
                "grant_type": "password",
                "username": self.username,
                "password": self.password,
                "client_id": "admin-cli",
            }
        else:
            raise RuntimeError(
                "No Keycloak credentials configured: set either "
                "KEYCLOAK_CLIENT_ID+KEYCLOAK_CLIENT_SECRET (preferred) or "
                "KEYCLOAK_USERNAME+KEYCLOAK_PASSWORD."
            )

        client = await self._ensure_client()
        response = await client.post(self._token_url(), data=data)
        response.raise_for_status()
        self.token = response.json()["access_token"]
        return self.token

    async def _get_headers(self) -> Dict[str, str]:
        if not self.token:
            await self._get_token()
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        skip_realm: bool = False,
        realm: Optional[str] = None,
    ) -> Any:
        url = self._admin_url(endpoint, skip_realm=skip_realm, realm=realm)
        try:
            client = await self._ensure_client()
            headers = await self._get_headers()

            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params,
            )

            # Token expired — refresh once and retry.
            if response.status_code == 401:
                await self._get_token()
                headers = await self._get_headers()
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data,
                    params=params,
                )

            response.raise_for_status()
            if response.content:
                return response.json()
            return None

        except httpx.RequestError as e:
            raise Exception(f"Keycloak API request failed: {str(e)}") from e

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
