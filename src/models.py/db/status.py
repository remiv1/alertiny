"""Modélisation des données liées aux statuts

.. module_author:: Rémi Verschuur rverschuur@audit-io.fr
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from enum import Enum
from datetime import datetime

from sqlalchemy import String, DateTime, CheckConstraint, ForeignKey, func
from sqlalchemy.orm import mapped_column, Mapped, relationship

from ._common import Base

if TYPE_CHECKING:
    from .mails import Mail

class MailStatus(Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    UNKNOWN = "unknown"

    @classmethod
    def as_sql_values(cls) -> str:
        return ', '.join(f"'{st.value}'" for st in cls)

class Status(Base):
    """Modèle représentant un statut dans la base de données.

    :param id: Identifiant UUID du statut.
    :type id: str
    :param name: Nom du statut.
    :type name: str
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
        server_default=func.now(),
        comment="Date de création du statut",
    )
    mail: Mapped["Mail"] = relationship(
        back_populates="statuses",
        comment="Relation vers le mail associé au statut",
    )
