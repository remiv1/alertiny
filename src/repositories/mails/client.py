"""Client pour la gestion des mails avec SMTP et IMAP.

Ce module fournit la classe `MailClient` qui permet de préparer, envoyer et copier des mails
dans les éléments envoyés en utilisant les protocoles SMTP et IMAP.


.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import ssl
from logging import getLogger

from email.message import EmailMessage
from smtplib import SMTP, SMTPException, SMTP_SSL
from imaplib import IMAP4, IMAP4_SSL, Time2Internaldate
import time

from params.mails import MailConfig
from models.db.mails import Mail
from exc.mails import MailSendException

logger = getLogger(__name__)

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
        except (SMTPException, OSError) as error:
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
        except (IMAP4.error, OSError) as error:
            raise MailSendException(f"IMAP copy failed: {error}") from error
        finally:
            if client is not None:
                try:
                    client.logout()
                except (IMAP4.error, OSError):
                    logger.warning("IMAP logout failed after the copy attempt")
