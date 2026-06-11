"""MCPPluginLoader — discovers, loads, and unloads MCP plugins.

Supports three discovery mechanisms:

1. **Explicit** — call :meth:`load` with a :class:`BaseMCP` instance.
2. **Directory scan** — :meth:`discover_from_directory` scans a folder for
   Python modules that export a ``get_mcp_plugins()`` function.
3. **Entry points** — :meth:`discover_from_entry_points` looks for the
   ``ai_code_assistant.mcp`` setuptools entry-point group.

Loaded MCPs are tracked; each tool is adapted via :class:`MCPToolAdapter`
and registered into the :class:`~app.tools.registry.ToolRegistry`.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from app.mcp.adapters import MCPToolAdapter
from app.mcp.base import BaseMCP
from app.tools.base import BaseTool
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# ── Entry-point group name (for setuptools discovery) ──────────────────────
ENTRY_POINT_GROUP = "ai_code_assistant.mcp"


class MCPPluginLoader:
    """Manages the lifecycle of MCP plugins.

    Usage::

        loader = MCPPluginLoader(tool_registry)
        loader.load(FileMCP())
        loader.load(GitMCP())

        # Later...
        loader.unload("git")
        loader.reload("file")
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry
        self._mcps: dict[str, BaseMCP] = {}          # name → MCP instance
        self._adapters: dict[str, list[MCPToolAdapter]] = {}  # mcp_name → adapters

    # ── Load / Unload ──────────────────────────────────────────────────

    def load(self, mcp: BaseMCP) -> list[MCPToolAdapter]:
        """Register *mcp* and all of its tools into the registry.

        Returns the list of :class:`MCPToolAdapter` instances created.
        """
        if mcp.name in self._mcps:
            logger.warning("MCP '%s' already loaded — reloading", mcp.name)
            self.unload(mcp.name)

        # Health check
        if not mcp.health_check():
            logger.error("MCP '%s' health check failed — skipping", mcp.name)
            return []

        # Lifecycle hook
        mcp.on_load()

        # Adapt & register each tool
        adapters: list[MCPToolAdapter] = []
        for tool_def in mcp.get_tools():
            adapter = MCPToolAdapter(mcp, tool_def)
            self.registry.register(adapter)
            adapters.append(adapter)

        self._mcps[mcp.name] = mcp
        self._adapters[mcp.name] = adapters
        logger.info(
            "MCP loaded: '%s' v%s | %d tool(s): %s",
            mcp.name, mcp.version, len(adapters),
            [a.name for a in adapters],
        )
        return adapters

    def unload(self, name: str) -> None:
        """Remove an MCP plugin and all its tools from the registry."""
        mcp = self._mcps.pop(name, None)
        if mcp is None:
            logger.warning("MCP '%s' not loaded — nothing to unload", name)
            return

        # Remove tools from registry
        for adapter in self._adapters.pop(name, []):
            self.registry.unregister(adapter.name)

        mcp.on_unload()
        logger.info("MCP unloaded: '%s'", name)

    def reload(self, name: str) -> list[MCPToolAdapter] | None:
        """Unload and re-load an MCP by name.  Returns adapters or None."""
        mcp = self._mcps.get(name)
        if mcp is None:
            logger.warning("MCP '%s' not loaded — cannot reload", name)
            return None
        self.unload(name)
        return self.load(mcp)

    def reload_all(self) -> None:
        """Reload every loaded MCP."""
        for name in list(self._mcps.keys()):
            self.reload(name)

    # ── Discovery ──────────────────────────────────────────────────────

    def discover_from_directory(self, directory: str | Path) -> list[BaseMCP]:
        """Scan *directory* for Python files that export ``get_mcp_plugins()``.

        Each .py file in *directory* is loaded as a module.  If the module
        has a top-level ``get_mcp_plugins()`` callable, it is called; it
        must return a ``list[BaseMCP]``.
        """
        directory = Path(directory)
        if not directory.is_dir():
            logger.error("MCP directory not found: %s", directory)
            return []

        discovered: list[BaseMCP] = []
        sys.path.insert(0, str(directory.parent))

        for py_file in sorted(directory.glob("*.py")):
            if py_file.name.startswith("_"):
                continue

            module_name = py_file.stem
            try:
                spec = importlib.util.spec_from_file_location(
                    f"mcp_plugin_{module_name}", py_file
                )
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if hasattr(module, "get_mcp_plugins"):
                    plugins = module.get_mcp_plugins()
                    if isinstance(plugins, list):
                        discovered.extend(plugins)
                        logger.info("Discovered %d MCP(s) in '%s'", len(plugins), py_file)
            except Exception as exc:
                logger.error("Failed to load MCP plugin '%s': %s", py_file, exc)

        return discovered

    def discover_from_entry_points(self) -> list[BaseMCP]:
        """Discover MCPs via the ``ai_code_assistant.mcp`` entry-point group.

        Plugins installed via pip can declare::

            [project.entry-points."ai_code_assistant.mcp"]
            my_mcp = "my_package.mcp:get_mcp_plugins"
        """
        discovered: list[BaseMCP] = []
        try:
            # Python 3.12+ / importlib.metadata
            from importlib.metadata import entry_points
        except ImportError:
            return discovered

        try:
            group = entry_points(group=ENTRY_POINT_GROUP)
        except TypeError:
            # Fallback for older importlib.metadata
            for ep in entry_points().get(ENTRY_POINT_GROUP, []):
                discovered.extend(self._load_entry_point(ep))
            return discovered

        for ep in group:
            discovered.extend(self._load_entry_point(ep))
        return discovered

    def discover_and_load_all(self, directory: str | None = None) -> dict[str, list[MCPToolAdapter]]:
        """Run all discovery mechanisms and load every found MCP.

        Returns a dict ``{mcp_name: [adapters]}``.
        """
        result: dict[str, list[MCPToolAdapter]] = {}

        # 1. Built-in MCPs (always load)
        from app.mcp.file_mcp import FileMCP
        from app.mcp.git_mcp import GitMCP
        for mcp in [FileMCP(), GitMCP()]:
            adapters = self.load(mcp)
            if adapters:
                result[mcp.name] = adapters

        # 2. Directory scan (optional)
        if directory:
            for mcp in self.discover_from_directory(directory):
                adapters = self.load(mcp)
                if adapters:
                    result[mcp.name] = adapters

        # 3. Entry points
        for mcp in self.discover_from_entry_points():
            adapters = self.load(mcp)
            if adapters:
                result[mcp.name] = adapters

        return result

    # ── Introspection ──────────────────────────────────────────────────

    def list_loaded(self) -> list[dict[str, Any]]:
        """Return metadata about every loaded MCP."""
        return [
            {
                "name": mcp.name,
                "description": mcp.description,
                "version": mcp.version,
                "tool_count": len(self._adapters.get(mcp.name, [])),
                "healthy": mcp.health_check(),
            }
            for mcp in self._mcps.values()
        ]

    def get_tools_for_mcp(self, mcp_name: str) -> list[BaseTool]:
        """Return all tool instances belonging to *mcp_name*."""
        return list(self._adapters.get(mcp_name, []))

    # ── Internal ───────────────────────────────────────────────────────

    def _load_entry_point(self, ep: Any) -> list[BaseMCP]:
        try:
            factory = ep.load()
            plugins = factory()
            if isinstance(plugins, list):
                return plugins
        except Exception as exc:
            logger.error("Failed to load entry point '%s': %s", ep.name, exc)
        return []


# ── Module-level singleton (bound to the default registry) ──────────────────
from app.tools.registry import tool_registry  # noqa: E402

mcp_loader = MCPPluginLoader(tool_registry)
