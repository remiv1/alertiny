"""Exceptions métier levées pendant le traitement des notifications.

Les exceptions de ce module permettent de distinguer les erreurs de validation et de
rendu, les erreurs de persistance, les échecs de transport et les demandes de relance
qui ne correspondent pas à un mail en échec.

.. exceptions::
    - :class:`MailException` : classe parente de toutes les erreurs mail.
    - :class:`MailNotFoundException` : identifiant de mail absent de la base.
    - :class:`MailSendException` : erreur de transport SMTP ou IMAP.
    - :class:`MailRetryNotAllowedException` : état incompatible avec une relance.
    - :class:`MailCompileException` : modèle invalide ou erreur de rendu.
    - :class:`MailDatabaseException` : erreur SQLAlchemy liée aux mails.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""

class MailException(Exception):
    """Classe de base des exceptions métier du domaine mail.

    :param args: Arguments transmis au constructeur de :class:`Exception`.
    :type args: object

    Cette exception n'est normalement pas levée directement; les exceptions spécialisées
    ci-dessous décrivent la catégorie d'échec.
    """

class MailNotFoundException(MailException):
    """Indique qu'un identifiant de notification n'existe pas.

    :param args: Message décrivant l'identifiant recherché ou arguments d'exception.
    :type args: object
    """

class MailSendException(MailException):
    """Indique un échec SMTP ou une erreur de copie du message dans IMAP.

    :param args: Message de diagnostic du transport, sans données de destinataire.
    :type args: object

    Les erreurs SMTP sont converties en retries par le dépôt. Une erreur IMAP survenant
    après l'acceptation SMTP est enregistrée sans nouvel envoi SMTP.
    """

class MailRetryNotAllowedException(MailException):
    """Indique qu'un mail ne peut pas être remis en file manuellement.

    Cette exception est utilisée lorsque le mail n'est pas en état ``failed`` ou qu'il
    ne reste aucun destinataire dont la livraison est à effectuer.

    :param args: Message décrivant l'état incompatible.
    :type args: object
    """

class MailCompileException(MailException):
    """Indique que la sélection ou le rendu d'un template a échoué.

    :param args: Message de diagnostic du modèle ou des variables manquantes.
    :type args: object
    """

class MailDatabaseException(MailException):
    """Indique qu'une opération SQLAlchemy liée aux mails a échoué.

    :param args: Message décrivant l'opération qui n'a pas pu être effectuée.
    :type args: object
    """
