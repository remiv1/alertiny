"""Modélisation des données liées aux mails

.. module_author:: Rémi Verschuur rverschuur@audit-io.fr
.. version:: 1.0.0
"""
from __future__ import annotations

from datetime import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, Text, text
from sqlalchemy.orm import mapped_column, Mapped, relationship

from ._common import Mixins
from ..pydantics.mails import MailIncoming

if TYPE_CHECKING:
    from .status import Status

class Mail(Mixins):
    """Modèle représentant un mail dans la base de données.

    :param id: Identifiant UUID du mail.
    :type id: str
    :param sender: Expéditeur du mail.
    :type sender: str
    :param recipients: Destinataires dont la livraison SMTP reste à effectuer.
    :type recipients: str
    :param delivered_recipients: Destinataires déjà acceptés lors d'un envoi partiel.
    :type delivered_recipients: str
    :param subject: Sujet du mail.
    :type subject: str
    :param template: Nom du template utilisé pour le rendu.
    :type template: str
    :param body: Corps HTML rendu, effacé après la livraison SMTP complète.
    :type body: str | None
    :param jinja_values: Valeurs du template conservées pendant les retries.
    :type jinja_values: str
    :param has_attachments: Indique si le mail a des pièces jointes.
    :type has_attachments: bool
    :param provider_id: Identifiant stable utilisé dans l'en-tête ``Message-ID``.
    :type provider_id: str
    :param current_status: Dernier statut connu du cycle de livraison.
    :type current_status: str
    :param retry_count: Nombre de retries SMTP déjà effectués.
    :type retry_count: int
    :param next_retry_at: Date du prochain essai différé, le cas échéant.
    :type next_retry_at: datetime | None
    :param sent_at: Date et heure d'acceptation SMTP, le cas échéant.
    :type sent_at: datetime | None
    :param last_error: Dernière erreur SMTP ou IMAP sans destinataire.
    :type last_error: str | None
    :param imap_copied_at: Date de copie IMAP confirmée, le cas échéant.
    :type imap_copied_at: datetime | None
    :param statuses: Liste des statuts associés au mail.
    :type statuses: list[Status]

    .. note::
        Les adresses de ``recipients`` et ``delivered_recipients`` sont effacées après
        acceptation SMTP complète. En cas d'échec terminal, elles restent disponibles
        pour une relance manuelle.
    """
    __tablename__ = "mails"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        index=True,
        default=lambda: str(uuid.uuid4()),
        comment="Identifiant unique du mail",
    )
    sender: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Expéditeur du mail",
    )
    # Destinataires conservés uniquement pour les besoins de retry.
    # Pour l'aspect RGPD, les destinataires ne sont pas conservés de manière permanente.
    recipients: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Destinataires du mail",
    )
    delivered_recipients: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
        comment="Destinataires déjà acceptés par SMTP pendant un envoi partiel",
    )
    subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Sujet du mail",
    )
    template: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Modèle du mail",
    )
    body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Contenu HTML rendu du mail",
    )
    jinja_values: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Paires clé-valeur Jinja de remplissage du template",
    )
    has_attachments: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default=text("0"),
        comment="Indique si le mail a des pièces jointes",
    )
    provider_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default=lambda: f"<{uuid.uuid4()}@alertiny>",
        comment="Identifiant du fournisseur du mail",
    )
    current_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="Dernier statut du mail",
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Nombre de retries SMTP déjà effectués",
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Date du prochain essai SMTP",
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Date et heure d'envoi du mail",
    )
    last_error: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Dernière erreur SMTP ou IMAP sans donnée destinataire",
    )
    imap_copied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Date de copie dans le dossier IMAP des éléments envoyés",
    )
    statuses: Mapped[list["Status"]] = relationship(
        back_populates="mail",
        cascade="all, delete-orphan",
        order_by="Status.created_at",
        passive_deletes=True,
    )

    @classmethod
    def from_incoming(cls, mail: MailIncoming) -> Mail:
        """Construit un modèle ORM à partir d'une requête Pydantic.

        Cette conversion conserve les champs nécessaires au traitement et initialise
        les marqueurs de pièces jointes à ``False`` conformément au périmètre de la V1.
        Les identifiants sont attribués par les valeurs par défaut SQLAlchemy lors de
        l'insertion.

        :param mail: Données entrantes validées par Pydantic.
        :type mail: models.pydantics.mails.MailIncoming
        :returns: Nouvelle instance non persistée du modèle :class:`Mail`.
        :rtype: Mail
        """
        return cls(
            sender=mail.sender,
            recipients=",".join([r.email for r in mail.recipient]),
            subject=mail.subject,
            template=mail.template,
            jinja_values=",".join([f"{j.key}={j.value}" for j in mail.jinja_values]),
            has_attachments=False,
        )
