"""Shared helpers for the auth tests."""

from __future__ import annotations

import re
import uuid

from httpx import AsyncClient

from app.core.mail.base import EmailMessage

PASSWORD = "correct-horse-battery"
TOKEN_PATTERN = re.compile(r"token=([A-Za-z0-9_\-]+)")


def unique_email() -> str:
    """Placeholder addresses only: no real address ever enters the repository.

    example.com is reserved by IANA for documentation, so nothing here can
    reach a real mailbox even if a test somehow sent mail for real.
    """
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


def extract_token(outbox: list[EmailMessage]) -> str:
    for message in reversed(outbox):
        match = TOKEN_PATTERN.search(message.body)
        if match:
            return match.group(1)
    raise AssertionError("no token found in the outgoing mail")


async def register_and_verify(
    client: AsyncClient, outbox: list[EmailMessage], email: str | None = None
) -> tuple[str, str]:
    """Walk the real signup path and return (email, access token)."""
    address = email or unique_email()
    response = await client.post(
        "/api/v1/auth/register", json={"email": address, "password": PASSWORD}
    )
    assert response.status_code == 202, response.text

    verify = await client.post("/api/v1/auth/verify-email", json={"token": extract_token(outbox)})
    assert verify.status_code == 200, verify.text
    token: str = verify.json()["tokens"]["accessToken"]
    return address, token
