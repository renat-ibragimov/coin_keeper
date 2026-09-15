#!/usr/bin/env python3
"""Register the support bot webhook from environment-backed settings."""

from __future__ import annotations

import asyncio

import httpx

from app.core.config import get_settings


async def main() -> None:
    settings = get_settings()
    required = {
        "SUPPORT_TELEGRAM_BOT_TOKEN": settings.support_telegram_bot_token,
        "SUPPORT_TELEGRAM_BOT_USERNAME": settings.support_telegram_bot_username,
        "SUPPORT_TELEGRAM_WEBHOOK_SECRET": settings.support_telegram_webhook_secret,
        "PUBLIC_BASE_URL": settings.public_base_url,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise SystemExit(f"Missing settings: {', '.join(missing)}")

    webhook_url = f"{settings.public_base_url.rstrip('/')}/api/v1/support/telegram/webhook"
    api_url = f"https://api.telegram.org/bot{settings.support_telegram_bot_token}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        identity = (await client.post(f"{api_url}/getMe")).json()
        if not identity.get("ok"):
            raise SystemExit(f"Telegram rejected the bot token: {identity}")
        actual_username = identity["result"]["username"].lower()
        configured_username = settings.support_telegram_bot_username.lstrip("@").lower()
        if actual_username != configured_username:
            raise SystemExit(
                f"Bot username mismatch: token belongs to @{actual_username}, "
                f"configuration says @{configured_username}"
            )
        result = (
            await client.post(
                f"{api_url}/setWebhook",
                json={
                    "url": webhook_url,
                    "secret_token": settings.support_telegram_webhook_secret,
                    "allowed_updates": ["message", "callback_query"],
                    "drop_pending_updates": True,
                },
            )
        ).json()
    if not result.get("ok"):
        raise SystemExit(f"Could not register webhook: {result}")
    print(f"Support webhook configured: {webhook_url}")


if __name__ == "__main__":
    asyncio.run(main())
