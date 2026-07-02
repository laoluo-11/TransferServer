from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(slots=True)
class LLMSettings:
    """LLM provider configuration.

    目前支持两种后端:
      - openai   : OpenAI API (也可兼容 vLLM / localai 等 OpenAI-compatible 服务)
      - anthropic: Anthropic Claude API

    真实使用时通过环境变量设置 API Key:
      export LLM_API_KEY="sk-..."
      export LLM_BASE_URL="https://api.openai.com/v1"   # 可选, 用于兼容服务

    示例:
      LLMSettings.from_env()
    """

    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.3
    max_tokens: int = 1024
    system_prompt: str = ""

    @classmethod
    def from_env(cls, defaults: "LLMSettings | None" = None) -> "LLMSettings":
        if defaults is None:
            defaults = cls()
        return cls(
            provider=os.getenv("LLM_PROVIDER", defaults.provider),
            model=os.getenv("LLM_MODEL", defaults.model),
            api_key=os.getenv("LLM_API_KEY", defaults.api_key),
            base_url=os.getenv("LLM_BASE_URL", defaults.base_url),
            temperature=float(os.getenv("LLM_TEMPERATURE", str(defaults.temperature))),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", str(defaults.max_tokens))),
            system_prompt=os.getenv("LLM_SYSTEM_PROMPT", defaults.system_prompt),
        )


@dataclass(slots=True)
class Settings:
    app_name: str = "Bumi Cloud Service"
    app_version: str = "0.1.0"
    heartbeat_timeout_seconds: int = 15
    llm: LLMSettings = field(default_factory=LLMSettings)

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            app_name=os.getenv("CLOUD_APP_NAME", defaults.app_name),
            app_version=os.getenv("CLOUD_APP_VERSION", defaults.app_version),
            heartbeat_timeout_seconds=int(
                os.getenv(
                    "CLOUD_HEARTBEAT_TIMEOUT_SECONDS",
                    str(defaults.heartbeat_timeout_seconds),
                )
            ),
            llm=LLMSettings.from_env(defaults.llm),
        )
