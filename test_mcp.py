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

    # ── Execute MCP tools ──
    print()

    # Git MCP
    r = tool_registry.execute("mcp:git:git_log", {"n": 3})
    print(f"mcp:git:git_log  | success={r.success}")
    print(f"  {r.output.split(chr(10))[0]}")

    r = tool_registry.execute("mcp:git:git_status", {})
    print(f"mcp:git:git_status | success={r.success}")
    print(f"  staged={r.metadata['staged']}")

    r = tool_registry.execute("mcp:git:git_branch", {"action": "list"})
    print(f"mcp:git:git_branch | success={r.success}")

    # File MCP
    with project_root_context(PROJECT_ROOT):
        r = tool_registry.execute(
            "mcp:file:list_directory", {}, project_root=PROJECT_ROOT,
        )
        print(f"mcp:file:list_dir  | success={r.success}, count={r.metadata['count']}")

        r = tool_registry.execute(
            "mcp:file:search_files",
            {"pattern": "LangGraph"},
            project_root=PROJECT_ROOT,
        )
        print(f"mcp:file:search    | success={r.success}, matches={len(r.metadata.get('matches', []))}")

    # ── MCP metadata ──
    print()
    for mcp in mcp_loader.list_loaded():
        print(f"[{mcp['name']}] v{mcp['version']} | {mcp['tool_count']} tools | healthy={mcp['healthy']}")

    # ── Unload test ──
    mcp_loader.unload("git")
    remaining = tool_registry.list_tools()
    git_remaining = [t for t in remaining if "git" in t]
    assert len(git_remaining) == 0, f"Git tools not fully unloaded: {git_remaining}"
    print(f"\nUnload git: OK ({len(remaining)} tools remain)")

    # ── Reload test ──
    mcp_loader.reload("file")
    print(f"Reload file: OK ({len(tool_registry.list_tools())} tools)")

    print("\nAll MCP tests passed!")


if __name__ == "__main__":
    main()
