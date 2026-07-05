"""Scan runs/ directory and extract structured data for the dashboard."""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


REPORT_NAMES = {
    "market": "Market Analysis",
    "sentiment": "Sentiment Analysis",
    "news": "News Analysis",
    "fundamentals": "Fundamentals Analysis",
    "bear_case": "Bear Researcher",
    "research_plan": "Research Manager",
    "trader_proposal": "Trader Proposal",
    "risk_aggressive": "Aggressive Risk",
    "risk_conservative": "Conservative Risk",
    "risk_neutral": "Neutral Risk",
    "final_decision": "Final Decision",
}

REPORT_ORDER = [
    "market",
    "sentiment",
    "news",
    "fundamentals",
    "bear_case",
    "research_plan",
    "trader_proposal",
    "risk_aggressive",
    "risk_conservative",
    "risk_neutral",
    "final_decision",
]

ALL_AGENTS = [
    "market",
    "sentiment",
    "news",
    "fundamentals",
    "bull_researcher",
    "bear_researcher",
    "research_manager",
    "trader",
    "risk_aggressive",
    "risk_conservative",
    "risk_neutral",
    "portfolio_manager",
]


@dataclass
class RunInfo:
    run_id: str
    ticker: str
    date: str
    timestamp: str
    path: str
    status: str = "unknown"
    agents_completed: int = 0
    agents_total: int = 12
    elapsed_seconds: float = 0.0
    reports: dict = field(default_factory=dict)
    final_decision: str = ""
    rating: str = ""

    @property
    def progress(self) -> int:
        if self.agents_total == 0:
            return 0
        return round(self.agents_completed / self.agents_total * 100)

    @property
    def elapsed_display(self) -> str:
        m = int(self.elapsed_seconds // 60)
        s = int(self.elapsed_seconds % 60)
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"


def parse_run_id(run_id: str) -> tuple[str, str, str]:
    """Parse 'TICKER_DATE_TIMESTAMP' into (ticker, date, timestamp)."""
    parts = run_id.rsplit("_", 2)
    if len(parts) >= 3:
        timestamp = parts[-1]
        date = parts[-2]
        ticker = "_".join(parts[:-2])
        return ticker, date, timestamp
    return run_id, "", ""


def scan_runs(runs_dir: str) -> list[RunInfo]:
    """Scan runs/ directory and return sorted list of RunInfo."""
    runs_path = Path(runs_dir)
    if not runs_path.exists():
        return []

    runs = []
    for entry in sorted(runs_path.iterdir(), reverse=True):
        if not entry.is_dir():
            continue

        run_id = entry.name
        ticker, date, timestamp = parse_run_id(run_id)
        run = RunInfo(
            run_id=run_id,
            ticker=ticker,
            date=date,
            timestamp=timestamp,
            path=str(entry),
        )

        # Parse run_log.json
        log_path = entry / "run_log.json"
        if log_path.exists():
            try:
                with open(log_path) as f:
                    log_data = json.load(f)
                run.agents_completed = sum(
                    1 for v in log_data.values() if v.get("status") == "success"
                )
                run.elapsed_seconds = sum(
                    v.get("elapsed_seconds", 0) for v in log_data.values()
                )
                if run.agents_completed == run.agents_total:
                    run.status = "completed"
                elif run.agents_completed > 0:
                    run.status = "partial"
                else:
                    run.status = "failed"
            except (json.JSONDecodeError, KeyError):
                run.status = "error"

        # Check for running state (prompt files exist but no run_log.json completion)
        if run.status == "unknown":
            prompt_files = list(entry.glob("*_prompt.md"))
            if prompt_files:
                run.status = "running"
                run.agents_completed = 0
                # Count completed reports as proxy
                reports_dir = entry / "reports"
                if reports_dir.exists():
                    report_files = list(reports_dir.glob("*.md"))
                    run.agents_completed = min(len(report_files), run.agents_total)

        # Read reports
        reports_dir = entry / "reports"
        if reports_dir.exists():
            for report_file in reports_dir.glob("*.md"):
                stem = report_file.stem
                if stem in REPORT_NAMES:
                    try:
                        content = report_file.read_text(encoding="utf-8")
                        run.reports[stem] = content
                    except Exception:
                        run.reports[stem] = "(failed to read)"

        # Extract rating from final_decision
        if "final_decision" in run.reports:
            first_line = run.reports["final_decision"].split("\n")[0].strip()
            if first_line.upper().startswith("RATING:"):
                run.rating = first_line.split(":", 1)[1].strip()

        runs.append(run)

    return runs


def get_run(runs_dir: str, run_id: str) -> RunInfo | None:
    """Get a single run by ID."""
    runs = scan_runs(runs_dir)
    for run in runs:
        if run.run_id == run_id:
            return run
    return None
