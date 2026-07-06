# TradingAgents — План улучшений (v2)

> Дата: 2026-07-06
> Статус: В ПРОЦЕССЕ
> Контекст: Мы улучшаем систему минимизации потерь + добавляем 2 новых агента (Smart Money анализ)

---

## ЧАСТЬ 1: Исправление существующих агентов (6 улучшений)

### 1.1 Валидация Portfolio Manager (аналогично Trader)

**Проблема:** `final_decision.md` содержит entry/stop без валидации. PM — отдельный LLM вызов, он может выдать stop 650pts или entry на 200pts от текущей цены.

**Решение:**
- Добавить `{current_price}`, `{day_high}`, `{day_low}` в `opencode_pipeline/prompts/portfolio_manager.md`
- Добавить строгие правила (как в trader.md): entry max 30pts от current, stop max 100pts
- В `orchestrator.py` вызывать `apply_validation_to_report()` для `final_decision.md` после PM

**Файлы:**
- `opencode_pipeline/prompts/portfolio_manager.md`
- `opencode_pipeline/orchestrator.py`

### 1.2 Согласование Trader ↔ Portfolio Manager

**Проблема:** Trader говорит entry 4200, PM говорит entry 4255 — 55pts разницы, никто не проверяет.

**Решение:**
- В `entry_validator.py` добавить функцию `validate_consistency(trader_entry, pm_entry, max_diff=20)`
- В `orchestrator.py` после PM: сравнить entry из `trader_proposal.md` и `final_decision.md`
- Если разница > 20pts: подтянуть PM entry к Trader entry (Trader ближе к рынку)
- Записать предупреждение в лог

**Файлы:**
- `tradingagents/agents/utils/entry_validator.py` — новая функция
- `opencode_pipeline/orchestrator.py`

### 1.3 Текущая цена в Risk Analysts

**Проблема:** Aggressive/Conservative/Neutral не знают текущую цену, работают из текста.

**Решение:**
- Добавить `{current_price}` в каждый промпт:
  - `opencode_pipeline/prompts/risk_aggressive.md`
  - `opencode_pipeline/prompts/risk_conservative.md`
  - `opencode_pipeline/prompts/risk_neutral.md`

**Пример добавления:**
```markdown
ТЕКУЩАЯ ЦЕНА: {current_price}
ВСЕ ТВОИ УРОВНИ (entry, stop, TP) ДОЛЖНЫ БЫТЬ В ПРЕДЕЛАХ 100 ПУНКТОВ ОТ ТЕКУЩЕЙ ЦЕНЫ.
```

### 1.4 Автоматический расчёт Lot Size

**Проблема:** "1.5% от депозита" — каждый агент пишет что хочет, нет расчёта.

**Решение:**
- В `entry_validator.py` добавить:
```python
def calculate_lot_size(
    entry_price: float,
    stop_loss: float,
    account_balance: float = 10000.0,
    risk_pct: float = 0.01,  # 1%
    pip_value: float = 1.0,   # для золота $1/pip, для forex $10/lot
) -> float:
    risk_amount = account_balance * risk_pct
    stop_distance = abs(entry_price - stop_loss)
    if stop_distance <= 0:
        return 0.01
    lot_size = risk_amount / (stop_distance * pip_value)
    return round(max(0.01, min(lot_size, 1.0)), 2)
```
- В `portfolio_manager.md` добавить формулу расчёта
- Валидатор автоматически пересчитывает lot если стоп изменён

**Файлы:**
- `tradingagents/agents/utils/entry_validator.py`
- `opencode_pipeline/prompts/portfolio_manager.md`

### 1.5 Trailing Stop правила

**Проблема:** Система выдаёт статичные уровни, не планирует динамическое управление.

**Решение:**
- Добавить секцию в `portfolio_manager.md`:
```markdown
## TRAILING RULES (ОБЯЗАТЕЛЬНО ВКЛЮЧИ В NEXT_ACTION):

1. Если цена в пользу на +30 пунктов → стоп на безубыток (breakeven)
2. Если цена в пользу на +60 пунктов → трейлинг-стоп 20 пунктов за ценой
3. Если сделка не закрылась за 4 часа → рассмотреть закрытие в Market
4. При новостях (NFP, CPI, FOMC) → закрыть позицию за 15 мин до события
```

**Файлы:**
- `opencode_pipeline/prompts/portfolio_manager.md`

### 1.6 ATR-based стоп валидация

**Проблема:** Стоп может быть 30pts при ATR=93 (будет выбиваться шумом) или 300pts при ATR=50 (слишком далеко).

**Решение:**
- В `entry_validator.py` добавить парсинг ATR из `data/indicators.md`:
```python
def parse_atr_from_indicators(indicators_path: str) -> float | None:
    """Parse ATR value from data/indicators.md"""
```
- Валидация стопа:
  - Min стоп = max(20, 0.5 × ATR)  — не меньше 0.5 ATR
  - Max стоп = min(100, 1.5 × ATR) — не больше 1.5 ATR
  - Clamp если вне диапазона
- В `orchestrator.py`: парсить ATR перед валидацией

**Файлы:**
- `tradingagents/agents/utils/entry_validator.py`
- `opencode_pipeline/orchestrator.py`

---

## ЧАСТЬ 2: Два новых агента Smart Money

### Концепция: Smart Money Analysis

Smart Money — это анализ на основе поведения институциональных игроков. Ключевые элементы:
- **Имбалансы (Imbalances)** — разрывы между свечами, куда "тянет" цену
- **Уровни поддержки/сопротивления** — не по индикаторам, а по реальным зонам концентрации ордеров
- **Объём (Volume)** — профиль объёма, volume clusters, volume-weighted уровни
- **Ликвидность** — зоны где скопились стопы крупных игроков
- **Structure** — HH/HL (bullish) или LH/LL (bearish)

### 2.1 Agent: Smart Money 15M (Intraday Micro)

**Временной горизонт:** 15-60 минут (интрадей micro)
**Роль:** Найти точку входа на 15-минутном таймфрейме

**Промпт:** `opencode_pipeline/prompts/smart_money_15m.md`

```markdown
Ты Smart Money Analyst (15M timeframe). Анализируй интрадей micro-структуру.

Прочитай:
- data/ohlcv.md (последние 48 часов на M15)
- data/indicators.md (ATR, RSI, Volume)
- data/snapshot.md
- reports/market.md (для общего контекста)

{instrument_context}

ТЕКУЩАЯ ЦЕНА: {current_price}

## SMART MONEY КОНЦЕПЦИИ (используй эти термины):

### 1. Order Blocks (OB)
- Последняя противоположная свеча перед импульсным движением
- Bullish OB: последняя красная свеча перед сильным ростом
- Bearish OB: последняя зелёная свеча перед сильным падением
- Вход: на возврате к OB с подтверждением (пин-бар, поглощение)

### 2. Fair Value Gaps (FVG) / Imbalances
- Три подряд свечи где тело middle свечи не перекрывается тенями outer свечей
- Bullish FVG: цена вернётся заполнить гэп снизу вверх
- Bearish FVG: цена вернётся заполнить гэп сверху вниз

### 3. Liquidity Zones
- Equal Highs / Equal Lows — зоны где стоят стопы
- Stop Hunt — пробой уровня для забора ликвидности перед разворотом
- Вход: после stop hunt + подтверждение разворота

### 4. Volume Analysis
- Volume spike на развороте = подтверждение
- Low volume на росте = слабый импульс
- Volume profile: POC, VAH, VAL

### 5. Market Structure
- Bullish: HH → HL → HH
- Bearish: LH → LL → LH
- Break of Structure (BOS): пробой предыдущего HH/HL
- Change of Character (CHoCH): смена структуры

## ЗАДАЧА:

1. Определи текущую micro-структуру (bullish/bearish/neutral)
2. Найди ближайшие:
   - Order Block (bullish и bearish)
   - FVG (imbalances)
   - Liquidity zone (equal highs/lows)
3. Определи zone для входа:
   - Entry zone (точная зона, не одна цена)
   - Stop loss (за OB или за liquidity zone)
   - Take profit (к следующему OB/FVG/liquidity)
4. Volume profile: текущий POC, VAH, VAL

## ФОРМАТ ВЫВОДА:

```
STRUCTURE: [Bullish/Bearish/Neutral]

CURRENT_ZONES:
- nearest_bullish_ob: [price range]
- nearest_bearish_ob: [price range]
- fvg: [price range, type: bullish/bearish]
- liquidity_high: [price — equal highs / stop hunt zone]
- liquidity_low: [price — equal lows / stop hunt zone]

ENTRY_SETUP:
- direction: [Buy/Sell]
- entry_zone: [price range — зона входа]
- stop_loss: [price — за OB/liquidity]
- take_profit_1: [price — к ближайшему OB/FVG]
- take_profit_2: [price — к следующему уровню]
- risk_reward: [ratio]
- confidence: [High/Medium/Low]

VOLUME_PROFILE:
- POC: [price]
- VAH: [price]
- VAL: [price]

TRIGGER:
- [Что должно произойти для входа: например "возврат к bullish OB 4180-4185 + пин-бар на M15"]
```

Запиши в файл reports/smart_money_15m.md
```

### 2.2 Agent: Smart Money 4H (Swing)

**Временной горизонт:** 4-24 часа (swing trade)
**Роль:** Определить общую структуру и ключевые уровни на 4H

**Промпт:** `opencode_pipeline/prompts/smart_money_4h.md`

```markdown
Ты Smart Money Analyst (4H timeframe). Анализируй swing-структуру на 4-24 часа.

Прочитай:
- data/ohlcv.md (последние 30 дней на H4)
- data/indicators.md (SMA 50/200, RSI, MACD, ATR)
- data/snapshot.md
- reports/market.md

{instrument_context}

ТЕКУЩАЯ ЦЕНА: {current_price}

## SMART MONEY КОНЦЕПЦИИ (4H適用):

### 1. Higher Timeframe Structure (HTF)
- Определи основной тренд на H4: HH/HL или LH/LL
- BOS (Break of Structure): где произошёл пробой
- CHoCH (Change of Character): где сменился тренд
- Важные уровни: предыдущие HH, HL, LH, LL

### 2. Premium/Discount Zones
- Premium: выше 50% диапазона ( sells только здесь)
- Discount: ниже 50% диапазона (buys только здесь)
- Equilibrium: 50% — зона баланса
- Входы ТОЛЬКО в premium (для sell) или discount (для buy)

### 3. Order Blocks на H4
- H4 OB сильнее чем M15/M1
- Поиск: последняя свеча перед импульсом на H4
- Зона OB: тело свечи ± ATR/4

### 4. Liquidity Pools
- Equal highs/lows на H4 — крупные зоны ликвидности
- Stop hunt перед major levels
- Sweep ликвидности → разворот

### 5. Divergence + Structure
- RSI divergence на H4 = сильный сигнал
- Volume divergence = слабый импульс
- MACD divergence на H4 = разворот вероятен

## ЗАДАЧА:

1. Определи HTF структуру (H4):
   - Текущий тренд (bullish/bearish/range)
   - BOS уровень (где сломалась структура)
   - CHoCH уровень (где сменился тренд)

2. Определи Premium/Discount:
   - Текущая зона (premium/discount/equilibrium)
   - Диапазон: [low — high]

3. Найди ключевые уровни:
   - H4 Order Block (bullish): [price range]
   - H4 Order Block (bearish): [price range]
   - Liquidity pool highs: [price]
   - Liquidity pool lows: [price]
   - BOS level: [price]
   - CHoCH level: [price]

4. Volume analysis:
   - Volume trend (increasing/decreasing)
   - Volume divergence: [yes/no]
   - Average volume: [value]

## ФОРМАТ ВЫВОДА:

```
HTF_STRUCTURE:
- trend: [Bullish/Bearish/Range]
- bos_level: [price — Break of Structure]
- choch_level: [price — Change of Character, or N/A]
- current_zone: [Premium/Discount/Equilibrium]
- range: [low] — [high]

KEY_LEVELS:
- h4_bullish_ob: [price range]
- h4_bearish_ob: [price range]
- liquidity_high: [price]
- liquidity_low: [price]
- equilibrium: [price]

VOLUME:
- trend: [Increasing/Decreasing/Flat]
- divergence: [Yes/No — bearish/bullish]
- avg_volume: [value]

BIAS:
- direction: [Bullish/Bearish/Neutral]
- reasoning: [2 предложения — почему]

TRADE_PLAN:
- preferred_direction: [Buy/Sell/Wait]
- entry_zone: [price range — в premium/discount]
- stop_loss: [price — за H4 OB]
- take_profit_1: [price — liquidity pool]
- take_profit_2: [price — next structure level]
- risk_reward: [ratio]
- time_horizon: [4-24 hours]
- confidence: [High/Medium/Low]
```

Запиши в файл reports/smart_money_4h.md
```

---

## ЧАСТЬ 3: Интеграция новых агентов в пайплайн

### 3.1 Порядок агентов (обновлённый)

```
Phase 0: Data Collection (data_collector.py)
Phase 1: Market Analyst (market.md)
Phase 2: Sentiment Analyst (sentiment.md)
Phase 3: News Analyst (news.md)
Phase 4: Fundamentals Analyst (fundamentals.md)
Phase 5: Smart Money 4H (smart_money_4h.md)        ← НОВЫЙ
Phase 6: Smart Money 15M (smart_money_15m.md)       ← НОВЫЙ
Phase 7: Bull Researcher (bull_case.md)
Phase 8: Bear Researcher (bear_case.md)
Phase 9: Research Manager (research_plan.md)
Phase 10: Trader (trader_proposal.md)
Phase 11: Risk Aggressive (risk_aggressive.md)
Phase 12: Risk Conservative (risk_conservative.md)
Phase 13: Risk Neutral (risk_neutral.md)
Phase 14: Portfolio Manager (final_decision.md)
```

### 3.2 Изменения в orchestrator.py

Добавить в `PIPELINE_STAGES`:
```python
("smart_money_4h", "smart_money_4h.md", "reports/smart_money_4h.md"),
("smart_money_15m", "smart_money_15m.md", "reports/smart_money_15m.md"),
```

Добавить в `format_kwargs`:
```python
format_kwargs["atr"] = parse_atr(run_dir)  # ATR для валидации стопов
```

### 3.3 Изменения в промптах других агентов

**market_analyst.md** — добавить:
```markdown
Также прочитай reports/smart_money_4h.md для HTF контекста.
```

**research_manager.md** — добавить:
```markdown
Прочитай также:
- reports/smart_money_4h.md (HTF структура)
- reports/smart_money_15m.md (micro entry zones)
Учитывай Smart Money уровни при принятии решения.
```

**portfolio_manager.md** — добавить:
```markdown
Прочитай также:
- reports/smart_money_4h.md (HTF контекста)
- reports/smart_money_15m.md (точные entry zones)
Используй Smart Money уровни для уточнения entry/stop.
```

### 3.4 Изменения в LangGraph pipeline

В `tradingagents/graph/setup.py` или `tradingagents/agents/`:
- Создать `tradingagents/agents/analysts/smart_money_4h.py`
- Создать `tradingagents/agents/analysts/smart_money_15m.py`
- Добавить в граф как отдельные ноды перед researchers

---

## ЧАСТЬ 4: Дополнительные улучшения (будущее)

### 4.1 Backtesting Integration
- Сохранять все решения в БД (SQLite)
- Сравнивать prediction vs reality через N дней
- Метрики: win rate, avg R:R, max drawdown, Sharpe ratio

### 4.2 Web Dashboard — Backtest View
- График: prediction entry/stop/TP vs реальная цена
- Win/Loss статистика по агентам
- Кто из агентов чаще ошибается

### 4.3 Adaptive Risk Management
- Если 3 сделки подряд убыточные → автоматически уменьшить risk до 0.5%
- Если 5 сделок прибыльных → увеличить risk до 1.5%
- Circuit breaker: 5 убыточных подряд → стоп на 24ч

### 4.4 News Impact Scoring
- Автоматически определять "высокоimpact" новости (NFP, CPI, FOMC)
- За 30 мин до новости → не входить / закрыть позицию
- После новости → ждать 15 мин перед входом

### 4.5 Correlation Check
- Если анализируем BTC и Gold — проверить корреляцию
- Не открывать одновременно 2 позиции в одном направлении на коррелирующих активах

### 4.6 Multi-Timeframe Confirmation
- 4H даёт направление (bias)
- 1H даёт entry zone
- 15M даёт точный триггер
- Вход ТОЛЬКО когда все 3 совпадают

---

## ЧАСТЬ 5: Тестирование

### 5.1 Unit тесты для entry_validator.py
```python
def test_entry_within_30pts():
    result = validate_entry_levels(4200, 4150, 4260, 4187.30, "Buy")
    assert result.is_valid

def test_entry_too_far():
    result = validate_entry_levels(4400, 4350, 4500, 4187.30, "Buy")
    assert not result.is_valid
    assert result.entry_price == 4187.30

def test_stop_too_large():
    result = validate_entry_levels(4200, 4500, 4300, 4187.30, "Sell")
    assert not result.is_valid
    assert abs(result.stop_loss - 4200) <= 100

def test_lot_size_calculation():
    lot = calculate_lot_size(4200, 4150, 10000, 0.01)
    assert lot == 0.02  # $100 risk / 50 pts / $10 = 0.2 lots
```

### 5.2 Integration тест
- Запустить полный пайплайн на XAU-USD
- Проверить что все 14 агентов отработали
- Проверить что entry/stop в final_decision валидированы
- Проверить что Smart Money отчёты созданы

### 5.3 Regression тест
- Запустить на 5 прошлых дат
- Сравнить новые результаты со старыми
- Убедиться что старые ошибки исправлены

---

## ЧЕКЛИСТ ВЫПОЛНЕНИЯ

- [ ] 1.1 PM валидация (portfolio_manager.md + orchestrator.py)
- [ ] 1.2 Согласование Trader↔PM (entry_validator.py + orchestrator.py)
- [ ] 1.3 Текущая цена в risk analysts (3 промпта)
- [ ] 1.4 Расчёт lot size (entry_validator.py + portfolio_manager.md)
- [ ] 1.5 Trailing stop правила (portfolio_manager.md)
- [ ] 1.6 ATR-based стоп (entry_validator.py + orchestrator.py)
- [ ] 2.1 Smart Money 15M agent (промпт + интеграция)
- [ ] 2.2 Smart Money 4H agent (промпт + интеграция)
- [ ] 3.1 Обновить PIPELINE_STAGES в orchestrator.py
- [ ] 3.2 Обновить промпты: market, research_manager, portfolio_manager
- [ ] 3.3 LangGraph pipeline: новые ноды
- [ ] 4.1 Тесты entry_validator
- [ ] 4.2 Интеграционный тест
- [ ] README обновить

---

## ПРИМЕР ИСПОЛЬЗОВАНИЯ

```bash
# Запуск с новыми агентами
python opencode_pipeline/orchestrator.py XAU-USD --trade_date 2026-07-07

# Результат: 14 отчётов в runs/XAU-USD_2026-07-07_<ts>/reports/
# - market.md
# - sentiment.md
# - news.md
# - fundamentals.md
# - smart_money_4h.md        ← НОВЫЙ
# - smart_money_15m.md       ← НОВЫЙ
# - bull_case.md
# - bear_case.md
# - research_plan.md
# - trader_proposal.md       ← валидирован
# - risk_aggressive.md
# - risk_conservative.md
# - risk_neutral.md
# - final_decision.md        ← валидирован + согласован с trader
```
