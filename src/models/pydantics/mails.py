"""Schémas Pydantic des requêtes de notification et de leurs variables.

Les modèles de ce module définissent la validation effectuée à l'entrée de l'API.
Une requête de mail doit contenir au moins un destinataire et un expéditeur valide;
les pièces jointes sont refusées en V1. Le sujet est facultatif : lorsqu'il n'est pas
fourni, celui déclaré dans la configuration du template est rendu.

.. classes::
    - :class:`Recipient` : adresse d'un destinataire.
    - :class:`JinjaValues` : valeur fournie à un template.
    - :class:`MailIncoming` : corps validé d'une requête de création de mail.

.. classes::
    - `Recipient`: Modèle pour les destinataires.
    - `JinjaValues`: Modèle pour les valeurs Jinja.
    - `MailIncoming`: Modèle pour les mails entrants.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from email.errors import HeaderParseError
from email.headerregistry import Address

from pydantic import BaseModel, Field, field_validator

class Recipient(BaseModel):
    """Adresse e-mail d'un destinataire de la notification.

    :param email: Adresse SMTP du destinataire. La valeur est validée avant d'être
        utilisée dans les en-têtes et l'enveloppe SMTP.
    :type email: str
    """
    email: str

    @field_validator("email")
    @classmethod
    def validate_email_address(cls, value: str) -> str:
        """Valide la syntaxe de l'adresse avec le parseur d'en-têtes standard.

        :param value: Adresse fournie par le client HTTP.
        :type value: str
        :returns: Adresse inchangée si sa syntaxe est valide.
        :rtype: str
        :raises ValueError: Si la valeur n'est pas une adresse exploitable.
        """
        try:
            Address(addr_spec=value)
        except (HeaderParseError, ValueError) as error:
            raise ValueError("A valid email address is required") from error
        return value

class JinjaValues(BaseModel):
    """Paire clé-valeur utilisée lors du rendu du template Jinja.

    :param key: Nom de la variable référencée dans le template.
    :type key: str
    :param value: Valeur textuelle associée à la variable.
    :type value: str
    """
    key: str
    value: str

class MailIncoming(BaseModel):
    """Schéma validé d'une requête de création de notification.

    ``template`` doit correspondre au nom ou au nom de fichier d'un modèle déclaré
    dans ``templates.yaml``. Les variables Jinja requises par ce modèle sont vérifiées
    avant la mise en file. Le sujet facultatif remplace le sujet du modèle comme texte
    littéral; il n'est pas interprété comme du code Jinja.

    :param sender: Adresse d'expédition fournie par le client. Le serveur utilise
        toutefois l'adresse ``mail.from`` de sa configuration SMTP.
    :type sender: str
    :param subject: Sujet littéral facultatif. En son absence, le sujet configuré pour
        le template est rendu à partir des variables fournies.
    :type subject: str | None
    :param template: Nom logique ou nom de fichier du template autorisé.
    :type template: str
    :param jinja_values: Variables utilisées pour rendre le sujet configuré et le corps.
    :type jinja_values: list[JinjaValues]
    :param attachments: Doit être une liste vide en V1; sa valeur par défaut est vide.
    :type attachments: list[str]
    :param recipient: Liste non vide des destinataires SMTP.
    :type recipient: list[Recipient]
    """
    sender: str
    subject: str | None = None
    template: str
    jinja_values: list[JinjaValues]
    attachments: list[str] = Field(default_factory=list)
    recipient: list[Recipient]

    @field_validator("sender")
    @classmethod
    def validate_sender_address(cls, value: str) -> str:
        """Valide l'adresse expéditeur transmise dans la requête.

        :param value: Adresse expéditeur fournie par le client.
        :type value: str
        :returns: Adresse inchangée si sa syntaxe est valide.
        :rtype: str
        :raises ValueError: Si la valeur n'est pas une adresse exploitable.
        """
        try:
            Address(addr_spec=value)
        except (HeaderParseError, ValueError) as error:
            raise ValueError("A valid sender email address is required") from error
        return value

    @field_validator("subject")
    @classmethod
    def reject_subject_newlines(cls, value: str | None) -> str | None:
        """Refuse les retours à la ligne dans un sujet littéral.

        :param value: Sujet facultatif fourni par le client.
        :type value: str | None
        :returns: Sujet inchangé, ou ``None`` lorsque le modèle fournit le sujet.
        :rtype: str | None
        :raises ValueError: Si le sujet contient CR ou LF.
        """
        if value is not None and ("\r" in value or "\n" in value):
            raise ValueError("Email subject must not contain line breaks")
        return value

    @field_validator("attachments")
    @classmethod
    def reject_attachments_in_v1(cls, value: list[str]) -> list[str]:
        """Garantit que la requête ne contient aucune pièce jointe.

        :param value: Liste de pièces jointes transmise par le client.
        :type value: list[str]
        :returns: Liste vide.
        :rtype: list[str]
        :raises ValueError: Si une pièce jointe est fournie.
        """
        if value:
            raise ValueError("Attachments are not supported in v1")
        return value

    @field_validator("recipient")
    @classmethod
    def require_recipients(cls, value: list[Recipient]) -> list[Recipient]:
        """Refuse les notifications sans destinataire.

        :param value: Destinataires validés de la requête.
        :type value: list[Recipient]
        :returns: Liste non vide de destinataires.
        :rtype: list[Recipient]
        :raises ValueError: Si la liste est vide.
        """
        if not value:
            raise ValueError("At least one recipient is required")
        return value
