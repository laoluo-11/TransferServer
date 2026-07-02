from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(slots=True)
class LLMSettings:
    """LLM provider configuration.

    Supported backends:
      - openai    : OpenAI API (also compatible with vLLM / localai / ollama)
      - anthropic : Anthropic Claude API (not yet implemented)

    Usage:
      export LLM_API_KEY=***
      export LLM_MODEL=gpt-4o      # optional, default: gpt-4o
      export LLM_BASE_URL=...      # optional, for OpenAI-compatible services
      export LLM_MAX_ROUNDS=10     # optional, max agent loop iterations
    """

    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.3
    max_tokens: int = 1024
    system_prompt: str = ""
    max_rounds: int = 10  # max iterations of agent loop (ReAct)

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
            max_rounds=int(os.getenv("LLM_MAX_ROUNDS", str(defaults.max_rounds))),
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
