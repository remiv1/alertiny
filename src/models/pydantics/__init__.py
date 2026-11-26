"""Modèles Pydantic pour l'application Alertiny.

.. classes::
    - `JinjaValues`: Modèle pour les valeurs Jinja.
    - `MailIncoming`: Modèle pour les mails entrants.
    - `Recipient`: Modèle pour les destinataires.
    - `TemplatesConfig`: Configuration des templates.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from .mails import JinjaValues, MailIncoming, Recipient
from .templates import TemplatesConfig

__all__ = [
    "TemplatesConfig",
    "JinjaValues",
    "MailIncoming",
    "Recipient",
]
