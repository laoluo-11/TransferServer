from __future__ import annotations

import asyncio
from dataclasses import asdict

from agent.bridge.base import BridgeSnapshot, ControlBridge
from agent.config import AgentSettings
from shared.protocol.enums import MotionState, SafetyState, SpeechState


class MockControlBridge(ControlBridge):
    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings
        self.snapshot = BridgeSnapshot(
            connected=False,
            battery_percent=settings.battery_start_percent,
        )

    async def connect(self) -> None:
        self.snapshot.connected = True
        self.snapshot.last_detail = "mock bridge connected"

    async def close(self) -> None:
        self.snapshot.connected = False
        self.snapshot.last_detail = "mock bridge closed"

    async def get_snapshot(self) -> BridgeSnapshot:
        return BridgeSnapshot(**asdict(self.snapshot))

    async def set_current_task(self, task_id: str | None) -> None:
        self.snapshot.current_task_id = task_id

    async def move(self, x: float, yaw: float, duration_ms: int) -> None:
        self.snapshot.motion_state = (
            MotionState.WALKING if abs(x) >= abs(yaw) else MotionState.TURNING
        )
        self.snapshot.workmode = 2
        self.snapshot.last_detail = f"mock move x={x}, yaw={yaw}"
        await asyncio.sleep(max(duration_ms / 1000, 0.1))
        self.snapshot.motion_state = MotionState.IDLE
        self.snapshot.workmode = 0

    async def stop(self) -> None:
        await self.safe_stop()

    async def gesture(self, name: str) -> None:
        self.snapshot.motion_state = MotionState.GESTURE_RUNNING
        self.snapshot.workmode = 8
        self.snapshot.last_detail = f"mock gesture {name}"
        await asyncio.sleep(2)
        self.snapshot.motion_state = MotionState.IDLE
        self.snapshot.workmode = 0

    async def play_teach(self, index: int) -> None:
        self.snapshot.motion_state = MotionState.TEACH_PLAYING
        self.snapshot.workmode = 12
        self.snapshot.last_detail = f"mock play teach index={index}"
        await asyncio.sleep(3)
        self.snapshot.motion_state = MotionState.IDLE
        self.snapshot.workmode = 0

    async def speak(self, text: str, voice: str = "default") -> None:
        self.snapshot.speech_state = SpeechState.SPEAKING
        self.snapshot.last_detail = f"mock speak voice={voice} text={text[:40]}"
        await asyncio.sleep(max(min(len(text) * 0.06, 4.0), 0.5))
        self.snapshot.speech_state = SpeechState.IDLE

    async def safe_stop(self) -> None:
        self.snapshot.motion_state = MotionState.STOPPING
        self.snapshot.safety_state = SafetyState.SAFE_STOP
        self.snapshot.last_detail = "mock safe stop"
        await asyncio.sleep(0.1)
        self.snapshot.motion_state = MotionState.IDLE
        self.snapshot.speech_state = SpeechState.IDLE
        self.snapshot.safety_state = SafetyState.NORMAL
        self.snapshot.workmode = 0
