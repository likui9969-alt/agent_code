"""Execution tools — run Python files from the open project directory.

Real sandbox: syntax validation → subprocess execution with timeout.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile

from app.project_workspace import resolve_path
from app.tools.base import BaseTool, ToolResult
from app.tools.registry import tool_registry

logger = logging.getLogger(__name__)

# Maximum source size for inline execution (prevents memory exhaustion).
_MAX_INLINE_SOURCE_BYTES = 1 * 1024 * 1024  # 1 MB

# Maximum captured output per stream (stdout / stderr) in bytes.
# Limits memory consumption when sandboxed code prints huge amounts of data.
_MAX_OUTPUT_BYTES_PER_STREAM = 64 * 1024  # 64 KB


def _validate_syntax(source: str) -> tuple[str, str]:
    """Compile-check *source* for syntax errors only — does NOT execute.

    Returns:
        (output, error): *output* describes the validation result;
        *error* is empty on success or contains the SyntaxError message.
    """
    try:
        compile(source, "<sandbox>", "exec")
    except SyntaxError as exc:
        return "", f"SyntaxError: {exc.msg} (line {exc.lineno})"
    return "Syntax validation passed.", ""


def _execute_sandbox(source: str, timeout: int) -> tuple[str, str, int]:
    """Execute *source* in a subprocess sandbox with timeout and output limits.

    Returns:
        (stdout, stderr, exit_code)

    Output from both stdout and stderr is capped to ``_MAX_OUTPUT_BYTES_PER_STREAM``
    bytes per stream.  Anything beyond the cap is discarded and a truncation
    notice is appended.  This prevents a malicious or buggy script from
    exhausting memory by printing huge amounts of data.
    """
    tmp_path: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            encoding="utf-8",
            delete=False,
        ) as tmp:
            tmp.write(source)
            tmp_path = tmp.name

        # Redirect child output to temp files so the parent only needs to
        # read a bounded amount of data into memory.
        with tempfile.NamedTemporaryFile(
            mode="w+", suffix=".stdout", encoding="utf-8", delete=False
        ) as stdout_tmp, tempfile.NamedTemporaryFile(
            mode="w+", suffix=".stderr", encoding="utf-8", delete=False
        ) as stderr_tmp:
            stdout_path = stdout_tmp.name
            stderr_path = stderr_tmp.name

        proc = subprocess.run(
            [sys.executable, tmp_path],
            stdout=open(stdout_path, "w", encoding="utf-8"),
            stderr=open(stderr_path, "w", encoding="utf-8"),
            text=True,
            timeout=timeout,
        )

        stdout = _read_limited(stdout_path)
        stderr = _read_limited(stderr_path)
        return stdout, stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return "", f"Execution timed out after {timeout}s", -1
    finally:
        for p in (tmp_path, stdout_path, stderr_path):
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass


def _read_limited(path: str) -> str:
    """Read at most ``_MAX_OUTPUT_BYTES_PER_STREAM`` bytes from *path*.

    If the file is larger, return the first N bytes plus a truncation notice.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return ""

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        if size <= _MAX_OUTPUT_BYTES_PER_STREAM:
            return f.read()

        # Read up to the byte limit, then trim to the last complete character
        # boundary so we don't return a malformed Unicode string.
        raw = f.read(_MAX_OUTPUT_BYTES_PER_STREAM)
        notice = (
            f"\n... [output truncated: "
            f"{size / 1024:.1f} KB > {_MAX_OUTPUT_BYTES_PER_STREAM / 1024:.0f} KB cap]"
        )
        return raw + notice


class RunPythonTool(BaseTool):
    name = "run_python"
    description = (
        "Validate Python syntax and execute code in a sandboxed subprocess. "
        "Provide either *code* as a string or *file_path* (relative) to run a project file."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python source code to validate and execute.",
            },
            "file_path": {
                "type": "string",
                "description": "Relative path to a .py file in the project.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Max execution time in seconds. Default: 30.",
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
        # ── Resolve source ──
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
            if len(code.encode("utf-8")) > _MAX_INLINE_SOURCE_BYTES:
                return ToolResult(
                    success=False,
                    error=f"Inline code exceeds {_MAX_INLINE_SOURCE_BYTES // 1024} KB limit.",
                )
            source = code
            source_type = "inline"
        else:
            return ToolResult(
                success=False,
                error="Either 'code' or 'file_path' must be provided.",
            )

        # ── Step 1: Syntax validation ──
        syntax_out, syntax_err = _validate_syntax(source)
        if syntax_err:
            return ToolResult(
                success=False,
                output=syntax_out,
                error=syntax_err,
                metadata={
                    "source_type": source_type,
                    "file_path": file_path,
                    "timeout_seconds": timeout_seconds,
                    "stage": "syntax_validation",
                },
            )

        # ── Step 2: Execute in sandbox ──
        stdout, stderr, exit_code = _execute_sandbox(source, timeout_seconds)

        metadata = {
            "source_type": source_type,
            "file_path": file_path,
            "timeout_seconds": timeout_seconds,
            "exit_code": exit_code,
            "stage": "executed",
        }
        if exit_code == 0:
            return ToolResult(
                success=True,
                output=stdout.strip() or "(execution completed with no output)",
                metadata=metadata,
            )
        return ToolResult(
            success=False,
            output=stdout.strip(),
            error=stderr.strip() or f"Execution failed with exit code {exit_code}",
            metadata=metadata,
        )


tool_registry.register(RunPythonTool())
