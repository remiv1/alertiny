"""Module v1 de l'API Alertiny.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from fastapi import APIRouter

from .v1 import router as v1_router

router = APIRouter(prefix="/api", tags=["api"])
router.include_router(v1_router)
