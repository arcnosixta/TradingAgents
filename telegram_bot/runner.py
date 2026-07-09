"""Run orchestrator.py as async subprocess and track progress."""

import asyncio
import datetime
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Ensure telegram_bot package is importable
_pkg_dir = Path(__file__).parent
if str(_pkg_dir) not in sys.path:
    sys.path.insert(0, str(_pkg_dir))

from config import PROJECT_ROOT

ORCHESTRATOR = PROJECT_ROOT / "opencode_pipeline" / "orchestrator.py"
TOTAL_AGENTS = 14


@dataclass
class RunResult:
    ticker: str
    trade_date: str
    status: str  # completed | failed
    final_decision: str
    run_dir: str
    agents_done: int
    elapsed: float


class RunManager:
    """Manages a single background analysis run."""

    def __init__(self):
        self._process: asyncio.subprocess.Process | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(
        self,
        ticker: str,
        trade_date: str | None = None,
        progress_callback=None,
    ) -> RunResult:
        """Run orchestrator and return parsed result.

        Args:
            ticker: Instrument ticker (e.g. XAU-USD, BTC-USD, AAPL).
            trade_date: Trade date YYYY-MM-DD. Defaults to today.
            progress_callback: async callable(progress_msg: str) for updates.

        Returns:
            RunResult with final_decision text and metadata.
        """
        if trade_date is None:
            trade_date = datetime.datetime.now().strftime("%Y-%m-%d")

        cmd = ["python", str(ORCHESTRATOR), ticker, "--trade_date", trade_date]

        self._running = True
        start_time = time.time()

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(PROJECT_ROOT),
                env={**os.environ},
            )
            self._process = process

            agents_done = 0

            async for line in process.stdout:
                decoded = line.decode(errors="replace").strip()
                if "--- Running" in decoded:
                    agents_done += 1
                    # Throttle progress updates: every 2 agents
                    if progress_callback and agents_done % 2 == 0:
                        try:
                            await progress_callback(
                                f"⏳ *{ticker}* | Агент {agents_done}/{TOTAL_AGENTS}..."
                            )
                        except Exception:
                            pass  # rate limit or message deleted

            await process.wait()
            elapsed = time.time() - start_time

            # Find the latest run directory for this ticker+date
            runs_dir = PROJECT_ROOT / "runs"
            pattern = f"{ticker}_{trade_date}_*"
            run_dirs = sorted(runs_dir.glob(pattern), reverse=True) if runs_dir.exists() else []

            if run_dirs and process.returncode == 0:
                run_dir = run_dirs[0]
                decision_path = run_dir / "reports" / "final_decision.md"
                if decision_path.exists():
                    final_decision = decision_path.read_text(encoding="utf-8")
                    return RunResult(
                        ticker=ticker,
                        trade_date=trade_date,
                        status="completed",
                        final_decision=final_decision,
                        run_dir=str(run_dir),
                        agents_done=agents_done,
                        elapsed=elapsed,
                    )

            return RunResult(
                ticker=ticker,
                trade_date=trade_date,
                status="failed",
                final_decision="",
                run_dir="",
                agents_done=agents_done,
                elapsed=elapsed,
            )

        except Exception as e:
            return RunResult(
                ticker=ticker,
                trade_date=trade_date or "",
                status="failed",
                final_decision=f"Error: {e}",
                run_dir="",
                agents_done=0,
                elapsed=0,
            )
        finally:
            self._running = False
            self._process = None

    def cancel(self):
        """Cancel the running process."""
        if self._process and self._process.returncode is None:
            self._process.terminate()
        self._running = False
