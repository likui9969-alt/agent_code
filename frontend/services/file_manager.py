"""本地文件管理器 — 目录扫描、树形结构、CRUD。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

IGNORE_PATTERNS = {
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    ".idea", ".vscode", "*.pyc", ".DS_Store", "Thumbs.db",
    ".env", "*.egg-info", "dist", "build",
}


def _should_ignore(name: str) -> bool:
    import fnmatch
    return any(fnmatch.fnmatch(name, p) for p in IGNORE_PATTERNS)


class FileManager:
    """Manage a local project directory.

    Usage::

        fm = FileManager("/path/to/project")
        tree = fm.scan()
        content = fm.read("src/main.py")
        fm.write("src/main.py", "print('hello')")
    """

    def __init__(self, root_path: str | None = None) -> None:
        self.root_path = Path(root_path).resolve() if root_path else None

    # ── Open / Switch ───────────────────────────────────────────────────

    def open_project(self, path: str) -> dict:
        """Open a directory and return scan result."""
        p = Path(path).resolve()
        if not p.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")
        self.root_path = p
        return self.scan()

    def is_open(self) -> bool:
        return self.root_path is not None and self.root_path.is_dir()

    # ── Scan ────────────────────────────────────────────────────────────

    def scan(self) -> dict:
        """Return a tree dict for the root path."""
        if not self.root_path:
            return {"name": "", "type": "directory", "children": []}
        return self._scan_dir(self.root_path)

    def _scan_dir(self, directory: Path, depth: int = 0) -> dict:
        """Return a tree dict for *directory*.

        Only the immediate level is expanded; nested directories are returned
        as stubs so the UI can lazy-load them on demand.
        """
        rel_path = str(directory.relative_to(self.root_path)) if directory != self.root_path else "."
        node = {"name": directory.name, "type": "directory", "path": rel_path, "children": []}

        try:
            entries = sorted(directory.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        except PermissionError:
            return node

        for entry in entries:
            if _should_ignore(entry.name):
                continue
            child_rel = str(entry.relative_to(self.root_path))
            if entry.is_dir():
                # Only expand the top-level directory. Nested directories are
                # returned as stubs and lazy-loaded by the UI on expansion.
                if depth == 0:
                    node["children"].append(self._scan_dir(entry, depth + 1))
                else:
                    node["children"].append({
                        "name": entry.name,
                        "type": "directory",
                        "path": child_rel,
                        "children": [],
                    })
            else:
                node["children"].append({
                    "name": entry.name,
                    "type": "file",
                    "path": child_rel,
                    "size": entry.stat().st_size,
                })
        return node

    def scan_subdir(self, relative_path: str) -> dict:
        """Lazy-load children of a subdirectory given by *relative_path*."""
        if not self.root_path:
            return {"name": "", "type": "directory", "children": []}
        target = self._resolve(relative_path)
        if not target.is_dir():
            return {"name": target.name, "type": "directory", "children": []}
        node = self._scan_dir(target, depth=1)
        return node

    # ── Read / Write ────────────────────────────────────────────────────

    def _resolve(self, relative_path: str, *, must_exist: bool = False) -> Path:
        if not self.root_path:
            raise RuntimeError("No project open")
        rel = relative_path.replace("\\", "/").strip()
        if rel in ("", "."):
            fp = self.root_path
        else:
            if rel.startswith("/"):
                rel = rel.lstrip("/")
            if ".." in Path(rel).parts:
                raise ValueError(f"Path traversal not allowed: {relative_path}")
            fp = (self.root_path / rel).resolve()
        if not fp.is_relative_to(self.root_path):
            raise ValueError(f"Path outside project root: {relative_path}")
        if must_exist and not fp.exists():
            raise FileNotFoundError(f"File not found: {relative_path}")
        return fp

    def read(self, relative_path: str) -> str:
        fp = self._resolve(relative_path, must_exist=True)
        if not fp.is_file():
            raise IsADirectoryError(f"Not a file: {relative_path}")
        return fp.read_text(encoding="utf-8", errors="replace")

    def write(self, relative_path: str, content: str) -> None:
        fp = self._resolve(relative_path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")

    def create_file(self, relative_path: str, content: str = "") -> str:
        """Create a new file. Returns the relative path."""
        self.write(relative_path, content)
        return relative_path

    def delete_file(self, relative_path: str) -> bool:
        if not self.root_path:
            return False
        try:
            fp = self._resolve(relative_path, must_exist=True)
            if fp.is_file():
                fp.unlink()
                return True
        except (OSError, ValueError, RuntimeError):
            pass
        return False

    def rename_file(self, old_path: str, new_path: str) -> bool:
        if not self.root_path:
            return False
        try:
            old = self._resolve(old_path, must_exist=True)
            new = self._resolve(new_path)
            if old.exists():
                old.rename(new)
                return True
        except (OSError, ValueError, RuntimeError):
            pass
        return False

    def exists(self, relative_path: str) -> bool:
        if not self.root_path:
            return False
        try:
            return self._resolve(relative_path, must_exist=True).exists()
        except (ValueError, RuntimeError, FileNotFoundError):
            return False

    # ── Info ────────────────────────────────────────────────────────────

    def get_project_name(self) -> str:
        return self.root_path.name if self.root_path else ""

    def get_project_path(self) -> str:
        return str(self.root_path) if self.root_path else ""


# Module-level singleton
_file_manager: FileManager | None = None


def get_file_manager() -> FileManager:
    global _file_manager
    if _file_manager is None:
        _file_manager = FileManager()
    return _file_manager
