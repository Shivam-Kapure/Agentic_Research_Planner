from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import SettingsDep

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    env: str


@router.get("/health", response_model=HealthResponse)
def health(settings: SettingsDep) -> HealthResponse:
    """Liveness probe, also used by the keep-warm ping on the free Render tier."""
    return HealthResponse(status="ok", version=settings.app_version, env=settings.app_env)
