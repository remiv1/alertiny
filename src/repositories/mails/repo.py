"""Dépôt pour la gestion des mails.

Ce module fournit la classe `MailsRepository` qui encapsule la logique d'accès aux données des mails
et fournit les méthodes pour interagir avec ces données.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import Any, Sequence, overload, Literal, cast, Optional

from jinja2 import Template
from jinja2.exceptions import TemplateError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from models.db.mails import Mail
from models.pydantics.mails import MailIncoming, JinjaValues
from params.application import SessionDep
from params.mails import load_mail_config
from repositories.mails.client import MailClient
from exc.mails import (
    MailDatabaseException,
    MailCompileException,
)

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
        """Envoie un mail en interne.
        
        :param mail: Le mail à envoyer.
        :type mail: alertiny.models.db.mails.Mail

        :raises MailSendException: Si l'envoi du mail échoue.
        :raises ValueError: Si le mail n'est pas défini.
        """
        MailClient(mail, self.config).send()

    def _compile(self) -> Any:
        """Compile le contenu du mail actuel.

        :raises MailCompileException: Si la compilation du mail échoue.
        :raises ValueError: Si aucun mail n'est défini.
        """
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
        """Récupère la liste des mails.

        :return: La liste des mails ou None si aucun mail n'est trouvé.
        :rtype: Optional[Sequence[alertiny.models.db.mails.Mail]]

        :raises MailDatabaseException: Si la récupération des mails échoue.
        """
        stmt = select(Mail)
        try:
            mails = self.session.execute(stmt)
            result = mails.scalars().all()
        except SQLAlchemyError as e:
            raise MailDatabaseException("Error occurred while fetching mails") from e
        return result

    @overload
    def get_mail_by_id(self, mail_id: str, chaine:Literal[True]) -> "MailsRepository": ...
    @overload
    def get_mail_by_id(self, mail_id: str, chaine: Literal[False]) -> "MailsRepository":...
    def get_mail_by_id(self, mail_id: str, chaine: bool = False) -> "MailsRepository | Mail | None":
        """Récupère un mail par son identifiant.
        
        :param mail_id: L'identifiant du mail à récupérer.
        :type mail_id: str
        :param chaine: Indique si le résultat doit être stocké dans l'attribut `mail` de la classe.
        :type chaine: bool

        :return: L'objet Mail correspondant ou la chaîne de l'objet MailsRepository si
        `chaine` est True.
        :rtype: alertiny.models.db.mails.Mail | MailsRepository | None

        :raises MailDatabaseException: Si la récupération du mail échoue.
        """
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
        """Récupère un mail par un attribut spécifique.
        
        :param attribut: Le nom de l'attribut à utiliser pour la recherche.
        :type attribut: str
        :param value: La valeur de l'attribut à rechercher.
        :type value: Any
        :param chaine: Indique si le résultat doit être stocké dans l'attribut `mail` de la classe.
        :type chaine: bool

        :return: L'objet Mail correspondant ou la chaîne de l'objet MailsRepository si
        `chaine` est True.
        :rtype: alertiny.models.db.mails.Mail | MailsRepository | None

        :raises MailDatabaseException: Si la récupération du mail échoue.
        """
        stmt = select(Mail).where(getattr(Mail, attribut) == value)
        result = self.session.execute(stmt).scalar_one_or_none()
        if chaine:
            self.mail = result
            return self
        return result

    def send_new_mail(self, *, mail: MailIncoming) -> Mail:
        """Crée un nouveau mail.

        :param mail: Objet MailIncoming contenant les informations du mail à créer.
        :type mail: alertiny.models.db.mails.MailIncoming

        :return: L'objet Mail créé.
        :rtype: alertiny.models.db.mails.Mail

        :raises MailDatabaseException: Si la création du mail échoue.
        """
        mail = Mail.from_incoming(mail)
        self.session.add(mail)
        try:
            self.session.commit()
        except SQLAlchemyError as e:
            raise MailDatabaseException("Error occurred while creating new mail in database") from e
        self._sender(mail=mail)
        return mail

    def generate_mail(self, *, mail: MailIncoming) -> str:
        """Génère un mail et l'ajoute à la base de données et retourne le contenu généré.

        :param mail: Objet MailIncoming contenant les informations du mail à générer.
        :type mail: alertiny.models.db.mails.MailIncoming

        :return: Le contenu généré du mail.
        :rtype: str

        :raises MailDatabaseException: Si l'ajout du mail à la base de données échoue.
        """
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
        """Envoie un mail.

        :raises MailSendException: Si aucun mail n'a été généré avant l'envoi.
        :raises MailCompileException: Si la compilation du mail échoue.
        :raises ValueError: Si le mail n'est pas valide pour l'envoi.
        """
        if not self.mail:
            raise ValueError("Pour générer et envoyer, utilisez la méthode send_new_mail")
        self._compile()
        self._sender(mail=self.mail)
