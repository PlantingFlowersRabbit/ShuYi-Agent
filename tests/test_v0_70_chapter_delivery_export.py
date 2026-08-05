from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient


def _role(role_id: str, name: str, voice_resource_id: str) -> dict:
    return {
        "role_id": role_id,
        "name": name,
        "description": f"{name} voice",
        "voice_mode": "voice_cloning",
        "voice_resource_id": voice_resource_id,
        "reference_audio_path": f"voices/{voice_resource_id}.wav",
        "reference_text": f"{name} 参考文本",
    }


def _utterance(
    utterance_id: str,
    paragraph_id: str,
    text: str,
    role_id: str,
    audio_path: Path | None,
) -> dict:
    payload = {
        "utterance_id": utterance_id,
        "paragraph_id": paragraph_id,
        "text": text,
        "speaker_role_id": role_id,
        "speaker_name": role_id,
        "voice_resource_id": f"voice-{role_id}",
        "audio_status": "success" if audio_path else "failed",
        "audio_duration": 0.6 if audio_path else 0.0,
        "audio_path": str(audio_path) if audio_path else "",
        "audio_error": "" if audio_path else "TTS 失败",
        "needs_human_review": False,
    }
    return payload


def test_v0_70_export_package_contains_manifest_scripts_subtitles_and_role_assets(tmp_path):
    """v0.7.2 delivery exports include complete production package metadata."""
    from backend.app.domain.audio import export_chapter_audio, write_silent_wav

    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    write_silent_wav(first, duration_seconds=0.6)
    write_silent_wav(second, duration_seconds=0.6)

    encoded_mp3: list[tuple[Path, Path]] = []

    def fake_mp3_encoder(source_wav: Path, target_mp3: Path) -> None:
        encoded_mp3.append((source_wav, target_mp3))
        target_mp3.write_bytes(b"fake mp3 bytes")

    report = export_chapter_audio(
        chapter_id="chapter-0001",
        chapter_title="第一章 雨夜",
        utterances_by_paragraph={
            "p-0001": [
                _utterance("p-0001-u-001", "p-0001", "第一句。", "narrator", first),
                _utterance("p-0001-u-002", "p-0001", "第二句。", "hero", second),
            ]
        },
        roles=[_role("narrator", "旁白", "voice-narrator"), _role("hero", "林舟", "voice-hero")],
        output_dir=tmp_path / "exports" / "project-a" / "chapter-0001",
        pause_ms=450,
        trim_silence=True,
        normalize_audio=True,
        export_formats=["wav", "mp3"],
        mp3_encoder=fake_mp3_encoder,
    )

    export_dir = Path(report.export_dir)
    manifest = json.loads(Path(report.manifest_path).read_text(encoding="utf-8"))

    assert report.missing_count == 0
    assert Path(report.full_audio_path or "").name == "chapter_full.wav"
    assert Path(report.full_mp3_path or "").name == "chapter_full.mp3"
    assert encoded_mp3 == [(export_dir / "chapter_full.wav", export_dir / "chapter_full.mp3")]
    assert manifest["package_version"] == "v0.7.2"
    assert manifest["project_artifact_type"] == "chapter_delivery_package"
    assert manifest["post_processing"] == {
        "pause_ms": 450,
        "speed": 1.0,
        "trim_silence": True,
        "normalize_audio": True,
        "target_peak": 0.9,
    }
    assert manifest["deliverables"]["full_audio_wav"] == "chapter_full.wav"
    assert manifest["deliverables"]["full_audio_mp3"] == "chapter_full.mp3"
    assert manifest["deliverables"]["script_csv"] == "script.csv"
    assert manifest["deliverables"]["subtitles_srt"] == "subtitles.srt"
    assert manifest["deliverables"]["subtitles_lrc"] == "subtitles.lrc"
    assert manifest["deliverables"]["roles_csv"] == "roles.csv"
    assert manifest["deliverables"]["voices_csv"] == "voices.csv"
    assert manifest["deliverables"]["failures_csv"] == "failures.csv"

    script_rows = list(csv.DictReader((export_dir / "script.csv").open(encoding="utf-8-sig")))
    assert [row["text"] for row in script_rows] == ["第一句。", "第二句。"]
    assert (export_dir / "subtitles.srt").read_text(encoding="utf-8").startswith(
        "1\n00:00:00,000 --> 00:00:00,600\n第一句。"
    )
    assert "[00:00.00]第一句。" in (export_dir / "subtitles.lrc").read_text(encoding="utf-8")
    assert list(csv.DictReader((export_dir / "roles.csv").open(encoding="utf-8-sig")))[1][
        "role_name"
    ] == "林舟"
    assert next(csv.DictReader((export_dir / "voices.csv").open(encoding="utf-8-sig")))[
        "voice_resource_id"
    ] == "voice-narrator"
    assert list(csv.DictReader((export_dir / "failures.csv").open(encoding="utf-8-sig"))) == []


def test_v0_70_project_export_api_isolates_package_path_by_project_id(monkeypatch, tmp_path):
    """Project export downloads are rooted under outputs/{project_id}/exports."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api.app import create_app
    from backend.app.domain.audio import write_silent_wav

    audio_path = tmp_path / "line.wav"
    write_silent_wav(audio_path, duration_seconds=0.6)

    with TestClient(create_app()) as client:
        project_id = client.post("/api/v1/projects", json={"name": "整章导出项目"}).json()[
            "project"
        ]["project_id"]
        exported = client.post(
            f"/api/v1/projects/{project_id}/exports/chapter-0001",
            json={
                "chapter_title": "第一章",
                "roles": [_role("narrator", "旁白", "voice-narrator")],
                "utterances_by_paragraph": {
                    "p-0001": [
                        _utterance("p-0001-u-001", "p-0001", "第一句。", "narrator", audio_path)
                    ]
                },
                "pause_ms": 300,
                "export_formats": ["wav"],
            },
        )
        assert exported.status_code == 200
        payload = exported.json()
        assert payload["download_url"].startswith(
            f"/api/v1/projects/{project_id}/downloads/exports/"
        )
        archive = client.get(payload["download_url"])

    assert archive.status_code == 200
    export_root = tmp_path / "outputs" / project_id / "exports"
    assert export_root.exists()
    with zipfile.ZipFile(export_root / Path(payload["download_url"]).name) as package:
        names = set(package.namelist())
    assert {"manifest.json", "script.csv", "subtitles.srt", "chapter_full.wav"}.issubset(names)


def test_v0_70_project_export_resolves_generated_relative_audio_paths(monkeypatch, tmp_path):
    """Project export accepts the generated audio paths returned to the frontend."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api import app as app_module
    from backend.app.domain.audio import write_silent_wav

    audio_dir = app_module.OUTPUT_AUDIO_DIR
    audio_dir.mkdir(parents=True, exist_ok=True)
    write_silent_wav(audio_dir / "vj-0001.wav", duration_seconds=0.6)

    with TestClient(app_module.create_app()) as client:
        project = client.post("/api/v1/projects", json={"name": "相对音频路径项目"}).json()[
            "project"
        ]
        project_id = project["project_id"]
        payload = {
            "chapter_title": "第一章",
            "roles": [_role("narrator", "旁白", "voice-narrator")],
            "utterances_by_paragraph": {
                "p-0001": [
                    _utterance(
                        "p-0001-u-001",
                        "p-0001",
                        "第一句。",
                        "narrator",
                        Path("outputs/audio/vj-0001.wav"),
                    )
                ]
            },
            "pause_ms": 300,
            "export_formats": ["wav"],
        }
        payload["utterances_by_paragraph"]["p-0001"][0]["audio_status"] = "succeeded"
        first = client.post(f"/api/v1/projects/{project_id}/exports/chapter-0001", json=payload)
        second = client.post(f"/api/v1/projects/{project_id}/exports/chapter-0001", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["missing_count"] == 0
    assert first.json()["item_count"] == 1
    assert first.json()["package_files"]["full_audio_wav"] == "chapter_full.wav"
    assert first.json()["download_url"] != second.json()["download_url"]

    export_root = Path(project["output_roots"]["exports"])
    with zipfile.ZipFile(export_root / Path(first.json()["download_url"]).name) as package:
        names = set(package.namelist())
    assert {"manifest.json", "script.csv", "chapter_full.wav"}.issubset(names)
