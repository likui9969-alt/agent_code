"""本地 JSON 设置存储 — 持久化用户偏好。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SettingsStore:
    """JSON-file backed user preferences.

    Data stored in ``data/user_settings.json``.
    """

    _DEFAULTS: dict[str, Any] = {
        "lang": "zh",
        "theme_idx": 0,
        "model": "qwen-plus",
        "api_key": "",
        "api_base_url": "http://localhost:8000",
        "auto_save": True,
        "recent_projects": [],
    }

    def __init__(self, data_dir: str = "data") -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "user_settings.json"
        self._cache = self._load()

    def _load(self) -> dict[str, Any]:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, OSError):
                pass
        return dict(self._DEFAULTS)

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, key: str, default: Any = None) -> Any:
        if key not in self._cache and key in self._DEFAULTS:
            return self._DEFAULTS[key]
        return self._cache.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = value
        self._save()

    def update(self, **kwargs: Any) -> None:
        self._cache.update(kwargs)
        self._save()

    def add_recent_project(self, path: str) -> None:
        """Add *path* to recent projects, keep up to 10 unique entries."""
        recents = self._cache.get("recent_projects", [])
        # Move to front if exists
        if path in recents:
            recents.remove(path)
        recents.insert(0, path)
        self._cache["recent_projects"] = recents[:10]
        self._save()

    def remove_recent_project(self, path: str) -> None:
        recents = self._cache.get("recent_projects", [])
        if path in recents:
            recents.remove(path)
            self._cache["recent_projects"] = recents
            self._save()

    def all(self) -> dict[str, Any]:
        """Return a copy of all settings merged with defaults."""
        merged = dict(self._DEFAULTS)
        merged.update(self._cache)
        return merged


# Module-level singleton
_settings_store: SettingsStore | None = None


def get_settings_store() -> SettingsStore:
    global _settings_store
    if _settings_store is None:
        _settings_store = SettingsStore()
    return _settings_store
