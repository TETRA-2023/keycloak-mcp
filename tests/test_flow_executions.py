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

# What GET .../executions returns for the flow before the update.
CURRENT = [
    {"id": "e1", "requirement": "DISABLED", "providerId": "idp-auto-link", "priority": 10},
    {"id": "e2", "requirement": "REQUIRED", "providerId": "idp-review-profile", "priority": 20},
]


def _with_current(put_handler, current=CURRENT):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=current)
        return put_handler(request)

    return handler


@pytest.mark.asyncio
async def test_one_put_per_execution_with_object_body():
    seen = _install(_with_current(lambda req: httpx.Response(204)))

    result = await amt.update_flow_executions(
        flow_alias="first broker login - auto-link",
        executions=EXECUTIONS,
        realm="stirling-pdf",
    )

    puts = [r for r in seen if r.method == "PUT"]
    assert len(puts) == 2
    for request, expected, current in zip(puts, EXECUTIONS, CURRENT):
        assert request.method == "PUT"
        assert request.url.path == (
            "/admin/realms/stirling-pdf/authentication/flows/"
            "first broker login - auto-link/executions"
        )
        body = json.loads(request.content)
        assert isinstance(body, dict), "Keycloak expects ONE execution object, not a list"
        assert body == {**current, **expected}
    assert result["updated"] == ["e1", "e2"]


@pytest.mark.asyncio
async def test_keycloak_error_body_is_surfaced_and_partial_progress_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["id"] == "e2":
            return httpx.Response(400, json={"errorMessage": "Requirement not allowed"})
        return httpx.Response(204)

    _install(_with_current(handler))

    with pytest.raises(Exception) as exc_info:
        await amt.update_flow_executions(flow_alias="f", executions=EXECUTIONS, realm="r")

    message = str(exc_info.value)
    assert "e2" in message
    assert "Requirement not allowed" in message
    assert "e1" in message  # already applied before the failure
    assert isinstance(exc_info.value.__cause__, httpx.HTTPStatusError)


@pytest.mark.asyncio
async def test_fields_not_given_keep_their_current_value():
    """A PUT with only id + requirement must not reset priority to 0."""
    seen = _install(_with_current(lambda req: httpx.Response(204)))

    await amt.update_flow_executions(
        flow_alias="browser", executions=[{"id": "e2", "requirement": "CONDITIONAL"}], realm="r"
    )

    (put,) = [r for r in seen if r.method == "PUT"]
    body = json.loads(put.content)
    assert body["requirement"] == "CONDITIONAL"
    assert body["priority"] == 20
    assert body["providerId"] == "idp-review-profile"


@pytest.mark.asyncio
async def test_explicit_priority_is_sent():
    seen = _install(_with_current(lambda req: httpx.Response(204)))

    await amt.update_flow_executions(
        flow_alias="browser", executions=[{"id": "e1", "priority": 30}], realm="r"
    )

    (put,) = [r for r in seen if r.method == "PUT"]
    assert json.loads(put.content)["priority"] == 30


@pytest.mark.asyncio
async def test_unknown_id_fails_before_any_put():
    seen = _install(_with_current(lambda req: httpx.Response(204)))

    with pytest.raises(ValueError, match="not-in-flow"):
        await amt.update_flow_executions(
            flow_alias="browser",
            executions=[{"id": "e1", "requirement": "REQUIRED"}, {"id": "not-in-flow"}],
            realm="r",
        )

    assert [r for r in seen if r.method == "PUT"] == []
