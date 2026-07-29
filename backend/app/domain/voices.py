from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
BUILTIN_REFERENCE_AUDIO = "assets/samples/voices/cmn_qixinxieli_canonni_cc0.wav"
BUILTIN_REFERENCE_TEXT = "齐心协力"


@dataclass(frozen=True)
class VoiceResource:
    voice_id: str
    name: str
    description: str
    reference_text: str
    reference_audio_path: str
    generated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_updates(self, **updates: Any) -> "VoiceResource":
        return replace(self, **updates)


def _slug(text: str) -> str:
    ascii_slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if ascii_slug:
        return ascii_slug
    return str(abs(hash(text)))[:8]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


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
    )


def default_voice_resources(sample_root: Path | None = None) -> list[VoiceResource]:
    resources: list[VoiceResource] = []
    if sample_root and sample_root.exists():
        known_ids = {
            "男声旁白": "voice-male-narrator",
            "年轻男": "voice-young-male",
            "御姐音": "voice-yujie",
            "播音腔女": "voice-broadcast-female",
        }
        descriptions = {
            "男声旁白": "沉稳、叙事感强，适合旁白和长段说明。",
            "年轻男": "清亮自然，适合年轻男性角色对白。",
            "御姐音": "成熟亲近，适合女性角色对白。",
            "播音腔女": "端正清晰，适合公告、说明和新闻感旁白。",
        }
        for folder in sorted(path for path in sample_root.iterdir() if path.is_dir()):
            audio_path = folder / f"{folder.name}.mp3"
            transcript_path = folder / "语音内容.txt"
            if not audio_path.exists() or not transcript_path.exists():
                continue
            resources.append(
                VoiceResource(
                    voice_id=known_ids.get(folder.name, f"voice-{_slug(folder.name)}"),
                    name=folder.name,
                    description=descriptions.get(folder.name, f"{folder.name} 本地参考音色。"),
                    reference_text=_read_text(transcript_path),
                    reference_audio_path=str(audio_path),
                    generated=False,
                )
            )
    if resources:
        return resources

    return [
        VoiceResource(
            voice_id="voice-male-narrator",
            name="男声旁白",
            description="默认旁白音色资源；可在资源库替换为真实项目素材。",
            reference_text=BUILTIN_REFERENCE_TEXT,
            reference_audio_path=BUILTIN_REFERENCE_AUDIO,
            generated=False,
        ),
        VoiceResource(
            voice_id="voice-young-male",
            name="年轻男",
            description="默认年轻男性音色资源；可在资源库替换为真实项目素材。",
            reference_text=BUILTIN_REFERENCE_TEXT,
            reference_audio_path=BUILTIN_REFERENCE_AUDIO,
            generated=False,
        ),
        VoiceResource(
            voice_id="voice-yujie",
            name="御姐音",
            description="默认成熟女性音色资源；可在资源库替换为真实项目素材。",
            reference_text=BUILTIN_REFERENCE_TEXT,
            reference_audio_path=BUILTIN_REFERENCE_AUDIO,
            generated=False,
        ),
    ]


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
            raise KeyError(f"Unknown voice_id: {voice_id}") from exc

    def upsert(self, resource: VoiceResource | dict[str, Any]) -> VoiceResource:
        item = _resource_from_mapping(resource)
        self._resources[item.voice_id] = item
        return item

    def remove(self, voice_id: str) -> None:
        if voice_id in self._resources:
            del self._resources[voice_id]

    def next_id(self) -> str:
        return f"voice-{len(self._resources) + 1:04d}"
