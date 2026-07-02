from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from types import ModuleType
from typing import Any, Awaitable, Callable


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
    BumiHighControlAction.TEAR: 17,  # WARNING: workmode 17 NOT listed in delivery manual's workmode table. VERIFY with real robot.
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

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SDK_ROOT_NAME = "noetix_sdk_bumi-main"


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


class PyBindBumiSdkAdapter(BumiSdkAdapter):
    """
    Adapter for the Python bindings shipped with the Noetix Bumi DDS SDK.

    The SDK exposes a compiled `highcontrol_py` module that internally speaks
    DDS to the robot runtime. This adapter focuses on:
    - locating/importing the compiled pybind module
    - configuring `CYCLONEDDS_URI`
    - translating bridge commands into `HighController.publish_cmd(...)`
    - polling the latest robot state into the shared protocol snapshot
    """

    def __init__(
        self,
        logger: logging.Logger,
        *,
        sdk_root_dir: str = "",
        sdk_build_dir: str = "",
        dds_config_path: str = "",
        sdk_module_name: str = "highcontrol_py",
    ) -> None:
        self.logger = logger
        self.sdk_root_dir = sdk_root_dir
        self.sdk_build_dir = sdk_build_dir
        self.dds_config_path = dds_config_path
        self.sdk_module_name = sdk_module_name
        self._callback: StateCallback | None = None
        self._state = SdkRobotState(connected=False)
        self._lock = asyncio.Lock()
        self._module: ModuleType | None = None
        self._controller: Any | None = None
        self._resolved_build_dir: Path | None = None
        self._resolved_dds_config_path: Path | None = None
        self._cyclonedds_uri: str = os.getenv("CYCLONEDDS_URI", "")

    async def connect(self) -> None:
        snapshot: SdkRobotState
        connect_error: RuntimeError | None = None
        async with self._lock:
            if self._controller is not None and self._state.connected:
                snapshot = self._clone_state()
            else:
                try:
                    self._configure_dds_environment()
                    self._module = self._import_sdk_module()
                    controller_cls = getattr(self._module, "HighController", None)
                    if controller_cls is None:
                        raise RuntimeError(
                            f"{self.sdk_module_name} does not export HighController"
                        )
                    self._controller = controller_cls.instance()
                    init_result = self._controller.init()
                    if init_result is False:
                        raise RuntimeError("HighController.init() returned false")
                    self._state.connected = True
                    self._state.last_error = ""
                    self._state.extra.update(
                        {
                            "sdk_module": self.sdk_module_name,
                            "sdk_build_dir": str(self._resolved_build_dir or ""),
                            "dds_config_path": str(self._resolved_dds_config_path or ""),
                            "cyclonedds_uri": self._cyclonedds_uri,
                        }
                    )
                    self._refresh_state_from_sdk()
                    self.logger.info(
                        "Bumi SDK connected module=%s build_dir=%s",
                        self.sdk_module_name,
                        self._resolved_build_dir or "<sys.path>",
                    )
                    snapshot = self._clone_state()
                except Exception as exc:
                    self._controller = None
                    self._module = None
                    self._mark_error(f"Bumi SDK connect failed: {exc}", disconnect=True)
                    snapshot = self._clone_state()
                    connect_error = RuntimeError(snapshot.last_error)
                    connect_error.__cause__ = exc
        await self._emit_state(snapshot)
        if connect_error is not None:
            raise connect_error

    async def close(self) -> None:
        async with self._lock:
            if self._controller is not None and self._module is not None:
                try:
                    default_action = getattr(self._module.ControlCmd, "DEFAULT")
                    # Send x=0, yaw=0, action=DEFAULT to stop — per delivery manual spec
                    self._controller.publish_cmd(0.0, 0.0, default_action, 0)
                except Exception as exc:
                    self.logger.warning("failed to send SDK default stop during close: %s", exc)
            self._controller = None
            self._state.connected = False
            self._state.workmode = 0
            self._state.last_error = ""
            snapshot = self._clone_state()
        await self._emit_state(snapshot)
        self.logger.info("Bumi SDK adapter closed")

    async def publish_control_command(self, command: HighControlCommand) -> None:
        publish_error: RuntimeError | None = None
        async with self._lock:
            controller = self._require_controller()
            module = self._require_module()
            try:
                sdk_action = getattr(module.ControlCmd, command.action.name)
                # CRITICAL: verify parameter order with real robot.
                # Bumi delivery manual C++ code:
                #   controlcmd.axes()[0] = cmd.yaw;   // turning
                #   controlcmd.axes()[1] = cmd.x;     // forward/backward
                # If pybind passes (param1, param2) -> (axes[0], axes[1]), then
                # x and yaw are SWAPPED below. TEST: send move(x=0.2,yaw=0) and
                # verify robot moves FORWARD (not turns).
                controller.publish_cmd(
                    float(command.x),
                    float(command.yaw),
                    sdk_action,
                    int(command.data),
                )
                self._state.connected = True
                self._state.workmode = ACTION_TO_WORKMODE.get(
                    command.action,
                    self._state.workmode,
                )
                self._state.last_error = ""
                self._refresh_state_from_sdk()
            except Exception as exc:
                self._mark_error(f"Bumi SDK publish failed: {exc}", disconnect=True)
                snapshot = self._clone_state()
                publish_error = RuntimeError(snapshot.last_error)
                publish_error.__cause__ = exc
            snapshot = self._clone_state()
        await self._emit_state(snapshot)
        if publish_error is not None:
            raise publish_error

    async def get_latest_state(self) -> SdkRobotState:
        async with self._lock:
            if self._controller is not None:
                try:
                    self._refresh_state_from_sdk()
                except Exception as exc:
                    self._mark_error(f"Bumi SDK state refresh failed: {exc}", disconnect=True)
                    self.logger.warning("failed to refresh Bumi SDK state: %s", exc)
            return self._clone_state()

    def set_state_callback(self, callback: StateCallback) -> None:
        self._callback = callback

    def _refresh_state_from_sdk(self) -> None:
        controller = self._require_controller()
        battery_data = controller.get_robot_bms_data()
        imu_data = controller.get_imu_data()
        joint_states = list(controller.get_joint_state())
        workmode = int(controller.get_mode())

        battery_percent = self._safe_int(
            self._read_attr(battery_data, "battery_soc", "battery_soc_"),
            default=self._state.battery_percent,
        )
        battery_alarm = self._safe_int(
            self._read_attr(battery_data, "battery_alarm", "battery_alarm_"),
            default=0,
        )
        battery_temperature = self._safe_int(
            self._read_attr(battery_data, "battery_temp", "battery_temp_"),
            default=0,
        )
        battery_soh = self._safe_int(
            self._read_attr(battery_data, "battery_soh", "battery_soh_"),
            default=0,
        )

        orientation = self._read_vector_attr(imu_data, "ori")
        angular_velocity = self._read_vector_attr(imu_data, "angular_vel")
        linear_acceleration = self._read_vector_attr(imu_data, "linear_acc")
        imu_ok = len(orientation) == 4 and len(angular_velocity) == 3 and len(linear_acceleration) == 3

        motor_error = any(self._safe_int(getattr(state, "error", 0), 0) != 0 for state in joint_states)
        max_motor_temperature = max(
            (float(getattr(state, "temperature", 0.0)) for state in joint_states),
            default=0.0,
        )

        extra = dict(self._state.extra)
        extra.update(
            {
                "sdk_module": self.sdk_module_name,
                "sdk_build_dir": str(self._resolved_build_dir or ""),
                "dds_config_path": str(self._resolved_dds_config_path or ""),
                "cyclonedds_uri": self._cyclonedds_uri,
                "battery_alarm": battery_alarm,
                "battery_temp": battery_temperature,
                "battery_soh": battery_soh,
                "joint_count": len(joint_states),
                "max_motor_temp": max_motor_temperature,
                "imu_orientation": orientation,
                "imu_angular_vel": angular_velocity,
                "imu_linear_acc": linear_acceleration,
            }
        )

        self._state.connected = True
        self._state.workmode = workmode
        self._state.battery_percent = battery_percent
        self._state.imu_ok = imu_ok
        self._state.motor_error = motor_error
        self._state.last_error = ""
        self._state.extra = extra

    def _configure_dds_environment(self) -> None:
        explicit_dds_path = self.dds_config_path.strip()
        existing_uri = os.getenv("CYCLONEDDS_URI", "").strip()
        dds_config_path: Path | None = None

        if explicit_dds_path:
            dds_config_path = Path(explicit_dds_path).expanduser().resolve()
            if not dds_config_path.is_file():
                raise RuntimeError(
                    f"BUMI_DDS_CONFIG_PATH does not exist: {dds_config_path}"
                )
        elif existing_uri:
            self._cyclonedds_uri = existing_uri
            self.logger.info("using existing CYCLONEDDS_URI=%s", existing_uri)
            return
        else:
            for candidate in self._candidate_dds_config_paths():
                if candidate.is_file():
                    dds_config_path = candidate
                    break

        if dds_config_path is None:
            self.logger.warning(
                "dds.xml not found and CYCLONEDDS_URI is unset; SDK init may fail"
            )
            self._resolved_dds_config_path = None
            self._cyclonedds_uri = existing_uri
            return

        self._resolved_dds_config_path = dds_config_path
        self._cyclonedds_uri = f"file://{dds_config_path.resolve().as_posix()}"
        os.environ["CYCLONEDDS_URI"] = self._cyclonedds_uri
        self.logger.info("configured CYCLONEDDS_URI=%s", self._cyclonedds_uri)

    def _import_sdk_module(self) -> ModuleType:
        if self.sdk_build_dir.strip():
            explicit_build_dir = Path(self.sdk_build_dir).expanduser().resolve()
            if not explicit_build_dir.is_dir():
                raise RuntimeError(
                    f"BUMI_SDK_BUILD_DIR does not exist: {explicit_build_dir}"
                )
        if self.sdk_root_dir.strip():
            explicit_sdk_root = Path(self.sdk_root_dir).expanduser().resolve()
            if not explicit_sdk_root.is_dir():
                raise RuntimeError(
                    f"BUMI_SDK_ROOT_DIR does not exist: {explicit_sdk_root}"
                )

        candidate_dirs = self._candidate_sdk_build_dirs()
        searched_dirs: list[str] = []
        self._resolved_build_dir = None
        for candidate in candidate_dirs:
            if not candidate.is_dir():
                continue
            searched_dirs.append(str(candidate))
            candidate_str = str(candidate)
            if candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)
            if self._resolved_build_dir is None:
                self._resolved_build_dir = candidate

        try:
            return importlib.import_module(self.sdk_module_name)
        except Exception as exc:
            search_summary = ", ".join(searched_dirs) if searched_dirs else "<none>"
            raise RuntimeError(
                "unable to import Bumi SDK module "
                f"{self.sdk_module_name!r}; searched build dirs: {search_summary}. "
                "Please build the SDK first and set BUMI_SDK_BUILD_DIR or BUMI_SDK_ROOT_DIR."
            ) from exc

    def _candidate_sdk_build_dirs(self) -> list[Path]:
        candidates: list[Path] = []
        if self.sdk_build_dir.strip():
            candidates.append(Path(self.sdk_build_dir).expanduser().resolve())

        for sdk_root in self._candidate_sdk_roots():
            candidates.append((sdk_root / "build").resolve())

        candidates.append((Path.cwd() / "build").resolve())
        return self._dedupe_paths(candidates)

    def _candidate_dds_config_paths(self) -> list[Path]:
        candidates: list[Path] = []
        for sdk_root in self._candidate_sdk_roots():
            candidates.append((sdk_root / "config" / "dds.xml").resolve())
        if self._resolved_build_dir is not None:
            candidates.append((self._resolved_build_dir.parent / "config" / "dds.xml").resolve())
        candidates.append((Path.cwd() / "config" / "dds.xml").resolve())
        return self._dedupe_paths(candidates)

    def _candidate_sdk_roots(self) -> list[Path]:
        candidates: list[Path] = []
        if self.sdk_root_dir.strip():
            candidates.append(Path(self.sdk_root_dir).expanduser().resolve())
        if self._resolved_build_dir is not None:
            candidates.append(self._resolved_build_dir.parent.resolve())
        candidates.append((PROJECT_ROOT / DEFAULT_SDK_ROOT_NAME).resolve())
        candidates.append((Path.cwd() / DEFAULT_SDK_ROOT_NAME).resolve())
        return self._dedupe_paths(candidates)

    def _dedupe_paths(self, paths: list[Path]) -> list[Path]:
        result: list[Path] = []
        seen: set[str] = set()
        for path in paths:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            result.append(path)
        return result

    def _require_controller(self) -> Any:
        if self._controller is None:
            raise RuntimeError("Bumi SDK controller is not initialized")
        return self._controller

    def _require_module(self) -> ModuleType:
        if self._module is None:
            raise RuntimeError("Bumi SDK module is not loaded")
        return self._module

    def _mark_error(self, message: str, *, disconnect: bool) -> None:
        self._state.connected = not disconnect and self._state.connected
        self._state.last_error = message

    def _clone_state(self) -> SdkRobotState:
        return SdkRobotState(
            connected=self._state.connected,
            workmode=self._state.workmode,
            battery_percent=self._state.battery_percent,
            imu_ok=self._state.imu_ok,
            motor_error=self._state.motor_error,
            last_error=self._state.last_error,
            extra=dict(self._state.extra),
        )

    def _read_attr(self, obj: object, *names: str) -> object | None:
        for name in names:
            if hasattr(obj, name):
                return getattr(obj, name)
        return None

    def _read_vector_attr(self, obj: object, name: str) -> list[float]:
        value = getattr(obj, name, None)
        if value is None:
            return []
        try:
            if hasattr(value, "tolist"):
                raw_values = value.tolist()
            else:
                raw_values = list(value)
            return [float(item) for item in raw_values]
        except Exception:
            return []

    def _safe_int(self, value: object | None, default: int) -> int:
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    async def _emit_state(self, snapshot: SdkRobotState) -> None:
        if self._callback is None:
            return
        result = self._callback(snapshot)
        if inspect.isawaitable(result):
            await result


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
        self._state.workmode = 0
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
