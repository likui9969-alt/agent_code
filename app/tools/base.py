"""Abstract base classes for the tool system.

Every tool inherits from :class:`BaseTool`.  The :class:`ToolRegistry` is a
singleton that holds all registered tools and dispatches execution calls.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ============================================================================
# ToolResult — what every tool returns
# ============================================================================


@dataclass
class ToolResult:
    """Standardised result envelope for every tool execution.

    Attributes:
        success:  ``True`` when the tool completed without error.
        output:   Human-readable / machine-parseable output string.
        error:    Error message when ``success`` is ``False``.
        metadata: Arbitrary extra info (e.g. ``{"lines": 42, "bytes": 512}``).
    """

    success: bool
    output: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }


# ============================================================================
# ToolExecutionLog — audit entry for every tool call
# ============================================================================


@dataclass
class ToolExecutionLog:
    """Immutable record of one tool invocation (used for audit trail)."""

    id: str
    tool_name: str
    arguments: dict
    result: dict  # ToolResult.to_dict()
    duration_ms: float
    timestamp: float
    session_id: str = ""
    project_root: str = ""
    error_stack: str | None = None

    @classmethod
    def from_execution(
        cls,
        tool_name: str,
        arguments: dict,
        result: ToolResult,
        duration_ms: float,
        *,
        session_id: str = "",
        project_root: str = "",
        error_stack: str | None = None,
    ) -> "ToolExecutionLog":
        return cls(
            id=str(uuid.uuid4())[:8],
            tool_name=tool_name,
            arguments=arguments,
            result=result.to_dict(),
            duration_ms=duration_ms,
            timestamp=time.time(),
            session_id=session_id,
            project_root=project_root,
            error_stack=error_stack,
        )

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "result": self.result,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }
        if self.session_id:
            d["session_id"] = self.session_id
        if self.project_root:
            d["project_root"] = self.project_root
        if self.error_stack:
            d["error_stack"] = self.error_stack
        return d


# ============================================================================
# BaseTool — the contract every tool must fulfill
# ============================================================================


class BaseTool(ABC):
    """Abstract tool contract.

    Subclasses **must** set ``name``, ``description``, and ``parameters``
    (a JSON Schema dict).  They implement :meth:`execute`.

    Example::

        class ReadFileTool(BaseTool):
            name = "read_file"
            description = "Read the contents of a file."
            parameters = {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"}
                },
                "required": ["path"],
            }

            def execute(self, path: str) -> ToolResult:
                ...
    """

    name: str
    description: str
    parameters: dict[str, Any]

    # ── Subclass contract ──────────────────────────────────────────────

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with validated parameters.  Must be overridden."""
        ...

    # ── Public API ──────────────────────────────────────────────────────

    def to_openai_schema(self) -> dict:
        """Return an OpenAI / Qwen Function Calling compatible schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def run(self, **kwargs: Any) -> ToolResult:
        """Validate, execute, time, and return a :class:`ToolResult`."""
        t0 = time.perf_counter()
        try:
            result = self.execute(**kwargs)
        except Exception as exc:
            result = ToolResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )
        duration_ms = (time.perf_counter() - t0) * 1000
        result.metadata["duration_ms"] = round(duration_ms, 2)
        result.metadata["tool_name"] = self.name
        return result
