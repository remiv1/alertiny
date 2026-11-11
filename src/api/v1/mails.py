"""Module de gestion des mails de l'API Alertiny.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from fastapi import APIRouter

from params.application import SessionDep
from repositories import MailsRepository
from models.pydantics.mails import MailIncoming

router = APIRouter(prefix="/mails", tags=["api", "v1", "mails"])

@router.get("/", tags=["api", "v1", "mails"])
def get_mails(session: SessionDep) -> dict[str, object]:
    """Récupère la liste des mails."""
    repo = MailsRepository(session)
    mails = repo.get_mails()
    return {"message": mails}

@router.post("/", tags=["api", "v1", "mails"])
def create_mail(session: SessionDep, data: MailIncoming) -> dict[str, str]:
    """Crée un nouveau mail et retourne un template réalisé."""
    repo = MailsRepository(session)
    mail_content = repo.generate_mail(mail=data)
    repo.create_mail(mail=data)
    return {"message": mail_content}

@router.post("/send", tags=["api", "v1", "mails"])
def send_mail(session: SessionDep, data: MailIncoming) -> dict[str, str]:
    """Envoie un mail."""
    repo = MailsRepository(session)
    mail = repo.create_mail(mail=data)
    repo.send_mail(mail=mail)
    return {"message": "Mail sent"}

@router.put("/send/{mail_id}", tags=["api", "v1", "mails"])
def send_mail_after_creation(mail_id: str, session: SessionDep) -> dict[str, str]:
    """Envoie un mail après sa création."""
    return {"message": f"Mail {mail_id} sent"}
