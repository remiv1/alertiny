"""Modèles Pydantic pour les templates de l'application.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from pydantic import BaseModel

class Variable(BaseModel):
    """Représente une variable dans un template."""
    required: bool
    type: str

class Template(BaseModel):
    """Représente un template dans l'application."""
    name: str
    subject: str
    template: str
    variables: dict[str, Variable]

    def required_variables(self) -> set[str]:
        """Retourne la liste des variables requises dans le template."""
        return {
            name
            for name, variable in self.variables.items()
            if variable.required
        }

    def optional_variables(self) -> set[str]:
        """Retourne la liste des variables optionnelles dans le template."""
        return {
            name
            for name, variable in self.variables.items()
            if not variable.required
        }

    def is_valid(self, provided_variables: set[str]) -> bool:
        """Vérifie si les variables fournies sont valides pour le template."""
        required = self.required_variables()
        return not required - provided_variables

class TemplatesConfig(BaseModel):
    """Représente la configuration des templates dans l'application."""
    template_folder: str
    templates: list[Template]
