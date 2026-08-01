from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class RoleCard:
    role_id: str
    name: str
    description: str
    voice_mode: str
    reference_audio_path: str | None
    reference_text: str | None
    design_prompt: str | None
    voice_resource_id: str | None = None
    aliases: list[str] = field(default_factory=list)
    gender: str | None = None
    profile: str | None = None
    voice_description: str | None = None
    voice_sample_text: str | None = None
    playable_voice_path: str | None = None
    voice_match_score: float | None = None
    voice_match_reason: str | None = None
    voice_generated_by_ai: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_updates(self, **updates: Any) -> RoleCard:
        return replace(self, **updates)


def _role_from_mapping(data: RoleCard | dict[str, Any]) -> RoleCard:
    if isinstance(data, RoleCard):
        return data
    return RoleCard(
        role_id=data["role_id"],
        name=data["name"],
        description=data.get("description", ""),
        voice_mode=data.get("voice_mode", "voice_cloning"),
        reference_audio_path=data.get("reference_audio_path"),
        reference_text=data.get("reference_text"),
        design_prompt=data.get("design_prompt"),
        voice_resource_id=data.get("voice_resource_id"),
        aliases=[str(alias) for alias in data.get("aliases") or []],
        gender=data.get("gender"),
        profile=data.get("profile"),
        voice_description=data.get("voice_description"),
        voice_sample_text=data.get("voice_sample_text"),
        playable_voice_path=data.get("playable_voice_path"),
        voice_match_score=data.get("voice_match_score"),
        voice_match_reason=data.get("voice_match_reason"),
        voice_generated_by_ai=bool(data.get("voice_generated_by_ai", False)),
    )


@dataclass(frozen=True)
class RoleDeleteResult:
    role_id: str
    deleted: bool
    referenced_count: int
    action: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_role_cards() -> list[RoleCard]:
    return []


class RoleCollection:
    def __init__(self, roles: list[RoleCard | dict[str, Any]] | None = None):
        self._roles = {role.role_id: role for role in map(_role_from_mapping, roles or [])}

    def list(self) -> list[RoleCard]:
        return list(self._roles.values())

    def get(self, role_id: str) -> RoleCard:
        try:
            return self._roles[role_id]
        except KeyError as exc:
            raise KeyError(f"角色不存在：{role_id}") from exc

    def upsert(self, role: RoleCard | dict[str, Any]) -> RoleCard:
        card = _role_from_mapping(role)
        self._roles[card.role_id] = card
        return card

    def remove(self, role_id: str) -> None:
        if role_id in self._roles:
            del self._roles[role_id]

    def delete_with_policy(
        self,
        role_id: str,
        utterances_by_paragraph: dict[str, list[dict[str, Any]]],
        *,
        action: str = "block",
        target_role_id: str | None = None,
    ) -> RoleDeleteResult:
        references = _role_references(role_id, utterances_by_paragraph)
        if not references:
            self.remove(role_id)
            return RoleDeleteResult(role_id, True, 0, "delete", "角色未被语句引用，已删除。")

        if action == "unbind":
            for utterance in references:
                utterance["speaker_role_id"] = None
                if utterance.get("role_id") == role_id:
                    utterance["role_id"] = None
                utterance["speaker_name"] = ""
                utterance["needs_human_review"] = True
            self.remove(role_id)
            return RoleDeleteResult(
                role_id,
                True,
                len(references),
                "unbind",
                f"已解除 {len(references)} 条语句的角色绑定并删除角色。",
            )

        if action == "migrate":
            if not target_role_id or target_role_id not in self._roles:
                return RoleDeleteResult(
                    role_id,
                    False,
                    len(references),
                    "migrate",
                    "迁移删除需要提供有效的 target_role_id。",
                )
            target = self._roles[target_role_id]
            for utterance in references:
                utterance["speaker_role_id"] = target_role_id
                if utterance.get("role_id") == role_id:
                    utterance["role_id"] = target_role_id
                utterance["speaker_name"] = target.name
            self.remove(role_id)
            return RoleDeleteResult(
                role_id,
                True,
                len(references),
                "migrate",
                f"已将 {len(references)} 条语句迁移到 {target.name} 并删除角色。",
            )

        return RoleDeleteResult(
            role_id,
            False,
            len(references),
            "block",
            f"角色正在被 {len(references)} 条语句引用；请选择取消、解除绑定或迁移到其他角色。",
        )

    def utterance_role_options(self) -> list[dict[str, str]]:
        return [{"value": role.role_id, "label": role.name} for role in self.list()]


def _role_references(
    role_id: str,
    utterances_by_paragraph: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for utterances in utterances_by_paragraph.values():
        for utterance in utterances:
            if utterance.get("speaker_role_id") == role_id or utterance.get("role_id") == role_id:
                references.append(utterance)
    return references
