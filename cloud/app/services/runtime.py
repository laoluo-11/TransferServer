from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from shared.protocol import (
    AckPayload,
    AgentHelloPayload,
    AlertPayload,
    CreateTaskRequest,
    Envelope,
    HeartbeatPayload,
    InterruptRequest,
    RobotStatePayload,
    TaskCommandPayload,
    TaskEventPayload,
    TaskRecord,
    TaskResultPayload,
    build_envelope,
    new_task_record,
    now_ms,
)
from shared.protocol.enums import MessageType, TaskStage, TaskStatus


class CloudRuntime:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._robot_states: dict[str, RobotStatePayload] = {}
        self._capabilities: dict[str, list[str]] = {}
        self._tasks: dict[str, TaskRecord] = {}
        self._robot_tasks: dict[str, list[str]] = defaultdict(list)
        self._alerts: list[dict[str, Any]] = []
        self._logger = logging.getLogger("cloud.runtime")
        self._lock = asyncio.Lock()

    async def connect(self, robot_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[robot_id] = websocket
            state = self._robot_states.get(robot_id, RobotStatePayload(online=True))
            state.online = True
            state.updated_at = now_ms()
            self._robot_states[robot_id] = state

    async def disconnect(self, robot_id: str) -> None:
        async with self._lock:
            self._connections.pop(robot_id, None)
            state = self._robot_states.get(robot_id)
            if state is not None:
                state.online = False
                state.updated_at = now_ms()

    def get_robot_state(self, robot_id: str) -> RobotStatePayload:
        return self._robot_states.get(robot_id, RobotStatePayload(online=False))

    def get_capabilities(self, robot_id: str) -> list[str]:
        return self._capabilities.get(robot_id, [])

    def get_task(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def list_robots(self) -> list[dict[str, Any]]:
        robot_ids = set(self._robot_states) | set(self._connections) | set(self._capabilities)
        items: list[dict[str, Any]] = []
        for robot_id in sorted(robot_ids):
            state = self._robot_states.get(robot_id, RobotStatePayload(online=False))
            items.append(
                {
                    "robot_id": robot_id,
                    "online": state.online,
                    "battery_percent": state.battery_percent,
                    "safety_state": state.safety_state.value,
                    "current_task_id": state.current_task_id,
                    "capabilities": self.get_capabilities(robot_id),
                    "updated_at": state.updated_at,
                }
            )
        items.sort(key=lambda item: item["updated_at"], reverse=True)
        return items

    def list_tasks(self, *, robot_id: str | None = None, limit: int = 20) -> list[TaskRecord]:
        items = list(self._tasks.values())
        if robot_id is not None:
            items = [item for item in items if item.robot_id == robot_id]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return items[:limit]

    def list_alerts(self, *, robot_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        items = list(self._alerts)
        if robot_id is not None:
            items = [item for item in items if item["robot_id"] == robot_id]
        items.sort(key=lambda item: item["timestamp"], reverse=True)
        return items[:limit]

    async def create_task(self, robot_id: str, request: CreateTaskRequest) -> TaskRecord:
        task = new_task_record(robot_id, request)
        async with self._lock:
            self._tasks[task.task_id] = task
            self._robot_tasks[robot_id].append(task.task_id)
        await self.dispatch_task(task.task_id)
        return task

    async def dispatch_task(self, task_id: str) -> bool:
        async with self._lock:
            task = self._tasks[task_id]
            websocket = self._connections.get(task.robot_id)
            if websocket is None:
                task.status = TaskStatus.QUEUED
                task.updated_at = now_ms()
                return False
            task.status = TaskStatus.DISPATCHED
            task.updated_at = now_ms()
            envelope = build_envelope(
                MessageType.TASK_COMMAND,
                task.robot_id,
                TaskCommandPayload(
                    task_id=task.task_id,
                    skill=task.skill,
                    params=task.params,
                    policy=task.policy,
                    source=task.source,
                ),
                trace_id=task.trace_id,
            )
        await self._send_envelope(websocket, envelope)
        return True

    async def interrupt_robot(self, robot_id: str, request: InterruptRequest) -> bool:
        async with self._lock:
            websocket = self._connections.get(robot_id)
            if websocket is None:
                return False
            trace_id = f"interrupt_{now_ms()}"
            envelope = build_envelope(
                MessageType.INTERRUPT_COMMAND,
                robot_id,
                request,
                trace_id=trace_id,
            )
        await self._send_envelope(websocket, envelope)
        return True

    async def handle_agent_message(self, envelope: Envelope) -> None:
        handlers = {
            MessageType.AGENT_HELLO: self._handle_agent_hello,
            MessageType.AGENT_HEARTBEAT: self._handle_heartbeat,
            MessageType.ROBOT_STATE: self._handle_robot_state,
            MessageType.TASK_ACK: self._handle_task_ack,
            MessageType.TASK_EVENT: self._handle_task_event,
            MessageType.TASK_RESULT: self._handle_task_result,
            MessageType.ALERT: self._handle_alert,
        }
        handler = handlers.get(envelope.msg_type)
        if handler is not None:
            await handler(envelope)
        else:
            self._logger.warning(
                "unhandled msg_type=%s from robot=%s trace=%s",
                envelope.msg_type,
                envelope.robot_id,
                envelope.trace_id,
            )

    async def _handle_agent_hello(self, envelope: Envelope) -> None:
        payload = AgentHelloPayload.model_validate(envelope.payload)
        async with self._lock:
            self._capabilities[envelope.robot_id] = [
                capability.value for capability in payload.capabilities
            ]
            state = self._robot_states.get(envelope.robot_id, RobotStatePayload())
            state.online = True
            state.updated_at = now_ms()
            self._robot_states[envelope.robot_id] = state
            websocket = self._connections.get(envelope.robot_id)
        if websocket is not None:
            ack = build_envelope(
                MessageType.TASK_ACK,
                envelope.robot_id,
                AckPayload(
                    ack_type="agent_hello",
                    accepted=True,
                    reason="connected",
                ),
                trace_id=envelope.trace_id,
            )
            await self._send_envelope(websocket, ack)
        await self._flush_queued_tasks(envelope.robot_id)

    async def _handle_heartbeat(self, envelope: Envelope) -> None:
        payload = HeartbeatPayload.model_validate(envelope.payload)
        async with self._lock:
            state = self._robot_states.get(envelope.robot_id, RobotStatePayload())
            state.online = payload.status == "online"
            state.battery_percent = payload.battery_percent
            state.current_task_id = payload.current_task_id
            state.safety_state = payload.safety_state
            state.updated_at = now_ms()
            self._robot_states[envelope.robot_id] = state

    async def _handle_robot_state(self, envelope: Envelope) -> None:
        payload = RobotStatePayload.model_validate(envelope.payload)
        payload.updated_at = now_ms()
        async with self._lock:
            self._robot_states[envelope.robot_id] = payload

    async def _handle_task_ack(self, envelope: Envelope) -> None:
        payload = AckPayload.model_validate(envelope.payload)
        if payload.task_id is None:
            return
        async with self._lock:
            task = self._tasks.get(payload.task_id)
            if task is None:
                return
            task.status = TaskStatus.ACKED if payload.accepted else TaskStatus.REJECTED
            task.result_code = payload.error_code
            task.result_message = payload.reason
            task.updated_at = now_ms()

    async def _handle_task_event(self, envelope: Envelope) -> None:
        payload = TaskEventPayload.model_validate(envelope.payload)
        async with self._lock:
            task = self._tasks.get(payload.task_id)
            if task is None:
                return
            task.last_stage = payload.stage
            if payload.stage in {TaskStage.STARTED, TaskStage.EXECUTING}:
                task.status = TaskStatus.RUNNING
            task.updated_at = now_ms()

    async def _handle_task_result(self, envelope: Envelope) -> None:
        payload = TaskResultPayload.model_validate(envelope.payload)
        async with self._lock:
            task = self._tasks.get(payload.task_id)
            if task is None:
                return
            task.status = payload.status
            task.result_code = payload.result_code
            task.result_message = payload.result_message
            task.updated_at = now_ms()

    async def _handle_alert(self, envelope: Envelope) -> None:
        payload = AlertPayload.model_validate(envelope.payload)
        async with self._lock:
            self._alerts.append(
                {
                    "robot_id": envelope.robot_id,
                    "trace_id": envelope.trace_id,
                    "timestamp": envelope.timestamp,
                    **payload.model_dump(mode="json"),
                }
            )

    async def _flush_queued_tasks(self, robot_id: str) -> None:
        task_ids = list(self._robot_tasks.get(robot_id, []))
        for task_id in task_ids:
            task = self._tasks.get(task_id)
            if task is not None:
                if task.status == TaskStatus.QUEUED:
                    await self.dispatch_task(task_id)
                elif task.status == TaskStatus.DISPATCHED:
                    task.status = TaskStatus.QUEUED
                    task.updated_at = now_ms()
                    await self.dispatch_task(task_id)

    async def _send_envelope(self, websocket: WebSocket, envelope: Envelope) -> None:
        await websocket.send_text(envelope.model_dump_json())
