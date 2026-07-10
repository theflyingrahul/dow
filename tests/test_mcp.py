"""MCP server: tool/resource registration, agnostic-aware docs, and parity.

These guard that the MCP surface stays in lock-step with dow.service - including
the data-structure-agnostic contract (built-in text drift is optional and the
`driftEnabled` flag is threaded through the tools) - and that the read-only
context resources register and read. Skipped when the optional `mcp` extra is
not installed.
"""
import asyncio
import os

import pytest

pytest.importorskip("mcp")

from dow import mcp_server as M  # noqa: E402

EXPECTED_TOOLS = {
    "dow_list_specs", "dow_init", "dow_read_spec", "dow_write_spec", "dow_commit",
    "dow_compare", "dow_explain", "dow_eval", "dow_aggregate", "dow_history",
    "dow_inspect", "dow_tag", "dow_tree", "dow_docs",
}


def test_tools_and_resources_registered():
    tools = {t.name for t in asyncio.run(M.mcp.list_tools())}
    assert tools == EXPECTED_TOOLS

    static = {str(r.uri) for r in asyncio.run(M.mcp.list_resources())}
    assert static == {"dow://overview", "dow://specs"}

    templates = {t.uriTemplate for t in asyncio.run(M.mcp.list_resource_templates())}
    assert templates == {"dow://docs/{command}", "dow://spec/{name}"}


def test_overview_resource_is_agnostic_aware():
    text = M.overview_resource()
    lowered = text.lower()
    assert "data-structure agnostic" in lowered
    assert "embedding_model" in text
    assert "dow://docs/" in text
    # per-command docs resource resolves real help text
    assert "compare" in M.command_docs_resource("compare").lower()


def test_project_resources_reflect_the_live_spec(tmp_path):
    d = str(tmp_path)
    M.dow_init(project_dir=d)
    os.environ["DOW_PROJECT_DIR"] = d
    try:
        specs = M.specs_resource()
        assert M.service.EXAMPLE_NAME in specs
        source = M.spec_source_resource(M.service.EXAMPLE_NAME)
        assert "model:" in source and "evaluation:" in source
    finally:
        os.environ.pop("DOW_PROJECT_DIR", None)


def test_compare_tool_threads_the_agnostic_flag(tmp_path):
    d = str(tmp_path)
    M.dow_init(project_dir=d)

    # v1: the scaffolded text spec (built-in drift on).
    M.dow_commit(project_dir=d, message="v1")

    # v2: change one field; built-in drift still on -> driftEnabled True.
    spec = M.dow_read_spec(project_dir=d)["text"]
    spec_v2 = spec.replace("temperature: 0.2", "temperature: 0.9")
    assert spec_v2 != spec
    assert M.dow_write_spec(spec_v2, project_dir=d)["valid"]
    M.dow_commit(project_dir=d, message="v2")

    hot = M.dow_compare(project_dir=d)
    assert hot["driftEnabled"] is True
    assert hot["semanticDrift"] is not None
    assert hot["embeddingModel"] != "none"

    # v3: turn the built-in text drift OFF for non-text outputs.
    spec_v3 = spec_v2.replace("embedding_model: hashing-256", "embedding_model: none")
    assert "embedding_model: none" in spec_v3
    assert M.dow_write_spec(spec_v3, project_dir=d)["valid"]
    M.dow_commit(project_dir=d, message="v3 non-text")

    off = M.dow_compare(project_dir=d)  # v2 vs v3; b=v3 -> drift disabled
    assert off["driftEnabled"] is False
    assert off["semanticDrift"] is None
    assert off["verdict"] is None
    assert off["embeddingModel"] == "none"
    # the configuration diff still carries the comparison
    assert off["configDiff"]

    # explain threads the same flag
    exp = M.dow_explain(project_dir=d)
    assert exp["driftEnabled"] is False
    assert exp["verdict"] is None
