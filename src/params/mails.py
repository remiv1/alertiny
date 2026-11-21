"""Paramètres des mails pour l'application Alertiny.

..constantes::
    - `CONFIG_PATH` : Chemin vers le fichier de configuration principal.
    - `LOCAL_CONFIG_PATH` : Chemin vers le fichier de configuration local.

.. fonctions::
    - `load_mail_config` : Charge les paramètres des mails depuis le fichier YAML.

.. classes::
    - `SMTPConfig` : Paramètres du serveur SMTP.
    - `IMAPConfig` : Paramètres du serveur IMAP.
    - `MailConfig` : Configuration complète des mails.

.. responsabilité : configuration

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path("/etc/alertiny/config.yaml")
LOCAL_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "config.yaml"


@dataclass(frozen=True)
class SMTPConfig:
    """Paramètres du serveur SMTP.

    :param server: Adresse du serveur SMTP.
    :type server: str
    :param port: Port du serveur SMTP.
    :type port: int
    :param tls: Indique si TLS est utilisé.
    :type tls: bool
    :param starttls: Indique si STARTTLS est utilisé.
    :type starttls: bool
    """

    server: str
    port: int
    tls: bool
    starttls: bool


@dataclass(frozen=True)
class IMAPConfig:
    """Paramètres du serveur IMAP.

    :param copy_to_sent: Indique si les mails doivent être copiés dans le dossier "Sent".
    :type copy_to_sent: bool
    :param server: Adresse du serveur IMAP.
    :type server: str
    :param port: Port du serveur IMAP.
    :type port: int
    :param tls: Indique si TLS est utilisé.
    :type tls: bool
    :param starttls: Indique si STARTTLS est utilisé.
    :type starttls: bool
    :param folder: Dossier IMAP à utiliser.
    :type folder: str
    """

    copy_to_sent: bool
    server: str
    port: int
    tls: bool
    starttls: bool
    folder: str


@dataclass(frozen=True)
class MailConfig:
    """Configuration complète des mails.

    :param sender: Adresse e-mail de l'expéditeur.
    :type sender: str
    :param smtp: Configuration du serveur SMTP.
    :type smtp: SMTPConfig
    :param retries: Nombre de tentatives en cas d'échec d'envoi.
    :type retries: int
    :param imap: Configuration du serveur IMAP.
    :type imap: IMAPConfig
    """

    sender: str
    smtp: SMTPConfig
    retries: int
    imap: IMAPConfig


def load_mail_config(path: Path | None = None) -> MailConfig:
    """Charge les paramètres des mails depuis le fichier YAML.

    :param path: Chemin vers le fichier de configuration YAML.
    :type path: Path | None

    :return: Configuration complète des mails.
    :rtype: MailConfig
    """
    if path is None:
        path = CONFIG_PATH if CONFIG_PATH.exists() else LOCAL_CONFIG_PATH

    with path.open("r", encoding="utf-8") as config_file:
        data: dict[str, Any] = yaml.safe_load(config_file)["mail"]

    return MailConfig(
        sender=data["from"],
        smtp=SMTPConfig(**data["smtp"]),
        retries=data["retries"],
        imap=IMAPConfig(**data["imap"]),
    )
