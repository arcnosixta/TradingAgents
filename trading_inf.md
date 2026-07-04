# TradingAgents — OpenCode Refactoring: Full Instruction

> **Цель**: Заменить LangGraph + LLM API архитектуру на систему, где каждый агент — это отдельный сеанс OpenCode (Claude Opus 4 с thinking). Агенты общаются через файлы. Оркестрация — простой Python-скрипт.

---

## 1. Расположение проекта

```
Путь:    /home/arcnosixta/TradingAgents/
Граф:    Проиндексирован в codebase-memory-mcp как "home-arcnosixta-TradingAgents"
Язык:    Python 3.12+
Стек:    LangGraph, LangChain, yfinance, stockstats, FRED API, Polymarket, Reddit RSS, StockTwits
```

### Ключевые директории

```
tradingagents/
├── agents/
│   ├── analysts/          # 4 аналитика (market, fundamentals, news, sentiment)
│   ├── researchers/       # bull_researcher, bear_researcher
│   ├── risk_mgmt/         # aggressive, conservative, neutral debators
│   ├── trader/            # trader.py
│   ├── managers/          # research_manager, portfolio_manager
│   ├── schemas.py         # Pydantic: ResearchPlan, TraderProposal, PortfolioDecision, SentimentReport
│   └── utils/
│       ├── agent_states.py      # AgentState, InvestDebateState, RiskDebateState
│       ├── agent_utils.py       # resolve_instrument_identity, build_instrument_context
│       ├── structured.py        # bind_structured, invoke_structured_or_freetext
│       ├── memory.py            # TradingMemoryLog
│       ├── rating.py            # parse_rating()
│       ├── core_stock_tools.py  # @tool get_stock_data
│       ├── technical_indicators_tools.py  # @tool get_indicators
│       ├── fundamental_data_tools.py      # @tool get_fundamentals, balance_sheet, cashflow, income
│       ├── news_data_tools.py             # @tool get_news, get_global_news, get_insider_transactions
│       ├── macro_data_tools.py            # @tool get_macro_indicators
│       ├── prediction_markets_tools.py    # @tool get_prediction_markets
│       └── market_data_validation_tools.py # @tool get_verified_market_snapshot
├── dataflows/
│   ├── interface.py             # route_to_vendor() — маршрутизатор данных
│   ├── y_finance.py             # Yahoo Finance: OHLCV, fundamentals, financials
│   ├── yfinance_news.py         # Yahoo Finance news
│   ├── alpha_vantage_*.py       # Alpha Vantage: stock, indicators, fundamentals, news
│   ├── fred.py                  # FRED макро-данные
│   ├── polymarket.py            # Prediction markets
│   ├── reddit.py                # Reddit RSS (r/wallstreetbets, r/stocks, r/investing)
│   ├── stocktwits.py            # StockTwits API
│   ├── stockstats_utils.py      # Кэширование OHLCV, расчёт индикаторов
│   ├── symbol_utils.py          # Нормализация тикеров (XAUUSD→GC=F, BTC→BTC-USD)
│   └── market_data_validator.py # Верификация данных
├── graph/
│   ├── trading_graph.py         # TradingAgentsGraph — главный класс
│   ├── setup.py                 # GraphSetup — сборка StateGraph
│   ├── propagation.py           # create_initial_state()
│   ├── conditional_logic.py     # Условные переходы (tool_calls?, debate_count?)
│   ├── analyst_execution.py     # Порядок аналитиков
│   ├── signal_processing.py     # Извлечение рейтинга
│   ├── reflection.py            # Рефлексия по прошлым решениям
│   └── checkpointer.py          # SQLite checkpoint для crash recovery
├── llm_clients/
│   ├── base_client.py           # BaseLLMClient ABC
│   ├── factory.py               # create_llm_client(provider, model)
│   ├── openai_client.py         # OpenAI + 16 совместимых провайдеров
│   ├── anthropic_client.py      # Claude
│   ├── google_client.py         # Gemini
│   ├── azure_client.py          # Azure OpenAI
│   ├── bedrock_client.py        # AWS Bedrock
│   ├── capabilities.py          # Таблица возможностей моделей
│   └── model_catalog.py         # Каталог моделей для CLI
├── cli/
│   └── main.py                  # Typer CLI с Rich dashboard
├── config/
│   └── default_config.py        # Вся конфигурация + env overrides
└── web_app.py                   # Flask веб-интерфейс (14 эндпоинтов)
```

---

## 2. Текущая архитектура (что заменяем)

### Pipeline (последовательность выполнения)

```
1. Resolve pending memory entries (рефлексия по прошлым решениям)
2. Build initial state (тикер + дата + память + instrument_context)
3. Execute LangGraph:
   a. Market Analyst    ◄──► tools (loop) → clear messages
   b. Sentiment Analyst (pre-fetch Reddit/StockTwits/News → prompt) → clear messages
   c. News Analyst      ◄──► tools (loop) → clear messages
   d. Fundamentals      ◄──► tools (loop) → clear messages
   e. Bull Researcher ◄──► Bear Researcher (N раундов, default N=1)
   f. Research Manager (deep LLM) → investment_plan
   g. Trader → trader_investment_plan
   h. Aggressive ──► Conservative ──► Neutral (N раундов, default N=1)
   i. Portfolio Manager (deep LLM) → final_trade_decision
4. Store decision in memory log
5. Extract rating (parse_rating → Buy/Overweight/Hold/Underweight/Sell)
6. Return (final_state, rating)
```

### Два уровня LLM

- **quick_think_llm** — для 10 из 12 агентов + Reflector + SignalProcessor
- **deep_think_llm** — только Research Manager и Portfolio Manager

### Три паттерна вызова LLM

| Паттерн | Агенты | Как работает |
|---------|--------|-------------|
| Tool-calling loop | Market, Fundamentals, News | `prompt \| llm.bind_tools(tools)` → loop пока есть tool_calls |
| Structured output | Sentiment, Research Mgr, Trader, Portfolio Mgr | `llm.with_structured_output(Schema)` → Pydantic → render to markdown |
| Plain invoke | Bull, Bear, Aggressive, Conservative, Neutral | `llm.invoke(prompt)` → свободный текст |

---

## 3. Новая архитектура (что строим)

### Концепция

Каждый агент = отдельный вызов OpenCode CLI. Агенты общаются через файлы в рабочей директории. Python-скрипт-оркестратор запускает агентов последовательно.

```
┌─────────────────────────────────────────────────────────┐
│                    orchestrator.py                        │
│                                                          │
│   1. Собирает данные (вызывает Python-функции напрямую)  │
│   2. Запускает OpenCode для каждой роли                  │
│   3. Читает результаты из файлов                         │
│   4. Передаёт контекст следующему агенту                 │
│   5. Сохраняет финальное решение                         │
│                                                          │
└─────────────────────────────────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
    [OpenCode #1]  [OpenCode #2]  [OpenCode #N]
    Market Analyst  Sentiment     ... Portfolio Mgr
         │              │              │
         ▼              ▼              ▼
    reports/         reports/       reports/
    market.md        sentiment.md   final_decision.md
```

### Преимущества перед текущей архитектурой

1. **Thinking mode** — каждый агент "думает" перед ответом (extended thinking)
2. **Доступ к интернету** — Google Search для свежих новостей в реальном времени
3. **Самокоррекция** — OpenCode может перепроверить свои выводы
4. **Всегда Opus 4** — максимальное качество для каждого агента
5. **Нет расхода API-токенов** — подписка покрывает всё

---

## 4. Детальный план реализации

### Фаза 0: Подготовка данных (БЕЗ LLM)

Оркестратор должен **сам** собрать все данные Python-функциями, а потом передать их агентам. Это критически важно — мы не хотим, чтобы OpenCode сам вызывал Yahoo Finance API.

```python
# orchestrator.py — Phase 0
from tradingagents.dataflows.y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as yf_get_fundamentals,
    get_balance_sheet, get_cashflow, get_income_statement,
)
from tradingagents.dataflows.yfinance_news import get_news_yfinance, get_global_news_yfinance
from tradingagents.dataflows.fred import get_macro_data
from tradingagents.dataflows.polymarket import get_prediction_markets as pm_get
from tradingagents.dataflows.reddit import fetch_reddit_posts
from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages
from tradingagents.dataflows.market_data_validator import build_verified_market_snapshot
from tradingagents.agents.utils.agent_utils import resolve_instrument_identity, build_instrument_context

# Собрать ВСЕ данные заранее:
ohlcv = get_YFin_data_online(ticker, start_date, end_date)
indicators = {}
for ind in ["close_50_sma", "close_200_sma", "close_10_ema", "macd", "macds", "macdh", "rsi", "boll", "boll_ub", "boll_lb", "atr"]:
    indicators[ind] = get_stock_stats_indicators_window(ticker, ind, trade_date, 30)
fundamentals = yf_get_fundamentals(ticker)
balance = get_balance_sheet(ticker, "quarterly")
cashflow = get_cashflow(ticker, "quarterly")
income = get_income_statement(ticker, "quarterly")
news = get_news_yfinance(ticker, start_date, end_date)
global_news = get_global_news_yfinance(trade_date)
macro = {ind: get_macro_data(ind, trade_date) for ind in ["fed_funds_rate", "cpi", "unemployment", "10y_treasury", "vix"]}
prediction_mkts = pm_get("topic_related_to_ticker")
reddit = fetch_reddit_posts(ticker)
stocktwits = fetch_stocktwits_messages(ticker)
snapshot = build_verified_market_snapshot(ticker, trade_date)
identity = resolve_instrument_identity(ticker)
instrument_context = build_instrument_context(ticker, "stock", identity)

# Записать всё в файлы
write_to_file("data/ohlcv.md", ohlcv)
write_to_file("data/indicators.md", format_indicators(indicators))
write_to_file("data/fundamentals.md", fundamentals)
# ... и т.д.
```

### Фаза 1: Аналитики (4 вызова OpenCode)

Каждый аналитик получает:
- Свои данные (из data/)
- Instrument context
- Дату анализа
- Инструкцию "напиши отчёт в reports/{name}.md"

#### 1a. Market Analyst

```
# Промпт для OpenCode:
Ты Market Analyst. Проанализируй технические данные для {ticker} на {trade_date}.

Данные OHLCV: [содержимое data/ohlcv.md]
Технические индикаторы: [содержимое data/indicators.md]
Верифицированный снимок: [содержимое data/snapshot.md]

{instrument_context}

ЗАДАЧА: Напиши детальный отчёт о трендах. Включи:
- Анализ каждого индикатора
- Уровни поддержки/сопротивления
- Направление тренда
- Конкретные actionable insights

В конце добавь Markdown-таблицу с ключевыми точками.

Запиши результат в файл reports/market.md
```

#### 1b. Sentiment Analyst

```
# Промпт для OpenCode:
Ты Sentiment Analyst для {ticker} за период {start_date} - {end_date}.

Новости Yahoo Finance:
[содержимое data/news.md]

StockTwits:
[содержимое data/stocktwits.md]

Reddit (r/wallstreetbets, r/stocks, r/investing):
[содержимое data/reddit.md]

{instrument_context}

ЗАДАЧА: Проведи анализ настроений. Определи:
- overall_band: Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish
- overall_score: 0.0-10.0 (5 = neutral)
- confidence: low / medium / high
- narrative: подробный разбор по каждому источнику

Формат вывода (JSON в начале файла, затем narrative):
```json
{
  "overall_band": "...",
  "overall_score": 0.0,
  "confidence": "..."
}
```

Далее полный narrative.

Используй Google Search для проверки последних событий если нужно.

Запиши результат в файл reports/sentiment.md
```

#### 1c. News Analyst

```
# Промпт для OpenCode:
Ты News Analyst.

Новости по {ticker}: [data/news.md]
Глобальные новости: [data/global_news.md]
Макроданные FRED: [data/macro.md]
Prediction Markets (Polymarket): [data/predictions.md]

{instrument_context}

ЗАДАЧА: Напиши комплексный отчёт о новостном фоне:
- Ключевые события по тикеру
- Макроэкономический контекст (ФРС, инфляция, рынок труда)
- Геополитические риски
- Вероятности с prediction markets

Используй Google Search чтобы найти САМЫЕ СВЕЖИЕ новости за сегодня.

Запиши результат в файл reports/news.md
```

#### 1d. Fundamentals Analyst

```
# Промпт для OpenCode:
Ты Fundamentals Analyst.

Профиль компании: [data/fundamentals.md]
Balance Sheet: [data/balance_sheet.md]
Cash Flow: [data/cashflow.md]
Income Statement: [data/income.md]

{instrument_context}

ЗАДАЧА: Напиши комплексный фундаментальный отчёт:
- Финансовое здоровье
- Маржинальность и рентабельность
- Долговая нагрузка
- Рост выручки
- Сравнение с сектором

Запиши результат в файл reports/fundamentals.md
```

### Фаза 2: Исследование (Bull vs Bear — 2 вызова OpenCode)

#### 2a. Bull Researcher

```
# Промпт для OpenCode:
Ты Bull Analyst. Твоя задача — построить сильный аргумент ЗА инвестирование в {ticker}.

Прочитай все отчёты аналитиков:
- reports/market.md
- reports/sentiment.md
- reports/news.md
- reports/fundamentals.md

{instrument_context}

Построй compelling case:
- Потенциал роста
- Конкурентные преимущества
- Позитивные индикаторы
- Контраргументы к рискам

Запиши результат в файл reports/bull_case.md
```

#### 2b. Bear Researcher

```
# Промпт для OpenCode:
Ты Bear Analyst. Твоя задача — построить аргумент ПРОТИВ инвестирования в {ticker}.

Прочитай все отчёты аналитиков:
- reports/market.md
- reports/sentiment.md
- reports/news.md
- reports/fundamentals.md

А также аргумент Bull аналитика:
- reports/bull_case.md

{instrument_context}

Построй compelling case:
- Риски и угрозы
- Конкурентные слабости
- Негативные индикаторы
- Контраргументы к bull case

Запиши результат в файл reports/bear_case.md
```

### Фаза 3: Research Manager (1 вызов OpenCode)

```
# Промпт для OpenCode:
Ты Research Manager. Оцени дебаты bull/bear и вынеси решение.

Прочитай:
- reports/bull_case.md
- reports/bear_case.md
- reports/market.md (для контекста)

{instrument_context}

ЗАДАЧА: Определи рейтинг (РОВНО ОДНО из пяти):
- Buy — сильная уверенность в bull тезисе
- Overweight — позитивный взгляд, постепенно наращивать
- Hold — баланс аргументов
- Underweight — осторожный взгляд, сокращать
- Sell — сильная уверенность в bear тезисе

Формат вывода:
```
RATING: [Buy/Overweight/Hold/Underweight/Sell]

RATIONALE:
[2-3 предложения]

STRATEGIC_ACTIONS:
[конкретные шаги для трейдера]
```

Запиши результат в файл reports/research_plan.md
```

### Фаза 4: Trader (1 вызов OpenCode)

```
# Промпт для OpenCode:
Ты Trader. На основе research plan прими торговое решение.

Прочитай:
- reports/research_plan.md
- reports/market.md (технические уровни для entry/stop-loss)

{instrument_context}

ЗАДАЧА: Определи действие (РОВНО ОДНО из трёх):
- Buy
- Hold
- Sell

Формат вывода:
```
ACTION: [Buy/Hold/Sell]

REASONING:
[2-4 предложения, привязанные к отчётам аналитиков]

ENTRY_PRICE: [число или N/A]
STOP_LOSS: [число или N/A]
POSITION_SIZING: [например "5% of portfolio" или N/A]
```

Запиши результат в файл reports/trader_proposal.md
```

### Фаза 5: Risk Debate (3 вызова OpenCode)

#### 5a. Aggressive Risk Analyst

```
# Промпт для OpenCode:
Ты Aggressive Risk Analyst. Защищай высокодоходные возможности.

Прочитай:
- reports/trader_proposal.md
- reports/market.md
- reports/sentiment.md
- reports/news.md
- reports/fundamentals.md

{instrument_context}

ЗАДАЧА: Построй аргумент за агрессивный подход к решению трейдера.
Фокусируйся на потенциале upside, growth, инновациях.

Запиши результат в файл reports/risk_aggressive.md
```

#### 5b. Conservative Risk Analyst

```
# Промпт для OpenCode:
Ты Conservative Risk Analyst. Защищай активы и минимизируй волатильность.

Прочитай:
- reports/trader_proposal.md
- reports/risk_aggressive.md
- reports/market.md, sentiment.md, news.md, fundamentals.md

{instrument_context}

ЗАДАЧА: Критикуй агрессивный подход. Укажи на риски, потенциальные потери.
Предложи консервативные альтернативы.

Запиши результат в файл reports/risk_conservative.md
```

#### 5c. Neutral Risk Analyst

```
# Промпт для OpenCode:
Ты Neutral Risk Analyst. Взвесь обе стороны.

Прочитай:
- reports/trader_proposal.md
- reports/risk_aggressive.md
- reports/risk_conservative.md
- reports/market.md, sentiment.md, news.md, fundamentals.md

{instrument_context}

ЗАДАЧА: Дай сбалансированную оценку. Укажи слабости обоих подходов.
Предложи оптимальный средний путь.

Запиши результат в файл reports/risk_neutral.md
```

### Фаза 6: Portfolio Manager (1 вызов OpenCode — ФИНАЛЬНОЕ РЕШЕНИЕ)

```
# Промпт для OpenCode:
Ты Portfolio Manager. Вынеси ФИНАЛЬНОЕ торговое решение.

Прочитай ВСЁ:
- reports/research_plan.md
- reports/trader_proposal.md
- reports/risk_aggressive.md
- reports/risk_conservative.md
- reports/risk_neutral.md

Также прочитай память прошлых решений:
- data/past_context.md (если существует)

{instrument_context}

ЗАДАЧА: Определи финальный рейтинг:
- Buy — сильная уверенность, входить в позицию
- Overweight — позитивно, наращивать
- Hold — держать текущую позицию
- Underweight — сокращать
- Sell — выходить

Формат:
```
RATING: [Buy/Overweight/Hold/Underweight/Sell]

EXECUTIVE_SUMMARY:
[план действий, 2-4 предложения]

INVESTMENT_THESIS:
[детальное обоснование с доказательствами]

PRICE_TARGET: [число или N/A]
TIME_HORIZON: [например "3-6 months" или N/A]
```

Запиши результат в файл reports/final_decision.md
```

---

## 5. Структура файлов новой системы

```
/home/arcnosixta/TradingAgents/
├── opencode_pipeline/                  # НОВАЯ ДИРЕКТОРИЯ
│   ├── orchestrator.py                 # Главный скрипт
│   ├── data_collector.py              # Сбор данных (Phase 0)
│   ├── agent_runner.py                # Запуск OpenCode subprocess
│   ├── prompts/                       # Шаблоны промптов
│   │   ├── market_analyst.md
│   │   ├── sentiment_analyst.md
│   │   ├── news_analyst.md
│   │   ├── fundamentals_analyst.md
│   │   ├── bull_researcher.md
│   │   ├── bear_researcher.md
│   │   ├── research_manager.md
│   │   ├── trader.md
│   │   ├── risk_aggressive.md
│   │   ├── risk_conservative.md
│   │   ├── risk_neutral.md
│   │   └── portfolio_manager.md
│   └── config.py                      # Настройки пайплайна
│
├── runs/                              # Результаты запусков (gitignored)
│   └── {ticker}_{date}_{timestamp}/
│       ├── data/                      # Собранные данные
│       │   ├── ohlcv.md
│       │   ├── indicators.md
│       │   ├── fundamentals.md
│       │   ├── balance_sheet.md
│       │   ├── cashflow.md
│       │   ├── income.md
│       │   ├── news.md
│       │   ├── global_news.md
│       │   ├── macro.md
│       │   ├── predictions.md
│       │   ├── reddit.md
│       │   ├── stocktwits.md
│       │   ├── snapshot.md
│       │   └── past_context.md
│       ├── reports/                   # Отчёты агентов
│       │   ├── market.md
│       │   ├── sentiment.md
│       │   ├── news.md
│       │   ├── fundamentals.md
│       │   ├── bull_case.md
│       │   ├── bear_case.md
│       │   ├── research_plan.md
│       │   ├── trader_proposal.md
│       │   ├── risk_aggressive.md
│       │   ├── risk_conservative.md
│       │   ├── risk_neutral.md
│       │   └── final_decision.md
│       └── run_log.json               # Лог запуска (тайминги, статусы)
│
├── tradingagents/                     # СУЩЕСТВУЮЩИЙ КОД (не трогаем!)
│   ├── dataflows/                     # Переиспользуем для сбора данных
│   └── agents/utils/memory.py         # Переиспользуем для памяти
└── trading_inf.md                     # Этот файл
```

---

## 6. Как запускать OpenCode из Python

### Вариант A: subprocess (рекомендуемый)

```python
import subprocess
import os

def run_opencode_agent(prompt_file: str, work_dir: str, timeout: int = 600) -> str:
    """
    Запускает OpenCode с промптом из файла.
    OpenCode работает в work_dir и может создавать/читать файлы там.
    """
    with open(prompt_file, "r") as f:
        prompt = f.read()

    result = subprocess.run(
        ["opencode", "--prompt", prompt],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ}  # наследуем API ключи из .env
    )

    if result.returncode != 0:
        raise RuntimeError(f"OpenCode failed: {result.stderr}")

    return result.stdout
```

> **ВАЖНО**: Точный синтаксис CLI opencode надо уточнить. Возможные варианты:
> - `opencode --prompt "текст"` — промпт как аргумент
> - `echo "текст" | opencode` — через stdin
> - `opencode -f prompt.md` — из файла
> - `opencode --non-interactive --prompt "текст"` — non-interactive режим
>
> **Первый шаг реализации**: проверить `opencode --help` и найти правильный способ non-interactive запуска.

### Вариант B: Через opencode.json конфигурацию

Можно настроить `opencode.json` в work_dir каждого запуска с нужными параметрами:

```json
{
  "model": "antigravity-claude-opus-4-6-thinking",
  "systemPrompt": "Ты {role}. {instructions}",
  "tools": {
    "bash": true,
    "read": true,
    "write": true,
    "webfetch": true,
    "google_search": true
  }
}
```

---

## 7. Данные: что собирать и как

### Источники данных (переиспользуем существующий код)

| Источник | Модуль | API Key | Бесплатный? |
|----------|--------|---------|-------------|
| Yahoo Finance | `dataflows/y_finance.py` | Нет | Да |
| Yahoo Finance News | `dataflows/yfinance_news.py` | Нет | Да |
| Alpha Vantage | `dataflows/alpha_vantage_*.py` | `ALPHA_VANTAGE_API_KEY` | Freemium |
| FRED | `dataflows/fred.py` | `FRED_API_KEY` | Да (бесплатный ключ) |
| Polymarket | `dataflows/polymarket.py` | Нет | Да |
| Reddit | `dataflows/reddit.py` | Нет | Да (RSS) |
| StockTwits | `dataflows/stocktwits.py` | Нет | Да |

### Symbol normalization

Тикеры нормализуются через `dataflows/symbol_utils.py`:
- Металлы: XAUUSD → GC=F, XAGUSD → SI=F
- Криптo: BTC/BTCUSD/BTCUSDT → BTC-USD
- Форекс: EURUSD → EURUSD=X
- Индексы: SPX500 → ^GSPC

### Кэширование

OHLCV данные кэшируются в `~/.tradingagents/cache/{SYMBOL}-YFin-data-{start}-{end}.csv`. При повторном запуске данные берутся из кэша.

---

## 8. Память (переиспользуем)

Файл: `tradingagents/agents/utils/memory.py` — класс `TradingMemoryLog`

Хранилище: `~/.tradingagents/memory/trading_memory.md`

### Формат записи

```markdown
[2024-05-10 | NVDA | Buy | +3.2% | +1.1% | 5d]

DECISION:
Rating: Buy
...полный текст решения Portfolio Manager...

REFLECTION:
...2-4 предложения о том, что пошло правильно/неправильно...

<!-- ENTRY_END -->
```

### Функции для переиспользования

```python
from tradingagents.agents.utils.memory import TradingMemoryLog

memory = TradingMemoryLog(config)

# Получить контекст прошлых решений для промпта
past_context = memory.get_past_context(ticker, n_same=5, n_cross=3)

# Сохранить новое решение (после финала)
memory.store_decision(ticker, trade_date, final_decision_text)

# Обновить outcome (при следующем запуске)
memory.update_with_outcome(ticker, trade_date, actual_return, alpha, horizon)
```

---

## 9. Конфигурация

Текущая конфигурация в `config/default_config.py`. Ключевые параметры для новой системы:

```python
config = {
    # Pipeline
    "selected_analysts": ["market", "social", "news", "fundamentals"],
    "max_debate_rounds": 1,        # Bull/Bear раунды
    "max_risk_discuss_rounds": 1,  # Risk debate раунды

    # Data
    "data_vendors": {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
        "macro_data": "fred",
        "prediction_markets": "polymarket",
    },
    "news_article_limit": 20,
    "global_news_lookback_days": 7,
    "global_news_article_limit": 10,

    # Memory
    "memory_enabled": True,
    "memory_log_max_entries": None,  # без ограничений

    # Output language
    "output_language": "en",  # или "ru", "kk"
}
```

---

## 10. Пошаговый план работы (для следующей сессии)

### Шаг 1: Проверить CLI opencode
```bash
opencode --help
# Найти non-interactive режим, способ передачи промпта
```

### Шаг 2: Создать структуру
```bash
mkdir -p /home/arcnosixta/TradingAgents/opencode_pipeline/prompts
```

### Шаг 3: Написать data_collector.py
- Импортировать функции из `tradingagents/dataflows/`
- Собрать все данные для тикера
- Записать в `runs/{ticker}_{date}/data/`

### Шаг 4: Написать agent_runner.py
- Функция `run_agent(role, prompt_template, data_dir, reports_dir)`
- Подставляет данные в шаблон
- Запускает opencode subprocess
- Проверяет что output файл создан

### Шаг 5: Написать промпты
- 12 файлов в `prompts/` (по одному на каждую роль)
- Шаблоны с `{ticker}`, `{trade_date}`, `{instrument_context}` плейсхолдерами

### Шаг 6: Написать orchestrator.py
- Main script: принимает тикер и дату
- Запускает Phase 0-6 последовательно
- Логирует прогресс
- Сохраняет в memory

### Шаг 7: Тестирование
- Запустить для NVDA, AAPL, BTC
- Сравнить качество с текущей системой
- Измерить время выполнения

---

## 11. Критические замечания

### Что НЕЛЬЗЯ делать

1. **Не ломать существующий код** — `tradingagents/` не трогаем, только переиспользуем dataflows и memory
2. **Не хардкодить данные** — всегда собирать через API
3. **Не удалять LangGraph версию** — она остаётся как fallback
4. **Не забывать instrument_context** — каждый агент должен знать тикер, сектор, тип актива

### Возможные проблемы

1. **OpenCode CLI синтаксис** — надо проверить точный способ non-interactive запуска
2. **Размер промптов** — OHLCV данные за год могут быть огромными, надо обрезать до нужного окна
3. **Таймауты** — один агент может работать 2-10 минут, надо выставить большие таймауты
4. **Ошибки парсинга** — агент может не создать файл или создать его в неправильном формате
5. **Rate limits** — если OpenCode имеет лимиты на запросы, 12 последовательных вызовов могут быть проблемой

### Fallback стратегия

Если OpenCode CLI не поддерживает non-interactive режим, альтернативы:
1. **HTTP proxy** — написать FastAPI сервер, который принимает промпт и возвращает ответ через Anthropic API напрямую
2. **Anthropic API с thinking** — использовать `anthropic.messages.create(model="claude-opus-4", thinking={"type": "enabled"})` — тот же Opus 4 с thinking, но через API
3. **Оставить как есть** — просто заменить модели на дешёвые (Haiku для аналитиков, Opus для менеджеров)

---

## 12. Граф знаний (codebase-memory-mcp)

Проект проиндексирован. Для навигации по коду:

```
project: "home-arcnosixta-TradingAgents"

# Найти функцию
search_graph(query="market analyst", project="home-arcnosixta-TradingAgents")

# Посмотреть кто вызывает функцию
trace_path(function_name="create_market_analyst", direction="inbound", project="home-arcnosixta-TradingAgents")

# Прочитать код функции
get_code_snippet(qualified_name="tradingagents.agents.analysts.market_analyst.create_market_analyst", project="home-arcnosixta-TradingAgents")

# Архитектура
get_architecture(project="home-arcnosixta-TradingAgents")
```

---

## 13. Полные системные промпты агентов (справочник)

Сохранены ниже для точного воспроизведения логики в новых промптах.

### Market Analyst (оригинал)

> You are a trading assistant tasked with analyzing financial markets. Your role is to select the most relevant indicators for a given market condition...
> [Полный текст из agents/analysts/market_analyst.py — ~800 слов, включает описания 12 индикаторов, инструкции по get_verified_market_snapshot]

### Sentiment Analyst (оригинал)

> You are a financial market sentiment analyst. Your task is to produce a comprehensive sentiment report for {ticker}...
> [Полный текст из agents/analysts/sentiment_analyst.py — ~1000 слов, включает блоки <start_of_news>, <start_of_stocktwits>, <start_of_reddit>, 8 best practices, описания полей вывода]

### News Analyst (оригинал)

> You are a news researcher tasked with analyzing recent news and trends over the past week...
> [Из agents/analysts/news_analyst.py]

### Fundamentals Analyst (оригинал)

> You are a researcher tasked with analyzing fundamental information over the past week about a company...
> [Из agents/analysts/fundamentals_analyst.py]

### Bull Researcher (оригинал)

> You are a Bull Analyst advocating for investing in the {target_label}...
> [Из agents/researchers/bull_researcher.py — ~200 слов, 5 ключевых точек]

### Bear Researcher (оригинал)

> You are a Bear Analyst making the case against investing in the {target_label}...
> [Из agents/researchers/bear_researcher.py — ~200 слов, 5 ключевых точек]

### Research Manager (оригинал)

> As the Research Manager and debate facilitator, your role is to critically evaluate this round of debate...
> [Из agents/managers/research_manager.py — включает 5-tier rating scale]

### Trader (оригинал)

> You are a trading agent analyzing market data to make investment decisions...
> [Из agents/trader/trader.py]

### Aggressive Risk Analyst (оригинал)

> As the Aggressive Risk Analyst, your role is to actively champion high-reward, high-risk opportunities...
> [Из agents/risk_mgmt/aggressive_debator.py — ~300 слов]

### Conservative Risk Analyst (оригинал)

> As the Conservative Risk Analyst, your primary objective is to protect assets, minimize volatility...
> [Из agents/risk_mgmt/conservative_debator.py — ~300 слов]

### Neutral Risk Analyst (оригинал)

> As the Neutral Risk Analyst, your role is to provide a balanced perspective...
> [Из agents/risk_mgmt/neutral_debator.py — ~300 слов]

### Portfolio Manager (оригинал)

> As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision...
> [Из agents/managers/portfolio_manager.py — включает 5-tier rating scale + lessons_line]

---

## 14. Pydantic-схемы (для валидации вывода)

Если нужно парсить структурированный вывод из markdown-файлов агентов:

### ResearchPlan
```python
class PortfolioRating(str, Enum):
    Buy = "Buy"
    Overweight = "Overweight"
    Hold = "Hold"
    Underweight = "Underweight"
    Sell = "Sell"

class ResearchPlan(BaseModel):
    recommendation: PortfolioRating
    rationale: str
    strategic_actions: str
```

### TraderProposal
```python
class TraderAction(str, Enum):
    Buy = "Buy"
    Hold = "Hold"
    Sell = "Sell"

class TraderProposal(BaseModel):
    action: TraderAction
    reasoning: str
    entry_price: float | None = None
    stop_loss: float | None = None
    position_sizing: str | None = None
```

### PortfolioDecision
```python
class PortfolioDecision(BaseModel):
    rating: PortfolioRating
    executive_summary: str
    investment_thesis: str
    price_target: float | None = None
    time_horizon: str | None = None
```

### SentimentReport
```python
class SentimentBand(str, Enum):
    Bullish = "Bullish"
    MildlyBullish = "Mildly Bullish"
    Neutral = "Neutral"
    Mixed = "Mixed"
    MildlyBearish = "Mildly Bearish"
    Bearish = "Bearish"

class SentimentReport(BaseModel):
    overall_band: SentimentBand
    overall_score: float  # 0.0-10.0
    confidence: Literal["low", "medium", "high"]
    narrative: str
```

---

## 15. API Keys (.env)

```bash
# LLM (для текущей системы, не для OpenCode пайплайна)
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...

# Data sources
ALPHA_VANTAGE_API_KEY=...    # Опционально (yfinance — default)
FRED_API_KEY=...             # Бесплатный, нужен для макро-данных

# Всё остальное бесплатное (yfinance, polymarket, reddit, stocktwits)
```

---

## Итого

**Что делаем**: Создаём `opencode_pipeline/` — альтернативный пайплайн, где вместо API-вызовов к LLM каждый агент — это отдельный сеанс OpenCode с Claude Opus 4 + thinking.

**Что переиспользуем**: `tradingagents/dataflows/` (сбор данных), `tradingagents/agents/utils/memory.py` (память решений), `tradingagents/agents/schemas.py` (схемы для парсинга).

**Что НЕ трогаем**: Весь существующий код LangGraph остаётся как есть.

**Первый шаг**: `opencode --help` — проверить non-interactive режим.
