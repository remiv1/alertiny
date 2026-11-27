"""Configuration et fixtures isolées pour les tests du projet."""

import asyncio
import json
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.types import Message

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


@pytest.fixture
def isolated_session() -> Iterator[Session]:
    """Fournit une session SQLAlchemy isolée pour les tests."""
    from models.db._common import Base # pylint: disable=C0415

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


@pytest.fixture
def isolated_mail_config() -> Any:
    """Fournit une configuration de mail isolée pour les tests."""
    from params.mails import IMAPConfig, MailConfig, SMTPConfig # pylint: disable=C0415

    return MailConfig(
        sender="alerts@example.com",
        smtp=SMTPConfig("smtp.example.com", 587, False, True),
        retries=1,
        imap=IMAPConfig(True, "imap.example.com", 993, True, False, "Sent"),
    )


@pytest.fixture
def mail_payload() -> dict[str, Any]:
    """Fournit un payload de mail pour les tests."""
    return {
        "sender": "alerts@example.com",
        "template": "service_down.html",
        "jinja_values": [
            {"key": "service", "value": "API"},
            {"key": "hostname", "value": "host-01"},
        ],
        "recipient": [{"email": "ops@example.com"}],
    }


class HTTPResult(NamedTuple):
    """Représente le résultat d'une requête HTTP simulée."""
    status: int
    body: Any
    headers: dict[str, str]


@pytest.fixture
def http_request(
    isolated_session: Session, # pylint: disable=W0621
    isolated_mail_config: Any, # pylint: disable=W0621
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., HTTPResult]:
    """Fournit une fonction simulant des requêtes HTTP vers l'application."""
    from application import get_app # pylint: disable=C0415
    from params.database import get_session # pylint: disable=C0415
    from repositories.mails import repo # pylint: disable=C0415

    monkeypatch.setenv("ALERTINY_BEARER_TOKEN", "test-token")
    monkeypatch.setattr(repo, "load_mail_config", lambda: isolated_mail_config)
    app = get_app()
    app.dependency_overrides[get_session] = lambda: isolated_session

    def request(
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        token: str | None = "test-token",
    ) -> HTTPResult:
        body = json.dumps(payload).encode() if payload is not None else b""
        headers = [(b"content-type", b"application/json")]
        if token is not None:
            headers.append((b"authorization", f"Bearer {token}".encode()))
        scope: dict[str, Any] = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": path,
            "raw_path": path.encode(), "query_string": b"", "headers": headers,
            "server": ("testserver", 80), "client": ("testclient", 1234),
            "root_path": "",
        }
        events: list[Message] = []
        received = False

        async def receive() -> dict[str, Any]:
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(event: Message) -> None:
            events.append(event)

        asyncio.run(app(scope, receive, send))
        start = next(event for event in events if event["type"] == "http.response.start")
        response_body = b"".join(
            event.get("body", b"") for event in events if event["type"] == "http.response.body"
        )
        response_headers = {
            key.decode().lower(): value.decode() for key, value in start["headers"]
        }
        return HTTPResult(start["status"], json.loads(response_body), response_headers)

    return request
