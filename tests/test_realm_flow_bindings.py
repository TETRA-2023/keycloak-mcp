"""Unit tests for update_realm_flow_bindings.

No live Keycloak: requests go through httpx.MockTransport.
"""

from __future__ import annotations

import json

import httpx
import pytest

from src.tools import realm_smtp_tools as rst

FLOWS = [
    {"id": "f1", "alias": "browser", "topLevel": True},
    {"id": "f2", "alias": "browser-mfa", "topLevel": True},
    {"id": "f3", "alias": "direct grant", "topLevel": True},
]

REALM = {
    "realm": "r",
    "enabled": True,
    "browserFlow": "browser",
    "directGrantFlow": "direct grant",
    "registrationFlow": "registration",
}


def _install() -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET" and request.url.path.endswith("/authentication/flows"):
            return httpx.Response(200, json=FLOWS)
        if request.method == "GET":
            return httpx.Response(200, json=dict(REALM))
        return httpx.Response(204)

    rst.client.token = "test-token"
    rst.client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return seen


@pytest.mark.asyncio
async def test_binds_browser_flow_and_keeps_other_fields():
    seen = _install()

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
async def test_unknown_alias_writes_nothing():
    seen = _install()

    with pytest.raises(ValueError, match="browser-typo"):
        await rst.update_realm_flow_bindings(browser_flow="browser-typo", realm="r")

    assert [r for r in seen if r.method == "PUT"] == []


@pytest.mark.asyncio
async def test_no_binding_is_a_noop():
    seen = _install()

    result = await rst.update_realm_flow_bindings(realm="r")

    assert result["status"] == "noop"
    assert seen == []
