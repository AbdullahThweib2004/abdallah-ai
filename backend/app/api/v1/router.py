from fastapi import APIRouter

from app.api.v1 import chat, content, health, voice

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(content.router)
api_router.include_router(chat.router)
api_router.include_router(voice.router)
