"""API FastAPI et planificateur des opérations Alertiny.

.. routes::
    - `/operations/{operation_id}/start`: Lance une opération immédiatement.
    - `/operations/{operation_id}/schedule`: Programme une opération à une date ISO 8601.

.. values::
    - `logger` : Logger utilisé pour consigner les événements du scheduler.
    - `scheduler` : Planificateur utilisé pour gérer les opérations programmées.
    - `_normalize_datetime` : Fonction utilisée pour normaliser les dates en UTC.
    - `execute_operation` : Fonction utilisée pour exécuter une opération donnée.
    - `lifespan` : Contexte de durée de vie utilisé pour démarrer et arrêter le scheduler
    avec FastAPI.
    - `get_app` : Fonction utilisée pour obtenir l'instance de l'application FastAPI.

.. classes::
    - `ScheduleRequest` : Classe représentant les paramètres de programmation d'une opération.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import os
from typing import AsyncGenerator
from uuid import uuid4

from apscheduler.executors.pool import ThreadPoolExecutor as ApschedulerThreadPoolExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict
import uvicorn

from params.database import session
from repositories.mails import MailsRepository


logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(
    timezone=timezone.utc,
    executors={"default": ApschedulerThreadPoolExecutor(max_workers=1)},
    job_defaults={
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 300,
    },
)


class ScheduleRequest(BaseModel):
    """Paramètres de programmation d'une opération."""

    model_config = ConfigDict(extra="forbid")

    run_at: datetime


def _normalize_datetime(value: datetime) -> datetime:
    """Normalise une date en UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def execute_operation(operation_id: str) -> None:
    """Charge et réalise l'opération associée à un identifiant de mail."""
    try:
        with session() as database_session:
            repository = MailsRepository(database_session)
            repository.get_mail_by_id(operation_id, chaine=True)
            if repository.mail is None:
                raise LookupError(f"Opération introuvable: {operation_id}")
            repository.send_mail()
    except LookupError:
        logger.warning("Opération introuvable: %s", operation_id)
        raise
    except Exception:
        logger.exception("Échec de l'opération %s", operation_id)
        raise


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Démarre et arrête le scheduler avec l'application FastAPI."""
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=True)


app = FastAPI(title="Alertiny Scheduler", lifespan=lifespan)


@app.put("/operations/{operation_id}/start", status_code=status.HTTP_202_ACCEPTED)
def start_operation(operation_id: str) -> dict[str, str]:
    """Planifie le lancement immédiat d'une opération."""
    job_id = f"operation:{operation_id}:start:{uuid4().hex}"
    scheduler.add_job(  # pyright: ignore[reportUnknownMemberType]
        execute_operation,
        trigger="date",
        run_date=datetime.now(timezone.utc),
        args=[operation_id],
        id=job_id,
    )
    return {"operation_id": operation_id, "job_id": job_id, "status": "scheduled"}


@app.put("/operations/{operation_id}/schedule", status_code=status.HTTP_202_ACCEPTED)
def schedule_operation(operation_id: str, request: ScheduleRequest) -> dict[str, str]:
    """Programme une opération à une date précise."""
    run_at = _normalize_datetime(request.run_at)
    if run_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="run_at doit être une date future.",
        )

    job_id = f"operation:{operation_id}:scheduled:{uuid4().hex}"
    scheduler.add_job(  # pyright: ignore[reportUnknownMemberType]
        execute_operation,
        trigger="date",
        run_date=run_at,
        args=[operation_id],
        id=job_id,
    )
    return {
        "operation_id": operation_id,
        "job_id": job_id,
        "status": "scheduled",
        "run_at": run_at.isoformat(),
    }


def get_app() -> FastAPI:
    """Retourne l'application FastAPI du scheduler."""
    return app


def main() -> None:
    """Lance l'API du scheduler sur le port 1111."""
    uvicorn.run(
        "scheduler.main:get_app",
        factory=True,
        host=os.getenv("SCHEDULER_HOST", "0.0.0.0"),
        port=int(os.getenv("SCHEDULER_PORT", "1111")),
        log_level=os.getenv("UVICORN_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
