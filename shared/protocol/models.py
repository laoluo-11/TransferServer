from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    AlertLevel,
    MessageType,
    MotionState,
    SafetyState,
    SkillName,
    SpeechState,
    TaskStage,
    TaskStatus,
)


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id(prefix: str = "msg") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class SchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Envelope(SchemaModel):
    msg_id: str = Field(default_factory=new_id)
    msg_type: MessageType
    timestamp: int = Field(default_factory=now_ms)
    robot_id: str
    trace_id: str = Field(default_factory=lambda: new_id("trace"))
    protocol_version: str = "1.0"
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskPolicy(SchemaModel):
    interruptible: bool = Field(default=True, description="Whether the task may be interrupted.")
    timeout_ms: int = Field(default=5000, description="Task timeout in milliseconds.")
    priority: int = Field(default=50, description="Higher number means higher scheduling priority.")
    need_ack: bool = Field(default=True, description="Whether the cloud expects an agent ack.")
    on_error: str = Field(default="abort", description="Error handling strategy for compound flows.")


class TaskSource(SchemaModel):
    type: str = Field(default="api", description="Origin type, such as api, panel, or agent.")
    name: str = Field(default="manual", description="Origin name for audit and debugging.")


class AgentHelloPayload(SchemaModel):
    agent_version: str
    sdk_version: str
    protocol_version: str
    capabilities: list[SkillName]


class HeartbeatPayload(SchemaModel):
    status: str = "online"
    battery_percent: int = 100
    current_task_id: str | None = None
    safety_state: SafetyState = SafetyState.NORMAL


class AckPayload(SchemaModel):
    ack_type: str
    accepted: bool
    reason: str = ""
    task_id: str | None = None
    error_code: int = 0


class TaskCommandPayload(SchemaModel):
    task_id: str
    skill: SkillName
    params: dict[str, Any] = Field(default_factory=dict)
    policy: TaskPolicy = Field(default_factory=TaskPolicy)
    source: TaskSource = Field(default_factory=TaskSource)


class TaskEventPayload(SchemaModel):
    task_id: str
    stage: TaskStage
    detail: str = ""


class TaskResultPayload(SchemaModel):
    task_id: str
    status: TaskStatus
    result_code: int = 0
    result_message: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)


class RobotStatePayload(SchemaModel):
    online: bool = True
    workmode: int = 0
    battery_percent: int = 100
    motion_state: MotionState = MotionState.IDLE
    speech_state: SpeechState = SpeechState.IDLE
    safety_state: SafetyState = SafetyState.NORMAL
    current_task_id: str | None = None
    updated_at: int = Field(default_factory=now_ms)


class AlertPayload(SchemaModel):
    level: AlertLevel
    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class InterruptRequest(SchemaModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "reason": "manual_override",
                "scope": "current_task",
            }
        },
    )

    reason: str = Field(default="manual_override", description="Why the interrupt is being sent.")
    scope: str = Field(default="current_task", description="Interrupt scope, usually current_task.")


class InterruptResultPayload(SchemaModel):
    task_id: str | None = None
    status: str
    message: str


class CreateTaskRequest(SchemaModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "skill": "speak",
                    "params": {
                        "text": "你好，我是 Bumi。",
                        "voice": "default",
                    },
                    "policy": {
                        "interruptible": True,
                        "timeout_ms": 5000,
                        "priority": 50,
                        "need_ack": True,
                        "on_error": "abort",
                    },
                    "source": {
                        "type": "panel",
                        "name": "local_debug_panel",
                    },
                },
                {
                    "skill": "move",
                    "params": {
                        "x": 0.15,
                        "yaw": 0.1,
                        "duration_ms": 1200,
                    },
                    "policy": {
                        "interruptible": True,
                        "timeout_ms": 3000,
                        "priority": 50,
                        "need_ack": True,
                        "on_error": "abort",
                    },
                    "source": {
                        "type": "api",
                        "name": "manual",
                    },
                },
            ]
        },
    )

    skill: SkillName = Field(description="Whitelisted skill name to execute.")
    params: dict[str, Any] = Field(default_factory=dict, description="Skill-specific parameters.")
    policy: TaskPolicy = Field(default_factory=TaskPolicy, description="Scheduling and timeout policy.")
    source: TaskSource = Field(default_factory=TaskSource, description="Task origin metadata.")


class TaskRecord(SchemaModel):
    task_id: str
    robot_id: str
    trace_id: str
    skill: SkillName
    params: dict[str, Any] = Field(default_factory=dict)
    policy: TaskPolicy = Field(default_factory=TaskPolicy)
    source: TaskSource = Field(default_factory=TaskSource)
    status: TaskStatus = TaskStatus.QUEUED
    last_stage: TaskStage | None = None
    result_code: int | None = None
    result_message: str = ""
    created_at: int = Field(default_factory=now_ms)
    updated_at: int = Field(default_factory=now_ms)


def build_envelope(
    msg_type: MessageType,
    robot_id: str,
    payload: SchemaModel | dict[str, Any],
    *,
    trace_id: str | None = None,
) -> Envelope:
    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    return Envelope(
        msg_type=msg_type,
        robot_id=robot_id,
        trace_id=trace_id or new_id("trace"),
        payload=data,
    )


def new_task_record(robot_id: str, request: CreateTaskRequest) -> TaskRecord:
    return TaskRecord(
        task_id=new_id("task"),
        robot_id=robot_id,
        trace_id=new_id("trace"),
        skill=request.skill,
        params=request.params,
        policy=request.policy,
        source=request.source,
    )
