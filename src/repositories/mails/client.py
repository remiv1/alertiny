"""Client pour la gestion des mails avec SMTP et IMAP.

Ce module fournit la classe `MailClient` qui permet de préparer, envoyer et copier des mails
dans les éléments envoyés en utilisant les protocoles SMTP et IMAP.


.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import Optional
from email.message import Message
from email.utils import make_msgid
from smtplib import SMTP, SMTPException, SMTP_SSL
from imaplib import IMAP4, Time2Internaldate
import time

from params.mails import MailConfig, load_mail_config
from models.db.mails import Mail
from exc.mails import MailSendException

class MailClient:
    """Client pour la préparation des objets mails, leur envoi et la copie dans les éléments
    envoyés avec les librairies smtp et imap.
    
    :param mail: Objet Mail contenant les informations du mail à envoyer.
    :type mail: alertiny.models.db.mails.Mail
    :param config: Configuration du client mail.
    :type config: alertiny.params.mails.MailConfig

    .. attributs::
        - `config` (MailConfig): Configuration du client mail.
        - `mail` (Mail): Objet Mail contenant les informations du mail à envoyer.
        - `email_message` (Message | None): Objet Message représentant le mail à envoyer.
        - `smtp` (SMTP | None): Client SMTP pour l'envoi des mails.
        - `imap` (IMAP4 | None): Client IMAP pour la gestion des éléments envoyés.
        - `timeout` (float): Délai d'attente pour les connexions SMTP.
    """

    def __init__(self, mail: Mail, config: Optional[MailConfig]) -> None:
        if config is None:
            self.config = load_mail_config()
        else:
            self.config = config
        self.mail: Mail = mail
        self.email_message: Message | None = None
        self.smtp: SMTP | None = None
        self.imap: IMAP4 | None = None
        self.timeout: float = 30.0

    def _create_mail(self) -> "MailClient":
        """Helper pour créer l'objet mail à envoyer.

        :return: L'instance du client mail avec l'objet mail créé.
        :rtype: MailClient
        """
        self.email_message = Message()
        self.email_message["From"] = self.config.sender
        self.email_message["To"] = self.mail.recipients
        self.email_message["Subject"] = self.mail.subject
        self.email_message["Message-ID"] = make_msgid(domain=self.mail.sender.split("@")[-1])
        return self

    def send(self) -> None:
        """Envoie un mail.

        :raises MailSendException: Si l'envoi du mail échoue.
        :raises ValueError: Si le mail n'a pas été créé.
        """
        self._create_mail()
        if not self.email_message:
            raise ValueError("Email message has not been created.")
        if self.config.smtp.tls:
            smtp: SMTP = SMTP_SSL(
                self.config.smtp.server,
                self.config.smtp.port,
                timeout=self.timeout,
            )
        else:
            smtp = SMTP(
                self.config.smtp.server,
                self.config.smtp.port,
                timeout=self.timeout,
            )
        self.smtp = smtp
        try:
            with smtp as server:
                if self.config.smtp.starttls and not self.config.smtp.tls:
                    server.starttls()
                server.send_message(self.email_message)
        except SMTPException as e:
            raise MailSendException("Failed to send email") from e

    def copy(self) -> bool:
        """Vérifie si un mail a déjà été copié dans les éléments envoyés.

        :return: True si le mail a été copié avec succès, False sinon.
        :rtype: bool

        :raises RuntimeError: Si le client IMAP n'a pas été initialisé.
        :raises ValueError: Si le message email n'a pas été créé.
        """
        if self.imap is None:
            raise RuntimeError("IMAP client has not been initialized.")
        if self.email_message is None:
            raise ValueError("Email message has not been created.")
        try:
            self.imap.append(
                "Sent",
                "",
                Time2Internaldate(time.time()),
                self.email_message.as_bytes()
            )
            return True
        except IMAP4.error:
            return False
