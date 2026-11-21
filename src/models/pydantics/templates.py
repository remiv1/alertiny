"""Modèles Pydantic pour les templates de l'application.

.. classes::
    - `Variable`: Modèle pour une variable dans un template.
    - `Template`: Modèle pour un template.
    - `TemplatesConfig`: Configuration des templates.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from pydantic import BaseModel

class Variable(BaseModel):
    """Représente une variable dans un template.

    :param required: Indique si la variable est requise.
    :type required: bool
    :param type: Le type de la variable.
    :type type: str
    """
    required: bool
    type: str

class Template(BaseModel):
    """Représente un template dans l'application.

    :param name: Le nom du template.
    :type name: str
    :param subject: L'objet du mail pour le template.
    :type subject: str
    :param template: Le contenu du template.
    :type template: str
    :param variables: Les variables associées au template.
    :type variables: dict[str, Variable]

    .. methods::
        - `required_variables`: Retourne la liste des variables requises.
        - `optional_variables`: Retourne la liste des variables optionnelles.
        - `is_valid`: Vérifie si les variables fournies sont valides pour le template.
    """
    name: str
    subject: str
    template: str
    variables: dict[str, Variable]

    def required_variables(self) -> set[str]:
        """Retourne la liste des variables requises dans le template.

        :return: La liste des variables requises.
        :rtype: set[str]
        """
        return {
            name
            for name, variable in self.variables.items()
            if variable.required
        }

    def optional_variables(self) -> set[str]:
        """Retourne la liste des variables optionnelles dans le template.

        :return: La liste des variables optionnelles.
        :rtype: set[str]
        """
        return {
            name
            for name, variable in self.variables.items()
            if not variable.required
        }

    def is_valid(self, provided_variables: set[str]) -> bool:
        """Vérifie si les variables fournies sont valides pour le template.

        :param provided_variables: Les variables fournies pour le template.
        :type provided_variables: set[str]

        :return: True si les variables sont valides, False sinon.
        :rtype: bool
        """
        required = self.required_variables()
        return not required - provided_variables

class TemplatesConfig(BaseModel):
    """Représente la configuration des templates dans l'application.

    :param template_folder: Le dossier contenant les templates.
    :type template_folder: str
    :param templates: La liste des templates.
    :type templates: list[Template]
    """
    template_folder: str
    templates: list[Template]
