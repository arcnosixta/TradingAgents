# TradingAgents

Multi-agent LLM trading framework for intraday analysis. Runs 14 specialized AI agents sequentially to produce actionable trade signals.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Install OpenCode](#install-opencode)
- [Two Ways to Run](#two-ways-to-run)
- [OpenCode Pipeline — How It Works](#opencode-pipeline--how-it-works)
- [Supported Instruments](#supported-instruments)
- [Configuration](#configuration)
- [Web Dashboard](#web-dashboard)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Русская версия](#русская-версия)

---

## Quick Start

```bash
git clone https://github.com/arcnosixta/TradingAgents.git
cd TradingAgents
pip install .
```

## Install OpenCode

The recommended pipeline uses [OpenCode](https://opencode.ai) — a free, open-source AI coding agent. Install it on your platform:

### Linux

```bash
# Any distro (curl installer)
curl -fsSL https://opencode.ai/install | bash

# Arch / Manjaro (AUR)
paru -S opencode
```

Or install the **Desktop app** (Beta):
- `.deb` — Ubuntu/Debian: `sudo dpkg -i opencode-desktop-linux-x64.deb`
- `.rpm` — Fedora/RHEL: `sudo rpm -i opencode-desktop-linux-x64.rpm`

### macOS

```bash
# Homebrew (recommended)
brew install anomalyco/tap/opencode

# Or Desktop app
brew install --cask opencode-desktop
```

Direct download: [Apple Silicon](https://opencode.ai/download/stable/darwin-aarch64-dmg) | [Intel](https://opencode.ai/download/stable/darwin-x64-dmg)

### Windows

Download the installer: [opencode-desktop-windows-x64.exe](https://opencode.ai/download/stable/windows-x64-nsis)

Or install via package managers:

```powershell
# npm
npm i -g opencode-ai

# bun
bun add -g opencode-ai
```

### IDE Extensions

OpenCode also works as an extension inside your editor:

| Editor | Install |
|--------|---------|
| VS Code | [opencode.ai/docs/ide](https://opencode.ai/docs/ide/) |
| Cursor | [opencode.ai/docs/ide](https://opencode.ai/docs/ide/) |
| Zed | [opencode.ai/docs/ide](https://opencode.ai/docs/ide/) |
| Windsurf | [opencode.ai/docs/ide](https://opencode.ai/docs/ide/) |
| VSCodium | [opencode.ai/docs/ide](https://opencode.ai/docs/ide/) |

---

## Two Ways to Run

### 1. OpenCode Pipeline (recommended)

Runs 12 agents via OpenCode CLI with free models. **No API keys needed.**

```bash
cd opencode_pipeline
python orchestrator.py              # XAU-USD (default)
python orchestrator.py BTC-USD      # Bitcoin
python orchestrator.py AAPL         # Apple
python orchestrator.py --trade_date 2026-07-03
```

Results saved to `runs/<TICKER>_<DATE>_<TIMESTAMP>/reports/`.

### 2. LangGraph Pipeline (original)

Uses direct LLM API calls. Requires an API key.

```bash
tradingagents                        # interactive CLI
python -m cli.main                   # alternative
```

Or programmatically:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())
_, decision = ta.propagate("NVDA", "2026-01-15")
```

---

## OpenCode Pipeline — How It Works

1. **Data Collection** — fetches OHLCV, indicators, news, sentiment, macro data via Yahoo Finance
2. **12 AI Agents** — each reads data files and writes a report
3. **Agreement Rules** — trader and portfolio manager must align with research manager rating
4. **Final Decision** — entry, stop loss, take profit, lot size for MetaTrader5

### Agents

| # | Agent | Role |
|---|-------|------|
| 1 | Market Analyst | H1/H4 technical analysis, support/resistance levels |
| 2 | Sentiment Analyst | News, Reddit, StockTwits sentiment scoring |
| 3 | News Analyst | Macro events, central bank, geopolitics |
| 4 | Fundamentals Analyst | Company financials (stocks only) |
| 5 | Smart Money 4H | Higher timeframe structure, order blocks, liquidity zones |
| 6 | Smart Money 15M | Intraday micro-structure, entry zones, volume profile |
| 7 | Bull Researcher | Argument FOR buying |
| 8 | Bear Researcher | Argument AGAINST buying |
| 9 | Research Manager | Final rating based on bull/bear debate |
| 10 | Trader | Entry/stop/take-profit for MT5 |
| 11 | Aggressive Risk | Max upside analysis |
| 12 | Conservative Risk | Capital preservation |
| 13 | Neutral Risk | Balanced assessment |
| 14 | Portfolio Manager | Final decision with lot size |

---

## Supported Instruments

Any ticker Yahoo Finance covers:

| Market | Examples |
|--------|----------|
| US Stocks | `AAPL`, `SPY`, `NVDA` |
| Gold | `XAU-USD`, `XAUUSD`, `GOLD` |
| Silver | `XAG-USD`, `XAGUSD` |
| Forex | `EURUSD`, `GBPJPY` |
| Crypto | `BTC-USD`, `ETH-USD` |
| Indices | `SPX500`, `NAS100`, `US30` |
| Oil | `WTICOUSD`, `BCOUSD` |

---

## Configuration

### Default settings (`opencode.json`)

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "opencode/mimo-v2.5-free"
}
```

Change model by editing this file or passing `-m provider/model` to `opencode run`.

### Environment variables (LangGraph pipeline)

```bash
# LLM providers (pick one)
export OPENAI_API_KEY=...
export GOOGLE_API_KEY=...
export ANTHROPIC_API_KEY=...
export DEEPSEEK_API_KEY=...

# Data sources (optional)
export ALPHA_VANTAGE_API_KEY=...
export FRED_API_KEY=...
```

### Docker

```bash
cp .env.example .env    # add API keys
docker compose run --rm tradingagents
```

### Web Dashboard

Visual interface to view past analyses, track progress, and launch new runs.

```bash
pip install ".[web]"
python run_web.py
# → http://localhost:8000
```

Features:
- Dashboard with all past analyses (ticker, status, rating)
- Detailed report view (all 12 agent outputs)
- Launch new analyses directly from the browser
- Real-time progress tracking

---

## Project Structure

```
TradingAgents/
├── opencode_pipeline/           # OpenCode-based pipeline
│   ├── orchestrator.py          # Main entry point
│   ├── data_collector.py        # Phase 0: collect all data
│   ├── agent_runner.py          # Runs OpenCode CLI per agent
│   └── prompts/                 # 12 agent prompt templates
├── tradingagents/               # Core library (LangGraph pipeline)
│   ├── agents/                  # Agent definitions
│   │   ├── analysts/            # Market, Sentiment, News, Fundamentals, Smart Money
│   │   ├── managers/            # Research Manager, Portfolio Manager
│   │   ├── researchers/         # Bull, Bear researchers
│   │   ├── risk_mgmt/           # Aggressive, Conservative, Neutral risk
│   │   ├── trader/              # Trader agent
│   │   └── utils/               # Tools, schemas, memory, validators
│   ├── dataflows/               # Data source adapters
│   ├── graph/                   # LangGraph orchestration
│   └── llm_clients/             # LLM provider abstraction
├── web/                         # Web dashboard
│   ├── app.py                   # FastAPI application
│   ├── scanner.py               # Parse runs/ directory
│   ├── runner.py                # Background analysis runner
│   ├── templates/               # HTML templates
│   └── static/                  # CSS + JS
├── cli/                         # Interactive CLI
├── tests/                       # Test suite
├── run_web.py                   # Web dashboard entry point
└── opencode.json                # OpenCode config (mimo-v2.5-free)
```

---

## Troubleshooting

**"No module named tradingagents"**
```bash
pip install -e .    # editable install from project root
```

**OHLCV data shows all zeros**
Make sure you installed from local: `pip install -e .` (not from PyPI).

**Macro data errors (FRED_API_KEY)**
Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html

**Reddit/StockTwits errors**
Rate limits — non-critical, analysis continues without them.

---

## License

MIT

---
---

# Русская версия

## Краткое начало

```bash
git clone https://github.com/arcnosixta/TradingAgents.git
cd TradingAgents
pip install .
```

## Установка OpenCode

Рекомендуемый пайплайн использует [OpenCode](https://opencode.ai) — бесплатный open-source AI агент для кода. Установите его на своей платформе:

### Linux

```bash
# Любая дистрибуция (curl установщик)
curl -fsSL https://opencode.ai/install | bash

# Arch / Manjaro (AUR)
paru -S opencode
```

Или установите **Desktop приложение** (Beta):
- `.deb` — Ubuntu/Debian: `sudo dpkg -i opencode-desktop-linux-x64.deb`
- `.rpm` — Fedora/RHEL: `sudo rpm -i opencode-desktop-linux-x64.rpm`

### macOS

```bash
# Homebrew (рекомендуется)
brew install anomalyco/tap/opencode

# Или Desktop приложение
brew install --cask opencode-desktop
```

Прямая загрузка: [Apple Silicon](https://opencode.ai/download/stable/darwin-aarch64-dmg) | [Intel](https://opencode.ai/download/stable/darwin-x64-dmg)

### Windows

Скачайте установщик: [opencode-desktop-windows-x64.exe](https://opencode.ai/download/stable/windows-x64-nsis)

Или установите через менеджеры пакетов:

```powershell
# npm
npm i -g opencode-ai

# bun
bun add -g opencode-ai
```

### Расширения для IDE

OpenCode также работает как расширение в вашем редакторе:

| Редактор | Установка |
|----------|-----------|
| VS Code | [opencode.ai/docs/ide](https://opencode.ai/docs/ide/) |
| Cursor | [opencode.ai/docs/ide](https://opencode.ai/docs/ide/) |
| Zed | [opencode.ai/docs/ide](https://opencode.ai/docs/ide/) |
| Windsurf | [opencode.ai/docs/ide](https://opencode.ai/docs/ide/) |
| VSCodium | [opencode.ai/docs/ide](https://opencode.ai/docs/ide/) |

---

## Два способа запуска

### 1. OpenCode пайплайн (рекомендуется)

Запускает 12 агентов через OpenCode CLI с бесплатными моделями. **API ключи не нужны.**

```bash
cd opencode_pipeline
python orchestrator.py              # XAU-USD (по умолчанию)
python orchestrator.py BTC-USD      # Биткоин
python orchestrator.py AAPL         # Apple
python orchestrator.py --trade_date 2026-07-03
```

Результаты сохраняются в `runs/<TICKER>_<DATE>_<TIMESTAMP>/reports/`.

### 2. LangGraph пайплайн (оригинальный)

Использует прямые API вызовы LLM. Требуется API ключ.

```bash
tradingagents                        # интерактивный CLI
python -m cli.main                   # альтернатива
```

Или программно:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())
_, decision = ta.propagate("NVDA", "2026-01-15")
```

---

## Как работает OpenCode пайплайн

1. **Сбор данных** — загружает OHLCV, индикаторы, новости,_sentiment, макро-данные через Yahoo Finance
2. **12 AI агентов** — каждый читает файлы данных и пишет отчёт
3. **Правила согласования** — трейдер и портфельный менеджер должны согласовываться с рейтингом исследовательского менеджера
4. **Финальное решение** — вход, стоп-лосс, тейк-профит, размер лота для MetaTrader5

### Агенты

| # | Агент | Роль |
|---|-------|------|
| 1 | Маркет аналитик | Технический анализ H1/H4, уровни поддержки/сопротивления |
| 2 | Сентимент аналитик | Оценка sentiment новостей, Reddit, StockTwits |
| 3 | Ньюс аналитик | Макро-события, центральные банки, геополитика |
| 4 | Фундаментальный аналитик | Финансы компаний (только акции) |
| 5 | Smart Money 4H | Структура старшего таймфрейма, ордер блоки, зоны ликвидности |
| 6 | Smart Money 15M | Интрадей микро-структуры, зоны входа, профиль объёма |
| 7 | Бычий исследователь | Аргументы ЗА покупку |
| 8 | Медвежий исследователь | Аргументы ПРОТИВ покупки |
| 9 | Исследовательский менеджер | Финальный рейтинг на основе дебатов быков и медведей |
| 10 | Трейдер | Вход/стоп/тейк-профит для MT5 |
| 11 | Агрессивный риск | Анализ максимального апсайда |
| 12 | Консервативный риск | Сохранение капитала |
| 13 | Нейтральный риск | Сбалансированная оценка |
| 14 | Портфельный менеджер | Финальное решение с размером лота |

---

## Поддерживаемые инструменты

Любой тикер из Yahoo Finance:

| Рынок | Примеры |
|-------|---------|
| Акции США | `AAPL`, `SPY`, `NVDA` |
| Золото | `XAU-USD`, `XAUUSD`, `GOLD` |
| Серебро | `XAG-USD`, `XAGUSD` |
| Форекс | `EURUSD`, `GBPJPY` |
| Крипто | `BTC-USD`, `ETH-USD` |
| Индексы | `SPX500`, `NAS100`, `US30` |
| Нефть | `WTICOUSD`, `BCOUSD` |

---

## Конфигурация

### Настройки по умолчанию (`opencode.json`)

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "opencode/mimo-v2.5-free"
}
```

Измените модель, отредактировав этот файл или передав `-m provider/model` в `opencode run`.

### Переменные окружения (LangGraph пайплайн)

```bash
# Провайдеры LLM (выберите один)
export OPENAI_API_KEY=...
export GOOGLE_API_KEY=...
export ANTHROPIC_API_KEY=...
export DEEPSEEK_API_KEY=...

# Источники данных (необязательно)
export ALPHA_VANTAGE_API_KEY=...
export FRED_API_KEY=...
```

### Docker

```bash
cp .env.example .env    # добавьте API ключи
docker compose run --rm tradingagents
```

### Веб-dashboard

Визуальный интерфейс для просмотра прошлых анализов, отслеживания прогресса и запуска новых.

```bash
pip install ".[web]"
python run_web.py
# → http://localhost:8000
```

Возможности:
- Дашборд со всеми прошлыми анализами (тикер, статус, рейтинг)
- Детальный просмотр отчётов (все 12 выводов агентов)
- Запуск новых анализов прямо из браузера
- Отслеживание прогресса в реальном времени

---

## Структура проекта

```
TradingAgents/
├── opencode_pipeline/           # Пайплайн на основе OpenCode
│   ├── orchestrator.py          # Главная точка входа
│   ├── data_collector.py        # Фаза 0: сбор всех данных
│   ├── agent_runner.py          # Запуск OpenCode CLI для каждого агента
│   └── prompts/                 # 12 шаблонов промптов агентов
├── tradingagents/               # Основная библиотека (LangGraph пайплайн)
│   ├── agents/                  # Определения агентов
│   ├── dataflows/               # Адаптеры источников данных
│   ├── graph/                   # Оркестрация LangGraph
│   └── llm_clients/             # Абстракция провайдеров LLM
├── web/                         # Веб-dashboard
│   ├── app.py                   # FastAPI приложение
│   ├── scanner.py               # Парсинг директории runs/
│   ├── runner.py                # Фоновый запуск анализов
│   ├── templates/               # HTML шаблоны
│   └── static/                  # CSS + JS
├── cli/                         # Интерактивный CLI
├── tests/                       # Тесты
├── run_web.py                   # Точка входа веб-dashboard
└── opencode.json                # Конфиг OpenCode (mimo-v2.5-free)
```

---

## Решение проблем

**"No module named tradingagents"**
```bash
pip install -e .    # editable установка из корня проекта
```

**OHLCV данные показывают нули**
Убедитесь, что установили локально: `pip install -e .` (не из PyPI).

**Ошибки макро-данных (FRED_API_KEY)**
Получите бесплатный ключ на https://fred.stlouisfed.org/docs/api/api_key.html

**Ошибки Reddit/StockTwits**
Лимиты запросов — некритично, анализ продолжается без них.

---

## Лицензия

MIT
