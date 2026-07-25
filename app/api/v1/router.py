from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import categories, health, profile, scan

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(categories.router)
api_router.include_router(scan.router)
api_router.include_router(profile.router)
