# TradingAgents — Инструкция для следующей сессии

## Текущий статус проекта

**Последние изменения (закоммичены в `ee6e85e`):**
- Добавлены Smart Money агенты (4H + 15M) в LangGraph pipeline
- 14 агентов работают в обоих пайплайнах (OpenCode CLI + LangGraph API)
- README, CHANGELOG, web/scanner.py обновлены
- MCP knowledge graph проиндексирован (1780 nodes, 6165 edges)
- 50 тестов проходят

**GitHub:** `https://github.com/arcnosixta/TradingAgents` (ветка `main`)

---

## Следующая задача: Telegram Bot

Пользователь хочет Telegram бота, который:
1. Принимает команду `/analyze XAU-USD`
2. Запускает 14 агентов (orchestrator.py)
3. Шлёт прогресс и результат в Telegram

### Что уже есть

- `python-telegram-bot==22.8` — УСТАНОВЛЕН (проверено через `pip list`)
- `orchestrator.py` — рабочий пайплайн, запуск: `python opencode_pipeline/orchestrator.py XAU-USD --trade_date 2026-07-09`
- `parse_trader_proposal()` в `tradingagents/agents/utils/entry_validator.py` — парсит entry/SL/TP/action из markdown
- `web/runner.py` — пример запуска orchestrator как subprocess с прогрессом
- `final_decision.md` — содержит результат с секциями RATING, EXECUTIVE_SUMMARY, INTRADAY_PLAN

### Паттерн запуска (из web/runner.py)

```python
cmd = ["python", "orchestrator.py", ticker, "--trade_date", trade_date]
process = subprocess.Popen(cmd, cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
for line in process.stdout:
    if "--- Running" in line:
        # агент завершился
```

### Парсинг результата

`parse_trader_proposal(text)` возвращает:
```python
{"action": "Buy", "entry_price": 3345.50, "stop_loss": 3295.00, "take_profit": 3446.50}
```

Также нужно парсить RATING из final_decision.md:
```python
re.search(r"RATING:\s*(\w+)", text)
```

---

## Структура проекта (важные файлы)

```
TradingAgents/
├── opencode_pipeline/
│   ├── orchestrator.py          # Главный пайплайн (14 агентов)
│   ├── agent_runner.py          # Запуск OpenCode CLI для агента
│   ├── data_collector.py        # Сбор данных (yfinance, FRED, Reddit)
│   └── prompts/                 # 14 промптов агентов (.md)
├── tradingagents/
│   ├── agents/
│   │   ├── analysts/            # market, sentiment, news, fundamentals, smart_money_4h, smart_money_15m
│   │   ├── researchers/         # bull, bear
│   │   ├── managers/            # research_manager, portfolio_manager
│   │   ├── risk_mgmt/           # aggressive, conservative, neutral
│   │   ├── trader/              # trader
│   │   └── utils/
│   │       ├── entry_validator.py  # parse_trader_proposal(), validate_entry_levels()
│   │       └── agent_states.py     # AgentState (все поля включая smart_money)
│   ├── graph/
│   │   ├── trading_graph.py     # TradingAgentsGraph (LangGraph pipeline)
│   │   ├── setup.py             # Граф агентов
│   │   └── propagation.py       # Начальное состояние
│   ├── reporting.py             # Запись отчётов в файлы
│   ├── watchlist.py             # Watchlist scheduler (polling)
│   └── monitoring.py            # Мониторинг TP/SL цен (yfinance)
├── web/
│   ├── app.py                   # FastAPI дашборд
│   ├── runner.py                # Subprocess запуск orchestrator
│   └── scanner.py               # Парсинг runs/ директории
├── cli/
│   └── main.py                  # Интерактивный CLI (typer + rich)
├── tests/                       # 50+ тестов
├── pyproject.toml               # Зависимости, ruff, pytest
└── opencode.json                # Конфиг OpenCode (mimo-v2.5-free)
```

---

## Реализация Telegram Bot

### Файлы для создания

```
telegram_bot/
├── __init__.py
├── bot.py         # Основной бот: хэндлеры, middleware
├── config.py      # Токен, whitelist, настройки
├── parser.py      # Парсинг final_decision.md → красивое сообщение
└── runner.py      # Запуск orchestrator.py subprocess + progress
```

### bot.py — основной хэндлер

```python
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config import BOT_TOKEN, ALLOWED_USER_IDS
from runner import RunManager
from parser import format_decision

run_manager = RunManager()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USER_IDS:
        await update.message.reply_text("Access denied.")
        return
    await update.message.reply_text(
        "🤖 TradingAgents Bot\n\n"
        "/analyze TICKER — запустить анализ\n"
        "/status — статус запуска\n"
        "/last — последний результат\n"
        "/help — справка"
    )

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USER_IDS:
        await update.message.reply_text("Access denied.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /analyze XAU-USD [YYYY-MM-DD]")
        return
    
    ticker = args[0].upper()
    trade_date = args[1] if len(args) > 1 else None
    
    msg = await update.message.reply_text(f"⏳ Запускаю анализ {ticker}...")
    
    # Запуск в фоне
    asyncio.create_task(run_analysis(msg, ticker, trade_date))

async def run_analysis(msg, ticker, trade_date):
    try:
        result = await run_manager.start(ticker, trade_date, progress_callback=update_progress)
        text = format_decision(result)
        await msg.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

async def update_progress(msg, text):
    try:
        await msg.edit_text(text)
    except Exception:
        pass  # rate limit
```

### runner.py — запуск orchestrator

```python
import subprocess
import asyncio
import os
import json
from pathlib import Path
from dataclasses import dataclass

PROJECT_ROOT = Path(__file__).parent.parent
ORCHESTRATOR = PROJECT_ROOT / "opencode_pipeline" / "orchestrator.py"

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
    def __init__(self):
        self.current_process = None
    
    async def start(self, ticker, trade_date, progress_callback=None):
        import datetime
        if trade_date is None:
            trade_date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        cmd = ["python", str(ORCHESTRATOR), ticker, "--trade_date", trade_date]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
            env={**os.environ},
        )
        self.current_process = process
        
        agents_done = 0
        total = 14
        
        async for line in process.stdout:
            line = line.decode().strip()
            if "--- Running" in line:
                agents_done += 1
                if progress_callback and agents_done % 3 == 0:
                    await progress_callback(
                        f"⏳ {ticker} | Агент {agents_done}/{total}..."
                    )
        
        await process.wait()
        
        # Найти последний run_dir
        runs_dir = PROJECT_ROOT / "runs"
        run_dirs = sorted(runs_dir.glob(f"{ticker}_{trade_date}_*"), reverse=True)
        
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
                    elapsed=0,
                )
        
        return RunResult(
            ticker=ticker,
            trade_date=trade_date,
            status="failed",
            final_decision="",
            run_dir="",
            agents_done=agents_done,
            elapsed=0,
        )
```

### parser.py — форматирование результата

```python
import re
from tradingagents.agents.utils.entry_validator import parse_trader_proposal

def format_decision(result) -> str:
    if result.status == "failed":
        return f"❌ Анализ {result.ticker} не удался"
    
    text = result.final_decision
    
    # Парсим
    rating_match = re.search(r"RATING:\s*(\w+)", text)
    rating = rating_match.group(1) if rating_match else "N/A"
    
    parsed = parse_trader_proposal(text)
    action = parsed.get("action") or "N/A"
    entry = parsed.get("entry_price")
    sl = parsed.get("stop_loss")
    tp = parsed.get("take_profit")
    
    # Executive Summary
    summary_match = re.search(r"EXECUTIVE_SUMMARY:\s*\n(.+?)(?=\n\n|\nINTRADAY)", text, re.DOTALL)
    summary = summary_match.group(1).strip()[:200] if summary_match else "N/A"
    
    # Confidence
    conf_match = re.search(r"CONVICTION:\s*(\w+)", text)
    confidence = conf_match.group(1) if conf_match else "N/A"
    
    # Форматируем
    stars = {"Buy": "🟢", "Overweight": "🟡", "Hold": "⚪", "Underweight": "🟠", "Sell": "🔴"}.get(rating, "⚪")
    
    msg = f"""
📊 *{result.ticker}* | {result.trade_date}

{stars} *RATING:* `{rating}`

📝 *Summary:*
{summary}

💰 *TRADE PLAN:*
├─ Action: `{action}`
├─ Entry: `{entry}`
├─ Stop Loss: `{sl}`
├─ Take Profit: `{tp}`
├─ Lot Size: calculated
└─ R:R: auto

🎯 Confidence: `{confidence}`
🕐 Horizon: 12-24 hours

📁 Full report: `{result.run_dir}`
""".strip()
    
    return msg
```

### config.py

```python
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_IDS = [int(x) for x in os.environ.get("TELEGRAM_ALLOWED_IDS", "").split(",") if x]
```

### .env.telegram

```
TELEGRAM_BOT_TOKEN=你的токен_от_BotFather
TELEGRAM_ALLOWED_IDS=你的Telegram_user_id
```

---

## Как получить токен

1. Открой Telegram, найди `@BotFather`
2. Отправь `/newbot`
3. Придумай имя (например `TradingAgents Signal Bot`)
4. Придумай username (например `tradingagents_xyz_bot`)
5. BotFather пришлёт токен — скопируй в `.env.telegram`
6. Узнай свой user_id: найди `@userinfobot` в Telegram, отправь `/start`

---

## Запуск

```bash
cd /home/arcnosixta/TradingAgents
# Установить зависимости (если нет)
pip install python-telegram-bot python-dotenv

# Создать .env.telegram с токеном

# Запустить бота
python -m telegram_bot.bot
```

---

## Важные замечания

1. **OpenCode CLI должен быть установлен** — orchestrator.py вызывает `opencode run` для каждого агента. Проверить: `which opencode`

2. **Время выполнения** — полный анализ занимает 5-15 минут в зависимости от модели и количества агентов. Бот должен показывать прогресс.

3. **Лимиты Telegram** — нельзя редактировать сообщение чаще чем раз в ~1.5 секунды. В `update_progress` нужен throttle.

4. **Одна задача за раз** — orchestrator.py не поддерживает параллельные запуски (один процесс на весь пайплайн).

5. **Тесты запускать:** `python -m pytest tests/test_smart_money_integration.py tests/test_entry_validator_v2.py -v`

6. **Git:** все изменения коммитить в `main`, пушить в `origin`

---

## Решение проблем

**"No module named tradingagents":**
```bash
pip install -e .
```

**"opencode: command not found":**
```bash
curl -fsSL https://opencode.ai/install | bash
```

**Telegram rate limit (429):**
Добавить `asyncio.sleep(1.5)` между edit_message.

**Orchestrator падает на агенте:**
Проверить `runs/<TICKER>_<DATE>_<TS>/run_log.json` — там статус каждого агента.

---

## Контакты

- GitHub: `https://github.com/arcnosixta/TradingAgents`
- MCP project: `home-arcnosixta-TradingAgents`
