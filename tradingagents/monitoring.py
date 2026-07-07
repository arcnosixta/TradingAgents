"""Background monitor that watches live price against TP/SL levels.

When a trade proposal is saved, the monitor polls the current price and
alerts when it reaches take-profit or stop-loss.

Usage:
    from tradingagents.monitoring import TradeMonitor
    monitor = TradeMonitor()
    monitor.add_position(ticker="NVDA", entry=850, sl=820, tp=900, action="Buy")
    monitor.start()   # starts background thread
    ...
    monitor.stop()    # graceful shutdown
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable

import yfinance as yf

from tradingagents.dataflows.cache import market_cache
from tradingagents.dataflows.symbol_utils import normalize_symbol

logger = logging.getLogger(__name__)


@dataclass
class Position:
    ticker: str
    entry: float
    sl: float
    tp: float
    action: str  # "Buy" | "Sell"
    added_at: str = field(default_factory=lambda: datetime.now().isoformat())
    triggered: str | None = None  # "TP" | "SL" | None
    triggered_at: str | None = None
    triggered_price: float | None = None


class TradeMonitor:
    """Background thread that watches price levels and fires callbacks."""

    def __init__(
        self,
        poll_interval: int = 60,
        positions_file: str | Path | None = None,
        on_trigger: Callable[[Position, str, float], None] | None = None,
    ):
        """
        Args:
            poll_interval: Seconds between price checks.
            positions_file: Optional JSON file to persist positions.
            on_trigger: Callback fired with (position, trigger_type, price).
        """
        self.poll_interval = poll_interval
        self._positions: list[Position] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._positions_file = Path(positions_file) if positions_file else None
        self._on_trigger = on_trigger or self._default_trigger

        if self._positions_file and self._positions_file.exists():
            self._load_positions()

    def add_position(
        self,
        ticker: str,
        entry: float,
        sl: float,
        tp: float,
        action: str = "Buy",
    ):
        pos = Position(ticker=ticker, entry=entry, sl=sl, tp=tp, action=action)
        with self._lock:
            self._positions.append(pos)
        self._save_positions()
        logger.info("Monitoring %s: entry=%.2f sl=%.2f tp=%.2f", ticker, entry, sl, tp)

    def remove_position(self, ticker: str):
        with self._lock:
            self._positions = [p for p in self._positions if p.ticker != ticker]
        self._save_positions()

    def get_positions(self) -> list[dict]:
        with self._lock:
            return [asdict(p) for p in self._positions]

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="tp-sl-monitor")
        self._thread.start()
        logger.info("Trade monitor started (poll every %ds)", self.poll_interval)

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Trade monitor stopped")

    def _run(self):
        while not self._stop_event.is_set():
            self._check_prices()
            self._stop_event.wait(self.poll_interval)

    def _check_prices(self):
        with self._lock:
            active = [p for p in self._positions if p.triggered is None]

        if not active:
            return

        # Group by normalized ticker to avoid duplicate requests
        tickers = list({normalize_symbol(p.ticker) for p in active})
        prices: dict[str, float] = {}

        for sym in tickers:
            try:
                cache_key = {"namespace": "monitor_price", "ticker": sym}
                price = market_cache.get(**cache_key)
                if price is None:
                    price = yf.Ticker(sym).fast_info.get("lastPrice")
                    if price and price > 0:
                        market_cache.set("monitor_price", price, ttl=30, ticker=sym)
                if price and price > 0:
                    prices[sym] = price
            except Exception as e:
                logger.warning("Failed to fetch price for %s: %s", sym, e)

        triggered = []
        with self._lock:
            for pos in self._positions:
                if pos.triggered is not None:
                    continue
                sym = normalize_symbol(pos.ticker)
                price = prices.get(sym)
                if price is None:
                    continue

                hit = self._check_levels(pos, price)
                if hit:
                    pos.triggered = hit
                    pos.triggered_at = datetime.now().isoformat()
                    pos.triggered_price = price
                    triggered.append((pos, hit, price))

        for pos, hit_type, price in triggered:
            self._on_trigger(pos, hit_type, price)

        if triggered:
            self._save_positions()

    def _check_levels(self, pos: Position, price: float) -> str | None:
        if pos.action == "Buy":
            if price <= pos.sl:
                return "SL"
            if price >= pos.tp:
                return "TP"
        else:  # Sell
            if price >= pos.sl:
                return "SL"
            if price <= pos.tp:
                return "TP"
        return None

    def _default_trigger(self, pos: Position, hit_type: str, price: float):
        emoji = "🔴" if hit_type == "SL" else "🟢"
        msg = (
            f"\n{emoji} **{hit_type} HIT** — {pos.ticker}\n"
            f"   Entry: {pos.entry:.2f} | Triggered: {price:.2f} | "
            f"{'Stop Loss' if hit_type == 'SL' else 'Take Profit'}: "
            f"{pos.sl if hit_type == 'SL' else pos.tp:.2f}\n"
        )
        print(msg)
        logger.info("%s hit for %s at %.2f", hit_type, pos.ticker, price)

    def _save_positions(self):
        if not self._positions_file:
            return
        self._positions_file.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            data = [asdict(p) for p in self._positions]
        self._positions_file.write_text(json.dumps(data, indent=2))

    def _load_positions(self):
        try:
            data = json.loads(self._positions_file.read_text())
            self._positions = [Position(**d) for d in data]
        except Exception as e:
            logger.warning("Failed to load positions: %s", e)
            self._positions = []
