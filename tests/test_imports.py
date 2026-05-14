"""Smoke import tests — no Keycloak connection required."""

from __future__ import annotations


def test_can_import_main():
    from src.main import main

    assert callable(main)


def test_can_import_tools():
    from src.tools import (
        authentication_management_tools,
        client_tools,
        group_tools,
        realm_smtp_tools,
        realm_tools,
        role_tools,
        user_tools,
    )

    for mod in (
        authentication_management_tools,
        client_tools,
        group_tools,
        realm_smtp_tools,
        realm_tools,
        role_tools,
        user_tools,
    ):
        assert mod is not None


def test_can_import_keycloak_client():
    from src.tools.keycloak_client import KeycloakClient

    assert KeycloakClient is not None


def test_can_import_settings():
    from src.common.config import KEYCLOAK_CFG, settings

    assert settings is not None
    assert KEYCLOAK_CFG is not None
    assert "server_url" in KEYCLOAK_CFG


def test_can_import_server():
    from src.common.server import mcp

    assert mcp is not None


def test_can_import_bearer_middleware():
    from src.middleware.auth import BearerAuthMiddleware

    assert BearerAuthMiddleware is not None


def test_can_import_logging_filter():
    from src.common.logging_filters import StandaloneSseWriterRaceFilter

    assert StandaloneSseWriterRaceFilter is not None
