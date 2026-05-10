"""Live Keycloak connection tests — gated on `-m integration`."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def keycloak_client():
    from src.tools.keycloak_client import KeycloakClient

    return KeycloakClient()


def test_keycloak_client_attrs(keycloak_client):
    assert hasattr(keycloak_client, "_get_token")
    assert hasattr(keycloak_client, "_make_request")


@pytest.mark.asyncio
async def test_keycloak_authentication(keycloak_client):
    try:
        token = await keycloak_client._get_token()
    except Exception as e:
        pytest.skip(f"Keycloak not reachable: {e}")
    assert isinstance(token, str)
    assert len(token) > 20


@pytest.mark.asyncio
async def test_keycloak_realm_info(keycloak_client):
    try:
        info = await keycloak_client._make_request("GET", "")
    except Exception as e:
        pytest.skip(f"Keycloak not reachable: {e}")
    assert isinstance(info, dict)
