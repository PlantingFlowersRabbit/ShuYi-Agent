from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class VoiceResource:
    voice_id: str
    name: str
    description: str
    reference_text: str
    reference_audio_path: str
    generated: bool = False
    gender: str | None = None
    suitable_role_types: list[str] = field(default_factory=list)
    playable_audio_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data["playable_audio_path"] is None:
            data["playable_audio_path"] = self.reference_audio_path
        return data

    def with_updates(self, **updates: Any) -> VoiceResource:
        return replace(self, **updates)


def _slug(text: str) -> str:
    ascii_slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if ascii_slug:
        return ascii_slug
    return str(abs(hash(text)))[:8]


def _resource_from_mapping(data: VoiceResource | dict[str, Any]) -> VoiceResource:
    if isinstance(data, VoiceResource):
        return data
    return VoiceResource(
        voice_id=data.get("voice_id") or f"voice-{_slug(str(data['name']))}",
        name=data["name"],
        description=data.get("description", ""),
        reference_text=data.get("reference_text", ""),
        reference_audio_path=data.get("reference_audio_path", ""),
        generated=bool(data.get("generated", False)),
        gender=data.get("gender"),
        suitable_role_types=[str(item) for item in data.get("suitable_role_types") or []],
        playable_audio_path=data.get("playable_audio_path") or data.get("reference_audio_path", ""),
    )


def default_voice_resources(_sample_root: Any | None = None) -> list[VoiceResource]:
    return []


def generated_voice_content(name: str, description: str) -> str:
    cleaned_name = name.strip() or "新音色"
    cleaned_description = description.strip() or "自然、清晰、稳定"
    return f"{cleaned_name} 的试听语音。请用{cleaned_description}的方式读出这段内容，保持语气自然，节奏稳定。"


class VoiceResourceCollection:
    def __init__(self, resources: list[VoiceResource | dict[str, Any]] | None = None):
        self._resources = {
            resource.voice_id: resource for resource in map(_resource_from_mapping, resources or [])
        }

    def list(self) -> list[VoiceResource]:
        return list(self._resources.values())

    def get(self, voice_id: str) -> VoiceResource:
        try:
            return self._resources[voice_id]
        except KeyError as exc:
            raise KeyError(f"音色档案不存在：{voice_id}") from exc

    def upsert(self, resource: VoiceResource | dict[str, Any]) -> VoiceResource:
        item = _resource_from_mapping(resource)
        self._resources[item.voice_id] = item
        return item

    def remove(self, voice_id: str) -> None:
        if voice_id in self._resources:
            del self._resources[voice_id]

    def next_id(self) -> str:
        return f"voice-{len(self._resources) + 1:04d}"
