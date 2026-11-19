"""Exceptions liées aux mails.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""

class MailException(Exception):
    """Exception de base pour les erreurs liées aux mails."""

class MailNotFoundException(MailException):
    """Exception levée lorsqu'un mail n'est pas trouvé."""

class MailSendException(MailException):
    """Exception levée lorsqu'un mail ne peut pas être envoyé."""

class MailCompileException(MailException):
    """Exception levée lorsqu'un mail ne peut pas être compilé."""

class MailDatabaseException(MailException):
    """Exception levée lorsqu'une erreur se produit dans la base de données des mails."""
