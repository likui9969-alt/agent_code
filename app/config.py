"""Application configuration via environment variables.

Use ``.env`` or export vars directly::

    REDIS_URL=redis://localhost:6379/0
    APP_PORT=8000
    LOG_LEVEL=info
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()  # Load .env file into os.environ (no-op if file missing)


def _bool_env(key: str, default: bool = True) -> bool:
    return os.getenv(key, str(default).lower()).lower() in ("1", "true", "yes")


@dataclass
class Settings:
    """Centralised settings loaded from environment variables."""

    # ── Redis ───────────────────────────────────────────────────────────
    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    )
    redis_enabled: bool = field(
        default_factory=lambda: _bool_env("REDIS_ENABLED", True),
    )
    session_ttl_seconds: int = field(
        default_factory=lambda: int(os.getenv("SESSION_TTL_SECONDS", "86400")),
    )

    # ── Message caps ────────────────────────────────────────────────────
    max_messages_per_session: int = 200
    max_plan_history: int = 20
    max_code_history: int = 50
    max_review_history: int = 50

    # ── App server ──────────────────────────────────────────────────────
    app_host: str = field(default_factory=lambda: os.getenv("APP_HOST", "0.0.0.0"))
    app_port: int = field(default_factory=lambda: int(os.getenv("APP_PORT", "8000")))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "info"))
    workers: int = field(default_factory=lambda: int(os.getenv("WORKERS", "1")))

    # ── LLM ─────────────────────────────────────────────────────────────
    qwen_api_key: str = field(default_factory=lambda: os.getenv("QWEN_API_KEY", ""))
    qwen_model: str = field(default_factory=lambda: os.getenv("QWEN_MODEL", "qwen-plus"))
    qwen_base_url: str = field(
        default_factory=lambda: os.getenv(
            "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
    )

    # ── Security ────────────────────────────────────────────────────────
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "*").split(",")
            if o.strip()
        ],
    )
    rate_limit_requests: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_REQUESTS", "100")),
    )
    rate_limit_window_seconds: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")),
    )

    # ── Observability ───────────────────────────────────────────────────
    langsmith_api_key: str = field(default_factory=lambda: os.getenv("LANGSMITH_API_KEY", ""))
    langsmith_project: str = field(default_factory=lambda: os.getenv("LANGSMITH_PROJECT", "ai-code-assistant"))
    sentry_dsn: str = field(default_factory=lambda: os.getenv("SENTRY_DSN", ""))


# Singleton
settings = Settings()
