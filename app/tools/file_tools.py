"""File system tools — read / write against the open project directory."""

from __future__ import annotations

from app.project_workspace import read_file, write_file
from app.tools.base import BaseTool, ToolResult
from app.tools.registry import tool_registry


class ReadFileTool(BaseTool):
    name = "read_file"
    description = (
        "Read the contents of a file at *path* (relative to the open project). "
        "Optionally specify *start_line* and *end_line* for pagination."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative file path within the project."},
            "start_line": {
                "type": "integer",
                "description": "1-based start line (inclusive). Default: 1.",
            },
            "end_line": {
                "type": "integer",
                "description": "1-based end line (inclusive). Default: last line.",
            },
        },
        "required": ["path"],
    }

    def execute(self, path: str, start_line: int = 1, end_line: int | None = None) -> ToolResult:
        try:
            output, meta = read_file(path, start_line, end_line)
            return ToolResult(success=True, output=output, metadata=meta)
        except Exception as exc:
            return ToolResult(
                success=False,
                error=str(exc),
                metadata={"path": path},
            )


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Create or overwrite a file at *path* (relative to the open project) with *content*."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Target file path (relative)."},
            "content": {"type": "string", "description": "Full file content to write."},
        },
        "required": ["path", "content"],
    }

    def execute(self, path: str, content: str) -> ToolResult:
        try:
            meta = write_file(path, content)
            existed = meta.pop("existed_before")
            return ToolResult(
                success=True,
                output=f"{'Updated' if existed else 'Created'} file: {meta['path']}",
                metadata=meta,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=str(exc),
                metadata={"path": path},
            )


tool_registry.register(ReadFileTool())
tool_registry.register(WriteFileTool())
