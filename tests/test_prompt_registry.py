import pytest

from src.agents.prompts.registry import load_registry, prompt_hash, record_usage, render


def test_default_prompts_are_versioned_and_hashable():
    registry = load_registry()
    assert registry["cn_research_agent_system"].prompt_version == 1
    assert prompt_hash("cn_research_agent_system")
    assert "never invent" in render("cn_research_agent_system")


def test_render_rejects_missing_and_extra_variables(tmp_path):
    (tmp_path / "x.md").write_text("---\nname: x\nversion: 1\nvariables: [symbol]\n---\nHello {symbol}", encoding="utf-8")
    load_registry(tmp_path)
    assert render("x", symbol="600519.SH") == "Hello 600519.SH"
    with pytest.raises(ValueError): render("x")
    with pytest.raises(ValueError): render("x", symbol="x", extra="bad")


def test_explicit_version_and_usage_record(tmp_path):
    (tmp_path / "x1.md").write_text("---\nname: x\nversion: 1\nvariables: []\n---\none", encoding="utf-8")
    (tmp_path / "x2.md").write_text("---\nname: x\nversion: 2\nvariables: []\n---\ntwo", encoding="utf-8")
    load_registry(tmp_path)
    assert render("x@1") == "one" and render("x") == "two"
    usage = record_usage("x@1", "offline", 0.0)
    assert usage["prompt_version"] == 1 and usage["prompt_hash"] == prompt_hash("x@1")
