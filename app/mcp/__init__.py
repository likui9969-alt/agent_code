"""MCP (Model Context Protocol) plugin layer.

Architecture
------------
::

    ┌──────────────────────────────────────────────┐
    │                 ToolRegistry                  │
    │  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
    │  │ BaseTool │  │ BaseTool │  │ MCPAdapter │  │  ← MCPToolAdapter
    │  │(native)  │  │(native)  │  │            │  │
    │  └──────────┘  └──────────┘  └─────┬──────┘  │
    └─────────────────────────────────────┼────────┘
                                          │ wraps
    ┌─────────────────────────────────────┼────────┐
    │                        MCP Layer   │         │
    │  ┌──────────┐  ┌──────────┐  ┌─────▼──────┐  │
    │  │ FileMCP  │  │  GitMCP  │  │  Custom    │  │
    │  │          │  │ (iface)  │  │  MCP ...   │  │
    │  └──────────┘  └──────────┘  └────────────┘  │
    │         ▲            ▲              ▲         │
    │         └────────────┼──────────────┘         │
    │                 MCPPluginLoader               │
    └──────────────────────────────────────────────┘

The MCPPluginLoader discovers :class:`BaseMCP` implementations, wraps each
tool as a :class:`MCPToolAdapter` (which is a :class:`~app.tools.base.BaseTool`
subclass), and registers them into the :class:`~app.tools.registry.ToolRegistry`.
"""

from app.mcp.adapters import MCPToolAdapter
from app.mcp.base import BaseMCP, MCPToolDefinition
from app.mcp.file_mcp import FileMCP
from app.mcp.git_mcp import GitMCP
from app.mcp.loader import MCPPluginLoader, mcp_loader

__all__ = [
    "BaseMCP",
    "MCPToolDefinition",
    "MCPToolAdapter",
    "MCPPluginLoader",
    "mcp_loader",
    "FileMCP",
    "GitMCP",
]
