"""Scheduled watchlist analysis — run TradingAgents on a list of tickers.

Periodically scans a watchlist file and triggers analysis for each ticker
when certain conditions are met (e.g. market open, custom schedule).

Usage:
    # CLI
    tradingagents watchlist --config watchlist.json

    # Programmatic
    from tradingagents.watchlist import WatchlistRunner
    runner = WatchlistRunner("watchlist.json")
    runner.run_once()  # single pass
    runner.start()     # background scheduler
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

logger = logging.getLogger(__name__)

DEFAULT_WATCHLIST_PATH = Path.home() / ".tradingagents" / "watchlist.json"


@dataclass
class WatchlistEntry:
    ticker: str
    asset_type: str = "stock"
    enabled: bool = True
    last_analyzed: str | None = None
    interval_minutes: int = 360  # re-analyze every 6 hours by default
    tags: list[str] = field(default_factory=list)


class WatchlistRunner:
    """Manages and executes scheduled analysis for a watchlist."""

    def __init__(self, config_path: str | Path | None = None, config: dict | None = None):
        self.config_path = Path(config_path) if config_path else DEFAULT_WATCHLIST_PATH
        self.app_config = config or DEFAULT_CONFIG.copy()
        self._entries: list[WatchlistEntry] = []
        self._load()

    def _load(self):
        if not self.config_path.exists():
            self._entries = []
            return
        try:
            data = json.loads(self.config_path.read_text())
            self._entries = [WatchlistEntry(**e) for e in data.get("entries", [])]
        except Exception as e:
            logger.warning("Failed to load watchlist: %s", e)
            self._entries = []

    def _save(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"entries": [
            {
                "ticker": e.ticker,
                "asset_type": e.asset_type,
                "enabled": e.enabled,
                "last_analyzed": e.last_analyzed,
                "interval_minutes": e.interval_minutes,
                "tags": e.tags,
            }
            for e in self._entries
        ]}
        self.config_path.write_text(json.dumps(data, indent=2))

    def add_ticker(self, ticker: str, asset_type: str = "stock", interval_minutes: int = 360, tags: list[str] | None = None):
        entry = WatchlistEntry(
            ticker=ticker.upper(),
            asset_type=asset_type,
            interval_minutes=interval_minutes,
            tags=tags or [],
        )
        self._entries.append(entry)
        self._save()
        logger.info("Added %s to watchlist", ticker)

    def remove_ticker(self, ticker: str):
        self._entries = [e for e in self._entries if e.ticker != ticker.upper()]
        self._save()

    def list_entries(self) -> list[dict]:
        return [
            {
                "ticker": e.ticker,
                "asset_type": e.asset_type,
                "enabled": e.enabled,
                "last_analyzed": e.last_analyzed,
                "interval_minutes": e.interval_minutes,
                "tags": e.tags,
            }
            for e in self._entries
        ]

    def get_due_entries(self) -> list[WatchlistEntry]:
        """Return entries that are due for re-analysis."""
        now = datetime.now()
        due = []
        for e in self._entries:
            if not e.enabled:
                continue
            if e.last_analyzed is None:
                due.append(e)
                continue
            try:
                last = datetime.fromisoformat(e.last_analyzed)
                elapsed = (now - last).total_seconds() / 60
                if elapsed >= e.interval_minutes:
                    due.append(e)
            except ValueError:
                due.append(e)
        return due

    def run_once(self, ticker: str | None = None) -> list[dict]:
        """Run analysis for due tickers (or a specific one). Returns results."""
        if ticker:
            entries = [e for e in self._entries if e.ticker == ticker.upper()]
            if not entries:
                entries = [WatchlistEntry(ticker=ticker.upper())]
        else:
            entries = self.get_due_entries()

        if not entries:
            logger.info("No tickers due for analysis")
            return []

        results = []
        for entry in entries:
            logger.info("Analyzing %s...", entry.ticker)
            try:
                ta = TradingAgentsGraph(debug=False, config=self.app_config)
                _, decision = ta.propagate(entry.ticker, datetime.now().strftime("%Y-%m-%d"), asset_type=entry.asset_type)

                entry.last_analyzed = datetime.now().isoformat()
                self._save()

                results.append({"ticker": entry.ticker, "decision": decision, "status": "ok"})
                logger.info("Completed %s: %s", entry.ticker, decision)
            except Exception as e:
                results.append({"ticker": entry.ticker, "error": str(e), "status": "error"})
                logger.error("Failed %s: %s", entry.ticker, e)

        return results

    def start(self, check_interval: int = 300):
        """Start background scheduler (blocking). Checks every check_interval seconds."""
        logger.info("Watchlist scheduler started (check every %ds)", check_interval)
        try:
            while True:
                due = self.get_due_entries()
                if due:
                    logger.info("%d ticker(s) due for analysis", len(due))
                    self.run_once()
                time.sleep(check_interval)
        except KeyboardInterrupt:
            logger.info("Watchlist scheduler stopped")


def _format_watchlist_table(entries: list[dict]) -> str:
    if not entries:
        return "Watchlist is empty."
    lines = ["Ticker       | Asset    | Enabled | Interval | Last Analyzed", "-" * 65]
    for e in entries:
        last = e["last_analyzed"][:16] if e["last_analyzed"] else "never"
        lines.append(
            f"{e['ticker']:<13}| {e['asset_type']:<9}| {'yes' if e['enabled'] else 'no':<8} | "
            f"{e['interval_minutes']:>4} min | {last}"
        )
    return "\n".join(lines)
