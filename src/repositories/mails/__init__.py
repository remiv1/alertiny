"""Module de gestion des mails dans le dépôt Alertiny.

.. classes::
    - `MailClient` : Client pour l'envoi des mails.
    - `MailsRepository` : Dépôt pour la gestion des mails.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from .repo import MailClient, MailsRepository

__all__ = [
    "MailClient",
    "MailsRepository",
]
