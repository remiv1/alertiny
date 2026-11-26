"""Tests de mise à niveau des schémas SQLite déjà présents.

Le module vérifie que l'initialisation ajoute les colonnes requises par la file V1 sans
perdre les statuts historiques existants.

.. moduleauthor:: Rémi Verschuur <rverschuur@audit-io.fr>
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

import params.database as database_parameters


def test_initialize_database_adds_queue_columns_to_existing_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vérifie l'ajout idempotent des colonnes et la reprise du statut historique.

    :param monkeypatch: Outil pytest qui substitue le moteur SQLAlchemy global.
    :type monkeypatch: pytest.MonkeyPatch
    :returns: ``None``.
    :rtype: None
    """
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(
            """
            CREATE TABLE mails (
                id VARCHAR(36) PRIMARY KEY,
                sender VARCHAR(255) NOT NULL,
                recipients VARCHAR(255) NOT NULL,
                subject VARCHAR(255),
                template VARCHAR(255),
                jinja_values VARCHAR(255),
                has_attachments BOOLEAN NOT NULL DEFAULT 0,
                provider_id VARCHAR(36) NOT NULL,
                sent_at DATETIME,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        ))
        connection.execute(text(
            """
            CREATE TABLE status (
                id VARCHAR(36) PRIMARY KEY,
                mail_id VARCHAR(36) NOT NULL,
                status VARCHAR(255) NOT NULL,
                comment VARCHAR(255),
                created_at DATETIME NOT NULL
            )
            """
        ))
        connection.execute(text(
            """
            INSERT INTO mails (
                id, sender, recipients, subject, template, jinja_values,
                has_attachments, provider_id, created_at, updated_at
            ) VALUES (
                'mail-1', 'alerts@example.com', 'ops@example.com', 'Alert',
                'service_down.html', '', 0, 'provider-1', CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """
        ))
        connection.execute(text(
            """
            INSERT INTO status (id, mail_id, status, created_at)
            VALUES ('status-1', 'mail-1', 'pending', CURRENT_TIMESTAMP)
            """
        ))

    monkeypatch.setattr(database_parameters, "engine", engine)

    database_parameters.initialize_database()

    columns = {column["name"] for column in inspect(engine).get_columns("mails")}
    with engine.connect() as connection:
        status, retry_count = connection.execute(
            text("SELECT current_status, retry_count FROM mails WHERE id = 'mail-1'")
        ).one()

    assert {
        "body",
        "current_status",
        "retry_count",
        "next_retry_at",
        "imap_copied_at",
        "last_error",
        "delivered_recipients",
    }.issubset(columns)
    assert status == "pending"
    assert retry_count == 0
    engine.dispose()
