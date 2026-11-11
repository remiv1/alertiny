"""Module de sécurité de base pour la gestion des jetons bearer.

Ce module fournit des fonctions pour vérifier la validité des jetons bearer
dans les requêtes HTTP entrantes.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import os
import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(auto_error=False)

def verify_bearer_token(
	credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    """Vérifie la validité du jeton bearer dans la requête entrante.
    
    :param credentials: Les informations d'autorisation HTTP extraites de la requête.
    :type credentials: HTTPAuthorizationCredentials | None

    :raises HTTPException: Si le jeton bearer est invalide ou manquant.
    """
    expected_token = os.getenv("ALERTINY_BEARER_TOKEN")
    if not expected_token:
        raise HTTPException(status_code=503, detail="Le jeton d'API n'est pas configuré")
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not secrets.compare_digest(credentials.credentials, expected_token)
    ):
        raise HTTPException(
            status_code=401,
            detail="Jeton bearer invalide ou manquant",
            headers={"WWW-Authenticate": "Bearer"},
        )
