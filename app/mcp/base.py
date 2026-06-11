"""Abstract base class for MCP (Model Context Protocol) plugins.

An **MCP plugin** is a grouped set of related tools that share a lifecycle.
For example, ``FileMCP`` exposes ``read_file`` / ``write_file`` / ``list_dir``;
``GitMCP`` exposes ``git_diff`` / ``git_log`` / ``git_status``.

Every MCP plugin:
- Declares its tool definitions via :meth:`get_tools`.
- Routes execution via :meth:`execute`.
- Reports health via :meth:`health_check`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.tools.base import ToolResult


class MCPToolDefinition:
    """Lightweight descriptor for one MCP tool.

    This is **not** a :class:`~app.tools.base.BaseTool` — it is the metadata
    that the :class:`MCPToolAdapter` consumes to build a fully-fledged tool.
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        *,
        permission: str = "read_only",
        tags: list[str] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters  # JSON Schema
        self.permission = permission  # "read_only" | "read_write" | "execute"
        self.tags = tags or []

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "permission": self.permission,
            "tags": self.tags,
        }


# ============================================================================
# BaseMCP — the plugin contract
# ============================================================================


class BaseMCP(ABC):
    """Abstract MCP plugin.

    Subclasses **must** provide:

    - ``name`` — unique plugin identifier (e.g. ``"file"``, ``"git"``).
    - ``description`` — human-readable summary.
    - :meth:`get_tools` — return the list of :class:`MCPToolDefinition` objects.
    - :meth:`execute` — dispatch *tool_name* with *arguments* → :class:`ToolResult`.

    Optional:
    - :meth:`health_check` — return ``True`` if the MCP backend is reachable.
    - :meth:`on_load` / :meth:`on_unload` — lifecycle hooks.
    """

    name: str
    description: str
    version: str = "0.1.0"

    # ── Subclass contract ──────────────────────────────────────────────

    @abstractmethod
    def get_tools(self) -> list[MCPToolDefinition]:
        """Return the tool definitions this MCP provides."""
        ...

    @abstractmethod
    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute one of this MCP's tools."""
        ...

    # ── Optional hooks ─────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Check whether the MCP backend is available.  Default: always OK."""
        return True

    def on_load(self) -> None:
        """Called when the plugin is loaded into the registry."""

    def on_unload(self) -> None:
        """Called when the plugin is removed from the registry."""

    # ── Magic ──────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r} v={self.version}>"
