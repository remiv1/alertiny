"""Module principal de l'application Alertiny.

.. prefix:: `/`

.. routes::
    - `/health`: Vérifie l'état de santé de l'application et retourne un diagnostique complet
    reprenant l'état de santé de la base de données ainsi que l'état de santé de l'application
    y compris les variables d'environnement et la complexité des mots-de-passe.

.. fonctions::
    - `get_app`: Crée et retourne l'instance de l'application FastAPI.
    - `lifespan`: Gestion du cycle de vie de l'application FastAPI.

Au démarrage, le contexte de cycle de vie initialise ou met à niveau le schéma SQLite et
valide la configuration SMTP/IMAP avant que l'application accepte des requêtes. Les routes
de l'API sont montées sous ``/api/v1`` et protégées par la dépendance Bearer; ``/health``
reste accessible sans authentification pour les sondes d'orchestration.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import os
from typing import Any, AsyncGenerator

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from security import (
    BEARER_TOKEN_ENV_VAR,
    REQUIRED_ENVIRONMENT_VARIABLES,
    verify_bearer_token,
)
from api import router as api_router
from params.application import SessionDep
from params.database import initialize_database
from params.mails import load_mail_config

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, Any]:   # pylint: disable=W0613
    """Gestion du cycle de vie de l'application FastAPI.

    Avant d'accepter des requêtes, initialise la base et charge la configuration mail
    afin de détecter les paramètres invalides au démarrage. Le bloc après ``yield`` est
    réservé au nettoyage des ressources lorsque l'application s'arrête.

    :param app: Instance de l'application FastAPI.
    :type app: fastapi.FastAPI

    :yields: Contrôle à l'application pendant sa période d'activité.
    :yieldtype: None
    :raises sqlalchemy.exc.SQLAlchemyError: Si l'initialisation du schéma échoue.
    :raises OSError: Si un fichier de configuration ne peut pas être lu.
    :raises ValueError: Si la configuration SMTP/IMAP est invalide.
    """
    initialize_database()
    load_mail_config()
    yield
    # Nettoyage après l'arrêt de l'application


def get_app() -> FastAPI:
    """Construit l'application FastAPI et monte les routes publiques et métier.

    Toutes les routes de l'API sont protégées par :func:`security.verify_bearer_token`;
    la route ``/health`` est explicitement exemptée dans cette dépendance pour permettre
    les sondes sans secret.

    :returns: Application FastAPI configurée avec son contexte de cycle de vie.
    :rtype: fastapi.FastAPI
    """

    app = FastAPI(
        title="Alertiny API",
        dependencies=[Depends(verify_bearer_token)],
    )
    app.include_router(api_router)
    app.router.lifespan_context = lifespan

    @app.get("/health")
    def health(session: SessionDep) -> dict[str, Any]:
        """Retourne un diagnostic synthétique de l'API, de la base et de l'environnement.

        Le diagnostic vérifie l'accès à la base avec une requête ``SELECT 1``, indique
        les variables d'environnement requises absentes et ajoute un avertissement si
        le jeton Bearer semble trop faible.

        :param session: Session de base de données fournie par la dépendance FastAPI.
        :type session: params.application.SessionDep
        :returns: Dictionnaire comprenant les clés ``API``, ``DATABASE`` et
            ``ENVIRONMENT``; la valeur de ``ENVIRONMENT`` inclut les variables manquantes
            et avertissements éventuels.
        :rtype: dict[str, typing.Any]
        """
        missing_environment_variables = [
            name for name in REQUIRED_ENVIRONMENT_VARIABLES if not os.getenv(name)
        ]
        bearer_token = os.getenv(BEARER_TOKEN_ENV_VAR, "")
        warnings: list[str] = []
        if bearer_token and len(bearer_token) < 32 and not (
            any(character.isupper() for character in bearer_token)
            and any(character.islower() for character in bearer_token)
            and any(character.isdigit() for character in bearer_token)
        ):
            warnings.append(
                f"{BEARER_TOKEN_ENV_VAR} devrait faire au moins 32 caractères "
                "ou contenir une majuscule, une minuscule et un chiffre."
            )
        try:
            session.execute(text("SELECT 1;"))
        except SQLAlchemyError:
            database_status = "NOK"
        else:
            database_status = "OK"

        diag: dict[str, Any] = {
            "API": "OK",
            "DATABASE": database_status,
            "ENVIRONMENT": {
                "status": "NOK" if missing_environment_variables else "OK",
            },
        }
        if len(missing_environment_variables) > 0:
            diag["ENVIRONMENT"]["missing_variables"] = missing_environment_variables
        if len(warnings) > 0:
            diag["ENVIRONMENT"]["warnings"] = warnings

        return diag

    return app

if __name__ == "__main__":
    get_app()
