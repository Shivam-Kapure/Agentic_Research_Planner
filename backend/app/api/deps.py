"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings


def get_app_settings(request: Request) -> Settings:
    """Settings the running app was created with (overridable in tests)."""
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
