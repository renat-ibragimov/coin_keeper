"""Health endpoint: reports each dependency separately (docs/10-infra.md)."""

from __future__ import annotations

import asyncio
import logging

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Response, status
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import AppSettings, DbSession
from app.core.config import Settings
from app.core.rate_limit import get_redis
from app.schemas.health import ComponentHealth, HealthOut

router = APIRouter(tags=["health"])
logger = logging.getLogger("app.health")


async def _check_database(session: DbSession) -> ComponentHealth:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("database health check failed: %s", exc)
        return ComponentHealth(status="error", detail="query failed")
    return ComponentHealth(status="ok")


async def _check_redis() -> ComponentHealth:
    try:
        await get_redis().ping()
    except (RedisError, OSError) as exc:
        logger.warning("redis health check failed: %s", exc)
        return ComponentHealth(status="error", detail="ping failed")
    return ComponentHealth(status="ok")


def _head_bucket(settings: Settings) -> None:
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=BotoConfig(connect_timeout=2, read_timeout=2, retries={"max_attempts": 1}),
    )
    client.head_bucket(Bucket=settings.s3_bucket)


async def _check_storage(settings: Settings) -> ComponentHealth:
    try:
        await asyncio.to_thread(_head_bucket, settings)
    except (BotoCoreError, ClientError, OSError) as exc:
        logger.warning("storage health check failed: %s", exc)
        return ComponentHealth(status="error", detail="bucket unreachable")
    return ComponentHealth(status="ok")


@router.get("/health")
async def health(session: DbSession, settings: AppSettings, response: Response) -> HealthOut:
    database, redis_health, storage = await asyncio.gather(
        _check_database(session), _check_redis(), _check_storage(settings)
    )
    components = (database, redis_health, storage)
    healthy = all(component.status == "ok" for component in components)
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthOut(
        status="ok" if healthy else "degraded",
        database=database,
        redis=redis_health,
        storage=storage,
    )
