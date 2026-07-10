"""Parse final_decision.md and format as Telegram message.

Enhanced formatting with:
- Risk/Reward ratio calculation
- Visual separators
- Compact summary for button-driven UI
"""

import re
import sys
from pathlib import Path

# Add telegram_bot package to path for config/runner imports
_pkg_dir = Path(__file__).parent
if str(_pkg_dir) not in sys.path:
    sys.path.insert(0, str(_pkg_dir))

# Add project root so we can import entry_validator
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from runner import RunResult

# Lazy import to avoid circular at module level
_parse_trader_proposal = None


def _get_parser():
    global _parse_trader_proposal
    if _parse_trader_proposal is None:
        from tradingagents.agents.utils.entry_validator import parse_trader_proposal
        _parse_trader_proposal = parse_trader_proposal
    return _parse_trader_proposal


def _extract_section(text: str, header: str) -> str:
    """Extract a section from markdown by header text."""
    pattern = rf"{header}[:\s]*\n(.+?)(?=\n\n|\n##|\n\*\*|\Z)"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _calc_rr(entry, sl, tp) -> str:
    """Calculate Risk:Reward ratio."""
    if not all(isinstance(v, (int, float)) and v > 0 for v in (entry, sl, tp)):
        return "N/A"
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    if risk == 0:
        return "N/A"
    ratio = reward / risk
    return f"1:{ratio:.1f}"


def format_decision(result: RunResult) -> str:
    """Format RunResult as a readable Telegram message with rich layout."""
    if result.status == "failed":
        return (
            f"❌ Анализ *{result.ticker}* не удался.\n\n"
            f"{result.final_decision[:500]}"
        )

    text = result.final_decision

    # Parse rating
    rating_match = re.search(r"RATING:\s*(\w+)", text)
    rating = rating_match.group(1) if rating_match else "N/A"

    # Parse trade data
    parse = _get_parser()
    parsed = parse(text)
    action = parsed.get("action") or "N/A"
    entry = parsed.get("entry_price")
    sl = parsed.get("stop_loss")
    tp = parsed.get("take_profit")

    # If TP is missing or looks wrong, try to parse Take Profit 1 specifically
    if tp is None or tp == 1.0:
        tp_match = re.search(
            r"(?:TAKE_PROFIT_1|Take Profit 1)[:\s]+([\d,]+\.?\d*)",
            text, re.IGNORECASE,
        )
        if tp_match:
            try:
                tp = float(tp_match.group(1).replace(",", ""))
            except ValueError:
                pass

    # Executive summary
    summary = _extract_section(text, "EXECUTIVE_SUMMARY")
    if not summary:
        summary = _extract_section(text, "Executive Summary")
    if summary:
        summary = summary[:300]

    # Confidence / Conviction
    conf_match = re.search(r"(?:CONVICTION|Confidence):\s*(\w+)", text, re.IGNORECASE)
    confidence = conf_match.group(1) if conf_match else "N/A"

    # Lot size
    lot_match = re.search(r"(?:Lot Size|LOT_SIZE)[:\s]+([\d.]+)", text, re.IGNORECASE)
    lot_size = lot_match.group(1) if lot_match else "N/A"

    # R:R ratio
    rr = _calc_rr(entry, sl, tp)

    # Rating emoji
    rating_emoji = {
        "Buy": "🟢", "Overweight": "🟡", "Hold": "⚪",
        "Underweight": "🟠", "Sell": "🔴",
    }.get(rating, "⚪")

    # Action emoji
    action_emoji = {"Buy": "📈", "Sell": "📉", "Hold": "⏸"}.get(action, "❓")

    # Format numbers
    def fmt(val):
        if val is None:
            return "N/A"
        return f"{val:,.2f}" if isinstance(val, (int, float)) else str(val)

    # ── Build message ──────────────────────────────────────────────
    lines = [
        f"{'━' * 24}",
        f"📊 *{result.ticker}*  |  {result.trade_date}",
        f"{'━' * 24}",
        "",
        f"{rating_emoji} *RATING:*  `{rating}`",
        f"🎯 *Confidence:*  `{confidence}`",
        "",
    ]

    if summary:
        lines.extend([
            "📝 *Summary:*",
            _escape_md(summary),
            "",
        ])

    lines.extend([
        f"{'─' * 24}",
        f"{action_emoji} *TRADE PLAN*",
        f"{'─' * 24}",
        f"  Action:       `{action}`",
        f"  Entry:        `{fmt(entry)}`",
        f"  Stop Loss:    `{fmt(sl)}`",
        f"  Take Profit:  `{fmt(tp)}`",
        f"  Lot Size:     `{lot_size}`",
        f"  R:R:          `{rr}`",
        f"{'─' * 24}",
        "",
        "🕐 Horizon: 12-24 hours",
    ])

    # Timing
    if result.elapsed > 0:
        mins = int(result.elapsed // 60)
        secs = int(result.elapsed % 60)
        lines.append(f"⏱ Время анализа: {mins}m {secs}s")

    if result.run_dir:
        run_name = Path(result.run_dir).name
        lines.append(f"📁 `{run_name}`")

    return "\n".join(lines)


def _escape_md(text: str) -> str:
    """Escape Markdown special characters for Telegram (v1 mode)."""
    # In Markdown v1 mode, only these need escaping inside normal text
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


def format_status(result: RunResult) -> str:
    """Format a status message for an ongoing run."""
    if not result:
        return "ℹ️ No run in progress."

    if result.status == "failed":
        return f"❌ *{result.ticker}* failed after {result.agents_done} agents."

    elapsed_m = int(result.elapsed // 60)
    elapsed_s = int(result.elapsed % 60)
    return (
        f"⏳ *{result.ticker}* | {result.trade_date}\n"
        f"Agents: {result.agents_done}/{14}\n"
        f"Elapsed: {elapsed_m}m {elapsed_s}s"
    )
