"""Modélisation des données liées aux statuts

.. module_author:: Rémi Verschuur rverschuur@audit-io.fr
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from enum import Enum
from datetime import datetime
import uuid

from sqlalchemy import String, DateTime, CheckConstraint, ForeignKey, func
from sqlalchemy.orm import mapped_column, Mapped, relationship

from ._common import Mixins

if TYPE_CHECKING:
    from .mails import Mail

class MailStatus(Enum):
    """Valeurs autorisées pour l'historique de statut d'une notification.

    ``PENDING`` représente une livraison à effectuer ou à retenter, ``SENT`` indique que
    SMTP a accepté le mail, ``FAILED`` indique que le budget de retries est épuisé et
    ``UNKNOWN`` est réservé aux données dont l'état ne peut pas être déterminé.
    """
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    UNKNOWN = "unknown"

    @classmethod
    def as_sql_values(cls) -> str:
        """Formate les valeurs pour la contrainte SQL ``CHECK`` du modèle.

        :returns: Liste séparée par des virgules des valeurs entre apostrophes.
        :rtype: str
        """
        return ', '.join(f"'{st.value}'" for st in cls)

class Status(Mixins):
    """Modèle représentant un statut dans la base de données.

    :param id: Identifiant UUID du statut.
    :type id: str
    :param mail_id: Identifiant du mail associé à cet événement.
    :type mail_id: str
    :param status: Valeur choisie parmi :class:`MailStatus`.
    :type status: str
    :param comment: Détail facultatif d'un échec ou d'une reprise.
    :type comment: str | None
    :param created_at: Horodatage de création de l'événement.
    :type created_at: datetime
    :param mail: Mail parent de la relation ORM.
    :type mail: models.db.mails.Mail

    Chaque changement notable est ajouté à l'historique plutôt que de remplacer les
    événements précédents. La dernière valeur courante est également stockée dans
    ``Mail.current_status`` pour permettre au worker de sélectionner efficacement les
    éléments de la file.
    """
    __tablename__ = "status"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({MailStatus.as_sql_values()})",
            name="ck_status"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Identifiant unique du statut",
    )
    mail_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mails.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Identifiant du mail associé au statut",
    )
    status: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Nom du statut",
        server_default=MailStatus.PENDING.value,
    )
    comment: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Commentaire associé au statut, notamment en cas d'échec",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),  # pylint: disable=E1102
        comment="Date de création du statut",
    )
    mail: Mapped["Mail"] = relationship(
        back_populates="statuses",
    )
