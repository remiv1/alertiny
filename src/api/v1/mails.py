"""Routes HTTP v1 de création, de suivi et de relance des notifications mail.

Les routes sont montées sous ``/api/v1/mails`` par
:mod:`api.v1`. La dépendance applicative de sécurité protège ces routes par
authentification Bearer. La création valide et rend le template avant de persister la
notification; elle retourne immédiatement un identifiant de suivi avec le statut HTTP
``202 Accepted``. Les réponses de suivi ne contiennent ni les adresses des destinataires
ni le contenu du message.

.. routes::
    - ``GET /`` : liste les états des notifications.
    - ``GET /{mail_id}`` : consulte l'état et les dates d'une notification.
    - ``POST /`` : valide et ajoute une notification à la file.
    - ``POST /send`` : alias historique de l'ajout à la file.
    - ``POST /{mail_id}/retry`` : remet en file un échec terminal.
    - ``PUT /send/{mail_id}`` : déclenche immédiatement le traitement d'un mail en file.

.. functions::
    - :func:`_queue` : applique les conversions d'erreurs du dépôt vers HTTP.
    - :func:`get_mails` : retourne la liste des états accessibles.
    - :func:`get_mail` : retourne un état par identifiant.
    - :func:`retry_mail` : réinscrit un mail en échec.
    - :func:`create_mail` : crée une notification asynchrone.
    - :func:`send_mail` : conserve l'alias de création historique.
    - :func:`send_mail_after_creation` : lance une tentative immédiate.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from exc.mails import (
    MailCompileException,
    MailDatabaseException,
    MailNotFoundException,
    MailRetryNotAllowedException,
)
from models.pydantics.mails import MailIncoming
from params.application import SessionDep
from repositories.mails import MailsRepository

router = APIRouter(prefix="/mails", tags=["api", "v1", "mails"])
MAIL_NOT_FOUND = "Email not found"


def _queue(incoming: MailIncoming, session: SessionDep) -> dict[str, str]:
    """Ajoute une notification à la file et convertit les erreurs en réponses HTTP.

    :param incoming: Données validées par Pydantic pour la notification à créer.
    :type incoming: models.pydantics.mails.MailIncoming
    :param session: Session SQLAlchemy fournie par la dépendance de l'application.
    :type session: params.application.SessionDep
    :returns: Identifiant de suivi et statut initial de la notification.
    :rtype: dict[str, str]
    :raises fastapi.HTTPException: Avec le statut ``422`` si le template ou les données
        ne sont pas valides, ou ``500`` si la persistance échoue.
    """
    try:
        mail = MailsRepository(session).queue_mail(incoming)
    except MailCompileException as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except MailDatabaseException as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not queue email",
        ) from error

    return {"id": mail.id, "status": mail.current_status}


@router.get("/")
def get_mails(session: SessionDep) -> dict[str, list[dict[str, str | int | None]]]:
    """Retourne la liste des notifications sans exposer leur contenu sensible.

    :param session: Session SQLAlchemy fournie par la dépendance de l'application.
    :type session: params.application.SessionDep
    :returns: Objet JSON contenant une liste d'états publics.
    :rtype: dict[str, list[dict[str, str | int | None]]]
    :raises fastapi.HTTPException: Avec le statut ``500`` si la lecture échoue.
    """
    try:
        mails = MailsRepository(session).get_mails()
    except MailDatabaseException as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not fetch emails",
        ) from error
    return {"mails": [MailsRepository.public_status(mail) for mail in mails]}


@router.get("/{mail_id}")
def get_mail(mail_id: str, session: SessionDep) -> dict[str, str | int | None]:
    """Retourne le statut public d'une notification.

    :param mail_id: Identifiant UUID communiqué à la création.
    :type mail_id: str
    :param session: Session SQLAlchemy fournie par la dépendance de l'application.
    :type session: params.application.SessionDep
    :returns: Statut, nombre de retries, dates d'envoi et erreur éventuelle.
    :rtype: dict[str, str | int | None]
    :raises fastapi.HTTPException: Avec le statut ``404`` si l'identifiant est inconnu,
        ou ``500`` si la lecture de la base échoue.
    """
    repository = MailsRepository(session)
    try:
        mail = repository.get_mail_by_id(mail_id)
    except MailDatabaseException as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not fetch email",
        ) from error
    if mail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=MAIL_NOT_FOUND,
        )
    return repository.public_status(mail)


@router.post("/{mail_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_mail(
    mail_id: str,
    session: SessionDep,
) -> dict[str, str | int | None]:
    """Remet en file une notification ayant épuisé ses retries automatiques.

    Les destinataires non livrés restent stockés jusqu'à l'acceptation SMTP. Le dépôt
    réinitialise le compteur de retries et le worker reprend ensuite le traitement.

    :param mail_id: Identifiant UUID de la notification en échec.
    :type mail_id: str
    :param session: Session SQLAlchemy fournie par la dépendance de l'application.
    :type session: params.application.SessionDep
    :returns: État public de la notification après sa remise en file.
    :rtype: dict[str, str | int | None]
    :raises fastapi.HTTPException: Avec le statut ``404`` si l'identifiant est inconnu,
        ``409`` si la notification ne peut pas être relancée, ou ``500`` si la
        persistance échoue.
    """
    repository = MailsRepository(session)
    try:
        mail = repository.retry_failed_mail(mail_id)
    except MailNotFoundException as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=MAIL_NOT_FOUND,
        ) from error
    except MailRetryNotAllowedException as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except MailDatabaseException as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not requeue email",
        ) from error
    return repository.public_status(mail)


@router.post("/", status_code=status.HTTP_202_ACCEPTED)
def create_mail(
    data: MailIncoming,
    session: SessionDep,
) -> dict[str, str]:
    """Valide une notification, la met en file et retourne immédiatement.

    Le rendu du template et la persistance sont réalisés avant le retour, mais aucune
    connexion SMTP n'est ouverte par cette route.

    :param data: Expéditeur, destinataires et données du template.
    :type data: models.pydantics.mails.MailIncoming
    :param session: Session SQLAlchemy fournie par la dépendance de l'application.
    :type session: params.application.SessionDep
    :returns: Identifiant de suivi et statut ``pending``.
    :rtype: dict[str, str]
    :raises fastapi.HTTPException: Avec le statut ``422`` si les données ou le template
        sont invalides, ou ``500`` si la persistance échoue.
    """
    return _queue(data, session)


@router.post("/send", status_code=status.HTTP_202_ACCEPTED)
def send_mail(
    data: MailIncoming,
    session: SessionDep,
) -> dict[str, str]:
    """Alias historique de ``POST /mails/``.

    Cette route conserve l'ancienne URL mais utilise désormais le traitement asynchrone:
    elle ajoute la notification à la même file persistante et ne transmet pas directement
    le message via SMTP.

    :param data: Expéditeur, destinataires et données du template.
    :type data: models.pydantics.mails.MailIncoming
    :param session: Session SQLAlchemy fournie par la dépendance de l'application.
    :type session: params.application.SessionDep
    :returns: Identifiant de suivi et statut initial.
    :rtype: dict[str, str]
    :raises fastapi.HTTPException: Avec le statut ``422`` si la requête est invalide,
        ou ``500`` si la persistance échoue.
    """
    return _queue(data, session)


@router.put("/send/{mail_id}")
def send_mail_after_creation(
    mail_id: str,
    session: SessionDep,
) -> dict[str, str | int | None]:
    """Déclenche une tentative immédiate pour un mail déjà en file.

    Contrairement aux routes de création, cette opération attend la tentative SMTP et,
    en cas de succès, la copie IMAP. Une notification qui n'est pas en état ``pending``
    est retournée sans être retraitée.

    :param mail_id: Identifiant UUID de la notification à traiter.
    :type mail_id: str
    :param session: Session SQLAlchemy fournie par la dépendance de l'application.
    :type session: params.application.SessionDep
    :returns: État public après la tentative, sans adresses ni contenu.
    :rtype: dict[str, str | int | None]
    :raises fastapi.HTTPException: Avec le statut ``404`` si l'identifiant est inconnu
        ou ``500`` si une transition en base échoue.
    """
    repository = MailsRepository(session)
    try:
        mail = repository.process_mail(mail_id)
    except MailNotFoundException as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=MAIL_NOT_FOUND,
        ) from error
    except MailDatabaseException as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not process email",
        ) from error
    return repository.public_status(mail)
