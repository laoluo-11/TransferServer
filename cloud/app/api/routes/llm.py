"""
LLM Agent Loop endpoint - natural language robot control.

POST /llm/chat  accepts natural language, runs the ReAct agent loop,
and the LLM decides what actions to take step by step.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from cloud.app.api.deps import get_runtime
from shared.protocol.enums import TaskStatus

logger = logging.getLogger("cloud.api.llm")

router = APIRouter(prefix="/llm", tags=["llm"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str = Field(description="user, assistant, or system")
    content: str = Field(description="Message content")


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(
        description="Conversation history. At minimum one user message.",
        min_length=1,
    )
    robot_id: str = Field(
        default="bumi_001",
        description="Target robot ID.",
    )


class StepInfo(BaseModel):
    round: int
    thought: str
    function: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class ChatResponse(BaseModel):
    text: str = Field(description="Final text reply from the agent")
    steps: list[StepInfo] = Field(
        default_factory=list,
        description="Each step the agent took (think -> act -> observe)",
    )
    total_rounds: int = 0
    raw: dict[str, Any] | None = Field(default=None)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """
    Natural language chat with Agent Loop (ReAct pattern).

    The LLM will:
      1. Think about what to do
      2. Call robot skills (move/gesture/speak/etc.)
      3. Observe results
      4. Decide next step or respond

    Example:
      "go forward, wave, and say hello"
        -> round 1: move(x=0.1)     -> OK
        -> round 2: gesture(wave)   -> OK
        -> round 3: speak("hello")  -> OK
        -> final reply
    """
    runtime = get_runtime(request)
    settings = request.app.state.settings
    llm_service = request.app.state.llm_service

    # Build the task executor callback
    async def execute_task(task_req):
        try:
            task_record = await runtime.create_task(body.robot_id, task_req)
            # In agent mode, we simulate task execution for responsiveness.
            # Real task result polling can be added when robot is connected.
            await asyncio.sleep(0.5)  # simulate execution time
            # Re-fetch to get latest status (may have been updated by agent)
            final = runtime.get_task(task_record.task_id)
            if final:
                return {
                    "status": final.status.value,
                    "task_id": final.task_id,
                    "skill": final.skill.value,
                    "result_code": final.result_code,
                    "result_message": final.result_message,
                }
            return {"status": task_record.status.value, "task_id": task_record.task_id}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    # Build messages for LLM
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

    # Run agent loop
    agent_response = await llm_service.chat(
        llm_messages,
        execute_task,
        robot_id=body.robot_id,
        robot_state=robot_state,
    )

    # Convert steps to response model
    step_infos = [
        StepInfo(
            round=s.round,
            thought=s.thought,
            function=s.function_name,
            args=s.function_args,
            result=s.result,
            error=s.error,
        )
        for s in agent_response.steps
    ]

    return ChatResponse(
        text=agent_response.text,
        steps=step_infos,
        total_rounds=len(agent_response.steps),
        raw=agent_response.raw,
    )


@router.get("/skills")
async def list_skills(request: Request) -> dict[str, Any]:
    """List all available robot skills with their function schemas."""
    from shared.llm import SKILL_SCHEMAS
    return {"skills": SKILL_SCHEMAS, "count": len(SKILL_SCHEMAS)}