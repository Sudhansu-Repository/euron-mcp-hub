from __future__ import annotations

from fastapi import APIRouter

from mcphub.api.routes import auth, calls, clients, health, keys, servers, stats, tools, users

api_router = APIRouter()
for module in (health, auth, users, servers, tools, clients, keys, calls, stats):
    api_router.include_router(module.router)
