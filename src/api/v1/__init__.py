"""Module v1 de l'API Alertiny.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from fastapi import APIRouter

from .mails import router as mails_router

router = APIRouter(prefix="/v1", tags=["v1"])
router.include_router(mails_router)
