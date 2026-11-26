"""Schémas Pydantic de déclaration des templates de notification.

Les modèles décrivent le manifeste YAML chargé par
:func:`params.templates.load_templates_config`. Chaque entrée associe un nom logique,
un sujet, un fichier HTML et les variables attendues. Les méthodes de :class:`Template`
permettent de séparer les variables requises des variables optionnelles et de vérifier
qu'une requête fournit les champs requis.

.. classes::
    - :class:`Variable` : règle de validation d'une variable.
    - :class:`Template` : configuration d'un template individuel.
    - :class:`TemplatesConfig` : configuration globale des templates.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from pydantic import BaseModel

class Variable(BaseModel):
    """Déclare les contraintes minimales d'une variable Jinja.

    :param required: Indique si la valeur doit être fournie lors de la création du mail.
    :type required: bool
    :param type: Nom du type attendu par le manifeste, par exemple ``str``.
    :type type: str

    Le type est conservé comme métadonnée de configuration; la validation d'exécution
    du contrat V1 vérifie principalement la présence des variables requises.
    """
    required: bool
    type: str

class Template(BaseModel):
    """Configuration d'un template d'e-mail autorisé.

    :param name: Identifiant logique utilisé par l'API.
    :type name: str
    :param subject: Sujet Jinja par défaut.
    :type subject: str
    :param template: Nom du fichier HTML situé dans le répertoire configuré.
    :type template: str
    :param variables: Variables déclarées et contraintes associées.
    :type variables: dict[str, Variable]
    """
    name: str
    subject: str
    template: str
    variables: dict[str, Variable]

    def required_variables(self) -> set[str]:
        """Retourne les noms des variables marquées comme obligatoires.

        :returns: Ensemble des noms de variables requises par ce template.
        :rtype: set[str]
        """
        return {
            name
            for name, variable in self.variables.items()
            if variable.required
        }

    def optional_variables(self) -> set[str]:
        """Retourne les noms des variables marquées comme optionnelles.

        :returns: Ensemble des noms de variables facultatives.
        :rtype: set[str]
        """
        return {
            name
            for name, variable in self.variables.items()
            if not variable.required
        }

    def is_valid(self, provided_variables: set[str]) -> bool:
        """Vérifie la présence de toutes les variables obligatoires.

        :param provided_variables: Noms des variables fournies par la requête.
        :type provided_variables: set[str]
        :returns: ``True`` si chaque variable obligatoire est présente; ``False`` sinon.
        :rtype: bool
        """
        required = self.required_variables()
        return not required - provided_variables

class TemplatesConfig(BaseModel):
    """Manifeste complet des templates disponibles pour la V1.

    :param template_folder: Répertoire contenant les fichiers HTML déclarés.
    :type template_folder: str
    :param templates: Liste des templates accessibles à l'API.
    :type templates: list[Template]
    """
    template_folder: str
    templates: list[Template]
