"""API v1 router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    auth,
    bootstrap,
    catalog,
    collection,
    completeness,
    expenses,
    google_auth,
    health,
    jobs,
    reference,
    series,
    support,
    telegram,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(admin.router)
api_router.include_router(auth.router)
api_router.include_router(google_auth.router)
api_router.include_router(bootstrap.router)
api_router.include_router(catalog.router)
api_router.include_router(collection.router)
api_router.include_router(expenses.router)
api_router.include_router(series.router)
api_router.include_router(completeness.router)
api_router.include_router(reference.router)
api_router.include_router(jobs.router)
api_router.include_router(telegram.router)
api_router.include_router(support.router)
