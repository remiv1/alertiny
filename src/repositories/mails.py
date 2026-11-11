"""Module de gestion des mails dans le dépôt Alertiny.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import Sequence, Any

from sqlalchemy import select
from jinja2 import Template

from params.application import SessionDep
from models.db.mails import Mail
from models.pydantics.mails import MailIncoming

class MailsRepository:
    """Dépôt pour la gestion des mails."""
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    def get_mails(self) -> Sequence[Mail]:
        """Récupère la liste des mails."""
        stmt = select(Mail)
        result = self.session.execute(stmt)
        return result.scalars().all()

    def get_mail_by_id(self, mail_id: str) -> Mail | None:
        """Récupère un mail par son identifiant."""
        stmt = select(Mail).where(Mail.id == mail_id)
        result = self.session.execute(stmt)
        return result.scalars().first()

    def get_mail_by(self, attribut: str, *, value: Any) -> Mail | None:
        """Récupère un mail par un attribut spécifique."""
        stmt = select(Mail).where(getattr(Mail, attribut) == value)
        result = self.session.execute(stmt)
        return result.scalars().first()

    def create_mail(self, *, mail: MailIncoming) -> Mail:
        """Crée un nouveau mail."""
        mail = Mail.from_incoming(mail)
        self.session.add(mail)
        self.session.commit()
        return mail

    def generate_mail(self, *, mail: MailIncoming) -> str:
        """Génère un mail et l'ajoute à la base de données et retourne le contenu généré."""
        mail_instance = Mail.from_incoming(mail)
        self.session.add(mail_instance)
        self.session.commit()
        template = Template(mail.template)
        return template.render(**{j.key: j.value for j in mail.jinja_values})

    def send_mail(self, *, mail: Mail) -> None:
        """Envoie un mail."""
        # Implémentation de l'envoi de mail ici TODO
        pass
