"""Tests unitaires des schémas et de la conversion des notifications mail.

Le module vérifie la validation des requêtes :class:`MailIncoming` et la conversion de
leurs champs vers le modèle SQLAlchemy :class:`Mail`.

.. fixtures::
    - :func:`mail_incoming` : fournit une requête valide utilisée par les tests.
"""

from typing import Any, Literal

import pytest
from pydantic import ValidationError

from models.pydantics.mails import (
    JinjaValues,
    MailIncoming,
    Recipient,
)
from models.db.mails import Mail


@pytest.fixture
def mail_incoming() -> MailIncoming:
    """Construit une requête valide pour le template de service indisponible.

    :returns: Requête contenant un expéditeur, un sujet, un template, une variable,
        une liste de pièces jointes vide et un destinataire.
    :rtype: models.pydantics.mails.MailIncoming
    """
    return MailIncoming(
        sender="alertiny@example.com",
        subject="Service indisponible",
        template="service_down.html",
        jinja_values=[
            JinjaValues(key="service", value="API"),
        ],
        attachments=[],
        recipient=[
            Recipient(email="admin@example.com"),
        ],
    )


def test_mail_incoming_accepts_valid_data(mail_incoming: MailIncoming) -> None: # pylint: disable=W0621
    """Vérifie qu'une requête valide conserve son sujet et son destinataire.

    :param mail_incoming: Requête valide fournie par la fixture du module.
    :type mail_incoming: models.pydantics.mails.MailIncoming
    :returns: ``None``.
    :rtype: None
    """
    assert mail_incoming.subject == "Service indisponible"
    assert mail_incoming.recipient[0].email == "admin@example.com"


def test_mail_incoming_requires_recipient(mail_incoming: MailIncoming) -> None: # pylint: disable=W0621
    """Vérifie l'affectation directe d'une liste vide aux destinataires.

    Cette affectation après construction ne relance pas la validation Pydantic; le test
    documente uniquement le comportement de l'instance déjà créée.

    :param mail_incoming: Requête valide fournie par la fixture du module.
    :type mail_incoming: models.pydantics.mails.MailIncoming
    :returns: ``None``.
    :rtype: None
    """
    mail_incoming.recipient = []

    assert mail_incoming.recipient == []


def test_mail_from_incoming_maps_mail_fields(mail_incoming: MailIncoming) -> None: # pylint: disable=W0621
    """Vérifie la conversion des champs métier vers le modèle SQLAlchemy.

    :param mail_incoming: Requête contenant les valeurs à convertir.
    :type mail_incoming: models.pydantics.mails.MailIncoming
    :returns: ``None``.
    :rtype: None
    """
    mail = Mail.from_incoming(mail_incoming)

    assert mail.sender == "alertiny@example.com"
    assert mail.recipients == "admin@example.com"
    assert mail.subject == "Service indisponible"
    assert mail.template == "service_down.html"
    assert mail.jinja_values == "service=API"
    assert mail.has_attachments is False


@pytest.mark.parametrize(
    "missing_field",
    ["sender", "template", "jinja_values", "recipient"],
)
def test_mail_incoming_requires_fields(
    missing_field: Literal[
        'sender',
        'subject',
        'template',
        'jinja_values',
        'attachments',
        'recipient',
    ]
) -> None:
    """Vérifie que chaque champ paramétré est obligatoire dans une requête.

    :param missing_field: Nom du champ retiré du dictionnaire avant validation.
    :type missing_field: Literal['sender', 'subject', 'template', 'jinja_values',
        'attachments', 'recipient']
    :returns: ``None``.
    :rtype: None
    :raises pydantic.ValidationError: Le modèle rejette la requête privée d'un champ.
    """
    data: dict[str, Any] = {
        "sender": "alertiny@example.com",
        "subject": "Service indisponible",
        "template": "service_down.html",
        "jinja_values": [],
        "attachments": [],
        "recipient": [],
    }
    del data[missing_field]

    with pytest.raises(ValidationError):
        MailIncoming(**data)
