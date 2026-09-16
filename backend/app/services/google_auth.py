"""Google OpenID Connect authorization-code flow.

The provider identity is the verified ``sub`` claim, never the email address.
OAuth state is both one-use in Redis and bound to the initiating browser cookie.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlencode

import httpx
import jwt
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.security import generate_token

GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"  # noqa: S105 - public endpoint
GOOGLE_JWKS = "https://www.googleapis.com/oauth2/v3/certs"
STATE_TTL_SECONDS = 600
STATE_COOKIE = "ck_google_oauth_state"

_jwks_client = jwt.PyJWKClient(GOOGLE_JWKS, cache_jwk_set=True, lifespan=300)


class GoogleOAuthError(Exception):
    """Invalid or expired provider response; never expose its internals."""


@dataclass(frozen=True, slots=True)
class GoogleFlow:
    url: str
    state: str


@dataclass(frozen=True, slots=True)
class GoogleClaims:
    subject: str
    email: str
    name: str | None
    google_controls_email: bool


@dataclass(frozen=True, slots=True)
class PendingFlow:
    mode: Literal["login", "link"]
    user_id: int | None
    verifier: str
    nonce: str


class GoogleOAuth:
    def __init__(self, settings: Settings, redis: Redis) -> None:
        self._settings = settings
        self._redis = redis

    @property
    def enabled(self) -> bool:
        return bool(self._settings.google_client_id and self._settings.google_client_secret)

    @property
    def redirect_uri(self) -> str:
        return f"{self._settings.public_base_url.rstrip('/')}/api/v1/auth/google/callback"

    async def start(
        self, *, mode: Literal["login", "link"], user_id: int | None = None
    ) -> GoogleFlow:
        if not self.enabled:
            raise GoogleOAuthError("Google sign-in is not configured")
        state = generate_token()
        verifier = generate_token()
        nonce = generate_token()
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        payload = json.dumps(
            {"mode": mode, "user_id": user_id, "verifier": verifier, "nonce": nonce}
        )
        await self._redis.set(f"google_oauth:{state}", payload, ex=STATE_TTL_SECONDS)
        query = urlencode(
            {
                "client_id": self._settings.google_client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )
        return GoogleFlow(url=f"{GOOGLE_AUTHORIZE}?{query}", state=state)

    async def consume(self, *, state: str, cookie_state: str | None) -> PendingFlow:
        if not cookie_state or not secrets.compare_digest(state, cookie_state):
            raise GoogleOAuthError("OAuth browser state mismatch")
        raw = await self._redis.getdel(f"google_oauth:{state}")
        if not raw:
            raise GoogleOAuthError("OAuth state expired or already used")
        try:
            value = json.loads(raw)
            if value["mode"] not in ("login", "link"):
                raise ValueError("invalid mode")
            return PendingFlow(
                mode=value["mode"],
                user_id=value["user_id"],
                verifier=value["verifier"],
                nonce=value["nonce"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GoogleOAuthError("Malformed OAuth state") from exc

    async def exchange(self, *, code: str, flow: PendingFlow) -> GoogleClaims:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    GOOGLE_TOKEN,
                    data={
                        "code": code,
                        "client_id": self._settings.google_client_id,
                        "client_secret": self._settings.google_client_secret,
                        "redirect_uri": self.redirect_uri,
                        "grant_type": "authorization_code",
                        "code_verifier": flow.verifier,
                    },
                )
                response.raise_for_status()
                id_token = response.json()["id_token"]
            signing_key = await asyncio.to_thread(_jwks_client.get_signing_key_from_jwt, id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._settings.google_client_id,
                issuer=["accounts.google.com", "https://accounts.google.com"],
                options={"require": ["aud", "exp", "iat", "iss", "sub"]},
            )
        except (httpx.HTTPError, KeyError, ValueError, jwt.PyJWTError) as exc:
            raise GoogleOAuthError("Google token verification failed") from exc
        if not isinstance(claims.get("nonce"), str) or not secrets.compare_digest(
            claims["nonce"], flow.nonce
        ):
            raise GoogleOAuthError("Google nonce mismatch")
        subject = claims.get("sub")
        email = claims.get("email")
        if not isinstance(subject, str) or not subject or not isinstance(email, str):
            raise GoogleOAuthError("Google identity is incomplete")
        if claims.get("email_verified") is not True:
            raise GoogleOAuthError("Google email is not verified")
        # Google is authoritative for Gmail and Workspace domains. For other
        # addresses, our own email-confirmation flow proves current ownership.
        controls_email = email.lower().endswith("@gmail.com") or bool(claims.get("hd"))
        name = claims.get("name")
        return GoogleClaims(
            subject=subject,
            email=email,
            name=name[:200] if isinstance(name, str) else None,
            google_controls_email=controls_email,
        )
