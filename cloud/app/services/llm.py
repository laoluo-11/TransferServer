"""
LLM service with Agent Loop (ReAct pattern) for Bumi robot.

The core idea:
  LLM -> Think -> Call Tool -> Observe Result -> Think -> ... -> Respond

Two modes:
  - Placeholder: no API key, simulates the loop with keyword parsing
  - OpenAI: real LLM with ReAct loop
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable

from cloud.app.core.config import LLMSettings
from shared.llm import SYSTEM_PROMPT, build_function_list
from shared.protocol import CreateTaskRequest, TaskRecord, TaskSource
from shared.protocol.enums import SkillName, TaskStatus

logger = logging.getLogger("cloud.llm")


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class AgentStep:
    """One step in the agent loop."""

    def __init__(
        self,
        round_num: int,
        thought: str = "",
        function_name: str = "",
        function_args: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        error: str = "",
    ) -> None:
        self.round = round_num
        self.thought = thought
        self.function_name = function_name
        self.function_args = function_args or {}
        self.result = result or {}
        self.error = error

    @property
    def success(self) -> bool:
        return not self.error and self.result.get("status") == "success"

    def to_dict(self) -> dict[str, Any]:
        return {
            "round": self.round,
            "thought": self.thought,
            "function": self.function_name,
            "args": self.function_args,
            "result": self.result,
            "error": self.error,
        }


class AgentResponse:
    """Result of an agent loop invocation."""

    def __init__(
        self,
        text: str = "",
        steps: list[AgentStep] | None = None,
        raw: dict[str, Any] | None = None,
    ) -> None:
        self.text = text
        self.steps = steps or []
        self.raw = raw or {}


TaskExecutor = Callable[[CreateTaskRequest], Awaitable[dict[str, Any]]]


# ---------------------------------------------------------------------------
# Abstract
# ---------------------------------------------------------------------------


class LLMService(ABC):
    """Abstract LLM backend with agent loop capability."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        execute_task: TaskExecutor,
        *,
        robot_id: str = "",
        robot_state: dict[str, Any] | None = None,
    ) -> AgentResponse:
        ...

# ---------------------------------------------------------------------------
# Placeholder
# ---------------------------------------------------------------------------


class PlaceholderLLMService(LLMService):
    """Placeholder agent - simulates the ReAct loop without a real LLM."""

    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings
        logger.info("Agent Loop running in PLACEHOLDER mode")

    async def chat(
        self,
        messages: list[dict[str, Any]],
        execute_task: TaskExecutor,
        *,
        robot_id: str = "",
        robot_state: dict[str, Any] | None = None,
    ) -> AgentResponse:
        last_msg = _last_user_text(messages)
        steps: list[AgentStep] = []

        actions = _parse_simple_actions(last_msg)
        if not actions:
            return AgentResponse(
                text=_place_msg_no_action(last_msg),
                steps=[],
            )

        for i, (skill_name, params) in enumerate(actions):
            round_num = i + 1
            if round_num > self.settings.max_rounds:
                steps.append(AgentStep(
                    round_num,
                    thought=_place_max_rounds(self.settings.max_rounds),
                ))
                break

            step = AgentStep(
                round_num=round_num,
                thought=_place_thought(round_num, skill_name),
                function_name=skill_name,
                function_args=params,
            )
            steps.append(step)

            try:
                task_req = CreateTaskRequest(
                    skill=SkillName(skill_name),
                    params=params,
                    source=TaskSource(type="agent_loop", name="placeholder"),
                )
                result = await execute_task(task_req)
                step.result = result
            except Exception as exc:
                step.error = str(exc)
                step.result = {"status": "failed", "error": str(exc)}

        final_text = _place_summary(steps)
        return AgentResponse(text=final_text, steps=steps)


# ---------------------------------------------------------------------------
# OpenAI Agent Loop (ReAct)
# ---------------------------------------------------------------------------


class OpenAILLMService(LLMService):
    """Real OpenAI-compatible LLM backend with ReAct agent loop."""

    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings
        self._client: Any = None

    async def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise RuntimeError("pip install openai required for LLM integration")
        kwargs: dict[str, Any] = {"api_key": self.settings.api_key}
        if self.settings.base_url:
            kwargs["base_url"] = self.settings.base_url
        self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def chat(
        self,
        messages: list[dict[str, Any]],
        execute_task: TaskExecutor,
        *,
        robot_id: str = "",
        robot_state: dict[str, Any] | None = None,
    ) -> AgentResponse:
        client = await self._ensure_client()
        functions = build_function_list()

        system_prompt = self.settings.system_prompt or SYSTEM_PROMPT
        if robot_state:
            state_text = json.dumps(robot_state, ensure_ascii=False, indent=2)
            system_prompt += "\n\nCurrent robot state:\n" + state_text

        agent_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        agent_messages.extend(messages)

        steps: list[AgentStep] = []
        final_text = ""
        last_completion = None

        for round_num in range(1, self.settings.max_rounds + 1):
            try:
                last_completion = await client.chat.completions.create(
                    model=self.settings.model,
                    messages=agent_messages,
                    tools=functions,
                    tool_choice="auto",
                    temperature=self.settings.temperature,
                    max_tokens=self.settings.max_tokens,
                )
            except Exception as exc:
                logger.exception("LLM call failed at round %d", round_num)
                return AgentResponse(
                    text="LLM call failed (round %d): %s" % (round_num, exc),
                    steps=steps,
                )

            choice = last_completion.choices[0]
            msg = choice.message

            # No tool calls -> LLM is done
            if not msg.tool_calls:
                final_text = msg.content or ""
                agent_messages.append({"role": "assistant", "content": final_text})
                break

            # Process tool calls sequentially
            tool_results: list[dict[str, Any]] = []
            for tool_call in msg.tool_calls:
                func_name = tool_call.function.name
                try:
                    func_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    func_args = {}

                step = AgentStep(
                    round_num=round_num,
                    thought="call %s" % func_name,
                    function_name=func_name,
                    function_args=func_args,
                )

                try:
                    skill = _func_to_skill(func_name)
                    if skill is None:
                        step.error = "unknown skill: %s" % func_name
                        step.result = {"status": "failed", "error": step.error}
                    else:
                        ok, err_msg = _validate_skill_params(func_name, func_args)
                        if not ok:
                            step.error = err_msg
                            step.result = {"status": "rejected", "error": err_msg}
                            logger.warning(
                                "Agent round %d: LLM param validation failed for %s: %s",
                                round_num, func_name, err_msg,
                            )
                        else:
                            task_req = CreateTaskRequest(
                                skill=skill,
                                params=func_args,
                                source=TaskSource(type="agent_loop", name="openai"),
                            )
                            result = await execute_task(task_req)
                            step.result = result
                except Exception as exc:
                    step.error = str(exc)
                    step.result = {"status": "failed", "error": str(exc)}

                steps.append(step)
                tool_results.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "content": json.dumps(step.result, ensure_ascii=False),
                })

            # Add assistant tool_calls + results to conversation
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
            agent_messages.append(assistant_msg)
            for tr in tool_results:
                agent_messages.append(tr)

            logger.info(
                "Agent round %d/%d completed, %d tool calls",
                round_num, self.settings.max_rounds, len(tool_results),
            )

        else:
            final_text = "max rounds (%d) reached" % self.settings.max_rounds
            logger.warning("Agent hit max rounds (%d)", self.settings.max_rounds)

        return AgentResponse(
            text=final_text,
            steps=steps,
            raw=last_completion.model_dump() if last_completion else {},
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_llm_service(settings: LLMSettings) -> LLMService:
    if settings.api_key:
        logger.info("LLM_API_KEY detected -> OpenAILLMService (Agent Loop)")
        return OpenAILLMService(settings)
    logger.info("No LLM_API_KEY -> PlaceholderLLMService")
    return PlaceholderLLMService(settings)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return str(m.get("content", ""))
    return ""


def _func_to_skill(func_name: str) -> SkillName | None:
    mapping = {
        "move": SkillName.MOVE,
        "stop": SkillName.STOP,
        "gesture": SkillName.GESTURE,
        "play_teach": SkillName.PLAY_TEACH,
        "speak": SkillName.SPEAK,
        "interrupt": SkillName.INTERRUPT_TASK,
    }
    return mapping.get(func_name)


def _validate_skill_params(func_name: str, args: dict[str, Any]) -> tuple[bool, str]:
    """Hard validate LLM tool call parameters before dispatching.

    Returns (ok, error_message).
    Even if the LLM hallucinates params, this catches them before they reach the robot.
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
            return False, "move x=%.2f exceeds limit ±0.2" % float(x)
        if abs(float(yaw)) > 0.3:
            return False, "move yaw=%.2f exceeds limit ±0.3" % float(yaw)
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
        pass  # no params to validate

    return True, "" 


def _place_msg_no_action(last_msg: str) -> str:
    return (
        "[Agent Loop] \u6536\u5230\uff1a\u300c" + last_msg
        + "\u300d\u3002\u5f53\u524d\u672a\u8bc6\u522b\u5230\u5177\u4f53\u52a8\u4f5c\uff0c"
        "\u8bf7\u8bf4\u5f97\u66f4\u5177\u4f53\u4e00\u4e9b\uff0c"
        "\u6bd4\u5982\u300c\u5f80\u524d\u4e00\u6b65\uff0c"
        "\u7136\u540e\u6325\u624b\u8bf4\u4f60\u597d\u300d\u3002"
    )


def _place_max_rounds(max_r: int) -> str:
    return "max rounds %d reached" % max_r


def _place_thought(round_num: int, skill_name: str) -> str:
    return "round %d: execute %s" % (round_num, skill_name)


def _place_summary(steps: list[AgentStep]) -> str:
    lines = []
    for s in steps:
        if s.function_name:
            status = "OK" if s.success else "FAIL"
            args_s = json.dumps(s.function_args, ensure_ascii=False)
            lines.append("  [%s] round %d: %s %s" % (status, s.round, s.function_name, args_s))
    summary = "\n".join(lines)
    return (
        "[Agent Loop] " + str(len(steps)) + " actions:\n"
        + summary
        + "\n\nSet LLM_API_KEY to use real LLM."
    )


def _parse_simple_actions(text: str) -> list[tuple[str, dict[str, Any]]]:
    """Simple keyword parser for placeholder mode."""
    actions: list[tuple[str, dict[str, Any]]] = []
    text_lower = text.lower()

    # Safety first: stop/interrupt
    if any(w in text for w in ["\u505c\u4e0b", "\u505c\u6b62", "\u7d27\u6025", "\u4e2d\u65ad"]):
        return [("stop", {})]

    # Move detection
    move_keywords = ["\u524d\u8fdb", "\u5f80\u524d", "\u5411\u524d", "\u8d70", "\u540e\u9000", "\u5f80\u540e"]
    if any(w in text for w in move_keywords):
        x = 0.1
        yaw = 0.0
        if "\u540e\u9000" in text or "\u5f80\u540e" in text:
            x = -0.1
        if "\u5de6\u8f6c" in text or "\u5411\u5de6" in text:
            yaw = 0.2
        if "\u53f3\u8f6c" in text or "\u5411\u53f3" in text:
            yaw = -0.2
        actions.append(("move", {"x": x, "yaw": yaw, "duration_ms": 2000}))

    # Gesture detection
    if "\u6325\u624b" in text or "\u62db\u624b" in text:
        actions.append(("gesture", {"name": "wave_hand"}))
    elif "\u63e1\u624b" in text:
        actions.append(("gesture", {"name": "shake_hand"}))
    elif "\u6b22\u547c" in text:
        actions.append(("gesture", {"name": "cheer"}))

    # Speak detection
    speak_text = ""
    if "\u81ea\u6211\u4ecb\u7ecd" in text:
        speak_text = "\u4f60\u597d\uff0c\u6211\u662f Bumi \u4eba\u5f62\u673a\u5668\u4eba\uff0c\u5f88\u9ad8\u5174\u8ba4\u8bc6\u4f60\uff01"
    elif "\u4f60\u597d" in text or "\u6253\u62db\u547c" in text:
        speak_text = "\u4f60\u597d\uff01\u6709\u4ec0\u4e48\u53ef\u4ee5\u5e2e\u52a9\u4f60\u7684\u5417\uff1f"
    elif "\u8bf4" in text:
        m = re.search(r"\u8bf4[\uff1a:]\s*(.+)", text)
        if m:
            speak_text = m.group(1)
        else:
            m = re.search(r"\u8bf4[\u300c\u201c](.+?)[\u300d\u201d]", text)
            if m:
                speak_text = m.group(1)
    if speak_text:
        actions.append(("speak", {"text": speak_text}))

    # Play teach detection
    teach_match = re.search(r"\u793a\u6559\s*(\d+)", text)
    if teach_match:
        actions.append(("play_teach", {"index": int(teach_match.group(1))}))

    return actions
