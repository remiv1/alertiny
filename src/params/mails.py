"""Paramètres des mails pour l'application Alertiny.

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
    """Paramètres du serveur SMTP."""

    server: str
    port: int
    tls: bool
    starttls: bool


@dataclass(frozen=True)
class IMAPConfig:
    """Paramètres du serveur IMAP."""

    copy_to_sent: bool
    server: str
    port: int
    tls: bool
    starttls: bool
    folder: str


@dataclass(frozen=True)
class MailConfig:
    """Configuration complète des mails."""

    sender: str
    smtp: SMTPConfig
    retries: int
    imap: IMAPConfig


def load_mail_config(path: Path | None = None) -> MailConfig:
    """Charge les paramètres des mails depuis le fichier YAML."""
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
