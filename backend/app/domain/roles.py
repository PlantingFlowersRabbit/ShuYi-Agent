from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

SMOKE_TEST_NOTE = "功能烟测占位，不代表最终音色质量"
DEFAULT_REFERENCE_AUDIO = "assets/samples/voices/cmn_qixinxieli_canonni_cc0.wav"
DEFAULT_REFERENCE_TEXT = "齐心协力"


@dataclass(frozen=True)
class RoleCard:
    role_id: str
    name: str
    description: str
    voice_mode: str
    reference_audio_path: str | None
    reference_text: str | None
    design_prompt: str | None
    sample_note: str = SMOKE_TEST_NOTE

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
        description=data["description"],
        voice_mode=data["voice_mode"],
        reference_audio_path=data.get("reference_audio_path"),
        reference_text=data.get("reference_text"),
        design_prompt=data.get("design_prompt"),
        sample_note=data.get("sample_note", SMOKE_TEST_NOTE),
    )


def default_role_cards() -> list[RoleCard]:
    return [
        RoleCard(
            role_id="narrator",
            name="旁白",
            description="用于叙述性文本。",
            voice_mode="voice_cloning",
            reference_audio_path=DEFAULT_REFERENCE_AUDIO,
            reference_text=DEFAULT_REFERENCE_TEXT,
            design_prompt=None,
        ),
        RoleCard(
            role_id="male_lead",
            name="男主",
            description="功能烟测默认角色，不代表最终项目必须只有一个男主。",
            voice_mode="voice_cloning",
            reference_audio_path=DEFAULT_REFERENCE_AUDIO,
            reference_text=DEFAULT_REFERENCE_TEXT,
            design_prompt=None,
        ),
        RoleCard(
            role_id="female_lead",
            name="女主",
            description="功能烟测默认角色，不代表最终项目必须只有一个女主。",
            voice_mode="voice_cloning",
            reference_audio_path=DEFAULT_REFERENCE_AUDIO,
            reference_text=DEFAULT_REFERENCE_TEXT,
            design_prompt=None,
        ),
    ]


class RoleCollection:
    def __init__(self, roles: list[RoleCard | dict[str, Any]] | None = None):
        self._roles = {role.role_id: role for role in map(_role_from_mapping, roles or [])}

    def list(self) -> list[RoleCard]:
        return list(self._roles.values())

    def get(self, role_id: str) -> RoleCard:
        try:
            return self._roles[role_id]
        except KeyError as exc:
            raise KeyError(f"Unknown role_id: {role_id}") from exc

    def upsert(self, role: RoleCard | dict[str, Any]) -> RoleCard:
        card = _role_from_mapping(role)
        self._roles[card.role_id] = card
        return card

    def remove(self, role_id: str) -> None:
        if role_id in self._roles:
            del self._roles[role_id]

    def utterance_role_options(self) -> list[dict[str, str]]:
        return [{"value": role.role_id, "label": role.name} for role in self.list()]
