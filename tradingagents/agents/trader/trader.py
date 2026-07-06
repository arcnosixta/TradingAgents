"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

import functools
import re

from langchain_core.messages import AIMessage

from tradingagents.agents.schemas import TraderProposal, render_trader_proposal
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.entry_validator import (
    parse_current_price_from_text,
    validate_entry_levels,
    parse_trader_proposal,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def _extract_current_price(state: dict) -> float | None:
    """Extract current price from market_report in state."""
    market_report = state.get("market_report", "")
    if not market_report:
        return None
    return parse_current_price_from_text(market_report)


def _validate_and_fix(raw_text: str, current_price: float | None) -> str:
    """Validate entry/stop levels and fix if needed."""
    if current_price is None or current_price <= 0:
        return raw_text

    parsed = parse_trader_proposal(raw_text)
    if parsed["action"] is None or parsed["action"] == "Hold":
        return raw_text

    result = validate_entry_levels(
        entry_price=parsed["entry_price"],
        stop_loss=parsed["stop_loss"],
        take_profit=parsed.get("take_profit"),
        current_price=current_price,
        action=parsed["action"],
    )

    if not result.is_valid:
        # Apply fixes to the raw text
        corrected = raw_text
        if result.entry_price is not None and parsed["entry_price"] != result.entry_price:
            corrected = re.sub(
                r"(ENTRY_PRICE[:\s]+)[\d,]+\.?\d*",
                f"\\g<1>{result.entry_price}",
                corrected,
                flags=re.IGNORECASE,
            )
        if result.stop_loss is not None and parsed["stop_loss"] != result.stop_loss:
            corrected = re.sub(
                r"(STOP_LOSS[:\s]+)[\d,]+\.?\d*",
                f"\\g<1>{result.stop_loss}",
                corrected,
                flags=re.IGNORECASE,
            )
        return corrected

    return raw_text


def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = get_instrument_context_from_state(state)
        investment_plan = state["investment_plan"]
        current_price = _extract_current_price(state)

        # Build current price context for the prompt
        price_context = ""
        if current_price and current_price > 0:
            price_context = (
                f"\n\nCURRENT MARKET PRICE: {current_price:.2f}\n"
                f"ENTRY_RULES:\n"
                f"- ENTRY_PRICE must be within 30 points of {current_price:.2f}\n"
                f"- STOP_LOSS max 100 points from ENTRY_PRICE\n"
                f"- If stop cannot fit in 100 points → choose Hold\n"
                f"- TAKE_PROFIT min 1:2 ratio to stop\n"
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a trading agent analyzing market data to make investment decisions. "
                    "Based on your analysis, provide a specific recommendation to buy, sell, or hold. "
                    "Anchor your reasoning in the analysts' reports and the research plan."
                    f"{price_context}"
                    + get_language_instruction()
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Based on a comprehensive analysis by a team of analysts, here is an investment "
                    f"plan tailored for {company_name}. {instrument_context} This plan incorporates "
                    f"insights from current technical market trends, macroeconomic indicators, and "
                    f"social media sentiment. Use this plan as a foundation for evaluating your next "
                    f"trading decision.\n\nProposed Investment Plan: {investment_plan}\n\n"
                    f"Leverage these insights to make an informed and strategic decision."
                ),
            },
        ]

        trader_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            messages,
            render_trader_proposal,
            "Trader",
        )

        # Validate and fix entry/stop levels
        trader_plan = _validate_and_fix(trader_plan, current_price)

        return {
            "messages": [AIMessage(content=trader_plan)],
            "trader_investment_plan": trader_plan,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
