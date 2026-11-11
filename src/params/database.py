"""Paramètres de configuration de la base de données SQLite.

.. db_location:: /data/alertiny.db
.. engine:: sqlite:////data/alertiny.db

.. module_author:: Rémi Verschuur rverschuur@audit-io.fr
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

engine = create_engine("sqlite:////data/alertiny.db")

session = sessionmaker(bind=engine, autoflush=True)

def get_session() -> Generator[Session, None, None]:
    """Obtient une session locale pour interagir avec la base de données.

    :return: Session locale SQLAlchemy.
    :rtype: Session
    """
    with session() as s:
        yield s
