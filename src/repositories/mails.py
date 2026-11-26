"""Persistance et livraison des notifications par courrier électronique.

Ce module regroupe le client de transport SMTP/IMAP et le dépôt qui gère le cycle de vie
des notifications. Le dépôt valide les templates configurés, enregistre les messages à
envoyer dans SQLite, tient leur historique de statuts et permet au worker de reprendre
les livraisons après une interruption.

Les adresses des destinataires sont conservées tant qu'une livraison reste à effectuer.
Elles sont supprimées, avec le corps rendu et les valeurs du template, dès que SMTP a
accepté le message pour tous les destinataires. Une erreur de copie IMAP est alors
enregistrée séparément et ne déclenche pas un nouvel envoi SMTP.

.. classes::
    - :class:`MailClient` : construit les messages MIME, les transmet à SMTP et copie
      les messages envoyés dans le dossier IMAP configuré.
    - :class:`MailsRepository` : valide, persiste, suit et traite les notifications.

.. functions::
    - :func:`_utc_now` : retourne l'heure courante avec un fuseau UTC.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid
import logging
import ssl
import time
from typing import Sequence

from imaplib import IMAP4, IMAP4_SSL, Time2Internaldate
from jinja2 import Environment, Template, TemplateError, select_autoescape
from smtplib import SMTP, SMTP_SSL, SMTPException
from sqlalchemy import or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from exc.mails import (
    MailCompileException,
    MailDatabaseException,
    MailNotFoundException,
    MailRetryNotAllowedException,
    MailSendException,
)
from models.db.mails import Mail
from models.db.status import MailStatus, Status
from models.pydantics.mails import MailIncoming
from params.mails import MailConfig, load_mail_config
from params.templates import get_templates_directory, load_templates_config

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Retourne l'heure courante comme date-heure consciente du fuseau UTC.

    :returns: L'instant courant en UTC.
    :rtype: datetime
    """
    return datetime.now(timezone.utc)


class MailClient:
    """Client de transport SMTP et IMAP pour une notification persistée.

    Le client construit un message multipart contenant une version texte et une version
    HTML. Il utilise les paramètres SMTP de :class:`~params.mails.MailConfig` et renvoie
    les adresses refusées par le serveur afin que le dépôt ne réessaie que ces adresses.
    La copie IMAP est exécutée après l'enregistrement du succès SMTP.

    :param mail: Notification persistée à transmettre. Les destinataires non encore
        acceptés par SMTP sont stockés dans ``mail.recipients``.
    :type mail: models.db.mails.Mail
    :param config: Paramètres SMTP et IMAP utilisés par le client.
    :type config: params.mails.MailConfig

    .. attributs::
        - ``mail`` (:class:`~models.db.mails.Mail`) : notification en cours de livraison.
        - ``config`` (:class:`~params.mails.MailConfig`) : configuration des transports.
        - ``timeout`` (float) : délai maximal de connexion SMTP, en secondes.
    """

    def __init__(self, mail: Mail, config: MailConfig) -> None:
        """Initialise le client avec une notification et sa configuration.

        :param mail: Enregistrement contenant l'expéditeur, les destinataires et le
            contenu HTML à envoyer.
        :type mail: models.db.mails.Mail
        :param config: Paramètres des serveurs SMTP et IMAP.
        :type config: params.mails.MailConfig
        """
        self.mail = mail
        self.config = config
        self.timeout = 30.0

    def create_message(self) -> EmailMessage:
        """Construit le message MIME à transmettre et à archiver dans IMAP.

        Le champ ``To`` contient l'ensemble des destinataires déjà acceptés et encore
        en attente, tandis que l'enveloppe SMTP est limitée aux destinataires en attente.
        Le corps HTML est ajouté comme alternative au texte simple.

        :returns: Message MIME avec en-têtes, contenu texte et contenu HTML.
        :rtype: email.message.EmailMessage
        """
        message = EmailMessage()
        message["From"] = self.config.sender
        all_recipients = list(dict.fromkeys(
            [
                *(
                    value.strip()
                    for value in (self.mail.delivered_recipients or "").split(",")
                    if value.strip()
                ),
                *(value.strip() for value in self.mail.recipients.split(",") if value.strip()),
            ]
        ))
        message["To"] = ", ".join(all_recipients)
        message["Subject"] = self.mail.subject or ""
        message["Message-ID"] = self.mail.provider_id
        message.set_content("Cette alerte est disponible au format HTML.")
        message.add_alternative(self.mail.body or "", subtype="html")
        return message

    def send(self, message: EmailMessage) -> set[str]:
        """Transmet le message à SMTP et identifie les destinataires refusés.

        La connexion utilise TLS implicite ou STARTTLS suivant la configuration. Les
        identifiants sont utilisés lorsqu'ils sont configurés. Une réponse de refus
        partiel est retournée au dépôt pour éviter de renvoyer le message aux
        destinataires déjà acceptés.

        :param message: Message MIME construit par :meth:`create_message`.
        :type message: email.message.EmailMessage
        :returns: Ensemble des adresses refusées par SMTP; l'ensemble est vide si
            toutes les adresses ont été acceptées.
        :rtype: set[str]
        :raises MailSendException: Si la connexion, l'authentification ou la
            transmission échoue.
        """
        recipients = [value.strip() for value in self.mail.recipients.split(",") if value.strip()]
        try:
            if self.config.smtp.tls:
                server: SMTP = SMTP_SSL(
                    self.config.smtp.server,
                    self.config.smtp.port,
                    timeout=self.timeout,
                    context=ssl.create_default_context(),
                )
            else:
                server = SMTP(
                    self.config.smtp.server,
                    self.config.smtp.port,
                    timeout=self.timeout,
                )
            with server:
                if self.config.smtp.starttls and not self.config.smtp.tls:
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                if self.config.smtp.username and self.config.smtp.password:
                    server.login(self.config.smtp.username, self.config.smtp.password)
                refused = server.send_message(
                    message,
                    from_addr=self.config.sender,
                    to_addrs=recipients,
                )
                return set(refused)
        except (SMTPException, OSError, TimeoutError) as error:
            raise MailSendException(f"SMTP delivery failed: {error}") from error

    def copy_to_sent(self, message: EmailMessage) -> bool:
        """Copie dans IMAP le message dont l'envoi SMTP a réussi.

        L'opération utilise le dossier configuré et ajoute le drapeau ``\\Seen``.
        L'échec de cette copie ne remet pas en cause le statut SMTP du message.

        :param message: Message MIME déjà transmis via SMTP.
        :type message: email.message.EmailMessage
        :returns: ``True`` lorsque le serveur IMAP confirme l'ajout.
        :rtype: bool
        :raises MailSendException: Si la copie est désactivée ou si la connexion,
            l'authentification ou l'ajout IMAP échoue.
        """
        if not self.config.imap.copy_to_sent:
            raise MailSendException("IMAP sent-message copying must be enabled in v1")

        client: IMAP4 | None = None
        try:
            if self.config.imap.tls:
                client = IMAP4_SSL(
                    self.config.imap.server,
                    self.config.imap.port,
                    ssl_context=ssl.create_default_context(),
                )
            else:
                client = IMAP4(self.config.imap.server, self.config.imap.port)
                if self.config.imap.starttls:
                    client.starttls(ssl_context=ssl.create_default_context())

            if self.config.imap.username and self.config.imap.password:
                client.login(self.config.imap.username, self.config.imap.password)
            result, _ = client.append(
                self.config.imap.folder,
                "\\Seen",
                Time2Internaldate(time.time()),
                message.as_bytes(),
            )
            if result != "OK":
                raise MailSendException("IMAP server rejected the sent-message copy")
            return True
        except (IMAP4.error, OSError, TimeoutError) as error:
            raise MailSendException(f"IMAP copy failed: {error}") from error
        finally:
            if client is not None:
                try:
                    client.logout()
                except (IMAP4.error, OSError):
                    logger.warning("IMAP logout failed after the copy attempt")


class MailsRepository:
    """Dépôt SQLAlchemy et service de cycle de vie des notifications.

    Cette classe centralise le rendu et la validation des templates, la persistance dans
    la file SQLite, les transitions de statut, les retries SMTP et la réconciliation
    des traitements interrompus. Les opérations de transport sont déléguées à
    :class:`MailClient`.

    :param session: Session SQLAlchemy active. Son cycle de vie est géré par l'appelant.
    :type session: sqlalchemy.orm.Session
    :param config: Configuration mail facultative; si elle n'est pas fournie, elle est
        chargée depuis le fichier YAML et l'environnement.
    :type config: params.mails.MailConfig | None

    .. attributs::
        - ``session`` (:class:`sqlalchemy.orm.Session`) : session de persistance.
        - ``config`` (:class:`~params.mails.MailConfig`) : configuration des transports.
    """

    def __init__(self, session: Session, config: MailConfig | None = None) -> None:
        """Initialise le dépôt avec la session et la configuration mail.

        :param session: Session SQLAlchemy associée à la requête ou au lot de travail.
        :type session: sqlalchemy.orm.Session
        :param config: Configuration mail facultative. Une configuration absente est
            chargée via :func:`~params.mails.load_mail_config`.
        :type config: params.mails.MailConfig | None
        :raises OSError: Si le fichier de configuration ne peut pas être lu.
        :raises ValueError: Si une partie de la configuration est invalide.
        """
        self.session = session
        self.config = config or load_mail_config()

    @staticmethod
    def _render(mail: MailIncoming) -> tuple[str, str]:
        """Valide un modèle autorisé et rend son sujet ainsi que son contenu HTML.

        Le modèle est choisi uniquement parmi ceux déclarés dans ``templates.yaml``.
        Les variables requises sont vérifiées avant lecture du fichier HTML et
        l'échappement automatique Jinja est activé pour le contenu.

        :param mail: Données entrantes contenant le nom du modèle et ses variables.
        :type mail: models.pydantics.mails.MailIncoming
        :returns: Couple ``(sujet, contenu_html)`` rendu.
        :rtype: tuple[str, str]
        :raises MailCompileException: Si le modèle est inconnu, si des variables
            requises manquent ou si le rendu échoue.
        """
        try:
            templates_config = load_templates_config()
            template_config = next(
                (
                    item
                    for item in templates_config.templates
                    if mail.template in (item.name, item.template)
                ),
                None,
            )
            if template_config is None:
                raise MailCompileException("Unknown email template")

            values = {item.key: item.value for item in mail.jinja_values}
            missing = template_config.required_variables() - values.keys()
            if missing:
                raise MailCompileException(
                    f"Missing template variables: {', '.join(sorted(missing))}"
                )

            directory = get_templates_directory(templates_config.template_folder)
            template_path = directory / template_config.template
            if template_path.parent.resolve() != directory.resolve():
                raise MailCompileException("Invalid email template path")

            environment = Environment(
                autoescape=select_autoescape(default_for_string=True, default=True),
            )
            html_template = environment.from_string(
                template_path.read_text(encoding="utf-8")
            )
            configured_subject = Template(template_config.subject).render(**values)
            subject = mail.subject if mail.subject is not None else configured_subject
            if "\r" in subject or "\n" in subject:
                raise MailCompileException("Email subject must not contain line breaks")
            return subject, html_template.render(**values)
        except (OSError, TemplateError, StopIteration, KeyError) as error:
            raise MailCompileException("Error occurred while compiling mail") from error

    def queue_mail(self, incoming: MailIncoming) -> Mail:
        """Valide une notification et l'ajoute à la file persistante.

        Le rendu est effectué avant l'insertion. Un statut initial ``pending`` est créé
        dans l'historique; le worker se chargera ensuite de l'envoi. La V1 refuse les
        pièces jointes. Les adresses de destinataires sont conservées pendant les
        retries et supprimées après acceptation SMTP complète.

        :param incoming: Paramètres de la notification et destinataires demandés.
        :type incoming: models.pydantics.mails.MailIncoming
        :returns: Enregistrement ORM créé, incluant son identifiant de suivi.
        :rtype: models.db.mails.Mail
        :raises ValueError: Si des pièces jointes sont présentes.
        :raises MailCompileException: Si le modèle ou les variables sont invalides.
        :raises MailDatabaseException: Si l'enregistrement en base échoue.
        """
        if incoming.attachments:
            raise ValueError("Attachments are not supported in v1")
        subject, body = self._render(incoming)
        mail = Mail.from_incoming(incoming)
        mail.subject = subject
        mail.body = body
        mail.provider_id = make_msgid()
        mail.current_status = MailStatus.PENDING.value
        mail.statuses.append(Status(status=MailStatus.PENDING.value))
        self.session.add(mail)
        try:
            self.session.commit()
        except SQLAlchemyError as error:
            self.session.rollback()
            raise MailDatabaseException("Could not queue email") from error
        return mail

    def get_mails(self) -> Sequence[Mail]:
        """Retourne les notifications enregistrées, de la plus récente à la plus ancienne.

        :returns: Séquence de notifications; une file vide produit une séquence vide.
        :rtype: collections.abc.Sequence[models.db.mails.Mail]
        :raises MailDatabaseException: Si la requête SQL échoue.
        """
        try:
            return self.session.execute(
                select(Mail).order_by(Mail.created_at.desc())
            ).scalars().all()
        except SQLAlchemyError as error:
            raise MailDatabaseException("Could not fetch emails") from error

    def get_mail_by_id(self, mail_id: str) -> Mail | None:
        """Recherche une notification par son identifiant de suivi.

        :param mail_id: Identifiant UUID de la notification.
        :type mail_id: str
        :returns: Enregistrement trouvé, ou ``None`` si l'identifiant est inconnu.
        :rtype: models.db.mails.Mail | None
        :raises MailDatabaseException: Si la consultation de la base échoue.
        """
        try:
            return self.session.get(Mail, mail_id)
        except SQLAlchemyError as error:
            raise MailDatabaseException("Could not fetch email") from error

    @staticmethod
    def public_status(mail: Mail) -> dict[str, str | int | None]:
        """Construit la représentation publique d'une notification.

        Les adresses, le corps et les valeurs du template ne sont jamais inclus dans
        cette représentation.

        :param mail: Notification dont l'état doit être exposé.
        :type mail: models.db.mails.Mail
        :returns: Dictionnaire comprenant ``id``, ``status``, ``retry_count``,
            ``sent_at``, ``imap_copied_at`` et ``error``.
        :rtype: dict[str, str | int | None]
        """
        return {
            "id": mail.id,
            "status": mail.current_status,
            "retry_count": mail.retry_count,
            "sent_at": mail.sent_at.isoformat() if mail.sent_at else None,
            "imap_copied_at": (
                mail.imap_copied_at.isoformat() if mail.imap_copied_at else None
            ),
            "error": mail.last_error,
        }

    def process_mail(self, mail_id: str) -> Mail:
        """Réserve puis traite une notification en attente.

        Une mise à jour conditionnelle évite que plusieurs workers ne revendiquent
        simultanément le même mail. En cas d'échec SMTP, le dépôt planifie un retry
        exponentiel jusqu'à la limite configurée, puis marque la notification
        ``failed``. Après succès SMTP, il efface les données de livraison avant de
        tenter la copie IMAP; un échec IMAP est enregistré sans nouvel envoi SMTP.

        :param mail_id: Identifiant UUID de la notification à traiter.
        :type mail_id: str
        :returns: Enregistrement avec son état après le traitement ou la tentative.
        :rtype: models.db.mails.Mail
        :raises MailNotFoundException: Si l'identifiant n'existe pas.
        :raises MailDatabaseException: Si une transition de statut ne peut pas être
            persistée.
        """
        mail = self.get_mail_by_id(mail_id)
        if mail is None:
            raise MailNotFoundException(f"Mail {mail_id} was not found")
        if mail.current_status != MailStatus.PENDING.value:
            return mail

        try:
            claim = self.session.execute(
                update(Mail)
                .where(
                    Mail.id == mail_id,
                    Mail.current_status == MailStatus.PENDING.value,
                )
                .values(current_status="sending", next_retry_at=None)
            )
            if claim.rowcount != 1:
                self.session.rollback()
                refreshed = self.session.get(Mail, mail_id)
                if refreshed is None:
                    raise MailNotFoundException(f"Mail {mail_id} was not found")
                return refreshed
            self.session.commit()
            self.session.refresh(mail)
        except SQLAlchemyError as error:
            self.session.rollback()
            raise MailDatabaseException("Could not claim queued email") from error

        client = MailClient(mail, self.config)
        message = client.create_message()
        try:
            refused_recipients = client.send(message)
            if refused_recipients:
                currently_pending = [
                    value.strip()
                    for value in mail.recipients.split(",")
                    if value.strip()
                ]
                accepted = [
                    value for value in currently_pending
                    if value not in refused_recipients
                ]
                delivered = [
                    value.strip()
                    for value in mail.delivered_recipients.split(",")
                    if value.strip()
                ]
                mail.delivered_recipients = ",".join(dict.fromkeys([*delivered, *accepted]))
                mail.recipients = ",".join(
                    value for value in currently_pending if value in refused_recipients
                )
                raise MailSendException(
                    f"SMTP refused {len(refused_recipients)} recipient(s)"
                )
        except MailSendException as error:
            mail.retry_count += 1
            if mail.retry_count <= self.config.retries:
                mail.current_status = MailStatus.PENDING.value
                mail.next_retry_at = _utc_now() + timedelta(
                    seconds=min(3600, 2 ** (mail.retry_count - 1))
                )
                status = MailStatus.PENDING.value
            else:
                mail.current_status = MailStatus.FAILED.value
                status = MailStatus.FAILED.value
            mail.last_error = str(error)[:255]
            mail.statuses.append(Status(status=status, comment=mail.last_error))
            try:
                self.session.commit()
            except SQLAlchemyError as database_error:
                self.session.rollback()
                raise MailDatabaseException("Could not record SMTP failure") from database_error
            return mail

        mail.current_status = MailStatus.SENT.value
        mail.sent_at = _utc_now()
        mail.recipients = ""
        mail.delivered_recipients = ""
        mail.body = None
        mail.jinja_values = ""
        mail.last_error = None
        mail.next_retry_at = None
        mail.statuses.append(Status(status=MailStatus.SENT.value))
        try:
            self.session.commit()
        except SQLAlchemyError as error:
            self.session.rollback()
            raise MailDatabaseException("SMTP accepted the message but status was not saved") from error

        try:
            copied = client.copy_to_sent(message)
        except MailSendException as error:
            mail.last_error = str(error)[:255]
            mail.statuses.append(
                Status(
                    status=MailStatus.SENT.value,
                    comment=f"IMAP copy failed: {error}"[:255],
                )
            )
            try:
                self.session.commit()
            except SQLAlchemyError as database_error:
                self.session.rollback()
                raise MailDatabaseException("Could not record IMAP copy failure") from database_error
            logger.error("Mail %s was sent but its IMAP copy failed: %s", mail.id, error)
        else:
            if copied:
                mail.imap_copied_at = _utc_now()
            try:
                self.session.commit()
            except SQLAlchemyError as error:
                self.session.rollback()
                raise MailDatabaseException("Could not record IMAP copy result") from error
        return mail

    def retry_failed_mail(self, mail_id: str) -> Mail:
        """Remet en file un échec terminal pour une nouvelle tentative manuelle.

        Le compteur de retries est réinitialisé et les destinataires conservés sont
        réutilisés. Un mail déjà en attente est retourné sans transition supplémentaire.

        :param mail_id: Identifiant UUID du mail à remettre en file.
        :type mail_id: str
        :returns: Enregistrement en état ``pending``.
        :rtype: models.db.mails.Mail
        :raises MailNotFoundException: Si l'identifiant n'existe pas.
        :raises MailRetryNotAllowedException: Si le mail n'est pas en état ``failed``
            ou si aucun destinataire n'est conservé.
        :raises MailDatabaseException: Si la nouvelle mise en file ne peut pas être
            enregistrée.
        """
        mail = self.get_mail_by_id(mail_id)
        if mail is None:
            raise MailNotFoundException(f"Mail {mail_id} was not found")
        if mail.current_status == MailStatus.PENDING.value:
            return mail
        if mail.current_status != MailStatus.FAILED.value or not mail.recipients:
            raise MailRetryNotAllowedException(
                "Only a failed email with retained recipients can be retried"
            )

        mail.current_status = MailStatus.PENDING.value
        mail.retry_count = 0
        mail.next_retry_at = None
        mail.last_error = None
        mail.statuses.append(
            Status(
                status=MailStatus.PENDING.value,
                comment="Manually requeued after delivery failure",
            )
        )
        try:
            self.session.commit()
        except SQLAlchemyError as error:
            self.session.rollback()
            raise MailDatabaseException("Could not requeue failed email") from error
        return mail

    def process_due_mails(self, limit: int = 25) -> int:
        """Traite un lot de notifications en attente dont l'échéance est atteinte.

        :param limit: Nombre maximal d'identifiants à prendre dans la file pour ce lot.
        :type limit: int
        :returns: Nombre de notifications prises en charge dans le lot.
        :rtype: int
        :raises MailDatabaseException: Si la lecture de la file échoue. Les erreurs de
            livraison individuelles sont enregistrées par :meth:`process_mail`.
        """
        now = _utc_now()
        try:
            mail_ids = self.session.execute(
                select(Mail.id)
                .where(
                    Mail.current_status == MailStatus.PENDING.value,
                    or_(Mail.next_retry_at.is_(None), Mail.next_retry_at <= now),
                )
                .order_by(Mail.created_at)
                .limit(limit)
            ).scalars().all()
        except SQLAlchemyError as error:
            raise MailDatabaseException("Could not read the delivery queue") from error

        for mail_id in mail_ids:
            self.process_mail(mail_id)
        return len(mail_ids)

    def reconcile_interrupted_mails(self) -> int:
        """Remet en attente les livraisons restées en état ``sending`` au redémarrage.

        SMTP et SQLite ne partagent pas de transaction; une tentative interrompue peut
        donc avoir été acceptée par le serveur avant que son succès soit persisté. Le
        mail est remis en file et cette ambiguïté est inscrite dans son erreur de suivi.

        :returns: Nombre de notifications réconciliées.
        :rtype: int
        :raises MailDatabaseException: Si la lecture ou la mise à jour de la file échoue.
        """
        try:
            interrupted = self.session.execute(
                select(Mail).where(Mail.current_status == "sending")
            ).scalars().all()
            for mail in interrupted:
                mail.current_status = MailStatus.PENDING.value
                mail.next_retry_at = None
                mail.last_error = (
                    "Recovered an interrupted SMTP attempt; delivery may be duplicated"
                )
                mail.statuses.append(
                    Status(
                        status=MailStatus.PENDING.value,
                        comment=mail.last_error,
                    )
                )
            self.session.commit()
            return len(interrupted)
        except SQLAlchemyError as error:
            self.session.rollback()
            raise MailDatabaseException("Could not reconcile interrupted emails") from error
