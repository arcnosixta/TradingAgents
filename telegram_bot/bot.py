"""TradingAgents Telegram Bot — button-driven UI with animated progress.

Run:
    python -m telegram_bot.bot

Requires .env.telegram with TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_IDS.
"""

import asyncio
import logging
import sys
from pathlib import Path

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# Add telegram_bot package to path
_pkg_dir = Path(__file__).parent
if str(_pkg_dir) not in sys.path:
    sys.path.insert(0, str(_pkg_dir))

# Add project root to path for imports
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config import BOT_TOKEN, ALLOWED_USER_IDS, WEBAPP_URL
from parser import format_decision
from runner import RunManager, PHASE_LABELS, PHASE_EMOJI

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Single run manager
run_manager = RunManager()

# Conversation states
AWAITING_TICKER, AWAITING_DATE = range(2)

# ── Popular tickers for quick-access buttons ───────────────────────
POPULAR_TICKERS = [
    ("XAU-USD", "Gold"),
    ("BTC-USD", "Bitcoin"),
    ("AAPL", "Apple"),
    ("NVDA", "NVIDIA"),
    ("EURUSD=X", "EUR/USD"),
    ("TSLA", "Tesla"),
]


# ── Access check ───────────────────────────────────────────────────

def check_access(update: Update) -> bool:
    uid = update.effective_user.id
    if ALLOWED_USER_IDS and uid not in ALLOWED_USER_IDS:
        return False
    return True


# ── Keyboards ──────────────────────────────────────────────────────

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Открыть TradingAgents", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton("📊 Запустить анализ", callback_data="menu_analyze")],
        [
            InlineKeyboardButton("📋 Статус", callback_data="menu_status"),
            InlineKeyboardButton("📁 Последний", callback_data="menu_last"),
        ],
        [
            InlineKeyboardButton("🛑 Отменить", callback_data="menu_cancel"),
            InlineKeyboardButton("❓ Справка", callback_data="menu_help"),
        ],
    ])


def ticker_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(POPULAR_TICKERS), 2):
        row = []
        for ticker, label in POPULAR_TICKERS[i:i + 2]:
            row.append(InlineKeyboardButton(
                f"{label} ({ticker})",
                callback_data=f"ticker_{ticker}",
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton("✏️ Ввести свой тикер", callback_data="ticker_custom")])
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def date_keyboard() -> InlineKeyboardMarkup:
    import datetime
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📅 Сегодня ({today})", callback_data=f"date_{today}")],
        [InlineKeyboardButton(f"📅 Вчера ({yesterday})", callback_data=f"date_{yesterday}")],
        [InlineKeyboardButton("✏️ Ввести дату", callback_data="date_custom")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_tickers")],
    ])


def result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Повторить анализ", callback_data="menu_analyze")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="back_main")],
    ])


def running_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Обновить статус", callback_data="menu_status")],
        [InlineKeyboardButton("🛑 Отменить", callback_data="menu_cancel")],
    ])


# ── /start ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        await update.message.reply_text("⛔ Access denied.")
        return ConversationHandler.END

    await update.message.reply_text(
        "🤖 *TradingAgents Bot*\n\n"
        "AI-анализ рынка на 14 агентов\n"
        "с параллельным выполнением.\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


# ── Callback: Main Menu ───────────────────────────────────────────

async def cb_main_menu(query, context):
    """Return to main menu."""
    await query.answer()
    await query.edit_message_text(
        "🤖 *TradingAgents Bot*\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


# ── Analyze flow ───────────────────────────────────────────────────

async def cb_analyze(query, context):
    """Show ticker selection."""
    await query.answer()
    if run_manager.is_running:
        await query.edit_message_text(
            "⏳ Анализ уже запущен!\n\n"
            "Дождитесь завершения или отмените.",
            reply_markup=running_keyboard(),
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "📊 *Выберите инструмент:*",
        parse_mode="Markdown",
        reply_markup=ticker_keyboard(),
    )
    return ConversationHandler.END


async def cb_ticker_select(query, context):
    """Handle ticker button press."""
    await query.answer()
    ticker = query.data.replace("ticker_", "")

    if ticker == "custom":
        await query.edit_message_text(
            "✏️ Введите тикер (например `XAU-USD`, `BTC-USD`, `AAPL`):",
            parse_mode="Markdown",
        )
        return AWAITING_TICKER

    context.user_data["selected_ticker"] = ticker
    await query.edit_message_text(
        f"📊 Тикер: *{ticker}*\n\n"
        "📅 Выберите дату анализа:",
        parse_mode="Markdown",
        reply_markup=date_keyboard(),
    )
    return ConversationHandler.END


async def msg_custom_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom ticker text input."""
    if not check_access(update):
        return ConversationHandler.END

    ticker = update.message.text.strip().upper()
    if not ticker or len(ticker) > 20:
        await update.message.reply_text(
            "❌ Некорректный тикер. Попробуйте снова:",
        )
        return AWAITING_TICKER

    context.user_data["selected_ticker"] = ticker
    await update.message.reply_text(
        f"📊 Тикер: *{ticker}*\n\n"
        "📅 Выберите дату анализа:",
        parse_mode="Markdown",
        reply_markup=date_keyboard(),
    )
    return ConversationHandler.END


async def cb_date_select(query, context):
    """Handle date button press -> start analysis."""
    await query.answer()
    date_val = query.data.replace("date_", "")

    if date_val == "custom":
        await query.edit_message_text(
            "✏️ Введите дату в формате `YYYY-MM-DD`:",
            parse_mode="Markdown",
        )
        return AWAITING_DATE

    ticker = context.user_data.get("selected_ticker", "XAU-USD")
    await _start_analysis(query.message, ticker, date_val, edit=True)
    return ConversationHandler.END


async def msg_custom_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom date text input."""
    if not check_access(update):
        return ConversationHandler.END

    import datetime
    date_text = update.message.text.strip()
    try:
        datetime.datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text(
            "❌ Некорректная дата. Формат: `YYYY-MM-DD`\nПопробуйте снова:",
            parse_mode="Markdown",
        )
        return AWAITING_DATE

    ticker = context.user_data.get("selected_ticker", "XAU-USD")
    await _start_analysis(update.message, ticker, date_text, edit=False)
    return ConversationHandler.END


async def cb_back_tickers(query, context):
    """Back to ticker selection."""
    await query.answer()
    await query.edit_message_text(
        "📊 *Выберите инструмент:*",
        parse_mode="Markdown",
        reply_markup=ticker_keyboard(),
    )
    return ConversationHandler.END


# ── Start analysis ─────────────────────────────────────────────────

async def _start_analysis(msg, ticker: str, trade_date: str, edit: bool = False):
    """Launch analysis and show animated progress."""
    text = (
        f"🚀 *Запуск анализа {ticker}* на {trade_date}\n\n"
        "⏳ Инициализация...\n\n"
        "░░░░░░░░░░  0/14 агентов"
    )
    if edit:
        status_msg = await msg.edit_text(text, parse_mode="Markdown", reply_markup=running_keyboard())
    else:
        status_msg = await msg.reply_text(text, parse_mode="Markdown", reply_markup=running_keyboard())

    asyncio.create_task(_run_analysis_bg(status_msg, ticker, trade_date))


async def _run_analysis_bg(msg, ticker: str, trade_date: str):
    """Background task: run orchestrator, update progress, show result."""

    async def progress_cb(text: str):
        try:
            await msg.edit_text(
                text,
                parse_mode="Markdown",
                reply_markup=running_keyboard(),
            )
        except Exception:
            pass  # rate limit / message not modified

    try:
        result = await run_manager.start(
            ticker, trade_date, progress_callback=progress_cb,
        )

        if result.status == "completed":
            text = format_decision(result)
            # Split if too long for Telegram (4096 char limit)
            if len(text) > 4000:
                await msg.edit_text(
                    text[:4000],
                    parse_mode="Markdown",
                    reply_markup=result_keyboard(),
                )
            else:
                await msg.edit_text(
                    text,
                    parse_mode="Markdown",
                    reply_markup=result_keyboard(),
                )
        else:
            error_text = result.final_decision[:500] if result.final_decision else "Unknown error"
            await msg.edit_text(
                f"❌ *Анализ {ticker} не удался*\n\n`{error_text}`",
                parse_mode="Markdown",
                reply_markup=result_keyboard(),
            )

    except Exception as e:
        logger.exception("Analysis failed")
        try:
            await msg.edit_text(
                f"❌ Ошибка: `{e}`",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
        except Exception:
            pass


# ── Status ─────────────────────────────────────────────────────────

async def cb_status(query, context):
    """Show current analysis status."""
    await query.answer()
    if not run_manager.is_running:
        await query.edit_message_text(
            "ℹ️ Нет запущенных анализов.",
            reply_markup=main_menu_keyboard(),
        )
        return

    text = run_manager._build_progress_text()
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=running_keyboard(),
    )


# ── Last result ────────────────────────────────────────────────────

async def cb_last(query, context):
    """Show the latest completed analysis."""
    await query.answer()
    from runner import RunResult

    runs_dir = _project_root / "runs"
    if not runs_dir.exists():
        await query.edit_message_text(
            "📁 Нет сохранённых анализов.",
            reply_markup=main_menu_keyboard(),
        )
        return

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

            result_obj = RunResult(
                ticker=ticker,
                trade_date=date,
                status="completed",
                final_decision=final_decision,
                run_dir=str(run_dir),
                agents_done=14,
                elapsed=0,
            )
            text = format_decision(result_obj)
            if len(text) > 4000:
                text = text[:4000]
            await query.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=result_keyboard(),
            )
            return

    await query.edit_message_text(
        "📁 Нет готовых анализов.",
        reply_markup=main_menu_keyboard(),
    )


# ── Cancel ─────────────────────────────────────────────────────────

async def cb_cancel(query, context):
    """Cancel running analysis."""
    await query.answer()
    if run_manager.is_running:
        run_manager.cancel()
        await query.edit_message_text(
            "🛑 Анализ отменён.",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await query.edit_message_text(
            "ℹ️ Нечего отменять.",
            reply_markup=main_menu_keyboard(),
        )


# ── Help ───────────────────────────────────────────────────────────

async def cb_help(query, context):
    """Show help."""
    await query.answer()
    await query.edit_message_text(
        "📖 *Справка — TradingAgents Bot*\n\n"
        "*Тикеры:*\n"
        "  `XAU-USD` — Золото\n"
        "  `BTC-USD` — Биткоин\n"
        "  `AAPL` — Apple\n"
        "  `EURUSD=X` — Форекс\n"
        "  `NVDA` — NVIDIA\n\n"
        "*Как работает:*\n"
        "1. Нажмите 📊 Запустить анализ\n"
        "2. Выберите инструмент\n"
        "3. Выберите дату\n"
        "4. Ждите результат (5-15 мин)\n\n"
        "*14 AI-агентов:*\n"
        "  📊 Market + Sentiment + News + Fundamentals\n"
        "  💰 Smart Money (4H + 15M)\n"
        "  🐂 Bull + 🐻 Bear Researchers\n"
        "  🔬 Research Manager\n"
        "  📈 Trader\n"
        "  🔥🛡⚖️ Risk Debate (3 агента)\n"
        "  👔 Portfolio Manager\n\n"
        "*Параллелизм:*\n"
        "  Фаза 1: 4 аналитика одновременно\n"
        "  Фаза 2: 2 Smart Money одновременно\n"
        "  Остальные — последовательно\n\n"
        "*Результат:*\n"
        "  Rating, Entry, SL, TP, Lot Size, Confidence",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_main")],
        ]),
    )


# ── /app — open Mini App ─────────────────────────────────────────

async def cmd_app(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        await update.message.reply_text("⛔ Access denied.")
        return
    await update.message.reply_text(
        "🚀 *TradingAgents Mini App*\n\n"
        "Нажмите кнопку ниже, чтобы открыть приложение:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Открыть TradingAgents", web_app=WebAppInfo(url=WEBAPP_URL))],
        ]),
    )


# ── Fallback: /analyze TICKER [DATE] still works ──────────────────

async def cmd_analyze_legacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Legacy /analyze command for power users."""
    if not check_access(update):
        await update.message.reply_text("⛔ Access denied.")
        return

    if run_manager.is_running:
        await update.message.reply_text(
            "⏳ Анализ уже запущен!",
            reply_markup=running_keyboard(),
        )
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "📊 *Выберите инструмент:*",
            parse_mode="Markdown",
            reply_markup=ticker_keyboard(),
        )
        return

    ticker = args[0].upper()
    import datetime
    trade_date = args[1] if len(args) > 1 else datetime.datetime.now().strftime("%Y-%m-%d")
    await _start_analysis(update.message, ticker, trade_date, edit=False)


# ── Dispatcher for callback_data routing ───────────────────────────

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route all InlineKeyboard callbacks."""
    query = update.callback_query
    if not check_access(update):
        await query.answer("⛔ Access denied.", show_alert=True)
        return ConversationHandler.END

    data = query.data

    if data == "back_main":
        return await cb_main_menu(query, context)
    elif data == "menu_analyze":
        return await cb_analyze(query, context)
    elif data == "menu_status":
        return await cb_status(query, context)
    elif data == "menu_last":
        return await cb_last(query, context)
    elif data == "menu_cancel":
        return await cb_cancel(query, context)
    elif data == "menu_help":
        return await cb_help(query, context)
    elif data.startswith("ticker_"):
        return await cb_ticker_select(query, context)
    elif data.startswith("date_"):
        return await cb_date_select(query, context)
    elif data == "back_tickers":
        return await cb_back_tickers(query, context)

    await query.answer()
    return ConversationHandler.END


# ── Main ───────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set.")
        print("Create .env.telegram in project root:")
        print("  TELEGRAM_BOT_TOKEN=your_token_here")
        print("  TELEGRAM_ALLOWED_IDS=your_user_id")
        sys.exit(1)

    logger.info("Starting TradingAgents Telegram Bot (button UI)...")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register /app handler outside conversation
    app.add_handler(CommandHandler("app", cmd_app))

    # ConversationHandler for the custom ticker/date input flow
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CommandHandler("analyze", cmd_analyze_legacy),
            CommandHandler("app", cmd_app),
            CallbackQueryHandler(callback_router),
        ],
        states={
            AWAITING_TICKER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, msg_custom_ticker),
            ],
            AWAITING_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, msg_custom_date),
            ],
        },
        fallbacks=[
            CommandHandler("start", cmd_start),
            CommandHandler("analyze", cmd_analyze_legacy),
            CallbackQueryHandler(callback_router),
        ],
        per_message=False,
    )

    app.add_handler(conv)

    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
