"""Run orchestrator.py as subprocess and track progress."""

import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RunState:
    run_id: str = ""
    ticker: str = ""
    date: str = ""
    status: str = "idle"  # idle | running | completed | failed
    pid: int = 0
    start_time: float = 0.0
    agents_done: int = 0
    agents_total: int = 12
    error: str = ""
    run_dir: str = ""

    @property
    def elapsed(self) -> float:
        if self.start_time == 0:
            return 0
        if self.status == "running":
            return time.time() - self.start_time
        return 0


class RunManager:
    """Manages background analysis runs."""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.current: RunState | None = None
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self, ticker: str, trade_date: str) -> RunState:
        """Start a new analysis run."""
        with self._lock:
            if self.current and self.current.status == "running":
                raise RuntimeError("An analysis is already running")

            state = RunState(
                ticker=ticker,
                date=trade_date,
                status="running",
                start_time=time.time(),
            )
            self.current = state

            self._thread = threading.Thread(
                target=self._run_orchestrator,
                args=(state, ticker, trade_date),
                daemon=True,
            )
            self._thread.start()
            return state

    def get_status(self) -> RunState | None:
        """Get current run status."""
        with self._lock:
            return self.current

    def _run_orchestrator(self, state: RunState, ticker: str, trade_date: str):
        """Run orchestrator.py in background thread."""
        orchestrator = self.project_root / "opencode_pipeline" / "orchestrator.py"

        cmd = [
            "python",
            str(orchestrator),
            ticker,
            "--trade_date",
            trade_date,
        ]

        try:
            self._process = subprocess.Popen(
                cmd,
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env={**__import__("os").environ},
            )
            state.pid = self._process.pid

            # Parse output to track progress
            for line in self._process.stdout:
                line = line.strip()
                if "--- Running" in line:
                    state.agents_done += 1

            self._process.wait()

            if self._process.returncode == 0:
                state.status = "completed"
                state.agents_done = state.agents_total
            else:
                state.status = "failed"
                state.error = f"Exit code {self._process.returncode}"

        except Exception as e:
            state.status = "failed"
            state.error = str(e)
        finally:
            self._process = None
