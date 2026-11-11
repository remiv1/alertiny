"""Paramètres de configuration de l'application Alertiny.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import Annotated
from sqlalchemy.orm import Session

from fastapi import Depends
from .database import get_session

SessionDep = Annotated[Session, Depends(get_session)]
