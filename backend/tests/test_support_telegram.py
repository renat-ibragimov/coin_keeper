from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail.base import EmailMessage
from app.models import SupportTicket
from tests.conftest import (
    SUPPORT_SETUP_SECRET,
    SUPPORT_WEBHOOK_SECRET,
    RecordingSupportTelegram,
)
from tests.helpers import register_and_verify

pytestmark = pytest.mark.asyncio

WEBHOOK = "/api/v1/support/telegram/webhook"
HEADERS = {"X-Telegram-Bot-Api-Secret-Token": SUPPORT_WEBHOOK_SECRET}
GROUP_ID = -100123456
USER_CHAT_ID = 7654


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def private_message(text: str, message_id: int = 1) -> dict[str, object]:
    return {
        "message": {
            "message_id": message_id,
            "chat": {"id": USER_CHAT_ID, "type": "private"},
            "from": {
                "id": USER_CHAT_ID,
                "is_bot": False,
                "first_name": "Іван",
                "username": "ivan_coin",
                "language_code": "uk",
            },
            "text": text,
        }
    }


async def setup_group(client: AsyncClient) -> None:
    response = await client.post(
        WEBHOOK,
        headers=HEADERS,
        json={
            "message": {
                "message_id": 10,
                "chat": {"id": GROUP_ID, "type": "supergroup", "is_forum": True},
                "from": {"id": 42, "is_bot": False},
                "text": f"/setup {SUPPORT_SETUP_SECRET}",
            }
        },
    )
    assert response.status_code == 200


async def test_public_and_account_link(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    public = await client.get("/api/v1/support/telegram")
    assert public.json() == {"url": "https://t.me/bakost_support_test_bot"}

    _, token = await register_and_verify(client, mail_outbox)
    linked = await client.post(
        "/api/v1/support/telegram/link",
        headers=auth(token),
        json={"sourcePath": "/collection/coins?page=2"},
    )
    assert linked.status_code == 200
    assert linked.json()["url"].startswith("https://t.me/bakost_support_test_bot?start=")


async def test_setup_then_anonymous_message_creates_topic_and_relays(
    client: AsyncClient, support_telegram: RecordingSupportTelegram
) -> None:
    await setup_group(client)
    assert support_telegram.sent[-1][0] == GROUP_ID

    await client.post(WEBHOOK, headers=HEADERS, json=private_message("Потрібна допомога"))

    assert support_telegram.created[0][0] == GROUP_ID
    assert support_telegram.created[0][1].startswith("#1 · Іван")
    assert support_telegram.copied == [(USER_CHAT_ID, 1, GROUP_ID, 1001)]
    assert support_telegram.sent[-1][0] == USER_CHAT_ID


async def test_account_start_adds_identity_and_source_page(
    client: AsyncClient,
    mail_outbox: list[EmailMessage],
    support_telegram: RecordingSupportTelegram,
) -> None:
    await setup_group(client)
    email, access = await register_and_verify(client, mail_outbox)
    linked = await client.post(
        "/api/v1/support/telegram/link",
        headers=auth(access),
        json={"sourcePath": "/catalog/99"},
    )
    code = linked.json()["url"].split("start=", 1)[1]

    await client.post(WEBHOOK, headers=HEADERS, json=private_message(f"/start {code}"))

    header = next(
        text for chat, text, thread, _ in support_telegram.sent if chat == GROUP_ID and thread
    )
    assert email in header
    assert "Сторінка: /catalog/99" in header
    assert "User ID:" in header


async def test_admin_topic_reply_and_close_are_relayed(
    client: AsyncClient,
    db_session: AsyncSession,
    support_telegram: RecordingSupportTelegram,
) -> None:
    await setup_group(client)
    await client.post(WEBHOOK, headers=HEADERS, json=private_message("Питання"))
    ticket = (await db_session.execute(select(SupportTicket))).scalar_one()
    support_telegram.copied.clear()

    reply = {
        "message": {
            "message_id": 55,
            "message_thread_id": 1001,
            "chat": {"id": GROUP_ID, "type": "supergroup", "is_forum": True},
            "from": {"id": 42, "is_bot": False},
            "text": "Відповідь адміністратора",
        }
    }
    await client.post(WEBHOOK, headers=HEADERS, json=reply)
    assert support_telegram.copied == [(GROUP_ID, 55, USER_CHAT_ID, None)]

    callback = {
        "callback_query": {
            "id": "callback-1",
            "from": {"id": 42, "is_bot": False},
            "data": f"support:close:{ticket.id}",
            "message": {
                "message_id": 11,
                "message_thread_id": 1001,
                "chat": {"id": GROUP_ID, "type": "supergroup"},
            },
        }
    }
    await client.post(WEBHOOK, headers=HEADERS, json=callback)
    await db_session.refresh(ticket)
    assert ticket.status == "closed"
    assert support_telegram.closed == [(GROUP_ID, 1001)]
    assert support_telegram.callbacks == [("callback-1", "Звернення закрито")]


async def test_webhook_rejects_wrong_secret(client: AsyncClient) -> None:
    response = await client.post(WEBHOOK, json=private_message("hello"))
    assert response.status_code == 403
