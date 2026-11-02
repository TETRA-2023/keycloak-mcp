"""Unit tests for update_flow_executions and Keycloak error-body surfacing.

No live Keycloak: requests go through httpx.MockTransport.
"""

from __future__ import annotations

import json

import httpx
import pytest

from src.tools import authentication_management_tools as amt


def _install(handler) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    amt.client.token = "test-token"
    amt.client._client = httpx.AsyncClient(transport=httpx.MockTransport(recording))
    return seen


EXECUTIONS = [
    {"id": "e1", "requirement": "ALTERNATIVE", "providerId": "idp-auto-link"},
    {"id": "e2", "requirement": "DISABLED", "providerId": "idp-review-profile"},
]


@pytest.mark.asyncio
async def test_one_put_per_execution_with_object_body():
    seen = _install(lambda req: httpx.Response(204))

    result = await amt.update_flow_executions(
        flow_alias="first broker login - auto-link",
        executions=EXECUTIONS,
        realm="stirling-pdf",
    )

    assert len(seen) == 2
    for request, expected in zip(seen, EXECUTIONS):
        assert request.method == "PUT"
        assert request.url.path == (
            "/admin/realms/stirling-pdf/authentication/flows/"
            "first broker login - auto-link/executions"
        )
        body = json.loads(request.content)
        assert isinstance(body, dict), "Keycloak expects ONE execution object, not a list"
        assert body == expected
    assert result["updated"] == ["e1", "e2"]


@pytest.mark.asyncio
async def test_keycloak_error_body_is_surfaced_and_partial_progress_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["id"] == "e2":
            return httpx.Response(400, json={"errorMessage": "Requirement not allowed"})
        return httpx.Response(204)

    _install(handler)

    with pytest.raises(Exception) as exc_info:
        await amt.update_flow_executions(flow_alias="f", executions=EXECUTIONS, realm="r")

    message = str(exc_info.value)
    assert "e2" in message
    assert "Requirement not allowed" in message
    assert "e1" in message  # already applied before the failure
    assert isinstance(exc_info.value.__cause__, httpx.HTTPStatusError)
