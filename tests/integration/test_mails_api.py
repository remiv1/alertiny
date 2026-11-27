"""Tests HTTP des routes de notifications, sans réseau externe."""

from collections.abc import Callable
from email.message import EmailMessage
from typing import Any

import pytest
from sqlalchemy.orm import Session

from exc.mails import MailDatabaseException
from models.db.mails import Mail
from repositories.mails import MailClient, MailsRepository


@pytest.mark.parametrize("path", ["/api/v1/mails/", "/api/v1/mails/send"])
def test_create_and_read_mail_without_disclosing_payload(
    http_request: Callable[..., Any], mail_payload: dict[str, Any], path: str,
) -> None:
    """Teste la création et la lecture d'un mail sans divulguer le contenu du payload."""
    response = http_request("POST", path, mail_payload)
    assert response.status == 202
    assert set(response.body) == {"id", "status"}
    assert response.body["status"] == "pending"

    result = http_request("GET", f"/api/v1/mails/{response.body['id']}")
    assert result.status == 200
    assert result.body["status"] == "pending"
    assert not {"recipients", "body", "jinja_values"} & result.body.keys()
    listing = http_request("GET", "/api/v1/mails/")
    assert listing.body["mails"][0]["id"] == response.body["id"]


@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_mail_routes_require_valid_bearer(
    http_request: Callable[..., Any], token: str | None,
) -> None:
    """Teste que les routes de mails nécessitent un token Bearer valide."""
    response = http_request("GET", "/api/v1/mails/", token=token)
    assert response.status == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_missing_server_token_returns_503(
    http_request: Callable[..., Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teste que l'absence du token serveur retourne un 503."""
    monkeypatch.delenv("ALERTINY_BEARER_TOKEN")
    assert http_request("GET", "/api/v1/mails/").status == 503


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/v1/mails/absent"),
    ("POST", "/api/v1/mails/absent/retry"),
    ("PUT", "/api/v1/mails/send/absent"),
])
def test_unknown_mail_returns_404(
    http_request: Callable[..., Any], method: str, path: str,
) -> None:
    """Teste que les mails inconnus retournent un 404."""
    assert http_request(method, path).status == 404


def test_invalid_template_and_retry_conflict(
    http_request: Callable[..., Any], mail_payload: dict[str, Any], isolated_session: Session,
) -> None:
    """Teste la gestion d'un template invalide et d'un conflit de retry."""
    invalid = dict(mail_payload, template="unknown.html")
    assert http_request("POST", "/api/v1/mails/", invalid).status == 422
    queued = http_request("POST", "/api/v1/mails/", mail_payload)
    mail = isolated_session.get(Mail, queued.body["id"])
    assert mail is not None
    mail.current_status = "sent"
    isolated_session.commit()
    result = http_request("POST", f"/api/v1/mails/{mail.id}/retry")
    assert result.status == 409


def test_retry_failed_mail_and_immediate_delivery(
    http_request: Callable[..., Any], mail_payload: dict[str, Any],
    isolated_session: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teste le retry d'un mail échoué et la livraison immédiate."""
    deliveries: list[str] = []

    def send(client: MailClient, _message: EmailMessage) -> set[str]:
        deliveries.append(client.mail.recipients)
        return set()

    def copy(_client: MailClient, _message: EmailMessage) -> bool:
        return True

    monkeypatch.setattr(MailClient, "send", send)
    monkeypatch.setattr(MailClient, "copy_to_sent", copy)
    queued = http_request("POST", "/api/v1/mails/", mail_payload)
    mail = isolated_session.get(Mail, queued.body["id"])
    assert mail is not None
    mail.current_status = "failed"
    mail.retry_count = 2
    isolated_session.commit()

    retried = http_request("POST", f"/api/v1/mails/{mail.id}/retry")
    assert retried.status == 202
    assert retried.body["status"] == "pending"
    assert retried.body["retry_count"] == 0
    sent = http_request("PUT", f"/api/v1/mails/send/{mail.id}")
    assert sent.status == 200
    assert sent.body["status"] == "sent"
    assert deliveries == ["ops@example.com"]
    assert http_request("PUT", f"/api/v1/mails/send/{mail.id}").body["status"] == "sent"
    assert len(deliveries) == 1


@pytest.mark.parametrize("method,path,repository_method", [
    ("GET", "/api/v1/mails/", "get_mails"),
    ("GET", "/api/v1/mails/absent", "get_mail_by_id"),
    ("POST", "/api/v1/mails/", "queue_mail"),
    ("POST", "/api/v1/mails/absent/retry", "retry_failed_mail"),
    ("PUT", "/api/v1/mails/send/absent", "process_mail"),
])
def test_database_errors_become_http_500_without_internal_details( # pylint: disable=R0913,R0917
    http_request: Callable[..., Any], mail_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch, method: str, path: str, repository_method: str,
) -> None:
    """Teste que les erreurs de base de données deviennent des HTTP 500 sans détails internes."""
    def fail(*_args: object, **_kwargs: object) -> None:
        raise MailDatabaseException("private database details")

    monkeypatch.setattr(MailsRepository, repository_method, fail)
    response = http_request(
        method,
        path,
        mail_payload if repository_method == "queue_mail" else None
    )
    assert response.status == 500
    assert "private database details" not in str(response.body)
