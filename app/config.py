"""Application configuration via environment variables.

Use ``.env`` or export vars directly::

    REDIS_URL=redis://localhost:6379/0
    APP_PORT=8000
    LOG_LEVEL=info
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()  # Load .env file into os.environ (no-op if file missing)


def _bool_env(key: str, default: bool = True) -> bool:
    return os.getenv(key, str(default).lower()).lower() in ("1", "true", "yes")


def _int_env(key: str, default: int) -> int:
    """Parse an integer env var with validation — falls back to *default* on error."""
    raw = os.getenv(key, str(default))
    try:
        return int(raw)
    except (ValueError, TypeError):
        logger.warning("Invalid integer for %s=%r, using default %d", key, raw, default)
        return default


@dataclass
class Settings:
    """Centralised settings loaded from environment variables.

    Supports :meth:`reload` for hot-reloading and :meth:`validate` for
    startup sanity checks.
    """

    # ── Redis ───────────────────────────────────────────────────────────
    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    )
    redis_enabled: bool = field(
        default_factory=lambda: _bool_env("REDIS_ENABLED", True),
    )
    redis_health_check_interval: int = field(
        default_factory=lambda: _int_env("REDIS_HEALTH_CHECK_INTERVAL", 30),
    )
    session_ttl_seconds: int = field(
        default_factory=lambda: _int_env("SESSION_TTL_SECONDS", 86400),
    )

    # ── Message caps ────────────────────────────────────────────────────
    max_messages_per_session: int = 200
    max_plan_history: int = 20
    max_code_history: int = 50
    max_review_history: int = 50

    # ── App server ──────────────────────────────────────────────────────
    app_host: str = field(default_factory=lambda: os.getenv("APP_HOST", "0.0.0.0"))
    app_port: int = field(default_factory=lambda: _int_env("APP_PORT", 8000))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "info"))
    workers: int = field(default_factory=lambda: _int_env("WORKERS", 1))

    # ── LLM ─────────────────────────────────────────────────────────────
    qwen_api_key: str = field(default_factory=lambda: os.getenv("QWEN_API_KEY", ""))
    qwen_model: str = field(default_factory=lambda: os.getenv("QWEN_MODEL", "qwen-plus"))
    qwen_base_url: str = field(
        default_factory=lambda: os.getenv(
            "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
    )
    llm_retry_attempts: int = field(
        default_factory=lambda: _int_env("LLM_RETRY_ATTEMPTS", 4),
    )
    llm_request_timeout: int = field(
        default_factory=lambda: _int_env("LLM_REQUEST_TIMEOUT", 120),
    )

    # ── Auth ─────────────────────────────────────────────────────────────
    api_auth_token: str = field(default_factory=lambda: os.getenv("API_AUTH_TOKEN", ""))

    # ── Security ────────────────────────────────────────────────────────
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "*").split(",")
            if o.strip()
        ],
    )
    rate_limit_requests: int = field(
        default_factory=lambda: _int_env("RATE_LIMIT_REQUESTS", 100),
    )
    rate_limit_window_seconds: int = field(
        default_factory=lambda: _int_env("RATE_LIMIT_WINDOW_SECONDS", 60),
    )

    # ── Observability ───────────────────────────────────────────────────
    langsmith_api_key: str = field(default_factory=lambda: os.getenv("LANGSMITH_API_KEY", ""))
    langsmith_project: str = field(default_factory=lambda: os.getenv("LANGSMITH_PROJECT", "ai-code-assistant"))
    sentry_dsn: str = field(default_factory=lambda: os.getenv("SENTRY_DSN", ""))

    # ── Methods ─────────────────────────────────────────────────────────

    def reload(self) -> list[str]:
        """Re-read environment variables and update all fields.

        Returns a list of changed field names (for observability).
        Useful for runtime hot-reload without restarting the process.
        """
        old = {k: getattr(self, k) for k in self.__dataclass_fields__}
        load_dotenv(override=True)
        for name in self.__dataclass_fields__:
            field_def = self.__dataclass_fields__[name]
            factory = field_def.default_factory
            if factory is not None:
                setattr(self, name, factory())
        changed = [k for k in old if old[k] != getattr(self, k)]
        if changed:
            logger.info("Config reloaded — %d field(s) changed: %s", len(changed), changed)
        return changed

    def validate(self) -> list[str]:
        """Run startup sanity checks.  Returns a list of warning messages.

        Call this after loading to detect misconfiguration early.
        """
        warnings: list[str] = []

        if not self.qwen_api_key or self.qwen_api_key == "":
            warnings.append("QWEN_API_KEY is not set — LLM calls will fail")

        if self.redis_enabled and not self.redis_url:
            warnings.append("REDIS_ENABLED is true but REDIS_URL is empty")

        if self.rate_limit_requests < 1:
            warnings.append("RATE_LIMIT_REQUESTS must be >= 1")
            self.rate_limit_requests = 1

        if self.rate_limit_window_seconds < 1:
            warnings.append("RATE_LIMIT_WINDOW_SECONDS must be >= 1")
            self.rate_limit_window_seconds = 1

        if self.workers < 1:
            warnings.append("WORKERS must be >= 1")
            self.workers = 1

        for w in warnings:
            logger.warning("Config validation: %s", w)

        return warnings


# Singleton
settings = Settings()
