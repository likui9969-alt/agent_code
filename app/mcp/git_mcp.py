"""GitMCP — Git operations as MCP tools (**interface only**).

This module defines the *shape* of a Git MCP plugin.  All ``execute`` methods
return mock responses — no real git repository is touched.  In production,
wire this to a real git backend (e.g. via ``gitpython`` or a ``git`` CLI
subprocess sandbox).

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

# ── Mock git data (for demo) ────────────────────────────────────────────────
_MOCK_LOG = [
    {"hash": "a1b2c3d", "author": "Alice", "date": "2026-06-08", "message": "feat: add user auth"},
    {"hash": "e4f5g6h", "author": "Bob",   "date": "2026-06-07", "message": "fix: null pointer in parser"},
    {"hash": "i7j8k9l", "author": "Alice", "date": "2026-06-06", "message": "chore: bump version to 2.0"},
]

_MOCK_STATUS = {
    "staged":   ["src/auth.py", "tests/test_auth.py"],
    "modified": ["README.md"],
    "untracked": ["docs/new-feature.md"],
}

_MOCK_BRANCHES = ["main", "develop", "feat/new-auth", "fix/parser-bug"]


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

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        match tool_name:
            case "git_diff":
                return self._diff(arguments)
            case "git_log":
                return self._log(arguments)
            case "git_status":
                return self._status(arguments)
            case "git_branch":
                return self._branch(arguments)
            case "git_blame":
                return self._blame(arguments)
            case _:
                return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    # ── Mock implementations ───────────────────────────────────────────

    def _diff(self, args: dict) -> ToolResult:
        target = args.get("target", "HEAD")
        staged = args.get("staged", False)
        path = args.get("path", "")

        diff_text = (
            f"diff --git a/{path or 'src/main.py'} b/{path or 'src/main.py'}\n"
            f"--- a/{path or 'src/main.py'}\n"
            f"+++ b/{path or 'src/main.py'}\n"
            f"@@ -1,3 +1,4 @@\n"
            f" def main():\n"
            f"-    print('hello')\n"
            f"+    print('hello, world')\n"
            f"+    logger.info('started')\n"
        ) if not path else (
            f"[mock] diff for {path} vs {target} (staged={staged})\n"
            f"+ added line 1\n- removed line 2\n"
        )
        return ToolResult(
            success=True,
            output=diff_text,
            metadata={"target": target, "staged": staged, "path": path, "files_changed": 1},
        )

    def _log(self, args: dict) -> ToolResult:
        n = int(args.get("n", 4))
        author = args.get("author")
        entries = _MOCK_LOG[:n]
        if author:
            entries = [e for e in entries if e["author"].lower() == author.lower()]

        lines = [f"{e['hash']}  {e['author']:<8} {e['date']}  {e['message']}" for e in entries]
        return ToolResult(
            success=True,
            output="\n".join(lines),
            metadata={"count": len(entries), "author_filter": author},
        )

    def _status(self, args: dict) -> ToolResult:
        return ToolResult(
            success=True,
            output=(
                f"Staged:    {len(_MOCK_STATUS['staged'])} file(s)\n"
                f"Modified:  {len(_MOCK_STATUS['modified'])} file(s)\n"
                f"Untracked: {len(_MOCK_STATUS['untracked'])} file(s)"
            ),
            metadata=_MOCK_STATUS,
        )

    def _branch(self, args: dict) -> ToolResult:
        action = args.get("action", "list")
        name = args.get("name", "")

        if action == "list":
            return ToolResult(
                success=True,
                output="\n".join(f"  {'*' if b == 'main' else ' '} {b}" for b in _MOCK_BRANCHES),
                metadata={"branches": _MOCK_BRANCHES, "current": "main"},
            )
        elif action in ("create", "switch"):
            return ToolResult(
                success=True,
                output=f"[mock] {action}d branch '{name}'",
                metadata={"action": action, "branch": name},
            )
        return ToolResult(success=False, error=f"Unknown action: {action}")

    def _blame(self, args: dict) -> ToolResult:
        path = args["path"]
        start = int(args.get("start_line", 1))
        end = int(args.get("end_line", start + 4))

        lines = []
        for i in range(start, end + 1):
            entry = _MOCK_LOG[i % len(_MOCK_LOG)]
            lines.append(f"{entry['hash'][:7]}  ({entry['author']:<6} {entry['date']})  line {i}: code...")

        return ToolResult(
            success=True,
            output="\n".join(lines),
            metadata={"path": path, "start": start, "end": end},
        )

    def health_check(self) -> bool:
        """Git MCP is always 'healthy' in mock mode."""
        return True
