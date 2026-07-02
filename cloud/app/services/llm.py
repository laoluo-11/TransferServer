"""
LLM service layer for Bumi cloud.

TODO: 接入真实 LLM API 时，只需实现 _call_llm 方法即可。
      当前 `PlaceholderLLMService` 用于开发调试，
      配置 `LLM_PROVIDER=openai` 并设置 `LLM_API_KEY` 后自动切换。
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from cloud.app.core.config import LLMSettings
from shared.llm import SYSTEM_PROMPT, build_function_list
from shared.protocol import CreateTaskRequest, TaskSource
from shared.protocol.enums import SkillName

logger = logging.getLogger("cloud.llm")


class LLMService(ABC):
    """Abstract base for LLM backends."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        robot_id: str = "",
        robot_state: dict[str, Any] | None = None,
    ) -> "LLMResponse":
        """Send messages to LLM and parse function calls into robot tasks."""
        ...


class LLMResponse:
    """Structured response from the LLM service."""

    def __init__(
        self,
        text: str = "",
        tasks: list[CreateTaskRequest] | None = None,
        raw_response: dict[str, Any] | None = None,
    ) -> None:
        self.text = text
        self.tasks = tasks or []
        self.raw_response = raw_response or {}

    @property
    def has_tasks(self) -> bool:
        return len(self.tasks) > 0

    @property
    def has_text(self) -> bool:
        return bool(self.text)


# ---------------------------------------------------------------------------
# Placeholder
# ---------------------------------------------------------------------------

class PlaceholderLLMService(LLMService):
    """Placeholder — echoes what WOULD be sent to the LLM."""

    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings
        logger.info(
            "LLM service running in PLACEHOLDER mode — "
            "set LLM_API_KEY to enable real LLM calls"
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        robot_id: str = "",
        robot_state: dict[str, Any] | None = None,
    ) -> LLMResponse:
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = str(m.get("content", ""))
                break

        return LLMResponse(
            text=(
                f"[\u5360\u4f4d\u6a21\u5f0f] \u6536\u5230\u6d88\u606f\uff1a\u300c{last_user_msg}\u300d\u3002"
                f"\u5f53\u524d\u672a\u914d\u7f6e LLM API Key\uff0c\u8bf7\u8bbe\u7f6e LLM_API_KEY \u73af\u5883\u53d8\u91cf\u540e\u91cd\u8bd5\u3002"
            ),
        )

# ---------------------------------------------------------------------------
# OpenAI-compatible
# ---------------------------------------------------------------------------

class OpenAILLMService(LLMService):
    """OpenAI-compatible LLM backend."""

    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings
        self._client: Any = None
        logger.info(
            "LLM service configured: provider=%s model=%s base_url=%s",
            settings.provider,
            settings.model,
            settings.base_url or "(default)",
        )

    async def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise RuntimeError(
                "openai package is required for LLM integration. "
                "Install it with: pip install openai"
            )
        kwargs: dict[str, Any] = {"api_key": self.settings.api_key}
        if self.settings.base_url:
            kwargs["base_url"] = self.settings.base_url
        self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        robot_id: str = "",
        robot_state: dict[str, Any] | None = None,
    ) -> LLMResponse:
        client = await self._ensure_client()

        system_prompt = self.settings.system_prompt or SYSTEM_PROMPT
        if robot_state:
            state_text = json.dumps(robot_state, ensure_ascii=False, indent=2)
            system_prompt += "\n\nCurrent robot state:\n" + state_text

        full_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        full_messages.extend(messages)

        functions = build_function_list()

        try:
            completion = await client.chat.completions.create(
                model=self.settings.model,
                messages=full_messages,
                tools=functions,
                tool_choice="auto",
                temperature=self.settings.temperature,
                max_tokens=self.settings.max_tokens,
            )
        except Exception as exc:
            logger.exception("LLM API call failed")
            return LLMResponse(text=f"LLM call failed: {exc}")

        choice = completion.choices[0]
        message = choice.message

        response = LLMResponse(
            text=message.content or "",
            raw_response=completion.model_dump(),
        )

        if message.tool_calls:
            for tool_call in message.tool_calls:
                task = self._tool_call_to_task(tool_call)
                if task is not None:
                    response.tasks.append(task)

        return response

    def _tool_call_to_task(self, tool_call: Any) -> CreateTaskRequest | None:
        func_name = tool_call.function.name
        try:
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            logger.warning("Failed to parse tool call args: %s", tool_call.function.arguments)
            return None

        skill_map: dict[str, SkillName] = {
            "move": SkillName.MOVE,
            "stop": SkillName.STOP,
            "gesture": SkillName.GESTURE,
            "play_teach": SkillName.PLAY_TEACH,
            "speak": SkillName.SPEAK,
            "interrupt": SkillName.INTERRUPT_TASK,
        }
        skill = skill_map.get(func_name)
        if skill is None:
            logger.warning("Unknown tool call function: %s", func_name)
            return None

        # Hard validate LLM parameters before dispatch
        ok, err_msg = _validate_skill_params(func_name, arguments)
        if not ok:
            logger.warning("LLM param validation failed for %s: %s", func_name, err_msg)
            return None

        return CreateTaskRequest(
            skill=skill,
            params=arguments,
            source=TaskSource(type="llm", name="llm"),
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------



def _validate_skill_params(func_name: str, args: dict[str, Any]) -> tuple[bool, str]:
    """Hard validate LLM tool call parameters before dispatching.

    Returns (ok, error_message).

    SAFETY NOTE (from Bumi delivery manual):
    - Speed values are NORMALIZED coefficients (-1.0 to 1.0), NOT meters/radians.
    - Reference: controlcmd.axes()[] = [-1.0, 1.0] range from joystick mapping.
    - Internal limits are conservative (0.2/0.3) for safe operation.
    - Even if LLM hallucinates, this layer catches before reaching the robot.
    """
    if func_name == "move":
        x = args.get("x", 0)
        yaw = args.get("yaw", 0)
        dur = args.get("duration_ms", 2000)
        if not isinstance(x, (int, float)):
            return False, "move x must be a number, got %s" % type(x).__name__
        if not isinstance(yaw, (int, float)):
            return False, "move yaw must be a number, got %s" % type(yaw).__name__
        if abs(float(x)) > 0.2:
            return False, "SAFETY: move x=%.2f exceeds normalized speed limit \u00b10.2" % float(x)
        if abs(float(yaw)) > 0.3:
            return False, "SAFETY: move yaw=%.2f exceeds normalized speed limit \u00b10.3" % float(yaw)
        if not isinstance(dur, int) or dur < 100 or dur > 10000:
            return False, "move duration_ms must be 100-10000, got %s" % dur

    elif func_name == "gesture":
        name = args.get("name", "")
        allowed = {"wave_hand", "shake_hand", "cheer", "tear"}
        if name not in allowed:
            return False, "gesture name '%s' not allowed, must be one of %s" % (name, allowed)

    elif func_name == "play_teach":
        index = args.get("index", 0)
        if not isinstance(index, int) or index < 1 or index > 100:
            return False, "play_teach index must be 1-100, got %s" % index

    elif func_name == "speak":
        text = args.get("text", "")
        if not text or not isinstance(text, str):
            return False, "speak text is required and must be a string"
        if len(text) > 500:
            return False, "speak text too long (%d chars, max 500)" % len(text)

    elif func_name in ("stop", "interrupt"):
        pass

    return True, ""

def build_llm_service(settings: LLMSettings) -> LLMService:
    if settings.api_key:
        logger.info("LLM_API_KEY detected, using OpenAILLMService")
        return OpenAILLMService(settings)
    logger.info("No LLM_API_KEY set, using PlaceholderLLMService")
    return PlaceholderLLMService(settings)
