from __future__ import annotations

AGENT_NAMES = {
    "novel_parser": "文本模型",
    "role_analyzer": "角色分析 Agent",
    "dubbing_director": "配音编排 Agent",
}


def test_v0_5_registry_exposes_exactly_three_versioned_agents():
    """Covers v0.5 AgentRegistry membership and versioned prompt metadata."""
    from backend.app.agents.registry import AgentRegistry

    registry = AgentRegistry.default()
    agents = registry.list_agents()

    assert {agent.agent_id: agent.display_name for agent in agents} == AGENT_NAMES
    assert len(agents) == 3
    for agent in agents:
        assert agent.release_version == "0.7.1"
        assert agent.prompt_id == agent.agent_id
        assert agent.prompt_version
        assert agent.prompt_text.strip()
        assert agent.prompt_sha256
        assert agent.input_schema
        assert agent.output_schema
        assert agent.timeout_seconds > 0
        assert agent.max_retries >= 0
        assert agent.checkpoint_policy
        assert registry.get(agent.agent_id, prompt_version=agent.prompt_version) == agent


def test_v0_5_application_uses_registry_prompts_in_runtime_skills(monkeypatch):
    """生产应用创建的技能必须引用集中管理的版本化 Prompt。"""
    from backend.app.api.app import _create_dubbing_workflow, create_app
    from backend.app.domain.ai_chapter_agent import ChapterSplitSkill

    app = create_app()
    registry = app.state.agent_registry
    workflow = _create_dubbing_workflow(app)
    chapter_skill = ChapterSplitSkill(
        system_prompt=registry.get("novel_parser").prompt_text,
    )

    assert chapter_skill.system_prompt == registry.get("novel_parser").prompt_text
    assert (
        workflow.role_skill.role_analysis_system_prompt == registry.get("role_analyzer").prompt_text
    )
    assert workflow.role_skill.dubbing_system_prompt == registry.get("dubbing_director").prompt_text


def test_v0_5_model_generated_python_is_never_materialized_or_executed(tmp_path, monkeypatch):
    """Covers v0.5 security boundary: model output is data, never executable Python."""
    from backend.app.domain.ai_chapter_agent import AiChapterSplitAgent

    class MaliciousSkill:
        def create_parser_rule(self, **_kwargs):
            return "import pathlib\npathlib.Path('owned').write_text('executed')"

    monkeypatch.chdir(tmp_path)
    rules_dir = tmp_path / "rules"
    agent = AiChapterSplitAgent(
        rules_dir=rules_dir,
        skill=MaliciousSkill(),
        max_reflections=1,
    )

    result = agent.split("第一章 开始\n正文" * 20)

    assert result.status == "failed"
    assert result.rule_path is None
    assert not list(rules_dir.glob("*.py"))
    assert not (tmp_path / "owned").exists()


def test_v0_5_existing_python_rules_are_never_executed(tmp_path, monkeypatch):
    """旧版 Python 解析器即使仍在规则目录中，也不得被运行。"""
    from backend.app.domain.ai_chapter_agent import AiChapterSplitAgent

    rules_dir = tmp_path / "chapter_rules"
    rules_dir.mkdir()
    (rules_dir / "legacy_parser.py").write_text(
        "from pathlib import Path\nPath('owned').write_text('executed')\n",
        encoding="utf-8",
    )

    class InvalidRuleSkill:
        def create_parser_rule(self, **_kwargs):
            return "不是有效的结构化规则"

    monkeypatch.chdir(tmp_path)
    result = AiChapterSplitAgent(
        rules_dir=rules_dir,
        skill=InvalidRuleSkill(),
        max_reflections=1,
    ).split("第一章 开始\n正文" * 20)

    assert result.status == "failed"
    assert not (tmp_path / "owned").exists()


def test_v0_5_batch_selection_stops_at_the_configured_round_bound():
    """Covers v0.5 bounded termination when a model never resolves any item."""
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


def test_v0_5_real_role_selection_service_stops_when_model_never_resolves():
    """真实配音编排服务不能因 uncertain 响应无限调用模型。"""
    from backend.app.domain.dubbing_workflow import BatchRoleSelectionService

    class NeverResolves:
        def __init__(self):
            self.calls = 0

        def choose_roles_batch(self, **kwargs):
            self.calls += 1
            return {
                "items": [
                    {
                        "statement_id": item["statement_id"],
                        "action": "uncertain",
                        "role_id": None,
                        "confidence": 0.0,
                        "reason": "无法确定",
                    }
                    for item in kwargs["statements"]
                ]
            }

    skill = NeverResolves()
    service = BatchRoleSelectionService(skill, batch_size=1, max_rounds=2)
    report = service.select_roles_for_statements_batch(
        chapter_id="chapter-0001",
        chapter_title="第一章",
        paragraphs=[{"paragraph_id": "p-1", "text": "未知人物说道。"}],
        utterances_by_paragraph={"p-1": [{"utterance_id": "p-1-u-001", "text": "未知人物说道。"}]},
        roles=[{"role_id": "narrator", "name": "旁白"}],
    )

    assert skill.calls == 2
    assert report.status == "needs_human_review"
    assert report.uncertain_count >= 1


def test_v0_5_workflow_preserves_human_review_status():
    """上层工作流不得把待人工处理误报为已完成。"""
    from backend.app.domain.dubbing_workflow import DubbingWorkflow

    class NeverResolves:
        def analyze_roles(self, **_kwargs):
            return []

        def choose_roles_batch(self, **kwargs):
            return {
                "items": [
                    {
                        "statement_id": item["statement_id"],
                        "action": "uncertain",
                        "role_id": None,
                        "confidence": 0.0,
                        "reason": "无法确定",
                    }
                    for item in kwargs["statements"]
                ]
            }

    workflow = DubbingWorkflow(role_skill=NeverResolves(), segmentation_service=None)
    started = workflow.start_role_analysis(
        chapter_id="chapter-0001",
        chapter_title="第一章",
        paragraphs=[{"paragraph_id": "p-1", "text": "未知人物说道。"}],
        existing_roles=[],
    )
    resumed = workflow.resume_after_roles(
        thread_id=started.thread_id,
        roles=[{"role_id": "narrator", "name": "旁白"}],
        existing_utterances_by_paragraph={},
    )

    assert resumed.status == "needs_human_review"
    assert "人工" in resumed.message


def test_v0_5_rejects_nested_quantifier_heading_regex():
    """模型给出的嵌套量词正则不得进入小说全文匹配。"""
    from backend.app.domain.ai_chapter_agent import _validate_chapter_rule

    spec, error = _validate_chapter_rule(
        {"heading_pattern": r"^((a+)+)$", "description": "危险规则"}
    )

    assert spec is None
    assert error and "嵌套量词" in error


def test_v0_5_rejects_overlapping_alternation_heading_regex():
    """互相包含的 alternation 不能靠运行时超时兜底。"""
    from backend.app.domain.ai_chapter_agent import _validate_chapter_rule

    spec, error = _validate_chapter_rule(
        {"heading_pattern": r"^((a|aa)+b)$", "description": "危险规则"}
    )

    assert spec is None
    assert error and "重叠分支" in error
