"""Telegram notice when a new user's account becomes real (docs/13-admin.md, part 3).

Fired at verification, not at registration: an unconfirmed or bot-filled
address never reaches a linked admin chat, only a person who finished signing
up does.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.mail.base import EmailMessage
from app.services.google_auth import GoogleClaims, GoogleOAuth
from tests.conftest import WEBHOOK_SECRET, RecordingTelegramSender
from tests.helpers import register_and_verify, unique_email
from tests.seed import promote_to_admin

pytestmark = pytest.mark.asyncio

WEBHOOK = "/api/v1/telegram/webhook"
SECRET_HEADERS = {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}
CHAT_ID = 900100


async def _link_admin_chat(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list[EmailMessage]
) -> None:
    """Register an admin and connect a chat, the way a person would."""
    email, token = await register_and_verify(client, mail_outbox)
    await promote_to_admin(db_session, email)
    link = await client.post(
        "/api/v1/admin/telegram/link", headers={"Authorization": f"Bearer {token}"}
    )
    assert link.status_code == 200, link.text
    code = link.json()["url"].split("start=", 1)[1]
    started = await client.post(
        WEBHOOK,
        json={
            "message": {
                "chat": {"id": CHAT_ID, "type": "private"},
                "from": {"id": CHAT_ID, "is_bot": False},
                "text": f"/start {code}",
            }
        },
        headers=SECRET_HEADERS,
    )
    assert started.status_code == 200


async def test_verifying_email_notifies_linked_admins(
    client: AsyncClient,
    db_session: AsyncSession,
    mail_outbox: list[EmailMessage],
    telegram_sender: RecordingTelegramSender,
) -> None:
    await _link_admin_chat(client, db_session, mail_outbox)
    telegram_sender.sent.clear()  # drop the "link confirmed" message

    new_email, _ = await register_and_verify(client, mail_outbox)

    assert len(telegram_sender.sent) == 1
    sent = telegram_sender.sent[0]
    assert sent.chat_id == CHAT_ID
    assert sent.text.startswith("🆕")
    assert new_email in sent.text


async def test_no_linked_chat_sends_nothing(
    client: AsyncClient,
    mail_outbox: list[EmailMessage],
    telegram_sender: RecordingTelegramSender,
) -> None:
    await register_and_verify(client, mail_outbox)
    assert telegram_sender.sent == []


async def test_registration_alone_notifies_nobody(
    client: AsyncClient,
    db_session: AsyncSession,
    mail_outbox: list[EmailMessage],
    telegram_sender: RecordingTelegramSender,
) -> None:
    """An address that never confirms must not reach the admin chat."""
    await _link_admin_chat(client, db_session, mail_outbox)
    telegram_sender.sent.clear()

    response = await client.post(
        "/api/v1/auth/register", json={"email": unique_email(), "password": "correct horse battery"}
    )
    assert response.status_code == 202
    assert telegram_sender.sent == []


async def test_google_signup_notifies_linked_admins(
    client: AsyncClient,
    db_session: AsyncSession,
    mail_outbox: list[EmailMessage],
    telegram_sender: RecordingTelegramSender,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Google path that activates a brand-new user immediately."""
    await _link_admin_chat(client, db_session, mail_outbox)
    telegram_sender.sent.clear()

    settings = get_settings()
    monkeypatch.setattr(settings, "google_client_id", "test-google-client")
    monkeypatch.setattr(settings, "google_client_secret", "test-google-secret")
    email = f"google-{unique_email().split('@')[0]}@gmail.com"

    async def fake_exchange(self: GoogleOAuth, *, code: str, flow: object) -> GoogleClaims:
        return GoogleClaims(
            subject="google-sub-notify",
            email=email,
            name="Google Person",
            google_controls_email=True,
        )

    monkeypatch.setattr(GoogleOAuth, "exchange", fake_exchange)

    start = await client.get("/api/v1/auth/google/start")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    callback = await client.get(
        "/api/v1/auth/google/callback", params={"state": state, "code": "test-code"}
    )
    assert callback.status_code == 303

    assert len(telegram_sender.sent) == 1
    assert email in telegram_sender.sent[0].text
