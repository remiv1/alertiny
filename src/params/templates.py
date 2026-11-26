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

from models.pydantics.templates import TemplatesConfig

CONFIG_PATH = Path("/etc/alertiny/templates.yaml")
LOCAL_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "templates.yaml"
LOCAL_TEMPLATES_PATH = Path(__file__).resolve().parents[1] / "templates"

def load_templates_config(path: Path | None = None) -> TemplatesConfig:
    """Charge et valide la déclaration des templates.

    :param path: Chemin explicite vers le fichier YAML. Si sa valeur est ``None``,
        le fichier ``/etc/alertiny/templates.yaml`` est utilisé lorsqu'il existe,
        sinon le fichier local ``src/config/templates.yaml``.
    :type path: pathlib.Path | None
    :returns: Configuration validée des templates et de leur répertoire.
    :rtype: models.pydantics.templates.TemplatesConfig
    :raises OSError: Si le fichier de configuration ne peut pas être lu.
    :raises pydantic.ValidationError: Si le contenu ne respecte pas le schéma attendu.
    :raises yaml.YAMLError: Si le document YAML est mal formé.
    """
    if path is None:
        path = CONFIG_PATH if CONFIG_PATH.exists() else LOCAL_CONFIG_PATH
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return TemplatesConfig(**data)


def get_templates_directory(configured_path: str) -> Path:
    """Résout le répertoire des fichiers HTML de templates.

    Le chemin configuré est utilisé s'il désigne un répertoire existant. En
    développement local, le chemin du paquet ``src/templates`` sert de repli.

    :param configured_path: Répertoire déclaré dans ``templates.yaml``.
    :type configured_path: str
    :returns: Chemin absolu du répertoire des templates disponible.
    :rtype: pathlib.Path
    """
    directory = Path(configured_path)
    if directory.is_dir():
        return directory
    return LOCAL_TEMPLATES_PATH
