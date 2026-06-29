from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from cloud.app.api.deps import get_runtime
from cloud.app.api.schemas import (
    CapabilityData,
    CapabilityResponse,
    InterruptData,
    InterruptResponse,
    RobotListResponse,
    RobotStateData,
    RobotStateResponse,
    RobotSummary,
    TaskCreateData,
    TaskCreateResponse,
)
from cloud.app.services.runtime import CloudRuntime
from shared.protocol import CreateTaskRequest, InterruptRequest

router = APIRouter(prefix="/api/v1/robots", tags=["robots"])


@router.get(
    "",
    response_model=RobotListResponse,
    summary="List known robots",
    description="Returns the latest state snapshot for every known robot connection.",
)
async def list_robots(
    runtime: CloudRuntime = Depends(get_runtime),
) -> RobotListResponse:
    data = [
        RobotSummary(
            robot_id=item["robot_id"],
            online=item["online"],
            battery_percent=item["battery_percent"],
            safety_state=item["safety_state"],
            current_task_id=item["current_task_id"],
            capabilities=item["capabilities"],
            updated_at=item["updated_at"],
        )
        for item in runtime.list_robots()
    ]
    return RobotListResponse(code=0, message="ok", data=data)


@router.post(
    "/{robot_id}/tasks",
    response_model=TaskCreateResponse,
    summary="Create a robot task",
    description="Creates and dispatches a structured skill task to the target robot.",
)
async def create_task(
    robot_id: str,
    request: CreateTaskRequest,
    runtime: CloudRuntime = Depends(get_runtime),
) -> TaskCreateResponse:
    task = await runtime.create_task(robot_id, request)
    return TaskCreateResponse(
        code=0,
        message="accepted",
        data=TaskCreateData(
            task_id=task.task_id,
            robot_id=task.robot_id,
            status=task.status.value,
        ),
    )


@router.get(
    "/{robot_id}/state",
    response_model=RobotStateResponse,
    summary="Get robot state",
    description="Returns the latest state snapshot and reported capabilities for one robot.",
)
async def get_robot_state(
    robot_id: str,
    runtime: CloudRuntime = Depends(get_runtime),
) -> RobotStateResponse:
    state = runtime.get_robot_state(robot_id)
    capabilities = runtime.get_capabilities(robot_id)
    return RobotStateResponse(
        code=0,
        message="ok",
        data=RobotStateData(
            robot_id=robot_id,
            **state.model_dump(mode="json"),
            capabilities=capabilities,
        ),
    )


@router.post(
    "/{robot_id}/interrupt",
    response_model=InterruptResponse,
    summary="Interrupt current robot task",
    description="Sends an interrupt request to the connected robot agent.",
)
async def interrupt_robot(
    robot_id: str,
    request: InterruptRequest,
    runtime: CloudRuntime = Depends(get_runtime),
) -> InterruptResponse:
    success = await runtime.interrupt_robot(robot_id, request)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"robot {robot_id} is not connected",
        )
    return InterruptResponse(
        code=0,
        message="interrupt_sent",
        data=InterruptData(robot_id=robot_id),
    )


@router.get(
    "/{robot_id}/capabilities",
    response_model=CapabilityResponse,
    summary="Get robot capabilities",
    description="Returns the capabilities announced by the connected robot agent.",
)
async def get_capabilities(
    robot_id: str,
    runtime: CloudRuntime = Depends(get_runtime),
) -> CapabilityResponse:
    return CapabilityResponse(
        code=0,
        message="ok",
        data=CapabilityData(
            robot_id=robot_id,
            skills=runtime.get_capabilities(robot_id),
        ),
    )
