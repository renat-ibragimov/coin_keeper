"""Settings refuse values that would quietly weaken security (docs/auth.md)."""

from __future__ import annotations

import pytest

from app.core.config import Settings


def test_a_short_jwt_secret_refuses_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "too-short")
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings()  # type: ignore[call-arg]
