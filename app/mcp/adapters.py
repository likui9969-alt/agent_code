"""MCPToolAdapter — bridges an MCP plugin into the ToolRegistry.

Each :class:`MCPToolAdapter` wraps a single tool from an MCP plugin and
conforms to the :class:`~app.tools.base.BaseTool` contract, so it can be
registered side-by-side with native tools.
"""

from __future__ import annotations

from typing import Any

from app.mcp.base import BaseMCP, MCPToolDefinition
from app.tools.base import BaseTool, ToolResult


class MCPToolAdapter(BaseTool):
    """Adapts one MCP tool → :class:`BaseTool` interface.

    Example::

        file_mcp = FileMCP()
        tool_def = file_mcp.get_tools()[0]          # read_file
        adapter  = MCPToolAdapter(file_mcp, tool_def)
        tool_registry.register(adapter)              # now usable like any tool
    """

    def __init__(self, mcp: BaseMCP, tool_def: MCPToolDefinition) -> None:
        self._mcp = mcp
        self._def = tool_def
        # BaseTool fields
        self.name = f"mcp:{mcp.name}:{tool_def.name}"
        self.description = f"[{mcp.name.upper()} MCP] {tool_def.description}"
        self.parameters = tool_def.parameters

    def execute(self, **kwargs: Any) -> ToolResult:
        """Delegate execution to the MCP plugin."""
        return self._mcp.execute(self._def.name, kwargs)

    @property
    def mcp_name(self) -> str:
        return self._mcp.name

    @property
    def source_tool_name(self) -> str:
        return self._def.name

    def __repr__(self) -> str:
        return f"<MCPAdapter {self.name}>"
