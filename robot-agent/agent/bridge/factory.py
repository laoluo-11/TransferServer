from __future__ import annotations

import logging

from agent.bridge.base import ControlBridge
from agent.bridge.bumi_bridge import BumiHighControlBridge
from agent.bridge.mock_bridge import MockControlBridge
from agent.config import AgentSettings


def build_bridge(settings: AgentSettings) -> ControlBridge:
    logger = logging.getLogger("robot-agent.bridge")
    if settings.bridge_mode in {"bumi", "bumi_stub"}:
        logger.info("using BumiHighControlBridge")
        return BumiHighControlBridge(settings)
    logger.info("using MockControlBridge")
    return MockControlBridge(settings)
