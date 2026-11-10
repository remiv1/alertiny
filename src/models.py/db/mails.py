"""Modélisation des données liées aux mails

.. module_author:: Rémi Verschuur rverschuur@audit-io.fr
.. version:: 1.0.0
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, text
from sqlalchemy.orm import mapped_column, Mapped, relationship

from ._common import Base

if TYPE_CHECKING:
    from .status import Status

class Mail(Base):
    """Modèle représentant un mail dans la base de données.
    
    :param id: Identifiant UUID du mail.
    :type id: str
    :param sender: Expéditeur du mail.
    :type sender: str
    :param subject: Sujet du mail.
    :type subject: str
    :param body: Contenu du mail.
    :type body: str
    :param has_attachments: Indique si le mail a des pièces jointes.
    :type has_attachments: bool
    :param sent_at: Date et heure d'envoi du mail.
    :type sent_at: datetime
    :param provider_id: Identifiant du fournisseur du mail.
    :type provider_id: str
    :param sent_at: Date et heure d'envoi du mail.
    :type sent_at: datetime
    :param statuses: Liste des statuts associés au mail.
    :type statuses: list[Status]
    """
    __tablename__ = "mails"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        index=True,
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
    subject: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        comment="Sujet du mail",
    )
    template: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        comment="Modèle du mail",
    )
    jinja_values: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        comment="Paires clé-valeur Jinja de remplissage du template",
    )
    has_attachments: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default=text("0"),
        comment="Indique si le mail a des pièces jointes",
    )
    provider_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        comment="Identifiant du fournisseur du mail",
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Date et heure d'envoi du mail",
    )
    statuses: Mapped[list["Status"]] = relationship(
        back_populates="mail",
        cascade="all, delete-orphan",
        order_by="Status.created_at",
        comment="Relation vers les statuts associés au mail",
        passive_deletes=True,
    )
