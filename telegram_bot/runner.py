"""Run orchestrator.py as async subprocess and track progress.

Parses phase-based output from the parallel orchestrator:
  === Phase N/10: Label ===     -> phase started
  --- Agents done: X/14 ---    -> agents completed count
  --- Running ROLE ---         -> single agent started
  --- Running parallel: A, B ---> parallel agents started
"""

import asyncio
import datetime
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Ensure telegram_bot package is importable
_pkg_dir = Path(__file__).parent
if str(_pkg_dir) not in sys.path:
    sys.path.insert(0, str(_pkg_dir))

from config import PROJECT_ROOT

ORCHESTRATOR = PROJECT_ROOT / "opencode_pipeline" / "orchestrator.py"
TOTAL_AGENTS = 14
TOTAL_PHASES = 10

# Phase labels matching orchestrator.py PHASE_LABELS
PHASE_LABELS = [
    "Analysts",
    "Smart Money",
    "Bull Research",
    "Bear Research",
    "Research Manager",
    "Trader",
    "Risk Aggressive",
    "Risk Conservative",
    "Risk Neutral",
    "Portfolio Manager",
]

# Phase emoji for animated progress
PHASE_EMOJI = [
    "📊", "💰", "🐂", "🐻", "🔬",
    "📈", "🔥", "🛡", "⚖️", "👔",
]

# Progress bar characters
_DONE = "▓"
_PENDING = "░"


def _progress_bar(done: int, total: int, width: int = 10) -> str:
    filled = int(width * done / total) if total else 0
    return _DONE * filled + _PENDING * (width - filled)


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
    """Manages a single background analysis run with phase-aware progress."""

    def __init__(self):
        self._process: asyncio.subprocess.Process | None = None
        self._running = False
        self._ticker: str = ""
        self._agents_done: int = 0
        self._current_phase: int = 0
        self._phase_label: str = ""
        self._start_time: float = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def progress_snapshot(self) -> dict:
        """Current progress for /status queries."""
        elapsed = time.time() - self._start_time if self._start_time else 0
        return {
            "ticker": self._ticker,
            "agents_done": self._agents_done,
            "total_agents": TOTAL_AGENTS,
            "phase": self._current_phase,
            "total_phases": TOTAL_PHASES,
            "phase_label": self._phase_label,
            "elapsed": elapsed,
        }

    def _build_progress_text(self) -> str:
        """Build a rich progress message for Telegram."""
        snap = self.progress_snapshot
        bar = _progress_bar(snap["agents_done"], snap["total_agents"])
        emoji = PHASE_EMOJI[snap["phase"] - 1] if 0 < snap["phase"] <= len(PHASE_EMOJI) else "⏳"

        elapsed_m = int(snap["elapsed"] // 60)
        elapsed_s = int(snap["elapsed"] % 60)

        # Build phase checklist
        lines = [
            f"🔄 *{snap['ticker']}* — анализ",
            "",
            f"{bar}  {snap['agents_done']}/{snap['total_agents']} агентов",
            "",
        ]

        for i, label in enumerate(PHASE_LABELS):
            phase_num = i + 1
            e = PHASE_EMOJI[i]
            if phase_num < snap["phase"]:
                lines.append(f"  ✅ {e} {label}")
            elif phase_num == snap["phase"]:
                lines.append(f"  ⏳ {e} *{label}*  ◀️")
            else:
                lines.append(f"  ⬜ {e} {label}")

        lines.extend([
            "",
            f"⏱ {elapsed_m}m {elapsed_s}s",
        ])
        return "\n".join(lines)

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
        self._ticker = ticker
        self._agents_done = 0
        self._current_phase = 0
        self._phase_label = ""
        self._start_time = time.time()
        _last_update = 0.0  # throttle edits to ~2s apart

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(PROJECT_ROOT),
                env={**os.environ},
            )
            self._process = process

            async for line in process.stdout:
                decoded = line.decode(errors="replace").strip()

                # Phase header: === Phase 1/10: Analysts ===
                phase_match = re.search(
                    r"=== Phase (\d+)/(\d+): (.+?) ===", decoded
                )
                if phase_match:
                    self._current_phase = int(phase_match.group(1))
                    self._phase_label = phase_match.group(3)

                # Agents done counter: --- Agents done: 6/14 ---
                done_match = re.search(
                    r"--- Agents done: (\d+)/(\d+) ---", decoded
                )
                if done_match:
                    self._agents_done = int(done_match.group(1))

                # Send progress update (throttled: max once per 2s)
                now = time.time()
                if progress_callback and (phase_match or done_match) and (now - _last_update) > 2.0:
                    _last_update = now
                    try:
                        await progress_callback(self._build_progress_text())
                    except Exception:
                        pass  # rate limit or message deleted

            await process.wait()
            elapsed = time.time() - self._start_time

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
                        agents_done=self._agents_done,
                        elapsed=elapsed,
                    )

            return RunResult(
                ticker=ticker,
                trade_date=trade_date,
                status="failed",
                final_decision="",
                run_dir="",
                agents_done=self._agents_done,
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
