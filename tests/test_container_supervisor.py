from __future__ import annotations

import signal


class FakeProcess:
    def __init__(self, pid: int, returncode: int | None = None):
        self.pid = pid
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = -signal.SIGTERM
        return self.returncode


def test_supervisor_tts_command_is_loopback_only(monkeypatch):
    from scripts.container import supervise

    monkeypatch.setenv("QWEN3_TTS_MODEL_PATH", "/models/base")
    monkeypatch.setenv("QWEN3_TTS_VOICE_DESIGN_MODEL_PATH", "/models/design")
    monkeypatch.setenv("QWEN3_TTS_DEVICE", "auto")

    command = supervise.tts_command()

    assert command[0] == supervise.sys.executable
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert command[command.index("--port") + 1] == "7811"
    assert command[command.index("--device") + 1] == "auto"


def test_supervisor_stops_tts_when_api_exits():
    from scripts.container.supervise import ProcessSupervisor

    api = FakeProcess(101, returncode=7)
    tts = FakeProcess(202)
    signals: list[tuple[int, int]] = []
    supervisor = ProcessSupervisor(
        {"api": api, "tts": tts},
        kill_process_group=lambda pid, signum: signals.append((pid, signum)),
    )

    assert supervisor.wait(poll_interval=0, terminate_timeout=0) == 7
    assert signals == [(tts.pid, signal.SIGTERM)]


def test_supervisor_forwards_sigterm_to_both_process_groups():
    from scripts.container.supervise import ProcessSupervisor

    api = FakeProcess(101)
    tts = FakeProcess(202)
    signals: list[tuple[int, int]] = []
    supervisor = ProcessSupervisor(
        {"api": api, "tts": tts},
        kill_process_group=lambda pid, signum: signals.append((pid, signum)),
    )

    supervisor.handle_signal(signal.SIGTERM, None)

    assert signals == [(api.pid, signal.SIGTERM), (tts.pid, signal.SIGTERM)]
    assert supervisor.requested_signal == signal.SIGTERM
    assert supervisor.wait(poll_interval=0, terminate_timeout=0) == 128 + signal.SIGTERM
    assert api.returncode == -signal.SIGTERM
    assert tts.returncode == -signal.SIGTERM
