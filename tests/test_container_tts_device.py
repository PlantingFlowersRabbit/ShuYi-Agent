from __future__ import annotations

import pytest


def _load_with_device(monkeypatch, device: str, *, cuda_available: bool):
    from backend.tts import qwen3_tts_server

    captured: dict[str, object] = {}

    class FakeTorch:
        float16 = "float16"
        float32 = "float32"
        bfloat16 = "bfloat16"

        class cuda:
            @staticmethod
            def is_available():
                return cuda_available

    class FakeModel:
        @staticmethod
        def from_pretrained(model_path: str, **kwargs):
            captured["model_path"] = model_path
            captured.update(kwargs)
            return object()

    monkeypatch.setattr(qwen3_tts_server, "torch", FakeTorch)
    monkeypatch.setattr(qwen3_tts_server, "Qwen3TTSModel", FakeModel)
    monkeypatch.setenv("QWEN3_TTS_DEVICE", device)

    qwen3_tts_server.load_model("/models/base")
    return captured


def test_container_tts_loader_resolves_auto_to_cuda(monkeypatch):
    captured = _load_with_device(monkeypatch, "auto", cuda_available=True)

    assert captured["device_map"] == "cuda:0"
    assert captured["dtype"] == "bfloat16"


def test_container_tts_loader_resolves_auto_to_cpu(monkeypatch):
    captured = _load_with_device(monkeypatch, "auto", cuda_available=False)

    assert captured["device_map"] == "cpu"
    assert captured["dtype"] == "float32"


def test_container_tts_loader_rejects_explicit_cuda_without_device(monkeypatch):
    with pytest.raises(RuntimeError, match="未检测到可用的 CUDA 设备"):
        _load_with_device(monkeypatch, "cuda", cuda_available=False)
