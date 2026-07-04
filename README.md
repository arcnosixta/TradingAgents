# TradingAgents

Multi-agent LLM trading framework for intraday analysis. Runs 12 specialized AI agents sequentially to produce actionable trade signals.

## Quick Start

```bash
git clone https://github.com/arcnosixta/TradingAgents.git
cd TradingAgents
pip install .
```

## Two Ways to Run

### 1. OpenCode Pipeline (recommended)

Runs 12 agents via [OpenCode CLI](https://opencode.ai) with free models. No API keys needed.

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
| 5 | Bull Researcher | Argument FOR buying |
| 6 | Bear Researcher | Argument AGAINST buying |
| 7 | Research Manager | Final rating based on bull/bear debate |
| 8 | Trader | Entry/stop/take-profit for MT5 |
| 9 | Aggressive Risk | Max upside analysis |
| 10 | Conservative Risk | Capital preservation |
| 11 | Neutral Risk | Balanced assessment |
| 12 | Portfolio Manager | Final decision with lot size |

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
│   ├── dataflows/               # Data source adapters
│   ├── graph/                   # LangGraph orchestration
│   └── llm_clients/             # LLM provider abstraction
├── cli/                         # Interactive CLI
├── tests/                       # Test suite
└── opencode.json                # OpenCode config (mimo-v2.5-free)
```

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

## License

MIT
