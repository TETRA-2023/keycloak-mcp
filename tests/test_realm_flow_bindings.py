"""Unit tests for update_realm_flow_bindings.

No live Keycloak: requests go through httpx.MockTransport.
"""

from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio

from src.tools import realm_smtp_tools as rst

FLOWS = [
    {"id": "f1", "alias": "browser", "providerId": "basic-flow", "topLevel": True},
    {"id": "f2", "alias": "browser-mfa", "providerId": "basic-flow", "topLevel": True},
    {"id": "f3", "alias": "direct grant", "providerId": "basic-flow", "topLevel": True},
    {"id": "f4", "alias": "clients", "providerId": "client-flow", "topLevel": True},
]

REALM = {
    "realm": "r",
    "enabled": True,
    "browserFlow": "browser",
    "directGrantFlow": "direct grant",
    "registrationFlow": "registration",
}


@pytest_asyncio.fixture
async def seen():
    """Point the module client at a mock transport; restore it afterwards."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path.endswith("/authentication/flows"):
            return httpx.Response(200, json=FLOWS)
        if request.method == "GET":
            return httpx.Response(200, json=dict(REALM))
        return httpx.Response(204)

    saved = (rst.client.token, rst.client._client)
    mock = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    rst.client.token, rst.client._client = "test-token", mock
    try:
        yield requests
    finally:
        rst.client.token, rst.client._client = saved
        await mock.aclose()


@pytest.mark.asyncio
async def test_binds_browser_flow_and_keeps_other_fields(seen):
    result = await rst.update_realm_flow_bindings(browser_flow="browser-mfa", realm="r")

    (put,) = [r for r in seen if r.method == "PUT"]
    assert put.url.path == "/admin/realms/r"
    body = json.loads(put.content)
    assert body["browserFlow"] == "browser-mfa"
    assert body["directGrantFlow"] == "direct grant"
    assert body["registrationFlow"] == "registration"
    assert body["enabled"] is True
    assert result["bindings"] == {"browserFlow": {"previous": "browser", "new": "browser-mfa"}}


@pytest.mark.asyncio
async def test_unknown_alias_writes_nothing(seen):
    with pytest.raises(ValueError, match="browser-typo"):
        await rst.update_realm_flow_bindings(browser_flow="browser-typo", realm="r")

    assert [r for r in seen if r.method == "PUT"] == []


@pytest.mark.asyncio
async def test_no_binding_is_a_noop(seen):
    result = await rst.update_realm_flow_bindings(realm="r")

    assert result["status"] == "noop"
    assert seen == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [{"browser_flow": "clients"}, {"client_authentication_flow": "browser"}],
)
async def test_wrong_flow_type_writes_nothing(seen, kwargs):
    with pytest.raises(ValueError, match="wrong type"):
        await rst.update_realm_flow_bindings(realm="r", **kwargs)

    assert [r for r in seen if r.method == "PUT"] == []


@pytest.mark.asyncio
async def test_binds_several_flows_in_one_write(seen):
    result = await rst.update_realm_flow_bindings(
        browser_flow="browser-mfa", client_authentication_flow="clients", realm="r"
    )

    (put,) = [r for r in seen if r.method == "PUT"]
    body = json.loads(put.content)
    assert body["browserFlow"] == "browser-mfa"
    assert body["clientAuthenticationFlow"] == "clients"
    assert set(result["bindings"]) == {"browserFlow", "clientAuthenticationFlow"}
