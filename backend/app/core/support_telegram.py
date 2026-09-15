"""Small Bot API client for the public support relay."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("app.support_telegram")


class SupportTelegramClient:
    def __init__(self, token: str) -> None:
        self._base_url = f"https://api.telegram.org/bot{token}"

    async def _call(self, method: str, payload: dict[str, Any]) -> Any | None:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(f"{self._base_url}/{method}", json=payload)
            response.raise_for_status()
            body = response.json()
            if body.get("ok"):
                return body.get("result")
            logger.warning("support telegram rejected %s: %s", method, response.text[:300])
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("support telegram %s failed: %s", method, exc)
        return None

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        thread_id: int | None = None,
        close_ticket_id: int | None = None,
    ) -> int | None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if thread_id is not None:
            payload["message_thread_id"] = thread_id
        if close_ticket_id is not None:
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [
                        {
                            "text": "Закрити звернення",
                            "callback_data": f"support:close:{close_ticket_id}",
                        }
                    ]
                ]
            }
        result = await self._call("sendMessage", payload)
        return result.get("message_id") if isinstance(result, dict) else None

    async def copy_message(
        self, *, from_chat_id: int, message_id: int, chat_id: int, thread_id: int | None = None
    ) -> int | None:
        payload: dict[str, Any] = {
            "from_chat_id": from_chat_id,
            "message_id": message_id,
            "chat_id": chat_id,
        }
        if thread_id is not None:
            payload["message_thread_id"] = thread_id
        result = await self._call("copyMessage", payload)
        return result.get("message_id") if isinstance(result, dict) else None

    async def create_topic(self, group_chat_id: int, name: str) -> int | None:
        result = await self._call(
            "createForumTopic", {"chat_id": group_chat_id, "name": name[:128]}
        )
        return result.get("message_thread_id") if isinstance(result, dict) else None

    async def close_topic(self, group_chat_id: int, thread_id: int) -> bool:
        return bool(
            await self._call(
                "closeForumTopic", {"chat_id": group_chat_id, "message_thread_id": thread_id}
            )
        )

    async def answer_callback(self, callback_id: str, text: str) -> None:
        await self._call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})


def get_support_telegram_client() -> SupportTelegramClient:
    from app.core.config import get_settings

    return SupportTelegramClient(get_settings().support_telegram_bot_token)
