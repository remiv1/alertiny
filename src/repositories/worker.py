"""Worker applicatif chargé de vider la file persistante des e-mails.

Ce module fournit une façade réduite autour de :class:`repositories.mails.MailsRepository`.
Le scheduler l'instancie avec une session dédiée pour chaque lot; cette séparation
permet de piloter le traitement et la réconciliation sans exposer la logique SQL au
planificateur.

.. classes::
    - :class:`MailWorker` : traite les lots dus et réconcilie les tâches interrompues.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from params.mails import MailConfig
from .mails import MailsRepository


class MailWorker:
    """Façade de traitement de la file d'envoi.

    :param session: Session SQLAlchemy à utiliser pour une opération du worker. La session
        doit rester ouverte pendant l'appel à :meth:`run_once` ou :meth:`reconcile`.
    :type session: sqlalchemy.orm.Session
    :param config: Configuration mail facultative, principalement utile aux tests et aux
        exécutions ayant déjà chargé la configuration.
    :type config: params.mails.MailConfig | None

    .. attributs::
        - ``repository`` (:class:`~repositories.mails.MailsRepository`) : service
          responsable de la persistance et des transitions d'état.
    """

    def __init__(self, session: Session, config: MailConfig | None = None) -> None:
        """Crée le worker et son dépôt associé.

        :param session: Session de base de données fournie par le scheduler.
        :type session: sqlalchemy.orm.Session
        :param config: Configuration mail facultative.
        :type config: params.mails.MailConfig | None
        :raises OSError: Si le fichier de configuration mail ne peut pas être lu.
        :raises ValueError: Si les paramètres mail sont invalides.
        """
        self.repository = MailsRepository(session, config)

    def run_once(self, limit: int = 25) -> int:
        """Traite un lot de notifications arrivées à échéance.

        :param limit: Nombre maximal d'éléments à lire dans la file pour ce lot.
        :type limit: int
        :returns: Nombre d'identifiants pris en charge.
        :rtype: int
        :raises MailDatabaseException: Si la lecture ou la mise à jour de la file échoue.
            Les erreurs de transport individuelles sont enregistrées dans le statut mail.
        """
        return self.repository.process_due_mails(limit)

    def reconcile(self) -> int:
        """Réconcilie les tentatives laissées en cours par un arrêt du scheduler.

        Les messages en état ``sending`` sont replacés en état ``pending``; l'incertitude
        liée à une éventuelle acceptation SMTP avant l'arrêt est conservée dans leur
        erreur de suivi.

        :returns: Nombre de messages remis en file.
        :rtype: int
        :raises MailDatabaseException: Si la lecture ou l'enregistrement de la
            réconciliation échoue.
        """
        return self.repository.reconcile_interrupted_mails()
