"""Runtime configuration. Everything is read from environment variables (or a .env
file next to the repo root) so the same code runs in tests, in the cloud scaffold
and on the M5 Ultra without edits."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    # Storage
    db_path: Path = field(default_factory=lambda: Path(_env("CC_DB_PATH", str(ROOT / "data" / "command_center.db"))))
    # Local model serving. "mock" needs no model server and is used in tests and
    # in the cloud scaffold; "ollama" talks to a local Ollama instance.
    llm_backend: str = field(default_factory=lambda: _env("CC_LLM_BACKEND", "mock"))
    ollama_url: str = field(default_factory=lambda: _env("CC_OLLAMA_URL", "http://127.0.0.1:11434"))
    model_large: str = field(default_factory=lambda: _env("CC_MODEL_LARGE", "qwen2.5:72b"))
    model_small: str = field(default_factory=lambda: _env("CC_MODEL_SMALL", "qwen2.5:7b"))
    # Integrations. "mock" reads fixtures; "http" talks to the real MCP/HTTP servers.
    deeds_backend: str = field(default_factory=lambda: _env("CC_DEEDS_BACKEND", "mock"))
    deeds_url: str = field(default_factory=lambda: _env("CC_DEEDS_URL", ""))
    deeds_token: str = field(default_factory=lambda: _env("CC_DEEDS_TOKEN", ""))
    matrix_backend: str = field(default_factory=lambda: _env("CC_MATRIX_BACKEND", "mock"))
    matrix_url: str = field(default_factory=lambda: _env("CC_MATRIX_URL", ""))
    matrix_token: str = field(default_factory=lambda: _env("CC_MATRIX_TOKEN", ""))
    # Server
    host: str = field(default_factory=lambda: _env("CC_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(_env("CC_PORT", "8787")))
    # Schedules (local time, HH:MM). Orchestrator twice a day, Validator and
    # Analyst once, Doctor every 6 hours. See spec §4 and §8.
    orchestrator_times: tuple[str, ...] = field(default_factory=lambda: tuple(_env("CC_ORCHESTRATOR_TIMES", "09:00,18:00").split(",")))
    validator_times: tuple[str, ...] = field(default_factory=lambda: tuple(_env("CC_VALIDATOR_TIMES", "08:30").split(",")))
    analyst_times: tuple[str, ...] = field(default_factory=lambda: tuple(_env("CC_ANALYST_TIMES", "08:00").split(",")))
    doctor_interval_hours: int = field(default_factory=lambda: int(_env("CC_DOCTOR_INTERVAL_HOURS", "6")))
    brief_times: tuple[str, ...] = field(default_factory=lambda: tuple(_env("CC_BRIEF_TIMES", "09:15").split(",")))
    # Stale task threshold (spec §5 derived views)
    stale_days: int = field(default_factory=lambda: int(_env("CC_STALE_DAYS", "14")))
    scheduler_enabled: bool = field(default_factory=lambda: _env("CC_SCHEDULER", "1") == "1")


settings = Settings()
