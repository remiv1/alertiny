"""Initialisation du module de modélisation des données liées aux mails et aux statuts.

.. module_author:: Rémi Verschuur rverschuur@audit-io.fr
.. version:: 1.0.0
"""
from __future__ import annotations

from .mails import Mail
from .status import Status

__all__ = [
    "Mail",
    "Status",
]
