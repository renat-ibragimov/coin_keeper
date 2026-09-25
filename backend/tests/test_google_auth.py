"""Google sign-in must never silently take over or duplicate an email account."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.mail.base import EmailMessage
from app.core.rate_limit import get_redis
from app.repositories.users import AuthIdentityRepository, UserRepository
from app.services import google_auth as google_module
from app.services.google_auth import GoogleClaims, GoogleOAuth, GoogleOAuthError, PendingFlow
from tests.helpers import PASSWORD, extract_token, register_and_verify, unique_email


def enable_google(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "google_client_id", "test-google-client")
    monkeypatch.setattr(settings, "google_client_secret", "test-google-secret")


def oauth_state(url: str) -> str:
    return parse_qs(urlparse(url).query)["state"][0]


def google_claims(
    monkeypatch: pytest.MonkeyPatch, email: str, subject: str, *, controls_email: bool = True
) -> None:
    async def fake_exchange(self: GoogleOAuth, *, code: str, flow: object) -> GoogleClaims:
        assert code == "test-code"
        return GoogleClaims(
            subject=subject, email=email, name="Google Person", google_controls_email=controls_email
        )

    monkeypatch.setattr(GoogleOAuth, "exchange", fake_exchange)


async def test_google_creates_one_account_and_can_add_password(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_google(monkeypatch)
    email = f"google-{unique_email().split('@')[0]}@gmail.com"
    google_claims(monkeypatch, email, "google-sub-1")

    start = await client.get("/api/v1/auth/google/start")
    assert start.status_code == 302
    callback = await client.get(
        "/api/v1/auth/google/callback",
        params={"state": oauth_state(start.headers["location"]), "code": "test-code"},
    )
    assert callback.status_code == 303
    assert callback.headers["location"].endswith("/google-complete")

    complete = await client.post("/api/v1/auth/refresh")
    assert complete.status_code == 200
    user = complete.json()["user"]
    assert user["email"] == email
    assert user["googleLinked"] is True
    assert user["hasPassword"] is False

    auth = {"Authorization": f"Bearer {complete.json()['tokens']['accessToken']}"}
    added = await client.post(
        "/api/v1/auth/set-password", json={"newPassword": PASSWORD}, headers=auth
    )
    assert added.status_code == 204
    password_login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert password_login.status_code == 200
    assert password_login.json()["user"]["id"] == user["id"]
    assert (await UserRepository(db_session).get_by_email(email)).id == user["id"]


async def test_password_registration_for_existing_google_account_is_generic_but_recoverable(
    client: AsyncClient,
    db_session: AsyncSession,
    mail_outbox: list[EmailMessage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_google(monkeypatch)
    email = f"google-{unique_email().split('@')[0]}@gmail.com"
    google_claims(monkeypatch, email, "google-sub-register-collision")
    start = await client.get("/api/v1/auth/google/start")
    await client.get(
        "/api/v1/auth/google/callback",
        params={"state": oauth_state(start.headers["location"]), "code": "test-code"},
    )
    original = await UserRepository(db_session).get_by_email(email)
    assert original is not None

    repeated = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert repeated.status_code == 202
    assert mail_outbox == []
    assert (await UserRepository(db_session).get_by_email(email)).id == original.id

    recovery = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert recovery.status_code == 202
    assert mail_outbox[-1].to == email
    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": extract_token(mail_outbox), "newPassword": PASSWORD},
    )
    assert reset.status_code == 204
    password_login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert password_login.status_code == 200
    assert password_login.json()["user"]["id"] == original.id


async def test_second_google_identity_cannot_replace_a_linked_one(
    client: AsyncClient, mail_outbox: list[EmailMessage], monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_google(monkeypatch)
    email, access = await register_and_verify(client, mail_outbox)
    google_claims(monkeypatch, email, "first-google-sub")
    auth = {"Authorization": f"Bearer {access}"}
    link = await client.post("/api/v1/auth/google/link/start", headers=auth)
    assert link.status_code == 200
    linked = await client.get(
        "/api/v1/auth/google/callback",
        params={"state": oauth_state(link.json()["url"]), "code": "test-code"},
    )
    assert linked.headers["location"].endswith("google=linked")

    assert (await client.post("/api/v1/auth/google/link/start", headers=auth)).status_code == 409
    google_claims(monkeypatch, email, "second-google-sub")
    start = await client.get("/api/v1/auth/google/start")
    collision = await client.get(
        "/api/v1/auth/google/callback",
        params={"state": oauth_state(start.headers["location"]), "code": "test-code"},
    )
    assert collision.headers["location"].endswith("/login?google=link-required")


async def test_matching_email_requires_explicit_link_to_existing_user(
    client: AsyncClient,
    db_session: AsyncSession,
    mail_outbox: list[EmailMessage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_google(monkeypatch)
    email, access = await register_and_verify(client, mail_outbox)
    original = await UserRepository(db_session).get_by_email(email)
    assert original is not None
    google_claims(monkeypatch, email, "google-sub-2")

    start = await client.get("/api/v1/auth/google/start")
    collision = await client.get(
        "/api/v1/auth/google/callback",
        params={"state": oauth_state(start.headers["location"]), "code": "test-code"},
    )
    assert collision.headers["location"].endswith("/login?google=link-required")
    assert (await UserRepository(db_session).get_by_email(email)).id == original.id

    link = await client.post(
        "/api/v1/auth/google/link/start", headers={"Authorization": f"Bearer {access}"}
    )
    assert link.status_code == 200
    linked = await client.get(
        "/api/v1/auth/google/callback",
        params={"state": oauth_state(link.json()["url"]), "code": "test-code"},
    )
    assert linked.headers["location"].endswith("/google-complete?mode=link&google=linked")
    profile = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert profile.json()["id"] == original.id
    assert profile.json()["googleLinked"] is True


async def test_google_callback_rejects_state_from_another_browser(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_google(monkeypatch)
    start = await client.get("/api/v1/auth/google/start")
    client.cookies.set("ck_google_oauth_state", "wrong-state", path="/api/v1/auth/google")
    callback = await client.get(
        "/api/v1/auth/google/callback",
        params={"state": oauth_state(start.headers["location"]), "code": "test-code"},
    )
    assert callback.headers["location"].endswith("/login?google=error")


async def test_google_without_a_google_owned_email_creates_nothing(
    client: AsyncClient,
    db_session: AsyncSession,
    mail_outbox: list[EmailMessage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outside Gmail and Workspace, Google only once checked the address and no
    longer vouches for it. Creating a pending account with that Google already
    attached let a former owner of the mailbox keep a way in once the real
    owner confirmed the address; such a user registers by email and links
    Google in settings instead (docs/auth.md, "Google sign-in")."""
    enable_google(monkeypatch)
    email = unique_email()
    google_claims(monkeypatch, email, "google-sub-external", controls_email=False)
    start = await client.get("/api/v1/auth/google/start")
    callback = await client.get(
        "/api/v1/auth/google/callback",
        params={"state": oauth_state(start.headers["location"]), "code": "test-code"},
    )
    assert callback.headers["location"].endswith("/login?google=email-unconfirmed")
    assert await UserRepository(db_session).get_by_email(email) is None
    assert mail_outbox == []


async def test_confirming_an_address_always_needs_a_password(
    client: AsyncClient,
    db_session: AsyncSession,
    mail_outbox: list[EmailMessage],
) -> None:
    """Even for an unconfirmed account that somehow carries a Google identity,
    the link never signs anyone in without the mailbox owner choosing a
    password — and it no longer hints at a password-free path."""
    email = unique_email()
    assert (await client.post("/api/v1/auth/register", json={"email": email})).status_code == 202
    user = await UserRepository(db_session).get_by_email(email)
    assert user is not None
    await AuthIdentityRepository(db_session).link_google(
        user, subject="google-sub-pending", email=email
    )
    await db_session.commit()

    assert (
        await client.post("/api/v1/auth/resend-verification", json={"email": email})
    ).status_code == 202
    assert "google=1" not in mail_outbox[-1].body

    missing = await client.post(
        "/api/v1/auth/verify-email", json={"token": extract_token(mail_outbox)}
    )
    assert missing.status_code == 422
    assert missing.json()["type"].endswith("password-required")

    confirmed = await client.post(
        "/api/v1/auth/verify-email",
        json={"token": extract_token(mail_outbox), "newPassword": PASSWORD},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["user"]["googleLinked"] is False


async def test_link_rejects_different_google_email(
    client: AsyncClient, mail_outbox: list[EmailMessage], monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_google(monkeypatch)
    email, access = await register_and_verify(client, mail_outbox)
    assert email
    google_claims(monkeypatch, unique_email(), "google-sub-other")
    link = await client.post(
        "/api/v1/auth/google/link/start", headers={"Authorization": f"Bearer {access}"}
    )
    callback = await client.get(
        "/api/v1/auth/google/callback",
        params={"state": oauth_state(link.json()["url"]), "code": "test-code"},
    )
    assert callback.headers["location"].endswith("/google-complete?mode=link&google=conflict")
    profile = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert profile.json()["googleLinked"] is False


async def test_google_id_token_checks_audience_and_nonce(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real verifier checks a signed token, not just mocked provider claims."""
    enable_google(monkeypatch)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        google_module,
        "_jwks_client",
        SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())),
    )
    now = datetime.now(UTC)
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "test-google-client",
        "sub": "signed-google-sub",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "nonce": "expected-nonce",
        "email": "person@gmail.com",
        "email_verified": True,
    }
    current_token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["timeout"] == 10

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, _url: str, *, data: object) -> httpx.Response:
            assert data
            return httpx.Response(
                200, json={"id_token": current_token}, request=httpx.Request("POST", _url)
            )

    monkeypatch.setattr(google_module.httpx, "AsyncClient", FakeClient)
    flow = PendingFlow(mode="login", user_id=None, verifier="x" * 43, nonce="expected-nonce")
    oauth = GoogleOAuth(get_settings(), get_redis())
    verified = await oauth.exchange(code="test-code", flow=flow)
    assert verified.subject == "signed-google-sub"

    current_token = jwt.encode(
        {**claims, "aud": "another-client"}, key, algorithm="RS256", headers={"kid": "test"}
    )
    with pytest.raises(GoogleOAuthError):
        await oauth.exchange(code="test-code", flow=flow)

    current_token = jwt.encode(
        {**claims, "nonce": "wrong"}, key, algorithm="RS256", headers={"kid": "test"}
    )
    with pytest.raises(GoogleOAuthError):
        await oauth.exchange(code="test-code", flow=flow)
