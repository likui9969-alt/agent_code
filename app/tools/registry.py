"""ToolRegistry — singleton that holds all tools and dispatches execution."""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from app.tools.base import BaseTool, ToolExecutionLog, ToolResult

logger = logging.getLogger(__name__)

# Maximum number of execution log entries retained in memory.
_MAX_LOG_ENTRIES = 500


class ToolRegistry:
    """Thread-safe registry of all available tools.

    Usage::

        registry = ToolRegistry()
        registry.register(ReadFileTool())
        result = registry.execute("read_file", {"path": "x.py"})
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._execution_log: deque[ToolExecutionLog] = deque(maxlen=_MAX_LOG_ENTRIES)

    # ── Registration ────────────────────────────────────────────────────

    def register(self, tool: BaseTool) -> None:
        """Add a tool instance.  Overwrites if name already exists."""
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def unregister(self, name: str) -> bool:
        """Remove a tool by name.  Returns ``True`` if it existed."""
        if name in self._tools:
            del self._tools[name]
            logger.debug("Unregistered tool: %s", name)
            return True
        return False

    def get(self, name: str) -> BaseTool | None:
        """Look up a tool by name, or ``None``."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """Return all registered tool names."""
        return sorted(self._tools.keys())

    def list_tools_by_source(self) -> dict[str, Any]:
        """Group tool names by source (native vs MCP plugin).

        Returns:
            dict with keys:
            - ``"native"``: ``list[str]`` — native tool names.
            - ``"mcp"``: ``dict[str, list[str]]`` — MCP plugin name → tool names.
        """
        groups: dict[str, Any] = {"native": [], "mcp": {}}
        for name in self._tools:
            if name.startswith("mcp:"):
                _, mcp_name, _ = name.split(":", 2)
                mcp_dict: dict[str, list[str]] = groups["mcp"]
                mcp_dict.setdefault(mcp_name, []).append(name)
            else:
                groups["native"].append(name)
        return groups

    # ── Execution ───────────────────────────────────────────────────────

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        project_root: str | None = None,
        session_id: str = "",
    ) -> ToolResult:
        """Execute a tool by name, log the call, return the result.

        Raises:
            ValueError: if *name* is not registered.
        """
        from app.project_workspace import project_root_context

        tool = self._tools.get(name)
        if tool is None:
            msg = f"Unknown tool: '{name}'. Available: {self.list_tools()}"
            logger.error(msg)
            return ToolResult(success=False, error=msg)

        # ── Security policy check (defence-in-depth against prompt injection) ─
        from app.tools.tool_policy import ToolPolicyViolation, check_tool_policy
        try:
            check_tool_policy(name, arguments)
        except ToolPolicyViolation as exc:
            logger.warning("Tool policy blocked: %s | %s", name, exc)
            return ToolResult(success=False, error=str(exc))

        with project_root_context(project_root):
            result = tool.run(**arguments)
        log_entry = ToolExecutionLog.from_execution(
            tool_name=name,
            arguments=arguments,
            result=result,
            duration_ms=result.metadata.get("duration_ms", 0),
            session_id=session_id,
            project_root=project_root or "",
            error_stack=result.error if not result.success else None,
        )
        self._execution_log.append(log_entry)

        status = "OK" if result.success else "FAIL"
        logger.info(
            "Tool %s | %s | %s | %.1fms",
            name,
            status,
            arguments.get("path", arguments.get("pattern", "")),
            result.metadata.get("duration_ms", 0),
        )
        return result

    # ── Schemas (for LLM function calling) ──────────────────────────────

    def get_all_schemas(self) -> list[dict]:
        """Return OpenAI-compatible schemas for every registered tool."""
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def get_schemas_for(self, names: list[str]) -> list[dict]:
        """Return schemas for a subset of tools."""
        return [
            tool.to_openai_schema()
            for name in names
            if (tool := self._tools.get(name))
        ]

    # ── Audit ───────────────────────────────────────────────────────────

    def get_execution_log(self, limit: int = 50) -> list[dict]:
        """Return the most recent execution log entries (up to *limit*)."""
        entries = list(self._execution_log)
        return [e.to_dict() for e in entries[-limit:]]

    def clear_log(self) -> None:
        self._execution_log.clear()


# ── Module-level singleton ──────────────────────────────────────────────────
tool_registry = ToolRegistry()
