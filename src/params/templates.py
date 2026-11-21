"""Module de gestion des templates dans l'application Alertiny.

.. functions::
    - `load_templates_config`: Charge la configuration des templates depuis le fichier YAML.

.. responsibility : configuration

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ..models.pydantics.templates import TemplatesConfig

CONFIG_PATH = Path("/") / "etc" / "alertiny" / "templates"

def load_templates_config(path: Path = CONFIG_PATH) -> TemplatesConfig:
    """Charge la configuration des templates depuis le fichier YAML.

    :param path: Chemin vers le dossier contenant le fichier de configuration YAML.
    :type path: Path

    :return: Configuration des templates.
    :rtype: TemplatesConfig
    """
    with open(path / "templates.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return TemplatesConfig(**data)
