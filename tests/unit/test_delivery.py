"""Tests unitaires du rendu, de la file et des transports SMTP/IMAP.

Les tests utilisent une base SQLite éphémère et remplacent les transports réseau par
des faux clients. Ils couvrent également les règles de conservation des destinataires,
la récupération après interruption, la validation des requêtes et la représentation
publique renvoyée par les routes.

.. fixtures::
    - :func:`database_session` : fournit une session SQLite isolée.
    - :func:`mail_config` : retourne une configuration de transport de test.
    - :func:`incoming_mail` : construit un exemple de requête mail valide.

.. moduleauthor:: Rémi Verschuur <rverschuur@audit-io.fr>
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from email.message import EmailMessage

import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.v1.mails import _queue, router # type: ignore
from exc.mails import MailCompileException, MailSendException
from models.db._common import Base
from models.db.mails import Mail
from models.pydantics.mails import JinjaValues, MailIncoming, Recipient
from params.mails import IMAPConfig, MailConfig, SMTPConfig
from repositories import mails as mails_repository
from repositories.mails import MailClient, MailsRepository, repo as mails_repo
from repositories.mails.client import MailClient as DirectMailClient


@pytest.fixture
def database_session() -> Iterator[Session]:
    """Fournit une session SQLite en mémoire et détruit sa base après le test.

    :yields: Session reliée à une base de données isolée du reste de la suite.
    :yieldtype: sqlalchemy.orm.Session
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    with test_session() as database_session: # pylint: disable=W0621
        yield database_session
    engine.dispose()


@pytest.fixture
def mail_config() -> MailConfig:
    """Construit une configuration SMTP/IMAP sans identifiants réels.

    :returns: Configuration destinée aux tests unitaires.
    :rtype: params.mails.MailConfig
    """
    return MailConfig(
        sender="alerts@example.com",
        smtp=SMTPConfig("smtp.example.com", 587, False, True),
        retries=1,
        imap=IMAPConfig(True, "imap.example.com", 993, True, False, "Sent"),
    )


def incoming_mail() -> MailIncoming:
    """Crée une requête valide utilisant le template de service indisponible.

    :returns: Données d'entrée avec deux variables et un destinataire.
    :rtype: models.pydantics.mails.MailIncoming
    """
    return MailIncoming(
        sender="alerts@example.com",
        subject=None,
        template="service_down.html",
        jinja_values=[
            JinjaValues(key="service", value="<API>"),
            JinjaValues(key="hostname", value="host-01"),
        ],
        attachments=[],
        recipient=[Recipient(email="ops@example.com")],
    )


def successful_copy(_client: MailClient, _message: EmailMessage) -> bool:
    """Simule une copie IMAP réussie."""
    return True


def successful_send(_client: MailClient, _message: EmailMessage) -> set[str]:
    """Simule un envoi SMTP réussi."""
    return set()


def test_queue_renders_and_persists_mail_without_exposing_payload(
    database_session: Session, # pylint: disable=W0621
    mail_config: MailConfig, # pylint: disable=W0621
) -> None:
    """Vérifie le rendu configuré, la persistance et l'absence de fuite de données.

    :param database_session: Session SQLite éphémère.
    :type database_session: sqlalchemy.orm.Session
    :param mail_config: Configuration mail de test.
    :type mail_config: params.mails.MailConfig
    :returns: ``None``.
    :rtype: None
    """
    repository = MailsRepository(database_session, mail_config)

    mail = repository.queue_mail(incoming_mail())
    public_status = repository.public_status(mail)

    assert mail.id
    assert mail.current_status == "pending"
    assert mail.subject == "Service <API> indisponible"
    assert "&lt;API&gt;" in (mail.body or "")
    assert public_status["id"] == mail.id
    assert "recipients" not in public_status
    assert len(repository.get_mails()) == 1


def test_imap_failure_does_not_retry_successful_smtp_or_retain_recipients(
    database_session: Session, # pylint: disable=W0621
    mail_config: MailConfig, # pylint: disable=W0621
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vérifie qu'un échec IMAP après SMTP ne déclenche pas un second envoi.

    :param database_session: Session SQLite éphémère.
    :type database_session: sqlalchemy.orm.Session
    :param mail_config: Configuration mail de test.
    :type mail_config: params.mails.MailConfig
    :param monkeypatch: Outil pytest pour substituer les méthodes de transport.
    :type monkeypatch: pytest.MonkeyPatch
    :returns: ``None``.
    :rtype: None
    """
    repository = MailsRepository(database_session, mail_config)
    mail = repository.queue_mail(incoming_mail())
    smtp_calls = 0

    def send(self: object, message: EmailMessage) -> set[str]: # pylint: disable=W0621, W0613
        nonlocal smtp_calls
        smtp_calls += 1
        return set()

    def fail_copy(self: object, message: EmailMessage) -> None:
        raise MailSendException("IMAP unavailable")

    monkeypatch.setattr(mails_repository.MailClient, "send", send)
    monkeypatch.setattr(mails_repository.MailClient, "copy_to_sent", fail_copy)

    result = repository.process_mail(mail.id)
    repository.process_mail(mail.id)

    assert smtp_calls == 1
    assert result.current_status == "sent"
    assert result.recipients == ""
    assert result.body is None
    assert result.imap_copied_at is None
    assert result.statuses[-1].comment is not None
    assert repository.process_due_mails() == 0


def test_smtp_failure_retries_then_clears_recipients_on_success(
    database_session: Session, # pylint: disable=W0621
    mail_config: MailConfig, # pylint: disable=W0621
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vérifie la planification d'un retry SMTP puis l'effacement des destinataires.

    :param database_session: Session SQLite éphémère.
    :type database_session: sqlalchemy.orm.Session
    :param mail_config: Configuration mail de test.
    :type mail_config: params.mails.MailConfig
    :param monkeypatch: Outil pytest pour simuler un échec SMTP puis un succès.
    :type monkeypatch: pytest.MonkeyPatch
    :returns: ``None``.
    :rtype: None
    """
    repository = MailsRepository(database_session, mail_config)
    mail = repository.queue_mail(incoming_mail())
    smtp_calls = 0

    def fail_once(self: object, message: EmailMessage) -> set[str]: # pylint: disable=W0621, W0613
        nonlocal smtp_calls
        smtp_calls += 1
        if smtp_calls == 1:
            raise MailSendException("SMTP unavailable")
        return set()

    monkeypatch.setattr(mails_repository.MailClient, "send", fail_once)
    monkeypatch.setattr(mails_repository.MailClient, "copy_to_sent", successful_copy)

    retry = repository.process_mail(mail.id)
    assert retry.current_status == "pending"
    assert retry.retry_count == 1
    assert retry.next_retry_at is not None

    sent = repository.process_mail(mail.id)

    assert sent.current_status == "sent"
    assert sent.recipients == ""
    assert sent.retry_count == 1
    assert smtp_calls == 2


def test_partial_smtp_acceptance_retries_only_refused_recipients(
    database_session: Session, # pylint: disable=W0621
    mail_config: MailConfig, # pylint: disable=W0621
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vérifie que seuls les destinataires refusés sont réessayés.

    :param database_session: Session SQLite éphémère.
    :type database_session: sqlalchemy.orm.Session
    :param mail_config: Configuration mail de test.
    :type mail_config: params.mails.MailConfig
    :param monkeypatch: Outil pytest pour simuler une réponse SMTP partielle.
    :type monkeypatch: pytest.MonkeyPatch
    :returns: ``None``.
    :rtype: None
    """
    repository = MailsRepository(database_session, mail_config)
    incoming = incoming_mail()
    incoming.recipient.append(Recipient(email="dev@example.com"))
    mail = repository.queue_mail(incoming)
    attempts: list[tuple[str, str]] = []

    def refuse_one_once(self: MailClient, message: EmailMessage) -> set[str]:
        attempts.append((self.mail.recipients, str(message["To"])))
        if len(attempts) == 1:
            return {"ops@example.com"}
        return set()

    monkeypatch.setattr(mails_repository.MailClient, "send", refuse_one_once)
    monkeypatch.setattr(mails_repository.MailClient, "copy_to_sent", successful_copy)

    retry = repository.process_mail(mail.id)
    assert retry.current_status == "pending"
    assert retry.recipients == "ops@example.com"
    assert retry.delivered_recipients == "dev@example.com"

    sent = repository.process_mail(mail.id)

    assert sent.current_status == "sent"
    assert sent.recipients == ""
    assert sent.delivered_recipients == ""
    assert attempts[1][0] == "ops@example.com"
    assert "dev@example.com" in attempts[1][1]
    assert "ops@example.com" in attempts[1][1]


def test_terminal_failure_retains_recipients_until_successful_retry(
    database_session: Session, # pylint: disable=W0621
    mail_config: MailConfig, # pylint: disable=W0621
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vérifie la conservation des destinataires d'un échec jusqu'à une livraison.

    :param database_session: Session SQLite éphémère.
    :type database_session: sqlalchemy.orm.Session
    :param mail_config: Configuration mail dont le nombre de retries sera ajusté.
    :type mail_config: params.mails.MailConfig
    :param monkeypatch: Outil pytest pour simuler l'échec puis le succès SMTP.
    :type monkeypatch: pytest.MonkeyPatch
    :returns: ``None``.
    :rtype: None
    """
    config = replace(mail_config, retries=0)
    repository = MailsRepository(database_session, config)
    mail = repository.queue_mail(incoming_mail())

    def fail(self: MailClient, message: EmailMessage) -> set[str]:
        raise MailSendException("SMTP unavailable")

    monkeypatch.setattr(mails_repository.MailClient, "send", fail)
    failed = repository.process_mail(mail.id)
    assert failed.current_status == "failed"
    assert failed.recipients == "ops@example.com"
    assert failed.body

    requeued = repository.retry_failed_mail(mail.id)
    assert requeued.current_status == "pending"
    assert requeued.retry_count == 0
    assert requeued.recipients == "ops@example.com"

    monkeypatch.setattr(mails_repository.MailClient, "send", successful_send)
    monkeypatch.setattr(mails_repository.MailClient, "copy_to_sent", successful_copy)
    sent = repository.process_mail(mail.id)

    assert sent.current_status == "sent"
    assert sent.recipients == ""
    assert sent.body is None


def test_reconcile_requeues_interrupted_delivery_with_warning(
    database_session: Session, # pylint: disable=W0621
    mail_config: MailConfig, # pylint: disable=W0621
) -> None:
    """Vérifie la remise en file des messages laissés en état ``sending``.

    :param database_session: Session SQLite éphémère.
    :type database_session: sqlalchemy.orm.Session
    :param mail_config: Configuration mail de test.
    :type mail_config: params.mails.MailConfig
    :returns: ``None``.
    :rtype: None
    """
    repository = MailsRepository(database_session, mail_config)
    mail = repository.queue_mail(incoming_mail())
    mail.current_status = "sending"
    database_session.commit()

    recovered = repository.reconcile_interrupted_mails()

    assert recovered == 1
    assert mail.current_status == "pending"
    assert mail.recipients == "ops@example.com"
    assert "may be duplicated" in (mail.last_error or "")


def test_mail_client_sends_mime_message_and_copies_it_to_imap(
    mail_config: MailConfig, # pylint: disable=W0621
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vérifie la création du message MIME et l'ajout du message au dossier IMAP.

    :param mail_config: Configuration SMTP/IMAP de test.
    :type mail_config: params.mails.MailConfig
    :param monkeypatch: Outil pytest pour substituer les clients SMTP et IMAP.
    :type monkeypatch: pytest.MonkeyPatch
    :returns: ``None``.
    :rtype: None
    """
    mail = Mail(
        id="mail-1",
        sender="requester@example.com",
        recipients="ops@example.com",
        subject="Service unavailable",
        template="service_down.html",
        body="<p>Service is down</p>",
        jinja_values="",
        provider_id="<mail-1@example.com>",
    )
    client = MailClient(mail, mail_config)
    assert DirectMailClient is MailClient
    message = client.create_message()
    smtp_calls: list[tuple[str, list[str], str]] = []
    imap_calls: list[tuple[str, str, bytes]] = []

    class FakeSMTP:
        """Faux client SMTP enregistrant les arguments d'envoi sans réseau."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            """Initialise le faux client sans ouvrir de connexion.

            :param args: Arguments SMTP ignorés par le faux client.
            :type args: object
            :param kwargs: Options SMTP ignorées par le faux client.
            :type kwargs: object
            """
            pass # pylint: disable=W0107

        def __enter__(self) -> 'FakeSMTP':
            """Retourne l'instance lors de l'entrée dans le gestionnaire de contexte.

            :returns: Cette instance.
            :rtype: FakeSMTP
            """
            return self

        def __exit__(self, *args: object) -> None:
            """Termine le gestionnaire de contexte sans effet réseau.

            :param args: Arguments transmis par le gestionnaire de contexte.
            :type args: object
            :returns: ``None``.
            :rtype: None
            """
            return None

        def starttls(self, **kwargs: object) -> None:
            """Simule la négociation STARTTLS sans modifier l'état du test.

            :param kwargs: Options STARTTLS ignorées par le faux client.
            :type kwargs: object
            :returns: ``None``.
            :rtype: None
            """
            pass # pylint: disable=W0107

        def ehlo(self) -> None:
            """Simule la commande EHLO SMTP.

            :returns: ``None``.
            :rtype: None
            """
            pass # pylint: disable=W0107

        def send_message(
            self,
            message: EmailMessage,
            *,
            from_addr: str,
            to_addrs: list[str],
        ) -> dict[str, tuple[int, bytes]]:
            """Enregistre le message et simule l'acceptation de tous les destinataires.

            :param message: Message MIME transmis par le client.
            :type message: email.message.EmailMessage
            :param from_addr: Adresse d'enveloppe de l'expéditeur.
            :type from_addr: str
            :param to_addrs: Destinataires de l'enveloppe SMTP.
            :type to_addrs: list[str]
            :returns: Dictionnaire vide indiquant l'absence de refus.
            :rtype: dict[str, tuple[int, bytes]]
            """
            smtp_calls.append((from_addr, to_addrs, message.get_content_type()))
            return {}

    class FakeIMAP:
        """Faux client IMAP enregistrant la commande APPEND sans réseau."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            """Initialise le faux client sans ouvrir de connexion.

            :param args: Arguments IMAP ignorés par le faux client.
            :type args: object
            :param kwargs: Options IMAP ignorées par le faux client.
            :type kwargs: object
            """
            pass # pylint: disable=W0107

        def append(
            self,
            folder: str,
            flags: str,
            date_time: str, # pylint: disable=W0621, W0613
            message_bytes: bytes,
        ) -> tuple[str, list[bytes]]:
            """Enregistre l'ajout et simule une réponse IMAP ``OK``.

            :param folder: Dossier cible.
            :type folder: str
            :param flags: Drapeaux appliqués au message ajouté.
            :type flags: str
            :param date_time: Date IMAP du message.
            :type date_time: str
            :param message_bytes: Représentation RFC du message.
            :type message_bytes: bytes
            :returns: Réponse IMAP ``OK`` et un message de confirmation.
            :rtype: tuple[str, list[bytes]]
            """
            imap_calls.append((folder, flags, message_bytes))
            return "OK", [b"stored"]

        def logout(self) -> tuple[str, list[bytes]]:
            """Simule la fermeture de la connexion IMAP.

            :returns: Réponse IMAP ``BYE``.
            :rtype: tuple[str, list[bytes]]
            """
            return "BYE", [b"logout"]

    monkeypatch.setattr(mails_repo, "SMTP", FakeSMTP)
    monkeypatch.setattr(mails_repo, "IMAP4_SSL", FakeIMAP)

    assert message["From"] == mail_config.sender
    assert message.get_content_type() == "multipart/alternative"
    html_part = message.get_body(preferencelist=("html",))
    assert html_part is not None
    assert "Service is down" in html_part.get_content()
    assert client.send(message) == set()
    assert client.copy_to_sent(message)
    assert smtp_calls == [
        (mail_config.sender, ["ops@example.com"], "multipart/alternative")
    ]
    assert imap_calls[0][0:2] == ("Sent", "\\Seen")
    assert b"Service is down" in imap_calls[0][2]


def test_mail_input_rejects_attachments_in_v1() -> None:
    """Vérifie le refus des pièces jointes et leur valeur vide par défaut.

    :returns: ``None``.
    :rtype: None
    """
    payload = incoming_mail().model_dump()
    payload["attachments"] = ["report.pdf"]

    with pytest.raises(ValueError, match="not supported in v1"):
        MailIncoming(**payload)

    payload.pop("attachments")
    assert MailIncoming(**payload).attachments == []


@pytest.mark.parametrize("address", ["", "not-an-email", "ops@example.com,attacker@example.com"])
def test_mail_input_rejects_invalid_addresses(address: str) -> None:
    """Vérifie qu'une adresse destinataire mal formée est rejetée.

    :param address: Adresse invalide utilisée pour ce cas paramétré.
    :type address: str
    :returns: ``None``.
    :rtype: None
    """
    with pytest.raises(ValidationError):
        Recipient(email=address)


def test_template_values_cannot_inject_email_subject_headers(
    database_session: Session, # pylint: disable=W0621
    mail_config: MailConfig, # pylint: disable=W0621
) -> None:
    """Vérifie que les retours de ligne ne peuvent pas injecter d'en-tête mail.

    :param database_session: Session SQLite éphémère.
    :type database_session: sqlalchemy.orm.Session
    :param mail_config: Configuration mail de test.
    :type mail_config: params.mails.MailConfig
    :returns: ``None``.
    :rtype: None
    """
    incoming = incoming_mail()
    incoming.jinja_values[0].value = "service\nBcc: attacker@example.com"

    with pytest.raises(MailCompileException, match="must not contain line breaks"):
        MailsRepository(database_session, mail_config).queue_mail(incoming)


def test_api_accepts_queue_request_and_returns_only_tracking_data(
    database_session: Session, # pylint: disable=W0621
) -> None:
    """Vérifie le contrat de file et l'absence de données privées dans la réponse.

    :param database_session: Session SQLite éphémère.
    :type database_session: sqlalchemy.orm.Session
    :returns: ``None``.
    :rtype: None
    """
    queued = _queue(incoming_mail(), database_session)
    post_route = next(
        route
        for route in router.routes
        if isinstance(route, APIRoute)
        and route.path == "/mails/"
        and route.methods is not None
        and "POST" in route.methods
    )
    saved_mail = MailsRepository(database_session).get_mail_by_id(queued["id"])

    assert post_route.status_code == 202
    assert queued["status"] == "pending"
    assert "recipients" not in queued
    assert saved_mail is not None
    assert MailsRepository.public_status(saved_mail)["status"] == "pending"
    assert "recipients" not in MailsRepository.public_status(saved_mail)
