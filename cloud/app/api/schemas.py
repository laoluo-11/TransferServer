from __future__ import annotations

from pydantic import BaseModel, Field

from shared.protocol import RobotStatePayload, TaskRecord


class ApiResponse(BaseModel):
    code: int = Field(default=0, description="Application-level status code.")
    message: str = Field(default="ok", description="Human-readable response message.")


class HealthResponse(BaseModel):
    status: str = "ok"


class TaskCreateData(BaseModel):
    task_id: str
    robot_id: str
    status: str


class TaskCreateResponse(ApiResponse):
    data: TaskCreateData


class TaskResponse(ApiResponse):
    data: TaskRecord


class TaskListResponse(ApiResponse):
    data: list[TaskRecord]


class CapabilityData(BaseModel):
    robot_id: str
    skills: list[str]


class CapabilityResponse(ApiResponse):
    data: CapabilityData


class InterruptData(BaseModel):
    robot_id: str


class InterruptResponse(ApiResponse):
    data: InterruptData


class RobotStateData(RobotStatePayload):
    robot_id: str
    capabilities: list[str] = Field(default_factory=list)


class RobotStateResponse(ApiResponse):
    data: RobotStateData


class RobotSummary(BaseModel):
    robot_id: str
    online: bool
    battery_percent: int
    safety_state: str
    current_task_id: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    updated_at: int


class RobotListResponse(ApiResponse):
    data: list[RobotSummary]


class AlertRecord(BaseModel):
    robot_id: str
    trace_id: str
    timestamp: int
    level: str
    code: str
    message: str
    detail: dict = Field(default_factory=dict)


class AlertListResponse(ApiResponse):
    data: list[AlertRecord]
