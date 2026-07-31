from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    display_name: str
    release_version: str
    prompt_id: str
    prompt_version: str


class AgentRegistry:
    def __init__(self, agents: list[AgentDefinition]):
        self._agents = {agent.agent_id: agent for agent in agents}

    @classmethod
    def default(cls) -> AgentRegistry:
        return cls(
            [
                AgentDefinition(
                    agent_id="novel_parser",
                    display_name="小说解析 Agent",
                    release_version="0.4.0",
                    prompt_id="novel_parser",
                    prompt_version="1",
                ),
                AgentDefinition(
                    agent_id="role_analyzer",
                    display_name="角色分析 Agent",
                    release_version="0.4.0",
                    prompt_id="role_analyzer",
                    prompt_version="1",
                ),
                AgentDefinition(
                    agent_id="dubbing_director",
                    display_name="配音编排 Agent",
                    release_version="0.4.0",
                    prompt_id="dubbing_director",
                    prompt_version="1",
                ),
            ]
        )

    def list_agents(self) -> list[AgentDefinition]:
        return list(self._agents.values())

    def get(self, agent_id: str, *, prompt_version: str | None = None) -> AgentDefinition:
        agent = self._agents[agent_id]
        if prompt_version is not None and prompt_version != agent.prompt_version:
            raise KeyError(f"unknown prompt version for {agent_id}: {prompt_version}")
        return agent
