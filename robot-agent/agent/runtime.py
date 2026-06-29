from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from typing import Any

import websockets
from websockets.client import WebSocketClientProtocol

from agent.bridge import BridgeExecutionError, build_bridge
from agent.config import AgentSettings
from shared.protocol import (
    AckPayload,
    AgentHelloPayload,
    AlertPayload,
    Envelope,
    HeartbeatPayload,
    InterruptResultPayload,
    RobotStatePayload,
    TaskCommandPayload,
    TaskEventPayload,
    TaskResultPayload,
    build_envelope,
    now_ms,
)
from shared.protocol.enums import (
    AlertLevel,
    MessageType,
    MotionState,
    SafetyState,
    SkillName,
    SpeechState,
    TaskStage,
    TaskStatus,
)
from shared.protocol.errors import ErrorCode, default_error_message


class RobotAgent:
    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings
        self.logger = logging.getLogger("robot-agent")
        self.bridge = build_bridge(settings)
        self.capabilities = [
            SkillName.MOVE,
            SkillName.STOP,
            SkillName.GESTURE,
            SkillName.PLAY_TEACH,
            SkillName.SPEAK,
            SkillName.INTERRUPT_TASK,
        ]
        self.state = RobotStatePayload(
            online=True,
            battery_percent=settings.battery_start_percent,
        )
        self.websocket: WebSocketClientProtocol | None = None
        self.execution_task: asyncio.Task[None] | None = None
        self._execution_task_id: str | None = None
        self._lock = asyncio.Lock()

    async def run_forever(self) -> None:
        while True:
            try:
                await self._run_once()
            except Exception as exc:  # pragma: no cover - keeps agent alive
                self.logger.exception("agent loop failed: %s", exc)
                await asyncio.sleep(2)

    async def _run_once(self) -> None:
        await self.bridge.connect()
        await self._sync_state_from_bridge()
        self.logger.info("connecting to %s", self.settings.websocket_url)
        try:
            async with websockets.connect(self.settings.websocket_url) as websocket:
                self.websocket = websocket
                await self._send_hello()
                heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                try:
                    async for raw_message in websocket:
                        envelope = Envelope.model_validate(json.loads(raw_message))
                        await self._handle_message(envelope)
                finally:
                    heartbeat_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await heartbeat_task
                    self.websocket = None
        finally:
            await self.bridge.close()
            await self._sync_state_from_bridge()

    async def _send_hello(self) -> None:
        payload = AgentHelloPayload(
            agent_version=self.settings.agent_version,
            sdk_version=self.settings.sdk_version,
            protocol_version=self.settings.protocol_version,
            capabilities=self.capabilities,
        )
        await self._send(build_envelope(MessageType.AGENT_HELLO, self.settings.robot_id, payload))
        await self._emit_state()

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.heartbeat_interval_seconds)
            await self._sync_state_from_bridge()
            heartbeat = HeartbeatPayload(
                status="online" if self.state.online else "offline",
                battery_percent=self.state.battery_percent,
                current_task_id=self.state.current_task_id,
                safety_state=self.state.safety_state,
            )
            await self._send(
                build_envelope(
                    MessageType.AGENT_HEARTBEAT,
                    self.settings.robot_id,
                    heartbeat,
                )
            )
            await self._emit_state()

    async def _handle_message(self, envelope: Envelope) -> None:
        if envelope.msg_type == MessageType.TASK_COMMAND:
            await self._handle_task_command(envelope)
        elif envelope.msg_type == MessageType.INTERRUPT_COMMAND:
            await self._handle_interrupt(envelope)
        elif envelope.msg_type == MessageType.TASK_ACK:
            self.logger.info("server ack received: %s", envelope.payload)

    async def _handle_task_command(self, envelope: Envelope) -> None:
        payload = TaskCommandPayload.model_validate(envelope.payload)
        await self._sync_state_from_bridge()
        accepted, error_code, reason = self._can_execute(payload)
        ack = AckPayload(
            ack_type="task_command",
            accepted=accepted,
            reason=reason,
            task_id=payload.task_id,
            error_code=int(error_code),
        )
        await self._send(
            build_envelope(
                MessageType.TASK_ACK,
                self.settings.robot_id,
                ack,
                trace_id=envelope.trace_id,
            )
        )
        if not accepted:
            await self._send_alert("TASK_REJECTED", reason, {"task_id": payload.task_id})
            return

        self.execution_task = asyncio.create_task(
            self._execute_task(payload, envelope.trace_id)
        )

    async def _handle_interrupt(self, envelope: Envelope) -> None:
        async with self._lock:
            running_task = self.execution_task
            running_task_id = self._execution_task_id
        if running_task is not None:
            running_task.cancel()
            await self._safe_stop()
            result = InterruptResultPayload(
                task_id=running_task_id,
                status="success",
                message="task interrupted and safe stop applied",
            )
        else:
            result = InterruptResultPayload(
                task_id=None,
                status="noop",
                message="no running task",
            )
        await self._send(
            build_envelope(
                MessageType.INTERRUPT_RESULT,
                self.settings.robot_id,
                result,
                trace_id=envelope.trace_id,
            )
        )

    def _can_execute(self, task: TaskCommandPayload) -> tuple[bool, ErrorCode, str]:
        if task.skill not in self.capabilities:
            return (
                False,
                ErrorCode.UNKNOWN_SKILL,
                default_error_message(ErrorCode.UNKNOWN_SKILL),
            )
        if self.execution_task is not None and not self.execution_task.done():
            return (
                False,
                ErrorCode.HIGH_PRIORITY_TASK_RUNNING,
                "another task is already running",
            )
        if task.skill in {SkillName.MOVE, SkillName.GESTURE, SkillName.PLAY_TEACH}:
            if self.state.battery_percent < 20:
                return (
                    False,
                    ErrorCode.LOW_BATTERY,
                    "battery too low for motion task",
                )
            if self.state.safety_state in {SafetyState.SAFE_STOP, SafetyState.FAULT}:
                return (
                    False,
                    ErrorCode.SAFETY_LOCKED,
                    "robot is safety locked",
                )
        return True, ErrorCode.SUCCESS, ""

    async def _execute_task(self, task: TaskCommandPayload, trace_id: str) -> None:
        started_at = asyncio.get_event_loop().time()
        async with self._lock:
            self._execution_task_id = task.task_id
            self.state.current_task_id = task.task_id
        await self.bridge.set_current_task(task.task_id)
        await self._sync_state_from_bridge()
        await self._emit_state()
        await self._send_task_event(task.task_id, TaskStage.STARTED, "task accepted")
        try:
            timeout_seconds = max(task.policy.timeout_ms / 1000, 0.1)
            await asyncio.wait_for(self._dispatch_skill(task), timeout=timeout_seconds)
            await self._send_task_event(task.task_id, TaskStage.COMPLETED, "task completed")
            await self._send_task_result(
                task.task_id,
                TaskStatus.SUCCESS,
                ErrorCode.SUCCESS,
                "task completed",
                {
                    "duration_ms": int(
                        (asyncio.get_event_loop().time() - started_at) * 1000
                    )
                },
                trace_id,
            )
        except asyncio.TimeoutError:
            await self._safe_stop()
            await self._send_task_result(
                task.task_id,
                TaskStatus.TIMEOUT,
                ErrorCode.TASK_TIMEOUT,
                "task timeout",
                {},
                trace_id,
            )
        except BridgeExecutionError as exc:
            self.logger.exception("bridge execution failed: %s", exc)
            await self._safe_stop()
            await self._send_task_event(task.task_id, TaskStage.FAILED, str(exc))
            await self._send_task_result(
                task.task_id,
                TaskStatus.FAILED,
                ErrorCode.SDK_CALL_FAILED,
                str(exc),
                {},
                trace_id,
            )
        except asyncio.CancelledError:
            await self._safe_stop()
            await self._send_task_event(task.task_id, TaskStage.INTERRUPTED, "task interrupted")
            await self._send_task_result(
                task.task_id,
                TaskStatus.INTERRUPTED,
                ErrorCode.TASK_INTERRUPTED,
                "task interrupted",
                {},
                trace_id,
            )
            raise
        except Exception as exc:  # pragma: no cover - task loop safety
            self.logger.exception("task execution failed: %s", exc)
            await self._safe_stop()
            await self._send_task_event(task.task_id, TaskStage.FAILED, str(exc))
            await self._send_task_result(
                task.task_id,
                TaskStatus.FAILED,
                ErrorCode.SDK_CALL_FAILED,
                str(exc),
                {},
                trace_id,
            )
        finally:
            await self.bridge.set_current_task(None)
            async with self._lock:
                self.state.current_task_id = None
                self._execution_task_id = None
                self.execution_task = None
            await self._sync_state_from_bridge()
            await self._emit_state()

    async def _dispatch_skill(self, task: TaskCommandPayload) -> None:
        await self._send_task_event(task.task_id, TaskStage.EXECUTING, task.skill.value)
        if task.skill == SkillName.MOVE:
            x = float(task.params.get("x", 0.0))
            yaw = float(task.params.get("yaw", 0.0))
            duration_ms = int(task.params.get("duration_ms", 1000))
            await self._send_task_event(
                task.task_id,
                TaskStage.MOTION_STARTED,
                f"x={x}, yaw={yaw}",
            )
            await self.bridge.move(x=x, yaw=yaw, duration_ms=duration_ms)
            await self._sync_state_from_bridge()
            return
        if task.skill == SkillName.STOP:
            await self.bridge.stop()
            await self._sync_state_from_bridge()
            await self._send_task_event(task.task_id, TaskStage.SAFE_STOP, "stop requested")
            return
        if task.skill == SkillName.GESTURE:
            gesture_name = str(task.params.get("name", "wave_hand"))
            await self._send_task_event(task.task_id, TaskStage.MOTION_STARTED, gesture_name)
            await self.bridge.gesture(gesture_name)
            await self._sync_state_from_bridge()
            return
        if task.skill == SkillName.PLAY_TEACH:
            index = int(task.params.get("index", 1))
            await self._send_task_event(
                task.task_id,
                TaskStage.MOTION_STARTED,
                f"teach index {index}",
            )
            await self.bridge.play_teach(index)
            await self._sync_state_from_bridge()
            return
        if task.skill == SkillName.SPEAK:
            text = str(task.params.get("text", ""))
            voice = str(task.params.get("voice", "default"))
            await self._send_task_event(task.task_id, TaskStage.SPEECH_STARTED, text[:60])
            await self.bridge.speak(text=text, voice=voice)
            await self._sync_state_from_bridge()
            return
        raise ValueError(f"unsupported skill: {task.skill}")

    async def _safe_stop(self) -> None:
        await self.bridge.safe_stop()
        await self._sync_state_from_bridge()
        await self._emit_state()

    async def _sync_state_from_bridge(self) -> None:
        snapshot = await self.bridge.get_snapshot()
        self.state.online = snapshot.connected
        self.state.workmode = snapshot.workmode
        self.state.battery_percent = snapshot.battery_percent
        self.state.motion_state = snapshot.motion_state
        self.state.speech_state = snapshot.speech_state
        self.state.safety_state = snapshot.safety_state
        if snapshot.current_task_id is not None or self.state.current_task_id is None:
            self.state.current_task_id = snapshot.current_task_id

    async def _send_task_event(self, task_id: str, stage: TaskStage, detail: str) -> None:
        payload = TaskEventPayload(task_id=task_id, stage=stage, detail=detail)
        await self._send(
            build_envelope(MessageType.TASK_EVENT, self.settings.robot_id, payload)
        )

    async def _send_task_result(
        self,
        task_id: str,
        status: TaskStatus,
        error_code: ErrorCode,
        message: str,
        metrics: dict[str, Any],
        trace_id: str,
    ) -> None:
        payload = TaskResultPayload(
            task_id=task_id,
            status=status,
            result_code=int(error_code),
            result_message=message,
            metrics=metrics,
        )
        await self._send(
            build_envelope(
                MessageType.TASK_RESULT,
                self.settings.robot_id,
                payload,
                trace_id=trace_id,
            )
        )

    async def _emit_state(self) -> None:
        self.state.updated_at = now_ms()
        payload = self.state.model_copy(update={"updated_at": self.state.updated_at})
        await self._send(
            build_envelope(MessageType.ROBOT_STATE, self.settings.robot_id, payload)
        )

    async def _send_alert(
        self,
        code: str,
        message: str,
        detail: dict[str, Any],
    ) -> None:
        payload = AlertPayload(
            level=AlertLevel.WARNING,
            code=code,
            message=message,
            detail=detail,
        )
        await self._send(build_envelope(MessageType.ALERT, self.settings.robot_id, payload))

    async def _send(self, envelope: Envelope) -> None:
        if self.websocket is None:
            return
        await self.websocket.send(envelope.model_dump_json())
