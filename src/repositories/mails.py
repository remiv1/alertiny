"""Module de gestion des mails dans le dépôt Alertiny.

.. classes::
    - `MailClient` : Client pour l'envoi des mails.
    - `MailsRepository` : Dépôt pour la gestion des mails.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import Sequence, Any, Optional, overload, Literal, cast
from email.message import Message
from email.utils import make_msgid
from smtplib import SMTP, SMTPException, SMTP_SSL
from imaplib import IMAP4, Time2Internaldate
import time

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from jinja2 import Template
from jinja2.exceptions import TemplateError

from params.application import SessionDep
from params.mails import MailConfig, load_mail_config
from models.db.mails import Mail
from models.pydantics.mails import MailIncoming, JinjaValues

from ..exc.mails import (
    MailDatabaseException,
    MailCompileException,
    MailSendException,
)

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
        self.email_message = Message()
        self.email_message["From"] = self.config.sender
        self.email_message["To"] = self.mail.recipients
        self.email_message["Subject"] = self.mail.subject
        self.email_message["Message-ID"] = make_msgid(domain=self.mail.sender.split("@")[-1])
        return self

    def send(self) -> None:
        """Envoie un mail."""
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
            raise RuntimeError("Failed to send email") from e

    def copy(self) -> bool:
        """Vérifie si un mail a déjà été copié dans les éléments envoyés."""
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


class MailsRepository:
    """Dépôt pour la gestion des mails. Ce dépôt encapsule la logique d'accès aux données des mails
    et fournit les méthodes pour interagir avec ces données.

    .. methodes::
        - `get_mails` : Retourne la liste des mails ou None si aucun mail n'est trouvé.
        - `get_mail_by_id` : Retourne un mail correspondant à l'identifiant fourni ou None si aucun
        mail n'est trouvé.
        - `get_mail_by` : Retourne un mail correspondant à l'attribut et à la valeur fournis ou None
        si aucun mail n'est trouvé.
        - `create_mail` : Crée un nouveau mail à partir des données fournies. et l'envoie.
        - `generate_mail` : Génère le contenu d'un mail à partir des données fournies et l'ajoute à
        la base de données.
        - `send_mail` : Envoie un mail existant.
    
    .. responsabilité : métier
    .. auteur:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. from_version:: initial
    """
    def __init__(self, session: SessionDep) -> None:
        self.session = session
        self.config = load_mail_config()
        self.mail: Mail | None = None
        self.client: MailClient | None = None

    def _sender(self, *, mail: Mail) -> None:
        """Envoie un mail en interne."""
        MailClient(mail, self.config).send()

    def _compile(self) -> Any:
        """Compile le contenu du mail actuel."""
        if not self.mail:
            raise ValueError("No mail is currently set for compilation.")
        try:
            template = Template(self.mail.template)
            compiled_mail = template.render(
                **{j.key: j.value for j in cast(list[JinjaValues], self.mail.jinja_values)}
            )
            return compiled_mail
        except TemplateError as e:
            raise MailCompileException("Error occurred while compiling mail") from e

    def get_mails(self) -> Optional[Sequence[Mail]]:
        """Récupère la liste des mails."""
        stmt = select(Mail)
        try:
            mails = self.session.execute(stmt)
            result = mails.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise MailDatabaseException("Error occurred while fetching mails") from e
        return result

    @overload
    def get_mail_by_id(self, mail_id: str, chaine:Literal[True]) -> "MailsRepository": ...
    @overload
    def get_mail_by_id(self, mail_id: str, chaine: Literal[False]) -> "MailsRepository":...
    def get_mail_by_id(self, mail_id: str, chaine: bool = False) -> "MailsRepository | Mail | None":
        """Récupère un mail par son identifiant."""
        stmt = select(Mail).where(Mail.id == mail_id)
        result = self.session.execute(stmt).scalar_one_or_none()
        if chaine:
            self.mail = result
            return self
        return result

    @overload
    def get_mail_by(self, attribut: str, *, value: Any, chaine: Literal[True]) -> "MailsRepository":
        ...
    @overload
    def get_mail_by(self, attribut: str, *, value: Any, chaine: Literal[False]) -> Mail | None:
        ...
    def get_mail_by(
        self,
        attribut: str,
        *,
        value: Any,
        chaine: bool = False,
    ) -> "MailsRepository | Mail | None":
        """Récupère un mail par un attribut spécifique."""
        stmt = select(Mail).where(getattr(Mail, attribut) == value)
        result = self.session.execute(stmt).scalar_one_or_none()
        if chaine:
            self.mail = result
            return self
        return result

    def send_new_mail(self, *, mail: MailIncoming) -> Mail:
        """Crée un nouveau mail."""
        # TODO gérer les exceptions et retourner un message personnalisé.
        mail = Mail.from_incoming(mail)
        self.session.add(mail)
        self.session.commit()
        self._sender(mail=mail)
        return mail

    def generate_mail(self, *, mail: MailIncoming) -> str:
        """Génère un mail et l'ajoute à la base de données et retourne le contenu généré."""
        mail_instance = Mail.from_incoming(mail)
        self.session.add(mail_instance)
        try:
            self.session.commit()
        except SQLAlchemyError as e:
            raise MailDatabaseException(
                "Error occurred while sending mail params in database"
            ) from e
        self.mail = mail_instance
        return self._compile()

    def send_mail(self) -> None:
        """Envoie un mail."""
        if not self.mail:
            raise MailSendException("Pour générer et envoyer, utilisez la méthode send_new_mail")
        self._compile()
        self._sender(mail=self.mail)
