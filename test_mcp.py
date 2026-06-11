"""Quick verification of MCP plugin layer."""
import os
from pathlib import Path

os.environ.setdefault("REDIS_ENABLED", "false")

PROJECT_ROOT = str(Path(__file__).resolve().parent)

from app.project_workspace import project_root_context
from app.tools.registry import tool_registry
from app.mcp.loader import mcp_loader


def main():
    # ── Load all MCPs ──
    result = mcp_loader.discover_and_load_all()
    print("MCPs loaded:", list(result.keys()))

    # ── Tool inventory ──
    all_tools = tool_registry.list_tools()
    print(f"Total tools: {len(all_tools)}")

    src = tool_registry.list_tools_by_source()
    print(f"  native: {src['native']}")
    for mcp_name, tools in src["mcp"].items():
        print(f"  mcp:{mcp_name}: {tools}")

    # GitMCP is skipped because health_check returns False
    assert "git" not in result, "GitMCP should be skipped (unhealthy)"
    git_tools = [t for t in all_tools if "git" in t]
    assert len(git_tools) == 0, f"Git tools should not be registered, got {git_tools}"
    print("\n  GitMCP correctly skipped (health_check=False)")

    # ── Execute MCP tools (File MCP only) ──
    print()

    with project_root_context(PROJECT_ROOT):
        r = tool_registry.execute(
            "mcp:file:list_directory", {}, project_root=PROJECT_ROOT,
        )
        print(f"mcp:file:list_dir  | success={r.success}, count={r.metadata['count']}")
        assert r.success

        r = tool_registry.execute(
            "mcp:file:search_files",
            {"pattern": "LangGraph"},
            project_root=PROJECT_ROOT,
        )
        print(f"mcp:file:search    | success={r.success}, matches={len(r.metadata.get('matches', []))}")
        assert r.success

    # ── MCP metadata ──
    print()
    for mcp in mcp_loader.list_loaded():
        print(f"[{mcp['name']}] v{mcp['version']} | {mcp['tool_count']} tools | healthy={mcp['healthy']}")

    # ── Unload test ──
    mcp_loader.unload("file")
    remaining = tool_registry.list_tools()
    file_remaining = [t for t in remaining if "mcp:file" in t]
    assert len(file_remaining) == 0, f"File MCP tools not fully unloaded: {file_remaining}"
    print(f"\nUnload file: OK ({len(remaining)} tools remain)")

    # ── Reload test ──
    mcp_loader.reload("file")
    print(f"Reload file: OK ({len(tool_registry.list_tools())} tools)")

    # ── GitMCP direct test (bypass loader) — verify "not implemented" ──
    print()
    from app.mcp.git_mcp import GitMCP
    git = GitMCP()
    assert git.health_check() is False, "GitMCP health_check should be False"
    r = git.execute("git_log", {"n": 3})
    assert r.success is False
    assert "not implemented" in r.error.lower()
    print("GitMCP direct: correctly returns 'not implemented'")

    print("\nAll MCP tests passed!")


if __name__ == "__main__":
    main()
