from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from cloud.app.api.schemas import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/panel")


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
    description="Simple liveness check for the cloud service.",
)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
