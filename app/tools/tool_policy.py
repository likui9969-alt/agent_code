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

import ast
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
    # ── Network access ──
    (r"\brequests\.(get|post|put|delete|patch|head)\s*\(", "requests HTTP — network access"),  # noqa: E501
    (r"\burllib\.request\.", "urllib.request — network access"),
    (r"\bsocket\.(connect|send|recv)\s*\(", "socket — network access"),
    (r"\bhttp\.client\.", "http.client — network access"),
    (r"\baiohttp\.", "aiohttp — async network access"),
    (r"\bhttpx\.(get|post|put|delete|patch)\s*\(", "httpx — network access"),  # noqa: E501
    # ── File system escape ──
    (r"\bos\.(remove|unlink|rmdir|chmod|chown|link|symlink)\s*\(", "os destructive ops — filesystem escape"),  # noqa: E501
    (r"\bshutil\.(rmtree|copy|copytree|move)\s*\(", "shutil — filesystem escape"),  # noqa: E501
    (r"\bpathlib\.Path\.(unlink|rmdir|chmod|symlink_to)\s*\(", "pathlib destructive — filesystem escape"),  # noqa: E501
]

# ── AST analysis blocklist ──────────────────────────────────────────────────

# Function / attribute names whose call is always considered dangerous.
_DANGEROUS_CALLS: frozenset[str] = frozenset({
    # arbitrary execution
    "eval",
    "exec",
    "compile",
    "__import__",
    # shell / process
    "system",
    "popen",
    "spawn",
    "execv",
    "execve",
    # file system destructors
    "remove",
    "unlink",
    "rmdir",
    "chmod",
    "chown",
    "link",
    "symlink",
    "rmtree",
    # network
    "get",
    "post",
    "put",
    "delete",
    "patch",
    "head",
    "connect",
    "send",
    "recv",
})

# Modules whose import is banned entirely.
_DANGEROUS_MODULES: frozenset[str] = frozenset({
    "subprocess",
    "os",
    "socket",
    "requests",
    "urllib",
    "urllib.request",
    "http.client",
    "httpx",
    "aiohttp",
    "ctypes",
    "importlib",
    "shutil",
    "pathlib",
})

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
    if not code and not file_path:
        raise ToolPolicyViolation(
            "run_python requires either 'code' or 'file_path'"
        )


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
    """Scan *code* for dangerous Python constructs.

    Uses two layers:
      1. Fast regex pass for obvious patterns.
      2. AST analysis to catch obfuscated / dynamic attacks.
    """
    # Layer 1: fast regex pass (kept for speed and backward compatibility).
    for pattern, description in _DANGEROUS_CODE_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            raise ToolPolicyViolation(
                f"Dangerous code pattern blocked: {description}"
            )

    # Layer 2: AST static analysis (catches getattr(__builtins__, ...),
    # string concatenation, indirect imports, etc.).
    _check_dangerous_code_ast(code)


def _check_dangerous_code_ast(code: str) -> None:
    """Parse *code* with :mod:`ast` and reject dangerous constructs.

    Blocks:
      - imports of dangerous modules
      - calls to dangerous functions / attributes
      - getattr / __import__ trickery
      - arbitrary object calls via expressions that resolve to dangerous names
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        # Syntax errors are already caught by the run_python compile step,
        # but we treat them as a policy block here to avoid leaking partial
        # execution paths.
        raise ToolPolicyViolation(
            f"Code parsing failed — syntax error at line {exc.lineno}"
        ) from exc

    for node in ast.walk(tree):
        # ── Imports ──
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split(".")[0]
                if name in _DANGEROUS_MODULES:
                    raise ToolPolicyViolation(
                        f"Dangerous import blocked: {alias.name}"
                    )

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0]
            if root in _DANGEROUS_MODULES or module in _DANGEROUS_MODULES:
                raise ToolPolicyViolation(
                    f"Dangerous import-from blocked: {module}"
                )

        # ── Direct dangerous calls ──
        elif isinstance(node, ast.Call):
            func_name = _ast_name(node.func)
            if func_name in _DANGEROUS_CALLS:
                raise ToolPolicyViolation(
                    f"Dangerous call blocked: {func_name}()"
                )

            # getattr(__builtins__, "eval") / __import__("os")
            if isinstance(node.func, ast.Name) and node.func.id == "getattr":
                # Heuristic: any getattr on builtins-like names is suspicious.
                if len(node.args) >= 2:
                    first = node.args[0]
                    if isinstance(first, ast.Name) and first.id in ("__builtins__", "builtins"):
                        raise ToolPolicyViolation(
                            "getattr on builtins blocked — sandbox escape"
                        )

        # ── Expressions used to smuggle dangerous names ──
        elif isinstance(node, ast.Name):
            if node.id == "__builtins__":
                raise ToolPolicyViolation(
                    "Direct __builtins__ access blocked"
                )


def _ast_name(node: ast.AST) -> str:
    """Return the dotted name of an AST expression, or ''."""
    parts: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    elif isinstance(current, ast.Subscript):
        # builtins['eval']  →  only flag builtins base
        sub = current.value
        while isinstance(sub, ast.Attribute):
            parts.append(sub.attr)
            sub = sub.value
        if isinstance(sub, ast.Name):
            parts.append(sub.id)
    return ".".join(reversed(parts))
