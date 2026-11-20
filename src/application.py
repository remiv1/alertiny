"""Module principal de l'application Alertiny.

.. prefix:: `/`

.. routes::
    - `/health`: Vérifie l'état de santé de l'application et retourne un diagnostique complet
    reprenant l'état de santé de la base de données ainsi que l'état de santé de l'application
    y compris les variables d'environnement et la complexité des mots-de-passe.

.. fonctions::
    - `get_app`: Crée et retourne l'instance de l'application FastAPI.
    - `lifespan`: Gestion du cycle de vie de l'application FastAPI.

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

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, Any]:   # pylint: disable=W0613
    """Gestion du cycle de vie de l'application FastAPI.

    Cette fonction est utilisée pour initialiser et nettoyer les ressources
    avant le démarrage et après l'arrêt de l'application.

    :param app: Instance de l'application FastAPI.
    :type app: fastapi.FastAPI

    :rtype: AsyncGenerator[None, Any]
    """
    # Initialisation avant le démarrage de l'application
    yield
    # Nettoyage après l'arrêt de l'application


def get_app() -> FastAPI:
    """Retourne l'instance de l'application FastAPI et sa route `/health`.
    
    :return: Instance de l'application FastAPI.
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
        """Vérifie l'état de santé de l'application.
        
        :param session: Session de base de données.
        :type session: SessionDep

        :return: Diagnostic de l'état de santé de l'application.
        :rtype: dict[str, Any]
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
