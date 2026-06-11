"""Tool execution guardrails — pre-execution policy checks.

These checks run **before** any tool executes, providing an additional
defence layer against prompt-injection attacks that attempt to:

- Write to sensitive files (``.env``, ``.git``, credentials).
- Write excessively large files (disk-exhaustion).
- Execute dangerous Python constructs.

Design
------
Policy checks are **deny-by-default**: unknown tool names are rejected.
Each check is stateless and side-effect-free — safe to call at high frequency.

Note
----
This is defence-in-depth, not a silver bullet.  A sufficiently advanced
prompt injection can still bypass these checks by, e.g., generating code
that passes syntax validation but performs malicious actions when later
run by a human.  The goal is to raise the cost of successful attacks.
"""

from __future__ import annotations

import re
from typing import Any

# ============================================================================
# Sensitive-file patterns (checked against relative paths)
# ============================================================================

_SENSITIVE_GLOBS: tuple[str, ...] = (
    ".env", ".env.*", ".env.local", ".env.production",
    "*.pem", "*.key", "*.crt", "*.cer",
    "id_rsa", "id_ed25519", "id_ecdsa",
    "credentials*", "secret*", "*.secret",
    ".git/config", ".git/HEAD",
    "*.pfx", "*.p12", "*.keystore", "*.jks",
    "*.tfstate", "*.tfstate.backup",
    "config.json", "secrets.toml", "secrets.yaml",
)

# ============================================================================
# Dangerous Python patterns (checked against code to be executed)
# ============================================================================

_DANGEROUS_CODE_PATTERNS: list[tuple[str, str]] = [
    # (regex, description)
    (r"\beval\s*\(", "eval() — arbitrary code execution"),  # noqa: E501
    (r"\bexec\s*\(", "exec() — arbitrary code execution"),  # noqa: E501
    (r"\b__import__\s*\(", "__import__() — dynamic module loading"),  # noqa: E501
    (r"\bcompile\s*\(", "compile() — code object creation"),  # noqa: E501
    (r"\bopen\s*\([^)]*\b[wa]\b", "open() for write/append — filesystem access"),  # noqa: E501
    (r"\bos\.system\s*\(", "os.system() — shell command execution"),  # noqa: E501
    (r"\bsubprocess\.", "subprocess — process execution"),
    (r"\bos\.popen\s*\(", "os.popen() — shell pipe execution"),
    (r"\bctypes\.", "ctypes — native code loading"),
    (r"\b__builtins__\b", "__builtins__ access — sandbox escape"),
    (r"\bimportlib\.import_module\s*\(", "importlib.import_module() — dynamic import"),  # noqa: E501
    (r"\bbuiltins\.\w+\s*\[", "builtins subscript access — sandbox escape"),
]

# ============================================================================
# Size limits
# ============================================================================

_MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB per file


# ============================================================================
# Policy checker
# ============================================================================


class ToolPolicyViolation(Exception):
    """Raised when a tool call violates a security policy."""


def check_tool_policy(tool_name: str, arguments: dict[str, Any]) -> None:
    """Run pre-execution policy checks on *tool_name* + *arguments*.

    Raises:
        ToolPolicyViolation: if the call is blocked by policy.
    """
    # ── Dispatch by tool ──────────────────────────────────────────────
    if tool_name in ("write_file", "mcp:file:write_file"):
        _check_write_file(arguments)
    elif tool_name in ("run_python",):
        _check_run_python(arguments)
    elif tool_name in ("read_file", "mcp:file:read_file",
                       "grep", "list_files",
                       "mcp:file:list_directory", "mcp:file:search_files"):
        _check_read_file(arguments)
    elif tool_name.startswith("mcp:"):
        # Unknown MCP tool — allow through (the MCP plugin handles its own validation)
        return
    else:
        # Unknown native tool — deny
        raise ToolPolicyViolation(f"Unknown tool blocked by policy: {tool_name!r}")


# ── Per-tool checks ──────────────────────────────────────────────────────────


def _check_write_file(args: dict[str, Any]) -> None:
    path = args.get("path", "")
    content = args.get("content", "")

    _check_sensitive_path(path)
    _check_file_size(content, path)


def _check_run_python(args: dict[str, Any]) -> None:
    code = args.get("code", "")
    file_path = args.get("file_path", "")

    if file_path:
        _check_sensitive_path(file_path)
    if code:
        _check_dangerous_code(code)


def _check_read_file(args: dict[str, Any]) -> None:
    path = args.get("path", "")
    _check_sensitive_path(path)


# ── Atomic checks ────────────────────────────────────────────────────────────


def _check_sensitive_path(path: str) -> None:
    """Reject paths that match sensitive-file patterns."""
    if not path:
        return

    path_lower = path.lower().replace("\\", "/")

    import fnmatch
    for pattern in _SENSITIVE_GLOBS:
        if fnmatch.fnmatch(path_lower, pattern) or fnmatch.fnmatch(
            path_lower.split("/")[-1] if "/" in path_lower else path_lower,
            pattern,
        ):
            raise ToolPolicyViolation(
                f"Access to sensitive file blocked: {path!r} "
                f"(matches pattern {pattern!r})"
            )


def _check_file_size(content: str, path: str) -> None:
    """Reject writes that exceed the maximum file size."""
    size = len(content.encode("utf-8"))
    if size > _MAX_FILE_SIZE_BYTES:
        raise ToolPolicyViolation(
            f"File too large: {path!r} ({size / 1024 / 1024:.1f} MB, "
            f"max {_MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f} MB)"
        )


def _check_dangerous_code(code: str) -> None:
    """Scan *code* for dangerous Python constructs."""
    for pattern, description in _DANGEROUS_CODE_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            raise ToolPolicyViolation(
                f"Dangerous code pattern blocked: {description}"
            )
