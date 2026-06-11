"""Search tools — grep and file listing over the open project directory."""

from __future__ import annotations

import re

from app.project_workspace import grep_files, list_files
from app.tools.base import BaseTool, ToolResult
from app.tools.registry import tool_registry


class GrepTool(BaseTool):
    name = "grep"
    description = (
        "Search for *pattern* (regex) in files under *path* (relative to project). "
        "Supports *glob* filtering and *context_lines*."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regular expression to search for."},
            "path": {
                "type": "string",
                "description": "Directory or file path to search in. Default: '.'",
            },
            "glob": {
                "type": "string",
                "description": "File-name glob filter, e.g. '*.py'.",
            },
            "context_lines": {
                "type": "integer",
                "description": "Lines of context around each match. Default: 0.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum matches to return. Default: 50.",
            },
        },
        "required": ["pattern"],
    }

    def execute(
        self,
        pattern: str,
        path: str = ".",
        glob: str | None = None,
        context_lines: int = 0,
        max_results: int = 50,
    ) -> ToolResult:
        try:
            re.compile(pattern)
        except re.error as exc:
            return ToolResult(success=False, error=f"Invalid regex: {exc}")

        try:
            matches = grep_files(pattern, path, glob, context_lines, max_results)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

        return ToolResult(
            success=True,
            output=f"Found {len(matches)} match(es) for '{pattern}'",
            metadata={
                "pattern": pattern,
                "total_matches": len(matches),
                "matches": matches,
                "max_results": max_results,
            },
        )


class ListFilesTool(BaseTool):
    name = "list_files"
    description = "List files under *path* (relative to the open project directory)."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path. Default: '.'",
            },
            "glob": {
                "type": "string",
                "description": "Optional glob filter, e.g. '*.py'.",
            },
        },
        "required": [],
    }

    def execute(self, path: str = ".", glob: str | None = None) -> ToolResult:
        try:
            entries = list_files(path, glob=glob, recursive=False)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

        if not entries:
            return ToolResult(
                success=True,
                output="(empty directory)",
                metadata={"path": path, "file_count": 0, "files": []},
            )

        return ToolResult(
            success=True,
            output=f"{len(entries)} file(s) found",
            metadata={
                "path": path,
                "file_count": len(entries),
                "files": entries,
            },
        )


tool_registry.register(GrepTool())
tool_registry.register(ListFilesTool())
