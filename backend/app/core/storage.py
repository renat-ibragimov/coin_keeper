"""S3-compatible object storage (MinIO locally, docs/06-media-storage.md)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import boto3
from botocore.config import Config as BotoConfig

from app.core.config import Settings

if TYPE_CHECKING:
    # Type-only: the stub package is a dev dependency and is absent in the
    # production image.
    from mypy_boto3_s3.client import S3Client


def build_s3_client(settings: Settings) -> S3Client:
    client: S3Client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=BotoConfig(retries={"max_attempts": 3, "mode": "standard"}),
    )
    return client


class ObjectStorage:
    """Thin wrapper: the migration only ever needs to put objects."""

    def __init__(self, client: S3Client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def put(self, key: str, payload: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=payload, ContentType=content_type
        )

    def ensure_bucket(self) -> None:
        """Create the bucket when missing, so a fresh server is not a blocker."""
        existing = {b["Name"] for b in self._client.list_buckets().get("Buckets", [])}
        if self._bucket not in existing:
            self._client.create_bucket(Bucket=self._bucket)
