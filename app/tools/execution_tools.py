"""Execution tools — run Python files from the open project directory."""

from __future__ import annotations

from app.project_workspace import resolve_path
from app.tools.base import BaseTool, ToolResult
from app.tools.registry import tool_registry


class RunPythonTool(BaseTool):
    name = "run_python"
    description = (
        "Execute Python code in a sandbox (mock). "
        "Provide either *code* as a string or *file_path* (relative) to run a project file. "
        "Returns stdout, stderr, and exit_code."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python source code to execute directly.",
            },
            "file_path": {
                "type": "string",
                "description": "Relative path to a .py file in the project.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Max execution time. Default: 30.",
            },
        },
        "required": [],
    }

    def execute(
        self,
        code: str | None = None,
        file_path: str | None = None,
        timeout_seconds: int = 30,
    ) -> ToolResult:
        if file_path:
            try:
                fp = resolve_path(file_path, must_exist=True)
                if not fp.is_file():
                    return ToolResult(
                        success=False,
                        error=f"Not a file: '{file_path}'",
                        metadata={"file_path": file_path},
                    )
                source = fp.read_text(encoding="utf-8", errors="replace")
                source_type = "file"
            except Exception as exc:
                return ToolResult(
                    success=False,
                    error=str(exc),
                    metadata={"file_path": file_path},
                )
        elif code:
            source = code
            source_type = "inline"
        else:
            return ToolResult(
                success=False,
                error="Either 'code' or 'file_path' must be provided.",
            )

        stdout, stderr, exit_code = _mock_execute(source)

        return ToolResult(
            success=exit_code == 0,
            output=stdout or "(no output)",
            error=stderr if exit_code != 0 else None,
            metadata={
                "source_type": source_type,
                "file_path": file_path,
                "exit_code": exit_code,
                "stdout_lines": len(stdout.split("\n")) if stdout else 0,
                "timeout_seconds": timeout_seconds,
                "sandbox": "mock",
            },
        )


def _mock_execute(source: str) -> tuple[str, str, int]:
    """Simulate running Python code (syntax + safety checks only)."""
    stdout = ""
    stderr = ""

    try:
        compile(source, "<sandbox>", "exec")
    except SyntaxError as exc:
        return "", f"SyntaxError: {exc.msg} (line {exc.lineno})", 1

    dangerous = ["os.system", "subprocess", "shutil.rmtree", "eval(", "exec("]
    for kw in dangerous:
        if kw in source:
            return "", f"SecurityError: dangerous call '{kw}' blocked by sandbox", 1

    for line in source.split("\n"):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            try:
                compile(stripped, "<sandbox>", "exec")
            except SyntaxError:
                stderr += f"ImportError: bad syntax in '{stripped}'\n"

    if 'print(' in source or 'print(' in source.lower():
        import re
        prints = re.findall(r'print\s*\(\s*(.+?)\s*\)', source)
        if prints:
            stdout = "\n".join(f"[mock] {p}" for p in prints)
        else:
            stdout = "[mock] code executed successfully (no output captured)"
    else:
        stdout = "[mock] code executed successfully"

    if stderr:
        return stdout, stderr.strip(), 0

    return stdout, "", 0


tool_registry.register(RunPythonTool())
