"""Module de gestion des mails de l'API Alertiny. Le module comprends l'ensemble de routes
liées aux mails.

.. prefixe:: `/api/v1/mails`

.. values::
    - routeur: APIRouter pour la gestion des mails de l'API Alertiny

.. routes::
    - `/` (GET): Récupère la liste des mails.
    - `/` (POST): Crée un nouveau mail et retourne le mail en html.
    - `/send` (POST): Crée un mail depuis le template et l'envoie.
    - `/send/{mail_id}` (PUT): Envoie un mail déjà existant en base.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from fastapi import APIRouter

from params.application import SessionDep
from repositories import MailsRepository
from models.pydantics.mails import MailIncoming

from exc.mails import MailDatabaseException, MailCompileException

router = APIRouter(prefix="/mails", tags=["api", "v1", "mails"])

@router.get("/", tags=["api", "v1", "mails"])
def get_mails(session: SessionDep) -> dict[str, object]:
    """Récupère la liste de tous les mails.
    
    :param session: La session de la base de données passée par les dépendances.
    :type session: params.application.SessionDep

    :raises MailDatabaseException: Si une erreur se produit lors de l'accès à la base de données
    des mails.
    """
    repo = MailsRepository(session)
    try:
        mails = repo.get_mails()
    except MailDatabaseException as e:
        return {"error": str(e)}
    return {"message": mails}

@router.post("/", tags=["api", "v1", "mails"])
async def create_mail(session: SessionDep, data: MailIncoming) -> dict[str, str]:
    """Crée un nouveau mail et retourne un template réalisé.
    
    :param session: La session de la base de données passée par les dépendances.
    :type session: params.application.SessionDep
    :param data: Les données du mail à créer.
    :type data: models.pydantics.mails.MailIncoming

    :raises MailDatabaseException: Si une erreur se produit lors de l'accès à la base de données
    des mails.
    """
    repo = MailsRepository(session)
    try:
        mail_content = repo.generate_mail(mail=data)
    except ValueError as e:
        return {"error": f"You have to send complete data to generate mail: {str(e)}"}
    except MailDatabaseException as e:
        return {"error": f"transactional error with database: {str(e)}"}
    except MailCompileException as e:
        return {"templating error when compiling mail": str(e)}
    await repo.send_new_mail(mail=data)
    return {"message": mail_content}

@router.post("/send", tags=["api", "v1", "mails"])
async def send_mail(session: SessionDep, data: MailIncoming) -> dict[str, str]:
    """Envoie un mail."""
    repo = MailsRepository(session)
    await repo.send_new_mail(mail=data)
    return {"message": "Mail sent"}

@router.put("/send/{mail_id}", tags=["api", "v1", "mails"])
def send_mail_after_creation(mail_id: str, session: SessionDep) -> dict[str, str]:
    """Envoie un mail après sa création."""
    repo = MailsRepository(session)
    repo.get_mail_by_id(mail_id=mail_id, chaine=True).send_mail()
    return {"message": f"Mail {mail_id} sent"}
