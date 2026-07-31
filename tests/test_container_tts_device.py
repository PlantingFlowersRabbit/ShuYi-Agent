from __future__ import annotations


def test_container_tts_loader_preserves_cuda_device(monkeypatch):
    from backend.tts import qwen3_tts_server

    captured: dict[str, object] = {}

    class FakeTorch:
        float16 = "float16"
        float32 = "float32"
        bfloat16 = "bfloat16"

    class FakeModel:
        @staticmethod
        def from_pretrained(model_path: str, **kwargs):
            captured["model_path"] = model_path
            captured.update(kwargs)
            return object()

    monkeypatch.setattr(qwen3_tts_server, "torch", FakeTorch)
    monkeypatch.setattr(qwen3_tts_server, "Qwen3TTSModel", FakeModel)
    monkeypatch.setenv("QWEN3_TTS_DEVICE", "cuda")

    qwen3_tts_server.load_model("/models/base")

    assert captured["device_map"] == "cuda"
    assert captured["dtype"] == "bfloat16"
