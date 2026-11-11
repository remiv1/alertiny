"""Scheduler entry point for TTL-LAMa.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import logging
from datetime import timezone

from apscheduler.schedulers.blocking import BlockingScheduler


logger = logging.getLogger(__name__)


def _reconcile_on_startup() -> bool:
    """Retry startup reconciliation and trigger configured panic actions on failure.

    :returns: Whether reconciliation succeeded.
    :rtype: bool
    """
    raise NotImplementedError("Startup reconciliation is not implemented.")


def main() -> None:
    """Main entry point for the TTL-LAMa scheduler."""
    scheduler = BlockingScheduler(timezone=timezone.utc)
    #_reconcile_on_startup()
    scheduler.start()   # type: ignore


if __name__ == "__main__":
    main()
