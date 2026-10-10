"""A private Linux display for pytest, including its child processes."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from typing import IO

DISPLAY_ENV = "HOI4CM_TEST_DISPLAY"


class TestDisplay:
    """Own one Xvfb server; never connect tests to the caller's desktop."""

    __test__ = False

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.output: IO[bytes] | None = None
        self.errors: IO[bytes] | None = None
        self.previous: dict[str, str | None] = {}

    def start(self, timeout: float = 10) -> None:
        executable = shutil.which("Xvfb")
        if executable is None:
            raise RuntimeError(
                "Quiet Tk tests need Xvfb on Linux. Install xvfb (and xauth for "
                "xvfb-run), or explicitly allow desktop windows with HOI4CM_SHOW_TK=1."
            )
        self.output = tempfile.TemporaryFile()
        self.errors = tempfile.TemporaryFile()
        try:
            # Xvfb chooses a free display atomically. No fixed :99, shell, or TCP.
            self.process = subprocess.Popen(
                [
                    executable,
                    "-displayfd",
                    "1",
                    "-screen",
                    "0",
                    "1280x1024x24",
                    "-nolisten",
                    "tcp",
                ],
                stdout=self.output,
                stderr=self.errors,
            )
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                # pread does not move the child's shared file position.
                ready = os.pread(self.output.fileno(), 64, 0).strip()
                if ready.isdigit():
                    display = ":" + ready.decode("ascii")
                    self.previous = {
                        name: os.environ.get(name) for name in ("DISPLAY", DISPLAY_ENV)
                    }
                    os.environ["DISPLAY"] = display
                    os.environ[DISPLAY_ENV] = display
                    return
                if self.process.poll() is not None:
                    self.errors.seek(0)
                    error = self.errors.read()
                    raise RuntimeError(f"Xvfb failed: {error.decode(errors='replace')}")
                time.sleep(0.01)
            raise RuntimeError("Xvfb did not become ready within the startup timeout")
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        """Restore the environment and reap the server, even after startup failure."""
        for name, value in self.previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self.previous.clear()
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            self.process = None
        if self.output is not None:
            self.output.close()
            self.output = None
        if self.errors is not None:
            self.errors.close()
            self.errors = None
