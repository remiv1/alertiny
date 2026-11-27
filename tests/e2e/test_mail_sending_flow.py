"""Parcours complet de notification avec transports simulés."""

from collections.abc import Callable
from email.message import EmailMessage
from typing import Any

import pytest
from sqlalchemy.orm import Session

from models.db.mails import Mail
from params.mails import MailConfig
from repositories.mails import MailClient
from repositories.worker import MailWorker


def test_api_queue_worker_smtp_imap_and_public_status(
    http_request: Callable[..., Any], mail_payload: dict[str, Any],
    isolated_session: Session, isolated_mail_config: MailConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teste le parcours complet de notification avec transports SMTP et IMAP simulés."""
    deliveries: list[tuple[str, str]] = []

    def send(client: MailClient, message: EmailMessage) -> set[str]:
        deliveries.append(("smtp", client.mail.recipients))
        assert message["Message-ID"] == client.mail.provider_id
        return set()

    def copy(client: MailClient, message: EmailMessage) -> bool:
        deliveries.append(("imap", str(message["To"])))
        assert client.mail.current_status == "sent"
        assert client.mail.body is None
        return True

    monkeypatch.setattr(MailClient, "send", send)
    monkeypatch.setattr(MailClient, "copy_to_sent", copy)
    created = http_request("POST", "/api/v1/mails/", mail_payload)
    assert created.status == 202
    mail_id = created.body["id"]
    assert not deliveries

    assert MailWorker(isolated_session, isolated_mail_config).run_once() == 1
    result = http_request("GET", f"/api/v1/mails/{mail_id}")
    assert result.body["status"] == "sent"
    assert result.body["sent_at"] is not None
    assert result.body["imap_copied_at"] is not None
    assert not {"recipients", "body", "jinja_values"} & result.body.keys()
    assert deliveries == [("smtp", "ops@example.com"), ("imap", "ops@example.com")]
    mail = isolated_session.get(Mail, mail_id)
    assert mail is not None
    assert mail.recipients == mail.delivered_recipients == mail.jinja_values == ""
    assert mail.body is None
    assert MailWorker(isolated_session, isolated_mail_config).run_once() == 0
