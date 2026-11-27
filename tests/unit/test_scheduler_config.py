"""Tests du scheduler et du chargement de la configuration mail."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy.orm import Session

from params.mails import MailConfig, load_mail_config
from scheduler import main as scheduler


def test_scheduler_registers_single_non_overlapping_polling_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teste que le scheduler enregistre un job de polling unique et non chevauchant."""
    calls: list[tuple[str, Any]] = []

    class FakeScheduler:
        """Simule un scheduler pour tester l'enregistrement des jobs."""
        def __init__(self, **kwargs: Any) -> None:
            calls.append(("init", kwargs))

        def add_job(self, function: Any, **kwargs: Any) -> None:
            """Simule l'ajout d'un job au scheduler."""
            calls.append(("job", (function, kwargs)))

        def start(self) -> None:
            """Simule le démarrage du scheduler."""
            calls.append(("start", None))

    monkeypatch.setattr(
        scheduler,
        "_reconcile_on_startup",
        lambda: calls.append(("reconcile", None)),
    )
    monkeypatch.setattr(scheduler, "BlockingScheduler", FakeScheduler)
    scheduler.main()

    assert [name for name, _ in calls] == ["reconcile", "init", "job", "start"]
    function, options = calls[2][1]
    assert function is getattr(scheduler, "_process_due_mails")
    assert options["seconds"] == 1
    assert options["max_instances"] == 1
    assert options["coalesce"] is True


def test_scheduler_initializes_and_delegates_to_worker(
    isolated_session: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teste que le scheduler initialise la base de données et délègue au worker."""
    calls: list[str] = []

    @contextmanager
    def fake_session() -> Generator[Session, None, None]:
        """Simule l'ouverture et la fermeture d'une session de base de données."""
        calls.append("open")
        yield isolated_session
        calls.append("close")

    class FakeWorker:
        """Simule un worker pour tester la délégation des tâches."""
        def __init__(self, session: Session) -> None:
            assert session is isolated_session

        def reconcile(self) -> int:
            """Simule la réconciliation des mails dus."""
            calls.append("reconcile")
            return 2

        def run_once(self) -> int:
            """Simule l'exécution d'un cycle unique du worker."""
            calls.append("run")
            return 1

    monkeypatch.setattr(scheduler, "session", fake_session)
    monkeypatch.setattr(scheduler, "MailWorker", FakeWorker)
    monkeypatch.setattr(scheduler, "initialize_database", lambda: calls.append("init"))
    reconcile = getattr(scheduler, "_reconcile_on_startup")
    process_due = getattr(scheduler, "_process_due_mails")
    assert reconcile() == 2
    process_due()
    assert calls == ["init", "open", "reconcile", "close", "open", "run", "close"]


@pytest.mark.parametrize("protocol", ["smtp", "imap"])
@pytest.mark.parametrize("tls,starttls", [(False, False), (True, True), ("false", False)])
def test_config_file_rejects_invalid_transport_security(
    tmp_path: Path, protocol: str, tls: object, starttls: object,
) -> None:
    """Teste que le fichier de configuration rejette une sécurité de transport invalide."""
    config: dict[str, Any] = {
        "mail": {
            "from": "alerts@example.com",
            "smtp": {"server": "smtp.example.com", "port": 465, "tls": True, "starttls": False},
            "imap": {"copy_to_sent": True, "server": "imap.example.com", "port": 993,
                     "tls": True, "starttls": False, "folder": "Sent"},
            "retries": 1,
        },
    }
    config["mail"][protocol]["tls"] = tls
    config["mail"][protocol]["starttls"] = starttls
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one of tls or starttls"):
        load_mail_config(path)


def test_config_loads_credentials_and_imap_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teste que le fichier de configuration charge correctement les identifiants et le fallback
    IMAP.
    """
    config = {
        "mail": {
            "from": "alerts@example.com",
            "smtp": {"server": "smtp.example.com", "port": 587, "tls": False, "starttls": True},
            "imap": {"copy_to_sent": True, "server": "imap.example.com", "port": 993,
                     "tls": True, "starttls": False, "folder": "Sent"},
            "retries": 1,
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setenv("SMTP_USERNAME", "test-user")
    monkeypatch.setenv("SMTP_PASSWORD", "test-password")
    monkeypatch.delenv("IMAP_USERNAME", raising=False)
    monkeypatch.delenv("IMAP_PASSWORD", raising=False)
    loaded: MailConfig = load_mail_config(path)
    assert loaded.imap.username == loaded.smtp.username == "test-user"
    assert loaded.imap.password == loaded.smtp.password == "test-password"
