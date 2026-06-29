from __future__ import annotations

import inspect
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Awaitable, Callable


class BumiHighControlAction(IntEnum):
    WALK = 0
    SWING = 1
    SHAKE = 2
    CHEER = 3
    RUN = 4
    START = 5
    SWITCH = 6
    STARTTEACH = 7
    SAVETEACH = 8
    ENDTEACH = 9
    PLAYTEACH = 10
    DANCE = 11
    FALLTOSTAND = 12
    STANDTOFALL = 13
    DANCE1 = 14
    DANCE2 = 15
    TEAR = 16
    DEFAULT = 17


ACTION_TO_WORKMODE: dict[BumiHighControlAction, int] = {
    BumiHighControlAction.DEFAULT: 0,
    BumiHighControlAction.WALK: 2,
    BumiHighControlAction.SWING: 8,
    BumiHighControlAction.SHAKE: 9,
    BumiHighControlAction.CHEER: 10,
    BumiHighControlAction.STARTTEACH: 11,
    BumiHighControlAction.PLAYTEACH: 13,
    BumiHighControlAction.DANCE: 5,
    BumiHighControlAction.FALLTOSTAND: 12,
    BumiHighControlAction.STANDTOFALL: 14,
    BumiHighControlAction.DANCE1: 15,
    BumiHighControlAction.DANCE2: 16,
    BumiHighControlAction.TEAR: 17,
}


@dataclass(slots=True)
class HighControlCommand:
    yaw: float = 0.0
    x: float = 0.0
    action: BumiHighControlAction = BumiHighControlAction.DEFAULT
    data: int = 0


@dataclass(slots=True)
class SdkRobotState:
    connected: bool = False
    workmode: int = 0
    battery_percent: int = 100
    imu_ok: bool = True
    motor_error: bool = False
    last_error: str = ""
    extra: dict[str, object] = field(default_factory=dict)


StateCallback = Callable[[SdkRobotState], Awaitable[None] | None]


class BumiSdkAdapter(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def publish_control_command(self, command: HighControlCommand) -> None: ...

    @abstractmethod
    async def get_latest_state(self) -> SdkRobotState: ...

    @abstractmethod
    def set_state_callback(self, callback: StateCallback) -> None: ...


class StubBumiSdkAdapter(BumiSdkAdapter):
    """
    Placeholder adapter for future DDS SDK integration.

    Replace this class with a real implementation that binds to:
    - DDS wrapper / CycloneDDS topics
    - Highcontrol publish API
    - robot state callback subscription
    """

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger
        self._callback: StateCallback | None = None
        self._state = SdkRobotState(connected=False)

    async def connect(self) -> None:
        self.logger.info("stub DDS adapter connected")
        self._state.connected = True
        await self._emit_state()

    async def close(self) -> None:
        self._state.connected = False
        await self._emit_state()
        self.logger.info("stub DDS adapter closed")

    async def publish_control_command(self, command: HighControlCommand) -> None:
        self.logger.info(
            "stub publish Highcontrol command yaw=%s x=%s action=%s data=%s",
            command.yaw,
            command.x,
            command.action.name,
            command.data,
        )
        self._state.workmode = ACTION_TO_WORKMODE.get(command.action, self._state.workmode)
        await self._emit_state()

    async def get_latest_state(self) -> SdkRobotState:
        return SdkRobotState(
            connected=self._state.connected,
            workmode=self._state.workmode,
            battery_percent=self._state.battery_percent,
            imu_ok=self._state.imu_ok,
            motor_error=self._state.motor_error,
            last_error=self._state.last_error,
            extra=dict(self._state.extra),
        )

    def set_state_callback(self, callback: StateCallback) -> None:
        self._callback = callback

    async def _emit_state(self) -> None:
        if self._callback is None:
            return
        result = self._callback(await self.get_latest_state())
        if inspect.isawaitable(result):
            await result
