"""Validate and fix Trader entry/stop levels against current price.

The LLM Trader agent sometimes proposes entry points too far from the current
price or stop-losses exceeding the 50-100 point maximum.  This module
deterministically validates and corrects those levels before the report is
saved.

Used by both the OpenCode pipeline (orchestrator.py) and the LangGraph
pipeline (trader.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ValidationResult:
    """Result of validating Trader entry/stop levels."""

    entry_price: float | None
    stop_loss: float | None
    take_profit: float | None
    is_valid: bool
    fixes: list[str]
    action: str  # Buy / Sell / Hold

    @property
    def summary(self) -> str:
        if self.is_valid:
            return "PASS"
        return "; ".join(self.fixes)


def parse_current_price_from_snapshot(snapshot_path: str | Path) -> dict | None:
    """Extract Close, High, Low from data/snapshot.md.

    Returns dict with keys: close, high, low.  Returns None if parsing fails.
    """
    path = Path(snapshot_path)
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8")
    result = {}

    # Match patterns like: | Close | 4187.30 | or **Close (2026-07-03)** | **4187.30** |
    for field in ["Close", "High", "Low"]:
        # Pattern: | Field | Value | or **Field** | **Value** |
        patterns = [
            rf"\|\s*\*?\*?{field}\s*(?:\([^)]*\))?\s*\*?\*?\s*\|\s*\*?\*?([\d,]+\.?\d*)\s*\*?\*?\s*\|",
            rf"{field}[:\s]+([\d,]+\.?\d*)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val_str = match.group(1).replace(",", "")
                try:
                    result[field.lower()] = float(val_str)
                    break
                except ValueError:
                    continue

    if "close" in result:
        # If High/Low missing, estimate from Close
        if "high" not in result:
            result["high"] = result["close"]
        if "low" not in result:
            result["low"] = result["close"]
        return result

    return None


def parse_current_price_from_text(text: str) -> float | None:
    """Extract current price from free-form text (e.g. market report).

    Looks for patterns like "price at 4187.30", "Close: 4187.30", etc.
    """
    patterns = [
        r"(?:Close|close|CLOSE)[:\s]+([\d,]+\.?\d*)",
        r"(?:price at|current price|Price)[:\s]+([\d,]+\.?\d*)",
        r"\*\*(?:Close|Price)\*\*[:\s]+([\d,]+\.?\d*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            val_str = match.group(1).replace(",", "")
            try:
                return float(val_str)
            except ValueError:
                continue
    return None


def parse_trader_proposal(text: str) -> dict:
    """Parse entry_price, stop_loss, take_profit, action from trader output."""
    result = {
        "entry_price": None,
        "stop_loss": None,
        "take_profit": None,
        "action": None,
    }

    # Action
    action_match = re.search(r"(?:ACTION|action)[:\s]+(Buy|Sell|Hold)", text, re.IGNORECASE)
    if action_match:
        result["action"] = action_match.group(1).capitalize()

    # Entry price — skip N/A
    entry_match = re.search(r"(?:ENTRY_PRICE|Entry Price|entry)[:\s]+([\d,]+\.?\d*)", text, re.IGNORECASE)
    if entry_match:
        val_str = entry_match.group(1).replace(",", "")
        try:
            result["entry_price"] = float(val_str)
        except ValueError:
            pass

    # Stop loss — skip N/A
    stop_match = re.search(r"(?:STOP_LOSS|Stop Loss|stop)[:\s]+([\d,]+\.?\d*)", text, re.IGNORECASE)
    if stop_match:
        val_str = stop_match.group(1).replace(",", "")
        try:
            result["stop_loss"] = float(val_str)
        except ValueError:
            pass

    # Take profit
    tp_match = re.search(r"(?:TAKE_PROFIT|Take Profit|take profit)[:\s]+([\d,]+\.?\d*)", text, re.IGNORECASE)
    if tp_match:
        val_str = tp_match.group(1).replace(",", "")
        try:
            result["take_profit"] = float(val_str)
        except ValueError:
            pass

    return result


def validate_entry_levels(
    entry_price: float | None,
    stop_loss: float | None,
    take_profit: float | None,
    current_price: float,
    action: str = "Buy",
    max_entry_offset: float = 30.0,
    max_stop_distance: float = 100.0,
    min_stop_distance: float = 20.0,
    atr: float | None = None,
) -> ValidationResult:
    """Validate and fix Trader entry/stop levels.

    Args:
        entry_price: Proposed entry price.
        stop_loss: Proposed stop loss.
        take_profit: Proposed take profit.
        current_price: Current market price (Close).
        action: Buy / Sell / Hold.
        max_entry_offset: Max allowed distance (points) from current price.
        max_stop_distance: Max allowed stop distance from entry.
        min_stop_distance: Min stop distance (too tight = noise stop).
        atr: Average True Range — if provided, stop bounds are ATR-dependent:
             min_stop = max(20, 0.5 * ATR), max_stop = min(100, 1.5 * ATR).

    Returns:
        ValidationResult with corrected levels and list of fixes.
    """
    fixes = []
    valid = True

    if action == "Hold" or (entry_price is None and stop_loss is None):
        return ValidationResult(
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            is_valid=True,
            fixes=[],
            action=action,
        )

    # --- Validate entry price ---
    if entry_price is not None:
        entry_offset = abs(entry_price - current_price)
        if entry_offset > max_entry_offset:
            fixes.append(
                f"ENTRY fixed: {entry_price} was {entry_offset:.0f} pts from "
                f"current ({current_price}), moved to {current_price:.2f}"
            )
            entry_price = round(current_price, 2)
            valid = False

    # --- Validate stop loss ---
    if stop_loss is not None and entry_price is not None:
        stop_distance = abs(stop_loss - entry_price)

        # ATR-dependent bounds
        effective_min = min_stop_distance
        effective_max = max_stop_distance
        if atr is not None and atr > 0:
            effective_min = max(min_stop_distance, round(0.5 * atr))
            effective_max = min(max_stop_distance, round(1.5 * atr))
            if effective_min > effective_max:
                effective_min, effective_max = effective_max, effective_min

        if stop_distance > effective_max:
            # Fix: clamp stop to max_distance from entry
            if action == "Buy":
                stop_loss = round(entry_price - effective_max, 2)
            else:
                stop_loss = round(entry_price + effective_max, 2)
            fixes.append(
                f"STOP fixed: was {stop_distance:.0f} pts from entry, "
                f"clamped to {effective_max:.0f} pts -> {stop_loss}"
            )
            valid = False

        elif stop_distance < effective_min:
            # Fix: stop too tight, widen to min_distance
            if action == "Buy":
                stop_loss = round(entry_price - effective_min, 2)
            else:
                stop_loss = round(entry_price + effective_min, 2)
            fixes.append(
                f"STOP fixed: was {stop_distance:.0f} pts (too tight), "
                f"widened to {effective_min:.0f} pts -> {stop_loss}"
            )
            valid = False

    # --- Validate take profit ---
    if take_profit is not None and entry_price is not None and stop_loss is not None:
        tp_distance = abs(take_profit - entry_price)
        stop_distance = abs(stop_loss - entry_price)
        if stop_distance > 0:
            rr_ratio = tp_distance / stop_distance
            if rr_ratio < 1.0:
                # Take profit is closer than stop — bad R:R
                fixes.append(
                    f"TP warning: R:R ratio is {rr_ratio:.1f}:1 (< 1:1), "
                    f"consider widening TP"
                )
                # Don't auto-fix TP, just warn

    return ValidationResult(
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        is_valid=valid,
        fixes=fixes,
        action=action or "Unknown",
    )


def validate_consistency(
    trader_entry: float | None,
    pm_entry: float | None,
    max_diff: float = 20.0,
) -> tuple[float | None, list[str]]:
    """Check consistency between Trader and Portfolio Manager entry prices.

    If the difference exceeds *max_diff* points the PM entry is pulled toward
    the Trader entry (Trader is closer to the market).

    Returns:
        (corrected_pm_entry, list_of_warnings)
    """
    if trader_entry is None or pm_entry is None:
        return pm_entry, []

    diff = abs(pm_entry - trader_entry)
    if diff <= max_diff:
        return pm_entry, []

    # Pull PM toward Trader
    warnings = [
        f"CONSISTENCY: PM entry {pm_entry} was {diff:.0f} pts from Trader "
        f"entry {trader_entry} (max {max_diff:.0f}), corrected to {trader_entry}"
    ]
    return round(trader_entry, 2), warnings


def calculate_lot_size(
    entry_price: float,
    stop_loss: float,
    account_balance: float = 10000.0,
    risk_pct: float = 0.01,
    pip_value: float = 1.0,
) -> float:
    """Calculate lot size based on risk percentage and stop distance.

    Args:
        entry_price: Entry price.
        stop_loss: Stop loss price.
        account_balance: Total account balance (default $10,000).
        risk_pct: Risk per trade as fraction (default 1%).
        pip_value: Value per pip/point (default $1 for gold).

    Returns:
        Lot size rounded to 2 decimals, clamped to [0.01, 1.0].
    """
    risk_amount = account_balance * risk_pct
    stop_distance = abs(entry_price - stop_loss)
    if stop_distance <= 0:
        return 0.01
    lot_size = risk_amount / (stop_distance * pip_value)
    return round(max(0.01, min(lot_size, 1.0)), 2)


def parse_atr_from_indicators(indicators_path: str | Path) -> float | None:
    """Parse ATR value from data/indicators.md.

    Looks for patterns like "ATR (14): 93.21" or "ATR: 93.21".
    Returns ATR value or None if not found.
    """
    path = Path(indicators_path)
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8")

    patterns = [
        r"ATR\s*\((?:\d+)\)[:\s]+([\d,]+\.?\d*)",
        r"ATR[:\s]+([\d,]+\.?\d*)",
        r"\*\*ATR\*\*[:\s]+([\d,]+\.?\d*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val_str = match.group(1).replace(",", "")
            try:
                return float(val_str)
            except ValueError:
                continue
    return None


def apply_validation_to_report(
    report_path: str | Path,
    current_price: float,
    atr: float | None = None,
) -> ValidationResult | None:
    """Read a trader_proposal.md, validate, and rewrite if corrected.

    Args:
        report_path: Path to the report markdown file.
        current_price: Current market price.
        atr: Average True Range for ATR-dependent stop validation.

    Returns:
        ValidationResult or None if file can't be parsed.
    """
    path = Path(report_path)
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8")
    parsed = parse_trader_proposal(text)

    if parsed["action"] is None:
        return None

    result = validate_entry_levels(
        entry_price=parsed["entry_price"],
        stop_loss=parsed["stop_loss"],
        take_profit=parsed["take_profit"],
        current_price=current_price,
        action=parsed["action"],
        atr=atr,
    )

    if not result.is_valid:
        # Rewrite the file with corrected values
        corrected = text
        if result.entry_price is not None and parsed["entry_price"] != result.entry_price:
            corrected = re.sub(
                r"(ENTRY_PRICE[:\s]+)[\d,]+\.?\d*",
                f"\\g<1>{result.entry_price}",
                corrected,
                flags=re.IGNORECASE,
            )
        if result.stop_loss is not None and parsed["stop_loss"] != result.stop_loss:
            corrected = re.sub(
                r"(STOP_LOSS[:\s]+)[\d,]+\.?\d*",
                f"\\g<1>{result.stop_loss}",
                corrected,
                flags=re.IGNORECASE,
            )
        path.write_text(corrected, encoding="utf-8")

    return result
