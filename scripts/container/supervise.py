#!/usr/bin/env python3
"""Run the container service and forward termination signals to its process group."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from collections.abc import Sequence

DEFAULT_COMMAND = (
    "uvicorn",
    "backend.app.api.app:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000",
)


def run(command: Sequence[str]) -> int:
    child = subprocess.Popen(list(command), start_new_session=True)

    def forward(signum: int, _frame: object) -> None:
        if child.poll() is None:
            os.killpg(child.pid, signum)

    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGINT, forward)
    try:
        return child.wait()
    except KeyboardInterrupt:
        forward(signal.SIGINT, None)
        return child.wait()


def main() -> int:
    command = tuple(sys.argv[1:]) or DEFAULT_COMMAND
    return run(command)


if __name__ == "__main__":
    raise SystemExit(main())
