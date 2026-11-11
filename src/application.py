"""Module principal de l'application Alertiny.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from security import verify_bearer_token
from api import router as api_router

@asynccontextmanager
async def lifespan(app: FastAPI):   # pylint: disable=W0613
    """Gestion du cycle de vie de l'application FastAPI."""
    # Initialisation avant le démarrage de l'application
    yield
    # Nettoyage après l'arrêt de l'application


def get_app() -> FastAPI:
    """Retourne l'instance de l'application FastAPI."""

    app = FastAPI(
        title="Alertiny API",
        dependencies=[Depends(verify_bearer_token)],
    )
    app.include_router(api_router)
    app.router.lifespan_context = lifespan

    @app.get("/health")
    def health() -> dict[str, str]:
        """Vérifie l'état de santé de l'application."""
        return {"status": "ok"}

    return app

if __name__ == "__main__":
    get_app()
