"""Environment configuration. Keys are never returned by an API response."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from .models import ResolvedMode

ExecutionMode = Literal["auto", "live", "replay"]


class HarnessError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


@dataclass(frozen=True)
class Settings:
    provider: str = "gemini"
    execution_mode: ExecutionMode = "auto"
    gemini_api_key: str = field(default="", repr=False)
    openai_api_key: str = field(default="", repr=False)
    gemini_model: str = "gemini-2.5-flash"
    openai_model: str = "gpt-4o-mini"
    timeout_seconds: float = 20.0
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    session_ttl_seconds: float = 1800
    max_sessions: int = 1000

    def __post_init__(self) -> None:
        if self.provider not in {"gemini", "openai"}:
            raise ValueError("LLM_PROVIDER must be gemini or openai.")
        if self.execution_mode not in {"auto", "live", "replay"}:
            raise ValueError("EXECUTION_MODE must be auto, live, or replay.")
        if not 0 < self.timeout_seconds <= 120:
            raise ValueError("LLM_TIMEOUT_SECONDS must be between 0 and 120.")

    @property
    def api_key(self) -> str:
        return self.gemini_api_key if self.provider == "gemini" else self.openai_api_key

    @property
    def model(self) -> str:
        return self.gemini_model if self.provider == "gemini" else self.openai_model

    def resolve_mode(self, override: ExecutionMode | None = None) -> ResolvedMode:
        requested = override or self.execution_mode
        if requested == "replay" or (requested == "auto" and not self.api_key):
            return "verified_replay"
        if not self.api_key:
            raise HarnessError(
                "API_KEY_REQUIRED", "Live execution requires the selected provider's API key.", 503
            )
        return "live_gemini" if self.provider == "gemini" else "live_openai"


def parse_execution_mode(value: str) -> ExecutionMode:
    """Validate external configuration before assigning its literal type."""
    if value == "auto":
        return "auto"
    if value == "live":
        return "live"
    if value == "replay":
        return "replay"
    raise ValueError("EXECUTION_MODE must be auto, live, or replay.")


def load_settings() -> Settings:
    load_dotenv(Path(__file__).with_name(".env"), override=False)
    return Settings(
        provider=os.getenv("LLM_PROVIDER", "gemini"),
        execution_mode=parse_execution_mode(os.getenv("EXECUTION_MODE", "auto")),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "20")),
        cors_origins=tuple(
            x.strip()
            for x in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(
                ","
            )
            if x.strip()
        ),
    )
