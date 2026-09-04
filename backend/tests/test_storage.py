"""app.core.storage — presigning against a public endpoint (docs/06-media-storage.md).

Client construction and URL signing are both local computation, no network
call — these run as plain unit tests, no MinIO required.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.storage import ObjectStorage, build_s3_client


def _settings(**overrides: str) -> Settings:
    values: dict[str, str] = {
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_SECRET": "secret",
        "PUBLIC_BASE_URL": "http://testserver",
        "S3_ENDPOINT": "http://minio:9000",
        "S3_ACCESS_KEY": "minioadmin",
        "S3_SECRET_KEY": "minioadmin",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_build_s3_client_defaults_to_the_settings_endpoint() -> None:
    client = build_s3_client(_settings())

    assert client.meta.endpoint_url == "http://minio:9000"


def test_build_s3_client_accepts_an_endpoint_override_for_presigning() -> None:
    client = build_s3_client(_settings(), endpoint_url="https://coins.example.com/media")

    assert client.meta.endpoint_url == "https://coins.example.com/media"


def test_presigned_url_is_signed_for_the_public_endpoint_when_configured() -> None:
    settings = _settings()
    internal = build_s3_client(settings)
    public = build_s3_client(settings, endpoint_url="https://coins.example.com/media")
    storage = ObjectStorage(internal, settings.s3_bucket, presign_client=public)

    url = storage.presigned_get_url("catalog/1/obverse/x_300.webp")

    # The docker-network host never leaks into a URL a browser has to open,
    # and the object still resolves under path-style /<bucket>/<key>.
    assert url.startswith(
        "https://coins.example.com/media/coinkeeper-media/catalog/1/obverse/x_300.webp"
    )


def test_presigned_url_falls_back_to_the_data_client_without_a_public_endpoint() -> None:
    settings = _settings()
    internal = build_s3_client(settings)
    storage = ObjectStorage(internal, settings.s3_bucket)

    url = storage.presigned_get_url("catalog/1/obverse/x_300.webp")

    assert url.startswith("http://minio:9000/coinkeeper-media/catalog/1/obverse/x_300.webp")
