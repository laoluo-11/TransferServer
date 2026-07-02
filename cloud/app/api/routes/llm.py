"""
LLM chat endpoint — 自然语言控制机器人。

POST /llm/chat 接受自然语言对话，
LLM 解析意图后自动调用对应技能并下发任务给机器人。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from cloud.app.api.deps import get_runtime
from cloud.app.services.llm import build_llm_service

logger = logging.getLogger("cloud.api.llm")

router = APIRouter(prefix="/llm", tags=["llm"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str = Field(description="'user', 'assistant', or 'system'")
    content: str = Field(description="Message content")


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(
        description="Conversation history. At minimum one user message.",
        min_length=1,
    )
    robot_id: str = Field(
        default="bumi_001",
        description="Target robot ID for task dispatching.",
    )


class TaskInfo(BaseModel):
    task_id: str
    skill: str
    status: str
    params: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    text: str = Field(description="LLM text reply (may be empty if only actions)")
    tasks_created: list[TaskInfo] = Field(
        default_factory=list,
        description="Tasks created from LLM function calls",
    )
    raw: dict[str, Any] | None = Field(
        default=None,
        description="Raw LLM API response (for debugging)",
    )

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """
    自然语言对话接口。

    LLM 会根据用户意图自动选择技能并生成任务。
    例如：
      - "往前走两步" → move(x=0.2, yaw=0)
      - "挥挥手"     → gesture(name="wave_hand")
      - "介绍一下你自己" → speak(text="...")

    当前如果未配置 LLM_API_KEY，会返回占位提示。
    """
    runtime = get_runtime(request)
    settings = request.app.state.settings
    llm_service = request.app.state.llm_service

    # Convert messages
    llm_messages: list[dict[str, Any]] = [
        {"role": m.role, "content": m.content} for m in body.messages
    ]

    # Get robot state for context
    robot_state_raw = runtime.get_robot_state(body.robot_id)
    robot_state = {
        "robot_id": body.robot_id,
        "online": robot_state_raw.online,
        "battery_percent": robot_state_raw.battery_percent,
        "safety_state": robot_state_raw.safety_state.value,
        "motion_state": robot_state_raw.motion_state.value,
        "current_task_id": robot_state_raw.current_task_id,
    }

    # Call LLM
    llm_response = await llm_service.chat(
        llm_messages,
        robot_id=body.robot_id,
        robot_state=robot_state,
    )

    # Create tasks from LLM function calls
    tasks_created: list[TaskInfo] = []
    for task_req in llm_response.tasks:
        try:
            task_record = await runtime.create_task(body.robot_id, task_req)
            tasks_created.append(
                TaskInfo(
                    task_id=task_record.task_id,
                    skill=task_record.skill.value,
                    status=task_record.status.value,
                    params=task_record.params,
                )
            )
            logger.info(
                "LLM task created: %s skill=%s robot=%s",
                task_record.task_id,
                task_record.skill.value,
                body.robot_id,
            )
        except Exception as exc:  # pragma: no cover
            logger.exception("Failed to create LLM task: %s", exc)
            tasks_created.append(
                TaskInfo(
                    task_id="",
                    skill=task_req.skill.value,
                    status="failed",
                    params={"error": str(exc)},
                )
            )

    return ChatResponse(
        text=llm_response.text,
        tasks_created=tasks_created,
        raw=llm_response.raw_response,
    )


@router.get("/skills")
async def list_skills(request: Request) -> dict[str, Any]:
    """List all available robot skills with their function schemas."""
    from shared.llm import SKILL_SCHEMAS

    return {
        "skills": SKILL_SCHEMAS,
        "count": len(SKILL_SCHEMAS),
    }
