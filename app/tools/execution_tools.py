"""Execution tools — run Python files from the open project directory.

.. warning::
    The execution backend is **not implemented**.  Only syntax validation
    is performed.  To enable real execution, replace :func:`_validate_syntax`
    with a proper sandbox (e.g. ``subprocess`` in a container).
"""

from __future__ import annotations

from app.project_workspace import resolve_path
from app.tools.base import BaseTool, ToolResult
from app.tools.registry import tool_registry


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
    return (
        "Syntax validation passed. "
        "Code was NOT executed — the Python execution backend is not implemented.",
        "",
    )


class RunPythonTool(BaseTool):
    name = "run_python"
    description = (
        "Validate Python syntax and (when backend is wired) execute code. "
        "Currently only syntax validation is available — no real execution. "
        "Provide either *code* as a string or *file_path* (relative) to run a project file."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python source code to validate (and eventually execute).",
            },
            "file_path": {
                "type": "string",
                "description": "Relative path to a .py file in the project.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Max execution time. Default: 30. (Not yet used.)",
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
            source = code
            source_type = "inline"
        else:
            return ToolResult(
                success=False,
                error="Either 'code' or 'file_path' must be provided.",
            )

        # ── Syntax validation only — no real execution ──
        output, err = _validate_syntax(source)

        if err:
            return ToolResult(
                success=False,
                output=output,
                error=err,
                metadata={
                    "source_type": source_type,
                    "file_path": file_path,
                    "timeout_seconds": timeout_seconds,
                    "execution_backend": "none",
                    "note": "Syntax validation only — code was NOT executed.",
                },
            )

        return ToolResult(
            success=False,
            output=output,
            error="Python execution backend not implemented. "
                  "Only syntax validation was performed — code was NOT executed.",
            metadata={
                "source_type": source_type,
                "file_path": file_path,
                "timeout_seconds": timeout_seconds,
                "execution_backend": "none",
                "note": "Syntax validation passed, but no real execution occurred.",
            },
        )


tool_registry.register(RunPythonTool())
