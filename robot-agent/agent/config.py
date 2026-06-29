from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class AgentSettings:
    robot_id: str = "bumi_001"
    server_base_url: str = "ws://127.0.0.1:8000"
    heartbeat_interval_seconds: int = 5
    battery_start_percent: int = 90
    bridge_mode: str = "mock"
    control_mode: str = "highcontrol"
    dds_host: str = "192.168.55.101"
    dds_domain_id: int = 0
    dds_network_interface: str = ""
    state_poll_interval_seconds: float = 0.2
    move_x_limit: float = 0.2
    move_yaw_limit: float = 0.3
    action_edge_delay_ms: int = 80
    tts_mode: str = "local_stub"
    agent_version: str = "0.1.0"
    sdk_version: str = "bumi-highcontrol-v1"
    protocol_version: str = "1.0"

    @property
    def websocket_url(self) -> str:
        return f"{self.server_base_url}/ws/agents/{self.robot_id}"

    @classmethod
    def from_env(cls) -> "AgentSettings":
        return cls(
            robot_id=os.getenv("BUMI_ROBOT_ID", cls.robot_id),
            server_base_url=os.getenv("BUMI_SERVER_BASE_URL", cls.server_base_url),
            heartbeat_interval_seconds=int(
                os.getenv(
                    "BUMI_HEARTBEAT_INTERVAL_SECONDS",
                    str(cls.heartbeat_interval_seconds),
                )
            ),
            battery_start_percent=int(
                os.getenv(
                    "BUMI_BATTERY_START_PERCENT",
                    str(cls.battery_start_percent),
                )
            ),
            bridge_mode=os.getenv("BUMI_BRIDGE_MODE", cls.bridge_mode),
            control_mode=os.getenv("BUMI_CONTROL_MODE", cls.control_mode),
            dds_host=os.getenv("BUMI_DDS_HOST", cls.dds_host),
            dds_domain_id=int(
                os.getenv("BUMI_DDS_DOMAIN_ID", str(cls.dds_domain_id))
            ),
            dds_network_interface=os.getenv(
                "BUMI_DDS_NETWORK_INTERFACE",
                cls.dds_network_interface,
            ),
            state_poll_interval_seconds=float(
                os.getenv(
                    "BUMI_STATE_POLL_INTERVAL_SECONDS",
                    str(cls.state_poll_interval_seconds),
                )
            ),
            move_x_limit=float(
                os.getenv("BUMI_MOVE_X_LIMIT", str(cls.move_x_limit))
            ),
            move_yaw_limit=float(
                os.getenv("BUMI_MOVE_YAW_LIMIT", str(cls.move_yaw_limit))
            ),
            action_edge_delay_ms=int(
                os.getenv(
                    "BUMI_ACTION_EDGE_DELAY_MS",
                    str(cls.action_edge_delay_ms),
                )
            ),
            tts_mode=os.getenv("BUMI_TTS_MODE", cls.tts_mode),
            agent_version=os.getenv("BUMI_AGENT_VERSION", cls.agent_version),
            sdk_version=os.getenv("BUMI_SDK_VERSION", cls.sdk_version),
            protocol_version=os.getenv(
                "BUMI_PROTOCOL_VERSION",
                cls.protocol_version,
            ),
        )
