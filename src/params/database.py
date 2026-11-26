"""Moteur SQLAlchemy, sessions de travail et initialisation du schéma.

.. db_location:: /data/alertiny.db
.. engine:: sqlite:////data/alertiny.db

L'URL de connexion peut être remplacée par ``ALERTINY_DATABASE_URL``. SQLite est la
base prévue pour la V1; les connexions SQLite autorisent leur utilisation dans les
threads de travail FastAPI. :func:`initialize_database` crée les tables déclarées dans
les modèles et ajoute les colonnes de file introduites par la V1 aux bases existantes.

.. functions::
    - :func:`initialize_database` : crée et met à niveau le schéma.
    - :func:`get_session` : fournit une session SQLAlchemy à FastAPI.

.. module_author:: Rémi Verschuur rverschuur@audit-io.fr
.. version:: 1.0.0
"""
from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session

DATABASE_URL = os.getenv("ALERTINY_DATABASE_URL", "sqlite:////data/alertiny.db")
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
session = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)


def initialize_database() -> None:
    """Crée les tables SQLAlchemy et applique les migrations additives de la V1.

    Les tables absentes sont créées depuis ``Base.metadata``. Pour la table ``mails``,
    les colonnes du corps rendu, de l'état courant, des retries, des dates et du suivi
    IMAP sont ajoutées si elles n'existent pas. Les états historiques sont ensuite
    recopiés dans la colonne de statut courant.

    La fonction est idempotente et peut être appelée par l'API ou le scheduler au
    démarrage.

    :returns: ``None``.
    :rtype: None
    :raises sqlalchemy.exc.SQLAlchemyError: Si la création des tables, l'inspection ou
        une migration SQL échoue.
    """
    from models.db._common import Base # pylint: disable=C0415

    Base.metadata.create_all(bind=engine, checkfirst=True)
    existing_columns = {
        column["name"] for column in inspect(engine).get_columns("mails")
    }
    migrations = {
        "body": "TEXT",
        "delivered_recipients": "TEXT NOT NULL DEFAULT ''",
        "current_status": "VARCHAR(20) NOT NULL DEFAULT 'pending'",
        "retry_count": "INTEGER NOT NULL DEFAULT 0",
        "next_retry_at": "DATETIME",
        "imap_copied_at": "DATETIME",
        "last_error": "VARCHAR(255)",
    }
    with engine.begin() as connection:
        for column_name, column_definition in migrations.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE mails ADD COLUMN {column_name} {column_definition}")
                )
        connection.execute(text(
            """
            UPDATE mails
            SET current_status = COALESCE(
                (SELECT status FROM status
                 WHERE status.mail_id = mails.id
                 ORDER BY status.created_at DESC LIMIT 1),
                current_status
            )
            """
        ))

def get_session() -> Generator[Session, None, None]:
    """Fournit une session SQLAlchemy et la ferme à la fin de la dépendance.

    Cette fonction génératrice est destinée à être utilisée comme dépendance FastAPI.
    La session ne doit pas être conservée au-delà de la requête.

    :yields: Session liée au moteur configuré.
    :yieldtype: sqlalchemy.orm.Session
    """
    with session() as s:
        yield s
