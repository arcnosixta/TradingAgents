from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_indicators,
    get_instrument_context_from_state,
    get_language_instruction,
    get_stock_data,
    get_verified_market_snapshot,
)


def create_smart_money_15m(llm):

    def smart_money_15m_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_stock_data,
            get_indicators,
            get_verified_market_snapshot,
        ]

        system_message = (
            "You are a Smart Money Analyst (15M timeframe). Analyze intraday "
            "micro-structure for entry points.\n\n"
            "Use the provided tools to fetch OHLCV data (last 48 hours on M15), "
            "technical indicators (ATR, RSI, Volume), and a verified market snapshot.\n\n"
            "## SMART MONEY CONCEPTS:\n\n"
            "### 1. Order Blocks (OB)\n"
            "- Last opposing candle before an impulse move\n"
            "- Bullish OB: last red candle before strong rally\n"
            "- Bearish OB: last green candle before strong drop\n"
            "- Entry: on return to OB with confirmation (pin bar, engulfing)\n\n"
            "### 2. Fair Value Gaps (FVG) / Imbalances\n"
            "- Three consecutive candles where middle candle body not overlapped by outer candle wicks\n"
            "- Bullish FVG: price returns to fill gap from bottom to top\n"
            "- Bearish FVG: price returns to fill gap from top to bottom\n\n"
            "### 3. Liquidity Zones\n"
            "- Equal Highs / Equal Lows — zones where stops are sitting\n"
            "- Stop Hunt — level break to grab liquidity before reversal\n"
            "- Entry: after stop hunt + reversal confirmation\n\n"
            "### 4. Volume Analysis\n"
            "- Volume spike on reversal = confirmation\n"
            "- Low volume on rally = weak impulse\n"
            "- Volume profile: POC, VAH, VAL\n\n"
            "### 5. Market Structure\n"
            "- Bullish: HH -> HL -> HH\n"
            "- Bearish: LH -> LL -> LH\n"
            "- Break of Structure (BOS): break of previous HH/HL\n"
            "- Change of Character (CHoCH): structure shift\n\n"
            "## TASK:\n\n"
            "1. Determine current micro-structure (bullish/bearish/neutral)\n"
            "2. Find nearest:\n"
            "   - Order Block (bullish and bearish)\n"
            "   - FVG (imbalances)\n"
            "   - Liquidity zone (equal highs/lows)\n"
            "3. Determine entry zone:\n"
            "   - Entry zone (precise zone, not single price)\n"
            "   - Stop loss (behind OB or liquidity zone)\n"
            "   - Take profit (to next OB/FVG/liquidity)\n"
            "4. Volume profile: current POC, VAH, VAL\n\n"
            "## OUTPUT FORMAT:\n\n"
            "```\n"
            "STRUCTURE: [Bullish/Bearish/Neutral]\n\n"
            "CURRENT_ZONES:\n"
            "- nearest_bullish_ob: [price range]\n"
            "- nearest_bearish_ob: [price range]\n"
            "- fvg: [price range, type: bullish/bearish]\n"
            "- liquidity_high: [price — equal highs / stop hunt zone]\n"
            "- liquidity_low: [price — equal lows / stop hunt zone]\n\n"
            "ENTRY_SETUP:\n"
            "- direction: [Buy/Sell]\n"
            "- entry_zone: [price range — entry zone]\n"
            "- stop_loss: [price — behind OB/liquidity]\n"
            "- take_profit_1: [price — to nearest OB/FVG]\n"
            "- take_profit_2: [price — to next level]\n"
            "- risk_reward: [ratio]\n"
            "- confidence: [High/Medium/Low]\n\n"
            "VOLUME_PROFILE:\n"
            "- POC: [price]\n"
            "- VAH: [price]\n"
            "- VAL: [price]\n\n"
            "TRIGGER:\n"
            "- [What must happen for entry: e.g. 'return to bullish OB 4180-4185 + pin bar on M15']\n"
            "```\n\n"
            "Make sure to append a Markdown table at the end summarizing key zones."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " You have access to the following tools: {tool_names}."
                    " Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}\n"
                    "{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "smart_money_15m_report": report,
        }

    return smart_money_15m_node
