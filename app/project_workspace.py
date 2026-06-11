"""Project workspace — real filesystem access scoped to an open project root."""

from __future__ import annotations

import fnmatch
import re
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator

IGNORE_PATTERNS = {
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    ".idea", ".vscode", "*.pyc", ".DS_Store", "Thumbs.db",
    ".env", "*.egg-info", "dist", "build",
}

_project_root: ContextVar[str | None] = ContextVar("project_root", default=None)


def _should_ignore(name: str) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in IGNORE_PATTERNS)


def set_project_root(path: str | None) -> None:
    """Set the active project root for the current execution context."""
    _project_root.set(path)


def get_project_root() -> Path | None:
    """Return the resolved project root, or ``None`` if unset."""
    raw = _project_root.get()
    if not raw:
        return None
    p = Path(raw).resolve()
    return p if p.is_dir() else None


@contextmanager
def project_root_context(path: str | None) -> Iterator[None]:
    """Temporarily bind *path* as the active project root."""
    token = _project_root.set(path)
    try:
        yield
    finally:
        _project_root.reset(token)


def require_project_root() -> Path:
    root = get_project_root()
    if root is None:
        raise RuntimeError("No project root set — open a project directory first")
    return root


def resolve_path(relative_path: str, *, must_exist: bool = False) -> Path:
    """Resolve *relative_path* under the project root (blocks traversal)."""
    root = require_project_root()
    rel = relative_path.replace("\\", "/").strip()
    if rel in ("", "."):
        return root
    if rel.startswith("/"):
        rel = rel.lstrip("/")
    if ".." in Path(rel).parts:
        raise ValueError(f"Path traversal not allowed: {relative_path}")

    full = (root / rel).resolve()
    if not full.is_relative_to(root):
        raise ValueError(f"Path outside project root: {relative_path}")
    if must_exist and not full.exists():
        raise FileNotFoundError(f"Path not found: {relative_path}")
    return full


def relative_path(full: Path) -> str:
    root = require_project_root()
    return str(full.relative_to(root)).replace("\\", "/")


def read_file(path: str, start_line: int = 1, end_line: int | None = None) -> tuple[str, dict]:
    fp = resolve_path(path, must_exist=True)
    if not fp.is_file():
        raise IsADirectoryError(f"Not a file: {path}")
    content = fp.read_text(encoding="utf-8", errors="replace")
    lines = content.split("\n")
    total = len(lines)
    end = min(end_line or total, total)
    start = max(1, start_line) - 1
    selected = lines[start:end]
    return "\n".join(selected), {
        "path": relative_path(fp),
        "total_lines": total,
        "start_line": start + 1,
        "end_line": end,
    }


def write_file(path: str, content: str) -> dict:
    fp = resolve_path(path)
    existed = fp.exists()
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")
    return {
        "path": relative_path(fp),
        "bytes_written": len(content.encode("utf-8")),
        "lines": content.count("\n") + 1,
        "existed_before": existed,
    }


def list_files(
    directory: str = ".",
    glob: str | None = None,
    *,
    recursive: bool = False,
) -> list[str]:
    dir_path = resolve_path(directory, must_exist=True)
    if not dir_path.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    root = require_project_root()
    entries: list[str] = []

    def _collect(base: Path) -> None:
        try:
            children = sorted(base.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        except PermissionError:
            return
        for entry in children:
            if _should_ignore(entry.name):
                continue
            rel = str(entry.relative_to(root)).replace("\\", "/")
            if entry.is_file():
                if glob is None or fnmatch.fnmatch(entry.name, glob):
                    entries.append(rel)
            elif entry.is_dir() and recursive:
                _collect(entry)

    _collect(dir_path)
    return sorted(entries)


def search_files(
    pattern: str,
    glob: str | None = None,
    max_results: int = 50,
) -> list[dict]:
    regex = re.compile(pattern)
    matches: list[dict] = []
    for rel in list_files(".", glob=glob, recursive=True):
        fp = resolve_path(rel, must_exist=True)
        if not fp.is_file():
            continue
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(content.split("\n"), 1):
            if regex.search(line):
                matches.append({"file": rel, "line": i, "text": line.strip()})
                if len(matches) >= max_results:
                    return matches
    return matches


def grep_files(
    pattern: str,
    path: str = ".",
    glob: str | None = None,
    context_lines: int = 0,
    max_results: int = 50,
) -> list[dict]:
    regex = re.compile(pattern)
    base = resolve_path(path, must_exist=True)
    root = require_project_root()

    if base.is_file():
        candidates = [relative_path(base)]
    else:
        candidates = list_files(path, glob=glob, recursive=True)

    matches: list[dict] = []
    for rel in candidates:
        fp = resolve_path(rel, must_exist=True)
        if not fp.is_file():
            continue
        try:
            lines = fp.read_text(encoding="utf-8", errors="replace").split("\n")
        except OSError:
            continue
        for i, line in enumerate(lines, start=1):
            if regex.search(line):
                ctx_start = max(0, i - 1 - context_lines)
                ctx_end = min(len(lines), i + context_lines)
                matches.append({
                    "file": rel,
                    "line_num": i,
                    "line": line.strip(),
                    "context": [
                        f"{j}: {lines[j - 1].strip()}"
                        for j in range(ctx_start + 1, ctx_end + 1)
                    ] if context_lines > 0 else [],
                })
                if len(matches) >= max_results:
                    return matches
    return matches
