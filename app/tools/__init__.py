"""Standardised tool system for the AI Code Assistant.

Usage::

    from app.tools import ToolRegistry, tool_registry

    # Register (done automatically at import time)
    tool_registry.register(ReadFileTool())

    # Execute
    result = tool_registry.execute("read_file", {"path": "src/main.py"})

    # Get OpenAI-compatible schemas (for LLM function calling)
    schemas = tool_registry.get_all_schemas()
"""

from app.tools.base import BaseTool, ToolExecutionLog, ToolResult
from app.tools.execution_tools import RunPythonTool
from app.tools.file_tools import ReadFileTool, WriteFileTool
from app.tools.registry import ToolRegistry, tool_registry
from app.tools.search_tools import GrepTool, ListFilesTool

# ── Import side-effect: registers all tools ──
# (kept here so a single import wires everything)
_ = tool_registry  # ensure singleton is alive

__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolExecutionLog",
    "ToolRegistry",
    "tool_registry",
    "ReadFileTool",
    "WriteFileTool",
    "GrepTool",
    "ListFilesTool",
    "RunPythonTool",
]
