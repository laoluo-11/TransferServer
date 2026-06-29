from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
for path in (PROJECT_ROOT, PACKAGE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent.config import AgentSettings
from agent.runtime import RobotAgent


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def main() -> None:
    configure_logging()
    settings = AgentSettings.from_env()
    agent = RobotAgent(settings)
    asyncio.run(agent.run_forever())


if __name__ == "__main__":
    main()
