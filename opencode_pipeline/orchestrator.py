import os
import argparse
import datetime
import logging
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.agents.utils.agent_utils import resolve_instrument_identity, build_instrument_context
from tradingagents.agents.utils.entry_validator import (
    parse_current_price_from_snapshot,
    apply_validation_to_report,
    validate_consistency,
    parse_trader_proposal,
    parse_atr_from_indicators,
)
from data_collector import collect_data
from agent_runner import run_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pipeline phases with dependency-aware parallelism
# ---------------------------------------------------------------------------
# Each phase is a list of (role, prompt_file, output_file) tuples.
# Agents within the same phase run in parallel; phases run sequentially.
# ---------------------------------------------------------------------------
PIPELINE_PHASES = [
    # Phase 1: Independent analysts — read only data/* files
    [
        ("market", "market_analyst.md", "reports/market.md"),
        ("sentiment", "sentiment_analyst.md", "reports/sentiment.md"),
        ("news", "news_analyst.md", "reports/news.md"),
        ("fundamentals", "fundamentals_analyst.md", "reports/fundamentals.md"),
    ],
    # Phase 2: Smart Money — depend on reports/market.md
    [
        ("smart_money_4h", "smart_money_4h.md", "reports/smart_money_4h.md"),
        ("smart_money_15m", "smart_money_15m.md", "reports/smart_money_15m.md"),
    ],
    # Phase 3-10: Sequential chain (each reads prior output)
    [("bull_researcher", "bull_researcher.md", "reports/bull_case.md")],
    [("bear_researcher", "bear_researcher.md", "reports/bear_case.md")],
    [("research_manager", "research_manager.md", "reports/research_plan.md")],
    [("trader", "trader.md", "reports/trader_proposal.md")],
    [("risk_aggressive", "risk_aggressive.md", "reports/risk_aggressive.md")],
    [("risk_conservative", "risk_conservative.md", "reports/risk_conservative.md")],
    [("risk_neutral", "risk_neutral.md", "reports/risk_neutral.md")],
    [("portfolio_manager", "portfolio_manager.md", "reports/final_decision.md")],
]

# Flat list for backward compatibility (e.g. total agent count)
PIPELINE_STAGES = [stage for phase in PIPELINE_PHASES for stage in phase]
TOTAL_AGENTS = len(PIPELINE_STAGES)

# Phase labels for progress reporting
PHASE_LABELS = [
    "Analysts",
    "Smart Money",
    "Bull Research",
    "Bear Research",
    "Research Manager",
    "Trader",
    "Risk Aggressive",
    "Risk Conservative",
    "Risk Neutral",
    "Portfolio Manager",
]


def _run_single_agent(role, prompt_path, format_kwargs, run_dir, output_file, models=None):
    """Run one agent and return (role, status, elapsed)."""
    start_t = time.time()
    try:
        run_agent(role, prompt_path, format_kwargs, run_dir, output_file, models=models)
        status = "success"
    except Exception as e:
        logger.error(f"Failed {role}: {e}")
        status = f"failed: {e}"
    elapsed = time.time() - start_t
    return role, status, elapsed


def _run_phase(agents, prompts_dir, format_kwargs, run_dir, max_workers=None, models=None):
    """Run a list of agents in parallel, return dict of {role: {status, elapsed}}."""
    results = {}
    if len(agents) == 1:
        role, prompt_file, output_file = agents[0]
        logger.info(f"--- Running {role} ---")
        prompt_path = os.path.join(prompts_dir, prompt_file)
        role, status, elapsed = _run_single_agent(
            role, prompt_path, format_kwargs, run_dir, output_file, models=models,
        )
        results[role] = {"status": status, "elapsed_seconds": round(elapsed, 2)}
    else:
        workers = max_workers or len(agents)
        role_names = [a[0] for a in agents]
        logger.info(f"--- Running parallel: {', '.join(role_names)} ---")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for role, prompt_file, output_file in agents:
                prompt_path = os.path.join(prompts_dir, prompt_file)
                fut = pool.submit(
                    _run_single_agent,
                    role, prompt_path, format_kwargs, run_dir, output_file, models,
                )
                futures[fut] = role

            for fut in as_completed(futures):
                role, status, elapsed = fut.result()
                logger.info(f"  {role} done ({elapsed:.1f}s) — {status}")
                results[role] = {"status": status, "elapsed_seconds": round(elapsed, 2)}
    return results


def main():
    parser = argparse.ArgumentParser(description="Run TradingAgents OpenCode Pipeline")
    parser.add_argument("ticker", nargs="?", default="XAU-USD", help="Ticker symbol (default: XAU-USD)")
    parser.add_argument("--trade_date", default=datetime.datetime.now().strftime("%Y-%m-%d"), help="Trade date YYYY-MM-DD")
    parser.add_argument("--max_workers", type=int, default=4, help="Max parallel agents per phase (default: 4)")
    parser.add_argument(
        "--models",
        help="Comma-separated model IDs for fallback chain "
             "(e.g. 'opencode/mimo-v2.5-free,opencode/big-pickle'). "
             "Overrides OPENCODE_MODELS env and defaults.",
    )
    args = parser.parse_args()

    ticker = args.ticker
    trade_date = args.trade_date
    max_workers = args.max_workers
    models = [m.strip() for m in args.models.split(",") if m.strip()] if args.models else None

    end_date_dt = datetime.datetime.strptime(trade_date, "%Y-%m-%d")
    start_date_dt = end_date_dt - datetime.timedelta(days=365) # 1 year of data
    start_date = start_date_dt.strftime("%Y-%m-%d")
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs", f"{ticker}_{trade_date}_{timestamp}")
    
    os.makedirs(run_dir, exist_ok=True)
    reports_dir = os.path.join(run_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    
    logger.info(f"Starting pipeline for {ticker} at {trade_date}")
    logger.info(f"Run directory: {run_dir}")
    logger.info(f"Max parallel workers: {max_workers}")
    if models:
        logger.info(f"Model fallback chain: {models}")
    else:
        from agent_runner import _get_model_chain
        logger.info(f"Model fallback chain (default): {_get_model_chain()}")
    
    # Phase 0: Collect Data
    logger.info("=== Phase 0: Data Collection ===")
    collect_data(ticker, start_date, trade_date, trade_date, run_dir)
    
    # Extract current price from snapshot for trader prompt
    snapshot_path = os.path.join(run_dir, "data", "snapshot.md")
    current_price_data = parse_current_price_from_snapshot(snapshot_path)
    if current_price_data:
        logger.info(f"Current price from snapshot: close={current_price_data['close']}, "
                     f"high={current_price_data['high']}, low={current_price_data['low']}")
    else:
        logger.warning("Could not parse current price from snapshot, using defaults")
        current_price_data = {"close": 0.0, "high": 0.0, "low": 0.0}
    
    # Memory past context
    memory = TradingMemoryLog(DEFAULT_CONFIG)
    past_context = memory.get_past_context(ticker, n_same=5, n_cross=3)
    if past_context:
        with open(os.path.join(run_dir, "data", "past_context.md"), "w") as f:
            f.write(past_context)
            
    # Resolve instrument context for prompts
    identity = resolve_instrument_identity(ticker)
    instrument_context = build_instrument_context(ticker, "stock", identity)

    format_kwargs = {
        "ticker": ticker,
        "trade_date": trade_date,
        "start_date": start_date,
        "end_date": trade_date,
        "instrument_context": instrument_context,
        "current_price": current_price_data["close"],
        "day_high": current_price_data["high"],
        "day_low": current_price_data["low"],
    }

    # Parse ATR from indicators for stop validation
    indicators_path = os.path.join(run_dir, "data", "indicators.md")
    atr = parse_atr_from_indicators(indicators_path)
    if atr is not None:
        logger.info(f"ATR from indicators: {atr}")
        format_kwargs["atr"] = atr
    else:
        logger.info("ATR not found in indicators, using default stop bounds")

    prompts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")

    run_log = {}
    agents_done = 0
    
    # Run phases with parallelism
    for phase_idx, agents in enumerate(PIPELINE_PHASES):
        phase_label = PHASE_LABELS[phase_idx] if phase_idx < len(PHASE_LABELS) else f"Phase {phase_idx}"
        logger.info(f"=== Phase {phase_idx + 1}/{len(PIPELINE_PHASES)}: {phase_label} ===")

        phase_results = _run_phase(agents, prompts_dir, format_kwargs, run_dir, max_workers, models=models)
        run_log.update(phase_results)
        agents_done += len(agents)
        logger.info(f"--- Agents done: {agents_done}/{TOTAL_AGENTS} ---")

        # Post-phase validation hooks
        for role, _pf, output_file in agents:
            status = phase_results.get(role, {}).get("status", "")

            # Validate trader entry/stop levels after trader stage
            if role == "trader" and status == "success":
                trader_report = os.path.join(run_dir, output_file)
                if current_price_data["close"] > 0:
                    result = apply_validation_to_report(
                        trader_report, current_price_data["close"], atr=atr
                    )
                    if result and not result.is_valid:
                        logger.warning(f"Trader entry/stop corrected: {result.summary}")
                    elif result:
                        logger.info("Trader entry/stop validated: PASS")

            # Validate PM final_decision + consistency with trader
            if role == "portfolio_manager" and status == "success":
                pm_report = os.path.join(run_dir, output_file)
                if current_price_data["close"] > 0:
                    result = apply_validation_to_report(
                        pm_report, current_price_data["close"], atr=atr
                    )
                    if result and not result.is_valid:
                        logger.warning(f"PM entry/stop corrected: {result.summary}")
                    elif result:
                        logger.info("PM entry/stop validated: PASS")

                    trader_path = os.path.join(run_dir, "reports/trader_proposal.md")
                    if os.path.exists(trader_path):
                        trader_text = open(trader_path, encoding="utf-8").read()
                        pm_text = open(pm_report, encoding="utf-8").read()
                        trader_parsed = parse_trader_proposal(trader_text)
                        pm_parsed = parse_trader_proposal(pm_text)
                        corrected_entry, warnings = validate_consistency(
                            trader_parsed["entry_price"],
                            pm_parsed["entry_price"],
                        )
                        for w in warnings:
                            logger.warning(w)
                        if corrected_entry != pm_parsed["entry_price"] and corrected_entry is not None:
                            import re as _re
                            pm_corrected = _re.sub(
                                r"(ENTRY_PRICE|Entry)[:\s]+[\d,]+\.?\d*",
                                f"\\g<1>: {corrected_entry}",
                                pm_text,
                                flags=_re.IGNORECASE,
                            )
                            with open(pm_report, "w", encoding="utf-8") as f:
                                f.write(pm_corrected)
                            logger.info(f"PM entry corrected to {corrected_entry} for consistency with Trader")

    with open(os.path.join(run_dir, "run_log.json"), "w") as f:
        json.dump(run_log, f, indent=2)
        
    # Final: Save to memory
    final_decision_path = os.path.join(reports_dir, "final_decision.md")
    if os.path.exists(final_decision_path):
        with open(final_decision_path, "r") as f:
            final_text = f.read()
            
        memory.store_decision(ticker, trade_date, final_text)
        logger.info("Saved final decision to memory log.")
    else:
        logger.warning("No final decision found to save.")
        
    logger.info("Pipeline complete.")

if __name__ == "__main__":
    main()
