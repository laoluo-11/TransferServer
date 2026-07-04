from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict

from agent.bridge.base import BridgeExecutionError, BridgeSnapshot, ControlBridge
from agent.bridge.bumi_sdk import (
    ACTION_TO_WORKMODE,
    BumiHighControlAction,
    BumiSdkAdapter,
    HighControlCommand,
    PyBindBumiSdkAdapter,
    SdkRobotState,
    StubBumiSdkAdapter,
)
from agent.config import AgentSettings
from shared.protocol.enums import MotionState, SafetyState, SpeechState


class BumiHighControlBridge(ControlBridge):
    """
    Bridge for real Bumi robot integration via HighControl SDK.

    SAFETY NOTES (from Bumi delivery manual):
    - Speed values are NORMALIZED coefficients (-1.0 to 1.0), NOT meters/radians.
    - Move limits: x=±0.2, yaw=±0.3 are conservative defaults for safe operation.
    - After each action, must send DEFAULT (x=0, yaw=0) to stop movement.
    - PLAYTEACH is edge-triggered: send ONCE, then DEFAULT on subsequent cycles.
    - CRITICAL: publish_cmd(yaw, x, action, data) — axes[0]=yaw(转向), axes[1]=x(前进后退).
      Fixed per delivery manual p.27/31. Still verify direction on real robot first.
    - TEAR workmode=33 (擦眼泪动作), FALLTOSTAND=27, STANDTOFALL=28, DANCE1=31, DANCE2=32.
      All verified from workmode table p.28 of delivery manual.
    """

    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings
        self.logger = logging.getLogger("robot-agent.bridge.bumi")
        self.snapshot = BridgeSnapshot(
            connected=False,
            battery_percent=settings.battery_start_percent,
        )
        self._dds_adapter: BumiSdkAdapter = self._build_dds_adapter()
        self._state_poll_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        self.logger.info(
            "initializing Bumi bridge skeleton, dds_host=%s control_mode=%s",
            self.settings.dds_host,
            self.settings.control_mode,
        )
        await self._initialize_sdk_clients()
        self._dds_adapter.set_state_callback(self._on_sdk_state)
        await self._dds_adapter.connect()
        await self._refresh_sdk_state()
        self._state_poll_task = asyncio.create_task(self._poll_sdk_state_loop())
        self.snapshot.connected = True
        self.snapshot.last_detail = "bumi bridge initialized"

    async def close(self) -> None:
        self.logger.info("closing Bumi bridge skeleton")
        if self._state_poll_task is not None:
            self._state_poll_task.cancel()
            try:
                await self._state_poll_task
            except asyncio.CancelledError:
                pass
            self._state_poll_task = None
        await self._dds_adapter.close()
        self.snapshot.connected = False
        self.snapshot.last_detail = "bumi bridge closed"

    async def get_snapshot(self) -> BridgeSnapshot:
        return BridgeSnapshot(**asdict(self.snapshot))

    async def set_current_task(self, task_id: str | None) -> None:
        self.snapshot.current_task_id = task_id

    async def move(self, x: float, yaw: float, duration_ms: int) -> None:
        normalized_x = self._validate_linear_axis(x)
        normalized_yaw = self._validate_yaw_axis(yaw)
        self.snapshot.motion_state = (
            MotionState.WALKING
            if abs(normalized_x) >= abs(normalized_yaw)
            else MotionState.TURNING
        )
        self.snapshot.workmode = ACTION_TO_WORKMODE[BumiHighControlAction.WALK]
        self.snapshot.last_detail = f"bumi move x={normalized_x}, yaw={normalized_yaw}"
        await self._publish_walk_command(x=normalized_x, yaw=normalized_yaw)
        await asyncio.sleep(max(duration_ms / 1000, 0.1))
        await self.safe_stop()

    async def stop(self) -> None:
        await self.safe_stop()

    async def gesture(self, name: str) -> None:
        self.snapshot.motion_state = MotionState.GESTURE_RUNNING
        self.snapshot.last_detail = f"bumi gesture {name}"
        await self._publish_action(name)
        await asyncio.sleep(2)
        self.snapshot.motion_state = MotionState.IDLE
        self.snapshot.workmode = 0

    async def play_teach(self, index: int) -> None:
        self.snapshot.motion_state = MotionState.TEACH_PLAYING
        self.snapshot.last_detail = f"bumi play teach index={index}"
        await self._publish_play_teach(index)
        await asyncio.sleep(3)
        self.snapshot.motion_state = MotionState.IDLE
        self.snapshot.workmode = 0

    async def speak(self, text: str, voice: str = "default") -> None:
        self.snapshot.speech_state = SpeechState.SPEAKING
        self.snapshot.last_detail = f"bumi speak voice={voice}"
        await self._play_tts(text=text, voice=voice)
        await asyncio.sleep(max(min(len(text) * 0.06, 4.0), 0.5))
        self.snapshot.speech_state = SpeechState.IDLE

    async def safe_stop(self) -> None:
        self.snapshot.motion_state = MotionState.STOPPING
        self.snapshot.safety_state = SafetyState.SAFE_STOP
        self.snapshot.last_detail = "bumi safe stop"
        await self._publish_stop_command()
        await asyncio.sleep(0.1)
        self.snapshot.motion_state = MotionState.IDLE
        self.snapshot.safety_state = SafetyState.NORMAL
        self.snapshot.speech_state = SpeechState.IDLE
        self.snapshot.workmode = 0

    async def _initialize_sdk_clients(self) -> None:
        self.logger.info(
            "initialize Bumi SDK domain_id=%s network_interface=%s sdk_root_dir=%s sdk_build_dir=%s dds_config_path=%s",
            self.settings.dds_domain_id,
            self.settings.dds_network_interface or "<default>",
            self.settings.sdk_root_dir or "<auto>",
            self.settings.sdk_build_dir or "<auto>",
            self.settings.dds_config_path or "<auto>",
        )

    def _build_dds_adapter(self) -> BumiSdkAdapter:
        if self.settings.bridge_mode == "bumi_stub":
            return StubBumiSdkAdapter(self.logger)
        if self.settings.bridge_mode == "bumi":
            return PyBindBumiSdkAdapter(
                self.logger,
                sdk_root_dir=self.settings.sdk_root_dir,
                sdk_build_dir=self.settings.sdk_build_dir,
                dds_config_path=self.settings.dds_config_path,
                sdk_module_name=self.settings.sdk_module_name,
            )
        return StubBumiSdkAdapter(self.logger)

    async def _poll_sdk_state_loop(self) -> None:
        while True:
            await asyncio.sleep(max(self.settings.state_poll_interval_seconds, 0.05))
            await self._refresh_sdk_state()

    async def _refresh_sdk_state(self) -> None:
        state = await self._dds_adapter.get_latest_state()
        await self._on_sdk_state(state)

    async def _on_sdk_state(self, state: SdkRobotState) -> None:
        self.snapshot.connected = state.connected
        self.snapshot.workmode = state.workmode
        self.snapshot.battery_percent = state.battery_percent
        self.snapshot.safety_state = self._derive_safety_state(state)
        self.snapshot.motion_state = self._derive_motion_state(state.workmode)
        if self.snapshot.speech_state != SpeechState.SPEAKING:
            self.snapshot.speech_state = SpeechState.IDLE
        if state.last_error:
            self.snapshot.last_detail = state.last_error

    def _derive_safety_state(self, state: SdkRobotState) -> SafetyState:
        if not state.connected or state.motor_error:
            return SafetyState.FAULT
        if not state.imu_ok:
            return SafetyState.WARNING
        return SafetyState.NORMAL

    def _derive_motion_state(self, workmode: int) -> MotionState:
        if workmode == ACTION_TO_WORKMODE[BumiHighControlAction.WALK]:
            return MotionState.WALKING
        if workmode in {
            ACTION_TO_WORKMODE[BumiHighControlAction.SWING],
            ACTION_TO_WORKMODE[BumiHighControlAction.SHAKE],
            ACTION_TO_WORKMODE[BumiHighControlAction.CHEER],
            ACTION_TO_WORKMODE[BumiHighControlAction.TEAR],
        }:
            return MotionState.GESTURE_RUNNING
        if workmode == ACTION_TO_WORKMODE[BumiHighControlAction.PLAYTEACH]:
            return MotionState.TEACH_PLAYING
        return MotionState.IDLE

    def _validate_linear_axis(self, value: float) -> float:
        if abs(value) > self.settings.move_x_limit:
            raise BridgeExecutionError(
                f"move x exceeds limit {self.settings.move_x_limit}: {value}"
            )
        return value

    def _validate_yaw_axis(self, value: float) -> float:
        if abs(value) > self.settings.move_yaw_limit:
            raise BridgeExecutionError(
                f"move yaw exceeds limit {self.settings.move_yaw_limit}: {value}"
            )
        return value

    def _build_walk_command(self, *, x: float, yaw: float) -> HighControlCommand:
        return HighControlCommand(
            yaw=yaw,
            x=x,
            action=BumiHighControlAction.WALK,
            data=0,
        )

    def _build_default_command(self) -> HighControlCommand:
        return HighControlCommand(
            yaw=0.0,
            x=0.0,
            action=BumiHighControlAction.DEFAULT,
            data=0,
        )

    def _build_action_command(self, action: BumiHighControlAction) -> HighControlCommand:
        return HighControlCommand(
            yaw=0.0,
            x=0.0,
            action=action,
            data=0,
        )

    def _build_play_teach_command(self, index: int) -> HighControlCommand:
        return HighControlCommand(
            yaw=0.0,
            x=0.0,
            action=BumiHighControlAction.PLAYTEACH,
            data=index,
        )

    async def _publish_control_command(self, command: HighControlCommand) -> None:
        await self._dds_adapter.publish_control_command(command)
        await self._refresh_sdk_state()

    async def _publish_walk_command(self, *, x: float, yaw: float) -> None:
        command = self._build_walk_command(x=x, yaw=yaw)
        self.logger.info(
            "publish Highcontrol WALK skeleton x=%s yaw=%s dds_host=%s",
            x,
            yaw,
            self.settings.dds_host,
        )
        await self._publish_control_command(command)

    async def _publish_stop_command(self) -> None:
        self.logger.info("publish Highcontrol DEFAULT stop skeleton")
        await self._publish_control_command(self._build_default_command())

    async def _publish_action(self, action_name: str) -> None:
        action_map = {
            "wave_hand": BumiHighControlAction.SWING,
            "shake_hand": BumiHighControlAction.SHAKE,
            "cheer": BumiHighControlAction.CHEER,
            "tear": BumiHighControlAction.TEAR,
        }
        action = action_map.get(action_name)
        if action is None:
            raise BridgeExecutionError(f"unsupported Bumi gesture: {action_name}")
        self.snapshot.workmode = ACTION_TO_WORKMODE.get(action, self.snapshot.workmode)
        self.logger.info("publish Highcontrol gesture skeleton action=%s", action.name)
        await self._publish_edge_trigger_command(self._build_action_command(action))

    async def _publish_play_teach(self, index: int) -> None:
        self.snapshot.workmode = ACTION_TO_WORKMODE[BumiHighControlAction.PLAYTEACH]
        self.logger.info("publish Highcontrol PLAYTEACH skeleton index=%s", index)
        await self._publish_edge_trigger_command(self._build_play_teach_command(index))

    async def _publish_edge_trigger_command(self, command: HighControlCommand) -> None:
        await self._publish_control_command(command)
        await asyncio.sleep(max(self.settings.action_edge_delay_ms, 10) / 1000)
        await self._publish_control_command(self._build_default_command())

    async def _play_tts(self, *, text: str, voice: str) -> None:
        self.logger.info(
            "TODO: invoke local or cloud TTS mode=%s voice=%s text=%s",
            self.settings.tts_mode,
            voice,
            text[:80],
        )
