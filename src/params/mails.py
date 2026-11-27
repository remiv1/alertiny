"""Chargement et définition typée de la configuration SMTP et IMAP.

La configuration principale est lue depuis ``/etc/alertiny/config.yaml`` dans le
conteneur, avec un repli vers ``src/config/config.yaml`` en développement local. Les
identifiants ne sont pas lus depuis le YAML : SMTP utilise ``SMTP_USERNAME`` et
``SMTP_PASSWORD``; IMAP réutilise ces variables par défaut et peut les remplacer avec
``IMAP_USERNAME`` et ``IMAP_PASSWORD``. La copie des messages envoyés dans IMAP est
obligatoire en V1.

.. classes::
    - :class:`SMTPConfig` : paramètres du transport SMTP.
    - :class:`IMAPConfig` : paramètres du transport et du dossier IMAP.
    - :class:`MailConfig` : configuration complète des e-mails.

.. functions::
    - :func:`load_mail_config` : charge, combine et valide les paramètres.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from dataclasses import dataclass
from email.errors import HeaderParseError
from email.headerregistry import Address
from pathlib import Path
from typing import Any
import os

import yaml

CONFIG_PATH = Path("/etc/alertiny/config.yaml")
LOCAL_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "config.yaml"


def _validate_tls_config(protocol: str, tls: bool, starttls: bool) -> None:
    if (
        not isinstance(tls, bool) # type: ignore
        or not isinstance(starttls, bool) # type: ignore
        or tls == starttls
    ):
        raise ValueError(f"{protocol} must enable exactly one of tls or starttls")


@dataclass(frozen=True)
class SMTPConfig:
    """Paramètres nécessaires à la connexion SMTP.

    :param server: Nom d'hôte ou adresse du serveur SMTP.
    :type server: str
    :param port: Port TCP du serveur SMTP.
    :type port: int
    :param tls: Active TLS implicite, généralement pour le port 465.
    :type tls: bool
    :param starttls: Négocie STARTTLS lorsque TLS implicite est désactivé.
    :type starttls: bool
    :param username: Nom d'utilisateur d'authentification; ``None`` désactive LOGIN.
    :type username: str | None
    :param password: Mot de passe associé; ``None`` désactive LOGIN.
    :type password: str | None
    """

    server: str
    port: int
    tls: bool
    starttls: bool
    username: str | None = None
    password: str | None = None

    def __post_init__(self) -> None:
        _validate_tls_config("SMTP", self.tls, self.starttls)


@dataclass(frozen=True)
class IMAPConfig:       # pylint: disable=R0902
    """Paramètres de connexion et d'archivage IMAP.

    :param copy_to_sent: Doit être vrai en V1 afin d'archiver chaque envoi SMTP réussi.
    :type copy_to_sent: bool
    :param server: Nom d'hôte ou adresse du serveur IMAP.
    :type server: str
    :param port: Port TCP du serveur IMAP.
    :type port: int
    :param tls: Active TLS implicite.
    :type tls: bool
    :param starttls: Négocie STARTTLS lorsque TLS implicite est désactivé.
    :type starttls: bool
    :param folder: Nom du dossier dans lequel le message envoyé est ajouté.
    :type folder: str
    :param username: Identifiant IMAP facultatif; à défaut, celui de SMTP est réutilisé.
    :type username: str | None
    :param password: Mot de passe IMAP facultatif; à défaut, celui de SMTP est réutilisé.
    :type password: str | None
    """

    copy_to_sent: bool
    server: str
    port: int
    tls: bool
    starttls: bool
    folder: str
    username: str | None = None
    password: str | None = None

    def __post_init__(self) -> None:
        _validate_tls_config("IMAP", self.tls, self.starttls)


@dataclass(frozen=True)
class MailConfig:
    """Configuration complète utilisée lors du traitement des e-mails.

    :param sender: Adresse d'expédition configurée pour l'en-tête et l'enveloppe SMTP.
    :type sender: str
    :param smtp: Paramètres de connexion SMTP.
    :type smtp: SMTPConfig
    :param retries: Nombre de tentatives supplémentaires après le premier essai.
    :type retries: int
    :param imap: Paramètres de connexion et de copie IMAP.
    :type imap: IMAPConfig
    """

    sender: str
    smtp: SMTPConfig
    retries: int
    imap: IMAPConfig


def load_mail_config(path: Path | None = None) -> MailConfig:
    """Charge les paramètres YAML et les identifiants depuis l'environnement.

    Si ``path`` n'est pas fourni, le fichier de configuration du conteneur est choisi
    lorsqu'il existe; sinon, le fichier de configuration local du dépôt est utilisé.
    Le nom d'utilisateur et le mot de passe de chaque protocole doivent être fournis
    ensemble. La configuration refuse également de désactiver la copie IMAP en V1.

    :param path: Chemin explicite vers ``config.yaml``; ``None`` sélectionne le chemin
        approprié à l'environnement d'exécution.
    :type path: pathlib.Path | None
    :returns: Configuration validée des transports mail.
    :rtype: MailConfig
    :raises OSError: Si le fichier YAML ne peut pas être ouvert.
    :raises KeyError: Si une clé obligatoire manque dans le YAML.
    :raises ValueError: Si les identifiants, l'adresse d'expédition ou la configuration
        de copie IMAP ne respectent pas les règles de la V1.
    :raises yaml.YAMLError: Si le document YAML est mal formé.
    """
    if path is None:
        path = CONFIG_PATH if CONFIG_PATH.exists() else LOCAL_CONFIG_PATH

    with path.open("r", encoding="utf-8") as config_file:
        data: dict[str, Any] = yaml.safe_load(config_file)["mail"]

    try:
        Address(addr_spec=data["from"])
    except (HeaderParseError, ValueError) as error:
        raise ValueError("mail.from must be a valid email address") from error
    if not data["imap"]["copy_to_sent"]:
        raise ValueError("IMAP sent-message copying must be enabled in v1")

    smtp_data = dict(data["smtp"])
    smtp_data["username"] = os.getenv("SMTP_USERNAME")
    smtp_data["password"] = os.getenv("SMTP_PASSWORD")
    imap_data = dict(data["imap"])
    imap_data["username"] = os.getenv("IMAP_USERNAME", smtp_data["username"])
    imap_data["password"] = os.getenv("IMAP_PASSWORD", smtp_data["password"])
    if bool(smtp_data["username"]) != bool(smtp_data["password"]):
        raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
    if bool(imap_data["username"]) != bool(imap_data["password"]):
        raise ValueError("IMAP_USERNAME and IMAP_PASSWORD must be configured together")

    return MailConfig(
        sender=data["from"],
        smtp=SMTPConfig(**smtp_data),
        retries=data["retries"],
        imap=IMAPConfig(**imap_data),
    )
