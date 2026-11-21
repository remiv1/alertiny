"""Module de gestion du worker dans le dépôt Alertiny.

Ce module fournit la classe `WorkerRepo` qui encapsule la logique de gestion des workers
et fournit les méthodes pour interagir avec ces workers.

.. classes::
    - `WorkerRepo` : Représente le dépôt pour la gestion des workers.

.. responsabilité : métier

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

class WorkerRepo:
    """Classe représentant le dépôt pour la gestion des workers dans Alertiny."""

    def __init__(self) -> None:
        """Initialise le dépôt des workers."""
        self.workers: list[str] = []

    def launch_task_now(self, task_name: str) -> None:
        """Lance immédiatement une tâche pour le worker spécifié.

        :param task_name: Nom de la tâche à lancer.
        :type task_name: str
        """
        raise NotImplementedError("La méthode launch_task_now doit être implémentée.")

    def get_tasks(self) -> list[str]:
        """Retourne la liste des tâches actuellement enregistrées pour le worker.

        :return: Liste des noms de tâches.
        :rtype: list[str]
        """
        raise NotImplementedError("La méthode get_tasks doit être implémentée.")
