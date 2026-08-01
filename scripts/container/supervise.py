#!/usr/bin/env python3
"""在一个容器内监督 API 与仅回环监听的 TTS 服务。"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

DEFAULT_API_COMMAND = (
    "uvicorn",
    "backend.app.api.app:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000",
)


def tts_command() -> tuple[str, ...]:
    app_root = Path(__file__).resolve().parents[2]
    return (
        sys.executable,
        str(app_root / "backend/tts/qwen3_tts_server.py"),
        "--model-path",
        os.environ.get("QWEN3_TTS_MODEL_PATH", "/models/Qwen3-TTS-12Hz-1.7B-Base"),
        "--voice-design-model-path",
        os.environ.get(
            "QWEN3_TTS_VOICE_DESIGN_MODEL_PATH",
            "/models/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
        ),
        "--device",
        os.environ.get("QWEN3_TTS_DEVICE", "auto"),
        "--host",
        "127.0.0.1",
        "--port",
        "7811",
    )


class ProcessSupervisor:
    def __init__(
        self,
        processes: Mapping[str, subprocess.Popen],
        *,
        kill_process_group: Callable[[int, int], None] = os.killpg,
    ) -> None:
        self.processes = dict(processes)
        self.kill_process_group = kill_process_group
        self.requested_signal: int | None = None

    def _signal(self, process: subprocess.Popen, signum: int) -> None:
        if process.poll() is not None:
            return
        try:
            self.kill_process_group(process.pid, signum)
        except ProcessLookupError:
            pass

    def handle_signal(self, signum: int, _frame: object) -> None:
        if self.requested_signal is None:
            self.requested_signal = signum
        for process in self.processes.values():
            self._signal(process, signum)

    def _reap(self, process: subprocess.Popen, timeout: float) -> None:
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._signal(process, signal.SIGKILL)
            process.wait()

    def wait(self, *, poll_interval: float = 0.2, terminate_timeout: float = 15.0) -> int:
        while True:
            if self.requested_signal is not None:
                for process in self.processes.values():
                    self._reap(process, terminate_timeout)
                return 128 + self.requested_signal

            for name, process in self.processes.items():
                returncode = process.poll()
                if returncode is None:
                    continue
                for other_name, other in self.processes.items():
                    if other_name != name:
                        self._signal(other, signal.SIGTERM)
                        self._reap(other, terminate_timeout)
                return returncode
            time.sleep(poll_interval)


def _enabled(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def run(api_command: Sequence[str], tts_service_command: Sequence[str] | None = None) -> int:
    processes: dict[str, subprocess.Popen] = {}
    try:
        processes["api"] = subprocess.Popen(list(api_command), start_new_session=True)
        if tts_service_command is not None:
            processes["tts"] = subprocess.Popen(list(tts_service_command), start_new_session=True)
    except Exception:
        for process in processes.values():
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait()
        raise

    supervisor = ProcessSupervisor(processes)
    signal.signal(signal.SIGTERM, supervisor.handle_signal)
    signal.signal(signal.SIGINT, supervisor.handle_signal)
    return supervisor.wait()


def main() -> int:
    api_command = tuple(sys.argv[1:]) or DEFAULT_API_COMMAND
    tts_service_command = (
        tts_command()
        if _enabled(os.environ.get("SHUYI_START_TTS_ON_BOOT", "0"))
        else None
    )
    return run(api_command, tts_service_command)


if __name__ == "__main__":
    raise SystemExit(main())
