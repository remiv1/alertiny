"""Module commun de la modélisation des données

.. module_author:: Rémi Verschuur rverschuur@audit-io.fr
.. version:: 1.0.0
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import declarative_base, mapped_column, Mapped
from sqlalchemy import DateTime, text

Base = declarative_base()

class Mixins(Base):
    """Classe de mixin commune pour les modèles de la base de données."""

    __abstract__ = True
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="Date et heure de création de l'enregistrement",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
        comment="Date et heure de la dernière mise à jour de l'enregistrement",
    )

    def __repr__(self) -> str:
        return (f"<{self.__class__.__name__}(created_at={self.created_at}, "
                f"updated_at={self.updated_at})>")

    def to_dict(self) -> dict[str, object]:
        """Convertit l'objet en dictionnaire.

        :return: Dictionnaire représentant l'objet.
        :rtype: dict[str, object]
        """
        return {k: getattr(self, k) for k in self.__mapper__.c.keys()}

    def from_dict(self, data: dict[str, object]) -> None:
        """Met à jour l'objet à partir d'un dictionnaire.

        :param data: Dictionnaire contenant les valeurs à mettre à jour.
        :type data: dict[str, object]
        """
        for k, v in data.items():
            if k in self.__mapper__.c.keys():
                setattr(self, k, v)
