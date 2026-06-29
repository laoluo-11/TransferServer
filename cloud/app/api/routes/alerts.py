from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from cloud.app.api.deps import get_runtime
from cloud.app.api.schemas import AlertListResponse
from cloud.app.services.runtime import CloudRuntime

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get(
    "",
    response_model=AlertListResponse,
    summary="List recent alerts",
    description="Returns recent robot alerts for debugging and local operations.",
)
async def list_alerts(
    robot_id: str | None = Query(default=None, description="Optional robot filter."),
    limit: int = Query(default=20, ge=1, le=200, description="Maximum records to return."),
    runtime: CloudRuntime = Depends(get_runtime),
) -> AlertListResponse:
    alerts = runtime.list_alerts(robot_id=robot_id, limit=limit)
    return AlertListResponse(code=0, message="ok", data=alerts)
