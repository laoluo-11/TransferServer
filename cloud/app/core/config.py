from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    app_name: str = "Bumi Cloud Service"
    app_version: str = "0.1.0"
    heartbeat_timeout_seconds: int = 15

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=os.getenv("CLOUD_APP_NAME", cls.app_name),
            app_version=os.getenv("CLOUD_APP_VERSION", cls.app_version),
            heartbeat_timeout_seconds=int(
                os.getenv(
                    "CLOUD_HEARTBEAT_TIMEOUT_SECONDS",
                    str(cls.heartbeat_timeout_seconds),
                )
            ),
        )
