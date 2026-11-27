"""Tests de persistance et de réservation du dépôt de notifications."""

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from exc.mails import (
    MailCompileException, MailDatabaseException, MailNotFoundException,
    MailRetryNotAllowedException,
)
from models.pydantics.mails import MailIncoming
from params.mails import MailConfig
from repositories.mails import MailClient, MailsRepository


def test_conditional_claim_rejects_stale_second_session(
    isolated_session: Session, isolated_mail_config: MailConfig, mail_payload: dict[str, Any],
) -> None:
    """Teste que la réclamation conditionnelle rejette une seconde session obsolète."""
    repository = MailsRepository(isolated_session, isolated_mail_config)
    mail = repository.queue_mail(MailIncoming(**mail_payload))
    with sessionmaker(bind=isolated_session.get_bind(), expire_on_commit=False)() as second:
        stale = second.get(type(mail), mail.id)
        assert stale is not None
        assert stale.current_status == "pending"
        claimed_mail, claimed = repository._claim_mail(mail) # pylint: disable=W0212 # type: ignore
        assert claimed
        assert claimed_mail.current_status == "sending"
        refreshed, claimed_again = MailsRepository( # pylint: disable=W0212
            second, isolated_mail_config
        )._claim_mail(stale) # type: ignore
        assert not claimed_again
        assert refreshed.current_status == "sending"


def test_missing_mail_and_disallowed_manual_retry(
    isolated_session: Session, isolated_mail_config: MailConfig, mail_payload: dict[str, Any],
) -> None:
    """Teste la gestion des mails manquants et des retries manuels interdits."""
    repository = MailsRepository(isolated_session, isolated_mail_config)
    assert repository.get_mail_by_id("absent") is None
    with pytest.raises(MailNotFoundException):
        repository.process_mail("absent")
    with pytest.raises(MailNotFoundException):
        repository.retry_failed_mail("absent")

    mail = repository.queue_mail(MailIncoming(**mail_payload))
    mail.current_status = "failed"
    mail.recipients = ""
    isolated_session.commit()
    with pytest.raises(MailRetryNotAllowedException):
        repository.retry_failed_mail(mail.id)


def test_queue_commit_failure_rolls_back(
    isolated_session: Session, isolated_mail_config: MailConfig,
    mail_payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teste que l'échec du commit lors de la mise en file d'attente d'un mail déclenche
    un rollback.
    """
    repository = MailsRepository(isolated_session, isolated_mail_config)
    incoming = MailIncoming(**mail_payload)
    rollback = isolated_session.rollback
    rollbacks: list[bool] = []

    def fail_commit() -> None:
        raise SQLAlchemyError("database failure")

    def record_rollback() -> None:
        rollbacks.append(True)
        rollback()

    monkeypatch.setattr(isolated_session, "commit", fail_commit)
    monkeypatch.setattr(isolated_session, "rollback", record_rollback)
    with pytest.raises(MailDatabaseException, match="Could not queue email"):
        repository.queue_mail(incoming)
    assert rollbacks == [True]
    assert repository.get_mails() == []


def test_reconcile_only_interrupted_messages(
    isolated_session: Session, isolated_mail_config: MailConfig, mail_payload: dict[str, Any],
) -> None:
    """Teste que seule la réconciliation des mails interrompus est effectuée."""
    repository = MailsRepository(isolated_session, isolated_mail_config)
    interrupted = repository.queue_mail(MailIncoming(**mail_payload))
    already_sent = repository.queue_mail(MailIncoming(**mail_payload))
    interrupted.current_status = "sending"
    already_sent.current_status = "sent"
    isolated_session.commit()

    assert repository.reconcile_interrupted_mails() == 1
    assert interrupted.current_status == "pending"
    assert "may be duplicated" in (interrupted.last_error or "")
    assert interrupted.statuses[-1].comment == interrupted.last_error
    assert already_sent.current_status == "sent"
    assert repository.reconcile_interrupted_mails() == 0


def test_listing_orders_newest_first(
    isolated_session: Session, isolated_mail_config: MailConfig, mail_payload: dict[str, Any],
) -> None:
    """Teste que la liste des mails est ordonnée du plus récent au plus ancien."""
    repository = MailsRepository(isolated_session, isolated_mail_config)
    assert repository.get_mails() == []
    older = repository.queue_mail(MailIncoming(**mail_payload))
    newer = repository.queue_mail(MailIncoming(**mail_payload))
    older.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    newer.created_at = older.created_at + timedelta(seconds=1)
    isolated_session.commit()
    assert [mail.id for mail in repository.get_mails()] == [newer.id, older.id]


@pytest.mark.parametrize("template,values", [
    ("unknown.html", [{"key": "service", "value": "API"}]),
    ("service_down.html", [{"key": "service", "value": "API"}]),
])
def test_invalid_templates_are_not_persisted(
    isolated_session: Session, isolated_mail_config: MailConfig, mail_payload: dict[str, Any],
    template: str, values: list[dict[str, str]],
) -> None:
    """Teste que les templates invalides ne sont pas persistés."""
    repository = MailsRepository(isolated_session, isolated_mail_config)
    incoming = MailIncoming(**dict(mail_payload, template=template, jinja_values=values))
    with pytest.raises(MailCompileException):
        repository.queue_mail(incoming)
    assert repository.get_mails() == []


def test_smtp_success_commit_failure_does_not_attempt_imap(
    isolated_session: Session, isolated_mail_config: MailConfig,
    mail_payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teste que l'échec de commit après un succès SMTP n'essaie pas le fallback IMAP."""
    repository = MailsRepository(isolated_session, isolated_mail_config)
    mail = repository.queue_mail(MailIncoming(**mail_payload))
    mail_id = mail.id
    commit = isolated_session.commit
    commits: list[str] = []
    copies: list[str] = []

    def fail_second_commit() -> None:
        commits.append("commit")
        if len(commits) == 2:
            raise SQLAlchemyError("database failure")
        commit()

    def send(_client: MailClient, _message: EmailMessage) -> set[str]:
        return set()

    def copy(_client: MailClient, _message: EmailMessage) -> bool:
        copies.append("copy")
        return True

    monkeypatch.setattr(isolated_session, "commit", fail_second_commit)
    monkeypatch.setattr(MailClient, "send", send)
    monkeypatch.setattr(MailClient, "copy_to_sent", copy)
    with pytest.raises(MailDatabaseException, match="SMTP accepted the message"):
        repository.process_mail(mail_id)
    assert not copies
    reloaded = repository.get_mail_by_id(mail_id)
    assert reloaded is not None
    assert reloaded.current_status == "sending"
