from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    display_name: str
    release_version: str
    prompt_id: str
    prompt_version: str
    prompt_text: str
    prompt_sha256: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    validator_id: str
    timeout_seconds: int
    max_retries: int
    checkpoint_policy: str


class AgentRegistry:
    def __init__(self, agents: list[AgentDefinition]):
        self._agents = {agent.agent_id: agent for agent in agents}

    @classmethod
    def default(cls) -> AgentRegistry:
        names = {
            "novel_parser": "文本模型",
            "role_analyzer": "角色分析 Agent",
            "dubbing_director": "配音编排 Agent",
        }
        agents = []
        for agent_id, display_name in names.items():
            prompt_version = "1"
            prompt_text = (PROMPT_DIR / f"{agent_id}.v{prompt_version}.txt").read_text(
                encoding="utf-8"
            )
            agents.append(
                AgentDefinition(
                    agent_id=agent_id,
                    display_name=display_name,
                    release_version="0.6.6",
                    prompt_id=agent_id,
                    prompt_version=prompt_version,
                    prompt_text=prompt_text,
                    prompt_sha256=hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
                    input_schema={"type": "object", "additionalProperties": False},
                    output_schema={"type": "object"},
                    validator_id=f"{agent_id}.v1",
                    timeout_seconds=120,
                    max_retries=2,
                    checkpoint_policy="每个 Agent 完成后写入 SQLite",
                )
            )
        return cls(agents)

    def list_agents(self) -> list[AgentDefinition]:
        return list(self._agents.values())

    def get(self, agent_id: str, *, prompt_version: str | None = None) -> AgentDefinition:
        agent = self._agents[agent_id]
        if prompt_version is not None and prompt_version != agent.prompt_version:
            raise KeyError(f"Agent 提示词版本不存在：{agent_id}/{prompt_version}")
        return agent
