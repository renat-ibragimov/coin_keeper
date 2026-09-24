"""The admin bot: linking a chat, the webhook, and reports going out.

The security story is the point of most of these (docs/admin.md, "Access rules"):
anyone can find the bot and press Start, so what matters is that nothing
happens without a one-time code issued to a signed-in administrator.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail.base import EmailMessage
from app.models import User
from tests.conftest import JOB_TOKEN, WEBHOOK_SECRET, RecordingTelegramSender
from tests.helpers import register_and_verify
from tests.seed import promote_to_admin

pytestmark = pytest.mark.asyncio

WEBHOOK = "/api/v1/telegram/webhook"
REPORT = "/api/v1/internal/job-runs"
JOB_HEADERS = {"X-Job-Token": JOB_TOKEN}
SECRET_HEADERS = {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}
CHAT_ID = 100500


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def start_update(code: str, chat_id: int = CHAT_ID) -> dict[str, object]:
    return message_update(f"/start {code}", chat_id)


def message_update(command: str, chat_id: int = CHAT_ID) -> dict[str, object]:
    return {
        "message": {
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "is_bot": False},
            "text": command,
        }
    }


@pytest.fixture
async def admin_token(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list[EmailMessage]
) -> str:
    email, token = await register_and_verify(client, mail_outbox)
    await promote_to_admin(db_session, email)
    return token


async def link_code(client: AsyncClient, token: str) -> str:
    response = await client.post("/api/v1/admin/telegram/link", headers=auth(token))
    assert response.status_code == 200, response.text
    url: str = response.json()["url"]
    return url.split("start=", 1)[1]


async def test_an_admin_connects_a_chat_by_pressing_start(
    client: AsyncClient, admin_token: str, telegram_sender: RecordingTelegramSender
) -> None:
    code = await link_code(client, admin_token)

    response = await client.post(WEBHOOK, json=start_update(code), headers=SECRET_HEADERS)
    assert response.status_code == 200

    status = await client.get("/api/v1/admin/telegram", headers=auth(admin_token))
    assert status.json() == {"connected": True, "chats": 1}
    assert "Готово" in telegram_sender.sent[-1].text


async def test_start_without_a_code_does_nothing(
    client: AsyncClient, telegram_sender: RecordingTelegramSender
) -> None:
    """A stranger who found the bot and pressed Start. Silence, not a refusal:
    an answer would confirm the bot is listening."""
    response = await client.post(
        WEBHOOK,
        json=message_update("/start", 777),
        headers=SECRET_HEADERS,
    )
    assert response.status_code == 200
    assert telegram_sender.sent == []


async def test_an_invented_code_does_nothing(
    client: AsyncClient, telegram_sender: RecordingTelegramSender
) -> None:
    response = await client.post(
        WEBHOOK, json=start_update("not-a-real-code"), headers=SECRET_HEADERS
    )
    assert response.status_code == 200
    assert telegram_sender.sent == []


async def test_a_code_works_once(
    client: AsyncClient, admin_token: str, telegram_sender: RecordingTelegramSender
) -> None:
    code = await link_code(client, admin_token)
    await client.post(WEBHOOK, json=start_update(code), headers=SECRET_HEADERS)
    telegram_sender.sent.clear()

    await client.post(WEBHOOK, json=start_update(code, chat_id=999), headers=SECRET_HEADERS)
    assert telegram_sender.sent == []


async def test_a_code_issued_to_a_non_admin_does_nothing(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_token: str,
    telegram_sender: RecordingTelegramSender,
) -> None:
    """The role can be taken away between issuing the code and pressing Start."""
    code = await link_code(client, admin_token)
    await db_session.execute(text("UPDATE users SET role = 'user'"))
    await db_session.commit()

    await client.post(WEBHOOK, json=start_update(code), headers=SECRET_HEADERS)
    assert telegram_sender.sent == []


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="no-secret"),
        pytest.param({"X-Telegram-Bot-Api-Secret-Token": "wrong"}, id="wrong-secret"),
    ],
)
async def test_the_webhook_checks_its_secret(
    client: AsyncClient, headers: dict[str, str], telegram_sender: RecordingTelegramSender
) -> None:
    response = await client.post(WEBHOOK, json=start_update("whatever"), headers=headers)
    assert response.status_code == 403
    assert telegram_sender.sent == []


async def test_a_regular_user_cannot_ask_for_a_link(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    _, token = await register_and_verify(client, mail_outbox)
    response = await client.post("/api/v1/admin/telegram/link", headers=auth(token))
    assert response.status_code == 403


async def test_unlinking_stops_the_reports(
    client: AsyncClient, admin_token: str, telegram_sender: RecordingTelegramSender
) -> None:
    code = await link_code(client, admin_token)
    await client.post(WEBHOOK, json=start_update(code), headers=SECRET_HEADERS)

    removed = await client.delete("/api/v1/admin/telegram", headers=auth(admin_token))
    assert removed.status_code == 204

    status = await client.get("/api/v1/admin/telegram", headers=auth(admin_token))
    assert status.json() == {"connected": False, "chats": 0}


async def test_a_finished_run_reaches_the_chat(
    client: AsyncClient, admin_token: str, telegram_sender: RecordingTelegramSender
) -> None:
    code = await link_code(client, admin_token)
    await client.post(WEBHOOK, json=start_update(code), headers=SECRET_HEADERS)
    telegram_sender.sent.clear()

    opened = await client.post(REPORT, json={"job": "update-prices"}, headers=JOB_HEADERS)
    assert telegram_sender.sent == [], "an opening report is not worth a message"

    await client.patch(
        f"{REPORT}/{opened.json()['id']}",
        json={
            "status": "ok",
            "summary": "update-prices ok series=8 scope=325",
            "stats": {"country": "Україна", "series": 8, "scope": 325, "inserted": 321},
            "exitCode": 0,
        },
        headers=JOB_HEADERS,
    )

    assert len(telegram_sender.sent) == 1
    text_sent = telegram_sender.sent[0].text
    assert "усе гаразд" in text_sent
    assert "8 серій" in text_sent
    assert "325 монет" in text_sent
    assert "321 ціну" in text_sent


async def test_a_failed_run_explains_itself(
    client: AsyncClient, admin_token: str, telegram_sender: RecordingTelegramSender
) -> None:
    code = await link_code(client, admin_token)
    await client.post(WEBHOOK, json=start_update(code), headers=SECRET_HEADERS)
    telegram_sender.sent.clear()

    await client.post(
        REPORT,
        json={
            "job": "update-prices",
            "status": "failed",
            "summary": "update-prices failed errors=1",
            "details": "reading the catalog: connection refused",
            "exitCode": 2,
        },
        headers=JOB_HEADERS,
    )

    assert len(telegram_sender.sent) == 1
    assert "не вдалося" in telegram_sender.sent[0].text
    assert "connection refused" in telegram_sender.sent[0].text


async def test_last_answers_a_linked_chat_only(
    client: AsyncClient, admin_token: str, telegram_sender: RecordingTelegramSender
) -> None:
    code = await link_code(client, admin_token)
    await client.post(WEBHOOK, json=start_update(code), headers=SECRET_HEADERS)
    await client.post(
        REPORT,
        json={"job": "update-prices", "status": "ok", "summary": "update-prices ok"},
        headers=JOB_HEADERS,
    )
    telegram_sender.sent.clear()

    stranger = await client.post(
        WEBHOOK,
        json=message_update("/last", 4242),
        headers=SECRET_HEADERS,
    )
    assert stranger.status_code == 200
    assert telegram_sender.sent == []

    await client.post(
        WEBHOOK,
        json=message_update("/last"),
        headers=SECRET_HEADERS,
    )
    assert len(telegram_sender.sent) == 1
    assert "Оновлення цін" in telegram_sender.sent[0].text


@pytest.mark.parametrize(
    "change", [{"role": "user"}, {"is_active": False}, {"email_verified": False}]
)
async def test_revoked_admin_cannot_link_read_or_receive(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_token: str,
    telegram_sender: RecordingTelegramSender,
    change: dict[str, str | bool],
) -> None:
    code = await link_code(client, admin_token)
    await client.post(WEBHOOK, json=start_update(code), headers=SECRET_HEADERS)
    pending_code = await link_code(client, admin_token)
    await db_session.execute(update(User).values(**change))
    await db_session.commit()
    telegram_sender.sent.clear()

    await client.post(WEBHOOK, json=message_update("/last"), headers=SECRET_HEADERS)
    await client.post(WEBHOOK, json=start_update(pending_code, 999), headers=SECRET_HEADERS)
    await client.post(REPORT, json={"job": "update-prices", "status": "ok"}, headers=JOB_HEADERS)
    assert telegram_sender.sent == []


@pytest.mark.parametrize(
    "command", ["/start", "/last", "/help", "/status", "hello", "/last@admin_bot"]
)
async def test_stranger_commands_never_disclose_information(
    client: AsyncClient, telegram_sender: RecordingTelegramSender, command: str
) -> None:
    response = await client.post(WEBHOOK, json=message_update(command, 777), headers=SECRET_HEADERS)
    assert response.status_code == 200
    assert telegram_sender.sent == []


@pytest.mark.parametrize("chat_type", ["group", "supergroup", "channel"])
async def test_group_cannot_consume_link_code(
    client: AsyncClient,
    admin_token: str,
    telegram_sender: RecordingTelegramSender,
    chat_type: str,
) -> None:
    code = await link_code(client, admin_token)
    await client.post(
        WEBHOOK,
        json={
            "message": {
                "chat": {"id": -100500, "type": chat_type},
                "from": {"id": CHAT_ID, "is_bot": False},
                "text": f"/start {code}",
            }
        },
        headers=SECRET_HEADERS,
    )
    assert telegram_sender.sent == []
    await client.post(WEBHOOK, json=start_update(code), headers=SECRET_HEADERS)
    assert len(telegram_sender.sent) == 1


async def test_unlink_revokes_pending_codes_and_last(
    client: AsyncClient,
    admin_token: str,
    telegram_sender: RecordingTelegramSender,
) -> None:
    code = await link_code(client, admin_token)
    await client.post(WEBHOOK, json=start_update(code), headers=SECRET_HEADERS)
    pending_code = await link_code(client, admin_token)
    await client.delete("/api/v1/admin/telegram", headers=auth(admin_token))
    telegram_sender.sent.clear()
    await client.post(WEBHOOK, json=message_update("/last"), headers=SECRET_HEADERS)
    await client.post(WEBHOOK, json=start_update(pending_code), headers=SECRET_HEADERS)
    await client.post(REPORT, json={"job": "update-prices", "status": "ok"}, headers=JOB_HEADERS)
    assert telegram_sender.sent == []


@pytest.mark.parametrize("mode", ["expired", "replaced"])
async def test_old_link_codes_are_silent(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_token: str,
    telegram_sender: RecordingTelegramSender,
    mode: str,
) -> None:
    code = await link_code(client, admin_token)
    if mode == "expired":
        await db_session.execute(
            text("UPDATE auth_tokens SET expires_at = now() - interval '1 minute'")
        )
        await db_session.commit()
    else:
        await link_code(client, admin_token)
    await client.post(WEBHOOK, json=start_update(code), headers=SECRET_HEADERS)
    assert telegram_sender.sent == []


@pytest.mark.parametrize(
    "sender",
    [None, {"id": 999, "is_bot": False}, {"id": CHAT_ID, "is_bot": True}],
)
async def test_invalid_sender_cannot_read_a_linked_chat(
    client: AsyncClient,
    admin_token: str,
    telegram_sender: RecordingTelegramSender,
    sender: dict[str, object] | None,
) -> None:
    code = await link_code(client, admin_token)
    await client.post(WEBHOOK, json=start_update(code), headers=SECRET_HEADERS)
    telegram_sender.sent.clear()
    await client.post(
        WEBHOOK,
        json={
            "message": {
                "chat": {"id": CHAT_ID, "type": "private"},
                "from": sender,
                "text": "/last",
            }
        },
        headers=SECRET_HEADERS,
    )
    assert telegram_sender.sent == []
