from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    provider: str = "openai_compatible"
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    max_investigation_tool_calls: int = 4
    max_hypotheses: int = 3
    max_llm_calls: int = 10
    command_timeout_seconds: int = 60
    max_patch_files: int = 3
    max_patch_changed_lines: int = 100
    max_patch_attempts: int = 3

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            provider=os.getenv("PATCHPROOF_PROVIDER", "openai_compatible"),
            model=os.getenv("PATCHPROOF_MODEL"),
            base_url=os.getenv("PATCHPROOF_BASE_URL"),
            api_key=os.getenv("PATCHPROOF_API_KEY"),
            max_investigation_tool_calls=_env_int("PATCHPROOF_MAX_INVESTIGATION_TOOL_CALLS", 4),
            max_hypotheses=_env_int("PATCHPROOF_MAX_HYPOTHESES", 3),
            max_llm_calls=_env_int("PATCHPROOF_MAX_LLM_CALLS", 10),
            command_timeout_seconds=_env_int("PATCHPROOF_COMMAND_TIMEOUT_SECONDS", 60),
            max_patch_files=_env_int("PATCHPROOF_MAX_PATCH_FILES", 3),
            max_patch_changed_lines=_env_int("PATCHPROOF_MAX_PATCH_CHANGED_LINES", 100),
            max_patch_attempts=_env_int("PATCHPROOF_MAX_PATCH_ATTEMPTS", 3),
        )
