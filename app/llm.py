"""LLM Provider — Qwen DashScope (Alibaba Cloud) + mock fallback.

Usage::

    from app.llm import chat

    reply = chat(
        system="You are a code reviewer.",
        user="Review this code: def foo(): pass",
    )
"""

from __future__ import annotations

import logging

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# ── Lazy client (created on first call) ─────────────────────────────────────
_client: OpenAI | None = None


def _get_client() -> OpenAI | None:
    """Return an OpenAI-compatible client for Qwen, or None if no API key."""
    global _client
    if _client is not None:
        return _client
    if not settings.qwen_api_key:
        logger.warning("QWEN_API_KEY not set — using mock LLM")
        return None
    _client = OpenAI(
        api_key=settings.qwen_api_key,
        base_url=settings.qwen_base_url,
    )
    logger.info("Qwen client ready — model=%s", settings.qwen_model)
    return _client


def configure(api_key: str | None = None, model: str | None = None) -> None:
    """Update runtime LLM credentials (called from the settings API)."""
    global _client
    _client = None
    if api_key is not None:
        settings.qwen_api_key = api_key
    if model is not None:
        settings.qwen_model = model


# ============================================================================
# Public API
# ============================================================================


def chat(
    system: str,
    user: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str | None:
    """Send a prompt to Qwen and return the reply.

    Returns ``None`` if no API key is configured (caller should fall back to mock).
    """
    client = _get_client()
    if client is None:
        return None

    try:
        response = client.chat.completions.create(
            model=settings.qwen_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
    except Exception as exc:
        logger.error("Qwen API error: %s", exc)
        return None  # Caller should fall back to mock


def is_available() -> bool:
    """Return True if a real LLM is configured."""
    return bool(settings.qwen_api_key)


# ── Pre-built prompts ───────────────────────────────────────────────────────

PLANNER_SYSTEM = """You are a senior software architect. Given a user request, produce a
structured implementation plan. Include:
1. Algorithm / framework selection with justification.
2. Function / class signatures with type hints.
3. Edge cases to handle.
4. Testing strategy.
Use Markdown. Be concise."""

CODER_SYSTEM = """You are an expert Python developer. Given an implementation plan, write
clean, production-ready Python code. Requirements:
- Type hints on all functions.
- Docstrings in Google style.
- Error handling for edge cases.
- if __name__ == '__main__' block with test cases.
Output ONLY the Python code, no explanation."""

CODER_FIX_SYSTEM = """You are an expert Python developer. The code you wrote was reviewed
and issues were found. Fix ALL the issues listed below. Output ONLY the corrected code."""

REVIEWER_SYSTEM = """You are a code reviewer. Review the following code and return a JSON
object with exactly these keys:
- "passed": true or false
- "issues": a list of strings describing problems found (empty if passed)

Check for: correctness, security, performance, error handling, type safety, docstrings.
Output ONLY the JSON object, no markdown, no explanation."""
