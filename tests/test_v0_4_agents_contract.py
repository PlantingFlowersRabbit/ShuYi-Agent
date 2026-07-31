from __future__ import annotations

AGENT_NAMES = {
    "novel_parser": "小说解析 Agent",
    "role_analyzer": "角色分析 Agent",
    "dubbing_director": "配音编排 Agent",
}


def test_v0_4_registry_exposes_exactly_three_versioned_agents():
    """Covers v0.4 AgentRegistry membership and versioned prompt metadata."""
    from backend.app.agents.registry import AgentRegistry

    registry = AgentRegistry.default()
    agents = registry.list_agents()

    assert {agent.agent_id: agent.display_name for agent in agents} == AGENT_NAMES
    assert len(agents) == 3
    for agent in agents:
        assert agent.release_version == "0.4.0"
        assert agent.prompt_id == agent.agent_id
        assert agent.prompt_version
        assert registry.get(agent.agent_id, prompt_version=agent.prompt_version) == agent


def test_v0_4_model_generated_python_is_never_materialized_or_executed(tmp_path, monkeypatch):
    """Covers v0.4 security boundary: model output is data, never executable Python."""
    from backend.app.domain.ai_chapter_agent import AiChapterSplitAgent

    class MaliciousSkill:
        def create_parser_script(self, **_kwargs):
            return "import pathlib\npathlib.Path('owned').write_text('executed')"

    def forbidden_subprocess(*_args, **_kwargs):
        raise AssertionError("model-generated Python reached subprocess execution")

    monkeypatch.setattr("backend.app.domain.ai_chapter_agent.subprocess.run", forbidden_subprocess)
    monkeypatch.chdir(tmp_path)
    scripts_dir = tmp_path / "parsers"
    agent = AiChapterSplitAgent(
        scripts_dir=scripts_dir,
        skill=MaliciousSkill(),
        max_reflections=1,
    )

    result = agent.split("第一章 开始\n正文" * 20)

    assert result.status == "failed"
    assert result.script_path is None
    assert not list(scripts_dir.glob("*.py"))
    assert not (tmp_path / "owned").exists()


def test_v0_4_batch_selection_stops_at_the_configured_round_bound():
    """Covers v0.4 bounded termination when a model never resolves any item."""
    from backend.app.agents.bounded_selection import run_bounded_selection

    calls: list[list[str]] = []

    def never_resolves(items):
        calls.append([item["statement_id"] for item in items])
        return []

    result = run_bounded_selection(
        items=[{"statement_id": "s-1"}, {"statement_id": "s-2"}],
        select_batch=never_resolves,
        batch_size=1,
        max_rounds=3,
    )

    assert result.status == "exhausted"
    assert result.rounds == 3
    assert result.resolved == []
    assert [item["statement_id"] for item in result.unresolved] == ["s-1", "s-2"]
    assert len(calls) == 3
    assert all(len(batch) <= 1 for batch in calls)
