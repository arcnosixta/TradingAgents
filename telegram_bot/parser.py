"""Parse final_decision.md and format as Telegram message."""

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


def format_decision(result: RunResult) -> str:
    """Format RunResult as a readable Telegram message."""
    if result.status == "failed":
        return f"❌ Анализ *{result.ticker}* не удался.\n\n{result.final_decision[:500]}"

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
        tp_match = re.search(r"(?:TAKE_PROFIT_1|Take Profit 1)[:\s]+([\d,]+\.?\d*)", text, re.IGNORECASE)
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

    # Rating emoji
    rating_emoji = {
        "Buy": "🟢",
        "Overweight": "🟡",
        "Hold": "⚪",
        "Underweight": "🟠",
        "Sell": "🔴",
    }.get(rating, "⚪")

    # Action emoji
    action_emoji = {"Buy": "📈", "Sell": "📉", "Hold": "⏸"}.get(action, "❓")

    # Format numbers
    def fmt(val):
        if val is None:
            return "N/A"
        return f"{val:,.2f}" if isinstance(val, (int, float)) else str(val)

    # Build message
    lines = [
        f"📊 *{result.ticker}* | {result.trade_date}",
        "",
        f"{rating_emoji} *RATING:* `{rating}`",
        "",
    ]

    if summary:
        lines.extend([
            "📝 *Summary:*",
            _escape_md(summary),
            "",
        ])

    lines.extend([
        f"{action_emoji} *TRADE PLAN:*",
        f"├─ Action: `{action}`",
        f"├─ Entry: `{fmt(entry)}`",
        f"├─ Stop Loss: `{fmt(sl)}`",
        f"├─ Take Profit: `{fmt(tp)}`",
        f"├─ Lot Size: `{lot_size}`",
        f"└─ Confidence: `{confidence}`",
        "",
        f"🕐 Horizon: 12-24 hours",
    ])

    # Timing
    if result.elapsed > 0:
        mins = int(result.elapsed // 60)
        secs = int(result.elapsed % 60)
        lines.append(f"⏱ Analysis took: {mins}m {secs}s")

    if result.run_dir:
        run_name = Path(result.run_dir).name
        lines.append(f"📁 Run: `{run_name}`")

    return "\n".join(lines)


def _escape_md(text: str) -> str:
    """Escape MarkdownV2 special characters for Telegram."""
    # Only escape characters that break Telegram MarkdownV2
    for ch in r"_*[]()~`>#+-=|{}.!":
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
