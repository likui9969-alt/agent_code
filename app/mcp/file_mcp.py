"""FileMCP — file-system operations on the open project directory.

Tools provided
--------------
- ``read_file``      — read file contents (with pagination).
- ``write_file``     — create / overwrite a file.
- ``list_directory`` — list directory contents with optional glob filter.
- ``search_files``   — regex search across files (grep).
"""

from __future__ import annotations

from typing import Any

from app.mcp.base import BaseMCP, MCPToolDefinition
from app.project_workspace import list_files, read_file, search_files, write_file
from app.tools.base import ToolResult


class FileMCP(BaseMCP):
    name = "file"
    description = "File-system operations — read, write, list, search."
    version = "1.0.0"

    def get_tools(self) -> list[MCPToolDefinition]:
        return [
            MCPToolDefinition(
                name="read_file",
                description="Read the contents of a file with optional line-range pagination.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative file path."},
                        "start_line": {"type": "integer", "description": "1-based start (default 1)."},
                        "end_line": {"type": "integer", "description": "1-based end (default EOF)."},
                    },
                    "required": ["path"],
                },
                permission="read_only",
                tags=["fs", "read"],
            ),
            MCPToolDefinition(
                name="write_file",
                description="Create or overwrite a file with the given content.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative target file path."},
                        "content": {"type": "string", "description": "File content."},
                    },
                    "required": ["path", "content"],
                },
                permission="read_write",
                tags=["fs", "write"],
            ),
            MCPToolDefinition(
                name="list_directory",
                description="List files in a directory, optionally filtered by glob pattern.",
                parameters={
                    "type": "object",
                    "properties": {
                        "directory": {"type": "string", "description": "Directory path. Default: '.'"},
                        "glob": {"type": "string", "description": "Glob filter, e.g. '*.py'."},
                        "recursive": {"type": "boolean", "description": "Recurse subdirectories."},
                    },
                    "required": [],
                },
                permission="read_only",
                tags=["fs", "discovery"],
            ),
            MCPToolDefinition(
                name="search_files",
                description="Search file contents with a regex pattern (grep).",
                parameters={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Regex pattern."},
                        "glob": {"type": "string", "description": "File-name filter, e.g. '*.py'."},
                        "max_results": {"type": "integer", "description": "Max matches (default 50)."},
                    },
                    "required": ["pattern"],
                },
                permission="read_only",
                tags=["fs", "search"],
            ),
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        match tool_name:
            case "read_file":
                return self._read(arguments)
            case "write_file":
                return self._write(arguments)
            case "list_directory":
                return self._list(arguments)
            case "search_files":
                return self._search(arguments)
            case _:
                return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    def _read(self, args: dict) -> ToolResult:
        path = args.get("path", "")
        try:
            output, meta = read_file(
                path,
                int(args.get("start_line", 1)),
                args.get("end_line"),
            )
            return ToolResult(
                success=True,
                output=output,
                metadata={**meta, "selected": meta["end_line"] - meta["start_line"] + 1},
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc), metadata={"path": path})

    def _write(self, args: dict) -> ToolResult:
        path = args.get("path")
        content = args.get("content")
        if not path:
            return ToolResult(success=False, error="Missing required parameter: 'path'")
        if content is None:
            return ToolResult(success=False, error="Missing required parameter: 'content'")
        try:
            meta = write_file(path, content)
            existed = meta.pop("existed_before")
            return ToolResult(
                success=True,
                output=f"{'Updated' if existed else 'Created'} {meta['path']}",
                metadata=meta,
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc), metadata={"path": path})

    def _list(self, args: dict) -> ToolResult:
        directory = args.get("directory", ".")
        glob_pat = args.get("glob")
        recursive = bool(args.get("recursive", False))
        try:
            files = list_files(directory, glob=glob_pat, recursive=recursive)
            return ToolResult(
                success=True,
                output=f"{len(files)} file(s)",
                metadata={"directory": directory, "count": len(files), "files": files},
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def _search(self, args: dict) -> ToolResult:
        pattern = args.get("pattern")
        if not pattern:
            return ToolResult(success=False, error="Missing required parameter: 'pattern'")
        glob_pat = args.get("glob")
        max_results = int(args.get("max_results", 50))
        try:
            matches = search_files(pattern, glob=glob_pat, max_results=max_results)
            return ToolResult(
                success=True,
                output=f"{len(matches)} match(es)",
                metadata={"pattern": pattern, "matches": matches},
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))
