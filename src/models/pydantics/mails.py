"""Modèles Pydantic pour les mails.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from pydantic import BaseModel

class Recipient(BaseModel):
    """Modèle représentant un destinataire de mail.
    
    :param email: L'adresse e-mail du destinataire.
    :type email: str
    """
    email: str

class JinjaValues(BaseModel):
    """Modèle représentant une paire clé-valeur pour Jinja.

    :param key: La clé Jinja.
    :type key: str
    :param value: La valeur associée à la clé.
    :type value: str
    """
    key: str
    value: str

class MailIncoming(BaseModel):
    """Modèle représentant un mail entrant.

    :param sender: L'adresse e-mail de l'expéditeur.
    :type sender: str
    :param subject: L'objet du mail.
    :type subject: str
    :param template: Le template Jinja utilisé pour le mail.
    :type template: str
    :param jinja_values: Les valeurs Jinja associées au template.
    :type jinja_values: list[model.pydantics.mails.JinjaValues]
    :param attachments: Les pièces jointes du mail.
    :type attachments: list[str]
    :param recipient: Les destinataires du mail.
    :type recipient: list[model.pydantics.mails.Recipient]
    """
    sender: str
    subject: str
    template: str
    jinja_values: list[JinjaValues]
    attachments: list[str]
    recipient: list[Recipient]
