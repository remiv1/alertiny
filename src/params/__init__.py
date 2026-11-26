"""Module de gestion des paramètres dans l'application Alertiny.

.. values::
    - `engine`: Objet de connexion à la base de données.
    - `session`: Session de base de données.

.. functions::
    - `load_mail_config`: Charge la configuration des mails depuis le fichier YAML.
    - `load_templates_config`: Charge la configuration des templates depuis le fichier YAML.
    - `get_session`: Fonction pour obtenir une session de base de données.

.. classes::
    - `SessionDep`: Dépendance pour la session de l'application.
    - `SMTPConfig`: Configuration SMTP pour l'envoi des mails.
    - `IMAPConfig`: Configuration IMAP pour la réception des mails.
    - `MailConfig`: Configuration globale des mails.
    - `TemplatesConfig`: Configuration des templates.

.. responsibility : configuration

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from .application import SessionDep
from .database import engine, session, get_session
from .mails import SMTPConfig, IMAPConfig, MailConfig, load_mail_config
from .templates import TemplatesConfig, load_templates_config

__all__ = [
    "SessionDep",
    "engine",
    "session",
    "get_session",
    "SMTPConfig",
    "IMAPConfig",
    "MailConfig",
    "load_mail_config",
    "TemplatesConfig",
    "load_templates_config",
]
