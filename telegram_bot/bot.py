"""TradingAgents Telegram Bot.

Run:
    python -m telegram_bot.bot

Requires .env.telegram with TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_IDS.
"""

import asyncio
import logging
import sys
from pathlib import Path

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# Add telegram_bot package to path
_pkg_dir = Path(__file__).parent
if str(_pkg_dir) not in sys.path:
    sys.path.insert(0, str(_pkg_dir))

# Add project root to path for imports
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config import BOT_TOKEN, ALLOWED_USER_IDS
from parser import format_decision, format_status
from runner import RunManager

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Single run manager — only one analysis at a time
run_manager = RunManager()


def check_access(update: Update) -> bool:
    """Check if user is in the allowed list."""
    user_id = update.effective_user.id
    if ALLOWED_USER_IDS and user_id not in ALLOWED_USER_IDS:
        return False
    return True


# ── /start ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        await update.message.reply_text("⛔ Access denied.")
        return

    await update.message.reply_text(
        "🤖 *TradingAgents Bot*\n\n"
        "AI-анализ рынка на 14 агентов.\n\n"
        "Команды:\n"
        "/analyze TICKER — запустить анализ\n"
        "/analyze TICKER 2026-07-09 — на дату\n"
        "/status — статус запуска\n"
        "/last — последний результат\n"
        "/cancel — отменить запуск\n"
        "/help — справка",
        parse_mode="Markdown",
    )


# ── /help ───────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        await update.message.reply_text("⛔ Access denied.")
        return

    await update.message.reply_text(
        "📖 *Справка*\n\n"
        "*Тикеры:*\n"
        "• `XAU-USD` — Золото\n"
        "• `BTC-USD` — Биткоин\n"
        "• `AAPL` — Apple\n"
        "• `EURUSD` — Форекс\n"
        "• `NVDA` — NVIDIA\n\n"
        "*Примеры:*\n"
        "• `/analyze XAU-USD` — анализ золота на сегодня\n"
        "• `/analyze BTC-USD 2026-07-09` — биткоин на дату\n"
        "• `/analyze AAPL` — акции Apple\n\n"
        "*Время анализа:* 5-15 минут (14 AI агентов)\n\n"
        "*Что получите:*\n"
        "• Рейтинг (Buy/Sell/Hold)\n"
        "• Entry / Stop Loss / Take Profit\n"
        "• Lot Size\n"
        "• Smart Money анализ\n"
        "• Confidence",
        parse_mode="Markdown",
    )


# ── /analyze ────────────────────────────────────────────────────────

async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        await update.message.reply_text("⛔ Access denied.")
        return

    if run_manager.is_running:
        await update.message.reply_text("⏳ Анализ уже запущен. /status")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "📝 *Использование:*\n"
            "`/analyze TICKER` — на сегодня\n"
            "`/analyze TICKER 2026-07-09` — на дату",
            parse_mode="Markdown",
        )
        return

    ticker = args[0].upper()
    trade_date = args[1] if len(args) > 1 else None

    date_str = trade_date or "сегодня"
    status_msg = await update.message.reply_text(
        f"🚀 *Запуск анализа {ticker}* на {date_str}...\n\n"
        f"⏳ Сбор данных (OHLCV, индикаторы, новости)...",
        parse_mode="Markdown",
    )

    # Run in background
    asyncio.create_task(_run_analysis(status_msg, ticker, trade_date))


async def _run_analysis(msg, ticker: str, trade_date: str | None):
    """Background task: run orchestrator and update message."""

    async def progress_cb(text: str):
        """Throttled progress update."""
        try:
            await msg.edit_text(text, parse_mode="Markdown")
        except Exception:
            pass  # rate limit or message not modified

    try:
        result = await run_manager.start(
            ticker, trade_date, progress_callback=progress_cb
        )

        if result.status == "completed":
            text = format_decision(result)
            await msg.edit_text(text, parse_mode="Markdown")
        else:
            error_text = result.final_decision[:500] if result.final_decision else "Unknown error"
            await msg.edit_text(
                f"❌ *Анализ {ticker} не удался*\n\n`{error_text}`",
                parse_mode="Markdown",
            )

    except Exception as e:
        logger.exception("Analysis failed")
        try:
            await msg.edit_text(f"❌ Ошибка: {e}")
        except Exception:
            pass


# ── /status ─────────────────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        await update.message.reply_text("⛔ Access denied.")
        return

    if not run_manager.is_running:
        await update.message.reply_text("ℹ️ Нет запущенных анализов.")
        return

    await update.message.reply_text("⏳ Анализ выполняется... /status")


# ── /last ───────────────────────────────────────────────────────────

async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        await update.message.reply_text("⛔ Access denied.")
        return

    from runner import RunResult

    runs_dir = _project_root / "runs"
    if not runs_dir.exists():
        await update.message.reply_text("📁 Нет сохранённых анализов.")
        return

    # Find latest run with final_decision.md
    run_dirs = sorted(runs_dir.iterdir(), reverse=True)
    for run_dir in run_dirs:
        if not run_dir.is_dir():
            continue
        decision_path = run_dir / "reports" / "final_decision.md"
        if decision_path.exists():
            parts = run_dir.name.rsplit("_", 2)
            ticker = parts[0] if len(parts) >= 3 else run_dir.name
            date = parts[1] if len(parts) >= 3 else ""
            final_decision = decision_path.read_text(encoding="utf-8")

            result = RunResult(
                ticker=ticker,
                trade_date=date,
                status="completed",
                final_decision=final_decision,
                run_dir=str(run_dir),
                agents_done=14,
                elapsed=0,
            )
            text = format_decision(result)
            await update.message.reply_text(text, parse_mode="Markdown")
            return

    await update.message.reply_text("📁 Нет готовых анализов.")


# ── /cancel ─────────────────────────────────────────────────────────

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        await update.message.reply_text("⛔ Access denied.")
        return

    if run_manager.is_running:
        run_manager.cancel()
        await update.message.reply_text("🛑 Анализ отменён.")
    else:
        await update.message.reply_text("ℹ️ Нечего отменять.")


# ── Main ────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set.")
        print("Create .env.telegram in project root:")
        print("  TELEGRAM_BOT_TOKEN=your_token_here")
        print("  TELEGRAM_ALLOWED_IDS=your_user_id")
        sys.exit(1)

    logger.info("Starting TradingAgents Telegram Bot...")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("analyze", cmd_analyze))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("last", cmd_last))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
