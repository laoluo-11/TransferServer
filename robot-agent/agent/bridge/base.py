from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from shared.protocol.enums import MotionState, SafetyState, SpeechState


class BridgeExecutionError(RuntimeError):
    """Raised when the underlying robot bridge cannot execute a command."""


@dataclass(slots=True)
class BridgeSnapshot:
    connected: bool = False
    workmode: int = 0
    battery_percent: int = 100
    motion_state: MotionState = MotionState.IDLE
    speech_state: SpeechState = SpeechState.IDLE
    safety_state: SafetyState = SafetyState.NORMAL
    current_task_id: str | None = None
    last_detail: str = ""


class ControlBridge(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def get_snapshot(self) -> BridgeSnapshot: ...

    @abstractmethod
    async def set_current_task(self, task_id: str | None) -> None: ...

    @abstractmethod
    async def move(self, x: float, yaw: float, duration_ms: int) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def gesture(self, name: str) -> None: ...

    @abstractmethod
    async def play_teach(self, index: int) -> None: ...

    @abstractmethod
    async def speak(self, text: str, voice: str = "default") -> None: ...

    @abstractmethod
    async def safe_stop(self) -> None: ...
