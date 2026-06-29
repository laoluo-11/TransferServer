from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from cloud.app.api.deps import get_runtime
from cloud.app.api.schemas import TaskListResponse, TaskResponse
from cloud.app.services.runtime import CloudRuntime

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get(
    "",
    response_model=TaskListResponse,
    summary="List recent tasks",
    description="Returns recent tasks, optionally filtered by robot.",
)
async def list_tasks(
    robot_id: str | None = Query(default=None, description="Optional robot filter."),
    limit: int = Query(default=20, ge=1, le=200, description="Maximum records to return."),
    runtime: CloudRuntime = Depends(get_runtime),
) -> TaskListResponse:
    tasks = runtime.list_tasks(robot_id=robot_id, limit=limit)
    return TaskListResponse(code=0, message="ok", data=tasks)


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Get task detail",
    description="Returns the current or final state of a single task.",
)
async def get_task(
    task_id: str,
    runtime: CloudRuntime = Depends(get_runtime),
) -> TaskResponse:
    task = runtime.get_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"task {task_id} not found",
        )
    return TaskResponse(code=0, message="ok", data=task)
