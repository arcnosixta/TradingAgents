from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_indicators,
    get_instrument_context_from_state,
    get_language_instruction,
    get_stock_data,
    get_verified_market_snapshot,
)


def create_smart_money_4h(llm):

    def smart_money_4h_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_stock_data,
            get_indicators,
            get_verified_market_snapshot,
        ]

        system_message = (
            "You are a Smart Money Analyst (4H timeframe). Analyze swing structure "
            "for the next 4-24 hours.\n\n"
            "Use the provided tools to fetch OHLCV data (last 30 days on H4), "
            "technical indicators (SMA 50/200, RSI, MACD, ATR), and a verified "
            "market snapshot.\n\n"
            "## SMART MONEY CONCEPTS (4H):\n\n"
            "### 1. Higher Timeframe Structure (HTF)\n"
            "- Determine the main trend on H4: HH/HL (bullish) or LH/LL (bearish)\n"
            "- BOS (Break of Structure): where the break occurred\n"
            "- CHoCH (Change of Character): where the trend changed\n"
            "- Key levels: previous HH, HL, LH, LL\n\n"
            "### 2. Premium/Discount Zones\n"
            "- Premium: above 50% of range (sells only here)\n"
            "- Discount: below 50% of range (buys only here)\n"
            "- Equilibrium: 50% — balance zone\n"
            "- Entries ONLY in premium (for sell) or discount (for buy)\n\n"
            "### 3. Order Blocks on H4\n"
            "- H4 OB stronger than M15/M1\n"
            "- Search: last candle before impulse on H4\n"
            "- OB zone: candle body +/- ATR/4\n\n"
            "### 4. Liquidity Pools\n"
            "- Equal highs/lows on H4 — major liquidity zones\n"
            "- Stop hunt before major levels\n"
            "- Liquidity sweep -> reversal\n\n"
            "### 5. Divergence + Structure\n"
            "- RSI divergence on H4 = strong signal\n"
            "- Volume divergence = weak momentum\n"
            "- MACD divergence on H4 = reversal likely\n\n"
            "## TASK:\n\n"
            "1. Determine HTF structure (H4):\n"
            "   - Current trend (bullish/bearish/range)\n"
            "   - BOS level (where structure broke)\n"
            "   - CHoCH level (where trend changed)\n\n"
            "2. Determine Premium/Discount:\n"
            "   - Current zone (premium/discount/equilibrium)\n"
            "   - Range: [low — high]\n\n"
            "3. Find key levels:\n"
            "   - H4 Order Block (bullish): [price range]\n"
            "   - H4 Order Block (bearish): [price range]\n"
            "   - Liquidity pool highs: [price]\n"
            "   - Liquidity pool lows: [price]\n"
            "   - BOS level: [price]\n"
            "   - CHoCH level: [price]\n\n"
            "4. Volume analysis:\n"
            "   - Volume trend (increasing/decreasing)\n"
            "   - Volume divergence: [yes/no]\n"
            "   - Average volume: [value]\n\n"
            "## OUTPUT FORMAT:\n\n"
            "```\n"
            "HTF_STRUCTURE:\n"
            "- trend: [Bullish/Bearish/Range]\n"
            "- bos_level: [price — Break of Structure]\n"
            "- choch_level: [price — Change of Character, or N/A]\n"
            "- current_zone: [Premium/Discount/Equilibrium]\n"
            "- range: [low] — [high]\n\n"
            "KEY_LEVELS:\n"
            "- h4_bullish_ob: [price range]\n"
            "- h4_bearish_ob: [price range]\n"
            "- liquidity_high: [price]\n"
            "- liquidity_low: [price]\n"
            "- equilibrium: [price]\n\n"
            "VOLUME:\n"
            "- trend: [Increasing/Decreasing/Flat]\n"
            "- divergence: [Yes/No — bearish/bullish]\n"
            "- avg_volume: [value]\n\n"
            "BIAS:\n"
            "- direction: [Bullish/Bearish/Neutral]\n"
            "- reasoning: [2 sentences — why]\n\n"
            "TRADE_PLAN:\n"
            "- preferred_direction: [Buy/Sell/Wait]\n"
            "- entry_zone: [price range — in premium/discount]\n"
            "- stop_loss: [price — behind H4 OB]\n"
            "- take_profit_1: [price — liquidity pool]\n"
            "- take_profit_2: [price — next structure level]\n"
            "- risk_reward: [ratio]\n"
            "- time_horizon: [4-24 hours]\n"
            "- confidence: [High/Medium/Low]\n"
            "```\n\n"
            "Make sure to append a Markdown table at the end summarizing key levels."
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
            "smart_money_4h_report": report,
        }

    return smart_money_4h_node
