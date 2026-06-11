"""GitMCP — Git operations as MCP tools (**not implemented**).

This module defines the *shape* of a Git MCP plugin.  All ``execute`` methods
return a ``ToolResult(success=False, ...)`` because no real git backend is
wired in yet.  To enable real git operations, replace the execute methods
with calls to ``gitpython`` or a ``git`` CLI subprocess sandbox.

Tools provided
--------------
- ``git_diff``    — show staged / unstaged diffs.
- ``git_log``     — show recent commit history.
- ``git_status``  — show working-tree status.
- ``git_branch``  — list / create / switch branches.
- ``git_blame``   — show line-by-line authorship.
"""

from __future__ import annotations

from typing import Any

from app.mcp.base import BaseMCP, MCPToolDefinition
from app.tools.base import ToolResult


class GitMCP(BaseMCP):
    name = "git"
    description = "Git version-control operations (interface only — no real git)."
    version = "0.1.0"

    def get_tools(self) -> list[MCPToolDefinition]:
        return [
            MCPToolDefinition(
                name="git_diff",
                description="Show changes between commits, branches, or the working tree.",
                parameters={
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "Branch, commit hash, or HEAD~N."},
                        "staged": {"type": "boolean", "description": "Show only staged changes."},
                        "path": {"type": "string", "description": "Filter to a specific file."},
                    },
                    "required": [],
                },
                permission="read_only",
                tags=["vcs", "review"],
            ),
            MCPToolDefinition(
                name="git_log",
                description="Show the commit history.",
                parameters={
                    "type": "object",
                    "properties": {
                        "n": {"type": "integer", "description": "Number of entries (default 10)."},
                        "author": {"type": "string", "description": "Filter by author."},
                        "since": {"type": "string", "description": "Date filter, e.g. '2026-01-01'."},
                        "path": {"type": "string", "description": "Filter to commits touching this file."},
                    },
                    "required": [],
                },
                permission="read_only",
                tags=["vcs", "history"],
            ),
            MCPToolDefinition(
                name="git_status",
                description="Show the working-tree status (staged, modified, untracked).",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Filter to a directory or file."},
                    },
                    "required": [],
                },
                permission="read_only",
                tags=["vcs", "workspace"],
            ),
            MCPToolDefinition(
                name="git_branch",
                description="List, create, or switch branches.",
                parameters={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["list", "create", "switch"],
                            "description": "Operation to perform.",
                        },
                        "name": {"type": "string", "description": "Branch name (for create / switch)."},
                    },
                    "required": ["action"],
                },
                permission="read_write",
                tags=["vcs", "branching"],
            ),
            MCPToolDefinition(
                name="git_blame",
                description="Show line-by-line authorship for a file.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path."},
                        "start_line": {"type": "integer"},
                        "end_line": {"type": "integer"},
                    },
                    "required": ["path"],
                },
                permission="read_only",
                tags=["vcs", "audit"],
            ),
        ]

    _NOT_IMPL = "Git backend not implemented. Wire this plugin to gitpython or git CLI."

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(success=False, error=self._NOT_IMPL)

    def health_check(self) -> bool:
        """Git backend is not wired in — always unhealthy."""
        return False
