"""Tests HTTP du diagnostic de santé."""

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import application


def test_health_is_public_and_reports_missing_token(
    http_request: Callable[..., Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teste que le diagnostic de santé est public et signale l'absence du token serveur."""
    monkeypatch.delenv("ALERTINY_BEARER_TOKEN")
    response = http_request("GET", "/health", token=None)
    assert response.status == 200
    assert response.body["DATABASE"] == "OK"
    assert response.body["ENVIRONMENT"]["status"] == "NOK"
    assert "ALERTINY_BEARER_TOKEN" in response.body["ENVIRONMENT"]["missing_variables"]


def test_health_reports_database_error(
    http_request: Callable[..., Any], isolated_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teste que le diagnostic de santé signale une erreur de base de données."""
    def fail_execute(*_args: object, **_kwargs: object) -> None:
        raise SQLAlchemyError("database failure")

    monkeypatch.setattr(isolated_session, "execute", fail_execute)
    response = http_request("GET", "/health", token=None)
    assert response.status == 200
    assert response.body["DATABASE"] == "NOK"


def test_health_warns_about_weak_bearer_token(
    http_request: Callable[..., Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teste que le diagnostic de santé avertit d'un token Bearer faible."""
    monkeypatch.setenv("ALERTINY_BEARER_TOKEN", "weak")
    response = http_request("GET", "/health", token=None)
    assert response.body["ENVIRONMENT"]["status"] == "OK"
    assert len(response.body["ENVIRONMENT"]["warnings"]) == 1
    assert "weak" not in str(response.body)


def test_application_lifespan_validates_configuration_before_serving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teste que le cycle de vie de l'application valide la configuration avant de servir."""
    calls: list[str] = []
    monkeypatch.setattr(application, "initialize_database", lambda: calls.append("database"))
    monkeypatch.setattr(application, "load_mail_config", lambda: calls.append("config"))
    app = application.get_app()

    async def run_lifespan() -> None:
        async with application.lifespan(app):
            calls.append("serving")

    asyncio.run(run_lifespan())
    assert calls == ["database", "config", "serving"]


def test_application_lifespan_rejects_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teste que le cycle de vie de l'application rejette une configuration invalide."""
    monkeypatch.setattr(application, "initialize_database", lambda: None)

    def invalid_config() -> None:
        raise ValueError("invalid mail configuration")

    monkeypatch.setattr(application, "load_mail_config", invalid_config)
    app = application.get_app()

    async def run_lifespan() -> None:
        async with application.lifespan(app):
            pytest.fail("Une configuration invalide ne doit pas démarrer")

    lifespan = run_lifespan()
    with pytest.raises(ValueError, match="invalid mail configuration"):
        asyncio.run(lifespan)
